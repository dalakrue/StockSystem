from __future__ import annotations

def select_action(direction_score: float, calibrated_buy_probability: float, calibrated_sell_probability: float, actionability: float, expected_utility: float, uncertainty_pct: float, *, primary_decision: str, entry_location_favourable: bool, existing_position: bool = False, reversal_validated: bool = False, buy_threshold: float = 0.2, sell_threshold: float = -0.2, probability_threshold: float = 0.55, actionability_threshold: float = 0.55, maximum_uncertainty_pct: float = 55.0) -> str:
    if primary_decision == "HOLD" or existing_position:
        return "WAIT" if reversal_validated else "HOLD"
    if primary_decision == "WAIT PULLBACK":
        return "WAIT PULLBACK"
    if uncertainty_pct > maximum_uncertainty_pct or expected_utility <= 0 or actionability < actionability_threshold:
        return "WAIT PULLBACK" if primary_decision in {"BUY", "SELL"} and not entry_location_favourable else "WAIT"
    if direction_score >= buy_threshold and calibrated_buy_probability >= probability_threshold:
        return "BUY" if entry_location_favourable else "WAIT PULLBACK"
    if direction_score <= sell_threshold and calibrated_sell_probability >= probability_threshold:
        return "SELL" if entry_location_favourable else "WAIT PULLBACK"
    return "WAIT"
