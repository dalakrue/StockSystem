"""Per-key Twelve Data provider pool for ADX Quant Pro.

This module treats each Twelve Data key as a separate rate-limited worker. It
never stores or displays raw credentials; only masked key tails and stable key
aliases are exposed to UI/status tables.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from typing import Any, Mapping, MutableMapping
import os
import threading
import time

try:  # Streamlit is optional for tests/CLI.
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover
    st = None  # type: ignore

_POOL_STATE_KEY = "twelve_data_key_pool_runtime_20260708"
_DEFAULT_MINUTE_LIMIT = int(os.environ.get("TWELVE_DATA_PER_KEY_MINUTE_LIMIT", "8") or 8)
_DEFAULT_COOLDOWN_SECONDS = float(os.environ.get("TWELVE_DATA_429_COOLDOWN_SECONDS", "60") or 60)
_LOCK = threading.RLock()
_GLOBAL_POOL_RUNTIME: dict[str, Any] = {"keys": {}}


def _state_getter_compatible(value: Any) -> bool:
    return value is not None and hasattr(value, "get")


def _state_mutable_compatible(value: Any) -> bool:
    # Streamlit SessionStateProxy is not guaranteed to register as MutableMapping
    # in every runtime, but it does expose get/__setitem__. Treat it as a real
    # shared state object so parallel key-pool workers share one credit ledger.
    return _state_getter_compatible(value) and hasattr(value, "__setitem__")


@dataclass(frozen=True)
class TwelveDataKeyLease:
    alias: str
    api_key: str
    masked_key: str
    remaining_before: int
    remaining_after: int
    cooldown_reset_time: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def mask_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "NOT_CONFIGURED"
    return "****" + text[-4:]


def _fingerprint(value: str) -> str:
    return sha256(str(value or "").encode("utf-8")).hexdigest()[:16] if value else ""


def _secret_path(*parts: str) -> str:
    if st is None:
        return ""
    try:
        value: Any = st.secrets
        for part in parts:
            value = value[part]
        return str(value or "").strip()
    except Exception:
        return ""


def _first_value(state: Mapping[str, Any] | Any, names: tuple[str, ...], secret_paths: tuple[tuple[str, ...], ...], env_names: tuple[str, ...], vault_names: tuple[str, ...]) -> str:
    for name in names:
        try:
            value = str(state.get(name) or "").strip() if _state_getter_compatible(state) else ""
        except Exception:
            value = ""
        if value:
            return value
    for path in secret_paths:
        value = _secret_path(*path)
        if value:
            return value
    for name in env_names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    try:
        from core.connectors.credential_vault import load_credential
        for provider in vault_names:
            value = str(load_credential(provider) or "").strip()
            if value:
                return value
    except Exception:
        pass
    return ""


def resolve_twelve_key(state: Mapping[str, Any] | None, alias: str) -> str:
    state_map = state if _state_getter_compatible(state) else {}
    alias = str(alias or "TWELVE_KEY_1").upper()
    if alias.endswith("2") or alias in {"KEY_2", "TWELVE_DATA_KEY_2"}:
        return _first_value(
            state_map,
            (
                "twelve_api_key_2", "twelve_data_api_key_2", "second_twelve_api_key",
                "second_api_key_2", "TWELVE_DATA_API_KEY_2", "TWELVE_API_KEY_2",
            ),
            (
                ("api_keys", "twelve_data_key_2"), ("api_keys", "twelve_api_key_2"),
                ("api_keys", "second_api_2"), ("TWELVE_DATA_API_KEY_2",),
                ("twelve_data", "api_key_2"), ("twelve", "api_key_2"),
            ),
            ("TWELVE_DATA_API_KEY_2", "TWELVE_API_KEY_2"),
            ("TWELVE_DATA_KEY_2", "TWELVE_KEY_2", "TWELVE_DATA_API_KEY_2"),
        )
    # Key 1 accepts legacy Twelve Data key names for backward compatibility.
    return _first_value(
        state_map,
        (
            "twelve_api_key_1", "twelve_data_api_key_1", "TWELVE_DATA_API_KEY_1", "TWELVE_API_KEY_1",
            "twelve_api_key", "second_api_key", "TWELVE_DATA_API_KEY", "TWELVE_API_KEY", "twelve_data_api_key",
        ),
        (
            ("api_keys", "twelve_data_key_1"), ("api_keys", "twelve_api_key_1"),
            ("api_keys", "second_api_1"), ("api_keys", "second_api"),
            ("api_keys", "second_api_key"), ("api_keys", "twelve_data"),
            ("api_keys", "twelve"), ("api_keys", "twelve_data_api_key"),
            ("TWELVE_DATA_API_KEY_1",), ("TWELVE_API_KEY_1",),
            ("TWELVE_DATA_API_KEY",), ("TWELVE_API_KEY",),
            ("twelve_data", "api_key_1"), ("twelve", "api_key_1"),
            ("twelve_data", "api_key"), ("twelve", "api_key"),
        ),
        ("TWELVE_DATA_API_KEY_1", "TWELVE_API_KEY_1", "TWELVE_DATA_API_KEY", "TWELVE_API_KEY"),
        ("TWELVE_DATA_KEY_1", "TWELVE_KEY_1", "TWELVE_DATA", "TWELVE_DATA_API_KEY"),
    )


class TwelveDataKeyPool:
    def __init__(self, state: MutableMapping[str, Any] | Mapping[str, Any] | None = None, *, minute_limit: int | None = None) -> None:
        # Do not require ``isinstance(state, MutableMapping)`` here. Streamlit's
        # SessionStateProxy can behave like a mutable mapping without registering
        # as one, and the old check caused every parallel worker to receive a
        # throw-away dict copy. That made all workers pick Key 1 and produced the
        # visible 7/12 loaded, 5/12 failed pattern even when Key 2 was configured.
        self.state = state if _state_mutable_compatible(state) else {}
        self.read_state = state if _state_getter_compatible(state) else {}
        self.minute_limit = max(1, int(minute_limit or self.read_state.get("twelve_data_per_key_minute_limit") or _DEFAULT_MINUTE_LIMIT))
        self.enable_multi = bool(self.read_state.get("enable_twelve_multi_key_loading", True))

    @classmethod
    def from_state(cls, state: MutableMapping[str, Any] | Mapping[str, Any] | None = None) -> "TwelveDataKeyPool":
        return cls(state)

    def _runtime(self) -> dict[str, Any]:
        runtime = None
        try:
            runtime = self.state.get(_POOL_STATE_KEY) if _state_getter_compatible(self.state) else None
        except Exception:
            runtime = None
        if not isinstance(runtime, dict):
            runtime = _GLOBAL_POOL_RUNTIME
            runtime.setdefault("keys", {})
            try:
                if _state_mutable_compatible(self.state):
                    self.state[_POOL_STATE_KEY] = runtime
            except Exception:
                # Keep the module-global ledger as the safety net. The key-pool
                # must remain usable in tests, CLI, and Streamlit reruns.
                pass
        runtime.setdefault("keys", {})
        return runtime

    def keys(self) -> list[dict[str, Any]]:
        configured: list[dict[str, Any]] = []
        for alias in ("TWELVE_KEY_1", "TWELVE_KEY_2"):
            if alias == "TWELVE_KEY_2" and not self.enable_multi:
                continue
            key = resolve_twelve_key(self.read_state, alias)
            if key:
                configured.append({
                    "alias": alias,
                    "api_key": key,
                    "masked_key": mask_key(key),
                    "fingerprint": _fingerprint(key),
                    "minute_limit": self.minute_limit,
                })
        return configured

    def active_key_count(self) -> int:
        return len(self.keys())

    def has_available_key(self) -> bool:
        return bool(self.keys())

    def _state_for_alias(self, alias: str, fingerprint: str) -> dict[str, Any]:
        runtime = self._runtime()
        keys = runtime.setdefault("keys", {})
        item = keys.get(alias)
        if not isinstance(item, dict) or item.get("fingerprint") != fingerprint:
            item = {
                "fingerprint": fingerprint,
                "window_started_epoch": time.time(),
                "used_this_window": 0,
                "last_success_time": None,
                "last_429_time": None,
                "cooldown_until_epoch": 0.0,
                "failure_reason": "",
                "connected": False,
            }
            keys[alias] = item
        return item

    def _refresh_window(self, item: dict[str, Any]) -> None:
        now = time.time()
        started = float(item.get("window_started_epoch") or now)
        if now - started >= 60.0:
            item["window_started_epoch"] = now
            item["used_this_window"] = 0

    def status_snapshot(self) -> dict[str, dict[str, Any]]:
        snapshot: dict[str, dict[str, Any]] = {}
        with _LOCK:
            now = time.time()
            configured = {item["alias"]: item for item in self.keys()}
            for alias in ("TWELVE_KEY_1", "TWELVE_KEY_2"):
                key_info = configured.get(alias)
                if not key_info:
                    snapshot[alias] = {
                        "alias": alias,
                        "configured": False,
                        "connected": False,
                        "masked_key": "NOT_CONFIGURED",
                        "remaining_credits": 0,
                        "used_credits": 0,
                        "last_successful_request_time": None,
                        "last_429_time": None,
                        "cooldown_reset_time": None,
                        "failure_reason": "KEY_NOT_CONFIGURED",
                    }
                    continue
                item = self._state_for_alias(alias, key_info["fingerprint"])
                self._refresh_window(item)
                cooldown_until = float(item.get("cooldown_until_epoch") or 0.0)
                remaining = max(0, int(self.minute_limit) - int(item.get("used_this_window") or 0))
                if cooldown_until > now:
                    remaining = 0
                snapshot[alias] = {
                    "alias": alias,
                    "configured": True,
                    "connected": bool(item.get("connected")),
                    "masked_key": key_info["masked_key"],
                    "remaining_credits": remaining,
                    "used_credits": int(item.get("used_this_window") or 0),
                    "minute_limit": self.minute_limit,
                    "last_successful_request_time": item.get("last_success_time"),
                    "last_429_time": item.get("last_429_time"),
                    "cooldown_reset_time": datetime.fromtimestamp(cooldown_until, tz=timezone.utc).isoformat() if cooldown_until > now else None,
                    "failure_reason": str(item.get("failure_reason") or ""),
                }
        return snapshot

    def reserve_key(self, *, symbol: Any = "", timeframe: Any = "") -> TwelveDataKeyLease | None:
        with _LOCK:
            candidates: list[tuple[int, float, dict[str, Any], dict[str, Any]]] = []
            now = time.time()
            for key_info in self.keys():
                item = self._state_for_alias(key_info["alias"], key_info["fingerprint"])
                self._refresh_window(item)
                cooldown_until = float(item.get("cooldown_until_epoch") or 0.0)
                if cooldown_until > now:
                    continue
                used = int(item.get("used_this_window") or 0)
                remaining = max(0, self.minute_limit - used)
                if remaining <= 0:
                    item["failure_reason"] = f"{key_info['alias'].replace('TWELVE_', '')}_RATE_LIMIT"
                    continue
                candidates.append((remaining, float(item.get("window_started_epoch") or now), key_info, item))
            if not candidates:
                return None
            # Prefer the key with most available credits; older windows break ties.
            candidates.sort(key=lambda value: (-value[0], value[1], value[2]["alias"]))
            remaining, _, key_info, item = candidates[0]
            item["used_this_window"] = int(item.get("used_this_window") or 0) + 1
            after = max(0, self.minute_limit - int(item.get("used_this_window") or 0))
            return TwelveDataKeyLease(
                alias=key_info["alias"], api_key=key_info["api_key"], masked_key=key_info["masked_key"],
                remaining_before=remaining, remaining_after=after,
            )

    def reserve_alias(self, alias: str, *, symbol: Any = "", timeframe: Any = "") -> TwelveDataKeyLease | None:
        """Reserve one credit from a specific key alias for Settings key tests.

        The Settings "Test Key 1/2" buttons are real provider requests, so they
        must consume the matching key's counter instead of leaving the UI at 8/8
        credits. This method still respects that key's own cooldown and limit.
        """
        normalized_alias = str(alias or "TWELVE_KEY_1").strip().upper()
        if normalized_alias in {"KEY_1", "TWELVE_DATA_KEY_1", "TWELVE_API_KEY_1"}:
            normalized_alias = "TWELVE_KEY_1"
        if normalized_alias in {"KEY_2", "TWELVE_DATA_KEY_2", "TWELVE_API_KEY_2"}:
            normalized_alias = "TWELVE_KEY_2"
        with _LOCK:
            key_info = next((item for item in self.keys() if item["alias"] == normalized_alias), None)
            if not key_info:
                return None
            item = self._state_for_alias(key_info["alias"], key_info["fingerprint"])
            self._refresh_window(item)
            now = time.time()
            cooldown_until = float(item.get("cooldown_until_epoch") or 0.0)
            if cooldown_until > now:
                return None
            used = int(item.get("used_this_window") or 0)
            remaining = max(0, self.minute_limit - used)
            if remaining <= 0:
                item["failure_reason"] = f"{key_info['alias'].replace('TWELVE_', '')}_RATE_LIMIT"
                return None
            item["used_this_window"] = used + 1
            after = max(0, self.minute_limit - int(item.get("used_this_window") or 0))
            return TwelveDataKeyLease(
                alias=key_info["alias"], api_key=key_info["api_key"], masked_key=key_info["masked_key"],
                remaining_before=remaining, remaining_after=after,
            )

    def mark_success(self, alias: str) -> None:
        with _LOCK:
            key = next((item for item in self.keys() if item["alias"] == alias), None)
            if not key:
                return
            item = self._state_for_alias(alias, key["fingerprint"])
            item["connected"] = True
            item["failure_reason"] = ""
            item["last_success_time"] = _utc_now().isoformat()

    def mark_failure(self, alias: str, reason: Any, *, rate_limited: bool = False, retry_after: float | None = None) -> None:
        with _LOCK:
            key = next((item for item in self.keys() if item["alias"] == alias), None)
            if not key:
                return
            state = self._state_for_alias(alias, key["fingerprint"])
            text = str(reason or "FAILED")[:180]
            state["failure_reason"] = text
            if rate_limited:
                seconds = max(1.0, float(retry_after or _DEFAULT_COOLDOWN_SECONDS))
                state["last_429_time"] = _utc_now().isoformat()
                state["cooldown_until_epoch"] = time.time() + seconds

    def mark_429(self, alias: str, *, retry_after: float | None = None, reason: str = "HTTP_429") -> None:
        self.mark_failure(alias, reason, rate_limited=True, retry_after=retry_after)


def test_twelve_data_key(state: MutableMapping[str, Any] | Mapping[str, Any] | None = None, *, alias: str = "TWELVE_KEY_1") -> dict[str, Any]:
    """Small Settings-button test. It validates auth/reachability, not ranking readiness."""
    from core.connectors.data_parts.fetchers import fetch_twelve
    pool = TwelveDataKeyPool.from_state(state)
    key = resolve_twelve_key(state if _state_getter_compatible(state) else {}, alias)
    started = time.monotonic()
    result = {
        "alias": alias,
        "masked_key": mask_key(key),
        "connected": False,
        "status": "FAILED",
        "remaining_credits": None,
        "last_successful_request_time": None,
        "last_429_time": None,
        "cooldown_reset_time": None,
        "api_response_time_ms": None,
        "error_message": "",
    }
    if not key:
        result["error_message"] = f"{alias}_NOT_CONFIGURED"
        return result
    lease = pool.reserve_alias(alias, symbol="EURUSD", timeframe="M1")
    if lease is None:
        snapshot = pool.status_snapshot().get(alias, {})
        result["remaining_credits"] = snapshot.get("remaining_credits")
        result["last_429_time"] = snapshot.get("last_429_time")
        result["cooldown_reset_time"] = snapshot.get("cooldown_reset_time")
        result["error_message"] = str(snapshot.get("failure_reason") or f"{alias}_RATE_LIMIT_OR_COOLDOWN")
        result["status"] = str(result["error_message"])
        return result
    try:
        raw = fetch_twelve("EUR/USD", lease.api_key, interval="1min", bars=2)
    except Exception as exc:
        raw = (None, False, f"{type(exc).__name__}: {exc}")
    result["api_response_time_ms"] = int((time.monotonic() - started) * 1000)
    ok = bool(isinstance(raw, tuple) and len(raw) >= 2 and raw[1])
    message = str(raw[2] if isinstance(raw, tuple) and len(raw) >= 3 else "")
    if ok:
        pool.mark_success(alias)
        result.update({"connected": True, "status": "CONNECTED", "last_successful_request_time": _utc_now().isoformat()})
    else:
        upper = message.upper()
        if "429" in upper or "RATE" in upper or "QUOTA" in upper:
            pool.mark_429(alias, reason=message or "HTTP_429")
            result["status"] = f"{alias.replace('TWELVE_', '')}_RATE_LIMIT"
        result["error_message"] = message or "Twelve Data key test returned no valid candles"
    status = pool.status_snapshot().get(alias, {})
    result.update({
        "remaining_credits": status.get("remaining_credits"),
        "last_429_time": status.get("last_429_time"),
        "cooldown_reset_time": status.get("cooldown_reset_time"),
    })
    return result


__all__ = [
    "TwelveDataKeyLease", "TwelveDataKeyPool", "resolve_twelve_key", "mask_key",
    "test_twelve_data_key",
]
