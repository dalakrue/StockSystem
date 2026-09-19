"""Typed shape for shadow research results."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ResearchEvaluation:
    summary: Mapping[str, Any]
    horizons: tuple[Mapping[str, Any], ...]
    models: tuple[Mapping[str, Any], ...]
    diagnostics: Mapping[str, Any]
