"""One-pass evidence critic and support-status classifier."""
from __future__ import annotations
from typing import Any, Iterable, Mapping

STATUSES = {"SUPPORTED", "PARTIALLY_SUPPORTED", "CONFLICTING_EVIDENCE", "INSUFFICIENT_EVIDENCE", "STALE_GENERATION"}


def critique_answer(evidence: Iterable[Mapping[str, Any]], *, required_sources: Iterable[str], stale: bool, conflict: bool) -> dict[str, Any]:
    rows = list(evidence)
    required = {str(x).lower() for x in required_sources}
    covered = set()
    for row in rows:
        hay = f"{row.get('field','')} {row.get('source_name','')}".lower()
        for token in required:
            if token in hay:
                covered.add(token)
    if stale:
        status = "STALE_GENERATION"
    elif conflict:
        status = "CONFLICTING_EVIDENCE"
    elif not rows:
        status = "INSUFFICIENT_EVIDENCE"
    elif len(covered) >= max(1, len(required) - 1):
        status = "SUPPORTED"
    elif covered:
        status = "PARTIALLY_SUPPORTED"
    else:
        status = "INSUFFICIENT_EVIDENCE"
    return {
        "status": status,
        "covered_sources": sorted(covered),
        "missing_sources": sorted(required - covered),
        "revision_needed": status != "SUPPORTED",
        "critic_note": "State only retrieved values; disclose missing, stale, or conflicting evidence.",
    }

__all__ = ["critique_answer", "STATUSES"]
