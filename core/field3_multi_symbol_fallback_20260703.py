"""Exact-symbol local Field 3 fallback for the Lunch selector.

This module is used only when a selected Settings/Top-10 symbol has no readable
completed child snapshot.  It calculates the existing three Field 3 regime
windows from that symbol's own completed selected-timeframe OHLC.  It never borrows another
symbol and never overwrites the protected production canonical result.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any
import gzip

import numpy as np
import pandas as pd

from core.field10_adaptive_regime_metrics_20260702 import compute_adaptive_regime_metrics
from core.timeframe_window_contract_20260706 import selected_timeframe, window_contract
from core.multi_symbol_field10_20260701 import (
    _read_cache_payload,
    _resolved_cache_path,
    normalize_symbol,
)

VERSION = "field3-local-multi-symbol-fallback-20260703-v1"
DISPLAY_KEY = "field3_local_symbol_snapshot_20260703"


def _canonical(state: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        from core.canonical_lookup_20260626 import resolve_canonical
        value = resolve_canonical(state)
        if isinstance(value, Mapping) and value:
            return value
    except Exception:
        pass
    for key in (
        "canonical_decision_result_20260617",
        "canonical_result_20260617",
        "last_valid_canonical_decision_result_20260617",
    ):
        value = state.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _current_symbol(state: Mapping[str, Any]) -> str:
    canonical = _canonical(state)
    return normalize_symbol(
        canonical.get("symbol")
        or state.get("active_snapshot_symbol_20260702")
        or state.get("symbol")
        or "EURUSD"
    )


def _saved_state(symbol: str) -> Mapping[str, Any]:
    path = _resolved_cache_path(symbol)
    if not path.is_file():
        return {}
    try:
        payload = _read_cache_payload(path)
        value = payload.get("state")
        return value if isinstance(value, Mapping) else {}
    except Exception:
        return {}


def _source_state(state: Mapping[str, Any], symbol: str) -> tuple[dict[str, Any], str]:
    target = normalize_symbol(symbol)
    if _current_symbol(state) == target:
        return dict(state), "CURRENT_EXACT_SYMBOL_STATE"
    cached = _saved_state(target)
    if cached:
        return dict(cached), "SAVED_EXACT_SYMBOL_SNAPSHOT"
    return {}, "NO_EXACT_SYMBOL_STATE"


def _regime_bias(regime: Any, z_value: Any = None, shadow: Any = None) -> str:
    text = str(regime or "").upper()
    if "BULL" in text:
        return "BUY"
    if "BEAR" in text:
        return "SELL"
    try:
        z = float(z_value)
        if np.isfinite(z) and abs(z) >= 0.10:
            return "BUY" if z > 0 else "SELL"
    except Exception:
        pass
    shadow_text = str(shadow or "").upper()
    if "BUY" in shadow_text:
        return "BUY"
    if "SELL" in shadow_text:
        return "SELL"
    return "WAIT"


def _reliability(z_value: Any, quality: Any) -> float:
    try:
        z = abs(float(z_value))
        if not np.isfinite(z):
            z = 0.0
    except Exception:
        z = 0.0
    quality_score = 100.0 if str(quality).upper() == "PASS" else 65.0
    return round(float(np.clip(48.0 + z * 18.0 + (quality_score - 65.0) * 0.25, 35.0, 94.0)), 2)


def _build_tables(work: Mapping[str, Any], symbol: str, source: str) -> dict[str, Any]:
    from core.lunch_h1_data_quality_v13 import build_regime_decision_matrix, cached_completed_ohlc

    canonical = dict(_canonical(work))
    canonical["symbol"] = symbol
    canonical.setdefault("timeframe", str(work.get("timeframe") or "H4").upper())
    frame = cached_completed_ohlc(work)
    if frame.empty:
        return {"ok": False, "status": "NO_EXACT_SYMBOL_OHLC", "symbol": symbol, "source": source}

    timeframe = selected_timeframe(canonical.get("timeframe") or work.get("timeframe") or "H4")
    bars_per_day = int(window_contract(timeframe)["bars_per_day"])
    maximum_window = bars_per_day * 25
    matrix = build_regime_decision_matrix(work, canonical, limit=maximum_window)
    if matrix.empty:
        return {"ok": False, "status": "NO_COMPLETED_TIMEFRAME_MATRIX", "symbol": symbol, "source": source, "timeframe": timeframe}

    try:
        adaptive = compute_adaptive_regime_metrics(frame, timeframe=timeframe)
    except TypeError:
        # Compatibility for injected legacy test adapters accepting frame only.
        adaptive = compute_adaptive_regime_metrics(frame)
    specs = (
        ("lower", "Lower Standard", "Lower 1-Day", bars_per_day),
        ("medium", "Middle Standard", "Middle 5-Day", bars_per_day * 5),
        ("higher", "Higher Standard", "Higher 25-Day", bars_per_day * 25),
    )
    summaries: list[dict[str, Any]] = []
    details: dict[str, pd.DataFrame] = {}
    latest = matrix.iloc[0]
    for key, standard, prefix, window in specs:
        regime_col = f"{prefix} Regime"
        z_col = f"{prefix} Z-Score"
        regime = latest.get(regime_col)
        z_value = latest.get(z_col)
        bias = _regime_bias(regime, z_value, latest.get("Shadow Decision"))
        if key == "higher" and adaptive.get("ok"):
            adaptive_bias = str(adaptive.get("bias") or "").upper()
            if bias == "WAIT" and adaptive_bias in {"BUY", "SELL"}:
                bias = adaptive_bias
            regime = adaptive.get("regime") or regime
        reliability = _reliability(z_value, latest.get("Data Quality"))
        if key == "higher" and adaptive.get("ok"):
            reliability = round(float(adaptive.get("calibrated_bias_probability") or reliability), 2)
        summaries.append({
            "Symbol": symbol,
            "Standard": standard,
            "Window": f"{window} {timeframe} candles",
            "Timeframe": timeframe,
            "Regime": regime,
            "Regime Bias": bias,
            "Less-Risky Bias": bias,
            "Reliability": reliability,
            "Sample Count": min(int(len(matrix)), window),
            "Regime Probability": adaptive.get("regime_probability") if key == "higher" else round(min(94.0, 50.0 + abs(float(z_value or 0.0)) * 15.0), 2),
            "Transition Risk 1H": adaptive.get("transition_risk_1h") if key == "higher" else None,
            "Transition Risk 3H": adaptive.get("transition_risk_3h") if key == "higher" else None,
            "Transition Risk 6H": adaptive.get("transition_risk_6h") if key == "higher" else None,
            "Data Quality Grade": "A" if len(matrix) >= window and str(latest.get("Data Quality")).upper() == "PASS" else ("B" if len(matrix) >= min(window, 120) else "C"),
            "Evidence Source": f"{source} · EXISTING FIELD3 {prefix.upper()} WINDOW",
            "Production Decision Changed": "NO",
        })
        detail = matrix.copy()
        detail.insert(0, "Symbol", symbol)
        detail.insert(1, "Standard", standard)
        detail["Regime"] = detail.get(regime_col)
        detail["Z-Score"] = pd.to_numeric(detail.get(z_col), errors="coerce")
        detail["Regime Bias"] = [
            _regime_bias(reg, z, shadow)
            for reg, z, shadow in zip(
                detail["Regime"], detail["Z-Score"], detail.get("Shadow Decision", pd.Series(index=detail.index, dtype=object))
            )
        ]
        detail["Less-Risky Bias"] = detail["Regime Bias"]
        detail["Reliability"] = [
            _reliability(z, quality)
            for z, quality in zip(detail["Z-Score"], detail.get("Data Quality", pd.Series(index=detail.index, dtype=object)))
        ]
        keep = [
            column for column in (
                "Symbol", "Standard", "Broker Time", "event_time_utc", "Time", "Regime", "Z-Score",
                "Regime Bias", "Less-Risky Bias", "Reliability", "Decision Level /10",
                "Regime Decision Level /10", "Shadow Decision", "Actionability", "Trend Agreement",
                "Data Quality Score /100", "Data Quality", "Source Provenance", "Production Decision Changed",
            ) if column in detail.columns
        ]
        details[key] = detail[keep].head(min(maximum_window, window)).reset_index(drop=True)

    completed = None
    for column in ("Broker Time", "event_time_utc", "Time"):
        if column in matrix.columns and len(matrix):
            completed = matrix.iloc[0].get(column)
            if completed not in (None, ""):
                break
    return {
        "ok": True,
        "status": "LOCAL_FIELD3_READY",
        "symbol": symbol,
        "source": source,
        "timeframe": timeframe,
        "summary": pd.DataFrame(summaries),
        "details": details,
        "matrix": matrix,
        "completed_broker_candle": completed,
        "rows": int(len(matrix)),
        "adaptive": adaptive,
        "version": VERSION,
    }


def build_field3_local_snapshot(
    state: MutableMapping[str, Any],
    symbol: Any,
    *,
    allow_provider_fetch: bool = True,
) -> dict[str, Any]:
    """Build one exact-symbol Field 3 display snapshot.

    Provider access is attempted only when no saved/current exact-symbol selected-timeframe frame
    exists. The provider work is isolated in a temporary state mapping.
    """
    target = normalize_symbol(symbol)
    work, source = _source_state(state, target)
    result = _build_tables(work, target, source) if work else {"ok": False, "status": "NO_EXACT_SYMBOL_STATE"}
    if result.get("ok"):
        state[DISPLAY_KEY] = result
        return result

    fetch_report: Mapping[str, Any] = {}
    if allow_provider_fetch:
        try:
            from core.multi_symbol_api_runtime_20260702 import CACHE_KEY, prepare_symbol_market_data
            temp = dict(state)
            existing_cache = state.get(CACHE_KEY)
            temp[CACHE_KEY] = dict(existing_cache) if isinstance(existing_cache, Mapping) else {}
            fetch_report = prepare_symbol_market_data(temp, target, force=False, max_attempts=2)
            report_symbol = normalize_symbol(fetch_report.get("symbol") or target)
            if fetch_report.get("ok") and report_symbol == target:
                result = _build_tables(temp, target, f"LOCAL_PROVIDER_OR_EXACT_CANDLE_CACHE:{fetch_report.get('status')}")
                if result.get("ok"):
                    result["provider_report"] = dict(fetch_report)
                    state[DISPLAY_KEY] = result
                    return result
        except Exception as exc:
            fetch_report = {"ok": False, "status": "PROVIDER_FALLBACK_ERROR", "error": f"{type(exc).__name__}: {exc}"}

    result = {
        "ok": False,
        "status": result.get("status") or "NO_EXACT_SYMBOL_TIMEFRAME_DATA",
        "symbol": target,
        "source": source,
        "provider_report": dict(fetch_report),
        "message": f"No saved exact-symbol {str(state.get('timeframe') or 'H4').upper()} snapshot or usable provider frame was available. Another symbol was not borrowed.",
        "version": VERSION,
    }
    state[DISPLAY_KEY] = result
    return result


__all__ = ["VERSION", "DISPLAY_KEY", "build_field3_local_snapshot"]
