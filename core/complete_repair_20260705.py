"""ADX Quant Pro 2026-07-05 reliability, provenance and migration helpers.

This module is intentionally additive.  It does not create market prices and it
never replaces the protected calculation engines.  It provides shared state,
measured preset selection, safe display fallbacks, lightweight Lunch refresh,
and idempotent persistence structures used by the repaired UI.
"""
from __future__ import annotations
from core.global_symbol_compat import set_legacy_configured_symbols, set_legacy_calculation_symbol

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import logging
import os
import shutil
import sqlite3
import time

import pandas as pd

VERSION = "complete-repair-20260705-v1"
SCHEMA_VERSION = 20260705
PROVIDER_PRIORITY = (
    "FINNHUB", "TWELVE_DATA", "MT5", "ALPHA_VANTAGE",
    "LOCAL_VALID_CACHE",
)
SECONDARY_SYMBOL_POOL: tuple[str, ...] = (
    "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "EURGBP", "EURJPY", "EURCHF",
    "EURAUD", "EURCAD", "EURNZD", "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "AUDJPY",
)
LOW_SPREAD_THRESHOLD_POINTS = 20.0

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "multi_symbol_field10_20260701.sqlite3"
LOG_PATH = ROOT / "data" / "adx_internal_errors_20260705.log"


def _logger() -> logging.Logger:
    logger = logging.getLogger("adx.complete_repair_20260705")
    if not logger.handlers:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_internal_error(area: str, exc: BaseException, **context: Any) -> str:
    """Log full details internally and return a non-sensitive incident id."""
    material = f"{area}|{type(exc).__name__}|{exc}|{time.time_ns()}"
    incident = sha256(material.encode("utf-8", "ignore")).hexdigest()[:12]
    safe_context = {
        str(k): v for k, v in context.items()
        if not any(token in str(k).lower() for token in ("key", "secret", "token", "password", "credential"))
    }
    _logger().exception("incident=%s area=%s context=%s", incident, area, safe_context, exc_info=exc)
    return incident


@dataclass(frozen=True)
class DataProvenance:
    source: str
    original_timestamp: str | None = None
    age_seconds: float | None = None
    freshness_status: str = "UNKNOWN"
    value_status: str = "NO_VALIDATED_VALUE"
    data_quality_score: float = 0.0
    coverage_pct: float = 0.0
    reliability_score: float = 0.0
    fallback_level: int = 7
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fallback_label(*, level: int, status: str, source: str, note: str = "") -> str:
    status = str(status or "NO_VALIDATED_VALUE").upper().replace("_", " ")
    source = str(source or "NO SOURCE").upper().replace("_", " ")
    suffix = f" • {note}" if note else ""
    return f"{status} • L{int(level)} • {source}{suffix}"


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) and abs(number) != float("inf") else None


def _spread_mapping(state: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in (
        "recent_spread_metrics_20260705", "recent_spread_metrics", "symbol_spread_metrics",
        "multi_symbol_spread_quality_20260704", "spread_quality_by_symbol",
    ):
        value = state.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def measured_spread_metrics(state: Mapping[str, Any], symbols: Sequence[str]) -> pd.DataFrame:
    """Return only observed spread measurements; never assert unmeasured spreads."""
    mapping = _spread_mapping(state)
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        raw = mapping.get(symbol) or mapping.get(str(symbol).upper())
        if isinstance(raw, Mapping):
            avg = _finite(raw.get("average_spread") or raw.get("avg_spread") or raw.get("spread_points"))
            sample = int(_finite(raw.get("sample_size")) or 0)
            if avg is None or sample <= 0:
                continue
            rows.append({
                "Symbol": str(symbol).upper(), "Average Spread": avg,
                "Spread Unit": str(raw.get("unit") or raw.get("spread_unit") or "points"),
                "Sample Size": sample, "Measurement Period": str(raw.get("period") or raw.get("measurement_period") or "recent quotes"),
                "Provider": str(raw.get("provider") or "measured provider"),
                "Last Updated": str(raw.get("last_updated") or raw.get("timestamp") or "unknown"),
            })
    return pd.DataFrame(rows)


def _availability_score(state: Mapping[str, Any], symbol: str) -> float:
    score = 0.0
    try:
        from core.multi_symbol_field10_20260701 import saved_symbol_available
        if saved_symbol_available(symbol):
            score += 35.0
    except Exception:
        pass
    provider = state.get("provider_coverage_by_symbol")
    if isinstance(provider, Mapping):
        score += min(25.0, max(0.0, _finite(provider.get(symbol)) or 0.0) * 0.25)
    continuity = state.get("quote_continuity_by_symbol")
    if isinstance(continuity, Mapping):
        score += min(20.0, max(0.0, _finite(continuity.get(symbol)) or 0.0) * 0.20)
    completeness = state.get("candle_completeness_by_symbol")
    if isinstance(completeness, Mapping):
        score += min(20.0, max(0.0, _finite(completeness.get(symbol)) or 0.0) * 0.20)
    return score


def select_secondary_top10(state: Mapping[str, Any]) -> tuple[list[str], pd.DataFrame]:
    """Rank the 15-pair secondary pool using measured availability/quality evidence."""
    spreads = measured_spread_metrics(state, SECONDARY_SYMBOL_POOL)
    spread_lookup = {str(r["Symbol"]): float(r["Average Spread"]) for _, r in spreads.iterrows()} if not spreads.empty else {}
    rows = []
    for order, symbol in enumerate(SECONDARY_SYMBOL_POOL):
        availability = _availability_score(state, symbol)
        spread = spread_lookup.get(symbol)
        spread_quality = 20.0 * max(0.0, min(1.0, (LOW_SPREAD_THRESHOLD_POINTS - spread) / LOW_SPREAD_THRESHOLD_POINTS)) if spread is not None else 0.0
        score = availability + spread_quality
        rows.append({
            "Symbol": symbol, "Selection Score": round(score, 4),
            "Availability Score": round(availability, 4), "Measured Average Spread": spread,
            "Spread Evidence": "MEASURED" if spread is not None else "NOT MEASURED",
            "Pool Order": order,
        })
    ranking = pd.DataFrame(rows).sort_values(["Selection Score", "Pool Order"], ascending=[False, True], kind="mergesort")
    # When evidence is absent, stable pool order is used without claiming superior liquidity/spread.
    selected = ranking.head(10)["Symbol"].tolist()
    return selected, ranking.reset_index(drop=True)


def select_low_spread_top8(state: Mapping[str, Any]) -> tuple[list[str], pd.DataFrame]:
    metrics = measured_spread_metrics(state, SECONDARY_SYMBOL_POOL)
    if metrics.empty:
        return [], metrics
    eligible = metrics.loc[pd.to_numeric(metrics["Average Spread"], errors="coerce") < LOW_SPREAD_THRESHOLD_POINTS].copy()
    eligible = eligible.sort_values(["Average Spread", "Sample Size"], ascending=[True, False], kind="mergesort")
    return eligible.head(8)["Symbol"].tolist(), eligible.reset_index(drop=True)


def build_cache_identity(*, symbols: Sequence[str], primary_symbol: str, timeframe: str,
                         run_id: str, latest_completed_candle: str, provider: str,
                         calculation_mode: str) -> str:
    material = {
        "symbols": [str(s).upper() for s in symbols], "primary_symbol": str(primary_symbol).upper(),
        "timeframe": str(timeframe).upper(), "run_id": str(run_id),
        "latest_completed_candle": str(latest_completed_candle), "provider": str(provider).upper(),
        "calculation_mode": str(calculation_mode).upper(),
    }
    return sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def ensure_canonical_multi_symbol_state(state: MutableMapping[str, Any]) -> dict[str, Any]:
    from core.multi_symbol_field10_20260701 import normalize_selected, normalize_symbol, recover_symbol_universe
    universe = recover_symbol_universe(state)
    selected = normalize_selected(universe.get("selected_symbols") or state.get("multi_symbol_selected_20260701") or [])
    primary = normalize_symbol(universe.get("main_symbol") or (selected[0] if selected else "EURUSD"))
    if primary not in selected:
        selected.insert(0, primary)
    canonical = state.get("canonical_decision_result_20260617") if isinstance(state.get("canonical_decision_result_20260617"), Mapping) else {}
    timeframe = str(canonical.get("timeframe") or state.get("timeframe") or "H1").upper()
    run_id = str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or state.get("multi_symbol_parent_run_id_20260701") or "")
    candle = str(canonical.get("completed_broker_candle") or canonical.get("latest_completed_candle_time") or canonical.get("broker_candle_time") or "")
    provider = str(state.get("active_market_provider_20260705") or state.get("source") or "LOCAL_DATABASE").upper()
    mode = str(state.get("settings_calculation_scope_20260625") or "QUICK").upper()
    payload = {
        "selected_symbols": selected, "primary_symbol": primary, "timeframe": timeframe,
        "provider_priority": list(PROVIDER_PRIORITY), "active_provider": provider,
        "calculation_mode": mode, "run_id": run_id,
        "snapshot_hash": str(canonical.get("snapshot_hash") or canonical.get("source_snapshot_hash") or ""),
        "latest_completed_candle": candle,
        "broker_candle_time": str(canonical.get("broker_candle_time") or candle),
        "cache_identity": build_cache_identity(symbols=selected, primary_symbol=primary, timeframe=timeframe,
                                                run_id=run_id, latest_completed_candle=candle,
                                                provider=provider, calculation_mode=mode),
        "version": VERSION,
    }
    state["canonical_multi_symbol_state_20260705"] = payload
    return payload


def refresh_lunch_snapshot(state: MutableMapping[str, Any]) -> dict[str, Any]:
    """Lightweight refresh: reload persisted evidence and clear render-only caches."""
    active_field = state.get("lunch_active_field_selector_20260624")
    selected = list(state.get("multi_symbol_selected_20260701") or [])
    timeframe = state.get("timeframe")
    report: dict[str, Any] = {"ok": True, "status": "REFRESHED_READ_ONLY", "heavy_calculation_started": False}
    try:
        from core.field10_daily_snapshot_contract_20260702 import load_current_daily_snapshot
        bundle = load_current_daily_snapshot()
        state["field10_latest_persisted_bundle_20260705"] = bundle
        report["field10_rows"] = int(len(bundle.get("current"))) if isinstance(bundle.get("current"), pd.DataFrame) else 0
        report["field10_snapshot_id"] = (bundle.get("metadata") or {}).get("daily_snapshot_id")
    except Exception as exc:
        report.update({"ok": False, "status": "REFRESH_PARTIAL", "incident_id": log_internal_error("lunch_refresh.field10", exc)})
    for key in list(state.keys()):
        name = str(key)
        if name.startswith(("presentation_cache_", "lunch_copy_payload_cache_", "field10_render_cache_", "field11_render_cache_")):
            state.pop(key, None)
    set_legacy_configured_symbols(state, selected)
    if timeframe is not None:
        state["timeframe"] = timeframe
    if active_field:
        state["lunch_active_field_selector_20260624"] = active_field
        state["lunch_active_field_selector_20260624__pending"] = active_field
    report["selected_symbols"] = selected
    report["timeframe"] = timeframe
    report["active_field"] = active_field
    report["refreshed_at_utc"] = pd.Timestamp.now(tz="UTC").isoformat()
    state["lunch_refresh_report_20260705"] = report
    return report


def _backup_database(path: Path) -> str | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")
    backup = backup_dir / f"{path.stem}.pre_20260705_{stamp}{path.suffix}"
    if not backup.exists():
        shutil.copy2(path, backup)
    return str(backup)


def migrate_complete_repair_schema(path: Path | str = DEFAULT_DB_PATH, *, create_backup: bool = True) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = _backup_database(target) if create_backup else None
    started = time.perf_counter()
    conn = sqlite3.connect(target)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("BEGIN IMMEDIATE")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_version_20260705(
                version INTEGER PRIMARY KEY, applied_at_utc TEXT NOT NULL, description TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS canonical_runs_20260705(
                run_id TEXT PRIMARY KEY, snapshot_hash TEXT NOT NULL, primary_symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL, calculation_mode TEXT NOT NULL, latest_completed_candle TEXT NOT NULL,
                broker_candle_time TEXT, selected_symbols_json TEXT NOT NULL, provider_priority_json TEXT NOT NULL,
                active_provider TEXT, status TEXT NOT NULL, created_at_utc TEXT NOT NULL,
                UNIQUE(snapshot_hash,primary_symbol,timeframe,latest_completed_candle,calculation_mode)
            );
            CREATE TABLE IF NOT EXISTS canonical_symbol_results_20260705(
                run_id TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
                latest_completed_candle TEXT NOT NULL, result_json TEXT NOT NULL, provenance_json TEXT NOT NULL,
                status TEXT NOT NULL, created_at_utc TEXT NOT NULL,
                PRIMARY KEY(run_id,symbol,timeframe),
                FOREIGN KEY(run_id) REFERENCES canonical_runs_20260705(run_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS field10_rankings_20260705(
                run_id TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, rank INTEGER,
                score REAL, bias TEXT, expected_value REAL, transition_risk REAL, reliability REAL,
                data_quality REAL, fallback_level INTEGER NOT NULL DEFAULT 0, row_json TEXT NOT NULL,
                PRIMARY KEY(run_id,symbol,timeframe)
            );
            CREATE TABLE IF NOT EXISTS field11_results_20260705(
                run_id TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
                simulator_run_id TEXT, status TEXT NOT NULL, result_json TEXT NOT NULL,
                PRIMARY KEY(run_id,symbol,timeframe)
            );
            CREATE TABLE IF NOT EXISTS provider_status_20260705(
                provider TEXT PRIMARY KEY, configured INTEGER NOT NULL, healthy INTEGER NOT NULL,
                last_success_utc TEXT, fallback_provider TEXT, detail_json TEXT NOT NULL, updated_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS data_quality_metadata_20260705(
                run_id TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
                quality_score REAL, coverage_pct REAL, reliability_score REAL,
                freshness_status TEXT, detail_json TEXT NOT NULL,
                PRIMARY KEY(run_id,symbol,timeframe)
            );
            CREATE TABLE IF NOT EXISTS missing_data_fallback_20260705(
                fallback_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, symbol TEXT, timeframe TEXT,
                field_name TEXT NOT NULL, fallback_level INTEGER NOT NULL, source TEXT NOT NULL,
                value_status TEXT NOT NULL, original_timestamp TEXT, age_seconds REAL,
                quality_score REAL, coverage_pct REAL, reliability_score REAL,
                detail_json TEXT NOT NULL, created_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS timeframe_results_20260705(
                run_id TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
                latest_completed_candle TEXT NOT NULL, result_json TEXT NOT NULL,
                PRIMARY KEY(run_id,symbol,timeframe,latest_completed_candle)
            );
            CREATE TABLE IF NOT EXISTS calculation_progress_20260705(
                run_id TEXT NOT NULL, symbol TEXT NOT NULL, field_name TEXT NOT NULL,
                status TEXT NOT NULL, retry_count INTEGER NOT NULL DEFAULT 0,
                fallback_count INTEGER NOT NULL DEFAULT 0, estimated_count INTEGER NOT NULL DEFAULT 0,
                updated_at_utc TEXT NOT NULL, detail_json TEXT NOT NULL,
                PRIMARY KEY(run_id,symbol,field_name)
            );
            CREATE TABLE IF NOT EXISTS calculation_failures_20260705(
                failure_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, symbol TEXT, field_name TEXT,
                provider TEXT, incident_id TEXT NOT NULL, retryable INTEGER NOT NULL,
                created_at_utc TEXT NOT NULL, detail_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS prediction_outcomes(
                outcome_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL, horizon TEXT NOT NULL, forecast_origin TEXT NOT NULL,
                forecast_value REAL, realized_value REAL, error REAL, absolute_error REAL,
                squared_error REAL, directional_result INTEGER, regime TEXT, data_quality_state TEXT,
                settled_at_utc TEXT, UNIQUE(run_id,symbol,timeframe,horizon,forecast_origin)
            );
            CREATE INDEX IF NOT EXISTS ix_canonical_results_symbol_time
                ON canonical_symbol_results_20260705(symbol,timeframe,latest_completed_candle);
            CREATE INDEX IF NOT EXISTS ix_field10_rank_run_rank ON field10_rankings_20260705(run_id,rank);
            CREATE INDEX IF NOT EXISTS ix_fallback_run_symbol ON missing_data_fallback_20260705(run_id,symbol,timeframe);
            CREATE INDEX IF NOT EXISTS ix_progress_status ON calculation_progress_20260705(run_id,status);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_version_20260705(version,applied_at_utc,description) VALUES(?,?,?)",
            (SCHEMA_VERSION, pd.Timestamp.now(tz="UTC").isoformat(), "Canonical multi-symbol, provenance, progress and Field 10/11 repair schema"),
        )
        conn.commit()
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {
            "ok": True, "status": "MIGRATED", "schema_version": SCHEMA_VERSION,
            "path": str(target), "backup": backup, "table_count": len(tables),
            "required_tables_present": all(name in tables for name in (
                "canonical_runs_20260705", "canonical_symbol_results_20260705", "field10_rankings_20260705",
                "field11_results_20260705", "provider_status_20260705", "data_quality_metadata_20260705",
                "missing_data_fallback_20260705", "timeframe_results_20260705", "calculation_progress_20260705",
                "calculation_failures_20260705", "prediction_outcomes",
            )),
            "elapsed_seconds": round(time.perf_counter() - started, 4), "version": VERSION,
        }
    except Exception as exc:
        conn.rollback()
        return {"ok": False, "status": "ROLLED_BACK", "incident_id": log_internal_error("database_migration", exc, path=str(target)), "path": str(target), "backup": backup}
    finally:
        conn.close()


__all__ = [
    "VERSION", "SCHEMA_VERSION", "PROVIDER_PRIORITY", "SECONDARY_SYMBOL_POOL",
    "LOW_SPREAD_THRESHOLD_POINTS", "DataProvenance", "fallback_label", "log_internal_error",
    "measured_spread_metrics", "select_secondary_top10", "select_low_spread_top8",
    "build_cache_identity", "ensure_canonical_multi_symbol_state", "refresh_lunch_snapshot",
    "migrate_complete_repair_schema",
]
