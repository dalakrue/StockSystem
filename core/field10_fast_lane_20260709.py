"""Field 10 fast-lane controls for the Settings Super Quick run.

The Super Quick button is intentionally a read/write Field-10-first path.  It
keeps the protected Field 10 production publication and the minimum Field 1/2/3
identity gates needed for a valid child snapshot, while heavier Lunch/AI/Field 11
and research rebuilds are explicitly deferred to Quick or Full.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from datetime import datetime, timezone
from typing import Any

FAST_LANE_KEY = "super_quick_field10_fast_lane_20260709"
DEFERRED_WORK_KEY = "super_quick_deferred_work_20260709"
LAST_PROFILE_KEY = "last_run_profile_20260709"

QUICK_OWNER = "Quick — Calculate All Loaded Symbols + Open Lunch"
FULL_OWNER = "Full — Calculate All Loaded Symbols + Open Lunch"


def set_field10_fast_lane(state: MutableMapping[str, Any], *, enabled: bool, scope: Any = None) -> None:
    """Enable the Field-10-first Super Quick profile for the next Settings run."""
    state[FAST_LANE_KEY] = bool(enabled)
    state[LAST_PROFILE_KEY] = "FIELD10_FAST_LANE" if enabled else str(scope or state.get("settings_calculation_scope_20260625") or "FULL").upper()
    if not enabled:
        state.pop(DEFERRED_WORK_KEY, None)


def is_field10_fast_lane(state: Mapping[str, Any] | None, scope: Any = None) -> bool:
    state_map = state if isinstance(state, Mapping) else {}
    normalized_scope = str(scope or state_map.get("settings_calculation_scope_20260625") or "").upper()
    return bool(state_map.get(FAST_LANE_KEY)) and normalized_scope == "LUNCH_CORE"


def defer_to_quick(
    state: MutableMapping[str, Any] | None,
    name: str,
    *,
    owner: str = QUICK_OWNER,
    reason: str = "Deferred by Super Quick Field 10 fast lane.",
) -> dict[str, Any]:
    """Return and record a standard deferred-work status payload."""
    payload = {
        "ok": False,
        "status": "DEFERRED_TO_QUICK_RUN",
        "deferred": True,
        "owner_button": owner,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "field10_production_modified": False,
    }
    if isinstance(state, MutableMapping):
        existing = state.get(DEFERRED_WORK_KEY)
        deferred = dict(existing) if isinstance(existing, Mapping) else {}
        deferred[str(name)] = payload
        state[DEFERRED_WORK_KEY] = deferred
    return payload


def field10_fast_lane_summary(state: Mapping[str, Any] | None) -> dict[str, Any]:
    state_map = state if isinstance(state, Mapping) else {}
    deferred = state_map.get(DEFERRED_WORK_KEY)
    deferred = dict(deferred) if isinstance(deferred, Mapping) else {}
    return {
        "enabled": bool(state_map.get(FAST_LANE_KEY)),
        "profile": state_map.get(LAST_PROFILE_KEY),
        "deferred_count": len(deferred),
        "deferred_items": sorted(deferred.keys()),
        "quick_owner": QUICK_OWNER,
    }


__all__ = [
    "FAST_LANE_KEY", "DEFERRED_WORK_KEY", "LAST_PROFILE_KEY", "QUICK_OWNER", "FULL_OWNER",
    "set_field10_fast_lane", "is_field10_fast_lane", "defer_to_quick", "field10_fast_lane_summary",
]
