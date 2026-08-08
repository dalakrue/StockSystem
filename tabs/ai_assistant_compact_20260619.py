"""Compact, submit-driven grounded AI Assistant UI.

Opening the field reads only the compact published fact pack. Evidence retrieval
and local analysis execute only after Send / Analyze is pressed.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import OrderedDict
from typing import Any, Mapping

import pandas as pd

from core.generation_identity_20260707 import numeric_generation
import streamlit as st

from core.compact_canonical_20260619 import get_ai_fact_pack
from core.performance_store_20260619 import append_ai_message, load_ai_messages

# Compatibility marker only: ``from tabs import ai_assistant_lite as legacy``.
# The legacy assistant is intentionally not imported; Field 5 uses the bounded
# grounded pipeline only after Send / Analyze.

CACHE_KEY = "ai_answer_cache_20260619"
LATEST_KEY = "ai_latest_messages_20260619"
LATEST_CALC_KEY = "ai_latest_messages_calculation_id_20260622"
LATEST_GENERATION_KEY = "ai_latest_messages_generation_20260622"
MAX_CACHE = 32
AI_ANSWER_VERSION = "20260622-question-focused-v2"

ANSWER_PANEL_KEY = "ai_answer_panel_20260624"
ANSWER_SUMMARY_KEY = "ai_answer_summary_20260624"
ANSWER_META_KEY = "ai_answer_meta_20260624"

_DOMAIN_TERMS = {
    "eurusd", "eur/usd", "h1", "price", "forecast", "projection", "decision", "buy", "sell", "wait",
    "entry", "exit", "hold", "tp", "sl", "risk", "lot", "regime", "alpha", "delta", "confidence",
    "reliability", "uncertainty", "history", "field", "session", "london", "new york", "ny", "broker",
    "candle", "technical", "sentiment", "news", "priority", "accuracy", "model", "system", "database",
    "connector", "calculation", "prediction", "path", "similar", "evidence", "metric", "trade",
    "arert", "research", "thesis", "module", "calibration", "conformal", "changepoint", "analogue",
    "behavioral", "herding", "anchoring", "entropy", "drift", "meta-label", "abstention"
}

def _is_domain_related(question: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9+/_-]+", _normalize(question)))
    return bool(tokens & _DOMAIN_TERMS)

def _answer_summary(answer: str, *, max_items: int = 5) -> str:
    """Create a compact deterministic summary without inventing new facts."""
    text = re.sub(r"`{1,3}", "", str(answer or ""))
    candidates = []
    for raw in text.splitlines():
        line = re.sub(r"^\s*(?:#{1,6}|[-*•]|\d+[.)])\s*", "", raw).strip()
        if not line or len(line) < 8:
            continue
        if line.lower().startswith(("evidence used", "status:", "generation:")):
            continue
        if line not in candidates:
            candidates.append(line)
        if len(candidates) >= max_items:
            break
    if not candidates:
        candidates = [re.sub(r"\s+", " ", text).strip()[:500] or "No grounded answer was produced."]
    return "\n".join(f"- {item[:240]}" for item in candidates)

def _render_persistent_answer_panel() -> None:
    answer = str(st.session_state.get(ANSWER_PANEL_KEY) or "")
    summary = str(st.session_state.get(ANSWER_SUMMARY_KEY) or "")
    meta = st.session_state.get(ANSWER_META_KEY)
    st.markdown("#### Answer")
    if not answer:
        st.info("Ask a Lunch/EURUSD H1 question. The grounded answer and summary will remain visible here.")
        return
    st.markdown("**Summary**")
    st.markdown(summary or _answer_summary(answer))
    st.markdown("**Detailed grounded answer**")
    st.markdown(answer)
    if isinstance(meta, Mapping):
        evidence = meta.get("evidence") if isinstance(meta.get("evidence"), list) else []
        cols = st.columns(3)
        cols[0].metric("Status", str(meta.get("status") or "GROUNDED"))
        cols[1].metric("Intent", str(meta.get("intent") or "related question"))
        cols[2].metric("Evidence items", str(len(evidence)))
        with st.expander("Answer evidence", expanded=False):
            if evidence:
                st.json(evidence)
            else:
                st.caption("The answer used the canonical fact pack; no separate evidence rows were returned.")


def _normalize(question: str) -> str:
    return re.sub(r"\s+", " ", str(question or "").strip().lower())


def answer_cache_key(
    calculation_id: str,
    question: str,
    mode: str,
    generation: Any = None,
    broker_contract: Any = None,
) -> str:
    """Generation- and clock-contract-bound deterministic answer cache key."""
    if isinstance(broker_contract, Mapping):
        broker_signature = "|".join(str(broker_contract.get(k) or "") for k in (
            "broker_offset_minutes", "broker_timezone_iana", "contract_version", "latest_completed_h1_utc"
        ))
    else:
        broker_signature = str(broker_contract or "")
    legacy_base = f"{calculation_id}|{_normalize(question)}|{mode}"
    base = f"{legacy_base}|{generation}|{broker_signature}"
    raw = f"{AI_ANSWER_VERSION}|{base}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _bounded_cache() -> OrderedDict:
    raw = st.session_state.get(CACHE_KEY)
    cache = raw if isinstance(raw, OrderedDict) else OrderedDict(raw or {}) if isinstance(raw, dict) else OrderedDict()
    while len(cache) > MAX_CACHE:
        cache.popitem(last=False)
    return cache


def _redact_sensitive_text(value: str) -> str:
    """Keep question history useful without persisting API keys or bearer tokens."""
    text = str(value or "")
    patterns = (
        r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,;]+",
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+",
        r"\bsk-[A-Za-z0-9_-]{12,}\b",
    )
    for pattern in patterns:
        text = re.sub(pattern, lambda m: (m.group(1) if m.lastindex else "") + "[REDACTED]", text)
    return text


def _recover_fact_pack(state: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    """Recover the newest valid read-only AI fact pack without calculating."""
    pack = get_ai_fact_pack(state)
    fallback_pack = dict(pack) if isinstance(pack, Mapping) and pack else {}
    try:
        from core.canonical_runtime_20260617 import get_canonical
        from core.compact_canonical_20260619 import publish_compact_runtime
        canonical = get_canonical(state)
        if canonical and fallback_pack:
            canonical_id = str(canonical.get("canonical_calculation_id") or canonical.get("run_id") or "")
            pack_id = str(fallback_pack.get("calculation_id") or "")
            canonical_time = str(canonical.get("latest_completed_candle_time") or "")
            pack_time = str(fallback_pack.get("latest_completed_h1") or "")
            if canonical_id == pack_id and (not pack_time or pack_time == canonical_time):
                return fallback_pack
        # Legacy aliases may still hold the last completed generation after an
        # optional display/publication step failed. Choose the newest *valid*
        # candidate, then restore the runtime pointer before rebuilding the pack.
        if not canonical:
            from core.canonical_runtime_20260617 import (
                CANONICAL_KEY, LAST_VALID_KEY, validate_canonical_result,
            )
            candidates: list[tuple[int, pd.Timestamp, dict[str, Any]]] = []
            for key in (
                "last_valid_canonical_decision_result_20260617",
                "canonical_decision_result_20260617",
                "canonical_decision_result",
                "canonical_result_20260617",
                "canonical_result",
            ):
                candidate = state.get(key) if isinstance(state, Mapping) else None
                if not isinstance(candidate, Mapping) or not candidate:
                    continue
                candidate_dict = dict(candidate)
                valid, _ = validate_canonical_result(candidate_dict)
                if not valid:
                    continue
                try:
                    generation = numeric_generation(candidate_dict.get("calculation_generation") or candidate_dict.get("generation_id"), default=1)
                except Exception:
                    generation = 0
                created = pd.to_datetime(candidate_dict.get("created_at"), errors="coerce", utc=True)
                created = pd.Timestamp.min.tz_localize("UTC") if pd.isna(created) else pd.Timestamp(created)
                candidates.append((generation, created, candidate_dict))
            if candidates:
                canonical = max(candidates, key=lambda item: (item[0], item[1]))[2]
                try:
                    state[CANONICAL_KEY] = canonical  # type: ignore[index]
                    state[LAST_VALID_KEY] = canonical  # type: ignore[index]
                    state["ai_canonical_runtime_recovered_20260622"] = True  # type: ignore[index]
                except Exception:
                    pass
        if isinstance(canonical, Mapping) and canonical:
            shared = state.get("shared_calculation_result_20260615") if isinstance(state, Mapping) else None
            _, rebuilt = publish_compact_runtime(state, canonical, shared if isinstance(shared, Mapping) else None)  # type: ignore[arg-type]
            if isinstance(rebuilt, dict) and rebuilt:
                return rebuilt
    except Exception:
        pass
    if fallback_pack:
        return fallback_pack
    # Disk recovery survives a connector disconnect, rejected attempted run, or
    # Streamlit state reset. It reads only the newest compact published summary.
    try:
        from core.performance_store_20260619 import load_latest_summary
        from core.compact_canonical_20260619 import SUMMARY_KEY, FACT_PACK_KEY, ACTIVE_CALCULATION_ID_KEY
        summary, persisted = load_latest_summary()
        if isinstance(persisted, dict) and persisted:
            try:
                state[SUMMARY_KEY] = summary if isinstance(summary, dict) else {}  # type: ignore[index]
                state[FACT_PACK_KEY] = persisted  # type: ignore[index]
                state[ACTIVE_CALCULATION_ID_KEY] = str(persisted.get("calculation_id") or summary.get("calculation_id") or "")  # type: ignore[index]
                state["ai_fact_pack_recovered_from_disk_20260622"] = True  # type: ignore[index]
            except Exception:
                pass
            return persisted
    except Exception:
        pass
    return {}


def _offline_fact_pack(state: Mapping[str, Any]) -> dict[str, Any]:
    """Non-trading diagnostic context so Field 5 never becomes a dead panel."""
    try:
        from core.market_time_freshness_20260622 import market_time_snapshot
        freshness = market_time_snapshot(state, query_mt5=False)  # type: ignore[arg-type]
    except Exception:
        freshness = {}
    status = state.get("settings_run_status_20260617")
    errors = list(status.get("errors") or []) if isinstance(status, Mapping) else []
    return {
        "calculation_id": "OFFLINE-DIAGNOSTIC",
        "symbol": str(state.get("symbol") or "EURUSD"),
        "timeframe": str(state.get("timeframe") or "H1"),
        "current_decision": "NO PUBLISHED GENERATION",
        "direction": "WAIT",
        "tradeability": "WAIT",
        "less_risky_bias": "WAIT",
        "directional_regime": "UNKNOWN",
        "latest_completed_h1": freshness.get("latest_loaded_time"),
        "validation_status": {"status": "OFFLINE DIAGNOSTIC"},
        "main_reason": errors[-1] if errors else "No completed canonical generation is currently available.",
        "blocking_reasons": errors[-5:],
        "fact_pack_source": "offline diagnostic only; no trading values fabricated",
        "offline_diagnostic": True,
        "freshness": freshness,
    }


def _offline_answer(question: str, pack: Mapping[str, Any]) -> dict[str, Any]:
    fresh = pack.get("freshness") if isinstance(pack.get("freshness"), Mapping) else {}
    blockers = list(pack.get("blocking_reasons") or [])
    answer = (
        "### Offline diagnostic mode\n"
        f"- Your question: {question.strip()}\n"
        f"- Connector/source: {fresh.get('source', 'DISCONNECTED')}\n"
        f"- Latest loaded candle: {fresh.get('latest_loaded_display', 'No loaded candle')}\n"
        f"- Feed freshness: {fresh.get('status', 'NO DATA')}\n"
        f"- Last run issue: {(blockers[-1] if blockers else pack.get('main_reason'))}\n\n"
        "The assistant is running, but it will not invent BUY/SELL, price, regime, or confidence values without a completed canonical generation. "
        "Use the single Settings → Run Calculation + Open Lunch button; after any rejected attempt, the last valid persisted generation is restored automatically when available."
    )
    return {"answer": answer, "status": "OFFLINE_DIAGNOSTIC", "generation_id": "OFFLINE-DIAGNOSTIC", "evidence": []}


def _append_ai_history(calc_id: str, question: str, answer: str, mode: str, pack: Mapping[str, Any]) -> None:
    """Persist grounded Q/A evidence outside browser state; never persist secrets."""
    try:
        from core.canonical_runtime_20260617 import get_canonical
        from core.history_identity_20260620 import canonical_history_identity
        from core.history_evidence_store_20260620 import append_history_bundle
        canonical = get_canonical(st.session_state)
        canonical = dict(canonical) if isinstance(canonical, Mapping) else {
            "canonical_calculation_id": calc_id, "run_id": calc_id, "symbol": "EURUSD",
            "timeframe": str(st.session_state.get("timeframe") or "H1"),
            "latest_completed_candle_time": pack.get("latest_completed_h1") or pack.get("latest_completed_candle"),
        }
        interaction_id = uuid.uuid4().hex
        safe_question = _redact_sensitive_text(question)
        safe_answer = _redact_sensitive_text(answer)
        current_id = str(pack.get("calculation_id") or calc_id)
        consistent = current_id == calc_id
        unsupported = "fallback" in safe_answer.lower() or not bool(pack)
        identity = canonical_history_identity(
            canonical, condition=str(mode), settled_status="OBSERVED",
            logic_version="ai-grounding-history-20260620-v1",
        )
        common = {**identity, "payload": {"interaction_id": interaction_id}}
        evidence_names = [
            name for name in ("protected_scores", "central_projection", "priority", "nlp_summary", "uncertainty")
            if pack.get(name) not in (None, {}, [])
        ]
        bundle = {
            "ai_assistant_history": [{
                **common, "metric_name": "grounded_question_answer",
                "value_text": "GROUNDED" if pack else "UNSUPPORTED",
                "payload": {
                    "interaction_id": interaction_id, "question": safe_question, "answer": safe_answer,
                    "mode": mode, "canonical_calculation_id_used": calc_id,
                    "grounding_status": "GROUNDED" if pack else "UNSUPPORTED",
                    "unsupported_evidence_warning": unsupported,
                    "answer_consistency_status": "CONSISTENT" if consistent else "STALE",
                },
            }],
            "ai_evidence_reference_history": [
                {**common, "condition": name, "metric_name": "evidence_reference",
                 "value_text": name, "payload": {"interaction_id": interaction_id, "table_or_fact_pack_key": name}}
                for name in evidence_names
            ],
            "ai_answer_consistency_history": [{
                **common, "metric_name": "answer_consistency",
                "value_numeric": 1 if consistent else 0,
                "value_text": "CONSISTENT" if consistent else "STALE",
                "payload": {
                    "interaction_id": interaction_id, "unsupported_evidence_warning": unsupported,
                    "calculation_id_at_answer": calc_id, "calculation_id_after_answer": current_id,
                },
            }],
        }
        append_history_bundle(bundle)
        from core.history_sync_engine_20260622 import verify_core_history_commit
        st.session_state["ai_history_sync_verification_20260622"] = verify_core_history_commit(
            canonical, table_names=tuple(bundle.keys())
        )
    except Exception as exc:
        st.session_state["ai_history_append_error_20260620"] = repr(exc)



def _real_related_local_answer(question: str, canonical: Mapping[str, Any], summary: Mapping[str, Any], pack: Mapping[str, Any]) -> dict[str, Any] | None:
    """Answer the detected question category instead of repeating one template.

    This remains a local grounded assistant: it selects and explains published
    values only.  It never invents missing market values or calls an external API.
    """
    from core.ai_intent_router import detect_intent

    q = _normalize(question)
    intent_info = detect_intent(question)
    intent = str(intent_info.get("intent") or "decision_explanation")
    score = int(intent_info.get("score") or 0)

    final = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
    regime = canonical.get("regime") if isinstance(canonical.get("regime"), Mapping) else {}
    forecasts = canonical.get("forecasts") if isinstance(canonical.get("forecasts"), Mapping) else {}
    horizons = forecasts.get("horizons") if isinstance(forecasts.get("horizons"), Mapping) else {}
    projection = summary.get("projection") if isinstance(summary.get("projection"), Mapping) else {}
    reliability = summary.get("reliability") if isinstance(summary.get("reliability"), Mapping) else {}
    uncertainty = summary.get("uncertainty") if isinstance(summary.get("uncertainty"), Mapping) else {}
    validation = summary.get("validation") if isinstance(summary.get("validation"), Mapping) else {}
    priority = summary.get("priority") if isinstance(summary.get("priority"), Mapping) else {}
    similar = summary.get("similar_day") if isinstance(summary.get("similar_day"), Mapping) else {}
    research_grade = pack.get("research_grade_shadow") if isinstance(pack.get("research_grade_shadow"), Mapping) else {}
    plan = st.session_state.get("position_sizing_plan_20260619") or {}
    plan = plan if isinstance(plan, Mapping) else {}

    selected_h = str(final.get("selected_horizon") or forecasts.get("selected_horizon") or projection.get("selected_horizon") or "3")
    selected = horizons.get(f"{selected_h}h") if isinstance(horizons.get(f"{selected_h}h"), Mapping) else {}
    if not selected and isinstance(horizons.get(selected_h), Mapping):
        selected = horizons.get(selected_h)

    def first(*values: Any, default: Any = "not published") -> Any:
        for value in values:
            if value not in (None, "", [], {}):
                return value
        return default

    def pct(value: Any) -> str:
        try:
            number = float(value)
            if abs(number) <= 1.0:
                number *= 100.0
            return f"{number:.1f}%"
        except Exception:
            return str(value if value not in (None, "") else "not published")

    decision = str(first(final.get("final_decision"), pack.get("current_decision"), default="WAIT")).upper()
    direction = str(first(final.get("directional_market_view"), canonical.get("full_metric_direction"), pack.get("direction"), default="WAIT")).upper()
    less_risky = str(first(final.get("less_risky_decision"), pack.get("less_risky_bias"), default="WAIT")).upper()
    current_price = first(canonical.get("current_price"), canonical.get("last_close"), projection.get("current_close"), pack.get("current_price"))
    predicted_price = first(selected.get("predicted_price"), selected.get("predicted_close"), projection.get("selected_predicted_price"), projection.get("predicted_price"))
    lower = first(selected.get("lower_bound"), projection.get("lower_bound"))
    upper = first(selected.get("upper_bound"), projection.get("upper_bound"))
    selected_tp = first(selected.get("selected_tp"), canonical.get("selected_tp"), final.get("selected_tp"))
    selected_sl = first(selected.get("selected_sl"), canonical.get("selected_sl"), final.get("selected_sl"))
    major = first(regime.get("major_regime"), regime.get("regime"), pack.get("directional_regime"), default="UNKNOWN")
    alpha = first(canonical.get("alpha"), regime.get("alpha"), pack.get("alpha"))
    delta = first(canonical.get("delta"), regime.get("delta"), pack.get("delta"))
    confidence = first(final.get("calibrated_confidence"), summary.get("calibrated_confidence"), reliability.get("score"), pack.get("calibrated_confidence"))
    conflict = first(final.get("conflict_warning"), final.get("conflict_status"), summary.get("conflict_status"), default="No material conflict published")
    latest = first(canonical.get("latest_completed_candle_time"), pack.get("latest_completed_h1"), summary.get("latest_completed_h1"))

    reasons: list[str] = []
    for src in (final, summary, pack):
        if not isinstance(src, Mapping):
            continue
        for key_name in ("main_reason", "reason", "primary_reason", "conflict_warning"):
            value = src.get(key_name)
            if value not in (None, "") and str(value) not in reasons:
                reasons.append(str(value))

    title = {
        "market_time": "Market and broker time",
        "tp_sl_guidance": "TP / SL evidence",
        "entry_guidance": "Entry decision evidence",
        "exit_guidance": "Exit decision evidence",
        "price_forecast": "Price forecast evidence",
        "risk_position_sizing": "Risk and position sizing",
        "priority_ranking": "Priority and best-hour ranking",
        "regime_explanation": "Regime explanation",
        "reliability_explanation": "Reliability and uncertainty",
        "similar_day": "Similar-day evidence",
        "historical_comparison": "Historical comparison",
        "system_health": "System health",
        "decision_explanation": "Current trading decision",
    }.get(intent, "Related EURUSD H1 answer")
    lines = [f"### {title}"]

    if intent == "market_time":
        try:
            from core.market_time_freshness_20260622 import market_time_snapshot
            clock = market_time_snapshot(st.session_state, query_mt5=False)
        except Exception:
            clock = {}
        lines.extend([
            f"- Broker clock: **{clock.get('broker_clock_display') or 'not available'}**",
            f"- Myanmar clock: **{clock.get('current_myanmar_display') or 'not available'}**",
            f"- Latest loaded candle in broker time: **{clock.get('latest_loaded_broker_display') or latest}**",
            f"- Feed freshness: **{clock.get('status') or validation.get('data_freshness') or 'UNKNOWN'}**",
            f"- Lag: **{clock.get('lag_minutes') if clock.get('lag_minutes') is not None else 'not available'} minutes**",
        ])
    elif intent == "tp_sl_guidance":
        lines.extend([
            f"- Current decision / direction: **{decision} / {direction}**",
            f"- Current price: **{current_price}**",
            f"- Selected horizon: **{selected_h}H**",
            f"- Published TP: **{selected_tp}**",
            f"- Published SL: **{selected_sl}**",
            f"- Forecast interval: **{lower} → {upper}**",
            f"- Risk note: **{first(plan.get('reason'), conflict)}**",
        ])
    elif intent == "entry_guidance":
        lines.extend([
            f"- Entry decision: **{decision}**",
            f"- Directional market view: **{direction}**",
            f"- Less-risky action: **{less_risky}**",
            f"- Priority: **{first(priority.get('label'), priority.get('priority_label'), priority.get('rank'))}**",
            f"- Regime / reliability: **{major} / {pct(first(regime.get('reliability'), confidence))}**",
            f"- Entry conflict: **{conflict}**",
        ])
    elif intent == "exit_guidance":
        lines.extend([
            f"- Current decision / direction: **{decision} / {direction}**",
            f"- Exit risk: **{first(canonical.get('exit_risk'), summary.get('exit_risk'))}**",
            f"- Hold safety: **{first(canonical.get('hold_safety'), summary.get('hold_safety'))}**",
            f"- Published TP / SL: **{selected_tp} / {selected_sl}**",
            f"- Forecast interval: **{lower} → {upper}**",
            f"- Exit conflict: **{conflict}**",
        ])
    elif intent == "price_forecast":
        lines.extend([
            f"- Current price: **{current_price}**",
            f"- Selected forecast horizon: **{selected_h}H**",
            f"- Predicted price: **{predicted_price}**",
            f"- Prediction band: **{lower} → {upper}**",
            f"- Forecast direction: **{first(selected.get('predicted_direction'), direction)}**",
            f"- Forecast confidence: **{pct(first(selected.get('confidence'), projection.get('projection_confidence'), confidence))}**",
            f"- Saved shadow model agreement H{selected_h}: **{first((research_grade.get('model_agreement') or {}).get(selected_h, {}).get('direction_agreement'))}**",
            f"- Saved probabilistic evidence: **{first((research_grade.get('scorecards') or {}).get('regime_conditioned_ensemble', {}).get(selected_h, {}).get('crps_method'))}**",
        ])
    elif intent == "risk_position_sizing":
        lines.extend([
            f"- Decision used by risk layer: **{decision}**",
            f"- Recommended lots: **{first(plan.get('recommended_lots'))}**",
            f"- Planned risk: **{first(plan.get('planned_risk_pct'))}%**",
            f"- Planned dollar loss: **{first(plan.get('planned_dollar_loss'))}**",
            f"- Estimated margin: **{first(plan.get('margin_estimate'))}**",
            f"- Risk reason: **{first(plan.get('reason'), conflict)}**",
        ])
    elif intent == "priority_ranking":
        top_two = priority.get("top_two") if isinstance(priority.get("top_two"), (list, tuple)) else []
        lines.extend([
            f"- Current priority label: **{first(priority.get('label'), priority.get('priority_label'))}**",
            f"- Priority score/rank: **{first(priority.get('score'), priority.get('priority_score'), priority.get('rank'))}**",
            f"- Best hour: **{first(priority.get('best_hour'))}**",
            f"- Safest hour: **{first(priority.get('safest_hour'))}**",
            f"- Top two opportunities: **{top_two if top_two else 'not published'}**",
            f"- Current decision: **{decision}**",
        ])
    elif intent == "regime_explanation":
        lines.extend([
            f"- Major regime: **{major}**",
            f"- Alpha: **{alpha}**",
            f"- Delta: **{delta}**",
            f"- Transition probability: **{first(regime.get('transition_probability_1h'), regime.get('transition_probability'))}**",
            f"- Regime reliability: **{pct(first(regime.get('reliability'), reliability.get('regime_reliability'), confidence))}**",
            f"- Direction under this regime: **{direction}**",
            f"- Saved duration age / expected / remaining: **{first((research_grade.get('duration_regime') or {}).get('regime_age'))} / {first((research_grade.get('duration_regime') or {}).get('expected_duration'))} / {first((research_grade.get('duration_regime') or {}).get('estimated_remaining_duration'))}**",
            f"- Saved changepoint warning: **{first((research_grade.get('duration_regime') or {}).get('changepoint_warning'))}**",
        ])
    elif intent == "reliability_explanation":
        lines.extend([
            f"- Evidence-calibrated confidence: **{pct(confidence)}**",
            f"- Uncertainty: **{pct(first(uncertainty.get('uncertainty_pct'), uncertainty.get('uncertainty')))}**",
            f"- Error estimate: **{pct(first(uncertainty.get('error_pct'), validation.get('error_pct'), validation.get('mean_absolute_error_pct')))}**",
            f"- Conflict status: **{conflict}**",
            f"- Data freshness: **{first(validation.get('data_freshness'), validation.get('stale_status'), default='UNKNOWN')}**",
            f"- Less-risky action: **{less_risky}**",
            f"- Saved promotion-eligible shadow models: **{(research_grade.get('promotion_eligibility') or {}).get('eligible_models') or 'none; shadow-only'}**",
            f"- Saved data sufficiency: **{(research_grade.get('data_quality') or {}).get('status') or 'INSUFFICIENT EVIDENCE'}**",
        ])
    elif intent == "similar_day":
        lines.extend([
            f"- Similar-day status: **{first(similar.get('status'))}**",
            f"- Best historical match: **{first(similar.get('best_match'), similar.get('matched_date'))}**",
            f"- Similarity score: **{first(similar.get('similarity_score'), similar.get('score'))}**",
            f"- Historical outcome: **{first(similar.get('outcome'), similar.get('forward_return'))}**",
            f"- Reliability: **{pct(first(similar.get('reliability'), confidence))}**",
        ])
    elif intent == "historical_comparison":
        history = canonical.get("history_summary") if isinstance(canonical.get("history_summary"), Mapping) else {}
        lines.extend([
            f"- Current decision: **{decision}**",
            f"- Current regime: **{major}**",
            f"- 25-day direction accuracy: **{pct(first(history.get('direction_accuracy_pct'), summary.get('direction_accuracy_pct')))}**",
            f"- Historical reliability: **{pct(first(history.get('reliability'), confidence))}**",
            f"- Latest completed H1: **{latest}**",
        ])
    elif intent == "system_health":
        try:
            from core.market_time_freshness_20260622 import market_time_snapshot
            clock = market_time_snapshot(st.session_state, query_mt5=False)
        except Exception:
            clock = {}
        lines.extend([
            f"- Generation ID: **{first(pack.get('calculation_id'), canonical.get('run_id'))}**",
            f"- Calculation status: **{first(canonical.get('calculation_status'), validation.get('status'), default='UNKNOWN')}**",
            f"- Feed freshness: **{first(clock.get('status'), validation.get('data_freshness'), default='UNKNOWN')}**",
            f"- Source / rows: **{clock.get('source') or canonical.get('source') or 'UNKNOWN'} / {clock.get('rows', 'not available')}**",
            f"- Latest completed H1: **{latest}**",
            f"- Validation warning: **{first(validation.get('warning'), validation.get('failure_reason'), default='None published')}**",
        ])
    else:
        lines.extend([
            f"- Current decision: **{decision}**",
            f"- Directional market view: **{direction}**",
            f"- Less-risky action: **{less_risky}**",
            f"- Current regime: **{major}**",
            f"- Confidence: **{pct(confidence)}**",
            f"- Conflict status: **{conflict}**",
        ])

    if reasons and intent in {"decision_explanation", "regime_explanation", "reliability_explanation", "tp_sl_guidance"}:
        lines.append("\n**Why:**")
        lines.extend(f"- {reason}" for reason in reasons[:4])

    if score <= 0:
        lines.append("\nThis local assistant did not detect a narrow category, so it answered from the closest published decision evidence. Ask about broker time, TP/SL, forecast, regime, reliability, priority, history, or system health for a more targeted answer.")
    try:
        from core.shared_broker_time_20260622 import shared_broker_time_provider
        timestamp_used = shared_broker_time_provider(st.session_state, canonical=canonical).get("shared_broker_time_display")
    except Exception:
        timestamp_used = latest
    relevant_sources = {
        "entry_guidance": "Entry, Reliability, Priority, Regime",
        "exit_guidance": "Exit Risk, Hold, Projection, Reliability",
        "tp_sl_guidance": "Projection, Risk, Decision",
        "price_forecast": "Forecast, Projection, Reliability",
        "regime_explanation": "Regime, Reliability, History",
        "reliability_explanation": "Reliability, Uncertainty, Validation",
        "priority_ranking": "Priority, Decision, Regime",
        "historical_comparison": "History, Decision, Regime",
        "market_time": "Shared Broker Time, Connector Freshness",
    }.get(intent, "Decision, Regime, Reliability")
    lines.extend([
        "", "---",
        f"**Confidence %:** {pct(confidence)}",
        f"**Data Sources Used:** {relevant_sources}",
        f"**Timestamp Used:** {timestamp_used}",
        f"**Current Regime:** {major}",
        f"**Current Reliability:** {pct(first(regime.get('reliability'), confidence))}",
        f"**Current Priority:** {first(priority.get('label'), priority.get('priority_label'), priority.get('rank'))}",
        f"**Reasoning Summary:** Classified as {intent.replace('_', ' ')} and restricted to the relevant published modules.",
        "\nRead-only answer from the current canonical generation; no protected calculation, external API, or heavy model was run.",
    ])
    return {
        "answer": "\n".join(lines),
        "status": f"LOCAL_FOCUSED_{intent.upper()}",
        "intent": intent,
        "generation_id": str(pack.get("calculation_id") or canonical.get("run_id") or "current"),
        "evidence": [f"intent:{intent}", "canonical", "compact_summary", "fact_pack"] + (["saved_research_grade_shadow"] if research_grade else []),
    }


def render_compact_ai_assistant() -> None:
    pack = get_ai_fact_pack(st.session_state) or _recover_fact_pack(st.session_state)
    st.caption("Reads the compact canonical fact pack. No analysis or history query runs until Send is pressed.")
    if not pack:
        # Last-resort recovery from a completed canonical generation. This does
        # not calculate; it only republishes the compact AI projection.
        pack = _recover_fact_pack(st.session_state)
    if not pack:
        pack = _offline_fact_pack(st.session_state)
        st.warning("No completed canonical generation is available, so the assistant is in safe offline diagnostic mode. The chat remains active and does not fabricate trading values.")
    elif bool(st.session_state.get("ai_fact_pack_recovered_from_disk_20260622") or st.session_state.get("ai_canonical_runtime_recovered_20260622")):
        st.success("AI Assistant restored the newest valid published generation. A failed refresh or disconnected API did not disable the assistant.")
    # Extend with the canonical generation-bound fact pack when available.
    try:
        from core.lunch_broker_sentiment_ai_history_20260622 import build_ai_fact_pack, market_time_contract, get_canonical_generation
        extended_pack = build_ai_fact_pack(st.session_state)
        if isinstance(extended_pack, Mapping) and not pack.get("offline_diagnostic"):
            pack = {**dict(pack), **dict(extended_pack)}
        contract = market_time_contract(st.session_state, get_canonical_generation(st.session_state))
        st.info(f"AI uses calculation {contract.get('calculation_id')} generation {contract.get('calculation_generation')} at {contract.get('broker_time_display')}. It is read-only and will not rerun calculation.")
        with st.expander("Evidence panel — canonical fields used", expanded=False):
            st.json({k: pack.get(k) for k in ["calculation_id", "generation", "latest_completed_h1_utc", "Broker Time", "Myanmar Time", "current decision", "less-risky decision", "direction", "data-quality status", "synchronization status"] if k in pack})
    except Exception:
        pass
    # Attach only saved Settings-owned research evidence. This read-only
    # extension never invokes a forecast, regime, calibration, or training job.
    research_payload = st.session_state.get("research_grade_shadow_20260624")
    if isinstance(research_payload, Mapping) and not pack.get("offline_diagnostic"):
        pack = {**dict(pack), "research_grade_shadow": {
            key: research_payload.get(key) for key in (
                "run_id", "origin_candle_time", "current_forecasts", "scorecards",
                "model_agreement", "duration_regime", "tft_explanations",
                "leaderboard_25d", "promotion_eligibility", "data_quality", "limitations",
            )
        }}
    field9_payload = st.session_state.get("field9_eurusd_h1_decision_impact")
    if isinstance(field9_payload, Mapping) and not pack.get("offline_diagnostic"):
        pack = {**dict(pack), "field9_eurusd_h1_decision_impact": {
            key: field9_payload.get(key) for key in (
                "identity", "current_summary", "impact_path", "counterfactual_action_matrix",
                "decision_flip", "attribution", "influence_audit", "readiness", "limitations",
                "policy_value", "counterfactual_risk", "reality_check"
            )
        }}
    calc_id = str(pack.get("calculation_id") or "OFFLINE-DIAGNOSTIC")
    generation = pack.get("generation", pack.get("calculation_generation", 0))
    broker_contract = {
        "broker_offset_minutes": pack.get("broker_offset_minutes"),
        "broker_timezone_iana": pack.get("broker_timezone_iana"),
        "contract_version": pack.get("contract_version"),
        "latest_completed_h1_utc": pack.get("latest_completed_h1_utc", pack.get("latest_completed_h1")),
    }
    phone = bool(st.session_state.get("phone_mode", False))
    messages = st.session_state.get(LATEST_KEY)
    if (not isinstance(messages, list)
            or str(st.session_state.get(LATEST_CALC_KEY) or "") != calc_id
            or str(st.session_state.get(LATEST_GENERATION_KEY) or "") != str(generation)):
        messages = [] if pack.get("offline_diagnostic") else load_ai_messages(calc_id, limit=6 if phone else 20)
        st.session_state[LATEST_KEY] = messages
        st.session_state[LATEST_CALC_KEY] = calc_id
        st.session_state[LATEST_GENERATION_KEY] = generation
    shown = messages[-6:] if phone else messages[-20:]
    for item in shown:
        role = str(item.get("role", "assistant"))
        with st.chat_message(role if role in {"user", "assistant"} else "assistant"):
            st.markdown(str(item.get("content", "")))

    _render_persistent_answer_panel()

    with st.form("compact_ai_form_20260619", clear_on_submit=True):
        mode = st.selectbox("Resource route", ["Automatic bounded route", "Simple evidence route", "Complex evidence route"], key="ai_mode_20260619")
        question = st.text_input("Ask about the synchronized EURUSD H1 result", key="ai_question_20260619")
        submitted = st.form_submit_button("Send / Analyze", use_container_width=True)
    if not submitted or not question.strip():
        return

    # Single-answer mode requested by the user: every new submitted question
    # replaces the previous visible exchange instead of duplicating answers.
    st.session_state[LATEST_KEY] = []
    st.session_state.pop(ANSWER_PANEL_KEY, None)
    st.session_state.pop(ANSWER_SUMMARY_KEY, None)
    st.session_state.pop(ANSWER_META_KEY, None)
    messages = []

    if not _is_domain_related(question):
        answer = (
            "### Related-question boundary\n"
            "This Grounded AI Assistant answers only questions about the published Lunch system, "
            "EURUSD H1, prediction paths, regimes, decisions, risk, history, data quality, sessions, "
            "research evidence, and system health. Rephrase the question so it is directly related to those areas."
        )
        st.session_state[ANSWER_PANEL_KEY] = answer
        st.session_state[ANSWER_SUMMARY_KEY] = "- The question was outside the assistant’s grounded EURUSD H1/Lunch scope.\n- No market value or unrelated answer was invented."
        st.session_state[ANSWER_META_KEY] = {"status": "OUT_OF_SCOPE", "intent": "domain_boundary", "evidence": []}
        _render_persistent_answer_panel()
        return

    key = answer_cache_key(calc_id, question, mode, generation, broker_contract)
    cache = _bounded_cache()
    cached = cache.get(key)
    from_cache = isinstance(cached, Mapping)
    if from_cache:
        result = dict(cached)
        answer = str(result.get("answer") or "")
    else:
        if pack.get("offline_diagnostic"):
            result = _offline_answer(question, pack)
        else:
            from core.canonical_runtime_20260617 import get_canonical
            from core.compact_canonical_20260619 import get_compact_summary
            from core.ai_grounded_pipeline_20260621 import answer_question
            canonical = get_canonical(st.session_state)
            summary = get_compact_summary(st.session_state)
            plan = st.session_state.get("position_sizing_plan_20260619") or {}
            # OpenRouter is optional and read-only. When configured, it receives
            # the bounded canonical + Dinner research evidence contract. Any
            # timeout, HTTP failure, or unavailable key falls back deterministically
            # to the existing local grounded pipeline.
            result = None
            openrouter_failure = None
            try:
                from services.openrouter_backend_20260628 import configuration_status, generate_grounded_answer
                openrouter_status = configuration_status(st.session_state)
                if openrouter_status.get("configured"):
                    external = generate_grounded_answer(
                        question,
                        canonical if isinstance(canonical, Mapping) else {},
                        st.session_state,
                    )
                    if external.get("ok"):
                        result = {
                            "answer": external.get("answer"),
                            "status": "OPENROUTER_GROUNDED",
                            "intent": "openrouter_grounded_research",
                            "generation_id": calc_id,
                            "evidence": [
                                {"source": "frozen canonical snapshot", "run_id": pack.get("calculation_id")},
                                {"source": "bounded Dinner ARERT research", "available": bool(st.session_state.get("arert_thesis_research_20260628"))},
                            ],
                            "openrouter_model": external.get("model"),
                            "openrouter_attempts": external.get("attempts"),
                            "memory_recorded": False,
                        }
                    else:
                        openrouter_failure = {
                            "status": external.get("status"),
                            "error": external.get("error"),
                            "attempts": external.get("attempts"),
                        }
            except Exception as exc:
                openrouter_failure = {"status": "FAILED_SAFELY", "error": f"{type(exc).__name__}: {exc}"}

            if not isinstance(result, Mapping):
                try:
                    result = answer_question(question, canonical=canonical, summary=summary, plan=plan, state=st.session_state)
                except Exception:
                    result = _real_related_local_answer(question, canonical if isinstance(canonical, Mapping) else {}, summary if isinstance(summary, Mapping) else {}, pack)
                if isinstance(result, Mapping) and openrouter_failure:
                    result = dict(result)
                    result["openrouter_fallback"] = openrouter_failure
                    result["status"] = str(result.get("status") or "LOCAL_GROUNDED") + "_AFTER_OPENROUTER_FALLBACK"
        answer = str(result.get("answer") or "")
        # Reject an answer produced for a replaced generation, except the safe
        # diagnostic context which has no mutable market generation.
        current_pack = _recover_fact_pack(st.session_state)
        current_generation = current_pack.get("generation", current_pack.get("calculation_generation", 0))
        if (not pack.get("offline_diagnostic") and (
                str(current_pack.get("calculation_id") or "") != calc_id
                or str(current_generation) != str(generation))):
            st.warning("A newer calculation replaced this request. The stale generation answer was discarded.")
            return
        cache[key] = result
        cache.move_to_end(key)
        while len(cache) > MAX_CACHE:
            cache.popitem(last=False)
        st.session_state[CACHE_KEY] = cache

    # Cached answers are checked against the last 20 pairs and restructured when
    # similarity exceeds 90%.  Fresh pipeline answers already passed this guard.
    if from_cache or not bool(result.get("memory_recorded")):
        try:
            from core.ai_duplicate_guard_20260622 import prevent_duplicate_answer
            from core.ai_conversation_memory import remember
            evidence_rows = result.get("evidence") if isinstance(result.get("evidence"), list) else []
            guarded = prevent_duplicate_answer(
                st.session_state, question=question, answer=answer,
                intent=str(result.get("intent") or "decision_explanation"), evidence=evidence_rows,
            )
            answer = str(guarded.get("answer") or answer)
            result["answer"] = answer
            result["duplicate_guard"] = guarded
            remember(
                st.session_state, question=question,
                intent=str(result.get("intent") or "decision_explanation"),
                generation_id=str(result.get("generation_id") or calc_id),
                evidence=evidence_rows, status=str(result.get("status") or mode), answer=answer,
            )
            result["memory_recorded"] = True
        except Exception:
            pass
    st.session_state[ANSWER_PANEL_KEY] = str(answer)
    st.session_state[ANSWER_SUMMARY_KEY] = _answer_summary(str(answer))
    st.session_state[ANSWER_META_KEY] = {
        "status": str(result.get("status") or mode),
        "intent": str(result.get("intent") or "decision_explanation"),
        "evidence": result.get("evidence") if isinstance(result.get("evidence"), list) else [],
        "calculation_id": calc_id,
        "generation": generation,
    }
    pair = [{"role": "user", "content": question}, {"role": "assistant", "content": str(answer)}]
    messages.extend(pair)
    st.session_state[LATEST_KEY] = messages[-20:]
    if not pack.get("offline_diagnostic"):
        for item in pair:
            append_ai_message(calc_id, item["role"], item["content"])
        _append_ai_history(calc_id, question, str(answer), str(result.get("status") or mode), pack)
    with st.chat_message("assistant"):
        st.markdown(str(answer))


__all__ = ["render_compact_ai_assistant", "answer_cache_key", "_recover_fact_pack", "MAX_CACHE", "AI_ANSWER_VERSION"]

# Additive helper consumed by the independent AI tab/router when available.
def render_current_hour_ai_priority_summary_20260624(state=None):
    import streamlit as st
    from ui.lunch_unified_quant_visuals_20260624 import render_priority_summary
    render_priority_summary(state if state is not None else st.session_state)
