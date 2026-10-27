"""Compact read-only Field 7 evidence inside the protected Lunch gate layout."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping

import pandas as pd


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def build_field7_evidence(
    state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None, *, limit: int = 600
) -> pd.DataFrame:
    from core.lunch_h1_data_quality_v13 import build_h1_decision_evidence

    evidence = build_h1_decision_evidence(state, canonical, days=25, limit=limit)
    if evidence.empty:
        return evidence
    preferred = [
        "event_time_utc", "Broker Time", "Close",
        "Momentum 3H (pips)", "Momentum 6H (pips)",
        "Trend Agreement", "ATR 14H (pips)", "Volatility 12H (pips)",
        "Session (UTC)", "Actionability", "Decision Level /10",
        "Data Quality Score /100", "Data Quality", "Evidence Class",
        "Settled Status", "Source Provenance", "Production Decision Changed",
    ]
    return evidence.loc[:, [column for column in preferred if column in evidence.columns]].head(limit)


def render_field7_shadow(
    state: MutableMapping[str, Any], canonical: Mapping[str, Any] | None = None
) -> None:
    import streamlit as st

    st.markdown("#### Field 7 — Stored Shadow Research + Completed-H1 Decision Evidence")
    st.caption(
        "This is the existing Field 7 research architecture shown inside the protected Lunch load gate. "
        "It reads only the saved Settings generation and cannot change production decisions or weights."
    )
    summary = _mapping(state.get("field_07_research_summary_v11"))
    v13 = _mapping(summary.get("v13_research"))
    compact = _mapping(v13.get("compact_results"))
    if compact:
        metrics = st.columns(4)
        metrics[0].metric("V13 Layers Available", f"{compact.get('available_layers', 0)}/{compact.get('total_layers', 10)}")
        metrics[1].metric("Completed H1 Rows", compact.get("completed_h1_rows", 0))
        metrics[2].metric("Matured Outcomes", compact.get("matured_embargoed_outcomes", 0))
        metrics[3].metric("Production Changed", "NO")
        st.caption(
            f"Snapshot {str(v13.get('snapshot_hash') or 'UNAVAILABLE')[:24]} · "
            f"data quality {compact.get('data_quality_status', 'UNAVAILABLE')} · "
            "future-actual leakage prohibited."
        )
    else:
        st.info("No stored V13 research snapshot exists for this generation; no certificate is invented.")

    evidence = build_field7_evidence(state, canonical, limit=600)
    if evidence.empty:
        st.info("Cached completed-H1 evidence is unavailable; no Field 7 fallback rows were fabricated.")
    else:
        st.dataframe(evidence, use_container_width=True, hide_index=True, height=560)
        st.caption(
            f"{len(evidence):,} completed-H1 shadow rows · newest first · "
            "COMPLETED_H1_SHADOW_DECISION_SUPPORT · NOT_A_SETTLED_OUTCOME."
        )
    with st.expander("Open / Close — Field 7 Decision-Role History — Last 25 Days", expanded=False):
        from core.field_789_history_20260625 import build_field_history
        history=build_field_history(state,7)
        if history.empty: st.info("No completed 25-day Field 7 decision evidence is available yet.")
        else: st.dataframe(history,use_container_width=True,hide_index=True,height=420)
    if st.button("Open Full Research Lab", key="open_full_research_lab_v13", use_container_width=True):
        state["active_page"] = "Research Lab"
        state["tab_choice"] = "Research Lab"
        state["active_subpage"] = ""
        st.rerun()


__all__ = ["build_field7_evidence", "render_field7_shadow"]
