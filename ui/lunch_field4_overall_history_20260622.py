"""Compatibility renderer for Field 4 overall Full Metric history."""
from __future__ import annotations
from typing import Any, Mapping, MutableMapping
import pandas as pd


def render_overall_history(state: MutableMapping[str, Any], canonical: Mapping[str, Any]) -> None:
    import streamlit as st
    from ui.lunch_four_core_fields_20260619 import _metric_result, _history_25day, _display_clock_frame

    result = _metric_result(state)
    history = result.get("history") if isinstance(result, Mapping) else None
    if not isinstance(history, pd.DataFrame) or history.empty:
        records = canonical.get("full_metric_history") if isinstance(canonical, Mapping) else None
        history = pd.DataFrame.from_records(records) if isinstance(records, list) else pd.DataFrame()
    history = _history_25day(history) if isinstance(history, pd.DataFrame) and not history.empty else pd.DataFrame()
    st.markdown("#### Overall Full Metric History — Last 25 Days")
    if history.empty:
        st.info("No published Full Metric history is available for the active canonical generation.")
        return
    st.dataframe(_display_clock_frame(history, state=state, broker_clock=True), use_container_width=True, hide_index=True, height=480)


__all__ = ["render_overall_history"]
