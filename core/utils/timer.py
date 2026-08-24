"""Timer helpers for sidebar and trading workflow."""

import time
import streamlit as st

from core.utils.numeric import safe_float


def format_timer(seconds):
    try:
        seconds = max(0, int(seconds))
    except Exception:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def remaining_time():
    end = st.session_state.get("timer_end_time") or st.session_state.get("trade_end_time")
    if not end:
        return 0
    try:
        return max(0, int(float(end) - time.time()))
    except Exception:
        return 0


def remaining_seconds():
    return remaining_time()


def start_timer(minutes=None):
    from core.state.session_state import log_event

    if minutes is None:
        minutes = st.session_state.get("timer_minutes", 120)
    minutes = safe_float(minutes, 120)
    minutes = max(1, min(minutes, 1440))
    end_time = time.time() + minutes * 60
    st.session_state.timer_minutes = int(minutes)
    st.session_state.timer_end_time = end_time
    st.session_state.trade_end_time = end_time
    st.session_state.trade_timer_running = True
    log_event(f"Timer started: {minutes} minutes")
    return end_time


def stop_timer():
    from core.state.session_state import log_event

    st.session_state.timer_end_time = None
    st.session_state.trade_end_time = None
    st.session_state.trade_timer_running = False
    log_event("Timer stopped")
