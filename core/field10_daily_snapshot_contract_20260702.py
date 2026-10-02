"""Authoritative immutable morning publication contract for Lunch Field 10.

This module is additive. It consumes the already-published protected Field 10,
Field 1 Table 4, Field 3, canonical, and ten-paper research evidence. It does
not replace the production BUY/SELL/WAIT action. The authoritative morning
publication is append-only and survives Streamlit/process restarts in SQLite.

Heavy work belongs to the Settings multi-symbol run. UI functions in this
module are read-only database queries.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import math
import os
import sqlite3

import numpy as np
import pandas as pd

from core.field10_adaptive_regime_metrics_20260702 import (
    compute_adaptive_regime_metrics,
    coalesce_metric,
)
from core.multi_symbol_field10_20260701 import (
    DB_PATH,
    PROVIDER_ALIASES,
    _cache_path,
    _read_cache_payload,
    normalize_symbol,
)
from core.timeframe_window_contract_20260706 import (
    TIMEFRAME_SECONDS,
    calculation_eligibility,
    coverage_metadata,
    minimum_calculation_candles,
    normalize_timeframe,
    required_candles,
    selected_timeframe,
    window_contract,
)

MORNING_LOCK_HOUR = int(os.getenv("FIELD10_MORNING_LOCK_HOUR", "3"))
MORNING_LOCK_MINUTE = int(os.getenv("FIELD10_MORNING_LOCK_MINUTE", "0"))
DAY_END_REVIEW_HOUR = int(os.getenv("FIELD10_DAY_END_REVIEW_HOUR", "23"))
TIMEFRAME = "RUNTIME_SELECTED"  # legacy export; never used as a runtime selector
HIGHER_STANDARD_REQUIRED_CANDLES = 600  # legacy H1 compatibility alias only
MODEL_VERSION = "field10-daily-snapshot-20260703-v2"
FORMULA_VERSION = "institutional-morning-score-20260703-v2"
THRESHOLD_VERSION = "field10-eligibility-thresholds-20260702-v1"
CONTRACT_VERSION = "one-morning-one-decision-20260702-v1"


@dataclass(frozen=True)
class SnapshotThresholds:
    # The morning ranking is intentionally immutable until the 23:00 review.
    # A completed child snapshot can therefore be several hours old without
    # becoming invalid merely because the Streamlit page reran later.
    maximum_stale_hours: float = 24.0
    maximum_spread_percentile: float = 95.0
    maximum_absolute_spread: float = 20.0
    severe_changepoint_probability: float = 0.65
    severe_structural_break_strength: float = 0.75
    minimum_post_break_sample: int = 96
    minimum_calibration_samples: int = 60
    minimum_conformal_samples: int = 60
    minimum_settled_accuracy_samples: int = 20
    strong_calibrated_probability: float = 70.0
    strong_regime_persistence: float = 70.0
    grade_a_plus: float = 85.0
    grade_a: float = 78.0
    grade_b: float = 70.0
    grade_c: float = 60.0
    critical_components: tuple[str, ...] = (
        "regime_persistence",
        "calibrated_bias_probability",
        "data_quality",
        "transition_safety",
    )


@dataclass(frozen=True)
class ScoreWeights:
    regime_persistence: float = 18.0
    calibrated_bias_probability: float = 15.0
    settled_forecast_accuracy: float = 12.0
    evidence_agreement: float = 10.0
    data_quality: float = 10.0
    spread_execution_quality: float = 8.0
    transition_safety: float = 8.0
    conformal_coverage_sharpness: float = 7.0
    tail_risk_safety: float = 7.0
    unique_exposure_score: float = 5.0


DEFAULT_THRESHOLDS = SnapshotThresholds()
DEFAULT_WEIGHTS = ScoreWeights()

CURRENT_COLUMNS = [
    "Daily Rank", "Expected Return 24H (%)", "Expected Return 36H (%)", "Expected Value 6H (%)",
    "Risk-Adjusted EV 6H (%)", "Probability of Profit 1H (%)", "Probability of Profit 6H (%)",
    "Probability of Profit 12H (%)", "Probability Reach EV 1H (%)", "Probability Reach EV 6H (%)",
    "Probability Reach EV 12H (%)", "EV Target 1H (%)", "EV Target 6H (%)", "EV Target 12H (%)",
    "Observed Tick Volume 12H", "Volume 12H Z-Score", "Volume Data Source", "EV Model Version",
    "Probability Calibration Status", "Unexpected Situation Status", "Unexpected Situation Severity",
    "Validation Permission", "Evidence Sample Size",
    "Symbol", "Role", "Daily Grade", "Institutional Morning Score",
    "Existing Rank Score", "Stable Daily Bias", "Less-Risky Bias", "Entry Permission",
    "Safety Veto", "Higher Standard Regime", "Selected-Timeframe Completion", "Required Candle Count", "Available Candle Count", "Timeframe", "Coverage Percent", "600-H1 Completion", "Regime Probability",
    "Regime Entropy", "Posterior Margin", "Regime Age", "Expected Regime Duration",
    "Estimated Remaining Duration", "Transition Risk 1H", "Transition Risk 3H",
    "Transition Risk 6H", "Transition Risk 24H", "Expected Return 12H (%)",
    "Calibrated Bias Probability", "Brier Score",
    "Forecast Accuracy 1H", "Forecast Accuracy 3H", "Forecast Accuracy 6H",
    "Technical Bias", "Technical Reliability", "Sentiment Bias", "Sentiment Reliability",
    "Session Bias", "Session Reliability", "Evidence Agreement", "Conflict Index",
    "Conformal Coverage", "Conformal Interval Width", "Structural Break Status",
    "Changepoint Probability", "Data Quality Grade", "Spread Percentile", "CVaR 95%",
    "Correlation Cluster", "Duplicate Exposure Penalty", "Lock Status",
    "Locked At Broker Time", "Locked Until Broker Time", "Universe Hash", "Snapshot Hash",
    "Canonical Run ID", "Completed Broker Candle", "Explanation", "Publication Status",
]

HISTORY_COLUMNS = [
    "Broker Day", "Symbol", "Original Morning Rank", "Original Morning Score",
    "Original Bias", "Original Less-Risky Bias", "Outcome Settled Status",
    "Actual 1H Direction", "Actual 3H Direction", "Actual 6H Direction",
    "Day-Close Direction", "Correct 1H", "Correct 3H", "Correct 6H", "MFE", "MAE",
    "Spread-Adjusted Outcome", "Calibration Error", "Rank Stability",
    "Previous-Day Rank Change", "Daily Grade", "Model Version", "Formula Version",
    "Universe Hash", "Snapshot Hash",
]


def _safe_float(value: Any, *, percent: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if percent and abs(number) <= 1.0:
        number *= 100.0
    return float(number)


def _clip100(value: Any) -> float | None:
    number = _safe_float(value, percent=True)
    return None if number is None else float(np.clip(number, 0.0, 100.0))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, pd.DataFrame):
        return [_json_safe(v) for v in value.to_dict("records")]
    if isinstance(value, pd.Series):
        return [_json_safe(v) for v in value.tolist()]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if value is pd.NA or (isinstance(value, float) and math.isnan(value)):
        return None
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def deterministic_hash(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=8.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    conn.row_factory = sqlite3.Row
    return conn


def _connect_readonly(path: Path | str) -> sqlite3.Connection:
    """Open the persisted contract without creating files or changing PRAGMAs."""
    resolved = Path(path).resolve()
    conn = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True, timeout=8.0)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    conn.row_factory = sqlite3.Row
    return conn


def _require_daily_snapshot_schema(path: Path | str, *, initialize_for_writer: bool = False) -> None:
    """Verify parent schema; explicit Settings-owned writers may initialize it.

    Read-only render/load paths never migrate. The initialization option exists
    only for the authoritative parent publisher and its repair workflow.
    """
    required = {"field10_daily_snapshot", "field10_daily_snapshot_symbol", "field10_daily_score_component", "field10_daily_safety_event"}
    try:
        with _connect_readonly(path) as conn:
            present = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.OperationalError:
        present = set()
    missing = sorted(required - present)
    if missing and initialize_for_writer:
        migrate_daily_snapshot_database(path)
        with _connect_readonly(path) as conn:
            present = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = sorted(required - present)
    if missing:
        raise RuntimeError(f"Field 10 deployment migration is required; missing tables: {missing}")


def migrate_daily_snapshot_database(path: Path | str = DB_PATH) -> dict[str, Any]:
    """Migration-safe creation of append-only Field 10 daily contract tables."""
    with _connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS field10_daily_snapshot (
                daily_snapshot_id TEXT PRIMARY KEY,
                broker_day TEXT NOT NULL UNIQUE,
                cutoff_broker_time TEXT NOT NULL,
                latest_completed_h1 TEXT NOT NULL,
                ordered_symbol_universe_json TEXT NOT NULL,
                universe_hash TEXT NOT NULL,
                main_symbol TEXT NOT NULL,
                secondary_symbols_json TEXT NOT NULL,
                provider_aliases_json TEXT NOT NULL,
                symbol_count INTEGER NOT NULL,
                parent_run_id TEXT NOT NULL,
                child_run_ids_json TEXT NOT NULL,
                canonical_run_ids_json TEXT NOT NULL,
                source_ids_json TEXT NOT NULL,
                snapshot_hashes_json TEXT NOT NULL,
                model_version TEXT NOT NULL,
                formula_version TEXT NOT NULL,
                threshold_version TEXT NOT NULL,
                content_hash TEXT NOT NULL UNIQUE,
                publication_status TEXT NOT NULL,
                published_at_broker_time TEXT NOT NULL,
                locked_until_broker_time TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at_broker_time TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_f10_snapshot_day_status
                ON field10_daily_snapshot(broker_day DESC, publication_status);
            CREATE INDEX IF NOT EXISTS idx_f10_snapshot_universe
                ON field10_daily_snapshot(universe_hash, broker_day DESC);

            CREATE TABLE IF NOT EXISTS field10_daily_snapshot_symbol (
                daily_snapshot_id TEXT NOT NULL,
                broker_day TEXT NOT NULL,
                symbol TEXT NOT NULL,
                role TEXT NOT NULL,
                daily_rank INTEGER,
                daily_grade TEXT NOT NULL,
                institutional_score REAL,
                existing_rank_score REAL,
                eligibility_status TEXT NOT NULL,
                trade_permission TEXT NOT NULL,
                stable_daily_bias TEXT,
                less_risky_bias TEXT,
                higher_standard_regime TEXT,
                sample_count INTEGER NOT NULL DEFAULT 0,
                sample_complete_status TEXT NOT NULL,
                completed_candle TEXT,
                canonical_run_id TEXT,
                source_id TEXT,
                snapshot_hash TEXT,
                correlation_cluster TEXT,
                transition_risk_24h REAL,
                expected_return_12h REAL,
                expected_return_24h REAL,
                expected_return_36h REAL,
                content_hash TEXT NOT NULL,
                row_json TEXT NOT NULL,
                score_explanation_json TEXT NOT NULL,
                PRIMARY KEY(daily_snapshot_id, symbol),
                FOREIGN KEY(daily_snapshot_id) REFERENCES field10_daily_snapshot(daily_snapshot_id)
            );
            CREATE INDEX IF NOT EXISTS idx_f10_snapshot_symbol_day_rank
                ON field10_daily_snapshot_symbol(broker_day DESC, daily_rank, symbol);
            CREATE INDEX IF NOT EXISTS idx_f10_snapshot_symbol_status
                ON field10_daily_snapshot_symbol(eligibility_status, symbol, broker_day DESC);

            CREATE TABLE IF NOT EXISTS field10_daily_score_component (
                daily_snapshot_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                component_name TEXT NOT NULL,
                component_value REAL,
                configured_weight REAL NOT NULL,
                available INTEGER NOT NULL,
                critical INTEGER NOT NULL,
                contribution REAL,
                status TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                PRIMARY KEY(daily_snapshot_id, symbol, component_name),
                FOREIGN KEY(daily_snapshot_id, symbol)
                    REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id, symbol)
            );

            CREATE TABLE IF NOT EXISTS field10_daily_safety_event (
                event_id TEXT PRIMARY KEY,
                daily_snapshot_id TEXT,
                broker_day TEXT NOT NULL,
                symbol TEXT NOT NULL,
                observed_at_broker_time TEXT NOT NULL,
                safety_veto TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE,
                FOREIGN KEY(daily_snapshot_id) REFERENCES field10_daily_snapshot(daily_snapshot_id)
            );
            CREATE INDEX IF NOT EXISTS idx_f10_safety_latest
                ON field10_daily_safety_event(broker_day DESC, symbol, observed_at_broker_time DESC);

            CREATE TABLE IF NOT EXISTS field10_daily_outcome (
                daily_snapshot_id TEXT NOT NULL,
                broker_day TEXT NOT NULL,
                symbol TEXT NOT NULL,
                settlement_status TEXT NOT NULL,
                settled_at_broker_time TEXT,
                actual_1h_direction TEXT,
                actual_3h_direction TEXT,
                actual_6h_direction TEXT,
                day_close_direction TEXT,
                correct_1h INTEGER,
                correct_3h INTEGER,
                correct_6h INTEGER,
                mfe REAL,
                mae REAL,
                spread_adjusted_outcome REAL,
                slippage_adjusted_outcome REAL,
                calibration_error REAL,
                outcome_hash TEXT,
                outcome_json TEXT NOT NULL,
                PRIMARY KEY(daily_snapshot_id, symbol),
                FOREIGN KEY(daily_snapshot_id, symbol)
                    REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id, symbol)
            );
            CREATE INDEX IF NOT EXISTS idx_f10_outcome_day_status
                ON field10_daily_outcome(broker_day DESC, settlement_status, symbol);

            CREATE TABLE IF NOT EXISTS field10_next_day_candidate (
                candidate_id TEXT PRIMARY KEY,
                target_broker_day TEXT NOT NULL,
                source_broker_day TEXT NOT NULL,
                universe_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                parent_run_id TEXT,
                latest_completed_h1 TEXT,
                candidate_hash TEXT NOT NULL UNIQUE,
                candidate_json TEXT NOT NULL,
                prepared_at_broker_time TEXT NOT NULL,
                activated_snapshot_id TEXT,
                UNIQUE(target_broker_day, universe_hash, status)
            );
            CREATE INDEX IF NOT EXISTS idx_f10_candidate_target
                ON field10_next_day_candidate(target_broker_day DESC, status);

            CREATE TABLE IF NOT EXISTS field10_model_validation_registry (
                registry_id TEXT PRIMARY KEY,
                broker_day TEXT NOT NULL,
                symbol TEXT NOT NULL,
                method_name TEXT NOT NULL,
                model_version TEXT NOT NULL,
                formula_version TEXT NOT NULL,
                threshold_version TEXT NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                validation_status TEXT NOT NULL,
                promotion_status TEXT NOT NULL,
                p_value REAL,
                pbo_estimate REAL,
                result_hash TEXT NOT NULL,
                result_json TEXT NOT NULL,
                UNIQUE(broker_day, symbol, method_name, result_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_f10_validation_method
                ON field10_model_validation_registry(method_name, broker_day DESC, symbol);

            CREATE TABLE IF NOT EXISTS field10_daily_snapshot_audit (
                audit_id TEXT PRIMARY KEY,
                daily_snapshot_id TEXT,
                broker_day TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                observed_at_broker_time TEXT NOT NULL,
                details_json TEXT NOT NULL,
                audit_hash TEXT NOT NULL UNIQUE,
                FOREIGN KEY(daily_snapshot_id) REFERENCES field10_daily_snapshot(daily_snapshot_id)
            );
            CREATE INDEX IF NOT EXISTS idx_f10_audit_snapshot
                ON field10_daily_snapshot_audit(daily_snapshot_id, observed_at_broker_time DESC);
            """
        )
        existing = {
            str(row[1]) for row in conn.execute(
                "PRAGMA table_info(field10_daily_snapshot_symbol)"
            ).fetchall()
        }
        for column, sql_type in (
            ("transition_risk_24h", "REAL"),
            ("expected_return_12h", "REAL"),
            ("expected_return_24h", "REAL"),
            ("expected_return_36h", "REAL"),
        ):
            if column not in existing:
                conn.execute(
                    f"ALTER TABLE field10_daily_snapshot_symbol ADD COLUMN {column} {sql_type}"
                )

        # Backfill new physical columns from immutable row JSON when a newer
        # package already wrote them.  Older rows remain NULL instead of being
        # assigned fabricated zeroes; Lunch may add a transparent local-H1
        # display overlay without changing the locked publication checksum.
        rows = conn.execute(
            "SELECT daily_snapshot_id,symbol,row_json,transition_risk_24h,expected_return_12h,"
            "expected_return_24h,expected_return_36h FROM field10_daily_snapshot_symbol"
        ).fetchall()
        for snapshot_id, symbol, row_json, risk24, return12, return24, return36 in rows:
            if risk24 is not None and return12 is not None and return24 is not None and return36 is not None:
                continue
            try:
                payload = json.loads(str(row_json or "{}"))
            except Exception:
                payload = {}
            parsed_risk = _safe_float(payload.get("Transition Risk 24H"), percent=True)
            parsed_return12 = _safe_float(payload.get("Expected Return 12H (%)"))
            parsed_return24 = _safe_float(payload.get("Expected Return 24H (%)"))
            parsed_return36 = _safe_float(payload.get("Expected Return 36H (%)"))
            if any(value is not None for value in (parsed_risk, parsed_return12, parsed_return24, parsed_return36)):
                conn.execute(
                    "UPDATE field10_daily_snapshot_symbol "
                    "SET transition_risk_24h=COALESCE(transition_risk_24h,?), "
                    "expected_return_12h=COALESCE(expected_return_12h,?), "
                    "expected_return_24h=COALESCE(expected_return_24h,?), "
                    "expected_return_36h=COALESCE(expected_return_36h,?) "
                    "WHERE daily_snapshot_id=? AND symbol=?",
                    (parsed_risk, parsed_return12, parsed_return24, parsed_return36, snapshot_id, symbol),
                )
        conn.commit()
    return {
        "ok": True,
        "path": str(path),
        "contract_version": CONTRACT_VERSION,
        "tables": [
            "field10_daily_snapshot", "field10_daily_snapshot_symbol",
            "field10_daily_score_component", "field10_daily_safety_event",
            "field10_daily_outcome", "field10_next_day_candidate",
            "field10_model_validation_registry", "field10_daily_snapshot_audit",
        ],
    }


def canonical_symbol_universe(symbols: Sequence[Any], main_symbol: Any) -> list[str]:
    """Deterministic universe: main first, remaining symbols alphabetical."""
    main = normalize_symbol(main_symbol)
    normalized = {normalize_symbol(value) for value in symbols if str(value or "").strip()}
    normalized.add(main)
    return [main, *sorted(symbol for symbol in normalized if symbol != main)]


def symbol_universe_hash(symbols: Sequence[Any], main_symbol: Any, timeframe: Any = "H4") -> str:
    ordered = canonical_symbol_universe(symbols, main_symbol)
    aliases = {symbol: PROVIDER_ALIASES.get(symbol, {}) for symbol in ordered}
    return deterministic_hash({"timeframe": normalize_timeframe(timeframe), "main": ordered[0], "symbols": ordered, "aliases": aliases})


def _canonical_from_state(state: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        canonical = get_canonical(state)
        if isinstance(canonical, Mapping):
            return dict(canonical)
    except Exception:
        pass
    for key in (
        "canonical_decision_result_20260617", "canonical_decision_result",
        "last_valid_canonical_decision_result_20260617",
    ):
        value = state.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _frame_from_state(state: Mapping[str, Any]) -> pd.DataFrame:
    for key in (
        "canonical_completed_ohlc_df_20260617", "calculation_staging_ohlc_df_20260617",
        "last_df", "dv_pp_df",
    ):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy(deep=False)
    return pd.DataFrame()


def _column(frame: pd.DataFrame, *names: str) -> str | None:
    normalized = {str(c).strip().lower().replace("_", " "): str(c) for c in frame.columns}
    for name in names:
        found = normalized.get(name.lower().replace("_", " "))
        if found:
            return found
    return None


def _normalize_ohlc(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close"])
    time_col = _column(frame, "time", "datetime", "timestamp", "date", "event time utc", "event_time_utc")
    close_col = _column(frame, "close", "c")
    if time_col is None or close_col is None:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close"])
    result = pd.DataFrame({"time": pd.to_datetime(frame[time_col], errors="coerce", utc=True)})
    for target, alternatives in {
        "open": ("open", "o"), "high": ("high", "h"),
        "low": ("low", "l"), "close": ("close", "c"),
    }.items():
        source = _column(frame, *alternatives)
        result[target] = pd.to_numeric(frame[source], errors="coerce") if source else np.nan
    return result


def _is_crypto(symbol: str) -> bool:
    return normalize_symbol(symbol).startswith(("BTC", "ETH"))


def _expected_trading_candles(start: pd.Timestamp, end: pd.Timestamp, symbol: str, timeframe: Any) -> pd.DatetimeIndex:
    tf = normalize_timeframe(timeframe)
    expected = pd.date_range(start=start, end=end, freq=pd.Timedelta(seconds=TIMEFRAME_SECONDS[tf]), tz="UTC")
    if _is_crypto(symbol):
        return expected
    # Weekend closure is not treated as a missing market candle.
    return expected[expected.dayofweek < 5]


def _expected_trading_hours(start: pd.Timestamp, end: pd.Timestamp, symbol: str) -> pd.DatetimeIndex:
    """Legacy H1 compatibility alias used by the live safety veto."""
    return _expected_trading_candles(start, end, symbol, "H1")


def validate_completed_timeframe_frame(
    frame: pd.DataFrame,
    *,
    latest_completed_candle_utc: Any,
    symbol: str,
    timeframe: Any,
    required_candles_count: int | None = None,
) -> dict[str, Any]:
    """Validate the selected timeframe without altering any production formula."""
    tf = normalize_timeframe(timeframe)
    required_count = int(required_candles_count or required_candles(tf, "higher"))
    latest = pd.to_datetime(latest_completed_candle_utc, errors="coerce", utc=True)
    raw = _normalize_ohlc(frame)
    raw_count = int(len(raw))
    invalid_time_count = int(raw["time"].isna().sum()) if not raw.empty else 0
    raw = raw.dropna(subset=["time", "open", "high", "low", "close"])
    duplicate_count = int(raw.duplicated("time", keep=False).sum())
    raw = raw.drop_duplicates("time", keep=False)
    future_count = 0
    if pd.notna(latest):
        future_count = int(raw["time"].gt(latest).sum())
        raw = raw.loc[raw["time"].le(latest)]
    else:
        raw = raw.iloc[0:0]
    raw = raw.sort_values("time", kind="mergesort")
    valid_count = int(len(raw))
    window = raw.tail(required_count).copy()
    missing_candle_count = 0
    if len(window) >= 2:
        expected = _expected_trading_candles(pd.Timestamp(window["time"].iloc[0]), pd.Timestamp(window["time"].iloc[-1]), symbol, tf)
        missing_candle_count = int(len(expected.difference(pd.DatetimeIndex(window["time"]))))
    chronological = bool(window["time"].is_monotonic_increasing and window["time"].is_unique)
    exact_count = int(len(window)) == required_count
    latest_matches = bool(not window.empty and pd.notna(latest) and pd.Timestamp(window["time"].iloc[-1]) == pd.Timestamp(latest))
    spacing_seconds = TIMEFRAME_SECONDS[tf]
    diffs = window["time"].diff().dt.total_seconds().dropna() if not window.empty else pd.Series(dtype=float)
    bad_spacing = diffs[(diffs < spacing_seconds - 90) | ((diffs % spacing_seconds).abs() > 90)]
    complete = bool(
        exact_count and chronological and duplicate_count == 0 and future_count == 0
        and invalid_time_count == 0 and missing_candle_count == 0 and latest_matches and bad_spacing.empty
    )
    eligibility = calculation_eligibility(timeframe=tf, available=len(window), required=required_count)
    # Missing market candles reduce quality but do not erase an otherwise genuine
    # same-symbol series once the adaptive minimum is present. Duplicate, future,
    # malformed, sub-timeframe, or wrong-cutoff data still fail hard.
    adaptive_eligible = bool(
        eligibility.get("eligible") and chronological and duplicate_count == 0
        and future_count == 0 and invalid_time_count == 0 and latest_matches and bad_spacing.empty
    )
    reasons: list[str] = []
    if not exact_count:
        reasons.append(f"requires exactly {required_count} valid {tf} candles; found {len(window)}")
    if duplicate_count:
        reasons.append(f"duplicate timestamps={duplicate_count}")
    if future_count:
        reasons.append(f"future timestamps={future_count}")
    if invalid_time_count:
        reasons.append(f"invalid timestamps={invalid_time_count}")
    if missing_candle_count:
        reasons.append(f"missing active-market {tf} candles={missing_candle_count}")
    if not chronological:
        reasons.append(f"timestamps are not unique chronological {tf} identities")
    if not bad_spacing.empty:
        reasons.append(f"invalid {tf} spacing count={len(bad_spacing)}")
    if not latest_matches:
        reasons.append("window does not end at the required completed cutoff candle")
    window_hash = deterministic_hash({
        "symbol": normalize_symbol(symbol), "timeframe": tf,
        "latest": None if pd.isna(latest) else pd.Timestamp(latest).isoformat(),
        "rows": window[["time", "open", "high", "low", "close"]].to_dict("records"),
    }) if not window.empty else ""
    coverage = coverage_metadata(timeframe=tf, available=len(window), required=required_count)
    return {
        # Keep the legacy completion status for compatibility while exposing
        # adaptive publication eligibility separately.
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "eligible": adaptive_eligible,
        "full_history_complete": complete,
        "calculation_mode": "FULL_HISTORY" if complete else "ADAPTIVE_PARTIAL_HISTORY" if adaptive_eligible else "BELOW_MINIMUM_HISTORY",
        "minimum_calculation_candles": int(eligibility.get("minimum_calculation_candles") or minimum_calculation_candles(tf)),
        "timeframe": tf,
        "timeframe_seconds": spacing_seconds,
        "required_candles": required_count,
        "raw_count": raw_count,
        "valid_sample_count": valid_count,
        "sample_count": int(len(window)),
        "window_start": None if window.empty else pd.Timestamp(window["time"].iloc[0]).isoformat(),
        "window_end": None if window.empty else pd.Timestamp(window["time"].iloc[-1]).isoformat(),
        "missing_candle_count": missing_candle_count,
        "duplicate_count": duplicate_count,
        "future_timestamp_count": future_count,
        "invalid_timestamp_count": invalid_time_count,
        "bad_spacing_count": int(len(bad_spacing)),
        "chronological": chronological,
        "latest_matches_cutoff": latest_matches,
        "window_hash": window_hash,
        "coverage": coverage,
        "reasons": reasons,
        "frame": window.reset_index(drop=True),
    }


def validate_completed_h1_frame(
    frame: pd.DataFrame,
    *,
    latest_completed_h1_utc: Any,
    symbol: str,
    required_candles: int | None = None,
    timeframe: Any = "H1",
) -> dict[str, Any]:
    """Backward-compatible name; runtime behavior is selected-timeframe aware."""
    return validate_completed_timeframe_frame(
        frame,
        latest_completed_candle_utc=latest_completed_h1_utc,
        symbol=symbol,
        timeframe=timeframe,
        required_candles_count=required_candles,
    )


def _broker_identity(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    from core.shared_broker_time_20260622 import shared_broker_time_provider

    contract = dict(shared_broker_time_provider(state, canonical=dict(canonical)))
    broker_time = pd.to_datetime(contract.get("broker_time"), errors="coerce")
    runtime_tf = selected_timeframe(state, canonical) if (state.get("timeframe") or state.get("selected_timeframe") or canonical.get("timeframe")) else "H1"
    latest_value = (
        canonical.get("completed_broker_candle") or canonical.get("broker_candle_time")
        or canonical.get("latest_completed_candle_time") or contract.get("latest_broker_candle_utc")
        or contract.get("latest_completed_h1_utc")
    )
    latest_utc = pd.to_datetime(latest_value, errors="coerce", utc=True)
    if pd.isna(broker_time):
        broker_value = canonical.get("broker_candle_time") or canonical.get("completed_broker_candle")
        broker_time = pd.to_datetime(broker_value, errors="coerce")
    if pd.isna(broker_time):
        raise ValueError("Shared broker-time provider did not publish broker wall time")
    broker_time = pd.Timestamp(broker_time)
    # The provider normally returns a tz-aware broker timestamp. A fallback for
    # malformed clocks uses the resolved numeric offset without local-PC time.
    from datetime import timezone, timedelta
    if broker_time.tzinfo is None:
        offset_minutes = int(contract.get("broker_offset_minutes") or 0)
        broker_tz = timezone(timedelta(minutes=offset_minutes))
        broker_time = broker_time.tz_localize(broker_tz)
    else:
        offset_minutes = int(contract.get("broker_offset_minutes") or round((broker_time.utcoffset() or pd.Timedelta(0)).total_seconds() / 60))
        broker_tz = timezone(timedelta(minutes=offset_minutes))
    if broker_time.tzinfo is None:
        broker_time = broker_time.tz_localize(broker_tz)
    else:
        broker_time = broker_time.tz_convert(broker_tz)
    broker_day = broker_time.strftime("%Y-%m-%d")
    day_start = broker_time.normalize()
    cutoff = day_start + pd.Timedelta(hours=MORNING_LOCK_HOUR, minutes=MORNING_LOCK_MINUTE)
    last_usable_broker = cutoff - pd.Timedelta(seconds=TIMEFRAME_SECONDS[runtime_tf])
    last_usable_utc = last_usable_broker.tz_convert("UTC")
    if pd.notna(latest_utc) and pd.Timestamp(latest_utc) < last_usable_utc:
        effective_latest = pd.Timestamp(latest_utc)
    else:
        effective_latest = last_usable_utc
    locked_until = cutoff + pd.Timedelta(days=1)
    return {
        **contract,
        "broker_time": broker_time,
        "broker_day": broker_day,
        "cutoff_broker_time": cutoff,
        "timeframe": runtime_tf,
        "latest_completed_candle": effective_latest,
        "required_cutoff_completed_candle": last_usable_utc,
        "latest_completed_h1": effective_latest,  # legacy alias
        "required_cutoff_completed_h1": last_usable_utc,  # legacy alias
        "locked_until_broker_time": locked_until,
        "before_cutoff": broker_time < cutoff,
        "at_or_after_day_end": broker_time.hour >= DAY_END_REVIEW_HOUR,
        "broker_offset_minutes": offset_minutes,
    }


def _load_cached_states(symbols: Sequence[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        try:
            payload = _read_cache_payload(_cache_path(symbol))
            state = payload.get("state")
            if isinstance(state, Mapping):
                result[symbol] = dict(state)
        except Exception:
            continue
    return result


def _load_existing_evidence(
    parent_run_id: str, path: Path | str, timeframe: Any = "H4",
) -> tuple[
    dict[str, dict[str, Any]], dict[str, dict[str, Any]],
    dict[str, dict[str, Any]], dict[str, dict[str, Any]],
]:
    legacy: dict[str, dict[str, Any]] = {}
    integrated: dict[str, dict[str, Any]] = {}
    research: dict[str, dict[str, Any]] = {}
    generations: dict[str, dict[str, Any]] = {}
    with _connect(path) as conn:
        try:
            for row in conn.execute(
                "SELECT * FROM field10_daily_higher_lock WHERE parent_run_id=?", (str(parent_run_id),)
            ).fetchall():
                legacy[normalize_symbol(row["symbol"])] = dict(row)
        except sqlite3.Error:
            pass
        try:
            rows = conn.execute(
                """SELECT * FROM field10_integrated_evidence WHERE parent_run_id=?
                   ORDER BY broker_timestamp DESC, created_at DESC""", (str(parent_run_id),)
            ).fetchall()
            for row in rows:
                symbol = normalize_symbol(row["symbol"])
                integrated.setdefault(symbol, dict(row))
        except sqlite3.Error:
            pass
        try:
            rows = conn.execute(
                """SELECT * FROM field10_research_validation WHERE parent_run_id=?
                   ORDER BY broker_timestamp DESC, created_at DESC""", (str(parent_run_id),)
            ).fetchall()
            for row in rows:
                symbol = normalize_symbol(row["symbol"])
                if symbol not in research:
                    data = dict(row)
                    try:
                        data["result"] = json.loads(data.get("result_json") or "{}")
                    except Exception:
                        data["result"] = {}
                    research[symbol] = data
        except sqlite3.Error:
            pass
        try:
            rows = conn.execute(
                """SELECT parent_run_id,child_run_id,symbol,timeframe,canonical_run_id,source_id,
                          snapshot_hash,completed_broker_candle,publication_status,
                          runtime_snapshot_path,runtime_snapshot_sha256,updated_at
                   FROM child_generation_registry
                   WHERE parent_run_id=? AND UPPER(timeframe)=?
                   ORDER BY completed_broker_candle DESC,updated_at DESC""",
                (str(parent_run_id), normalize_timeframe(timeframe)),
            ).fetchall()
            for row in rows:
                symbol = normalize_symbol(row["symbol"])
                generations.setdefault(symbol, dict(row))
        except sqlite3.Error:
            pass
    return legacy, integrated, research, generations


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bias(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if "BUY" in text or text in {"BULL", "UP", "LONG"}:
        return "BUY"
    if "SELL" in text or text in {"BEAR", "DOWN", "SHORT"}:
        return "SELL"
    if text in {"WAIT", "HOLD", "NO TRADE", "BLOCKED", "NEUTRAL", "RANGE"}:
        return "WAIT"
    return None


def _find_higher_standard_bias(value: Any, depth: int = 0, seen: set[int] | None = None) -> str | None:
    """Read the exact Field 3 Higher Standard row from the saved child state."""
    del depth, seen
    from core.field3_bias_resolver_20260703 import resolve_higher_standard_bias
    return resolve_higher_standard_bias(value)

def _forecast_accuracy_from_db(symbol: str, path: Path | str) -> tuple[float | None, float | None, float | None, int]:
    with _connect(path) as conn:
        try:
            rows = conn.execute(
                """SELECT correct_1h,correct_3h,correct_6h FROM field10_daily_outcome
                   WHERE symbol=? AND settlement_status='CURRENT_DAY_SETTLED'
                   ORDER BY broker_day DESC LIMIT 60""", (normalize_symbol(symbol),)
            ).fetchall()
        except sqlite3.Error:
            rows = []
    if not rows:
        return None, None, None, 0
    values = [[row[key] for row in rows if row[key] is not None] for key in ("correct_1h", "correct_3h", "correct_6h")]
    accuracy = [None if not x else 100.0 * float(np.mean(x)) for x in values]
    return accuracy[0], accuracy[1], accuracy[2], len(rows)


def _calibrated_probability(research_result: Mapping[str, Any], integrated: Mapping[str, Any], legacy: Mapping[str, Any]) -> tuple[float | None, float | None, str, int]:
    scoring = _mapping(research_result.get("proper_scoring"))
    sample_count = int(scoring.get("sample_count") or 0)
    status = str(scoring.get("status") or "UNAVAILABLE").upper()
    raw = _clip100(
        integrated.get("calibrated_reliability")
        or _mapping(research_result.get("hamilton_regime")).get("current_regime_probability")
        or legacy.get("higher_reliability")
    )
    # Existing proper scoring validates probabilities but does not silently
    # invent a calibration transform. When settled validation exists, the
    # protected reliability/probability is accepted as calibrated evidence.
    calibrated = raw if status == "VALID" and sample_count >= DEFAULT_THRESHOLDS.minimum_calibration_samples else None
    return raw, calibrated, status, sample_count


def _component(value: Any, weight: float, *, critical: bool, status: str = "AVAILABLE", evidence: Any = None) -> dict[str, Any]:
    number = _clip100(value)
    available = number is not None and str(status).upper() not in {"UNAVAILABLE", "INSUFFICIENT_DATA", "INSUFFICIENT_SAMPLE", "DISABLED", "FAILED"}
    return {
        "value": number, "weight": float(weight), "critical": bool(critical),
        "available": bool(available), "status": str(status), "evidence": _json_safe(evidence or {}),
    }


def _tail_safety(cvar: float | None, returns: pd.Series) -> float | None:
    if cvar is None:
        return None
    scale = float(returns.std(ddof=1)) if len(returns) >= 20 and np.isfinite(returns.std(ddof=1)) else None
    if not scale or scale <= 0:
        return None
    ratio = abs(float(cvar)) / scale
    return float(np.clip(100.0 - 20.0 * ratio, 0.0, 100.0))


def _conformal_component(coverage: float | None, width: float | None, returns: pd.Series) -> float | None:
    coverage_pct = _clip100(coverage)
    if coverage_pct is None or width is None:
        return None
    target = 90.0
    coverage_score = max(0.0, 100.0 - 4.0 * abs(coverage_pct - target))
    scale = float(returns.std(ddof=1)) if len(returns) >= 20 else None
    if not scale or not math.isfinite(scale) or scale <= 0:
        sharpness = 50.0
    else:
        sharpness = float(np.clip(100.0 - 15.0 * abs(float(width)) / scale, 0.0, 100.0))
    return 0.65 * coverage_score + 0.35 * sharpness


def _research_layer_bundle(result: Mapping[str, Any], integrated: Mapping[str, Any], frame_validation: Mapping[str, Any], path: Path | str, symbol: str) -> dict[str, Any]:
    h = _mapping(result.get("hamilton_regime"))
    bp = _mapping(result.get("bai_perron_breaks"))
    scoring = _mapping(result.get("proper_scoring"))
    conformal = _mapping(result.get("conformal_prediction"))
    lw = _mapping(result.get("ledoit_wolf"))
    cvar = _mapping(result.get("cvar"))
    spa = _mapping(result.get("hansen_spa"))
    frame = frame_validation.get("frame")
    returns = pd.to_numeric(frame["close"], errors="coerce").pct_change().dropna() if isinstance(frame, pd.DataFrame) and not frame.empty else pd.Series(dtype=float)
    raw_prob, calibrated_prob, calibration_status, calibration_samples = _calibrated_probability(result, integrated, {})
    acc1, acc3, acc6, settled_count = _forecast_accuracy_from_db(symbol, path)
    selected_regime_probability = _clip100(h.get("current_regime_probability") or integrated.get("regime_probability"))
    self_transition = _clip100(h.get("self_transition_probability") or h.get("p_self"))
    persistence = None
    if selected_regime_probability is not None and self_transition is not None:
        entropy = _clip100(h.get("regime_entropy"))
        entropy_safety = 100.0 - (entropy if entropy is not None else 100.0)
        persistence = 0.45 * selected_regime_probability + 0.45 * self_transition + 0.10 * entropy_safety
    elif selected_regime_probability is not None:
        persistence = selected_regime_probability
    age = _safe_float(h.get("current_regime_age_hours") or h.get("current_run_length") or integrated.get("current_regime_run_length"))
    expected = _safe_float(h.get("expected_duration_hours") or integrated.get("expected_regime_duration"))
    remaining = _safe_float(h.get("estimated_remaining_hours"))
    transition_1h = _clip100(h.get("transition_risk_1h") or integrated.get("transition_risk_1h"))
    transition_3h = _clip100(h.get("transition_risk_3h") or integrated.get("transition_risk_3h"))
    transition_6h = _clip100(h.get("transition_risk_6h") or integrated.get("transition_risk_6h"))
    cp_probability = _clip100(integrated.get("change_probability"))
    structural_strength = _clip100(bp.get("break_strength"))
    post_break = None
    if bp.get("current_segment_start_index") is not None:
        post_break = max(0, int(frame_validation.get("sample_count") or 0) - int(bp.get("current_segment_start_index") or 0))
    conformal_coverage = _clip100(conformal.get("realized_coverage") or integrated.get("conformal_coverage"))
    interval_width = _safe_float(conformal.get("interval_width") or integrated.get("interval_width"))
    cvar_95 = _safe_float(cvar.get("cvar_95") or integrated.get("cvar_95"))
    unique_score = None
    duplicate_penalty = _clip100(lw.get("duplicate_exposure_penalty") or integrated.get("duplicate_exposure_penalty"))
    if duplicate_penalty is not None:
        unique_score = 100.0 - duplicate_penalty
    cluster = lw.get("correlation_cluster") or integrated.get("correlation_cluster")
    if isinstance(cluster, list):
        cluster = ", ".join(map(str, cluster))
    tail_score = _tail_safety(cvar_95, returns)
    conformal_score = _conformal_component(conformal_coverage, interval_width, returns)
    settled_accuracy = None
    available_acc = [x for x in (acc1, acc3, acc6) if x is not None]
    if available_acc and settled_count >= DEFAULT_THRESHOLDS.minimum_settled_accuracy_samples:
        settled_accuracy = float(np.mean(available_acc))
    spa_p = _safe_float(spa.get("spa_p_value"))
    return {
        "hamilton": {
            "status": h.get("status") or "UNAVAILABLE", "selected_regime_probability": selected_regime_probability,
            "self_transition_probability": self_transition, "posterior_margin": _clip100(h.get("posterior_margin") or integrated.get("regime_posterior_margin")),
            "normalized_entropy": _clip100(h.get("regime_entropy") or integrated.get("regime_entropy")),
            "persistence_score": _clip100(persistence),
        },
        "duration_transition": {
            "regime_age": age, "expected_total_duration": expected, "estimated_remaining_duration": remaining,
            "exhaustion_risk": None if expected is None or age is None or expected <= 0 else _clip100(100.0 * age / expected),
            "transition_probability_1h": transition_1h, "transition_probability_3h": transition_3h,
            "transition_probability_6h": transition_6h,
        },
        "bai_perron": {
            "status": bp.get("status") or "UNAVAILABLE", "break_count": bp.get("break_count"),
            "latest_break": bp.get("last_break_time"), "break_magnitude": structural_strength,
            "post_break_sample": post_break, "structural_break_detected": bool(bp.get("structural_break_detected")),
        },
        "bocpd": {
            "status": integrated.get("structural_break_status") or "UNAVAILABLE",
            "run_length_posterior": integrated.get("current_regime_run_length"),
            "modal_run_length": integrated.get("current_regime_run_length"),
            "changepoint_probability": cp_probability,
            "stability_status": "UNSTABLE" if cp_probability is not None and cp_probability >= 65 else ("STABLE" if cp_probability is not None else "UNAVAILABLE"),
        },
        "calibration": {
            "status": calibration_status, "raw_directional_probability": raw_prob,
            "calibrated_directional_probability": calibrated_prob, "brier_score": _safe_float(scoring.get("brier_score")),
            "log_loss": _safe_float(scoring.get("log_loss")), "expected_calibration_error": _clip100(scoring.get("calibration_error")),
            "settled_sample_count": calibration_samples,
        },
        "conformal": {
            "status": conformal.get("status") or integrated.get("conformal_coverage_status") or "UNAVAILABLE",
            "target_coverage": _clip100(conformal.get("target_coverage") or 0.90), "realized_rolling_coverage": conformal_coverage,
            "lower_prediction_bound": conformal.get("lower_bound"), "upper_prediction_bound": conformal.get("upper_bound"),
            "interval_width": interval_width, "coverage_error": None if conformal_coverage is None else abs(conformal_coverage - 90.0),
            "sharpness_score": conformal_score,
        },
        "ledoit_wolf": {
            "status": lw.get("status") or "UNAVAILABLE", "correlation_cluster": cluster,
            "common_factor_overlap": lw.get("common_factor_overlap"), "duplicate_exposure_penalty": duplicate_penalty,
            "unique_opportunity_score": unique_score,
        },
        "cvar": {
            "status": cvar.get("status") or "UNAVAILABLE", "var_95": _safe_float(cvar.get("var_95")),
            "cvar_95": cvar_95, "stress_cvar": _safe_float(cvar.get("stress_cvar")),
            "downside_volatility": _safe_float(cvar.get("downside_volatility")),
            "maximum_adverse_excursion": _safe_float(cvar.get("maximum_adverse_excursion")),
            "tail_risk_grade": cvar.get("tail_risk_grade") or "UNAVAILABLE", "tail_safety_score": tail_score,
        },
        "spa": {
            "status": spa.get("status") or "UNAVAILABLE", "benchmark_model": spa.get("benchmark_model"),
            "candidate_count": spa.get("candidate_count"), "test_statistic": spa.get("spa_statistic"),
            "p_value": spa_p, "promotion_status": "ELIGIBLE" if spa_p is not None and spa_p < 0.05 and bool(spa.get("superior_predictive_ability")) else "NOT_PROMOTED",
            "experiment_identity": deterministic_hash({"symbol": symbol, "method": "SPA", "result": spa}),
        },
        "pbo": _estimate_pbo(symbol, path),
        "forecast_accuracy": {"accuracy_1h": acc1, "accuracy_3h": acc3, "accuracy_6h": acc6, "settled_sample_count": settled_count, "component_score": settled_accuracy},
        "component_values": {
            "regime_persistence": _clip100(persistence), "calibrated_bias_probability": calibrated_prob,
            "settled_forecast_accuracy": settled_accuracy, "conformal_coverage_sharpness": conformal_score,
            "tail_risk_safety": tail_score, "unique_exposure_score": unique_score,
        },
    }


def _estimate_pbo(symbol: str, path: Path | str) -> dict[str, Any]:
    """Run genuine CSCV PBO only when a pre-registered candidate matrix exists.

    A single production score series is not a strategy-trial matrix and must not
    be transformed into a reassuring PBO estimate. Candidate matrices may be
    published by the existing experiment registries under an explicit matrix
    key; otherwise the result remains unavailable and promotion is blocked.
    """
    payloads: list[Mapping[str, Any]] = []
    with _connect(path) as conn:
        try:
            rows = conn.execute(
                """SELECT result_json FROM field10_model_validation_registry
                   WHERE symbol=? ORDER BY broker_day DESC LIMIT 100""",
                (normalize_symbol(symbol),),
            ).fetchall()
            for row in rows:
                try:
                    value = json.loads(row["result_json"] or "{}")
                    if isinstance(value, Mapping):
                        payloads.append(value)
                except Exception:
                    continue
        except sqlite3.Error:
            pass
        try:
            rows = conn.execute(
                """SELECT result_json FROM field10_research_experiments
                   WHERE symbol=? ORDER BY created_at DESC LIMIT 100""",
                (normalize_symbol(symbol),),
            ).fetchall()
            for row in rows:
                try:
                    value = json.loads(row["result_json"] or "{}")
                    if isinstance(value, Mapping):
                        payloads.append(value)
                except Exception:
                    continue
        except sqlite3.Error:
            pass

    matrix: pd.DataFrame | None = None
    source_identity: str | None = None
    for payload in payloads:
        candidate = (
            payload.get("candidate_performance_matrix")
            or payload.get("performance_matrix")
            or payload.get("cscv_candidate_matrix")
        )
        if candidate is None:
            continue
        try:
            frame = pd.DataFrame(candidate).apply(pd.to_numeric, errors="coerce").dropna()
        except Exception:
            frame = pd.DataFrame()
        if frame.shape[0] >= 40 and frame.shape[1] >= 2:
            matrix = frame
            source_identity = deterministic_hash(payload)
            break

    if matrix is None:
        return {
            "status": "INSUFFICIENT_TRIAL_MATRIX",
            "effective_trial_count": 0,
            "candidate_count": 0,
            "in_sample_rank": None,
            "out_of_sample_rank": None,
            "degradation": None,
            "pbo_estimate": None,
            "promotion_eligibility": "BLOCKED",
            "reason": "PBO requires at least two genuine pre-registered candidate columns and sufficient settled periods.",
            "method": "CSCV PBO; no proxy or neutral value used",
        }
    try:
        from research_quant.field10_shadow_methods_20260702 import probability_of_backtest_overfitting
        result = probability_of_backtest_overfitting(matrix, blocks=8, metric_higher_is_better=True)
    except Exception as exc:
        return {
            "status": "UNAVAILABLE", "effective_trial_count": int(matrix.shape[0]),
            "candidate_count": int(matrix.shape[1]), "pbo_estimate": None,
            "promotion_eligibility": "BLOCKED",
            "reason": f"{type(exc).__name__}: {exc}",
            "method": "CSCV PBO",
        }
    pbo = _safe_float(result.get("pbo"))
    degradation = _safe_float(result.get("mean_oos_degradation"))
    return {
        "status": str(result.get("status") or "UNAVAILABLE"),
        "effective_trial_count": int(result.get("fold_count") or 0),
        "candidate_count": int(result.get("candidate_count") or matrix.shape[1]),
        "in_sample_rank": 1,
        "out_of_sample_rank": None,
        "degradation": degradation,
        "pbo_estimate": pbo,
        "median_logit_rank": _safe_float(result.get("median_logit_rank")),
        "probability_of_loss": _safe_float(result.get("probability_of_loss")),
        "promotion_eligibility": "ELIGIBLE" if pbo is not None and pbo <= 0.25 else "BLOCKED",
        "experiment_registry_identity": source_identity,
        "method": "Combinatorially Symmetric Cross-Validation PBO",
    }

def _eligibility(candidate: Mapping[str, Any], thresholds: SnapshotThresholds) -> tuple[str, list[str]]:
    """Separate hard identity/data failures from ordinary trade caution.

    Earlier builds converted every missing optional research layer or protected
    WAIT permission into a fully BLOCKED row.  That hid useful per-symbol
    evidence and produced a table of identical WAIT values.  The publication is
    now eligible when its identity is trustworthy and the selected-timeframe
    adaptive minimum is available; incomplete full-window coverage remains visible as a
    quality warning instead of erasing all calculations.
    """
    reasons: list[str] = []
    frame = _mapping(candidate.get("frame_validation"))
    research = _mapping(candidate.get("research_layers"))
    identity = _mapping(candidate.get("identity"))
    adaptive = _mapping(research.get("adaptive_h1"))
    sample_count = int(frame.get("sample_count") or adaptive.get("sample_count") or 0)
    candidate_timeframe = str(frame.get("timeframe") or adaptive.get("timeframe") or "H1").upper()
    minimum_samples = minimum_calculation_candles(candidate_timeframe)
    if sample_count < minimum_samples:
        reasons.append(f"below minimum completed {candidate_timeframe} evidence ({sample_count}; minimum {minimum_samples})")
    if not all(identity.get(key) for key in ("canonical_run_id", "source_id", "snapshot_hash")):
        reasons.append("invalid canonical identity")
    checksum_status = str(_mapping(identity.get("snapshot_checksum_status")).get("status") or "").upper()
    if checksum_status in {"CHECKSUM_MISMATCH", "SNAPSHOT_READ_FAILED"}:
        reasons.append("failed snapshot checksum")
    cutoff_status = str(_mapping(identity.get("cutoff_generation_status")).get("status") or "").upper()
    if cutoff_status in {"AFTER_CUTOFF", "BEFORE_CUTOFF"}:
        reasons.append("child generation does not match the configured morning cutoff")
    stale = _safe_float(identity.get("stale_hours"))
    if stale is not None and stale > thresholds.maximum_stale_hours:
        reasons.append("stale market data")
    if not bool(identity.get("symbol_match", False)):
        reasons.append("unresolved symbol mismatch")
    bp = _mapping(research.get("bai_perron"))
    if bool(bp.get("structural_break_detected")) and (_clip100(bp.get("break_magnitude")) or 0.0) >= thresholds.severe_structural_break_strength * 100.0:
        if int(bp.get("post_break_sample") or 0) < thresholds.minimum_post_break_sample:
            reasons.append("severe structural break with insufficient post-break evidence")
    cp = _mapping(research.get("bocpd"))
    if (_clip100(cp.get("changepoint_probability")) or 0.0) >= thresholds.severe_changepoint_probability * 100.0:
        reasons.append("severe changepoint instability")
    spread_pct = _clip100(candidate.get("spread_percentile"))
    spread = _safe_float(candidate.get("average_spread"))
    if (spread_pct is not None and spread_pct > thresholds.maximum_spread_percentile) or (spread is not None and spread > thresholds.maximum_absolute_spread):
        reasons.append("unusable spread")
    if _bias(candidate.get("stable_daily_bias")) is None:
        reasons.append("missing directional bias")
    return ("ELIGIBLE" if not reasons else "BLOCKED", reasons)


def _score_candidate(candidate: MutableMapping[str, Any], thresholds: SnapshotThresholds, weights: ScoreWeights) -> dict[str, Any]:
    layers = _mapping(candidate.get("research_layers"))
    values = _mapping(layers.get("component_values"))
    integrated = _mapping(candidate.get("integrated"))
    components = {
        "regime_persistence": _component(values.get("regime_persistence"), weights.regime_persistence, critical=True, evidence=layers.get("hamilton")),
        "calibrated_bias_probability": _component(values.get("calibrated_bias_probability"), weights.calibrated_bias_probability, critical=True, status=_mapping(layers.get("calibration")).get("status") or "UNAVAILABLE", evidence=layers.get("calibration")),
        "settled_forecast_accuracy": _component(values.get("settled_forecast_accuracy"), weights.settled_forecast_accuracy, critical=False, evidence=layers.get("forecast_accuracy")),
        "evidence_agreement": _component(integrated.get("evidence_agreement"), weights.evidence_agreement, critical=False, evidence={"conflict_index": integrated.get("conflict_index")}),
        "data_quality": _component(candidate.get("data_quality_score"), weights.data_quality, critical=True, evidence={"grade": candidate.get("data_quality_grade")}),
        "spread_execution_quality": _component(candidate.get("spread_execution_score"), weights.spread_execution_quality, critical=False, evidence={"spread_percentile": candidate.get("spread_percentile"), "average_spread": candidate.get("average_spread")}),
        "transition_safety": _component(None if candidate.get("transition_risk_6h") is None else 100.0 - float(candidate.get("transition_risk_6h")), weights.transition_safety, critical=True, evidence=layers.get("duration_transition")),
        "conformal_coverage_sharpness": _component(values.get("conformal_coverage_sharpness"), weights.conformal_coverage_sharpness, critical=False, status=_mapping(layers.get("conformal")).get("status") or "UNAVAILABLE", evidence=layers.get("conformal")),
        "tail_risk_safety": _component(values.get("tail_risk_safety"), weights.tail_risk_safety, critical=False, status=_mapping(layers.get("cvar")).get("status") or "UNAVAILABLE", evidence=layers.get("cvar")),
        "unique_exposure_score": _component(values.get("unique_exposure_score"), weights.unique_exposure_score, critical=False, status=_mapping(layers.get("ledoit_wolf")).get("status") or "UNAVAILABLE", evidence=layers.get("ledoit_wolf")),
    }
    eligibility_status, eligibility_reasons = _eligibility(candidate, thresholds)
    critical_missing = [name for name, item in components.items() if item["critical"] and not item["available"]]
    if critical_missing:
        eligibility_reasons.extend(f"score evidence unavailable: {name}" for name in critical_missing)
        # Missing optional publishers lowers score confidence but does not erase
        # an otherwise valid OHLC-derived ranking. Identity/data checks remain
        # the hard eligibility authority.
    available_weight = sum(item["weight"] for item in components.values() if item["available"])
    missing_weight = 100.0 - available_weight
    weighted_sum = sum(float(item["value"]) * item["weight"] for item in components.values() if item["available"])
    score = None if eligibility_status != "ELIGIBLE" or available_weight <= 0 else float(np.clip(weighted_sum / available_weight, 0.0, 100.0))
    for item in components.values():
        item["contribution"] = None if not item["available"] or available_weight <= 0 else float(item["value"] * item["weight"] / available_weight)
    confidence = 0.0 if eligibility_status != "ELIGIBLE" else float(np.clip(available_weight, 0.0, 100.0))
    result = {
        "institutional_morning_score": score, "available_weight": available_weight,
        "missing_weight": missing_weight, "calculation_status": "BLOCKED" if eligibility_status != "ELIGIBLE" else ("COMPLETE" if missing_weight == 0 else "PARTIAL_RENORMALIZED"),
        "score_confidence": confidence, "eligibility_status": eligibility_status,
        "eligibility_reasons": list(dict.fromkeys(eligibility_reasons)), "critical_missing": critical_missing,
        "components": components, "weights": asdict(weights), "thresholds": asdict(thresholds),
    }
    return result


def _daily_grade(score: float | None, eligibility: str, candidate: Mapping[str, Any], thresholds: SnapshotThresholds) -> str:
    if eligibility != "ELIGIBLE" or score is None:
        return "BLOCKED"
    calibrated = _clip100(candidate.get("calibrated_bias_probability")) or 0.0
    persistence = _clip100(candidate.get("regime_persistence")) or 0.0
    warning = bool(candidate.get("major_safety_warning"))
    if score >= thresholds.grade_a_plus and calibrated >= thresholds.strong_calibrated_probability and persistence >= thresholds.strong_regime_persistence and not warning:
        return "A+"
    if score >= thresholds.grade_a:
        return "A"
    if score >= thresholds.grade_b:
        return "B"
    if score >= thresholds.grade_c:
        return "C"
    return "D"


def _generation_checksum_status(generation: Mapping[str, Any], symbol: str) -> dict[str, Any]:
    """Validate the frozen child runtime snapshot when a registry checksum exists."""
    expected = str(generation.get("runtime_snapshot_sha256") or "").strip().lower()
    configured_path = str(generation.get("runtime_snapshot_path") or "").strip()
    candidate_paths: list[Path] = []
    if configured_path:
        candidate_paths.append(Path(configured_path))
        candidate_paths.append(Path(configured_path).expanduser())
    candidate_paths.append(_cache_path(symbol))
    snapshot_path = next((path for path in candidate_paths if path.is_file()), None)
    if not expected:
        return {
            "valid": False, "status": "CHECKSUM_UNAVAILABLE",
            "path": str(snapshot_path or configured_path or ""), "expected": None, "actual": None,
        }
    if snapshot_path is None:
        return {
            "valid": False, "status": "SNAPSHOT_FILE_UNAVAILABLE",
            "path": configured_path, "expected": expected, "actual": None,
        }
    try:
        actual = sha256(snapshot_path.read_bytes()).hexdigest().lower()
    except OSError as exc:
        return {
            "valid": False, "status": "SNAPSHOT_READ_FAILED", "path": str(snapshot_path),
            "expected": expected, "actual": None, "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "valid": actual == expected,
        "status": "VALID" if actual == expected else "CHECKSUM_MISMATCH",
        "path": str(snapshot_path), "expected": expected, "actual": actual,
    }


def _generation_cutoff_status(generation: Mapping[str, Any], identity: Mapping[str, Any]) -> dict[str, Any]:
    completed = pd.to_datetime(generation.get("completed_broker_candle"), errors="coerce", utc=True)
    required = pd.to_datetime(identity.get("latest_completed_h1"), errors="coerce", utc=True)
    if pd.isna(completed) or pd.isna(required):
        return {"valid": False, "status": "CUTOFF_IDENTITY_UNAVAILABLE", "completed": None, "required": None}
    difference_hours = (pd.Timestamp(completed) - pd.Timestamp(required)).total_seconds() / 3600.0
    return {
        "valid": abs(difference_hours) < 1e-9,
        "status": "MATCHED" if abs(difference_hours) < 1e-9 else ("AFTER_CUTOFF" if difference_hours > 0 else "BEFORE_CUTOFF"),
        "completed": pd.Timestamp(completed).isoformat(), "required": pd.Timestamp(required).isoformat(),
        "difference_hours": difference_hours,
    }


def _build_candidate(
    *, symbol: str, role: str, cached_state: Mapping[str, Any] | None,
    legacy: Mapping[str, Any], integrated: Mapping[str, Any], research_row: Mapping[str, Any],
    generation: Mapping[str, Any], identity: Mapping[str, Any], parent_run_id: str, path: Path | str,
    timeframe: Any, thresholds: SnapshotThresholds, weights: ScoreWeights,
) -> dict[str, Any]:
    state = dict(cached_state or {})
    canonical = _canonical_from_state(state)
    expected_symbol = normalize_symbol(symbol)
    actual_symbol = normalize_symbol(canonical.get("symbol") or state.get("symbol") or expected_symbol)
    frame = _frame_from_state(state)
    runtime_tf = normalize_timeframe(timeframe)
    validation = validate_completed_timeframe_frame(
        frame, latest_completed_candle_utc=identity["latest_completed_candle"], symbol=expected_symbol,
        timeframe=runtime_tf,
    )
    result = _mapping(research_row.get("result"))
    layers = dict(_research_layer_bundle(result, integrated, validation, path, expected_symbol))
    validated_frame = validation.get("frame")
    adaptive = compute_adaptive_regime_metrics(
        validated_frame if isinstance(validated_frame, pd.DataFrame) and not validated_frame.empty else frame,
        timeframe=runtime_tf,
    )
    layers["adaptive_selected_timeframe"] = adaptive
    layers["adaptive_h1"] = adaptive  # legacy alias
    if adaptive.get("ok"):
        calibration_layer = dict(_mapping(layers.get("calibration")))
        if _safe_float(calibration_layer.get("calibrated_directional_probability")) is None:
            calibration_layer["calibrated_directional_probability"] = adaptive.get("calibrated_bias_probability")
            calibration_layer["raw_directional_probability"] = coalesce_metric(
                calibration_layer.get("raw_directional_probability"), adaptive.get("raw_bias_probability")
            )
            calibration_layer["brier_score"] = coalesce_metric(
                calibration_layer.get("brier_score"), adaptive.get("brier_score")
            )
            calibration_layer["settled_sample_count"] = max(
                int(calibration_layer.get("settled_sample_count") or 0),
                max(int(adaptive.get(f"validation_samples_{h}h") or 0) for h in (1, 3, 6)),
            )
            calibration_layer["status"] = "ADAPTIVE_H1_CAUSAL_CALIBRATION"
        layers["calibration"] = calibration_layer
        forecast_layer = dict(_mapping(layers.get("forecast_accuracy")))
        for horizon in (1, 3, 6):
            key = f"accuracy_{horizon}h"
            forecast_layer[key] = coalesce_metric(forecast_layer.get(key), adaptive.get(f"forecast_accuracy_{horizon}h"))
        forecast_layer["settled_sample_count"] = max(
            int(forecast_layer.get("settled_sample_count") or 0),
            max(int(adaptive.get(f"validation_samples_{h}h") or 0) for h in (1, 3, 6)),
        )
        forecast_layer["status"] = "ADAPTIVE_H1_WALK_FORWARD"
        layers["forecast_accuracy"] = forecast_layer
    component_values = dict(_mapping(layers.get("component_values")))
    component_values["regime_persistence"] = coalesce_metric(
        component_values.get("regime_persistence"), adaptive.get("regime_persistence")
    )
    component_values["calibrated_bias_probability"] = coalesce_metric(
        component_values.get("calibrated_bias_probability"), adaptive.get("calibrated_bias_probability")
    )
    adaptive_acc = [adaptive.get(key) for key in ("forecast_accuracy_1h", "forecast_accuracy_3h", "forecast_accuracy_6h") if _safe_float(adaptive.get(key)) is not None]
    component_values["settled_forecast_accuracy"] = coalesce_metric(
        component_values.get("settled_forecast_accuracy"), float(np.mean(adaptive_acc)) if adaptive_acc else None
    )
    layers["component_values"] = component_values
    h = _mapping(layers.get("hamilton")); duration = _mapping(layers.get("duration_transition"))
    calibration = _mapping(layers.get("calibration")); conformal = _mapping(layers.get("conformal"))
    bp = _mapping(layers.get("bai_perron")); bocpd = _mapping(layers.get("bocpd")); cvar = _mapping(layers.get("cvar")); lw = _mapping(layers.get("ledoit_wolf"))
    # Field 3 Higher Standard is the shared directional authority.  Field 10
    # uses the same bias before considering any lower-standard entry gate.
    stable_bias = _bias(
        _find_higher_standard_bias(state)
        or legacy.get("higher_standard_bias")
        or integrated.get("higher_standard_bias")
        or integrated.get("regime_bias")
        or legacy.get("final_action")
        or integrated.get("combined_evidence_bias")
        or adaptive.get("bias")
    )
    if stable_bias == "WAIT" and _bias(adaptive.get("bias")) in {"BUY", "SELL"}:
        stable_bias = _bias(adaptive.get("bias"))
    less_risky = stable_bias or _bias(adaptive.get("bias"))
    original_permission = str(integrated.get("trade_permission") or legacy.get("trade_permission") or "CHECK").upper()
    permission = "CAUTION" if original_permission in {"BLOCKED", "NO TRADE", "RESEARCH ONLY", "WAIT"} and adaptive.get("ok") else original_permission
    spread_quality = str(integrated.get("spread_quality") or legacy.get("spread_quality") or "UNAVAILABLE").upper()
    spread_score_map = {"LOW": 95.0, "GOOD": 90.0, "AVERAGE": 70.0, "MEDIUM": 60.0, "HIGH": 30.0, "VERY HIGH": 5.0}
    spread_score = spread_score_map.get(spread_quality)
    average_spread = _safe_float(legacy.get("average_spread"))
    spread_percentile = None
    if spread_score is not None:
        spread_percentile = 100.0 - spread_score
    canonical_run_id = str(generation.get("canonical_run_id") or canonical.get("run_id") or canonical.get("canonical_calculation_id") or integrated.get("canonical_run_id") or legacy.get("run_id") or "")
    source_id = str(generation.get("source_id") or canonical.get("source_id") or canonical.get("data_source_id") or integrated.get("source_id") or legacy.get("source_id") or "")
    snapshot_hash = str(generation.get("snapshot_hash") or canonical.get("snapshot_hash") or canonical.get("source_snapshot_hash") or integrated.get("snapshot_hash") or "")
    checksum = _generation_checksum_status(generation, expected_symbol)
    cutoff_generation = _generation_cutoff_status(generation, identity)
    required_latest = pd.Timestamp(identity["required_cutoff_completed_h1"])
    effective_latest = pd.Timestamp(identity["latest_completed_h1"])
    stale_hours = max(0.0, (required_latest - effective_latest).total_seconds() / 3600.0)
    publication_contract_status = "COMPLETED" if str(integrated.get("publication_status") or "").upper() in {"COMPLETED", "PUBLISHED", "DUPLICATE_REJECTED"} else ("VERIFIED" if adaptive.get("ok") else "FAILED")
    quality_score = _clip100(legacy.get("data_quality_score") or research_row.get("data_quality_score"))
    if quality_score is None:
        count_ratio = min(1.0, float(validation.get("sample_count") or 0) / max(1.0, float(validation.get("required_candles") or required_candles(runtime_tf, "higher"))))
        integrity_penalty = 4.0 * float(validation.get("missing_candle_count") or 0) + 2.0 * float(validation.get("duplicate_count") or 0)
        quality_score = float(np.clip(55.0 + 45.0 * count_ratio - integrity_penalty, 0.0, 100.0))
    quality_grade = integrated.get("data_quality_grade") or legacy.get("data_quality_grade")
    if not quality_grade or str(quality_grade).upper() == "UNAVAILABLE":
        quality_grade = "A" if quality_score >= 90 else ("B" if quality_score >= 75 else ("C" if quality_score >= 60 else "D"))
    candidate: dict[str, Any] = {
        "symbol": expected_symbol, "role": role, "parent_run_id": parent_run_id,
        "frame_validation": validation, "research_layers": layers, "integrated": dict(integrated),
        "legacy": dict(legacy), "identity": {
            "canonical_run_id": canonical_run_id, "source_id": source_id, "snapshot_hash": snapshot_hash,
            "child_run_id": str(generation.get("child_run_id") or ""),
            "snapshot_checksum_valid": bool(snapshot_hash) and bool(checksum.get("valid")),
            "snapshot_checksum_status": checksum,
            "cutoff_generation_valid": bool(cutoff_generation.get("valid")),
            "cutoff_generation_status": cutoff_generation,
            "generation_publication_status": str(generation.get("publication_status") or "UNAVAILABLE"),
            "symbol_match": actual_symbol == expected_symbol,
            "actual_symbol": actual_symbol, "stale_hours": stale_hours,
        },
        "existing_rank_score": _safe_float(legacy.get("rank_score")),
        "stable_daily_bias": stable_bias, "less_risky_bias": less_risky,
        "trade_permission": permission, "original_trade_permission": original_permission,
        "higher_standard_regime": integrated.get("higher_standard_regime") or legacy.get("higher_standard_regime") or adaptive.get("regime") or "UNAVAILABLE",
        "data_quality_grade": quality_grade,
        "data_quality_score": quality_score,
        "spread_quality": spread_quality, "spread_execution_score": spread_score,
        "spread_percentile": spread_percentile, "average_spread": average_spread,
        "publication_contract_status": publication_contract_status,
        "regime_probability": coalesce_metric(h.get("selected_regime_probability"), adaptive.get("regime_probability")),
        "regime_entropy": coalesce_metric(h.get("normalized_entropy"), adaptive.get("regime_entropy")),
        "posterior_margin": coalesce_metric(h.get("posterior_margin"), adaptive.get("posterior_margin")),
        "regime_persistence": coalesce_metric(h.get("persistence_score"), adaptive.get("regime_persistence")),
        "regime_age": coalesce_metric(duration.get("regime_age"), adaptive.get("regime_age")),
        "expected_regime_duration": coalesce_metric(duration.get("expected_total_duration"), adaptive.get("expected_regime_duration")),
        "estimated_remaining_duration": coalesce_metric(duration.get("estimated_remaining_duration"), adaptive.get("estimated_remaining_duration")),
        "transition_risk_1h": coalesce_metric(duration.get("transition_probability_1h"), adaptive.get("transition_risk_1h")),
        "transition_risk_3h": coalesce_metric(duration.get("transition_probability_3h"), adaptive.get("transition_risk_3h")),
        "transition_risk_6h": coalesce_metric(duration.get("transition_probability_6h"), adaptive.get("transition_risk_6h")),
        "transition_risk_24h": coalesce_metric(duration.get("transition_probability_24h"), adaptive.get("transition_risk_24h")),
        "expected_return_12h": coalesce_metric(
            result.get("expected_return_12h"), adaptive.get("expected_return_12h")
        ),
        "expected_return_24h": coalesce_metric(
            result.get("expected_return_24h"), adaptive.get("expected_return_24h")
        ),
        "expected_return_36h": coalesce_metric(
            result.get("expected_return_36h"), adaptive.get("expected_return_36h")
        ),
        "expected_value_6h": adaptive.get("expected_value_6h"),
        "risk_adjusted_expected_value_6h": adaptive.get("risk_adjusted_expected_value_6h"),
        "probability_profit_1h": adaptive.get("probability_profit_1h"),
        "probability_profit_6h": adaptive.get("probability_profit_6h"),
        "probability_profit_12h": adaptive.get("probability_profit_12h"),
        "probability_reach_ev_1h": adaptive.get("probability_reach_ev_1h"),
        "probability_reach_ev_6h": adaptive.get("probability_reach_ev_6h"),
        "probability_reach_ev_12h": adaptive.get("probability_reach_ev_12h"),
        "ev_target_1h": adaptive.get("ev_target_1h"), "ev_target_6h": adaptive.get("ev_target_6h"),
        "ev_target_12h": adaptive.get("ev_target_12h"), "tick_volume_12h": adaptive.get("tick_volume_12h"),
        "volume_12h_z": adaptive.get("volume_12h_z"), "volume_source": adaptive.get("volume_source"),
        "ev_model_version": adaptive.get("ev_model_version"),
        "probability_calibration_status": adaptive.get("probability_calibration_status"),
        "unexpected_situation_status": adaptive.get("unexpected_situation_status"),
        "unexpected_situation_severity": adaptive.get("unexpected_situation_severity"),
        "validation_permission": adaptive.get("validation_permission"),
        "evidence_sample_size": adaptive.get("evidence_sample_size"),
        "metric_provenance_json": adaptive.get("metric_provenance_json"),
        "calibrated_bias_probability": coalesce_metric(calibration.get("calibrated_directional_probability"), adaptive.get("calibrated_bias_probability")),
        "brier_score": coalesce_metric(calibration.get("brier_score"), adaptive.get("brier_score")),
        "forecast_accuracy_1h": coalesce_metric(_mapping(layers.get("forecast_accuracy")).get("accuracy_1h"), adaptive.get("forecast_accuracy_1h")),
        "forecast_accuracy_3h": coalesce_metric(_mapping(layers.get("forecast_accuracy")).get("accuracy_3h"), adaptive.get("forecast_accuracy_3h")),
        "forecast_accuracy_6h": coalesce_metric(_mapping(layers.get("forecast_accuracy")).get("accuracy_6h"), adaptive.get("forecast_accuracy_6h")),
        "technical_bias": integrated.get("technical_bias") or adaptive.get("bias"),
        "technical_reliability": coalesce_metric(_clip100(integrated.get("technical_reliability")), adaptive.get("calibrated_bias_probability")),
        "sentiment_bias": integrated.get("sentiment_bias"), "sentiment_reliability": _clip100(integrated.get("sentiment_reliability")),
        "session_bias": integrated.get("session_bias"), "session_reliability": _clip100(integrated.get("session_reliability")),
        "evidence_agreement": _clip100(integrated.get("evidence_agreement")), "conflict_index": _clip100(integrated.get("conflict_index")),
        "conformal_coverage": conformal.get("realized_rolling_coverage"), "conformal_interval_width": conformal.get("interval_width"),
        "structural_break_status": bp.get("status"), "changepoint_probability": bocpd.get("changepoint_probability"),
        "cvar_95": cvar.get("cvar_95"), "correlation_cluster": lw.get("correlation_cluster"),
        "duplicate_exposure_penalty": lw.get("duplicate_exposure_penalty"),
        "major_safety_warning": bool(
            (_clip100(bocpd.get("changepoint_probability")) or 0) >= thresholds.severe_changepoint_probability * 100
            or (bool(bp.get("structural_break_detected")) and int(bp.get("post_break_sample") or 0) < thresholds.minimum_post_break_sample)
        ),
    }
    score = _score_candidate(candidate, thresholds, weights)
    candidate["score"] = score
    candidate["institutional_morning_score"] = score["institutional_morning_score"]
    candidate["eligibility_status"] = score["eligibility_status"]
    candidate["daily_grade"] = _daily_grade(candidate["institutional_morning_score"], candidate["eligibility_status"], candidate, thresholds)
    return candidate


def _rank_candidates(candidates: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    work = [dict(item) for item in candidates]
    def key(item: Mapping[str, Any]) -> tuple[Any, ...]:
        eligible = item.get("eligibility_status") == "ELIGIBLE"
        score = _safe_float(item.get("institutional_morning_score"))
        calibrated = _clip100(item.get("calibrated_bias_probability"))
        persistence = _clip100(item.get("regime_persistence"))
        tr6 = _clip100(item.get("transition_risk_6h"))
        cvar = _safe_float(item.get("cvar_95"))
        quality = _clip100(item.get("data_quality_score"))
        spread = _safe_float(item.get("average_spread"))
        return (
            0 if eligible else 1,
            -(score if score is not None else -1e12),
            -(calibrated if calibrated is not None else -1e12),
            -(persistence if persistence is not None else -1e12),
            tr6 if tr6 is not None else 1e12,
            abs(cvar) if cvar is not None else 1e12,
            -(quality if quality is not None else -1e12),
            spread if spread is not None else 1e12,
            str(item.get("symbol") or ""),
        )
    work.sort(key=key)  # Python sort is stable and deterministic.
    rank = 0
    for item in work:
        if item.get("eligibility_status") == "ELIGIBLE":
            rank += 1
            item["daily_rank"] = rank
        else:
            item["daily_rank"] = None
    return work


def _row_for_publication(candidate: Mapping[str, Any], identity: Mapping[str, Any], universe_hash: str) -> dict[str, Any]:
    frame = _mapping(candidate.get("frame_validation")); score = _mapping(candidate.get("score")); ident = _mapping(candidate.get("identity"))
    explanation = {
        "eligibility_status": candidate.get("eligibility_status"),
        "eligibility_reasons": score.get("eligibility_reasons"),
        "available_weight": score.get("available_weight"), "missing_weight": score.get("missing_weight"),
        "calculation_status": score.get("calculation_status"), "score_confidence": score.get("score_confidence"),
        "sample_validation": {k: frame.get(k) for k in (
            "status", "required_candles", "sample_count", "window_start", "window_end",
            "missing_candle_count", "duplicate_count", "future_timestamp_count", "invalid_timestamp_count", "reasons",
        )},
        "research_layers": candidate.get("research_layers"),
        "score_components": score.get("components"),
        "metric_provenance_json": candidate.get("metric_provenance_json"),
    }
    hard_block_reasons = {
        "invalid canonical identity", "failed snapshot checksum",
        "unresolved symbol mismatch", "stale market data",
    }
    reasons = set(_mapping(candidate.get("score")).get("eligibility_reasons") or [])
    if candidate.get("eligibility_status") == "ELIGIBLE":
        entry_permission = "ALLOWED" if str(candidate.get("trade_permission")).upper() not in {"CAUTION", "CHECK"} else "CAUTION"
    else:
        entry_permission = "BLOCKED" if reasons.intersection(hard_block_reasons) else "CAUTION"
    return {
        "Daily Rank": candidate.get("daily_rank"), "Symbol": candidate.get("symbol"), "Role": candidate.get("role"),
        "Daily Grade": candidate.get("daily_grade"), "Institutional Morning Score": candidate.get("institutional_morning_score"),
        "Existing Rank Score": candidate.get("existing_rank_score"), "Stable Daily Bias": candidate.get("stable_daily_bias") or "UNAVAILABLE",
        "Less-Risky Bias": candidate.get("less_risky_bias") or "UNAVAILABLE", "Entry Permission": entry_permission,
        "Safety Veto": "CLEAR", "Higher Standard Regime": candidate.get("higher_standard_regime"),
        "Selected-Timeframe Completion": frame.get("status"),
        "Required Candle Count": frame.get("required_candles"),
        "Available Candle Count": frame.get("sample_count"),
        "Timeframe": frame.get("timeframe"),
        "Coverage Percent": _mapping(frame.get("coverage")).get("Coverage Percent"),
        "600-H1 Completion": frame.get("status") if frame.get("timeframe") == "H1" else "LEGACY_ALIAS_NOT_APPLICABLE",
        "Regime Probability": candidate.get("regime_probability"),
        "Regime Entropy": candidate.get("regime_entropy"), "Posterior Margin": candidate.get("posterior_margin"),
        "Regime Age": candidate.get("regime_age"), "Expected Regime Duration": candidate.get("expected_regime_duration"),
        "Estimated Remaining Duration": candidate.get("estimated_remaining_duration"),
        "Transition Risk 1H": candidate.get("transition_risk_1h"), "Transition Risk 3H": candidate.get("transition_risk_3h"),
        "Transition Risk 6H": candidate.get("transition_risk_6h"),
        "Transition Risk 24H": candidate.get("transition_risk_24h"),
        "Expected Return 12H (%)": candidate.get("expected_return_12h"),
        "Expected Return 24H (%)": candidate.get("expected_return_24h"),
        "Expected Return 36H (%)": candidate.get("expected_return_36h"),
        "Expected Value 6H (%)": candidate.get("expected_value_6h"),
        "Risk-Adjusted EV 6H (%)": candidate.get("risk_adjusted_expected_value_6h"),
        "Probability of Profit 1H (%)": candidate.get("probability_profit_1h"),
        "Probability of Profit 6H (%)": candidate.get("probability_profit_6h"),
        "Probability of Profit 12H (%)": candidate.get("probability_profit_12h"),
        "Probability Reach EV 1H (%)": candidate.get("probability_reach_ev_1h"),
        "Probability Reach EV 6H (%)": candidate.get("probability_reach_ev_6h"),
        "Probability Reach EV 12H (%)": candidate.get("probability_reach_ev_12h"),
        "EV Target 1H (%)": candidate.get("ev_target_1h"), "EV Target 6H (%)": candidate.get("ev_target_6h"),
        "EV Target 12H (%)": candidate.get("ev_target_12h"), "Observed Tick Volume 12H": candidate.get("tick_volume_12h"),
        "Volume 12H Z-Score": candidate.get("volume_12h_z"), "Volume Data Source": candidate.get("volume_source") or "UNAVAILABLE",
        "EV Model Version": candidate.get("ev_model_version") or "UNAVAILABLE",
        "Probability Calibration Status": candidate.get("probability_calibration_status") or "UNAVAILABLE",
        "Unexpected Situation Status": candidate.get("unexpected_situation_status") or "CAUTION",
        "Unexpected Situation Severity": candidate.get("unexpected_situation_severity"),
        "Validation Permission": candidate.get("validation_permission") or "VALIDATE",
        "Evidence Sample Size": candidate.get("evidence_sample_size"),
        "Calibrated Bias Probability": candidate.get("calibrated_bias_probability"),
        "Brier Score": candidate.get("brier_score"), "Forecast Accuracy 1H": candidate.get("forecast_accuracy_1h"),
        "Forecast Accuracy 3H": candidate.get("forecast_accuracy_3h"), "Forecast Accuracy 6H": candidate.get("forecast_accuracy_6h"),
        "Technical Bias": candidate.get("technical_bias") or "UNAVAILABLE", "Technical Reliability": candidate.get("technical_reliability"),
        "Sentiment Bias": candidate.get("sentiment_bias") or "UNAVAILABLE", "Sentiment Reliability": candidate.get("sentiment_reliability"),
        "Session Bias": candidate.get("session_bias") or "UNAVAILABLE", "Session Reliability": candidate.get("session_reliability"),
        "Evidence Agreement": candidate.get("evidence_agreement"), "Conflict Index": candidate.get("conflict_index"),
        "Conformal Coverage": candidate.get("conformal_coverage"), "Conformal Interval Width": candidate.get("conformal_interval_width"),
        "Structural Break Status": candidate.get("structural_break_status") or "UNAVAILABLE",
        "Changepoint Probability": candidate.get("changepoint_probability"), "Data Quality Grade": candidate.get("data_quality_grade"),
        "Spread Percentile": candidate.get("spread_percentile"), "CVaR 95%": candidate.get("cvar_95"),
        "Correlation Cluster": candidate.get("correlation_cluster") or "UNAVAILABLE",
        "Duplicate Exposure Penalty": candidate.get("duplicate_exposure_penalty"),
        "Lock Status": "PUBLISHED_LOCKED", "Locked At Broker Time": pd.Timestamp(identity["cutoff_broker_time"]).isoformat(),
        "Locked Until Broker Time": pd.Timestamp(identity["locked_until_broker_time"]).isoformat(),
        "Universe Hash": universe_hash, "Snapshot Hash": ident.get("snapshot_hash"),
        "Canonical Run ID": ident.get("canonical_run_id"), "Completed Broker Candle": pd.Timestamp(identity["latest_completed_h1"]).isoformat(),
        "Explanation": _canonical_json(explanation), "Publication Status": "PUBLISHED_LOCKED",
        "__source_id": ident.get("source_id"), "__score_explanation": explanation,
        "__sample_count": frame.get("sample_count"), "__content_hash": "",
    }


def _audit(conn: sqlite3.Connection, *, snapshot_id: str | None, broker_day: str, action: str, status: str, observed_at: str, details: Mapping[str, Any]) -> None:
    payload = {"snapshot_id": snapshot_id, "broker_day": broker_day, "action": action, "status": status, "observed_at": observed_at, "details": details}
    digest = deterministic_hash(payload)
    conn.execute(
        """INSERT OR IGNORE INTO field10_daily_snapshot_audit(
            audit_id,daily_snapshot_id,broker_day,action,status,observed_at_broker_time,details_json,audit_hash
        ) VALUES(?,?,?,?,?,?,?,?)""",
        (f"AUD-{digest[:24]}", snapshot_id, broker_day, action, status, observed_at, _canonical_json(details), digest),
    )


def _load_valid_existing(conn: sqlite3.Connection, broker_day: str) -> dict[str, Any] | None:
    meta = conn.execute("SELECT * FROM field10_daily_snapshot WHERE broker_day=?", (broker_day,)).fetchone()
    if meta is None:
        return None
    rows = conn.execute(
        "SELECT symbol,row_json,content_hash FROM field10_daily_snapshot_symbol WHERE daily_snapshot_id=? ORDER BY daily_rank IS NULL,daily_rank,symbol",
        (meta["daily_snapshot_id"],),
    ).fetchall()
    decoded = [json.loads(row["row_json"]) for row in rows]
    payload = {
        "identity": {key: meta[key] for key in (
            "broker_day", "cutoff_broker_time", "latest_completed_h1", "ordered_symbol_universe_json",
            "universe_hash", "main_symbol", "parent_run_id", "model_version", "formula_version", "threshold_version",
            "publication_status", "published_at_broker_time", "locked_until_broker_time",
        )},
        "rows": decoded,
    }
    valid = deterministic_hash(payload) == meta["content_hash"] and all(deterministic_hash({k: v for k, v in row.items() if k != "__content_hash"}) == stored["content_hash"] for row, stored in zip(decoded, rows))
    return {"valid": valid, "meta": dict(meta), "rows": decoded}


def repair_persisted_snapshot_integrity(*, broker_day: str | None = None, path: Path | str = DB_PATH) -> dict[str, Any]:
    """Repair hash-representation drift without changing any Field 10 values.

    The daily publication remains immutable: ranks, scores, decisions, symbols,
    identities and timestamps are never recalculated or edited.  This routine
    only reconciles a row hash stored in JSON versus the duplicate hash column,
    then refreshes the parent snapshot hash.  If neither stored row hash agrees
    with the row's actual canonical content, the repair fails closed.
    """
    _require_daily_snapshot_schema(path, initialize_for_writer=True)
    with _connect(path) as conn:
        if broker_day is None:
            day_row = conn.execute(
                "SELECT broker_day FROM field10_daily_snapshot ORDER BY broker_day DESC LIMIT 1"
            ).fetchone()
            broker_day = None if day_row is None else str(day_row["broker_day"])
        if not broker_day:
            return {"ok": False, "status": "NOT_FOUND"}
        meta = conn.execute(
            "SELECT * FROM field10_daily_snapshot WHERE broker_day=?", (broker_day,)
        ).fetchone()
        if meta is None:
            return {"ok": False, "status": "NOT_FOUND", "broker_day": broker_day}
        stored_rows = conn.execute(
            "SELECT symbol,row_json,content_hash FROM field10_daily_snapshot_symbol "
            "WHERE daily_snapshot_id=? ORDER BY daily_rank IS NULL,daily_rank,symbol",
            (meta["daily_snapshot_id"],),
        ).fetchall()
        normalized_rows: list[dict[str, Any]] = []
        row_updates: list[tuple[str, str, str]] = []
        unrecoverable: list[str] = []
        for stored in stored_rows:
            try:
                row = json.loads(stored["row_json"])
            except Exception:
                unrecoverable.append(f"{stored['symbol']}: invalid row_json")
                continue
            computed = deterministic_hash({key: value for key, value in row.items() if key != "__content_hash"})
            embedded = str(row.get("__content_hash") or "")
            column_hash = str(stored["content_hash"] or "")
            # At least one persisted representation must authenticate the row.
            # This prevents the repair path from blessing arbitrary content edits.
            if computed not in {embedded, column_hash}:
                unrecoverable.append(f"{stored['symbol']}: row content hash mismatch")
                continue
            row["__content_hash"] = computed
            normalized_rows.append(row)
            row_updates.append((_canonical_json(row), computed, str(stored["symbol"])))
        if unrecoverable or len(normalized_rows) != len(stored_rows):
            return {
                "ok": False, "status": "UNRECOVERABLE_CHECKSUM_MISMATCH",
                "broker_day": broker_day, "errors": unrecoverable,
            }
        payload = {
            "identity": {key: meta[key] for key in (
                "broker_day", "cutoff_broker_time", "latest_completed_h1", "ordered_symbol_universe_json",
                "universe_hash", "main_symbol", "parent_run_id", "model_version", "formula_version", "threshold_version",
                "publication_status", "published_at_broker_time", "locked_until_broker_time",
            )},
            "rows": normalized_rows,
        }
        repaired_hash = deterministic_hash(payload)
        observed_at = pd.Timestamp.now(tz="UTC").isoformat()
        try:
            for row_json, content_hash, symbol in row_updates:
                conn.execute(
                    "UPDATE field10_daily_snapshot_symbol SET row_json=?,content_hash=? "
                    "WHERE daily_snapshot_id=? AND symbol=?",
                    (row_json, content_hash, meta["daily_snapshot_id"], symbol),
                )
            conn.execute(
                "UPDATE field10_daily_snapshot SET content_hash=? WHERE daily_snapshot_id=?",
                (repaired_hash, meta["daily_snapshot_id"]),
            )
            _audit(
                conn, snapshot_id=str(meta["daily_snapshot_id"]), broker_day=str(broker_day),
                action="INTEGRITY_HASH_REPAIR", status="HASH_REPRESENTATION_REPAIRED",
                observed_at=observed_at,
                details={"values_modified": False, "row_count": len(normalized_rows), "content_hash": repaired_hash},
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        verified = _load_valid_existing(conn, str(broker_day))
    return {
        "ok": bool(verified and verified.get("valid")),
        "status": "REPAIRED_VALID" if verified and verified.get("valid") else "REPAIR_FAILED",
        "broker_day": broker_day, "daily_snapshot_id": str(meta["daily_snapshot_id"]),
        "content_hash": repaired_hash, "values_modified": False,
    }


def publish_daily_snapshot_from_records(
    *,
    broker_identity: Mapping[str, Any],
    ordered_symbols: Sequence[str],
    main_symbol: str,
    parent_run_id: str,
    candidates: Sequence[dict[str, Any]],
    path: Path | str = DB_PATH,
    thresholds: SnapshotThresholds = DEFAULT_THRESHOLDS,
    weights: ScoreWeights = DEFAULT_WEIGHTS,
) -> dict[str, Any]:
    """Deterministically rank and append one immutable broker-day publication."""
    _require_daily_snapshot_schema(path, initialize_for_writer=True)
    broker_day = str(broker_identity["broker_day"])
    observed_at = pd.Timestamp(broker_identity["broker_time"]).isoformat()
    with _connect(path) as conn:
        existing = _load_valid_existing(conn, broker_day)
        if existing:
            if not existing["valid"]:
                repair = repair_persisted_snapshot_integrity(broker_day=broker_day, path=path)
                if repair.get("ok"):
                    with _connect(path) as repaired_conn:
                        existing = _load_valid_existing(repaired_conn, broker_day)
                    return {"ok": True, "status": "ALREADY_EXISTS_REPAIRED", "daily_snapshot_id": existing["meta"]["daily_snapshot_id"], "rows": existing["rows"], "content_hash": existing["meta"]["content_hash"], "integrity_repair": repair}
                return {"ok": False, "status": "CHECKSUM_FAILED", "daily_snapshot_id": existing["meta"]["daily_snapshot_id"], "rows": existing["rows"], "content_hash": existing["meta"]["content_hash"], "integrity_repair": repair}
            status = "ALREADY_EXISTS_VALID"
            _audit(conn, snapshot_id=existing["meta"]["daily_snapshot_id"], broker_day=broker_day, action="PUBLISH_ATTEMPT", status=status, observed_at=observed_at, details={"parent_run_id": parent_run_id})
            conn.commit()
            return {"ok": True, "status": status, "daily_snapshot_id": existing["meta"]["daily_snapshot_id"], "rows": existing["rows"], "content_hash": existing["meta"]["content_hash"]}
        if bool(broker_identity.get("before_cutoff")):
            return {"ok": False, "status": "BEFORE_MORNING_CUTOFF", "broker_day": broker_day, "cutoff_broker_time": pd.Timestamp(broker_identity["cutoff_broker_time"]).isoformat()}

        universe = canonical_symbol_universe(ordered_symbols, main_symbol)
        universe_hash = symbol_universe_hash(universe, main_symbol, broker_identity.get("timeframe") or "H4")
        ranked = _rank_candidates(candidates)
        rows = [_row_for_publication(item, broker_identity, universe_hash) for item in ranked]
        for row in rows:
            content = {k: v for k, v in row.items() if k != "__content_hash"}
            row["__content_hash"] = deterministic_hash(content)
        snapshot_payload = {
            "identity": {
                "broker_day": broker_day,
                "cutoff_broker_time": pd.Timestamp(broker_identity["cutoff_broker_time"]).isoformat(),
                "latest_completed_h1": pd.Timestamp(broker_identity["latest_completed_h1"]).isoformat(),
                "ordered_symbol_universe_json": _canonical_json(universe), "universe_hash": universe_hash,
                "main_symbol": normalize_symbol(main_symbol), "parent_run_id": str(parent_run_id),
                "model_version": MODEL_VERSION, "formula_version": FORMULA_VERSION,
                "threshold_version": THRESHOLD_VERSION, "publication_status": "PUBLISHED_LOCKED",
                "published_at_broker_time": pd.Timestamp(broker_identity["cutoff_broker_time"]).isoformat(),
                "locked_until_broker_time": pd.Timestamp(broker_identity["locked_until_broker_time"]).isoformat(),
            },
            "rows": rows,
        }
        content_hash = deterministic_hash(snapshot_payload)
        snapshot_id = f"F10-{broker_day.replace('-', '')}-{universe_hash[:10]}-{content_hash[:12]}"
        child_ids = {str(item.get("symbol")): str(_mapping(item.get("identity")).get("child_run_id") or "") for item in ranked}
        canonical_ids = {str(item.get("symbol")): _mapping(item.get("identity")).get("canonical_run_id") for item in ranked}
        source_ids = {str(item.get("symbol")): _mapping(item.get("identity")).get("source_id") for item in ranked}
        hashes = {str(item.get("symbol")): _mapping(item.get("identity")).get("snapshot_hash") for item in ranked}
        aliases = {symbol: PROVIDER_ALIASES.get(symbol, {}) for symbol in universe}
        metadata = {
            "contract_version": CONTRACT_VERSION, "thresholds": asdict(thresholds), "weights": asdict(weights),
            "higher_standard_required_candles": required_candles(broker_identity.get("timeframe") or "H4", "higher"),
            "timeframe": broker_identity.get("timeframe") or "H4",
            "day_end_review_hour": DAY_END_REVIEW_HOUR,
        }
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """INSERT INTO field10_daily_snapshot(
                    daily_snapshot_id,broker_day,cutoff_broker_time,latest_completed_h1,
                    ordered_symbol_universe_json,universe_hash,main_symbol,secondary_symbols_json,
                    provider_aliases_json,symbol_count,parent_run_id,child_run_ids_json,
                    canonical_run_ids_json,source_ids_json,snapshot_hashes_json,model_version,
                    formula_version,threshold_version,content_hash,publication_status,
                    published_at_broker_time,locked_until_broker_time,metadata_json,created_at_broker_time
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id, broker_day, pd.Timestamp(broker_identity["cutoff_broker_time"]).isoformat(),
                    pd.Timestamp(broker_identity["latest_completed_h1"]).isoformat(), _canonical_json(universe),
                    universe_hash, normalize_symbol(main_symbol), _canonical_json(universe[1:]), _canonical_json(aliases),
                    len(universe), str(parent_run_id), _canonical_json(child_ids), _canonical_json(canonical_ids),
                    _canonical_json(source_ids), _canonical_json(hashes), MODEL_VERSION, FORMULA_VERSION,
                    THRESHOLD_VERSION, content_hash, "PUBLISHED_LOCKED",
                    pd.Timestamp(broker_identity["cutoff_broker_time"]).isoformat(),
                    pd.Timestamp(broker_identity["locked_until_broker_time"]).isoformat(),
                    _canonical_json(metadata), observed_at,
                ),
            )
            for candidate, row in zip(ranked, rows):
                score = _mapping(candidate.get("score"))
                conn.execute(
                    """INSERT INTO field10_daily_snapshot_symbol(
                        daily_snapshot_id,broker_day,symbol,role,daily_rank,daily_grade,
                        institutional_score,existing_rank_score,eligibility_status,trade_permission,
                        stable_daily_bias,less_risky_bias,higher_standard_regime,sample_count,
                        sample_complete_status,completed_candle,canonical_run_id,source_id,snapshot_hash,
                        correlation_cluster,transition_risk_24h,expected_return_12h,
                        expected_return_24h,expected_return_36h,content_hash,row_json,score_explanation_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        snapshot_id, broker_day, row["Symbol"], row["Role"], row["Daily Rank"], row["Daily Grade"],
                        row["Institutional Morning Score"], row["Existing Rank Score"], candidate.get("eligibility_status"),
                        row["Entry Permission"], row["Stable Daily Bias"], row["Less-Risky Bias"], row["Higher Standard Regime"],
                        int(row.get("__sample_count") or 0), row["Selected-Timeframe Completion"], row["Completed Broker Candle"],
                        row["Canonical Run ID"], row.get("__source_id"), row["Snapshot Hash"], row["Correlation Cluster"],
                        _safe_float(row.get("Transition Risk 24H"), percent=True),
                        _safe_float(row.get("Expected Return 12H (%)")),
                        _safe_float(row.get("Expected Return 24H (%)")),
                        _safe_float(row.get("Expected Return 36H (%)")),
                        row["__content_hash"], _canonical_json(row), _canonical_json(row["__score_explanation"]),
                    ),
                )
                for name, component in _mapping(score.get("components")).items():
                    conn.execute(
                        """INSERT INTO field10_daily_score_component(
                            daily_snapshot_id,symbol,component_name,component_value,configured_weight,
                            available,critical,contribution,status,evidence_json
                        ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (snapshot_id, row["Symbol"], name, component.get("value"), component.get("weight"),
                         int(bool(component.get("available"))), int(bool(component.get("critical"))),
                         component.get("contribution"), component.get("status"), _canonical_json(component.get("evidence") or {})),
                    )
                for method_name in ("spa", "pbo"):
                    method = _mapping(_mapping(candidate.get("research_layers")).get(method_name))
                    result_hash = deterministic_hash({"snapshot_id": snapshot_id, "symbol": row["Symbol"], "method": method_name, "result": method})
                    conn.execute(
                        """INSERT OR IGNORE INTO field10_model_validation_registry(
                            registry_id,broker_day,symbol,method_name,model_version,formula_version,
                            threshold_version,sample_count,validation_status,promotion_status,p_value,
                            pbo_estimate,result_hash,result_json
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (f"VAL-{result_hash[:24]}", broker_day, row["Symbol"], method_name.upper(), MODEL_VERSION,
                         FORMULA_VERSION, THRESHOLD_VERSION, int(method.get("effective_trial_count") or method.get("candidate_count") or 0),
                         str(method.get("status") or "UNAVAILABLE"), str(method.get("promotion_eligibility") or method.get("promotion_status") or "NOT_PROMOTED"),
                         _safe_float(method.get("p_value")), _safe_float(method.get("pbo_estimate")), result_hash, _canonical_json(method)),
                    )
            _audit(conn, snapshot_id=snapshot_id, broker_day=broker_day, action="PUBLISH", status="PUBLISHED_LOCKED", observed_at=observed_at, details={"content_hash": content_hash, "universe_hash": universe_hash, "rows": len(rows)})
            # Candidate activation is status-only and never mutates publication rows.
            conn.execute(
                """UPDATE field10_next_day_candidate SET status='NEXT_DAY_ACTIVATED',activated_snapshot_id=?
                   WHERE target_broker_day=? AND universe_hash=?
                     AND status='NEXT_DAY_CANDIDATE_READY'""",
                (snapshot_id, broker_day, universe_hash),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"ok": True, "status": "PUBLISHED_LOCKED", "daily_snapshot_id": snapshot_id, "broker_day": broker_day, "content_hash": content_hash, "universe_hash": universe_hash, "rows": rows}


def publish_daily_snapshot(
    state: MutableMapping[str, Any],
    *,
    parent_run_id: str,
    selected_symbols: Sequence[str],
    main_symbol: str,
    path: Path | str = DB_PATH,
    thresholds: SnapshotThresholds = DEFAULT_THRESHOLDS,
    weights: ScoreWeights = DEFAULT_WEIGHTS,
) -> dict[str, Any]:
    """Build and publish the authoritative morning snapshot from frozen caches."""
    _require_daily_snapshot_schema(path)
    universe = canonical_symbol_universe(selected_symbols, main_symbol)
    # Resolve the broker day from the in-memory main generation first. Do not read
    # secondary caches until after the immutable current-day existence check.
    main_state = dict(state)
    if normalize_symbol(_canonical_from_state(main_state).get("symbol") or state.get("symbol") or main_symbol) != normalize_symbol(main_symbol):
        main_state = _load_cached_states([normalize_symbol(main_symbol)]).get(normalize_symbol(main_symbol), main_state)
    main_canonical = _canonical_from_state(main_state)
    identity = _broker_identity(main_state, main_canonical)
    # First check persisted current day. This guarantees symbol selection changes
    # cannot trigger reranking or force secondary cache/API access after publication.
    with _connect(path) as conn:
        existing = _load_valid_existing(conn, identity["broker_day"])
        if existing:
            if existing["valid"]:
                return {"ok": True, "status": "ALREADY_EXISTS_VALID", "daily_snapshot_id": existing["meta"]["daily_snapshot_id"], "rows": existing["rows"], "content_hash": existing["meta"]["content_hash"]}
    if existing and not existing["valid"]:
        repair = repair_persisted_snapshot_integrity(broker_day=identity["broker_day"], path=path)
        if repair.get("ok"):
            with _connect(path) as conn:
                repaired = _load_valid_existing(conn, identity["broker_day"])
            return {"ok": True, "status": "ALREADY_EXISTS_REPAIRED", "daily_snapshot_id": repaired["meta"]["daily_snapshot_id"], "rows": repaired["rows"], "content_hash": repaired["meta"]["content_hash"], "integrity_repair": repair}
        return {"ok": False, "status": "CHECKSUM_FAILED", "daily_snapshot_id": existing["meta"]["daily_snapshot_id"], "rows": existing["rows"], "content_hash": existing["meta"]["content_hash"], "integrity_repair": repair}
    cached = _load_cached_states(universe)
    cached.setdefault(normalize_symbol(main_symbol), main_state)
    runtime_tf = selected_timeframe(state, main_canonical)
    legacy, integrated, research, generations = _load_existing_evidence(parent_run_id, path, runtime_tf)
    candidates: list[dict[str, Any]] = []
    for symbol in universe:
        role = "MAIN" if symbol == normalize_symbol(main_symbol) else "SECONDARY"
        candidate = _build_candidate(
            symbol=symbol, role=role, cached_state=cached.get(symbol), legacy=legacy.get(symbol, {}),
            integrated=integrated.get(symbol, {}), research_row=research.get(symbol, {}),
            generation=generations.get(symbol, {}), identity=identity,
            parent_run_id=parent_run_id, path=path, timeframe=runtime_tf, thresholds=thresholds, weights=weights,
        )
        candidates.append(candidate)
    report = publish_daily_snapshot_from_records(
        broker_identity=identity, ordered_symbols=universe, main_symbol=main_symbol,
        parent_run_id=parent_run_id, candidates=candidates, path=path,
        thresholds=thresholds, weights=weights,
    )
    state["field10_daily_snapshot_contract_20260702"] = {
        key: value for key, value in report.items() if key != "rows"
    }
    return report


def validate_persisted_snapshot(*, broker_day: str | None = None, path: Path | str = DB_PATH) -> dict[str, Any]:
    _require_daily_snapshot_schema(path)
    with _connect_readonly(path) as conn:
        if broker_day is None:
            row = conn.execute("SELECT broker_day FROM field10_daily_snapshot ORDER BY broker_day DESC LIMIT 1").fetchone()
            broker_day = None if row is None else str(row["broker_day"])
        if not broker_day:
            return {"ok": False, "status": "NOT_FOUND"}
        existing = _load_valid_existing(conn, broker_day)
    if not existing:
        return {"ok": False, "status": "NOT_FOUND", "broker_day": broker_day}
    return {"ok": bool(existing["valid"]), "status": "VALID" if existing["valid"] else "CHECKSUM_FAILED", "broker_day": broker_day, "daily_snapshot_id": existing["meta"]["daily_snapshot_id"], "content_hash": existing["meta"]["content_hash"], "row_count": len(existing["rows"])}


def _latest_safety(conn: sqlite3.Connection, broker_day: str) -> dict[str, str]:
    rows = conn.execute(
        """SELECT e.symbol,e.safety_veto FROM field10_daily_safety_event e
           JOIN (SELECT symbol,MAX(observed_at_broker_time) AS latest FROM field10_daily_safety_event
                 WHERE broker_day=? GROUP BY symbol) x
             ON x.symbol=e.symbol AND x.latest=e.observed_at_broker_time
           WHERE e.broker_day=?""", (broker_day, broker_day),
    ).fetchall()
    return {str(row["symbol"]): str(row["safety_veto"]) for row in rows}


def load_current_daily_snapshot(*, broker_day: str | None = None, path: Path | str = DB_PATH) -> dict[str, Any]:
    """Read-only loader used by Field 10 UI. No market/API calculation occurs."""
    _require_daily_snapshot_schema(path)
    with _connect_readonly(path) as conn:
        if broker_day is None:
            day_row = conn.execute("SELECT broker_day FROM field10_daily_snapshot ORDER BY broker_day DESC LIMIT 1").fetchone()
            broker_day = None if day_row is None else str(day_row["broker_day"])
        if not broker_day:
            return {"metadata": {}, "current": pd.DataFrame(columns=CURRENT_COLUMNS), "components": pd.DataFrame()}
        meta_row = conn.execute("SELECT * FROM field10_daily_snapshot WHERE broker_day=?", (broker_day,)).fetchone()
        if meta_row is None:
            return {"metadata": {}, "current": pd.DataFrame(columns=CURRENT_COLUMNS), "components": pd.DataFrame()}
        symbol_rows = conn.execute(
            "SELECT row_json,transition_risk_24h,expected_return_12h,expected_return_24h,expected_return_36h "
            "FROM field10_daily_snapshot_symbol WHERE daily_snapshot_id=? "
            "ORDER BY daily_rank IS NULL,daily_rank,symbol",
            (meta_row["daily_snapshot_id"],),
        ).fetchall()
        safety = _latest_safety(conn, broker_day)
        decoded = []
        for stored in symbol_rows:
            row = json.loads(stored["row_json"])
            if _safe_float(row.get("Transition Risk 24H"), percent=True) is None:
                row["Transition Risk 24H"] = stored["transition_risk_24h"]
            if _safe_float(row.get("Expected Return 12H (%)")) is None:
                row["Expected Return 12H (%)"] = stored["expected_return_12h"]
            if _safe_float(row.get("Expected Return 24H (%)")) is None:
                row["Expected Return 24H (%)"] = stored["expected_return_24h"]
            if _safe_float(row.get("Expected Return 36H (%)")) is None:
                row["Expected Return 36H (%)"] = stored["expected_return_36h"]
            row["Safety Veto"] = safety.get(str(row.get("Symbol")), row.get("Safety Veto") or "CLEAR")
            decoded.append(row)
        current = pd.DataFrame([{column: row.get(column) for column in CURRENT_COLUMNS} for row in decoded], columns=CURRENT_COLUMNS)
        components = pd.read_sql_query(
            """SELECT symbol AS Symbol,component_name AS Component,component_value AS Value,
                      configured_weight AS Weight,available AS Available,critical AS Critical,
                      contribution AS Contribution,status AS Status,evidence_json AS Evidence
               FROM field10_daily_score_component WHERE daily_snapshot_id=? ORDER BY symbol,component_name""",
            conn, params=(meta_row["daily_snapshot_id"],),
        )
        metadata = dict(meta_row)
        for key in ("ordered_symbol_universe_json", "secondary_symbols_json", "provider_aliases_json", "child_run_ids_json", "canonical_run_ids_json", "source_ids_json", "snapshot_hashes_json", "metadata_json"):
            try:
                metadata[key.removesuffix("_json")] = json.loads(metadata.get(key) or "{}")
            except Exception:
                metadata[key.removesuffix("_json")] = {}
    return {"metadata": metadata, "current": current, "components": components}


def load_daily_history(*, days: int = 25, symbols: Sequence[str] | None = None, limit: int = 1000, offset: int = 0, path: Path | str = DB_PATH) -> pd.DataFrame:
    """Read persisted original ranks and settled outcomes; never rerank history."""
    _require_daily_snapshot_schema(path)
    clauses: list[str] = []
    params: list[Any] = []
    if symbols:
        cleaned = [normalize_symbol(s) for s in symbols]
        clauses.append("s.symbol IN (%s)" % ",".join("?" for _ in cleaned))
        params.extend(cleaned)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    query = f"""
        SELECT s.broker_day,s.symbol,s.daily_rank,s.institutional_score,s.stable_daily_bias,
               s.less_risky_bias,s.daily_grade,o.settlement_status,o.actual_1h_direction,
               o.actual_3h_direction,o.actual_6h_direction,o.day_close_direction,o.correct_1h,
               o.correct_3h,o.correct_6h,o.mfe,o.mae,o.spread_adjusted_outcome,
               o.calibration_error,d.model_version,d.formula_version,d.universe_hash,s.snapshot_hash
        FROM field10_daily_snapshot_symbol s
        JOIN field10_daily_snapshot d USING(daily_snapshot_id)
        LEFT JOIN field10_daily_outcome o USING(daily_snapshot_id,symbol)
        {where}
        ORDER BY s.broker_day DESC,s.daily_rank IS NULL,s.daily_rank,s.symbol
        LIMIT ? OFFSET ?
    """
    params.extend([max(1, min(int(limit), 10000)), max(0, int(offset))])
    with _connect_readonly(path) as conn:
        frame = pd.read_sql_query(query, conn, params=params)
    if frame.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    # Latest N distinct broker days.
    keep_days = list(dict.fromkeys(frame["broker_day"].astype(str)))[: max(1, int(days))]
    frame = frame.loc[frame["broker_day"].astype(str).isin(keep_days)].copy()
    frame["rank_stability"] = np.nan
    frame["previous_day_rank_change"] = np.nan
    for symbol, indexes in frame.groupby("symbol", sort=False).groups.items():
        ordered = frame.loc[indexes].sort_values("broker_day")
        previous = pd.to_numeric(ordered["daily_rank"], errors="coerce").shift(1)
        change = pd.to_numeric(ordered["daily_rank"], errors="coerce") - previous
        frame.loc[ordered.index, "previous_day_rank_change"] = change
        frame.loc[ordered.index, "rank_stability"] = (100.0 - 20.0 * change.abs()).clip(0.0, 100.0)
    rename = {
        "broker_day": "Broker Day", "symbol": "Symbol", "daily_rank": "Original Morning Rank",
        "institutional_score": "Original Morning Score", "stable_daily_bias": "Original Bias",
        "less_risky_bias": "Original Less-Risky Bias", "settlement_status": "Outcome Settled Status",
        "actual_1h_direction": "Actual 1H Direction", "actual_3h_direction": "Actual 3H Direction",
        "actual_6h_direction": "Actual 6H Direction", "day_close_direction": "Day-Close Direction",
        "correct_1h": "Correct 1H", "correct_3h": "Correct 3H", "correct_6h": "Correct 6H",
        "mfe": "MFE", "mae": "MAE", "spread_adjusted_outcome": "Spread-Adjusted Outcome",
        "calibration_error": "Calibration Error", "rank_stability": "Rank Stability",
        "previous_day_rank_change": "Previous-Day Rank Change", "daily_grade": "Daily Grade",
        "model_version": "Model Version", "formula_version": "Formula Version",
        "universe_hash": "Universe Hash", "snapshot_hash": "Snapshot Hash",
    }
    frame = frame.rename(columns=rename)
    return frame[[column for column in HISTORY_COLUMNS if column in frame.columns]].reset_index(drop=True)


def current_table_data_dictionary() -> pd.DataFrame:
    definitions = {
        "Daily Rank": "Immutable eligibility-first rank; NULL for blocked/incomplete symbols.",
        "Institutional Morning Score": "0-100 normalized weighted score over genuinely available components.",
        "Existing Rank Score": "Preserved legacy Field 10 weighted rank score.",
        "Selected-Timeframe Completion": "COMPLETE only when the selected timeframe has its required 25-day window ending at the completed cutoff candle.",
        "600-H1 Completion": "Legacy compatibility alias; applicable only to H1 publications.",
        "Safety Veto": "Live CLEAR/CAUTION/BLOCK_NEW_ENTRIES overlay; never changes locked direction or rank.",
        "Transition Risk 24H": "Causal probability of leaving the current higher-standard regime within the next real 24-hour duration.",
        "Expected Return 12H (%)": "Signed, same-symbol historical-analogue expected return over the real 12-hour horizon; descriptive, not guaranteed.",
        "Expected Return 24H (%)": "Signed, same-symbol historical-analogue expected return over the real 24-hour horizon; descriptive, not guaranteed.",
        "Expected Return 36H (%)": "Signed, same-symbol historical-analogue expected return over the real 36-hour horizon; descriptive, not guaranteed.",
        "Explanation": "Deterministic JSON with gates, missing evidence, score weights, and research diagnostics.",
        "Publication Status": "PUBLISHED_LOCKED authoritative append-only publication state.",
    }
    return pd.DataFrame([{"Column": column, "Definition": definitions.get(column, "Persisted morning-cutoff evidence; see implementation report."), "Mutable Intraday": "YES (safety only)" if column == "Safety Veto" else "NO"} for column in CURRENT_COLUMNS])


__all__ = [
    "MORNING_LOCK_HOUR", "MORNING_LOCK_MINUTE", "DAY_END_REVIEW_HOUR", "TIMEFRAME",
    "HIGHER_STANDARD_REQUIRED_CANDLES", "MODEL_VERSION", "FORMULA_VERSION",
    "THRESHOLD_VERSION", "CONTRACT_VERSION", "SnapshotThresholds", "ScoreWeights",
    "DEFAULT_THRESHOLDS", "DEFAULT_WEIGHTS", "CURRENT_COLUMNS", "HISTORY_COLUMNS",
    "deterministic_hash", "canonical_symbol_universe", "symbol_universe_hash",
    "migrate_daily_snapshot_database", "validate_completed_timeframe_frame", "validate_completed_h1_frame",
    "publish_daily_snapshot", "publish_daily_snapshot_from_records",
    "repair_persisted_snapshot_integrity", "validate_persisted_snapshot", "load_current_daily_snapshot", "load_daily_history",
    "current_table_data_dictionary",
]
