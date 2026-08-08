"""Universal UI/UX helpers for the Quant app.

This file is additive: it does not replace any original tab logic.  It gives every
page the same readable header, connection strip, data-quality hints, and empty
state cards so the app feels consistent on laptop and phone.
"""

from __future__ import annotations

from typing import Any
import time
import pandas as pd
import streamlit as st


def _safe_len_df(obj: Any) -> int:
    try:
        if obj is None:
            return 0
        return int(len(obj))
    except Exception:
        return 0


def _fmt_age(seconds: float) -> str:
    try:
        seconds = max(0, float(seconds))
    except Exception:
        seconds = 0
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    return f"{seconds / 3600:.1f}h ago"


def _last_timestamp(df: Any) -> str:
    try:
        if df is None or len(df) == 0:
            return "N/A"
        for col in ["time", "datetime", "timestamp", "date"]:
            if col in df.columns:
                v = df[col].iloc[-1]
                return str(v)[:19]
        if isinstance(df.index, pd.DatetimeIndex):
            return str(df.index[-1])[:19]
        return "Loaded"
    except Exception:
        return "N/A"


def render_universal_header(tab_name: str):
    """Render a compact status header above every tab."""
    symbol = str(st.session_state.get("symbol", "XAUUSD") or "XAUUSD")
    source = str(st.session_state.get("source", "DISCONNECTED") or "DISCONNECTED")
    connected = bool(st.session_state.get("connected", False))
    timeframe = str(st.session_state.get("timeframe", "M1") or "M1")
    df = st.session_state.get("last_df")
    rows = _safe_len_df(df)
    last_fetch = float(st.session_state.get("last_fetch", 0) or 0)
    age = _fmt_age(time.time() - last_fetch) if last_fetch else "not refreshed"
    mode = "Phone" if bool(st.session_state.get("phone_mode", False)) else "Wide"
    status_cls = "qx-ok" if connected and rows > 0 else "qx-off"
    status_text = "LIVE / READY" if connected and rows > 0 else "DISCONNECTED"

    st.markdown(
        f"""
        <div class="qx-page-head">
            <div class="qx-title-wrap">
                <div class="qx-kicker">{tab_name} workspace</div>
                <div class="qx-title">⚡ M1 ADX Quant Pro</div>
                <div class="qx-subtitle">{symbol} • {timeframe} • {mode} layout • last update {age}</div>
            </div>
            <div class="qx-status {status_cls}">{status_text}</div>
        </div>
        <div class="qx-strip">
            <div><b>Source</b><span>{source}</span></div>
            <div><b>Rows</b><span>{rows:,}</span></div>
            <div><b>Last Candle</b><span>{_last_timestamp(df)}</span></div>
            <div><b>Auto Refresh</b><span>10 min</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_data_quality_card():
    """Small global diagnostic card shown when data is missing or stale."""
    df = st.session_state.get("last_df")
    rows = _safe_len_df(df)
    connected = bool(st.session_state.get("connected", False))
    last_fetch = float(st.session_state.get("last_fetch", 0) or 0)
    stale = bool(last_fetch and (time.time() - last_fetch) > 1800)

    if connected and rows > 0 and not stale:
        return

    if not connected or rows == 0:
        title = "No shared market dataframe yet"
        body = "Use the sidebar Quick Refresh or Connector settings once. All tabs will reuse that same data after it loads."
        kind = "warning"
    else:
        title = "Data may be stale"
        body = "The last refresh is older than 30 minutes. Press Quick Refresh before making decisions from the analytics panels."
        kind = "alert"

    st.markdown(
        f"""
        <div class="qx-empty qx-{kind}">
            <b>{title}</b><br>
            <span>{body}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_mobile_hint_once():
    if not bool(st.session_state.get("phone_mode", False)):
        return
    if st.session_state.get("uiux_mobile_hint_seen"):
        return
    st.session_state.uiux_mobile_hint_seen = True
    st.info("Phone mode is active: metric rows stay compact and wide tables can scroll sideways.")
