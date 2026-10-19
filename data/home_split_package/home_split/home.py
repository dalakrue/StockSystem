# Main Home tab entry.
# This imports the unchanged original implementation.

from .implementation import show

# =====================================================================
# 2026-06-09 MERGED DIRECT UPGRADE - DATA VISUALIZATION PRO++ CANDLES
# =====================================================================

# =====================================================================
# 2026-06-09 ADDITIVE COPY-PASTE UPGRADE
# Data Visualization Pro++: actual candle chart + BLUE predicted future
# candles + historical predicted-vs-actual candles + smoother regime
# detection. Paste this at the VERY END of tabs/home.py.
# It does not delete or edit your original code; it overrides only the
# Data Visualization renderer and adds helper functions below it.
# =====================================================================


def _dv_safe_num_v20260609(v, default=0.0):
    try:
        import numpy as np
        x = float(v)
        if np.isfinite(x):
            return x
    except Exception:
        pass
    return float(default)


def _dv_prepare_ohlc_v20260609(d, limit=3000):
    import pandas as pd
    import numpy as np
    if d is None or not isinstance(d, pd.DataFrame) or d.empty:
        return pd.DataFrame()
    x = d.copy().tail(int(limit)).reset_index(drop=True)
    for c in ["open", "high", "low", "close", "volume"]:
        if c in x.columns:
            x[c] = pd.to_numeric(x[c], errors="coerce")
    if "close" not in x.columns:
        return pd.DataFrame()
    if "open" not in x.columns:
        x["open"] = x["close"].shift(1).fillna(x["close"])
    if "high" not in x.columns:
        x["high"] = x[["open", "close"]].max(axis=1)
    if "low" not in x.columns:
        x["low"] = x[["open", "close"]].min(axis=1)
    if "time" not in x.columns:
        x["time"] = pd.date_range(end=pd.Timestamp.now(), periods=len(x), freq="h")
    x["time"] = pd.to_datetime(x["time"], errors="coerce")
    x = x.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time")
    x = x.drop_duplicates("time", keep="last").reset_index(drop=True)
    x["high"] = x[["open", "high", "close"]].max(axis=1)
    x["low"] = x[["open", "low", "close"]].min(axis=1)
    x["returns"] = x["close"].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    x["range_pct"] = ((x["high"] - x["low"]) / x["close"].replace(0, np.nan) * 100).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    x["body_pct"] = ((x["close"] - x["open"]) / x["open"].replace(0, np.nan) * 100).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    x["atr_proxy"] = (x["high"] - x["low"]).rolling(48, min_periods=12).median().fillna((x["high"] - x["low"]).median())
    return x


def _dv_infer_bar_timedelta_v20260609(x):
    import pandas as pd
    try:
        dt = pd.to_datetime(x["time"]).diff().dropna()
        if len(dt):
            med = dt.median()
            if pd.notna(med) and med.total_seconds() > 0:
                return med
    except Exception:
        pass
    return pd.Timedelta(hours=1)


def _dv_predict_future_candles_v20260609(d, horizon=24):
    """Create future OHLC candles. Predicted candles are designed for visualization, not guaranteed price."""
    import pandas as pd
    import numpy as np
    x = _dv_prepare_ohlc_v20260609(d, limit=3000)
    if x.empty or len(x) < 80:
        return pd.DataFrame()
    horizon = int(max(3, min(int(horizon or 24), 96)))
    close = x["close"].astype(float)
    ret = x["returns"].astype(float)
    ema_fast = close.ewm(span=24, adjust=False).mean()
    ema_slow = close.ewm(span=144, adjust=False).mean()
    trend_gap = float((ema_fast.iloc[-1] - ema_slow.iloc[-1]) / max(close.iloc[-1], 1e-12))
    mom_short = float(ret.tail(12).mean())
    mom_mid = float(ret.tail(48).mean())
    vol = float(ret.tail(180).std()) if len(ret) >= 60 else float(ret.std())
    vol = max(vol, 1e-7)
    # Drift is deliberately clipped to avoid wild fake-looking projections.
    drift = max(-0.0035, min(0.0035, mom_short * 0.40 + mom_mid * 0.35 + trend_gap / 220.0))
    bar_delta = _dv_infer_bar_timedelta_v20260609(x)
    last_time = pd.Timestamp(x["time"].iloc[-1])
    last_close = float(close.iloc[-1])
    typical_range = float((x["high"] - x["low"]).tail(180).median())
    if not np.isfinite(typical_range) or typical_range <= 0:
        typical_range = max(last_close * vol * 1.8, last_close * 0.0002)
    rows = []
    prev = last_close
    for i in range(1, horizon + 1):
        # damp the projection so it stays readable and less noisy farther ahead
        step_drift = drift * (0.97 ** (i - 1))
        wave = np.sin(i / 3.0) * vol * 0.20
        pred_close = prev * (1.0 + step_drift + wave)
        pred_open = prev
        body = abs(pred_close - pred_open)
        wick = max(typical_range * (0.75 + min(i, 24) / 80.0), body * 1.4, last_close * vol * 0.8)
        pred_high = max(pred_open, pred_close) + wick * 0.45
        pred_low = min(pred_open, pred_close) - wick * 0.45
        rows.append({
            "time": last_time + bar_delta * i,
            "open": round(float(pred_open), 6),
            "high": round(float(pred_high), 6),
            "low": round(float(pred_low), 6),
            "close": round(float(pred_close), 6),
            "candle_type": "BLUE_PREDICTED_FUTURE",
            "prediction_step": i,
            "confidence_pct": int(max(25, min(92, 78 - i * 0.8 - vol * 7000))),
        })
        prev = float(pred_close)
    return pd.DataFrame(rows)


def _dv_prediction_vs_actual_history_v20260609(d, lookback=180, horizon=1):
    """Walk-forward check: for each old candle, predict next candle from prior data, then compare to actual."""
    import pandas as pd
    import numpy as np
    x = _dv_prepare_ohlc_v20260609(d, limit=3500)
    if x.empty or len(x) < 180:
        return pd.DataFrame(), {}
    lookback = int(max(30, min(int(lookback or 180), 500)))
    start = max(80, len(x) - lookback - int(horizon))
    rows = []
    for i in range(start, len(x) - int(horizon)):
        train = x.iloc[:i].copy()
        actual = x.iloc[i + int(horizon) - 1]
        pred = _dv_predict_future_candles_v20260609(train, horizon=int(horizon))
        if pred.empty:
            continue
        p = pred.iloc[-1]
        actual_dir = "UP" if float(actual["close"]) >= float(actual["open"]) else "DOWN"
        pred_dir = "UP" if float(p["close"]) >= float(p["open"]) else "DOWN"
        err_pct = (float(p["close"]) / max(float(actual["close"]), 1e-12) - 1.0) * 100.0
        rows.append({
            "time": actual["time"],
            "Actual Open": round(float(actual["open"]), 6),
            "Actual High": round(float(actual["high"]), 6),
            "Actual Low": round(float(actual["low"]), 6),
            "Actual Close": round(float(actual["close"]), 6),
            "Pred Open": round(float(p["open"]), 6),
            "Pred High": round(float(p["high"]), 6),
            "Pred Low": round(float(p["low"]), 6),
            "Pred Close": round(float(p["close"]), 6),
            "Actual Direction": actual_dir,
            "Pred Direction": pred_dir,
            "Direction Correct": bool(actual_dir == pred_dir),
            "Close Error %": round(float(err_pct), 5),
        })
    hist = pd.DataFrame(rows)
    if hist.empty:
        return hist, {}
    accuracy = float(hist["Direction Correct"].mean() * 100.0)
    mae = float(hist["Close Error %"].abs().mean())
    summary = {
        "tested_candles": int(len(hist)),
        "direction_accuracy_pct": round(accuracy, 2),
        "avg_abs_close_error_pct": round(mae, 5),
        "last_test_time": str(pd.Timestamp(hist["time"].iloc[-1])),
    }
    return hist.sort_values("time", ascending=False).reset_index(drop=True), summary


def _dv_major_regime_detector_v20260609(d, min_days=5.0, lookback_days=240, horizon=24):
    """Less noisy major-regime detector with hysteresis and minimum duration filter."""
    import pandas as pd
    import numpy as np
    x = _dv_prepare_ohlc_v20260609(d, limit=5000)
    if x.empty or len(x) < 120:
        return {"ok": False, "message": "Need at least 120 clean candles for smooth major-regime detection."}, pd.DataFrame()
    last_time = pd.Timestamp(x["time"].iloc[-1])
    cutoff = last_time - pd.Timedelta(days=float(max(60, lookback_days)))
    x = x[x["time"] >= cutoff].reset_index(drop=True)
    if len(x) < 120:
        x = _dv_prepare_ohlc_v20260609(d, limit=2500)
    close = x["close"].astype(float)
    ret = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    ema_48 = close.ewm(span=48, adjust=False).mean()
    ema_240 = close.ewm(span=240, adjust=False).mean()
    ema_720 = close.ewm(span=720, adjust=False).mean()
    gap_fast = ((ema_48 - ema_240) / close.replace(0, np.nan) * 100).fillna(0.0)
    gap_slow = ((ema_240 - ema_720) / close.replace(0, np.nan) * 100).fillna(0.0)
    slope = ema_240.pct_change(72).fillna(0.0) * 100
    vol = ret.rolling(144, min_periods=36).std().fillna(ret.rolling(36, min_periods=12).std()).fillna(0.0) * 100
    vol_med = vol.rolling(720, min_periods=120).median().fillna(vol.median())
    vol_hi = vol.rolling(720, min_periods=120).quantile(0.72).fillna(vol.quantile(0.72))
    # Hysteresis: stronger threshold to enter trend, weaker threshold to stay.
    labels = []
    prev_dir = "RANGE"
    for gf, gs, sl in zip(gap_fast, gap_slow, slope):
        bull_enter = gf > 0.020 and (gs > -0.018 or sl > 0.004)
        bear_enter = gf < -0.020 and (gs < 0.018 or sl < -0.004)
        bull_stay = prev_dir == "BULL" and gf > 0.006
        bear_stay = prev_dir == "BEAR" and gf < -0.006
        if bull_enter or bull_stay:
            prev_dir = "BULL"
        elif bear_enter or bear_stay:
            prev_dir = "BEAR"
        else:
            prev_dir = "RANGE"
        labels.append(prev_dir)
    env = np.where(vol > vol_hi, "EXPANSION", np.where(vol < vol_med * 0.70, "COMPRESSION", "NORMAL"))
    raw = pd.Series(labels, index=x.index).astype(str) + "_" + pd.Series(env, index=x.index).astype(str)
    # Mode smoothing over at least min_days. This removes tiny noisy flips.
    bar_delta = _dv_infer_bar_timedelta_v20260609(x)
    bars_per_day = max(1, int(round(pd.Timedelta(days=1) / bar_delta)))
    smooth_window = int(max(24, min(float(min_days) * bars_per_day, 240)))
    smoothed = []
    raw_list = raw.astype(str).tolist()
    for i in range(len(raw_list)):
        w = raw_list[max(0, i - smooth_window + 1):i + 1]
        vc = pd.Series(w).value_counts()
        smoothed.append(str(vc.index[0]) if not vc.empty else raw_list[i])
    x["Major Regime"] = smoothed
    x["Regime Power /100"] = (35 + gap_fast.abs() * 420 + gap_slow.abs() * 240 + slope.abs() * 120 + (vol / vol_med.replace(0, np.nan)).fillna(1) * 8).clip(0, 100).round(1)
    change_points = x.index[x["Major Regime"].ne(x["Major Regime"].shift(1))].tolist()
    if not change_points:
        change_points = [0]
    # Merge short segments into prior segment.
    min_bars = int(max(12, float(min_days) * bars_per_day))
    final = [change_points[0]]
    for cp in change_points[1:]:
        prev = final[-1]
        if cp - prev < min_bars:
            continue
        final.append(cp)
    rows = []
    for j, cp in enumerate(final):
        end = final[j + 1] - 1 if j + 1 < len(final) else len(x) - 1
        seg = x.iloc[cp:end + 1]
        if seg.empty:
            continue
        start_t = pd.Timestamp(seg["time"].iloc[0])
        end_t = pd.Timestamp(seg["time"].iloc[-1])
        days = max((end_t - start_t).total_seconds() / 86400.0, 0.0)
        rows.append({
            "Regime Start": start_t.strftime("%Y-%m-%d %H:%M"),
            "Major Regime": str(seg["Major Regime"].iloc[0]),
            "Days Lasted / So Far": round(float(days), 2),
            "Open": round(float(seg["open"].iloc[0]), 6),
            "Close": round(float(seg["close"].iloc[-1]), 6),
            "Return %": round((float(seg["close"].iloc[-1]) / max(float(seg["open"].iloc[0]), 1e-12) - 1) * 100, 4),
            "Regime Power /100": round(float(seg["Regime Power /100"].mean()), 1),
            "Bars": int(len(seg)),
        })
    hist = pd.DataFrame(rows)
    if hist.empty:
        return {"ok": False, "message": "No major regime history was built."}, pd.DataFrame()
    current = hist.iloc[-1].to_dict()
    completed = pd.to_numeric(hist["Days Lasted / So Far"], errors="coerce").iloc[:-1].dropna()
    expected = max(float(completed.median()) if len(completed) else float(min_days) * 2.0, float(min_days))
    days_now = float(current.get("Days Lasted / So Far", 0.0))
    days_left = max(expected - days_now, 0.0)
    status = "STABLE / KEEP STRATEGY"
    note = "Major regime is smooth enough; no strategy change from noise alone."
    if days_now >= expected * 1.35:
        status = "REVIEW STRATEGY SOON"
        note = "Current regime is older than normal. Watch for transition and reduce blind one-way assumptions."
    elif days_left <= max(1.0, expected * 0.18):
        status = "WATCH CHANGE"
        note = "Current regime is near its normal duration limit. Watch for true structure change, not one candle noise."
    summary = {
        "ok": True,
        "current_regime": str(current.get("Major Regime", "UNKNOWN")),
        "last_regime_change": str(current.get("Regime Start", "-")),
        "days_since_change": round(days_now, 2),
        "expected_days": round(expected, 2),
        "estimated_days_left": round(days_left, 2),
        "estimated_next_change": (pd.Timestamp(x["time"].iloc[-1]) + pd.Timedelta(days=days_left)).strftime("%Y-%m-%d %H:%M"),
        "regime_power_100": round(float(current.get("Regime Power /100", 0.0)), 1),
        "strategy_status": status,
        "strategy_note": note,
        "min_days_filter": float(min_days),
    }
    return summary, hist.sort_values("Regime Start", ascending=False).reset_index(drop=True)


def _dv_render_candle_powerbi_chart_v20260609(d, predicted, backtest_hist=None):
    import streamlit as st
    import pandas as pd
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception as exc:
        st.warning(f"Plotly is not available for candle chart: {exc}")
        return
    x = _dv_prepare_ohlc_v20260609(d, limit=900)
    if x.empty:
        st.warning("No clean OHLC candles available for chart.")
        return
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.72, 0.28], subplot_titles=("Actual candles + BLUE predicted future candles", "Prediction vs actual close error history"))
    fig.add_trace(go.Candlestick(x=x["time"], open=x["open"], high=x["high"], low=x["low"], close=x["close"], name="Actual candles"), row=1, col=1)
    if isinstance(predicted, pd.DataFrame) and not predicted.empty:
        fig.add_trace(go.Candlestick(
            x=predicted["time"], open=predicted["open"], high=predicted["high"], low=predicted["low"], close=predicted["close"],
            name="BLUE predicted candles",
            increasing={"line":{"color":"#006BFF"}, "fillcolor":"rgba(0,107,255,0.35)"},
            decreasing={"line":{"color":"#0047AB"}, "fillcolor":"rgba(0,71,171,0.25)"},
        ), row=1, col=1)
        fig.add_vrect(x0=x["time"].iloc[-1], x1=predicted["time"].iloc[-1], fillcolor="rgba(0,107,255,0.06)", line_width=0, row=1, col=1)
    if isinstance(backtest_hist, pd.DataFrame) and not backtest_hist.empty:
        bh = backtest_hist.sort_values("time").tail(180)
        fig.add_trace(go.Bar(x=bh["time"], y=bh["Close Error %"], name="Close prediction error %"), row=2, col=1)
    fig.update_layout(height=820, margin=dict(l=6, r=6, t=54, b=8), xaxis_rangeslider_visible=False, legend=dict(orientation="h"), title="Advanced Power BI Price Candle + ML Projection")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})


def _render_lunch_data_visualization_inner_tab():
    import streamlit as st
    import pandas as pd
    import json

    st.markdown("### 📊 Data Visualization Pro++")
    st.caption("Adds actual candles, BLUE predicted future candles, historical predicted-vs-actual candles, and smoother major-regime detection. Original code is not deleted.")

    top = st.columns([1.05, .85, .85, .85, .85])
    with top[0]:
        run = st.button("▶ Run Calculating", use_container_width=True, key="lunch_data_visual_run_calculating_propp_candles_20260609")
    with top[1]:
        rows_limit = st.slider("Rows used", 1000, 5000, int(st.session_state.get("dv_pp_rows", 3000)), 250, key="dv_pp_rows")
    with top[2]:
        horizon = st.slider("Predicted candles", 6, 96, int(st.session_state.get("dv_pp_horizon", 36)), 6, key="dv_pp_horizon")
    with top[3]:
        min_days = st.slider("Regime min days", 3, 21, int(st.session_state.get("dv_pp_min_days", 5)), 1, key="dv_pp_min_days")
    with top[4]:
        bt_lookback = st.slider("Backtest candles", 60, 500, int(st.session_state.get("dv_pp_bt", 180)), 20, key="dv_pp_bt")

    sig = (_lunch_df_signature(), int(rows_limit), int(horizon), int(min_days), int(bt_lookback), "dv_propp_candle_20260609")
    if run or st.session_state.get("dv_pp_sig") != sig:
        st.session_state["lunch_bi_visual_ready"] = True
        with st.spinner("Calculating Data Visualization Pro++ candle projection…"):
            d = _clean_lunch_visual_df(limit=int(rows_limit))
            d = _dv_prepare_ohlc_v20260609(d, limit=int(rows_limit))
            if d.empty or len(d) < 120:
                st.warning("Not enough clean OHLC data. Refresh/connect EURUSD or selected symbol first. Need at least 120 candles.")
                _render_lunch_copy_refresh_bar()
                return
            base_result = _five_layer_powerbi_calculate(d, horizon=int(horizon))
            predicted = _dv_predict_future_candles_v20260609(d, horizon=int(horizon))
            bt_hist, bt_summary = _dv_prediction_vs_actual_history_v20260609(d, lookback=int(bt_lookback), horizon=1)
            regime_summary, regime_hist = _dv_major_regime_detector_v20260609(d, min_days=float(min_days), lookback_days=240, horizon=int(horizon))
            st.session_state["dv_pp_df"] = d
            st.session_state["dv_pp_base_result"] = base_result
            st.session_state["dv_pp_predicted"] = predicted
            st.session_state["dv_pp_bt_hist"] = bt_hist
            st.session_state["dv_pp_bt_summary"] = bt_summary
            st.session_state["dv_pp_regime_summary"] = regime_summary
            st.session_state["dv_pp_regime_hist"] = regime_hist
            st.session_state["dv_pp_sig"] = sig
        st.success("Calculation complete: candle chart, blue future candles, history check, and smooth regime detector are ready.")

    if not st.session_state.get("lunch_bi_visual_ready", False):
        st.info("Press **Run Calculating**. Nothing heavy runs until you press it.")
        _render_lunch_copy_refresh_bar()
        return

    d = st.session_state.get("dv_pp_df", pd.DataFrame())
    result = st.session_state.get("dv_pp_base_result", {})
    predicted = st.session_state.get("dv_pp_predicted", pd.DataFrame())
    bt_hist = st.session_state.get("dv_pp_bt_hist", pd.DataFrame())
    bt_summary = st.session_state.get("dv_pp_bt_summary", {})
    regime_summary = st.session_state.get("dv_pp_regime_summary", {})
    regime_hist = st.session_state.get("dv_pp_regime_hist", pd.DataFrame())

    tabs = st.tabs(["Candle Chart", "Original PowerBI + ML", "Prediction vs Actual", "Smooth Regime", "Copy Export"])

    with tabs[0]:
        c = st.columns(6)
        if isinstance(result, dict) and result.get("ok"):
            c[0].metric("Master Score", f"{result.get('master_score', '-')}/10")
            c[1].metric("Bull Probability", f"{result.get('bull_probability', '-')}%")
        if isinstance(regime_summary, dict) and regime_summary.get("ok"):
            c[2].metric("Current Regime", regime_summary.get("current_regime", "-"))
            c[3].metric("Days In Regime", regime_summary.get("days_since_change", "-"))
            c[4].metric("Est. Days Left", regime_summary.get("estimated_days_left", "-"))
            c[5].metric("Strategy", regime_summary.get("strategy_status", "-"))
        _dv_render_candle_powerbi_chart_v20260609(d, predicted, bt_hist)
        if isinstance(predicted, pd.DataFrame) and not predicted.empty:
            st.markdown("#### BLUE predicted future candle table")
            st.dataframe(predicted, use_container_width=True, hide_index=True, height=260)

    with tabs[1]:
        # Keep your existing advanced dashboard visible.
        try:
            st.session_state["lunch_5layer_powerbi_result"] = result
            st.session_state["lunch_5layer_powerbi_df"] = d
            _render_lunch_advanced_powerbi_ml_projection(d, horizon=int(horizon))
        except Exception as exc:
            st.warning(f"Original PowerBI + ML renderer could not display: {exc}")
            if isinstance(result, dict):
                st.json({k: str(v) for k, v in result.items() if k not in {"vote_df", "deep_df", "forecast_df", "history"}})

    with tabs[2]:
        st.markdown("#### How previous predicted candle compared with what actually happened")
        if bt_summary:
            b = st.columns(4)
            b[0].metric("Tested Candles", bt_summary.get("tested_candles", 0))
            b[1].metric("Direction Accuracy", f"{bt_summary.get('direction_accuracy_pct', 0)}%")
            b[2].metric("Avg Close Error", f"{bt_summary.get('avg_abs_close_error_pct', 0)}%")
            b[3].metric("Last Test", bt_summary.get("last_test_time", "-"))
        if isinstance(bt_hist, pd.DataFrame) and not bt_hist.empty:
            st.dataframe(bt_hist, use_container_width=True, hide_index=True, height=420)
        else:
            st.info("Need more history for prediction-vs-actual testing.")

    with tabs[3]:
        st.markdown("#### Smooth major-regime detector — less noise, more reliable structure change")
        if isinstance(regime_summary, dict) and regime_summary.get("ok"):
            r = st.columns(6)
            r[0].metric("Current Regime", regime_summary.get("current_regime", "-"))
            r[1].metric("Started", regime_summary.get("last_regime_change", "-"))
            r[2].metric("Days So Far", regime_summary.get("days_since_change", "-"))
            r[3].metric("Expected Days", regime_summary.get("expected_days", "-"))
            r[4].metric("Estimated Days Left", regime_summary.get("estimated_days_left", "-"))
            r[5].metric("Power", f"{regime_summary.get('regime_power_100', '-')}/100")
            st.info(regime_summary.get("strategy_note", ""))
            st.caption(f"Noise filter: a regime must persist around {regime_summary.get('min_days_filter', min_days)} days before it counts as a major structure change.")
            st.dataframe(regime_hist, use_container_width=True, hide_index=True, height=420)
        else:
            st.warning((regime_summary or {}).get("message", "Smooth regime detector unavailable."))

    with tabs[4]:
        payload = {
            "smooth_regime_summary": regime_summary,
            "prediction_backtest_summary": bt_summary,
            "future_blue_predicted_candles": predicted.to_dict("records") if isinstance(predicted, pd.DataFrame) else [],
            "advanced_powerbi_ml_summary": {k: v for k, v in (result or {}).items() if k not in {"vote_df", "deep_df", "forecast_df", "history"}},
        }
        st.session_state["lunch_visualization_export"] = json.dumps(payload, indent=2, default=str)
        try:
            from core.pro_terminal_uiux import render_mobile_copy_button
            render_mobile_copy_button("Copy Data Visualization Pro++", st.session_state["lunch_visualization_export"], "copy_dv_propp_candle_20260609")
        except Exception:
            st.json(payload)

    _render_lunch_copy_refresh_bar()


