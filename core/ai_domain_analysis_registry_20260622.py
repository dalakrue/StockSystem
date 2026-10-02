"""Pure read-only domain registry for the local Grounded AI Assistant.

Builders consume a published canonical generation and selected history evidence.
They never import Streamlit renderers and never mutate protected production
outputs.  The only state writes are bounded caches/audits keyed by generation.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
from typing import Any, Callable, Mapping, MutableMapping

import pandas as pd

from core.generation_order_guard_20260622 import generation_cache_key, generation_identity, publish_if_not_older
from core.shared_broker_time_20260622 import shared_broker_time_provider
from core.cross_table_sync_20260622 import validate_cross_table_sync

ANALYSIS_VERSION = "ai-domain-registry-20260622-v1"


def _m(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(*values: Any, default: Any = "UNAVAILABLE") -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return default


def _canonical_from_state(state: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        if isinstance(value, Mapping):
            return dict(value)
    except Exception:
        pass
    for key in ("canonical_result_20260617", "canonical_decision_result_20260617", "canonical_result"):
        value = state.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _history_rows(table_names: tuple[str, ...], calculation_id: str, *, limit_each: int = 25) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    try:
        from core.history_evidence_store_20260620 import query_history
    except Exception:
        return [], list(table_names)
    for table in table_names:
        try:
            frame = query_history(table, calculation_id=calculation_id if calculation_id != "UNAVAILABLE" else None, limit=limit_each)
        except Exception:
            frame = pd.DataFrame()
        if frame.empty:
            missing.append(table)
            continue
        compact = frame.head(limit_each).copy()
        if "payload_json" in compact.columns:
            compact["payload_json"] = compact["payload_json"].astype(str).str.slice(0, 1800)
        for row in compact.to_dict("records"):
            row["table_name"] = table
            rows.append(row)
    return rows, missing


@dataclass
class DomainAnalysis:
    domain: str
    identity: dict[str, Any]
    facts: dict[str, Any]
    history_rows: list[dict[str, Any]]
    evidence_modules: list[str]
    missing_sources: list[str]
    synchronization_status: str
    data_quality_status: str
    deterministic_cache_key: str
    analysis_version: str = ANALYSIS_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Builder = Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], tuple[dict[str, Any], tuple[str, ...], list[str]]]


def _identity(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    contract = shared_broker_time_provider(state, canonical=canonical)
    sync = validate_cross_table_sync(state, canonical=canonical)
    return {
        "calculation_id": contract.get("calculation_id") or "UNAVAILABLE",
        "generation": contract.get("calculation_generation"),
        "event_time_utc": contract.get("event_time_utc"),
        "latest_completed_h1_utc": contract.get("latest_completed_h1_utc"),
        "broker_time": contract.get("broker_time_display"),
        "myanmar_time": contract.get("myanmar_time_display"),
        "broker_offset_minutes": contract.get("broker_offset_minutes"),
        "contract_version": contract.get("contract_version"),
        "symbol": contract.get("symbol"),
        "timeframe": contract.get("timeframe"),
        "source": contract.get("source"),
        "synchronization_status": sync.get("status"),
        "data_quality_status": contract.get("data_quality_status"),
    }


def _decision_facts(c: Mapping[str, Any], s: Mapping[str, Any], p: Mapping[str, Any], state: Mapping[str, Any]):
    final, decision = _m(c.get("final_decision")), _m(s.get("decision"))
    facts = {
        "current_decision": _first(decision.get("current_decision"), final.get("final_decision"), c.get("decision")),
        "direction": _first(decision.get("direction"), final.get("directional_market_view"), c.get("full_metric_direction")),
        "less_risky_decision": _first(decision.get("less_risky_bias"), final.get("less_risky_decision")),
        "main_reason": _first(final.get("main_reason"), final.get("reason"), decision.get("main_reason")),
        "blocking_reasons": _first(final.get("blocking_reasons"), c.get("conflict_warnings"), default=[]),
        "reliability": _first(_m(c.get("reliability")).get("score"), _m(s.get("regime")).get("regime_reliability")),
        "priority": _first(_m(s.get("priority")).get("opportunity_quality"), _m(c.get("priority")).get("priority_label")),
    }
    return facts, ("protected_decision_history", "decision_change_audit_history"), []


def _entry_facts(c, s, p, state):
    facts, tables, missing = _decision_facts(c, s, p, state)
    scores = _m(s.get("scores"))
    facts.update({
        "entry_score": _first(scores.get("entry"), c.get("entry_score")),
        "market_quality": _first(_m(c.get("priority")).get("market_quality"), _m(s.get("priority")).get("market_quality")),
        "forecast_agreement": _first(c.get("forecast_agreement"), _m(c.get("final_decision")).get("forecast_agreement")),
        "regime": _first(_m(c.get("regime")).get("major_regime"), _m(s.get("regime")).get("directional_regime")),
    })
    return facts, tables + ("canonical_priority_history", "reliability_conflict_history"), missing


def _hold_facts(c, s, p, state):
    facts, tables, missing = _decision_facts(c, s, p, state)
    scores = _m(s.get("scores")); final = _m(c.get("final_decision"))
    facts.update({
        "hold_safety": _first(scores.get("hold"), c.get("hold_safety"), c.get("hold_score")),
        "exit_risk": _first(scores.get("exit_risk"), c.get("exit_risk")),
        "trend_capacity_remaining": _first(scores.get("trend_capacity_remaining"), c.get("trend_capacity_remaining")),
        "decision_expiry": _first(final.get("decision_expiry_time"), c.get("expires_at")),
        "hold_warning": _first(final.get("hold_warning"), final.get("blocking_reasons"), default=[]),
    })
    return facts, tables + ("hold_decision_history", "decision_outcome_settlement_history"), missing


def _field6_facts(c, s, p, state):
    combined = _m(state.get("field6_combined_history_summary_20260622"))
    facts = {
        "field6_scope": "stored settled history first; completed-H1 shadow support when sparse",
        "combined_sentiment_technical": combined or state.get("research_sentiment_summary_20260622", "UNAVAILABLE"),
        "technical_summary": state.get("field4_technical_fact_summary_20260622", "UNAVAILABLE"),
        "evidence_classification": "COMPLETED_H1_SHADOW_DECISION_SUPPORT",
        "fallback_settlement_status": "NOT_A_SETTLED_OUTCOME",
        "current_decision": _first(_m(c.get("final_decision")).get("final_decision"), _m(s.get("decision")).get("current_decision")),
        "data_quality": _first(_m(c.get("data_quality")).get("status"), _m(s.get("validation")).get("data_quality_status")),
    }
    return facts, (
        "combined_sentiment_technical_decision_history",
        "session_specific_settled_outcomes_history",
        "decision_outcome_settlement_history",
    ), []


def _field7_facts(c, s, p, state):
    research = _m(state.get("field_07_research_summary_v11"))
    v13 = _m(research.get("v13_research")); compact = _m(v13.get("compact_results"))
    facts = {
        "research_status": research.get("research_status", "UNAVAILABLE"),
        "research_approved_action": research.get("research_approved_action", "UNAVAILABLE"),
        "research_trust_score": research.get("research_trust_score", "UNAVAILABLE"),
        "v13_available_layers": compact.get("available_layers", "UNAVAILABLE"),
        "v13_completed_h1_rows": compact.get("completed_h1_rows", "UNAVAILABLE"),
        "v13_matured_embargoed_outcomes": compact.get("matured_embargoed_outcomes", "UNAVAILABLE"),
        "v13_snapshot_hash": v13.get("snapshot_hash", "UNAVAILABLE"),
        "promotion_status": "SHADOW_ONLY_NOT_PROMOTED",
        "production_changed": False,
        "warnings": list(v13.get("warnings") or [])[:8],
    }
    return facts, ("research_run_summary", "research_rule_spa_validation_history", "decision_outcome_settlement_history"), []


def _session_facts(c, s, p, state):
    market = _m(c.get("market")); priority = _m(c.get("priority")); summary_priority = _m(s.get("priority"))
    facts = {
        "current_session": _first(market.get("session"), c.get("session")),
        "london_new_york_overlap": _first(market.get("london_new_york_overlap"), c.get("london_new_york_overlap")),
        "best_entry_hour": _first(priority.get("best_entry_hour"), summary_priority.get("best_entry_hour")),
        "second_best_entry_hour": _first(priority.get("second_best_entry_hour"), summary_priority.get("second_best_entry_hour")),
        "session_decision": _first(market.get("session_decision"), _m(c.get("final_decision")).get("final_decision")),
        "session_evidence_status": _first(_m(state.get("field6_combined_history_summary_20260622")).get("Session"), "UNAVAILABLE"),
    }
    return facts, ("session_specific_settled_outcomes_history", "canonical_priority_history"), []


def _exit_facts(c, s, p, state):
    facts, tables, missing = _decision_facts(c, s, p, state)
    scores = _m(s.get("scores"))
    facts.update({
        "exit_risk": _first(scores.get("exit_risk"), c.get("exit_risk")),
        "hold_safety": _first(scores.get("hold"), c.get("hold_safety")),
        "trend_capacity_remaining": _first(scores.get("trend_capacity_remaining"), c.get("trend_capacity_remaining")),
        "selected_tp": _first(_m(c.get("final_decision")).get("selected_tp"), _m(c.get("risk")).get("selected_tp")),
        "selected_sl": _first(_m(c.get("final_decision")).get("selected_sl"), _m(c.get("risk")).get("selected_sl")),
    })
    return facts, tables + ("powerbi_forecast_settlement_history",), missing


def _tp_sl_facts(c, s, p, state):
    final, risk, projection = _m(c.get("final_decision")), _m(c.get("risk")), _m(s.get("projection"))
    facts = {
        "selected_tp": _first(final.get("selected_tp"), risk.get("selected_tp"), risk.get("take_profit")),
        "selected_sl": _first(final.get("selected_sl"), risk.get("selected_sl"), risk.get("stop_loss")),
        "tp_sl_guidance": _first(final.get("tp_sl_guidance"), risk.get("tp_sl_guidance")),
        "forecast_horizon": _first(projection.get("selected_horizon"), risk.get("forecast_horizon")),
        "projection_confidence": _first(projection.get("projection_confidence"), final.get("calibrated_confidence")),
        "exit_risk": _first(c.get("exit_risk"), _m(s.get("scores")).get("exit_risk")),
        "current_decision": _first(final.get("final_decision"), _m(s.get("decision")).get("current_decision")),
    }
    return facts, ("powerbi_prediction_ledger", "powerbi_forecast_settlement_history", "decision_outcome_settlement_history"), []


def _forecast_facts(c, s, p, state):
    forecasts, projection = _m(c.get("forecasts")), _m(s.get("projection"))
    facts = {"current_close": projection.get("current_close"), "projection_confidence": projection.get("projection_confidence")}
    horizons = _m(forecasts.get("horizons"))
    for h in range(1, 7):
        item = _m(horizons.get(f"{h}h") or horizons.get(f"H+{h}") or horizons.get(str(h)))
        facts[f"H+{h}"] = item or projection.get(f"h{h}") or "UNAVAILABLE"
    facts["calibrated_bands"] = _first(forecasts.get("calibrated_bands"), projection.get("bands"))
    return facts, ("powerbi_prediction_ledger", "powerbi_forecast_settlement_history", "forecast_coverage_calibration_history"), []


def _regime_facts(c, s, p, state):
    regime = _m(c.get("regime")); sr = _m(s.get("regime")); trust = _m(c.get("transition_trust")); risk = _m(c.get("transition_risk"))
    facts = {
        "current_major_regime": _first(regime.get("major_regime"), sr.get("directional_regime"), c.get("current_major_regime")),
        "regime_start": _first(regime.get("start"), regime.get("regime_start"), regime.get("last_change")),
        "regime_age": _first(regime.get("age"), regime.get("days_since_change"), sr.get("days_since_change")),
        "expected_duration": _first(regime.get("expected_duration"), regime.get("expected_days")),
        "estimated_remaining_duration": _first(regime.get("remaining_duration"), regime.get("estimated_days_remaining")),
        "alpha": _first(regime.get("alpha"), c.get("regime_alpha")),
        "delta": _first(regime.get("delta"), c.get("regime_delta")),
        "transition_probability": _first(trust.get("transition_probability"), risk.get("probability"), regime.get("transition_probability")),
        "transition_trust": _first(trust.get("score"), trust.get("label"), risk.get("status")),
        "regime_reliability": _first(regime.get("reliability"), sr.get("regime_reliability"), _m(c.get("reliability")).get("score")),
        "H1_H4_D1_agreement": _first(regime.get("multitimeframe_agreement"), c.get("h1_h4_d1_agreement")),
        "forecast_regime_conflict": _first(regime.get("forecast_conflict"), _m(c.get("final_decision")).get("conflict_status")),
        "priority_regime_conflict": _first(regime.get("priority_conflict"), _m(c.get("priority")).get("regime_conflict")),
        "change_point_drift": _first(_m(c.get("drift")).get("status"), regime.get("changepoint_status")),
        "similar_day_summary": _first(_m(s.get("similar_day")), state.get("similar_day_summary_20260619")),
    }
    return facts, (
        "regime_overall_history", "regime_standard_history", "regime_duration_history",
        "regime_transition_reliability_history", "regime_alpha_delta_history",
        "regime_conflict_history", "regime_changepoint_history", "similar_day_ranked_match_history",
    ), []


def _bias_facts(c, s, p, state):
    """Build a question-focused directional-bias answer without rerunning the app."""
    final = _m(c.get("final_decision"))
    regime = _m(c.get("regime"))
    priority = _m(c.get("priority"))
    reliability = _m(c.get("reliability"))
    forecasts = _m(c.get("forecasts"))
    technical = _m(c.get("technical_analysis"))
    summary_decision = _m(s.get("decision"))
    summary_regime = _m(s.get("regime"))
    summary_priority = _m(s.get("priority"))

    directional = _first(
        final.get("directional_market_view"),
        final.get("less_risky_decision"),
        summary_decision.get("less_risky_decision"),
        summary_decision.get("current_decision"),
        final.get("final_decision"),
        c.get("direction"),
        c.get("decision"),
    )
    facts = {
        "directional_bias": directional,
        "current_decision": _first(
            final.get("final_decision"),
            summary_decision.get("current_decision"),
            c.get("decision"),
        ),
        "less_risky_bias": _first(
            final.get("less_risky_decision"),
            summary_decision.get("less_risky_decision"),
            directional,
        ),
        "major_regime": _first(
            regime.get("major_regime"),
            regime.get("current_regime"),
            summary_regime.get("directional_regime"),
        ),
        "regime_reliability": _first(
            regime.get("reliability"),
            summary_regime.get("regime_reliability"),
            reliability.get("score"),
            reliability.get("calibrated_score_0_100"),
        ),
        "priority_label": _first(
            priority.get("priority_label"),
            priority.get("opportunity_quality"),
            summary_priority.get("priority_label"),
        ),
        "priority_rank": _first(
            priority.get("priority_rank"),
            priority.get("current_rank"),
            summary_priority.get("priority_rank"),
        ),
        "forecast_direction": _first(
            forecasts.get("direction"),
            forecasts.get("forecast_direction"),
            _m(c.get("powerbi")).get("direction"),
        ),
        "forecast_agreement": _first(
            forecasts.get("agreement"),
            _m(c.get("validation_metrics")).get("forecast_agreement"),
            c.get("forecast_agreement"),
        ),
        "technical_bias": _first(
            technical.get("direction"),
            technical.get("bias"),
            state.get("field4_technical_fact_summary_20260622"),
        ),
        "sentiment_bias": _first(
            _m(c.get("sentiment")).get("direction"),
            _m(c.get("sentiment")).get("bias"),
            state.get("research_sentiment_summary_20260622"),
        ),
        "conflict_status": _first(
            final.get("conflict_status"),
            c.get("conflict_status"),
            regime.get("forecast_conflict"),
        ),
        "uncertainty": _first(
            _m(s.get("uncertainty")).get("uncertainty_pct"),
            reliability.get("uncertainty"),
            c.get("uncertainty_pct"),
        ),
    }
    return facts, (
        "protected_decision_history",
        "regime_overall_history",
        "canonical_priority_history",
        "powerbi_prediction_ledger",
        "reliability_conflict_history",
        "combined_sentiment_technical_decision_history",
    ), []


def _reliability_facts(c, s, p, state):
    reliability, uncertainty, validation = _m(c.get("reliability")), _m(s.get("uncertainty")), _m(s.get("validation"))
    facts = {
        "reliability": _first(reliability.get("score"), reliability.get("calibrated_score_0_100"), _m(s.get("regime")).get("regime_reliability")),
        "uncertainty": _first(uncertainty.get("uncertainty_pct"), uncertainty.get("uncertainty")),
        "calibration_error": _first(uncertainty.get("error_pct"), validation.get("calibration_error")),
        "forecast_coverage": _first(validation.get("coverage"), _m(c.get("validation_metrics")).get("coverage")),
        "conflict_status": _first(_m(c.get("final_decision")).get("conflict_status"), c.get("conflict_status")),
    }
    return facts, ("reliability_conflict_history", "forecast_coverage_calibration_history", "adaptive_coverage_controller_history"), []


def _priority_facts(c, s, p, state):
    priority = dict(_m(c.get("priority"))); priority.update(dict(_m(s.get("priority"))))
    facts = {
        "priority_label": _first(priority.get("opportunity_quality"), priority.get("priority_label"), priority.get("knn_priority")),
        "priority_rank": _first(priority.get("current_rank"), priority.get("priority_rank")),
        "best_entry_hour": _first(priority.get("best_entry_hour"), priority.get("best_hour")),
        "second_best_entry_hour": _first(priority.get("second_best_entry_hour"), priority.get("second_best_hour")),
        "greedy_score": priority.get("greedy_score", "UNAVAILABLE"),
        "knn_score": priority.get("knn_score", "UNAVAILABLE"),
    }
    return facts, ("canonical_priority_history", "knn_rank_history", "greedy_rank_history"), []


def _similar_day_facts(c, s, p, state):
    facts = dict(_m(s.get("similar_day"))) or dict(_m(c.get("similar_day")))
    if not facts:
        facts = {"summary": state.get("similar_day_summary_20260619", "UNAVAILABLE")}
    return facts, ("similar_day_query_history", "similar_day_ranked_match_history", "similar_day_outcome_history", "motif_history", "discord_history"), []


def _sentiment_facts(c, s, p, state):
    facts = dict(_m(c.get("sentiment")))
    facts.update(dict(_m(state.get("research_sentiment_summary_20260622"))))
    if not facts:
        facts = {"sentiment_summary": state.get("research_sentiment_summary_20260622", "UNAVAILABLE")}
    return facts, ("combined_sentiment_technical_decision_history",), []


def _technical_facts(c, s, p, state):
    facts = dict(_m(c.get("technical_analysis")))
    facts.update(dict(_m(state.get("field4_technical_fact_summary_20260622"))))
    if not facts:
        facts = {"technical_summary": state.get("field4_technical_fact_summary_20260622", "UNAVAILABLE")}
    return facts, ("canonical_priority_history", "reliability_conflict_history"), []


def _agreement_facts(c, s, p, state):
    facts = {
        "sentiment": state.get("research_sentiment_summary_20260622", "UNAVAILABLE"),
        "technical": state.get("field4_technical_fact_summary_20260622", "UNAVAILABLE"),
        "decision": _first(_m(c.get("final_decision")).get("final_decision"), _m(s.get("decision")).get("current_decision")),
        "agreement": _first(_m(c.get("agreement")).get("status"), _m(state.get("field6_combined_history_summary_20260622")).get("Agreement")),
        "conflict": _first(_m(c.get("final_decision")).get("conflict_status"), c.get("conflict_status")),
    }
    return facts, ("combined_sentiment_technical_decision_history", "reliability_conflict_history"), []


def _position_facts(c, s, p, state):
    risk = dict(_m(c.get("risk"))); risk.update(dict(_m(p)))
    facts = {
        "recommended_lots": risk.get("recommended_lots", "UNAVAILABLE"),
        "planned_risk_pct": risk.get("planned_risk_pct", "UNAVAILABLE"),
        "planned_dollar_loss": risk.get("planned_dollar_loss", "UNAVAILABLE"),
        "margin_estimate": risk.get("margin_estimate", "UNAVAILABLE"),
        "stop_loss_pips": _first(_m(risk.get("inputs")).get("stop_loss_pips"), risk.get("stop_loss_pips")),
        "status": risk.get("status", "UNAVAILABLE"),
        "reason": risk.get("reason", "UNAVAILABLE"),
    }
    return facts, ("execution_cost_trade_feasibility_history",), []


def _execution_facts(c, s, p, state):
    execution = _m(c.get("execution")); market = _m(c.get("market"))
    facts = {
        "spread_points_pips": _first(execution.get("spread_pips"), execution.get("spread_points"), market.get("spread")),
        "estimated_slippage": _first(execution.get("estimated_slippage"), execution.get("slippage")),
        "expected_move": _first(execution.get("expected_move"), _m(c.get("forecasts")).get("expected_move")),
        "expected_transaction_cost": execution.get("expected_transaction_cost", "UNAVAILABLE"),
        "cost_to_expected_move_ratio": execution.get("cost_to_expected_move_ratio", "UNAVAILABLE"),
        "feasibility_label": execution.get("feasibility_label", "UNAVAILABLE"),
        "reason": execution.get("reason", "Unavailable inputs are never invented."),
    }
    return facts, ("execution_cost_trade_feasibility_history",), []


def _validation_facts(c, s, p, state):
    facts = dict(_m(c.get("validation_metrics"))); facts.update(dict(_m(s.get("validation"))))
    return facts or {"validation": "UNAVAILABLE"}, ("forecast_coverage_calibration_history", "conditional_model_skill_history", "research_rule_spa_validation_history", "decision_outcome_settlement_history"), []


def _data_quality_facts(c, s, p, state):
    facts = dict(_m(c.get("data_quality"))); facts.update(dict(_m(s.get("validation"))))
    facts["cross_table_sync"] = validate_cross_table_sync(state, canonical=c)
    return facts, ("broker_time_synchronization_audit_history", "cross_table_generation_consistency_history", "input_data_quality_history"), []


def _system_health_facts(c, s, p, state):
    facts = _data_quality_facts(c, s, p, state)[0]
    facts.update({"connector_state": state.get("connector_state_20260621", state.get("source", "UNAVAILABLE")), "calculation_status": state.get("last_calculation_status_20260617", "UNAVAILABLE")})
    return facts, ("broker_time_synchronization_audit_history", "cross_table_generation_consistency_history", "cache_diagnostics_history", "performance_history"), []


def _historical_facts(c, s, p, state):
    facts = dict(_m(c.get("history_summary")))
    return facts or {"history_summary": "UNAVAILABLE"}, ("full_metric_overall_history", "protected_decision_history", "regime_overall_history", "canonical_priority_history", "decision_outcome_settlement_history"), []


DOMAIN_BUILDERS: dict[str, Builder] = {
    "market_time_and_synchronization": _data_quality_facts,
    "current_decision": _decision_facts,
    "entry": _entry_facts,
    "hold": _hold_facts,
    "exit": _exit_facts,
    "field6_evidence": _field6_facts,
    "field7_research": _field7_facts,
    "session_evidence": _session_facts,
    "tp_sl": _tp_sl_facts,
    "price_forecast": _forecast_facts,
    "regime": _regime_facts,
    "regime_transition": _regime_facts,
    "alpha_delta": _regime_facts,
    "reliability_uncertainty": _reliability_facts,
    "priority_best_hours": _priority_facts,
    "similar_day_pattern": _similar_day_facts,
    "sentiment": _sentiment_facts,
    "technical_analysis": _technical_facts,
    "sentiment_technical_decision_agreement": _agreement_facts,
    "position_sizing": _position_facts,
    "execution_cost_feasibility": _execution_facts,
    "forecast_validation": _validation_facts,
    "data_quality": _data_quality_facts,
    "system_health": _system_health_facts,
    "historical_comparison": _historical_facts,
    "directional_bias": _bias_facts,
}

INTENT_TO_DOMAIN = {
    "market_time": "market_time_and_synchronization",
    "decision_explanation": "current_decision",
    "entry_guidance": "entry",
    "hold_guidance": "hold",
    "exit_guidance": "exit",
    "field6_evidence": "field6_evidence",
    "field7_research": "field7_research",
    "session_evidence": "session_evidence",
    "tp_sl_guidance": "tp_sl",
    "price_forecast": "price_forecast",
    "regime_explanation": "regime",
    "regime_transition": "regime_transition",
    "alpha_delta": "alpha_delta",
    "reliability_explanation": "reliability_uncertainty",
    "priority_ranking": "priority_best_hours",
    "similar_day": "similar_day_pattern",
    "sentiment_analysis": "sentiment",
    "technical_analysis": "technical_analysis",
    "agreement_analysis": "sentiment_technical_decision_agreement",
    "risk_position_sizing": "position_sizing",
    "execution_feasibility": "execution_cost_feasibility",
    "forecast_validation": "forecast_validation",
    "data_quality": "data_quality",
    "system_health": "system_health",
    "historical_comparison": "historical_comparison",
    "bias_analysis": "directional_bias",
}


def execute_domain_analysis(
    intent: str,
    *,
    question: str,
    canonical: Mapping[str, Any] | None,
    summary: Mapping[str, Any] | None,
    plan: Mapping[str, Any] | None,
    state: MutableMapping[str, Any],
) -> dict[str, Any]:
    canonical = dict(canonical or _canonical_from_state(state))
    summary = dict(summary or {})
    plan = dict(plan or {})
    domain = INTENT_TO_DOMAIN.get(intent, "current_decision")
    contract = shared_broker_time_provider(state, canonical=canonical)
    normalized_question = " ".join(str(question or "").lower().split())
    cache_key = generation_cache_key(
        canonical=canonical,
        namespace=f"ai-domain:{domain}",
        extra={
            "question": normalized_question,
            "broker_offset_minutes": contract.get("broker_offset_minutes"),
            "contract_version": contract.get("contract_version"),
            "analysis_version": ANALYSIS_VERSION,
        },
    )
    cache = state.setdefault("ai_domain_analysis_cache_20260622", {})
    if isinstance(cache, MutableMapping) and cache_key in cache:
        result = dict(cache[cache_key])
        result["cache_hit"] = True
        return result

    builder = DOMAIN_BUILDERS[domain]
    identity = _identity(state, canonical)
    facts, tables, explicit_missing = builder(canonical, summary, plan, state)
    history_rows, history_missing = _history_rows(tables, str(identity.get("calculation_id")), limit_each=25 if domain in {"regime", "historical_comparison"} else 8)
    missing = list(dict.fromkeys([*explicit_missing, *history_missing]))
    modules = list(dict.fromkeys([domain, *tables]))
    result_obj = DomainAnalysis(
        domain=domain,
        identity=identity,
        facts=dict(facts),
        history_rows=history_rows,
        evidence_modules=modules,
        missing_sources=missing,
        synchronization_status=str(identity.get("synchronization_status") or "UNAVAILABLE"),
        data_quality_status=str(identity.get("data_quality_status") or "UNAVAILABLE"),
        deterministic_cache_key=cache_key,
    )
    result = result_obj.to_dict()
    result["cache_hit"] = False
    if isinstance(cache, MutableMapping):
        cache[cache_key] = result
        # Bounded deterministic cache.
        while len(cache) > 40:
            cache.pop(next(iter(cache)))
    state["ai_last_executed_domain_20260622"] = domain
    state["ai_domain_execution_trace_20260622"] = [domain]
    publish_if_not_older(state, key="ai_last_domain_analysis_20260622", value=result, candidate=canonical)
    return result


__all__ = [
    "ANALYSIS_VERSION", "DOMAIN_BUILDERS", "INTENT_TO_DOMAIN", "DomainAnalysis",
    "execute_domain_analysis",
]
