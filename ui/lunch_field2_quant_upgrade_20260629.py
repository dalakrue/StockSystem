"""Read-only renderer for the adaptive Field 2 quant overlay."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping
import pandas as pd


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def render_field2_quant_upgrade(state: MutableMapping[str, Any]) -> None:
    import streamlit as st

    from core.field2_quant_upgrade_20260629 import STATE_KEY

    result = state.get(STATE_KEY)
    if not isinstance(result, Mapping) or not result.get("ok"):
        with st.expander("Open / Close — Adaptive Field 2 Quant Upgrade", expanded=False):
            error = result.get("error") if isinstance(result, Mapping) else None
            st.info(
                "Run Quick, Full, or Super Quick from Settings to build the symbol-specific central tendency, "
                "dynamic bands, relationship map, and similar-day analysis."
            )
            if error:
                st.caption(str(error))
        return

    symbol = str(result.get("symbol") or state.get("symbol") or "EURUSD")
    active = str(state.get("symbol") or symbol)
    stale = symbol.upper() != active.upper()

    st.markdown("### Adaptive Prediction Path — Central Tendency + Dynamic Bands")
    st.caption(
        "Built during the explicit Settings run from completed OHLC rows. The overlay expands bands with a GARCH-style "
        "variance recursion and strong-breakout momentum; it does not overwrite the legacy protected prediction cache."
    )
    if stale:
        st.warning(f"This cached upgrade belongs to {symbol}; the active symbol is {active}. Run Settings for {active} before using it.")

    breakout = _mapping(result.get("breakout"))
    path = result.get("prediction_path")
    path = path if isinstance(path, pd.DataFrame) else pd.DataFrame(path or [])
    cols = st.columns(5)
    cols[0].metric("Central Tendency +1H", f"{float(result.get('central_tendency') or 0):.5f}")
    cols[1].metric("Strong Trend Breakout", f"{float(breakout.get('probability') or 0):.1f}%")
    cols[2].metric("Breakout Direction", str(breakout.get("direction") or "WAIT"))
    cols[3].metric("Hurst Exponent", str(breakout.get("hurst_exponent") or "—"))
    cols[4].metric("Classification", str(breakout.get("classification") or "UNAVAILABLE"))

    if not path.empty:
        try:
            import plotly.graph_objects as go
            figure = go.Figure()
            figure.add_trace(go.Scatter(x=path["Hour"], y=path["Central Tendency"], mode="lines+markers", name="Central Tendency"))
            figure.add_trace(go.Scatter(x=path["Hour"], y=path["Dynamic Upper Band"], mode="lines", name="Dynamic Upper Band"))
            figure.add_trace(go.Scatter(x=path["Hour"], y=path["Dynamic Lower Band"], mode="lines", name="Dynamic Lower Band", fill="tonexty"))
            figure.update_layout(
                height=430,
                xaxis_title="Forecast Horizon (hours)",
                yaxis_title=f"{symbol} Price",
                margin=dict(l=15, r=15, t=35, b=15),
                legend=dict(orientation="h"),
            )
            st.plotly_chart(figure, use_container_width=True, key="field2_adaptive_path_chart_20260629")
        except Exception:
            st.line_chart(path.set_index("Hour")[["Central Tendency", "Dynamic Upper Band", "Dynamic Lower Band"]])
        st.dataframe(
            path[[
                "Horizon", "Central Tendency", "Dynamic Upper Band", "Dynamic Lower Band",
                "Forecast Volatility %", "Band Expansion Factor",
            ]],
            use_container_width=True,
            hide_index=True,
            height=280,
        )

    with st.expander("Open / Close — Strong Trend Breakout Probability Evidence", expanded=False):
        evidence = pd.DataFrame([
            {"Evidence": "Candle body / previous body", "Value": breakout.get("body_ratio_vs_previous")},
            {"Evidence": "Range / ATR", "Value": breakout.get("range_atr_ratio")},
            {"Evidence": "Resistance broken", "Value": breakout.get("broke_recent_resistance")},
            {"Evidence": "Support broken", "Value": breakout.get("broke_recent_support")},
            {"Evidence": "Momentum Z", "Value": breakout.get("momentum_z")},
            {"Evidence": "Volume Z / order-flow proxy", "Value": breakout.get("volume_z")},
            {"Evidence": "Hurst trend memory", "Value": breakout.get("hurst_exponent")},
        ])
        st.dataframe(evidence, use_container_width=True, hide_index=True)
        st.caption(
            "A large candle alone is not enough. The probability rises when candle expansion, resistance/support break, "
            "volatility expansion, aligned momentum, volume pressure, and persistent trend memory agree."
        )

    st.markdown("### 25-Day Column Relationship Map")
    relationship = result.get("relationship_history")
    relationship = relationship if isinstance(relationship, pd.DataFrame) else pd.DataFrame(relationship or [])
    summary = _mapping(result.get("relationship_summary"))
    rcols = st.columns(4)
    rcols[0].metric("Relationship Decision", str(summary.get("decision") or "WAIT"))
    rcols[1].metric("Buy Relationship Weight", str(summary.get("buy_weight") or 0))
    rcols[2].metric("Sell Relationship Weight", str(summary.get("sell_weight") or 0))
    rcols[3].metric("Buy/Sell Relationship Ratio", str(summary.get("buy_sell_relationship_ratio") or 1))

    if relationship.empty:
        st.info("Not enough 25-day numeric history was available to build trusted column relationships.")
    else:
        pie_rows = pd.DataFrame({
            "Relationship": ["BUY", "SELL", "NEUTRAL"],
            "Weight": [
                float(summary.get("buy_weight") or 0),
                float(summary.get("sell_weight") or 0),
                float(summary.get("neutral_weight") or 0),
            ],
        })
        try:
            import plotly.express as px
            pie = px.pie(pie_rows, names="Relationship", values="Weight", title="Relationship Weight Distribution")
            pie.update_layout(height=360, margin=dict(l=15, r=15, t=50, b=15))
            st.plotly_chart(pie, use_container_width=True, key="field2_relationship_pie_20260629")
        except Exception:
            st.dataframe(pie_rows, use_container_width=True, hide_index=True)
        st.dataframe(
            relationship[[
                "Column A", "Column B", "Pearson", "Spearman", "Relationship Trust Score",
                "Absorb or Not", "Definitive Decision", "Samples",
            ]],
            use_container_width=True,
            hide_index=True,
            height=480,
        )

    similar = _mapping(result.get("similar_day"))
    with st.expander("Open / Close — Most Similar Historical Day: Current 6H + Subsequent 6H", expanded=False):
        if not similar.get("ok"):
            st.info(str(similar.get("reason") or "Similar-day evidence is unavailable."))
        else:
            scol = st.columns(5)
            scol[0].metric("Similarity Score", f"{float(similar.get('similarity_score') or 0):.1f}%")
            scol[1].metric("Historical Open", f"{float(similar.get('historical_open') or 0):.5f}")
            scol[2].metric("Historical Close", f"{float(similar.get('historical_close') or 0):.5f}")
            scol[3].metric("Subsequent 6H Close", f"{float(similar.get('subsequent_close') or 0):.5f}")
            scol[4].metric("Subsequent 6H Move", f"{float(similar.get('subsequent_return_pct') or 0):+.3f}%")
            st.caption(
                f"Matched interval: {similar.get('match_start_time')} → {similar.get('match_end_time')} · "
                f"subsequent path ends {similar.get('subsequent_end_time')} · DTW distance {similar.get('dtw_distance')}."
            )
            overlay = similar.get("overlay")
            overlay = overlay if isinstance(overlay, pd.DataFrame) else pd.DataFrame(overlay or [])
            if not overlay.empty:
                try:
                    import plotly.express as px
                    chart = px.line(
                        overlay,
                        x="Step",
                        y="Normalized Move %",
                        color="Series",
                        markers=True,
                        title="Current Last 6H vs Historical Match and Its Subsequent 6H",
                    )
                    chart.update_layout(height=430, margin=dict(l=15, r=15, t=50, b=15))
                    st.plotly_chart(chart, use_container_width=True, key="field2_similar_day_overlay_20260629")
                except Exception:
                    pivot = overlay.pivot_table(index="Step", columns="Series", values="Normalized Move %", aggfunc="last")
                    st.line_chart(pivot)
            st.caption(
                "The similar-day path is historical evidence, not a guaranteed forecast. Dynamic Time Warping compares shape "
                "even when the movement speed differs slightly."
            )

    st.caption(
        f"Upgrade identity: symbol={symbol} · timeframe={result.get('timeframe')} · completed candle={result.get('completed_candle')} · "
        f"run={result.get('run_id')} · generation={result.get('generation_id')} · rows={result.get('rows')} · build={result.get('wall_seconds')}s."
    )


__all__ = ["render_field2_quant_upgrade"]
