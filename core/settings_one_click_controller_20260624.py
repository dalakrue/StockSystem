"""Durable one-click action controller for Settings buttons."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Callable, MutableMapping
import hashlib, time, uuid

VERSION = "settings-one-click-controller-20260624-v1"
STORE_KEY = "settings_one_click_transactions_20260624"
RUNNING_KEY = "settings_one_click_running_20260624"

@dataclass
class TransactionResult:
    transaction_id: str
    action_name: str
    status: str
    started_at: float
    completed_at: float | None
    idempotency_key: str
    result_run_id: str | None
    target_page: str | None
    result_payload: Any
    error: str | None
    retryable: bool


def _store(state: MutableMapping[str, Any]) -> dict[str, Any]:
    value = state.get(STORE_KEY)
    if not isinstance(value, dict):
        value = {}; state[STORE_KEY] = value
    return value


def idempotency_key(action_name: str, payload: Any = None) -> str:
    return hashlib.sha256(f"{action_name}|{repr(payload)}".encode()).hexdigest()[:24]


def run_one_click_action(state: MutableMapping[str, Any], action_name: str, func: Callable[[], Any], *, payload: Any = None, target_page: str | None = None, result_run_id_getter: Callable[[Any], str | None] | None = None) -> dict[str, Any]:
    key = idempotency_key(action_name, payload)
    store = _store(state)
    prev = store.get(key)
    if isinstance(prev, dict) and prev.get("status") == "COMPLETED":
        return {**prev, "deduplicated": True}
    if state.get(RUNNING_KEY):
        return asdict(TransactionResult(str(state.get(RUNNING_KEY)), action_name, "RUNNING", time.time(), None, key, None, None, None, "Another Settings action is running", True))
    tid = uuid.uuid4().hex
    state[RUNNING_KEY] = tid
    started = time.time()
    result = TransactionResult(tid, action_name, "RUNNING", started, None, key, None, target_page, None, None, False)
    store[key] = asdict(result)
    try:
        payload_out = func()
        result.status = "COMPLETED"
        result.result_payload = payload_out
        result.result_run_id = result_run_id_getter(payload_out) if result_run_id_getter else None
        result.completed_at = time.time()
        result.target_page = target_page
        if target_page:
            from core.navigation_state_20260627 import navigate_now
            navigate_now(state, target_page, "", reason="settings_one_click_completed", close_menu=True)
    except Exception as exc:
        result.status = "FAILED"; result.error = f"{type(exc).__name__}: {exc}"; result.retryable = True; result.completed_at = time.time(); result.target_page = "Settings"
        from core.navigation_state_20260627 import navigate_now
        navigate_now(state, "Settings", "", reason="settings_one_click_failed", close_menu=True)
    finally:
        state.pop(RUNNING_KEY, None)
        store[key] = asdict(result)
        state["settings_one_click_last_transaction_20260624"] = asdict(result)
    return asdict(result)


def audit_button(action_name: str, key: str, *, stable: bool = True) -> dict[str, Any]:
    return {"action_name": action_name, "stable_unique_key": key, "one_click_lifecycle": "click → validate → lock → execute → persist → route → release → rerun", "stable": bool(stable), "controller_version": VERSION}

__all__ = ["VERSION", "run_one_click_action", "audit_button", "idempotency_key"]
