"""Additive UI/UX relationship layer for all tabs.

This module does not replace original trading logic. It standardizes the
relationship between sidebar navigation, main tabs, inner tabs, connection state,
and shared helper functions so every page reads the same session state.
"""

from __future__ import annotations

import time
from typing import Any, Dict

import streamlit as st


def init_ui_relationship_state() -> None:
    defaults: Dict[str, Any] = {
        "ui_active_path": "Home",
        "ui_last_tab": "Home",
        "ui_last_inner": "",
        "ui_transition_active": False,
        "ui_transition_ts": 0.0,
        "ui_popup_queue": [],
        "ui_density_level": "balanced",
        "ui_show_command_bar": True,
        "shared_connection_epoch": 0,
        "shared_connection_signature": "DISCONNECTED|XAUUSD|M1|0",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def mark_navigation(target: str, inner: str = "") -> None:
    target = str(target or "Home")
    inner = str(inner or "")
    st.session_state["ui_last_tab"] = target
    st.session_state["ui_last_inner"] = inner
    st.session_state["ui_active_path"] = f"{target} / {inner}" if inner else target
    st.session_state["ui_transition_active"] = True
    st.session_state["ui_transition_ts"] = time.time()
    st.session_state["ui_navigation_click_ts"] = time.time()
    st.session_state["ui_navigation_target"] = st.session_state["ui_active_path"]


def sync_shared_connection_signature() -> str:
    df = st.session_state.get("last_df")
    try:
        rows = len(df) if df is not None else 0
    except Exception:
        rows = 0
    signature = "|".join([
        str(st.session_state.get("source", "DISCONNECTED")),
        str(st.session_state.get("symbol", "XAUUSD")),
        str(st.session_state.get("timeframe", "M1")),
        str(rows),
    ])
    old = st.session_state.get("shared_connection_signature")
    if signature != old:
        st.session_state["shared_connection_signature"] = signature
        st.session_state["shared_connection_epoch"] = int(st.session_state.get("shared_connection_epoch", 0) or 0) + 1
    return signature


def render_transition_popup() -> None:
    ts = float(st.session_state.get("ui_transition_ts", 0) or 0)
    if not ts:
        return
    age = time.time() - ts
    if age > 2.2:
        st.session_state["ui_transition_active"] = False
        return
    path = str(st.session_state.get("ui_active_path", "Home"))
    st.markdown(
        f"""
        <div class="qx-toast qx-toast-show">
            <div class="qx-toast-dot"></div>
            <div><b>Opened</b><br><span>{path}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_command_bar(tab_name: str) -> None:
    if not bool(st.session_state.get("ui_show_command_bar", True)):
        return
    sync_shared_connection_signature()
    df = st.session_state.get("last_df")
    try:
        rows = len(df) if df is not None else 0
    except Exception:
        rows = 0
    source = st.session_state.get("source", "DISCONNECTED")
    symbol = st.session_state.get("symbol", "XAUUSD")
    tf = st.session_state.get("timeframe", "M1")
    epoch = st.session_state.get("shared_connection_epoch", 0)
    inner = st.session_state.get("ui_last_inner", "") or "selected section"
    st.markdown(
        f"""
        <div class="qx-command-bar">
          <div class="qx-command-left">
            <span class="qx-pill-blue">{tab_name}</span>
            <span><b>{symbol}</b> / {tf}</span>
            <span>{source}</span>
            <span>{rows:,} rows</span>
          </div>
          <div class="qx-command-right">
            <span>Data v{epoch}</span>
            <span>{inner}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_relation_footer(tab_name: str) -> None:
    df = st.session_state.get("last_df")
    try:
        rows = len(df) if df is not None else 0
    except Exception:
        rows = 0
    connected = bool(st.session_state.get("connected", False)) and rows > 0
    status = "shared data ready" if connected else "waiting for sidebar connection"
    st.markdown(
        f"""
        <div class="qx-relation-footer">
          <b>Relationship check:</b> Sidebar connector → shared session dataframe → {tab_name} tab → selected inner section. 
          Current status: <span>{status}</span>.
        </div>
        """,
        unsafe_allow_html=True,
    )
