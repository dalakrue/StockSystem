"""Read-only compatibility view for Field 3 priority synchronization."""
from __future__ import annotations
from typing import Any, MutableMapping


def render_priority_sync_v9(state: MutableMapping[str, Any]) -> None:
    import streamlit as st
    from core.canonical_lookup_20260626 import resolve_canonical
    from ui.lunch_four_core_fields_20260619 import _current_priority_table

    canonical = resolve_canonical(state)
    table = _current_priority_table(state, canonical)
    with st.expander("Open / Close — Field 3 Priority Synchronization", expanded=False):
        st.caption("Read-only priority evidence from the active canonical run; no recalculation is performed.")
        if table.empty:
            st.info("No canonical priority table is published for the active generation.")
            return
        st.dataframe(table, use_container_width=True, hide_index=True, height=360)


__all__ = ["render_priority_sync_v9"]
