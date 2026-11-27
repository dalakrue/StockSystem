"""OpenRouter one-line narration (user order 2026-11-28: the
three-API combine — Twelve = data, Finnhub = verification +
context, OpenRouter = words).

Turns a machine verdict the app already computed into ONE
short plain sentence a trader can read at a glance:

- "verification_stamp": the Finnhub cross-check verdict under
  a calculated check (section 1),
- "replay_different": why a Replay calculation differs from
  the recorded past (section 3 compare),
- "similarity": the Memory Building report's similarity
  sentence (section 4).

Dormant by default: it does nothing unless a key is configured
in the app's Streamlit secrets as::

    [openrouter]
    api_key = "..."

Safety contract (same as the save-back): NEVER raises, one
attempt, short timeout, no retries. With no key — or on any
failure — one_line() returns the caller's fallback (usually
None), so every section renders exactly its existing plain
template text. Results are cached per (kind, facts) for the
life of the process, and callers cache on their result dicts,
so a re-render never re-calls.
"""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "openai/gpt-4o-mini"
_TIMEOUT_S = 10.0

_CACHE: dict[str, str] = {}

_SYSTEM = (
    "You write ONE short plain sentence for a forex trading "
    "app, from the facts given. Plain words, no markdown, no "
    "quotes, no exclamation marks, at most 22 words. State "
    "only what the facts support; never invent prices, "
    "symbols or reasons not in the facts.")

_KIND_HINTS = {
    "verification_stamp": (
        "This is the data-verification stamp under a "
        "calculated trade check: say whether the two data "
        "feeds agreed on the signal bar and what that means "
        "for trusting the signal."),
    "replay_different": (
        "This explains why a fresh recalculation of a past "
        "check differs from what was recorded at the time: "
        "say what differed and the most likely plain reason "
        "the facts support (different data source or the "
        "walked memory's path)."),
    "similarity": (
        "This summarises how similar a freshly built month "
        "of trading memory is to the stored past: say the "
        "similarity plainly and what the differences mean."),
}


def _api_key():
    """OpenRouter key from Streamlit secrets, else None.
    Never raises; None outside Streamlit or with nothing
    configured."""
    try:
        import streamlit as st
        secrets = st.secrets
    except Exception:
        return None
    try:
        section = secrets["openrouter"]
        if isinstance(section, dict):
            for field in ("api_key", "token", "key"):
                val = section.get(field)
                if val and str(val).strip():
                    return str(val).strip()
        elif isinstance(section, str) and section.strip():
            return section.strip()
    except Exception:
        pass
    try:
        val = secrets["OPENROUTER_API_KEY"]
        if val and str(val).strip():
            return str(val).strip()
    except Exception:
        pass
    return None


def is_configured():
    return _api_key() is not None


def _http_post(url, token, payload):
    """One POST attempt; returns (status, parsed_json_or_None)
    for every HTTP response. Raises only on transport failure;
    callers swallow. Module-level so tests can monkeypatch the
    whole HTTP layer here."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json",
                 "User-Agent": "stocksystem-narration/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
            parsed = json.loads(body) if body else None
        except Exception:
            parsed = None
        return e.code, parsed


def one_line(kind, facts, fallback=None, token=None):
    """One narrated sentence for `kind` from `facts` (a dict
    of plain values), or `fallback` when narration is not
    configured or anything fails. Never raises."""
    try:
        if token is None:
            token = _api_key()
        if not token:
            return fallback
        cache_key = hashlib.sha256(
            (kind + "|" + json.dumps(
                facts, sort_keys=True, default=str)
             ).encode("utf-8")).hexdigest()
        if cache_key in _CACHE:
            return _CACHE[cache_key]
        hint = _KIND_HINTS.get(kind, "")
        user = (f"{hint}\nFacts: "
                f"{json.dumps(facts, default=str)}")
        payload = {
            "model": _MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user}],
            "max_tokens": 60,
            "temperature": 0.2,
        }
        status, parsed = _http_post(_API_URL, token, payload)
        if status != 200 or not isinstance(parsed, dict):
            return fallback
        choices = parsed.get("choices") or []
        if not choices:
            return fallback
        text = str(
            (choices[0].get("message") or {}).get("content")
            or "").strip()
        text = " ".join(text.split())[:220].strip()
        if not text:
            return fallback
        _CACHE[cache_key] = text
        return text
    except Exception:
        return fallback
