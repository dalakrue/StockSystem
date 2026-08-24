"""Process-bounded TinyLFU display cache.

Only compact reusable display artifacts are admitted. Keys are caller-created
metadata identifiers and must never contain API keys, credentials or raw user
questions. One-time exports are explicitly excluded.
"""
from __future__ import annotations

from threading import RLock
from typing import Any, Callable

from core.research_evidence_algorithms_20260620 import TinyLFUCache

_LOCK = RLock()
_CACHE = TinyLFUCache(max_entries=48, max_bytes=12_000_000, sample_size=4096)


def get_or_prepare(key: str, builder: Callable[[], Any], *, size_bytes: Callable[[Any], int] | None = None) -> tuple[Any, str]:
    safe_key = str(key)
    with _LOCK:
        cached = _CACHE.get(safe_key, default=None)
        if cached is not None:
            return cached, "HIT"
    value = builder()
    try:
        estimated = int(size_bytes(value)) if callable(size_bytes) else 1
    except Exception:
        estimated = 1
    with _LOCK:
        admitted = _CACHE.put(safe_key, value, size_bytes=max(1, estimated))
    return value, "MISS_ADMITTED" if admitted else "MISS_NOT_ADMITTED"


def diagnostics() -> dict[str, Any]:
    with _LOCK:
        return dict(_CACHE.diagnostics())


__all__ = ["get_or_prepare", "diagnostics"]
