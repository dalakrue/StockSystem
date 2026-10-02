"""SQLite repository for Field 7 shadow results.

All readers are cached by database path, file modification stamp and query
parameters.  Saving a Settings-owned research run invalidates those caches.
"""
from __future__ import annotations

from functools import lru_cache
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from core.canonical.migrations import RESEARCH_DB_PATH, migrate_research_database
from research.run_snapshot_v12 import ResearchRunSnapshot


def _stamp(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


@lru_cache(maxsize=256)
def _cached_rows(path_text: str, stamp: int, query: str, params: tuple[Any, ...]) -> tuple[tuple[Any, ...], tuple[str, ...]]:
    del stamp  # Used only as part of the cache key.
    with sqlite3.connect(path_text, timeout=10) as conn:
        cursor = conn.execute(query, params)
        columns = tuple(item[0] for item in cursor.description or ())
        rows = tuple(cursor.fetchall())
    return rows, columns


def _frame(path: Path, query: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    rows, columns = _cached_rows(str(path), _stamp(path), query, params)
    return pd.DataFrame.from_records(rows, columns=columns).copy()


def _clear_read_cache() -> None:
    _cached_rows.cache_clear()


class StaleResearchGenerationError(ValueError):
    """Raised when a V12 snapshot predates the latest stored canonical candle."""


class ImmutableResearchSnapshotError(ValueError):
    """Raised when a run_id is reused with different immutable content."""


class ResearchRepository:
    def __init__(self, path: Path | str = RESEARCH_DB_PATH):
        self.path = Path(path)
        migrate_research_database(self.path)

    def save(
        self,
        summary: Mapping[str, Any],
        horizons: list[Mapping[str, Any]],
        models: list[Mapping[str, Any]],
        diagnostics: Mapping[str, Any],
    ) -> None:
        """Persist one shadow result without touching production tables."""
        now = datetime.now(timezone.utc).isoformat()
        run_id = str(summary["run_id"])
        with sqlite3.connect(str(self.path), timeout=15) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO canonical_runs(run_id,broker_candle_time,symbol,timeframe,snapshot_hash,created_at_utc) VALUES(?,?,?,?,?,?)",
                (run_id, summary["broker_candle_time"], summary["symbol"], summary["timeframe"], summary.get("snapshot_hash"), now),
            )
            conn.execute(
                "INSERT OR REPLACE INTO research_run_summary(run_id,broker_candle_time,symbol,timeframe,canonical_decision,research_approved_action,research_status,research_trust_score,risk_multiplier,summary_json,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    summary["broker_candle_time"],
                    summary["symbol"],
                    summary["timeframe"],
                    summary["canonical_decision"],
                    summary["research_approved_action"],
                    summary["research_status"],
                    summary["research_trust_score"],
                    summary["risk_multiplier"],
                    json.dumps(dict(summary), default=str, sort_keys=True),
                    now,
                ),
            )
            for row in horizons:
                conn.execute(
                    "INSERT OR REPLACE INTO research_horizon_results(run_id,broker_candle_time,symbol,timeframe,horizon_hours,gate_status,forecastability,coverage,coverage_status,raw_prediction,corrected_prediction,forecast_bias,nominal_ev,robust_ev,tail_risk,model_agreement,sample_size,details_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        summary["broker_candle_time"],
                        summary["symbol"],
                        summary["timeframe"],
                        row["horizon_hours"],
                        row["gate_status"],
                        row.get("forecastability"),
                        row.get("coverage"),
                        row.get("coverage_status"),
                        row.get("raw_prediction"),
                        row.get("corrected_prediction"),
                        row.get("forecast_bias"),
                        row.get("nominal_ev"),
                        row.get("robust_ev"),
                        row.get("tail_risk"),
                        row.get("model_agreement"),
                        row.get("sample_size", 0),
                        json.dumps(dict(row), default=str, sort_keys=True),
                    ),
                )
                conformal = row.get("conformal") if isinstance(row.get("conformal"), Mapping) else {}
                conn.execute(
                    "INSERT OR REPLACE INTO research_conformal_history(run_id,horizon_hours,target_coverage,actual_coverage,interval_width,coverage_debt,consecutive_violations,status,details_json) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        row["horizon_hours"],
                        conformal.get("target_coverage"),
                        conformal.get("actual_coverage"),
                        conformal.get("interval_width"),
                        conformal.get("coverage_debt"),
                        conformal.get("consecutive_violations"),
                        conformal.get("status"),
                        json.dumps(dict(conformal), default=str, sort_keys=True),
                    ),
                )
            for row in models:
                conn.execute(
                    "INSERT OR REPLACE INTO research_model_confidence(run_id,model_name,eligibility,loss_score,evidence_count,details_json) VALUES(?,?,?,?,?,?)",
                    (
                        run_id,
                        row["model_name"],
                        row["eligibility"],
                        row.get("loss_score"),
                        row.get("evidence_count", 0),
                        json.dumps(dict(row), default=str, sort_keys=True),
                    ),
                )
            changepoint = diagnostics.get("changepoint") if isinstance(diagnostics.get("changepoint"), Mapping) else {}
            conn.execute(
                "INSERT OR REPLACE INTO research_changepoints(run_id,change_probability,direction_shift_probability,volatility_shift_probability,safe_horizon_hours,status,details_json) VALUES(?,?,?,?,?,?,?)",
                (
                    run_id,
                    changepoint.get("change_probability"),
                    changepoint.get("direction_shift_probability"),
                    changepoint.get("volatility_shift_probability"),
                    changepoint.get("safe_horizon_hours"),
                    changepoint.get("status"),
                    json.dumps(dict(changepoint), default=str, sort_keys=True),
                ),
            )
            mfe_rows = diagnostics.get("mfe_mae") if isinstance(diagnostics.get("mfe_mae"), list) else []
            for row in mfe_rows:
                conn.execute(
                    "INSERT OR REPLACE INTO research_mfe_mae(run_id,horizon_hours,mfe_pips,mae_pips,sample_size,details_json) VALUES(?,?,?,?,?,?)",
                    (
                        run_id,
                        row.get("horizon_hours"),
                        row.get("median_mfe_pips"),
                        row.get("median_mae_pips"),
                        row.get("sample_size", 0),
                        json.dumps(dict(row), default=str, sort_keys=True),
                    ),
                )
            delay_rows = diagnostics.get("entry_delay") if isinstance(diagnostics.get("entry_delay"), list) else []
            for row in delay_rows:
                conn.execute(
                    "INSERT OR REPLACE INTO research_entry_delay(run_id,delay_name,win_rate,net_ev,mae,missed_trade_rate,evidence_count,details_json) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        row.get("delay_name"),
                        row.get("win_rate"),
                        row.get("net_ev"),
                        row.get("mae"),
                        row.get("missed_trade_rate"),
                        row.get("evidence_count", 0),
                        json.dumps(dict(row), default=str, sort_keys=True),
                    ),
                )
            overfit = diagnostics.get("overfitting") if isinstance(diagnostics.get("overfitting"), Mapping) else {}
            conn.execute(
                "INSERT OR REPLACE INTO research_overfitting_ledger(run_id,models_tested,thresholds_tested,feature_combinations,horizons_tested,tp_sl_alternatives,in_sample_score,out_of_sample_score,degradation,overfitting_risk,production_eligibility,details_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    overfit.get("models_tested", 0),
                    overfit.get("thresholds_tested", 0),
                    overfit.get("feature_combinations", 0),
                    overfit.get("horizons_tested", 0),
                    overfit.get("tp_sl_alternatives", 0),
                    overfit.get("in_sample_score"),
                    overfit.get("out_of_sample_score"),
                    overfit.get("degradation"),
                    overfit.get("overfitting_risk"),
                    overfit.get("production_eligibility"),
                    json.dumps(dict(overfit), default=str, sort_keys=True),
                ),
            )
            conn.commit()
        _clear_read_cache()


    def save_v12_snapshot(self, snapshot: ResearchRunSnapshot, *, history_cap: int = 500) -> dict[str, Any]:
        """Insert one immutable V12 snapshot; reject stale or conflicting generations."""
        payload = snapshot.to_dict()
        with sqlite3.connect(str(self.path), timeout=15) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT snapshot_hash,calculation_generation FROM research_run_snapshot_v12 WHERE run_id=?",
                (snapshot.run_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) == snapshot.snapshot_hash and str(existing[1]) == snapshot.calculation_generation:
                    conn.rollback()
                    return {"inserted": False, "duplicate": True, "run_id": snapshot.run_id, "snapshot_hash": snapshot.snapshot_hash}
                conn.rollback()
                raise ImmutableResearchSnapshotError(f"run_id {snapshot.run_id!r} already has different immutable V12 content")
            latest = conn.execute(
                "SELECT candle_time FROM research_run_snapshot_v12 WHERE symbol=? AND timeframe=? ORDER BY candle_time DESC LIMIT 1",
                (snapshot.symbol, snapshot.timeframe),
            ).fetchone()
            if latest is not None and str(snapshot.candle_time) < str(latest[0]):
                conn.rollback()
                raise StaleResearchGenerationError(
                    f"stale V12 generation {snapshot.candle_time}; latest stored candle is {latest[0]}"
                )
            conn.execute(
                """INSERT INTO research_run_snapshot_v12(
                    run_id,calculation_generation,snapshot_hash,broker_time,candle_time,symbol,timeframe,
                    settled_outcome_cutoff,source_hashes_json,configuration_hash,schema_version,
                    module_statuses_json,sample_sizes_json,warnings_json,compact_results_json,full_results_json,created_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot.run_id, snapshot.calculation_generation, snapshot.snapshot_hash, snapshot.broker_time,
                    snapshot.candle_time, snapshot.symbol, snapshot.timeframe, snapshot.settled_outcome_cutoff,
                    json.dumps(payload["source_hashes"], sort_keys=True), snapshot.configuration_hash, snapshot.schema_version,
                    json.dumps(payload["module_statuses"], sort_keys=True), json.dumps(payload["sample_sizes"], sort_keys=True),
                    json.dumps(payload["warnings"], sort_keys=True), json.dumps(payload["compact_results"], default=str, sort_keys=True),
                    json.dumps(payload["full_results"], default=str, sort_keys=True), snapshot.created_at_utc,
                ),
            )
            cap = max(25, min(int(history_cap), 5000))
            conn.execute(
                """DELETE FROM research_run_snapshot_v12 WHERE run_id IN (
                    SELECT run_id FROM research_run_snapshot_v12 ORDER BY candle_time DESC LIMIT -1 OFFSET ?
                )""",
                (cap,),
            )
            conn.commit()
        _clear_read_cache()
        return {"inserted": True, "duplicate": False, "run_id": snapshot.run_id, "snapshot_hash": snapshot.snapshot_hash}

    def latest_v12_snapshot(self, run_id: str | None = None) -> dict[str, Any]:
        query = "SELECT * FROM research_run_snapshot_v12"
        params: tuple[Any, ...] = ()
        if run_id:
            query += " WHERE run_id=?"
            params = (run_id,)
        query += " ORDER BY candle_time DESC LIMIT 1"
        frame = _frame(self.path, query, params)
        if frame.empty:
            return {}
        row = dict(frame.iloc[0])
        for key in ("source_hashes_json", "module_statuses_json", "sample_sizes_json", "warnings_json", "compact_results_json", "full_results_json"):
            try:
                row[key.removesuffix("_json")] = json.loads(str(row.pop(key)))
            except (TypeError, ValueError, json.JSONDecodeError):
                row[key.removesuffix("_json")] = {} if key != "warnings_json" else []
        return row

    def v12_history(self, limit: int = 100) -> pd.DataFrame:
        return _frame(
            self.path,
            "SELECT run_id,calculation_generation,snapshot_hash,broker_time,candle_time,symbol,timeframe,schema_version,module_statuses_json,sample_sizes_json,created_at_utc FROM research_run_snapshot_v12 ORDER BY candle_time DESC LIMIT ?",
            (max(1, min(int(limit), 5000)),),
        )

    def latest_summary(self, run_id: str | None = None) -> dict[str, Any]:
        query = "SELECT summary_json FROM research_run_summary"
        params: tuple[Any, ...] = ()
        if run_id:
            query += " WHERE run_id=?"
            params = (run_id,)
        query += " ORDER BY broker_candle_time DESC LIMIT 1"
        frame = _frame(self.path, query, params)
        if frame.empty:
            return {}
        try:
            return json.loads(str(frame.iloc[0]["summary_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    def history(self, limit: int = 25) -> pd.DataFrame:
        frame = _frame(
            self.path,
            "SELECT summary_json FROM research_run_summary ORDER BY broker_candle_time DESC LIMIT ?",
            (int(limit),),
        )
        if frame.empty:
            return pd.DataFrame()
        records: list[dict[str, Any]] = []
        for value in frame["summary_json"]:
            try:
                decoded = json.loads(str(value))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(decoded, Mapping):
                records.append(dict(decoded))
        return pd.DataFrame(records)

    def horizons(self, run_id: str) -> pd.DataFrame:
        return _frame(
            self.path,
            "SELECT * FROM research_horizon_results WHERE run_id=? ORDER BY horizon_hours",
            (run_id,),
        )

    def models(self, run_id: str) -> pd.DataFrame:
        return _frame(
            self.path,
            "SELECT model_name,eligibility,loss_score,evidence_count FROM research_model_confidence WHERE run_id=? ORDER BY model_name",
            (run_id,),
        )

    def conformal(self, run_id: str) -> pd.DataFrame:
        return _frame(
            self.path,
            "SELECT horizon_hours,target_coverage,actual_coverage,interval_width,coverage_debt,consecutive_violations,status FROM research_conformal_history WHERE run_id=? ORDER BY horizon_hours",
            (run_id,),
        )

    def mfe_mae(self, run_id: str) -> pd.DataFrame:
        return _frame(
            self.path,
            "SELECT horizon_hours,mfe_pips,mae_pips,sample_size FROM research_mfe_mae WHERE run_id=? ORDER BY horizon_hours",
            (run_id,),
        )

    def entry_delay(self, run_id: str) -> pd.DataFrame:
        return _frame(
            self.path,
            "SELECT delay_name,win_rate,net_ev,mae,missed_trade_rate,evidence_count FROM research_entry_delay WHERE run_id=? ORDER BY delay_name",
            (run_id,),
        )

    def overfitting(self, run_id: str) -> dict[str, Any]:
        frame = _frame(
            self.path,
            "SELECT details_json FROM research_overfitting_ledger WHERE run_id=? LIMIT 1",
            (run_id,),
        )
        if frame.empty:
            return {}
        try:
            decoded = json.loads(str(frame.iloc[0]["details_json"]))
            return dict(decoded) if isinstance(decoded, Mapping) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    def promotion_ledger(self, limit: int = 250) -> pd.DataFrame:
        return _frame(
            self.path,
            "SELECT run_id,model_name,action,reason,created_at_utc FROM research_promotion_ledger ORDER BY created_at_utc DESC LIMIT ?",
            (int(limit),),
        )


__all__ = ["ResearchRepository", "StaleResearchGenerationError", "ImmutableResearchSnapshotError"]
