"""Process-level once-registry for app startup work (2026-11-28).

Streamlit re-executes the entry script on every rerun, so a guard
kept in the script's own globals does not survive; a registry in an
imported module does (sys.modules lives for the process). Used by
app.py to run the startup DB migrations once per DB file version
per process instead of on every rerun: the migrations are additive
and idempotent, but two of them re-scan the whole candle store on
every call (~49 s on a small VM), which made every app open wait
on work that was already done.
"""
from __future__ import annotations

import threading
from typing import Any

_LOCK = threading.Lock()
_CLAIMED: dict[str, Any] = {}


def claim(key: str, stamp: Any) -> bool:
    """Return True exactly once per (key, stamp) in this process.

    The caller that gets True owns the work for that stamp; every
    later caller with the same stamp gets False. A different stamp
    (e.g. the DB file was replaced by the cache restore) claims
    again, so the work still runs once per file version.
    """
    with _LOCK:
        if key in _CLAIMED and _CLAIMED[key] == stamp:
            return False
        _CLAIMED[key] = stamp
        return True


__all__ = ["claim"]
