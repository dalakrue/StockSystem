# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Persistent prediction/outcome ledger with safe SQLite migrations.

The ledger shares the project's existing SQLite file, uses parameterized SQL,
WAL mode, bounded retries for locked databases, and an in-process fallback when
persistent storage is unavailable.  Secrets are never accepted or stored.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "quant_app.sqlite3"
_LOCK = threading.RLock()
_FALLBACK: Dict[str, List[Dict[str, Any]]] = {
    "calculation_runs": [], "predictions": [], "regime_snapshots": [],
    "prediction_outcomes": [], "drift_history": [], "nlp_event_memory": [],
}
_REQUIRED_TABLES = tuple(_FALLBACK)
_SCHEMA_REPAIR_ERRORS = ("no such table", "no such column", "database schema has changed")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite(value: Any) -> Optional[float]:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _normalize_time(value: Any) -> Optional[str]:
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts.isoformat()
    except Exception:
        return None


def _compact_run_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return the durable scalar run summary, never full frames or chart payloads.

    Forecast horizon rows, regime snapshots and drift details are already stored in
    normalized ledger tables.  Persisting the entire in-memory canonical result here
    duplicated history DataFrames and could add tens of megabytes per click.  The
    compact JSON keeps the fields consumed by legacy readers (especially
    ``final_decision``) while preserving audit identifiers and research summaries.
    """
    src = dict(payload or {})
    compact: Dict[str, Any] = {
        key: src.get(key) for key in (
            "run_id", "created_at", "symbol", "timeframe", "source",
            "data_signature", "model_version", "calculation_version",
            "schema_version", "calculation_status", "failure_reason",
        ) if src.get(key) is not None
    }

    def scalar_dict(value: Any, *, max_items: int = 80) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        out: Dict[str, Any] = {}
        for key, item in value.items():
            if len(out) >= max_items:
                break
            if item is None or isinstance(item, (str, int, float, bool)):
                out[str(key)] = item
            elif isinstance(item, dict):
                nested = {
                    str(k): v for k, v in item.items()
                    if v is None or isinstance(v, (str, int, float, bool))
                }
                if nested:
                    out[str(key)] = dict(list(nested.items())[:40])
        return out

    market = scalar_dict(src.get("market"), max_items=40)
    if market:
        compact["market"] = market
    for key in (
        "data_quality", "final_decision", "reliability", "priority",
        "drift", "regime", "canonical_authority", "calculation_metadata",
    ):
        value = scalar_dict(src.get(key))
        if value:
            compact[key] = value

    research = src.get("research_risk_stack") or src.get("research_risk")
    if isinstance(research, dict):
        compact["research_risk"] = {
            "ok": bool(research.get("ok")),
            "version": research.get("version"),
            "less_risky_decision": research.get("less_risky_decision"),
            "short_reason": research.get("short_reason"),
        }
        for key in (
            "proper_scoring", "competing_risk", "confidence_sequence",
            "selective_prediction", "evt_tail", "invariance",
            "risk_multiplier", "robust_expectancy", "event_intensity",
        ):
            value = scalar_dict(research.get(key), max_items=30)
            if value:
                compact["research_risk"][key] = value

    compact["persistence"] = {
        "mode": "COMPACT_NORMALIZED_V1",
        "forecast_rows_stored_separately": True,
        "full_history_frames_omitted": True,
    }
    return compact


class PredictionLedger:
    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        configured = os.environ.get("ADX_LEDGER_DB_PATH")
        self.db_path = Path(db_path or configured or DEFAULT_DB_PATH)
        self.available = False
        self.last_error = ""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.initialize()
            self.available = True
        except Exception as exc:
            self.last_error = str(exc)
            self.available = False

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=15, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=15000")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _schema_is_complete(self) -> bool:
        try:
            with _LOCK, self.connection() as conn:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            existing = {str(row[0]) for row in rows}
            return set(_REQUIRED_TABLES).issubset(existing)
        except Exception:
            return False

    def ensure_schema(self, *, force: bool = False) -> bool:
        """Idempotently repair an old/partial SQLite ledger in place.

        Streamlit Cloud can preserve an older database file while deploying newer
        code.  This method makes every critical ledger operation tolerant of that
        state instead of allowing a missing table to abort the whole Settings run.
        """
        try:
            if force or not self._schema_is_complete():
                self.initialize()
            self.available = self._schema_is_complete()
            if not self.available:
                self.last_error = "Ledger schema verification failed after repair."
            return self.available
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.available = False
            return False

    def _execute_retry(self, sql: str, params: Sequence[Any] = (), *, fetch: bool = False) -> Any:
        last: Optional[Exception] = None
        repaired = False
        for attempt in range(5):
            try:
                with _LOCK, self.connection() as conn:
                    cur = conn.execute(sql, tuple(params))
                    if fetch:
                        return [dict(row) for row in cur.fetchall()]
                    return cur.rowcount
            except sqlite3.OperationalError as exc:
                last = exc
                message = str(exc).lower()
                if any(token in message for token in _SCHEMA_REPAIR_ERRORS) and not repaired:
                    repaired = True
                    if self.ensure_schema(force=True):
                        continue
                if "locked" in message and attempt < 4:
                    time.sleep(0.12 * (attempt + 1))
                    continue
                raise
        raise RuntimeError(str(last or "database operation failed"))

    def initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS calculation_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                source TEXT NOT NULL,
                latest_completed_candle_time TEXT,
                data_signature TEXT NOT NULL,
                model_version TEXT NOT NULL,
                calculation_version TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                data_quality_status TEXT NOT NULL,
                calculation_status TEXT NOT NULL,
                failure_reason TEXT,
                result_json TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                horizon_hours INTEGER NOT NULL,
                current_price REAL,
                predicted_price REAL,
                predicted_direction TEXT,
                buy_probability_raw REAL,
                sell_probability_raw REAL,
                wait_probability_raw REAL,
                buy_probability_calibrated REAL,
                sell_probability_calibrated REAL,
                wait_probability_calibrated REAL,
                lower_bound REAL,
                upper_bound REAL,
                interval_target_coverage REAL,
                decision TEXT,
                decision_threshold REAL,
                expected_value REAL,
                expected_gain REAL,
                expected_loss REAL,
                estimated_cost REAL,
                actionability_probability REAL,
                priority_score REAL,
                knn_score REAL,
                greedy_score REAL,
                due_time TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(run_id, horizon_hours),
                FOREIGN KEY(run_id) REFERENCES calculation_runs(run_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS regime_snapshots (
                run_id TEXT PRIMARY KEY,
                major_regime TEXT,
                lower_standard_regime TEXT,
                middle_standard_regime TEXT,
                higher_standard_regime TEXT,
                regime_score REAL,
                regime_confidence REAL,
                regime_reliability REAL,
                regime_age_hours REAL,
                expected_duration_hours REAL,
                remaining_duration_hours REAL,
                alpha REAL,
                delta REAL,
                delta_acceleration REAL,
                transition_probability_1h REAL,
                transition_probability_3h REAL,
                transition_probability_6h REAL,
                possible_next_regimes_json TEXT,
                FOREIGN KEY(run_id) REFERENCES calculation_runs(run_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS prediction_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                horizon_hours INTEGER NOT NULL,
                due_time TEXT NOT NULL,
                actual_time TEXT,
                actual_price REAL,
                actual_direction TEXT,
                direction_correct INTEGER,
                absolute_error REAL,
                percentage_error REAL,
                target_hit INTEGER,
                stop_hit INTEGER,
                maximum_favourable_excursion REAL,
                maximum_adverse_excursion REAL,
                outcome_status TEXT NOT NULL DEFAULT 'PENDING',
                settled_at TEXT,
                UNIQUE(run_id, horizon_hours),
                FOREIGN KEY(run_id) REFERENCES calculation_runs(run_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS drift_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                created_at TEXT NOT NULL,
                symbol TEXT,
                timeframe TEXT,
                prediction_status TEXT,
                feature_status TEXT,
                decision_status TEXT,
                overall_status TEXT,
                score REAL,
                details_json TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS nlp_event_memory (
                article_id TEXT PRIMARY KEY,
                source TEXT,
                publication_time TEXT,
                retrieval_time TEXT,
                event_type TEXT,
                entities_json TEXT,
                currency_relevance REAL,
                sentiment REAL,
                importance REAL,
                source_reliability REAL,
                duplicate_cluster_id TEXT,
                regime_at_publication TEXT,
                session_at_publication TEXT,
                alpha REAL,
                delta REAL,
                price_at_publication REAL,
                return_1h REAL,
                return_2h REAL,
                return_3h REAL,
                return_6h REAL,
                mfe REAL,
                mae REAL,
                finnhub_available INTEGER,
                reaction_status TEXT DEFAULT 'PENDING'
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_predictions_due ON predictions(due_time)",
            "CREATE INDEX IF NOT EXISTS idx_outcomes_status_due ON prediction_outcomes(outcome_status, due_time)",
            "CREATE INDEX IF NOT EXISTS idx_runs_symbol_tf_created ON calculation_runs(symbol, timeframe, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_drift_symbol_tf_created ON drift_history(symbol, timeframe, created_at)",
        ]
        with _LOCK, self.connection() as conn:
            for sql in statements:
                conn.execute(sql)
            existing = {
                str(row[0]) for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            missing = sorted(set(_REQUIRED_TABLES) - existing)
            if missing:
                raise sqlite3.OperationalError(
                    "ledger schema incomplete; missing tables: " + ", ".join(missing)
                )
        self.available = True
        self.last_error = ""

    def health(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        if self.available:
            self.ensure_schema()
        if self.available:
            try:
                with self.connection() as conn:
                    for table in ("calculation_runs", "predictions", "prediction_outcomes", "regime_snapshots", "drift_history", "nlp_event_memory"):
                        counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except Exception as exc:
                self.last_error = str(exc)
                self.available = False
        if not self.available:
            counts = {k: len(v) for k, v in _FALLBACK.items()}
        return {
            "status": "SQLITE" if self.available else "MEMORY_FALLBACK",
            "path": str(self.db_path),
            "counts": counts,
            "error": self.last_error,
        }

    def record_failed_run(self, run: Dict[str, Any]) -> None:
        payload = dict(run)
        payload.setdefault("created_at", _utc_now())
        payload.setdefault("calculation_status", "FAILED")
        self._insert_run(payload)

    def record_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Append one immutable run and all horizon rows in one transaction."""
        payload = dict(result or {})
        if not payload.get("run_id"):
            raise ValueError("run_id is required")
        if not self.available:
            _FALLBACK["calculation_runs"].append(payload)
            for h in ((payload.get("forecasts") or {}).get("horizons") or {}).values():
                _FALLBACK["predictions"].append({"run_id": payload["run_id"], **dict(h or {})})
            _FALLBACK["regime_snapshots"].append({"run_id": payload["run_id"], **dict(payload.get("regime") or {})})
            return {"status": "MEMORY_FALLBACK", "ok": True}

        run = self._run_row(payload)
        forecasts = ((payload.get("forecasts") or {}).get("horizons") or {})
        regime = dict(payload.get("regime") or {})
        drift = dict(payload.get("drift") or {})
        with _LOCK, self.connection() as conn:
            conn.execute(
                """INSERT INTO calculation_runs(
                    run_id,created_at,symbol,timeframe,source,latest_completed_candle_time,
                    data_signature,model_version,calculation_version,schema_version,
                    data_quality_status,calculation_status,failure_reason,result_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                run,
            )
            for key, forecast in forecasts.items():
                row = dict(forecast or {})
                horizon = int(row.get("horizon_hours") or str(key).replace("h", "") or 0)
                conn.execute(
                    """INSERT INTO predictions(
                        run_id,horizon_hours,current_price,predicted_price,predicted_direction,
                        buy_probability_raw,sell_probability_raw,wait_probability_raw,
                        buy_probability_calibrated,sell_probability_calibrated,wait_probability_calibrated,
                        lower_bound,upper_bound,interval_target_coverage,decision,decision_threshold,
                        expected_value,expected_gain,expected_loss,estimated_cost,actionability_probability,
                        priority_score,knn_score,greedy_score,due_time,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        payload["run_id"], horizon, _finite((payload.get("market") or {}).get("current_price")),
                        _finite(row.get("point_forecast")), row.get("direction"),
                        _finite(row.get("buy_probability_raw")), _finite(row.get("sell_probability_raw")), _finite(row.get("wait_probability_raw")),
                        _finite(row.get("buy_probability_calibrated")), _finite(row.get("sell_probability_calibrated")), _finite(row.get("wait_probability_calibrated")),
                        _finite(row.get("lower_bound")), _finite(row.get("upper_bound")), _finite(row.get("target_coverage")),
                        row.get("decision"), _finite(row.get("threshold")), _finite(row.get("expected_value")),
                        _finite(row.get("expected_gain")), _finite(row.get("expected_loss")), _finite(row.get("estimated_cost")),
                        _finite(row.get("actionability_probability")), _finite(row.get("priority_score")), _finite(row.get("knn_score")), _finite(row.get("greedy_score")),
                        row.get("due_time"), payload.get("created_at") or _utc_now(),
                    ),
                )
                if row.get("due_time"):
                    conn.execute(
                        "INSERT INTO prediction_outcomes(run_id,horizon_hours,due_time,outcome_status) VALUES (?,?,?,'PENDING')",
                        (payload["run_id"], horizon, row.get("due_time")),
                    )
            conn.execute(
                """INSERT INTO regime_snapshots(
                    run_id,major_regime,lower_standard_regime,middle_standard_regime,higher_standard_regime,
                    regime_score,regime_confidence,regime_reliability,regime_age_hours,expected_duration_hours,
                    remaining_duration_hours,alpha,delta,delta_acceleration,transition_probability_1h,
                    transition_probability_3h,transition_probability_6h,possible_next_regimes_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    payload["run_id"], regime.get("major_regime"), regime.get("lower_standard_regime"),
                    regime.get("middle_standard_regime"), regime.get("higher_standard_regime"),
                    _finite(regime.get("regime_score")), _finite(regime.get("confidence")), _finite(regime.get("reliability")),
                    _finite(regime.get("age_hours")), _finite(regime.get("expected_duration_hours")), _finite(regime.get("remaining_duration_hours")),
                    _finite(regime.get("alpha")), _finite(regime.get("delta")), _finite(regime.get("delta_acceleration")),
                    _finite(regime.get("transition_probability_1h")), _finite(regime.get("transition_probability_3h")),
                    _finite(regime.get("transition_probability_6h")), _json(regime.get("possible_next_regimes") or {}),
                ),
            )
            conn.execute(
                """INSERT INTO drift_history(
                    run_id,created_at,symbol,timeframe,prediction_status,feature_status,decision_status,
                    overall_status,score,details_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    payload["run_id"], payload.get("created_at") or _utc_now(), payload.get("symbol"), payload.get("timeframe"),
                    drift.get("prediction_status"), drift.get("feature_status"), drift.get("decision_status"),
                    drift.get("status"), _finite(drift.get("score")), _json(drift),
                ),
            )
        return {"status": "SQLITE", "ok": True}

    def _run_row(self, payload: Dict[str, Any]) -> Tuple[Any, ...]:
        market = dict(payload.get("market") or {})
        quality = dict(payload.get("data_quality") or {})
        return (
            payload.get("run_id"), payload.get("created_at") or _utc_now(), payload.get("symbol") or "UNKNOWN",
            payload.get("timeframe") or "UNKNOWN", payload.get("source") or "UNKNOWN",
            market.get("latest_completed_candle_time"), payload.get("data_signature") or "unknown",
            payload.get("model_version") or "unknown", payload.get("calculation_version") or "unknown",
            payload.get("schema_version") or "unknown", quality.get("status") or "FAIL_ALL",
            payload.get("calculation_status") or "COMPLETED", payload.get("failure_reason"), _json(_compact_run_payload(payload)),
        )

    def _insert_run(self, payload: Dict[str, Any]) -> None:
        if not self.available:
            _FALLBACK["calculation_runs"].append(payload)
            return
        self._execute_retry(
            """INSERT OR REPLACE INTO calculation_runs(
                run_id,created_at,symbol,timeframe,source,latest_completed_candle_time,
                data_signature,model_version,calculation_version,schema_version,
                data_quality_status,calculation_status,failure_reason,result_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            self._run_row(payload),
        )

    def settled_predictions(self, *, symbol: Optional[str] = None, timeframe: Optional[str] = None,
                            horizon: Optional[int] = None, limit: int = 5000) -> pd.DataFrame:
        if not self.available:
            rows = [x for x in _FALLBACK["prediction_outcomes"] if x.get("outcome_status") == "SETTLED"]
            return pd.DataFrame(rows).tail(limit)
        clauses = ["o.outcome_status='SETTLED'"]
        params: List[Any] = []
        if symbol:
            clauses.append("r.symbol=?"); params.append(symbol)
        if timeframe:
            clauses.append("r.timeframe=?"); params.append(timeframe)
        if horizon:
            clauses.append("p.horizon_hours=?"); params.append(int(horizon))
        params.append(int(limit))
        sql = f"""
            SELECT r.run_id,r.created_at,r.symbol,r.timeframe,r.source,r.latest_completed_candle_time,
                   p.*,o.actual_time,o.actual_price,o.actual_direction,o.direction_correct,o.absolute_error,
                   o.percentage_error,o.target_hit,o.stop_hit,o.maximum_favourable_excursion,
                   o.maximum_adverse_excursion,o.outcome_status,rs.major_regime
            FROM prediction_outcomes o
            JOIN predictions p ON p.run_id=o.run_id AND p.horizon_hours=o.horizon_hours
            JOIN calculation_runs r ON r.run_id=o.run_id
            LEFT JOIN regime_snapshots rs ON rs.run_id=o.run_id
            WHERE {' AND '.join(clauses)}
            ORDER BY r.created_at DESC LIMIT ?
        """
        try:
            return pd.DataFrame(self._execute_retry(sql, params, fetch=True))
        except Exception as exc:
            self.last_error = str(exc)
            return pd.DataFrame()

    def recent_runs(self, *, symbol: Optional[str] = None, timeframe: Optional[str] = None, limit: int = 200) -> pd.DataFrame:
        if not self.available:
            return pd.DataFrame(_FALLBACK["calculation_runs"]).tail(limit)
        clauses = ["1=1"]
        params: List[Any] = []
        if symbol:
            clauses.append("symbol=?"); params.append(symbol)
        if timeframe:
            clauses.append("timeframe=?"); params.append(timeframe)
        params.append(int(limit))
        try:
            rows = self._execute_retry(
                f"SELECT * FROM calculation_runs WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?",
                params, fetch=True,
            )
            return pd.DataFrame(rows)
        except Exception as exc:
            self.last_error = str(exc)
            return pd.DataFrame()

    def settle_pending_outcomes(self, ohlc: pd.DataFrame) -> Dict[str, Any]:
        """Settle only predictions whose required future completed candle exists."""
        frame = _normalize_ohlc(ohlc)
        if frame.empty:
            return {"ok": False, "settled": 0, "pending": 0, "message": "No completed OHLC rows"}
        if not self.available and not self.ensure_schema(force=True):
            return {
                "ok": True, "settled": 0,
                "pending": len(_FALLBACK["prediction_outcomes"]),
                "status": "MEMORY_FALLBACK",
                "message": self.last_error or "Persistent ledger unavailable; calculation continued safely.",
            }
        if not self.ensure_schema():
            return {
                "ok": True, "settled": 0,
                "pending": len(_FALLBACK["prediction_outcomes"]),
                "status": "MEMORY_FALLBACK",
                "message": self.last_error or "Ledger schema repair failed; calculation continued safely.",
            }
        try:
            pending = self._execute_retry(
                """SELECT o.run_id,o.horizon_hours,o.due_time,p.current_price,p.predicted_price,
                          p.predicted_direction,p.lower_bound,p.upper_bound
                   FROM prediction_outcomes o JOIN predictions p
                   ON p.run_id=o.run_id AND p.horizon_hours=o.horizon_hours
                   WHERE o.outcome_status='PENDING' ORDER BY o.due_time ASC""",
                fetch=True,
            )
        except Exception as exc:
            # Outcome settlement is auxiliary bookkeeping.  A damaged or
            # read-only Cloud database must never abort the canonical run.
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.available = False
            return {
                "ok": True, "settled": 0,
                "pending": len(_FALLBACK["prediction_outcomes"]),
                "status": "MEMORY_FALLBACK",
                "message": "Outcome ledger unavailable; calculation continued safely.",
                "error": self.last_error[:240],
            }
        settled = 0
        latest = frame.index.max()
        for row in pending:
            due = pd.to_datetime(row.get("due_time"), utc=True, errors="coerce")
            if pd.isna(due) or due > latest:
                continue
            eligible = frame.loc[frame.index >= due]
            if eligible.empty:
                continue
            actual_time = eligible.index[0]
            actual = float(eligible.iloc[0]["close"])
            current = _finite(row.get("current_price"))
            predicted = _finite(row.get("predicted_price"))
            if current is None or predicted is None:
                continue
            direction = str(row.get("predicted_direction") or "WAIT").upper()
            actual_direction = "BUY" if actual > current else "SELL" if actual < current else "WAIT"
            correct = int(direction == actual_direction) if direction in {"BUY", "SELL", "WAIT"} else 0
            abs_err = abs(actual - predicted)
            pct_err = abs_err / abs(actual) * 100 if actual else None
            segment = frame.loc[(frame.index > (due - pd.Timedelta(hours=int(row.get("horizon_hours") or 1)))) & (frame.index <= actual_time)]
            highs = segment["high"] if not segment.empty else pd.Series([actual])
            lows = segment["low"] if not segment.empty else pd.Series([actual])
            if direction == "BUY":
                mfe = float(highs.max() - current); mae = float(current - lows.min())
            elif direction == "SELL":
                mfe = float(current - lows.min()); mae = float(highs.max() - current)
            else:
                mfe = 0.0; mae = float(max(abs(highs.max() - current), abs(current - lows.min())))
            lower = _finite(row.get("lower_bound")); upper = _finite(row.get("upper_bound"))
            target_hit = int((direction == "BUY" and actual >= predicted) or (direction == "SELL" and actual <= predicted))
            stop_hit = int((lower is not None and actual < lower) or (upper is not None and actual > upper))
            self._execute_retry(
                """UPDATE prediction_outcomes SET actual_time=?,actual_price=?,actual_direction=?,direction_correct=?,
                   absolute_error=?,percentage_error=?,target_hit=?,stop_hit=?,maximum_favourable_excursion=?,
                   maximum_adverse_excursion=?,outcome_status='SETTLED',settled_at=?
                   WHERE run_id=? AND horizon_hours=? AND outcome_status='PENDING'""",
                (
                    actual_time.isoformat(), actual, actual_direction, correct, abs_err, pct_err, target_hit,
                    stop_hit, max(0.0, mfe), max(0.0, mae), _utc_now(), row.get("run_id"), int(row.get("horizon_hours") or 1),
                ),
            )
            settled += 1
        return {"ok": True, "settled": settled, "pending": max(0, len(pending) - settled), "latest_completed": latest.isoformat()}

    def save_nlp_events(self, rows: Iterable[Dict[str, Any]]) -> int:
        count = 0
        for raw in rows or []:
            row = dict(raw or {})
            article_id = str(row.get("article_id") or row.get("id") or "").strip()
            if not article_id:
                continue
            if not self.available:
                if not any(x.get("article_id") == article_id for x in _FALLBACK["nlp_event_memory"]):
                    _FALLBACK["nlp_event_memory"].append(row); count += 1
                continue
            try:
                self._execute_retry(
                    """INSERT OR IGNORE INTO nlp_event_memory(
                        article_id,source,publication_time,retrieval_time,event_type,entities_json,currency_relevance,
                        sentiment,importance,source_reliability,duplicate_cluster_id,regime_at_publication,
                        session_at_publication,alpha,delta,price_at_publication,return_1h,return_2h,return_3h,
                        return_6h,mfe,mae,finnhub_available,reaction_status
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        article_id, row.get("source"), _normalize_time(row.get("publication_time") or row.get("timestamp")),
                        _normalize_time(row.get("retrieval_time")) or _utc_now(), row.get("event_type"), _json(row.get("entities") or []),
                        _finite(row.get("currency_relevance")), _finite(row.get("sentiment")), _finite(row.get("importance")),
                        _finite(row.get("source_reliability")), row.get("duplicate_cluster_id"), row.get("regime_at_publication"),
                        row.get("session_at_publication"), _finite(row.get("alpha")), _finite(row.get("delta")),
                        _finite(row.get("price_at_publication")), _finite(row.get("return_1h")), _finite(row.get("return_2h")),
                        _finite(row.get("return_3h")), _finite(row.get("return_6h")), _finite(row.get("mfe")), _finite(row.get("mae")),
                        int(bool(row.get("finnhub_available"))), row.get("reaction_status") or "PENDING",
                    ),
                )
                count += 1
            except Exception as exc:
                self.last_error = str(exc)
        return count


def _normalize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    out = df.copy()
    cmap = {str(c).strip().lower(): c for c in out.columns}
    tcol = next((cmap[x] for x in ("time", "timestamp", "datetime", "date") if x in cmap), None)
    required = {}
    for name in ("open", "high", "low", "close"):
        col = cmap.get(name) or cmap.get(name[0])
        if col is None:
            return pd.DataFrame()
        required[name] = col
    if tcol is not None:
        idx = pd.to_datetime(out[tcol], utc=True, errors="coerce")
    else:
        idx = pd.to_datetime(out.index, utc=True, errors="coerce")
    out = pd.DataFrame({name: pd.to_numeric(out[col], errors="coerce").to_numpy() for name, col in required.items()}, index=pd.DatetimeIndex(idx))
    out = out[~out.index.isna()].dropna().sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out


_DEFAULT_LEDGER: Optional[PredictionLedger] = None


def get_prediction_ledger() -> PredictionLedger:
    global _DEFAULT_LEDGER
    if _DEFAULT_LEDGER is None:
        _DEFAULT_LEDGER = PredictionLedger()
    return _DEFAULT_LEDGER
