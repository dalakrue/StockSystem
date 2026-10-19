"""Small display-only timestamp normalizers used at legacy UI boundaries.

The production publishers intentionally retain their original schemas.  These
helpers only create comparable UTC sort keys for read-only tables, preventing
mixed Python ``str``/``Timestamp`` comparisons without rewriting source data.
"""
from __future__ import annotations

from typing import Any, Iterable
import pandas as pd

_TIME_ALIASES = (
    "Broker Time", "Broker Candle", "Broker Candle Time", "Completed Broker Candle",
    "event_time_utc", "Time", "Datetime", "DateTime", "Timestamp", "Date Time", "Date",
)


def comparable_utc(value: Any) -> pd.Timestamp | None:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed)


def find_time_column(frame: pd.DataFrame, aliases: Iterable[str] = _TIME_ALIASES) -> str | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    direct = {str(column): str(column) for column in frame.columns}
    for alias in aliases:
        if alias in direct:
            return direct[alias]
    normalized = {str(column).strip().lower().replace("_", " "): str(column) for column in frame.columns}
    for alias in aliases:
        key = str(alias).strip().lower().replace("_", " ")
        if key in normalized:
            return normalized[key]
    for column in frame.columns:
        name = str(column).strip().lower().replace("_", " ")
        if any(token in name for token in ("timestamp", "datetime", "broker time", "candle time")):
            return str(column)
    return None


def safe_sort_by_time(
    frame: pd.DataFrame,
    *,
    column: str | None = None,
    ascending: bool = False,
    drop_invalid: bool = False,
    floor: str | None = None,
) -> pd.DataFrame:
    """Sort a display frame using one UTC key while preserving the original column.

    Invalid timestamps stay at the bottom unless ``drop_invalid`` is requested.
    The function never converts unrelated numeric columns to strings.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame() if not isinstance(frame, pd.DataFrame) else frame.copy(deep=False)
    time_column = column if column in frame.columns else find_time_column(frame)
    if time_column is None:
        return frame.copy(deep=False).reset_index(drop=True)
    work = frame.copy(deep=False)
    parsed = pd.to_datetime(work[time_column], errors="coerce", utc=True, format="mixed")
    if floor:
        parsed = parsed.dt.floor(floor)
    work = work.assign(__safe_utc_sort_20260628=parsed)
    if drop_invalid:
        work = work.loc[work["__safe_utc_sort_20260628"].notna()]
    work = work.sort_values(
        "__safe_utc_sort_20260628", ascending=ascending, kind="mergesort", na_position="last"
    )
    return work.drop(columns="__safe_utc_sort_20260628").reset_index(drop=True)


__all__ = ["comparable_utc", "find_time_column", "safe_sort_by_time"]
