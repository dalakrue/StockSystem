# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Second-generation reliability and distribution-shift transaction.

This module is intentionally additive and display-independent.  It consumes one
already-cleaned completed-UTC-H1 frame, one chronological settled-prediction
frame, and one canonical payload.  It never creates an independent BUY/SELL
signal and never reverses the protected Full Metric direction.  Its only policy
powers are to:

* calibrate probabilities when evidence and assumptions are valid;
* cap research trust / effective priority;
* append warnings; and
* conservatively downgrade an existing BUY/SELL tradeability decision to WAIT
  through the final Conformal Risk Control gate.

The implementation is lightweight (NumPy/Pandas/SQLite only), bounded, and safe
for Streamlit Cloud / Python 3.12.  Offline-only DML maintenance is exposed as a
pure function and is never executed by normal tab navigation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from core.generation_identity_20260707 import numeric_generation

VERSION = "advanced-reliability-shift-20260620-v2"
SCHEMA_VERSION = "adx-advanced-reliability-shift-2.0.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "quant_app.sqlite3"
HORIZONS = (1, 2, 3, 6)
_MAX_OHLC_ROWS = 720
_MAX_SETTLED_ROWS = 6000
_MAX_MMD_SAMPLE = 128
_LOCK = threading.RLock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _finite(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except Exception:
        return default


def _clip(value: Any, lo: float, hi: float, default: float = 0.0) -> float:
    number = _finite(value, default)
    return float(max(lo, min(hi, number if number is not None else default)))


def _prob(value: Any, default: Optional[float] = None) -> Optional[float]:
    number = _finite(value, default)
    if number is None:
        return None
    if number > 1.0:
        number /= 100.0
    return float(max(0.0, min(1.0, number)))


def _direction(value: Any) -> str:
    text = str(value or "").upper()
    if "BUY" in text or "BULL" in text or text == "UP":
        return "BUY"
    if "SELL" in text or "BEAR" in text or text == "DOWN":
        return "SELL"
    return "WAIT"


def _utc(value: Any) -> Optional[pd.Timestamp]:
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    except Exception:
        return None


def _session(value: Any) -> str:
    ts = _utc(value)
    if ts is None:
        return "UNKNOWN"
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
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(v) for v in value.tolist()]
    if isinstance(value, pd.DataFrame):
        return [_json_safe(v) for v in value.to_dict("records")]
    if isinstance(value, pd.Series):
        return [_json_safe(v) for v in value.tolist()]
    if isinstance(value, (pd.Timestamp, datetime)):
        ts = _utc(value)
        return ts.isoformat() if ts is not None else str(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if value is pd.NA:
        return None
    return value


def _stable_hash(value: Any) -> str:
    payload = json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _find_column(frame: pd.DataFrame, aliases: Sequence[str]) -> Optional[str]:
    lookup = {str(column).strip().lower(): column for column in frame.columns}
    return next((lookup[name.lower()] for name in aliases if name.lower() in lookup), None)


def normalize_completed_h1(frame: Any, latest_completed: Any = None, *, limit: int = _MAX_OHLC_ROWS) -> pd.DataFrame:
    """Return one sorted, unique, bounded completed-H1 frame.

    The upstream data-quality layer already removes an open candle.  This helper
    applies an additional explicit canonical cutoff and never infers or appends
    future rows.  Rolling features elsewhere use trailing windows only.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    data = frame.copy(deep=False)
    tcol = _find_column(data, ("time", "timestamp", "datetime", "date"))
    columns: Dict[str, Optional[str]] = {
        name: _find_column(data, (name, name[0])) for name in ("open", "high", "low", "close")
    }
    if any(value is None for value in columns.values()):
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    times = pd.to_datetime(data[tcol] if tcol is not None else data.index, errors="coerce", utc=True)
    out = pd.DataFrame({"time": times})
    for name, column in columns.items():
        out[name] = pd.to_numeric(data[column], errors="coerce").to_numpy()
    volume_col = _find_column(data, ("volume", "tick_volume", "real_volume"))
    out["volume"] = pd.to_numeric(data[volume_col], errors="coerce").to_numpy() if volume_col else 0.0
    # Carry existing bounded indicators without recalculating them.
    for name in ("atr", "adx", "plus_di", "minus_di", "pressure", "periodicity_normalized_residual"):
        column = _find_column(data, (name,))
        if column is not None:
            out[name] = pd.to_numeric(data[column], errors="coerce").to_numpy()
    out = out.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time")
    out = out.drop_duplicates("time", keep="last")
    cutoff = _utc(latest_completed)
    if cutoff is not None:
        out = out.loc[out["time"] <= cutoff]
    return out.tail(max(1, int(limit))).reset_index(drop=True)


def normalize_settled_predictions(frame: Any, latest_completed: Any = None, *, limit: int = _MAX_SETTLED_ROWS) -> pd.DataFrame:
    """Return one chronological bounded settled-evidence frame."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    data = frame.copy(deep=False)
    status_col = _find_column(data, ("record_status", "outcome_status", "status"))
    if status_col is not None:
        statuses = data[status_col].astype(str).str.upper()
        if statuses.str.contains("SETTLED").any():
            data = data.loc[statuses.str.contains("SETTLED")]
    origin_col = _find_column(data, ("forecast_origin_time", "origin_time", "created_at", "time"))
    target_col = _find_column(data, ("target_time", "settled_target_time"))
    settled_col = _find_column(data, ("settlement_timestamp", "settled_at"))
    data = data.assign(
        __origin=pd.to_datetime(data[origin_col], errors="coerce", utc=True) if origin_col else pd.NaT,
        __target=pd.to_datetime(data[target_col], errors="coerce", utc=True) if target_col else pd.NaT,
        __settled=pd.to_datetime(data[settled_col], errors="coerce", utc=True) if settled_col else pd.NaT,
    )
    data["__order"] = data["__settled"].fillna(data["__target"]).fillna(data["__origin"])
    cutoff = _utc(latest_completed)
    if cutoff is not None:
        data = data.loc[data["__target"].isna() | (data["__target"] <= cutoff)]
    data = data.loc[data["__order"].notna()].sort_values("__order")
    calc_col = _find_column(data, ("calculation_id", "canonical_calculation_id", "run_id"))
    horizon_col = _find_column(data, ("horizon", "horizon_hours"))
    if calc_col and horizon_col:
        data = data.drop_duplicates([calc_col, horizon_col], keep="last")
    return data.tail(max(1, int(limit))).reset_index(drop=True)


def completed_h1_hash(frame: pd.DataFrame) -> str:
    if frame.empty:
        return hashlib.sha256(b"empty-h1").hexdigest()
    columns = [column for column in ("time", "open", "high", "low", "close", "volume") if column in frame]
    records = frame[columns].tail(_MAX_OHLC_ROWS).copy(deep=False)
    if "time" in records:
        records = records.assign(time=pd.to_datetime(records["time"], utc=True, errors="coerce").astype(str))
    return _stable_hash(records.to_dict("records"))


def _selected_horizon(canonical: Mapping[str, Any]) -> int:
    final = _mapping(canonical.get("final_decision"))
    forecasts = _mapping(canonical.get("forecasts"))
    value = _finite(final.get("selected_horizon") or forecasts.get("selected_horizon"), 3)
    horizon = int(value or 3)
    return horizon if horizon in HORIZONS else 3


def _selected_forecast(canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    horizon = _selected_horizon(canonical)
    return _mapping(_mapping(_mapping(canonical.get("forecasts")).get("horizons")).get(f"{horizon}h"))


def _current_identity(canonical: Mapping[str, Any], h1: pd.DataFrame) -> Dict[str, Any]:
    final = _mapping(canonical.get("final_decision"))
    regime = _mapping(canonical.get("regime"))
    multiscale = _mapping(canonical.get("multiscale_regime"))
    latest = canonical.get("latest_completed_candle_time")
    if latest is None and not h1.empty:
        latest = h1["time"].iloc[-1]
    direction = _direction(final.get("directional_market_view") or canonical.get("full_metric_direction"))
    return {
        "calculation_id": str(canonical.get("canonical_calculation_id") or canonical.get("run_id") or ""),
        "generation": numeric_generation(canonical.get("calculation_generation") or canonical.get("generation_id"), default=1),
        "latest_completed_h1_time": _json_safe(latest),
        "data_hash": completed_h1_hash(h1),
        "direction": direction,
        "decision": _direction(final.get("final_decision")),
        "horizon": _selected_horizon(canonical),
        "session": _session(latest),
        "hour": int(_utc(latest).hour) if _utc(latest) is not None else None,
        "h1_regime": str(regime.get("h1_regime") or regime.get("major_regime") or canonical.get("current_major_regime") or "UNKNOWN"),
        "h4_regime": str(regime.get("h4_regime") or "UNKNOWN"),
        "d1_regime": str(regime.get("d1_regime") or "UNKNOWN"),
        "volatility_state": str(multiscale.get("current_volatility_regime") or "UNKNOWN"),
        "event_risk": str(_mapping(canonical.get("nlp")).get("event_risk_status") or _mapping(canonical.get("nlp")).get("importance") or "UNKNOWN"),
        "conflict": bool(final.get("blocking_reasons")),
        "counter_trend": bool("counter" in " ".join(map(str, final.get("blocking_reasons") or [])).lower()),
        "transition_risk": _finite(multiscale.get("multi_scale_transition_risk_pct") or regime.get("transition_risk"), None),
    }


def _column_numeric(frame: pd.DataFrame, aliases: Sequence[str], default: Any = np.nan) -> pd.Series:
    column = _find_column(frame, aliases)
    if column is None:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _column_text(frame: pd.DataFrame, aliases: Sequence[str], default: str = "UNKNOWN") -> pd.Series:
    column = _find_column(frame, aliases)
    if column is None:
        return pd.Series(default, index=frame.index, dtype=object)
    return frame[column].fillna(default).astype(str)


def _predicted_direction_series(frame: pd.DataFrame) -> pd.Series:
    column = _find_column(frame, ("full_metric_direction", "final_decision", "predicted_direction", "direction"))
    if column is not None:
        return frame[column].map(_direction)
    buy = _column_numeric(frame, ("calibrated_buy_probability", "raw_buy_probability"))
    sell = _column_numeric(frame, ("calibrated_sell_probability", "raw_sell_probability"))
    wait = _column_numeric(frame, ("calibrated_wait_probability", "raw_wait_probability"))
    matrix = np.column_stack([buy.fillna(0), sell.fillna(0), wait.fillna(0)])
    labels = np.array(["BUY", "SELL", "WAIT"])
    return pd.Series(labels[np.argmax(matrix, axis=1)], index=frame.index)


def _actual_direction_series(frame: pd.DataFrame) -> pd.Series:
    actual = _column_numeric(frame, ("actual_close",))
    origin = _column_numeric(frame, ("forecast_origin_price", "origin_price", "last_close"))
    delta = actual - origin
    deadband = 0.00002
    labels = np.where(delta > deadband, "BUY", np.where(delta < -deadband, "SELL", "WAIT"))
    missing = actual.isna() | origin.isna()
    predicted = _predicted_direction_series(frame)
    correct = _column_numeric(frame, ("direction_correct",))
    fallback = np.where(correct.fillna(-1).to_numpy() == 1, predicted.to_numpy(), np.where(predicted == "BUY", "SELL", np.where(predicted == "SELL", "BUY", "WAIT")))
    labels = np.where(missing.to_numpy(), fallback, labels)
    return pd.Series(labels, index=frame.index)


def _probability_for_direction(frame: pd.DataFrame, direction: str, *, calibrated: bool = True) -> pd.Series:
    prefix = "calibrated" if calibrated else "raw"
    aliases = (f"{prefix}_{direction.lower()}_probability", f"{direction.lower()}_probability_{prefix}")
    series = _column_numeric(frame, aliases)
    if series.notna().sum() == 0 and calibrated:
        series = _probability_for_direction(frame, direction, calibrated=False)
    return series.map(lambda value: _prob(value, np.nan))


def _current_probabilities(canonical: Mapping[str, Any]) -> Dict[str, float]:
    forecast = _selected_forecast(canonical)
    values = {
        "BUY": _prob(forecast.get("buy_probability_calibrated") or forecast.get("buy_probability_raw"), None),
        "SELL": _prob(forecast.get("sell_probability_calibrated") or forecast.get("sell_probability_raw"), None),
        "WAIT": _prob(forecast.get("wait_probability_calibrated") or forecast.get("wait_probability_raw"), None),
    }
    missing = [key for key, value in values.items() if value is None]
    if missing:
        direction = _direction(_mapping(canonical.get("final_decision")).get("directional_market_view"))
        default = {"BUY": 0.25, "SELL": 0.25, "WAIT": 0.50}
        if direction == "BUY":
            default = {"BUY": 0.55, "SELL": 0.20, "WAIT": 0.25}
        elif direction == "SELL":
            default = {"BUY": 0.20, "SELL": 0.55, "WAIT": 0.25}
        for key in missing:
            values[key] = default[key]
    total = sum(float(value or 0) for value in values.values()) or 1.0
    return {key: float(value or 0) / total for key, value in values.items()}


# ---------------------------------------------------------------------------
# A. Conformal Risk Control (operational chronological approximation)
# ---------------------------------------------------------------------------


def _risk_losses(frame: pd.DataFrame, direction: str) -> pd.DataFrame:
    predicted = _predicted_direction_series(frame)
    correct = _column_numeric(frame, ("direction_correct",))
    tp = _column_numeric(frame, ("tp_touched",))
    sl = _column_numeric(frame, ("sl_touched",))
    confidence = _probability_for_direction(frame, direction, calibrated=True)
    non_wait = predicted.isin(["BUY", "SELL"]).astype(float)
    false_entry = ((non_wait == 1) & (correct.fillna(0) <= 0)).astype(float)
    sl_before_tp = ((sl.fillna(0) > 0) & (tp.fillna(0) <= 0)).astype(float)
    incorrect_high = ((confidence.fillna(0) >= 0.70) & (correct.fillna(0) <= 0)).astype(float)
    unsafe_non_wait = np.maximum.reduce([
        false_entry.to_numpy(dtype=float),
        sl_before_tp.to_numpy(dtype=float),
        incorrect_high.to_numpy(dtype=float),
    ])
    return pd.DataFrame({
        "confidence": confidence.fillna(0.0).clip(0, 1),
        "false_entry": false_entry,
        "sl_before_tp": sl_before_tp,
        "incorrect_high_confidence": incorrect_high,
        "unsafe_non_wait": unsafe_non_wait,
    }, index=frame.index)


def _condition_masks(frame: pd.DataFrame, identity: Mapping[str, Any]) -> Sequence[Tuple[str, pd.Series, int]]:
    predicted = _predicted_direction_series(frame)
    horizon = _column_numeric(frame, ("horizon", "horizon_hours"))
    origin = pd.to_datetime(frame.get("__origin", pd.Series(pd.NaT, index=frame.index)), utc=True, errors="coerce")
    sessions = origin.map(_session)
    regime = _column_text(frame, ("h1_regime", "regime", "major_regime"))
    event = _column_text(frame, ("event_risk_status", "event_importance"))
    direction = str(identity.get("direction") or "WAIT")
    selected = int(identity.get("horizon") or 3)
    session = str(identity.get("session") or "UNKNOWN")
    h1_regime = str(identity.get("h1_regime") or "UNKNOWN")
    event_risk = str(identity.get("event_risk") or "UNKNOWN")
    all_mask = pd.Series(True, index=frame.index)
    return (
        ("direction+horizon+session+regime+event", (predicted == direction) & (horizon == selected) & (sessions == session) & (regime == h1_regime) & (event == event_risk), 40),
        ("direction+horizon+session+regime", (predicted == direction) & (horizon == selected) & (sessions == session) & (regime == h1_regime), 35),
        ("direction+horizon+session", (predicted == direction) & (horizon == selected) & (sessions == session), 30),
        ("direction+horizon", (predicted == direction) & (horizon == selected), 25),
        ("horizon", horizon == selected, 25),
        ("global", all_mask, 25),
    )


def conformal_risk_control(
    settled: pd.DataFrame,
    identity: Mapping[str, Any],
    *,
    target_risk: Optional[float] = None,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    target = float(target_risk if target_risk is not None else (0.15 if str(identity.get("event_risk", "")).upper() in {"HIGH", "CRITICAL"} or bool(identity.get("conflict")) else 0.20))
    if settled.empty or identity.get("direction") not in {"BUY", "SELL"}:
        return {
            "status": "INSUFFICIENT_EVIDENCE", "validity_status": "INVALID",
            "target_risk": target, "observed_risk": None, "risk_upper_bound": None,
            "threshold": None, "condition": None, "sample_count": 0,
            "losses": {}, "reason": "No settled non-WAIT directional evidence.",
        }
    chosen = None
    for level, mask, minimum in _condition_masks(settled, identity):
        subset = settled.loc[mask]
        if len(subset) >= minimum:
            chosen = (level, subset.tail(1200), minimum)
            break
    if chosen is None:
        return {
            "status": "INSUFFICIENT_EVIDENCE", "validity_status": "INVALID",
            "target_risk": target, "observed_risk": None, "risk_upper_bound": None,
            "threshold": None, "condition": "no_fallback_met", "sample_count": int(len(settled)),
            "losses": {}, "reason": "Hierarchical calibration groups did not meet minimum settled support.",
        }
    level, subset, minimum = chosen
    losses = _risk_losses(subset, str(identity["direction"]))
    n = int(len(losses))
    correction = math.sqrt(math.log(1.0 / max(1e-9, alpha)) / (2.0 * max(1, n)))
    thresholds = np.round(np.linspace(0.50, 1.00, 51), 2)
    curve = []
    unsafe = losses["unsafe_non_wait"].to_numpy(dtype=float)
    confidence = losses["confidence"].to_numpy(dtype=float)
    for threshold in thresholds:
        # Monotone bounded loss: a stricter threshold can only turn an action
        # into abstention, so every per-row loss is non-increasing in threshold.
        gated_loss = unsafe * (confidence >= threshold).astype(float)
        observed = float(np.mean(gated_loss))
        upper = min(1.0, observed + correction)
        curve.append({
            "threshold": float(threshold), "observed_risk": observed,
            "risk_upper_bound": upper, "action_rate": float(np.mean(confidence >= threshold)),
        })
    feasible = [row for row in curve if row["risk_upper_bound"] <= target]
    selected = feasible[0] if feasible else curve[-1]
    loss_summary = {name: float(losses[name].mean()) for name in ("false_entry", "sl_before_tp", "incorrect_high_confidence", "unsafe_non_wait")}
    valid = bool(feasible) and n >= minimum
    return {
        "status": "VALID" if valid else "RISK_NOT_CONTROLLED",
        "validity_status": "VALID" if valid else "CONSERVATIVE_BLOCK",
        "target_risk": target,
        "observed_risk": selected["observed_risk"],
        "risk_upper_bound": selected["risk_upper_bound"],
        "threshold": selected["threshold"],
        "condition": level,
        "sample_count": n,
        "minimum_sample_rule": minimum,
        "action_rate": selected["action_rate"],
        "losses": loss_summary,
        "monotone_loss_verified": all(curve[index]["observed_risk"] + 1e-12 >= curve[index + 1]["observed_risk"] for index in range(len(curve) - 1)),
        "curve": curve[::5] + ([curve[-1]] if curve[-1] not in curve[::5] else []),
        "assumption_note": "Chronological settled operational approximation; no iid/exchangeability guarantee is claimed for EURUSD H1.",
    }


# ---------------------------------------------------------------------------
# B. Multicalibration with overlapping groups and shrinkage
# ---------------------------------------------------------------------------


def _settled_group_columns(frame: pd.DataFrame) -> pd.DataFrame:
    origin = pd.to_datetime(frame.get("__origin", pd.Series(pd.NaT, index=frame.index)), utc=True, errors="coerce")
    result = pd.DataFrame(index=frame.index)
    result["session"] = origin.map(_session)
    result["hour"] = origin.dt.hour.fillna(-1).astype(int)
    result["h1_regime"] = _column_text(frame, ("h1_regime", "major_regime", "regime"))
    result["h4_regime"] = _column_text(frame, ("h4_regime",))
    result["d1_regime"] = _column_text(frame, ("d1_regime",))
    result["volatility_state"] = _column_text(frame, ("volatility_state", "drift_status"))
    result["direction"] = _predicted_direction_series(frame)
    result["horizon"] = _column_numeric(frame, ("horizon", "horizon_hours")).fillna(-1).astype(int)
    result["event_risk"] = _column_text(frame, ("event_risk_status", "event_importance"))
    result["conflict"] = _column_text(frame, ("conflict_status", "strongest_blocker"), "NONE").str.upper().ne("NONE")
    result["counter_trend"] = _column_text(frame, ("counter_trend", "strongest_blocker"), "").str.lower().str.contains("counter")
    transition = _column_numeric(frame, ("regime_transition_risk", "transition_risk"))
    result["transition_risk"] = pd.cut(transition, [-np.inf, 0.33, 0.66, np.inf], labels=["LOW", "MEDIUM", "HIGH"]).astype(str)
    return result


def multicalibrate_probability(
    settled: pd.DataFrame,
    identity: Mapping[str, Any],
    raw_probability: float,
    *,
    min_support: int = 30,
    shrinkage: float = 60.0,
    max_total_adjustment: float = 0.15,
) -> Dict[str, Any]:
    direction = str(identity.get("direction") or "WAIT")
    if settled.empty or direction not in {"BUY", "SELL", "WAIT"}:
        return {"status": "INSUFFICIENT_EVIDENCE", "raw_probability": raw_probability, "calibrated_probability": raw_probability, "calibration_gap": 0.0, "subgroup_support": 0, "fallback_level": "NONE", "groups": []}
    groups = _settled_group_columns(settled)
    probability = _probability_for_direction(settled, direction, calibrated=False)
    actual = (_actual_direction_series(settled) == direction).astype(float)
    valid = probability.notna() & actual.notna()
    probability = probability.loc[valid]
    actual = actual.loc[valid]
    groups = groups.loc[valid]
    if len(probability) < min_support:
        return {"status": "INSUFFICIENT_EVIDENCE", "raw_probability": raw_probability, "calibrated_probability": raw_probability, "calibration_gap": 0.0, "subgroup_support": int(len(probability)), "fallback_level": "GLOBAL_INSUFFICIENT", "groups": []}

    transition_value = _finite(identity.get("transition_risk"), None)
    transition_label = "UNKNOWN" if transition_value is None else "LOW" if transition_value <= 33 else "MEDIUM" if transition_value <= 66 else "HIGH"
    current = {
        "session": identity.get("session"), "hour": identity.get("hour"),
        "h1_regime": identity.get("h1_regime"), "h4_regime": identity.get("h4_regime"),
        "d1_regime": identity.get("d1_regime"), "volatility_state": identity.get("volatility_state"),
        "direction": direction, "horizon": identity.get("horizon"), "event_risk": identity.get("event_risk"),
        "conflict": bool(identity.get("conflict")), "counter_trend": bool(identity.get("counter_trend")),
        "transition_risk": transition_label,
    }
    candidate_groups = []
    for name, value in current.items():
        if value in (None, "", "UNKNOWN", -1):
            continue
        mask = groups[name].astype(str) == str(value)
        support = int(mask.sum())
        if support < min_support:
            continue
        residual = float((actual.loc[mask] - probability.loc[mask]).mean())
        weight = support / (support + shrinkage)
        candidate_groups.append({"group": f"{name}={value}", "support": support, "raw_gap": residual, "shrinkage_weight": weight, "adjustment": residual * weight})
    # Add a few high-value intersections only when they are genuinely supported.
    intersections = (("session", "direction"), ("h1_regime", "direction"), ("horizon", "direction"), ("event_risk", "direction"), ("conflict", "direction"))
    for fields in intersections:
        if any(current.get(field) in (None, "", "UNKNOWN", -1) for field in fields):
            continue
        mask = pd.Series(True, index=groups.index)
        for field in fields:
            mask &= groups[field].astype(str) == str(current[field])
        support = int(mask.sum())
        if support < max(min_support, 40):
            continue
        residual = float((actual.loc[mask] - probability.loc[mask]).mean())
        weight = support / (support + 1.5 * shrinkage)
        candidate_groups.append({"group": "&".join(f"{field}={current[field]}" for field in fields), "support": support, "raw_gap": residual, "shrinkage_weight": weight, "adjustment": residual * weight})
    if not candidate_groups:
        global_gap = float((actual - probability).mean())
        weight = len(probability) / (len(probability) + 2.0 * shrinkage)
        adjustment = float(np.clip(global_gap * weight, -max_total_adjustment, max_total_adjustment))
        calibrated = float(np.clip(raw_probability + adjustment, 0, 1))
        return {"status": "VALID_GLOBAL_FALLBACK", "raw_probability": raw_probability, "calibrated_probability": calibrated, "calibration_gap": calibrated - raw_probability, "subgroup_support": int(len(probability)), "fallback_level": "GLOBAL", "groups": []}
    candidate_groups = sorted(candidate_groups, key=lambda row: (-row["support"], abs(row["adjustment"])))[:8]
    weights = np.array([math.sqrt(row["support"]) for row in candidate_groups], dtype=float)
    adjustments = np.array([row["adjustment"] for row in candidate_groups], dtype=float)
    aggregate = float(np.sum(weights * adjustments) / max(1e-12, np.sum(weights)))
    aggregate = float(np.clip(aggregate, -max_total_adjustment, max_total_adjustment))
    calibrated = float(np.clip(raw_probability + aggregate, 0, 1))
    return {
        "status": "VALID", "raw_probability": float(raw_probability),
        "calibrated_probability": calibrated, "calibration_gap": calibrated - float(raw_probability),
        "subgroup_support": int(max(row["support"] for row in candidate_groups)),
        "fallback_level": "OVERLAPPING_GROUP_SHRINKAGE", "groups": candidate_groups,
        "tiny_group_protection": {"minimum_support": min_support, "shrinkage": shrinkage, "maximum_total_adjustment": max_total_adjustment},
    }


# ---------------------------------------------------------------------------
# C. Reversible Instance Normalization wrapper / evidence gate
# ---------------------------------------------------------------------------


def revin_normalize(values: Sequence[float], epsilon: float = 1e-8) -> Tuple[np.ndarray, float, float]:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return array.copy(), 0.0, 1.0
    mean = float(np.nanmean(array))
    std = float(np.nanstd(array))
    if not math.isfinite(std) or std < epsilon:
        std = 1.0
    return (array - mean) / std, mean, std


def revin_inverse(values: Sequence[float], mean: float, std: float) -> np.ndarray:
    return np.asarray(values, dtype=float) * float(std) + float(mean)


def build_revin_evidence(h1: pd.DataFrame, settled: pd.DataFrame, canonical: Mapping[str, Any]) -> Dict[str, Any]:
    if h1.empty:
        return {"status": "UNAVAILABLE", "influence_enabled": False, "reason": "No completed H1 input window.", "predictions": []}
    close = h1["close"].tail(96).to_numpy(dtype=float)
    normalized, mean, std = revin_normalize(close)
    forecasts = _mapping(_mapping(canonical.get("forecasts")).get("horizons"))
    predictions = []
    for horizon in HORIZONS:
        row = _mapping(forecasts.get(f"{horizon}h"))
        original = _finite(row.get("point_forecast"), None)
        if original is None:
            continue
        normalized_point = (original - mean) / std
        reversed_point = float(revin_inverse([normalized_point], mean, std)[0])
        predictions.append({"horizon": horizon, "original_prediction": original, "revin_prediction": reversed_point, "absolute_roundtrip_error": abs(reversed_point - original)})
    original_col = _find_column(settled, ("original_prediction", "original_predicted_close")) if not settled.empty else None
    revin_col = _find_column(settled, ("revin_prediction", "revin_predicted_close")) if not settled.empty else None
    actual_col = _find_column(settled, ("actual_close",)) if not settled.empty else None
    influence = False
    evidence: Dict[str, Any] = {"status": "DIAGNOSTIC_ONLY", "sample_count": 0, "mae_original": None, "mae_revin": None, "relative_improvement": None}
    if original_col and revin_col and actual_col:
        validation = settled[[original_col, revin_col, actual_col]].apply(pd.to_numeric, errors="coerce").dropna().tail(1200)
        if len(validation) >= 60:
            split = int(len(validation) * 0.70)
            test = validation.iloc[split:]
            mae_original = float(np.mean(np.abs(test[original_col] - test[actual_col])))
            mae_revin = float(np.mean(np.abs(test[revin_col] - test[actual_col])))
            relative = (mae_original - mae_revin) / max(mae_original, 1e-12)
            influence = bool(relative >= 0.02 and len(test) >= 20)
            evidence = {"status": "VALID" if influence else "NO_SUPERIORITY", "sample_count": int(len(test)), "mae_original": mae_original, "mae_revin": mae_revin, "relative_improvement": relative, "purged_walk_forward_required": True}
    return {
        "status": evidence["status"], "input_window_rows": int(len(close)), "window_mean": mean,
        "window_std": std, "latest_normalized_value": float(normalized[-1]) if normalized.size else None,
        "predictions": predictions, "influence_enabled": influence, "settled_evidence": evidence,
        "reason": "Existing contributor interface exposes price-space points only; RevIN is kept as a reversible wrapper and cannot influence weights without settled walk-forward superiority." if not influence else "Settled purged evidence met the conservative RevIN superiority gate.",
    }


# ---------------------------------------------------------------------------
# D. MMD drift detection with bounded block permutation
# ---------------------------------------------------------------------------


def _standardize_pair(x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    pooled = np.vstack([x, y])
    median = np.nanmedian(pooled, axis=0)
    q75 = np.nanpercentile(pooled, 75, axis=0)
    q25 = np.nanpercentile(pooled, 25, axis=0)
    scale = q75 - q25
    std = np.nanstd(pooled, axis=0)
    scale = np.where((~np.isfinite(scale)) | (scale < 1e-9), std, scale)
    scale = np.where((~np.isfinite(scale)) | (scale < 1e-9), 1.0, scale)
    return np.nan_to_num((x - median) / scale), np.nan_to_num((y - median) / scale)


def _pairwise_sqdist(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.maximum(0.0, np.sum(x * x, axis=1)[:, None] + np.sum(y * y, axis=1)[None, :] - 2.0 * x @ y.T)


def rbf_mmd2(x: np.ndarray, y: np.ndarray, gamma: Optional[float] = None) -> Tuple[float, float]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 2 or len(y) < 2:
        return 0.0, 1.0
    x, y = _standardize_pair(x, y)
    pooled = np.vstack([x, y])
    if gamma is None:
        sample = pooled[: min(96, len(pooled))]
        distances = _pairwise_sqdist(sample, sample)
        positive = distances[np.triu_indices_from(distances, k=1)]
        positive = positive[positive > 1e-12]
        median = float(np.median(positive)) if positive.size else 1.0
        gamma = 1.0 / max(1e-9, 2.0 * median)
    kxx = np.exp(-gamma * _pairwise_sqdist(x, x))
    kyy = np.exp(-gamma * _pairwise_sqdist(y, y))
    kxy = np.exp(-gamma * _pairwise_sqdist(x, y))
    # Biased statistic is non-negative and stable in small bounded samples.
    statistic = float(max(0.0, kxx.mean() + kyy.mean() - 2.0 * kxy.mean()))
    return statistic, float(gamma)


def mmd_block_test(
    reference: np.ndarray,
    recent: np.ndarray,
    *,
    seed: int = 0,
    block_size: int = 6,
    permutations: int = 64,
    feature_names: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    x = np.asarray(reference, dtype=float)[-_MAX_MMD_SAMPLE:]
    y = np.asarray(recent, dtype=float)[-_MAX_MMD_SAMPLE:]
    if x.ndim != 2 or y.ndim != 2 or len(x) < 12 or len(y) < 12 or x.shape[1] != y.shape[1]:
        return {"status": "INSUFFICIENT_EVIDENCE", "statistic": None, "threshold": None, "significance": None, "severity": "UNKNOWN", "sample_count_reference": int(len(x) if x.ndim else 0), "sample_count_recent": int(len(y) if y.ndim else 0), "shifted_features": []}
    observed, gamma = rbf_mmd2(x, y)
    pooled = np.vstack([x, y])
    n = len(x)
    rng = np.random.default_rng(int(seed) % (2**32 - 1))
    blocks = [np.arange(start, min(start + max(2, block_size), len(pooled))) for start in range(0, len(pooled), max(2, block_size))]
    null = []
    for _ in range(max(16, int(permutations))):
        order = rng.permutation(len(blocks))
        indices = np.concatenate([blocks[index] for index in order])
        permuted = pooled[indices]
        stat, _ = rbf_mmd2(permuted[:n], permuted[n:], gamma=gamma)
        null.append(stat)
    threshold = float(np.quantile(null, 0.95))
    pvalue = float((1 + sum(value >= observed for value in null)) / (len(null) + 1))
    ref_mean = np.nanmean(x, axis=0)
    rec_mean = np.nanmean(y, axis=0)
    pooled_std = np.nanstd(pooled, axis=0)
    effects = np.abs(rec_mean - ref_mean) / np.where(pooled_std < 1e-9, 1.0, pooled_std)
    names = list(feature_names or [f"feature_{index}" for index in range(x.shape[1])])
    shifted = sorted(({"feature": names[index], "standardized_mean_shift": float(effects[index])} for index in range(len(names))), key=lambda row: row["standardized_mean_shift"], reverse=True)[:6]
    significant = observed > threshold and pvalue <= 0.05
    severity = "HIGH" if significant and observed > 2.0 * max(threshold, 1e-12) else "MEDIUM" if significant else "LOW"
    return {"status": "VALID", "statistic": observed, "threshold": threshold, "significance": pvalue, "significant": significant, "severity": severity, "kernel": "RBF", "gamma": gamma, "block_size": block_size, "permutations": len(null), "sample_count_reference": int(len(x)), "sample_count_recent": int(len(y)), "shifted_features": shifted}


def build_market_feature_frame(h1: pd.DataFrame) -> pd.DataFrame:
    if h1.empty:
        return pd.DataFrame()
    result = pd.DataFrame({"time": h1["time"]})
    close = pd.to_numeric(h1["close"], errors="coerce")
    high = pd.to_numeric(h1["high"], errors="coerce")
    low = pd.to_numeric(h1["low"], errors="coerce")
    open_ = pd.to_numeric(h1["open"], errors="coerce")
    volume = pd.to_numeric(h1.get("volume", 0.0), errors="coerce").fillna(0.0)
    result["return"] = close.pct_change().fillna(0.0)
    result["range"] = ((high - low) / close.replace(0, np.nan)).fillna(0.0)
    result["pressure"] = ((close - open_) / (high - low).replace(0, np.nan)).fillna(0.0).clip(-2, 2)
    result["volume_change"] = volume.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(-10, 10)
    result["volatility"] = result["return"].rolling(24, min_periods=6).std().fillna(0.0)
    result["atr_proxy"] = (high - low).rolling(14, min_periods=4).mean().fillna(high - low)
    for column in ("adx", "plus_di", "minus_di", "periodicity_normalized_residual"):
        if column in h1:
            result[column] = pd.to_numeric(h1[column], errors="coerce").fillna(0.0)
    return result.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def build_mmd_drift(h1: pd.DataFrame, settled: pd.DataFrame, identity: Mapping[str, Any]) -> Dict[str, Any]:
    features = build_market_feature_frame(h1)
    columns = [column for column in ("return", "range", "pressure", "volume_change", "volatility", "atr_proxy", "adx", "plus_di", "minus_di") if column in features]
    seed = int(_stable_hash(identity)[:8], 16)
    comparisons: Dict[str, Any] = {}
    if len(features) >= 96:
        recent = features[columns].tail(48).to_numpy(dtype=float)
        reference = features[columns].iloc[:-48].tail(600).to_numpy(dtype=float)
        comparisons["recent_vs_25_day"] = mmd_block_test(reference, recent, seed=seed, feature_names=columns)
        current_session = str(identity.get("session") or "UNKNOWN")
        sessions = features["time"].map(_session)
        session_rows = features.loc[sessions == current_session, columns]
        if len(session_rows) >= 36:
            comparisons["current_session_vs_historical_session"] = mmd_block_test(session_rows.iloc[:-12].to_numpy(dtype=float), session_rows.tail(12).to_numpy(dtype=float), seed=seed + 1, feature_names=columns)
    if not settled.empty:
        residual_columns = [column for column in ("absolute_error_pips", "squared_error", "maximum_favorable_excursion", "maximum_adverse_excursion") if column in settled]
        if residual_columns:
            residuals = settled[residual_columns].apply(pd.to_numeric, errors="coerce").dropna()
            if len(residuals) >= 48:
                split = max(24, int(len(residuals) * 0.75))
                comparisons["recent_residual_vs_reference_residual"] = mmd_block_test(residuals.iloc[:split].to_numpy(dtype=float), residuals.iloc[split:].to_numpy(dtype=float), seed=seed + 2, feature_names=residual_columns)
    valid = [value for value in comparisons.values() if value.get("status") == "VALID"]
    severity_order = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
    severity = max((value.get("severity", "UNKNOWN") for value in valid), key=lambda label: severity_order.get(label, 0), default="UNKNOWN")
    significant = any(bool(value.get("significant")) for value in valid)
    return {"status": "VALID" if valid else "INSUFFICIENT_EVIDENCE", "severity": severity, "strong_feature_drift": significant and severity in {"MEDIUM", "HIGH"}, "comparisons": comparisons, "bounded_samples": True, "maximum_sample_per_side": _MAX_MMD_SAMPLE}


# ---------------------------------------------------------------------------
# E. BBSE label-shift correction
# ---------------------------------------------------------------------------


def _confusion_pred_given_true(predicted: Sequence[str], actual: Sequence[str], labels: Sequence[str]) -> np.ndarray:
    matrix = np.zeros((len(labels), len(labels)), dtype=float)
    lookup = {label: index for index, label in enumerate(labels)}
    for pred, truth in zip(predicted, actual):
        if pred in lookup and truth in lookup:
            matrix[lookup[pred], lookup[truth]] += 1.0
    for column in range(matrix.shape[1]):
        total = matrix[:, column].sum()
        if total > 0:
            matrix[:, column] /= total
    return matrix


def _prior(labels_values: Sequence[str], labels: Sequence[str]) -> np.ndarray:
    values = pd.Series(labels_values).value_counts(normalize=True)
    return np.array([float(values.get(label, 0.0)) for label in labels], dtype=float)


def bbse_label_shift(settled: pd.DataFrame, mmd: Mapping[str, Any]) -> Dict[str, Any]:
    labels = ("BUY", "SELL", "WAIT")
    if settled.empty or len(settled) < 90:
        return {"status": "INSUFFICIENT_EVIDENCE", "valid": False, "reason": "At least 90 chronological settled rows are required.", "direction": {}, "tp_sl": {"status": "UNAVAILABLE", "reason": "Insufficient predictor/outcome labels."}}
    if bool(mmd.get("strong_feature_drift")):
        return {"status": "REJECTED", "valid": False, "reason": "Strong feature drift contradicts the label-shift-only assumption.", "direction": {}, "tp_sl": {"status": "UNAVAILABLE", "reason": "Correction disabled while feature drift is strong."}}
    predicted = _predicted_direction_series(settled)
    actual = _actual_direction_series(settled)
    split = int(len(settled) * 0.70)
    reference_pred, reference_actual = predicted.iloc[:split], actual.iloc[:split]
    current_pred = predicted.iloc[split:]
    support = reference_actual.value_counts()
    if any(int(support.get(label, 0)) < 10 for label in labels):
        return {"status": "REJECTED", "valid": False, "reason": "Reference confusion matrix has fewer than 10 samples in at least one direction class.", "direction": {"class_support": support.to_dict()}, "tp_sl": {"status": "UNAVAILABLE", "reason": "Direction support failed."}}
    confusion = _confusion_pred_given_true(reference_pred, reference_actual, labels)
    condition = float(np.linalg.cond(confusion))
    rank = int(np.linalg.matrix_rank(confusion))
    if rank < len(labels) or not math.isfinite(condition) or condition > 50.0:
        return {"status": "REJECTED", "valid": False, "reason": "Confusion matrix is singular or ill-conditioned.", "direction": {"confusion_matrix": confusion.tolist(), "condition_number": condition, "rank": rank}, "tp_sl": {"status": "UNAVAILABLE", "reason": "Direction correction rejected."}}
    q_pred = _prior(current_pred, labels)
    estimated = np.linalg.solve(confusion, q_pred)
    estimated = np.clip(estimated, 0.0, None)
    estimated = estimated / max(estimated.sum(), 1e-12)
    original = _prior(reference_actual, labels)
    weights = estimated / np.maximum(original, 1e-9)
    direction = {
        "status": "VALID", "labels": list(labels), "confusion_matrix": confusion.tolist(),
        "condition_number": condition, "rank": rank,
        "original_priors": {label: float(original[index]) for index, label in enumerate(labels)},
        "current_predicted_priors": {label: float(q_pred[index]) for index, label in enumerate(labels)},
        "estimated_current_priors": {label: float(estimated[index]) for index, label in enumerate(labels)},
        "correction_weights": {label: float(weights[index]) for index, label in enumerate(labels)},
        "reference_sample_count": int(split), "current_sample_count": int(len(settled) - split),
    }
    touch_pred_col = _find_column(settled, ("predicted_touch_label", "predicted_tp_sl_label"))
    if touch_pred_col and {"tp_touched", "sl_touched"}.issubset(settled.columns):
        touch_actual = np.where(pd.to_numeric(settled["tp_touched"], errors="coerce").fillna(0) > 0, "TP_FIRST", np.where(pd.to_numeric(settled["sl_touched"], errors="coerce").fillna(0) > 0, "SL_FIRST", "NEITHER"))
        touch = {"status": "AVAILABLE_FOR_OFFLINE_EXTENSION", "observed_base_rates": pd.Series(touch_actual).value_counts(normalize=True).to_dict(), "note": "A full BBSE correction requires a validated pre-outcome touch-class predictor."}
    else:
        tp = _column_numeric(settled, ("tp_touched",)).fillna(0)
        sl = _column_numeric(settled, ("sl_touched",)).fillna(0)
        touch = {"status": "UNAVAILABLE", "reason": "No pre-outcome TP-first/SL-first predictor label exists in the settled schema.", "observed_base_rates": {"TP_FIRST": float(((tp > 0) & (sl <= 0)).mean()), "SL_FIRST": float(((sl > 0) & (tp <= 0)).mean()), "OTHER_OR_ORDER_UNKNOWN": float(((tp > 0) == (sl > 0)).mean())}}
    return {"status": "VALID", "valid": True, "reason": "Chronological BBSE direction correction passed support and conditioning checks.", "direction": direction, "tp_sl": touch, "assumption": "p(x|y) stable; correction is rejected under strong feature drift."}


# ---------------------------------------------------------------------------
# F. Double / Debiased Machine Learning (offline bounded maintenance only)
# ---------------------------------------------------------------------------


def chronological_purged_splits(n_rows: int, *, n_splits: int = 3, purge: int = 6, embargo: int = 6, min_train: int = 40) -> Sequence[Tuple[np.ndarray, np.ndarray]]:
    if n_rows < min_train + 20:
        return []
    boundaries = np.linspace(min_train, n_rows, n_splits + 1, dtype=int)
    splits = []
    for index in range(n_splits):
        test_start = int(boundaries[index])
        test_end = int(boundaries[index + 1])
        train_end = max(0, test_start - max(purge, embargo))
        train = np.arange(0, train_end, dtype=int)
        test = np.arange(test_start, test_end, dtype=int)
        if len(train) >= min_train and len(test) >= 8:
            splits.append((train, test))
    return splits


def _ridge_fit(x: np.ndarray, y: np.ndarray, penalty: float = 1.0) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    design = np.column_stack([np.ones(len(x)), x])
    identity = np.eye(design.shape[1])
    identity[0, 0] = 0.0
    return np.linalg.pinv(design.T @ design + penalty * identity) @ design.T @ y


def _ridge_predict(x: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(x)), np.asarray(x, dtype=float)]) @ coefficients


def double_ml_partial_linear(
    outcome: Sequence[float], treatment: Sequence[float], confounders: np.ndarray,
    *, times: Optional[Sequence[Any]] = None, purge: int = 6, embargo: int = 6, n_splits: int = 3,
) -> Dict[str, Any]:
    y = np.asarray(outcome, dtype=float)
    d = np.asarray(treatment, dtype=float)
    x = np.asarray(confounders, dtype=float)
    valid = np.isfinite(y) & np.isfinite(d) & np.all(np.isfinite(x), axis=1)
    y, d, x = y[valid], d[valid], x[valid]
    if len(y) < 80 or np.unique(d).size < 2:
        return {"status": "INSUFFICIENT_EVIDENCE", "effect": None, "standard_error": None, "confidence_interval": [None, None], "sample_count": int(len(y)), "identification_warnings": ["Need at least 80 valid rows and treatment variation."]}
    splits = chronological_purged_splits(len(y), n_splits=n_splits, purge=purge, embargo=embargo)
    y_residuals: list[np.ndarray] = []
    d_residuals: list[np.ndarray] = []
    for train, test in splits:
        y_coef = _ridge_fit(x[train], y[train], penalty=2.0)
        d_coef = _ridge_fit(x[train], d[train], penalty=2.0)
        g = _ridge_predict(x[test], y_coef)
        m = np.clip(_ridge_predict(x[test], d_coef), 0.01, 0.99)
        y_residuals.append(y[test] - g)
        d_residuals.append(d[test] - m)
    if not y_residuals:
        return {"status": "INSUFFICIENT_EVIDENCE", "effect": None, "standard_error": None, "confidence_interval": [None, None], "sample_count": int(len(y)), "identification_warnings": ["Chronological purge/embargo left no valid cross-fitting fold."]}
    yr = np.concatenate(y_residuals)
    dr = np.concatenate(d_residuals)
    denominator = float(np.sum(dr * dr))
    if denominator < 1e-10:
        return {"status": "UNIDENTIFIED", "effect": None, "standard_error": None, "confidence_interval": [None, None], "sample_count": int(len(yr)), "identification_warnings": ["Residualized treatment has near-zero variation."]}
    effect = float(np.sum(dr * yr) / denominator)
    influence = dr * (yr - effect * dr)
    moment = float(np.mean(dr * dr))
    standard_error = float(math.sqrt(max(0.0, np.mean(influence * influence))) / max(moment, 1e-12) / math.sqrt(len(yr)))
    ci = [effect - 1.96 * standard_error, effect + 1.96 * standard_error]
    warnings = ["Observational identification depends on no unmeasured confounding and correct event timing."]
    if np.mean(d) < 0.05 or np.mean(d) > 0.95:
        warnings.append("Treatment overlap is weak.")
    return {"status": "VALID", "effect": effect, "standard_error": standard_error, "confidence_interval": ci, "sample_count": int(len(yr)), "fold_count": int(len(splits)), "purge_hours": purge, "embargo_hours": embargo, "identification_warnings": warnings}


def build_dml_event_effects(h1: pd.DataFrame, *, event_indicator: Optional[Sequence[float]] = None, maintenance: bool = False) -> Dict[str, Any]:
    if not maintenance:
        return {"status": "DEFERRED_OFFLINE", "ran_during_navigation": False, "effects": {}, "reason": "DML is restricted to explicit bounded maintenance/offline execution."}
    if h1.empty or len(h1) < 140 or event_indicator is None:
        return {"status": "INSUFFICIENT_EVIDENCE", "ran_during_navigation": False, "effects": {}, "reason": "Completed H1 history and an aligned historical event indicator are required."}
    features = build_market_feature_frame(h1)
    treatment = np.asarray(event_indicator, dtype=float)
    if len(treatment) != len(h1):
        return {"status": "INVALID_INPUT", "ran_during_navigation": False, "effects": {}, "reason": "Event indicator length does not match completed H1 rows."}
    confounder_columns = [column for column in ("return", "range", "pressure", "volume_change", "volatility", "atr_proxy", "adx", "plus_di", "minus_di") if column in features]
    x_all = features[confounder_columns].to_numpy(dtype=float)
    close = h1["close"].to_numpy(dtype=float)
    high = h1["high"].to_numpy(dtype=float)
    low = h1["low"].to_numpy(dtype=float)
    effects: Dict[str, Any] = {}
    for horizon in (1, 3, 6):
        n = len(close) - horizon
        if n <= 0:
            continue
        future_close = close[horizon:]
        origin_close = close[:n]
        returns = future_close / np.where(origin_close == 0, np.nan, origin_close) - 1.0
        mfe = np.empty(n, dtype=float)
        mae = np.empty(n, dtype=float)
        realized = np.empty(n, dtype=float)
        for index in range(n):
            forward_high = high[index + 1:index + horizon + 1]
            forward_low = low[index + 1:index + horizon + 1]
            forward_close = close[index:index + horizon + 1]
            mfe[index] = np.max(forward_high - origin_close[index])
            mae[index] = np.min(forward_low - origin_close[index])
            path_returns = np.diff(np.log(np.maximum(forward_close, 1e-12)))
            realized[index] = float(np.std(path_returns)) if path_returns.size else 0.0
        for name, outcome in (("return", returns), ("mfe", mfe), ("mae", mae), ("realized_volatility", realized)):
            effects[f"h{horizon}_{name}"] = double_ml_partial_linear(outcome, treatment[:n], x_all[:n], purge=horizon, embargo=horizon)
    return {"status": "VALID" if any(value.get("status") == "VALID" for value in effects.values()) else "INSUFFICIENT_EVIDENCE", "ran_during_navigation": False, "effects": effects, "pre_treatment_confounders": confounder_columns, "outcome_policy": "Future values are used only as settled offline outcomes, never as predictor inputs."}


# ---------------------------------------------------------------------------
# G. Lightweight IRM diagnostics
# ---------------------------------------------------------------------------


def _diagnostic_matrix(settled: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    features = pd.DataFrame(index=settled.index)
    aliases = {
        "raw_confidence": ("raw_confidence",), "calibrated_confidence": ("calibrated_confidence",),
        "priority": ("priority",), "knn_score": ("knn_score",), "greedy_rank": ("greedy_rank",),
        "model_agreement": ("model_agreement",), "transition_risk": ("regime_transition_risk",),
        "expected_value": ("expected_value_after_costs",), "interval_width": ("upper_band",),
    }
    for name, candidates in aliases.items():
        series = _column_numeric(settled, candidates)
        if name == "interval_width" and "lower_band" in settled:
            series = series - pd.to_numeric(settled["lower_band"], errors="coerce")
        features[name] = series
    features = features.dropna(axis=1, how="all")
    features = features.fillna(features.median(numeric_only=True)).fillna(0.0)
    outcome = _column_numeric(settled, ("direction_correct",)).fillna(0.0).clip(0, 1)
    groups = _settled_group_columns(settled)
    groups["chronological_period"] = pd.qcut(np.arange(len(settled)), q=min(4, max(1, len(settled) // 30)), labels=False, duplicates="drop").astype(str)
    return features, outcome, groups


def irm_diagnostics(settled: pd.DataFrame, *, min_environment_support: int = 20) -> Dict[str, Any]:
    if settled.empty or len(settled) < 80:
        return {"status": "INSUFFICIENT_EVIDENCE", "invariance_score": None, "features": {}, "environment_loss_dispersion": None, "environment_count": 0}
    features, outcome, groups = _diagnostic_matrix(settled)
    if features.empty:
        return {"status": "INSUFFICIENT_EVIDENCE", "invariance_score": None, "features": {}, "environment_loss_dispersion": None, "environment_count": 0}
    mean = features.mean()
    std = features.std().replace(0, 1.0)
    x = ((features - mean) / std).to_numpy(dtype=float)
    y = outcome.to_numpy(dtype=float)
    coefficients = []
    losses = []
    environment_names = []
    environment_specs = (("session", groups["session"]), ("h1_regime", groups["h1_regime"]), ("volatility", groups["volatility_state"]), ("event", groups["event_risk"]), ("period", groups["chronological_period"]))
    for family, labels in environment_specs:
        for label in pd.Series(labels).dropna().unique():
            mask = pd.Series(labels, index=settled.index).astype(str) == str(label)
            if int(mask.sum()) < min_environment_support:
                continue
            coef = _ridge_fit(x[mask.to_numpy()], y[mask.to_numpy()], penalty=3.0)[1:]
            prediction = np.clip(x[mask.to_numpy()] @ coef + float(y[mask.to_numpy()].mean()), 0, 1)
            coefficients.append(coef)
            losses.append(float(np.mean((prediction - y[mask.to_numpy()]) ** 2)))
            environment_names.append(f"{family}={label}")
    if len(coefficients) < 3:
        return {"status": "INSUFFICIENT_EVIDENCE", "invariance_score": None, "features": {}, "environment_loss_dispersion": None, "environment_count": len(coefficients)}
    matrix = np.vstack(coefficients)
    feature_results = {}
    scores = []
    for index, name in enumerate(features.columns):
        values = matrix[:, index]
        nonzero = values[np.abs(values) > 1e-8]
        sign_stability = float(max(np.mean(nonzero >= 0), np.mean(nonzero <= 0))) if nonzero.size else 0.0
        coefficient_stability = float(1.0 / (1.0 + np.std(values) / (abs(np.mean(values)) + 1e-6)))
        ranks = np.argsort(np.argsort(-np.abs(matrix), axis=1), axis=1)[:, index]
        rank_stability = float(1.0 / (1.0 + np.std(ranks)))
        score = float(np.mean([sign_stability, coefficient_stability, rank_stability]))
        status = "STABLE" if score >= 0.72 and sign_stability >= 0.75 else "ENVIRONMENT_SPECIFIC" if score >= 0.40 else "UNSUPPORTED"
        feature_results[name] = {"status": status, "sign_stability": sign_stability, "coefficient_stability": coefficient_stability, "rank_stability": rank_stability, "invariance_score": score}
        scores.append(score)
    loss_dispersion = float(np.std(losses) / (np.mean(losses) + 1e-9))
    overall = float(np.clip(np.mean(scores) * (1.0 / (1.0 + loss_dispersion)), 0, 1))
    return {"status": "VALID", "invariance_score": overall, "features": feature_results, "environment_loss_dispersion": loss_dispersion, "environment_count": len(coefficients), "environments": environment_names[:40], "implementation": "lightweight diagnostic; no neural IRM training"}


# ---------------------------------------------------------------------------
# H. Group DRO validation
# ---------------------------------------------------------------------------


def group_dro_validation(settled: pd.DataFrame, *, min_group_support: int = 15) -> Dict[str, Any]:
    if settled.empty or len(settled) < 80:
        return {"status": "INSUFFICIENT_EVIDENCE", "candidates": {}, "selected_candidate": None, "weights_changed": False}
    actual_direction = _actual_direction_series(settled)
    predicted_direction = _predicted_direction_series(settled)
    groups = _settled_group_columns(settled)
    group_keys = (
        groups["session"].astype(str) + "|" + groups["h1_regime"].astype(str) + "|" +
        groups["volatility_state"].astype(str) + "|" + groups["direction"].astype(str) + "|h" +
        groups["horizon"].astype(str) + "|c" + groups["conflict"].astype(str) + "|e" + groups["event_risk"].astype(str)
    )
    candidate_losses: Dict[str, pd.Series] = {}
    calibrated = pd.Series(index=settled.index, dtype=float)
    raw = pd.Series(index=settled.index, dtype=float)
    for label in ("BUY", "SELL", "WAIT"):
        mask = actual_direction == label
        calibrated.loc[mask] = 1.0 - _probability_for_direction(settled.loc[mask], label, calibrated=True)
        raw.loc[mask] = 1.0 - _probability_for_direction(settled.loc[mask], label, calibrated=False)
    candidate_losses["calibrated_probability"] = calibrated.fillna(1.0).clip(0, 1) ** 2
    candidate_losses["raw_probability"] = raw.fillna(1.0).clip(0, 1) ** 2
    candidate_losses["point_direction"] = (predicted_direction != actual_direction).astype(float)
    results = {}
    for name, loss in candidate_losses.items():
        per_group = []
        for key, indices in pd.Series(group_keys).groupby(group_keys).groups.items():
            if len(indices) < min_group_support:
                continue
            value = float(loss.loc[indices].mean())
            per_group.append((str(key), value, int(len(indices))))
        average = float(loss.mean())
        if not per_group:
            worst_name, worst_loss, worst_n = "UNAVAILABLE", average, int(len(loss))
        else:
            worst_name, worst_loss, worst_n = max(per_group, key=lambda item: item[1])
        regularization_penalty = min(0.15, 1.0 / math.sqrt(max(1, worst_n)))
        robust_score = float(np.clip(1.0 - (0.40 * average + 0.60 * worst_loss + regularization_penalty), 0, 1))
        results[name] = {"average_loss": average, "worst_group_loss": worst_loss, "worst_group": worst_name, "worst_group_support": worst_n, "robust_selection_score": robust_score, "regularization_penalty": regularization_penalty}
    selected = max(results, key=lambda name: results[name]["robust_selection_score"]) if results else None
    return {"status": "VALID", "candidates": results, "selected_candidate": selected, "weights_changed": False, "selection_policy": "validation only; existing model weights require separate settled walk-forward superiority", "minimum_group_support": min_group_support}


# ---------------------------------------------------------------------------
# I. Bounded Random Cut Forest approximation for stream anomaly scores
# ---------------------------------------------------------------------------


def _average_path_length(n: int) -> float:
    if n <= 1:
        return 1.0
    harmonic = math.log(n - 1) + 0.5772156649 if n > 2 else 1.0
    return 2.0 * harmonic - 2.0 * (n - 1) / n


def _random_cut_depth(sample: np.ndarray, point: np.ndarray, rng: np.random.Generator, depth: int = 0, max_depth: int = 18) -> int:
    if len(sample) <= 1 or depth >= max_depth:
        return depth
    minimum = np.min(sample, axis=0)
    maximum = np.max(sample, axis=0)
    ranges = maximum - minimum
    total = float(np.sum(ranges))
    if total <= 1e-12:
        return depth
    dimension = int(rng.choice(sample.shape[1], p=ranges / total))
    cut = float(rng.uniform(minimum[dimension], maximum[dimension]))
    left = sample[:, dimension] <= cut
    point_left = point[dimension] <= cut
    child = sample[left] if point_left else sample[~left]
    if len(child) == 0 or len(child) == len(sample):
        return depth + 1
    return _random_cut_depth(child, point, rng, depth + 1, max_depth)


def random_cut_forest_score(history: np.ndarray, point: np.ndarray, *, seed: int = 0, trees: int = 24, sample_size: int = 128) -> float:
    data = np.asarray(history, dtype=float)
    point = np.asarray(point, dtype=float)
    if data.ndim != 2 or len(data) < 16 or point.ndim != 1 or data.shape[1] != len(point):
        return 0.0
    data, standardized_point = _standardize_pair(data[-sample_size:], point.reshape(1, -1))
    point = standardized_point[0]
    rng = np.random.default_rng(int(seed) % (2**32 - 1))
    depths = []
    for _ in range(max(8, trees)):
        size = min(len(data), sample_size)
        subset = data[rng.choice(len(data), size=size, replace=False)]
        depths.append(_random_cut_depth(subset, point, rng))
    mean_depth = float(np.mean(depths))
    score = 2.0 ** (-mean_depth / max(_average_path_length(min(len(data), sample_size)), 1e-9))
    return float(np.clip(score, 0, 1))


def _market_system_vectors(h1: pd.DataFrame, settled: pd.DataFrame, canonical: Mapping[str, Any]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, Sequence[str], Sequence[str]]:
    features = build_market_feature_frame(h1)
    market_names = [column for column in ("return", "range", "pressure", "volume_change", "volatility", "atr_proxy", "adx", "plus_di", "minus_di") if column in features]
    market_history = features[market_names].tail(256).to_numpy(dtype=float) if market_names else np.empty((0, 0))
    market_point = market_history[-1] if len(market_history) else np.array([])
    system_names = ["absolute_error_pips", "squared_error", "model_agreement", "raw_calibration_gap", "missingness", "api_timing", "sync_health"]
    if settled.empty:
        system_history = np.empty((0, len(system_names)))
        system_point = np.zeros(len(system_names), dtype=float)
    else:
        absolute_error = _column_numeric(settled, ("absolute_error_pips",)).fillna(0.0)
        squared_error = _column_numeric(settled, ("squared_error",)).fillna(0.0)
        agreement = _column_numeric(settled, ("model_agreement",)).fillna(0.0)
        raw_p = _probability_for_direction(settled, "BUY", calibrated=False).fillna(0.0)
        cal_p = _probability_for_direction(settled, "BUY", calibrated=True).fillna(raw_p)
        gap = (cal_p - raw_p).abs()
        missingness = settled.isna().mean(axis=1)
        api_timing = pd.Series(0.0, index=settled.index)
        sync_health = pd.Series(0.0, index=settled.index)
        system_history = np.column_stack([absolute_error, squared_error, agreement, gap, missingness, api_timing, sync_health])[-256:]
        final = _mapping(canonical.get("final_decision"))
        system_point = np.array([
            float(absolute_error.tail(1).iloc[0]) if len(absolute_error) else 0.0,
            float(squared_error.tail(1).iloc[0]) if len(squared_error) else 0.0,
            _finite(_mapping(canonical.get("priority")).get("model_agreement"), 0.0) or 0.0,
            0.0,
            0.0,
            _finite(_mapping(canonical.get("metadata")).get("api_timing_seconds"), 0.0) or 0.0,
            1.0 if final.get("data_quality_warning") not in (None, "PASS", "PASS_WITH_WARNING") else 0.0,
        ], dtype=float)
    return market_history, market_point, system_history, system_point, market_names, system_names


def build_rrcf_anomaly(h1: pd.DataFrame, settled: pd.DataFrame, canonical: Mapping[str, Any], identity: Mapping[str, Any]) -> Dict[str, Any]:
    market_history, market_point, system_history, system_point, market_names, system_names = _market_system_vectors(h1, settled, canonical)
    seed = int(_stable_hash(identity)[:8], 16)
    market_score = random_cut_forest_score(market_history[:-1], market_point, seed=seed) if len(market_history) >= 17 else 0.0
    system_score = random_cut_forest_score(system_history[:-1], system_point, seed=seed + 1) if len(system_history) >= 17 else 0.0
    market_cap = 100.0 if market_score < 0.60 else 85.0 if market_score < 0.72 else 70.0 if market_score < 0.82 else 50.0
    system_cap = 100.0 if system_score < 0.60 else 80.0 if system_score < 0.72 else 60.0 if system_score < 0.82 else 40.0
    def contributions(history: np.ndarray, point: np.ndarray, names: Sequence[str]) -> list[dict[str, Any]]:
        if len(history) < 8 or point.size == 0:
            return []
        median = np.median(history, axis=0)
        scale = np.median(np.abs(history - median), axis=0) * 1.4826
        scale = np.where(scale < 1e-9, np.std(history, axis=0), scale)
        scale = np.where(scale < 1e-9, 1.0, scale)
        values = np.abs(point - median) / scale
        return sorted(({"feature": names[index], "robust_deviation": float(values[index])} for index in range(len(names))), key=lambda row: row["robust_deviation"], reverse=True)[:6]
    return {
        "status": "VALID" if len(market_history) >= 17 or len(system_history) >= 17 else "INSUFFICIENT_EVIDENCE",
        "market_anomaly_score": market_score, "system_anomaly_score": system_score,
        "market_trust_cap_pct": market_cap, "system_trust_cap_pct": system_cap,
        "combined_trust_cap_pct": min(market_cap, system_cap),
        "market_contributions": contributions(market_history[:-1], market_point, market_names),
        "system_contributions": contributions(system_history[:-1], system_point, system_names),
        "implementation": "bounded random-cut-tree forest approximation; exact dynamic RRCF codisp is not claimed",
        "update_policy": "one update per new completed canonical H1 generation",
    }


# ---------------------------------------------------------------------------
# J. Truncated lead-lag path signatures
# ---------------------------------------------------------------------------


def lead_lag_path(path: np.ndarray) -> np.ndarray:
    values = np.asarray(path, dtype=float)
    if values.ndim != 2 or len(values) == 0:
        return np.empty((0, 0))
    result = np.empty((2 * len(values) - 1, 2 * values.shape[1]), dtype=float)
    result[0] = np.concatenate([values[0], values[0]])
    cursor = 1
    for index in range(1, len(values)):
        result[cursor] = np.concatenate([values[index], values[index - 1]])
        result[cursor + 1] = np.concatenate([values[index], values[index]])
        cursor += 2
    return result


def _signature_compose(levels_a: Sequence[np.ndarray], levels_b: Sequence[np.ndarray], dimension: int, level: int) -> list[np.ndarray]:
    result = [np.array([1.0])]
    for order in range(1, level + 1):
        total = np.zeros(dimension ** order, dtype=float)
        for split in range(order + 1):
            left = levels_a[split]
            right = levels_b[order - split]
            total += np.kron(left, right)
        result.append(total)
    return result


def truncated_signature(path: np.ndarray, *, level: int = 2, max_dimensions: int = 260) -> Dict[str, Any]:
    values = np.asarray(path, dtype=float)
    if values.ndim != 2 or len(values) < 2 or level not in {2, 3}:
        return {"status": "INVALID_INPUT", "features": [], "dimension": 0, "level": level}
    dimension = values.shape[1]
    output_dimension = sum(dimension ** order for order in range(1, level + 1))
    if output_dimension > max_dimensions:
        return {"status": "DIMENSION_BOUND", "features": [], "dimension": output_dimension, "level": level, "maximum_dimension": max_dimensions}
    signature = [np.array([1.0])] + [np.zeros(dimension ** order, dtype=float) for order in range(1, level + 1)]
    for delta in np.diff(values, axis=0):
        segment = [np.array([1.0])]
        for order in range(1, level + 1):
            tensor = delta.copy()
            for _ in range(order - 1):
                tensor = np.kron(tensor, delta)
            segment.append(tensor / math.factorial(order))
        signature = _signature_compose(signature, segment, dimension, level)
    flattened = np.concatenate(signature[1:])
    return {"status": "VALID", "features": flattened.tolist(), "dimension": int(len(flattened)), "level": level, "path_dimension": dimension, "composition": "Chen identity incremental segment composition"}


def build_path_signature_features(h1: pd.DataFrame) -> Dict[str, Any]:
    features = build_market_feature_frame(h1)
    required = ["return", "range", "pressure", "volume_change", "volatility"]
    if features.empty or len(features) < 16:
        return {"status": "INSUFFICIENT_EVIDENCE", "features": [], "dimension": 0, "usage": []}
    window = features.tail(32).copy(deep=False)
    time_feature = np.linspace(0.0, 1.0, len(window))
    matrix = np.column_stack([window[required].to_numpy(dtype=float), time_feature])
    median = np.median(matrix, axis=0)
    scale = np.std(matrix, axis=0)
    scale = np.where(scale < 1e-9, 1.0, scale)
    normalized = (matrix - median) / scale
    path = lead_lag_path(normalized)
    signature = truncated_signature(path, level=2, max_dimensions=260)
    signature.update({"source_features": ["return", "range", "pressure", "volume", "volatility", "time"], "lead_lag": True, "usage": ["Similar-Day support", "KNN support", "regime-transition confirmation", "anomaly confirmation"], "direction_engine": False})
    return signature


# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------


class AdvancedReliabilityStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        configured = os.environ.get("ADX_LEDGER_DB_PATH")
        self.db_path = Path(db_path or configured or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=20, check_same_thread=False)
        conn.row_factory = sqlite3.Row
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
        statements = (
            """
            CREATE TABLE IF NOT EXISTS advanced_reliability_shift_snapshots_v2 (
                calculation_id TEXT PRIMARY KEY,
                calculation_generation INTEGER NOT NULL,
                latest_completed_h1_time TEXT,
                data_hash TEXT NOT NULL,
                version TEXT NOT NULL,
                publication_status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                published_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS advanced_reliability_shift_vectors_v2 (
                calculation_id TEXT NOT NULL,
                calculation_generation INTEGER NOT NULL,
                stream_type TEXT NOT NULL,
                vector_time TEXT,
                score REAL,
                vector_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(calculation_id, stream_type)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_advanced_shift_generation_v2 ON advanced_reliability_shift_snapshots_v2(calculation_generation)",
            "CREATE INDEX IF NOT EXISTS idx_advanced_shift_vector_time_v2 ON advanced_reliability_shift_vectors_v2(stream_type, vector_time)",
        )
        with _LOCK, self.connection() as conn:
            for statement in statements:
                conn.execute(statement)

    def stage(self, result: Mapping[str, Any], vectors: Optional[Mapping[str, Sequence[float]]] = None) -> Dict[str, Any]:
        identity = _mapping(result.get("identity"))
        calculation_id = str(identity.get("calculation_id") or "")
        generation = numeric_generation(identity.get("generation") or identity.get("generation_id"), default=1)
        if not calculation_id:
            return {"ok": False, "status": "SKIPPED", "reason": "Missing calculation id"}
        compact = _json_safe(result)
        now = _utc_now()
        with _LOCK, self.connection() as conn:
            current = conn.execute("SELECT MAX(calculation_generation) AS generation FROM advanced_reliability_shift_snapshots_v2 WHERE publication_status='PUBLISHED'").fetchone()
            latest_generation = int(current["generation"] or 0) if current else 0
            if generation < latest_generation:
                return {"ok": False, "status": "STALE_REJECTED", "latest_generation": latest_generation}
            conn.execute(
                """
                INSERT OR REPLACE INTO advanced_reliability_shift_snapshots_v2(
                    calculation_id,calculation_generation,latest_completed_h1_time,data_hash,version,
                    publication_status,payload_json,created_at,published_at
                ) VALUES (?,?,?,?,?,'STAGED',?,?,NULL)
                """,
                (calculation_id, generation, str(identity.get("latest_completed_h1_time") or ""), str(identity.get("data_hash") or ""), VERSION, json.dumps(compact, ensure_ascii=False, default=str), now),
            )
            for stream_type, vector in (vectors or {}).items():
                vector_list = [float(value) for value in list(vector)[:260] if _finite(value, None) is not None]
                score = _finite(_mapping(result.get("rrcf")).get(f"{stream_type}_anomaly_score"), None)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO advanced_reliability_shift_vectors_v2(
                        calculation_id,calculation_generation,stream_type,vector_time,score,vector_json,created_at
                    ) VALUES (?,?,?,?,?,?,?)
                    """,
                    (calculation_id, generation, str(stream_type), str(identity.get("latest_completed_h1_time") or ""), score, json.dumps(vector_list), now),
                )
            # Bound persisted vectors without scanning application history.
            conn.execute(
                """
                DELETE FROM advanced_reliability_shift_vectors_v2
                WHERE rowid NOT IN (
                    SELECT rowid FROM advanced_reliability_shift_vectors_v2
                    ORDER BY calculation_generation DESC LIMIT 1024
                )
                """
            )
        return {"ok": True, "status": "STAGED", "calculation_id": calculation_id, "generation": generation}

    def mark_published(self, calculation_id: str) -> Dict[str, Any]:
        with _LOCK, self.connection() as conn:
            cursor = conn.execute("UPDATE advanced_reliability_shift_snapshots_v2 SET publication_status='PUBLISHED',published_at=? WHERE calculation_id=? AND publication_status='STAGED'", (_utc_now(), str(calculation_id)))
        return {"ok": cursor.rowcount >= 0, "status": "PUBLISHED" if cursor.rowcount else "NOT_FOUND", "calculation_id": str(calculation_id)}

    def latest(self) -> Dict[str, Any]:
        with _LOCK, self.connection() as conn:
            row = conn.execute("SELECT payload_json FROM advanced_reliability_shift_snapshots_v2 WHERE publication_status='PUBLISHED' ORDER BY calculation_generation DESC LIMIT 1").fetchone()
        if not row:
            return {}
        try:
            return json.loads(row["payload_json"])
        except Exception:
            return {}


# ---------------------------------------------------------------------------
# Integration and policy
# ---------------------------------------------------------------------------


def _renormalize_probabilities(probabilities: Mapping[str, float], direction: str, new_value: float) -> Dict[str, float]:
    result = {label: float(probabilities.get(label, 0.0)) for label in ("BUY", "SELL", "WAIT")}
    new_value = float(np.clip(new_value, 0, 1))
    others = [label for label in result if label != direction]
    other_total = sum(result[label] for label in others)
    result[direction] = new_value
    remaining = 1.0 - new_value
    if other_total <= 1e-12:
        for label in others:
            result[label] = remaining / len(others)
    else:
        for label in others:
            result[label] = remaining * result[label] / other_total
    return result


def _apply_probability_updates(canonical: MutableMapping[str, Any], probabilities: Mapping[str, float], source: str) -> None:
    """Copy-on-write update of only the selected forecast row.

    The canonical input can contain large record lists, so a full deepcopy would
    be wasteful.  Copying the three nested mapping levels prevents mutation of
    the protected pre-research canonical object without duplicating large data.
    """
    horizon = _selected_horizon(canonical)
    forecasts = dict(_mapping(canonical.get("forecasts")))
    horizons = dict(_mapping(forecasts.get("horizons")))
    key = f"{horizon}h"
    row = dict(_mapping(horizons.get(key)))
    if not row:
        return
    row["buy_probability_calibrated"] = float(probabilities["BUY"])
    row["sell_probability_calibrated"] = float(probabilities["SELL"])
    row["wait_probability_calibrated"] = float(probabilities["WAIT"])
    row["advanced_calibration_source"] = source
    horizons[key] = row
    forecasts["horizons"] = horizons
    canonical["forecasts"] = forecasts


def apply_advanced_reliability_policy(canonical: Mapping[str, Any], result: Mapping[str, Any]) -> Dict[str, Any]:
    # Shallow top-level copy plus targeted copy-on-write mappings avoids both
    # input mutation and a duplicate of large canonical histories/data frames.
    payload = dict(canonical)
    payload["metadata"] = dict(_mapping(canonical.get("metadata")))
    final = dict(_mapping(canonical.get("final_decision")))
    priority = dict(_mapping(canonical.get("priority")))
    direction = _direction(final.get("directional_market_view") or payload.get("full_metric_direction"))
    existing_decision = _direction(final.get("final_decision"))
    probabilities = dict(_mapping(result.get("adjusted_probabilities")))
    if probabilities and abs(sum(float(value) for value in probabilities.values()) - 1.0) <= 1e-6:
        _apply_probability_updates(payload, probabilities, str(result.get("probability_adjustment_source") or "advanced_reliability_shift"))
    trust_cap = _clip(result.get("trust_cap_pct"), 0, 100, 100)
    existing_priority = _finite(priority.get("score"), None)
    if existing_priority is not None:
        priority["protected_score"] = existing_priority
        priority["research_adjusted_score"] = min(existing_priority, trust_cap)
        priority["research_adjustment_does_not_change_scale"] = True
        payload["priority"] = priority
    final["research_trust_cap_pct"] = trust_cap
    final["research_adjusted_confidence"] = min(_prob(final.get("calibrated_confidence"), 1.0) or 1.0, trust_cap / 100.0)
    warnings = list(final.get("supporting_reasons") or [])
    blockers = list(final.get("blocking_reasons") or [])
    mmd = _mapping(result.get("mmd"))
    rrcf = _mapping(result.get("rrcf"))
    if mmd.get("severity") in {"MEDIUM", "HIGH"}:
        warnings.append(f"Advanced drift warning: MMD severity {mmd.get('severity')}")
    if max(_finite(rrcf.get("market_anomaly_score"), 0.0) or 0.0, _finite(rrcf.get("system_anomaly_score"), 0.0) or 0.0) >= 0.72:
        warnings.append("Advanced anomaly warning: bounded random-cut forest score exceeded the conservative watch threshold")
    crc = _mapping(result.get("conformal_risk_control"))
    current_probability = _prob(probabilities.get(direction), None) if probabilities else _prob(final.get("calibrated_confidence"), None)
    downgrade_reasons = []
    if existing_decision in {"BUY", "SELL"} and crc.get("validity_status") in {"VALID", "CONSERVATIVE_BLOCK"}:
        threshold = _prob(crc.get("threshold"), None)
        upper = _prob(crc.get("risk_upper_bound"), None)
        target = _prob(crc.get("target_risk"), None)
        if crc.get("status") == "RISK_NOT_CONTROLLED":
            downgrade_reasons.append(f"CRC risk upper bound {upper!s} did not meet target {target!s}")
        if threshold is not None and current_probability is not None and current_probability + 1e-12 < threshold:
            downgrade_reasons.append(f"Adjusted {direction} probability {current_probability:.3f} is below CRC threshold {threshold:.3f}")
    if downgrade_reasons:
        final["final_decision"] = "WAIT"
        final["tradeability_decision"] = "WAIT"
        final["less_risky_decision"] = "WAIT"
        final["research_downgraded_from"] = existing_decision
        blockers.extend(downgrade_reasons)
        final["main_reason"] = downgrade_reasons[0]
    final["supporting_reasons"] = list(dict.fromkeys(map(str, warnings)))
    final["blocking_reasons"] = list(dict.fromkeys(map(str, blockers)))
    final["advanced_reliability_policy"] = {
        "direction_reversal_allowed": False,
        "direction_before": direction,
        "direction_after": _direction(final.get("directional_market_view") or direction),
        "decision_before": existing_decision,
        "decision_after": _direction(final.get("final_decision")),
        "downgrade_reasons": downgrade_reasons,
    }
    payload["final_decision"] = final
    payload["advanced_reliability_shift"] = _json_safe(result)
    payload.setdefault("metadata", {})["advanced_reliability_shift_version"] = VERSION
    payload["metadata"]["advanced_reliability_direction_policy"] = "confirm/reduce/warn/WAIT-only; never reverse BUY/SELL"
    return payload


def build_advanced_reliability_transaction(
    canonical: Mapping[str, Any],
    *,
    completed_h1: pd.DataFrame,
    settled_predictions: pd.DataFrame,
    store: Optional[AdvancedReliabilityStore] = None,
    previous: Optional[Mapping[str, Any]] = None,
    persist_stage: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Compute, apply, and stage one hidden versioned research transaction."""
    started = time.perf_counter()
    latest = canonical.get("latest_completed_candle_time")
    h1 = normalize_completed_h1(completed_h1, latest)
    settled = normalize_settled_predictions(settled_predictions, latest)
    identity = _current_identity(canonical, h1)
    base_probabilities = _current_probabilities(canonical)

    mmd = build_mmd_drift(h1, settled, identity)
    bbse = bbse_label_shift(settled, mmd)
    direction = str(identity.get("direction") or "WAIT")
    probabilities = dict(base_probabilities)
    probability_sources = []
    if bbse.get("valid"):
        weights = _mapping(_mapping(bbse.get("direction")).get("correction_weights"))
        adjusted = {label: probabilities[label] * _clip(weights.get(label), 0.25, 4.0, 1.0) for label in probabilities}
        total = sum(adjusted.values()) or 1.0
        probabilities = {label: value / total for label, value in adjusted.items()}
        probability_sources.append("BBSE")
    multicalibration = multicalibrate_probability(settled, identity, probabilities.get(direction, 0.0))
    if multicalibration.get("status") in {"VALID", "VALID_GLOBAL_FALLBACK"}:
        probabilities = _renormalize_probabilities(probabilities, direction, float(multicalibration["calibrated_probability"]))
        probability_sources.append("MULTICALIBRATION")
    crc = conformal_risk_control(settled, identity)
    revin = build_revin_evidence(h1, settled, canonical)
    irm = irm_diagnostics(settled)
    group_dro = group_dro_validation(settled)
    rrcf = build_rrcf_anomaly(h1, settled, canonical, identity)
    signatures = build_path_signature_features(h1)
    dml = {"status": "DEFERRED_OFFLINE", "ran_during_navigation": False, "effects": {}, "reason": "No explicit maintenance request in normal Run Calculation."}

    caps = [100.0, _finite(rrcf.get("combined_trust_cap_pct"), 100.0) or 100.0]
    if mmd.get("severity") == "MEDIUM":
        caps.append(80.0)
    elif mmd.get("severity") == "HIGH":
        caps.append(60.0)
    invariance_score = _prob(irm.get("invariance_score"), None)
    if invariance_score is not None:
        caps.append(55.0 + 45.0 * invariance_score)
    if group_dro.get("status") == "VALID":
        selected_name = group_dro.get("selected_candidate")
        robust = _prob(_mapping(_mapping(group_dro.get("candidates")).get(selected_name)).get("robust_selection_score"), None)
        if robust is not None:
            caps.append(50.0 + 50.0 * robust)
    if crc.get("status") == "INSUFFICIENT_EVIDENCE":
        caps.append(70.0)
    trust_cap = float(min(caps))
    result: Dict[str, Any] = {
        "version": VERSION, "schema_version": SCHEMA_VERSION, "created_at": _utc_now(),
        "identity": identity,
        "input_contract": {"completed_h1_rows": int(len(h1)), "settled_prediction_rows": int(len(settled)), "completed_utc_h1_only": True, "bounded_windows": True, "renderers_calculate": False},
        "conformal_risk_control": crc,
        "multicalibration": multicalibration,
        "revin": revin,
        "mmd": mmd,
        "bbse": bbse,
        "dml": dml,
        "irm": irm,
        "group_dro": group_dro,
        "rrcf": rrcf,
        "path_signatures": signatures,
        "base_probabilities": base_probabilities,
        "adjusted_probabilities": probabilities,
        "probability_adjustment_source": "+".join(probability_sources) if probability_sources else "UNCHANGED_INSUFFICIENT_OR_INVALID",
        "trust_cap_pct": trust_cap,
        "research_confidence_status": "VALIDATED" if crc.get("status") == "VALID" and trust_cap >= 70 else "CONSERVATIVE" if len(settled) >= 25 else "INSUFFICIENT_EVIDENCE",
        "decision_policy": {"new_direction_engine": False, "direction_reversal_allowed": False, "allowed_actions": ["CONFIRM", "LOWER_CONFIDENCE", "LOWER_PRIORITY", "WARN", "DOWNGRADE_TO_WAIT"]},
        "performance": {"duration_seconds": None, "bounded_ohlc_rows": _MAX_OHLC_ROWS, "bounded_settled_rows": _MAX_SETTLED_ROWS, "maximum_mmd_sample_per_side": _MAX_MMD_SAMPLE},
        "limitations": [
            "EURUSD H1 is serially dependent, so paper-level iid/exchangeability guarantees are not claimed.",
            "RevIN influence remains disabled unless compatible contributor outputs and settled purged superiority evidence exist.",
            "TP-first/SL-first BBSE is unavailable without a pre-outcome touch-class predictor.",
            "The live anomaly implementation is a bounded random-cut-tree approximation, not an exact dynamic RRCF codisp implementation.",
            "DML effects are not computed during normal UI navigation and require explicit historical event indicators.",
        ],
    }
    result["performance"]["duration_seconds"] = round(time.perf_counter() - started, 6)
    applied = apply_advanced_reliability_policy(canonical, result)
    persistence = {"ok": False, "status": "NOT_REQUESTED"}
    if persist_stage:
        store = store or AdvancedReliabilityStore()
        vector_payload = {"signature": _mapping(signatures).get("features", [])}
        persistence = store.stage(result, vector_payload)
    result["persistence"] = persistence
    # Keep canonical and returned result synchronized after the staging status is known.
    applied["advanced_reliability_shift"] = _json_safe(result)
    return applied, result, persistence


def mark_advanced_reliability_published(calculation_id: str, store: Optional[AdvancedReliabilityStore] = None) -> Dict[str, Any]:
    return (store or AdvancedReliabilityStore()).mark_published(calculation_id)


__all__ = [
    "VERSION", "SCHEMA_VERSION", "AdvancedReliabilityStore",
    "normalize_completed_h1", "normalize_settled_predictions", "completed_h1_hash",
    "conformal_risk_control", "multicalibrate_probability",
    "revin_normalize", "revin_inverse", "build_revin_evidence",
    "rbf_mmd2", "mmd_block_test", "build_mmd_drift",
    "bbse_label_shift", "chronological_purged_splits", "double_ml_partial_linear", "build_dml_event_effects",
    "irm_diagnostics", "group_dro_validation", "random_cut_forest_score", "build_rrcf_anomaly",
    "lead_lag_path", "truncated_signature", "build_path_signature_features",
    "apply_advanced_reliability_policy", "build_advanced_reliability_transaction",
    "mark_advanced_reliability_published",
]
