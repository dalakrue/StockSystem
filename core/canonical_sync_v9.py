"""Canonical synchronization contract for Settings, Lunch, Priority, AI and copy.

V10 is an additive, immutable projection over the protected Settings calculation.
It never starts a complete calculation. Every Lunch field, copy export, priority
view and grounded AI answer reads the same published run contract.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, MutableMapping
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

VERSION = "canonical-sync-v10-20260623"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "canonical_sync_v9.sqlite3"
STATE_KEY = "canonical_run_snapshot_v9"
RUN_ID_KEY = "canonical_run_id_v9"
HASH_KEY = "canonical_snapshot_hash_v9"


@dataclass(frozen=True)
class CanonicalRunSnapshot:
    """One immutable run contract shared by all read-only consumers.

    The compatibility scalar fields remain in the same contract so existing V9
    UI and exports continue to work without a second source of truth.
    """

    # Required V10 identity and evidence contract.
    run_id: str
    generation_id: str
    created_at_utc: str
    completed_candle_utc: str
    broker_candle_time: str
    broker_timezone: str
    broker_offset_minutes: int
    symbol: str
    timeframe: str
    decision: str
    less_risky_bias: str
    regime: str
    regime_probabilities: Mapping[str, Any]
    priority: Mapping[str, Any]
    reliability: Mapping[str, Any]
    forecasts: Mapping[str, Any]
    prediction_intervals: Mapping[str, Any]
    technical_evidence: Mapping[str, Any]
    sentiment: Mapping[str, Any]
    conflicts: Mapping[str, Any]
    uncertainty: float
    data_quality: Mapping[str, Any]
    histories: Mapping[str, Any]
    provenance: Mapping[str, Any]

    # V9 compatibility fields, all derived from the same values above.
    broker_time: str
    candle_time: str
    master_score: float
    entry_score: float
    hold_score: float
    tp_score: float
    exit_risk_score: float
    regime_probability: float
    regime_age: float
    change_point_probability: float
    priority_score: float
    priority_label: str
    reliability_score: float
    data_quality_score: float
    direction: str
    confidence: float
    error_pct: float
    source_freshness_minutes: float
    snapshot_hash: str


_REQUIRED_V10 = (
    "run_id", "generation_id", "created_at_utc", "completed_candle_utc",
    "broker_candle_time", "broker_timezone", "broker_offset_minutes", "symbol",
    "timeframe", "decision", "less_risky_bias", "regime",
    "regime_probabilities", "priority", "reliability", "forecasts",
    "prediction_intervals", "technical_evidence", "sentiment", "conflicts",
    "uncertainty", "data_quality", "histories", "provenance",
)


def _state(state: MutableMapping[str, Any] | None = None) -> MutableMapping[str, Any]:
    if state is not None:
        return state
    try:
        import streamlit as st
        return st.session_state
    except Exception:
        return {}


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.DataFrame):
        return value.tail(100).to_dict("records")
    if isinstance(value, pd.Series):
        return value.tail(100).tolist()
    if isinstance(value, set):
        return sorted(value)
    return str(value)


def _json_mapping(value: Any, *, maximum_rows: int = 25) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(k): _json_value(v, maximum_rows=maximum_rows) for k, v in value.items()}
    return {}


def _json_value(value: Any, *, maximum_rows: int = 25) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_value(v, maximum_rows=maximum_rows) for k, v in value.items()}
    if isinstance(value, pd.DataFrame):
        return value.tail(maximum_rows).to_dict("records")
    if isinstance(value, pd.Series):
        return value.tail(maximum_rows).tolist()
    if isinstance(value, (list, tuple)):
        return [_json_value(v, maximum_rows=maximum_rows) for v in list(value)[-maximum_rows:]]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if np.isfinite(out) else default
    except Exception:
        return default


def _score10(value: Any, default: float = 5.0) -> float:
    value = _num(value, default)
    return value / 10.0 if value > 10.0 else value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return default


def _find(mapping: Mapping[str, Any], aliases: tuple[str, ...], default: Any = None, depth: int = 0) -> Any:
    if depth > 6:
        return default
    normalized = {str(k).lower().replace(" ", "_").replace("/", "_"): v for k, v in mapping.items()}
    for alias in aliases:
        key = alias.lower().replace(" ", "_").replace("/", "_")
        if key in normalized and normalized[key] not in (None, ""):
            return normalized[key]
    for value in mapping.values():
        if isinstance(value, Mapping):
            found = _find(value, aliases, None, depth + 1)
            if found not in (None, ""):
                return found
    return default


def _utc(value: Any) -> pd.Timestamp | None:
    try:
        ts = pd.to_datetime(value, errors="coerce", utc=True)
        return None if pd.isna(ts) else pd.Timestamp(ts)
    except Exception:
        return None


def _canonical(state: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        if isinstance(value, Mapping) and value:
            return dict(value)
    except Exception:
        pass
    for key in (
        "canonical_decision_result_20260617", "last_valid_canonical_decision_result_20260617",
        "canonical_decision_result", "canonical_result_20260617", "canonical_result",
    ):
        value = state.get(key)
        if isinstance(value, Mapping) and value:
            return dict(value)
    return {}


def _clock(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from core.shared_broker_time_20260622 import shared_broker_time_provider
        value = shared_broker_time_provider(state, canonical=canonical)
        return dict(value) if isinstance(value, Mapping) else {}
    except Exception:
        return {}


def _priority_row(canonical: Mapping[str, Any], state: Mapping[str, Any]) -> Mapping[str, Any]:
    candidates = [
        canonical.get("canonical_priority_table"), canonical.get("priority_table"),
        state.get("canonical_priority_table_20260617"),
    ]
    for value in candidates:
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.iloc[0].to_dict()
        if isinstance(value, list) and value and isinstance(value[0], Mapping):
            return value[0]
        if isinstance(value, Mapping):
            return value
    return {}


def _label(score: float) -> str:
    if score >= 85: return "A+"
    if score >= 72: return "A"
    if score >= 60: return "B"
    if score >= 48: return "C"
    return "AVOID"


def _anti_constant_priority(*, base: float, entry: float, exit_risk: float, tp: float,
                            reliability: float, data_quality: float, freshness: float,
                            volatility: float, change_probability: float,
                            forecast_disagreement: float) -> tuple[float, list[str]]:
    factors = {
        "entry strength": 0.18 * (entry * 10.0 - 50.0),
        "exit-risk control": 0.16 * (50.0 - exit_risk * 10.0),
        "TP quality": 0.12 * (tp * 10.0 - 50.0),
        "reliability": 0.14 * (reliability - 50.0),
        "data quality": 0.12 * (data_quality - 50.0),
        "freshness": -0.12 * max(freshness - 60.0, 0.0),
        "volatility risk": -0.08 * (volatility - 50.0),
        "regime change": -18.0 * change_probability,
        "forecast disagreement": -0.10 * forecast_disagreement,
    }
    score = float(np.clip(0.35 * base + 0.65 * 50.0 + sum(factors.values()), 0.0, 100.0))
    ranked = sorted(factors.items(), key=lambda item: abs(item[1]), reverse=True)
    reasons = [f"{name}: {'+' if value >= 0 else ''}{value:.1f}" for name, value in ranked[:3]]
    return round(score, 4), reasons


def _hash_payload(payload: Mapping[str, Any]) -> str:
    clean = {k: payload.get(k) for k in sorted(payload) if k != "snapshot_hash"}
    raw = json.dumps(clean, sort_keys=True, ensure_ascii=True, default=_json_default, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()[:20]


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS canonical_run_snapshots (
        run_id TEXT PRIMARY KEY, created_at_utc TEXT NOT NULL, broker_time TEXT NOT NULL,
        candle_time TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
        snapshot_hash TEXT NOT NULL UNIQUE, snapshot_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS priority_history (
        run_id TEXT PRIMARY KEY, broker_time TEXT, candle_time TEXT, symbol TEXT, timeframe TEXT,
        priority_score REAL, priority_label TEXT, regime TEXT, reliability_score REAL,
        data_quality_score REAL, decision TEXT, priority_reason_1 TEXT,
        priority_reason_2 TEXT, priority_reason_3 TEXT, snapshot_hash TEXT
    );
    CREATE TABLE IF NOT EXISTS lunch_history_quality (
        unique_key TEXT PRIMARY KEY, symbol TEXT, timeframe TEXT, candle_time TEXT,
        broker_time TEXT, field_name TEXT, metric_name TEXT, metric_value TEXT,
        data_quality_score REAL, source_freshness_minutes REAL, run_id TEXT,
        snapshot_hash TEXT, payload_json TEXT, updated_at_utc TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_priority_broker_time ON priority_history(broker_time DESC);
    CREATE INDEX IF NOT EXISTS idx_lunch_quality_broker_time ON lunch_history_quality(broker_time DESC);
    """)


def _persist(snapshot: CanonicalRunSnapshot, reasons: list[str], state: MutableMapping[str, Any]) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(snapshot)
    with sqlite3.connect(str(DB_PATH), timeout=20) as conn:
        _ensure_schema(conn)
        conn.execute(
            "INSERT OR REPLACE INTO canonical_run_snapshots(run_id,created_at_utc,broker_time,candle_time,symbol,timeframe,snapshot_hash,snapshot_json) VALUES (?,?,?,?,?,?,?,?)",
            (snapshot.run_id, snapshot.created_at_utc, snapshot.broker_time, snapshot.candle_time,
             snapshot.symbol, snapshot.timeframe, snapshot.snapshot_hash,
             json.dumps(payload, default=_json_default, sort_keys=True)),
        )
        padded = (reasons + [None, None, None])[:3]
        conn.execute(
            "INSERT OR REPLACE INTO priority_history(run_id,broker_time,candle_time,symbol,timeframe,priority_score,priority_label,regime,reliability_score,data_quality_score,decision,priority_reason_1,priority_reason_2,priority_reason_3,snapshot_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (snapshot.run_id, snapshot.broker_time, snapshot.candle_time, snapshot.symbol,
             snapshot.timeframe, snapshot.priority_score, snapshot.priority_label, snapshot.regime,
             snapshot.reliability_score, snapshot.data_quality_score, snapshot.decision,
             padded[0], padded[1], padded[2], snapshot.snapshot_hash),
        )
        conn.commit()
    state["canonical_priority_reasons_v9"] = reasons
    state["canonical_priority_history_v9"] = load_priority_history()


def validate_snapshot(snapshot: CanonicalRunSnapshot | Mapping[str, Any]) -> dict[str, Any]:
    payload = asdict(snapshot) if isinstance(snapshot, CanonicalRunSnapshot) else dict(snapshot or {})
    errors: list[str] = []
    for key in _REQUIRED_V10:
        if key not in payload or payload.get(key) is None or (isinstance(payload.get(key), str) and not payload.get(key)):
            errors.append(f"missing {key}")
    if payload.get("snapshot_hash") and str(payload.get("snapshot_hash")) != _hash_payload(payload):
        errors.append("snapshot_hash mismatch")
    for key in ("priority_score", "reliability_score", "data_quality_score", "confidence", "uncertainty"):
        value = _num(payload.get(key), -1.0)
        if value < 0.0 or value > 100.0:
            errors.append(f"{key} outside 0..100")
    if str(payload.get("symbol", "")).upper() == "": errors.append("symbol empty")
    if str(payload.get("timeframe", "")).upper() == "": errors.append("timeframe empty")
    return {
        "ok": not errors, "errors": errors, "run_id": payload.get("run_id"),
        "snapshot_hash": payload.get("snapshot_hash"), "version": VERSION,
        "required_contract_fields": list(_REQUIRED_V10),
    }


def _usable(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (pd.DataFrame, pd.Series)):
        return not value.empty
    if isinstance(value, (Mapping, list, tuple, set, str)):
        return bool(value)
    return True


def _choose(*values: Any) -> Any:
    return next((value for value in values if _usable(value)), None)


def _bounded_histories(canonical: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    candidates = {
        "overall_full_metric": _choose(canonical.get("full_metric_history"), state.get("full_metric_history_df_20260618")),
        "decision_histories": _choose(canonical.get("reverse_10_history"), _mapping(state.get("lunch_metric_result_cache")).get("history_by_factor")),
        "priority": _choose(canonical.get("canonical_priority_table"), canonical.get("priority_table")),
        "reliability": _choose(canonical.get("reliability_history"), state.get("reliability_history_20260618")),
        "settled_outcomes": _choose(canonical.get("settled_outcomes"), canonical.get("decision_outcome")),
    }
    for name, value in candidates.items():
        if _usable(value):
            output[name] = _json_value(value, maximum_rows=25)
    return output


def _prediction_intervals(forecasts: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    horizons = _mapping(forecasts.get("horizons"))
    for horizon in (1, 3, 6):
        item = _mapping(horizons.get(horizon) or horizons.get(str(horizon)) or horizons.get(f"{horizon}h") or horizons.get(f"H+{horizon}"))
        if item:
            result[f"{horizon}h"] = {
                "lower": _first(item.get("calibrated_lower"), item.get("lower_bound"), item.get("lower")),
                "upper": _first(item.get("calibrated_upper"), item.get("upper_bound"), item.get("upper")),
                "coverage": _first(item.get("coverage"), item.get("interval_coverage")),
                "status": _first(item.get("settlement_status"), item.get("status"), default="PENDING"),
            }
    if not result:
        result = _json_mapping(forecasts.get("prediction_intervals"))
    return result


def write_snapshot_from_settings_run(result: Mapping[str, Any] | None,
                                     state: MutableMapping[str, Any] | None = None) -> CanonicalRunSnapshot:
    state = _state(state)
    canonical = _canonical(state)
    if not canonical:
        raise RuntimeError("No completed canonical Settings generation is available for V10 publication.")
    result = result if isinstance(result, Mapping) else {}
    final = _mapping(canonical.get("final_decision"))
    full = _mapping(canonical.get("full_metric_snapshot"))
    row = _mapping(canonical.get("full_metric_current_row"))
    priority_row = _priority_row(canonical, state)
    clock = _clock(state, canonical)
    candle_ts = _utc(_first(
        canonical.get("latest_completed_candle_time"), canonical.get("latest_completed_h1_utc"),
        clock.get("latest_completed_h1_utc"), clock.get("latest_broker_candle_utc"),
    ))
    created = _utc(canonical.get("created_at")) or pd.Timestamp.now(tz="UTC")
    now = pd.Timestamp.now(tz="UTC")
    freshness = max(0.0, float((now - candle_ts).total_seconds() / 60.0)) if candle_ts is not None else 99999.0
    run_id = str(_first(canonical.get("canonical_calculation_id"), canonical.get("run_id"), result.get("run_id"), default=""))
    generation_id = str(_first(canonical.get("calculation_generation"), state.get("canonical_calculation_generation_20260617"), result.get("generation_id"), default="0"))
    master = _score10(_first(_find(full, ("master_score", "master")), _find(row, ("master_score", "master")), default=5.0))
    entry = _score10(_first(_find(full, ("entry_score", "entry_strength", "entry")), _find(row, ("entry_score", "entry_strength", "entry")), default=5.0))
    hold = _score10(_first(_find(full, ("hold_score", "hold_safety", "hold")), _find(row, ("hold_score", "hold_safety", "hold")), default=5.0))
    tp = _score10(_first(_find(full, ("tp_score", "tp_quality", "tp")), _find(row, ("tp_score", "tp_quality", "tp")), default=5.0))
    exit_risk = _score10(_first(_find(full, ("exit_risk_score", "exit_risk")), _find(row, ("exit_risk_score", "exit_risk")), default=5.0))
    regime_value = _first(_find(canonical, ("current_regime", "current_major_regime", "regime_label", "regime")), default="UNKNOWN")
    if isinstance(regime_value, Mapping):
        regime_value = _first(regime_value.get("major_regime"), regime_value.get("current_regime"), regime_value.get("regime"), default="UNKNOWN")
    regime = str(regime_value)
    regime_probability = _num(_first(_find(canonical, ("regime_probability", "regime_confidence", "regime_reliability")), default=0.5), 0.5)
    if regime_probability > 1.0: regime_probability /= 100.0
    regime_age = _num(_first(_find(canonical, ("regime_age", "days_since_regime_change", "regime_days")), default=0.0), 0.0)
    reliability_score = _num(_first(_find(canonical, ("deflated_reliability_score", "reliability_score", "reliability")), _find(priority_row, ("reliability_score", "reliability")), default=50.0), 50.0)
    if reliability_score <= 1.0: reliability_score *= 100.0
    confidence = _num(_first(final.get("confidence"), final.get("confidence_pct"), _find(canonical, ("confidence", "forecast_confidence")), default=reliability_score), reliability_score)
    if confidence <= 1.0: confidence *= 100.0
    uncertainty = _num(_first(final.get("uncertainty"), final.get("uncertainty_pct"), canonical.get("uncertainty"), default=100.0 - confidence), 100.0 - confidence)
    if uncertainty <= 1.0: uncertainty *= 100.0
    error_pct = _num(_first(_find(canonical, ("error_pct", "avg_abs_close_error_pct", "prediction_error_pct")), default=0.0), 0.0)
    disagreement = _num(_first(_find(canonical, ("forecast_disagreement", "forecast_disagreement_pct")), default=0.0), 0.0)
    if disagreement <= 1.0: disagreement *= 100.0
    base_priority = _num(_first(_find(priority_row, ("priority_score", "score", "knn_priority_score")), _find(canonical, ("priority_score",)), default=50.0), 50.0)
    raw_quality = _num(_first(_find(canonical, ("data_quality_score", "quality_score")), default=100.0 - min(freshness / 6.0, 60.0)), 50.0)
    frame = state.get("canonical_completed_ohlc_df_20260617")
    if not isinstance(frame, pd.DataFrame):
        frame = state.get("last_df")
    try:
        from core.quant_research_v9 import build_quant_research_v9
        quant = build_quant_research_v9(
            frame, raw_reliability=reliability_score,
            sample_count=len(frame) if isinstance(frame, pd.DataFrame) else 0,
            model_count=4, forecast_disagreement=disagreement, error_pct=error_pct,
            entry_score=entry, exit_risk=exit_risk, tp_quality=tp, data_quality=raw_quality,
        )
    except Exception as exc:
        quant = {"status": "FAILED SAFELY", "error": str(exc), "protected_logic_changed": False}
    state["quant_research_v9"] = quant
    cp = _num(_mapping(quant.get("bayesian_changepoint")).get("change_point_probability"), _num(_find(canonical, ("change_point_probability",)), 0.0))
    vol_risk = _num(_mapping(quant.get("garch_volatility")).get("volatility_risk_score"), 50.0)
    deflated = _num(_mapping(quant.get("deflated_reliability")).get("deflated_reliability_score"), reliability_score)
    priority_score, reasons = _anti_constant_priority(
        base=base_priority, entry=entry, exit_risk=exit_risk, tp=tp,
        reliability=deflated, data_quality=raw_quality, freshness=freshness,
        volatility=vol_risk, change_probability=cp, forecast_disagreement=disagreement,
    )
    decision = str(_first(final.get("final_decision"), final.get("tradeability_decision"), _find(canonical, ("decision",)), default="WAIT"))
    less_risky = str(_first(final.get("less_risky_decision"), final.get("direction"), _find(canonical, ("less_risky_bias", "direction", "full_metric_direction")), default="WAIT"))
    broker_time = str(_first(clock.get("shared_broker_time_display"), clock.get("broker_time_display"), canonical.get("latest_completed_candle_time"), default="UNAVAILABLE"))
    candle_time = candle_ts.isoformat() if candle_ts is not None else str(canonical.get("latest_completed_candle_time") or "UNAVAILABLE")
    broker_offset = int(round(_num(_first(clock.get("broker_offset_minutes"), state.get("manual_broker_utc_offset_hours_20260622"), default=0.0), 0.0)))
    if abs(broker_offset) <= 24 and clock.get("broker_offset_minutes") is None:
        broker_offset *= 60
    broker_timezone = str(_first(clock.get("broker_timezone_iana"), clock.get("broker_timezone"), default=f"UTC{broker_offset / 60:+g}"))

    forecasts = _json_mapping(_choose(canonical.get("forecasts"), canonical.get("powerbi"), {}))
    regime_map = _mapping(canonical.get("regime"))
    regime_probabilities = _json_mapping(
        regime_map.get("probabilities") or canonical.get("regime_probabilities") or {regime: regime_probability}
    )
    priority_map = {
        **_json_mapping(canonical.get("priority")), **_json_mapping(priority_row),
        "priority_score": priority_score, "priority_label": _label(priority_score), "reasons": reasons,
    }
    reliability_map = {
        **_json_mapping(canonical.get("reliability")),
        "score": float(np.clip(deflated, 0.0, 100.0)), "confidence": float(np.clip(confidence, 0.0, 100.0)),
    }
    data_quality_map = {
        **_json_mapping(canonical.get("data_quality")),
        "score": float(np.clip(raw_quality, 0.0, 100.0)),
        "freshness_minutes": freshness,
    }
    conflicts = _json_mapping(canonical.get("conflicts") or final.get("conflicts") or {
        "status": _first(final.get("conflict_status"), canonical.get("conflict_status"), default="UNAVAILABLE"),
        "warning": _first(final.get("conflict_warning"), canonical.get("conflict_warning"), default=""),
    })
    technical = _json_mapping(_choose(canonical.get("technical_evidence"), canonical.get("technical"), canonical.get("full_metric_snapshot"), {}))
    sentiment = _json_mapping(_choose(canonical.get("sentiment"), canonical.get("nlp"), {}))
    histories = _bounded_histories(canonical, state)
    provenance = {
        "contract_version": VERSION,
        "source": _first(canonical.get("source"), clock.get("source"), default="UNKNOWN"),
        "timestamp_source": clock.get("timestamp_source"),
        "canonical_calculation_id": run_id,
        "calculation_generation": generation_id,
        "snapshot_source": "Settings -> Run Calculation + Open Lunch",
        "full_recalculation_allowed": False,
    }
    payload = {
        "run_id": run_id,
        "generation_id": generation_id,
        "created_at_utc": created.isoformat(),
        "completed_candle_utc": candle_time,
        "broker_candle_time": broker_time,
        "broker_timezone": broker_timezone,
        "broker_offset_minutes": broker_offset,
        "symbol": str(canonical.get("symbol") or state.get("symbol") or "EURUSD").upper(),
        "timeframe": str(canonical.get("timeframe") or state.get("timeframe") or "H1").upper(),
        "decision": decision,
        "less_risky_bias": less_risky,
        "regime": regime,
        "regime_probabilities": regime_probabilities,
        "priority": priority_map,
        "reliability": reliability_map,
        "forecasts": forecasts,
        "prediction_intervals": _prediction_intervals(forecasts),
        "technical_evidence": technical,
        "sentiment": sentiment,
        "conflicts": conflicts,
        "uncertainty": float(np.clip(uncertainty, 0.0, 100.0)),
        "data_quality": data_quality_map,
        "histories": histories,
        "provenance": provenance,
        "broker_time": broker_time,
        "candle_time": candle_time,
        "master_score": master,
        "entry_score": entry,
        "hold_score": hold,
        "tp_score": tp,
        "exit_risk_score": exit_risk,
        "regime_probability": float(np.clip(regime_probability, 0.0, 1.0)),
        "regime_age": regime_age,
        "change_point_probability": float(np.clip(cp, 0.0, 1.0)),
        "priority_score": priority_score,
        "priority_label": _label(priority_score),
        "reliability_score": float(np.clip(deflated, 0.0, 100.0)),
        "data_quality_score": float(np.clip(raw_quality, 0.0, 100.0)),
        "direction": less_risky,
        "confidence": float(np.clip(confidence, 0.0, 100.0)),
        "error_pct": max(error_pct, 0.0),
        "source_freshness_minutes": freshness,
    }
    payload["snapshot_hash"] = _hash_payload(payload)
    snapshot = CanonicalRunSnapshot(**payload)
    report = validate_snapshot(snapshot)
    if not report["ok"]:
        raise ValueError("Invalid V10 snapshot: " + "; ".join(report["errors"]))
    state[STATE_KEY] = asdict(snapshot)
    state[RUN_ID_KEY] = snapshot.run_id
    state[HASH_KEY] = snapshot.snapshot_hash
    state["canonical_sync_validation_v9"] = report
    state["canonical_run_contract_v10"] = asdict(snapshot)
    _persist(snapshot, reasons, state)

    history_sources = {
        "FIELD_1": [state.get("full_metric_history_df_20260618"), _mapping(state.get("lunch_metric_result_cache")).get("history")],
        "FIELD_3": [state.get("regime_history_table_Lunch"), state.get("canonical_priority_table_20260617")],
        "FIELD_4": [state.get("field4_technical_fact_table_20260622"), state.get("reliability_history_20260618")],
        "FIELD_6": [state.get("field6_combined_history_20260622")],
    }
    history_report: dict[str, Any] = {}
    for field_name, candidates in history_sources.items():
        for index, candidate in enumerate(candidates, start=1):
            if isinstance(candidate, pd.DataFrame) and not candidate.empty:
                try:
                    history_report[f"{field_name}_{index}"] = upsert_history_rows(candidate, field_name=field_name, metric_name="row", state=state)
                except Exception as exc:
                    history_report[f"{field_name}_{index}"] = {"ok": False, "error": str(exc)}
    state["canonical_history_quality_report_v9"] = history_report
    return snapshot


def _upgrade_snapshot_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    """Upgrade persisted V9 JSON to the single V10 contract without recalculation."""
    old = dict(value or {})
    run_id = str(old.get("run_id") or "")
    candle = str(old.get("completed_candle_utc") or old.get("candle_time") or "UNAVAILABLE")
    broker = str(old.get("broker_candle_time") or old.get("broker_time") or "UNAVAILABLE")
    regime = str(old.get("regime") or "UNKNOWN")
    priority_score = _num(old.get("priority_score"), 50.0)
    reliability_score = _num(old.get("reliability_score"), 50.0)
    dq_score = _num(old.get("data_quality_score"), 50.0)
    payload = {
        "run_id": run_id,
        "generation_id": str(old.get("generation_id") or old.get("generation") or "0"),
        "created_at_utc": str(old.get("created_at_utc") or datetime.now(timezone.utc).isoformat()),
        "completed_candle_utc": candle,
        "broker_candle_time": broker,
        "broker_timezone": str(old.get("broker_timezone") or "UNAVAILABLE"),
        "broker_offset_minutes": int(_num(old.get("broker_offset_minutes"), 0.0)),
        "symbol": str(old.get("symbol") or "EURUSD"),
        "timeframe": str(old.get("timeframe") or "H1"),
        "decision": str(old.get("decision") or "WAIT"),
        "less_risky_bias": str(old.get("less_risky_bias") or old.get("direction") or "WAIT"),
        "regime": regime,
        "regime_probabilities": _json_mapping(old.get("regime_probabilities") or {regime: old.get("regime_probability", 0.0)}),
        "priority": _json_mapping(old.get("priority") or {"priority_score": priority_score, "priority_label": old.get("priority_label")}),
        "reliability": _json_mapping(old.get("reliability") or {"score": reliability_score}),
        "forecasts": _json_mapping(old.get("forecasts")),
        "prediction_intervals": _json_mapping(old.get("prediction_intervals")),
        "technical_evidence": _json_mapping(old.get("technical_evidence")),
        "sentiment": _json_mapping(old.get("sentiment")),
        "conflicts": _json_mapping(old.get("conflicts")),
        "uncertainty": _num(old.get("uncertainty"), 100.0 - _num(old.get("confidence"), 50.0)),
        "data_quality": _json_mapping(old.get("data_quality") or {"score": dq_score}),
        "histories": _json_mapping(old.get("histories")),
        "provenance": _json_mapping(old.get("provenance") or {"contract_version": "migrated-v9", "full_recalculation_allowed": False}),
        "broker_time": broker,
        "candle_time": candle,
        "master_score": _num(old.get("master_score"), 5.0),
        "entry_score": _num(old.get("entry_score"), 5.0),
        "hold_score": _num(old.get("hold_score"), 5.0),
        "tp_score": _num(old.get("tp_score"), 5.0),
        "exit_risk_score": _num(old.get("exit_risk_score"), 5.0),
        "regime_probability": _num(old.get("regime_probability"), 0.0),
        "regime_age": _num(old.get("regime_age"), 0.0),
        "change_point_probability": _num(old.get("change_point_probability"), 0.0),
        "priority_score": priority_score,
        "priority_label": str(old.get("priority_label") or _label(priority_score)),
        "reliability_score": reliability_score,
        "data_quality_score": dq_score,
        "direction": str(old.get("direction") or old.get("less_risky_bias") or "WAIT"),
        "confidence": _num(old.get("confidence"), reliability_score),
        "error_pct": _num(old.get("error_pct"), 0.0),
        "source_freshness_minutes": _num(old.get("source_freshness_minutes"), 0.0),
    }
    payload["snapshot_hash"] = _hash_payload(payload)
    return payload


def _from_mapping(value: Mapping[str, Any]) -> CanonicalRunSnapshot | None:
    try:
        payload = _upgrade_snapshot_payload(value)
        snapshot = CanonicalRunSnapshot(**{f.name: payload.get(f.name) for f in fields(CanonicalRunSnapshot)})
        return snapshot if validate_snapshot(snapshot)["ok"] else None
    except Exception:
        return None


def get_latest_snapshot(force: bool = False, state: MutableMapping[str, Any] | None = None) -> CanonicalRunSnapshot | None:
    state = _state(state)
    cached = state.get(STATE_KEY) or state.get("canonical_run_contract_v10")
    if not force and isinstance(cached, Mapping):
        snapshot = _from_mapping(cached)
        if snapshot is not None:
            return snapshot
    if DB_PATH.exists():
        try:
            with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
                _ensure_schema(conn)
                row = conn.execute("SELECT snapshot_json FROM canonical_run_snapshots ORDER BY created_at_utc DESC LIMIT 1").fetchone()
            if row:
                snapshot = _from_mapping(json.loads(row[0]))
                if snapshot is not None:
                    state[STATE_KEY] = asdict(snapshot)
                    state["canonical_run_contract_v10"] = asdict(snapshot)
                    state[RUN_ID_KEY] = snapshot.run_id
                    state[HASH_KEY] = snapshot.snapshot_hash
                    return snapshot
        except Exception:
            pass
    if force and _canonical(state):
        try:
            return write_snapshot_from_settings_run(state.get("settings_run_status_20260617"), state=state)
        except Exception:
            return None
    return None


def read_snapshot_for_lunch(state: MutableMapping[str, Any] | None = None) -> CanonicalRunSnapshot | None:
    """Read the Lunch snapshot, repairing a successful Settings run if needed.

    V11 Lunch is read-only and must not run heavy calculations.  However, the
    Settings transaction can finish the protected calculation while failing the
    final V9/V10 publication step, leaving Lunch with the message "No canonical
    snapshot is available" even after the user pressed Run Calculation + Open
    Lunch.  This repair path only publishes the already completed canonical
    result from session state/disk; it never refreshes market data or recalculates
    strategies/predictions.
    """
    state = _state(state)
    snapshot = get_latest_snapshot(False, state)
    if snapshot is None:
        try:
            status = state.get("settings_run_status_20260617")
            if _canonical(state):
                snapshot = write_snapshot_from_settings_run(status if isinstance(status, Mapping) else {}, state=state)
                state["lunch_snapshot_repaired_from_settings_run_v11"] = True
        except Exception as exc:
            state["lunch_snapshot_repair_error_v11"] = str(exc)
            snapshot = None
    if snapshot is None:
        return None
    expected_run = str(state.get(RUN_ID_KEY) or snapshot.run_id)
    expected_hash = str(state.get(HASH_KEY) or snapshot.snapshot_hash)
    state["lunch_canonical_sync_ok_v9"] = snapshot.run_id == expected_run and snapshot.snapshot_hash == expected_hash
    return snapshot


def snapshot_identity(state: MutableMapping[str, Any] | None = None) -> dict[str, Any]:
    snapshot = read_snapshot_for_lunch(state)
    if snapshot is None:
        return {"ok": False, "status": "NOT AVAILABLE", "version": VERSION}
    report = validate_snapshot(snapshot)
    return {"ok": report["ok"], "status": "SYNC OK" if report["ok"] else "NOT OK", **asdict(snapshot), "version": VERSION}


def load_priority_history(limit: int = 500) -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            _ensure_schema(conn)
            return pd.read_sql_query("SELECT * FROM priority_history ORDER BY broker_time DESC LIMIT ?", conn, params=(int(limit),))
    except Exception:
        return pd.DataFrame()


def _normalized_column_map(frame: pd.DataFrame) -> dict[str, Any]:
    return {re.sub(r"[^a-z0-9]+", " ", str(c).strip().lower()).strip(): c for c in frame.columns}


def _parse_history_utc(out: pd.DataFrame, snapshot: CanonicalRunSnapshot) -> pd.Series:
    columns = _normalized_column_map(out)
    for name in ("event time utc", "completed candle utc", "candle time", "timestamp", "datetime", "date time", "time"):
        col = columns.get(name)
        if col is not None:
            parsed = pd.to_datetime(out[col], errors="coerce", utc=True)
            if parsed.notna().any():
                return parsed

    # A broker display column is local broker wall time; convert it back to UTC.
    broker_col = next((c for c in out.columns if str(c).strip().lower().startswith("broker time")), None)
    if broker_col is not None:
        text = out[broker_col].astype(str).str.extract(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)", expand=False)
        local = pd.to_datetime(text, errors="coerce")
        if local.notna().any():
            return local.dt.tz_localize("UTC") - pd.to_timedelta(snapshot.broker_offset_minutes, unit="m")

    # Legacy tables sometimes store separate Date and Hour strings. The old Hour
    # is never trusted on its own; it is used only to recover the row timestamp,
    # after which Date/Weekday/Hour are rebuilt from the canonical broker clock.
    date_col, hour_col = columns.get("date"), columns.get("hour")
    if date_col is not None and hour_col is not None:
        combined = out[date_col].astype(str).str.split().str[0] + " " + out[hour_col].astype(str)
        local = pd.to_datetime(combined, errors="coerce")
        if local.notna().any():
            return local.dt.tz_localize("UTC") - pd.to_timedelta(snapshot.broker_offset_minutes, unit="m")

    if len(out) == 1:
        return pd.Series([pd.to_datetime(snapshot.completed_candle_utc, errors="coerce", utc=True)], index=out.index)
    return pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")


def _broker_local_series(utc_series: pd.Series, snapshot: CanonicalRunSnapshot) -> pd.Series:
    try:
        if snapshot.broker_timezone and snapshot.broker_timezone not in {"UNAVAILABLE", "UTC"} and "/" in snapshot.broker_timezone:
            return utc_series.dt.tz_convert(ZoneInfo(snapshot.broker_timezone))
    except Exception:
        pass
    return utc_series + pd.to_timedelta(snapshot.broker_offset_minutes, unit="m")


def normalize_history_frame(frame: Any, *, field_name: str, metric_name: str = "row",
                            state: MutableMapping[str, Any] | None = None) -> pd.DataFrame:
    """Normalize every row before display/persistence using the one broker clock.

    This deliberately ignores any previously stored visible Hour value, rebuilds
    Date/Weekday/Hour from the canonical completed-candle clock, preserves all
    distinct history rows, rejects future rows and sorts current-first.
    """
    state = _state(state)
    snapshot = read_snapshot_for_lunch(state)
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    out = frame.copy()
    if out.empty or snapshot is None:
        return out

    parsed = _parse_history_utc(out, snapshot)
    cutoff = pd.to_datetime(snapshot.completed_candle_utc, errors="coerce", utc=True)
    valid = parsed.notna()
    if pd.notna(cutoff):
        valid &= parsed.le(cutoff)
    out = out.loc[valid].copy()
    parsed = parsed.loc[valid]
    if out.empty:
        return out.reset_index(drop=True)

    out["candle_time"] = parsed.map(lambda value: pd.Timestamp(value).isoformat())
    broker = _broker_local_series(parsed, snapshot)
    out["broker_time"] = broker.dt.strftime("%Y-%m-%d %H:%M:%S")
    out["Date"] = broker.dt.strftime("%Y-%m-%d")
    out["Weekday"] = broker.dt.strftime("%A")
    out["Hour"] = broker.dt.strftime("%H:00")
    out["run_id"] = snapshot.run_id
    out["generation_id"] = snapshot.generation_id
    out["snapshot_hash"] = snapshot.snapshot_hash
    out["data_quality_score"] = snapshot.data_quality_score
    out["source_freshness_minutes"] = snapshot.source_freshness_minutes
    out["symbol"] = snapshot.symbol
    out["timeframe"] = snapshot.timeframe
    out["field_name"] = field_name
    out["metric_name"] = metric_name

    # Deduplicate per table exactly by canonical symbol/timeframe/candle/run.
    dedup_columns = ["symbol", "timeframe", "candle_time", "run_id"]
    out = out.drop_duplicates(subset=dedup_columns, keep="last")
    out["unique_key"] = (
        out["symbol"].astype(str) + "|" + out["timeframe"].astype(str) + "|" +
        out["candle_time"].astype(str) + "|" + out["run_id"].astype(str) + "|" +
        out["field_name"].astype(str) + "|" + out["metric_name"].astype(str)
    ).map(lambda x: sha256(x.encode()).hexdigest()[:24])
    out["__sort"] = pd.to_datetime(out["candle_time"], errors="coerce", utc=True)
    out = out.sort_values("__sort", ascending=False, na_position="last", kind="mergesort").drop(columns="__sort")
    return out.reset_index(drop=True)


def upsert_history_rows(frame: Any, *, field_name: str, metric_name: str = "row",
                        state: MutableMapping[str, Any] | None = None) -> dict[str, Any]:
    state = _state(state)
    out = normalize_history_frame(frame, field_name=field_name, metric_name=metric_name, state=state)
    if out.empty:
        return {"ok": True, "rows": 0}
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH), timeout=20) as conn:
        _ensure_schema(conn)
        for row in out.to_dict("records"):
            conn.execute(
                "INSERT OR REPLACE INTO lunch_history_quality(unique_key,symbol,timeframe,candle_time,broker_time,field_name,metric_name,metric_value,data_quality_score,source_freshness_minutes,run_id,snapshot_hash,payload_json,updated_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (row.get("unique_key"), row.get("symbol"), row.get("timeframe"), row.get("candle_time"), row.get("broker_time"), field_name, metric_name, str(row.get(metric_name, "")), row.get("data_quality_score"), row.get("source_freshness_minutes"), row.get("run_id"), row.get("snapshot_hash"), json.dumps(row, default=_json_default, sort_keys=True), datetime.now(timezone.utc).isoformat()),
            )
        conn.commit()
    return {"ok": True, "rows": len(out), "unique_guard": "symbol+timeframe+candle_time+run_id (per field/metric table)"}


__all__ = [
    "VERSION", "CanonicalRunSnapshot", "validate_snapshot", "get_latest_snapshot",
    "write_snapshot_from_settings_run", "read_snapshot_for_lunch", "snapshot_identity",
    "load_priority_history", "normalize_history_frame", "upsert_history_rows", "DB_PATH",
]
