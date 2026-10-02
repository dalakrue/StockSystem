"""Lightweight Field-1 decision identity strip for all five principal Lunch fields.

Reads only the immutable decision table already published by Field 1. It never
starts calculation, fits a model, or mutates protected production decisions.
"""
from __future__ import annotations
from typing import Any, Mapping
import pandas as pd
import streamlit as st
from core.decision_table_20260626 import build_decision_table, freeze_canonical_decision_snapshot


def _snapshot_payload(state: Mapping[str, Any], snapshot: Any) -> dict[str, Any]:
    cached = state.get("canonical_decision_snapshot")
    if isinstance(cached, dict) and cached.get("run_id") == snapshot.run_id:
        return cached
    table = build_decision_table(state, snapshot)
    return freeze_canonical_decision_snapshot(snapshot, table, state)


def render_decision_sync(context: Any, *, field_name: str, show_latest_row: bool = True) -> None:
    state = context.history_repository.state
    payload = _snapshot_payload(state, context.snapshot)
    row = payload.get("decision_table_row") or {}
    st.markdown(f"#### Field 1 Decision Synchronization — {field_name}")
    cols = st.columns(5)
    cols[0].metric("Canonical Decision", payload.get("production_decision", "N/A"))
    cols[1].metric("Direction Confirmation", row.get("Direction Confirmation Decision", "N/A"))
    cols[2].metric("Master Decision", row.get("Master Decision", "N/A"))
    cols[3].metric("Reliability", row.get("Decision Reliability", "N/A"))
    cols[4].metric("Broker Candle", str(payload.get("broker_candle_time", "N/A"))[:16])
    st.caption(
        "Read-only synchronization with Field 1 · same run_id, generation_id, snapshot hash and completed broker candle · no logic blending or recalculation."
    )
    if show_latest_row and row:
        wanted = [
            "Date", "Weekday", "Hour", "Entry Strength Decision", "SELL Pressure Decision",
            "BUY Pressure Decision", "Pressure Decision", "M1 Confirmation Decision",
            "Pullback Readiness Decision", "Hold Safety Decision", "TP Quality Decision",
            "Master Decision", "Direction Confirmation Decision", "Final Decision",
        ]
        st.dataframe(pd.DataFrame([{k: row.get(k, "N/A") for k in wanted}]), use_container_width=True, hide_index=True)
