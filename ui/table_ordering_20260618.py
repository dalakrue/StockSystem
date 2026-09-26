"""Deterministic chronological and opportunity-ranking table views.

These helpers never recalculate trading values.  They only normalize timestamps,
reject invalid/future operational rows, and create two independent views from the
same canonical rows:

* ``chronological_view``: latest completed H1 first.
* ``priority_view``: qualification/risk/EV ranking first.

The separation prevents the historic ``sort descending -> tail()`` defect from
showing old backtest candles as the current operational row.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

import pandas as pd

_TIME_CANDIDATES = (
    "Time", "time", "candle time", "Candidate Time", "DateTime", "datetime",
    "timestamp", "Timestamp", "latest_completed_candle_time", "Published",
    "publication_time", "Date",
)


def _time_column(frame: pd.DataFrame, preferred: Optional[str] = None) -> Optional[str]:
    if preferred and preferred in frame.columns:
        return preferred
    for name in _TIME_CANDIDATES:
        if name in frame.columns:
            return name
    return None


def _utc_series(frame: pd.DataFrame, column: Optional[str]) -> pd.Series:
    if column is None:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    if column == "Date" and "Hour" in frame.columns:
        values = frame["Date"].astype(str) + " " + frame["Hour"].astype(str)
    else:
        values = frame[column]
    return pd.to_datetime(values, errors="coerce", utc=True)


def chronological_view(
    frame: pd.DataFrame,
    row_limit: Optional[int] = None,
    *,
    time_column: Optional[str] = None,
    now: Optional[pd.Timestamp | datetime] = None,
    future_tolerance: str | pd.Timedelta = "5min",
) -> pd.DataFrame:
    """Return current/latest valid rows first without changing source values.

    Invalid timestamps and future timestamps are excluded whenever a timestamp
    column is available.  ``head`` is intentionally used after descending sort;
    calling ``tail`` here would reintroduce the current-first regression.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    view = frame.copy(deep=False)
    column = _time_column(view, time_column)
    parsed = _utc_series(view, column)
    if column is not None:
        current = pd.Timestamp(now or datetime.now(timezone.utc))
        if current.tzinfo is None:
            current = current.tz_localize("UTC")
        else:
            current = current.tz_convert("UTC")
        tolerance = pd.Timedelta(future_tolerance)
        valid = parsed.notna() & parsed.le(current + tolerance)
        view = view.loc[valid].copy(deep=False)
        parsed = parsed.loc[valid]
        view = view.assign(__canonical_order_time=parsed)
        view = view.sort_values(
            "__canonical_order_time", ascending=False, kind="stable", na_position="last"
        ).drop(columns="__canonical_order_time")
    if row_limit is not None:
        view = view.head(max(0, int(row_limit)))
    return view.reset_index(drop=True)


def priority_view(frame: pd.DataFrame, row_limit: Optional[int] = None) -> pd.DataFrame:
    """Rank canonical opportunity rows without altering chronological history.

    Ordering: qualified status, priority score, expected value, reliability,
    lower conflict, lower exit risk, current-day preference, then newest time.
    Missing fields are handled neutrally and no direction is recalculated.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    view = frame.copy(deep=False)
    status_col = next((c for c in ("Qualification Status", "qualification status", "Status") if c in view.columns), None)
    status = view[status_col].astype(str).str.upper() if status_col else pd.Series("NO ENTRY / WAIT", index=view.index)
    status_order = status.map({
        "QUALIFIED ENTRY": 0,
        "WATCH CANDIDATE": 1,
        "NO ENTRY / WAIT": 2,
        "NO ENTRY": 2,
    }).fillna(3)

    def numeric(*names: str, default: float = 0.0) -> pd.Series:
        name = next((n for n in names if n in view.columns), None)
        if name is None:
            return pd.Series(default, index=view.index, dtype=float)
        return pd.to_numeric(view[name], errors="coerce").fillna(default)

    priority = numeric("Priority Score", "combined score", "Final Score")
    expected_value = numeric("Expected Value", "expected_value", default=float("-inf"))
    reliability = numeric("Reliability %", "Reliability", "regime reliability")
    exit_risk = numeric("Exit Risk /10", "Exit Risk", default=10.0)
    current_day_col = next((c for c in ("Current Day", "current day") if c in view.columns), None)
    current_day = view[current_day_col].fillna(False).astype(bool) if current_day_col else pd.Series(False, index=view.index)
    conflict_col = next((c for c in ("Conflict Status", "conflict status", "NLP Conflict") if c in view.columns), None)
    conflict_text = view[conflict_col].astype(str).str.upper() if conflict_col else pd.Series("NONE", index=view.index)
    conflict_order = conflict_text.map(
        lambda text: 3 if "CRITICAL" in text else 2 if "SEVERE" in text else 1 if "CONFLICT" in text else 0
    )
    time_col = _time_column(view)
    times = _utc_series(view, time_col)

    view = view.assign(
        __status_order=status_order,
        __priority_score=priority,
        __expected_value=expected_value,
        __reliability=reliability,
        __conflict_order=conflict_order,
        __exit_risk=exit_risk,
        __current_day=current_day,
        __priority_time=times,
    ).sort_values(
        [
            "__status_order", "__priority_score", "__expected_value", "__reliability",
            "__conflict_order", "__exit_risk", "__current_day", "__priority_time",
        ],
        ascending=[True, False, False, False, True, True, False, False],
        kind="stable",
        na_position="last",
    )
    helper_columns = [c for c in view.columns if c.startswith("__")]
    view = view.drop(columns=helper_columns, errors="ignore")
    if row_limit is not None:
        view = view.head(max(0, int(row_limit)))
    return view.reset_index(drop=True)


def newest_first(frame: pd.DataFrame, row_limit: Optional[int] = None) -> pd.DataFrame:
    """Backward-compatible alias for chronological operational displays."""
    return chronological_view(frame, row_limit=row_limit)


__all__ = ["chronological_view", "priority_view", "newest_first"]
