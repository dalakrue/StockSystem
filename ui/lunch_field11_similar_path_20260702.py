"""Lunch Field 11 — Similar-Market Path Simulator UI.

The renderer is local-state only and reads prepared, identity-matched artifacts.
It never mutates the global Lunch/Settings symbol and never recalculates Fields 1-10.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.field11_similar_path_simulator_20260702 import (
    Field11Selection,
    load_index_manifest,
    load_validation_history,
    read_index_frame,
    resolve_field11_identity,
    simulate_field11,
    validate_index_identity,
)

FIELD11_LABEL = "11. Open / Close — Similar Path Simulator"
_LOCAL_PREFIX = "field11_local_20260702_"


def _reset_local_controls() -> None:
    for key in list(st.session_state.keys()):
        if str(key).startswith(_LOCAL_PREFIX):
            st.session_state.pop(key, None)
    st.session_state.pop("field11_last_result_20260702", None)


def _safe_rank_control(current: pd.DataFrame) -> tuple[int | None, int | None]:
    if current.empty or "Daily Rank" not in current.columns:
        st.caption("Field 10 rank filter unavailable for this snapshot.")
        return None, None
    ranks = pd.to_numeric(current["Daily Rank"], errors="coerce").dropna().astype(int)
    if ranks.empty:
        st.caption("No eligible frozen ranks are available.")
        return None, None
    low, high = int(ranks.min()), int(ranks.max())
    if low == high:
        st.text_input("Field 10 rank", value=str(low), disabled=True, key=f"{_LOCAL_PREFIX}rank_fixed")
        return low, high
    value = st.slider(
        "Field 10 frozen-rank range", min_value=low, max_value=high, value=(low, high),
        key=f"{_LOCAL_PREFIX}rank_range",
    )
    return int(value[0]), int(value[1])


def _normalise_cached_analogues(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    if "Match Rank" in frame.columns:
        return frame
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        component = row.get("component_json") if isinstance(row.get("component_json"), Mapping) else {}
        outcome = row.get("outcome_json") if isinstance(row.get("outcome_json"), Mapping) else {}
        candle = str(row.get("historical_broker_candle") or "")
        endpoint = outcome.get("endpoint_pips")
        rows.append({
            "Match Rank": row.get("match_rank"),
            "Historical Broker Date": candle[:10],
            "Historical Broker Hour": candle[11:16],
            "Source Symbol": row.get("historical_symbol"),
            "Overall Similarity": row.get("overall_similarity"),
            "Final Weight": row.get("final_weight"),
            "Shape Similarity": component.get("shape_similarity"),
            "Technical Similarity": component.get("technical_similarity"),
            "Regime Similarity": component.get("regime_similarity"),
            "Session Similarity": component.get("session_similarity"),
            "Volatility Similarity": component.get("volatility_similarity"),
            "Sentiment Similarity": component.get("sentiment_similarity"),
            "Liquidity Similarity": component.get("liquidity_similarity"),
            "Cross-Market Similarity": component.get("cross_market_similarity"),
            "Future Direction": "BUY" if isinstance(endpoint, (int, float)) and endpoint > 0 else ("SELL" if isinstance(endpoint, (int, float)) and endpoint < 0 else "WAIT"),
            "Endpoint Pips": endpoint,
            "Maximum Favorable Pips": outcome.get("mfe_pips"),
            "Maximum Adverse Pips": outcome.get("mae_pips"),
            "Scenario Cluster": row.get("scenario_cluster"),
            "Inclusion Status": row.get("inclusion_status"),
            "Rejection Reason": row.get("rejection_reason"),
            "Canonical Source ID": row.get("analogue_id"),
        })
    return pd.DataFrame(rows)


def _render_metrics(summary: Mapping[str, Any]) -> None:
    compact = [
        ("Symbol", summary.get("selected_symbol")),
        ("Horizon", f"{summary.get('selected_horizon_hours')}H"),
        ("Dominant Scenario", summary.get("dominant_scenario")),
        ("Simulator Grade", summary.get("simulator_reliability_grade")),
        ("Effective Sample Size", summary.get("effective_sample_size")),
        ("Median Endpoint", f"{float(summary.get('weighted_median_endpoint_pips') or 0):.2f} pips"),
        ("Historical Outcome Range", f"{float(summary.get('endpoint_p10') or 0):.2f} to {float(summary.get('endpoint_p90') or 0):.2f} pips"),
        ("Drift Status", summary.get("drift_status")),
    ]
    for start in range(0, len(compact), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, compact[start:start + 4]):
            column.metric(label, value if value not in (None, "") else "UNAVAILABLE")

    with st.expander("Open / Close — Full simulator metrics", expanded=False):
        full = [
            ("Source Broker Candle", summary.get("source_broker_candle")),
            ("Canonical Run ID", summary.get("canonical_run_id")),
            ("Snapshot Hash", str(summary.get("snapshot_hash") or "")[:28]),
            ("Candidate Count", summary.get("candidate_count")),
            ("Qualified Analogues", summary.get("qualified_analogue_count")),
            ("Rejected Analogues", summary.get("rejected_analogue_count")),
            ("Best Similarity", f"{float(summary.get('best_match_similarity') or 0):.2f}%"),
            ("Median Similarity", f"{float(summary.get('median_similarity') or 0):.2f}%"),
            ("Weighted Mean Similarity", f"{float(summary.get('weighted_mean_similarity') or 0):.2f}%"),
            ("Dominant Weighted Frequency", f"{float(summary.get('dominant_weighted_historical_frequency') or 0):.2f}%"),
            ("Median MFE", f"{float(summary.get('median_mfe_pips') or 0):.2f} pips"),
            ("Median MAE", f"{float(summary.get('median_mae_pips') or 0):.2f} pips"),
            ("Direction Agreement", f"{float(summary.get('direction_agreement') or 0):.2f}%"),
            ("Regime Match Quality", f"{float(summary.get('regime_match_quality') or 0):.2f}%"),
            ("Session Match Quality", f"{float(summary.get('session_match_quality') or 0):.2f}%"),
            ("Sentiment Match Quality", f"{float(summary.get('sentiment_match_quality') or 0):.2f}%"),
            ("Path Dispersion", summary.get("path_dispersion")),
            ("Data Quality", summary.get("data_quality_grade")),
            ("Feature Coverage", f"{float(summary.get('feature_coverage') or 0):.2f}%"),
            ("Coverage Health", summary.get("coverage_health")),
        ]
        table = pd.DataFrame(full, columns=["Metric", "Value"])
        st.dataframe(table, use_container_width=True, hide_index=True, height=520)


def _render_path_chart(summary: Mapping[str, Any], scenarios: list[Mapping[str, Any]]) -> None:
    median = np.asarray(summary.get("weighted_median_path_pips") or [], dtype=float)
    if median.size == 0:
        st.info("No historical path is available for chart rendering.")
        return
    x = list(range(len(median)))
    figure = go.Figure()
    low80 = np.asarray(summary.get("central_80_low") or [], dtype=float)
    high80 = np.asarray(summary.get("central_80_high") or [], dtype=float)
    low50 = np.asarray(summary.get("central_50_low") or [], dtype=float)
    high50 = np.asarray(summary.get("central_50_high") or [], dtype=float)
    if len(low80) == len(x) and len(high80) == len(x):
        figure.add_trace(go.Scatter(x=x, y=high80, mode="lines", line={"width": 0}, hoverinfo="skip", showlegend=False))
        figure.add_trace(go.Scatter(x=x, y=low80, mode="lines", line={"width": 0}, fill="tonexty", name="Central 80% historical band"))
    if len(low50) == len(x) and len(high50) == len(x):
        figure.add_trace(go.Scatter(x=x, y=high50, mode="lines", line={"width": 0}, hoverinfo="skip", showlegend=False))
        figure.add_trace(go.Scatter(x=x, y=low50, mode="lines", line={"width": 0}, fill="tonexty", name="Central 50% historical band"))
    figure.add_trace(go.Scatter(x=x, y=median, mode="lines+markers", name="Weighted median analogue path"))
    for scenario in scenarios[:3]:
        path = np.asarray(scenario.get("median_path_pips") or [], dtype=float)
        if len(path) == len(x):
            figure.add_trace(go.Scatter(
                x=x, y=path, mode="lines", name=f"{scenario.get('scenario_name')} ({float(scenario.get('weighted_historical_frequency') or 0):.1f}% weighted analogues)",
            ))
    figure.add_vline(x=0, line_dash="dash", annotation_text="Simulation start")
    figure.add_hline(y=0, line_dash="dot")
    figure.update_layout(
        title="Conditional Historical-Analogue Path Projector",
        xaxis_title="Future completed-bar step",
        yaxis_title="Rebased path (pips from source close)",
        hovermode="x unified",
        height=520,
        margin={"l": 30, "r": 20, "t": 60, "b": 35},
        legend={"orientation": "h", "y": -0.22},
    )
    st.plotly_chart(figure, use_container_width=True, key="field11_conditional_path_projector_20260702")
    st.caption("The displayed frequencies describe qualified weighted historical analogues. They are not guaranteed future probabilities.")


def _render_scenario_table(scenarios: list[Mapping[str, Any]]) -> None:
    if not scenarios:
        return
    rows = []
    for scenario in scenarios:
        rows.append({
            "Scenario": scenario.get("scenario_name"),
            "Analogue Count": scenario.get("supporting_analogue_count"),
            "Effective Sample Size": scenario.get("supporting_effective_sample_size"),
            "Weighted Historical Frequency": scenario.get("weighted_historical_frequency"),
            "Median Endpoint Pips": scenario.get("median_endpoint_pips"),
            "Endpoint P10": scenario.get("endpoint_p10"),
            "Endpoint P25": scenario.get("endpoint_p25"),
            "Endpoint P75": scenario.get("endpoint_p75"),
            "Endpoint P90": scenario.get("endpoint_p90"),
            "Scenario Stability": scenario.get("scenario_stability"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=min(320, 45 + 35 * len(rows)))


def _render_field11_fallback(state: MutableMapping[str, Any], identity: Mapping[str, Any], guard: Mapping[str, Any]) -> None:
    """Always expose a useful, honest persisted summary when the analogue index is absent."""
    errors = list(guard.get("errors") or identity.get("errors") or [])
    state["field11_last_guard_errors_20260705"] = errors
    try:
        from core.complete_repair_20260705 import log_internal_error
        incident = log_internal_error("field11.index_guard", RuntimeError("; ".join(map(str, errors)) or "index unavailable"))
    except Exception:
        incident = "FIELD11-INDEX"
    current = identity.get("field10_current") if isinstance(identity.get("field10_current"), pd.DataFrame) else pd.DataFrame()
    active = str(state.get("lunch_active_symbol_20260704") or state.get("lunch_display_symbol_20260702") or identity.get("symbol") or "").upper()
    row = pd.DataFrame()
    if not current.empty and "Symbol" in current.columns:
        row = current.loc[current["Symbol"].astype(str).str.upper().eq(active)].head(1)
    cards = st.columns(3)
    cards[0].metric("Calculation Status", "PERSISTED FALLBACK")
    cards[1].metric("Symbol / Timeframe", f"{active or '-'} / {identity.get('timeframe') or state.get('timeframe') or 'H1'}")
    cards[2].metric("Data Quality", (row.iloc[0].get("Data Quality Grade") if not row.empty else None) or "LOW — INDEX MISSING")
    if not row.empty:
        visible = [column for column in (
            "Daily Rank", "Symbol", "Stable Daily Bias", "Less-Risky Bias", "Higher Standard Regime",
            "Calibrated Reliability", "Data Quality Grade", "Transition Risk 6H", "Expected Return 12H (%)",
            "Expected Return 24H (%)", "Expected Return 36H (%)", "Completed Broker Candle",
        ) if column in row.columns]
        st.dataframe(row[visible], use_container_width=True, hide_index=True)
    st.warning(
        "The historical analogue index is not readable for this completed publication. "
        "The persisted Field 10 identity remains visible and no market value was fabricated."
    )
    st.caption(f"Support reference: {incident}. A future completed Settings run will rebuild the bounded index automatically.")
    payload = {
        "status": "PERSISTED_FALLBACK", "symbol": active,
        "timeframe": identity.get("timeframe") or state.get("timeframe"),
        "run_id": identity.get("canonical_run_id") or identity.get("parent_run_id"),
        "snapshot_hash": identity.get("snapshot_hash"), "support_reference": incident,
        "field10_row": row.to_dict(orient="records") if not row.empty else [],
    }
    state["field11_structured_context_20260705"] = payload
    st.download_button(
        "Copy / Export Field 11 Fallback JSON",
        data=__import__("json").dumps(payload, indent=2, default=str),
        file_name=f"field11_{active or 'snapshot'}_fallback.json",
        mime="application/json", use_container_width=True,
        key="field11_fallback_export_20260705",
    )


def render_field11_content(state: MutableMapping[str, Any] | None = None) -> None:
    state = state if state is not None else st.session_state
    st.markdown("### Field 11 — Similar-Market Path Simulator and Conditional Scenario Projector")
    selected_symbol = str(state.get("field11_selected_symbol_20260709") or state.get("canonical_display_symbol_20260709") or "").upper()
    selected_horizon = "1H"
    try:
        from core.canonical_symbol_selection_20260709 import render_selector, filter_frame_for_symbol, active_symbol
        selected_symbol, selected_horizon, _ = render_selector(st, state, surface="field11", title="Field 11 Multi-Symbol Selector — Load Similar Path", show_horizon=True)
        selected_symbol = selected_symbol or active_symbol(state, surface="field11")
    except Exception as selector_exc_20260709:
        st.caption(f"Field 11 selector unavailable: {type(selector_exc_20260709).__name__}")
    try:
        from core.canonical_symbol_selection_20260709 import filter_frame_for_symbol
        institutional_field11 = state.get("field11_similar_path_multisymbol_20260708")
        if isinstance(institutional_field11, pd.DataFrame) and not institutional_field11.empty:
            with st.expander("🏛️ Open / Close — Canonical Field 11 Multi-Symbol Snapshot from Super Quick Run", expanded=True):
                st.caption("This table follows the Field 11 selector above and uses the same canonical universe as Field 10.")
                view = filter_frame_for_symbol(institutional_field11, selected_symbol)
                if selected_horizon and "Horizon" in view.columns:
                    hview = view[view["Horizon"].astype(str).str.upper().eq(str(selected_horizon).upper())]
                    if not hview.empty:
                        view = hview
                st.dataframe(view if not view.empty else institutional_field11, use_container_width=True, hide_index=True)
                if not view.empty:
                    cols = st.columns(4)
                    row = view.iloc[0]
                    cols[0].metric("Reliability", str(row.get("Reliability", "—")))
                    cols[1].metric("Endpoint P50", str(row.get("Endpoint P50", "—")))
                    cols[2].metric("MFE / MAE", f"{row.get('MFE','—')} / {row.get('MAE','—')}")
                    cols[3].metric("Rank Link", str(row.get("Rank link back to Field 10", "—")))
    except Exception as institutional_exc_20260708:
        st.caption(f"Canonical Field 11 snapshot unavailable: {type(institutional_exc_20260708).__name__}")
    st.caption(
        "Historical-analogue and conditional-scenario evidence only. Field 11 does not claim a guaranteed next move, exact future price, or certain path."
    )
    enabled = st.checkbox("Enable Field 11", value=True, key="field11_enable_20260705")
    if not enabled:
        st.info("Field 11 is closed. Its completed snapshot remains available to Copy Full and the AI Assistant.")
        return
    # The canonical selector above owns Field 11 symbol selection. The old shared
    # child-publication selector is intentionally hidden because it could fall
    # back to the previous active symbol when child evidence was incomplete.

    actions = st.columns(2)
    if actions[0].button("Refresh Field 11 Snapshot", key="field11_refresh_20260705", use_container_width=True):
        from core.complete_repair_20260705 import refresh_lunch_snapshot
        refresh_lunch_snapshot(state)
        st.rerun()
    actions[1].caption("Refresh reloads completed evidence only; it does not start a heavy calculation.")

    identity = resolve_field11_identity(state)
    manifest = load_index_manifest(identity=identity)
    guard = validate_index_identity(identity, manifest)
    if not guard.get("ok"):
        # Pre-render repair is bounded to already-saved runtime snapshots. It does
        # not call MT5/APIs and does not rerank Field 10. This makes symbol
        # switching robust after deployments that retained child caches but lost
        # the optional Field 11 index artifact.
        try:
            from core.multi_symbol_field10_20260701 import available_saved_symbols
            from core.field11_similar_path_simulator_20260702 import prepare_field11_index
            symbols = available_saved_symbols(identity.get("symbol_universe") or [])
            if symbols:
                repair = prepare_field11_index(
                    state, parent_run_id=str(identity.get("parent_run_id") or identity.get("canonical_run_id") or "F11-REPAIR"),
                    symbols=symbols,
                )
                if repair.get("ok"):
                    identity = resolve_field11_identity(state)
                    manifest = load_index_manifest(identity=identity)
                    guard = validate_index_identity(identity, manifest)
                    state["field11_index_auto_repair_20260702"] = repair
        except Exception as exc:
            state["field11_index_auto_repair_error_20260702"] = f"{type(exc).__name__}: {exc}"
    if not guard.get("ok"):
        _render_field11_fallback(state, identity, guard)
        return

    universe = list(manifest.get("symbol_universe") or identity.get("symbol_universe") or [])
    supported = {str(value).upper() for value in (manifest.get("supported_timeframes") or [])}
    selected_tf = str(identity.get("timeframe") or state.get("timeframe") or "H1").upper()
    if selected_tf in {"M1", "H1", "H4", "D1"}:
        supported.add(selected_tf)
    timeframes = [value for value in ("M1", "H1", "H4", "D1", "M15", "M30") if value in supported]
    if not timeframes:
        timeframes = [selected_tf]
    for warning in identity.get("warnings") or []:
        st.info(str(warning))
    # Symbol and timeframe are read-only global identities. Field 11 owns only
    # analogue/simulation filters and cannot create a second display authority.
    symbol = str(selected_symbol or "").upper()
    timeframe = selected_tf
    if symbol not in universe and universe:
        st.warning("The active global symbol is not present in this saved Field 11 generation.")
    current = identity.get("field10_current") if isinstance(identity.get("field10_current"), pd.DataFrame) else pd.DataFrame()
    top = st.columns(6)
    top[0].metric("Index Status", manifest.get("status"))
    top[1].metric("Broker Date", identity.get("broker_date"))
    top[2].metric("Source Candle", str(identity.get("source_candle_time") or "")[:16])
    top[3].metric("Symbols", len(universe))
    top[4].metric("Indexed Rows", manifest.get("row_count"))
    top[5].metric("Index Version", str(manifest.get("index_version") or "")[-12:])

    reset_col, note_col = st.columns([1, 4])
    reset_col.button("Reset Filters", on_click=_reset_local_controls, use_container_width=True, key="field11_reset_filters_20260702")
    note_col.info(f"Global identity: {symbol or 'NOT PUBLISHED'} · {timeframe}. Symbol/timeframe changes are made only in the floating Global Symbol control and Settings.")

    with st.form("field11_selector_form_20260702", clear_on_submit=False):
        first = st.columns(1)
        horizon = first[0].selectbox("Future horizon", options=[1, 2, 3, 6, 12, 24], index=3, format_func=lambda value: f"Next {value} hour{'s' if value != 1 else ''}", key=f"{_LOCAL_PREFIX}horizon")

        second = st.columns(3)
        lookback_label = second[0].selectbox("Historical lookback", options=[25, 60, 90, 180, 365, 5000], index=4, format_func=lambda value: "Maximum available" if value == 5000 else f"{value} days", key=f"{_LOCAL_PREFIX}lookback")
        requested = second[1].selectbox("Requested analogues", options=[10, 20, 30, 50, 100], index=2, key=f"{_LOCAL_PREFIX}requested")
        minimum_similarity = second[2].selectbox("Minimum similarity", options=[60, 70, 75, 80, 85, 90], index=1, format_func=lambda value: f"{value}%", key=f"{_LOCAL_PREFIX}min_similarity")

        third = st.columns(3)
        engine = third[0].selectbox("Similarity engine", options=["Hybrid Recommended", "Matrix Profile", "Dynamic Time Warping", "Feature KNN", "Regime-First Hybrid", "Shape-First Hybrid"], key=f"{_LOCAL_PREFIX}engine")
        historical_source = third[1].selectbox("Historical source", options=["same symbol only", "compatible symbols", "all eligible multi-symbol instruments"], key=f"{_LOCAL_PREFIX}history_source")
        scenario_count = third[2].selectbox("Scenario count", options=[3, 4, 5], key=f"{_LOCAL_PREFIX}scenario_count")

        fourth = st.columns(2)
        weighting = fourth[0].selectbox("Weighting policy", options=["distance weighted", "similarity softmax", "equal weight for diagnostic comparison"], index=1, key=f"{_LOCAL_PREFIX}weighting")
        start_mode = fourth[1].selectbox("Simulation start", options=["latest completed candle", "selected historical broker candle"], key=f"{_LOCAL_PREFIX}start_mode")
        source_candle = None
        if start_mode.startswith("selected"):
            st.warning("Historical source selection remains completed-candle only.")
            # A bounded selector avoids loading thousands of timestamps into the phone UI.
            feature_path = manifest.get("feature_path")
            source_rows = read_index_frame(feature_path, columns=["symbol", "timeframe", "time"])
            source_rows["time"] = pd.to_datetime(source_rows["time"], errors="coerce", utc=True)
            available = source_rows.loc[(source_rows["symbol"] == symbol) & (source_rows["timeframe"] == timeframe), "time"].dropna().sort_values(ascending=False).head(500)
            source_candle = st.selectbox("Historical broker candle", options=[timestamp.isoformat() for timestamp in available], key=f"{_LOCAL_PREFIX}source_candle")

        with st.expander("Open / Close — Advanced market-condition selectors", expanded=False):
            cols = st.columns(3)
            same_hour = cols[0].checkbox("Same broker hour only", value=False, key=f"{_LOCAL_PREFIX}same_hour")
            compatible_hour_range = cols[1].selectbox("Compatible hour range", options=[0, 1, 2, 3, 4, 6, 12], index=2, format_func=lambda value: f"±{value} hours", disabled=same_hour, key=f"{_LOCAL_PREFIX}hour_range")
            high_news_exclusion = cols[2].checkbox("Exclude high-impact-news mismatches", value=True, key=f"{_LOCAL_PREFIX}news_exclusion")
            exact_regime = cols[0].checkbox("Exact canonical regime match", value=False, key=f"{_LOCAL_PREFIX}exact_regime")
            spread_limit = cols[1].slider("Spread-percentile limit", min_value=0, max_value=100, value=95, key=f"{_LOCAL_PREFIX}spread_limit")
            grade_options = ["Any"]
            if not current.empty and "Daily Grade" in current.columns:
                grade_options += sorted({str(value) for value in current["Daily Grade"].dropna() if str(value).strip()})
            grade_filter = cols[2].selectbox("Field 10 grade", options=grade_options, key=f"{_LOCAL_PREFIX}grade_filter")
            rank_min, rank_max = _safe_rank_control(current)
            st.caption(
                "Regime, sentiment, news and liquidity filters are enforced only where a timestamped historical archive exists. Missing historical context remains UNAVAILABLE and reduces reliability; it is never fabricated."
            )

        submitted = st.form_submit_button("Generate Conditional Historical-Analogue Scenarios", use_container_width=True)

    if submitted:
        selection = Field11Selection(
            symbol=symbol, timeframe=timeframe, source_candle=source_candle,
            horizon_hours=horizon, lookback_days=lookback_label, requested_analogues=requested,
            minimum_similarity=minimum_similarity, similarity_engine=engine,
            historical_source=historical_source, scenario_count=scenario_count,
            weighting_policy=weighting, exact_regime_match=exact_regime,
            same_broker_hour_only=same_hour, compatible_hour_range=compatible_hour_range,
            high_impact_news_exclusion=high_news_exclusion, spread_percentile_limit=spread_limit,
            field10_rank_min=rank_min, field10_rank_max=rank_max,
            field10_grade=None if grade_filter == "Any" else grade_filter,
        )
        with st.spinner("Matching qualified completed-candle analogues and clustering conditional scenarios…"):
            result = simulate_field11(state, selection)
        state["field11_last_result_20260702"] = result

    result = state.get("field11_last_result_20260702")
    if not isinstance(result, Mapping):
        st.info("Choose the simulator conditions and generate a historical-analogue scenario set.")
        return
    if not result.get("ok"):
        errors = result.get("errors") or []
        from core.complete_repair_20260705 import log_internal_error
        incident = log_internal_error("field11.simulation", RuntimeError("; ".join(map(str, errors)) or str(result.get("status") or "unavailable")))
        st.warning(f"The simulator could not produce a validated scenario set. Support reference: {incident}.")
        rejected = result.get("rejected_records")
        if isinstance(rejected, pd.DataFrame) and not rejected.empty:
            with st.expander("Open / Close — Rejected-case audit", expanded=False):
                st.dataframe(rejected, use_container_width=True, hide_index=True)
        return

    summary = result.get("summary") if isinstance(result.get("summary"), Mapping) else {}
    scenarios = result.get("scenarios") if isinstance(result.get("scenarios"), list) else []
    state["field11_structured_context_20260705"] = {
        "status": "COMPLETED", "run_id": identity.get("canonical_run_id"),
        "snapshot_hash": identity.get("snapshot_hash"), "timeframe": timeframe,
        "symbol": symbol, "summary": dict(summary), "scenarios": scenarios,
        "data_quality_status": summary.get("data_quality_status") or manifest.get("status"),
    }
    _render_metrics(summary)
    st.success(
        f"{float(summary.get('dominant_weighted_historical_frequency') or 0):.1f}% of the qualified weighted historical analogues followed the dominant scenario: {summary.get('dominant_scenario')}."
    )
    st.warning(summary.get("language_guard") or "Historical analogue evidence is conditional and not guaranteed.")
    _render_path_chart(summary, scenarios)
    st.markdown("#### Conditional Scenario Families")
    _render_scenario_table(scenarios)

    analogue_frame = result.get("analogue_records") if isinstance(result.get("analogue_records"), pd.DataFrame) else pd.DataFrame()
    analogue_frame = _normalise_cached_analogues(analogue_frame)
    st.markdown("#### Similar Historical Cases")
    if analogue_frame.empty:
        st.info("No included analogue table is available.")
    else:
        compact_columns = [
            "Match Rank", "Historical Broker Date", "Historical Broker Hour", "Source Symbol",
            "Overall Similarity", "Final Weight", "Future Direction", "Endpoint Pips",
            "Maximum Favorable Pips", "Maximum Adverse Pips", "Scenario Cluster",
        ]
        st.dataframe(analogue_frame[[column for column in compact_columns if column in analogue_frame.columns]], use_container_width=True, hide_index=True, height=480)
        with st.expander("Open / Close — Full analogue component audit", expanded=False):
            st.dataframe(analogue_frame, use_container_width=True, hide_index=True, height=600)

    rejected = result.get("rejected_records") if isinstance(result.get("rejected_records"), pd.DataFrame) else pd.DataFrame()
    with st.expander("Open / Close — Rejected-case audit table", expanded=False):
        if rejected.empty:
            st.info("No rejected-case details were retained for this cached result.")
        else:
            st.dataframe(rejected, use_container_width=True, hide_index=True, height=420)

    with st.expander("Open / Close — Bootstrap stability and drift diagnostics", expanded=False):
        stability = summary.get("stability") if isinstance(summary.get("stability"), Mapping) else {}
        drift = summary.get("drift_details") if isinstance(summary.get("drift_details"), Mapping) else {}
        st.dataframe(pd.DataFrame([
            {"Diagnostic": "Dominant scenario stability", "Value": stability.get("dominant_scenario_stability")},
            {"Diagnostic": "Direction stability", "Value": stability.get("direction_stability")},
            {"Diagnostic": "Remove-top-match sensitivity", "Value": stability.get("remove_top_match_sensitivity")},
            {"Diagnostic": "Bootstrap status", "Value": stability.get("status")},
            {"Diagnostic": "Analogue drift", "Value": drift.get("status")},
            {"Diagnostic": "Drift score", "Value": drift.get("score")},
            {"Diagnostic": "Drift reason", "Value": drift.get("reason")},
        ]), use_container_width=True, hide_index=True)

    with st.expander("Open / Close — Field 11 25-day validation history", expanded=False):
        history = load_validation_history(days=25)
        if history.empty:
            st.info("No matured Field 11 outcomes are available yet. Pending requests settle exactly once after their future horizon is fully completed.")
        else:
            st.dataframe(history, use_container_width=True, hide_index=True, height=500)


def render_field11_gate(state: MutableMapping[str, Any] | None = None) -> None:
    if not st.toggle(FIELD11_LABEL, value=False, key="lunch_field11_gate_20260702"):
        return
    render_field11_content(state)


__all__ = ["FIELD11_LABEL", "render_field11_content", "render_field11_gate"]
