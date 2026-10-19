"""Shared short decision text and causal, timestamp-based 12-hour exit notice."""
from __future__ import annotations

import numpy as np
import pandas as pd

EXIT_NOTICE_HOURS = 12


def compact_entry(bias, hits, tp, sl):
    return f"{str(bias).upper()}-{int(hits)} TP {tp} SL {sl}"


def annotate_middle_bias_exits(frame, *, copy=True):
    """Retain a notice for [flip, flip+12h), including on fresh entry rows.

    Stored flip timestamps let a date-filtered Finder and a single-row live
    table retain events that happened before the displayed range.
    """
    out = frame.copy() if copy else frame
    if out.empty:
        return out
    time_col = next((c for c in ("signal_available_at", "bar_close_time", "Completed Candle", "Datetime", "_FinderDatetime", "open_time") if c in out), None)
    if time_col is None or "Middle Regime Bias" not in out:
        return out
    ts = pd.to_datetime(out[time_col], errors="coerce", utc=True)
    event = pd.to_datetime(out.get("Middle Bias Flip At", pd.Series(pd.NaT, index=out.index)), errors="coerce", utc=True)
    symbols = out.get("Symbol", pd.Series("", index=out.index)).astype(str)
    timeframes = out.get("Timeframe", pd.Series("", index=out.index)).astype(str)
    temp = pd.DataFrame({"ts": ts, "bias": out["Middle Regime Bias"].astype(str).str.upper(),
                         "symbol": symbols, "tf": timeframes, "event": event}, index=out.index)
    temp = temp.sort_values("ts", kind="mergesort")
    group = temp.groupby(["symbol", "tf"], sort=False, dropna=False)
    previous = group["bias"].shift()
    flip = previous.isin(["BUY", "SELL"]) & temp["bias"].isin(["BUY", "SELL"]) & previous.ne(temp["bias"])
    temp["event"] = temp["event"].where(~flip, temp["ts"])
    event = temp.groupby(["symbol", "tf"], sort=False, dropna=False)["event"].ffill().reindex(out.index)
    age = (ts - event).dt.total_seconds() / 3600.0
    active = age.ge(0) & age.lt(EXIT_NOTICE_HOURS)
    out["Middle Bias Flip At"] = event
    out["Middle Bias SL Reach"] = active
    return out


def apply_exit_notice(frame, *, recompute=True, copy=True):
    """Keep exit-state audit columns without adding SL text to the decision.

    Older persisted rows can still contain ``| SL reach``.  Strip that legacy
    suffix during every live/Finder normalization so Strategy Decision remains
    entry-only as requested.
    """
    out = annotate_middle_bias_exits(frame, copy=copy) if recompute else (frame.copy() if copy else frame)
    if "Strategy Decision" not in out:
        out["Strategy Decision"] = "None"
    text = out["Strategy Decision"].fillna("None").astype(str)
    text = text.str.replace(r"\s*\|\s*SL\s*reach\b.*$", "", regex=True, case=False)
    out["Strategy Decision"] = text.mask(text.str.fullmatch(r"\s*SL\s*reach\s*", case=False), "None")
    return out
