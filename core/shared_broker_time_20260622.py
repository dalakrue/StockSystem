# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Canonical event-time and MT5 broker-chart clock contract.

UTC remains the identity/storage clock.  Broker and Myanmar clocks are display
projections only.  Broker time is never silently replaced with UTC when the
broker clock is not configured.
"""
from __future__ import annotations

from datetime import timedelta, timezone
import re
from typing import Any, Mapping, MutableMapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

CONTRACT_VERSION = "broker-time-contract-20260630-v4"
BROKER_TIME_UNAVAILABLE = "BROKER TIME UNAVAILABLE — CONFIGURE SETTINGS"

# Date and Hour are deliberately excluded: neither is an authoritative candle
# timestamp.  A DatetimeIndex is accepted after the explicit columns.
_TIME_COLUMNS: tuple[str, ...] = (
    "event_time_utc", "latest_completed_h1_utc", "record_time", "target_time",
    "broker_candle_time", "Broker Candle Time", "Completed Broker Candle",
    "completed_broker_candle", "Broker Candle", "Completed Candle",
    "time", "Time", "Datetime", "DateTime", "Timestamp", "timestamp",
    "candle time", "Candle Time", "candle_time", "latest_completed_h1",
    "latest_completed_candle_time", "anchor_time", "future_time", "Future Time",
    "projection_time", "Projection Time", "target time", "Target Time",
)
_DISPLAY_CLOCK_ALIASES: frozenset[str] = frozenset({
    "broker candle time", "completed broker candle", "completed candle",
    "broker candle", "broker time", "candle time", "time", "datetime", "timestamp",
})
_MANUAL_OFFSET_KEYS: tuple[str, ...] = (
    "manual_broker_offset_minutes_20260622",
    "manual_broker_utc_offset_hours_20260622",
    "mt5_broker_utc_offset_hours_20260622",
    "broker_utc_offset_hours",
    "mt5_server_utc_offset_hours",
)
_IANA_KEYS: tuple[str, ...] = (
    "broker_timezone_iana_20260622", "broker_iana_timezone", "broker_timezone",
    "mt5_broker_timezone", "mt5_broker_timezone_iana",
)

_BRIDGE_TIME_KEYS: tuple[str, ...] = (
    "validated_doo_bridge_broker_timestamp_20260622", "doo_bridge_broker_timestamp",
    "bridge_broker_server_time", "broker_server_timestamp",
)
_BRIDGE_RECEIPT_KEYS: tuple[str, ...] = (
    "validated_doo_bridge_receipt_utc_20260622", "doo_bridge_receipt_utc",
    "bridge_receipt_time_utc", "broker_timestamp_received_at_utc",
)
_PERSISTED_OFFSET_KEYS: tuple[str, ...] = (
    "persisted_broker_offset_minutes_20260622", "last_valid_broker_offset_minutes_20260622",
    "persisted_broker_utc_offset_hours", "last_valid_broker_utc_offset_hours",
)


def _as_utc(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    try:
        parsed = pd.to_datetime(value, errors="coerce", utc=True)
        if isinstance(parsed, pd.Series):
            parsed = parsed.dropna().max() if parsed.notna().any() else pd.NaT
        elif isinstance(parsed, pd.DatetimeIndex):
            parsed = parsed.dropna().max() if len(parsed.dropna()) else pd.NaT
        return None if pd.isna(parsed) else pd.Timestamp(parsed).tz_convert("UTC")
    except Exception:
        return None


def _canonical_from_state(state: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        current = get_canonical(state)
        if isinstance(current, Mapping):
            return current
    except Exception:
        pass
    for key in (
        "canonical_result_20260617", "canonical_decision_result_20260617",
        "canonical_decision_result", "last_valid_canonical_decision_result_20260617",
        "canonical_result",
    ):
        value = state.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _state_with_saved_broker_clock(
    state: Mapping[str, Any],
    canonical: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Recover display-clock evidence from the immutable saved snapshot.

    This is presentation-only. It never changes candle identity, calculations,
    predictions, decisions, strategy rules, or model weights. Explicit Settings
    values remain first priority; saved snapshot evidence is used only when those
    values are absent after a Streamlit rerun/navigation.
    """
    if any(state.get(key) not in (None, "") for key in (*_IANA_KEYS, *_MANUAL_OFFSET_KEYS, *_PERSISTED_OFFSET_KEYS)):
        return state
    merged = dict(state)
    candidates: list[Mapping[str, Any]] = []
    if isinstance(canonical, Mapping):
        candidates.append(canonical)
    for key in ("canonical_run_snapshot_v9", "canonical_run_contract_v10"):
        value = state.get(key)
        if isinstance(value, Mapping):
            candidates.append(value)
    for candidate in candidates:
        timezone_name = candidate.get("broker_timezone_iana") or candidate.get("broker_timezone")
        if timezone_name not in (None, "", "UNAVAILABLE") and "/" in str(timezone_name):
            merged["broker_timezone_iana_20260622"] = str(timezone_name)
            return merged
        display = str(
            candidate.get("shared_broker_time_display")
            or candidate.get("broker_time_display")
            or candidate.get("broker_candle_time")
            or candidate.get("broker_time")
            or ""
        )
        resolution = str(candidate.get("broker_clock_resolution") or candidate.get("resolution_precedence") or "").lower()
        available = candidate.get("broker_clock_available") is True or resolution not in {"", "unavailable", "none"}
        explicit_label = "BROKER UTC" in display.upper() or bool(re.search(r"UTC\s*[+-]\s*\d", str(timezone_name or ""), re.I))
        raw_minutes = candidate.get("broker_offset_minutes")
        minutes = _valid_offset_minutes(raw_minutes, value_is_hours=False) if raw_minutes not in (None, "") else None
        if minutes is not None and (available or explicit_label or minutes != 0):
            merged["persisted_broker_offset_minutes_20260622"] = minutes
            return merged
        match = re.search(r"UTC\s*([+-])\s*(\d{1,2})(?::(\d{2}))?", display, re.I)
        if match:
            parsed = (int(match.group(2)) * 60 + int(match.group(3) or 0)) * (1 if match.group(1) == "+" else -1)
            parsed = _valid_offset_minutes(parsed, value_is_hours=False)
            if parsed is not None:
                merged["persisted_broker_offset_minutes_20260622"] = parsed
                return merged
    return merged


def _authoritative_time_column(frame: pd.DataFrame) -> str | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    for name in _TIME_COLUMNS:
        if name in frame.columns:
            return name
    normalized = {str(c).strip().lower().replace("_", " "): c for c in frame.columns}
    for name in _TIME_COLUMNS:
        hit = normalized.get(str(name).strip().lower().replace("_", " "))
        if hit is not None:
            return str(hit)
    return None


def _frame_time_series(frame: Any) -> pd.Series:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.Series(dtype="datetime64[ns, UTC]")
    col = _authoritative_time_column(frame)
    if col is not None:
        parsed = pd.to_datetime(frame[col], errors="coerce", utc=True)
        return pd.Series(parsed, index=frame.index)
    if isinstance(frame.index, pd.DatetimeIndex):
        return pd.Series(pd.to_datetime(frame.index, errors="coerce", utc=True), index=frame.index)
    if not isinstance(frame.index, pd.RangeIndex):
        parsed = pd.to_datetime(frame.index, errors="coerce", utc=True)
        if isinstance(parsed, pd.DatetimeIndex) and parsed.notna().any():
            return pd.Series(parsed, index=frame.index)
    return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")


def _frame_latest_utc(frame: Any) -> pd.Timestamp | None:
    parsed = _frame_time_series(frame).dropna()
    return pd.Timestamp(parsed.max()).tz_convert("UTC") if not parsed.empty else None


def _valid_offset_minutes(value: Any, *, value_is_hours: bool) -> int | None:
    try:
        number = float(value)
    except Exception:
        return None
    minutes = int(round(number * 60.0)) if value_is_hours else int(round(number))
    return minutes if -12 * 60 <= minutes <= 14 * 60 else None


def _first_present(state: Mapping[str, Any], keys: Sequence[str]) -> tuple[str | None, Any]:
    for key in keys:
        if key in state and state.get(key) not in (None, ""):
            return key, state.get(key)
    return None, None


def _offset_label_minutes(minutes: int | None) -> str:
    if minutes is None:
        return "UNAVAILABLE"
    sign = "+" if minutes >= 0 else "-"
    hours, remainder = divmod(abs(int(minutes)), 60)
    return f"{sign}{hours}" if remainder == 0 else f"{sign}{hours}:{remainder:02d}"


def _fixed_timezone(minutes: int):
    return timezone(timedelta(minutes=int(minutes)))


def _utc_now_iso() -> str:
    """Observation metadata only; never used as a candle identity fallback."""
    return pd.Timestamp.now(tz="UTC").isoformat()


def _validated_bridge_offset(state: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a bridge server timestamp against its UTC receipt observation."""
    time_key, server_raw = _first_present(state, _BRIDGE_TIME_KEYS)
    receipt_key, receipt_raw = _first_present(state, _BRIDGE_RECEIPT_KEYS)
    if time_key is None or receipt_key is None:
        return {"available": False, "error": None}
    receipt = _as_utc(receipt_raw)
    if receipt is None:
        return {"available": False, "error": "Bridge receipt UTC is invalid."}
    try:
        raw = pd.Timestamp(server_raw)
    except Exception:
        return {"available": False, "error": "Bridge broker-server timestamp is invalid."}
    now = pd.Timestamp.now(tz="UTC")
    if abs((now - receipt).total_seconds()) > 86400:
        return {"available": False, "error": "Bridge broker-clock observation is stale."}
    if raw.tzinfo is not None:
        offset = raw.utcoffset()
        minutes = int(round(offset.total_seconds() / 60.0)) if offset is not None else None
        server_utc = raw.tz_convert("UTC")
        # Server clock and receipt should describe the same observation within a safe network window.
        if abs((server_utc - receipt).total_seconds()) > 900:
            return {"available": False, "error": "Bridge broker timestamp differs from UTC receipt by more than 15 minutes."}
    else:
        # Naive server timestamps are interpreted only for offset discovery. Round to
        # 15 minutes to tolerate network delay while rejecting impossible offsets.
        naive_utc_wall = receipt.tz_localize(None)
        minutes = int(round((raw - naive_utc_wall).total_seconds() / 900.0) * 15)
    minutes = _valid_offset_minutes(minutes, value_is_hours=False)
    if minutes is None:
        return {"available": False, "error": "Bridge supplied an impossible broker UTC offset."}
    return {"available": True, "minutes": minutes, "source_key": time_key, "receipt_key": receipt_key, "observed_at_utc": receipt.isoformat()}


def resolve_broker_clock(
    state: Mapping[str, Any],
    *,
    event_time_utc: Any | None = None,
    consolidate_aliases: bool = True,
) -> dict[str, Any]:
    """Resolve validated bridge > manual offset > IANA timezone > persisted offset.

    The returned ``available`` flag must be checked by every display caller.
    No zero-offset fallback is provided and impossible bridge offsets are rejected.
    """
    event = _as_utc(event_time_utc)
    if event is None:
        return {
            "available": False, "status": BROKER_TIME_UNAVAILABLE, "display": BROKER_TIME_UNAVAILABLE,
            "broker_offset_minutes": None, "broker_offset_hours": None,
            "broker_offset_label": "UNAVAILABLE", "broker_timezone_iana": None,
            "broker_tzinfo": None, "resolution_precedence": "unavailable",
            "resolution_error": "No canonical completed candle timestamp was supplied.",
            "observation_time_utc": None,
        }
    minutes: int | None = None
    timezone_name: str | None = None
    precedence = "unavailable"
    error: str | None = None
    observation_time: str | None = None

    bridge = _validated_bridge_offset(state)
    if bridge.get("available"):
        minutes = int(bridge["minutes"]); precedence = "validated_doo_bridge"; observation_time = bridge.get("observed_at_utc")
    elif bridge.get("error"):
        error = str(bridge.get("error"))

    if minutes is None:
        key, raw = _first_present(state, _MANUAL_OFFSET_KEYS)
        if key is not None:
            minutes = _valid_offset_minutes(raw, value_is_hours=not key.endswith("minutes_20260622"))
            if minutes is not None: precedence = "manual_offset"
            else: error = f"Invalid manual broker offset in {key}."

    if minutes is None:
        tz_key, tz_raw = _first_present(state, _IANA_KEYS)
        if tz_key is not None:
            timezone_name = str(tz_raw).strip()
            try:
                zone = ZoneInfo(timezone_name)
                offset = event.astimezone(zone).utcoffset()
                minutes = int(offset.total_seconds() // 60) if offset is not None else None
                if minutes is not None: precedence = "iana_timezone"
                else: error = f"Timezone {timezone_name} returned no UTC offset."
            except (ZoneInfoNotFoundError, ValueError) as exc:
                error = f"Invalid broker timezone {timezone_name}: {exc}"; timezone_name = None

    if minutes is None:
        persisted_key, persisted_raw = _first_present(state, _PERSISTED_OFFSET_KEYS)
        if persisted_key is not None:
            minutes = _valid_offset_minutes(persisted_raw, value_is_hours="hours" in persisted_key)
            if minutes is not None: precedence = "persisted_offset"
            elif error is None: error = f"Invalid persisted broker offset in {persisted_key}."

    available = minutes is not None
    tzinfo = None
    if available:
        tzinfo = ZoneInfo(timezone_name) if precedence == "iana_timezone" and timezone_name else _fixed_timezone(int(minutes))
        if consolidate_aliases and isinstance(state, MutableMapping):
            state["persisted_broker_offset_minutes_20260622"] = int(minutes)
            state["last_valid_broker_offset_minutes_20260622"] = int(minutes)
            state["broker_clock_resolution_source_20260622"] = precedence
            state["broker_clock_observation_time_utc_20260622"] = observation_time or _utc_now_iso()
            # Backward aliases remain synchronized, but never outrank IANA or validated bridge evidence.
            hours = float(minutes) / 60.0
            state["broker_utc_offset_hours"] = hours
            if precedence == "iana_timezone" and timezone_name: state["broker_timezone_iana_20260622"] = timezone_name
    return {
        "available": available, "broker_offset_minutes": int(minutes) if minutes is not None else None,
        "broker_offset_hours": float(minutes) / 60.0 if minutes is not None else None,
        "broker_offset_label": _offset_label_minutes(minutes), "broker_timezone_iana": timezone_name,
        "broker_tzinfo": tzinfo, "resolution_precedence": precedence, "resolution_error": error,
        "observation_time_utc": observation_time,
    }


def _canonical_completed_utc(canonical: Mapping[str, Any]) -> pd.Timestamp | None:
    market = canonical.get("market") if isinstance(canonical.get("market"), Mapping) else {}
    for value in (
        canonical.get("event_time_utc"), canonical.get("latest_completed_h1_utc"),
        canonical.get("latest_completed_candle_time"), canonical.get("latest_completed_h1"),
        canonical.get("anchor_time"), market.get("latest_completed_candle_time"),
        market.get("latest_completed_h1"),
    ):
        parsed = _as_utc(value)
        if parsed is not None:
            return parsed
    return None


def _generation(canonical: Mapping[str, Any], state: Mapping[str, Any]) -> Any:
    return canonical.get("calculation_generation", state.get("canonical_calculation_generation_20260617", state.get("calculation_generation")))


def _calculation_id(canonical: Mapping[str, Any], state: Mapping[str, Any]) -> Any:
    return (
        canonical.get("calculation_id") or canonical.get("canonical_calculation_id")
        or canonical.get("run_id") or state.get("canonical_calculation_id_20260617")
        or state.get("active_calculation_id_20260619")
    )


def shared_broker_time_provider(
    state: Mapping[str, Any],
    *,
    frame: Any | None = None,
    canonical: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the complete canonical market-time contract."""
    canonical = canonical if isinstance(canonical, Mapping) else _canonical_from_state(state)
    canonical_utc = _canonical_completed_utc(canonical)
    # A restored session can contain an old canonical generation while MT5/API
    # data has already advanced.  Select the freshest authoritative candle
    # timestamp across the canonical object and loaded market frames.  This is
    # a clock/watermark repair only; it never recalculates trading scores.
    frame_candidates = []
    if isinstance(frame, pd.DataFrame):
        frame_candidates.append(("explicit_frame", frame))
    for key in (
        "canonical_completed_ohlc_df_20260617", "last_df", "dv_pp_df", "custom_h1_df",
        "home_df", "prepared_lunch_df", "lunch_visual_df", "live_df", "shared_df",
        "market_df", "eurusd_h1_df", "lunch_df", "full_metric_history_df_20260618",
    ):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            frame_candidates.append((key, value))
    loaded = [(name, _frame_latest_utc(value)) for name, value in frame_candidates]
    loaded = [(name, stamp) for name, stamp in loaded if stamp is not None]
    newest_loaded = max(loaded, key=lambda item: item[1]) if loaded else (None, None)
    completed_utc = canonical_utc
    timestamp_source = "canonical_completed_h1" if canonical_utc is not None else "unavailable"
    if newest_loaded[1] is not None and (completed_utc is None or newest_loaded[1] > completed_utc):
        completed_utc = newest_loaded[1]
        timestamp_source = f"freshest_loaded_candle:{newest_loaded[0]}"

    resolution_state = _state_with_saved_broker_clock(state, canonical)
    clock = resolve_broker_clock(resolution_state, event_time_utc=completed_utc)
    if clock.get("available") and isinstance(state, MutableMapping):
        minutes = clock.get("broker_offset_minutes")
        if minutes is not None:
            state.setdefault("persisted_broker_offset_minutes_20260622", int(minutes))
            state.setdefault("last_valid_broker_offset_minutes_20260622", int(minutes))
    tzinfo = clock.get("broker_tzinfo")
    broker_time = completed_utc.tz_convert(tzinfo) if completed_utc is not None and tzinfo is not None else None
    myanmar_time = completed_utc.tz_convert(_fixed_timezone(390)) if completed_utc is not None else None
    label = clock.get("broker_offset_label")
    market = canonical.get("market") if isinstance(canonical.get("market"), Mapping) else {}
    quality = canonical.get("data_quality") if isinstance(canonical.get("data_quality"), Mapping) else {}
    processing = pd.Timestamp.now(tz="UTC")
    lag = max(0.0, (processing - completed_utc).total_seconds() / 60.0) if completed_utc is not None else None
    broker_display = (
        broker_time.strftime("%Y-%m-%d %H:%M:%S") + f" (Broker UTC{label})"
        if broker_time is not None else BROKER_TIME_UNAVAILABLE
    )
    source = canonical.get("source") or market.get("source") or timestamp_source
    watermark_status = "AVAILABLE" if completed_utc is not None else "UNAVAILABLE"
    if completed_utc is not None and lag is not None and lag > 180:
        watermark_status = "STALE"
    return {
        "event_time_utc": completed_utc.isoformat() if completed_utc is not None else None,
        "latest_completed_h1_utc": completed_utc.isoformat() if completed_utc is not None else None,
        "latest_broker_candle_utc": completed_utc,
        "latest_broker_candle_utc_iso": completed_utc.isoformat() if completed_utc is not None else None,
        "shared_broker_time": broker_time,
        "shared_broker_time_iso": broker_time.isoformat() if broker_time is not None else None,
        "shared_broker_time_display": broker_display,
        "latest_broker_candle_timestamp": broker_time,
        "broker_time": broker_time,
        "broker_time_display": broker_display,
        "broker_hour": broker_time.strftime("%H:00") if broker_time is not None else BROKER_TIME_UNAVAILABLE,
        "broker_date": broker_time.strftime("%Y-%m-%d") if broker_time is not None else BROKER_TIME_UNAVAILABLE,
        "broker_weekday": broker_time.strftime("%A") if broker_time is not None else BROKER_TIME_UNAVAILABLE,
        "myanmar_time": myanmar_time,
        "myanmar_time_display": myanmar_time.strftime("%Y-%m-%d %H:%M:%S (Myanmar UTC+6:30)") if myanmar_time is not None else "UNAVAILABLE",
        "broker_offset_minutes": clock.get("broker_offset_minutes"),
        "broker_offset_hours": clock.get("broker_offset_hours"),
        "broker_offset_label": label,
        "broker_timezone_iana": clock.get("broker_timezone_iana"),
        "broker_clock_available": bool(clock.get("available")),
        "broker_clock_resolution": clock.get("resolution_precedence"),
        "broker_clock_error": clock.get("resolution_error"),
        "broker_clock_observation_time_utc": clock.get("observation_time_utc"),
        "contract_version": CONTRACT_VERSION,
        "calculation_id": _calculation_id(canonical, state),
        "calculation_generation": _generation(canonical, state),
        "source": source,
        "symbol": canonical.get("symbol") or state.get("symbol") or "EURUSD",
        "timeframe": canonical.get("timeframe") or state.get("timeframe") or "H1",
        "ingested_at_utc": canonical.get("ingested_at_utc") or canonical.get("created_at"),
        "processing_time_utc": processing.isoformat(),
        "watermark_status": watermark_status,
        "freshness_lag_minutes": round(lag, 2) if lag is not None else None,
        "timestamp_source": timestamp_source,
        "contract_version": CONTRACT_VERSION,
        "is_completed_candle": completed_utc is not None,
        "data_quality_status": quality.get("quality_status") or quality.get("status") or canonical.get("data_quality_status") or "UNAVAILABLE",
    }


def frame_to_shared_broker_clock(
    frame: pd.DataFrame,
    state: Mapping[str, Any],
    *,
    canonical: Mapping[str, Any] | None = None,
    include_myanmar: bool = True,
    reject_future_incomplete: bool = True,
    hide_raw_utc: bool = True,
) -> pd.DataFrame:
    """Create a newest-first display projection from canonical UTC event times."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    work = frame.copy(deep=False)
    time_col = _authoritative_time_column(work)
    if time_col is None and isinstance(work.index, pd.DatetimeIndex):
        index_name = work.index.name or "event_time_utc"
        work = work.reset_index().rename(columns={index_name: "event_time_utc", "index": "event_time_utc"})
        time_col = "event_time_utc"
    if time_col is None:
        return work
    parsed = pd.to_datetime(work[time_col], errors="coerce", utc=True)
    work = work.loc[parsed.notna()].copy()
    parsed = parsed.loc[work.index]
    if work.empty:
        return work.reset_index(drop=True)

    # The frame itself is authoritative evidence. Passing it into the provider
    # prevents an old restored canonical object from filtering out newer completed
    # rows that are already present in the table being rendered.
    contract = shared_broker_time_provider(state, frame=work, canonical=canonical)
    watermark = _as_utc(contract.get("latest_completed_h1_utc"))
    if reject_future_incomplete and watermark is not None:
        keep = parsed.le(watermark)
        work = work.loc[keep].copy()
        parsed = parsed.loc[keep]
    if work.empty:
        return work.reset_index(drop=True)

    work["__event_time_utc"] = parsed
    # Preserve caller order; history query layers own newest-first ordering.
    parsed = work["__event_time_utc"]
    position = list(work.columns).index(time_col) if time_col in work.columns else 0
    if hide_raw_utc and time_col in work.columns:
        work = work.drop(columns=[time_col])

    if not contract.get("broker_clock_available"):
        broker_col = "Broker Time"
        work.insert(min(position, len(work.columns)), broker_col, BROKER_TIME_UNAVAILABLE)
        if include_myanmar:
            myanmar = parsed.dt.tz_convert(_fixed_timezone(390)).dt.strftime("%Y-%m-%d %H:%M:%S")
            work.insert(min(position + 1, len(work.columns)), "Myanmar Time (UTC+6:30)", myanmar)
        # Never corrupt usable history dates with a configuration warning. When
        # broker offset evidence is temporarily unavailable after navigation,
        # preserve canonical candle identity and rebuild visible calendar fields
        # from the authoritative UTC event timestamp. The Broker Time column stays
        # explicit about the missing offset; no broker time is guessed.
        canonical_utc = parsed.dt.tz_convert("UTC")
        work["Date"] = canonical_utc.dt.strftime("%Y-%m-%d")
        work["Weekday"] = canonical_utc.dt.strftime("%A")
        work["Hour"] = canonical_utc.dt.strftime("%H:00")
        # Repeated display projections must not leave a second stale time alias.
        for column in list(work.columns):
            normalized = str(column).strip().lower().replace("_", " ")
            if normalized in _DISPLAY_CLOCK_ALIASES and column != broker_col:
                work[column] = canonical_utc.dt.tz_localize(None)
    else:
        resolution_state = _state_with_saved_broker_clock(state, canonical if isinstance(canonical, Mapping) else _canonical_from_state(state))
        tzinfo = resolve_broker_clock(resolution_state, event_time_utc=watermark).get("broker_tzinfo")
        broker = parsed.dt.tz_convert(tzinfo)
        label = str(contract.get("broker_offset_label"))
        broker_col = f"Broker Time (UTC{label})"
        work.insert(min(position, len(work.columns)), broker_col, broker.dt.tz_localize(None))
        if include_myanmar:
            myanmar = parsed.dt.tz_convert(_fixed_timezone(390)).dt.tz_localize(None)
            work.insert(min(position + 1, len(work.columns)), "Myanmar Time (UTC+6:30)", myanmar)
        # Always rebuild these visible fields from broker time, even when they
        # already existed with stale UTC-derived values.
        work["Date"] = broker.dt.strftime("%Y-%m-%d")
        work["Weekday"] = broker.dt.strftime("%A")
        work["Hour"] = broker.dt.strftime("%H:00")
        # Every visible candle-time alias is rebuilt from the same broker-aware
        # timestamp. This prevents Date/Hour/Completed Candle disagreements.
        for column in list(work.columns):
            normalized = str(column).strip().lower().replace("_", " ")
            if normalized in _DISPLAY_CLOCK_ALIASES and column != broker_col:
                work[column] = broker.dt.tz_localize(None)
    work = work.drop(columns=["__event_time_utc"], errors="ignore")
    return work.reset_index(drop=True)


def latest_history_utc(frame: Any) -> pd.Timestamp | None:
    return _frame_latest_utc(frame)


def _single_column_identity(frame: Any, names: Sequence[str]) -> set[str]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return set()
    normalized = {str(c).strip().lower(): c for c in frame.columns}
    for name in names:
        col = normalized.get(name.lower())
        if col is not None:
            return {str(v) for v in frame[col].dropna().astype(str).unique()}
    return set()


def history_sync_status(
    state: Mapping[str, Any],
    *,
    history_frame: Any | None = None,
    canonical: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate timestamp, calculation, generation, offset, source and contract."""
    clock = shared_broker_time_provider(state, frame=history_frame, canonical=canonical)
    expected = _as_utc(clock.get("latest_completed_h1_utc"))
    actual = latest_history_utc(history_frame)
    difference = abs((actual - expected).total_seconds()) / 60.0 if actual is not None and expected is not None else None
    expected_calc = str(clock.get("calculation_id"))
    expected_gen = str(clock.get("calculation_generation"))
    expected_offset = str(clock.get("broker_offset_minutes"))
    expected_source = str(clock.get("source"))
    calc_values = _single_column_identity(history_frame, ("calculation_id", "canonical_calculation_id", "run_id"))
    gen_values = _single_column_identity(history_frame, ("generation", "calculation_generation"))
    offset_values = _single_column_identity(history_frame, ("broker_offset_minutes",))
    source_values = _single_column_identity(history_frame, ("source",))
    contract_values = _single_column_identity(history_frame, ("contract_version", "timestamp_contract_version"))
    calc_match = not calc_values or calc_values == {expected_calc}
    gen_match = not gen_values or gen_values == {expected_gen}
    offset_match = not offset_values or offset_values == {expected_offset}
    source_match = not source_values or source_values == {expected_source}
    contract_match = not contract_values or contract_values == {CONTRACT_VERSION}
    timestamp_match = difference is not None and difference < 1.0
    if expected is None:
        status, reason = "UNAVAILABLE", "No canonical completed-H1 watermark is published."
    elif not clock.get("broker_clock_available"):
        status, reason = "UNAVAILABLE", BROKER_TIME_UNAVAILABLE
    elif actual is None:
        status, reason = "STALE", "No authoritative history timestamp is available."
    elif timestamp_match and calc_match and gen_match and offset_match and source_match and contract_match:
        status, reason = "SYNCED", "Timestamp, calculation ID, generation, broker clock, source and contract match."
    elif difference is not None and difference > 0 and calc_match and gen_match and offset_match and source_match:
        status, reason = "STALE", "History watermark differs from the active completed-H1 watermark."
    else:
        status, reason = "OUT OF SYNC", "One or more generation/identity/broker-contract checks failed."
    resolution_state = _state_with_saved_broker_clock(state, canonical if isinstance(canonical, Mapping) else _canonical_from_state(state))
    tzinfo = resolve_broker_clock(resolution_state, event_time_utc=actual).get("broker_tzinfo")
    actual_broker = actual.tz_convert(tzinfo) if actual is not None and tzinfo is not None else None
    return {
        **clock,
        "status": status,
        "status_code": status.replace(" ", "_"),
        "synced": status == "SYNCED",
        "latest_history_record_utc": actual,
        "latest_history_record_utc_iso": actual.isoformat() if actual is not None else None,
        "latest_history_record": actual_broker,
        "latest_history_record_display": (
            actual_broker.strftime("%Y-%m-%d %H:%M:%S") + f" (Broker UTC{clock.get('broker_offset_label')})"
            if actual_broker is not None else (BROKER_TIME_UNAVAILABLE if actual is not None else "Not available")
        ),
        "difference_minutes": round(difference, 2) if difference is not None else None,
        "difference_in_minutes": round(difference, 2) if difference is not None else None,
        "canonical_latest_completed_h1_utc": clock.get("latest_completed_h1_utc"),
        "displayed_broker_candle_time": clock.get("broker_time_display"),
        "displayed_myanmar_candle_time": clock.get("myanmar_time_display"),
        "latest_field1_history_utc": actual.isoformat() if actual is not None else None,
        "latest_field6_history_utc": None,
        "calculation_id_match": calc_match,
        "generation_match": gen_match,
        "broker_offset_match": offset_match,
        "source_match": source_match,
        "contract_version_match": contract_match,
        "timestamp_match": timestamp_match,
        "reason": reason,
    }


__all__ = [
    "CONTRACT_VERSION", "BROKER_TIME_UNAVAILABLE", "resolve_broker_clock",
    "shared_broker_time_provider", "frame_to_shared_broker_clock",
    "history_sync_status", "latest_history_utc",
]
