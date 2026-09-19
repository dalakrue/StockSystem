"""Compact reliability-first Dinner research history view."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping
import numpy as np
import pandas as pd


def _time_column(frame: pd.DataFrame) -> str | None:
    preferred = (
        "Broker Candle", "Broker Candle Time", "Completed Broker Candle",
        "Time", "Datetime", "Timestamp", "DateTime",
    )
    return next((c for c in preferred if c in frame.columns), None)


def _numeric_score(frame: pd.DataFrame, tokens: tuple[str, ...]) -> pd.Series:
    matches = [c for c in frame.columns if any(token in str(c).lower() for token in tokens)]
    series: list[pd.Series] = []
    for column in matches:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.notna().any():
            maximum = float(values.max(skipna=True))
            if maximum <= 1.5:
                values = values * 100.0
            elif maximum <= 10.5:
                values = values * 10.0
            series.append(values.clip(0.0, 100.0))
    if not series:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.concat(series, axis=1).mean(axis=1, skipna=True)


def build_research_history_view(history: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame(), {"rows": 0, "status": "UNAVAILABLE"}
    frame = history.copy(deep=False)
    time_col = _time_column(frame)
    if time_col:
        parsed = pd.to_datetime(frame[time_col], errors="coerce", utc=True, format="mixed")
        frame = frame.loc[parsed.notna()].copy()
        parsed = parsed.loc[frame.index]
        frame[time_col] = parsed
        frame["__time"] = parsed
        cutoff = parsed.max() - pd.Timedelta(days=25)
        frame = frame.loc[parsed >= cutoff].copy()
        frame = frame.sort_values("__time", ascending=False, kind="mergesort")
        frame = frame.drop_duplicates(subset=[time_col], keep="first")

    reliability = _numeric_score(frame, ("reliability", "confidence", "trust"))
    uncertainty = _numeric_score(frame, ("uncertainty", "error", "conflict"))
    coverage = _numeric_score(frame, ("coverage", "availability", "completeness"))
    # When the source publishes no explicit reliability field, use transparent
    # coverage/conflict quality rather than inventing a model score.
    effective_reliability = reliability.copy()
    fallback = 0.60 * coverage + 0.40 * (100.0 - uncertainty)
    effective_reliability = effective_reliability.where(effective_reliability.notna(), fallback)

    decision_col = next((c for c in (
        "Protective Action", "Production Master Decision", "Technical Consensus",
        "Final Decision", "Decision",
    ) if c in frame.columns), None)
    source_columns = [
        c for c in frame.columns
        if any(token in str(c).lower() for token in ("field 4", "field 6", "field 7", "field 8", "field 9", "research"))
        and any(token in str(c).lower() for token in ("decision", "bias", "score", "reliab", "status"))
    ]

    view = pd.DataFrame(index=frame.index)
    if time_col:
        view["Broker Candle"] = frame[time_col]
    if decision_col:
        view["Decision"] = frame[decision_col]
    view["Research Reliability %"] = effective_reliability.round(2)
    view["Coverage %"] = coverage.round(2)
    view["Uncertainty / Conflict %"] = uncertainty.round(2)
    view["Evidence Status"] = np.select(
        [
            effective_reliability.ge(75) & coverage.ge(70) & uncertainty.le(35),
            effective_reliability.ge(55) & coverage.ge(45),
        ],
        ["RELIABLE", "USE WITH CAUTION"],
        default="INSUFFICIENT / CONFLICTED",
    )
    for column in source_columns[:12]:
        view[str(column)] = frame[column]
    view = view.dropna(axis=1, how="all").reset_index(drop=True)

    summary = {
        "rows": int(len(view)),
        "status": "READY" if len(view) else "UNAVAILABLE",
        "reliable_rows": int((view.get("Evidence Status", pd.Series(dtype=str)) == "RELIABLE").sum()),
        "median_reliability": round(float(pd.to_numeric(view.get("Research Reliability %"), errors="coerce").median()), 2) if "Research Reliability %" in view else None,
        "median_coverage": round(float(pd.to_numeric(view.get("Coverage %"), errors="coerce").median()), 2) if "Coverage %" in view else None,
        "median_uncertainty": round(float(pd.to_numeric(view.get("Uncertainty / Conflict %"), errors="coerce").median()), 2) if "Uncertainty / Conflict %" in view else None,
    }
    return view, summary


def render_dinner_research_history_upgrade(state: MutableMapping[str, Any], history: Any) -> None:
    import streamlit as st

    view, summary = build_research_history_view(history)
    state["dinner_research_history_upgrade_20260629"] = view
    with st.expander("Open / Close — Research History Quality, Reliability and Efficiency", expanded=True):
        st.caption(
            "One deduplicated row per completed broker candle, newest first, bounded to the last 25 broker days. "
            "Reliability, coverage and conflict are separated so a wide research table is easier to audit."
        )
        cols = st.columns(4)
        cols[0].metric("History Rows", summary.get("rows", 0))
        cols[1].metric("Reliable Rows", summary.get("reliable_rows", 0))
        cols[2].metric("Median Reliability", "—" if summary.get("median_reliability") is None else f"{summary['median_reliability']:.1f}%")
        cols[3].metric("Median Coverage", "—" if summary.get("median_coverage") is None else f"{summary['median_coverage']:.1f}%")
        if view.empty:
            st.info("The current Dinner generation does not contain timestamped research history rows.")
            return
        query = st.text_input(
            "Search research history", key="dinner_research_history_upgrade_search_20260629",
            placeholder="Example: RELIABLE, BUY, NO TRADE, Field 9",
        )
        shown = view
        if query.strip():
            mask = shown.astype(str).apply(lambda col: col.str.contains(query.strip(), case=False, na=False)).any(axis=1)
            shown = shown.loc[mask]
        st.dataframe(shown.head(600), use_container_width=True, hide_index=True, height=460)
        st.download_button(
            "Export Reliability-First Research History CSV",
            shown.to_csv(index=False).encode("utf-8"),
            file_name="dinner_research_history_quality_last_25_broker_days.csv",
            mime="text/csv",
            key="dinner_research_history_upgrade_export_20260629",
            use_container_width=True,
        )


__all__ = ["build_research_history_view", "render_dinner_research_history_upgrade"]
