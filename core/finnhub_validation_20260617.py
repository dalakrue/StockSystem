"""Pure Finnhub key normalization and response classification.

This module deliberately has no Streamlit, network, logging, cache, database or
filesystem dependency, so it can be imported and tested without exposing a key.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

_ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff"
_INVALID_KEY_MARKERS = (
    "invalid api key", "api key is invalid", "invalid token", "token is invalid",
    "please use an api key", "missing api key", "authentication failed", "unauthorized",
)
_ENTITLEMENT_MARKERS = (
    "premium", "subscription", "not available on your plan", "upgrade your plan",
    "permission", "access denied", "do not have access", "doesn't have access",
)
_RATE_LIMIT_MARKERS = ("rate limit", "api limit", "too many requests")


def normalize_api_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.translate({ord(ch): None for ch in _ZERO_WIDTH}).strip()
    if not text:
        return ""
    if text.lower().startswith(("http://", "https://")):
        try:
            query = parse_qs(urlparse(text).query)
            for name in ("token", "api_key", "apikey", "api-key"):
                if query.get(name):
                    text = str(query[name][0])
                    break
        except Exception:
            pass
    text = text.strip().strip("`\"'").strip()
    match = re.match(r"(?is)^(?:token|api[_-]?key)\s*[:=]\s*(.+)$", text)
    if match:
        text = match.group(1).strip().strip("`\"'").strip()
    return re.sub(r"\s+", "", text)


def validate_key_format(value: Any) -> Dict[str, Any]:
    clean = normalize_api_key(value)
    if not clean:
        return {"ok": False, "reason": "EMPTY", "normalized_key": ""}
    if len(clean) < 8:
        return {"ok": False, "reason": "INVALID_FORMAT", "normalized_key": clean}
    return {"ok": True, "reason": "FORMAT_OK", "normalized_key": clean}


def classify_response(status_code: int, server_message: Any = "") -> Dict[str, Any]:
    lower = str(server_message or "").lower()
    if int(status_code) == 429 or any(marker in lower for marker in _RATE_LIMIT_MARKERS):
        return {"kind": "RATE_LIMITED", "retryable": True, "auth_invalid": False, "entitlement_denied": False}
    if int(status_code) == 401 or any(marker in lower for marker in _INVALID_KEY_MARKERS):
        return {"kind": "AUTH_INVALID", "retryable": False, "auth_invalid": True, "entitlement_denied": False}
    if int(status_code) == 403:
        return {
            "kind": "ENTITLEMENT_DENIED", "retryable": False, "auth_invalid": False,
            "entitlement_denied": any(marker in lower for marker in _ENTITLEMENT_MARKERS) or not lower,
        }
    if int(status_code) in {408, 425, 500, 502, 503, 504}:
        return {"kind": "TEMPORARY", "retryable": True, "auth_invalid": False, "entitlement_denied": False}
    return {"kind": "HTTP_ERROR", "retryable": int(status_code) >= 500, "auth_invalid": False, "entitlement_denied": False}
