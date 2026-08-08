"""Connector refresh controls that remain separate from Run Calculation."""
from __future__ import annotations
from core.global_symbol_compat import set_legacy_calculation_symbol

import hashlib
import time
from typing import Any, Mapping, MutableMapping

import pandas as pd
import streamlit as st

from core.data_connectors import maybe_refresh, refresh_now


def _first_not_none(*values: Any) -> Any:
    """Return the first present value without evaluating tabular objects as booleans."""
    for value in values:
        if value is not None:
            return value
    return None


def _sequence_values(value: Any) -> list[Any]:
    """Return a plain list only for sequence-like state values, never tabular objects."""
    if value is None or isinstance(value, (str, bytes, bytearray, pd.DataFrame, pd.Series, pd.Index)):
        return []
    try:
        return list(value)
    except TypeError:
        return []


def _attempt_for(attempts: list[dict[str, Any]], provider: str) -> dict[str, Any]:
    wanted = str(provider or "").strip().upper()
    return next(
        (item for item in attempts if isinstance(item, Mapping) and str(item.get("provider") or "").upper() == wanted),
        {},
    )


def _preferred_provider_message(
    *, preferred: str, actual: str, attempt: Mapping[str, Any], success_message: str,
) -> str:
    preferred_name = preferred.replace("_", " ").title()
    actual_name = actual.replace("_", " ").title() if actual else "no provider"
    if actual == preferred:
        return str(attempt.get("message") or success_message or f"{preferred_name} supplied validated candles.")
    if not attempt and actual and actual != "NONE":
        return (
            f"Validated cached candles associated with {actual_name} were reused; "
            f"no live {preferred_name} candle request was required."
        )
    category = str(attempt.get("category") or "NOT_USED").upper()
    detail = str(attempt.get("message") or category).strip()
    if actual and actual != "NONE":
        return (
            f"{preferred_name} was attempted first but could not supply validated candles "
            f"({detail}). {actual_name} supplied the validated candle data."
        )
    return f"{preferred_name} could not supply validated candles ({detail}); no usable fallback was found."


def _source_signature(frame: Any, *, source: str, symbol: str, timeframe: str) -> str:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return hashlib.sha256(f"{source}|{symbol}|{timeframe}|EMPTY".encode()).hexdigest()[:24]
    columns = [c for c in ("time", "Time", "Datetime", "open", "high", "low", "close", "volume") if c in frame.columns]
    sample = frame.loc[:, columns].tail(32) if columns else frame.tail(32)
    digest = pd.util.hash_pandas_object(sample, index=True).values.tobytes()
    return hashlib.sha256(f"{source}|{symbol}|{timeframe}|{len(frame)}".encode() + digest).hexdigest()[:24]


def _quality(frame: Any) -> dict[str, Any]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {"rows": 0, "missing": "BLOCKED", "duplicates": "UNKNOWN", "latest_completed_h1": None}
    time_col = next((c for c in ("time", "Time", "Datetime", "DateTime", "Timestamp") if c in frame.columns), None)
    latest = None
    duplicates = 0
    if time_col:
        parsed = pd.to_datetime(frame[time_col], errors="coerce", utc=True)
        valid = parsed.dropna()
        latest = valid.max().isoformat() if not valid.empty else None
        duplicates = int(parsed.duplicated().sum())
    missing = int(frame.isna().sum().sum())
    return {
        "rows": int(len(frame)),
        "missing": "PASS" if missing == 0 else f"WARNING ({missing})",
        "duplicates": "PASS" if duplicates == 0 else f"WARNING ({duplicates})",
        "latest_completed_h1": latest,
    }


def _clear_source_dependent_presentation(state: MutableMapping[str, Any]) -> None:
    prefixes = (
        "lunch_bi_visual_cache", "lunch_visualization_export", "lunch_red_chart_alpha",
        "canonical_copy_", "canonical_export_", "ai_grounded_cache_", "ai_retrieval_",
        "history_search_result_", "temporary_dataframe_", "presentation_cache_20260621",
    )
    protected = ("canonical_result", "canonical_calculation", "history", "connector", "user_settings")
    for key in list(state.keys()):
        text = str(key)
        if any(token in text for token in protected):
            continue
        if text.startswith(prefixes):
            state.pop(key, None)
    try:
        from core.adaptive_presentation_cache_20260621 import clear_reconstructable
        clear_reconstructable(state)
    except Exception:
        pass


def refresh_data(
    state: MutableMapping[str, Any] | None = None,
    *,
    symbol_override: str | None = None,
    timeframe_override: str | None = None,
) -> dict[str, Any]:
    """Force the existing connector path without running the calculation engine."""
    state = state if state is not None else st.session_state
    before_generation = state.get("canonical_calculation_generation_20260617", state.get("calculation_generation"))
    before_canonical = _first_not_none(
        state.get("canonical_result_20260617"),
        state.get("canonical_result"),
    )
    started = time.perf_counter()
    try:
        from core.symbol_universe_20260629 import apply_symbol_selection, normalize_instrument
        requested_symbol = normalize_instrument(symbol_override or state.get("symbol", "EURUSD"))
        requested_timeframe = str(timeframe_override or state.get("timeframe", "H1") or "H1").upper()
        apply_symbol_selection(state, requested_symbol, reason="refresh_data")
        state["timeframe"] = requested_timeframe
        # Every explicit refresh passes through the quota-safe provider
        # orchestrator. During a Settings run the current normalized candle set
        # is already persisted, so this becomes a local canonical-cache read and
        # does not consume another API credit.
        from core.data.market_data_orchestrator import MarketDataOrchestrator
        market_result = MarketDataOrchestrator().fetch(
            symbol=requested_symbol,
            timeframe=requested_timeframe,
            state=state,
            bars=int(state.get("connector_bars", 600) or 600),
            run_id=str(state.get("quota_safe_run_id_20260705") or state.get("multi_symbol_parent_run_id_20260701") or ""),
            force_live=bool(state.pop("explicit_connector_refresh_20260705", False)),
        )
        normalized = market_result.frame
        frame = pd.DataFrame()
        if isinstance(normalized, pd.DataFrame) and not normalized.empty:
            frame = normalized.copy()
            if "open_time" in frame.columns:
                frame["time"] = pd.to_datetime(frame["open_time"], errors="coerce", utc=True)
            keep = [column for column in ("time", "open", "high", "low", "close", "volume") if column in frame.columns]
            frame = frame.loc[:, keep]
        ok = bool(market_result.ok)
        source = str(market_result.provider or "LOCAL_VALID_CACHE")
        message = str(market_result.message)
        provenance = market_result.to_dict(include_frame=False)
        state["active_symbol_market_provenance_20260705"] = provenance
        raw_attempts = provenance.get("attempts")
        attempts = list(raw_attempts) if isinstance(raw_attempts, list) else []
        active_provider = str(market_result.provider or "").upper()
        finnhub_attempt = _attempt_for(attempts, "FINNHUB")
        finnhub_ok = bool(finnhub_attempt.get("ok")) or (
            bool(market_result.ok) and active_provider == "FINNHUB"
        )
        state["finnhub_data_connected"] = finnhub_ok
        state["finnhub_data_last_message"] = _preferred_provider_message(
            preferred="FINNHUB", actual=active_provider, attempt=finnhub_attempt,
            success_message=str(market_result.message or ""),
        )
        twelve_attempt = _attempt_for(attempts, "TWELVE_DATA")
        twelve_ok = bool(twelve_attempt.get("ok")) or (
            bool(market_result.ok) and active_provider == "TWELVE_DATA"
        )
        state["twelve_data_connected"] = twelve_ok
        state["twelve_data_last_message"] = str(
            twelve_attempt.get("message")
            or twelve_attempt.get("category")
            or (market_result.message if twelve_ok else "Twelve Data was not required or did not supply candles.")
            or ""
        )
        fallback_reason = ""
        if bool(market_result.ok) and active_provider != "FINNHUB":
            if finnhub_attempt:
                upstream_category = str(finnhub_attempt.get("category") or "UNAVAILABLE").strip().upper()
                fallback_reason = f"FINNHUB_CANDLE_UNAVAILABLE ({upstream_category})"
            elif str(market_result.status or "").upper() in {"CACHED_VALID", "STALE_VALID"}:
                fallback_reason = "VALIDATED_LOCAL_CACHE_REUSED"
            else:
                fallback_reason = "FALLBACK_PROVIDER_USED"
        state["preferred_market_provider_20260708"] = "FINNHUB"
        state["actual_market_provider_used_20260708"] = active_provider or "NONE"
        state["market_provider_fallback_reason_20260708"] = fallback_reason
        state["market_connection_outcome_20260708"] = (
            "CONNECTED" if bool(market_result.ok) and active_provider == "FINNHUB"
            else "CONNECTED_WITH_FALLBACK" if bool(market_result.ok)
            else "ERROR"
        )
        quality = _quality(frame)
        signature = _source_signature(frame, source=str(source), symbol=requested_symbol, timeframe=requested_timeframe)
        old_signature = state.get("source_data_signature_20260621")
        state["source_data_signature_20260621"] = signature
        state["source_data_quality_20260621"] = quality
        state["last_manual_refresh_20260621"] = time.time()
        state["last_manual_refresh_message_20260621"] = str(message)
        state["last_connected_symbol"] = requested_symbol
        state["last_connected_timeframe"] = requested_timeframe
        state["last_connection_rows"] = int(quality.get("rows", 0) or 0)
        state["last_connection_message"] = str(message)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            state["last_df"] = frame
            state["source"] = str(source)
            state["connected"] = bool(ok)
        else:
            state["connected"] = False
            state["source"] = str(source or "DISCONNECTED")
            state["last_connection_error"] = str(message)
        state["dependent_calculations_stale_20260621"] = bool(ok and signature != old_signature)
        state["canonical_display_stale_20260621"] = bool(ok and signature != old_signature)
        # Explicitly preserve the last completed immutable result.
        if before_canonical is not None:
            state.setdefault("canonical_result_20260617", before_canonical)
        if before_generation is not None:
            state.setdefault("canonical_calculation_generation_20260617", before_generation)
        _clear_source_dependent_presentation(state)
        status = "SUCCESS" if ok and quality["rows"] > 0 else "WARNING" if ok else "FAILURE"
        result = {
            "status": status, "ok": bool(ok), "source": source, "message": message,
            "symbol": requested_symbol, "timeframe": requested_timeframe,
            "source_signature": signature, "source_changed": signature != old_signature,
            "provider_attempts": attempts,
            "selected_api_source": str(state.get("connector_mode") or "twelve_pool").lower(),
            "preferred_provider": "FINNHUB",
            "active_provider": active_provider or source,
            "actual_provider": active_provider or source,
            "fallback_reason": fallback_reason,
            "connection_state": state.get("market_connection_outcome_20260708"),
            "finnhub_data_connected": finnhub_ok,
            "twelve_data_connected": twelve_ok,
            "calculation_marked_stale": bool(state["dependent_calculations_stale_20260621"]),
            "preserved_generation": before_generation, "quality": quality,
            "wall_seconds": round(time.perf_counter() - started, 4),
        }
    except Exception as exc:
        state["market_connection_outcome_20260708"] = "ERROR"
        result = {
            "status": "FAILURE", "ok": False, "message": f"{type(exc).__name__}: {exc}",
            "preserved_generation": before_generation,
            "wall_seconds": round(time.perf_counter() - started, 4),
        }
    state["last_refresh_result_20260621"] = result
    return result


def run_deferred_refresh():
    """Restore credentials, validated candles and connection status without network I/O."""
    try:
        from core.connectors.credential_vault import restore_into_state
        restored = restore_into_state(st.session_state)
    except Exception:
        restored = {}

    cache_rows = 0
    cache_source = ""
    try:
        from core.data.candle_repository import CandleRepository
        from core.runtime_selection_20260705 import normalize_symbol, normalize_timeframe

        selected = _sequence_values(st.session_state.get("multi_symbol_selected_20260701"))
        symbol = normalize_symbol(
            st.session_state.get("multi_symbol_main_symbol_20260702")
            or (selected[0] if selected else st.session_state.get("symbol") or "EURUSD")
        )
        timeframe = normalize_timeframe(st.session_state.get("timeframe") or "H1")
        cached = CandleRepository().load(
            symbol,
            timeframe,
            limit=int(st.session_state.get("connector_bars", 600) or 600),
            completed_only=True,
        )
        if isinstance(cached, pd.DataFrame) and not cached.empty:
            legacy = cached.copy()
            legacy["time"] = pd.to_datetime(legacy["open_time"], errors="coerce", utc=True)
            keep = [column for column in ("time", "open", "high", "low", "close", "volume") if column in legacy.columns]
            st.session_state["last_df"] = legacy.loc[:, keep].copy()
            cache_rows = int(len(legacy))
            cache_source = str(legacy.iloc[-1].get("provider") or "LOCAL_VALID_CACHE")
            st.session_state["source"] = cache_source
            st.session_state["connected"] = True
            set_legacy_calculation_symbol(st.session_state, symbol, connector=True)
            st.session_state["timeframe"] = timeframe
            st.session_state["last_connection_rows"] = cache_rows
            st.session_state["last_connection_message"] = "Validated local candle cache restored; no API credit used."
            try:
                from core.connector_state_machine_20260621 import succeed
                succeed(
                    st.session_state,
                    "market_connector_20260621",
                    f"Validated cache restored: {symbol} {timeframe}, {cache_rows:,} candles. Refresh Main Feed for a new live request.",
                )
            except Exception:
                pass
    except Exception as exc:
        st.session_state["deferred_cache_restore_error_20260705"] = f"{type(exc).__name__}: {str(exc)[:160]}"

    persisted_connections: dict[str, dict[str, Any]] = {}
    try:
        from core.connectors.credential_vault import status as credential_status
        persisted_connections = {
            str(row.get("provider") or "").upper(): dict(row)
            for row in credential_status()
            if str(row.get("provider") or "").upper() in {"FINNHUB", "TWELVE_DATA"}
        }
    except Exception:
        persisted_connections = {}
    for provider, prefix in (("FINNHUB", "finnhub"), ("TWELVE_DATA", "twelve")):
        persisted = persisted_connections.get(provider, {})
        st.session_state[f"{prefix}_data_connected"] = bool(
            persisted.get("connected") and cache_rows and cache_source.upper() == provider
        )
        if persisted.get("last_status") and not st.session_state.get(f"{prefix}_data_last_message"):
            st.session_state[f"{prefix}_data_last_message"] = str(persisted.get("last_status"))
        if persisted.get("last_success_at"):
            st.session_state[f"{prefix}_data_last_success_at"] = str(persisted.get("last_success_at"))

    st.session_state["deferred_auto_refresh_reason"] = (
        "Connector configuration and validated local candles were restored without a network request. "
        "Use Connect or Refresh only when a new live candle download is required."
    )
    st.session_state["deferred_connector_restore_20260705"] = {
        "credentials": restored,
        "cache_rows": cache_rows,
        "cache_source": cache_source,
    }


__all__ = ["refresh_data", "run_deferred_refresh"]
