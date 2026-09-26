"""Pure canonical grounding helpers for the Dinner AI Assistant."""
from __future__ import annotations

from typing import Any, Mapping

from core.canonical_runtime_20260617 import component_freshness_guard


def build_ai_grounding(canonical: Mapping[str, Any], ai_component: Mapping[str, Any] | None = None) -> dict[str, Any]:
    canonical = dict(canonical or {})
    component = dict(ai_component or {})
    guard = component_freshness_guard(component, canonical) if component else {
        "ok": False, "status": "GROUNDING UNAVAILABLE", "safe_action": "WAIT", "reasons": ["missing AI grounding"]
    }
    final = dict(canonical.get("final_decision") or {})
    regime = dict(canonical.get("regime") or {})
    reliability = dict(canonical.get("reliability") or {})
    nlp = dict(canonical.get("nlp") or {})
    forecasts = dict(canonical.get("forecasts") or {})
    selected = int(final.get("selected_horizon") or forecasts.get("selected_horizon") or 3)
    projection = dict((forecasts.get("horizons") or {}).get(f"{selected}h") or {})
    opportunities = list(canonical.get("top_two_daily_candidates") or canonical.get("opportunity_candidates") or [])
    first = opportunities[0] if opportunities else {}
    canonical_action = str(final.get("tradeability_decision") or canonical.get("tradeability_decision") or "WAIT").upper()
    safe_action = canonical_action if guard.get("ok") and canonical_action in {"BUY", "SELL"} else "WAIT"
    return {
        "current_canonical_decision": final.get("final_decision") or canonical.get("full_metric_decision_label") or "WAIT",
        "less_risky_decision": safe_action,
        "current_regime": regime.get("major_regime") or canonical.get("current_regime") or "UNKNOWN",
        "entry_permission": first.get("Qualification Status") or ("QUALIFIED ENTRY" if safe_action in {"BUY", "SELL"} else "NO ENTRY / WAIT"),
        "opportunity_rank": first.get("Opportunity") or first.get("Priority Rank") or "N/A",
        "tp_sl_context": {
            "tp_quality": canonical.get("tp_quality"),
            "exit_risk": canonical.get("exit_risk"),
            "point": projection.get("point_forecast"),
            "lower": projection.get("lower_bound"),
            "upper": projection.get("upper_bound"),
        },
        "main_supporting_reasons": list(final.get("supporting_reasons") or final.get("reasons") or []),
        "main_conflicts": list(final.get("blocking_reasons") or []) + ([str(nlp.get("conflict_level"))] if nlp.get("conflict_level") not in (None, "", "NONE") else []),
        "data_freshness": {
            "status": guard.get("status"),
            "latest_completed_h1": canonical.get("latest_completed_candle_time"),
            "run_id": canonical.get("run_id"),
            "generation": canonical.get("calculation_generation"),
        },
        "uncertainty_reliability": {
            "uncertainty_pct": final.get("uncertainty_pct"),
            "error_estimate_pct": final.get("error_estimate_pct"),
            "reliability_pct": reliability.get("score"),
        },
        "directional_market_view": final.get("directional_market_view") or canonical.get("full_metric_direction") or "WAIT",
        "alpha": regime.get("alpha"),
        "delta": regime.get("delta"),
        "nlp": nlp,
        "research": canonical.get("research_confirmation_result") or canonical.get("research_confirmation") or {},
        "opportunities": opportunities,
        "freshness_guard": guard,
    }


def format_grounded_answer(grounding: Mapping[str, Any], local_answer: str = "", question: str = "") -> str:
    """Ground a local answer without making every question look identical.

    Calls without ``question`` retain the full ten-field audit format used by
    exports/tests. Interactive chat calls pass the question and receive the
    local, intent-specific answer first plus only relevant canonical evidence.
    """
    g = dict(grounding or {})
    tp = dict(g.get("tp_sl_context") or {})
    freshness = dict(g.get("data_freshness") or {})
    uncertainty = dict(g.get("uncertainty_reliability") or {})
    support = g.get("main_supporting_reasons") or ["No additional supporting reason is available"]
    conflicts = g.get("main_conflicts") or ["No critical conflict recorded"]
    full_lines = [
        f"1. Current canonical decision: **{g.get('current_canonical_decision', 'WAIT')}** ({g.get('directional_market_view', 'WAIT')})",
        f"2. Less-risky decision: **{g.get('less_risky_decision', 'WAIT')}**",
        f"3. Current regime: **{g.get('current_regime', 'UNKNOWN')}** • Alpha {g.get('alpha')} • Delta {g.get('delta')}",
        f"4. Entry permission: **{g.get('entry_permission', 'NO ENTRY / WAIT')}**",
        f"5. Opportunity rank: **{g.get('opportunity_rank', 'N/A')}**",
        f"6. TP/SL context: TP quality {tp.get('tp_quality')} • Exit risk {tp.get('exit_risk')} • Forecast {tp.get('point')} [{tp.get('lower')}, {tp.get('upper')}]",
        "7. Main supporting reasons: " + "; ".join(map(str, support[:5])),
        "8. Main conflicts: " + "; ".join(map(str, conflicts[:5])),
        f"9. Data freshness: **{freshness.get('status', 'UNKNOWN')}** • H1 {freshness.get('latest_completed_h1')} • Generation {freshness.get('generation')}",
        f"10. Uncertainty and reliability: uncertainty {uncertainty.get('uncertainty_pct')}% • error {uncertainty.get('error_estimate_pct')}% • reliability {uncertainty.get('reliability_pct')}%",
    ]
    q = str(question or "").lower().strip()
    if not q:
        if local_answer:
            full_lines.extend(["", "Local explanation:", local_answer])
        return "\n\n".join(full_lines)

    relevant = []
    if any(token in q for token in ("tp", "take profit", "target", "sl", "stop", "price", "1 hour", "1h", "6 hour", "6h")):
        relevant.append(f"Canonical TP/SL evidence: forecast {tp.get('point')} within [{tp.get('lower')}, {tp.get('upper')}], TP quality {tp.get('tp_quality')}, exit risk {tp.get('exit_risk')}.")
    if any(token in q for token in ("regime", "alpha", "delta", "trend", "reversal")):
        relevant.append(f"Regime evidence: {g.get('current_regime', 'UNKNOWN')} • alpha {g.get('alpha')} • delta {g.get('delta')}.")
    if any(token in q for token in ("enter", "entry", "buy", "sell", "trade", "wait", "decision", "bias", "safe")):
        relevant.append(f"Decision evidence: canonical {g.get('current_canonical_decision', 'WAIT')} • less-risky {g.get('less_risky_decision', 'WAIT')} • permission {g.get('entry_permission', 'NO ENTRY / WAIT')}.")
    if any(token in q for token in ("reliab", "confidence", "uncertain", "error", "accur")):
        relevant.append(f"Reliability evidence: {uncertainty.get('reliability_pct')}% reliability, {uncertainty.get('uncertainty_pct')}% uncertainty, {uncertainty.get('error_estimate_pct')}% error estimate.")
    if any(token in q for token in ("why", "reason", "conflict", "risk")):
        relevant.append("Main support: " + "; ".join(map(str, support[:3])))
        relevant.append("Main conflicts: " + "; ".join(map(str, conflicts[:3])))
    if not relevant:
        relevant.append(f"Canonical context: {g.get('current_canonical_decision', 'WAIT')} • less-risky {g.get('less_risky_decision', 'WAIT')} • regime {g.get('current_regime', 'UNKNOWN')}.")
    relevant.append(f"Freshness: {freshness.get('status', 'UNKNOWN')} • H1 {freshness.get('latest_completed_h1')} • generation {freshness.get('generation')}.")
    answer = str(local_answer or "No intent-specific local answer was produced.").strip()
    return answer + "\n\n" + "\n\n".join(relevant[:5])


__all__ = ["build_ai_grounding", "format_grounded_answer"]
