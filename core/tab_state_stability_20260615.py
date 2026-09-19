"""Compatibility mirror for the reduced two-page application.

Authoritative routing lives in :mod:`core.navigation_state_20260627`. This
module only keeps older callers stable while preventing hidden legacy pages
from reappearing.
"""
from __future__ import annotations

from typing import Dict, List

from core.navigation_state_20260627 import (
    VALID_PAGES,
    commit_requested_page,
    initialize_navigation,
    normalize_page,
)

PAGES: List[str] = list(VALID_PAGES)
SUBPAGES: Dict[str, List[str]] = {page: [""] for page in PAGES}
ALIASES = {
    "Home": "Field 3",
    "Lunch": "Field 3",
    "Data Visualization": "Field 3",
    "Metric": "Field 3",
    "Power BI": "Field 3",
    "PowerBI": "Field 3",
    "Morning": "Field 3",
    "Dinner": "Field 3",
    "Regime": "Field 3",
    "Field 456": "Field 3",
    "Field 789": "Field 3",
    "Field 456+789": "Field 3",
    "Field 4 to 9": "Field 3",
}
SUBPAGE_PARENT: Dict[str, str] = {}


def stabilize_tab_state() -> None:
    try:
        import streamlit as st
    except Exception:
        return

    ss = st.session_state
    initialize_navigation(ss)
    page = normalize_page(commit_requested_page(ss))

    ss["active_page"] = page
    ss["active_subpage"] = ""
    ss["tab_choice"] = page
    if page == "Field 3":
        ss["home_inner_tab"] = page
    ss["tab_state_stable_20260615"] = True
