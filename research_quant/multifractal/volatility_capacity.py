from __future__ import annotations
import math

def risk_capacity(expected_move: float, forecast_variance: float) -> float:
    return float(expected_move / math.sqrt(max(float(forecast_variance), 1e-12)))
