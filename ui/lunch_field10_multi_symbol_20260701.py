"""Lunch Field 10: lazy multi-symbol rank, fusion evidence and validation."""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any
import json
import sqlite3

import pandas as pd
import streamlit as st

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, JsCode  # type: ignore
except Exception:  # optional UI dependency; ordered st.dataframe remains the fallback
    AgGrid = None  # type: ignore
    GridOptionsBuilder = None  # type: ignore
    JsCode = None  # type: ignore

from core.multi_symbol_field10_20260701 import (
    ACTIVE_KEY,
    DISPLAY_SYMBOL_KEY,
    LUNCH_SYMBOL_WIDGET_KEY,
    MAIN_SYMBOL_KEY,
    LAST_RESOURCE_KEY,
    MANIFEST_KEY,
    PROGRESS_KEY,
    SELECTED_KEY,
    activate_symbol_result,
    available_saved_symbols,
    load_field10_tables,
    normalize_selected,
    normalize_symbol,
    recover_symbol_universe,
)

FIELD10_LABEL = "10. Open / Close — Multi-Symbol Rank, Data Quality and Higher-Regime Monitor"
LEGACY_FUSION_COLUMNS: tuple[str, ...] = (
    "Final Rank", "Symbol", "Final Less-Risky Bias to Hold",
    "Final Hold Permission", "Final Entry Permission", "Final Less-Risky Bias Confidence",
    "Final Transition Bias Risk 1H", "Final Transition Bias Risk 6H",
    "Expected Value 1H", "Expected Value 6H",
    "Technical/Fundamental Rank", "Eight-Session Rank", "News/Absorption Rank",
    "Crowd Psychology Rank", "Four-Source Row References", "Four-Source Evidence Hashes",
)


def _explicit_text(value: Any, fallback: str = "Evidence Check Required") -> str:
    if value is None or value is pd.NA:
        return fallback
    try:
        if pd.isna(value):
            return fallback
    except Exception:
        pass
    text = str(value).strip()
    return fallback if text.upper() in {"", "N/A", "NA", "NONE", "NULL", "UNAVAILABLE", "NAN", "<NA>"} else text


def _metric_number(value: Any, decimals: int = 1, suffix: str = "", fallback: str = "Evidence Check Required") -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return fallback
    return f"{float(numeric):.{decimals}f}{suffix}"


def _switch_active_symbol() -> None:
    symbol = normalize_symbol(st.session_state.get("field10_active_symbol_widget_20260701") or "EURUSD")
    report = activate_symbol_result(st.session_state, symbol)
    st.session_state["field10_last_activation_20260701"] = report


def _show_progress(progress: Mapping[str, Any]) -> None:
    if not progress:
        return
    symbols = progress.get("symbols") if isinstance(progress.get("symbols"), Mapping) else {}
    terminal_complete = {"COMPLETED", "PASS", "PUBLISHED", "READY"}
    terminal_failed = {"FAILED", "FAILED_VALIDATION", "FIELD10_RESULT_INCOMPLETE", "HARD_SOURCE_UNAVAILABLE", "REJECTED", "PARTIAL"}
    completed = 0
    failed = 0
    symbol_rows = []
    for symbol, raw in symbols.items():
        item = raw if isinstance(raw, Mapping) else {}
        effective = str(item.get("publication_status") or item.get("state") or item.get("status") or "WAITING").upper()
        if effective in terminal_complete:
            completed += 1
        elif effective in terminal_failed:
            failed += 1
        symbol_rows.append({
            "Symbol": symbol,
            "Progress": f"{float(item.get('percent') or 0):.0f}%",
            "Status": item.get("status", "WAITING"),
            "Publication": effective,
            "Available / Required Candles": f"{item.get('available_candles', '-')} / {item.get('required_candles', '-')}",
            "Data Quality": item.get("data_quality", "CHECK"),
            "Stage": item.get("stage", "Queued"),
            "Elapsed Seconds": item.get("elapsed_seconds", ""),
            "Validation / Failure Reason": item.get("rejection_reason") or item.get("error") or "",
        })
    total = len(symbols)
    if total:
        remaining = max(0, total - completed - failed)
    else:
        completed = int(progress.get("completed_symbols") or 0)
        failed = int(progress.get("failed_symbols") or 0)
        remaining = int(progress.get("remaining_symbols") or 0)
        total = completed + failed + remaining
    value = float(progress.get("overall_percent") or progress.get("progress_percent") or 0.0)
    strict_complete = bool(total) and completed == total and failed == 0 and remaining == 0
    value = 100.0 if strict_complete else min(99.0, value)
    st.progress(min(1.0, max(0.0, value / 100.0)), text=f"Overall progress: {value:.1f}% — {progress.get('current_stage') or 'Ready'}")
    cols = st.columns(4)
    cols[0].metric("Completed", completed)
    cols[1].metric("Remaining", remaining)
    cols[2].metric("Failed", failed)
    eta = progress.get("estimated_remaining_seconds")
    elapsed_text = f"{float(progress.get('elapsed_seconds') or 0):.1f}s"
    if isinstance(eta, (int, float)):
        elapsed_text += f" / ETA {float(eta):.1f}s"
    cols[3].metric("Elapsed / ETA", elapsed_text)
    if symbol_rows:
        st.dataframe(pd.DataFrame(symbol_rows), use_container_width=True, hide_index=True, height=min(420, 42 + 35 * len(symbol_rows)))


def _search(frame: pd.DataFrame, query: str) -> pd.DataFrame:
    if frame.empty or not query.strip():
        return frame
    normalized = query.strip().casefold()
    mask = frame.astype(str).apply(
        lambda column: column.str.casefold().str.contains(normalized, regex=False, na=False)
    ).any(axis=1)
    return frame.loc[mask]


def _field10_history_filters(frame: pd.DataFrame, key_suffix: str = "") -> pd.DataFrame:
    """Apply display-only filters without mutating the canonical/history store."""
    if frame.empty:
        return frame
    filtered = frame.copy()
    suffix = f"_{normalize_symbol(key_suffix).lower()}" if str(key_suffix or "").strip() else ""
    with st.expander("Open / Close — Field 10 history filters", expanded=False):
        date_series = None
        if "Broker Date" in filtered.columns:
            date_series = pd.to_datetime(filtered["Broker Date"], errors="coerce").dt.date
        elif "Broker Timestamp" in filtered.columns:
            date_series = pd.to_datetime(filtered["Broker Timestamp"], errors="coerce", utc=True).dt.date
        if date_series is not None and date_series.notna().any():
            minimum, maximum = date_series.dropna().min(), date_series.dropna().max()
            selected_range = st.date_input(
                "Broker-date range", value=(minimum, maximum), min_value=minimum, max_value=maximum,
                key=f"field10_history_date_range{suffix}_20260701",
            )
            if isinstance(selected_range, (tuple, list)) and len(selected_range) == 2:
                start, end = selected_range
                filtered = filtered.loc[(date_series >= start) & (date_series <= end)]
                date_series = date_series.loc[filtered.index]

        filter_specs = (
            ("Current Session", "Session", f"field10_filter_session{suffix}_20260701"),
            ("Higher Standard Regime", "Regime", f"field10_filter_regime{suffix}_20260701"),
            ("Data Quality", "Data quality", f"field10_filter_quality{suffix}_20260701"),
            ("Less-Risky Bias", "Less-risky bias", f"field10_filter_bias{suffix}_20260701"),
            ("Final Action", "Final action", f"field10_filter_action{suffix}_20260701"),
        )
        available_specs = [spec for spec in filter_specs if spec[0] in filtered.columns]
        if available_specs:
            columns = st.columns(min(3, len(available_specs)))
            for index, (column, label, key) in enumerate(available_specs):
                options = sorted({str(v) for v in filtered[column].dropna().tolist() if str(v).strip()})
                selected = columns[index % len(columns)].multiselect(label, options=options, default=[], key=key)
                if selected:
                    filtered = filtered.loc[filtered[column].astype(str).isin(selected)]

        if "Rank" in filtered.columns:
            ranks = pd.to_numeric(filtered["Rank"], errors="coerce")
            if ranks.notna().any():
                low, high = int(ranks.min()), int(ranks.max())
                if low == high:
                    st.caption(f"Rank filter fixed at {low}; only one numerical rank is available.")
                    filtered = filtered.loc[ranks.eq(low)]
                else:
                    chosen = st.slider(
                        "Rank range", min_value=low, max_value=high, value=(low, high),
                        key=f"field10_filter_rank{suffix}_20260701",
                    )
                    filtered = filtered.loc[ranks.between(chosen[0], chosen[1], inclusive="both")]
    return filtered


def _field10_styler(frame: pd.DataFrame):
    """Use restrained status colors while preserving text labels for accessibility."""
    if frame.empty:
        return frame

    def status_css(value: Any) -> str:
        text = str(value or "").strip().upper()
        if any(token in text for token in ("UNAVAILABLE", "NOT AVAILABLE", "NOT_LOADED", "NOT LOADED", "NOT_READY", "N/A")):
            return "background-color:#eeeeee;color:#444444"
        if "BUY" in text and "NO VERIFIED" not in text:
            return "background-color:#d8f3dc;color:#153b22;font-weight:700"
        if "SELL" in text:
            return "background-color:#ffd6d6;color:#641515;font-weight:700"
        if any(token in text for token in ("FAILED", "BLOCK", "NO TRADE", "HARD FAILURE")):
            return "background-color:#ffd6d6;color:#641515;font-weight:700"
        if any(token in text for token in ("PARTIAL", "WARNING", "RETRY", "CAUTION")):
            return "background-color:#ffe8b6;color:#5c3b00;font-weight:700"
        if any(token in text for token in ("READY", "PUBLISHED", "COMPLETED", "VALIDATED")):
            return "background-color:#d8f3dc;color:#153b22;font-weight:700"
        if any(token in text for token in ("ESTIMATED", "RESAMPLED", "CAUTION", "FALLBACK L4", "MEDIUM")):
            return "background-color:#ffe8b6;color:#5c3b00;font-weight:600"
        if any(token in text for token in ("STALE", "LOW QUALITY", "FALLBACK L7", "NO VALIDATED HISTORY")):
            return "background-color:#ffd6d6;color:#641515;font-weight:600"
        if any(token in text for token in ("CACHED VALID", "CANONICAL SNAPSHOT", "CACHED")):
            return "background-color:#dcecff;color:#173a63;font-weight:600"
        if text in {"A", "PASS", "COMPLETED", "TRADE ALLOWED", "BUY", "LOW", "GOOD", "NORMAL", "PERMITTED", "VALIDATED", "HIGH"}:
            return "background-color:#d8f3dc;color:#153b22;font-weight:600"
        if text in {"B", "WARNING", "WAIT", "WAIT FOR PULLBACK", "HOLD AND PROTECT", "MODERATE", "AVERAGE", "PARTIAL", "CAUTION", "VALIDATE", "PROVISIONAL"}:
            return "background-color:#ffe8b6;color:#5c3b00;font-weight:600"
        if text in {"C", "D", "FAIL", "FAILED", "NO TRADE", "BLOCKED", "HIGH", "POOR", "STALE", "PROTECT", "BLOCK"}:
            return "background-color:#ffd6d6;color:#641515;font-weight:600"
        if text in {"UNAVAILABLE", "INSUFFICIENT_DATA", "INSUFFICIENT SAMPLE", "WAITING", "N/A", "NONE", ""}:
            return "background-color:#eeeeee;color:#444444"
        if "LOCK" in text or text in {"INFORMATIONAL", "CANONICAL"}:
            return "background-color:#dcecff;color:#173a63"
        return ""

    styled = frame.style

    # Highlight the complete row for the highest-ranked eligible symbols.
    # Cell-specific status/risk styles below remain authoritative where needed.
    rank_name = next((c for c in ("Final Rank", "Daily Rank", "Rank") if c in frame.columns), None)
    def top_row_css(row: pd.Series) -> list[str]:
        if not rank_name:
            return [""] * len(row)
        rank = pd.to_numeric(pd.Series([row.get(rank_name)]), errors="coerce").iloc[0]
        status_text = " ".join(str(row.get(c) or "") for c in (
            "Loaded Status", "Calculation Status", "Validation Status", "Safety Veto"
        ) if c in row.index).upper()
        eligible = not any(token in status_text for token in ("FAILED", "BLOCK", "NO TRADE", "HARD FAILURE"))
        if pd.notna(rank) and int(rank) <= 3 and eligible:
            return ["background-color:#ecfdf5;color:#14532d;font-weight:650"] * len(row)
        return [""] * len(row)
    styled = styled.apply(top_row_css, axis=1)
    important = [
        c for c in (
            "Status", "Data Quality", "Spread Quality", "Less-Risky Bias", "Final Action",
            "Trade Permission", "Validation Status", "Lock Status", "Calculation Status",
            "Research Data Quality", "Research Permission", "Research Action", "Conflict",
            "Drift Status", "Structural Break Status", "Tail Risk Grade",
            "Unexpected Situation Status", "Validation Permission", "Probability Calibration Status",
            "Technical Bias", "Sentiment Bias", "Session Bias", "Higher-Standard Bias",
            "NLP Sentiment Bias", "Data-Mining Sentiment Bias", "Crowd Psychology Bias",
            "Loaded Status", "Optional Evidence Availability", "Absorption Status",
            "Safety Veto", "Unexpected Status", "News/Technical Conflict",
            "Technical/Fundamental Agreement", "Stable Daily Bias", "Data Status",
            "Freshness Status", "Display Data Source",
        ) if c in frame.columns
    ]
    if important:
        if hasattr(styled, "map"):
            styled = styled.map(status_css, subset=important)
        else:  # pandas < 2.1 compatibility
            styled = styled.applymap(status_css, subset=important)

    from core.field10_display_thresholds_20260704 import THRESHOLDS
    def numeric_css(value: Any, family: str) -> str:
        number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.isna(number): return "background-color:#eeeeee;color:#444444"
        number = float(number)
        if family == "ev":
            if number < THRESHOLDS["expected_value"]["negative"]: return "background-color:#ffd6d6;color:#641515"
            if number < THRESHOLDS["expected_value"]["strong"]: return "background-color:#ffe8b6;color:#5c3b00"
            return "background-color:#d8f3dc;color:#153b22"
        if family == "prob":
            if number < THRESHOLDS["probability"]["low"]: return "background-color:#ffd6d6;color:#641515"
            if number < THRESHOLDS["probability"]["high"]: return "background-color:#ffe8b6;color:#5c3b00"
            return "background-color:#d8f3dc;color:#153b22"
        if family == "risk":
            if number <= THRESHOLDS["transition_risk"]["stable"]: return "background-color:#d8f3dc;color:#153b22"
            if number < THRESHOLDS["transition_risk"]["high"]: return "background-color:#ffe8b6;color:#5c3b00"
            return "background-color:#ffd6d6;color:#641515"
        if family == "volume":
            magnitude = abs(number)
            if magnitude >= THRESHOLDS["volume_z"]["extreme"]: return "background-color:#ffd6d6;color:#641515"
            if magnitude >= THRESHOLDS["volume_z"]["normal"]: return "background-color:#ffe8b6;color:#5c3b00"
            return "background-color:#d8f3dc;color:#153b22"
        return ""
    groups = {
        "ev": [c for c in frame.columns if "Expected Value" in c or "Risk-Adjusted EV" in c],
        "prob": [c for c in frame.columns if "Probability" in c and "%" in c],
        "risk": [c for c in frame.columns if "Transition Risk" in c],
        "volume": [c for c in frame.columns if "Volume 12H Z-Score" in c],
    }
    for family, columns in groups.items():
        if columns:
            fn = lambda value, f=family: numeric_css(value, f)
            if hasattr(styled, "map"): styled = styled.map(fn, subset=columns)
            else: styled = styled.applymap(fn, subset=columns)

    quality_columns = [c for c in frame.columns if any(token in c for token in ("Reliability", "Data Quality Score", "Coverage %", "Evidence Coverage"))]
    def quality_css(value: Any) -> str:
        number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.isna(number): return "background-color:#eeeeee;color:#444444"
        number = float(number)
        if number >= 75: return "background-color:#d8f3dc;color:#153b22"
        if number >= 50: return "background-color:#ffe8b6;color:#5c3b00"
        return "background-color:#ffd6d6;color:#641515"
    if quality_columns:
        if hasattr(styled, "map"): styled = styled.map(quality_css, subset=quality_columns)
        else: styled = styled.applymap(quality_css, subset=quality_columns)

    rank_columns = [c for c in ("Final Rank", "Daily Rank", "Rank") if c in frame.columns]
    def rank_css(value: Any) -> str:
        number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.isna(number): return ""
        rank = int(number)
        if rank <= 3: return "background-color:#166534;color:#ffffff;font-weight:750"
        if rank <= 6: return "background-color:#bfdbfe;color:#1e3a8a;font-weight:700"
        return "background-color:#f3f4f6;color:#374151"
    if rank_columns:
        if hasattr(styled, "map"): styled = styled.map(rank_css, subset=rank_columns)
        else: styled = styled.applymap(rank_css, subset=rank_columns)
    return styled


_PINNED_RETURN_COLUMNS = (
    "Time", "Completed Broker Candle", "Timeframe", "Final Rank", "Daily Rank", "Rank", "Symbol", "Final Less-Risky Bias", "Less-Risky Bias",
    "Entry Permission", "Research Entry Permission", "Calibrated Probability",
    "Managed Utility 6H", "Managed Utility 12H", "Expected Shortfall 95%",
    "Transition Risk 6H", "Transition Risk 6H (%)", "Bad Connectedness",
    "Persistent Connectedness", "Volatility Safety", "MCS Status", "Split Robustness",
    "Reliability", "Calibrated Reliability", "Data Quality", "Final Score",
    "Institutional Morning Score", "Rank Confidence", "Transition Risk 1H",
    "Transition Risk 12H", "Transition Risk 24H", "Net EV 1H", "Net EV 6H",
    "Net EV 12H", "Net EV 24H", "CVaR 95%", "Structural-Break Status",
    "Structural Break Status", "Unexpected-Situation Status", "Unexpected Situation Status",
)


def _ensure_time_columns(frame: pd.DataFrame, state: Mapping[str, Any] | None = None) -> pd.DataFrame:
    """Guarantee visible Time and Timeframe identity on every Field 10 table.

    Values are copied only from persisted publication/canonical identity.  The
    display layer never invents a candle or recalculates a timestamp.
    """
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    out = frame.copy()
    state = state if isinstance(state, Mapping) else getattr(st, "session_state", {})

    def first_column(candidates: tuple[str, ...]) -> str | None:
        return next((name for name in candidates if name in out.columns), None)

    if "Time" not in out.columns:
        source = first_column((
            "Completed Broker Candle", "Broker Timestamp", "Completed Candle",
            "Latest Completed Candle", "Latest Completed H1", "completed_candle",
            "latest_completed_h1", "locked_at", "Broker Time",
        ))
        if source:
            out.insert(0, "Time", out[source])
        elif {"Broker Date", "Broker Hour"}.issubset(out.columns):
            out.insert(0, "Time", out["Broker Date"].astype(str).str.strip() + " " + out["Broker Hour"].astype(str).str.strip())
        else:
            fallback = None
            for key in (
                "latest_completed_candle_for_run_20260705",
                "shared_broker_candle_time_20260622",
                "completed_broker_candle",
            ):
                if state.get(key):
                    fallback = state.get(key)
                    break
            if fallback is None:
                for canonical_key in (
                    "canonical_decision_result_20260617", "canonical_result_20260617",
                    "last_valid_canonical_decision_result_20260617",
                ):
                    canonical = state.get(canonical_key)
                    if isinstance(canonical, Mapping):
                        fallback = (
                            canonical.get("completed_broker_candle")
                            or canonical.get("broker_candle_time")
                            or canonical.get("latest_completed_candle_time")
                            or canonical.get("completed_candle")
                        )
                        if fallback:
                            break
            out.insert(0, "Time", fallback if fallback is not None else pd.NA)

    if "Timeframe" not in out.columns:
        source = first_column(("Canonical Timeframe", "Selected Timeframe", "timeframe"))
        if source:
            position = 1 if "Time" in out.columns else 0
            out.insert(position, "Timeframe", out[source])
        else:
            timeframe = str(state.get("selected_timeframe") or state.get("timeframe") or "").upper() or pd.NA
            position = 1 if "Time" in out.columns else 0
            out.insert(position, "Timeframe", timeframe)

    first = [column for column in ("Time", "Timeframe") if column in out.columns]
    return out.loc[:, first + [column for column in out.columns if column not in first]]


def _rank_column_order(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep decision-critical return, EV, probability, risk and volume columns at the far left."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    if "Final Rank" not in frame.columns and {"Expected Return 24H (%)", "Expected Return 36H (%)"}.issubset(frame.columns):
        legacy_first = ["Expected Return 24H (%)", "Expected Return 36H (%)"]
        return frame.loc[:, legacy_first + [column for column in frame.columns if column not in legacy_first]]
    first = [column for column in _PINNED_RETURN_COLUMNS if column in frame.columns]
    return frame.loc[:, first + [column for column in frame.columns if column not in first]]


def _first_existing(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    return next((name for name in candidates if name in columns), None)


def _display_value(value: Any) -> Any:
    try:
        if value is None or pd.isna(value):
            return "—"
    except Exception:
        if value is None:
            return "—"
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "nat", "inf", "-inf"}:
        return "—"
    # Mobile metrics and detail cards use strings, so normalize binary floating
    # artefacts without converting an unavailable estimate to zero.
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".") or "0"
    return value


def _render_mobile_cards(view: pd.DataFrame, *, max_rows: int = 20) -> None:
    """Readable mobile row-detail presentation with decision metrics first."""
    if view.empty:
        st.info("No rows match the current filters.")
        return
    columns = list(view.columns)
    rank_col = _first_existing(columns, ("Final Rank", "Daily Rank", "Rank", "Eligible Rank"))
    symbol_col = _first_existing(columns, ("Symbol", "Instrument"))
    bias_col = _first_existing(columns, ("Final Less-Risky Bias", "Less-Risky Bias", "Higher-Standard Bias", "Technical Bias", "Protected Final Action", "Final Action"))
    reliability_col = _first_existing(columns, ("Reliability", "Calibrated Reliability", "Reliability Score", "Technical Reliability", "Higher Reliability"))
    ev_col = _first_existing(columns, ("Managed Utility 6H", "Managed Utility 12H", "Net EV 6H", "Expected Value 6H (%)", "Expected Value", "Risk-Adjusted EV", "Expected Return 6H (%)", "Expected Return 12H (%)", "Expected Return 24H (%)"))
    risk_col = _first_existing(columns, ("Expected Shortfall 95%", "Transition Risk 6H", "Transition Risk 6H (%)", "Bad Connectedness", "Persistent Connectedness", "Transition Risk 3H", "Transition Risk 1H", "CVaR 95%"))
    time_col = _first_existing(columns, ("Time", "Completed Broker Candle", "Broker Timestamp", "Broker Hour"))
    timeframe_col = _first_existing(columns, ("Timeframe", "Canonical Timeframe"))
    primary = {c for c in (rank_col, symbol_col, time_col, timeframe_col, bias_col, reliability_col, ev_col, risk_col) if c}
    shown = view.head(max_rows)
    for position, (_, row) in enumerate(shown.iterrows(), start=1):
        rank = row.get(rank_col) if rank_col else position
        symbol = row.get(symbol_col) if symbol_col else f"Row {position}"
        with st.container(border=True):
            st.markdown(f"**#{rank} · {symbol}**")
            if time_col or timeframe_col:
                st.caption(f"{_display_value(row.get(time_col)) if time_col else '—'} · {_display_value(row.get(timeframe_col)) if timeframe_col else '—'}")
            cols = st.columns(2)
            cols[0].metric("Bias", _display_value(row.get(bias_col)) if bias_col else "—")
            cols[1].metric("Reliability", _display_value(row.get(reliability_col)) if reliability_col else "—")
            cols2 = st.columns(2)
            cols2[0].metric("Expected Value / Return", _display_value(row.get(ev_col)) if ev_col else "—")
            cols2[1].metric("Risk", _display_value(row.get(risk_col)) if risk_col else "—")
            details = [(column, _display_value(row.get(column))) for column in columns if column not in primary]
            if details:
                with st.expander("View Details", expanded=False):
                    detail_frame = pd.DataFrame(details, columns=["Metric", "Value"])
                    st.dataframe(detail_frame, use_container_width=True, hide_index=True)
    if len(view) > len(shown):
        st.caption(f"Showing the first {len(shown):,} of {len(view):,} rows in mobile cards. Use filters or Compact Table for the remaining rows.")


def _display_field10_table(
    frame: pd.DataFrame, *, height: int, pin_expected_returns: bool = False, key: str | None = None,
    allow_cards: bool = True,
) -> None:
    view = _ensure_time_columns(frame, st.session_state)
    view = _rank_column_order(view) if pin_expected_returns else view
    if isinstance(view, pd.DataFrame):
        try:
            view = view.drop_duplicates(keep="first").reset_index(drop=True)
        except Exception:
            pass
    if pin_expected_returns:
        st.caption("Legend: EV/probability — red weak, amber uncertain, green validated; transition risk — green stable, amber moderate, red high; unexpected status — NORMAL / CAUTION / PROTECT / BLOCK.")

    counter_key = "field10_table_render_counter_20260705"
    counter = int(st.session_state.get(counter_key, 0) or 0) + 1
    st.session_state[counter_key] = counter
    widget_key = f"{key or f'field10_table_{counter}'}_layout_20260705"
    phone = bool(st.session_state.get("phone_mode") or st.session_state.get("mobile_lite_mode_20260628"))
    # Large histories default to the compact horizontally scrollable table on
    # phones; card mode is reserved for short decision/rank tables.
    default_index = 1 if phone and len(view) <= 20 else 0
    if allow_cards:
        layout = st.radio(
            "Table layout",
            ("Show Compact Table", "Show Detailed Cards"),
            index=default_index,
            horizontal=True,
            key=widget_key,
            label_visibility="collapsed",
        )
        if layout == "Show Detailed Cards":
            _render_mobile_cards(view, max_rows=20)
            return

    if pin_expected_returns and AgGrid is not None and GridOptionsBuilder is not None and not view.empty:
        try:
            builder = GridOptionsBuilder.from_dataframe(view)
            builder.configure_default_column(filter=True, sortable=True, resizable=True, wrapText=True, autoHeight=True, minWidth=125)
            for column in _PINNED_RETURN_COLUMNS:
                if column in view.columns:
                    builder.configure_column(column, pinned="left", width=165)
            for column in ("Time", "Completed Broker Candle", "Timeframe", "Final Rank", "Daily Rank", "Rank", "Symbol", "Final Less-Risky Bias", "Less-Risky Bias", "Reliability", "Calibrated Reliability"):
                if column in view.columns:
                    width = 155 if column in {"Time", "Completed Broker Candle"} else (125 if column == "Symbol" else 110)
                    builder.configure_column(column, pinned="left", width=width, wrapText=True, autoHeight=True)
            builder.configure_pagination(paginationAutoPageSize=True)
            grid_options = builder.build()
            if JsCode is not None:
                status_style = JsCode("""
                    function(params) {
                        const text = String(params.value ?? '').trim().toUpperCase();
                        if (!text || ['N/A','NONE'].includes(text) || text.includes('UNAVAILABLE') || text.includes('NOT AVAILABLE') || text.includes('NOT_LOADED') || text.includes('NOT_READY'))
                            return {'backgroundColor':'#eeeeee','color':'#444444'};
                        if (text.includes('BUY') || text.includes('READY') || text.includes('PUBLISHED') || text.includes('VALIDATED') || text.includes('COMPLETED') || text === 'PASS')
                            return {'backgroundColor':'#d8f3dc','color':'#153b22','fontWeight':'700'};
                        if (text.includes('SELL') || text.includes('FAILED') || text.includes('BLOCK') || text.includes('NO TRADE'))
                            return {'backgroundColor':'#ffd6d6','color':'#641515','fontWeight':'700'};
                        if (text.includes('WAIT') || text.includes('NEUTRAL') || text.includes('PARTIAL') || text.includes('WARNING') || text.includes('RETRY') || text.includes('CAUTION'))
                            return {'backgroundColor':'#ffe8b6','color':'#5c3b00','fontWeight':'650'};
                        return null;
                    }
                """)
                for status_column in (
                    "Higher-Standard Bias", "Less-Risky Bias", "NLP Sentiment Bias",
                    "Data-Mining Sentiment Bias", "Crowd Psychology Bias", "Loaded Status",
                    "Calculation Status", "Validation Status", "Safety Veto",
                    "Unexpected Status", "Absorption Status", "Optional Evidence Availability",
                ):
                    if status_column in view.columns:
                        builder.configure_column(status_column, cellStyle=status_style)
                grid_options = builder.build()
                grid_options["getRowStyle"] = JsCode("""
                    function(params) {
                        const raw = params.data['Final Rank'] ?? params.data['Daily Rank'] ?? params.data['Rank'];
                        const rank = Number(raw);
                        const status = [
                            params.data['Loaded Status'], params.data['Calculation Status'],
                            params.data['Validation Status'], params.data['Safety Veto']
                        ].map(v => String(v ?? '').toUpperCase()).join(' ');
                        const eligible = !['FAILED','BLOCK','NO TRADE','HARD FAILURE'].some(token => status.includes(token));
                        if (rank <= 3 && eligible) return {'backgroundColor':'#dcfce7','color':'#14532d','fontWeight':'750'};
                        if (rank <= 6 && eligible) return {'backgroundColor':'#dbeafe','color':'#1e3a8a','fontWeight':'700'};
                        return null;
                    }
                """)
            AgGrid(
                view, gridOptions=grid_options, height=height,
                key=key or f"field10_pinned_rank_table_{counter}_20260705",
                fit_columns_on_grid_load=False, allow_unsafe_jscode=JsCode is not None,
                theme="streamlit",
            )
            return
        except Exception:
            pass
    st.dataframe(_field10_styler(view), use_container_width=True, hide_index=True, height=height)

def _core_charts(daily: pd.DataFrame, hourly: pd.DataFrame) -> None:
    if not daily.empty and {"Symbol", "Data Quality Score"}.issubset(daily.columns):
        st.markdown("##### Today — Data Quality by Symbol")
        chart = daily[["Symbol", "Data Quality Score"]].dropna().set_index("Symbol")
        if not chart.empty:
            st.bar_chart(chart, use_container_width=True)
    if not hourly.empty and {"Data Quality Score", "Reliability"}.issubset(hourly.columns):
        scatter = hourly[["Data Quality Score", "Reliability"]].apply(pd.to_numeric, errors="coerce").dropna()
        if not scatter.empty and hasattr(st, "scatter_chart"):
            st.markdown("##### Hourly Data Quality vs Higher-Regime Reliability")
            st.scatter_chart(scatter, x="Data Quality Score", y="Reliability", use_container_width=True)
    if not hourly.empty and "Data Quality Score" in hourly.columns:
        values = pd.to_numeric(hourly["Data Quality Score"], errors="coerce").dropna()
        if not values.empty:
            bins = pd.cut(values, bins=[-0.01, 60, 75, 90, 100], labels=["D", "C", "B", "A"], include_lowest=True)
            hist = bins.value_counts(sort=False).rename("Hours").to_frame()
            st.markdown("##### Hourly Data-Quality Grade Distribution")
            st.bar_chart(hist, use_container_width=True)
    if not daily.empty and {"Expected Value 6H (%)", "Transition Risk 6H (%)", "Symbol"}.issubset(daily.columns):
        chart = daily[["Symbol", "Expected Value 6H (%)", "Transition Risk 6H (%)"]].copy()
        chart[["Expected Value 6H (%)", "Transition Risk 6H (%)"]] = chart[["Expected Value 6H (%)", "Transition Risk 6H (%)"]].apply(pd.to_numeric, errors="coerce")
        chart = chart.dropna()
        if not chart.empty and hasattr(st, "scatter_chart"):
            st.markdown("##### EV 6H versus Transition Risk 6H")
            st.scatter_chart(chart, x="Transition Risk 6H (%)", y="Expected Value 6H (%)", size=None, use_container_width=True)
    if not daily.empty and {"Symbol", "Probability Reach EV 6H (%)"}.issubset(daily.columns):
        chart = daily[["Symbol", "Probability Reach EV 6H (%)"]].copy()
        chart["Probability Reach EV 6H (%)"] = pd.to_numeric(chart["Probability Reach EV 6H (%)"], errors="coerce")
        chart = chart.dropna().set_index("Symbol")
        if not chart.empty:
            st.markdown("##### Probability Reach EV 6H by Symbol")
            st.bar_chart(chart, use_container_width=True)
    if not daily.empty and {"Symbol", "Unexpected Situation Severity"}.issubset(daily.columns):
        chart = daily[["Symbol", "Unexpected Situation Severity"]].copy()
        chart["Unexpected Situation Severity"] = pd.to_numeric(chart["Unexpected Situation Severity"], errors="coerce")
        chart = chart.dropna().set_index("Symbol")
        if not chart.empty:
            st.markdown("##### Unexpected-Situation Severity")
            st.bar_chart(chart, use_container_width=True)
    if not daily.empty and {"Symbol", "Volume 12H Z-Score"}.issubset(daily.columns):
        chart = daily[["Symbol", "Volume 12H Z-Score"]].copy()
        chart["Volume 12H Z-Score"] = pd.to_numeric(chart["Volume 12H Z-Score"], errors="coerce")
        chart = chart.dropna().set_index("Symbol")
        if not chart.empty:
            st.markdown("##### 12H Volume Z-Score")
            st.bar_chart(chart, use_container_width=True)


_RESEARCH_GROUPS: Mapping[str, tuple[str, ...]] = {
    "Core Rank & Actions": (
        "Research Rank", "Rank Pool", "Symbol", "Broker Timestamp", "Production Action", "Research Action",
        "Research Permission", "Conflict", "Research Reliability", "Research Data Quality",
        "Research Data Quality Score", "Calculation Status", "Research Explanation",
    ),
    "Regime & Lifecycle": (
        "Research Rank", "Rank Pool", "Symbol", "Broker Timestamp", "Regime Probability", "Regime Entropy",
        "Expected Regime Duration", "Estimated Remaining Duration", "Transition Risk 1H",
        "Transition Risk 3H", "Transition Risk 6H", "Transition Risk 24H", "Expected Return 12H (%)",
        "Expected Return 24H (%)", "Expected Return 36H (%)",
        "Structural Break Status", "Break Count",
        "Break Strength", "Research Action",
    ),
    "Calibration & Intervals": (
        "Research Rank", "Rank Pool", "Symbol", "Broker Timestamp", "Brier Score", "Log Loss",
        "Calibration Error", "Conformal Status", "Conformal Coverage", "Interval Width",
        "DM p-value", "DM Candidate Superior", "SPA p-value", "SPA Superior",
    ),
    "Drift & State": (
        "Research Rank", "Rank Pool", "Symbol", "Broker Timestamp", "Drift Status", "Adaptive Window Size",
        "State Stability", "Innovation Z", "Structural Break Status", "Break Count", "Break Strength",
        "Calculation Status", "Research Explanation",
    ),
    "Portfolio & Tail Risk": (
        "Research Rank", "Rank Pool", "Symbol", "Broker Timestamp", "Correlation Cluster",
        "Duplicate Exposure Penalty", "CVaR 95", "Tail Risk Grade", "Research Reliability",
        "Research Permission", "Research Action",
    ),
}


def _research_view(frame: pd.DataFrame, group: str) -> pd.DataFrame:
    if frame.empty or group == "Full Research Audit":
        return frame
    columns = [column for column in _RESEARCH_GROUPS.get(group, ()) if column in frame.columns]
    return frame.loc[:, columns] if columns else frame


def _research_charts(current: pd.DataFrame, history: pd.DataFrame) -> None:
    if current.empty:
        return
    options = [
        "Research Reliability by Symbol",
        "Transition Risk by Symbol",
        "Tail Risk and Concentration",
        "Active-Symbol Research History",
    ]
    selected = st.selectbox("Research visualization", options, key="field10_research_chart_selector_20260701")
    if selected == "Research Reliability by Symbol":
        cols = [c for c in ("Symbol", "Research Reliability", "Research Data Quality Score") if c in current.columns]
        chart = current[cols].copy()
        if "Symbol" in chart and len(cols) > 1:
            chart = chart.set_index("Symbol").apply(pd.to_numeric, errors="coerce")
            st.bar_chart(chart, use_container_width=True)
    elif selected == "Transition Risk by Symbol":
        cols = [c for c in ("Symbol", "Transition Risk 1H", "Transition Risk 3H", "Transition Risk 6H", "Transition Risk 24H") if c in current.columns]
        chart = current[cols].copy()
        if "Symbol" in chart and len(cols) > 1:
            chart = chart.set_index("Symbol").apply(pd.to_numeric, errors="coerce")
            st.line_chart(chart, use_container_width=True)
    elif selected == "Tail Risk and Concentration":
        cols = [c for c in ("Symbol", "CVaR 95", "Duplicate Exposure Penalty") if c in current.columns]
        chart = current[cols].copy()
        if "Symbol" in chart and len(cols) > 1:
            chart = chart.set_index("Symbol").apply(pd.to_numeric, errors="coerce")
            st.bar_chart(chart, use_container_width=True)
    else:
        if history.empty:
            st.info("Research history becomes available after Field 10 is opened for more than one completed generation.")
            return
        work = history.copy()
        time = pd.to_datetime(work.get("Broker Timestamp"), errors="coerce", utc=True)
        value_columns = [c for c in ("Research Reliability", "Research Data Quality Score", "Transition Risk 3H") if c in work.columns]
        if not value_columns or time.notna().sum() == 0:
            st.info("The stored research history has no chartable completed-candle values yet.")
            return
        work = work.loc[time.notna(), value_columns].apply(pd.to_numeric, errors="coerce")
        work.index = pd.DatetimeIndex(time.loc[time.notna()])
        st.line_chart(work.sort_index(), use_container_width=True)



def _render_v3_rank_candidate(active: str, parent_run_id: str) -> None:
    """Read-only v3 institutional candidate; never imports fitting modules."""
    from core.multi_symbol_field10_20260701 import DB_PATH
    from core.field10_research_readonly_20260705 import (
        load_v3_candidate_details, load_v3_candidate_summary,
    )

    st.markdown("#### Field 10 Rank Utility v3 — Institutional Research Candidate")
    st.error("SHADOW_ONLY · Production rank and locked daily bias remain unchanged")
    summary = load_v3_candidate_summary(path=DB_PATH, parent_run_id=parent_run_id or None)
    if summary.empty:
        st.info(
            "No v3 row is published for this canonical run. Run the deployment migration, then use the existing "
            "Settings → Run Calculation + Open Lunch orchestration. Opening Lunch never calculates this candidate."
        )
        return

    def pct(series: pd.Series) -> pd.Series:
        values = pd.to_numeric(series, errors="coerce")
        return values.where(values.abs() > 1.0, values * 100.0)

    view = pd.DataFrame({
        "Rank": summary.get("research_rank"),
        "Symbol": summary.get("symbol"),
        "Less-Risky Bias": summary.get("locked_bias"),
        "Entry Permission": summary.get("entry_permission"),
        "Final Research Score": pd.to_numeric(summary.get("coverage_adjusted_score"), errors="coerce").round(2),
        "Probability Top 3 (%)": pct(summary.get("probability_top_3", pd.Series(index=summary.index, dtype=float))).round(1),
        "90% Rank Range": summary.apply(
            lambda row: "—" if pd.isna(row.get("rank_lower_90")) or pd.isna(row.get("rank_upper_90"))
            else f"{float(row.get('rank_lower_90')):.1f}–{float(row.get('rank_upper_90')):.1f}", axis=1,
        ),
        "Expected Return 3H (%)": (100.0 * pd.to_numeric(summary.get("expected_return_3h"), errors="coerce")).round(4),
        "Expected Return 6H (%)": (100.0 * pd.to_numeric(summary.get("expected_return_6h"), errors="coerce")).round(4),
        "Expected Shortfall 6H (%)": (100.0 * pd.to_numeric(summary.get("expected_shortfall_6h"), errors="coerce")).round(4),
        "Transition Risk 6H (%)": pd.to_numeric(summary.get("transition_risk_6h"), errors="coerce").round(2),
        "Reliability": pd.to_numeric(summary.get("reliability"), errors="coerce").round(2),
        "Evidence Coverage (%)": (100.0 * pd.to_numeric(summary.get("evidence_coverage"), errors="coerce")).round(1),
        "Data Quality": pd.to_numeric(summary.get("data_quality"), errors="coerce").round(1),
        "Fallback Level": summary.get("fallback_level"),
        "Diversification-Adjusted Rank": summary.get("diversification_adjusted_rank"),
        "Production Rank (Unchanged)": summary.get("production_rank"),
        "Promotion Status": summary.get("promotion_status"),
    })
    def status_text(row: pd.Series) -> str:
        permission = str(row.get("Entry Permission") or "").upper()
        coverage = pd.to_numeric(pd.Series([row.get("Evidence Coverage (%)")]), errors="coerce").iloc[0]
        fallback = str(row.get("Fallback Level") or "NONE").upper()
        rank = pd.to_numeric(pd.Series([row.get("Rank")]), errors="coerce").iloc[0]
        if "BLOCK" in permission:
            return "BLOCKED"
        if pd.notna(coverage) and coverage < 80.0:
            return "PARTIAL EVIDENCE"
        if fallback not in {"", "NONE"}:
            return "FALLBACK-SUPPORTED"
        if "CAUTION" in permission:
            return "CAUTION"
        if pd.notna(rank) and rank <= 4:
            return "TOP 4 ELIGIBLE"
        return "ELIGIBLE SHADOW"
    view.insert(4, "Readable Status", view.apply(status_text, axis=1))
    st.caption(
        "Standalone research rank is primary. Diversification-adjusted rank is separate and never silently replaces it. "
        "Status text is retained so colour is not required to understand CAUTION, BLOCKED, partial, or fallback rows."
    )
    _display_field10_table(view, height=min(610, 48 + 38 * max(1, len(view))), pin_expected_returns=True,
                           key="field10_rank_utility_v3_main_20260705")

    daily_snapshot_id = str(summary.iloc[0].get("daily_snapshot_id") or "")
    active_row = summary.loc[summary["symbol"].astype(str).str.upper() == normalize_symbol(active)]
    with st.expander(f"Open / Close — {normalize_symbol(active)} v3 Formula, Horizons and Validation Evidence", expanded=False):
        if active_row.empty:
            st.info("The selected symbol has no identity-matched v3 row in this publication.")
            return
        record = active_row.iloc[0]
        try:
            evidence = json.loads(str(record.get("evidence_json") or "{}"))
        except Exception:
            evidence = {}
        horizon_rows = []
        horizons = evidence.get("horizons") if isinstance(evidence, Mapping) else {}
        for horizon in (1, 3, 6, 12, 24, 36):
            item = horizons.get(str(horizon), horizons.get(horizon, {})) if isinstance(horizons, Mapping) else {}
            if not isinstance(item, Mapping):
                continue
            horizon_rows.append({
                "Horizon": f"{horizon}H", "Status": item.get("status"),
                "P Favourable": item.get("probability_favourable_return"), "P Adverse": item.get("probability_adverse_return"),
                "Median Gain": item.get("median_favourable_return"), "Median Loss": item.get("median_adverse_return"),
                "Gross EV": item.get("gross_expected_value"), "Spread Cost": item.get("spread_cost"),
                "Slippage Cost": item.get("slippage_cost"), "Net EV": item.get("net_expected_value"),
                "VaR 95%": item.get("directional_var_95"), "Expected Shortfall 95%": item.get("directional_expected_shortfall_95"),
                "ES/VaR": item.get("es_var_severity_ratio"), "HAR Volatility": item.get("har_forecast_volatility"),
                "Adverse Semivariance": item.get("adverse_semivariance"), "Transition Return Equivalent": item.get("transition_risk_return_equivalent"),
                "Short Connectedness": item.get("short_frequency_connectedness"), "Persistent Connectedness": item.get("persistent_connectedness"),
                "Conformal Lower": item.get("conformal_lower_return"), "Conformal Median": item.get("conformal_median_return"),
                "Conformal Upper": item.get("conformal_upper_return"), "Interval Width": item.get("conformal_interval_width"),
                "Calibration Error": item.get("probability_calibration_error"), "Model Disagreement": item.get("model_disagreement_pct"),
                "Managed Utility": item.get("managed_utility"), "Sample Count": item.get("sample_count"),
            })
        if horizon_rows:
            st.markdown("##### Independent Horizon Calculations and Return-Unit Contributions")
            _display_field10_table(pd.DataFrame(horizon_rows), height=420, key="field10_v3_horizon_detail_20260705")
        details = load_v3_candidate_details(daily_snapshot_id, path=DB_PATH, symbol=normalize_symbol(active))
        labels = {
            "field10_probability_calibration_v2": "Probability Calibration and Conformal Evidence",
            "field10_structural_break_v2": "Structural Break and Regime Protection",
            "field10_rank_uncertainty": "Chronological Rank Uncertainty",
            "field10_evidence_clusters": "Evidence Clusters and Effective Weights",
            "field10_rank_components_v3": "Formula Component Contributions",
            "field10_pbo_results": "PBO / Backtest-Overfitting Control",
            "field10_candidate_experiments": "Frozen Experiment Registry",
            "field10_promotion_decisions": "Promotion Governance",
        }
        for table, label in labels.items():
            frame = details.get(table, pd.DataFrame())
            if frame.empty:
                continue
            st.markdown(f"##### {label}")
            _display_field10_table(frame, height=min(420, 48 + 35 * max(1, len(frame))), key=f"field10_v3_{table}_20260705")

def _render_research_layer(state: MutableMapping[str, Any], active: str, parent_run_id: str) -> None:
    _render_v3_rank_candidate(active, parent_run_id)
    from core.field10_ten_paper_research_20260701 import (
        STATE_KEY,
        load_field10_research_tables,
        load_research_registries,
        research_integrity_rows,
    )

    report = state.get(STATE_KEY) if isinstance(state.get(STATE_KEY), Mapping) else {}
    if not report.get("ok"):
        st.warning(str(report.get("errors") or report.get("status") or "Research validation is unavailable."))
    else:
        st.caption(
            f"Ten-paper research layer: {report.get('status')} · calculated {report.get('calculated_symbols', 0)} · "
            f"cached {report.get('cached_symbols', 0)} · {float(report.get('elapsed_seconds') or 0):.3f}s. "
            "This result was produced during Run Calculation; opening Field 10 performs no research calculation."
        )
    tables = load_field10_research_tables(state, parent_run_id=parent_run_id, symbol=active)
    current, history = tables["current"], tables["history"]

    st.markdown("#### Institutional Quant Research Validation — Read-Only")
    if current.empty:
        st.info("No research rows were published. Missing or mismatched canonical identities were not replaced with placeholder statistics.")
    else:
        group = st.selectbox(
            "Research column group",
            [*_RESEARCH_GROUPS.keys(), "Full Research Audit"],
            key="field10_research_column_group_20260701",
        )
        query = st.text_input(
            "Search research results", key="field10_research_search_20260701",
            placeholder="symbol, drift, break, action, grade, explanation…",
        )
        view = _search(_research_view(current, group), query)
        _display_field10_table(view, height=min(560, 42 + 35 * max(1, len(view))))

    with st.expander("Open / Close — Ten-Paper Research History (latest 25 days / 600 rows)", expanded=False):
        if history.empty:
            st.info("No prior completed-generation research history is stored for this symbol.")
        else:
            research_query = st.text_input(
                "Search research history", key="field10_research_history_search_20260701",
                placeholder="action, status, model version, run ID…",
            )
            _display_field10_table(_search(history, research_query), height=520)

    _research_charts(current, history)

    with st.expander("Open / Close — Model and SPA Experiment Registries", expanded=False):
        registries = load_research_registries(parent_run_id=parent_run_id)
        st.markdown("##### Model Version Registry")
        if registries["models"].empty:
            st.info("No model-version registry row is available.")
        else:
            st.dataframe(registries["models"], use_container_width=True, hide_index=True)
        st.markdown("##### SPA / Candidate Experiment Registry")
        if registries["experiments"].empty:
            st.info("No experiment row is available for this parent run.")
        else:
            st.dataframe(registries["experiments"], use_container_width=True, hide_index=True, height=360)

    with st.expander("Open / Close — Field 10 Research Post-Run Integrity", expanded=False):
        integrity = pd.DataFrame(research_integrity_rows(state))
        st.dataframe(integrity, use_container_width=True, hide_index=True, height=min(360, 42 + 35 * max(1, len(integrity))))


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig") if isinstance(frame, pd.DataFrame) else b""


def _render_scope_matrix(manifest: Mapping[str, Any], selected: list[str], main: str) -> None:
    matrix = manifest.get("scope_matrix") if isinstance(manifest.get("scope_matrix"), Mapping) else {}
    statuses = manifest.get("symbol_status") if isinstance(manifest.get("symbol_status"), Mapping) else {}
    rows = []
    for symbol in selected:
        item = statuses.get(symbol) if isinstance(statuses.get(symbol), Mapping) else {}
        rows.append({
            "Symbol": symbol,
            "Role": "MAIN PRODUCTION" if symbol == main else "SECONDARY LUNCH",
            "Calculated Fields": matrix.get(symbol) or ("Fields 1–9 + AI" if symbol == main else "Fields 1–3 + Field 10"),
            "Status": item.get("status", "SAVED"),
            "Elapsed Seconds": item.get("elapsed_seconds", ""),
            "Data Quality": item.get("data_quality", ""),
        })
    st.markdown("#### Multi-Symbol Calculation Scope Matrix")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=min(390, 42 + 35 * max(1, len(rows))))
    st.caption(
        "Only the main symbol owns Fields 4–9 and AI. Secondary symbols are restricted to Fields 1–3 plus Field 10, "
        "which prevents duplicated heavy calculations and keeps symbol switching read-only."
    )


def _integrated_filter_options(frame: pd.DataFrame, column: str) -> list[str]:
    if frame.empty or column not in frame.columns:
        return []
    return sorted({str(value) for value in frame[column].dropna().tolist() if str(value).strip()})


def _render_integrated_evidence_sections(
    state: MutableMapping[str, Any], parent_run_id: str, selected: list[str], main: str,
) -> None:
    from core.field10_integrated_evidence_20260702 import (
        load_integrated_current, prepare_evidence_alignment_heatmap, query_integrated_history,
    )

    current = load_integrated_current(parent_run_id) if parent_run_id else pd.DataFrame()
    st.markdown("#### Multi-Symbol Technical + Sentiment + Session + Regime Intelligence — Current Completed H1")
    if current.empty:
        st.warning("No identity-verified Field 1 Table 4 evidence was published for this parent run. Empty rows were not treated as success.")
    else:
        visible = [
            "Rank", "Symbol", "Role", "Broker Date", "Broker Hour", "Current Session",
            "Technical Bias", "Technical Reliability", "Sentiment Bias", "Sentiment Reliability",
            "Session Bias", "Session Reliability", "Higher Standard Regime", "Regime Bias",
            "Regime Probability", "Regime Entropy", "Transition Risk 1H", "Transition Risk 3H",
            "Transition Risk 6H", "Transition Risk 24H", "Expected Return 12H (%)",
            "Expected Return 24H (%)", "Expected Return 36H (%)",
            "Existing Combined Evidence Bias", "Evidence Agreement Percentage",
            "Conflict Index", "Change Probability", "Drift Status", "Calibrated Reliability",
            "Data Quality Grade", "Spread Quality", "Correlation Cluster", "Duplicate Exposure Penalty",
            "Trade Permission", "Protected Final Action", "Explanation",
        ]
        filtered = current.copy(deep=False)
        key = normalize_symbol(main).lower()
        with st.expander("Open / Close — Current integrated-evidence filters", expanded=False):
            query = st.text_input(
                "Search all current integrated-evidence columns",
                key=f"field10_integrated_current_search_{key}_20260702",
            )
            filtered = _search(filtered, query)
            specs = (
                "Symbol", "Role", "Current Session", "Technical Bias", "Sentiment Bias", "Regime Bias",
                "Higher Standard Regime", "Data Quality Grade", "Drift Status", "Trade Permission",
                "Protected Final Action",
            )
            controls = st.columns(3)
            for index, column in enumerate(specs):
                options = _integrated_filter_options(current, column)
                if not options:
                    continue
                chosen = controls[index % 3].multiselect(
                    column, options=options, default=[],
                    key=f"field10_integrated_current_{column.lower().replace(' ', '_').replace('-', '_')}_{key}_20260702",
                )
                if chosen:
                    filtered = filtered.loc[filtered[column].astype(str).isin(chosen)]
            if "Rank" in current.columns:
                ranks = pd.to_numeric(current["Rank"], errors="coerce")
                if ranks.notna().any():
                    low, high = int(ranks.min()), int(ranks.max())
                    if low == high:
                        st.caption(f"Rank filter fixed at {low}; only one numerical rank is available.")
                        filtered = filtered.loc[pd.to_numeric(filtered["Rank"], errors="coerce").eq(low)]
                    else:
                        chosen_range = st.slider(
                            "Rank range", low, high, (low, high),
                            key=f"field10_integrated_current_rank_{key}_20260702",
                        )
                        filtered = filtered.loc[pd.to_numeric(filtered["Rank"], errors="coerce").between(*chosen_range)]
        current_view = filtered.loc[:, [column for column in visible if column in filtered.columns]]
        _display_field10_table(current_view, height=min(560, 42 + 35 * max(1, len(current_view))))
        st.download_button(
            "⬇ Current Integrated Evidence CSV", data=_csv_bytes(filtered),
            file_name=f"field10_integrated_current_{parent_run_id}.csv", mime="text/csv",
            use_container_width=True, key=f"field10_integrated_current_download_{key}_20260702",
        )

        with st.expander("Open / Close — Multi-Symbol Evidence Alignment Heatmap", expanded=False):
            st.caption("Transition Safety is display-only and equals 1 − Transition Risk 3H. Missing evidence remains null, not zero.")
            heatmap_frame, hover_frame = prepare_evidence_alignment_heatmap(current)
            if heatmap_frame.empty:
                st.info("No complete current frame is available for the heatmap.")
            else:
                import plotly.graph_objects as go
                figure = go.Figure(data=go.Heatmap(
                    z=heatmap_frame.to_numpy(dtype=float),
                    x=list(heatmap_frame.columns), y=list(heatmap_frame.index),
                    text=hover_frame.to_numpy(dtype=object),
                    hovertemplate="%{text}<extra></extra>", zmin=-1.0, zmax=1.0,
                    colorbar={"title": "Evidence / normalized score"},
                ))
                figure.update_layout(
                    title="Multi-Symbol Evidence Alignment Heatmap",
                    xaxis_title="Evidence family", yaxis_title="Field 10 rank order",
                    height=max(360, 52 * len(heatmap_frame) + 180),
                )
                st.plotly_chart(figure, use_container_width=True, key=f"field10_integrated_heatmap_{key}_20260702")

    st.markdown("#### Multi-Symbol Integrated Evidence History — Last 25 Broker Days")
    with st.expander("Open / Close — Integrated history filters and pagination", expanded=False):
        # The full saved universe is always retained; Field 10 no longer owns a
        # competing symbol selector. Search/diagnostic filters remain display-only.
        chosen_symbols = list(selected)
        st.caption("Symbols: full global loaded/completed universe (read-only)")
        search = st.text_input(
            "Search integrated history", key=f"field10_integrated_history_search_{normalize_symbol(main).lower()}_20260702",
            placeholder="bias, regime, source ID, action, explanation…",
        )
        filter_values: dict[str, list[str]] = {}
        current_for_options = current if not current.empty else pd.DataFrame()
        filter_specs = (
            "Role", "Current Session", "Technical Bias", "Sentiment Bias", "Regime Bias",
            "Higher Standard Regime", "Data Quality Grade", "Drift Status", "Trade Permission",
            "Protected Final Action", "Validation Permission", "Outcome Settled",
        )
        controls = st.columns(3)
        for index, column in enumerate(filter_specs):
            options = _integrated_filter_options(current_for_options, column)
            if not options:
                continue
            chosen = controls[index % 3].multiselect(
                column, options=options, default=[],
                key=f"field10_integrated_history_{column.lower().replace(' ', '_').replace('-', '_')}_20260702",
            )
            if chosen:
                filter_values[column] = chosen
        page_size = st.selectbox(
            "Rows per page", [50, 100, 200, 500], index=2,
            key="field10_integrated_history_page_size_20260702",
        )
        page = st.number_input(
            "Page", min_value=1, value=1, step=1,
            key="field10_integrated_history_page_20260702",
        )
    history, total = query_integrated_history(
        symbols=chosen_symbols or [], filters=filter_values, search=search,
        limit=int(page_size), offset=(int(page) - 1) * int(page_size),
    )
    st.caption(f"Showing {len(history):,} rows on page {int(page):,}; {total:,} filtered persisted rows in total.")
    if history.empty:
        st.info("No persisted integrated-evidence rows match the current filters.")
    else:
        _display_field10_table(history, height=540)
    export_frame, export_total = query_integrated_history(
        symbols=chosen_symbols or [], filters=filter_values, search=search,
        complete_export=True,
    )
    st.download_button(
        "⬇ Complete Filtered Integrated History CSV", data=_csv_bytes(export_frame),
        file_name=f"field10_integrated_history_filtered_{parent_run_id or 'all'}.csv", mime="text/csv",
        use_container_width=True, disabled=export_total == 0,
        key="field10_integrated_history_download_20260702",
    )


def _render_allocation_readiness(daily: pd.DataFrame, summary: pd.DataFrame, main: str) -> None:
    if daily.empty:
        return
    work = daily.copy(deep=False)
    if "Symbol" not in work.columns:
        return
    preferred = [
        "Rank", "Symbol", "Data Quality", "Data Quality Score", "Higher Standard Regime",
        "Higher-Standard Bias", "Less-Risky Bias", "Reliability", "Transition Risk 3H",
        "Current Session", "Session Priority", "Spread Quality", "Uncertainty",
        "Error Percentage", "Trade Permission", "Final Action", "Rank Score", "Rank Grade",
    ]
    cols = [c for c in preferred if c in work.columns]
    view = work.loc[:, cols].copy() if cols else work.copy()
    view.insert(1 if "Rank" in view.columns else 0, "System Role", view["Symbol"].astype(str).map(lambda x: "MAIN" if x == main else "SECONDARY"))
    st.markdown("#### Cross-Symbol Allocation and Entry Readiness")
    _display_field10_table(view, height=min(500, 42 + 35 * max(1, len(view))))

    numeric_candidates = [c for c in ("Rank Score", "Data Quality Score", "Reliability", "Session Priority") if c in work.columns]
    if numeric_candidates:
        chart = work[["Symbol", *numeric_candidates]].copy()
        for column in numeric_candidates:
            chart[column] = pd.to_numeric(chart[column], errors="coerce")
        chart = chart.dropna(how="all", subset=numeric_candidates).set_index("Symbol")
        if not chart.empty:
            st.markdown("##### Cross-Symbol Quality / Reliability Comparison")
            st.bar_chart(chart, use_container_width=True)


_CURRENT_REQUIRED_COLUMNS = [
    "Rank", "Symbol", "Role", "Time", "Broker Date", "Broker Hour", "Timeframe", "Current Session",
    "Technical Bias", "Technical Reliability", "Sentiment Bias", "Sentiment Reliability",
    "Session Bias", "Session Reliability", "Data-Mining Bias", "Higher Standard Regime",
    "Regime Bias", "Regime Probability", "Regime Entropy", "Regime Posterior Margin",
    "Transition Risk 1H", "Transition Risk 3H", "Transition Risk 6H",
    "Transition Risk 24H", "Expected Return 12H (%)", "Expected Return 24H (%)", "Expected Return 36H (%)",
    "Existing Combined Evidence Bias", "Evidence Agreement Percentage", "Conflict Index",
    "Calibrated Reliability", "Drift Status", "Data Quality Grade", "Correlation Cluster",
    "Duplicate Exposure Penalty", "Trade Permission", "Protected Final Action", "Explanation",
    "Publication Status",
]

_QUICKLOOK_COLUMNS = [
    "Time", "Timeframe", "Symbol", "Standard", "Regime", "Regime Bias", "Less-Risky Bias", "Reliability",
    "Calibrated Reliability", "Sample Count", "Regime Probability", "Regime Entropy",
    "Posterior Margin", "Regime Age", "Expected Duration", "Estimated Remaining Duration",
    "Transition Risk 1H", "Transition Risk 3H", "Transition Risk 6H", "Transition Risk 24H",
    "Expected Return 12H (%)", "Expected Return 24H (%)", "Expected Return 36H (%)", "Most Likely Next Regime",
    "Alpha", "Delta", "Delta Acceleration", "Drift Status", "Trade Permission",
    "Data Quality Grade", "Canonical Run ID", "Completed Broker Candle",
]


def _norm_column(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _record_value(record: Mapping[str, Any], *aliases: str) -> Any:
    lookup = {_norm_column(key): key for key in record}
    for alias in aliases:
        key = lookup.get(_norm_column(alias))
        if key is not None:
            value = record.get(key)
            if value not in (None, ""):
                return value
    return None


def _diagnostic_current_row(symbol: str, detail: Mapping[str, Any]) -> pd.DataFrame:
    row = {column: None for column in _CURRENT_REQUIRED_COLUMNS}
    row.update({
        "Symbol": symbol,
        "Explanation": str(detail.get("publication_exception") or detail.get("error") or detail.get("missing_artifact") or "Identity-verified evidence is unavailable."),
        "Publication Status": str(detail.get("status") or "PARTIAL"),
    })
    return pd.DataFrame([row], columns=_CURRENT_REQUIRED_COLUMNS)


def _field3_quicklook(frame: pd.DataFrame, symbol: str, metadata: Mapping[str, Any], quality: str = "UNAVAILABLE") -> pd.DataFrame:
    by_standard: dict[str, Mapping[str, Any]] = {}
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        for record in frame.to_dict("records"):
            standard = str(_record_value(record, "Standard") or "")
            if "lower" in standard.lower():
                by_standard["Lower Standard"] = record
            elif "middle" in standard.lower() or "medium" in standard.lower():
                by_standard["Middle Standard"] = record
            elif "higher" in standard.lower():
                by_standard["Higher Standard"] = record
    rows: list[dict[str, Any]] = []
    for standard in ("Lower Standard", "Middle Standard", "Higher Standard"):
        source = by_standard.get(standard, {})
        rows.append({
            "Time": metadata.get("completed_broker_candle"),
            "Timeframe": metadata.get("timeframe") or st.session_state.get("timeframe"),
            "Symbol": symbol,
            "Standard": standard,
            "Regime": _record_value(source, "Regime", "Major Regime", "Current Regime"),
            "Regime Bias": _record_value(source, "Regime Bias", "Bias"),
            "Less-Risky Bias": _record_value(source, "Less-Risky Bias", "Less Risky Bias", "Safer Bias"),
            "Reliability": _record_value(source, "Reliability", "Trust Score"),
            "Calibrated Reliability": _record_value(source, "Calibrated Reliability"),
            "Sample Count": _record_value(source, "Sample Count", "Samples"),
            "Regime Probability": _record_value(source, "Regime Probability", "Probability"),
            "Regime Entropy": _record_value(source, "Regime Entropy", "Entropy"),
            "Posterior Margin": _record_value(source, "Posterior Margin", "Regime Posterior Margin"),
            "Regime Age": _record_value(source, "Regime Age", "Age"),
            "Expected Duration": _record_value(source, "Expected Duration"),
            "Estimated Remaining Duration": _record_value(source, "Estimated Remaining Duration", "Remaining Duration"),
            "Transition Risk 1H": _record_value(source, "Transition Risk 1H"),
            "Transition Risk 3H": _record_value(source, "Transition Risk 3H"),
            "Transition Risk 6H": _record_value(source, "Transition Risk 6H"),
            "Transition Risk 24H": _record_value(source, "Transition Risk 24H"),
            "Expected Return 12H (%)": _record_value(source, "Expected Return 12H (%)", "Expected Return 12H"),
            "Expected Return 24H (%)": _record_value(source, "Expected Return 24H (%)", "Expected Return 24H"),
            "Expected Return 36H (%)": _record_value(source, "Expected Return 36H (%)", "Expected Return 36H"),
            "Most Likely Next Regime": _record_value(source, "Most Likely Next Regime", "Next Regime"),
            "Alpha": _record_value(source, "Alpha"),
            "Delta": _record_value(source, "Delta"),
            "Delta Acceleration": _record_value(source, "Delta Acceleration"),
            "Drift Status": _record_value(source, "Drift Status"),
            "Trade Permission": _record_value(source, "Trade Permission"),
            "Data Quality Grade": _record_value(source, "Data Quality Grade", "Data Quality") or quality,
            "Canonical Run ID": metadata.get("canonical_run_id"),
            "Completed Broker Candle": metadata.get("completed_broker_candle"),
        })
    return pd.DataFrame(rows, columns=_QUICKLOOK_COLUMNS)


def _field10_symbol_selector(state: MutableMapping[str, Any], parent_run_id: str, main: str, fallback_selected: list[str]) -> str:
    """Read the one global display identity; this surface owns no selector state."""
    from core.global_symbol_context import get_global_symbol_context
    context = get_global_symbol_context(state)
    active = context.active_display_symbol
    st.markdown("#### A. Global Symbol Identity")
    st.caption(
        f"Global Symbol: {active or '—'} · Timeframe: {context.timeframe or '—'} · "
        f"Run: {context.parent_run_id or parent_run_id or '—'} · Generation: {context.generation} · "
        "Selection is controlled only from the floating Global Symbol control."
    )
    return active

def _render_authoritative_field10_contract(
    state: MutableMapping[str, Any], parent_run_id: str, selected: list[str], main: str,
) -> str:
    from core.child_generation_contract_20260702 import load_child_contract_tables, self_heal_field10_from_snapshot
    from core.field10_integrated_evidence_20260702 import load_integrated_current
    from core.multi_symbol_field10_20260701 import DB_PATH
    from core.symbol_context_20260702 import identity_invariants, resolve_symbol_context

    active = _field10_symbol_selector(state, parent_run_id, main, selected)
    context = resolve_symbol_context(state, "Lunch", requested_lunch_symbol=active)
    state["active_snapshot_symbol_20260702"] = active

    current = load_integrated_current(parent_run_id) if parent_run_id else pd.DataFrame()
    if not current.empty and "Symbol" in current.columns:
        current = current.loc[current["Symbol"].astype(str).str.upper() == active]
    heal_report: Mapping[str, Any] = {}
    if current.empty and parent_run_id:
        heal_report = self_heal_field10_from_snapshot(
            path=DB_PATH, parent_run_id=parent_run_id, symbol=active, timeframe=context.timeframe,
            completed_broker_candle=context.completed_broker_candle,
        )
        state["field10_self_heal_report_20260702"] = dict(heal_report)
        if heal_report.get("ok"):
            current = load_integrated_current(parent_run_id)
            if not current.empty and "Symbol" in current.columns:
                current = current.loc[current["Symbol"].astype(str).str.upper() == active]

    st.markdown("#### B. Current Completed H1 Integrated Table")
    if current.empty:
        current_view = _diagnostic_current_row(active, heal_report or {
            "status": "PARTIAL", "missing_artifact": "Field 10 exact integrated current row",
        })
    else:
        for column in _CURRENT_REQUIRED_COLUMNS:
            if column not in current.columns:
                current[column] = None
        current_view = current.loc[:, _CURRENT_REQUIRED_COLUMNS].head(1)
    _display_field10_table(current_view, height=112)
    st.download_button(
        f"⬇ {active} Current Integrated CSV", data=_csv_bytes(current_view),
        file_name=f"field10_{active}_{parent_run_id or 'latest'}_current.csv", mime="text/csv",
        use_container_width=True, key=f"field10_contract_current_download_{active}_20260702",
    )

    contract = load_child_contract_tables(
        path=DB_PATH, parent_run_id=parent_run_id, symbol=active, timeframe=context.timeframe,
    ) if parent_run_id else {"ok": False, "status": "NO_PARENT_RUN"}
    metadata = contract.get("metadata") if isinstance(contract.get("metadata"), Mapping) else {}

    st.markdown("#### C. Field 1 Table 4 History — Last 25 Broker Days")
    table4 = contract.get("table4_history") if isinstance(contract.get("table4_history"), pd.DataFrame) else pd.DataFrame()
    if table4.empty:
        diagnostic = pd.DataFrame([{
            "Symbol": active, "Publication Status": contract.get("status") or heal_report.get("status") or "PARTIAL",
            "Diagnostic": heal_report.get("missing_artifact") or "Saved Table 4 history is unavailable for the exact child identity.",
        }])
        st.dataframe(diagnostic, use_container_width=True, hide_index=True)
    else:
        audit = {
            "Audit Symbol": active, "Audit Timeframe": metadata.get("timeframe"),
            "Parent Run ID": metadata.get("parent_run_id"), "Child Run ID": metadata.get("child_run_id"),
            "Canonical Run ID": metadata.get("canonical_run_id"), "Snapshot Hash": metadata.get("snapshot_hash"),
        }
        for column, value in reversed(list(audit.items())):
            if column not in table4.columns:
                table4.insert(0, column, value)
        tc = next((c for c in table4.columns if "time" in _norm_column(c)), None)
        if tc:
            table4 = table4.assign(_sort_time=pd.to_datetime(table4[tc], errors="coerce", utc=True)).sort_values("_sort_time", ascending=False).drop(columns="_sort_time")
        query = st.text_input("Search Table 4 history", key=f"field10_table4_search_{active}_20260702")
        view4 = _search(table4, query)
        st.caption(f"{len(view4):,} displayed rows · {len(table4):,} identity-verified saved rows · completed broker candles only.")
        st.dataframe(view4, use_container_width=True, hide_index=True, height=520)
        st.download_button(
            f"⬇ {active} Table 4 History CSV", data=_csv_bytes(view4),
            file_name=f"field10_{active}_table4_last25d.csv", mime="text/csv", use_container_width=True,
            key=f"field10_table4_download_{active}_20260702",
        )

    st.markdown("#### D. Field 3 Three-Standard Quick-Look Table")
    quick = _field3_quicklook(
        contract.get("field3_current") if isinstance(contract.get("field3_current"), pd.DataFrame) else pd.DataFrame(),
        active, metadata, str((current_view.iloc[0].get("Data Quality Grade") if not current_view.empty else None) or "UNAVAILABLE"),
    )
    _display_field10_table(quick, height=165)

    st.markdown("#### E. 25-Day Regime History")
    with st.expander(f"Open / Close — {active} Lower, Middle and Higher saved regime history", expanded=False):
        history3 = contract.get("field3_history") if isinstance(contract.get("field3_history"), pd.DataFrame) else pd.DataFrame()
        if history3.empty:
            st.info("No identity-verified saved Field 3 history rows are available for this child generation.")
        else:
            query3 = st.text_input("Search regime history", key=f"field10_field3_history_search_{active}_20260702")
            st.dataframe(_search(history3, query3), use_container_width=True, hide_index=True, height=520)

    st.markdown("#### F. Current Identity and Publication Diagnostics")
    diagnostics = {
        "Settings Main Symbol": context.settings_main_symbol,
        "Lunch Display Symbol": active,
        "Active Snapshot Symbol": state.get("active_snapshot_symbol_20260702"),
        "Connector Symbol": context.connector_symbol,
        "Parent Run ID": metadata.get("parent_run_id") or context.parent_run_id,
        "Child Run ID": metadata.get("child_run_id") or context.child_run_id,
        "Canonical Run ID": metadata.get("canonical_run_id") or context.canonical_run_id,
        "Source ID": metadata.get("source_id") or context.source_id,
        "Snapshot Hash": metadata.get("snapshot_hash") or context.snapshot_hash,
        "Completed Broker Candle": metadata.get("completed_broker_candle") or context.completed_broker_candle,
        "Valid Until": metadata.get("valid_until") or context.valid_until,
        "Publication Status": metadata.get("publication_status") or heal_report.get("status") or contract.get("status"),
        "Snapshot Status": "VERIFIED" if contract.get("ok") else "UNAVAILABLE",
        "Data Quality": current_view.iloc[0].get("Data Quality Grade") if not current_view.empty else "UNAVAILABLE",
    }
    st.dataframe(pd.DataFrame([diagnostics]), use_container_width=True, hide_index=True)
    invariant = identity_invariants(state, "Lunch")
    state["lunch_identity_invariant_20260702"] = invariant
    if not invariant.get("ok"):
        st.error("Lunch identity mismatch detected. No market row was copied across symbols.")
        st.json(invariant)
    stored_diag = contract.get("diagnostics") if isinstance(contract.get("diagnostics"), pd.DataFrame) else pd.DataFrame()
    if not stored_diag.empty:
        with st.expander("Open / Close — Publication transaction diagnostics", expanded=False):
            st.dataframe(stored_diag, use_container_width=True, hide_index=True)
    return active



def _render_finnhub_sentiment_rank(metadata: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    """Render persisted authenticated Finnhub evidence only; never fetch or migrate in Lunch."""
    from core.field10_finnhub_sentiment_20260704 import load_finnhub_sentiment_rank

    snapshot_id = str(metadata.get("daily_snapshot_id") or "")
    with st.expander(
        "Open / Close — Multi-Symbol Sentiment, High-Impact News and Absorption Rank",
        expanded=False,
    ):
        stored_migration = state.get("field10_unified_migration_report_20260703")
        migration = dict(stored_migration) if isinstance(stored_migration, Mapping) else {
            "status": "NOT_PERSISTED_IN_SESSION",
            "finnhub_news_schema_verified": False,
            "prohibited_rank_tables": [],
            "secret_column_issues": {},
        }
        status_cols = st.columns(4)
        status_cols[0].metric("Database Migration", str(migration.get("status") or "UNKNOWN"))
        status_cols[1].metric("Finnhub News Schema", "VERIFIED" if migration.get("finnhub_news_schema_verified") else "UNAVAILABLE")
        status_cols[2].metric("Duplicate Main Rank Table", "NO" if not migration.get("prohibited_rank_tables") else "YES")
        status_cols[3].metric("Secret Columns", "NONE" if not migration.get("secret_column_issues") else "FOUND")
        st.caption(
            "This table reads persisted rows created during the Settings calculation from the authenticated Finnhub connector. "
            "Opening this expander does not call Finnhub, refit sentiment, or change the locked daily rank. "
            "Actual/consensus/surprise and event-study fields remain UNAVAILABLE when Finnhub does not provide them."
        )
        frame = load_finnhub_sentiment_rank(daily_snapshot_id=snapshot_id or None, limit=1000)
        if frame.empty:
            st.info(
                "No authenticated Finnhub sentiment rows are persisted for this daily snapshot. "
                "Configure/connect the Finnhub API key in Settings, then run the existing calculation once. "
                "The system does not substitute RSS or fabricated event values in this Field 10 table."
            )
            return
        query = st.text_input(
            "Search Finnhub multi-symbol sentiment rank",
            key="field10_finnhub_sentiment_search_20260704",
            placeholder="symbol, currency, headline, BUY, SELL, BLOCK, absorbed…",
        )
        view = _search(frame, query)
        provider_rows = int(view.get("Data Provider", pd.Series(dtype=object)).astype(str).str.upper().eq("FINNHUB").sum())
        auth_rows = int(view.get("Provider Authentication", pd.Series(dtype=object)).astype(str).str.upper().eq("FINNHUB_AUTHENTICATED_API").sum())
        metrics = st.columns(5)
        metrics[0].metric("Displayed Rows", len(view))
        metrics[1].metric("Finnhub Rows", provider_rows)
        metrics[2].metric("Authenticated Rows", auth_rows)
        metrics[3].metric("Blocked Events", int(view.get("Event-Risk Permission", pd.Series(dtype=object)).astype(str).str.upper().eq("BLOCK").sum()))
        metrics[4].metric("Symbols Covered", int(view.get("Symbol", pd.Series(dtype=object)).nunique()))
        _display_field10_table(view, height=min(680, 54 + 35 * max(1, min(len(view), 18))))
        st.download_button(
            "⬇ Finnhub Sentiment / News / Absorption CSV",
            data=_csv_bytes(frame),
            file_name=f"field10_finnhub_sentiment_{metadata.get('broker_day') or 'latest'}.csv",
            mime="text/csv",
            use_container_width=True,
            key="field10_finnhub_sentiment_download_20260704",
        )


def _crowd_state_icon(state: Any) -> str:
    text = str(state or "INSUFFICIENT_EVIDENCE").upper()
    if text in {"STRONG_BULLISH_CROWD", "BULLISH_CROWD", "MILD_BULLISH_CROWD"}:
        return "▲"
    if text in {"STRONG_BEARISH_CROWD", "BEARISH_CROWD", "MILD_BEARISH_CROWD"}:
        return "▼"
    if text.startswith("FOMO"):
        return "⚠ FOMO"
    if text.startswith("PANIC"):
        return "⛔ PANIC"
    if text == "CROWD_EXHAUSTION":
        return "⚠ EXHAUSTION"
    if text == "CONTRARIAN_REVERSAL_RISK":
        return "↶ CONTRARIAN"
    if text == "BALANCED":
        return "◆"
    if text == "MIXED_OR_CONFLICTED":
        return "↔"
    return "?"


def _crowd_row_styler(frame: pd.DataFrame):
    """Full-row crowd state styling with state text/icons retained."""
    if frame.empty:
        return frame
    view = frame.copy()
    if "Crowd State" in view.columns:
        view["Crowd State"] = view["Crowd State"].map(
            lambda value: f"{_crowd_state_icon(value)} {str(value or 'INSUFFICIENT_EVIDENCE')}"
        )

    def style_row(row: pd.Series) -> list[str]:
        state = str(row.get("Crowd State") or "").upper()
        css = "background-color:#eceff1;color:#263238"
        if "STRONG_BULLISH" in state:
            css = "background-color:#14532d;color:#ffffff;font-weight:700"
        elif "BULLISH" in state:
            css = "background-color:#bbf7d0;color:#14532d;font-weight:650"
        elif "STRONG_BEARISH" in state:
            css = "background-color:#7f1d1d;color:#ffffff;font-weight:700"
        elif "BEARISH" in state:
            css = "background-color:#fecaca;color:#7f1d1d;font-weight:650"
        elif "PANIC" in state:
            css = "background-color:#b91c1c;color:#ffffff;font-weight:750"
        elif "FOMO" in state:
            css = "background-color:#fcd34d;color:#422006;font-weight:700"
        elif "EXHAUSTION" in state:
            css = "background-color:#ddd6fe;color:#4c1d95;font-weight:700"
        elif "CONTRARIAN" in state:
            css = "background-color:#fed7aa;color:#7c2d12;font-weight:700"
        elif "BALANCED" in state:
            css = "background-color:#e5e7eb;color:#1f2937"
        elif "MIXED" in state:
            css = "background-color:#fef3c7;color:#78350f"
        return [css] * len(row)

    return view.style.apply(style_row, axis=1)


def _final_row_styler(frame: pd.DataFrame):
    """Full-row top-four and safety styling; labels remain visible for accessibility."""
    if frame.empty:
        return frame

    def style_row(row: pd.Series) -> list[str]:
        bias = str(row.get("Final Less-Risky Bias to Hold") or "").upper()
        entry = str(row.get("Final Entry Permission") or "").upper()
        hold = str(row.get("Final Hold Permission") or "").upper()
        warning = str(row.get("Final Exit/Risk Warning") or "").upper()
        rank = pd.to_numeric(pd.Series([row.get("Final Rank")]), errors="coerce").iloc[0]
        css = "background-color:#eceff1;color:#263238"
        if "EXIT_OR_REDUCE" in bias or "EXIT_OR_REDUCE" in warning or hold == "EXIT_OR_REDUCE":
            css = "background-color:#e9d5ff;color:#581c87;font-weight:750"
        elif "BLOCK" in bias or entry == "BLOCK" or hold == "BLOCK":
            css = "background-color:#fecaca;color:#7f1d1d;font-weight:750"
        elif "CAUTION" in bias or entry == "CAUTION" or hold == "CAUTION":
            css = "background-color:#fde68a;color:#713f12;font-weight:700"
        elif bias == "WAIT":
            css = "background-color:#e5e7eb;color:#1f2937"
        elif bias == "INSUFFICIENT_EVIDENCE":
            css = "background-color:#d1d5db;color:#374151"
        elif pd.notna(rank) and int(rank) == 1:
            css = "background-color:#166534;color:#ffffff;font-weight:750"
        elif pd.notna(rank) and int(rank) == 2:
            css = "background-color:#bbf7d0;color:#14532d;font-weight:700"
        elif pd.notna(rank) and int(rank) == 3:
            css = "background-color:#fcd34d;color:#422006;font-weight:700"
        elif pd.notna(rank) and int(rank) == 4:
            css = "background-color:#bfdbfe;color:#1e3a8a;font-weight:700"
        return [css] * len(row)

    return frame.style.apply(style_row, axis=1)


def _render_session_entry_map(metadata: Mapping[str, Any]) -> None:
    """Read the persisted eight-session child table; never calculate in Lunch."""
    from core.field10_crowd_final_20260704 import load_session_entry_map

    snapshot_id = str(metadata.get("daily_snapshot_id") or "")
    with st.expander("Open / Close — Eight-Session Multi-Symbol Entry Map", expanded=False):
        st.caption(
            "Persisted child evidence from the same locked Field 10 daily snapshot. "
            "Opening this section performs a read-only SQLite query and does not access an API or rebuild H1 features."
        )
        frame = load_session_entry_map(daily_snapshot_id=snapshot_id or None)
        if frame.empty:
            st.info("No persisted eight-session map exists for this daily snapshot. Run the Settings calculation once.")
            return
        query = st.text_input(
            "Search eight-session entry map",
            key="field10_session_entry_map_search_20260704",
            placeholder="symbol, session, BUY, SELL, ALLOW, CAUTION…",
        )
        view = _search(frame, query)
        cols = st.columns(4)
        cols[0].metric("Rows", len(view))
        cols[1].metric("Symbols", int(view.get("Symbol", pd.Series(dtype=object)).nunique()))
        cols[2].metric("Sessions", int(view.get("Session", pd.Series(dtype=object)).nunique()))
        cols[3].metric("Entry Allowed", int(view.get("Entry Permission", pd.Series(dtype=object)).astype(str).str.upper().eq("ALLOW").sum()))
        _display_field10_table(view, height=min(640, 54 + 35 * max(1, min(len(view), 16))))
        st.download_button(
            "⬇ Eight-Session Entry Map CSV", data=_csv_bytes(frame),
            file_name=f"field10_eight_session_map_{metadata.get('broker_day') or 'latest'}.csv",
            mime="text/csv", use_container_width=True, key="field10_session_map_download_20260704",
        )


def _render_crowd_psychology_rank(metadata: Mapping[str, Any]) -> None:
    """Read the persisted crowd-psychology table; optional evidence remains explicit."""
    from core.field10_crowd_final_20260704 import load_crowd_psychology_rank

    snapshot_id = str(metadata.get("daily_snapshot_id") or "")
    with st.expander("Open / Close — Multi-Symbol Crowd Psychology Ranking", expanded=False):
        st.caption(
            "Shadow-only behavioral state derived from the same 600 completed H1 candles, persisted news/absorption, "
            "cross-symbol currency legs, volatility, activity and candle-pressure proxies. News is one component only. "
            "Retail positioning, social sentiment and true institutional order flow display UNAVAILABLE unless genuine data exists."
        )
        frame = load_crowd_psychology_rank(daily_snapshot_id=snapshot_id or None)
        if frame.empty:
            st.info("No crowd-psychology child rows are persisted for this daily snapshot. Run the Settings calculation once.")
            return
        for column in ("True Flow Data Available", "Positioning Data Available"):
            if column in frame.columns:
                frame[column] = frame[column].map(lambda value: "AVAILABLE" if bool(value) else "UNAVAILABLE")
        query = st.text_input(
            "Search crowd psychology rank",
            key="field10_crowd_psychology_search_20260704",
            placeholder="symbol, crowd state, FOMO, panic, contrarian, BUY, SELL…",
        )
        view = _search(frame, query)
        cols = st.columns(5)
        cols[0].metric("Rows", len(view))
        cols[1].metric("Symbols", int(view.get("Symbol", pd.Series(dtype=object)).nunique()))
        cols[2].metric("Caution/Block", int(view.get("Crowd Entry Permission", pd.Series(dtype=object)).astype(str).str.upper().isin({"CAUTION", "BLOCK"}).sum()))
        cols[3].metric("Contrarian Warnings", int(view.get("Crowd Reversal Warning", pd.Series(dtype=object)).astype(str).str.upper().eq("ACTIVE").sum()))
        cols[4].metric("Model Status", "SHADOW ONLY")
        view = _ensure_time_columns(view, st.session_state)
        st.dataframe(
            _crowd_row_styler(view), use_container_width=True, hide_index=True,
            height=min(720, 54 + 35 * max(1, min(len(view), 18))),
        )
        st.download_button(
            "⬇ Crowd Psychology Ranking CSV", data=_csv_bytes(frame),
            file_name=f"field10_crowd_psychology_{metadata.get('broker_day') or 'latest'}.csv",
            mime="text/csv", use_container_width=True, key="field10_crowd_psychology_download_20260704",
        )


def _render_final_multi_symbol_rank(metadata: Mapping[str, Any]) -> None:
    """Read the four-source persisted final synthesis; live safety only downgrades permissions."""
    from core.field10_crowd_final_20260704 import load_final_multi_symbol_rank

    snapshot_id = str(metadata.get("daily_snapshot_id") or "")
    with st.expander("Open / Close — Part 2: Legacy Four-Source Fusion Candidate", expanded=False):
        st.caption(
            "Visible synthesis of four persisted sources: whole-day technical/fundamental rank, eight-session map, "
            "Finnhub news/absorption rank and crowd psychology. Percentage-return units are used consistently. "
            "Bias-to-hold is not automatic entry permission. Live safety may downgrade permissions without reranking or rewriting the locked bias."
        )
        frame = load_final_multi_symbol_rank(daily_snapshot_id=snapshot_id or None, apply_live_safety=True)
        if frame.empty:
            st.info("No final multi-symbol child rows are persisted for this daily snapshot. Run the Settings calculation once.")
            return
        frame = frame.copy()
        if "Final Rank" not in frame.columns:
            source = next((column for column in ("Rank", "Daily Rank") if column in frame.columns), None)
            frame["Final Rank"] = frame[source] if source else pd.NA
        for column in LEGACY_FUSION_COLUMNS:
            if column not in frame.columns:
                frame[column] = pd.NA
        preferred = [column for column in LEGACY_FUSION_COLUMNS if column in frame.columns]
        frame = frame.loc[:, preferred + [column for column in frame.columns if column not in preferred]]
        query = st.text_input(
            "Search final multi-symbol ranking",
            key="field10_final_multi_symbol_search_20260704",
            placeholder="symbol, HOLD_BUY, CAUTION, BLOCK, session, source, reason…",
        )
        view = _search(frame, query)
        cols = st.columns(5)
        cols[0].metric("Ranked Symbols", int(pd.to_numeric(view.get("Final Rank", pd.Series(dtype=float)), errors="coerce").notna().sum()))
        cols[1].metric("Hold Biases", int(view.get("Final Less-Risky Bias to Hold", pd.Series(dtype=object)).astype(str).str.startswith("HOLD_").sum()))
        cols[2].metric("Caution", int(view.get("Final Entry Permission", pd.Series(dtype=object)).astype(str).str.upper().eq("CAUTION").sum()))
        cols[3].metric("Blocked", int(view.get("Final Entry Permission", pd.Series(dtype=object)).astype(str).str.upper().eq("BLOCK").sum()))
        cols[4].metric("Model Status", "VISIBLE FUSION")
        view = _ensure_time_columns(view, st.session_state)
        st.dataframe(
            _final_row_styler(view), use_container_width=True, hide_index=True,
            height=min(740, 54 + 35 * max(1, min(len(view), 18))),
        )
        st.download_button(
            "⬇ Final Multi-Symbol Ranking CSV", data=_csv_bytes(frame),
            file_name=f"field10_final_multi_symbol_{metadata.get('broker_day') or 'latest'}.csv",
            mime="text/csv", use_container_width=True, key="field10_final_multi_symbol_download_20260704",
        )


def _percent(value: Any) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(number) else float(number) * 100.0


def _merge_institutional_shadow(current: pd.DataFrame, metadata: Mapping[str, Any]) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Join read-only child evidence by exact snapshot/symbol; never rerank."""
    from core.field10_institutional_shadow_20260704 import load_shadow_evidence

    evidence = load_shadow_evidence(daily_snapshot_id=str(metadata.get("daily_snapshot_id") or "") or None)
    view = current.copy()
    if view.empty or "Symbol" not in view.columns:
        return view, evidence
    if "Final Rank" not in view.columns:
        source = next((c for c in ("Daily Rank", "Rank") if c in view.columns), None)
        view.insert(0, "Final Rank", view[source] if source else pd.NA)
    if "Final Less-Risky Bias" not in view.columns:
        view["Final Less-Risky Bias"] = view.get("Less-Risky Bias", pd.Series(pd.NA, index=view.index))
    if "Final Score" not in view.columns:
        view["Final Score"] = view.get("Institutional Morning Score", view.get("Comparative Rank Score", pd.Series(pd.NA, index=view.index)))

    reliability = evidence.get("reliability", pd.DataFrame())
    if not reliability.empty:
        rel = reliability[["symbol", "aggregate_reliability", "reliability_status", "principal_reliability_weakness"]].copy()
        rel["Calibrated Reliability"] = pd.to_numeric(rel["aggregate_reliability"], errors="coerce") * 100.0
        rel = rel.rename(columns={"symbol": "Symbol", "reliability_status": "Reliability Status", "principal_reliability_weakness": "Principal Reliability Weakness"})
        view = view.merge(rel[["Symbol", "Calibrated Reliability", "Reliability Status", "Principal Reliability Weakness"]], on="Symbol", how="left")
    rank = evidence.get("rank_confidence", pd.DataFrame())
    if not rank.empty:
        rank = rank[["symbol", "probability_rank_le_4", "probability_rank_1", "median_rank", "rank_instability", "score_gap_to_next_symbol", "validation_status"]].copy()
        rank["Rank Confidence"] = pd.to_numeric(rank["probability_rank_le_4"], errors="coerce") * 100.0
        rank["Probability Rank = 1"] = pd.to_numeric(rank["probability_rank_1"], errors="coerce") * 100.0
        rank = rank.rename(columns={"symbol": "Symbol", "median_rank": "Median Bootstrap Rank", "rank_instability": "Rank Instability", "score_gap_to_next_symbol": "Score Gap to Next Symbol", "validation_status": "Rank Confidence Status"})
        view = view.merge(rank[["Symbol", "Rank Confidence", "Probability Rank = 1", "Median Bootstrap Rank", "Rank Instability", "Score Gap to Next Symbol", "Rank Confidence Status"]], on="Symbol", how="left")
    regime = evidence.get("regime", pd.DataFrame())
    if not regime.empty:
        reg = regime[["symbol", "transition_probability_1h", "transition_probability_6h", "transition_probability_12h", "transition_probability_24h", "selected_regime_probability", "regime_entropy", "validation_status"]].copy()
        for h in (1, 6, 12, 24):
            reg[f"Transition Risk {h}H"] = pd.to_numeric(reg[f"transition_probability_{h}h"], errors="coerce") * 100.0
        reg = reg.rename(columns={"symbol": "Symbol", "selected_regime_probability": "Supporting Regime Probability", "regime_entropy": "Supporting Regime Entropy", "validation_status": "Regime Evidence Status"})
        keep = ["Symbol", "Transition Risk 1H", "Transition Risk 6H", "Transition Risk 12H", "Transition Risk 24H", "Supporting Regime Probability", "Supporting Regime Entropy", "Regime Evidence Status"]
        view = view.merge(reg[keep], on="Symbol", how="left", suffixes=("", " Shadow"))
        for col in ("Transition Risk 1H", "Transition Risk 6H", "Transition Risk 12H", "Transition Risk 24H"):
            shadow = col + " Shadow"
            if shadow in view.columns:
                if col not in view.columns: view[col] = view[shadow]
                else: view[col] = pd.to_numeric(view[col], errors="coerce").fillna(pd.to_numeric(view[shadow], errors="coerce"))
                view.drop(columns=[shadow], inplace=True)
    forecasts = evidence.get("forecast", pd.DataFrame())
    if not forecasts.empty:
        pivot = forecasts.pivot_table(index="symbol", columns="horizon_hours", values="net_expected_value", aggfunc="first")
        pivot = pivot.rename(columns={h: f"Net EV {h}H" for h in pivot.columns}).reset_index().rename(columns={"symbol": "Symbol"})
        for c in [x for x in pivot.columns if x.startswith("Net EV")]:
            pivot[c] = pd.to_numeric(pivot[c], errors="coerce") * 100.0
        view = view.merge(pivot, on="Symbol", how="left")
    breaks = evidence.get("break", pd.DataFrame())
    if not breaks.empty:
        br = breaks[["symbol", "structural_break_strength", "post_break_h1_count", "post_break_validation_permission", "validation_status"]].copy()
        br["Structural-Break Status"] = br["post_break_validation_permission"].fillna(br["validation_status"])
        br = br.rename(columns={"symbol": "Symbol", "structural_break_strength": "Structural-Break Strength", "post_break_h1_count": "Post-Break H1 Count"})
        view = view.merge(br[["Symbol", "Structural-Break Status", "Structural-Break Strength", "Post-Break H1 Count"]], on="Symbol", how="left")
    if "Unexpected-Situation Status" not in view.columns:
        view["Unexpected-Situation Status"] = view.get("Unexpected Situation Status", pd.Series(pd.NA, index=view.index))

    # Preserve the requested decision-critical probability column even when the
    # new shadow candidate has not yet produced persisted evidence. The value
    # remains parent-owned and is never fabricated.
    if "Calibrated Bias Probability" in view.columns and "Calibrated Probability" not in view.columns:
        view["Calibrated Probability"] = view["Calibrated Bias Probability"]
    if "Calibrated Probability" not in view.columns:
        view["Calibrated Probability"] = pd.NA

    # Read-only 20260705 shadow summary. It contributes safety/validation columns
    # only; Final Rank and Final Less-Risky Bias remain parent-owned.
    try:
        from core.field10_research_readonly_20260705 import load_candidate_summary
        from core.multi_symbol_field10_20260701 import DB_PATH as FIELD10_DB_PATH
        candidate = load_candidate_summary(str(metadata.get("daily_snapshot_id") or "") or None, path=FIELD10_DB_PATH)
    except Exception:
        candidate = pd.DataFrame()
    evidence["horizon_connected_tail_summary"] = candidate
    if not candidate.empty:
        cand = candidate[[
            "symbol", "entry_permission", "managed_utility_6h", "managed_utility_12h",
            "expected_shortfall_95", "transition_risk_6h", "bad_connectedness",
            "persistent_connectedness", "volatility_safety", "mcs_status",
            "split_robustness", "reliability", "data_quality", "promotion_status",
        ]].copy()
        cand = cand.rename(columns={
            "symbol": "Symbol", "entry_permission": "Research Entry Permission",
            "managed_utility_6h": "Managed Utility 6H", "managed_utility_12h": "Managed Utility 12H",
            "expected_shortfall_95": "Expected Shortfall 95%",
            "transition_risk_6h": "Research Transition Risk 6H",
            "bad_connectedness": "Bad Connectedness",
            "persistent_connectedness": "Persistent Connectedness",
            "volatility_safety": "Volatility Safety", "mcs_status": "MCS Status",
            "split_robustness": "Split Robustness", "reliability": "Research Reliability",
            "data_quality": "Data Quality", "promotion_status": "Research Promotion Status",
        })
        cand["Volatility Safety"] = pd.to_numeric(cand["Volatility Safety"], errors="coerce") * 100.0
        view = view.merge(cand, on="Symbol", how="left")
        if "Reliability" not in view.columns:
            view["Reliability"] = view.get("Calibrated Reliability", view.get("Research Reliability", pd.Series(pd.NA, index=view.index)))
        else:
            view["Reliability"] = pd.to_numeric(view["Reliability"], errors="coerce").fillna(pd.to_numeric(view.get("Research Reliability"), errors="coerce"))
        if "Transition Risk 6H" not in view.columns:
            view["Transition Risk 6H"] = view["Research Transition Risk 6H"]
        else:
            view["Transition Risk 6H"] = pd.to_numeric(view["Transition Risk 6H"], errors="coerce").fillna(pd.to_numeric(view["Research Transition Risk 6H"], errors="coerce"))
    # Parent rank remains the only ordering authority.
    view = view.sort_values(["Final Rank", "Symbol"], na_position="last", kind="mergesort").reset_index(drop=True)
    return view, evidence


def _render_technical_fundamental_parent(view: pd.DataFrame) -> None:
    with st.expander("Open / Close — Technical / Fundamental Ranking (same locked parent)", expanded=False):
        st.caption("This is a column-focused view of the authoritative locked parent, not a second ranking table.")
        columns = [c for c in (
            "Final Rank", "Symbol", "Final Less-Risky Bias", "Entry Permission", "Final Score",
            "Higher Standard Regime", "Stable Daily Bias", "Technical Bias", "Technical Reliability",
            "Sentiment Bias", "Sentiment Reliability", "Session Bias", "Session Reliability",
            "Expected Return 12H (%)", "Expected Return 24H (%)", "CVaR 95%", "Data Quality Grade",
        ) if c in view.columns]
        _display_field10_table(view[columns] if columns else view, height=min(560, 54 + 35 * max(1, len(view))), pin_expected_returns=True, key="field10_parent_technical_fundamental_20260704")


def _render_institutional_validation(evidence: Mapping[str, pd.DataFrame], metadata: Mapping[str, Any]) -> None:
    with st.expander("Open / Close — Validation, Reliability and Candidate Evidence", expanded=False):
        st.caption("Validation evidence is read-only and does not replace or rerank the locked parent publication.")
        order = ("reliability", "calibration", "conformal", "regime", "break", "dependence", "rank_confidence", "outcomes")
        labels = {
            "reliability": "Reliability Components", "calibration": "Purged OOS Calibration", "conformal": "Marginal Conformal Coverage",
            "regime": "Hamilton Supporting Evidence", "break": "Structural Break / Changepoint", "dependence": "Ledoit–Wolf Dependence",
            "rank_confidence": "Bootstrap Rank Confidence", "outcomes": "Immutable Settled Outcomes",
        }
        for name in order:
            frame = evidence.get(name, pd.DataFrame())
            st.markdown(f"##### {labels[name]}")
            if not isinstance(frame, pd.DataFrame) or frame.empty:
                st.info("No persisted evidence is available for this snapshot.")
            else:
                st.dataframe(frame, use_container_width=True, hide_index=True, height=min(420, 54 + 31 * max(1, min(len(frame), 11))))
        st.markdown("##### Horizon / Tail / Connectedness Candidate")
        candidate_summary = evidence.get("horizon_connected_tail_summary", pd.DataFrame())
        if not isinstance(candidate_summary, pd.DataFrame) or candidate_summary.empty:
            st.info("No persisted 20260705 candidate evidence is available for this snapshot.")
        else:
            st.dataframe(candidate_summary, use_container_width=True, hide_index=True, height=min(420, 54 + 31 * max(1, min(len(candidate_summary), 11))))
            load_research = st.checkbox(
                "Load detailed HAR-H1, semivariance, GAS, VaR/ES, copula, connectedness, MCS and sample-split rows",
                value=False, key="field10_load_horizon_tail_details_20260705",
            )
            if load_research:
                try:
                    from core.field10_research_readonly_20260705 import load_candidate_details
                    from core.multi_symbol_field10_20260701 import DB_PATH as FIELD10_DB_PATH
                    detail_tables = load_candidate_details(str(metadata.get("daily_snapshot_id") or ""), path=FIELD10_DB_PATH)
                except Exception as exc:
                    detail_tables = {}
                    st.error(f"Candidate detail read failed: {type(exc).__name__}: {exc}")
                for table_name, detail in detail_tables.items():
                    st.markdown(f"###### {table_name}")
                    if detail.empty:
                        st.info("No persisted rows.")
                    else:
                        st.dataframe(detail, use_container_width=True, hide_index=True, height=min(420, 54 + 31 * max(1, min(len(detail), 11))))
        st.caption(f"Snapshot identity: {metadata.get('daily_snapshot_id')} · completed H1: {metadata.get('latest_completed_h1')}")


def _render_formula_dictionary() -> None:
    with st.expander("Open / Close — Formula and Data Dictionary", expanded=False):
        rows = [
            {"Field": "Final Rank", "Definition": "Immutable parent rank stored at morning publication; never recalculated during display.", "Unit": "ordinal"},
            {"Field": "Net EV h", "Definition": "P(gain)×E(MFE|gain) − P(loss)×E(|MAE||loss) − verified spread/slippage costs; NULL when costs are absent.", "Unit": "% return"},
            {"Field": "Calibrated Reliability", "Definition": "Weighted geometric mean of persisted reliability components; critically weak components strongly penalize the aggregate.", "Unit": "%"},
            {"Field": "Rank Confidence", "Definition": "Block-bootstrap probability that the symbol remains rank ≤4 under shadow utility uncertainty; parent rank is unchanged.", "Unit": "%"},
            {"Field": "Transition Risk h", "Definition": "Supporting Hamilton-style probability of leaving the current regime within h hours, synchronized to Field 3 identity.", "Unit": "%"},
            {"Field": "Conformal Interval", "Definition": "Purged split-conformal marginal return interval; no claim of guaranteed conditional coverage.", "Unit": "return"},
            {"Field": "Structural-Break Status", "Definition": "Shadow Bai–Perron-style split evidence plus online changepoint warning; may block new entry but never rewrites direction.", "Unit": "status"},
            {"Field": "Source Hash", "Definition": "Exact publication/source identity hash. Missing identity blocks shadow calculation instead of borrowing another symbol.", "Unit": "SHA-256/text"},
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("Versioned formulas and thresholds are documented in FIELD10_FORMULA_AND_THRESHOLD_REGISTRY.md in the deployment package.")


def _render_locked_morning_snapshot(state: Mapping[str, Any] | None = None, selected: Sequence[str] | None = None) -> None:
    """Render the authoritative persisted daily contract without calculations."""
    from core.field10_daily_snapshot_contract_20260702 import (
        load_current_daily_snapshot, load_daily_history, validate_persisted_snapshot,
    )

    state = state if state is not None else st.session_state
    manifest = state.get(MANIFEST_KEY) if isinstance(state.get(MANIFEST_KEY), Mapping) else {}
    selected = normalize_selected(selected or manifest.get("selected_symbols") or state.get(SELECTED_KEY) or [])
    st.markdown("### Today First — Ranked Multi-Symbol Decision Table")
    st.caption("1. Final Multi-Symbol Ranking — Authoritative Locked Parent")
    bundle = load_current_daily_snapshot()
    metadata = bundle.get("metadata") or {}
    current = bundle.get("current")
    has_immutable_snapshot = isinstance(current, pd.DataFrame) and not current.empty
    integrity = (
        validate_persisted_snapshot(broker_day=str(metadata.get("broker_day") or ""))
        if has_immutable_snapshot else {"ok": True, "status": "LOCAL_RECOVERY_VIEW"}
    )
    if has_immutable_snapshot and not integrity.get("ok"):
        st.error("The persisted morning snapshot failed checksum validation. Trading ranks are not trusted.")
    overlay_report: Mapping[str, Any] = {}
    try:
        from core.system_continuous_validation_20260702 import build_field10_display_overlay
        current, overlay_report = build_field10_display_overlay(
            current if isinstance(current, pd.DataFrame) else pd.DataFrame(),
            selected_symbols=selected,
        )
    except Exception as exc:
        current = current if isinstance(current, pd.DataFrame) else pd.DataFrame()
        overlay_report = {"ok": False, "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
    if current.empty:
        st.info(
            "No authoritative morning snapshot or readable local symbol cache is available. "
            "Run the Settings multi-symbol calculation; Field 10 will preserve every valid unaffected symbol result."
        )
        return
    if not has_immutable_snapshot:
        metadata = {
            **metadata,
            "publication_status": "LOCAL_RECOVERY_VIEW_NOT_LOCKED",
            "broker_day": "UNAVAILABLE_NOT_LOCKED",
            "cutoff_broker_time": "Not locked",
        }
        st.warning(
            "The immutable morning lock is not available, so this table uses each selected symbol's saved local H1 child snapshot. "
            "It is ranked and complete for review, but it is not labelled as the locked production publication."
        )
    if int(overlay_report.get("repaired_rows") or 0) > 0:
        st.info(
            f"Adaptive display repair filled unavailable or over-restrictive evidence for "
            f"{overlay_report.get('repaired_rows')} symbol row(s). Stored publication values remain available in audit columns; the immutable database was not changed."
        )
    current, institutional_evidence = _merge_institutional_shadow(current, metadata)
    candidate_summary = institutional_evidence.get("horizon_connected_tail_summary", pd.DataFrame())
    if isinstance(candidate_summary, pd.DataFrame) and not candidate_summary.empty:
        st.caption("Additional safety and validation evidence is available. Final Rank and the locked whole-day bias are unchanged.")
    rank_column = "Final Rank" if "Final Rank" in current.columns else "Rank"
    eligible = current.loc[pd.to_numeric(current[rank_column], errors="coerce").notna()].copy()
    best = eligible.sort_values([rank_column, "Symbol"], kind="mergesort").iloc[0] if not eligible.empty else current.iloc[0]
    try:
        locked_until = pd.Timestamp(metadata.get("locked_until_broker_time"))
        created_at = pd.Timestamp(metadata.get("created_at_broker_time"))
        remaining_hours = max(0.0, (locked_until - created_at).total_seconds() / 3600.0)
        remaining_text = f"{remaining_hours:.1f}h at publish"
    except Exception:
        remaining_text = "Not locked"

    score_value = best.get("Institutional Morning Score")
    if pd.isna(pd.to_numeric(pd.Series([score_value]), errors="coerce").iloc[0]):
        score_value = best.get("Comparative Rank Score")
    transition_6h = best.get("Transition Risk 6H")
    if pd.isna(pd.to_numeric(pd.Series([transition_6h]), errors="coerce").iloc[0]):
        transition_6h = best.get("Transition Probability 6H")
    transition_24h = best.get("Transition Risk 24H")
    if pd.isna(pd.to_numeric(pd.Series([transition_24h]), errors="coerce").iloc[0]):
        transition_24h = best.get("Transition Probability 24H")
    expected_return_12h = best.get("Expected Return 12H (%)")
    expected_return_24h = best.get("Expected Return 24H (%)")
    expected_return_36h = best.get("Expected Return 36H (%)")
    metric_values = [
        ("Best Symbol Today", _explicit_text(best.get("Symbol"), "No selected symbol")),
        ("Stable Bias", _explicit_text(best.get("Stable Daily Bias"))),
        ("Less-Risky Bias", _explicit_text(best.get("Less-Risky Bias"))),
        ("Best Score", _metric_number(score_value, decimals=2)),
        ("Calibrated Probability", _metric_number(best.get("Calibrated Bias Probability"), decimals=1, suffix="%")),
        ("Regime", _explicit_text(best.get("Higher Standard Regime"))),
        ("Estimated Remaining Duration", _metric_number(best.get("Estimated Remaining Duration"), decimals=1, suffix="h")),
        ("Transition Risk 6H", _metric_number(transition_6h, decimals=1, suffix="%")),
        ("Transition Risk 24H", _metric_number(transition_24h, decimals=1, suffix="%")),
        ("Expected Return 12H", _metric_number(expected_return_12h, decimals=3, suffix="%")),
        ("Expected Return 24H", _metric_number(expected_return_24h, decimals=3, suffix="%")),
        ("Expected Return 36H", _metric_number(expected_return_36h, decimals=3, suffix="%")),
        ("Lock Time", _explicit_text(metadata.get("cutoff_broker_time"), "Not locked")),
        ("Lock Remaining", remaining_text),
        ("Safety Veto", _explicit_text(best.get("Safety Veto"), "CLEAR")),
        ("Number Ranked / Hard-Blocked", f"{len(eligible)} / {int(current.get('Safety Web', pd.Series(dtype=object)).astype(str).str.upper().eq('BLOCK').sum())}"),
    ]
    for start in range(0, len(metric_values), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, metric_values[start:start + 4]):
            column.metric(label, value)

    st.caption(
        f"Publication: {metadata.get('publication_status')} | Broker day: {metadata.get('broker_day')} | "
        f"Cutoff completed H1: {metadata.get('latest_completed_h1')} | Universe hash: {str(metadata.get('universe_hash') or '')[:20]}… | "
        f"Checksum: {integrity.get('status')} | Display validation: {overlay_report.get('status', 'CHECK')}"
    )
    query = st.text_input(
        "Search locked morning ranking (display only)",
        key="field10_locked_daily_search_20260702",
        placeholder="symbol, bias, regime, grade, safety, explanation…",
    )
    view = _rank_column_order(_search(current, query))
    st.caption("Decision-critical columns are pinned left for mobile review. The full rows of the top four eligible parent ranks are highlighted; blocked and evidence-check rows remain visible.")
    _display_field10_table(
        view, height=min(620, 48 + 35 * max(1, len(view))), pin_expected_returns=True,
        key="field10_authoritative_rank_table_pinned_20260703",
    )
    st.download_button(
        "⬇ Locked Morning Ranking CSV", data=_csv_bytes(current),
        file_name=f"field10_locked_morning_{metadata.get('broker_day') or 'latest'}.csv",
        mime="text/csv", use_container_width=True, key="field10_locked_morning_download_20260702",
    )

    _render_technical_fundamental_parent(view)
    _render_session_entry_map(metadata)
    _render_finnhub_sentiment_rank(metadata, state)
    _render_crowd_psychology_rank(metadata)
    _render_final_multi_symbol_rank(metadata)
    _render_institutional_validation(institutional_evidence, metadata)

    with st.expander("Open / Close — Latest 25 broker days immutable history", expanded=False):
        load_history = st.checkbox(
            "Load persisted 25-day history and the primary stability map",
            value=False, key="field10_load_locked_history_20260702",
        )
        if load_history:
            history = load_daily_history(days=25, limit=5000)
            if history.empty:
                st.info("No settled immutable daily history is available yet.")
            else:
                history_query = st.text_input(
                    "Search immutable daily history (display only)",
                    key="field10_locked_history_search_20260702",
                )
                history_view = _search(history, history_query)
                _display_field10_table(history_view, height=520)
                st.download_button(
                    "⬇ Full Immutable 25-Day History CSV", data=_csv_bytes(history),
                    file_name="field10_immutable_25_day_history.csv", mime="text/csv",
                    use_container_width=True, key="field10_locked_history_download_20260702",
                )
                st.markdown("##### 25-Day Multi-Symbol Morning Rank Stability and Outcome Map")
                try:
                    import plotly.graph_objects as go
                    plot = history.copy()
                    plot["Original Morning Score"] = pd.to_numeric(plot["Original Morning Score"], errors="coerce")
                    days = sorted(plot["Broker Day"].dropna().astype(str).unique())
                    symbols = sorted(plot["Symbol"].dropna().astype(str).unique())
                    score_pivot = plot.pivot_table(index="Symbol", columns="Broker Day", values="Original Morning Score", aggfunc="first").reindex(index=symbols, columns=days)
                    custom = []
                    for symbol in symbols:
                        row_custom = []
                        for day in days:
                            match = plot.loc[plot["Symbol"].astype(str).eq(symbol) & plot["Broker Day"].astype(str).eq(day)]
                            if match.empty:
                                row_custom.append(["UNAVAILABLE", "UNSETTLED", "—"])
                            else:
                                rec = match.iloc[0]
                                correctness = f"1H={rec.get('Correct 1H')}; 3H={rec.get('Correct 3H')}; 6H={rec.get('Correct 6H')}"
                                row_custom.append([rec.get("Daily Grade"), rec.get("Outcome Settled Status"), correctness])
                        custom.append(row_custom)
                    figure = go.Figure(data=go.Heatmap(
                        z=score_pivot.to_numpy(dtype=float), x=days, y=symbols, customdata=custom,
                        colorbar={"title": "Morning Score"},
                        hovertemplate="Broker day=%{x}<br>Symbol=%{y}<br>Score=%{z:.2f}<br>Grade=%{customdata[0]}<br>Status=%{customdata[1]}<br>%{customdata[2]}<extra></extra>",
                    ))
                    figure.update_layout(height=max(360, 55 * len(symbols)), xaxis_title="Broker Day", yaxis_title="Symbol")
                    st.plotly_chart(figure, use_container_width=True, key="field10_rank_stability_outcome_map_20260702")
                except Exception as exc:
                    st.warning(f"The persisted history table is available, but the stability map could not render: {type(exc).__name__}: {exc}")

    with st.expander("Open / Close — Score components and threshold audit", expanded=False):
        components = bundle.get("components")
        if isinstance(components, pd.DataFrame) and not components.empty:
            st.dataframe(components, use_container_width=True, hide_index=True, height=480)
        else:
            st.info("No score-component rows are stored for this publication.")
    _render_formula_dictionary()


def _render_field3_higher_standard_multi_symbol_top(
    state: MutableMapping[str, Any], universe: Mapping[str, Any]
) -> tuple[list[str], str, str]:
    """Render the requested all-symbol Field 3 Higher row before every Field 10 surface."""
    selected = normalize_selected(universe.get("selected_symbols") or state.get(SELECTED_KEY) or [])
    main = normalize_symbol(universe.get("main_symbol") or (selected[0] if selected else "EURUSD"))
    parent_run_id = str(universe.get("parent_run_id") or state.get("multi_symbol_parent_run_id_20260701") or "")
    if main not in selected:
        selected.insert(0, main)
    from core.system_continuous_validation_20260702 import build_field3_higher_standard_multi_symbol_table

    table, report = build_field3_higher_standard_multi_symbol_table(
        state, selected_symbols=selected, parent_run_id=parent_run_id or None
    )
    st.markdown("### Field 3 Higher-Standard Multi-Symbol Bias — All Completed Settings Symbols")
    st.caption(
        "This is the Field 3 three-standard table's Higher Standard row for every recovered Settings symbol. "
        "BUY/SELL comes from that exact symbol's saved Higher row; exact-symbol local completed H1 evidence is used only when the saved row has no direction. "
        "Lower/Middle rows and other symbols are never borrowed."
    )
    if table.empty:
        st.warning("No exact-symbol Higher Standard evidence is available yet. Run the Settings multi-symbol calculation or use the Field 3 Top 10 Plan B connector.")
    else:
        query = st.text_input(
            "Search Field 3 Higher-Standard all-symbol table",
            key="field10_field3_higher_multi_search_20260703",
            placeholder="symbol, BUY, SELL, regime, quality, evidence source…",
        )
        _display_field10_table(_search(table, query), height=min(520, 48 + 38 * max(1, len(table))))
        metrics = st.columns(4)
        metrics[0].metric("Symbols", int(report.get("row_count") or len(table)))
        metrics[1].metric("Directional BUY/SELL", int(report.get("directional_rows") or 0))
        metrics[2].metric("WAIT", int(report.get("wait_rows") or 0))
        metrics[3].metric("Sync Status", str(report.get("status") or "CHECK"))
        st.download_button(
            "⬇ Field 3 Higher-Standard Multi-Symbol CSV",
            data=_csv_bytes(table),
            file_name=f"field3_higher_standard_multi_symbol_{parent_run_id or 'latest'}.csv",
            mime="text/csv",
            use_container_width=True,
            key="field10_field3_higher_multi_download_20260703",
        )
    state["field10_field3_higher_multi_report_20260703"] = dict(report)
    return selected, main, parent_run_id

def _first_column(frame: pd.DataFrame, *names: str) -> str | None:
    lookup = {str(column).strip().casefold(): column for column in frame.columns}
    for name in names:
        found = lookup.get(str(name).strip().casefold())
        if found is not None:
            return str(found)
    return None


def _normalized_symbol_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    symbol_column = _first_column(out, "Symbol", "symbol", "Affected Symbol", "Affected Symbols")
    if symbol_column is None:
        return pd.DataFrame()
    if symbol_column != "Symbol":
        out = out.rename(columns={symbol_column: "Symbol"})
    out["Symbol"] = out["Symbol"].map(normalize_symbol)
    return out.loc[out["Symbol"].astype(bool)].reset_index(drop=True)


def _latest_run_main_table_20260706(
    state: MutableMapping[str, Any], selected: Sequence[str], manifest: Mapping[str, Any]
) -> tuple[pd.DataFrame, Mapping[str, Any]]:
    report: Mapping[str, Any] = {}
    table = state.get("field10_latest_complete_run_table_20260706")
    run_id = str(state.get("field10_latest_complete_run_id_20260706") or "")
    parent_run_id = str(manifest.get("parent_run_id") or "")
    if not isinstance(table, pd.DataFrame) or table.empty or (parent_run_id and run_id != parent_run_id):
        try:
            from core.multi_symbol_completion_contract_20260706 import load_persisted_complete_run
            persisted, persisted_report = load_persisted_complete_run(parent_run_id or None)
            if isinstance(persisted, pd.DataFrame) and not persisted.empty:
                table = persisted
                report = persisted_report
                run_id = str(persisted_report.get("parent_run_id") or parent_run_id)
                state["field10_latest_complete_run_table_20260706"] = persisted.copy(deep=False)
                state["field10_latest_complete_run_id_20260706"] = run_id
        except Exception:
            pass
    if not isinstance(table, pd.DataFrame) or table.empty or (parent_run_id and run_id != parent_run_id):
        try:
            from core.multi_symbol_completion_contract_20260706 import validate_multi_symbol_completion
            report = validate_multi_symbol_completion(state, manifest, selected_symbols=selected)
            table = state.get("field10_latest_complete_run_table_20260706")
        except Exception as exc:
            report = {"ok": False, "status": "VALIDATION_ERROR", "error": f"{type(exc).__name__}: {exc}"}
    else:
        report = state.get("multi_symbol_completion_contract_20260706") or {}
    table = _normalized_symbol_frame(table if isinstance(table, pd.DataFrame) else pd.DataFrame())
    if table.empty:
        try:
            tables = load_field10_tables(state, parent_run_id=parent_run_id, symbol=selected[0] if selected else None)
            table = _normalized_symbol_frame(tables.get("summary", pd.DataFrame()))
        except Exception:
            table = pd.DataFrame()
    if not table.empty and selected:
        order = {symbol: index for index, symbol in enumerate(selected)}
        table = table.loc[table["Symbol"].isin(selected)].copy()
        table["__order"] = table["Symbol"].map(order)
        rank_column = _first_column(table, "Rank", "Final Rank", "Daily Rank")
        if rank_column:
            table["__rank"] = pd.to_numeric(table[rank_column], errors="coerce")
            table = table.sort_values(["__rank", "__order"], na_position="last", kind="mergesort")
            table = table.drop(columns="__rank")
        else:
            table = table.sort_values("__order", kind="mergesort")
            table.insert(0, "Rank", range(1, len(table) + 1))
        table = table.drop(columns="__order").reset_index(drop=True)
    return table, report if isinstance(report, Mapping) else {}


def _top_news_per_symbol(news: pd.DataFrame) -> pd.DataFrame:
    news = _normalized_symbol_frame(news)
    if news.empty:
        return news
    impact_column = _first_column(news, "News Impact Score", "Impact Score", "Impact", "Event Impact", "News Priority Score", "Priority Score")
    title_column = _first_column(news, "Headline", "Title", "News Item", "Event", "Highest Impact News")
    reason_column = _first_column(news, "Reason", "Impact Reason", "Explanation", "Why Highest Impact", "Rank Reason")
    sentiment_column = _first_column(news, "Sentiment Strength", "Sentiment Score", "Sentiment", "Compound Sentiment")
    source_column = _first_column(news, "Source", "Data Provider", "Provider")
    if impact_column:
        news["__impact"] = pd.to_numeric(news[impact_column], errors="coerce").fillna(-1e12)
        news = news.sort_values(["Symbol", "__impact"], ascending=[True, False], kind="mergesort")
    news = news.drop_duplicates("Symbol", keep="first")
    result = pd.DataFrame({"Symbol": news["Symbol"]})
    result["Highest-Impact News"] = news[title_column] if title_column else "No directly matched persisted news"
    result["News Impact Score"] = news[impact_column] if impact_column else 0.0
    result["Sentiment Strength"] = news[sentiment_column] if sentiment_column else "NEUTRAL / NOT AVAILABLE"
    result["Why This News Has Greatest Impact"] = news[reason_column] if reason_column else "Highest persisted impact score for this symbol"
    result["News Source"] = news[source_column] if source_column else "Persisted news evidence"
    result["Affected Symbol(s)"] = news["Symbol"]
    return result.reset_index(drop=True)


def _load_field10_source_frames_20260706(metadata: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    snapshot_id = str(metadata.get("daily_snapshot_id") or "") or None
    frames: dict[str, pd.DataFrame] = {}
    try:
        from core.field10_crowd_final_20260704 import (
            load_crowd_psychology_rank, load_final_multi_symbol_rank, load_session_entry_map,
        )
        frames["legacy_fusion"] = load_final_multi_symbol_rank(daily_snapshot_id=snapshot_id, apply_live_safety=True)
        frames["session_map"] = load_session_entry_map(daily_snapshot_id=snapshot_id)
        frames["crowd"] = load_crowd_psychology_rank(daily_snapshot_id=snapshot_id)
    except Exception:
        frames.setdefault("legacy_fusion", pd.DataFrame())
        frames.setdefault("session_map", pd.DataFrame())
        frames.setdefault("crowd", pd.DataFrame())
    try:
        from core.field10_finnhub_sentiment_20260704 import load_finnhub_sentiment_rank
        frames["news"] = load_finnhub_sentiment_rank(daily_snapshot_id=snapshot_id, limit=5000)
    except Exception:
        frames["news"] = pd.DataFrame()
    try:
        from core.field10_institutional_shadow_20260704 import load_shadow_evidence
        evidence = load_shadow_evidence(daily_snapshot_id=snapshot_id)
        for key, value in evidence.items():
            if isinstance(value, pd.DataFrame):
                frames[f"validation_{key}"] = value
    except Exception:
        pass
    try:
        from core.field10_research_readonly_20260705 import load_candidate_summary
        frames["horizon_tail_candidate"] = load_candidate_summary(snapshot_id)
    except Exception:
        frames["horizon_tail_candidate"] = pd.DataFrame()
    return frames


def _build_visible_four_source_fusion_20260706(
    base: pd.DataFrame, frames: Mapping[str, pd.DataFrame], completion: Mapping[str, Any]
) -> pd.DataFrame:
    out = _normalized_symbol_frame(base)
    if out.empty:
        return out
    legacy = _normalized_symbol_frame(frames.get("legacy_fusion", pd.DataFrame()))
    if not legacy.empty:
        legacy = legacy.drop_duplicates("Symbol", keep="first")
        duplicates = [column for column in legacy.columns if column != "Symbol" and column in out.columns]
        legacy = legacy.rename(columns={column: f"Fusion {column}" for column in duplicates})
        out = out.merge(legacy, on="Symbol", how="left")
    top_news = _top_news_per_symbol(frames.get("news", pd.DataFrame()))
    if not top_news.empty:
        out = out.merge(top_news, on="Symbol", how="left")
    session = _normalized_symbol_frame(frames.get("session_map", pd.DataFrame()))
    if not session.empty:
        score_col = _first_column(session, "Session Score", "Entry Score", "Session Priority", "Eight-Session Score")
        if score_col:
            session["__score"] = pd.to_numeric(session[score_col], errors="coerce").fillna(-1e12)
            session = session.sort_values(["Symbol", "__score"], ascending=[True, False], kind="mergesort")
        session = session.drop_duplicates("Symbol", keep="first")
        keep = ["Symbol"] + [column for column in session.columns if column != "Symbol"][:8]
        session = session[keep].rename(columns={column: f"Session {column}" for column in keep if column != "Symbol"})
        out = out.merge(session, on="Symbol", how="left")
    crowd = _normalized_symbol_frame(frames.get("crowd", pd.DataFrame()))
    if not crowd.empty:
        crowd = crowd.drop_duplicates("Symbol", keep="first")
        keep = ["Symbol"] + [column for column in crowd.columns if column != "Symbol"][:10]
        crowd = crowd[keep].rename(columns={column: f"Crowd {column}" for column in keep if column != "Symbol"})
        out = out.merge(crowd, on="Symbol", how="left")

    rank_source = _first_column(out, "Final Rank", "Rank", "Daily Rank")
    score_source = _first_column(out, "Final Score", "Comparative Score", "Rank Score", "Data Quality Score")
    reliability_source = _first_column(out, "Calibrated Reliability", "Reliability Score", "Reliability", "Higher Reliability", "Trust Score")
    validation_source = _first_column(out, "Validation Status", "Snapshot Status", "Data Status", "Status")
    bias_source = _first_column(out, "Final Less-Risky Bias to Hold", "Less-Risky Bias", "Higher-Standard Bias", "Final Action")
    out["Technical Ranking"] = pd.to_numeric(out[rank_source], errors="coerce") if rank_source else range(1, len(out) + 1)
    impact = pd.to_numeric(out.get("News Impact Score", pd.Series(0.0, index=out.index)), errors="coerce").fillna(0.0)
    out["News-Impact Ranking"] = impact.rank(method="first", ascending=False).astype(int)
    out["Fundamental Ranking"] = out["News-Impact Ranking"]
    out["Technical Score"] = pd.to_numeric(out[score_source], errors="coerce") if score_source else pd.NA
    out["Final Less-Risky Decision"] = out[bias_source] if bias_source else "WAIT"
    out["Reliability"] = out[reliability_source] if reliability_source else "CHECK"
    out["Visible Validation"] = out[validation_source] if validation_source else "COMPLETE CHILD SNAPSHOT"
    failures = completion.get("field10_failure_reasons") if isinstance(completion.get("field10_failure_reasons"), Mapping) else {}
    out["Validation Failure Reason"] = out["Symbol"].map(lambda symbol: "; ".join(map(str, failures.get(symbol) or [])) or "None")
    out["Four-Source Coverage"] = out.apply(
        lambda row: sum(
            1 for name in ("Technical Ranking", "Fundamental Ranking", "News-Impact Ranking", "Crowd Crowd State")
            if name in out.columns and pd.notna(row.get(name))
        ), axis=1,
    ).map(lambda value: f"{value}/4")
    preferred = [
        "Technical Ranking", "Fundamental Ranking", "News-Impact Ranking", "Symbol",
        "Final Less-Risky Decision", "Technical Score", "Sentiment Strength",
        "Highest-Impact News", "Why This News Has Greatest Impact", "Affected Symbol(s)",
        "Reliability", "Visible Validation", "Validation Failure Reason", "Four-Source Coverage",
    ]
    return out[[column for column in preferred if column in out.columns] + [column for column in out.columns if column not in preferred]]


def _render_visible_validation_table_20260706(completion: Mapping[str, Any]) -> None:
    failures = completion.get("field10_failure_reasons") if isinstance(completion.get("field10_failure_reasons"), Mapping) else {}
    rows = []
    for symbol in completion.get("selected_symbols") or []:
        rows.append({
            "Symbol": symbol,
            "Child Snapshot": (completion.get("child_status") or {}).get(symbol, "WAITING"),
            "Saved Cache": "READY" if symbol not in (completion.get("missing_saved_symbol_caches") or []) else "MISSING",
            "Field 10 Row": "COMPLETE" if symbol not in (completion.get("missing_or_invalid_field10_symbols") or []) else "INCOMPLETE",
            "Reliability / Validation": "PASSED" if symbol not in (completion.get("missing_or_invalid_field10_symbols") or []) else "FAILED",
            "Failure Reason": "; ".join(map(str, failures.get(symbol) or [])) or "None",
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_field10_three_sections_20260706(state: MutableMapping[str, Any]) -> None:
    universe = recover_symbol_universe(state)
    selected = normalize_selected(universe.get("selected_symbols") or state.get(SELECTED_KEY) or [])
    manifest = state.get(MANIFEST_KEY) if isinstance(state.get(MANIFEST_KEY), Mapping) else {}
    if not selected:
        selected = normalize_selected(manifest.get("selected_symbols") or [])
    main_table, completion = _latest_run_main_table_20260706(state, selected, manifest)
    try:
        from core.field10_daily_snapshot_contract_20260702 import load_current_daily_snapshot, load_daily_history
        bundle = load_current_daily_snapshot()
        metadata = bundle.get("metadata") if isinstance(bundle.get("metadata"), Mapping) else {}
    except Exception:
        metadata = {}
        load_daily_history = None  # type: ignore
    source_frames = _load_field10_source_frames_20260706(metadata)
    fusion = _build_visible_four_source_fusion_20260706(main_table, source_frames, completion)

    st.markdown('<div id="field-10-anchor"></div>', unsafe_allow_html=True)
    st.markdown("### Field 10 — Restored Complete Three-Section Multi-Symbol Decision System")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selected Symbols", len(selected))
    c2.metric("Complete Field 10 Rows", int(completion.get("field10_row_count") or len(main_table)))
    c3.metric("Completion Contract", "PASSED" if completion.get("ok") else "NOT COMPLETE")
    c4.metric("Run ID", str(manifest.get("parent_run_id") or "-")[-18:])
    if completion.get("ok"):
        st.success("Visible validation passed: all selected symbols have complete Field 10 rows from the same calculation run.")
    else:
        st.error("Field 10 is not marked successful because one or more selected symbols lacks a complete validated result row.")

    with st.expander("FIELD 10 — SECTION 1: Complete Latest-Run Ranking Table", expanded=False):
        st.caption("Latest-run first ranking table. It uses the same selected-symbol calculation generation and does not borrow another symbol's values.")
        if main_table.empty:
            st.error("No latest-run ranking table is available.")
        else:
            query = st.text_input("Search Section 1 ranking", key="field10_section1_search_20260706")
            _display_field10_table(_search(main_table, query), height=min(720, 60 + 38 * max(1, len(main_table))), pin_expected_returns=True, key="field10_section1_table_20260706")
        st.markdown("#### Visible Validation")
        _render_visible_validation_table_20260706(completion)

    with st.expander("FIELD 10 — SECTION 2: Legacy Four-Source Fusion + Technical/Fundamental Ranking", expanded=False):
        st.caption("Complete visible fusion of technical, fundamental/news, eight-session and crowd-psychology evidence. Highest-impact news is ranked first; validation remains visible.")
        if fusion.empty:
            st.warning("The fusion table is unavailable because no current multi-symbol ranking rows were published.")
        else:
            query = st.text_input("Search four-source fusion", key="field10_section2_search_20260706")
            view = _search(fusion, query)
            if "News Impact Score" in view.columns:
                view = view.assign(__impact=pd.to_numeric(view["News Impact Score"], errors="coerce").fillna(-1e12)).sort_values(["__impact", "Technical Ranking"], ascending=[False, True], kind="mergesort").drop(columns="__impact")
            _display_field10_table(view, height=min(760, 60 + 38 * max(1, len(view))), pin_expected_returns=True, key="field10_section2_fusion_20260706")
        tabs = st.tabs(["Technical/Fundamental", "News + Sentiment + Absorption", "Eight Sessions", "Crowd Psychology"])
        with tabs[0]:
            technical_columns = [column for column in (
                "Technical Ranking", "Fundamental Ranking", "Symbol", "Final Less-Risky Decision",
                "Technical Score", "Reliability", "Visible Validation", "Validation Failure Reason",
            ) if column in fusion.columns]
            st.dataframe(fusion[technical_columns] if technical_columns else fusion, use_container_width=True, hide_index=True)
        with tabs[1]:
            news = source_frames.get("news", pd.DataFrame())
            st.dataframe(news if not news.empty else _top_news_per_symbol(news), use_container_width=True, hide_index=True)
        with tabs[2]:
            st.dataframe(source_frames.get("session_map", pd.DataFrame()), use_container_width=True, hide_index=True)
        with tabs[3]:
            st.dataframe(source_frames.get("crowd", pd.DataFrame()), use_container_width=True, hide_index=True)

    with st.expander("FIELD 10 — SECTION 3: Combined Advanced Ranking and Decision Field", expanded=False):
        st.caption("Combines the 10-day first-rank history, scores, entry map, sentiment, high-impact news, absorption, crowd psychology, validation, reliability and risk-protection status.")
        advanced = fusion.copy() if not fusion.empty else main_table.copy()
        if not advanced.empty:
            permission_column = _first_column(advanced, "Final Entry Permission", "Trade Permission", "Entry Permission", "Visible Validation")
            advanced["Shutdown / Risk-Protection Status"] = (
                advanced[permission_column].astype(str).str.upper().map(
                    lambda value: "PROTECTED / BLOCKED" if any(token in value for token in ("BLOCK", "FAIL", "INCOMPLETE")) else "ACTIVE WITH VALIDATION"
                ) if permission_column else "ACTIVE WITH VALIDATION"
            )
            _display_field10_table(advanced, height=min(760, 60 + 38 * max(1, len(advanced))), pin_expected_returns=True, key="field10_section3_advanced_20260706")
            score_col = _first_column(advanced, "Technical Score", "Comparative Score", "Rank Score", "Reliability")
            if score_col and "Symbol" in advanced.columns:
                chart = advanced[["Symbol", score_col]].copy()
                chart[score_col] = pd.to_numeric(chart[score_col], errors="coerce")
                chart = chart.dropna()
                if not chart.empty:
                    st.markdown("#### Main Advanced Ranking Visualization")
                    st.bar_chart(chart.set_index("Symbol")[score_col], use_container_width=True)
        detail_tabs = st.tabs(["10-Day Rank-1", "AI High-Impact News", "Absorption", "Validation + Reliability", "Risk Protection", "Shadow Candidate Audit"])
        with detail_tabs[0]:
            try:
                history = load_daily_history(days=10, limit=5000) if callable(load_daily_history) else pd.DataFrame()
                rank_col = _first_column(history, "Daily Rank", "Rank", "Final Rank")
                if rank_col:
                    history = history.loc[pd.to_numeric(history[rank_col], errors="coerce").eq(1)]
                st.dataframe(history if not history.empty else advanced.head(1), use_container_width=True, hide_index=True)
            except Exception as exc:
                st.info(f"10-day rank-1 history is not available: {type(exc).__name__}")
        with detail_tabs[1]:
            news = source_frames.get("news", pd.DataFrame())
            if not news.empty:
                impact_col = _first_column(news, "News Impact Score", "Impact Score", "Impact", "Priority Score")
                if impact_col:
                    news = news.assign(__impact=pd.to_numeric(news[impact_col], errors="coerce").fillna(-1e12)).sort_values("__impact", ascending=False).drop(columns="__impact")
            st.dataframe(news, use_container_width=True, hide_index=True)
        with detail_tabs[2]:
            news = source_frames.get("news", pd.DataFrame())
            absorption_columns = [column for column in news.columns if "absorp" in str(column).casefold() or str(column).casefold() in {"symbol", "headline", "title"}]
            st.dataframe(news[absorption_columns] if absorption_columns else news, use_container_width=True, hide_index=True)
        with detail_tabs[3]:
            _render_visible_validation_table_20260706(completion)
            validation_frames = [frame for name, frame in source_frames.items() if name.startswith("validation_") and isinstance(frame, pd.DataFrame) and not frame.empty]
            for frame in validation_frames[:4]:
                st.dataframe(frame, use_container_width=True, hide_index=True)
        with detail_tabs[4]:
            if not advanced.empty:
                risk_columns = [column for column in advanced.columns if any(token in str(column).casefold() for token in ("risk", "permission", "shutdown", "warning", "validation", "reliability", "symbol"))]
                st.dataframe(advanced[risk_columns] if risk_columns else advanced, use_container_width=True, hide_index=True)
        with detail_tabs[5]:
            st.markdown("#### Legacy / Diagnostics — Previous Field 10 Surfaces")
            st.info("SHADOW VALIDATION — NO PRODUCTION INFLUENCE")
            candidate = source_frames.get("horizon_tail_candidate", pd.DataFrame())
            if candidate.empty:
                st.caption("No horizon-connected tail candidate was published for this completed run.")
            else:
                st.dataframe(candidate, use_container_width=True, hide_index=True)


def _dedupe_ordered(values: Sequence[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        symbol = normalize_symbol(value)
        if symbol and symbol not in result:
            result.append(symbol)
    return result


def _field10_loaded_symbol_contract(
    state: MutableMapping[str, Any], universe: Mapping[str, Any]
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Return only the current exact loaded/published universe in selector order."""
    load_evidence: dict[str, dict[str, Any]] = {}
    loaded: list[str] = []
    timeframe = str(state.get("canonical_ranking_timeframe") or state.get("settings_timeframe") or state.get("timeframe") or state.get("selected_timeframe") or "H4").upper()
    try:
        from core.multi_symbol_run_groups_20260706 import configured_groups
        from core.multi_symbol_load_manager_20260707 import loaded_universe_status
        groups = configured_groups(state)
        status = loaded_universe_status(state, groups, timeframe)
        requested = normalize_selected(
            status.get("requested_symbols")
            or state.get("canonical_ranking_symbols")
            or state.get("canonical_selected_symbols")
            or state.get("canonical_selected_symbols_20260705")
            or []
        )
        loaded_symbols = set(normalize_selected(status.get("loaded_symbols") or []))
        failed_symbols = set(normalize_selected(status.get("failed_symbols") or []))
        # Field 10 must render every canonical selected symbol, not only the
        # already-successful subset. Failed symbols keep a visible row with
        # FAILED_NO_DATA and a clear reason.
        loaded = list(requested)
        memberships: dict[str, list[str]] = {}
        group_status_map = status.get("group_status") if isinstance(status.get("group_status"), Mapping) else {}
        for group_name, group_status in group_status_map.items():
            group_status = group_status if isinstance(group_status, Mapping) else {}
            validations = group_status.get("validations") if isinstance(group_status.get("validations"), Mapping) else {}
            for symbol in normalize_selected(group_status.get("requested_symbols") or []):
                memberships.setdefault(symbol, []).append(str(group_name).lower())
                evidence = dict(validations.get(symbol) or {})
                current = load_evidence.get(symbol, {})
                if evidence.get("ok") or not current:
                    load_evidence[symbol] = evidence
        for row in status.get("status_rows") or []:
            if isinstance(row, Mapping):
                symbol = normalize_symbol(row.get("Symbol"))
                if symbol:
                    load_evidence.setdefault(symbol, {}).update({
                        "provider": row.get("Data Provider Used"),
                        "rows": row.get("Candle Count"),
                        "latest_candle_time": row.get("Latest Candle Time") or row.get("Last Candle Time"),
                        "data_quality": row.get("Data Quality Grade"),
                        "Load Status": row.get("Load Status"),
                        "reason": row.get("Failure Reason"),
                        "key_pool_attempted": row.get("Twelve Key Pool Attempted"),
                        "key_pool_error": row.get("Twelve Key Pool Error"),
                        "twelve_attempted": row.get("Twelve Attempted"),
                        "twelve_error": row.get("Twelve Error"),
                        "cache_used": row.get("Cache Used"),
                        "reload_eligible": row.get("Reload Eligible"),
                    })
        for symbol in requested:
            evidence = load_evidence.setdefault(symbol, {})
            if symbol in loaded_symbols:
                evidence["Load Status"] = evidence.get("Load Status") or "READY"
                evidence.setdefault("ok", True)
            elif symbol in failed_symbols:
                evidence["Load Status"] = "FAILED_NO_DATA"
                evidence.setdefault("ok", False)
            else:
                evidence["Load Status"] = evidence.get("Load Status") or "PENDING"
            evidence["Selector Groups"] = ", ".join(memberships.get(symbol) or ["canonical"])
    except Exception as exc:
        state["field10_loaded_universe_display_error_20260707"] = f"{type(exc).__name__}: {exc}"

    if not loaded:
        loaded = normalize_selected(
            state.get("canonical_ranking_symbols")
            or state.get("canonical_selected_symbols")
            or state.get("canonical_selected_symbols_20260705")
            or universe.get("selected_symbols")
            or []
        )
        for symbol in loaded:
            load_evidence.setdefault(symbol, {"Load Status": "PENDING", "Selector Groups": "canonical", "ok": False})

    # After a successful publication, retain exact completed rows from the same
    # active manifest only when the in-memory load report was restored lazily.
    if not loaded:
        manifest = state.get(MANIFEST_KEY) if isinstance(state.get(MANIFEST_KEY), Mapping) else {}
        symbol_status = manifest.get("symbol_status") if isinstance(manifest.get("symbol_status"), Mapping) else {}
        for symbol in normalize_selected(manifest.get("selected_symbols") or []):
            item = symbol_status.get(symbol) if isinstance(symbol_status.get(symbol), Mapping) else {}
            effective = str(item.get("publication_status") or item.get("state") or item.get("status") or "").upper()
            if effective in {"COMPLETED", "PUBLISHED", "READY"}:
                loaded.append(symbol)
                load_evidence[symbol] = {
                    "Load Status": "PUBLISHED",
                    "Selector Groups": "published manifest",
                    "provider": item.get("provider"),
                    "rows": item.get("available_candles"),
                    "reason": item.get("rejection_reason") or "PUBLISHED",
                    "ok": True,
                }
    return _dedupe_ordered(loaded), load_evidence

def _frame_for_symbol_merge(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    normalized = _normalized_symbol_frame(frame)
    if normalized.empty:
        return pd.DataFrame(columns=["Symbol"])
    # One current row per exact symbol.  Existing ranking order is retained.
    normalized = normalized.drop_duplicates(subset=["Symbol"], keep="first").reset_index(drop=True)
    rename = {column: f"{prefix} • {column}" for column in normalized.columns if column != "Symbol"}
    return normalized.rename(columns=rename)


def _coalesce_column(frame: pd.DataFrame, target: str, candidates: Sequence[str]) -> None:
    available = [column for column in candidates if column in frame.columns]
    if not available:
        return
    if target in frame.columns:
        series = frame[target].copy()
        candidate_iter = available
    else:
        series = frame[available[0]].copy()
        candidate_iter = available[1:]
    for column in candidate_iter:
        series = series.where(series.notna() & series.astype(str).str.strip().ne(""), frame[column])
    frame[target] = series



def _latest_load_cache_20260708(symbols: Sequence[str], timeframe: str) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    try:
        from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH, migrate_deployment_schema
        migrate_deployment_schema(DEFAULT_DB_PATH)
        placeholders = ",".join("?" for _ in symbols)
        query = f"""
            SELECT symbol,timeframe,provider_used,api_status,candle_count,latest_price,
                   latest_candle_time,data_quality,load_time,error_message,run_id
            FROM forex_symbol_load_cache_20260708
            WHERE symbol IN ({placeholders}) AND timeframe=?
            ORDER BY symbol, load_time DESC
        """
        out: dict[str, dict[str, Any]] = {}
        with sqlite3.connect(str(DEFAULT_DB_PATH), timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute(query, [normalize_symbol(s) for s in symbols] + [str(timeframe or "H4").upper()]):
                symbol = normalize_symbol(row["symbol"])
                if symbol not in out:
                    out[symbol] = dict(row)
        return out
    except Exception:
        return {}


def _latest_news_bias_20260708(symbols: Sequence[str]) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    try:
        from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH, migrate_deployment_schema
        migrate_deployment_schema(DEFAULT_DB_PATH)
        with sqlite3.connect(str(DEFAULT_DB_PATH), timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT title,description,published_at,fetched_at,provider_sentiment,
                          pair_direction_implication,eurusd_relevance,event_importance
                   FROM news_articles
                   ORDER BY COALESCE(published_at,fetched_at) DESC
                   LIMIT 250"""
            ).fetchall()
    except Exception:
        rows = []
    out: dict[str, dict[str, Any]] = {}
    for symbol in [normalize_symbol(s) for s in symbols]:
        base, quote = symbol[:3], symbol[3:]
        best: dict[str, Any] | None = None
        best_score = -1.0
        for row in rows:
            title = str(row["title"] or "")
            text = (title + " " + str(row["description"] or "")).upper()
            score = 0.0
            if symbol in text or f"{base}/{quote}" in text:
                score += 100.0
            if base and base in text:
                score += 35.0
            if quote and quote in text:
                score += 35.0
            try:
                score += float(row["eurusd_relevance"] or 0) * (1.0 if symbol == "EURUSD" else 0.25)
            except Exception:
                pass
            try:
                score += float(row["event_importance"] or 0)
            except Exception:
                pass
            if score > best_score:
                implication = row["pair_direction_implication"]
                try:
                    value = float(implication or row["provider_sentiment"] or 0.0)
                except Exception:
                    value = 0.0
                bias = "BUY" if value > 0.05 else "SELL" if value < -0.05 else "NEUTRAL"
                best_score = score
                best = {
                    "New Title": title or "Not available",
                    "Sentiment Bias": bias,
                    "News Published Time": row["published_at"] or row["fetched_at"] or "Not available",
                }
        out[symbol] = best or {"New Title": "Not available", "Sentiment Bias": "NEUTRAL", "News Published Time": "Not available"}
    return out


def _best_session_for_entry_20260708(row: Mapping[str, Any]) -> str:
    for key in ("Best Session to Trade", "Current Session", "Session Bias"):
        value = str(row.get(key) or "").strip()
        if value and value.lower() not in {"not available", "unavailable", "nan", "none"}:
            return value
    bias = str(row.get("Less-Risky Bias") or row.get("Higher-Standard Bias") or "").upper()
    if bias in {"BUY", "SELL"}:
        return "London / New York overlap"
    return "Wait / no clean session"


def _build_consolidated_field10_table_20260707(
    state: MutableMapping[str, Any], universe: Mapping[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    symbols, load_evidence = _field10_loaded_symbol_contract(state, universe)
    active_timeframe_20260708 = str(state.get("canonical_ranking_timeframe") or state.get("settings_timeframe") or state.get("timeframe") or state.get("selected_timeframe") or "H4").upper()
    load_cache_20260708 = _latest_load_cache_20260708(symbols, active_timeframe_20260708)
    news_bias_20260708 = _latest_news_bias_20260708(symbols)
    parent_run_id = str(universe.get("parent_run_id") or state.get("multi_symbol_parent_run_id_20260701") or "")
    manifest = state.get(MANIFEST_KEY) if isinstance(state.get(MANIFEST_KEY), Mapping) else {}

    try:
        from core.system_continuous_validation_20260702 import build_field3_higher_standard_multi_symbol_table
        higher, higher_report = build_field3_higher_standard_multi_symbol_table(
            state, selected_symbols=symbols, parent_run_id=parent_run_id or None
        )
    except Exception as exc:
        higher, higher_report = pd.DataFrame(), {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}

    latest, completion = _latest_run_main_table_20260706(state, symbols, manifest)
    try:
        from core.field10_daily_snapshot_contract_20260702 import load_current_daily_snapshot
        bundle = load_current_daily_snapshot()
        metadata = bundle.get("metadata") if isinstance(bundle.get("metadata"), Mapping) else {}
    except Exception:
        metadata = {}
    sources = _load_field10_source_frames_20260706(metadata)
    fusion = _build_visible_four_source_fusion_20260706(latest, sources, completion)

    # The symbol spine guarantees every loaded/configured exact symbol remains visible.
    base = pd.DataFrame({"Symbol": symbols}) if symbols else pd.DataFrame(columns=["Symbol"])
    for source, prefix in ((higher, "Field 3 Higher"), (latest, "Latest Run"), (fusion, "Integrated")):
        merge = _frame_for_symbol_merge(source, prefix)
        if not merge.empty:
            base = base.merge(merge, on="Symbol", how="left", sort=False)

    # Add exact load/validation evidence without serializing or exposing secrets.
    load_rows = []
    for symbol in base.get("Symbol", pd.Series(dtype=object)).astype(str):
        evidence = load_evidence.get(normalize_symbol(symbol), {})
        symbol_key = normalize_symbol(symbol)
        cached_load = load_cache_20260708.get(symbol_key, {})
        news = news_bias_20260708.get(symbol_key, {})
        provider_used = cached_load.get("provider_used") or evidence.get("provider") or "Not available"
        if str(provider_used).upper() in {"TWELVE_DATA", "TWELVE_DATA_FALLBACK"}:
            provider_used = "TWELVE_DATA_KEY_POOL"
        rows_loaded = cached_load.get("candle_count") or evidence.get("rows")
        latest_candle_time = cached_load.get("latest_candle_time") or evidence.get("latest_candle_time") or evidence.get("latest_completed_candle")
        load_status_value = evidence.get("Load Status", "COMPLETED SNAPSHOT" if evidence.get("ok") else "PENDING")
        data_quality_value = cached_load.get("data_quality") or evidence.get("data_quality") or ("USABLE" if evidence.get("ok") else "CHECK")
        reason_value = cached_load.get("error_message") or evidence.get("failure_reason") or evidence.get("reason") or "Not available"
        freshness_value = (
            "FRESH" if str(cached_load.get("api_status") or evidence.get("api_status") or "").upper() in {"COMPLETED", "TWELVE_SUCCESS", "FINNHUB_SUCCESS"}
            else "STALE_BUT_USABLE" if str(provider_used).upper() in {"LOCAL_VALID_CACHE", "CACHE", "SQLITE"} and (rows_loaded or 0)
            else "NO_USABLE_DATA" if str(load_status_value).upper() == "FAILED_NO_DATA"
            else "PENDING"
        )
        load_rows.append({
            "Symbol": symbol_key,
            "Timeframe": active_timeframe_20260708,
            "Data Provider Used": provider_used,
            "Actual Candle Provider": provider_used,
            "Provider Trace": str(evidence.get("provider_trace") or {"provider_used": provider_used, "key_pool_attempted": evidence.get("key_pool_attempted"), "twelve_attempted": evidence.get("twelve_attempted"), "cache_used": evidence.get("cache_used")}),
            "Candle Count": rows_loaded,
            "Latest Candle Time": latest_candle_time,
            "Data Freshness": freshness_value,
            "Data Quality Grade": data_quality_value,
            "Load Status": load_status_value,
            "Load Final State": "VALIDATED" if str(load_status_value).upper() in {"CACHE_SUCCESS", "TWELVE_SUCCESS", "FINNHUB_SUCCESS", "READY", "COMPLETED"} else "DEGRADED_VALID_CACHE" if str(load_status_value).upper() in {"EMERGENCY_CACHE_SUCCESS", "STALE_VALID"} else "FAILED_EXPLICIT" if str(load_status_value).upper().startswith("FAILED") else str(load_status_value),
            "Failure Reason if not rankable": reason_value,
            "Rank Score": None,
            "Decision": evidence.get("decision") or evidence.get("bias") or "WAIT / REVIEW",
            "Reason": reason_value,
            "Selector Group": evidence.get("Selector Group", evidence.get("Selector Groups", "canonical")),
            "Loaded Candles": rows_loaded,
            "Required Candles": evidence.get("required_rows"),
            "Minimum Candles": evidence.get("minimum_rows"),
            "History Mode": evidence.get("calculation_mode"),
            "Provider": provider_used,
            "Provider Used": provider_used,
            "Rows": rows_loaded,
            "Latest Candle": latest_candle_time,
            "Latest Price": cached_load.get("latest_price"),
            "API Status": cached_load.get("api_status") or evidence.get("api_status") or ("COMPLETED" if evidence.get("ok") else "CHECK"),
            "Twelve Key Pool Attempted": bool(evidence.get("key_pool_attempted") or evidence.get("twelve_attempted")),
            "Twelve Key Pool Error": evidence.get("key_pool_error") or evidence.get("twelve_error") or "",
            "Twelve Attempted": bool(evidence.get("twelve_attempted")),
            "Twelve Error": evidence.get("twelve_error") or "",
            "Cache Used": bool(evidence.get("cache_used")),
            "Reload Eligible": bool(evidence.get("reload_eligible") or str(load_status_value).upper() in {"FAILED_NO_DATA", "FAILED_VALIDATION", "EMPTY_RESPONSE", "API_ERROR", "FAILED", "PENDING"}),
            "Load Data Quality": data_quality_value,
            "New Title": news.get("New Title"),
            "Sentiment Bias": news.get("Sentiment Bias"),
            "Timeframe Spacing": (evidence.get("spacing") or {}).get("status") if isinstance(evidence.get("spacing"), Mapping) else None,
            "Load Validation": "PASS" if evidence.get("ok") or cached_load.get("api_status") == "COMPLETED" else reason_value,
        })
    if load_rows:
        base = base.merge(pd.DataFrame(load_rows), on="Symbol", how="left")

    # Publish concise authoritative columns first, while retaining all source
    # columns to the right for detailed institutional review.
    aliases = {
        "Rank": (
            "Field 3 Higher • Rank", "Latest Run • Final Rank", "Latest Run • Daily Rank",
            "Latest Run • Rank", "Integrated • Technical Ranking",
        ),
        "Completed Candle": (
            "Field 3 Higher • Completed Broker Candle", "Field 3 Higher • Time",
            "Latest Run • Completed Broker Candle", "Latest Run • Time",
            "Integrated • Completed Broker Candle", "Integrated • Time",
        ),
        "Timeframe": (
            "Field 3 Higher • Timeframe", "Latest Run • Timeframe", "Integrated • Timeframe",
        ),
        "Higher Standard Regime": (
            "Field 3 Higher • Higher Standard Regime", "Field 3 Higher • Higher Standard",
            "Field 3 Higher • Regime", "Latest Run • Higher Standard Regime",
        ),
        "Higher-Standard Bias": (
            "Field 3 Higher • Higher-Standard Bias", "Field 3 Higher • Higher Standard Bias",
            "Field 3 Higher • Bias", "Latest Run • Higher-Standard Bias",
        ),
        "Less-Risky Bias": (
            "Field 3 Higher • Less-Risky Bias", "Field 3 Higher • Less Risky Bias",
            "Latest Run • Final Less-Risky Bias", "Latest Run • Less-Risky Bias",
            "Integrated • Final Less-Risky Decision", "Integrated • Final Less-Risky Bias",
        ),
        "Reliability": (
            "Field 3 Higher • Reliability", "Latest Run • Calibrated Reliability",
            "Latest Run • Reliability", "Integrated • Reliability",
        ),
        "Data Quality": (
            "Field 3 Higher • Data Quality", "Latest Run • Data Quality",
            "Integrated • Data Quality",
        ),
        "Sample Count": (
            "Field 3 Higher • Sample Count", "Latest Run • Sample Count",
            "Latest Run • Available Candles", "Integrated • Sample Count",
        ),
        "Regime Probability": (
            "Field 3 Higher • Regime Probability", "Latest Run • Regime Probability",
            "Latest Run • Calibrated Probability", "Integrated • Calibrated Probability",
        ),
        "Transition Risk 1H": (
            "Field 3 Higher • Transition Risk 1H", "Latest Run • Transition Risk 1H",
            "Integrated • Transition Risk 1H",
        ),
        "Transition Risk 3H": (
            "Field 3 Higher • Transition Risk 3H", "Latest Run • Transition Risk 3H",
            "Integrated • Transition Risk 3H",
        ),
        "Transition Risk 6H": (
            "Field 3 Higher • Transition Risk 6H", "Latest Run • Transition Risk 6H",
            "Integrated • Transition Risk 6H",
        ),
        "Transition Risk 12H": (
            "Field 3 Higher • Transition Risk 12H", "Latest Run • Transition Risk 12H",
            "Integrated • Transition Risk 12H",
        ),
        "Transition Risk 24H": (
            "Field 3 Higher • Transition Risk 24H", "Latest Run • Transition Risk 24H",
            "Integrated • Transition Risk 24H",
        ),
        "Transition Risk 36H": (
            "Field 3 Higher • Transition Risk 36H", "Latest Run • Transition Risk 36H",
            "Integrated • Transition Risk 36H",
        ),
        "Expected Return 1H (%)": (
            "Field 3 Higher • Expected Return 1H (%)", "Latest Run • Expected Return 1H (%)",
            "Integrated • Expected Return 1H (%)",
        ),
        "Expected Return 3H (%)": (
            "Field 3 Higher • Expected Return 3H (%)", "Latest Run • Expected Return 3H (%)",
            "Integrated • Expected Return 3H (%)",
        ),
        "Expected Return 6H (%)": (
            "Field 3 Higher • Expected Return 6H (%)", "Latest Run • Expected Return 6H (%)",
            "Integrated • Expected Return 6H (%)",
        ),
        "Expected Return 12H (%)": (
            "Field 3 Higher • Expected Return 12H (%)", "Latest Run • Expected Return 12H (%)",
            "Integrated • Expected Return 12H (%)", "Integrated • Expected Value 12H",
        ),
        "Expected Return 24H (%)": (
            "Field 3 Higher • Expected Return 24H (%)", "Latest Run • Expected Return 24H (%)",
            "Integrated • Expected Return 24H (%)",
        ),
        "Expected Return 36H (%)": (
            "Field 3 Higher • Expected Return 36H (%)", "Latest Run • Expected Return 36H (%)",
            "Integrated • Expected Return 36H (%)",
        ),
        "Technical Rank": (
            "Integrated • Technical Ranking", "Integrated • Technical/Fundamental Rank",
            "Latest Run • Technical Rank",
        ),
        "Fundamental Rank": (
            "Integrated • Fundamental Ranking", "Latest Run • Fundamental Rank",
        ),
        "Technical Score": (
            "Integrated • Technical Score", "Latest Run • Technical Score",
            "Latest Run • Institutional Morning Score",
        ),
        "Final Score": (
            "Latest Run • Final Score", "Latest Run • Rank Score", "Integrated • Comparative Score",
        ),
        "News Impact": (
            "Integrated • News Impact Score", "Integrated • Impact Score", "Integrated • News/Absorption Rank",
        ),
        "Sentiment Bias": (
            "Integrated • Sentiment Bias", "Integrated • News Bias", "Integrated • Fundamental Bias",
        ),
        "Session Bias": (
            "Integrated • Session Bias", "Integrated • Eight-Session Bias", "Integrated • Eight Sessions",
        ),
        "Crowd Psychology": (
            "Integrated • Crowd Psychology", "Integrated • Crowd Psychology Bias", "Integrated • Crowd Psychology Rank",
        ),
        "Entry Permission": (
            "Latest Run • Final Entry Permission", "Latest Run • Entry Permission",
            "Integrated • Final Entry Permission", "Integrated • Trade Permission",
        ),
        "Validation Status": (
            "Latest Run • Validation Status", "Latest Run • Visible Validation",
            "Integrated • Visible Validation", "Integrated • Validation Status",
        ),
        "Validation Evidence": (
            "Latest Run • Validation Failure Reason", "Integrated • Validation Failure Reason",
            "Field 3 Higher • Evidence Source",
        ),
        "Evidence Source": (
            "Field 3 Higher • Evidence Source", "Latest Run • Evidence Source",
            "Integrated • Evidence Source",
        ),
    }
    for target, candidates in aliases.items():
        _coalesce_column(base, target, candidates)

    # Canonical three-group column contract. Values are coalesced only from the
    # same exact-symbol row; unavailable optional evidence is explicit.
    additional_aliases = {
        "Expected Value": ("Latest Run • Expected Value", "Integrated • Expected Value", "Integrated • Risk-Adjusted EV", "Expected Return 12H (%)"),
        "Fundamental Score": ("Integrated • Fundamental Score", "Latest Run • Fundamental Score", "News Impact"),
        "Combined Score": ("Latest Run • Combined Score", "Integrated • Combined Score", "Final Score", "Technical Score"),
        "Safety Veto": ("Latest Run • Safety Veto", "Integrated • Safety Veto", "Integrated • Protect Veto", "Latest Run • Protect / Block"),
        "Unexpected Status": ("Latest Run • Unexpected Status", "Integrated • Unexpected Status", "Integrated • Risk Status"),
        "Calculation Status": ("Latest Run • Calculation Status", "Latest Run • Publication Status", "Validation Status"),
        "Best Session to Trade": ("Integrated • Best Session to Trade", "Integrated • Best Session", "Session Bias"),
        "Best Session Score": ("Integrated • Best Session Score", "Integrated • Session Score", "Integrated • Eight-Session Score"),
        "Current Session": ("Integrated • Current Session", "Latest Run • Current Session"),
        "Current Session Suitability": ("Integrated • Current Session Suitability", "Integrated • Session Suitability", "Integrated • Current Session Score"),
        "Highest-Impact Current News Title": ("Integrated • Highest-Impact Current News Title", "Integrated • Highest Impact News Title", "Integrated • Top News Title", "Integrated • Headline", "Integrated • Title"),
        "News Published Time": ("Integrated • News Published Time", "Integrated • Published Time", "Integrated • News Time"),
        "News Impact Level": ("Integrated • News Impact Level", "Integrated • Impact Level", "News Impact"),
        "News Currency/Pair Relevance": ("Integrated • News Currency/Pair Relevance", "Integrated • Pair Relevance", "Integrated • Relevance"),
        "News Surprise": ("Integrated • News Surprise", "Integrated • Surprise", "Integrated • Surprise Score"),
        "Absorption Status": ("Integrated • Absorption Status", "Integrated • News Absorption Status", "Integrated • Absorption"),
        "Absorption Score": ("Integrated • Absorption Score", "Integrated • News Absorption Score"),
        "NLP Sentiment Bias": ("Integrated • NLP Sentiment Bias", "Integrated • Sentiment Bias", "Sentiment Bias"),
        "NLP Sentiment Score": ("Integrated • NLP Sentiment Score", "Integrated • Sentiment Score"),
        "Data-Mining Sentiment Bias": ("Integrated • Data-Mining Sentiment Bias", "Integrated • Data Mining Sentiment Bias"),
        "Crowd Psychology Bias": ("Integrated • Crowd Psychology Bias", "Crowd Psychology"),
        "Technical/Fundamental Agreement": ("Integrated • Technical/Fundamental Agreement", "Integrated • Technical Fundamental Agreement", "Integrated • Agreement"),
        "News/Technical Conflict": ("Integrated • News/Technical Conflict", "Integrated • News Technical Conflict", "Integrated • Conflict"),
        "Protect/Block Reason": ("Integrated • Protect/Block Reason", "Latest Run • Protect/Block Reason", "Validation Evidence"),
        "Data Quality Score": ("Latest Run • Data Quality Score", "Integrated • Data Quality Score", "Field 3 Higher • Data Quality Score"),
        "Ranking Result": ("Latest Run • Ranking Result", "Integrated • Ranking Result", "Final Score", "Combined Score"),
        "Best Session For Entry": ("Integrated • Best Session For Entry", "Best Session to Trade", "Current Session"),
    }
    for target, candidates in additional_aliases.items():
        _coalesce_column(base, target, candidates)

    manifest_generation = (manifest.get("generation") or manifest.get("publication_generation") or state.get("canonical_generation_20260705"))
    manifest_run_id = str(manifest.get("parent_run_id") or manifest.get("run_id") or parent_run_id or "Not available")
    optional_columns = {
        "Highest-Impact Current News Title", "New Title", "News Published Time", "News Impact Level",
        "News Currency/Pair Relevance", "News Surprise", "Absorption Status",
        "Absorption Score", "NLP Sentiment Bias", "NLP Sentiment Score",
        "Data-Mining Sentiment Bias", "Crowd Psychology Bias",
    }
    required_contract = [
        "Final Rank", "Symbol", "Timeframe", "Scaled Score", "Actual Candle Provider", "Provider Trace", "Load Final State",
        "Data Provider Used", "Candle Count", "Sample Count", "Latest Candle Time",
        "Data Freshness", "Data Quality Grade", "Load Status", "Failure Reason if not rankable", "Rank Score", "Decision", "Reason",
        "Provider Used", "Data Quality", "Rows", "Latest Candle", "Ranking Result",
        "New Title", "Sentiment Bias", "Best Session For Entry", "Timeframe", "Latest Completed Broker Candle",
        "Higher-Standard Regime", "Higher-Standard Bias", "Less-Risky Bias",
        "Regime Probability", "Reliability", "Data Quality Grade", "Sample Count",
        "Transition Risk 3H", "Transition Risk 6H", "Transition Risk 24H",
        "Expected Return 3H", "Expected Return 12H", "Expected Return 24H", "Expected Value",
        "Technical Score", "Fundamental Score", "Combined Score", "Safety Veto",
        "Unexpected Status", "Calculation Status", "Evidence Source",
        "Best Session to Trade", "Best Session Score", "Current Session",
        "Current Session Suitability", "Highest-Impact Current News Title",
        "News Published Time", "News Impact Level", "News Currency/Pair Relevance",
        "News Surprise", "Absorption Status", "Absorption Score", "NLP Sentiment Bias",
        "NLP Sentiment Score", "Data-Mining Sentiment Bias", "Crowd Psychology Bias",
        "Technical/Fundamental Agreement", "News/Technical Conflict", "Protect/Block Reason",
        "Configured Selector Group(s)", "Loaded Status", "Provider", "API Status",
        "Twelve Key Pool Attempted", "Twelve Key Pool Error", "Twelve Attempted", "Twelve Error", "Cache Used", "Reload Eligible",
        "Load Data Quality", "Latest Price", "Genuine Candle Rows",
        "Required Minimum", "Preferred Rows", "Retry Count", "Validation Status",
        "Failure Code", "Publication Generation", "Run ID", "Snapshot Checksum Status",
        "Data Age", "Previous Valid Generation Used", "Optional Evidence Availability", "Notes",
    ]
    # Keep the public contract ordered and unique. Duplicate names such as
    # Timeframe/Data Quality Grade can make pandas return a DataFrame instead of
    # a Series for table["Timeframe"], which breaks Field 10 consumers/tests.
    required_contract = list(dict.fromkeys(required_contract))

    rename_contract = {
        "Rank": "Final Rank", "Completed Candle": "Latest Completed Broker Candle",
        "Higher Standard Regime": "Higher-Standard Regime", "Data Quality": "Data Quality Grade",
        "Expected Return 3H (%)": "Expected Return 3H", "Expected Return 12H (%)": "Expected Return 12H",
        "Expected Return 24H (%)": "Expected Return 24H", "Selector Group": "Configured Selector Group(s)",
        "Load Status": "Loaded Status", "Loaded Candles": "Genuine Candle Rows",
        "Minimum Candles": "Required Minimum", "Required Candles": "Preferred Rows",
    }
    for source, target in rename_contract.items():
        if source in base.columns and target not in base.columns:
            base[target] = base[source]

    for symbol in base.get("Symbol", pd.Series(dtype=object)).astype(str):
        evidence = load_evidence.get(normalize_symbol(symbol), {})
        mask = base["Symbol"].astype(str).map(normalize_symbol).eq(normalize_symbol(symbol))
        base.loc[mask, "Configured Selector Group(s)"] = evidence.get("Selector Groups") or "Not available"
        base.loc[mask, "Loaded Status"] = evidence.get("Load Status") or ("READY" if evidence.get("ok") else "WARNING")
        base.loc[mask, "Retry Count"] = int(evidence.get("retry_count") or 0)
        base.loc[mask, "Failure Code"] = evidence.get("failure_code") or ("—" if evidence.get("ok") else "VALIDATION_WARNING")
        base.loc[mask, "Data Age"] = evidence.get("data_age_seconds") if evidence.get("data_age_seconds") is not None else "Not available"
        base.loc[mask, "Notes"] = evidence.get("reason") or "Not available"
        cached_load = load_cache_20260708.get(normalize_symbol(symbol), {})
        if cached_load:
            provider_used = cached_load.get("provider_used") or base.loc[mask, "Provider"].iloc[0]
            base.loc[mask, "Provider Used"] = provider_used
            base.loc[mask, "Rows"] = cached_load.get("candle_count")
            base.loc[mask, "Latest Candle"] = cached_load.get("latest_candle_time")
            base.loc[mask, "API Status"] = cached_load.get("api_status")
            base.loc[mask, "Load Data Quality"] = cached_load.get("data_quality")
            existing_quality_20260708 = None
            if "Data Quality" in base.columns:
                existing_quality_series_20260708 = base.loc[mask, "Data Quality"]
                if existing_quality_series_20260708 is not None and not existing_quality_series_20260708.empty:
                    existing_quality_20260708 = existing_quality_series_20260708.iloc[0]
            base.loc[mask, "Data Quality"] = cached_load.get("data_quality") or existing_quality_20260708 or "UNKNOWN"
        news = news_bias_20260708.get(normalize_symbol(symbol), {})
        if news:
            base.loc[mask, "New Title"] = news.get("New Title")
            base.loc[mask, "Sentiment Bias"] = news.get("Sentiment Bias")
    if "Sample Count" in base.columns and "Rows" in base.columns:
        base["Sample Count"] = base["Sample Count"].where(base["Sample Count"].astype(str).str.lower().ne("not available"), base["Rows"])
    if "Final Score" in base.columns:
        base["Rank Score"] = base["Rank Score"].where(base["Rank Score"].notna(), base["Final Score"])
    elif "Combined Score" in base.columns:
        base["Rank Score"] = base["Rank Score"].where(base["Rank Score"].notna(), base["Combined Score"])
    # Current public Field 3/Table 3 contract requires a visible 0-100 scaled
    # score for every selected symbol.  It is exact-row only: no symbol borrows
    # another symbol's score.  If model scores are unavailable, use candle/status
    # evidence to show a conservative valid-data score or 0 for failed rows.
    def _scaled_score_20260708(row):
        for candidate in ("Rank Score", "Final Score", "Combined Score", "Technical Score", "Reliability", "Regime Probability"):
            if candidate in row.index:
                numeric = pd.to_numeric(pd.Series([row.get(candidate)]), errors="coerce").iloc[0]
                if pd.notna(numeric):
                    value = float(numeric)
                    if value <= 1.0:
                        value *= 100.0
                    return round(max(0.0, min(100.0, value)), 2)
        rows_value = pd.to_numeric(pd.Series([row.get("Rows", row.get("Candle Count", row.get("Sample Count")))]), errors="coerce").iloc[0]
        if pd.notna(rows_value) and float(rows_value) > 0:
            return round(max(25.0, min(88.0, 35.0 + float(rows_value) / 10.0)), 2)
        status = str(row.get("Loaded Status") or row.get("Load Status") or "").upper()
        if status in {"READY", "LOADED", "PUBLISHED", "CACHE_SUCCESS", "TWELVE_SUCCESS", "FCS_SUCCESS", "LOCAL_VALID_CACHE"}:
            return 50.0
        return 0.0
    base["Scaled Score"] = base.apply(_scaled_score_20260708, axis=1)
    if "Less-Risky Bias" in base.columns:
        base["Decision"] = base["Decision"].where(base["Decision"].astype(str).str.strip().ne("WAIT / REVIEW"), base["Less-Risky Bias"])
    if "Validation Evidence" in base.columns:
        base["Reason"] = base["Reason"].where(base["Reason"].astype(str).str.strip().ne("Not available"), base["Validation Evidence"])

    base["Publication Generation"] = manifest_generation if manifest_generation is not None else "Not available"
    base["Run ID"] = manifest_run_id
    base["Snapshot Checksum Status"] = "VALID" if (manifest.get("checksum") or manifest.get("snapshot_checksum")) else "Not available"
    base["Previous Valid Generation Used"] = "YES" if state.get("previous_valid_generation_used_20260707") else "NO"

    for column in required_contract:
        if column not in base.columns:
            base[column] = "Not available" if column in optional_columns or column not in {"Absorption Status", "NLP Sentiment Bias"} else "UNAVAILABLE"
    if "Timeframe" in base.columns:
        base["Timeframe"] = (
            base["Timeframe"]
            .replace({"": active_timeframe_20260708, "nan": active_timeframe_20260708, "NaN": active_timeframe_20260708, "None": active_timeframe_20260708, "<NA>": active_timeframe_20260708})
            .fillna(active_timeframe_20260708)
        )
        base.loc[base["Timeframe"].astype(str).str.strip().str.lower().isin({"", "nan", "none", "not available"}), "Timeframe"] = active_timeframe_20260708
    base["Absorption Status"] = base["Absorption Status"].map(lambda v: str(v).upper() if str(v).upper() in {"ABSORBED", "PARTIALLY_ABSORBED", "NOT_ABSORBED"} else "UNAVAILABLE")
    base["NLP Sentiment Bias"] = base["NLP Sentiment Bias"].map(lambda v: str(v).upper() if str(v).upper() in {"BUY", "SELL", "NEUTRAL"} else "UNAVAILABLE")
    if {"Highest-Impact Current News Title", "NLP Sentiment Score", "NLP Sentiment Bias"}.issubset(base.columns):
        missing_sentiment_evidence = (
            base["Highest-Impact Current News Title"].astype(str).str.strip().isin({"", "Not available", "nan", "None"})
            & base["NLP Sentiment Score"].astype(str).str.strip().isin({"", "Not available", "nan", "None", "UNAVAILABLE"})
            & base["NLP Sentiment Bias"].astype(str).str.upper().eq("NEUTRAL")
        )
        base.loc[missing_sentiment_evidence, "NLP Sentiment Bias"] = "UNAVAILABLE"
    base["Optional Evidence Availability"] = base.apply(
        lambda row: "AVAILABLE" if row.get("Highest-Impact Current News Title") not in {None, "", "Not available"} else "OPTIONAL_NEWS_UNAVAILABLE", axis=1
    )
    if "Ranking Result" not in base.columns or base["Ranking Result"].astype(str).str.lower().isin({"", "nan", "not available"}).all():
        base["Ranking Result"] = base.apply(lambda row: f"Rank {row.get('Final Rank')} | {row.get('Less-Risky Bias', row.get('Higher-Standard Bias', 'NEUTRAL'))}", axis=1)
    base["Best Session For Entry"] = base.apply(_best_session_for_entry_20260708, axis=1)
    usable_mask = pd.to_numeric(base.get("Rows", base.get("Genuine Candle Rows", pd.Series(dtype=object))), errors="coerce").fillna(0).gt(0)
    for column in base.columns:
        if base[column].dtype == object:
            base.loc[usable_mask, column] = base.loc[usable_mask, column].astype(str).str.replace("Insufficient data", "Usable loaded data", case=False, regex=False).str.replace("INSUFFICIENT_DATA", "USABLE_LOADED_DATA", case=False, regex=False)
    for column in required_contract:
        base[column] = base[column].where(base[column].notna() & base[column].astype(str).str.strip().ne(""), "Not available")

    # Stable rank/order: authoritative rank where available, then loaded order.
    base["__loaded_order"] = base["Symbol"].map({symbol: i for i, symbol in enumerate(symbols)})
    if "Final Rank" in base.columns:
        base["Final Rank"] = pd.to_numeric(base["Final Rank"], errors="coerce")
        base = base.sort_values(["Final Rank", "__loaded_order"], kind="mergesort", na_position="last")
    else:
        base = base.sort_values("__loaded_order", kind="mergesort")
        base["Final Rank"] = range(1, len(base) + 1)
    missing_rank = base["Final Rank"].isna()
    if missing_rank.any():
        numeric_rank = pd.to_numeric(base["Final Rank"], errors="coerce")
        start_rank = int(numeric_rank.max()) if numeric_rank.notna().any() else 0
        base.loc[missing_rank, "Final Rank"] = range(start_rank + 1, start_rank + 1 + int(missing_rank.sum()))
    base = base.drop(columns="__loaded_order").reset_index(drop=True)

    base = base.loc[:, ~base.columns.duplicated(keep="first")]
    base = base[base["Symbol"].astype(str).map(normalize_symbol).isin(symbols)]
    base = base.drop_duplicates(subset=["Symbol"], keep="first").reset_index(drop=True)
    base = base[[column for column in required_contract if column in base.columns] + [
        column for column in base.columns if column not in required_contract
    ]]
    base = base.loc[:, ~base.columns.duplicated(keep="first")]
    report = {
        "symbols": symbols,
        "row_count": int(len(base)),
        "loaded_count": int(sum(str(v).upper() in {"LOADED", "READY", "PUBLISHED", "CACHE_SUCCESS", "TWELVE_SUCCESS", "FCS_SUCCESS", "FINNHUB_SUCCESS", "LOCAL_VALID_CACHE", "EMERGENCY_CACHE_SUCCESS", "VALIDATED", "COMPLETED", "USABLE_LOADED_DATA"} for v in base.get("Loaded Status", []))),
        "higher_report": dict(higher_report) if isinstance(higher_report, Mapping) else {},
        "completion": dict(completion) if isinstance(completion, Mapping) else {},
        "parent_run_id": parent_run_id,
    }
    state["field10_consolidated_report_20260707"] = report
    state["field10_consolidated_table_20260707"] = base.copy(deep=False)
    return base, report


def _render_consolidated_field10_visual_20260707(frame: pd.DataFrame) -> None:
    """Render interactive Field 10 ranking visuals from the saved consolidated table."""
    if frame.empty or "Symbol" not in frame.columns:
        return
    columns = [column for column in frame.columns if column != "Notes"]
    default_metric = next((c for c in ("Final Rank", "Combined Score", "Rows", "Reliability", "Sentiment Bias") if c in columns), columns[0])
    metric = st.selectbox(
        "Ranking visualization column",
        columns,
        index=columns.index(default_metric) if default_metric in columns else 0,
        key="field10_consolidated_visual_metric_20260708",
        help="All visible Field 10 columns are available. Numeric columns draw symbol bars; text columns draw category counts and a symbol detail table.",
    )
    chart = frame[["Symbol", metric]].copy().drop_duplicates("Symbol")
    numeric = pd.to_numeric(chart[metric], errors="coerce")
    try:
        import plotly.express as px
        if numeric.notna().any():
            chart[metric] = numeric
            figure = px.bar(chart.dropna(subset=[metric]), x="Symbol", y=metric, title=f"{metric} by loaded symbol")
            figure.update_layout(xaxis_title="Symbol", yaxis_title=metric)
            st.plotly_chart(figure, use_container_width=True, key="field10_consolidated_interactive_chart_20260708")
        else:
            counts = chart[metric].astype(str).replace({"": "Not available", "nan": "Not available"}).value_counts().reset_index()
            counts.columns = [metric, "Symbol Count"]
            figure = px.bar(counts, x=metric, y="Symbol Count", title=f"{metric} category distribution")
            st.plotly_chart(figure, use_container_width=True, key="field10_consolidated_category_chart_20260708")
            st.dataframe(chart, use_container_width=True, hide_index=True)
        if "Final Rank" in frame.columns:
            ranking = frame[["Symbol", "Final Rank"]].copy().drop_duplicates("Symbol")
            ranking["Final Rank"] = pd.to_numeric(ranking["Final Rank"], errors="coerce")
            ranking = ranking.dropna(subset=["Final Rank"]).sort_values("Final Rank")
            if not ranking.empty:
                rank_fig = px.bar(ranking, x="Symbol", y="Final Rank", title="Multi-symbol final ranking order")
                rank_fig.update_layout(xaxis_title="Symbol", yaxis_title="Final Rank")
                st.plotly_chart(rank_fig, use_container_width=True, key="field10_multi_symbol_rank_visual_20260708")
    except Exception:
        if numeric.notna().any():
            chart[metric] = numeric
            st.bar_chart(chart.dropna(subset=[metric]).set_index("Symbol")[[metric]], use_container_width=True)
        else:
            st.dataframe(chart, use_container_width=True, hide_index=True)



def _field10_existing_columns(frame: pd.DataFrame, desired: Sequence[str]) -> list[str]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return []
    return [column for column in desired if column in frame.columns]


def _render_numeric_bar_chart_20260709(frame: pd.DataFrame, *, title: str, preferred_metrics: Sequence[str], key: str) -> None:
    """Small mobile-safe visualization; no extra ranking authority is created."""
    if not isinstance(frame, pd.DataFrame) or frame.empty or "Symbol" not in frame.columns:
        return
    metrics = []
    for column in preferred_metrics:
        if column in frame.columns and pd.to_numeric(frame[column], errors="coerce").notna().any():
            metrics.append(column)
    if not metrics:
        return
    selected = st.selectbox(title, metrics, index=0, key=key)
    chart = frame[["Symbol", selected]].copy().drop_duplicates("Symbol")
    chart[selected] = pd.to_numeric(chart[selected], errors="coerce")
    chart = chart.dropna(subset=[selected])
    if chart.empty:
        return
    try:
        import plotly.express as px
        figure = px.bar(chart, x="Symbol", y=selected, title=f"{selected} by symbol")
        figure.update_layout(xaxis_title="Symbol", yaxis_title=selected)
        st.plotly_chart(figure, use_container_width=True, key=f"{key}_plotly")
    except Exception:
        st.bar_chart(chart.set_index("Symbol")[[selected]], use_container_width=True)


def _render_text_distribution_chart_20260709(frame: pd.DataFrame, *, title: str, preferred_categories: Sequence[str], key: str) -> None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return
    categories = [c for c in preferred_categories if c in frame.columns]
    if not categories:
        return
    selected = st.selectbox(title, categories, index=0, key=key)
    counts = frame[selected].astype(str).replace({"": "Not available", "nan": "Not available", "None": "Not available"}).value_counts().reset_index()
    counts.columns = [selected, "Symbol Count"]
    if counts.empty:
        return
    try:
        import plotly.express as px
        figure = px.bar(counts, x=selected, y="Symbol Count", title=f"{selected} distribution")
        st.plotly_chart(figure, use_container_width=True, key=f"{key}_plotly")
    except Exception:
        st.bar_chart(counts.set_index(selected)[["Symbol Count"]], use_container_width=True)


def _compact_merged_authority_support_view_20260709(frame: pd.DataFrame) -> pd.DataFrame:
    columns = _field10_existing_columns(frame, (
        "Merged Surface", "Rank Star", "Rank", "Legacy Rank", "Symbol", "Authority Score",
        "Probability 100 Pip Move 4H", "Projected 4H Move Pips", "100 Pip 4H Priority", "100 Pip 4H Target Status",
        "Higher-Standard Regime Bias", "Higher-Standard Regime Bias Priority", "Transition Risk 6H", "Transition Safety 6H Priority",
        "Ranking Priority 1", "Ranking Priority 2", "Ranking Priority 3",
        "Reliability Grade", "Can Trust Rank?", "Trust Status", "Authority Placement",
        "Timeframe", "Completed Broker Candle", "Next Allowed Refresh", "Refresh Gate",
        "Stable Daily Bias", "Less-Risky Bias", "Final Bias Rule", "Entry Permission", "Risk Control Gate", "Whole-Day Bias Lock Confidence",
        "Regime Probability", "Transition Risk 1H", "Transition Risk 3H", "Transition Risk 12H", "Transition Risk 24H", "Transition Risk 36H",
        "Expected Return 3H", "Expected Return 4H", "Expected Return 6H", "Expected Return 12H", "Expected Return 24H", "Expected Return 36H",
        "Probability Profit 3H", "Probability Profit 4H", "Probability Profit 6H", "Probability Profit 12H",
        "Timing • Best Entry Session", "Timing • Session Score", "Timing • Entry Timing Permission", "Timing • News Sentiment Bias",
        "Timing • High-Impact Event", "Timing • Event-Risk Permission", "Timing • Absorption Status", "Timing • Impact Remaining",
        "Data Completeness %", "Event/Tail Safety %", "Calibration Quality %", "Unique Opportunity %",
        "Data Quality Grade", "Evidence Sample Size", "Provider Used", "Supporting Evidence Role",
        "Cross-Section Rank Reason", "Rank Freeze Reason", "publication_status", "Snapshot Hash",
    ))
    return frame[columns].copy() if columns else frame.copy()


def _compact_authority_view_20260709(frame: pd.DataFrame) -> pd.DataFrame:
    columns = _field10_existing_columns(frame, (
        "Rank Star", "Rank", "Legacy Rank", "Symbol", "Authority Score",
        "Probability 100 Pip Move 4H", "Projected 4H Move Pips", "100 Pip 4H Priority", "100 Pip 4H Target Status",
        "Higher-Standard Regime Bias", "Higher-Standard Regime Bias Priority", "Transition Safety 6H Priority",
        "Reliability Grade", "Can Trust Rank?", "Trust Status", "Authority Placement",
        "Timeframe", "Completed Broker Candle", "Next Allowed Refresh", "Refresh Gate",
        "Stable Daily Bias", "Less-Risky Bias", "Entry Permission", "Risk Control Gate", "Whole-Day Bias Lock Confidence",
        "Data Completeness %", "Transition Safety %", "Event/Tail Safety %", "Calibration Quality %", "Unique Opportunity %",
        "Regime Probability", "Transition Risk 1H", "Transition Risk 3H", "Transition Risk 6H", "Transition Risk 12H", "Transition Risk 24H", "Transition Risk 36H",
        "Expected Return 1H", "Expected Return 3H", "Expected Return 6H", "Expected Return 12H", "Expected Return 24H", "Expected Return 36H",
        "Probability Profit 1H", "Probability Profit 3H", "Probability Profit 6H", "Probability Profit 12H",
        "Data Quality Grade", "Evidence Sample Size", "Provider Used", "Cross-Section Rank Reason", "Rank Freeze Reason", "publication_status", "Snapshot Hash",
    ))
    return frame[columns].copy() if columns else frame.copy()


def _compact_support_view_20260709(frame: pd.DataFrame) -> pd.DataFrame:
    columns = _field10_existing_columns(frame, (
        "Evidence Rank", "Symbol", "Timeframe", "Completed Broker Candle", "Next Allowed Refresh", "Refresh Gate",
        "Authority Daily Bias", "Probability 100 Pip Move 4H", "Projected 4H Move Pips", "100 Pip 4H Target Status", "Entry Timing Permission", "Best Entry Session", "Session Score",
        "News Sentiment Bias", "High-Impact Event", "Event-Risk Permission", "Absorption Status", "Impact Remaining",
        "Transition Risk 1H", "Transition Risk 3H", "Transition Risk 6H", "Transition Risk 12H", "Transition Risk 24H", "Transition Risk 36H",
        "Probability Profit 1H", "Probability Profit 3H", "Probability Profit 6H", "Probability Profit 12H",
        "Expected Return 1H", "Expected Return 3H", "Expected Return 6H", "Expected Return 12H", "Expected Return 24H", "Expected Return 36H",
        "Data Quality Grade", "Evidence Sample Size", "Provider Used", "Trust Role", "Can Override Authority Bias?",
        "snapshot_hash", "publication_status",
    ))
    return frame[columns].copy() if columns else frame.copy()


def _render_restored_field3_field10_section_20260709(
    state: MutableMapping[str, Any],
    table: pd.DataFrame,
    report: Mapping[str, Any],
    *,
    authority_snapshot: Mapping[str, Any] | None = None,
    expanded: bool = False,
) -> None:
    """Restore the legacy combined evidence section without creating authority drift.

    This is display-only and exact-symbol only.  It intentionally reuses the
    already-built table from render_field10_content, so opening it does not call
    an API, rebuild Field 10, or change the H4 locked rank snapshot.
    """
    snapshot = authority_snapshot if isinstance(authority_snapshot, Mapping) else {}
    with st.expander(
        "Field 3 Higher-Standard Multi-Symbol Bias + Consolidated Field 10 — All Loaded Settings Symbols",
        expanded=expanded,
    ):
        st.caption(
            "Restored as supporting exact-symbol evidence. Use it to compare Field 3 Higher-Standard bias, load validation, "
            "provider evidence, news/session/crowd support, and consolidated diagnostics. It cannot override the trusted "
            "Field 10 Unified Institutional Daily Rank Authority above."
        )
        cards = st.columns(4)
        cards[0].metric("Visible Symbols", int(report.get("row_count") or 0))
        cards[1].metric("Loaded Now", int(report.get("loaded_count") or 0))
        completion = report.get("completion") if isinstance(report.get("completion"), Mapping) else {}
        cards[2].metric("Validated Rows", int(completion.get("field10_row_count") or 0))
        cards[3].metric("Trust Role", "SUPPORTING ONLY")

        if snapshot:
            st.info(
                f"Authority sync: {snapshot.get('publication_status', 'CHECK')} · "
                f"Timeframe: {snapshot.get('timeframe', 'H4')} · "
                f"Completed candle: {snapshot.get('completed_broker_candle', 'UNAVAILABLE')} · "
                f"Snapshot: {snapshot.get('snapshot_hash', 'UNAVAILABLE')}"
            )

        if not isinstance(table, pd.DataFrame) or table.empty:
            st.warning("No loaded or completed exact-symbol rows are available yet. Load symbols in Settings, then click Super Quick.")
            return

        view = table.copy(deep=False)
        _display_field10_table(
            view,
            height=min(820, 80 + 40 * max(1, min(len(view), 18))),
            pin_expected_returns=True,
            key="field10_consolidated_exact_symbol_table_20260709_restored",
            allow_cards=False,
        )
        st.markdown("#### Consolidated Multi-Symbol Visualization")
        _render_consolidated_field10_visual_20260707(view)

        st.download_button(
            "⬇ Consolidated Field 3 + Field 10 CSV",
            data=_csv_bytes(view),
            file_name=f"field3_field10_consolidated_{report.get('parent_run_id') or 'latest'}.csv",
            mime="text/csv",
            use_container_width=True,
            key="field10_consolidated_download_20260709_restored",
        )
        csv_data = state.get("adx_current_result_csv_bytes_20260708")
        if isinstance(csv_data, (bytes, bytearray)) and csv_data:
            st.download_button(
                "Download current full result CSV",
                data=bytes(csv_data),
                file_name=f"adx_current_full_result_{report.get('parent_run_id') or 'latest'}.csv",
                mime="text/csv",
                use_container_width=True,
                key="field10_current_result_download_csv_20260709_restored",
            )

def render_field10_content(state: MutableMapping[str, Any] | None = None) -> None:
    """Render one consolidated, closed-first multi-symbol Field 3/Field 10 surface."""
    state = state if state is not None else st.session_state
    state["field10_table_render_counter_20260705"] = 0
    # Lunch is a read-only projection.  The Settings run is the only caller
    # allowed to build and publish the authority.  Opening Field 10 now reads
    # the exact saved snapshot and never invokes the connector or fusion path.
    try:
        from core.field10_unified_authority_20260709 import load_saved_field10_authority
        saved_authority = load_saved_field10_authority(state)
    except Exception as exc:
        saved_authority = None
        state["field10_saved_authority_load_error_20260717"] = f"{type(exc).__name__}: {exc}"
    if isinstance(saved_authority, Mapping):
        table = saved_authority.get("table") if isinstance(saved_authority.get("table"), pd.DataFrame) else pd.DataFrame()
        snapshot = saved_authority.get("snapshot") if isinstance(saved_authority.get("snapshot"), Mapping) else {}
        report = {
            "symbols": snapshot.get("ordered_symbol_universe") or [],
            "row_count": len(table), "loaded_count": snapshot.get("loaded_symbol_count", 0),
            "completion": {"field10_row_count": len(table)},
            "parent_run_id": snapshot.get("parent_run_id", ""),
        }
    else:
        table = state.get("field10_consolidated_table_20260707") if isinstance(state.get("field10_consolidated_table_20260707"), pd.DataFrame) else pd.DataFrame()
        report = state.get("field10_consolidated_report_20260707") if isinstance(state.get("field10_consolidated_report_20260707"), Mapping) else {"row_count": len(table), "loaded_count": 0, "completion": {"field10_row_count": len(table)}}
    if table.empty:
        st.info("No saved Field 10 authority snapshot matches the selected symbols, timeframe and completed candle. Run Settings once, then reopen Lunch.")
        return
    # Restored supporting section: "Field 3 Higher-Standard Multi-Symbol Bias + Consolidated Field 10 — All Loaded Settings Symbols".
    # The helper renders the exact-symbol evidence table with allow_cards=False and does not recalculate Field 10.
    # Legacy Streamlit key preserved for compatibility: field10_consolidated_exact_symbol_table_20260707.
    # Visual helper preserved: _render_consolidated_field10_visual_20260707.

    try:
        from core.field10_unified_authority_20260709 import (
            UNIFIED_TABLE_KEY, UNIFIED_SNAPSHOT_KEY,
            SUPPORTING_TABLE_KEY, MERGED_TABLE_KEY,
        )
        from core.view_model_sync import render_sync_status_panel
        from ui.color_system import style_mobile_table
        from ui.mobile_export_panel import render_mobile_export_panel

        authority = saved_authority if isinstance(saved_authority, Mapping) else {
            "table": table,
            "supporting": state.get(SUPPORTING_TABLE_KEY),
            "merged": state.get(MERGED_TABLE_KEY),
            "snapshot": state.get(UNIFIED_SNAPSHOT_KEY),
            "why_trust": (state.get(UNIFIED_SNAPSHOT_KEY) or {}).get("why_trust", {}) if isinstance(state.get(UNIFIED_SNAPSHOT_KEY), Mapping) else {},
        }
        trusted = authority.get("table")
        supporting = authority.get("supporting")
        merged = authority.get("merged")
        if not isinstance(supporting, pd.DataFrame):
            supporting = state.get(SUPPORTING_TABLE_KEY)
        if not isinstance(merged, pd.DataFrame):
            merged = state.get(MERGED_TABLE_KEY)
        if not isinstance(merged, pd.DataFrame) or merged.empty:
            merged = trusted
        why = authority.get("why_trust") if isinstance(authority.get("why_trust"), Mapping) else {}
        snapshot = authority.get("snapshot") if isinstance(authority.get("snapshot"), Mapping) else state.get(UNIFIED_SNAPSHOT_KEY)
        snapshot = snapshot if isinstance(snapshot, Mapping) else {}

        st.caption(
            "Field 10 now displays ONE first merged open/close surface: trusted daily authority rank + supporting entry timing evidence. "
            "Final direction is BUY/SELL only; WAIT is removed. Ranking priority is 100-pip/4H probability, Higher-Standard regime bias, then 6H transition risk."
        )

        with st.expander("✅📊 Open / Close — Field 10 Unified Institutional Daily Rank Authority + Supporting Evidence / Entry Timing Rank", expanded=True):
            st.caption(
                "TRUST THIS FIRST MERGED TABLE for final rank, Top 4, BUY/SELL direction, 100-pip/4H probability, "
                "Higher-Standard regime agreement, transition risk 6H, and entry-timing evidence. "
                "Supporting evidence explains timing/risk only; it cannot create a separate competing rank."
            )
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Publication", str(why.get("publication status") or snapshot.get("publication_status") or "CHECK"))
            c2.metric("Bias Options", "BUY / SELL")
            c3.metric("Loaded / Failed", f"{why.get('loaded symbols', snapshot.get('loaded_symbol_count', 0))} / {why.get('failed symbols', snapshot.get('failed_symbol_count', 0))}")
            c4.metric("Refresh Gate", str(why.get("refresh gate") or "SELECTED_CANDLE_END"))
            try:
                if isinstance(trusted, pd.DataFrame) and not trusted.empty and "Can Trust Rank?" in trusted.columns:
                    trust_counts = trusted["Can Trust Rank?"].astype(str).value_counts().to_dict()
                    st.caption(
                        f"Trust summary: YES={trust_counts.get('YES', 0)} · CAUTION={trust_counts.get('CAUTION', 0)} · NO={trust_counts.get('NO', 0)} · "
                        f"Method: {why.get('ranking method', 'Governed Authority Score v3')}"
                    )
            except Exception:
                pass
            st.info(
                f"Completed candle: {why.get('broker candle') or snapshot.get('completed_broker_candle') or 'UNAVAILABLE'} · "
                f"Next allowed refresh: {why.get('next allowed refresh') or 'UNAVAILABLE'} · "
                f"Snapshot: {why.get('snapshot hash') or snapshot.get('snapshot_hash') or 'UNAVAILABLE'}"
            )
            st.success(
                "Rank order priority: ① Probability 100 Pip Move 4H  →  ② Higher-Standard Regime Bias Priority  →  ③ lowest Transition Risk 6H. "
                "WAIT is not published as a bias; caution is shown through gates and trust status."
            )
            if isinstance(merged, pd.DataFrame) and not merged.empty:
                merged_view = _compact_merged_authority_support_view_20260709(merged)
                st.dataframe(
                    style_mobile_table(merged_view),
                    use_container_width=True,
                    hide_index=True,
                    height=min(820, 90 + 38 * max(1, min(len(merged_view), 18))),
                )
                _render_numeric_bar_chart_20260709(
                    merged_view,
                    title="Merged authority visualization metric",
                    preferred_metrics=(
                        "Probability 100 Pip Move 4H", "Projected 4H Move Pips", "100 Pip 4H Priority",
                        "Higher-Standard Regime Bias Priority", "Transition Risk 6H", "Transition Safety 6H Priority",
                        "Authority Score", "Regime Probability", "Whole-Day Bias Lock Confidence", "Session Score", "Impact Remaining",
                        "Data Completeness %", "Evidence Sample Size",
                    ),
                    key="field10_merged_authority_visual_metric_20260709",
                )
                _render_text_distribution_chart_20260709(
                    merged_view,
                    title="Merged authority category visualization",
                    preferred_categories=(
                        "Stable Daily Bias", "Less-Risky Bias", "100 Pip 4H Target Status", "Higher-Standard Regime Bias",
                        "Reliability Grade", "Can Trust Rank?", "Trust Status", "Entry Permission", "Data Quality Grade",
                        "Best Entry Session", "Event-Risk Permission", "Absorption Status", "publication_status",
                    ),
                    key="field10_merged_authority_category_metric_20260709",
                )
                with st.expander("Merged raw supporting details inside the same Field 10 section", expanded=False):
                    if isinstance(supporting, pd.DataFrame) and not supporting.empty:
                        support_view = _compact_support_view_20260709(supporting)
                        st.dataframe(
                            style_mobile_table(support_view),
                            use_container_width=True,
                            hide_index=True,
                            height=min(760, 90 + 38 * max(1, min(len(support_view), 18))),
                        )
                    else:
                        st.info("Supporting evidence table is waiting for the unified authority snapshot.")
            else:
                st.warning("Merged Field 10 authority table is empty. Load selected symbols and run calculation first.")
            with st.expander("Why this first merged table is trusted", expanded=False):
                st.json(why)


        _render_restored_field3_field10_section_20260709(
            state,
            table,
            report,
            authority_snapshot=snapshot,
            expanded=False,
        )

        render_sync_status_panel(st, state)
        render_mobile_export_panel(st, state)
        return
    except Exception as authority_exc_20260709:
        st.warning(f"Field 10 unified two-table authority layer unavailable: {type(authority_exc_20260709).__name__}: {authority_exc_20260709}")
        st.caption("Fallback diagnostic tables below are not authority tables. Trust only the unified authority after this error is repaired.")

    try:
        from core.institutional_quant_layer_20260708 import render_institutional_field10_panel
        with st.expander("🏛️ Open / Close — Institutional Field 10 Quant Ranking + News/NLP Evidence", expanded=True):
            render_institutional_field10_panel(state)
    except Exception as institutional_exc_20260708:
        st.caption(f"Institutional Field 10 panel unavailable: {type(institutional_exc_20260708).__name__}")

    _render_restored_field3_field10_section_20260709(
        state,
        table,
        report,
        authority_snapshot={},
        expanded=True,
    )

def _field10_part4_diagnostic_table(summary: pd.DataFrame, daily: pd.DataFrame, hourly: pd.DataFrame) -> pd.DataFrame:
    diagnostic = summary.copy() if isinstance(summary, pd.DataFrame) else pd.DataFrame()
    if diagnostic.empty and isinstance(daily, pd.DataFrame):
        diagnostic = daily.copy()
    elif not diagnostic.empty and isinstance(daily, pd.DataFrame) and not daily.empty and "Symbol" in diagnostic and "Symbol" in daily:
        extra = [
            column for column in (
                "Symbol", "Lock Status", "Locked At", "Last Reviewed", "Next Review",
                "Transition Risk 24H", "Expected Return 12H (%)",
                "Expected Return 24H (%)", "Expected Return 36H (%)", "Higher Reliability",
            ) if column in daily.columns
        ]
        if len(extra) > 1:
            diagnostic = diagnostic.merge(daily[extra].drop_duplicates("Symbol"), on="Symbol", how="left", suffixes=("", " Daily"))
    if diagnostic.empty and isinstance(hourly, pd.DataFrame) and not hourly.empty:
        diagnostic = hourly.tail(60).copy()
    diagnostic = diagnostic.drop(
        columns=[column for column in diagnostic.columns if column in {"Rank", "Rank Score", "Rank Grade", "Rank Reason"}],
        errors="ignore",
    )
    return diagnostic.reset_index(drop=True) if isinstance(diagnostic, pd.DataFrame) else pd.DataFrame()


def render_field10_dinner_remainder(state: MutableMapping[str, Any] | None = None) -> None:
    """Render Field 10 Part 4 in Dinner as one table and one visualization."""
    state = state if state is not None else st.session_state
    universe = recover_symbol_universe(state)
    selected = normalize_selected(universe.get("selected_symbols") or state.get(SELECTED_KEY) or [])
    main = normalize_symbol(universe.get("main_symbol") or (selected[0] if selected else "EURUSD"))
    parent_run_id = str(universe.get("parent_run_id") or state.get("multi_symbol_parent_run_id_20260701") or "")
    active = normalize_symbol(universe.get("active_symbol") or state.get(ACTIVE_KEY) or state.get(DISPLAY_SYMBOL_KEY) or main)
    tables = load_field10_tables(state, parent_run_id=parent_run_id, symbol=active)
    summary = tables.get("summary", pd.DataFrame())
    daily = tables.get("daily", pd.DataFrame())
    hourly = tables.get("hourly", pd.DataFrame())
    diagnostic = _field10_part4_diagnostic_table(summary, daily, hourly)

    with st.expander("Open / Close — Field 10 Part 4: Consolidated Remainder", expanded=False):
        st.caption(
            "Moved from Lunch. Legacy diagnostics, remaining Field 10 tables and saved calculation resource data are consolidated here "
            "from the existing Field 10 store; no connector or recalculation is started."
        )
        cols = st.columns(4)
        cols[0].metric("Parent Run", parent_run_id[:20] or "-")
        cols[1].metric("Active Symbol", active)
        cols[2].metric("Summary Rows", int(len(summary)) if isinstance(summary, pd.DataFrame) else 0)
        cols[3].metric("Hourly Rows", int(len(hourly)) if isinstance(hourly, pd.DataFrame) else 0)
        if diagnostic.empty:
            st.info("No saved Field 10 remainder data is available for this generation.")
            return
        query = st.text_input(
            "Search Field 10 Part 4 consolidated table",
            key="dinner_field10_part4_search_20260706",
            placeholder="symbol, source, lock, quality, reliability, status...",
        )
        view = _search(diagnostic, query)
        _display_field10_table(view, height=min(560, 48 + 35 * max(1, min(len(view), 14))), key="dinner_field10_part4_table_20260706")

        chart_frame = diagnostic.copy()
        if "Symbol" in chart_frame.columns:
            numeric_columns = [
                column for column in (
                    "Final Score", "Comparative Rank Score", "Institutional Morning Score",
                    "Calibrated Reliability", "Higher Reliability", "Transition Risk 24H",
                    "Expected Return 24H (%)",
                )
                if column in chart_frame.columns and pd.to_numeric(chart_frame[column], errors="coerce").notna().any()
            ]
            if numeric_columns:
                chart = chart_frame[["Symbol", *numeric_columns]].copy()
                for column in numeric_columns:
                    chart[column] = pd.to_numeric(chart[column], errors="coerce")
                chart = chart.dropna(how="all", subset=numeric_columns).drop_duplicates("Symbol").set_index("Symbol")
                if not chart.empty:
                    st.markdown("##### Field 10 Part 4 Consolidated Visualization")
                    st.bar_chart(chart, use_container_width=True)
        resource = state.get(LAST_RESOURCE_KEY)
        resource = resource if isinstance(resource, Mapping) else (state.get(MANIFEST_KEY) or {}).get("resource_report") if isinstance(state.get(MANIFEST_KEY), Mapping) else {}
        if isinstance(resource, Mapping) and resource:
            st.caption(
                f"Resource audit: {float(resource.get('total_elapsed_seconds') or 0):.2f}s total, "
                f"{float(resource.get('rss_delta_mb') or 0):.2f} MB RSS delta, heat proxy {resource.get('heat_proxy') or 'UNKNOWN'}."
            )


def render_field10_gate(state: MutableMapping[str, Any] | None = None) -> None:
    """Backward-compatible optional gate for legacy callers.

    The authoritative Lunch layout now places Field 10 inside the main field
    selector.  This wrapper remains for old imports and does not run unless its
    legacy toggle is explicitly opened.
    """
    state = state if state is not None else st.session_state
    st.markdown("---")
    if not st.toggle(FIELD10_LABEL, value=False, key="lunch_field10_gate_20260701"):
        return
    render_field10_content(state)


__all__ = ["FIELD10_LABEL", "render_field10_content", "render_field10_dinner_remainder", "render_field10_gate"]
