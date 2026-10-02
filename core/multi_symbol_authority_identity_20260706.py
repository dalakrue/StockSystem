"""Identity-only adapter for exact-symbol multi-symbol child publications.

The protected Full Metric adapter remains byte-for-byte unchanged and retains
its EURUSD/H1 operational guard.  During an explicit Settings-owned
multi-symbol child transaction, the protected adapter is executed exactly as
before and this module restamps only the resulting publication identity to the
selected symbol/timeframe.  No score, formula, direction, threshold, rank, or
tradeability value is recalculated or replaced.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

VERSION = "multi-symbol-authority-identity-20260706-v1"


def _latest_time(frame: Any) -> str | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    column = next((name for name in ("time", "Time", "datetime", "timestamp") if name in frame.columns), None)
    if column is None:
        return None
    stamp = pd.to_datetime(frame[column].iloc[-1], errors="coerce", utc=True)
    return None if pd.isna(stamp) else pd.Timestamp(stamp).isoformat()


def restamp_child_authority(
    authority: Mapping[str, Any],
    *,
    symbol: Any,
    timeframe: Any,
    source_frame: Any = None,
) -> dict[str, Any]:
    """Return an identity-restamped child authority without formula changes."""
    result = dict(authority or {})
    snapshot = dict(result.get("snapshot") or {})
    canonical_symbol = str(symbol or "").upper()
    canonical_timeframe = str(timeframe or "").upper()
    completed = _latest_time(source_frame) or snapshot.get("latest_completed_h1_time")
    snapshot.update({
        "symbol": canonical_symbol,
        "timeframe": canonical_timeframe,
        "latest_completed_candle_time": completed,
        "authority_scope": "MULTI_SYMBOL_CHILD",
        "operational_authority": False,
        "identity_adapter_version": VERSION,
        "protected_full_metric_logic_unchanged": True,
    })
    result["snapshot"] = snapshot

    top_two: list[dict[str, Any]] = []
    for record in result.get("top_two_daily_candidates") or []:
        if isinstance(record, Mapping):
            top_two.append({**dict(record), "symbol": canonical_symbol, "timeframe": canonical_timeframe})
    if top_two:
        result["top_two_daily_candidates"] = top_two
        snapshot["top_two_daily_candidates"] = top_two
    return result


__all__ = ["VERSION", "restamp_child_authority"]
