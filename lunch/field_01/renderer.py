"""Field 1 display wrapper over the preserved Full Metric history renderer."""
from __future__ import annotations
import streamlit as st


def render(view_model) -> None:
    context = view_model["context"]
    st.markdown("### Field 1 — Full Metric History")
    st.caption(f"Run {context.snapshot.run_id} · broker time {context.snapshot.broker_candle_time.isoformat()}")
    from ui.lunch_four_core_fields_20260619 import _render_full_metric_history
    _render_full_metric_history(context.history_repository.state)
    st.markdown("---")
    st.markdown("#### Direction Confirmation History — Last 25 Broker Days")
    from ui.lunch_one_hour_direction_20260626 import render_for_field
    render_for_field(context.history_repository.state, 1)
