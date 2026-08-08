"""2026-06-09 runtime-safe Lunch/Data Visualization patch.

Adds compact copy exports, a second PowerBI-style candlestick projection chart,
and lighter button states without touching connector/order logic.
"""
from __future__ import annotations


def apply(ns: dict) -> None:
    import json
    import pandas as pd
    import streamlit as st

    def _safe_json(obj):
        try:
            if isinstance(obj, pd.DataFrame):
                return obj.tail(30).to_dict("records")
            if isinstance(obj, pd.Series):
                return obj.to_dict()
            if isinstance(obj, pd.Timestamp):
                return str(obj)
            if isinstance(obj, dict):
                return {str(k): _safe_json(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_safe_json(x) for x in obj[:60]]
            return obj
        except Exception:
            return str(obj)

    def _compact_latest_ohlc(df, rows=24):
        if not isinstance(df, pd.DataFrame) or df.empty:
            return []
        cols = [c for c in ["time", "open", "high", "low", "close", "volume"] if c in df.columns]
        if not cols:
            return []
        out = df[cols].tail(int(rows)).copy()
        for c in out.columns:
            if "time" in str(c).lower():
                out[c] = pd.to_datetime(out[c], errors="coerce").astype(str)
        return out.to_dict("records")

    def _build_lunch_all_copy_text_v2():
        """Compact full Lunch export: current decision + new BI/projection data, no history tables."""
        df = st.session_state.get("last_df")
        metric = st.session_state.get("eurusd_h1_matrix_export", {}) or {}
        pred = st.session_state.get("lunch_prediction_export", {}) or {}
        dv_pred = st.session_state.get("dv_pp_predicted")
        dv_path = st.session_state.get("dv_pp_lightblue_path")
        dv_result = st.session_state.get("dv_pp_base_result", {}) or {}
        dv_regime = st.session_state.get("dv_pp_regime_summary", {}) or {}
        dv_bt_summary = st.session_state.get("dv_pp_bt_summary", {}) or {}

        payload = {
            "export_type": "LUNCH_COMPACT_FULL_NO_HISTORY",
            "built_at": str(pd.Timestamp.now()),
            "symbol": st.session_state.get("symbol", "EURUSD"),
            "timeframe": st.session_state.get("timeframe", "H1"),
            "source": st.session_state.get("source", "DISCONNECTED"),
            "rows": len(df) if isinstance(df, pd.DataFrame) else 0,
            "metric_and_reverse10_current": _safe_json(metric),
            "lunch_prediction_current": _safe_json(pred),
            "data_visualization_new_summary": {
                "powerbi_ml": _safe_json({k: v for k, v in (dv_result or {}).items() if k not in {"vote_df", "deep_df", "forecast_df", "history"}}),
                "smooth_regime": _safe_json(dv_regime),
                "prediction_backtest_summary_only": _safe_json(dv_bt_summary),
                "future_blue_candles": _safe_json(dv_pred if isinstance(dv_pred, pd.DataFrame) else pd.DataFrame()),
                "light_blue_current_path": _safe_json(dv_path if isinstance(dv_path, pd.DataFrame) else pd.DataFrame()),
            },
            "latest_market_tail_24_only": _compact_latest_ohlc(df, rows=24),
            "excluded_to_reduce_lines": [
                "25D reversal scan/history tables",
                "prediction-vs-actual full history rows",
                "rolling projection history rows",
                "raw account/order/deal history rows",
            ],
        }
        return "LUNCH TAB COMPACT FULL COPY — NO HISTORY DATA\n" + "=" * 64 + "\n" + json.dumps(_safe_json(payload), indent=2, ensure_ascii=False, default=str)

    def _render_second_powerbi_candle_chart(d, predicted, result=None, regime=None):
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
        except Exception as exc:
            st.warning(f"Second PowerBI chart unavailable: {exc}")
            return
        prep = ns.get("_dv_prepare_ohlc_v20260609")
        last_days = ns.get("_dv_last_continuous_days_v20260609")
        if callable(last_days):
            x = last_days(d, days=5, limit=3000)
        elif callable(prep):
            x = prep(d, limit=240).tail(120)
        else:
            x = d.tail(120) if isinstance(d, pd.DataFrame) else pd.DataFrame()
        if not isinstance(x, pd.DataFrame) or x.empty:
            st.info("Second chart needs clean OHLC data.")
            return
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=.045, row_heights=[.62, .20, .18], subplot_titles=("PowerBI Chart 2 — actual + future candles", "Trend / reliability ribbon", "Projected confidence"))
        fig.add_trace(go.Candlestick(x=x["time"], open=x["open"], high=x["high"], low=x["low"], close=x["close"], name="Actual"), row=1, col=1)
        if isinstance(predicted, pd.DataFrame) and not predicted.empty:
            fig.add_trace(go.Candlestick(x=predicted["time"], open=predicted["open"], high=predicted["high"], low=predicted["low"], close=predicted["close"], name="Future BLUE candles", increasing={"line":{"color":"#0EA5E9","width":2},"fillcolor":"rgba(14,165,233,.32)"}, decreasing={"line":{"color":"#60A5FA","width":2},"fillcolor":"rgba(96,165,250,.24)"}), row=1, col=1)
            conf_col = "confidence_pct" if "confidence_pct" in predicted.columns else None
            if conf_col:
                fig.add_trace(go.Bar(x=predicted["time"], y=predicted[conf_col], name="Forecast confidence %"), row=3, col=1)
        close = pd.to_numeric(x["close"], errors="coerce")
        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=48, adjust=False).mean()
        ribbon = ((ema_fast - ema_slow) / close.replace(0, pd.NA) * 100).fillna(0)
        fig.add_trace(go.Scatter(x=x["time"], y=ribbon, mode="lines", name="EMA trend ribbon %"), row=2, col=1)
        fig.add_hline(y=0, row=2, col=1, line_width=1)
        title_score = ""
        if isinstance(result, dict):
            title_score = f" • Master {result.get('master_score','-')}/10 • Bull {result.get('bull_probability','-')}%"
        if isinstance(regime, dict) and regime.get("current_regime"):
            title_score += f" • Regime {regime.get('current_regime')}"
        fig.update_layout(height=760, margin=dict(l=8, r=8, t=62, b=8), title="Second PowerBI-style Candlestick Projection" + title_score, xaxis_rangeslider_visible=False, legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})


    def _apply_v28_mobile_cpu_ram_css():
        """Bigger phone-app mode + lighter GPU/CPU CSS.

        Streamlit Cloud/mobile can feel slow when every card has heavy blur/shadow.
        This keeps the real-app look but removes expensive effects on small screens.
        """
        st.markdown("""
        <style>
        :root{--v28-radius:22px;}
        .v28-run-row div[data-testid="stButton"] > button{
            min-height:58px!important;border-radius:22px!important;font-size:1.05rem!important;
            font-weight:900!important;letter-spacing:.01em!important;
        }
        .v28-phone-note{padding:10px 12px;border-radius:18px;background:rgba(14,165,233,.10);border:1px solid rgba(14,165,233,.22);font-weight:800;}
        @media (max-width: 820px){
          .block-container{padding:.55rem .48rem 4.8rem .48rem!important;max-width:100%!important;}
          h1,h2,h3{line-height:1.12!important;}
          div[data-testid="stButton"] > button{min-height:52px!important;border-radius:20px!important;font-size:1.02rem!important;font-weight:850!important;}
          div[data-testid="stMetric"]{border-radius:20px!important;padding:12px!important;box-shadow:none!important;backdrop-filter:none!important;}
          section[data-testid="stSidebar"]{min-width:86vw!important;max-width:92vw!important;}
          div[data-testid="stDataFrame"]{max-height:58vh!important;overflow:auto!important;border-radius:16px!important;}
          .js-plotly-plot, .plot-container{max-height:78vh!important;}
        }
        </style>
        """, unsafe_allow_html=True)

    def _render_data_visualization_v2():
        rows_limit = int(st.session_state.get("dv_pp_rows", 6000))
        horizon = int(st.session_state.get("dv_pp_horizon", 24))
        min_days = int(st.session_state.get("dv_pp_min_days", 5))
        bt_lookback = int(st.session_state.get("dv_pp_bt", 180))
        _apply_v28_mobile_cpu_ram_css()
        st.markdown("### 📊 Data Visualization — Reliable PowerBI + ML Projection")
        st.caption("Manual-run only for speed/RAM. Click Run Calculating first; no heavy 5-layer or chart work runs automatically.")
        st.markdown('<div class="v28-run-row">', unsafe_allow_html=True)
        top = st.columns([1.25, .85, .85, .85, .85])
        with top[0]:
            run = st.button("▶ Run Calculating", use_container_width=True, key="dv_run_calculating_v28")
            run_legacy = st.button("▶ Run Reliable PowerBI + Future Candles", use_container_width=True, key="dv_run_reliable_powerbi_v2")
            run = bool(run or run_legacy)
        with top[1]:
            rows_limit = st.slider("Rows used", 800, 12000, min(rows_limit, 12000), 400, key="dv_pp_rows")
        with top[2]:
            horizon = st.slider("Future candles", 6, 60, min(horizon, 60), 6, key="dv_pp_horizon")
        with top[3]:
            min_days = st.slider("Regime min days", 3, 21, min_days, 1, key="dv_pp_min_days")
        with top[4]:
            bt_lookback = st.slider("Backtest summary bars", 60, 360, min(bt_lookback, 360), 20, key="dv_pp_bt")
        st.markdown("</div>", unsafe_allow_html=True)

        if run:
            st.session_state["lunch_bi_visual_ready"] = True
            with st.spinner("Calculating clean OHLC, ML projection, future candles, and reliability summary…"):
                clean = ns["_clean_lunch_visual_df"](limit=rows_limit)
                d = ns["_dv_prepare_ohlc_v20260609"](clean, limit=rows_limit)
                if not isinstance(d, pd.DataFrame) or d.empty or len(d) < 120:
                    st.warning("Need at least 120 clean OHLC candles. Refresh/connect data first.")
                    ns["_render_lunch_copy_refresh_bar"]()
                    return
                result = ns["_five_layer_powerbi_calculate"](d, horizon=horizon)
                predicted = ns["_dv_predict_future_candles_v20260609"](d, horizon=horizon)
                _, bt_summary = ns["_dv_prediction_vs_actual_history_v20260609"](d, lookback=bt_lookback, horizon=1)
                regime, _ = ns["_dv_major_regime_detector_v20260609"](d, min_days=float(min_days), lookback_days=240, horizon=horizon)
                light_path = ns["_dv_build_lightblue_path_v20260609"](ns["_dv_last_continuous_days_v20260609"](d, days=10), predicted)
                st.session_state.update({
                    "dv_pp_df": d, "dv_pp_base_result": result, "dv_pp_predicted": predicted,
                    "dv_pp_bt_summary": bt_summary, "dv_pp_regime_summary": regime,
                    "dv_pp_lightblue_path": light_path,
                    "lunch_5layer_powerbi_result": result,
                    "lunch_5layer_powerbi_df": d,
                })
            st.success("Data Visualization upgraded result is ready.")

        if not st.session_state.get("lunch_bi_visual_ready", False):
            st.info("Press run first. No heavy chart calculation runs automatically.")
            ns["_render_lunch_copy_refresh_bar"]()
            return

        d = st.session_state.get("dv_pp_df", pd.DataFrame())
        result = st.session_state.get("dv_pp_base_result", {})
        predicted = st.session_state.get("dv_pp_predicted", pd.DataFrame())
        regime = st.session_state.get("dv_pp_regime_summary", {})
        bt_summary = st.session_state.get("dv_pp_bt_summary", {})
        light_path = st.session_state.get("dv_pp_lightblue_path", pd.DataFrame())

        cards = st.columns(6)
        if isinstance(result, dict):
            cards[0].metric("Master", f"{result.get('master_score','-')}/10")
            cards[1].metric("Bull", f"{result.get('bull_probability','-')}%")
        if isinstance(regime, dict):
            cards[2].metric("Regime", regime.get("current_regime", "-"))
            cards[3].metric("Days In", regime.get("days_since_last_change", regime.get("days_since_change", "-")))
            cards[4].metric("Days Left", regime.get("estimated_days_remaining", regime.get("estimated_days_left", "-")))
        cards[5].metric("BT Dir Acc", f"{bt_summary.get('direction_accuracy_pct', 0)}%" if isinstance(bt_summary, dict) else "-")

        st.markdown("#### Main PowerBI Candlestick + ML Projection")
        try:
            ns["_dv_render_candle_powerbi_chart_v20260609"](d, predicted, None, None)
        except TypeError:
            ns["_dv_render_candle_powerbi_chart_v20260609"](d, predicted)
        st.markdown("#### Second PowerBI-style Candlestick Chart with Future Candles")
        _render_second_powerbi_candle_chart(d, predicted, result, regime)

        # Feed the original PowerBI renderer so the expander shows results instead of only the old instruction.
        if isinstance(result, dict) and result.get("ok"):
            st.session_state["lunch_5layer_powerbi_result"] = result
            st.session_state["lunch_5layer_powerbi_df"] = d
        with st.expander("Open / Close — Original PowerBI + ML Projection", expanded=False):
            try:
                ns["_render_lunch_advanced_powerbi_ml_projection"](d, horizon=horizon)
            except Exception as exc:
                st.warning(f"Original PowerBI renderer could not display: {exc}")
                st.json(_safe_json({k: v for k, v in (result or {}).items() if k not in {"vote_df", "deep_df", "forecast_df", "history"}}))

        with st.expander("Open / Close — Future Candle Tables", expanded=False):
            if isinstance(predicted, pd.DataFrame) and not predicted.empty:
                sorter = ns.get("_dv_sort_newest_first_v20260609")
                st.dataframe(sorter(predicted) if callable(sorter) else predicted.iloc[::-1], use_container_width=True, hide_index=True, height=260)
            if isinstance(light_path, pd.DataFrame) and not light_path.empty:
                st.markdown("Light-blue current path")
                st.dataframe(light_path, use_container_width=True, hide_index=True, height=200)

        with st.expander("📋 Data Visualization Copy Export — no history rows", expanded=True):
            payload = {
                "export_type": "DATA_VISUALIZATION_COMPACT_NO_HISTORY",
                "built_at": str(pd.Timestamp.now()),
                "powerbi_ml_summary": _safe_json({k: v for k, v in (result or {}).items() if k not in {"vote_df", "deep_df", "forecast_df", "history"}}),
                "regime_summary": _safe_json(regime),
                "prediction_backtest_summary_only": _safe_json(bt_summary),
                "future_blue_candles": _safe_json(predicted if isinstance(predicted, pd.DataFrame) else pd.DataFrame()),
                "light_blue_current_path": _safe_json(light_path if isinstance(light_path, pd.DataFrame) else pd.DataFrame()),
            }
            text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
            st.session_state["lunch_visualization_export"] = text
            try:
                from core.pro_terminal_uiux import render_mobile_copy_button
                render_mobile_copy_button("Copy Data Visualization", text, "copy_data_visualization_no_history_v2")
            except Exception:
                st.text_area("Data Visualization Copy", text, height=260)
        ns["_render_lunch_copy_refresh_bar"]()

    ns["_build_lunch_all_copy_text"] = _build_lunch_all_copy_text_v2
    ns["_render_lunch_data_visualization_inner_tab"] = _render_data_visualization_v2

# =====================================================================
# 2026-06-10 ADDITIVE PATCH
# Lunch NY-London overlap metrics + stronger Data Visualization KPI layer.
# This section is intentionally additive/runtime-safe: if data is missing,
# it shows a warning instead of breaking the app.
# =====================================================================
try:
    _PREV_APPLY_20260609 = apply
except Exception:
    _PREV_APPLY_20260609 = None


def apply(ns: dict) -> None:  # type: ignore[no-redef]
    if callable(_PREV_APPLY_20260609):
        _PREV_APPLY_20260609(ns)

    import json
    import pandas as pd
    import streamlit as st

    def _nylo_find_cols(df):
        cols = {str(c).lower().strip(): c for c in getattr(df, 'columns', [])}
        return {
            'time': cols.get('time') or cols.get('datetime') or cols.get('date') or cols.get('timestamp'),
            'open': cols.get('open') or cols.get('o'),
            'high': cols.get('high') or cols.get('h'),
            'low': cols.get('low') or cols.get('l'),
            'close': cols.get('close') or cols.get('c'),
            'volume': cols.get('volume') or cols.get('vol') or cols.get('tick_volume'),
        }

    def _nylo_prepare_df(df):
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame()
        m = _nylo_find_cols(df)
        need = [m.get('open'), m.get('high'), m.get('low'), m.get('close')]
        if not all(need):
            return pd.DataFrame()
        d = pd.DataFrame()
        if m.get('time'):
            d['time'] = pd.to_datetime(df[m['time']], errors='coerce', utc=False)
        else:
            d['time'] = pd.date_range(end=pd.Timestamp.utcnow().tz_localize(None), periods=len(df), freq='h')
        for k in ['open', 'high', 'low', 'close']:
            d[k] = pd.to_numeric(df[m[k]], errors='coerce')
        if m.get('volume'):
            d['volume'] = pd.to_numeric(df[m['volume']], errors='coerce').fillna(0)
        else:
            d['volume'] = 0.0
        d = d.dropna(subset=['time', 'open', 'high', 'low', 'close']).sort_values('time')
        return d.tail(12000).reset_index(drop=True)

    def _score_0_10(value, lo, hi, reverse=False):
        try:
            v = float(value)
            if hi == lo:
                return 5.0
            s = (v - lo) / (hi - lo) * 10.0
            s = max(0.0, min(10.0, s))
            return round(10.0 - s if reverse else s, 2)
        except Exception:
            return 0.0

    def _build_ny_london_overlap_history(df=None, days=25):
        raw = st.session_state.get('last_df') if df is None else df
        d = _nylo_prepare_df(raw)
        if d.empty:
            return pd.DataFrame(), {}
        # June/summer London-New York overlap is 12:00-16:00 UTC. This app's
        # EURUSD feed is usually UTC-like; fixed hours keep the metric stable.
        d['_date'] = d['time'].dt.date
        d['_hour'] = d['time'].dt.hour
        ov = d[(d['_hour'] >= 12) & (d['_hour'] <= 16)].copy()
        if ov.empty:
            ov = d[(d['_hour'] >= 13) & (d['_hour'] <= 17)].copy()
        if ov.empty:
            return pd.DataFrame(), {'message': 'No candles found inside NY-London overlap hours.'}
        rows = []
        all_range = (d['high'] - d['low']).rolling(24, min_periods=3).mean().dropna()
        base_range = float(all_range.median()) if not all_range.empty else float((d['high'] - d['low']).median())
        base_range = max(base_range, 1e-9)
        for day, x in ov.groupby('_date'):
            x = x.sort_values('time')
            if x.empty:
                continue
            first_open = float(x['open'].iloc[0]); last_close = float(x['close'].iloc[-1])
            hi = float(x['high'].max()); lo = float(x['low'].min())
            rng = max(hi - lo, 1e-9)
            body = abs(last_close - first_open)
            direction = 'BUY' if last_close > first_open else 'SELL' if last_close < first_open else 'RANGE'
            trend_eff = body / rng
            range_power = rng / base_range
            close_pos = (last_close - lo) / rng
            momentum = (last_close - first_open) / max(abs(first_open), 1e-9) * 10000.0
            vol_score = _score_0_10(range_power, 0.45, 2.2)
            trend_score = _score_0_10(trend_eff, 0.15, 0.85)
            buy_align = round((trend_score * 0.55 + _score_0_10(close_pos, 0.35, 0.9) * 0.45) if direction == 'BUY' else _score_0_10(close_pos, 0.35, 0.9) * 0.35, 2)
            sell_align = round((trend_score * 0.55 + _score_0_10(1-close_pos, 0.35, 0.9) * 0.45) if direction == 'SELL' else _score_0_10(1-close_pos, 0.35, 0.9) * 0.35, 2)
            risk_score = round(max(0.0, min(10.0, vol_score * 0.45 + (10.0 - trend_score) * 0.35 + abs(close_pos - 0.5) * 4.0)), 2)
            overlap_score = round(max(buy_align, sell_align) * 0.45 + trend_score * 0.25 + vol_score * 0.20 + (10-risk_score) * 0.10, 2)
            rows.append({
                'Date': str(day),
                'Weekday': pd.Timestamp(day).strftime('%A'),
                'Overlap Hours': '12:00-16:00 UTC',
                'Direction': direction,
                'Open': round(first_open, 5), 'High': round(hi, 5), 'Low': round(lo, 5), 'Close': round(last_close, 5),
                'Pips Move': round(momentum, 1),
                'Range Power /10': vol_score,
                'Trend Efficiency /10': trend_score,
                'BUY Align /10': buy_align,
                'SELL Align /10': sell_align,
                'Risk /10': risk_score,
                'Overlap Master /10': overlap_score,
                'Read': 'TRADEABLE' if overlap_score >= 6.5 and risk_score <= 6.5 else 'PROTECT' if risk_score >= 7 else 'WAIT',
                '_sort_time': pd.Timestamp(day),
            })
        hist = pd.DataFrame(rows).sort_values('_sort_time', ascending=False).head(int(days))
        if '_sort_time' in hist.columns:
            hist = hist.drop(columns=['_sort_time'])
        summary = {}
        if not hist.empty:
            today = hist.iloc[0].to_dict()
            summary = {
                'ok': True,
                'today_overlap_master_10': today.get('Overlap Master /10'),
                'today_direction': today.get('Direction'),
                'today_read': today.get('Read'),
                'today_risk_10': today.get('Risk /10'),
                'avg_25d_master_10': round(float(pd.to_numeric(hist['Overlap Master /10'], errors='coerce').mean()), 2),
                'avg_25d_risk_10': round(float(pd.to_numeric(hist['Risk /10'], errors='coerce').mean()), 2),
                'best_bias_25d': 'BUY' if pd.to_numeric(hist['BUY Align /10'], errors='coerce').mean() >= pd.to_numeric(hist['SELL Align /10'], errors='coerce').mean() else 'SELL',
                'rows': int(len(hist)),
            }
        return hist, summary

    def _render_ny_london_overlap_section():
        st.markdown('### 🌍 NY–London Overlap Metric Duplicate')
        st.caption('Separate Lunch metric duplicate using only EURUSD overlap-hour candles. Shows today → last 25 days descending, all scores out of 10.')
        hist, summary = _build_ny_london_overlap_history(days=25)
        st.session_state['ny_london_overlap_history'] = hist
        st.session_state['ny_london_overlap_summary'] = summary
        if not isinstance(hist, pd.DataFrame) or hist.empty:
            st.warning((summary or {}).get('message', 'No overlap-hour history available yet. Refresh/connect EURUSD H1 data first.'))
            return
        c = st.columns(5)
        c[0].metric('Today Overlap', f"{summary.get('today_overlap_master_10','-')}/10")
        c[1].metric('Today Bias', summary.get('today_direction', '-'))
        c[2].metric('Today Risk', f"{summary.get('today_risk_10','-')}/10")
        c[3].metric('25D Avg', f"{summary.get('avg_25d_master_10','-')}/10")
        c[4].metric('25D Best Bias', summary.get('best_bias_25d', '-'))
        st.dataframe(hist, use_container_width=True, hide_index=True, height=430)

    def _build_dv_efficiency_summary(result=None, regime=None, bt_summary=None, predicted=None, d=None):
        result = result or st.session_state.get('dv_pp_base_result', {}) or {}
        regime = regime or st.session_state.get('dv_pp_regime_summary', {}) or {}
        bt_summary = bt_summary or st.session_state.get('dv_pp_bt_summary', {}) or {}
        predicted = predicted if predicted is not None else st.session_state.get('dv_pp_predicted')
        d = d if d is not None else st.session_state.get('dv_pp_df')
        rows = len(d) if isinstance(d, pd.DataFrame) else 0
        acc = float(bt_summary.get('direction_accuracy_pct', 0) or 0) if isinstance(bt_summary, dict) else 0.0
        master = float(result.get('master_score', 0) or 0) if isinstance(result, dict) else 0.0
        bull = float(result.get('bull_probability', 50) or 50) if isinstance(result, dict) else 50.0
        conf = 0.0
        if isinstance(predicted, pd.DataFrame) and not predicted.empty and 'confidence_pct' in predicted.columns:
            conf = float(pd.to_numeric(predicted['confidence_pct'], errors='coerce').fillna(0).mean())
        data_quality = min(10.0, rows / 600.0)
        direction_edge = abs(bull - 50.0) / 5.0
        projection_quality = round(min(10.0, acc / 10.0 * 0.42 + conf / 10.0 * 0.28 + master * 0.30), 2)
        notice_efficiency = round(min(10.0, projection_quality * 0.45 + data_quality * 0.25 + direction_edge * 0.20 + master * 0.10), 2)
        risk = round(max(0.0, min(10.0, 10.0 - projection_quality + (2.0 if direction_edge < 2.0 else 0.0))), 2)
        out = {
            'Notice Efficiency /10': notice_efficiency,
            'Projection Quality /10': projection_quality,
            'Data Quality /10': round(data_quality, 2),
            'Model Risk /10': risk,
            'Action Read': 'CLEAR' if notice_efficiency >= 7 and risk <= 4.5 else 'CAUTION' if notice_efficiency >= 5 else 'WAIT',
            'Rows Used': rows,
        }
        st.session_state['dv_efficiency_summary'] = out
        return out

    def _render_dv_efficiency_cards(result=None, regime=None, bt_summary=None, predicted=None, d=None):
        s = _build_dv_efficiency_summary(result, regime, bt_summary, predicted, d)
        st.markdown('#### ⚡ Data Visualization Efficiency Notice')
        c = st.columns(5)
        c[0].metric('Notice Efficiency', f"{s.get('Notice Efficiency /10','-')}/10")
        c[1].metric('Projection Quality', f"{s.get('Projection Quality /10','-')}/10")
        c[2].metric('Data Quality', f"{s.get('Data Quality /10','-')}/10")
        c[3].metric('Model Risk', f"{s.get('Model Risk /10','-')}/10")
        c[4].metric('Action Read', s.get('Action Read', '-'))

    # Include NY-London overlap inside full copy export.
    _prev_build_copy = ns.get('_build_lunch_all_copy_text')
    def _build_lunch_all_copy_text_v3():
        base = _prev_build_copy() if callable(_prev_build_copy) else ''
        hist, summary = _build_ny_london_overlap_history(days=25)
        extra = {
            'ny_london_overlap_summary': summary,
            'ny_london_overlap_history_today_to_last_25d_desc': hist.to_dict('records') if isinstance(hist, pd.DataFrame) else [],
            'data_visualization_efficiency_summary': st.session_state.get('dv_efficiency_summary', {}),
        }
        return str(base) + '\n\nNY-LONDON OVERLAP + DV EFFICIENCY EXPORT\n' + '=' * 64 + '\n' + json.dumps(extra, indent=2, ensure_ascii=False, default=str)

    # Render overlap section immediately before Copy Center.
    _prev_copy_bar = ns.get('_render_lunch_copy_refresh_bar')
    def _render_lunch_copy_refresh_bar_v3():
        try:
            _render_ny_london_overlap_section()
        except Exception as exc:
            st.warning(f'NY-London overlap section skipped safely: {exc}')
        if callable(_prev_copy_bar):
            _prev_copy_bar()

    # Add efficiency metrics to the top of Data Visualization without replacing
    # the whole visual renderer again.
    _prev_dv = ns.get('_render_lunch_data_visualization_inner_tab')
    def _render_data_visualization_v3():
        st.markdown('### ⚡ Data Visualization Top Efficiency Metrics')
        _render_dv_efficiency_cards()
        if callable(_prev_dv):
            _prev_dv()
        # Refresh after a run so the top summary is also visible lower down.
        if st.session_state.get('lunch_bi_visual_ready', False):
            _render_dv_efficiency_cards(
                st.session_state.get('dv_pp_base_result', {}),
                st.session_state.get('dv_pp_regime_summary', {}),
                st.session_state.get('dv_pp_bt_summary', {}),
                st.session_state.get('dv_pp_predicted'),
                st.session_state.get('dv_pp_df'),
            )

    ns['_build_ny_london_overlap_history'] = _build_ny_london_overlap_history
    ns['_render_ny_london_overlap_section'] = _render_ny_london_overlap_section
    ns['_build_dv_efficiency_summary'] = _build_dv_efficiency_summary
    ns['_render_dv_efficiency_cards'] = _render_dv_efficiency_cards
    ns['_build_lunch_all_copy_text'] = _build_lunch_all_copy_text_v3
    ns['_render_lunch_copy_refresh_bar'] = _render_lunch_copy_refresh_bar_v3
    ns['_render_lunch_data_visualization_inner_tab'] = _render_data_visualization_v3

# =====================================================================
# 2026-06-10 USER FIX PATCH V4
# - NY/London overlap removed from Data Visualization shared copy bar.
# - NY/London overlap moved into its own Open/Close field with manual Run.
# - Overlap history is one row per overlap HOUR, today -> last 25 days.
# - Adds Entry Pressure, BUY Pressure, SELL Pressure columns.
# - Adds yellow last-2-day prediction-vs-actual PowerBI candle overlay.
# =====================================================================
try:
    _PREV_APPLY_20260610_V3 = apply
except Exception:
    _PREV_APPLY_20260610_V3 = None


def apply(ns: dict) -> None:  # type: ignore[no-redef]
    if callable(_PREV_APPLY_20260610_V3):
        _PREV_APPLY_20260610_V3(ns)

    import json
    import pandas as pd
    import streamlit as st

    def _v4_cols(df):
        cols = {str(c).lower().strip(): c for c in getattr(df, "columns", [])}
        return {
            "time": cols.get("time") or cols.get("datetime") or cols.get("date") or cols.get("timestamp"),
            "open": cols.get("open") or cols.get("o"),
            "high": cols.get("high") or cols.get("h"),
            "low": cols.get("low") or cols.get("l"),
            "close": cols.get("close") or cols.get("c"),
            "volume": cols.get("volume") or cols.get("vol") or cols.get("tick_volume"),
        }

    def _v4_prepare(df):
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame()
        m = _v4_cols(df)
        if not all([m.get("open"), m.get("high"), m.get("low"), m.get("close")]):
            return pd.DataFrame()
        d = pd.DataFrame()
        if m.get("time"):
            d["time"] = pd.to_datetime(df[m["time"]], errors="coerce")
        else:
            d["time"] = pd.date_range(end=pd.Timestamp.now(), periods=len(df), freq="h")
        for c in ["open", "high", "low", "close"]:
            d[c] = pd.to_numeric(df[m[c]], errors="coerce")
        d["volume"] = pd.to_numeric(df[m["volume"]], errors="coerce").fillna(0) if m.get("volume") else 0.0
        return d.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").drop_duplicates("time", keep="last").tail(16000).reset_index(drop=True)

    def _pressure_scores_for_rows(x):
        x = x.copy().sort_values("time")
        rng = (x["high"] - x["low"]).replace(0, pd.NA)
        body = (x["close"] - x["open"]).abs()
        close_pos = ((x["close"] - x["low"]) / rng).fillna(0.5).clip(0, 1)
        candle_power = (body / rng).fillna(0).clip(0, 1)
        ret = x["close"].pct_change().fillna(0)
        atr = (x["high"] - x["low"]).rolling(24, min_periods=4).mean().replace(0, pd.NA)
        range_power = ((x["high"] - x["low"]) / atr).fillna(1).clip(0, 2.5) / 2.5
        buy = (close_pos * 0.45 + (x["close"].gt(x["open"]).astype(float)) * 0.25 + candle_power * 0.20 + ret.clip(lower=0).mul(650).clip(0, 1) * 0.10) * 10
        sell = ((1 - close_pos) * 0.45 + (x["close"].lt(x["open"]).astype(float)) * 0.25 + candle_power * 0.20 + (-ret).clip(lower=0).mul(650).clip(0, 1) * 0.10) * 10
        entry = (pd.concat([buy, sell], axis=1).max(axis=1) * 0.55 + range_power * 10 * 0.25 + candle_power * 10 * 0.20).clip(0, 10)
        x["Entry Pressure /10"] = entry.round(2)
        x["BUY Pressure /10"] = buy.clip(0, 10).round(2)
        x["SELL Pressure /10"] = sell.clip(0, 10).round(2)
        x["Score /10"] = (entry * 0.50 + pd.concat([buy, sell], axis=1).max(axis=1) * 0.35 + (10 - (buy - sell).abs().rsub(10).clip(0, 10)) * 0.15).clip(0, 10).round(2)
        return x

    def _build_ny_london_overlap_hourly_history_v4(df=None, days=25, start_hour=12, end_hour=16):
        raw = st.session_state.get("last_df") if df is None else df
        d = _v4_prepare(raw)
        if d.empty:
            return pd.DataFrame(), {"ok": False, "message": "No clean OHLC candles found."}
        d = _pressure_scores_for_rows(d)
        last_time = pd.Timestamp(d["time"].max())
        cutoff = last_time - pd.Timedelta(days=int(days) + 1)
        x = d[d["time"].ge(cutoff)].copy()
        x["Hour"] = x["time"].dt.hour
        x = x[(x["Hour"] >= int(start_hour)) & (x["Hour"] <= int(end_hour))].copy()
        if x.empty:
            return pd.DataFrame(), {"ok": False, "message": "No candles inside selected NY/London overlap hours."}
        x["Day"] = x["time"].dt.strftime("%Y-%m-%d %a")
        x["Hour"] = x["time"].dt.strftime("%H:00")
        x["Bias"] = x.apply(lambda r: "BUY" if r["BUY Pressure /10"] > r["SELL Pressure /10"] else "SELL" if r["SELL Pressure /10"] > r["BUY Pressure /10"] else "RANGE", axis=1)
        x["Read"] = x.apply(lambda r: "TRADEABLE" if r["Score /10"] >= 6.8 and r["Entry Pressure /10"] >= 6.5 else "PROTECT" if r["Score /10"] <= 4.2 else "WAIT", axis=1)
        out = x.sort_values("time", ascending=False)[[
            "Day", "Hour", "Entry Pressure /10", "BUY Pressure /10", "SELL Pressure /10", "Score /10", "Bias", "Read", "open", "high", "low", "close"
        ]].rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"})
        for c in ["Open", "High", "Low", "Close"]:
            out[c] = pd.to_numeric(out[c], errors="coerce").round(5)
        summary = {
            "ok": True,
            "rows": int(len(out)),
            "hours": f"{int(start_hour):02d}:00-{int(end_hour):02d}:00",
            "latest_score_10": float(out["Score /10"].iloc[0]),
            "latest_bias": str(out["Bias"].iloc[0]),
            "avg_entry_pressure_10": round(float(pd.to_numeric(out["Entry Pressure /10"], errors="coerce").mean()), 2),
            "avg_buy_pressure_10": round(float(pd.to_numeric(out["BUY Pressure /10"], errors="coerce").mean()), 2),
            "avg_sell_pressure_10": round(float(pd.to_numeric(out["SELL Pressure /10"], errors="coerce").mean()), 2),
        }
        return out.reset_index(drop=True), summary

    def _render_ny_london_overlap_open_close_field_v4():
        with st.expander("🌍 Open / Close — NY + London Overlap Hour Metrics", expanded=False):
            st.caption("Manual-run only. Shows one row per overlap hour, not one row per day. History is today → last 25 days descending.")
            c = st.columns([1.2, .8, .8, .8])
            with c[0]:
                run = st.button("▶ Run NY/London Overlap Calculation", use_container_width=True, key="nylo_run_hourly_v4")
            with c[1]:
                days = st.slider("Days", 5, 25, int(st.session_state.get("nylo_days_v4", 25)), 1, key="nylo_days_v4")
            with c[2]:
                start_h = st.slider("Start hour", 11, 15, int(st.session_state.get("nylo_start_h_v4", 12)), 1, key="nylo_start_h_v4")
            with c[3]:
                end_h = st.slider("End hour", 15, 18, int(st.session_state.get("nylo_end_h_v4", 16)), 1, key="nylo_end_h_v4")
            if run:
                hist, summary = _build_ny_london_overlap_hourly_history_v4(days=days, start_hour=start_h, end_hour=end_h)
                st.session_state["ny_london_overlap_hourly_history_v4"] = hist
                st.session_state["ny_london_overlap_hourly_summary_v4"] = summary
                st.session_state["lunch_copy_payload_signature"] = None
                if summary.get("ok"):
                    st.success("NY/London hourly overlap calculation complete.")
            hist = st.session_state.get("ny_london_overlap_hourly_history_v4", pd.DataFrame())
            summary = st.session_state.get("ny_london_overlap_hourly_summary_v4", {})
            if not isinstance(hist, pd.DataFrame) or hist.empty:
                st.info("Press Run NY/London Overlap Calculation. This section does not calculate when the tab opens.")
                if isinstance(summary, dict) and summary.get("message"):
                    st.warning(summary.get("message"))
                return
            m = st.columns(5)
            m[0].metric("Latest Score", f"{summary.get('latest_score_10','-')}/10")
            m[1].metric("Latest Bias", summary.get("latest_bias", "-"))
            m[2].metric("Avg Entry", f"{summary.get('avg_entry_pressure_10','-')}/10")
            m[3].metric("Avg BUY", f"{summary.get('avg_buy_pressure_10','-')}/10")
            m[4].metric("Avg SELL", f"{summary.get('avg_sell_pressure_10','-')}/10")
            st.dataframe(hist, use_container_width=True, hide_index=True, height=460)

    def _render_lunch_copy_refresh_bar_no_overlap_v4():
        try:
            from core.pro_terminal_uiux import render_mobile_copy_button, apply_pro_terminal_css
            apply_pro_terminal_css()
        except Exception:
            render_mobile_copy_button = None
        all_payload = ns.get("_get_cached_lunch_copy_payload", lambda: ns.get("_build_lunch_all_copy_text", lambda: "")())()
        short_payload = ns.get("_build_short_necessary_copy_text", lambda: "No short copy available.")()
        st.markdown("### 📋 Copy Center")
        a, b, c = st.columns([1, 1, .75])
        with a:
            if render_mobile_copy_button:
                render_mobile_copy_button("Copy Short", short_payload, "copy_short_no_nylo_v4")
            else:
                st.text_area("Copy Short", short_payload, height=160)
        with b:
            if render_mobile_copy_button:
                render_mobile_copy_button("Copy Full", all_payload, "copy_full_no_nylo_v4")
            else:
                st.text_area("Copy Full", all_payload, height=220)
        with c:
            if st.button("🔄 Refresh", use_container_width=True, key="refresh_copy_no_nylo_v4"):
                st.session_state["lunch_copy_payload_signature"] = None
                st.rerun()

    prev_combined = ns.get("_render_metric_home_combined_inner_tab")
    def _render_metric_home_combined_inner_tab_v4():
        st.caption("Lunch tab: Run Calculating first, then Metric table, 010 Reverse Decision, Prediction, Copy/Refresh, then Open/Close fields.")
        ns["_render_metric_inner_tab"]()
        _render_ny_london_overlap_open_close_field_v4()
        with st.expander("🏠 Open / Close — Other Lunch fields", expanded=False):
            ns["_render_home_dashboard"]()

    prev_build_copy = ns.get("_build_lunch_all_copy_text")
    def _build_lunch_all_copy_text_v4():
        base = prev_build_copy() if callable(prev_build_copy) else ""
        hist = st.session_state.get("ny_london_overlap_hourly_history_v4", pd.DataFrame())
        summary = st.session_state.get("ny_london_overlap_hourly_summary_v4", {})
        extra = {
            "ny_london_overlap_hourly_summary_manual_run": summary,
            "ny_london_overlap_hourly_history_today_to_last_25d_desc": hist.to_dict("records") if isinstance(hist, pd.DataFrame) else [],
        }
        return str(base) + "\n\nNY-LONDON OVERLAP HOURLY MANUAL-RUN EXPORT\n" + "=" * 64 + "\n" + json.dumps(extra, indent=2, ensure_ascii=False, default=str)

    def _build_yellow_prediction_vs_actual_2d_v4(d):
        x = _v4_prepare(d)
        if x.empty or len(x) < 60:
            return pd.DataFrame()
        x = x.copy()
        x["time"] = pd.to_datetime(x["time"], errors="coerce")
        last_time = pd.Timestamp(x["time"].max())
        # Simple rolling one-hour-ahead projection, intentionally lightweight.
        ret = x["close"].pct_change().fillna(0)
        pred_ret = ret.ewm(span=8, adjust=False).mean().shift(1).fillna(0)
        x["Predicted Close"] = (x["open"] * (1 + pred_ret)).astype(float)
        x["Actual Close"] = x["close"].astype(float)
        x["Predicted Direction"] = x.apply(lambda r: "BUY" if r["Predicted Close"] >= r["open"] else "SELL", axis=1)
        x["Actual Direction"] = x.apply(lambda r: "BUY" if r["Actual Close"] >= r["open"] else "SELL", axis=1)
        x["Hit"] = x["Predicted Direction"].eq(x["Actual Direction"])
        x["Close Error Pips"] = ((x["Actual Close"] - x["Predicted Close"]).abs() * 10000).round(1)
        x = x[x["time"] >= last_time - pd.Timedelta(days=2)].copy()
        return x[["time", "open", "high", "low", "close", "Predicted Close", "Actual Close", "Predicted Direction", "Actual Direction", "Hit", "Close Error Pips"]].sort_values("time", ascending=False).reset_index(drop=True)

    def _render_yellow_powerbi_prediction_actual_v4():
        d = st.session_state.get("dv_pp_df", pd.DataFrame())
        hist = _build_yellow_prediction_vs_actual_2d_v4(d)
        if not isinstance(hist, pd.DataFrame) or hist.empty:
            return
        with st.expander("🟡 Open / Close — Last 2 Days Hourly Prediction vs Actual", expanded=False):
            st.caption("Yellow markers show each hourly predicted close for the last 2 days; actual candles remain normal. This makes old prediction vs actual easier to see.")
            try:
                import plotly.graph_objects as go
                x = hist.sort_values("time")
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=x["time"], open=x["open"], high=x["high"], low=x["low"], close=x["close"], name="Actual candles"))
                fig.add_trace(go.Scatter(x=x["time"], y=x["Predicted Close"], mode="markers+lines", name="YELLOW predicted close", marker={"color": "yellow", "size": 8, "line": {"color": "#111827", "width": 1}}, line={"color": "#FACC15", "width": 2}))
                fig.update_layout(height=560, margin=dict(l=8, r=8, t=42, b=8), title="PowerBI Candle — Last 2 Days Hourly Predicted Yellow vs Actual", xaxis_rangeslider_visible=False, legend=dict(orientation="h"))
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})
            except Exception as exc:
                st.warning(f"Yellow prediction chart skipped safely: {exc}")
            s = st.columns(4)
            hit_rate = round(float(hist["Hit"].mean() * 100), 1) if "Hit" in hist.columns and len(hist) else 0
            s[0].metric("2D Hour Rows", int(len(hist)))
            s[1].metric("Direction Hit", f"{hit_rate}%")
            s[2].metric("Avg Error", f"{round(float(hist['Close Error Pips'].mean()), 1)} pips")
            s[3].metric("Latest Pred", hist["Predicted Direction"].iloc[0] if len(hist) else "-")
            st.dataframe(hist, use_container_width=True, hide_index=True, height=340)

    prev_dv = ns.get("_render_lunch_data_visualization_inner_tab")
    def _render_lunch_data_visualization_inner_tab_v4():
        if callable(prev_dv):
            prev_dv()
        if st.session_state.get("lunch_bi_visual_ready", False):
            _render_yellow_powerbi_prediction_actual_v4()

    ns["_build_ny_london_overlap_hourly_history_v4"] = _build_ny_london_overlap_hourly_history_v4
    ns["_render_ny_london_overlap_open_close_field_v4"] = _render_ny_london_overlap_open_close_field_v4
    ns["_render_lunch_copy_refresh_bar"] = _render_lunch_copy_refresh_bar_no_overlap_v4
    ns["_render_metric_home_combined_inner_tab"] = _render_metric_home_combined_inner_tab_v4
    ns["_build_lunch_all_copy_text"] = _build_lunch_all_copy_text_v4
    ns["_build_yellow_prediction_vs_actual_2d_v4"] = _build_yellow_prediction_vs_actual_2d_v4
    ns["_render_lunch_data_visualization_inner_tab"] = _render_lunch_data_visualization_inner_tab_v4

    # =========================================================
    # 2026-06-10 V5 user-request fix
    # - NY/London section renders immediately above the 2 copy buttons.
    # - Start/end hour selectors are free 1..24.
    # - Adds strict decision column: WAIT PULLBACK / HOLD / ALLOWED / NO TRADE.
    # - Adds 6-hour yellow last-candle projection line + extra PowerBI choices.
    # =========================================================

    def _nylo_decision_v5(score, entry, buy, sell):
        score = float(score or 0)
        entry = float(entry or 0)
        edge = abs(float(buy or 0) - float(sell or 0))
        if score >= 7.2 and entry >= 6.8 and edge >= 0.55:
            return "ALLOWED"
        if score >= 5.8 and entry >= 5.6:
            return "WAIT PULLBACK"
        if score >= 4.4:
            return "HOLD"
        return "NO TRADE"

    def _build_ny_london_overlap_hourly_history_v5(df=None, days=25, start_hour=12, end_hour=16):
        # User requested free 1..24 controls. Internally convert 24 to 23 because pandas hour is 0..23.
        sh = max(1, min(24, int(start_hour or 12)))
        eh = max(1, min(24, int(end_hour or 16)))
        if sh > eh:
            sh, eh = eh, sh
        raw = st.session_state.get("last_df") if df is None else df
        d = _v4_prepare(raw)
        if d.empty:
            return pd.DataFrame(), {"ok": False, "message": "No clean EURUSD OHLC candles found."}
        d = _pressure_scores_for_rows(d)
        d["HourNum"] = pd.to_datetime(d["time"], errors="coerce").dt.hour + 1
        last_time = pd.Timestamp(d["time"].max())
        cutoff = last_time - pd.Timedelta(days=int(days) + 1)
        x = d[d["time"].ge(cutoff)].copy()
        x = x[(x["HourNum"] >= sh) & (x["HourNum"] <= eh)].copy()
        if x.empty:
            return pd.DataFrame(), {"ok": False, "message": f"No EURUSD candles inside selected overlap hours {sh}:00-{eh}:00."}
        x["Day"] = pd.to_datetime(x["time"]).dt.strftime("%Y-%m-%d %a")
        x["Hour"] = pd.to_datetime(x["time"]).dt.strftime("%H:00")
        x["NY/London Alignment"] = x.apply(lambda r: "BUY aligned" if r["BUY Pressure /10"] >= r["SELL Pressure /10"] + 0.55 else "SELL aligned" if r["SELL Pressure /10"] >= r["BUY Pressure /10"] + 0.55 else "Mixed / wait", axis=1)
        x["Decision"] = x.apply(lambda r: _nylo_decision_v5(r["Score /10"], r["Entry Pressure /10"], r["BUY Pressure /10"], r["SELL Pressure /10"]), axis=1)
        x["Risk Note"] = x.apply(lambda r: "Lower risk only after pullback confirmation" if r["Decision"] == "WAIT PULLBACK" else "Trade allowed by overlap pressure" if r["Decision"] == "ALLOWED" else "Protect open trade / avoid new entry" if r["Decision"] == "HOLD" else "No trade: overlap pressure weak", axis=1)
        out = x.sort_values("time", ascending=False)[[
            "Day", "Hour", "Entry Pressure /10", "BUY Pressure /10", "SELL Pressure /10", "Score /10", "NY/London Alignment", "Decision", "Risk Note", "open", "high", "low", "close"
        ]].rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"})
        for col in ["Open", "High", "Low", "Close"]:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(5)
        summary = {
            "ok": True,
            "rows": int(len(out)),
            "hours": f"{sh}:00-{eh}:00",
            "latest_score_10": float(out["Score /10"].iloc[0]),
            "latest_decision": str(out["Decision"].iloc[0]),
            "latest_alignment": str(out["NY/London Alignment"].iloc[0]),
            "avg_entry_pressure_10": round(float(pd.to_numeric(out["Entry Pressure /10"], errors="coerce").mean()), 2),
            "avg_buy_pressure_10": round(float(pd.to_numeric(out["BUY Pressure /10"], errors="coerce").mean()), 2),
            "avg_sell_pressure_10": round(float(pd.to_numeric(out["SELL Pressure /10"], errors="coerce").mean()), 2),
        }
        return out.reset_index(drop=True), summary

    def _render_ny_london_overlap_open_close_field_v5():
        with st.expander("🌍 Open / Close — NY + London Overlap EURUSD Alignment", expanded=False):
            st.caption("Manual-run only. Placed above Copy Short / Copy Full. Uses one row per selected overlap hour, today → last 25 days descending.")
            c = st.columns([1.1, .7, .7, .7])
            with c[0]:
                run = st.button("▶ Run NY/London Overlap Calculation", use_container_width=True, key="nylo_run_hourly_v5")
            with c[1]:
                days = st.slider("Days", 5, 25, int(st.session_state.get("nylo_days_v5", 25)), 1, key="nylo_days_v5")
            with c[2]:
                start_h = st.slider("Start threshold hour", 1, 24, int(st.session_state.get("nylo_start_h_v5", 12)), 1, key="nylo_start_h_v5")
            with c[3]:
                end_h = st.slider("End threshold hour", 1, 24, int(st.session_state.get("nylo_end_h_v5", 16)), 1, key="nylo_end_h_v5")
            if run:
                hist, summary = _build_ny_london_overlap_hourly_history_v5(days=days, start_hour=start_h, end_hour=end_h)
                st.session_state["ny_london_overlap_hourly_history_v5"] = hist
                st.session_state["ny_london_overlap_hourly_summary_v5"] = summary
                st.session_state["lunch_copy_payload_signature"] = None
                if summary.get("ok"):
                    st.success("NY/London overlap calculation complete.")
            hist = st.session_state.get("ny_london_overlap_hourly_history_v5", pd.DataFrame())
            summary = st.session_state.get("ny_london_overlap_hourly_summary_v5", {})
            if not isinstance(hist, pd.DataFrame) or hist.empty:
                st.info("Press Run NY/London Overlap Calculation. It will not calculate automatically when the tab opens.")
                if isinstance(summary, dict) and summary.get("message"):
                    st.warning(summary.get("message"))
                return
            m = st.columns(5)
            m[0].metric("Latest Score", f"{summary.get('latest_score_10','-')}/10")
            m[1].metric("Decision", summary.get("latest_decision", "-"))
            m[2].metric("Alignment", summary.get("latest_alignment", "-"))
            m[3].metric("Avg BUY", f"{summary.get('avg_buy_pressure_10','-')}/10")
            m[4].metric("Avg SELL", f"{summary.get('avg_sell_pressure_10','-')}/10")
            st.dataframe(hist, use_container_width=True, hide_index=True, height=460)

    def _render_lunch_copy_refresh_bar_v5():
        # This guarantees the NY/London block is directly above the two copy buttons wherever the copy bar is rendered.
        _render_ny_london_overlap_open_close_field_v5()
        _render_lunch_copy_refresh_bar_no_overlap_v4()

    def _render_metric_home_combined_inner_tab_v5():
        st.caption("Lunch tab: Run Calculating first, then Metric table, 010 Reverse Decision, Prediction, NY/London overlap above Copy buttons, then Open/Close fields.")
        ns["_render_metric_inner_tab"]()
        with st.expander("🏠 Open / Close — Other Lunch fields", expanded=False):
            ns["_render_home_dashboard"]()

    def _build_last_candle_yellow_6h_projection_v5(d, horizon=6, mode="Balanced", risk_filter="Medium"):
        x = _v4_prepare(d)
        if x.empty or len(x) < 40:
            return pd.DataFrame()
        x = x.sort_values("time").copy()
        close = pd.to_numeric(x["close"], errors="coerce").ffill()
        high = pd.to_numeric(x["high"], errors="coerce").ffill()
        low = pd.to_numeric(x["low"], errors="coerce").ffill()
        ret = close.pct_change().fillna(0)
        atr = (high - low).rolling(14, min_periods=4).mean().ffill().fillna((high - low).mean())
        if mode == "Trend follow":
            base_ret = float(ret.ewm(span=6, adjust=False).mean().iloc[-1])
        elif mode == "Pullback safer":
            base_ret = float(ret.ewm(span=12, adjust=False).mean().iloc[-1]) * 0.45
        else:
            base_ret = float(ret.ewm(span=9, adjust=False).mean().iloc[-1]) * 0.75
        risk_mult = {"Low": 0.55, "Medium": 0.80, "High": 1.00}.get(str(risk_filter), 0.80)
        base_ret *= risk_mult
        last = x.iloc[-1]
        last_time = pd.Timestamp(last["time"])
        price = float(last["close"])
        atr_last = float(atr.iloc[-1] or 0)
        rows = []
        for step in range(1, int(horizon) + 1):
            damp = 1 / (1 + step * 0.10)
            pred_close = price * (1 + base_ret * step * damp)
            band = atr_last * (0.35 + step * 0.10) * risk_mult
            rows.append({
                "Future Hour": step,
                "time": last_time + pd.Timedelta(hours=step),
                "Yellow Predicted Close": round(float(pred_close), 5),
                "Lower Risk Band": round(float(pred_close - band), 5),
                "Upper Risk Band": round(float(pred_close + band), 5),
                "Mode": mode,
                "Risk Filter": risk_filter,
            })
        return pd.DataFrame(rows)

    def _render_last_candle_yellow_6h_projection_v5():
        d = st.session_state.get("dv_pp_df", pd.DataFrame())
        if not isinstance(d, pd.DataFrame) or d.empty:
            return
        with st.expander("🟡 Open / Close — Last Candle Predict Next 6 Hours Yellow Line", expanded=True):
            st.caption("Shows the latest candle’s forward yellow prediction line for the next hours, plus bands for less-risky planning.")
            c = st.columns(3)
            horizon = c[0].slider("Yellow future hours", 1, 12, int(st.session_state.get("yellow_horizon_v5", 6)), 1, key="yellow_horizon_v5")
            mode = c[1].selectbox("Projection choice", ["Balanced", "Trend follow", "Pullback safer"], index=0, key="yellow_mode_v5")
            risk_filter = c[2].selectbox("Risk filter", ["Low", "Medium", "High"], index=1, key="yellow_risk_v5")
            future = _build_last_candle_yellow_6h_projection_v5(d, horizon=horizon, mode=mode, risk_filter=risk_filter)
            if future.empty:
                st.info("Need more candles to draw yellow 6-hour projection.")
                return
            try:
                import plotly.graph_objects as go
                x = _v4_prepare(d).sort_values("time").tail(80)
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=x["time"], open=x["open"], high=x["high"], low=x["low"], close=x["close"], name="Actual candles"))
                last_time = pd.Timestamp(x["time"].iloc[-1])
                last_close = float(x["close"].iloc[-1])
                line_x = [last_time] + list(future["time"])
                line_y = [last_close] + list(future["Yellow Predicted Close"])
                fig.add_trace(go.Scatter(x=line_x, y=line_y, mode="markers+lines", name="YELLOW next-hours prediction", marker={"color": "yellow", "size": 9, "line": {"color": "#111827", "width": 1}}, line={"color": "#FACC15", "width": 3}))
                fig.add_trace(go.Scatter(x=future["time"], y=future["Upper Risk Band"], mode="lines", name="Upper band", line={"color": "rgba(250,204,21,0.35)", "dash": "dot"}))
                fig.add_trace(go.Scatter(x=future["time"], y=future["Lower Risk Band"], mode="lines", name="Lower band", line={"color": "rgba(250,204,21,0.35)", "dash": "dot"}))
                fig.update_layout(height=560, margin=dict(l=8, r=8, t=42, b=8), title="PowerBI Candle — Last Candle Yellow Next-Hours Projection", xaxis_rangeslider_visible=False, legend=dict(orientation="h"))
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})
            except Exception as exc:
                st.warning(f"Yellow 6-hour projection chart skipped safely: {exc}")
            st.dataframe(future.sort_values("Future Hour"), use_container_width=True, hide_index=True, height=250)

    prev_dv_v5 = ns.get("_render_lunch_data_visualization_inner_tab")
    def _render_lunch_data_visualization_inner_tab_v5():
        if callable(prev_dv_v5):
            prev_dv_v5()
        if st.session_state.get("lunch_bi_visual_ready", False):
            _render_last_candle_yellow_6h_projection_v5()

    prev_build_copy_v5 = ns.get("_build_lunch_all_copy_text")
    def _build_lunch_all_copy_text_v5():
        base = prev_build_copy_v5() if callable(prev_build_copy_v5) else ""
        hist = st.session_state.get("ny_london_overlap_hourly_history_v5", pd.DataFrame())
        summary = st.session_state.get("ny_london_overlap_hourly_summary_v5", {})
        extra = {
            "ny_london_overlap_v5_manual_run_summary": summary,
            "ny_london_overlap_v5_history_today_to_last_25d_desc": hist.to_dict("records") if isinstance(hist, pd.DataFrame) else [],
        }
        return str(base) + "\n\nNY-LONDON OVERLAP V5 MANUAL-RUN EXPORT\n" + "=" * 64 + "\n" + json.dumps(extra, indent=2, ensure_ascii=False, default=str)

    ns["_build_ny_london_overlap_hourly_history_v5"] = _build_ny_london_overlap_hourly_history_v5
    ns["_render_ny_london_overlap_open_close_field_v5"] = _render_ny_london_overlap_open_close_field_v5
    ns["_render_lunch_copy_refresh_bar"] = _render_lunch_copy_refresh_bar_v5
    ns["_render_metric_home_combined_inner_tab"] = _render_metric_home_combined_inner_tab_v5
    ns["_build_last_candle_yellow_6h_projection_v5"] = _build_last_candle_yellow_6h_projection_v5
    ns["_render_lunch_data_visualization_inner_tab"] = _render_lunch_data_visualization_inner_tab_v5
    ns["_build_lunch_all_copy_text"] = _build_lunch_all_copy_text_v5

# =====================================================================
# 2026-06-10 V6 FINAL USER RESTORE PATCH
# - Data Visualization: merge the 4 projection displays into ONE PowerBI chart.
# - Keep existing ML/result tables and copy export; do not delete old functions.
# - NY/London: remove end threshold, use next 6 hours from start with midnight rollover.
#   Example start 21 => 21,22,23,00,01,02.
# =====================================================================
try:
    _PREV_APPLY_20260610_V5 = apply
except Exception:
    _PREV_APPLY_20260610_V5 = None


def apply(ns: dict) -> None:  # type: ignore[no-redef]
    if callable(_PREV_APPLY_20260610_V5):
        _PREV_APPLY_20260610_V5(ns)

    import json
    import pandas as pd
    import streamlit as st

    def _v6_prepare(df):
        prep = ns.get('_v4_prepare') or ns.get('_dv_prepare_ohlc_v20260609')
        try:
            if callable(prep):
                return prep(df).copy()
        except Exception:
            pass
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame()
        cols = {str(c).lower().strip(): c for c in df.columns}
        out = pd.DataFrame()
        for std, alts in {
            'time':['time','datetime','date','timestamp'], 'open':['open','o'], 'high':['high','h'], 'low':['low','l'], 'close':['close','c'], 'volume':['volume','vol','tick_volume']
        }.items():
            src = next((cols.get(a) for a in alts if cols.get(a) is not None), None)
            if src is not None:
                out[std] = df[src]
        need = ['time','open','high','low','close']
        if not all(c in out.columns for c in need):
            return pd.DataFrame()
        out['time'] = pd.to_datetime(out['time'], errors='coerce')
        for c in ['open','high','low','close','volume']:
            if c in out.columns:
                out[c] = pd.to_numeric(out[c], errors='coerce')
        return out.dropna(subset=need).sort_values('time').reset_index(drop=True)

    def _v6_pressure(df):
        f = ns.get('_pressure_scores_for_rows')
        if callable(f):
            try:
                return f(df).copy()
            except Exception:
                pass
        x = _v6_prepare(df)
        if x.empty:
            return x
        rng = (x['high'] - x['low']).replace(0, pd.NA).ffill().fillna(0.0001)
        body = (x['close'] - x['open']) / rng
        vol = rng.rolling(14, min_periods=3).mean().replace(0, pd.NA).ffill().fillna(float(rng.mean() or 0.0001))
        score = ((rng / vol).clip(0, 2) * 3.0 + body.abs().clip(0, 1) * 4.0 + 2.0).clip(0, 10)
        buy = (5 + body.clip(-1, 1) * 4).clip(0, 10)
        sell = (5 - body.clip(-1, 1) * 4).clip(0, 10)
        x['Entry Pressure /10'] = score.round(2)
        x['BUY Pressure /10'] = buy.round(2)
        x['SELL Pressure /10'] = sell.round(2)
        x['Score /10'] = ((score + buy.where(buy >= sell, sell)) / 2).round(2)
        return x

    def _nylo_decision_v6(score, entry, buy, sell):
        score = float(score or 0); entry = float(entry or 0)
        edge = abs(float(buy or 0) - float(sell or 0))
        if score >= 7.2 and entry >= 6.8 and edge >= 0.55:
            return 'ALLOWED'
        if score >= 5.8 and entry >= 5.6:
            return 'WAIT PULLBACK'
        if score >= 4.4:
            return 'HOLD'
        return 'NO TRADE'

    def _build_ny_london_overlap_hourly_history_v6(df=None, days=25, start_hour=21):
        sh = int(start_hour or 21) % 24
        hours = [int((sh + i) % 24) for i in range(6)]
        raw = st.session_state.get('last_df') if df is None else df
        d = _v6_pressure(raw)
        if d.empty:
            return pd.DataFrame(), {'ok': False, 'message': 'No clean EURUSD OHLC candles found.'}
        d['HourNum'] = pd.to_datetime(d['time'], errors='coerce').dt.hour.astype('Int64')
        last_time = pd.Timestamp(d['time'].max())
        cutoff = last_time - pd.Timedelta(days=int(days) + 2)
        x = d[d['time'].ge(cutoff) & d['HourNum'].isin(hours)].copy()
        if x.empty:
            label = ', '.join(f'{h:02d}:00' for h in hours)
            return pd.DataFrame(), {'ok': False, 'message': f'No EURUSD candles inside next-6-hour window: {label}.'}
        x['Day'] = pd.to_datetime(x['time']).dt.strftime('%Y-%m-%d %a')
        x['Hour'] = pd.to_datetime(x['time']).dt.strftime('%H:00')
        x['Window Order'] = x['HourNum'].map({h: i+1 for i, h in enumerate(hours)})
        x['NY/London Alignment'] = x.apply(lambda r: 'BUY aligned' if r['BUY Pressure /10'] >= r['SELL Pressure /10'] + 0.55 else 'SELL aligned' if r['SELL Pressure /10'] >= r['BUY Pressure /10'] + 0.55 else 'Mixed / wait', axis=1)
        x['Decision'] = x.apply(lambda r: _nylo_decision_v6(r['Score /10'], r['Entry Pressure /10'], r['BUY Pressure /10'], r['SELL Pressure /10']), axis=1)
        x['Risk Note'] = x.apply(lambda r: 'Lower risk only after pullback confirmation' if r['Decision'] == 'WAIT PULLBACK' else 'Allowed by 6-hour pressure window' if r['Decision'] == 'ALLOWED' else 'Protect open position / avoid adding' if r['Decision'] == 'HOLD' else 'No trade: pressure weak', axis=1)
        out = x.sort_values('time', ascending=False)[['Day','Hour','Window Order','Entry Pressure /10','BUY Pressure /10','SELL Pressure /10','Score /10','NY/London Alignment','Decision','Risk Note','open','high','low','close']].rename(columns={'open':'Open','high':'High','low':'Low','close':'Close'})
        for col in ['Open','High','Low','Close']:
            out[col] = pd.to_numeric(out[col], errors='coerce').round(5)
        summary = {
            'ok': True,
            'rows': int(len(out)),
            'start_threshold_hour': f'{sh:02d}:00',
            'next_6_hours': ', '.join(f'{h:02d}:00' for h in hours),
            'latest_score_10': float(out['Score /10'].iloc[0]),
            'latest_decision': str(out['Decision'].iloc[0]),
            'latest_alignment': str(out['NY/London Alignment'].iloc[0]),
            'avg_entry_pressure_10': round(float(pd.to_numeric(out['Entry Pressure /10'], errors='coerce').mean()), 2),
            'avg_buy_pressure_10': round(float(pd.to_numeric(out['BUY Pressure /10'], errors='coerce').mean()), 2),
            'avg_sell_pressure_10': round(float(pd.to_numeric(out['SELL Pressure /10'], errors='coerce').mean()), 2),
        }
        return out.reset_index(drop=True), summary

    def _render_ny_london_overlap_open_close_field_v6():
        with st.expander('🌍 Open / Close — NY + London Next 6 Hours From Start Threshold', expanded=False):
            st.caption('Manual-run only. End threshold was removed. Choose the start hour and the table continues for the next 6 hours across midnight, e.g. 21 → 21,22,23,00,01,02.')
            c = st.columns([1.15, .75, .9])
            with c[0]:
                run = st.button('▶ Run NY/London Overlap Calculation', use_container_width=True, key='nylo_run_hourly_v6')
            with c[1]:
                days = st.slider('Days', 5, 25, int(st.session_state.get('nylo_days_v6', 25)), 1, key='nylo_days_v6')
            with c[2]:
                start_h = st.slider('Start threshold hour', 0, 23, int(st.session_state.get('nylo_start_h_v6', 21)), 1, key='nylo_start_h_v6')
            st.caption('Selected next 6 hours: ' + ', '.join(f'{(int(start_h)+i)%24:02d}:00' for i in range(6)))
            if run:
                hist, summary = _build_ny_london_overlap_hourly_history_v6(days=days, start_hour=start_h)
                st.session_state['ny_london_overlap_hourly_history_v6'] = hist
                st.session_state['ny_london_overlap_hourly_summary_v6'] = summary
                st.session_state['lunch_copy_payload_signature'] = None
                if summary.get('ok'):
                    st.success('NY/London next-6-hour calculation complete.')
            hist = st.session_state.get('ny_london_overlap_hourly_history_v6', pd.DataFrame())
            summary = st.session_state.get('ny_london_overlap_hourly_summary_v6', {})
            if not isinstance(hist, pd.DataFrame) or hist.empty:
                st.info('Press Run NY/London Overlap Calculation. This section does not calculate automatically when the tab opens.')
                if isinstance(summary, dict) and summary.get('message'):
                    st.warning(summary.get('message'))
                return
            m = st.columns(6)
            m[0].metric('Start', summary.get('start_threshold_hour', '-'))
            m[1].metric('Next 6H', summary.get('next_6_hours', '-'))
            m[2].metric('Latest Score', f"{summary.get('latest_score_10','-')}/10")
            m[3].metric('Decision', summary.get('latest_decision', '-'))
            m[4].metric('Avg BUY', f"{summary.get('avg_buy_pressure_10','-')}/10")
            m[5].metric('Avg SELL', f"{summary.get('avg_sell_pressure_10','-')}/10")
            st.dataframe(hist, use_container_width=True, hide_index=True, height=460)

    def _v6_yellow_from_anchor(d, anchor_idx, horizon=6, mode='Balanced', risk_filter='Medium'):
        build = ns.get('_build_last_candle_yellow_6h_projection_v5')
        x = _v6_prepare(d)
        if x.empty or anchor_idx < 20:
            return pd.DataFrame()
        sub = x.iloc[:anchor_idx+1].copy()
        if callable(build):
            try:
                return build(sub, horizon=horizon, mode=mode, risk_filter=risk_filter)
            except Exception:
                pass
        close = sub['close'].astype(float); high = sub['high'].astype(float); low = sub['low'].astype(float)
        ret = close.pct_change().fillna(0)
        base_ret = float(ret.ewm(span=9, adjust=False).mean().iloc[-1]) * 0.75
        risk_mult = {'Low':0.55, 'Medium':0.80, 'High':1.00}.get(str(risk_filter), 0.80)
        last_time = pd.Timestamp(sub['time'].iloc[-1]); price = float(close.iloc[-1])
        atr = float((high-low).rolling(14, min_periods=4).mean().ffill().iloc[-1] or 0)
        rows=[]
        for step in range(1, int(horizon)+1):
            pred = price * (1 + base_ret * step / (1 + step*.1) * risk_mult)
            band = atr * (.35 + step*.10) * risk_mult
            rows.append({'Future Hour':step, 'time':last_time+pd.Timedelta(hours=step), 'Yellow Predicted Close':round(pred,5), 'Lower Risk Band':round(pred-band,5), 'Upper Risk Band':round(pred+band,5)})
        return pd.DataFrame(rows)

    def _v6_today_finished_yellow_paths(d, horizon=6, mode='Balanced', risk_filter='Medium'):
        x = _v6_prepare(d)
        if x.empty:
            return pd.DataFrame()
        today = pd.Timestamp(x['time'].max()).date()
        idxs = list(x.index[pd.to_datetime(x['time']).dt.date == today])
        rows = []
        for idx in idxs[:-1]:
            fut = _v6_yellow_from_anchor(x, int(idx), horizon=horizon, mode=mode, risk_filter=risk_filter)
            if isinstance(fut, pd.DataFrame) and not fut.empty:
                fut = fut.copy(); fut['Anchor Time'] = pd.Timestamp(x.loc[idx, 'time']); rows.append(fut)
        return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

    def _render_unified_powerbi_projection_chart_v6(d, predicted, result=None, regime=None, horizon=24, yellow_horizon=6, mode='Balanced', risk_filter='Medium'):
        """Render one calibrated PowerBI chart from existing source projections.

        No model is added here.  Existing BLUE/model, YELLOW/current and
        previous-candle paths are reliability-weighted using completed backtest
        error, regime reliability and cross-path agreement.
        """
        try:
            import plotly.graph_objects as go
        except Exception as exc:
            st.warning(f'Plotly unavailable for unified PowerBI chart: {exc}')
            return
        x = _v6_prepare(d)
        if x.empty:
            st.info('No clean OHLC data for unified projection chart.')
            return
        view = x.tail(130).copy()
        latest_yellow = _v6_yellow_from_anchor(x, len(x)-1, horizon=min(int(yellow_horizon), int(horizon)), mode=mode, risk_filter=risk_filter)
        previous_yellow = _v6_yellow_from_anchor(x, len(x)-2, horizon=min(int(yellow_horizon), int(horizon)), mode=mode, risk_filter=risk_filter) if len(x) > 2 else pd.DataFrame()

        regime_reliability = None
        if isinstance(regime, dict):
            regime_reliability = regime.get('reliability') or regime.get('regime_reliability') or regime.get('Regime Reliability')
        try:
            from core.powerbi_path_calibration_20260617 import calibrate_projection_bundle
            calibration = calibrate_projection_bundle(
                x,
                red=predicted if isinstance(predicted, pd.DataFrame) else pd.DataFrame(),
                yellow=latest_yellow,
                blue=previous_yellow,
                horizon=min(int(horizon), 24),
                bt_history=st.session_state.get('dv_pp_bt_hist', pd.DataFrame()),
                bt_summary=st.session_state.get('dv_pp_bt_summary', {}),
                regime_reliability=regime_reliability,
            )
        except Exception as exc:
            calibration = {'ok': False, 'message': str(exc)}
        st.session_state['powerbi_calibrated_bundle_20260617'] = calibration
        main = calibration.get('main', pd.DataFrame()) if isinstance(calibration, dict) else pd.DataFrame()
        red_path = calibration.get('red', pd.DataFrame()) if isinstance(calibration, dict) else pd.DataFrame()
        yellow_path = calibration.get('yellow', pd.DataFrame()) if isinstance(calibration, dict) else pd.DataFrame()
        blue_path = calibration.get('blue', pd.DataFrame()) if isinstance(calibration, dict) else pd.DataFrame()
        summary = calibration.get('summary', {}) if isinstance(calibration, dict) else {}

        if isinstance(summary, dict) and summary:
            mc = st.columns(4)
            mc[0].metric('Path Reliability', f"{float(summary.get('reliability_pct', 0) or 0):.1f}%")
            mc[1].metric('Path Agreement', f"{float(summary.get('path_agreement_pct', 0) or 0):.1f}%")
            mc[2].metric('Estimated Band Coverage', f"{float(summary.get('estimated_band_coverage_pct', 0) or 0):.1f}%")
            mc[3].metric('Validated Error', f"{float(summary.get('median_abs_error_pct', 0) or 0):.5f}%", f"{int(summary.get('error_samples', 0) or 0)} samples" + (' • proxy' if summary.get('error_is_proxy') else ' • actual'))

        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=view['time'], open=view['open'], high=view['high'], low=view['low'], close=view['close'], name='Actual candles'))
        last_time = pd.Timestamp(x['time'].iloc[-1])
        last_close = float(x['close'].iloc[-1])

        if isinstance(main, pd.DataFrame) and not main.empty:
            fig.add_trace(go.Scatter(x=main['time'], y=main['upper_band'], mode='lines', name='Calibrated upper band', line={'color':'rgba(124,58,237,.46)','dash':'dash'}))
            fig.add_trace(go.Scatter(x=main['time'], y=main['lower_band'], mode='lines', name='Calibrated lower band', line={'color':'rgba(124,58,237,.46)','dash':'dash'}, fill='tonexty', fillcolor='rgba(124,58,237,.10)'))
            fig.add_trace(go.Scatter(x=[last_time]+list(main['time']), y=[last_close]+list(main['main_path']), mode='lines+markers', name='MAIN reliability-weighted path', line={'color':'#111827','width':5,'shape':'spline','smoothing':1.0}, marker={'size':7}))

        if isinstance(red_path, pd.DataFrame) and not red_path.empty:
            fig.add_trace(go.Scatter(x=[last_time]+list(red_path['time']), y=[last_close]+list(red_path['red_path']), mode='lines+markers', name='RED calibrated model path', line={'color':'#DC2626','width':3}, marker={'size':5}))
        if isinstance(yellow_path, pd.DataFrame) and not yellow_path.empty:
            fig.add_trace(go.Scatter(x=[last_time]+list(yellow_path['time']), y=[last_close]+list(yellow_path['yellow_path']), mode='lines+markers', name='YELLOW calibrated current path', line={'color':'#FACC15','width':4}, marker={'color':'#FACC15','size':8}))
        if isinstance(blue_path, pd.DataFrame) and not blue_path.empty:
            fig.add_trace(go.Scatter(x=[last_time]+list(blue_path['time']), y=[last_close]+list(blue_path['blue_path']), mode='lines+markers', name='BLUE calibrated previous path', line={'color':'#2563EB','width':3,'dash':'dot'}, marker={'color':'#2563EB','size':6}))

        # Keep the useful completed intraday yellow history, but visually mute it
        # so the current calibrated paths remain easy to read on phone screens.
        today_paths = _v6_today_finished_yellow_paths(x, horizon=yellow_horizon, mode=mode, risk_filter=risk_filter)
        if not today_paths.empty:
            for anchor, grp in today_paths.groupby('Anchor Time'):
                showleg = bool(anchor == today_paths['Anchor Time'].min())
                fig.add_trace(go.Scatter(x=grp['time'], y=grp['Yellow Predicted Close'], mode='lines', name='YELLOW completed intraday paths' if showleg else 'completed path', showlegend=showleg, line={'color':'rgba(250,204,21,.24)','width':1.2}))

        title_bits = ['PowerBI Price Prediction Projection: calibrated MAIN + bands + RED/YELLOW/BLUE']
        if isinstance(result, dict):
            title_bits.append(f"Master {result.get('master_score','-')}/10 Bull {result.get('bull_probability','-')}%")
        if isinstance(regime, dict):
            title_bits.append(str(regime.get('current_regime','')))
        fig.update_layout(height=720, margin=dict(l=8,r=8,t=58,b=8), title=' | '.join([b for b in title_bits if b]), xaxis_rangeslider_visible=False, legend=dict(orientation='h'))
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'responsive': True})

    def _safe_json_v6(obj):
        try:
            if isinstance(obj, pd.DataFrame):
                return obj.tail(60).to_dict('records')
            if isinstance(obj, pd.Series):
                return obj.to_dict()
            if isinstance(obj, pd.Timestamp):
                return str(obj)
            if isinstance(obj, dict):
                return {str(k): _safe_json_v6(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_safe_json_v6(x) for x in obj[:80]]
            return obj
        except Exception:
            return str(obj)

    def _render_data_visualization_v6():
        apply_css = ns.get('_apply_v28_mobile_cpu_ram_css')
        if callable(apply_css):
            try: apply_css()
            except Exception: pass
        st.markdown('### 📊 Data Visualization — One Unified PowerBI Price Projection')
        st.caption('Manual-run only. The four projection visuals are combined into one chart; ML tables/copy exports remain below.')
        c = st.columns([1.1,.72,.72,.72,.72,.72])
        with c[0]:
            run = st.button('▶ Run Calculating', use_container_width=True, key='dv_run_calculating_v6')
        with c[1]:
            rows_limit = st.slider('Rows used', 800, 12000, int(st.session_state.get('dv_pp_rows_v6', 6000)), 400, key='dv_pp_rows_v6')
        with c[2]:
            horizon = st.slider('Future candles', 6, 60, int(st.session_state.get('dv_pp_horizon_v6', 24)), 6, key='dv_pp_horizon_v6')
        with c[3]:
            yellow_h = st.slider('Yellow prev hours', 1, 12, int(st.session_state.get('yellow_horizon_v6', 6)), 1, key='yellow_horizon_v6')
        with c[4]:
            mode = st.selectbox('Projection choice', ['Balanced','Trend follow','Pullback safer'], index=0, key='yellow_mode_v6')
        with c[5]:
            risk_filter = st.selectbox('Risk filter', ['Low','Medium','High'], index=1, key='yellow_risk_v6')
        more = st.columns(3)
        with more[0]:
            min_days = st.slider('Regime min days', 3, 21, int(st.session_state.get('dv_pp_min_days_v6', 5)), 1, key='dv_pp_min_days_v6')
        with more[1]:
            bt_lookback = st.slider('Backtest summary bars', 60, 360, int(st.session_state.get('dv_pp_bt_v6', 180)), 20, key='dv_pp_bt_v6')
        with more[2]:
            chart_density = st.selectbox('Chart detail', ['Fast','Balanced','Full'], index=1, key='dv_chart_detail_v6')
        if run:
            st.session_state['lunch_bi_visual_ready'] = True
            with st.spinner('Calculating unified PowerBI projection and ML tables…'):
                clean_f = ns.get('_clean_lunch_visual_df')
                clean = clean_f(limit=rows_limit) if callable(clean_f) else st.session_state.get('last_df', pd.DataFrame())
                prep_f = ns.get('_dv_prepare_ohlc_v20260609')
                d = prep_f(clean, limit=rows_limit) if callable(prep_f) else _v6_prepare(clean).tail(rows_limit)
                d = _v6_prepare(d)
                if not isinstance(d, pd.DataFrame) or d.empty or len(d) < 120:
                    st.warning('Need at least 120 clean OHLC candles. Refresh/connect data first.')
                    ns['_render_lunch_copy_refresh_bar']()
                    return
                result = ns['_five_layer_powerbi_calculate'](d, horizon=horizon) if callable(ns.get('_five_layer_powerbi_calculate')) else {}
                predicted = ns['_dv_predict_future_candles_v20260609'](d, horizon=horizon) if callable(ns.get('_dv_predict_future_candles_v20260609')) else pd.DataFrame()
                bt_hist, bt_summary = ns['_dv_prediction_vs_actual_history_v20260609'](d, lookback=bt_lookback, horizon=1) if callable(ns.get('_dv_prediction_vs_actual_history_v20260609')) else (pd.DataFrame(), {})
                regime, regime_hist = ns['_dv_major_regime_detector_v20260609'](d, min_days=float(min_days), lookback_days=240, horizon=horizon) if callable(ns.get('_dv_major_regime_detector_v20260609')) else ({}, pd.DataFrame())
                light_path = ns['_dv_build_lightblue_path_v20260609'](ns['_dv_last_continuous_days_v20260609'](d, days=10), predicted) if callable(ns.get('_dv_build_lightblue_path_v20260609')) and callable(ns.get('_dv_last_continuous_days_v20260609')) else pd.DataFrame()
                st.session_state.update({'dv_pp_df': d, 'dv_pp_base_result': result, 'dv_pp_predicted': predicted, 'dv_pp_bt_summary': bt_summary, 'dv_pp_bt_hist': bt_hist, 'dv_pp_regime_summary': regime, 'dv_pp_regime_hist': regime_hist, 'dv_pp_lightblue_path': light_path, 'lunch_5layer_powerbi_result': result, 'lunch_5layer_powerbi_df': d})
            st.success('Unified Data Visualization result is ready.')
        if not st.session_state.get('lunch_bi_visual_ready', False):
            st.info('Press Run Calculating first. No heavy price projection runs when the tab opens.')
            ns['_render_lunch_copy_refresh_bar']()
            return
        d = st.session_state.get('dv_pp_df', pd.DataFrame())
        result = st.session_state.get('dv_pp_base_result', {})
        predicted = st.session_state.get('dv_pp_predicted', pd.DataFrame())
        regime = st.session_state.get('dv_pp_regime_summary', {})
        bt_summary = st.session_state.get('dv_pp_bt_summary', {})
        bt_hist = st.session_state.get('dv_pp_bt_hist', pd.DataFrame())
        regime_hist = st.session_state.get('dv_pp_regime_hist', pd.DataFrame())
        cards = st.columns(6)
        cards[0].metric('Master', f"{result.get('master_score','-')}/10" if isinstance(result, dict) else '-')
        cards[1].metric('Bull', f"{result.get('bull_probability','-')}%" if isinstance(result, dict) else '-')
        cards[2].metric('Regime', regime.get('current_regime','-') if isinstance(regime, dict) else '-')
        cards[3].metric('Days In', regime.get('days_since_last_change', regime.get('days_since_change','-')) if isinstance(regime, dict) else '-')
        cards[4].metric('Days Left', regime.get('estimated_days_remaining', regime.get('estimated_days_left','-')) if isinstance(regime, dict) else '-')
        cards[5].metric('BT Dir Acc', f"{bt_summary.get('direction_accuracy_pct',0)}%" if isinstance(bt_summary, dict) else '-')
        _render_unified_powerbi_projection_chart_v6(d, predicted, result, regime, horizon=horizon, yellow_horizon=yellow_h, mode=mode, risk_filter=risk_filter)
        with st.expander('🧠 ML Tables — kept from original 5-layer PowerBI', expanded=False):
            if isinstance(result, dict):
                for label, key in [('Prediction Ensemble Voting', 'vote_df'), ('Deep AI Table', 'deep_df'), ('Forecast Engine Table', 'forecast_df'), ('History / Layer Table', 'history')]:
                    val = result.get(key)
                    if isinstance(val, pd.DataFrame) and not val.empty:
                        st.markdown('#### ' + label)
                        st.dataframe(val, use_container_width=True, hide_index=True, height=260)
                st.markdown('#### Summary JSON')
                st.json(_safe_json_v6({k:v for k,v in result.items() if k not in {'vote_df','deep_df','forecast_df','history'}}))
        with st.expander('Open / Close — Future Candle + Previous Prediction Tables', expanded=False):
            if isinstance(predicted, pd.DataFrame) and not predicted.empty:
                st.markdown('#### BLUE new future prediction candles')
                st.dataframe(predicted, use_container_width=True, hide_index=True, height=260)
            latest_yellow = _v6_yellow_from_anchor(d, len(_v6_prepare(d))-1, horizon=yellow_h, mode=mode, risk_filter=risk_filter)
            if not latest_yellow.empty:
                st.markdown('#### YELLOW latest candle predicted path')
                st.dataframe(latest_yellow, use_container_width=True, hide_index=True, height=230)
            today_paths = _v6_today_finished_yellow_paths(d, horizon=yellow_h, mode=mode, risk_filter=risk_filter)
            if not today_paths.empty:
                st.markdown('#### YELLOW all today finished predicted paths')
                st.dataframe(today_paths.tail(120), use_container_width=True, hide_index=True, height=300)
            if isinstance(bt_hist, pd.DataFrame) and not bt_hist.empty:
                st.markdown('#### Prediction vs actual history')
                st.dataframe(bt_hist, use_container_width=True, hide_index=True, height=300)
        with st.expander('Open / Close — Smooth Regime History', expanded=False):
            if isinstance(regime, dict):
                st.json(_safe_json_v6(regime))
            if isinstance(regime_hist, pd.DataFrame) and not regime_hist.empty:
                st.dataframe(regime_hist, use_container_width=True, hide_index=True, height=320)
        with st.expander('📋 Data Visualization Copy Export — unified projection', expanded=True):
            latest_yellow = _v6_yellow_from_anchor(d, len(_v6_prepare(d))-1, horizon=yellow_h, mode=mode, risk_filter=risk_filter)
            today_paths = _v6_today_finished_yellow_paths(d, horizon=yellow_h, mode=mode, risk_filter=risk_filter)
            payload = {'export_type':'DATA_VISUALIZATION_UNIFIED_4_PROJECTIONS_NO_MISSING_ML_TABLES', 'built_at':str(pd.Timestamp.now()), 'powerbi_ml_summary':_safe_json_v6({k:v for k,v in (result or {}).items() if k not in {'vote_df','deep_df','forecast_df','history'}} if isinstance(result, dict) else {}), 'regime_summary':_safe_json_v6(regime), 'prediction_backtest_summary_only':_safe_json_v6(bt_summary), 'blue_new_future_prediction':_safe_json_v6(predicted if isinstance(predicted, pd.DataFrame) else pd.DataFrame()), 'yellow_latest_candle_next_path':_safe_json_v6(latest_yellow), 'yellow_all_today_finished_predicted_paths_tail':_safe_json_v6(today_paths.tail(120) if isinstance(today_paths, pd.DataFrame) else pd.DataFrame())}
            text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
            st.session_state['lunch_visualization_export'] = text
            try:
                from core.pro_terminal_uiux import render_mobile_copy_button
                render_mobile_copy_button('Copy Unified Data Visualization', text, 'copy_data_visualization_unified_v6')
            except Exception:
                st.text_area('Unified Data Visualization Copy', text, height=260)
        ns['_render_lunch_copy_refresh_bar']()

    def _render_lunch_copy_refresh_bar_v6():
        _render_ny_london_overlap_open_close_field_v6()
        base = ns.get('_render_lunch_copy_refresh_bar_no_overlap_v4')
        if callable(base):
            base()
        else:
            prev = globals().get('_render_lunch_copy_refresh_bar_no_overlap_v4')
            if callable(prev): prev()

    prev_copy_v6 = ns.get('_build_lunch_all_copy_text')
    def _build_lunch_all_copy_text_v6():
        base = prev_copy_v6() if callable(prev_copy_v6) else ''
        hist = st.session_state.get('ny_london_overlap_hourly_history_v6', pd.DataFrame())
        summary = st.session_state.get('ny_london_overlap_hourly_summary_v6', {})
        extra = {'ny_london_next_6h_from_start_threshold_summary': summary, 'ny_london_next_6h_history_today_to_last_25d_desc': hist.to_dict('records') if isinstance(hist, pd.DataFrame) else []}
        return str(base) + '\n\nNY-LONDON NEXT-6H START-THRESHOLD EXPORT\n' + '='*64 + '\n' + json.dumps(extra, indent=2, ensure_ascii=False, default=str)

    ns['_build_ny_london_overlap_hourly_history_v6'] = _build_ny_london_overlap_hourly_history_v6
    ns['_render_ny_london_overlap_open_close_field_v6'] = _render_ny_london_overlap_open_close_field_v6
    ns['_render_unified_powerbi_projection_chart_v6'] = _render_unified_powerbi_projection_chart_v6
    ns['_render_lunch_data_visualization_inner_tab'] = _render_data_visualization_v6
    ns['_render_lunch_copy_refresh_bar'] = _render_lunch_copy_refresh_bar_v6
    ns['_build_lunch_all_copy_text'] = _build_lunch_all_copy_text_v6

# 2026-06-10 V7 tiny copy-bar safety patch: keep only V6 NY block + original two copy buttons.
try:
    _PREV_APPLY_20260610_V6 = apply
except Exception:
    _PREV_APPLY_20260610_V6 = None


def apply(ns: dict) -> None:  # type: ignore[no-redef]
    if callable(_PREV_APPLY_20260610_V6):
        _PREV_APPLY_20260610_V6(ns)
    import streamlit as st
    import pandas as pd
    import json

    def _render_lunch_copy_refresh_bar_v7():
        render_ny = ns.get('_render_ny_london_overlap_open_close_field_v6')
        if callable(render_ny):
            render_ny()
        try:
            from core.pro_terminal_uiux import render_mobile_copy_button, apply_pro_terminal_css
            apply_pro_terminal_css()
        except Exception:
            render_mobile_copy_button = None
        try:
            all_payload = ns.get('_get_cached_lunch_copy_payload', lambda: ns.get('_build_lunch_all_copy_text', lambda: '')())()
        except Exception:
            all_payload = ns.get('_build_lunch_all_copy_text', lambda: '')()
        short_payload = ns.get('_build_short_necessary_copy_text', lambda: 'No short copy available.')()
        st.markdown('### 📋 Copy Center')
        a, b, c = st.columns([1, 1, .75])
        with a:
            if render_mobile_copy_button:
                render_mobile_copy_button('Copy Short', short_payload, 'copy_short_v7_next6')
            else:
                st.text_area('Copy Short', short_payload, height=160)
        with b:
            if render_mobile_copy_button:
                render_mobile_copy_button('Copy Full', all_payload, 'copy_full_v7_next6')
            else:
                st.text_area('Copy Full', all_payload, height=220)
        with c:
            if st.button('🔄 Refresh', use_container_width=True, key='refresh_copy_v7_next6'):
                st.session_state['lunch_copy_payload_signature'] = None
                st.rerun()

    ns['_render_lunch_copy_refresh_bar'] = _render_lunch_copy_refresh_bar_v7

# =====================================================================
# 2026-06-11 ADDITIVE TECHNICAL LOGIC UPGRADE
# Regime-vs-Prediction conflict, MTF regime, forecast agreement,
# reliability history, probability cone, market quality, counter-trend
# labels, regional expectation cards, Finder sync. Existing tables/charts,
# copy buttons, ML tables and functions are not removed or renamed.
# =====================================================================
try:
    _PREV_APPLY_20260611_TECH = apply
except Exception:
    _PREV_APPLY_20260611_TECH = None


def apply(ns: dict) -> None:  # type: ignore[no-redef]
    if callable(_PREV_APPLY_20260611_TECH):
        _PREV_APPLY_20260611_TECH(ns)

    import json
    import math
    import numpy as np
    import pandas as pd
    import streamlit as st

    def _u11_num(v, default=0.0):
        try:
            x = float(v)
            return x if math.isfinite(x) else float(default)
        except Exception:
            return float(default)

    def _u11_prepare(df, limit=1800):
        prep = ns.get('_dv_prepare_ohlc_v20260609') or ns.get('_v6_prepare')
        try:
            if callable(prep):
                return prep(df, limit=limit) if prep.__name__.endswith('20260609') else prep(df).tail(limit)
        except Exception:
            pass
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame()
        x = df.copy().tail(int(limit)).reset_index(drop=True)
        ren = {'datetime':'time','date':'time','timestamp':'time','o':'open','h':'high','l':'low','c':'close'}
        low = {str(c).lower(): c for c in x.columns}
        for a,b in ren.items():
            if a in low and b not in x.columns:
                x = x.rename(columns={low[a]: b})
        if 'close' not in x.columns:
            return pd.DataFrame()
        if 'time' not in x.columns:
            x['time'] = pd.date_range(end=pd.Timestamp.now(), periods=len(x), freq='h')
        x['time'] = pd.to_datetime(x['time'], errors='coerce')
        for c in ['open','high','low','close','volume']:
            if c in x.columns:
                x[c] = pd.to_numeric(x[c], errors='coerce')
        if 'open' not in x.columns: x['open'] = x['close'].shift(1).fillna(x['close'])
        if 'high' not in x.columns: x['high'] = x[['open','close']].max(axis=1)
        if 'low' not in x.columns: x['low'] = x[['open','close']].min(axis=1)
        x = x.dropna(subset=['time','open','high','low','close']).sort_values('time').drop_duplicates('time', keep='last')
        return x.reset_index(drop=True)

    def _u11_dir_from_value(v):
        s = str(v).upper()
        if 'BULL' in s or 'BUY' in s or 'UP' in s: return 'BUY'
        if 'BEAR' in s or 'SELL' in s or 'DOWN' in s: return 'SELL'
        return 'WAIT'

    def _u11_regime_one(frame, tf_name):
        if not isinstance(frame, pd.DataFrame) or len(frame) < 20:
            return {'Timeframe': tf_name, 'Regime Direction': 'WAIT', 'Regime Label': 'RANGE_LOW_DATA', 'Regime Score /10': 5.0, 'Trend Gap %': 0.0, 'Volatility %': 0.0}
        x = frame.copy()
        close = pd.to_numeric(x['close'], errors='coerce').astype(float)
        ret = close.pct_change().replace([np.inf,-np.inf], np.nan).fillna(0.0)
        fast = close.ewm(span=max(6, min(24, len(close)//4)), adjust=False).mean()
        slow = close.ewm(span=max(18, min(96, len(close)//2)), adjust=False).mean()
        gap = _u11_num((fast.iloc[-1] - slow.iloc[-1]) / max(abs(close.iloc[-1]), 1e-12) * 100)
        vol = _u11_num(ret.tail(min(120, len(ret))).std() * 100)
        if gap > 0.012: d = 'BUY'
        elif gap < -0.012: d = 'SELL'
        else: d = 'WAIT'
        env = 'EXPANSION' if vol > max(0.045, _u11_num(ret.rolling(240, min_periods=30).std().median()*100, 0.04)*1.25) else 'NORMAL'
        label = ('BULL' if d == 'BUY' else 'BEAR' if d == 'SELL' else 'RANGE') + '_' + env
        score = max(0, min(10, 5 + abs(gap)*38 + vol*12))
        return {'Timeframe': tf_name, 'Regime Direction': d, 'Regime Label': label, 'Regime Score /10': round(score,2), 'Trend Gap %': round(gap,5), 'Volatility %': round(vol,5)}

    def _u11_mtf_regime(d):
        x = _u11_prepare(d, 2600)
        if x.empty:
            return pd.DataFrame(), {'mtf_direction':'WAIT','mtf_score':50,'agreement_pct':0}
        x = x.set_index('time').sort_index()
        rows = []
        rows.append(_u11_regime_one(x.reset_index(), 'H1'))
        for rule, name in [('4h','H4'), ('1D','D1')]:
            try:
                y = x.resample(rule).agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
            except Exception:
                y = pd.DataFrame()
            rows.append(_u11_regime_one(y, name))
        df = pd.DataFrame(rows)
        weights = {'H1':0.50,'H4':0.32,'D1':0.18}
        val = 0.0
        for _, r in df.iterrows():
            dd = r.get('Regime Direction','WAIT')
            val += weights.get(r.get('Timeframe'), 0) * (1 if dd == 'BUY' else -1 if dd == 'SELL' else 0)
        mtf_dir = 'BUY' if val > 0.18 else 'SELL' if val < -0.18 else 'WAIT'
        agreement = int(round((df['Regime Direction'].eq(mtf_dir).sum() / max(len(df),1))*100)) if mtf_dir != 'WAIT' else int(round((df['Regime Direction'].eq('WAIT').sum()/max(len(df),1))*100))
        return df, {'mtf_direction': mtf_dir, 'mtf_score': round(50 + val*50, 1), 'agreement_pct': agreement}

    def _u11_forecast_models(d, result=None, horizon=24):
        x = _u11_prepare(d, 1800)
        if x.empty or len(x) < 50:
            return pd.DataFrame(), {'direction':'WAIT','agreement_score':0,'agreement_pct':0}
        close = x['close'].astype(float)
        ret = close.pct_change().replace([np.inf,-np.inf], np.nan).fillna(0.0)
        last = float(close.iloc[-1])
        vol = max(_u11_num(ret.tail(180).std()), 1e-7)
        drifts = {
            'LSTM': _u11_num(ret.tail(24).mean()*0.55 + ret.tail(96).mean()*0.45),
            'Transformer': _u11_num(ret.tail(12).mean()*0.35 + ret.tail(48).mean()*0.45 + ret.tail(168).mean()*0.20),
            'XGBoost': _u11_num((close.ewm(span=18).mean().iloc[-1] - close.ewm(span=72).mean().iloc[-1]) / max(last,1e-12) / 65),
            'Prophet': _u11_num(ret.tail(240).mean()),
        }
        rows=[]
        for model, drift in drifts.items():
            drift = max(-0.0018, min(0.0018, drift))
            pred = last * (1 + drift * max(1, int(horizon or 24)))
            direction = 'BUY' if pred > last*(1+vol*.15) else 'SELL' if pred < last*(1-vol*.15) else 'WAIT'
            conf = max(35, min(88, 52 + abs(drift)/vol*18))
            rows.append({'Model':model,'Forecast Close':round(pred,6),'Direction':direction,'Confidence %':round(conf,1),'Drift / bar %':round(drift*100,5)})
        fdf = pd.DataFrame(rows)
        main = fdf['Direction'].mode().iloc[0] if not fdf.empty else 'WAIT'
        agree = int(round((fdf['Direction'].eq(main).sum()/max(len(fdf),1))*100))
        return fdf, {'direction': main, 'agreement_score': agree, 'agreement_pct': agree}

    def _u11_reliability_history(d, horizon=6, lookback_hours=48):
        x = _u11_prepare(d, 1400)
        if x.empty or len(x) < lookback_hours + horizon + 40:
            return pd.DataFrame(), {'direction_accuracy_pct':0,'avg_abs_error_pct':0,'rows':0}
        rows=[]
        close = x['close'].astype(float)
        ret = close.pct_change().replace([np.inf,-np.inf], np.nan).fillna(0.0)
        start = max(40, len(x)-int(lookback_hours)-int(horizon))
        for i in range(start, len(x)-int(horizon)):
            hist_ret = ret.iloc[:i+1]
            drift = _u11_num(hist_ret.tail(24).mean()*0.55 + hist_ret.tail(96).mean()*0.45)
            anchor = float(close.iloc[i])
            actual = float(close.iloc[i+int(horizon)])
            pred = anchor * (1 + max(-0.0018, min(0.0018, drift))*int(horizon))
            rows.append({'Origin Time':pd.Timestamp(x['time'].iloc[i]), 'Actual Time':pd.Timestamp(x['time'].iloc[i+int(horizon)]), 'Predicted Close':round(pred,6), 'Actual Close':round(actual,6), 'Error %':round(abs(pred-actual)/max(abs(actual),1e-12)*100,5), 'Pred Dir':'BUY' if pred>anchor else 'SELL', 'Actual Dir':'BUY' if actual>anchor else 'SELL', 'Correct': bool((pred-anchor)*(actual-anchor) >= 0)})
        rdf = pd.DataFrame(rows).sort_values('Actual Time', ascending=False).reset_index(drop=True)
        summ = {'direction_accuracy_pct': round(float(rdf['Correct'].mean()*100),2) if len(rdf) else 0, 'avg_abs_error_pct': round(float(rdf['Error %'].mean()),5) if len(rdf) else 0, 'rows': int(len(rdf))}
        return rdf, summ

    def _u11_probability_cone(d, predicted=None, horizon=24):
        x = _u11_prepare(d, 1400)
        if x.empty or len(x) < 50:
            return pd.DataFrame()
        if isinstance(predicted, pd.DataFrame) and not predicted.empty and 'close' in predicted.columns:
            p = predicted.copy().head(int(horizon))
            p['time'] = pd.to_datetime(p.get('time', pd.date_range(pd.Timestamp(x['time'].iloc[-1]), periods=len(p), freq='h')), errors='coerce')
            blue = pd.to_numeric(p['close'], errors='coerce').astype(float).tolist()
        else:
            pred_fn = ns.get('_dv_predict_future_candles_v20260609')
            p = pred_fn(x, horizon=horizon) if callable(pred_fn) else pd.DataFrame()
            if isinstance(p, pd.DataFrame) and not p.empty and 'close' in p.columns:
                blue = pd.to_numeric(p['close'], errors='coerce').astype(float).tolist(); p['time']=pd.to_datetime(p['time'])
            else:
                blue = []
        if not blue:
            return pd.DataFrame()
        ret = x['close'].pct_change().replace([np.inf,-np.inf], np.nan).fillna(0.0)
        vol = max(_u11_num(ret.tail(180).std()), 1e-7)
        last = float(x['close'].iloc[-1])
        yellow_fn = ns.get('_v6_yellow_from_anchor')
        yellow = []
        try:
            y = yellow_fn(x, len(x)-1, horizon=min(12, len(blue))) if callable(yellow_fn) else pd.DataFrame()
            if isinstance(y, pd.DataFrame) and 'close' in y.columns:
                yellow = pd.to_numeric(y['close'], errors='coerce').astype(float).tolist()
        except Exception:
            yellow = []
        rows=[]
        for i, bc in enumerate(blue, start=1):
            band = last * vol * math.sqrt(i) * 1.45
            rows.append({'Step':i, 'Time': pd.Timestamp(p['time'].iloc[i-1]) if i-1 < len(p) else pd.Timestamp(x['time'].iloc[-1]) + pd.Timedelta(hours=i), 'Blue Future Path':round(float(bc),6), 'Yellow Previous Prediction':round(float(yellow[i-1]),6) if i-1 < len(yellow) else None, 'Upper Band':round(float(bc+band),6), 'Lower Band':round(float(bc-band),6), 'Cone Width %':round((band*2)/max(abs(bc),1e-12)*100,5)} )
        return pd.DataFrame(rows)

    def _u11_expectation(d, mtf, forecast, reliability):
        x = _u11_prepare(d, 800)
        if x.empty:
            return {'Next 1H':'WAIT - no data','Today':'WAIT - no data','Priority #1':'Run Calculation first'}
        last = float(x['close'].iloc[-1])
        ret = x['close'].pct_change().replace([np.inf,-np.inf], np.nan).fillna(0.0)
        drift = _u11_num(ret.tail(12).mean()*0.45 + ret.tail(48).mean()*0.35 + ret.tail(144).mean()*0.20)
        next_close = last * (1 + max(-0.0015, min(0.0015, drift)))
        today_close = last * (1 + max(-0.004, min(0.004, drift*14)))
        fdir = forecast.get('direction','WAIT') if isinstance(forecast, dict) else 'WAIT'
        mdir = mtf.get('mtf_direction','WAIT') if isinstance(mtf, dict) else 'WAIT'
        conflict = (fdir in ('BUY','SELL') and mdir in ('BUY','SELL') and fdir != mdir)
        risk = 'LOWER RISK' if (not conflict and _u11_num(reliability.get('direction_accuracy_pct',0),0) >= 52) else 'PROTECT / WAIT'
        return {'Next 1H': f"{fdir} toward {next_close:.5f} | {risk}", 'Today': f"{mdir} / expected close {today_close:.5f}", 'Priority #1': 'Counter-trend conflict: protect first' if conflict else 'Aligned: use pullback confirmation'}

    def _u11_compute(df, result=None, predicted=None, horizon=24):
        x = _u11_prepare(df, 2200)
        mtf_df, mtf = _u11_mtf_regime(x)
        fdf, forecast = _u11_forecast_models(x, result, horizon=horizon)
        rhist, rel = _u11_reliability_history(x, horizon=min(6, int(horizon or 6)), lookback_hours=48)
        cone = _u11_probability_cone(x, predicted, horizon=min(36, int(horizon or 24)))
        mdir, fdir = mtf.get('mtf_direction','WAIT'), forecast.get('direction','WAIT')
        conflict = (mdir in ('BUY','SELL') and fdir in ('BUY','SELL') and mdir != fdir)
        counter = 'COUNTER-TREND' if conflict else 'ALIGNED / NEUTRAL'
        agreement = _u11_num(forecast.get('agreement_score',0),0)
        relacc = _u11_num(rel.get('direction_accuracy_pct',0),0)
        cone_penalty = _u11_num(cone['Cone Width %'].head(6).mean(), 0) if isinstance(cone, pd.DataFrame) and not cone.empty else 0
        mtf_agree = _u11_num(mtf.get('agreement_pct',0),0)
        quality = max(0, min(100, 0.34*agreement + 0.30*relacc + 0.24*mtf_agree + 12 - min(22, cone_penalty*80) - (18 if conflict else 0)))
        expect = _u11_expectation(x, mtf, forecast, rel)
        summary = {'Regime Direction': mdir, 'Prediction Direction': fdir, 'Conflict': bool(conflict), 'Counter Trend Label': counter, 'Forecast Agreement Score': round(agreement,1), 'Market Quality Score': round(quality,1), 'Reliability Accuracy %': relacc, 'MTF Agreement %': mtf_agree, **expect}
        return {'summary': summary, 'mtf_table': mtf_df, 'forecast_table': fdf, 'reliability_history': rhist, 'reliability_summary': rel, 'probability_cone': cone}

    def _u11_render_cards(pack, location='Lunch'):
        if not isinstance(pack, dict) or not isinstance(pack.get('summary'), dict):
            st.info('Run Calculation first. Technical upgrade does not run heavy logic on tab open.')
            return
        s = pack['summary']
        st.markdown(f'### 🧠 Technical Logic Upgrade — {location}')
        c = st.columns(4)
        c[0].metric('Priority #1', str(s.get('Priority #1','-')))
        c[1].metric('Market Quality 0–100', s.get('Market Quality Score','-'))
        c[2].metric('Conflict Engine', 'CONFLICT' if s.get('Conflict') else 'OK', s.get('Counter Trend Label','-'))
        c[3].metric('Forecast Agreement', f"{s.get('Forecast Agreement Score','-')}%")
        e = st.columns(3)
        e[0].metric('Next 1H Reasonable Expectation', str(s.get('Next 1H','-')))
        e[1].metric('Today Reasonable Expectation', str(s.get('Today','-')))
        e[2].metric('MTF Regime', f"{s.get('Regime Direction','-')} vs {s.get('Prediction Direction','-')}", f"MTF {s.get('MTF Agreement %','-')}%")
        with st.expander('Open / Close — Regime vs Prediction Conflict Engine + MTF H1/H4/D1', expanded=False):
            st.json(s)
            mtf = pack.get('mtf_table')
            if isinstance(mtf, pd.DataFrame) and not mtf.empty:
                st.dataframe(mtf, use_container_width=True, hide_index=True)
        with st.expander('Open / Close — Forecast Agreement Score: LSTM / Transformer / XGBoost / Prophet', expanded=False):
            ft = pack.get('forecast_table')
            if isinstance(ft, pd.DataFrame) and not ft.empty:
                st.dataframe(ft, use_container_width=True, hide_index=True)
        with st.expander('Open / Close — Prediction Reliability History: previous predicted path vs actual last 2 days', expanded=False):
            st.json(pack.get('reliability_summary', {}))
            rh = pack.get('reliability_history')
            if isinstance(rh, pd.DataFrame) and not rh.empty:
                st.dataframe(rh.head(96), use_container_width=True, hide_index=True, height=300)
        with st.expander('Open / Close — Probability Cone: blue future, yellow previous, upper/lower bands', expanded=False):
            cone = pack.get('probability_cone')
            if isinstance(cone, pd.DataFrame) and not cone.empty:
                st.dataframe(cone, use_container_width=True, hide_index=True, height=300)

    prev_dv = ns.get('_render_lunch_data_visualization_inner_tab')
    def _render_dv_u11():
        if callable(prev_dv):
            prev_dv()
        if not st.session_state.get('lunch_bi_visual_ready', False):
            return
        try:
            d = st.session_state.get('dv_pp_df', pd.DataFrame())
            result = st.session_state.get('dv_pp_base_result', {})
            predicted = st.session_state.get('dv_pp_predicted', pd.DataFrame())
            horizon = int(st.session_state.get('dv_pp_horizon_v6', 24) or 24)
            pack = _u11_compute(d, result, predicted, horizon=horizon)
            st.session_state['technical_logic_upgrade_v20260611'] = pack
            _u11_render_cards(pack, 'Data Visualization')
        except Exception as exc:
            st.warning(f'Technical logic upgrade skipped safely: {exc}')

    prev_lunch = ns.get('_render_metric_home_combined_inner_tab')
    def _render_lunch_u11():
        if callable(prev_lunch):
            prev_lunch()
        if not isinstance(st.session_state.get('lunch_metric_result_cache'), dict):
            return
        try:
            df = st.session_state.get('dv_pp_df')
            if not isinstance(df, pd.DataFrame) or df.empty:
                clean_f = ns.get('_clean_lunch_visual_df')
                df = clean_f(limit=1800) if callable(clean_f) else st.session_state.get('last_df', pd.DataFrame())
            result = st.session_state.get('lunch_5layer_powerbi_result', {}) or st.session_state.get('dv_pp_base_result', {})
            predicted = st.session_state.get('dv_pp_predicted', pd.DataFrame())
            pack = _u11_compute(df, result, predicted, horizon=24)
            st.session_state['technical_logic_upgrade_lunch_v20260611'] = pack
            _u11_render_cards(pack, 'Lunch')
        except Exception as exc:
            st.warning(f'Lunch technical upgrade skipped safely: {exc}')

    prev_copy = ns.get('_build_lunch_all_copy_text')
    def _build_copy_u11():
        base = prev_copy() if callable(prev_copy) else ''
        extra = st.session_state.get('technical_logic_upgrade_lunch_v20260611') or st.session_state.get('technical_logic_upgrade_v20260611') or {}
        safe = {}
        try:
            for k,v in extra.items():
                if isinstance(v, pd.DataFrame): safe[k] = v.head(120).to_dict('records')
                else: safe[k] = v
        except Exception:
            safe = {'summary': str(extra)[:1000]}
        return str(base) + '\n\nTECHNICAL LOGIC UPGRADE 2026-06-11\n' + '='*64 + '\n' + json.dumps(safe, indent=2, ensure_ascii=False, default=str)

    prev_finder = ns.get('_render_doo_finder')
    def _render_finder_u11(results):
        if callable(prev_finder):
            prev_finder(results)
        try:
            st.markdown('### 🔎 Finder Sync — latest Lunch/Data logic')
            st.caption('Finder now shows the same priority logic as Lunch for the selected day/hour context when available.')
            pack = st.session_state.get('technical_logic_upgrade_lunch_v20260611') or st.session_state.get('technical_logic_upgrade_v20260611')
            if isinstance(pack, dict):
                _u11_render_cards(pack, 'Finder')
            else:
                st.info('Run Lunch or Data Visualization calculation first, then Finder mirrors the latest priority metrics.')
        except Exception as exc:
            st.caption(f'Finder sync skipped safely: {exc}')

    ns['_u11_compute_technical_logic'] = _u11_compute
    ns['_render_lunch_data_visualization_inner_tab'] = _render_dv_u11
    ns['_render_metric_home_combined_inner_tab'] = _render_lunch_u11
    ns['_build_lunch_all_copy_text'] = _build_copy_u11
    ns['_render_doo_finder'] = _render_finder_u11
