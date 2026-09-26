import time
import streamlit as st

from core.common import DEFAULT_TABS, log_event
from core.styles import request_close_sidebar
from core.ui_relationship import mark_navigation, sync_shared_connection_signature
from core.ui.effects import queue_ui_popup
from core.data_connectors import manual_connect
from core.websocket_feed import render_websocket_panel, websocket_status
from core.system_upgrade import sidebar_health_card, add_snapshot_button
from core.system_contract import render_sidebar_mini_contract, record_system_event
from core.system_relations import render_system_relation_hub
from core.global_upgrade import render_sidebar_upgrade_panel, render_sidebar_pro_header, data_quality, get_live_df
from core.ui.compact import render_metric_cards
from core.full_system_upgrade import render_sidebar_v21_top, queue_popup, build_copy_payload
from core.light_auth_20260612 import render_auth_status_sidebar
from ui.sidebar_hard_lock import native_sidebar_disabled, inject_sidebar_policy_css

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    def st_autorefresh(*args, **kwargs):
        return None


from .timer import _sidebar_timer_panel
from .state import _init_sidebar_state, _safe_log_event, _normalize_symbol, _set_mode, _open_tab
from .timer import _safe_rerun
from .connection import _connect_now
from .panels import _priority_rank, _sidebar_download_center, _disconnect_shared_state, _sidebar_deep_sync_from_shared, _sidebar_one_click_console


def _sidebar_reversal_top_panel():
    """Sidebar V17: keep 10-Reversal status at the top before connector controls."""
    try:
        import pandas as pd
        score = st.session_state.get("last_reversal_score", st.session_state.get("reversal_score", 0))
        engine = st.session_state.get("last_reversal_engine", {})
        if isinstance(engine, dict):
            score = engine.get("active_count", score)
        try:
            score_i = int(round(float(score or 0)))
        except Exception:
            score_i = 0
        scan = st.session_state.get("home_reversal_25d_scan")
        low_count = 0
        high_count = 0
        if isinstance(scan, pd.DataFrame) and not scan.empty:
            col = "10_reversal_score" if "10_reversal_score" in scan.columns else "active_count" if "active_count" in scan.columns else "score" if "score" in scan.columns else None
            if col:
                vals = pd.to_numeric(scan[col], errors="coerce")
                low_count = int((vals <= 3).sum())
                high_count = int((vals >= 8).sum())
        with st.expander("🚨 Top 10-Reversal status", expanded=False):
            c1, c2, c3 = st.columns(3)
            c1.metric("Now", f"{score_i}/10")
            c2.metric("≤3 Calm", low_count)
            c3.metric("8+ Locked", high_count)
            st.caption("Sidebar placement upgraded: reverse-decision status appears before connector/settings sections. Full tables remain at the top of Lunch.")
    except Exception:
        pass

def sidebar_nav():
    """Clean native-sidebar menu only.

    2026-06-15 final: the old duplicated sidebar blocks (API/timer/copy/status)
    are removed from the native sidebar to stop UI conflict and lower RAM/CPU.
    The sidebar now displays only the same Liquid Menu as the top popup and
    writes to active_page/tab_choice. Heavy controls remain in main-page menu
    or Settings, not duplicated here.
    """
    _init_sidebar_state()
    try:
        inject_sidebar_policy_css()
    except Exception:
        pass
    current = st.session_state.get("active_page", st.session_state.get("tab_choice", DEFAULT_TABS[0] if DEFAULT_TABS else "Settings"))
    try:
        from ui.liquid_menu_popup_20260615 import render_sidebar_liquid_menu_only
        page = render_sidebar_liquid_menu_only(current)
        return page
    except Exception as exc:
        # Ultra-safe fallback: menu only, no previous duplicated sidebar sections.
        pages = ["Settings", "Field 3"]
        if current == "Home" or current not in pages:
            current = "Settings"
        with st.sidebar:
            st.markdown("### ⋮ Liquid Menu")
            st.caption("Clean sidebar fallback. Old duplicated sections are removed.")
            page = st.selectbox("Page", pages, index=pages.index(current), key="sidebar_clean_menu_fallback_20260615")
            if page != st.session_state.get("active_page"):
                st.session_state["active_page"] = page
                st.session_state["tab_choice"] = page
                st.session_state["active_subpage"] = ""
                st.session_state["ui_navigation_click_ts"] = time.time()
                st.session_state["fast_tab_switch_active"] = True
                _safe_rerun()
            with st.expander("Sidebar fallback status", expanded=False):
                st.caption(f"Liquid sidebar helper skipped safely: {exc}")
        return st.session_state.get("active_page", page)

