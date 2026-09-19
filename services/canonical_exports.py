"""Canonical copy/export payload service.

Every visible copy location calls this module. Builders are pure and read only a
published canonical generation, compact summary and published risk plan. Copy
All is a structured eight-field summary, not a raw canonical/database dump.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

MAX_SHORT_LINES = 40
MAX_SHORT_CHARS = 6_000
TARGET_SHORT_TOKENS = 1_500


def _m(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _text(value: Any, default: str = "-") -> str:
    if not _present(value):
        return default
    if isinstance(value, float):
        if math.isfinite(value):
            return f"{value:.5f}".rstrip("0").rstrip(".")
        return default
    return str(value).strip() or default


def _num(value: Any, digits: int = 2, suffix: str = "") -> str:
    try:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError
        return f"{number:.{digits}f}{suffix}"
    except Exception:
        return "-"



def _published_num(value: Any, digits: int = 2, suffix: str = "") -> str:
    text = _num(value, digits, suffix)
    return "Not published" if text == "-" else text

def _unique_strings(values: Iterable[Any], limit: int = 3, max_len: int = 180) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value or "").split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text if len(text) <= max_len else text[: max_len - 1].rstrip() + "…")
        if len(out) >= limit:
            break
    return out


@dataclass(frozen=True)
class PayloadStats:
    characters: int
    lines: int
    estimated_tokens: int


def payload_stats(text: str) -> PayloadStats:
    raw = str(text or "")
    return PayloadStats(len(raw), len(raw.splitlines()), int(math.ceil(len(raw) / 4.0)))


def generation_identity(canonical: Mapping[str, Any]) -> str:
    return "|".join(str(canonical.get(k) or "") for k in ("run_id", "calculation_generation", "checksum", "latest_completed_candle_time"))


def _selected_forecast(canonical: Mapping[str, Any], summary: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    final = _m(canonical.get("final_decision"))
    selected = final.get("selected_horizon") or _m(summary.get("projection")).get("selected_horizon") or 6
    digits = "".join(ch for ch in str(selected) if ch.isdigit()) or "6"
    key = f"{digits}h"
    horizons = _m(_m(canonical.get("forecasts")).get("horizons"))
    raw = horizons.get(key)
    return key, _m(raw)


def _latest_ai_summary(state: Mapping[str, Any] | None, canonical: Mapping[str, Any]) -> str:
    state = state if isinstance(state, Mapping) else {}
    for key in ("ai_assistant_last_answer_20260622", "ai_assistant_last_answer", "last_ai_answer"):
        value = state.get(key)
        if isinstance(value, Mapping):
            value = value.get("answer") or value.get("text") or value.get("summary")
        if _present(value):
            return " ".join(str(value).split())[:500]
    pack = _m(canonical.get("compact_ai_fact_pack"))
    for key in ("summary", "ai_summary", "reasoning_summary"):
        if _present(pack.get(key)):
            return " ".join(str(pack.get(key)).split())[:500]
    final = _m(canonical.get("final_decision"))
    reasons = _unique_strings([final.get("main_reason"), *list(final.get("supporting_reasons") or [])], limit=2)
    return " | ".join(reasons) if reasons else "No grounded AI summary published"


def _quick_tp_sl(canonical: Mapping[str, Any], plan: Mapping[str, Any]) -> tuple[Any, Any]:
    final = _m(canonical.get("final_decision"))
    selected = _m(final.get("selected_forecast"))
    tp = _first_present(
        final.get("selected_tp"), final.get("quick_tp"), canonical.get("selected_tp"),
        plan.get("take_profit"), plan.get("tp"), selected.get("take_profit"),
    )
    sl = _first_present(
        final.get("selected_sl"), final.get("quick_sl"), canonical.get("selected_sl"),
        plan.get("stop_loss"), plan.get("sl"), selected.get("stop_loss"),
    )
    return tp, sl


def _first_present(*values: Any) -> Any:
    for value in values:
        if _present(value):
            return value
    return None


def _short_lines(canonical: Mapping[str, Any], summary: Mapping[str, Any], plan: Mapping[str, Any], state: Mapping[str, Any] | None = None) -> list[tuple[str, bool]]:
    """Exact V5 Copy Short contract; no raw tables or unrelated diagnostics."""
    identity = _m(summary.get("identity")); decision = _m(summary.get("decision")); scores = _m(summary.get("scores"))
    priority = _m(summary.get("priority")); regime = _m(summary.get("regime")); projection = _m(summary.get("projection"))
    final = _m(canonical.get("final_decision"))
    hkey, forecast = _selected_forecast(canonical, summary)
    direction = decision.get("direction") or forecast.get("direction") or projection.get("direction") or final.get("directional_market_view") or "WAIT"
    reliability = regime.get("regime_reliability") or _m(canonical.get("reliability")).get("score")
    best_entry = priority.get("best_entry_hour")
    second_entry = priority.get("second_best_entry_hour")
    if _present(second_entry) and str(second_entry) not in {"N/A", "-"}:
        best_entry = f"{_text(best_entry)}; second {_text(second_entry)}"
    tp, sl = _quick_tp_sl(canonical, plan)
    current_time = identity.get("latest_completed_candle_time") or canonical.get("latest_completed_candle_time")
    if isinstance(state, Mapping):
        try:
            from core.shared_broker_time_20260622 import shared_broker_time_provider
            current_time = shared_broker_time_provider(state, canonical=canonical).get("shared_broker_time_display") or current_time
        except Exception:
            pass
    projection_text = f"{hkey.upper()} {_text(forecast.get('point_forecast') or projection.get(hkey), 'Not published')} ({_text(direction)})"
    confidence = final.get("calibrated_confidence") or forecast.get("reliability") or projection.get("projection_confidence")
    symbol = identity.get("symbol") or canonical.get("symbol") or "EURUSD"
    timeframe = identity.get("timeframe") or canonical.get("timeframe") or "H1"
    price = projection.get("current_close") or canonical.get("last_close") or _m(canonical.get("market")).get("current_price")
    run_id = canonical.get("run_id") or canonical.get("canonical_calculation_id") or summary.get("calculation_id")
    generation_number = canonical.get("calculation_generation") or identity.get("calculation_generation")
    generation = f"{run_id} / {generation_number}" if _present(generation_number) else run_id
    checksum = canonical.get("checksum") or identity.get("checksum")
    less_risky = decision.get("less_risky_bias") or final.get("less_risky_decision") or "WAIT"
    lower = forecast.get("lower_bound") or projection.get("lower_band")
    upper = forecast.get("upper_bound") or projection.get("upper_band")
    uncertainty = _m(summary.get("uncertainty"))
    validation = _m(summary.get("validation"))
    quant_v3 = _m(canonical.get("quant_research_v3"))
    quant_summary = _m(quant_v3.get("summary"))
    quant_identity = _m(quant_v3.get("identity"))
    quant_line = (
        f"Quant V3 (SHADOW): YZ {_text(quant_summary.get('yz_volatility'), 'Unavailable')} | "
        f"HAR {_text(quant_summary.get('har_volatility_state'), 'Unavailable')} | "
        f"Jump {_text(quant_summary.get('jump_risk'), 'Unavailable')} | "
        f"VaR5 {_text(quant_summary.get('var_5pct_1h'), 'Unavailable')} | "
        f"ES5 {_text(quant_summary.get('expected_shortfall_5pct_1h'), 'Unavailable')} | "
        f"CVaR multiplier {_text(quant_summary.get('cvar_risk_multiplier'), 'Unavailable')} | "
        f"Density {_text(quant_summary.get('density_test'), 'Unavailable')} | "
        f"Execution {_text(quant_summary.get('execution_cost_status'), 'Unavailable')} | "
        f"Generation {_text(quant_identity.get('source_generation_id'), 'Unavailable')}"
    )
    quant_v4 = _m(canonical.get("quant_research_v4"))
    quant_v4_summary = _m(quant_v4.get("summary"))
    quant_v4_identity = _m(quant_v4.get("identity"))
    quant_v4_line = (
        f"Quant V4 (SHADOW): Direction {_text(quant_v4_summary.get('direction_skill'), 'INSUFFICIENT_EVIDENCE')} | "
        f"Probability {_text(quant_v4_summary.get('probability_reliability'), 'INSUFFICIENT_EVIDENCE')} | "
        f"Intervals {_text(quant_v4_summary.get('interval_conditional_coverage'), 'INSUFFICIENT_EVIDENCE')} | "
        f"Regime prob {_text(quant_v4_summary.get('regime_state_probability'), 'INSUFFICIENT_EVIDENCE')} | "
        f"Transition 6H {_text(quant_v4_summary.get('transition_risk_6h'), 'INSUFFICIENT_EVIDENCE')} | "
        f"Tail {_text(quant_v4_summary.get('tail_risk_backtest'), 'INSUFFICIENT_EVIDENCE')} | "
        f"Monitor {_text(quant_v4_summary.get('sequential_monitor'), 'CONTINUE_MONITORING')} | "
        f"Generation {_text(quant_v4_identity.get('source_generation_id'), 'Unavailable')}"
    )
    return [
        (f"ADX Quant Pro — Copy Short | Symbol/timeframe: {_text(symbol)} {_text(timeframe)} | Current price: {_text(price, 'Not published')} | Generation ID: {_text(generation, 'Not published')} | Checksum: {_text(checksum, 'Not published')}", True),
        (f"Current Time: {_text(current_time, 'Not published')} | Completed candle: {_text(identity.get('latest_completed_candle_time') or canonical.get('latest_completed_candle_time'), 'Not published')} | Data freshness: {_text(validation.get('stale_status') or validation.get('data_freshness'), 'Not published')}", True),
        (f"Decision: {_text(decision.get('current_decision') or final.get('final_decision') or 'WAIT')} | Current decision: {_text(decision.get('current_decision') or final.get('final_decision') or 'WAIT')} | Less-risky decision: {_text(less_risky)}", True),
        (f"Direction: {_text(direction)}", True),
        (f"Regime: {_text(regime.get('directional_regime') or _m(canonical.get('regime')).get('major_regime') or 'UNKNOWN')} | Current regime", True),
        (f"Reliability: {_published_num(reliability, 1, '%')} | Regime reliability", True),
        (f"Priority: {_text(priority.get('opportunity_quality') or priority.get('knn_priority') or 'WATCH')} | Priority/rank: {_text(priority.get('current_rank') or priority.get('rank'), 'Not published')}", True),
        (f"Master Score: {_published_num(scores.get('master'), 2)} | Master/Entry/Hold/TP/Exit Risk: " + "/".join(_published_num(scores.get(k), 2) for k in ("master", "entry", "hold", "tp", "exit_risk")), True),
        (f"Entry Score: {_published_num(scores.get('entry'), 2)}", True),
        (f"Hold Score: {_published_num(scores.get('hold'), 2)}", True),
        (f"Exit Risk: {_published_num(scores.get('exit_risk'), 2)}", True),
        (f"TP Quality: {_published_num(scores.get('tp'), 2)}", True),
        (f"Trend Capacity: {_published_num(scores.get('trend_capacity_remaining'), 2)}", True),
        (f"PowerBI Projection: {projection_text} | Forecast direction/horizon: {_text(direction)} / {hkey.upper()} | Prediction interval: {_text(lower, 'Not published')} to {_text(upper, 'Not published')}", True),
        (f"Best Entry Summary: {_text(best_entry, 'Not published')}", True),
        (f"Quick TP: {_text(tp, 'Not published')}", True),
        (f"Quick SL: {_text(sl, 'Not published')}", True),
        (f"Forecast Confidence: {_published_num(confidence, 1, '%')} | Uncertainty/error: {_published_num(uncertainty.get('combined'), 1, '%')} / {_published_num(final.get('error_estimate_pct') or uncertainty.get('error_estimate_pct'), 1, '%')}", True),
        (quant_line, True),
        (quant_v4_line, True),
        (f"AI Summary: {_latest_ai_summary(state, canonical)}", True),
    ]


def build_short_payload(canonical: Mapping[str, Any], summary: Mapping[str, Any], plan: Mapping[str, Any], state: Mapping[str, Any] | None = None) -> tuple[str, PayloadStats]:
    items = _short_lines(canonical, summary, plan, state)
    lines = [line for line, _ in items]
    compressed = False

    def over() -> bool:
        text = "\n".join(lines)
        stats = payload_stats(text)
        return stats.lines > MAX_SHORT_LINES or stats.characters > MAX_SHORT_CHARS or stats.estimated_tokens > TARGET_SHORT_TOKENS

    # Remove low-priority optional lines from the end, never slicing a value.
    optional = [line for line, required in reversed(items) if not required]
    while over() and optional:
        candidate = optional.pop(0)
        if candidate in lines:
            lines.remove(candidate)
            compressed = True
    # Shorten verbose reasons/warnings as a second bounded step.
    if over():
        for index, line in enumerate(list(lines)):
            if line.startswith(("Reason ", "Warning ")) and len(line) > 120:
                lines[index] = line[:119].rsplit(" ", 1)[0] + "…"
                compressed = True
    # Required fields alone are comfortably below limits, but enforce by removing
    # only remaining optional reason/warning lines if a pathological value exists.
    while over():
        removable = next((line for line in reversed(lines) if line.startswith(("Reason ", "Warning "))), None)
        if removable is None:
            break
        lines.remove(removable)
        compressed = True
    if compressed:
        lines.append("[Short export compressed to configured limit]")
    text = "\n".join(lines[:MAX_SHORT_LINES])
    # Last-resort whole-line removal; never character-truncate numeric values.
    while len(text) > MAX_SHORT_CHARS and len(lines) > 15:
        lines.pop(-2 if lines[-1].startswith("[") else -1)
        if "[Short export compressed to configured limit]" not in lines:
            lines.append("[Short export compressed to configured limit]")
        text = "\n".join(lines[:MAX_SHORT_LINES])
    return text, payload_stats(text)


def short_text(canonical: Mapping[str, Any], summary: Mapping[str, Any], plan: Mapping[str, Any], state: Mapping[str, Any] | None = None) -> str:
    return build_short_payload(canonical, summary, plan, state)[0]


def _section(title: str, rows: Iterable[tuple[str, Any]]) -> list[str]:
    lines = [f"## {title}"]
    for label, value in rows:
        if _present(value):
            lines.append(f"- {label}: {_text(value)}")
    return lines


def all_text(canonical: Mapping[str, Any], summary: Mapping[str, Any], plan: Mapping[str, Any], readiness: Mapping[str, Any] | None = None, state: Mapping[str, Any] | None = None) -> str:
    """Full Lunch export: all published metrics plus bounded history/projection/AI summaries."""
    readiness = _m(readiness)
    identity = _m(summary.get("identity")); decision = _m(summary.get("decision")); scores = _m(summary.get("scores"))
    regime = _m(summary.get("regime")); projection = _m(summary.get("projection")); priority = _m(summary.get("priority"))
    validation = _m(summary.get("validation")); similar = _m(summary.get("similar_day")); final = _m(canonical.get("final_decision"))
    evidence_rows = list(canonical.get("latest_relevant_evidence_rows") or _m(canonical.get("compact_ai_fact_pack")).get("latest_relevant_evidence_rows") or [])
    limitations = _unique_strings([
        *list(canonical.get("known_limitations") or []),
        "Historical summaries are bounded; complete machine-readable data remains in the on-demand JSON export.",
        "No copied summary is a guarantee of future market performance.",
    ], limit=8, max_len=260)
    identity_record = {
        "run_id": canonical.get("run_id") or identity.get("run_id"),
        "generation": canonical.get("calculation_generation") or identity.get("calculation_generation"),
        "checksum": canonical.get("checksum"),
    }
    lines = [
        "ADX Quant Pro — Copy All (Eight-Field Structured Summary)",
        f"Generation ID: {_text(summary.get('calculation_id') or canonical.get('run_id'))}",
        "Generation identity JSON: " + json.dumps(identity_record, ensure_ascii=False),
        f"Completed candle: {_text(identity.get('latest_completed_candle_time') or canonical.get('latest_completed_candle_time'))}",
        "",
    ]
    lines += _section("Field 1 — Full Metric 25-Day History + Decision Tables", [
        ("Current decision", decision.get("current_decision")), ("Less-risky decision", decision.get("less_risky_bias")),
        ("Protected scores", "/".join(_num(scores.get(k), 2) for k in ("master", "entry", "hold", "tp", "exit_risk"))),
        ("Priority", priority.get("opportunity_quality")), ("Rank", priority.get("current_rank")),
        ("Position sizing", plan.get("status")), ("Decision 11", _m(canonical.get("medium_standard_regime_bias")).get("decision")),
        ("History summary", "25-day newest-completed-H1-first view; ten protected histories preserved"),
    ])
    lines += [""] + _section("Field 2 — Power BI Price Prediction Path", [
        ("Current price", projection.get("current_close")), ("H+1", projection.get("h1")), ("H+3", projection.get("h3")), ("H+6", projection.get("h6")),
        ("Lower band", projection.get("lower_band")), ("Upper band", projection.get("upper_band")),
        ("Projection confidence", projection.get("projection_confidence")), ("Validation", validation.get("validation_status")),
    ])
    lines += [""] + _section("Field 3 — Regime History + Standards", [
        ("Directional regime", regime.get("directional_regime")), ("Volatility regime", regime.get("volatility_regime")),
        ("Reliability", regime.get("regime_reliability")), ("Transition risk", regime.get("transition_risk")),
        ("Estimated transition window", regime.get("estimated_transition_window")), ("Alpha", regime.get("alpha")), ("Delta", regime.get("delta")),
        ("History summary", "Lower, medium and higher standard 25-day views preserved"),
    ])
    lines += [""] + _section("Field 4 — Dinner Full Combined Intelligence", [
        ("Combined decision", decision.get("current_decision")), ("Forecast agreement", final.get("forecast_agreement")),
        ("KNN priority", priority.get("knn_priority")), ("Greedy priority", priority.get("greedy_priority")),
        ("Similar-day pattern", similar.get("pattern_family")), ("Best historical match", similar.get("best_match_date")),
        ("Similar-day weighted result", similar.get("weighted_result")),
    ])
    lines += [""] + _section("Field 5 — Grounded AI Assistant", [
        ("Architecture", "local lexical RAG + controlled read-only routing + evidence critic + one revision pass"),
        ("Generation grounding", summary.get("calculation_id")), ("Evidence records available", len(evidence_rows)),
        ("External AI", "Not used"),
    ])
    quant_v3 = _m(canonical.get("quant_research_v3"))
    quant_summary = _m(quant_v3.get("summary"))
    quant_identity = _m(quant_v3.get("identity"))
    quant_v4 = _m(canonical.get("quant_research_v4"))
    quant_v4_summary = _m(quant_v4.get("summary"))
    quant_v4_identity = _m(quant_v4.get("identity"))
    lines += [""] + _section("Field 6 — Future Strategy Research History", [
        ("Evidence status", readiness.get("final_status")),
        ("Persisted research rows", readiness.get("persisted_research_rows")),
        ("Tables with evidence", readiness.get("available_history_tables")),
        ("Configured research tables", readiness.get("configured_history_tables")),
        ("Allowed strategy effect", readiness.get("strategy_influence")),
        ("Direction reversal allowed", readiness.get("direction_reversal_allowed")),
        ("Production influence default", readiness.get("production_influence_default")),
        ("Quant V3 mode", quant_v3.get("mode")),
        ("Quant V3 source generation", quant_identity.get("source_generation_id")),
        ("YZ volatility", quant_summary.get("yz_volatility")),
        ("HAR volatility state", quant_summary.get("har_volatility_state")),
        ("Jump risk", quant_summary.get("jump_risk")),
        ("5% VaR", quant_summary.get("var_5pct_1h")),
        ("5% Expected Shortfall", quant_summary.get("expected_shortfall_5pct_1h")),
        ("CVaR risk multiplier", quant_summary.get("cvar_risk_multiplier")),
        ("Density test", quant_summary.get("density_test")),
        ("Execution cost status", quant_summary.get("execution_cost_status")),
        ("Overall Quant V3 status", quant_summary.get("overall_quant_v3_status")),
        ("Quant V4 mode", "SHADOW"),
        ("Quant V4 source generation", quant_v4_identity.get("source_generation_id")),
        ("Quant V4 completed broker H1", quant_v4_identity.get("latest_completed_broker_h1_time")),
        ("Direction statistical skill", quant_v4_summary.get("direction_skill")),
        ("Direction skill p-value", quant_v4_summary.get("direction_skill_p_value")),
        ("Probability reliability", quant_v4_summary.get("probability_reliability")),
        ("Interval conditional coverage", quant_v4_summary.get("interval_conditional_coverage")),
        ("Shadow regime state", quant_v4_summary.get("regime_state")),
        ("Shadow regime probability", quant_v4_summary.get("regime_state_probability")),
        ("Transition risk 6H", quant_v4_summary.get("transition_risk_6h")),
        ("Volatility model status", quant_v4_summary.get("volatility_model_status")),
        ("Preferred shadow volatility", quant_v4_summary.get("preferred_shadow_volatility_method")),
        ("Tail-risk backtest", quant_v4_summary.get("tail_risk_backtest")),
        ("Sequential monitor", quant_v4_summary.get("sequential_monitor")),
        ("Overall Quant V4 status", quant_v4_summary.get("overall_status")),
    ])
    field7 = _m(state.get("field_07_research_summary_v11") if isinstance(state, Mapping) else {})
    field7_compact = _m(_m(field7.get("v13_research")).get("compact_results"))
    lines += [""] + _section("Field 7 — Scientific Research Intelligence", [
        ("Research status", field7.get("research_status") or field7.get("status")),
        ("Available research layers", field7_compact.get("available_layers")),
        ("Completed H1 rows", field7_compact.get("completed_h1_rows")),
        ("Matured embargoed outcomes", field7_compact.get("matured_embargoed_outcomes")),
        ("Automatic promotion", field7_compact.get("automatic_promotion")),
        ("Production decision changed", field7.get("production_decision_unchanged") is False),
    ])
    field8_status = _m(state.get("field8_publication_status_20260624") if isinstance(state, Mapping) else {})
    field8_identity = _m(state.get("field8_publication_identity_20260624") if isinstance(state, Mapping) else {})
    lines += [""] + _section("Field 8 — Integrated 25-Day Accuracy History", [
        ("Publication status", field8_status.get("status") or ("PUBLISHED" if field8_status.get("published") else "NOT PUBLISHED")),
        ("Published rows", field8_status.get("row_count")),
        ("Run ID", field8_identity.get("run_id")),
        ("Generation ID", field8_identity.get("generation_id")),
        ("Snapshot hash", field8_identity.get("snapshot_hash")),
        ("Mode", "Shadow evidence only; production decisions and protected weights unchanged"),
    ])

    lines += ["", "## Evidence and limitations"]
    for row in evidence_rows[:12]:
        if isinstance(row, Mapping):
            lines.append(f"- {_text(row.get('source_name') or row.get('table_name') or 'Evidence')}: {_text(row.get('metric_name') or row.get('condition'))} = {_text(row.get('metric_value') or row.get('value_text') or row.get('value_numeric'))}")
    for limitation in limitations:
        lines.append(f"- Limitation: {limitation}")

    # Include every scalar published metric without serialising model objects or
    # unbounded raw tables. This keeps Copy Full useful and mobile-safe.
    lines += ["", "## All published scalar metrics"]
    for key in sorted(canonical):
        value = canonical.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            if _present(value):
                lines.append(f"- {key}: {_text(value)}")

    state = state if isinstance(state, Mapping) else {}
    lines += ["", "## History refresh and synchronization summary"]
    verification = _m(state.get("history_sync_verification_20260622"))
    lines.append(f"- Status: {_text(verification.get('status'), 'Not verified')}")
    lines.append(f"- Expected latest broker candle UTC: {_text(verification.get('expected_latest_completed_h1'), 'Not verified')}")
    for table, row in _m(verification.get("tables")).items():
        item = _m(row)
        lines.append(f"- {table}: {'Synced' if item.get('synced') else 'Out of Sync'}; latest={_text(item.get('latest_completed_h1'))}; difference_minutes={_text(item.get('difference_minutes'))}")

    lines += ["", "## Latest AI summary"]
    lines.append(_latest_ai_summary(state, canonical))
    return "\n".join(lines)


def machine_json(canonical: Mapping[str, Any], summary: Mapping[str, Any], plan: Mapping[str, Any]) -> str:
    """Complete machine-readable export, prepared only on explicit demand."""
    payload = {
        "canonical_generation": dict(canonical),
        "compact_display_summary": dict(summary),
        "risk_sizing_plan": dict(plan),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)


def _json_default(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict("records")
        except Exception:
            try:
                return value.to_dict()
            except Exception:
                pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


__all__ = [
    "MAX_SHORT_LINES", "MAX_SHORT_CHARS", "TARGET_SHORT_TOKENS", "PayloadStats",
    "payload_stats", "generation_identity", "build_short_payload", "short_text", "all_text", "machine_json",
]
