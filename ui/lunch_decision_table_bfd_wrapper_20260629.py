"""Protected Table 1 presentation wrapper with additive BFD/SFD columns.

The original ``lunch_decision_table_20260626.py`` remains byte-for-byte intact.
This wrapper reuses its protected builder/snapshot/fallback functions and changes
presentation only.
"""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping
import pandas as pd

from ui.lunch_decision_table_20260626 import _fallback_from_history, _snapshot
from core.decision_table_20260626 import build_decision_table


def render_field1_decision_history(*, state: MutableMapping[str, Any], canonical: Mapping[str, Any]) -> None:
    import streamlit as st

    st.markdown("#### Table 1 — Decision History — Last 25 Days")
    st.caption(
        "Protected Field 1 source of truth with additive BFD/SFD display states · "
        "newest completed broker candle first · production decisions are unchanged."
    )
    try:
        table = build_decision_table(state, _snapshot(canonical, state))
    except Exception:
        table = _fallback_from_history(state)
    if isinstance(table, pd.DataFrame) and not table.empty:
        from core.self_contained_table_logic_20260627 import enrich_decision_history
        from core.buy_sell_frequency_20260629 import enrich_bfd_sfd
        table = enrich_decision_history(table, state)
        table = enrich_bfd_sfd(table)
    if not isinstance(table, pd.DataFrame) or table.empty:
        st.info(
            "Decision History has no published rows yet. Historical rows accumulate only from completed "
            "broker candles and are never fabricated."
        )
        return

    state["field1_table1_decision_history_20260628"] = table.copy(deep=False)
    preferred = [
        "Date", "Weekday", "Hour", "BFD", "SFD",
        "Entry Strength Decision", "SELL Pressure Decision", "BUY Pressure Decision",
        "Net Pressure Decision", "Pullback Readiness Decision", "M1 Confirmation Decision",
        "Master Decision", "Hold Safety Decision", "TP Quality Decision",
        "Direction Confirmation Decision", "Decision Name", "Production Decision Raw", "Action Display Label",
        "Outcome Status", "Decision Correct", "Net Pressure Source", "Direction Confirmation Source",
        "Master Decision Source", "Source Run ID", "Source Generation ID", "Completed Broker Candle",
        "Source Snapshot Hash", "Source Signature", "Final Decision",
    ]
    shown = table.loc[:, [c for c in preferred if c in table.columns]].copy()
    if {"Decision Correct", "Outcome Status"}.issubset(shown.columns):
        pending = ~shown["Outcome Status"].astype(str).str.upper().isin({"SETTLED", "RESOLVED"})
        missing = shown["Decision Correct"].isna() | shown["Decision Correct"].astype(str).str.upper().isin(
            {"", "N/A", "NA", "NONE"}
        )
        shown.loc[pending & missing, "Decision Correct"] = "PENDING — NEXT H1 NOT SETTLED"
    try:
        from core.shared_broker_time_20260622 import frame_to_shared_broker_clock
        clock_source = shown.copy()
        if "Completed Broker Candle" in clock_source.columns and "Time" not in clock_source.columns:
            clock_source["Time"] = clock_source["Completed Broker Candle"]
        shown = frame_to_shared_broker_clock(clock_source, state, canonical=canonical)
    except Exception:
        pass
    st.dataframe(shown, use_container_width=True, hide_index=True, height=520)

    latest = table.iloc[0].to_dict()
    decision_cols = [c for c in preferred if c.endswith("Decision") and c in latest]
    directional = [str(latest.get(c, "")).upper() for c in decision_cols]
    buy = sum("BUY" in value for value in directional)
    sell = sum("SELL" in value for value in directional)
    available = sum(value not in {"", "N/A", "NONE", "MISSING"} for value in directional)
    cols = st.columns(4)
    cols[0].metric("BUY Decisions", buy)
    cols[1].metric("SELL Decisions", sell)
    cols[2].metric("Directional Conflict", min(buy, sell))
    cols[3].metric("Decision Coverage", f"{available}/{len(decision_cols)}" if decision_cols else "0/0")
    st.caption(
        "BFD/SFD are display-only frequency states: Wait Pullback, Hold and Protect, Allowed, or No Trade. "
        "They do not lower protected thresholds or rewrite Table 3."
    )


__all__ = ["render_field1_decision_history"]
