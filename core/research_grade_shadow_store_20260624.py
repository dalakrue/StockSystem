"""Immutable SQLite persistence for research-grade shadow evidence."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import sqlite3

SCHEMA_VERSION = "research-grade-shadow-store-1.0"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS research_grade_shadow_snapshot (
            run_id TEXT PRIMARY KEY,
            generation_id TEXT NOT NULL,
            origin_candle_time TEXT NOT NULL,
            snapshot_hash TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            model_version TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS research_grade_shadow_origin (
            run_id TEXT NOT NULL,
            model_id TEXT NOT NULL,
            horizon INTEGER NOT NULL,
            origin_time TEXT NOT NULL,
            origin_price REAL,
            mean REAL,
            median REAL,
            lower REAL,
            upper REAL,
            direction_probability REAL,
            origin_regime TEXT,
            origin_features_json TEXT NOT NULL,
            model_version TEXT NOT NULL,
            shadow_only INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            PRIMARY KEY (model_id, horizon, origin_time, model_version)
        );
        CREATE INDEX IF NOT EXISTS idx_rg_shadow_origin_run
            ON research_grade_shadow_origin(run_id, horizon, origin_time);
        CREATE TABLE IF NOT EXISTS research_grade_shadow_score (
            run_id TEXT NOT NULL,
            model_id TEXT NOT NULL,
            horizon INTEGER NOT NULL,
            sample_count INTEGER NOT NULL,
            crps REAL,
            crps_method TEXT,
            mae REAL,
            rmse REAL,
            directional_accuracy REAL,
            log_score REAL,
            interval_score REAL,
            interval_coverage REAL,
            interval_width REAL,
            coverage_debt REAL,
            score_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (run_id, model_id, horizon)
        );
        CREATE TABLE IF NOT EXISTS research_grade_promotion_report (
            run_id TEXT NOT NULL,
            model_id TEXT NOT NULL,
            promotion_eligible INTEGER NOT NULL,
            automatic_promotion_enabled INTEGER NOT NULL,
            blockers_json TEXT NOT NULL,
            leakage_tests TEXT NOT NULL,
            causality_tests TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (run_id, model_id)
        );
        """
    )
    conn.commit()


def save(conn: sqlite3.Connection, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Persist without overwriting historical origin forecasts."""
    ensure_schema(conn)
    now = datetime.now(timezone.utc).isoformat()
    run_id = str(payload.get("run_id") or "")
    if not run_id:
        return {"ok": False, "reason": "RUN_ID_REQUIRED"}
    conn.execute(
        """INSERT OR IGNORE INTO research_grade_shadow_snapshot
        (run_id,generation_id,origin_candle_time,snapshot_hash,schema_version,model_version,payload_json,created_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (
            run_id, str(payload.get("generation_id") or run_id),
            str(payload.get("origin_candle_time") or ""), str(payload.get("snapshot_hash") or ""),
            str(payload.get("schema_version") or ""), str(payload.get("model_version") or ""),
            _json(payload), now,
        ),
    )
    inserted_origins = 0
    for row in payload.get("origin_records") or []:
        before = conn.total_changes
        conn.execute(
            """INSERT OR IGNORE INTO research_grade_shadow_origin
            (run_id,model_id,horizon,origin_time,origin_price,mean,median,lower,upper,
             direction_probability,origin_regime,origin_features_json,model_version,shadow_only,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id, str(row.get("model_id") or ""), int(row.get("horizon") or 0),
                str(row.get("origin_time") or ""), row.get("origin_price"), row.get("mean"),
                row.get("median"), row.get("lower"), row.get("upper"),
                row.get("direction_probability"), str(row.get("origin_regime") or "UNKNOWN"),
                _json(row.get("origin_features") or {}), str(row.get("model_version") or payload.get("model_version") or ""),
                1, now,
            ),
        )
        inserted_origins += int(conn.total_changes > before)
    for model_id, cards in (payload.get("scorecards") or {}).items():
        if not isinstance(cards, Mapping):
            continue
        for horizon, score in cards.items():
            if not isinstance(score, Mapping):
                continue
            conn.execute(
                """INSERT OR REPLACE INTO research_grade_shadow_score
                (run_id,model_id,horizon,sample_count,crps,crps_method,mae,rmse,directional_accuracy,
                 log_score,interval_score,interval_coverage,interval_width,coverage_debt,score_json,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, str(model_id), int(horizon), int(score.get("sample_count") or 0),
                    score.get("crps"), str(score.get("crps_method") or "UNAVAILABLE"), score.get("mae"),
                    score.get("rmse"), score.get("directional_accuracy"), score.get("log_score"),
                    score.get("interval_score"), score.get("interval_coverage"), score.get("interval_width"),
                    score.get("coverage_debt"), _json(score), now,
                ),
            )
    for report in (payload.get("promotion_eligibility") or {}).get("models") or []:
        conn.execute(
            """INSERT OR REPLACE INTO research_grade_promotion_report
            (run_id,model_id,promotion_eligible,automatic_promotion_enabled,blockers_json,
             leakage_tests,causality_tests,created_at) VALUES (?,?,?,?,?,?,?,?)""",
            (
                run_id, str(report.get("model_id") or ""), int(bool(report.get("promotion_eligible"))),
                int(bool(report.get("automatic_promotion_enabled"))), _json(report.get("blockers") or []),
                str(report.get("leakage_tests") or "UNKNOWN"), str(report.get("causality_tests") or "UNKNOWN"), now,
            ),
        )
    conn.commit()
    return {
        "ok": True, "run_id": run_id, "inserted_origin_records": inserted_origins,
        "origin_records_total": conn.execute("SELECT COUNT(*) FROM research_grade_shadow_origin").fetchone()[0],
        "snapshot_rows": conn.execute("SELECT COUNT(*) FROM research_grade_shadow_snapshot").fetchone()[0],
        "schema_version": SCHEMA_VERSION,
    }


def load_latest(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_schema(conn)
    row = conn.execute(
        "SELECT payload_json FROM research_grade_shadow_snapshot ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    return json.loads(row[0]) if row else {}


__all__ = ["ensure_schema", "save", "load_latest", "SCHEMA_VERSION"]
