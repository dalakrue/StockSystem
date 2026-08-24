"""Read-only priority service."""
from __future__ import annotations
from core.canonical.snapshot import CanonicalRunSnapshot


def priority_summary(snapshot: CanonicalRunSnapshot) -> dict[str, float | str]:
    return {"decision": snapshot.decision, "priority": snapshot.priority, "reliability": snapshot.reliability}
