"""Immutable V11 Lunch snapshot adapted from the protected V10 publication.

This module never starts a calculation. It converts the already-published V10
snapshot into the compact contract consumed by every modular Lunch field.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping

from core.canonical.schema import SCHEMA_VERSION


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        output = float(value)
        return output if output == output else default
    except Exception:
        return default


def _datetime(value: Any, *, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return fallback or datetime.fromtimestamp(0, tz=timezone.utc)
    return fallback or datetime.fromtimestamp(0, tz=timezone.utc)


def _deep_find(mapping: Mapping[str, Any], aliases: tuple[str, ...]) -> Any:
    normalized = {str(k).lower().replace(" ", "_").replace("/", "_"): v for k, v in mapping.items()}
    for alias in aliases:
        key = alias.lower().replace(" ", "_").replace("/", "_")
        if key in normalized and normalized[key] not in (None, ""):
            return normalized[key]
    for value in mapping.values():
        if isinstance(value, Mapping):
            found = _deep_find(value, aliases)
            if found not in (None, ""):
                return found
    return None


@dataclass(frozen=True)
class CanonicalRunSnapshot:
    schema_version: str
    run_id: str
    created_at_utc: datetime
    broker_candle_time: datetime
    symbol: str
    timeframe: str
    current_price: float
    decision: str
    entry_decision: str
    less_risky_decision: str
    regime: str
    regime_age: float
    regime_reliability: float
    priority: float
    reliability: float
    uncertainty: float
    error_rate: float
    predictions: Mapping[str, Any] = field(default_factory=dict)
    metrics: Mapping[str, Any] = field(default_factory=dict)
    histories: Mapping[str, Any] = field(default_factory=dict)
    research_summary: Mapping[str, Any] = field(default_factory=dict)
    generation_id: str = ""
    broker_timezone: str = "UNAVAILABLE"
    source_snapshot_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def adapt_v10_snapshot(source: Any, *, research_summary: Mapping[str, Any] | None = None) -> CanonicalRunSnapshot:
    """Create the exact V11 field contract from one protected V10 snapshot."""
    if hasattr(source, "to_dict"):
        raw = source.to_dict()
    elif hasattr(source, "__dataclass_fields__"):
        raw = asdict(source)
    elif isinstance(source, Mapping):
        raw = dict(source)
    elif hasattr(source, "__dict__"):
        raw = dict(vars(source))
    else:
        raw = {}
    forecasts = _mapping(raw.get("forecasts"))
    technical = _mapping(raw.get("technical_evidence"))
    metrics = {
        **technical,
        "master_score": _number(raw.get("master_score"), 5.0),
        "entry_score": _number(raw.get("entry_score"), 5.0),
        "hold_score": _number(raw.get("hold_score"), 5.0),
        "tp_score": _number(raw.get("tp_score"), 5.0),
        "exit_risk_score": _number(raw.get("exit_risk_score"), 5.0),
        "data_quality_score": _number(raw.get("data_quality_score"), 0.0),
        "confidence": _number(raw.get("confidence"), 0.0),
        "prediction_intervals": _mapping(raw.get("prediction_intervals")),
        "sentiment": _mapping(raw.get("sentiment")),
        "conflicts": _mapping(raw.get("conflicts")),
    }
    current_price = _number(
        _deep_find(
            {"forecasts": forecasts, "technical": technical, "raw": raw},
            ("current_price", "last_close", "close", "anchor_price", "spot_price"),
        ),
        0.0,
    )
    reliability_map = _mapping(raw.get("reliability"))
    regime_reliability = _number(
        _deep_find(reliability_map, ("regime_reliability", "regime_score", "score")),
        _number(raw.get("regime_probability"), 0.0) * 100.0,
    )
    if 0.0 <= regime_reliability <= 1.0:
        regime_reliability *= 100.0
    decision = str(raw.get("decision") or "WAIT").upper()
    return CanonicalRunSnapshot(
        schema_version=SCHEMA_VERSION,
        run_id=str(raw.get("run_id") or ""),
        created_at_utc=_datetime(raw.get("created_at_utc")),
        broker_candle_time=_datetime(
            raw.get("broker_candle_time") or raw.get("broker_time"),
            fallback=_datetime(raw.get("completed_candle_utc") or raw.get("candle_time") or raw.get("latest_completed_candle_time")),
        ),
        symbol=str(raw.get("symbol") or "EURUSD").upper(),
        timeframe=str(raw.get("timeframe") or "H1").upper(),
        current_price=current_price,
        decision=decision,
        entry_decision=str(raw.get("entry_decision") or decision).upper(),
        less_risky_decision=str(raw.get("less_risky_bias") or raw.get("direction") or "WAIT").upper(),
        regime=str(raw.get("regime") or "UNKNOWN"),
        regime_age=_number(raw.get("regime_age"), 0.0),
        regime_reliability=max(0.0, min(100.0, regime_reliability)),
        priority=max(0.0, min(100.0, _number(raw.get("priority_score"), 0.0))),
        reliability=max(0.0, min(100.0, _number(raw.get("reliability_score"), 0.0))),
        uncertainty=max(0.0, min(100.0, _number(raw.get("uncertainty"), 100.0))),
        error_rate=max(0.0, _number(raw.get("error_pct"), 0.0)),
        predictions=forecasts,
        metrics=metrics,
        histories=_mapping(raw.get("histories")),
        research_summary=_mapping(research_summary),
        generation_id=str(raw.get("generation_id") or ""),
        broker_timezone=str(raw.get("broker_timezone") or "UNAVAILABLE"),
        source_snapshot_hash=str(raw.get("snapshot_hash") or ""),
    )


def load_canonical_snapshot(state: MutableMapping[str, Any] | None = None) -> CanonicalRunSnapshot | None:
    """Read the latest valid snapshot and attach stored shadow research only."""
    try:
        import streamlit as st
        runtime_state = state if state is not None else st.session_state
    except Exception:
        runtime_state = state if state is not None else {}
    from core.canonical_sync_v9 import read_snapshot_for_lunch

    source = read_snapshot_for_lunch(runtime_state)
    if source is None:
        return None
    research = runtime_state.get("field_07_research_summary_v11")
    if not isinstance(research, Mapping) or str(research.get("run_id") or "") != str(source.run_id):
        try:
            from core.repositories.research_repository import ResearchRepository
            research = ResearchRepository().latest_summary(run_id=str(source.run_id)) or {}
        except Exception:
            research = {}
    return adapt_v10_snapshot(source, research_summary=research)
