"""Single lightweight orchestration layer for the ten 2026-06-21 concepts."""
from __future__ import annotations

from typing import Any, Mapping
import os
import resource

import numpy as np
import pandas as pd

from core.conditional_predictive_ability_20260621 import evaluate_conditional_predictive_ability
from core.superior_predictive_ability_20260621 import evaluate_superior_predictive_ability
from core.covariate_shift_conformal_20260621 import build_covariate_shift_conformal
from core.fforma_shadow_weighting_20260621 import shadow_weights
from core.fixed_share_expert_tracker_20260621 import fixed_share_update
from core.ml_production_readiness_score_20260621 import build_ml_production_readiness_score
from core.sliding_monitoring_statistics_20260621 import update_operational_counters
from core.bounded_quantile_monitoring_20260621 import update_quantile_summaries
from core.research_validation_common_20260621 import finite, mapping, profile_int, stable_hash, utc_now_iso
from core.research_validation_store_20260621 import BUNDLE_KEY, latest_expert_state

VERSION = "research-validation-layer-20260621-v1"


def _column(frame: pd.DataFrame, *names: str) -> pd.Series:
    lookup = {str(c).strip().lower(): c for c in frame.columns}
    for name in names:
        if name.lower() in lookup:
            return frame[lookup[name.lower()]]
    return pd.Series(np.nan, index=frame.index)


def _current_covariates(canonical: Mapping[str, Any], frame: pd.DataFrame) -> dict[str, Any]:
    latest = frame.iloc[-1] if isinstance(frame, pd.DataFrame) and not frame.empty else pd.Series(dtype=object)
    regime = mapping(canonical.get("regime"))
    advanced = mapping(canonical.get("advanced_reliability_shift"))
    market = mapping(canonical.get("market"))
    feature = mapping(canonical.get("feature_snapshot"))
    def pick(*keys: str) -> Any:
        for key in keys:
            for source in (feature, regime, advanced, market, canonical):
                value = source.get(key) if isinstance(source, Mapping) else None
                if value not in (None, ""): return value
            if key in latest.index and latest.get(key) not in (None, ""): return latest.get(key)
        return None
    session = pick("session", "market_session")
    session_code = {"ASIA": 0, "LONDON": 1, "LONDON_NY_OVERLAP": 2, "NEW_YORK": 3, "LATE_NY": 4}.get(str(session).upper(), -1)
    return {
        "atr_percentile": pick("atr_percentile", "atr_pct"), "adx": pick("adx", "ADX"),
        "di_spread": pick("di_spread", "di_separation"), "di_separation": pick("di_separation", "di_spread"),
        "session": session, "session_code": session_code,
        "major_regime": pick("major_regime", "current_regime", "h1_regime"),
        "regime_age": pick("regime_age", "days_in_regime"),
        "compression_score": pick("compression_score", "compression"), "compression": pick("compression", "compression_score"),
        "event_intensity": pick("event_intensity", "event_score"), "event_score": pick("event_score", "event_intensity"),
        "recent_residual_scale": pick("recent_residual_scale", "residual_scale"),
        "mmd_shift_score": mapping(advanced.get("mmd")).get("score") or pick("mmd_shift_score"),
        "recent_path_mae": pick("recent_path_mae", "mae"), "recent_path_crps": pick("recent_path_crps", "crps"),
        "coverage_error": pick("coverage_error"), "residual_skew": pick("residual_skew"),
        "forecast_disagreement": pick("forecast_disagreement", "model_disagreement"),
        "shift_score": pick("shift_score", "mmd_shift_score"),
    }


def _existing_intervals(canonical: Mapping[str, Any]) -> dict[str, Any]:
    horizons = mapping(mapping(canonical.get("forecasts")).get("horizons"))
    result: dict[str, Any] = {}
    for horizon in range(1, 7):
        row = mapping(horizons.get(f"{horizon}h") or horizons.get(str(horizon)) or horizons.get(horizon))
        result[f"{horizon}h"] = {
            "lower": row.get("lower_bound") or row.get("lower_band") or row.get("p10"),
            "median": row.get("point_forecast") or row.get("p50"),
            "upper": row.get("upper_bound") or row.get("upper_band") or row.get("p90"),
        }
    return result


def _combined_settled(canonical_rows: pd.DataFrame, method_rows: pd.DataFrame) -> pd.DataFrame:
    canonical = canonical_rows.copy(deep=False) if isinstance(canonical_rows, pd.DataFrame) else pd.DataFrame()
    methods = method_rows.copy(deep=False) if isinstance(method_rows, pd.DataFrame) else pd.DataFrame()
    if not canonical.empty:
        canonical = canonical.assign(method="canonical")
    if not methods.empty and not canonical.empty:
        condition_columns = [c for c in ("calculation_id", "horizon", "session", "h1_regime", "d1_regime", "h4_regime", "regime_age", "regime_transition_risk", "event_risk_status", "model_agreement", "forecast_origin_price") if c in canonical.columns]
        keys = [c for c in ("calculation_id", "horizon") if c in methods.columns and c in canonical.columns]
        if len(keys) == 2:
            conditions = canonical[condition_columns].drop_duplicates(keys)
            methods = methods.merge(conditions, on=keys, how="left", suffixes=("", "_canonical"))
        rename = {"absolute_error": "absolute_error_pips"}
        methods = methods.rename(columns={k: v for k, v in rename.items() if k in methods.columns and v not in methods.columns})
    return pd.concat([canonical, methods], ignore_index=True, sort=False) if not canonical.empty or not methods.empty else pd.DataFrame()


def _loss_panel(method_rows: pd.DataFrame, horizon: int) -> pd.DataFrame:
    if not isinstance(method_rows, pd.DataFrame) or method_rows.empty:
        return pd.DataFrame()
    h = method_rows.loc[pd.to_numeric(_column(method_rows, "horizon"), errors="coerce") == horizon].copy(deep=False)
    status = _column(h, "record_status").fillna("SETTLED").astype(str).str.upper()
    h = h.loc[status == "SETTLED"]
    if h.empty: return pd.DataFrame()
    h["loss"] = pd.to_numeric(_column(h, "absolute_error", "absolute_error_pips"), errors="coerce")
    h["model"] = _column(h, "method", "model").astype(str)
    h["key"] = _column(h, "calculation_id").astype(str) + "|" + _column(h, "target_time").astype(str)
    panel = h.pivot_table(index="key", columns="model", values="loss", aggfunc="first").sort_index()
    if "canonical" not in panel.columns and len(panel.columns):
        # The production path may be named central/canonical/mmse in old ledgers.
        candidate = next((c for c in panel.columns if str(c).lower() in {"central", "canonical", "production", "mmse", "reconciled"}), panel.columns[0])
        panel = panel.rename(columns={candidate: "canonical"})
    return panel


def _latest_fixed_share(method_rows: pd.DataFrame, previous_state: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(method_rows, pd.DataFrame) or method_rows.empty:
        return {"version": "fixed-share-expert-tracker-20260621-v1", "status": "NO_SETTLED_METHOD_ROWS", "updated": False, "weights": dict(previous_state.get("weights") or {}), "promotion_allowed": False}
    data = method_rows.copy(deep=False)
    status = _column(data, "record_status").fillna("SETTLED").astype(str).str.upper()
    data = data.loc[status == "SETTLED"]
    data["settled_at"] = pd.to_datetime(_column(data, "settlement_timestamp", "target_time"), errors="coerce", utc=True)
    data = data.loc[data["settled_at"].notna()]
    if data.empty:
        return {"version": "fixed-share-expert-tracker-20260621-v1", "status": "NO_VALID_SETTLEMENT", "updated": False, "weights": dict(previous_state.get("weights") or {}), "promotion_allowed": False}
    latest_time = data["settled_at"].max()
    latest = data.loc[data["settled_at"] == latest_time]
    losses = {}
    for _, row in latest.iterrows():
        model = str(row.get("method") or row.get("model") or "")
        loss = finite(row.get("absolute_error"), finite(row.get("absolute_error_pips")))
        if model and loss is not None: losses[model] = loss
    settlement_id = stable_hash(sorted((str(row.get("calculation_id")), int(row.get("horizon") or 0), str(row.get("method"))) for _, row in latest.iterrows()))
    return fixed_share_update(previous_state, losses, settlement_id=settlement_id, settled_at=latest_time)


def _rss_mb() -> float | None:
    try:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return float(rss / 1024.0 if os.name != "posix" or rss > 10_000 else rss / (1024.0 * 1024.0))
    except Exception:
        return None


def build_research_validation_transaction(
    canonical: Mapping[str, Any],
    *,
    completed_h1: pd.DataFrame,
    settled_predictions: pd.DataFrame | None = None,
    settled_method_predictions: pd.DataFrame | None = None,
    preflight_validation: Any = None,
    previous: Mapping[str, Any] | None = None,
    runtime_metrics: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    result_canonical = dict(canonical)
    previous_layer = mapping(mapping(previous).get("research_validation_20260621"))
    source_generation_id = str(result_canonical.get("canonical_calculation_id") or result_canonical.get("run_id") or result_canonical.get("calculation_generation") or "")
    canonical_rows = settled_predictions if isinstance(settled_predictions, pd.DataFrame) else pd.DataFrame()
    method_rows = settled_method_predictions if isinstance(settled_method_predictions, pd.DataFrame) else pd.DataFrame()
    # Bounded recent settled windows keep the explicit Settings calculation
    # lightweight while retaining enough chronological evidence for H+1..H+6.
    if not canonical_rows.empty:
        canonical_rows = canonical_rows.tail(profile_int(6000, 1000)).copy(deep=False)
    if not method_rows.empty:
        method_rows = method_rows.tail(profile_int(12000, 2000)).copy(deep=False)
    combined = _combined_settled(canonical_rows, method_rows)
    covariates = _current_covariates(result_canonical, completed_h1)

    cpa = evaluate_conditional_predictive_ability(combined, benchmark_id="canonical", source_generation_id=source_generation_id)
    spa_results = []
    for horizon in range(1, 7):
        spa = evaluate_superior_predictive_ability(
            _loss_panel(method_rows, horizon), benchmark_id="canonical", horizon=horizon,
            calibration_pass=False, regime_catastrophe_pass=False, resource_budget_pass=False,
            second_window_pass=False, rollback_available=True, source_generation_id=source_generation_id,
        )
        spa_results.append(spa)
    conformal = build_covariate_shift_conformal(
        canonical_rows, current_covariates=covariates, existing_intervals=_existing_intervals(result_canonical),
        source_generation_id=source_generation_id,
    )
    fforma = shadow_weights(covariates)
    try:
        persisted_state = latest_expert_state()
    except Exception:
        persisted_state = {}
    previous_expert = mapping(previous_layer.get("fixed_share")).get("state") or persisted_state
    fixed_share = _latest_fixed_share(method_rows, mapping(previous_expert))

    preflight_ok = bool(getattr(preflight_validation, "publication_allowed", False)) if preflight_validation is not None else None
    metrics = dict(runtime_metrics or {})
    readiness = build_ml_production_readiness_score({
        "feature_schema_pass": preflight_ok,
        "feature_usefulness_pass": cpa.get("status") == "EVALUATED",
        "feature_cost_pass": metrics.get("cpu_regression_pass"),
        "secret_handling_pass": metrics.get("secret_handling_pass"),
        "reproducibility_pass": metrics.get("determinism_pass"),
        "baseline_comparison_pass": any(item.get("status") != "INSUFFICIENT_EVIDENCE" for item in spa_results),
        "important_slice_pass": cpa.get("row_count", 0) > 0,
        "model_staleness_pass": metrics.get("model_staleness_pass"),
        "unit_tests_pass": metrics.get("unit_tests_pass"),
        "integration_tests_pass": metrics.get("integration_tests_pass"),
        "rollback_pass": True,
        "debuggability_pass": True,
        "numerical_stability_pass": True,
        "dependency_change_pass": metrics.get("dependency_change_pass"),
        "data_invariants_pass": preflight_ok,
        "training_production_skew_pass": metrics.get("training_production_skew_pass"),
        "cpu_regression_pass": metrics.get("cpu_regression_pass"),
        "ram_regression_pass": metrics.get("ram_regression_pass"),
        "settled_quality_regression_pass": metrics.get("settled_quality_regression_pass"),
    })
    previous_counters = mapping(previous_layer.get("sliding_monitoring")).get("counters") or {}
    counters = update_operational_counters(previous_counters, {
        "coverage_pass": conformal.get("safe_horizon_count", 0) > 0,
        "coverage_fail": conformal.get("safe_horizon_count", 0) == 0,
        "validation_failure": preflight_ok is False,
        "connector_failure": bool(metrics.get("connector_failure", False)),
        "drift_alert": str(mapping(mapping(result_canonical.get("advanced_reliability_shift")).get("mmd")).get("severity", "")).upper() in {"HIGH", "SEVERE"},
        "regime_change": bool(metrics.get("regime_change", False)),
        "wait_downgrade": bool(metrics.get("wait_downgrade", False)),
        "calculation_failure": False,
    })
    previous_quantiles = mapping(previous_layer.get("bounded_quantile_monitoring")).get("summaries") or {}
    quantiles = update_quantile_summaries(previous_quantiles, {
        "calculation_latency": [metrics.get("calculation_latency_ms")],
        "database_write_latency": [metrics.get("database_write_latency_ms")],
        "memory_usage": [metrics.get("rss_mb") or _rss_mb()],
        "absolute_forecast_error": pd.to_numeric(_column(canonical_rows, "absolute_error_pips"), errors="coerce").dropna().tail(24).tolist() if not canonical_rows.empty else [],
        "normalized_residual": pd.to_numeric(_column(canonical_rows, "normalized_residual"), errors="coerce").dropna().tail(24).tolist() if not canonical_rows.empty else [],
        "interval_width": (pd.to_numeric(_column(canonical_rows, "upper_band"), errors="coerce") - pd.to_numeric(_column(canonical_rows, "lower_band"), errors="coerce")).dropna().tail(24).tolist() if not canonical_rows.empty else [],
        "mfe": pd.to_numeric(_column(canonical_rows, "maximum_favorable_excursion"), errors="coerce").dropna().tail(24).tolist() if not canonical_rows.empty else [],
        "mae": pd.to_numeric(_column(canonical_rows, "maximum_adverse_excursion"), errors="coerce").dropna().tail(24).tolist() if not canonical_rows.empty else [],
        "drift_score": [covariates.get("mmd_shift_score")],
        "anomaly_score": [metrics.get("anomaly_score")],
    })

    layer = {
        "version": VERSION, "evaluated_at": utc_now_iso(), "source_generation_id": source_generation_id,
        "mode": "SHADOW_VALIDATION", "conditional_predictive_ability": cpa,
        "superior_predictive_ability": spa_results, "covariate_shift_conformal": conformal,
        "fforma": fforma, "fixed_share": fixed_share, "ml_production_readiness": readiness,
        "sliding_monitoring": counters, "bounded_quantile_monitoring": quantiles,
        "direction_reversal_allowed": False, "protected_calculation_changed": False,
        "promotion_allowed": False,
    }
    layer["layer_id"] = "RVL-" + stable_hash({k: v for k, v in layer.items() if k != "evaluated_at"})[:24]
    result_canonical["research_validation_20260621"] = layer
    result_canonical.setdefault("metadata", {})["research_validation_summary"] = readiness.get("compact_summary")
    result_canonical.setdefault("metadata", {})["research_validation_mode"] = "SHADOW_VALIDATION"
    reliability = result_canonical.get("reliability")
    if isinstance(reliability, dict):
        reliability["research_validation_summary"] = readiness.get("compact_summary")
        reliability["research_validation_promotion_allowed"] = False
    advanced = result_canonical.get("advanced_reliability_shift")
    if isinstance(advanced, dict):
        advanced["research_validation_summary"] = readiness.get("compact_summary")
        advanced["research_validation_mode"] = "SHADOW_VALIDATION"

    bundle: dict[str, list[dict[str, Any]]] = {
        "conditional_predictive_ability_history": list(cpa.get("rows") or []),
        "research_spa_results": [item.get("row") for item in spa_results if isinstance(item.get("row"), Mapping) and item.get("row")],
        "covariate_shift_conformal_history": [dict(row, evaluated_at=conformal.get("evaluated_at"), source_generation_id=source_generation_id, calculation_version=conformal.get("version")) for row in mapping(conformal.get("horizons")).values()],
        "fforma_shadow_history": [{"evaluation_id": fforma.get("evaluation_id") or ("FFORMA-" + stable_hash(fforma)[:24]), "evaluated_at": layer["evaluated_at"], "artifact_id": fforma.get("artifact_id"), "status": fforma.get("status"), "source_generation_id": source_generation_id, "promotion_allowed": False, "calculation_version": fforma.get("version"), **fforma}],
        "expert_weight_history": list(fixed_share.get("history_rows") or []),
        "expert_tracker_state": [dict(fixed_share.get("state") or {}, calculation_version=fixed_share.get("version"))] if fixed_share.get("state") else [],
        "expert_tracker_comparison": [fixed_share.get("comparison")] if fixed_share.get("comparison") else [],
        "ml_production_readiness_history": [readiness],
        "sliding_monitoring_state": [{"state_id": counters.get("state_id"), "updated_at": counters.get("updated_at"), "calculation_version": counters.get("version"), **counters}],
        "bounded_quantile_monitoring_state": [{"state_id": quantiles.get("state_id"), "updated_at": quantiles.get("updated_at"), "relative_error_tolerance": quantiles.get("relative_error_tolerance"), "calculation_version": quantiles.get("version"), **quantiles}],
    }
    if preflight_validation is not None and hasattr(preflight_validation, "atomic_rows"):
        for table, rows in preflight_validation.atomic_rows(source_generation_id=source_generation_id).items():
            bundle.setdefault(table, []).extend(rows)
    summary = {
        "version": VERSION, "layer_id": layer["layer_id"], "mode": layer["mode"],
        "cpa_rows": len(bundle["conditional_predictive_ability_history"]),
        "spa_rows": len(bundle["research_spa_results"]),
        "data_quality_pass": preflight_ok, "readiness_score": readiness.get("overall_readiness_score"),
        "protected_calculation_changed": False, "promotion_allowed": False,
    }
    return result_canonical, {BUNDLE_KEY: bundle}, summary


__all__ = ["VERSION", "build_research_validation_transaction"]
