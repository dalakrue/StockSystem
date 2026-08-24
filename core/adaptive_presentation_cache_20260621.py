"""Small session-local recency/frequency-aware presentation cache.

This is ARC-inspired rather than a literal ARC implementation: it balances hit
frequency and recency while keeping a strict item count and byte estimate. It is
used only for reconstructable UI payloads, never canonical calculations.
"""
from __future__ import annotations

import json
import time
from typing import Any, MutableMapping

CACHE_KEY = "adaptive_presentation_cache_20260621"
MAX_ITEMS = 32
MAX_BYTES = 2_000_000


def _size(value: Any) -> int:
    try:
        return len(json.dumps(value, default=str, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return 1024


def _cache(state: MutableMapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = state.get(CACHE_KEY)
    if not isinstance(raw, dict):
        raw = {}
        state[CACHE_KEY] = raw
    return raw


def cache_get(state: MutableMapping[str, Any], key: str) -> Any | None:
    cache = _cache(state)
    item = cache.get(str(key))
    if not isinstance(item, dict):
        return None
    item["hits"] = int(item.get("hits", 0)) + 1
    item["last_access"] = time.time()
    return item.get("value")


def cache_put(state: MutableMapping[str, Any], key: str, value: Any) -> None:
    cache = _cache(state)
    now = time.time()
    cache[str(key)] = {
        "value": value,
        "hits": int(cache.get(str(key), {}).get("hits", 0)) + 1,
        "created": float(cache.get(str(key), {}).get("created", now)),
        "last_access": now,
        "size": _size(value),
    }
    while len(cache) > MAX_ITEMS or sum(int(v.get("size", 0)) for v in cache.values() if isinstance(v, dict)) > MAX_BYTES:
        victim = min(
            cache,
            key=lambda k: (
                int(cache[k].get("hits", 0)),
                float(cache[k].get("last_access", 0.0)),
                float(cache[k].get("created", 0.0)),
            ),
        )
        cache.pop(victim, None)


def clear_reconstructable(state: MutableMapping[str, Any]) -> int:
    cache = state.pop(CACHE_KEY, None)
    return len(cache) if isinstance(cache, dict) else 0


def cache_stats(state: MutableMapping[str, Any]) -> dict[str, int]:
    cache = state.get(CACHE_KEY)
    if not isinstance(cache, dict):
        return {"entries": 0, "estimated_bytes": 0}
    return {
        "entries": len(cache),
        "estimated_bytes": sum(int(v.get("size", 0)) for v in cache.values() if isinstance(v, dict)),
    }


__all__ = ["cache_get", "cache_put", "clear_reconstructable", "cache_stats", "CACHE_KEY"]
