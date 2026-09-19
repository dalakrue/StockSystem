"""Real button controls for canonical short/full copy payloads."""
from __future__ import annotations

import json
from typing import Any
import streamlit as st
from core.canonical.snapshot import CanonicalRunSnapshot


def build_short(snapshot: CanonicalRunSnapshot) -> str:
    research = dict(snapshot.research_summary)
    lines = [
        f"Broker candle time: {snapshot.broker_candle_time.isoformat()}",
        f"Symbol/timeframe: {snapshot.symbol} {snapshot.timeframe}",
        f"Run ID: {snapshot.run_id}",
        f"Decision: {snapshot.decision}",
        f"Regime: {snapshot.regime}",
        f"Priority: {snapshot.priority:.2f}",
        f"Reliability: {snapshot.reliability:.2f}%",
        f"Predictions: {json.dumps(dict(snapshot.predictions), default=str, ensure_ascii=False)}",
        f"Field 7 status: {research.get('research_status', 'INSUFFICIENT EVIDENCE')}",
        f"Risk multiplier: {research.get('risk_multiplier', 0.0)}",
    ]
    return "\n".join(lines)


def build_full(snapshot: CanonicalRunSnapshot) -> str:
    return json.dumps(snapshot.to_dict(), default=str, ensure_ascii=False, indent=2, sort_keys=True)


def render_copy_controls(snapshot: CanonicalRunSnapshot) -> None:
    short_col, full_col = st.columns(2)
    if short_col.button("Copy Short", use_container_width=True, key="copy_short_button_v11"):
        st.session_state["lunch_copy_payload_v11"] = build_short(snapshot)
        st.session_state["lunch_copy_kind_v11"] = "Short"
    if full_col.button("Copy Full", use_container_width=True, key="copy_full_button_v11"):
        st.session_state["lunch_copy_payload_v11"] = build_full(snapshot)
        st.session_state["lunch_copy_kind_v11"] = "Full"
    payload = st.session_state.get("lunch_copy_payload_v11")
    if payload:
        st.text_area(
            f"{st.session_state.get('lunch_copy_kind_v11', 'Copy')} payload — select and copy",
            value=str(payload),
            height=120,
            key="lunch_copy_textarea_v11",
        )
