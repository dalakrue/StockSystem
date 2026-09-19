"""Robust EV matrix for BUY/SELL/WAIT/HOLD/EXIT/SKIP."""
from __future__ import annotations
from typing import Any
from research.robust_expected_value import evaluate as evaluate_single

ACTIONS = ("BUY NOW", "SELL NOW", "WAIT", "HOLD", "EXIT", "SKIP")


def evaluate(*, current_price: float, target_price: float | None, uncertainty: float, reliability: float, tail_risk_penalty_pips: float) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for action in ACTIONS:
        decision = "BUY" if action == "BUY NOW" else "SELL" if action == "SELL NOW" else "WAIT"
        if action in {"WAIT", "SKIP"}:
            row = {"nominal_ev": 0.0, "robust_ev": 0.0, "spread_cost": 0.0, "slippage_cost": 0.0, "uncertainty_penalty": 0.0, "tail_risk_penalty": 0.0, "final_net_edge": 0.0, "status": "CAPITAL PRESERVATION"}
        elif action == "EXIT":
            row = {"nominal_ev": None, "robust_ev": None, "spread_cost": 0.0, "slippage_cost": 0.0, "uncertainty_penalty": None, "tail_risk_penalty": tail_risk_penalty_pips, "final_net_edge": None, "status": "POSITION DATA REQUIRED"}
        elif action == "HOLD":
            row = evaluate_single(current_price=current_price, target_price=target_price, decision=decision, uncertainty=uncertainty + 5.0, reliability=reliability, spread_pips=0.0, slippage_pips=0.0, tail_risk_penalty_pips=tail_risk_penalty_pips)
        else:
            row = evaluate_single(current_price=current_price, target_price=target_price, decision=decision, uncertainty=uncertainty, reliability=reliability, tail_risk_penalty_pips=tail_risk_penalty_pips)
        output.append({"action": action, **row})
    return output
