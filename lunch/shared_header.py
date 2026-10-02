"""Canonical Quick Decision header shared across all fields."""
from __future__ import annotations
import streamlit as st
from core.canonical.snapshot import CanonicalRunSnapshot


def render_quick_decision(snapshot: CanonicalRunSnapshot) -> None:
    st.markdown("### ⚡ Lunch Quick Decision")
    first = st.columns(4)
    first[0].metric("Decision", snapshot.decision)
    first[1].metric("Less-Risky", snapshot.less_risky_decision)
    first[2].metric("Regime", snapshot.regime)
    first[3].metric("Broker Candle", snapshot.broker_candle_time.strftime("%Y-%m-%d %H:%M"))
    second = st.columns(4)
    second[0].metric("Priority", f"{snapshot.priority:.1f}/100")
    second[1].metric("Reliability", f"{snapshot.reliability:.1f}%")
    second[2].metric("Uncertainty", f"{snapshot.uncertainty:.1f}%")
    second[3].metric("Run ID", snapshot.run_id[-12:] if len(snapshot.run_id) > 12 else snapshot.run_id)
    st.caption(f"{snapshot.symbol} {snapshot.timeframe} · one immutable run ID and broker candle time for Fields 1–7")
