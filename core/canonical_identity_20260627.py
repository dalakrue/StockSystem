"""Strict immutable canonical identity and completed-H1 validation.

This module is presentation/orchestration infrastructure only.  It does not
calculate a decision, forecast, or historical row.  It normalizes aliases from
one already-published generation and validates that consumers read that exact
identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from datetime import timedelta, timezone
import re
from typing import Any, Mapping

import pandas as pd



_BROKER_DISPLAY_RE = re.compile(
    r"^\s*(?P<stamp>.+?)\s*\(Broker\s+UTC(?P<sign>[+-])(?P<hours>\d{1,2})(?::?(?P<minutes>\d{2}))?\)\s*$",
    re.IGNORECASE,
)


def _parse_broker_display(value: Any) -> tuple[Any, Any | None]:
    """Return timestamp text and an explicit fixed offset from UI broker displays.

    Published snapshots in this project historically used values such as
    ``2026-06-22 07:00:00 (Broker UTC+3)``.  This is an explicit broker clock,
    not local-PC time, so it is safe to normalize before pandas parsing.
    """
    if not isinstance(value, str):
        return value, None
    match = _BROKER_DISPLAY_RE.match(value)
    if not match:
        return value, None
    hours = int(match.group("hours"))
    minutes = int(match.group("minutes") or 0)
    if hours > 23 or minutes > 59:
        raise CanonicalIntegrityError("completed_broker_candle has an invalid broker UTC offset")
    total = hours * 60 + minutes
    if match.group("sign") == "-":
        total = -total
    return match.group("stamp").strip(), timezone(timedelta(minutes=total))


class CanonicalIntegrityError(ValueError):
    """Raised when a published canonical identity is malformed."""


class ProjectionState(str, Enum):
    VALID = "VALID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    STALE = "STALE"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    PATH_UNAVAILABLE = "PATH_UNAVAILABLE"
    PUBLICATION_INCOMPLETE = "PUBLICATION_INCOMPLETE"


@dataclass(frozen=True)
class CanonicalIdentity:
    run_id: str
    generation_id: str
    symbol: str
    timeframe: str
    completed_broker_candle: pd.Timestamp
    source_snapshot_hash: str
    source_signature: str

    def as_dict(self) -> dict[str, Any]:
        stamp = self.completed_broker_candle
        return {
            "run_id": self.run_id,
            "generation_id": self.generation_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "completed_broker_candle": stamp,
            "completed_broker_candle_iso": stamp.isoformat(),
            "source_snapshot_hash": self.source_snapshot_hash,
            "source_signature": self.source_signature,
        }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def canonical_timestamp_value(canonical: Mapping[str, Any]) -> Any:
    market = _mapping(canonical.get("market"))
    metadata = _mapping(canonical.get("metadata"))
    return (
        _first(
            canonical,
            "completed_broker_candle",
            "broker_candle_time",
            "latest_completed_candle_time",
            "latest_completed_h1_utc",
            "completed_candle_utc",
            "candle_time",
            "completed_candle_identity",
        )
        or _first(
            market,
            "completed_broker_candle",
            "broker_candle_time",
            "latest_completed_candle_time",
            "latest_completed_h1_utc",
            "completed_candle_utc",
        )
        or _first(
            metadata,
            "completed_broker_candle",
            "broker_candle_time",
            "latest_completed_candle_time",
            "latest_completed_h1_utc",
        )
    )


def _broker_tz(state: Mapping[str, Any] | None, event_time: Any = None):
    if state is None:
        return "UTC"
    try:
        from core.shared_broker_time_20260622 import resolve_broker_clock

        resolved = resolve_broker_clock(state, event_time_utc=event_time)
        return resolved.get("broker_tzinfo") or "UTC"
    except Exception:
        return "UTC"


def parse_completed_broker_candle(
    value: Any,
    *,
    state: Mapping[str, Any] | None = None,
    require_h1_alignment: bool = True,
) -> pd.Timestamp:
    """Parse one authoritative completed candle into UTC.

    A timezone-naive value is interpreted in the configured MetaTrader broker
    timezone; it is never interpreted using the local PC/browser timezone.
    """
    if value in (None, ""):
        raise CanonicalIntegrityError("completed_broker_candle is missing")
    try:
        parsed_value, explicit_broker_tz = _parse_broker_display(value)
        stamp = pd.Timestamp(parsed_value)
    except CanonicalIntegrityError:
        raise
    except Exception as exc:
        raise CanonicalIntegrityError("completed_broker_candle is malformed") from exc
    if pd.isna(stamp):
        raise CanonicalIntegrityError("completed_broker_candle is NaT")
    if stamp.tzinfo is None:
        try:
            stamp = stamp.tz_localize(explicit_broker_tz or _broker_tz(state, stamp))
        except Exception as exc:
            raise CanonicalIntegrityError("completed_broker_candle timezone could not be resolved") from exc
    if require_h1_alignment and any((stamp.minute, stamp.second, stamp.microsecond, stamp.nanosecond)):
        raise CanonicalIntegrityError("completed_broker_candle is not H1 aligned")
    try:
        stamp = stamp.tz_convert("UTC")
    except Exception as exc:
        raise CanonicalIntegrityError("completed_broker_candle is not timezone-aware") from exc
    return stamp


def normalize_identity_aliases(
    canonical: Mapping[str, Any], state: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Return a copy with all identity aliases bound to one value."""
    out = dict(canonical)
    market = _mapping(out.get("market"))
    run_id = _first(out, "run_id", "canonical_calculation_id", "calculation_id")
    generation = _first(out, "generation_id", "calculation_generation", "generation")
    snapshot_hash = _first(out, "source_snapshot_hash", "snapshot_hash", "checksum", "data_signature")
    signature = _first(out, "source_signature", "signature")
    candle_raw = canonical_timestamp_value(out)
    if candle_raw not in (None, ""):
        stamp = parse_completed_broker_candle(candle_raw, state=state)
        out["completed_broker_candle"] = stamp
        out["broker_candle_time"] = stamp
        out["latest_completed_candle_time"] = stamp
        out["latest_completed_h1_utc"] = stamp
        out["completed_candle_utc"] = stamp
    if run_id not in (None, ""):
        out["run_id"] = str(run_id)
        out["canonical_calculation_id"] = str(run_id)
    if generation not in (None, ""):
        out["generation_id"] = str(generation)
        out["calculation_generation"] = str(generation)
    if snapshot_hash not in (None, ""):
        out["source_snapshot_hash"] = str(snapshot_hash)
        out["snapshot_hash"] = str(snapshot_hash)
    if signature not in (None, ""):
        out["source_signature"] = str(signature)
    out["symbol"] = str(_first(out, "symbol") or _first(market, "symbol") or (state or {}).get("symbol") or "EURUSD")
    out["timeframe"] = str(_first(out, "timeframe") or _first(market, "timeframe") or (state or {}).get("timeframe") or "H1")
    return out


def build_canonical_identity(
    canonical: Mapping[str, Any],
    *,
    state: Mapping[str, Any] | None = None,
    require_complete: bool = True,
) -> CanonicalIdentity:
    normalized = normalize_identity_aliases(canonical, state)
    values = {
        "run_id": str(normalized.get("run_id") or ""),
        "generation_id": str(normalized.get("generation_id") or ""),
        "symbol": str(normalized.get("symbol") or ""),
        "timeframe": str(normalized.get("timeframe") or ""),
        "source_snapshot_hash": str(normalized.get("source_snapshot_hash") or ""),
        "source_signature": str(normalized.get("source_signature") or ""),
    }
    missing = [name for name, value in values.items() if not value]
    if require_complete and missing:
        raise CanonicalIntegrityError("canonical identity is incomplete: " + ", ".join(missing))
    stamp = parse_completed_broker_candle(
        normalized.get("completed_broker_candle"), state=state
    )
    return CanonicalIdentity(completed_broker_candle=stamp, **values)


def component_identity(component: Mapping[str, Any], fallback: Mapping[str, Any] | None = None) -> dict[str, str]:
    summary = _mapping(component.get("summary"))
    fallback = fallback or {}
    return {
        "run_id": str(_first(component, "run_id", "source_run_id") or _first(summary, "run_id", "source_run_id") or fallback.get("run_id") or ""),
        "generation_id": str(_first(component, "generation_id", "calculation_generation") or _first(summary, "generation_id", "calculation_generation") or fallback.get("generation_id") or ""),
        "symbol": str(_first(component, "symbol") or _first(summary, "symbol") or fallback.get("symbol") or ""),
        "timeframe": str(_first(component, "timeframe") or _first(summary, "timeframe") or fallback.get("timeframe") or ""),
        "source_snapshot_hash": str(_first(component, "source_snapshot_hash", "snapshot_hash") or _first(summary, "source_snapshot_hash", "snapshot_hash") or fallback.get("source_snapshot_hash") or ""),
        "source_signature": str(_first(component, "source_signature") or _first(summary, "source_signature") or fallback.get("source_signature") or ""),
    }


def identity_mismatches(component: Mapping[str, Any], identity: CanonicalIdentity) -> list[str]:
    expected = identity.as_dict()
    observed = component_identity(component)
    mismatches: list[str] = []
    for key in ("run_id", "generation_id", "symbol", "timeframe", "source_snapshot_hash", "source_signature"):
        value = observed.get(key, "")
        if not value:
            mismatches.append(f"{key} is missing from the component publication")
        elif str(value) != str(expected[key]):
            mismatches.append(f"{key} does not match the canonical generation")
    raw_stamp = canonical_timestamp_value(component) or canonical_timestamp_value(_mapping(component.get("summary")))
    if raw_stamp in (None, ""):
        mismatches.append("completed_broker_candle is missing from the component publication")
    else:
        try:
            observed_stamp = parse_completed_broker_candle(raw_stamp)
            if observed_stamp != identity.completed_broker_candle:
                mismatches.append("completed_broker_candle does not match the canonical generation")
        except CanonicalIntegrityError as exc:
            mismatches.append(str(exc))
    return mismatches


__all__ = [
    "CanonicalIdentity",
    "CanonicalIntegrityError",
    "ProjectionState",
    "build_canonical_identity",
    "canonical_timestamp_value",
    "component_identity",
    "identity_mismatches",
    "normalize_identity_aliases",
    "parse_completed_broker_candle",
]
