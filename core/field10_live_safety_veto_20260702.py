"""Incremental live safety overlay for immutable Field 10 morning decisions.

The overlay can only return CLEAR, CAUTION, or BLOCK_NEW_ENTRIES. It never
changes the locked daily rank, BUY/SELL/WAIT bias, grade, or score.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any
import json
import sqlite3

import numpy as np
import pandas as pd

from core.sqlite_readonly_20260704 import connect_readonly

from core.field10_daily_snapshot_contract_20260702 import (
    DB_PATH, _canonical_from_state, _connect, _expected_trading_hours, _frame_from_state,
    _json_safe, _normalize_ohlc, _safe_float, _clip100, deterministic_hash,
    load_current_daily_snapshot, migrate_daily_snapshot_database,
)
from core.multi_symbol_field10_20260701 import (
    MANIFEST_KEY, _cache_path, _read_cache_payload, normalize_symbol,
)

VERSION = "field10-live-safety-veto-20260702-v2"
VALID_VALUES = {"CLEAR", "CAUTION", "BLOCK_NEW_ENTRIES"}
LIVE_STALE_CAUTION_HOURS = 1.5
LIVE_STALE_BLOCK_HOURS = 3.0


def evaluate_safety_veto(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Pure deterministic safety decision from current evidence."""
    block: list[str] = []
    caution: list[str] = []
    stale_hours = _safe_float(evidence.get("stale_hours"))
    if stale_hours is None or stale_hours > LIVE_STALE_BLOCK_HOURS:
        block.append("API/market data is stale")
    elif stale_hours > LIVE_STALE_CAUTION_HOURS:
        caution.append("API/market data freshness is degraded")
    missing = int(evidence.get("missing_candles") or 0)
    if missing > 0:
        block.append(f"missing completed H1 candles={missing}")
    spread_pct = _clip100(evidence.get("spread_percentile"))
    if spread_pct is not None and spread_pct >= 98:
        block.append("spread percentile is extreme")
    elif spread_pct is not None and spread_pct >= 90:
        caution.append("spread percentile is elevated")
    cp = _clip100(evidence.get("changepoint_probability"))
    if cp is not None and cp >= 75:
        block.append("BOCPD changepoint probability is severe")
    elif cp is not None and cp >= 55:
        caution.append("BOCPD changepoint probability is elevated")
    break_status = str(evidence.get("structural_break_status") or "").upper()
    if break_status in {"SEVERE", "BREAK_DETECTED_SEVERE", "RECALIBRATION_REQUIRED"}:
        block.append("severe structural break")
    elif "BREAK" in break_status and "NO_" not in break_status:
        caution.append("structural break warning")
    volatility_z = _safe_float(evidence.get("volatility_z"))
    if volatility_z is not None and abs(volatility_z) >= 4.0:
        block.append("extreme volatility")
    elif volatility_z is not None and abs(volatility_z) >= 2.5:
        caution.append("elevated volatility")
    interval_ratio = _safe_float(evidence.get("conformal_interval_ratio"))
    if interval_ratio is not None and interval_ratio >= 4.0:
        block.append("conformal interval explosion")
    elif interval_ratio is not None and interval_ratio >= 2.5:
        caution.append("conformal interval widened")
    if not bool(evidence.get("canonical_identity_valid", False)):
        block.append("canonical identity failure")
    if not bool(evidence.get("connector_ok", True)):
        block.append("connector failure")
    veto = "BLOCK_NEW_ENTRIES" if block else ("CAUTION" if caution else "CLEAR")
    return {
        "safety_veto": veto,
        "block_reasons": block,
        "caution_reasons": caution,
        "direction_unchanged": True,
        "version": VERSION,
    }


def record_safety_event(
    *, daily_snapshot_id: str | None, broker_day: str, symbol: str,
    observed_at_broker_time: Any, evidence: Mapping[str, Any],
    path: Path | str = DB_PATH,
) -> dict[str, Any]:
    migrate_daily_snapshot_database(path)
    result = evaluate_safety_veto(evidence)
    observed = pd.Timestamp(observed_at_broker_time).isoformat()
    payload = {
        "daily_snapshot_id": daily_snapshot_id, "broker_day": broker_day,
        "symbol": normalize_symbol(symbol), "observed_at": observed,
        "result": result, "evidence": _json_safe(evidence),
    }
    event_hash = deterministic_hash(payload)
    event_id = f"SAFE-{event_hash[:28]}"
    with _connect(path) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO field10_daily_safety_event(
                event_id,daily_snapshot_id,broker_day,symbol,observed_at_broker_time,
                safety_veto,reasons_json,evidence_json,event_hash
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (event_id, daily_snapshot_id, broker_day, normalize_symbol(symbol), observed,
             result["safety_veto"], json.dumps({"block": result["block_reasons"], "caution": result["caution_reasons"]}, sort_keys=True),
             json.dumps(_json_safe(evidence), sort_keys=True), event_hash),
        )
        conn.commit()
    return {"ok": True, "event_id": event_id, **result}


def _cached_state(symbol: str) -> dict[str, Any]:
    try:
        payload = _read_cache_payload(_cache_path(symbol))
        state = payload.get("state")
        return dict(state) if isinstance(state, Mapping) else {}
    except Exception:
        return {}


def _volatility_z(frame: pd.DataFrame) -> float | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    close_col = next((c for c in frame.columns if str(c).strip().lower() in {"close", "c"}), None)
    if close_col is None:
        return None
    returns = pd.to_numeric(frame[close_col], errors="coerce").pct_change().dropna()
    if len(returns) < 50:
        return None
    recent = float(returns.tail(6).std(ddof=1))
    rolling = returns.rolling(24).std().dropna().tail(120)
    if len(rolling) < 20 or float(rolling.std(ddof=1)) <= 0:
        return None
    return (recent - float(rolling.mean())) / float(rolling.std(ddof=1))


def _latest_live_evidence(parent_run_id: str, symbol: str, path: Path | str) -> dict[str, Any]:
    if not parent_run_id:
        return {}
    with _connect(path) as conn:
        try:
            row = conn.execute(
                """SELECT change_probability,structural_break_status,interval_width,spread_quality,
                          drift_status,broker_timestamp,publication_status
                   FROM field10_integrated_evidence
                   WHERE parent_run_id=? AND symbol=?
                   ORDER BY broker_timestamp DESC,created_at DESC LIMIT 1""",
                (str(parent_run_id), normalize_symbol(symbol)),
            ).fetchone()
        except sqlite3.Error:
            row = None
    return {} if row is None else dict(row)


def _recent_missing_candles(frame: pd.DataFrame, symbol: str) -> int:
    normalized = _normalize_ohlc(frame).dropna(subset=["time", "open", "high", "low", "close"])
    normalized = normalized.sort_values("time", kind="mergesort").drop_duplicates("time", keep=False).tail(72)
    if len(normalized) < 2:
        return 1
    expected = _expected_trading_hours(
        pd.Timestamp(normalized["time"].iloc[0]), pd.Timestamp(normalized["time"].iloc[-1]), symbol,
    )
    return int(len(expected.difference(pd.DatetimeIndex(normalized["time"]))))


def _interval_explosion_ratio(interval_width: Any, frame: pd.DataFrame) -> float | None:
    width = _safe_float(interval_width)
    if width is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    normalized = _normalize_ohlc(frame)
    returns = pd.to_numeric(normalized.get("close"), errors="coerce").pct_change().dropna().tail(120)
    if len(returns) < 30:
        return None
    scale = float(returns.std(ddof=1))
    if not np.isfinite(scale) or scale <= 0:
        return None
    return abs(float(width)) / scale


def update_live_safety_veto(
    state: MutableMapping[str, Any], *, symbols: Sequence[str] | None = None,
    path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Update safety events during a calculation run; never called by UI."""
    snapshot = load_current_daily_snapshot(path=path)
    metadata = snapshot.get("metadata") or {}
    current = snapshot.get("current")
    if not metadata or not isinstance(current, pd.DataFrame) or current.empty:
        return {"ok": False, "status": "NO_LOCKED_SNAPSHOT", "events": []}
    chosen = [normalize_symbol(s) for s in (symbols or current["Symbol"].tolist())]
    manifest = state.get(MANIFEST_KEY) if isinstance(state.get(MANIFEST_KEY), Mapping) else {}
    live_parent_run_id = str(manifest.get("parent_run_id") or "")
    events: list[dict[str, Any]] = []
    for symbol in chosen:
        row_frame = current.loc[current["Symbol"].astype(str).eq(symbol)]
        if row_frame.empty:
            continue
        row = row_frame.iloc[0]
        cached = _cached_state(symbol)
        canonical = _canonical_from_state(cached)
        frame = _frame_from_state(cached)
        try:
            from core.shared_broker_time_20260622 import shared_broker_time_provider
            clock = dict(shared_broker_time_provider(cached or state, canonical=canonical))
            observed = pd.Timestamp(clock.get("broker_time"))
            freshness_minutes = _safe_float(clock.get("freshness_lag_minutes"))
            stale_hours = None if freshness_minutes is None else max(0.0, freshness_minutes / 60.0)
        except Exception:
            observed = pd.Timestamp(metadata["locked_until_broker_time"]) - pd.Timedelta(days=1)
            stale_hours = None
        connector = cached.get("multi_symbol_api_router_20260702")
        connector_ok = True if not isinstance(connector, Mapping) else bool(connector.get("ok", True))
        live = _latest_live_evidence(live_parent_run_id, symbol, path)
        spread_quality = str(live.get("spread_quality") or "").upper()
        spread_percentile = row.get("Spread Percentile")
        if spread_quality in {"VERY HIGH", "EXTREME"}:
            spread_percentile = 99.0
        elif spread_quality == "HIGH" and (spread_percentile is None or pd.isna(spread_percentile)):
            spread_percentile = 92.0
        evidence = {
            "stale_hours": stale_hours,
            "missing_candles": _recent_missing_candles(frame, symbol),
            "spread_percentile": spread_percentile,
            "changepoint_probability": live.get("change_probability", row.get("Changepoint Probability")),
            "structural_break_status": live.get("structural_break_status", row.get("Structural Break Status")),
            "volatility_z": _volatility_z(frame),
            "conformal_interval_ratio": _interval_explosion_ratio(
                live.get("interval_width", row.get("Conformal Interval Width")), frame,
            ),
            "canonical_identity_valid": bool(canonical.get("run_id") or canonical.get("canonical_calculation_id")) and normalize_symbol(canonical.get("symbol") or symbol) == symbol,
            "connector_ok": connector_ok,
            "live_parent_run_id": live_parent_run_id,
            "live_evidence_broker_timestamp": live.get("broker_timestamp"),
            "live_evidence_publication_status": live.get("publication_status"),
        }
        event = record_safety_event(
            daily_snapshot_id=metadata.get("daily_snapshot_id"), broker_day=metadata.get("broker_day"),
            symbol=symbol, observed_at_broker_time=observed, evidence=evidence, path=path,
        )
        events.append({"symbol": symbol, **event})
    state["field10_live_safety_veto_20260702"] = {"ok": True, "events": events}
    return {"ok": True, "status": "UPDATED", "events": events}


def load_latest_safety_events(*, broker_day: str | None = None, path: Path | str = DB_PATH) -> pd.DataFrame:
    with connect_readonly(path) as conn:
        if broker_day is None:
            row = conn.execute("SELECT MAX(broker_day) AS day FROM field10_daily_safety_event").fetchone()
            broker_day = row["day"] if row else None
        if not broker_day:
            return pd.DataFrame()
        return pd.read_sql_query(
            """SELECT broker_day AS [Broker Day],symbol AS Symbol,observed_at_broker_time AS [Observed At Broker Time],
                      safety_veto AS [Safety Veto],reasons_json AS Reasons,evidence_json AS Evidence
               FROM field10_daily_safety_event WHERE broker_day=?
               ORDER BY observed_at_broker_time DESC,symbol""",
            conn, params=(broker_day,),
        )


__all__ = [
    "VERSION", "VALID_VALUES", "evaluate_safety_veto", "record_safety_event",
    "update_live_safety_veto", "load_latest_safety_events",
]
