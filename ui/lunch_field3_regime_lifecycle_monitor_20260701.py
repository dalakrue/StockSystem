"""Read-only Lunch Field 3 renderer for the saved institutional monitor."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping
import json

import pandas as pd

from core.field3_regime_lifecycle_monitor_20260701 import FIRST_14_COLUMNS, STATE_KEY

REGIME_COLORS = {
    "BULL_TREND": "rgba(46, 204, 113, 0.13)",
    "BEAR_TREND": "rgba(231, 76, 60, 0.13)",
    "RANGE": "rgba(149, 165, 166, 0.12)",
    "COMPRESSION": "rgba(52, 152, 219, 0.12)",
    "EXPANSION": "rgba(241, 196, 15, 0.14)",
    "TRANSITION": "rgba(155, 89, 182, 0.16)",
}
BIAS_SYMBOLS = {"BUY": "triangle-up", "SELL": "triangle-down", "WAIT": "circle-open"}
BIAS_COLORS = {"BUY": "#2ecc71", "SELL": "#e74c3c", "WAIT": "#95a5a6"}


def _number(value: Any, digits: int = 1, suffix: str = "") -> str:
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except Exception:
        return "N/A"


def _prob(value: Any) -> str:
    try:
        return f"{100*float(value):.1f}%"
    except Exception:
        return "N/A"


def _payload(state: Mapping[str, Any]) -> dict[str, Any]:
    value = state.get(STATE_KEY)
    return dict(value) if isinstance(value, Mapping) else {}


def _metric_cards(current: Mapping[str, Any]) -> None:
    import streamlit as st
    cards = [
        ("Current Regime", current.get("current_canonical_regime", "N/A")),
        ("Bias", current.get("current_bias", "WAIT")),
        ("Posterior", _prob(current.get("selected_regime_posterior"))),
        ("Probability Margin", _prob(current.get("probability_margin"))),
        ("Regime Age", _number(current.get("regime_age"), 0, " H1")),
        ("Expected Total Duration", _number(current.get("expected_total_duration"), 1, " H")),
        ("Median Remaining", _number(current.get("median_remaining_duration"), 1, " H")),
        ("Remaining 50% Interval", current.get("remaining_duration_50_interval", "N/A")),
        ("Remaining 80% Interval", current.get("remaining_duration_80_interval", "N/A")),
        ("Switch Risk 1H", _prob(current.get("switch_probability_1h"))),
        ("Switch Risk 3H", _prob(current.get("switch_probability_3h"))),
        ("Switch Risk 6H", _prob(current.get("switch_probability_6h"))),
        ("Likely Next Regime", current.get("most_likely_next_regime", "N/A")),
        ("Next-Regime Probability", _prob(current.get("next_regime_probability"))),
        ("Change-Point Probability", _prob(current.get("change_point_probability"))),
        ("Volatility Regime", current.get("volatility_regime", "N/A")),
        ("Stability", _number(current.get("stability"), 1, "/100")),
        ("Bias Reliability", _number(current.get("bias_reliability"), 1, "/100")),
        ("Model Agreement", _number(current.get("model_agreement"), 1, "/100")),
        ("Calibration Quality", _number(current.get("calibration_quality"), 1, "/100")),
        ("Duration Confidence", _number(current.get("duration_confidence"), 1, "/100")),
        ("Drift Risk", _number(current.get("drift_risk"), 1, "/100")),
        ("Calibrated Trust", _number(current.get("calibrated_trust"), 1, "/100")),
        ("Uncertainty", _number(current.get("uncertainty"), 1, "/100")),
        ("Data Quality", _number(current.get("data_quality"), 1, "/100")),
        ("Final Action", current.get("final_action", "BLOCK")),
        ("Primary Invalidation", current.get("primary_invalidation_condition", "N/A")),
    ]
    cols = st.columns(3)
    for i, (label, value) in enumerate(cards):
        cols[i % 3].metric(label, value)


def _regime_intervals(frame: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp, str]]:
    if frame.empty:
        return []
    work = frame.sort_values("__x").reset_index(drop=True)
    groups = work["Canonical Combined Regime"].ne(work["Canonical Combined Regime"].shift()).cumsum()
    rows = []
    for _, g in work.groupby(groups, sort=False):
        rows.append((pd.Timestamp(g["__x"].iloc[0]), pd.Timestamp(g["__x"].iloc[-1]) + pd.Timedelta(hours=1), str(g["Canonical Combined Regime"].iloc[-1])))
    return rows


def _timeline(payload: Mapping[str, Any]) -> None:
    import streamlit as st
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception as exc:
        st.info(f"Timeline unavailable because Plotly could not load: {exc}")
        return
    frame = pd.DataFrame(payload.get("chart_timeline") or [])
    if frame.empty:
        st.info("No saved lifecycle timeline is available for this canonical run.")
        return
    x = pd.to_datetime(frame.get("Broker Candle Time"), errors="coerce")
    fallback = pd.to_datetime(frame.get("event_time_utc"), errors="coerce", utc=True).dt.tz_localize(None)
    frame["__x"] = x.fillna(fallback)
    frame = frame.dropna(subset=["__x"]).sort_values("__x")
    if frame.empty:
        st.info("Timeline timestamps are unavailable.")
        return

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=.035,
                        row_heights=[.55, .24, .21], specs=[[{}], [{}], [{}]])
    for start, end, regime in _regime_intervals(frame):
        fig.add_vrect(x0=start, x1=end, fillcolor=REGIME_COLORS.get(regime, "rgba(127,127,127,.10)"),
                      opacity=1, line_width=0, row="all", col=1)
    fig.add_trace(go.Scatter(x=frame["__x"], y=frame["Close"], mode="lines", name=f"{str(payload.get('symbol') or 'SYMBOL')} H1 Close", line={"width": 1.6}), row=1, col=1)
    for bias in ("BUY", "SELL", "WAIT"):
        subset = frame.loc[frame["Regime Bias"].eq(bias)]
        if subset.empty:
            continue
        fig.add_trace(go.Scatter(x=subset["__x"], y=subset["Close"], mode="markers", name=bias,
                                 marker={"symbol": BIAS_SYMBOLS[bias], "size": 7, "color": BIAS_COLORS[bias], "opacity": .75}), row=1, col=1)
    cp = frame.loc[pd.to_numeric(frame["BOCPD Change-Point Probability"], errors="coerce").ge(.45)]
    if not cp.empty:
        fig.add_trace(go.Scatter(x=cp["__x"], y=cp["Close"], mode="markers", name="BOCPD candidate",
                                 marker={"symbol": "x", "size": 10, "color": "#8e44ad"}), row=1, col=1)
    pelt = frame.loc[frame["PELT Confirmed Boundary"].astype(bool)]
    if not pelt.empty:
        fig.add_trace(go.Scatter(x=pelt["__x"], y=pelt["Close"], mode="markers", name="PELT boundary",
                                 marker={"symbol": "diamond-open", "size": 10, "color": "#f39c12"}), row=1, col=1)

    fig.add_trace(go.Scatter(x=frame["__x"], y=100*pd.to_numeric(frame["Selected-Regime Posterior"], errors="coerce"),
                             mode="lines", name="Selected posterior", line={"width": 1.4}), row=2, col=1)
    fig.add_trace(go.Scatter(x=frame["__x"], y=100*pd.to_numeric(frame["Probability Margin"], errors="coerce"),
                             mode="lines", name="Probability margin", line={"width": 1.2, "dash": "dot"}), row=2, col=1)
    entropy = 100*(1-pd.to_numeric(frame["Probability Entropy"], errors="coerce"))
    fig.add_trace(go.Scatter(x=frame["__x"], y=entropy, mode="lines", name="Entropy quality", line={"width": 1.1, "dash": "dash"}), row=2, col=1)

    fig.add_trace(go.Scatter(x=frame["__x"], y=100*pd.to_numeric(frame["Switch Probability Within 3H"], errors="coerce"),
                             mode="lines", name="Switch risk 3H", line={"width": 1.4}), row=3, col=1)
    fig.add_trace(go.Scatter(x=frame["__x"], y=100*pd.to_numeric(frame["BOCPD Change-Point Probability"], errors="coerce"),
                             mode="lines", name="BOCPD", line={"width": 1.2, "dash": "dot"}), row=3, col=1)
    fig.add_trace(go.Scatter(x=frame["__x"], y=pd.to_numeric(frame["Calibrated Trust Score"], errors="coerce"),
                             mode="lines", name="Trust", line={"width": 1.5}), row=3, col=1)

    lifecycle = payload.get("lifecycle_window") if isinstance(payload.get("lifecycle_window"), Mapping) else {}
    def dt(key: str):
        value = pd.to_datetime(lifecycle.get(key), errors="coerce", utc=True)
        return value.tz_localize(None) if pd.notna(value) else None
    start, median = dt("current_regime_start_utc"), dt("median_exit_utc")
    q25, q75 = dt("remaining_50_start_utc"), dt("remaining_50_end_utc")
    q10, q90 = dt("remaining_80_start_utc"), dt("remaining_80_end_utc")
    if start is not None:
        fig.add_vline(x=start, line_dash="dash", row="all", col=1)
        fig.add_annotation(x=start, y=1.0, xref="x", yref="paper", text="Current regime start", showarrow=False, yshift=10)
    if q10 is not None and q90 is not None:
        fig.add_vrect(x0=q10, x1=q90, fillcolor="rgba(52,152,219,.08)", line_width=0, row="all", col=1)
    if q25 is not None and q75 is not None:
        fig.add_vrect(x0=q25, x1=q75, fillcolor="rgba(52,152,219,.16)", line_width=0, row="all", col=1)
    if median is not None:
        fig.add_vline(x=median, line_dash="dot", row="all", col=1)
        fig.add_annotation(x=median, y=.96, xref="x", yref="paper", text="Median estimated exit", showarrow=False, yshift=8)

    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Confidence %", range=[0, 100], row=2, col=1)
    fig.update_yaxes(title_text="Risk / Trust", range=[0, 100], row=3, col=1)
    fig.update_layout(height=720, margin={"l": 35, "r": 20, "t": 35, "b": 30}, legend={"orientation": "h", "y": 1.02},
                      hovermode="x unified", title=f"{str(payload.get('symbol') or 'Symbol')} Regime Lifecycle and Switch-Risk Timeline")
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "scrollZoom": False})
    st.caption("Filtered probabilities and action gates are causal. Smoothed probabilities and PELT markers are retrospective audit evidence only.")


def _history_table(payload: Mapping[str, Any]) -> None:
    import streamlit as st
    frame = pd.DataFrame(payload.get("history_25d") or [])
    st.markdown("#### Main 25-Day H1 Regime Intelligence History")
    st.caption("Newest completed broker H1 first. The first 14 decision columns remain visible first; all remaining evidence is preserved through horizontal scrolling.")
    if frame.empty:
        st.info("No saved 25-day Field 3 monitor history is available.")
        return
    try:
        from core.regime_age_columns_20260722 import add_age_alias_to_table
        frame = add_age_alias_to_table(frame, fallback_age=(payload.get("current") or {}).get("regime_age"))
    except Exception:
        pass
    ordered = [c for c in FIRST_14_COLUMNS if c in frame] + [c for c in frame.columns if c not in FIRST_14_COLUMNS]
    frame = frame.loc[:, ordered]
    st.dataframe(frame, use_container_width=True, hide_index=True, height=560)
    csv = frame.to_csv(index=False).encode("utf-8")
    st.download_button("Download Field 3 Regime Monitor CSV", csv,
                       file_name=f"field3_{str(payload.get('symbol') or 'symbol').lower()}_regime_lifecycle_monitor_25d.csv", mime="text/csv",
                       use_container_width=True, key="field3_regime_lifecycle_csv_20260701")


def _daily_table(payload: Mapping[str, Any]) -> None:
    import streamlit as st
    frame = pd.DataFrame(payload.get("daily_25d") or [])
    st.markdown("#### Daily 25-Broker-Day Regime Summary")
    if frame.empty:
        st.info("No daily summary is available.")
        return
    try:
        from core.regime_age_columns_20260722 import add_age_alias_to_table
        frame = add_age_alias_to_table(frame, fallback_age=(payload.get("current") or {}).get("regime_age"))
    except Exception:
        pass
    st.dataframe(frame, use_container_width=True, hide_index=True, height=430)


def render_field3_regime_lifecycle_monitor(state: MutableMapping[str, Any], canonical: Mapping[str, Any] | None = None) -> None:
    """Render saved results only; never imports or calls the fitting engine."""
    import streamlit as st
    payload = _payload(state)
    st.markdown("## Regime Intelligence, Bias Reliability and Lifecycle Monitor")
    st.caption("Additive shadow validation layer. Protected Lower/Middle/Higher regimes, KNN/Greedy priorities, scores, histories and decisions remain unchanged.")
    if not payload:
        st.info("This saved monitor has not been published for the current canonical run. Use Settings → Run Calculation + Open Lunch.")
        return
    current = payload.get("current") if isinstance(payload.get("current"), Mapping) else {}
    expected_run = str((canonical or {}).get("run_id") or "")
    if expected_run and str(payload.get("run_id") or "") != expected_run:
        st.error("OUT OF SYNC — the saved Field 3 monitor run_id does not match the active canonical run. No stale result is presented as current.")
    if str(payload.get("status")) == "INVALID_DATA_QUALITY":
        st.error("Current result is invalid because the data-quality gate failed. The last protected production regime remains reference-only and the monitor action is BLOCK.")
    _metric_cards(current)
    _timeline(payload)
    _history_table(payload)
    _daily_table(payload)
    with st.expander("Probability Vector, Duration, Change-Point and Volatility Evidence", expanded=False):
        st.json({
            "full_state_probability_vector": payload.get("full_state_probability_vector"),
            "latent_state_model": payload.get("latent_state_model"),
            "hamilton_markov_switching": payload.get("hamilton_markov_switching"),
            "bocpd": payload.get("bocpd"), "pelt_audit": payload.get("pelt_audit"),
            "duration_model": payload.get("duration_model"), "volatility_model": payload.get("volatility_model"),
        }, expanded=False)
    with st.expander("Walk-Forward Calibration and Baseline Validation", expanded=False):
        st.json(payload.get("validation") or {}, expanded=False)
    with st.expander("Trust Function, Action Gates and Method Disclosures", expanded=False):
        st.json({"trust_definition": payload.get("trust_definition"), "action_thresholds": payload.get("action_thresholds"),
                 "calibration": payload.get("calibration"), "data_quality": payload.get("data_quality"),
                 "method_disclosures": payload.get("method_disclosures"), "performance": payload.get("performance")}, expanded=False)
    export = json.dumps(payload, indent=2, default=str).encode("utf-8")
    st.download_button("Download Complete Field 3 Regime Monitor JSON", export,
                       file_name=f"field3_{str(payload.get('symbol') or 'symbol').lower()}_regime_lifecycle_monitor.json", mime="application/json",
                       use_container_width=True, key="field3_regime_lifecycle_json_20260701")


__all__ = ["render_field3_regime_lifecycle_monitor"]
