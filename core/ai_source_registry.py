"""Compact evidence registry over the latest completed canonical generation."""
from __future__ import annotations
from hashlib import sha1
from typing import Any, Mapping, MutableMapping, Iterable


def _m(v: Any) -> Mapping[str, Any]:
    return v if isinstance(v, Mapping) else {}


def _nonempty(v: Any) -> bool:
    return v not in (None, "", [], {})


def _record(source: str, field: str, metric: str, value: Any, explanation: str, *, generation_id: str, completed: Any, symbol: str, timeframe: str, reliability: Any = None, freshness: str = "CURRENT", evidence_status: str = "SETTLED") -> dict[str, Any]:
    raw = f"{generation_id}|{source}|{field}|{metric}|{value}"
    return {
        "evidence_id": sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16],
        "source_name": source,
        "generation_id": generation_id,
        "completed_candle": completed,
        "symbol": symbol,
        "timeframe": timeframe,
        "field": field,
        "metric_name": metric,
        "metric_value": value,
        "short_explanation": explanation,
        "reliability": reliability,
        "freshness": freshness,
        "evidence_status": evidence_status,
    }


def build_source_registry(canonical: Mapping[str, Any], summary: Mapping[str, Any], plan: Mapping[str, Any] | None = None, extra_records: Iterable[Mapping[str, Any]] | None = None, *, max_records: int = 80, state: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    plan = _m(plan)
    identity = _m(summary.get("identity"))
    generation_id = str(summary.get("calculation_id") or canonical.get("canonical_calculation_id") or canonical.get("run_id") or "")
    completed = identity.get("latest_completed_candle_time") or canonical.get("latest_completed_candle_time")
    symbol = str(identity.get("symbol") or canonical.get("symbol") or "EURUSD")
    timeframe = str(identity.get("timeframe") or canonical.get("timeframe") or "H1")
    validation = _m(summary.get("validation"))
    freshness = str(validation.get("stale_status") or validation.get("data_freshness") or "UNKNOWN")
    regime_rel = _m(summary.get("regime")).get("regime_reliability")
    records: list[dict[str, Any]] = []

    def add(source: str, field: str, metric: str, value: Any, explanation: str, reliability: Any = None, status: str = "SETTLED") -> None:
        if _nonempty(value) and len(records) < max_records:
            records.append(_record(source, field, metric, value, explanation, generation_id=generation_id, completed=completed, symbol=symbol, timeframe=timeframe, reliability=reliability, freshness=freshness, evidence_status=status))

    add("Canonical identity", "system_health", "generation_id", generation_id, "Published canonical generation identity.", 100)
    add("Canonical identity", "system_health", "completed_candle", completed, "Latest completed H1 candle used by the generation.", 100)
    if state is not None:
        try:
            from core.shared_broker_time_20260622 import shared_broker_time_provider
            broker_clock = shared_broker_time_provider(state, canonical=canonical)
            add("Shared broker time", "system_health", "broker_candle_time", broker_clock.get("shared_broker_time_display"), "Single broker-candle display time used across Lunch histories.", 100)
        except Exception:
            pass
    add("Canonical market", "decision", "current_price", _m(summary.get("projection")).get("current_close"), "Current close from the completed generation.", 100)

    quant = _m(canonical.get("quant_research_v3"))
    quant_summary = _m(quant.get("summary"))
    quant_identity = _m(quant.get("identity"))
    quant_sample = _m(quant.get("input_contract")).get("retained_row_count")
    quant_limitations = list(quant.get("limitations") or [])
    quant_metrics = {
        "current_volatility_yang_zhang": quant_summary.get("yz_volatility"),
        "har_volatility_state": quant_summary.get("har_volatility_state"),
        "har_h1_forecast_volatility": quant_summary.get("har_h1_forecast_volatility"),
        "latest_move_jump_risk": quant_summary.get("jump_risk"),
        "jump_share": quant_summary.get("jump_share"),
        "downside_var_1h_5pct": quant_summary.get("var_5pct_1h"),
        "downside_var_3h_5pct": quant_summary.get("var_5pct_3h"),
        "downside_var_6h_5pct": quant_summary.get("var_5pct_6h"),
        "expected_shortfall_1h_5pct": quant_summary.get("expected_shortfall_5pct_1h"),
        "cvar_risk_multiplier": quant_summary.get("cvar_risk_multiplier"),
        "pit_berkowitz_density_test": quant_summary.get("density_test"),
        "execution_cost_status": quant_summary.get("execution_cost_status"),
        "overall_quant_v3_status": quant_summary.get("overall_quant_v3_status"),
    }
    for key, value in quant_metrics.items():
        add(
            "Advanced Quant V3 shadow evidence", "quant_research_v3", key, value,
            f"Published Quant V3 value; generation={quant_identity.get('source_generation_id') or generation_id}; sample_count={quant_sample}; production influence disabled.",
            100 if value not in (None, "Unavailable") else 0,
            "SHADOW",
        )
    if quant_limitations:
        add(
            "Advanced Quant V3 assumptions", "quant_research_v3", "unsupported_assumptions_and_limitations",
            " | ".join(str(x) for x in quant_limitations[:6]),
            f"Exact limitations for generation {quant_identity.get('source_generation_id') or generation_id}; sample_count={quant_sample}.",
            100, "SHADOW",
        )

    quant_v4 = _m(canonical.get("quant_research_v4"))
    quant_v4_summary = _m(quant_v4.get("summary"))
    quant_v4_identity = _m(quant_v4.get("identity"))
    quant_v4_metrics = {
        "direction_statistical_skill": quant_v4_summary.get("direction_skill"),
        "direction_skill_p_value": quant_v4_summary.get("direction_skill_p_value"),
        "probability_reliability": quant_v4_summary.get("probability_reliability"),
        "interval_conditional_coverage": quant_v4_summary.get("interval_conditional_coverage"),
        "shadow_regime_state": quant_v4_summary.get("regime_state"),
        "shadow_regime_state_probability": quant_v4_summary.get("regime_state_probability"),
        "next_six_hour_transition_risk": quant_v4_summary.get("transition_risk_6h"),
        "volatility_model_status": quant_v4_summary.get("volatility_model_status"),
        "preferred_shadow_volatility_method": quant_v4_summary.get("preferred_shadow_volatility_method"),
        "tail_risk_backtest": quant_v4_summary.get("tail_risk_backtest"),
        "live_performance_sequential_monitor": quant_v4_summary.get("sequential_monitor"),
        "overall_quant_v4_status": quant_v4_summary.get("overall_status"),
    }
    for key, value in quant_v4_metrics.items():
        add(
            "Advanced Quant V4 shadow verification", "quant_research_v4", key, value,
            f"Published V4 evidence from generation={quant_v4_identity.get('source_generation_id') or generation_id}; broker H1={quant_v4_identity.get('latest_completed_broker_h1_time') or completed}; no refit and no production direction influence.",
            100 if value not in (None, "Unavailable", "INSUFFICIENT_EVIDENCE") else 0,
            "SHADOW",
        )
    v4_limitations = []
    for method_key in (
        "regime_probability", "transition_probability", "realized_garch", "rough_volatility",
        "volatility_evaluation", "probability_decomposition", "directional_skill",
        "interval_backtest", "expected_shortfall_backtest", "sequential_monitor",
    ):
        v4_limitations.extend(list(_m(quant_v4.get(method_key)).get("limitations") or []))
    if v4_limitations:
        add(
            "Advanced Quant V4 assumptions", "quant_research_v4", "limitations_and_insufficient_evidence_policy",
            " | ".join(str(x) for x in v4_limitations[:8]),
            "The AI must answer INSUFFICIENT_EVIDENCE whenever the published method status or support gate does not justify a conclusion.",
            100, "SHADOW",
        )

    quant_v7 = _m(canonical.get("quant_research_v7"))
    quant_v7_identity = _m(quant_v7.get("identity"))
    quant_v7_summary = _m(quant_v7.get("summary"))
    quant_v7_methods = _m(quant_v7.get("methods"))
    def v7_metrics(method_id: str) -> Mapping[str, Any]:
        return _m(_m(quant_v7_methods.get(method_id)).get("output_metrics"))
    v7_facts = {
        "overall_status": quant_v7_summary.get("overall_status"),
        "stable_feature_count": v7_metrics("stability_selection").get("stable_feature_count"),
        "bootstrap_mean_block_length": v7_metrics("stationary_bootstrap").get("mean_block_length"),
        "covariance_condition_improved": v7_metrics("ledoit_wolf_covariance").get("conditioning_improved_or_equal"),
        "dcc_cross_market_state": v7_metrics("dynamic_conditional_correlation").get("cross_market_conflict_state"),
        "gas_uncertainty_state": v7_metrics("generalized_autoregressive_score").get("tail_warning_state"),
        "hsmm_survival_h1": _m(v7_metrics("hidden_semi_markov_duration").get("survival_probability")).get("H+1"),
        "hsmm_survival_h6": _m(v7_metrics("hidden_semi_markov_duration").get("survival_probability")).get("H+6"),
        "midas_status": _m(quant_v7_methods.get("midas_multi_frequency")).get("status"),
        "bds_residual_status": _m(quant_v7_methods.get("bds_residual_test")).get("status"),
        "dynamic_trading_advisory": v7_metrics("dynamic_trading_costs").get("advisory_label"),
        "coherent_risk_state": v7_metrics("coherent_risk").get("final_shadow_risk_state"),
    }
    for key, value in v7_facts.items():
        add(
            "Advanced Quant V7 shadow evidence", "quant_research_v7", key, value,
            f"Published V7 shadow fact; generation={quant_v7_identity.get('source_generation_id') or generation_id}; broker candle={quant_v7_identity.get('completed_broker_time') or completed}; protected decision remains authoritative.",
            100 if value not in (None, "UNAVAILABLE", "INSUFFICIENT_EVIDENCE") else 0, "SHADOW",
        )

    quant_v8 = _m(canonical.get("quant_research_v8"))
    quant_v8_identity = _m(quant_v8.get("identity"))
    morning = _m(quant_v8.get("morning"))
    calibration = _m(quant_v8.get("conformal_calibration"))
    ensemble = _m(quant_v8.get("bates_granger"))
    readiness = _m(quant_v8.get("readiness"))
    field1 = _m(quant_v8.get("field1_data_quality"))
    v8_facts = {
        "morning_readiness": readiness.get("visible_status"),
        "expected_shortfall_95": morning.get("expected_shortfall_95"),
        "expected_shortfall_99": morning.get("expected_shortfall_99"),
        "stress_1atr": morning.get("stress_1atr"),
        "stress_2atr": morning.get("stress_2atr"),
        "stress_3atr": morning.get("stress_3atr"),
        "field1_sync_status": field1.get("sync_status"),
        "calibration_status": calibration.get("status"),
        "calibration_fallback": calibration.get("fallback_level"),
        "effective_expert_count": ensemble.get("effective_expert_count"),
        "production_readiness": readiness.get("overall_status"),
    }
    for key, value in v8_facts.items():
        add(
            "Advanced Quant V8 monitoring evidence", "quant_research_v8", key, value,
            f"Published V8 shadow/validation fact; generation={quant_v8_identity.get('generation_id') or generation_id}; completed H1={quant_v8_identity.get('latest_completed_h1_utc') or completed}; production influence remains disabled unless explicit promotion gates pass.",
            100 if value not in (None, "UNAVAILABLE", "INSUFFICIENT_EVIDENCE") else 0, "SHADOW",
        )

    for key, value in _m(summary.get("decision")).items():
        add("Canonical final decision", "decision", key, value, "Protected final-decision output.", regime_rel)
    for key, value in _m(summary.get("scores")).items():
        add("Protected Full Metric scores", "scores", key, value, "Protected score copied without recalculation.", regime_rel)
    for key, value in _m(summary.get("regime")).items():
        add("Canonical regime", "regime", key, value, "Published regime and transition output.", regime_rel)
    for key, value in _m(summary.get("projection")).items():
        add("Published Power BI projection", "projection", key, value, "Cached path/interval output from the completed generation.", _m(summary.get("projection")).get("projection_confidence"))
    for key, value in _m(summary.get("priority")).items():
        if key != "top_two":
            add("Canonical priority", "priority", key, value, "Published KNN/Greedy priority output.", regime_rel)
    for key, value in _m(summary.get("uncertainty")).items():
        add("Calibration and uncertainty", "reliability", key, value, "Published uncertainty/calibration evidence.", regime_rel)
    for key, value in validation.items():
        add("Validation", "system_health", key, value, "Published validation and freshness status.", 100)
    for key, value in _m(summary.get("similar_day")).items():
        add("Similar-Day intelligence", "similar_day", key, value, "Published historical analogue summary.", _m(summary.get("similar_day")).get("reliability"))
    for key, value in _m(summary.get("nlp")).items():
        add("Published NLP summary", "evidence", key, value, "Settled local/news evidence summary.", _m(summary.get("nlp")).get("reliability"))
    for key, value in _m(canonical.get("history_summary")).items():
        add("Current history summary", "history", key, value, "Bounded summary from synchronized historical evidence.", regime_rel)
    final = _m(canonical.get("final_decision"))
    add("Forecast agreement", "forecast", "forecast_agreement", canonical.get("forecast_agreement") or final.get("forecast_agreement"), "Agreement across the published forecast contributors.", regime_rel)
    add("Risk score", "risk", "exit_risk", canonical.get("exit_risk") or _m(summary.get("scores")).get("exit_risk"), "Protected exit-risk score from the current generation.", regime_rel)
    add("Trend capacity", "scores", "trend_capacity_remaining", canonical.get("trend_capacity_remaining") or _m(summary.get("scores")).get("trend_capacity_remaining"), "Protected remaining trend-capacity output.", regime_rel)
    add("Conflict status", "warnings", "conflict_status", final.get("conflict_status") or final.get("conflict_warning") or canonical.get("conflict_status"), "Current published conflict state.", regime_rel)

    risk_map = {
        "status": plan.get("status"), "recommended_lots": plan.get("recommended_lots"),
        "planned_risk_pct": plan.get("planned_risk_pct"), "planned_dollar_loss": plan.get("planned_dollar_loss"),
        "margin_estimate": plan.get("margin_estimate"), "reason": plan.get("reason"),
        "stop_loss_pips": _m(plan.get("inputs")).get("stop_loss_pips"),
    }
    for key, value in risk_map.items():
        add("Published position sizing", "risk", key, value, "Read-only published risk/position-sizing output.", regime_rel)

    for raw in list(extra_records or [])[:16]:
        if not isinstance(raw, Mapping):
            continue
        metric = raw.get("metric_name") or raw.get("condition") or "settled_evidence"
        value = raw.get("value_text") if _nonempty(raw.get("value_text")) else raw.get("value_numeric")
        add(str(raw.get("source_name") or raw.get("table_name") or "Settled evidence"), str(raw.get("field") or "evidence"), str(metric), value, str(raw.get("short_explanation") or "Settled evidence record."), raw.get("reliability"), str(raw.get("settled_status") or "SETTLED"))
    return records[:max_records]


def load_settled_evidence(required_sources: Iterable[str], *, max_tables: int = 4, rows_per_table: int = 4) -> list[dict[str, Any]]:
    """Load only a tiny selected settled-evidence sample after the user submits."""
    try:
        from core.history_evidence_store_20260620 import catalog_frame, query_history
        catalog = catalog_frame()
    except Exception:
        return []
    if getattr(catalog, "empty", True):
        return []
    wanted = {str(x).lower() for x in required_sources}
    selected: list[str] = []
    for row in catalog.to_dict("records"):
        table = str(row.get("table_name") or row.get("name") or "")
        field = str(row.get("field") or row.get("field_name") or "")
        hay = f"{table} {field}".lower()
        if not wanted or any(token in hay for token in wanted):
            selected.append(table)
        if len(selected) >= max_tables:
            break
    output: list[dict[str, Any]] = []
    for table in selected:
        try:
            frame = query_history(table, limit=rows_per_table)
        except Exception:
            continue
        if getattr(frame, "empty", True):
            continue
        compact_cols = [c for c in ("latest_completed_h1", "record_time", "condition", "metric_name", "value_numeric", "value_text", "coverage_flag", "settled_status", "calculation_generation") if c in frame.columns]
        for row in frame.loc[:, compact_cols].to_dict("records"):
            row["table_name"] = table
            output.append(row)
    return output[: max_tables * rows_per_table]

__all__ = ["build_source_registry", "load_settled_evidence"]
