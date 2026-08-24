"""Decision persistence, flip frequency and variance diagnostics."""
from __future__ import annotations
from statistics import pvariance
from typing import Any, Iterable, Mapping

from research._utils import number


def _variance(rows: list[Mapping[str, Any]], aliases: tuple[str, ...]) -> float | None:
    values: list[float] = []
    for row in rows:
        for alias in aliases:
            value = number(row.get(alias), None)
            if value is not None:
                values.append(float(value))
                break
    return round(pvariance(values), 6) if len(values) >= 2 else None


def evaluate(rows: Iterable[Mapping[str, Any]], current_decision: str) -> dict[str, Any]:
    records = [dict(row) for row in rows if isinstance(row, Mapping)]
    decisions = [str(row.get("decision") or row.get("canonical_decision") or "").upper() for row in records]
    decisions = [value for value in decisions if value]
    if not decisions:
        decisions = [current_decision]
    flips = sum(1 for previous, current in zip(decisions, decisions[1:]) if previous != current)
    persistence = 100.0 * max(0, len(decisions) - flips) / max(len(decisions), 1)
    flip_frequency = 100.0 * flips / max(len(decisions) - 1, 1)
    confidence_variance = _variance(records, ("confidence", "reliability", "reliability_score"))
    target_variance = _variance(records, ("predicted_price", "target_price", "bias_corrected_target"))
    priority_variance = _variance(records, ("priority", "priority_score"))
    regime_variance = _variance(records, ("regime_probability", "regime_reliability"))
    variance_penalty = min(
        25.0,
        sum(value or 0.0 for value in (confidence_variance, priority_variance, regime_variance)) ** 0.5,
    )
    score = max(0.0, min(100.0, persistence - 0.6 * flip_frequency - variance_penalty))
    return {
        "decision_path": decisions[-10:],
        "decision_persistence": round(persistence, 3),
        "flip_frequency": round(flip_frequency, 3),
        "confidence_variance": confidence_variance,
        "target_variance": target_variance,
        "priority_variance": priority_variance,
        "regime_probability_variance": regime_variance,
        "score": round(score, 3),
        "status": "STABLE" if score >= 65 else "VARIABLE" if score >= 40 else "UNSTABLE",
        "sample_size": len(records),
    }
