"""Incremental DuckDB store for regime-transition, calibration and audit history.

The store is an analytical sidecar.  It never computes or publishes a trading
signal and it never replaces the canonical SQLite snapshot transaction.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Mapping, Sequence
import json

import pandas as pd

from core.generation_identity_20260707 import numeric_generation

try:
    import duckdb
except Exception:  # pragma: no cover - dependency is declared in requirements.txt
    duckdb = None  # type: ignore

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None  # type: ignore

VERSION = "regime-trust-store-20260621-v1"
DB_PATH = Path(__file__).resolve().parents[1] / "data" / "regime_trust_history.duckdb"
PARQUET_DIR = Path(__file__).resolve().parents[1] / "data" / "history_parquet"

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "regime_transition_history": (
        "timestamp", "run_id", "calculation_generation", "transition_time",
        "previous_regime", "new_regime", "change_probability", "drift_type",
        "run_length_before", "confirmation_delay_bars", "volatility_before",
        "volatility_after", "forecast_disagreement", "calibrated_regime_trust",
        "trigger_summary",
    ),
    "post_transition_outcome_history": (
        "timestamp", "run_id", "calculation_generation", "transition_time",
        "new_regime", "entry_reference_price", "actual_close_1h", "actual_close_2h",
        "actual_close_3h", "actual_close_6h", "direction_correct_1h",
        "direction_correct_3h", "direction_correct_6h", "maximum_favorable_excursion",
        "maximum_adverse_excursion", "regime_still_active_6h",
    ),
    "prediction_calibration_history": (
        "timestamp", "run_id", "calculation_generation", "raw_confidence",
        "calibrated_confidence", "predicted_direction", "actual_direction",
        "absolute_close_error", "interval_lower", "interval_upper",
        "actual_inside_interval", "rolling_coverage", "expected_calibration_error",
        "brier_score",
    ),
    "drift_detector_history": (
        "timestamp", "run_id", "calculation_generation", "bocpd_probability",
        "adwin_detection_status", "adaptive_window_size", "drift_type",
        "forecast_spread", "error_drift_score", "volatility_drift_score",
        "action_taken",
    ),
    "decision_audit_history": (
        "timestamp", "run_id", "calculation_generation", "master_decision",
        "less_risky_decision", "priority_rank", "regime", "regime_trust",
        "forecast_reliability", "conflict_status", "data_freshness", "fallback_use",
        "reason_summary",
    ),
    "component_error_history": (
        "timestamp", "component", "run_id", "calculation_generation",
        "exception_type", "safe_summary", "fallback_used",
    ),
}

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS regime_transition_history(
  timestamp TIMESTAMP, run_id VARCHAR, calculation_generation BIGINT,
  transition_time TIMESTAMP, previous_regime VARCHAR, new_regime VARCHAR,
  change_probability DOUBLE, drift_type VARCHAR, run_length_before BIGINT,
  confirmation_delay_bars BIGINT, volatility_before DOUBLE, volatility_after DOUBLE,
  forecast_disagreement DOUBLE, calibrated_regime_trust DOUBLE, trigger_summary VARCHAR,
  UNIQUE(transition_time, previous_regime, new_regime));
CREATE TABLE IF NOT EXISTS post_transition_outcome_history(
  timestamp TIMESTAMP, run_id VARCHAR, calculation_generation BIGINT,
  transition_time TIMESTAMP, new_regime VARCHAR, entry_reference_price DOUBLE,
  actual_close_1h DOUBLE, actual_close_2h DOUBLE, actual_close_3h DOUBLE,
  actual_close_6h DOUBLE, direction_correct_1h BOOLEAN, direction_correct_3h BOOLEAN,
  direction_correct_6h BOOLEAN, maximum_favorable_excursion DOUBLE,
  maximum_adverse_excursion DOUBLE, regime_still_active_6h BOOLEAN,
  UNIQUE(transition_time, new_regime));
CREATE TABLE IF NOT EXISTS prediction_calibration_history(
  timestamp TIMESTAMP, run_id VARCHAR, calculation_generation BIGINT,
  raw_confidence DOUBLE, calibrated_confidence DOUBLE, predicted_direction VARCHAR,
  actual_direction VARCHAR, absolute_close_error DOUBLE, interval_lower DOUBLE,
  interval_upper DOUBLE, actual_inside_interval BOOLEAN, rolling_coverage DOUBLE,
  expected_calibration_error DOUBLE, brier_score DOUBLE,
  UNIQUE(run_id, calculation_generation));
CREATE TABLE IF NOT EXISTS drift_detector_history(
  timestamp TIMESTAMP, run_id VARCHAR, calculation_generation BIGINT,
  bocpd_probability DOUBLE, adwin_detection_status VARCHAR, adaptive_window_size BIGINT,
  drift_type VARCHAR, forecast_spread DOUBLE, error_drift_score DOUBLE,
  volatility_drift_score DOUBLE, action_taken VARCHAR,
  UNIQUE(run_id, calculation_generation));
CREATE TABLE IF NOT EXISTS decision_audit_history(
  timestamp TIMESTAMP, run_id VARCHAR, calculation_generation BIGINT,
  master_decision VARCHAR, less_risky_decision VARCHAR, priority_rank VARCHAR,
  regime VARCHAR, regime_trust DOUBLE, forecast_reliability DOUBLE,
  conflict_status VARCHAR, data_freshness VARCHAR, fallback_use BOOLEAN,
  reason_summary VARCHAR,
  UNIQUE(run_id, calculation_generation));
CREATE TABLE IF NOT EXISTS component_error_history(
  timestamp TIMESTAMP, component VARCHAR, run_id VARCHAR,
  calculation_generation BIGINT, exception_type VARCHAR, safe_summary VARCHAR,
  fallback_used BOOLEAN);
CREATE INDEX IF NOT EXISTS idx_transition_pair ON regime_transition_history(previous_regime,new_regime,transition_time);
CREATE INDEX IF NOT EXISTS idx_calibration_time ON prediction_calibration_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_drift_time ON drift_detector_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_time ON decision_audit_history(timestamp);
CREATE OR REPLACE VIEW regime_transition_matches AS
  SELECT t.*, o.entry_reference_price, o.actual_close_1h, o.actual_close_2h,
         o.actual_close_3h, o.actual_close_6h, o.maximum_favorable_excursion,
         o.maximum_adverse_excursion, o.regime_still_active_6h
  FROM regime_transition_history t
  LEFT JOIN post_transition_outcome_history o
    ON t.transition_time=o.transition_time AND t.new_regime=o.new_regime;
"""


def _jsonable(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


@dataclass
class RegimeTrustStore:
    path: Path = DB_PATH

    def __post_init__(self) -> None:
        if duckdb is None:
            raise RuntimeError("duckdb is unavailable")
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.ensure_schema()

    def connect(self):
        return duckdb.connect(str(self.path))

    def ensure_schema(self) -> None:
        with self._lock:
            conn = self.connect()
            try:
                conn.execute(_SCHEMA_SQL)
            finally:
                conn.close()

    def append_bundle(self, bundle: Mapping[str, Iterable[Mapping[str, Any]]]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        updates: dict[str, int] = {}
        with self._lock:
            conn = self.connect()
            try:
                conn.execute("BEGIN TRANSACTION")
                for table, rows_iter in dict(bundle or {}).items():
                    if table not in TABLE_COLUMNS:
                        continue
                    rows = [dict(row) for row in (rows_iter or []) if isinstance(row, Mapping)]
                    if not rows:
                        counts[table] = 0
                        continue
                    columns = TABLE_COLUMNS[table]
                    frame = pd.DataFrame([{col: _jsonable(row.get(col)) for col in columns} for row in rows], columns=columns)
                    before = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                    conn.register("_regime_trust_batch", frame)
                    col_sql = ",".join(f'"{c}"' for c in columns)
                    if table == "post_transition_outcome_history":
                        # A transition can be observed before its 1/2/3/6-hour
                        # outcomes settle. Mature only missing outcome fields,
                        # keep one physical event row, and record the canonical
                        # generation that supplied the newly settled evidence.
                        maturity_fields = (
                            "actual_close_1h", "actual_close_2h", "actual_close_3h",
                            "actual_close_6h", "direction_correct_1h",
                            "direction_correct_3h", "direction_correct_6h",
                            "regime_still_active_6h",
                        )
                        condition = " OR ".join(
                            f'(target."{field}" IS NULL AND source."{field}" IS NOT NULL)'
                            for field in maturity_fields
                        )
                        maturity_gain = " + ".join(
                            f'CASE WHEN target."{field}" IS NULL AND source."{field}" IS NOT NULL THEN 1 ELSE 0 END'
                            for field in maturity_fields
                        )
                        matured_fields = int(conn.execute(
                            f'SELECT COALESCE(SUM({maturity_gain}),0) '
                            f'FROM "post_transition_outcome_history" AS target '
                            f'JOIN _regime_trust_batch AS source '
                            f'ON target.transition_time=source.transition_time '
                            f'AND target.new_regime=source.new_regime'
                        ).fetchone()[0])
                        update_fields = [
                            "timestamp", "run_id", "calculation_generation",
                            "entry_reference_price", "actual_close_1h", "actual_close_2h",
                            "actual_close_3h", "actual_close_6h", "direction_correct_1h",
                            "direction_correct_3h", "direction_correct_6h",
                            "maximum_favorable_excursion", "maximum_adverse_excursion",
                            "regime_still_active_6h",
                        ]
                        assignments = ", ".join(
                            f'"{field}" = COALESCE(source."{field}", target."{field}")'
                            for field in update_fields
                        )
                        conn.execute(
                            f'UPDATE "post_transition_outcome_history" AS target SET {assignments} '
                            f'FROM _regime_trust_batch AS source '
                            f'WHERE target.transition_time=source.transition_time '
                            f'AND target.new_regime=source.new_regime AND ({condition})'
                        )
                        conn.execute(
                            f'INSERT OR IGNORE INTO "{table}" ({col_sql}) SELECT {col_sql} FROM _regime_trust_batch'
                        )
                        updates[table] = max(0, matured_fields)
                    else:
                        conn.execute(
                            f'INSERT OR IGNORE INTO "{table}" ({col_sql}) SELECT {col_sql} FROM _regime_trust_batch'
                        )
                    conn.unregister("_regime_trust_batch")
                    after = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                    counts[table] = max(0, after - before)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()
        return {"ok": True, "version": VERSION, "tables": counts, "updates": updates, "path": str(self.path)}

    def query(
        self,
        table: str,
        *,
        columns: Sequence[str] | None = None,
        where_sql: str = "",
        params: Sequence[Any] | None = None,
        order_by: str | None = "timestamp",
        descending: bool = True,
        limit: int = 200,
    ) -> pd.DataFrame:
        if table not in set(TABLE_COLUMNS) | {"regime_transition_matches"}:
            raise ValueError(f"Unsupported history table: {table}")
        selected = "*" if not columns else ",".join(f'"{c}"' for c in columns)
        sql = f'SELECT {selected} FROM "{table}"'
        if where_sql:
            sql += " WHERE " + where_sql
        if order_by:
            sql += f' ORDER BY "{order_by}" {"DESC" if descending else "ASC"}'
        sql += " LIMIT ?"
        values = list(params or []) + [max(1, min(int(limit), 5000))]
        with self._lock:
            conn = self.connect()
            try:
                return conn.execute(sql, values).fetchdf()
            finally:
                conn.close()

    def transition_matches(self, previous_regime: str, new_regime: str, *, limit: int = 100) -> pd.DataFrame:
        return self.query(
            "regime_transition_matches",
            where_sql="previous_regime = ? AND new_regime = ?",
            params=[str(previous_regime), str(new_regime)],
            order_by="transition_time",
            limit=limit,
        )

    def checkpoint_parquet(self, tables: Sequence[str] | None = None) -> dict[str, str]:
        """Create compact analytical checkpoints; DuckDB remains authoritative."""
        PARQUET_DIR.mkdir(parents=True, exist_ok=True)
        targets = list(tables or TABLE_COLUMNS.keys())
        written: dict[str, str] = {}
        with self._lock:
            conn = self.connect()
            try:
                for table in targets:
                    if table not in TABLE_COLUMNS:
                        continue
                    target = PARQUET_DIR / f"{table}.parquet"
                    escaped = str(target).replace("'", "''")
                    conn.execute(f'COPY (SELECT * FROM "{table}") TO \'{escaped}\' (FORMAT PARQUET, COMPRESSION ZSTD)')
                    written[table] = str(target)
            finally:
                conn.close()
        return written


def _make_store(path: str) -> RegimeTrustStore:
    return RegimeTrustStore(Path(path))


if st is not None:
    get_regime_trust_store = st.cache_resource(show_spinner=False)(_make_store)
else:  # pragma: no cover
    get_regime_trust_store = _make_store


def default_store() -> RegimeTrustStore:
    return get_regime_trust_store(str(DB_PATH))


def persist_regime_trust_bundle(bundle: Mapping[str, Iterable[Mapping[str, Any]]]) -> dict[str, Any]:
    store = default_store()
    result = store.append_bundle(bundle)
    # Parquet is a periodic durable analytical checkpoint, not a per-widget reload.
    total_rows = sum(len(v) for k, v in dict(bundle or {}).items() if k in TABLE_COLUMNS and isinstance(v, (list, tuple)))
    if total_rows and total_rows % 12 == 0:
        try:
            result["parquet"] = store.checkpoint_parquet()
        except Exception as exc:
            result["parquet_warning"] = str(exc)
    return result


def record_component_error(
    *, component: str, run_id: str = "", calculation_generation: int = 0,
    exception: BaseException | str, fallback_used: bool = True,
) -> None:
    safe = str(exception).replace("\n", " ")[:500]
    row = {
        "timestamp": pd.Timestamp.now(tz="UTC"),
        "component": component,
        "run_id": run_id,
        "calculation_generation": numeric_generation(calculation_generation, default=1),
        "exception_type": type(exception).__name__ if isinstance(exception, BaseException) else "Error",
        "safe_summary": safe,
        "fallback_used": bool(fallback_used),
    }
    default_store().append_bundle({"component_error_history": [row]})


__all__ = [
    "VERSION", "DB_PATH", "PARQUET_DIR", "TABLE_COLUMNS", "RegimeTrustStore",
    "default_store", "persist_regime_trust_bundle", "record_component_error",
]
