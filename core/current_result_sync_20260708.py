"""Current-run source-of-truth synchronizer for ADX Quant Pro.

Additive repair layer, July 2026:
- Settings selected symbols + timeframe are the only public selection source.
- Field 3/Table 3, Field 10, NLP, CSV and copy payloads read one canonical
  current-result object.
- Stale screen/export/copy outputs are cleared whenever symbol/timeframe changes.
"""
from __future__ import annotations
from core.global_symbol_compat import set_legacy_calculation_symbol, set_legacy_configured_symbols

from collections.abc import Mapping, MutableMapping, Sequence
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
from typing import Any
import json

import pandas as pd

CURRENT_RESULT_KEY = "adx_current_canonical_result_20260708"
CURRENT_SIGNATURE_KEY = "adx_current_selection_signature_20260708"
CURRENT_RUN_ID_KEY = "adx_current_run_id_20260708"
CURRENT_SELECTED_KEY = "adx_current_selected_symbols_20260708"
CURRENT_TIMEFRAME_KEY = "adx_current_timeframe_20260708"
CURRENT_TABLE3_KEY = "field3_table3_current_symbols_20260708"
CURRENT_NLP_KEY = "nlp_sentiment_current_symbols_20260708"
CURRENT_CSV_KEY = "adx_current_result_csv_bytes_20260708"
CURRENT_SHORT_COPY_KEY = "adx_current_copy_short_20260708"
CURRENT_FULL_COPY_KEY = "adx_current_copy_full_20260708"

_STALE_OUTPUT_KEYS = (
    CURRENT_RESULT_KEY,
    CURRENT_TABLE3_KEY,
    CURRENT_NLP_KEY,
    CURRENT_CSV_KEY,
    CURRENT_SHORT_COPY_KEY,
    CURRENT_FULL_COPY_KEY,
    "field10_consolidated_table_20260707",
    "field10_consolidated_report_20260707",
    "direct_current_copy_payloads_20260702_v3",
    "copy_payload_cache_short_20260702",
    "copy_payload_cache_full_20260702",
    "canonical_copy_short_payload_20260621",
    "canonical_copy_all_payload_20260621",
)


def normalize_symbol(value: Any) -> str:
    raw = str(value or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")
    aliases = {
        "GOLD": "XAUUSD", "XBTUSD": "BTCUSD", "BTCUSDT": "BTCUSD",
        "USTEC": "NAS100", "US100": "NAS100", "NDX": "NAS100",
        "SPX500": "US500", "SP500": "US500", "GSPC": "US500",
        "USDX": "DXY", "DOLLARINDEX": "DXY", "DX-Y.NYB": "DXY",
    }
    return aliases.get(raw, raw)


def normalize_symbols(values: Any, *, limit: int | None = 30) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Sequence):
        values = []
    out: list[str] = []
    for value in values:
        symbol = normalize_symbol(value)
        if symbol and symbol not in out:
            out.append(symbol)
        if limit is not None and len(out) >= max(0, int(limit)):
            break
    return out


def normalize_timeframe(value: Any, default: str = "H4") -> str:
    """Use one public spelling so H4 reconnects keep one selection identity."""
    text = str(value or default).strip().upper().replace(" ", "")
    aliases = {"4H": "H4", "1H": "H1", "60": "H1", "60MIN": "H1", "240": "H4", "240MIN": "H4"}
    return aliases.get(text, text or default)


def current_timeframe(state: Mapping[str, Any]) -> str:
    for key in ("canonical_ranking_timeframe", "settings_timeframe", "selected_timeframe", "timeframe", "last_connected_timeframe"):
        text = str(state.get(key) or "").strip().upper()
        if text and text.lower() not in {"nan", "none", "not available"}:
            return normalize_timeframe(text)
    return "H4"


def selection_signature(symbols: Any, timeframe: Any) -> str:
    selected = normalize_symbols(symbols, limit=30)
    tf = normalize_timeframe(timeframe)
    return sha256((tf + "|" + "|".join(selected)).encode("utf-8")).hexdigest()[:24]


def selected_symbols_from_settings(state: Mapping[str, Any]) -> list[str]:
    # Settings group keys are authoritative.  Fallbacks are used only during
    # startup before the settings selector widgets are initialized.
    group_keys = (
        "multi_symbol_first_selected_20260706",
        "multi_symbol_second_selected_20260706",
        "multi_symbol_third_selected_20260706",
    )
    grouped: list[str] = []
    for key in group_keys:
        grouped.extend(normalize_symbols(state.get(key), limit=None))
    if grouped:
        return normalize_symbols(grouped, limit=30)
    for key in (
        "multi_symbol_configured_union_20260706",
        "canonical_selected_symbols",
        "canonical_ranking_symbols",
        "canonical_selected_symbols_20260705",
        "multi_symbol_selected_20260701",
    ):
        symbols = normalize_symbols(state.get(key), limit=30)
        if symbols:
            return symbols
    symbol = normalize_symbol(state.get("symbol") or state.get("connector_symbol_20260702") or "EURUSD")
    return [symbol] if symbol else ["EURUSD"]


def _clear_stale_outputs(state: MutableMapping[str, Any], *, old_signature: str, new_signature: str, reason: str) -> None:
    for key in _STALE_OUTPUT_KEYS:
        state.pop(key, None)
    state["current_result_stale_cleared_20260708"] = {
        "old_signature": old_signature,
        "new_signature": new_signature,
        "reason": reason,
        "cleared_at": datetime.now(timezone.utc).isoformat(),
    }


def sync_settings_source_of_truth(
    state: MutableMapping[str, Any],
    symbols: Any | None = None,
    timeframe: Any | None = None,
    *,
    reason: str = "settings_sync",
    clear_stale: bool = True,
) -> dict[str, Any]:
    selected = normalize_symbols(symbols if symbols is not None else selected_symbols_from_settings(state), limit=30)
    tf = normalize_timeframe(timeframe or current_timeframe(state))
    if not selected:
        return {"symbols": [], "timeframe": tf, "signature": selection_signature([], tf), "run_id": state.get(CURRENT_RUN_ID_KEY)}
    sig = selection_signature(selected, tf)
    old_sig = str(state.get(CURRENT_SIGNATURE_KEY) or "")
    if clear_stale and old_sig and old_sig != sig:
        _clear_stale_outputs(state, old_signature=old_sig, new_signature=sig, reason=reason)
    state[CURRENT_SIGNATURE_KEY] = sig
    state[CURRENT_SELECTED_KEY] = list(selected)
    state[CURRENT_TIMEFRAME_KEY] = tf
    # Public/legacy keys all point to the current Settings selection, never to
    # unrelated cached DB symbols and never to the loaded-only subset.
    for key in (
        "canonical_selected_symbols",
        "canonical_ranking_symbols",
        "canonical_selected_symbols_20260705",
        "selected_symbols_for_run_20260705",
        "multi_symbol_configured_union_20260706",
    ):
        state[key] = list(selected)
    set_legacy_configured_symbols(state, selected)
    for key in ("canonical_ranking_timeframe", "settings_timeframe", "selected_timeframe", "timeframe", "last_connected_timeframe"):
        state[key] = tf
    if selected:
        state["lunch_display_symbol_20260702"] = selected[0]
        state.setdefault(CURRENT_RUN_ID_KEY, f"SEL-{sig}")
    return {"symbols": selected, "timeframe": tf, "signature": sig, "run_id": state.get(CURRENT_RUN_ID_KEY)}


def _status_rows(state: Mapping[str, Any], symbols: Sequence[str], timeframe: str) -> pd.DataFrame:
    try:
        from core.multi_symbol_run_groups_20260706 import configured_groups
        from core.multi_symbol_load_manager_20260707 import loaded_universe_status
        status = loaded_universe_status(state, configured_groups(state), timeframe)
        rows = status.get("status_rows") if isinstance(status, Mapping) else []
        frame = pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception as exc:
        frame = pd.DataFrame([{"Symbol": s, "Timeframe": timeframe, "Load Status": "STATUS_ERROR", "Failure Reason": f"{type(exc).__name__}: {exc}"} for s in symbols])
    if frame.empty:
        frame = pd.DataFrame([{"Symbol": s, "Timeframe": timeframe, "Load Status": "NOT_LOADED", "Failure Reason": "Load Selected Symbols has not produced a valid exact-symbol result yet."} for s in symbols])
    if "Symbol" in frame.columns:
        frame["Symbol"] = frame["Symbol"].map(normalize_symbol)
        frame = frame[frame["Symbol"].isin(symbols)]
    else:
        frame["Symbol"] = symbols[:len(frame)] if len(frame) else []
    if "Timeframe" not in frame.columns:
        frame["Timeframe"] = timeframe
    frame["Timeframe"] = frame["Timeframe"].replace({"": timeframe, "nan": timeframe, "None": timeframe, "Not available": timeframe}).fillna(timeframe)
    missing = [s for s in symbols if s not in set(frame["Symbol"].astype(str).map(normalize_symbol))]
    if missing:
        frame = pd.concat([frame, pd.DataFrame([{"Symbol": s, "Timeframe": timeframe, "Load Status": "NOT_LOADED", "Failure Reason": "Selected now but no current exact-symbol load/status row is available."} for s in missing])], ignore_index=True)
    return frame.drop_duplicates("Symbol", keep="first").reset_index(drop=True)


def _field10_frame(state: Mapping[str, Any], symbols: Sequence[str]) -> pd.DataFrame:
    frame = state.get("field10_consolidated_table_20260707")
    if not isinstance(frame, pd.DataFrame) or frame.empty or "Symbol" not in frame.columns:
        return pd.DataFrame()
    out = frame.copy()
    out["Symbol"] = out["Symbol"].map(normalize_symbol)
    return out[out["Symbol"].isin(symbols)].drop_duplicates("Symbol", keep="first").reset_index(drop=True)


def _score_from_rows(row: Mapping[str, Any], n: int) -> float:
    for key in ("Scaled Score", "Rank Score", "Final Score", "Combined Score", "Technical Score", "Reliability", "Regime Probability"):
        if key in row:
            value = pd.to_numeric(pd.Series([row.get(key)]), errors="coerce").iloc[0]
            if pd.notna(value):
                value = float(value)
                if value <= 1.0:
                    value *= 100.0
                return max(0.0, min(100.0, value))
    candles = pd.to_numeric(pd.Series([row.get("Candle Count", row.get("Rows", row.get("Sample Count")))]), errors="coerce").iloc[0]
    if pd.notna(candles) and float(candles) > 0:
        return max(25.0, min(88.0, 35.0 + float(candles) / max(10.0, n)))
    status = str(row.get("Load Status") or row.get("Loaded Status") or "").upper()
    if status in {"READY", "LOADED", "PUBLISHED", "CACHE_SUCCESS", "TWELVE_SUCCESS", "FCS_SUCCESS", "LOCAL_VALID_CACHE"}:
        return 50.0
    return 0.0


def build_table3_current(state: MutableMapping[str, Any]) -> pd.DataFrame:
    sync = sync_settings_source_of_truth(state, reason="build_table3_current", clear_stale=False)
    symbols = sync["symbols"]
    timeframe = sync["timeframe"]
    run_id = str(state.get(CURRENT_RUN_ID_KEY) or f"SEL-{sync['signature']}")
    status = _status_rows(state, symbols, timeframe)
    f10 = _field10_frame(state, symbols)
    merged = pd.DataFrame({"Symbol": symbols}).merge(status, on="Symbol", how="left", sort=False)
    if not f10.empty:
        keep = [c for c in (
            "Symbol", "Final Rank", "Scaled Score", "Rank Score", "Higher-Standard Regime", "Higher-Standard Bias",
            "Less-Risky Bias", "Reliability", "Regime Probability", "Expected Return 12H", "Expected Return 24H",
            "Expected Value", "Decision", "Ranking Result", "Evidence Source", "Data Quality Grade", "Sample Count",
        ) if c in f10.columns]
        merged = merged.merge(f10[keep], on="Symbol", how="left", suffixes=("", " Field10"))
    # Ensure exact current timeframe and current rows only.
    merged["Timeframe"] = timeframe
    rows: list[dict[str, Any]] = []
    for i, symbol in enumerate(symbols):
        row = merged[merged["Symbol"].map(normalize_symbol).eq(symbol)].head(1)
        data = row.iloc[0].to_dict() if not row.empty else {"Symbol": symbol, "Timeframe": timeframe}
        score = _score_from_rows(data, max(1, len(symbols)))
        rows.append({
            "Rank": None,
            "Symbol": symbol,
            "Timeframe": timeframe,
            "Scaled Score": round(score, 2),
            "Higher-Standard Regime": data.get("Higher-Standard Regime") or data.get("Higher Standard Regime") or "CHECK",
            "Higher-Standard Bias": data.get("Higher-Standard Bias") or data.get("Less-Risky Bias") or data.get("Decision") or "WAIT / REVIEW",
            "Less-Risky Bias": data.get("Less-Risky Bias") or data.get("Decision") or "WAIT / REVIEW",
            "Monitoring Status": data.get("Load Status") or data.get("Loaded Status") or "CHECK",
            "Prediction Output": data.get("Ranking Result") or data.get("Expected Value") or data.get("Expected Return 12H") or "Not available",
            "Data Provider Used": data.get("Data Provider Used") or data.get("Provider Used") or data.get("Actual Candle Provider") or "Not available",
            "Candle Count": data.get("Candle Count") or data.get("Rows") or data.get("Sample Count") or "Not available",
            "Latest Candle Time": data.get("Latest Candle Time") or data.get("Latest Candle") or "Not available",
            "Data Quality Grade": data.get("Data Quality Grade") or data.get("Data Quality") or "CHECK",
            "Load Status": data.get("Load Status") or data.get("Loaded Status") or "NOT_LOADED",
            "Failure Reason": data.get("Failure Reason") or data.get("Failure Reason if not rankable") or data.get("Reason") or data.get("Notes") or "Not available",
            "Run ID": run_id,
        })
    table = pd.DataFrame(rows)
    table["__selected_order"] = table["Symbol"].map({symbol: idx for idx, symbol in enumerate(symbols)})
    table = table.sort_values(["Scaled Score", "__selected_order"], ascending=[False, True], kind="mergesort").reset_index(drop=True)
    table["Rank"] = range(1, len(table) + 1)
    table = table.drop(columns=["__selected_order"], errors="ignore")
    state[CURRENT_TABLE3_KEY] = table.copy(deep=False)
    state["field3_current_table3_20260708"] = table.copy(deep=False)
    return table


def build_nlp_sentiment_current(state: MutableMapping[str, Any]) -> pd.DataFrame:
    sync = sync_settings_source_of_truth(state, reason="build_nlp_sentiment_current", clear_stale=False)
    symbols = sync["symbols"]
    timeframe = sync["timeframe"]
    f10 = _field10_frame(state, symbols)
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        item = f10[f10["Symbol"].map(normalize_symbol).eq(symbol)].head(1) if not f10.empty else pd.DataFrame()
        data = item.iloc[0].to_dict() if not item.empty else {}
        sentiment = data.get("NLP Sentiment Bias") or data.get("Sentiment Bias") or data.get("Data-Mining Sentiment Bias") or "UNAVAILABLE"
        direction = data.get("Less-Risky Bias") or data.get("Higher-Standard Bias") or data.get("Decision") or "WAIT / REVIEW"
        rows.append({
            "Symbol": symbol,
            "Timeframe": timeframe,
            "Direction": direction,
            "Sentiment": sentiment,
            "Impact": data.get("News Impact Level") or data.get("News Impact") or "Not available",
            "Relevance": data.get("News Currency/Pair Relevance") or "Current selected symbol",
            "Confidence": data.get("NLP Sentiment Score") or data.get("Reliability") or "Not available",
            "Time": data.get("News Published Time") or data.get("Latest Candle Time") or "Not available",
            "Reason": data.get("Highest-Impact Current News Title") or data.get("New Title") or data.get("Reason") or "No current selected-symbol NLP/news evidence was published for this run.",
        })
    table = pd.DataFrame(rows)
    state[CURRENT_NLP_KEY] = table.copy(deep=False)
    return table


def _csv_section(name: str, frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame([{"Section": name, "Status": "EMPTY"}])
    out = frame.copy()
    out.insert(0, "Section", name)
    return out


def build_current_result(state: MutableMapping[str, Any], *, run_id: Any | None = None, reason: str = "current_result") -> dict[str, Any]:
    sync = sync_settings_source_of_truth(state, reason=reason, clear_stale=False)
    if run_id:
        state[CURRENT_RUN_ID_KEY] = str(run_id)
    else:
        state[CURRENT_RUN_ID_KEY] = str(state.get(CURRENT_RUN_ID_KEY) or f"SEL-{sync['signature']}")
    table3 = build_table3_current(state)
    field10 = _field10_frame(state, sync["symbols"])
    try:
        from core.field10_unified_authority_20260709 import build_unified_field10_authority
        authority_20260709 = build_unified_field10_authority(state, source_frame=field10, persist=True)
        unified_field10_20260709 = authority_20260709.get("table")
    except Exception:
        authority_20260709 = {}
        unified_field10_20260709 = pd.DataFrame()
    load_status = _status_rows(state, sync["symbols"], sync["timeframe"])
    nlp = build_nlp_sentiment_current(state)
    institutional = state.get("field10_institutional_ranking_20260708")
    institutional_news = state.get("field10_news_nlp_evidence_20260708")
    institutional_field3 = state.get("field3_multisymbol_regime_20260708")
    institutional_field11 = state.get("field11_similar_path_multisymbol_20260708")
    institutional_research = state.get("research_model_validation_20260708")
    result = {
        "run_id": state[CURRENT_RUN_ID_KEY],
        "selection_signature": sync["signature"],
        "selected_symbols": list(sync["symbols"]),
        "timeframe": sync["timeframe"],
        "field3_table3": table3,
        "field10": field10,
        "field10_unified_daily_locked_rank": unified_field10_20260709 if isinstance(unified_field10_20260709, pd.DataFrame) else pd.DataFrame(),
        "field10_unified_snapshot": authority_20260709.get("snapshot") if isinstance(authority_20260709, Mapping) else {},
        "load_status": load_status,
        "nlp_sentiment": nlp,
        "field10_institutional_ranking": institutional if isinstance(institutional, pd.DataFrame) else pd.DataFrame(),
        "field10_news_nlp_evidence": institutional_news if isinstance(institutional_news, pd.DataFrame) else pd.DataFrame(),
        "field3_multisymbol_regime": institutional_field3 if isinstance(institutional_field3, pd.DataFrame) else pd.DataFrame(),
        "field11_similar_path_multisymbol": institutional_field11 if isinstance(institutional_field11, pd.DataFrame) else pd.DataFrame(),
        "research_model_validation": institutional_research if isinstance(institutional_research, pd.DataFrame) else pd.DataFrame(),
        "canonical_run_identity": state.get("canonical_run_identity_20260708") if isinstance(state.get("canonical_run_identity_20260708"), Mapping) else {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    }
    state[CURRENT_RESULT_KEY] = result
    state[CURRENT_SHORT_COPY_KEY] = current_short_copy_text(state)
    state[CURRENT_FULL_COPY_KEY] = current_full_copy_text(state)
    state[CURRENT_CSV_KEY] = current_result_csv_bytes(state)
    return result


def _frame_to_text(title: str, frame: pd.DataFrame, *, max_rows: int = 18) -> str:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return f"\n{title}\nEMPTY\n"
    return "\n" + title + "\n" + frame.head(max_rows).to_string(index=False) + "\n"


def current_short_copy_text(state: Mapping[str, Any]) -> str:
    result = state.get(CURRENT_RESULT_KEY) if isinstance(state.get(CURRENT_RESULT_KEY), Mapping) else {}
    symbols = result.get("selected_symbols") or selected_symbols_from_settings(state)
    tf = result.get("timeframe") or current_timeframe(state)
    run_id = result.get("run_id") or state.get(CURRENT_RUN_ID_KEY) or "current"
    field10 = result.get("field10") if isinstance(result, Mapping) else pd.DataFrame()
    if not isinstance(field10, pd.DataFrame):
        field10 = _field10_frame(state, normalize_symbols(symbols))
    lines = [f"ADX Quant Pro — Copy Short", f"Run ID: {run_id}", f"Timeframe: {tf}", f"Selected Symbols: {', '.join(normalize_symbols(symbols))}"]
    lines.append(_frame_to_text("Field 10 Current Main Result", field10, max_rows=12))
    return "\n".join(lines)


def current_full_copy_text(state: Mapping[str, Any]) -> str:
    result = state.get(CURRENT_RESULT_KEY) if isinstance(state.get(CURRENT_RESULT_KEY), Mapping) else {}
    symbols = result.get("selected_symbols") or selected_symbols_from_settings(state)
    tf = result.get("timeframe") or current_timeframe(state)
    run_id = result.get("run_id") or state.get(CURRENT_RUN_ID_KEY) or "current"
    table3 = result.get("field3_table3") if isinstance(result, Mapping) else pd.DataFrame()
    field10 = result.get("field10") if isinstance(result, Mapping) else pd.DataFrame()
    load_status = result.get("load_status") if isinstance(result, Mapping) else pd.DataFrame()
    nlp = result.get("nlp_sentiment") if isinstance(result, Mapping) else pd.DataFrame()
    institutional = result.get("field10_institutional_ranking") if isinstance(result, Mapping) else pd.DataFrame()
    field11 = result.get("field11_similar_path_multisymbol") if isinstance(result, Mapping) else pd.DataFrame()
    research = result.get("research_model_validation") if isinstance(result, Mapping) else pd.DataFrame()
    parts = [
        "ADX Quant Pro — Copy Full Current Result",
        f"Run ID: {run_id}",
        f"Timeframe: {tf}",
        f"Selected Symbols: {', '.join(normalize_symbols(symbols))}",
        _frame_to_text("Field 3 / Table 3 Current Ranking", table3 if isinstance(table3, pd.DataFrame) else pd.DataFrame(), max_rows=20),
        _frame_to_text("Field 10 Current Result", field10 if isinstance(field10, pd.DataFrame) else pd.DataFrame(), max_rows=20),
        _frame_to_text("Current Loaded Candles / Provider Status", load_status if isinstance(load_status, pd.DataFrame) else pd.DataFrame(), max_rows=20),
        _frame_to_text("Current NLP / Sentiment", nlp if isinstance(nlp, pd.DataFrame) else pd.DataFrame(), max_rows=20),
        _frame_to_text("Field 10 Institutional Ranking", institutional if isinstance(institutional, pd.DataFrame) else pd.DataFrame(), max_rows=20),
        _frame_to_text("Field 11 Similar Path Multi-Symbol", field11 if isinstance(field11, pd.DataFrame) else pd.DataFrame(), max_rows=20),
        _frame_to_text("Research Model Validation", research if isinstance(research, pd.DataFrame) else pd.DataFrame(), max_rows=20),
    ]
    return "\n".join(parts)


def current_result_csv_bytes(state: Mapping[str, Any]) -> bytes:
    result = state.get(CURRENT_RESULT_KEY) if isinstance(state.get(CURRENT_RESULT_KEY), Mapping) else {}
    symbols = normalize_symbols(result.get("selected_symbols") or selected_symbols_from_settings(state))
    tf = result.get("timeframe") or current_timeframe(state)
    meta = pd.DataFrame([{
        "Section": "Run Metadata",
        "Run ID": result.get("run_id") or state.get(CURRENT_RUN_ID_KEY) or "current",
        "Timeframe": tf,
        "Selected Symbols": ", ".join(symbols),
        "Selection Signature": result.get("selection_signature") or selection_signature(symbols, tf),
        "Updated At": result.get("updated_at") or datetime.now(timezone.utc).isoformat(),
    }])
    frames = [
        meta,
        _csv_section("Field 3 Table 3", result.get("field3_table3") if isinstance(result.get("field3_table3"), pd.DataFrame) else pd.DataFrame()),
        _csv_section("Field 10 Unified Daily Locked Rank", result.get("field10_unified_daily_locked_rank") if isinstance(result.get("field10_unified_daily_locked_rank"), pd.DataFrame) else pd.DataFrame()),
        _csv_section("Field 10 Legacy/Supporting", result.get("field10") if isinstance(result.get("field10"), pd.DataFrame) else pd.DataFrame()),
        _csv_section("Loaded Candles Status", result.get("load_status") if isinstance(result.get("load_status"), pd.DataFrame) else pd.DataFrame()),
        _csv_section("NLP Sentiment", result.get("nlp_sentiment") if isinstance(result.get("nlp_sentiment"), pd.DataFrame) else pd.DataFrame()),
        _csv_section("Field 10 Institutional Ranking", result.get("field10_institutional_ranking") if isinstance(result.get("field10_institutional_ranking"), pd.DataFrame) else pd.DataFrame()),
        _csv_section("Field 10 News NLP Evidence", result.get("field10_news_nlp_evidence") if isinstance(result.get("field10_news_nlp_evidence"), pd.DataFrame) else pd.DataFrame()),
        _csv_section("Field 3 Multi-Symbol Regime", result.get("field3_multisymbol_regime") if isinstance(result.get("field3_multisymbol_regime"), pd.DataFrame) else pd.DataFrame()),
        _csv_section("Field 11 Similar Path", result.get("field11_similar_path_multisymbol") if isinstance(result.get("field11_similar_path_multisymbol"), pd.DataFrame) else pd.DataFrame()),
        _csv_section("Research Model Validation", result.get("research_model_validation") if isinstance(result.get("research_model_validation"), pd.DataFrame) else pd.DataFrame()),
    ]
    all_columns: list[str] = []
    for frame in frames:
        for column in frame.columns:
            if column not in all_columns:
                all_columns.append(column)
    combined = pd.concat([frame.reindex(columns=all_columns) for frame in frames], ignore_index=True)
    return combined.to_csv(index=False).encode("utf-8")


def render_current_data_visualization(state: MutableMapping[str, Any] | None = None) -> None:
    import streamlit as st
    state = state if state is not None else st.session_state
    result = build_current_result(state, reason="data_visualization_tab")
    symbols = result["selected_symbols"]
    st.markdown("### 📊 Data Visualization — Current Selected Symbols Only")
    st.caption(f"Run ID: {result['run_id']} · Timeframe: {result['timeframe']} · Symbols: {', '.join(symbols)}")
    table3 = result["field3_table3"]
    field10 = result["field10"]
    unified_field10 = result.get("field10_unified_daily_locked_rank")
    load_status = result["load_status"]
    nlp = result["nlp_sentiment"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selected", len(symbols))
    c2.metric("Loaded rows", int((pd.to_numeric(load_status.get("Candle Count", pd.Series(dtype=object)), errors="coerce").fillna(0) > 0).sum()) if isinstance(load_status, pd.DataFrame) and not load_status.empty else 0)
    c3.metric("Timeframe", str(result["timeframe"]))
    c4.metric("Field 10 rows", int(len(field10)) if isinstance(field10, pd.DataFrame) else 0)
    try:
        from ui.color_system import style_mobile_table
        from core.view_model_sync import render_sync_status_panel
        if isinstance(unified_field10, pd.DataFrame) and not unified_field10.empty:
            st.markdown("#### Field 10 Unified Daily Locked Rank — Trusted Visualization Source")
            st.dataframe(style_mobile_table(unified_field10), use_container_width=True, hide_index=True, height=min(720, 80 + 38 * min(len(unified_field10), 16)))
            viz_cols = [c for c in ["Symbol", "Rank", "Authority Score", "Reliability Grade", "Can Trust Rank?", "Calibrated Probability", "Transition Safety %", "Transition Risk 6H", "CVaR 95%", "Data Quality Grade"] if c in unified_field10.columns]
            if len(viz_cols) >= 2:
                chart_df = unified_field10[viz_cols].copy()
                for c in chart_df.columns:
                    if c != "Symbol": chart_df[c] = pd.to_numeric(chart_df[c], errors="coerce")
                numeric_cols = [c for c in chart_df.columns if c != "Symbol" and chart_df[c].notna().any()]
                if numeric_cols:
                    st.bar_chart(chart_df.set_index("Symbol")[numeric_cols], use_container_width=True)
        render_sync_status_panel(st, state)
    except Exception as unified_viz_exc_20260709:
        st.caption(f"Unified visualization panel skipped safely: {type(unified_viz_exc_20260709).__name__}")
    try:
        from core.institutional_quant_layer_20260708 import render_institutional_data_visualization
        render_institutional_data_visualization(state)
    except Exception as institutional_viz_exc:
        st.caption(f"Institutional visualization unavailable: {type(institutional_viz_exc).__name__}")
    if isinstance(table3, pd.DataFrame) and not table3.empty:
        st.markdown("#### Field 3 / Table 3 scaled ranking")
        st.dataframe(table3, use_container_width=True, hide_index=True)
        numeric = pd.to_numeric(table3.get("Scaled Score"), errors="coerce")
        if numeric.notna().any():
            chart = table3[["Symbol", "Scaled Score"]].copy()
            chart["Scaled Score"] = numeric
            try:
                import plotly.express as px
                st.plotly_chart(px.bar(chart, x="Symbol", y="Scaled Score", title="Scaled Score by Selected Symbol"), use_container_width=True)
            except Exception:
                st.bar_chart(chart.set_index("Symbol")[["Scaled Score"]], use_container_width=True)
    st.markdown("#### Loaded candle/provider status")
    st.dataframe(load_status, use_container_width=True, hide_index=True)
    if isinstance(field10, pd.DataFrame) and not field10.empty:
        st.markdown("#### Field 10 current result")
        st.dataframe(field10, use_container_width=True, hide_index=True)
    st.markdown("#### NLP / Sentiment — current run only")
    st.dataframe(nlp, use_container_width=True, hide_index=True)
    st.download_button(
        "Download CSV",
        data=current_result_csv_bytes(state),
        file_name=f"adx_current_result_{result['run_id']}.csv".replace("/", "_"),
        mime="text/csv",
        use_container_width=True,
        key="current_result_download_csv_20260708",
    )


__all__ = [
    "CURRENT_RESULT_KEY", "CURRENT_RUN_ID_KEY", "CURRENT_TABLE3_KEY", "CURRENT_NLP_KEY",
    "sync_settings_source_of_truth", "selected_symbols_from_settings", "current_timeframe",
    "build_table3_current", "build_nlp_sentiment_current", "build_current_result",
    "current_result_csv_bytes", "current_short_copy_text", "current_full_copy_text",
    "render_current_data_visualization", "normalize_symbol", "normalize_symbols", "selection_signature",
]
