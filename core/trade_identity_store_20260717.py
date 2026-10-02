"""Append-safe paper-trade identity storage.

This module is intentionally separate from the market-ranking engine.  It can
record a paper trade only after a caller supplies an already-frozen snapshot
identity; changing a selector later cannot rewrite the trade's symbol,
timeframe, provider, entry price or entry snapshot hash.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import json
import os
import sqlite3
from typing import Any

from core.reliable_quant_contract_20260717 import TradeIdentity, freeze_trade_identity, stable_contract_hash, validate_trade_update


def _path(path: str | Path | None = None) -> Path:
    return Path(path or os.environ.get("ADX_FIELD10_AUTHORITY_DB_PATH") or "data/multi_symbol_field10_20260701.sqlite3")


def record_trade(identity: TradeIdentity | Mapping[str, Any], *, path: str | Path | None = None) -> dict[str, Any]:
    if isinstance(identity, TradeIdentity):
        trade = identity
    else:
        raw = dict(identity)
        trade = freeze_trade_identity(**{key: raw[key] for key in ("trade_id", "symbol", "timeframe", "entry_time_utc", "entry_snapshot_hash", "provider", "entry_price", "stop_price", "target_price") if key in raw})
    db = _path(path)
    from core.field10_research_migration_20260709 import migrate_field10_research_authority
    migration = migrate_field10_research_authority(db)
    if not migration.get("ok"):
        return {"ok": False, "status": "STORAGE_UNAVAILABLE", "error": migration.get("error")}
    payload = trade.to_dict()
    identity_hash = stable_contract_hash({key: payload[key] for key in ("trade_id", "symbol", "timeframe", "entry_time_utc", "entry_snapshot_hash", "provider", "entry_price", "stop_price", "target_price")})
    try:
        with sqlite3.connect(str(db), timeout=8.0) as conn:
            conn.execute(
                "INSERT INTO field10_trade_identity(trade_id,symbol,timeframe,entry_time_utc,entry_snapshot_hash,provider,entry_price,stop_price,target_price,status,exit_reason,identity_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (payload["trade_id"], payload["symbol"], payload["timeframe"], payload["entry_time_utc"], payload["entry_snapshot_hash"], payload["provider"], payload["entry_price"], payload["stop_price"], payload["target_price"], payload["status"], payload["exit_reason"], identity_hash),
            )
            event_hash = stable_contract_hash({"trade_id": payload["trade_id"], "event_type": "OPENED", "payload": payload})
            conn.execute(
                "INSERT INTO field10_trade_event(trade_id,event_type,event_time_utc,payload_json,event_hash) VALUES(?,?,?,?,?)",
                (payload["trade_id"], "OPENED", payload["entry_time_utc"], json.dumps(payload, sort_keys=True, default=str), event_hash),
            )
            conn.commit()
        return {"ok": True, "status": "RECORDED", "trade": payload}
    except sqlite3.IntegrityError:
        with sqlite3.connect(str(db)) as conn:
            existing = conn.execute("SELECT * FROM field10_trade_identity WHERE trade_id=?", (payload["trade_id"],)).fetchone()
        if existing:
            return {"ok": True, "status": "IDEMPOTENT_EXISTING", "trade_id": payload["trade_id"]}
        return {"ok": False, "status": "IDENTITY_CONFLICT", "trade_id": payload["trade_id"]}


def close_trade(
    trade_id: str,
    *,
    exit_reason: str,
    event_time_utc: str,
    path: str | Path | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    db = _path(path)
    with sqlite3.connect(str(db), timeout=8.0) as conn:
        row = conn.execute("SELECT * FROM field10_trade_identity WHERE trade_id=?", (trade_id,)).fetchone()
        if not row:
            return {"ok": False, "status": "TRADE_NOT_FOUND", "trade_id": trade_id}
        columns = [item[1] for item in conn.execute("PRAGMA table_info(field10_trade_identity)").fetchall()]
        current = dict(zip(columns, row))
        if str(current.get("status")) == "CLOSED":
            return {"ok": True, "status": "IDEMPOTENT_CLOSED", "trade_id": trade_id}
        conn.execute("UPDATE field10_trade_identity SET status='CLOSED', exit_reason=? WHERE trade_id=?", (str(exit_reason), trade_id))
        payload = {"exit_reason": str(exit_reason), "evidence": dict(evidence or {})}
        event_hash = stable_contract_hash({"trade_id": trade_id, "event_type": "CLOSED", "event_time_utc": event_time_utc, "payload": payload})
        conn.execute(
            "INSERT INTO field10_trade_event(trade_id,event_type,event_time_utc,payload_json,event_hash) VALUES(?,?,?,?,?)",
            (trade_id, "CLOSED", str(event_time_utc), json.dumps(payload, sort_keys=True, default=str), event_hash),
        )
        conn.commit()
    return {"ok": True, "status": "CLOSED", "trade_id": trade_id, "exit_reason": str(exit_reason)}


__all__ = ["close_trade", "record_trade", "validate_trade_update"]
