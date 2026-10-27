"""Lazy registry for the reduced Settings / Field 3 application."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class TabSpec:
    name: str
    module: str
    function: str = "show"
    icon: str = "📌"
    layer: str = "page"
    notes: str = ""


TAB_REGISTRY: Dict[str, TabSpec] = {
    "Settings": TabSpec(
        "Settings", "tabs.antd_page_router_20260615", icon="⚙️",
        notes="Configure providers, select/load symbols and run calculations.",
    ),
    "Field 3": TabSpec(
        "Field 3", "tabs.field3_page_20260722", icon="📈",
        notes="All loaded-symbol Lower/Middle/Higher summaries, final ranking and selected-symbol evidence.",
    ),
}


def get_tab_spec(tab_name: str) -> TabSpec:
    """Return one of the only two exposed pages; unknown routes go to Settings."""
    return TAB_REGISTRY.get(str(tab_name), TAB_REGISTRY["Settings"])


def tab_icons() -> dict[str, str]:
    return {name: spec.icon for name, spec in TAB_REGISTRY.items()}


__all__ = ["TabSpec", "TAB_REGISTRY", "get_tab_spec", "tab_icons"]
