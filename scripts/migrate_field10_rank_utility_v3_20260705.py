#!/usr/bin/env python3
"""Backup-first idempotent migration for Field 10 rank utility v3."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import shutil
import sqlite3
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.multi_symbol_field10_20260701 import DB_PATH

MIGRATION_ID = "20260705_field10_rank_utility_v3_research_candidate_v1"
DESCRIPTION = "Append-only Field 10 v3 calibration, breaks, rank uncertainty, clusters, PBO, components and promotion governance"
DEFAULT_DB = Path(DB_PATH)

IDENTITY = """
    daily_snapshot_id TEXT NOT NULL,
    parent_run_id TEXT NOT NULL,
    child_run_id TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    broker_day TEXT NOT NULL,
    completed_broker_candle TEXT NOT NULL,
"""
VERSIONS = """
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
    created_system_time TEXT NOT NULL
"""

DDL = f"""
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    description TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS field10_probability_calibration_v2 (
{IDENTITY}
    horizon INTEGER NOT NULL CHECK(horizon IN (1,3,6,12,24,36)),
    direction TEXT NOT NULL,
    raw_probability REAL,
    calibrated_probability REAL,
    calibration_method TEXT NOT NULL,
    brier_score REAL,
    log_loss REAL,
    expected_calibration_error REAL,
    calibration_slope REAL,
    calibration_intercept REAL,
    calibration_sample_count INTEGER NOT NULL DEFAULT 0,
    test_sample_count INTEGER NOT NULL DEFAULT 0,
    calibration_permission TEXT NOT NULL,
    purge_hours INTEGER NOT NULL,
    embargo_hours INTEGER NOT NULL,
    final_test_used_for_fit INTEGER NOT NULL DEFAULT 0 CHECK(final_test_used_for_fit IN (0,1)),
    conformal_lower_return REAL,
    conformal_median_return REAL,
    conformal_upper_return REAL,
    conformal_interval_width REAL,
    conformal_coverage REAL,
    reliability_bins_json TEXT NOT NULL,
    settled_forecast_count INTEGER NOT NULL DEFAULT 0,
    settlement_status TEXT NOT NULL,
{VERSIONS},
    PRIMARY KEY(daily_snapshot_id,symbol,horizon,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_cal_v2_snapshot ON field10_probability_calibration_v2(daily_snapshot_id,symbol,horizon);
CREATE INDEX IF NOT EXISTS idx_f10_cal_v2_settlement ON field10_probability_calibration_v2(settlement_status,symbol,horizon,completed_broker_candle);

CREATE TABLE IF NOT EXISTS field10_structural_break_v2 (
{IDENTITY}
    last_structural_break_time TEXT,
    break_strength REAL,
    post_break_h1_count INTEGER,
    pre_post_distribution_distance REAL,
    current_regime_probability REAL,
    second_regime_probability REAL,
    regime_entropy REAL,
    regime_persistence REAL,
    structural_entry_permission TEXT NOT NULL,
    actionable_rank_permission TEXT NOT NULL,
    feature_breaks_json TEXT NOT NULL,
{VERSIONS},
    PRIMARY KEY(daily_snapshot_id,symbol,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_break_v2_snapshot ON field10_structural_break_v2(daily_snapshot_id,symbol);
CREATE INDEX IF NOT EXISTS idx_f10_break_v2_permission ON field10_structural_break_v2(structural_entry_permission,break_strength,post_break_h1_count);

CREATE TABLE IF NOT EXISTS field10_rank_uncertainty (
{IDENTITY}
    median_bootstrap_rank REAL,
    rank_lower_90 REAL,
    rank_upper_90 REAL,
    probability_rank_1 REAL,
    probability_top_3 REAL,
    probability_top_4 REAL,
    rank_standard_deviation REAL,
    top_3_membership_stability REAL,
    rank_turnover_risk REAL,
    rank_confidence_status TEXT NOT NULL,
    bootstrap_method TEXT NOT NULL,
    block_length INTEGER NOT NULL,
    bootstrap_seed INTEGER NOT NULL,
    bootstrap_draw_count INTEGER NOT NULL,
    sample_count INTEGER NOT NULL,
{VERSIONS},
    PRIMARY KEY(daily_snapshot_id,symbol,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_rank_unc_snapshot ON field10_rank_uncertainty(daily_snapshot_id,probability_top_3 DESC,symbol);

CREATE TABLE IF NOT EXISTS field10_evidence_clusters (
{IDENTITY}
    component_name TEXT NOT NULL,
    cluster_id TEXT NOT NULL,
    configured_weight REAL NOT NULL,
    cluster_budget REAL NOT NULL,
    effective_weight REAL NOT NULL,
    duplicate_penalty REAL NOT NULL,
    effective_number_independent REAL,
    dependence_threshold REAL NOT NULL,
{VERSIONS},
    PRIMARY KEY(daily_snapshot_id,symbol,component_name,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_evidence_cluster_snapshot ON field10_evidence_clusters(daily_snapshot_id,cluster_id,symbol);

CREATE TABLE IF NOT EXISTS field10_candidate_experiments (
{IDENTITY}
    candidate_name TEXT NOT NULL,
    experiment_registry_hash TEXT NOT NULL,
    registered_before_test INTEGER NOT NULL CHECK(registered_before_test IN (0,1)),
    frozen_registry_json TEXT NOT NULL,
    candidate_count INTEGER NOT NULL,
{VERSIONS},
    PRIMARY KEY(daily_snapshot_id,experiment_registry_hash),
    FOREIGN KEY(daily_snapshot_id) REFERENCES field10_daily_snapshot(daily_snapshot_id)
);
CREATE INDEX IF NOT EXISTS idx_f10_experiment_snapshot ON field10_candidate_experiments(daily_snapshot_id,candidate_name);

CREATE TABLE IF NOT EXISTS field10_pbo_results (
{IDENTITY}
    experiment_registry_hash TEXT NOT NULL,
    pbo_probability REAL,
    oos_rank_logit REAL,
    in_sample_winner TEXT,
    out_of_sample_rank REAL,
    performance_degradation REAL,
    number_of_candidates INTEGER,
    promotion_permission TEXT NOT NULL,
{VERSIONS},
    PRIMARY KEY(daily_snapshot_id,experiment_registry_hash,model_version),
    FOREIGN KEY(daily_snapshot_id) REFERENCES field10_daily_snapshot(daily_snapshot_id)
);
CREATE INDEX IF NOT EXISTS idx_f10_pbo_snapshot ON field10_pbo_results(daily_snapshot_id,pbo_probability);

CREATE TABLE IF NOT EXISTS field10_rank_components_v3 (
{IDENTITY}
    horizon INTEGER NOT NULL DEFAULT 0 CHECK(horizon IN (0,1,3,6,12,24,36)),
    component_name TEXT NOT NULL,
    raw_value REAL,
    historical_quality_score REAL,
    cross_sectional_percentile REAL,
    normalized_component_score REAL,
    configured_weight REAL,
    cluster_id TEXT,
    cluster_budget REAL,
    effective_weight REAL,
    weighted_contribution REAL,
    evidence_coverage REAL,
    evidence_penalty REAL,
    raw_research_score REAL,
    coverage_adjusted_score REAL,
    research_rank INTEGER,
    diversification_adjusted_rank INTEGER,
    production_rank INTEGER,
    locked_bias TEXT,
    entry_permission TEXT NOT NULL,
    probability_top_3 REAL,
    rank_lower_90 REAL,
    rank_upper_90 REAL,
    expected_return_3h REAL,
    expected_return_6h REAL,
    expected_shortfall_6h REAL,
    transition_risk_6h REAL,
    reliability REAL,
    data_quality REAL,
    fallback_level TEXT NOT NULL,
    promotion_status TEXT NOT NULL,
    formula_contributions_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
{VERSIONS},
    PRIMARY KEY(daily_snapshot_id,symbol,component_name,model_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_rank_v3_snapshot ON field10_rank_components_v3(daily_snapshot_id,research_rank,symbol);
CREATE INDEX IF NOT EXISTS idx_f10_rank_v3_permission ON field10_rank_components_v3(entry_permission,evidence_coverage,symbol);

CREATE TABLE IF NOT EXISTS field10_promotion_decisions (
{IDENTITY}
    decision TEXT NOT NULL,
    decision_version TEXT NOT NULL,
    decision_reason TEXT NOT NULL,
    all_gates_pass INTEGER NOT NULL CHECK(all_gates_pass IN (0,1)),
    explicit_decision_present INTEGER NOT NULL CHECK(explicit_decision_present IN (0,1)),
    gate_results_json TEXT NOT NULL,
    production_rank_before INTEGER,
    production_rank_after INTEGER,
    locked_bias_before TEXT,
    locked_bias_after TEXT,
{VERSIONS},
    PRIMARY KEY(daily_snapshot_id,symbol,decision_version),
    FOREIGN KEY(daily_snapshot_id,symbol) REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_f10_promotion_snapshot ON field10_promotion_decisions(daily_snapshot_id,decision,symbol);
"""

TABLES = (
    "field10_probability_calibration_v2", "field10_structural_break_v2", "field10_rank_uncertainty",
    "field10_evidence_clusters", "field10_candidate_experiments", "field10_pbo_results",
    "field10_rank_components_v3", "field10_promotion_decisions",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def checksum() -> str:
    return sha256(DDL.encode("utf-8")).hexdigest()


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    names = [str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {name: int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]) for name in names}


def authoritative_fingerprint(conn: sqlite3.Connection) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for table in ("field10_daily_snapshot", "field10_daily_snapshot_symbol"):
        rows = [list(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1,2")]
        output[table] = {"row_count": len(rows), "sha256": sha256(json.dumps(rows, default=str, separators=(",", ":")).encode()).hexdigest()}
    return output


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
    before_counts = table_counts(conn)
    before_authority = authoritative_fingerprint(conn)
    migration_checksum = checksum()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.executescript(DDL)
        for table in TABLES:
            conn.executescript(immutable_trigger_sql(table))
        existing = conn.execute("SELECT checksum FROM schema_migrations WHERE migration_id=?", (MIGRATION_ID,)).fetchone()
        if existing is None:
            conn.execute("INSERT INTO schema_migrations(migration_id,checksum,description,applied_at_utc) VALUES(?,?,?,?)",
                         (MIGRATION_ID, migration_checksum, DESCRIPTION, utc_now()))
        elif str(existing[0]) != migration_checksum:
            raise RuntimeError("migration checksum mismatch")
        conn.commit()
    except Exception:
        conn.rollback(); conn.close(); raise
    after_counts = table_counts(conn)
    after_authority = authoritative_fingerprint(conn)
    preserved = {name: {"before": count, "after": after_counts.get(name, 0), "preserved": after_counts.get(name, 0) >= count}
                 for name, count in before_counts.items()}
    foreign_key_errors = [list(row) for row in conn.execute("PRAGMA foreign_key_check")]
    integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    present = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing = sorted(set(TABLES) - present)
    migration_rows = int(conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE migration_id=?", (MIGRATION_ID,)).fetchone()[0])
    conn.close()
    if before_authority != after_authority:
        raise RuntimeError("authoritative production snapshot fingerprint changed")
    if any(not item["preserved"] for item in preserved.values()):
        raise RuntimeError("one or more existing table row counts decreased")
    if integrity.lower() != "ok" or foreign_key_errors or missing or migration_rows != 1:
        raise RuntimeError(f"verification failed: integrity={integrity}, fk={foreign_key_errors}, missing={missing}, rows={migration_rows}")
    return {
        "migration_id": MIGRATION_ID, "database": str(db.resolve()), "backup": str(backup.resolve()),
        "checksum": migration_checksum, "authoritative_before": before_authority, "authoritative_after": after_authority,
        "row_count_preservation": preserved, "integrity_check": integrity, "foreign_key_errors": foreign_key_errors,
        "tables": list(TABLES), "idempotent_registry_row_count": migration_rows, "status": "PASS",
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
    raise SystemExit(main())
