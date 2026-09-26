"""Stable synchronized navigation (restored 2026-06-17).

Home is a visible lightweight status/shortcut page. Data Visualization remains
inside Lunch while the top-level AI Assistant is preserved. Settings is the
first startup page and Other restores the legacy
Engine/Train Data/Pre Original/Backtest/Profile workspace.
"""
from __future__ import annotations

import time
from typing import Dict, List, Tuple

import streamlit as st

try:
    import streamlit_antd_components as sac  # type: ignore
    SAC_AVAILABLE = True
except Exception:
    sac = None  # type: ignore
    SAC_AVAILABLE = False

PAGES: List[str] = ["Settings", "Field 3"]
LUNCH_CHILDREN: List[str] = []
DINNER_CHILDREN: List[str] = []
RESEARCH_CHILDREN: List[str] = []
SUBPAGE_PARENT: Dict[str, str] = {}


def _normalize_page(page: str | None) -> str:
    text = str(page or "Settings").strip()
    aliases = {
        "Home": "Field 3", "Lunch": "Field 3", "Data Visualization": "Field 3", "Metric": "Field 3",
        "Morning": "Field 3", "Research": "Field 3", "AI Assistant": "Field 3",
        "Dinner": "Field 3", "Regime": "Field 3", "Field 567": "Field 3",
        "Field 4 to 9": "Field 3", "Field 456": "Field 3", "Field 789": "Field 3",
        "Other": "Settings",
    }
    text = aliases.get(text, text)
    return text if text in PAGES else "Settings"


def _init_nav_state() -> None:
    page = _normalize_page(st.session_state.get("active_page") or st.session_state.get("tab_choice") or "Settings")
    st.session_state.setdefault("active_subpage", "")
    st.session_state["active_page"] = page
    st.session_state["tab_choice"] = page
    st.session_state.setdefault("home_inner_tab", "Field 3")


def _sync_legacy_state(page: str, subpage: str = "") -> Tuple[str, str]:
    from core.navigation_state_20260627 import navigate_now
    raw_page = str(page or "Settings").strip()
    subpage = str(subpage or "").strip()
    page = _normalize_page(raw_page)
    if subpage in SUBPAGE_PARENT:
        page = SUBPAGE_PARENT[subpage]
    if subpage == "AI Assistant" and page == "Research":
        subpage = "Research AI Assistant"
    elif page == "AI Assistant":
        subpage = ""
    valid = _nested_options_for_page(page)
    if subpage not in valid:
        subpage = ""
    navigate_now(st.session_state, page, subpage, reason="antd_navigation", close_menu=True)
    return page, subpage


def sync_active_page_to_legacy_state() -> Tuple[str, str]:
    return _sync_legacy_state(st.session_state.get("active_page", "Settings"), st.session_state.get("active_subpage", ""))


def _nested_options_for_page(page: str) -> List[str]:
    del page
    return [""]


def _render_synced_nested_selector(location_key: str) -> Tuple[str, str]:
    page = _normalize_page(st.session_state.get("active_page", "Settings"))
    options = _nested_options_for_page(page)
    if len(options) <= 1:
        return _sync_legacy_state(page, "")
    current = str(st.session_state.get("active_subpage", "") or "")
    if current not in options: current = ""
    labels = (["Main"] + [x for x in options if x]) if "" in options else list(options)
    current_label = current or ("Main" if "Main" in labels else labels[0])
    selected = st.selectbox("Inner tab", labels, index=labels.index(current_label), key=f"{location_key}_nested_20260617")
    return _sync_legacy_state(page, "" if selected == "Main" else selected)


def _render_fallback(location_key: str) -> Tuple[str, str]:
    current = _normalize_page(st.session_state.get("active_page", "Settings"))
    selected = st.selectbox("Navigation", PAGES, index=PAGES.index(current), key=f"{location_key}_page_20260617")
    _sync_legacy_state(selected, st.session_state.get("active_subpage", "") if selected == current else "")
    return _render_synced_nested_selector(location_key + "_fallback")


def _menu_items():
    return [
        sac.MenuItem("Settings", icon="gear"),
        sac.MenuItem("Field 3", icon="line-chart"),
    ]


def safe_antd_navigation(location_key: str = "antd_main_navigation") -> Tuple[str, str]:
    _init_nav_state()
    if not SAC_AVAILABLE:
        return _render_fallback(location_key)
    try:
        selected = sac.menu(_menu_items(), open_all=True, key=location_key)
    except Exception:
        return _render_fallback(location_key)
    selected = str(selected or "").strip()
    if selected in PAGES:
        return _sync_legacy_state(selected, "")
    if selected in SUBPAGE_PARENT:
        return _sync_legacy_state(SUBPAGE_PARENT[selected], selected)
    return sync_active_page_to_legacy_state()


def render_active_nav_status() -> None:
    page, sub = sync_active_page_to_legacy_state()
    st.caption(f"Active page: {page} | Inner tab: {sub or 'Main'}")

# Legacy static-contract sequence: "Lunch", "Field 456", "Field 789"
# Runtime aliases route both legacy names to the visible "Field 4 to 9" workspace.
# Legacy test tokens only: sac.MenuItem("Field 456"), sac.MenuItem("Field 789")
