"""Forecastability score combining reliability, uncertainty and evidence size."""
from __future__ import annotations
import math


def evaluate(*, reliability: float, uncertainty: float, model_agreement: float, sample_size: int, horizon: int) -> dict[str, float | str | int]:
    evidence_factor = min(1.0, math.log1p(max(sample_size, 0)) / math.log1p(250))
    horizon_penalty = {1: 0.0, 2: 3.0, 3: 7.0, 6: 15.0}.get(horizon, horizon * 2.0)
    score = 0.42 * reliability + 0.28 * model_agreement + 0.20 * (100.0 - uncertainty) + 10.0 * evidence_factor - horizon_penalty
    score = max(0.0, min(100.0, score))
    status = "HIGH" if score >= 70 else "MEDIUM" if score >= 50 else "LOW" if score >= 30 else "UNFORECASTABLE"
    return {"score": round(score, 3), "status": status, "sample_size": int(sample_size)}
