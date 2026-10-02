# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Session-only Finnhub connector for the existing Research > NLP workspace.

The API key remains in Streamlit session state only.  It is never written to
project files, SQLite, exports, logs, or cached function arguments.

Connection validation deliberately uses Finnhub news/symbol endpoints instead
of a forex quote request.  A valid Finnhub key can be denied access to a
specific market-data endpoint by plan/entitlement; that must not be reported as
"API key rejected".
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

try:
    import streamlit as st
except Exception:  # Pure validation/tests can run without Streamlit installed.
    class _StreamlitFallback:
        session_state: Dict[str, Any] = {}

        @staticmethod
        def cache_resource(*args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

        def __getattr__(self, name):
            def unavailable(*args, **kwargs):
                return None
            return unavailable

    st = _StreamlitFallback()  # type: ignore

from core.finnhub_validation_20260617 import (
    classify_response as _pure_classify_response,
    normalize_api_key as _pure_normalize_api_key,
    validate_key_format as _pure_validate_key_format,
)

try:
    import httpx
except Exception:  # pragma: no cover - handled in UI
    httpx = None  # type: ignore

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
KEY_STATE = "finnhub_api_key"
CONNECTED_STATE = "finnhub_connected"
LAST_TEST_STATE = "finnhub_last_test"
LAST_SUCCESS_STATE = "finnhub_last_success"
ERROR_STATE = "finnhub_error"
AVAILABILITY_STATE = "finnhub_api_available"
CLIENT_STATE = "finnhub_client_id"
VALIDATION_STATE = "finnhub_validation_endpoint"
NEWS_MODE_STATE = "finnhub_news_mode"
NEWS_STATE = "finnhub_news_cache"
NEWS_TIME_STATE = "finnhub_news_cache_time"
CONNECTION_PREFIX = "finnhub_connector_20260621"
DEFAULT_TIMEOUT = 12.0
MAX_RETRIES = 2

_ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff"
_INVALID_KEY_MARKERS = (
    "invalid api key",
    "api key is invalid",
    "invalid token",
    "token is invalid",
    "please use an api key",
    "missing api key",
    "authentication failed",
    "unauthorized",
)
_ENTITLEMENT_MARKERS = (
    "premium",
    "subscription",
    "not available on your plan",
    "upgrade your plan",
    "permission",
    "access denied",
    "do not have access",
    "doesn't have access",
)
_RATE_LIMIT_MARKERS = ("rate limit", "too many requests")


class FinnhubRequestError(RuntimeError):
    """Redacted request failure carrying enough classification for safe UI."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        auth_invalid: bool = False,
        entitlement_denied: bool = False,
        rate_limited: bool = False,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.auth_invalid = auth_invalid
        self.entitlement_denied = entitlement_denied
        self.rate_limited = rate_limited
        self.retryable = retryable


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def normalize_api_key(value: Any) -> str:
    """Pure, session-safe normalization delegated to the testable module."""
    return _pure_normalize_api_key(value)


def _fingerprint(key: str) -> str:
    return hashlib.sha256(str(key).encode("utf-8", errors="ignore")).hexdigest()[:12] if key else ""


def _redact(value: Any, key: str = "") -> str:
    text = str(value or "")
    clean = normalize_api_key(key)
    if clean:
        text = text.replace(clean, "[REDACTED]")
    text = re.sub(r"(?i)(token|api[_-]?key)=([^&\s]+)", r"\1=[REDACTED]", text)
    text = re.sub(r"https://(?:api\.)?finnhub\.io/[^\s]+", "Finnhub request", text)
    return text[:500]


def _response_message(response: Any) -> str:
    """Extract a short server message without ever including the request URL."""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            for field in ("error", "message", "detail"):
                if payload.get(field):
                    return str(payload[field])[:300]
        if isinstance(payload, list):
            return ""
    except Exception:
        pass
    try:
        return str(response.text or "")[:300]
    except Exception:
        return ""


def _classify_http_error(status_code: int, server_message: str) -> FinnhubRequestError:
    classification = _pure_classify_response(status_code, server_message)
    lower = str(server_message or "").lower()
    if classification["kind"] == "RATE_LIMITED":
        return FinnhubRequestError(
            "Finnhub rate limit reached. Wait briefly and test again.",
            status_code=status_code,
            rate_limited=True,
            retryable=True,
        )
    if classification["kind"] == "AUTH_INVALID":
        return FinnhubRequestError(
            "Finnhub did not accept this API key. Copy the token again from your Finnhub dashboard.",
            status_code=status_code,
            auth_invalid=True,
        )
    if classification["kind"] == "ENTITLEMENT_DENIED":
        # A 403 can be endpoint entitlement/plan restriction. Never label every
        # 403 as an invalid key; validation can continue with a free endpoint.
        entitlement = any(marker in lower for marker in _ENTITLEMENT_MARKERS) or not lower
        return FinnhubRequestError(
            "Finnhub authenticated the request path but this endpoint may be restricted by the account plan.",
            status_code=status_code,
            entitlement_denied=entitlement,
        )
    if classification["kind"] == "TEMPORARY":
        return FinnhubRequestError(
            "Finnhub is temporarily unavailable. Test again shortly.",
            status_code=status_code,
            retryable=True,
        )
    detail = server_message.strip() if server_message else f"HTTP {status_code}"
    return FinnhubRequestError(
        f"Finnhub request failed: {detail}",
        status_code=status_code,
        retryable=status_code >= 500,
    )


def initialize_finnhub_state() -> None:
    st.session_state.setdefault(KEY_STATE, "")
    st.session_state.setdefault(CONNECTED_STATE, False)
    st.session_state.setdefault(LAST_TEST_STATE, "Never")
    st.session_state.setdefault(LAST_SUCCESS_STATE, "Never")
    st.session_state.setdefault(ERROR_STATE, "")
    st.session_state.setdefault(AVAILABILITY_STATE, "UNKNOWN")
    st.session_state.setdefault(CLIENT_STATE, "")
    st.session_state.setdefault(VALIDATION_STATE, "")
    st.session_state.setdefault(NEWS_MODE_STATE, "forex")
    st.session_state.setdefault(NEWS_STATE, [])
    st.session_state.setdefault(NEWS_TIME_STATE, 0.0)
    try:
        from core.connector_state_machine_20260621 import initialize, succeed
        initialize(st.session_state, CONNECTION_PREFIX)
        if st.session_state.get(CONNECTED_STATE):
            succeed(st.session_state, CONNECTION_PREFIX, "Finnhub connected.")
    except Exception:
        pass


def get_session_key() -> str:
    initialize_finnhub_state()
    session_key = normalize_api_key(st.session_state.get(KEY_STATE, ""))
    if session_key:
        return session_key
    try:
        from core.secure_api_startup_20260619 import resolve_api_key
        return normalize_api_key(resolve_api_key("finnhub", st.session_state))
    except Exception:
        return ""


def connection_status() -> Dict[str, Any]:
    initialize_finnhub_state()
    return {
        "connected": bool(st.session_state.get(CONNECTED_STATE, False)),
        "last_test": st.session_state.get(LAST_TEST_STATE, "Never"),
        "last_success": st.session_state.get(LAST_SUCCESS_STATE, "Never"),
        "error": st.session_state.get(ERROR_STATE, ""),
        "availability": st.session_state.get(AVAILABILITY_STATE, "UNKNOWN"),
        "validation_endpoint": st.session_state.get(VALIDATION_STATE, ""),
        "news_mode": st.session_state.get(NEWS_MODE_STATE, "forex"),
        "state": st.session_state.get(f"{CONNECTION_PREFIX}_state", "CONNECTED" if st.session_state.get(CONNECTED_STATE) else "DISCONNECTED"),
        "state_message": st.session_state.get(f"{CONNECTION_PREFIX}_message", ""),
    }


@st.cache_resource(show_spinner=False)
def _shared_http_client():
    """One reusable Finnhub HTTP client; the secret is never a cache key."""
    if httpx is None:
        return None
    return httpx.Client(
        timeout=httpx.Timeout(DEFAULT_TIMEOUT, connect=DEFAULT_TIMEOUT),
        follow_redirects=True,
        headers={
            "Accept": "application/json",
            "User-Agent": "ADX-Quant-Pro-Finnhub-Connector/2026.06",
        },
    )


def _request_json(path: str, key: str, params: Optional[Dict[str, Any]] = None) -> Any:
    if httpx is None:
        raise FinnhubRequestError("httpx is not installed. Install the project requirements.")
    clean = normalize_api_key(key)
    if not clean:
        raise FinnhubRequestError("Finnhub API key is empty.", auth_invalid=True)

    key = clean
    request_params = dict(params or {})
    request_params["token"] = key
    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            client = _shared_http_client()
            if client is None:
                raise FinnhubRequestError("httpx is not installed. Install the project requirements.")
            response = client.get(f"{FINNHUB_BASE_URL}/{path.lstrip('/')}", params=request_params)
            if int(response.status_code) >= 400:
                raise _classify_http_error(int(response.status_code), _response_message(response))
            payload = response.json()
            if isinstance(payload, dict) and payload.get("error"):
                message = str(payload.get("error"))
                lower = message.lower()
                raise FinnhubRequestError(
                    message,
                    auth_invalid=any(marker in lower for marker in _INVALID_KEY_MARKERS),
                    entitlement_denied=any(marker in lower for marker in _ENTITLEMENT_MARKERS),
                    rate_limited=any(marker in lower for marker in _RATE_LIMIT_MARKERS),
                )
            if not isinstance(payload, (dict, list)):
                raise FinnhubRequestError("Finnhub returned an unsupported JSON response.")
            return payload
        except FinnhubRequestError as exc:
            last_error = exc
            if not exc.retryable or attempt >= MAX_RETRIES:
                break
            time.sleep(0.7 * (attempt + 1))
        except Exception as exc:
            last_error = exc
            if attempt >= MAX_RETRIES:
                break
            time.sleep(0.55 * (attempt + 1))

    if isinstance(last_error, FinnhubRequestError):
        raise last_error
    raise FinnhubRequestError(_redact(last_error or "Finnhub request failed", clean), retryable=True)


def _validate_payload(payload: Any, expected_type: type) -> bool:
    return isinstance(payload, expected_type)


def validate_connection(key: str) -> Dict[str, Any]:
    """Validate authentication with NLP-relevant/free-safe endpoints.

    Validation order:
      1. Forex market news (the connector's actual purpose).
      2. General market news (safe fallback if forex category is restricted).
      3. US symbol list (authentication-only fallback).

    A plan restriction is reported separately from an invalid token.
    """
    format_result = _pure_validate_key_format(key)
    clean = str(format_result.get("normalized_key") or "")
    if not format_result.get("ok"):
        return {
            "ok": False,
            "message": "Enter a valid Finnhub API key.",
            "availability": "UNAVAILABLE",
            "reason": str(format_result.get("reason") or "INVALID_FORMAT"),
        }

    checks: Tuple[Tuple[str, Dict[str, Any], type, str, str], ...] = (
        ("news", {"category": "forex", "minId": 0}, list, "FOREX_NEWS", "forex"),
        ("news", {"category": "general", "minId": 0}, list, "GENERAL_NEWS", "general"),
        ("stock/symbol", {"exchange": "US"}, list, "US_SYMBOLS", "general"),
    )
    failures: List[FinnhubRequestError] = []
    for path, params, expected, label, news_mode in checks:
        try:
            payload = _request_json(path, clean, params)
            if not _validate_payload(payload, expected):
                raise FinnhubRequestError(f"Finnhub {label.lower()} validation returned an unexpected payload.")
            availability = "AVAILABLE" if label in {"FOREX_NEWS", "GENERAL_NEWS"} else "AUTHENTICATED"
            message = (
                "Finnhub connected and forex news is available."
                if label == "FOREX_NEWS"
                else "Finnhub connected; general news fallback will be used."
                if label == "GENERAL_NEWS"
                else "Finnhub key is valid, but the news endpoint is unavailable for this account right now."
            )
            return {
                "ok": True,
                "message": message,
                "availability": availability,
                "validation_endpoint": label,
                "news_mode": news_mode,
                "sample_count": len(payload) if isinstance(payload, list) else 1,
            }
        except FinnhubRequestError as exc:
            failures.append(exc)
            if exc.auth_invalid:
                return {
                    "ok": False,
                    "message": _redact(exc, clean),
                    "availability": "UNAVAILABLE",
                    "reason": "AUTH_INVALID",
                }
            # Entitlement/temporary endpoint problems can continue to fallback.
            continue
        except Exception as exc:
            failures.append(FinnhubRequestError(_redact(exc, clean), retryable=True))
            continue

    if any(f.rate_limited for f in failures):
        return {
            "ok": False,
            "message": "Finnhub rate limit reached. Wait about one minute and press Test again.",
            "availability": "RATE_LIMITED",
            "reason": "RATE_LIMITED",
        }
    if failures and all(f.entitlement_denied for f in failures):
        return {
            "ok": False,
            "message": "The key was not rejected, but all validation endpoints are restricted for this account plan.",
            "availability": "PLAN_RESTRICTED",
            "reason": "PLAN_RESTRICTED",
        }
    return {
        "ok": False,
        "message": "Finnhub could not be reached or returned an unexpected response. Check internet/DNS access and press Test again.",
        "availability": "UNAVAILABLE",
        "reason": "NETWORK_OR_SERVICE",
    }


def _apply_success(clean: str, result: Dict[str, Any]) -> None:
    st.session_state[KEY_STATE] = clean
    st.session_state[CONNECTED_STATE] = True
    st.session_state[LAST_SUCCESS_STATE] = st.session_state[LAST_TEST_STATE]
    st.session_state[CLIENT_STATE] = _fingerprint(clean)
    st.session_state[ERROR_STATE] = ""
    st.session_state[VALIDATION_STATE] = result.get("validation_endpoint", "")
    st.session_state[NEWS_MODE_STATE] = result.get("news_mode", "forex")


def connect(key: str) -> Dict[str, Any]:
    initialize_finnhub_state()
    from core.connector_state_machine_20260621 import begin, fail, succeed
    if not begin(st.session_state, CONNECTION_PREFIX):
        return {"ok": False, "duplicate_blocked": True, "message": "Finnhub connection is already in progress.", "availability": "CONNECTING"}
    clean = normalize_api_key(key)
    try:
        result = validate_connection(clean)
        st.session_state[LAST_TEST_STATE] = _utc_now_text()
        st.session_state[AVAILABILITY_STATE] = result.get("availability", "UNKNOWN")
        if result.get("ok"):
            _apply_success(clean, result)
            succeed(st.session_state, CONNECTION_PREFIX, str(result.get("message") or "Finnhub connected."))
        else:
            # Failed candidate validation never leaves an unverified token active.
            st.session_state[KEY_STATE] = ""
            st.session_state[CONNECTED_STATE] = False
            st.session_state[CLIENT_STATE] = ""
            st.session_state[VALIDATION_STATE] = ""
            st.session_state[NEWS_STATE] = []
            st.session_state[NEWS_TIME_STATE] = 0.0
            safe = _redact(result.get("message", "Connection failed"), clean)
            st.session_state[ERROR_STATE] = safe
            fail(st.session_state, CONNECTION_PREFIX, safe)
        return result
    except Exception as exc:
        safe = _redact(exc, clean)
        st.session_state[CONNECTED_STATE] = False
        st.session_state[ERROR_STATE] = safe
        fail(st.session_state, CONNECTION_PREFIX, safe)
        return {"ok": False, "message": safe, "availability": "UNAVAILABLE"}


def test_connection(candidate_key: str = "") -> Dict[str, Any]:
    """One-click idempotent test; a valid candidate is saved and connected."""
    initialize_finnhub_state()
    from core.connector_state_machine_20260621 import begin, fail, succeed
    if not begin(st.session_state, CONNECTION_PREFIX):
        return {"ok": False, "duplicate_blocked": True, "message": "Finnhub connection is already in progress.", "availability": "CONNECTING"}
    candidate = normalize_api_key(candidate_key)
    key = candidate or get_session_key()
    try:
        if not key:
            result = {"ok": False, "message": "Enter a Finnhub API key first.", "availability": "UNAVAILABLE"}
        else:
            result = validate_connection(key)
        st.session_state[LAST_TEST_STATE] = _utc_now_text()
        st.session_state[AVAILABILITY_STATE] = result.get("availability", "UNKNOWN")
        if result.get("ok"):
            _apply_success(key, result)
            succeed(st.session_state, CONNECTION_PREFIX, str(result.get("message") or "Finnhub connected."))
        else:
            st.session_state[CONNECTED_STATE] = bool(get_session_key() and st.session_state.get(CONNECTED_STATE))
            safe = _redact(result.get("message"), key)
            st.session_state[ERROR_STATE] = safe
            fail(st.session_state, CONNECTION_PREFIX, safe)
        return result
    except Exception as exc:
        safe = _redact(exc, key)
        st.session_state[ERROR_STATE] = safe
        fail(st.session_state, CONNECTION_PREFIX, safe)
        return {"ok": False, "message": safe, "availability": "UNAVAILABLE"}


def disconnect() -> None:
    initialize_finnhub_state()
    for key in (KEY_STATE, CLIENT_STATE, VALIDATION_STATE):
        st.session_state[key] = ""
    st.session_state[CONNECTED_STATE] = False
    st.session_state[AVAILABILITY_STATE] = "DISCONNECTED"
    st.session_state[ERROR_STATE] = ""
    st.session_state[NEWS_MODE_STATE] = "forex"
    st.session_state[NEWS_STATE] = []
    st.session_state[NEWS_TIME_STATE] = 0.0
    st.session_state["finnhub_clear_widget_pending"] = True
    try:
        from core.connector_state_machine_20260621 import disconnect as mark_disconnected
        mark_disconnected(st.session_state, CONNECTION_PREFIX, "Finnhub disconnected for this session.")
    except Exception:
        pass


def _safe_news_rows(payload: Any, *, category: str) -> List[Dict[str, Any]]:
    rows = payload if isinstance(payload, list) else []
    safe_rows: List[Dict[str, Any]] = []
    for row in rows[:250]:
        if not isinstance(row, dict):
            continue
        safe_rows.append({
            "id": row.get("id"),
            "headline": str(row.get("headline") or ""),
            "summary": str(row.get("summary") or ""),
            "source": str(row.get("source") or "Finnhub"),
            "url": str(row.get("url") or ""),
            "datetime": row.get("datetime"),
            "category": str(row.get("category") or category),
            "related": str(row.get("related") or ""),
            "image": str(row.get("image") or ""),
        })
    return safe_rows


def fetch_market_news(category: str = "forex", *, force: bool = False, ttl_seconds: int = 900) -> List[Dict[str, Any]]:
    """Fetch and merge existing Finnhub categories into a retained 25-day cache.

    Refreshes never replace a larger valid cache with one article.  The existing
    forex/general endpoints are merged, deduplicated and newest-sorted.
    """
    initialize_finnhub_state()
    key = get_session_key()
    if not key or not st.session_state.get(CONNECTED_STATE):
        cached = st.session_state.get(NEWS_STATE, [])
        return cached if isinstance(cached, list) else []
    cached = st.session_state.get(NEWS_STATE, [])
    cached = cached if isinstance(cached, list) else []
    age = time.time() - float(st.session_state.get(NEWS_TIME_STATE, 0.0) or 0.0)
    if not force and cached and age < max(60, int(ttl_seconds)):
        return cached

    requested = str(category or "forex").strip().lower() or "forex"
    preferred = str(st.session_state.get(NEWS_MODE_STATE, "forex") or "forex")
    categories: List[str] = []
    for item in (requested if preferred == "forex" else preferred, "forex", "general"):
        if item and item not in categories:
            categories.append(item)

    fresh: List[Dict[str, Any]] = []
    last_error: Optional[Exception] = None
    successful_category = ""
    for current_category in categories:
        try:
            payload = _request_json("news", key, {"category": current_category, "minId": 0})
            rows = _safe_news_rows(payload, category=current_category)
            fresh.extend(rows)
            successful_category = successful_category or current_category
        except FinnhubRequestError as exc:
            last_error = exc
            if exc.auth_invalid:
                st.session_state[CONNECTED_STATE] = False
                st.session_state[AVAILABILITY_STATE] = "UNAVAILABLE"
                break
            if exc.rate_limited:
                st.session_state[AVAILABILITY_STATE] = "RATE_LIMITED"
                break
            continue
        except Exception as exc:
            last_error = exc
            continue

    combined = fresh + cached
    cutoff = int(time.time()) - 25 * 86400
    seen: set[str] = set()
    merged: List[Dict[str, Any]] = []
    for row in sorted(combined, key=lambda r: int(r.get("datetime") or 0), reverse=True):
        if not isinstance(row, dict):
            continue
        timestamp = int(row.get("datetime") or 0)
        if timestamp and timestamp < cutoff:
            continue
        fingerprint = str(row.get("id") or row.get("url") or (str(row.get("headline") or "").strip().lower() + "|" + str(row.get("source") or "").strip().lower()))
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint); merged.append(row)
        if len(merged) >= 250:
            break
    if merged:
        st.session_state[NEWS_STATE] = merged
        st.session_state[NEWS_TIME_STATE] = time.time()
        st.session_state[NEWS_MODE_STATE] = successful_category or requested
        st.session_state[ERROR_STATE] = ""
        st.session_state[AVAILABILITY_STATE] = "AVAILABLE"
        return merged
    st.session_state[ERROR_STATE] = _redact(last_error or "Finnhub news request returned no articles", key)
    return cached


def _safe_rerun() -> None:
    if "research_inner_tab" in st.session_state:
        st.session_state["research_inner_tab"] = st.session_state.get("research_inner_tab", "Data Analysis")
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def _connect_button_callback(widget_key: str) -> None:
    candidate = normalize_api_key(st.session_state.get(widget_key, ""))
    effective = candidate or get_session_key()
    if candidate:
        try:
            from core.connectors.credential_vault import save_credential
            save_credential("FINNHUB", candidate)
        except Exception:
            pass
    result = connect(effective)
    try:
        from core.connectors.credential_vault import mark_connection
        mark_connection("FINNHUB", connected=bool(result.get("ok")), status=str(result.get("availability") or result.get("status") or "VALIDATED"))
    except Exception:
        pass


def _test_button_callback(widget_key: str) -> None:
    test_connection(normalize_api_key(st.session_state.get(widget_key, "")))


def _disconnect_button_callback(generation: int) -> None:
    disconnect()
    st.session_state["finnhub_widget_generation"] = int(generation) + 1


def render_finnhub_connector(*, location: str = "sidebar") -> None:
    """Render secure status plus an optional temporary replacement field."""
    initialize_finnhub_state()
    if st.session_state.pop("finnhub_clear_widget_pending", False):
        for k in list(st.session_state.keys()):
            if str(k).startswith("finnhub_key_input_"):
                st.session_state.pop(k, None)
    status = connection_status()
    generation = int(st.session_state.get("finnhub_widget_generation", 0) or 0)
    widget_key = f"finnhub_key_input_{location}_{generation}"
    stored_key = get_session_key()
    try:
        from core.secure_api_startup_20260619 import secure_secret_status
        secret_state = secure_secret_status(st.session_state)
    except Exception:
        secret_state = {"finnhub_configured": bool(stored_key), "finnhub_source": "Temporary session replacement" if stored_key else "Not configured"}

    st.markdown("#### Finnhub API Connector")
    if secret_state.get("finnhub_configured"):
        st.success(f"Finnhub API: ✅ Configured securely ({secret_state.get('finnhub_source', 'server-side')})")
    else:
        st.info("Finnhub API: not configured. Add it to Streamlit Secrets or use a temporary replacement below.")
    st.caption("The actual key is never placed into a widget value, export, log, URL, copy payload, or browser storage.")

    replace_key = st.toggle(
        "Use temporary replacement Finnhub key",
        value=(str(location).lower() == "settings"),
        key=f"finnhub_replace_toggle_{location}",
        help="Use only to replace/test the server-side key for this session. The stored secret remains hidden.",
    )
    candidate = ""
    if replace_key:
        if str(location).lower() == "settings":
            candidate = st.text_area(
                "Finnhub API key — mobile paste box",
                key=widget_key,
                height=74,
                placeholder="Long press here, paste a temporary replacement token, then press Connect",
                help="This field is intentionally blank and never autofills a stored secret.",
            )
        else:
            candidate = st.text_input(
                "Finnhub API key", type="password", key=widget_key,
                placeholder="Paste a temporary replacement token",
            )
    typed_key = normalize_api_key(candidate)
    effective_key = typed_key or stored_key
    connector_state = str(status.get("state") or "DISCONNECTED")
    c1, c2 = st.columns(2)
    c1.button(
        "Save + Validate + Connect (One Click)" if replace_key else "Validate + Connect (One Click)",
        key=f"finnhub_connect_{location}", use_container_width=True,
        disabled=not bool(effective_key) or connector_state == "CONNECTING",
        on_click=_connect_button_callback, args=(widget_key,),
    )
    c2.button(
        "Disconnect session", key=f"finnhub_disconnect_{location}", use_container_width=True,
        disabled=connector_state == "CONNECTING" or not bool(status.get("connected") or st.session_state.get(KEY_STATE)),
        on_click=_disconnect_button_callback, args=(generation,),
    )

    status = connection_status()
    m1, m2 = st.columns(2)
    m1.metric("Connection", str(status.get("state") or ("CONNECTED" if status["connected"] else "DISCONNECTED")))
    m2.metric("API", status.get("availability", "UNKNOWN"))
    endpoint = str(status.get("validation_endpoint") or "")
    if endpoint:
        st.caption(f"Validated with: {endpoint.replace('_', ' ').title()} · News mode: {status.get('news_mode', 'forex').title()}")
    st.caption(f"Last successful connection: {status.get('last_success', 'Never')}")
    st.caption(f"Last test attempt: {status.get('last_test', 'Never')}")
    if status.get("error"):
        st.warning(_redact(status["error"], effective_key))
        availability = str(status.get("availability") or "")
        if availability == "RATE_LIMITED":
            st.caption("Wait about one minute, then press Connect once. The key is not automatically treated as invalid.")
        elif availability == "PLAN_RESTRICTED":
            st.caption("The key was not marked invalid. Check the Finnhub account plan or use cached/local NLP.")
        else:
            st.caption("Copy only the token value from the Finnhub dashboard, without quotes or a label, then press Connect once.")

def render_finnhub_status_compact(*, location: str = "sidebar") -> None:
    """Display connection status only; API-key entry remains in Settings."""
    del location
    initialize_finnhub_state()
    status = connection_status()
    c1, c2 = st.columns(2)
    c1.metric("Finnhub", "CONNECTED" if status.get("connected") else "DISCONNECTED")
    c2.metric("API", status.get("availability", "UNKNOWN"))
    st.caption("Configure or change the Finnhub API key in Settings. This compact panel never renders a key input.")
    st.caption(f"Last successful connection: {status.get('last_success', 'Never')}")
    if status.get("error"):
        st.warning(_redact(str(status.get("error")), get_session_key()))
