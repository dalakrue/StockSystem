"""Lamport-style generation ordering for display caches and read-only analyses."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping, MutableMapping

LOGIC_VERSION = "generation-order-guard-20260622-v1"


def _int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def generation_identity(canonical: Mapping[str, Any]) -> dict[str, Any]:
    calculation_id = str(
        canonical.get("calculation_id") or canonical.get("canonical_calculation_id")
        or canonical.get("run_id") or "UNAVAILABLE"
    )
    return {
        "calculation_id": calculation_id,
        "generation": _int(canonical.get("calculation_generation") or canonical.get("generation")),
        "latest_completed_h1_utc": canonical.get("latest_completed_h1_utc") or canonical.get("latest_completed_candle_time"),
        "symbol": str(canonical.get("symbol") or "EURUSD"),
        "timeframe": str(canonical.get("timeframe") or "H1"),
    }


def generation_cache_key(*, canonical: Mapping[str, Any], namespace: str, extra: Mapping[str, Any] | None = None) -> str:
    payload = {"namespace": namespace, **generation_identity(canonical), "extra": dict(extra or {}), "logic_version": LOGIC_VERSION}
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8", "ignore")).hexdigest()[:32]


def compare_generation(candidate: Mapping[str, Any], active: Mapping[str, Any]) -> int:
    """Return -1 older, 0 same, +1 newer; calculation IDs break ambiguous ties."""
    candidate_id = generation_identity(candidate)
    active_id = generation_identity(active)
    if candidate_id["generation"] < active_id["generation"]:
        return -1
    if candidate_id["generation"] > active_id["generation"]:
        return 1
    if candidate_id["calculation_id"] == active_id["calculation_id"]:
        return 0
    # Same logical clock but different IDs is a conflict, never an overwrite.
    return -1


def publish_if_not_older(
    state: MutableMapping[str, Any],
    *,
    key: str,
    value: Any,
    candidate: Mapping[str, Any],
    identity_key: str | None = None,
) -> bool:
    identity_key = identity_key or f"{key}__generation_identity"
    current_identity = state.get(identity_key)
    if isinstance(current_identity, Mapping) and compare_generation(candidate, current_identity) < 0:
        state[f"{key}__stale_rejection"] = {
            "candidate": generation_identity(candidate), "active": generation_identity(current_identity),
            "reason": "older generation cannot overwrite newer cache", "logic_version": LOGIC_VERSION,
        }
        return False
    state[key] = value
    state[identity_key] = generation_identity(candidate)
    return True


def active_generation_matches(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    a, b = generation_identity(before), generation_identity(after)
    return a["calculation_id"] == b["calculation_id"] and a["generation"] == b["generation"]


__all__ = [
    "LOGIC_VERSION", "generation_identity", "generation_cache_key", "compare_generation",
    "publish_if_not_older", "active_generation_matches",
]
