"""Bounded caches for pure preparation/display/export operations.

Calculation formulas remain in their original modules. These helpers separate
full calculation data from bounded browser payloads and include the canonical
identity in cache keys. Secrets are never accepted as parameters.
"""
from __future__ import annotations

import re
from typing import Iterable, Sequence

import pandas as pd

try:
    import streamlit as st
    cache_data = st.cache_data
except Exception:  # pragma: no cover - validation environment
    def cache_data(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

CALCULATION_VERSION = "decision-product-20260617-v1"


@cache_data(show_spinner=False, ttl=900, max_entries=24)
def cached_clean_ohlc(
    frame: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    source: str,
    data_signature: str,
    calculation_version: str = CALCULATION_VERSION,
) -> pd.DataFrame:
    """Normalize a real timestamped OHLC frame without inventing timestamps."""
    del symbol, timeframe, source, data_signature, calculation_version
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    out = frame.copy(deep=False)
    lower = {str(column).strip().lower(): column for column in out.columns}
    rename = {}
    for candidate in ("time", "datetime", "timestamp", "date_time", "date"):
        if candidate in lower:
            if lower[candidate] != "time":
                rename[lower[candidate]] = "time"
            break
    for candidate, target in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close")):
        if candidate in lower and target not in out.columns:
            rename[lower[candidate]] = target
    if rename:
        out = out.rename(columns=rename)
    if "time" not in out.columns or "close" not in out.columns:
        return pd.DataFrame()
    out["time"] = pd.to_datetime(out["time"], errors="coerce", utc=True).dt.tz_convert(None)
    for column in ("open", "high", "low", "close"):
        if column not in out.columns:
            out[column] = out["close"]
        out[column] = pd.to_numeric(out[column], errors="coerce")
    return out.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)


@cache_data(show_spinner=False, ttl=600, max_entries=32)
def cached_display_dataframe(
    frame: pd.DataFrame,
    *,
    row_limit: int,
    time_column: str,
    sort_columns: tuple[str, ...],
    ascending: tuple[bool, ...],
    data_signature: str,
    calculation_version: str = CALCULATION_VERSION,
) -> pd.DataFrame:
    """Return a bounded browser view while leaving full data untouched."""
    del data_signature, calculation_version
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    limit = max(24, int(row_limit))
    view = frame.copy(deep=False)
    parsed_time = None
    if time_column and time_column in view.columns:
        parsed_time = pd.to_datetime(view[time_column], errors="coerce", utc=True)
        if len(view) > limit:
            recent_index = parsed_time.sort_values(ascending=False, na_position="last").head(limit).index
            view = view.loc[recent_index]
            parsed_time = parsed_time.loc[recent_index]
    elif len(view) > limit:
        # Source tables are normally appended oldest -> newest. Keep the newest
        # bounded rows when no timestamp column exists.
        view = view.tail(limit)

    # A historical table must always begin at the current/latest completed row.
    # Ranking columns remain secondary so their values are preserved without
    # allowing an old high-ranked backtest row to appear above today's row.
    sort_names: list[str] = []
    sort_directions: list[bool] = []
    helper = "__new7_display_time"
    if parsed_time is not None and parsed_time.notna().any():
        view = view.assign(**{helper: parsed_time})
        sort_names.append(helper)
        sort_directions.append(False)
    for index, column in enumerate(sort_columns):
        if column == time_column or column not in view.columns or column in sort_names:
            continue
        sort_names.append(column)
        sort_directions.append(bool(ascending[index]) if index < len(ascending) else True)
    if sort_names:
        view = view.sort_values(sort_names, ascending=sort_directions, kind="stable", na_position="last")
    if helper in view.columns:
        view = view.drop(columns=helper)
    return view.reset_index(drop=True)


@cache_data(show_spinner=False, ttl=900, max_entries=16)
def cached_export_csv(
    frame: pd.DataFrame,
    *,
    data_signature: str,
    calculation_version: str = CALCULATION_VERSION,
) -> bytes:
    del data_signature, calculation_version
    if not isinstance(frame, pd.DataFrame):
        return b""
    return frame.to_csv(index=False).encode("utf-8")


@cache_data(show_spinner=False, ttl=1800, max_entries=32)
def cached_nlp_normalize(
    texts: tuple[str, ...],
    *,
    symbol: str,
    timeframe: str,
    source: str,
    data_signature: str,
    calculation_version: str = CALCULATION_VERSION,
) -> tuple[str, ...]:
    del symbol, timeframe, source, data_signature, calculation_version
    return tuple(re.sub(r"\s+", " ", str(text or "").strip().lower()) for text in texts)
