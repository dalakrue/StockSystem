"""Independent 1H/2H/3H/6H abstention gate."""
from __future__ import annotations
from typing import Any


def evaluate(*, forecastability: float, coverage_status: str, similar_history_count: int, regime_stability: float, error_risk: float, robust_ev: float | None, model_agreement: float, data_quality: float, event_multiplier: float, safe_horizon_hours: int, horizon: int) -> dict[str, Any]:
    if horizon > safe_horizon_hours:
        return {"status": "ABSTAIN", "reason": "Structural-change gate limits the safe horizon."}
    if similar_history_count < 10 or robust_ev is None or coverage_status == "INSUFFICIENT EVIDENCE":
        return {"status": "WAIT", "reason": "Insufficient settled evidence for scientific approval."}
    score = 0.22 * forecastability + 0.18 * regime_stability + 0.16 * model_agreement + 0.16 * data_quality + 0.14 * (100.0 - error_risk) + 0.14 * min(100.0, max(0.0, robust_ev * 5.0 + 50.0))
    score *= max(0.0, min(1.0, event_multiplier))
    if coverage_status == "UNDERCOVERED":
        score -= 15.0
    if robust_ev <= 0:
        return {"status": "ABSTAIN", "reason": "Robust expected value is not positive.", "score": round(score, 3)}
    if score >= 68:
        return {"status": "ACCEPT", "reason": "All main scientific gates passed.", "score": round(score, 3)}
    if score >= 52:
        return {"status": "ACCEPT WITH REDUCED RISK", "reason": "Edge is positive but one or more trust gates are weak.", "score": round(score, 3)}
    if score >= 38:
        return {"status": "WAIT", "reason": "Wait for stronger confirmation.", "score": round(score, 3)}
    return {"status": "ABSTAIN", "reason": "Combined research trust is too low.", "score": round(score, 3)}
