"""No-JavaScript native sidebar compatibility layer (2026-06-15).

Older modules imported these names. They are now safe state updates so no code
tries to click private Streamlit sidebar DOM controls.
"""
from __future__ import annotations

import streamlit as st


def request_open_native_sidebar() -> None:
    try:
        from ui.sidebar_hard_lock import enable_native_sidebar_backup
        enable_native_sidebar_backup()
    except Exception:
        pass
    st.session_state["new7_native_sidebar_status_20260614"] = "Native sidebar backup unlocked. Use Streamlit's own control if needed; navigation is in Main Page Menu."


def request_close_native_sidebar() -> None:
    try:
        from ui.sidebar_hard_lock import disable_native_sidebar
        disable_native_sidebar("Native sidebar backup disabled. Use Main Page Menu for reliable navigation.")
    except Exception:
        pass
    st.session_state["new7_native_sidebar_status_20260614"] = "Native sidebar backup disabled. Main Page Menu remains active."


def request_toggle_native_sidebar() -> None:
    try:
        from ui.sidebar_hard_lock import native_sidebar_disabled
        if native_sidebar_disabled():
            request_open_native_sidebar()
        else:
            request_close_native_sidebar()
    except Exception:
        request_open_native_sidebar()
