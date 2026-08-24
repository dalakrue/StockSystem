"""Decayed residual-bias correction for research display only."""
from __future__ import annotations
from typing import Any, Iterable, Mapping

from research._utils import number


def evaluate(
    raw_prediction: float | None,
    outcomes: Iterable[Mapping[str, Any]],
    *,
    decay: float = 0.94,
) -> dict[str, Any]:
    samples: list[tuple[str, float]] = []
    for item in outcomes:
        residual = number(item.get("residual"), None)
        if residual is None:
            actual = number(item.get("actual_price"), None)
            predicted = number(item.get("predicted_price"), None)
            residual = actual - predicted if actual is not None and predicted is not None else None
        if residual is None:
            continue
        timestamp = str(item.get("settled_at") or item.get("settled_at_utc") or item.get("actual_time") or "")
        samples.append((timestamp, float(residual)))
    if not samples:
        return {
            "adaptive_bias": 0.0,
            "corrected_prediction": raw_prediction,
            "sample_size": 0,
            "status": "INSUFFICIENT EVIDENCE",
        }
    # ISO timestamps sort chronologically; newest residual gets age zero.  When
    # timestamps are missing, input order is preserved and treated newest-first.
    if any(timestamp for timestamp, _ in samples):
        samples.sort(key=lambda item: item[0], reverse=True)
    weighted = 0.0
    total = 0.0
    for age, (_, residual) in enumerate(samples[:100]):
        weight = decay ** age
        weighted += residual * weight
        total += weight
    bias = weighted / total if total else 0.0
    return {
        "adaptive_bias": round(bias, 8),
        "corrected_prediction": round(raw_prediction + bias, 8) if raw_prediction is not None else None,
        "sample_size": len(samples),
        "decay": decay,
        "status": "SHADOW ONLY",
    }
