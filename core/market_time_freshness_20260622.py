"""Low-cost market/feed time and dataframe freshness diagnostics.

All source timestamps are normalized to UTC first.  Broker-chart and Myanmar
clocks are display projections only; the underlying OHLC data and protected
calculation timestamps are never rewritten.
"""
from __future__ import annotations

import time
from typing import Any, Mapping, MutableMapping

import pandas as pd

_TIME_COLUMNS = ("time", "Time", "Datetime", "DateTime", "Timestamp", "timestamp", "date", "Date")
_INTERVAL_SECONDS = {
    "M1": 60, "M2": 120, "M3": 180, "M4": 240, "M5": 300,
    "M10": 600, "M15": 900, "M30": 1800, "H1": 3600,
    "H4": 14400, "D1": 86400, "CUSTOM": 3600,
}
MYANMAR_UTC_OFFSET_HOURS = 6.5


def _as_utc(value: Any) -> pd.Timestamp | None:
    try:
        parsed = pd.to_datetime(value, errors="coerce", utc=True)
        if isinstance(parsed, pd.DatetimeIndex):
            parsed = parsed.max()
        if pd.isna(parsed):
            return None
        return pd.Timestamp(parsed)
    except Exception:
        return None


def _time_values(frame: Any) -> pd.Series | pd.DatetimeIndex | None:
    """Return timestamp values from a normal column or DatetimeIndex.

    Several connector/canonical paths keep candle time in the index.  Ignoring
    that index made Field 1 appear stale while other Lunch fields were current.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    try:
        from core.lunch_h1_data_quality_v13 import combined_h1_time
        combined = combined_h1_time(frame)
        if combined.notna().any():
            return combined
    except Exception:
        pass
    column = next((name for name in _TIME_COLUMNS if name in frame.columns), None)
    if column is None:
        normalized = {str(c).strip().lower(): c for c in frame.columns}
        column = next((normalized.get(name.lower()) for name in _TIME_COLUMNS if normalized.get(name.lower()) is not None), None)
    if column is not None:
        return frame[column]
    if isinstance(frame.index, pd.DatetimeIndex):
        return frame.index
    # Object indexes can still contain valid ISO timestamps.  Avoid treating a
    # plain RangeIndex as time.
    if not isinstance(frame.index, pd.RangeIndex):
        parsed = pd.to_datetime(frame.index, errors="coerce", utc=True)
        if isinstance(parsed, pd.DatetimeIndex) and parsed.notna().any():
            return parsed
    return None


def frame_time_series(frame: Any) -> pd.Series:
    """Return a UTC timestamp Series aligned to ``frame.index``."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.Series(dtype="datetime64[ns, UTC]")
    values = _time_values(frame)
    if values is None:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    if isinstance(parsed, pd.DatetimeIndex):
        return pd.Series(parsed, index=frame.index)
    parsed.index = frame.index
    return parsed


def latest_frame_time(frame: Any) -> pd.Timestamp | None:
    """Return the latest valid dataframe timestamp normalized to UTC."""
    parsed = frame_time_series(frame)
    valid = parsed.dropna()
    return pd.Timestamp(valid.max()) if not valid.empty else None


def broker_offset_hours(state: Mapping[str, Any]) -> float:
    """Return the user-configured MT5 chart offset without changing market data."""
    for key in (
        "mt5_broker_utc_offset_hours_20260622",
        "broker_utc_offset_hours",
        "mt5_server_utc_offset_hours",
    ):
        try:
            value = float(state.get(key))
            if -12.0 <= value <= 14.0:
                return value
        except Exception:
            continue
    return 0.0


def to_display_clock(value: Any, *, offset_hours: float) -> pd.Timestamp | None:
    stamp = _as_utc(value)
    if stamp is None:
        return None
    return stamp + pd.Timedelta(hours=float(offset_hours))


def _offset_text(offset: float) -> str:
    sign = "+" if offset >= 0 else "-"
    total_minutes = int(round(abs(float(offset)) * 60.0))
    hours, minutes = divmod(total_minutes, 60)
    return f"{sign}{hours}" if minutes == 0 else f"{sign}{hours}:{minutes:02d}"


def _clock_text(value: pd.Timestamp | None, offset: float, label: str) -> str:
    if value is None:
        return "Not available"
    return value.strftime("%Y-%m-%d %H:%M:%S") + f" ({label} UTC{_offset_text(offset)})"


def _floor_interval(now: pd.Timestamp, seconds: int) -> pd.Timestamp:
    epoch = int(now.timestamp())
    return pd.Timestamp((epoch // seconds) * seconds, unit="s", tz="UTC")


def _query_mt5_tick_time(state: MutableMapping[str, Any], *, ttl_seconds: int = 15) -> pd.Timestamp | None:
    """Read one MT5 tick timestamp with a tiny TTL; failures are non-fatal."""
    source = str(state.get("source") or "").upper()
    mode = str(state.get("connector_mode") or "").lower()
    if "MT5" not in source and mode != "mt5":
        return _as_utc(state.get("mt5_latest_tick_time_utc_20260622"))
    now = time.time()
    cached_at = float(state.get("mt5_tick_probe_at_20260622", 0.0) or 0.0)
    cached = _as_utc(state.get("mt5_latest_tick_time_utc_20260622"))
    if cached is not None and now - cached_at < max(5, int(ttl_seconds)):
        return cached
    state["mt5_tick_probe_at_20260622"] = now
    try:
        import MetaTrader5 as mt5  # type: ignore
        initialized_here = False
        try:
            terminal = mt5.terminal_info()
        except Exception:
            terminal = None
        if terminal is None:
            initialized_here = bool(mt5.initialize())
        symbol = str(state.get("symbol") or "EURUSD")
        tick = mt5.symbol_info_tick(symbol)
        raw = getattr(tick, "time_msc", 0) or getattr(tick, "time", 0)
        if raw:
            seconds = float(raw) / 1000.0 if float(raw) > 10_000_000_000 else float(raw)
            value = pd.Timestamp(seconds, unit="s", tz="UTC")
            state["mt5_latest_tick_time_utc_20260622"] = value.isoformat()
            state["mt5_tick_probe_error_20260622"] = ""
            if initialized_here:
                try:
                    mt5.shutdown()
                except Exception:
                    pass
            return value
        state["mt5_tick_probe_error_20260622"] = "No MT5 tick is available for the selected symbol."
        if initialized_here:
            try:
                mt5.shutdown()
            except Exception:
                pass
    except Exception as exc:
        state["mt5_tick_probe_error_20260622"] = f"{type(exc).__name__}: {exc}"[:240]
    return cached


def market_time_snapshot(
    state: MutableMapping[str, Any] | Mapping[str, Any],
    *,
    frame: Any | None = None,
    query_mt5: bool = False,
) -> dict[str, Any]:
    """Return truthful, low-cost UTC, broker and Myanmar freshness values."""
    mutable = state if isinstance(state, MutableMapping) else dict(state)
    now = pd.Timestamp.now(tz="UTC")
    timeframe = str(state.get("timeframe") or "H1").upper()
    seconds = int(_INTERVAL_SECONDS.get(timeframe, 3600))
    active_frame = frame if isinstance(frame, pd.DataFrame) else state.get("last_df")
    latest = latest_frame_time(active_frame)
    current_bar_open = _floor_interval(now, seconds)
    expected_completed_open = current_bar_open - pd.Timedelta(seconds=seconds)
    lag_seconds = None
    lag_bars = None
    if latest is not None:
        lag_seconds = max(0.0, float((current_bar_open - latest).total_seconds()))
        lag_bars = max(0.0, lag_seconds / seconds)
    if latest is None:
        status = "NO DATA"
    elif latest >= expected_completed_open:
        status = "CURRENT"
    elif lag_bars is not None and lag_bars <= 2.0:
        status = "WATCH"
    else:
        status = "LATE"

    last_fetch = state.get("last_fetch")
    try:
        fetch_age_seconds = max(0.0, time.time() - float(last_fetch)) if last_fetch else None
    except Exception:
        fetch_age_seconds = None

    tick = _query_mt5_tick_time(mutable) if query_mt5 else _as_utc(state.get("mt5_latest_tick_time_utc_20260622"))
    # Strict display resolution: never label UTC as Broker Time when Settings
    # does not contain a valid manual offset, IANA timezone, or persisted offset.
    try:
        from core.shared_broker_time_20260622 import BROKER_TIME_UNAVAILABLE, resolve_broker_clock
        resolved_clock = resolve_broker_clock(state, event_time_utc=latest or tick or now)
    except Exception:
        resolved_clock = {"available": False, "broker_offset_hours": None}
        BROKER_TIME_UNAVAILABLE = "BROKER TIME UNAVAILABLE — CONFIGURE SETTINGS"
    broker_available = bool(resolved_clock.get("available"))
    broker_offset = float(resolved_clock.get("broker_offset_hours")) if broker_available else 0.0
    broker_clock = to_display_clock(tick or now, offset_hours=broker_offset) if broker_available else None
    myanmar_clock = to_display_clock(now, offset_hours=MYANMAR_UTC_OFFSET_HOURS)
    latest_broker = to_display_clock(latest, offset_hours=broker_offset) if broker_available else None
    latest_myanmar = to_display_clock(latest, offset_hours=MYANMAR_UTC_OFFSET_HOURS)

    return {
        "status": status,
        "timeframe": timeframe,
        "current_utc": now.isoformat(),
        "current_utc_display": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "current_myanmar_time": myanmar_clock.isoformat() if myanmar_clock is not None else None,
        "current_myanmar_display": _clock_text(myanmar_clock, MYANMAR_UTC_OFFSET_HOURS, "Myanmar"),
        "latest_loaded_time": latest.isoformat() if latest is not None else None,
        "latest_loaded_display": latest.strftime("%Y-%m-%d %H:%M:%S UTC") if latest is not None else "No loaded candle",
        "latest_loaded_broker_time": latest_broker.isoformat() if latest_broker is not None else None,
        "latest_loaded_broker_display": _clock_text(latest_broker, broker_offset, "Broker") if broker_available else BROKER_TIME_UNAVAILABLE,
        "latest_loaded_myanmar_time": latest_myanmar.isoformat() if latest_myanmar is not None else None,
        "latest_loaded_myanmar_display": _clock_text(latest_myanmar, MYANMAR_UTC_OFFSET_HOURS, "Myanmar"),
        "expected_completed_open": expected_completed_open.isoformat(),
        "expected_completed_display": expected_completed_open.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "lag_seconds": lag_seconds,
        "lag_minutes": round(lag_seconds / 60.0, 1) if lag_seconds is not None else None,
        "lag_bars": round(lag_bars, 2) if lag_bars is not None else None,
        "last_fetch_age_seconds": fetch_age_seconds,
        "mt5_tick_time_utc": tick.isoformat() if tick is not None else None,
        "mt5_tick_display": tick.strftime("%Y-%m-%d %H:%M:%S UTC") if tick is not None else "Not available",
        "broker_offset_hours": resolved_clock.get("broker_offset_hours"),
        "broker_clock_available": broker_available,
        "broker_clock_display": _clock_text(broker_clock, broker_offset, "Broker") if broker_available else BROKER_TIME_UNAVAILABLE,
        "source": str(state.get("source") or "DISCONNECTED"),
        "rows": int(len(active_frame)) if isinstance(active_frame, pd.DataFrame) else 0,
    }


__all__ = [
    "MYANMAR_UTC_OFFSET_HOURS", "broker_offset_hours", "frame_time_series",
    "latest_frame_time", "market_time_snapshot", "to_display_clock",
]
