"""Persistent four-step Global Symbol control for the reduced application.

The control selects only successfully loaded/completed symbols.  Loading saved
Field 3 evidence, activating the display identity and opening the data surface
are explicit independent steps.  No provider request or heavy calculation is
triggered by this component.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from core.global_symbol_context import (
    get_global_symbol_context,
    loaded_selector_options,
    restore_latest_context,
    select_active_display_symbol,
)

GLOBAL_WIDGET_KEY = "global_symbol_widget_v2"
GLOBAL_APPLY_KEY = "global_symbol_apply_v2"
GLOBAL_RELOAD_KEY = "global_symbol_reload_v2"
GLOBAL_SETTINGS_KEY = "global_symbol_open_settings_v2"
GLOBAL_LOAD_STEP_KEY = "global_symbol_step2_loaded_v3"
GLOBAL_ACTIVATE_STEP_KEY = "global_symbol_step3_activated_v3"
GLOBAL_LAST_SELECTION_KEY = "global_symbol_step1_selection_v3"
GLOBAL_STATUS_KEY = "global_symbol_four_step_status_v3"


def _rerun(st: Any) -> None:
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def _go(state: Any, page: str) -> None:
    state.update({
        "active_page": page,
        "tab_choice": page,
        "requested_page": page,
        "requested_subpage": "",
        "active_subpage": "",
    })


def _ranking_has_symbol(state: Any, symbol: str) -> bool:
    ranking = state.get("field3_multisymbol_regime_20260708")
    return bool(
        isinstance(ranking, pd.DataFrame)
        and not ranking.empty
        and "Symbol" in ranking.columns
        and ranking["Symbol"].astype(str).str.upper().eq(str(symbol).upper()).any()
    )


def _load_saved_symbol_evidence(state: Any, context: Any, symbol: str) -> dict[str, Any]:
    """Reload exact saved generation and verify the selected symbol is present."""
    try:
        from core.field3_three_regime_engine import load_saved_field3_v2
        report = load_saved_field3_v2(state, context=context)
    except Exception as exc:
        return {
            "ok": False,
            "status": "SAVED_EVIDENCE_LOAD_FAILED",
            "symbol": symbol,
            "error": f"{type(exc).__name__}: {exc}",
            "provider_calls": 0,
            "calculation_calls": 0,
        }
    if not _ranking_has_symbol(state, symbol):
        return {
            "ok": False,
            "status": "SELECTED_SYMBOL_HAS_NO_COMPLETED_FIELD3_EVIDENCE",
            "symbol": symbol,
            "message": "The symbol is loaded but its completed Field 3 evidence is unavailable. Run a Settings calculation.",
            "provider_calls": 0,
            "calculation_calls": 0,
            **dict(report or {}),
        }
    return {
        "ok": True,
        "status": "SELECTED_SYMBOL_SAVED_EVIDENCE_LOADED",
        "symbol": symbol,
        "rank_rows": int((report or {}).get("rank_rows") or 0),
        "evidence_rows": int((report or {}).get("evidence_rows") or 0),
        "provider_calls": 0,
        "calculation_calls": 0,
    }


def _render_control_body(st: Any, *, compact: bool) -> str:
    state = st.session_state
    context = get_global_symbol_context(state)
    if not context.universe_id:
        context = restore_latest_context(state)
    options = loaded_selector_options(context)

    st.markdown("#### 🌐 Global Multi-Symbol Selector")
    st.caption("Four independent steps: select → load saved evidence → activate globally → show symbol data.")
    if not options:
        st.warning("No successfully loaded symbol is available. Configure and load symbols in Settings first; default symbols are not inserted here.")
        if st.button("1. Open Settings", key=GLOBAL_SETTINGS_KEY, use_container_width=True):
            _go(state, "Settings")
            _rerun(st)
        return ""

    active = context.active_display_symbol if context.active_display_symbol in options else ""
    current = state.get(GLOBAL_WIDGET_KEY)
    if current not in options:
        state[GLOBAL_WIDGET_KEY] = active if active in options else options[0]
    selected = st.selectbox(
        "1. Select a loaded symbol",
        options=options,
        key=GLOBAL_WIDGET_KEY,
        help="Only symbols successfully loaded/completed in the published multi-symbol universe are selectable.",
    )

    previous_selection = str(state.get(GLOBAL_LAST_SELECTION_KEY) or "")
    if previous_selection != selected:
        state[GLOBAL_LAST_SELECTION_KEY] = selected
        state.pop(GLOBAL_LOAD_STEP_KEY, None)
        state.pop(GLOBAL_ACTIVATE_STEP_KEY, None)
        state[GLOBAL_STATUS_KEY] = {
            "status": "STEP_1_SELECTED",
            "symbol": selected,
            "provider_calls": 0,
            "calculation_calls": 0,
        }

    loaded_step = str(state.get(GLOBAL_LOAD_STEP_KEY) or "") == selected
    activated_step = str(state.get(GLOBAL_ACTIVATE_STEP_KEY) or "") == selected and context.active_display_symbol == selected

    load_clicked = st.button(
        "2. Load Selected Symbol Evidence",
        key=GLOBAL_RELOAD_KEY,
        use_container_width=True,
        help="Reloads the exact saved generation only. It does not call Twelve Data, Finnhub, MT5, or any calculation engine.",
    )
    if load_clicked:
        report = _load_saved_symbol_evidence(state, context, selected)
        state[GLOBAL_STATUS_KEY] = report
        if report.get("ok"):
            state[GLOBAL_LOAD_STEP_KEY] = selected
            state.pop(GLOBAL_ACTIVATE_STEP_KEY, None)
        else:
            state.pop(GLOBAL_LOAD_STEP_KEY, None)
            state.pop(GLOBAL_ACTIVATE_STEP_KEY, None)
        _rerun(st)

    activate_clicked = st.button(
        "3. Activate Symbol Globally",
        key=GLOBAL_APPLY_KEY,
        use_container_width=True,
        disabled=not loaded_step,
        help="Updates the one database-backed display identity used by Field 3.",
    )
    if activate_clicked:
        try:
            updated = select_active_display_symbol(selected, state=state)
            state[GLOBAL_ACTIVATE_STEP_KEY] = updated.active_display_symbol
            state[GLOBAL_STATUS_KEY] = {
                "ok": True,
                "status": "STEP_3_ACTIVATED_GLOBALLY",
                "symbol": updated.active_display_symbol,
                "provider_calls": 0,
                "calculation_calls": 0,
            }
        except Exception as exc:
            state.pop(GLOBAL_ACTIVATE_STEP_KEY, None)
            state[GLOBAL_STATUS_KEY] = {
                "ok": False,
                "status": "GLOBAL_ACTIVATION_FAILED",
                "symbol": selected,
                "error": f"{type(exc).__name__}: {exc}",
                "provider_calls": 0,
                "calculation_calls": 0,
            }
        _rerun(st)

    # Refresh after any prior rerun/DB activation.
    context = get_global_symbol_context(state)
    activated_step = str(state.get(GLOBAL_ACTIVATE_STEP_KEY) or "") == selected and context.active_display_symbol == selected
    show_clicked = st.button(
        "4. Show Symbol Data",
        key="global_symbol_show_data_v3",
        use_container_width=True,
        disabled=not activated_step,
        help="Opens Field 3 using the activated global symbol.",
    )
    if show_clicked:
        target = "Field 3"
        _go(state, target)
        state[GLOBAL_STATUS_KEY] = {
            "ok": True,
            "status": "STEP_4_SHOWING_SYMBOL_DATA",
            "symbol": selected,
            "page": target,
            "provider_calls": 0,
            "calculation_calls": 0,
        }
        _rerun(st)

    step_cols = st.columns(4)
    step_cols[0].metric("Select", "✓" if selected else "—")
    step_cols[1].metric("Load", "✓" if loaded_step else "—")
    step_cols[2].metric("Activate", "✓" if activated_step else "—")
    step_cols[3].metric("Show", "Ready" if activated_step else "Locked")
    st.caption(
        f"Active: {context.active_display_symbol or '—'} · Timeframe: {context.timeframe or '—'} · "
        f"Loaded choices: {len(options)} · Generation: {context.generation or '—'}"
    )
    status = state.get(GLOBAL_STATUS_KEY)
    if isinstance(status, dict):
        text = str(status.get("error") or status.get("message") or status.get("status") or "")
        if status.get("ok") is False:
            st.error(text)
        elif text:
            st.success(text)
    return context.active_display_symbol


def render_global_symbol_control(st: Any, *, compact: bool = True) -> str:
    """Render one persistent floating global selector across all three tabs."""
    state = st.session_state
    st.markdown(
        """
        <style id="global-symbol-floating-v3">
        .st-key-global_symbol_floating_control_v3{
          position:fixed!important; right:3.15rem!important; top:.55rem!important;
          z-index:100001!important; width:auto!important; max-width:92vw!important;
          margin:0!important; padding:0!important;
        }
        .st-key-global_symbol_floating_control_v3 button{
          min-height:34px!important; border-radius:12px!important; font-weight:800!important;
          box-shadow:0 8px 24px rgba(15,23,42,.16)!important;
        }
        @media(max-width:780px){
          .st-key-global_symbol_floating_control_v3{right:2.9rem!important;top:.38rem!important;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    try:
        container = st.container(key="global_symbol_floating_control_v3")
    except TypeError:
        container = st.container()
    with container:
        if hasattr(st, "popover"):
            with st.popover("🌐 Symbols", use_container_width=False):
                return _render_control_body(st, compact=compact)
        with st.expander("🌐 Global Symbols", expanded=False):
            return _render_control_body(st, compact=compact)
    return get_global_symbol_context(state).active_display_symbol


__all__ = ["render_global_symbol_control", "GLOBAL_WIDGET_KEY"]
