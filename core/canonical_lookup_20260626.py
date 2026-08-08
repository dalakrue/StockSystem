"""Read-only canonical generation lookup for presentation consumers.

The protected canonical publisher remains authoritative.  This adapter only
recovers the same already-published generation from compatible session aliases
when the strict active pointer is temporarily absent during navigation/reruns.
It never calculates, publishes, mutates, or replaces a canonical generation.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, Mapping

_ACTIVE_KEYS = ("canonical_decision_result_20260617",)
_LAST_VALID_KEYS = ("last_valid_canonical_decision_result_20260617",)
_SYNC_KEYS = (
    "canonical_run_snapshot_v9",
    "canonical_run_snapshot_20260619",
    "canonical_sync_snapshot",
    "canonical_run_contract_v10",
)
_ALIAS_KEYS = (
    "canonical_decision_result",
    "canonical_result_20260617",
    "canonical_result",
    "adx_shared_calc_result_20260615",
    "shared_calc_result",
    "runtime_context_20260617",
)
_NESTED_KEYS = (
    "canonical",
    "canonical_result",
    "result",
    "snapshot",
    "run_snapshot",
    "metadata",
    "ai_grounding",
)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        try:
            return asdict(value)
        except Exception:
            return {}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            result = to_dict()
            return dict(result) if isinstance(result, Mapping) else {}
        except Exception:
            return {}
    raw = getattr(value, "__dict__", None)
    return dict(raw) if isinstance(raw, Mapping) else {}


def _expanded(value: Any) -> Iterable[dict[str, Any]]:
    root = _mapping(value)
    if not root:
        return
    yield root
    for key in _NESTED_KEYS:
        nested = _mapping(root.get(key))
        if nested:
            yield nested


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _has_identity(value: Mapping[str, Any]) -> bool:
    market = value.get("market") if isinstance(value.get("market"), Mapping) else {}
    run_id = _first(value, "run_id", "canonical_calculation_id", "calculation_id")
    generation = _first(value, "generation_id", "calculation_generation", "generation")
    candle = _first(
        value,
        "completed_broker_candle",
        "broker_candle_time",
        "latest_completed_candle_time",
        "completed_candle_utc",
        "candle_time",
        "completed_candle_identity",
    ) or _first(market, "completed_broker_candle", "latest_completed_candle_time", "broker_candle_time")
    return bool(run_id and generation and candle)


def _normalized(value: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(value)
    market = out.get("market") if isinstance(out.get("market"), Mapping) else {}
    manifest = state.get("quick_publication_manifest_20260626")
    manifest = manifest if isinstance(manifest, Mapping) else {}
    signature = state.get("quick_source_signature_20260626")
    signature = signature if isinstance(signature, Mapping) else {}

    run_id = _first(out, "run_id", "canonical_calculation_id", "calculation_id")
    generation = _first(out, "generation_id", "calculation_generation", "generation")
    snapshot_hash = _first(out, "source_snapshot_hash", "snapshot_hash", "checksum", "data_signature")
    candle = _first(
        out,
        "completed_broker_candle",
        "broker_candle_time",
        "latest_completed_candle_time",
        "completed_candle_utc",
        "candle_time",
        "completed_candle_identity",
    ) or _first(market, "completed_broker_candle", "latest_completed_candle_time", "broker_candle_time")

    # The quick manifest/signature may augment only the same published identity.
    manifest_matches = not manifest or not run_id or str(manifest.get("run_id") or "") in ("", str(run_id))
    if manifest_matches:
        snapshot_hash = snapshot_hash or _first(manifest, "source_snapshot_hash", "snapshot_hash")
        candle = candle or _first(manifest, "broker_candle_time", "latest_completed_candle_time")
        source_signature = _first(out, "source_signature") or manifest.get("source_signature") or signature.get("source_signature")
    else:
        source_signature = _first(out, "source_signature")

    if run_id is not None:
        out.setdefault("run_id", run_id)
        out.setdefault("canonical_calculation_id", run_id)
    if generation is not None:
        out.setdefault("generation_id", generation)
        out.setdefault("calculation_generation", generation)
    if snapshot_hash is not None:
        out.setdefault("source_snapshot_hash", snapshot_hash)
        out.setdefault("snapshot_hash", snapshot_hash)
    if candle is not None:
        out.setdefault("completed_broker_candle", candle)
        out.setdefault("broker_candle_time", candle)
        out.setdefault("latest_completed_candle_time", candle)
        out.setdefault("latest_completed_h1_utc", candle)
    if source_signature not in (None, ""):
        out.setdefault("source_signature", source_signature)
    out.setdefault("symbol", _first(out, "symbol") or state.get("symbol"))
    out.setdefault("timeframe", _first(out, "timeframe") or state.get("timeframe"))
    return out


def resolve_canonical(state: Mapping[str, Any], preferred: Any = None) -> dict[str, Any]:
    """Return one already-published canonical generation without side effects.

    Lookup order is strict active, last-valid, sync snapshots, then compatible
    aliases.  ``preferred`` is treated as an active caller-provided view only
    when it carries a complete identity.
    """
    candidates: list[Any] = []
    # Preserve the published lookup contract: active first, then last-valid,
    # sync snapshots, and finally compatible aliases.  A caller-provided view
    # may supplement the active group but may never override a valid active
    # canonical generation.
    try:
        from core.canonical_runtime_20260617 import get_canonical
        protected = get_canonical(state)
        if protected:
            candidates.append(protected)
    except Exception:
        pass
    candidates.extend(state.get(key) for key in _ACTIVE_KEYS)
    # Settings status/quick manifest are publication records, not calculations.
    status = state.get("settings_run_status_20260617")
    if isinstance(status, Mapping):
        candidates.extend((status.get("canonical"), status))
    candidates.append(state.get("quick_publication_manifest_20260626"))
    if preferred is not None:
        candidates.append(preferred)
    for group in (_LAST_VALID_KEYS, _SYNC_KEYS, _ALIAS_KEYS):
        candidates.extend(state.get(key) for key in group)

    for candidate in candidates:
        for expanded in _expanded(candidate):
            normalized = _normalized(expanded, state)
            if _has_identity(normalized):
                return normalized

    # Last read-only rescue: search nested publication wrappers for a complete
    # identity. This fixes navigation reruns where the active pointer was lost
    # but the immutable publication remains in session state.
    seen: set[int] = set()
    def walk(value: Any, depth: int = 0):
        if depth > 5 or id(value) in seen:
            return
        seen.add(id(value))
        mapped = _mapping(value)
        if mapped:
            normalized = _normalized(mapped, state)
            if _has_identity(normalized):
                yield normalized
            for child in mapped.values():
                if isinstance(child, Mapping) or is_dataclass(child):
                    yield from walk(child, depth + 1)
    for recovered in walk(state):
        return recovered
    return {}


__all__ = ["resolve_canonical"]
