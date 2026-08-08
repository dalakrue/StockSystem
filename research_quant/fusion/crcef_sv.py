from __future__ import annotations
import math
from typing import Iterable
import numpy as np
from research_quant.fusion.evidence_registry import Evidence


def _softmax(values, temperature: float):
    array = np.asarray(values, dtype=float) / max(float(temperature), 1e-9)
    array -= np.max(array) if len(array) else 0.0
    weights = np.exp(array)
    return weights / max(weights.sum(), 1e-12)


def fuse_evidence(evidence: Iterable[Evidence], *, temperature: float = 0.5) -> dict[str, float | dict]:
    items = [item.bounded() for item in evidence]
    if not items:
        return {"direction_fusion_score": 0.0, "buy_evidence": 0.0, "sell_evidence": 0.0, "conflict": 1.0, "coverage": 0.0, "weights": {}}
    qualities = [item.quality_score for item in items]
    weights = _softmax(qualities, temperature)
    contributions = np.asarray([item.directional_value * item.calibration_quality * item.regime_relevance for item in items]) * weights
    score = float(np.clip(contributions.sum(), -1, 1))
    buy = float(contributions[contributions > 0].sum())
    sell = float(-contributions[contributions < 0].sum())
    conflict = float(min(buy, sell) / max(buy, sell, 1e-12))
    coverage = float(np.mean([item.quality_score > 0 for item in items]))
    return {"direction_fusion_score": score, "buy_evidence": buy, "sell_evidence": sell, "conflict": conflict, "coverage": coverage, "weights": {item.name: float(weight) for item, weight in zip(items, weights)}}


def uncertainty_score(*, direction_probability: float, conflict: float, drift_level: float, normalized_interval_width: float, coverage_error: float, missing_data_penalty: float, lambdas=(0.25, 0.20, 0.20, 0.15, 0.10, 0.10)) -> float:
    p = min(max(float(direction_probability), 1e-9), 1 - 1e-9)
    entropy = -(p * math.log(p) + (1 - p) * math.log(1 - p)) / math.log(2)
    values = (entropy, conflict, drift_level, normalized_interval_width, coverage_error, missing_data_penalty)
    return float(np.clip(100 * sum(weight * value for weight, value in zip(lambdas, values)), 0, 100))
