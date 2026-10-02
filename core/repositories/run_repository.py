"""Read-only access to the canonical run contract."""
from __future__ import annotations
from typing import Any, MutableMapping
from core.canonical.snapshot import CanonicalRunSnapshot, load_canonical_snapshot


class RunRepository:
    def __init__(self, state: MutableMapping[str, Any] | None = None):
        self.state = state

    def latest(self) -> CanonicalRunSnapshot | None:
        return load_canonical_snapshot(self.state)
