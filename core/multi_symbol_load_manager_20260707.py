"""Explicit load-first workflow for the three Settings multi-symbol groups.

The Load button owns all provider/cache collection and validates enough genuine
selected-timeframe history before a symbol is admitted to a calculation run.
The three calculation buttons then reuse only that validated in-memory report;
they never silently fetch or borrow another symbol's candles.
"""
from __future__ import annotations
from core.global_symbol_compat import set_legacy_calculation_symbol, set_legacy_configured_symbols

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
import copy
import json
import sqlite3
import time
import uuid

import pandas as pd

LOAD_RECORDS_KEY = "multi_symbol_load_records_20260707"
CANONICAL_GROUP = "CANONICAL"
CANONICAL_SELECTED_KEY = "canonical_selected_symbols"
CANONICAL_LOADED_KEY = "canonical_loaded_symbols"
CANONICAL_LOAD_RECORD_KEY = "canonical_symbol_load_record_20260708"
CANONICAL_RANKING_SYMBOLS_KEY = "canonical_ranking_symbols"
CANONICAL_RANKING_TIMEFRAME_KEY = "canonical_ranking_timeframe"
CANONICAL_SYMBOL_LOAD_STATUS_KEY = "canonical_symbol_load_status"
CANONICAL_SYMBOL_CANDLES_KEY = "canonical_symbol_candles"
CANONICAL_PROVIDER_TRACE_KEY = "canonical_provider_trace"
CANONICAL_LAST_LOAD_RUN_ID_KEY = "canonical_last_load_run_id"
MAX_CANONICAL_SYMBOLS = 30
REQUIRE_EXPLICIT_LOAD_KEY = "require_explicit_multi_symbol_load_20260707"
LOADED_RUN_ACTIVE_KEY = "multi_symbol_loaded_run_active_20260707"
LAST_LOAD_KEY = "multi_symbol_last_load_20260707"
SELECTOR_KEY_ASSIGNMENT_STATE_KEY = "selector_key_assignment_20260708"
SELECTOR_WORKER_STATE_KEY = "selector_owned_twelve_worker_state_20260708"
SELECTOR_REQUEST_LEDGER_KEY = "selector_owned_twelve_request_ledger_20260708"
ASSIGNED_TWELVE_KEY_STATE_KEY = "selector_owned_twelve_assigned_key_20260708"
ASSIGNED_SELECTOR_STATE_KEY = "selector_owned_twelve_active_selector_20260708"
SELECTOR_TWELVE_ONLY_STATE_KEY = "selector_owned_twelve_only_20260708"
EMERGENCY_CROSS_KEY_STATE_KEY = "selector_owned_twelve_emergency_cross_key_enabled_20260708"
SELECTOR_KEY_MAP = {"FIRST": "TWELVE_KEY_1", "SECOND": "TWELVE_KEY_2", "THIRD": "TWELVE_DATA_KEY_POOL"}


@dataclass(frozen=True)
class SelectorKeyAssignment:
    selector_1_key: str = "TWELVE_KEY_1"
    selector_2_key: str = "TWELVE_KEY_2"
    selector_3_key: str = "TWELVE_DATA_KEY_POOL"

    def key_for_group(self, group: Any) -> str:
        group_name = str(group or "").strip().upper()
        if group_name == "FIRST":
            return self.selector_1_key
        if group_name == "SECOND":
            return self.selector_2_key
        if group_name == "THIRD":
            return self.selector_3_key
        return "TWELVE_DATA_KEY_POOL"


_GROUP_TO_SCOPE = {"FIRST": "LUNCH_CORE", "SECOND": "QUICK", "THIRD": "FULL", CANONICAL_GROUP: "QUICK"}
_SCOPE_TO_GROUP = {value: key for key, value in _GROUP_TO_SCOPE.items()}


def group_symbol_limit(group: Any) -> int:
    group_name = str(group or "").strip().upper()
    if group_name == CANONICAL_GROUP:
        return MAX_CANONICAL_SYMBOLS
    try:
        from core.multi_symbol_run_groups_20260706 import group_symbol_limit as configured_limit
        return int(configured_limit(group))
    except Exception:
        return 6


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")


def normalize_symbols(values: Any, *, limit: int | None = None) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Sequence):
        values = []
    result: list[str] = []
    for value in values:
        symbol = _normalize_symbol(value)
        if symbol and symbol not in result:
            result.append(symbol)
        if limit is not None and len(result) >= max(1, int(limit)):
            break
    return result


def is_valid_candle_df(df: Any, min_rows: int = 50, allow_stale: bool = False) -> bool:
    """Validate an OHLC candle frame without Boolean-evaluating pandas objects."""
    if df is None:
        return False
    if not isinstance(df, pd.DataFrame):
        return False
    if df.empty:
        return False
    required_cols = ["open", "high", "low", "close"]
    for col in required_cols:
        if col not in df.columns:
            return False
    if len(df) < int(min_rows) and not allow_stale:
        return False
    if df[required_cols].isna().all().any():
        return False
    return True


def first_valid_df(*dfs: Any) -> pd.DataFrame:
    """Choose the first valid DataFrame without using df in a truth-value test."""
    for df in dfs:
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            return df
    return pd.DataFrame()


def get_canonical_ranking_symbols(state: Mapping[str, Any] | None = None) -> list[str]:
    """Read Selector 1/2/3 state and return one deduplicated 30-symbol universe."""
    state_map = state if isinstance(state, Mapping) else {}
    try:
        from core.multi_symbol_run_groups_20260706 import FIRST_GROUP_KEY, SECOND_GROUP_KEY, THIRD_GROUP_KEY
        selector_1 = state_map.get("multi_symbol_selector_1", state_map.get(FIRST_GROUP_KEY, []))
        selector_2 = state_map.get("multi_symbol_selector_2", state_map.get(SECOND_GROUP_KEY, []))
        selector_3 = state_map.get("multi_symbol_selector_3", state_map.get(THIRD_GROUP_KEY, []))
    except Exception:
        selector_1 = state_map.get("multi_symbol_selector_1", [])
        selector_2 = state_map.get("multi_symbol_selector_2", [])
        selector_3 = state_map.get("multi_symbol_selector_3", [])
    combined: list[Any] = []
    for values in (selector_1, selector_2, selector_3):
        if isinstance(values, str):
            combined.append(values)
        elif isinstance(values, Sequence):
            combined.extend(list(values))
    return normalize_symbols(combined, limit=MAX_CANONICAL_SYMBOLS)


def canonical_universe_from_groups(configured: Mapping[str, Any] | None, *, limit: int = MAX_CANONICAL_SYMBOLS) -> list[str]:
    """Deduplicate Selector 1/2/3 into one authoritative 30-symbol universe."""
    configured = configured if isinstance(configured, Mapping) else {}
    ordered: list[Any] = []
    for group in ("FIRST", "SECOND", "THIRD"):
        values = configured.get(group)
        if isinstance(values, str):
            ordered.append(values)
        elif isinstance(values, Sequence):
            ordered.extend(list(values))
    return normalize_symbols(ordered, limit=limit)


def publish_canonical_universe(state: MutableMapping[str, Any], symbols: Any, timeframe: Any) -> list[str]:
    """Publish the Settings-selected symbol universe as the only selection source.

    Loaded/cache frames are kept separately; this function never replaces the
    selected symbols with a loaded-only subset.  A selector/timeframe change
    clears stale visible/export/copy outputs through the additive current-result
    synchronizer.
    """
    selected = normalize_symbols(symbols, limit=MAX_CANONICAL_SYMBOLS)
    tf = str(timeframe or state.get("timeframe") or state.get("selected_timeframe") or "H4").strip().upper() or "H4"
    try:
        from core.current_result_sync_20260708 import sync_settings_source_of_truth
        sync_settings_source_of_truth(state, selected, tf, reason="publish_canonical_universe")
    except Exception:
        state[CANONICAL_SELECTED_KEY] = list(selected)
        state[CANONICAL_RANKING_SYMBOLS_KEY] = list(selected)
        state["canonical_selected_symbols_20260705"] = list(selected)
        set_legacy_configured_symbols(state, list(selected))
        state["selected_symbols_for_run_20260705"] = list(selected)
        state[CANONICAL_RANKING_TIMEFRAME_KEY] = tf
        state["selected_timeframe"] = tf
        state["settings_timeframe"] = tf
        state["timeframe"] = tf
        if selected:
            state["lunch_display_symbol_20260702"] = selected[0]
    try:
        from core.global_symbol_context import configure_universe
        context = configure_universe(selected, tf, state=state)
        state["global_symbol_universe_id_v2"] = context.universe_id
    except Exception as exc:
        state["global_symbol_configure_warning_v2"] = f"{type(exc).__name__}: {exc}"
    return selected


def _publish_loaded_to_global_context(
    state: MutableMapping[str, Any], requested: Any, loaded: Any, failed: Any,
    results: Mapping[str, Any] | None, timeframe: str,
) -> None:
    """Bridge the existing loader into the canonical database authority."""
    try:
        from core.global_symbol_context import configure_universe, publish_loaded_universe
        from core.field3_three_regime_engine import candle_hash, standardize_candles
        requested_symbols = normalize_symbols(requested, limit=MAX_CANONICAL_SYMBOLS)
        context = configure_universe(requested_symbols, timeframe, state=state)
        payloads: dict[str, Any] = {}
        result_map = results if isinstance(results, Mapping) else {}
        for symbol in normalize_symbols(loaded, limit=None):
            raw = result_map.get(symbol) if isinstance(result_map.get(symbol), Mapping) else {}
            frame = standardize_candles(raw.get("frame"))
            if frame.empty:
                continue
            payloads[symbol] = {
                "provider": raw.get("provider") or raw.get("source") or "LOADER",
                "provider_symbol": raw.get("provider_symbol") or symbol,
                "candle_count": len(frame), "latest_completed_candle": frame["open_time"].iloc[-1].isoformat(),
                "candle_hash": candle_hash(frame),
                "data_quality_grade": _data_quality_grade(len(frame), raw.get("status")),
            }
        failed_payload = {symbol: {"failure_code": "LOAD_FAILED", "failure_message": "Exact symbol load did not complete"}
                          for symbol in normalize_symbols(failed, limit=None)}
        publish_loaded_universe(context.universe_id, payloads, failed_members=failed_payload, state=state)
    except Exception as exc:
        state["global_symbol_loaded_publish_warning_v2"] = f"{type(exc).__name__}: {exc}"


def _data_quality_grade(rows: int, status: Any = "") -> str:
    status_text = str(status or "").upper()
    if rows >= 200:
        return "A_IDEAL_200_PLUS"
    if rows >= 100:
        return "B_GOOD_100_PLUS"
    if rows >= 50:
        return "C_MINIMUM_USABLE_50_PLUS"
    if rows >= 25:
        return "D_EMERGENCY_USABLE_25_PLUS"
    if "STALE" in status_text or "CACHE" in status_text:
        return "D_EMERGENCY_CACHE"
    return "F_NO_USABLE_DATA"


def group_for_scope(scope: Any) -> str:
    return _SCOPE_TO_GROUP.get(str(scope or "QUICK").strip().upper(), "SECOND")


def scope_for_group(group: Any) -> str:
    return _GROUP_TO_SCOPE.get(str(group or "SECOND").strip().upper(), "QUICK")


def selection_signature(symbols: Any, timeframe: Any) -> str:
    selected = normalize_symbols(symbols)
    tf = str(timeframe or "H4").strip().upper() or "H4"
    return sha256((tf + "|" + "|".join(selected)).encode("utf-8")).hexdigest()[:24]


def _records(state: Mapping[str, Any]) -> dict[str, Any]:
    value = state.get(LOAD_RECORDS_KEY)
    return dict(value) if isinstance(value, Mapping) else {}


def _restore_group_record_from_database(
    state: Mapping[str, Any], group_name: str, selected: Sequence[str], timeframe: str,
) -> dict[str, Any] | None:
    """Rebuild a load record from persisted audit + exact candle repository.

    Browser/session restarts previously lost the in-memory report even though the
    validated candles and load audit were already in SQLite.  This restore path
    uses only the same symbol/timeframe rows and reruns the normal validation;
    it never pads data or borrows another symbol's frame.
    """
    try:
        from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH, migrate_deployment_schema
        from core.data.candle_repository import CandleRepository
        from core.timeframe_window_contract_20260706 import required_candles, minimum_calculation_candles
        migrate_deployment_schema(DEFAULT_DB_PATH)
        signature = selection_signature(selected, timeframe)
        with sqlite3.connect(str(DEFAULT_DB_PATH), timeout=15) as conn:
            conn.execute("PRAGMA busy_timeout=15000")
            row = conn.execute(
                """SELECT load_id,scope,requested_symbols_json,loaded_symbols_json,
                          failed_symbols_json,validation_json,status,loaded_at
                   FROM multi_symbol_load_audit_20260707
                   WHERE group_name=? AND timeframe=? AND selection_signature=?
                   ORDER BY loaded_at DESC LIMIT 1""",
                (group_name, timeframe, signature),
            ).fetchone()
        if not row:
            return None
        requested = normalize_symbols(json.loads(row[2] or "[]"), limit=None)
        audited_loaded = normalize_symbols(json.loads(row[3] or "[]"), limit=None)
        try:
            audited_validations = json.loads(row[5] or "{}")
        except Exception:
            audited_validations = {}
        required_rows = int(required_candles(timeframe, "higher"))
        minimum_rows = int(minimum_calculation_candles(timeframe, "higher"))
        repository = CandleRepository(DEFAULT_DB_PATH)
        results: dict[str, Any] = {}
        validations: dict[str, Any] = {}
        loaded: list[str] = []
        failed: list[str] = []
        for symbol in requested:
            frame = repository.load(
                symbol, timeframe,
                limit=max(required_rows + max(24, required_rows // 5), 600),
                completed_only=True,
            )
            latest = (
                pd.to_datetime(frame.get("open_time"), errors="coerce", utc=True).max()
                if isinstance(frame, pd.DataFrame) and not frame.empty and "open_time" in frame.columns
                else pd.NaT
            )
            payload = {
                "ok": isinstance(frame, pd.DataFrame) and not frame.empty,
                "symbol": symbol,
                "timeframe": timeframe,
                "frame": frame,
                "provider": "LOCAL_VALID_CACHE",
                "provider_symbol": symbol,
                "status": "RESTORED_EXACT_LOAD_AUDIT",
                "message": "Restored exact-symbol selected-timeframe candles from SQLite load audit.",
                "latest_completed_candle": None if pd.isna(latest) else pd.Timestamp(latest).isoformat(),
                "validation_status": "VALID",
                "run_id": str(row[0]),
                "recovery_provenance": "PERSISTED_LOAD_AUDIT_AND_EXACT_CANDLES",
            }
            validation = _validate_result(payload, symbol=symbol, timeframe=timeframe, required_rows=required_rows)
            validations[symbol] = {**dict(audited_validations.get(symbol) or {}), **validation}
            if validation.get("ok"):
                loaded.append(symbol)
                results[symbol] = payload
            else:
                failed.append(symbol)
        record = {
            "group": group_name,
            "scope": str(row[1] or scope_for_group(group_name)),
            "load_id": str(row[0]),
            "loaded_at": str(row[7] or ""),
            "timeframe": timeframe,
            "selection_signature": signature,
            "requested_symbols": requested,
            "loaded_symbols": loaded,
            "failed_symbols": failed,
            "required_candles": required_rows,
            "minimum_calculation_candles": minimum_rows,
            "validations": validations,
            "status": "READY" if loaded and not failed else "PARTIAL_READY" if loaded else "FAILED",
            "restored_from_database": True,
            "report": {
                "run_id": str(row[0]), "load_id": str(row[0]), "timeframe": timeframe,
                "results": results, "requested_symbols": requested, "loaded_symbols": loaded,
                "unresolved_symbols": failed, "required_candles_per_symbol": required_rows,
                "minimum_calculation_candles_per_symbol": minimum_rows,
                "complete": bool(loaded) and not failed, "load_only": True,
                "restored_from_database": True,
            },
        }
        if isinstance(state, MutableMapping):
            records = _records(state)
            records[group_name] = record
            state[LOAD_RECORDS_KEY] = records
        return record
    except Exception as exc:
        if isinstance(state, MutableMapping):
            state["multi_symbol_load_restore_error_20260707"] = f"{type(exc).__name__}: {exc}"
        return None


def _result_rows(payload: Mapping[str, Any]) -> int:
    frame = payload.get("frame")
    return int(len(frame)) if isinstance(frame, pd.DataFrame) else 0


def _latest_loaded_price_time(payload: Mapping[str, Any]) -> tuple[float | None, str | None]:
    frame = payload.get("frame") if isinstance(payload, Mapping) else None
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None, None
    time_col = next((column for column in ("open_time", "time", "datetime", "broker_open_time") if column in frame.columns), None)
    close_col = next((column for column in ("close", "Close", "c") if column in frame.columns), None)
    if time_col is None or close_col is None:
        return None, None
    working = frame[[time_col, close_col]].copy()
    working[time_col] = pd.to_datetime(working[time_col], errors="coerce", utc=True)
    working[close_col] = pd.to_numeric(working[close_col], errors="coerce")
    working = working.dropna(subset=[time_col, close_col]).sort_values(time_col)
    if working.empty:
        return None, None
    row = working.iloc[-1]
    return float(row[close_col]), pd.Timestamp(row[time_col]).isoformat()


def _canonical_provider_used(value: Any) -> str:
    provider = str(value or "UNKNOWN").strip().upper()
    if provider in {"FCS", "FCS_API", "FCSAPI", "FCS_API_MAIN", "FCS_ACCESS_KEY", "FCS_MAIN"}:
        return "FCS_API_MAIN"
    if provider in {"TWELVE_KEY_1", "KEY_1", "TWELVE_DATA_KEY_1", "TWELVE_API_KEY_1"}:
        return "TWELVE_KEY_1"
    if provider in {"TWELVE_KEY_2", "KEY_2", "TWELVE_DATA_KEY_2", "TWELVE_API_KEY_2"}:
        return "TWELVE_KEY_2"
    if provider in {"TWELVE_DATA_KEY_POOL", "TWELVE_KEY_POOL", "TWELVE_DATA_POOL", "TWELVE_DATA", "TWELVE", "TWELVEDATA", "TWELVE_DATA_FALLBACK"}:
        return "TWELVE_DATA_KEY_POOL"
    if provider in {"LOCAL_VALID_CACHE", "LOCAL_CACHE", "CACHE", "SQLITE"}:
        return "LOCAL_CACHE"
    if provider in {"STALE_VALID", "LAST_KNOWN_VALID_CACHE", "EMERGENCY_CACHE"}:
        return "LAST_KNOWN_VALID_CACHE"
    return provider or "UNKNOWN"


def _validate_result(
    payload: Mapping[str, Any], *, symbol: str, timeframe: str, required_rows: int
) -> dict[str, Any]:
    target_timeframe = str(timeframe or "H4").strip().upper() or "H4"
    frame = payload.get("frame")
    rows = _result_rows(payload)
    from core.timeframe_window_contract_20260706 import evidence_contract
    coverage = evidence_contract(timeframe=target_timeframe, available=rows, required=required_rows)
    spacing: dict[str, Any]
    try:
        from core.timeframe_window_contract_20260706 import TIMEFRAME_SECONDS, validate_timeframe_spacing
        spacing = validate_timeframe_spacing(frame, timeframe=target_timeframe) if isinstance(frame, pd.DataFrame) else {
            "ok": False, "status": "NO_FRAME", "rows": rows,
        }
        # Equities, indices and some metals have legitimate exchange-closure
        # gaps that are not exact timeframe multiples. They remain valid when
        # every observed gap is at least one selected-timeframe candle; only
        # duplicate/sub-timeframe rows are unsafe for Field 3/Field 10.
        if isinstance(frame, pd.DataFrame) and not spacing.get("ok") and rows > 1:
            time_col = next((c for c in frame.columns if str(c).strip().lower() in {"open_time", "time", "datetime", "timestamp"}), None)
            if time_col is not None:
                stamps = pd.to_datetime(frame[time_col], errors="coerce", utc=True).dropna().sort_values().drop_duplicates()
                diffs = stamps.diff().dt.total_seconds().dropna()
                expected = float(TIMEFRAME_SECONDS.get(target_timeframe, TIMEFRAME_SECONDS["H4"]))
                if not diffs.empty and bool((diffs >= expected - 90.0).all()):
                    spacing = {
                        **spacing,
                        "ok": True,
                        "status": "PASS_WITH_MARKET_CLOSURE_GAPS",
                        "minimum_spacing_seconds": float(diffs.min()),
                        "median_spacing_seconds": float(diffs.median()),
                    }
    except Exception as exc:
        spacing = {"ok": False, "status": "SPACING_VALIDATION_ERROR", "error": f"{type(exc).__name__}: {exc}"}
    payload_symbol = _normalize_symbol(payload.get("symbol") or symbol)
    payload_timeframe = str(payload.get("timeframe") or timeframe).strip().upper()
    exact_identity = payload_symbol == _normalize_symbol(symbol) and payload_timeframe == target_timeframe
    provider_ok = bool(payload.get("ok"))
    provider_name = str(payload.get("provider") or payload.get("source") or "UNKNOWN").strip().upper()
    validation_status = str(payload.get("validation_status") or "").strip().upper()
    # A genuine exact-symbol local repository frame remains admissible when a
    # transient provider attempt failed after the cache was read.  We never
    # accept another symbol/timeframe, generated rows, or an unvalidated frame.
    trusted_exact_cache = bool(
        exact_identity
        and provider_name in {
            "LOCAL_VALID_CACHE", "CACHE", "SQLITE",
            "TWELVE_DATA_KEY_POOL", "TWELVE_DATA_FALLBACK", "TWELVE_DATA", "MT5", "FINNHUB", "ALPHA_VANTAGE",
        }
        and validation_status in {"VALID", "PASS", "CACHED_VALID", "STALE_VALID"}
    )
    # A symbol is admitted only when it meets the shared selected-timeframe
    # minimum calculation contract.  This gate is intentionally stricter than
    # the old 25-candle emergency path because Field 3 must independently fit
    # Lower, Middle and Higher regimes without synthetic padding or borrowing.
    try:
        from core.timeframe_window_contract_20260706 import minimum_calculation_candles
        minimum_rows = int(minimum_calculation_candles(target_timeframe, "higher"))
    except Exception:
        minimum_rows = min(int(required_rows), 100)
    enough_rows = rows >= minimum_rows
    full_history = rows >= int(required_rows)
    valid = exact_identity and (provider_ok or trusted_exact_cache) and enough_rows and bool(spacing.get("ok"))
    if not exact_identity:
        reason = f"IDENTITY_MISMATCH: expected {symbol}/{timeframe}, received {payload_symbol}/{payload_timeframe}"
    elif not (provider_ok or trusted_exact_cache):
        reason = str(payload.get("status") or payload.get("message") or "PROVIDER_NOT_READY")
    elif not enough_rows:
        reason = f"INSUFFICIENT_LOCAL_HISTORY_BELOW_MINIMUM: {rows}/{minimum_rows} {target_timeframe} candles"
    elif not spacing.get("ok"):
        reason = str(spacing.get("status") or "INVALID_TIMEFRAME_SPACING")
    else:
        # Keep the public readiness token stable. Full/adaptive detail is
        # already carried by ``calculation_mode`` and ``full_history``.
        reason = "READY" if full_history else f"READY_ADAPTIVE_PARTIAL_HISTORY: {rows}/{required_rows}"

    combined_error_parts: list[str] = []
    for key in ("status", "message", "error"):
        value = payload.get(key)
        if value is not None:
            combined_error_parts.append(str(value))
    combined_error = " ".join(combined_error_parts).upper()
    if valid:
        failure_code = None
        retryable = False
    elif not exact_identity:
        failure_code = "IDENTITY_MISMATCH"
        retryable = False
    elif "RATE" in combined_error or "429" in combined_error or "QUOTA" in combined_error:
        failure_code = "PROVIDER_RATE_LIMIT"
        retryable = True
    elif "TIMEFRAME" in combined_error and ("UNSUPPORTED" in combined_error or "NOT SUPPORT" in combined_error):
        failure_code = "TIMEFRAME_NOT_SUPPORTED"
        retryable = False
    elif "SYMBOL" in combined_error and ("UNSUPPORTED" in combined_error or "NOT SUPPORT" in combined_error or "INVALID" in combined_error):
        failure_code = "SYMBOL_NOT_SUPPORTED"
        retryable = False
    elif rows <= 0:
        failure_code = "NO_GENUINE_CANDLES"
        retryable = True
    elif not enough_rows:
        failure_code = "BELOW_MODULE_MINIMUM"
        retryable = True
    elif not spacing.get("ok"):
        failure_code = "VALIDATION_WARNING"
        retryable = True
    else:
        failure_code = "VALIDATION_WARNING"
        retryable = True
    attempts_raw = payload.get("attempts")
    attempts = list(attempts_raw) if isinstance(attempts_raw, Sequence) and not isinstance(attempts_raw, (str, bytes)) else []
    attempt_categories = {
        str(item.get("category") or "").strip().upper()
        for item in attempts if isinstance(item, Mapping)
    }
    key_pool_attempted = any(_canonical_provider_used(item.get("provider")) == "TWELVE_DATA_KEY_POOL" for item in attempts if isinstance(item, Mapping))
    twelve_attempted = key_pool_attempted
    key_pool_errors = [
        str(item.get("message") or item.get("category") or "").strip()
        for item in attempts
        if isinstance(item, Mapping) and _canonical_provider_used(item.get("provider")) == "TWELVE_DATA_KEY_POOL" and not bool(item.get("ok"))
    ]
    twelve_errors = [
        str(item.get("message") or item.get("category") or "").strip()
        for item in attempts
        if isinstance(item, Mapping) and _canonical_provider_used(item.get("provider")) == "TWELVE_DATA_KEY_POOL" and not bool(item.get("ok"))
    ]
    actual_provider = str(payload.get("provider") or payload.get("source") or "UNKNOWN").strip().upper()
    provider_symbol_value = payload.get("provider_symbol")
    provider_symbol_text = str(provider_symbol_value) if provider_symbol_value is not None else symbol
    load_duration_value = payload.get("load_duration_seconds")
    if load_duration_value is None:
        load_duration_value = payload.get("elapsed_seconds")
    try:
        load_duration = max(0.0, float(load_duration_value)) if load_duration_value is not None else 0.0
    except (TypeError, ValueError):
        load_duration = 0.0
    if load_duration <= 0.0:
        load_duration = sum(
            max(0.0, float(item.get("load_duration_seconds") or 0.0))
            for item in attempts if isinstance(item, Mapping)
        )
    failure_category = None if valid else (
        "RATE_LIMITED" if failure_code == "PROVIDER_RATE_LIMIT" or "RATE_LIMITED" in attempt_categories else
        "TEMPORARY_ERROR" if "TEMPORARY_PROVIDER_ERROR" in attempt_categories else
        "PROVIDER_UNAVAILABLE" if (
            failure_code in {"TIMEFRAME_NOT_SUPPORTED", "SYMBOL_NOT_SUPPORTED"}
            or bool(attempt_categories & {"PERMANENT_CLIENT_ERROR", "RUN_CIRCUIT_OPEN"})
        ) else
        "EMPTY" if failure_code == "NO_GENUINE_CANDLES" else
        "INVALID_DATA" if failure_code in {"IDENTITY_MISMATCH", "VALIDATION_WARNING", "BELOW_MODULE_MINIMUM"} else
        "TEMPORARY_ERROR" if retryable else "FAILED"
    )
    persisted_value = payload.get("persisted")
    if persisted_value is None:
        persisted_value = any(
            isinstance(item, Mapping)
            and isinstance(item.get("persistence"), Mapping)
            and int(item["persistence"].get("inserted") or 0) + int(item["persistence"].get("duplicates") or 0) > 0
            for item in attempts
        ) or actual_provider == "LOCAL_VALID_CACHE"
    latest_price, latest_candle_time = _latest_loaded_price_time(payload)
    canonical_provider_used = _canonical_provider_used(actual_provider)
    actual_key_alias = str(payload.get("actual_key_name") or payload.get("provider_key_alias") or "").strip().upper()
    if canonical_provider_used == "TWELVE_DATA_KEY_POOL" and actual_key_alias in {"TWELVE_KEY_1", "TWELVE_KEY_2"}:
        canonical_provider_used = actual_key_alias
    request_attempted = any(
        isinstance(item, Mapping)
        and _canonical_provider_used(item.get("provider")) in {"TWELVE_DATA_KEY_POOL", "TWELVE_KEY_1", "TWELVE_KEY_2"}
        and bool(item.get("request_sent", item.get("ok", False)))
        for item in attempts
    )
    quota_blocked = any(
        isinstance(item, Mapping)
        and _canonical_provider_used(item.get("provider")) in {"TWELVE_DATA_KEY_POOL", "TWELVE_KEY_1", "TWELVE_KEY_2"}
        and (str(item.get("category") or "").upper() == "RATE_LIMITED" or bool(item.get("quota_blocked")))
        for item in attempts
    )
    circuit_skipped = any(
        isinstance(item, Mapping)
        and str(item.get("category") or "").upper() == "RUN_CIRCUIT_OPEN"
        and not bool(item.get("request_sent", False))
        for item in attempts
    )
    assigned_key = str(payload.get("assigned_key") or actual_key_alias or "").strip().upper()
    return {
        "ok": valid,
        "status": "COMPLETED" if valid else str(failure_category or "FAILED"),
        "rows": rows,
        "genuine_rows": rows,
        "required_rows": int(required_rows),
        "minimum_rows": int(minimum_rows),
        "full_history": bool(full_history),
        "calculation_mode": "FULL_HISTORY" if full_history else "EMERGENCY_ADAPTIVE_HISTORY" if valid and rows < 50 else "ADAPTIVE_PARTIAL_HISTORY" if valid else "BELOW_EMERGENCY_MINIMUM",
        "coverage": coverage,
        "evidence_tier": str(coverage.get("Evidence Tier") or "NO_SELECTED_TIMEFRAME_HISTORY"),
        "preferred_provider": "TWELVE_DATA_KEY_POOL",
        "provider": canonical_provider_used,
        "actual_provider": canonical_provider_used,
        "provider_symbol": provider_symbol_text,
        "provider_key_alias": str(payload.get("provider_key_alias") or payload.get("actual_key_name") or ""),
        "actual_key_name": actual_key_alias,
        "assigned_key": assigned_key,
        "request_attempted": bool(request_attempted),
        "quota_blocked": bool(quota_blocked),
        "circuit_skipped": bool(circuit_skipped),
        "provider_status": str(payload.get("status") or ""),
        "key_pool_attempted": bool(key_pool_attempted),
        "key_pool_error": "; ".join([item for item in key_pool_errors if item])[:500],
        "twelve_attempted": bool(twelve_attempted),
        "twelve_error": "; ".join([item for item in twelve_errors if item])[:500],
        "cache_used": bool(_canonical_provider_used(actual_provider) in {"LOCAL_CACHE", "LAST_KNOWN_VALID_CACHE"}),
        "provider_trace": {
            "provider_used": canonical_provider_used,
            "assigned_key": assigned_key,
            "request_attempted": bool(request_attempted),
            "quota_blocked": bool(quota_blocked),
            "circuit_skipped": bool(circuit_skipped),
            "key_pool_attempted": bool(key_pool_attempted),
            "key_pool_error": "; ".join([item for item in key_pool_errors if item])[:500],
            "twelve_attempted": bool(twelve_attempted),
            "twelve_error": "; ".join([item for item in twelve_errors if item])[:500],
        },
        "exact_identity": exact_identity,
        "trusted_exact_cache": trusted_exact_cache,
        "reason": reason,
        "failure_code": failure_code,
        "failure_category": failure_category,
        "failure_reason": reason,
        "retryable": retryable,
        "attempt_count": len(attempts),
        "load_duration_seconds": round(load_duration, 3),
        "persisted": bool(persisted_value),
        "validation_state": "PASS" if valid else "FAILED",
        "latest_completed_candle": payload.get("latest_completed_candle") or latest_candle_time,
        "latest_price": latest_price,
        "latest_candle_time": latest_candle_time or payload.get("latest_completed_candle"),
        "data_quality": _data_quality_grade(rows, actual_provider if valid else failure_category),
        "api_status": ("USING_CACHE" if valid and actual_provider in {"LOCAL_VALID_CACHE", "CACHE", "SQLITE"} else "COMPLETED" if valid else str(failure_category or "FAILED")),
        "error_message": "" if valid else str(reason or failure_category or "FAILED"),
        "spacing": spacing,
    }


def _persist_load_audit(record: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    """Persist selector choices and load validation without serializing frames."""
    from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH, migrate_deployment_schema
    from core.multi_symbol_run_groups_20260706 import save_group_preferences

    migrate_deployment_schema(DEFAULT_DB_PATH)
    save_group_preferences(DEFAULT_DB_PATH, state)
    metadata = {key: value for key, value in record.items() if key != "report"}
    with sqlite3.connect(str(DEFAULT_DB_PATH), timeout=15) as conn:
        conn.execute("PRAGMA busy_timeout=15000")
        requested_symbols = normalize_symbols(record.get("requested_symbols") or [], limit=None)
        loaded_symbols = normalize_symbols(record.get("loaded_symbols") or [], limit=None)
        failed_symbols = normalize_symbols(record.get("failed_symbols") or [], limit=None)
        conn.execute(
            """INSERT OR REPLACE INTO multi_symbol_load_audit_20260707(
                   load_id,group_name,scope,timeframe,selection_signature,
                   requested_symbols_json,loaded_symbols_json,failed_symbols_json,
                   validation_json,status,loaded_at,requested_count,loaded_count,
                   failed_count,accepted_live_capacity
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(record.get("load_id") or ""), str(record.get("group") or ""),
                str(record.get("scope") or ""), str(record.get("timeframe") or ""),
                str(record.get("selection_signature") or ""),
                json.dumps(requested_symbols), json.dumps(loaded_symbols), json.dumps(failed_symbols),
                json.dumps(metadata.get("validations") or {}, default=str),
                str(record.get("status") or "UNKNOWN"), str(record.get("loaded_at") or ""),
                len(requested_symbols), len(loaded_symbols), len(failed_symbols), 7,
            ),
        )
        validations = metadata.get("validations") if isinstance(metadata.get("validations"), Mapping) else {}
        for position, symbol in enumerate(requested_symbols, start=1):
            validation = validations.get(symbol) if isinstance(validations.get(symbol), Mapping) else {}
            provider_used = _canonical_provider_used(validation.get("provider") or validation.get("actual_provider"))
            api_status = str(validation.get("api_status") or ("COMPLETED" if bool(validation.get("ok")) else "FAILED"))
            rows_loaded = int(validation.get("rows") or 0)
            load_time = str(record.get("loaded_at") or "")
            error_message = str(validation.get("error_message") or ("" if bool(validation.get("ok")) else validation.get("reason") or ""))
            conn.execute(
                """INSERT INTO multi_symbol_symbol_sync_20260707(
                       group_name,symbol,timeframe,load_id,selector_position,rows_loaded,
                       required_rows,minimum_rows,provider,calculation_mode,validation_status,
                       validation_reason,selection_signature,updated_at,provider_used,api_status,
                       candle_count,latest_price,latest_candle_time,data_quality,load_time,error_message,run_id
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(group_name,symbol,timeframe) DO UPDATE SET
                       load_id=excluded.load_id,selector_position=excluded.selector_position,
                       rows_loaded=excluded.rows_loaded,required_rows=excluded.required_rows,
                       minimum_rows=excluded.minimum_rows,provider=excluded.provider,
                       calculation_mode=excluded.calculation_mode,
                       validation_status=excluded.validation_status,
                       validation_reason=excluded.validation_reason,
                       selection_signature=excluded.selection_signature,updated_at=excluded.updated_at,
                       provider_used=excluded.provider_used,api_status=excluded.api_status,
                       candle_count=excluded.candle_count,latest_price=excluded.latest_price,
                       latest_candle_time=excluded.latest_candle_time,data_quality=excluded.data_quality,
                       load_time=excluded.load_time,error_message=excluded.error_message,run_id=excluded.run_id""",
                (
                    str(record.get("group") or ""), symbol, str(record.get("timeframe") or ""),
                    str(record.get("load_id") or ""), position, rows_loaded,
                    int(validation.get("required_rows") or record.get("required_candles") or 0),
                    int(validation.get("minimum_rows") or record.get("minimum_calculation_candles") or 0),
                    provider_used, str(validation.get("calculation_mode") or "BELOW_MINIMUM_HISTORY"),
                    "PASS" if bool(validation.get("ok")) else "FAILED",
                    str(validation.get("reason") or ""), str(record.get("selection_signature") or ""),
                    load_time, provider_used, api_status, rows_loaded, validation.get("latest_price"),
                    validation.get("latest_candle_time") or validation.get("latest_completed_candle"),
                    str(validation.get("data_quality") or ("USABLE" if bool(validation.get("ok")) else "FAILED")),
                    load_time, error_message, str(record.get("load_id") or ""),
                ),
            )
            conn.execute(
                """INSERT OR REPLACE INTO forex_symbol_load_cache_20260708(
                       symbol,timeframe,provider_used,api_status,candle_count,latest_price,
                       latest_candle_time,data_quality,load_time,error_message,run_id
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    symbol, str(record.get("timeframe") or ""), provider_used, api_status, rows_loaded,
                    validation.get("latest_price"),
                    validation.get("latest_candle_time") or validation.get("latest_completed_candle"),
                    str(validation.get("data_quality") or ("USABLE" if bool(validation.get("ok")) else "FAILED")),
                    load_time, error_message, str(record.get("load_id") or ""),
                ),
            )
        conn.commit()



def _state_get(state: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    try:
        return state.get(key, default)
    except Exception:
        return default


def _normalize_key_alias(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"1", "KEY1", "KEY_1", "TWELVE_DATA_KEY_1", "TWELVE_API_KEY_1"}:
        return "TWELVE_KEY_1"
    if text in {"2", "KEY2", "KEY_2", "TWELVE_DATA_KEY_2", "TWELVE_API_KEY_2"}:
        return "TWELVE_KEY_2"
    if text in {"TWELVE_KEY_1", "TWELVE_KEY_2", "TWELVE_DATA_KEY_POOL", "CACHE_OR_FALLBACK"}:
        return text
    return "CACHE_OR_FALLBACK"


def _normalize_selector_group(selector_id: Any) -> str:
    text = str(selector_id or "").strip().upper().replace("SELECTOR", "").replace(" ", "")
    if text in {"1", "FIRST", "ONE"}:
        return "FIRST"
    if text in {"2", "SECOND", "TWO"}:
        return "SECOND"
    if text in {"3", "THIRD", "THREE"}:
        return "THIRD"
    if text == CANONICAL_GROUP:
        return CANONICAL_GROUP
    return text or "SECOND"


def selector_key_assignment(state: Mapping[str, Any] | None = None) -> SelectorKeyAssignment:
    state_map = state if isinstance(state, Mapping) else {}
    raw = state_map.get(SELECTOR_KEY_ASSIGNMENT_STATE_KEY)
    if isinstance(raw, Mapping):
        return SelectorKeyAssignment(
            selector_1_key=_normalize_key_alias(raw.get("selector_1_key") or raw.get("FIRST") or "TWELVE_KEY_1"),
            selector_2_key=_normalize_key_alias(raw.get("selector_2_key") or raw.get("SECOND") or "TWELVE_KEY_2"),
            selector_3_key=_normalize_key_alias(raw.get("selector_3_key") or raw.get("THIRD") or "TWELVE_DATA_KEY_POOL"),
        )
    return SelectorKeyAssignment()


def clear_circuit_breaker_for_symbols(symbols: Any, timeframe: Any, provider: Any = "TWELVE_DATA_KEY_POOL") -> dict[str, Any]:
    """Clear foreground symbol-level circuit state for exact failed symbol/timeframe.

    Manual foreground retry must make a fresh provider decision. This function
    clears only the local symbol-provider circuit flags; Twelve Data per-key
    minute counters and cooldowns are deliberately not reset.
    """
    selected = normalize_symbols(symbols, limit=None)
    tf = str(timeframe or "H4").strip().upper() or "H4"
    providers = [provider] if isinstance(provider, str) else list(provider or [])
    normalized_providers: list[str] = []
    for item in providers or ["TWELVE_DATA_KEY_POOL"]:
        name = _canonical_provider_used(item)
        if name in {"TWELVE_KEY_1", "TWELVE_KEY_2"}:
            name = "TWELVE_DATA_KEY_POOL"
        if name not in normalized_providers:
            normalized_providers.append(name)
    cleared = 0
    errors: list[str] = []
    try:
        from core.data.symbol_level_provider_registry_20260708 import SymbolLevelProviderRegistry
        from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
        registry = SymbolLevelProviderRegistry(DEFAULT_DB_PATH)
        for symbol in selected:
            for provider_name in normalized_providers:
                try:
                    cleared += int(registry.reset_circuit(provider=provider_name, symbol=symbol, timeframe=tf) or 0)
                except Exception as exc:
                    errors.append(f"{symbol}/{provider_name}: {type(exc).__name__}: {exc}")
    except Exception as exc:
        errors.append(f"registry: {type(exc).__name__}: {exc}")
    return {"symbols": selected, "timeframe": tf, "providers": normalized_providers, "cleared": cleared, "errors": errors}


def _fresh_cache_payload(symbol: str, timeframe: str, *, required_rows: int) -> dict[str, Any] | None:
    try:
        from core.data.candle_repository import CandleRepository
        from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
        repository = CandleRepository(DEFAULT_DB_PATH)
        frame = repository.load(symbol, timeframe, limit=max(int(required_rows) + 24, 600), completed_only=True)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            return None
        latest = pd.to_datetime(frame.get("open_time"), errors="coerce", utc=True).max() if "open_time" in frame.columns else pd.NaT
        return {
            "ok": True,
            "symbol": symbol,
            "timeframe": timeframe,
            "frame": frame,
            "provider": "LOCAL_VALID_CACHE",
            "provider_symbol": symbol,
            "status": "READY_FROM_CACHE",
            "message": "Fresh/validated exact symbol+timeframe cache reused before spending Twelve Data credit.",
            "latest_completed_candle": None if pd.isna(latest) else pd.Timestamp(latest).isoformat(),
            "validation_status": "VALID",
            "request_attempted": False,
            "cache_used": True,
        }
    except Exception:
        return None


def _retryable_symbols_from_status(status: Mapping[str, Any]) -> list[str]:
    retryable_states = {
        "FAILED_EXPLICIT", "FAILED_NO_DATA", "INSUFFICIENT", "PENDING", "RUN_CIRCUIT_OPEN",
        "PROVIDER_NONE", "FAILED", "FAILED_VALIDATION", "EMPTY", "EMPTY_RESPONSE", "API_ERROR",
        "INVALID_DATA", "TEMPORARY_ERROR", "PROVIDER_UNAVAILABLE", "QUOTA_COOLDOWN",
    }
    validations = status.get("validations") if isinstance(status.get("validations"), Mapping) else {}
    requested = normalize_symbols(status.get("requested_symbols") or [], limit=None)
    failed = normalize_symbols(status.get("failed_symbols") or [], limit=None)
    retry: list[str] = []
    for symbol in requested:
        evidence = validations.get(symbol) if isinstance(validations.get(symbol), Mapping) else {}
        if bool(evidence.get("ok")):
            continue
        final_state = str(evidence.get("final_state") or evidence.get("failure_category") or evidence.get("failure_code") or evidence.get("status") or "").upper()
        provider = _canonical_provider_used(evidence.get("provider") or evidence.get("actual_provider") or "NONE")
        rows = int(evidence.get("rows") or evidence.get("genuine_rows") or 0)
        data_quality = str(evidence.get("data_quality") or "").upper()
        if symbol in failed or final_state in retryable_states or rows == 0 or provider in {"NONE", "UNKNOWN", ""} or data_quality.startswith("F_"):
            retry.append(symbol)
    return retry


def _append_request_ledger_from_record(state: MutableMapping[str, Any], record: Mapping[str, Any], *, assigned_key: str, attempted_symbols: Sequence[str]) -> None:
    ledger = state.get(SELECTOR_REQUEST_LEDGER_KEY)
    if not isinstance(ledger, list):
        ledger = []
    validations = record.get("validations") if isinstance(record.get("validations"), Mapping) else {}
    now = datetime.now(timezone.utc).isoformat()
    attempted_set = set(normalize_symbols(attempted_symbols, limit=None))
    for symbol in normalize_symbols(record.get("requested_symbols") or [], limit=None):
        evidence = validations.get(symbol) if isinstance(validations.get(symbol), Mapping) else {}
        provider = _canonical_provider_used(evidence.get("provider") or evidence.get("actual_provider") or "NONE")
        request_attempted = bool(evidence.get("request_attempted")) and symbol in attempted_set
        ledger.append({
            "symbol": symbol,
            "timeframe": str(record.get("timeframe") or "H4").upper(),
            "selector": str(record.get("group") or ""),
            "assigned_key": assigned_key,
            "request_attempted": request_attempted,
            "request_time": now,
            "status": str(evidence.get("status") or record.get("status") or "UNKNOWN"),
            "error": str(evidence.get("error_message") or evidence.get("failure_reason") or evidence.get("reason") or ""),
            "provider_used": provider,
            "credit_spent_estimate": 1 if request_attempted and provider in {"TWELVE_KEY_1", "TWELVE_KEY_2", "TWELVE_DATA_KEY_POOL"} else 0,
        })
    # Keep the newest 500 ledger rows in session; SQLite symbol_load_ledger keeps
    # durable request audit for actual provider attempts.
    state[SELECTOR_REQUEST_LEDGER_KEY] = ledger[-500:]


def _cooldown_seconds_from_snapshot(item: Mapping[str, Any]) -> int:
    reset = item.get("cooldown_reset_time")
    if not reset:
        return 0
    try:
        target = datetime.fromisoformat(str(reset).replace("Z", "+00:00"))
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        return max(0, int((target - datetime.now(timezone.utc)).total_seconds()))
    except Exception:
        return 0


def _update_selector_worker_state(state: MutableMapping[str, Any], group_name: str, symbols: Sequence[str], timeframe: str, key_alias: str, record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    try:
        from core.twelve_data_key_pool import TwelveDataKeyPool
        pool_snapshot = TwelveDataKeyPool.from_state(state).status_snapshot()
    except Exception:
        pool_snapshot = {}
    key_info = pool_snapshot.get(key_alias, {}) if isinstance(pool_snapshot, Mapping) else {}
    status = loaded_group_status(state, group_name, symbols, timeframe)
    validations = status.get("validations") if isinstance(status.get("validations"), Mapping) else {}
    quota_skipped: list[str] = []
    circuit_skipped: list[str] = []
    last_error = str(key_info.get("failure_reason") or "")
    for symbol, evidence in validations.items():
        if not isinstance(evidence, Mapping):
            continue
        if evidence.get("quota_blocked"):
            quota_skipped.append(str(symbol))
        if evidence.get("circuit_skipped"):
            circuit_skipped.append(str(symbol))
        if not bool(evidence.get("ok")) and not last_error:
            last_error = str(evidence.get("failure_reason") or evidence.get("reason") or evidence.get("error_message") or "")[:220]
    ledger = state.get(SELECTOR_REQUEST_LEDGER_KEY) if isinstance(state.get(SELECTOR_REQUEST_LEDGER_KEY), list) else []
    last_request_time = ""
    for row in reversed(ledger):
        if isinstance(row, Mapping) and str(row.get("assigned_key") or "") == key_alias and bool(row.get("request_attempted")):
            last_request_time = str(row.get("request_time") or "")
            break
    worker = {
        "Assigned selector": "Selector 1" if group_name == "FIRST" else "Selector 2" if group_name == "SECOND" else "Selector 3",
        "Assigned key": key_alias,
        "Selected symbols": " → ".join(normalize_symbols(symbols, limit=None)),
        "Loaded count": len(normalize_symbols(status.get("loaded_symbols") or [], limit=None)),
        "Failed count": len(normalize_symbols(status.get("failed_symbols") or [], limit=None)),
        "Remaining local minute credits": int(key_info.get("remaining_credits") or 0),
        "Cooldown seconds": _cooldown_seconds_from_snapshot(key_info if isinstance(key_info, Mapping) else {}),
        "Last request time": last_request_time or str(key_info.get("last_successful_request_time") or ""),
        "Last error": last_error,
        "Symbols skipped because of quota": " → ".join(quota_skipped),
        "Symbols skipped because of circuit breaker": " → ".join(circuit_skipped),
        "Status": str(status.get("status") or "NOT_LOADED"),
    }
    all_workers = state.get(SELECTOR_WORKER_STATE_KEY)
    if not isinstance(all_workers, dict):
        all_workers = {}
    all_workers[group_name] = worker
    state[SELECTOR_WORKER_STATE_KEY] = all_workers
    return worker


def _run_group_with_temporary_assignment(
    state: MutableMapping[str, Any], group_name: str, symbols: Sequence[str], timeframe: str, key_alias: str,
    *, progress_callback: Any = None, retry_symbols: Sequence[str] | None = None, force_reload: bool = False,
) -> dict[str, Any]:
    assigned_key = _normalize_key_alias(key_alias)
    temporary_keys = {
        ASSIGNED_TWELVE_KEY_STATE_KEY: assigned_key,
        ASSIGNED_SELECTOR_STATE_KEY: group_name,
        SELECTOR_TWELVE_ONLY_STATE_KEY: True,
        "multi_symbol_fetch_rounds_20260706": 1,
        "quota_safe_stagger_enabled_20260706": False,
        "market_data_progress_full_range_20260708": True,
    }
    prior_values = {key: state.get(key, None) for key in temporary_keys}
    prior_presence = {key: key in state for key in temporary_keys}
    state.update(temporary_keys)
    try:
        record = load_group_market_data(
            state, group_name, symbols, timeframe,
            progress_callback=progress_callback,
            retry_symbols=list(retry_symbols) if retry_symbols is not None else None,
            force_reload=bool(force_reload),
        )
    finally:
        for key in temporary_keys:
            if prior_presence[key]:
                state[key] = prior_values[key]
            else:
                state.pop(key, None)
    attempted_symbols = list(retry_symbols) if retry_symbols is not None else list(symbols)
    _append_request_ledger_from_record(state, record, assigned_key=assigned_key, attempted_symbols=attempted_symbols)
    _update_selector_worker_state(state, group_name, list(symbols), str(timeframe or "H4").upper(), assigned_key, record)
    return record


def load_selector_with_assigned_key(
    state: MutableMapping[str, Any], selector_id: Any, symbols: Any, timeframe: Any, key_name: Any,
    *, force: bool = False, retry_failed_only: bool = False, progress_callback: Any = None,
    emergency_cross_key_retry: bool | None = None,
) -> dict[str, Any]:
    """Load one selector with its assigned Twelve Data key only.

    Selector 1 reserves only TWELVE_KEY_1 and Selector 2 reserves only
    TWELVE_KEY_2. Valid cache rows are reused first and do not spend credits.
    Manual retry clears local circuit-breaker flags for the exact failed symbols
    before making a new request decision. Existing READY rows are preserved.
    """
    group_name = _normalize_selector_group(selector_id)
    selected_all = normalize_symbols(symbols, limit=group_symbol_limit(group_name))
    if not selected_all:
        raise ValueError(f"{group_name} has no selected symbols to load.")
    tf = str(timeframe or state.get("timeframe") or state.get("selected_timeframe") or "H4").strip().upper() or "H4"
    assigned_key = _normalize_key_alias(key_name)
    if group_name == "FIRST" and assigned_key != "TWELVE_KEY_1":
        assigned_key = "TWELVE_KEY_1"
    if group_name == "SECOND" and assigned_key != "TWELVE_KEY_2":
        assigned_key = "TWELVE_KEY_2"
    if group_name == "THIRD":
        assigned_key = "TWELVE_DATA_KEY_POOL"
    if assigned_key not in {"TWELVE_KEY_1", "TWELVE_KEY_2", "TWELVE_DATA_KEY_POOL"}:
        raise ValueError(f"{group_name} has no valid Twelve Data assignment.")

    retry_symbols: list[str] | None = None
    if retry_failed_only:
        status = loaded_group_status(state, group_name, selected_all, tf)
        retry_symbols = _retryable_symbols_from_status(status)
        if not retry_symbols:
            record = _records(state).get(group_name)
            merge_selector_load_results(state, None, tf)
            return dict(record) if isinstance(record, Mapping) else {
                "group": group_name, "timeframe": tf, "requested_symbols": selected_all,
                "loaded_symbols": selected_all, "failed_symbols": [], "status": "READY",
                "message": "No failed symbols are eligible for retry.",
            }
    request_symbols = retry_symbols if retry_symbols is not None else selected_all
    if force or retry_failed_only:
        clear_result = clear_circuit_breaker_for_symbols(request_symbols, tf, provider=("TWELVE_DATA_KEY_POOL", assigned_key))
        state["last_selector_owned_circuit_clear_20260708"] = clear_result
        state["market_connector_force_refresh_requested_20260702"] = True

    if assigned_key == "TWELVE_DATA_KEY_POOL":
        # Selector 3 uses the shared pool so every configured key may work in
        # parallel. It is no longer cache-only and therefore can be loaded alone,
        # after another selector, or as part of Load All.
        record = load_group_market_data(
            state, group_name, selected_all, tf,
            progress_callback=progress_callback,
            retry_symbols=retry_symbols,
            force_reload=bool(force or retry_failed_only),
        )
        attempted_symbols = list(retry_symbols) if retry_symbols is not None else list(selected_all)
        _append_request_ledger_from_record(
            state, record, assigned_key="TWELVE_DATA_KEY_POOL", attempted_symbols=attempted_symbols,
        )
        _update_selector_worker_state(
            state, group_name, list(selected_all), tf, "TWELVE_DATA_KEY_POOL", record,
        )
    else:
        record = _run_group_with_temporary_assignment(
            state, group_name, selected_all, tf, assigned_key,
            progress_callback=progress_callback, retry_symbols=retry_symbols, force_reload=bool(force or retry_failed_only),
        )

    # Automatic resilient recovery is always enabled for explicit user loads.
    # A selector's assigned key is attempted first, then the other configured
    # key(s), then the shared pool. Every retry is failed-symbol-only, so valid
    # rows from this or earlier selector loads can never be erased.
    recovery_order: list[str] = []
    if assigned_key == "TWELVE_KEY_1":
        recovery_order = ["TWELVE_KEY_2", "TWELVE_DATA_KEY_POOL"]
    elif assigned_key == "TWELVE_KEY_2":
        recovery_order = ["TWELVE_KEY_1", "TWELVE_DATA_KEY_POOL"]
    else:
        recovery_order = ["TWELVE_KEY_1", "TWELVE_KEY_2"]
    recovery_trace: list[dict[str, Any]] = []
    for recovery_key in recovery_order:
        status_after = loaded_group_status(state, group_name, selected_all, tf)
        still_failed = _retryable_symbols_from_status(status_after)
        if not still_failed:
            break
        clear_circuit_breaker_for_symbols(
            still_failed, tf, provider=("TWELVE_DATA_KEY_POOL", recovery_key)
        )
        try:
            if recovery_key == "TWELVE_DATA_KEY_POOL":
                recovery_record = load_group_market_data(
                    state, group_name, selected_all, tf,
                    progress_callback=progress_callback, retry_symbols=still_failed, force_reload=True,
                )
                _append_request_ledger_from_record(
                    state, recovery_record, assigned_key=recovery_key, attempted_symbols=still_failed,
                )
            else:
                recovery_record = _run_group_with_temporary_assignment(
                    state, group_name, selected_all, tf, recovery_key,
                    progress_callback=progress_callback, retry_symbols=still_failed, force_reload=True,
                )
            record = recovery_record
            recovery_trace.append({
                "key": recovery_key, "symbols": list(still_failed), "ok": True,
                "used_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as recovery_exc:
            recovery_trace.append({
                "key": recovery_key, "symbols": list(still_failed), "ok": False,
                "error": f"{type(recovery_exc).__name__}: {recovery_exc}",
                "used_at": datetime.now(timezone.utc).isoformat(),
            })
            continue
    state["selector_owned_automatic_recovery_trace_20260722"] = recovery_trace
    merge_selector_load_results(state, None, tf)
    return record


def _cache_only_validation_for_symbol(symbol: str, timeframe: str, required_rows: int) -> tuple[dict[str, Any], dict[str, Any] | None]:
    payload = _fresh_cache_payload(symbol, timeframe, required_rows=required_rows)
    if isinstance(payload, Mapping):
        validation = _validate_result(payload, symbol=symbol, timeframe=timeframe, required_rows=required_rows)
        if validation.get("ok"):
            validation["status"] = "READY_FROM_CACHE"
            validation["api_status"] = "READY_FROM_CACHE"
            validation["request_attempted"] = False
            validation["cache_used"] = True
            return validation, dict(payload)
    validation = _validate_result({
        "ok": False, "symbol": symbol, "timeframe": timeframe, "provider": "NONE",
        "status": "PENDING", "message": "No selector worker loaded this symbol and no valid cache exists.",
        "request_attempted": False,
    }, symbol=symbol, timeframe=timeframe, required_rows=required_rows)
    validation.update({
        "status": "PENDING", "api_status": "PENDING", "provider": "NONE", "actual_provider": "NONE",
        "request_attempted": False, "failure_category": "PENDING", "failure_code": "PROVIDER_NONE",
        "data_quality": "F_NO_USABLE_DATA", "retryable": True,
    })
    return validation, None


def merge_selector_load_results(state: MutableMapping[str, Any], configured: Mapping[str, Any] | None = None, timeframe: Any | None = None) -> dict[str, Any]:
    """Create the canonical 30-symbol board from all three selector workers.

    This is the single Field 10 read surface. Selector 1 reserves Key 1,
    Selector 2 reserves Key 2, and Selector 3 uses the shared key pool. Existing
    valid rows from earlier selector-by-selector loads are preserved and merged.
    """
    if configured is None:
        try:
            from core.multi_symbol_run_groups_20260706 import configured_groups
            configured = configured_groups(state)
        except Exception:
            configured = {}
    tf = str(timeframe or state.get("timeframe") or state.get("selected_timeframe") or "H4").strip().upper() or "H4"
    selected = canonical_universe_from_groups(configured, limit=MAX_CANONICAL_SYMBOLS) if isinstance(configured, Mapping) else get_canonical_ranking_symbols(state)
    if not selected:
        selected = get_canonical_ranking_symbols(state)
    publish_canonical_universe(state, selected, tf)
    try:
        from core.timeframe_window_contract_20260706 import minimum_calculation_candles, required_candles
        required_rows = int(required_candles(tf, "higher"))
        minimum_rows = int(minimum_calculation_candles(tf, "higher"))
    except Exception:
        required_rows = 600
        minimum_rows = 25
    records = _records(state)
    validations: dict[str, Any] = {}
    results: dict[str, Any] = {}
    requested_union = canonical_universe_from_groups(configured, limit=MAX_CANONICAL_SYMBOLS)
    loaded: list[str] = []
    failed: list[str] = []
    source_group_by_symbol: dict[str, str] = {}
    group_order = ("FIRST", "SECOND", "THIRD")
    for group_name in group_order:
        group_symbols = normalize_symbols((configured or {}).get(group_name) if isinstance(configured, Mapping) else [], limit=group_symbol_limit(group_name))
        for symbol in group_symbols:
            source_group_by_symbol.setdefault(symbol, group_name)
    for symbol in selected:
        preferred_group = source_group_by_symbol.get(symbol, "THIRD")
        candidate_groups = [preferred_group] + [g for g in group_order if g != preferred_group]
        candidates: list[tuple[str, dict[str, Any], Mapping[str, Any] | None]] = []
        for candidate_group in candidate_groups:
            record = records.get(candidate_group) if isinstance(records.get(candidate_group), Mapping) else {}
            record_validations = record.get("validations") if isinstance(record.get("validations"), Mapping) else {}
            record_report = record.get("report") if isinstance(record.get("report"), Mapping) else {}
            record_results = record_report.get("results") if isinstance(record_report.get("results"), Mapping) else {}
            evidence = record_validations.get(symbol) if isinstance(record_validations.get(symbol), Mapping) else None
            payload = record_results.get(symbol) if isinstance(record_results.get(symbol), Mapping) else None
            if isinstance(evidence, Mapping):
                candidates.append((candidate_group, dict(evidence), payload))
        # Any valid exact-symbol result wins, regardless of which selector loaded
        # it. This fixes duplicate symbols and sequential selector loads where a
        # stale failed record previously masked a valid record from another group.
        chosen = next((item for item in candidates if bool(item[1].get("ok"))), None)
        if chosen is None and candidates:
            chosen = max(
                candidates,
                key=lambda item: (
                    int(item[1].get("rows") or item[1].get("genuine_rows") or 0),
                    str(item[1].get("latest_candle_time") or item[1].get("latest_completed_candle") or ""),
                ),
            )
        if chosen is not None:
            group_name, validation, payload = chosen
            if isinstance(payload, Mapping):
                results[symbol] = payload
        else:
            group_name = preferred_group
            validation, payload = _cache_only_validation_for_symbol(symbol, tf, required_rows)
            if isinstance(payload, Mapping):
                results[symbol] = payload
        validation["source_selector"] = group_name
        validation.setdefault("assigned_key", SELECTOR_KEY_MAP.get(group_name, "TWELVE_DATA_KEY_POOL"))
        validations[symbol] = validation
        (loaded if bool(validation.get("ok")) else failed).append(symbol)
    load_id = f"MERGED-SELECTOR-OWNED-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    status = "READY" if selected and len(loaded) == len(selected) else "PARTIAL_READY" if loaded else "FAILED"
    filtered_report = {
        "run_id": load_id, "load_id": load_id, "timeframe": tf, "results": results,
        "requested_symbols": list(selected), "loaded_symbols": list(loaded), "unresolved_symbols": list(failed),
        "required_candles_per_symbol": required_rows,
        "minimum_calculation_candles_per_symbol": minimum_rows,
        "complete": bool(selected) and not failed, "load_only": True,
        "selector_owned_merge": True,
    }
    record = {
        "group": CANONICAL_GROUP, "scope": scope_for_group(CANONICAL_GROUP), "load_id": load_id,
        "loaded_at": datetime.now(timezone.utc).isoformat(), "timeframe": tf,
        "selection_signature": selection_signature(selected, tf), "requested_symbols": list(selected),
        "loaded_symbols": list(loaded), "failed_symbols": list(failed),
        "required_candles": required_rows, "minimum_calculation_candles": minimum_rows,
        "validations": validations, "status": status,
        "load_status": "COMPLETED" if status == "READY" else "PARTIAL" if status == "PARTIAL_READY" else "FAILED",
        "selected_count": len(selected), "loaded_count": len(loaded), "failed_count": len(failed),
        "selector_owned_merge": True, "source_groups": [g for g in group_order if isinstance(records.get(g), Mapping)],
        "report": filtered_report,
    }
    records[CANONICAL_GROUP] = record
    state[LOAD_RECORDS_KEY] = records
    state[CANONICAL_LOADED_KEY] = list(loaded)
    state["canonical_loaded_symbols_20260705"] = list(loaded)
    state[CANONICAL_LOAD_RECORD_KEY] = {key: value for key, value in record.items() if key != "report"}
    state[CANONICAL_LAST_LOAD_RUN_ID_KEY] = load_id
    state[CANONICAL_SYMBOL_CANDLES_KEY] = {
        symbol: results[symbol].get("frame")
        for symbol in selected
        if isinstance(results.get(symbol), Mapping) and isinstance(results[symbol].get("frame"), pd.DataFrame)
    }
    try:
        _persist_load_audit(record, state)
    except Exception as exc:
        state["selector_owned_merge_persistence_error_20260708"] = f"{type(exc).__name__}: {exc}"
    _publish_loaded_to_global_context(state, selected, loaded, failed, results, tf)
    return loaded_canonical_status(state, selected, tf)


def load_all_selectors_safely(
    state: MutableMapping[str, Any], configured: Mapping[str, Any], timeframe: Any,
    *, progress_callback: Any = None, retry_failed_only: bool = False, force_retry_failed: bool = False,
    emergency_cross_key_retry: bool | None = None,
) -> dict[str, Any]:
    """Load every selector independently and never abort the remaining selectors.

    Provider/key failures are isolated to their exact symbols. Successful rows
    remain merged and calculation-ready while failed rows stay visible/retryable.
    """
    tf = str(timeframe or state.get("timeframe") or "H4").strip().upper() or "H4"
    groups = configured if isinstance(configured, Mapping) else {}
    plan = (
        ("FIRST", normalize_symbols(groups.get("FIRST") or [], limit=group_symbol_limit("FIRST")), "TWELVE_KEY_1"),
        ("SECOND", normalize_symbols(groups.get("SECOND") or [], limit=group_symbol_limit("SECOND")), "TWELVE_KEY_2"),
        ("THIRD", normalize_symbols(groups.get("THIRD") or [], limit=group_symbol_limit("THIRD")), "TWELVE_DATA_KEY_POOL"),
    )
    errors: dict[str, str] = {}
    for group_name, symbols, assigned_key in plan:
        if not symbols:
            continue
        try:
            load_selector_with_assigned_key(
                state, group_name, symbols, tf, assigned_key,
                force=bool(force_retry_failed),
                retry_failed_only=bool(retry_failed_only or force_retry_failed),
                progress_callback=progress_callback,
                emergency_cross_key_retry=True,
            )
        except Exception as exc:
            errors[group_name] = f"{type(exc).__name__}: {exc}"
            # Continue to the next selector. A single bad key/symbol must never
            # prevent other selected symbols from loading.
            continue
    if errors:
        state["selector_load_all_nonblocking_errors_20260722"] = errors
    return merge_selector_load_results(state, groups, tf)


def refresh_all_selectors_safely(
    state: MutableMapping[str, Any], configured: Mapping[str, Any], timeframe: Any,
    *, progress_callback: Any = None,
) -> dict[str, Any]:
    """Force-refresh every configured selector, preserving usable prior rows.

    This powers the Settings ``Load & Update + Super Quick`` action. Each
    selector keeps its assigned Twelve Data route, requests the newest
    completed candle where available, and falls back to the last exact valid
    symbol/timeframe history when a provider fails. One selector failure never
    aborts the remaining selectors.
    """
    tf = str(timeframe or state.get("timeframe") or "H1").strip().upper() or "H1"
    groups = configured if isinstance(configured, Mapping) else {}
    plan = (
        ("FIRST", normalize_symbols(groups.get("FIRST") or [], limit=group_symbol_limit("FIRST")), "TWELVE_KEY_1"),
        ("SECOND", normalize_symbols(groups.get("SECOND") or [], limit=group_symbol_limit("SECOND")), "TWELVE_KEY_2"),
        ("THIRD", normalize_symbols(groups.get("THIRD") or [], limit=group_symbol_limit("THIRD")), "TWELVE_DATA_KEY_POOL"),
    )
    errors: dict[str, str] = {}
    refreshed_groups: list[str] = []
    state["load_update_refresh_started_20260729"] = datetime.now(timezone.utc).isoformat()
    for group_name, symbols, assigned_key in plan:
        if not symbols:
            continue
        try:
            load_selector_with_assigned_key(
                state, group_name, symbols, tf, assigned_key,
                force=True,
                retry_failed_only=False,
                progress_callback=progress_callback,
                emergency_cross_key_retry=True,
            )
            refreshed_groups.append(group_name)
        except Exception as exc:
            errors[group_name] = f"{type(exc).__name__}: {exc}"
            continue
    if errors:
        state["load_update_nonblocking_errors_20260729"] = errors
    merged = merge_selector_load_results(state, groups, tf)
    state["load_update_refresh_result_20260729"] = {
        "timeframe": tf,
        "refreshed_groups": refreshed_groups,
        "errors": errors,
        "loaded_symbols": list(merged.get("loaded_symbols") or []),
        "failed_symbols": list(merged.get("failed_symbols") or []),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    return merged

def load_group_market_data(
    state: MutableMapping[str, Any],
    group: Any,
    symbols: Any,
    timeframe: Any,
    *,
    progress_callback: Any = None,
    retry_symbols: Any = None,
    force_reload: bool = False,
) -> dict[str, Any]:
    """Load and validate one selector group without running calculations."""
    group_name = str(group or "SECOND").strip().upper()
    if group_name not in _GROUP_TO_SCOPE:
        raise ValueError(f"Unknown multi-symbol group: {group}")
    selected_all = normalize_symbols(symbols, limit=group_symbol_limit(group_name))
    if not selected_all:
        raise ValueError("Select at least one symbol, then press Load Selected Data.")
    tf = str(timeframe or "H4").strip().upper() or "H4"
    existing_record = _records(state).get(group_name)
    retry_requested = retry_symbols is not None
    if retry_requested:
        if not isinstance(existing_record, Mapping):
            raise ValueError("No previous failed-symbol load exists for this selector.")
        if str(existing_record.get("selection_signature") or "") != selection_signature(selected_all, tf):
            raise ValueError("Selection or timeframe changed; use Load Selected Data before retrying failures.")
        previous_failed = normalize_symbols(existing_record.get("failed_symbols") or [], limit=None)
        selected = [symbol for symbol in normalize_symbols(retry_symbols, limit=None) if symbol in selected_all and symbol in previous_failed]
        if not selected:
            return dict(existing_record)
    else:
        selected = list(selected_all)
    from core.calculation.run_orchestrator import prepare_market_data_for_run
    from core.timeframe_window_contract_20260706 import minimum_calculation_candles, required_candles

    required_rows = int(required_candles(tf, "higher"))
    minimum_rows = int(minimum_calculation_candles(tf, "higher"))
    operation = "RELOAD" if retry_requested else "LOAD"
    load_id = f"{operation}-{group_name}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    load_started_monotonic = time.monotonic()
    load_started_at = datetime.now(timezone.utc).isoformat()
    state[REQUIRE_EXPLICIT_LOAD_KEY] = True
    state["multi_symbol_load_in_progress_20260707"] = group_name
    # Twelve Data key pool is the active live provider. Each configured key is
    # treated as its own small rate-limited worker; the foreground loader keeps
    # symbol-level validation, cache recovery, and unresolved-only retries.
    try:
        from core.data.market_data_orchestrator import provider_priority_for_state
        primary_provider = provider_priority_for_state(state)[0]
    except Exception:
        primary_provider = "TWELVE_DATA_KEY_POOL"
    selector_assigned_key = _normalize_key_alias(state.get(ASSIGNED_TWELVE_KEY_STATE_KEY) or SELECTOR_KEY_MAP.get(group_name, ""))
    selector_owned_mode = bool(selector_assigned_key in {"TWELVE_KEY_1", "TWELVE_KEY_2"} and group_name in {"FIRST", "SECOND"})
    temporary_keys = {
        "quota_safe_stagger_enabled_20260706": False if selector_owned_mode else bool(primary_provider in {"TWELVE_DATA", "TWELVE_DATA_FALLBACK", "TWELVE_DATA_KEY_POOL"} and len(selected) > 1),
        "quota_safe_batch_size_20260706": min(7, max(1, len(selected))),
        "quota_safe_batch_interval_seconds_20260706": 60.0,
        "multi_symbol_fetch_rounds_20260706": 1 if selector_owned_mode else 4,
        "settings_calculation_scope_20260625": "LUNCH_CORE",
        "fast_multi_symbol_primary_provider_20260708": primary_provider,
        "market_data_progress_full_range_20260708": True,
    }
    if selector_owned_mode:
        temporary_keys.update({
            ASSIGNED_TWELVE_KEY_STATE_KEY: selector_assigned_key,
            ASSIGNED_SELECTOR_STATE_KEY: group_name,
            SELECTOR_TWELVE_ONLY_STATE_KEY: True,
        })
    prior_values = {key: state.get(key, None) for key in temporary_keys}
    prior_presence = {key: key in state for key in temporary_keys}
    state.update(temporary_keys)
    if force_reload or retry_requested:
        # Explicit reload/failed-only retry should never reuse a stale local
        # RUN_CIRCUIT_OPEN decision. Clear only the local circuit flags for the
        # exact selected symbols/timeframe; Twelve Data per-key credit counters
        # and cooldowns remain enforced by the key pool.
        try:
            from core.data.symbol_level_provider_registry_20260708 import SymbolLevelProviderRegistry
            from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
            registry = SymbolLevelProviderRegistry(DEFAULT_DB_PATH)
            cleared = 0
            for retry_symbol in selected:
                for retry_provider in ("TWELVE_DATA_KEY_POOL", "TWELVE_DATA", "TWELVE_DATA_FALLBACK", "FINNHUB", "ALPHA_VANTAGE"):
                    cleared += registry.reset_circuit(provider=retry_provider, symbol=retry_symbol, timeframe=tf)
            state["last_reload_circuit_reset_count_20260708"] = cleared
        except Exception as circuit_exc:
            state["last_reload_circuit_reset_error_20260708"] = f"{type(circuit_exc).__name__}: {circuit_exc}"
        state["market_connector_force_refresh_requested_20260702"] = True
    try:
        try:
            report = prepare_market_data_for_run(
                state,
                run_id=load_id,
                selected_symbols=selected,
                timeframe=tf,
                progress_callback=progress_callback,
            )
        except Exception as prepare_exc:
            # Always return a structured per-symbol result instead of leaving the
            # UI spinner hanging or discarding the selector state. Exact local
            # recovery below still gets a chance to admit previously persisted
            # candles for the same symbol/timeframe.
            report = {
                "run_id": load_id,
                "timeframe": tf,
                "results": {},
                "requested_symbols": list(selected),
                "unresolved_symbols": list(selected),
                "complete": False,
                "load_only": True,
                "fatal_prepare_error": f"{type(prepare_exc).__name__}: {prepare_exc}",
            }
    finally:
        state.pop("multi_symbol_load_in_progress_20260707", None)
        for key in temporary_keys:
            if prior_presence[key]:
                state[key] = prior_values[key]
            else:
                state.pop(key, None)

    raw_results = dict(report.get("results")) if isinstance(report, Mapping) and isinstance(report.get("results"), Mapping) else {}
    # A failed-symbol reload is an exact merge transaction: already-valid
    # symbols retain their prior validated frames and are never fetched again.
    if retry_requested and isinstance(existing_record, Mapping):
        previous_report = existing_record.get("report") if isinstance(existing_record.get("report"), Mapping) else {}
        previous_results = previous_report.get("results") if isinstance(previous_report.get("results"), Mapping) else {}
        merged_results = {
            symbol: previous_results[symbol]
            for symbol in selected_all
            if symbol not in selected and isinstance(previous_results.get(symbol), Mapping)
        }
        merged_results.update(raw_results)
        raw_results = merged_results

    # Last-resort exact local recovery: the provider layer can return an error
    # after a valid repository read. Recover only the same symbol/timeframe and
    # never borrow, pad, forward-fill, or synthesize candles.
    try:
        from core.data.candle_repository import CandleRepository
        from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
        repository = CandleRepository(DEFAULT_DB_PATH)
        for symbol in selected:
            payload = raw_results.get(symbol)
            provisional = _validate_result(
                payload if isinstance(payload, Mapping) else {},
                symbol=symbol, timeframe=tf, required_rows=required_rows,
            )
            if provisional.get("ok"):
                continue
            cached = repository.load(symbol, tf, limit=max(required_rows + 24, 600), completed_only=True)
            if not isinstance(cached, pd.DataFrame) or cached.empty:
                continue
            latest = pd.to_datetime(cached.get("open_time"), errors="coerce", utc=True).max() if "open_time" in cached.columns else pd.NaT
            quality_mean = pd.to_numeric(cached.get("data_quality_score"), errors="coerce").mean() if "data_quality_score" in cached.columns else pd.NA
            raw_results[symbol] = {
                "ok": True,
                "symbol": symbol,
                "timeframe": tf,
                "frame": cached,
                "provider": "LOCAL_VALID_CACHE",
                "provider_symbol": symbol,
                "status": "CACHED_VALID_EXACT_RECOVERY",
                "message": "Exact-symbol validated SQLite candle history recovered after provider failure; no synthetic data used.",
                "latest_completed_candle": None if pd.isna(latest) else pd.Timestamp(latest).isoformat(),
                "fallback_provider": "LOCAL_VALID_CACHE",
                "attempts": list(payload.get("attempts")) if isinstance(payload, Mapping) and isinstance(payload.get("attempts"), Sequence) and not isinstance(payload.get("attempts"), (str, bytes)) else [],
                "data_age_seconds": None,
                "data_quality_score": (
                    float(quality_mean) if pd.notna(quality_mean) else 0.0
                ) if "data_quality_score" in cached.columns else 0.0,
                "validation_status": "VALID",
                "run_id": load_id,
                "recovery_provenance": "EXACT_SYMBOL_TIMEFRAME_SQLITE",
            }
    except Exception as recovery_exc:
        state["multi_symbol_exact_cache_recovery_error_20260707"] = f"{type(recovery_exc).__name__}: {recovery_exc}"

    validations: dict[str, dict[str, Any]] = {}
    loaded: list[str] = []
    failed: list[str] = []
    previous_validations = existing_record.get("validations") if retry_requested and isinstance(existing_record, Mapping) and isinstance(existing_record.get("validations"), Mapping) else {}
    previous_retry_counts = existing_record.get("retry_count_by_symbol") if retry_requested and isinstance(existing_record, Mapping) and isinstance(existing_record.get("retry_count_by_symbol"), Mapping) else {}
    retry_count_by_symbol: dict[str, int] = {}
    for symbol in selected_all:
        payload = raw_results.get(symbol) if isinstance(raw_results, Mapping) else None
        validation = _validate_result(
            payload if isinstance(payload, Mapping) else {},
            symbol=symbol, timeframe=tf, required_rows=required_rows,
        )
        if symbol not in selected and isinstance(previous_validations.get(symbol), Mapping):
            # Retry-only loads fetch only failed symbols. Preserve the prior
            # successful validation for already-loaded symbols instead of letting
            # an empty placeholder validation overwrite it. This keeps 7 good
            # symbols READY while the last 5 are retried.
            previous_validation = dict(previous_validations[symbol])
            if bool(previous_validation.get("ok")):
                validation = previous_validation
            else:
                validation = {**validation, **previous_validation}
        prior_count = int(previous_retry_counts.get(symbol) or 0)
        retry_count_by_symbol[symbol] = prior_count + (1 if retry_requested and symbol in selected else 0)
        validation["retry_count"] = retry_count_by_symbol[symbol]
        validations[symbol] = validation
        (loaded if validation["ok"] else failed).append(symbol)

    filtered_results = {
        symbol: raw_results[symbol]
        for symbol in selected_all
        if isinstance(raw_results, Mapping) and isinstance(raw_results.get(symbol), Mapping)
    }
    filtered_report = dict(report) if isinstance(report, Mapping) else {}
    filtered_report.update({
        "run_id": load_id,
        "load_id": load_id,
        "timeframe": tf,
        "results": filtered_results,
        "requested_symbols": list(selected_all),
        "loaded_symbols": list(loaded),
        "unresolved_symbols": list(failed),
        "required_candles_per_symbol": required_rows,
        "minimum_calculation_candles_per_symbol": minimum_rows,
        "complete": bool(loaded) and not failed,
        "load_only": True,
        "load_elapsed_seconds": round(max(0.0, time.monotonic() - load_started_monotonic), 3),
    })
    load_elapsed_seconds = round(max(0.0, time.monotonic() - load_started_monotonic), 3)
    record = {
        "group": group_name,
        "scope": scope_for_group(group_name),
        "load_id": load_id,
        "load_started_at": load_started_at,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
        "timeframe": tf,
        "selection_signature": selection_signature(selected_all, tf),
        "requested_symbols": list(selected_all),
        "loaded_symbols": list(loaded),
        "failed_symbols": list(failed),
        "required_candles": required_rows,
        "minimum_calculation_candles": minimum_rows,
        "validations": validations,
        "retry_count_by_symbol": retry_count_by_symbol,
        "latest_load_attempt": datetime.now(timezone.utc).isoformat(),
        "latest_successful_load": datetime.now(timezone.utc).isoformat() if loaded else (existing_record.get("latest_successful_load") if isinstance(existing_record, Mapping) else None),
        "retry_only": bool(retry_requested),
        "retried_symbols": list(selected) if retry_requested else [],
        "previous_load_id": existing_record.get("load_id") if retry_requested and isinstance(existing_record, Mapping) else None,
        "status": "READY" if loaded and not failed else "PARTIAL_READY" if loaded else "FAILED",
        "load_status": "COMPLETED" if loaded and not failed else "PARTIAL" if loaded else "FAILED",
        "selected_count": len(selected_all),
        "loaded_count": len(loaded),
        "failed_count": len(failed),
        "load_elapsed_seconds": load_elapsed_seconds,
        "seconds_per_requested_symbol": round(load_elapsed_seconds / max(1, len(selected)), 3),
        "provider_plan_primary": primary_provider,
        "run_disabled_providers": list(report.get("run_disabled_providers") or []) if isinstance(report, Mapping) else [],
        "fatal_prepare_error": str(report.get("fatal_prepare_error") or "") if isinstance(report, Mapping) else "",
        "report": filtered_report,
    }
    records = _records(state)
    records[group_name] = record
    state[LOAD_RECORDS_KEY] = records
    state[LAST_LOAD_KEY] = {key: value for key, value in record.items() if key != "report"}
    # Do not leave a load-only report globally active. A calculation click must
    # explicitly activate the exact matching group and selection first.
    state.pop(LOADED_RUN_ACTIVE_KEY, None)
    try:
        _persist_load_audit(record, state)
        try:
            from core.normalized_multi_symbol_migration_20260707 import persist_load_attempts
            from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
            persist_load_attempts(DEFAULT_DB_PATH, record)
        except Exception as normalized_exc:
            record["normalized_attempt_persistence_error"] = f"{type(normalized_exc).__name__}: {normalized_exc}"
        record["database_persistence"] = "SAVED"
    except Exception as persist_exc:
        record["database_persistence"] = "FAILED"
        record["database_persistence_error"] = f"{type(persist_exc).__name__}: {persist_exc}"
        state["multi_symbol_load_audit_error_20260707"] = record["database_persistence_error"]
    return record


def load_canonical_market_data(
    state: MutableMapping[str, Any],
    configured: Mapping[str, Any] | Sequence[Any],
    timeframe: Any,
    *,
    progress_callback: Any = None,
    force_reload: bool = False,
    retry_failed_only: bool = False,
) -> dict[str, Any]:
    """Load the one canonical top-30 ranking universe.

    Selector state is used only to build the ordered, deduplicated universe.  The
    provider/cache transaction is a single CANONICAL queue, so Selector 2 and
    Selector 3 cannot fail just because their old independent group state is stale.
    """
    if isinstance(configured, Mapping):
        selected = canonical_universe_from_groups(configured, limit=MAX_CANONICAL_SYMBOLS)
    else:
        selected = normalize_symbols(configured, limit=MAX_CANONICAL_SYMBOLS)
    if not selected:
        selected = get_canonical_ranking_symbols(state)
    if not selected:
        raise ValueError("Select at least one symbol across Selector 1, 2, or 3.")
    tf = str(timeframe or state.get("settings_timeframe") or state.get("timeframe") or state.get("selected_timeframe") or "H4").strip().upper() or "H4"
    publish_canonical_universe(state, selected, tf)
    try:
        from core.global_symbol_context import get_global_symbol_context, mark_universe_loading
        loading_context = get_global_symbol_context(state)
        if loading_context.universe_id:
            mark_universe_loading(loading_context.universe_id, state=state,
                                  details={"requested_symbols": selected, "timeframe": tf})
    except Exception as lifecycle_exc:
        state["global_symbol_loading_transition_warning_v2"] = f"{type(lifecycle_exc).__name__}: {lifecycle_exc}"

    # Selector-owned default: Selector 1 uses Key 1 only; Selector 2 uses
    # Key 2 only; Selector 3 uses all currently available pool keys. The old global pool
    # canonical queue is retained below as a compatibility fallback only when the
    # caller explicitly disables this architecture.
    if bool(state.get("selector_owned_twelve_architecture_enabled_20260708", True)) and isinstance(configured, Mapping):
        status = load_all_selectors_safely(
            state, configured, tf, progress_callback=progress_callback,
            retry_failed_only=bool(retry_failed_only), force_retry_failed=bool(force_reload),
            emergency_cross_key_retry=bool(state.get(EMERGENCY_CROSS_KEY_STATE_KEY)),
        )
        record = _records(state).get(CANONICAL_GROUP)
        return dict(record) if isinstance(record, Mapping) else {
            "group": CANONICAL_GROUP, "timeframe": tf, "requested_symbols": selected,
            "loaded_symbols": normalize_symbols(status.get("loaded_symbols") or [], limit=None),
            "failed_symbols": normalize_symbols(status.get("failed_symbols") or [], limit=None),
            "status": str(status.get("status") or "FAILED"),
        }

    if retry_failed_only:
        status = loaded_canonical_status(state, selected, tf)
        failed_for_retry: list[str] = []
        for row in status.get("status_rows") or []:
            if not isinstance(row, Mapping):
                continue
            symbol = _normalize_symbol(row.get("Symbol"))
            load_status = str(row.get("Load Status") or "").upper()
            candle_count = int(pd.to_numeric(pd.Series([row.get("Candle Count")]), errors="coerce").fillna(0).iloc[0])
            if symbol in selected and (
                load_status in {"FAILED_EXPLICIT", "RUN_CIRCUIT_OPEN", "FAILED_NO_DATA", "FAILED_VALIDATION", "EMPTY_RESPONSE", "API_ERROR", "FAILED", "INVALID_DATA", "PENDING", "INSUFFICIENT"}
                or candle_count < 25
            ):
                failed_for_retry.append(symbol)
        if not failed_for_retry:
            record = _records(state).get(CANONICAL_GROUP)
            return dict(record) if isinstance(record, Mapping) else {
                "group": CANONICAL_GROUP, "timeframe": tf, "requested_symbols": selected,
                "loaded_symbols": [], "failed_symbols": [], "status": "READY",
            }
        record = load_group_market_data(
            state, CANONICAL_GROUP, selected, tf,
            progress_callback=progress_callback, retry_symbols=failed_for_retry,
            force_reload=True,
        )
    else:
        record = load_group_market_data(
            state, CANONICAL_GROUP, selected, tf,
            progress_callback=progress_callback, force_reload=bool(force_reload),
        )

    loaded = normalize_symbols(record.get("loaded_symbols") or [], limit=MAX_CANONICAL_SYMBOLS)
    failed = normalize_symbols(record.get("failed_symbols") or [], limit=MAX_CANONICAL_SYMBOLS)
    state[CANONICAL_LOADED_KEY] = list(loaded)
    state["canonical_loaded_symbols_20260705"] = list(loaded)
    state[CANONICAL_LOAD_RECORD_KEY] = {key: value for key, value in record.items() if key != "report"}
    state[CANONICAL_LAST_LOAD_RUN_ID_KEY] = str(record.get("load_id") or "")
    report = record.get("report") if isinstance(record.get("report"), Mapping) else {}
    results = report.get("results") if isinstance(report.get("results"), Mapping) else {}
    state[CANONICAL_SYMBOL_CANDLES_KEY] = {
        symbol: results[symbol].get("frame")
        for symbol in selected
        if isinstance(results.get(symbol), Mapping) and isinstance(results[symbol].get("frame"), pd.DataFrame)
    }
    # Publish authoritative status/trace immediately for Settings and Field 10.
    loaded_canonical_status(state, selected, tf)
    try:
        from core.multi_symbol_run_groups_20260706 import COMPLETED_UNION_KEY, union_symbols
        state[COMPLETED_UNION_KEY] = union_symbols(state.get(COMPLETED_UNION_KEY) or [], loaded)
    except Exception:
        pass
    _publish_loaded_to_global_context(state, selected, loaded, failed, results, tf)
    return record


def loaded_canonical_status(
    state: Mapping[str, Any], current_symbols: Any | None = None, timeframe: Any | None = None,
) -> dict[str, Any]:
    tf = str(timeframe or state.get(CANONICAL_RANKING_TIMEFRAME_KEY) or state.get("settings_timeframe") or state.get("timeframe") or state.get("selected_timeframe") or "H4").strip().upper() or "H4"
    selected = normalize_symbols(
        current_symbols if current_symbols is not None else state.get(CANONICAL_RANKING_SYMBOLS_KEY) or state.get(CANONICAL_SELECTED_KEY) or state.get("canonical_selected_symbols_20260705") or state.get("multi_symbol_selected_20260701") or [],
        limit=MAX_CANONICAL_SYMBOLS,
    )
    if isinstance(state, MutableMapping) and selected:
        publish_canonical_universe(state, selected, tf)
    status = loaded_group_status(state, CANONICAL_GROUP, selected, tf)
    loaded = normalize_symbols(status.get("loaded_symbols") or [], limit=MAX_CANONICAL_SYMBOLS)
    failed = normalize_symbols(status.get("failed_symbols") or [], limit=MAX_CANONICAL_SYMBOLS)
    validations = status.get("validations") if isinstance(status.get("validations"), Mapping) else {}
    status_rows: list[dict[str, Any]] = []
    provider_summary = {"LOCAL_CACHE": 0, "TWELVE_KEY_1": 0, "TWELVE_KEY_2": 0, "TWELVE_DATA_KEY_POOL": 0, "FINNHUB": 0, "LAST_KNOWN_VALID_CACHE": 0, "NONE": 0}
    provider_trace: dict[str, Any] = {}
    success_statuses = {"CACHE_SUCCESS", "TWELVE_SUCCESS", "TWELVE_KEY_1_SUCCESS", "TWELVE_KEY_2_SUCCESS", "FINNHUB_SUCCESS", "EMERGENCY_CACHE_SUCCESS", "READY_FROM_CACHE", "VALIDATED", "DEGRADED_VALID", "DEGRADED_VALID_CACHE"}

    for position, symbol in enumerate(selected, start=1):
        evidence = validations.get(symbol) if isinstance(validations.get(symbol), Mapping) else {}
        rows = int(evidence.get("rows") or evidence.get("genuine_rows") or 0)
        provider = _canonical_provider_used(evidence.get("provider") or evidence.get("actual_provider") or "NONE")
        api_status = str(evidence.get("api_status") or evidence.get("status") or "").strip().upper()
        key_pool_attempted = bool(evidence.get("key_pool_attempted") or evidence.get("twelve_attempted"))
        key_pool_error = str(evidence.get("key_pool_error") or evidence.get("twelve_error") or "")
        twelve_attempted = bool(evidence.get("twelve_attempted"))
        twelve_error = str(evidence.get("twelve_error") or "")
        cache_used = bool(evidence.get("cache_used") or provider in {"LOCAL_CACHE", "LAST_KNOWN_VALID_CACHE"})

        if symbol in loaded:
            if provider in {"TWELVE_KEY_1", "TWELVE_KEY_2"}:
                load_status = f"{provider}_SUCCESS"
            elif provider == "TWELVE_DATA_KEY_POOL":
                load_status = "TWELVE_SUCCESS"
            elif provider == "FINNHUB":
                load_status = "FINNHUB_SUCCESS"
            elif provider == "LAST_KNOWN_VALID_CACHE" or str(api_status).upper() == "STALE_VALID":
                load_status = "EMERGENCY_CACHE_SUCCESS"
                provider = "LAST_KNOWN_VALID_CACHE"
            elif provider == "LOCAL_CACHE":
                load_status = "CACHE_SUCCESS"
            else:
                load_status = api_status if api_status in success_statuses else "CACHE_SUCCESS"
                if provider in {"NONE", "UNKNOWN", ""}:
                    provider = "LOCAL_CACHE"
        elif symbol in failed:
            if bool(evidence.get("quota_blocked")) or str(evidence.get("failure_code") or "").upper() == "PROVIDER_RATE_LIMIT":
                load_status = "QUOTA_COOLDOWN"
                # Quota/cooldown is an assigned-key decision, not a candle provider
                # success. Show the key that blocked the request so Field 10 does
                # not collapse the reason into a vague provider NONE row.
                assigned_for_quota = _normalize_key_alias(evidence.get("assigned_key") or evidence.get("actual_key_name") or evidence.get("provider_key_alias"))
                provider = assigned_for_quota if assigned_for_quota in {"TWELVE_KEY_1", "TWELVE_KEY_2"} else ("NONE" if provider in {"UNKNOWN", ""} else provider)
            elif bool(evidence.get("circuit_skipped")) or str(evidence.get("failure_category") or "").upper() == "PROVIDER_UNAVAILABLE" and "CIRCUIT" in str(evidence.get("reason") or "").upper():
                load_status = "RUN_CIRCUIT_OPEN"
                # Circuit-skip means no real provider request was attempted. Keep
                # provider_used NONE until the manual reload clears the breaker and
                # sends a fresh assigned-key request.
                provider = "NONE"
            else:
                load_status = "FAILED_EXPLICIT"
                provider = "NONE" if provider in {"UNKNOWN", ""} else provider
        else:
            load_status = "PENDING"
            provider = "NONE" if provider in {"UNKNOWN", ""} else provider

        coverage_info = evidence.get("coverage") if isinstance(evidence.get("coverage"), Mapping) else {}
        try:
            coverage_ratio = float(coverage_info.get("Coverage Ratio") or coverage_info.get("coverage_ratio") or rows / max(1, int(evidence.get("required_rows") or 600)))
        except Exception:
            coverage_ratio = 0.0
        final_state = (
            "VALIDATED" if load_status in {"TWELVE_SUCCESS", "TWELVE_KEY_1_SUCCESS", "TWELVE_KEY_2_SUCCESS", "FINNHUB_SUCCESS", "CACHE_SUCCESS", "READY_FROM_CACHE"} else
            "DEGRADED_VALID_CACHE" if load_status == "EMERGENCY_CACHE_SUCCESS" else
            "FAILED_EXPLICIT" if load_status == "FAILED_EXPLICIT" else
            "PENDING"
        )
        latest = evidence.get("latest_candle_time") or evidence.get("latest_completed_candle") or ""
        freshness = "FRESH" if load_status in {"TWELVE_SUCCESS", "TWELVE_KEY_1_SUCCESS", "TWELVE_KEY_2_SUCCESS", "FINNHUB_SUCCESS"} else "STALE_BUT_USABLE" if load_status in {"CACHE_SUCCESS", "READY_FROM_CACHE", "EMERGENCY_CACHE_SUCCESS"} else "NO_USABLE_DATA" if load_status in {"FAILED_NO_DATA", "FAILED_EXPLICIT"} else "PENDING"
        reload_eligible = bool(
            load_status in {"FAILED_EXPLICIT", "RUN_CIRCUIT_OPEN", "FAILED_NO_DATA", "FAILED_VALIDATION", "EMPTY_RESPONSE", "API_ERROR", "FAILED", "INVALID_DATA", "PENDING", "INSUFFICIENT"}
            or rows < 25
        )
        provider_summary[provider if provider in provider_summary else "NONE"] += 1
        provider_trace[symbol] = {
            "provider_used": provider,
            "key_pool_attempted": key_pool_attempted,
            "key_pool_error": key_pool_error,
            "actual_key_name": str(evidence.get("actual_key_name") or evidence.get("provider_key_alias") or evidence.get("assigned_key") or ""),
            "assigned_key": str(evidence.get("assigned_key") or ""),
            "request_attempted": bool(evidence.get("request_attempted")),
            "quota_blocked": bool(evidence.get("quota_blocked")),
            "circuit_skipped": bool(evidence.get("circuit_skipped")),
            "twelve_attempted": twelve_attempted,
            "twelve_error": twelve_error,
            "cache_used": cache_used,
            "final_state": final_state,
            "coverage_ratio": round(float(coverage_ratio), 4),
        }
        status_rows.append({
            "Order": position,
            "Symbol": symbol,
            "Requested timeframe": tf,
            "Timeframe": tf,
            "Local cache status": "USED" if provider == "LOCAL_CACHE" else "AVAILABLE" if cache_used else "NOT_USED",
            "Twelve Key Pool result": "ATTEMPTED" if key_pool_attempted and not key_pool_error else key_pool_error or "NOT_ATTEMPTED",
            "Actual key name": str(evidence.get("actual_key_name") or evidence.get("provider_key_alias") or evidence.get("assigned_key") or ""),
            "Assigned key": str(evidence.get("assigned_key") or ""),
            "API request attempted after click": bool(evidence.get("request_attempted")),
            "Skipped by quota cooldown": bool(evidence.get("quota_blocked")),
            "Skipped by circuit breaker": bool(evidence.get("circuit_skipped")),
            "Last valid cache result": "USED" if provider == "LAST_KNOWN_VALID_CACHE" else "AVAILABLE" if cache_used else "MISSING_OR_NOT_USED",
            "Actual provider used": provider,
            "Actual Candle Provider": provider,
            "Load Status": load_status,
            "Load Final State": final_state,
            "Candle Count": rows,
            "Completed candle time": latest or "—",
            "Last Candle Time": latest or "—",
            "Latest Candle Time": latest or "—",
            "Coverage ratio": round(float(coverage_ratio), 4),
            "Data Quality Grade": str(evidence.get("data_quality") or _data_quality_grade(rows, load_status)),
            "Final state": final_state,
            "Explicit failure reason": str(evidence.get("failure_reason") or evidence.get("reason") or ""),
            "Data Provider Used": provider,
            "Provider Trace": json.dumps(provider_trace[symbol], default=str),
            "Twelve Key Pool Attempted": key_pool_attempted,
            "Twelve Key Pool Error": key_pool_error,
            "Twelve Attempted": twelve_attempted,
            "Twelve Error": twelve_error,
            "Cache Used": cache_used,
            "Reload Eligible": reload_eligible,
            "Data Freshness": freshness,
            "Failure Reason": str(evidence.get("failure_reason") or evidence.get("reason") or ""),
        })

    loaded_now_count = sum(1 for row in status_rows if str(row.get("Load Status") or "").upper() in success_statuses)
    result = {
        **status,
        "group": CANONICAL_GROUP,
        "requested_symbols": selected,
        "loaded_symbols": loaded,
        "failed_symbols": failed,
        "status_rows": status_rows,
        "provider_summary": provider_summary,
        "loaded_now_count": loaded_now_count,
        "ready": bool(loaded),
        "complete": bool(selected) and loaded_now_count == len(selected),
        "message": (
            f"{loaded_now_count}/{len(selected)} canonical selected symbols are usable."
            if loaded_now_count else "Press Load Selected Data for 12-Symbol Ranking before calculation."
        ),
    }
    if isinstance(state, MutableMapping):
        status_df = pd.DataFrame(status_rows)
        if "Timeframe" in status_df.columns:
            status_df["Timeframe"] = status_df["Timeframe"].replace({"": tf, "nan": tf, "NaN": tf, "None": tf}).fillna(tf)
        state[CANONICAL_SYMBOL_LOAD_STATUS_KEY] = status_df
        state[CANONICAL_PROVIDER_TRACE_KEY] = provider_trace
        state[CANONICAL_RANKING_SYMBOLS_KEY] = list(selected)
        state[CANONICAL_RANKING_TIMEFRAME_KEY] = tf
        state["canonical_loaded_now_count"] = loaded_now_count
    return result



def reload_failed_symbols(
    state: MutableMapping[str, Any],
    group: Any,
    current_symbols: Any,
    timeframe: Any,
    *,
    progress_callback: Any = None,
) -> dict[str, Any]:
    """Retry only the latest failed/rejected exact symbols for one selector."""
    group_name = str(group or "SECOND").strip().upper()
    selected = normalize_symbols(current_symbols, limit=group_symbol_limit(group_name))
    tf = str(timeframe or "H4").strip().upper() or "H4"
    status = loaded_group_status(state, group_name, selected, tf)
    if status.get("stale"):
        raise ValueError("Selection or timeframe changed; use Load Selected Data first.")
    allowed_retry_states = {
        "FAILED", "FAILED_NO_DATA", "FAILED_VALIDATION", "EMPTY", "EMPTY_RESPONSE",
        "INVALID_DATA", "API_ERROR", "PROVIDER_UNAVAILABLE", "TEMPORARY_ERROR",
        "BELOW_MODULE_MINIMUM", "NO_GENUINE_CANDLES", "FAILED_EXPLICIT",
        "RUN_CIRCUIT_OPEN", "INSUFFICIENT", "SYMBOL_FAILED",
    }
    validations = status.get("validations") if isinstance(status.get("validations"), Mapping) else {}
    failed: list[str] = []
    for symbol in normalize_symbols(status.get("failed_symbols") or [], limit=None):
        if symbol not in selected:
            continue
        evidence = validations.get(symbol) if isinstance(validations.get(symbol), Mapping) else {}
        latest_state = str(evidence.get("failure_category") or evidence.get("failure_code") or evidence.get("status") or "FAILED").strip().upper()
        rows = int(evidence.get("rows") or evidence.get("genuine_rows") or 0)
        minimum_rows = int(evidence.get("minimum_rows") or 25)
        if latest_state in allowed_retry_states or rows < minimum_rows:
            failed.append(symbol)
    if not failed:
        record = _records(state).get(group_name)
        return dict(record) if isinstance(record, Mapping) else {
            "group": group_name, "timeframe": tf, "requested_symbols": selected,
            "loaded_symbols": [], "failed_symbols": [], "status": "READY",
        }
    return load_group_market_data(
        state, group_name, selected, tf,
        progress_callback=progress_callback,
        retry_symbols=failed,
        force_reload=True,
    )


def loaded_group_status(
    state: Mapping[str, Any], group: Any, current_symbols: Any, timeframe: Any,
) -> dict[str, Any]:
    group_name = str(group or "SECOND").strip().upper()
    selected = normalize_symbols(current_symbols, limit=group_symbol_limit(group_name))
    tf = str(timeframe or "H4").strip().upper() or "H4"
    record = _records(state).get(group_name)
    if not isinstance(record, Mapping):
        record = _restore_group_record_from_database(state, group_name, selected, tf)
    if not isinstance(record, Mapping):
        return {
            "group": group_name, "status": "NOT_LOADED", "ready": False,
            "requested_symbols": selected, "loaded_symbols": [], "failed_symbols": [],
            "stale": False, "message": "Press Load Selected Data before calculating.",
        }
    exact = str(record.get("selection_signature") or "") == selection_signature(selected, tf)
    loaded = normalize_symbols(record.get("loaded_symbols") or [], limit=None)
    failed = normalize_symbols(record.get("failed_symbols") or [], limit=None)
    loaded_timeframe = str(record.get("timeframe") or "").strip().upper()
    requested_before = normalize_symbols(record.get("requested_symbols") or [], limit=None)
    same_membership = set(requested_before) == set(selected) and len(requested_before) == len(selected)
    order_only_change = not exact and loaded_timeframe == tf and same_membership
    if order_only_change:
        # Multiselect widgets may normalize chip order on rerun. Candle identity
        # is symbol+timeframe, so a pure reorder never requires another API call.
        # Preserve the current selector order for the canonical ordered union.
        loaded = [symbol for symbol in selected if symbol in loaded]
        failed = [symbol for symbol in selected if symbol in failed]
        if isinstance(state, MutableMapping):
            records = _records(state)
            updated = dict(record)
            updated["requested_symbols"] = list(selected)
            updated["loaded_symbols"] = list(loaded)
            updated["failed_symbols"] = list(failed)
            updated["selection_signature"] = selection_signature(selected, tf)
            updated["order_reconciled_without_refetch"] = True
            report = updated.get("report")
            if isinstance(report, Mapping):
                report = dict(report)
                report["requested_symbols"] = list(selected)
                report["loaded_symbols"] = list(loaded)
                report["unresolved_symbols"] = list(failed)
                updated["report"] = report
            records[group_name] = updated
            state[LOAD_RECORDS_KEY] = records
            record = updated
        exact = True
    if not exact:
        changes = {
            "loaded_timeframe": loaded_timeframe or None,
            "current_timeframe": tf,
            "timeframe_changed": bool(loaded_timeframe and loaded_timeframe != tf),
            "added": [symbol for symbol in selected if symbol not in requested_before],
            "removed": [symbol for symbol in requested_before if symbol not in selected],
            "reordered": bool(same_membership and requested_before != selected),
        }
        return {
            **{key: value for key, value in record.items() if key != "report"},
            "group": group_name, "status": "STALE", "ready": False, "stale": True,
            "loaded_symbols": [], "selection_changes": changes,
            "message": "Selection membership or timeframe changed. Load this selector again.",
        }
    ready = bool(loaded)
    status = "FULL_READY" if ready and not failed else "PARTIAL_READY" if ready else "FAILED"
    return {
        **{key: value for key, value in record.items() if key != "report"},
        "group": group_name, "status": status, "ready": ready, "stale": False,
        "loaded_symbols": loaded, "failed_symbols": failed,
        "message": (
            f"{len(loaded)}/{len(selected)} selected symbols are calculation-ready (full or adaptive partial history)."
            if ready else "No selected symbol reached the genuine minimum calculation history. Reload after checking providers/API limits."
        ),
    }


def loaded_universe_status(
    state: Mapping[str, Any], configured: Mapping[str, Any], timeframe: Any,
) -> dict[str, Any]:
    """Return the canonical exact 12-symbol load record.

    The old per-selector union is retained only as a backward-compatible fallback
    when no canonical record exists yet.
    """
    tf = str(timeframe or "H4").strip().upper() or "H4"
    canonical_selected = canonical_universe_from_groups(configured, limit=MAX_CANONICAL_SYMBOLS)
    requested_union = list(canonical_selected)
    existing_selected = normalize_symbols(state.get(CANONICAL_SELECTED_KEY) or state.get("canonical_selected_symbols_20260705") or [], limit=MAX_CANONICAL_SYMBOLS)
    if canonical_selected:
        if isinstance(state, MutableMapping):
            publish_canonical_universe(state, canonical_selected, tf)
        canonical_status = loaded_canonical_status(state, canonical_selected, tf)
        records = _records(state)
        if isinstance(records.get(CANONICAL_GROUP), Mapping) or canonical_status.get("loaded_symbols") or canonical_status.get("stale"):
            report = records.get(CANONICAL_GROUP, {}).get("report") if isinstance(records.get(CANONICAL_GROUP), Mapping) else None
            raw = report.get("results") if isinstance(report, Mapping) and isinstance(report.get("results"), Mapping) else {}
            return {
                **canonical_status,
                "status": "READY" if canonical_status.get("complete") else "PARTIAL_READY" if canonical_status.get("loaded_symbols") else canonical_status.get("status", "NOT_LOADED"),
                "results": {symbol: raw[symbol] for symbol in canonical_status.get("loaded_symbols", []) if isinstance(raw.get(symbol), Mapping)},
                "load_ids": [str(records.get(CANONICAL_GROUP, {}).get("load_id"))] if isinstance(records.get(CANONICAL_GROUP), Mapping) and records.get(CANONICAL_GROUP, {}).get("load_id") else [],
                "group_status": {CANONICAL_GROUP: canonical_status},
                "timeframe": tf,
                "canonical": True,
            }
    elif existing_selected:
        canonical_status = loaded_canonical_status(state, existing_selected, tf)
        if canonical_status.get("loaded_symbols"):
            return {**canonical_status, "results": {}, "load_ids": [], "group_status": {CANONICAL_GROUP: canonical_status}, "timeframe": tf, "canonical": True}
    loaded: list[str] = []
    failed: list[str] = []
    stale_groups: list[str] = []
    result_payloads: dict[str, Any] = {}
    load_ids: list[str] = []
    group_status: dict[str, Any] = {}
    for group in ("FIRST", "SECOND", "THIRD"):
        current = normalize_symbols(configured.get(group) if isinstance(configured, Mapping) else [], limit=group_symbol_limit(group))
        status = loaded_group_status(state, group, current, tf)
        group_status[group] = status
        if status.get("stale"):
            stale_groups.append(group)
            continue
        record = _records(state).get(group)
        report = record.get("report") if isinstance(record, Mapping) else None
        raw = report.get("results") if isinstance(report, Mapping) and isinstance(report.get("results"), Mapping) else {}
        for symbol in normalize_symbols(status.get("loaded_symbols") or [], limit=None):
            if symbol not in loaded and isinstance(raw.get(symbol), Mapping):
                loaded.append(symbol)
                result_payloads[symbol] = raw[symbol]
        for symbol in normalize_symbols(status.get("failed_symbols") or [], limit=None):
            if symbol not in failed:
                failed.append(symbol)
        if isinstance(record, Mapping) and record.get("load_id"):
            load_ids.append(str(record.get("load_id")))
    aggregate_status = (
        "PARTIAL_READY" if loaded and (failed or stale_groups) else
        "READY" if loaded else
        "FAILED" if failed else "NOT_LOADED"
    )
    return {
        "ready": bool(loaded), "status": aggregate_status,
        "requested_symbols": requested_union,
        "loaded_symbols": loaded, "failed_symbols": failed, "stale_groups": stale_groups,
        "results": result_payloads, "load_ids": load_ids, "group_status": group_status,
        "timeframe": tf,
        "message": f"{len(loaded)} cumulative loaded symbol(s) are ready across all selectors." if loaded else "No current selector load is calculation-ready.",
    }


def activate_loaded_universe_for_run(
    state: MutableMapping[str, Any], scope: Any, configured: Mapping[str, Any], timeframe: Any,
) -> dict[str, Any]:
    """Activate every symbol loaded by any selector; the button controls depth only."""
    status = loaded_universe_status(state, configured, timeframe)
    if not status.get("ready"):
        return {"ok": False, **status}
    from core.calculation.run_orchestrator import MARKET_RESULTS_KEY
    loaded = normalize_symbols(status.get("loaded_symbols") or [], limit=None)
    requested = normalize_symbols(status.get("requested_symbols") or [symbol for group in configured.values() for symbol in normalize_symbols(group, limit=None)] if isinstance(configured, Mapping) else status.get("requested_symbols") or loaded, limit=MAX_CANONICAL_SYMBOLS)
    tf = str(timeframe or "H4").strip().upper() or "H4"
    active_report = {
        "run_id": "CUMULATIVE-" + sha256((tf + "|" + "|".join(status.get("load_ids") or [])).encode("utf-8")).hexdigest()[:20],
        "load_id": "+".join(status.get("load_ids") or []),
        "timeframe": tf, "results": dict(status.get("results") or {}),
        "requested_symbols": list(requested), "loaded_symbols": list(loaded),
        "unresolved_symbols": list(status.get("failed_symbols") or []),
        "complete": bool(status.get("loaded_symbols")) and not bool(status.get("failed_symbols")), "load_only": False,
        "canonical_selected_symbols": list(requested),
        "selector_load_status": status.get("status"),
        "configured_symbols": list(requested),
        "selector_failed_symbols": list(status.get("failed_symbols") or []),
        "calculation_reuses_preloaded_data": True,
        "source_groups": [group for group, group_status in status.get("group_status", {}).items() if group_status.get("ready")],
    }
    state[MARKET_RESULTS_KEY] = active_report
    state[CANONICAL_LOADED_KEY] = list(loaded)
    state["canonical_loaded_symbols_20260705"] = list(loaded)
    try:
        from core.current_result_sync_20260708 import sync_settings_source_of_truth
        sync_settings_source_of_truth(state, requested, tf, reason="activate_loaded_universe_for_run", clear_stale=False)
    except Exception:
        set_legacy_configured_symbols(state, list(requested))
        state["selected_symbols_for_run_20260705"] = list(requested)
        state["timeframe"] = tf
    if requested:
            set_legacy_calculation_symbol(state, requested[0], connector=True)
    state[REQUIRE_EXPLICIT_LOAD_KEY] = True
    state[LOADED_RUN_ACTIVE_KEY] = {
        "group": "ALL_LOADED", "scope": str(scope or "QUICK").strip().upper(),
        "load_id": active_report["load_id"], "loaded_symbols": list(loaded),
        "timeframe": tf, "activated_at": datetime.now(timezone.utc).isoformat(),
        "source_groups": active_report["source_groups"],
    }
    _publish_loaded_to_global_context(state, requested, loaded, status.get("failed_symbols") or [], active_report.get("results"), tf)
    return {"ok": True, **status, "loaded_symbols": loaded}


def activate_loaded_scope_for_run(
    state: MutableMapping[str, Any], scope: Any, current_symbols: Any, timeframe: Any,
) -> dict[str, Any]:
    """Publish only the exact validated group report for calculation reuse."""
    group = group_for_scope(scope)
    status = loaded_group_status(state, group, current_symbols, timeframe)
    if not status.get("ready"):
        return {"ok": False, **status}
    record = _records(state).get(group)
    report = record.get("report") if isinstance(record, Mapping) else None
    if not isinstance(report, Mapping):
        return {"ok": False, **status, "status": "MISSING_LOADED_REPORT", "message": "Loaded frames are unavailable; press Load again."}

    from core.calculation.run_orchestrator import MARKET_RESULTS_KEY
    loaded = normalize_symbols(status.get("loaded_symbols") or [], limit=None)
    active_report = copy.copy(dict(report))
    raw_results = report.get("results") if isinstance(report.get("results"), Mapping) else {}
    active_report["results"] = {symbol: raw_results[symbol] for symbol in loaded if symbol in raw_results}
    requested = normalize_symbols(current_symbols or loaded, limit=MAX_CANONICAL_SYMBOLS)
    active_report["requested_symbols"] = list(requested)
    active_report["loaded_symbols"] = list(loaded)
    active_report["unresolved_symbols"] = [symbol for symbol in requested if symbol not in set(loaded)]
    active_report["complete"] = not bool(active_report["unresolved_symbols"])
    active_report["calculation_reuses_preloaded_data"] = True
    state[MARKET_RESULTS_KEY] = active_report
    state[CANONICAL_LOADED_KEY] = list(loaded)
    state["canonical_loaded_symbols_20260705"] = list(loaded)
    state["timeframe"] = str(timeframe or "H4").strip().upper() or "H4"
    try:
        from core.current_result_sync_20260708 import sync_settings_source_of_truth
        sync_settings_source_of_truth(state, requested, state["timeframe"], reason="activate_loaded_scope_for_run", clear_stale=False)
    except Exception:
        set_legacy_configured_symbols(state, list(requested))
        state["selected_symbols_for_run_20260705"] = list(requested)
    if requested:
            set_legacy_calculation_symbol(state, requested[0], connector=True)
    state[REQUIRE_EXPLICIT_LOAD_KEY] = True
    state[LOADED_RUN_ACTIVE_KEY] = {
        "group": group,
        "scope": scope_for_group(group),
        "load_id": record.get("load_id"),
        "selection_signature": record.get("selection_signature"),
        "loaded_symbols": list(loaded),
        "timeframe": state["timeframe"],
        "activated_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"ok": True, **status, "loaded_symbols": loaded}


def active_loaded_run(state: Mapping[str, Any]) -> dict[str, Any]:
    value = state.get(LOADED_RUN_ACTIVE_KEY)
    return dict(value) if isinstance(value, Mapping) else {}


__all__ = [
    "LOAD_RECORDS_KEY", "CANONICAL_GROUP", "CANONICAL_SELECTED_KEY", "CANONICAL_LOADED_KEY",
    "CANONICAL_RANKING_SYMBOLS_KEY", "CANONICAL_RANKING_TIMEFRAME_KEY", "CANONICAL_SYMBOL_LOAD_STATUS_KEY",
    "CANONICAL_SYMBOL_CANDLES_KEY", "CANONICAL_PROVIDER_TRACE_KEY", "CANONICAL_LAST_LOAD_RUN_ID_KEY",
    "REQUIRE_EXPLICIT_LOAD_KEY", "LOADED_RUN_ACTIVE_KEY", "LAST_LOAD_KEY",
    "SELECTOR_KEY_ASSIGNMENT_STATE_KEY", "SELECTOR_WORKER_STATE_KEY", "SELECTOR_REQUEST_LEDGER_KEY",
    "ASSIGNED_TWELVE_KEY_STATE_KEY", "ASSIGNED_SELECTOR_STATE_KEY", "SELECTOR_TWELVE_ONLY_STATE_KEY",
    "EMERGENCY_CROSS_KEY_STATE_KEY", "SelectorKeyAssignment",
    "normalize_symbols", "is_valid_candle_df", "first_valid_df", "get_canonical_ranking_symbols",
    "canonical_universe_from_groups", "publish_canonical_universe", "group_symbol_limit", "group_for_scope", "scope_for_group", "selection_signature",
    "selector_key_assignment", "clear_circuit_breaker_for_symbols", "load_selector_with_assigned_key",
    "merge_selector_load_results", "load_all_selectors_safely", "refresh_all_selectors_safely",
    "load_group_market_data", "load_canonical_market_data", "loaded_canonical_status", "reload_failed_symbols", "loaded_group_status", "loaded_universe_status",
    "activate_loaded_scope_for_run", "activate_loaded_universe_for_run", "active_loaded_run",
]
