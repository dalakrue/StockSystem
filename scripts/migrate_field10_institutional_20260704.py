#!/usr/bin/env python3
"""Dedicated non-destructive Field 10 institutional shadow migration.

This script is deliberately not imported by Streamlit renderers. Run it during
packaging/deployment before starting the application.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

MIGRATION_ID = "20260704_field10_institutional_shadow_v1"
DESCRIPTION = "Append-only normalized forecast/outcome and institutional shadow evidence under authoritative Field 10 daily snapshots."

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "multi_symbol_field10_20260701.sqlite3"

BASE_DDL = r"""
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    description TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS field10_canonical_identity (
    daily_snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    broker_day TEXT NOT NULL,
    broker_timestamp TEXT NOT NULL,
    completed_h1_candle TEXT NOT NULL,
    main_symbol TEXT NOT NULL,
    selected_symbol_universe_json TEXT NOT NULL,
    universe_hash TEXT NOT NULL,
    source_ids_json TEXT NOT NULL,
    snapshot_hashes_json TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    threshold_version TEXT NOT NULL,
    model_version TEXT NOT NULL,
    publication_status TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    created_system_time TEXT NOT NULL,
    FOREIGN KEY(daily_snapshot_id) REFERENCES field10_daily_snapshot(daily_snapshot_id)
);
CREATE INDEX IF NOT EXISTS idx_f10_identity_day ON field10_canonical_identity(broker_day DESC);
CREATE INDEX IF NOT EXISTS idx_f10_identity_candle ON field10_canonical_identity(completed_h1_candle DESC);

CREATE TABLE IF NOT EXISTS field10_forecast_ledger (
    forecast_id TEXT PRIMARY KEY,
    daily_snapshot_id TEXT NOT NULL,
    parent_run_id TEXT NOT NULL,
    child_run_id TEXT,
    broker_day TEXT NOT NULL,
    symbol TEXT NOT NULL,
    horizon_hours INTEGER NOT NULL CHECK(horizon_hours IN (1,6,12,24)),
    completed_h1_candle TEXT NOT NULL,
    published_at_broker_time TEXT NOT NULL,
    outcome_due_broker_time TEXT NOT NULL,
    raw_direction_probability REAL,
    calibrated_direction_probability REAL,
    calibration_status TEXT NOT NULL,
    raw_expected_return REAL,
    expected_value REAL,
    net_expected_value REAL,
    risk_adjusted_expected_value REAL,
    expected_spread_cost REAL,
    expected_slippage_cost REAL,
    var_95 REAL,
    cvar_95 REAL,
    expected_mfe REAL,
    expected_mae REAL,
    probability_reach_expected_value REAL,
    sample_count INTEGER,
    effective_sample_size REAL,
    lower_interval REAL,
    median_prediction REAL,
    upper_interval REAL,
    target_coverage REAL,
    transition_probability REAL,
    entry_permission TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    model_version TEXT NOT NULL,
    calibration_version TEXT NOT NULL,
    source_id TEXT,
    source_hash TEXT,
    content_hash TEXT NOT NULL UNIQUE,
    missing_reason TEXT,
    publication_status TEXT NOT NULL,
    created_system_time TEXT NOT NULL,
    UNIQUE(daily_snapshot_id,symbol,horizon_hours,model_version,calibration_version),
    FOREIGN KEY(daily_snapshot_id,symbol)
      REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_forecast_day_symbol ON field10_forecast_ledger(broker_day DESC,symbol,horizon_hours);
CREATE INDEX IF NOT EXISTS idx_f10_forecast_snapshot ON field10_forecast_ledger(daily_snapshot_id,symbol,horizon_hours);
CREATE INDEX IF NOT EXISTS idx_f10_forecast_due ON field10_forecast_ledger(outcome_due_broker_time,publication_status);
CREATE INDEX IF NOT EXISTS idx_f10_forecast_status ON field10_forecast_ledger(publication_status,broker_day DESC);

CREATE TABLE IF NOT EXISTS field10_outcome_ledger (
    forecast_id TEXT NOT NULL,
    settlement_version TEXT NOT NULL,
    outcome_due_broker_time TEXT NOT NULL,
    settled_at_broker_time TEXT NOT NULL,
    realized_return REAL,
    realized_mfe REAL,
    realized_mae REAL,
    direction_outcome TEXT,
    expected_value_reached INTEGER,
    transition_occurred INTEGER,
    spread_cost REAL,
    slippage_cost REAL,
    net_realized_return REAL,
    outcome_source_id TEXT NOT NULL,
    outcome_source_hash TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(forecast_id,settlement_version),
    FOREIGN KEY(forecast_id) REFERENCES field10_forecast_ledger(forecast_id)
);
CREATE INDEX IF NOT EXISTS idx_f10_outcome_settled ON field10_outcome_ledger(settled_at_broker_time DESC);
CREATE INDEX IF NOT EXISTS idx_f10_outcome_forecast ON field10_outcome_ledger(forecast_id);

CREATE TABLE IF NOT EXISTS field10_regime_shadow (
    daily_snapshot_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    selected_regime TEXT,
    selected_regime_probability REAL,
    second_regime TEXT,
    second_regime_probability REAL,
    posterior_margin REAL,
    regime_entropy REAL,
    self_transition_probability REAL,
    transition_probability_1h REAL,
    transition_probability_6h REAL,
    transition_probability_12h REAL,
    transition_probability_24h REAL,
    regime_age INTEGER,
    expected_remaining_duration REAL,
    regime_model_version TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    evidence_sample_size INTEGER NOT NULL,
    missing_reason TEXT,
    content_hash TEXT NOT NULL UNIQUE,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,regime_model_version),
    FOREIGN KEY(daily_snapshot_id,symbol)
      REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_regime_shadow_symbol ON field10_regime_shadow(symbol,daily_snapshot_id);

CREATE TABLE IF NOT EXISTS field10_structural_break_shadow (
    daily_snapshot_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    last_structural_break TEXT,
    structural_break_strength REAL,
    post_break_h1_count INTEGER,
    pre_post_parameter_distance REAL,
    changepoint_probability REAL,
    modal_run_length INTEGER,
    expected_run_length REAL,
    run_length_uncertainty REAL,
    post_break_validation_permission TEXT NOT NULL,
    break_components_json TEXT NOT NULL,
    model_version TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    content_hash TEXT NOT NULL UNIQUE,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol)
      REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_break_shadow_symbol ON field10_structural_break_shadow(symbol,daily_snapshot_id);

CREATE TABLE IF NOT EXISTS field10_session_shadow (
    daily_snapshot_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    session_name TEXT NOT NULL,
    session_rank INTEGER,
    session_normalized_volatility REAL,
    volatility_percentile REAL,
    abnormal_activity REAL,
    normalized_tick_volume REAL,
    normalized_spread REAL,
    expected_movement REAL,
    net_expected_value REAL,
    cvar_95 REAL,
    directional_hit_rate REAL,
    regime_compatibility REAL,
    entry_permission TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    data_completeness REAL,
    current_active_session INTEGER NOT NULL DEFAULT 0,
    next_session INTEGER NOT NULL DEFAULT 0,
    session_transition_risk REAL,
    formula_version TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    content_hash TEXT NOT NULL UNIQUE,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,session_name,formula_version),
    FOREIGN KEY(daily_snapshot_id,symbol)
      REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_session_shadow_day ON field10_session_shadow(daily_snapshot_id,session_rank,symbol);
CREATE INDEX IF NOT EXISTS idx_f10_session_shadow_symbol ON field10_session_shadow(symbol,session_name,daily_snapshot_id);

CREATE TABLE IF NOT EXISTS field10_calibration_shadow (
    daily_snapshot_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    horizon_hours INTEGER NOT NULL,
    target_name TEXT NOT NULL,
    raw_probability REAL,
    calibrated_probability REAL,
    selected_method TEXT,
    calibration_status TEXT NOT NULL,
    brier_score REAL,
    brier_skill_score REAL,
    baseline_brier_score REAL,
    log_loss REAL,
    expected_calibration_error REAL,
    maximum_calibration_error REAL,
    reliability_component REAL,
    resolution_component REAL,
    calibration_sample_count INTEGER NOT NULL,
    calibration_freshness_hours REAL,
    purging_hours INTEGER NOT NULL,
    embargo_hours INTEGER NOT NULL,
    training_interval TEXT,
    validation_interval TEXT,
    test_interval TEXT,
    calibration_version TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    metrics_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,horizon_hours,target_name,calibration_version),
    FOREIGN KEY(daily_snapshot_id,symbol)
      REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_calibration_symbol ON field10_calibration_shadow(symbol,horizon_hours,daily_snapshot_id);

CREATE TABLE IF NOT EXISTS field10_conformal_shadow (
    daily_snapshot_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    horizon_hours INTEGER NOT NULL,
    regime_key TEXT NOT NULL,
    session_key TEXT NOT NULL,
    lower_conformal_return REAL,
    median_expected_return REAL,
    upper_conformal_return REAL,
    interval_width REAL,
    target_coverage REAL,
    rolling_realized_coverage REAL,
    lower_tail_miss_rate REAL,
    upper_tail_miss_rate REAL,
    adaptive_alpha REAL,
    coverage_error REAL,
    distribution_shift_status TEXT NOT NULL,
    calibration_sample_count INTEGER NOT NULL,
    conformal_version TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    content_hash TEXT NOT NULL UNIQUE,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,horizon_hours,regime_key,session_key,conformal_version),
    FOREIGN KEY(daily_snapshot_id,symbol)
      REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_conformal_symbol ON field10_conformal_shadow(symbol,horizon_hours,daily_snapshot_id);

CREATE TABLE IF NOT EXISTS field10_dependence_shadow (
    daily_snapshot_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    correlation_cluster TEXT,
    cluster_concentration REAL,
    duplicate_exposure_penalty REAL,
    marginal_diversification_value REAL,
    usd_exposure REAL,
    eur_exposure REAL,
    common_factor_exposure REAL,
    covariance_method TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    evidence_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,covariance_method),
    FOREIGN KEY(daily_snapshot_id,symbol)
      REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_dependence_snapshot ON field10_dependence_shadow(daily_snapshot_id,symbol);

CREATE TABLE IF NOT EXISTS field10_event_intensity_shadow (
    daily_snapshot_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    event_family TEXT NOT NULL,
    baseline_intensity REAL,
    current_excitation REAL,
    decay REAL,
    event_cluster_state TEXT,
    estimated_remaining_impact REAL,
    event_transition_warning TEXT,
    model_version TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    missing_reason TEXT,
    content_hash TEXT NOT NULL UNIQUE,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,event_family,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol)
      REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);

CREATE TABLE IF NOT EXISTS field10_reliability_shadow (
    daily_snapshot_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    calibration_reliability REAL,
    conformal_coverage_reliability REAL,
    sample_adequacy REAL,
    data_completeness REAL,
    source_identity_reliability REAL,
    regime_stability REAL,
    structural_stability REAL,
    rank_stability REAL,
    feature_availability REAL,
    outcome_settlement_completeness REAL,
    aggregate_reliability REAL,
    reliability_status TEXT NOT NULL,
    principal_reliability_weakness TEXT,
    reliability_explanation TEXT NOT NULL,
    effective_sample_size REAL,
    component_weights_json TEXT NOT NULL,
    reliability_version TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,reliability_version),
    FOREIGN KEY(daily_snapshot_id,symbol)
      REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_reliability_snapshot ON field10_reliability_shadow(daily_snapshot_id,aggregate_reliability DESC);

CREATE TABLE IF NOT EXISTS field10_rank_confidence_shadow (
    daily_snapshot_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    original_rank INTEGER,
    candidate_utility REAL,
    probability_rank_1 REAL,
    probability_rank_le_4 REAL,
    median_rank REAL,
    rank_percentile_low REAL,
    rank_percentile_high REAL,
    rank_instability REAL,
    score_gap_to_next_symbol REAL,
    bootstrap_draws INTEGER NOT NULL,
    block_length INTEGER NOT NULL,
    bootstrap_seed TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    model_version TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol)
      REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_rank_confidence_snapshot ON field10_rank_confidence_shadow(daily_snapshot_id,original_rank,symbol);

CREATE TABLE IF NOT EXISTS field10_shadow_publication_audit (
    audit_id TEXT PRIMARY KEY,
    daily_snapshot_id TEXT,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    details_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    created_system_time TEXT NOT NULL,
    FOREIGN KEY(daily_snapshot_id) REFERENCES field10_daily_snapshot(daily_snapshot_id)
);
"""

IMMUTABLE_TRIGGER_DDL = r"""
CREATE TRIGGER IF NOT EXISTS trg_f10_forecast_no_update
BEFORE UPDATE ON field10_forecast_ledger
BEGIN SELECT RAISE(ABORT,'field10_forecast_ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_f10_forecast_no_delete
BEFORE DELETE ON field10_forecast_ledger
BEGIN SELECT RAISE(ABORT,'field10_forecast_ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_f10_outcome_no_update
BEFORE UPDATE ON field10_outcome_ledger
BEGIN SELECT RAISE(ABORT,'field10_outcome_ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_f10_outcome_no_delete
BEFORE DELETE ON field10_outcome_ledger
BEGIN SELECT RAISE(ABORT,'field10_outcome_ledger is append-only'); END;
"""

FORECAST_LEDGER_COLUMNS: dict[str, str] = {
    "expected_spread_cost": "REAL",
    "expected_slippage_cost": "REAL",
    "var_95": "REAL",
    "cvar_95": "REAL",
    "expected_mfe": "REAL",
    "expected_mae": "REAL",
    "probability_reach_expected_value": "REAL",
    "sample_count": "INTEGER",
    "effective_sample_size": "REAL",
}

EXPERIMENT_COLUMNS: dict[str, str] = {
    "parent_model_version": "TEXT",
    "candidate_model_version": "TEXT",
    "feature_version": "TEXT",
    "formula_version": "TEXT",
    "threshold_version": "TEXT",
    "training_interval": "TEXT",
    "validation_interval": "TEXT",
    "test_interval": "TEXT",
    "purging_interval": "TEXT",
    "embargo_interval": "TEXT",
    "parameter_values_json": "TEXT",
    "evaluation_results_json": "TEXT",
    "source_code_hash": "TEXT",
    "data_hash": "TEXT",
    "walk_forward_type": "TEXT",
    "spa_p_value_v2": "REAL",
    "pbo_probability": "REAL",
    "deflated_sharpe_probability": "REAL",
    "in_sample_metric": "REAL",
    "out_of_sample_metric": "REAL",
    "rank_correlation_stability": "REAL",
    "regime_stability": "REAL",
    "session_stability": "REAL",
    "promotion_gate_status": "TEXT",
    "promotion_reasons_json": "TEXT",
}

REQUIRED_PARENT_TABLES = ("field10_daily_snapshot", "field10_daily_snapshot_symbol")
SHADOW_TABLES = (
    "field10_canonical_identity", "field10_forecast_ledger", "field10_outcome_ledger",
    "field10_regime_shadow", "field10_structural_break_shadow", "field10_session_shadow",
    "field10_calibration_shadow", "field10_conformal_shadow", "field10_dependence_shadow",
    "field10_event_intensity_shadow", "field10_reliability_shadow",
    "field10_rank_confidence_shadow", "field10_shadow_publication_audit",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def migration_checksum() -> str:
    payload = BASE_DDL + IMMUTABLE_TRIGGER_DDL + json.dumps(EXPERIMENT_COLUMNS, sort_keys=True) + json.dumps(FORECAST_LEDGER_COLUMNS, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def row_counts(conn: sqlite3.Connection, tables: Iterable[str] | None = None) -> dict[str, int]:
    names = list(tables or [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")])
    result: dict[str, int] = {}
    for name in sorted(names):
        try:
            result[name] = int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
        except sqlite3.Error:
            continue
    return result


def schema_hash(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT type,name,tbl_name,COALESCE(sql,'') FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
    ).fetchall()
    payload = json.dumps([tuple(row) for row in rows], separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()




def execute_sql_script(conn: sqlite3.Connection, script: str) -> None:
    """Execute a SQL script statement-by-statement without implicit commits.

    sqlite3.Connection.executescript() issues an implicit COMMIT, which would
    defeat the migration's BEGIN IMMEDIATE transaction. This parser relies on
    sqlite3.complete_statement so trigger bodies remain intact.
    """
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            sql = statement.strip()
            statement = ""
            if sql:
                conn.execute(sql)
    if statement.strip():
        raise sqlite3.OperationalError("Incomplete SQL statement in migration DDL")

def apply_migration(conn: sqlite3.Connection) -> dict[str, Any]:
    missing_parent = [name for name in REQUIRED_PARENT_TABLES if not table_exists(conn, name)]
    if missing_parent:
        raise RuntimeError(f"Authoritative Field 10 parent tables are missing: {missing_parent}")

    checksum = migration_checksum()
    conn.execute("BEGIN IMMEDIATE")
    try:
        execute_sql_script(conn, BASE_DDL)
        if not table_exists(conn, "field10_research_experiments"):
            conn.execute(
                "CREATE TABLE field10_research_experiments ("
                "experiment_id TEXT PRIMARY KEY,parent_run_id TEXT NOT NULL,symbol TEXT NOT NULL,"
                "model_version TEXT NOT NULL,created_at TEXT NOT NULL)"
            )
        forecast_existing = columns(conn, "field10_forecast_ledger")
        forecast_added: list[str] = []
        for name, sql_type in FORECAST_LEDGER_COLUMNS.items():
            if name not in forecast_existing:
                conn.execute(f'ALTER TABLE field10_forecast_ledger ADD COLUMN "{name}" {sql_type}')
                forecast_added.append(name)
        existing = columns(conn, "field10_research_experiments")
        added: list[str] = []
        for name, sql_type in EXPERIMENT_COLUMNS.items():
            if name not in existing:
                conn.execute(f'ALTER TABLE field10_research_experiments ADD COLUMN "{name}" {sql_type}')
                added.append(name)
        execute_sql_script(conn, IMMUTABLE_TRIGGER_DDL)
        prior = conn.execute("SELECT checksum FROM schema_migrations WHERE migration_id=?", (MIGRATION_ID,)).fetchone()
        if prior is not None and str(prior[0]) != checksum:
            raise RuntimeError("Migration checksum mismatch for an already-applied migration ID")
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(migration_id,checksum,description,applied_at_utc) VALUES(?,?,?,?)",
            (MIGRATION_ID, checksum, DESCRIPTION, utc_now()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "migration_id": MIGRATION_ID, "checksum": checksum,
        "forecast_columns_added": forecast_added, "experiment_columns_added": added,
    }


def verify(conn: sqlite3.Connection) -> dict[str, Any]:
    integrity = [str(row[0]) for row in conn.execute("PRAGMA integrity_check")]
    fk = [tuple(row) for row in conn.execute("PRAGMA foreign_key_check")]
    missing_tables = [name for name in SHADOW_TABLES if not table_exists(conn, name)]
    duplicates: dict[str, list[tuple[Any, ...]]] = {}
    duplicate_queries = {
        "forecast_identity": (
            "SELECT daily_snapshot_id,symbol,horizon_hours,model_version,calibration_version,COUNT(*) "
            "FROM field10_forecast_ledger GROUP BY daily_snapshot_id,symbol,horizon_hours,model_version,calibration_version HAVING COUNT(*)>1"
        ),
        "outcome_identity": (
            "SELECT forecast_id,settlement_version,COUNT(*) FROM field10_outcome_ledger "
            "GROUP BY forecast_id,settlement_version HAVING COUNT(*)>1"
        ),
    }
    for name, query in duplicate_queries.items():
        duplicates[name] = [tuple(row) for row in conn.execute(query)] if not missing_tables else []
    orphan_queries = {
        "forecast_without_parent": (
            "SELECT f.forecast_id FROM field10_forecast_ledger f LEFT JOIN field10_daily_snapshot_symbol s "
            "ON s.daily_snapshot_id=f.daily_snapshot_id AND s.symbol=f.symbol WHERE s.symbol IS NULL"
        ),
        "outcome_without_forecast": (
            "SELECT o.forecast_id FROM field10_outcome_ledger o LEFT JOIN field10_forecast_ledger f "
            "ON f.forecast_id=o.forecast_id WHERE f.forecast_id IS NULL"
        ),
    }
    orphans = {name: [tuple(row) for row in conn.execute(query)] for name, query in orphan_queries.items()} if not missing_tables else {}
    parent_hash_audit = {}
    if table_exists(conn, "field10_daily_snapshot_symbol"):
        parent_hash_audit = {
            "missing_source_id": int(conn.execute("SELECT COUNT(*) FROM field10_daily_snapshot_symbol WHERE source_id IS NULL OR TRIM(source_id)='' ").fetchone()[0]),
            "missing_snapshot_hash": int(conn.execute("SELECT COUNT(*) FROM field10_daily_snapshot_symbol WHERE snapshot_hash IS NULL OR TRIM(snapshot_hash)='' ").fetchone()[0]),
        }
    secret_columns: dict[str, list[str]] = {}
    for table in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
        bad = sorted(c for c in columns(conn, table) if any(token in c.lower() for token in ("api_key", "password", "credential", "access_token")))
        if bad:
            secret_columns[str(table)] = bad
    trigger_names = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    required_triggers = {
        "trg_f10_forecast_no_update", "trg_f10_forecast_no_delete",
        "trg_f10_outcome_no_update", "trg_f10_outcome_no_delete",
    }
    ok = integrity == ["ok"] and not fk and not missing_tables and not any(duplicates.values()) and not any(orphans.values()) and not secret_columns and required_triggers.issubset(trigger_names)
    return {
        "ok": ok,
        "integrity_check": integrity,
        "foreign_key_issues": fk,
        "missing_tables": missing_tables,
        "duplicates": duplicates,
        "orphans": orphans,
        "parent_source_hash_audit": parent_hash_audit,
        "secret_column_issues": secret_columns,
        "immutable_triggers_present": sorted(required_triggers & trigger_names),
        "schema_hash": schema_hash(conn),
        "row_counts": row_counts(conn),
    }


def create_backup(db_path: Path, backup_dir: Path | None = None) -> dict[str, Any]:
    backup_dir = backup_dir or (db_path.parent.parent / "backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_dir / f"{db_path.stem}.pre_{MIGRATION_ID}_{stamp}{db_path.suffix}"
    with connect(db_path) as conn:
        conn.execute("PRAGMA wal_checkpoint(FULL)")
    source_hash = sha256_file(db_path)
    shutil.copy2(db_path, backup)
    backup_hash = sha256_file(backup)
    with connect(backup) as conn:
        backup_integrity = [str(r[0]) for r in conn.execute("PRAGMA integrity_check")]
    if source_hash != backup_hash or backup_integrity != ["ok"]:
        raise RuntimeError("Pre-migration backup verification failed")
    return {
        "backup_path": str(backup), "source_sha256": source_hash,
        "backup_sha256": backup_hash, "hash_match": True,
        "backup_integrity_check": backup_integrity,
    }


def run(db_path: Path, *, make_backup: bool = True, idempotency_test: bool = True) -> dict[str, Any]:
    db_path = db_path.resolve()
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    backup = create_backup(db_path) if make_backup else None
    pre_hash = sha256_file(db_path)
    with connect(db_path) as conn:
        pre_schema_hash = schema_hash(conn)
        pre_counts = row_counts(conn)
        migration = apply_migration(conn)
        first_verify = verify(conn)
        first_schema_hash = schema_hash(conn)
        first_counts = row_counts(conn)
    second = None
    if idempotency_test:
        with connect(db_path) as conn:
            apply_migration(conn)
            second_verify = verify(conn)
            second_schema_hash = schema_hash(conn)
            second_counts = row_counts(conn)
        second = {
            "schema_unchanged": first_schema_hash == second_schema_hash,
            "row_counts_unchanged": first_counts == second_counts,
            "verification": second_verify,
        }
    # Force WAL contents into the database before calculating the post-migration hash.
    with connect(db_path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    post_hash = sha256_file(db_path)
    report = {
        "ok": bool(first_verify.get("ok") and (second is None or (second["schema_unchanged"] and second["row_counts_unchanged"] and second["verification"].get("ok")))),
        "database": str(db_path), "migration": migration, "backup": backup,
        "pre_migration_sha256": pre_hash, "post_migration_sha256": post_hash,
        "pre_schema_hash": pre_schema_hash, "post_schema_hash": first_schema_hash,
        "pre_row_counts": pre_counts, "post_row_counts": first_counts,
        "verification": first_verify, "idempotency_test": second,
        "completed_at_utc": utc_now(),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--skip-idempotency-test", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        report = run(args.db, make_backup=not args.no_backup, idempotency_test=not args.skip_idempotency_test)
    except Exception as exc:
        report = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "database": str(args.db)}
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
