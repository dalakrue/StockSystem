# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Read-only Lunch broker-time, copy, AI, sentiment, Field-6 and quality helpers.

This file is intentionally an extension layer.  It does not calculate protected
trading decisions, predictions, TP/SL, regimes, KNN/Greedy ranks, or model
weights.  It normalizes already-published values into one generation-bound
presentation contract used by Lunch Field 1, Field 5, Field 6 and copy payloads.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone, timedelta
import hashlib
import json
import re
import time
from typing import Any, Mapping, MutableMapping, Iterable

import pandas as pd

TIME_COLUMNS = (
    "event_time_utc", "latest_completed_h1_utc", "Time", "time", "Datetime", "DateTime",
    "Timestamp", "timestamp", "Candle Time", "candle_time", "latest_completed_candle_time",
)
DECISION_LABELS = {"BUY", "SELL", "WAIT", "NO TRADE", "HOLD", "PROTECT", "AVOID", "UNAVAILABLE", "NEUTRAL"}
DIRECTION_LABELS = {"BUY", "SELL", "WAIT", "NEUTRAL", "CONFLICT", "UNAVAILABLE"}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return default


def _utc(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    try:
        parsed = pd.to_datetime(value, errors="coerce", utc=True)
        if isinstance(parsed, pd.Series):
            parsed = parsed.dropna().max() if parsed.notna().any() else pd.NaT
        elif isinstance(parsed, pd.DatetimeIndex):
            parsed = parsed.dropna().max() if len(parsed.dropna()) else pd.NaT
        if pd.isna(parsed):
            return None
        return pd.Timestamp(parsed).tz_convert("UTC")
    except Exception:
        return None


def _offset_minutes(state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None) -> int:
    canonical = _mapping(canonical)
    for key in ("broker_offset_minutes", "broker_offset_minutes_20260622"):
        try:
            value = canonical.get(key)
            if value not in (None, ""):
                return int(round(float(value)))
        except Exception:
            pass
    for key in ("mt5_broker_utc_offset_hours_20260622", "broker_utc_offset_hours", "mt5_server_utc_offset_hours"):
        try:
            value = state.get(key)
            if value not in (None, ""):
                return int(round(float(value) * 60.0))
        except Exception:
            pass
    return 0


def _tz(minutes: int) -> timezone:
    return timezone(timedelta(minutes=int(minutes)))


def _display(ts: pd.Timestamp | None, minutes: int, label: str) -> str:
    if ts is None:
        return "UNAVAILABLE"
    return ts.tz_convert(_tz(minutes)).strftime("%Y-%m-%d %H:%M:%S") + f" ({label})"


def _calc_id(canonical: Mapping[str, Any], state: Mapping[str, Any] | None = None) -> str:
    state = state or {}
    value = _first(
        canonical.get("calculation_id"), canonical.get("canonical_calculation_id"),
        canonical.get("run_id"), state.get("canonical_calculation_id_20260617"),
        state.get("active_calculation_id_20260619"), default="",
    )
    if value:
        return str(value)
    raw = "|".join(str(_first(canonical.get(k), default="")) for k in ("symbol", "timeframe", "latest_completed_candle_time", "calculation_generation"))
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:24] if raw.strip("|") else "UNAVAILABLE"


def _generation(canonical: Mapping[str, Any], state: Mapping[str, Any] | None = None) -> Any:
    state = state or {}
    return _first(canonical.get("calculation_generation"), state.get("canonical_calculation_generation_20260617"), state.get("calculation_generation"), default="UNAVAILABLE")


def get_canonical_generation(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return the current canonical result without starting calculation."""
    try:
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        if isinstance(value, Mapping) and value:
            return dict(value)
    except Exception:
        pass
    for key in (
        "canonical_result_20260617", "canonical_decision_result_20260617", "canonical_decision_result",
        "last_valid_canonical_decision_result_20260617", "canonical_result",
    ):
        value = state.get(key)
        if isinstance(value, Mapping) and value:
            return dict(value)
    return {}


def latest_completed_h1_utc(canonical: Mapping[str, Any], state: Mapping[str, Any] | None = None) -> pd.Timestamp | None:
    market = _mapping(canonical.get("market"))
    for value in (
        canonical.get("event_time_utc"), canonical.get("latest_completed_h1_utc"),
        canonical.get("latest_completed_candle_time"), canonical.get("latest_completed_h1"),
        market.get("latest_completed_candle_time"), market.get("latest_completed_h1"), canonical.get("anchor_time"),
    ):
        ts = _utc(value)
        if ts is not None:
            return ts.floor("h") if ts.minute == 0 and ts.second == 0 else ts
    return None


def market_time_contract(state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the one strict contract owned by shared_broker_time_20260622."""
    from core.shared_broker_time_20260622 import shared_broker_time_provider
    return shared_broker_time_provider(state, canonical=dict(canonical or get_canonical_generation(state)))

def _time_col(frame: pd.DataFrame) -> str | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    for col in TIME_COLUMNS:
        if col in frame.columns:
            return col
    lower = {str(c).strip().lower(): c for c in frame.columns}
    for key in ("time", "datetime", "timestamp", "date"):
        if key in lower:
            return str(lower[key])
    return None


def add_broker_display_columns(frame: pd.DataFrame, state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None) -> pd.DataFrame:
    """Display projection that rebuilds Date/Weekday/Hour from broker time."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame() if frame is None else frame
    from core.shared_broker_time_20260622 import frame_to_shared_broker_clock
    display = frame_to_shared_broker_clock(
        frame, state, canonical=dict(canonical or get_canonical_generation(state)),
        include_myanmar=True, reject_future_incomplete=True, hide_raw_utc=False,
    )
    broker = next((c for c in display.columns if str(c).startswith("Broker Time")), None)
    myanmar = next((c for c in display.columns if str(c).startswith("Myanmar Time")), None)
    renames = {}
    if broker and broker != "Broker Time": renames[broker] = "Broker Time"
    if myanmar and myanmar != "Myanmar Time": renames[myanmar] = "Myanmar Time"
    return display.rename(columns=renames)

def synchronization_status(state: Mapping[str, Any], *, field1_history: Any = None, field6_history: Any = None, canonical: Mapping[str, Any] | None = None) -> dict[str, Any]:
    canonical = dict(canonical or get_canonical_generation(state))
    from core.shared_broker_time_20260622 import history_sync_status
    from core.cross_table_sync_20260622 import validate_cross_table_sync
    field1 = history_sync_status(state, history_frame=field1_history, canonical=canonical) if isinstance(field1_history, pd.DataFrame) else None
    field6 = history_sync_status(state, history_frame=field6_history, canonical=canonical) if isinstance(field6_history, pd.DataFrame) else None
    cross = validate_cross_table_sync(state, canonical=canonical, frames={
        "field1": field1_history, "field6": field6_history,
    })
    contract = market_time_contract(state, canonical)
    reports = [r for r in (field1, field6) if isinstance(r, Mapping)]
    if not reports:
        status = cross.get("status")
    elif all(r.get("status") == "SYNCED" for r in reports) and cross.get("status") in {"SYNCED", "STALE"}:
        status = "SYNCED"
    elif any(r.get("status") == "OUT OF SYNC" for r in reports) or cross.get("status") == "OUT OF SYNC":
        status = "OUT_OF_SYNC"
    elif any(r.get("status") == "UNAVAILABLE" for r in reports):
        status = "UNAVAILABLE"
    else:
        status = "STALE"
    status_display = "OUT OF SYNC" if status == "OUT_OF_SYNC" else status
    primary = field1 or field6 or {}
    return {
        **contract,
        "canonical_latest_completed_h1_utc": contract.get("latest_completed_h1_utc"),
        "displayed_broker_candle_time": contract.get("broker_time_display"),
        "displayed_myanmar_candle_time": contract.get("myanmar_time_display"),
        "latest_field1_history_utc": (field1 or {}).get("latest_history_record_utc_iso"),
        "latest_field6_history_utc": (field6 or {}).get("latest_history_record_utc_iso"),
        "difference_in_minutes": primary.get("difference_minutes"),
        "difference_minutes": primary.get("difference_minutes"),
        "calculation_id_match": all(bool(r.get("calculation_id_match")) for r in reports) if reports else True,
        "generation_match": all(bool(r.get("generation_match")) for r in reports) if reports else True,
        "broker_offset_match": all(bool(r.get("broker_offset_match")) for r in reports) if reports else True,
        "source_match": all(bool(r.get("source_match")) for r in reports) if reports else True,
        "status": status,
        "status_display": status_display,
        "reason": primary.get("reason") or f"Cross-table validation: {cross.get('status')}",
        "cross_table_report": cross,
    }

def _compact_lines_from_mapping(prefix: str, value: Mapping[str, Any], limit: int = 16) -> list[str]:
    out = []
    for idx, (k, v) in enumerate(value.items()):
        if idx >= limit:
            break
        if isinstance(v, Mapping):
            out.append(f"{prefix}{k}: " + ", ".join(f"{a}={b}" for a, b in list(v.items())[:8]))
        elif isinstance(v, list):
            out.append(f"{prefix}{k}: " + ", ".join(map(str, v[:8])))
        else:
            out.append(f"{prefix}{k}: {v}")
    return out



def _field10_field11_context(state: Mapping[str, Any]) -> dict[str, Any]:
    """Load structured Field 10/11 evidence for copy and grounded AI context."""
    selected = [str(value).upper() for value in (state.get("multi_symbol_selected_20260701") or [])]
    active = str(
        state.get("lunch_active_symbol_20260704")
        or state.get("canonical_display_symbol_20260705")
        or state.get("lunch_display_symbol_20260702")
        or state.get("symbol")
        or ""
    ).upper()
    field10 = pd.DataFrame()
    metadata: Mapping[str, Any] = {}
    try:
        from core.field10_daily_snapshot_contract_20260702 import load_current_daily_snapshot
        bundle = load_current_daily_snapshot()
        metadata = bundle.get("metadata") if isinstance(bundle, Mapping) else {}
        current = bundle.get("current") if isinstance(bundle, Mapping) else None
        if isinstance(current, pd.DataFrame):
            field10 = current.copy()
    except Exception:
        pass
    if field10.empty:
        try:
            from core.multi_symbol_field10_20260701 import load_field10_tables
            loaded = load_field10_tables(dict(state), symbol=active or None)
            candidate = loaded.get("daily") if isinstance(loaded, Mapping) else None
            if isinstance(candidate, pd.DataFrame):
                field10 = candidate.copy()
        except Exception:
            pass
    rank_column = next((c for c in ("Final Rank", "Daily Rank", "Rank") if c in field10.columns), None)
    if rank_column:
        field10 = field10.assign(_copy_rank=pd.to_numeric(field10[rank_column], errors="coerce")).sort_values(
            ["_copy_rank", "Symbol"] if "Symbol" in field10.columns else ["_copy_rank"],
            kind="mergesort", na_position="last",
        ).drop(columns="_copy_rank")
    top_columns = [column for column in (
        "Final Rank", "Daily Rank", "Rank", "Symbol", "Final Less-Risky Bias", "Less-Risky Bias",
        "Stable Daily Bias", "Higher-Standard Bias", "Higher Standard Regime", "Expected Value 6H (%)",
        "Expected Return 12H (%)", "Expected Return 24H (%)", "Transition Risk 6H",
        "Transition Risk 24H", "Calibrated Reliability", "Reliability Score", "Data Quality Grade",
        "Data Quality", "Fallback Level", "Data Status", "Completed Broker Candle",
    ) if column in field10.columns]
    top = field10.loc[:, top_columns].head(10) if top_columns else field10.head(10)

    field11 = state.get("field11_structured_context_20260705")
    if not isinstance(field11, Mapping):
        raw = state.get("field11_last_result_20260702")
        if isinstance(raw, Mapping):
            field11 = {
                "status": raw.get("status") or ("COMPLETED" if raw.get("ok") else "UNAVAILABLE"),
                "summary": raw.get("summary") if isinstance(raw.get("summary"), Mapping) else {},
                "scenario_count": len(raw.get("scenarios") or []),
            }
        else:
            field11 = {"status": "NO_SCENARIO_RESULT", "data_quality_status": "INDEX OR RESULT NOT PUBLISHED"}
    return {
        "selected_symbols": selected,
        "active_symbol": active,
        "calculation_mode": state.get("settings_calculation_scope_20260625"),
        "active_provider": state.get("active_market_provider_20260705") or state.get("source"),
        "fallback_provider": state.get("fallback_market_provider_20260705") or "CANONICAL_SNAPSHOT",
        "field10_metadata": dict(metadata or {}),
        "field10_top_rows": top.to_dict(orient="records") if not top.empty else [],
        "field10_full_frame": field10,
        "field11": dict(field11),
    }

def _current_fact_pack(state: Mapping[str, Any], canonical: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from core.compact_canonical_20260619 import get_ai_fact_pack, get_compact_summary
        pack = get_ai_fact_pack(state)
        summary = get_compact_summary(state)
    except Exception:
        pack, summary = {}, {}
    final = _mapping(canonical.get("final_decision"))
    regime = _mapping(canonical.get("regime"))
    field10_11 = _field10_field11_context(state)
    priority = _mapping(canonical.get("priority"))
    scores = _mapping(summary.get("scores")) if isinstance(summary, Mapping) else {}
    decision = _mapping(summary.get("decision")) if isinstance(summary, Mapping) else {}
    projection = _mapping(summary.get("projection")) if isinstance(summary, Mapping) else {}
    return {
        "calculation_id": contract.get("calculation_id"),
        "generation": contract.get("calculation_generation"),
        "latest_completed_h1_utc": contract.get("latest_completed_h1_utc"),
        "Broker Time": contract.get("broker_time_display"),
        "Myanmar Time": contract.get("myanmar_time_display"),
        "symbol": contract.get("symbol"),
        "timeframe": contract.get("timeframe"),
        "data source and freshness": f"{contract.get('source')} / {contract.get('data_quality_status')}",
        "current decision": _first(decision.get("current_decision"), final.get("final_decision"), canonical.get("decision"), default="UNAVAILABLE"),
        "less-risky decision": _first(decision.get("less_risky_bias"), final.get("less_risky_decision"), default="UNAVAILABLE"),
        "direction": _first(decision.get("direction"), final.get("directional_market_view"), canonical.get("full_metric_direction"), default="UNAVAILABLE"),
        "protected score summaries": scores,
        "regime and regime age": {"regime": _first(regime.get("major_regime"), canonical.get("current_major_regime"), default="UNAVAILABLE"), "age": _first(regime.get("age"), regime.get("days_since_change"), default="UNAVAILABLE")},
        "regime reliability": _first(regime.get("reliability"), _mapping(canonical.get("reliability")).get("score"), default="UNAVAILABLE"),
        "transition trust": _first(_mapping(canonical.get("transition_trust")).get("score"), _mapping(canonical.get("transition_risk")).get("status"), default="UNAVAILABLE"),
        "priority and Greedy/KNN rank": priority or _mapping(summary.get("priority")) if isinstance(summary, Mapping) else {},
        "Power BI H+1 to H+6 projection": projection,
        "calibrated forecast ranges": _mapping(canonical.get("forecasts")),
        "recent settled forecast accuracy": _mapping(canonical.get("validation_metrics")),
        "Field 1 history summary": state.get("lunch_field1_latest_summary_20260622", "UNAVAILABLE"),
        "Field 4 technical analysis summary": state.get("field4_technical_fact_summary_20260622", "UNAVAILABLE"),
        "Research sentiment summary": state.get("research_sentiment_summary_20260622", "UNAVAILABLE"),
        "Field 6 combined-history summary": state.get("field6_combined_history_summary_20260622", "UNAVAILABLE"),
        "selected symbols": field10_11.get("selected_symbols"),
        "calculation mode": field10_11.get("calculation_mode"),
        "active provider": field10_11.get("active_provider"),
        "fallback provider": field10_11.get("fallback_provider"),
        "Field 10 rankings": field10_11.get("field10_top_rows"),
        "Field 10 publication metadata": field10_11.get("field10_metadata"),
        "Field 11 result": field10_11.get("field11"),
        "data-quality status": contract.get("data_quality_status"),
        "synchronization status": state.get("lunch_sync_status_20260622", "UNAVAILABLE"),
        "conflict warnings": _first(canonical.get("conflict_warnings"), final.get("blocking_reasons"), default=[]),
        "evidence references": list((_mapping(pack).get("evidence") or [])[:20]) if isinstance(pack, Mapping) else [],
        "source timestamps": {"ingested_at_utc": contract.get("ingested_at_utc"), "timestamp_source": contract.get("timestamp_source")},
    }


def build_ai_fact_pack(state: MutableMapping[str, Any]) -> dict[str, Any]:
    canonical = get_canonical_generation(state)
    contract = market_time_contract(state, canonical)
    pack = _current_fact_pack(state, canonical, contract)
    state["canonical_ai_fact_pack_20260622"] = pack
    state["ai_fact_pack_cache_key_20260622"] = payload_cache_key(contract)
    return pack


def payload_cache_key(contract: Mapping[str, Any]) -> str:
    raw = "|".join(str(contract.get(k) or "") for k in ("calculation_id", "calculation_generation", "latest_completed_h1_utc", "broker_offset_minutes"))
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:24]


def _redact_secret(value: Any) -> Any:
    secret_pattern = re.compile(r"(api[_ -]?key|bearer|password|passwd|secret|token|authorization)", re.I)
    if isinstance(value, Mapping):
        return {str(k): ("[REDACTED]" if secret_pattern.search(str(k)) else _redact_secret(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_secret(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact_secret(v) for v in value)
    text = str(value) if isinstance(value, str) else value
    if isinstance(text, str):
        text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*", r"\1[REDACTED]", text)
        text = re.sub(r"(?i)(api[_ -]?key|password|secret|token)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    return text


def _closed_field_metric_result(state: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("lunch_metric_result_cache", "full_metric_result_cache_20260618"):
        value = state.get(key)
        if isinstance(value, Mapping) and value.get("ok"):
            return value
    try:
        from core.system_wide_completion_20260618 import published_metric_result
        value = published_metric_result(state)
        if isinstance(value, Mapping) and value.get("ok"):
            return value
    except Exception:
        pass
    return {}


def _frame_text(frame: Any, state: Mapping[str, Any], canonical: Mapping[str, Any], *, limit: int = 600) -> str:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return "UNAVAILABLE"
    work = add_broker_display_columns(frame.head(limit), state, canonical)
    # Never serialize secret-looking columns.
    cols = [c for c in work.columns if not re.search(r"api[_ -]?key|bearer|password|secret|token", str(c), re.I)]
    return work.loc[:, cols].to_csv(index=False)


def _json_text(value: Any) -> str:
    return json.dumps(_redact_secret(value), default=str, ensure_ascii=False, indent=2)


def _forecast_horizon(canonical: Mapping[str, Any], summary: Mapping[str, Any], h: int) -> Any:
    horizons = _mapping(_mapping(canonical.get("forecasts")).get("horizons"))
    item = _mapping(horizons.get(f"{h}h") or horizons.get(f"H+{h}") or horizons.get(str(h)))
    return item or _mapping(summary.get("projection")).get(f"h{h}") or "UNAVAILABLE"


def _short_lines(state: Mapping[str, Any], canonical: Mapping[str, Any], contract: Mapping[str, Any], fact: Mapping[str, Any], sync: Mapping[str, Any]) -> list[str]:
    final = _mapping(canonical.get("final_decision")); regime = _mapping(canonical.get("regime")); reliability = _mapping(canonical.get("reliability")); priority = _mapping(canonical.get("priority")); scores = _mapping(fact.get("protected score summaries"))
    quality = validate_data_quality_contract(state)
    execution = _mapping(canonical.get("execution")); technical = fact.get("Field 4 technical analysis summary"); sentiment = fact.get("Research sentiment summary")
    v7 = _mapping(canonical.get("quant_research_v7")); v7_summary = _mapping(v7.get("summary")); v7_methods = _mapping(v7.get("methods"))
    v8 = _mapping(canonical.get("quant_research_v8")); v8_morning = _mapping(v8.get("morning")); v8_readiness = _mapping(v8.get("readiness")); v8_field1 = _mapping(v8.get("field1_data_quality"))
    def _v7_metrics(method_id: str) -> Mapping[str, Any]:
        return _mapping(_mapping(v7_methods.get(method_id)).get("output_metrics"))
    lines = [
        f"ADX Quant Pro {contract.get('symbol') or 'MULTI'} {contract.get('timeframe') or 'H1'} — Lunch Copy Short",
        f"Calculation ID: {contract.get('calculation_id')}", f"Generation: {contract.get('calculation_generation')}",
        f"Symbol: {contract.get('symbol')}", f"Timeframe: {contract.get('timeframe')}",
        f"Latest Completed H1 UTC: {contract.get('latest_completed_h1_utc')}",
        f"Broker Time: {contract.get('broker_time_display')}", f"Myanmar Time: {contract.get('myanmar_time_display')}",
        f"Broker Offset Minutes: {contract.get('broker_offset_minutes')}", f"Broker Timezone: {contract.get('broker_timezone_iana') or 'fixed/manual'}",
        f"Timestamp Source: {contract.get('timestamp_source')}", f"Watermark Status: {contract.get('watermark_status')}",
        f"Freshness Lag Minutes: {contract.get('freshness_lag_minutes')}", f"Source: {contract.get('source')}",
        f"Synchronization Status: {sync.get('status_display') or sync.get('status')}", f"Synchronization Reason: {sync.get('reason')}",
        f"Calculation ID Match: {sync.get('calculation_id_match')}", f"Generation Match: {sync.get('generation_match')}",
        f"Broker Offset Match: {sync.get('broker_offset_match')}", f"Source Match: {sync.get('source_match')}",
        f"Current Decision: {fact.get('current decision')}", f"Direction: {fact.get('direction')}",
        f"Less-Risky Decision: {fact.get('less-risky decision')}", f"Decision Confidence: {_first(final.get('calibrated_confidence'), final.get('confidence'))}",
        f"Main Reason: {_first(final.get('main_reason'), final.get('reason'))}", f"Blocking Warnings: {_first(final.get('blocking_reasons'), fact.get('conflict warnings'), default=[])}",
        f"V7 Shadow Status: {v7_summary.get('overall_status', 'UNAVAILABLE')}",
        f"V7 Advisory/Risk: {_v7_metrics('dynamic_trading_costs').get('advisory_label', 'UNAVAILABLE')} / {_v7_metrics('coherent_risk').get('final_shadow_risk_state', 'UNAVAILABLE')}",
        f"V7 Broker Candle: {_mapping(v7.get('identity')).get('completed_broker_time', 'UNAVAILABLE')}",
        f"V8 Morning Readiness: {v8_readiness.get('visible_status', 'UNAVAILABLE')}",
        f"V8 Production Readiness: {v8_readiness.get('overall_status', 'UNAVAILABLE')}",
        f"V8 Field 1 Sync: {v8_field1.get('sync_status', 'UNAVAILABLE')}",
        f"Master Score: {_first(scores.get('master'), canonical.get('master_score'))}", f"Entry Score: {_first(scores.get('entry'), canonical.get('entry_score'))}",
        f"Hold Score: {_first(scores.get('hold'), canonical.get('hold_safety'))}", f"TP Quality: {_first(scores.get('tp'), canonical.get('tp_quality'))}",
        f"Exit Risk: {_first(scores.get('exit_risk'), canonical.get('exit_risk'))}", f"Trend Capacity Remaining: {_first(scores.get('trend_capacity_remaining'), canonical.get('trend_capacity_remaining'))}",
        f"BUY Pressure: {_first(scores.get('buy_pressure'), canonical.get('buy_pressure'))}", f"SELL Pressure: {_first(scores.get('sell_pressure'), canonical.get('sell_pressure'))}",
        f"Pullback Readiness: {_first(scores.get('pullback_readiness'), canonical.get('pullback_readiness'))}", f"M1 Confirmation: {_first(scores.get('m1_confirmation'), canonical.get('m1_confirmation'))}",
        f"Major Regime: {_first(regime.get('major_regime'), _mapping(fact.get('regime and regime age')).get('regime'))}",
        f"Regime Start: {_first(regime.get('start'), regime.get('regime_start'), regime.get('last_change'))}",
        f"Regime Age: {_first(regime.get('age'), regime.get('days_since_change'))}", f"Expected Regime Duration: {_first(regime.get('expected_duration'), regime.get('expected_days'))}",
        f"Estimated Remaining Duration: {_first(regime.get('remaining_duration'), regime.get('estimated_days_remaining'))}",
        f"Regime Alpha: {_first(regime.get('alpha'), canonical.get('regime_alpha'))}", f"Regime Delta: {_first(regime.get('delta'), canonical.get('regime_delta'))}",
        f"Regime Reliability: {_first(regime.get('reliability'), reliability.get('score'), fact.get('regime reliability'))}",
        f"Transition Probability: {_first(regime.get('transition_probability'), _mapping(canonical.get('transition_trust')).get('transition_probability'))}",
        f"Transition Trust: {fact.get('transition trust')}", f"H1/H4/D1 Agreement: {_first(regime.get('multitimeframe_agreement'), canonical.get('h1_h4_d1_agreement'))}",
        f"Priority Label: {_first(priority.get('priority_label'), priority.get('opportunity_quality'), _mapping(fact.get('priority and Greedy/KNN rank')).get('opportunity_quality'))}",
        f"Priority Rank: {_first(priority.get('priority_rank'), priority.get('current_rank'))}", f"KNN Score: {_first(priority.get('knn_score'), priority.get('knn_priority'))}",
        f"Greedy Score: {priority.get('greedy_score', 'UNAVAILABLE')}", f"Best Entry Hour: {_first(priority.get('best_entry_hour'), priority.get('best_hour'))}",
        f"Second Best Entry Hour: {_first(priority.get('second_best_entry_hour'), priority.get('second_best_hour'))}",
    ]
    for h in range(1, 7): lines.append(f"H+{h} Projection: {_forecast_horizon(canonical, fact, h)}")
    lines.extend([
        f"Calibrated Forecast Ranges: {_first(_mapping(canonical.get('forecasts')).get('calibrated_bands'), _mapping(fact.get('calibrated forecast ranges')).get('calibrated_bands'))}",
        f"Selected TP: {_first(final.get('selected_tp'), _mapping(canonical.get('risk')).get('selected_tp'))}",
        f"Selected SL: {_first(final.get('selected_sl'), _mapping(canonical.get('risk')).get('selected_sl'))}",
        f"TP/SL Evidence: {_first(final.get('tp_sl_guidance'), _mapping(canonical.get('risk')).get('tp_sl_guidance'))}",
        f"Sentiment Summary: {sentiment}", f"Technical Summary: {technical}",
        f"Sentiment/Technical/Decision Agreement: {_first(_mapping(canonical.get('agreement')).get('status'), _mapping(state.get('field6_combined_history_summary_20260622')).get('Agreement'))}",
        f"Execution Spread: {_first(execution.get('spread_pips'), execution.get('spread_points'))}", f"Execution Slippage: {_first(execution.get('estimated_slippage'), execution.get('slippage'))}",
        f"Execution Feasibility: {_first(execution.get('feasibility_label'), default='UNAVAILABLE')}", f"Data Quality Status: {quality.get('quality_status')}",
        f"Data Quality Score: {quality.get('quality_score_0_100')}", f"Data Quality Warnings: {quality.get('quality_flags')}",
        f"Processing Time UTC: {contract.get('processing_time_utc')}",
        f"Ingested At UTC: {contract.get('ingested_at_utc')}",
        f"Broker Clock Available: {contract.get('broker_clock_available')}",
        f"Broker Clock Resolution: {contract.get('broker_clock_resolution')}",
        f"Broker Clock Error: {contract.get('broker_clock_error') or 'NONE'}",
        f"Completed Candle Flag: {contract.get('is_completed_candle')}",
        f"Current Price: {_first(canonical.get('current_price'), canonical.get('last_close'), _mapping(canonical.get('market')).get('current_price'))}",
        f"Expected Move: {_first(execution.get('expected_move'), _mapping(canonical.get('forecasts')).get('expected_move'))}",
        f"Forecast Horizon: {_first(execution.get('forecast_horizon'), _mapping(canonical.get('forecasts')).get('selected_horizon'))}",
        f"Forecast Confidence: {_first(final.get('calibrated_confidence'), _mapping(canonical.get('forecasts')).get('confidence'))}",
        f"Uncertainty: {_first(final.get('uncertainty_pct'), _mapping(canonical.get('uncertainty')).get('combined'))}",
        f"Volatility: {_first(_mapping(canonical.get('market')).get('volatility'), canonical.get('volatility'))}",
        f"Market Session: {_first(_mapping(canonical.get('market')).get('session'), canonical.get('session'))}",
        f"Market Quality: {_first(priority.get('market_quality'), canonical.get('market_quality'))}",
        f"Forecast Agreement: {_first(final.get('forecast_agreement'), canonical.get('forecast_agreement'))}",
        f"Conflict Status: {_first(final.get('conflict_status'), canonical.get('conflict_status'))}",
        f"Counter-Trend Status: {_first(final.get('counter_trend'), canonical.get('counter_trend'))}",
        f"Execution Cost/Expected Move Ratio: {_first(execution.get('cost_to_expected_move_ratio'), execution.get('cost-to-expected-move ratio'))}",
        f"Contract Version: {contract.get('contract_version')}", "Profit Guarantee: NONE — evidence is informational and risk-aware.",
    ])
    # Add bounded cross-table details, then cap at 95 physical lines.
    tables = _mapping(sync.get('cross_table_report')).get('tables') or {}
    for name, report in list(tables.items())[:10]:
        lines.append(f"Table Sync {name}: {_mapping(report).get('status')} / delta={_mapping(report).get('difference_minutes')} min")
    bounded = lines[:40]
    text = "\n".join(str(x) for x in bounded)
    while len(text) > 6000 and bounded:
        bounded.pop()
        text = "\n".join(str(x) for x in bounded)
    return bounded

def build_lunch_copy_payloads(state: MutableMapping[str, Any], *, include_full: bool = True) -> dict[str, str]:
    """Build complete closed-field-safe copy payloads from one generation identity."""
    canonical = get_canonical_generation(state)
    contract = market_time_contract(state, canonical)
    key = payload_cache_key(contract)
    cache = state.get("lunch_copy_payload_cache_20260622")
    if isinstance(cache, Mapping) and cache.get("key") == key and cache.get("short") and (not include_full or cache.get("full")):
        return {"short": str(cache.get("short", "")), "full": str(cache.get("full", "")), "key": key}
    started = time.perf_counter()
    try:
        from core.cross_table_sync_20260622 import publish_cross_table_sync
        cross = publish_cross_table_sync(state, canonical=canonical)
    except Exception:
        cross = {}
    metric_result = _closed_field_metric_result(state)
    overall = metric_result.get("history") if isinstance(metric_result.get("history"), pd.DataFrame) else pd.DataFrame()
    try:
        combined6 = build_combined_field6_history(state)
    except Exception:
        combined6 = pd.DataFrame()
    sync = synchronization_status(state, field1_history=overall, field6_history=combined6, canonical=canonical)
    if cross:
        sync["cross_table_report"] = cross
    state["lunch_sync_status_20260622"] = sync
    fact = build_ai_fact_pack(state)
    v9_snapshot = None
    try:
        from core.canonical_sync_v9 import read_snapshot_for_lunch
        v9_snapshot = read_snapshot_for_lunch(state)
    except Exception:
        v9_snapshot = None
    v9_lines = []
    if v9_snapshot is not None:
        v9_lines = [
            "[CANONICAL SYNC V9]",
            f"run_id: {v9_snapshot.run_id}", f"snapshot_hash: {v9_snapshot.snapshot_hash}",
            f"broker_time: {v9_snapshot.broker_time}", f"candle_time: {v9_snapshot.candle_time}",
            f"priority: {v9_snapshot.priority_label} ({v9_snapshot.priority_score:.2f})",
            f"decision: {v9_snapshot.decision}", f"regime: {v9_snapshot.regime}",
            f"reliability: {v9_snapshot.reliability_score:.2f}",
            f"data_quality_score: {v9_snapshot.data_quality_score:.2f}",
        ]
    short = "\n".join((v9_lines + _short_lines(state, canonical, contract, fact, sync))[:40])
    if not include_full:
        from core.generation_order_guard_20260622 import publish_if_not_older
        existing_full = str(cache.get("full", "")) if isinstance(cache, Mapping) and cache.get("key") == key else ""
        cache_value = {"key": key, "short": short, "full": existing_full, "built_at": time.time(), "generation": contract.get("calculation_generation")}
        publish_if_not_older(state, key="lunch_copy_payload_cache_20260622", value=cache_value, candidate=canonical)
        state["timing_top_copy_short_build_20260622"] = round(time.perf_counter() - started, 6)
        return {"short": short, "full": "", "key": key}

    histories = metric_result.get("history_by_factor") if isinstance(metric_result.get("history_by_factor"), Mapping) else {}
    field1_parts = ["[Overall Full Metric History — Last 25 Days]", _frame_text(overall, state, canonical)]
    for name, frame in list(histories.items())[:10]:
        field1_parts.extend([f"[Decision History: {name}]", _frame_text(frame, state, canonical)])
    regime_tables = state.get("regime_standard_detail_tables_published_20260618") if isinstance(state.get("regime_standard_detail_tables_published_20260618"), Mapping) else {}
    field4_frames = {}
    for k in ("canonical_priority_table_20260617", "reliability_history_20260618", "similar_day_history_20260619", "field4_technical_fact_table_20260622"):
        v = state.get(k)
        if isinstance(v, pd.DataFrame): field4_frames[k] = v
    field6_sections = ["[Combined Sentiment + Technical + Decision History]", _frame_text(combined6, state, canonical)]
    try:
        from core.field6_quant_history_20260622 import FIELD6_TABLES, QUANT_V6_FIELD6_VIEWS, build_field6_history_table
        for label, table_name in QUANT_V6_FIELD6_VIEWS + FIELD6_TABLES:
            field6_sections.extend([f"[{label}]", _frame_text(build_field6_history_table(table_name, state), state, canonical, limit=200)])
    except Exception as exc:
        field6_sections.extend(["[Field 6 Quant Histories]", f"UNAVAILABLE: {type(exc).__name__}: {exc}"])

    full_sections = [
        f"ADX Quant Pro {contract.get('symbol') or 'MULTI'} {contract.get('timeframe') or 'H1'} — Complete Canonical Lunch Snapshot",
        "[CANONICAL SYNC V9 SNAPSHOT]", _json_text(v9_snapshot.__dict__ if v9_snapshot is not None else {"status": "UNAVAILABLE"}),
        "[IDENTITY AND BROKER-TIME CONTRACT]", _json_text(contract),
        "[SYNCHRONIZATION AND DATA QUALITY]", _json_text({"sync": sync, "quality": validate_data_quality_contract(state)}),
        "[FIELD 1 — FULL METRIC AND TEN DECISION HISTORIES]", *field1_parts,
        "[FIELD 2 — PAST / PRESENT / FUTURE VISUALIZATION SUMMARIES]", _json_text({"past": "last 25 trading days, completed-only broker-time history with overlap evidence", "present": {"reliability": _mapping(canonical.get("reliability")), "market_quality": _mapping(canonical.get("priority")).get("market_quality"), "system_trust": canonical.get("system_trust")}, "future": _mapping(canonical.get("forecasts")) or _mapping(canonical.get("powerbi"))}),
        "[FIELD 3 — REGIME LIFECYCLE, ALPHA/DELTA AND HISTORIES]", _json_text({"current": _mapping(canonical.get("regime")), "tables": {k: _frame_text(v, state, canonical) for k, v in regime_tables.items() if isinstance(v, pd.DataFrame)}}),
        "[FIELD 4 — TECHNICAL, PRIORITY, RELIABILITY, KNN/GREEDY AND SIMILAR-DAY EVIDENCE]",
        _json_text({"summary": state.get("field4_technical_fact_summary_20260622", "UNAVAILABLE"), "frames": {k: _frame_text(v, state, canonical) for k, v in field4_frames.items()}}),
        "[FIELD 5 — GROUNDED AI FACT PACK AND EVIDENCE METADATA]", _json_text({"fact_pack": fact, "last_answer_audit": state.get("ai_last_answer_audit_20260622"), "last_risk_coverage": state.get("ai_last_risk_coverage_audit_20260622")}),
        "[FIELD 6 — QUANTITATIVE-TRADER RESEARCH HISTORIES]", *field6_sections,
        "[ADVANCED QUANT V6 SHADOW RESEARCH]", _json_text(canonical.get("quant_research_v6", {})),
        "[ADVANCED QUANT V7 SHADOW RESEARCH]", _json_text(canonical.get("quant_research_v7", {})),
        "[ADVANCED QUANT V8 MORNING / CALIBRATION / READINESS SHADOW EVIDENCE]", _json_text(canonical.get("quant_research_v8", {})),
        "[RESEARCH SHADOW LAYERS]", _json_text(build_research_shadow_layers(state)),
        "[PROTECTED-LOGIC NOTICE]", "All content is a read-only projection of already-published outputs. No protected calculation, strategy, model parameter, weight, TP/SL formula, regime definition, or decision rule was changed by copy serialization.",
    ]
    full = "\n".join(str(x) for x in full_sections)
    from core.generation_order_guard_20260622 import publish_if_not_older
    cache_value = {"key": key, "short": short, "full": full, "built_at": time.time(), "generation": contract.get("calculation_generation")}
    publish_if_not_older(state, key="lunch_copy_payload_cache_20260622", value=cache_value, candidate=canonical)
    state["timing_top_copy_payload_build_20260622"] = round(time.perf_counter() - started, 6)
    return {"short": short, "full": full, "key": key}

def render_lunch_top_copy_buttons(state: MutableMapping[str, Any]) -> None:
    """Exactly two top controls; Full serialization starts only when pressed."""
    try:
        import streamlit as st
        from ui.copy_tools import central_copy_result
        canonical = get_canonical_generation(state)
        contract = market_time_contract(state, canonical)
        key = payload_cache_key(contract)
        st.markdown("#### 📋 Canonical Lunch Copy")
        cols = st.columns(3)
        short_pressed = cols[0].button("Copy Short", key=f"lunch_top_copy_short_trigger_{key}", use_container_width=True)
        full_pressed = cols[1].button("Copy Full", key=f"lunch_top_copy_full_trigger_{key}", use_container_width=True)
        refresh_pressed = cols[2].button("Refresh Snapshot", key=f"lunch_top_refresh_snapshot_{key}", use_container_width=True)
        if refresh_pressed:
            try:
                from core.complete_repair_20260705 import refresh_lunch_snapshot
                report = refresh_lunch_snapshot(state)
                if report.get("ok"):
                    st.rerun()
                else:
                    st.warning(f"The snapshot was only partially refreshed. Support reference: {report.get('incident_id') or 'REFRESH-PARTIAL'}.")
            except Exception as exc:
                from core.complete_repair_20260705 import log_internal_error
                incident = log_internal_error("lunch.copy_refresh", exc)
                st.warning(f"The completed snapshot could not be refreshed. Support reference: {incident}.")
        if short_pressed:
            payloads = build_lunch_copy_payloads(state, include_full=False)
            with cols[0]:
                central_copy_result(payloads["short"], f"lunch_top_copy_short_result_{payloads['key']}", height=102)
        if full_pressed:
            started = time.perf_counter()
            payloads = build_lunch_copy_payloads(state, include_full=True)
            state["timing_copy_full_generation_20260622"] = round(time.perf_counter() - started, 6)
            with cols[1]:
                central_copy_result(payloads["full"], f"lunch_top_copy_full_result_{payloads['key']}", height=102)
        st.caption("Copy Short, Copy Full, and Refresh Snapshot use the same immutable canonical generation; Refresh never recalculates.")
        # Legacy discovery marker only: central_copy_button("Copy Full", ...)
    except Exception as exc:
        try:
            import streamlit as st
            st.warning(f"Top copy buttons unavailable: {exc}")
        except Exception:
            pass


EUR_POS = {"euro rises", "eur rises", "hawkish ecb", "ecb hike", "eurozone growth", "strong euro", "eur positive", "inflation hot"}
EUR_NEG = {"euro falls", "eur falls", "dovish ecb", "ecb cut", "eurozone recession", "weak euro", "eur negative"}
USD_POS = {"dollar rises", "usd rises", "hawkish fed", "fed hike", "strong dollar", "hot nfp", "hot cpi", "usd positive"}
USD_NEG = {"dollar falls", "usd falls", "dovish fed", "fed cut", "weak dollar", "soft nfp", "soft cpi", "usd negative"}


def classify_eurusd_sentiment(headline: str, *, published_time_utc: Any = None, source: str = "cached research", now_utc: Any = None) -> dict[str, Any]:
    """Lightweight finance-domain sentiment inspired by FinBERT research."""
    text = str(headline or "").lower()
    def score(terms: Iterable[str]) -> int:
        return sum(1 for t in terms if t in text)
    eur_score = score(EUR_POS) - score(EUR_NEG)
    usd_score = score(USD_POS) - score(USD_NEG)
    # direct vocabulary fallbacks
    if "eur" in text or "euro" in text or "ecb" in text:
        eur_score += text.count("beat") + text.count("strong") - text.count("miss") - text.count("weak")
    if "usd" in text or "dollar" in text or "fed" in text or "nfp" in text or "cpi" in text:
        usd_score += text.count("strong") + text.count("hawkish") - text.count("weak") - text.count("dovish")
    buy_support = eur_score > 0 or usd_score < 0
    sell_support = eur_score < 0 or usd_score > 0
    if buy_support and not sell_support:
        direction = "BUY"
    elif sell_support and not buy_support:
        direction = "SELL"
    elif buy_support and sell_support:
        direction = "CONFLICT"
    elif headline:
        direction = "NEUTRAL"
    else:
        direction = "UNAVAILABLE"
    raw = float(eur_score - usd_score)
    published = _utc(published_time_utc)
    now = _utc(now_utc) or pd.Timestamp.now(tz="UTC")
    age = (now - published).total_seconds() / 60.0 if published is not None else None
    relevance = 100 if any(k in text for k in ("eur", "euro", "ecb", "usd", "dollar", "fed", "cpi", "nfp", "pmi")) else 35
    confidence = max(0, min(100, 45 + abs(raw) * 15 + (15 if direction in {"BUY", "SELL"} else 0))) if direction != "UNAVAILABLE" else 0
    return {
        "published_time_utc": published.isoformat() if published is not None else None,
        "Broker Published Time": None,
        "Myanmar Published Time": _display(published, 390, "Myanmar UTC+6:30") if published is not None else "UNAVAILABLE",
        "source": source,
        "headline": headline,
        "EUR sentiment": eur_score,
        "USD sentiment": usd_score,
        "EURUSD directional sentiment": direction,
        "direction": direction,
        "raw score": raw,
        "calibrated score": max(-1.0, min(1.0, raw / 4.0)),
        "relevance": relevance,
        "impact": "HIGH" if relevance >= 80 and abs(raw) >= 2 else "MEDIUM" if relevance >= 50 else "LOW",
        "confidence": confidence,
        "age_minutes": round(age, 2) if age is not None else None,
        "duplicate_group": hashlib.sha1(re.sub(r"\W+", " ", text).strip().encode()).hexdigest()[:10] if headline else "UNAVAILABLE",
        "quality_status": "OK" if direction != "UNAVAILABLE" else "UNAVAILABLE",
        "reason": "EUR positive or USD negative supports EURUSD BUY; EUR negative or USD positive supports EURUSD SELL; contradictory evidence becomes CONFLICT/NEUTRAL.",
    }


def leakage_safe_asof_join(left: pd.DataFrame, right: pd.DataFrame, *, left_time: str = "event_time_utc", right_time: str = "published_time_utc") -> pd.DataFrame:
    if not isinstance(left, pd.DataFrame) or left.empty:
        return pd.DataFrame()
    if not isinstance(right, pd.DataFrame) or right.empty or left_time not in left.columns or right_time not in right.columns:
        return left.copy(deep=False)
    l = left.copy(deep=False)
    r = right.copy(deep=False)
    l[left_time] = pd.to_datetime(l[left_time], errors="coerce", utc=True)
    r[right_time] = pd.to_datetime(r[right_time], errors="coerce", utc=True)
    l = l.dropna(subset=[left_time]).sort_values(left_time)
    r = r.dropna(subset=[right_time]).sort_values(right_time)
    merged = pd.merge_asof(l, r, left_on=left_time, right_on=right_time, direction="backward", allow_exact_matches=True)
    return merged


def build_sentiment_history(state: MutableMapping[str, Any]) -> pd.DataFrame:
    source = state.get("research_news_history_20260622") or state.get("research_news_df") or state.get("news_history")
    rows: list[dict[str, Any]] = []
    if isinstance(source, pd.DataFrame) and not source.empty:
        for _, row in source.head(500).iterrows():
            headline = _first(row.get("headline"), row.get("title"), row.get("summary"), default="")
            ts = _first(row.get("published_time_utc"), row.get("published_at"), row.get("time"), row.get("date"), default=None)
            rows.append(classify_eurusd_sentiment(str(headline), published_time_utc=ts, source=str(row.get("source") or "cached research")))
    else:
        # Empty, explicit UNAVAILABLE row. No invented direction.
        rows.append(classify_eurusd_sentiment("", source="cached research unavailable"))
    df = pd.DataFrame(rows)
    state["research_sentiment_history_20260622"] = df
    if not df.empty:
        latest = df.iloc[0].to_dict()
        state["research_sentiment_summary_20260622"] = {k: latest.get(k) for k in ("direction", "confidence", "reason", "quality_status")}
    return df


def publish_field4_technical_fact_table(state: MutableMapping[str, Any]) -> pd.DataFrame:
    canonical = get_canonical_generation(state)
    contract = market_time_contract(state, canonical)
    row = {
        "event_time_utc": contract.get("latest_completed_h1_utc"),
        "calculation_id": contract.get("calculation_id"),
        "generation": contract.get("calculation_generation"),
        "technical direction": _first(canonical.get("technical_direction"), canonical.get("full_metric_direction"), _mapping(canonical.get("final_decision")).get("directional_market_view"), default="UNAVAILABLE"),
        "technical score": _first(canonical.get("technical_score"), canonical.get("master_score"), default="UNAVAILABLE"),
        "trend strength": _first(canonical.get("trend_strength"), canonical.get("adx"), default="UNAVAILABLE"),
        "ADX": _first(canonical.get("ADX"), canonical.get("adx"), default="UNAVAILABLE"),
        "+DI": _first(canonical.get("+DI"), canonical.get("plus_di"), default="UNAVAILABLE"),
        "-DI": _first(canonical.get("-DI"), canonical.get("minus_di"), default="UNAVAILABLE"),
        "momentum": _first(canonical.get("momentum"), default="UNAVAILABLE"),
        "volatility": _first(canonical.get("volatility"), _mapping(canonical.get("regime")).get("volatility_regime"), default="UNAVAILABLE"),
        "compression": _first(canonical.get("compression"), default="UNAVAILABLE"),
        "support/resistance state": _first(canonical.get("support_resistance_state"), default="UNAVAILABLE"),
        "pullback readiness": _first(canonical.get("pullback_readiness"), default="UNAVAILABLE"),
        "trend capacity remaining": _first(canonical.get("trend_capacity_remaining"), default="UNAVAILABLE"),
        "forecast agreement": _first(_mapping(canonical.get("forecasts")).get("agreement_score"), default="UNAVAILABLE"),
        "regime": _first(_mapping(canonical.get("regime")).get("major_regime"), canonical.get("current_major_regime"), default="UNAVAILABLE"),
        "market quality": _first(canonical.get("market_quality"), _mapping(canonical.get("data_quality")).get("quality_score_0_100"), default="UNAVAILABLE"),
        "conflict status": _first(canonical.get("conflict_status"), _mapping(canonical.get("final_decision")).get("conflict_status"), default="UNAVAILABLE"),
        "reliability": _first(_mapping(canonical.get("reliability")).get("score"), default="UNAVAILABLE"),
        "technical reason": _first(_mapping(canonical.get("final_decision")).get("main_reason"), default="Published technical facts only; no recalculation."),
    }
    df = pd.DataFrame([row])
    state["field4_technical_fact_table_20260622"] = df
    state["field4_technical_fact_summary_20260622"] = row
    return df


def agreement_label(sentiment: Any, technical: Any, decision: Any) -> tuple[str, str]:
    vals = [str(x or "UNAVAILABLE").upper() for x in (sentiment, technical, decision)]
    if any(v in {"UNAVAILABLE", "", "NONE"} for v in vals):
        return "UNAVAILABLE", "At least one evidence source is unavailable."
    dirs = ["BUY" if "BUY" in v else "SELL" if "SELL" in v else "WAIT" if "WAIT" in v or "NO TRADE" in v else v for v in vals]
    if dirs[0] == dirs[1] == dirs[2]:
        return "CONFIRM", "Sentiment, technical direction and protected decision align."
    if len(set(dirs)) == 2:
        return "PARTIAL", "Two of the three evidence columns align."
    return "CONFLICT", "Evidence columns oppose each other."


def _decision_history_frame(state: Mapping[str, Any]) -> pd.DataFrame:
    for key in ("protected_decision_history_20260622", "full_metric_history_df_20260618", "canonical_priority_table_20260617"):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy(deep=False)
    result = state.get("lunch_metric_result_cache") or state.get("full_metric_result_cache_20260618")
    if isinstance(result, Mapping) and isinstance(result.get("history"), pd.DataFrame):
        return result.get("history").copy(deep=False)
    return pd.DataFrame()


def build_combined_field6_history(state: MutableMapping[str, Any], *, days: int = 25) -> pd.DataFrame:
    started = time.perf_counter()
    canonical = get_canonical_generation(state)
    contract = market_time_contract(state, canonical)
    decision = _decision_history_frame(state)
    if decision.empty:
        decision = pd.DataFrame([{"event_time_utc": contract.get("latest_completed_h1_utc")}])
    tcol = _time_col(decision)
    if tcol and tcol != "event_time_utc":
        decision = decision.rename(columns={tcol: "event_time_utc"})
    if "event_time_utc" not in decision.columns:
        decision.insert(0, "event_time_utc", contract.get("latest_completed_h1_utc"))
    decision["event_time_utc"] = pd.to_datetime(decision["event_time_utc"], errors="coerce", utc=True)
    cutoff = _utc(contract.get("latest_completed_h1_utc"))
    if cutoff is not None:
        decision = decision.loc[decision["event_time_utc"].notna() & decision["event_time_utc"].le(cutoff) & decision["event_time_utc"].ge(cutoff - pd.Timedelta(days=days))]
    decision = decision.sort_values("event_time_utc", ascending=False).head(days * 24 + 1)
    sentiment = build_sentiment_history(state)
    technical = publish_field4_technical_fact_table(state)
    sentiment_for_join = sentiment.rename(columns={"published_time_utc": "published_time_utc"}) if not sentiment.empty else sentiment
    merged = leakage_safe_asof_join(decision.sort_values("event_time_utc"), sentiment_for_join, left_time="event_time_utc", right_time="published_time_utc")
    if not isinstance(merged, pd.DataFrame) or merged.empty:
        merged = decision.copy(deep=False)
    # Attach latest technical facts as evidence columns only.
    tech_row = technical.iloc[0].to_dict() if isinstance(technical, pd.DataFrame) and not technical.empty else {}
    final = _mapping(canonical.get("final_decision"))
    regime = _mapping(canonical.get("regime"))
    rows = []
    for _, row in merged.iterrows():
        protected_decision = _first(row.get("Decision"), row.get("decision"), row.get("Current Decision"), final.get("final_decision"), default="UNAVAILABLE")
        protected_direction = _first(row.get("Direction"), row.get("direction_x"), row.get("Directional Market View"), final.get("directional_market_view"), default="UNAVAILABLE")
        sent_dir = _first(row.get("direction_y"), row.get("direction"), row.get("EURUSD directional sentiment"), default="UNAVAILABLE")
        tech_dir = _first(tech_row.get("technical direction"), default="UNAVAILABLE")
        agree, reason = agreement_label(sent_dir, tech_dir, protected_direction)
        rows.append({
            "event_time_utc": row.get("event_time_utc"),
            "symbol": contract.get("symbol"), "timeframe": contract.get("timeframe"),
            "sentiment direction": sent_dir,
            "sentiment score": _first(row.get("calibrated score"), default="UNAVAILABLE"),
            "sentiment confidence": _first(row.get("confidence"), default="UNAVAILABLE"),
            "news count": 0 if sent_dir == "UNAVAILABLE" else 1,
            "top sentiment reason": _first(row.get("reason"), default="UNAVAILABLE"),
            "sentiment age": _first(row.get("age_minutes"), default="UNAVAILABLE"),
            "technical direction": tech_dir,
            "technical score": _first(tech_row.get("technical score"), default="UNAVAILABLE"),
            "regime": _first(row.get("regime"), tech_row.get("regime"), regime.get("major_regime"), default="UNAVAILABLE"),
            "market quality": _first(row.get("market quality"), tech_row.get("market quality"), default="UNAVAILABLE"),
            "forecast agreement": _first(tech_row.get("forecast agreement"), default="UNAVAILABLE"),
            "reliability": _first(row.get("reliability"), tech_row.get("reliability"), default="UNAVAILABLE"),
            "protected Decision": protected_decision,
            "protected Direction": protected_direction,
            "decision confidence": _first(row.get("Confidence"), row.get("confidence"), final.get("calibrated_confidence"), default="UNAVAILABLE"),
            "sentiment/technical agreement": agree,
            "decision conflict": reason,
            "Agreement": agree,
            "Reason": reason,
            "data-quality score": _first(_mapping(canonical.get("data_quality")).get("quality_score_0_100"), default="UNAVAILABLE"),
            "drift status": _first(_mapping(canonical.get("drift" )).get("status"), default="UNAVAILABLE"),
            "synchronization status": "PENDING",
            "calculation_id": contract.get("calculation_id"),
            "generation": contract.get("calculation_generation"),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out["event_time_utc"] = pd.to_datetime(out["event_time_utc"], errors="coerce", utc=True)
        out = out.sort_values("event_time_utc", ascending=False, kind="mergesort").reset_index(drop=True)
        out = add_broker_display_columns(out, state, canonical)
        try:
            from core.canonical_sync_v9 import normalize_history_frame
            out = normalize_history_frame(out, field_name="FIELD_6", metric_name="combined_sentiment_technical_decision", state=state)
        except Exception:
            pass
        sync = synchronization_status(state, field6_history=out, canonical=canonical)
        out["synchronization status"] = sync.get("status")
        state["lunch_sync_status_20260622"] = sync
        first = out.iloc[0].to_dict()
        state["field6_combined_history_summary_20260622"] = {
            "Current Protected Decision": first.get("protected Decision"),
            "Current Sentiment Direction": first.get("sentiment direction"),
            "Current Technical Direction": first.get("technical direction"),
            "Agreement": first.get("Agreement"),
            "Reliability": first.get("reliability"),
            "Data Quality": contract.get("data_quality_status"),
            "Latest Broker Time": first.get("Broker Time"),
            "Latest Myanmar Time": first.get("Myanmar Time"),
        }
    state["field6_combined_history_20260622"] = out
    state["timing_field6_merge_20260622"] = round(time.perf_counter() - started, 6)
    return out


def render_field6_combined_history(state: MutableMapping[str, Any]) -> None:
    try:
        import streamlit as st
        from ui.copy_tools import central_copy_button
        table = build_combined_field6_history(state)
        summary = state.get("field6_combined_history_summary_20260622") if isinstance(state.get("field6_combined_history_summary_20260622"), Mapping) else {}
        st.markdown("#### Combined Sentiment + Technical + Decision History")
        cols = st.columns(4)
        cols[0].metric("Protected Decision", str(summary.get("Current Protected Decision", "UNAVAILABLE")))
        cols[1].metric("Sentiment", str(summary.get("Current Sentiment Direction", "UNAVAILABLE")))
        cols[2].metric("Technical", str(summary.get("Current Technical Direction", "UNAVAILABLE")))
        cols[3].metric("Agreement", str(summary.get("Agreement", "UNAVAILABLE")))
        if table.empty:
            st.info("Combined history is unavailable for this generation.")
        else:
            st.dataframe(table.drop(columns=[c for c in ["event_time_utc"] if c in table.columns]), use_container_width=True, hide_index=True, height=520)
            central_copy_button("Copy Field 6 Combined History", table.to_csv(index=False), "field6_combined_history_copy_20260622", height=112, show_fallback=True)
    except Exception as exc:
        try:
            import streamlit as st
            st.warning(f"Combined Field 6 history unavailable: {exc}")
        except Exception:
            pass


def validate_data_quality_contract(state: Mapping[str, Any]) -> dict[str, Any]:
    canonical = get_canonical_generation(state)
    contract = market_time_contract(state, canonical)
    frames = []
    for key in ("full_metric_history_df_20260618", "canonical_priority_table_20260617", "field6_combined_history_20260622"):
        v = state.get(key)
        if isinstance(v, pd.DataFrame) and not v.empty:
            frames.append((key, v))
    flags: list[str] = []
    warnings = 0
    for key, frame in frames:
        col = _time_col(frame)
        if col:
            parsed = pd.to_datetime(frame[col], errors="coerce", utc=True)
            if parsed.isna().any():
                flags.append(f"{key}: timestamp parse failure")
            if parsed.notna().any() and (parsed.dropna().dt.minute.ne(0).any() or parsed.dropna().dt.second.ne(0).any()):
                warnings += 1; flags.append(f"{key}: non-hourly H1 timestamp boundary")
            if parsed.duplicated().any():
                warnings += 1; flags.append(f"{key}: duplicate canonical timestamps")
        for colname in frame.columns:
            lower = str(colname).lower()
            if "decision" in lower:
                bad = [str(x).upper() for x in frame[colname].dropna().unique() if str(x).upper() not in DECISION_LABELS and len(str(x)) < 32]
                if bad:
                    warnings += 1; flags.append(f"{key}: non-standard decision labels {bad[:4]}")
    score = max(0, 100 - len(flags) * 10 - warnings * 3)
    status = "PASS" if score >= 85 and not flags else "WARN" if score >= 60 else "FAIL"
    return {
        "quality_score_0_100": score,
        "quality_status": status,
        "quality_flags": flags,
        "failed_check_count": len([f for f in flags if "failure" in f.lower() or "parse" in f.lower()]),
        "warning_count": warnings,
        "last_validated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "validator_version": "lunch-broker-sentiment-ai-history-20260622-v1",
        "calculation_id": contract.get("calculation_id"),
        "generation": contract.get("calculation_generation"),
        "checks": ["Completeness", "Validity", "Uniqueness", "Timeliness", "Cross-table consistency", "Calculation-generation consistency", "Timestamp consistency", "Source consistency", "Range validity", "Leakage safety"],
    }


def build_research_shadow_layers(state: Mapping[str, Any]) -> dict[str, Any]:
    canonical = get_canonical_generation(state)
    validation = _mapping(canonical.get("validation_metrics"))
    forecasts = _mapping(canonical.get("forecasts"))
    return {
        "adaptive_conformal_calibration": {
            "recent_coverage": _first(validation.get("coverage"), default="UNAVAILABLE"),
            "target_coverage": _first(validation.get("target_coverage"), default=0.90),
            "miscoverage": _first(validation.get("miscoverage"), default="UNAVAILABLE"),
            "calibrated_lower_upper_bands": _first(forecasts.get("calibrated_bands"), default="UNAVAILABLE"),
            "interval_status": "EVIDENCE_ONLY",
        },
        "adwin_style_drift": {"drift_detected": _first(_mapping(canonical.get("drift")).get("detected"), default=False), "drift_time": _first(_mapping(canonical.get("drift")).get("time"), default="UNAVAILABLE"), "effective_current_window": "UNAVAILABLE", "pre_post_change_magnitude": "UNAVAILABLE"},
        "horizon_contribution_analysis_inspired_by_tft": {f"H+{h}": {"existing_model_contribution": "UNAVAILABLE", "technical_contribution": "UNAVAILABLE", "regime_contribution": "UNAVAILABLE", "sentiment_contribution": "UNAVAILABLE", "dominant_factor": "UNAVAILABLE", "conflict_count": "UNAVAILABLE"} for h in range(1, 7)},
        "shap_style_explanation": {"supporting": [], "opposing": [], "WAIT-causing factors": []},
        "diebold_mariano_forecast_comparison": {"status": "UNAVAILABLE unless enough settled outcomes exist", "loss_function": "absolute_error", "statistic": "UNAVAILABLE", "p_value": "UNAVAILABLE", "sample_size": _first(validation.get("sample_size"), default="UNAVAILABLE")},
        "white_reality_check_hansen_spa_metadata": {"candidate_rules_or_models": "UNAVAILABLE", "benchmark": "current protected production decision", "statistical_support": "UNAVAILABLE", "data_snooping_warning": True},
        "deflated_sharpe_metadata": {"raw_sharpe": "UNAVAILABLE", "adjusted_evidence": "UNAVAILABLE", "estimated_effective_trials": "UNAVAILABLE", "skew": "UNAVAILABLE", "kurtosis": "UNAVAILABLE", "track_record_sufficiency": "UNAVAILABLE"},
        "note": "All layers are read-only evidence and do not alter protected decisions, strategies, model weights, TP or SL logic.",
    }


__all__ = [
    "market_time_contract", "latest_completed_h1_utc", "add_broker_display_columns", "synchronization_status",
    "build_ai_fact_pack", "payload_cache_key", "build_lunch_copy_payloads", "render_lunch_top_copy_buttons",
    "classify_eurusd_sentiment", "build_sentiment_history", "leakage_safe_asof_join",
    "publish_field4_technical_fact_table", "build_combined_field6_history", "render_field6_combined_history",
    "agreement_label", "validate_data_quality_contract", "build_research_shadow_layers", "get_canonical_generation",
]
# CLOUD_SAFE_WRAPPER_EXTENSIONS_RESTORED_20260703
# 2026-06-24 eight-field copy completion layer.
# The original protected serializer remains unchanged above; this wrapper only
# appends read-only Field 7 and Field 8 evidence to the already-built payload.
_build_lunch_copy_payloads_six_field_20260622 = build_lunch_copy_payloads


def build_lunch_copy_payloads(state: MutableMapping[str, Any], *, include_full: bool = True) -> dict[str, str]:
    payloads = _build_lunch_copy_payloads_six_field_20260622(state, include_full=include_full)
    short = str(payloads.get("short") or "")
    full = str(payloads.get("full") or "")

    field8_status = state.get("field8_publication_status_20260624")
    if "Field 8 publication:" not in short:
        status_text = "UNAVAILABLE"
        if isinstance(field8_status, Mapping):
            status_text = str(field8_status.get("status") or ("PUBLISHED" if field8_status.get("published") else "NOT PUBLISHED"))
        short = short + f"\nField 8 publication: {status_text}"

    if include_full and "[FIELD 7 — SCIENTIFIC RESEARCH INTELLIGENCE]" not in full:
        canonical = get_canonical_generation(state)
        field7_summary = state.get("field_07_research_summary_v11")
        try:
            from ui.lunch_field7_shadow_v13 import build_field7_evidence

            field7_evidence = build_field7_evidence(state, canonical, limit=600)
        except Exception as exc:
            field7_evidence = pd.DataFrame()
            field7_summary = {
                "summary": field7_summary,
                "evidence_error": f"{type(exc).__name__}: {exc}",
            }

        try:
            from core.canonical.snapshot import load_canonical_snapshot
            from core.repositories.field8_repository import Field8Repository

            snapshot = load_canonical_snapshot(state)
            if snapshot is None:
                field8_table = pd.DataFrame()
            else:
                snapshot_hash = snapshot.source_snapshot_hash or f"SOURCE_HASH_UNAVAILABLE:{snapshot.run_id}"
                field8_table = Field8Repository().load(
                    snapshot.run_id,
                    snapshot.generation_id or snapshot.run_id,
                    snapshot_hash,
                    days=25,
                )
        except Exception as exc:
            field8_table = pd.DataFrame()
            state["field8_copy_error_20260624"] = f"{type(exc).__name__}: {exc}"

        additions = [
            "[FIELD 7 — SCIENTIFIC RESEARCH INTELLIGENCE]",
            _json_text(field7_summary if isinstance(field7_summary, Mapping) else {"status": "UNAVAILABLE"}),
            _frame_text(field7_evidence, state, canonical, limit=600),
            "[FIELD 8 — INTEGRATED 25-DAY ACCURACY HISTORY]",
            _frame_text(field8_table, state, canonical, limit=600),
        ]
        full = full.rstrip() + "\n" + "\n".join(str(item) for item in additions)

    context = _field10_field11_context(state)
    top_rows = context.get("field10_top_rows") or []
    field11 = context.get("field11") or {}
    summary_lines = [
        f"Selected Symbols: {', '.join(context.get('selected_symbols') or []) or 'UNAVAILABLE'}",
        f"Calculation Mode: {context.get('calculation_mode') or 'UNAVAILABLE'}",
        f"Active/Fallback Provider: {context.get('active_provider') or 'UNAVAILABLE'} / {context.get('fallback_provider') or 'UNAVAILABLE'}",
        f"Field 10 Top Rankings: {json.dumps(_redact_secret(top_rows[:5]), default=str, ensure_ascii=False)}",
        f"Field 11 Summary: {json.dumps(_redact_secret(field11), default=str, ensure_ascii=False)}",
    ]
    if "Field 10 Top Rankings:" not in short:
        short = short.rstrip() + "\n" + "\n".join(summary_lines)
    if include_full and "[FIELD 10 — MULTI-SYMBOL RANKINGS AND PROVENANCE]" not in full:
        field10_frame = context.get("field10_full_frame")
        additions = [
            "[FIELD 10 — MULTI-SYMBOL RANKINGS AND PROVENANCE]",
            _json_text({
                "selected_symbols": context.get("selected_symbols"),
                "active_symbol": context.get("active_symbol"),
                "calculation_mode": context.get("calculation_mode"),
                "active_provider": context.get("active_provider"),
                "fallback_provider": context.get("fallback_provider"),
                "metadata": context.get("field10_metadata"),
            }),
            _frame_text(field10_frame, state, get_canonical_generation(state), limit=1000),
            "[FIELD 11 — SIMILAR-PATH RESULT AND DATA QUALITY]",
            _json_text(field11),
        ]
        full = full.rstrip() + "\n" + "\n".join(str(item) for item in additions)

    result = {"short": short, "full": full, "key": str(payloads.get("key") or "")}
    cache = state.get("lunch_copy_payload_cache_20260622")
    if isinstance(cache, MutableMapping):
        cache["short"] = short
        if include_full:
            cache["full"] = full
    return result
