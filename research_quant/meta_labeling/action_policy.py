from __future__ import annotations

def expected_utility(probability_correct: float, expected_gain: float, expected_loss: float, transaction_cost: float, uncertainty_penalty: float, transition_penalty: float) -> float:
    return float(probability_correct * expected_gain - (1 - probability_correct) * expected_loss - transaction_cost - uncertainty_penalty - transition_penalty)


def shadow_action(primary: str, actionability: float, utility: float, *, entry_location_favourable: bool, existing_position: bool, reversal_validated: bool, threshold: float = 0.55) -> str:
    if primary == "HOLD":
        return "WAIT" if reversal_validated else "HOLD"
    if primary in {"BUY", "SELL"}:
        if actionability >= threshold and utility > 0 and entry_location_favourable:
            return primary
        if actionability >= threshold and not entry_location_favourable:
            return "WAIT PULLBACK"
        return "WAIT"
    if primary == "WAIT PULLBACK":
        return "WAIT PULLBACK"
    return "WAIT"
