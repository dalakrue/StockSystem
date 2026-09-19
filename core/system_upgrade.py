"""
Non-destructive global upgrade layer for all tabs.
Adds shared market header, websocket health, dataframe guard, and quick diagnostics.
Original tab code is not replaced; app_shell calls these helpers before loading each tab.
"""
from __future__ import annotations

import time
from typing import Any, Dict

import pandas as pd
import streamlit as st

try:
    from core.data_connectors import _normalize_ohlc, manual_connect
except Exception:
    _normalize_ohlc = None
    manual_connect = None


def _safe_len(df: Any) -> int:
    try:
        return len(df) if isinstance(df, pd.DataFrame) else 0
    except Exception:
        return 0


def _age_text(ts: Any) -> str:
    try:
        if not ts:
            return "never"
        sec = max(0, int(time.time() - float(ts)))
        if sec < 60:
            return f"{sec}s ago"
        if sec < 3600:
            return f"{sec//60}m {sec%60}s ago"
        return f"{sec//3600}h {(sec%3600)//60}m ago"
    except Exception:
        return "unknown"


def get_shared_market_df() -> pd.DataFrame:
    df = st.session_state.get("last_df")
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    if _normalize_ohlc is None:
        return df.copy()
    try:
        return _normalize_ohlc(df)
    except Exception:
        return df.copy()


def ensure_safe_market_data() -> pd.DataFrame:
    """Return the current shared market dataframe without silently creating demo data.

    Earlier builds tried to auto-connect from the global status bar, which could
    create SAFE_DEMO candles and make a trading screen look usable when live data
    was not actually available. This version is safer: only explicit connector
    buttons load data.
    """
    return get_shared_market_df()


def render_global_status_bar(tab_name: str = "") -> None:
    """Collapsed global status and pulse for faster decision reading."""
    df = ensure_safe_market_data()
    rows = _safe_len(df)
    source = st.session_state.get("source", "DISCONNECTED")
    symbol = st.session_state.get("symbol", "XAUUSD")
    tf = st.session_state.get("timeframe", "M1")
    last_fetch = _age_text(st.session_state.get("last_fetch", 0))

    ws = {"enabled": False, "runtime_connected": False, "queued_ticks": 0, "last_message_age": None, "last_error": ""}
    try:
        from core.websocket_feed import websocket_status
        ws = websocket_status()
    except Exception:
        pass

    live = "LIVE" if ws.get("runtime_connected") else ("ON" if ws.get("enabled") else "OFF")
    age = ws.get("last_message_age")
    tick_age = "-" if age is None else f"{round(float(age), 1)}s"
    connected = source != "DISCONNECTED" and rows > 0
    dot_cls = "ws-dot-live" if connected else "ws-dot-off"

    st.markdown(
        f"""
        <div class="ws-live-card compact-status-line">
            <b>📡 {symbol}</b> • {tf} • <b>{source}</b> • <b>{rows:,}</b> rows • fetch <b>{last_fetch}</b> • WS <b>{live}</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("📊 Open shared status + Global Market Pulse", expanded=False):
        st.markdown(
            f"""
            <div class="ws-live-card">
                <b>📡 Shared System Status</b> &nbsp; <span class="{dot_cls}"></span>
                <b>{symbol}</b> • {tf} • Source: <b>{source}</b> • Rows: <b>{rows:,}</b> • Last fetch: <b>{last_fetch}</b><br>
                <small>Tab: {tab_name or st.session_state.get('tab_choice','Home')} • Websocket: <b>{live}</b> • queued ticks: <b>{ws.get('queued_ticks',0)}</b> • tick age: <b>{tick_age}</b></small>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if ws.get("last_error"):
            st.caption(f"Websocket note: {ws.get('last_error')}")
        render_market_pulse("global")


def _pct(a: float, b: float) -> float:
    try:
        if b == 0 or pd.isna(a) or pd.isna(b):
            return 0.0
        return (float(a) - float(b)) / max(abs(float(b)), 1e-12) * 100.0
    except Exception:
        return 0.0


def market_pulse(df: pd.DataFrame) -> Dict[str, Any]:
    """Small, safe analysis layer used by every tab.
    It never trades and never blocks original code; it only reads the shared dataframe.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty or "close" not in df.columns:
        return {"bias": "WAIT", "score": 0, "status": "No shared candle data", "change": 0.0, "volatility": 0.0}

    d = df.copy().tail(300)
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["close"])
    if len(d) < 10:
        return {"bias": "WAIT", "score": 0, "status": "Need more candles", "change": 0.0, "volatility": 0.0}

    close = d["close"]
    change_5 = _pct(close.iloc[-1], close.iloc[-min(6, len(close))])
    change_20 = _pct(close.iloc[-1], close.iloc[-min(21, len(close))]) if len(close) >= 21 else change_5
    ret = close.pct_change().replace([float("inf"), float("-inf")], 0).fillna(0)
    volatility = float(ret.tail(60).std() * 100.0) if len(ret) else 0.0

    pressure = 0.0
    if "+di" in d.columns and "-di" in d.columns:
        pressure = float(pd.to_numeric(d["+di"], errors="coerce").iloc[-1] - pd.to_numeric(d["-di"], errors="coerce").iloc[-1])
    elif "pressure" in d.columns:
        pressure = float(pd.to_numeric(d["pressure"], errors="coerce").iloc[-1])

    score = 0
    score += 1 if change_5 > 0 else -1 if change_5 < 0 else 0
    score += 1 if change_20 > 0 else -1 if change_20 < 0 else 0
    score += 1 if pressure > 0 else -1 if pressure < 0 else 0

    if score >= 2:
        bias = "BUY pressure"
    elif score <= -2:
        bias = "SELL pressure"
    else:
        bias = "WAIT / mixed"

    if abs(change_20) > 0.35 and volatility > 0.05:
        status = "High movement — manage margin and avoid over-entry"
    elif abs(change_20) > 0.15:
        status = "One-side pressure possible"
    else:
        status = "Normal / mixed movement"

    return {
        "bias": bias,
        "score": score,
        "status": status,
        "change": round(float(change_20), 4),
        "volatility": round(float(volatility), 4),
        "pressure": round(float(pressure), 4),
    }


def render_market_pulse(location: str = "global") -> None:
    df = get_shared_market_df()
    pulse = market_pulse(df)
    cols = st.columns(5)
    cols[0].metric("Pulse Bias", pulse.get("bias", "WAIT"))
    cols[1].metric("Pulse Score", pulse.get("score", 0))
    cols[2].metric("20-candle %", pulse.get("change", 0.0))
    cols[3].metric("Volatility %", pulse.get("volatility", 0.0))
    cols[4].metric("DI Pressure", pulse.get("pressure", 0.0))
    st.caption(f"Global pulse: {pulse.get('status','')}. This is shared across all tabs and does not replace your original strategy logic.")


def sidebar_health_card() -> None:
    df = get_shared_market_df()
    rows = _safe_len(df)
    connected = bool(st.session_state.get("connected", False))
    source = st.session_state.get("source", "DISCONNECTED")
    st.markdown(
        f'''
        <div class="glass-card compact-hero">
            <b>🩺 Health</b><br>
            <small>Status: {'Connected' if connected else 'Not connected'} • Source: {source} • Rows: {rows:,}</small>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def add_snapshot_button(location: str = "global") -> None:
    st.caption("✅ Runtime snapshots auto-save in the backend. Manual snapshot button removed to avoid duplicate Save controls.")
