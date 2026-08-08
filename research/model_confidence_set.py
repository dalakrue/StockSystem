"""Non-destructive model confidence set over multiple stored loss families."""
from __future__ import annotations
from typing import Any, Mapping

from research._utils import clamp, deep_find, number

MODELS = (
    "KNN", "Greedy", "Regime model", "Price-path model", "Technical model",
    "NLP model", "Historical-similarity model",
)
LOSS_FAMILIES = (
    "directional_loss", "price_error", "calibration_loss", "net_economic_loss", "tail_risk_loss",
)


def _loss(metrics: Mapping[str, Any], key: str, family: str) -> float | None:
    aliases = (
        f"{key}_{family}",
        f"{key}_{family.replace('_loss', '')}",
        f"{key}_loss" if family == "directional_loss" else f"{key}_{family}_score",
    )
    value = number(deep_find(metrics, aliases), None)
    if value is None:
        return None
    return clamp(value * 100.0 if 0.0 <= value <= 1.0 else value)


def evaluate(metrics: Mapping[str, Any], *, sample_size: int) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for model in MODELS:
        key = model.lower().replace(" ", "_").replace("-", "_")
        losses = {family: _loss(metrics, key, family) for family in LOSS_FAMILIES}
        available = [value for value in losses.values() if value is not None]
        aggregate = sum(available) / len(available) if available else None
        if sample_size < 25:
            eligibility = "INSUFFICIENT EVIDENCE"
        elif aggregate is None:
            eligibility = "SUPPORT ONLY"
        elif aggregate <= 35:
            eligibility = "ELIGIBLE"
        elif aggregate <= 60:
            eligibility = "SUPPORT ONLY"
        else:
            eligibility = "REMOVED FROM CURRENT SET"
        output.append({
            "model_name": model,
            "eligibility": eligibility,
            "loss_score": round(aggregate, 4) if aggregate is not None else None,
            "evidence_count": sample_size,
            **losses,
        })
    return output
