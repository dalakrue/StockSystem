"""Permanent no-sidebar policy requested on 2026-06-19.

Navigation remains available through the main-page Liquid Glass App Drawer.
This module exists only for backward-compatible imports; it never exposes or
reopens Streamlit's native sidebar.
"""
from __future__ import annotations

import streamlit as st

NATIVE_SIDEBAR_DISABLED_KEY = "new7_native_sidebar_disabled_20260614"
NATIVE_SIDEBAR_STATUS_KEY = "new7_native_sidebar_status_20260614"
MAIN_DRAWER_KEY = "new7_main_menu_drawer_open"
LEGACY_DRAWER_KEY = "menu_open"
SOFT_HIDDEN_KEY = "new7_native_sidebar_soft_hidden_20260617"


def init_sidebar_policy() -> None:
    st.session_state[NATIVE_SIDEBAR_DISABLED_KEY] = True
    st.session_state[SOFT_HIDDEN_KEY] = True
    st.session_state[NATIVE_SIDEBAR_STATUS_KEY] = "Native sidebar permanently removed; use the main-page menu."
    st.session_state.setdefault(MAIN_DRAWER_KEY, False)
    st.session_state.setdefault(LEGACY_DRAWER_KEY, False)
    st.session_state["use_native_sidebar_fallback_20260619"] = False
    for key in ("sidebar_force_hidden_20260614", "sidebar_close_requested_20260614", "sidebar_close_requested_native_only"):
        st.session_state[key] = True


def native_sidebar_disabled() -> bool:
    init_sidebar_policy()
    return True


def soft_sidebar_hidden() -> bool:
    init_sidebar_policy()
    return True


def hide_native_sidebar() -> None:
    init_sidebar_policy()


def show_native_sidebar() -> None:
    """Backward-compatible no-op: native sidebar cannot be reopened."""
    init_sidebar_policy()


def disable_native_sidebar(reason: str = "Native sidebar permanently removed.") -> None:
    del reason
    init_sidebar_policy()


def enable_native_sidebar_backup() -> None:
    """Backward-compatible no-op retained for old imports."""
    init_sidebar_policy()


def open_main_drawer() -> None:
    init_sidebar_policy()
    st.session_state[MAIN_DRAWER_KEY] = True
    st.session_state[LEGACY_DRAWER_KEY] = True


def close_main_drawer() -> None:
    init_sidebar_policy()
    st.session_state[MAIN_DRAWER_KEY] = False
    st.session_state[LEGACY_DRAWER_KEY] = False


def inject_sidebar_policy_css() -> None:
    """Remove the native sidebar and collapsed-sidebar button at every width."""
    init_sidebar_policy()
    st.markdown(
        """
<style id="new7-native-sidebar-removed-20260619">
section[data-testid="stSidebar"],
[data-testid="stSidebar"],
[data-testid="stSidebarNav"],
[data-testid="stSidebarCollapsedControl"],
button[data-testid="stSidebarCollapsedControl"],
div[data-testid="stSidebarCollapsedControl"]{
  display:none!important;
  visibility:hidden!important;
  width:0!important;
  min-width:0!important;
  max-width:0!important;
  height:0!important;
  overflow:hidden!important;
  pointer-events:none!important;
}
[data-testid="stAppViewContainer"]>.main,
[data-testid="stAppViewContainer"] main,
.main{
  margin-left:0!important;
  max-width:100%!important;
}
body,html,.stApp,.main .block-container{max-width:100vw!important;overflow-x:hidden!important;}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_policy_status() -> None:
    """Compatibility status without controls or a sidebar reopen action."""
    init_sidebar_policy()
    inject_sidebar_policy_css()
    st.caption("Native sidebar removed. Use the three-dot main-page menu for navigation and controls.")
