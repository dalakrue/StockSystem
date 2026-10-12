"""No-Trade Guard."""
from __future__ import annotations
from typing import Any, Dict, List
from ._shared import current_values


def evaluate(metrics: Dict[str, Any], health: Dict[str, Any], danger: Dict[str, Any], drift: Dict[str, Any], data_quality: Dict[str, Any], signal: Dict[str, Any], conflicts: Dict[str, Any]) -> Dict[str, Any]:
    v = current_values(metrics)
    reasons: List[str] = []
    if health.get("score", 50) < 40: reasons.append("Logic Health is unsafe")
    if danger.get("danger_level") == "Critical": reasons.append("Critical hidden danger detected")
    if data_quality.get("status") == "FAIL": reasons.append("Data quality failed")
    if v["exit_risk"] >= 72: reasons.append("Exit risk is high")
    if v["forecast_agreement"] < 45: reasons.append("Forecast agreement is too low")
    if v["regime_confidence"] < 45: reasons.append("Regime confidence is too low")
    if v["market_quality"] < 45: reasons.append("Market quality is weak")
    if drift.get("drift_level") == "High": reasons.append("Prediction drift is high")
    if conflicts.get("conflict_count", 0) >= 3: reasons.append("Too many logic conflicts")
    if signal.get("label") == "Unstable": reasons.append("Signal stability is weak")
    if v["tp_quality"] < 42: reasons.append("TP quality is weak")
    if data_quality.get("status") == "WARNING": reasons.append("Data quality warning exists")
    original = v.get("original_decision", "Original decision unavailable")
    if any(r in reasons for r in ["Data quality failed", "Logic Health is unsafe", "Critical hidden danger detected"]):
        safety = "No Trade"
        status = "Blocked"
    elif len(reasons) >= 4:
        safety = "No Trade"
        status = "Blocked"
    elif len(reasons) >= 2:
        safety = "Wait / Pullback Confirmation Needed"
        status = "Defensive Wait"
    elif len(reasons) == 1:
        safety = "Trade Allowed But Risky / Reduce Confidence"
        status = "Caution"
    else:
        safety = "Keep Original Decision"
        status = "Allowed"
    return {"original_decision": original, "safety_adjusted_decision": safety, "guard_status": status, "reasons": reasons or ["No hard safety block detected"], "final_instruction": "Do not override original logic silently; read this as a safety wrapper."}
