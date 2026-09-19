"""Versioned risk-managed utility and duplicate-aware shadow ranking for Field 10.

The production expected-return columns, production rank and locked daily direction
are inputs only.  This module creates research evidence and never mutates them.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
import math

import numpy as np
import pandas as pd

from core.field10_research_common_20260705 import HORIZONS, clip, finite, direction_sign

VERSION = "field10-rank-utility-v2-20260705-v1"

# Research-only registry.  Values are inert until explicit promotion.
FORMULA_THRESHOLD_REGISTRY: dict[str, Any] = {
    "version": "field10-managed-utility-registry-20260705-v1",
    "status": "RESEARCH_ONLY_NOT_PRODUCTION",
    "horizon_weights": {1: 0.05, 3: 0.10, 6: 0.25, 12: 0.25, 24: 0.20, 36: 0.15},
    "target_volatility": {1: 0.0040, 3: 0.0070, 6: 0.0100, 12: 0.0140, 24: 0.0200, 36: 0.0250},
    "minimum_scale": 0.25,
    "lambdas": {
        "expected_shortfall": 0.35,
        "transition": 0.15,
        "spillover": 0.12,
        "uncertainty": 0.10,
        "conflict": 0.10,
    },
    "component_weights": {
        "managed_utility": 0.20,
        "directional_probability": 0.12,
        "tail_safety": 0.10,
        "volatility_safety": 0.08,
        "regime_stability": 0.06,
        "transition_safety": 0.06,
        "semivariance_safety": 0.06,
        "bad_connectedness_safety": 0.07,
        "frequency_connectedness_safety": 0.05,
        "tail_dependence_safety": 0.05,
        "duplicate_exposure_safety": 0.04,
        "mcs_membership": 0.03,
        "split_robustness": 0.03,
        "data_quality": 0.03,
        "settlement_completeness": 0.01,
        "rank_bootstrap_stability": 0.01,
    },
    "evidence_duplicate_correlation": 0.92,
    "minimum_rank_evidence_fraction": 0.55,
    "rank_bootstrap_draws": 250,
}


def _strategy_targets(frame: pd.DataFrame, horizon: int, sign: int) -> pd.Series:
    close = pd.to_numeric(frame.get("close"), errors="coerce")
    return (float(sign) * np.log(close.shift(-horizon) / close)).replace([np.inf, -np.inf], np.nan)


def _quality_score(value: Any) -> float | None:
    number = finite(value)
    if number is not None:
        return float(np.clip(number, 0.0, 100.0))
    text = str(value or "").strip().upper()
    return {
        "A": 95.0, "A+": 100.0, "A-": 90.0,
        "B": 82.0, "B+": 87.0, "B-": 77.0,
        "C": 65.0, "C+": 70.0, "C-": 58.0,
        "D": 42.0, "E": 20.0, "F": 5.0,
        "FULL": 95.0, "AVAILABLE": 85.0, "PARTIAL": 55.0,
        "PROXY": 40.0, "FALLBACK": 35.0, "UNAVAILABLE": 0.0,
    }.get(text)


def horizon_managed_utility(
    frame: pd.DataFrame,
    *,
    bias: str,
    horizon: int,
    forecast_volatility: Any,
    expected_shortfall: Any,
    transition_risk_pct: Any,
    bad_spillover_pct: Any,
    prediction_interval_width: Any,
    model_disagreement: Any,
    spread_cost: Any,
    slippage_cost: Any,
) -> dict[str, Any]:
    """Compute raw and managed utility without fabricating unavailable costs."""
    if horizon not in HORIZONS:
        raise ValueError(f"unsupported Field 10 horizon: {horizon}")
    sign = direction_sign(bias)
    if sign == 0 or frame is None or len(frame) < 180:
        return {"horizon": horizon, "status": "DIRECTION_OR_SAMPLE_UNAVAILABLE"}
    targets = _strategy_targets(frame, horizon, sign).dropna().tail(360)
    if len(targets) < 120:
        return {"horizon": horizon, "status": "INSUFFICIENT_SETTLED_TARGETS", "sample_count": int(len(targets))}

    wins = targets.loc[targets > 0]
    losses = targets.loc[targets <= 0]
    p_win = float((targets > 0).mean())
    p_loss = 1.0 - p_win
    median_gain = float(wins.median()) if not wins.empty else 0.0
    median_loss = abs(float(losses.median())) if not losses.empty else 0.0
    gross_ev = p_win * median_gain - p_loss * median_loss

    spread = finite(spread_cost)
    slippage = finite(slippage_cost)
    cost_status = "AVAILABLE" if spread is not None and slippage is not None else "MISSING_EXECUTION_COST"
    net_ev = None if cost_status != "AVAILABLE" else gross_ev - max(0.0, spread) - max(0.0, slippage)

    forecast_vol = finite(forecast_volatility)
    es = finite(expected_shortfall)
    transition = finite(transition_risk_pct)
    spillover = finite(bad_spillover_pct)
    interval = finite(prediction_interval_width)
    disagreement = finite(model_disagreement)
    target_vol = float(FORMULA_THRESHOLD_REGISTRY["target_volatility"][horizon])
    minimum_scale = float(FORMULA_THRESHOLD_REGISTRY["minimum_scale"])
    vol_safety = None if forecast_vol is None or forecast_vol <= 0 else float(np.clip(target_vol / forecast_vol, minimum_scale, 1.0))

    # Translate percentage-style safety factors into return units using the
    # horizon volatility.  This prevents adding percentages directly to returns.
    transition_equivalent = None if transition is None or forecast_vol is None else max(0.0, transition) / 100.0 * forecast_vol
    spillover_equivalent = None if spillover is None or forecast_vol is None else max(0.0, spillover) / 100.0 * forecast_vol
    disagreement_equivalent = None if disagreement is None or forecast_vol is None else max(0.0, disagreement) / 100.0 * forecast_vol
    lambdas = FORMULA_THRESHOLD_REGISTRY["lambdas"]
    required = (net_ev, es, transition_equivalent, spillover_equivalent, interval, disagreement_equivalent, vol_safety)
    if any(v is None for v in required):
        tail_adjusted = None
        managed = None
        status = "PARTIAL_EVIDENCE_NO_MANAGED_UTILITY"
    else:
        tail_adjusted = (
            float(net_ev)
            - float(lambdas["expected_shortfall"]) * abs(float(es))
            - float(lambdas["transition"]) * float(transition_equivalent)
            - float(lambdas["spillover"]) * float(spillover_equivalent)
            - float(lambdas["uncertainty"]) * abs(float(interval))
            - float(lambdas["conflict"]) * float(disagreement_equivalent)
        )
        managed = float(tail_adjusted) * float(vol_safety)
        status = "AVAILABLE"
    return {
        "horizon": horizon,
        "status": status,
        "probability_win": p_win,
        "probability_loss": p_loss,
        "median_gain": median_gain,
        "median_loss": median_loss,
        "gross_expected_value": gross_ev,
        "spread_cost": spread,
        "slippage_cost": slippage,
        "execution_cost_status": cost_status,
        "net_expected_value": net_ev,
        "expected_shortfall_95": es,
        "transition_risk_pct": transition,
        "bad_spillover_pct": spillover,
        "prediction_interval_width": interval,
        "model_disagreement_pct": disagreement,
        "transition_risk_return_equivalent": transition_equivalent,
        "bad_spillover_return_equivalent": spillover_equivalent,
        "model_disagreement_return_equivalent": disagreement_equivalent,
        "target_volatility": target_vol,
        "forecast_volatility": forecast_vol,
        "volatility_safety": vol_safety,
        "tail_adjusted_utility": tail_adjusted,
        "managed_utility": managed,
        "sample_count": int(len(targets)),
        "formula_registry_version": FORMULA_THRESHOLD_REGISTRY["version"],
    }


def _percentile_scores(records: list[dict[str, Any]], key: str, *, higher_is_better: bool = True) -> dict[str, float | None]:
    values = [(str(row["symbol"]), finite(row.get(key))) for row in records]
    available = [(s, v) for s, v in values if v is not None]
    if not available:
        return {s: None for s, _ in values}
    series = pd.Series({s: v for s, v in available}, dtype=float)
    rank = series.rank(method="average", pct=True)
    if not higher_is_better:
        rank = 1.0 - rank + 1.0 / max(len(series), 1)
    return {s: (float(np.clip(rank.get(s), 0.0, 1.0)) if s in rank else None) for s, _ in values}


def _component_matrix(records: list[dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, dict[str, float | None]]]:
    keys = {
        "managed_utility": ("managed_utility_weighted", True),
        "directional_probability": ("calibrated_probability", True),
        "tail_safety": ("expected_shortfall_abs", False),
        "volatility_safety": ("volatility_safety", True),
        "regime_stability": ("regime_stability", True),
        "transition_safety": ("transition_risk_6h", False),
        "semivariance_safety": ("adverse_semivariance_pressure", False),
        "bad_connectedness_safety": ("adverse_connectedness_score", False),
        "frequency_connectedness_safety": ("persistent_connectedness", False),
        "tail_dependence_safety": ("tail_crowding_penalty", False),
        "duplicate_exposure_safety": ("duplicate_exposure_penalty", False),
        "mcs_membership": ("mcs_membership_score", True),
        "split_robustness": ("split_robustness_score", True),
        "data_quality": ("data_quality_score", True),
        "settlement_completeness": ("settlement_completeness", True),
        "rank_bootstrap_stability": ("rank_bootstrap_stability", True),
    }
    by_component: dict[str, dict[str, float | None]] = {}
    for component, (source_key, higher) in keys.items():
        by_component[component] = _percentile_scores(records, source_key, higher_is_better=higher)
    matrix = pd.DataFrame({component: values for component, values in by_component.items()}).sort_index()
    return matrix, by_component


def _duplicate_groups(matrix: pd.DataFrame) -> tuple[dict[str, float], list[dict[str, Any]]]:
    threshold = float(FORMULA_THRESHOLD_REGISTRY["evidence_duplicate_correlation"])
    penalties = {column: 1.0 for column in matrix.columns}
    details: list[dict[str, Any]] = []
    if len(matrix) < 3:
        return penalties, details
    correlations = matrix.corr(min_periods=3)
    for i, first in enumerate(correlations.columns):
        for second in correlations.columns[i + 1:]:
            value = finite(correlations.loc[first, second])
            if value is None or abs(value) < threshold:
                continue
            # Split overlapping evidence rather than counting it twice.
            penalties[first] = min(penalties[first], 0.5)
            penalties[second] = min(penalties[second], 0.5)
            details.append({"component_a": first, "component_b": second, "correlation": value, "penalty_each": 0.5})
    return penalties, details


def _bootstrap_rank_stability(records: list[dict[str, Any]], seed_key: str) -> dict[str, float | None]:
    if len(records) < 2:
        return {str(r["symbol"]): 100.0 for r in records}
    base = pd.DataFrame(records).set_index("symbol")
    candidate_columns = [c for c in (
        "managed_utility_weighted", "calibrated_probability", "volatility_safety",
        "regime_stability", "split_robustness_score", "data_quality_score",
    ) if c in base.columns]
    numeric = base[candidate_columns].apply(pd.to_numeric, errors="coerce")
    if numeric.notna().sum().sum() == 0:
        return {str(r["symbol"]): None for r in records}
    normalized = numeric.rank(pct=True).fillna(0.5)
    base_rank = normalized.mean(axis=1).rank(ascending=False, method="min")
    seed = int.from_bytes(seed_key.encode("utf-8")[:8].ljust(8, b"0"), "little", signed=False)
    rng = np.random.default_rng(seed)
    draws = int(FORMULA_THRESHOLD_REGISTRY["rank_bootstrap_draws"])
    ranks = {symbol: [] for symbol in normalized.index}
    for _ in range(draws):
        sampled = rng.choice(normalized.columns, size=len(normalized.columns), replace=True)
        jittered = normalized.loc[:, sampled].mean(axis=1) + rng.normal(0.0, 0.01, len(normalized))
        rank = jittered.rank(ascending=False, method="average")
        for symbol in normalized.index:
            ranks[symbol].append(float(rank.loc[symbol]))
    output: dict[str, float | None] = {}
    for symbol, values in ranks.items():
        dispersion = float(np.std(values, ddof=0))
        output[str(symbol)] = float(np.clip(100.0 * (1.0 - dispersion / max(len(records) - 1, 1)), 0.0, 100.0))
    return output


def rank_shadow_candidates(records: Sequence[Mapping[str, Any]], *, seed_key: str) -> dict[str, Any]:
    """Produce a deterministic research rank with every component retained.

    This returned rank is a shadow diagnostic only.  It must never replace or
    reorder the immutable production rank.
    """
    rows = [dict(record) for record in records]
    if not rows:
        return {"status": "NO_RECORDS", "rows": [], "components": [], "duplicate_evidence": []}
    bootstrap = _bootstrap_rank_stability(rows, seed_key)
    for row in rows:
        row["rank_bootstrap_stability"] = bootstrap.get(str(row.get("symbol")))
        row["data_quality_score"] = _quality_score(row.get("data_quality_score") or row.get("data_quality"))
        es = finite(row.get("expected_shortfall_95"))
        row["expected_shortfall_abs"] = None if es is None else abs(es)
    matrix, component_map = _component_matrix(rows)
    duplicate_penalties, duplicate_details = _duplicate_groups(matrix)
    weights = FORMULA_THRESHOLD_REGISTRY["component_weights"]
    component_rows: list[dict[str, Any]] = []
    ranked: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row["symbol"])
        numerator = 0.0
        denominator = 0.0
        available_count = 0
        for component, configured_weight in weights.items():
            score = component_map.get(component, {}).get(symbol)
            duplicate_penalty = duplicate_penalties.get(component, 1.0)
            effective_weight = float(configured_weight) * float(duplicate_penalty)
            contribution = None if score is None else float(score) * effective_weight
            if score is not None:
                numerator += contribution or 0.0
                denominator += effective_weight
                available_count += 1
            component_rows.append({
                "symbol": symbol,
                "component_name": component,
                "raw_value": row.get({
                    "managed_utility": "managed_utility_weighted",
                    "directional_probability": "calibrated_probability",
                    "tail_safety": "expected_shortfall_abs",
                    "volatility_safety": "volatility_safety",
                    "regime_stability": "regime_stability",
                    "transition_safety": "transition_risk_6h",
                    "semivariance_safety": "adverse_semivariance_pressure",
                    "bad_connectedness_safety": "adverse_connectedness_score",
                    "frequency_connectedness_safety": "persistent_connectedness",
                    "tail_dependence_safety": "tail_crowding_penalty",
                    "duplicate_exposure_safety": "duplicate_exposure_penalty",
                    "mcs_membership": "mcs_membership_score",
                    "split_robustness": "split_robustness_score",
                    "data_quality": "data_quality_score",
                    "settlement_completeness": "settlement_completeness",
                    "rank_bootstrap_stability": "rank_bootstrap_stability",
                }[component]),
                "normalized_score": score,
                "configured_weight": configured_weight,
                "duplicate_penalty": duplicate_penalty,
                "effective_weight": effective_weight,
                "weighted_contribution": contribution,
                "available": score is not None,
            })
        evidence_fraction = available_count / max(len(weights), 1)
        score_100 = None if denominator <= 0 else 100.0 * numerator / denominator
        rank_permission = "ELIGIBLE_SHADOW_ONLY" if evidence_fraction >= FORMULA_THRESHOLD_REGISTRY["minimum_rank_evidence_fraction"] else "INSUFFICIENT_EVIDENCE"
        ranked.append({**row, "shadow_score": score_100, "rank_evidence_fraction": evidence_fraction, "shadow_rank_permission": rank_permission})
    ranked.sort(key=lambda item: (item.get("shadow_score") is None, -(item.get("shadow_score") or -1e18), str(item.get("symbol"))))
    next_rank = 1
    for row in ranked:
        row["shadow_rank"] = next_rank if row.get("shadow_score") is not None else None
        if row.get("shadow_score") is not None:
            next_rank += 1
    return {
        "status": "AVAILABLE",
        "version": VERSION,
        "registry": FORMULA_THRESHOLD_REGISTRY,
        "rows": ranked,
        "components": component_rows,
        "duplicate_evidence": duplicate_details,
        "production_rank_modified": False,
    }


__all__ = [
    "VERSION", "FORMULA_THRESHOLD_REGISTRY", "horizon_managed_utility",
    "rank_shadow_candidates",
]
