"""Secure API-secret resolution and guarded authenticated startup.

Secrets are read server-side and never returned to UI code.  The guarded startup
is idempotent per authenticated symbol/timeframe session and keeps manual Run Calculation available.
"""
from __future__ import annotations

import os
import threading
import time
import json
from hashlib import sha256
from typing import Any, Mapping, MutableMapping

import pandas as pd

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None  # type: ignore

_LOCK = threading.Lock()


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


def _secret_bool(section: str, name: str, default: bool) -> bool:
    value = _secret_path(section, name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on", "enabled"}


def _first_secret(*paths: tuple[str, ...]) -> str:
    """Return the first configured Streamlit secret from accepted aliases."""
    for path in paths:
        value = _secret_path(*path)
        if value:
            return value
    return ""


def _provider_config(provider: str) -> dict[str, Any] | None:
    name = str(provider or "").strip().lower()
    if name in {"finnhub", "finn"}:
        return {
            "logical": "FINNHUB",
            "state": ("finnhub_api_key", "FINNHUB_API_KEY"),
            "env": ("FINNHUB_API_KEY",),
            "secret_paths": (
                ("api_keys", "finnhub"), ("api_keys", "finnhub_api_key"),
                ("FINNHUB_API_KEY",), ("finnhub_api_key",),
                ("finnhub", "api_key"),
            ),
        }
    if name in {"second_api", "twelve", "twelve_data", "market"}:
        return {
            "logical": "TWELVE_DATA",
            "state": (
                "twelve_api_key_1", "twelve_data_api_key_1", "TWELVE_DATA_API_KEY_1", "TWELVE_API_KEY_1",
                "twelve_api_key", "second_api_key", "TWELVE_DATA_API_KEY",
                "TWELVE_API_KEY", "twelve_data_api_key",
            ),
            "env": ("TWELVE_DATA_API_KEY_1", "TWELVE_API_KEY_1", "TWELVE_DATA_API_KEY", "TWELVE_API_KEY"),
            "secret_paths": (
                ("api_keys", "twelve_data_key_1"), ("api_keys", "twelve_api_key_1"),
                ("api_keys", "second_api_1"), ("api_keys", "second_api"), ("api_keys", "second_api_key"),
                ("api_keys", "twelve_data"), ("api_keys", "twelve"),
                ("api_keys", "twelve_data_api_key"),
                ("TWELVE_DATA_API_KEY",), ("TWELVE_API_KEY",),
                ("twelve_data_api_key",), ("twelve_api_key",),
                ("second_api",), ("second_api_key",),
                ("twelve_data", "api_key"), ("twelve", "api_key"),
            ),
        }
    if name in {"twelve_key_2", "twelve_data_key_2", "second_api_2", "twelve2"}:
        return {
            "logical": "TWELVE_DATA_KEY_2",
            "state": ("twelve_api_key_2", "twelve_data_api_key_2", "second_api_key_2", "TWELVE_DATA_API_KEY_2", "TWELVE_API_KEY_2"),
            "env": ("TWELVE_DATA_API_KEY_2", "TWELVE_API_KEY_2"),
            "secret_paths": (
                ("api_keys", "twelve_data_key_2"), ("api_keys", "twelve_api_key_2"),
                ("api_keys", "second_api_2"), ("TWELVE_DATA_API_KEY_2",),
                ("twelve_data", "api_key_2"), ("twelve", "api_key_2"),
            ),
        }
    if name in {"alpha_vantage", "alphavantage", "alpha"}:
        return {
            "logical": "ALPHA_VANTAGE",
            "state": ("alpha_vantage_api_key", "ALPHA_VANTAGE_API_KEY"),
            "env": ("ALPHA_VANTAGE_API_KEY",),
            "secret_paths": (
                ("api_keys", "alpha_vantage"), ("ALPHA_VANTAGE_API_KEY",),
                ("alpha_vantage", "api_key"),
            ),
        }
    if name in {"fred", "fred_macro"}:
        return {
            "logical": "FRED",
            "state": ("fred_api_key", "FRED_API_KEY"),
            "env": ("FRED_API_KEY",),
            "secret_paths": (("api_keys", "fred"), ("FRED_API_KEY",), ("fred", "api_key")),
        }
    if name in {"openrouter", "ai", "ai_api"}:
        return {
            "logical": "OPENROUTER",
            "state": ("openrouter_api_key", "OPENROUTER_API_KEY"),
            "env": ("OPENROUTER_API_KEY",),
            "secret_paths": (
                ("api_keys", "openrouter"), ("OPENROUTER_API_KEY",),
                ("openrouter", "api_key"),
            ),
        }
    return None


def resolve_api_key(provider: str, state: Mapping[str, Any] | None = None) -> str:
    """Resolve a credential without exposing it to widgets or logs.

    A temporary key explicitly pasted by the user has highest priority. This is
    important when a stale Streamlit Secret exists: the replacement must be used
    immediately instead of being silently shadowed by the old server value.
    """
    state = state or {}
    config = _provider_config(provider)
    if not config:
        return ""

    deferred_state_values: list[str] = []
    for name in config["state"]:
        value = str(state.get(name) or "").strip()
        if not value:
            continue
        source = str(state.get(f"{name}_source") or "").strip().lower()
        if source == "vault":
            deferred_state_values.append(value)
            continue
        return value

    secret = _first_secret(*config["secret_paths"])
    if secret:
        return secret

    for name in config["env"]:
        value = os.getenv(name, "").strip()
        if value:
            return value

    if deferred_state_values:
        return deferred_state_values[0]

    try:
        from core.connectors.credential_vault import load_credential
        return str(load_credential(config["logical"]) or "").strip()
    except Exception:
        return ""


def _credential_source(provider: str, state: Mapping[str, Any]) -> str:
    config = _provider_config(provider)
    if not config:
        return "Not configured"
    for name in config["state"]:
        if not str(state.get(name) or "").strip():
            continue
        if str(state.get(f"{name}_source") or "").strip().lower() != "vault":
            return "Temporary session replacement"
    if _first_secret(*config["secret_paths"]):
        return "Streamlit Secrets"
    for name in config["state"]:
        if str(state.get(name) or "").strip() and str(state.get(f"{name}_source") or "").strip().lower() == "vault":
            return "Encrypted server-side connection state"
    if any(os.getenv(name, "").strip() for name in config["env"]):
        return "Environment variable"
    try:
        from core.connectors.credential_vault import load_credential
        if load_credential(config["logical"]):
            return "Encrypted server-side connection state"
    except Exception:
        pass
    return "Not configured"


def secure_secret_status(state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    state = state or {}
    sources = {
        "finnhub": _credential_source("finnhub", state),
        "twelve_key_1": _credential_source("second_api", state),
        "twelve_key_2": _credential_source("twelve_key_2", state),
        "alpha": _credential_source("alpha_vantage", state),
        "fred": _credential_source("fred", state),
        "openrouter": _credential_source("openrouter", state),
    }
    key1 = bool(resolve_api_key("second_api", state))
    key2 = bool(resolve_api_key("twelve_key_2", state))
    return {
        "finnhub_configured": bool(resolve_api_key("finnhub", state)),
        "second_api_configured": key1,
        "twelve_key_1_configured": key1,
        "twelve_key_2_configured": key2,
        "alpha_vantage_configured": bool(resolve_api_key("alpha_vantage", state)),
        "fred_configured": bool(resolve_api_key("fred", state)),
        "openrouter_configured": bool(resolve_api_key("openrouter", state)),
        "finnhub_source": sources["finnhub"],
        "second_api_source": sources["twelve_key_1"],
        "twelve_key_1_source": sources["twelve_key_1"],
        "twelve_key_2_source": sources["twelve_key_2"],
        "alpha_vantage_source": sources["alpha"],
        "fred_source": sources["fred"],
        "openrouter_source": sources["openrouter"],
    }

def initialize_secure_settings(state: MutableMapping[str, Any]) -> None:
    try:
        from core.connectors.credential_vault import restore_into_state
        state["credential_vault_restore_20260705"] = restore_into_state(state)
    except Exception:
        state.setdefault("credential_vault_restore_20260705", {})
    # Secure server-side credentials and connection-only startup are fixed
    # product defaults.  They never expose the secret value to a widget and
    # never grant startup permission to calculate a trading generation.
    state["use_secure_api_keys_20260619"] = True
    state["auto_connect_after_login_20260619"] = True
    # Manual authority: the protected all-in-one transaction is owned only by
    # Settings → Run Calculation + Open Lunch. Startup may connect APIs but may
    # never calculate or navigate automatically.
    state["auto_calculate_new_h1_20260619"] = False
    state["open_lunch_after_auto_run_20260619"] = False
    state["auto_run_cooldown_minutes_20260619"] = 3


def _latest_h1(frame: Any) -> pd.Timestamp | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    aliases = ("time", "datetime", "timestamp", "date")
    normalized = {str(col).lower().replace("_", " "): col for col in frame.columns}
    column = next((normalized.get(name) for name in aliases if normalized.get(name) is not None), None)
    if column is None:
        return None
    values = pd.to_datetime(frame[column], errors="coerce", utc=True).dropna()
    return pd.Timestamp(values.max()) if not values.empty else None


def _canonical_latest(state: MutableMapping[str, Any]) -> pd.Timestamp | None:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        canonical = get_canonical(state)
    except Exception:
        canonical = state.get("canonical_result_20260617") or {}
    if not isinstance(canonical, Mapping):
        return None
    value = canonical.get("latest_completed_candle_time") or canonical.get("latest_completed_h1_timestamp")
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return pd.Timestamp(parsed) if pd.notna(parsed) else None


def _connect_market(state: MutableMapping[str, Any]) -> dict[str, Any]:
    requested_mode = str(state.get("connector_mode") or "twelve_pool").strip().lower()
    if requested_mode not in {"twelve_pool", "twelve", "finnhub", "mt5", "doo_bridge", "fallback", "safe_demo"}:
        requested_mode = "twelve_pool"
    mode = requested_mode
    key = resolve_api_key("finnhub" if mode == "finnhub" else "second_api", state) if state.get("use_secure_api_keys_20260619", True) else str(state.get("finnhub_api_key" if mode == "finnhub" else "twelve_api_key") or "")
    if mode in {"twelve_pool", "twelve"} and not (resolve_api_key("second_api", state) or resolve_api_key("twelve_key_2", state)) and state.get("last_df") is None:
        return {"ok": False, "status": "SKIPPED", "message": "Twelve Data key pool is not configured."}
    if mode == "finnhub" and not key and state.get("last_df") is None:
        return {"ok": False, "status": "SKIPPED", "message": "Finnhub API key is not configured."}
    symbol = str(state.get("multi_symbol_main_symbol_20260702") or state.get("symbol") or "EURUSD").upper()
    timeframe = str(state.get("timeframe") or "H4").upper()
    bars = int(state.get("connector_bars") or 600)
    bridge_url = str(state.get("doo_bridge_url") or "")
    bridge_token = str(state.get("doo_bridge_token") or "")
    if mode in {"twelve_pool", "twelve", "fallback"}:
        try:
            from core.data.market_data_orchestrator import MarketDataOrchestrator
            state["connector_mode"] = "twelve_pool"
            result = MarketDataOrchestrator().fetch(symbol=symbol, timeframe=timeframe, state=state, bars=bars, force_live=True, run_id="TWELVE_POOL_CONNECT_TEST")
            frame, ok, source, message = result.frame, bool(result.ok), result.provider, result.message
        except Exception as exc:
            frame, ok, source, message = pd.DataFrame(), False, "TWELVE_DATA_KEY_POOL", f"{type(exc).__name__}: {exc}"
    else:
        from core.connectors.data_parts.session import manual_connect
        frame, ok, source, message = manual_connect(
            mode=mode, symbol=symbol, api_key=key, bars=bars, timeframe=timeframe,
            bridge_url=bridge_url, bridge_token=bridge_token,
            allow_demo=bool(state.get("allow_safe_demo", False)),
        )
    rows = len(frame) if isinstance(frame, pd.DataFrame) else 0
    state["connected"] = bool(ok)
    state["source"] = str(source or "")
    state["last_connection_message"] = str(message or "")
    state["last_connection_rows"] = rows
    state["last_connection_mode"] = mode
    state["last_connected_symbol"] = symbol
    state["last_connected_timeframe"] = timeframe
    if ok and isinstance(frame, pd.DataFrame) and not frame.empty:
        state["last_df"] = frame
        selected = state.get("multi_symbol_selected_20260701")
        selected = [str(item).upper() for item in selected] if isinstance(selected, (list, tuple)) else [symbol]
        if symbol not in selected:
            selected.insert(0, symbol)
        profile = {"mode": mode, "source": source, "symbol": symbol, "timeframe": timeframe, "bars": bars, "selected_symbols": selected, "rows": rows}
        state["market_connector_saved_profile_20260702"] = profile
    return {"ok": bool(ok), "status": "CONNECTED" if ok else "FAILED", "message": str(message or ""), "rows": rows, "source": str(source or ""), "mode": mode}

def _validate_finnhub_once(state: MutableMapping[str, Any]) -> dict[str, Any]:
    key = resolve_api_key("finnhub", state) if state.get("use_secure_api_keys_20260619", True) else str(state.get("finnhub_api_key") or "")
    if not key:
        return {"ok": False, "status": "SKIPPED", "message": "Finnhub key is not configured."}
    now = time.time()
    last = float(state.get("secure_finnhub_validation_ts_20260619", 0.0) or 0.0)
    if now - last < 3600 and state.get("finnhub_connected"):
        return {"ok": True, "status": "CACHED"}
    from core.finnhub_connector import connect
    result = connect(key)
    state["secure_finnhub_validation_ts_20260619"] = now
    return {"ok": bool(result.get("ok")), "status": result.get("availability", "UNKNOWN"), "message": result.get("message", "")}


def run_guarded_startup(state: MutableMapping[str, Any], home_namespace: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Connect configured providers once after any successful login.

    Guest sessions are authenticated application sessions too. The connection
    attempt is idempotent for the current login, symbol and timeframe, while
    heavy calculation remains owned exclusively by the Settings run buttons.
    """
    initialize_secure_settings(state)
    result: dict[str, Any] = {"ok": True, "status": "NO_ACTION", "auto_connected": False, "auto_calculated": False}
    if not state.get("new7_auth_logged_in"):
        result.update(ok=False, status="AUTH_REQUIRED")
        state["secure_startup_status_20260619"] = result
        return result

    symbol = str(state.get("multi_symbol_main_symbol_20260702") or state.get("symbol") or "EURUSD").upper()
    timeframe = str(state.get("timeframe") or "H4").upper()
    login_token = str(state.get("new7_auth_login_ts") or "session")
    identity = f"{login_token}|{symbol}|{timeframe}"
    previous_identity = state.get("secure_auto_connect_identity_20260706")
    previous_status = state.get("secure_startup_status_20260619")
    last_attempt = float(state.get("secure_startup_attempt_ts_20260619") or 0.0)
    now = time.time()
    previous_connected = bool(isinstance(previous_status, Mapping) and previous_status.get("auto_connected"))
    if previous_identity == identity and (previous_connected or now - last_attempt < 60.0):
        if isinstance(previous_status, Mapping):
            return {**dict(previous_status), "status": "RERUN_GUARD", "idempotent_reuse": True}
        return {**result, "status": "RERUN_GUARD", "idempotent_reuse": True}

    state["secure_auto_connect_identity_20260706"] = identity
    state["secure_startup_attempt_ts_20260619"] = now
    status = secure_secret_status(state)
    result["secret_status"] = {
        "twelve_configured": bool(status.get("second_api_configured")),
        "finnhub_configured": bool(status.get("finnhub_configured")),
        "twelve_source": status.get("second_api_source"),
        "finnhub_source": status.get("finnhub_source"),
    }

    if state.get("auto_connect_after_login_20260619", True):
        if status.get("second_api_configured"):
            try:
                market = _connect_market(state)
            except Exception as exc:
                market = {"ok": False, "status": "CONNECT_ERROR", "message": f"{type(exc).__name__}: {exc}"}
            result["market_connection"] = market
            source = str(market.get("source") or "").upper()
            twelve_ok = bool(market.get("ok") and source in {"TWELVE", "TWELVE_DATA", "CACHE"})
            state["twelve_data_connected"] = twelve_ok
            state["twelve_connected"] = twelve_ok
            state["twelve_last_auto_connect_20260706"] = time.time()
            state["twelve_last_auto_connect_message_20260706"] = str(market.get("message") or market.get("status") or "")
        else:
            result["market_connection"] = {"ok": False, "status": "NOT_CONFIGURED"}

        if status.get("finnhub_configured"):
            try:
                finnhub = _validate_finnhub_once(state)
            except Exception as exc:
                finnhub = {"ok": False, "status": "CONNECT_ERROR", "message": f"{type(exc).__name__}: {exc}"}
            result["finnhub_connection"] = finnhub
        else:
            result["finnhub_connection"] = {"ok": False, "status": "NOT_CONFIGURED"}

        result["auto_connected"] = bool(
            (result.get("market_connection") or {}).get("ok")
            or (result.get("finnhub_connection") or {}).get("ok")
        )

    latest = _latest_h1(state.get("last_df"))
    published = _canonical_latest(state)
    result["latest_candle"] = latest.isoformat() if latest is not None else None
    result["published_candle"] = published.isoformat() if published is not None else None
    newer = latest is not None and (published is None or latest > published)
    result["newer_candle_available"] = bool(newer)
    result["auto_calculated"] = False
    result["status"] = "AUTO_CONNECTED" if result.get("auto_connected") else "CONNECTORS_NOT_READY"
    result["message"] = (
        "Configured deployment secrets were connected automatically. Use Settings to start calculation."
        if result.get("auto_connected") else
        "No configured provider connected automatically; Settings remains available for manual connection."
    )
    state["secure_startup_status_20260619"] = result
    return result


__all__ = [
    "resolve_api_key", "secure_secret_status", "initialize_secure_settings", "run_guarded_startup",
]
