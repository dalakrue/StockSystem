"""Institutional-quality Field 10 v3 research ranking candidate.

This module is additive and SHADOW_ONLY. Production rank and locked daily bias
are immutable inputs. Every horizon is calculated independently in return units.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
import math

import numpy as np
import pandas as pd

from core.field10_research_common_20260705 import HORIZONS, canonical_json, deterministic_hash, direction_sign, finite

VERSION = "field10-rank-utility-v3-20260705-v1"
CANDIDATE_NAME = "field10-rank-utility-v3-research-candidate"
FORMULA_VERSION = "field10-rank-utility-v3-formula-20260705-v1"
FEATURE_VERSION = "field10-rank-utility-v3-features-20260705-v1"
THRESHOLD_VERSION = "field10-rank-utility-v3-thresholds-20260705-v1"
PROMOTION_STATUS = "SHADOW_ONLY"

FORMULA_THRESHOLD_REGISTRY: dict[str, Any] = {
    "candidate_name": CANDIDATE_NAME, "version": FORMULA_VERSION, "status": PROMOTION_STATUS,
    "horizon_weight_candidates": {
        "v3_starting_candidate": {1: 0.10, 3: 0.30, 6: 0.35, 12: 0.15, 24: 0.07, 36: 0.03},
        "equal": {1: 1/6, 3: 1/6, 6: 1/6, 12: 1/6, 24: 1/6, 36: 1/6},
        "short_horizon_heavy": {1: 0.20, 3: 0.35, 6: 0.30, 12: 0.10, 24: 0.04, 36: 0.01},
        "production_v2": {1: 0.05, 3: 0.10, 6: 0.25, 12: 0.25, 24: 0.20, 36: 0.15},
        "regime_adaptive": {1: 0.12, 3: 0.28, 6: 0.32, 12: 0.16, 24: 0.08, 36: 0.04},
        "volatility_adaptive": {1: 0.16, 3: 0.31, 6: 0.31, 12: 0.13, 24: 0.06, 36: 0.03},
    },
    "active_research_weights": "v3_starting_candidate",
    "risk_coefficients": {"lambda_es": 0.35, "lambda_transition": 0.15, "lambda_connectedness": 0.12,
                          "lambda_uncertainty": 0.10, "lambda_semivariance": 0.12},
    "component_weights": {"horizon_utility": 0.30, "probability_calibration": 0.12, "conformal_coverage": 0.08,
                          "tail_safety": 0.12, "structural_stability": 0.10, "connectedness_safety": 0.08,
                          "data_quality": 0.08, "rank_stability": 0.07, "absolute_utility": 0.05},
    "normalization": {"winsor_lower_z": -4.0, "winsor_upper_z": 4.0, "minimum_samples": 30},
    "coverage_gamma": 1.5,
    "coverage_permissions": {"eligible": 0.80, "caution": 0.65, "diagnostic_only": 0.55},
    "absolute_minimum_utility": 0.0,
    "structural_veto": {"break_strength": 0.75, "post_break_h1_count": 96},
    "pbo_threshold": 0.40,
}
REGISTRY_HASH = deterministic_hash(FORMULA_THRESHOLD_REGISTRY)


def strategy_targets(frame: pd.DataFrame, *, bias: str, horizon: int) -> pd.Series:
    if horizon not in HORIZONS:
        raise ValueError(f"unsupported Field 10 horizon: {horizon}")
    sign = direction_sign(bias)
    close = pd.to_numeric(frame.get("close"), errors="coerce")
    if sign == 0:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return (sign * np.log(close.shift(-horizon) / close)).replace([np.inf, -np.inf], np.nan)


def robust_historical_normalization(value: Any, history: pd.Series, *, higher_is_better: bool = True) -> dict[str, Any]:
    current = finite(value)
    settled = pd.to_numeric(history, errors="coerce").dropna()
    minimum = int(FORMULA_THRESHOLD_REGISTRY["normalization"]["minimum_samples"])
    if current is None or len(settled) < minimum:
        return {"historical_quality_score": None, "robust_z_score": None, "normalization_sample_count": int(len(settled)), "normalization_status": "INSUFFICIENT_HISTORY"}
    median = float(settled.median()); mad = float((settled - median).abs().median()) * 1.4826
    scale = max(mad, float(settled.std(ddof=0)), 1e-12)
    z = (current - median) / scale
    if not higher_is_better:
        z = -z
    lo = float(FORMULA_THRESHOLD_REGISTRY["normalization"]["winsor_lower_z"])
    hi = float(FORMULA_THRESHOLD_REGISTRY["normalization"]["winsor_upper_z"])
    winsor = float(np.clip(z, lo, hi))
    score = float(100.0 / (1.0 + math.exp(-winsor)))
    return {"historical_quality_score": score, "robust_z_score": float(z), "winsorized_robust_z": winsor,
            "normalization_sample_count": int(len(settled)), "normalization_status": "AVAILABLE"}


def horizon_utility_v3(
    frame: pd.DataFrame, *, bias: str, horizon: int,
    calibrated_probability: Any = None, spread_cost: Any = None, slippage_cost: Any = None,
    directional_var_95: Any = None, expected_shortfall_95: Any = None,
    forecast_volatility: Any = None, adverse_semivariance: Any = None,
    transition_risk_pct: Any = None, short_connectedness_pct: Any = None,
    persistent_connectedness_pct: Any = None, conformal_lower_return: Any = None,
    conformal_median_return: Any = None, conformal_upper_return: Any = None,
    probability_calibration_error: Any = None, model_disagreement_pct: Any = None,
) -> dict[str, Any]:
    targets = strategy_targets(frame, bias=bias, horizon=horizon).dropna().tail(600)
    if len(targets) < 120:
        return {"horizon": horizon, "status": "INSUFFICIENT_SETTLED_TARGETS", "sample_count": int(len(targets)), "formula_version": FORMULA_VERSION}
    empirical_probability = float((targets > 0.0).mean())
    p_win = finite(calibrated_probability)
    if p_win is None:
        p_win = empirical_probability
        probability_status = "EMPIRICAL_UNCALIBRATED"
    else:
        if p_win > 1.0:
            p_win /= 100.0
        p_win = float(np.clip(p_win, 0.0, 1.0)); probability_status = "CALIBRATED"
    p_loss = 1.0 - p_win
    wins = targets[targets > 0.0]; losses = targets[targets <= 0.0]
    median_gain = float(wins.median()) if len(wins) else 0.0
    median_loss = abs(float(losses.median())) if len(losses) else 0.0
    gross_ev = p_win * median_gain - p_loss * median_loss
    spread, slippage = finite(spread_cost), finite(slippage_cost)
    exact_costs_available = spread is not None and slippage is not None
    net_ev = None if not exact_costs_available else gross_ev - max(spread, 0.0) - max(slippage, 0.0)
    var95 = finite(directional_var_95)
    if var95 is None:
        var95 = float(np.quantile(targets, 0.05))
    es95 = finite(expected_shortfall_95)
    if es95 is None:
        tail = targets[targets <= var95]
        es95 = float(tail.mean()) if len(tail) else var95
    severity = None if abs(var95) < 1e-12 else abs(es95) / abs(var95)
    vol = finite(forecast_volatility)
    semivariance = finite(adverse_semivariance)
    semivariance_equivalent = None if semivariance is None else math.sqrt(max(semivariance, 0.0))
    transition = finite(transition_risk_pct)
    short_conn, persistent_conn = finite(short_connectedness_pct), finite(persistent_connectedness_pct)
    transition_equivalent = None if transition is None or vol is None else max(transition, 0.0) / 100.0 * vol
    connectedness_pct = None if short_conn is None and persistent_conn is None else 0.35 * (short_conn or 0.0) + 0.65 * (persistent_conn or 0.0)
    connectedness_equivalent = None if connectedness_pct is None or vol is None else max(connectedness_pct, 0.0) / 100.0 * vol
    lower, median, upper = finite(conformal_lower_return), finite(conformal_median_return), finite(conformal_upper_return)
    interval_width = None if lower is None or upper is None else max(0.0, upper - lower)
    half_width = None if interval_width is None else interval_width / 2.0
    disagreement = finite(model_disagreement_pct)
    coefficients = FORMULA_THRESHOLD_REGISTRY["risk_coefficients"]
    contributions = {
        "net_expected_value": net_ev,
        "expected_shortfall_penalty": None if es95 is None else -coefficients["lambda_es"] * abs(es95),
        "transition_penalty": None if transition_equivalent is None else -coefficients["lambda_transition"] * transition_equivalent,
        "connectedness_penalty": None if connectedness_equivalent is None else -coefficients["lambda_connectedness"] * connectedness_equivalent,
        "uncertainty_penalty": None if half_width is None else -coefficients["lambda_uncertainty"] * half_width,
        "semivariance_penalty": None if semivariance_equivalent is None else -coefficients["lambda_semivariance"] * semivariance_equivalent,
    }
    managed = None if any(value is None for value in contributions.values()) else float(sum(contributions.values()))
    return {
        "horizon": horizon, "status": "AVAILABLE" if managed is not None else "PARTIAL_EVIDENCE",
        "probability_favourable_return": p_win, "probability_adverse_return": p_loss,
        "empirical_probability": empirical_probability, "probability_status": probability_status,
        "median_favourable_return": median_gain, "median_adverse_return": median_loss,
        "gross_expected_value": gross_ev, "spread_cost": spread, "slippage_cost": slippage,
        "execution_cost_status": "EXACT_AVAILABLE" if exact_costs_available else "MISSING_EXACT_COST",
        "net_expected_value": net_ev, "directional_var_95": var95, "directional_expected_shortfall_95": es95,
        "es_var_severity_ratio": severity, "har_forecast_volatility": vol,
        "adverse_semivariance": semivariance, "adverse_semivariance_return_equivalent": semivariance_equivalent,
        "transition_risk_pct": transition, "transition_risk_return_equivalent": transition_equivalent,
        "short_frequency_connectedness": short_conn, "persistent_connectedness": persistent_conn,
        "connectedness_return_equivalent": connectedness_equivalent,
        "conformal_lower_return": lower, "conformal_median_return": median, "conformal_upper_return": upper,
        "conformal_interval_width": interval_width, "conformal_half_width": half_width,
        "probability_calibration_error": finite(probability_calibration_error),
        "model_disagreement_pct": disagreement, "managed_utility": managed,
        "contributions": contributions, "coefficients": dict(coefficients), "sample_count": int(len(targets)),
        "formula_version": FORMULA_VERSION, "registry_hash": REGISTRY_HASH,
    }


def _geometric_reliability(values: Mapping[str, float | None], weights: Mapping[str, float]) -> tuple[float | None, float]:
    available = [(name, float(values[name]), float(weights[name])) for name in weights if values.get(name) is not None and weights[name] > 0]
    total = float(sum(weights.values())); available_weight = float(sum(weight for _, _, weight in available))
    if not available or total <= 0:
        return None, 0.0
    exponent = sum(weight * math.log(max(min(value / 100.0, 1.0), 1e-6)) for _, value, weight in available) / available_weight
    return float(100.0 * math.exp(exponent)), available_weight / total


def rank_v3_candidates(records: Sequence[Mapping[str, Any]], *, cluster_effective_weights: Mapping[str, float] | None = None) -> dict[str, Any]:
    rows = [dict(record) for record in records]
    component_weights = dict(FORMULA_THRESHOLD_REGISTRY["component_weights"])
    if cluster_effective_weights:
        component_weights.update({key: float(value) for key, value in cluster_effective_weights.items() if key in component_weights})
    component_names = list(component_weights)
    # Keep absolute and cross-sectional normalization separate.
    for component in component_names:
        values = pd.Series({str(row["symbol"]): finite(row.get(component)) for row in rows}, dtype=float).dropna()
        percentiles = values.rank(method="average", pct=True) * 100.0 if len(values) else pd.Series(dtype=float)
        for row in rows:
            symbol = str(row["symbol"])
            row.setdefault("cross_sectional_percentiles", {})[component] = finite(percentiles.get(symbol))
    ranked: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    gamma = float(FORMULA_THRESHOLD_REGISTRY["coverage_gamma"])
    for row in rows:
        normalized: dict[str, float | None] = {}
        for component in component_names:
            historical = finite(row.get(f"historical_quality::{component}"))
            cross = row["cross_sectional_percentiles"].get(component)
            normalized[component] = None if historical is None and cross is None else historical if cross is None else cross if historical is None else 0.70 * historical + 0.30 * cross
        geometric, evidence_coverage = _geometric_reliability(normalized, component_weights)
        evidence_penalty = evidence_coverage ** gamma
        score = None if geometric is None else geometric * evidence_penalty
        utility = finite(row.get("absolute_managed_utility"))
        thresholds = FORMULA_THRESHOLD_REGISTRY["coverage_permissions"]
        if evidence_coverage >= thresholds["eligible"]:
            coverage_permission = "ELIGIBLE"
        elif evidence_coverage >= thresholds["caution"]:
            coverage_permission = "CAUTION"
        elif evidence_coverage >= thresholds["diagnostic_only"]:
            coverage_permission = "DIAGNOSTIC_ONLY"
        else:
            coverage_permission = "INSUFFICIENT_EVIDENCE"
        structural = str(row.get("structural_entry_permission") or "BLOCK")
        absolute_gate = utility is not None and utility > float(FORMULA_THRESHOLD_REGISTRY["absolute_minimum_utility"])
        entry_permission = "BLOCK" if structural == "BLOCK" or not absolute_gate or coverage_permission in {"DIAGNOSTIC_ONLY", "INSUFFICIENT_EVIDENCE"} else "CAUTION" if coverage_permission == "CAUTION" or structural == "CAUTION" else "ELIGIBLE_SHADOW_ONLY"
        ranked_row = {**row, "normalized_components": normalized, "raw_research_score": geometric,
                      "evidence_coverage": evidence_coverage, "evidence_penalty": evidence_penalty,
                      "coverage_adjusted_score": score, "coverage_permission": coverage_permission,
                      "absolute_minimum_utility_pass": absolute_gate, "entry_permission_v3": entry_permission,
                      "promotion_status": PROMOTION_STATUS}
        ranked.append(ranked_row)
        for component in component_names:
            raw = finite(row.get(component)); normalized_value = normalized.get(component); weight = component_weights[component]
            components.append({"symbol": row["symbol"], "component_name": component, "raw_value": raw,
                               "historical_quality_score": finite(row.get(f"historical_quality::{component}")),
                               "cross_sectional_percentile": row["cross_sectional_percentiles"].get(component),
                               "normalized_component_score": normalized_value, "configured_weight": FORMULA_THRESHOLD_REGISTRY["component_weights"][component],
                               "effective_weight": weight, "weighted_contribution": None if normalized_value is None else weight * normalized_value})
    ranked.sort(key=lambda row: (row.get("coverage_adjusted_score") is None, -(row.get("coverage_adjusted_score") or -1e18), str(row.get("symbol"))))
    for index, row in enumerate(ranked, start=1):
        row["research_rank_v3"] = index if row.get("coverage_adjusted_score") is not None else None
    return {"candidate_name": CANDIDATE_NAME, "status": PROMOTION_STATUS, "rows": ranked, "components": components,
            "formula_registry": FORMULA_THRESHOLD_REGISTRY, "formula_registry_hash": REGISTRY_HASH,
            "production_rank_modified": False, "locked_bias_modified": False}


def formula_registry_json() -> str:
    return canonical_json(FORMULA_THRESHOLD_REGISTRY)


__all__ = [
    "VERSION", "CANDIDATE_NAME", "FORMULA_VERSION", "FEATURE_VERSION", "THRESHOLD_VERSION", "PROMOTION_STATUS",
    "FORMULA_THRESHOLD_REGISTRY", "REGISTRY_HASH", "strategy_targets", "robust_historical_normalization",
    "horizon_utility_v3", "rank_v3_candidates", "formula_registry_json",
]
