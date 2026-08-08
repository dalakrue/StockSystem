"""Stable main-page menu replacing native-sidebar dependency (2026-06-15).

The app is fully navigated and controlled from this main-page drawer.
The native Streamlit sidebar is permanently removed.
"""
from __future__ import annotations

import time
import streamlit as st


def _safe_rerun() -> None:
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def _soft_menu_css() -> None:
    st.markdown(
        """
<style id="new7-main-page-menu-antd-20260615">
.new7-card{
  border:1px solid rgba(99,102,241,.13);
  border-radius:20px;
  padding:11px 12px;
  margin:.20rem 0 .55rem 0;
  background:linear-gradient(135deg,rgba(255,255,255,.83),rgba(239,246,255,.68));
  box-shadow:0 10px 26px rgba(15,23,42,.055);
}
.new7-menu-note{font-size:.76rem;color:#64748b;line-height:1.28;}
.new7-liquid-drawer{max-width:min(360px,92vw);margin-left:auto;border:1px solid rgba(99,102,241,.13);border-radius:18px;padding:.5rem;background:rgba(255,255,255,.92);}
@media(max-width:430px){
  .new7-card{border-radius:16px;padding:9px 10px;margin:.15rem 0 .42rem 0;box-shadow:none;}
  .new7-liquid-drawer{max-width:min(310px,88vw);padding:.35rem;border-radius:14px;} 
  div[data-testid="stExpander"] details{border-radius:16px!important;}
  div[data-testid="stButton"] button{min-height:38px!important;font-size:.78rem!important;padding:.18rem .35rem!important;}
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _sync_status() -> None:
    try:
        from ui.antd_navigation_20260615 import render_active_nav_status
        render_active_nav_status()
    except Exception:
        page = st.session_state.get("active_page", "Settings")
        sub = st.session_state.get("active_subpage", "")
        st.caption(f"Active page: {page} | Subpage: {sub or 'Main'}")


def _open_lunch_after_calculation() -> None:
    st.session_state.update({
        "active_page": "Field 3",
        "tab_choice": "Field 3",
        "active_subpage": "",
        "lunch_active_subpage": "",
        "lunch_bi_visual_ready": True,
        "show_restored_powerbi_20260617": True,
        "load_original_powerbi_from_antd_lunch_20260615": True,
        "settings_auto_open_lunch_20260617": True,
        "lunch_calculation_completed_notice_20260621": True,
    })


def _render_quick_actions() -> None:
    """Menu refresh only. The only two copy controls live at Lunch top."""
    st.markdown("#### ⚡ Quick Controls")
    if st.button("🔄 Refresh Data Only", key="main_menu_refresh_data_20260621", use_container_width=True):
        try:
            from core.app.refresh import refresh_data
            result = refresh_data(st.session_state)
            if result.get("status") == "SUCCESS":
                st.success(str(result.get("message") or "Data refreshed. Run a Settings calculation to publish Field 3."))
            elif result.get("status") == "WARNING":
                st.warning(str(result.get("message") or "Data refreshed with warnings."))
            else:
                st.error(str(result.get("message") or "Data refresh failed."))
        except Exception as exc:
            st.error(f"Refresh failed safely: {exc}")
    st.caption("The Global Symbol control remains available across Settings, Field 3.")


def render_main_menu_drawer(current_tab: str | None = None) -> str:
    """Liquid-glass app drawer.

    Hidden by default. Opens from the top ☰ button and replaces the bulky
    always-open controls above the page tabs. It is normal Streamlit UI, so no
    no native sidebar is used; the drawer is ordinary main-page Streamlit UI.
    """
    _soft_menu_css()
    try:
        from ui.liquid_glass_theme_20260615 import apply_liquid_glass_theme
        apply_liquid_glass_theme()
    except Exception:
        pass
    pages = {"Settings", "Field 3"}
    if current_tab and current_tab in pages:
        st.session_state.setdefault("active_page", current_tab)
    st.session_state.setdefault("active_page", st.session_state.get("tab_choice", "Settings"))
    st.session_state.setdefault("active_subpage", "")
    # Persistent floating application bar: the only interactive symbol selector
    # remains visible across every page, even while the drawer itself is closed.
    try:
        from ui.global_symbol_control_v2 import render_global_symbol_control
        render_global_symbol_control(st, compact=True)
    except Exception as global_symbol_exc:
        st.session_state["global_symbol_control_error_v2"] = f"{type(global_symbol_exc).__name__}: {global_symbol_exc}"
    if not bool(st.session_state.get("new7_main_menu_drawer_open", False) or st.session_state.get("menu_open", False)):
        return st.session_state.get("active_page", st.session_state.get("tab_choice", "Settings"))

    st.markdown('<div class="new7-liquid-drawer">', unsafe_allow_html=True)
    top_a, top_b = st.columns([5, 1])
    with top_a:
        st.markdown('<div class="new7-liquid-drawer-title"><div><b>⋮ Liquid Glass App Drawer</b><br><span style="color:#64748b;font-size:.78rem;font-weight:750;">Two-tab navigation only: Settings and Field 3.</span></div></div>', unsafe_allow_html=True)
    with top_b:
        if st.button("✕ Close", key="liquid_close_app_drawer_20260615", use_container_width=True):
            st.session_state["new7_main_menu_drawer_open"] = False
            st.session_state["menu_open"] = False
            st.session_state["ui_navigation_click_ts"] = time.time()
            _safe_rerun()

    # Reduced app contract: this drawer is navigation only. Provider controls
    # remain in Settings; no Connector, Timer, Copy, AI, or UI utility pages are
    # exposed from the menu.
    st.markdown('<div class="new7-liquid-section">', unsafe_allow_html=True)
    try:
        from ui.antd_navigation_20260615 import safe_antd_navigation
        safe_antd_navigation("antd_liquid_drawer_navigation")
    except Exception as exc:
        st.warning("Navigation component unavailable; using the safe two-page selector.")
        st.caption(f"Navigation fallback reason: {exc}")
        page_list = ["Settings", "Field 3"]
        current = st.session_state.get("active_page", "Settings")
        idx = page_list.index(current) if current in page_list else 0
        page = st.selectbox("Choose tab", page_list, index=idx, key="hard_fallback_nav_liquid_20260615")
        from core.navigation_authority_20260625 import navigate_to
        navigate_to(st.session_state, page, "")
    _sync_status()
    st.caption("Menu contains tab choice only: Settings and Field 3.")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)
    return st.session_state.get("active_page", st.session_state.get("tab_choice", "Settings"))
