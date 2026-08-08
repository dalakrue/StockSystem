"""Compact UI helpers for deduplicated Streamlit pages.

These helpers intentionally render lightweight HTML cards instead of many
`st.metric` calls. They keep the dashboard readable on phone and laptop while
avoiding repeated metric blocks across Home, Sidebar, Engine, Train Data,
Database, and Profile.
"""
from __future__ import annotations

from html import escape
from typing import Iterable, Mapping, Any

import streamlit as st


def _fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        if isinstance(value, float):
            return f"{value:,.5f}".rstrip("0").rstrip(".")
        if isinstance(value, int):
            return f"{value:,}"
    except Exception:
        pass
    return str(value)


def render_metric_cards(items: Iterable[Mapping[str, Any]], *, class_name: str = "dedup-metric-grid") -> None:
    """Render a compact responsive card row without creating Streamlit metrics.

    Expected item keys: label, value, delta/detail. Missing keys are safe.
    """
    cards = []
    for item in items or []:
        label = escape(_fmt(item.get("label", "Metric")))
        value = escape(_fmt(item.get("value", "N/A")))
        delta = escape(_fmt(item.get("delta", item.get("detail", ""))))
        cards.append(
            f"<div class='dedup-metric-card'><b>{label}</b><span>{value}</span>"
            + (f"<small>{delta}</small>" if delta else "")
            + "</div>"
        )
    if not cards:
        return
    st.markdown(f"<div class='{escape(class_name)}'>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def render_section_note(title: str, body: str = "") -> None:
    st.markdown(
        f"""
        <div class="dedup-note-card">
          <b>{escape(str(title))}</b>
          <span>{escape(str(body))}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
