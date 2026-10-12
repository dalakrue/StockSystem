"""Stable numeric/string calculation-generation identity helpers.

Older repair builds sometimes wrote values such as ``GEN-d95bb1bf93bb3e05``
into ``calculation_generation`` even though the canonical runtime and SQLite
schema require a positive integer.  These helpers preserve the human-readable
``generation_id`` while guaranteeing that every numerical generation consumer
receives a deterministic positive integer.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any
import re

_GEN_HEX = re.compile(r"(?:^|[^0-9a-f])GEN-([0-9a-f]+)", re.IGNORECASE)


def numeric_generation(value: Any, default: int = 1) -> int:
    """Return a deterministic positive integer for any legacy generation value."""
    try:
        number = int(value)
        if number > 0:
            return number
    except Exception:
        pass

    text = str(value or "").strip()
    if text:
        match = _GEN_HEX.search(text)
        if match:
            # Keep the value inside signed SQLite INTEGER range and away from 0.
            return (int(match.group(1)[:15], 16) % 2_000_000_000) + 1
        digest = sha256(text.encode("utf-8", errors="ignore")).hexdigest()
        return (int(digest[:15], 16) % 2_000_000_000) + 1
    try:
        fallback = int(default)
    except Exception:
        fallback = 1
    return max(1, fallback)


def generation_id(value: Any, *, fallback_seed: Any = "") -> str:
    """Return the display/string identity without contaminating numeric fields."""
    text = str(value or "").strip()
    if text:
        return text if text.upper().startswith("GEN-") else f"GEN-{text}"
    digest = sha256(str(fallback_seed or "generation").encode("utf-8", errors="ignore")).hexdigest()
    return f"GEN-{digest[:16]}"


def canonical_generation(payload: Mapping[str, Any] | None, default: int = 1) -> int:
    mapping = payload if isinstance(payload, Mapping) else {}
    return numeric_generation(
        mapping.get("calculation_generation")
        or mapping.get("generation")
        or mapping.get("generation_id"),
        default=default,
    )


def normalize_generation_fields(payload: Mapping[str, Any] | None, default: int = 1) -> dict[str, Any]:
    """Copy a canonical mapping with a numeric generation and readable ID."""
    result = dict(payload or {})
    original_id = result.get("generation_id")
    original_number = result.get("calculation_generation") or result.get("generation")
    number = numeric_generation(original_number or original_id, default=default)
    result["calculation_generation"] = number
    result["generation"] = number
    result["generation_id"] = generation_id(original_id or number, fallback_seed=number)
    return result


__all__ = [
    "numeric_generation", "generation_id", "canonical_generation",
    "normalize_generation_fields",
]
