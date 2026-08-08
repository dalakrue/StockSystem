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

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    def st_autorefresh(*args, **kwargs):
        return None


def _safe_log_event(message):
    try:
        log_event(message)
    except Exception:
        st.session_state.setdefault("activity_log", [])
        st.session_state.activity_log.insert(0, str(message))

def _init_sidebar_state():
    st.session_state.setdefault("tab_choice", DEFAULT_TABS[0] if DEFAULT_TABS else "Settings")
    if st.session_state.tab_choice not in DEFAULT_TABS:
        st.session_state.tab_choice = DEFAULT_TABS[0] if DEFAULT_TABS else "Settings"
    st.session_state.setdefault("phone_mode", False)
    st.session_state.setdefault("connector_mode", "mt5")
    st.session_state.setdefault("timeframe", "M1")
    st.session_state.setdefault("connector_bars", 600)
    st.session_state.setdefault("allow_safe_demo", False)

def _normalize_symbol(symbol):
    return str(symbol or "XAUUSD").strip().upper().replace(" ", "").replace("/", "")

def _set_mode(phone_mode: bool):
    st.session_state.phone_mode = bool(phone_mode)
    queue_ui_popup("UI mode changed", "Phone layout" if phone_mode else "Laptop layout", "success")
    request_close_sidebar()

def _open_tab(tab):
    # Fast navigation path: no connector refresh, no heavy maintenance, no data rebuild.
    # Existing tab logic remains unchanged; this only marks the rerun as UI-only.
    st.session_state.tab_choice = tab
    st.session_state["ui_navigation_click_ts"] = time.time()
    st.session_state["fast_tab_switch_active"] = True
    mark_navigation(tab)
    _safe_log_event(f"Open tab: {tab}")
    queue_ui_popup("Tab opened", str(tab), "info")
    request_close_sidebar()



# Compatibility helper: older refactor pieces imported _safe_rerun from state.py.
# Keep this thin wrapper so both old and new imports work safely.
def _safe_rerun():
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass
