"""Generation-bound, route-selective local grounded-answer pipeline."""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping, MutableMapping

from core.ai_intent_router import detect_intent
from core.ai_resource_budget import select_budget
from core.ai_conversation_memory import remember
from core.generation_order_guard_20260622 import active_generation_matches
from core.ai_domain_analysis_registry_20260622 import execute_domain_analysis
from core.ai_source_registry import load_settled_evidence  # backward-compatible patch point; domain routes perform selective retrieval


def _m(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _canonical_from_state(state: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        if isinstance(value, Mapping):
            return dict(value)
    except Exception:
        pass
    return {}


def _present(value: Any) -> bool:
    return value not in (None, "", [], {}, "UNAVAILABLE", "Not published", "not published")


def _fact_evidence(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    identity = _m(analysis.get("identity"))
    rows: list[dict[str, Any]] = []
    for metric, value in _m(analysis.get("facts")).items():
        if not _present(value):
            continue
        rows.append({
            "evidence_id": sha256(f"{analysis.get('domain')}|{metric}|{value}".encode("utf-8", "ignore")).hexdigest()[:16],
            "source_name": str(analysis.get("domain")),
            "field": str(analysis.get("domain")),
            "metric_name": str(metric),
            "metric_value": value,
            "short_explanation": "Read-only fact from the selected generation-bound domain route.",
            "generation_id": identity.get("calculation_id"),
            "completed_candle": identity.get("latest_completed_h1_utc"),
            "reliability": _m(analysis.get("facts")).get("reliability") or _m(analysis.get("facts")).get("regime_reliability"),
            "freshness": analysis.get("synchronization_status"),
            "evidence_status": "SETTLED",
        })
    for raw in list(analysis.get("history_rows") or [])[:24]:
        value = raw.get("value_text") if _present(raw.get("value_text")) else raw.get("value_numeric")
        rows.append({
            "evidence_id": str(raw.get("record_key") or sha256(str(raw).encode()).hexdigest()[:16]),
            "source_name": str(raw.get("table_name") or "history"),
            "field": str(analysis.get("domain")),
            "metric_name": str(raw.get("metric_name") or raw.get("condition") or "history_evidence"),
            "metric_value": value,
            "short_explanation": "Bounded row from the relevant history table.",
            "generation_id": raw.get("calculation_id"),
            "completed_candle": raw.get("latest_completed_h1"),
            "reliability": None,
            "freshness": analysis.get("synchronization_status"),
            "evidence_status": raw.get("settled_status") or "SETTLED",
        })
    return rows


def _status(analysis: Mapping[str, Any], evidence: list[Mapping[str, Any]]) -> tuple[str, float, float]:
    facts = _m(analysis.get("facts"))
    meaningful = sum(1 for value in facts.values() if _present(value))
    completeness = meaningful / max(1, len(facts))
    history_bonus = min(0.15, len(analysis.get("history_rows") or []) / 100.0)
    completeness = min(1.0, completeness + history_bonus)
    sync = str(analysis.get("synchronization_status") or "UNAVAILABLE").upper()
    quality = str(analysis.get("data_quality_status") or "UNAVAILABLE").upper()
    missing = list(analysis.get("missing_sources") or [])
    confidence = max(0.0, min(95.0, 25.0 + completeness * 65.0 - min(25.0, len(missing) * 2.5)))
    if sync in {"OUT OF SYNC", "OUT_OF_SYNC", "UNAVAILABLE"} or quality in {"FAIL", "REJECT", "SEVERE"}:
        return "ABSTAIN", round(min(confidence, 35.0), 1), round(completeness, 3)
    if completeness < 0.25 or not evidence:
        return "ABSTAIN", round(min(confidence, 30.0), 1), round(completeness, 3)
    if missing or sync == "STALE" or quality in {"WARN", "UNAVAILABLE"}:
        return "PARTIAL ANSWER", round(min(confidence, 74.0), 1), round(completeness, 3)
    return "ANSWER", round(confidence, 1), round(completeness, 3)


def _answer_text(question: str, intent: str, analysis: Mapping[str, Any], response_status: str, confidence: float, completeness: float) -> str:
    identity = _m(analysis.get("identity")); facts = _m(analysis.get("facts"))
    direct = []
    for key, value in facts.items():
        if _present(value):
            direct.append(f"- **{str(key).replace('_', ' ').title()}:** {value}")
        if len(direct) >= 12:
            break
    if str(analysis.get("domain")) == "directional_bias" and response_status != "ABSTAIN":
        bias = facts.get("less_risky_bias") or facts.get("directional_bias") or facts.get("current_decision") or "UNAVAILABLE"
        conflict = facts.get("conflict_status") or "UNAVAILABLE"
        lead = f"The current less-risky directional bias is {bias}. Conflict status is {conflict}; the detailed evidence is listed below."
    elif response_status == "ABSTAIN":
        lead = "I am abstaining from trading guidance because the selected evidence does not pass the timestamp, generation, data-quality, or completeness gate."
    elif response_status == "PARTIAL ANSWER":
        lead = "The synchronized evidence supports only a partial answer; unavailable components are listed below."
    else:
        lead = "The current synchronized generation provides sufficient evidence for this answer."
    current_decision = facts.get("current_decision") or facts.get("decision") or "Not relevant/not published"
    direction = facts.get("direction") or "Not relevant/not published"
    regime = facts.get("current_major_regime") or facts.get("regime") or "Not relevant/not published"
    reliability = facts.get("reliability") or facts.get("regime_reliability") or "Not published"
    priority = facts.get("priority") or facts.get("priority_label") or "Not relevant/not published"
    missing = list(analysis.get("missing_sources") or [])
    lines = [
        f"### {response_status}",
        f"**Direct answer:** {lead}",
        f"**Question:** {question.strip()}",
        "",
        *direct,
        "",
        "---",
        f"**Current decision:** {current_decision}",
        f"**Direction:** {direction}",
        f"**Broker timestamp used:** {identity.get('broker_time') or 'UNAVAILABLE'}",
        f"**Completed-H1 watermark:** {identity.get('latest_completed_h1_utc') or 'UNAVAILABLE'}",
        f"**Current regime:** {regime}",
        f"**Reliability:** {reliability}",
        f"**Priority:** {priority}",
        f"**Evidence modules used:** {', '.join(analysis.get('evidence_modules') or []) or 'None'}",
        f"**Calculation ID:** {identity.get('calculation_id') or 'UNAVAILABLE'}",
        f"**Generation ID:** {identity.get('calculation_id') or 'UNAVAILABLE'}",
        f"**Generation:** {identity.get('generation')}",
        f"**Evidence coverage status:** {response_status} ({completeness:.1%} complete)",
        f"**Synchronization status:** {analysis.get('synchronization_status')}",
        f"**Data-quality status:** {analysis.get('data_quality_status')}",
        f"**Reasoning summary:** Intent `{intent}` executed only the `{analysis.get('domain')}` read-only route for this generation.",
        f"**Missing evidence warning:** {', '.join(missing) if missing else 'None'}",
        f"**Evidence completeness:** {completeness:.1%}",
        f"**Answer confidence:** {confidence:.1f}% (evidence support, not probability of profit)",
        f"**Response status:** {response_status}",
    ]
    if response_status == "ABSTAIN":
        lines.append("**Safety gate:** ABSTAIN is not converted into BUY, SELL, TP, SL, or price guidance.")
    return "\n".join(lines)


def answer_question(question: str, *, canonical: Mapping[str, Any], summary: Mapping[str, Any], plan: Mapping[str, Any] | None, state: MutableMapping[str, Any]) -> dict[str, Any]:
    intent_info = detect_intent(question)
    intent = str(intent_info["intent"])
    budget = select_budget(question, intent)
    initial = dict(canonical or _canonical_from_state(state))
    analysis = execute_domain_analysis(intent, question=question, canonical=initial, summary=summary, plan=plan, state=state)

    # If a newer generation appeared during the route, discard and rebuild once.
    active = _canonical_from_state(state) or initial
    stale_rebuilt = False
    if not active_generation_matches(initial, active):
        stale_rebuilt = True
        analysis = execute_domain_analysis(intent, question=question, canonical=active, summary=summary, plan=plan, state=state)
        latest = _canonical_from_state(state) or active
        if not active_generation_matches(active, latest):
            analysis = dict(analysis)
            analysis["synchronization_status"] = "OUT OF SYNC"
            analysis.setdefault("missing_sources", []).append("generation changed twice during answer construction")
            active = latest

    evidence = _fact_evidence(analysis)
    response_status, confidence, completeness = _status(analysis, evidence)
    # Plan A remains primary. Plan B is question-triggered and runs only after
    # submission when grounded retrieval cannot support a useful answer.
    synchronization_conflict = str(analysis.get("synchronization_status") or "").upper() in {"OUT OF SYNC", "GENERATION CONFLICT", "STALE"}
    if (response_status == "ABSTAIN" or completeness < 0.35) and not synchronization_conflict:
        try:
            from core.ai_plan_b_20260622 import answer_plan_b
            fallback = answer_plan_b(question, canonical=active, state=state)
            fallback.setdefault("response_status", "PARTIAL ANSWER" if fallback.get("route_label") != "OFFLINE DIAGNOSTIC" else "ABSTAIN")
            fallback.setdefault("status", "PARTIALLY_SUPPORTED" if fallback.get("route_label") != "OFFLINE DIAGNOSTIC" else "INSUFFICIENT_EVIDENCE")
            fallback.setdefault("intent", intent)
            fallback.setdefault("generation_id", str((_m(analysis.get("identity"))).get("calculation_id") or ""))
            fallback.setdefault("analysis", analysis)
            fallback.setdefault("evidence_completeness", completeness)
            fallback.setdefault("answer_confidence", fallback.get("confidence", confidence))
            fallback.setdefault("memory_recorded", False)
            return fallback
        except Exception:
            pass
    answer = "PLAN A GROUNDED\n" + _answer_text(question, intent, analysis, response_status, confidence, completeness)
    if len(answer) > budget.max_answer_chars:
        answer = answer[: budget.max_answer_chars - 100].rsplit("\n", 1)[0] + "\n[Answer compressed to the local route budget]"

    from core.ai_duplicate_guard_20260622 import prevent_duplicate_answer
    duplicate_guard = prevent_duplicate_answer(state, question=question, answer=answer, intent=intent, evidence=evidence)
    answer = str(duplicate_guard.get("answer") or answer)
    identity = _m(analysis.get("identity"))
    generation_id = str(identity.get("calculation_id") or "")
    remember(state, question=question, intent=intent, generation_id=generation_id, evidence=evidence, status=response_status, answer=answer)

    answer_hash = sha256(answer.encode("utf-8", "ignore")).hexdigest()
    try:
        from core.field6_quant_history_20260622 import record_ai_audit
        audit_storage = record_ai_audit(
            state, analysis=analysis, question=question, response_status=response_status,
            answer_confidence=confidence, evidence_completeness=completeness, answer_hash=answer_hash,
        )
    except Exception as exc:
        audit_storage = {"storage_status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}

    legacy_status = {
        "ANSWER": "SUPPORTED",
        "PARTIAL ANSWER": "PARTIALLY_SUPPORTED",
        "ABSTAIN": "STALE_GENERATION" if stale_rebuilt else "INSUFFICIENT_EVIDENCE",
    }.get(response_status, "INSUFFICIENT_EVIDENCE")
    return {
        "answer": answer,
        "route_label": "PLAN A GROUNDED",
        "status": legacy_status,
        "response_status": response_status,
        "intent": intent,
        "domain": analysis.get("domain"),
        "generation_id": generation_id,
        "calculation_id": identity.get("calculation_id"),
        "generation": identity.get("generation"),
        "completed_candle": identity.get("latest_completed_h1_utc"),
        "broker_time": identity.get("broker_time"),
        "evidence": evidence,
        "analysis": analysis,
        "answer_confidence": confidence,
        "evidence_completeness": completeness,
        "synchronization_status": analysis.get("synchronization_status"),
        "data_quality_status": analysis.get("data_quality_status"),
        "duplicate_guard": duplicate_guard,
        "audit_storage": audit_storage,
        "stale_generation_rebuilt": stale_rebuilt,
        "memory_recorded": True,
        "stages": [
            "narrow_intent_detection", "generation_resolution", "domain_builder_execution",
            "relevant_history_retrieval", "timestamp_generation_validation", "risk_coverage_gate",
            "structured_answer", "bounded_audit_persistence",
        ],
    }


__all__ = ["answer_question", "load_settled_evidence"]
