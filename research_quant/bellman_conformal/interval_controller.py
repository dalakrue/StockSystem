from __future__ import annotations
from research_quant.bellman_conformal.interval_policy import bounded_width_adjustment
from research_quant.bellman_conformal.interval_utility import interval_cost


def control_interval(base_lower: float, base_upper: float, *, target_coverage: float, recent_coverage: float, volatility_state: float = 0.0, previous_width: float | None = None, decision_uncertainty: float = 0.0) -> dict[str, float | str]:
    base_width = max(0.0, float(base_upper) - float(base_lower))
    coverage_debt = max(0.0, float(target_coverage) - float(recent_coverage))
    adjustment = bounded_width_adjustment(coverage_debt, volatility_state, base_width)
    controlled_width = max(0.0, base_width + adjustment)
    midpoint = (float(base_lower) + float(base_upper)) / 2.0
    change = controlled_width - (base_width if previous_width is None else float(previous_width))
    coverage_penalty = coverage_debt ** 2
    cost = interval_cost(coverage_penalty, controlled_width, change, decision_uncertainty)
    return {
        "base_interval_width": base_width, "controlled_interval_width": controlled_width,
        "width_adjustment": adjustment, "coverage_debt": coverage_debt,
        "lower": midpoint - controlled_width / 2, "upper": midpoint + controlled_width / 2,
        "control_action": "WIDEN" if adjustment > 0 else "HOLD" if adjustment == 0 else "NARROW",
        "control_cost": cost, "coverage_penalty": coverage_penalty,
    }
