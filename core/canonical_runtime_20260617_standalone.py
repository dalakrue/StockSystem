"""Canonical runtime state, explicit adapters, and atomic publication.

This module contains no calculation formulas.  It enforces one successful
Settings calculation as the authoritative run and exposes one-way compatibility
adapters for legacy renderers.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Tuple

from core.generation_identity_20260707 import numeric_generation, normalize_generation_fields
import time

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None  # type: ignore

CANONICAL_KEY = "canonical_decision_result_20260617"
LAST_VALID_KEY = "last_valid_canonical_decision_result_20260617"
STAGING_KEY = "canonical_decision_staging_20260617"
RUNTIME_CONTEXT_KEY = "runtime_context_20260617"
SHARED_KEY = "adx_shared_calc_result_20260615"
LEGACY_SHARED_KEY = "shared_calc_result"
GENERATION_KEY = "successful_calculation_generation_20260617"

REQUIRED_CANONICAL_FIELDS = (
    "run_id", "calculation_generation", "data_signature", "symbol", "timeframe",
    "source", "latest_completed_candle_time", "created_at", "expires_at", "schema_version", "calculation_version",
    "calculation_status",
)

ADAPTER_SPECS: Dict[str, Dict[str, Any]] = {
    "market": {"accepted_legacy_source_keys": ("dv_pp_df", "lunch_5layer_powerbi_df", "last_df", "ohlc_df", "df")},
    "metric": {"accepted_legacy_source_keys": ("lunch_metric_result_cache", "last_result", "current_result")},
    "powerbi": {"accepted_legacy_source_keys": ("dv_pp_base_result", "lunch_5layer_powerbi_result", "lunch_prediction_export")},
    "regime": {"accepted_legacy_source_keys": ("dv_pp_regime_summary", "regime_context_20260614", "canonical_regime_snapshot_20260617")},
    "alpha_delta": {"accepted_legacy_source_keys": ("adx_regime_alpha_delta_20260615", "regime_alpha_delta")},
    "priority": {"accepted_legacy_source_keys": ("canonical_priority_table_20260617", "adx_hourly_priority_calibrated_20260615")},
    "knn_greedy": {"accepted_legacy_source_keys": ("canonical_priority_table_20260617", "three_center_priority_sorted_20260614")},
    "reliability": {"accepted_legacy_source_keys": ("reliability_control_center_20260614", "adx_reliability_calibrated_20260615")},
    "nlp": {"accepted_legacy_source_keys": ("nlp_market_intelligence_result", "regime_nlp_today_table", "nlp_ranked_news_df")},
    "data_mining": {"accepted_legacy_source_keys": ("research_pack_20260612", "final_synced_research_merge_pack_20260612")},
    "prediction_history": {"accepted_legacy_source_keys": ("dv_pp_bt_hist", "prediction_history_df", "prediction_vs_actual_history_df")},
    "ai_grounding": {"accepted_legacy_source_keys": ("adx_ai_grounding_20260615",)},
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_df(value: Any) -> bool:
    return pd is not None and isinstance(value, pd.DataFrame)


def proposed_generation(state: Mapping[str, Any]) -> int:
    """Return the next generation without mutating state."""
    current = numeric_generation(state.get(GENERATION_KEY, 0), default=0)
    existing = state.get(CANONICAL_KEY) or state.get(LAST_VALID_KEY) or {}
    if isinstance(existing, dict):
        try:
            current = max(current, numeric_generation(
                existing.get("calculation_generation") or existing.get("generation") or existing.get("generation_id"),
                default=0,
            ))
        except Exception:
            pass
    return current + 1


def validate_canonical_result(payload: Any) -> Tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["canonical result is not a dictionary"]
    for key in REQUIRED_CANONICAL_FIELDS:
        if key not in payload or payload.get(key) in (None, ""):
            errors.append(f"missing {key}")
    try:
        if numeric_generation(
            payload.get("calculation_generation") or payload.get("generation") or payload.get("generation_id"),
            default=0,
        ) < 1:
            errors.append("calculation_generation must be positive")
    except Exception:
        errors.append("calculation_generation is invalid")
    status = str(payload.get("calculation_status", "")).upper()
    if not status.startswith("COMPLETED"):
        errors.append(f"calculation_status is not completed: {status or 'missing'}")
    market = payload.get("market") or {}
    if not isinstance(market, dict) or not market.get("latest_completed_candle_time"):
        errors.append("missing latest_completed_candle_time")
    if not isinstance(payload.get("final_decision"), dict):
        errors.append("missing final_decision object")
    shared_schema = payload.get("shared_result_schema_version")
    if shared_schema:
        for key in (
            "canonical_calculation_id", "multiscale_regime", "probabilistic_projection",
            "dynamic_feature_weights", "forecast_decomposition", "validation_metrics",
            "meta_labels", "layer_execution_metadata",
        ):
            if key not in payload:
                errors.append(f"missing shared-result field {key}")
        try:
            from core.multiscale_probabilistic_upgrade_20260618 import invariant_report
            invariants = invariant_report(payload)
            for name, valid in invariants.items():
                if not valid:
                    errors.append(f"shared-result invariant failed: {name}")
        except Exception as exc:
            errors.append(f"shared-result validation error: {exc}")
    research = payload.get("research_calibration")
    if isinstance(research, Mapping) and research:
        try:
            from core.research_calibration_20260618 import validate_research_invariants
            research_invariants = validate_research_invariants(research)
            for name, valid in research_invariants.items():
                if not valid:
                    errors.append(f"research-calibration invariant failed: {name}")
            if str(research.get("last_completed_h1_timestamp")) != str(payload.get("latest_completed_candle_time")):
                errors.append("research-calibration latest completed H1 time mismatch")
            if not bool(research.get("causal_completed_candle_only")):
                errors.append("research-calibration is not marked completed-candle-only")
            if int(research.get("future_rows_used", 1) or 0) != 0:
                errors.append("research-calibration reports future rows")
        except Exception as exc:
            errors.append(f"research-calibration validation error: {exc}")
    advanced = payload.get("advanced_reliability_shift")
    if isinstance(advanced, Mapping) and advanced:
        try:
            advanced_identity = advanced.get("identity") if isinstance(advanced.get("identity"), Mapping) else {}
            expected_id = str(payload.get("canonical_calculation_id") or payload.get("run_id") or "")
            if str(advanced_identity.get("calculation_id") or "") != expected_id:
                errors.append("advanced-reliability calculation id mismatch")
            if numeric_generation(advanced_identity.get("generation") or advanced_identity.get("generation_id"), default=0) != numeric_generation(
                payload.get("calculation_generation") or payload.get("generation") or payload.get("generation_id"), default=0
            ):
                errors.append("advanced-reliability calculation generation mismatch")
            if str(advanced_identity.get("latest_completed_h1_time")) != str(payload.get("latest_completed_candle_time")):
                errors.append("advanced-reliability latest completed H1 time mismatch")
            contract = advanced.get("input_contract") if isinstance(advanced.get("input_contract"), Mapping) else {}
            if not bool(contract.get("completed_utc_h1_only")):
                errors.append("advanced-reliability is not marked completed-UTC-H1-only")
            policy = advanced.get("decision_policy") if isinstance(advanced.get("decision_policy"), Mapping) else {}
            if bool(policy.get("direction_reversal_allowed", True)):
                errors.append("advanced-reliability direction reversal policy is unsafe")
        except Exception as exc:
            errors.append(f"advanced-reliability validation error: {exc}")
    authority = str((payload.get("metadata") or {}).get("primary_calculation_authority") or "")
    if authority == "Full Metric Detail + History":
        if str(payload.get("symbol") or "").upper() != "EURUSD":
            errors.append("operational symbol must be EURUSD")
        if str(payload.get("timeframe") or "").upper() != "H1":
            errors.append("operational timeframe must be H1")
        required_full_metric = (
            "full_metric_snapshot", "full_metric_direction", "tradeability_decision",
            "full_metric_current_row", "full_metric_history", "reverse_10_current",
            "reverse_10_history", "canonical_priority_table", "top_two_daily_candidates",
        )
        for key in required_full_metric:
            if key not in payload:
                errors.append(f"missing {key}")
        snapshot = payload.get("full_metric_snapshot") or {}
        expected_time = payload.get("latest_completed_candle_time")
        if isinstance(snapshot, Mapping) and str(snapshot.get("latest_completed_h1_time")) != str(expected_time):
            errors.append("full metric latest completed H1 time mismatch")
    return not errors, errors


def canonical_identity(payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    p = payload if isinstance(payload, Mapping) else {}
    market = p.get("market") if isinstance(p.get("market"), Mapping) else {}
    return {
        "run_id": p.get("run_id"),
        "calculation_generation": p.get("calculation_generation"),
        "data_signature": p.get("data_signature"),
        "symbol": p.get("symbol"),
        "timeframe": p.get("timeframe"),
        "source": p.get("source"),
        "latest_completed_candle_time": p.get("latest_completed_candle_time") or market.get("latest_completed_candle_time"),
        "created_at": p.get("created_at"),
        "expires_at": p.get("expires_at"),
        "schema_version": p.get("schema_version"),
        "calculation_version": p.get("calculation_version"),
        "calculation_status": p.get("calculation_status"),
        "checksum": p.get("checksum"),
        "snapshot_schema_version": p.get("snapshot_schema_version"),
    }


def component_matches_canonical(component: Any, canonical: Mapping[str, Any]) -> Tuple[bool, list[str]]:
    """Validate identity fields for a synchronized component."""
    if not isinstance(component, Mapping):
        return False, ["component is not a mapping"]
    expected = canonical_identity(canonical)
    reasons: list[str] = []
    aliases = {"generation": "calculation_generation", "candle time": "latest_completed_candle_time"}
    for label, key in aliases.items():
        got = component.get(key, component.get(label))
        if got not in (None, "") and str(got) != str(expected.get(key)):
            reasons.append(f"{key} mismatch")
    for key in ("run_id", "symbol", "timeframe", "source", "data_signature"):
        got = component.get(key)
        if got not in (None, "") and str(got) != str(expected.get(key)):
            reasons.append(f"{key} mismatch")
    return not reasons, reasons


def validate_operational_component(component: Any, canonical: Mapping[str, Any]) -> Tuple[bool, list[str]]:
    """Require every operational identity field, not merely compare present ones."""
    if not isinstance(component, Mapping):
        return False, ["component is not a mapping"]
    expected = canonical_identity(canonical)
    reasons: list[str] = []
    for key in (
        "run_id", "calculation_generation", "data_signature", "symbol", "timeframe",
        "latest_completed_candle_time",
    ):
        got = component.get(key)
        if got in (None, ""):
            reasons.append(f"missing {key}")
        elif str(got) != str(expected.get(key)):
            reasons.append(f"{key} mismatch")
    return not reasons, reasons


def component_freshness_guard(component: Any, canonical: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate one supporting component and return a safe operational action.

    Stale or incomplete supporting evidence is never mixed silently with the
    current Full Metric generation.  The canonical directional view is retained
    for explanation, but entry permission becomes WAIT until identities match.
    """
    canonical_ok, canonical_errors = validate_canonical_result(dict(canonical or {}))
    if not canonical_ok:
        return {
            "ok": False, "status": "CANONICAL NOT READY", "reasons": canonical_errors,
            "safe_action": "WAIT", "directional_view": "WAIT",
        }
    ok, reasons = validate_operational_component(component, canonical)
    final = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
    direction = str(final.get("directional_market_view") or canonical.get("full_metric_direction") or "WAIT").upper()
    tradeability = str(final.get("tradeability_decision") or canonical.get("tradeability_decision") or "WAIT").upper()
    return {
        "ok": bool(ok),
        "status": "CURRENT" if ok else "STALE / MISMATCHED",
        "reasons": list(reasons),
        "safe_action": tradeability if ok and tradeability in {"BUY", "SELL"} else "WAIT",
        "directional_view": direction if direction in {"BUY", "SELL"} else "WAIT",
        **canonical_identity(canonical),
    }


def _source_meta(canonical: Mapping[str, Any], component: str) -> Dict[str, Any]:
    meta = canonical_identity(canonical)
    meta.update({
        "adapter": component,
        "accepted_legacy_source_keys": list(ADAPTER_SPECS.get(component, {}).get("accepted_legacy_source_keys", ())),
        "source_timestamp": canonical.get("created_at"),
        "validation_status": "VALID",
    })
    return meta


def _canonical_priority_frame(priority_table: Any, canonical: Mapping[str, Any]):
    if not _is_df(priority_table):
        return pd.DataFrame() if pd is not None else priority_table
    table = priority_table
    identity = canonical_identity(canonical)
    stamp = {
        "run_id": identity["run_id"],
        "generation": identity["calculation_generation"],
        "calculation_generation": identity["calculation_generation"],
        "data_signature": identity["data_signature"],
        "symbol": identity["symbol"],
        "timeframe": identity["timeframe"],
        "source": identity["source"],
        "latest_completed_candle_time": identity["latest_completed_candle_time"],
        "data-quality status": (canonical.get("data_quality") or {}).get("status", "UNKNOWN"),
    }
    # One controlled copy prevents mutating the source table while avoiding many
    # renderer-level copies later.
    table = table.copy(deep=False)
    for key, value in stamp.items():
        table[key] = value

    def first_existing(*names: str):
        return next((table[name] for name in names if name in table.columns), None)

    aliases = {
        "candle time": first_existing("Time", "time", "latest_completed_candle_time"),
        "hour": first_existing("Hour", "hour"),
        "regime": first_existing("Major Regime", "Regime", "regime"),
        "regime reliability": first_existing("Reliability %", "Reliability", "regime reliability"),
        "prediction direction": first_existing("Direction", "Prediction Direction", "prediction direction", "Decision"),
        "KNN score": first_existing("KNN Score /10", "KNN Score", "Priority Score"),
        "Greedy score": first_existing("Greedy Score /10", "Greedy Score", "Priority Score"),
        "combined score": first_existing("Priority Score", "Combined Score", "combined score"),
        "priority rank": first_existing("Priority Rank", "priority rank", "Ascending Priority", "KNN Priority"),
        "less-risky bias": first_existing("Less Risky Bias", "less-risky bias", "Decision"),
        "qualification status": first_existing("Qualification Status", "qualification status"),
        "blocking reason": first_existing("Blocking Reason", "blocking reason"),
    }
    for name, values in aliases.items():
        if values is not None:
            table[name] = values
    if "priority label" not in table.columns:
        rank_source = table["priority rank"] if "priority rank" in table.columns else pd.Series(14.0, index=table.index, dtype=float)
        ranks = pd.to_numeric(rank_source, errors="coerce").fillna(14)
        table["priority label"] = ranks.map(lambda rank: "A+" if rank <= 3 else "A" if rank <= 6 else "B" if rank <= 9 else "C" if rank <= 12 else "AVOID")
    if "conflict status" not in table.columns:
        canonical_direction = str((canonical.get("final_decision") or {}).get("directional_market_view") or "WAIT").upper()
        row_direction = table.get("prediction direction", pd.Series("WAIT", index=table.index)).astype(str).str.upper()
        table["conflict status"] = row_direction.map(lambda value: "ALIGNED" if value in {canonical_direction, "WAIT"} or canonical_direction == "WAIT" else "CONFLICT")
    return table


def build_shared_adapter(
    state: Mapping[str, Any], canonical: Mapping[str, Any], legacy_shared: Optional[Mapping[str, Any]] = None,
    priority_table: Any = None,
) -> Dict[str, Any]:
    """Create one-way legacy views derived from the authoritative canonical run."""
    legacy = dict(legacy_shared or {})
    final = dict(canonical.get("final_decision") or {})
    market = dict(canonical.get("market") or {})
    regime = dict(canonical.get("regime") or {})
    reliability = dict(canonical.get("reliability") or {})
    nlp = dict(canonical.get("nlp") or {})
    priority = dict(canonical.get("priority") or {})
    forecasts = dict(canonical.get("forecasts") or {})
    horizons = dict(forecasts.get("horizons") or {})
    multiscale = dict(canonical.get("multiscale_regime") or {})
    probabilistic = dict(canonical.get("probabilistic_projection") or {})
    validation_metrics = dict(canonical.get("validation_metrics") or {})
    meta_labels = dict(canonical.get("meta_labels") or {})
    layer_metadata = list(canonical.get("layer_execution_metadata") or [])
    feature_weights = list(canonical.get("dynamic_feature_weights") or [])
    decomposition = dict(canonical.get("forecast_decomposition") or {})
    temporal_patches = dict(canonical.get("temporal_patches") or {})
    research = dict(canonical.get("research_calibration") or {})
    research_risk = dict(canonical.get("research_risk_stack") or {})
    research_risk_summary = dict(research_risk.get("current_summary") or {})
    advanced_reliability = dict(canonical.get("advanced_reliability_shift") or {})
    ten_paper_research = dict(canonical.get("ten_paper_research_20260621") or {})
    quant_research_v3 = dict(canonical.get("quant_research_v3") or {})
    quant_v3_summary = dict(quant_research_v3.get("summary") or {})
    quant_v3_identity = dict(quant_research_v3.get("identity") or {})
    quant_research_v4 = dict(canonical.get("quant_research_v4") or {})
    quant_v4_summary = dict(quant_research_v4.get("summary") or {})
    quant_v4_identity = dict(quant_research_v4.get("identity") or {})
    quant_research_v7 = dict(canonical.get("quant_research_v7") or {})
    quant_v7_summary = dict(quant_research_v7.get("summary") or {})
    quant_v7_identity = dict(quant_research_v7.get("identity") or {})
    ten_paper_reject = dict(ten_paper_research.get("paper_3") or {})
    ten_paper_explanations = dict(ten_paper_research.get("paper_5") or {})
    advanced_identity = dict(advanced_reliability.get("identity") or {})
    advanced_crc = dict(advanced_reliability.get("conformal_risk_control") or {})
    advanced_mmd = dict(advanced_reliability.get("mmd") or {})
    advanced_rrcf = dict(advanced_reliability.get("rrcf") or {})
    advanced_multicalibration = dict(advanced_reliability.get("multicalibration") or {})
    similar_day = dict(canonical.get("similar_day_intelligence") or {})
    similar_day_summary = dict(similar_day.get("summary") or {})
    regime_transition_trust = dict(canonical.get("regime_transition_trust_center") or {})
    research_uncertainty = dict(research.get("uncertainty") or {})
    research_change = dict(research.get("bayesian_changepoint") or {})
    research_windows = dict(research.get("adaptive_windows") or {})
    research_conformal = dict(research.get("conformal_prediction") or {})
    research_coverage = dict(research.get("adaptive_coverage") or {})
    research_dma = dict(research.get("dynamic_model_averaging") or {})
    research_cset = dict(research.get("conditional_method_confidence_set") or {})
    research_baselines = dict(research.get("baseline_forecasts") or {})
    research_skill = dict(research.get("baseline_skill") or {})
    research_reliability = dict(research.get("research_reliability") or {})
    selected = int(final.get("selected_horizon") or forecasts.get("selected_horizon") or 3)
    selected_forecast = dict(horizons.get(f"{selected}h") or {})
    table = _canonical_priority_frame(priority_table, canonical)
    if not _is_df(table):
        existing = state.get("canonical_priority_table_20260617")
        table = _canonical_priority_frame(existing, canonical) if _is_df(existing) else (pd.DataFrame() if pd is not None else None)

    identity = canonical_identity(canonical)
    full_metric = dict(canonical.get("full_metric_snapshot") or {})
    top_two = list(canonical.get("top_two_daily_candidates") or full_metric.get("top_two_daily_candidates") or [])
    current = {
        "symbol": canonical.get("symbol"), "timeframe": canonical.get("timeframe"), "source": canonical.get("source"),
        "latest_completed_h1_time": canonical.get("latest_completed_candle_time"),
        "latest_completed_candle_time": canonical.get("latest_completed_candle_time"),
        "last_close": canonical.get("last_close", market.get("current_price")),
        "regime": canonical.get("current_major_regime", regime.get("major_regime", "UNKNOWN")),
        "regime_direction": canonical.get("full_metric_direction", final.get("directional_market_view", "WAIT")),
        "full_metric_direction": canonical.get("full_metric_direction", final.get("directional_market_view", "WAIT")),
        "prediction_direction": selected_forecast.get("direction", "WAIT"),
        "decision": final.get("final_decision", "DATA NOT READY"),
        "tradeability_decision": final.get("tradeability_decision", "WAIT"),
        "less_risky_decision": final.get("less_risky_decision", "WAIT"),
        "master_score": canonical.get("master_score"), "entry_score": canonical.get("entry_score"),
        "buy_score": canonical.get("buy_score"), "sell_score": canonical.get("sell_score"),
        "hold_safety": canonical.get("hold_safety"), "tp_quality": canonical.get("tp_quality"),
        "exit_risk": canonical.get("exit_risk"), "pullback_readiness": canonical.get("pullback_readiness"),
        "trend_capacity_remaining": canonical.get("trend_capacity_remaining"),
        "m1_confirmation": canonical.get("m1_confirmation"),
        "forecast_close": selected_forecast.get("point_forecast"),
        "forecast_confidence": final.get("calibrated_confidence"),
        "reliability": reliability.get("score"), "uncertainty": final.get("uncertainty_pct"),
        "error_estimate": final.get("error_estimate_pct"),
        "blocking_reasons": list(final.get("blocking_reasons") or []),
        "selected_horizon": selected,
        "decision_policy": final.get("main_reason", ""),
        "top_two_daily_candidates": top_two,
        "run_id": canonical.get("run_id"), "calculation_generation": canonical.get("calculation_generation"),
        "data_signature": canonical.get("data_signature"),
        "canonical_calculation_id": canonical.get("canonical_calculation_id"),
        "volatility_regime": multiscale.get("current_volatility_regime"),
        "combined_regime": multiscale.get("combined_existing_and_volatility_regime"),
        "regime_entropy": multiscale.get("mean_normalized_entropy"),
        "regime_transition_risk_pct": multiscale.get("multi_scale_transition_risk_pct"),
        "multi_scale_agreement_score": multiscale.get("multi_scale_agreement_score_0_10"),
        "meta_labels": meta_labels,
        "research_calculation_id": research.get("canonical_calculation_id"),
        "research_reliability": research_reliability.get("calibrated_score_0_100"),
        "aleatoric_uncertainty": research_uncertainty.get("aleatoric_uncertainty_0_100"),
        "epistemic_uncertainty": research_uncertainty.get("epistemic_uncertainty_0_100"),
        "combined_uncertainty": research_uncertainty.get("combined_uncertainty_0_100"),
        "transition_risk": research_change.get("transition_risk_0_100"),
        "transition_window": research_change.get("estimated_transition_window"),
        "research_validation_status": research.get("validation_status"),
        "required_confidence_threshold": research_risk_summary.get("required_confidence_threshold"),
        "selective_prediction_pass": research_risk_summary.get("selective_prediction_pass"),
        "tp_first_probability": research_risk_summary.get("tp_first_probability"),
        "sl_first_probability": research_risk_summary.get("sl_first_probability"),
        "robust_expected_value": research_risk_summary.get("robust_expected_value"),
        "extreme_risk_block": research_risk_summary.get("extreme_risk_block"),
        "display_risk_multiplier": research_risk_summary.get("display_risk_multiplier"),
        "similar_day_index": similar_day_summary.get("Best Similarity Index"),
        "similar_day_result": similar_day_summary.get("Weighted historical result"),
        "similar_day_reliability": similar_day_summary.get("Similar-day reliability"),
        "similar_day_conflict": similar_day.get("conflict_warning"),
        "advanced_research_status": advanced_reliability.get("research_confidence_status"),
        "advanced_trust_cap_pct": advanced_reliability.get("trust_cap_pct"),
        "advanced_crc_status": advanced_crc.get("status"),
        "advanced_crc_risk_upper_bound": advanced_crc.get("risk_upper_bound"),
        "advanced_crc_threshold": advanced_crc.get("threshold"),
        "advanced_multicalibrated_probability": advanced_multicalibration.get("calibrated_probability"),
        "advanced_mmd_severity": advanced_mmd.get("severity"),
        "advanced_market_anomaly_score": advanced_rrcf.get("market_anomaly_score"),
        "advanced_system_anomaly_score": advanced_rrcf.get("system_anomaly_score"),
        "advanced_research_calculation_id": advanced_identity.get("calculation_id"),
        "ten_paper_research_status": ten_paper_research.get("status"),
        "ten_paper_research_mode": ten_paper_research.get("mode"),
        "ten_paper_shadow_decision": ten_paper_reject.get("shadow_reject_option_decision"),
        "ten_paper_transaction_id": ten_paper_research.get("transaction_id"),
        "quant_v3_status": quant_v3_summary.get("overall_quant_v3_status"),
        "quant_v3_mode": quant_research_v3.get("mode"),
        "quant_v3_source_generation_id": quant_v3_identity.get("source_generation_id"),
        "quant_v3_risk_multiplier": quant_v3_summary.get("cvar_risk_multiplier"),
        "quant_v3_density_test": quant_v3_summary.get("density_test"),
        "quant_v4_status": quant_v4_summary.get("overall_status"),
        "quant_v4_mode": "SHADOW",
        "quant_v4_source_generation_id": quant_v4_identity.get("source_generation_id"),
        "quant_v4_direction_skill": quant_v4_summary.get("direction_skill"),
        "quant_v4_interval_coverage": quant_v4_summary.get("interval_conditional_coverage"),
        "quant_v4_transition_risk_6h": quant_v4_summary.get("transition_risk_6h"),
        "quant_v4_tail_risk_backtest": quant_v4_summary.get("tail_risk_backtest"),
        "quant_v4_sequential_monitor": quant_v4_summary.get("sequential_monitor"),
    }
    old_powerbi = legacy.get("powerbi") if isinstance(legacy.get("powerbi"), dict) else {}
    old_nlp = legacy.get("nlp") if isinstance(legacy.get("nlp"), dict) else {}
    old_data_mining = legacy.get("data_mining") if isinstance(legacy.get("data_mining"), dict) else {}
    old_history = legacy.get("history") if isinstance(legacy.get("history"), dict) else {}
    old_market = legacy.get("market") if isinstance(legacy.get("market"), dict) else {}
    old_decision = legacy.get("decision") if isinstance(legacy.get("decision"), dict) else {}
    old_regime = legacy.get("regime") if isinstance(legacy.get("regime"), dict) else {}
    false_reversal_risk = old_decision.get("false_reversal_risk") or legacy.get("false_reversal_risk") or {}
    window_analytics = old_regime.get("window_analytics") or legacy.get("regime_window_analytics") or {}

    adapter = {
        "version": "20260618_full_metric_canonical_adapter_v2",
        "built_at": canonical.get("created_at"),
        "signature": canonical.get("data_signature"),
        # Keep one immutable reference; a shallow top-level duplicate made every
        # adapter generation retain another large canonical container.
        "canonical": canonical,
        **canonical_identity(canonical),
        "current": current,
        "market": {**old_market, **current, "latest_completed_candle_time": market.get("latest_completed_candle_time"), "row_count": market.get("row_count"), "adapter_meta": _source_meta(canonical, "market")},
        "decision": {**identity, "central_decision": final.get("final_decision"), "directional_market_view": final.get("directional_market_view"), "tradeability_decision": final.get("tradeability_decision"), "less_risky_decision": final.get("less_risky_decision"), "blocking_reasons": list(final.get("blocking_reasons") or []), "selected_horizon": selected, "false_reversal_risk": false_reversal_risk, "adapter_meta": _source_meta(canonical, "metric")},
        "regime": {**identity, "current": regime.get("major_regime"), "direction": final.get("directional_market_view"), "alpha_delta": {"alpha": regime.get("alpha"), "delta": regime.get("delta"), "delta_acceleration": regime.get("delta_acceleration")}, "standards": {"lower": regime.get("lower_standard_regime"), "middle": regime.get("middle_standard_regime"), "higher": regime.get("higher_standard_regime")}, "window_analytics": window_analytics, "volatility_regime": multiscale.get("current_volatility_regime"), "combined_regime": multiscale.get("combined_existing_and_volatility_regime"), "scales": multiscale.get("scales", {}), "joint_27_state_probabilities": multiscale.get("joint_27_state_probabilities", []), "entropy": multiscale.get("mean_normalized_entropy"), "transition_risk_pct": multiscale.get("multi_scale_transition_risk_pct"), "agreement_score_0_10": multiscale.get("multi_scale_agreement_score_0_10"), "bayesian_changepoint": research_change, "adaptive_windows": research_windows, "research_transition_risk_0_100": research_change.get("transition_risk_0_100"), "estimated_transition_window": research_change.get("estimated_transition_window"), "adapter_meta": _source_meta(canonical, "regime")},
        "priority": {**identity, "table": table, "best": table.iloc[0].to_dict() if _is_df(table) and not table.empty else priority, "top_two": top_two, "summary": priority, "research_refinements": canonical.get("research_score_refinements", {}), "knn_neighbor_quality": (canonical.get("research_score_refinements") or {}).get("knn_neighbor_quality", {}), "greedy_calibration_inputs": (canonical.get("research_score_refinements") or {}).get("greedy_inputs", {}), "adapter_meta": _source_meta(canonical, "priority")},
        "hourly_priority_table": table,
        "reliability": {**reliability, **identity, "selected_horizon": selected, "selected_horizon_validation": (reliability.get("validation_by_horizon") or {}).get(f"{selected}h", {}), "selected_horizon_calibration": (reliability.get("calibration_by_horizon") or {}).get(f"{selected}h", {}), "validation_metrics": validation_metrics, "regime_entropy": multiscale.get("mean_normalized_entropy"), "transition_risk_pct": multiscale.get("multi_scale_transition_risk_pct"), "agreement_score_0_10": multiscale.get("multi_scale_agreement_score_0_10"), "research_calibrated_score": research_reliability.get("calibrated_score_0_100"), "research_components": research_reliability.get("components", {}), "adaptive_coverage": research_coverage, "uncertainty_separation": research_uncertainty, "pbo": research.get("pbo", {}), "dsr": research.get("dsr", {}), "baseline_skill": research_skill, "research_risk_stack": research_risk, "advanced_reliability_shift": advanced_reliability, "adapter_meta": _source_meta(canonical, "reliability")},
        "reliability_calibration": reliability,
        "powerbi": {**old_powerbi, **identity, "forecast_close": selected_forecast.get("point_forecast"), "lower_bound": selected_forecast.get("lower_bound"), "upper_bound": selected_forecast.get("upper_bound"), "direction": selected_forecast.get("direction"), "canonical_direction": final.get("directional_market_view"), "tradeability_decision": final.get("tradeability_decision"), "selected_horizon": selected, "probabilistic_projection": probabilistic, "forecast_decomposition": decomposition, "dynamic_feature_weights": feature_weights, "volatility_regime": multiscale.get("current_volatility_regime"), "run_id": canonical.get("run_id"), "calculation_generation": canonical.get("calculation_generation"), "data_signature": canonical.get("data_signature"), "latest_completed_candle_time": canonical.get("latest_completed_candle_time"), "conformal_prediction": research_conformal, "adaptive_coverage": research_coverage, "dynamic_model_averaging": research_dma, "conditional_model_set": research_cset, "challenger_baselines": research_baselines, "baseline_skill": research_skill, "research_calculation_id": research.get("canonical_calculation_id"), "research_risk_stack": research_risk, "advanced_reliability_shift": advanced_reliability, "adapter_meta": _source_meta(canonical, "powerbi")},
        "nlp": {**old_nlp, **identity, "summary": {**(old_nlp.get("summary") or {}), "nlp_direction": nlp.get("direction", "WAIT"), "reliability": nlp.get("reliability", 0), "conflict_level": nlp.get("conflict_level", "NONE"), "latest_rank_1_news": nlp.get("latest_headline", "No relevant news"), "news_time": nlp.get("latest_time"), "less_risky_decision": final.get("less_risky_decision", "WAIT")}, "adapter_meta": _source_meta(canonical, "nlp")},
        "data_mining": {**old_data_mining, **identity, "temporal_patches": temporal_patches, "dynamic_feature_weights": feature_weights, "validation_metrics": validation_metrics, "layer_execution_metadata": layer_metadata, "ten_paper_research_calibration": research, "advanced_reliability_shift": advanced_reliability, "ten_paper_research_20260621": ten_paper_research, "adapter_meta": _source_meta(canonical, "data_mining")},
        "history": {**old_history, **identity, "priority": table, "adapter_meta": _source_meta(canonical, "prediction_history")},
        "prediction_feedback": legacy.get("prediction_feedback", {}),
        "regime_alpha_delta": {"alpha": regime.get("alpha"), "delta": regime.get("delta"), "delta_acceleration": regime.get("delta_acceleration")},
        "false_reversal_risk": false_reversal_risk,
        "regime_window_analytics": window_analytics,
        "full_metric_snapshot": full_metric,
        "full_metric_history": canonical.get("full_metric_history", []),
        "reverse_10_current": canonical.get("reverse_10_current", []),
        "reverse_10_history": canonical.get("reverse_10_history", {}),
        "top_two_daily_candidates": top_two,
        "shared_result_schema_version": canonical.get("shared_result_schema_version"),
        "canonical_calculation_id": canonical.get("canonical_calculation_id"),
        "multiscale_regime": multiscale,
        "probabilistic_projection": probabilistic,
        "forecast_decomposition": decomposition,
        "dynamic_feature_weights": feature_weights,
        "temporal_patches": temporal_patches,
        "validation_metrics": validation_metrics,
        "meta_labels": meta_labels,
        "layer_execution_metadata": layer_metadata,
        "research_calibration": research,
        "research_risk_stack": research_risk,
        "advanced_reliability_shift": advanced_reliability,
        "similar_day_intelligence": similar_day,
        "regime_transition_trust_center": regime_transition_trust,
        "ten_paper_research_20260621": ten_paper_research,
        "quant_research_v4": quant_research_v4,
        "quant_research_v7": quant_research_v7,
        "research_calculation_id": research.get("canonical_calculation_id"),
        "ai_grounding": {"first_decision": final.get("final_decision"), "decision": final.get("final_decision"), "directional_market_view": final.get("directional_market_view"), "tradeability_decision": final.get("tradeability_decision"), "less_risky_decision": final.get("less_risky_decision"), "blocking_reasons": list(final.get("blocking_reasons") or []), "regime": regime.get("major_regime"), "alpha": regime.get("alpha"), "delta": regime.get("delta"), "prediction_direction": selected_forecast.get("direction"), "prediction_range": {"point": selected_forecast.get("point_forecast"), "lower": selected_forecast.get("lower_bound"), "upper": selected_forecast.get("upper_bound")}, "selected_horizon": selected, "full_metric_scores": {"master": canonical.get("master_score"), "entry": canonical.get("entry_score"), "buy": canonical.get("buy_score"), "sell": canonical.get("sell_score"), "hold": canonical.get("hold_safety"), "tp": canonical.get("tp_quality"), "exit_risk": canonical.get("exit_risk")}, "top_two_daily_candidates": top_two, "reliability_score": reliability.get("score", 0), "uncertainty": final.get("uncertainty_pct"), "error_estimate": final.get("error_estimate_pct"), "nlp_impact": nlp, "research_confirmation": canonical.get("research_confirmation", {}), "research_risk_stack": research_risk, "advanced_reliability_shift": advanced_reliability, "advanced_trust_cap_pct": advanced_reliability.get("trust_cap_pct"), "advanced_crc_status": advanced_crc.get("status"), "advanced_mmd_severity": advanced_mmd.get("severity"), "volatility_regime": multiscale.get("current_volatility_regime"), "regime_entropy": multiscale.get("mean_normalized_entropy"), "transition_risk_pct": multiscale.get("multi_scale_transition_risk_pct"), "multi_scale_agreement_score": multiscale.get("multi_scale_agreement_score_0_10"), "meta_labels": meta_labels, "probabilistic_projection": probabilistic, "research_calibration_id": research.get("canonical_calculation_id"), "research_reliability": research_reliability.get("calibrated_score_0_100"), "uncertainty_separation": research_uncertainty, "bayesian_changepoint": research_change, "conformal_prediction": research_conformal, "baseline_skill": research_skill, "data_quality_score": (canonical.get("data_quality") or {}).get("score", 0), "similar_day_summary": similar_day_summary, "similar_day_reliability": similar_day.get("reliability"), "similar_day_conflict_warning": similar_day.get("conflict_warning"), "regime_transition_trust_center": regime_transition_trust, "ten_paper_research_status": ten_paper_research.get("status"), "ten_paper_shadow_decision": ten_paper_reject.get("shadow_reject_option_decision"), "ten_paper_explanations": ten_paper_explanations, "quant_research_v3_summary": quant_v3_summary, "quant_research_v3_identity": quant_v3_identity, "quant_research_v3_limitations": list(quant_research_v3.get("limitations") or []), "quant_research_v4_summary": quant_v4_summary, "quant_research_v4_identity": quant_v4_identity, "quant_research_v4_errors": list(quant_research_v4.get("errors") or []), "quant_research_v7_summary": quant_v7_summary, "quant_research_v7_identity": quant_v7_identity, "quant_research_v7_evidence": canonical.get("quant_research_v7_ai_evidence", {}), "latest_completed_h1_time": canonical.get("latest_completed_candle_time"), "latest_completed_candle_time": canonical.get("latest_completed_candle_time"), "run_id": canonical.get("run_id"), "calculation_generation": canonical.get("calculation_generation"), "data_signature": canonical.get("data_signature"), "symbol": canonical.get("symbol"), "timeframe": canonical.get("timeframe"), "adapter_meta": _source_meta(canonical, "ai_grounding")},
        "adapter_specs": deepcopy(ADAPTER_SPECS),
        "metadata": {"calculation_source": "canonical_decision_result_20260617", "one_way_legacy_adapter": True, **canonical_identity(canonical)},
    }
    return adapter


def publish_canonical_atomically(
    state: MutableMapping[str, Any], canonical: Dict[str, Any], *, legacy_shared: Optional[Mapping[str, Any]] = None,
    priority_table: Any = None,
    history_bundle: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate staging data and publish all synchronized keys as one generation.

    The last valid canonical run remains untouched if validation fails.
    """
    ok, errors = validate_canonical_result(canonical)
    if not ok:
        state["canonical_publish_error_20260617"] = errors
        state.pop(STAGING_KEY, None)
        raise ValueError("Canonical validation failed: " + "; ".join(errors))
    canonical = normalize_generation_fields(canonical, default=1)
    generation = numeric_generation(canonical.get("calculation_generation"), default=1)
    table = _canonical_priority_frame(priority_table, canonical)
    canonical = dict(canonical)
    if _is_df(table):
        priority_records = table.to_dict("records")
        canonical["priority_table"] = priority_records
        canonical["canonical_priority_table"] = priority_records

    # External architecture only: stamp, checksum, freeze, and atomically persist
    # the completed generation before publishing any UI/session pointer. Protected
    # calculation values are not recalculated or changed here.
    from core.snapshot_schema_20260619 import (
        SNAPSHOT_KEY, SCHEMA_VERSION as SNAPSHOT_SCHEMA_VERSION,
        build_run_snapshot, canonical_checksum,
    )
    canonical.setdefault("calculation_completed_at", _utc_now_iso())
    canonical["snapshot_schema_version"] = SNAPSHOT_SCHEMA_VERSION
    canonical["checksum"] = canonical_checksum(canonical)
    run_snapshot = build_run_snapshot(canonical)
    snapshot_commit_started = time.perf_counter()
    try:
        from services.canonical_snapshot_store import commit_snapshot
        commit_snapshot(run_snapshot, history_bundle=dict(history_bundle or {}))
    except Exception as exc:
        state["canonical_publish_error_20260617"] = [f"snapshot atomic commit failed: {exc}"]
        state.pop(STAGING_KEY, None)
        raise
    try:
        from services.tracing import record
        record(
            state, run_id=run_snapshot.run_id, generation=run_snapshot.generation,
            stage="snapshot_commit", started_at=run_snapshot.calculation_completed_at,
            ended_at=_utc_now_iso(), duration_ms=(time.perf_counter()-snapshot_commit_started)*1000,
            success=True, rows_processed=int(len(table)) if hasattr(table, "__len__") else 0,
            cache_status="MISS", detail="Atomic canonical snapshot committed",
        )
    except Exception:
        pass

    adapter = build_shared_adapter(state, canonical, legacy_shared=legacy_shared, priority_table=table)
    adapter["run_snapshot"] = run_snapshot
    adapter["risk_plan"] = canonical.get("risk_plan", {})
    staging = {"canonical": canonical, "adapter": adapter, "priority_table": table, "published_at": _utc_now_iso()}
    state[STAGING_KEY] = staging

    # Compatibility values are references to the same validated objects; they are
    # not separately recalculated copies.
    state["canonical_priority_table_20260617"] = table
    state["adx_hourly_priority_calibrated_20260615"] = table
    state["three_center_priority_sorted_20260614"] = table
    state["reliability_dynamic_priority_table_20260614"] = table
    state[SHARED_KEY] = adapter
    state[LEGACY_SHARED_KEY] = adapter
    state[SNAPSHOT_KEY] = run_snapshot
    state["canonical_decision_result"] = canonical
    state[LAST_VALID_KEY] = canonical
    state[GENERATION_KEY] = generation
    # Authoritative pointer is written last.
    state[CANONICAL_KEY] = canonical
    # Build the small display/AI projection once, after atomic publication.
    # Failure here is optional and may never invalidate the protected result.
    try:
        from core.compact_canonical_20260619 import publish_compact_runtime
        evidence = table.head(40).to_dict("records") if _is_df(table) and not table.empty else []
        summary, fact_pack = publish_compact_runtime(state, canonical, adapter, evidence_rows=evidence)
        from core.performance_store_20260619 import persist_summary
        persist_summary(str(summary.get("calculation_id")), summary, fact_pack)
    except Exception as exc:
        state["compact_runtime_optional_error_20260619"] = str(exc)
    state["canonical_publish_error_20260617"] = []
    state.pop(STAGING_KEY, None)
    return adapter


def get_canonical(state: Mapping[str, Any]) -> Dict[str, Any]:
    current = state.get(CANONICAL_KEY)
    if isinstance(current, dict) and validate_canonical_result(current)[0]:
        normalized = normalize_generation_fields(current, default=1)
        if isinstance(state, MutableMapping):
            state[CANONICAL_KEY] = normalized
            state[GENERATION_KEY] = normalized["calculation_generation"]
        return normalized
    previous = state.get(LAST_VALID_KEY)
    if isinstance(previous, dict) and validate_canonical_result(previous)[0]:
        normalized = normalize_generation_fields(previous, default=1)
        if isinstance(state, MutableMapping):
            state[LAST_VALID_KEY] = normalized
            state[GENERATION_KEY] = normalized["calculation_generation"]
        return normalized
    return {}


def begin_rerun(state: MutableMapping[str, Any]) -> int:
    try:
        value = int(state.get("app_rerun_identifier_20260617", 0) or 0) + 1
    except Exception:
        value = 1
    state["app_rerun_identifier_20260617"] = value
    state["shared_sync_calls_this_rerun_20260617"] = 0
    state["navigation_authoritative_20260617"] = False
    return value


def build_runtime_context(state: MutableMapping[str, Any], *, active_page: str, active_subpage: str, phone_mode: bool) -> Dict[str, Any]:
    canonical = get_canonical(state)
    identity = canonical_identity(canonical)
    context = {
        "rerun_identifier": state.get("app_rerun_identifier_20260617", 0),
        "active_page": active_page,
        "active_subpage": active_subpage,
        "phone_mode": bool(phone_mode),
        "canonical_result": canonical,
        "canonical_run_id": identity.get("run_id"),
        "canonical_generation": identity.get("calculation_generation"),
        "data_signature": identity.get("data_signature"),
        "symbol": identity.get("symbol") or state.get("symbol"),
        "timeframe": identity.get("timeframe") or state.get("timeframe"),
        "source": identity.get("source") or state.get("source"),
        "canonical_status": "READY" if canonical else "DATA NOT READY",
    }
    state[RUNTIME_CONTEXT_KEY] = context
    state["navigation_authoritative_20260617"] = True
    return context


def shared_from_runtime(state: Mapping[str, Any]) -> Dict[str, Any]:
    value = state.get(SHARED_KEY) or state.get(LEGACY_SHARED_KEY)
    return value if isinstance(value, dict) else {}
