"""Lightweight Bayesian-style structural-change risk projection."""
from __future__ import annotations
from typing import Any, Mapping
from research._utils import clamp, deep_find, number


def evaluate(snapshot_metrics: Mapping[str, Any], *, regime_age: float, uncertainty: float) -> dict[str, Any]:
    explicit = number(deep_find(snapshot_metrics, ("change_point_probability", "changepoint_probability", "transition_probability")), None)
    volatility = number(deep_find(snapshot_metrics, ("volatility_shift_probability", "volatility_transition", "volatility_risk")), None)
    direction = number(deep_find(snapshot_metrics, ("direction_shift_probability", "direction_transition", "flip_probability")), None)
    base = clamp(explicit * 100.0 if explicit is not None and explicit <= 1.0 else explicit, default=0.0)
    age_penalty = min(max(regime_age - 15.0, 0.0) * 1.5, 25.0)
    probability = clamp(max(base, 0.45 * uncertainty + age_penalty))
    direction_p = clamp(direction * 100.0 if direction is not None and direction <= 1.0 else direction, default=probability * 0.8)
    volatility_p = clamp(volatility * 100.0 if volatility is not None and volatility <= 1.0 else volatility, default=probability * 0.9)
    if probability >= 70:
        status, safe = "HIGH RISK", 1
    elif probability >= 50:
        status, safe = "TRANSITION", 1
    elif probability >= 30:
        status, safe = "WATCH", 3
    else:
        status, safe = "STABLE", 6
    return {
        "change_probability": round(probability, 3),
        "direction_shift_probability": round(direction_p, 3),
        "volatility_shift_probability": round(volatility_p, 3),
        "most_likely_regime_age": round(float(regime_age), 3),
        "safe_horizon_hours": safe,
        "status": status,
    }
