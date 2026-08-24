"""Chronological selective-risk versus coverage curves for shadow actions."""
from __future__ import annotations

from typing import Any, Iterable, Mapping
import numpy as np


def evaluate(records: Iterable[Mapping[str, Any]], *, min_accepted: int = 5) -> dict[str, Any]:
    rows = [dict(row) for row in records if isinstance(row, Mapping)]
    parsed = []
    for index, row in enumerate(rows):
        action = str(row.get("action", row.get("decision", row.get("predicted_direction", "WAIT")))).upper()
        if action not in {"BUY", "SELL"}:
            continue
        try:
            confidence = float(row.get("confidence", row.get("probability", row.get("priority_score", 0.0))))
            if confidence > 1.0:
                confidence /= 100.0
            confidence = float(np.clip(confidence, 0.0, 1.0))
            correct = float(row.get("direction_correct", 1.0 if str(row.get("settled_outcome")).upper() == "WIN" else 0.0))
            correct = float(np.clip(correct, 0.0, 1.0))
        except (TypeError, ValueError):
            continue
        parsed.append({"index": index, "confidence": confidence, "error": 1.0 - correct, "action": action})
    n = len(parsed)
    if n == 0:
        return {"status": "INSUFFICIENT EVIDENCE", "sample_size": 0, "curve": []}
    unique = sorted({round(row["confidence"], 8) for row in parsed})
    if len(unique) > 199:
        positions = np.linspace(0, len(unique) - 1, 199).round().astype(int)
        unique = [unique[index] for index in sorted(set(positions.tolist()))]
    thresholds = sorted({0.0, 1.0, *unique})
    curve = []
    for threshold in thresholds:
        accepted = [row for row in parsed if row["confidence"] >= threshold]
        if not accepted:
            continue
        risk = float(np.mean([row["error"] for row in accepted]))
        curve.append({
            "confidence_threshold": float(threshold),
            "accepted_count": len(accepted),
            "coverage": len(accepted) / n,
            "selective_risk": risk,
            "accuracy": 1.0 - risk,
            "abstained_count": n - len(accepted),
        })
    eligible = [row for row in curve if row["accepted_count"] >= int(min_accepted)]
    best = min(eligible or curve, key=lambda row: (row["selective_risk"], -row["coverage"]))
    baseline = curve[0]
    return {
        "status": "OK" if n >= int(min_accepted) else "INSUFFICIENT EVIDENCE",
        "sample_size": n,
        "curve": curve,
        "baseline_risk": baseline["selective_risk"],
        "best_operating_point": best,
        "risk_reduction": baseline["selective_risk"] - best["selective_risk"],
        "chronological_input_preserved": True,
        "production_decision_changed": False,
    }


__all__ = ["evaluate"]
