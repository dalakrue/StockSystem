"""Decision Reason Chain."""
from __future__ import annotations
from typing import Any, Dict, List


def build(health: Dict[str, Any], danger: Dict[str, Any], guard: Dict[str, Any], drift: Dict[str, Any], regime: Dict[str, Any], calibration: Dict[str, Any]) -> Dict[str, Any]:
    support: List[str] = []
    warning: List[str] = []
    if health.get("score", 0) >= 70: support.append(f"Logic Health is {health.get('label')} ({health.get('score')}).")
    else: warning.append(f"Logic Health is weak: {health.get('label')} ({health.get('score')}).")
    if danger.get("danger_level") in {"Low", "Medium"}: support.append(f"Hidden danger level is {danger.get('danger_level')}.")
    else: warning.append(f"Main danger: {danger.get('main_danger')} — {danger.get('reason')}.")
    if drift.get("drift_level") == "Low": support.append("Prediction drift is low.")
    elif drift.get("drift_level") == "High": warning.append("Prediction drift is high; forecast trust is reduced.")
    if regime.get("risk_label") in {"Stable", "Aging"}: support.append(f"Regime status: {regime.get('risk_label')}.")
    else: warning.append(f"Regime warning: {regime.get('risk_label')}.")
    if calibration.get("label") in {"Well Calibrated", "Underconfident"}: support.append(f"Confidence calibration: {calibration.get('label')}.")
    elif calibration.get("label"): warning.append(f"Confidence calibration warning: {calibration.get('label')}.")
    for r in guard.get("reasons", []):
        if r != "No hard safety block detected": warning.append(r)
    return {"original_decision": guard.get("original_decision"), "safety_adjusted_decision": guard.get("safety_adjusted_decision"), "supporting_reasons": support[:5] or ["No strong supporting reason detected."], "warning_reasons": warning[:5] or ["No major warning reason detected."], "confidence_reduced_by": danger.get("main_danger", "No major reducer"), "confidence_improved_by": health.get("main_positive", "No strong improver"), "final_defensive_instruction": guard.get("final_instruction", "Read as safety wrapper, not replacement.")}
