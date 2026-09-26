"""Cached, read-only settled-outcome access for Field 7 research.

The preserved production ledger remains the source of truth.  The V11 database
is used only as an empty-safe fallback; neither database is mutated here.
"""
from __future__ import annotations

from functools import lru_cache
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from core.canonical.migrations import RESEARCH_DB_PATH, migrate_research_database

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_LEDGER_PATH = PROJECT_ROOT / "data" / "quant_app.sqlite3"


def _stamp(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


@lru_cache(maxsize=64)
def _cached_query(
    path_text: str,
    stamp: int,
    sql: str,
    params: tuple[Any, ...],
) -> tuple[tuple[str, ...], tuple[tuple[Any, ...], ...]]:
    del stamp
    with sqlite3.connect(path_text, timeout=10) as conn:
        cursor = conn.execute(sql, params)
        columns = tuple(item[0] for item in cursor.description or ())
        rows = tuple(cursor.fetchall())
    return columns, rows


def _read(path: Path, sql: str, params: tuple[Any, ...]) -> pd.DataFrame:
    columns, rows = _cached_query(str(path), _stamp(path), sql, params)
    return pd.DataFrame.from_records(rows, columns=columns).copy()


class OutcomeRepository:
    def __init__(
        self,
        research_path: Path | str = RESEARCH_DB_PATH,
        production_path: Path | str = PRODUCTION_LEDGER_PATH,
    ):
        self.research_path = Path(research_path)
        self.production_path = Path(production_path)
        migrate_research_database(self.research_path)

    def _production_settled(self, limit: int | None) -> pd.DataFrame:
        if not self.production_path.exists():
            return pd.DataFrame()
        sql = """
            SELECT o.run_id,o.horizon_hours,o.actual_time,o.actual_price,o.actual_direction,
                   o.direction_correct,o.absolute_error,o.percentage_error,o.target_hit,o.stop_hit,
                   o.maximum_favourable_excursion AS mfe_raw,
                   o.maximum_adverse_excursion AS mae_raw,
                   o.outcome_status,o.settled_at,
                   p.current_price,p.predicted_price,p.predicted_direction,p.lower_bound,p.upper_bound,
                   p.expected_value,p.estimated_cost,p.priority_score,p.knn_score,p.greedy_score,p.decision
            FROM prediction_outcomes o
            LEFT JOIN predictions p ON p.run_id=o.run_id AND p.horizon_hours=o.horizon_hours
            WHERE o.outcome_status='SETTLED'
            ORDER BY o.settled_at DESC
        """
        params: tuple[Any, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (int(limit),)
        try:
            frame = _read(self.production_path, sql, params)
        except (sqlite3.Error, ValueError):
            return pd.DataFrame()
        if frame.empty:
            return frame
        frame["residual"] = (
            pd.to_numeric(frame["actual_price"], errors="coerce")
            - pd.to_numeric(frame["predicted_price"], errors="coerce")
        )
        direction = frame["predicted_direction"].fillna(frame["decision"]).astype(str).str.upper()
        multiplier = direction.map({"BUY": 1.0, "SELL": -1.0}).fillna(0.0)
        frame["realized_pips"] = (
            pd.to_numeric(frame["actual_price"], errors="coerce")
            - pd.to_numeric(frame["current_price"], errors="coerce")
        ) * 10000.0 * multiplier
        frame["mfe_pips"] = pd.to_numeric(frame["mfe_raw"], errors="coerce") * 10000.0
        frame["mae_pips"] = pd.to_numeric(frame["mae_raw"], errors="coerce") * 10000.0
        frame["settled_outcome"] = (
            frame["direction_correct"].map({1: "WIN", 0: "LOSS"}).fillna("UNKNOWN")
        )
        return frame

    def _research_settled(self, limit: int | None) -> pd.DataFrame:
        sql = (
            "SELECT * FROM prediction_outcomes WHERE settled_outcome IS NOT NULL "
            "ORDER BY settled_at_utc DESC"
        )
        params: tuple[Any, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (int(limit),)
        try:
            return _read(self.research_path, sql, params)
        except (sqlite3.Error, ValueError):
            return pd.DataFrame()

    def settled(self, limit: int | None = None) -> pd.DataFrame:
        production = self._production_settled(limit)
        if not production.empty:
            return production
        return self._research_settled(limit)


__all__ = ["OutcomeRepository", "PRODUCTION_LEDGER_PATH"]
