"""Heavy Settings-only publisher for Field 10 rank utility v3.

The publisher consumes the same immutable daily snapshot and, when supplied,
the already-computed v2 research packs. It never writes production rank/bias and
never runs from Lunch rendering.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any
import json
import math
import sqlite3

import numpy as np
import pandas as pd

from core.field10_adaptive_regime_metrics_20260702 import compute_adaptive_regime_metrics
from core.field10_evidence_clustering_20260705 import cluster_evidence
from core.field10_probability_calibration_v2_20260705 import calibrate_from_frame
from core.field10_promotion_governance_20260705 import (
    evaluate_promotion_gates, freeze_experiment_registry, probability_of_backtest_overfitting,
)
from core.field10_rank_uncertainty_20260705 import chronological_rank_uncertainty
from core.field10_rank_utility_v3_20260705 import (
    CANDIDATE_NAME, FEATURE_VERSION, FORMULA_THRESHOLD_REGISTRY, FORMULA_VERSION,
    PROMOTION_STATUS, REGISTRY_HASH, THRESHOLD_VERSION, horizon_utility_v3,
    rank_v3_candidates, strategy_targets,
)
from core.field10_research_common_20260705 import (
    HORIZONS, audit_system_time, build_identity, canonical_json, connect,
    deterministic_hash, exact_completed_h1, finite, identity_columns,
    insert_or_ignore, load_snapshot_contract, normalize_symbol,
)
from core.field10_structural_stability_v2_20260705 import structural_stability_evidence

VERSION = "field10-v3-candidate-orchestrator-20260705-v1"
V3_TABLES = (
    "field10_probability_calibration_v2", "field10_structural_break_v2",
    "field10_rank_uncertainty", "field10_evidence_clusters",
    "field10_candidate_experiments", "field10_pbo_results",
    "field10_rank_components_v3", "field10_promotion_decisions",
)


def schema_ready_v3(path: Path | str) -> tuple[bool, list[str]]:
    try:
        with connect(path, read_only=True) as conn:
            present = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except Exception as exc:
        return False, [f"database unavailable: {type(exc).__name__}: {exc}"]
    missing = sorted(set(V3_TABLES) - present)
    return not missing, missing


def _v3_identity(identity: Any, *, status: str, missing_reason: str | None = None) -> dict[str, Any]:
    payload = identity_columns(identity, validation_status=status, missing_reason=missing_reason)
    payload.update({"model_version": VERSION, "feature_version": FEATURE_VERSION,
                    "formula_version": FORMULA_VERSION, "threshold_version": THRESHOLD_VERSION})
    return payload


def _content(payload: Mapping[str, Any]) -> str:
    excluded = {"content_hash", "created_system_time"}
    return deterministic_hash({key: value for key, value in payload.items() if key not in excluded})


def _persist(conn: sqlite3.Connection, table: str, payload: Mapping[str, Any]) -> int:
    record = dict(payload)
    record.setdefault("created_system_time", audit_system_time())
    record.setdefault("content_hash", _content(record))
    return insert_or_ignore(conn, table, record)


def _as_fraction(value: Any) -> float | None:
    number = finite(value)
    if number is None:
        return None
    return number / 100.0 if abs(number) > 1.0 else number


def _bounded_quality(value: Any, *, lower: float = 0.0, upper: float = 100.0) -> float | None:
    number = finite(value)
    return None if number is None else float(np.clip(number, lower, upper))


def _costs_from_pack(pack: Mapping[str, Any]) -> tuple[float | None, float | None, str]:
    utility = pack.get("utility") if isinstance(pack.get("utility"), Mapping) else {}
    for horizon in HORIZONS:
        row = utility.get(horizon) if isinstance(utility.get(horizon), Mapping) else {}
        spread, slippage = finite(row.get("spread_cost")), finite(row.get("slippage_cost"))
        if spread is not None or slippage is not None:
            return spread, slippage, str(row.get("cost_evidence_status") or row.get("execution_cost_status") or "PARTIAL")
    return None, None, "MISSING_PROVIDER_COST_EVIDENCE"


def _transition_from_pack(pack: Mapping[str, Any], horizon: int) -> float | None:
    utility = pack.get("utility") if isinstance(pack.get("utility"), Mapping) else {}
    row = utility.get(horizon) if isinstance(utility.get(horizon), Mapping) else {}
    return finite(row.get("transition_risk_pct"))


def _model_disagreement(pack: Mapping[str, Any], horizon: int) -> float | None:
    utility = pack.get("utility") if isinstance(pack.get("utility"), Mapping) else {}
    row = utility.get(horizon) if isinstance(utility.get(horizon), Mapping) else {}
    return finite(row.get("model_disagreement_pct"))


def _candidate_performance_matrix(packs: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    profiles = FORMULA_THRESHOLD_REGISTRY["horizon_weight_candidates"]
    candidate_series: dict[str, list[pd.Series]] = {name: [] for name in profiles}
    for pack in packs.values():
        frame = pack.get("frame")
        bias = str(pack.get("bias") or "WAIT")
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        targets = {h: strategy_targets(frame, bias=bias, horizon=h) for h in HORIZONS}
        for name, weights in profiles.items():
            combined = sum(float(weights[h]) * targets[h] for h in HORIZONS)
            candidate_series[name].append(combined.rename(str(pack.get("identity").symbol if pack.get("identity") else "symbol")))
    aggregate: dict[str, pd.Series] = {}
    for name, series_list in candidate_series.items():
        if series_list:
            aggregate[name] = pd.concat(series_list, axis=1).mean(axis=1, skipna=True)
    if not aggregate:
        return pd.DataFrame()
    chronological = pd.DataFrame(aggregate).dropna(how="all")
    if len(chronological) < 80:
        return pd.DataFrame()
    bins = min(12, max(8, len(chronological) // 40))
    labels = pd.qcut(pd.Series(np.arange(len(chronological))), q=bins, labels=False, duplicates="drop")
    return chronological.groupby(labels.to_numpy()).mean()


def _settled_rank_panel(packs: Mapping[str, Mapping[str, Any]], weights: Mapping[int, float]) -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    for symbol, pack in packs.items():
        frame = pack.get("frame")
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        combined = sum(float(weights[h]) * strategy_targets(frame, bias=str(pack.get("bias") or "WAIT"), horizon=h) for h in HORIZONS)
        time = pd.to_datetime(frame.get("time", frame.index), errors="coerce", utc=True)
        combined.index = time
        series[symbol] = combined
    return pd.DataFrame(series).sort_index().dropna(how="all") if series else pd.DataFrame()


def _cluster_observations(per_symbol: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for symbol, item in per_symbol.items():
        for horizon, utility in item.get("horizons", {}).items():
            calibration = item.get("calibrations", {}).get(horizon, {})
            conformal = calibration.get("conformal") if isinstance(calibration.get("conformal"), Mapping) else {}
            rows.append({
                "symbol_horizon": f"{symbol}:{horizon}",
                "horizon_utility": utility.get("managed_utility"),
                "probability_calibration": None if calibration.get("expected_calibration_error") is None else 100.0 * (1.0 - min(float(calibration["expected_calibration_error"]) / 0.25, 1.0)),
                "conformal_coverage": None if conformal.get("empirical_coverage") is None else 100.0 * (1.0 - min(abs(float(conformal["empirical_coverage"]) - 0.90) / 0.10, 1.0)),
                "tail_safety": None if utility.get("es_var_severity_ratio") is None else 100.0 / (1.0 + float(utility["es_var_severity_ratio"])),
                "structural_stability": item.get("structural_quality"),
                "connectedness_safety": item.get("connectedness_quality"),
                "data_quality": item.get("data_quality"),
                "rank_stability": None,
                "absolute_utility": utility.get("managed_utility"),
            })
    return pd.DataFrame(rows).set_index("symbol_horizon") if rows else pd.DataFrame()


def publish_field10_rank_utility_v3_candidate(
    state: MutableMapping[str, Any], *, daily_snapshot_id: str,
    selected_symbols: Sequence[str], path: Path | str,
    precomputed: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    ready, missing = schema_ready_v3(path)
    if not ready:
        return {"ok": False, "status": "MIGRATION_REQUIRED", "missing_tables": missing,
                "candidate": CANDIDATE_NAME, "production_rank_modified": False, "locked_bias_modified": False}
    meta, parents = load_snapshot_contract(daily_snapshot_id, path=path)
    if not meta or not parents:
        return {"ok": False, "status": "PARENT_SNAPSHOT_UNAVAILABLE", "daily_snapshot_id": daily_snapshot_id}
    requested = [normalize_symbol(symbol) for symbol in selected_symbols if normalize_symbol(symbol)]
    parent_symbols = [normalize_symbol(row.get("symbol")) for row in parents]
    if set(requested) != set(parent_symbols):
        return {"ok": False, "status": "IDENTITY_MISMATCH", "requested": requested, "parent": parent_symbols}

    precomputed = dict(precomputed or {})
    existing_calculated = precomputed.get("calculated") if isinstance(precomputed.get("calculated"), Mapping) else {}
    connected = precomputed.get("connected") if isinstance(precomputed.get("connected"), Mapping) else {}
    packs: dict[str, dict[str, Any]] = {}
    for parent in parents:
        symbol = normalize_symbol(parent.get("symbol"))
        if symbol in existing_calculated:
            packs[symbol] = dict(existing_calculated[symbol])
            continue
        identity = build_identity(meta, parent, path=path)
        frame, reasons = exact_completed_h1(state, identity, required_rows=600)
        packs[symbol] = {"parent": parent, "identity": identity, "frame": frame, "reasons": reasons,
                         "bias": str(parent.get("less_risky_bias") or parent.get("stable_daily_bias") or "WAIT").upper(),
                         "har": {}, "semivariance": {}, "tail": {}, "mcs_rows": {}, "summary": {}}

    per_symbol: dict[str, dict[str, Any]] = {}
    calibration_rows: list[tuple[Any, int, dict[str, Any]]] = []
    structural_rows: list[tuple[Any, dict[str, Any]]] = []
    for symbol, pack in packs.items():
        identity = pack.get("identity")
        parent = pack.get("parent") if isinstance(pack.get("parent"), Mapping) else {}
        frame = pack.get("frame")
        reasons = list(pack.get("reasons") or [])
        bias = str(pack.get("bias") or parent.get("less_risky_bias") or parent.get("stable_daily_bias") or "WAIT").upper()
        if identity is None or not isinstance(frame, pd.DataFrame) or frame.empty:
            per_symbol[symbol] = {"identity": identity, "parent": parent, "frame": frame, "bias": bias,
                                  "status": "IDENTITY_OR_600H1_UNAVAILABLE", "reasons": reasons, "horizons": {}, "calibrations": {}}
            continue
        adaptive = compute_adaptive_regime_metrics(frame, timeframe=identity.get("timeframe") if isinstance(identity, Mapping) else parent.get("timeframe"))
        calibration_by_horizon: dict[int, dict[str, Any]] = {}
        utility_by_horizon: dict[int, dict[str, Any]] = {}
        spread, slippage, cost_status = _costs_from_pack(pack)
        har = pack.get("har") if isinstance(pack.get("har"), Mapping) else {}
        tail = pack.get("tail") if isinstance(pack.get("tail"), Mapping) else {}
        semivariance = pack.get("semivariance") if isinstance(pack.get("semivariance"), Mapping) else {}
        asym = connected.get("asymmetric", {}).get("symbols", {}).get(symbol, {}) if connected else {}
        freq = connected.get("frequency", {}).get("symbols", {}).get(symbol, {}) if connected else {}
        cop = connected.get("copula", {}).get("symbols", {}).get(symbol, {}) if connected else {}
        for horizon in HORIZONS:
            parent_raw = parent.get(f"probability_profit_{horizon}h")
            calibration = calibrate_from_frame(frame, bias=bias, horizon=horizon,
                                               current_raw_probability=_as_fraction(parent_raw),
                                               seed_key=f"{daily_snapshot_id}:{symbol}:{horizon}")
            calibration_by_horizon[horizon] = calibration
            conformal = calibration.get("conformal") if isinstance(calibration.get("conformal"), Mapping) else {}
            har_row = har.get("horizons", {}).get(horizon, {}) if isinstance(har.get("horizons"), Mapping) else {}
            tail_row = tail.get("horizons", {}).get(horizon, {}) if isinstance(tail.get("horizons"), Mapping) else {}
            adverse_semivar = semivariance.get("downside_semivariance") or semivariance.get("adverse_semivariance")
            utility = horizon_utility_v3(
                frame, bias=bias, horizon=horizon,
                calibrated_probability=calibration.get("calibrated_probability"), spread_cost=spread, slippage_cost=slippage,
                directional_var_95=tail_row.get("directional_var_95"), expected_shortfall_95=tail_row.get("directional_expected_shortfall_95"),
                forecast_volatility=har_row.get("forecast_volatility"), adverse_semivariance=adverse_semivar,
                transition_risk_pct=_transition_from_pack(pack, horizon), short_connectedness_pct=freq.get("connectedness_short"),
                persistent_connectedness_pct=freq.get("connectedness_persistent"),
                conformal_lower_return=conformal.get("conformal_lower_return"), conformal_median_return=conformal.get("conformal_median_return"),
                conformal_upper_return=conformal.get("conformal_upper_return"), probability_calibration_error=calibration.get("expected_calibration_error"),
                model_disagreement_pct=_model_disagreement(pack, horizon),
            )
            utility["cost_evidence_status"] = cost_status
            utility_by_horizon[horizon] = utility
            calibration_rows.append((identity, horizon, calibration))
        panel6 = calibration_by_horizon.get(6, {}).get("panel")
        residuals = None
        if isinstance(panel6, pd.DataFrame) and not panel6.empty:
            residuals = panel6["outcome"] - panel6["raw_probability"]
        structural = structural_stability_evidence(frame, calibration_residuals=residuals, adaptive_regime=adaptive)
        structural_rows.append((identity, structural))
        active_weights = FORMULA_THRESHOLD_REGISTRY["horizon_weight_candidates"][FORMULA_THRESHOLD_REGISTRY["active_research_weights"]]
        available = [(h, finite(utility_by_horizon[h].get("managed_utility"))) for h in HORIZONS]
        available = [(h, value) for h, value in available if value is not None]
        aggregate_utility = None if not available else sum(active_weights[h] * value for h, value in available) / sum(active_weights[h] for h, _ in available)
        ece_values = [finite(calibration_by_horizon[h].get("expected_calibration_error")) for h in HORIZONS]
        ece_values = [value for value in ece_values if value is not None]
        conformal_coverages = [finite(calibration_by_horizon[h].get("conformal", {}).get("empirical_coverage")) for h in HORIZONS]
        conformal_coverages = [value for value in conformal_coverages if value is not None]
        severity_values = [finite(utility_by_horizon[h].get("es_var_severity_ratio")) for h in HORIZONS]
        severity_values = [value for value in severity_values if value is not None]
        persistent = finite(freq.get("connectedness_persistent"))
        structural_quality = 100.0 * (1.0 - float(structural.get("break_strength") or 0.0))
        if finite(structural.get("regime_persistence")) is not None:
            structural_quality *= 0.5 + 0.5 * float(structural["regime_persistence"])
        connected_quality = None if persistent is None else float(np.clip(100.0 - persistent, 0.0, 100.0))
        summary = pack.get("summary") if isinstance(pack.get("summary"), Mapping) else {}
        data_quality = finite(summary.get("data_quality_score"))
        if data_quality is None:
            data_quality = 100.0 if not reasons and len(frame) == 600 else max(0.0, 100.0 - 15.0 * len(reasons))
        utility_scale = np.nanmedian([abs(float(value)) for _, value in available]) if available else np.nan
        utility_quality = None if aggregate_utility is None or not np.isfinite(utility_scale) else float(100.0 / (1.0 + math.exp(-aggregate_utility / max(utility_scale, 1e-8))))
        component_values = {
            "horizon_utility": utility_quality,
            "probability_calibration": None if not ece_values else float(100.0 * (1.0 - min(np.mean(ece_values) / 0.25, 1.0))),
            "conformal_coverage": None if not conformal_coverages else float(100.0 * (1.0 - min(abs(np.mean(conformal_coverages) - 0.90) / 0.10, 1.0))),
            "tail_safety": None if not severity_values else float(100.0 / (1.0 + np.mean(severity_values))),
            "structural_stability": float(np.clip(structural_quality, 0.0, 100.0)),
            "connectedness_safety": connected_quality,
            "data_quality": data_quality,
            "rank_stability": None,
            "absolute_utility": utility_quality,
        }
        per_symbol[symbol] = {
            "identity": identity, "parent": parent, "frame": frame, "bias": bias, "status": "CALCULATED",
            "horizons": utility_by_horizon, "calibrations": calibration_by_horizon, "structural": structural,
            "adaptive": adaptive, "component_values": component_values, "absolute_managed_utility": aggregate_utility,
            "structural_quality": structural_quality, "connectedness_quality": connected_quality, "data_quality": data_quality,
            "duplicate_exposure_penalty": finite(cop.get("duplicate_exposure_penalty")),
            "persistent_connectedness_penalty": persistent,
            "cluster_concentration_penalty": finite(cop.get("tail_crowding_penalty")),
            "mcs_rows": pack.get("mcs_rows") or {}, "reasons": reasons,
        }

    observations = _cluster_observations(per_symbol)
    clustering = cluster_evidence(observations, FORMULA_THRESHOLD_REGISTRY["component_weights"])
    records: list[dict[str, Any]] = []
    for symbol, item in per_symbol.items():
        if item.get("status") != "CALCULATED":
            continue
        parent = item["parent"]
        record = {"symbol": symbol, "production_rank": parent.get("daily_rank"), "locked_bias": item["bias"],
                  "absolute_managed_utility": item["absolute_managed_utility"],
                  "structural_entry_permission": item["structural"].get("structural_entry_permission"),
                  "identity_integrity_pass": not item["reasons"] and len(item["frame"]) == 600,
                  "data_quality_score": item["data_quality"]}
        record.update(item["component_values"])
        for name, value in item["component_values"].items():
            record[f"historical_quality::{name}"] = value
        records.append(record)
    first_rank = rank_v3_candidates(records, cluster_effective_weights=clustering.get("effective_weights"))
    base_scores = {row["symbol"]: row.get("coverage_adjusted_score") or 0.0 for row in first_rank["rows"]}
    active_weights = FORMULA_THRESHOLD_REGISTRY["horizon_weight_candidates"][FORMULA_THRESHOLD_REGISTRY["active_research_weights"]]
    uncertainty = chronological_rank_uncertainty(
        _settled_rank_panel(packs, active_weights), base_scores=base_scores,
        snapshot_id=daily_snapshot_id, formula_version=FORMULA_VERSION, horizon=6, draws=500,
    )
    uncertainty_map = {row["symbol"]: row for row in uncertainty.get("rows", [])}
    for record in records:
        u = uncertainty_map.get(record["symbol"], {})
        stability = None if u.get("rank_standard_deviation") is None else float(np.clip(100.0 - 20.0 * float(u["rank_standard_deviation"]), 0.0, 100.0))
        record["rank_stability"] = stability
        record["historical_quality::rank_stability"] = stability
    final_rank = rank_v3_candidates(records, cluster_effective_weights=clustering.get("effective_weights"))
    rank_map = {row["symbol"]: row for row in final_rank["rows"]}
    component_map: dict[str, list[dict[str, Any]]] = {}
    for component in final_rank["components"]:
        component_map.setdefault(str(component["symbol"]), []).append(component)

    # Diversification-adjusted rank remains separate from standalone rank.
    diversification_rows = []
    for symbol, ranked in rank_map.items():
        item = per_symbol[symbol]
        penalties = [finite(item.get("duplicate_exposure_penalty")), finite(item.get("persistent_connectedness_penalty")), finite(item.get("cluster_concentration_penalty"))]
        penalties = [max(0.0, value) for value in penalties if value is not None]
        total_penalty = min(40.0, sum(penalties) / max(len(penalties), 1)) if penalties else 0.0
        diversification_rows.append((symbol, (ranked.get("coverage_adjusted_score") or 0.0) - total_penalty))
    diversification_rows.sort(key=lambda pair: (-pair[1], pair[0]))
    diversification_rank = {symbol: index + 1 for index, (symbol, _) in enumerate(diversification_rows)}

    registry = freeze_experiment_registry({
        "candidate_name": CANDIDATE_NAME, "formula_hash": REGISTRY_HASH, "feature_version": FEATURE_VERSION,
        "threshold_version": THRESHOLD_VERSION, "horizon_weights": FORMULA_THRESHOLD_REGISTRY["horizon_weight_candidates"],
        "risk_coefficients": FORMULA_THRESHOLD_REGISTRY["risk_coefficients"], "calibration_method": "PLATT_VS_ISOTONIC_CHRONOLOGICAL",
        "structural_break_settings": FORMULA_THRESHOLD_REGISTRY["structural_veto"], "normalization_settings": FORMULA_THRESHOLD_REGISTRY["normalization"],
        "candidate_model_list": list(FORMULA_THRESHOLD_REGISTRY["horizon_weight_candidates"]),
        "sample_period": {"broker_day": meta.get("broker_day"), "latest_completed_h1": meta.get("latest_completed_h1"), "rows_per_symbol": 600},
        "symbols": parent_symbols, "timeframe": "H1", "spread_slippage_treatment": "EXACT_PROVIDER_ONLY_NO_FABRICATION",
    })
    pbo = probability_of_backtest_overfitting(_candidate_performance_matrix(packs))
    inserted = {table: 0 for table in V3_TABLES}
    created = audit_system_time()
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for identity, horizon, calibration in calibration_rows:
                panel = calibration.get("panel") if isinstance(calibration.get("panel"), pd.DataFrame) else pd.DataFrame()
                conformal = calibration.get("conformal") if isinstance(calibration.get("conformal"), Mapping) else {}
                payload = _v3_identity(identity, status=str(calibration.get("calibration_permission") or "UNAVAILABLE"))
                payload.update({
                    "horizon": horizon, "direction": per_symbol[identity.symbol]["bias"],
                    "raw_probability": calibration.get("raw_probability"), "calibrated_probability": calibration.get("calibrated_probability"),
                    "calibration_method": calibration.get("calibration_method"), "brier_score": calibration.get("brier_score"),
                    "log_loss": calibration.get("log_loss"), "expected_calibration_error": calibration.get("expected_calibration_error"),
                    "calibration_slope": calibration.get("calibration_slope"), "calibration_intercept": calibration.get("calibration_intercept"),
                    "calibration_sample_count": int(calibration.get("calibration_sample_count") or 0),
                    "test_sample_count": int(calibration.get("test_sample_count") or 0), "calibration_permission": calibration.get("calibration_permission"),
                    "purge_hours": horizon, "embargo_hours": horizon, "final_test_used_for_fit": 0,
                    "conformal_lower_return": conformal.get("conformal_lower_return"), "conformal_median_return": conformal.get("conformal_median_return"),
                    "conformal_upper_return": conformal.get("conformal_upper_return"), "conformal_interval_width": conformal.get("conformal_interval_width"),
                    "conformal_coverage": conformal.get("empirical_coverage"), "reliability_bins_json": canonical_json(calibration.get("reliability_bins") or []),
                    "settled_forecast_count": int(len(panel)), "settlement_status": "SETTLED_CHRONOLOGICAL" if len(panel) else "INSUFFICIENT",
                    "evidence_json": canonical_json({key: value for key, value in calibration.items() if key != "panel"}), "created_system_time": created,
                })
                inserted["field10_probability_calibration_v2"] += _persist(conn, "field10_probability_calibration_v2", payload)
            for identity, structural in structural_rows:
                payload = _v3_identity(identity, status=str(structural.get("status") or "UNAVAILABLE"))
                payload.update({
                    "last_structural_break_time": structural.get("last_structural_break_time"), "break_strength": structural.get("break_strength"),
                    "post_break_h1_count": structural.get("post_break_h1_count"), "pre_post_distribution_distance": structural.get("pre_post_distribution_distance"),
                    "current_regime_probability": structural.get("current_regime_probability"), "second_regime_probability": structural.get("second_regime_probability"),
                    "regime_entropy": structural.get("regime_entropy"), "regime_persistence": structural.get("regime_persistence"),
                    "structural_entry_permission": structural.get("structural_entry_permission"), "actionable_rank_permission": structural.get("actionable_rank_permission"),
                    "feature_breaks_json": canonical_json(structural.get("feature_breaks") or {}), "evidence_json": canonical_json(structural),
                    "created_system_time": created,
                })
                inserted["field10_structural_break_v2"] += _persist(conn, "field10_structural_break_v2", payload)
            for row in uncertainty.get("rows", []):
                item = per_symbol[row["symbol"]]; identity = item["identity"]
                payload = _v3_identity(identity, status=str(uncertainty.get("status") or "UNAVAILABLE"))
                payload.update({key: row.get(key) for key in (
                    "median_bootstrap_rank", "rank_lower_90", "rank_upper_90", "probability_rank_1", "probability_top_3", "probability_top_4",
                    "rank_standard_deviation", "top_3_membership_stability", "rank_turnover_risk", "rank_confidence_status")})
                payload.update({"bootstrap_method": uncertainty.get("method"), "block_length": uncertainty.get("block_length"),
                                "bootstrap_seed": uncertainty.get("seed"), "bootstrap_draw_count": uncertainty.get("draws"),
                                "sample_count": uncertainty.get("sample_count"), "evidence_json": canonical_json(uncertainty), "created_system_time": created})
                inserted["field10_rank_uncertainty"] += _persist(conn, "field10_rank_uncertainty", payload)
            for audit in clustering.get("audit_rows", []):
                # Cluster evidence is universe-level and repeated per symbol only when that component contributes.
                for symbol, item in per_symbol.items():
                    if item.get("status") != "CALCULATED":
                        continue
                    identity = item["identity"]
                    payload = _v3_identity(identity, status=str(clustering.get("status") or "UNAVAILABLE"))
                    payload.update({"component_name": audit.get("component"), "cluster_id": str(audit.get("cluster_id")),
                                    "configured_weight": audit.get("configured_weight"), "cluster_budget": audit.get("cluster_budget"),
                                    "effective_weight": audit.get("effective_weight"), "duplicate_penalty": audit.get("duplicate_penalty"),
                                    "effective_number_independent": clustering.get("effective_number_of_independent_components"),
                                    "dependence_threshold": clustering.get("threshold"), "evidence_json": canonical_json(clustering), "created_system_time": created})
                    inserted["field10_evidence_clusters"] += _persist(conn, "field10_evidence_clusters", payload)
            registry_identity = next((item["identity"] for item in per_symbol.values() if item.get("identity") is not None), None)
            if registry_identity is not None:
                payload = _v3_identity(registry_identity, status="FROZEN_BEFORE_EVALUATION")
                payload.update({"symbol": "__UNIVERSE__", "candidate_name": CANDIDATE_NAME,
                                "experiment_registry_hash": registry["experiment_registry_hash"], "registered_before_test": int(registry["registered_before_test"]),
                                "frozen_registry_json": registry["frozen_registry_json"], "candidate_count": len(FORMULA_THRESHOLD_REGISTRY["horizon_weight_candidates"]),
                                "evidence_json": canonical_json(registry), "created_system_time": created})
                inserted["field10_candidate_experiments"] += _persist(conn, "field10_candidate_experiments", payload)
                pbo_payload = _v3_identity(registry_identity, status=str(pbo.get("status") or "UNAVAILABLE"))
                pbo_payload.update({"symbol": "__UNIVERSE__", "experiment_registry_hash": registry["experiment_registry_hash"],
                                    "pbo_probability": pbo.get("pbo_probability"), "oos_rank_logit": pbo.get("oos_rank_logit"),
                                    "in_sample_winner": pbo.get("in_sample_winner"), "out_of_sample_rank": pbo.get("out_of_sample_rank"),
                                    "performance_degradation": pbo.get("performance_degradation"), "number_of_candidates": pbo.get("number_of_candidates"),
                                    "promotion_permission": pbo.get("promotion_permission"), "evidence_json": canonical_json(pbo), "created_system_time": created})
                inserted["field10_pbo_results"] += _persist(conn, "field10_pbo_results", pbo_payload)
            for symbol, ranked in rank_map.items():
                item = per_symbol[symbol]; identity = item["identity"]; u = uncertainty_map.get(symbol, {})
                h3, h6 = item["horizons"].get(3, {}), item["horizons"].get(6, {})
                fallback_level = "NONE" if all(str(item["calibrations"][h].get("calibration_method")) != "UNCALIBRATED" for h in HORIZONS) else "CALIBRATION_RAW_PROBABILITY"
                common = {
                    "evidence_coverage": ranked.get("evidence_coverage"), "evidence_penalty": ranked.get("evidence_penalty"),
                    "raw_research_score": ranked.get("raw_research_score"), "coverage_adjusted_score": ranked.get("coverage_adjusted_score"),
                    "research_rank": ranked.get("research_rank_v3"), "diversification_adjusted_rank": diversification_rank.get(symbol),
                    "production_rank": item["parent"].get("daily_rank"), "locked_bias": item["bias"], "entry_permission": ranked.get("entry_permission_v3"),
                    "probability_top_3": u.get("probability_top_3"), "rank_lower_90": u.get("rank_lower_90"), "rank_upper_90": u.get("rank_upper_90"),
                    "expected_return_3h": h3.get("net_expected_value"), "expected_return_6h": h6.get("net_expected_value"),
                    "expected_shortfall_6h": h6.get("directional_expected_shortfall_95"), "transition_risk_6h": h6.get("transition_risk_pct"),
                    "reliability": ranked.get("coverage_adjusted_score"), "data_quality": item["data_quality"], "fallback_level": fallback_level,
                    "promotion_status": PROMOTION_STATUS,
                }
                summary_payload = _v3_identity(identity, status="SHADOW_ONLY")
                summary_payload.update({"horizon": 0, "component_name": "__SUMMARY__", "raw_value": ranked.get("coverage_adjusted_score"),
                                        "historical_quality_score": None, "cross_sectional_percentile": None, "normalized_component_score": None,
                                        "configured_weight": None, "cluster_id": None, "cluster_budget": None, "effective_weight": None,
                                        "weighted_contribution": None, **common,
                                        "formula_contributions_json": canonical_json({h: item["horizons"][h].get("contributions") for h in HORIZONS}),
                                        "summary_json": canonical_json({**ranked, "uncertainty": u, "structural": item["structural"],
                                                                        "duplicate_currency_exposure_penalty": item.get("duplicate_exposure_penalty"),
                                                                        "persistent_connectedness_penalty": item.get("persistent_connectedness_penalty"),
                                                                        "cluster_concentration_penalty": item.get("cluster_concentration_penalty")}),
                                        "evidence_json": canonical_json({"horizons": item["horizons"], "calibration": {h: {k: v for k, v in item["calibrations"][h].items() if k != "panel"} for h in HORIZONS}}),
                                        "created_system_time": created})
                inserted["field10_rank_components_v3"] += _persist(conn, "field10_rank_components_v3", summary_payload)
                for component in component_map.get(symbol, []):
                    cluster_id = clustering.get("clusters", {}).get(component["component_name"])
                    cluster_budget = clustering.get("cluster_budgets", {}).get(cluster_id)
                    payload = _v3_identity(identity, status="COMPONENT_AUDIT")
                    payload.update({"horizon": 0, "component_name": component["component_name"], "raw_value": component.get("raw_value"),
                                    "historical_quality_score": component.get("historical_quality_score"), "cross_sectional_percentile": component.get("cross_sectional_percentile"),
                                    "normalized_component_score": component.get("normalized_component_score"), "configured_weight": component.get("configured_weight"),
                                    "cluster_id": None if cluster_id is None else str(cluster_id), "cluster_budget": cluster_budget,
                                    "effective_weight": component.get("effective_weight"), "weighted_contribution": component.get("weighted_contribution"),
                                    **common, "formula_contributions_json": canonical_json({}), "summary_json": canonical_json(component),
                                    "evidence_json": canonical_json(component), "created_system_time": created})
                    inserted["field10_rank_components_v3"] += _persist(conn, "field10_rank_components_v3", payload)
                calibration6 = item["calibrations"].get(6, {}); conformal6 = calibration6.get("conformal", {})
                mcs6 = item.get("mcs_rows", {}).get(6, []) if isinstance(item.get("mcs_rows"), Mapping) else []
                mcs_survives = any(bool(row.get("mcs_membership")) for row in mcs6)
                promotion = evaluate_promotion_gates({
                    "net_oos_utility": item["absolute_managed_utility"], "brier_delta": 0.0 if calibration6.get("brier_score") is not None else None,
                    "ece_delta": 0.0 if calibration6.get("expected_calibration_error") is not None else None,
                    "conformal_coverage": conformal6.get("empirical_coverage"), "mcs_survives": mcs_survives,
                    "pbo_probability": pbo.get("pbo_probability"), "pbo_threshold": FORMULA_THRESHOLD_REGISTRY["pbo_threshold"],
                    "evidence_coverage": ranked.get("evidence_coverage"), "structural_entry_permission": item["structural"].get("structural_entry_permission"),
                    "identity_integrity_pass": ranked.get("identity_integrity_pass"),
                })
                decision_payload = _v3_identity(identity, status=promotion["promotion_status"])
                decision_payload.update({"decision": "SHADOW_ONLY", "decision_version": "field10-v3-promotion-decision-20260705-v1",
                                         "decision_reason": promotion["promotion_status"], "all_gates_pass": int(promotion["all_research_gates_pass"]),
                                         "explicit_decision_present": 0, "gate_results_json": canonical_json(promotion["gate_results"]),
                                         "production_rank_before": item["parent"].get("daily_rank"), "production_rank_after": item["parent"].get("daily_rank"),
                                         "locked_bias_before": item["bias"], "locked_bias_after": item["bias"],
                                         "evidence_json": canonical_json(promotion), "created_system_time": created})
                inserted["field10_promotion_decisions"] += _persist(conn, "field10_promotion_decisions", decision_payload)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    report = {
        "ok": True, "status": "PUBLISHED_SHADOW_ONLY", "candidate": CANDIDATE_NAME,
        "daily_snapshot_id": daily_snapshot_id, "parent_run_id": meta.get("parent_run_id"),
        "symbols": parent_symbols, "inserted": inserted, "formula_registry_hash": REGISTRY_HASH,
        "experiment_registry_hash": registry["experiment_registry_hash"], "pbo": pbo,
        "uncertainty_status": uncertainty.get("status"), "evidence_clustering_status": clustering.get("status"),
        "production_rank_modified": False, "locked_bias_modified": False,
        "same_canonical_snapshot": True, "runtime_migration_executed": False,
        "version": VERSION,
    }
    state["field10_rank_utility_v3_research_candidate_20260705"] = report
    return report


def load_v3_summary(daily_snapshot_id: str | None = None, *, path: Path | str) -> pd.DataFrame:
    ready, _ = schema_ready_v3(path)
    if not ready:
        return pd.DataFrame()
    with connect(path, read_only=True) as conn:
        if not daily_snapshot_id:
            found = conn.execute("SELECT daily_snapshot_id FROM field10_rank_components_v3 WHERE component_name='__SUMMARY__' ORDER BY created_system_time DESC LIMIT 1").fetchone()
            daily_snapshot_id = None if found is None else str(found[0])
        if not daily_snapshot_id:
            return pd.DataFrame()
        return pd.read_sql_query("SELECT * FROM field10_rank_components_v3 WHERE daily_snapshot_id=? AND component_name='__SUMMARY__' ORDER BY research_rank,symbol", conn, params=(daily_snapshot_id,))


__all__ = ["VERSION", "V3_TABLES", "schema_ready_v3", "publish_field10_rank_utility_v3_candidate", "load_v3_summary"]
