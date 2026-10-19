"""Additive compressed SQLite storage for the Field 3 lifecycle monitor."""
from __future__ import annotations

from typing import Any, Mapping
import json
import sqlite3
import zlib

VERSION = "field3-regime-lifecycle-store-20260701-v1"
DDL = """
CREATE TABLE IF NOT EXISTS field3_regime_lifecycle_history_20260701(
 run_id TEXT NOT NULL,
 generation_id TEXT NOT NULL,
 snapshot_hash TEXT NOT NULL,
 completed_candle_time_utc TEXT NOT NULL,
 model_version TEXT NOT NULL,
 cache_key TEXT NOT NULL,
 status TEXT NOT NULL,
 current_regime TEXT,
 current_bias TEXT,
 final_action TEXT,
 trust_score REAL,
 payload_zlib BLOB NOT NULL,
 PRIMARY KEY(run_id, snapshot_hash, model_version)
)
"""


def save(conn: sqlite3.Connection, payload: Mapping[str, Any]) -> dict[str, Any]:
    conn.execute(DDL)
    current = payload.get("current") if isinstance(payload.get("current"), Mapping) else {}
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    # Fast deterministic compression avoids long CPU stalls on constrained Streamlit hosts.
    compressed = zlib.compress(raw, level=1)
    row = (
        str(payload.get("run_id") or ""), str(payload.get("generation_id") or ""),
        str(payload.get("snapshot_hash") or ""), str(payload.get("completed_candle_time_utc") or "UNAVAILABLE"),
        str(payload.get("version") or ""), str(payload.get("cache_key") or ""), str(payload.get("status") or "UNKNOWN"),
        current.get("current_canonical_regime"), current.get("current_bias"), current.get("final_action"),
        current.get("calibrated_trust"), sqlite3.Binary(compressed),
    )
    conn.execute(
        "INSERT OR REPLACE INTO field3_regime_lifecycle_history_20260701 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        row,
    )
    conn.commit()
    return {"ok": True, "rows": 1, "compressed_bytes": len(compressed), "raw_bytes": len(raw),
            "idempotent_key": [row[0], row[2], row[4]], "store_version": VERSION}


def load(conn: sqlite3.Connection, *, run_id: str, snapshot_hash: str) -> dict[str, Any] | None:
    conn.execute(DDL)
    row = conn.execute(
        "SELECT payload_zlib FROM field3_regime_lifecycle_history_20260701 WHERE run_id=? AND snapshot_hash=? ORDER BY rowid DESC LIMIT 1",
        (str(run_id), str(snapshot_hash)),
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(zlib.decompress(row[0]).decode("utf-8"))
    except Exception:
        return None


__all__ = ["VERSION", "DDL", "save", "load"]
