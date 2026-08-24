"""Pre-render validation and bounded self-repair for the multi-symbol Lunch flow.

Streamlit has no background worker in this application.  "Continuous" therefore
means this validator runs at every Settings completion and Lunch render, while
expensive repairs are fingerprinted and executed at most once per generation.
It never calls a market API and never modifies an immutable Field 10 publication;
old same-day publications receive a transparent display overlay instead.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from hashlib import sha256
from typing import Any
import math

import numpy as np
import pandas as pd

from core.field10_adaptive_regime_metrics_20260702 import compute_adaptive_regime_metrics
from core.field3_bias_resolver_20260703 import normalize_bias, resolve_standard_evidence
from core.timeframe_window_contract_20260706 import (
    evidence_contract, insufficiency_label, minimum_calculation_candles,
    selected_timeframe as resolve_selected_timeframe, validated_estimate_label,
)
from core.multi_symbol_field10_20260701 import (
    ACTIVE_KEY,
    DISPLAY_SYMBOL_KEY,
    LUNCH_SYMBOL_WIDGET_KEY,
    MAIN_SYMBOL_KEY,
    MANIFEST_KEY,
    SELECTED_KEY,
    _cache_path,
    _read_cache_payload,
    _resolved_cache_path,
    available_saved_symbols,
    recover_symbol_universe,
    normalize_selected,
    normalize_symbol,
)

VERSION = "multi-symbol-pre-render-validation-20260702-v1"
FIELD1_LABEL = "1. Open / Close — Full Metric 25-Day History + Decision Tables"
FIELD10_LABEL = "10. Open / Close — Multi-Symbol Rank, Data Quality and Higher-Regime Monitor"

_METRIC_FALLBACK_MAP = {
    "Regime Probability": "regime_probability",
    "Regime Entropy": "regime_entropy",
    "Posterior Margin": "posterior_margin",
    "Regime Age": "regime_age",
    "Expected Regime Duration": "expected_regime_duration",
    "Estimated Remaining Duration": "estimated_remaining_duration",
    "Transition Risk 1H": "transition_risk_1h",
    "Transition Risk 3H": "transition_risk_3h",
    "Transition Risk 6H": "transition_risk_6h",
    "Transition Risk 24H": "transition_risk_24h",
    "Expected Return 12H (%)": "expected_return_12h",
    "Expected Return 24H (%)": "expected_return_24h",
    "Expected Return 36H (%)": "expected_return_36h",
    "Calibrated Bias Probability": "calibrated_bias_probability",
    "Brier Score": "brier_score",
    "Forecast Accuracy 1H": "forecast_accuracy_1h",
    "Forecast Accuracy 3H": "forecast_accuracy_3h",
    "Forecast Accuracy 6H": "forecast_accuracy_6h",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except Exception:
        return False


def _bias(value: Any) -> str | None:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    text = str(value).upper()
    if "BUY" in text or text.strip() in {"BULL", "LONG", "UP"}:
        return "BUY"
    if "SELL" in text or text.strip() in {"BEAR", "SHORT", "DOWN"}:
        return "SELL"
    if any(token in text for token in ("WAIT", "HOLD", "NO TRADE", "BLOCK")):
        return "WAIT"
    return None


def _find_ohlc(value: Any, depth: int = 0, seen: set[int] | None = None) -> pd.DataFrame:
    if depth > 5:
        return pd.DataFrame()
    seen = seen if seen is not None else set()
    if isinstance(value, (Mapping, list, tuple, pd.DataFrame)):
        marker = id(value)
        if marker in seen:
            return pd.DataFrame()
        seen.add(marker)
    if isinstance(value, pd.DataFrame):
        cols = {str(c).strip().lower() for c in value.columns}
        if "close" in cols and ("time" in cols or "timestamp" in cols or isinstance(value.index, pd.DatetimeIndex)):
            return value
        return pd.DataFrame()
    if isinstance(value, Mapping):
        preferred = (
            "canonical_completed_ohlc_df_20260617", "calculation_staging_ohlc_df_20260617",
            "last_df", "data", "ohlc", "market_data", "df",
        )
        for key in preferred:
            if key in value:
                found = _find_ohlc(value[key], depth + 1, seen)
                if not found.empty:
                    return found
        for child in value.values():
            found = _find_ohlc(child, depth + 1, seen)
            if not found.empty:
                return found
    if isinstance(value, (list, tuple)):
        for child in value[:50]:
            found = _find_ohlc(child, depth + 1, seen)
            if not found.empty:
                return found
    return pd.DataFrame()


def _find_higher_bias(value: Any, depth: int = 0, seen: set[int] | None = None) -> str | None:
    """Compatibility wrapper around the standard-aware Field 3 resolver."""
    del depth, seen
    return normalize_bias(resolve_standard_evidence(value, "higher").get("bias"))


def _find_standard_bias(value: Any, standard: str, depth: int = 0, seen: set[int] | None = None) -> str | None:
    """Find one exact Field 3 standard without borrowing another standard."""
    del depth, seen
    return normalize_bias(resolve_standard_evidence(value, standard).get("bias"))

def _is_blank(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    return str(value).strip().upper() in {"", "N/A", "NA", "NONE", "NULL", "UNAVAILABLE", "NAN", "<NA>"}


def _quality_grade(sample_count: int, coverage: float) -> str:
    if sample_count >= 500 and coverage >= 80:
        return "A"
    if sample_count >= 250 and coverage >= 70:
        return "B"
    if sample_count >= 100 and coverage >= 50:
        return "C"
    return "D"


def _text(value: Any, default: str = "") -> str:
    return default if _is_blank(value) else str(value).strip()


def _cached_symbol_state(symbol: str) -> Mapping[str, Any]:
    path = _resolved_cache_path(symbol)
    if not path.is_file():
        return {}
    try:
        payload = _read_cache_payload(path)
        state = payload.get("state")
        return state if isinstance(state, Mapping) else {}
    except Exception:
        return {}



def _percent_number(value: Any) -> float | None:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    text = str(value).strip().replace("%", "")
    try:
        number = float(text)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    if 0.0 <= number <= 1.0:
        number *= 100.0
    return round(float(np.clip(number, 0.0, 100.0)), 2)


def _bias_from_regime(regime: Any) -> str | None:
    text = str(regime or "").strip().upper()
    if "BULL" in text or text in {"UP", "LONG"}:
        return "BUY"
    if "BEAR" in text or text in {"DOWN", "SHORT"}:
        return "SELL"
    return None


def _exact_symbol_state(state: Mapping[str, Any], symbol: str) -> Mapping[str, Any]:
    """Return only evidence whose canonical identity matches ``symbol``."""
    target = normalize_symbol(symbol)
    current = normalize_symbol(_canonical(state).get("symbol") or state.get("active_snapshot_symbol_20260702") or state.get("symbol"), default="")
    if current == target:
        return state
    return _cached_symbol_state(target)


def build_field3_higher_standard_multi_symbol_table(
    state: Mapping[str, Any],
    selected_symbols: Sequence[Any] | None = None,
    *,
    parent_run_id: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Create the Field 10 top table from each symbol's Field 3 Higher row.

    Source precedence is strict: identity-verified child publication, the exact
    symbol runtime snapshot, then the currently active exact-symbol state. A
    local adaptive selected-timeframe calculation is used only when the saved Higher row has no
    directional bias. No other symbol or lower/middle standard is borrowed.
    """
    universe = recover_symbol_universe(state) if isinstance(state, MutableMapping) else {
        "selected_symbols": normalize_selected(selected_symbols or []),
        "parent_run_id": str(parent_run_id or ""),
    }
    selected = normalize_selected(selected_symbols or universe.get("selected_symbols") or [])
    parent = str(parent_run_id or universe.get("parent_run_id") or "")
    if not selected:
        current = normalize_symbol(_canonical(state).get("symbol") or state.get("symbol") or "EURUSD")
        selected = [current]

    selected_timeframe = str(state.get("timeframe") or _canonical(state).get("timeframe") or "H1").upper()
    rows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for symbol in selected:
        exact_state = _exact_symbol_state(state, symbol)
        evidence: dict[str, Any] = {}
        evidence_source = ""
        metadata: Mapping[str, Any] = {}

        if parent:
            try:
                from core.child_generation_contract_20260702 import load_child_contract_tables
                from core.multi_symbol_field10_20260701 import DB_PATH
                child = load_child_contract_tables(path=DB_PATH, parent_run_id=parent, symbol=symbol, timeframe=selected_timeframe)
                if child.get("ok"):
                    evidence = resolve_standard_evidence(child.get("field3_current"), "higher")
                    metadata = child.get("metadata") if isinstance(child.get("metadata"), Mapping) else {}
                    if evidence:
                        evidence_source = "FIELD3_CHILD_PUBLICATION_CURRENT_PARENT"
            except Exception as exc:
                diagnostics.append({"symbol": symbol, "stage": "child_publication", "error": f"{type(exc).__name__}: {exc}"})

        # A cumulative Field 10 view spans the independent Super/Quick/Full
        # parent runs.  Recover only this exact symbol's newest completed child;
        # never borrow another symbol or another standard.
        if not evidence:
            try:
                from core.child_generation_contract_20260702 import load_latest_child_contract_tables
                from core.multi_symbol_field10_20260701 import DB_PATH
                child = load_latest_child_contract_tables(path=DB_PATH, symbol=symbol, timeframe=selected_timeframe)
                if child.get("ok"):
                    evidence = resolve_standard_evidence(child.get("field3_current"), "higher")
                    metadata = child.get("metadata") if isinstance(child.get("metadata"), Mapping) else {}
                    if evidence:
                        evidence_source = "FIELD3_CHILD_PUBLICATION_LATEST_EXACT_SYMBOL"
            except Exception as exc:
                diagnostics.append({"symbol": symbol, "stage": "latest_exact_child_publication", "error": f"{type(exc).__name__}: {exc}"})

        if not evidence:
            evidence = resolve_standard_evidence(exact_state, "higher")
            if evidence:
                evidence_source = "FIELD3_EXACT_SYMBOL_SNAPSHOT"

        frame = _find_ohlc(exact_state)
        adaptive = compute_adaptive_regime_metrics(frame, timeframe=exact_state.get("timeframe") or _canonical(exact_state).get("timeframe"))
        adaptive_ok = bool(adaptive.get("ok"))
        stored_bias = normalize_bias(evidence.get("bias"))
        regime = evidence.get("regime") or adaptive.get("regime")
        regime_bias = _bias_from_regime(regime)
        if stored_bias in {"BUY", "SELL"}:
            bias = stored_bias
            bias_source = evidence_source
        elif regime_bias in {"BUY", "SELL"}:
            bias = regime_bias
            bias_source = f"{evidence_source or 'FIELD3'}_REGIME_DIRECTION"
        else:
            bias = normalize_bias(adaptive.get("bias")) if adaptive_ok else stored_bias
            bias_source = "EXACT_SYMBOL_LOCAL_H1_ADAPTIVE" if bias in {"BUY", "SELL"} else (evidence_source or "NO_DIRECTIONAL_EVIDENCE")
        if bias not in {"BUY", "SELL"}:
            bias = "WAIT"

        reliability = _percent_number(evidence.get("reliability"))
        if reliability is None:
            reliability = _percent_number(adaptive.get("calibrated_reliability") or adaptive.get("calibrated_bias_probability"))
        probability = _percent_number(evidence.get("regime_probability"))
        if probability is None:
            probability = _percent_number(adaptive.get("regime_probability"))
        sample_count = evidence.get("sample_count")
        try:
            sample_count = int(float(sample_count))
        except Exception:
            sample_count = int(len(frame)) if isinstance(frame, pd.DataFrame) else 0
        quality = evidence.get("data_quality") or _quality_grade(sample_count, 100.0 if adaptive_ok else 0.0)
        transition_3h = _percent_number(evidence.get("transition_risk_3h"))
        transition_6h = _percent_number(evidence.get("transition_risk_6h"))
        transition_24h = _percent_number(evidence.get("transition_risk_24h"))
        if transition_3h is None:
            transition_3h = _percent_number(adaptive.get("transition_risk_3h"))
        if transition_6h is None:
            transition_6h = _percent_number(adaptive.get("transition_risk_6h"))
        if transition_24h is None:
            transition_24h = _percent_number(adaptive.get("transition_risk_24h"))
        expected_return_12h = adaptive.get("expected_return_12h") if adaptive_ok else None
        expected_return_24h = adaptive.get("expected_return_24h") if adaptive_ok else None
        expected_return_36h = adaptive.get("expected_return_36h") if adaptive_ok else None
        completed = (
            metadata.get("completed_broker_candle") or evidence.get("broker_time")
            or _canonical(exact_state).get("completed_broker_candle")
            or _canonical(exact_state).get("latest_completed_candle_time")
            or _canonical(exact_state).get("completed_candle_utc")
        )
        if not completed and isinstance(frame, pd.DataFrame) and not frame.empty:
            lookup = {str(column).strip().lower().replace("_", " "): column for column in frame.columns}
            time_column = next((lookup.get(name) for name in ("broker candle time", "time", "timestamp", "datetime", "date") if lookup.get(name) is not None), None)
            if time_column is not None:
                stamps = pd.to_datetime(frame[time_column], errors="coerce", utc=True).dropna()
                completed = stamps.max().isoformat() if not stamps.empty else None
        score = (
            0.45 * float(reliability or 0.0)
            + 0.35 * float(probability or 0.0)
            + 0.20 * max(0.0, 100.0 - float(transition_6h if transition_6h is not None else 100.0))
        )
        if bias == "WAIT":
            score -= 25.0
        selected_timeframe = str(
            metadata.get("timeframe")
            or _canonical(exact_state).get("timeframe")
            or state.get("timeframe")
            or "H4"
        ).upper()
        history_contract = evidence_contract(timeframe=selected_timeframe, available=sample_count)
        history_label = str(history_contract.get("History Status Label") or insufficiency_label(timeframe=selected_timeframe, available=sample_count))
        estimate_label = str(history_contract.get("Estimate Status Label") or validated_estimate_label(timeframe=selected_timeframe, available=sample_count))
        rows.append({
            "Rank": 0,
            "Symbol": symbol,
            "Higher Standard Regime": str(regime or history_label),
            "Higher-Standard Bias": bias,
            "Less-Risky Bias": bias,
            "Reliability": reliability if reliability is not None else history_label,
            "Regime Probability": probability if probability is not None else history_label,
            "Transition Risk 3H": transition_3h if transition_3h is not None else history_label,
            "Transition Risk 6H": transition_6h if transition_6h is not None else history_label,
            "Transition Risk 24H": transition_24h if transition_24h is not None else history_label,
            "Expected Return 12H (%)": expected_return_12h if _finite(expected_return_12h) else estimate_label,
            "Expected Return 24H (%)": expected_return_24h if _finite(expected_return_24h) else estimate_label,
            "Expected Return 36H (%)": expected_return_36h if _finite(expected_return_36h) else estimate_label,
            "Sample Count": sample_count,
            "Data Quality": str(quality),
            "Evidence Source": bias_source,
            "Snapshot Status": "DIRECTIONAL" if bias in {"BUY", "SELL"} else "WAIT — NO VERIFIED DIRECTION",
            "Completed Broker Candle": completed or history_label,
            "Comparative Score": round(score, 4),
            "Evidence Tier": history_contract.get("Evidence Tier"),
            "Coverage %": history_contract.get("Coverage Percent"),
            "Required Candle Count": history_contract.get("Required Candle Count"),
        })

    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.sort_values(["Comparative Score", "Symbol"], ascending=[False, True], kind="mergesort").reset_index(drop=True)
        table["Rank"] = range(1, len(table) + 1)
    report = {
        "ok": bool(len(table)) and set(table.get("Symbol", pd.Series(dtype=str))) == set(selected),
        "status": "COMPLETE" if len(table) == len(selected) else "PARTIAL",
        "selected_symbols": selected,
        "row_count": int(len(table)),
        "directional_rows": int(table["Higher-Standard Bias"].isin(["BUY", "SELL"]).sum()) if not table.empty else 0,
        "wait_rows": int(table["Higher-Standard Bias"].eq("WAIT").sum()) if not table.empty else 0,
        "diagnostics": diagnostics,
        "version": VERSION,
    }
    return table, report

def build_field10_display_overlay(
    current: pd.DataFrame,
    selected_symbols: Sequence[Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build a complete, read-only Field 10 priority view for the selected universe.

    The immutable morning publication is never changed. ``Eligible Rank`` keeps
    its original safety-gated rank, while ``Rank`` is a comparative all-symbol
    ordering so every selected instrument remains visible. Missing derived
    metrics are recovered only from that symbol's own saved local H1 snapshot.
    """
    out = current.copy() if isinstance(current, pd.DataFrame) else pd.DataFrame()
    selected = normalize_selected(selected_symbols or [])
    if "Symbol" not in out.columns:
        out["Symbol"] = pd.Series(dtype=object)
    existing_symbols = [normalize_symbol(value) for value in out["Symbol"].tolist()]
    for symbol in selected:
        if symbol not in existing_symbols:
            out = pd.concat([out, pd.DataFrame([{
                "Symbol": symbol,
                "Publication Status": "LOCAL_RECOVERY_VIEW",
                "Entry Permission": "EVIDENCE CHECK",
                "Safety Veto": "CLEAR",
            }])], ignore_index=True, sort=False)
            existing_symbols.append(symbol)
    if out.empty:
        return out, {
            "ok": False, "status": "NO_FIELD10_ROWS_OR_SELECTED_SYMBOLS", "repaired_rows": 0,
            "selected_symbols": selected, "immutable_source_modified": False, "version": VERSION,
        }

    priority_columns = (
        "Rank", "Eligible Rank", "Symbol", "Stable Daily Bias", "Lower-Standard Bias",
        "Higher-Standard Bias", "Less-Risky Bias", "Entry Permission", "Safety Web",
        "Regime Probability", "Regime Entropy", "Posterior Margin", "Regime Age",
        "Expected Regime Duration", "Estimated Remaining Duration",
        "Transition Risk 1H", "Transition Risk 3H", "Transition Risk 6H",
        "Transition Risk 24H", "Expected Return 12H (%)",
        "Expected Return 24H (%)", "Expected Return 36H (%)",
        "Calibrated Bias Probability", "Brier Score", "Forecast Accuracy 1H",
        "Forecast Accuracy 3H", "Forecast Accuracy 6H", "Data Quality",
        "Evidence Coverage", "Coverage %", "Reliability Score", "Data Status",
        "Fallback Level", "Display Data Source", "Freshness Status",
        "Block Reason", "Snapshot Status", "Comparative Rank Score",
    )
    for column in priority_columns:
        if column not in out.columns:
            out[column] = pd.NA
    if "Daily Rank" in out.columns:
        out["Eligible Rank"] = out["Daily Rank"]

    repaired_rows = 0
    details: list[dict[str, Any]] = []
    metric_columns = list(_METRIC_FALLBACK_MAP)
    score_values: dict[int, float] = {}
    # Legacy display text was "Insufficient Local History" for every missing
    # cell. The repaired overlay uses typed, provenance-aware fallback labels.

    for index, row in out.iterrows():
        symbol = normalize_symbol(row.get("Symbol"))
        out.at[index, "Symbol"] = symbol
        cached = _cached_symbol_state(symbol)
        frame = _find_ohlc(cached)
        adaptive = compute_adaptive_regime_metrics(frame, timeframe=cached.get("timeframe") or _canonical(cached).get("timeframe"))
        adaptive_ok = bool(adaptive.get("ok"))
        changed: list[str] = []

        lower_bias = _find_standard_bias(cached, "lower")
        higher_bias = _find_standard_bias(cached, "higher") or _find_higher_bias(cached)
        adaptive_bias = _bias(adaptive.get("bias"))
        # A generic WAIT must not mask a directional exact-symbol H1 result.
        # BUY/SELL from the requested Field 3 standard remains authoritative.
        higher_bias = higher_bias if higher_bias in {"BUY", "SELL"} else adaptive_bias or higher_bias
        lower_bias = lower_bias if lower_bias in {"BUY", "SELL"} else adaptive_bias or lower_bias

        for column, value in (
            ("Lower-Standard Bias", lower_bias),
            ("Higher-Standard Bias", higher_bias),
        ):
            if value and (_is_blank(row.get(column)) or _bias(row.get(column)) not in {"BUY", "SELL", "WAIT"}):
                out.at[index, column] = value
                changed.append(column)

        for column in ("Stable Daily Bias", "Less-Risky Bias"):
            stored = _bias(row.get(column))
            if higher_bias in {"BUY", "SELL"} and stored not in {"BUY", "SELL"}:
                stored_column = f"Stored {column}"
                if stored_column not in out.columns:
                    out[stored_column] = pd.NA
                out.at[index, stored_column] = row.get(column)
                out.at[index, column] = higher_bias
                changed.append(column)
            elif _is_blank(row.get(column)):
                out.at[index, column] = higher_bias or adaptive_bias or "WAIT"
                changed.append(column)

        regime = _text(row.get("Higher Standard Regime")).upper()
        if regime in {"", "UNAVAILABLE", "N/A", "NONE", "WAIT"} and adaptive_ok:
            out.at[index, "Higher Standard Regime"] = adaptive.get("regime")
            changed.append("Higher Standard Regime")

        for column, key in _METRIC_FALLBACK_MAP.items():
            if column not in out.columns:
                out[column] = pd.NA
            if not _finite(row.get(column)) and _finite(adaptive.get(key)):
                out.at[index, column] = adaptive.get(key)
                changed.append(column)

        # Transition Risk columns are the single authoritative leaving-state probabilities.

        safety = _text(row.get("Safety Veto"), "CLEAR").upper()
        hard_block = safety in {"BLOCK", "BLOCKED", "VETO", "BLOCK_NEW_ENTRIES"}
        permission = _text(row.get("Entry Permission")).upper()
        if hard_block:
            out.at[index, "Entry Permission"] = "BLOCKED"
            out.at[index, "Safety Web"] = "BLOCK"
            block_reason = f"Hard safety veto: {safety}"
        elif adaptive_ok:
            if permission in {"", "BLOCKED", "NO TRADE", "WAIT", "UNAVAILABLE", "RESEARCH ONLY", "EVIDENCE CHECK"}:
                if "Stored Entry Permission" not in out.columns:
                    out["Stored Entry Permission"] = pd.NA
                out.at[index, "Stored Entry Permission"] = row.get("Entry Permission")
                out.at[index, "Entry Permission"] = "CAUTION"
                changed.append("Entry Permission")
            out.at[index, "Safety Web"] = "CAUTION" if str(out.at[index, "Entry Permission"]).upper() == "CAUTION" else "CLEAR"
            original_reason = _text(row.get("Block Reason")) or _text(row.get("Explanation"))
            block_reason = original_reason if original_reason and original_reason.upper() not in {"N/A", "UNAVAILABLE"} else "No hard safety block; review confidence and execution gates"
        else:
            out.at[index, "Entry Permission"] = "EVIDENCE CHECK"
            out.at[index, "Safety Web"] = "CAUTION"
            block_reason = "No usable symbol-specific local H1 history was found"
        out.at[index, "Block Reason"] = block_reason

        finite_metrics = sum(_finite(out.at[index, column]) for column in metric_columns if column in out.columns)
        bias_evidence = sum(_bias(out.at[index, column]) in {"BUY", "SELL"} for column in ("Stable Daily Bias", "Higher-Standard Bias", "Less-Risky Bias"))
        sample_count = int(len(frame)) if isinstance(frame, pd.DataFrame) else 0
        coverage = 100.0 * (finite_metrics + bias_evidence + (1 if sample_count >= 80 else 0)) / (len(metric_columns) + 4)
        coverage = float(np.clip(coverage, 0.0, 100.0))
        out.at[index, "Evidence Coverage"] = round(coverage, 2)
        out.at[index, "Coverage %"] = round(coverage, 2)
        reliability_value = row.get("Reliability Score") if "Reliability Score" in out.columns else row.get("Reliability")
        if not _finite(reliability_value):
            reliability_value = min(100.0, coverage * (0.85 if adaptive_ok else 0.35))
        out.at[index, "Reliability Score"] = round(float(reliability_value), 2)
        adaptive_full_history = bool(adaptive.get("full_history")) if adaptive_ok else False
        adaptive_available = int(adaptive.get("available_candles") or sample_count or 0)
        adaptive_required = int(adaptive.get("required_candles") or 0)
        adaptive_timeframe = str(adaptive.get("timeframe") or cached.get("timeframe") or "H4").upper()
        out.at[index, "Fallback Level"] = 0 if adaptive_full_history else (2 if adaptive_ok else 7)
        out.at[index, "Data Status"] = (
            "CACHED VALID • FULL HISTORY" if adaptive_full_history
            else f"ADAPTIVE PARTIAL HISTORY • {adaptive_available}/{adaptive_required}" if adaptive_ok
            else f"BELOW MINIMUM HISTORY • {sample_count}/{minimum_calculation_candles(adaptive_timeframe)}"
        )
        out.at[index, "Display Data Source"] = (
            f"SYMBOL LOCAL {adaptive_timeframe} + IMMUTABLE PUBLICATION" if adaptive_ok
            else "IMMUTABLE PUBLICATION ONLY"
        )
        out.at[index, "Freshness Status"] = "CACHED" if adaptive_ok else "UNKNOWN"
        existing_quality = row.get("Data Quality Grade") if "Data Quality Grade" in out.columns else row.get("Data Quality")
        if _is_blank(existing_quality):
            out.at[index, "Data Quality"] = _quality_grade(sample_count, coverage)
        else:
            out.at[index, "Data Quality"] = str(existing_quality)
        out.at[index, "Snapshot Status"] = (
            "VERIFIED PUBLICATION + FULL LOCAL CHECK" if adaptive_full_history and _text(row.get("Publication Status")).upper().startswith("PUBLISHED")
            else "ADAPTIVE PARTIAL-HISTORY CALCULATION COMPLETED" if adaptive_ok
            else "BELOW MINIMUM HISTORY"
        )
        out.at[index, "Display Evidence Source"] = (
            f"IMMUTABLE PUBLICATION + FIELD3 BIAS + SYMBOL {adaptive_timeframe} ADAPTIVE" if adaptive_ok
            else "IMMUTABLE PUBLICATION WITHOUT ELIGIBLE LOCAL RECOVERY"
        )

        existing_score = row.get("Institutional Morning Score")
        if not _finite(existing_score):
            existing_score = row.get("Rank Score")
        if _finite(existing_score):
            comparative_score = float(existing_score)
        elif adaptive_ok:
            probability = float(adaptive.get("calibrated_bias_probability") or 0.0)
            accuracy_values = [float(adaptive.get(f"forecast_accuracy_{h}h")) for h in (1, 3, 6) if _finite(adaptive.get(f"forecast_accuracy_{h}h"))]
            accuracy = float(np.mean(accuracy_values)) if accuracy_values else 0.0
            persistence = float(adaptive.get("regime_persistence") or 0.0)
            transition_safety = 100.0 - float(adaptive.get("transition_risk_6h") or 100.0)
            comparative_score = 0.30 * probability + 0.20 * accuracy + 0.20 * persistence + 0.15 * transition_safety + 0.15 * coverage
        else:
            comparative_score = -1.0
        out.at[index, "Comparative Rank Score"] = round(comparative_score, 4)
        score_values[index] = comparative_score

        if changed:
            repaired_rows += 1
        details.append({
            "symbol": symbol, "status": "RECOVERED_FULL" if adaptive_full_history else "RECOVERED_ADAPTIVE" if adaptive_ok else "BELOW_MINIMUM_HISTORY",
            "changed": changed, "sample_count": sample_count, "evidence_coverage": round(coverage, 2),
        })

    # Comparative rank includes every selected row. The original safety-gated
    # rank remains separately visible as Eligible Rank.
    rank_frame = pd.DataFrame({
        "index": list(out.index),
        "score": [score_values.get(index, -1.0) for index in out.index],
        "coverage": [float(out.at[index, "Evidence Coverage"] or 0.0) if _finite(out.at[index, "Evidence Coverage"]) else 0.0 for index in out.index],
        "symbol": [str(out.at[index, "Symbol"]) for index in out.index],
    }).sort_values(["score", "coverage", "symbol"], ascending=[False, False, True], kind="mergesort")
    for rank, index in enumerate(rank_frame["index"].tolist(), start=1):
        out.at[index, "Rank"] = rank

    # Never leave a selected symbol row visually blank. Numeric evidence is not
    # fabricated. Unresolved values receive a typed status with fallback level,
    # source, and reliability context while the immutable numeric publication
    # remains unchanged.
    display_required = [
        "Stable Daily Bias", "Lower-Standard Bias", "Higher-Standard Bias", "Less-Risky Bias",
        "Entry Permission", "Safety Web", *metric_columns,
        "Transition Risk 1H", "Transition Risk 3H", "Transition Risk 6H",
        "Transition Risk 24H", "Expected Return 12H (%)",
        "Expected Return 24H (%)", "Expected Return 36H (%)",
        "Data Quality", "Evidence Coverage", "Coverage %", "Reliability Score",
        "Data Status", "Fallback Level", "Display Data Source", "Freshness Status",
        "Block Reason", "Snapshot Status",
    ]

    def explicit_fallback(column: str) -> str:
        upper = column.upper()
        if "BIAS" in upper or upper in {"ENTRY PERMISSION", "SAFETY WEB"}:
            return "WAIT • DIRECTION NOT ESTIMABLE"
        if any(token in upper for token in (
            "RETURN", "RISK", "PROBABILITY", "SCORE", "ACCURACY", "ENTROPY",
            "MARGIN", "DURATION", "AGE", "COVERAGE", "RANK", "VOLUME", "CVAR",
        )):
            return validated_estimate_label(timeframe="H4", available=0)
        if "SOURCE" in upper:
            return "CANONICAL SNAPSHOT • LIMITED EVIDENCE"
        if "FRESH" in upper:
            return "UNKNOWN • LIMITED EVIDENCE"
        if "QUALITY" in upper or "STATUS" in upper:
            return "LOW QUALITY • BELOW MINIMUM"
        return insufficiency_label(timeframe="H4", available=0)

    for column in display_required:
        if column not in out.columns:
            out[column] = explicit_fallback(column)
        mask = out[column].map(_is_blank)
        if bool(mask.any()):
            out[column] = out[column].astype("object")
            out.loc[mask, column] = explicit_fallback(column)

    for column in out.columns:
        mask = out[column].map(_is_blank)
        if bool(mask.any()):
            if not pd.api.types.is_object_dtype(out[column].dtype):
                out[column] = out[column].astype(object)
            out.loc[mask, column] = explicit_fallback(column)

    # Normalize legacy generic UNAVAILABLE text inherited from old immutable
    # rows into explicit fallback wording without manufacturing numeric values.
    for column in out.select_dtypes(include=["object"]).columns:
        out[column] = out[column].map(
            lambda value: str(value).replace("UNAVAILABLE", "NO VALIDATED VALUE")
            if isinstance(value, str) else value
        )

    ordered = [column for column in priority_columns if column in out.columns]
    out = out[ordered + [column for column in out.columns if column not in ordered]]
    if selected:
        order = {symbol: position for position, symbol in enumerate(selected)}
        out["_selected_order"] = out["Symbol"].map(lambda value: order.get(normalize_symbol(value), len(order)))
        out = out.sort_values(["Rank", "_selected_order"], kind="mergesort").drop(columns="_selected_order").reset_index(drop=True)
    else:
        out = out.sort_values(["Rank", "Symbol"], kind="mergesort").reset_index(drop=True)

    selected_present = {normalize_symbol(value) for value in out["Symbol"].tolist()}
    missing_selected = [symbol for symbol in selected if symbol not in selected_present]
    blank_counts = {column: int(out[column].map(_is_blank).sum()) for column in display_required if column in out.columns}
    all_blank_counts = {column: int(out[column].map(_is_blank).sum()) for column in out.columns}
    numeric_columns = [column for column in _METRIC_FALLBACK_MAP if column in out.columns]
    variability = {column: int(pd.to_numeric(out[column], errors="coerce").nunique(dropna=True)) for column in numeric_columns}
    return out, {
        "ok": not missing_selected and bool(out["Rank"].notna().all()),
        "status": "COMPLETE_PRIORITY_VIEW" if not missing_selected else "PARTIAL_PRIORITY_VIEW",
        "repaired_rows": repaired_rows,
        "row_count": len(out),
        "selected_symbols": selected,
        "missing_selected_symbols": missing_selected,
        "all_rows_ranked": bool(out["Rank"].notna().all()),
        "blank_priority_cells": blank_counts,
        "blank_all_visible_cells": all_blank_counts,
        "all_visible_cells_explicit": not any(all_blank_counts.values()),
        "column_variability": variability,
        "details": details,
        "immutable_source_modified": False,
        "version": VERSION,
    }


def _canonical(state: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        from core.canonical_lookup_20260626 import resolve_canonical
        value = resolve_canonical(state)
        if isinstance(value, Mapping):
            return value
    except Exception:
        pass
    for key in ("canonical_decision_result_20260617", "canonical_result_20260617"):
        value = state.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _powerbi_repair(state: MutableMapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    frame = _find_ohlc(state)
    symbol = normalize_symbol(
        canonical.get("symbol") or state.get(DISPLAY_SYMBOL_KEY) or state.get(ACTIVE_KEY)
        or state.get("symbol") or "EURUSD"
    )
    if frame.empty:
        # Lunch symbol activation should restore the whole child state, but older
        # deployments sometimes restored identity before OHLC aliases. Recover
        # only from the exact active symbol cache; never borrow another symbol.
        frame = _find_ohlc(_cached_symbol_state(symbol))
    if frame.empty:
        return {"ok": False, "status": "NO_ACTIVE_SYMBOL_OHLC", "symbol": symbol}
    try:
        from ui.lunch_field2_saved_path_v13 import recover_saved_prediction_bundle
        bundle, candles, meta = recover_saved_prediction_bundle(state, canonical, frame)
        if meta.get("ok"):
            state["powerbi_calibrated_bundle_20260617"] = bundle
            state["dv_pp_predicted_calibrated_20260617"] = candles
            history = meta.get("historical_reference")
            if isinstance(history, pd.DataFrame) and not history.empty:
                state["dv_pp_projection_history"] = history
        return dict(meta)
    except Exception as exc:
        return {"ok": False, "status": "REPAIR_FAILED", "error": f"{type(exc).__name__}: {exc}"}


def validate_and_repair_state(state: MutableMapping[str, Any]) -> dict[str, Any]:
    """Run inexpensive sync checks and bounded repairs for the active generation."""
    universe = recover_symbol_universe(state)
    selected = normalize_selected(universe.get("selected_symbols") or [])
    main = normalize_symbol(universe.get("main_symbol") or (selected[0] if selected else "EURUSD"))
    if not selected:
        selected = [main]
    state[SELECTED_KEY] = selected
    state[MAIN_SYMBOL_KEY] = main

    ready = available_saved_symbols(selected)
    active = normalize_symbol(universe.get("active_symbol") or state.get(DISPLAY_SYMBOL_KEY) or state.get(ACTIVE_KEY) or state.get("symbol") or main)
    if ready and active not in ready:
        active = ready[0]
        state[ACTIVE_KEY] = active
        state[DISPLAY_SYMBOL_KEY] = active
        state["active_snapshot_symbol_20260702"] = active
        state["lunch_symbol_selector_pending_widget_reset_20260702"] = active
    elif not ready:
        ready = [active]

    if state.get("settings_auto_open_lunch_20260617") and state.get("lunch_active_field_selector_20260624") in (None, "", "All Lunch fields closed"):
        state["lunch_active_field_selector_20260624"] = FIELD10_LABEL
        state["lunch_active_field_selector_20260624__pending"] = FIELD10_LABEL
        state["active_field"] = "Field 10"
        state["field_10_expanded"] = True
        state["scroll_target"] = "field-10-anchor"

    canonical = _canonical(state)
    identity = {
        "run_id": canonical.get("run_id") or canonical.get("canonical_calculation_id"),
        "symbol": canonical.get("symbol") or active,
        "candle": canonical.get("completed_broker_candle") or canonical.get("broker_candle_time") or canonical.get("latest_completed_candle_time"),
    }
    fingerprint = sha256(repr((selected, active, identity)).encode("utf-8")).hexdigest()[:20]
    previous = _mapping(state.get("continuous_validation_report_20260702"))
    # Reuse a successful same-generation report but refresh the live-session check.
    powerbi = _mapping(previous.get("powerbi")) if previous.get("fingerprint") == fingerprint else _powerbi_repair(state, canonical)
    try:
        from core.session_context_20260625 import resolve_session_contract
        session = resolve_session_contract(state, canonical).to_dict()
    except Exception as exc:
        session = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}

    try:
        from core.field10_daily_snapshot_contract_20260702 import load_current_daily_snapshot
        daily_bundle = load_current_daily_snapshot()
        priority_view, priority_validation = build_field10_display_overlay(
            daily_bundle.get("current") if isinstance(daily_bundle, Mapping) else pd.DataFrame(),
            selected_symbols=selected,
        )
        priority_validation = {**dict(priority_validation), "rows": int(len(priority_view))}
    except Exception as exc:
        priority_validation = {"ok": False, "status": "VALIDATION_FAILED", "error": f"{type(exc).__name__}: {exc}"}

    overall_ok = bool(ready) and bool(powerbi.get("ok")) and bool(priority_validation.get("ok"))
    report = {
        "ok": overall_ok,
        "status": "READY" if overall_ok else "CAUTION",
        "fingerprint": fingerprint,
        "main_symbol": main,
        "active_symbol": active,
        "selected_symbols": selected,
        "cache_ready_symbols": ready,
        "symbol_sync": active in ready and main == state.get(MAIN_SYMBOL_KEY),
        "powerbi": dict(powerbi),
        "field10_priority": priority_validation,
        "session": session,
        "navigation_field": state.get("lunch_active_field_selector_20260624"),
        "checked_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "version": VERSION,
    }
    state["continuous_validation_report_20260702"] = report
    return report


__all__ = ["VERSION", "build_field3_higher_standard_multi_symbol_table", "build_field10_display_overlay", "validate_and_repair_state"]
