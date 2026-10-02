"""Additive institutional quant schema for the canonical multi-symbol pipeline.

This migration is intentionally conservative: it creates the new production tables
requested by the July 8 institutional ranking upgrade, repairs legacy
``schema_migrations`` shapes that are missing a ``version`` column, and never drops
or truncates user history.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sqlite3

try:
    from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
except Exception:  # pragma: no cover - import fallback for isolated tests
    DEFAULT_DB_PATH = Path("data/multi_symbol_field10_20260701.sqlite3")

SCHEMA_VERSION = 2026070803
TABLES = (
    "canonical_run_identity",
    "canonical_symbol_evidence",
    "field10_institutional_ranking",
    "field10_news_nlp_evidence",
    "field10_rank_explanation",
    "field10_model_scores",
    "field10_rank_history",
    "field3_multisymbol_regime",
    "field11_similar_path_multisymbol",
    "research_model_validation",
    "data_load_audit",
)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
    except sqlite3.Error:
        return set()


def _add_columns(conn: sqlite3.Connection, table: str, definitions: list[tuple[str, str]]) -> None:
    existing = _columns(conn, table)
    for name, definition in definitions:
        if name not in existing:
            conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}')
            existing.add(name)


def _repair_schema_migrations(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
    if row:
        cols = _columns(conn, "schema_migrations")
        if "version" not in cols:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            legacy_name = f"schema_migrations_legacy_institutional_20260708_{stamp}"
            try:
                conn.execute(f'ALTER TABLE schema_migrations RENAME TO "{legacy_name}"')
            except sqlite3.Error:
                conn.execute("DROP TABLE IF EXISTS schema_migrations")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations(
            version INTEGER PRIMARY KEY,
            migration_name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def migrate_institutional_quant_schema(db_path: str | Path | None = None) -> dict[str, Any]:
    """Create/repair the additive institutional quant tables idempotently."""
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(path), timeout=30)
    changed: list[str] = []
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("BEGIN IMMEDIATE")
        _repair_schema_migrations(conn)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS canonical_run_identity(
                parent_run_id TEXT PRIMARY KEY,
                generation TEXT,
                snapshot_hash TEXT NOT NULL,
                broker_candle_time TEXT,
                timeframe TEXT NOT NULL,
                canonical_symbols_json TEXT NOT NULL,
                loaded_symbols_json TEXT NOT NULL,
                degraded_symbols_json TEXT NOT NULL,
                missing_symbols_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS canonical_symbol_evidence(
                parent_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                provider_used TEXT,
                provider_symbol TEXT,
                candle_count INTEGER NOT NULL DEFAULT 0,
                coverage_ratio REAL NOT NULL DEFAULT 0,
                data_quality_grade TEXT,
                loaded_status TEXT,
                failure_reason TEXT,
                latest_candle_time TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,symbol,timeframe)
            );
            CREATE TABLE IF NOT EXISTS field10_institutional_ranking(
                parent_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                rank INTEGER,
                institutional_utility REAL,
                weighted_net_ev REAL,
                risk_penalty REAL,
                net_expected_value REAL,
                risk_adjusted_expected_value REAL,
                wasserstein_robust_ev REAL,
                rank_confidence REAL,
                rank_stability REAL,
                entry_permission TEXT,
                missing_reason TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,symbol,timeframe)
            );
            CREATE TABLE IF NOT EXISTS field10_news_nlp_evidence(
                parent_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                latest_news_title TEXT,
                news_currency_symbol_match TEXT,
                news_sentiment TEXT,
                news_relevance_score REAL,
                news_freshness_minutes REAL,
                news_absorption_score REAL,
                news_conflict_flag TEXT,
                nlp_evidence_source TEXT,
                nlp_missing_reason TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,symbol,timeframe)
            );
            CREATE TABLE IF NOT EXISTS field10_rank_explanation(
                parent_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                explanation_text TEXT,
                top_drivers_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,symbol,timeframe)
            );
            CREATE TABLE IF NOT EXISTS field10_model_scores(
                parent_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                model_name TEXT NOT NULL,
                brier_score REAL,
                log_score REAL,
                crps_score REAL,
                calibration_score REAL,
                coverage_score REAL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,symbol,timeframe,model_name)
            );
            CREATE TABLE IF NOT EXISTS field10_rank_history(
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                rank INTEGER,
                institutional_utility REAL,
                snapshot_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS field3_multisymbol_regime(
                parent_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                standard TEXT NOT NULL,
                scaled_score REAL,
                rank INTEGER,
                regime TEXT,
                bias TEXT,
                regime_probability REAL,
                regime_age INTEGER,
                reliability REAL,
                sample_count INTEGER,
                data_source TEXT,
                missing_reason TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,symbol,timeframe,standard)
            );
            CREATE TABLE IF NOT EXISTS field11_similar_path_multisymbol(
                parent_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                horizon TEXT NOT NULL,
                similar_path_count INTEGER,
                effective_sample_size REAL,
                regime_session_match TEXT,
                mfe REAL,
                mae REAL,
                endpoint_p10 REAL,
                endpoint_p25 REAL,
                endpoint_p50 REAL,
                endpoint_p75 REAL,
                endpoint_p90 REAL,
                drift_changepoint_warning TEXT,
                reliability REAL,
                rank_link TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,symbol,timeframe,horizon)
            );
            CREATE TABLE IF NOT EXISTS research_model_validation(
                parent_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                model_name TEXT NOT NULL,
                brier_score REAL,
                log_score REAL,
                crps_score REAL,
                calibration_curve_json TEXT,
                conformal_coverage REAL,
                spa_result TEXT,
                mcs_result TEXT,
                white_reality_check TEXT,
                pbo_cscv REAL,
                deflated_sharpe REAL,
                rank_stability REAL,
                duplicate_exposure_risk REAL,
                changepoint_risk REAL,
                data_quality_grade TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id,symbol,timeframe,model_name)
            );
            CREATE TABLE IF NOT EXISTS data_load_audit(
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_run_id TEXT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                provider_used TEXT,
                provider_source TEXT,
                provider_symbol TEXT,
                candle_count INTEGER NOT NULL DEFAULT 0,
                coverage_ratio REAL NOT NULL DEFAULT 0,
                loaded_status TEXT,
                failure_reason TEXT,
                last_successful_candle_time TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        for table in TABLES:
            changed.append(table)
        conn.execute(
            "INSERT OR REPLACE INTO schema_migrations(version,migration_name,applied_at) VALUES(?,?,?)",
            (SCHEMA_VERSION, "institutional_quant_schema_20260708", now),
        )
        conn.commit()
        return {"ok": True, "db_path": str(path), "version": SCHEMA_VERSION, "tables": changed}
    except Exception as exc:
        conn.rollback()
        return {"ok": False, "db_path": str(path), "version": SCHEMA_VERSION, "error": f"{type(exc).__name__}: {exc}", "tables": changed}
    finally:
        conn.close()


__all__ = ["SCHEMA_VERSION", "TABLES", "migrate_institutional_quant_schema"]
