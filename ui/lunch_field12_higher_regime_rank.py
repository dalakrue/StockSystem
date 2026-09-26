"""Lunch Field 12 — fundamental-only multi-symbol news/NLP rank."""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

import pandas as pd
import streamlit as st

from core.field12_fundamental_nlp_20260722 import CSV_KEY, META_KEY, TABLE_KEY

FIELD12_LABEL = "12. Open / Close — Multi-Symbol Fundamental News NLP Rank"


def render_field12(state: MutableMapping[str, Any] | None = None) -> None:
    """Display the saved Settings publication; never fetch/calculate on open."""
    state = state if state is not None else st.session_state
    st.markdown("## Field 12 — Multi-Symbol Fundamental News NLP Rank")
    st.caption(
        "Ranks only the symbols that were actually loaded. Bias and rank use recent, "
        "high-relevance symbol/currency news, freshness, absorption and NLP sentiment. "
        "Technical indicators and Field 10 utility do not influence this table."
    )
    try:
        from core.canonical_symbol_selection_20260709 import filter_frame_for_symbol, render_selector
        selected, _, _ = render_selector(
            st, state, surface="field12",
            title="Field 12 Loaded-Symbol Selector — Fundamental Evidence",
            expanded=True,
        )
    except Exception as exc:
        selected = str(state.get("canonical_display_symbol_20260709") or "")
        st.caption(f"Field 12 selector unavailable: {type(exc).__name__}: {exc}")

    table = state.get(TABLE_KEY)
    meta = state.get(META_KEY) if isinstance(state.get(META_KEY), Mapping) else {}
    if not isinstance(table, pd.DataFrame) or table.empty:
        st.info("No saved Field 12 fundamental publication exists. Load symbols and run a Settings calculation once.")
        return

    selected_view = filter_frame_for_symbol(table, selected) if selected else pd.DataFrame()
    row = selected_view.iloc[0].to_dict() if not selected_view.empty else table.iloc[0].to_dict()
    cards = st.columns(5)
    cards[0].metric("Selected", str(row.get("Symbol") or selected or "UNAVAILABLE"))
    cards[1].metric("Fundamental rank", str(row.get("Fundamental Rank") or "—"))
    cards[2].metric("News bias", str(row.get("Fundamental Bias") or "WAIT"))
    cards[3].metric("News score", str(row.get("Fundamental News Score") or "—"))
    cards[4].metric("Permission", str(row.get("News Permission") or "WAIT"))
    st.info(
        f"Latest relevant news: {row.get('Latest High-Impact Symbol News') or 'NEWS_UNAVAILABLE'} · "
        f"sentiment: {row.get('News Sentiment') or 'UNAVAILABLE'} · "
        f"source: {row.get('NLP Evidence Source') or 'UNAVAILABLE'}"
    )
    st.caption(
        f"Run: {meta.get('parent_run_id') or 'UNAVAILABLE'} · Snapshot: {meta.get('snapshot_hash') or 'UNAVAILABLE'} · "
        f"Timeframe: {meta.get('timeframe') or 'UNAVAILABLE'} · Build rule: NEWS/NLP ONLY · Tab-open calculation: NO"
    )
    st.dataframe(table, use_container_width=True, hide_index=True, height=min(650, 110 + 38 * len(table)))
    csv_data = state.get(CSV_KEY)
    if not isinstance(csv_data, (bytes, bytearray)):
        csv_data = table.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Field 12 fundamental news rank CSV",
        data=csv_data,
        file_name="field12_multi_symbol_fundamental_news_nlp_rank.csv",
        mime="text/csv",
        use_container_width=True,
        key="field12_fundamental_news_rank_download_20260722",
    )


__all__ = ["FIELD12_LABEL", "render_field12"]
