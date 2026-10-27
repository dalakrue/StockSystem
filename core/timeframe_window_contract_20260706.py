"""Shared selected-timeframe window and horizon contract.

This module contains no trading formula.  It only translates calendar windows
and forecast horizons into bars for the selected runtime timeframe, validates
completed-candle spacing, and supplies display-safe coverage metadata.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

BARS_PER_DAY: dict[str, int] = {
    "M1": 1440,
    "M5": 288,
    "M15": 96,
    "M30": 48,
    "H1": 24,
    "H4": 6,
    "D1": 1,
}
TIMEFRAME_SECONDS: dict[str, int] = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}
ALIASES = {
    "1M": "M1", "5M": "M5", "15M": "M15", "30M": "M30",
    "1H": "H1", "4H": "H4", "60MIN": "H1", "240MIN": "H4",
    "1D": "D1", "1DAY": "D1", "DAILY": "D1",
}


def normalize_timeframe(value: Any, default: str = "H4") -> str:
    raw = str(value or default).strip().upper().replace(" ", "")
    raw = ALIASES.get(raw, raw)
    return raw if raw in BARS_PER_DAY else default


@dataclass(frozen=True)
class TimeframeWindowContract:
    timeframe: str
    bars_per_day: int
    lower_required: int
    middle_required: int
    higher_required: int
    timeframe_seconds: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


def window_contract(timeframe: Any) -> TimeframeWindowContract:
    tf = normalize_timeframe(timeframe)
    per_day = BARS_PER_DAY[tf]
    return TimeframeWindowContract(
        timeframe=tf,
        bars_per_day=per_day,
        lower_required=per_day,
        middle_required=per_day * 5,
        higher_required=per_day * 25,
        timeframe_seconds=TIMEFRAME_SECONDS[tf],
    )


def required_candles(timeframe: Any, standard: str = "higher") -> int:
    contract = window_contract(timeframe)
    key = str(standard or "higher").strip().lower()
    if key in {"lower", "low", "1d", "1-day"}:
        return contract.lower_required
    if key in {"middle", "medium", "5d", "5-day"}:
        return contract.middle_required
    return contract.higher_required


def minimum_calculation_candles(timeframe: Any, standard: str = "higher") -> int:
    """Smallest genuine-history window admitted to degraded calculation.

    The full 25-day window remains the quality target.  A symbol is no longer
    rejected merely because a provider is a few candles short (for example
    597/600), and a real 100-candle series can still produce an explicitly
    labelled adaptive result.  No candle is padded, copied, or synthesized.
    """
    return max(1, min(int(required_candles(timeframe, standard)), 100))


def calculation_eligibility(*, timeframe: Any, available: Any, required: Any | None = None) -> dict[str, Any]:
    tf = normalize_timeframe(timeframe)
    full_required = int(required if required is not None else required_candles(tf, "higher"))
    minimum_required = min(full_required, minimum_calculation_candles(tf, "higher"))
    count = max(0, int(available or 0))
    if count >= full_required:
        mode = "FULL_HISTORY"
    elif count >= minimum_required:
        mode = "ADAPTIVE_PARTIAL_HISTORY"
    else:
        mode = "BELOW_MINIMUM_HISTORY"
    return {
        "eligible": count >= minimum_required,
        "mode": mode,
        "available_candles": count,
        "required_candles": full_required,
        "minimum_calculation_candles": minimum_required,
        "full_history": count >= full_required,
    }


def horizon_contract(*, horizon_bars: Any | None = None, horizon_hours: Any | None = None, timeframe: Any = "H4") -> dict[str, Any]:
    """Return an explicit bars/hours/seconds identity without changing duration.

    When ``horizon_hours`` is supplied, it is converted to the smallest whole
    number of selected-timeframe bars that fully covers that real duration.
    When ``horizon_bars`` is supplied, hours are derived from bar duration.
    """
    tf = normalize_timeframe(timeframe)
    seconds = TIMEFRAME_SECONDS[tf]
    if horizon_bars is None and horizon_hours is None:
        raise ValueError("horizon_bars or horizon_hours is required")
    if horizon_bars is None:
        hours = float(horizon_hours)
        bars = int(np.ceil(max(0.0, hours * 3600.0) / seconds))
    else:
        bars = max(0, int(horizon_bars))
        hours = bars * seconds / 3600.0
    return {
        "timeframe": tf,
        "timeframe_seconds": seconds,
        "horizon_bars": bars,
        "horizon_hours": float(hours),
    }


def normalize_completed_frame(
    frame: pd.DataFrame, *, timeframe: Any, cutoff: Any | None = None,
    completed_candle: Any | None = None, max_rows: int | None = None,
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    work = frame.copy()
    time_col = next((c for c in work.columns if str(c).strip().lower() in {
        "time", "datetime", "timestamp", "open_time", "broker timestamp", "completed broker candle"
    }), None)
    if time_col is None:
        if isinstance(work.index, pd.DatetimeIndex):
            work = work.reset_index().rename(columns={work.index.name or "index": "time"})
            time_col = "time"
        else:
            return pd.DataFrame()
    work[time_col] = pd.to_datetime(work[time_col], errors="coerce", utc=True)
    work = work.dropna(subset=[time_col]).sort_values(time_col, kind="mergesort")
    work = work.drop_duplicates(subset=[time_col], keep="last")
    effective_cutoff = completed_candle if completed_candle is not None else cutoff
    if effective_cutoff is not None:
        stamp = pd.to_datetime(effective_cutoff, errors="coerce", utc=True)
        if pd.notna(stamp):
            work = work.loc[work[time_col].le(stamp)]
    if max_rows is not None:
        work = work.tail(max(1, int(max_rows)))
    work = work.reset_index(drop=True)
    work.attrs["time_column"] = time_col
    work.attrs["timeframe"] = normalize_timeframe(timeframe)
    return work


def validate_timeframe_spacing(
    frame: pd.DataFrame, *, timeframe: Any, tolerance_seconds: int = 90,
    time_column: str | None = None,
) -> dict[str, Any]:
    tf = normalize_timeframe(timeframe)
    work = normalize_completed_frame(frame, timeframe=tf)
    time_col = time_column if time_column in work.columns else (work.attrs.get("time_column") or next((c for c in work.columns if str(c).lower() == "time"), None))
    if work.empty or time_col is None:
        return {"ok": False, "status": "NO_VALID_TIMESTAMPS", "timeframe": tf, "rows": 0}
    times = pd.to_datetime(work[time_col], errors="coerce", utc=True)
    diffs = times.diff().dt.total_seconds().dropna()
    expected = TIMEFRAME_SECONDS[tf]
    # Reject duplicate/sub-timeframe rows and small irregular offsets. Large
    # gaps are legal market closures (weekends, holidays, equity sessions) even
    # when the closure length is not an exact timeframe multiple because of
    # daylight-saving or exchange-session boundaries.
    modulo_error = (diffs % expected).abs()
    small_irregular = (diffs <= expected * 1.5) & (modulo_error > tolerance_seconds)
    bad = diffs[(diffs < expected - tolerance_seconds) | small_irregular]
    return {
        "ok": bool(bad.empty),
        "status": "PASS" if bad.empty else "INVALID_TIMEFRAME_SPACING",
        "timeframe": tf,
        "timeframe_seconds": expected,
        "rows": int(len(work)),
        "bad_spacing_count": int(len(bad)),
        "minimum_spacing_seconds": None if diffs.empty else float(diffs.min()),
        "median_spacing_seconds": None if diffs.empty else float(diffs.median()),
    }


def coverage_metadata(*, timeframe: Any, available: Any, required: Any | None = None) -> dict[str, Any]:
    tf = normalize_timeframe(timeframe)
    required_count = int(required if required is not None else required_candles(tf, "higher"))
    available_count = max(0, int(available or 0))
    eligibility = calculation_eligibility(timeframe=tf, available=available_count, required=required_count)
    coverage = min(100.0, 100.0 * available_count / max(1, required_count))
    completion = (
        "COMPLETE" if eligibility["full_history"]
        else "ADAPTIVE_PARTIAL" if eligibility["eligible"]
        else "BELOW_MINIMUM"
    )
    return {
        "Selected-Timeframe Completion": completion,
        "Required Candle Count": required_count,
        "Minimum Calculation Candle Count": eligibility["minimum_calculation_candles"],
        "Available Candle Count": available_count,
        "Timeframe": tf,
        "Coverage Percent": round(coverage, 2),
        "Calculation Eligible": bool(eligibility["eligible"]),
        "Calculation Mode": str(eligibility["mode"]),
    }


def evidence_tier(*, timeframe: Any, available: Any, required: Any | None = None) -> str:
    coverage = coverage_metadata(timeframe=timeframe, available=available, required=required)
    available_count = int(coverage["Available Candle Count"])
    required_count = int(coverage["Required Candle Count"])
    minimum_count = int(coverage["Minimum Calculation Candle Count"])
    if available_count >= required_count:
        return "COMPLETE_SELECTED_TIMEFRAME"
    if available_count >= minimum_count:
        return "ADAPTIVE_PARTIAL_SELECTED_TIMEFRAME"
    if available_count > 0:
        return "BELOW_MINIMUM_SELECTED_TIMEFRAME"
    return "NO_SELECTED_TIMEFRAME_HISTORY"


def insufficiency_label(*, timeframe: Any, available: Any, required: Any | None = None) -> str:
    coverage = coverage_metadata(timeframe=timeframe, available=available, required=required)
    available_count = int(coverage["Available Candle Count"])
    required_count = int(coverage["Required Candle Count"])
    minimum_count = int(coverage["Minimum Calculation Candle Count"])
    if available_count >= required_count:
        return "READY • FULL HISTORY"
    if available_count >= minimum_count:
        return f"READY • ADAPTIVE PARTIAL HISTORY {available_count}/{required_count}"
    return f"BELOW MINIMUM HISTORY {available_count}/{minimum_count}"


def validated_estimate_label(*, timeframe: Any, available: Any, required: Any | None = None) -> str:
    coverage = coverage_metadata(timeframe=timeframe, available=available, required=required)
    available_count = int(coverage["Available Candle Count"])
    required_count = int(coverage["Required Candle Count"])
    minimum_count = int(coverage["Minimum Calculation Candle Count"])
    if available_count >= required_count:
        return "VALIDATED ESTIMATE AVAILABLE • FULL HISTORY"
    if available_count >= minimum_count:
        return f"ADAPTIVE ESTIMATE AVAILABLE • PARTIAL HISTORY {available_count}/{required_count}"
    return f"ESTIMATE NOT AVAILABLE • BELOW MINIMUM {available_count}/{minimum_count}"


def evidence_contract(*, timeframe: Any, available: Any, required: Any | None = None) -> dict[str, Any]:
    coverage = coverage_metadata(timeframe=timeframe, available=available, required=required)
    return {
        **coverage,
        "Evidence Tier": evidence_tier(
            timeframe=timeframe,
            available=coverage["Available Candle Count"],
            required=coverage["Required Candle Count"],
        ),
        "History Status Label": insufficiency_label(
            timeframe=timeframe,
            available=coverage["Available Candle Count"],
            required=coverage["Required Candle Count"],
        ),
        "Estimate Status Label": validated_estimate_label(
            timeframe=timeframe,
            available=coverage["Available Candle Count"],
            required=coverage["Required Candle Count"],
        ),
    }


def selected_timeframe(value: Any = None, canonical: Mapping[str, Any] | None = None) -> str:
    """Resolve a selected timeframe from a state mapping or a direct value."""
    canonical = canonical if isinstance(canonical, Mapping) else {}
    if isinstance(value, Mapping):
        raw = (
            value.get("selected_timeframe")
            or value.get("timeframe")
            or canonical.get("timeframe")
            or "H4"
        )
    else:
        raw = value or canonical.get("timeframe") or "H4"
    return normalize_timeframe(raw)


__all__ = [
    "BARS_PER_DAY", "TIMEFRAME_SECONDS", "TimeframeWindowContract",
    "normalize_timeframe", "window_contract", "required_candles", "minimum_calculation_candles", "calculation_eligibility",
    "horizon_contract", "normalize_completed_frame", "validate_timeframe_spacing",
    "coverage_metadata", "evidence_tier", "insufficiency_label",
    "validated_estimate_label", "evidence_contract", "selected_timeframe",
]
