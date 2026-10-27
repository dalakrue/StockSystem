"""Broker-day locked Middle/Higher regime evidence for Lunch Field 3.

The existing protected regime calculations remain untouched.  This module
reuses the completed-H1 120/600-candle analytics, samples them at broker-day
start, and holds the published Middle/Higher display regime until the next
broker 00:00 boundary.  The Lower 24-candle regime is intentionally not locked.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta, timezone
from typing import Any, Mapping, MutableMapping

import pandas as pd

LOCK_KEY = "daily_locked_regime_20260625"
HISTORY_KEY = "daily_locked_regime_history_20260625"
VERSION = "daily-locked-regime-20260625-v1"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _canonical(state: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical

        value = get_canonical(state)
        if isinstance(value, Mapping):
            return value
    except Exception:
        pass
    for key in (
        "canonical_decision_result_20260617",
        "canonical_decision_result",
        "last_valid_canonical_decision_result_20260617",
    ):
        value = state.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _ohlc(state: Mapping[str, Any]) -> pd.DataFrame:
    frame = None
    for key in (
        "canonical_completed_ohlc_df_20260617",
        "calculation_staging_ohlc_df_20260617",
        "dv_pp_df",
        "last_df",
    ):
        candidate = state.get(key)
        if isinstance(candidate, pd.DataFrame) and not candidate.empty:
            frame = candidate
            break
    if frame is None:
        return pd.DataFrame()
    normalized = {str(c).strip().lower().replace("_", " "): c for c in frame.columns}
    time_col = next(
        (normalized.get(name) for name in ("time", "datetime", "timestamp", "date") if normalized.get(name) is not None),
        None,
    )
    close_col = normalized.get("close") or normalized.get("c")
    if time_col is None or close_col is None:
        return pd.DataFrame()
    out = pd.DataFrame({"time": pd.to_datetime(frame[time_col], errors="coerce", utc=True)})
    for target, aliases in {
        "open": ("open", "o"),
        "high": ("high", "h"),
        "low": ("low", "l"),
        "close": ("close", "c"),
    }.items():
        source = next((normalized.get(alias) for alias in aliases if normalized.get(alias) is not None), None)
        out[target] = pd.to_numeric(frame[source], errors="coerce") if source is not None else pd.NA
    out = out.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates("time", keep="last")
    out["open"] = out["open"].fillna(out["close"])
    out["high"] = out["high"].fillna(out[["open", "close"]].max(axis=1))
    out["low"] = out["low"].fillna(out[["open", "close"]].min(axis=1))
    return out.tail(1200).reset_index(drop=True)


def _broker_contract(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from core.shared_broker_time_20260622 import shared_broker_time_provider

        return dict(shared_broker_time_provider(state, canonical=dict(canonical)))
    except Exception:
        event = pd.to_datetime(
            canonical.get("latest_completed_candle_time") or canonical.get("broker_candle_time"),
            errors="coerce",
            utc=True,
        )
        return {
            "latest_completed_h1_utc": None if pd.isna(event) else pd.Timestamp(event),
            "broker_time": None if pd.isna(event) else pd.Timestamp(event),
            "broker_clock_available": False,
            "broker_offset_minutes": 0,
            "broker_time_display": str(event),
        }


def _row(table: Any) -> dict[str, Any]:
    if isinstance(table, pd.DataFrame) and not table.empty:
        return {str(k): v for k, v in table.iloc[-1].to_dict().items()}
    return {}


def _iso(value: Any) -> str | None:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return None if pd.isna(parsed) else pd.Timestamp(parsed).isoformat()


def _candidate(
    frame: pd.DataFrame,
    *,
    existing_regime: str,
    existing_reliability: float,
) -> dict[str, Any]:
    from core.regime_window_analytics_20260618 import build_regime_window_analytics

    analytics = build_regime_window_analytics(
        frame,
        existing_regime=existing_regime,
        existing_reliability=existing_reliability,
    )
    tables = _mapping(analytics.get("tables"))
    return {
        "analytics_ok": bool(analytics.get("ok")),
        "lower": _row(tables.get("lower")),
        "middle": _row(tables.get("medium")),
        "higher": _row(tables.get("higher")),
        "alignment": dict(_mapping(analytics.get("alignment"))),
        "last_completed_candle": analytics.get("last_completed_candle"),
        "actual_history_rows": int(analytics.get("actual_history_rows") or 0),
    }


def ensure_daily_locked_regime(
    state: MutableMapping[str, Any],
    canonical: Mapping[str, Any] | None = None,
    *,
    force_new_day: bool = False,
) -> dict[str, Any]:
    """Return the stable broker-day regime lock, creating it only once per day."""
    canonical = dict(canonical or _canonical(state))
    frame = _ohlc(state)
    contract = _broker_contract(state, canonical)
    completed_utc = pd.to_datetime(contract.get("latest_completed_h1_utc"), errors="coerce", utc=True)
    if pd.isna(completed_utc) and not frame.empty:
        completed_utc = pd.Timestamp(frame["time"].max())
    if pd.isna(completed_utc):
        return {
            "ok": False,
            "status": "UNAVAILABLE",
            "reason": "No canonical completed-H1 candle is available.",
            "version": VERSION,
        }
    completed_utc = pd.Timestamp(completed_utc).tz_convert("UTC")

    offset_minutes = contract.get("broker_offset_minutes")
    try:
        offset_minutes = int(offset_minutes)
    except Exception:
        offset_minutes = 0
    # A fixed offset is sufficient because the broker contract already resolves
    # any configured IANA/DST clock to the active candle's exact offset.
    broker_tz = timezone(timedelta(minutes=offset_minutes))
    broker_time = completed_utc.tz_convert(broker_tz)
    broker_day = broker_time.strftime("%Y-%m-%d")
    broker_day_start_wall = broker_time.normalize()
    cutoff_utc = broker_day_start_wall.tz_convert("UTC")
    next_review_utc = (broker_day_start_wall + pd.Timedelta(days=1)).tz_convert("UTC")

    existing = state.get(LOCK_KEY)
    if (
        isinstance(existing, Mapping)
        and existing.get("broker_day") == broker_day
        and not force_new_day
    ):
        locked = deepcopy(dict(existing))
        locked["hours_until_next_review"] = round(max(0.0, (next_review_utc - completed_utc).total_seconds() / 3600.0), 2)
        locked["current_completed_candle_utc"] = completed_utc.isoformat()
        # Intraday candidate is diagnostic only; the locked values never change.
        if not frame.empty:
            current = _candidate(
                frame.loc[frame["time"].le(completed_utc)],
                existing_regime=str(_mapping(canonical.get("regime")).get("major_regime") or ""),
                existing_reliability=float(_mapping(canonical.get("regime")).get("reliability") or 50.0),
            )
            locked["intraday_candidate"] = current
            locked["intraday_change_detected"] = any(
                str(_mapping(current.get(name)).get("Current Regime") or "UNKNOWN")
                != str(_mapping(locked.get(name)).get("regime") or "UNKNOWN")
                for name in ("middle", "higher")
            )
        state[LOCK_KEY] = locked
        return locked

    if frame.empty:
        return {
            "ok": False,
            "status": "UNAVAILABLE",
            "reason": "Completed H1 OHLC is unavailable.",
            "version": VERSION,
        }

    # At any intraday run, use only observations available at broker 00:00.
    cutoff_frame = frame.loc[frame["time"].le(cutoff_utc)].copy()
    if cutoff_frame.empty:
        cutoff_frame = frame.loc[frame["time"].le(completed_utc)].copy()
    regime = _mapping(canonical.get("regime"))
    candidate = _candidate(
        cutoff_frame,
        existing_regime=str(regime.get("major_regime") or regime.get("current_regime") or ""),
        existing_reliability=float(regime.get("reliability") or regime.get("regime_reliability") or 50.0),
    )

    history = state.get(HISTORY_KEY)
    history = list(history) if isinstance(history, list) else []
    previous = history[-1] if history and isinstance(history[-1], Mapping) else {}

    def locked_standard(name: str, requested: int) -> dict[str, Any]:
        row = _mapping(candidate.get(name))
        regime_name = str(row.get("Current Regime") or "UNKNOWN")
        previous_standard = _mapping(previous.get(name))
        previous_regime = str(previous_standard.get("regime") or "")
        if previous_regime == regime_name and previous_standard.get("regime_start_broker_time"):
            regime_start = previous_standard.get("regime_start_broker_time")
        else:
            regime_start = broker_day_start_wall.isoformat()
        indicator_samples = int(row.get("Actual Sample Count") or 0)
        source_candles = min(requested, int(len(cutoff_frame)))
        return {
            "regime": regime_name,
            "bias": str(row.get("Less-Risky Bias") or "WAIT"),
            "reliability": float(row.get("Reliability") or 0.0),
            "transition_risk": float(row.get("Transition Risk") or 0.0),
            "alpha": float(row.get("Alpha Point") or 0.0),
            "delta": float(row.get("Delta Point") or 0.0),
            "alpha_slope": float(row.get("Alpha Slope") or 0.0),
            # ``sample_count`` is the raw completed-H1 window requested by the
            # user.  Indicator observations are separately exposed because the
            # six-bar causal return naturally has fewer initialized values.
            "sample_count": source_candles,
            "indicator_sample_count": indicator_samples,
            "required_candles": requested,
            "sample_complete": source_candles >= requested,
            "window_start_utc": _iso(row.get("Start Time")),
            "window_end_utc": _iso(row.get("End Time")),
            "regime_start_broker_time": regime_start,
            "locked_at_broker_time": broker_day_start_wall.isoformat(),
            "locked_until_broker_time": (broker_day_start_wall + pd.Timedelta(days=1)).isoformat(),
        }

    locked = {
        "ok": bool(candidate.get("analytics_ok")),
        "status": "LOCKED_UNTIL_NEXT_BROKER_DAY",
        "version": VERSION,
        "broker_day": broker_day,
        "broker_offset_minutes": offset_minutes,
        "lock_start_broker_time": broker_day_start_wall.isoformat(),
        "next_review_broker_time": (broker_day_start_wall + pd.Timedelta(days=1)).isoformat(),
        "analysis_cutoff_utc": cutoff_utc.isoformat(),
        "source_run_id": str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or ""),
        "source_generation": canonical.get("calculation_generation"),
        "source_snapshot_hash": str(canonical.get("snapshot_hash") or canonical.get("source_snapshot_hash") or ""),
        "current_completed_candle_utc": completed_utc.isoformat(),
        "hours_until_next_review": round(max(0.0, (next_review_utc - completed_utc).total_seconds() / 3600.0), 2),
        "lower": {
            "regime": str(_mapping(candidate.get("lower")).get("Current Regime") or "UNKNOWN"),
            "bias": str(_mapping(candidate.get("lower")).get("Less-Risky Bias") or "WAIT"),
            "reliability": float(_mapping(candidate.get("lower")).get("Reliability") or 0.0),
            "sample_count": int(_mapping(candidate.get("lower")).get("Actual Sample Count") or 0),
            "update_policy": "ROLLING_EACH_COMPLETED_H1",
        },
        "middle": locked_standard("middle", 120),
        "higher": locked_standard("higher", 600),
        "alignment": dict(_mapping(candidate.get("alignment"))),
        "intraday_candidate": candidate,
        "intraday_change_detected": False,
        "production_regime_changed": False,
        "protected_logic_unchanged": True,
    }
    history.append(deepcopy(locked))
    state[HISTORY_KEY] = history[-40:]
    state[LOCK_KEY] = locked
    return locked


__all__ = ["LOCK_KEY", "HISTORY_KEY", "VERSION", "ensure_daily_locked_regime"]
