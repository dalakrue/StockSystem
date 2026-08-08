"""Atomic, column-projecting history evidence store.

Every logical history is a separate SQLite table.  The tables share one identity
contract but remain physically independent so Field 4A, Field 4B, prediction,
regime, and AI evidence are never merged into one opaque blob.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from core.history_identity_20260620 import IDENTITY_COLUMNS, history_record_key, validate_history_time
from core.generation_identity_20260707 import numeric_generation
from services.canonical_snapshot_store import DB_PATH


@dataclass(frozen=True)
class HistorySpec:
    name: str
    field: str
    workspace: str
    grain: str
    business_key: str
    description: str


SPECS: tuple[HistorySpec, ...] = (
    HistorySpec("full_metric_overall_history", "FIELD_1", "FULL_METRIC", "one row per canonical completed H1 generation", "calculation_id", "Overall Full Metric 25-day evidence"),
    HistorySpec("protected_decision_history", "FIELD_1", "FULL_METRIC", "one row per protected decision per canonical generation", "calculation_id + condition", "Ten protected decision histories"),
    HistorySpec("decision11_support_history", "FIELD_1", "FULL_METRIC", "one row per canonical generation", "calculation_id", "Decision 11 medium-standard support"),
    HistorySpec("decision_change_audit_history", "FIELD_1", "FULL_METRIC", "one row per consecutive canonical generation comparison", "calculation_id", "Decision changes without formula mutation"),
    HistorySpec("input_data_quality_history", "FIELD_1", "FULL_METRIC", "one row per canonical generation", "calculation_id", "Input quality and rejected-row evidence"),
    HistorySpec("metric_availability_history", "FIELD_1", "FULL_METRIC", "one row per metric per canonical generation", "calculation_id + condition", "Metric availability and missing values"),

    HistorySpec("powerbi_prediction_ledger", "FIELD_2", "POWER_BI", "one row per forecast origin and H+1..H+6", "calculation_id + horizon", "Prediction, actual, residual, interval, settlement"),
    HistorySpec("powerbi_source_path_history", "FIELD_2", "POWER_BI", "one row per protected source path and horizon", "calculation_id + condition + horizon", "Original red/yellow/blue or named source paths"),
    HistorySpec("powerbi_reconciled_path_history", "FIELD_2", "POWER_BI", "one row per displayed reconciled horizon", "calculation_id + horizon", "MinT-style display-only path and delta"),
    HistorySpec("powerbi_forecast_settlement_history", "FIELD_2", "POWER_BI", "one row per settled target", "calculation_id + target_time + horizon", "Coverage and TP/SL/ambiguous settlement evidence"),

    HistorySpec("regime_overall_history", "FIELD_3", "REGIME", "one row per canonical completed H1 generation", "calculation_id", "Overall regime history"),
    HistorySpec("regime_standard_history", "FIELD_3", "REGIME", "one row per standard level per generation", "calculation_id + condition", "Lower, medium and higher regime standards"),
    HistorySpec("regime_changepoint_history", "FIELD_3", "REGIME", "one row per detected changepoint and signal", "calculation_id + condition + record_time", "PELT changepoint evidence"),
    HistorySpec("regime_duration_history", "FIELD_3", "REGIME", "one row per regime segment or generation", "calculation_id + condition", "Regime duration evidence"),
    HistorySpec("regime_transition_reliability_history", "FIELD_3", "REGIME", "one row per generation", "calculation_id", "Transition probability and reliability"),
    HistorySpec("regime_alpha_delta_history", "FIELD_3", "REGIME", "one row per generation", "calculation_id", "Regime alpha, delta and acceleration"),
    HistorySpec("regime_conflict_history", "FIELD_3", "REGIME", "one row per conflict component per generation", "calculation_id + condition", "Regime disagreement and conflict"),

    HistorySpec("similar_day_query_history", "FIELD_4A", "SIMILAR_DAY", "one row per current-query generation and window", "calculation_id + condition", "Similar-Day query identity and constraints"),
    HistorySpec("similar_day_ranked_match_history", "FIELD_4A", "SIMILAR_DAY", "one row per ranked match", "calculation_id + condition + rank_value", "Rank, distance and compatibility"),
    HistorySpec("similar_day_outcome_history", "FIELD_4A", "SIMILAR_DAY", "one row per ranked match and outcome horizon", "calculation_id + condition + horizon + rank_value", "Historical H+1/H+2/H+3/H+6 outcomes and excursions"),
    HistorySpec("motif_history", "FIELD_4A", "SIMILAR_DAY", "one row per motif match", "calculation_id + condition + rank_value", "Matrix Profile motif metadata"),
    HistorySpec("discord_history", "FIELD_4A", "SIMILAR_DAY", "one row per discord window", "calculation_id + condition", "Matrix Profile discord/anomaly metadata"),
    HistorySpec("match_quality_calibration_history", "FIELD_4A", "SIMILAR_DAY", "one row per generation and window", "calculation_id + condition", "Similarity quality calibration"),

    HistorySpec("canonical_priority_history", "FIELD_4B", "COMBINED_LOGIC", "one row per priority candidate per generation", "calculation_id + rank_value + record_time", "Canonical priority history"),
    HistorySpec("knn_rank_history", "FIELD_4B", "COMBINED_LOGIC", "one row per KNN-ranked candidate", "calculation_id + rank_value + record_time", "KNN rank evidence"),
    HistorySpec("greedy_rank_history", "FIELD_4B", "COMBINED_LOGIC", "one row per Greedy-ranked candidate", "calculation_id + rank_value + record_time", "Greedy rank evidence"),
    HistorySpec("reliability_conflict_history", "FIELD_4B", "COMBINED_LOGIC", "one row per component per generation", "calculation_id + condition", "Reliability and conflict evidence"),
    HistorySpec("component_availability_history", "FIELD_4B", "COMBINED_LOGIC", "one row per component per generation", "calculation_id + condition", "Component presence and staleness"),
    HistorySpec("combined_evidence_explanation_history", "FIELD_4B", "COMBINED_LOGIC", "one row per generation", "calculation_id", "Combined evidence explanation"),
    HistorySpec("canonical_generation_change_history", "FIELD_4B", "COMBINED_LOGIC", "one row per consecutive generation comparison", "calculation_id", "Changes between canonical generations"),

    HistorySpec("ai_assistant_history", "FIELD_5", "AI_ASSISTANT", "one row per user question/assistant answer pair", "calculation_id + record_key", "Question, answer, grounding and consistency"),
    HistorySpec("ai_evidence_reference_history", "FIELD_5", "AI_ASSISTANT", "one row per referenced evidence item", "calculation_id + record_key", "Evidence tables and row references"),
    HistorySpec("ai_answer_consistency_history", "FIELD_5", "AI_ASSISTANT", "one row per answered question", "calculation_id + record_key", "Answer consistency and unsupported warning"),

    HistorySpec("combined_sentiment_technical_decision_history", "FIELD_6", "QUANT_HISTORY", "one row per canonical generation", "calculation_id", "Preserved combined sentiment, technical and protected-decision evidence"),
    HistorySpec("broker_time_synchronization_audit_history", "FIELD_6", "QUANT_HISTORY", "one row per canonical generation and table", "calculation_id + condition", "Broker-time watermark and timestamp-contract audit"),
    HistorySpec("cross_table_generation_consistency_history", "FIELD_6", "QUANT_HISTORY", "one row per canonical generation and table", "calculation_id + condition", "Cross-table calculation/generation identity consistency"),
    HistorySpec("forecast_coverage_calibration_history", "FIELD_6", "QUANT_HISTORY", "one row per horizon and settled calibration window", "calculation_id + horizon", "Conformal forecast coverage evidence"),
    HistorySpec("adaptive_coverage_controller_history", "FIELD_6", "QUANT_HISTORY", "one row per horizon and controller update", "calculation_id + horizon", "Adaptive conformal coverage feedback evidence"),
    HistorySpec("market_changepoint_drift_history", "FIELD_6", "QUANT_HISTORY", "one row per generation and detected change", "calculation_id + condition", "Bayesian/change-point and drift metadata"),
    HistorySpec("conditional_model_skill_history", "FIELD_6", "QUANT_HISTORY", "one row per model/condition/horizon", "calculation_id + condition + horizon", "Conditional predictive ability metadata"),
    HistorySpec("research_rule_spa_validation_history", "FIELD_6", "QUANT_HISTORY", "one row per candidate rule/model", "calculation_id + condition", "Hansen SPA research-rule validation metadata"),
    HistorySpec("execution_cost_trade_feasibility_history", "FIELD_6", "QUANT_HISTORY", "one row per generation/horizon", "calculation_id + horizon", "Execution cost versus expected-move feasibility"),
    HistorySpec("ai_evidence_retrieval_answer_audit_history", "FIELD_6", "QUANT_HISTORY", "one row per AI answer", "calculation_id + record_key", "AI evidence retrieval and answer provenance audit"),
    HistorySpec("ai_risk_coverage_abstention_history", "FIELD_6", "QUANT_HISTORY", "one row per AI answer", "calculation_id + record_key", "AI risk-coverage and selective abstention history"),
    HistorySpec("decision_outcome_settlement_history", "FIELD_6", "QUANT_HISTORY", "one row per settled decision/horizon", "calculation_id + target_time + horizon", "Decision outcome and settlement evidence"),

    HistorySpec("cache_diagnostics_history", "SYSTEM", "PERFORMANCE", "one row per cache diagnostic snapshot", "calculation_id + condition", "Hit, miss, admission and eviction history"),
    HistorySpec("performance_history", "SYSTEM", "PERFORMANCE", "one row per timed renderer/stage", "calculation_id + condition + created_at", "Duration, rows, payload, Python allocation and RSS"),
)

SPEC_BY_NAME = {spec.name: spec for spec in SPECS}
_MEMORY_FALLBACK: dict[str, list[dict[str, Any]]] = {}

COMMON_DB_COLUMNS = (
    "record_key", *IDENTITY_COLUMNS,
    "metric_name", "value_numeric", "value_text", "rank_value",
    "lower_value", "median_value", "upper_value", "actual_value", "residual_value",
    "coverage_flag", "tab_name", "renderer_name", "row_count", "browser_rows",
    "payload_bytes", "duration_ms", "python_allocation_bytes", "rss_mb",
    "cache_status", "payload_json",
)


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def ensure_history_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS history_catalog(
          table_name TEXT PRIMARY KEY, field_name TEXT NOT NULL, workspace TEXT NOT NULL,
          grain TEXT NOT NULL, business_key TEXT NOT NULL, description TEXT NOT NULL,
          schema_version TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS history_watermarks(
          table_name TEXT PRIMARY KEY, latest_completed_h1 TEXT, last_calculation_id TEXT,
          last_generation INTEGER, data_signature TEXT, updated_at TEXT NOT NULL);
        """
    )
    columns_sql = """
        record_key TEXT PRIMARY KEY,
        calculation_id TEXT NOT NULL,
        calculation_generation INTEGER NOT NULL,
        run_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        source TEXT NOT NULL,
        latest_completed_h1 TEXT NOT NULL,
        record_time TEXT,
        target_time TEXT,
        horizon INTEGER,
        data_signature TEXT,
        logic_version TEXT NOT NULL,
        condition TEXT,
        sample_count INTEGER,
        settled_status TEXT NOT NULL,
        is_revision INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        metric_name TEXT,
        value_numeric REAL,
        value_text TEXT,
        rank_value INTEGER,
        lower_value REAL,
        median_value REAL,
        upper_value REAL,
        actual_value REAL,
        residual_value REAL,
        coverage_flag INTEGER,
        tab_name TEXT,
        renderer_name TEXT,
        row_count INTEGER,
        browser_rows INTEGER,
        payload_bytes INTEGER,
        duration_ms REAL,
        python_allocation_bytes INTEGER,
        rss_mb REAL,
        cache_status TEXT,
        payload_json TEXT NOT NULL
    """
    for spec in SPECS:
        conn.execute(f"CREATE TABLE IF NOT EXISTS {_quote(spec.name)}({columns_sql})")
        # Additive, reversible schema evolution for databases created by v1.0.0.
        existing_columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({_quote(spec.name)})").fetchall()}
        additive_columns = {
            "tab_name": "TEXT",
            "renderer_name": "TEXT",
            "row_count": "INTEGER",
            "python_allocation_bytes": "INTEGER",
        }
        for column_name, column_type in additive_columns.items():
            if column_name not in existing_columns:
                conn.execute(f"ALTER TABLE {_quote(spec.name)} ADD COLUMN {_quote(column_name)} {column_type}")
        conn.execute(f"CREATE INDEX IF NOT EXISTS {_quote('idx_'+spec.name+'_latest')} ON {_quote(spec.name)}(latest_completed_h1 DESC, calculation_generation DESC)")
        conn.execute(f"CREATE INDEX IF NOT EXISTS {_quote('idx_'+spec.name+'_calc')} ON {_quote(spec.name)}(calculation_id, horizon, condition)")
        conn.execute(f"CREATE INDEX IF NOT EXISTS {_quote('idx_'+spec.name+'_identity')} ON {_quote(spec.name)}(symbol, timeframe, calculation_generation DESC)")
        conn.execute(
            "INSERT OR REPLACE INTO history_catalog(table_name,field_name,workspace,grain,business_key,description,schema_version) VALUES(?,?,?,?,?,?,?)",
            (spec.name, spec.field, spec.workspace, spec.grain, spec.business_key, spec.description, "history-evidence-1.0.0"),
        )


def _normalize_row(table_name: str, row: Mapping[str, Any]) -> dict[str, Any]:
    if table_name not in SPEC_BY_NAME:
        raise KeyError(f"Unknown history table: {table_name}")
    identity = {name: row.get(name) for name in IDENTITY_COLUMNS}
    valid, reason = validate_history_time(identity)
    if not valid:
        raise ValueError(f"{table_name}: {reason}")
    payload = row.get("payload") if isinstance(row.get("payload"), Mapping) else row.get("payload_json")
    if isinstance(payload, str):
        try:
            payload_obj = json.loads(payload)
        except Exception:
            payload_obj = {"value": payload}
    elif isinstance(payload, Mapping):
        payload_obj = dict(payload)
    else:
        payload_obj = {}
    normalized = {name: row.get(name) for name in COMMON_DB_COLUMNS}
    normalized["record_key"] = str(row.get("record_key") or history_record_key(table_name, identity, payload_obj))
    normalized["payload_json"] = json.dumps(payload_obj, ensure_ascii=False, default=str, separators=(",", ":"))
    normalized["is_revision"] = 1 if bool(row.get("is_revision")) else 0
    normalized["coverage_flag"] = None if row.get("coverage_flag") is None else (1 if bool(row.get("coverage_flag")) else 0)
    normalized["calculation_generation"] = numeric_generation(row.get("calculation_generation") or row.get("generation_id"), default=1)
    normalized["settled_status"] = str(row.get("settled_status") or "UNSETTLED")
    return normalized


def insert_history_bundle(conn: sqlite3.Connection, bundle: Mapping[str, Iterable[Mapping[str, Any]]]) -> dict[str, Any]:
    """Insert all affected history tables inside the caller's transaction."""
    ensure_history_schema(conn)
    results: dict[str, Any] = {}
    placeholders = ",".join("?" for _ in COMMON_DB_COLUMNS)
    columns = ",".join(_quote(name) for name in COMMON_DB_COLUMNS)
    for table_name, rows in bundle.items():
        if table_name not in SPEC_BY_NAME:
            continue
        inserted = 0
        ignored = 0
        latest: dict[str, Any] | None = None
        for raw in rows or []:
            row = _normalize_row(table_name, raw)
            values = [row.get(name) for name in COMMON_DB_COLUMNS]
            before = conn.total_changes
            conn.execute(f"INSERT OR IGNORE INTO {_quote(table_name)}({columns}) VALUES({placeholders})", values)
            if conn.total_changes > before:
                inserted += 1
            else:
                ignored += 1
            latest = row
        if latest:
            conn.execute(
                "INSERT OR REPLACE INTO history_watermarks(table_name,latest_completed_h1,last_calculation_id,last_generation,data_signature,updated_at) VALUES(?,?,?,?,?,?)",
                (table_name, latest.get("latest_completed_h1"), latest.get("calculation_id"), latest.get("calculation_generation"), latest.get("data_signature"), latest.get("created_at")),
            )
        results[table_name] = {"inserted": inserted, "idempotent_ignored": ignored}
    return results


def append_history_bundle(bundle: Mapping[str, Iterable[Mapping[str, Any]]], *, db_path: Path | str = DB_PATH, retries: int = 3) -> dict[str, Any]:
    """Atomic append with bounded SQLite-lock retries and labelled memory fallback."""
    last_error: Exception | None = None
    for attempt in range(max(1, int(retries))):
        conn = sqlite3.connect(str(db_path), timeout=10, check_same_thread=False)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("BEGIN IMMEDIATE")
            result = insert_history_bundle(conn, bundle)
            conn.commit()
            for table_result in result.values():
                if isinstance(table_result, dict):
                    table_result["storage_status"] = "SQLITE"
            return result
        except sqlite3.OperationalError as exc:
            conn.rollback()
            last_error = exc
            if "locked" not in str(exc).lower() and "busy" not in str(exc).lower() and "readonly" not in str(exc).lower():
                raise
            time.sleep(0.08 * (attempt + 1))
        except Exception as exc:
            conn.rollback()
            last_error = exc
            if "readonly" not in str(exc).lower():
                raise
            break
        finally:
            conn.close()
    # Compact bounded in-process fallback.  It is explicit and never presented
    # as durable storage.
    for table_name, rows in bundle.items():
        if table_name not in SPEC_BY_NAME:
            continue
        bucket = _MEMORY_FALLBACK.setdefault(table_name, [])
        for row in rows or []:
            try:
                bucket.append(_normalize_row(table_name, row))
            except Exception:
                continue
        del bucket[:-500]
    error_text = f"{type(last_error).__name__}: {last_error}" if last_error else "persistent storage unavailable"
    fallback_result: dict[str, Any] = {}
    for table_name in bundle:
        if table_name in SPEC_BY_NAME:
            fallback_result[table_name] = {
                "inserted": 0,
                "idempotent_ignored": 0,
                "storage_status": "MEMORY_FALLBACK",
                "memory_records": len(_MEMORY_FALLBACK.get(table_name, [])),
                "error": error_text,
            }
    return fallback_result


def query_history(
    table_name: str,
    *,
    columns: Sequence[str] | None = None,
    limit: int = 100,
    offset: int = 0,
    calculation_id: str | None = None,
    db_path: Path | str = DB_PATH,
) -> pd.DataFrame:
    if table_name not in SPEC_BY_NAME:
        return pd.DataFrame()
    selected = [name for name in (columns or COMMON_DB_COLUMNS) if name in COMMON_DB_COLUMNS]
    if not selected:
        return pd.DataFrame()
    sql = f"SELECT {','.join(_quote(name) for name in selected)} FROM {_quote(table_name)}"
    params: list[Any] = []
    if calculation_id:
        sql += " WHERE calculation_id=?"
        params.append(str(calculation_id))
    sql += " ORDER BY latest_completed_h1 DESC, record_time DESC, created_at DESC LIMIT ? OFFSET ?"
    params.extend([max(1, min(int(limit), 500)), max(0, int(offset))])
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    try:
        ensure_history_schema(conn)
        frame = pd.read_sql_query(sql, conn, params=params)
    except sqlite3.Error:
        frame = pd.DataFrame()
    finally:
        conn.close()
    if frame.empty and table_name in _MEMORY_FALLBACK:
        rows = list(reversed(_MEMORY_FALLBACK.get(table_name, [])))
        if calculation_id:
            rows = [row for row in rows if str(row.get("calculation_id")) == str(calculation_id)]
        frame = pd.DataFrame(rows[offset: offset + max(1, min(int(limit), 500))])
        if not frame.empty:
            frame = frame.loc[:, [c for c in selected if c in frame.columns]]
    return frame


def export_history(table_name: str, *, db_path: Path | str = DB_PATH) -> pd.DataFrame:
    if table_name not in SPEC_BY_NAME:
        return pd.DataFrame()
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    try:
        ensure_history_schema(conn)
        return pd.read_sql_query(
            f"SELECT * FROM {_quote(table_name)} ORDER BY latest_completed_h1 DESC, record_time DESC, created_at DESC",
            conn,
        )
    finally:
        conn.close()


def catalog_frame(*, field: str | None = None) -> pd.DataFrame:
    rows = [spec.__dict__ for spec in SPECS if not field or spec.field == field]
    return pd.DataFrame(rows)


def validate_no_future_rows(*, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    try:
        ensure_history_schema(conn)
        for spec in SPECS:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {_quote(spec.name)} WHERE record_time > latest_completed_h1 OR (settled_status IN ('SETTLED','OBSERVED','COMPLETED') AND target_time > latest_completed_h1)"
            ).fetchone()[0]
            if count:
                violations.append({"table": spec.name, "violations": int(count)})
    finally:
        conn.close()
    return violations


__all__ = [
    "HistorySpec", "SPECS", "SPEC_BY_NAME", "COMMON_DB_COLUMNS", "ensure_history_schema",
    "insert_history_bundle", "append_history_bundle", "query_history", "export_history",
    "catalog_frame", "validate_no_future_rows",
]
