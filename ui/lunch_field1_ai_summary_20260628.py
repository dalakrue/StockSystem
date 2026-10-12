"""Lightweight current-candle AI-style summary moved to the bottom of Lunch Field 1.

The section is deterministic and read-only. It summarizes already-published
canonical/Table 5/Dinner research evidence and never invokes a model, connector,
or production calculation when the expander opens.
"""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping
import math
import pandas as pd


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _present(value: Any) -> bool:
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except Exception:
        pass
    text = str(value).strip().upper()
    return text not in {"", "N/A", "NA", "NONE", "NAN", "UNAVAILABLE", "-", "—"}


def _time_column(frame: pd.DataFrame) -> str | None:
    for name in ("Broker Candle Time", "Completed Broker Candle", "Broker Candle", "Time", "Timestamp", "Datetime"):
        if name in frame.columns:
            return name
    return None


def _current_row(frame: Any, candle: Any) -> dict[str, Any]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {}
    work = frame.copy(deep=False)
    time_col = _time_column(work)
    target = pd.to_datetime(candle, errors="coerce", utc=True)
    if time_col is not None:
        parsed = pd.to_datetime(work[time_col], errors="coerce", utc=True, format="mixed").dt.floor("h")
        if pd.notna(target):
            exact = work.loc[parsed.eq(pd.Timestamp(target).floor("h"))]
            if not exact.empty:
                work = exact
            else:
                return {}
        elif parsed.notna().any():
            work = work.loc[parsed.eq(parsed.max())]
    return work.iloc[0].to_dict() if not work.empty else {}


def _protective_label(value: Any) -> str:
    text = str(value or "").strip().upper().replace("_", " ")
    if any(token in text for token in ("WAIT", "PULLBACK", "NO TRADE", "NEUTRAL")):
        return "WAIT FOR PULLBACK"
    if any(token in text for token in ("BUY", "SELL", "HOLD", "PROTECT", "BULL", "BEAR")):
        return "HOLD & PROTECT"
    return "NOT PUBLISHED"


def build_field1_ai_summary(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    final = _mapping(canonical.get("final_decision"))
    candle = (
        canonical.get("completed_broker_candle")
        or canonical.get("broker_candle_time")
        or canonical.get("latest_completed_candle_time")
        or _mapping(canonical.get("market")).get("latest_completed_candle_time")
    )
    table5 = _current_row(state.get("field1_table5_integrated_decision_collection_20260627"), candle)
    dinner_frame = state.get("field4to9_collection_history_full_20260628")
    if not isinstance(dinner_frame, pd.DataFrame):
        dinner_frame = state.get("field4to9_collection_history_20260627")
    dinner = _current_row(dinner_frame, candle)
    thesis = state.get("arert_thesis_research_20260628")
    thesis = thesis if isinstance(thesis, Mapping) else {}
    module20 = _mapping(_mapping(thesis.get("modules")).get("20"))
    module20_summary = _mapping(module20.get("summary"))

    production = (
        final.get("final_decision") or final.get("decision")
        or canonical.get("full_metric_direction") or canonical.get("decision")
        or table5.get("Production Master Decision")
    )
    less_risky = final.get("less_risky_decision") or final.get("less_risky_bias")
    protective = (
        table5.get("Protective Action — Production Master Decision")
        or dinner.get("Action 20 — Final Protective Action")
        or _protective_label(less_risky or production)
    )
    factor_columns = [
        "Net Pressure Decision", "Pressure Decision", "Entry Strength Decision",
        "SELL Pressure Decision", "BUY Pressure Decision", "Pullback Readiness Decision",
        "M1 Confirmation Decision", "Hold Safety Decision", "TP Quality Decision",
        "Master Decision", "Direction Confirmation Decision",
    ]
    available = {column: table5.get(column) for column in factor_columns if _present(table5.get(column))}
    missing = [column for column in factor_columns if column not in available]
    decision_values = [str(value).upper() for value in available.values()]
    buy = sum("BUY" in value for value in decision_values)
    sell = sum("SELL" in value for value in decision_values)
    wait = sum(any(token in value for token in ("WAIT", "PULLBACK")) for value in decision_values)

    arert_score = module20_summary.get("final_arert_score") or module20_summary.get("ARERT Score")
    try:
        arert_score = round(float(arert_score), 2) if math.isfinite(float(arert_score)) else None
    except Exception:
        arert_score = None

    quality = "COMPLETE" if len(available) == len(factor_columns) else "PARTIAL" if available else "UNAVAILABLE"
    try:
        from core.buy_sell_frequency_20260629 import frequency_summary
        distribution = frequency_summary(state.get("field1_table1_decision_history_20260628"))
    except Exception:
        distribution = {"BFD": "No Trade", "SFD": "No Trade", "rows": 0}
    if quality == "UNAVAILABLE":
        explanation = "No current-hour Table 1 factor row is published, so the summary does not infer missing evidence."
    else:
        balance = "mixed" if buy and sell else "buy-aligned" if buy else "sell-aligned" if sell else "neutral/pullback"
        explanation = (
            f"Current completed-H1 evidence is {balance}: {buy} BUY, {sell} SELL and {wait} WAIT/pullback factor labels "
            f"across {len(available)} available Table 1 factors. The protective display action is {protective}."
        )

    return {
        "run_id": canonical.get("run_id") or canonical.get("canonical_calculation_id"),
        "generation_id": canonical.get("generation_id") or canonical.get("calculation_generation"),
        "symbol": canonical.get("symbol") or "EURUSD",
        "timeframe": canonical.get("timeframe") or "H1",
        "completed_broker_candle": candle,
        "production_decision": production,
        "less_risky_decision": less_risky,
        "protective_display_action": protective,
        "table1_factor_availability": f"{len(available)}/{len(factor_columns)}",
        "data_quality": quality,
        "available_factors": available,
        "missing_factors": missing,
        "buy_factor_count": buy,
        "sell_factor_count": sell,
        "wait_or_pullback_factor_count": wait,
        "BFD": distribution.get("BFD", "No Trade"),
        "SFD": distribution.get("SFD", "No Trade"),
        "distribution_rows": distribution.get("rows", 0),
        "arert_score": arert_score,
        "explanation": explanation,
        "calculation_notice": "Read-only current-candle summary; production logic and Table 3 are unchanged.",
    }


def render_field1_ai_summary(state: MutableMapping[str, Any], canonical: Mapping[str, Any]) -> None:
    import streamlit as st

    summary = build_field1_ai_summary(state, canonical)
    state["lunch_field1_ai_summary_20260628"] = summary
    with st.expander("Open / Close — AI Summary (Moved to Bottom of Lunch Field 1)", expanded=False):
        st.caption(
            "Current completed-broker-candle evidence only. This lightweight section reads cached publications; "
            "opening it does not call AirLLM/OpenRouter, fetch APIs, or rerun calculations."
        )
        st.markdown(
            f"""**Identity.** `{summary.get('symbol') or '—'} / {summary.get('timeframe') or '—'}` · completed broker candle `{summary.get('completed_broker_candle') or '—'}` · run `{summary.get('run_id') or '—'}` · generation `{summary.get('generation_id') or '—'}`.

**Decision state.** Production decision: **{summary.get('production_decision') or 'NOT PUBLISHED'}**. Less-risky decision: **{summary.get('less_risky_decision') or 'NOT PUBLISHED'}**. Protective action: **{summary.get('protective_display_action') or 'NOT PUBLISHED'}**.

**Frequency distribution.** BFD: **{summary.get('BFD') or 'No Trade'}**. SFD: **{summary.get('SFD') or 'No Trade'}**. The distribution is derived from {summary.get('distribution_rows') or 0} published Field 1 rows and does not overwrite the production decision.

**Evidence density.** Table 1 factor availability is **{summary.get('table1_factor_availability') or '0/11'}**, quality is **{summary.get('data_quality') or 'UNAVAILABLE'}**, with **{summary.get('buy_factor_count') or 0} BUY**, **{summary.get('sell_factor_count') or 0} SELL**, and **{summary.get('wait_or_pullback_factor_count') or 0} WAIT/pullback** labels.

**Interpretation.** {summary.get('explanation') or 'No current-candle interpretation is available.'}"""
        )
        evidence = summary.get("available_factors") or {}
        if evidence:
            lines = [f"- **{key}:** {value}" for key, value in evidence.items()]
            st.markdown("**Current factor evidence**\n" + "\n".join(lines))
        if summary.get("missing_factors"):
            st.markdown("**Not published for this exact candle:** " + ", ".join(summary["missing_factors"]))
        if summary.get("arert_score") is not None:
            st.markdown(f"**ARERT academic reliability:** {summary['arert_score']}")
        st.caption(str(summary.get("calculation_notice")))


__all__ = ["build_field1_ai_summary", "render_field1_ai_summary"]
