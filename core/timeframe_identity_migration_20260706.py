"""Idempotent timeframe-aware identity migration.

The migration is additive.  Legacy H1 rows are retained and receive H1 aliases
only when their timeframe is missing.  No production value is recalculated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import shutil
import sqlite3

MIGRATION_ID = "20260706_timeframe_identity_child_publication_v1"


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if not exists:
        return set()
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _add(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> list[str]:
    existing = _columns(conn, table)
    added: list[str] = []
    if not existing:
        return added
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}')
            added.append(name)
    return added


def migrate_timeframe_identity(path: Path | str, *, create_backup: bool = True) -> dict[str, Any]:
    db = Path(path)
    db.parent.mkdir(parents=True, exist_ok=True)
    backup = ""
    if create_backup and db.exists():
        backup_dir = db.parent.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{db.stem}.pre_{MIGRATION_ID}.sqlite3"
        if not backup_path.exists():
            shutil.copy2(db, backup_path)
        backup = str(backup_path)

    now = datetime.now(timezone.utc).isoformat()
    added: dict[str, list[str]] = {}
    with sqlite3.connect(str(db), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations_20260706(
                   migration_id TEXT PRIMARY KEY,
                   applied_at TEXT NOT NULL,
                   details_json TEXT NOT NULL
               )"""
        )

        identity_columns = {
            "timeframe": "TEXT",
            "completed_candle": "TEXT",
            "parent_run_id": "TEXT",
            "child_run_id": "TEXT",
            "canonical_run_id": "TEXT",
            "generation_id": "TEXT",
            "snapshot_hash": "TEXT",
            "source_id": "TEXT",
        }
        for table in (
            "multi_symbol_runs", "field10_hourly_quality", "field10_daily_higher_lock",
            "field10_daily_snapshot_symbol", "field10_integrated_evidence_history",
            "canonical_symbol_results_20260705", "field11_results_20260705",
        ):
            added[table] = _add(conn, table, identity_columns)

        added["field10_daily_snapshot"] = _add(conn, "field10_daily_snapshot", {
            "timeframe": "TEXT",
            "latest_completed_candle": "TEXT",
            "generation_ids_json": "TEXT",
        })
        # Compatibility aliases: retain latest_completed_h1 and sample_complete_status.
        if _columns(conn, "field10_daily_snapshot"):
            conn.execute("UPDATE field10_daily_snapshot SET timeframe='H1' WHERE timeframe IS NULL OR TRIM(timeframe)='' ")
            conn.execute("UPDATE field10_daily_snapshot SET latest_completed_candle=latest_completed_h1 WHERE latest_completed_candle IS NULL OR TRIM(latest_completed_candle)='' ")
        for table in ("multi_symbol_runs", "field10_hourly_quality", "field10_daily_higher_lock", "field10_daily_snapshot_symbol", "field10_integrated_evidence_history"):
            cols = _columns(conn, table)
            if "timeframe" in cols:
                conn.execute(f"UPDATE {table} SET timeframe='H1' WHERE timeframe IS NULL OR TRIM(timeframe)='' ")
            if "completed_candle" in cols:
                source = next((c for c in ("broker_timestamp", "completed_broker_candle", "latest_completed_h1") if c in cols), None)
                if source:
                    conn.execute(f"UPDATE {table} SET completed_candle={source} WHERE completed_candle IS NULL OR TRIM(completed_candle)='' ")

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS child_snapshot_publication_20260706(
                parent_run_id TEXT NOT NULL,
                child_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                canonical_run_id TEXT NOT NULL,
                generation_id TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_signature TEXT,
                completed_candle TEXT NOT NULL,
                runtime_snapshot_path TEXT NOT NULL,
                runtime_snapshot_sha256 TEXT NOT NULL,
                available_candles INTEGER NOT NULL,
                required_candles INTEGER NOT NULL,
                coverage_percent REAL NOT NULL,
                field1_complete INTEGER NOT NULL,
                field2_complete INTEGER NOT NULL,
                field3_complete INTEGER NOT NULL,
                field10_complete INTEGER NOT NULL,
                reload_validation_passed INTEGER NOT NULL,
                publication_status TEXT NOT NULL,
                validation_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(symbol,timeframe,completed_candle,parent_run_id,child_run_id,canonical_run_id,generation_id,snapshot_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_child_snapshot_reload_20260706
                ON child_snapshot_publication_20260706(symbol,timeframe,completed_candle DESC,publication_status);

            CREATE TABLE IF NOT EXISTS field2_powerbi_publication_20260706(
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                completed_candle TEXT NOT NULL,
                parent_run_id TEXT NOT NULL,
                child_run_id TEXT NOT NULL,
                canonical_run_id TEXT NOT NULL,
                generation_id TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_signature TEXT,
                publication_type TEXT NOT NULL,
                calibration_status TEXT NOT NULL,
                bundle_json TEXT NOT NULL,
                bundle_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(symbol,timeframe,completed_candle,parent_run_id,child_run_id,canonical_run_id,generation_id,snapshot_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_field2_powerbi_reload_20260706
                ON field2_powerbi_publication_20260706(symbol,timeframe,completed_candle DESC);

            CREATE TABLE IF NOT EXISTS multi_symbol_state_machine_20260706(
                parent_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                state TEXT NOT NULL,
                progress_percent REAL NOT NULL,
                provider TEXT,
                available_candles INTEGER,
                required_candles INTEGER,
                latest_timestamp TEXT,
                rejection_reason TEXT,
                details_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,symbol,timeframe)
            );

            CREATE TABLE IF NOT EXISTS field10_shadow_research_validation_20260706(
                research_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                completed_candle TEXT NOT NULL,
                model_name TEXT NOT NULL,
                model_version TEXT NOT NULL,
                training_cutoff TEXT,
                test_window TEXT,
                purging_bars INTEGER,
                embargo_bars INTEGER,
                sample_count INTEGER,
                effective_sample_size REAL,
                calibration_status TEXT,
                brier_score REAL,
                log_loss REAL,
                crps REAL,
                interval_coverage REAL,
                interval_width REAL,
                cpa_p_value REAL,
                spa_p_value REAL,
                pbo REAL,
                drift_status TEXT,
                promotion_status TEXT NOT NULL,
                rejection_reason TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(research_run_id,symbol,timeframe,completed_candle,model_name,model_version)
            );
            """
        )

        # Unique timeframe-aware lookup indexes.  These do not replace legacy PKs.
        index_specs = {
            "uq_ms_runs_identity_20260706": ("multi_symbol_runs", ("symbol", "timeframe", "completed_candle", "parent_run_id", "child_run_id", "canonical_run_id", "generation_id", "snapshot_hash")),
            "idx_f10_hourly_tf_identity_20260706": ("field10_hourly_quality", ("symbol", "timeframe", "broker_timestamp", "parent_run_id")),
            "idx_f10_snapshot_symbol_tf_20260706": ("field10_daily_snapshot_symbol", ("symbol", "timeframe", "completed_candle", "canonical_run_id", "snapshot_hash")),
        }
        for name, (table, columns) in index_specs.items():
            existing = _columns(conn, table)
            usable = [c for c in columns if c in existing]
            if len(usable) >= 3:
                unique = "UNIQUE " if name.startswith("uq_") else ""
                try:
                    conn.execute(f'CREATE {unique}INDEX IF NOT EXISTS "{name}" ON "{table}"({",".join(usable)})')
                except sqlite3.IntegrityError:
                    # Keep all legacy duplicates; add a normal lookup index instead.
                    conn.execute(f'CREATE INDEX IF NOT EXISTS "{name}_lookup" ON "{table}"({",".join(usable)})')

        details = {"migration_id": MIGRATION_ID, "added_columns": added, "backup": backup}
        conn.execute(
            "INSERT OR REPLACE INTO schema_migrations_20260706(migration_id,applied_at,details_json) VALUES(?,?,?)",
            (MIGRATION_ID, now, json.dumps(details, sort_keys=True)),
        )
        conn.commit()
    return {"ok": True, "status": "MIGRATED", **details, "path": str(db)}


__all__ = ["MIGRATION_ID", "migrate_timeframe_identity"]
