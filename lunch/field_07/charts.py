"""Compact, read-only Field 7 charts."""
from __future__ import annotations
import pandas as pd
import streamlit as st


def render_horizon_chart(horizons: pd.DataFrame) -> None:
    if not isinstance(horizons, pd.DataFrame) or horizons.empty:
        st.info("No stored horizon diagnostics are available for this run.")
        return
    columns = [column for column in ("forecastability", "model_agreement") if column in horizons.columns]
    if columns and "horizon_hours" in horizons.columns:
        chart = horizons.set_index("horizon_hours")[columns]
        st.line_chart(chart)


def render_history_chart(history: pd.DataFrame) -> None:
    if not isinstance(history, pd.DataFrame) or history.empty:
        return
    columns = [column for column in ("research_trust_score", "risk_multiplier", "change_probability") if column in history.columns]
    if not columns:
        return
    chart = history.copy()
    if "broker_candle_time" in chart.columns:
        chart["broker_candle_time"] = pd.to_datetime(chart["broker_candle_time"], errors="coerce")
        chart = chart.set_index("broker_candle_time")
    st.line_chart(chart[columns])
