"""Frozen experiment registry, PBO and non-automatic promotion governance."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import combinations
from typing import Any
import math

import numpy as np
import pandas as pd

from core.field10_research_common_20260705 import canonical_json, deterministic_hash

VERSION = "field10-promotion-governance-20260705-v1"
GOVERNANCE_THRESHOLD_VERSION = "field10-v3-governance-thresholds-20260705-v1"


def freeze_experiment_registry(candidate: Mapping[str, Any]) -> dict[str, Any]:
    required = (
        "candidate_name", "formula_hash", "feature_version", "threshold_version", "horizon_weights",
        "risk_coefficients", "calibration_method", "structural_break_settings", "normalization_settings",
        "candidate_model_list", "sample_period", "symbols", "timeframe", "spread_slippage_treatment",
    )
    missing = [key for key in required if key not in candidate]
    payload = {key: candidate.get(key) for key in required}
    payload["registered_before_test"] = not missing
    payload["missing_registry_fields"] = missing
    payload["experiment_registry_hash"] = deterministic_hash(payload)
    payload["frozen_registry_json"] = canonical_json(payload)
    return payload


def probability_of_backtest_overfitting(performance: pd.DataFrame) -> dict[str, Any]:
    """Combinatorially symmetric cross-validation PBO estimate.

    Rows are chronological subperiods and columns are candidates. Higher values
    are better. The candidate matrix must be frozen before this function runs.
    """
    matrix = performance.apply(pd.to_numeric, errors="coerce").dropna(how="any")
    periods, candidates = matrix.shape
    if periods < 8 or candidates < 4:
        return {"status": "INSUFFICIENT_CANDIDATE_MATRIX", "pbo_probability": None,
                "number_of_candidates": candidates, "number_of_subperiods": periods}
    if periods % 2:
        matrix = matrix.iloc[:-1]
        periods -= 1
    half = periods // 2
    logits: list[float] = []
    degradations: list[float] = []
    winners: list[str] = []
    oos_ranks: list[float] = []
    for selected in combinations(range(periods), half):
        # Avoid evaluating both a split and its exact complement twice.
        if 0 not in selected:
            continue
        selected_set = set(selected)
        test = [index for index in range(periods) if index not in selected_set]
        in_sample = matrix.iloc[list(selected)].mean()
        out_sample = matrix.iloc[test].mean()
        winner = str(in_sample.idxmax())
        rank = float(out_sample.rank(ascending=False, method="average")[winner])
        percentile = (rank - 0.5) / candidates
        percentile = float(np.clip(percentile, 1e-6, 1.0 - 1e-6))
        logits.append(math.log(percentile / (1.0 - percentile)))
        degradations.append(float(in_sample[winner] - out_sample[winner]))
        winners.append(winner); oos_ranks.append(rank)
    if not logits:
        return {"status": "INSUFFICIENT_SPLITS", "pbo_probability": None,
                "number_of_candidates": candidates, "number_of_subperiods": periods}
    pbo = float(np.mean(np.asarray(logits) > 0.0))
    winner_mode = max(set(winners), key=winners.count)
    return {
        "status": "AVAILABLE", "pbo_probability": pbo, "oos_rank_logit": float(np.mean(logits)),
        "in_sample_winner": winner_mode, "out_of_sample_rank": float(np.mean(oos_ranks)),
        "performance_degradation": float(np.mean(degradations)), "number_of_candidates": candidates,
        "number_of_subperiods": periods, "split_count": len(logits),
        "promotion_permission": "PASS" if pbo <= 0.40 else "BLOCK",
    }


def evaluate_promotion_gates(metrics: Mapping[str, Any], *, explicit_decision: Mapping[str, Any] | None = None) -> dict[str, Any]:
    gates = {
        "positive_cost_adjusted_oos_utility": bool((metrics.get("net_oos_utility") or 0.0) > 0.0),
        "brier_not_materially_degraded": bool(metrics.get("brier_delta") is not None and float(metrics["brier_delta"]) <= 0.02),
        "calibration_not_materially_degraded": bool(metrics.get("ece_delta") is not None and float(metrics["ece_delta"]) <= 0.03),
        "conformal_coverage_acceptable": bool(metrics.get("conformal_coverage") is not None and 0.84 <= float(metrics["conformal_coverage"]) <= 0.96),
        "survives_mcs": bool(metrics.get("mcs_survives")),
        "pbo_pass": bool(metrics.get("pbo_probability") is not None and float(metrics["pbo_probability"]) <= float(metrics.get("pbo_threshold", 0.40))),
        "evidence_coverage_pass": bool(float(metrics.get("evidence_coverage") or 0.0) >= 0.80),
        "structural_break_clear": str(metrics.get("structural_entry_permission") or "BLOCK") != "BLOCK",
        "identity_freshness_integrity_pass": bool(metrics.get("identity_integrity_pass")),
    }
    all_pass = all(gates.values())
    explicit = dict(explicit_decision or {})
    explicit_promote = explicit.get("decision") == "PROMOTE" and explicit.get("version") and explicit.get("decision_hash")
    promoted = bool(all_pass and explicit_promote)
    return {
        "gate_results": gates, "all_research_gates_pass": all_pass,
        "explicit_versioned_promotion_decision_present": bool(explicit_promote),
        "promotion_permission": "PROMOTED" if promoted else "SHADOW_ONLY",
        "promotion_status": "SHADOW_ONLY_PENDING_EXPLICIT_VERSIONED_DECISION" if all_pass and not explicit_promote else "SHADOW_ONLY_VALIDATION_INCOMPLETE" if not all_pass else "PROMOTED",
        "production_rank_modified": False, "locked_bias_modified": False,
        "threshold_version": GOVERNANCE_THRESHOLD_VERSION,
    }


__all__ = ["VERSION", "GOVERNANCE_THRESHOLD_VERSION", "freeze_experiment_registry", "probability_of_backtest_overfitting", "evaluate_promotion_gates"]
