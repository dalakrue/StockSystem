
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from core.publication_identity_20260625 import freeze_publication_identity

SESSION_WIDGET_KEY = 'shared_fx_session_widget'
SESSION_SELECTION_KEY = 'shared_fx_session_selected'
SESSION_EFFECTIVE_KEY = 'shared_fx_session_effective'
SESSION_AUTO_KEY = 'shared_fx_session_auto'
SESSION_MODE_KEY = 'shared_fx_session_mode'
LEGACY_SESSION_SELECTION_KEYS = ('shared_fx_session_selected', 'field2_session_selector_20260625', 'shared_fx_session_selector_20260625')
SESSION_OPTIONS = {
    'AUTO': 'Auto — Current completed broker candle',
    'SYDNEY': 'Sydney only',
    'TOKYO': 'Tokyo only',
    'TOKYO_SYDNEY_OVERLAP': 'Tokyo + Sydney overlap',
    'TOKYO_LONDON_OVERLAP': 'Tokyo + London overlap',
    'ASIA_SYDNEY': 'Asia + Sydney (legacy)',
    'LONDON': 'London only',
    'LONDON_NEW_YORK_OVERLAP': 'London + New York overlap',
    'NEW_YORK': 'New York only',
    'GLOBAL_FALLBACK': 'Global fallback',
}



def normalize_session_selection(value: Any) -> str:
    """Return a valid internal session code from either a code or UI label."""
    raw = str(value or 'AUTO').strip()
    upper = raw.upper()
    if upper in SESSION_OPTIONS:
        return upper
    reverse = {str(label).strip().upper(): code for code, label in SESSION_OPTIONS.items()}
    return reverse.get(upper, 'AUTO')

_SESSION_ZONES = {
    'Australia/Sydney': ZoneInfo('Australia/Sydney'),
    'Asia/Tokyo': ZoneInfo('Asia/Tokyo'),
    'Europe/London': ZoneInfo('Europe/London'),
    'America/New_York': ZoneInfo('America/New_York'),
}


@dataclass(frozen=True)
class SessionContract:
    session_mode: str
    selected_session: str
    detected_session: str
    broker_candle_time: str
    utc_candle_time: str
    london_open: bool
    new_york_open: bool
    sydney_open: bool
    tokyo_open: bool
    overlap_state: str
    source_run_id: str
    generation_id: str
    snapshot_hash: str
    reason_code: str
    session_evidence_count: int = 0
    session_model_status: str = 'UNAVAILABLE'
    session_clock_utc: str = ''
    session_clock_broker: str = ''

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ('broker_candle_time', 'utc_candle_time', 'session_clock_utc', 'session_clock_broker'):
            value = data.get(key)
            if hasattr(value, "isoformat"):
                data[key] = value.isoformat()
        return data


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, 'to_dict') and callable(value.to_dict):
        try:
            return dict(value.to_dict())
        except Exception:
            return {}
    if hasattr(value, '__dict__'):
        try:
            return dict(vars(value))
        except Exception:
            return {}
    return {}


def _canonical_time(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> pd.Timestamp:
    market = _mapping(canonical.get('market'))
    # Session detection must use an absolute UTC candle instant.  A broker-time
    # display string may be naive, so prefer the canonical completed-H1 UTC
    # timestamp and only fall back to broker time when it carries an offset.
    candidates = [
        canonical.get('latest_completed_candle_time'),
        market.get('latest_completed_candle_time'),
        canonical.get('candle_time'),
        canonical.get('broker_candle_time'),
    ]
    if isinstance(state, Mapping):
        for key in ('canonical_broker_candle_time_20260625', 'shared_broker_time'):
            candidates.append(state.get(key))
    for value in candidates:
        ts = pd.to_datetime(value, errors='coerce', utc=True)
        if not pd.isna(ts):
            return pd.Timestamp(ts).tz_convert('UTC')
    return pd.Timestamp.now(tz='UTC').floor('h')


def _is_open(ts_utc: datetime, zone_name: str, open_hour: int, close_hour: int) -> bool:
    local = ts_utc.astimezone(_SESSION_ZONES[zone_name])
    hour = local.hour + local.minute / 60.0
    if open_hour <= close_hour:
        return open_hour <= hour < close_hour
    return hour >= open_hour or hour < close_hour


def detect_session_from_utc(ts_utc: datetime) -> tuple[str, dict[str, bool], str]:
    london_open = _is_open(ts_utc, 'Europe/London', 8, 17)
    new_york_open = _is_open(ts_utc, 'America/New_York', 8, 17)
    sydney_open = _is_open(ts_utc, 'Australia/Sydney', 7, 16)
    tokyo_open = _is_open(ts_utc, 'Asia/Tokyo', 9, 18)
    if london_open and new_york_open:
        detected = 'LONDON_NEW_YORK_OVERLAP'
        overlap = 'LONDON_NEW_YORK_OVERLAP'
    elif tokyo_open and london_open:
        detected = 'TOKYO_LONDON_OVERLAP'
        overlap = 'TOKYO_LONDON_OVERLAP'
    elif tokyo_open and sydney_open:
        detected = 'TOKYO_SYDNEY_OVERLAP'
        overlap = 'TOKYO_SYDNEY_OVERLAP'
    elif london_open:
        detected = 'LONDON'
        overlap = 'NONE'
    elif new_york_open:
        detected = 'NEW_YORK'
        overlap = 'NONE'
    elif tokyo_open:
        detected = 'TOKYO'
        overlap = 'NONE'
    elif sydney_open:
        detected = 'SYDNEY'
        overlap = 'NONE'
    else:
        detected = 'GLOBAL_FALLBACK'
        overlap = 'NONE'
    return detected, {
        'london_open': london_open,
        'new_york_open': new_york_open,
        'sydney_open': sydney_open,
        'tokyo_open': tokyo_open,
    }, overlap


def resolve_session_contract(state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None, selected_session: str | None = None) -> SessionContract:
    canonical = _mapping(canonical)
    identity = freeze_publication_identity(state, canonical)
    candle = _canonical_time(state, canonical)
    # Session identity is a live wall-clock property, not a frozen forecast
    # candle property. Using the canonical candle here caused the Lunch metric
    # to remain permanently stuck on the session active when calculation ran.
    session_clock = pd.Timestamp.now(tz='UTC').floor('min')
    detected, flags, overlap = detect_session_from_utc(session_clock.to_pydatetime())
    stored_selection = ''
    if isinstance(state, Mapping):
        for key in LEGACY_SESSION_SELECTION_KEYS:
            candidate = state.get(key)
            if candidate not in (None, ''):
                stored_selection = candidate
                break
    selected = normalize_session_selection(selected_session or stored_selection or 'AUTO')
    mode = 'AUTO' if selected == 'AUTO' else 'MANUAL'
    effective = detected if selected == 'AUTO' else selected
    reason_code = 'AUTO_FROM_CURRENT_UTC_TIME' if selected == 'AUTO' else 'MANUAL_SESSION_SELECTION'
    broker_candle_raw = canonical.get('broker_candle_time') or canonical.get('latest_completed_candle_time') or candle
    broker_candle = pd.to_datetime(broker_candle_raw, errors='coerce')
    if pd.isna(broker_candle):
        broker_candle = candle
    if getattr(broker_candle, 'tzinfo', None) is not None:
        session_clock_broker = session_clock.tz_convert(broker_candle.tzinfo)
    else:
        session_clock_broker = session_clock
    return SessionContract(
        session_mode=mode,
        selected_session=effective,
        detected_session=detected,
        broker_candle_time=broker_candle,
        utc_candle_time=candle.to_pydatetime(),
        overlap_state=overlap,
        london_open=flags['london_open'],
        new_york_open=flags['new_york_open'],
        sydney_open=flags['sydney_open'],
        tokyo_open=flags['tokyo_open'],
        source_run_id=identity['run_id'],
        generation_id=identity['generation_id'],
        snapshot_hash=identity['snapshot_hash'],
        reason_code=reason_code,
        session_clock_utc=session_clock.isoformat(),
        session_clock_broker=session_clock_broker.isoformat(),
    )


__all__ = ['SESSION_OPTIONS', 'SESSION_WIDGET_KEY', 'SESSION_SELECTION_KEY', 'SESSION_EFFECTIVE_KEY', 'SESSION_AUTO_KEY', 'SESSION_MODE_KEY', 'LEGACY_SESSION_SELECTION_KEYS', 'SessionContract', 'normalize_session_selection', 'detect_session_from_utc', 'resolve_session_contract']
