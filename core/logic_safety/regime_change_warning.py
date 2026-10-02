"""Regime Change Early Warning."""
from __future__ import annotations
from typing import Any, Dict
from ._shared import find_number, find_text, safe_float


def analyze(metrics: Dict[str, Any]) -> Dict[str, Any]:
    current = find_text(metrics, ["current regime", "major regime", "regime"], "Unknown")
    age = find_number(metrics, ["days in regime", "regime age", "days_in_regime"], None)
    expected = find_number(metrics, ["expected regime duration", "expected days", "median days"], None)
    remaining = find_number(metrics, ["estimated days remaining", "days remaining", "estimated_days_remaining"], None)
    if age is None:
        return {"current_regime": current, "regime_age": "Unknown", "expected_duration": "Unknown", "estimated_days_remaining": "Unknown", "risk_label": "Partial", "exhaustion_score": 50, "change_pressure": "Partial", "regime_stability": "Partial", "reason": "Regime age was not exposed by existing calculations."}
    if expected is None or expected <= 0:
        expected = max(float(age) * 1.3, 3.0)
    if remaining is None:
        remaining = max(float(expected) - float(age), 0.0)
    ratio = float(age) / max(float(expected), 1e-9)
    if ratio >= 1.35:
        label = "Regime Break Warning"
    elif ratio >= 1.0:
        label = "Exhausted"
    elif ratio >= 0.8:
        label = "Change Pressure Rising"
    elif ratio >= 0.6:
        label = "Aging"
    else:
        label = "Stable"
    score = min(100, max(0, ratio * 75))
    return {"current_regime": current, "regime_age": round(float(age), 2), "expected_duration": round(float(expected), 2), "estimated_days_remaining": round(float(remaining), 2), "risk_label": label, "exhaustion_score": round(score, 1), "change_pressure": "High" if score >= 75 else "Medium" if score >= 45 else "Low", "regime_stability": "Weak" if score >= 85 else "Mixed" if score >= 60 else "Stable", "reason": "Current regime is older than typical duration." if score >= 75 else "Regime age is within or near normal range."}
