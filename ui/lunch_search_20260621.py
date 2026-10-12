"""Mobile-friendly Enter-to-search form for cached Lunch data."""
from __future__ import annotations

from typing import Any, MutableMapping

import pandas as pd
import streamlit as st

from core.generation_identity_20260707 import numeric_generation

from core.lunch_search_20260621 import remember_search, search_cached_lunch


def render_lunch_search(*, state: MutableMapping[str, Any] | None = None) -> None:
    state = state if state is not None else st.session_state
    st.markdown("### 🔎 Search Lunch and 25-Day History")
    st.caption("Search reads the published canonical result and normalized history only. It never runs the trading calculation.")
    with st.form("lunch_search_form_20260621", clear_on_submit=False, border=True):
        query = st.text_input(
            "Search",
            value=str(state.get("lunch_search_query_20260621") or ""),
            placeholder="Examples: last BEAR_NORMAL, exit risk above 7, XGBoost disagreement",
            key="lunch_search_input_20260621",
            help="Type a query and press Enter or select Search.",
        )
        submitted = st.form_submit_button("Search", use_container_width=True)
    if submitted:
        state["lunch_search_query_20260621"] = query
        remember_search(state, query)
        try:
            state["lunch_search_results_20260621"] = search_cached_lunch(query, state)
            state.pop("lunch_search_error_20260621", None)
        except Exception as exc:
            state["lunch_search_results_20260621"] = pd.DataFrame()
            state["lunch_search_error_20260621"] = f"{type(exc).__name__}: {exc}"
            try:
                from core.regime_trust_store_20260621 import record_component_error
                canonical = state.get("canonical_decision_result") or {}
                record_component_error(
                    component="Lunch Search", run_id=str(canonical.get("run_id") or ""),
                    calculation_generation=numeric_generation(canonical.get("calculation_generation") or canonical.get("generation_id"), default=1),
                    exception=exc, fallback_used=True,
                )
            except Exception:
                pass
    error = state.get("lunch_search_error_20260621")
    if error:
        st.error("Search could not read one optional history source. The last valid trading result remains available.")
        with st.expander("Technical search detail", expanded=False):
            st.code(str(error))
    results = state.get("lunch_search_results_20260621")
    active_query = str(state.get("lunch_search_query_20260621") or "").strip()
    if isinstance(results, pd.DataFrame) and active_query:
        if results.empty:
            st.info(f'No cached result matched “{active_query}”. Try a metric, regime, timestamp, run ID, model, warning, or numeric condition.')
        else:
            phone = bool(state.get("phone_mode", False))
            display = results.copy()
            if phone:
                preferred = ["Score", "Source", "Field / Path", "Value", "Timestamp"]
                display = display[[column for column in preferred if column in display.columns]]
            st.dataframe(display, use_container_width=True, hide_index=True, height=min(520, 100 + 30 * min(len(display), 14)))
            st.caption(f"{len(results)} ranked cached matches. Exact matches appear before partial matches; every row identifies its source field or table.")
    recent = list(state.get("lunch_recent_searches_20260621") or [])
    if recent:
        st.caption("Recent searches: " + " · ".join(recent))


__all__ = ["render_lunch_search"]
