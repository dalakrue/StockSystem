"""Research experiment multiplicity and production-eligibility guard."""
from __future__ import annotations
from typing import Any


def evaluate(*, sample_size: int, models_tested: int = 7, thresholds_tested: int = 4, feature_combinations: int = 1, horizons_tested: int = 4, tp_sl_alternatives: int = 0, in_sample_score: float | None = None, out_of_sample_score: float | None = None) -> dict[str, Any]:
    degradation = None if in_sample_score is None or out_of_sample_score is None else max(0.0, in_sample_score - out_of_sample_score)
    multiplicity = models_tested * thresholds_tested * feature_combinations * horizons_tested * max(1, tp_sl_alternatives or 1)
    if sample_size < 250:
        risk, eligibility = "HIGH", "SHADOW ONLY"
    elif degradation is not None and degradation > 20:
        risk, eligibility = "HIGH", "SHADOW ONLY"
    elif multiplicity > sample_size * 2:
        risk, eligibility = "MEDIUM", "SHADOW ONLY"
    else:
        risk, eligibility = "LOW", "RESEARCH ELIGIBLE; MANUAL PROMOTION REQUIRED"
    return {"models_tested": models_tested, "thresholds_tested": thresholds_tested, "feature_combinations": feature_combinations, "horizons_tested": horizons_tested, "tp_sl_alternatives": tp_sl_alternatives, "in_sample_score": in_sample_score, "out_of_sample_score": out_of_sample_score, "degradation": degradation, "overfitting_risk": risk, "production_eligibility": eligibility, "sample_size": sample_size}
