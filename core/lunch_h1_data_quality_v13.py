"""Read-only selected-timeframe quality helpers for Lunch Fields 1, 3, 6 and 7.

Legacy H1 function names remain as compatibility aliases. The module never calls
a connector, trains a production model, settles an outcome or changes a protected decision.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping
import re

import numpy as np
import pandas as pd

from core.timeframe_window_contract_20260706 import horizon_contract, required_candles, selected_timeframe, window_contract

H1_EVIDENCE_VERSION = "lunch-selected-timeframe-decision-support-v14-20260706"
H1_QUALITY_VERSION = "lunch-selected-timeframe-quality-v14-20260706"


def _lookup(frame: pd.DataFrame) -> dict[str, Any]:
    return {str(column).strip().lower().replace("_", " "): column for column in frame.columns}


def _column(frame: pd.DataFrame, *aliases: str) -> Any | None:
    lookup = _lookup(frame)
    for alias in aliases:
        hit = lookup.get(alias.strip().lower().replace("_", " "))
        if hit is not None:
            return hit
    return None


def _hour_delta(values: pd.Series) -> pd.Series:
    """Parse numeric or text Hour values without attaching today's date."""
    numeric = pd.to_numeric(values, errors="coerce")
    result = pd.Series(pd.NaT, index=values.index, dtype="timedelta64[ns]")
    numeric_mask = numeric.notna() & numeric.between(0, 24, inclusive="left")
    result.loc[numeric_mask] = pd.to_timedelta(numeric.loc[numeric_mask], unit="h")

    text = values.astype(str).str.strip()
    plain_hour = text.str.fullmatch(r"\d{1,2}")
    text = text.where(~plain_hour, text + ":00:00")
    short_clock = text.str.fullmatch(r"\d{1,2}:\d{2}")
    text = text.where(~short_clock, text + ":00")
    clock_mask = text.str.fullmatch(r"\d{1,2}:\d{2}:\d{2}(?:\.\d+)?")
    if clock_mask.any():
        clock = pd.to_timedelta(text.where(clock_mask), errors="coerce")
        result = result.where(result.notna(), clock)

    # A few legacy frames store a full datetime in Hour.  Keep only its clock.
    remaining = result.isna()
    remaining_values = values.loc[remaining].dropna() if remaining.any() else pd.Series(dtype=object)
    if not remaining_values.empty:
        parsed = pd.to_datetime(remaining_values, errors="coerce", utc=True)
        seconds = parsed.dt.hour * 3600 + parsed.dt.minute * 60 + parsed.dt.second
        result.loc[remaining_values.index] = pd.to_timedelta(seconds, unit="s")
    return result


def combined_h1_time(frame: pd.DataFrame) -> pd.Series:
    """Return one UTC timestamp per row, combining separate Date + Hour first."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.Series(dtype="datetime64[ns, UTC]")

    date_col = _column(frame, "Date")
    hour_col = _column(frame, "Hour", "Broker Hour", "Candle Hour")
    if date_col is not None and hour_col is not None and date_col != hour_col:
        date = pd.to_datetime(frame[date_col], errors="coerce", utc=True).dt.floor("D")
        delta = _hour_delta(frame[hour_col])
        combined = date + delta
        if combined.notna().any():
            return pd.Series(combined, index=frame.index)

    for aliases in (
        ("event_time_utc",), ("latest_completed_h1_utc",), ("completed_candle_utc",),
        ("Time",), ("Datetime", "DateTime"), ("Timestamp",),
        ("Candle Time", "candle_time"), ("Date",),
    ):
        col = _column(frame, *aliases)
        if col is not None:
            parsed = pd.to_datetime(frame[col], errors="coerce", utc=True)
            if parsed.notna().any():
                return pd.Series(parsed, index=frame.index)

    if isinstance(frame.index, pd.DatetimeIndex):
        return pd.Series(pd.to_datetime(frame.index, errors="coerce", utc=True), index=frame.index)
    if not isinstance(frame.index, pd.RangeIndex):
        parsed = pd.to_datetime(frame.index, errors="coerce", utc=True)
        if isinstance(parsed, pd.DatetimeIndex) and parsed.notna().any():
            return pd.Series(parsed, index=frame.index)
    return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")


def with_h1_timestamp(frame: pd.DataFrame, *, output_column: str = "event_time_utc") -> pd.DataFrame:
    """Add an authoritative H1 timestamp while preserving every original column."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame() if frame is None else frame.copy(deep=False)
    work = frame.copy(deep=False)
    parsed = combined_h1_time(work)
    if parsed.notna().any():
        work = work.copy()
        work[output_column] = parsed
        # Existing renderers commonly search Time before event_time_utc.
        work["Time"] = parsed
    return work


def completed_h1_frame(
    frame: pd.DataFrame,
    *,
    completed_h1: Any | None = None,
    days: int = 25,
    maximum_rows: int | None = None,
    descending: bool = True,
    timeframe: str = "H1",
) -> pd.DataFrame:
    """Return unique completed H1 rows over a bounded 25-day window."""
    source_rows = int(len(frame)) if isinstance(frame, pd.DataFrame) else 0
    tf = selected_timeframe(timeframe)
    maximum_rows = int(maximum_rows or required_candles(tf, "higher"))
    work = with_h1_timestamp(frame)
    if work.empty or "event_time_utc" not in work.columns:
        return work.tail(maximum_rows).reset_index(drop=True)
    stamps = pd.to_datetime(work["event_time_utc"], errors="coerce", utc=True)
    cutoff = pd.to_datetime(completed_h1, errors="coerce", utc=True)
    if pd.isna(cutoff):
        cutoff = stamps.max() if stamps.notna().any() else pd.NaT
    mask = stamps.notna()
    if pd.notna(cutoff):
        mask &= stamps.le(cutoff) & stamps.ge(cutoff - pd.Timedelta(days=max(1, int(days))))
    work = work.loc[mask].copy()
    if work.empty:
        return work.reset_index(drop=True)
    work["event_time_utc"] = stamps.loc[work.index]
    work["Time"] = work["event_time_utc"]
    identity = canonical_identity_columns(work)
    work = work.sort_values("event_time_utc", ascending=not descending, kind="mergesort")
    work = work.drop_duplicates(identity, keep="first").head(max(1, int(maximum_rows))).reset_index(drop=True)
    work.attrs["h1_projection"] = quality_report(
        frame, projected=work, source_rows=source_rows, identity_columns=identity,
        completed_h1=cutoff,
    )
    return work


def canonical_identity_columns(frame: pd.DataFrame) -> list[str]:
    """Return stable event identity columns without using local wall-clock time."""
    if not isinstance(frame, pd.DataFrame):
        return ["event_time_utc"]
    columns = ["event_time_utc"] if "event_time_utc" in frame.columns else []
    for aliases in (
        ("Symbol", "symbol"), ("Timeframe", "timeframe"),
        ("Horizon", "horizon", "horizon_hours"),
        ("Model Version", "model_version", "version", "logic_version"),
    ):
        column = _column(frame, *aliases)
        if column is not None and column not in columns:
            columns.append(column)
    if columns:
        return columns
    return [str(frame.columns[0])] if len(frame.columns) else []


def quality_report(
    source: pd.DataFrame,
    *,
    projected: pd.DataFrame | None = None,
    source_rows: int | None = None,
    identity_columns: Iterable[str] | None = None,
    completed_h1: Any | None = None,
    provenance: str = "published_lunch_history",
    timeframe: str = "H1",
) -> dict[str, Any]:
    """Return transparent finite/time/missingness diagnostics for a history view."""
    frame = source if isinstance(source, pd.DataFrame) else pd.DataFrame()
    normalized = with_h1_timestamp(frame)
    if "event_time_utc" in normalized.columns:
        stamps = pd.to_datetime(normalized["event_time_utc"], errors="coerce", utc=True)
    else:
        stamps = pd.Series(pd.NaT, index=normalized.index, dtype="datetime64[ns, UTC]")
    rows = int(source_rows if source_rows is not None else len(frame))
    ids = [c for c in (identity_columns or canonical_identity_columns(normalized)) if c in normalized.columns]
    duplicate_rows = int(normalized.duplicated(ids, keep=False).sum()) if ids and not normalized.empty else 0
    numeric = normalized.select_dtypes(include=[np.number])
    finite_ratio = 1.0
    if not numeric.empty:
        values = numeric.apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
        finite_ratio = float(np.isfinite(values).sum() / max(1, values.size))
    missing_ratio = float(normalized.isna().sum().sum() / max(1, normalized.size)) if not normalized.empty else 1.0
    valid = stamps.dropna()
    monotonic = bool(valid.is_monotonic_increasing or valid.is_monotonic_decreasing) if not valid.empty else False
    cutoff = pd.to_datetime(completed_h1, errors="coerce", utc=True)
    latest = valid.max() if not valid.empty else pd.NaT
    stale_hours = None
    if pd.notna(cutoff) and pd.notna(latest):
        stale_hours = max(0.0, float((cutoff - latest).total_seconds() / 3600.0))
    projected_rows = int(len(projected)) if isinstance(projected, pd.DataFrame) else None
    status = "PASS"
    flags: list[str] = []
    if valid.empty:
        status = "FAIL"; flags.append("NO_VALID_EVENT_TIME")
    if finite_ratio < 1.0:
        status = "WARN" if status == "PASS" else status; flags.append("NON_FINITE_NUMERIC_VALUES")
    if missing_ratio > 0.20:
        status = "WARN" if status == "PASS" else status; flags.append("HIGH_MISSINGNESS")
    if duplicate_rows:
        status = "WARN" if status == "PASS" else status; flags.append("DUPLICATE_CANONICAL_IDENTITY")
    if valid.size > 1 and not monotonic:
        status = "WARN" if status == "PASS" else status; flags.append("NON_MONOTONIC_SOURCE_TIME")
    if stale_hours is not None and stale_hours > max(2.0, window_contract(selected_timeframe(timeframe))["timeframe_seconds"] / 3600.0 * 2.0):
        status = "WARN" if status == "PASS" else status; flags.append("STALE_COMPLETED_SELECTED_TIMEFRAME_SOURCE")
    return {
        "version": H1_QUALITY_VERSION,
        "status": status,
        "source_rows": rows,
        "projected_rows": projected_rows,
        "valid_timestamp_ratio": round(float(valid.size / max(1, rows)), 6),
        "finite_numeric_ratio": round(finite_ratio, 6),
        "missingness_ratio": round(missing_ratio, 6),
        "duplicate_ratio": round(float(duplicate_rows / max(1, rows)), 6),
        "monotonic_time": monotonic,
        "stale_hours": None if stale_hours is None else round(stale_hours, 3),
        "identity_columns": list(ids),
        "source_provenance": provenance,
        "future_actual_columns_allowed": False,
        "flags": flags,
    }


def cached_completed_ohlc(state: Mapping[str, Any]) -> pd.DataFrame:
    for key in (
        "canonical_completed_ohlc_df_20260617", "last_df", "dv_pp_df",
        "lunch_5layer_powerbi_df", "clean_preflight_ohlc_20260617",
    ):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy(deep=False)
    return pd.DataFrame()


def _canonical_cutoff(canonical: Mapping[str, Any] | None, state: Mapping[str, Any]) -> Any:
    canonical = canonical or {}
    market = canonical.get("market") if isinstance(canonical.get("market"), Mapping) else {}
    for value in (
        canonical.get("completed_candle_utc"), canonical.get("latest_completed_h1_utc"),
        canonical.get("latest_completed_candle_time"), market.get("latest_completed_candle_time"),
        state.get("latest_completed_h1_utc_20260622"),
    ):
        if value not in (None, ""):
            return value
    return None


def _numeric_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series:
    col = _column(frame, *aliases)
    if col is None:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce")


def build_h1_decision_evidence(
    state: Mapping[str, Any],
    canonical: Mapping[str, Any] | None = None,
    *,
    days: int = 25,
    limit: int = 600,
) -> pd.DataFrame:
    """Build causal shadow decision-support rows from completed cached H1 OHLC.

    These rows are not model validation and are never represented as settled
    outcomes.  They make empty Field 6/7 tables useful while preserving strict
    chronological ordering and the protected production decision.
    """
    canonical_map = canonical if isinstance(canonical, Mapping) else {}
    tf = selected_timeframe(canonical_map.get("timeframe") or state.get("timeframe") or "H1")
    source = cached_completed_ohlc(state)
    if source.empty:
        return pd.DataFrame()
    higher_required = required_candles(tf, "higher")
    data = completed_h1_frame(
        source, completed_h1=_canonical_cutoff(canonical, state), days=days,
        maximum_rows=max(limit, higher_required), descending=False, timeframe=tf,
    )
    if data.empty:
        return data

    close = _numeric_column(data, ("close", "Close", "c"))
    open_ = _numeric_column(data, ("open", "Open", "o"))
    high = _numeric_column(data, ("high", "High", "h"))
    low = _numeric_column(data, ("low", "Low", "l"))
    pip = 10000.0
    previous_close = close.shift(1)
    true_range = pd.concat(
        [(high - low).abs(), (high - previous_close).abs(), (low - previous_close).abs()], axis=1
    ).max(axis=1)

    result = pd.DataFrame(index=data.index)
    result["event_time_utc"] = pd.to_datetime(data["event_time_utc"], errors="coerce", utc=True)
    result["Open"] = open_
    result["High"] = high
    result["Low"] = low
    result["Close"] = close
    bars = {h: int(horizon_contract(timeframe=tf, horizon_hours=h)["horizon_bars"]) for h in (1, 3, 6, 12, 14, 24, 120)}
    result["Timeframe"] = tf
    result["Return 1H (pips)"] = (close - close.shift(bars[1])) * pip
    result["Momentum 3H (pips)"] = (close - close.shift(bars[3])) * pip
    result["Momentum 6H (pips)"] = (close - close.shift(bars[6])) * pip
    result["ATR 14H (pips)"] = true_range.rolling(bars[14], min_periods=max(2, bars[14] // 3)).mean() * pip
    result["Volatility 12H (pips)"] = close.diff().rolling(bars[12], min_periods=max(2, bars[12] // 3)).std() * pip
    ema12 = close.ewm(span=max(2, bars[12]), adjust=False, min_periods=max(2, bars[12] // 3)).mean()
    ema24 = close.ewm(span=max(3, bars[24]), adjust=False, min_periods=max(2, bars[24] // 3)).mean()
    ema120 = close.ewm(span=max(4, bars[120]), adjust=False, min_periods=max(3, bars[120] // 3)).mean()
    result["EMA 12H"] = ema12
    result["EMA 24H"] = ema24
    result["EMA 120H"] = ema120

    momentum_score = np.sign(result["Momentum 3H (pips)"].fillna(0)) + np.sign(result["Momentum 6H (pips)"].fillna(0))
    trend_score = np.sign((ema12 - ema24).fillna(0)) + np.sign((ema24 - ema120).fillna(0))
    candle_score = np.sign((close - open_).fillna(0))
    raw_score = momentum_score + trend_score + 0.5 * candle_score
    decision_level = (5.0 + raw_score * 0.9).clip(0.0, 10.0)
    result["Decision Level /10"] = decision_level.round(2)
    result["Shadow Decision"] = np.select(
        [decision_level >= 6.25, decision_level <= 3.75], ["BUY", "SELL"], default="WAIT"
    )
    strength = (decision_level - 5.0).abs()
    result["Actionability"] = np.select(
        [strength >= 2.25, strength >= 1.25], ["HIGH", "MEDIUM"], default="LOW"
    )
    result["Trend Agreement"] = np.where(
        np.sign((ema12 - ema24).fillna(0)) == np.sign(result["Momentum 3H (pips)"].fillna(0)),
        "ALIGNED", "MIXED",
    )
    hour = result["event_time_utc"].dt.hour
    result["Session (UTC)"] = np.select(
        [hour.between(7, 11), hour.between(12, 16), hour.between(17, 20)],
        ["LONDON", "LONDON/NY OVERLAP", "NEW YORK"], default="ASIA/OFF-HOURS",
    )
    quality_inputs = pd.concat([open_, high, low, close], axis=1).notna().mean(axis=1)
    result["Data Quality Score /100"] = (quality_inputs * 100.0).round(1)
    result["Data Quality"] = np.where(quality_inputs.eq(1.0), "PASS", "PARTIAL")
    result["Source Provenance"] = "CACHED_CANONICAL_COMPLETED_SELECTED_TIMEFRAME_OHLC"
    result["Evidence Class"] = "COMPLETED_SELECTED_TIMEFRAME_SHADOW_DECISION_SUPPORT"
    result["Settled Status"] = "NOT_A_SETTLED_OUTCOME"
    result["Production Decision Changed"] = "NO"
    result["Logic Version"] = H1_EVIDENCE_VERSION
    result = result.sort_values("event_time_utc", ascending=False).head(max(1, int(limit))).reset_index(drop=True)

    try:
        from core.shared_broker_time_20260622 import frame_to_shared_broker_clock
        result = frame_to_shared_broker_clock(
            result, state, canonical=dict(canonical or {}), hide_raw_utc=False,
            include_myanmar=False, reject_future_incomplete=True,
        )
        broker = next((c for c in result.columns if str(c).startswith("Broker Time")), None)
        if broker and broker != "Broker Time":
            result = result.rename(columns={broker: "Broker Time"})
    except Exception:
        pass
    return result


def build_regime_decision_matrix(
    state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None, *, limit: int = 600
) -> pd.DataFrame:
    evidence = build_h1_decision_evidence(state, canonical, limit=limit)
    if evidence.empty:
        return evidence
    out = evidence.copy()
    close = pd.to_numeric(out["Close"], errors="coerce")
    # Preserve 1/5/25-day semantics for every selected timeframe. For H4 this
    # means 6/30/150 completed candles instead of incorrectly using 24/120/600.
    canonical_map = canonical if isinstance(canonical, Mapping) else {}
    tf = selected_timeframe(canonical_map.get("timeframe") or state.get("timeframe") or "H4")
    bars_per_day = int(window_contract(tf)["bars_per_day"])
    out["Timeframe"] = tf
    # Work oldest-to-newest for rolling standards, then restore latest first.
    order = out.sort_values("event_time_utc").copy()
    order["Timeframe"] = tf
    close = pd.to_numeric(order["Close"], errors="coerce")
    for label, bars in (("Lower 1-Day", bars_per_day), ("Middle 5-Day", bars_per_day * 5), ("Higher 25-Day", bars_per_day * 25)):
        minimum = max(3, min(bars, bars_per_day)) if bars > 1 else 1
        mean = close.rolling(bars, min_periods=minimum).mean()
        scale = close.rolling(bars, min_periods=minimum).std().replace(0, np.nan)
        z = (close - mean) / scale
        order[f"{label} Z-Score"] = z.round(3)
        order[f"{label} Regime"] = np.select([z >= 0.35, z <= -0.35], ["BULL", "BEAR"], default="NEUTRAL")
    order["Regime Decision Level /10"] = pd.to_numeric(order["Decision Level /10"], errors="coerce")
    return order.sort_values("event_time_utc", ascending=False).head(limit).reset_index(drop=True)


def field6_fallback(table_name: str, state: Mapping[str, Any], canonical: Mapping[str, Any] | None, *, limit: int = 200) -> pd.DataFrame:
    frame = build_h1_decision_evidence(state, canonical, limit=max(25, limit))
    if frame.empty:
        return frame
    frame = frame.copy()
    frame.insert(0, "History Context", table_name)
    frame.insert(1, "Evidence Scope", "25-DAY COMPLETED SELECTED-TIMEFRAME DECISION SUPPORT")
    return frame.head(limit)


__all__ = [
    "H1_EVIDENCE_VERSION", "H1_QUALITY_VERSION", "combined_h1_time", "with_h1_timestamp",
    "completed_h1_frame", "cached_completed_ohlc", "build_h1_decision_evidence",
    "build_regime_decision_matrix", "field6_fallback", "canonical_identity_columns", "quality_report",
]
