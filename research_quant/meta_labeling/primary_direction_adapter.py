from __future__ import annotations
from typing import Any, Mapping

ALLOWED = {"BUY", "SELL", "WAIT", "WAIT PULLBACK", "HOLD"}

def production_direction(canonical: Mapping[str, Any]) -> str:
    final = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
    raw = str(final.get("final_decision") or final.get("decision") or canonical.get("full_metric_direction") or "WAIT").upper().replace("_", " ")
    if raw in {"PULLBACK", "WAIT/PULLBACK"}:
        raw = "WAIT PULLBACK"
    if raw in {"HOLD & PROTECT", "HOLD AND PROTECT"}:
        raw = "HOLD"
    return raw if raw in ALLOWED else "WAIT"

def direction_value(label: str) -> int:
    return 1 if label == "BUY" else -1 if label == "SELL" else 0
