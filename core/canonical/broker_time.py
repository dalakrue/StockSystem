"""Shared broker-time utilities; displayed Lunch time always comes from snapshot."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from core.canonical.snapshot import CanonicalRunSnapshot


def broker_candle_time(snapshot: CanonicalRunSnapshot) -> datetime:
    return snapshot.broker_candle_time


def broker_time_iso(snapshot: CanonicalRunSnapshot) -> str:
    return snapshot.broker_candle_time.isoformat()


def assert_same_broker_time(*snapshots: Any) -> bool:
    values = {getattr(item, "broker_candle_time", None) for item in snapshots if item is not None}
    return len(values) <= 1
