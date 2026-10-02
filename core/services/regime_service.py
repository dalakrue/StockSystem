"""Read-only regime service."""
from __future__ import annotations
from core.canonical.snapshot import CanonicalRunSnapshot


def regime_summary(snapshot: CanonicalRunSnapshot) -> dict[str, object]:
    return {"regime": snapshot.regime, "age": snapshot.regime_age, "reliability": snapshot.regime_reliability}
