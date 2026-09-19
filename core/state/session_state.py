"""Session-state bootstrap and repair logic.

This file is intentionally small and stable. It is the safest place to add
future app-wide state defaults without touching tabs or connectors.
"""

import uuid
import pandas as pd
import streamlit as st

from core.config.defaults import SESSION_DEFAULTS, LIST_STATE_KEYS, DICT_STATE_KEYS


def _fresh_default(value):
    if isinstance(value, list):
        return []
    if isinstance(value, dict):
        return {}
    if value is None:
        return None
    try:
        # DataFrame default is handled separately below to avoid pandas import
        # surprises in app startup.
        if hasattr(value, "copy") and value.__class__.__name__ == "DataFrame":
            return value.copy()
    except Exception:
        pass
    return value


def init_state():
    # Avoid a hard pandas object in config defaults while preserving the old
    # public state key used by websocket consumers.
    defaults = dict(SESSION_DEFAULTS)
    if defaults.get("ws_ticks") is None:
        defaults["ws_ticks"] = pd.DataFrame()

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = _fresh_default(value)

    repair_state()

    if not bool(st.session_state.get("startup_route_initialized_20260617", False)):
        st.session_state["active_page"] = "Settings"
        st.session_state["tab_choice"] = "Settings"
        st.session_state["active_subpage"] = ""
        st.session_state["startup_route_initialized_20260617"] = True

    if not st.session_state.get("system_boot_id"):
        try:
            st.session_state["system_boot_id"] = uuid.uuid4().hex[:12]
        except Exception:
            st.session_state["system_boot_id"] = "boot"

    if not st.session_state.get("system_boot_time"):
        try:
            st.session_state["system_boot_time"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            st.session_state["system_boot_time"] = ""


def repair_state():
    for key in LIST_STATE_KEYS:
        if not isinstance(st.session_state.get(key), list):
            st.session_state[key] = []
    for key in DICT_STATE_KEYS:
        if not isinstance(st.session_state.get(key), dict):
            st.session_state[key] = {}


def log_event(msg):
    try:
        if "activity_log" not in st.session_state or not isinstance(st.session_state.activity_log, list):
            st.session_state.activity_log = []
        st.session_state.activity_log.insert(
            0,
            {
                "time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                "event": str(msg),
            },
        )
        st.session_state.activity_log = st.session_state.activity_log[:500]
    except Exception:
        pass


def is_phone_mode():
    return bool(st.session_state.get("phone_mode", False))
