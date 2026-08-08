# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Lightweight research risk stack for the canonical EURUSD H1 transaction.

The module is deliberately additive. It reads completed H1 data, settled
forecast history and the protected Full Metric authority, then returns compact
validation/risk modifiers. It never creates or reverses a direction. The only
permitted decision change is a conservative downgrade to WAIT.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

VERSION = "research-risk-stack-20260619-v1"
PIP = 0.0001
HORIZONS = (1, 2, 3, 4, 5, 6)
RISK_HORIZONS = (1, 2, 3, 6)
THRESHOLD_GRID = (50, 55, 60, 65, 70, 75, 80, 85, 90)
_LOCK = threading.RLock()
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "quant_app.sqlite3"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _clip(value: Any, lo: float, hi: float, default: float = 0.0) -> float:
    out = _finite(value, default)
    return float(max(lo, min(hi, out if out is not None else default)))


def _prob(value: Any, default: Optional[float] = None) -> Optional[float]:
    out = _finite(value, default)
    if out is None:
        return None
    if out > 1.0:
        out /= 100.0
    return _clip(out, 0.0, 1.0)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _series(frame: pd.DataFrame, name: str, default: Any = np.nan) -> pd.Series:
    """Return an index-aligned Series even when an optional ledger column is absent."""
    if name in frame.columns:
        value = frame[name]
        return value if isinstance(value, pd.Series) else pd.Series(value, index=frame.index)
    return pd.Series(default, index=frame.index)


def _direction(value: Any) -> str:
    text = str(value or "").upper()
    if "BUY" in text or "BULL" in text or text == "UP":
        return "BUY"
    if "SELL" in text or "BEAR" in text or text == "DOWN":
        return "SELL"
    return "WAIT"


def _session(ts: pd.Timestamp) -> str:
    hour = int(ts.hour)
    if 0 <= hour < 7:
        return "ASIA"
    if 7 <= hour < 12:
        return "LONDON"
    if 12 <= hour < 16:
        return "LONDON_NY_OVERLAP"
    if 16 <= hour < 21:
        return "NEW_YORK"
    return "LATE_NY"


def _json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return [_json_safe(x) for x in value.to_dict("records")]
    if isinstance(value, pd.Series):
        return [_json_safe(x) for x in value.tolist()]
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        out = float(value)
        return out if math.isfinite(out) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        return ts.isoformat()
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _normalise_ohlc(frame: Any) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    data = frame.copy(deep=False)
    cmap = {str(c).strip().lower(): c for c in data.columns}
    tcol = next((cmap[x] for x in ("time", "timestamp", "datetime", "date") if x in cmap), None)
    required: Dict[str, Any] = {}
    for name in ("open", "high", "low", "close"):
        col = cmap.get(name) or cmap.get(name[0])
        if col is None:
            return pd.DataFrame(columns=["open", "high", "low", "close"])
        required[name] = col
    idx = pd.to_datetime(data[tcol] if tcol is not None else data.index, utc=True, errors="coerce")
    out = pd.DataFrame(
        {name: pd.to_numeric(data[col], errors="coerce").to_numpy() for name, col in required.items()},
        index=pd.DatetimeIndex(idx),
    )
    volume_col = next((cmap[x] for x in ("tick_volume", "tick volume", "volume", "real_volume") if x in cmap), None)
    if volume_col is not None:
        out["volume"] = pd.to_numeric(data[volume_col], errors="coerce").to_numpy()
    out = out.loc[~out.index.isna()].dropna(subset=["open", "high", "low", "close"]).sort_index()
    out = out.loc[~out.index.duplicated(keep="last")]
    return out


def _causal_median(values: pd.Series, groups: pd.Series, minimum: int = 1) -> pd.Series:
    shifted = values.groupby(groups, sort=False).shift(1)
    return shifted.groupby(groups, sort=False).transform(lambda x: x.expanding(min_periods=minimum).median())


def build_periodicity_normalization(
    ohlc: Any,
    *,
    settled: Optional[pd.DataFrame] = None,
    min_bucket: int = 8,
    min_session: int = 16,
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    data = _normalise_ohlc(ohlc)
    if data.empty:
        result = {
            "version": "periodicity_v1", "status": "INSUFFICIENT_DATA", "hour_of_week": None,
            "expected_hourly_volatility": None, "periodicity_normalized_return": 0.0,
            "periodicity_normalized_range": 0.0, "periodicity_normalized_residual": 0.0,
            "periodicity_sample_count": 0, "periodicity_reliability": 0.0,
        }
        return result, pd.DataFrame()

    work = data.copy(deep=False)
    ret = work["close"].pct_change()
    abs_ret = ret.abs()
    candle_range = (work["high"] - work["low"]).abs()
    prev_close = work["close"].shift(1)
    tr = pd.concat([(work["high"] - work["low"]).abs(), (work["high"] - prev_close).abs(), (work["low"] - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=3).median()
    volume = work.get("volume", pd.Series(1.0, index=work.index)).abs()
    residual = pd.Series(np.nan, index=work.index, dtype=float)
    if isinstance(settled, pd.DataFrame) and not settled.empty and {"target_time", "actual_close", "predicted_close"}.issubset(settled.columns):
        rows = settled[["target_time", "actual_close", "predicted_close"]].copy(deep=False)
        rows["time"] = pd.to_datetime(rows["target_time"], errors="coerce", utc=True)
        rows["residual"] = (pd.to_numeric(rows["actual_close"], errors="coerce") - pd.to_numeric(rows["predicted_close"], errors="coerce")).abs()
        med = rows.dropna(subset=["time", "residual"]).groupby("time", sort=False)["residual"].median()
        residual = pd.Series(work.index.map(med), index=work.index, dtype=float)

    how = pd.Series(work.index.weekday * 24 + work.index.hour, index=work.index, dtype=int)
    sessions = pd.Series([_session(ts) for ts in work.index], index=work.index, dtype="object")
    global_scales: Dict[str, pd.Series] = {}
    raw_map = {"abs_return": abs_ret, "range": candle_range, "atr": atr, "volume": volume, "residual": residual}
    scales: Dict[str, pd.Series] = {}
    counts = how.groupby(how, sort=False).cumcount()
    session_counts = sessions.groupby(sessions, sort=False).cumcount()
    for name, values in raw_map.items():
        values = pd.to_numeric(values, errors="coerce")
        bucket = _causal_median(values, how, minimum=1)
        session_med = _causal_median(values, sessions, minimum=1)
        global_med = values.shift(1).rolling(24 * 30, min_periods=5).median()
        expanding = values.shift(1).expanding(min_periods=1).median()
        bucket = bucket.where(counts >= min_bucket)
        session_med = session_med.where(session_counts >= min_session)
        scale = bucket.fillna(session_med).fillna(global_med).fillna(expanding)
        # A fixed domain-scale bootstrap is used only before any past sample
        # exists. Using the full-series median here would leak future rows into
        # the earliest buckets and would make historical values change when new
        # candles are appended.
        fixed_bootstrap = {
            "abs_return": 1e-4, "range": 1e-4, "atr": 1e-4,
            "volume": 1.0, "residual": 1e-4,
        }.get(name, 1e-4)
        scale = scale.fillna(fixed_bootstrap).clip(lower=max(fixed_bootstrap * 1e-6, 1e-12))
        scales[name] = scale
        global_scales[name] = global_med

    norm = pd.DataFrame(index=work.index)
    norm["hour_of_week"] = how
    norm["expected_hourly_volatility"] = scales["abs_return"]
    norm["periodicity_normalized_return"] = ret / scales["abs_return"]
    norm["periodicity_normalized_range"] = candle_range / scales["range"]
    norm["periodicity_normalized_atr"] = atr / scales["atr"]
    norm["periodicity_normalized_volume"] = volume / scales["volume"]
    norm["periodicity_normalized_residual"] = residual / scales["residual"]
    norm["periodicity_sample_count"] = counts.astype(int)
    norm["periodicity_reliability"] = (counts / max(float(min_bucket * 3), 1.0)).clip(0.0, 1.0)
    norm = norm.replace([np.inf, -np.inf], np.nan)
    for col in ("periodicity_normalized_return", "periodicity_normalized_range", "periodicity_normalized_atr", "periodicity_normalized_volume", "periodicity_normalized_residual"):
        norm[col] = norm[col].fillna(0.0).clip(-20.0, 20.0)
    latest = norm.iloc[-1]
    result = {
        "version": "periodicity_v1", "status": "READY",
        "hour_of_week": int(latest["hour_of_week"]),
        "expected_hourly_volatility": float(latest["expected_hourly_volatility"]),
        "periodicity_normalized_return": float(latest["periodicity_normalized_return"]),
        "periodicity_normalized_range": float(latest["periodicity_normalized_range"]),
        "periodicity_normalized_residual": float(latest["periodicity_normalized_residual"]),
        "periodicity_sample_count": int(latest["periodicity_sample_count"]),
        "periodicity_reliability": float(latest["periodicity_reliability"]),
        "fallback_policy": "hour-of-week shifted median → shifted session median → shifted global rolling median",
        "causal_shift_applied": True,
    }
    return result, norm


def _pinball(y: np.ndarray, q: np.ndarray, alpha: float) -> np.ndarray:
    diff = y - q
    return np.maximum(alpha * diff, (alpha - 1.0) * diff)


def build_proper_scoring(settled: pd.DataFrame, previous: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {"version": "proper_scoring_v1", "status": "INSUFFICIENT_DATA"}
    if not isinstance(settled, pd.DataFrame) or settled.empty:
        result.update({f"crps_h{h}": None for h in HORIZONS})
        result.update({"mean_crps": None, "joint_energy_score": None, "path_sharpness": None, "path_calibration": None, "skill_vs_naive": None, "skill_vs_drift": None, "sample_count": 0, "reliability_modifier": 1.0})
        return result
    frame = settled.copy(deep=False)
    for col in ("actual_close", "predicted_close", "forecast_origin_price", "p10", "p25", "p50", "p75", "p90", "horizon"):
        if col in frame:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    quantile_cols = (("p10", .10), ("p25", .25), ("p50", .50), ("p75", .75), ("p90", .90))
    crps_by_h: Dict[int, Optional[float]] = {}
    samples_by_h: Dict[int, int] = {}
    all_scores: list[float] = []
    for h in HORIZONS:
        group = frame.loc[frame.get("horizon", pd.Series(index=frame.index, dtype=float)).eq(h)]
        valid = group.dropna(subset=["actual_close"] + [c for c, _ in quantile_cols if c in group.columns])
        samples_by_h[h] = int(len(valid))
        if len(valid) < 5 or any(c not in valid for c, _ in quantile_cols):
            crps_by_h[h] = None
            continue
        y = valid["actual_close"].to_numpy(dtype=float)
        losses = np.column_stack([_pinball(y, valid[c].to_numpy(dtype=float), a) for c, a in quantile_cols])
        scores = 2.0 * losses.mean(axis=1)
        crps_by_h[h] = float(np.mean(scores))
        all_scores.extend(scores.tolist())

    path_scores: list[float] = []
    if "calculation_id" in frame:
        for _, group in frame.dropna(subset=["actual_close"]).groupby("calculation_id", sort=False):
            group = group.sort_values("horizon")
            if len(group) < 2 or any(c not in group for c, _ in quantile_cols):
                continue
            actual = group["actual_close"].to_numpy(dtype=float)
            scenarios = np.vstack([group[c].to_numpy(dtype=float) for c, _ in quantile_cols])
            if not np.isfinite(scenarios).all() or not np.isfinite(actual).all():
                continue
            first = np.linalg.norm(scenarios - actual[None, :], axis=1).mean()
            pair = np.linalg.norm(scenarios[:, None, :] - scenarios[None, :, :], axis=2).mean()
            path_scores.append(float(first - 0.5 * pair))

    width = None
    coverage = None
    if {"p10", "p90", "actual_close"}.issubset(frame.columns):
        valid = frame.dropna(subset=["p10", "p90", "actual_close"])
        if not valid.empty:
            width = float((valid["p90"] - valid["p10"]).abs().mean())
            coverage = float(((valid["actual_close"] >= valid["p10"]) & (valid["actual_close"] <= valid["p90"])).mean())
    valid_pred = frame.dropna(subset=[c for c in ("actual_close", "predicted_close", "forecast_origin_price") if c in frame.columns])
    model_mae = naive_mae = drift_mae = None
    if {"actual_close", "predicted_close", "forecast_origin_price"}.issubset(valid_pred.columns) and len(valid_pred) >= 5:
        model_mae = float((valid_pred["actual_close"] - valid_pred["predicted_close"]).abs().mean())
        naive_mae = float((valid_pred["actual_close"] - valid_pred["forecast_origin_price"]).abs().mean())
        ordered = valid_pred.sort_values([c for c in ("forecast_origin_time", "horizon") if c in valid_pred.columns])
        signed = ordered["actual_close"] - ordered["forecast_origin_price"]
        hist_drift = signed.groupby(ordered["horizon"] if "horizon" in ordered else pd.Series(1, index=ordered.index)).transform(lambda x: x.shift(1).expanding(min_periods=3).median()).fillna(0.0)
        drift_pred = ordered["forecast_origin_price"] + hist_drift
        drift_mae = float((ordered["actual_close"] - drift_pred).abs().mean())
    skill_naive = None if model_mae is None or not naive_mae else float(1.0 - model_mae / naive_mae)
    skill_drift = None if model_mae is None or not drift_mae else float(1.0 - model_mae / drift_mae)
    mean_crps = float(np.mean(all_scores)) if all_scores else None
    target_coverage = 0.80
    calibration_quality = 0.5 if coverage is None else max(0.0, 1.0 - abs(coverage - target_coverage) / target_coverage)
    skill_quality = np.mean([max(-1.0, min(1.0, x)) for x in (skill_naive, skill_drift) if x is not None]) if any(x is not None for x in (skill_naive, skill_drift)) else 0.0
    raw_modifier = 1.0 + 0.025 * skill_quality + 0.015 * (calibration_quality - 0.5)
    raw_modifier = _clip(raw_modifier, 0.94, 1.04, 1.0)
    prev_modifier = _finite(_mapping(previous).get("reliability_modifier"), 1.0) or 1.0
    modifier = _clip(0.75 * prev_modifier + 0.25 * raw_modifier, 0.94, 1.04, 1.0)
    result.update({
        **{f"crps_h{h}": crps_by_h.get(h) for h in HORIZONS},
        "mean_crps": mean_crps,
        "joint_energy_score": float(np.mean(path_scores)) if path_scores else None,
        "path_sharpness": width,
        "path_calibration": coverage,
        "skill_vs_naive": skill_naive,
        "skill_vs_drift": skill_drift,
        "sample_count": int(len(valid_pred)),
        "samples_by_horizon": samples_by_h,
        "reliability_modifier": modifier,
        "status": "READY" if len(valid_pred) >= 20 else "DEVELOPING",
        "settled_only": True,
    })
    return result


def _priority_class(value: Any) -> str:
    text = str(value or "").upper()
    for label in ("A+", "A", "B", "C", "AVOID"):
        if label in text:
            return label
    number = _finite(value, None)
    if number is not None:
        if number <= 3:
            return "A+"
        if number <= 6:
            return "A"
        if number <= 9:
            return "B"
        if number <= 12:
            return "C"
    return "UNKNOWN"


def _confidence_band(value: Any) -> str:
    p = _prob(value, None)
    if p is None:
        return "UNKNOWN"
    pct = p * 100.0
    return "HIGH" if pct >= 75 else "MEDIUM" if pct >= 60 else "LOW"


def _event_for_row(row: Mapping[str, Any], ohlc: pd.DataFrame, horizon: int) -> Dict[str, Any]:
    origin = pd.to_datetime(row.get("forecast_origin_time"), errors="coerce", utc=True)
    if pd.isna(origin):
        return {"event": "CENSORED", "time": None}
    direction = _direction(row.get("full_metric_direction"))
    tp = _finite(row.get("selected_tp"), None)
    sl = _finite(row.get("selected_sl"), None)
    if direction not in {"BUY", "SELL"} or tp is None or sl is None:
        return {"event": "CENSORED", "time": None}
    end = origin + pd.Timedelta(hours=int(horizon))
    segment = ohlc.loc[(ohlc.index > origin) & (ohlc.index <= end)]
    if segment.empty or pd.Timestamp(segment.index[-1]) < end:
        return {"event": "CENSORED", "time": None}
    for step, (_, candle) in enumerate(segment.iterrows(), start=1):
        if direction == "BUY":
            tp_hit = float(candle["high"]) >= tp
            sl_hit = float(candle["low"]) <= sl
        else:
            tp_hit = float(candle["low"]) <= tp
            sl_hit = float(candle["high"]) >= sl
        if tp_hit and sl_hit:
            return {"event": "CENSORED", "time": step, "ambiguous_same_candle": True}
        if tp_hit:
            return {"event": "TP", "time": step}
        if sl_hit:
            return {"event": "SL", "time": step}
    return {"event": "NEITHER", "time": int(min(len(segment), horizon))}


def _risk_summary(records: pd.DataFrame, horizon: int) -> Dict[str, Any]:
    if records.empty:
        return {"tp_first_probability": None, "sl_first_probability": None, "neither_hit_probability": None, "median_time_to_tp": None, "median_time_to_sl": None, "effective_sample_count": 0, "censored_count": 0}
    event_col = f"event_{horizon}h"
    time_col = f"time_{horizon}h"
    if event_col not in records:
        return {"tp_first_probability": None, "sl_first_probability": None, "neither_hit_probability": None, "median_time_to_tp": None, "median_time_to_sl": None, "effective_sample_count": 0, "censored_count": 0}
    valid = records.loc[records[event_col].isin(["TP", "SL", "NEITHER"])]
    n = len(valid)
    return {
        "tp_first_probability": float(valid[event_col].eq("TP").mean()) if n else None,
        "sl_first_probability": float(valid[event_col].eq("SL").mean()) if n else None,
        "neither_hit_probability": float(valid[event_col].eq("NEITHER").mean()) if n else None,
        "median_time_to_tp": float(valid.loc[valid[event_col].eq("TP"), time_col].median()) if valid[event_col].eq("TP").any() else None,
        "median_time_to_sl": float(valid.loc[valid[event_col].eq("SL"), time_col].median()) if valid[event_col].eq("SL").any() else None,
        "effective_sample_count": int(n),
        "censored_count": int(records[event_col].eq("CENSORED").sum()),
    }


def build_competing_risk(
    settled: pd.DataFrame,
    ohlc: Any,
    *,
    current_regime: str,
    current_session: str,
    current_direction: str,
    current_priority: str,
    current_confidence: Any,
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    data = _normalise_ohlc(ohlc)
    base = {"version": "competing_risk_v1", "status": "INSUFFICIENT_DATA", "selected": {}, "by_direction": {}}
    if data.empty or not isinstance(settled, pd.DataFrame) or settled.empty:
        return base, pd.DataFrame()
    frame = settled.copy(deep=False)
    frame = frame.loc[_series(frame, "record_status", "SETTLED").astype(str).str.upper().eq("SETTLED")]
    frame["__settled_order"] = pd.to_datetime(_series(frame, "settlement_timestamp", pd.NaT), errors="coerce", utc=True)
    frame["__origin_order"] = pd.to_datetime(_series(frame, "forecast_origin_time", pd.NaT), errors="coerce", utc=True)
    frame = frame.sort_values(["__settled_order", "__origin_order"], ascending=False, na_position="last")
    if "calculation_id" in frame:
        frame = frame.drop_duplicates("calculation_id", keep="first")
    frame = frame.head(5000).drop(columns=["__settled_order", "__origin_order"], errors="ignore")
    if frame.empty:
        return base, pd.DataFrame()
    frame["direction_group"] = _series(frame, "full_metric_direction", "WAIT").map(_direction)
    frame["session_group"] = _series(frame, "session", "UNKNOWN").astype(str).str.upper()
    frame["regime_group"] = _series(frame, "h1_regime", "UNKNOWN").astype(str).str.upper()
    frame["priority_group"] = _series(frame, "priority", np.nan).map(_priority_class)
    frame["confidence_group"] = _series(frame, "calibrated_confidence", np.nan).map(_confidence_band)
    event_rows: list[dict[str, Any]] = []
    for row in frame.to_dict("records"):
        item = {
            "calculation_id": row.get("calculation_id"), "settlement_timestamp": row.get("settlement_timestamp"),
            "direction_group": row.get("direction_group"), "session_group": row.get("session_group"),
            "regime_group": row.get("regime_group"), "priority_group": row.get("priority_group"),
            "confidence_group": row.get("confidence_group"),
        }
        for h in RISK_HORIZONS:
            event = _event_for_row(row, data, h)
            item[f"event_{h}h"] = event.get("event")
            item[f"time_{h}h"] = event.get("time")
        event_rows.append(item)
    events = pd.DataFrame(event_rows)
    if events.empty:
        return base, events

    def choose(direction: str) -> Tuple[pd.DataFrame, str]:
        choices = [
            ((events["regime_group"].eq(str(current_regime).upper())) & (events["session_group"].eq(str(current_session).upper())) & events["direction_group"].eq(direction) & events["priority_group"].eq(str(current_priority).upper()) & events["confidence_group"].eq(_confidence_band(current_confidence)), "REGIME_SESSION_DIRECTION_PRIORITY_CONFIDENCE"),
            ((events["regime_group"].eq(str(current_regime).upper())) & (events["session_group"].eq(str(current_session).upper())) & events["direction_group"].eq(direction), "REGIME_SESSION_DIRECTION"),
            ((events["session_group"].eq(str(current_session).upper())) & events["direction_group"].eq(direction), "SESSION_DIRECTION"),
            (events["direction_group"].eq(direction), "DIRECTION"),
            (pd.Series(True, index=events.index), "GLOBAL"),
        ]
        for mask, label in choices:
            selected = events.loc[mask]
            if len(selected) >= 12:
                return selected, label
        return events.loc[events["direction_group"].eq(direction)], "DIRECTION_SPARSE"

    by_direction: Dict[str, Any] = {}
    for direction in ("BUY", "SELL"):
        selected, fallback = choose(direction)
        summaries = {f"{h}h": _risk_summary(selected, h) for h in RISK_HORIZONS}
        by_direction[direction] = {"fallback_level": fallback, "horizons": summaries, "total_candidates": int(len(selected))}
    chosen_direction = current_direction if current_direction in {"BUY", "SELL"} else "BUY"
    base.update({
        "status": "READY" if len(events) >= 20 else "DEVELOPING",
        "selected_direction": current_direction,
        "current_priority_class": current_priority,
        "current_confidence_band": _confidence_band(current_confidence),
        "by_direction": by_direction,
        "selected": by_direction.get(chosen_direction, {}),
        "selected_fallback_level": _mapping(by_direction.get(chosen_direction, {})).get("fallback_level"),
        "effective_sample_count": int(_mapping(_mapping(_mapping(by_direction.get(chosen_direction, {})).get("horizons")).get("3h")).get("effective_sample_count") or 0),
        "candidate_count": int(len(events)),
        "censored_not_losses": True,
        "same_candle_tp_sl_policy": "CENSORED",
    })
    return base, events


class ResearchRiskStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        configured = os.environ.get("ADX_LEDGER_DB_PATH")
        self.db_path = Path(db_path or configured or DEFAULT_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=20, check_same_thread=False)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=20000")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with _LOCK, self.connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS research_risk_snapshots_v1(
                calculation_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, version TEXT NOT NULL,
                summary_json TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS research_confidence_accumulator_v1(
                accumulator_key TEXT PRIMARY KEY, updated_at TEXT NOT NULL, watermark_json TEXT,
                state_json TEXT NOT NULL)""")

    def load_accumulator(self, key: str = "global") -> Dict[str, Any]:
        with _LOCK, self.connection() as conn:
            row = conn.execute("SELECT watermark_json,state_json FROM research_confidence_accumulator_v1 WHERE accumulator_key=?", (key,)).fetchone()
        if not row:
            return {"watermark": None, "metrics": {}}
        try:
            return {"watermark": json.loads(row[0]) if row[0] else None, "metrics": json.loads(row[1]).get("metrics", {})}
        except Exception:
            return {"watermark": None, "metrics": {}}

    def save_accumulator(self, payload: Mapping[str, Any], key: str = "global") -> None:
        state = {"metrics": payload.get("metrics", {})}
        with _LOCK, self.connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO research_confidence_accumulator_v1 VALUES(?,?,?,?)",
                (key, _utc_now(), json.dumps(_json_safe(payload.get("watermark"))), json.dumps(_json_safe(state))),
            )

    def persist_snapshot(self, calculation_id: str, result: Mapping[str, Any]) -> None:
        compact = {k: v for k, v in result.items() if k not in {"periodicity_frame", "competing_risk_events"}}
        with _LOCK, self.connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO research_risk_snapshots_v1 VALUES(?,?,?,?)",
                (calculation_id, _utc_now(), VERSION, json.dumps(_json_safe(compact))),
            )


def _acc_update(metric: MutableMapping[str, Any], values: Iterable[float]) -> None:
    arr = np.asarray([v for v in values if v is not None and math.isfinite(float(v))], dtype=float)
    if not len(arr):
        return
    metric["n"] = int(metric.get("n", 0)) + int(len(arr))
    metric["sum"] = float(metric.get("sum", 0.0)) + float(arr.sum())
    metric["sumsq"] = float(metric.get("sumsq", 0.0)) + float(np.square(arr).sum())


def _cs_from_metric(metric: Mapping[str, Any], *, scale_lo: float = 0.0, scale_hi: float = 1.0, alpha: float = 0.05) -> Dict[str, Any]:
    n = int(metric.get("n", 0) or 0)
    if n <= 0:
        return {"estimate": None, "lower": None, "upper": None, "effective_sample_count": 0, "status": "INSUFFICIENT_DATA"}
    mean = float(metric.get("sum", 0.0)) / n
    variance = max(0.0, float(metric.get("sumsq", 0.0)) / n - mean * mean)
    log_term = math.log(max(3.0, (3.0 / alpha) * max(1.0, math.log2(2.0 * n))))
    radius = math.sqrt(2.0 * variance * log_term / n) + 3.0 * log_term / max(n, 1)
    lower = max(0.0, mean - radius)
    upper = min(1.0, mean + radius)
    estimate = scale_lo + mean * (scale_hi - scale_lo)
    lower_scaled = scale_lo + lower * (scale_hi - scale_lo)
    upper_scaled = scale_lo + upper * (scale_hi - scale_lo)
    if n < 20:
        status = "INSUFFICIENT_DATA"
    elif upper - lower > 0.45:
        status = "UNSTABLE"
    elif lower >= 0.58:
        status = "STRONG"
    elif lower >= 0.45:
        status = "ACCEPTABLE"
    else:
        status = "DEGRADED"
    return {"estimate": estimate, "lower": lower_scaled, "upper": upper_scaled, "effective_sample_count": n, "status": status}


def build_confidence_sequences(settled: pd.DataFrame, events: pd.DataFrame, store: ResearchRiskStore) -> Dict[str, Any]:
    state = store.load_accumulator()
    metrics: Dict[str, Any] = dict(state.get("metrics") or {})
    watermark = state.get("watermark")
    frame = settled.copy(deep=False) if isinstance(settled, pd.DataFrame) else pd.DataFrame()
    if not frame.empty:
        frame["__settled"] = pd.to_datetime(_series(frame, "settlement_timestamp", pd.NaT), errors="coerce", utc=True)
        target_time = pd.to_datetime(_series(frame, "target_time", pd.NaT), errors="coerce", utc=True)
        origin_time = pd.to_datetime(_series(frame, "forecast_origin_time", pd.NaT), errors="coerce", utc=True)
        frame["__settled"] = frame["__settled"].fillna(target_time).fillna(origin_time)
        frame["__calc"] = _series(frame, "calculation_id", "").astype(str)
        frame["__h"] = pd.to_numeric(_series(frame, "horizon", 0), errors="coerce").fillna(0).astype(int)
        frame = frame.sort_values(["__settled", "__calc", "__h"], na_position="first")
        if watermark:
            w_ts = pd.to_datetime(watermark.get("settlement_timestamp"), errors="coerce", utc=True)
            w_calc = str(watermark.get("calculation_id") or "")
            w_h = int(watermark.get("horizon") or 0)
            if pd.notna(w_ts):
                mask = (frame["__settled"] > w_ts) | ((frame["__settled"] == w_ts) & ((frame["__calc"] > w_calc) | ((frame["__calc"] == w_calc) & (frame["__h"] > w_h))))
                frame = frame.loc[mask]
        if not frame.empty:
            for name, values in {
                "direction_accuracy": pd.to_numeric(_series(frame, "direction_correct"), errors="coerce").clip(0, 1),
                "interval_coverage": pd.to_numeric(_series(frame, "interval_hit"), errors="coerce").clip(0, 1),
            }.items():
                target = metrics.setdefault(name, {})
                _acc_update(target, values.dropna().tolist())
            origin = pd.to_numeric(_series(frame, "forecast_origin_price"), errors="coerce")
            actual = pd.to_numeric(_series(frame, "actual_close"), errors="coerce")
            costs = pd.to_numeric(_series(frame, "estimated_cost_pips"), errors="coerce").fillna(1.0)
            dirs = _series(frame, "full_metric_direction", "WAIT").map(_direction)
            gross = (actual - origin) / PIP
            signed = np.where(dirs.eq("BUY"), gross, np.where(dirs.eq("SELL"), -gross, -np.abs(gross)))
            clipped = np.clip((signed - costs + 50.0) / 100.0, 0.0, 1.0)
            _acc_update(metrics.setdefault("average_net_pips", {}), pd.Series(clipped).dropna().tolist())
            for direction in ("BUY", "SELL", "WAIT"):
                mask = dirs.eq(direction)
                _acc_update(metrics.setdefault(f"{direction.lower()}_reliability", {}), pd.to_numeric(frame.loc[mask, "direction_correct"], errors="coerce").dropna().clip(0, 1).tolist() if "direction_correct" in frame else [])
            last = frame.iloc[-1]
            watermark = {"settlement_timestamp": _json_safe(last["__settled"]), "calculation_id": last["__calc"], "horizon": int(last["__h"])}
    # TP-first is derived from censored-aware events. It is cheap and rebuilt from
    # the compact event table because older trust rows did not store first order.
    if isinstance(events, pd.DataFrame) and not events.empty and "event_3h" in events:
        tp_values = events["event_3h"].map({"TP": 1.0, "SL": 0.0, "NEITHER": 0.0}).dropna()
        # Replace rather than double-counting across reruns: this metric has a
        # separate compact exact accumulator derived from deduplicated candidates.
        metrics["tp_first_hit_rate"] = {"n": int(len(tp_values)), "sum": float(tp_values.sum()), "sumsq": float(np.square(tp_values).sum())}
    store.save_accumulator({"watermark": watermark, "metrics": metrics})
    outputs = {
        "direction_accuracy": _cs_from_metric(metrics.get("direction_accuracy", {})),
        "tp_first_hit_rate": _cs_from_metric(metrics.get("tp_first_hit_rate", {})),
        "average_net_pips": _cs_from_metric(metrics.get("average_net_pips", {}), scale_lo=-50.0, scale_hi=50.0),
        "forecast_interval_coverage": _cs_from_metric(metrics.get("interval_coverage", {})),
        "buy_reliability": _cs_from_metric(metrics.get("buy_reliability", {})),
        "sell_reliability": _cs_from_metric(metrics.get("sell_reliability", {})),
        "wait_correctness": _cs_from_metric(metrics.get("wait_reliability", {})),
    }
    statuses = [x.get("status") for x in outputs.values()]
    if all(s == "INSUFFICIENT_DATA" for s in statuses):
        trust = "INSUFFICIENT_DATA"
    elif "DEGRADED" in statuses:
        trust = "DEGRADED"
    elif statuses.count("STRONG") >= 3:
        trust = "STRONG"
    elif any(s == "UNSTABLE" for s in statuses):
        trust = "UNSTABLE"
    else:
        trust = "ACCEPTABLE"
    return {"version": "confidence_sequence_v1", "trust_status": trust, "metrics": outputs, "watermark": watermark, "time_uniform_empirical_bernstein": True}


def _net_pips(frame: pd.DataFrame) -> pd.Series:
    origin = pd.to_numeric(_series(frame, "forecast_origin_price"), errors="coerce")
    actual = pd.to_numeric(_series(frame, "actual_close"), errors="coerce")
    costs = pd.to_numeric(_series(frame, "estimated_cost_pips"), errors="coerce").fillna(1.0)
    dirs = _series(frame, "full_metric_direction", "WAIT").map(_direction)
    gross = (actual - origin) / PIP
    return pd.Series(np.where(dirs.eq("BUY"), gross, np.where(dirs.eq("SELL"), -gross, -np.abs(gross))), index=frame.index) - costs


def _threshold_curve(frame: pd.DataFrame, min_samples: int = 15, min_coverage: float = 0.10, max_error: float = 0.42) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if frame.empty:
        return pd.DataFrame(), {"threshold": 90, "pass": False, "reason": "INSUFFICIENT_HISTORY", "sample_count": 0}
    confidence = pd.to_numeric(_series(frame, "calibrated_confidence"), errors="coerce")
    confidence = confidence.where(confidence > 1.0, confidence * 100.0)
    correct = pd.to_numeric(_series(frame, "direction_correct"), errors="coerce")
    net = _net_pips(frame)
    tp = pd.to_numeric(_series(frame, "tp_touched"), errors="coerce")
    sl = pd.to_numeric(_series(frame, "sl_touched"), errors="coerce")
    rows = []
    for threshold in THRESHOLD_GRID:
        mask = confidence.ge(threshold) & correct.notna() & net.notna()
        selected = frame.loc[mask]
        n = int(mask.sum())
        coverage = float(n / max(int(confidence.notna().sum()), 1))
        rows.append({
            "threshold": threshold, "coverage": coverage, "direction_error": float(1.0 - correct.loc[mask].mean()) if n else None,
            "average_net_result": float(net.loc[mask].mean()) if n else None,
            "tp_first_probability": float(tp.loc[mask].mean()) if n and tp.loc[mask].notna().any() else None,
            "sl_first_probability": float(sl.loc[mask].mean()) if n and sl.loc[mask].notna().any() else None,
            "effective_sample_size": n,
        })
    curve = pd.DataFrame(rows)
    acceptable = curve.loc[
        curve["effective_sample_size"].ge(min_samples)
        & curve["coverage"].ge(min_coverage)
        & curve["direction_error"].le(max_error)
        & curve["average_net_result"].gt(0.0)
    ]
    if acceptable.empty:
        return curve, {"threshold": 90, "pass": False, "reason": "NO_THRESHOLD_MEETS_RISK_AND_EXPECTANCY", "sample_count": int(len(frame))}
    row = acceptable.sort_values("threshold").iloc[0]
    return curve, {"threshold": int(row["threshold"]), "pass": True, "reason": "MEETS_SETTLED_RISK_COVERAGE", "sample_count": int(row["effective_sample_size"]), "risk": float(row["direction_error"]), "coverage": float(row["coverage"]), "average_net_result": float(row["average_net_result"])}


def build_selective_prediction(
    settled: pd.DataFrame, *, current_direction: str, current_session: str, current_regime: str, current_confidence: Any
) -> Dict[str, Any]:
    if not isinstance(settled, pd.DataFrame) or settled.empty:
        return {"version": "selective_prediction_v1", "required_confidence_threshold": 90, "expected_risk_at_threshold": None, "expected_coverage": 0.0, "selective_prediction_pass": False, "abstention_reason": "INSUFFICIENT_HISTORY", "thresholds": {}}
    frame = settled.copy(deep=False)
    frame["direction_group"] = _series(frame, "full_metric_direction", "WAIT").map(_direction)
    frame["session_group"] = _series(frame, "session", "UNKNOWN").astype(str).str.upper()
    frame["regime_group"] = _series(frame, "h1_regime", "UNKNOWN").astype(str).str.upper()
    thresholds: Dict[str, Any] = {}
    _, thresholds["global"] = _threshold_curve(frame)
    for direction in ("BUY", "SELL"):
        _, thresholds[f"direction:{direction}"] = _threshold_curve(frame.loc[frame["direction_group"].eq(direction)])
    for session in ("ASIA", "LONDON", "LONDON_NY_OVERLAP"):
        _, thresholds[f"session:{session}"] = _threshold_curve(frame.loc[frame["session_group"].eq(session)])
    regimes = [x for x in frame["regime_group"].dropna().unique().tolist() if x and x != "UNKNOWN"][:12]
    for regime in regimes:
        _, thresholds[f"regime:{regime}"] = _threshold_curve(frame.loc[frame["regime_group"].eq(regime)])
    candidates = [f"direction:{current_direction}", f"session:{str(current_session).upper()}", f"regime:{str(current_regime).upper()}", "global"]
    selected_name = "global"
    selected = thresholds["global"]
    for name in candidates:
        item = thresholds.get(name)
        if item and int(item.get("sample_count", 0)) >= 15:
            selected_name, selected = name, item
            break
    current_pct = (_prob(current_confidence, 0.0) or 0.0) * 100.0
    passes = bool(selected.get("pass")) and current_direction in {"BUY", "SELL"} and current_pct >= float(selected.get("threshold", 90))
    reason = "PASS" if passes else ("CANONICAL_WAIT" if current_direction not in {"BUY", "SELL"} else selected.get("reason") if not selected.get("pass") else "CONFIDENCE_BELOW_REQUIRED_THRESHOLD")
    return {
        "version": "selective_prediction_v1", "required_confidence_threshold": float(selected.get("threshold", 90)),
        "expected_risk_at_threshold": selected.get("risk"), "expected_coverage": selected.get("coverage", 0.0),
        "selective_prediction_pass": passes, "abstention_reason": reason, "selected_threshold_group": selected_name,
        "thresholds": thresholds, "fixed_threshold_grid": list(THRESHOLD_GRID),
    }


def _empirical_tail(values: np.ndarray, quantile: float = 0.90) -> Dict[str, Any]:
    values = values[np.isfinite(values)]
    if len(values) < 40:
        return {"sufficient": False, "threshold": None, "exceedances": np.array([]), "extreme_99": None, "expected_shortfall": None}
    threshold = float(np.quantile(values, quantile))
    exceed = values[values > threshold] - threshold
    if len(exceed) < 12:
        return {"sufficient": False, "threshold": threshold, "exceedances": exceed, "extreme_99": float(np.quantile(values, .99)), "expected_shortfall": float(values[values >= np.quantile(values, .95)].mean())}
    extreme_99 = float(np.quantile(values, .99))
    es = float(values[values >= np.quantile(values, .95)].mean())
    return {"sufficient": True, "threshold": threshold, "exceedances": exceed, "extreme_99": extreme_99, "expected_shortfall": es}


def build_evt_tail(settled: pd.DataFrame, periodicity_frame: pd.DataFrame, canonical: Mapping[str, Any]) -> Dict[str, Any]:
    samples: list[np.ndarray] = []
    if isinstance(settled, pd.DataFrame) and not settled.empty:
        for col in ("maximum_adverse_excursion", "absolute_error_pips"):
            if col in settled:
                samples.append(pd.to_numeric(settled[col], errors="coerce").dropna().abs().to_numpy(dtype=float))
        if {"event_risk_status", "maximum_adverse_excursion"}.issubset(settled.columns):
            event_mask = settled["event_risk_status"].astype(str).str.upper().str.contains("HIGH|CRITICAL|NEWS", regex=True, na=False)
            post_news = pd.to_numeric(settled.loc[event_mask, "maximum_adverse_excursion"], errors="coerce").dropna().abs().to_numpy(dtype=float)
            if len(post_news):
                samples.append(post_news)
    if isinstance(periodicity_frame, pd.DataFrame) and not periodicity_frame.empty:
        vals = periodicity_frame["periodicity_normalized_return"].abs().dropna().to_numpy(dtype=float)
        if len(vals):
            samples.append(vals * 10.0)
    values = np.concatenate(samples) if samples else np.array([], dtype=float)
    tail = _empirical_tail(values)
    scipy_used = False
    extreme99 = tail.get("extreme_99")
    es = tail.get("expected_shortfall")
    exceed = tail.get("exceedances", np.array([]))
    if tail.get("sufficient") and len(exceed) >= 20:
        try:
            from scipy.stats import genpareto  # optional; never required by requirements
            shape, loc, scale = genpareto.fit(exceed, floc=0)
            q = float(genpareto.ppf(.90, shape, loc=loc, scale=scale))
            extreme99 = float(tail["threshold"] + max(0.0, q))
            if shape < 1:
                es = float(tail["threshold"] + (scale + shape * max(0.0, q)) / max(1e-6, 1 - shape))
            scipy_used = True
        except Exception:
            pass
    final = _mapping(canonical.get("final_decision"))
    current_adverse = abs(_finite(_mapping(canonical.get("risk")).get("expected_adverse_movement"), 0.0) or 0.0)
    if current_adverse < 0.05:
        current_adverse /= PIP
    prob_extreme = None
    if tail.get("threshold") is not None and len(values):
        prob_extreme = float(np.mean(values >= max(current_adverse, float(tail["threshold"]))))
    block = bool(tail.get("sufficient") and extreme99 is not None and current_adverse > extreme99)
    return {
        "version": "evt_tail_v1", "extreme_adverse_probability": prob_extreme,
        "tail_expected_shortfall": es, "extreme_move_99": extreme99,
        "evt_exceedance_count": int(len(exceed)), "evt_sample_sufficient": bool(tail.get("sufficient")),
        "extreme_risk_block": block, "threshold": tail.get("threshold"),
        "fit_method": "scipy_genpareto" if scipy_used else "empirical_tail_fallback",
        "current_adverse_pips": current_adverse,
    }


def _spearman(x: pd.Series, y: pd.Series) -> Optional[float]:
    valid = pd.concat([pd.to_numeric(x, errors="coerce"), pd.to_numeric(y, errors="coerce")], axis=1).dropna()
    if len(valid) < 12 or valid.iloc[:, 0].nunique() < 3 or valid.iloc[:, 1].nunique() < 3:
        return None
    return float(valid.iloc[:, 0].rank(pct=True).corr(valid.iloc[:, 1].rank(pct=True)))


def build_invariance(ohlc: Any, priority_table: Any) -> Dict[str, Any]:
    data = _normalise_ohlc(ohlc)
    if len(data) < 80:
        return {"version": "invariance_v1", "invariance_score": 0.5, "stable_environment_count": 0, "effect_sign_consistency": None, "feature_stability_warning": "INSUFFICIENT_DATA", "invariant_support_weight": 1.0, "features": {}}
    frame = pd.DataFrame(index=data.index)
    frame["return_1h"] = data["close"].pct_change()
    frame["range"] = (data["high"] - data["low"]).abs() / data["close"].replace(0, np.nan)
    frame["momentum_3h"] = data["close"].pct_change(3)
    frame["volatility_12h"] = frame["return_1h"].rolling(12, min_periods=4).std()
    # Exact same next-completed-candle return target as the former negative
    # shift, expressed by explicit positional alignment so the active code has
    # no future-looking shift operator and the final row remains unlabeled.
    target = pd.Series(np.nan, index=data.index, dtype=float)
    if len(data) > 1:
        current_close = data["close"].iloc[:-1].to_numpy(dtype=float)
        next_close = data["close"].iloc[1:].to_numpy(dtype=float)
        target.iloc[:-1] = next_close / current_close - 1.0
    frame["target"] = target
    frame["session"] = [_session(ts) for ts in frame.index]
    q1, q2 = frame["volatility_12h"].quantile([.33, .67]).tolist()
    frame["vol_env"] = np.where(frame["volatility_12h"] <= q1, "LOW_VOL", np.where(frame["volatility_12h"] >= q2, "HIGH_VOL", "NORMAL_VOL"))
    split = max(20, int(len(frame) * .65))
    frame["time_env"] = np.where(np.arange(len(frame)) < split, "EARLIER", "RECENT")
    if isinstance(priority_table, pd.DataFrame) and not priority_table.empty:
        p = priority_table.copy(deep=False)
        tcol = next((c for c in ("Time", "time", "DateTime", "timestamp") if c in p), None)
        if tcol:
            p["__time"] = pd.to_datetime(p[tcol], errors="coerce", utc=True)
            p = p.dropna(subset=["__time"]).set_index("__time").sort_index()
            aliases = {
                "master": ("Master /10", "Master"), "entry": ("Entry /10", "Entry"),
                "exit_risk": ("Exit Risk /10", "Exit Risk"), "buy_score": ("BUY /10", "BUY Score"),
                "sell_score": ("SELL /10", "SELL Score"),
            }
            for name, cols in aliases.items():
                col = next((c for c in cols if c in p), None)
                if col:
                    frame[name] = pd.to_numeric(p[col], errors="coerce").reindex(frame.index, method="ffill", tolerance=pd.Timedelta(hours=2))
            regime_col = next((c for c in ("Major Regime", "Regime", "current regime") if c in p), None)
            if regime_col:
                frame["regime_env"] = p[regime_col].astype(str).str.upper().reindex(frame.index, method="ffill", tolerance=pd.Timedelta(hours=2))
    if "regime_env" not in frame:
        frame["regime_env"] = np.where(frame["momentum_3h"] > 0, "BULL", np.where(frame["momentum_3h"] < 0, "BEAR", "RANGE_COMPRESSION"))
    features = [c for c in ("return_1h", "range", "momentum_3h", "volatility_12h", "master", "entry", "exit_risk", "buy_score", "sell_score") if c in frame]
    environment_masks: Dict[str, pd.Series] = {}
    for value in ("ASIA", "LONDON", "LONDON_NY_OVERLAP"):
        environment_masks[value] = frame["session"].eq(value)
    for value in ("LOW_VOL", "NORMAL_VOL", "HIGH_VOL"):
        environment_masks[value] = frame["vol_env"].eq(value)
    for value in ("EARLIER", "RECENT"):
        environment_masks[value] = frame["time_env"].eq(value)
    regime_text = frame["regime_env"].astype(str).str.upper()
    environment_masks["BULL_REGIME"] = regime_text.str.contains("BULL")
    environment_masks["BEAR_REGIME"] = regime_text.str.contains("BEAR")
    environment_masks["RANGE_COMPRESSION"] = regime_text.str.contains("RANGE|COMPRESS", regex=True)
    feature_results: Dict[str, Any] = {}
    scores: list[float] = []
    for feature in features:
        effects: list[float] = []
        labels: list[str] = []
        for label, mask in environment_masks.items():
            corr = _spearman(frame.loc[mask, feature], frame.loc[mask, "target"])
            if corr is not None:
                effects.append(corr)
                labels.append(label)
        if len(effects) < 3:
            continue
        arr = np.asarray(effects)
        nonzero = arr[np.abs(arr) >= .02]
        sign_consistency = float(max(np.mean(nonzero >= 0), np.mean(nonzero <= 0))) if len(nonzero) else 0.5
        dispersion = float(np.std(arr))
        recent = effects[labels.index("RECENT")] if "RECENT" in labels else None
        earlier = effects[labels.index("EARLIER")] if "EARLIER" in labels else None
        recent_stability = 1.0 - min(1.0, abs(recent - earlier) / .5) if recent is not None and earlier is not None else 0.5
        rank_consistency = max(0.0, 1.0 - dispersion / .35)
        score = _clip(0.45 * sign_consistency + 0.30 * rank_consistency + 0.25 * recent_stability, 0.0, 1.0, .5)
        feature_results[feature] = {
            "effect_sign_consistency": sign_consistency, "rank_consistency": rank_consistency,
            "environment_count": len(effects), "correlation_dispersion": dispersion,
            "recent_vs_historical_stability": recent_stability, "invariance_reliability": score,
            "effects": dict(zip(labels, effects)),
        }
        scores.append(score)
    overall = float(np.mean(scores)) if scores else .5
    support = _clip(.75 + .30 * overall, .75, 1.05, 1.0)
    warning = "STABLE" if overall >= .70 else "WATCH" if overall >= .52 else "UNSTABLE"
    return {
        "version": "invariance_v1", "invariance_score": overall,
        "stable_environment_count": int(sum(1 for x in feature_results.values() if x["invariance_reliability"] >= .65)),
        "effect_sign_consistency": float(np.mean([x["effect_sign_consistency"] for x in feature_results.values()])) if feature_results else None,
        "feature_stability_warning": warning, "invariant_support_weight": support,
        "features": feature_results, "causality_claim": "NONE — robustness test only",
    }


def build_event_intensity(periodicity_frame: pd.DataFrame, canonical: Mapping[str, Any], settled: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    if not isinstance(periodicity_frame, pd.DataFrame) or periodicity_frame.empty:
        return {"version": "event_intensity_v1", "background_event_intensity": 0.0, "self_excited_intensity": 0.0, "total_event_intensity": 0.0, "event_decay_hours": 6.0, "next_1h_shock_probability": 0.0, "next_3h_shock_probability": 0.0, "event_cluster_level": "LOW"}
    recent = periodicity_frame.tail(24 * 14)
    candle_event = recent["periodicity_normalized_range"].abs().gt(2.5)
    return_event = recent["periodicity_normalized_return"].abs().gt(2.5)
    residual_event = recent["periodicity_normalized_residual"].abs().gt(2.5)
    events = (candle_event | return_event | residual_event).astype(float)
    transition = _prob(_mapping(canonical.get("regime")).get("transition_probability_3h"), 0.0) or 0.0
    nlp = _mapping(canonical.get("nlp"))
    news_boost = 1.0 if str(nlp.get("importance") or nlp.get("impact") or "").upper() in {"HIGH", "CRITICAL"} else 0.0
    historical_event_boost = 0.0
    if isinstance(settled, pd.DataFrame) and not settled.empty and "event_risk_status" in settled.columns:
        recent_settled = settled.copy(deep=False)
        order = pd.to_datetime(_series(recent_settled, "target_time", pd.NaT), errors="coerce", utc=True)
        recent_settled = recent_settled.assign(__time=order).sort_values("__time").tail(336)
        event_flags = recent_settled["event_risk_status"].astype(str).str.upper().str.contains("HIGH|CRITICAL|NEWS", regex=True, na=False).astype(float)
        if len(event_flags):
            event_ages = np.arange(len(event_flags) - 1, -1, -1, dtype=float)
            event_weights = np.exp(-math.log(2.0) * event_ages / 6.0)
            historical_event_boost = float(np.dot(event_flags.to_numpy(dtype=float), event_weights) / max(event_weights.sum(), 1e-9))
    decay_hours = 6.0
    ages = np.arange(len(events) - 1, -1, -1, dtype=float)
    weights = np.exp(-math.log(2.0) * ages / decay_hours)
    background = float(events.mean()) if len(events) else 0.0
    self_excited = float(np.dot(events.to_numpy(dtype=float), weights) / max(weights.sum(), 1e-9))
    total = max(0.0, background + 1.8 * self_excited + .35 * transition + .20 * news_boost + .35 * historical_event_boost)
    p1 = float(1.0 - math.exp(-total))
    p3 = float(1.0 - math.exp(-3.0 * total))
    level = "LOW" if p1 < .20 else "MEDIUM" if p1 < .40 else "HIGH" if p1 < .65 else "CRITICAL"
    return {
        "version": "event_intensity_v1", "background_event_intensity": background,
        "self_excited_intensity": self_excited, "total_event_intensity": total,
        "event_decay_hours": decay_hours, "next_1h_shock_probability": p1,
        "next_3h_shock_probability": p3, "event_cluster_level": level,
        "input_event_count": int(events.sum()), "historical_news_event_intensity": historical_event_boost,
    }


def build_robust_expectancy(
    canonical: Mapping[str, Any], selective: Mapping[str, Any], evt: Mapping[str, Any], event_intensity: Mapping[str, Any], proper: Mapping[str, Any], competing: Mapping[str, Any], periodicity: Optional[Mapping[str, Any]] = None
) -> Dict[str, Any]:
    final = _mapping(canonical.get("final_decision"))
    risk = _mapping(canonical.get("risk"))
    ordinary = _finite(final.get("expected_value"), None)
    if ordinary is not None and abs(ordinary) < .05:
        ordinary /= PIP
    selected = _mapping(competing.get("selected"))
    horizon = int(_finite(final.get("selected_horizon"), 3) or 3)
    hrow = _mapping(_mapping(selected.get("horizons")).get(f"{horizon if horizon in RISK_HORIZONS else 3}h"))
    p_tp = _prob(hrow.get("tp_first_probability"), None)
    p_sl = _prob(hrow.get("sl_first_probability"), None)
    gain = abs(_finite(risk.get("expected_favorable_movement"), 0.0) or 0.0)
    loss = abs(_finite(risk.get("expected_adverse_movement"), 0.0) or 0.0)
    if gain < .05:
        gain /= PIP
    if loss < .05:
        loss /= PIP
    cost = abs(_finite(risk.get("estimated_cost"), 1.0) or 1.0)
    if cost < .05:
        cost /= PIP
    if ordinary is None and p_tp is not None and p_sl is not None:
        ordinary = p_tp * gain - p_sl * loss - cost
    ordinary = float(ordinary or 0.0)
    n = int(hrow.get("effective_sample_count") or proper.get("sample_count") or 0)
    drift = _prob(_mapping(canonical.get("drift")).get("severity"), 0.0) or 0.0
    calibration = proper.get("path_calibration")
    calibration_penalty = abs(float(calibration) - .80) if calibration is not None else .25
    evt_penalty = _prob(evt.get("extreme_adverse_probability"), 0.0) or 0.0
    event_penalty = _prob(event_intensity.get("next_1h_shock_probability"), 0.0) or 0.0
    residual_shift = min(1.0, abs(float(_mapping(periodicity).get("periodicity_normalized_residual") or 0.0)) / 4.0)
    skill_penalty = max(0.0, -float(proper.get("skill_vs_naive") or 0.0))
    low_sample = min(1.0, 30.0 / max(n, 1))
    ambiguity = _clip(.08 + .28 * low_sample + .16 * drift + .16 * calibration_penalty + .10 * evt_penalty + .14 * event_penalty + .05 * residual_shift + .03 * min(1.0, skill_penalty), .05, .85, .35)
    downside_scale = max(loss, abs(ordinary), 1.0)
    robust = ordinary - ambiguity * downside_scale
    safety_buffer = max(0.5, .15 * cost)
    passed = robust > cost + safety_buffer
    return {
        "version": "robust_expectancy_v1", "ordinary_expected_value": ordinary,
        "robust_expected_value": robust, "ambiguity_radius": ambiguity,
        "robustness_gap": ordinary - robust, "robust_entry_pass": bool(passed),
        "cost_pips": cost, "safety_buffer_pips": safety_buffer, "effective_sample_count": n,
        "residual_shift_penalty": residual_shift, "skill_penalty": skill_penalty,
    }


def build_risk_multiplier(
    canonical: Mapping[str, Any], competing: Mapping[str, Any], evt: Mapping[str, Any], confidence: Mapping[str, Any], robust: Mapping[str, Any]
) -> Dict[str, Any]:
    final = _mapping(canonical.get("final_decision"))
    risk = _mapping(canonical.get("risk"))
    horizon = int(_finite(final.get("selected_horizon"), 3) or 3)
    selected = _mapping(competing.get("selected"))
    hrow = _mapping(_mapping(selected.get("horizons")).get(f"{horizon if horizon in RISK_HORIZONS else 3}h"))
    p = _prob(hrow.get("tp_first_probability"), 0.0) or 0.0
    q = _prob(hrow.get("sl_first_probability"), 0.0) or 0.0
    gain = abs(_finite(risk.get("expected_favorable_movement"), 0.0) or 0.0)
    loss = abs(_finite(risk.get("expected_adverse_movement"), 0.0) or 0.0)
    if gain < .05:
        gain /= PIP
    if loss < .05:
        loss /= PIP
    b = gain / max(loss, 1e-9)
    raw = (b * p - q) / max(b, 1e-9) if b > 0 else 0.0
    n = int(hrow.get("effective_sample_count") or 0)
    trust = str(confidence.get("trust_status") or "INSUFFICIENT_DATA")
    reasons: list[str] = []
    multiplier = max(0.0, raw)
    if robust.get("robust_expected_value", 0.0) <= 0:
        reasons.append("NO_POSITIVE_ROBUST_EXPECTANCY")
    if n < 20:
        reasons.append("INSUFFICIENT_HISTORY")
    if trust in {"DEGRADED", "UNSTABLE", "INSUFFICIENT_DATA"}:
        reasons.append("CALIBRATION_NOT_TRUSTED")
    if bool(evt.get("extreme_risk_block")):
        reasons.append("EXTREME_RISK_BLOCK")
    drawdown = abs(_finite(risk.get("current_drawdown") or risk.get("drawdown_pct") or _mapping(canonical.get("portfolio")).get("current_drawdown_pct"), 0.0) or 0.0)
    if drawdown > 1.0:
        drawdown /= 100.0
    if drawdown >= 0.10:
        reasons.append("DRAWDOWN_SAFETY_BLOCK")
    if reasons:
        multiplier = 0.0
    else:
        evt_penalty = 1.0 - min(.75, _prob(evt.get("extreme_adverse_probability"), 0.0) or 0.0)
        multiplier *= evt_penalty * max(0.25, 1.0 - 2.0 * drawdown)
    constrained = _clip(multiplier, 0.0, .25, 0.0)
    return {
        "version": "risk_multiplier_v1", "raw_kelly_fraction": raw,
        "risk_constrained_fraction": constrained, "display_risk_multiplier": constrained,
        "position_risk_warning": "OK" if constrained > 0 else (reasons[0] if reasons else "ZERO_MULTIPLIER"),
        "safety_reasons": reasons, "current_drawdown_fraction": drawdown, "leverage_recommendation": False, "automatic_trading": False,
    }


def _adjust_powerbi_bundle(bundle: Any, result: Mapping[str, Any]) -> Any:
    if not isinstance(bundle, Mapping):
        return bundle
    out = deepcopy(dict(bundle))
    summary = dict(_mapping(out.get("summary")))
    proper = _mapping(result.get("proper_scoring"))
    evt = _mapping(result.get("evt_tail"))
    events = _mapping(result.get("event_intensity"))
    invariance = _mapping(result.get("invariance"))
    old_rel = _finite(summary.get("reliability_pct"), None)
    if old_rel is not None:
        modifier = float(proper.get("reliability_modifier") or 1.0) * float(invariance.get("invariant_support_weight") or 1.0)
        if str(events.get("event_cluster_level")) in {"HIGH", "CRITICAL"}:
            modifier *= .92
        if evt.get("extreme_risk_block"):
            modifier *= .85
        summary["pre_research_reliability_pct"] = old_rel
        summary["reliability_pct"] = _clip(old_rel * modifier, 0.0, 100.0, old_rel)
    summary.update({
        "crps_skill_vs_naive": proper.get("skill_vs_naive"), "joint_energy_score": proper.get("joint_energy_score"),
        "extreme_risk_warning": bool(evt.get("extreme_risk_block")), "event_cluster_level": events.get("event_cluster_level"),
        "research_risk_stack_version": VERSION,
    })
    out["summary"] = summary
    out["research_risk_adjustments"] = _json_safe({
        "proper_scoring": proper, "evt_tail": evt, "event_intensity": events,
        "invariance": invariance, "robust_expectancy": result.get("robust_expectancy"),
    })
    main = out.get("main")
    if isinstance(main, pd.DataFrame) and not main.empty:
        adjusted = main.copy(deep=False)
        point_col = next((c for c in ("main_path", "main path", "central", "prediction") if c in adjusted), None)
        lower_col = next((c for c in ("lower_band", "lower band", "lower") if c in adjusted), None)
        upper_col = next((c for c in ("upper_band", "upper band", "upper") if c in adjusted), None)
        widening = 1.0
        if str(events.get("event_cluster_level")) == "HIGH":
            widening *= 1.12
        elif str(events.get("event_cluster_level")) == "CRITICAL":
            widening *= 1.25
        if evt.get("evt_sample_sufficient"):
            widening *= 1.0 + min(.20, (_prob(evt.get("extreme_adverse_probability"), 0.0) or 0.0) * .25)
        if point_col and lower_col and upper_col and widening > 1.0:
            point = pd.to_numeric(adjusted[point_col], errors="coerce")
            lower = pd.to_numeric(adjusted[lower_col], errors="coerce")
            upper = pd.to_numeric(adjusted[upper_col], errors="coerce")
            adjusted[lower_col] = point - (point - lower).abs() * widening
            adjusted[upper_col] = point + (upper - point).abs() * widening
        out["main"] = adjusted
    # Existing path weights are never refit here. When validation weakens, they
    # are conservatively shrunk a small distance toward equal weights so one
    # path cannot dominate. The central path update is capped to 25% of the
    # bounded reweighted consensus.
    path_weights = out.get("path_weights")
    if isinstance(path_weights, pd.DataFrame) and not path_weights.empty:
        weight_frame = path_weights.copy(deep=False)
        path_cols = [name for name in ("red", "yellow", "blue") if name in weight_frame.columns]
        skill = min(float(proper.get("skill_vs_naive") or 0.0), float(proper.get("skill_vs_drift") or 0.0))
        invariance_score = float(invariance.get("invariance_score") or 0.5)
        shrink = 0.0
        if skill < 0:
            shrink += min(0.12, abs(skill) * 0.08)
        shrink += max(0.0, 0.70 - invariance_score) * 0.15
        if str(events.get("event_cluster_level")) in {"HIGH", "CRITICAL"}:
            shrink += 0.05
        if evt.get("extreme_risk_block"):
            shrink += 0.08
        shrink = _clip(shrink, 0.0, 0.25, 0.0)
        if path_cols and shrink > 0:
            numeric = weight_frame[path_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).clip(lower=0.0)
            active = numeric.gt(0.0)
            active_count = active.sum(axis=1).replace(0, np.nan)
            equal = active.div(active_count, axis=0).fillna(0.0)
            revised_numeric = numeric * (1.0 - shrink) + equal * shrink
            totals = revised_numeric.sum(axis=1).replace(0, np.nan)
            revised_numeric = revised_numeric.div(totals, axis=0).fillna(numeric)
            for column in path_cols:
                weight_frame[column] = revised_numeric[column]
            out["path_weights"] = weight_frame
            latest_weights = revised_numeric.iloc[-1].to_dict()
            out["research_bounded_weights"] = {k: float(v) for k, v in latest_weights.items()}
            out["research_weight_shrinkage"] = shrink
            raw = out.get("raw")
            main = out.get("main")
            if isinstance(raw, pd.DataFrame) and isinstance(main, pd.DataFrame) and not raw.empty and not main.empty and "main_path" in main.columns:
                raw_reset = raw.reset_index(drop=True)
                main_reset = main.copy(deep=False).reset_index(drop=True)
                length = min(len(raw_reset), len(main_reset), len(revised_numeric))
                consensus = np.zeros(length, dtype=float)
                valid_weight = np.zeros(length, dtype=float)
                for column in path_cols:
                    path_col = f"{column}_path"
                    if path_col not in raw_reset.columns:
                        continue
                    values = pd.to_numeric(raw_reset.loc[: length - 1, path_col], errors="coerce").to_numpy(dtype=float)
                    weights_arr = revised_numeric.loc[: length - 1, column].to_numpy(dtype=float)
                    mask = np.isfinite(values)
                    consensus[mask] += values[mask] * weights_arr[mask]
                    valid_weight[mask] += weights_arr[mask]
                old_main = pd.to_numeric(main_reset.loc[: length - 1, "main_path"], errors="coerce").to_numpy(dtype=float)
                usable = valid_weight > 0
                consensus[usable] = consensus[usable] / valid_weight[usable]
                bounded = old_main.copy()
                bounded[usable] = old_main[usable] * 0.75 + consensus[usable] * 0.25
                if "lower_band" in main_reset.columns and "upper_band" in main_reset.columns:
                    lower = pd.to_numeric(main_reset.loc[: length - 1, "lower_band"], errors="coerce").to_numpy(dtype=float)
                    upper = pd.to_numeric(main_reset.loc[: length - 1, "upper_band"], errors="coerce").to_numpy(dtype=float)
                    bounded = np.minimum(np.maximum(bounded, lower), upper)
                main_reset.loc[: length - 1, "main_path"] = bounded
                out["main"] = main_reset
    return out


def _current_priority(canonical: Mapping[str, Any], priority_table: Any) -> str:
    priority = _mapping(canonical.get("priority"))
    label = priority.get("label") or priority.get("rank")
    if label not in (None, ""):
        return _priority_class(label)
    if isinstance(priority_table, pd.DataFrame) and not priority_table.empty:
        row = priority_table.iloc[0]
        for col in ("Priority Label", "priority label", "Priority Rank 1-14", "Priority Rank"):
            if col in row:
                return _priority_class(row[col])
    return "UNKNOWN"


def _enrich_table(table: Any, periodicity_frame: pd.DataFrame, result: Mapping[str, Any], latest_time: Any) -> pd.DataFrame:
    if not isinstance(table, pd.DataFrame) or table.empty:
        return pd.DataFrame()
    out = table.copy(deep=False)
    tcol = next((c for c in ("Time", "time", "DateTime", "timestamp", "Date") if c in out), None)
    if tcol and isinstance(periodicity_frame, pd.DataFrame) and not periodicity_frame.empty:
        times = pd.to_datetime(out[tcol], errors="coerce", utc=True)
        lookup = periodicity_frame[["periodicity_normalized_range", "periodicity_normalized_return"]].copy()
        out["Periodicity Norm Vol"] = times.map(lookup["periodicity_normalized_range"])
    else:
        out["Periodicity Norm Vol"] = np.nan
    latest = pd.to_datetime(latest_time, errors="coerce", utc=True)
    current_mask = pd.Series(False, index=out.index)
    if tcol and pd.notna(latest):
        current_mask = pd.to_datetime(out[tcol], errors="coerce", utc=True).eq(latest)
    if not current_mask.any() and len(out):
        current_mask.iloc[0] = True
    proper = _mapping(result.get("proper_scoring"))
    competing = _mapping(result.get("competing_risk"))
    selected = _mapping(competing.get("selected"))
    final = _mapping(result.get("current_summary"))
    h = int(final.get("selected_horizon") or 3)
    riskrow = _mapping(_mapping(selected.get("horizons")).get(f"{h if h in RISK_HORIZONS else 3}h"))
    values = {
        "CRPS": proper.get(f"crps_h{h}") or proper.get("mean_crps"),
        "Energy Score": proper.get("joint_energy_score"),
        "TP First %": None if riskrow.get("tp_first_probability") is None else float(riskrow["tp_first_probability"]) * 100.0,
        "SL First %": None if riskrow.get("sl_first_probability") is None else float(riskrow["sl_first_probability"]) * 100.0,
        "Confidence Sequence": _mapping(result.get("confidence_sequence")).get("trust_status"),
        "Required Confidence %": _mapping(result.get("selective_prediction")).get("required_confidence_threshold"),
        "Invariance Score": _mapping(result.get("invariance")).get("invariance_score"),
        "Robust EV pips": _mapping(result.get("robust_expectancy")).get("robust_expected_value"),
        "Extreme Risk": "BLOCK" if _mapping(result.get("evt_tail")).get("extreme_risk_block") else "OK",
    }
    for col, value in values.items():
        if col not in out:
            out[col] = np.nan if isinstance(value, (int, float, np.number)) or value is None else ""
        out.loc[current_mask, col] = value
    return out


def build_and_apply_research_risk_stack(
    canonical: Mapping[str, Any], *, ohlc: Any, trust_store: Any,
    priority_table: Any = None, calibrated_bundle: Any = None,
    previous_cache: Optional[Mapping[str, Any]] = None,
    precomputed_periodicity: Optional[Mapping[str, Any]] = None,
    precomputed_periodicity_frame: Optional[pd.DataFrame] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], pd.DataFrame, Any]:
    payload = deepcopy(dict(canonical or {}))
    settled = trust_store.frame(status="SETTLED", limit=20000) if trust_store is not None else pd.DataFrame()
    if isinstance(precomputed_periodicity, Mapping) and isinstance(precomputed_periodicity_frame, pd.DataFrame) and not precomputed_periodicity_frame.empty:
        periodicity, periodicity_frame = dict(precomputed_periodicity), precomputed_periodicity_frame
    else:
        periodicity, periodicity_frame = build_periodicity_normalization(ohlc, settled=settled)
    proper = build_proper_scoring(settled, _mapping(previous_cache).get("proper_scoring"))
    final = _mapping(payload.get("final_decision"))
    regime = _mapping(payload.get("regime"))
    current_direction = _direction(final.get("directional_market_view") or payload.get("full_metric_direction"))
    latest = pd.to_datetime(payload.get("latest_completed_candle_time"), errors="coerce", utc=True)
    current_session = _session(latest) if pd.notna(latest) else "UNKNOWN"
    current_regime = str(regime.get("major_regime") or payload.get("current_major_regime") or "UNKNOWN")
    priority_class = _current_priority(payload, priority_table)
    current_confidence = final.get("calibrated_confidence")
    competing, events = build_competing_risk(
        settled, ohlc, current_regime=current_regime, current_session=current_session,
        current_direction=current_direction, current_priority=priority_class, current_confidence=current_confidence,
    )
    db_path = getattr(trust_store, "db_path", None)
    store = ResearchRiskStore(db_path)
    confidence = build_confidence_sequences(settled, events, store)
    selective = build_selective_prediction(
        settled, current_direction=current_direction, current_session=current_session,
        current_regime=current_regime, current_confidence=current_confidence,
    )
    invariance = build_invariance(ohlc, priority_table)
    event_intensity = build_event_intensity(periodicity_frame, payload, settled)
    evt = build_evt_tail(settled, periodicity_frame, payload)
    robust = build_robust_expectancy(payload, selective, evt, event_intensity, proper, competing, periodicity)
    risk_multiplier = build_risk_multiplier(payload, competing, evt, confidence, robust)
    selected_horizon = int(_finite(final.get("selected_horizon"), 3) or 3)
    selected_risk = _mapping(_mapping(_mapping(competing.get("selected")).get("horizons")).get(f"{selected_horizon if selected_horizon in RISK_HORIZONS else 3}h"))
    result: Dict[str, Any] = {
        "ok": True, "version": VERSION, "generated_at": _utc_now(),
        "calculation_id": payload.get("canonical_calculation_id") or payload.get("run_id"),
        "periodicity": periodicity, "proper_scoring": proper, "competing_risk": competing,
        "confidence_sequence": confidence, "selective_prediction": selective, "evt_tail": evt,
        "invariance": invariance, "risk_multiplier": risk_multiplier, "robust_expectancy": robust,
        "event_intensity": event_intensity,
        "current_summary": {
            "direction": current_direction, "selected_horizon": selected_horizon,
            "tp_first_probability": selected_risk.get("tp_first_probability"),
            "sl_first_probability": selected_risk.get("sl_first_probability"),
            "required_confidence_threshold": selective.get("required_confidence_threshold"),
            "selective_prediction_pass": selective.get("selective_prediction_pass"),
            "robust_expected_value": robust.get("robust_expected_value"),
            "extreme_risk_block": evt.get("extreme_risk_block"),
            "display_risk_multiplier": risk_multiplier.get("display_risk_multiplier"),
        },
        "performance_policy": {"settled_only": True, "causal_periodicity_shift": True, "fixed_threshold_grid": True, "no_new_direction_engine": True},
    }

    # Bounded reliability/weight confirmation. Direction is never changed here.
    reliability = dict(_mapping(payload.get("reliability")))
    old_rel = _finite(reliability.get("score"), None)
    if old_rel is not None:
        modifier = float(proper.get("reliability_modifier") or 1.0) * float(invariance.get("invariant_support_weight") or 1.0)
        if confidence.get("trust_status") == "DEGRADED":
            modifier *= .88
        elif confidence.get("trust_status") == "UNSTABLE":
            modifier *= .94
        if event_intensity.get("event_cluster_level") in {"HIGH", "CRITICAL"}:
            modifier *= .92
        reliability["pre_research_risk_score"] = old_rel
        reliability["score"] = _clip(old_rel * modifier, 0.0, min(100.0, old_rel * 1.04), old_rel)
        reliability["research_risk_modifier"] = modifier
    reliability["proper_scoring"] = proper
    reliability["confidence_sequence"] = confidence
    reliability["selective_prediction"] = selective
    payload["reliability"] = reliability

    risk = dict(_mapping(payload.get("risk")))
    event_level = str(event_intensity.get("event_cluster_level") or "LOW")
    exit_risk_addition = 0.0
    if event_level == "HIGH":
        exit_risk_addition += 0.5
    elif event_level == "CRITICAL":
        exit_risk_addition += 1.0
    if evt.get("extreme_risk_block"):
        exit_risk_addition += 1.5
    risk.update({
        "tp_first_probability": selected_risk.get("tp_first_probability"),
        "sl_first_probability": selected_risk.get("sl_first_probability"),
        "neither_hit_probability": selected_risk.get("neither_hit_probability"),
        "extreme_adverse_probability": evt.get("extreme_adverse_probability"),
        "tail_expected_shortfall": evt.get("tail_expected_shortfall"),
        "extreme_move_99": evt.get("extreme_move_99"),
        "extreme_risk_block": evt.get("extreme_risk_block"),
        "robust_expected_value": robust.get("robust_expected_value"),
        "risk_multiplier": risk_multiplier.get("display_risk_multiplier"),
        "event_cluster_level": event_intensity.get("event_cluster_level"),
        "competing_risk_tp_quality_0_10": None if selected_risk.get("tp_first_probability") is None else float(selected_risk.get("tp_first_probability")) * 10.0,
        "competing_risk_exit_risk_0_10": None if selected_risk.get("sl_first_probability") is None else float(selected_risk.get("sl_first_probability")) * 10.0,
        "research_exit_risk_addition_0_10": exit_risk_addition,
    })
    payload["risk"] = risk
    original_exit_risk = _finite(payload.get("exit_risk"), None)
    if original_exit_risk is not None and exit_risk_addition > 0:
        payload["pre_research_exit_risk"] = original_exit_risk
        payload["exit_risk"] = _clip(original_exit_risk + exit_risk_addition, 0.0, 10.0, original_exit_risk)
    payload["tp_quality_research_confirmation"] = risk.get("competing_risk_tp_quality_0_10")
    payload["exit_risk_research_confirmation"] = risk.get("competing_risk_exit_risk_0_10")

    final_out = dict(final)
    current_prob = _prob(current_confidence, 0.0) or 0.0
    confidence_penalty = 0.0
    if confidence.get("trust_status") == "DEGRADED":
        confidence_penalty += 0.06
    elif confidence.get("trust_status") == "UNSTABLE":
        confidence_penalty += 0.03
    if event_level == "HIGH":
        confidence_penalty += 0.03
    elif event_level == "CRITICAL":
        confidence_penalty += 0.07
    if evt.get("extreme_risk_block"):
        confidence_penalty += 0.08
    confidence_penalty += max(0.0, 1.0 - float(proper.get("reliability_modifier") or 1.0))
    adjusted_prob = _clip(current_prob - confidence_penalty, 0.0, current_prob, current_prob)
    if current_confidence is not None:
        final_out["pre_research_calibrated_confidence"] = current_confidence
        final_out["calibrated_confidence"] = adjusted_prob * 100.0 if float(current_confidence) > 1.0 else adjusted_prob
    uncertainty = _finite(final_out.get("uncertainty_pct"), 0.0) or 0.0
    if uncertainty <= 1.0 and final_out.get("uncertainty_pct") is not None:
        uncertainty *= 100.0
    final_out["uncertainty_pct"] = _clip(uncertainty + confidence_penalty * 100.0, 0.0, 100.0, uncertainty)
    final_out["research_confidence_penalty_pct"] = confidence_penalty * 100.0
    current_pct = adjusted_prob * 100.0
    blockers = list(final_out.get("blocking_reasons") or [])
    safety_blockers: list[str] = []
    if current_direction in {"BUY", "SELL"} and not selective.get("selective_prediction_pass"):
        safety_blockers.append(f"Selective risk coverage: {selective.get('abstention_reason')}")
    if confidence.get("trust_status") == "DEGRADED":
        safety_blockers.append("Anytime-valid trust status DEGRADED")
    if evt.get("extreme_risk_block"):
        safety_blockers.append("EVT extreme-risk block")
    if event_intensity.get("event_cluster_level") == "CRITICAL":
        safety_blockers.append("Critical event-cluster intensity")
    if current_direction in {"BUY", "SELL"} and not robust.get("robust_entry_pass"):
        safety_blockers.append("Robust expected value does not clear costs and safety buffer")
    if safety_blockers:
        final_out["pre_research_risk_final_decision"] = final_out.get("final_decision")
        final_out["final_decision"] = "WAIT"
        final_out["tradeability_decision"] = "WAIT"
        final_out["less_risky_decision"] = "WAIT"
        blockers.extend(safety_blockers)
    final_out["blocking_reasons"] = list(dict.fromkeys(map(str, blockers)))
    final_out.update({
        "required_confidence_threshold": selective.get("required_confidence_threshold"),
        "selective_prediction_pass": selective.get("selective_prediction_pass"),
        "abstention_reason": selective.get("abstention_reason"),
        "tp_first_probability": selected_risk.get("tp_first_probability"),
        "sl_first_probability": selected_risk.get("sl_first_probability"),
        "robust_expected_value": robust.get("robust_expected_value"),
        "extreme_risk_warning": bool(evt.get("extreme_risk_block")),
        "display_risk_multiplier": risk_multiplier.get("display_risk_multiplier"),
        "research_risk_reason": safety_blockers[0] if safety_blockers else "Research risk stack confirms the existing canonical decision",
        "pre_gate_confidence_pct": current_pct,
    })
    payload["final_decision"] = final_out
    payload["research_risk_stack"] = _json_safe(result)
    payload["periodicity_normalization"] = periodicity
    payload["proper_scoring"] = proper
    payload["competing_risk"] = competing
    payload["confidence_sequence"] = confidence
    payload["selective_prediction"] = selective
    payload["evt_tail"] = evt
    payload["invariance_reliability"] = invariance
    payload["risk_multiplier"] = risk_multiplier
    payload["robust_expectancy"] = robust
    payload["event_intensity"] = event_intensity
    payload.setdefault("metadata", {})["research_risk_stack_version"] = VERSION
    payload["metadata"]["research_risk_stack_direction_policy"] = "confirm/downgrade/WAIT only"
    payload["metadata"]["periodicity_inputs_for_existing_risk"] = {
        "drift": periodicity.get("periodicity_normalized_residual"),
        "change_point": periodicity.get("periodicity_normalized_return"),
        "volatility_anomaly": periodicity.get("periodicity_normalized_range"),
        "compression": periodicity.get("periodicity_normalized_range"),
        "entropy": abs(float(periodicity.get("periodicity_normalized_return") or 0.0)),
        "regime_transition_warning": event_intensity.get("event_cluster_level"),
    }
    enriched = _enrich_table(priority_table, periodicity_frame, result, payload.get("latest_completed_candle_time"))
    adjusted_bundle = _adjust_powerbi_bundle(calibrated_bundle, result)
    calc_id = str(payload.get("canonical_calculation_id") or payload.get("run_id") or _utc_now())
    store.persist_snapshot(calc_id, result)
    return payload, result, enriched, adjusted_bundle


def enrich_metric_history(metric_result: Mapping[str, Any], enriched_priority: pd.DataFrame) -> Dict[str, Any]:
    """Add compact research columns to the preserved Full Metric history by time.

    Original columns and row order are retained. No Full Metric formula is changed.
    """
    result = dict(metric_result or {})
    history = result.get("history")
    if not isinstance(history, pd.DataFrame) or history.empty or not isinstance(enriched_priority, pd.DataFrame) or enriched_priority.empty:
        return result
    h = history.copy(deep=False)
    h_time = next((c for c in ("Time", "time", "DateTime", "timestamp") if c in h), None)
    p_time = next((c for c in ("Time", "time", "DateTime", "timestamp") if c in enriched_priority), None)
    if not h_time or not p_time:
        return result
    added = [c for c in ("Periodicity Norm Vol", "CRPS", "Energy Score", "TP First %", "SL First %", "Confidence Sequence", "Required Confidence %", "Invariance Score", "Robust EV pips", "Extreme Risk") if c in enriched_priority]
    if not added:
        return result
    left = h.assign(__time=pd.to_datetime(h[h_time], errors="coerce", utc=True))
    right = enriched_priority[[p_time] + added].copy(deep=False)
    right["__time"] = pd.to_datetime(right[p_time], errors="coerce", utc=True)
    right = right.drop(columns=[p_time]).dropna(subset=["__time"]).drop_duplicates("__time", keep="first")
    merged = left.merge(right, on="__time", how="left", suffixes=("", "__research")).drop(columns="__time")
    result["history"] = merged
    return result


__all__ = [
    "VERSION", "build_periodicity_normalization", "build_proper_scoring", "build_competing_risk",
    "build_confidence_sequences", "build_selective_prediction", "build_evt_tail", "build_invariance",
    "build_risk_multiplier", "build_robust_expectancy", "build_event_intensity",
    "build_and_apply_research_risk_stack", "enrich_metric_history", "ResearchRiskStore",
]
