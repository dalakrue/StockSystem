from __future__ import annotations
from typing import Mapping
import numpy as np


def combined_forecast_variance(base_variance: float, multipliers: Mapping[str, float]) -> float:
    product = 1.0
    for value in multipliers.values():
        product *= max(float(value), 1e-12)
    return float(max(base_variance, 0.0) * product)


def msm_summary(components: Mapping[str, float]) -> dict[str, float | str]:
    finite = {key: float(value) for key, value in components.items() if np.isfinite(value)}
    base = max(finite.get("daily", 0.0) ** 2, 1e-12)
    normalizer = max(finite.get("daily", 1e-12), 1e-12)
    multipliers = {key: max(value / normalizer, 1e-6) for key, value in finite.items() if key != "residual"}
    variance = combined_forecast_variance(base, multipliers)
    state = "HIGH" if finite.get("immediate", 0) > 1.5 * normalizer else "LOW" if finite.get("immediate", 0) < 0.65 * normalizer else "NORMAL"
    return {"combined_forecast_variance": variance, "volatility_regime": state, "volatility_persistence": finite.get("persistent", 0.0) / normalizer}
