"""Immutable Field 10 day-end settlement and next-day candidate workflow.

Settlement is append-only and never updates the locked morning snapshot or its
symbol rows. It is intended to run from the existing Settings calculation at
broker 23:00 or later, not from Field 10 rendering.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any
import json

import numpy as np
import pandas as pd

from core.timeframe_window_contract_20260706 import horizon_contract, selected_timeframe, validate_timeframe_spacing

from core.sqlite_readonly_20260704 import connect_readonly

from core.field10_daily_snapshot_contract_20260702 import (
    DB_PATH, DAY_END_REVIEW_HOUR, _canonical_from_state, _canonical_json, _connect,
    _frame_from_state, _json_safe, _normalize_ohlc, deterministic_hash,
    load_current_daily_snapshot, migrate_daily_snapshot_database,
)
from core.multi_symbol_field10_20260701 import _cache_path, _read_cache_payload, normalize_symbol

VERSION = "field10-day-end-settlement-20260702-v1"


def _direction(start: float | None, end: float | None, tolerance: float = 1e-12) -> str:
    if start is None or end is None or not np.isfinite(start) or not np.isfinite(end):
        return "UNAVAILABLE"
    change = float(end) - float(start)
    if change > tolerance:
        return "BUY"
    if change < -tolerance:
        return "SELL"
    return "WAIT"


def _correct(bias: Any, actual: str) -> int | None:
    expected = str(bias or "").upper()
    if expected not in {"BUY", "SELL", "WAIT"} or actual == "UNAVAILABLE":
        return None
    return int(expected == actual)


def _cached_state(symbol: str) -> dict[str, Any]:
    try:
        payload = _read_cache_payload(_cache_path(symbol))
        state = payload.get("state")
        return dict(state) if isinstance(state, Mapping) else {}
    except Exception:
        return {}


def _broker_now(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> pd.Timestamp:
    from core.shared_broker_time_20260622 import shared_broker_time_provider
    contract = shared_broker_time_provider(state, canonical=dict(canonical))
    value = pd.to_datetime(contract.get("broker_time"), errors="coerce")
    if pd.isna(value):
        raise ValueError("Shared broker-time provider did not publish broker time")
    return pd.Timestamp(value)


def _settle_symbol(row: Mapping[str, Any], state: Mapping[str, Any], latest_completed_utc: Any) -> dict[str, Any]:
    timeframe = selected_timeframe(row.get("Timeframe") or state.get("timeframe") or _canonical_from_state(state).get("timeframe") or "H1")
    frame = _normalize_ohlc(_frame_from_state(state)).dropna(subset=["time", "open", "high", "low", "close"])
    frame = frame.sort_values("time", kind="mergesort").drop_duplicates("time", keep="last")
    spacing = validate_timeframe_spacing(frame, timeframe=timeframe, time_column="time")
    if not spacing.get("valid"):
        return {"settlement_status": "FAILED_VALIDATION", "reason": spacing.get("reason"), "timeframe": timeframe}
    cutoff = pd.to_datetime(row.get("Completed Broker Candle"), errors="coerce", utc=True)
    latest = pd.to_datetime(latest_completed_utc, errors="coerce", utc=True)
    if pd.isna(cutoff) or frame.empty:
        return {"settlement_status": "INSUFFICIENT_DATA", "reason": "cutoff or OHLC unavailable"}
    frame = frame.loc[frame["time"].ge(cutoff)]
    if pd.notna(latest):
        frame = frame.loc[frame["time"].le(latest)]
    anchor_rows = frame.loc[frame["time"].eq(cutoff)]
    if anchor_rows.empty:
        return {"settlement_status": "INSUFFICIENT_DATA", "reason": "cutoff close not found"}
    anchor = float(anchor_rows.iloc[-1]["close"])

    def horizon(hours: int) -> tuple[str, float | None]:
        # Target remains a real elapsed duration. The bar count is recorded only
        # for audit and never substituted for hours.
        target = pd.Timestamp(cutoff) + pd.Timedelta(hours=hours)
        found = frame.loc[frame["time"].ge(target)]
        if found.empty:
            return "UNAVAILABLE", None
        close = float(found.iloc[0]["close"])
        return _direction(anchor, close), close

    actual1, close1 = horizon(1)
    actual3, close3 = horizon(3)
    actual6, close6 = horizon(6)
    last_close = float(frame.iloc[-1]["close"]) if not frame.empty else None
    day_direction = _direction(anchor, last_close)
    after = frame.loc[frame["time"].gt(cutoff)]
    bias = str(row.get("Stable Daily Bias") or "WAIT").upper()
    if after.empty or anchor == 0:
        mfe = mae = None
    else:
        highs = pd.to_numeric(after["high"], errors="coerce")
        lows = pd.to_numeric(after["low"], errors="coerce")
        if bias == "BUY":
            mfe = float((highs.max() - anchor) / anchor)
            mae = float((lows.min() - anchor) / anchor)
        elif bias == "SELL":
            mfe = float((anchor - lows.min()) / anchor)
            mae = float((anchor - highs.max()) / anchor)
        else:
            mfe = float(max(abs(highs.max() - anchor), abs(lows.min() - anchor)) / anchor)
            mae = 0.0
    raw_result = None
    if last_close is not None and anchor:
        signed = (last_close - anchor) / anchor
        raw_result = signed if bias == "BUY" else (-signed if bias == "SELL" else 0.0)
    spread_pct = row.get("Spread Percentile")
    spread_cost = 0.0 if spread_pct is None or pd.isna(spread_pct) else min(0.002, float(spread_pct) / 100.0 * 0.0002)
    slippage_cost = spread_cost * 0.25
    spread_adjusted = None if raw_result is None else raw_result - spread_cost
    slippage_adjusted = None if spread_adjusted is None else spread_adjusted - slippage_cost
    calibrated = row.get("Calibrated Bias Probability")
    actual_correct = _correct(bias, actual1)
    calibration_error = None
    if calibrated is not None and not pd.isna(calibrated) and actual_correct is not None:
        probability = float(calibrated) / 100.0 if abs(float(calibrated)) > 1 else float(calibrated)
        calibration_error = abs(probability - float(actual_correct))
    settled = all(value != "UNAVAILABLE" for value in (actual1, actual3, actual6))
    return {
        "settlement_status": "CURRENT_DAY_SETTLED" if settled else "PARTIAL_SETTLEMENT",
        "actual_1h_direction": actual1, "actual_3h_direction": actual3,
        "actual_6h_direction": actual6, "day_close_direction": day_direction,
        "correct_1h": _correct(bias, actual1), "correct_3h": _correct(bias, actual3),
        "correct_6h": _correct(bias, actual6), "mfe": mfe, "mae": mae,
        "spread_adjusted_outcome": spread_adjusted,
        "slippage_adjusted_outcome": slippage_adjusted,
        "calibration_error": calibration_error,
        "anchor_close": anchor, "close_1h": close1, "close_3h": close3,
        "close_6h": close6, "day_close": last_close, "observed_rows": int(len(frame)),
        "timeframe": timeframe,
        "timeframe_seconds": int(horizon_contract(timeframe=timeframe, horizon_hours=1)["timeframe_seconds"]),
        "horizon_bars": {str(h): int(horizon_contract(timeframe=timeframe, horizon_hours=h)["horizon_bars"]) for h in (1, 3, 6)},
        "horizon_hours": [1, 3, 6],
    }


def prepare_next_day_candidate(
    *, metadata: Mapping[str, Any], current_rows: pd.DataFrame,
    prepared_at_broker_time: Any, parent_run_id: str | None = None,
    path: Path | str = DB_PATH,
) -> dict[str, Any]:
    migrate_daily_snapshot_database(path)
    source_day = str(metadata.get("broker_day"))
    target_day = (pd.Timestamp(source_day) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    payload = {
        "target_broker_day": target_day, "source_broker_day": source_day,
        "universe_hash": metadata.get("universe_hash"),
        "ordered_symbol_universe": metadata.get("ordered_symbol_universe"),
        "main_symbol": metadata.get("main_symbol"), "parent_run_id": parent_run_id,
        "latest_completed_h1": metadata.get("latest_completed_h1"),
        "source_rows": current_rows[[c for c in ("Daily Rank", "Symbol", "Daily Grade", "Institutional Morning Score", "Stable Daily Bias") if c in current_rows]].to_dict("records"),
        "activation_rule": "activate only at configured next morning cutoff after cutoff-complete evidence validation",
    }
    digest = deterministic_hash(payload)
    candidate_id = f"NEXT-{target_day.replace('-', '')}-{digest[:18]}"
    prepared = pd.Timestamp(prepared_at_broker_time).isoformat()
    with _connect(path) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO field10_next_day_candidate(
                candidate_id,target_broker_day,source_broker_day,universe_hash,status,
                parent_run_id,latest_completed_h1,candidate_hash,candidate_json,
                prepared_at_broker_time,activated_snapshot_id
            ) VALUES(?,?,?,?,?,?,?,?,?,?,NULL)""",
            (candidate_id, target_day, source_day, str(metadata.get("universe_hash") or ""),
             "NEXT_DAY_CANDIDATE_READY", str(parent_run_id or metadata.get("parent_run_id") or ""),
             str(metadata.get("latest_completed_h1") or ""), digest, _canonical_json(payload), prepared),
        )
        conn.commit()
    return {"ok": True, "status": "NEXT_DAY_CANDIDATE_READY", "candidate_id": candidate_id, "target_broker_day": target_day, "candidate_hash": digest}


def settle_current_day(
    state: MutableMapping[str, Any], *, parent_run_id: str | None = None,
    symbols: Sequence[str] | None = None, path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Settle at broker 23:00+ without mutating the locked current publication."""
    migrate_daily_snapshot_database(path)
    snapshot = load_current_daily_snapshot(path=path)
    metadata = snapshot.get("metadata") or {}
    current = snapshot.get("current")
    if not metadata or not isinstance(current, pd.DataFrame) or current.empty:
        return {"ok": False, "status": "NO_LOCKED_SNAPSHOT"}
    main = normalize_symbol(metadata.get("main_symbol") or current.iloc[0]["Symbol"])
    main_state = _cached_state(main) or dict(state)
    canonical = _canonical_from_state(main_state)
    broker_now = _broker_now(main_state, canonical)
    if int(broker_now.hour) < DAY_END_REVIEW_HOUR:
        return {"ok": False, "status": "BEFORE_DAY_END_REVIEW", "broker_time": broker_now.isoformat()}
    latest_utc = pd.to_datetime(
        canonical.get("latest_completed_candle_time") or canonical.get("completed_broker_candle") or canonical.get("broker_candle_time"),
        errors="coerce", utc=True,
    )
    selected = {normalize_symbol(s) for s in (symbols or current["Symbol"].tolist())}
    settlements: list[dict[str, Any]] = []
    with _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for _, series in current.iterrows():
                row = series.to_dict()
                symbol = normalize_symbol(row.get("Symbol"))
                if symbol not in selected:
                    continue
                existing = conn.execute(
                    "SELECT settlement_status,outcome_hash FROM field10_daily_outcome WHERE daily_snapshot_id=? AND symbol=?",
                    (metadata["daily_snapshot_id"], symbol),
                ).fetchone()
                if existing and existing["settlement_status"] == "CURRENT_DAY_SETTLED":
                    settlements.append({"symbol": symbol, "status": "ALREADY_SETTLED", "outcome_hash": existing["outcome_hash"]})
                    continue
                symbol_state = _cached_state(symbol)
                symbol_canonical = _canonical_from_state(symbol_state)
                symbol_latest = pd.to_datetime(
                    symbol_canonical.get("latest_completed_candle_time") or symbol_canonical.get("completed_broker_candle") or latest_utc,
                    errors="coerce", utc=True,
                )
                result = _settle_symbol(row, symbol_state, symbol_latest)
                outcome_payload = {
                    "daily_snapshot_id": metadata["daily_snapshot_id"], "broker_day": metadata["broker_day"],
                    "symbol": symbol, "settled_at_broker_time": broker_now.isoformat(), "result": result,
                }
                digest = deterministic_hash(outcome_payload)
                conn.execute(
                    """INSERT INTO field10_daily_outcome(
                        daily_snapshot_id,broker_day,symbol,settlement_status,settled_at_broker_time,
                        actual_1h_direction,actual_3h_direction,actual_6h_direction,day_close_direction,
                        correct_1h,correct_3h,correct_6h,mfe,mae,spread_adjusted_outcome,
                        slippage_adjusted_outcome,calibration_error,outcome_hash,outcome_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(daily_snapshot_id,symbol) DO UPDATE SET
                        settlement_status=excluded.settlement_status,
                        settled_at_broker_time=excluded.settled_at_broker_time,
                        actual_1h_direction=excluded.actual_1h_direction,
                        actual_3h_direction=excluded.actual_3h_direction,
                        actual_6h_direction=excluded.actual_6h_direction,
                        day_close_direction=excluded.day_close_direction,
                        correct_1h=excluded.correct_1h,correct_3h=excluded.correct_3h,
                        correct_6h=excluded.correct_6h,mfe=excluded.mfe,mae=excluded.mae,
                        spread_adjusted_outcome=excluded.spread_adjusted_outcome,
                        slippage_adjusted_outcome=excluded.slippage_adjusted_outcome,
                        calibration_error=excluded.calibration_error,outcome_hash=excluded.outcome_hash,
                        outcome_json=excluded.outcome_json
                    WHERE field10_daily_outcome.settlement_status!='CURRENT_DAY_SETTLED'""",
                    (metadata["daily_snapshot_id"], metadata["broker_day"], symbol, result["settlement_status"],
                     broker_now.isoformat(), result.get("actual_1h_direction"), result.get("actual_3h_direction"),
                     result.get("actual_6h_direction"), result.get("day_close_direction"), result.get("correct_1h"),
                     result.get("correct_3h"), result.get("correct_6h"), result.get("mfe"), result.get("mae"),
                     result.get("spread_adjusted_outcome"), result.get("slippage_adjusted_outcome"),
                     result.get("calibration_error"), digest, _canonical_json(outcome_payload)),
                )
                settlements.append({"symbol": symbol, "status": result["settlement_status"], "outcome_hash": digest})
                # Settlement evidence enters calibration/validation only here.
                registry_payload = {"symbol": symbol, "broker_day": metadata["broker_day"], "result": result}
                registry_hash = deterministic_hash(registry_payload)
                conn.execute(
                    """INSERT OR IGNORE INTO field10_model_validation_registry(
                        registry_id,broker_day,symbol,method_name,model_version,formula_version,
                        threshold_version,sample_count,validation_status,promotion_status,p_value,
                        pbo_estimate,result_hash,result_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"SET-{registry_hash[:24]}", metadata["broker_day"], symbol, "SETTLED_OUTCOME",
                     metadata["model_version"], metadata["formula_version"], metadata["threshold_version"],
                     int(result.get("observed_rows") or 0), result["settlement_status"], "HISTORY_ONLY",
                     None, None, registry_hash, _canonical_json(registry_payload)),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    candidate = prepare_next_day_candidate(
        metadata=metadata, current_rows=current, prepared_at_broker_time=broker_now,
        parent_run_id=parent_run_id, path=path,
    )
    all_settled = bool(settlements) and all(item["status"] in {"CURRENT_DAY_SETTLED", "ALREADY_SETTLED"} for item in settlements)
    report = {
        "ok": True, "status": "CURRENT_DAY_SETTLED" if all_settled else "PARTIAL_SETTLEMENT",
        "broker_time": broker_now.isoformat(), "daily_snapshot_id": metadata["daily_snapshot_id"],
        "settlements": settlements, "next_day_candidate": candidate,
        "locked_publication_mutated": False, "version": VERSION,
    }
    state["field10_daily_outcome_settlement_20260702"] = report
    return report


def load_outcomes(*, broker_day: str | None = None, path: Path | str = DB_PATH) -> pd.DataFrame:
    with connect_readonly(path) as conn:
        clauses = ""
        params: tuple[Any, ...] = ()
        if broker_day:
            clauses = "WHERE broker_day=?"
            params = (broker_day,)
        return pd.read_sql_query(
            f"""SELECT broker_day AS [Broker Day],symbol AS Symbol,settlement_status AS Status,
                       settled_at_broker_time AS [Settled At Broker Time],actual_1h_direction AS [Actual 1H],
                       actual_3h_direction AS [Actual 3H],actual_6h_direction AS [Actual 6H],
                       day_close_direction AS [Day Close],correct_1h AS [Correct 1H],
                       correct_3h AS [Correct 3H],correct_6h AS [Correct 6H],MFE,MAE,
                       spread_adjusted_outcome AS [Spread Adjusted],slippage_adjusted_outcome AS [Slippage Adjusted],
                       calibration_error AS [Calibration Error],outcome_hash AS [Outcome Hash]
                FROM field10_daily_outcome {clauses} ORDER BY broker_day DESC,symbol""",
            conn, params=params,
        )


__all__ = [
    "VERSION", "settle_current_day", "prepare_next_day_candidate", "load_outcomes",
]
