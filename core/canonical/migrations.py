"""Idempotent, non-destructive research schema migration."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DB_PATH = PROJECT_ROOT / "data" / "research_v11.sqlite3"

_TABLES = {
    "canonical_runs": """CREATE TABLE IF NOT EXISTS canonical_runs(
        run_id TEXT PRIMARY KEY, broker_candle_time TEXT NOT NULL, symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL, snapshot_hash TEXT, created_at_utc TEXT NOT NULL)""",
    "prediction_outcomes": """CREATE TABLE IF NOT EXISTS prediction_outcomes(
        run_id TEXT NOT NULL, horizon_hours INTEGER NOT NULL, settled_outcome TEXT,
        realized_pips REAL, actual_price REAL, settled_at_utc TEXT,
        PRIMARY KEY(run_id,horizon_hours))""",
    "research_horizon_results": """CREATE TABLE IF NOT EXISTS research_horizon_results(
        run_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL, horizon_hours INTEGER NOT NULL, gate_status TEXT NOT NULL,
        forecastability REAL, coverage REAL, coverage_status TEXT, raw_prediction REAL,
        corrected_prediction REAL, forecast_bias REAL, nominal_ev REAL, robust_ev REAL,
        tail_risk TEXT, model_agreement REAL, sample_size INTEGER, details_json TEXT NOT NULL,
        PRIMARY KEY(run_id,horizon_hours))""",
    "research_model_confidence": """CREATE TABLE IF NOT EXISTS research_model_confidence(
        run_id TEXT NOT NULL, model_name TEXT NOT NULL, eligibility TEXT NOT NULL,
        loss_score REAL, evidence_count INTEGER, details_json TEXT NOT NULL,
        PRIMARY KEY(run_id,model_name))""",
    "research_conformal_history": """CREATE TABLE IF NOT EXISTS research_conformal_history(
        run_id TEXT NOT NULL, horizon_hours INTEGER NOT NULL, target_coverage REAL,
        actual_coverage REAL, interval_width REAL, coverage_debt REAL,
        consecutive_violations INTEGER, status TEXT, details_json TEXT NOT NULL,
        PRIMARY KEY(run_id,horizon_hours))""",
    "research_changepoints": """CREATE TABLE IF NOT EXISTS research_changepoints(
        run_id TEXT PRIMARY KEY, change_probability REAL, direction_shift_probability REAL,
        volatility_shift_probability REAL, safe_horizon_hours INTEGER, status TEXT,
        details_json TEXT NOT NULL)""",
    "research_mfe_mae": """CREATE TABLE IF NOT EXISTS research_mfe_mae(
        run_id TEXT NOT NULL, horizon_hours INTEGER NOT NULL, mfe_pips REAL, mae_pips REAL,
        sample_size INTEGER, details_json TEXT NOT NULL, PRIMARY KEY(run_id,horizon_hours))""",
    "research_entry_delay": """CREATE TABLE IF NOT EXISTS research_entry_delay(
        run_id TEXT NOT NULL, delay_name TEXT NOT NULL, win_rate REAL, net_ev REAL,
        mae REAL, missed_trade_rate REAL, evidence_count INTEGER, details_json TEXT NOT NULL,
        PRIMARY KEY(run_id,delay_name))""",
    "research_overfitting_ledger": """CREATE TABLE IF NOT EXISTS research_overfitting_ledger(
        run_id TEXT PRIMARY KEY, models_tested INTEGER, thresholds_tested INTEGER,
        feature_combinations INTEGER, horizons_tested INTEGER, tp_sl_alternatives INTEGER,
        in_sample_score REAL, out_of_sample_score REAL, degradation REAL,
        overfitting_risk TEXT, production_eligibility TEXT, details_json TEXT NOT NULL)""",
    "research_promotion_ledger": """CREATE TABLE IF NOT EXISTS research_promotion_ledger(
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, model_name TEXT NOT NULL,
        action TEXT NOT NULL, reason TEXT, created_at_utc TEXT NOT NULL)""",
    "research_run_summary": """CREATE TABLE IF NOT EXISTS research_run_summary(
        run_id TEXT PRIMARY KEY, broker_candle_time TEXT NOT NULL, symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL, canonical_decision TEXT NOT NULL,
        research_approved_action TEXT NOT NULL, research_status TEXT NOT NULL,
        research_trust_score REAL, risk_multiplier REAL, summary_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL)""",
    "research_run_snapshot_v12": """CREATE TABLE IF NOT EXISTS research_run_snapshot_v12(
        run_id TEXT PRIMARY KEY, calculation_generation TEXT NOT NULL, snapshot_hash TEXT NOT NULL UNIQUE,
        broker_time TEXT NOT NULL, candle_time TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
        settled_outcome_cutoff TEXT NOT NULL, source_hashes_json TEXT NOT NULL, configuration_hash TEXT NOT NULL,
        schema_version TEXT NOT NULL, module_statuses_json TEXT NOT NULL, sample_sizes_json TEXT NOT NULL,
        warnings_json TEXT NOT NULL, compact_results_json TEXT NOT NULL, full_results_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL, UNIQUE(run_id,calculation_generation))""",
}


def migrate_research_database(path: Path | str = RESEARCH_DB_PATH) -> dict[str, Any]:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    with sqlite3.connect(str(db_path), timeout=15) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        for name, ddl in _TABLES.items():
            conn.execute(ddl)
            created.append(name)
        indexes = (
            "CREATE INDEX IF NOT EXISTS idx_rrs_broker_time ON research_run_summary(broker_candle_time DESC)",
            "CREATE INDEX IF NOT EXISTS idx_rrs_symbol_tf ON research_run_summary(symbol,timeframe)",
            "CREATE INDEX IF NOT EXISTS idx_rhr_run ON research_horizon_results(run_id)",
            "CREATE INDEX IF NOT EXISTS idx_rhr_broker_time ON research_horizon_results(broker_candle_time DESC)",
            "CREATE INDEX IF NOT EXISTS idx_rhr_symbol_tf_horizon ON research_horizon_results(symbol,timeframe,horizon_hours)",
            "CREATE INDEX IF NOT EXISTS idx_outcome_run_horizon ON prediction_outcomes(run_id,horizon_hours)",
            "CREATE INDEX IF NOT EXISTS idx_promotion_run ON research_promotion_ledger(run_id)",
            "CREATE INDEX IF NOT EXISTS idx_v12_symbol_time ON research_run_snapshot_v12(symbol,timeframe,candle_time DESC)",
            "CREATE INDEX IF NOT EXISTS idx_v12_generation ON research_run_snapshot_v12(calculation_generation)",
        )
        for statement in indexes:
            conn.execute(statement)
        conn.commit()
    return {"ok": True, "path": str(db_path), "tables": created, "destructive": False}


def migrate_field10_rank_evidence_20260704(path: Path | str | None = None) -> dict[str, Any]:
    """Run the canonical additive Field 10 migration through one registry entry.

    The delayed import avoids coupling the research database bootstrap to the
    multi-symbol database at module import time.
    """
    from core.field10_unified_migration_20260703 import migrate_and_verify_field10
    from core.multi_symbol_field10_20260701 import DB_PATH as FIELD10_DB_PATH

    return migrate_and_verify_field10(path or FIELD10_DB_PATH)
