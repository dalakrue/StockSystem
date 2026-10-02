"""Sidebar policy for the single-page Field 3 application.

Settings now lives in Streamlit's native sidebar.  The old main-page drawer
flags remain as compatibility state but no longer hide the sidebar.
"""
from __future__ import annotations

import streamlit as st

NATIVE_SIDEBAR_DISABLED_KEY = "new7_native_sidebar_disabled_20260614"
NATIVE_SIDEBAR_STATUS_KEY = "new7_native_sidebar_status_20260614"
MAIN_DRAWER_KEY = "new7_main_menu_drawer_open"
LEGACY_DRAWER_KEY = "menu_open"
SOFT_HIDDEN_KEY = "new7_native_sidebar_soft_hidden_20260617"


def init_sidebar_policy() -> None:
    st.session_state[NATIVE_SIDEBAR_DISABLED_KEY] = False
    st.session_state[SOFT_HIDDEN_KEY] = False
    st.session_state[NATIVE_SIDEBAR_STATUS_KEY] = "Native sidebar enabled for Settings controls."
    st.session_state.setdefault(MAIN_DRAWER_KEY, False)
    st.session_state.setdefault(LEGACY_DRAWER_KEY, False)
    st.session_state["use_native_sidebar_fallback_20260619"] = True
    for key in ("sidebar_force_hidden_20260614", "sidebar_close_requested_20260614", "sidebar_close_requested_native_only"):
        st.session_state[key] = True


def native_sidebar_disabled() -> bool:
    init_sidebar_policy()
    return False


def soft_sidebar_hidden() -> bool:
    init_sidebar_policy()
    return False


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
    """Keep the native sidebar open and sized for the Settings controls."""
    init_sidebar_policy()
    st.markdown(
        """
<style id="new7-native-sidebar-enabled-20260823">
section[data-testid="stSidebar"]{display:block!important;visibility:visible!important;min-width:340px!important;max-width:420px!important;}
/* Final water-glass pass: the page behind the sidebar remains visible while
   controls retain a readable frosted surface. */
section[data-testid="stSidebar"]{
  background:
    linear-gradient(155deg,rgba(255,255,255,.22),rgba(186,230,253,.13) 48%,rgba(255,255,255,.08))!important;
  backdrop-filter:blur(28px) saturate(180%)!important;
  -webkit-backdrop-filter:blur(28px) saturate(180%)!important;
  border-right:1px solid rgba(255,255,255,.42)!important;
  box-shadow:16px 0 48px rgba(15,23,42,.10),inset -1px 0 0 rgba(255,255,255,.25)!important;
}
section[data-testid="stSidebar"]>div:first-child,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"]{background:transparent!important;}
section[data-testid="stSidebar"] .block-container{padding:1rem .85rem 2rem!important;background:rgba(255,255,255,.06)!important;}
section[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"],
section[data-testid="stSidebar"] [data-testid="stExpander"]{
  background:rgba(255,255,255,.14)!important;
  border-color:rgba(255,255,255,.34)!important;
  box-shadow:0 12px 30px rgba(14,116,144,.08),inset 0 1px 0 rgba(255,255,255,.34)!important;
  backdrop-filter:blur(18px) saturate(160%)!important;
  -webkit-backdrop-filter:blur(18px) saturate(160%)!important;
}
/* Streamlit automatically renders every module in pages/ as a second
   navigation rail.  This app has its own single Field 3 workspace and its
   own Settings controls, so the generated page list is redundant noise. */
div[data-testid="stSidebarNav"]{display:none!important;visibility:hidden!important;height:0!important;min-height:0!important;overflow:hidden!important;}
body,html,.stApp{overflow-x:hidden!important;}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_policy_status() -> None:
    """Compatibility status without controls or a sidebar reopen action."""
    init_sidebar_policy()
    inject_sidebar_policy_css()
    st.caption("Settings controls are available in the sidebar.")
