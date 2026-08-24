"""Read-only prediction projection service."""
from __future__ import annotations
from typing import Any, Mapping
from core.canonical.snapshot import CanonicalRunSnapshot


def predictions(snapshot: CanonicalRunSnapshot) -> Mapping[str, Any]:
    return snapshot.predictions
