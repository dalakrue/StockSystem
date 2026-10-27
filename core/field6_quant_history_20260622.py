"""Read-only quantitative-trader evidence histories inside existing Lunch Field 6."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping, MutableMapping

import pandas as pd

from core.cross_table_sync_20260622 import validate_cross_table_sync
from core.history_identity_20260620 import canonical_history_identity
from core.shared_broker_time_20260622 import CONTRACT_VERSION, frame_to_shared_broker_clock, shared_broker_time_provider

LOGIC_VERSION = "field6-quant-history-20260622-v1"

FIELD6_TABLES: tuple[tuple[str, str], ...] = (
    ("Broker-Time Synchronization Audit History", "broker_time_synchronization_audit_history"),
    ("Cross-Table Generation Consistency History", "cross_table_generation_consistency_history"),
    ("Forecast Coverage Calibration History", "forecast_coverage_calibration_history"),
    ("Adaptive Coverage Controller History", "adaptive_coverage_controller_history"),
    ("Market Change-Point and Drift History", "market_changepoint_drift_history"),
    ("Conditional Model Skill History", "conditional_model_skill_history"),
    ("Research Rule SPA Validation History", "research_rule_spa_validation_history"),
    ("Execution Cost and Trade Feasibility History", "execution_cost_trade_feasibility_history"),
    ("AI Evidence Retrieval and Answer Audit History", "ai_evidence_retrieval_answer_audit_history"),
    ("AI Risk-Coverage and Abstention History", "ai_risk_coverage_abstention_history"),
    ("Decision Outcome and Settlement History", "decision_outcome_settlement_history"),
)
# Additive V10 histories are separated so older integrations that explicitly
# validate the original eleven-table public contract remain compatible.
FIELD6_ADVANCED_TABLES: tuple[tuple[str, str], ...] = (
    ("Probability Calibration and Brier Score History", "probability_calibration_brier_history"),
    ("Prediction Interval Conditional-Coverage History", "prediction_interval_conditional_coverage_history"),
    ("Christoffersen Coverage-Test History", "christoffersen_coverage_test_history"),
    ("Regime Transition Hazard and Duration History", "regime_transition_hazard_duration_history"),
    ("Backtest Overfitting PBO and Deflated-Sharpe Audit", "backtest_overfitting_pbo_dsr_history"),
    ("Feature Stability and Drift Attribution History", "feature_stability_drift_attribution_history"),
    ("Bayesian Change-Point History", "bayesian_changepoint_history"),
    ("Session-Specific Settled Outcomes", "session_specific_settled_outcomes_history"),
)
ALL_FIELD6_TABLES: tuple[tuple[str, str], ...] = FIELD6_TABLES + FIELD6_ADVANCED_TABLES
QUANT_V6_FIELD6_VIEWS: tuple[tuple[str, str], ...] = (
    ("Cross-Market Alignment History", "quant_v6_cross_market_alignment"),
    ("Session and Overlap Performance", "quant_v6_session_overlap"),
    ("Signal Survival and Churn History", "quant_v6_survival_churn"),
    ("Time-Variance and Drift History", "quant_v6_time_variance_drift"),
    ("Low-Rank Data Quality History", "quant_v6_low_rank_quality"),
    ("Tail-Risk and Execution Feasibility", "quant_v6_tail_execution"),
)
LABEL_TO_TABLE = dict(ALL_FIELD6_TABLES + QUANT_V6_FIELD6_VIEWS)


def _m(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(*values: Any, default: Any = "UNAVAILABLE") -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return default


def _canonical(state: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        if isinstance(value, Mapping) and value:
            return dict(value)
    except Exception:
        pass
    for key in ("canonical_result_20260617", "canonical_decision_result_20260617", "canonical_result"):
        value = state.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
        return number if pd.notna(number) else None
    except Exception:
        return None


def _execution_payload(canonical: Mapping[str, Any]) -> dict[str, Any]:
    execution, market, forecasts, priority = _m(canonical.get("execution")), _m(canonical.get("market")), _m(canonical.get("forecasts")), _m(canonical.get("priority"))
    spread = _safe_float(_first(execution.get("spread_pips"), execution.get("spread_points"), market.get("spread"), default=None))
    slippage = _safe_float(_first(execution.get("estimated_slippage"), execution.get("slippage"), default=None))
    expected_move = _safe_float(_first(execution.get("expected_move"), forecasts.get("expected_move"), default=None))
    transaction_cost = _safe_float(execution.get("expected_transaction_cost"))
    if transaction_cost is None and spread is not None and slippage is not None:
        transaction_cost = spread + slippage
    ratio = transaction_cost / expected_move if transaction_cost is not None and expected_move not in (None, 0.0) else None
    if ratio is None:
        label, reason = "UNAVAILABLE", "Spread, slippage, expected move, or transaction cost is unavailable; no value was invented."
    elif ratio <= 0.25:
        label, reason = "GOOD", "Estimated transaction cost is at most 25% of expected move."
    elif ratio <= 0.50:
        label, reason = "MARGINAL", "Estimated transaction cost is 25–50% of expected move."
    else:
        label, reason = "AVOID", "Estimated transaction cost exceeds 50% of expected move."
    return {
        "spread points/pips": spread if spread is not None else "UNAVAILABLE",
        "estimated slippage": slippage if slippage is not None else "UNAVAILABLE",
        "expected move": expected_move if expected_move is not None else "UNAVAILABLE",
        "forecast horizon": _first(execution.get("forecast_horizon"), forecasts.get("selected_horizon")),
        "expected transaction cost": transaction_cost if transaction_cost is not None else "UNAVAILABLE",
        "cost-to-expected-move ratio": ratio if ratio is not None else "UNAVAILABLE",
        "volatility": _first(market.get("volatility"), canonical.get("volatility")),
        "session": _first(market.get("session"), canonical.get("session")),
        "market quality": _first(priority.get("market_quality"), canonical.get("market_quality")),
        "decision": _first(_m(canonical.get("final_decision")).get("final_decision"), canonical.get("decision")),
        "feasibility label": label,
        "reason": reason,
    }


def _payload_for(table_name: str, state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    contract = shared_broker_time_provider(state, canonical=canonical)
    sync = validate_cross_table_sync(state, canonical=canonical)
    validation = _m(canonical.get("validation_metrics")); drift = _m(canonical.get("drift")); forecasts = _m(canonical.get("forecasts"))
    mapping = {
        "broker_time_synchronization_audit_history": {
            "watermark_status": contract.get("watermark_status"), "freshness_lag_minutes": contract.get("freshness_lag_minutes"),
            "broker_clock_available": contract.get("broker_clock_available"), "broker_clock_resolution": contract.get("broker_clock_resolution"),
            "broker_offset_minutes": contract.get("broker_offset_minutes"), "timestamp_source": contract.get("timestamp_source"),
            "contract_version": contract.get("contract_version"), "status": sync.get("status"),
        },
        "cross_table_generation_consistency_history": {
            "status": sync.get("status"), "table_count": sync.get("table_count"), "table_reports": sync.get("tables"),
        },
        "forecast_coverage_calibration_history": {
            "recent_coverage": _first(validation.get("coverage"), validation.get("recent_coverage")),
            "target_coverage": _first(validation.get("target_coverage"), default=0.90),
            "miscoverage": validation.get("miscoverage", "UNAVAILABLE"), "calibrated_bands": forecasts.get("calibrated_bands", "UNAVAILABLE"),
            "evidence_only": True,
        },
        "adaptive_coverage_controller_history": {
            "recent_coverage": _first(validation.get("coverage"), validation.get("recent_coverage")),
            "target_coverage": _first(validation.get("target_coverage"), default=0.90),
            "controller_adjustment": validation.get("adaptive_coverage_adjustment", "UNAVAILABLE"),
            "controller_status": "EVIDENCE_ONLY",
        },
        "market_changepoint_drift_history": {
            "drift_detected": _first(drift.get("detected"), default=False), "drift_status": drift.get("status", "UNAVAILABLE"),
            "change_probability": _first(drift.get("change_probability"), _m(canonical.get("regime")).get("transition_probability")),
            "change_time": _first(drift.get("time"), _m(canonical.get("regime")).get("last_change")), "evidence_only": True,
        },
        "conditional_model_skill_history": {
            "conditional_skill": validation.get("conditional_skill", "UNAVAILABLE"), "sample_size": validation.get("sample_size", "UNAVAILABLE"),
            "benchmark": validation.get("benchmark", "naive/published benchmark"), "evidence_only": True,
        },
        "research_rule_spa_validation_history": {
            "candidate_rules_or_models": validation.get("spa_candidates", "UNAVAILABLE"), "benchmark": "current protected production decision",
            "spa_statistic": validation.get("spa_statistic", "UNAVAILABLE"), "p_value": validation.get("spa_p_value", "UNAVAILABLE"),
            "data_snooping_warning": True, "evidence_only": True,
        },
        "execution_cost_trade_feasibility_history": _execution_payload(canonical),
        "ai_evidence_retrieval_answer_audit_history": dict(_m(state.get("ai_last_answer_audit_20260622"))) or {"status": "No AI answer has been audited for this generation."},
        "ai_risk_coverage_abstention_history": dict(_m(state.get("ai_last_risk_coverage_audit_20260622"))) or {"status": "No AI risk-coverage decision has been audited for this generation."},
        "decision_outcome_settlement_history": dict(_m(canonical.get("decision_outcome"))) or {"settled_status": "PENDING", "reason": "No settled decision outcome is published for this generation."},
        "probability_calibration_brier_history": {
            "brier_score": _first(validation.get("brier_score"), validation.get("probability_brier_score")),
            "calibration_error": _first(validation.get("calibration_error"), validation.get("ece")),
            "reliability": _first(_m(canonical.get("reliability")).get("score"), canonical.get("reliability_score")),
            "sample_size": validation.get("sample_size", "UNAVAILABLE"),
            "status": validation.get("calibration_status", "EVIDENCE_ONLY"),
        },
        "prediction_interval_conditional_coverage_history": {
            "target_coverage": _first(validation.get("target_coverage"), default=0.90),
            "observed_coverage": _first(validation.get("coverage"), validation.get("recent_coverage")),
            "conditional_coverage_p_value": validation.get("conditional_coverage_p_value", "UNAVAILABLE"),
            "independence_p_value": validation.get("interval_independence_p_value", "UNAVAILABLE"),
            "mean_interval_width": validation.get("mean_interval_width", "UNAVAILABLE"),
            "status": validation.get("coverage_status", "EVIDENCE_ONLY"),
        },
        "christoffersen_coverage_test_history": {
            "sample_size": validation.get("interval_sample_size", validation.get("sample_size", "UNAVAILABLE")),
            "unconditional_coverage_lr": validation.get("christoffersen_lr_uc", "UNAVAILABLE"),
            "unconditional_coverage_p_value": validation.get("christoffersen_uc_p_value", "UNAVAILABLE"),
            "independence_lr": validation.get("christoffersen_lr_ind", "UNAVAILABLE"),
            "independence_p_value": validation.get("interval_independence_p_value", "UNAVAILABLE"),
            "conditional_coverage_lr": validation.get("christoffersen_lr_cc", "UNAVAILABLE"),
            "conditional_coverage_p_value": validation.get("conditional_coverage_p_value", "UNAVAILABLE"),
            "status": "UNAVAILABLE" if _safe_float(validation.get("interval_sample_size", validation.get("sample_size"))) in (None,) or (_safe_float(validation.get("interval_sample_size", validation.get("sample_size"))) or 0) < 20 else "EVIDENCE_ONLY",
        },
        "regime_transition_hazard_duration_history": {
            "major_regime": _first(_m(canonical.get("regime")).get("major_regime"), canonical.get("regime")),
            "regime_age": _first(_m(canonical.get("regime")).get("age"), _m(canonical.get("regime")).get("days_since_change")),
            "expected_duration": _m(canonical.get("regime")).get("expected_duration", "UNAVAILABLE"),
            "estimated_remaining_duration": _first(_m(canonical.get("regime")).get("remaining_duration"), _m(canonical.get("regime")).get("estimated_days_remaining")),
            "transition_probability": _first(_m(canonical.get("transition_trust")).get("transition_probability"), _m(canonical.get("regime")).get("transition_probability")),
            "hazard_rate": _m(canonical.get("regime")).get("transition_hazard", "UNAVAILABLE"),
            "status": "EVIDENCE_ONLY",
        },
        "backtest_overfitting_pbo_dsr_history": {
            "probability_of_backtest_overfitting": _first(validation.get("pbo"), _m(canonical.get("backtest_validation")).get("pbo")),
            "deflated_sharpe_ratio": _first(validation.get("deflated_sharpe_ratio"), _m(canonical.get("backtest_validation")).get("deflated_sharpe_ratio")),
            "candidate_count": _first(validation.get("candidate_model_count"), _m(canonical.get("backtest_validation")).get("candidate_count")),
            "out_of_sample_status": _first(validation.get("out_of_sample_status"), _m(canonical.get("backtest_validation")).get("status")),
            "status": "EVIDENCE_ONLY — unavailable values are not invented",
        },
        "feature_stability_drift_attribution_history": {
            "drift_status": drift.get("status", "UNAVAILABLE"),
            "change_probability": drift.get("change_probability", "UNAVAILABLE"),
            "stable_selected_features": _first(_m(_m(canonical.get("ten_paper_research_20260621")).get("paper_1")).get("stable_selected_features"), validation.get("stable_features")),
            "top_supporting_factors": _m(_m(canonical.get("ten_paper_research_20260621")).get("paper_5")).get("top_supporting_factors", "UNAVAILABLE"),
            "top_opposing_factors": _m(_m(canonical.get("ten_paper_research_20260621")).get("paper_5")).get("top_opposing_factors", "UNAVAILABLE"),
            "status": "EVIDENCE_ONLY",
        },
        "bayesian_changepoint_history": {
            "posterior_change_probability": _first(
                drift.get("change_probability"),
                _m(canonical.get("bayesian_changepoint")).get("change_point_probability"),
                _m(canonical.get("regime")).get("transition_probability"),
            ),
            "change_time": _first(drift.get("time"), _m(canonical.get("regime")).get("last_change")),
            "prior_hazard": _first(_m(canonical.get("bayesian_changepoint")).get("hazard"), _m(canonical.get("regime")).get("transition_hazard")),
            "sample_size": _first(_m(canonical.get("bayesian_changepoint")).get("sample_size"), validation.get("sample_size")),
            "status": "UNAVAILABLE" if not _m(canonical.get("bayesian_changepoint")) and drift.get("change_probability") in (None, "", "UNAVAILABLE") else "EVIDENCE_ONLY",
        },
        "session_specific_settled_outcomes_history": {
            "session": _first(_m(canonical.get("market")).get("session"), canonical.get("session")),
            "london_new_york_overlap": _first(_m(canonical.get("market")).get("london_new_york_overlap"), canonical.get("london_new_york_overlap")),
            "settled_status": _first(_m(canonical.get("decision_outcome")).get("settled_status"), "UNAVAILABLE"),
            "direction_correct": _first(_m(canonical.get("decision_outcome")).get("direction_correct"), "UNAVAILABLE"),
            "absolute_forecast_error": _first(_m(canonical.get("decision_outcome")).get("absolute_forecast_error"), "UNAVAILABLE"),
            "sample_size": _first(_m(canonical.get("decision_outcome")).get("session_sample_size"), validation.get("session_settled_sample_size")),
            "status": "UNAVAILABLE" if str(_m(canonical.get("decision_outcome")).get("settled_status") or "").upper() not in {"SETTLED", "COMPLETED"} else "SETTLED_EVIDENCE",
        },
    }
    return mapping.get(table_name, {})


def _current_row(table_name: str, state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    contract = shared_broker_time_provider(state, canonical=canonical)
    payload = _payload_for(table_name, state, canonical)
    identity = canonical_history_identity(
        canonical,
        condition="CURRENT_GENERATION",
        settled_status="COMPLETED" if table_name not in {"decision_outcome_settlement_history"} else str(payload.get("settled_status") or "PENDING"),
        logic_version=LOGIC_VERSION,
    )
    return {
        **identity,
        "metric_name": table_name,
        "value_text": str(payload.get("status") or payload.get("feasibility label") or payload.get("settled_status") or "EVIDENCE_ONLY"),
        "payload": payload,
        "cache_status": "CURRENT_READ_ONLY_PROJECTION",
    }


def record_ai_audit(state: MutableMapping[str, Any], *, analysis: Mapping[str, Any], question: str, response_status: str, answer_confidence: float, evidence_completeness: float, answer_hash: str) -> dict[str, Any]:
    canonical = _canonical(state)
    identity = canonical_history_identity(canonical, condition=str(analysis.get("domain") or "UNKNOWN"), settled_status="COMPLETED", logic_version=LOGIC_VERSION)
    retrieval_payload = {
        "intent": analysis.get("domain"), "question_hash": sha256(question.encode("utf-8", "ignore")).hexdigest(),
        "evidence_modules": analysis.get("evidence_modules"), "missing_sources": analysis.get("missing_sources"),
        "synchronization_status": analysis.get("synchronization_status"), "data_quality_status": analysis.get("data_quality_status"),
        "answer_hash": answer_hash, "calculation_id": identity.get("calculation_id"), "generation": identity.get("calculation_generation"),
    }
    risk_payload = {
        "intent": analysis.get("domain"), "question_hash": retrieval_payload["question_hash"], "evidence_completeness": evidence_completeness,
        "answer_confidence": answer_confidence, "response_status": response_status,
        "synchronization_status": analysis.get("synchronization_status"), "data_quality_status": analysis.get("data_quality_status"),
        "later_consistency_result": "PENDING",
    }
    state["ai_last_answer_audit_20260622"] = retrieval_payload
    state["ai_last_risk_coverage_audit_20260622"] = risk_payload
    bundle = {
        "ai_evidence_retrieval_answer_audit_history": [{**identity, "metric_name": "ai_answer_audit", "value_text": response_status, "payload": retrieval_payload}],
        "ai_risk_coverage_abstention_history": [{**identity, "metric_name": "ai_risk_coverage", "value_numeric": answer_confidence, "value_text": response_status, "payload": risk_payload}],
    }
    try:
        from core.history_evidence_store_20260620 import append_history_bundle
        return append_history_bundle(bundle)
    except Exception as exc:
        state["ai_audit_storage_error_20260622"] = f"{type(exc).__name__}: {exc}"
        return {"storage_status": "MEMORY_STATE_ONLY", "error": state["ai_audit_storage_error_20260622"]}


def _build_quant_v6_view(table_name: str, state: Mapping[str, Any], limit: int) -> pd.DataFrame:
    try:
        from core.quant_research_v6_store_20260622 import query_v6_market_history
        frame = query_v6_market_history(limit=max(1, min(limit, 500)))
    except Exception:
        frame = state.get("quant_v6_market_history_page_20260622")
        frame = frame.copy(deep=False) if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    if frame.empty:
        statuses = state.get("quant_v6_market_statuses_20260622")
        return pd.DataFrame(statuses if isinstance(statuses, list) else [])
    rename = {"broker_time":"Broker Time", "myanmar_time":"Myanmar Time", "protected_decision":"protected decision", "volatility":"ATR or existing volatility", "spread":"available spread", "slippage":"available slippage", "expected_move":"expected move", "london_new_york_overlap":"London/NY Overlap"}
    frame = frame.rename(columns={k:v for k,v in rename.items() if k in frame.columns})
    if table_name == "quant_v6_cross_market_alignment":
        wanted = ["event_time_utc","Broker Time","Myanmar Time","calculation_id","generation_id","symbol","timeframe","source","completed_status","session","London/NY Overlap","close","return_1","candle_range","ATR or existing volatility","gap_flag","data_quality_status","synchronization_status","logic_version"]
    elif table_name == "quant_v6_session_overlap":
        wanted = ["event_time_utc","Broker Time","symbol","timeframe","session","London/NY Overlap","return_1","direction_correct","absolute_forecast_error","close"]
    elif table_name == "quant_v6_survival_churn":
        wanted = ["event_time_utc","Broker Time","symbol","timeframe","protected decision","signal_survival_probability","churn_risk","regime","forecast_direction","forecast_confidence"]
    elif table_name == "quant_v6_time_variance_drift":
        wanted = ["event_time_utc","Broker Time","symbol","timeframe","return_1","ATR or existing volatility","regime","drift_state","absolute_forecast_error","data_quality_status"]
    elif table_name == "quant_v6_low_rank_quality":
        wanted = ["event_time_utc","Broker Time","symbol","timeframe","return_1","candle_range","ATR or existing volatility","data_quality_status","synchronization_status","gap_flag"]
    else:
        wanted = ["event_time_utc","Broker Time","symbol","timeframe","session","available spread","available slippage","expected move","absolute_forecast_error","drift_state","data_quality_status"]
    cols = [c for c in wanted if c in frame.columns]
    return frame.loc[:, cols].head(limit).reset_index(drop=True)


def build_field6_history_table(table_name: str, state: Mapping[str, Any], *, include_current: bool = True, limit: int = 200) -> pd.DataFrame:
    canonical = _canonical(state)
    if table_name.startswith("quant_v6_"):
        primary = _build_quant_v6_view(table_name, state, limit)
        if len(primary) >= min(25, limit):
            return primary.head(limit).reset_index(drop=True)
        try:
            from core.lunch_h1_data_quality_v13 import field6_fallback
            support = field6_fallback(table_name, state, canonical, limit=limit)
        except Exception:
            support = pd.DataFrame()
        if primary.empty:
            return support.head(limit).reset_index(drop=True)
        return pd.concat([primary, support], ignore_index=True, sort=False).head(limit).reset_index(drop=True)
    contract = shared_broker_time_provider(state, canonical=canonical)
    try:
        from core.history_evidence_store_20260620 import query_history
        stored = query_history(table_name, limit=limit)
    except Exception:
        stored = pd.DataFrame()
    records: list[dict[str, Any]] = []
    if include_current and canonical:
        current = _current_row(table_name, state, canonical)
        payload = dict(_m(current.pop("payload", {})))
        records.append({**current, **payload})
    if not stored.empty:
        for row in stored.to_dict("records"):
            payload = {}
            try:
                payload = json.loads(str(row.get("payload_json") or "{}"))
            except Exception:
                payload = {}
            records.append({**row, **payload})
    if not records:
        try:
            from core.lunch_h1_data_quality_v13 import field6_fallback
            return field6_fallback(table_name, state, canonical, limit=limit)
        except Exception:
            return pd.DataFrame()
    frame = pd.DataFrame(records)
    if "latest_completed_h1" in frame.columns and "event_time_utc" not in frame.columns:
        frame["event_time_utc"] = frame["latest_completed_h1"]
    frame["generation"] = frame.get("calculation_generation", contract.get("calculation_generation"))
    frame["data_quality_status"] = contract.get("data_quality_status")
    frame["synchronization_status"] = validate_cross_table_sync(state, canonical=canonical).get("status")
    frame["logic_version"] = frame.get("logic_version", LOGIC_VERSION)
    frame["contract_version"] = CONTRACT_VERSION
    frame["broker_offset_minutes"] = contract.get("broker_offset_minutes")
    display = frame_to_shared_broker_clock(frame, state, canonical=canonical, hide_raw_utc=False)
    broker_col = next((c for c in display.columns if str(c).startswith("Broker Time")), None)
    if broker_col and broker_col != "Broker Time":
        display = display.rename(columns={broker_col: "Broker Time"})
    myanmar_col = next((c for c in display.columns if str(c).startswith("Myanmar Time")), None)
    if myanmar_col and myanmar_col != "Myanmar Time":
        display = display.rename(columns={myanmar_col: "Myanmar Time"})
    common = [
        "event_time_utc", "Broker Time", "Myanmar Time", "calculation_id", "generation", "symbol", "timeframe", "source",
        "data_quality_status", "synchronization_status", "logic_version", "settled_status",
    ]
    front = [c for c in common if c in display.columns]
    rest = [c for c in display.columns if c not in front and c not in {"payload_json", "record_key", "run_id", "created_at", "latest_completed_h1"}]
    display = display.loc[:, front + rest].drop_duplicates().head(limit).reset_index(drop=True)
    try:
        from core.canonical_sync_v9 import normalize_history_frame
        display = normalize_history_frame(display, field_name="FIELD_6", metric_name=table_name, state=dict(state))
    except Exception:
        pass
    # Keep truthful stored/audit rows first, then fill sparse histories with
    # completed-H1 shadow decision support. The support rows are explicitly
    # marked NOT_A_SETTLED_OUTCOME and cannot alter production decisions.
    if len(display) < min(25, limit):
        try:
            from core.lunch_h1_data_quality_v13 import field6_fallback
            support = field6_fallback(table_name, state, canonical, limit=limit)
            if not support.empty:
                display = pd.concat([display, support], ignore_index=True, sort=False).head(limit)
        except Exception:
            pass
    return display.reset_index(drop=True)


def render_field6_quant_history(state: MutableMapping[str, Any], table_name: str) -> None:
    import streamlit as st
    from ui.copy_tools import central_copy_button
    title = next((label for label, name in ALL_FIELD6_TABLES + QUANT_V6_FIELD6_VIEWS if name == table_name), table_name)
    st.markdown(f"#### {title}")
    st.caption("Read-only evidence/history. Sparse stored audits are supplemented by clearly labelled completed-H1 shadow decision-support rows; protected decisions, strategies, weights, TP/SL and prediction engines are unchanged.")
    frame = build_field6_history_table(table_name, state)
    if frame.empty:
        st.info("No evidence rows are available for this history yet.")
        return
    st.dataframe(frame, use_container_width=True, hide_index=True, height=520)
    central_copy_button(f"Copy {title}", frame.to_csv(index=False), f"field6_quant_{table_name}_20260622", height=112, show_fallback=True)


__all__ = [
    "LOGIC_VERSION", "FIELD6_TABLES", "FIELD6_ADVANCED_TABLES", "ALL_FIELD6_TABLES", "QUANT_V6_FIELD6_VIEWS", "LABEL_TO_TABLE", "build_field6_history_table",
    "render_field6_quant_history", "record_ai_audit",
]
