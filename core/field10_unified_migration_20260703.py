"""Idempotent Field 10 schema/data migration and synchronization verification.

The migration keeps one canonical schema for Settings publication and Lunch
readers.  Expected-return columns are never filled with zero or scaled from a
shorter horizon.  Historical rows are backfilled only from persisted same-row
evidence or from the same symbol's local completed-H1 history when available.
"""
from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from core.multi_symbol_field10_20260701 import DB_PATH

MIGRATION_VERSION = "field10-crowd-final-unified-migration-20260704-v1"
_RETURN_COLUMNS = ("expected_return_12h", "expected_return_24h", "expected_return_36h")
_NEW_COLUMN_TYPES: dict[str, str] = {
    "transition_risk_6h": "REAL",
    "expected_value_6h": "REAL",
    "risk_adjusted_expected_value_6h": "REAL",
    "probability_profit_1h": "REAL",
    "probability_profit_6h": "REAL",
    "probability_profit_12h": "REAL",
    "probability_reach_ev_1h": "REAL",
    "probability_reach_ev_6h": "REAL",
    "probability_reach_ev_12h": "REAL",
    "ev_target_1h": "REAL",
    "ev_target_6h": "REAL",
    "ev_target_12h": "REAL",
    "tick_volume_12h": "REAL",
    "volume_12h_z": "REAL",
    "volume_source": "TEXT",
    "ev_model_version": "TEXT",
    "probability_calibration_status": "TEXT",
    "unexpected_situation_status": "TEXT",
    "unexpected_situation_severity": "REAL",
    "validation_permission": "TEXT",
    "evidence_sample_size": "INTEGER",
    "metric_provenance_json": "TEXT",
    "migration_version": "TEXT",
}
_REQUIRED: dict[str, tuple[str, ...]] = {
    "field10_hourly_quality": ("transition_risk_24h", *_RETURN_COLUMNS, *_NEW_COLUMN_TYPES),
    "field10_daily_higher_lock": ("transition_risk_24h", *_RETURN_COLUMNS, *_NEW_COLUMN_TYPES),
    "field10_daily_snapshot_symbol": ("transition_risk_24h", *_RETURN_COLUMNS, *_NEW_COLUMN_TYPES),
    "field10_integrated_evidence_history": ("transition_risk_24h", *_RETURN_COLUMNS, *_NEW_COLUMN_TYPES),
}
_DISPLAY_KEYS = {
    "transition_risk_24h": ("Transition Risk 24H", "Transition Probability 24H"),
    "expected_return_12h": ("Expected Return 12H (%)", "Expected Return 12H"),
    "expected_return_24h": ("Expected Return 24H (%)", "Expected Return 24H"),
    "expected_return_36h": ("Expected Return 36H (%)", "Expected Return 36H"),
}


def _pct(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    if 0.0 <= number <= 1.0:
        number *= 100.0
    return float(np.clip(number, 0.0, 100.0))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _risk24_from_risk6(value: Any) -> float | None:
    risk6 = _pct(value)
    if risk6 is None:
        return None
    probability = risk6 / 100.0
    return float((1.0 - (1.0 - probability) ** 4) * 100.0)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_20260704_columns(conn: sqlite3.Connection) -> dict[str, Any]:
    """Add the quant columns idempotently and create only compatible indexes."""
    before: dict[str, list[str]] = {}
    added: dict[str, list[str]] = {}
    for table in _REQUIRED:
        if not _table_exists(conn, table):
            continue
        existing = _columns(conn, table)
        before[table] = sorted(existing)
        added[table] = []
        for column, sql_type in _NEW_COLUMN_TYPES.items():
            if column not in existing:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}')
                added[table].append(column)
        if "migration_version" in _columns(conn, table):
            conn.execute(f'UPDATE "{table}" SET migration_version=? WHERE migration_version IS NULL', (MIGRATION_VERSION,))
    index_specs = {
        "idx_f10_hourly_symbol_broker_20260704": ("field10_hourly_quality", "symbol,broker_timestamp"),
        "idx_f10_hourly_parent_rank_20260704": ("field10_hourly_quality", "parent_run_id,rank"),
        "idx_f10_hourly_unexpected_20260704": ("field10_hourly_quality", "unexpected_situation_status"),
        "idx_f10_hourly_permission_20260704": ("field10_hourly_quality", "validation_permission"),
        "idx_f10_daily_broker_20260704": ("field10_daily_higher_lock", "broker_day"),
        "idx_f10_daily_unexpected_20260704": ("field10_daily_higher_lock", "unexpected_situation_status"),
        "idx_f10_daily_permission_20260704": ("field10_daily_higher_lock", "validation_permission"),
    }
    for name, (table, expression) in index_specs.items():
        wanted = {part.strip() for part in expression.split(",")}
        if _table_exists(conn, table) and wanted.issubset(_columns(conn, table)):
            conn.execute(f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}"({expression})')
    after = {table: sorted(_columns(conn, table)) for table in _REQUIRED if _table_exists(conn, table)}
    return {"before_schema": before, "after_schema": after, "added_columns": added}


def _payload_metric(payload: Mapping[str, Any], column: str) -> float | None:
    for key in _DISPLAY_KEYS[column]:
        value = _pct(payload.get(key)) if column == "transition_risk_24h" else _number(payload.get(key))
        if value is not None:
            return value
    return None


def _frame_for_exact_symbol(
    frame: pd.DataFrame, symbol: str, *, state: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Return evidence only when its instrument identity exactly matches."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    requested = str(symbol).strip().upper()
    normalized = {str(column).strip().lower().replace("_", " "): column for column in frame.columns}
    symbol_column = next(
        (normalized.get(name) for name in ("symbol", "instrument", "ticker", "pair") if normalized.get(name) is not None),
        None,
    )
    if symbol_column is not None:
        mask = frame[symbol_column].astype(str).str.strip().str.upper().eq(requested)
        return frame.loc[mask].copy()

    # A cache without a per-row symbol column is usable only when the saved
    # state itself has an explicit matching identity. Unknown identity is rejected.
    identities: list[str] = []
    if isinstance(state, Mapping):
        for key in (
            "calculation_symbol_20260702", "active_analysis_symbol_20260701",
            "selected_symbol", "symbol", "instrument", "ticker",
        ):
            value = state.get(key)
            if value is not None and str(value).strip():
                identities.append(str(value).strip().upper())
        for key in (
            "canonical_decision_result_20260617", "canonical_result_20260617",
            "last_valid_canonical_decision_result_20260617",
        ):
            nested = state.get(key)
            if isinstance(nested, Mapping):
                for nested_key in ("symbol", "instrument", "ticker"):
                    value = nested.get(nested_key)
                    if value is not None and str(value).strip():
                        identities.append(str(value).strip().upper())
    return frame.copy() if requested in identities else pd.DataFrame()


def _frame_through_cutoff(frame: pd.DataFrame, cutoff: Any) -> pd.DataFrame:
    """Apply an as-of completed-candle cutoff so historical migration is causal."""
    if not isinstance(frame, pd.DataFrame) or frame.empty or cutoff is None:
        return frame
    stamp = pd.to_datetime(cutoff, errors="coerce", utc=True)
    if pd.isna(stamp):
        return frame
    normalized = {str(column).strip().lower().replace("_", " "): column for column in frame.columns}
    time_column = next(
        (normalized.get(name) for name in ("broker candle time", "time", "datetime", "timestamp", "date") if normalized.get(name) is not None),
        None,
    )
    if time_column is not None:
        times = pd.to_datetime(frame[time_column], errors="coerce", utc=True)
    else:
        times = pd.to_datetime(frame.index, errors="coerce", utc=True)
    return frame.loc[times.notna() & times.le(stamp)].copy()


def _local_symbol_metrics(symbol: str, *, cutoff: Any = None) -> dict[str, float | None]:
    """Read exact same-symbol local H1 evidence through the row's causal cutoff."""
    frame = pd.DataFrame()
    try:
        from core.multi_symbol_field10_20260701 import _read_cache_payload, _resolved_cache_path, _source_frame

        cache_path = _resolved_cache_path(symbol)
        if cache_path.is_file():
            payload = _read_cache_payload(cache_path)
            state = payload.get("state") if isinstance(payload, Mapping) else None
            if isinstance(state, Mapping):
                frame = _frame_through_cutoff(
                    _frame_for_exact_symbol(_source_frame(state), symbol, state=state), cutoff
                )
    except Exception:
        frame = pd.DataFrame()

    if frame.empty:
        # Field 11 stores a bounded historical H1 index. It is a legitimate
        # offline fallback only when the file itself identifies the requested symbol.
        root = Path(__file__).resolve().parents[1]
        for candidate in sorted((root / "data" / "field11_similar_path_20260702").glob("*/ohlc.pkl.gz")):
            try:
                source = pd.read_pickle(candidate)
                source = _frame_through_cutoff(_frame_for_exact_symbol(source, symbol), cutoff)
                if not source.empty:
                    frame = source
                    break
            except Exception:
                continue

    if frame.empty:
        return {}
    try:
        from core.field10_adaptive_regime_metrics_20260702 import compute_adaptive_regime_metrics

        result = compute_adaptive_regime_metrics(frame, timeframe=state.get("timeframe") if isinstance(state, Mapping) else None)
    except Exception:
        return {}
    if not isinstance(result, Mapping) or not result.get("ok"):
        return {}
    return {
        "transition_risk_24h": _pct(result.get("transition_risk_24h")),
        "expected_return_12h": _number(result.get("expected_return_12h")),
        "expected_return_24h": _number(result.get("expected_return_24h")),
        "expected_return_36h": _number(result.get("expected_return_36h")),
    }


def _coalesce_missing(target: dict[str, float | None], source: Mapping[str, Any]) -> None:
    for column in ("transition_risk_24h", *_RETURN_COLUMNS):
        if target.get(column) is None:
            value = _pct(source.get(column)) if column == "transition_risk_24h" else _number(source.get(column))
            if value is not None:
                target[column] = value


def _backfill_snapshot_columns(conn: sqlite3.Connection) -> dict[str, int]:
    stats = {
        "snapshot_risk24": 0,
        "snapshot_return12": 0,
        "snapshot_return24": 0,
        "snapshot_return36": 0,
        "local_symbol_calculations": 0,
    }
    if not _table_exists(conn, "field10_daily_snapshot_symbol"):
        return stats
    rows = conn.execute(
        "SELECT daily_snapshot_id,broker_day,symbol,row_json,transition_risk_24h,"
        "expected_return_12h,expected_return_24h,expected_return_36h "
        "FROM field10_daily_snapshot_symbol"
    ).fetchall()
    local_cache: dict[tuple[str, str], dict[str, float | None]] = {}
    for snapshot_id, broker_day, symbol, row_json, risk24, return12, return24, return36 in rows:
        try:
            payload = json.loads(str(row_json or "{}"))
        except Exception:
            payload = {}
        stored = {
            "transition_risk_24h": _pct(risk24),
            "expected_return_12h": _number(return12),
            "expected_return_24h": _number(return24),
            "expected_return_36h": _number(return36),
        }
        values: dict[str, float | None] = {
            "transition_risk_24h": _payload_metric(payload, "transition_risk_24h"),
            "expected_return_12h": _payload_metric(payload, "expected_return_12h"),
            "expected_return_24h": _payload_metric(payload, "expected_return_24h"),
            "expected_return_36h": _payload_metric(payload, "expected_return_36h"),
        }
        _coalesce_missing(values, stored)
        if values["transition_risk_24h"] is None:
            values["transition_risk_24h"] = _risk24_from_risk6(
                payload.get("Transition Risk 6H", payload.get("Transition Probability 6H"))
            )

        if _table_exists(conn, "field10_daily_higher_lock"):
            legacy = conn.execute(
                "SELECT transition_risk_24h,expected_return_12h,expected_return_24h,"
                "expected_return_36h,higher_transition_risk FROM field10_daily_higher_lock "
                "WHERE broker_day=? AND symbol=?",
                (broker_day, symbol),
            ).fetchone()
            if legacy:
                _coalesce_missing(values, {
                    "transition_risk_24h": legacy[0], "expected_return_12h": legacy[1],
                    "expected_return_24h": legacy[2], "expected_return_36h": legacy[3],
                })
                if values["transition_risk_24h"] is None:
                    values["transition_risk_24h"] = _risk24_from_risk6(legacy[4])

        if _table_exists(conn, "field10_integrated_evidence_history"):
            integrated = conn.execute(
                "SELECT transition_risk_24h,expected_return_12h,expected_return_24h,expected_return_36h "
                "FROM field10_integrated_evidence_history WHERE symbol=? AND broker_date=? "
                "ORDER BY broker_timestamp DESC LIMIT 1",
                (symbol, broker_day),
            ).fetchone()
            if integrated:
                _coalesce_missing(values, {
                    "transition_risk_24h": integrated[0], "expected_return_12h": integrated[1],
                    "expected_return_24h": integrated[2], "expected_return_36h": integrated[3],
                })

        missing_returns = any(values[column] is None for column in _RETURN_COLUMNS)
        if missing_returns:
            cutoff = next((
                payload.get(key) for key in (
                    "Completed Broker Candle", "Completed Candle", "Latest Completed H1",
                    "latest_completed_h1", "completed_broker_candle",
                ) if payload.get(key) is not None
            ), None)
            if cutoff is None:
                cutoff = f"{broker_day}T23:59:59+00:00"
            cache_key = (str(symbol).upper(), str(pd.to_datetime(cutoff, errors="coerce", utc=True)))
            if cache_key not in local_cache:
                local_cache[cache_key] = _local_symbol_metrics(cache_key[0], cutoff=cutoff)
                if local_cache[cache_key]:
                    stats["local_symbol_calculations"] += 1
            _coalesce_missing(values, local_cache[cache_key])

        updates = {column: values[column] for column in values if stored[column] is None and values[column] is not None}
        if not updates:
            continue
        assignments = ",".join(f"{column}=?" for column in updates)
        conn.execute(
            f"UPDATE field10_daily_snapshot_symbol SET {assignments} WHERE daily_snapshot_id=? AND symbol=?",
            (*updates.values(), snapshot_id, symbol),
        )
        for column in updates:
            stats[{
                "transition_risk_24h": "snapshot_risk24",
                "expected_return_12h": "snapshot_return12",
                "expected_return_24h": "snapshot_return24",
                "expected_return_36h": "snapshot_return36",
            }[column]] += 1
    return stats


def _backfill_20260704_from_row_json(conn: sqlite3.Connection) -> dict[str, int]:
    """Copy only explicitly published same-row metrics into physical columns."""
    if not _table_exists(conn, "field10_daily_snapshot_symbol"):
        return {}
    mapping = {
        "transition_risk_6h": "Transition Risk 6H",
        "expected_value_6h": "Expected Value 6H (%)",
        "risk_adjusted_expected_value_6h": "Risk-Adjusted EV 6H (%)",
        "probability_profit_1h": "Probability of Profit 1H (%)",
        "probability_profit_6h": "Probability of Profit 6H (%)",
        "probability_profit_12h": "Probability of Profit 12H (%)",
        "probability_reach_ev_1h": "Probability Reach EV 1H (%)",
        "probability_reach_ev_6h": "Probability Reach EV 6H (%)",
        "probability_reach_ev_12h": "Probability Reach EV 12H (%)",
        "ev_target_1h": "EV Target 1H (%)", "ev_target_6h": "EV Target 6H (%)", "ev_target_12h": "EV Target 12H (%)",
        "tick_volume_12h": "Observed Tick Volume 12H", "volume_12h_z": "Volume 12H Z-Score",
        "volume_source": "Volume Data Source", "ev_model_version": "EV Model Version",
        "probability_calibration_status": "Probability Calibration Status",
        "unexpected_situation_status": "Unexpected Situation Status",
        "unexpected_situation_severity": "Unexpected Situation Severity",
        "validation_permission": "Validation Permission", "evidence_sample_size": "Evidence Sample Size",
    }
    stats = {column: 0 for column in mapping}
    rows = conn.execute("SELECT daily_snapshot_id,symbol,row_json FROM field10_daily_snapshot_symbol").fetchall()
    numeric = {column for column, sql_type in _NEW_COLUMN_TYPES.items() if sql_type in {"REAL", "INTEGER"}}
    for snapshot_id, symbol, raw in rows:
        try:
            payload = json.loads(str(raw or "{}"))
        except Exception:
            continue
        values: dict[str, Any] = {}
        for column, display in mapping.items():
            value = payload.get(display)
            if column in numeric:
                value = _number(value)
                if value is None:
                    continue
            elif value is None or str(value).strip() == "":
                continue
            values[column] = value
        explanation = payload.get("Explanation")
        if explanation:
            values["metric_provenance_json"] = str(explanation)
        values["migration_version"] = MIGRATION_VERSION
        if not values:
            continue
        assignments = ",".join(f'"{column}"=COALESCE("{column}",?)' for column in values)
        conn.execute(f'UPDATE field10_daily_snapshot_symbol SET {assignments} WHERE daily_snapshot_id=? AND symbol=?', (*values.values(), snapshot_id, symbol))
        for column in values:
            if column in stats: stats[column] += 1
    return stats


def _non_null_counts(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    report: dict[str, dict[str, int]] = {}
    for table, columns in _REQUIRED.items():
        if not _table_exists(conn, table):
            continue
        report[table] = {
            column: int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL").fetchone()[0])
            for column in columns if column in _columns(conn, table)
        }
    return report


def _sync_conflicts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Report only conflicting finite values for identical broker day/symbol."""
    conflicts: list[dict[str, Any]] = []
    if not (_table_exists(conn, "field10_daily_snapshot_symbol") and _table_exists(conn, "field10_daily_higher_lock")):
        return conflicts
    rows = conn.execute(
        "SELECT s.broker_day,s.symbol,s.expected_return_24h,s.expected_return_36h,"
        "d.expected_return_24h,d.expected_return_36h "
        "FROM field10_daily_snapshot_symbol s JOIN field10_daily_higher_lock d "
        "ON d.broker_day=s.broker_day AND d.symbol=s.symbol"
    ).fetchall()
    for day, symbol, s24, s36, d24, d36 in rows:
        for horizon, left, right in ((24, s24, d24), (36, s36, d36)):
            a, b = _number(left), _number(right)
            if a is not None and b is not None and not np.isclose(a, b, rtol=1e-9, atol=1e-9):
                conflicts.append({"broker_day": day, "symbol": symbol, "horizon": horizon, "snapshot": a, "daily": b})
    return conflicts


def migrate_and_verify_field10(path: Path | str = DB_PATH) -> dict[str, Any]:
    """Run every Field 10 migration, backfill real evidence, and verify one schema."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    from core.multi_symbol_field10_20260701 import migrate_database
    from core.field10_integrated_evidence_20260702 import migrate_integrated_evidence_database
    from core.field10_daily_snapshot_contract_20260702 import migrate_daily_snapshot_database
    from core.child_generation_contract_20260702 import migrate_child_publication_contract
    from core.field10_finnhub_sentiment_20260704 import migrate_finnhub_sentiment_database
    from core.field10_crowd_final_20260704 import migrate_crowd_final_database

    component_reports = [
        migrate_database(path),
        migrate_integrated_evidence_database(path),
        migrate_daily_snapshot_database(path),
        migrate_child_publication_contract(path),
        migrate_finnhub_sentiment_database(path),
        migrate_crowd_final_database(path),
    ]

    with sqlite3.connect(str(path), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=8000")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS field10_schema_migration_audit_20260703 (
                migration_id TEXT PRIMARY KEY,
                migration_version TEXT NOT NULL,
                status TEXT NOT NULL,
                details_json TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )"""
        )
        conn.execute("BEGIN IMMEDIATE")
        schema_audit = _ensure_20260704_columns(conn)
        backfill = _backfill_snapshot_columns(conn)
        backfill_20260704 = _backfill_20260704_from_row_json(conn)
        missing = {
            table: sorted(set(columns) - _columns(conn, table))
            for table, columns in _REQUIRED.items()
        }
        missing = {table: columns for table, columns in missing.items() if columns}
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_key_issues = conn.execute("PRAGMA foreign_key_check").fetchall()
        additional_tables = (
            "field10_daily_news_event_rank", "field10_news_event_outcome",
            "field10_daily_session_entry_map",
            "field10_daily_crowd_psychology_rank",
            "field10_daily_final_multi_symbol_rank",
            "field10_crowd_psychology_outcome",
            "field10_final_multi_symbol_outcome",
        )
        missing_tables = [table for table in additional_tables if not _table_exists(conn, table)]
        counts = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (*_REQUIRED.keys(), *additional_tables) if _table_exists(conn, table)
        }
        non_null = _non_null_counts(conn)
        conflicts = _sync_conflicts(conn)
        table_names = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        prohibited_rank_tables = sorted(
            name for name in table_names
            if name.lower() in {"field10_rank", "field10_rank_20260704", "field10_production_rank"}
        )
        required_index_fragments = {
            "field10_daily_crowd_psychology_rank": {
                "idx_f10_crowd_broker_day", "idx_f10_crowd_snapshot", "idx_f10_crowd_symbol",
                "idx_f10_crowd_publication", "idx_f10_crowd_completed",
            },
            "field10_daily_final_multi_symbol_rank": {
                "idx_f10_final_broker_day", "idx_f10_final_snapshot", "idx_f10_final_symbol",
                "idx_f10_final_publication", "idx_f10_final_lock", "idx_f10_final_completed",
            },
            "field10_daily_session_entry_map": {
                "idx_f10_session_snapshot", "idx_f10_session_broker_day",
            },
        }
        missing_indexes: dict[str, list[str]] = {}
        for table, expected in required_index_fragments.items():
            if not _table_exists(conn, table):
                missing_indexes[table] = sorted(expected)
                continue
            actual = {str(row[1]) for row in conn.execute(f'PRAGMA index_list("{table}")').fetchall()}
            absent = sorted(expected - actual)
            if absent:
                missing_indexes[table] = absent

        primary_key_issues: dict[str, list[str]] = {}
        expected_primary_keys = {
            "field10_daily_crowd_psychology_rank": ["daily_snapshot_id", "symbol"],
            "field10_daily_final_multi_symbol_rank": ["daily_snapshot_id", "symbol"],
            "field10_daily_session_entry_map": ["daily_snapshot_id", "symbol", "session_name"],
        }
        for table, expected in expected_primary_keys.items():
            if not _table_exists(conn, table):
                primary_key_issues[table] = expected
                continue
            info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            actual = [str(row[1]) for row in sorted((row for row in info if int(row[5] or 0) > 0), key=lambda row: int(row[5]))]
            if actual != expected:
                primary_key_issues[table] = actual

        secret_column_issues: dict[str, list[str]] = {}
        for table in table_names:
            columns = sorted(_columns(conn, table))
            bad = [column for column in columns if any(token in column.lower() for token in ("api_key", "password", "secret", "credential", "access_token"))]
            if bad:
                secret_column_issues[table] = bad
        ok = (
            not missing and not missing_tables and integrity.lower() == "ok"
            and not foreign_key_issues and not conflicts and not prohibited_rank_tables
            and not secret_column_issues and not missing_indexes and not primary_key_issues
        )
        details = {
            "required_columns": {k: list(v) for k, v in _REQUIRED.items()},
            "missing_columns": missing,
            "backfilled_rows": backfill,
            "backfilled_20260704_rows": backfill_20260704,
            "table_counts": counts,
            "non_null_counts": non_null,
            "sync_conflicts": conflicts,
            "integrity_check": integrity,
            "foreign_key_issue_count": len(foreign_key_issues),
            "component_reports": component_reports,
            "schema_audit": schema_audit,
            "missing_required_tables": missing_tables,
            "prohibited_rank_tables": prohibited_rank_tables,
            "duplicate_rank_table_created": bool(prohibited_rank_tables),
            "secret_column_issues": secret_column_issues,
            "missing_required_indexes": missing_indexes,
            "primary_key_issues": primary_key_issues,
            "crowd_final_schema_verified": not missing_tables and not missing_indexes and not primary_key_issues and not secret_column_issues,
            "finnhub_news_schema_verified": not missing_tables and not secret_column_issues,
        }
        applied_at = pd.Timestamp.now(tz="UTC").isoformat()
        migration_id = sha256(
            f"{MIGRATION_VERSION}|{path.resolve()}|{json.dumps(details, sort_keys=True, default=str)}".encode()
        ).hexdigest()
        conn.execute(
            "INSERT OR REPLACE INTO field10_schema_migration_audit_20260703 "
            "(migration_id,migration_version,status,details_json,applied_at) VALUES(?,?,?,?,?)",
            (migration_id, MIGRATION_VERSION, "PASS" if ok else "FAIL", json.dumps(details, sort_keys=True, default=str), applied_at),
        )
        conn.commit()

    return {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "path": str(path),
        "migration_version": MIGRATION_VERSION,
        "missing_columns": missing,
        "backfilled_rows": backfill,
        "backfilled_20260704_rows": backfill_20260704,
        "table_counts": counts,
        "non_null_counts": non_null,
        "sync_conflict_count": len(conflicts),
        "integrity_check": integrity,
        "foreign_key_issue_count": len(foreign_key_issues),
        "schema_audit": schema_audit,
        "missing_required_tables": missing_tables,
        "prohibited_rank_tables": prohibited_rank_tables,
        "secret_column_issues": secret_column_issues,
        "missing_required_indexes": missing_indexes,
        "primary_key_issues": primary_key_issues,
        "crowd_final_schema_verified": not missing_tables and not missing_indexes and not primary_key_issues and not secret_column_issues,
        "finnhub_news_schema_verified": not missing_tables and not secret_column_issues,
        "applied_at": applied_at,
    }
