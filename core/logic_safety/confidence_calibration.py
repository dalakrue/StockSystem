"""Confidence Calibration."""
from __future__ import annotations
from typing import Any, Dict
from ._shared import current_values, find_number, clamp


def calibrate(metrics: Dict[str, Any], df: Any = None) -> Dict[str, Any]:
    v = current_values(metrics)
    historical = find_number(metrics, ["direction accuracy", "historical accuracy", "accuracy", "win rate"], None)
    if historical is not None and historical <= 1:
        historical *= 100
    if historical is None:
        # Partial fallback based on reliability inputs, not a real calibration.
        historical = (v["prediction_reliability"] * 0.55 + v["forecast_agreement"] * 0.25 + v["regime_confidence"] * 0.20)
        label = "Not Enough History"
        note = "Using reliability proxy because historical confidence buckets were not exposed."
    else:
        label = "Well Calibrated"
        note = "Uses existing historical accuracy/confidence scalar exposed by the app."
    raw = v["raw_confidence"]
    calibrated = clamp(historical, 0, 100, 60)
    gap = raw - calibrated
    if abs(gap) <= 8 and label != "Not Enough History": label = "Well Calibrated"
    elif gap > 22: label = "Overconfident"
    elif gap > 10: label = "Slightly Overconfident"
    elif gap < -12: label = "Underconfident"
    return {"raw_confidence": round(raw, 1), "calibrated_confidence": round(calibrated, 1), "confidence_gap": round(gap, 1), "label": label, "trust_adjustment": "Reduce trust" if gap > 10 else "Normal" if abs(gap) <= 10 else "May be conservative", "note": note}
