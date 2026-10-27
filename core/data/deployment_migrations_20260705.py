"""Idempotent deployment schema for quota-safe canonical market-data runtime."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import sqlite3
import shutil

SCHEMA_VERSION = 2026070802
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "multi_symbol_field10_20260701.sqlite3"


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _add_columns(conn: sqlite3.Connection, table: str, definitions: Iterable[tuple[str, str]]) -> None:
    existing = _columns(conn, table)
    for name, definition in definitions:
        if name not in existing:
            conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}')
            existing.add(name)


@contextmanager
def _transaction(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_deployment_schema(db_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(db_path or DEFAULT_DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    backup_path = path.with_suffix(path.suffix + ".pre_normalized_20260707.bak")
    if path.exists() and not backup_path.exists():
        try:
            shutil.copy2(path, backup_path)
        except OSError:
            backup_path = Path("")
    with _transaction(path) as conn:
        # Legacy repair: older packages created schema_migrations with columns
        # such as migration_id/checksum but no version column.  CREATE TABLE IF
        # NOT EXISTS cannot repair that shape, so preserve the old table and
        # create the canonical versioned table transaction-safely.
        existing_schema = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
        if existing_schema:
            schema_cols = _columns(conn, "schema_migrations")
            if "version" not in schema_cols:
                conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations_legacy_backup_20260708 AS SELECT * FROM schema_migrations WHERE 0")
                try:
                    conn.execute("INSERT INTO schema_migrations_legacy_backup_20260708 SELECT * FROM schema_migrations")
                except Exception:
                    pass
                conn.execute("ALTER TABLE schema_migrations RENAME TO schema_migrations_legacy_20260708")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_migrations(
            version INTEGER PRIMARY KEY,
            migration_name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS deployment_schema_migrations(
            version INTEGER PRIMARY KEY,
            migration_name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runtime_preferences(
            preference_id INTEGER PRIMARY KEY CHECK(preference_id=1),
            selected_symbols_json TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runtime_symbol_groups_20260706(
            preference_id INTEGER PRIMARY KEY CHECK(preference_id=1),
            first_symbols_json TEXT NOT NULL,
            second_symbols_json TEXT NOT NULL,
            third_symbols_json TEXT NOT NULL,
            completed_symbols_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            profile_version INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS multi_symbol_load_audit_20260707(
            load_id TEXT PRIMARY KEY,
            group_name TEXT NOT NULL,
            scope TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            selection_signature TEXT NOT NULL,
            requested_symbols_json TEXT NOT NULL,
            loaded_symbols_json TEXT NOT NULL,
            failed_symbols_json TEXT NOT NULL,
            validation_json TEXT NOT NULL,
            status TEXT NOT NULL,
            loaded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS multi_symbol_symbol_sync_20260707(
            group_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            load_id TEXT NOT NULL,
            selector_position INTEGER NOT NULL,
            rows_loaded INTEGER NOT NULL DEFAULT 0,
            required_rows INTEGER NOT NULL DEFAULT 0,
            minimum_rows INTEGER NOT NULL DEFAULT 0,
            provider TEXT,
            calculation_mode TEXT,
            validation_status TEXT NOT NULL,
            validation_reason TEXT,
            selection_signature TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(group_name,symbol,timeframe)
        );
        CREATE TABLE IF NOT EXISTS forex_symbol_load_cache_20260708(
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            provider_used TEXT NOT NULL,
            api_status TEXT NOT NULL,
            candle_count INTEGER NOT NULL DEFAULT 0,
            latest_price REAL,
            latest_candle_time TEXT,
            data_quality TEXT,
            load_time TEXT NOT NULL,
            error_message TEXT,
            run_id TEXT,
            PRIMARY KEY(symbol,timeframe,run_id)
        );
        CREATE TABLE IF NOT EXISTS symbol_load_ledger_20260708(
            ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            provider_attempted TEXT NOT NULL,
            provider_used TEXT,
            status TEXT NOT NULL,
            rows INTEGER NOT NULL DEFAULT 0,
            completed_candle_time TEXT,
            response_time_ms REAL,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS symbol_provider_health_20260708(
            provider TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            live_state TEXT NOT NULL DEFAULT 'HEALTHY',
            score REAL NOT NULL DEFAULT 0.5,
            circuit_open INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            successes INTEGER NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0,
            last_success_at TEXT,
            last_failure_at TEXT,
            last_error TEXT,
            median_response_ms REAL,
            last_rows INTEGER NOT NULL DEFAULT 0,
            last_coverage_ratio REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(provider,symbol,timeframe)
        );
        CREATE TABLE IF NOT EXISTS accepted_candles_by_provider_20260708(
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            candle_time TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_key_alias TEXT,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL,
            run_id TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY(symbol,timeframe,candle_time,provider)
        );
        CREATE TABLE IF NOT EXISTS api_connection_state(
            provider TEXT PRIMARY KEY,
            configured INTEGER NOT NULL DEFAULT 0,
            connected INTEGER NOT NULL DEFAULT 0,
            secret_fingerprint TEXT,
            last_success_at TEXT,
            last_failure_at TEXT,
            last_status TEXT,
            last_error_code TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS api_request_ledger(
            request_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            endpoint_category TEXT NOT NULL,
            request_cost REAL NOT NULL DEFAULT 1,
            requested_at TEXT NOT NULL,
            response_status TEXT NOT NULL,
            http_status INTEGER,
            retry_count INTEGER NOT NULL DEFAULT 0,
            run_id TEXT,
            symbol_hash TEXT,
            timeframe TEXT
        );
        CREATE TABLE IF NOT EXISTS provider_health(
            provider TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            healthy INTEGER NOT NULL DEFAULT 0,
            last_success_at TEXT,
            last_failure_at TEXT,
            last_429_at TEXT,
            retry_after_seconds REAL,
            fallback_count INTEGER NOT NULL DEFAULT 0,
            detail_code TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS daily_quota_usage(
            provider TEXT NOT NULL,
            usage_day TEXT NOT NULL,
            estimated_used REAL NOT NULL DEFAULT 0,
            emergency_used REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(provider, usage_day)
        );
        CREATE TABLE IF NOT EXISTS candles(
            candle_id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            broker_open_time TEXT NOT NULL,
            broker_close_time TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL,
            provider TEXT NOT NULL,
            provider_key_alias TEXT,
            fetched_at TEXT NOT NULL,
            is_complete INTEGER NOT NULL,
            broker_time TEXT NOT NULL,
            data_quality_score REAL NOT NULL,
            validation_status TEXT NOT NULL,
            source_status TEXT NOT NULL,
            run_id TEXT,
            UNIQUE(symbol,timeframe,broker_open_time)
        );
        CREATE TABLE IF NOT EXISTS news_articles(
            article_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            source TEXT,
            source_quality REAL,
            title TEXT NOT NULL,
            description TEXT,
            article_url TEXT,
            published_at TEXT,
            fetched_at TEXT NOT NULL,
            language TEXT,
            translated_title TEXT,
            title_hash TEXT NOT NULL,
            body_hash TEXT,
            duplicate_group TEXT,
            novelty_score REAL,
            eur_relevance REAL,
            usd_relevance REAL,
            eurusd_relevance REAL,
            event_type TEXT,
            event_importance REAL,
            finbert_result TEXT,
            vader_result REAL,
            provider_sentiment REAL,
            pair_direction_implication REAL,
            freshness_score REAL,
            uncertainty REAL,
            reliability REAL,
            payload_json TEXT
        );
        CREATE TABLE IF NOT EXISTS sentiment_results(
            result_id TEXT PRIMARY KEY,
            dataset_hash TEXT NOT NULL,
            symbol TEXT NOT NULL,
            run_id TEXT,
            eur_score REAL,
            usd_score REAL,
            eurusd_score REAL,
            strength REAL,
            uncertainty REAL,
            event_risk REAL,
            reliability REAL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(dataset_hash,symbol)
        );
        CREATE TABLE IF NOT EXISTS macro_observations(
            provider TEXT NOT NULL,
            series_id TEXT NOT NULL,
            observation_date TEXT NOT NULL,
            value REAL,
            release_at TEXT,
            fetched_at TEXT NOT NULL,
            freshness_status TEXT NOT NULL,
            payload_json TEXT,
            PRIMARY KEY(provider,series_id,observation_date)
        );
        CREATE TABLE IF NOT EXISTS canonical_snapshots(
            run_id TEXT PRIMARY KEY,
            generation INTEGER NOT NULL,
            selected_symbols_json TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            latest_completed_candle TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            calculation_version TEXT NOT NULL,
            snapshot_json TEXT NOT NULL,
            snapshot_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS fallback_events(
            event_id TEXT PRIMARY KEY,
            run_id TEXT,
            symbol TEXT,
            timeframe TEXT,
            from_provider TEXT,
            to_provider TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS calculation_runs(
            run_id TEXT PRIMARY KEY,
            generation INTEGER NOT NULL,
            selected_symbols_json TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            latest_completed_candle TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            canonical_snapshot_hash TEXT,
            error_code TEXT
        );
        CREATE TABLE IF NOT EXISTS multi_symbol_completion_audit_20260706(
            parent_run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            selected_symbols_json TEXT NOT NULL,
            completed_child_count INTEGER NOT NULL DEFAULT 0,
            field10_row_count INTEGER NOT NULL DEFAULT 0,
            failure_json TEXT,
            report_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS field10_latest_run_result_20260706(
            parent_run_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            rank_value REAL,
            result_json TEXT NOT NULL,
            validation_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(parent_run_id, symbol)
        );
        """)
        connection_columns = _columns(conn, "api_connection_state")
        if "credential_fingerprint" in connection_columns and "secret_fingerprint" not in connection_columns:
            conn.execute('ALTER TABLE "api_connection_state" RENAME COLUMN "credential_fingerprint" TO "secret_fingerprint"')
        elif "credential_fingerprint" in connection_columns and "secret_fingerprint" in connection_columns:
            conn.execute(
                "UPDATE api_connection_state SET secret_fingerprint=COALESCE(secret_fingerprint,credential_fingerprint)"
            )
            conn.execute('ALTER TABLE "api_connection_state" DROP COLUMN "credential_fingerprint"')
        _add_columns(conn, "runtime_preferences", (("selection_profile_version", "INTEGER NOT NULL DEFAULT 0"),))
        _add_columns(conn, "multi_symbol_load_audit_20260707", (
            ("requested_count", "INTEGER NOT NULL DEFAULT 0"),
            ("loaded_count", "INTEGER NOT NULL DEFAULT 0"),
            ("failed_count", "INTEGER NOT NULL DEFAULT 0"),
            ("accepted_live_capacity", "INTEGER NOT NULL DEFAULT 7"),
        ))
        _add_columns(conn, "multi_symbol_symbol_sync_20260707", (
            ("provider_used", "TEXT"),
            ("api_status", "TEXT"),
            ("candle_count", "INTEGER NOT NULL DEFAULT 0"),
            ("latest_price", "REAL"),
            ("latest_candle_time", "TEXT"),
            ("data_quality", "TEXT"),
            ("load_time", "TEXT"),
            ("error_message", "TEXT"),
            ("run_id", "TEXT"),
        ))
        _add_columns(conn, "candles", (("provider_symbol", "TEXT"), ("provider_key_alias", "TEXT"), ("data_age_seconds", "REAL")))
        _add_columns(conn, "accepted_candles_by_provider_20260708", (("provider_key_alias", "TEXT"),))
        _add_columns(conn, "canonical_snapshots", (("broker_time", "TEXT"), ("expires_at", "TEXT")))
        conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_symbol_groups_updated ON runtime_symbol_groups_20260706(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_multi_symbol_load_group_time ON multi_symbol_load_audit_20260707(group_name,loaded_at DESC);
        CREATE INDEX IF NOT EXISTS idx_multi_symbol_load_signature ON multi_symbol_load_audit_20260707(selection_signature,timeframe);
        CREATE INDEX IF NOT EXISTS idx_multi_symbol_symbol_sync_load ON multi_symbol_symbol_sync_20260707(load_id,selector_position);
        CREATE INDEX IF NOT EXISTS idx_multi_symbol_symbol_sync_exact ON multi_symbol_symbol_sync_20260707(symbol,timeframe,validation_status,updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_forex_symbol_load_cache_latest ON forex_symbol_load_cache_20260708(symbol,timeframe,load_time DESC);
        CREATE INDEX IF NOT EXISTS idx_forex_symbol_load_cache_run ON forex_symbol_load_cache_20260708(run_id,symbol,timeframe);
        CREATE INDEX IF NOT EXISTS idx_symbol_load_ledger_run ON symbol_load_ledger_20260708(run_id,symbol,timeframe,created_at);
        CREATE INDEX IF NOT EXISTS idx_symbol_provider_health_state ON symbol_provider_health_20260708(provider,live_state,circuit_open,updated_at);
        CREATE INDEX IF NOT EXISTS idx_accepted_candles_provider_lookup ON accepted_candles_by_provider_20260708(symbol,timeframe,candle_time DESC);
        CREATE INDEX IF NOT EXISTS idx_api_request_provider_time ON api_request_ledger(provider,requested_at);
        CREATE INDEX IF NOT EXISTS idx_api_request_run ON api_request_ledger(run_id,provider);
        CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles(symbol,timeframe,broker_open_time DESC);
        CREATE INDEX IF NOT EXISTS idx_candles_provider ON candles(provider,symbol,timeframe,broker_open_time DESC);
        CREATE INDEX IF NOT EXISTS idx_news_time ON news_articles(published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_news_hash ON news_articles(title_hash,body_hash);
        CREATE INDEX IF NOT EXISTS idx_sentiment_run ON sentiment_results(run_id,symbol);
        CREATE INDEX IF NOT EXISTS idx_macro_series ON macro_observations(provider,series_id,observation_date DESC);
        CREATE INDEX IF NOT EXISTS idx_snapshot_scope ON canonical_snapshots(timeframe,latest_completed_candle,created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_fallback_run ON fallback_events(run_id,symbol,occurred_at);
        CREATE INDEX IF NOT EXISTS idx_calculation_status ON calculation_runs(status,started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_completion_audit_created ON multi_symbol_completion_audit_20260706(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_field10_latest_run_created ON field10_latest_run_result_20260706(created_at DESC, parent_run_id, rank_value);
        """)
        conn.execute(
            "INSERT OR IGNORE INTO deployment_schema_migrations(version,migration_name,applied_at) VALUES(?,?,?)",
            (SCHEMA_VERSION, "foreground_symbol_router_schema_20260708", now),
        )
    normalized_report: dict[str, Any] = {}
    try:
        from core.normalized_multi_symbol_migration_20260707 import migrate_normalized_multi_symbol_schema
        normalized_report = migrate_normalized_multi_symbol_schema(path)
    except Exception as exc:
        normalized_report = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": bool(normalized_report.get("ok", True)),
        "db_path": str(path),
        "schema_version": SCHEMA_VERSION,
        "applied_at": now,
        "normalized_multi_symbol": normalized_report,
        "backup_path": str(backup_path) if backup_path else None,
    }


if __name__ == "__main__":
    print(migrate_deployment_schema())
