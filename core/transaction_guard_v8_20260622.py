"""Small idempotency/debounce guard for user-triggered Streamlit transactions."""
from __future__ import annotations
from typing import Any, MutableMapping
import hashlib, time, uuid

VERSION = "transaction-guard-v8-20260622"


def begin_transaction(state: MutableMapping[str, Any], name: str, *, payload: str = "", debounce_seconds: float = 1.5) -> dict[str, Any]:
    now = time.time(); key = f"v8_transaction_{name}"; previous = state.get(key) if isinstance(state.get(key), dict) else {}
    signature = hashlib.sha256(f"{name}|{payload}".encode()).hexdigest()[:20]
    if previous.get("active"):
        return {"accepted": False, "reason": "transaction already active", "token": previous.get("token")}
    if previous.get("signature") == signature and now - float(previous.get("completed_at", 0) or 0) < float(debounce_seconds):
        return {"accepted": False, "reason": "duplicate transaction debounced", "token": previous.get("token")}
    token = uuid.uuid4().hex
    state[key] = {"active": True, "token": token, "signature": signature, "started_at": now, "completed_at": previous.get("completed_at")}
    return {"accepted": True, "token": token, "signature": signature}


def finish_transaction(state: MutableMapping[str, Any], name: str, token: str, *, status: str = "COMPLETED") -> bool:
    key = f"v8_transaction_{name}"; current = state.get(key)
    if not isinstance(current, dict) or current.get("token") != token: return False
    current = dict(current); current.update({"active": False, "status": status, "completed_at": time.time()}); state[key] = current
    return True


def transaction_active(state: MutableMapping[str, Any], name: str) -> bool:
    value = state.get(f"v8_transaction_{name}")
    return bool(isinstance(value, dict) and value.get("active"))

__all__ = ["begin_transaction", "finish_transaction", "transaction_active", "VERSION"]
