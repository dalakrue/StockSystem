"""Lightweight answer confidence calibration over evidence coverage."""
from __future__ import annotations
from typing import Any, Iterable, Mapping


def calibrate_confidence(evidence: Iterable[Mapping[str, Any]], *, required_count: int, stale: bool, conflict: bool) -> dict[str, Any]:
    rows = list(evidence)
    coverage = min(1.0, len(rows) / max(1, int(required_count)))
    reliabilities: list[float] = []
    for row in rows:
        try:
            reliabilities.append(min(max(float(row.get("reliability")), 0.0), 100.0))
        except Exception:
            pass
    rel = sum(reliabilities) / len(reliabilities) if reliabilities else 50.0
    raw = 20.0 + 50.0 * coverage + 0.30 * rel
    if stale:
        raw -= 30.0
    if conflict:
        raw -= 25.0
    calibrated = max(0.0, min(95.0, raw))
    return {
        "calibrated_confidence": round(calibrated, 1),
        "coverage_ratio": round(coverage, 3),
        "mean_evidence_reliability": round(rel, 1),
        "calibration_boundary": "Heuristic post-hoc calibration; not a guarantee of trading correctness.",
    }

__all__ = ["calibrate_confidence"]
