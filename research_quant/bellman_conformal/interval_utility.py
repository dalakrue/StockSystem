from __future__ import annotations

def interval_cost(coverage_penalty: float, interval_width: float, interval_change: float, decision_uncertainty: float, *, lambda_width: float = 1.0, lambda_instability: float = 0.25, lambda_decision: float = 0.5) -> float:
    return float(coverage_penalty + lambda_width * interval_width + lambda_instability * abs(interval_change) + lambda_decision * decision_uncertainty)
