"""Single application-shell navigation state machine.

Only this module owns top-level page transitions. Page renderers may keep local
field/section state, but they must not overwrite ``active_page``.
"""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping
import time

VALID_PAGES: tuple[str, ...] = (
    "Settings", "Field 3"
)
ALIASES: dict[str, str] = {
    "Home": "Field 3",
    "Lunch": "Field 3",
    "Data Visualization": "Field 3",
    "Metric": "Field 3",
    "Power BI": "Field 3",
    "PowerBI": "Field 3",
    "Dinner": "Field 3",
    "Regime": "Field 3",
    "Field 4 to 9": "Field 3",
    "Field 456+789": "Field 3",
    "Field 456": "Field 3",
    "Field 789": "Field 3",
    "Morning": "Field 3",
    "Research": "Field 3",
    "Other": "Settings",
    "AI Assistant": "Field 3",
}



def normalize_page(page: Any, default: str = "Settings") -> str:
    text = str(page or default).strip() or default
    text = ALIASES.get(text, text)
    return text if text in VALID_PAGES else default


def initialize_navigation(state: MutableMapping[str, Any]) -> str:
    """Initialize once. Legacy keys may seed the page but never override it later."""
    if "active_page" not in state:
        state["active_page"] = normalize_page(state.get("tab_choice"), "Settings")
    else:
        state["active_page"] = normalize_page(state.get("active_page"), "Settings")
    state.setdefault("requested_page", None)
    state.setdefault("requested_subpage", "")
    state.setdefault("active_subpage", "")
    state.setdefault("active_lunch_field", None)
    state.setdefault("active_dinner_field", None)
    state.setdefault("menu_open", False)
    state.setdefault("navigation_generation", 0)
    _mirror_legacy(state)
    return str(state["active_page"])


def request_page(
    state: MutableMapping[str, Any],
    page: Any,
    subpage: str = "",
    *,
    lunch_field: Any = None,
    dinner_field: Any = None,
    reason: str = "user_navigation",
    close_menu: bool = True,
) -> dict[str, Any]:
    """Queue a route transaction. It is committed before page rendering."""
    target = normalize_page(page)
    state["requested_page"] = target
    state["requested_subpage"] = str(subpage or "")
    if lunch_field is not None:
        state["requested_lunch_field"] = lunch_field
    if dinner_field is not None:
        state["requested_dinner_field"] = dinner_field
    state["navigation_request_reason"] = str(reason or "navigation")
    state["navigation_request_timestamp"] = time.time()
    state["ui_navigation_click_ts"] = state["navigation_request_timestamp"]
    state["fast_tab_switch_active"] = True
    if close_menu:
        state["menu_open"] = False
        state["new7_main_menu_drawer_open"] = False
    return {
        "page": target,
        "subpage": str(subpage or ""),
        "reason": state["navigation_request_reason"],
    }


def commit_requested_page(state: MutableMapping[str, Any]) -> str:
    """Commit at most one queued route and return the authoritative page."""
    initialize_navigation(state)
    requested = state.get("requested_page")
    if requested not in (None, ""):
        target = normalize_page(requested)
        subpage = str(state.get("requested_subpage") or "")
        old_page = normalize_page(state.get("active_page"))
        old_subpage = str(state.get("active_subpage") or "")
        state["active_page"] = target
        state["active_subpage"] = subpage
        if "requested_lunch_field" in state:
            state["active_lunch_field"] = state.pop("requested_lunch_field")
        if "requested_dinner_field" in state:
            state["active_dinner_field"] = state.pop("requested_dinner_field")
        state["requested_page"] = None
        state["requested_subpage"] = ""
        if target != old_page or subpage != old_subpage:
            state["navigation_generation"] = int(state.get("navigation_generation", 0) or 0) + 1
        state["navigation_committed_at"] = time.time()
    else:
        state["active_page"] = normalize_page(state.get("active_page"))
    _mirror_legacy(state)
    return str(state["active_page"])


def navigate_now(
    state: MutableMapping[str, Any],
    page: Any,
    subpage: str = "",
    *,
    lunch_field: Any = None,
    dinner_field: Any = None,
    reason: str = "user_navigation",
    close_menu: bool = True,
) -> str:
    request_page(
        state, page, subpage, lunch_field=lunch_field, dinner_field=dinner_field,
        reason=reason, close_menu=close_menu,
    )
    return commit_requested_page(state)


def _mirror_legacy(state: MutableMapping[str, Any]) -> None:
    page = normalize_page(state.get("active_page"))
    subpage = str(state.get("active_subpage") or "")
    state["active_page"] = page
    state["tab_choice"] = page
    if page == "Field 3":
        state["home_inner_tab"] = "Field 3"
        state["lunch_active_subpage"] = subpage


def navigation_snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "active_page": normalize_page(state.get("active_page")),
        "active_subpage": str(state.get("active_subpage") or ""),
        "requested_page": state.get("requested_page"),
        "navigation_generation": int(state.get("navigation_generation", 0) or 0),
        "menu_open": bool(state.get("menu_open", False)),
    }


__all__ = [
    "VALID_PAGES", "ALIASES", "normalize_page", "initialize_navigation",
    "request_page", "commit_requested_page", "navigate_now", "navigation_snapshot",
]
