"""Lightweight Other workspace containing only the independent Pre-Original tool."""
import importlib
import streamlit as st

try:
    from core.global_upgrade import render_page_shell, render_tab_footer
except Exception:
    def render_page_shell(title, subtitle="", icon=""):
        st.markdown(f"# {icon} {title}")
        if subtitle: st.caption(subtitle)
    def render_tab_footer(title): return None

INNER_TABS = [("Pre Original", "🧾", "tabs.pre_original")]

def _choose_inner_tab():
    st.session_state["other_inner_tab"] = "Pre Original"
    return "Pre Original"

def _render_inner_page(name: str):
    module_name = dict((n, m) for n, _i, m in INNER_TABS).get(name)
    if not module_name:
        st.warning("Unknown inner tab."); return
    try:
        return getattr(importlib.import_module(module_name), "show")()
    except Exception as exc:
        st.error(f"{name} inner tab could not run safely.")
        with st.expander(f"Show {name} error", expanded=True): st.exception(exc)

def show():
    render_page_shell("Other", "Independent API-free manual-input workspace.", "📂")
    selected = _choose_inner_tab()
    # Route before any canonical/API/Settings readiness check. Pre-Original is independent.
    _render_inner_page(selected)
    render_tab_footer("Other")
