"""Standalone Field 3 page for the reduced three-tab application."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import streamlit as st


def show(runtime_context: Mapping[str, Any] | None = None) -> None:
    del runtime_context
    state = st.session_state
    st.title("Field 3 — Multi-Symbol Regime Ranking")
    try:
        from core.canonical_symbol_selection_20260709 import render_identity_strip
        render_identity_strip(st, state, surface="field3_standalone")
    except Exception:
        pass
    try:
        from ui.field3_multisymbol_regime_summary_20260722 import render_multisymbol_regime_summary
        render_multisymbol_regime_summary(st, state)
    except Exception as exc:
        state["field3_summary_render_error_20260722"] = f"{type(exc).__name__}: {exc}"
        st.error(f"The all-symbol summary could not render safely: {type(exc).__name__}: {exc}")
    if bool(state.get("field3_fast_two_table_mode_20260722")) or str(state.get("field3_last_run_scope_20260722") or "").upper() == "LUNCH_CORE":
        return
    st.divider()
    try:
        from ui.field3_three_regime_panel import render_field3_three_regime_panel
        render_field3_three_regime_panel(st, state)
    except Exception as exc:
        state["field3_detail_render_error_20260722"] = f"{type(exc).__name__}: {exc}"
        st.error(f"Field 3 selected-symbol detail could not render safely: {type(exc).__name__}: {exc}")


__all__ = ["show"]
