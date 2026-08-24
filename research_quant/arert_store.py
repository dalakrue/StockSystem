"""Isolated persistence for the ARERT academic research layer.

The database is deliberately separate from the protected production database.
Migrations are additive (`CREATE TABLE IF NOT EXISTS`) and never drop, rename,
or rewrite an existing production table.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import sqlite3
from typing import Any, Mapping

DEFAULT_DB_PATH = Path(os.getenv("ARERT_RESEARCH_DB_PATH", "data/arert_research.sqlite3"))

TABLES = (
    "research_runs",
    "research_feature_snapshots",
    "research_regime_duration",
    "research_changepoints",
    "research_jumps",
    "research_conformal_forecasts",
    "research_meta_labels",
    "research_model_weights",
    "research_analogues",
    "research_behavioral_scores",
    "research_event_responses",
    "research_information_scores",
    "research_validation_results",
    "research_arert_scores",
)

MODULE_TABLE = {
    1: "research_regime_duration",
    2: "research_regime_duration",
    3: "research_changepoints",
    4: "research_jumps",
    5: "research_conformal_forecasts",
    6: "research_conformal_forecasts",
    7: "research_meta_labels",
    8: "research_meta_labels",
    9: "research_model_weights",
    10: "research_model_weights",
    11: "research_analogues",
    12: "research_analogues",
    13: "research_behavioral_scores",
    14: "research_behavioral_scores",
    15: "research_behavioral_scores",
    16: "research_model_weights",
    17: "research_event_responses",
    18: "research_information_scores",
    19: "research_validation_results",
    20: "research_arert_scores",
}


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return str(value)


def _connection(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = Path(path or DEFAULT_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def migrate_arert_database(path: str | Path | None = None) -> dict[str, Any]:
    """Create additive ARERT tables and indexes; preserve every existing table."""
    conn = _connection(path)
    try:
        before = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in TABLES:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_key TEXT NOT NULL UNIQUE,
                    run_id TEXT,
                    generation_id TEXT,
                    broker_candle TEXT,
                    symbol TEXT,
                    timeframe TEXT,
                    research_version TEXT NOT NULL,
                    module_number INTEGER,
                    module_status TEXT,
                    created_timestamp TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_identity ON {table}(symbol, timeframe, broker_candle)")
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_run ON {table}(run_id, generation_id)")
        conn.commit()
        after = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {
            "ok": True,
            "database_path": str(Path(path or DEFAULT_DB_PATH)),
            "tables_created": sorted((after - before) & set(TABLES)),
            "existing_tables_preserved": sorted(before),
            "research_tables": list(TABLES),
        }
    finally:
        conn.close()


def _insert(conn: sqlite3.Connection, table: str, payload: Mapping[str, Any], *, module_number: int | None = None) -> None:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
    broker_candle = str(metadata.get("completed_broker_candle") or "")
    run_id = str(metadata.get("run_id") or "")
    generation_id = str(metadata.get("generation_id") or "")
    research_version = str(metadata.get("research_model_version") or payload.get("model_version") or "UNKNOWN")
    created = str(metadata.get("calculation_timestamp") or "")
    record_key = "|".join([
        table, run_id, generation_id, broker_candle,
        str(module_number or payload.get("module_number") or 0),
        str(payload.get("output_hash") or payload.get("parameter_version") or research_version),
    ])
    conn.execute(
        f"""
        INSERT INTO {table} (
            record_key, run_id, generation_id, broker_candle, symbol, timeframe,
            research_version, module_number, module_status, created_timestamp, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(record_key) DO UPDATE SET
            module_status=excluded.module_status,
            created_timestamp=excluded.created_timestamp,
            payload_json=excluded.payload_json
        """,
        (
            record_key, run_id, generation_id, broker_candle,
            str(metadata.get("symbol") or ""), str(metadata.get("timeframe") or ""),
            research_version, module_number,
            str(payload.get("status") or ""), created,
            json.dumps(payload, sort_keys=True, default=_json_default),
        ),
    )


def persist_arert_envelope(envelope: Mapping[str, Any], path: str | Path | None = None) -> dict[str, Any]:
    migration = migrate_arert_database(path)
    conn = _connection(path)
    persisted: list[dict[str, Any]] = []
    try:
        _insert(conn, "research_runs", envelope, module_number=0)
        _insert(conn, "research_feature_snapshots", envelope, module_number=0)
        modules = envelope.get("modules") if isinstance(envelope.get("modules"), Mapping) else {}
        for raw_number, payload in modules.items():
            if not isinstance(payload, Mapping):
                continue
            try:
                number = int(raw_number)
            except Exception:
                continue
            table = MODULE_TABLE.get(number)
            if not table:
                continue
            _insert(conn, table, payload, module_number=number)
            persisted.append({"module": number, "table": table, "status": payload.get("status")})
        conn.commit()
        return {
            "ok": True,
            "database_path": str(Path(path or DEFAULT_DB_PATH)),
            "migration": migration,
            "persisted": persisted,
            "production_database_modified": False,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def table_counts(path: str | Path | None = None) -> dict[str, int]:
    migrate_arert_database(path)
    conn = _connection(path)
    try:
        return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in TABLES}
    finally:
        conn.close()


__all__ = [
    "DEFAULT_DB_PATH", "TABLES", "MODULE_TABLE", "migrate_arert_database",
    "persist_arert_envelope", "table_counts",
]
