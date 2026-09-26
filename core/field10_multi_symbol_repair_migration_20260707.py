"""Additive migration for unlocked three-group runs and cumulative Field 10.

No trading formula or historical value is changed.  The migration creates the
selector preference row, preserves existing choices, and adds exact-symbol
lookup indexes used to recover completed children across independent parent
runs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import sqlite3

from core.multi_symbol_run_groups_20260706 import DEFAULT_GROUPS, normalize_symbols, union_symbols

MIGRATION_ID = "20260707_consolidated_field10_symbol_sync_v2"


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.Error:
        return set()


def _completed_symbols(conn: sqlite3.Connection) -> list[str]:
    tables = _tables(conn)
    found: list[str] = []
    if "child_generation_registry" in tables:
        try:
            found.extend(
                row[0]
                for row in conn.execute(
                    """SELECT symbol FROM child_generation_registry
                       WHERE UPPER(COALESCE(publication_status,'')) IN
                           ('COMPLETED','INSERTED','ALREADY_EXISTS_VALID','REPAIRED_FROM_VALID_SNAPSHOT')
                       GROUP BY symbol ORDER BY MAX(completed_broker_candle) DESC"""
                ).fetchall()
            )
        except sqlite3.Error:
            pass
    if "multi_symbol_runs" in tables:
        try:
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(multi_symbol_runs)").fetchall()}
            clause = " WHERE UPPER(COALESCE(status,''))='COMPLETED'" if "status" in columns else ""
            found.extend(row[0] for row in conn.execute("SELECT symbol FROM multi_symbol_runs" + clause).fetchall())
        except sqlite3.Error:
            pass
    if "field10_daily_higher_lock" in tables:
        try:
            found.extend(row[0] for row in conn.execute("SELECT DISTINCT symbol FROM field10_daily_higher_lock").fetchall())
        except sqlite3.Error:
            pass
    return normalize_symbols(found)


def migrate_field10_multi_symbol_repair(path: Path | str) -> dict[str, Any]:
    db = Path(path)
    db.parent.mkdir(parents=True, exist_ok=True)
    # The deployment migration owns the additive per-symbol load/sync registry.
    # Running it here makes both app.py and the legacy entry point converge on
    # one schema before selector restoration or Field 10 publication begins.
    try:
        from core.data.deployment_migrations_20260705 import migrate_deployment_schema
        migrate_deployment_schema(db)
    except Exception:
        pass
    # Ensure publication tables exist before adding lookup indexes.
    try:
        from core.child_generation_contract_20260702 import migrate_child_publication_contract
        migrate_child_publication_contract(db)
    except Exception:
        # The migration remains useful for a fresh Settings-only startup.  The
        # child contract migration is retried by the calculation transaction.
        pass

    now = datetime.now(timezone.utc).isoformat()
    seeded = False
    completed: list[str] = []
    with sqlite3.connect(str(db), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations_20260706(
                   migration_id TEXT PRIMARY KEY,
                   applied_at TEXT NOT NULL,
                   details_json TEXT NOT NULL
               )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS runtime_symbol_groups_20260706(
                   preference_id INTEGER PRIMARY KEY CHECK(preference_id=1),
                   first_symbols_json TEXT NOT NULL,
                   second_symbols_json TEXT NOT NULL,
                   third_symbols_json TEXT NOT NULL,
                   completed_symbols_json TEXT NOT NULL,
                   updated_at TEXT NOT NULL,
                   profile_version INTEGER NOT NULL
               )"""
        )
        existing = conn.execute(
            "SELECT first_symbols_json,second_symbols_json,third_symbols_json,completed_symbols_json "
            "FROM runtime_symbol_groups_20260706 WHERE preference_id=1"
        ).fetchone()
        completed = _completed_symbols(conn)
        if existing:
            try:
                previous_completed = json.loads(existing[3] or "[]")
            except Exception:
                previous_completed = []
            merged_completed = union_symbols(previous_completed, completed)
            conn.execute(
                "UPDATE runtime_symbol_groups_20260706 SET completed_symbols_json=?,updated_at=?,profile_version=? WHERE preference_id=1",
                (json.dumps(merged_completed), now, 20260707),
            )
            completed = merged_completed
        else:
            conn.execute(
                """INSERT INTO runtime_symbol_groups_20260706(
                       preference_id,first_symbols_json,second_symbols_json,third_symbols_json,
                       completed_symbols_json,updated_at,profile_version
                   ) VALUES(1,?,?,?,?,?,?)""",
                (
                    json.dumps(DEFAULT_GROUPS["FIRST"]),
                    json.dumps(DEFAULT_GROUPS["SECOND"]),
                    json.dumps(DEFAULT_GROUPS["THIRD"]),
                    json.dumps(completed), now, 20260707,
                ),
            )
            seeded = True

        tables = _tables(conn)
        indexes: list[str] = []
        registry_columns = _columns(conn, "child_generation_registry")
        if {"symbol", "timeframe", "publication_status", "completed_broker_candle", "updated_at"}.issubset(registry_columns):
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_child_generation_latest_exact_20260707
                   ON child_generation_registry(symbol,timeframe,publication_status,completed_broker_candle DESC,updated_at DESC)"""
            )
            indexes.append("idx_child_generation_latest_exact_20260707")
        field3_columns = _columns(conn, "field3_standard_evidence")
        if {"symbol", "timeframe", "standard", "broker_timestamp", "parent_run_id", "child_run_id"}.issubset(field3_columns):
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_field3_latest_exact_standard_20260707
                   ON field3_standard_evidence(symbol,timeframe,standard,broker_timestamp DESC,parent_run_id,child_run_id)"""
            )
            indexes.append("idx_field3_latest_exact_standard_20260707")
        integrated_columns = _columns(conn, "field10_integrated_evidence_history")
        if {"symbol", "timeframe", "broker_timestamp", "parent_run_id", "child_run_id"}.issubset(integrated_columns):
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_field10_integrated_exact_child_20260707
                   ON field10_integrated_evidence_history(symbol,timeframe,broker_timestamp DESC,parent_run_id,child_run_id)"""
            )
            indexes.append("idx_field10_integrated_exact_child_20260707")
        daily_columns = _columns(conn, "field10_daily_higher_lock")
        if {"symbol", "timeframe", "broker_day", "last_reviewed_broker_time"}.issubset(daily_columns):
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_field10_daily_latest_symbol_20260707
                   ON field10_daily_higher_lock(symbol,timeframe,broker_day DESC,last_reviewed_broker_time DESC)"""
            )
            indexes.append("idx_field10_daily_latest_symbol_20260707")

        detail = {
            "migration_id": MIGRATION_ID,
            "seeded_default_groups": seeded,
            "completed_symbols": completed,
            "indexes": indexes,
            "formula_changes": False,
        }
        conn.execute(
            "INSERT OR REPLACE INTO schema_migrations_20260706(migration_id,applied_at,details_json) VALUES(?,?,?)",
            (MIGRATION_ID, now, json.dumps(detail, sort_keys=True)),
        )
        conn.commit()
    return {"ok": True, **detail, "database": str(db)}


__all__ = ["MIGRATION_ID", "migrate_field10_multi_symbol_repair"]
