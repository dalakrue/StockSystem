"""One-way adapter from the protected Full Metric result to canonical runtime.

This module intentionally contains no Full Metric formulas. It only reads the
completed output produced by :mod:`tabs.eurusd_h1_matrix` and exposes that
output to the existing canonical runtime. Research, NLP, KNN, Greedy, regime,
M1 and PowerBI values are confirmations; they cannot replace the protected
EURUSD H1 direction.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, Mapping, Optional

import numpy as np
import pandas as pd


_ALLOWED_FULL_METRIC_DECISIONS = {"STRONG", "ALLOWED"}
_WATCH_FULL_METRIC_DECISIONS = {"WAIT PULLBACK", "HOLD / PROTECT"}


def _num(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        out = float(value)
        return out if np.isfinite(out) else default
    except Exception:
        return default


def _direction(value: Any) -> str:
    text = str(value or "").upper()
    if "BUY" in text or "BULL" in text or text == "UP":
        return "BUY"
    if "SELL" in text or "BEAR" in text or text == "DOWN":
        return "SELL"
    return "WAIT"


def _json_scalar(value: Any) -> Any:
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _json_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(k): _json_scalar(v) for k, v in row.items()}


def _records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, pd.DataFrame):
        return [_json_record(row) for row in value.to_dict("records")]
    if isinstance(value, list):
        return [_json_record(x) for x in value if isinstance(x, Mapping)]
    return []


def _series_or_default(frame: pd.DataFrame, name: str, default: Any) -> pd.Series:
    if name in frame.columns:
        return frame[name]
    return pd.Series(default, index=frame.index)


def _history_frame(metric_result: Mapping[str, Any]) -> pd.DataFrame:
    value = metric_result.get("history")
    if not isinstance(value, pd.DataFrame) or value.empty:
        return pd.DataFrame()
    out = value.copy(deep=False)
    if "Time" in out.columns:
        out["_canonical_time"] = pd.to_datetime(out["Time"], utc=True, errors="coerce")
    elif "time" in out.columns:
        out["_canonical_time"] = pd.to_datetime(out["time"], utc=True, errors="coerce")
    elif "Date" in out.columns and "Hour" in out.columns:
        out["_canonical_time"] = pd.to_datetime(
            out["Date"].astype(str) + " " + out["Hour"].astype(str), utc=True, errors="coerce"
        )
    else:
        out["_canonical_time"] = pd.NaT
    now = pd.Timestamp.now(tz="UTC")
    out = out.loc[out["_canonical_time"].notna() & out["_canonical_time"].le(now + pd.Timedelta(minutes=5))].copy(deep=False)
    out = out.sort_values("_canonical_time", ascending=False, na_position="last", kind="stable").reset_index(drop=True)
    if "row_id" not in out.columns:
        def _row_identity(row: pd.Series) -> str:
            raw = "|".join([
                str(row.get("_canonical_time")), str(row.get("Direction", "")),
                str(row.get("Decision", "")), str(row.get("Master /10", "")),
                str(row.get("Entry /10", "")), str(row.get("Exit Risk /10", "")),
            ])
            return "FM-" + hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:20]
        out["row_id"] = out.apply(_row_identity, axis=1)
    return out


def _confirmation_frame(value: Any) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame) or value.empty:
        return pd.DataFrame()
    out = value.copy(deep=False)
    time_col = next(
        (
            c
            for c in (
                "Time",
                "time",
                "candle time",
                "latest_completed_candle_time",
                "DateTime",
                "Candidate Time",
            )
            if c in out.columns
        ),
        None,
    )
    if time_col is not None:
        out["_confirmation_time"] = pd.to_datetime(out[time_col], utc=True, errors="coerce")
    elif "Date" in out.columns and "Hour" in out.columns:
        out["_confirmation_time"] = pd.to_datetime(
            out["Date"].astype(str) + " " + out["Hour"].astype(str), utc=True, errors="coerce"
        )
    else:
        return pd.DataFrame()
    return out.dropna(subset=["_confirmation_time"]).sort_values("_confirmation_time").reset_index(drop=True)


def _first_numeric(row: Mapping[str, Any], names: tuple[str, ...], default: Optional[float] = None) -> Optional[float]:
    for name in names:
        if name not in row:
            continue
        value = _num(row.get(name), None)
        if value is None:
            continue
        # Existing score/reliability fields are mixed between /10 and /100.
        return value * 10.0 if value <= 10.0 and any(x in name.lower() for x in ("score", "reliability")) else value
    return default


def _first_text(row: Mapping[str, Any], names: tuple[str, ...], default: str = "") -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value)
    return default


def _build_priority_table(
    history: pd.DataFrame,
    *,
    latest_completed_h1_time: Optional[pd.Timestamp],
    confirmation_table: Any = None,
    data_quality_status: str = "UNKNOWN",
    default_reliability: Optional[float] = None,
) -> pd.DataFrame:
    """Rank existing Full Metric rows; never calculate another direction."""
    if history.empty:
        return pd.DataFrame()
    h = history.copy(deep=False)
    numeric = {
        "Master /10": 0.0,
        "Entry /10": 0.0,
        "BUY /10": 0.0,
        "SELL /10": 0.0,
        "Hold /10": 0.0,
        "TP /10": 0.0,
        "Exit Risk /10": 10.0,
    }
    for col, default in numeric.items():
        h[col] = pd.to_numeric(_series_or_default(h, col, default), errors="coerce").fillna(default).clip(0, 10)
    h["Direction"] = _series_or_default(h, "Direction", "WAIT").astype(str).map(_direction)
    h["Full Metric Decision"] = _series_or_default(h, "Decision", "NO TRADE").astype(str).str.upper()
    h["Base Full Metric Score"] = (
        h["Master /10"] * 10 * 0.30
        + h["Entry /10"] * 10 * 0.25
        + h[["BUY /10", "SELL /10"]].max(axis=1) * 10 * 0.15
        + h["Hold /10"] * 10 * 0.10
        + h["TP /10"] * 10 * 0.10
        + (10 - h["Exit Risk /10"]) * 10 * 0.10
    )

    h["KNN Score"] = np.nan
    h["Greedy Score"] = np.nan
    h["Reliability %"] = _num(default_reliability, np.nan)
    h["Expected Value"] = np.nan
    h["NLP Confirmation"] = "UNAVAILABLE"
    h["Research Confirmation"] = "UNAVAILABLE"
    h["Conflict Status"] = "NONE"

    confirm = _confirmation_frame(confirmation_table)
    if not confirm.empty and h["_canonical_time"].notna().any():
        left = h.sort_values("_canonical_time").copy()
        left["_left_index"] = left.index
        merged = pd.merge_asof(
            left,
            confirm,
            left_on="_canonical_time",
            right_on="_confirmation_time",
            direction="backward",
            tolerance=pd.Timedelta(hours=1),
            suffixes=("", "__confirm"),
        )
        for _, row in merged.iterrows():
            idx = int(row["_left_index"])
            row_map = row.to_dict()
            h.loc[idx, "KNN Score"] = _first_numeric(
                row_map, ("KNN Score /10", "KNN Score", "KNN Priority Score", "KNN score")
            )
            h.loc[idx, "Greedy Score"] = _first_numeric(
                row_map, ("Greedy Score /10", "Greedy Score", "Greedy score")
            )
            h.loc[idx, "Reliability %"] = _first_numeric(
                row_map, ("Reliability %", "Reliability", "regime reliability"), _num(default_reliability, None)
            )
            h.loc[idx, "Expected Value"] = _first_numeric(
                row_map, ("Expected Value", "expected_value", "Net Expected Value", "EV")
            )
            h.loc[idx, "NLP Confirmation"] = _first_text(
                row_map, ("NLP Sync", "NLP Confirmation", "nlp confirmation"), "UNAVAILABLE"
            ).upper()
            h.loc[idx, "Research Confirmation"] = _first_text(
                row_map, ("Research Confirmation", "RF Sync", "research confirmation"), "UNAVAILABLE"
            ).upper()
            h.loc[idx, "Conflict Status"] = _first_text(
                row_map, ("Conflict Status", "conflict status"), "NONE"
            ).upper()

    # Confirmations are deliberately capped. They can sort otherwise similar
    # Full Metric rows, but cannot replace or reverse Full Metric direction.
    knn = pd.to_numeric(h["KNN Score"], errors="coerce").fillna(50).clip(0, 100)
    greedy = pd.to_numeric(h["Greedy Score"], errors="coerce").fillna(50).clip(0, 100)
    reliability = pd.to_numeric(h["Reliability %"], errors="coerce").fillna(50).clip(0, 100)
    confirmation_adjustment = (
        (knn - 50) * 0.025 + (greedy - 50) * 0.025 + (reliability - 50) * 0.015
    ).clip(-5, 5)
    conflict_penalty = np.where(
        h["Conflict Status"].str.contains("CRITICAL|SEVERE|CONFLICT", regex=True, na=False), 4.0, 0.0
    )
    nlp_penalty = np.where(h["NLP Confirmation"].str.contains("CONFLICT", na=False), 2.0, 0.0)
    h["Priority Score"] = (
        h["Base Full Metric Score"] + confirmation_adjustment - conflict_penalty - nlp_penalty
    ).clip(0, 100).round(2)

    quality_block = str(data_quality_status or "UNKNOWN").upper().startswith("FAIL")
    reliability_ok = pd.to_numeric(h["Reliability %"], errors="coerce").ge(45)
    expected_value_ok = pd.to_numeric(h["Expected Value"], errors="coerce").gt(0)
    qualified = (
        h["Direction"].isin(["BUY", "SELL"])
        & h["Full Metric Decision"].isin(_ALLOWED_FULL_METRIC_DECISIONS)
        & reliability_ok
        & expected_value_ok
        & ~h["Conflict Status"].str.contains("CRITICAL|SEVERE", regex=True, na=False)
        & ~h["NLP Confirmation"].str.contains("CRITICAL", regex=True, na=False)
        & (not quality_block)
    )
    watch = h["Direction"].isin(["BUY", "SELL"]) & h["Full Metric Decision"].isin(
        _ALLOWED_FULL_METRIC_DECISIONS | _WATCH_FULL_METRIC_DECISIONS
    )
    h["Qualification Status"] = np.select(
        [qualified, watch], ["QUALIFIED ENTRY", "WATCH CANDIDATE"], default="NO ENTRY / WAIT"
    )

    def reason(row: pd.Series) -> str:
        reasons: list[str] = []
        if row["Direction"] == "WAIT":
            reasons.append("Full Metric direction is WAIT")
        if row["Full Metric Decision"] not in _ALLOWED_FULL_METRIC_DECISIONS:
            reasons.append(f"Full Metric decision is {row['Full Metric Decision']}")
        if quality_block:
            reasons.append(f"Data quality is {data_quality_status}")
        rel = _num(row.get("Reliability %"), None)
        if rel is None:
            reasons.append("Reliability confirmation unavailable")
        elif rel < 45:
            reasons.append("Reliability below existing safe range")
        ev = _num(row.get("Expected Value"), None)
        if ev is None:
            reasons.append("Expected value confirmation unavailable")
        elif ev <= 0:
            reasons.append("Expected value is not positive after cost")
        if "CONFLICT" in str(row["NLP Confirmation"]):
            reasons.append("NLP conflict")
        if any(token in str(row["Conflict Status"]) for token in ("CRITICAL", "SEVERE")):
            reasons.append(str(row["Conflict Status"]))
        return "; ".join(dict.fromkeys(reasons)) or "Passed protected Full Metric safety gate"

    h["Blocking Reason"] = h.apply(reason, axis=1)
    h["Less Risky Bias"] = np.where(h["Qualification Status"] == "QUALIFIED ENTRY", h["Direction"], "WAIT")
    h["Time"] = h["_canonical_time"]
    h["Hour"] = h["_canonical_time"].dt.strftime("%H:00")
    latest_date = (
        latest_completed_h1_time.date()
        if latest_completed_h1_time is not None and not pd.isna(latest_completed_h1_time)
        else None
    )
    h["Current Day"] = h["_canonical_time"].dt.date.eq(latest_date) if latest_date else False
    status_order = {"QUALIFIED ENTRY": 0, "WATCH CANDIDATE": 1, "NO ENTRY / WAIT": 2, "NO ENTRY": 2}
    h["_status_order"] = h["Qualification Status"].map(status_order).fillna(3)
    h["_conflict_order"] = h["Conflict Status"].astype(str).str.upper().map(
        lambda text: 3 if "CRITICAL" in text else 2 if "SEVERE" in text else 1 if "CONFLICT" in text else 0
    )
    h["_ev_order"] = pd.to_numeric(h["Expected Value"], errors="coerce").fillna(-np.inf)
    h["_reliability_order"] = pd.to_numeric(h["Reliability %"], errors="coerce").fillna(0)
    h = h.sort_values(
        ["_status_order", "Priority Score", "_ev_order", "_reliability_order",
         "_conflict_order", "Exit Risk /10", "Current Day", "_canonical_time"],
        ascending=[True, False, False, False, True, True, False, False],
        na_position="last", kind="stable",
    ).reset_index(drop=True)
    h["Priority Rank"] = np.arange(1, len(h) + 1)
    # Preserve legacy column aliases consumed by existing tabs.
    h["priority rank"] = h["Priority Rank"]
    h["combined score"] = h["Priority Score"]
    h["prediction direction"] = h["Direction"]
    h["less-risky bias"] = h["Less Risky Bias"]
    h["conflict status"] = h["Conflict Status"]
    return h.drop(columns=["_status_order", "_conflict_order", "_ev_order", "_reliability_order"], errors="ignore")


def _top_two_daily_candidates(priority: pd.DataFrame) -> list[dict[str, Any]]:
    """Return two evaluated daily opportunity slots without forcing a trade."""
    slot_columns = {
        "Opportunity": None, "Qualification Status": "NO ENTRY / WAIT",
        "Less Risky Bias": "WAIT", "Blocking Reason": "No completed H1 candidate available",
        "row_id": None, "Time": None, "Direction": "WAIT",
    }
    if not isinstance(priority, pd.DataFrame) or priority.empty:
        return [{**slot_columns, "Opportunity": 1}, {**slot_columns, "Opportunity": 2}]
    current_day = _series_or_default(priority, "Current Day", False).fillna(False).astype(bool)
    pool = priority.loc[current_day].copy()
    if pool.empty:
        all_times = pd.to_datetime(_series_or_default(priority, "Time", pd.NaT), utc=True, errors="coerce")
        newest = all_times.max()
        pool = priority.loc[all_times.dt.date.eq(newest.date())].copy() if pd.notna(newest) else priority.head(24).copy()
    selected: list[pd.Series] = []
    for _, row in pool.iterrows():
        if not selected:
            selected.append(row)
        else:
            first = selected[0]
            t1 = pd.to_datetime(first.get("Time"), utc=True, errors="coerce")
            t2 = pd.to_datetime(row.get("Time"), utc=True, errors="coerce")
            separated = bool(pd.notna(t1) and pd.notna(t2) and abs((t1 - t2).total_seconds()) >= 7200)
            meaningfully_different = (
                row.get("Direction") != first.get("Direction")
                or abs(float(row.get("Entry /10", 0) or 0) - float(first.get("Entry /10", 0) or 0)) >= 0.7
                or abs(float(row.get("Exit Risk /10", 10) or 10) - float(first.get("Exit Risk /10", 10) or 10)) >= 0.7
                or abs(float(row.get("Master /10", 0) or 0) - float(first.get("Master /10", 0) or 0)) >= 0.7
                or str(row.get("Full Metric Decision")) != str(first.get("Full Metric Decision"))
            )
            if separated or meaningfully_different:
                selected.append(row)
        if len(selected) == 2:
            break
    records: list[dict[str, Any]] = []
    for index, series in enumerate(selected[:2], start=1):
        record = _json_record(series.where(pd.notna(series), None).to_dict())
        record["Opportunity"] = index
        status = str(record.get("Qualification Status") or "NO ENTRY / WAIT").upper()
        if status == "NO ENTRY":
            record["Qualification Status"] = "NO ENTRY / WAIT"
        records.append(record)
    while len(records) < 2:
        number = len(records) + 1
        records.append({
            **slot_columns,
            "Opportunity": number,
            "Blocking Reason": "No materially distinct second completed H1 candidate; no trade was forced",
        })
    return records


def build_full_metric_authority(
    metric_result: Mapping[str, Any],
    h1: pd.DataFrame,
    *,
    symbol: str = "EURUSD",
    timeframe: str = "H1",
    legacy_shared: Optional[Mapping[str, Any]] = None,
    confirmation_table: Any = None,
    data_quality_status: str = "UNKNOWN",
) -> Dict[str, Any]:
    """Return a canonical-ready view without recalculating Full Metric values."""
    if not isinstance(metric_result, Mapping) or not metric_result.get("ok"):
        raise ValueError("Protected Full Metric result is not ready")
    if str(symbol).upper() != "EURUSD" or str(timeframe).upper() != "H1":
        raise ValueError("Operational canonical authority requires EURUSD H1")

    frame = h1 if isinstance(h1, pd.DataFrame) else pd.DataFrame()
    time_col = next((c for c in ("time", "Time", "datetime", "timestamp") if c in frame.columns), None)
    latest_time = (
        pd.to_datetime(frame[time_col].iloc[-1], utc=True, errors="coerce")
        if time_col and not frame.empty
        else pd.NaT
    )
    history = _history_frame(metric_result)
    scores = dict(metric_result.get("scores") or {})
    metrics = dict(metric_result.get("metrics") or {})
    current_history = (
        _json_record(history.iloc[0].drop(labels=["_canonical_time"], errors="ignore").to_dict())
        if not history.empty
        else {}
    )
    direction = _direction(scores.get("Direction"))
    metric_decision = str(scores.get("Decision") or "NO TRADE").upper()
    tradeability = direction if direction in {"BUY", "SELL"} and metric_decision in _ALLOWED_FULL_METRIC_DECISIONS else "WAIT"
    blockers = (
        []
        if tradeability in {"BUY", "SELL"}
        else ["Full Metric direction is WAIT" if direction == "WAIT" else f"Full Metric decision is {metric_decision}"]
    )

    shared = dict(legacy_shared or {})
    regime = dict(shared.get("regime") or {})
    reliability = dict(shared.get("reliability") or shared.get("reliability_calibration") or {})
    nlp = dict(shared.get("nlp") or {})
    data_mining = dict(shared.get("data_mining") or {})
    powerbi = dict(shared.get("powerbi") or {})
    reliability_score = _num(reliability.get("score"), None)
    if reliability_score is not None and reliability_score <= 1:
        reliability_score *= 100.0
    priority = _build_priority_table(
        history,
        latest_completed_h1_time=latest_time if pd.notna(latest_time) else None,
        confirmation_table=confirmation_table,
        data_quality_status=data_quality_status,
        default_reliability=reliability_score,
    )
    top_two = _top_two_daily_candidates(priority)

    reverse_history_raw = metric_result.get("history_by_factor") or {}
    reverse_history = (
        {str(name): _records(table) for name, table in reverse_history_raw.items()}
        if isinstance(reverse_history_raw, Mapping)
        else {}
    )

    snapshot = {
        "symbol": "EURUSD",
        "timeframe": "H1",
        "latest_completed_h1_time": latest_time.isoformat() if pd.notna(latest_time) else None,
        "last_close": _num(metrics.get("close"), _num(current_history.get("Close"))),
        "current_major_regime": regime.get("current") or regime.get("major_regime") or "UNKNOWN",
        "regime_start_time": regime.get("regime_start_time") or regime.get("start_time"),
        "regime_age": regime.get("age_hours") or regime.get("regime_age"),
        "regime_reliability": reliability_score if reliability_score is not None else regime.get("reliability"),
        "master_score": _num(scores.get("Master /10"), 0.0),
        "entry_score": _num(scores.get("Entry /10"), 0.0),
        "buy_score": _num(scores.get("BUY Score"), 0.0),
        "sell_score": _num(scores.get("SELL Score"), 0.0),
        "hold_safety": _num(scores.get("Hold /10"), 0.0),
        "tp_quality": _num(scores.get("TP /10"), 0.0),
        "exit_risk": _num(scores.get("Exit Risk /10"), 10.0),
        "pullback_readiness": (_num(metrics.get("pullback_readiness"), 0.0) or 0.0) / 10.0,
        "trend_capacity_remaining": (100.0 - (_num(metrics.get("trend_capacity_used"), 100.0) or 100.0)) / 10.0,
        "m1_confirmation": (_num(metrics.get("m1_confirm"), 0.0) or 0.0) / 10.0,
        "m1_timing_status": "CONFIRM" if (_num(metrics.get("m1_confirm"), 0.0) or 0.0) >= 50 else "WAIT FOR CONFIRMATION",
        "full_metric_direction": direction,
        "full_metric_decision_label": metric_decision,
        "tradeability_decision": tradeability,
        "blocking_reasons": blockers,
        "uncertainty": None,
        "error_estimate": None,
        "prediction_reliability": reliability_score,
        "full_metric_current_row": {**current_history, **{k: _json_scalar(v) for k, v in scores.items()}},
        "full_metric_history": _records(history.drop(columns=["_canonical_time"], errors="ignore")),
        "reverse_10_current": _records(metric_result.get("reverse10")),
        "reverse_10_history": reverse_history,
        "canonical_priority_table": _records(priority.drop(columns=["_canonical_time"], errors="ignore")),
        "top_two_daily_candidates": top_two,
        "research_confirmation": data_mining,
        "nlp_confirmation": nlp,
        "knn_confirmation": {
            "source": "existing KNN columns",
            "available": bool(priority["KNN Score"].notna().any()) if not priority.empty else False,
        },
        "greedy_confirmation": {
            "source": "existing Greedy columns",
            "available": bool(priority["Greedy Score"].notna().any()) if not priority.empty else False,
        },
        "powerbi_confirmation": powerbi,
    }
    return {"snapshot": snapshot, "priority_table": priority, "top_two_daily_candidates": top_two}


def _stamp_records(records: list[dict[str, Any]], identity: Mapping[str, Any]) -> list[dict[str, Any]]:
    stamped: list[dict[str, Any]] = []
    for row in records:
        item = _json_record(row)
        item.update(identity)
        stamped.append(item)
    return stamped



def apply_canonical_confirmations(
    authority: Mapping[str, Any], canonical_payload: Mapping[str, Any]
) -> Dict[str, Any]:
    """Apply validated downstream gates to the current Full Metric candidate.

    The rank base and direction remain unchanged.  This second pass exists
    because expected value, calibrated reliability, drift and NLP conflict are
    available only after the existing decision-product confirmation engine has
    completed. Historical rows without causal confirmation remain WATCH rather
    than being upgraded with today's information.
    """
    result = dict(authority or {})
    table = result.get("priority_table")
    if not isinstance(table, pd.DataFrame) or table.empty:
        return result
    out = table.copy(deep=False)
    latest = pd.to_datetime(
        canonical_payload.get("latest_completed_candle_time"), utc=True, errors="coerce"
    )
    times = pd.to_datetime(_series_or_default(out, "Time", pd.NaT), utc=True, errors="coerce")
    current_mask = times.eq(latest) if pd.notna(latest) else pd.Series(False, index=out.index)
    final = canonical_payload.get("final_decision") or {}
    reliability = canonical_payload.get("reliability") or {}
    nlp = canonical_payload.get("nlp") or {}
    quality = canonical_payload.get("data_quality") or {}
    reliability_score = _num(reliability.get("score"), None)
    expected_value = _num(final.get("expected_value"), None)
    final_direction = _direction(final.get("directional_market_view"))
    final_tradeability = _direction(final.get("tradeability_decision") or final.get("final_decision"))
    conflict = str(nlp.get("conflict_level") or "NONE").upper()
    quality_status = str(quality.get("status") or "UNKNOWN").upper()

    if current_mask.any():
        if reliability_score is not None:
            out.loc[current_mask, "Reliability %"] = reliability_score
        if expected_value is not None:
            out.loc[current_mask, "Expected Value"] = expected_value
        out.loc[current_mask, "NLP Confirmation"] = conflict
        out.loc[current_mask, "Conflict Status"] = conflict
        row_direction = out.loc[current_mask, "Direction"].astype(str).str.upper()
        metric_allowed = out.loc[current_mask, "Full Metric Decision"].isin(_ALLOWED_FULL_METRIC_DECISIONS)
        qualified = (
            row_direction.isin(["BUY", "SELL"])
            & metric_allowed
            & row_direction.eq(final_direction)
            & row_direction.eq(final_tradeability)
            & (reliability_score is not None and reliability_score >= 45)
            & (expected_value is not None and expected_value > 0)
            & (not quality_status.startswith("FAIL"))
            & (conflict not in {"CRITICAL", "SEVERE"})
        )
        if bool(qualified.any()):
            out.loc[current_mask, "Qualification Status"] = "QUALIFIED ENTRY"
            out.loc[current_mask, "Less Risky Bias"] = row_direction
            out.loc[current_mask, "Blocking Reason"] = "Passed Full Metric and validated confirmation safety gates"
        else:
            blockers = list(final.get("blocking_reasons") or [])
            if expected_value is None:
                blockers.append("Expected value confirmation unavailable")
            elif expected_value <= 0:
                blockers.append("Expected value is not positive after cost")
            if reliability_score is None:
                blockers.append("Reliability confirmation unavailable")
            elif reliability_score < 45:
                blockers.append("Reliability below existing safe range")
            if final_tradeability == "WAIT" and final_direction in {"BUY", "SELL"}:
                blockers.append("Directional setup is currently blocked; tradeability is WAIT")
            if quality_status.startswith("FAIL"):
                blockers.append(f"Data quality is {quality_status}")
            if conflict in {"CRITICAL", "SEVERE"}:
                blockers.append(f"NLP conflict is {conflict}")
            out.loc[current_mask, "Qualification Status"] = np.where(
                row_direction.isin(["BUY", "SELL"]), "WATCH CANDIDATE", "NO ENTRY / WAIT"
            )
            out.loc[current_mask, "Less Risky Bias"] = "WAIT"
            out.loc[current_mask, "Blocking Reason"] = "; ".join(dict.fromkeys(blockers)) or "Confirmation gate not passed"

    status_order = {"QUALIFIED ENTRY": 0, "WATCH CANDIDATE": 1, "NO ENTRY / WAIT": 2, "NO ENTRY": 2}
    out["_status_order"] = out["Qualification Status"].map(status_order).fillna(3)
    out["_conflict_order"] = out["Conflict Status"].astype(str).str.upper().map(
        lambda text: 3 if "CRITICAL" in text else 2 if "SEVERE" in text else 1 if "CONFLICT" in text else 0
    )
    out["_ev_order"] = pd.to_numeric(out["Expected Value"], errors="coerce").fillna(-np.inf)
    out["_reliability_order"] = pd.to_numeric(out["Reliability %"], errors="coerce").fillna(0)
    out = out.sort_values(
        ["_status_order", "Priority Score", "_ev_order", "_reliability_order",
         "_conflict_order", "Exit Risk /10", "Current Day", "Time"],
        ascending=[True, False, False, False, True, True, False, False],
        na_position="last", kind="stable",
    ).drop(columns=["_status_order", "_conflict_order", "_ev_order", "_reliability_order"], errors="ignore").reset_index(drop=True)
    out["Priority Rank"] = np.arange(1, len(out) + 1)
    out["priority rank"] = out["Priority Rank"]
    top_two = _top_two_daily_candidates(out)
    result["priority_table"] = out
    result["top_two_daily_candidates"] = top_two
    snapshot = dict(result.get("snapshot") or {})
    snapshot["canonical_priority_table"] = _records(out.drop(columns=["_canonical_time"], errors="ignore"))
    snapshot["top_two_daily_candidates"] = top_two
    result["snapshot"] = snapshot
    return result

def enrich_canonical_payload(payload: Dict[str, Any], authority: Mapping[str, Any]) -> Dict[str, Any]:
    """Attach protected Full Metric fields and one canonical identity."""
    snapshot = dict(authority.get("snapshot") or {})
    identity = {
        "run_id": payload.get("run_id"),
        "calculation_generation": payload.get("calculation_generation"),
        "data_signature": payload.get("data_signature"),
        "latest_completed_h1_time": payload.get("latest_completed_candle_time"),
        "latest_completed_candle_time": payload.get("latest_completed_candle_time"),
        "symbol": payload.get("symbol"),
        "timeframe": payload.get("timeframe"),
        "source": payload.get("source"),
    }
    snapshot.update(identity)
    snapshot["calculated_at"] = payload.get("created_at")
    final = dict(payload.get("final_decision") or {})
    snapshot["tradeability_decision"] = final.get(
        "tradeability_decision", snapshot.get("tradeability_decision", "WAIT")
    )
    snapshot["blocking_reasons"] = final.get("blocking_reasons", snapshot.get("blocking_reasons", []))
    snapshot["uncertainty"] = final.get("uncertainty_pct")
    snapshot["error_estimate"] = final.get("error_estimate_pct")
    snapshot["prediction_reliability"] = (payload.get("reliability") or {}).get("score")

    priority_records = _stamp_records(_records(authority.get("priority_table")), identity)
    top_two = _stamp_records(list(authority.get("top_two_daily_candidates") or []), identity)
    history_records = _stamp_records(list(snapshot.get("full_metric_history") or []), identity)
    reverse_current = _stamp_records(list(snapshot.get("reverse_10_current") or []), identity)
    reverse_history = {
        str(name): _stamp_records(list(rows or []), identity)
        for name, rows in dict(snapshot.get("reverse_10_history") or {}).items()
    }
    snapshot["full_metric_history"] = history_records
    snapshot["reverse_10_current"] = reverse_current
    snapshot["reverse_10_history"] = reverse_history
    snapshot["canonical_priority_table"] = priority_records
    snapshot["top_two_daily_candidates"] = top_two

    payload.update(snapshot)
    payload["full_metric_snapshot"] = snapshot
    payload["canonical_priority_table"] = priority_records
    payload["priority_table"] = priority_records
    payload["top_two_daily_candidates"] = top_two
    # Stable canonical aliases let every route consume the same generation.
    payload["current_regime"] = (payload.get("regime") or {}).get("major_regime") or snapshot.get("current_major_regime")
    payload["alpha"] = (payload.get("regime") or {}).get("alpha")
    payload["delta"] = (payload.get("regime") or {}).get("delta")
    payload["powerbi_projection_result"] = payload.get("forecasts") or payload.get("powerbi_confirmation") or {}
    payload["finder_priorities"] = priority_records
    payload["nlp_result"] = payload.get("nlp") or snapshot.get("nlp_confirmation") or {}
    payload["research_confirmation_result"] = payload.get("research_confirmation") or snapshot.get("research_confirmation") or {}
    payload["conflict_state"] = (payload.get("nlp") or {}).get("conflict_level", "NONE")
    payload["counter_trend_state"] = (payload.get("final_decision") or {}).get("counter_trend_state", "NONE")
    payload["data_quality_state"] = payload.get("data_quality") or {}
    payload["current_actionable_decision"] = (payload.get("final_decision") or {}).get("tradeability_decision", "WAIT")
    payload["opportunity_candidates"] = top_two
    payload["source_freshness_metadata"] = {**identity, "created_at": payload.get("created_at"), "expires_at": payload.get("expires_at")}
    payload.setdefault("metadata", {})["primary_calculation_authority"] = "Full Metric Detail + History"
    payload["metadata"]["confirmation_components_cannot_reverse_direction"] = True
    payload["metadata"]["m1_role"] = "entry timing and confirmation only"
    return payload
