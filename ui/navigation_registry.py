"""Future-proof navigation registry.

Single source of truth for visible page navigation. Display/control layer only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

try:
    from core.common import DEFAULT_TABS
except Exception:
    DEFAULT_TABS = ["Lunch", "Other"]

try:
    from core.app.registry import tab_icons
except Exception:
    def tab_icons() -> Dict[str, str]:
        return {"Lunch": "🍱", "Other": "📂"}

@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    tab: str
    icon: str = "📌"

def _stable_key(name: str) -> str:
    return str(name or "page").strip().lower().replace(" ", "_").replace("/", "_")

def get_nav_items() -> List[NavItem]:
    icons = tab_icons()
    items: List[NavItem] = []
    seen = set()
    for tab in DEFAULT_TABS:
        if not isinstance(tab, str) or not tab.strip():
            continue
        tab = tab.strip()
        key = _stable_key(tab)
        if key in seen:
            continue
        seen.add(key)
        items.append(NavItem(key=key, label=tab, tab=tab, icon=icons.get(tab, "📌")))
    return items or [NavItem(key="lunch", label="Lunch", tab="Lunch", icon="🍱")]

def valid_tabs() -> List[str]:
    return [item.tab for item in get_nav_items()]

def is_valid_tab(tab: str) -> bool:
    return str(tab) in set(valid_tabs())

def fallback_tab() -> str:
    tabs = valid_tabs()
    return tabs[0] if tabs else "Lunch"

def normalize_active_tab(tab: str | None) -> str:
    candidate = str(tab or "").strip()
    return candidate if is_valid_tab(candidate) else fallback_tab()

def registry_diagnostics() -> dict:
    items = get_nav_items()
    keys = [i.key for i in items]
    tabs = [i.tab for i in items]
    return {"items": len(items), "unique_keys": len(keys) == len(set(keys)), "unique_tabs": len(tabs) == len(set(tabs)), "tabs": tabs, "keys": keys}
