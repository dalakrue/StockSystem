"""Atomic SQLite metadata store for completed canonical generations."""
from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import json
import sqlite3
from typing import Any

from core.snapshot_schema_20260619 import RunSnapshot

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "canonical_runtime.sqlite3"


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(db_path); path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS runs(
      run_id TEXT NOT NULL, generation INTEGER NOT NULL, symbol TEXT NOT NULL,
      timeframe TEXT NOT NULL, completed_candle TEXT, created_at TEXT NOT NULL,
      status TEXT NOT NULL, schema_version TEXT NOT NULL, checksum TEXT NOT NULL,
      source TEXT NOT NULL DEFAULT 'canonical', PRIMARY KEY(run_id,generation));
    CREATE INDEX IF NOT EXISTS idx_runs_generation ON runs(generation DESC);
    CREATE INDEX IF NOT EXISTS idx_runs_candle ON runs(symbol,timeframe,completed_candle DESC);
    CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
    CREATE TABLE IF NOT EXISTS run_snapshots(
      run_id TEXT NOT NULL, generation INTEGER NOT NULL, snapshot_json TEXT NOT NULL,
      checksum TEXT NOT NULL, created_at TEXT NOT NULL,
      PRIMARY KEY(run_id,generation), FOREIGN KEY(run_id,generation) REFERENCES runs(run_id,generation));
    CREATE TABLE IF NOT EXISTS performance_trace(
      id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, generation INTEGER,
      stage TEXT NOT NULL, started_at TEXT, ended_at TEXT, duration_ms REAL,
      success INTEGER NOT NULL, rows_processed INTEGER NOT NULL DEFAULT 0,
      cache_status TEXT, process_rss_mb REAL, cpu_pct REAL, detail TEXT);
    CREATE INDEX IF NOT EXISTS idx_trace_run ON performance_trace(run_id,generation,id DESC);
    """)
    conn.commit()
    return conn


def _thaw(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        try:
            return {str(k): _thaw(v) for k, v in value.items()}
        except Exception:
            pass
    if isinstance(value, (list, tuple)):
        return [_thaw(v) for v in value]
    return value


def _snapshot_json(snapshot: RunSnapshot) -> str:
    data = {field.name: _thaw(getattr(snapshot, field.name)) for field in fields(snapshot)}
    # Keep DB metadata compact; large history remains in the disk-backed frame store.
    data["full_metric_history"] = {"storage": "disk-backed", "authority": "Full Metric Detail + History"}
    return json.dumps(data, ensure_ascii=False, default=str, separators=(",", ":"))


def commit_snapshot(
    snapshot: RunSnapshot, *, db_path: Path | str = DB_PATH,
    fail_after_stage: bool = False,
    history_bundle: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR REPLACE INTO runs(run_id,generation,symbol,timeframe,completed_candle,created_at,status,schema_version,checksum,source) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (snapshot.run_id, snapshot.generation, snapshot.symbol, snapshot.timeframe, snapshot.completed_candle,
             snapshot.calculation_completed_at, "CALCULATING", snapshot.schema_version, snapshot.checksum, "canonical"),
        )
        if fail_after_stage:
            raise RuntimeError("injected snapshot rollback test")
        conn.execute(
            "INSERT OR REPLACE INTO run_snapshots(run_id,generation,snapshot_json,checksum,created_at) VALUES(?,?,?,?,?)",
            (snapshot.run_id, snapshot.generation, _snapshot_json(snapshot), snapshot.checksum, snapshot.calculation_completed_at),
        )
        # The history evidence bundle shares the canonical transaction. A failure
        # rolls back both the snapshot and every affected history table, preventing
        # mixed generations across Lunch, Morning, Research, Power BI and AI.
        if history_bundle:
            # The 2026-06-21 research-validation rows use exact purpose-built
            # schemas but still share this same canonical BEGIN IMMEDIATE.
            bundle = dict(history_bundle)
            from core.research_validation_store_20260621 import (
                BUNDLE_KEY, insert_research_validation_bundle,
            )
            research_validation_bundle = bundle.pop(BUNDLE_KEY, None)
            # Quant Research V3 purpose-built rows share this exact canonical
            # BEGIN IMMEDIATE transaction, so no partial research generation can
            # be visible beside a completed snapshot.
            from core.quant_research_v3_store_20260622 import (
                BUNDLE_KEY as QUANT_V3_BUNDLE_KEY,
                insert_quant_v3_bundle,
            )
            quant_v3_bundle = bundle.pop(QUANT_V3_BUNDLE_KEY, None)
            # Quant Research V4 uses the same canonical BEGIN IMMEDIATE boundary.
            # Its compact normalized rows cannot become visible unless the full
            # canonical snapshot and every other staged history row also commit.
            from core.quant_research_v4_store_20260622 import (
                BUNDLE_KEY as QUANT_V4_BUNDLE_KEY,
                insert_quant_v4_bundle,
            )
            quant_v4_bundle = bundle.pop(QUANT_V4_BUNDLE_KEY, None)
            from core.quant_research_v6_store_20260622 import BUNDLE_KEY as QUANT_V6_BUNDLE_KEY, insert_quant_v6_bundle
            quant_v6_bundle = bundle.pop(QUANT_V6_BUNDLE_KEY, None)
            # Quant Research V7 shares the exact same canonical BEGIN IMMEDIATE.
            from core.quant_research_v7_store_20260622 import BUNDLE_KEY as QUANT_V7_BUNDLE_KEY, insert_quant_v7_bundle
            quant_v7_bundle = bundle.pop(QUANT_V7_BUNDLE_KEY, None)
            # Quant Research V8 Morning/calibration/governance histories share
            # the exact same canonical transaction and remain sidecar-safe.
            from core.morning_quant_store_20260622 import BUNDLE_KEY as QUANT_V8_BUNDLE_KEY, insert_bundle as insert_quant_v8_bundle
            quant_v8_bundle = bundle.pop(QUANT_V8_BUNDLE_KEY, None)
            if bundle:
                from core.history_evidence_store_20260620 import insert_history_bundle
                insert_history_bundle(conn, bundle)
            if research_validation_bundle:
                insert_research_validation_bundle(conn, research_validation_bundle)
            if quant_v3_bundle:
                insert_quant_v3_bundle(conn, quant_v3_bundle)
            if quant_v4_bundle:
                insert_quant_v4_bundle(conn, quant_v4_bundle)
            if quant_v6_bundle:
                insert_quant_v6_bundle(conn, quant_v6_bundle)
            if quant_v7_bundle:
                insert_quant_v7_bundle(conn, quant_v7_bundle)
            if quant_v8_bundle:
                insert_quant_v8_bundle(conn, quant_v8_bundle)
        conn.execute("UPDATE runs SET status='COMPLETED' WHERE run_id=? AND generation=?", (snapshot.run_id, snapshot.generation))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def latest_completed(*, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT snapshot_json FROM run_snapshots s JOIN runs r USING(run_id,generation) WHERE r.status='COMPLETED' ORDER BY r.generation DESC,r.created_at DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else {}
    finally:
        conn.close()


__all__ = ["DB_PATH", "connect", "commit_snapshot", "latest_completed"]
