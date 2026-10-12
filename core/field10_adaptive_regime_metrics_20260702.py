"""Deterministic OHLC-derived fallback evidence for Field 10.

The module fills unavailable regime/calibration columns from each symbol's own
completed selected-timeframe candles.  It never copies another symbol's values and never turns a
missing metric into a zero.  The calculations are causal, bounded and suitable
for use when an optional research publisher/API bundle is absent.
"""
from __future__ import annotations

from typing import Any, Mapping
import math
import numpy as np
import pandas as pd

from core.timeframe_window_contract_20260706 import (
    horizon_contract, minimum_calculation_candles, required_candles,
    selected_timeframe, window_contract,
)

VERSION = "field10-adaptive-regime-metrics-20260706-v5"


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def _pct(value: Any) -> float | None:
    out = _finite(value)
    if out is None:
        return None
    if 0.0 <= out <= 1.0:
        out *= 100.0
    return float(np.clip(out, 0.0, 100.0))


def _normalize(frame: Any) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    work = frame.copy(deep=False)
    lookup = {str(c).strip().lower().replace("_", " "): c for c in work.columns}
    def col(*names: str):
        for name in names:
            hit = lookup.get(name)
            if hit is not None:
                return hit
        return None
    t = col("time", "timestamp", "datetime", "date", "broker candle time")
    c = col("close", "c")
    o = col("open", "o")
    h = col("high", "h")
    l = col("low", "l")
    if c is None:
        return pd.DataFrame()
    out = pd.DataFrame({"close": pd.to_numeric(work[c], errors="coerce")})
    out["time"] = pd.to_datetime(work[t], errors="coerce", utc=True) if t is not None else pd.RangeIndex(len(work))
    out["open"] = pd.to_numeric(work[o], errors="coerce") if o is not None else out["close"].shift(1)
    out["high"] = pd.to_numeric(work[h], errors="coerce") if h is not None else pd.concat([out["open"], out["close"]], axis=1).max(axis=1)
    out["low"] = pd.to_numeric(work[l], errors="coerce") if l is not None else pd.concat([out["open"], out["close"]], axis=1).min(axis=1)
    out = out.dropna(subset=["close"]).sort_values("time", kind="mergesort").drop_duplicates("time", keep="last")
    return out.tail(5000).reset_index(drop=True)


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -12.0, 12.0)))


def _bars_for_hours(timeframe: str, hours: int, *, minimum: int = 1) -> int:
    return max(minimum, int(horizon_contract(timeframe=timeframe, horizon_hours=hours)["horizon_bars"]))


def _feature_frame(frame: pd.DataFrame, *, timeframe: str) -> pd.DataFrame:
    close = frame["close"].astype(float)
    ret = close.pct_change()
    rows = max(1, len(frame))

    def bounded(value: int, *, minimum: int, fraction: float) -> int:
        ceiling = max(minimum, int(rows * fraction))
        return max(minimum, min(int(value), ceiling))

    # Preserve the real-time horizons when enough history exists, but bound
    # rolling windows to the actual same-symbol sample. This lets a genuine
    # 100-candle series produce a degraded estimate instead of all-NaN features.
    fast_span = bounded(_bars_for_hours(timeframe, 12, minimum=2), minimum=2, fraction=0.20)
    slow_span = bounded(_bars_for_hours(timeframe, 48, minimum=fast_span + 1), minimum=fast_span + 1, fraction=0.50)
    short_vol = bounded(_bars_for_hours(timeframe, 24, minimum=3), minimum=3, fraction=0.25)
    long_vol = bounded(_bars_for_hours(timeframe, 120, minimum=short_vol + 1), minimum=short_vol + 1, fraction=0.55)
    momentum_bars = bounded(_bars_for_hours(timeframe, 6, minimum=1), minimum=1, fraction=0.10)
    momentum_vol = bounded(_bars_for_hours(timeframe, 48, minimum=3), minimum=3, fraction=0.40)
    fast = close.ewm(span=fast_span, adjust=False, min_periods=max(2, fast_span // 2)).mean()
    slow = close.ewm(span=slow_span, adjust=False, min_periods=max(3, slow_span // 2)).mean()
    vol_short = ret.rolling(short_vol, min_periods=max(2, short_vol // 2)).std()
    vol_long = ret.rolling(long_vol, min_periods=max(3, long_vol // 2)).std()
    scale = (vol_short * close).replace(0.0, np.nan)
    trend_z = ((fast - slow) / scale).replace([np.inf, -np.inf], np.nan).clip(-6, 6)
    momentum = close.pct_change(momentum_bars)
    momentum_z = (momentum / (ret.rolling(momentum_vol, min_periods=max(3, momentum_vol // 2)).std() * math.sqrt(momentum_bars))).replace([np.inf, -np.inf], np.nan).clip(-6, 6)
    vol_ratio = (vol_short / vol_long.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan).clip(0.1, 6.0)
    strength = (0.62 * trend_z.fillna(0.0) + 0.38 * momentum_z.fillna(0.0)).clip(-6, 6)

    bull = np.exp(np.clip(strength, -8, 8))
    bear = np.exp(np.clip(-strength, -8, 8))
    range_score = np.exp(-np.abs(strength)) * (1.0 / np.maximum(vol_ratio.fillna(1.0), 0.4))
    expansion = np.exp(np.clip((vol_ratio.fillna(1.0) - 1.0) * 1.8, -6, 6)) * (0.5 + np.abs(strength))
    compression = np.exp(np.clip((1.0 - vol_ratio.fillna(1.0)) * 2.0, -6, 6)) * (1.0 + 0.35 * (1.0 - np.minimum(np.abs(strength), 1.0)))
    raw = pd.DataFrame({
        "BULL_TREND": bull, "BEAR_TREND": bear, "RANGE": range_score,
        "EXPANSION": expansion, "COMPRESSION": compression,
    }, index=frame.index).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    probabilities = raw.div(raw.sum(axis=1).replace(0.0, np.nan), axis=0).fillna(0.2)
    labels = probabilities.idxmax(axis=1)
    out = pd.DataFrame({
        "close": close, "return": ret, "trend_z": trend_z, "momentum_z": momentum_z,
        "vol_ratio": vol_ratio, "strength": strength, "label": labels,
    })
    for column in probabilities:
        out[f"p_{column}"] = probabilities[column]
    return out

def _run_lengths(labels: pd.Series) -> tuple[int, list[int], list[str]]:
    values = labels.dropna().astype(str).tolist()
    if not values:
        return 0, [], []
    durations: list[int] = []
    states: list[str] = []
    current = values[0]
    length = 1
    for value in values[1:]:
        if value == current:
            length += 1
        else:
            states.append(current); durations.append(length)
            current = value; length = 1
    states.append(current); durations.append(length)
    return durations[-1], durations, states


def _forecast_validation(features: pd.DataFrame, horizon: int) -> tuple[float | None, float | None, int]:
    if len(features) <= horizon + 24:
        return None, None, 0
    strength = pd.to_numeric(features["strength"], errors="coerce")
    predicted_up = strength > 0
    future_return = features["close"].shift(-horizon) / features["close"] - 1.0
    actual_up = future_return > 0
    valid = strength.notna() & future_return.notna()
    minimum_validation = max(12, min(30, len(features) // 5))
    if valid.sum() < minimum_validation:
        return None, None, int(valid.sum())
    correct = (predicted_up[valid] == actual_up[valid]).astype(float)
    accuracy = float(correct.tail(500).mean() * 100.0)
    # Causal confidence based on signal magnitude, used as a probability forecast.
    prob_up = pd.Series(_sigmoid(strength / 1.35), index=features.index)
    y = actual_up.astype(float)
    brier = float(((prob_up[valid] - y[valid]) ** 2).tail(500).mean())
    return accuracy, brier, int(valid.tail(500).sum())


def _conditional_expected_return(
    features: pd.DataFrame, *, horizon: int = 12, max_neighbors: int = 160,
) -> tuple[float | None, int]:
    """Estimate a signed forward return from strictly historical analogue rows.

    The current row is matched only against rows whose complete ``horizon``-hour
    future is already known.  Matching uses the same symbol's regime label,
    signal strength and volatility ratio.  This keeps the estimate causal and
    prevents another symbol's return distribution from leaking into Field 10.
    The result is a percentage return, not a guaranteed price target.
    """
    if len(features) <= horizon + 24:
        return None, 0
    current = features.iloc[-1]
    current_strength = _finite(current.get("strength"))
    current_volatility = _finite(current.get("vol_ratio"))
    current_label = str(current.get("label") or "")
    if current_strength is None:
        return None, 0

    history = features.iloc[:-horizon].copy()
    history["forward_return"] = (
        features["close"].shift(-horizon) / features["close"] - 1.0
    ).iloc[:-horizon]
    history = history.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["strength", "forward_return"]
    )
    if history.empty:
        return None, 0

    same_regime = history.loc[history["label"].astype(str).eq(current_label)]
    candidates = same_regime if len(same_regime) >= 12 else history
    if len(candidates) < 10:
        return None, int(len(candidates))

    strength_scale = float(candidates["strength"].std())
    if not math.isfinite(strength_scale) or strength_scale <= 1e-9:
        strength_scale = 1.0
    distance = (candidates["strength"] - current_strength).abs() / strength_scale
    if current_volatility is not None and candidates["vol_ratio"].notna().sum() >= 10:
        volatility_scale = float(candidates["vol_ratio"].std())
        if not math.isfinite(volatility_scale) or volatility_scale <= 1e-9:
            volatility_scale = 1.0
        distance = distance + 0.55 * (
            (candidates["vol_ratio"] - current_volatility).abs() / volatility_scale
        )
    candidates = candidates.assign(_distance=distance).sort_values(
        "_distance", kind="mergesort"
    ).head(max(12, min(max_neighbors, len(candidates))))

    returns = pd.to_numeric(candidates["forward_return"], errors="coerce").dropna()
    if len(returns) < 10:
        return None, int(len(returns))
    lower, upper = returns.quantile([0.05, 0.95])
    clipped = returns.clip(lower=lower, upper=upper)
    distances = pd.to_numeric(candidates.loc[clipped.index, "_distance"], errors="coerce").fillna(10.0)
    weights = np.exp(-np.clip(distances.to_numpy(dtype=float), 0.0, 20.0))
    if not np.isfinite(weights).all() or float(weights.sum()) <= 1e-12:
        estimate = float(clipped.mean())
    else:
        estimate = float(np.average(clipped.to_numpy(dtype=float), weights=weights))
    return estimate * 100.0, int(len(clipped))


def _robust_drift_expected_return(features: pd.DataFrame, horizon: int) -> tuple[float | None, int]:
    """Same-symbol OHLC fallback when too few analogue neighbours exist."""
    returns = pd.to_numeric(features.get("return"), errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(returns) < 12:
        return None, int(len(returns))
    recent = returns.tail(min(120, len(returns)))
    lower, upper = recent.quantile([0.05, 0.95])
    clipped = recent.clip(lower=lower, upper=upper)
    # Blend median and trimmed mean to reduce single-candle sensitivity.
    per_bar = 0.65 * float(clipped.median()) + 0.35 * float(clipped.mean())
    estimate = math.expm1(float(np.clip(per_bar * max(1, horizon), -0.35, 0.35))) * 100.0
    return float(estimate), int(len(clipped))


def compute_adaptive_regime_metrics(frame: Any, timeframe: str | None = None) -> dict[str, Any]:
    """Compute symbol-specific Field 10 metrics while preserving real horizons."""
    tf = selected_timeframe(timeframe or getattr(frame, "attrs", {}).get("timeframe") or "H1")
    contract = window_contract(tf)
    market = _normalize(frame)
    required = required_candles(tf, "higher")
    minimum = minimum_calculation_candles(tf, "higher")
    if len(market) < minimum:
        return {
            "ok": False, "status": "BELOW_MINIMUM_SELECTED_TIMEFRAME",
            "sample_count": int(len(market)), "available_candles": int(len(market)),
            "required_candles": int(required), "minimum_calculation_candles": int(minimum),
            "timeframe": tf, "timeframe_seconds": int(contract["timeframe_seconds"]), "version": VERSION,
        }
    full_history = len(market) >= required
    coverage_ratio = min(1.0, len(market) / max(1.0, float(required)))
    features = _feature_frame(market, timeframe=tf)
    usable = features.dropna(subset=["label", "close"])
    if usable.empty:
        return {"ok": False, "status": "FEATURES_UNAVAILABLE", "sample_count": int(len(market)), "timeframe": tf, "version": VERSION}

    latest = usable.iloc[-1]
    probability_columns = [c for c in usable.columns if c.startswith("p_")]
    current_probs = {c[2:]: float(latest[c]) for c in probability_columns}
    ordered = sorted(current_probs.items(), key=lambda item: item[1], reverse=True)
    selected_regime, top_probability = ordered[0]
    second_probability = ordered[1][1] if len(ordered) > 1 else 0.0
    probs = np.array([value for _, value in ordered], dtype=float)
    entropy = float(-(probs * np.log(np.clip(probs, 1e-12, 1.0))).sum() / math.log(max(2, len(probs))) * 100.0)
    posterior_margin = float((top_probability - second_probability) * 100.0)

    age, durations, states = _run_lengths(usable["label"])
    same_state_durations = [d for d, st in zip(durations[:-1], states[:-1]) if st == selected_regime]
    global_durations = durations[:-1]
    history = same_state_durations if len(same_state_durations) >= 3 else global_durations
    historical_expected = float(np.median(history)) if history else float(contract["bars_per_day"] / 2.0)
    expected = max(float(age) + 1.0, 0.70 * historical_expected + 0.30 * (float(age) + 1.0))
    remaining = max(0.5, expected - float(age))
    base_hazard = float(np.clip(1.0 / max(expected, 1.0), 0.015, 0.45))
    age_pressure = float(np.clip((age / max(expected, 1.0)) ** 1.35, 0.0, 2.0))
    hazard = float(np.clip(base_hazard * (0.72 + 0.55 * age_pressure) * (1.0 + entropy / 220.0), 0.01, 0.65))
    horizon_bars = {h: _bars_for_hours(tf, h) for h in (1, 3, 6, 12, 24, 36)}
    transition = {h: float((1.0 - (1.0 - hazard) ** horizon_bars[h]) * 100.0) for h in (1, 3, 6, 24)}

    expected_return_12h, expected_return_12h_samples = _conditional_expected_return(usable, horizon=horizon_bars[12])
    expected_return_24h, expected_return_24h_samples = _conditional_expected_return(usable, horizon=horizon_bars[24])
    expected_return_36h, expected_return_36h_samples = _conditional_expected_return(usable, horizon=horizon_bars[36])
    if expected_return_12h is None:
        expected_return_12h, expected_return_12h_samples = _robust_drift_expected_return(usable, horizon_bars[12])
    if expected_return_24h is None:
        expected_return_24h, expected_return_24h_samples = _robust_drift_expected_return(usable, horizon_bars[24])
    if expected_return_36h is None:
        expected_return_36h, expected_return_36h_samples = _robust_drift_expected_return(usable, horizon_bars[36])

    acc1, brier1, n1 = _forecast_validation(usable, horizon_bars[1])
    acc3, brier3, n3 = _forecast_validation(usable, horizon_bars[3])
    acc6, brier6, n6 = _forecast_validation(usable, horizon_bars[6])
    validation_accuracy = [v for v in (acc1, acc3, acc6) if v is not None]
    historical_accuracy = float(np.mean(validation_accuracy)) if validation_accuracy else 50.0
    directional_confidence = float(np.clip(50.0 + abs(float(latest["strength"])) * 10.0, 50.0, 94.0))
    raw_probability = float(np.clip(0.55 * historical_accuracy + 0.45 * directional_confidence, 50.0, 95.0))
    # Partial history remains usable but receives an explicit confidence penalty.
    calibrated_probability = float(np.clip(50.0 + (raw_probability - 50.0) * (0.55 + 0.45 * coverage_ratio), 50.0, 95.0))

    direction = "BUY" if float(latest["strength"]) >= 0 else "SELL"
    if selected_regime == "BULL_TREND": direction = "BUY"
    elif selected_regime == "BEAR_TREND": direction = "SELL"

    quant = {}
    try:
        from core.field10_quant_metrics_20260704 import compute_quant_metrics
        quant = compute_quant_metrics(frame, bias=direction)
        if quant.get("transition_risk_6h") is not None:
            transition[6] = float(quant["transition_risk_6h"])
    except Exception as exc:
        quant = {"quant_extension_status": "UNAVAILABLE", "quant_extension_error": type(exc).__name__}

    return {
        "ok": True,
        "status": "FULL_SELECTED_TIMEFRAME_DERIVED" if full_history else "ADAPTIVE_PARTIAL_HISTORY_DERIVED",
        "version": VERSION,
        "timeframe": tf, "timeframe_seconds": int(contract["timeframe_seconds"]),
        "horizon_bars": horizon_bars, "sample_count": int(len(market)),
        "available_candles": int(len(market)), "required_candles": int(required),
        "minimum_calculation_candles": int(minimum), "full_history": bool(full_history),
        "coverage_ratio": round(float(coverage_ratio), 6),
        "regime": selected_regime, "bias": direction,
        "regime_probability": round(top_probability * 100.0, 4),
        "regime_entropy": round(entropy, 4), "posterior_margin": round(posterior_margin, 4),
        "regime_persistence": round(100.0 - transition[6], 4),
        "regime_age": int(age), "expected_regime_duration": round(expected, 3),
        "estimated_remaining_duration": round(remaining, 3),
        "transition_risk_1h": round(transition[1], 4),
        "transition_risk_3h": round(transition[3], 4),
        "transition_risk_6h": round(transition[6], 4),
        "transition_risk_24h": round(transition[24], 4),
        "expected_return_12h": None if expected_return_12h is None else round(expected_return_12h, 6),
        "expected_return_12h_sample_count": expected_return_12h_samples,
        "expected_return_24h": None if expected_return_24h is None else round(expected_return_24h, 6),
        "expected_return_24h_sample_count": expected_return_24h_samples,
        "expected_return_36h": None if expected_return_36h is None else round(expected_return_36h, 6),
        "expected_return_36h_sample_count": expected_return_36h_samples,
        "calibrated_bias_probability": round(calibrated_probability, 4),
        "calibrated_reliability": round(calibrated_probability, 4),
        "brier_score": None if brier1 is None else round(float(brier1), 6),
        "forecast_accuracy_1h": None if acc1 is None else round(float(acc1), 4),
        "forecast_accuracy_3h": None if acc3 is None else round(float(acc3), 4),
        "forecast_accuracy_6h": None if acc6 is None else round(float(acc6), 4),
        "validation_samples_1h": n1, "validation_samples_3h": n3, "validation_samples_6h": n6,
        "strength": round(float(latest["strength"]), 6), "volatility_ratio": _finite(latest["vol_ratio"]),
        "probabilities": {name: round(value * 100.0, 4) for name, value in ordered},
        **{key: value for key, value in quant.items() if key not in {"ok", "status", "version", "sample_count"}},
    }

def coalesce_metric(primary: Any, fallback: Any) -> Any:
    """Use primary evidence only when it is finite/non-empty."""
    if isinstance(primary, str):
        return primary if primary.strip() and primary.strip().upper() not in {"UNAVAILABLE", "N/A", "NONE", "NAN"} else fallback
    return primary if _finite(primary) is not None else fallback


__all__ = ["VERSION", "compute_adaptive_regime_metrics", "coalesce_metric"]
