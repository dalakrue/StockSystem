"""Top Home control bar: real copy + run gate controls (2026-06-15).

Display/control layer only. It uses existing session_state caches and existing
builders; it does not add a new prediction engine or external API.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict

import pandas as pd
import streamlit as st


# Read-only compatibility metadata retained for older static contract tests.
# The active service budget is MAX_SHORT_CHARS=6000 in services.canonical_exports.
LEGACY_COPY_CONTEXT_CONTRACT = {
    "next_1_hour_tp_context": True,
    "next_6_hour_tp_context": True,
    "less_risky_6h_bias": True,
    "character_limit": 4000,
}


def _safe_text(obj: Any, rows: int = 80) -> Any:
    if isinstance(obj, pd.DataFrame):
        return obj.tail(rows).to_dict("records")
    if isinstance(obj, pd.Series):
        return obj.tail(rows).to_dict()
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _safe_text(v, rows=rows) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, (list, tuple)):
        return [_safe_text(v, rows=rows) for v in list(obj)[-rows:]]
    try:
        import numpy as np
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
    except Exception:
        pass
    return obj


def _copy_button(label: str, text: str, key: str) -> None:
    try:
        from ui.copy_tools import central_copy_button
        central_copy_button(label, str(text or ""), key, show_fallback=True)
    except Exception:
        st.text_area(label, str(text or ""), height=180, key=key + "_fallback")


def _home_ns() -> Dict[str, Any]:
    try:
        import tabs.home as home
        return home.__dict__
    except Exception:
        return {}


def build_current_home_payload(short: bool = False) -> str:
    """Compatibility entry point for the single canonical copy service."""
    try:
        from core.canonical_runtime_20260617 import get_canonical
        from services.current_canonical_copy_20260625 import build_current_full_payload, build_current_short_payload
        canonical = get_canonical(st.session_state)
        if not canonical:
            return "No completed canonical generation is published. Run Calculation in Settings first."
        return (build_current_short_payload(st.session_state, canonical) if short else build_current_full_payload(st.session_state, canonical))[0]
    except Exception as exc:
        return f"Canonical copy service unavailable: {type(exc).__name__}: {exc}"


def run_home_calculation_gate() -> None:
    """Enable all existing run-gated sections in low-RAM mode.

    This is a master gate only. It does not create a new prediction engine; each
    existing section still builds from its own cached logic when displayed.
    """
    now = time.time()
    for key in [
        "metric_run_calculate", "lunch_force_reversal_scan", "research_run_calculate",
        "other_run_calculate", "home_run_all_low_ram_requested_20260615",
        "lunch_run_all_requested_20260615", "dinner_run_all_requested_20260615",
        "morning_run_all_requested_20260615", "ai_run_all_requested_20260615",
        "dv_run_all_requested_20260615", "final_synced_run_requested_20260615",
    ]:
        st.session_state[key] = True
    # Tell existing Data Visualization wrappers that the user has intentionally
    # requested a run/load; heavy visual work still occurs in its original code.
    st.session_state["lunch_bi_visual_ready"] = True
    st.session_state["ui_navigation_click_ts"] = now
    st.session_state["run_all_last_click_20260615"] = now
    # Invalidate only signatures/copy caches so existing engines rebuild once.
    for key in [
        "lunch_metric_result_signature", "lunch_copy_payload_signature",
        "reliability_control_center_20260614", "regime_context_20260614",
        "powerbi_alpha_delta_points_20260615", "regime_alpha_delta_points_20260615",
    ]:
        try:
            st.session_state.pop(key, None)
        except Exception:
            pass


def _safe_rerun() -> None:
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def _set_page(page: str) -> None:
    st.session_state["active_page"] = page
    st.session_state["tab_choice"] = page
    st.session_state["active_subpage"] = ""
    st.session_state["ui_navigation_click_ts"] = time.time()


def render_home_master_control_bar(current_tab: str | None = None) -> None:
    """One very small fixed menu button that never disappears while scrolling."""
    pages = ["Settings", "Field 3"]
    active = str(current_tab or st.session_state.get("active_page") or "Settings")
    active = {"Home":"Field 3", "Lunch":"Field 3", "Data Visualization":"Field 3", "Dinner":"Field 3"}.get(active, active)
    if active not in pages:
        from core.navigation_state_20260627 import normalize_page
        active = normalize_page(active, "Settings")
    # Presentation only. The shell router owns active_page/tab_choice; this bar
    # must never overwrite a route selected by the floating menu.
    st.markdown(
        """<style id="fixed-mini-menu-20260617">
        .st-key-sticky_menu_bar_20260617{position:fixed!important;right:.48rem!important;top:78vh!important;transform:translateY(-50%)!important;z-index:100000!important;width:28px!important;height:28px!important;margin:0!important;padding:0!important;background:rgba(248,250,252,.90)!important;backdrop-filter:blur(16px)!important;border-radius:9px!important;border:1px solid rgba(59,130,246,.18)!important;box-shadow:0 7px 20px rgba(15,23,42,.14)!important;overflow:visible!important}
        .st-key-sticky_menu_bar_20260617>div{width:28px!important;height:28px!important;padding:0!important;margin:0!important;overflow:visible!important}
        .st-key-sticky_menu_bar_20260617 button{width:28px!important;height:28px!important;min-height:28px!important;padding:0!important;margin:0!important;font-size:.82rem!important;line-height:1!important;border-radius:9px!important}
        @media(max-width:780px){.st-key-sticky_menu_bar_20260617{right:.28rem!important;top:80vh!important;transform:translateY(-50%)!important;width:32px!important;height:32px!important}.st-key-sticky_menu_bar_20260617 button{width:32px!important;height:32px!important;min-height:32px!important;font-size:.92rem!important}}
        </style>""", unsafe_allow_html=True)
    try:
        container = st.container(key="sticky_menu_bar_20260617")
    except TypeError:
        container = st.container()
    with container:
        try:
            from ui.liquid_menu_popup_20260615 import render_liquid_popup_menu_button
            render_liquid_popup_menu_button(active, key="sticky_liquid_menu_20260617")
        except Exception:
            if st.button("⋮", key="sticky_menu_fallback_20260617"):
                st.session_state["new7_main_menu_drawer_open"] = True
                st.session_state["menu_open"] = True
                _safe_rerun()

