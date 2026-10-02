"""Field 1 Table 4/5 publication bridge and Field 10 integrated evidence store.

This module is additive and read-only with respect to protected production logic.
It normalizes already-published Field 1 and Field 3/10 evidence, persists one
identity-verified row per completed symbol generation, and exposes display-only
validation/heatmap frames.  It never replaces the protected Combined Evidence
Bias or Master Action.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import math
import sqlite3

import numpy as np
import pandas as pd

from core.sqlite_readonly_20260704 import connect_readonly

from core.multi_symbol_field10_20260701 import DB_PATH, main_symbol, normalize_symbol

VERSION = "field10-integrated-evidence-20260702-v1"
CALCULATION_VERSION = "field10-integrated-shadow-validation-20260702-v1"
TABLE_NAME = "field10_integrated_evidence_history"
STATE_TABLE4_STATUS = "field10_table4_publication_status_20260702"
STATE_CURRENT = "field10_integrated_current_20260702"
STATE_HISTORY = "field10_integrated_history_20260702"

_BIAS_COMPONENTS = (
    "Technical Bias",
    "Sentiment Bias",
    "Session Bias",
    "Regime Bias",
    "Data-Mining Bias",
)
_BASE_WEIGHTS = {
    "Technical Bias": 1.30,
    "Sentiment Bias": 0.80,
    "Session Bias": 0.90,
    "Regime Bias": 1.10,
    "Data-Mining Bias": 1.20,
}

_TABLE5_COLUMNS = (
    "Symbol", "Technical Bias", "Sentiment Bias", "Session Bias", "Regime Bias",
    "Data-Mining Bias", "Existing Combined Evidence Bias", "Master Action",
    "News", "Evidence Available Count", "Evidence Agreement Percentage", "Weighted Conflict Index",
    "Higher Standard Regime", "Regime Probability", "Regime Entropy", "Regime Posterior Margin",
    "Transition Risk 1H", "Transition Risk 3H", "Transition Risk 6H", "Change Probability Now",
    "Current Regime Run Length", "Drift Status", "Adaptive Window Size", "Calibrated Reliability",
    "Conformal Coverage Status", "Prediction Interval Width", "Data Quality Grade", "Outcome Settled",
    "Actual Next-H1 Direction", "Master Action Correct", "Brier Score", "Conditional Accuracy",
    "Validation Permission", "Canonical Run ID", "Child Run ID", "Parent Multi-Symbol Run ID",
    "Source ID", "Snapshot Hash", "Calculation Version",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _col(frame: pd.DataFrame, *aliases: str) -> str | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    exact = {_norm(c): str(c) for c in frame.columns}
    for alias in aliases:
        key = _norm(alias)
        if key in exact:
            return exact[key]
    for alias in aliases:
        key = _norm(alias)
        if not key:
            continue
        for normalized, original in exact.items():
            if key in normalized:
                return original
    return None


def _first(row: Mapping[str, Any] | pd.Series, *aliases: str) -> Any:
    if isinstance(row, pd.Series):
        lookup = {_norm(c): c for c in row.index}
        for alias in aliases:
            key = _norm(alias)
            if key in lookup:
                value = row.get(lookup[key])
                if not _missing(value):
                    return value
        return None
    lookup = {_norm(k): k for k in row.keys()}
    for alias in aliases:
        key = _norm(alias)
        if key in lookup:
            value = row.get(lookup[key])
            if not _missing(value):
                return value
    return None


def _first_present(*values: Any) -> Any:
    """Return the first non-missing value while preserving valid numeric zeroes."""
    for value in values:
        if not _missing(value):
            return value
    return None


def _missing(value: Any) -> bool:
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    if isinstance(value, str):
        return value.strip().upper() in {"", "NAN", "NONE", "N/A", "NA", "NULL", "MISSING", "UNAVAILABLE"}
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _number(value: Any, *, percent: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if percent and abs(number) > 1.0:
        number /= 100.0
    return float(number)


def _bias(value: Any) -> str | None:
    if _missing(value):
        return None
    text = str(value).strip().upper()
    if any(token in text for token in ("BUY", "BULL", "LONG", "UP", "POSITIVE")):
        return "BUY"
    if any(token in text for token in ("SELL", "BEAR", "SHORT", "DOWN", "NEGATIVE")):
        return "SELL"
    if any(token in text for token in ("WAIT", "HOLD", "FLAT", "NEUTRAL", "NO TRADE")):
        return "WAIT"
    return None


def _encoded_bias(value: Any) -> float | None:
    normalized = _bias(value)
    return {"BUY": 1.0, "SELL": -1.0, "WAIT": 0.0}.get(normalized) if normalized else None


def _timestamp(value: Any, *, utc: bool = True) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce", utc=utc)
    if pd.isna(parsed):
        return pd.NaT
    return pd.Timestamp(parsed).floor("h")


def _broker_value(canonical: Mapping[str, Any]) -> Any:
    return (
        canonical.get("completed_broker_candle")
        or canonical.get("broker_candle_time")
        or canonical.get("latest_completed_candle_time")
        or canonical.get("completed_candle")
    )


def _canonical(state: Mapping[str, Any]) -> Mapping[str, Any]:
    with suppress(Exception):
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        if isinstance(value, Mapping):
            return value
    for key in (
        "canonical_decision_result_20260617", "canonical_result_20260617",
        "last_valid_canonical_decision_result_20260617",
    ):
        value = state.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _created_at() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def migrate_integrated_evidence_database(path: Path | str = DB_PATH) -> dict[str, Any]:
    """Create the migration-safe integrated evidence/history tables and indexes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=8000")
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                parent_run_id TEXT NOT NULL,
                child_run_id TEXT NOT NULL,
                canonical_run_id TEXT,
                symbol TEXT NOT NULL,
                role TEXT,
                timeframe TEXT NOT NULL,
                broker_timestamp TEXT NOT NULL,
                broker_date TEXT,
                broker_hour INTEGER,
                rank INTEGER,
                current_session TEXT,
                technical_bias TEXT,
                technical_source TEXT,
                technical_reliability REAL,
                sentiment_bias TEXT,
                sentiment_source TEXT,
                sentiment_reliability REAL,
                sentiment_headline TEXT,
                sentiment_publication_time TEXT,
                sentiment_entity_match TEXT,
                session_bias TEXT,
                session_source TEXT,
                session_reliability REAL,
                regime_bias TEXT,
                regime_source TEXT,
                higher_standard_regime TEXT,
                regime_probability REAL,
                regime_entropy REAL,
                regime_posterior_margin REAL,
                expected_regime_duration REAL,
                data_mining_bias TEXT,
                data_mining_source TEXT,
                combined_evidence_bias TEXT,
                shadow_fusion_score REAL,
                evidence_available_count INTEGER,
                evidence_agreement REAL,
                conflict_index REAL,
                transition_risk_1h REAL,
                transition_risk_3h REAL,
                transition_risk_6h REAL,
                transition_risk_24h REAL,
                expected_return_12h REAL,
                expected_return_24h REAL,
                expected_return_36h REAL,
                change_probability REAL,
                current_regime_run_length REAL,
                expected_stable_duration REAL,
                structural_break_status TEXT,
                drift_status TEXT,
                adaptive_window_size INTEGER,
                conformal_target_coverage REAL,
                conformal_coverage REAL,
                conformal_coverage_status TEXT,
                interval_width REAL,
                calibrated_reliability REAL,
                data_quality_grade TEXT,
                spread_quality TEXT,
                correlation_cluster TEXT,
                duplicate_exposure_penalty REAL,
                cvar_95 REAL,
                marginal_tail_risk REAL,
                suggested_risk_weight REAL,
                trade_permission TEXT,
                validation_permission TEXT,
                protected_final_action TEXT,
                outcome_settled INTEGER,
                actual_next_h1_direction TEXT,
                master_action_correct INTEGER,
                brier_score REAL,
                conditional_accuracy REAL,
                explanation TEXT,
                source_id TEXT,
                snapshot_hash TEXT NOT NULL,
                calculation_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (
                    parent_run_id, symbol, timeframe, broker_timestamp, child_run_id, snapshot_hash
                )
            );
            CREATE INDEX IF NOT EXISTS idx_field10_integrated_symbol_time
                ON {TABLE_NAME}(symbol, broker_timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_field10_integrated_parent_rank
                ON {TABLE_NAME}(parent_run_id, rank ASC);
            CREATE INDEX IF NOT EXISTS idx_field10_integrated_broker_date
                ON {TABLE_NAME}(broker_date DESC);
            CREATE INDEX IF NOT EXISTS idx_field10_integrated_action
                ON {TABLE_NAME}(protected_final_action);
            CREATE INDEX IF NOT EXISTS idx_field10_integrated_regime
                ON {TABLE_NAME}(higher_standard_regime, regime_bias);
            CREATE INDEX IF NOT EXISTS idx_field10_integrated_session
                ON {TABLE_NAME}(current_session);
            CREATE INDEX IF NOT EXISTS idx_field10_integrated_quality
                ON {TABLE_NAME}(data_quality_grade);
            CREATE TABLE IF NOT EXISTS field10_shadow_incremental_state (
                symbol TEXT NOT NULL,
                state_name TEXT NOT NULL,
                last_broker_timestamp TEXT,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(symbol, state_name)
            );
            CREATE TABLE IF NOT EXISTS field10_conformal_state (
                symbol TEXT NOT NULL,
                horizon INTEGER NOT NULL,
                session TEXT NOT NULL,
                target_coverage REAL,
                realized_coverage REAL,
                coverage_status TEXT,
                interval_width REAL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                last_broker_timestamp TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(symbol, horizon, session)
            );
            """
        )
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE_NAME})")}
        additive_columns = {
            "publication_status": "TEXT",
            "transition_risk_24h": "REAL",
            "expected_return_12h": "REAL",
            "expected_return_24h": "REAL",
            "expected_return_36h": "REAL",
        }
        for column, sql_type in additive_columns.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {column} {sql_type}")
        conn.commit()
    return {"ok": True, "path": str(path), "table": TABLE_NAME, "version": VERSION}


def _load_incremental_state(symbol: str, state_name: str, path: Path | str) -> dict[str, Any]:
    migrate_integrated_evidence_database(path)
    with sqlite3.connect(str(path), timeout=30) as conn:
        row = conn.execute(
            "SELECT state_json,last_broker_timestamp FROM field10_shadow_incremental_state WHERE symbol=? AND state_name=?",
            (symbol, state_name),
        ).fetchone()
    if not row:
        return {}
    try:
        payload = json.loads(str(row[0]))
        if isinstance(payload, dict):
            payload["last_broker_timestamp"] = row[1]
            return payload
    except Exception:
        pass
    return {}


def _save_incremental_state(symbol: str, state_name: str, broker_timestamp: str, payload: Mapping[str, Any], path: Path | str) -> None:
    safe = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    with sqlite3.connect(str(path), timeout=30) as conn:
        conn.execute(
            """INSERT INTO field10_shadow_incremental_state(symbol,state_name,last_broker_timestamp,state_json,updated_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(symbol,state_name) DO UPDATE SET
                 last_broker_timestamp=excluded.last_broker_timestamp,
                 state_json=excluded.state_json,
                 updated_at=excluded.updated_at""",
            (symbol, state_name, broker_timestamp, safe, _created_at()),
        )
        conn.commit()


def _source_frame(state: Mapping[str, Any]) -> pd.DataFrame:
    for key in (
        "canonical_completed_ohlc_df_20260617", "calculation_staging_ohlc_df_20260617",
        "last_df", "dv_pp_df",
    ):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy(deep=False)
    return pd.DataFrame()


def _return_series(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> pd.Series:
    frame = _source_frame(state)
    if frame.empty:
        return pd.Series(dtype=float)
    tc = _col(frame, "time", "datetime", "timestamp", "broker candle time")
    cc = _col(frame, "close")
    if not tc or not cc:
        return pd.Series(dtype=float)
    times = pd.to_datetime(frame[tc], errors="coerce", utc=True)
    close = pd.to_numeric(frame[cc], errors="coerce")
    work = pd.DataFrame({"time": times, "close": close}).dropna().sort_values("time").drop_duplicates("time", keep="last")
    cutoff = _timestamp(_broker_value(canonical))
    if pd.notna(cutoff):
        work = work.loc[work["time"] <= cutoff]
    returns = work.set_index("time")["close"].pct_change().dropna()
    return returns.tail(1500)


def _incremental_changepoint(state: Mapping[str, Any], canonical: Mapping[str, Any], path: Path | str) -> dict[str, Any]:
    symbol = normalize_symbol(canonical.get("symbol") or state.get("symbol") or "EURUSD")
    returns = _return_series(state, canonical)
    if returns.empty:
        return {"status": "INSUFFICIENT", "changepoint_probability": None, "modal_run_length": None}
    prior = _load_incremental_state(symbol, "BOCPD_RETURNS", path)
    prior_values = list(prior.get("recent_returns") or [])
    last_stamp = _timestamp(prior.get("last_broker_timestamp"))
    unseen = returns.loc[returns.index > last_stamp] if pd.notna(last_stamp) else returns
    values = [float(v) for v in prior_values if _number(v) is not None]
    values.extend(float(v) for v in unseen.to_numpy(dtype=float) if math.isfinite(float(v)))
    values = values[-128:]
    try:
        from core.research_grade_system_v17_20260624 import bayesian_online_changepoint
        result = dict(bayesian_online_changepoint(values, hazard=1 / 72, max_run=128))
    except Exception as exc:
        result = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}
    broker = _timestamp(_broker_value(canonical))
    payload = {"recent_returns": values, "result": result}
    if pd.notna(broker):
        _save_incremental_state(symbol, "BOCPD_RETURNS", broker.isoformat(), payload, path)
    return result


def _adwin_bundle(state: Mapping[str, Any], table4: pd.DataFrame) -> dict[str, Any]:
    """Run bounded, shadow-only ADWIN diagnostics on available published series."""
    try:
        from research_quant.ten_paper_validation_20260701 import adwin_drift
    except Exception:
        return {"status": "UNAVAILABLE", "drift_status": "UNAVAILABLE", "effective_window": None, "details": {}}

    candidates: dict[str, Sequence[float]] = {}
    returns = _return_series(state, _canonical(state))
    if not returns.empty:
        candidates["volatility"] = np.abs(returns.to_numpy(dtype=float))

    bt = state.get("dv_pp_bt_hist")
    if isinstance(bt, pd.DataFrame) and not bt.empty:
        c = _col(bt, "absolute error", "abs error", "error", "close error")
        if c:
            candidates["forecast_error"] = pd.to_numeric(bt[c], errors="coerce").dropna().to_numpy(dtype=float)

    table5 = state.get("field1_table5_integrated_decision_collection_20260627")
    if isinstance(table5, pd.DataFrame) and not table5.empty:
        c = _col(table5, "decision correct", "master action correct")
        if c:
            series = table5[c].astype(str).str.upper().map({"TRUE": 1.0, "FALSE": 0.0, "1": 1.0, "0": 0.0}).dropna()
            if not series.empty:
                candidates["table5_correctness"] = series.to_numpy(dtype=float)

    for label, aliases in {
        "technical_reliability": ("technical reliability",),
        "sentiment_reliability": ("sentiment reliability",),
        "regime_reliability": ("regime reliability", "higher reliability"),
        "spread": ("spread", "average spread"),
    }.items():
        c = _col(table4, *aliases)
        if c:
            values = pd.to_numeric(table4[c], errors="coerce").dropna().to_numpy(dtype=float)
            if len(values):
                candidates[label] = values

    details: dict[str, Any] = {}
    severities = {"DRIFT": 3, "WARNING": 2, "STABLE": 1, "INSUFFICIENT_DATA": 0, "DISABLED": 0}
    worst = "INSUFFICIENT_DATA"
    windows: list[int] = []
    for name, values in candidates.items():
        try:
            result = dict(adwin_drift(np.asarray(values, dtype=float)))
        except Exception as exc:
            result = {"status": "UNAVAILABLE", "drift_status": "UNAVAILABLE", "error": str(exc)}
        details[name] = result
        status = str(result.get("drift_status") or result.get("status") or "INSUFFICIENT_DATA").upper()
        if severities.get(status, 0) > severities.get(worst, 0):
            worst = status
        window = _number(result.get("adaptive_window_size"))
        if window is not None:
            windows.append(int(window))
    return {
        "status": "AVAILABLE" if details else "INSUFFICIENT_DATA",
        "drift_status": worst,
        "effective_window": min(windows) if windows else None,
        "details": details,
    }


def _field3_values(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    monitor = _mapping(state.get("field3_regime_lifecycle_monitor_20260701"))
    current = _mapping(monitor.get("current"))
    calibration = _mapping(monitor.get("calibration"))
    posterior = _mapping(calibration.get("regime_posterior"))
    regime = _mapping(canonical.get("regime"))
    probs = current.get("posterior_probabilities") or posterior.get("posterior_probabilities")
    if not isinstance(probs, Mapping):
        probs = {}
    ordered = sorted((_number(v) or 0.0 for v in probs.values()), reverse=True)
    margin = ordered[0] - ordered[1] if len(ordered) >= 2 else None
    adaptive: dict[str, Any] = {}
    with suppress(Exception):
        from core.field10_adaptive_regime_metrics_20260702 import compute_adaptive_regime_metrics
        candidate = compute_adaptive_regime_metrics(_source_frame(state), timeframe=state.get("timeframe") or _canonical(state).get("timeframe"))
        if isinstance(candidate, Mapping) and candidate.get("ok"):
            adaptive = dict(candidate)
    return {
        "higher_standard_regime": _first(current, "existing higher regime", "higher standard regime", "selected regime")
            or regime.get("higher_regime") or regime.get("major_regime") or canonical.get("regime"),
        "regime_probability": _first(current, "selected regime posterior", "regime probability")
            or posterior.get("selected_regime_posterior"),
        "regime_entropy": _first(current, "regime entropy") or posterior.get("regime_entropy"),
        "posterior_margin": margin,
        "transition_risk_1h": _first(current, "transition risk 1h") or adaptive.get("transition_risk_1h"),
        "transition_risk_3h": _first(current, "transition risk 3h") or adaptive.get("transition_risk_3h"),
        "transition_risk_6h": _first(current, "transition risk 6h") or adaptive.get("transition_risk_6h"),
        "transition_risk_24h": _first(current, "transition risk 24h")
            or canonical.get("transition_risk_24h") or regime.get("transition_risk_24h")
            or adaptive.get("transition_risk_24h"),
        "expected_return_12h": _first_present(
            _first(current, "expected return 12h", "expected return 12h (%)"),
            canonical.get("expected_return_12h"), regime.get("expected_return_12h"),
            adaptive.get("expected_return_12h"),
        ),
        "expected_return_24h": _first_present(
            _first(current, "expected return 24h", "expected return 24h (%)"),
            canonical.get("expected_return_24h"), regime.get("expected_return_24h"),
            adaptive.get("expected_return_24h"),
        ),
        "expected_return_36h": _first_present(
            _first(current, "expected return 36h", "expected return 36h (%)"),
            canonical.get("expected_return_36h"), regime.get("expected_return_36h"),
            adaptive.get("expected_return_36h"),
        ),
        "expected_duration": _first(current, "expected duration", "expected regime duration"),
        "calibrated_reliability": _first(current, "calibrated reliability", "bias reliability score", "reliability"),
    }


def _quality_values(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    with suppress(Exception):
        from core.multi_symbol_field10_20260701 import assess_data_quality
        report = assess_data_quality(state, canonical)
        if isinstance(report, Mapping):
            return dict(report)
    return {"score": None, "grade": None, "status": "UNAVAILABLE", "reasons": []}


def _execution_values(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    with suppress(Exception):
        from core.multi_symbol_field10_20260701 import _session_execution_context
        return dict(_session_execution_context(state, canonical, _timestamp(_broker_value(canonical), utc=False)))
    final = _mapping(canonical.get("final_decision"))
    return {
        "current_session": "UNAVAILABLE", "spread_quality": "UNAVAILABLE",
        "trade_permission": final.get("trade_permission") or canonical.get("trade_permission") or "CHECK",
        "final_action": final.get("final_decision") or final.get("less_risky_decision") or canonical.get("decision"),
    }


def _table4_row(table4: pd.DataFrame, canonical: Mapping[str, Any]) -> tuple[pd.Series | None, pd.Timestamp]:
    if not isinstance(table4, pd.DataFrame) or table4.empty:
        return None, pd.NaT
    time_col = _col(table4, "Broker Candle Time", "Completed Broker Candle", "Time", "Datetime", "Timestamp")
    if not time_col:
        return None, pd.NaT
    times_utc = pd.to_datetime(table4[time_col], errors="coerce", utc=True).dt.floor("h")
    target_utc = _timestamp(_broker_value(canonical), utc=True)
    matched = table4.loc[times_utc.eq(target_utc)] if pd.notna(target_utc) else pd.DataFrame()
    if matched.empty:
        # Broker-wall fallback: compare hour labels without timezone conversion.
        wall = table4[time_col].map(lambda value: pd.Timestamp(value).tz_localize(None).floor("h") if not _missing(value) else pd.NaT)
        raw_target = _broker_value(canonical)
        try:
            target_wall = pd.Timestamp(raw_target)
            if target_wall.tzinfo is not None:
                target_wall = target_wall.tz_localize(None)
            target_wall = target_wall.floor("h")
        except Exception:
            target_wall = pd.NaT
        matched = table4.loc[wall.eq(target_wall)] if pd.notna(target_wall) else pd.DataFrame()
    if matched.empty:
        return None, target_utc
    return matched.iloc[0], target_utc


def _component_reliabilities(row: pd.Series, field3: Mapping[str, Any]) -> dict[str, float | None]:
    return {
        "Technical Bias": _number(_first(row, "Technical Reliability", "Technical Bias Reliability"), percent=True),
        "Sentiment Bias": _number(_first(row, "Sentiment Reliability", "Sentiment Bias Reliability"), percent=True),
        "Session Bias": _number(_first(row, "Session Reliability", "Session Bias Reliability"), percent=True),
        "Regime Bias": _number(_first(row, "Regime Reliability", "Higher Reliability") or field3.get("calibrated_reliability"), percent=True),
        "Data-Mining Bias": _number(_first(row, "Data-Mining Reliability", "Data Mining Reliability"), percent=True),
    }


def _fusion_metrics(components: Mapping[str, Any], reliabilities: Mapping[str, float | None], quality_score: Any) -> dict[str, Any]:
    available = {name: _encoded_bias(value) for name, value in components.items()}
    available = {name: value for name, value in available.items() if value is not None}
    count = len(available)
    if not count:
        return {"available": 0, "agreement": None, "conflict": None, "shadow_score": None}
    values = list(available.values())
    counts = [values.count(-1.0), values.count(0.0), values.count(1.0)]
    agreement = max(counts) / count
    data_quality = _number(quality_score, percent=True)
    weighted: list[tuple[float, float]] = []
    for name, encoded in available.items():
        reliability = reliabilities.get(name)
        if reliability is None or data_quality is None:
            continue
        effective = _BASE_WEIGHTS[name] * float(np.clip(reliability, 0.0, 1.0)) * float(np.clip(data_quality, 0.0, 1.0))
        if effective > 0:
            weighted.append((effective, encoded))
    if not weighted:
        return {"available": count, "agreement": agreement, "conflict": None, "shadow_score": None}
    denominator = sum(weight for weight, _ in weighted)
    score = sum(weight * value for weight, value in weighted) / denominator
    variance = sum(weight * (value - score) ** 2 for weight, value in weighted) / denominator
    return {
        "available": count,
        "agreement": agreement,
        "conflict": float(np.clip(variance, 0.0, 1.0)),
        "shadow_score": float(np.clip(score, -1.0, 1.0)),
    }


def _shared_news_projection(state: Mapping[str, Any], symbol: str) -> dict[str, Any]:
    """Lightweight entity mapping over an already-published shared news pool."""
    frames: list[pd.DataFrame] = []
    for key in ("nlp_ranked_news_df", "ranked_news", "articles", "nlp_related_news_priority_20260615"):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            frames.append(value.copy(deep=False))
        elif isinstance(value, list) and value and isinstance(value[0], Mapping):
            frames.append(pd.DataFrame(value))
    if not frames:
        return {"bias": None, "source": "UNAVAILABLE", "headline": None, "publication_time": None, "entity_match": None}
    news = max(frames, key=len)
    headline_col = _col(news, "headline", "title", "news headline")
    sentiment_col = _col(news, "sentiment bias", "sentiment", "direction", "label", "regime direction")
    time_col = _col(news, "published at", "news time", "time", "date", "timestamp")
    if not headline_col or not sentiment_col:
        return {"bias": None, "source": "UNAVAILABLE", "headline": None, "publication_time": None, "entity_match": None}
    entity_map = {
        "EUR": ("EUR", "EURO", "ECB", "EUROZONE"), "USD": ("USD", "DOLLAR", "FED", "FOMC", "US "),
        "JPY": ("JPY", "YEN", "BOJ", "JAPAN"), "GBP": ("GBP", "STERLING", "BOE", "UK "),
        "AUD": ("AUD", "RBA", "AUSTRALIA"), "NZD": ("NZD", "RBNZ", "NEW ZEALAND"),
        "CAD": ("CAD", "BOC", "CANADA"), "CHF": ("CHF", "SNB", "SWISS"),
        "XAU": ("GOLD", "XAU"), "BTC": ("BITCOIN", "BTC", "CRYPTO"),
        "NAS": ("NASDAQ", "TECH STOCK"), "US5": ("S&P", "SP500", "US STOCK"),
    }
    canonical = normalize_symbol(symbol)
    codes = [canonical[:3], canonical[3:6]] if len(canonical) >= 6 else [canonical[:3]]
    terms = tuple(dict.fromkeys(term for code in codes for term in entity_map.get(code, (code,))))
    ranked: list[tuple[int, int, pd.Series]] = []
    for idx, row in news.iterrows():
        headline = str(row.get(headline_col) or "")
        upper = headline.upper()
        matches = sum(1 for term in terms if term and term in upper)
        if matches:
            ranked.append((matches, -int(idx) if isinstance(idx, (int, np.integer)) else 0, row))
    if not ranked:
        return {"bias": None, "source": "UNAVAILABLE", "headline": None, "publication_time": None, "entity_match": None}
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    row = ranked[0][2]
    return {
        "bias": _bias(row.get(sentiment_col)),
        "source": "SHARED_NEWS_SYMBOL_PROJECTION",
        "headline": str(row.get(headline_col) or ""),
        "publication_time": row.get(time_col) if time_col else None,
        "entity_match": ", ".join(term for term in terms if term in str(row.get(headline_col) or "").upper()),
    }


def publish_field1_table4_to_field10(
    *, state: MutableMapping[str, Any], canonical: Mapping[str, Any], parent_run_id: str,
    child_run_id: str, symbol: str, path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Publish the active frozen symbol's existing Field 1 Table 4 into Field 10.

    The existing Table 4 publisher is called directly.  No Technical, Sentiment,
    Session, Regime, Data-Mining, Combined Evidence or Master Action formula is
    independently reimplemented here.
    """
    migrate_integrated_evidence_database(path)
    requested = normalize_symbol(symbol)
    settings_main = main_symbol(state)
    report: dict[str, Any]
    try:
        # Publication is intentionally side-effect-free with respect to active
        # symbol/session identity. The caller must supply the matching frozen
        # child canonical object and state snapshot.
        active_canonical = dict(canonical) if isinstance(canonical, Mapping) else {}
        active_symbol = normalize_symbol(active_canonical.get("symbol") or requested)
        if active_symbol != requested:
            raise ValueError(
                f"IDENTITY_CONFLICT: frozen canonical symbol {active_symbol} does not match {requested}"
            )

        from ui.lunch_next_hour_bias_history_20260626 import build_field1_table4_publication
        table4, table4_source_status = build_field1_table4_publication(state=state, canonical=active_canonical)
        if not isinstance(table4, pd.DataFrame) or table4.empty:
            raise ValueError("Field 1 Table 4 publisher returned no completed evidence row")
        row, broker_utc = _table4_row(table4, active_canonical)
        if row is None:
            raise ValueError("Field 1 Table 4 has no row matching the active completed broker candle")

        timeframe = str(active_canonical.get("timeframe") or state.get("timeframe") or "H1").upper()
        canonical_run_id = str(active_canonical.get("run_id") or active_canonical.get("canonical_calculation_id") or "")
        source_id = str(active_canonical.get("source_id") or active_canonical.get("data_source_id") or active_canonical.get("source_snapshot_hash") or "")
        snapshot_hash = str(active_canonical.get("snapshot_hash") or active_canonical.get("source_snapshot_hash") or "")
        if not canonical_run_id or not source_id or not snapshot_hash or pd.isna(broker_utc):
            raise ValueError("Canonical run ID, source ID, snapshot hash or completed broker candle is unavailable")

        field3 = _field3_values(state, active_canonical)
        quality = _quality_values(state, active_canonical)
        execution = _execution_values(state, active_canonical)
        technical = _bias(_first(row, "Technical Bias for Next H1", "Technical Bias"))
        sentiment = _bias(_first(row, "Sentiment Bias for Next H1", "Sentiment Bias"))
        session_bias = _bias(_first(row, "Session Bias for Next H1", "Session Bias"))
        regime_bias = _bias(_first(row, "Regime Bias for Next H1", "Regime Bias"))
        data_mining = _bias(_first(row, "Data Mining Bias for Next H1", "Data-Mining Bias", "Data Mining Bias"))
        combined = _bias(_first(row, "Combined Next-Hour Direction", "Existing Combined Evidence Bias"))
        components = {
            "Technical Bias": technical,
            "Sentiment Bias": sentiment,
            "Session Bias": session_bias,
            "Regime Bias": regime_bias,
            "Data-Mining Bias": data_mining,
        }
        reliabilities = _component_reliabilities(row, field3)
        fusion = _fusion_metrics(components, reliabilities, quality.get("score"))
        cp = _incremental_changepoint(state, active_canonical, path)
        adwin = _adwin_bundle(state, table4)
        shared_sentiment = _shared_news_projection(state, requested) if sentiment is None and requested != settings_main else {}
        if sentiment is None and shared_sentiment.get("bias"):
            sentiment = shared_sentiment.get("bias")
            components["Sentiment Bias"] = sentiment
            fusion = _fusion_metrics(components, reliabilities, quality.get("score"))

        final = _mapping(active_canonical.get("final_decision"))
        protected_action = str(
            final.get("final_decision") or final.get("less_risky_decision")
            or active_canonical.get("decision") or execution.get("final_action") or "UNAVAILABLE"
        ).upper()
        permission = str(
            final.get("trade_permission") or active_canonical.get("trade_permission")
            or execution.get("trade_permission") or "CHECK"
        ).upper()
        broker_wall = pd.Timestamp(_broker_value(active_canonical))
        if broker_wall.tzinfo is not None:
            broker_wall = broker_wall.tz_localize(None)
        broker_wall = broker_wall.floor("h")
        sentiment_source = _first(row, "Sentiment Source", "Bias Source")
        if shared_sentiment.get("source"):
            sentiment_source = shared_sentiment["source"]
        missing_sources = [name for name, value in components.items() if value is None]
        explanation = (
            "Protected Table 4 evidence reused. "
            f"Available={fusion['available']}/5; missing={', '.join(missing_sources) if missing_sources else 'none'}; "
            f"shadow fusion={'UNAVAILABLE' if fusion['shadow_score'] is None else round(fusion['shadow_score'], 4)}; "
            f"weighted conflict={'UNAVAILABLE' if fusion['conflict'] is None else round(fusion['conflict'], 4)}. "
            "Protected Combined Evidence Bias and Protected Final Action were not replaced."
        )
        row_values = {
            "parent_run_id": str(parent_run_id), "child_run_id": str(child_run_id),
            "canonical_run_id": canonical_run_id, "symbol": requested,
            "role": "MAIN" if requested == settings_main else "SECONDARY", "timeframe": timeframe,
            "broker_timestamp": broker_utc.isoformat(), "broker_date": broker_wall.strftime("%Y-%m-%d"),
            "broker_hour": int(broker_wall.hour), "rank": None,
            "current_session": str(execution.get("current_session") or _first(row, "Current Session") or "UNAVAILABLE"),
            "technical_bias": technical, "technical_source": _first(row, "Technical Source", "Calculation Source") or "FIELD1_TABLE4",
            "technical_reliability": reliabilities["Technical Bias"],
            "sentiment_bias": sentiment, "sentiment_source": sentiment_source or "FIELD1_TABLE4",
            "sentiment_reliability": reliabilities["Sentiment Bias"],
            "sentiment_headline": _first(row, "Most Affecting News Headline", "Headline") or shared_sentiment.get("headline"),
            "sentiment_publication_time": shared_sentiment.get("publication_time"),
            "sentiment_entity_match": shared_sentiment.get("entity_match"),
            "session_bias": session_bias, "session_source": _first(row, "Session Source", "Bias Source") or "FIELD1_TABLE4",
            "session_reliability": reliabilities["Session Bias"],
            "regime_bias": regime_bias, "regime_source": _first(row, "Regime Source") or "FIELD1_TABLE4",
            "higher_standard_regime": field3.get("higher_standard_regime"),
            "regime_probability": _number(field3.get("regime_probability"), percent=True),
            "regime_entropy": _number(field3.get("regime_entropy")),
            "regime_posterior_margin": _number(field3.get("posterior_margin")),
            "expected_regime_duration": _number(field3.get("expected_duration")),
            "data_mining_bias": data_mining, "data_mining_source": _first(row, "Data-Mining Source", "Data Mining Source") or "FIELD1_TABLE4",
            "combined_evidence_bias": combined, "shadow_fusion_score": fusion.get("shadow_score"),
            "evidence_available_count": fusion.get("available"), "evidence_agreement": fusion.get("agreement"),
            "conflict_index": fusion.get("conflict"),
            "transition_risk_1h": _number(field3.get("transition_risk_1h"), percent=True),
            "transition_risk_3h": _number(field3.get("transition_risk_3h"), percent=True),
            "transition_risk_6h": _number(field3.get("transition_risk_6h"), percent=True),
            "transition_risk_24h": _number(field3.get("transition_risk_24h"), percent=True),
            "expected_return_12h": _number(field3.get("expected_return_12h")),
            "expected_return_24h": _number(field3.get("expected_return_24h")),
            "expected_return_36h": _number(field3.get("expected_return_36h")),
            "change_probability": _number(cp.get("changepoint_probability"), percent=True),
            "current_regime_run_length": _number(cp.get("modal_run_length")),
            "expected_stable_duration": _number(cp.get("expected_run_length")),
            "structural_break_status": str(cp.get("status") or "UNAVAILABLE"),
            "drift_status": str(adwin.get("drift_status") or "UNAVAILABLE"),
            "adaptive_window_size": adwin.get("effective_window"),
            "conformal_target_coverage": None, "conformal_coverage": None,
            "conformal_coverage_status": "UNAVAILABLE", "interval_width": None,
            "calibrated_reliability": _number(field3.get("calibrated_reliability"), percent=True),
            "data_quality_grade": quality.get("grade"), "spread_quality": execution.get("spread_quality"),
            "correlation_cluster": None, "duplicate_exposure_penalty": None, "cvar_95": None,
            "marginal_tail_risk": None, "suggested_risk_weight": None,
            "trade_permission": permission, "validation_permission": permission,
            "protected_final_action": protected_action,
            "outcome_settled": None, "actual_next_h1_direction": None, "master_action_correct": None,
            "brier_score": None, "conditional_accuracy": None,
            "explanation": explanation, "source_id": source_id, "snapshot_hash": snapshot_hash,
            "calculation_version": CALCULATION_VERSION, "created_at": _created_at(),
        }
        columns = list(row_values)
        placeholders = ",".join("?" for _ in columns)
        with sqlite3.connect(str(path), timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            cursor = conn.execute(
                f"INSERT OR IGNORE INTO {TABLE_NAME}({','.join(columns)}) VALUES({placeholders})",
                tuple(row_values[column] for column in columns),
            )
            # Retain at most 600 completed H1 identities per symbol (about 25 broker days).
            conn.execute(
                f"""DELETE FROM {TABLE_NAME} WHERE rowid IN (
                    SELECT rowid FROM {TABLE_NAME} WHERE symbol=?
                    ORDER BY broker_timestamp DESC, created_at DESC LIMIT -1 OFFSET 600
                )""",
                (requested,),
            )
            conn.commit()
            inserted = int(cursor.rowcount or 0) == 1
        report = {
            "ok": True, "status": "PUBLISHED" if inserted else "DUPLICATE_REJECTED",
            "inserted": inserted, "duplicate_rejected": not inserted, "symbol": requested,
            "parent_run_id": parent_run_id, "child_run_id": child_run_id,
            "canonical_run_id": canonical_run_id, "broker_timestamp": broker_utc.isoformat(),
            "snapshot_hash": snapshot_hash, "available_evidence_count": fusion.get("available"),
            "table4_rows": int(len(table4)), "table4_source_status": table4_source_status, "version": VERSION,
        }
    except Exception as exc:
        report = {
            "ok": False, "status": "FAILED", "symbol": requested,
            "parent_run_id": str(parent_run_id), "child_run_id": str(child_run_id),
            "error": f"{type(exc).__name__}: {exc}", "version": VERSION,
        }
    finally:
        report["activation"] = None
        report["main_restore"] = None
        state[STATE_TABLE4_STATUS] = report
    return report


def _research_rows(parent_run_id: str, path: Path | str) -> list[dict[str, Any]]:
    with sqlite3.connect(str(path), timeout=30) as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='field10_research_validation'"
        ).fetchone()
        if not exists:
            return []
        cursor = conn.execute(
            """SELECT symbol,broker_timestamp,research_reliability,data_quality_grade,
                      regime_probability,regime_entropy,expected_regime_duration,
                      transition_risk_1h,transition_risk_3h,transition_risk_6h,
                      structural_break_status,drift_status,adaptive_window_size,
                      conformal_status,conformal_coverage,interval_width,
                      correlation_cluster,duplicate_exposure_penalty,cvar_95,
                      research_permission,brier_score,explanation,result_json
               FROM field10_research_validation WHERE parent_run_id=?""",
            (parent_run_id,),
        )
        names = [item[0] for item in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def sync_integrated_research(parent_run_id: str, *, path: Path | str = DB_PATH) -> dict[str, Any]:
    """Merge saved ten-paper research diagnostics into already-persisted rows."""
    migrate_integrated_evidence_database(path)
    rows = _research_rows(parent_run_id, path)
    updated = 0
    with sqlite3.connect(str(path), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        for row in rows:
            posterior_margin = None
            current_run_length = None
            change_probability = None
            target_coverage = None
            try:
                payload = json.loads(str(row.get("result_json") or "{}"))
                hamilton = _mapping(payload.get("hamilton_regime"))
                probs = hamilton.get("probabilities") or hamilton.get("posterior_probabilities") or {}
                if isinstance(probs, Mapping):
                    ordered = sorted((_number(v) or 0.0 for v in probs.values()), reverse=True)
                    posterior_margin = ordered[0] - ordered[1] if len(ordered) >= 2 else None
                conformal = _mapping(payload.get("conformal_prediction"))
                target_coverage = _number(conformal.get("target_coverage"), percent=True)
                change = _mapping(payload.get("bayesian_changepoint"))
                change_probability = _number(change.get("change_probability"), percent=True)
                current_run_length = _number(change.get("run_length"))
            except Exception:
                pass
            cursor = conn.execute(
                f"""UPDATE {TABLE_NAME} SET
                    calibrated_reliability=COALESCE(?,calibrated_reliability),
                    data_quality_grade=COALESCE(?,data_quality_grade),
                    regime_probability=COALESCE(?,regime_probability),
                    regime_entropy=COALESCE(?,regime_entropy),
                    regime_posterior_margin=COALESCE(?,regime_posterior_margin),
                    expected_regime_duration=COALESCE(?,expected_regime_duration),
                    transition_risk_1h=COALESCE(?,transition_risk_1h),
                    transition_risk_3h=COALESCE(?,transition_risk_3h),
                    transition_risk_6h=COALESCE(?,transition_risk_6h),
                    change_probability=COALESCE(?,change_probability),
                    current_regime_run_length=COALESCE(?,current_regime_run_length),
                    structural_break_status=COALESCE(?,structural_break_status),
                    drift_status=COALESCE(?,drift_status),
                    adaptive_window_size=COALESCE(?,adaptive_window_size),
                    conformal_target_coverage=COALESCE(?,conformal_target_coverage),
                    conformal_coverage=COALESCE(?,conformal_coverage),
                    conformal_coverage_status=COALESCE(?,conformal_coverage_status),
                    interval_width=COALESCE(?,interval_width),
                    correlation_cluster=COALESCE(?,correlation_cluster),
                    duplicate_exposure_penalty=COALESCE(?,duplicate_exposure_penalty),
                    cvar_95=COALESCE(?,cvar_95),
                    validation_permission=COALESCE(?,validation_permission),
                    brier_score=COALESCE(?,brier_score),
                    explanation=CASE WHEN ? IS NULL OR ?='' THEN explanation ELSE explanation || ' Research: ' || ? END
                    WHERE parent_run_id=? AND symbol=?""",
                (
                    _number(row.get("research_reliability"), percent=True), row.get("data_quality_grade"),
                    _number(row.get("regime_probability"), percent=True), _number(row.get("regime_entropy")),
                    posterior_margin, _number(row.get("expected_regime_duration")),
                    _number(row.get("transition_risk_1h"), percent=True), _number(row.get("transition_risk_3h"), percent=True),
                    _number(row.get("transition_risk_6h"), percent=True), change_probability, current_run_length,
                    row.get("structural_break_status"), row.get("drift_status"), row.get("adaptive_window_size"),
                    target_coverage, _number(row.get("conformal_coverage"), percent=True), row.get("conformal_status"),
                    _number(row.get("interval_width")), row.get("correlation_cluster"),
                    _number(row.get("duplicate_exposure_penalty")), _number(row.get("cvar_95")),
                    row.get("research_permission"), _number(row.get("brier_score")),
                    row.get("explanation"), row.get("explanation"), row.get("explanation"),
                    parent_run_id, normalize_symbol(row.get("symbol")),
                ),
            )
            updated += max(0, int(cursor.rowcount or 0))
        conn.commit()
    return {"ok": True, "updated_rows": updated, "research_rows": len(rows), "parent_run_id": parent_run_id}


def sync_integrated_ranks(parent_run_id: str, *, path: Path | str = DB_PATH) -> dict[str, Any]:
    migrate_integrated_evidence_database(path)
    updated = 0
    with sqlite3.connect(str(path), timeout=30) as conn:
        rows = conn.execute(
            "SELECT symbol,rank FROM field10_hourly_quality WHERE parent_run_id=? AND rank IS NOT NULL",
            (parent_run_id,),
        ).fetchall()
        for symbol, rank in rows:
            cursor = conn.execute(
                f"UPDATE {TABLE_NAME} SET rank=? WHERE parent_run_id=? AND symbol=?",
                (int(rank), parent_run_id, str(symbol)),
            )
            updated += max(0, int(cursor.rowcount or 0))
        conn.commit()
    return {"ok": True, "updated_rows": updated, "parent_run_id": parent_run_id}


def _select_sql() -> str:
    return f"""SELECT
        rank AS Rank,symbol AS Symbol,role AS Role,broker_date AS [Broker Date],broker_hour AS [Broker Hour],
        timeframe AS Timeframe,broker_timestamp AS [Broker Timestamp],current_session AS [Current Session],
        technical_bias AS [Technical Bias],technical_source AS [Technical Source],technical_reliability AS [Technical Reliability],
        sentiment_bias AS [Sentiment Bias],sentiment_source AS [Sentiment Source],sentiment_reliability AS [Sentiment Reliability],
        sentiment_headline AS [Most Affecting News Headline],session_bias AS [Session Bias],session_source AS [Session Source],
        session_reliability AS [Session Reliability],data_mining_bias AS [Data-Mining Bias],
        higher_standard_regime AS [Higher Standard Regime],regime_bias AS [Regime Bias],
        regime_probability AS [Regime Probability],regime_entropy AS [Regime Entropy],regime_posterior_margin AS [Regime Posterior Margin],
        transition_risk_1h AS [Transition Risk 1H],transition_risk_3h AS [Transition Risk 3H],transition_risk_6h AS [Transition Risk 6H],
        transition_risk_24h AS [Transition Risk 24H],expected_return_12h AS [Expected Return 12H (%)],
        expected_return_24h AS [Expected Return 24H (%)],expected_return_36h AS [Expected Return 36H (%)],
        combined_evidence_bias AS [Existing Combined Evidence Bias],shadow_fusion_score AS [Shadow Fusion Score],
        evidence_available_count AS [Evidence Available Count],evidence_agreement AS [Evidence Agreement Percentage],
        conflict_index AS [Conflict Index],change_probability AS [Change Probability],current_regime_run_length AS [Current Regime Run Length],
        drift_status AS [Drift Status],adaptive_window_size AS [Adaptive Window Size],calibrated_reliability AS [Calibrated Reliability],
        conformal_coverage_status AS [Conformal Coverage Status],conformal_coverage AS [Conformal Coverage],interval_width AS [Prediction Interval Width],
        data_quality_grade AS [Data Quality Grade],spread_quality AS [Spread Quality],correlation_cluster AS [Correlation Cluster],
        duplicate_exposure_penalty AS [Duplicate Exposure Penalty],cvar_95 AS [CVaR 95],marginal_tail_risk AS [Marginal Tail Risk],
        suggested_risk_weight AS [Suggested Risk Weight],trade_permission AS [Trade Permission],validation_permission AS [Validation Permission],
        protected_final_action AS [Protected Final Action],outcome_settled AS [Outcome Settled],actual_next_h1_direction AS [Actual Next-H1 Direction],
        master_action_correct AS [Master Action Correct],brier_score AS [Brier Score],conditional_accuracy AS [Conditional Accuracy],
        explanation AS Explanation,parent_run_id AS [Parent Run ID],child_run_id AS [Child Run ID],canonical_run_id AS [Canonical Run ID],
        source_id AS [Source ID],snapshot_hash AS [Snapshot Hash],calculation_version AS [Calculation Version],
        publication_status AS [Publication Status],created_at AS [Created At]
        FROM {TABLE_NAME}"""


def load_integrated_current(parent_run_id: str, *, path: Path | str = DB_PATH) -> pd.DataFrame:
    with connect_readonly(path, timeout=30) as conn:
        frame = pd.read_sql_query(
            _select_sql() + " WHERE parent_run_id=? ORDER BY rank IS NULL,rank ASC,broker_timestamp DESC,symbol",
            conn, params=(str(parent_run_id),),
        )
    if frame.empty:
        return frame
    frame["Broker Timestamp"] = pd.to_datetime(frame["Broker Timestamp"], errors="coerce", utc=True)
    frame = frame.sort_values(["Symbol", "Broker Timestamp"], ascending=[True, False], kind="mergesort")
    frame = frame.drop_duplicates("Symbol", keep="first")
    return frame.sort_values(["Rank", "Symbol"], na_position="last", kind="mergesort").reset_index(drop=True)


def query_integrated_history(
    *, symbols: Sequence[str] | None = None, parent_run_id: str | None = None,
    filters: Mapping[str, Sequence[Any] | Any] | None = None, search: str = "",
    limit: int = 200, offset: int = 0, complete_export: bool = False,
    path: Path | str = DB_PATH,
) -> tuple[pd.DataFrame, int]:
    """Lazy/paginated history query with a bounded complete export path."""
    clauses: list[str] = []
    params: list[Any] = []
    if parent_run_id:
        clauses.append("parent_run_id=?")
        params.append(str(parent_run_id))
    selected = [normalize_symbol(value) for value in (symbols or []) if str(value or "").strip()]
    if selected:
        clauses.append("symbol IN (" + ",".join("?" for _ in selected) + ")")
        params.extend(selected)
    sql_columns = {
        "Role": "role", "Current Session": "current_session", "Technical Bias": "technical_bias",
        "Sentiment Bias": "sentiment_bias", "Regime Bias": "regime_bias",
        "Higher Standard Regime": "higher_standard_regime", "Data Quality Grade": "data_quality_grade",
        "Drift Status": "drift_status", "Trade Permission": "trade_permission",
        "Protected Final Action": "protected_final_action", "Validation Permission": "validation_permission",
        "Outcome Settled": "outcome_settled",
    }
    for label, values in (filters or {}).items():
        column = sql_columns.get(str(label))
        if not column:
            continue
        choices = list(values) if isinstance(values, (list, tuple, set)) else [values]
        choices = [value for value in choices if not _missing(value)]
        if choices:
            clauses.append(f"{column} IN (" + ",".join("?" for _ in choices) + ")")
            params.extend(choices)
    if search.strip():
        needle = f"%{search.strip().lower()}%"
        search_columns = (
            "symbol", "role", "current_session", "technical_bias", "sentiment_bias", "session_bias",
            "regime_bias", "higher_standard_regime", "combined_evidence_bias", "data_quality_grade",
            "drift_status", "trade_permission", "protected_final_action", "explanation", "source_id",
            "canonical_run_id", "parent_run_id", "child_run_id",
        )
        clauses.append("(" + " OR ".join(f"LOWER(COALESCE({column},'')) LIKE ?" for column in search_columns) + ")")
        params.extend([needle] * len(search_columns))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    max_limit = 20000 if complete_export else max(1, min(int(limit), 1000))
    with connect_readonly(path, timeout=30) as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}{where}", tuple(params)).fetchone()[0])
        frame = pd.read_sql_query(
            _select_sql() + where + " ORDER BY broker_timestamp DESC,rank IS NULL,rank ASC,symbol LIMIT ? OFFSET ?",
            conn, params=tuple(params + [max_limit, 0 if complete_export else max(0, int(offset))]),
        )
    return frame, total


def load_integrated_validation_for_symbol(symbol: str, *, path: Path | str = DB_PATH) -> pd.DataFrame:
    frame, _ = query_integrated_history(symbols=[symbol], limit=600, path=path)
    return frame


def _series_alias(frame: pd.DataFrame, aliases: Sequence[str]) -> pd.Series:
    column = _col(frame, *aliases)
    return frame[column] if column else pd.Series(pd.NA, index=frame.index, dtype="object")


def _settled_mask(frame: pd.DataFrame) -> pd.Series:
    status = _series_alias(frame, ("Outcome Status", "Outcome Settled", "Settlement Status"))
    normalized = status.astype(str).str.strip().str.upper()
    return normalized.isin({"SETTLED", "RESOLVED", "TRUE", "1", "YES"})


def enrich_table5_quant_validation(
    table5: pd.DataFrame, *, state: Mapping[str, Any], canonical: Mapping[str, Any],
    field10_validation: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return a display-only enriched copy of protected Field 1 Table 5."""
    if not isinstance(table5, pd.DataFrame) or table5.empty:
        return pd.DataFrame(columns=list(table5.columns) + list(_TABLE5_COLUMNS)) if isinstance(table5, pd.DataFrame) else pd.DataFrame(columns=_TABLE5_COLUMNS)
    protected = table5.copy(deep=True)
    out = table5.copy(deep=True)
    time_col = _col(out, "Broker Candle Time", "Completed Broker Candle", "Time", "Datetime", "Timestamp")
    if not time_col:
        for column in _TABLE5_COLUMNS:
            if column not in out.columns:
                out[column] = pd.NA
        return out
    out["_field10_join_time"] = pd.to_datetime(out[time_col], errors="coerce", utc=True).dt.floor("h")
    symbol = normalize_symbol(canonical.get("symbol") or state.get("symbol") or "EURUSD")
    if "Symbol" not in out.columns:
        out["Symbol"] = symbol
    else:
        out["Symbol"] = out["Symbol"].where(out["Symbol"].notna(), symbol).map(normalize_symbol)

    direct_aliases = {
        "Technical Bias": ("Technical Bias for Next H1", "Table 4 Technical Bias"),
        "Sentiment Bias": ("Sentiment Bias for Next H1",),
        "Session Bias": ("Session Bias for Next H1",),
        "Regime Bias": ("Regime Bias for Next H1",),
        "Data-Mining Bias": ("Data Mining Bias for Next H1", "Data-Mining Bias"),
        "Existing Combined Evidence Bias": ("Combined Next-Hour Direction", "Existing Combined Evidence Bias"),
        "Master Action": ("Master Action", "Production Master Decision", "Final Decision", "Master Decision"),
        "News": ("News", "Most Affecting News Headline", "Headline", "Title", "News Headline", "Highest Impact News Title"),
        "Evidence Available Count": ("Available Sources", "Evidence Available Count"),
        "Evidence Agreement Percentage": ("Evidence Agreement Percentage",),
        "Weighted Conflict Index": ("Weighted Conflict Index", "Conflict Index"),
        "Canonical Run ID": ("Canonical Run ID", "Canonical run_id", "run_id"),
        "Source ID": ("Source ID",), "Snapshot Hash": ("Snapshot Hash", "Source Snapshot Hash"),
    }
    for target, aliases in direct_aliases.items():
        if target == "Master Action" and target in out.columns:
            continue
        source = _col(out, *aliases)
        if source:
            out[target] = out[source]
        elif target not in out.columns:
            out[target] = pd.NA

    if "Evidence Agreement Percentage" not in out.columns or out["Evidence Agreement Percentage"].isna().all():
        directional = pd.to_numeric(_series_alias(out, ("Directional Agreement",)), errors="coerce")
        available = pd.to_numeric(_series_alias(out, ("Available Sources", "Evidence Available Count")), errors="coerce").replace(0, np.nan)
        out["Evidence Agreement Percentage"] = directional.div(available)

    if field10_validation is None:
        field10_validation = load_integrated_validation_for_symbol(symbol)
    validation = field10_validation.copy(deep=True) if isinstance(field10_validation, pd.DataFrame) else pd.DataFrame()
    if not validation.empty:
        validation_time = _col(validation, "Broker Timestamp", "Broker Candle Time")
        if validation_time:
            validation["_field10_join_time"] = pd.to_datetime(validation[validation_time], errors="coerce", utc=True).dt.floor("h")
            validation["Symbol"] = _series_alias(validation, ("Symbol",)).map(normalize_symbol)
            keep = ["_field10_join_time", "Symbol"] + [column for column in validation.columns if column not in {"_field10_join_time", "Symbol"}]
            validation = validation.loc[:, list(dict.fromkeys(keep))].drop_duplicates(["_field10_join_time", "Symbol"], keep="first")
            out = out.merge(validation, on=["_field10_join_time", "Symbol"], how="left", suffixes=("", "__field10"), validate="many_to_one")

    field10_aliases = {
        "Higher Standard Regime": ("Higher Standard Regime",), "Regime Probability": ("Regime Probability",),
        "Regime Entropy": ("Regime Entropy",), "Regime Posterior Margin": ("Regime Posterior Margin",),
        "Transition Risk 1H": ("Transition Risk 1H",), "Transition Risk 3H": ("Transition Risk 3H",),
        "Transition Risk 6H": ("Transition Risk 6H",), "Change Probability Now": ("Change Probability",),
        "Current Regime Run Length": ("Current Regime Run Length",), "Drift Status": ("Drift Status",),
        "Adaptive Window Size": ("Adaptive Window Size",), "Calibrated Reliability": ("Calibrated Reliability",),
        "Conformal Coverage Status": ("Conformal Coverage Status",), "Prediction Interval Width": ("Prediction Interval Width",),
        "Data Quality Grade": ("Data Quality Grade", "Data Quality"), "Validation Permission": ("Validation Permission", "Trade Permission"),
        "Child Run ID": ("Child Run ID",), "Parent Multi-Symbol Run ID": ("Parent Run ID",),
        "Calculation Version": ("Calculation Version",), "Brier Score": ("Brier Score",),
        "Conditional Accuracy": ("Conditional Accuracy",),
    }
    for target, aliases in field10_aliases.items():
        candidates = []
        for alias in aliases:
            candidates.extend([alias, f"{alias}__field10"])
        source = _col(out, *candidates)
        if source and source != target:
            if target not in out.columns:
                out[target] = out[source]
            else:
                out[target] = out[target].where(out[target].notna(), out[source])
        elif target not in out.columns:
            out[target] = pd.NA

    settled = _settled_mask(out)
    out["Outcome Settled"] = settled
    actual = _series_alias(out, ("Actual Next-H1 Direction", "Actual Direction", "Realized Direction", "Outcome Direction"))
    correct = _series_alias(out, ("Master Action Correct", "Decision Correct"))
    out["Actual Next-H1 Direction"] = actual.where(settled, pd.NA)
    out["Master Action Correct"] = correct.where(settled, pd.NA)
    for column in ("Brier Score", "Conditional Accuracy"):
        if column in out.columns:
            out[column] = out[column].where(settled, pd.NA)

    current = _timestamp(_broker_value(canonical))
    current_mask = out["_field10_join_time"].eq(current) if pd.notna(current) else pd.Series(False, index=out.index)
    identities = {
        "Canonical Run ID": canonical.get("run_id") or canonical.get("canonical_calculation_id"),
        "Child Run ID": state.get("multi_symbol_current_child_id_20260701"),
        "Parent Multi-Symbol Run ID": state.get("multi_symbol_parent_run_id_20260701"),
        "Source ID": canonical.get("source_id") or canonical.get("data_source_id"),
        "Snapshot Hash": canonical.get("snapshot_hash") or canonical.get("source_snapshot_hash"),
        "Calculation Version": CALCULATION_VERSION,
    }
    for column, value in identities.items():
        if column not in out.columns:
            out[column] = pd.NA
        if not _missing(value):
            out.loc[current_mask & out[column].isna(), column] = value

    for column in _TABLE5_COLUMNS:
        if column not in out.columns:
            out[column] = pd.NA
    out = out.sort_values("_field10_join_time", ascending=False, kind="mergesort")
    days = list(dict.fromkeys(out["_field10_join_time"].dropna().dt.date.tolist()))[:25]
    out = out.loc[out["_field10_join_time"].dt.date.isin(days)].drop(columns=["_field10_join_time"], errors="ignore").reset_index(drop=True)

    # Explicit immutability guard for tests and future maintenance.
    if not protected.equals(table5):
        raise AssertionError("Protected Table 5 source was mutated during enrichment")
    return out


def prepare_evidence_alignment_heatmap(current: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create encoded heatmap data and hover text from copies only."""
    if not isinstance(current, pd.DataFrame) or current.empty:
        return pd.DataFrame(), pd.DataFrame()
    source = current.copy(deep=True)
    if "Rank" in source.columns:
        source["_rank"] = pd.to_numeric(source["Rank"], errors="coerce")
        source = source.sort_values(["_rank", "Symbol"], na_position="last", kind="mergesort")
    else:
        source = source.sort_values("Symbol", kind="mergesort")
    columns = [
        "Technical Evidence", "Sentiment Evidence", "Session Evidence", "Regime Evidence",
        "Existing Combined Evidence", "Agreement", "Calibrated Reliability", "Data Quality", "Transition Safety",
    ]
    data = pd.DataFrame(index=source["Symbol"].astype(str), columns=columns, dtype=float)
    bias_map = {
        "Technical Evidence": "Technical Bias", "Sentiment Evidence": "Sentiment Bias",
        "Session Evidence": "Session Bias", "Regime Evidence": "Regime Bias",
        "Existing Combined Evidence": "Existing Combined Evidence Bias",
    }
    for display, original in bias_map.items():
        if original in source.columns:
            data[display] = source.set_index(source["Symbol"].astype(str))[original].map(_encoded_bias)
    def normalized(column: str) -> pd.Series:
        values = pd.to_numeric(source.get(column), errors="coerce")
        return values.where(values.abs() <= 1.0, values / 100.0).clip(0.0, 1.0)
    if "Evidence Agreement Percentage" in source.columns:
        data["Agreement"] = normalized("Evidence Agreement Percentage").to_numpy()
    if "Calibrated Reliability" in source.columns:
        data["Calibrated Reliability"] = normalized("Calibrated Reliability").to_numpy()
    grade_map = {"A": 1.0, "B": 0.75, "C": 0.50, "D": 0.25}
    if "Data Quality Grade" in source.columns:
        data["Data Quality"] = source["Data Quality Grade"].astype(str).str.upper().map(grade_map).to_numpy()
    if "Transition Risk 3H" in source.columns:
        risk = normalized("Transition Risk 3H")
        data["Transition Safety"] = (1.0 - risk).where(risk.notna()).to_numpy()
    hover = pd.DataFrame(index=data.index, columns=data.columns, dtype=object)
    for position, (_, row) in enumerate(source.iterrows()):
        symbol = str(row.get("Symbol") or "")
        base = (
            f"Symbol={symbol}<br>Broker Timestamp={row.get('Broker Timestamp', '')}"
            f"<br>Canonical Run ID={row.get('Canonical Run ID', '')}"
            f"<br>Source ID={row.get('Source ID', '')}<br>Explanation={row.get('Explanation', '')}"
        )
        originals = {
            "Technical Evidence": row.get("Technical Bias"), "Sentiment Evidence": row.get("Sentiment Bias"),
            "Session Evidence": row.get("Session Bias"), "Regime Evidence": row.get("Regime Bias"),
            "Existing Combined Evidence": row.get("Existing Combined Evidence Bias"),
            "Agreement": row.get("Evidence Agreement Percentage"),
            "Calibrated Reliability": row.get("Calibrated Reliability"),
            "Data Quality": row.get("Data Quality Grade"),
            "Transition Safety": f"1 - Transition Risk 3H ({row.get('Transition Risk 3H')})",
        }
        for column in data.columns:
            hover.iloc[position, hover.columns.get_loc(column)] = f"{base}<br>{column}={originals[column]}"
    return data, hover


def table5_data_dictionary() -> pd.DataFrame:
    rows = []
    for column in _TABLE5_COLUMNS:
        rows.append({
            "Column": column,
            "Type": "numeric" if any(token in column for token in ("Percentage", "Index", "Probability", "Entropy", "Risk", "Length", "Reliability", "Width", "Score", "Accuracy")) else "text/boolean",
            "Source": "Protected Table 5/Table 4 or identity-matched Field 10 validation",
            "Missing Rule": "Null/UNAVAILABLE; never forward-filled and never converted to WAIT",
            "Production Effect": "None — display/shadow validation only" if column not in {"Master Action", "Existing Combined Evidence Bias"} else "Protected production value copied unchanged",
        })
    return pd.DataFrame(rows)


def current_table_data_dictionary() -> pd.DataFrame:
    migrate_integrated_evidence_database(DB_PATH)
    with sqlite3.connect(str(DB_PATH), timeout=30) as conn:
        info = conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
    return pd.DataFrame([
        {"Column": row[1], "SQLite Type": row[2], "Not Null": bool(row[3]), "Primary Key Position": int(row[5])}
        for row in info
    ])


__all__ = [
    "VERSION", "CALCULATION_VERSION", "TABLE_NAME", "STATE_TABLE4_STATUS", "STATE_CURRENT", "STATE_HISTORY",
    "migrate_integrated_evidence_database", "publish_field1_table4_to_field10", "sync_integrated_research",
    "sync_integrated_ranks", "load_integrated_current", "query_integrated_history",
    "load_integrated_validation_for_symbol", "enrich_table5_quant_validation", "prepare_evidence_alignment_heatmap",
    "table5_data_dictionary", "current_table_data_dictionary",
]
