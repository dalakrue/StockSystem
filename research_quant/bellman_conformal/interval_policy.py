from __future__ import annotations
import numpy as np

def bounded_width_adjustment(coverage_debt: float, volatility_state: float, current_width: float, *, maximum_fraction: float = 0.35) -> float:
    raw = 0.55 * float(coverage_debt) + 0.25 * max(0.0, float(volatility_state))
    bound = maximum_fraction * max(float(current_width), 1e-12)
    return float(np.clip(raw * current_width, -bound, bound))
