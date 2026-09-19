"""Legacy facade for the one database-backed global symbol identity.

This module intentionally renders no selector. The only interactive display
selector is ``ui.global_symbol_control_v2`` in the persistent application bar.
"""
from __future__ import annotations
from collections.abc import MutableMapping
from typing import Any


def render_global_symbol_selector(
    state: MutableMapping[str, Any], *, key_prefix: str,
    auto_refresh_library: bool = True, show_refresh_status: bool = True,
) -> str:
    del key_prefix, auto_refresh_library
    import streamlit as st
    from core.canonical_symbol_selection_20260709 import render_identity_strip
    symbol = render_identity_strip(st, state, surface="legacy_global_selector")
    if show_refresh_status:
        refresh = state.get("last_refresh_result_20260621")
        if isinstance(refresh, dict):
            st.caption(f"Latest saved refresh: {refresh.get('status', 'NOT RUN')} · no fetch was triggered by this view")
    return symbol


__all__ = ["render_global_symbol_selector"]
