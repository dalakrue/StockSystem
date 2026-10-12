"""Shared lightweight Lunch search state."""
from __future__ import annotations
import streamlit as st


def render_search() -> str:
    return st.text_input(
        "Search current field history",
        key="lunch_shared_search_v11",
        placeholder="Decision, regime, session, run ID, date…",
        help="Filtering is read-only and never reruns calculations.",
    ).strip()
