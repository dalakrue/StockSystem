"""SQLite persistence for immutable CRCEF-SV research publications.

The store is additive.  It never edits protected production decisions or
canonical snapshots.  Every table is created with IF NOT EXISTS so an empty
installation can be initialized safely.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

DEFAULT_DB_PATH = Path("data") / "crcef_sv_research.sqlite3"

DDL = (
    """CREATE TABLE IF NOT EXISTS canonical_snapshots (
        run_id TEXT NOT NULL, generation_id TEXT NOT NULL, symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL, completed_broker_candle TEXT NOT NULL,
        source_snapshot_hash TEXT NOT NULL, source_signature TEXT NOT NULL,
        payload_json TEXT NOT NULL, created_at_broker_time TEXT NOT NULL,
        PRIMARY KEY (run_id, generation_id, symbol, timeframe, completed_broker_candle)
    )""",
    """CREATE TABLE IF NOT EXISTS research_results (
        run_id TEXT NOT NULL, generation_id TEXT NOT NULL, symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL, completed_broker_candle TEXT NOT NULL,
        model_name TEXT NOT NULL, model_version TEXT NOT NULL,
        source_snapshot_hash TEXT NOT NULL, input_feature_hash TEXT NOT NULL,
        status TEXT NOT NULL, reason TEXT NOT NULL, sample_size INTEGER NOT NULL,
        quality_flags_json TEXT NOT NULL, payload_json TEXT NOT NULL,
        created_at_broker_time TEXT NOT NULL,
        PRIMARY KEY (run_id, generation_id, symbol, timeframe,
                     completed_broker_candle, model_name, model_version)
    )""",
    """CREATE TABLE IF NOT EXISTS research_model_registry (
        model_name TEXT NOT NULL, model_version TEXT NOT NULL,
        training_window TEXT, input_schema_hash TEXT, artifact_path TEXT,
        status TEXT NOT NULL, metadata_json TEXT NOT NULL,
        created_at_broker_time TEXT NOT NULL,
        PRIMARY KEY (model_name, model_version)
    )""",
    """CREATE TABLE IF NOT EXISTS research_validation_runs (
        validation_id TEXT PRIMARY KEY, run_id TEXT, generation_id TEXT,
        model_name TEXT NOT NULL, model_version TEXT NOT NULL,
        validation_method TEXT NOT NULL, payload_json TEXT NOT NULL,
        status TEXT NOT NULL, created_at_broker_time TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS calibration_models (
        model_name TEXT NOT NULL, model_version TEXT NOT NULL,
        regime TEXT NOT NULL DEFAULT '', forecast_horizon TEXT NOT NULL DEFAULT '',
        training_window TEXT, calibration_window TEXT, test_window TEXT,
        method TEXT NOT NULL, metrics_json TEXT NOT NULL, artifact_path TEXT,
        created_at_broker_time TEXT NOT NULL,
        PRIMARY KEY (model_name, model_version, regime, forecast_horizon)
    )""",
    """CREATE TABLE IF NOT EXISTS drift_events (
        event_id TEXT PRIMARY KEY, run_id TEXT, generation_id TEXT,
        monitor_name TEXT NOT NULL, affected_model TEXT NOT NULL,
        drift_start_candle TEXT, detection_candle TEXT NOT NULL,
        magnitude REAL, payload_json TEXT NOT NULL, created_at_broker_time TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS prediction_intervals (
        run_id TEXT NOT NULL, generation_id TEXT NOT NULL, symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL, completed_broker_candle TEXT NOT NULL,
        model_name TEXT NOT NULL, model_version TEXT NOT NULL,
        forecast_horizon TEXT NOT NULL, point_prediction REAL,
        lower_bound REAL, upper_bound REAL, target_coverage REAL,
        realized_coverage REAL, payload_json TEXT NOT NULL,
        PRIMARY KEY (run_id, generation_id, symbol, timeframe,
                     completed_broker_candle, model_name, model_version, forecast_horizon)
    )""",
    """CREATE TABLE IF NOT EXISTS prediction_outcomes (
        run_id TEXT NOT NULL, generation_id TEXT NOT NULL, symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL, completed_broker_candle TEXT NOT NULL,
        model_name TEXT NOT NULL, model_version TEXT NOT NULL,
        forecast_horizon TEXT NOT NULL, target_candle TEXT,
        actual_value REAL, realized_return REAL, settled INTEGER NOT NULL DEFAULT 0,
        settlement_timestamp TEXT, payload_json TEXT NOT NULL,
        PRIMARY KEY (run_id, generation_id, symbol, timeframe,
                     completed_broker_candle, model_name, model_version, forecast_horizon)
    )""",
    """CREATE TABLE IF NOT EXISTS event_memory (
        event_id TEXT PRIMARY KEY, event_time TEXT NOT NULL, headline_hash TEXT NOT NULL,
        normalized_title_hash TEXT NOT NULL, duplicate_status TEXT NOT NULL,
        primary_entity TEXT, eurusd_relevance REAL, embedding_json TEXT,
        payload_json TEXT NOT NULL, created_at_broker_time TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS event_responses (
        event_id TEXT NOT NULL, forecast_horizon TEXT NOT NULL,
        target_candle TEXT, realized_return REAL, settled INTEGER NOT NULL DEFAULT 0,
        payload_json TEXT NOT NULL, PRIMARY KEY (event_id, forecast_horizon)
    )""",
    """CREATE TABLE IF NOT EXISTS promotion_decisions (
        decision_id TEXT PRIMARY KEY, model_name TEXT NOT NULL,
        model_version TEXT NOT NULL, validation_run_id TEXT,
        promotion_status TEXT NOT NULL, reason TEXT NOT NULL,
        payload_json TEXT NOT NULL, created_at_broker_time TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS research_audit (
        run_id TEXT NOT NULL, generation_id TEXT NOT NULL,
        broker_candle TEXT NOT NULL, module TEXT NOT NULL,
        model_version TEXT NOT NULL, input_hash TEXT NOT NULL,
        output_hash TEXT NOT NULL, data_window TEXT, sample_size INTEGER NOT NULL,
        status TEXT NOT NULL, warnings_json TEXT NOT NULL,
        runtime_seconds REAL, peak_memory_mb REAL,
        validation_status TEXT NOT NULL, promotion_status TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        PRIMARY KEY (run_id, generation_id, broker_candle, module, model_version)
    )""",
)


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    try:
        return value.item()
    except Exception:
        return str(value)


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=_json_default, separators=(",", ":"))


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def initialize_database(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    path = Path(db_path)
    with connect(path) as connection:
        for statement in DDL:
            connection.execute(statement)
        connection.commit()
    return path


def store_canonical_snapshot(identity: Mapping[str, Any], payload: Mapping[str, Any], *, db_path: str | Path = DEFAULT_DB_PATH) -> bool:
    initialize_database(db_path)
    row = (
        str(identity["run_id"]), str(identity["generation_id"]), str(identity["symbol"]),
        str(identity["timeframe"]), str(identity["completed_broker_candle"]),
        str(identity["source_snapshot_hash"]), str(identity["source_signature"]),
        dumps(payload), str(identity["completed_broker_candle"]),
    )
    with connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO canonical_snapshots VALUES (?,?,?,?,?,?,?,?,?)", row
        )
        connection.commit()
        return cursor.rowcount > 0


def store_research_result(result: Mapping[str, Any], *, db_path: str | Path = DEFAULT_DB_PATH) -> bool:
    initialize_database(db_path)
    payload = result.get("payload") if isinstance(result.get("payload"), Mapping) else result
    row = (
        str(result.get("run_id") or ""), str(result.get("generation_id") or ""),
        str(result.get("symbol") or ""), str(result.get("timeframe") or ""),
        str(result.get("completed_broker_candle") or ""), str(result.get("model_name") or "CRCEF-SV"),
        str(result.get("model_version") or "CRCEF-SV-1.0.0"), str(result.get("source_snapshot_hash") or ""),
        str(result.get("input_feature_hash") or ""), str(result.get("status") or "RESEARCH_ONLY"),
        str(result.get("reason") or ""), int(result.get("sample_size") or 0),
        dumps(result.get("quality_flags") or []), dumps(payload),
        str(result.get("created_at_broker_time") or result.get("completed_broker_candle") or ""),
    )
    with connect(db_path) as connection:
        cursor = connection.execute(
            """INSERT OR IGNORE INTO research_results
            (run_id,generation_id,symbol,timeframe,completed_broker_candle,model_name,
             model_version,source_snapshot_hash,input_feature_hash,status,reason,sample_size,
             quality_flags_json,payload_json,created_at_broker_time)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", row,
        )
        connection.commit()
        return cursor.rowcount > 0


def store_audit_row(row: Mapping[str, Any], *, db_path: str | Path = DEFAULT_DB_PATH) -> bool:
    initialize_database(db_path)
    values = (
        str(row.get("run_id") or ""), str(row.get("generation_id") or ""),
        str(row.get("broker_candle") or ""), str(row.get("module") or ""),
        str(row.get("model_version") or ""), str(row.get("input_hash") or ""),
        str(row.get("output_hash") or ""), str(row.get("data_window") or ""),
        int(row.get("sample_size") or 0), str(row.get("status") or "RESEARCH_ONLY"),
        dumps(row.get("warnings") or []), row.get("runtime_seconds"), row.get("peak_memory_mb"),
        str(row.get("validation_status") or "NOT_RUN"), str(row.get("promotion_status") or "RESEARCH_ONLY"),
        dumps(row),
    )
    with connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO research_audit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values
        )
        connection.commit()
        return cursor.rowcount > 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize CRCEF-SV research persistence")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()
    path = initialize_database(args.db)
    print(f"Initialized CRCEF-SV database: {path}")


if __name__ == "__main__":
    main()
