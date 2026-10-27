"""Idempotent non-destructive migration for Field 10 research authority layer."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import sqlite3

try:
    from core.multi_symbol_field10_20260701 import DB_PATH as DEFAULT_DB_PATH
except Exception:  # pragma: no cover
    DEFAULT_DB_PATH = Path("data/multi_symbol_field10_20260701.sqlite3")

MIGRATION_VERSION = "20260717_reliable_field10_authority_v1"


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def repair_schema_migrations(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)")
    cols = _columns(conn, "schema_migrations")
    if "version" not in cols:
        _ensure_column(conn, "schema_migrations", "version", "TEXT")
        cols = _columns(conn, "schema_migrations")
        if "migration_id" in cols:
            conn.execute("UPDATE schema_migrations SET version = COALESCE(version, migration_id)")
    _ensure_column(conn, "schema_migrations", "applied_at", "TEXT")
    _ensure_column(conn, "schema_migrations", "checksum", "TEXT")
    _ensure_column(conn, "schema_migrations", "status", "TEXT")
    conn.execute("UPDATE schema_migrations SET applied_at = COALESCE(applied_at, CURRENT_TIMESTAMP)")
    conn.execute("UPDATE schema_migrations SET checksum = COALESCE(checksum, '')")
    conn.execute("UPDATE schema_migrations SET status = COALESCE(status, 'APPLIED')")
    conn.execute("CREATE TABLE IF NOT EXISTS migration_lock (name TEXT PRIMARY KEY, locked_at TEXT DEFAULT CURRENT_TIMESTAMP, owner TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS migration_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, migration_version TEXT, action TEXT, status TEXT, detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS field10_unified_rank_snapshot (
            daily_snapshot_id TEXT PRIMARY KEY,
            parent_run_id TEXT,
            generation_id TEXT,
            broker_day TEXT,
            timeframe TEXT,
            completed_broker_candle TEXT,
            ordered_symbol_universe TEXT,
            loaded_symbol_count INTEGER,
            failed_symbol_count INTEGER,
            universe_hash TEXT,
            snapshot_hash TEXT,
            input_hash TEXT,
            output_hash TEXT,
            model_version TEXT,
            formula_version TEXT,
            created_at_broker_time TEXT,
            publication_status TEXT,
            incomplete_reason TEXT,
            why_trust_json TEXT,
            authority_key TEXT,
            canonical_symbol TEXT,
            provider_symbol TEXT,
            broker_timezone_policy TEXT,
            source_id TEXT,
            source_snapshot_hash TEXT,
            data_revision TEXT,
            feature_schema_hash TEXT,
            cross_device_parity_status TEXT,
            publication_mode TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS field10_unified_rank_symbol (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            daily_snapshot_id TEXT,
            parent_run_id TEXT,
            generation_id TEXT,
            broker_day TEXT,
            timeframe TEXT,
            completed_broker_candle TEXT,
            symbol TEXT,
            rank INTEGER,
            stable_daily_bias TEXT,
            less_risky_bias TEXT,
            entry_permission TEXT,
            data_quality_grade TEXT,
            sample_count INTEGER,
            provider_used TEXT,
            evidence_source TEXT,
            row_json TEXT,
            model_version TEXT,
            formula_version TEXT,
            input_hash TEXT,
            output_hash TEXT,
            created_at_broker_time TEXT,
            publication_status TEXT,
            incomplete_reason TEXT,
            authority_key TEXT,
            row_hash TEXT,
            UNIQUE(daily_snapshot_id, symbol)
        )
    """)
    common = """
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        daily_snapshot_id TEXT,
        parent_run_id TEXT,
        generation_id TEXT,
        broker_day TEXT,
        timeframe TEXT,
        completed_broker_candle TEXT,
        symbol TEXT,
        row_json TEXT,
        model_version TEXT,
        formula_version TEXT,
        input_hash TEXT,
        output_hash TEXT,
        created_at_broker_time TEXT,
        publication_status TEXT,
        incomplete_reason TEXT,
        authority_key TEXT,
        row_hash TEXT
    """
    for table in (
        "field10_daily_session_rank",
        "field10_daily_news_event_rank",
        "field10_research_background_evidence",
        "field10_session_outcome",
        "field10_news_event_outcome",
        "field10_candidate_governance",
        "dinner_research_background_evidence",
        "visualization_view_materialized",
        "export_manifest",
        "mobile_download_audit",
    ):
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({common})")
        _ensure_column(conn, table, "authority_key", "TEXT")
        _ensure_column(conn, table, "row_hash", "TEXT")
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_authority_row ON {table}(daily_snapshot_id, row_hash)")
    # Additive columns for databases created by the earlier 20260709 package.
    # Existing rows remain untouched; new authority publications carry the
    # complete cross-device identity and a content hash.
    snapshot_columns = {
        "authority_key": "TEXT", "canonical_symbol": "TEXT", "provider_symbol": "TEXT",
        "broker_timezone_policy": "TEXT", "source_id": "TEXT", "source_snapshot_hash": "TEXT",
        "data_revision": "TEXT", "feature_schema_hash": "TEXT",
        "cross_device_parity_status": "TEXT", "publication_mode": "TEXT",
        "authority_identity_json": "TEXT",
    }
    for column, decl in snapshot_columns.items():
        _ensure_column(conn, "field10_unified_rank_snapshot", column, decl)
    for column, decl in {"authority_key": "TEXT", "row_hash": "TEXT"}.items():
        _ensure_column(conn, "field10_unified_rank_symbol", column, decl)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_field10_unified_rank_symbol_authority ON field10_unified_rank_symbol(daily_snapshot_id, symbol)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS field10_authority_publication_attempt (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            authority_key TEXT NOT NULL,
            daily_snapshot_id TEXT NOT NULL,
            attempt_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(authority_key, attempt_hash)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS field10_trade_identity (
            trade_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            entry_time_utc TEXT NOT NULL,
            entry_snapshot_hash TEXT NOT NULL,
            provider TEXT NOT NULL,
            entry_price REAL NOT NULL,
            stop_price REAL,
            target_price REAL,
            status TEXT NOT NULL,
            exit_reason TEXT,
            identity_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS field10_trade_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_time_utc TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            event_hash TEXT NOT NULL UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS background_function_registry (
            function_name TEXT PRIMARY KEY,
            research_source TEXT,
            purpose TEXT,
            input_contract TEXT,
            output_contract TEXT,
            required_columns TEXT,
            optional_columns TEXT,
            version TEXT,
            is_heavy INTEGER,
            runs_during TEXT,
            writes_to_table TEXT,
            ui_consumer_tabs TEXT,
            health_status TEXT DEFAULT 'READY',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _record_migration(conn: sqlite3.Connection) -> None:
    info = conn.execute("PRAGMA table_info(schema_migrations)").fetchall()
    cols = [row[1] for row in info]
    type_by_col = {row[1]: str(row[2] or "").upper() for row in info}
    payload: dict[str, Any] = {}
    if "version" in cols:
        payload["version"] = 2026070901 if "INT" in type_by_col.get("version", "") else MIGRATION_VERSION
    if "migration_id" in cols:
        payload["migration_id"] = MIGRATION_VERSION
    if "migration_name" in cols:
        payload["migration_name"] = MIGRATION_VERSION
    if "applied_at" in cols:
        payload["applied_at"] = None
    if "checksum" in cols:
        payload["checksum"] = "additive_field10_research_authority_v1"
    if "status" in cols:
        payload["status"] = "APPLIED"
    payload = {k: v for k, v in payload.items() if k in cols}
    if "applied_at" in payload and payload["applied_at"] is None:
        insert_cols = [k for k in payload if k != "applied_at"] + ["applied_at"]
        placeholders = ["?"] * (len(insert_cols) - 1) + ["CURRENT_TIMESTAMP"]
        values = [payload[k] for k in insert_cols if k != "applied_at"]
    else:
        insert_cols = list(payload)
        placeholders = ["?"] * len(insert_cols)
        values = [payload[k] for k in insert_cols]
    if not insert_cols:
        return
    # Migration bookkeeping is itself append-safe.  A rerun must not rewrite
    # the original applied row or make a false new version appear current.
    sql = f"INSERT INTO schema_migrations({','.join(insert_cols)}) VALUES({','.join(placeholders)}) ON CONFLICT DO NOTHING"
    conn.execute(sql, values)


def migrate_field10_research_authority(db_path: str | Path | None = None) -> dict[str, Any]:
    conn = _connect(db_path)
    try:
        repair_schema_migrations(conn)
        _create_tables(conn)
        _record_migration(conn)
        conn.execute(
            "INSERT INTO migration_audit(migration_version, action, status, detail) VALUES(?, 'migrate', 'APPLIED', ?)",
            (MIGRATION_VERSION, "Created Field 10 unified rank, session/news/background, export and mobile audit tables."),
        )
        conn.commit()
        return {"ok": True, "migration_version": MIGRATION_VERSION, "db_path": str(Path(db_path or DEFAULT_DB_PATH))}
    except Exception as exc:
        conn.rollback()
        return {"ok": False, "migration_version": MIGRATION_VERSION, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover
    print(migrate_field10_research_authority())
