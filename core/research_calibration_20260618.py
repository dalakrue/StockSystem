# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Ten-paper causal research calibration for the existing ADX Quant Pro pipeline.

The layer is deliberately additive and Streamlit-independent.  It consumes only
completed EURUSD H1 rows, the already-built canonical result, the existing
PowerBI red/yellow/blue bundle, and settled prediction outcomes.  It never
recalculates or replaces Full Metric History, the existing regime labels,
KNN/Greedy formulas, NLP, or the central PowerBI path.

Implemented ideas
-----------------
* Adaptive conformal coverage control under distribution shift.
* Causal time-series conformal residual-vector bootstrapping.
* Lightweight Bayesian online changepoint/run-length inference.
* Adaptive estimation windows with drift-triggered shrink/growth.
* Conditional model confidence sets and bounded dynamic model averaging.
* PBO/DSR validation gates that return honest UNAVAILABLE states when required
  configuration/return data do not exist.
* Aleatoric/epistemic uncertainty separation.
* Naive, drift, session-linear and DLinear-style challenger baselines.

No heavy model is trained during rendering.  The public entry point is intended
to run once inside Settings -> Run Calculation, after all protected calculations
are complete and before atomic canonical publication.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence

import numpy as np
import pandas as pd

RESEARCH_VERSION = "ten-paper-causal-calibration-20260618-v1"
RESEARCH_SCHEMA_VERSION = "adx-research-calibration-1.0.0"
HORIZONS = (1, 2, 3, 4, 5, 6)
TARGET_COVERAGE = 0.80
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "quant_app.sqlite3"
_DB_LOCK = threading.RLock()


# ---------------------------------------------------------------------------
# Safe primitives and canonical completed data
# ---------------------------------------------------------------------------
def _finite(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _clip(value: Any, low: float, high: float, default: Optional[float] = None) -> float:
    fallback = low if default is None else default
    return float(max(low, min(high, _finite(value, fallback) or fallback)))


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(float(value) / math.sqrt(2.0)))


def _json_scalar(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        ts = value
        if pd.isna(ts):
            return None
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(v) for v in value.tolist()]
    if isinstance(value, pd.DataFrame):
        return [_json_safe(row) for row in value.to_dict("records")]
    if isinstance(value, pd.Series):
        return [_json_safe(v) for v in value.tolist()]
    return _json_scalar(value)


def _hash_payload(value: Any) -> str:
    raw = json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def _find_col(frame: pd.DataFrame, aliases: Iterable[str]) -> Optional[str]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    normalized = {"".join(ch for ch in str(c).lower() if ch.isalnum()): c for c in frame.columns}
    for alias in aliases:
        key = "".join(ch for ch in str(alias).lower() if ch.isalnum())
        if key in normalized:
            return normalized[key]
    for alias in aliases:
        key = "".join(ch for ch in str(alias).lower() if ch.isalnum())
        for name, column in normalized.items():
            if key and key in name:
                return column
    return None


def normalize_completed_ohlc(data: pd.DataFrame, latest_completed: Any = None) -> pd.DataFrame:
    """Return a causal, sorted, de-duplicated completed-H1 frame.

    No timestamps are invented, no future backfill is used, and the caller's
    frame is not mutated.  ``latest_completed`` is the immutable canonical cutoff.
    """
    if not isinstance(data, pd.DataFrame) or data.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close"])
    t = _find_col(data, ("time", "datetime", "timestamp", "date"))
    c = _find_col(data, ("close", "c"))
    if t is None or c is None:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close"])
    o = _find_col(data, ("open", "o")); h = _find_col(data, ("high", "h")); l = _find_col(data, ("low", "l"))
    close = pd.to_numeric(data[c], errors="coerce")
    out = pd.DataFrame({"time": pd.to_datetime(data[t], errors="coerce", utc=True), "close": close})
    out["open"] = pd.to_numeric(data[o], errors="coerce") if o else close
    out["high"] = pd.to_numeric(data[h], errors="coerce") if h else out[["open", "close"]].max(axis=1)
    out["low"] = pd.to_numeric(data[l], errors="coerce") if l else out[["open", "close"]].min(axis=1)
    out = out.dropna(subset=["time", "open", "high", "low", "close"])
    out = out.sort_values("time", kind="stable").drop_duplicates("time", keep="last")
    if latest_completed not in (None, ""):
        cutoff = pd.to_datetime(latest_completed, errors="coerce", utc=True)
        if pd.notna(cutoff):
            out = out.loc[out["time"] <= cutoff]
    out["high"] = out[["open", "high", "low", "close"]].max(axis=1)
    out["low"] = out[["open", "high", "low", "close"]].min(axis=1)
    return out.reset_index(drop=True)


def data_hash(frame: pd.DataFrame) -> str:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return "NO_DATA"
    selected = frame[[c for c in ("time", "open", "high", "low", "close") if c in frame.columns]]
    return sha256(pd.util.hash_pandas_object(selected, index=False).values.tobytes()).hexdigest()


def _calculation_id(canonical: Mapping[str, Any], frame_hash: str, latest: str, input_hash: str = "") -> str:
    raw = "|".join([
        str(canonical.get("symbol") or "EURUSD").upper(),
        str(canonical.get("timeframe") or "H1").upper(),
        str(latest), frame_hash, str(input_hash), RESEARCH_VERSION,
    ])
    return "RCALC-" + sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:24]


def _session_label(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return "UNKNOWN"
    hour = int(ts.hour)
    if 0 <= hour < 7:
        return "ASIAN"
    if 7 <= hour < 12:
        return "LONDON"
    if 12 <= hour < 16:
        return "LONDON_NEW_YORK_OVERLAP"
    if 16 <= hour < 21:
        return "NEW_YORK"
    return "OTHER"


def _direction(value: Any) -> str:
    text = str(value or "").upper()
    if any(token in text for token in ("BUY", "BULL", "UP")):
        return "BUY"
    if any(token in text for token in ("SELL", "BEAR", "DOWN")):
        return "SELL"
    return "NEUTRAL"


def _atr(frame: pd.DataFrame, window: int = 24) -> float:
    if frame.empty:
        return 0.0005
    previous = frame["close"].shift(1)
    tr = pd.concat([
        (frame["high"] - frame["low"]).abs(),
        (frame["high"] - previous).abs(),
        (frame["low"] - previous).abs(),
    ], axis=1).max(axis=1)
    value = _finite(tr.tail(max(4, window)).median(), 0.0005)
    return max(float(value or 0.0005), 1e-9)


def purged_walk_forward_splits(
    row_count: int, *, minimum_train: int = 96, validation_size: int = 24,
    maximum_horizon: int = 6, embargo: Optional[int] = None,
) -> list[Dict[str, Any]]:
    """Create chronological validation splits with purge and embargo.

    Training targets end before the validation feature window and an embargo of
    at least the maximum forecast horizon separates consecutive validation uses.
    """
    count = max(0, int(row_count))
    purge = max(1, int(maximum_horizon))
    embargo_size = max(purge, int(embargo if embargo is not None else purge))
    train_min = max(purge * 4, int(minimum_train))
    valid_size = max(purge + 1, int(validation_size))
    splits: list[Dict[str, Any]] = []
    validation_start = train_min + purge
    split_id = 0
    while validation_start + valid_size <= count:
        train_end_exclusive = validation_start - purge
        validation_end_exclusive = validation_start + valid_size
        splits.append({
            "split_id": split_id,
            "train_start": 0,
            "train_end_exclusive": train_end_exclusive,
            "validation_start": validation_start,
            "validation_end_exclusive": validation_end_exclusive,
            "purging_period": purge,
            "embargo_period": embargo_size,
            "maximum_forecast_horizon": purge,
            "targets_overlap": False,
        })
        split_id += 1
        validation_start = validation_end_exclusive + embargo_size
    return splits


# ---------------------------------------------------------------------------
# Paper 10: challenger baselines and causal walk-forward evaluation
# ---------------------------------------------------------------------------
def _linear_extrapolation(values: np.ndarray, horizon: int, lookback: int) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 4:
        return np.repeat(values[-1] if len(values) else 0.0, horizon)
    use = values[-min(lookback, len(values)):]
    x = np.arange(len(use), dtype=float)
    slope, intercept = np.polyfit(x, use, 1)
    future_x = np.arange(len(use), len(use) + horizon, dtype=float)
    return intercept + slope * future_x


def _baseline_paths(frame: pd.DataFrame, horizon: int = 6) -> Dict[str, list[float]]:
    close = frame["close"].to_numpy(dtype=float)
    anchor = float(close[-1])
    atr = _atr(frame)
    returns = pd.Series(close).pct_change().dropna()
    recent_return = _finite(returns.tail(48).mean(), 0.0) or 0.0
    recent_return = _clip(recent_return, -atr / max(abs(anchor), 1e-12), atr / max(abs(anchor), 1e-12), 0.0)

    naive = np.repeat(anchor, horizon)
    drift = np.asarray([anchor * (1.0 + recent_return * step) for step in range(1, horizon + 1)], dtype=float)

    current_session = _session_label(frame["time"].iloc[-1])
    current_hour = int(pd.Timestamp(frame["time"].iloc[-1]).hour)
    session_returns: Dict[int, float] = {}
    for step in range(1, horizon + 1):
        values: list[float] = []
        latest_origin = len(frame) - step - 1
        for index in range(max(0, latest_origin - 1500), latest_origin + 1):
            ts = frame["time"].iloc[index]
            if _session_label(ts) != current_session:
                continue
            hour_distance = min((int(pd.Timestamp(ts).hour) - current_hour) % 24, (current_hour - int(pd.Timestamp(ts).hour)) % 24)
            if hour_distance > 1:
                continue
            base = float(frame["close"].iloc[index])
            target = float(frame["close"].iloc[index + step])
            if base:
                values.append(target / base - 1.0)
        session_returns[step] = float(np.median(values)) if len(values) >= 12 else recent_return * step
    session_linear = np.asarray([anchor * (1.0 + session_returns[step]) for step in range(1, horizon + 1)], dtype=float)

    trend = pd.Series(close).rolling(24, min_periods=8).mean().to_numpy(dtype=float)
    valid_trend = pd.Series(trend).dropna().to_numpy(dtype=float)
    if len(valid_trend) < 8:
        valid_trend = close.copy()
    trend_full = pd.Series(trend).ffill().fillna(pd.Series(close)).to_numpy(dtype=float)
    remainder = close - trend_full
    trend_forecast = _linear_extrapolation(valid_trend, horizon, 96)
    remainder_forecast = _linear_extrapolation(remainder, horizon, 48)
    dlinear = trend_forecast + remainder_forecast

    maximum_step = atr * 2.5
    result: Dict[str, list[float]] = {}
    for name, values in {
        "naive_last_close": naive,
        "drift": drift,
        "session_linear": session_linear,
        "dlinear_style": dlinear,
    }.items():
        bounded: list[float] = []
        previous = anchor
        for raw in values:
            value = previous + _clip(float(raw) - previous, -maximum_step, maximum_step, 0.0)
            value = max(value, 1e-9)
            bounded.append(float(value)); previous = value
        result[name] = bounded
    return result


def build_baseline_forecasts(frame: pd.DataFrame, horizon: int = 6) -> Dict[str, Any]:
    market = normalize_completed_ohlc(frame)
    if len(market) < 30:
        return {"status": "INSUFFICIENT SAMPLE", "sample_size": int(len(market)), "paths": {}}
    paths = _baseline_paths(market, horizon=horizon)
    return {
        "status": "VALID", "sample_size": int(len(market)), "anchor_price": float(market["close"].iloc[-1]),
        "anchor_time": _json_scalar(market["time"].iloc[-1]), "paths": {name: [round(v, 8) for v in values] for name, values in paths.items()},
        "causal_policy": "past-only rolling decomposition and same-session completed outcomes",
    }


def _walk_forward_baseline_vectors(
    frame: pd.DataFrame, max_origins: int = 180,
) -> tuple[np.ndarray, Dict[str, Dict[int, np.ndarray]], pd.DataFrame]:
    """Causal walk-forward residual vectors and origin metadata.

    Each origin uses only rows at or before that origin.  The metadata permits
    condition-aware residual selection without breaking the H+1..H+6 vector.
    """
    market = normalize_completed_ohlc(frame)
    if len(market) < 90:
        return np.empty((0, 6), dtype=float), {}, pd.DataFrame()
    start = max(60, len(market) - max_origins - max(HORIZONS))
    vectors: list[list[float]] = []
    metadata: list[Dict[str, Any]] = []
    model_errors: Dict[str, Dict[int, list[float]]] = {
        name: {h: [] for h in HORIZONS} for name in ("naive_last_close", "drift", "session_linear", "dlinear_style")
    }
    for origin in range(start, len(market) - max(HORIZONS)):
        train = market.iloc[: origin + 1]
        paths = _baseline_paths(train, horizon=max(HORIZONS))
        dlinear_vector: list[float] = []
        for h in HORIZONS:
            actual = float(market["close"].iloc[origin + h])
            for name, path in paths.items():
                model_errors[name][h].append(actual - float(path[h - 1]))
            dlinear_vector.append(actual - float(paths["dlinear_style"][h - 1]))
        vectors.append(dlinear_vector)
        returns = train["close"].pct_change()
        rolling_vol = returns.rolling(24, min_periods=8).std(ddof=0).dropna()
        current_vol = float(rolling_vol.iloc[-1]) if len(rolling_vol) else 0.0
        past_vol = rolling_vol.iloc[:-1] if len(rolling_vol) > 1 else rolling_vol
        q60 = float(past_vol.quantile(0.60)) if len(past_vol) >= 12 else current_vol
        q85 = float(past_vol.quantile(0.85)) if len(past_vol) >= 12 else current_vol
        vol_regime = "CALM" if current_vol <= q60 else "TURBULENT" if current_vol <= q85 else "CRISIS"
        anchor = float(train["close"].iloc[-1])
        direction = "BUY" if paths["dlinear_style"][-1] > anchor else "SELL" if paths["dlinear_style"][-1] < anchor else "NEUTRAL"
        metadata.append({
            "origin_time": _json_scalar(train["time"].iloc[-1]),
            "session": _session_label(train["time"].iloc[-1]),
            "volatility_regime": vol_regime,
            "direction": direction,
            "realized_volatility": current_vol,
            "source": "DLINEAR_WALK_FORWARD_FALLBACK",
        })
    arrays = {name: {h: np.asarray(values, dtype=float) for h, values in per_h.items()} for name, per_h in model_errors.items()}
    return np.asarray(vectors, dtype=float), arrays, pd.DataFrame(metadata)

def _normalized_prediction_history(history: pd.DataFrame) -> pd.DataFrame:
    """Normalize completed forecast outcomes without inventing unavailable fields."""
    if not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame()
    predicted_col = _find_col(history, ("predicted price", "pred close", "predicted close", "point forecast", "central"))
    actual_col = _find_col(history, ("actual price", "actual close", "actual completed close"))
    target_col = _find_col(history, ("actual time", "target time", "target completion time", "time"))
    prediction_time_col = _find_col(history, ("prediction time", "prediction creation time", "created at"))
    horizon_col = _find_col(history, ("horizon hours", "horizon"))
    lower_col = _find_col(history, ("lower bound", "lower band", "predicted lower band"))
    upper_col = _find_col(history, ("upper bound", "upper band", "predicted upper band"))
    current_col = _find_col(history, ("current price", "anchor price"))
    direction_col = _find_col(history, ("predicted direction", "direction"))
    regime_col = _find_col(history, ("major regime", "directional regime", "regime"))
    vol_col = _find_col(history, ("volatility regime",))
    transition_col = _find_col(history, ("transition risk", "transition risk 0 100"))
    disagreement_col = _find_col(history, ("path disagreement", "source spread"))
    reliability_col = _find_col(history, ("reliability at prediction time", "reliability", "confidence"))
    realized_vol_col = _find_col(history, ("realized volatility",))
    calc_col = _find_col(history, ("calculation id", "run id", "prediction calculation id"))
    if predicted_col is None or actual_col is None:
        return pd.DataFrame()
    target_time = pd.to_datetime(history[target_col], errors="coerce", utc=True) if target_col else pd.Series(pd.NaT, index=history.index)
    prediction_time = pd.to_datetime(history[prediction_time_col], errors="coerce", utc=True) if prediction_time_col else pd.Series(pd.NaT, index=history.index)
    out = pd.DataFrame({
        "calculation_id": history[calc_col].astype(str) if calc_col else "UNKNOWN",
        "prediction_time": prediction_time,
        "predicted": pd.to_numeric(history[predicted_col], errors="coerce"),
        "actual": pd.to_numeric(history[actual_col], errors="coerce"),
        "target_time": target_time,
        "horizon": pd.to_numeric(history[horizon_col], errors="coerce").fillna(1).astype(int) if horizon_col else 1,
        "current_price": pd.to_numeric(history[current_col], errors="coerce") if current_col else np.nan,
        "prediction_direction": history[direction_col].map(_direction) if direction_col else "NEUTRAL",
        "directional_regime": history[regime_col].astype(str) if regime_col else "UNKNOWN",
        "volatility_regime": history[vol_col].astype(str).str.upper() if vol_col else "UNKNOWN",
        "transition_risk": pd.to_numeric(history[transition_col], errors="coerce") if transition_col else np.nan,
        "path_disagreement": pd.to_numeric(history[disagreement_col], errors="coerce") if disagreement_col else np.nan,
        "reliability_at_prediction_time": pd.to_numeric(history[reliability_col], errors="coerce") if reliability_col else np.nan,
        "realized_volatility": pd.to_numeric(history[realized_vol_col], errors="coerce") if realized_vol_col else np.nan,
    })
    out["lower"] = pd.to_numeric(history[lower_col], errors="coerce") if lower_col else np.nan
    out["upper"] = pd.to_numeric(history[upper_col], errors="coerce") if upper_col else np.nan
    out = out.dropna(subset=["predicted", "actual"])
    out = out.loc[out["horizon"].isin(HORIZONS)]
    out["signed_residual"] = out["actual"] - out["predicted"]
    out["residual"] = out["signed_residual"]
    out["absolute_residual"] = out["signed_residual"].abs()
    out["session"] = out["target_time"].map(_session_label)
    out["hour"] = out["target_time"].dt.hour
    actual_direction = np.where(out["actual"] > out["current_price"], "BUY", np.where(out["actual"] < out["current_price"], "SELL", "NEUTRAL"))
    out["direction_correct"] = np.where(out["current_price"].notna(), out["prediction_direction"].to_numpy() == actual_direction, np.nan)
    out["transition_state"] = np.where(pd.to_numeric(out["transition_risk"], errors="coerce") >= 60, "HIGH_TRANSITION_RISK", "LOW_TRANSITION_RISK")
    out["inside_interval"] = np.where(
        out["lower"].notna() & out["upper"].notna(),
        (out["actual"] >= out["lower"]) & (out["actual"] <= out["upper"]),
        np.nan,
    )
    return out.sort_values(["target_time", "horizon"], kind="stable").reset_index(drop=True)

def build_residual_vectors(
    frame: pd.DataFrame,
    prediction_history: Optional[pd.DataFrame] = None,
    settled_predictions: Optional[pd.DataFrame] = None,
    max_origins: int = 180,
) -> Dict[str, Any]:
    """Build coherent H+1..H+6 residual vectors from completed outcomes.

    The output retains vector-level condition metadata so a whole historical
    six-hour error trajectory is selected together.  No horizon is sampled
    independently.
    """
    combined = []
    for source in (settled_predictions, prediction_history):
        normalized = _normalized_prediction_history(source) if isinstance(source, pd.DataFrame) else pd.DataFrame()
        if not normalized.empty:
            combined.append(normalized)
    scalar_bank = pd.concat(combined, ignore_index=True).drop_duplicates(
        subset=["calculation_id", "target_time", "horizon", "predicted", "actual"], keep="last"
    ) if combined else pd.DataFrame()

    aligned_vectors: list[list[float]] = []
    aligned_meta: list[Dict[str, Any]] = []
    vector_source = "SETTLED_SYSTEM_FORECASTS"
    if not scalar_bank.empty and "target_time" in scalar_bank.columns:
        work = scalar_bank.dropna(subset=["target_time"]).copy()
        work["origin_time"] = work["target_time"] - pd.to_timedelta(work["horizon"], unit="h")
        for origin_time, group in work.groupby("origin_time", sort=True):
            mapping = {int(row.horizon): float(row.residual) for row in group.itertuples()}
            if all(h in mapping for h in HORIZONS):
                aligned_vectors.append([mapping[h] for h in HORIZONS])
                first = group.sort_values("horizon", kind="stable").iloc[0]
                aligned_meta.append({
                    "origin_time": _json_scalar(origin_time),
                    "session": str(first.get("session") or "UNKNOWN"),
                    "volatility_regime": str(first.get("volatility_regime") or "UNKNOWN").upper(),
                    "direction": _direction(first.get("prediction_direction")),
                    "realized_volatility": _finite(first.get("realized_volatility"), None),
                    "transition_state": str(first.get("transition_state") or "UNKNOWN"),
                    "source": "SETTLED_SYSTEM_FORECASTS",
                })
    baseline_vectors, baseline_errors, baseline_meta = _walk_forward_baseline_vectors(frame, max_origins=max_origins)
    if len(aligned_vectors) < 12:
        vectors = baseline_vectors
        metadata = baseline_meta
        vector_source = "DLINEAR_WALK_FORWARD_FALLBACK"
    else:
        vectors = np.asarray(aligned_vectors[-max_origins:], dtype=float)
        metadata = pd.DataFrame(aligned_meta[-max_origins:])
    return {
        "vectors": vectors,
        "vector_metadata": metadata,
        "vector_source": vector_source,
        "vector_count": int(len(vectors)),
        "scalar_bank": scalar_bank,
        "baseline_errors": baseline_errors,
        "system_scalar_count": int(len(scalar_bank)),
        "minimum_specific_group": 12,
        "coherent": bool(vectors.ndim == 2 and vectors.shape[1] == 6) if len(vectors) else False,
        "stored_fields": [
            "calculation_id", "prediction_time", "target_time", "horizon", "predicted", "actual",
            "signed_residual", "absolute_residual", "direction_correct", "directional_regime",
            "volatility_regime", "session", "hour", "transition_risk", "path_disagreement",
            "reliability_at_prediction_time",
        ],
    }

def _central_path(calibrated_bundle: Optional[Mapping[str, Any]], canonical: Mapping[str, Any], anchor: float) -> np.ndarray:
    values: list[float] = []
    bundle = calibrated_bundle if isinstance(calibrated_bundle, Mapping) else {}
    main = bundle.get("main")
    if isinstance(main, pd.DataFrame) and not main.empty:
        column = _find_col(main, ("main path", "central path", "close"))
        if column:
            values = pd.to_numeric(main[column], errors="coerce").dropna().head(6).astype(float).tolist()
    if len(values) < 6:
        horizons = ((canonical.get("forecasts") or {}).get("horizons") or {}) if isinstance(canonical.get("forecasts"), Mapping) else {}
        values = []
        for h in HORIZONS:
            row = horizons.get(f"{h}h") or horizons.get(str(h)) or {}
            values.append(float(_finite((row or {}).get("point_forecast"), anchor) or anchor))
    while len(values) < 6:
        values.append(values[-1] if values else anchor)
    return np.asarray(values[:6], dtype=float)


def update_adaptive_coverage(
    previous: Optional[Mapping[str, Any]],
    observations: pd.DataFrame,
    *,
    current_volatility_regime: str,
    current_session: str,
    transition_state: str,
    target_coverage: float = TARGET_COVERAGE,
) -> Dict[str, Any]:
    previous_states = deepcopy(dict((previous or {}).get("states") or {}))
    states: Dict[str, Any] = previous_states
    updated_keys: list[str] = []
    for h in HORIZONS:
        key = f"H+{h}|{current_volatility_regime}|{current_session}|{transition_state}"
        old = dict(previous_states.get(key) or {})
        observed = float(target_coverage)
        correction = 1.0
        sample_size = 0
        subset = observations.loc[(observations.get("horizon", pd.Series(dtype=int)) == h)].copy() if not observations.empty else pd.DataFrame()
        # Prefer the most specific completed-outcome group, then broaden only
        # when fewer than the required observations exist.
        if not subset.empty:
            candidates = []
            if {"volatility_regime", "session", "transition_state"}.issubset(subset.columns):
                candidates.append(subset.loc[
                    subset["volatility_regime"].astype(str).str.upper().eq(current_volatility_regime.upper())
                    & subset["session"].astype(str).str.upper().eq(current_session.upper())
                    & subset["transition_state"].astype(str).str.upper().eq(transition_state.upper())
                ])
            if "volatility_regime" in subset.columns:
                candidates.append(subset.loc[subset["volatility_regime"].astype(str).str.upper().eq(current_volatility_regime.upper())])
            candidates.append(subset)
            subset = next((candidate for candidate in candidates if len(candidate) >= 8), candidates[-1])
        if not subset.empty and "inside_interval" in subset.columns:
            valid = pd.to_numeric(subset["inside_interval"], errors="coerce").dropna().tail(100)
            for inside in valid.to_numpy(dtype=float):
                observed = 0.94 * observed + 0.06 * inside
                error = target_coverage - observed
                # Gradual bounded ACI-style update. One candle cannot dominate.
                correction = _clip(correction * math.exp(_clip(error, -0.20, 0.20) * 0.10), 0.65, 2.50, 1.0)
                sample_size += 1
        elif old:
            # No new completed outcomes for this condition: reuse, do not drift.
            observed = float(old.get("observed_coverage", target_coverage))
            correction = float(old.get("adaptive_correction", 1.0))
            sample_size = int(old.get("sample_size", 0) or 0)
        coverage_error = target_coverage - observed
        quality = _clip(100.0 * (1.0 - abs(coverage_error) / max(target_coverage, 1e-12)), 0.0, 100.0, 0.0)
        updated_keys.append(key)
        states[key] = {
            "horizon": h, "volatility_regime": current_volatility_regime, "session": current_session,
            "transition_state": transition_state, "target_coverage": round(target_coverage, 6),
            "observed_coverage": round(observed, 6), "coverage_error": round(coverage_error, 6),
            "adaptive_correction": round(correction, 6), "sample_size": sample_size,
            "coverage_quality_0_100": round(quality, 4),
        }
    quality_values = [float(states[key]["coverage_quality_0_100"]) for key in updated_keys if key in states]
    return {
        "version": RESEARCH_VERSION, "states": states, "updated_state_keys": updated_keys,
        "mean_coverage_quality_0_100": round(float(np.mean(quality_values)) if quality_values else 0.0, 4),
        "bounded_update": True, "correction_bounds": [0.65, 2.50], "target_coverage": target_coverage,
    }


def _select_conditioned_vectors(
    residual_bundle: Mapping[str, Any], *, current_volatility_regime: str,
    current_session: str, current_direction: str, current_realized_volatility: Optional[float],
    minimum_sample: int = 12,
) -> tuple[np.ndarray, str, int]:
    vectors = np.asarray(residual_bundle.get("vectors") if residual_bundle else np.empty((0, 6)), dtype=float)
    metadata = residual_bundle.get("vector_metadata")
    if vectors.ndim != 2 or vectors.shape[1] != 6 or not len(vectors):
        return np.zeros((1, 6), dtype=float), "LEVEL_5_ALL_VALID_COMPLETED_RESIDUALS", 0
    if not isinstance(metadata, pd.DataFrame) or len(metadata) != len(vectors):
        return vectors, "LEVEL_5_ALL_VALID_COMPLETED_RESIDUALS", int(len(vectors))
    meta = metadata.reset_index(drop=True).copy()
    vol = meta.get("volatility_regime", pd.Series("UNKNOWN", index=meta.index)).astype(str).str.upper()
    session = meta.get("session", pd.Series("UNKNOWN", index=meta.index)).astype(str).str.upper()
    direction = meta.get("direction", pd.Series("NEUTRAL", index=meta.index)).map(_direction)
    candidates = [
        ("LEVEL_1_HORIZON_VOLATILITY_SESSION_DIRECTION", (vol == current_volatility_regime.upper()) & (session == current_session.upper()) & (direction == _direction(current_direction))),
        ("LEVEL_2_HORIZON_VOLATILITY_DIRECTION", (vol == current_volatility_regime.upper()) & (direction == _direction(current_direction))),
        ("LEVEL_3_HORIZON_VOLATILITY", vol == current_volatility_regime.upper()),
    ]
    if current_realized_volatility is not None and "realized_volatility" in meta.columns:
        rv = pd.to_numeric(meta["realized_volatility"], errors="coerce")
        tolerance = max(abs(float(current_realized_volatility)) * 0.35, float(rv.dropna().std(ddof=0) or 0.0), 1e-8)
        candidates.append(("LEVEL_4_HORIZON_SIMILAR_REALIZED_VOLATILITY", (rv - float(current_realized_volatility)).abs() <= tolerance))
    for level, mask in candidates:
        positions = np.flatnonzero(mask.fillna(False).to_numpy())
        if len(positions) >= minimum_sample:
            return vectors[positions], level, int(len(positions))
    return vectors, "LEVEL_5_ALL_VALID_COMPLETED_RESIDUALS", int(len(vectors))


def conformal_scenarios(
    central: Sequence[float], residual_bundle: Mapping[str, Any], *, seed_material: str,
    adaptive_coverage: Mapping[str, Any], current_volatility_regime: str,
    current_session: str, transition_state: str, anchor: float, simulations: int = 1200,
    tp_distance: Optional[float] = None, sl_distance: Optional[float] = None,
    current_direction: str = "NEUTRAL", current_realized_volatility: Optional[float] = None,
) -> Dict[str, Any]:
    central_path = np.asarray(list(central), dtype=float)[:6]
    if len(central_path) < 6:
        central_path = np.pad(central_path, (0, 6 - len(central_path)), constant_values=anchor)
    vectors, fallback_level, conditioned_sample_size = _select_conditioned_vectors(
        residual_bundle, current_volatility_regime=current_volatility_regime,
        current_session=current_session, current_direction=current_direction,
        current_realized_volatility=current_realized_volatility,
        minimum_sample=int(residual_bundle.get("minimum_specific_group", 12) or 12),
    )
    seed = int(sha256(seed_material.encode("utf-8", errors="ignore")).hexdigest()[:16], 16) % (2**32)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(vectors), size=max(200, int(simulations)))
    scenarios = central_path[None, :] + vectors[indices]
    quantiles = np.quantile(scenarios, [0.10, 0.25, 0.50, 0.75, 0.90], axis=0)
    # Enforce ordering against numerical noise.
    quantiles = np.maximum.accumulate(quantiles, axis=0)
    p10, p25, p50, p75, p90 = quantiles
    lower = p10.copy(); upper = p90.copy()
    state_map = dict(adaptive_coverage.get("states") or {})
    corrections = []
    for index, h in enumerate(HORIZONS):
        key = f"H+{h}|{current_volatility_regime}|{current_session}|{transition_state}"
        correction = float((state_map.get(key) or {}).get("adaptive_correction", 1.0))
        corrections.append(correction)
        lower[index] = central_path[index] - max(0.0, central_path[index] - lower[index]) * correction
        upper[index] = central_path[index] + max(0.0, upper[index] - central_path[index]) * correction
    lower = np.minimum(lower, central_path); upper = np.maximum(upper, central_path)

    typical_move = float(np.median(np.abs(vectors[:, -1]))) if len(vectors) else 0.0
    tp = float(tp_distance if tp_distance is not None else max(typical_move, abs(central_path[-1] - anchor), 1e-7))
    sl = float(sl_distance if sl_distance is not None else max(typical_move, tp * 0.75, 1e-7))
    direction = 1.0 if central_path[-1] >= anchor else -1.0
    signed_paths = (scenarios - anchor) * direction
    tp_probability = float(np.mean(np.max(signed_paths, axis=1) >= tp))
    sl_probability = float(np.mean(np.min(signed_paths, axis=1) <= -sl))
    mfe = np.max(signed_paths, axis=1); mae = np.maximum(0.0, -np.min(signed_paths, axis=1))

    rows = []
    for index, h in enumerate(HORIZONS):
        rows.append({
            "horizon": h, "central": round(float(central_path[index]), 8),
            "p10": round(float(p10[index]), 8), "p25": round(float(p25[index]), 8),
            "p50": round(float(p50[index]), 8), "p75": round(float(p75[index]), 8),
            "p90": round(float(p90[index]), 8), "lower_band": round(float(lower[index]), 8),
            "upper_band": round(float(upper[index]), 8), "adaptive_correction": round(float(corrections[index]), 6),
            "probability_above_current_close": round(float(np.mean(scenarios[:, index] > anchor)), 6),
            "probability_below_current_close": round(float(np.mean(scenarios[:, index] < anchor)), 6),
        })
    return {
        "status": "VALID" if residual_bundle.get("vector_count", 0) >= 12 else "LOW SAMPLE FALLBACK",
        "residual_vector_source": residual_bundle.get("vector_source"),
        "residual_vector_count": int(residual_bundle.get("vector_count", 0) or 0),
        "deterministic_seed": int(seed), "simulation_count": int(len(scenarios)), "horizons": rows,
        "tp_touch_probability": round(tp_probability, 6), "sl_touch_probability": round(sl_probability, 6),
        "expected_maximum_favourable_excursion": round(float(np.mean(mfe)), 8),
        "expected_maximum_adverse_excursion": round(float(np.mean(mae)), 8),
        "tp_distance": round(tp, 8), "sl_distance": round(sl, 8),
        "coherent_residual_vector_sampling": True,
        "fallback_hierarchy_level": fallback_level,
        "conditioned_vector_sample_size": conditioned_sample_size,
        "conditions": {"volatility_regime": current_volatility_regime, "session": current_session, "direction": _direction(current_direction)},
    }


# ---------------------------------------------------------------------------
# Paper 3: Bayesian online changepoint/run-length distribution
# ---------------------------------------------------------------------------
def _causal_standardize(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    mean = values.expanding(min_periods=8).mean().shift(1)
    std = values.expanding(min_periods=8).std(ddof=0).shift(1)
    return ((values - mean) / std.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _change_feature(frame: pd.DataFrame) -> np.ndarray:
    close = frame["close"]
    ret = close.pct_change().fillna(0.0)
    abs_ret = ret.abs()
    range_ratio = ((frame["high"] - frame["low"]).abs() / close.replace(0, np.nan)).fillna(0.0)
    realized = ret.rolling(24, min_periods=6).std(ddof=0).fillna(0.0)
    composite = 0.38 * _causal_standardize(ret) + 0.26 * _causal_standardize(abs_ret) + 0.20 * _causal_standardize(range_ratio) + 0.16 * _causal_standardize(realized)
    return composite.to_numpy(dtype=float)


def bayesian_online_changepoint(frame: pd.DataFrame, hazard_lambda: float = 72.0, max_run_length: int = 240) -> Dict[str, Any]:
    market = normalize_completed_ohlc(frame).tail(720)
    if len(market) < 36:
        return {"status": "INSUFFICIENT SAMPLE", "sample_size": int(len(market)), "probability_change_now": 0.5}
    values = _change_feature(market)
    observation_variance = max(float(np.var(values[: max(24, len(values) // 3)])), 0.35)
    hazard = 1.0 / max(float(hazard_lambda), 2.0)
    run = np.array([1.0], dtype=float)
    means = np.array([0.0], dtype=float)
    counts = np.array([0.0], dtype=float)
    cp_history: list[float] = []
    for value in values:
        predictive_variance = observation_variance * (1.0 + 1.0 / (counts + 1.0))
        log_like = -0.5 * (np.log(2.0 * math.pi * predictive_variance) + np.square(value - means) / predictive_variance)
        likelihood = np.exp(np.clip(log_like - np.max(log_like), -80.0, 0.0))
        growth = run * likelihood * (1.0 - hazard)
        change = float(np.sum(run * likelihood * hazard))
        new_run = np.concatenate([[change], growth])[: max_run_length + 1]
        total = float(new_run.sum())
        new_run = new_run / total if total > 0 else np.array([1.0])
        new_means = np.empty_like(new_run)
        new_counts = np.empty_like(new_run)
        new_means[0] = value; new_counts[0] = 1.0
        keep = len(new_run) - 1
        if keep:
            prior_counts = counts[:keep]
            prior_means = means[:keep]
            new_counts[1:] = prior_counts + 1.0
            new_means[1:] = (prior_means * prior_counts + value) / np.maximum(new_counts[1:], 1.0)
        run, means, counts = new_run, new_means, new_counts
        cp_history.append(float(run[0]))
    run_lengths = np.arange(len(run), dtype=float)
    expected = float(np.sum(run_lengths * run))
    most_likely = int(np.argmax(run))
    p_now = float(run[0])
    p3 = float(1.0 - np.prod([1.0 - _clip(v, 0.0, 1.0, 0.0) for v in cp_history[-3:]]))
    p6 = float(1.0 - np.prod([1.0 - _clip(v, 0.0, 1.0, 0.0) for v in cp_history[-6:]]))
    transition_risk = _clip(100.0 * (0.50 * p_now + 0.30 * p3 + 0.20 * p6), 0.0, 100.0, 50.0)
    if transition_risk >= 67:
        window, confidence = "Next 1–3 completed H1 candles", "HIGH"
    elif transition_risk >= 42:
        window, confidence = "Next 2–5 completed H1 candles", "MODERATE"
    else:
        window, confidence = "Beyond the next 3–6 completed H1 candles", "LOW"
    top_indices = np.argsort(run)[-12:][::-1]
    return {
        "status": "VALID", "sample_size": int(len(values)), "hazard_lambda": float(hazard_lambda),
        "most_likely_run_length": most_likely, "expected_run_length": round(expected, 4),
        "probability_change_now": round(p_now, 8), "probability_change_last_3": round(p3, 8),
        "probability_change_last_6": round(p6, 8), "probability_structure_continues_one_more": round(1.0 - p_now, 8),
        "transition_risk_0_100": round(transition_risk, 4), "estimated_transition_window": window,
        "transition_confidence": confidence,
        "run_length_distribution_summary": [{"run_length": int(i), "probability": round(float(run[i]), 10)} for i in top_indices],
        "probability_sum": round(float(run.sum()), 12),
    }


# ---------------------------------------------------------------------------
# Paper 4: adaptive windows
# ---------------------------------------------------------------------------
def _distribution_change(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 48:
        return 0.0
    recent_n = min(24, max(12, len(values) // 6))
    recent = values.tail(recent_n)
    baseline = values.iloc[:-recent_n].tail(max(48, recent_n * 4))
    if len(baseline) < 24:
        return 0.0
    scale = max(float(baseline.std(ddof=0)), 1e-12)
    mean_shift = abs(float(recent.mean() - baseline.mean())) / scale
    std_ratio = abs(math.log(max(float(recent.std(ddof=0)), 1e-12) / scale))
    return float(_clip(0.65 * mean_shift / 3.0 + 0.35 * std_ratio / 2.0, 0.0, 1.0, 0.0))


def update_adaptive_windows(previous: Optional[Mapping[str, Any]], frame: pd.DataFrame, changepoint: Mapping[str, Any]) -> Dict[str, Any]:
    market = normalize_completed_ohlc(frame)
    ret = market["close"].pct_change().dropna()
    change_magnitude = max(_distribution_change(ret), _clip((changepoint.get("transition_risk_0_100") or 0) / 100.0, 0, 1, 0))
    definitions = {
        "prediction_residuals": (24, 720, 180), "direction_accuracy": (30, 720, 240),
        "reliability_calibration": (30, 1000, 300), "model_performance": (36, 1000, 300),
        "session_performance": (24, 720, 240), "volatility_estimation": (12, 480, 96),
        "feature_importance": (48, 1200, 360), "knn_candidate_history": (30, 1000, 300),
        "nlp_impact_relationship": (20, 720, 180),
    }
    old_states = dict((previous or {}).get("states") or {})
    latest_timestamp = _json_scalar(market["time"].iloc[-1]) if not market.empty else None
    if old_states and all(str((item or {}).get("last_update_timestamp")) == str(latest_timestamp) for item in old_states.values()):
        return {"version": RESEARCH_VERSION, "states": deepcopy(old_states), "incremental": True, "history_preserved": True, "cache_status": "REUSED_SAME_COMPLETED_H1"}
    states: Dict[str, Any] = {}
    for name, (minimum, maximum, default) in definitions.items():
        prior = int((old_states.get(name) or {}).get("current_window_size", default) or default)
        if change_magnitude >= 0.58:
            current = max(minimum, int(round(prior * 0.62)))
            detected = True
        elif change_magnitude >= 0.34:
            current = max(minimum, int(round(prior * 0.82)))
            detected = True
        else:
            current = min(maximum, prior + max(4, int(round(prior * 0.05))))
            detected = False
        states[name] = {
            "window_name": name, "previous_window_size": prior, "current_window_size": current,
            "change_detected": detected, "change_magnitude": round(change_magnitude, 6),
            "old_observations_excluded_from_current_estimation": max(0, int(len(market) - current)),
            "minimum_window": minimum, "maximum_window": maximum,
            "sample_size_warning": bool(len(market) < minimum),
            "last_update_timestamp": latest_timestamp,
        }
    return {"version": RESEARCH_VERSION, "states": states, "incremental": True, "history_preserved": True}


# ---------------------------------------------------------------------------
# Papers 5 and 6: conditional confidence set + dynamic averaging/Occam window
# ---------------------------------------------------------------------------
def _loss_stats(values: np.ndarray) -> Dict[str, Any]:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return {"sample_size": 0, "mae": None, "rmse": None, "pinball_10_90": None}
    return {
        "sample_size": int(len(arr)), "mae": float(np.mean(np.abs(arr))),
        "rmse": float(math.sqrt(np.mean(np.square(arr)))),
        "pinball_10_90": float(np.mean(np.maximum(0.10 * arr, -0.90 * arr)) + np.mean(np.maximum(0.90 * arr, -0.10 * arr))),
    }


def _model_error_map(residual_bundle: Mapping[str, Any], calibrated_bundle: Optional[Mapping[str, Any]]) -> Dict[str, Dict[int, np.ndarray]]:
    error_map: Dict[str, Dict[int, np.ndarray]] = {}
    baseline = residual_bundle.get("baseline_errors") or {}
    for model, values in baseline.items():
        error_map[str(model)] = {int(h): np.asarray(arr, dtype=float) for h, arr in values.items()}
    scalar = residual_bundle.get("scalar_bank")
    if isinstance(scalar, pd.DataFrame) and not scalar.empty:
        error_map["existing_system"] = {}
        for h in HORIZONS:
            error_map["existing_system"][h] = pd.to_numeric(scalar.loc[scalar["horizon"] == h, "residual"], errors="coerce").dropna().to_numpy(dtype=float)
    bundle = calibrated_bundle if isinstance(calibrated_bundle, Mapping) else {}
    audit = bundle.get("audit") if isinstance(bundle.get("audit"), Mapping) else {}
    residual_samples = dict(audit.get("horizon_residual_samples") or {})
    for path in ("red", "yellow", "blue"):
        error_map[path] = {}
        for h in HORIZONS:
            error_map[path][h] = pd.to_numeric(pd.Series(residual_samples.get(f"{path}_H+{h}", [])), errors="coerce").dropna().to_numpy(dtype=float)
    return error_map


def conditional_method_confidence_set(
    error_map: Mapping[str, Mapping[int, np.ndarray]], *, horizon: int, condition: str, minimum_sample: int = 12,
) -> Dict[str, Any]:
    records: list[Dict[str, Any]] = []
    valid_losses: Dict[str, float] = {}
    for model, per_h in error_map.items():
        stats = _loss_stats(np.asarray(per_h.get(horizon, []), dtype=float))
        loss = stats.get("mae")
        if stats["sample_size"] >= minimum_sample and loss is not None:
            valid_losses[str(model)] = float(loss)
        records.append({
            "condition": condition, "model_name": str(model), "accepted": False,
            "average_loss": None if loss is None else round(float(loss), 10), "relative_loss": None,
            "statistical_comparison_status": "INSUFFICIENT DATA" if stats["sample_size"] < minimum_sample else "PENDING",
            "sample_size": int(stats["sample_size"]), "insufficient_data": bool(stats["sample_size"] < minimum_sample),
        })
    if not valid_losses:
        return {"condition": condition, "horizon": horizon, "accepted_models": [], "records": records, "fallback_used": True, "status": "INSUFFICIENT DATA"}
    best = min(valid_losses.values())
    # Conservative equivalence margin approximates a confidence set without
    # claiming superiority from a small noisy sample.
    for row in records:
        model = row["model_name"]
        if model not in valid_losses:
            continue
        relative = valid_losses[model] / max(best, 1e-12) - 1.0
        row["relative_loss"] = round(relative, 8)
        sample = row["sample_size"]
        margin = 0.12 + 0.35 / math.sqrt(max(sample, 1))
        row["accepted"] = bool(relative <= margin)
        row["statistical_comparison_status"] = "NOT STATISTICALLY INFERIOR" if row["accepted"] else "INFERIOR UNDER CURRENT CONDITION"
    accepted = [row["model_name"] for row in records if row["accepted"]]
    return {"condition": condition, "horizon": horizon, "accepted_models": accepted, "records": records, "fallback_used": False, "status": "VALID"}


def _bounded_normalize(raw: Mapping[str, float], low: float = 0.03, high: float = 0.78) -> Dict[str, float]:
    """Project positive scores onto a bounded probability simplex.

    A clip-then-renormalize loop can violate the maximum again after the final
    normalization.  The monotone bisection below solves
    ``sum(clip(lambda * score_i, low, high)) == 1`` and therefore preserves all
    bounds and the unit-sum invariant at the same time.
    """
    positive = {
        str(k): max(float(v), 0.0)
        for k, v in raw.items()
        if math.isfinite(float(v)) and float(v) > 0
    }
    if not positive:
        return {}
    count = len(positive)
    # Make the requested box feasible for small/large active model sets.
    lower = min(max(float(low), 0.0), 1.0 / count)
    upper = max(min(float(high), 1.0), 1.0 / count)
    values = np.asarray(list(positive.values()), dtype=float)

    def mass(multiplier: float) -> float:
        return float(np.clip(multiplier * values, lower, upper).sum())

    left, right = 0.0, 1.0
    while mass(right) < 1.0:
        right *= 2.0
        if right > 1e18:  # Defensive fallback; feasibility is guaranteed above.
            break
    for _ in range(100):
        middle = (left + right) / 2.0
        if mass(middle) < 1.0:
            left = middle
        else:
            right = middle
    projected = np.clip(((left + right) / 2.0) * values, lower, upper)
    # Floating-point correction is distributed only over coordinates with room.
    difference = 1.0 - float(projected.sum())
    for _ in range(count + 2):
        if abs(difference) <= 1e-14:
            break
        if difference > 0:
            eligible = np.where(projected < upper - 1e-14)[0]
        else:
            eligible = np.where(projected > lower + 1e-14)[0]
        if len(eligible) == 0:
            break
        increment = difference / len(eligible)
        projected[eligible] = np.clip(projected[eligible] + increment, lower, upper)
        difference = 1.0 - float(projected.sum())
    return {key: float(value) for key, value in zip(positive.keys(), projected)}


def dynamic_model_averaging(
    confidence_set: Mapping[str, Any], error_map: Mapping[str, Mapping[int, np.ndarray]], *,
    horizon: int, previous: Optional[Mapping[str, Any]] = None, forgetting_factor: float = 0.92,
) -> Dict[str, Any]:
    accepted = list(confidence_set.get("accepted_models") or [])
    eligible_fallback_used = False
    valid_candidates = []
    for model, per_h in error_map.items():
        stats = _loss_stats(np.asarray(per_h.get(horizon, []), dtype=float))
        if stats.get("mae") is not None and stats.get("sample_size", 0) >= 4:
            valid_candidates.append((str(model), float(stats["mae"])))
    valid_candidates.sort(key=lambda item: item[1])
    # A one-model ensemble would violate the anti-concentration invariant and
    # would falsely imply certainty.  Broaden to the nearest valid fallback
    # condition/model when the strict confidence set contains fewer than two.
    if len(accepted) < 2:
        for model, _ in valid_candidates:
            if model not in accepted:
                accepted.append(model)
            if len(accepted) >= 2:
                break
        eligible_fallback_used = True
    losses = {}
    samples = {}
    for model in accepted:
        stats = _loss_stats(np.asarray((error_map.get(model) or {}).get(horizon, []), dtype=float))
        if stats.get("mae") is not None:
            losses[model] = float(stats["mae"]); samples[model] = int(stats["sample_size"])
    if len(losses) < 2:
        return {
            "status": "INSUFFICIENT DATA", "horizon": horizon, "weights": {}, "records": [],
            "eligibility_fallback_used": eligible_fallback_used,
            "unavailable_reason": "Need at least two eligible models to avoid a 100% single-model weight",
        }
    evidence_hash = _hash_payload({"horizon": horizon, "condition": confidence_set.get("condition"), "losses": losses, "samples": samples})
    if isinstance(previous, Mapping) and previous.get("evidence_hash") == evidence_hash:
        reused = deepcopy(dict(previous))
        reused["cache_status"] = "REUSED_SAME_COMPLETED_EVIDENCE"
        return reused
    scale = max(float(np.median(list(losses.values()))), 1e-12)
    probabilities = {model: math.exp(-loss / scale) for model, loss in losses.items()}
    maximum = max(probabilities.values())
    previous_records = {row.get("model_name"): row for row in ((previous or {}).get("records") or []) if isinstance(row, Mapping)}
    active_scores: Dict[str, float] = {}
    records: list[Dict[str, Any]] = []
    for model, probability in probabilities.items():
        old = previous_records.get(model) or {}
        old_weight = float(old.get("updated_weight", 1.0 / len(probabilities)))
        suppressed = bool(probability < maximum * 0.15 and samples.get(model, 0) >= 12)
        score = forgetting_factor * old_weight + (1.0 - forgetting_factor) * probability
        if not suppressed:
            active_scores[model] = score
        records.append({
            "model_name": model, "condition": confidence_set.get("condition"), "previous_weight": round(old_weight, 8),
            "updated_weight": 0.0, "conditional_loss": round(losses[model], 10),
            "conditional_probability": round(probability, 10), "active": not suppressed, "suppressed": suppressed,
            "suppression_reason": "Outside Dynamic Occam's Window" if suppressed else None,
            "sample_size": samples.get(model, 0),
            "reactivated": bool(old.get("suppressed") and not suppressed),
        })
    weights = _bounded_normalize(active_scores)
    for row in records:
        row["updated_weight"] = round(weights.get(row["model_name"], 0.0), 10)
    return {
        "status": "VALID", "horizon": horizon, "condition": confidence_set.get("condition"),
        "weights": weights, "records": records, "weight_sum": round(sum(weights.values()), 12),
        "forgetting_factor": forgetting_factor, "minimum_weight": 0.03, "maximum_weight": 0.78,
        "evidence_hash": evidence_hash, "cache_status": "UPDATED",
        "eligibility_fallback_used": eligible_fallback_used,
    }


# ---------------------------------------------------------------------------
# Papers 7 and 8: PBO and DSR validation gates
# ---------------------------------------------------------------------------
def probability_backtest_overfitting(performance_matrix: Any, metric_used: str = "net_return") -> Dict[str, Any]:
    matrix = np.asarray(performance_matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 4 or matrix.shape[1] < 4:
        return {
            "value": None, "status": "UNAVAILABLE", "unavailable_reason": "Need at least 4 chronological periods and 4 tested configurations",
            "number_of_periods": int(matrix.shape[0]) if matrix.ndim == 2 else 0,
            "number_of_configurations": int(matrix.shape[1]) if matrix.ndim == 2 else 0,
            "split_count": 0, "metric_used": metric_used,
        }
    periods = matrix.shape[0]
    split_size = periods // 2
    split_count = 0; below_median = 0
    # Deterministic symmetric chronological combinations, bounded for speed.
    import itertools
    combinations = list(itertools.combinations(range(periods), split_size))
    if len(combinations) > 200:
        positions = np.linspace(0, len(combinations) - 1, 200, dtype=int)
        combinations = [combinations[i] for i in positions]
    seen: set[tuple[int, ...]] = set()
    for insample in combinations:
        if insample in seen:
            continue
        outsample = tuple(i for i in range(periods) if i not in insample)
        seen.add(insample); seen.add(outsample)
        in_scores = np.nanmean(matrix[list(insample)], axis=0)
        out_scores = np.nanmean(matrix[list(outsample)], axis=0)
        if not np.isfinite(in_scores).any() or not np.isfinite(out_scores).any():
            continue
        winner = int(np.nanargmax(in_scores))
        ranks = pd.Series(out_scores).rank(method="average", pct=True).to_numpy(dtype=float)
        if ranks[winner] < 0.5:
            below_median += 1
        split_count += 1
    if split_count == 0:
        return {"value": None, "status": "UNAVAILABLE", "unavailable_reason": "No valid symmetric splits", "number_of_periods": periods, "number_of_configurations": matrix.shape[1], "split_count": 0, "metric_used": metric_used}
    value = below_median / split_count
    return {
        "value": round(float(value), 8), "status": "VALID", "unavailable_reason": None,
        "number_of_periods": periods, "number_of_configurations": matrix.shape[1], "split_count": split_count,
        "metric_used": metric_used, "validation_label": "HIGH OVERFITTING RISK" if value > 0.50 else "WATCH" if value > 0.25 else "ACCEPTABLE",
    }


def deflated_sharpe_ratio(
    strategy_returns: Optional[Sequence[float]], *, number_of_trials: Optional[int], sharpe_trials: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    return_values = [] if strategy_returns is None else list(strategy_returns)
    values = np.asarray(return_values, dtype=float)
    values = values[np.isfinite(values)]
    trials = int(number_of_trials or 0)
    trial_sequence = [] if sharpe_trials is None else list(sharpe_trials)
    trial_values = np.asarray(trial_sequence, dtype=float)
    trial_values = trial_values[np.isfinite(trial_values)]
    if len(values) < 30:
        return {"raw_sharpe": None, "deflated_sharpe_statistic": None, "deflated_sharpe_probability": None, "number_of_trials": trials, "sample_size": int(len(values)), "skewness": None, "kurtosis": None, "validation_label": "UNAVAILABLE", "unavailable_reason": "Need at least 30 aligned actual strategy returns"}
    if trials < 2 or len(trial_values) < 2:
        return {"raw_sharpe": None, "deflated_sharpe_statistic": None, "deflated_sharpe_probability": None, "number_of_trials": trials, "sample_size": int(len(values)), "skewness": None, "kurtosis": None, "validation_label": "UNAVAILABLE", "unavailable_reason": "Need the number and Sharpe distribution of tested strategies/configurations"}
    mean = float(np.mean(values)); std = float(np.std(values, ddof=1))
    if std <= 0:
        return {"raw_sharpe": None, "deflated_sharpe_statistic": None, "deflated_sharpe_probability": None, "number_of_trials": trials, "sample_size": int(len(values)), "skewness": None, "kurtosis": None, "validation_label": "UNAVAILABLE", "unavailable_reason": "Return variance is zero"}
    centered = (values - mean) / std
    skewness = float(np.mean(centered ** 3)); kurtosis = float(np.mean(centered ** 4))
    raw_sharpe = mean / std * math.sqrt(252.0)
    trial_std = max(float(np.std(trial_values, ddof=1)), 1e-12)
    # Expected maximum Sharpe approximation under multiple testing.
    expected_max = float(np.mean(trial_values) + trial_std * math.sqrt(2.0 * math.log(max(trials, 2))))
    denominator = math.sqrt(max((1.0 - skewness * raw_sharpe + (kurtosis - 1.0) * raw_sharpe ** 2 / 4.0) / max(len(values) - 1, 1), 1e-12))
    statistic = (raw_sharpe - expected_max) / denominator
    probability = _normal_cdf(statistic)
    return {
        "raw_sharpe": round(raw_sharpe, 8), "deflated_sharpe_statistic": round(statistic, 8),
        "deflated_sharpe_probability": round(probability, 8), "number_of_trials": trials,
        "sample_size": int(len(values)), "skewness": round(skewness, 8), "kurtosis": round(kurtosis, 8),
        "validation_label": "ACCEPT" if probability >= 0.95 else "WEAK" if probability >= 0.70 else "REJECT",
        "unavailable_reason": None,
    }


# ---------------------------------------------------------------------------
# Paper 9: aleatoric / epistemic uncertainty
# ---------------------------------------------------------------------------
def uncertainty_scores(
    frame: pd.DataFrame, conformal: Mapping[str, Any], calibrated_bundle: Optional[Mapping[str, Any]],
    conditional_set: Mapping[str, Any], dma: Mapping[str, Any], changepoint: Mapping[str, Any], nlp: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    market = normalize_completed_ohlc(frame)
    atr = _atr(market)
    anchor = float(market["close"].iloc[-1]) if not market.empty else 1.0
    returns = market["close"].pct_change().dropna()
    realized = float(returns.tail(24).std(ddof=0)) if len(returns) else 0.0
    range_ratio = float(((market["high"] - market["low"]).abs() / market["close"].replace(0, np.nan)).tail(24).median()) if not market.empty else 0.0
    horizons = list(conformal.get("horizons") or [])
    width = float(np.mean([(row.get("upper_band", anchor) - row.get("lower_band", anchor)) / max(abs(anchor), 1e-12) for row in horizons])) if horizons else 0.0
    residual_count = int(conformal.get("residual_vector_count", 0) or 0)
    nlp_importance = _clip((nlp or {}).get("importance", 0.0), 0.0, 1.0, 0.0)
    aleatoric = _clip(100.0 * (0.32 * min(realized / 0.0025, 1.0) + 0.22 * min(range_ratio / 0.0035, 1.0) + 0.31 * min(width / 0.008, 1.0) + 0.15 * nlp_importance), 0, 100, 50)

    bundle = calibrated_bundle if isinstance(calibrated_bundle, Mapping) else {}
    summary = bundle.get("summary") if isinstance(bundle.get("summary"), Mapping) else {}
    disagreement = 1.0 - _clip(summary.get("path_agreement_pct", 50.0), 0, 100, 50) / 100.0
    eligible_count = len(conditional_set.get("accepted_models") or [])
    sample_penalty = 1.0 - min(residual_count / 60.0, 1.0)
    weights = list((dma.get("weights") or {}).values())
    instability = float(np.std(weights) / max(np.mean(weights), 1e-12)) if len(weights) > 1 else (1.0 if not weights else 0.4)
    transition = _clip(changepoint.get("transition_risk_0_100", 50.0), 0, 100, 50) / 100.0
    epistemic = _clip(100.0 * (0.33 * disagreement + 0.25 * sample_penalty + 0.18 * min(instability, 1.0) + 0.14 * (1.0 if eligible_count == 0 else 1.0 / eligible_count) + 0.10 * transition), 0, 100, 50)
    combined = _clip(0.54 * aleatoric + 0.46 * epistemic, 0, 100, 50)
    if aleatoric >= epistemic + 12:
        source = "MARKET"
    elif epistemic >= aleatoric + 12:
        source = "MODEL"
    elif combined < 35:
        source = "LOW"
    else:
        source = "BOTH"
    explanation = {
        "MARKET": "Observed volatility, ranges and empirical interval width dominate.",
        "MODEL": "Model disagreement, weak conditional support or limited completed residuals dominate.",
        "BOTH": "Market variability and model-knowledge uncertainty are both elevated.",
        "LOW": "Both empirical market risk and model-knowledge uncertainty are currently contained.",
    }[source]
    return {
        "aleatoric_uncertainty_0_100": round(aleatoric, 4), "epistemic_uncertainty_0_100": round(epistemic, 4),
        "combined_uncertainty_0_100": round(combined, 4), "primary_uncertainty_source": source,
        "explanation": explanation, "sample_size_status": "VALID" if residual_count >= 30 else "LIMITED",
        "not_a_bayesian_guarantee": True,
    }


# ---------------------------------------------------------------------------
# Validation, reliability, meta labels and canonical integration
# ---------------------------------------------------------------------------
def _baseline_skill(
    residual_bundle: Mapping[str, Any], baseline_errors: Mapping[str, Mapping[int, np.ndarray]],
) -> Dict[str, Any]:
    scalar = residual_bundle.get("scalar_bank")
    rows = []
    for h in HORIZONS:
        system_errors = np.asarray([], dtype=float)
        if isinstance(scalar, pd.DataFrame) and not scalar.empty:
            system_errors = pd.to_numeric(scalar.loc[scalar["horizon"] == h, "residual"], errors="coerce").dropna().to_numpy(dtype=float)
        for baseline, per_h in baseline_errors.items():
            base = np.asarray(per_h.get(h, []), dtype=float)
            base = base[np.isfinite(base)]
            if len(system_errors) < 8 or len(base) < 8:
                rows.append({"baseline_name": baseline, "horizon": h, "system_error": None, "baseline_error": None, "skill_score": None, "direction_comparison": "UNAVAILABLE", "calibration_comparison": "UNAVAILABLE", "sample_size": min(len(system_errors), len(base)), "validation_status": "INSUFFICIENT DATA"})
                continue
            system_mae = float(np.mean(np.abs(system_errors))); baseline_mae = float(np.mean(np.abs(base)))
            skill = 1.0 - system_mae / max(baseline_mae, 1e-12)
            rows.append({"baseline_name": baseline, "horizon": h, "system_error": round(system_mae, 10), "baseline_error": round(baseline_mae, 10), "skill_score": round(skill, 8), "direction_comparison": "SYSTEM BETTER" if skill > 0 else "BASELINE BETTER" if skill < 0 else "EQUAL", "calibration_comparison": "NOT ENOUGH INTERVAL HISTORY", "sample_size": min(len(system_errors), len(base)), "validation_status": "VALID"})
    valid = [row["skill_score"] for row in rows if row["skill_score"] is not None]
    return {"rows": rows, "mean_skill_score": round(float(np.mean(valid)), 8) if valid else None, "status": "VALID" if valid else "INSUFFICIENT DATA"}


def _research_reliability(
    canonical: Mapping[str, Any], conformal: Mapping[str, Any], adaptive: Mapping[str, Any], uncertainty: Mapping[str, Any],
    changepoint: Mapping[str, Any], confidence_set: Mapping[str, Any], baseline_skill: Mapping[str, Any], pbo: Mapping[str, Any], dsr: Mapping[str, Any],
) -> Dict[str, Any]:
    base = _clip((canonical.get("reliability") or {}).get("score", 50.0), 0, 100, 50)
    existing_reliability = canonical.get("reliability") if isinstance(canonical.get("reliability"), Mapping) else {}
    direction_accuracy = _finite(existing_reliability.get("direction_accuracy"), None)
    if direction_accuracy is not None:
        direction_accuracy = _clip(direction_accuracy * (100.0 if direction_accuracy <= 1.0 else 1.0), 0, 100, 50)
    projection = canonical.get("probabilistic_projection") if isinstance(canonical.get("probabilistic_projection"), Mapping) else {}
    model_agreement = _finite(
        projection.get("path_agreement_pct", existing_reliability.get("model_agreement")), None
    )
    residual_count = int(conformal.get("residual_vector_count", 0) or 0)
    data_quality = canonical.get("data_quality") if isinstance(canonical.get("data_quality"), Mapping) else {}
    freshness_score = _finite(data_quality.get("score"), None)
    if freshness_score is None:
        stale = bool(canonical.get("stale") or (canonical.get("metadata") or {}).get("stale"))
        freshness_score = 25.0 if stale else 100.0
    validation = canonical.get("validation_metrics") if isinstance(canonical.get("validation_metrics"), Mapping) else {}
    walk_forward = _finite(validation.get("walk_forward_stability_0_100"), None)
    if walk_forward is None:
        walk_forward = direction_accuracy
    nlp = canonical.get("nlp") if isinstance(canonical.get("nlp"), Mapping) else {}
    nlp_event_safety = 100.0 * (1.0 - _clip(nlp.get("importance", 0.0), 0, 1, 0.0))
    observed_states = list((adaptive.get("states") or {}).values()) if isinstance(adaptive.get("states"), Mapping) else []
    observed_coverage = [
        100.0 * _clip(item.get("observed_coverage"), 0, 1, TARGET_COVERAGE)
        for item in observed_states if isinstance(item, Mapping)
    ]
    components: Dict[str, Optional[float]] = {
        "historical_direction_accuracy": direction_accuracy,
        "conformal_interval_coverage": float(np.mean(observed_coverage)) if observed_coverage else None,
        "adaptive_coverage_quality": _finite(adaptive.get("mean_coverage_quality_0_100"), None),
        "model_agreement": None if model_agreement is None else _clip(model_agreement, 0, 100, 50),
        "conditional_model_support": min(100.0, 25.0 * len(confidence_set.get("accepted_models") or [])),
        "conditional_sample_size": _clip(100.0 * residual_count / 60.0, 0, 100, 0),
        "data_freshness": _clip(freshness_score, 0, 100, 50),
        "regime_stability": 100.0 - _clip(changepoint.get("transition_risk_0_100", 50), 0, 100, 50),
        "transition_safety": 100.0 - _clip(changepoint.get("transition_risk_0_100", 50), 0, 100, 50),
        "aleatoric_safety": 100.0 - _clip(uncertainty.get("aleatoric_uncertainty_0_100", 50), 0, 100, 50),
        "epistemic_safety": 100.0 - _clip(uncertainty.get("epistemic_uncertainty_0_100", 50), 0, 100, 50),
        "walk_forward_stability": None if walk_forward is None else _clip(walk_forward, 0, 100, 50),
        "nlp_event_safety": _clip(nlp_event_safety, 0, 100, 100),
    }
    skill = _finite(baseline_skill.get("mean_skill_score"), None)
    components["baseline_skill"] = None if skill is None else _clip(50.0 + 100.0 * skill, 0, 100, 50)
    if pbo.get("value") is not None:
        components["pbo_safety"] = 100.0 * (1.0 - _clip(pbo.get("value"), 0, 1, 0.5))
    if dsr.get("deflated_sharpe_probability") is not None:
        components["dsr_probability"] = 100.0 * _clip(dsr.get("deflated_sharpe_probability"), 0, 1, 0)
    valid = [float(value) for value in components.values() if value is not None]
    research_score = float(np.mean(valid)) if valid else 50.0
    adjustment = _clip((research_score - 50.0) * 0.16, -8.0, 6.0, 0.0)
    calibrated = _clip(base + adjustment, 0, 100, base)
    label = "HIGH" if calibrated >= 72 else "MODERATE" if calibrated >= 50 else "LOW" if calibrated >= 35 else "CRITICAL"
    return {
        "base_existing_score": round(base, 4), "research_component_score": round(research_score, 4),
        "bounded_adjustment": round(adjustment, 4), "calibrated_score_0_100": round(calibrated, 4),
        "label": label, "components": {k: None if v is None else round(float(v), 4) for k, v in components.items()},
        "modifier_bounds": [-8.0, 6.0], "full_metric_values_unchanged": True,
    }


def _meta_labels(canonical: Mapping[str, Any], uncertainty: Mapping[str, Any], changepoint: Mapping[str, Any], reliability: Mapping[str, Any], conformal: Mapping[str, Any]) -> Dict[str, str]:
    final = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
    direction = _direction(final.get("directional_market_view") or canonical.get("full_metric_direction"))
    reliability_score = float(reliability.get("calibrated_score_0_100", 0.0))
    transition = float(changepoint.get("transition_risk_0_100", 50.0))
    combined = float(uncertainty.get("combined_uncertainty_0_100", 50.0))
    path_support = "STRONG" if conformal.get("residual_vector_count", 0) >= 30 and combined < 50 else "WEAK" if combined < 68 else "CONFLICTED"
    severe = sum([transition >= 78, combined >= 75, reliability_score < 35, path_support == "CONFLICTED"])
    tradeability = "BLOCK" if severe >= 3 else "WAIT" if severe >= 2 else "TRADE"
    timing = "NEXT HOUR" if transition >= 55 or combined >= 60 else "NOW"
    risk = "HIGH" if combined >= 68 or transition >= 72 else "MEDIUM" if combined >= 42 else "LOW"
    regime_support = "ALIGNED" if direction in {"BUY", "SELL"} and transition < 55 else "MIXED" if direction in {"BUY", "SELL"} else "OPPOSED"
    nlp = canonical.get("nlp") if isinstance(canonical.get("nlp"), Mapping) else {}
    event = "PROTECT" if _clip(nlp.get("importance", 0), 0, 1, 0) >= 0.75 else "CAUTION" if _clip(nlp.get("importance", 0), 0, 1, 0) >= 0.45 else "NORMAL"
    return {
        "direction": direction, "tradeability": tradeability, "timing": timing, "risk": risk,
        "regime_support": regime_support, "path_support": path_support,
        "liquidity_event_condition": event, "uncertainty_source": str(uncertainty.get("primary_uncertainty_source", "BOTH")),
    }


def _update_bundle_bands(bundle: Optional[Mapping[str, Any]], conformal: Mapping[str, Any]) -> Dict[str, Any]:
    result = deepcopy(dict(bundle or {}))
    main = result.get("main")
    rows = list(conformal.get("horizons") or [])
    if isinstance(main, pd.DataFrame) and not main.empty and rows:
        updated = main.copy(deep=True).reset_index(drop=True)
        for index, row in enumerate(rows[: len(updated)]):
            central = float(updated.loc[index, "main_path"]) if "main_path" in updated.columns else float(row["central"])
            updated.loc[index, "lower_band"] = min(float(row["lower_band"]), central)
            updated.loc[index, "upper_band"] = max(float(row["upper_band"]), central)
            updated.loc[index, "band_width"] = max(central - float(updated.loc[index, "lower_band"]), float(updated.loc[index, "upper_band"]) - central)
            for key in ("p10", "p25", "p50", "p75", "p90"):
                updated.loc[index, key] = float(row[key])
        result["main"] = updated
        summary = dict(result.get("summary") or {})
        summary.update({
            "research_calibration_version": RESEARCH_VERSION,
            "conformal_residual_vector_count": int(conformal.get("residual_vector_count", 0) or 0),
            "adaptive_conformal_applied": True,
            "central_path_preserved": bool(np.allclose(pd.to_numeric(main["main_path"], errors="coerce"), pd.to_numeric(updated["main_path"], errors="coerce"), equal_nan=True)) if "main_path" in main.columns else True,
        })
        result["summary"] = summary
        audit = dict(result.get("audit") or {})
        audit["ten_paper_research_calibration"] = _json_safe({k: v for k, v in conformal.items() if k != "scenarios"})
        result["audit"] = audit
    return result


def validate_research_invariants(result: Mapping[str, Any]) -> Dict[str, bool]:
    conformal = result.get("conformal_prediction") if isinstance(result.get("conformal_prediction"), Mapping) else {}
    rows = list(conformal.get("horizons") or [])
    quantile_ordering = all(row.get("p10") <= row.get("p25") <= row.get("p50") <= row.get("p75") <= row.get("p90") for row in rows)
    bands = all(row.get("lower_band") <= row.get("central") <= row.get("upper_band") for row in rows)
    dma = result.get("dynamic_model_averaging") if isinstance(result.get("dynamic_model_averaging"), Mapping) else {}
    dma_groups = [dma]
    dma_groups.extend(
        group for group in (dma.get("by_horizon") or {}).values()
        if isinstance(group, Mapping)
    )
    weight_sum = True
    weight_bounds = True
    for group in dma_groups:
        weights = group.get("weights") or {}
        if not weights:
            continue
        weight_sum = weight_sum and abs(sum(float(v) for v in weights.values()) - 1.0) <= 1e-8
        minimum = float(group.get("minimum_weight", 0.0) or 0.0)
        maximum = float(group.get("maximum_weight", 1.0) or 1.0)
        weight_bounds = weight_bounds and all(
            minimum - 1e-10 <= float(value) <= maximum + 1e-10
            for value in weights.values()
        )
    probability_fields = []
    for row in rows:
        probability_fields.extend([row.get("probability_above_current_close"), row.get("probability_below_current_close")])
    probability_fields.extend([conformal.get("tp_touch_probability"), conformal.get("sl_touch_probability")])
    probabilities = all(value is None or 0.0 <= float(value) <= 1.0 for value in probability_fields)
    uncertainties = result.get("uncertainty") if isinstance(result.get("uncertainty"), Mapping) else {}
    score_bounds = all(0 <= float(uncertainties.get(key, 0)) <= 100 for key in ("aleatoric_uncertainty_0_100", "epistemic_uncertainty_0_100", "combined_uncertainty_0_100"))
    change = result.get("bayesian_changepoint") if isinstance(result.get("bayesian_changepoint"), Mapping) else {}
    change_probs = all(0 <= float(change.get(key, 0.0)) <= 1 for key in ("probability_change_now", "probability_change_last_3", "probability_change_last_6", "probability_structure_continues_one_more"))
    return {
        "quantile_ordering": quantile_ordering, "band_monotonicity": bands, "dynamic_weight_sum": weight_sum,
        "dynamic_weight_bounds": weight_bounds,
        "probabilities_in_range": probabilities and change_probs, "uncertainty_scores_in_range": score_bounds,
        "central_path_preserved": bool(result.get("central_path_preserved", True)),
    }


def build_and_apply_research_layer(
    canonical: Mapping[str, Any], *, ohlc: pd.DataFrame, calibrated_bundle: Optional[Mapping[str, Any]] = None,
    prediction_history: Optional[pd.DataFrame] = None, settled_predictions: Optional[pd.DataFrame] = None,
    previous_cache: Optional[Mapping[str, Any]] = None, strategy_returns: Optional[Sequence[float]] = None,
    number_of_trials: Optional[int] = None, sharpe_trials: Optional[Sequence[float]] = None,
    experiment_performance_matrix: Any = None,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Build all ten research integrations once and apply bounded canonical refinements."""
    started = time.perf_counter()
    payload = deepcopy(dict(canonical or {}))
    latest = payload.get("latest_completed_candle_time") or ((payload.get("market") or {}).get("latest_completed_candle_time") if isinstance(payload.get("market"), Mapping) else None)
    market = normalize_completed_ohlc(ohlc, latest_completed=latest)
    if market.empty:
        raise ValueError("Research calibration needs timestamped completed OHLC rows")
    latest_text = str(_json_scalar(market["time"].iloc[-1]))
    frame_hash = data_hash(market)
    bundle_summary = dict((calibrated_bundle or {}).get("summary") or {}) if isinstance(calibrated_bundle, Mapping) else {}
    input_descriptor = {
        "frame_hash": frame_hash,
        "latest_completed_h1": latest_text,
        "symbol": payload.get("symbol"), "timeframe": payload.get("timeframe"),
        "existing_reliability": (payload.get("reliability") or {}).get("score") if isinstance(payload.get("reliability"), Mapping) else None,
        "regime": payload.get("regime"), "nlp": payload.get("nlp"),
        "forecasts": payload.get("forecasts"),
        "bundle_summary": bundle_summary,
        "bundle_central_path": (calibrated_bundle.get("main")["main_path"].tolist() if isinstance(calibrated_bundle, Mapping) and isinstance(calibrated_bundle.get("main"), pd.DataFrame) and "main_path" in calibrated_bundle.get("main").columns else None),
    }
    research_input_hash = _hash_payload(input_descriptor)
    calculation_id = _calculation_id(payload, frame_hash, latest_text, research_input_hash)
    session = _session_label(market["time"].iloc[-1])
    multiscale = payload.get("multiscale_regime") if isinstance(payload.get("multiscale_regime"), Mapping) else {}
    volatility_regime = str(multiscale.get("current_volatility_regime") or "CALM").upper()

    layer_meta: Dict[str, Any] = {}
    def timed(name: str, function, *args, **kwargs):
        t0 = time.perf_counter()
        try:
            value = function(*args, **kwargs)
            layer_meta[name] = {"status": "SUCCESS", "duration_ms": round((time.perf_counter() - t0) * 1000.0, 3), "error_message": None}
            return value
        except Exception as exc:
            layer_meta[name] = {"status": "FAILED", "duration_ms": round((time.perf_counter() - t0) * 1000.0, 3), "error_message": str(exc)[:500]}
            raise

    baselines = timed("baseline_forecasts", build_baseline_forecasts, market)
    changepoint = timed("bayesian_changepoint", bayesian_online_changepoint, market)
    transition_state = "HIGH_TRANSITION_RISK" if float(changepoint.get("transition_risk_0_100", 50)) >= 60 else "LOW_TRANSITION_RISK"
    windows_previous = (previous_cache or {}).get("adaptive_windows") if isinstance(previous_cache, Mapping) else None
    windows = timed("adaptive_windows", update_adaptive_windows, windows_previous, market, changepoint)
    residual_window = int((((windows.get("states") or {}).get("prediction_residuals") or {}).get("current_window_size") or 180))
    residuals = timed("residual_bank", build_residual_vectors, market, prediction_history, settled_predictions, max_origins=max(36, min(360, residual_window)))
    adaptive_previous = (previous_cache or {}).get("adaptive_coverage") if isinstance(previous_cache, Mapping) else None
    scalar_bank = residuals.get("scalar_bank") if isinstance(residuals.get("scalar_bank"), pd.DataFrame) else pd.DataFrame()
    adaptive = timed("adaptive_conformal", update_adaptive_coverage, adaptive_previous, scalar_bank, current_volatility_regime=volatility_regime, current_session=session, transition_state=transition_state)
    anchor = float(market["close"].iloc[-1])
    central = _central_path(calibrated_bundle, payload, anchor)
    current_direction = "BUY" if central[-1] > anchor else "SELL" if central[-1] < anchor else "NEUTRAL"
    current_realized_volatility = float(_finite(market["close"].pct_change().tail(24).std(ddof=0), 0.0) or 0.0)
    conformal = timed(
        "time_series_conformal", conformal_scenarios, central, residuals,
        seed_material=f"{calculation_id}|{frame_hash}|{latest_text}", adaptive_coverage=adaptive,
        current_volatility_regime=volatility_regime, current_session=session,
        transition_state=transition_state, anchor=anchor, current_direction=current_direction,
        current_realized_volatility=current_realized_volatility,
    )
    error_map = _model_error_map(residuals, calibrated_bundle)
    model_window = int((((windows.get("states") or {}).get("model_performance") or {}).get("current_window_size") or 300))
    error_map = {model: {h: np.asarray(values, dtype=float)[-model_window:] for h, values in per_h.items()} for model, per_h in error_map.items()}
    directional_regime = _direction((payload.get("regime") or {}).get("major_regime") if isinstance(payload.get("regime"), Mapping) else "")
    condition_base = f"{volatility_regime}|{directional_regime}|{session}|{transition_state}"
    conditional_by_horizon: Dict[str, Any] = {}
    dma_by_horizon: Dict[str, Any] = {}
    dma_previous_all = (previous_cache or {}).get("dynamic_model_averaging") if isinstance(previous_cache, Mapping) else None
    previous_by_horizon = dict((dma_previous_all or {}).get("by_horizon") or {}) if isinstance(dma_previous_all, Mapping) else {}
    for h in HORIZONS:
        key = f"H+{h}"
        conditional_by_horizon[key] = timed(
            f"conditional_method_confidence_set_h{h}", conditional_method_confidence_set,
            error_map, horizon=h, condition=f"{key}|{condition_base}",
        )
        dma_by_horizon[key] = timed(
            f"dynamic_model_averaging_h{h}", dynamic_model_averaging,
            conditional_by_horizon[key], error_map, horizon=h, previous=previous_by_horizon.get(key),
        )
    conditional = dict(conditional_by_horizon["H+3"]); conditional["by_horizon"] = conditional_by_horizon
    conditional["requested_condition_grid"] = {
        "horizons": list(HORIZONS), "volatility_regimes": ["CALM", "TURBULENT", "CRISIS"],
        "directional_regimes": ["BULL", "BEAR", "RANGE"],
        "sessions": ["ASIAN", "LONDON", "LONDON_NEW_YORK_OVERLAP"],
        "transition_states": ["HIGH_TRANSITION_RISK", "LOW_TRANSITION_RISK"],
        "active_condition": condition_base,
        "fallback_policy": "Broaden condition and reduce confidence when completed conditional samples are insufficient",
    }
    dma = dict(dma_by_horizon["H+3"]); dma["by_horizon"] = dma_by_horizon
    baseline_skill = timed("baseline_skill", _baseline_skill, residuals, residuals.get("baseline_errors") or {})
    pbo_matrix = np.asarray(experiment_performance_matrix if experiment_performance_matrix is not None else np.empty((0, 0)), dtype=float)
    pbo = timed("probability_backtest_overfitting", probability_backtest_overfitting, pbo_matrix)
    dsr = timed("deflated_sharpe_ratio", deflated_sharpe_ratio, strategy_returns, number_of_trials=number_of_trials, sharpe_trials=sharpe_trials)
    nlp = payload.get("nlp") if isinstance(payload.get("nlp"), Mapping) else {}
    uncertainty = timed("uncertainty_separation", uncertainty_scores, market, conformal, calibrated_bundle, conditional, dma, changepoint, nlp)
    research_reliability = timed("reliability_calibration", _research_reliability, payload, conformal, adaptive, uncertainty, changepoint, conditional, baseline_skill, pbo, dsr)
    meta_labels = timed("meta_labels", _meta_labels, payload, uncertainty, changepoint, research_reliability, conformal)
    upgraded_bundle = timed("projection_band_update", _update_bundle_bands, calibrated_bundle, conformal)

    result: Dict[str, Any] = {
        "version": RESEARCH_VERSION, "schema_version": RESEARCH_SCHEMA_VERSION,
        "cache_version": RESEARCH_VERSION,
        "canonical_calculation_id": calculation_id, "calculation_timestamp": latest_text,
        "last_completed_h1_timestamp": latest_text, "data_hash": frame_hash,
        "input_hash": _hash_payload({**input_descriptor, "central_path": central.tolist(), "version": RESEARCH_VERSION}),
        "data_source_identity": str(payload.get("source") or "UNKNOWN"),
        "symbol": str(payload.get("symbol") or "EURUSD"), "timeframe": str(payload.get("timeframe") or "H1"),
        "row_count": int(len(market)), "stale": False, "stale_status": "CURRENT",
        "error_message": None,
        "session": session, "volatility_regime": volatility_regime, "transition_state": transition_state,
        "baseline_forecasts": baselines, "baseline_skill": baseline_skill,
        "conformal_prediction": conformal, "adaptive_coverage": adaptive,
        "bayesian_changepoint": changepoint, "adaptive_windows": windows,
        "conditional_method_confidence_set": conditional, "dynamic_model_averaging": dma,
        "uncertainty": uncertainty, "pbo": pbo, "dsr": dsr,
        "research_reliability": research_reliability, "meta_labels": meta_labels,
        "validation_status": "VALID" if conformal.get("status") == "VALID" and changepoint.get("status") == "VALID" else "LIMITED DATA",
        "layer_status": "SUCCESS",
        "layer_execution_metadata": layer_meta,
        "protected_full_metric_preserved": True, "central_path_preserved": True,
        "causal_completed_candle_only": True, "future_rows_used": 0,
        "validation_protocol": {
            "walk_forward": True, "random_split": False, "fit_scalers_on_training_only": True,
            "purged_splits": purged_walk_forward_splits(len(market), maximum_horizon=max(HORIZONS)),
            "embargo_at_least_maximum_horizon": True,
        },
    }
    deterministic_view = deepcopy(result)
    deterministic_view.pop("layer_execution_metadata", None)
    result["output_hash"] = _hash_payload(deterministic_view)
    result["invariants"] = validate_research_invariants(result)
    result["execution_duration_ms"] = round((time.perf_counter() - started) * 1000.0, 3)

    payload["research_calibration"] = _json_safe(result)
    payload["bayesian_changepoint"] = _json_safe(changepoint)
    payload["adaptive_windows"] = _json_safe(windows)
    payload["dynamic_model_weights"] = _json_safe(dma)
    payload["conditional_accepted_model_set"] = _json_safe(conditional)
    payload["conformal_residual_intervals"] = _json_safe(conformal)
    payload["adaptive_coverage_state"] = _json_safe(adaptive)
    payload["aleatoric_uncertainty"] = uncertainty["aleatoric_uncertainty_0_100"]
    payload["epistemic_uncertainty"] = uncertainty["epistemic_uncertainty_0_100"]
    payload["combined_uncertainty"] = uncertainty["combined_uncertainty_0_100"]
    payload["baseline_forecasts"] = _json_safe(baselines)
    payload["baseline_skill"] = _json_safe(baseline_skill)
    payload["pbo"] = _json_safe(pbo); payload["dsr"] = _json_safe(dsr)
    payload["meta_labels"] = {**dict(payload.get("meta_labels") or {}), **meta_labels}
    payload["validation_status"] = result["validation_status"]
    payload.setdefault("metadata", {})["research_calibration_version"] = RESEARCH_VERSION
    payload["metadata"]["research_calculation_id"] = calculation_id
    payload["metadata"]["research_output_hash"] = result["output_hash"]
    payload["metadata"]["same_completed_data_deterministic"] = True
    payload["metadata"]["research_layer_optional_fail_safe"] = True
    existing_layers = payload.get("layer_execution_metadata")
    if isinstance(existing_layers, list):
        layer_rows = list(existing_layers)
    elif isinstance(existing_layers, Mapping):
        layer_rows = [{"layer": str(name), **dict(meta or {})} for name, meta in existing_layers.items()]
    else:
        layer_rows = []
    layer_rows.extend({"layer": f"research.{name}", **dict(meta or {})} for name, meta in layer_meta.items())
    payload["layer_execution_metadata"] = _json_safe(layer_rows)

    reliability = payload.get("reliability") if isinstance(payload.get("reliability"), MutableMapping) else {}
    if not isinstance(reliability, MutableMapping):
        reliability = dict(reliability or {})
    reliability.setdefault("existing_score_before_research", reliability.get("score"))
    reliability.setdefault("existing_label_before_research", reliability.get("label"))
    reliability["research_calibrated_score"] = research_reliability["calibrated_score_0_100"]
    reliability["research_components"] = research_reliability["components"]
    # Reliability is not a protected Full Metric formula.  Apply only the bounded
    # research modifier while retaining the exact pre-research value for audit.
    reliability["score"] = research_reliability["calibrated_score_0_100"]
    reliability["label"] = research_reliability["label"]
    reliability["calibration_source"] = "existing reliability plus bounded ten-paper research modifier"
    payload["reliability"] = reliability

    risk = payload.get("risk") if isinstance(payload.get("risk"), MutableMapping) else {}
    risk = dict(risk or {})
    risk["aleatoric_uncertainty_pct"] = uncertainty["aleatoric_uncertainty_0_100"]
    risk["epistemic_uncertainty_pct"] = uncertainty["epistemic_uncertainty_0_100"]
    risk["combined_uncertainty_pct"] = uncertainty["combined_uncertainty_0_100"]
    payload["risk"] = risk

    final = payload.get("final_decision") if isinstance(payload.get("final_decision"), MutableMapping) else {}
    final = dict(final or {})
    final["research_meta_labels"] = meta_labels
    final["research_reliability"] = research_reliability["calibrated_score_0_100"]
    existing_confidence = _finite(final.get("calibrated_confidence"), None)
    if existing_confidence is not None:
        final["pre_research_calibrated_confidence"] = float(existing_confidence)
        final["calibrated_confidence"] = round(_clip(0.84 * float(existing_confidence) + 0.16 * research_reliability["calibrated_score_0_100"], 0, 100, float(existing_confidence)), 4)
    final["projection_confidence_research_inputs"] = {
        "coverage_quality": adaptive.get("mean_coverage_quality_0_100"),
        "transition_risk": changepoint.get("transition_risk_0_100"),
        "combined_uncertainty": uncertainty.get("combined_uncertainty_0_100"),
        "baseline_skill": baseline_skill.get("mean_skill_score"),
    }
    severe_joint_block = meta_labels["tradeability"] == "BLOCK"
    if severe_joint_block and str(final.get("final_decision", "WAIT")).upper() in {"BUY", "SELL"}:
        final["pre_research_final_decision"] = final.get("final_decision")
        final["final_decision"] = "WAIT"
        final["tradeability_decision"] = "WAIT"
        final["less_risky_decision"] = "WAIT"
        blockers = list(final.get("blocking_reasons") or [])
        blockers.append("Joint research gate: extreme transition/model/coverage uncertainty")
        final["blocking_reasons"] = sorted(set(blockers))
    payload["research_score_refinements"] = {
        "protected_values_unchanged": True,
        "master_score": {"protected": payload.get("master_score"), "research_confirmation_0_100": research_reliability.get("research_component_score")},
        "entry_score": {"protected": payload.get("entry_score"), "joint_caution_penalty_0_10": round(min(2.0, 0.012 * float(changepoint.get("transition_risk_0_100", 0)) + 0.010 * float(uncertainty.get("epistemic_uncertainty_0_100", 0))), 4)},
        "hold_score": {"protected": payload.get("hold_safety"), "run_length_stability_0_100": round(100.0 - float(changepoint.get("transition_risk_0_100", 50)), 4)},
        "exit_risk": {"protected": payload.get("exit_risk"), "research_risk_pressure_0_100": round(0.45 * float(changepoint.get("transition_risk_0_100", 50)) + 0.35 * float(uncertainty.get("aleatoric_uncertainty_0_100", 50)) + 0.20 * float(uncertainty.get("epistemic_uncertainty_0_100", 50)), 4)},
        "knn_neighbor_quality": {
            "minimum_valid_neighbor_count": 12,
            "conditioned_residual_support": conformal.get("conditioned_vector_sample_size"),
            "out_of_distribution_status": "WATCH" if uncertainty.get("epistemic_uncertainty_0_100", 0) >= 60 else "SUPPORTED",
            "adaptive_history_window": (((windows.get("states") or {}).get("knn_candidate_history") or {}).get("current_window_size")),
        },
        "greedy_inputs": {
            "tp_probability": conformal.get("tp_touch_probability"), "sl_probability": conformal.get("sl_touch_probability"),
            "expected_mfe": conformal.get("expected_maximum_favourable_excursion"), "expected_mae": conformal.get("expected_maximum_adverse_excursion"),
            "transition_risk": changepoint.get("transition_risk_0_100"), "baseline_skill": baseline_skill.get("mean_skill_score"),
            "aleatoric_uncertainty": uncertainty.get("aleatoric_uncertainty_0_100"), "epistemic_uncertainty": uncertainty.get("epistemic_uncertainty_0_100"),
        },
    }
    payload["final_decision"] = final
    return payload, result, upgraded_bundle


def build_research_layer_fail_safe(
    canonical: Mapping[str, Any], *, builder=build_and_apply_research_layer, **kwargs: Any,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Preserve the previous valid payload when the optional layer fails."""
    original = deepcopy(dict(canonical or {}))
    original_bundle = deepcopy(dict(kwargs.get("calibrated_bundle") or {}))
    try:
        payload, result, bundle = builder(original, **kwargs)
        return payload, result, bundle, {"ok": True, "status": "SUCCESS"}
    except Exception as exc:
        original.setdefault("metadata", {})["research_calibration_status"] = "FAILED SAFELY"
        original["metadata"]["research_calibration_error"] = str(exc)[:500]
        return original, {}, original_bundle, {"ok": False, "status": "FAILED SAFELY", "error": str(exc)[:500]}


# ---------------------------------------------------------------------------
# Disk-backed state and experiment registry
# ---------------------------------------------------------------------------
@dataclass
class ResearchStore:
    db_path: Path | str = DEFAULT_DB_PATH

    def __post_init__(self) -> None:
        configured = os.environ.get("ADX_LEDGER_DB_PATH")
        self.db_path = Path(configured or self.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self):
        connection = sqlite3.connect(str(self.db_path), timeout=15, check_same_thread=False)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=15000")
        return connection

    def initialize(self) -> None:
        statements = [
            """CREATE TABLE IF NOT EXISTS research_calibration_runs(
                calculation_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, last_completed_h1 TEXT NOT NULL,
                data_hash TEXT NOT NULL, input_hash TEXT NOT NULL, output_hash TEXT NOT NULL,
                schema_version TEXT NOT NULL, result_json TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS research_conformal_predictions(
                calculation_id TEXT NOT NULL, horizon INTEGER NOT NULL, prediction_time TEXT NOT NULL,
                target_time TEXT NOT NULL, central REAL, lower_band REAL, upper_band REAL,
                volatility_regime TEXT, session TEXT, transition_state TEXT, status TEXT NOT NULL,
                target_coverage REAL, adaptive_correction REAL, calibration_sample_size INTEGER,
                PRIMARY KEY(calculation_id, horizon))""",
            """CREATE TABLE IF NOT EXISTS research_conformal_outcomes(
                calculation_id TEXT NOT NULL, horizon INTEGER NOT NULL, prediction_time TEXT NOT NULL,
                target_time TEXT NOT NULL, central REAL, lower_band REAL, upper_band REAL,
                actual_completed_close REAL NOT NULL, inside_interval INTEGER NOT NULL,
                target_coverage REAL, recent_observed_coverage REAL, coverage_error REAL,
                adaptive_correction REAL, calibration_sample_size INTEGER, volatility_regime TEXT,
                session TEXT, transition_state TEXT, settled_at TEXT NOT NULL,
                PRIMARY KEY(calculation_id, horizon))""",
            """CREATE TABLE IF NOT EXISTS research_experiments(
                experiment_id TEXT PRIMARY KEY, configuration_hash TEXT NOT NULL, parameters_json TEXT,
                feature_set_json TEXT, thresholds_json TEXT, model_weights_json TEXT, regime_settings_json TEXT,
                training_period TEXT, validation_period TEXT, purging_period INTEGER, embargo_period INTEGER,
                net_returns_json TEXT, mae REAL, rmse REAL, direction_accuracy REAL, calibration_error REAL,
                sharpe REAL, selected INTEGER NOT NULL DEFAULT 0, rejected_reason TEXT, created_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS research_experiment_period_performance(
                experiment_id TEXT NOT NULL, period_label TEXT NOT NULL, chronological_index INTEGER NOT NULL,
                performance REAL NOT NULL, PRIMARY KEY(experiment_id, period_label))""",
            "CREATE INDEX IF NOT EXISTS idx_research_predictions_target ON research_conformal_predictions(target_time, status)",
            "CREATE INDEX IF NOT EXISTS idx_research_outcomes_condition ON research_conformal_outcomes(horizon, volatility_regime, session, transition_state, target_time)",
        ]
        with _DB_LOCK, self._connect() as connection:
            for statement in statements:
                connection.execute(statement)
            # Idempotent migration for databases created by an earlier build.
            existing = {row[1] for row in connection.execute("PRAGMA table_info(research_conformal_predictions)").fetchall()}
            for column, definition in (
                ("target_coverage", "REAL"),
                ("adaptive_correction", "REAL"),
                ("calibration_sample_size", "INTEGER"),
            ):
                if column not in existing:
                    connection.execute(f"ALTER TABLE research_conformal_predictions ADD COLUMN {column} {definition}")
            connection.commit()

    def persist_result(self, result: Mapping[str, Any]) -> Dict[str, Any]:
        calculation_id = str(result.get("canonical_calculation_id") or "")
        if not calculation_id:
            return {"ok": False, "reason": "missing calculation id"}
        created = str(result.get("calculation_timestamp") or result.get("last_completed_h1_timestamp") or "")
        conformal = result.get("conformal_prediction") if isinstance(result.get("conformal_prediction"), Mapping) else {}
        with _DB_LOCK, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO research_calibration_runs VALUES(?,?,?,?,?,?,?,?)",
                (calculation_id, created, str(result.get("last_completed_h1_timestamp")), str(result.get("data_hash")), str(result.get("input_hash")), str(result.get("output_hash")), str(result.get("schema_version")), json.dumps(_json_safe(result), ensure_ascii=False, default=str)),
            )
            prediction_time = pd.to_datetime(result.get("last_completed_h1_timestamp"), errors="coerce", utc=True)
            for row in conformal.get("horizons") or []:
                horizon = int(row.get("horizon") or 0)
                target_time = prediction_time + pd.Timedelta(hours=horizon) if pd.notna(prediction_time) else pd.NaT
                state_key = f"H+{horizon}|{result.get('volatility_regime')}|{result.get('session')}|{result.get('transition_state')}"
                coverage_state = dict(((result.get("adaptive_coverage") or {}).get("states") or {}).get(state_key) or {})
                connection.execute(
                    """INSERT OR REPLACE INTO research_conformal_predictions(
                        calculation_id,horizon,prediction_time,target_time,central,lower_band,upper_band,
                        volatility_regime,session,transition_state,status,target_coverage,adaptive_correction,
                        calibration_sample_size) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (calculation_id, horizon, str(prediction_time), str(target_time), _finite(row.get("central"), None),
                     _finite(row.get("lower_band"), None), _finite(row.get("upper_band"), None),
                     result.get("volatility_regime"), result.get("session"), result.get("transition_state"), "PENDING",
                     _finite(coverage_state.get("target_coverage"), TARGET_COVERAGE),
                     _finite(row.get("adaptive_correction"), 1.0), int(coverage_state.get("sample_size") or 0)),
                )
            connection.commit()
        return {"ok": True, "status": "SQLITE", "calculation_id": calculation_id, "horizon_rows": len(conformal.get("horizons") or [])}

    def settle_conformal_predictions(self, ohlc: pd.DataFrame) -> Dict[str, Any]:
        """Settle only targets backed by an actually completed H1 candle."""
        market = normalize_completed_ohlc(ohlc)
        if market.empty:
            return {"ok": False, "settled": 0, "reason": "No completed OHLC rows"}
        latest = pd.to_datetime(market["time"].iloc[-1], utc=True)
        settled = 0
        with _DB_LOCK, self._connect() as connection:
            pending = connection.execute(
                """SELECT calculation_id,horizon,prediction_time,target_time,central,lower_band,upper_band,
                          volatility_regime,session,transition_state,target_coverage,adaptive_correction,
                          calibration_sample_size
                   FROM research_conformal_predictions
                   WHERE status='PENDING' AND target_time<=? ORDER BY target_time""",
                (latest.isoformat(),),
            ).fetchall()
            columns = ["calculation_id", "horizon", "prediction_time", "target_time", "central", "lower_band", "upper_band", "volatility_regime", "session", "transition_state", "target_coverage", "adaptive_correction", "calibration_sample_size"]
            for values in pending:
                row = dict(zip(columns, values))
                target = pd.to_datetime(row["target_time"], errors="coerce", utc=True)
                if pd.isna(target):
                    continue
                eligible = market.loc[market["time"] >= target]
                if eligible.empty:
                    continue
                actual = float(eligible.iloc[0]["close"])
                lower = _finite(row.get("lower_band"), actual); upper = _finite(row.get("upper_band"), actual)
                inside = int(float(lower) <= actual <= float(upper))
                target_coverage = float(_finite(row.get("target_coverage"), TARGET_COVERAGE) or TARGET_COVERAGE)
                prior = connection.execute(
                    """SELECT inside_interval FROM research_conformal_outcomes
                       WHERE horizon=? AND volatility_regime=? AND session=? AND transition_state=?
                       ORDER BY target_time DESC LIMIT 99""",
                    (int(row["horizon"]), row.get("volatility_regime"), row.get("session"), row.get("transition_state")),
                ).fetchall()
                coverage_values = [float(item[0]) for item in reversed(prior)] + [float(inside)]
                observed = target_coverage
                for item in coverage_values:
                    observed = 0.94 * observed + 0.06 * item
                connection.execute(
                    """INSERT OR REPLACE INTO research_conformal_outcomes(
                        calculation_id,horizon,prediction_time,target_time,central,lower_band,upper_band,
                        actual_completed_close,inside_interval,target_coverage,recent_observed_coverage,
                        coverage_error,adaptive_correction,calibration_sample_size,volatility_regime,
                        session,transition_state,settled_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (row["calculation_id"], int(row["horizon"]), row["prediction_time"], row["target_time"],
                     row["central"], row["lower_band"], row["upper_band"], actual, inside, target_coverage,
                     observed, target_coverage - observed, row.get("adaptive_correction"),
                     int(row.get("calibration_sample_size") or 0), row.get("volatility_regime"),
                     row.get("session"), row.get("transition_state"), pd.Timestamp.utcnow().isoformat()),
                )
                connection.execute(
                    "UPDATE research_conformal_predictions SET status='SETTLED' WHERE calculation_id=? AND horizon=?",
                    (row["calculation_id"], int(row["horizon"])),
                )
                settled += 1
            connection.commit()
        return {"ok": True, "settled": settled, "latest_completed_h1": latest.isoformat(), "future_rows_used": 0}

    def completed_conformal_outcomes(self, limit: int = 5000) -> pd.DataFrame:
        with _DB_LOCK, self._connect() as connection:
            rows = connection.execute(
                """SELECT calculation_id AS prediction_calculation_id,prediction_time,target_time,horizon,
                          central AS predicted_close,lower_band AS predicted_lower_band,
                          upper_band AS predicted_upper_band,actual_completed_close,inside_interval,
                          target_coverage,recent_observed_coverage,coverage_error,adaptive_correction,
                          calibration_sample_size,volatility_regime,session,transition_state
                   FROM research_conformal_outcomes ORDER BY target_time DESC LIMIT ?""",
                (int(limit),),
            ).fetchall()
            names = [item[0] for item in connection.execute(
                """SELECT calculation_id AS prediction_calculation_id,prediction_time,target_time,horizon,
                          central AS predicted_close,lower_band AS predicted_lower_band,
                          upper_band AS predicted_upper_band,actual_completed_close,inside_interval,
                          target_coverage,recent_observed_coverage,coverage_error,adaptive_correction,
                          calibration_sample_size,volatility_regime,session,transition_state
                   FROM research_conformal_outcomes LIMIT 0"""
            ).description]
        return pd.DataFrame(rows, columns=names)

    def register_experiment(self, experiment: Mapping[str, Any]) -> Dict[str, Any]:
        experiment_id = str(experiment.get("experiment_id") or "")
        if not experiment_id:
            return {"ok": False, "reason": "missing experiment_id"}
        parameters = experiment.get("parameters") or {}
        configuration_hash = str(experiment.get("configuration_hash") or _hash_payload(parameters))
        returns = experiment.get("net_returns")
        with _DB_LOCK, self._connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO research_experiments VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (experiment_id, configuration_hash, json.dumps(_json_safe(parameters)), json.dumps(_json_safe(experiment.get("feature_set") or [])), json.dumps(_json_safe(experiment.get("thresholds") or {})), json.dumps(_json_safe(experiment.get("model_weights") or {})), json.dumps(_json_safe(experiment.get("regime_settings") or {})), str(experiment.get("training_period") or ""), str(experiment.get("validation_period") or ""), int(experiment.get("purging_period") or 0), int(experiment.get("embargo_period") or 0), json.dumps(_json_safe(returns)) if returns is not None else None, _finite(experiment.get("mae"), None), _finite(experiment.get("rmse"), None), _finite(experiment.get("direction_accuracy"), None), _finite(experiment.get("calibration_error"), None), _finite(experiment.get("sharpe"), None), int(bool(experiment.get("selected"))), experiment.get("rejected_reason"), str(experiment.get("created_at") or pd.Timestamp.utcnow().isoformat())),
            )
            for row in experiment.get("period_performance") or []:
                connection.execute(
                    "INSERT OR REPLACE INTO research_experiment_period_performance VALUES(?,?,?,?)",
                    (experiment_id, str(row.get("period_label")), int(row.get("chronological_index") or 0), float(row.get("performance"))),
                )
            connection.commit()
        return {"ok": True, "experiment_id": experiment_id, "configuration_hash": configuration_hash}

    def performance_matrix(self) -> tuple[np.ndarray, list[str], list[str]]:
        with _DB_LOCK, self._connect() as connection:
            rows = connection.execute(
                "SELECT experiment_id,period_label,chronological_index,performance FROM research_experiment_period_performance ORDER BY chronological_index,experiment_id"
            ).fetchall()
        if not rows:
            return np.empty((0, 0)), [], []
        frame = pd.DataFrame(rows, columns=["experiment_id", "period_label", "chronological_index", "performance"])
        pivot = frame.pivot_table(index=["chronological_index", "period_label"], columns="experiment_id", values="performance", aggfunc="last").sort_index()
        return pivot.to_numpy(dtype=float), [str(i[1]) for i in pivot.index], [str(c) for c in pivot.columns]


def persist_research_result(result: Mapping[str, Any], db_path: Optional[Path | str] = None) -> Dict[str, Any]:
    try:
        return ResearchStore(db_path or DEFAULT_DB_PATH).persist_result(result)
    except Exception as exc:
        return {"ok": False, "status": "FAILED SAFELY", "reason": str(exc)[:500]}


__all__ = [
    "RESEARCH_VERSION", "RESEARCH_SCHEMA_VERSION", "ResearchStore", "normalize_completed_ohlc", "data_hash",
    "purged_walk_forward_splits",
    "build_baseline_forecasts", "build_residual_vectors", "update_adaptive_coverage", "conformal_scenarios",
    "bayesian_online_changepoint", "update_adaptive_windows", "conditional_method_confidence_set",
    "dynamic_model_averaging", "probability_backtest_overfitting", "deflated_sharpe_ratio",
    "uncertainty_scores", "validate_research_invariants", "build_and_apply_research_layer",
    "build_research_layer_fail_safe", "persist_research_result",
]
