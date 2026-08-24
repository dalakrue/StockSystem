"""Lightweight read-only accessors for Field 10 research evidence.

This module deliberately avoids importing fitting, bootstrap, or connectedness
modules so Streamlit reruns do not pay heavy research import costs.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd

_REQUIRED = {
    "field10_rank_components_v2",
    "field10_horizon_volatility_shadow",
    "field10_semivariance_shadow",
    "field10_gas_state_shadow",
    "field10_tail_risk_shadow",
    "field10_copula_shadow",
    "field10_connectedness_shadow",
    "field10_frequency_connectedness_shadow",
    "field10_model_confidence_set",
    "field10_sample_split_validation",
}

_V3_REQUIRED = {
    "field10_probability_calibration_v2",
    "field10_structural_break_v2",
    "field10_rank_uncertainty",
    "field10_evidence_clusters",
    "field10_candidate_experiments",
    "field10_pbo_results",
    "field10_rank_components_v3",
    "field10_promotion_decisions",
}


def _connect(path: Path | str) -> sqlite3.Connection:
    resolved = Path(path).resolve()
    conn = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True, timeout=8.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


def _ready(conn: sqlite3.Connection) -> bool:
    present = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return _REQUIRED.issubset(present)


def load_candidate_summary(daily_snapshot_id: str | None = None, *, path: Path | str) -> pd.DataFrame:
    try:
        with _connect(path) as conn:
            if not _ready(conn):
                return pd.DataFrame()
            if not daily_snapshot_id:
                row = conn.execute(
                    "SELECT daily_snapshot_id FROM field10_rank_components_v2 "
                    "WHERE component_name='__SUMMARY__' ORDER BY created_system_time DESC LIMIT 1"
                ).fetchone()
                daily_snapshot_id = None if row is None else str(row[0])
            if not daily_snapshot_id:
                return pd.DataFrame()
            return pd.read_sql_query(
                "SELECT * FROM field10_rank_components_v2 WHERE daily_snapshot_id=? "
                "AND component_name='__SUMMARY__' "
                "ORDER BY production_rank IS NULL,production_rank,symbol",
                conn, params=(daily_snapshot_id,),
            )
    except (OSError, sqlite3.Error):
        return pd.DataFrame()


def load_candidate_details(daily_snapshot_id: str, *, path: Path | str) -> dict[str, pd.DataFrame]:
    if not daily_snapshot_id:
        return {}
    tables = tuple(sorted(_REQUIRED))
    result: dict[str, pd.DataFrame] = {}
    try:
        with _connect(path) as conn:
            if not _ready(conn):
                return {}
            for table in tables:
                result[table] = pd.read_sql_query(
                    f"SELECT * FROM {table} WHERE daily_snapshot_id=?", conn, params=(daily_snapshot_id,)
                )
    except (OSError, sqlite3.Error):
        return {}
    return result


def _v3_ready(conn: sqlite3.Connection) -> bool:
    present = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return _V3_REQUIRED.issubset(present)


def load_v3_candidate_summary(daily_snapshot_id: str | None = None, *, path: Path | str, parent_run_id: str | None = None) -> pd.DataFrame:
    try:
        with _connect(path) as conn:
            if not _v3_ready(conn):
                return pd.DataFrame()
            if not daily_snapshot_id:
                if parent_run_id:
                    row = conn.execute(
                        "SELECT daily_snapshot_id FROM field10_rank_components_v3 "
                        "WHERE component_name='__SUMMARY__' AND parent_run_id=? ORDER BY created_system_time DESC LIMIT 1",
                        (parent_run_id,),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT daily_snapshot_id FROM field10_rank_components_v3 "
                        "WHERE component_name='__SUMMARY__' ORDER BY created_system_time DESC LIMIT 1"
                    ).fetchone()
                daily_snapshot_id = None if row is None else str(row[0])
            if not daily_snapshot_id:
                return pd.DataFrame()
            return pd.read_sql_query(
                "SELECT * FROM field10_rank_components_v3 WHERE daily_snapshot_id=? "
                "AND component_name='__SUMMARY__' ORDER BY research_rank,symbol",
                conn, params=(daily_snapshot_id,),
            )
    except (OSError, sqlite3.Error):
        return pd.DataFrame()


def load_v3_candidate_details(daily_snapshot_id: str, *, path: Path | str, symbol: str | None = None) -> dict[str, pd.DataFrame]:
    if not daily_snapshot_id:
        return {}
    result: dict[str, pd.DataFrame] = {}
    try:
        with _connect(path) as conn:
            if not _v3_ready(conn):
                return {}
            for table in sorted(_V3_REQUIRED):
                query = f"SELECT * FROM {table} WHERE daily_snapshot_id=?"
                params: list[object] = [daily_snapshot_id]
                columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
                if symbol and "symbol" in columns and table not in {"field10_candidate_experiments", "field10_pbo_results"}:
                    query += " AND symbol=?"
                    params.append(symbol)
                result[table] = pd.read_sql_query(query, conn, params=params)
    except (OSError, sqlite3.Error):
        return {}
    return result


__all__ = ["load_candidate_summary", "load_candidate_details", "load_v3_candidate_summary", "load_v3_candidate_details"]
