"""One-use Settings-to-page navigation transaction.

The former token repeatedly forced Lunch during the same rerun and could lock the
application there. This compatibility module now delegates to the shell router and
consumes each token once.
"""
from __future__ import annotations
from typing import Any, Mapping, MutableMapping
import hashlib
import time

from core.navigation_state_20260627 import navigate_now, request_page

TOKEN_KEY = "pending_navigation_quant_v6_20260622"
CONFIRMED_KEY = "confirmed_navigation_quant_v6_20260627"


def request_page_navigation(
    state: MutableMapping[str, Any],
    *,
    target_page: str,
    generation_id: Any,
    reason: str,
    used_previous: bool = False,
) -> dict[str, Any]:
    signature = hashlib.sha256(
        f"{target_page}|{generation_id}|{reason}|{int(used_previous)}".encode()
    ).hexdigest()[:24]
    token = {
        "token": signature,
        "signature": signature,
        "target_page": str(target_page),
        "generation_id": str(generation_id or "UNAVAILABLE"),
        "request_timestamp": time.time(),
        "reason": str(reason),
        "used_previous": bool(used_previous),
        "consumed": False,
        "confirmed": False,
    }
    state[TOKEN_KEY] = token
    request_page(
        state,
        target_page,
        "",
        reason=f"settings_transaction:{reason}",
        close_menu=True,
    )
    return token


def request_lunch_navigation(
    state: MutableMapping[str, Any],
    *,
    generation_id: Any,
    reason: str,
    used_previous: bool = False,
):
    state["settings_used_previous_canonical_20260622"] = bool(used_previous)
    return request_page_navigation(
        state,
        target_page="Field 3",
        generation_id=generation_id,
        reason=reason,
        used_previous=used_previous,
    )


def pending_lunch_navigation(state: Mapping[str, Any]) -> bool:
    token = state.get(TOKEN_KEY)
    return isinstance(token, Mapping) and str(token.get("target_page")) in {"Field 3", "Lunch"} and not token.get("consumed")


def consume_pending_navigation(state: MutableMapping[str, Any]):
    token = state.get(TOKEN_KEY)
    if not isinstance(token, Mapping) or token.get("consumed"):
        return None
    token = dict(token)
    target = str(token.get("target_page") or "Settings")
    navigate_now(state, target, "", reason="consume_pending_navigation", close_menu=True)
    token["consumed"] = True
    token["consumed_timestamp"] = time.time()
    state.pop(TOKEN_KEY, None)
    state[CONFIRMED_KEY] = token
    return token


def confirm_lunch_navigation(state: MutableMapping[str, Any], page: str) -> bool:
    token = state.get(CONFIRMED_KEY)
    if not isinstance(token, Mapping) or str(token.get("target_page")) not in {"Field 3", "Lunch"} or str(page) != "Field 3":
        return False
    state.pop(CONFIRMED_KEY, None)
    state["lunch_calculation_completed_notice_20260621"] = True
    state["lunch_auto_open_message_20260622"] = "Calculation completed — Field 3 opened automatically."
    state["lunch_auto_open_used_previous_20260622"] = bool(token.get("used_previous"))
    return True


__all__ = [
    "TOKEN_KEY", "request_page_navigation", "request_lunch_navigation",
    "pending_lunch_navigation", "consume_pending_navigation", "confirm_lunch_navigation",
]
