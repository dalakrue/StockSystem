"""Mobile-safe single-field selector and persistent navigation controls."""
from __future__ import annotations

import streamlit as st

from lunch.registry import FIELD_REGISTRY, ordered_field_ids

SELECTED_KEY = "lunch_selected_field_v11"
OPEN_KEY = "lunch_selected_field_open_v11"
PENDING_SELECTED_KEY = "lunch_selected_field_pending_v11"


def _initialize(options: list[str]) -> None:
    # Pending navigation is consumed before the selectbox is instantiated.
    # Streamlit forbids changing a widget-owned session key later in the same
    # rerun, which previously made Previous/Next vulnerable to the same
    # StreamlitAPIException as the multi-symbol selector.
    pending = st.session_state.pop(PENDING_SELECTED_KEY, None)
    current = str(pending or st.session_state.get(SELECTED_KEY) or options[0])
    if current not in options:
        current = options[0]
    st.session_state[SELECTED_KEY] = current
    st.session_state.setdefault(OPEN_KEY, True)


def render_field_navigation() -> tuple[str, bool]:
    """Render controls outside field boundaries so they cannot disappear."""
    options = ordered_field_ids()
    _initialize(options)
    selected = st.selectbox(
        "Open Lunch Field",
        options=options,
        format_func=lambda field_id: (
            f"Field {FIELD_REGISTRY[field_id].order} — "
            f"{FIELD_REGISTRY[field_id].title}"
        ),
        key=SELECTED_KEY,
    )
    index = options.index(selected)

    previous_col, next_col = st.columns(2)
    if previous_col.button(
        "Previous Field",
        use_container_width=True,
        disabled=index == 0,
        key="lunch_previous_field_v11",
    ):
        st.session_state[PENDING_SELECTED_KEY] = options[index - 1]
        st.session_state[OPEN_KEY] = True
        st.rerun()
    if next_col.button(
        "Next Field",
        use_container_width=True,
        disabled=index == len(options) - 1,
        key="lunch_next_field_v11",
    ):
        st.session_state[PENDING_SELECTED_KEY] = options[index + 1]
        st.session_state[OPEN_KEY] = True
        st.rerun()

    open_col, close_col = st.columns(2)
    if open_col.button("Open Field", use_container_width=True, key="lunch_open_field_v11"):
        st.session_state[OPEN_KEY] = True
    if close_col.button("Close Field", use_container_width=True, key="lunch_close_field_v11"):
        st.session_state[OPEN_KEY] = False
    return str(st.session_state[SELECTED_KEY]), bool(st.session_state[OPEN_KEY])


__all__ = ["render_field_navigation", "SELECTED_KEY", "OPEN_KEY", "PENDING_SELECTED_KEY"]
