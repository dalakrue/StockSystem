"""Settings-owned end-to-end run orchestration.

This module does not replace the existing ADX/Field 10 calculation engine. It
prepares one normalized market-data set, lets the protected engine calculate
once, then atomically publishes a shared canonical envelope.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import os
import sqlite3
import tempfile

import pandas as pd

from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH, SCHEMA_VERSION, migrate_deployment_schema
from core.data.market_data_orchestrator import PROVIDER_PRIORITY, provider_priority_for_state
from core.data.multi_symbol_scheduler import MultiSymbolScheduler
from core.generation_identity_20260707 import generation_id, numeric_generation
from core.runtime_selection_20260705 import (
    latest_completed_candle, load_runtime_preferences, normalize_symbols,
    normalize_timeframe, save_runtime_preferences, synchronize_runtime_selection,
)

MARKET_RESULTS_KEY = "market_data_run_results_20260705"
RUN_ID_KEY = "quota_safe_run_id_20260705"
SNAPSHOT_KEY = "quota_safe_canonical_snapshot_20260705"


def _jsonable(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return _jsonable(value.to_dict("records"))
    if isinstance(value, pd.Series):
        return _jsonable(value.to_list())
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    try:
        if hasattr(value, "item") and callable(value.item):
            scalar = value.item()
            if scalar is not value:
                return _jsonable(scalar)
    except Exception:
        pass
    if value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def prepare_market_data_for_run(
    state: MutableMapping[str, Any],
    *,
    run_id: str,
    selected_symbols: Sequence[Any] | None = None,
    timeframe: Any | None = None,
    bars: int | None = None,
    progress_callback: Any = None,
) -> dict[str, Any]:
    """Load exact candles for the configured GlobalSymbolContext universe.

    The caller may repeat the configured list for validation, but cannot create a
    parallel calculation universe.  This is an explicit load action, never a tab
    render or display-selection side effect.
    """
    migrate_deployment_schema(DEFAULT_DB_PATH)
    from core.global_symbol_context import (
        get_global_symbol_context, mark_universe_loading, publish_loaded_universe,
    )
    from core.field3_three_regime_engine import candle_hash, standardize_candles
    context = get_global_symbol_context(state, db_path=DEFAULT_DB_PATH, restore=True)
    if not context.universe_id or not context.configured_symbols:
        raise RuntimeError("NO_CONFIGURED_GLOBAL_SYMBOL_UNIVERSE")
    configured = list(context.configured_symbols)
    requested = normalize_symbols(selected_symbols or [], default_top10=False)
    if requested:
        unknown = [symbol for symbol in requested if symbol not in configured]
        if unknown:
            raise RuntimeError(
                "REQUESTED_SYMBOLS_NOT_IN_GLOBAL_CONFIGURED_UNIVERSE:" + ",".join(unknown)
            )
        # Selector 1/2/3 foreground loads are intentionally allowed to request a
        # strict subset of the configured top-30 universe. This keeps the global
        # selection authoritative while permitting sequential loading without
        # forcing every previously selected symbol through the provider again.
        selected = list(requested)
    else:
        selected = list(configured)
    tf = normalize_timeframe(timeframe or context.timeframe)
    if tf != context.timeframe:
        raise RuntimeError(f"TIMEFRAME_DOES_NOT_MATCH_GLOBAL_CONTEXT:{tf}!={context.timeframe}")
    mark_universe_loading(context.universe_id, state=state, db_path=DEFAULT_DB_PATH,
                          details={"run_id": run_id, "symbols": selected, "configured_symbols": configured,
                                   "request_scope": "SUBSET" if selected != configured else "FULL",
                                   "timeframe": tf})
    # Never shrink the persisted Settings universe merely because one selector
    # is being loaded. Runtime preferences stay on the complete canonical list.
    save_runtime_preferences(DEFAULT_DB_PATH, configured, tf)
    state[RUN_ID_KEY] = run_id
    if state.get("quota_safe_stagger_enabled_20260706"):
        state["super_quick_run_started_monotonic_20260706"] = __import__("time").monotonic()
    if callable(progress_callback):
        progress_callback({"overall_percent": 2.0, "current_symbol": selected[0], "current_stage": "Loading configured global universe"})
    from core.timeframe_window_contract_20260706 import required_candles
    requested_bars = int(bars or state.get("connector_bars") or 600)
    contract_bars = int(required_candles(tf, "higher"))
    effective_bars = max(requested_bars, contract_bars + max(12, contract_bars // 10))
    state["prepared_market_data_required_candles_20260706"] = contract_bars
    state["prepared_market_data_requested_bars_20260706"] = effective_bars
    scheduler = MultiSymbolScheduler(db_path=DEFAULT_DB_PATH, max_live_requests_per_window=7)
    report = scheduler.run(
        symbols=selected, timeframe=tf, state=state,
        active_symbol=selected[0],
        bars=effective_bars,
        run_id=run_id, force_live=bool(state.pop("market_connector_force_refresh_requested_20260702", False)),
        progress_callback=progress_callback,
    )
    results = report.get("results") if isinstance(report.get("results"), Mapping) else {}
    loaded_payloads: dict[str, Any] = {}
    failed_payloads: dict[str, Any] = {}
    for symbol in selected:
        raw = results.get(symbol) if isinstance(results.get(symbol), Mapping) else {}
        frame = standardize_candles(raw.get("frame"))
        result_tf = normalize_timeframe(raw.get("timeframe") or tf)
        if frame.empty or result_tf != tf or not bool(raw.get("ok", not frame.empty)):
            failed_payloads[symbol] = {
                "failure_code": str(raw.get("status") or "LOAD_FAILED"),
                "failure_message": str(raw.get("message") or raw.get("error") or "Exact symbol load did not complete"),
            }
            continue
        loaded_payloads[symbol] = {
            "provider": raw.get("provider") or raw.get("source") or "LOADER",
            "provider_symbol": raw.get("provider_symbol") or symbol,
            "candle_count": len(frame),
            "latest_completed_candle": frame["open_time"].iloc[-1].isoformat(),
            "candle_hash": candle_hash(frame),
            "data_quality_grade": raw.get("data_quality_grade") or ("A" if len(frame) >= contract_bars else "C"),
        }
    loaded_context = publish_loaded_universe(
        context.universe_id, loaded_payloads, failed_members=failed_payloads,
        state=state, db_path=DEFAULT_DB_PATH,
    )
    report = dict(report)
    report.update({
        "global_universe_id": loaded_context.universe_id,
        "global_generation": loaded_context.generation,
        "configured_symbols": list(loaded_context.configured_symbols),
        "requested_symbols": list(selected),
        "request_scope": "SUBSET" if selected != configured else "FULL",
        "loaded_symbols": list(loaded_context.loaded_symbols),
        "failed_symbols": dict(loaded_context.failed_symbols),
        "timeframe": loaded_context.timeframe,
    })
    state[MARKET_RESULTS_KEY] = report
    provider_plan = provider_priority_for_state(state)
    configured_active = str(provider_plan[0] if provider_plan else "UNCONFIGURED")
    configured_fallback = str(provider_plan[1] if len(provider_plan) > 1 else "LOCAL_VALID_CACHE")
    used_providers = [
        str(value.get("provider") or "").upper()
        for value in results.values()
        if isinstance(value, Mapping) and str(value.get("provider") or "").strip()
    ]
    state["active_market_provider_20260705"] = configured_active
    state["fallback_market_provider_20260705"] = configured_fallback
    state["actual_market_providers_used_20260708"] = list(dict.fromkeys(used_providers))
    state["actual_primary_provider_used_20260708"] = next(iter(used_providers), "NONE")
    state["selected_timeframe"] = tf
    state["timeframe"] = tf
    state["selected_symbols_for_run_20260705"] = list(loaded_context.loaded_symbols)
    state["latest_completed_candle_for_run_20260705"] = loaded_context.latest_completed_candle
    return report


def activate_prepared_symbol(state: MutableMapping[str, Any], symbol: str) -> dict[str, Any]:
    report = state.get(MARKET_RESULTS_KEY)
    report = report if isinstance(report, Mapping) else {}
    results = report.get("results") if isinstance(report.get("results"), Mapping) else {}
    result = results.get(symbol) if isinstance(results, Mapping) else None
    if not isinstance(result, Mapping):
        return {"ok": False, "status": "NOT_PREPARED", "symbol": symbol}
    frame = result.get("frame")
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        legacy = frame.copy()
        if "open_time" in legacy.columns:
            legacy["time"] = pd.to_datetime(legacy["open_time"], errors="coerce", utc=True)
        columns = [column for column in ("time", "open", "high", "low", "close", "volume") if column in legacy.columns]
        state["last_df"] = legacy.loc[:, columns].copy()
        state["source"] = str(result.get("provider") or "LOCAL_VALID_CACHE")
        state["connected"] = bool(result.get("ok"))
        state["last_connected_symbol"] = symbol
        state["last_connected_timeframe"] = str(result.get("timeframe") or state.get("timeframe") or "H4")
        state["last_connection_rows"] = int(len(legacy))
        state["last_connection_message"] = str(result.get("message") or "Prepared canonical market data")
    state["active_symbol_market_provenance_20260705"] = {
        key: value for key, value in result.items() if key != "frame"
    }
    return {key: value for key, value in result.items() if key != "frame"}


def _collect_news_macro(state: MutableMapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        from core.sentiment.news_orchestrator import NewsOrchestrator
        news = NewsOrchestrator(DEFAULT_DB_PATH).collect(state, force=False)
    except Exception as exc:
        news = {"ok": False, "status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    try:
        from core.fundamental.fred_macro_provider import FredMacroProvider
        macro = FredMacroProvider(DEFAULT_DB_PATH).collect(state, force=False)
    except Exception as exc:
        macro = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    state["shared_news_sentiment_20260705"] = news
    state["shared_macro_pressure_20260705"] = macro
    return news, macro


def _existing_canonical(state: Mapping[str, Any]) -> dict[str, Any]:
    for key in (
        "canonical_decision_result_20260617", "canonical_result_20260617",
        "last_valid_canonical_decision_result_20260617",
    ):
        value = state.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _safe_scalar(value: Any) -> Any:
    """Return a JSON-safe evidence value without manufacturing a replacement."""
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item") and callable(value.item):
        try:
            return _safe_scalar(value.item())
        except Exception:
            pass
    return value


def _first_evidence(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(key).strip().lower(): key for key in row}
    for name in names:
        key = lowered.get(name.strip().lower())
        if key is not None:
            value = _safe_scalar(row.get(key))
            if value is not None and str(value).strip().lower() not in {"", "nan", "none", "null"}:
                return value
    return None


def _frame_records_by_symbol(frame: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {}
    symbol_column = next((column for column in frame.columns if str(column).strip().lower() == "symbol"), None)
    if symbol_column is None:
        return {}
    records: dict[str, dict[str, Any]] = {}
    for raw in frame.to_dict("records"):
        symbol = str(raw.get(symbol_column) or "").upper().replace("/", "").replace("_", "")
        if symbol and symbol not in records:
            records[symbol] = {str(key): _safe_scalar(value) for key, value in raw.items()}
    return records


def _latest_table_records(conn: sqlite3.Connection, table: str, rank_column: str | None = None) -> dict[str, dict[str, Any]]:
    """Read the newest publication for a Field 10 evidence table, when present."""
    columns = {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
    if not columns or "symbol" not in columns:
        return {}
    where = ""
    params: tuple[Any, ...] = ()
    if "daily_snapshot_id" in columns:
        newest = conn.execute(
            f'SELECT daily_snapshot_id FROM "{table}" ORDER BY rowid DESC LIMIT 1'
        ).fetchone()
        if newest and newest[0]:
            where = " WHERE daily_snapshot_id=?"
            params = (newest[0],)
    elif "broker_day" in columns:
        newest = conn.execute(f'SELECT MAX(broker_day) FROM "{table}"').fetchone()
        if newest and newest[0]:
            where = " WHERE broker_day=?"
            params = (newest[0],)
    order = f' ORDER BY "{rank_column}" ASC' if rank_column and rank_column in columns else " ORDER BY rowid DESC"
    cursor = conn.execute(f'SELECT * FROM "{table}"{where}{order}', params)
    names = [str(item[0]) for item in cursor.description or []]
    records: dict[str, dict[str, Any]] = {}
    for values in cursor.fetchall():
        row = {names[index]: _safe_scalar(value) for index, value in enumerate(values)}
        symbol = str(row.get("symbol") or "").upper().replace("/", "").replace("_", "")
        if symbol and symbol not in records:
            records[symbol] = row
    return records


def _field10_evidence(state: MutableMapping[str, Any], manifest: Mapping[str, Any] | None) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Collect existing protected Field 10 outputs without recalculation or API work."""
    frames: dict[str, Any] = {}
    try:
        from core.multi_symbol_field10_20260701 import (
            FIELD10_DAILY_KEY, FIELD10_HOURLY_KEY, FIELD10_SUMMARY_KEY, load_field10_tables,
        )
        parent_run_id = str((manifest or {}).get("parent_run_id") or state.get("multi_symbol_parent_run_id_20260701") or "")
        loaded = load_field10_tables(state, parent_run_id=parent_run_id or None)
        frames.update(loaded if isinstance(loaded, Mapping) else {})
        frames.setdefault("summary", state.get(FIELD10_SUMMARY_KEY))
        frames.setdefault("daily", state.get(FIELD10_DAILY_KEY))
        frames.setdefault("hourly", state.get(FIELD10_HOURLY_KEY))
    except Exception as exc:
        frames["load_warning"] = f"{type(exc).__name__}: {str(exc)[:160]}"

    merged: dict[str, dict[str, Any]] = {}
    for frame_name in ("summary", "daily", "hourly"):
        for symbol, row in _frame_records_by_symbol(frames.get(frame_name)).items():
            merged.setdefault(symbol, {}).update({key: value for key, value in row.items() if value is not None})

    database_sources: dict[str, dict[str, dict[str, Any]]] = {}
    with sqlite3.connect(str(DEFAULT_DB_PATH), timeout=20) as conn:
        conn.execute("PRAGMA busy_timeout=12000")
        database_sources = {
            "final": _latest_table_records(conn, "field10_daily_final_multi_symbol_rank", "final_rank"),
            "daily": _latest_table_records(conn, "field10_daily_snapshot_symbol", "daily_rank"),
            "crowd": _latest_table_records(conn, "field10_daily_crowd_psychology_rank", "crowd_rank"),
            "session": _latest_table_records(conn, "field10_daily_session_entry_map", "session_rank"),
            "news": _latest_table_records(conn, "field10_daily_news_event_rank", "news_rank"),
            "utility": _latest_table_records(conn, "field10_rankings_20260705", "rank"),
        }
    # Later, more-specific publications take precedence while missing values are
    # inherited from the protected daily/hourly production tables.
    for source_name in ("daily", "session", "news", "crowd", "utility", "final"):
        for symbol, row in database_sources[source_name].items():
            merged.setdefault(symbol, {}).update({key: value for key, value in row.items() if value is not None})

    metadata = {
        "source_tables": [name for name, records in database_sources.items() if records],
        "frame_rows": {
            name: int(len(frame)) for name, frame in frames.items() if isinstance(frame, pd.DataFrame)
        },
    }
    if frames.get("load_warning"):
        metadata["load_warning"] = frames["load_warning"]
    return merged, metadata


def _provider_health_snapshot(report: Mapping[str, Any]) -> dict[str, Any]:
    providers = ["TWELVE_DATA", "MT5", "FINNHUB", "ALPHA_VANTAGE", "GDELT", "FRED"]
    health: dict[str, Any] = {provider: {"status": "UNKNOWN", "healthy": False} for provider in providers}
    with sqlite3.connect(str(DEFAULT_DB_PATH), timeout=20) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute("SELECT * FROM provider_health"):
            provider = str(row["provider"] or "").upper()
            if provider in health:
                health[provider] = {key: _safe_scalar(row[key]) for key in row.keys()}
        connection_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(api_connection_state)")}
        if connection_columns:
            for row in conn.execute("SELECT provider,configured,connected,last_success_at,last_failure_at,last_status,last_error_code,updated_at FROM api_connection_state"):
                provider = str(row[0] or "").upper()
                if provider in health:
                    health[provider].update({
                        "configured": bool(row[1]), "connected": bool(row[2]),
                        "connection_last_success_at": row[3], "connection_last_failure_at": row[4],
                        "connection_status": row[5], "connection_error_code": row[6], "connection_updated_at": row[7],
                    })
    health["twelve_data_quota"] = _jsonable(report.get("quota", {}))
    results = report.get("results") if isinstance(report.get("results"), Mapping) else {}
    health["fallback_activity"] = [
        {"symbol": symbol, "provider": data.get("provider"), "status": data.get("status")}
        for symbol, data in results.items()
        if isinstance(data, Mapping) and str(data.get("provider") or "") != "TWELVE_DATA"
    ]
    return health


def _add_identity_to_field10_frames(state: MutableMapping[str, Any], *, run_id: str, timeframe: str, selected: Sequence[str]) -> None:
    scope = ",".join(selected)
    for key in (
        "field10_multi_symbol_summary_20260701",
        "field10_daily_higher_regime_20260701",
        "field10_hourly_quality_20260701",
    ):
        frame = state.get(key)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            tagged = frame.copy()
            tagged["Canonical Run ID"] = run_id
            tagged["Canonical Timeframe"] = timeframe
            tagged["Canonical Symbol Scope"] = scope
            state[key] = tagged


def finalize_canonical_run(
    state: MutableMapping[str, Any],
    manifest: Mapping[str, Any] | None,
    *,
    run_id: str,
) -> dict[str, Any]:
    migrate_deployment_schema(DEFAULT_DB_PATH)
    report = state.get(MARKET_RESULTS_KEY)
    report = report if isinstance(report, Mapping) else {}
    from core.global_symbol_context import get_global_symbol_context
    global_context = get_global_symbol_context(state, db_path=DEFAULT_DB_PATH, restore=True)
    selected = list(global_context.loaded_symbols)
    timeframe = normalize_timeframe(global_context.timeframe)
    if not selected:
        raise RuntimeError("NO_LOADED_GLOBAL_SYMBOLS_FOR_FINALIZATION")
    from core.timeframe_window_contract_20260706 import evidence_contract, required_candles
    completed = str(state.get("latest_completed_candle_for_run_20260705") or latest_completed_candle(timeframe=timeframe).isoformat())
    news, macro = _collect_news_macro(state)
    legacy = _existing_canonical(state)
    broker_time = completed
    try:
        from core.shared_broker_time_20260622 import shared_broker_time_provider
        broker_clock = shared_broker_time_provider(
            state,
            canonical={
                **legacy,
                "symbol": selected[0] if selected else legacy.get("symbol"),
                "selected_symbols": list(selected),
                "timeframe": timeframe,
                "latest_completed_candle_time": completed,
            },
        )
        broker_time = str(
            broker_clock.get("shared_broker_time_iso")
            or broker_clock.get("broker_time_iso")
            or completed
        )
    except Exception:
        broker_time = completed
    generation = numeric_generation(
        legacy.get("calculation_generation") or legacy.get("generation") or legacy.get("generation_id")
        or state.get("canonical_calculation_generation_20260617")
        or state.get("successful_calculation_generation_20260617"),
        default=1,
    )
    created = datetime.now(timezone.utc)
    provider_results = report.get("results") if isinstance(report.get("results"), Mapping) else {}
    required_rows = int(required_candles(timeframe, "higher"))
    field10_rows, field10_evidence_metadata = _field10_evidence(state, manifest)
    per_symbol: dict[str, Any] = {}
    ranking_outputs: list[dict[str, Any]] = []
    for position, symbol in enumerate(selected, start=1):
        result = provider_results.get(symbol) if isinstance(provider_results, Mapping) else {}
        result = result if isinstance(result, Mapping) else {}
        available_rows = int(len(result.get("frame"))) if isinstance(result.get("frame"), pd.DataFrame) else 0
        coverage = evidence_contract(timeframe=timeframe, available=available_rows, required=required_rows)
        row = field10_rows.get(symbol, {})
        final_rank = _first_evidence(row, "final_rank", "rank", "daily_rank", "Rank", "Daily Rank")
        final_score = _first_evidence(row, "final_score", "score", "rank_score", "Rank Score", "institutional_score")
        less_risky_bias = _first_evidence(
            row, "final_less_risky_bias_to_hold", "less_risky_bias", "Less-Risky Bias", "Less Risky Bias"
        )
        transition_bias = _first_evidence(
            row, "transition_direction_6h", "session_bias", "technical_fundamental_bias", "higher_standard_bias"
        )
        full_day_bias = _first_evidence(
            row, "stable_daily_bias", "final_less_risky_bias_to_hold", "higher_standard_bias", "Higher-Standard Bias"
        )
        reliability = _first_evidence(
            row, "final_less_risky_bias_confidence", "reliability", "higher_reliability", "Higher Reliability", "provider_reliability"
        )
        uncertainty = _first_evidence(row, "uncertainty", "Uncertainty", "model_uncertainty")
        actionability = _first_evidence(
            row, "final_entry_permission", "trade_permission", "Trade Permission", "entry_permission", "eligibility_status"
        )
        technical_outputs = {
            "rank": _first_evidence(row, "technical_fundamental_rank", "technical_rank", "production_rank"),
            "score": _first_evidence(row, "technical_fundamental_score", "technical_score", "existing_rank_score"),
            "bias": _first_evidence(row, "technical_fundamental_bias", "higher_standard_bias", "Higher-Standard Bias"),
        }
        regime_outputs = {
            "higher_standard_regime": _first_evidence(row, "higher_standard_regime", "Higher Standard Regime"),
            "higher_standard_bias": _first_evidence(row, "higher_standard_bias", "Higher-Standard Bias"),
            "alpha": _first_evidence(row, "higher_alpha", "Alpha"),
            "delta": _first_evidence(row, "higher_delta", "Delta"),
        }
        session_outputs = {
            "rank": _first_evidence(row, "best_session_rank", "session_rank"),
            "current_session": _first_evidence(row, "current_session", "Current Session", "session_name"),
            "best_session_1": _first_evidence(row, "best_session_1"),
            "best_session_2": _first_evidence(row, "best_session_2"),
            "score": _first_evidence(row, "session_score", "session_priority", "Session Priority"),
            "bias": _first_evidence(row, "session_bias"),
        }
        expected_returns = {
            "1h": _first_evidence(row, "expected_return_1h", "expected_value_1h", "ev_target_1h", "EV Target 1H (%)"),
            "6h": _first_evidence(row, "expected_return_6h", "expected_value_6h", "Expected Value 6H (%)", "ev_target_6h", "EV Target 6H (%)"),
            "12h": _first_evidence(row, "expected_return_12h", "Expected Return 12H (%)", "expected_value_12h", "ev_target_12h", "EV Target 12H (%)"),
            "24h": _first_evidence(row, "expected_return_24h", "Expected Return 24H (%)", "expected_value_24h"),
        }
        transition_risks = {
            "1h": _first_evidence(row, "final_transition_bias_risk_1h", "transition_risk_1h"),
            "6h": _first_evidence(row, "final_transition_bias_risk_6h", "transition_risk_6h", "Transition Risk 6H (%)"),
            "12h": _first_evidence(row, "final_transition_bias_risk_12h", "transition_risk_12h"),
            "24h": _first_evidence(row, "final_transition_bias_risk_24h", "transition_risk_24h", "Transition Risk 24H"),
        }
        probability_expected_value = {
            "1h": _first_evidence(row, "probability_reach_expected_value_1h", "probability_reach_ev_1h", "Probability Reach EV 1H (%)"),
            "6h": _first_evidence(row, "probability_reach_expected_value_6h", "probability_reach_ev_6h", "Probability Reach EV 6H (%)"),
            "12h": _first_evidence(row, "probability_reach_expected_value_12h", "probability_reach_ev_12h", "Probability Reach EV 12H (%)"),
            "24h": _first_evidence(row, "probability_reach_expected_value_24h"),
        }
        sentiment_outputs = {
            "rank": _first_evidence(row, "news_sentiment_rank", "news_rank"),
            "bias": _first_evidence(row, "news_sentiment_bias", "sentiment_bias"),
            "score": _first_evidence(row, "sentiment_probability", "pair_direction_effect", "finnhub_news_sentiment_contribution"),
            "event_risk": _first_evidence(row, "event_risk_permission", "active_event_risk", "unexpected_situation_severity"),
        }
        crowd_outputs = {
            "rank": _first_evidence(row, "crowd_psychology_rank", "crowd_rank"),
            "score": _first_evidence(row, "crowd_psychology_score", "crowd_score"),
            "state": _first_evidence(row, "crowd_state"),
            "direction": _first_evidence(row, "crowd_direction", "crowd_less_risky_bias"),
            "confidence": _first_evidence(row, "crowd_confidence"),
        }
        warnings = [attempt for attempt in result.get("attempts", []) if isinstance(attempt, Mapping) and not attempt.get("ok")]
        if actionability in {"BLOCKED", "INSUFFICIENT", "NO TRADE", "UNAVAILABLE"}:
            reason = _first_evidence(row, "no_trade_reason", "rank_reason", "Rank Reason", "quality_reason")
            if reason:
                warnings.append({"category": "ACTIONABILITY", "message": reason})
        per_symbol[symbol] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "latest_completed_candle": result.get("latest_completed_candle") or _first_evidence(row, "completed_h1_candle", "completed_candle", "Completed Candle"),
            "required_candles": required_rows,
            "available_candles": available_rows,
            "coverage": coverage,
            "evidence_tier": coverage.get("Evidence Tier"),
            "candle_provider": result.get("provider"),
            "fallback_provider": result.get("fallback_provider"),
            "live_or_cached_status": result.get("status"),
            "data_age_seconds": result.get("data_age_seconds"),
            "data_completeness": result.get("data_quality_score") if result.get("data_quality_score") is not None else _first_evidence(row, "data_quality_score", "Data Quality Score", "evidence_completeness"),
            "data_freshness": _first_evidence(row, "data_freshness", "freshness_score"),
            "validation_status": result.get("validation_status") or _first_evidence(row, "validation_status", "Validation Status", "sample_complete_status"),
            "technical_outputs": technical_outputs,
            "regime_outputs": regime_outputs,
            "session_outputs": session_outputs,
            "expected_returns": expected_returns,
            "transition_risks": transition_risks,
            "probability_of_expected_value": probability_expected_value,
            "sentiment_outputs": sentiment_outputs,
            "macro_outputs": macro,
            "crowd_psychology": crowd_outputs,
            "uncertainty": uncertainty,
            "reliability": reliability,
            "less_risky_bias": less_risky_bias,
            "transition_bias": transition_bias,
            "full_day_bias": full_day_bias,
            "confidence": _first_evidence(row, "final_less_risky_bias_confidence", "crowd_confidence", "confidence"),
            "actionability_status": actionability,
            "final_rank": final_rank,
            "final_score": final_score,
            "warnings": warnings,
        }
        ranking_outputs.append({
            "symbol": symbol,
            "final_rank": final_rank,
            "final_score": final_score,
            "less_risky_bias": less_risky_bias,
            "transition_bias": transition_bias,
            "full_day_bias": full_day_bias,
            "confidence": per_symbol[symbol]["confidence"],
            "reliability": reliability,
            "actionability_status": actionability,
            "selected_order": position,
        })
    ranking_outputs.sort(
        key=lambda item: (
            item["final_rank"] is None,
            float(item["final_rank"]) if isinstance(item["final_rank"], (int, float)) else 10_000,
            item["selected_order"],
        )
    )
    snapshot = {
        "identity": {
            "run_id": run_id, "generation": generation,
            "generation_id": generation_id(legacy.get("generation_id") or generation, fallback_seed=run_id),
            "created_at": created.isoformat(), "expires_at": (created + timedelta(days=7)).isoformat(),
            "broker_time": broker_time, "latest_completed_candle": completed,
            "selected_symbols": selected, "timeframe": timeframe,
            "calculation_version": "quota-safe-multi-provider-20260705",
            "schema_version": SCHEMA_VERSION,
        },
        "provider_priority": list(PROVIDER_PRIORITY),
        "provider_health": _provider_health_snapshot(report),
        "per_symbol": per_symbol,
        "ranking_outputs": ranking_outputs,
        "field10_evidence_metadata": field10_evidence_metadata,
        "news_sentiment": {key: value for key, value in news.items() if key != "articles"},
        "macro": macro,
        "legacy_canonical": legacy,
        "field10_manifest": dict(manifest or {}),
    }
    json_payload = json.dumps(_jsonable(snapshot), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = sha256(json_payload.encode("utf-8")).hexdigest()
    snapshot["identity"]["snapshot_hash"] = digest
    json_payload = json.dumps(_jsonable(snapshot), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    with sqlite3.connect(str(DEFAULT_DB_PATH), timeout=20) as conn:
        conn.execute("PRAGMA busy_timeout=12000")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT OR REPLACE INTO canonical_snapshots(
               run_id,generation,selected_symbols_json,timeframe,latest_completed_candle,schema_version,
               calculation_version,snapshot_json,snapshot_hash,created_at,completed,broker_time,expires_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?)""",
            (
                run_id, generation, json.dumps(selected), timeframe, completed, SCHEMA_VERSION,
                "quota-safe-multi-provider-20260705", json_payload, digest, created.isoformat(),
                broker_time, snapshot["identity"]["expires_at"],
            ),
        )
        conn.execute(
            """INSERT OR REPLACE INTO calculation_runs(
               run_id,generation,selected_symbols_json,timeframe,latest_completed_candle,status,
               started_at,completed_at,canonical_snapshot_hash,error_code)
               VALUES(?,?,?,?,?,'COMPLETED',?,?,?,NULL)""",
            (run_id, generation, json.dumps(selected), timeframe, completed, created.isoformat(), created.isoformat(), digest),
        )
        conn.commit()
    state[SNAPSHOT_KEY] = snapshot
    state["canonical_run_id_20260617"] = run_id
    state["canonical_selected_symbols_20260705"] = list(selected)
    state["canonical_selected_timeframe_20260705"] = timeframe
    state["canonical_snapshot_hash_20260705"] = digest
    state["canonical_shared_run_identity_20260705"] = snapshot["identity"]
    _add_identity_to_field10_frames(state, run_id=run_id, timeframe=timeframe, selected=selected)
    # Add identity to legacy canonical mappings without replacing their
    # calculation outputs.
    for key in ("canonical_decision_result_20260617", "canonical_result_20260617"):
        value = state.get(key)
        if isinstance(value, Mapping):
            updated = dict(value)
            updated.update({
                "run_id": run_id, "timeframe": timeframe,
                "selected_symbols": list(selected),
                "latest_completed_candle_time": completed,
                "snapshot_hash": digest,
                "generation_id": snapshot["identity"]["generation_id"],
                "calculation_generation": generation,
            })
            state[key] = updated

    # Publish the new global generation only after every loaded child passed the
    # existing completion contract and its exact frame identity still matches.
    contract = manifest.get("completion_contract") if isinstance(manifest, Mapping) else None
    if str((manifest or {}).get("status") or "").upper() != "COMPLETED" or (isinstance(contract, Mapping) and not bool(contract.get("ok"))):
        raise RuntimeError("GLOBAL_PUBLICATION_BLOCKED_INCOMPLETE_CALCULATION")
    from core.field3_three_regime_engine import candle_hash, standardize_candles
    from core.global_symbol_context import publish_completed_generation
    completion_members: dict[str, Any] = {}
    exact_cutoffs: set[str] = set()
    for symbol in selected:
        raw = provider_results.get(symbol) if isinstance(provider_results.get(symbol), Mapping) else {}
        frame = standardize_candles(raw.get("frame"))
        if frame.empty:
            raise RuntimeError(f"GLOBAL_PUBLICATION_MISSING_EXACT_FRAME:{symbol}")
        actual_candle = frame["open_time"].iloc[-1].isoformat()
        exact_cutoffs.add(actual_candle)
        completion_members[symbol] = {
            "timeframe": timeframe,
            "latest_completed_candle": actual_candle,
            "source_data_hash": candle_hash(frame),
            "data_quality_grade": (per_symbol.get(symbol) or {}).get("data_quality", {}).get("grade") if isinstance((per_symbol.get(symbol) or {}).get("data_quality"), Mapping) else None,
        }
    if len(exact_cutoffs) != 1:
        raise RuntimeError("GLOBAL_PUBLICATION_MIXED_COMPLETED_CANDLE_CUTOFFS")
    exact_completed = next(iter(exact_cutoffs))
    if completed and exact_completed != completed:
        raise RuntimeError(f"GLOBAL_PUBLICATION_COMPLETED_CANDLE_MISMATCH:{exact_completed}!={completed}")
    published_context = publish_completed_generation(
        global_context.universe_id, completion_members,
        parent_run_id=run_id, snapshot_hash=digest,
        latest_completed_candle=exact_completed,
        calculation_depth=str((manifest or {}).get("calculation_depth") or state.get("settings_calculation_scope_20260625") or "FULL"),
        state=state, db_path=DEFAULT_DB_PATH,
    )
    snapshot["identity"].update({
        "global_universe_id": published_context.universe_id,
        "global_generation": published_context.generation,
        "global_publication_status": published_context.publication_status,
    })
    return snapshot


def execute_existing_multi_symbol_run(
    state: MutableMapping[str, Any],
    single_symbol_runner: Any,
    *,
    scope: str,
    progress_callback: Any,
    existing_runner: Any,
) -> dict[str, Any]:
    """Calculate only the exact loaded members of GlobalSymbolContext.

    No provider request is allowed here.  Loading is an explicit Settings action;
    calculation reuses the exact in-memory frames whose hashes match the database
    member publication.
    """
    from core.global_symbol_context import get_global_symbol_context, mark_universe_calculating
    from core.field3_three_regime_engine import candle_hash, standardize_candles
    context = get_global_symbol_context(state, db_path=DEFAULT_DB_PATH, restore=True)
    selected = list(context.loaded_symbols)
    if not context.universe_id or not selected:
        raise RuntimeError("NO_LOADED_GLOBAL_SYMBOL_UNIVERSE")
    prepared = state.get(MARKET_RESULTS_KEY)
    prepared = prepared if isinstance(prepared, Mapping) else {}
    results = prepared.get("results") if isinstance(prepared.get("results"), Mapping) else {}
    if normalize_timeframe(prepared.get("timeframe") or context.timeframe) != context.timeframe:
        raise RuntimeError("PREPARED_TIMEFRAME_DOES_NOT_MATCH_GLOBAL_CONTEXT")
    with sqlite3.connect(str(DEFAULT_DB_PATH), timeout=20) as conn:
        conn.row_factory = sqlite3.Row
        members = {str(r["symbol"]): r for r in conn.execute(
            "SELECT * FROM canonical_symbol_universe_member_v2 WHERE universe_id=?", (context.universe_id,)
        )}
    identity_errors: list[str] = []
    for symbol in selected:
        raw = results.get(symbol) if isinstance(results.get(symbol), Mapping) else None
        if not isinstance(raw, Mapping):
            identity_errors.append(f"MISSING_PREPARED_FRAME:{symbol}")
            continue
        frame = standardize_candles(raw.get("frame"))
        member = members.get(symbol)
        if frame.empty or member is None:
            identity_errors.append(f"MISSING_EXACT_DATA:{symbol}")
            continue
        if str(member["candle_hash"] or "") and candle_hash(frame) != str(member["candle_hash"]):
            identity_errors.append(f"SOURCE_DATA_HASH_MISMATCH:{symbol}")
        actual_candle = frame["open_time"].iloc[-1].isoformat()
        if str(member["latest_completed_candle"] or "") and actual_candle != str(member["latest_completed_candle"]):
            identity_errors.append(f"COMPLETED_CANDLE_MISMATCH:{symbol}")
    if identity_errors:
        raise RuntimeError(";".join(identity_errors))
    run_id = f"V10-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{os.urandom(4).hex()}"
    state[RUN_ID_KEY] = run_id
    state["selected_symbols_for_run_20260705"] = selected
    mark_universe_calculating(context.universe_id, state=state, db_path=DEFAULT_DB_PATH,
                              details={"run_id": run_id, "scope": scope, "symbols": selected})
    if callable(progress_callback):
        progress_callback({
            "overall_percent": 4.0, "current_symbol": selected[0],
            "current_stage": f"Reusing exact loaded evidence for {len(selected)} symbol(s)",
        })
    manifest = existing_runner(state, single_symbol_runner, scope=scope, progress_callback=progress_callback)
    manifest = dict(manifest or {})
    manifest["quota_safe_run_id"] = run_id
    manifest["provider_priority"] = list(PROVIDER_PRIORITY)
    manifest["calculation_reused_preloaded_data_20260707"] = True
    snapshot = finalize_canonical_run(state, manifest, run_id=run_id)
    manifest["canonical_snapshot_hash_20260705"] = snapshot["identity"]["snapshot_hash"]
    manifest["canonical_run_id_20260705"] = run_id
    return manifest


__all__ = [
    "MARKET_RESULTS_KEY", "RUN_ID_KEY", "SNAPSHOT_KEY",
    "prepare_market_data_for_run", "activate_prepared_symbol",
    "finalize_canonical_run", "execute_existing_multi_symbol_run",
]
