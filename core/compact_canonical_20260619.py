"""Compact immutable runtime summary and AI fact-pack helpers.

This module never calculates protected trading values.  It only projects the
already-published canonical generation into small display/AI payloads so page
navigation does not deserialize or scan full histories.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping, MutableMapping, Sequence

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None  # type: ignore

SUMMARY_KEY = "compact_canonical_summary_20260619"
FACT_PACK_KEY = "ai_fact_pack_20260619"
BOUNDED_CACHE_KEY = "bounded_canonical_cache_20260619"
ACTIVE_CALCULATION_ID_KEY = "active_calculation_id_20260619"
SCHEMA_VERSION = "adx-compact-runtime-1.0.0"
CACHE_VERSION = "20260619-v1"
MAX_GENERATIONS = 2
MAX_EVIDENCE_ROWS = 40


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if number != number:
            return float(default)
        return number
    except Exception:
        return float(default)


def _pct(value: Any, default: float = 0.0) -> float:
    number = _num(value, default)
    if 0.0 <= number <= 1.0:
        number *= 100.0
    return max(0.0, min(100.0, number))


def _text(value: Any, default: str = "-") -> str:
    if value in (None, ""):
        return default
    return str(value)


def calculation_id(canonical: Mapping[str, Any]) -> str:
    """Return the one published calculation ID used by every workspace.

    Successful canonical runs carry an explicit ID. Compatibility payloads that
    lack it are deterministically keyed by run, generation and completed candle
    so a new H1 candle can never reuse a stale display/cache generation.
    """
    explicit = _first(canonical.get("calculation_id"), canonical.get("canonical_calculation_id"))
    if explicit:
        return str(explicit)
    generation = canonical.get("calculation_generation")
    signature = canonical.get("data_signature")
    candle = canonical.get("latest_completed_candle_time")
    run_id = canonical.get("run_id")
    raw = "|".join(map(str, (run_id, signature, candle, generation, canonical.get("symbol"), canonical.get("timeframe"))))
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:24]


def _priority_best(shared: Mapping[str, Any], canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    priority = _mapping(shared.get("priority"))
    best = _mapping(priority.get("best"))
    if best:
        return best
    candidates = canonical.get("top_two_daily_candidates") or canonical.get("opportunity_candidates") or []
    return _mapping(candidates[0]) if isinstance(candidates, Sequence) and candidates else {}


def _forecast(canonical: Mapping[str, Any], horizon: int) -> Mapping[str, Any]:
    forecasts = _mapping(canonical.get("forecasts"))
    horizons = _mapping(forecasts.get("horizons"))
    return _mapping(horizons.get(f"{horizon}h"))


def build_compact_summary(
    canonical: Mapping[str, Any] | None,
    shared: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return all values required by Lunch/Dinner in a small deterministic dict."""
    canonical = _mapping(canonical)
    shared = _mapping(shared)
    final = _mapping(canonical.get("final_decision"))
    regime = _mapping(canonical.get("regime"))
    reliability = _mapping(canonical.get("reliability"))
    risk = _mapping(canonical.get("risk"))
    data_quality = _mapping(canonical.get("data_quality"))
    market = _mapping(canonical.get("market"))
    priority = _mapping(canonical.get("priority"))
    shared_current = _mapping(shared.get("current"))
    shared_decision = _mapping(shared.get("decision"))
    shared_reliability = _mapping(shared.get("reliability"))
    shared_regime = _mapping(shared.get("regime"))
    nlp = _mapping(canonical.get("nlp"))
    shared_nlp = _mapping(shared.get("nlp"))
    nlp_summary = _mapping(shared_nlp.get("summary"))
    multiscale = _mapping(canonical.get("multiscale_regime"))
    research = _mapping(canonical.get("research_calibration"))
    research_risk = _mapping(canonical.get("research_risk_stack"))
    research_risk_summary = _mapping(research_risk.get("current_summary"))
    similar_day = _mapping(canonical.get("similar_day_intelligence"))
    similar_day_summary = _mapping(similar_day.get("summary"))
    uncertainty = _mapping(research.get("uncertainty"))
    changepoint = _mapping(research.get("bayesian_changepoint"))
    validation = _mapping(canonical.get("validation_metrics"))
    pattern = _mapping(canonical.get("pattern_memory"))
    transition = _mapping(canonical.get("transition_risk"))
    actionability = _mapping(canonical.get("actionability"))
    best = _priority_best(shared, canonical)
    h1, h3, h6 = _forecast(canonical, 1), _forecast(canonical, 3), _forecast(canonical, 6)
    selected_horizon = int(_num(_first(final.get("selected_horizon"), _mapping(canonical.get("forecasts")).get("selected_horizon"), default=3), 3))
    selected_forecast = _forecast(canonical, selected_horizon)
    powerbi = _mapping(shared.get("powerbi"))
    powerbi_summary = _mapping(powerbi.get("summary"))
    top_two = canonical.get("top_two_daily_candidates") or []
    if not isinstance(top_two, list):
        top_two = []

    decision_value = _first(
        final.get("final_decision"),
        shared_decision.get("central_decision"),
        shared_current.get("decision"),
        canonical.get("decision"),
        default="WAIT",
    )
    direction = _first(
        final.get("directional_market_view"),
        canonical.get("full_metric_direction"),
        shared_decision.get("directional_market_view"),
        shared_current.get("regime_direction"),
        default="WAIT",
    )
    less_risky = _first(final.get("less_risky_decision"), shared_current.get("less_risky_decision"), default="WAIT")
    tradeability = _first(final.get("tradeability_decision"), canonical.get("tradeability_decision"), default="WAIT")
    current_close = _num(_first(canonical.get("last_close"), market.get("current_price"), shared_current.get("last_close")), 0.0)
    calc_id = calculation_id(canonical)
    latest_candle = _first(canonical.get("latest_completed_candle_time"), market.get("latest_completed_candle_time"), default="-")
    layer_status = _first(canonical.get("calculation_status"), default="DATA NOT READY")
    validation_status = _first(research.get("validation_status"), validation.get("status"), reliability.get("status"), default="INSUFFICIENT SAMPLE")
    stale = bool(canonical.get("stale") or _mapping(canonical.get("metadata")).get("stale"))

    summary = {
        "schema_version": SCHEMA_VERSION,
        "cache_version": CACHE_VERSION,
        "calculation_id": calc_id,
        "identity": {
            "run_id": canonical.get("run_id"),
            "calculation_generation": canonical.get("calculation_generation"),
            "data_signature": canonical.get("data_signature"),
            "symbol": canonical.get("symbol", "EURUSD"),
            "timeframe": canonical.get("timeframe", "H1"),
            "source": canonical.get("source"),
            "calculation_timestamp": canonical.get("created_at"),
            "latest_completed_candle_time": latest_candle,
            "calculation_version": canonical.get("calculation_version"),
        },
        "decision": {
            "current_decision": _text(decision_value, "WAIT"),
            "direction": _text(direction, "WAIT"),
            "less_risky_bias": _text(less_risky, "WAIT"),
            "tradeability": _text(tradeability, "WAIT"),
            "timing": _text(canonical.get("m1_timing_status") or final.get("timing_status") or f"{selected_horizon}h selected", "WAIT"),
            "risk_label": _text(risk.get("risk_level") or transition.get("status") or "WATCH"),
            "main_reason": _text(final.get("main_reason"), "No reason available"),
            "blocking_reasons": [str(x) for x in list(final.get("blocking_reasons") or [])[:12]],
            "expected_value": _num(final.get("expected_value") or actionability.get("expected_value"), 0.0),
        },
        "scores": {
            "master": _num(_first(canonical.get("master_score"), shared_current.get("master_score")), 0.0),
            "entry": _num(_first(canonical.get("entry_score"), shared_current.get("entry_score")), 0.0),
            "hold": _num(_first(canonical.get("hold_safety"), shared_current.get("hold_safety")), 0.0),
            "tp": _num(_first(canonical.get("tp_quality"), shared_current.get("tp_quality")), 0.0),
            "exit_risk": _num(_first(canonical.get("exit_risk"), shared_current.get("exit_risk")), 0.0),
            "trend_capacity_remaining": _num(_first(canonical.get("trend_capacity_remaining"), shared_current.get("trend_capacity_remaining")), 0.0),
        },
        "regime": {
            "directional_regime": _text(_first(regime.get("major_regime"), canonical.get("current_major_regime"), shared_regime.get("current")), "UNKNOWN"),
            "volatility_regime": _text(_first(multiscale.get("current_volatility_regime"), shared_regime.get("volatility_regime")), "UNKNOWN"),
            "regime_reliability": _pct(_first(reliability.get("score"), shared_reliability.get("score")), 0.0),
            "alpha": _num(_first(canonical.get("alpha"), regime.get("alpha"), _mapping(shared.get("regime_alpha_delta")).get("alpha")), 0.0),
            "delta": _num(_first(canonical.get("delta"), regime.get("delta"), _mapping(shared.get("regime_alpha_delta")).get("delta")), 0.0),
            "transition_risk": _pct(_first(changepoint.get("transition_risk_0_100"), multiscale.get("multi_scale_transition_risk_pct"), transition.get("value")), 0.0),
            "estimated_transition_window": _text(_first(changepoint.get("estimated_transition_window"), regime.get("estimated_transition_window")), "Not estimated"),
            "pattern_confirmation": _text(pattern.get("pattern_confirmation"), "NEUTRAL"),
        },
        "projection": {
            "projection_confidence": _pct(_first(final.get("calibrated_confidence"), selected_forecast.get("reliability"), powerbi_summary.get("reliability_pct")), 0.0),
            "path_agreement": _pct(_first(powerbi_summary.get("path_agreement_pct"), _mapping(canonical.get("forecasts")).get("agreement_score")), 0.0),
            "current_close": current_close,
            "h1": _num(h1.get("point_forecast"), current_close),
            "h3": _num(h3.get("point_forecast"), current_close),
            "h6": _num(h6.get("point_forecast"), current_close),
            "lower_band": _num(_first(h6.get("lower_bound"), selected_forecast.get("lower_bound")), current_close),
            "upper_band": _num(_first(h6.get("upper_bound"), selected_forecast.get("upper_bound")), current_close),
            "selected_horizon": selected_horizon,
            "red_path_preserved": True,
            "yellow_path_preserved": True,
            "blue_path_preserved": True,
        },
        "priority": {
            "knn_priority": _text(_first(best.get("KNN Priority"), best.get("priority rank"), priority.get("rank")), "N/A"),
            "greedy_priority": _text(_first(best.get("Greedy Priority"), best.get("priority rank"), priority.get("rank")), "N/A"),
            "current_rank": _text(_first(best.get("Priority Rank 1-14"), best.get("Priority Rank"), best.get("priority rank"), priority.get("rank")), "N/A"),
            "best_entry_hour": _text(_first(best.get("Hour"), best.get("hour"), _mapping(top_two[0] if top_two else {}).get("Hour")), "N/A"),
            "second_best_entry_hour": _text(_first(_mapping(top_two[1] if len(top_two) > 1 else {}).get("Hour"), _mapping(top_two[1] if len(top_two) > 1 else {}).get("Candidate Timestamp")), "N/A"),
            "opportunity_quality": _text(_first(best.get("Priority Label"), best.get("priority label"), best.get("Qualification Status"), priority.get("label")), "WATCH"),
            "top_two": deepcopy(top_two[:2]),
        },
        "uncertainty": {
            "aleatoric": _pct(_first(uncertainty.get("aleatoric_uncertainty_0_100"), final.get("aleatoric_uncertainty")), 0.0),
            "epistemic": _pct(_first(uncertainty.get("epistemic_uncertainty_0_100"), final.get("epistemic_uncertainty")), 0.0),
            "combined": _pct(_first(uncertainty.get("combined_uncertainty_0_100"), final.get("uncertainty_pct")), 0.0),
            "main_source": _text(_first(uncertainty.get("main_uncertainty_source"), risk.get("main_uncertainty_source")), "Not classified"),
            "calibration_status": _text(_first(reliability.get("status"), validation_status), "INSUFFICIENT SAMPLE"),
            "sample_size_status": _text(_first(reliability.get("sample_count"), research.get("sample_count")), "0"),
        },
        "nlp": {
            "direction": _text(_first(nlp.get("direction"), nlp_summary.get("nlp_direction")), "WAIT"),
            "reliability": _pct(_first(nlp.get("reliability"), nlp_summary.get("reliability")), 0.0),
            "conflict": _text(_first(nlp.get("conflict_level"), nlp_summary.get("conflict_level")), "NO NLP DATA"),
            "highest_ranked_news": _text(_first(nlp.get("latest_headline"), nlp_summary.get("latest_rank_1_news")), "No relevant news"),
            "news_time": _text(_first(nlp.get("latest_time"), nlp_summary.get("news_time")), "Not available"),
            "event_impact": _text(_first(nlp.get("importance"), nlp.get("impact"), nlp_summary.get("impact")), "N/A"),
            "event_risk_condition": _text(_first(nlp.get("event_risk_condition"), nlp_summary.get("event_risk_condition"), nlp_summary.get("conflict_level")), "WATCH"),
        },
        "research_risk": {
            "required_confidence_threshold": _num(_first(final.get("required_confidence_threshold"), research_risk_summary.get("required_confidence_threshold")), 90.0),
            "selective_prediction_pass": bool(_first(final.get("selective_prediction_pass"), research_risk_summary.get("selective_prediction_pass"), default=False)),
            "tp_first_probability": _pct(_first(final.get("tp_first_probability"), research_risk_summary.get("tp_first_probability")), 0.0),
            "sl_first_probability": _pct(_first(final.get("sl_first_probability"), research_risk_summary.get("sl_first_probability")), 0.0),
            "robust_expected_value": _num(_first(final.get("robust_expected_value"), research_risk_summary.get("robust_expected_value")), 0.0),
            "extreme_risk_block": bool(_first(final.get("extreme_risk_warning"), research_risk_summary.get("extreme_risk_block"), default=False)),
            "display_risk_multiplier": _num(_first(final.get("display_risk_multiplier"), research_risk_summary.get("display_risk_multiplier")), 0.0),
            "trust_status": _text(_mapping(research_risk.get("confidence_sequence")).get("trust_status"), "INSUFFICIENT_DATA"),
            "event_cluster_level": _text(_mapping(research_risk.get("event_intensity")).get("event_cluster_level"), "LOW"),
            "reason": _text(final.get("research_risk_reason"), "Research risk stack not yet available"),
        },
        "similar_day": {
            "pattern_family": _text(similar_day_summary.get("Current pattern family"), "Unavailable"),
            "best_match_date": _text(similar_day_summary.get("Best historical match date"), "Unavailable"),
            "similarity_index": _num(similar_day_summary.get("Best Similarity Index"), 0.0),
            "weighted_result": _text(similar_day_summary.get("Weighted historical result"), "WAIT"),
            "h1_median_pips": _num(similar_day_summary.get("Weighted median H+1 movement"), 0.0),
            "h3_median_pips": _num(similar_day_summary.get("Weighted median H+3 movement"), 0.0),
            "h6_median_pips": _num(similar_day_summary.get("Weighted median H+6 movement"), 0.0),
            "effective_sample_size": _num(similar_day_summary.get("Effective sample size"), 0.0),
            "reliability": _text(similar_day.get("reliability") or similar_day_summary.get("Similar-day reliability"), "Unavailable"),
            "conflict_warning": _text(similar_day.get("conflict_warning"), ""),
            "is_probability": False,
        },
        "quant_research_v3": {
            **deepcopy(dict(_mapping(canonical.get("quant_research_v3")).get("summary") or {})),
            "source_generation_id": _mapping(_mapping(canonical.get("quant_research_v3")).get("identity")).get("source_generation_id"),
            "completed_h1_time": _mapping(_mapping(canonical.get("quant_research_v3")).get("identity")).get("completed_h1_time"),
            "mode": _mapping(canonical.get("quant_research_v3")).get("mode", "SHADOW"),
            "production_influence_enabled": bool(_mapping(canonical.get("quant_research_v3")).get("production_influence_enabled", False)),
        },
        "quant_research_v4": {
            **deepcopy(dict(_mapping(canonical.get("quant_research_v4")).get("summary") or {})),
            "source_generation_id": _mapping(_mapping(canonical.get("quant_research_v4")).get("identity")).get("source_generation_id"),
            "completed_h1_time": _mapping(_mapping(canonical.get("quant_research_v4")).get("identity")).get("latest_completed_broker_h1_time"),
            "mode": "SHADOW",
            "production_influence_enabled": bool(_mapping(canonical.get("quant_research_v4")).get("production_influence_enabled", False)),
        },
        "quant_research_v7": {
            **deepcopy(dict(_mapping(canonical.get("quant_research_v7")).get("summary") or {})),
            "source_generation_id": _mapping(_mapping(canonical.get("quant_research_v7")).get("identity")).get("source_generation_id"),
            "completed_broker_time": _mapping(_mapping(canonical.get("quant_research_v7")).get("identity")).get("completed_broker_time"),
            "mode": "SHADOW",
            "production_influence_enabled": bool(_mapping(canonical.get("quant_research_v7")).get("production_influence_enabled", False)),
        },
        "validation": {
            "data_freshness": _text(_first(data_quality.get("freshness"), data_quality.get("status")), "UNKNOWN"),
            "stale_status": "STALE" if stale else "CURRENT",
            "layer_status": _text(layer_status),
            "validation_status": _text(validation_status),
            "data_quality_status": _text(data_quality.get("status"), "UNKNOWN"),
            "data_quality_score": _num(data_quality.get("score"), 0.0),
        },
    }
    return summary


def _safe_json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except Exception:
        return 0


def build_ai_fact_pack(
    summary: Mapping[str, Any],
    *,
    canonical: Mapping[str, Any] | None = None,
    evidence_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    canonical = _mapping(canonical)
    evidence = [dict(row) for row in list(evidence_rows or [])[:MAX_EVIDENCE_ROWS] if isinstance(row, Mapping)]
    identity = _mapping(summary.get("identity"))
    pack = {
        "schema_version": SCHEMA_VERSION,
        "calculation_id": summary.get("calculation_id"),
        "timestamp": identity.get("calculation_timestamp"),
        "last_completed_h1_timestamp": identity.get("latest_completed_candle_time"),
        "symbol": identity.get("symbol", "EURUSD"),
        "timeframe": identity.get("timeframe", "H1"),
        "current_close": _mapping(summary.get("projection")).get("current_close"),
        "current_decision": _mapping(summary.get("decision")).get("current_decision"),
        "quant_research_v3": deepcopy(dict(_mapping(summary.get("quant_research_v3")))),
        "quant_research_v4": deepcopy(dict(_mapping(summary.get("quant_research_v4")))),
        "quant_research_v7": deepcopy(dict(_mapping(summary.get("quant_research_v7")))),
        "direction": _mapping(summary.get("decision")).get("direction"),
        "less_risky_bias": _mapping(summary.get("decision")).get("less_risky_bias"),
        "tradeability": _mapping(summary.get("decision")).get("tradeability"),
        "protected_scores": deepcopy(dict(_mapping(summary.get("scores")))),
        "directional_regime": _mapping(summary.get("regime")).get("directional_regime"),
        "volatility_regime": _mapping(summary.get("regime")).get("volatility_regime"),
        "reliability": _mapping(summary.get("regime")).get("regime_reliability"),
        "priority": deepcopy(dict(_mapping(summary.get("priority")))),
        "central_projection": deepcopy(dict(_mapping(summary.get("projection")))),
        "quantiles": {
            "lower": _mapping(summary.get("projection")).get("lower_band"),
            "central": _mapping(summary.get("projection")).get("h6"),
            "upper": _mapping(summary.get("projection")).get("upper_band"),
        },
        "uncertainty": deepcopy(dict(_mapping(summary.get("uncertainty")))),
        "transition_risk": _mapping(summary.get("regime")).get("transition_risk"),
        "transition_window": _mapping(summary.get("regime")).get("estimated_transition_window"),
        "research_risk": deepcopy(dict(_mapping(summary.get("research_risk")))),
        "nlp_summary": deepcopy(dict(_mapping(summary.get("nlp")))),
        "similar_day_summary": deepcopy(dict(_mapping(summary.get("similar_day")))),
        "quant_research_v3": deepcopy(dict(_mapping(canonical.get("quant_research_v3")).get("summary") or {})),
        "quant_research_v3_identity": deepcopy(dict(_mapping(canonical.get("quant_research_v3")).get("identity") or {})),
        "quant_research_v3_limitations": list(_mapping(canonical.get("quant_research_v3")).get("limitations") or [])[:8],
        "quant_research_v7_evidence": deepcopy(dict(_mapping(canonical.get("quant_research_v7_ai_evidence")))),
        "quant_research_v7_identity": deepcopy(dict(_mapping(canonical.get("quant_research_v7")).get("identity") or {})),
        "quant_research_v7_limitations": list(_mapping(canonical.get("quant_research_v7")).get("limitations") or [])[:8],
        "top_two_opportunities": deepcopy(list(_mapping(summary.get("priority")).get("top_two") or [])[:2]),
        "latest_relevant_evidence_rows": evidence,
        "validation_status": deepcopy(dict(_mapping(summary.get("validation")))),
        "blocking_reasons": list(_mapping(summary.get("decision")).get("blocking_reasons") or [])[:12],
        "main_reason": _mapping(summary.get("decision")).get("main_reason"),
        "fact_pack_source": "published canonical generation only",
    }
    # Defensive cap: evidence is the only potentially large element.
    while _safe_json_size(pack) > 100_000 and len(pack["latest_relevant_evidence_rows"]) > 5:
        pack["latest_relevant_evidence_rows"] = pack["latest_relevant_evidence_rows"][: max(5, len(pack["latest_relevant_evidence_rows"]) // 2)]
    pack["size_bytes"] = _safe_json_size(pack)
    return pack


def publish_compact_runtime(
    state: MutableMapping[str, Any],
    canonical: Mapping[str, Any],
    shared: Mapping[str, Any] | None = None,
    *,
    evidence_rows: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = build_compact_summary(canonical, shared)
    fact_pack = build_ai_fact_pack(summary, canonical=canonical, evidence_rows=evidence_rows)
    calc_id = str(summary.get("calculation_id") or calculation_id(canonical))
    cache = state.get(BOUNDED_CACHE_KEY)
    if not isinstance(cache, OrderedDict):
        cache = OrderedDict(cache.items()) if isinstance(cache, dict) else OrderedDict()
    cache[calc_id] = {"summary": summary, "fact_pack": fact_pack}
    cache.move_to_end(calc_id)
    while len(cache) > MAX_GENERATIONS:
        cache.popitem(last=False)
    state[BOUNDED_CACHE_KEY] = cache
    state[ACTIVE_CALCULATION_ID_KEY] = calc_id
    state[SUMMARY_KEY] = summary
    state[FACT_PACK_KEY] = fact_pack
    return summary, fact_pack


def get_compact_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    value = state.get(SUMMARY_KEY)
    return value if isinstance(value, dict) else {}


def get_ai_fact_pack(state: Mapping[str, Any]) -> dict[str, Any]:
    value = state.get(FACT_PACK_KEY)
    return value if isinstance(value, dict) else {}


def compact_ai_context(fact_pack: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt a fact pack to the existing local AI engine without full scans."""
    scores = _mapping(fact_pack.get("protected_scores"))
    projection = _mapping(fact_pack.get("central_projection"))
    current = {
        "symbol": fact_pack.get("symbol", "EURUSD"),
        "timeframe": fact_pack.get("timeframe", "H1"),
        "decision": fact_pack.get("current_decision", "DATA NOT READY"),
        "direction": fact_pack.get("direction", "WAIT"),
        "regime_direction": fact_pack.get("direction", "WAIT"),
        "tradeability_decision": fact_pack.get("tradeability", "WAIT"),
        "less_risky_decision": fact_pack.get("less_risky_bias", "WAIT"),
        "regime": fact_pack.get("directional_regime", "UNKNOWN"),
        "volatility_regime": fact_pack.get("volatility_regime", "UNKNOWN"),
        "selected_horizon": projection.get("selected_horizon", 3),
        "entry_score": scores.get("entry"),
        "master_score": scores.get("master"),
        "hold_score": scores.get("hold"),
        "tp_score": scores.get("tp"),
        "exit_risk": scores.get("exit_risk"),
        "trend_capacity_remaining": scores.get("trend_capacity_remaining"),
        "forecast_confidence": projection.get("projection_confidence"),
        "prediction_reliability": fact_pack.get("reliability"),
        "uncertainty": _mapping(fact_pack.get("uncertainty")).get("combined"),
        "last_close": fact_pack.get("current_close"),
        "forecast_close": projection.get("h6"),
        "estimated_price_close": projection.get("h6"),
        "upper_band": projection.get("upper_band"),
        "lower_band": projection.get("lower_band"),
        "blocking_reasons": list(fact_pack.get("blocking_reasons") or []),
        "best_opportunity_rows": list(fact_pack.get("top_two_opportunities") or []),
        "last_time": fact_pack.get("last_completed_h1_timestamp"),
        "calculation_id": fact_pack.get("calculation_id"),
        "quant_research_v3": deepcopy(dict(_mapping(fact_pack.get("quant_research_v3")))),
        "quant_research_v3_identity": deepcopy(dict(_mapping(fact_pack.get("quant_research_v3_identity")))),
        "quant_research_v3_limitations": list(fact_pack.get("quant_research_v3_limitations") or []),
        "quant_research_v7_evidence": deepcopy(dict(_mapping(fact_pack.get("quant_research_v7_evidence")))),
        "quant_research_v7_identity": deepcopy(dict(_mapping(fact_pack.get("quant_research_v7_identity")))),
        "quant_research_v7_limitations": list(fact_pack.get("quant_research_v7_limitations") or []),
    }
    evidence = list(fact_pack.get("latest_relevant_evidence_rows") or [])
    if pd is not None:
        evidence_df = pd.DataFrame.from_records(evidence) if evidence else pd.DataFrame()
        projection_rows = []
        for horizon in (1, 3, 6):
            projection_rows.append({"horizon": f"{horizon}h", "point_forecast": projection.get(f"h{horizon}")})
        predicted_df = pd.DataFrame(projection_rows)
    else:  # pragma: no cover
        evidence_df = evidence
        predicted_df = []
    missing = [key for key in ("entry_score", "tp_score", "exit_risk", "last_close", "forecast_confidence") if current.get(key) in (None, "", "-")]
    return {
        "data_available": bool(fact_pack.get("calculation_id")),
        "current": current,
        "flat": {},
        "ohlc_df": pd.DataFrame() if pd is not None else [],
        "predicted_df": predicted_df,
        "history_df": evidence_df,
        "regime_history_df": pd.DataFrame() if pd is not None else [],
        "overlap_history_df": evidence_df,
        "prediction_history_df": pd.DataFrame() if pd is not None else [],
        "missing_fields": missing,
        "missing_message": "Compact canonical fact pack is ready." if not missing else "Some optional compact fields are unavailable.",
        "ai_fact_pack": dict(fact_pack),
        "read_only_canonical": True,
    }


__all__ = [
    "SUMMARY_KEY", "FACT_PACK_KEY", "BOUNDED_CACHE_KEY", "ACTIVE_CALCULATION_ID_KEY",
    "build_compact_summary", "build_ai_fact_pack", "publish_compact_runtime",
    "get_compact_summary", "get_ai_fact_pack", "compact_ai_context", "calculation_id",
]
