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
    """Glass overlay sidebar + the app-wide glass finish.

    UI overhaul (user order 2026-11-16). The previous policy CSS
    forced the sidebar open (``display:block`` + ``min-width:340px``
    with ``!important``), which defeated Streamlit's collapse on
    desktop -- the sidebar could not be closed on a laptop. Now:

    * no forced display/width on the sidebar, so the native
      collapse control works on every device;
    * the sidebar is ``position:fixed`` and the main section keeps
      the full width, so an open sidebar OVERLAYS the dashboard
      instead of pushing it aside;
    * the sidebar surface is translucent glass (backdrop blur) --
      the dashboard shows through it;
    * the sidebar content keeps its own vertical scroll, so every
      control is reachable while it is open;
    * the collapsed-state reopen control is glass-styled and kept
      on top;
    * the same glass language is applied app-wide (cards, buttons,
      inputs, metrics, expanders) so the app reads as one product.
    """
    init_sidebar_policy()
    st.markdown(
        """
<style id="new7-glass-overlay-sidebar-20261116">
/* ---- Sidebar: closable, overlaying, glass ---- */
section[data-testid="stSidebar"]{
  position:fixed!important;top:0!important;left:0!important;
  height:100vh!important;max-height:100vh!important;
  z-index:999990!important;
  background:
    linear-gradient(155deg,rgba(255,255,255,.34),rgba(186,230,253,.20) 48%,rgba(255,255,255,.14))!important;
  backdrop-filter:blur(28px) saturate(180%)!important;
  -webkit-backdrop-filter:blur(28px) saturate(180%)!important;
  border-right:1px solid rgba(255,255,255,.45)!important;
  box-shadow:16px 0 48px rgba(15,23,42,.12),inset -1px 0 0 rgba(255,255,255,.25)!important;
}
section[data-testid="stSidebar"]>div:first-child,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"]{background:transparent!important;}
section[data-testid="stSidebar"] [data-testid="stSidebarContent"]{
  overflow-y:auto!important;max-height:100vh!important;
}
section[data-testid="stSidebar"] .block-container{padding:1rem .85rem 2rem!important;background:rgba(255,255,255,.05)!important;}
section[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"],
section[data-testid="stSidebar"] [data-testid="stExpander"]{
  background:rgba(255,255,255,.16)!important;
  border-color:rgba(255,255,255,.36)!important;
  box-shadow:0 12px 30px rgba(14,116,144,.08),inset 0 1px 0 rgba(255,255,255,.34)!important;
  backdrop-filter:blur(18px) saturate(160%)!important;
  -webkit-backdrop-filter:blur(18px) saturate(160%)!important;
}
/* Main keeps the full width whether the sidebar is open or not:
   the sidebar floats over it. */
section[data-testid="stMain"]{margin-left:0!important;width:100%!important;}
/* The reopen control (visible while the sidebar is collapsed)
   stays reachable and wears the same glass. */
div[data-testid="stSidebarCollapsedControl"]{
  z-index:999991!important;
  background:rgba(255,255,255,.55)!important;
  backdrop-filter:blur(12px) saturate(160%)!important;
  -webkit-backdrop-filter:blur(12px) saturate(160%)!important;
  border:1px solid rgba(255,255,255,.6)!important;
  border-radius:0 12px 12px 0!important;
  box-shadow:4px 4px 16px rgba(15,23,42,.10)!important;
}
/* Streamlit automatically renders every module in pages/ as a second
   navigation rail.  This app has its own single Field 3 workspace and its
   own Settings controls, so the generated page list is redundant noise. */
div[data-testid="stSidebarNav"]{display:none!important;visibility:hidden!important;height:0!important;min-height:0!important;overflow:hidden!important;}
body,html,.stApp{overflow-x:hidden!important;}

/* ---- App-wide glass finish (main area) ---- */
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"]{
  background:rgba(255,255,255,.45)!important;
  border:1px solid rgba(255,255,255,.60)!important;
  border-radius:14px!important;
  box-shadow:0 8px 24px rgba(15,23,42,.06)!important;
  backdrop-filter:blur(12px) saturate(150%)!important;
  -webkit-backdrop-filter:blur(12px) saturate(150%)!important;
}
[data-testid="stMain"] [data-testid="stExpander"]{
  background:rgba(255,255,255,.40)!important;
  border:1px solid rgba(255,255,255,.55)!important;
  border-radius:12px!important;
  backdrop-filter:blur(10px) saturate(150%)!important;
  -webkit-backdrop-filter:blur(10px) saturate(150%)!important;
}
.stButton>button,.stDownloadButton>button{
  background:rgba(255,255,255,.55)!important;
  border:1px solid rgba(255,255,255,.70)!important;
  border-radius:10px!important;
  box-shadow:0 2px 8px rgba(15,23,42,.08)!important;
  backdrop-filter:blur(8px) saturate(150%)!important;
  -webkit-backdrop-filter:blur(8px) saturate(150%)!important;
}
.stButton>button:hover,.stDownloadButton>button:hover{
  background:rgba(255,255,255,.78)!important;
}
[data-testid="stMetric"]{
  background:rgba(255,255,255,.45)!important;
  border:1px solid rgba(255,255,255,.55)!important;
  border-radius:12px!important;
  padding:6px 10px!important;
}
div[data-testid="stTextInput"] input,div[data-testid="stTextArea"] textarea{
  background:rgba(255,255,255,.65)!important;
  border-radius:10px!important;
}
[data-testid="stMain"] h2,[data-testid="stMain"] h3{
  letter-spacing:.01em!important;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_policy_status() -> None:
    """Compatibility status without controls or a sidebar reopen action."""
    init_sidebar_policy()
    inject_sidebar_policy_css()
    st.caption("Settings controls are available in the sidebar.")
