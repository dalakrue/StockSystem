#!/usr/bin/env python3
"""Additive migration for Field 10 horizon/connected/tail shadow candidate.

This script is never imported by a renderer.  It creates a timestamped database
backup before applying an atomic, idempotent migration and verifies that parent
snapshot row counts and hashes are unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "multi_symbol_field10_20260701.sqlite3"
MIGRATION_ID = "20260705_field10_horizon_connected_tail_candidate_v1"
DESCRIPTION = "Append-only normalized evidence for field10_horizon_connected_tail_candidate_v1."

DDL = r"""
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    description TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS field10_horizon_volatility_shadow (
    daily_snapshot_id TEXT NOT NULL,
    parent_run_id TEXT NOT NULL,
    child_run_id TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    broker_day TEXT NOT NULL,
    horizon INTEGER NOT NULL CHECK(horizon IN (1,3,6,12,24,36)),
    completed_broker_candle TEXT NOT NULL,
    forecast_volatility REAL,
    volatility_percentile REAL,
    volatility_surprise REAL,
    volatility_forecast_error REAL,
    expected_movement_lower REAL,
    expected_movement_upper REAL,
    har_sample_count INTEGER NOT NULL DEFAULT 0,
    har_validation_status TEXT NOT NULL,
    har_missing_reason TEXT,
    model_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    threshold_version TEXT NOT NULL,
    source_id TEXT,
    source_hash TEXT,
    snapshot_hash TEXT,
    universe_hash TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,horizon,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_hvol_snapshot ON field10_horizon_volatility_shadow(daily_snapshot_id,symbol,horizon);

CREATE TABLE IF NOT EXISTS field10_semivariance_shadow (
    daily_snapshot_id TEXT NOT NULL,
    parent_run_id TEXT NOT NULL,
    child_run_id TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    broker_day TEXT NOT NULL,
    horizon INTEGER NOT NULL DEFAULT 1,
    completed_broker_candle TEXT NOT NULL,
    positive_realized_semivariance REAL,
    negative_realized_semivariance REAL,
    downside_share REAL,
    upside_share REAL,
    semivariance_imbalance REAL,
    buy_directional_tail_pressure REAL,
    sell_directional_tail_pressure REAL,
    semivariance_method TEXT NOT NULL,
    semivariance_sample_count INTEGER NOT NULL DEFAULT 0,
    semivariance_validation_status TEXT NOT NULL,
    reliability_penalty REAL,
    model_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    threshold_version TEXT NOT NULL,
    source_id TEXT,
    source_hash TEXT,
    snapshot_hash TEXT,
    universe_hash TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,semivariance_method,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);

CREATE TABLE IF NOT EXISTS field10_gas_state_shadow (
    daily_snapshot_id TEXT NOT NULL,
    parent_run_id TEXT NOT NULL,
    child_run_id TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    broker_day TEXT NOT NULL,
    horizon INTEGER NOT NULL DEFAULT 1,
    completed_broker_candle TEXT NOT NULL,
    state_name TEXT NOT NULL,
    previous_state REAL,
    scaled_score REAL,
    omega REAL,
    score_loading REAL,
    persistence REAL,
    update_magnitude REAL,
    resulting_state REAL,
    lower_bound REAL,
    upper_bound REAL,
    finite_validation INTEGER NOT NULL,
    bound_validation INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    threshold_version TEXT NOT NULL,
    source_id TEXT,
    source_hash TEXT,
    snapshot_hash TEXT,
    universe_hash TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,state_name,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);

CREATE TABLE IF NOT EXISTS field10_tail_risk_shadow (
    daily_snapshot_id TEXT NOT NULL,
    parent_run_id TEXT NOT NULL,
    child_run_id TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    broker_day TEXT NOT NULL,
    horizon INTEGER NOT NULL CHECK(horizon IN (1,3,6,12,24,36)),
    completed_broker_candle TEXT NOT NULL,
    direction TEXT NOT NULL,
    directional_var_95 REAL,
    directional_expected_shortfall_95 REAL,
    es_var_severity_ratio REAL,
    tail_loss_probability REAL,
    tail_adjusted_expected_value REAL,
    tail_model_coverage REAL,
    tail_exception_count INTEGER,
    tail_exception_total INTEGER,
    tail_exception_independence REAL,
    joint_var_es_loss REAL,
    tail_backtest_status TEXT NOT NULL,
    purge_hours INTEGER NOT NULL,
    embargo_hours INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    threshold_version TEXT NOT NULL,
    source_id TEXT,
    source_hash TEXT,
    snapshot_hash TEXT,
    universe_hash TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,horizon,direction,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_tail_symbol ON field10_tail_risk_shadow(symbol,horizon,daily_snapshot_id);

CREATE TABLE IF NOT EXISTS field10_copula_shadow (
    daily_snapshot_id TEXT NOT NULL,
    parent_run_id TEXT NOT NULL,
    child_run_id TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    broker_day TEXT NOT NULL,
    peer_symbol TEXT NOT NULL,
    horizon INTEGER NOT NULL DEFAULT 1,
    completed_broker_candle TEXT NOT NULL,
    ordinary_conditional_dependence REAL,
    lower_tail_dependence REAL,
    upper_tail_dependence REAL,
    joint_adverse_move_probability REAL,
    joint_favorable_move_probability REAL,
    dependence_regime TEXT,
    dependence_instability REAL,
    duplicate_currency_exposure REAL,
    currency_leg_detail_json TEXT NOT NULL,
    copula_validation_status TEXT NOT NULL,
    sample_count INTEGER NOT NULL DEFAULT 0,
    model_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    threshold_version TEXT NOT NULL,
    source_id TEXT,
    source_hash TEXT,
    snapshot_hash TEXT,
    universe_hash TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,peer_symbol,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);

CREATE TABLE IF NOT EXISTS field10_connectedness_shadow (
    daily_snapshot_id TEXT NOT NULL,
    parent_run_id TEXT NOT NULL,
    child_run_id TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    broker_day TEXT NOT NULL,
    horizon INTEGER NOT NULL DEFAULT 12,
    completed_broker_candle TEXT NOT NULL,
    bad_volatility_received REAL,
    bad_volatility_transmitted REAL,
    good_volatility_received REAL,
    good_volatility_transmitted REAL,
    net_bad_spillover REAL,
    net_good_spillover REAL,
    stress_receiver_status TEXT,
    stress_transmitter_status TEXT,
    adverse_connectedness_score REAL,
    contagion_safety_permission TEXT NOT NULL,
    model_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    threshold_version TEXT NOT NULL,
    source_id TEXT,
    source_hash TEXT,
    snapshot_hash TEXT,
    universe_hash TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);

CREATE TABLE IF NOT EXISTS field10_frequency_connectedness_shadow (
    daily_snapshot_id TEXT NOT NULL,
    parent_run_id TEXT NOT NULL,
    child_run_id TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    broker_day TEXT NOT NULL,
    horizon INTEGER NOT NULL CHECK(horizon IN (1,3,6,12,24,36)),
    completed_broker_candle TEXT NOT NULL,
    connectedness_short REAL,
    connectedness_medium REAL,
    connectedness_persistent REAL,
    mapped_connectedness REAL,
    mapped_band TEXT NOT NULL,
    persistent_shock_share REAL,
    short_horizon_net_transmitter REAL,
    medium_horizon_net_transmitter REAL,
    persistent_net_transmitter REAL,
    horizon_connectedness_status TEXT NOT NULL,
    frequency_mapping_version TEXT NOT NULL,
    model_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    threshold_version TEXT NOT NULL,
    source_id TEXT,
    source_hash TEXT,
    snapshot_hash TEXT,
    universe_hash TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,horizon,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);

CREATE TABLE IF NOT EXISTS field10_model_confidence_set (
    daily_snapshot_id TEXT NOT NULL,
    parent_run_id TEXT NOT NULL,
    child_run_id TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    broker_day TEXT NOT NULL,
    horizon INTEGER NOT NULL CHECK(horizon IN (1,3,6,12,24,36)),
    completed_broker_candle TEXT NOT NULL,
    model_name TEXT NOT NULL,
    loss_function TEXT NOT NULL,
    mean_loss REAL,
    mcs_membership INTEGER NOT NULL DEFAULT 0,
    elimination_round INTEGER,
    test_statistic REAL,
    p_value REAL,
    validation_window TEXT,
    bootstrap_draws INTEGER NOT NULL,
    block_length INTEGER NOT NULL,
    model_weight REAL,
    mcs_status TEXT NOT NULL,
    candidate_registry_hash TEXT NOT NULL,
    model_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    threshold_version TEXT NOT NULL,
    source_id TEXT,
    source_hash TEXT,
    snapshot_hash TEXT,
    universe_hash TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,horizon,model_name,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);

CREATE TABLE IF NOT EXISTS field10_sample_split_validation (
    daily_snapshot_id TEXT NOT NULL,
    parent_run_id TEXT NOT NULL,
    child_run_id TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    broker_day TEXT NOT NULL,
    horizon INTEGER NOT NULL CHECK(horizon IN (1,3,6,12,24,36)),
    completed_broker_candle TEXT NOT NULL,
    model_name TEXT NOT NULL,
    split_id TEXT NOT NULL,
    training_start TEXT,
    training_end TEXT,
    validation_start TEXT,
    validation_end TEXT,
    test_start TEXT,
    test_end TEXT,
    out_of_sample_loss REAL,
    calibration_error REAL,
    coverage_error REAL,
    net_expected_value_error REAL,
    split_rank REAL,
    split_pass INTEGER NOT NULL DEFAULT 0,
    purge_hours INTEGER NOT NULL,
    embargo_hours INTEGER NOT NULL,
    candidate_registered_before_test INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    threshold_version TEXT NOT NULL,
    source_id TEXT,
    source_hash TEXT,
    snapshot_hash TEXT,
    universe_hash TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,horizon,model_name,split_id,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);

CREATE TABLE IF NOT EXISTS field10_rank_components_v2 (
    daily_snapshot_id TEXT NOT NULL,
    parent_run_id TEXT NOT NULL,
    child_run_id TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    broker_day TEXT NOT NULL,
    horizon INTEGER NOT NULL DEFAULT 0,
    completed_broker_candle TEXT NOT NULL,
    component_name TEXT NOT NULL,
    raw_value REAL,
    normalized_score REAL,
    configured_weight REAL,
    duplicate_penalty REAL,
    effective_weight REAL,
    weighted_contribution REAL,
    shadow_score REAL,
    shadow_rank INTEGER,
    production_rank INTEGER,
    locked_bias TEXT,
    entry_permission TEXT,
    managed_utility_6h REAL,
    managed_utility_12h REAL,
    expected_shortfall_95 REAL,
    transition_risk_6h REAL,
    bad_connectedness REAL,
    persistent_connectedness REAL,
    volatility_safety REAL,
    mcs_status TEXT,
    split_robustness REAL,
    reliability REAL,
    data_quality REAL,
    rank_evidence_fraction REAL,
    promotion_status TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    model_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    threshold_version TEXT NOT NULL,
    source_id TEXT,
    source_hash TEXT,
    snapshot_hash TEXT,
    universe_hash TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    validation_status TEXT NOT NULL,
    missing_reason TEXT,
    created_system_time TEXT NOT NULL,
    PRIMARY KEY(daily_snapshot_id,symbol,component_name,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_rank_v2_snapshot ON field10_rank_components_v2(daily_snapshot_id,shadow_rank,symbol);
"""

TABLES = (
    "field10_horizon_volatility_shadow", "field10_semivariance_shadow", "field10_gas_state_shadow",
    "field10_tail_risk_shadow", "field10_copula_shadow", "field10_connectedness_shadow",
    "field10_frequency_connectedness_shadow", "field10_model_confidence_set",
    "field10_sample_split_validation", "field10_rank_components_v2",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def checksum() -> str:
    return sha256(DDL.encode("utf-8")).hexdigest()


def parent_fingerprint(conn: sqlite3.Connection) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for table in ("field10_daily_snapshot", "field10_daily_snapshot_symbol"):
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY 1,2").fetchall()
        serial = [list(row) for row in rows]
        result[table] = {"row_count": len(rows), "sha256": sha256(json.dumps(serial, default=str, separators=(",", ":")).encode()).hexdigest()}
    return result


def create_backup(db: Path, backup_dir: Path | None = None) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination_dir = backup_dir or db.parent / "backups"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{db.stem}.pre_{MIGRATION_ID}.{stamp}{db.suffix}"
    shutil.copy2(db, destination)
    return destination


def immutable_trigger_sql(table: str) -> str:
    return f"""
    CREATE TRIGGER IF NOT EXISTS trg_{table}_no_update BEFORE UPDATE ON {table}
    BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS trg_{table}_no_delete BEFORE DELETE ON {table}
    BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END;
    """


def apply(db: Path, *, backup_dir: Path | None = None) -> dict[str, Any]:
    if not db.exists():
        raise FileNotFoundError(db)
    backup = create_backup(db, backup_dir)
    conn = sqlite3.connect(str(db), timeout=60.0)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=60000")
    before = parent_fingerprint(conn)
    migration_checksum = checksum()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.executescript(DDL)
        for table in TABLES:
            conn.executescript(immutable_trigger_sql(table))
        existing = conn.execute("SELECT checksum FROM schema_migrations WHERE migration_id=?", (MIGRATION_ID,)).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO schema_migrations(migration_id,checksum,description,applied_at_utc) VALUES(?,?,?,?)",
                (MIGRATION_ID, migration_checksum, DESCRIPTION, utc_now()),
            )
        elif str(existing[0]) != migration_checksum:
            raise RuntimeError("migration checksum mismatch")
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    after = parent_fingerprint(conn)
    foreign_key_errors = [list(row) for row in conn.execute("PRAGMA foreign_key_check")]
    integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    present = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing = sorted(set(TABLES) - present)
    migration_rows = int(conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE migration_id=?", (MIGRATION_ID,)).fetchone()[0])
    conn.close()
    if before != after:
        raise RuntimeError("authoritative parent snapshot rows changed during migration")
    if integrity.lower() != "ok" or foreign_key_errors or missing or migration_rows != 1:
        raise RuntimeError(f"migration verification failed: integrity={integrity}, fk={foreign_key_errors}, missing={missing}, migration_rows={migration_rows}")
    return {
        "migration_id": MIGRATION_ID,
        "database": str(db.resolve()),
        "backup": str(backup.resolve()),
        "checksum": migration_checksum,
        "parent_before": before,
        "parent_after": after,
        "integrity_check": integrity,
        "foreign_key_errors": foreign_key_errors,
        "tables": list(TABLES),
        "idempotent_registry_row_count": migration_rows,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()
    report = apply(args.db.resolve(), backup_dir=None if args.backup_dir is None else args.backup_dir.resolve())
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
