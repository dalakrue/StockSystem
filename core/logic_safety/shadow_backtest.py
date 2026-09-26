"""Shadow Backtest Mode."""
from __future__ import annotations
from typing import Dict, Any


def compare(guard: Dict[str, Any], health: Dict[str, Any], danger: Dict[str, Any]) -> Dict[str, Any]:
    original = str(guard.get("original_decision", "Unknown"))
    safety = str(guard.get("safety_adjusted_decision", "Unknown"))
    if safety == "Keep Original Decision":
        diff = "Low"
    elif "Risky" in safety or "Wait" in safety:
        diff = "Medium"
    else:
        diff = "High"
    return {"current_original_logic_decision": original, "safety_guard_decision": safety, "difference_level": diff, "warning": "Safety layer disagrees with original decision; review hidden danger reasons." if diff in {"Medium", "High"} else "Safety layer does not materially disagree.", "result_quality": "Display-only shadow comparison; does not replace original logic.", "health_score": health.get("score"), "danger_level": danger.get("danger_level")}
