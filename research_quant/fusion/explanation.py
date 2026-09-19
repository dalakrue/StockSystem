from __future__ import annotations
from typing import Iterable
from research_quant.fusion.evidence_registry import Evidence

def explain(evidence: Iterable[Evidence], action: str) -> str:
    ordered = sorted((item.bounded() for item in evidence), key=lambda item: abs(item.directional_value * item.quality_score), reverse=True)
    drivers = ", ".join(f"{item.name}={item.directional_value:+.2f}" for item in ordered[:4]) or "no valid evidence"
    return f"{action}: {drivers}. Research-only; production decision unchanged."
