"""Cost- and uncertainty-adjusted expected value for research approval."""
from __future__ import annotations
from typing import Any


def evaluate(*, current_price: float, target_price: float | None, decision: str, uncertainty: float, reliability: float, spread_pips: float = 1.2, slippage_pips: float = 0.4, tail_risk_penalty_pips: float = 0.0) -> dict[str, Any]:
    if current_price <= 0 or target_price is None:
        return {"nominal_ev": None, "robust_ev": None, "spread_cost": spread_pips, "slippage_cost": slippage_pips, "uncertainty_penalty": None, "tail_risk_penalty": tail_risk_penalty_pips, "final_net_edge": None, "status": "INSUFFICIENT EVIDENCE"}
    direction = 1.0 if decision == "BUY" else -1.0 if decision == "SELL" else 0.0
    gross_pips = (target_price - current_price) * 10000.0 * direction
    nominal = gross_pips - spread_pips - slippage_pips
    uncertainty_penalty = abs(gross_pips) * min(max(uncertainty, 0.0), 100.0) / 100.0 * 0.55
    reliability_penalty = abs(gross_pips) * max(0.0, 55.0 - reliability) / 100.0
    robust = nominal - uncertainty_penalty - reliability_penalty - tail_risk_penalty_pips
    status = "POSITIVE" if nominal > 0 and robust > 0 else "COST-DOMINATED" if gross_pips > 0 and nominal <= 0 else "NEGATIVE"
    return {
        "nominal_ev": round(nominal, 4), "robust_ev": round(robust, 4),
        "spread_cost": spread_pips, "slippage_cost": slippage_pips,
        "uncertainty_penalty": round(uncertainty_penalty + reliability_penalty, 4),
        "tail_risk_penalty": round(tail_risk_penalty_pips, 4),
        "final_net_edge": round(robust, 4), "status": status,
    }
