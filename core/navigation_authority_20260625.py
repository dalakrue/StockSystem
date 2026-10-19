"""Backward-compatible facade over the single 2026-06-27 shell router."""
from __future__ import annotations
from typing import Any, MutableMapping
from core.navigation_state_20260627 import navigate_now

TX_KEY = "navigation_tx_20260625"


def navigate_to(
    state: MutableMapping[str, Any],
    page: str,
    subpage: str = "",
    lunch_field: str | None = None,
) -> dict[str, Any]:
    target = navigate_now(
        state,
        page,
        subpage,
        lunch_field=lunch_field,
        reason="navigation_authority",
        close_menu=True,
    )
    tx = {
        "page": target,
        "subpage": str(subpage or ""),
        "lunch_field": lunch_field,
        "generation": int(state.get("navigation_generation", 0) or 0),
    }
    state[TX_KEY] = tx
    if lunch_field:
        state["lunch_active_field_selector_20260624"] = lunch_field
        state["lunch_active_field_selector_20260624__pending"] = lunch_field
    return tx


__all__ = ["navigate_to", "TX_KEY"]
