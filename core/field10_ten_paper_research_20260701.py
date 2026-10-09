"""Lazy, persisted ten-paper shadow validation for Lunch Field 10.

The Settings-owned multi-symbol transaction saves each canonical symbol state,
calculates research diagnostics once per parent run/model version after all
symbols are frozen, and stores read-only audit rows in the existing Field 10
SQLite database. Field 10 rendering only reads those saved rows.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from contextlib import suppress
from pathlib import Path
from typing import Any
from hashlib import sha256
import json
import sqlite3
import time

import numpy as np
import pandas as pd

from core.sqlite_readonly_20260704 import connect_readonly

from core.multi_symbol_field10_20260701 import (
    ACTIVE_KEY,
    DB_PATH,
    MANIFEST_KEY,
    SELECTED_KEY,
    _cache_path,
    _read_cache_payload,
    normalize_selected,
    normalize_symbol,
)
from research_quant.ten_paper_validation_20260701 import (
    MODEL_VERSION, CALCULATION_VERSION, DEFAULT_CONFIG,
    build_ten_paper_validation,
    extract_return_series,
    flatten_validation,
    ledoit_wolf_risk_all,
    resolve_canonical,
)

STATE_KEY = "field10_ten_paper_validation_manifest_20260701"
CURRENT_TABLE_KEY = "field10_ten_paper_current_table_20260701"
HISTORY_TABLE_KEY = "field10_ten_paper_history_table_20260701"
VERSION = "field10-ten-paper-lazy-20260701-v2"


def migrate_research_database(path: Path | str = DB_PATH) -> dict[str, Any]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS field10_research_validation (
                parent_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                broker_timestamp TEXT NOT NULL,
                research_rank INTEGER,
                rank_pool TEXT,
                production_action TEXT,
                research_action TEXT,
                research_permission TEXT,
                conflict_status TEXT,
                research_reliability REAL,
                data_quality_grade TEXT,
                data_quality_score REAL,
                regime_probability REAL,
                regime_entropy REAL,
                expected_regime_duration REAL,
                remaining_regime_duration REAL,
                transition_risk_1h REAL,
                transition_risk_3h REAL,
                transition_risk_6h REAL,
                structural_break_status TEXT,
                break_count INTEGER,
                break_strength REAL,
                drift_status TEXT,
                adaptive_window_size INTEGER,
                state_stability REAL,
                innovation_z REAL,
                brier_score REAL,
                log_loss REAL,
                calibration_error REAL,
                conformal_status TEXT,
                conformal_coverage REAL,
                interval_width REAL,
                dm_p_value REAL,
                dm_candidate_superior INTEGER,
                spa_p_value REAL,
                spa_superior INTEGER,
                correlation_cluster TEXT,
                duplicate_exposure_penalty REAL,
                cvar_95 REAL,
                tail_risk_grade TEXT,
                calculation_status TEXT,
                explanation TEXT,
                canonical_run_id TEXT,
                source_id TEXT,
                result_hash TEXT,
                model_version TEXT NOT NULL,
                result_json TEXT NOT NULL,
                elapsed_seconds REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                PRIMARY KEY(parent_run_id, symbol, broker_timestamp, model_version)
            );
            CREATE INDEX IF NOT EXISTS idx_field10_research_current
                ON field10_research_validation(parent_run_id, research_rank, symbol);
            CREATE INDEX IF NOT EXISTS idx_field10_research_history
                ON field10_research_validation(symbol, broker_timestamp DESC);
            CREATE TABLE IF NOT EXISTS field10_research_model_registry (
                model_version TEXT PRIMARY KEY,
                calculation_version TEXT NOT NULL,
                shadow_mode INTEGER NOT NULL,
                feature_flags_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS field10_research_experiments (
                experiment_id TEXT PRIMARY KEY,
                parent_run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                model_version TEXT NOT NULL,
                canonical_run_id TEXT,
                broker_timestamp TEXT,
                candidate_count INTEGER NOT NULL DEFAULT 0,
                candidate_names_json TEXT NOT NULL,
                best_candidate TEXT,
                spa_statistic REAL,
                spa_p_value REAL,
                bootstrap_draws INTEGER,
                block_length INTEGER,
                settlement_verified INTEGER NOT NULL DEFAULT 0,
                out_of_sample_verified INTEGER NOT NULL DEFAULT 0,
                validation_start TEXT,
                validation_end TEXT,
                promotion_status TEXT NOT NULL,
                parameter_hash TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_field10_experiment_parent
                ON field10_research_experiments(parent_run_id, symbol);
            """
        )
        existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(field10_research_validation)").fetchall()}
        if "rank_pool" not in existing:
            conn.execute("ALTER TABLE field10_research_validation ADD COLUMN rank_pool TEXT")
        flags_json = json.dumps(DEFAULT_CONFIG.flags.__dict__, sort_keys=True, separators=(",", ":"))
        conn.execute(
            """INSERT OR REPLACE INTO field10_research_model_registry(
                model_version,calculation_version,shadow_mode,feature_flags_json,status,created_at
            ) VALUES(?,?,?,?,?,?)""",
            (MODEL_VERSION, CALCULATION_VERSION, 1, flags_json, "SHADOW_VALIDATION", pd.Timestamp.now(tz="UTC").isoformat()),
        )
        conn.commit()
    return {"ok": True, "path": str(path), "version": VERSION}


def _selected(state: Mapping[str, Any]) -> tuple[str, list[str]]:
    manifest = state.get(MANIFEST_KEY) if isinstance(state.get(MANIFEST_KEY), Mapping) else {}
    parent_run_id = str(manifest.get("parent_run_id") or "")
    symbols = normalize_selected(manifest.get("selected_symbols") or state.get(SELECTED_KEY))
    if not symbols:
        active = normalize_symbol(state.get(ACTIVE_KEY) or state.get("symbol") or "EURUSD")
        symbols = [active]
    return parent_run_id, symbols


def _saved_state(symbol: str) -> Mapping[str, Any] | None:
    path = _cache_path(symbol)
    if not path.is_file():
        return None
    try:
        payload = _read_cache_payload(path)
        value = payload.get("state")
        return value if isinstance(value, Mapping) else None
    except Exception:
        return None


def _existing_symbols(parent_run_id: str, path: Path | str) -> set[str]:
    if not parent_run_id:
        return set()
    with sqlite3.connect(str(path), timeout=30) as conn:
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM field10_research_validation WHERE parent_run_id=? AND model_version=?",
            (parent_run_id, MODEL_VERSION),
        ).fetchall()
    return {str(row[0]) for row in rows}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _persist_result(parent_run_id: str, result: Mapping[str, Any], elapsed: float, path: Path | str) -> None:
    flat = flatten_validation(result)
    created = pd.Timestamp.now(tz="UTC").isoformat()
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    with sqlite3.connect(str(path), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(
            """INSERT OR REPLACE INTO field10_research_validation(
                parent_run_id,symbol,timeframe,broker_timestamp,research_rank,rank_pool,
                production_action,research_action,research_permission,conflict_status,
                research_reliability,data_quality_grade,data_quality_score,
                regime_probability,regime_entropy,expected_regime_duration,remaining_regime_duration,
                transition_risk_1h,transition_risk_3h,transition_risk_6h,
                structural_break_status,break_count,break_strength,drift_status,adaptive_window_size,
                state_stability,innovation_z,brier_score,log_loss,calibration_error,
                conformal_status,conformal_coverage,interval_width,dm_p_value,dm_candidate_superior,
                spa_p_value,spa_superior,correlation_cluster,duplicate_exposure_penalty,cvar_95,
                tail_risk_grade,calculation_status,explanation,canonical_run_id,source_id,
                result_hash,model_version,result_json,elapsed_seconds,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                parent_run_id, str(flat.get("Symbol") or ""), str(flat.get("Timeframe") or "H1"),
                str(flat.get("Broker Timestamp") or ""), None, None,
                str(flat.get("Production Action") or ""), str(flat.get("Research Action") or ""),
                str(flat.get("Research Permission") or ""), str(flat.get("Conflict") or ""),
                _number(flat.get("Research Reliability")), str(flat.get("Research Data Quality") or "D"),
                _number(flat.get("Research Data Quality Score")), _number(flat.get("Regime Probability")),
                _number(flat.get("Regime Entropy")), _number(flat.get("Expected Regime Duration")),
                _number(flat.get("Estimated Remaining Duration")), _number(flat.get("Transition Risk 1H")),
                _number(flat.get("Transition Risk 3H")), _number(flat.get("Transition Risk 6H")),
                str(flat.get("Structural Break Status") or ""), int(flat.get("Break Count") or 0),
                _number(flat.get("Break Strength")), str(flat.get("Drift Status") or ""),
                int(flat.get("Adaptive Window Size") or 0), _number(flat.get("State Stability")),
                _number(flat.get("Innovation Z")), _number(flat.get("Brier Score")),
                _number(flat.get("Log Loss")), _number(flat.get("Calibration Error")),
                str(flat.get("Conformal Status") or ""), _number(flat.get("Conformal Coverage")),
                _number(flat.get("Interval Width")), _number(flat.get("DM p-value")),
                int(bool(flat.get("DM Candidate Superior"))), _number(flat.get("SPA p-value")),
                int(bool(flat.get("SPA Superior"))), str(flat.get("Correlation Cluster") or ""),
                _number(flat.get("Duplicate Exposure Penalty")), _number(flat.get("CVaR 95")),
                str(flat.get("Tail Risk Grade") or ""), str(flat.get("Calculation Status") or ""),
                str(flat.get("Research Explanation") or ""), str(flat.get("Canonical Run ID") or ""),
                str(result.get("source_snapshot_hash") or ""), str(flat.get("Result Hash") or ""),
                MODEL_VERSION, payload, float(elapsed), created,
            ),
        )
        spa = result.get("hansen_spa") if isinstance(result.get("hansen_spa"), Mapping) else {}
        candidates = list(spa.get("candidate_names") or [])
        parameter_hash = sha256(json.dumps({
            "model_version": MODEL_VERSION, "candidates": candidates,
            "bootstrap_draws": spa.get("bootstrap_draws"), "block_length": spa.get("block_length"),
        }, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        experiment_id = sha256(f"{parent_run_id}|{result.get('symbol')}|{result.get('canonical_run_id')}|{MODEL_VERSION}|{parameter_hash}".encode("utf-8")).hexdigest()[:32]
        conn.execute(
            """INSERT OR REPLACE INTO field10_research_experiments(
                experiment_id,parent_run_id,symbol,model_version,canonical_run_id,broker_timestamp,
                candidate_count,candidate_names_json,best_candidate,spa_statistic,spa_p_value,
                bootstrap_draws,block_length,settlement_verified,out_of_sample_verified,
                validation_start,validation_end,promotion_status,parameter_hash,result_json,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                experiment_id,parent_run_id,str(result.get("symbol") or ""),MODEL_VERSION,
                str(result.get("canonical_run_id") or ""),str(result.get("completed_candle_time") or ""),
                int(spa.get("candidate_count") or 0),json.dumps(candidates, ensure_ascii=False),
                str(spa.get("best_candidate") or ""),_number(spa.get("spa_statistic")),_number(spa.get("spa_p_value")),
                int(spa.get("bootstrap_draws") or 0),int(spa.get("block_length") or 0),
                int(bool(spa.get("settlement_verified"))),int(bool(spa.get("out_of_sample_verified"))),
                str(spa.get("validation_start") or ""),str(spa.get("validation_end") or ""),
                str(spa.get("promotion_status") or "RESEARCH_ONLY"),parameter_hash,
                json.dumps(spa, ensure_ascii=False, sort_keys=True, default=str),created,
            ),
        )
        conn.commit()


def _rank(parent_run_id: str, path: Path | str) -> None:
    """Rank eligible/caution and blocked research rows in separate pools."""
    with sqlite3.connect(str(path), timeout=30) as conn:
        rows = conn.execute(
            """SELECT symbol,research_reliability,data_quality_score,COALESCE(cvar_95,0),
                      COALESCE(duplicate_exposure_penalty,0),research_permission,calculation_status
               FROM field10_research_validation
               WHERE parent_run_id=? AND model_version=?""",
            (parent_run_id, MODEL_VERSION),
        ).fetchall()
        if not rows:
            return
        frame = pd.DataFrame(rows, columns=[
            "symbol", "reliability", "quality", "cvar", "duplicate_penalty", "permission", "status"
        ])
        for column in ("reliability", "quality", "cvar", "duplicate_penalty"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        frame["eligibility"] = frame["permission"].map({"ALLOWED": 2, "CAUTION": 1, "BLOCKED": 0}).fillna(0)
        frame["status_gate"] = frame["status"].map({"PASS": 2, "WARNING": 1, "FAIL": 0}).fillna(0)
        frame["rank_pool"] = np.where(
            frame["eligibility"].gt(0) & frame["status_gate"].gt(0),
            "ELIGIBLE_OR_CAUTION", "BLOCKED_OR_FAILED",
        )
        frame["score"] = (
            frame["eligibility"] * 1000.0 + frame["status_gate"] * 100.0
            + frame["quality"] * 0.45 + frame["reliability"] * 0.45
            - frame["duplicate_penalty"] * 10.0 - frame["cvar"].abs() * 10.0
        )
        frame = frame.sort_values(
            ["rank_pool", "score", "quality", "reliability", "cvar", "duplicate_penalty", "symbol"],
            ascending=[False, False, False, False, True, True, True], kind="mergesort",
        )
        frame["rank"] = frame.groupby("rank_pool", sort=False).cumcount() + 1
        conn.execute("BEGIN IMMEDIATE")
        try:
            for row in frame.itertuples(index=False):
                conn.execute(
                    "UPDATE field10_research_validation SET research_rank=?,rank_pool=? WHERE parent_run_id=? AND symbol=? AND model_version=?",
                    (int(row.rank), str(row.rank_pool), parent_run_id, str(row.symbol), MODEL_VERSION),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def ensure_field10_research_validation(
    state: MutableMapping[str, Any], *, force: bool = False, path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Calculate the ten-paper layer once inside the explicit multi-symbol run."""
    migrate_research_database(path)
    parent_run_id, symbols = _selected(state)
    if not parent_run_id:
        report = {"ok": False, "status": "NO_PARENT_RUN", "symbols": symbols, "version": VERSION}
        state[STATE_KEY] = report
        return report
    existing = _existing_symbols(parent_run_id, path)
    missing = symbols if force else [symbol for symbol in symbols if symbol not in existing]
    if not missing:
        report = {
            "ok": True, "status": "CACHED", "parent_run_id": parent_run_id,
            "symbols": symbols, "calculated_symbols": 0, "model_version": MODEL_VERSION,
        }
        state[STATE_KEY] = report
        return report

    started = time.perf_counter()
    saved_states: dict[str, Mapping[str, Any]] = {}
    returns: dict[str, pd.Series] = {}
    errors: dict[str, str] = {}
    active_symbol = normalize_symbol(state.get(ACTIVE_KEY) or state.get("symbol") or (symbols[0] if symbols else "EURUSD"))
    for symbol in symbols:
        value = _saved_state(symbol)
        if value is None and symbol == active_symbol:
            # v9 fallback: the active symbol may have just been calculated in this
            # same run before its compressed cache is readable. Use the current
            # in-memory state, after repairing canonical identity, instead of
            # failing with saved canonical symbol state unavailable.
            try:
                from core.v9_architecture_guard_20260702 import publish_v9_canonical_state
                publish_v9_canonical_state(state, force=True, reason="field10_research_active_symbol")
            except Exception:
                pass
            value = dict(state)
        if value is None:
            errors[symbol] = "saved canonical symbol state is unavailable"
            continue
        try:
            from core.v9_architecture_guard_20260702 import build_v9_canonical
            repaired_canonical = build_v9_canonical(value)
            if isinstance(value, dict):
                value["canonical_decision_result_20260617"] = repaired_canonical
                value["last_valid_canonical_decision_result_20260617"] = repaired_canonical
                value["canonical_decision_result"] = repaired_canonical
        except Exception:
            pass
        saved_states[symbol] = value
        series = extract_return_series(value)
        if not series.empty:
            returns[symbol] = series

    portfolio_risk = ledoit_wolf_risk_all(returns) if len(returns) >= 2 else {}
    calculated = 0
    per_symbol_seconds: dict[str, float] = {}
    for symbol in missing:
        symbol_state = saved_states.get(symbol)
        if symbol_state is None:
            continue
        symbol_started = time.perf_counter()
        canonical = resolve_canonical(symbol_state)
        result = build_ten_paper_validation(
            symbol_state, canonical, cross_symbol_returns=returns,
            portfolio_risk=portfolio_risk.get(symbol),
        )
        elapsed = time.perf_counter() - symbol_started
        per_symbol_seconds[symbol] = round(elapsed, 6)
        _persist_result(parent_run_id, result, elapsed, path)
        calculated += 1
    _rank(parent_run_id, path)
    elapsed_total = time.perf_counter() - started
    report = {
        "ok": calculated > 0 or bool(existing),
        "status": "COMPLETED" if not errors else ("PARTIAL" if calculated or existing else "FAILED"),
        "parent_run_id": parent_run_id, "symbols": symbols,
        "calculated_symbols": calculated, "cached_symbols": len(existing),
        "errors": errors, "elapsed_seconds": round(elapsed_total, 6),
        "per_symbol_seconds": per_symbol_seconds, "model_version": MODEL_VERSION,
        "version": VERSION, "lazy_trigger": "RUN_CALCULATION_TRANSACTION",
    }
    state[STATE_KEY] = report
    return report


_CURRENT_COLUMNS = """
research_rank AS [Research Rank],rank_pool AS [Rank Pool],symbol AS Symbol,timeframe AS Timeframe,
broker_timestamp AS [Broker Timestamp],production_action AS [Production Action],
research_action AS [Research Action],research_permission AS [Research Permission],
conflict_status AS Conflict,research_reliability AS [Research Reliability],
data_quality_grade AS [Research Data Quality],data_quality_score AS [Research Data Quality Score],
regime_probability AS [Regime Probability],regime_entropy AS [Regime Entropy],
expected_regime_duration AS [Expected Regime Duration],remaining_regime_duration AS [Estimated Remaining Duration],
transition_risk_1h AS [Transition Risk 1H],transition_risk_3h AS [Transition Risk 3H],
transition_risk_6h AS [Transition Risk 6H],structural_break_status AS [Structural Break Status],
break_count AS [Break Count],break_strength AS [Break Strength],drift_status AS [Drift Status],
adaptive_window_size AS [Adaptive Window Size],state_stability AS [State Stability],innovation_z AS [Innovation Z],
brier_score AS [Brier Score],log_loss AS [Log Loss],calibration_error AS [Calibration Error],
conformal_status AS [Conformal Status],conformal_coverage AS [Conformal Coverage],interval_width AS [Interval Width],
dm_p_value AS [DM p-value],dm_candidate_superior AS [DM Candidate Superior],
spa_p_value AS [SPA p-value],spa_superior AS [SPA Superior],correlation_cluster AS [Correlation Cluster],
duplicate_exposure_penalty AS [Duplicate Exposure Penalty],cvar_95 AS [CVaR 95],tail_risk_grade AS [Tail Risk Grade],
calculation_status AS [Calculation Status],explanation AS [Research Explanation],canonical_run_id AS [Canonical Run ID],
source_id AS [Source ID],model_version AS [Model Version],result_hash AS [Result Hash],elapsed_seconds AS [Research Seconds]
"""


def load_field10_research_tables(
    state: MutableMapping[str, Any] | None = None, *, parent_run_id: str | None = None,
    symbol: str | None = None, path: Path | str = DB_PATH,
) -> dict[str, pd.DataFrame]:
    state = state if state is not None else {}
    if parent_run_id is None or symbol is None:
        derived_parent, symbols = _selected(state)
        parent_run_id = parent_run_id or derived_parent
        symbol = symbol or normalize_symbol(state.get(ACTIVE_KEY) or (symbols[0] if symbols else "EURUSD"))
    symbol = normalize_symbol(symbol)
    with connect_readonly(path, timeout=30) as conn:
        current = pd.read_sql_query(
            f"SELECT {_CURRENT_COLUMNS} FROM field10_research_validation WHERE parent_run_id=? AND model_version=? ORDER BY CASE WHEN rank_pool='ELIGIBLE_OR_CAUTION' THEN 0 ELSE 1 END, research_rank ASC,symbol",
            conn, params=(str(parent_run_id or ""), MODEL_VERSION),
        ) if parent_run_id else pd.DataFrame()
        history = pd.read_sql_query(
            f"SELECT {_CURRENT_COLUMNS} FROM field10_research_validation WHERE symbol=? AND model_version=? ORDER BY broker_timestamp DESC LIMIT 600",
            conn, params=(symbol, MODEL_VERSION),
        )
        audit = pd.read_sql_query(
            "SELECT symbol AS Symbol,result_json AS [Result JSON] FROM field10_research_validation WHERE parent_run_id=? AND model_version=? ORDER BY CASE WHEN rank_pool='ELIGIBLE_OR_CAUTION' THEN 0 ELSE 1 END, research_rank ASC,symbol",
            conn, params=(str(parent_run_id or ""), MODEL_VERSION),
        ) if parent_run_id else pd.DataFrame()
    if state is not None:
        state[CURRENT_TABLE_KEY] = current
        state[HISTORY_TABLE_KEY] = history
    return {"current": current, "history": history, "audit": audit}


def load_research_registries(*, parent_run_id: str | None = None, path: Path | str = DB_PATH) -> dict[str, pd.DataFrame]:
    with connect_readonly(path, timeout=30) as conn:
        models = pd.read_sql_query(
            "SELECT * FROM field10_research_model_registry ORDER BY created_at DESC", conn,
        )
        if parent_run_id:
            experiments = pd.read_sql_query(
                "SELECT * FROM field10_research_experiments WHERE parent_run_id=? ORDER BY symbol,created_at DESC",
                conn, params=(parent_run_id,),
            )
        else:
            experiments = pd.read_sql_query(
                "SELECT * FROM field10_research_experiments ORDER BY created_at DESC LIMIT 1000", conn,
            )
    return {"models": models, "experiments": experiments}


def research_integrity_rows(state: Mapping[str, Any], *, path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    parent_run_id, symbols = _selected(state)
    if not parent_run_id:
        return [{"Field": 10, "Status": "FAIL", "Check": "Parent run", "Message": "No multi-symbol parent run is saved"}]
    with sqlite3.connect(str(path), timeout=30) as conn:
        rows = conn.execute(
            "SELECT symbol,calculation_status,canonical_run_id,broker_timestamp,model_version,result_hash FROM field10_research_validation WHERE parent_run_id=? AND model_version=?",
            (parent_run_id, MODEL_VERSION),
        ).fetchall()
    by_symbol = {str(row[0]): row for row in rows}
    result: list[dict[str, Any]] = []
    for symbol in symbols:
        row = by_symbol.get(symbol)
        if row is None:
            result.append({"Field": 10, "Symbol": symbol, "Status": "WARNING", "Check": "Research publication", "Message": "Not calculated yet; open Field 10 to run the lazy shadow layer"})
            continue
        status = str(row[1] or "WARNING")
        messages = []
        if not row[2]: messages.append("canonical run_id missing")
        if not row[3]: messages.append("broker timestamp missing")
        if row[4] != MODEL_VERSION: messages.append("model version mismatch")
        if not row[5]: messages.append("result hash missing")
        result.append({
            "Field": 10, "Symbol": symbol,
            "Status": "FAIL" if messages else status,
            "Check": "Canonical identity + research publication",
            "Message": "; ".join(messages) or "Research result is versioned, hashed and linked to the canonical completed candle",
        })
    return result


__all__ = [
    "STATE_KEY", "CURRENT_TABLE_KEY", "HISTORY_TABLE_KEY", "VERSION", "migrate_research_database",
    "ensure_field10_research_validation", "load_field10_research_tables", "load_research_registries", "research_integrity_rows",
]
