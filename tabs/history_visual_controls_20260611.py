"""2026-06-11 additive History/Visualization control centers.

Non-destructive patch: adds UI controls, filters, tables, replay data, and
interpretation panels using existing session-state calculation outputs only.
No new ML model and no replacement of existing charts/tables.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
import streamlit as st


def install(ns: Dict[str, Any]) -> None:
    def _num(x: Any, default: float = 0.0) -> float:
        try:
            if x is None or (isinstance(x, float) and np.isnan(x)):
                return default
            return float(x)
        except Exception:
            return default

    def _prep_df(df: Any, limit: int = 2500) -> pd.DataFrame:
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame()
        x = df.copy().tail(limit)
        x.columns = [str(c).strip().lower() for c in x.columns]
        for src in ("datetime", "timestamp", "date"):
            if src in x.columns and "time" not in x.columns:
                x = x.rename(columns={src: "time"})
        if "time" not in x.columns:
            return pd.DataFrame()
        x["time"] = pd.to_datetime(x["time"], errors="coerce")
        x = x.dropna(subset=["time"]).sort_values("time").drop_duplicates("time", keep="last")
        for c in ("open", "high", "low", "close"):
            if c in x.columns:
                x[c] = pd.to_numeric(x[c], errors="coerce")
        return x.reset_index(drop=True)

    def _existing_data() -> pd.DataFrame:
        for key in ("dv_pp_df", "lunch_5layer_powerbi_df", "last_df", "shared_df", "market_df", "df"):
            x = _prep_df(st.session_state.get(key), 3200)
            if not x.empty:
                return x
        return pd.DataFrame()

    def _direction_from_close(x: pd.DataFrame, lookback: int = 6) -> str:
        try:
            if len(x) <= lookback or "close" not in x.columns:
                return "WAIT"
            delta = float(x["close"].iloc[-1] - x["close"].iloc[-lookback-1])
            if abs(delta) < max(0.00005, float(x["close"].iloc[-1]) * 0.00005):
                return "WAIT"
            return "BUY" if delta > 0 else "SELL"
        except Exception:
            return "WAIT"

    def _regime_label(window: pd.DataFrame) -> Tuple[str, str]:
        if not isinstance(window, pd.DataFrame) or window.empty or "close" not in window.columns:
            return "RANGE_LOW_DATA", "WAIT"
        close = pd.to_numeric(window["close"], errors="coerce").dropna()
        if len(close) < 8:
            return "RANGE_LOW_DATA", "WAIT"
        ret = close.pct_change().dropna()
        vol = float(ret.tail(min(48, len(ret))).std() or 0.0)
        gap = float((close.iloc[-1] - close.iloc[max(0, len(close)-min(24, len(close)))]) / max(abs(close.iloc[-1]), 1e-12))
        if abs(gap) < 0.00035:
            return ("COMPRESSION" if vol < 0.00045 else "RANGE"), "WAIT"
        if gap > 0:
            return ("BULL_COMPRESSION" if vol < 0.00045 else "BULL_NORMAL"), "BUY"
        return ("BEAR_COMPRESSION" if vol < 0.00045 else "BEAR_NORMAL"), "SELL"

    def _latest_pack() -> Dict[str, Any]:
        return (st.session_state.get("technical_logic_upgrade_lunch_v20260611") or
                st.session_state.get("technical_logic_upgrade_v20260611") or {})

    def _summary_values() -> Dict[str, Any]:
        pack = _latest_pack()
        s = pack.get("summary", {}) if isinstance(pack, dict) else {}
        result = st.session_state.get("dv_pp_base_result", {}) or st.session_state.get("lunch_5layer_powerbi_result", {}) or {}
        bt = st.session_state.get("dv_pp_bt_summary", {}) or {}
        regime = st.session_state.get("dv_pp_regime_summary", {}) or {}
        return {"summary": s if isinstance(s, dict) else {}, "result": result if isinstance(result, dict) else {}, "bt": bt if isinstance(bt, dict) else {}, "regime": regime if isinstance(regime, dict) else {}}

    def _history_table(df: pd.DataFrame) -> pd.DataFrame:
        x = _prep_df(df, 1600)
        if x.empty:
            return pd.DataFrame()
        vals = _summary_values(); s = vals["summary"]; r = vals["result"]; bt = vals["bt"]
        rows = []
        for i in range(max(0, len(x)-720), len(x)):
            w1 = x.iloc[max(0, i-24):i+1]
            w4 = x.iloc[max(0, i-96):i+1]
            wd = x.iloc[max(0, i-240):i+1]
            h1, d1 = _regime_label(w1); h4, d4 = _regime_label(w4); dd, dday = _regime_label(wd)
            dirs = [d1, d4, dday]
            regime_dir = max(set(dirs), key=dirs.count) if dirs else "WAIT"
            pred_dir = _direction_from_close(x.iloc[max(0, i-6):i+1], 3)
            conflict = regime_dir in ("BUY", "SELL") and pred_dir in ("BUY", "SELL") and regime_dir != pred_dir
            close = pd.to_numeric(w1["close"], errors="coerce").dropna()
            ret = close.pct_change().dropna()
            vol_penalty = min(25.0, float((ret.std() or 0.0) * 45000)) if len(ret) else 8.0
            agreement = _num(s.get("Forecast Agreement Score", 0), 50)
            reliability = _num(s.get("Reliability Accuracy %", bt.get("direction_accuracy_pct", 0)), 50)
            market_q = max(0, min(100, 0.38*agreement + 0.36*reliability + 26 - vol_penalty - (15 if conflict else 0)))
            master = _num(r.get("master_score", s.get("Master Score", 5)), 5)
            entry = _num(r.get("entry_score", s.get("Entry Score", master)), master)
            hold = _num(r.get("hold_score", s.get("Hold Safety", master)), master)
            exit_risk = _num(r.get("exit_risk", s.get("Exit Risk", max(0,10-master))), max(0,10-master))
            tpq = _num(r.get("tp_quality", s.get("TP Quality", master)), master)
            decision = "NO TRADE" if market_q < 42 or exit_risk >= 7 else "COUNTER TREND / PROTECT" if conflict else "ALLOWED" if market_q >= 62 and entry >= 5 else "WAIT / PULLBACK"
            rows.append({
                "Time": x["time"].iloc[i], "H1 Regime": h1, "H4 Regime": h4, "D1 Regime": dd,
                "Regime Direction": regime_dir, "Prediction Direction": pred_dir,
                "Master Score": round(master, 2), "Entry Score": round(entry, 2), "Hold Safety": round(hold, 2),
                "Exit Risk": round(exit_risk, 2), "TP Quality": round(tpq, 2), "Market Quality": round(market_q, 1),
                "Forecast Agreement": round(agreement, 1), "Reliability": round(reliability, 1),
                "Conflict Status": "CONFLICT" if conflict else "OK", "Counter Trend Label": "COUNTER TREND" if conflict else "ALIGNED / NEUTRAL",
                "Final Decision": decision,
            })
        return pd.DataFrame(rows).sort_values("Time", ascending=False).reset_index(drop=True)

    def _apply_history_filters(hist: pd.DataFrame, prefix: str) -> pd.DataFrame:
        if not isinstance(hist, pd.DataFrame) or hist.empty:
            return pd.DataFrame()
        out = hist.copy()
        now = pd.Timestamp(out["Time"].max())
        c1 = st.columns(4)
        with c1[0]: day_sel = st.date_input("Day Selector", value=now.date(), key=f"{prefix}_day")
        with c1[1]: hour_sel = st.selectbox("Hour Selector", ["All"] + list(range(24)), key=f"{prefix}_hour")
        with c1[2]: regime_sel = st.selectbox("Regime Selector", ["All"] + sorted(out["Regime Direction"].dropna().astype(str).unique().tolist()), key=f"{prefix}_regime")
        with c1[3]: decision_sel = st.selectbox("Decision Selector", ["All"] + sorted(out["Final Decision"].dropna().astype(str).unique().tolist()), key=f"{prefix}_decision")
        c2 = st.columns(2)
        with c2[0]: rel_range = st.slider("Reliability Range", 0, 100, (0, 100), key=f"{prefix}_rel")
        with c2[1]: mq_range = st.slider("Market Quality Range", 0, 100, (0, 100), key=f"{prefix}_mq")
        if day_sel:
            out = out[pd.to_datetime(out["Time"]).dt.date == day_sel]
        if hour_sel != "All":
            out = out[pd.to_datetime(out["Time"]).dt.hour == int(hour_sel)]
        if regime_sel != "All":
            out = out[out["Regime Direction"].astype(str) == regime_sel]
        if decision_sel != "All":
            out = out[out["Final Decision"].astype(str) == decision_sel]
        out = out[(pd.to_numeric(out["Reliability"], errors="coerce").between(rel_range[0], rel_range[1])) & (pd.to_numeric(out["Market Quality"], errors="coerce").between(mq_range[0], mq_range[1]))]
        return out

    def _quick_filter(hist: pd.DataFrame, label: str) -> pd.DataFrame:
        out = hist.copy(); t = pd.to_datetime(out["Time"], errors="coerce"); max_t = t.max()
        if label == "Today": out = out[t.dt.date == max_t.date()]
        elif label.startswith("Last ") and "Days" in label:
            days = int(label.split()[1]); out = out[t >= max_t - pd.Timedelta(days=days)]
        elif label == "NY/London Overlap Only": out = out[t.dt.hour.isin([12,13,14,15,16])]
        elif label == "High Quality Only": out = out[pd.to_numeric(out["Market Quality"], errors="coerce") >= 62]
        elif label == "High Risk Only": out = out[pd.to_numeric(out["Exit Risk"], errors="coerce") >= 7]
        elif label == "Conflict Only": out = out[out["Conflict Status"].astype(str).str.contains("CONFLICT", case=False, na=False)]
        elif label == "Counter Trend Only": out = out[out["Counter Trend Label"].astype(str).str.contains("COUNTER", case=False, na=False)]
        elif label == "Best Hours": out = out.sort_values(["Market Quality", "Reliability"], ascending=False).head(60)
        elif label == "Worst Hours": out = out.sort_values(["Market Quality", "Reliability"], ascending=True).head(60)
        return out

    def _render_history_control_center(location: str = "Lunch") -> None:
        df = _existing_data()
        hist = _history_table(df)
        st.markdown("### 🧭 History Control Center")
        st.caption("Filter existing calculated rows only. No recalculation is triggered here.")
        if hist.empty:
            st.info("Run Calculation first so the control center can filter the stored output.")
            return
        choices = ["Today", "Last 2 Days", "Last 5 Days", "Last 10 Days", "Last 25 Days", "Custom Day", "Custom Hour", "NY/London Overlap Only", "High Quality Only", "High Risk Only", "Conflict Only", "Counter Trend Only", "Best Hours", "Worst Hours"]
        choice = st.radio("History choice buttons", choices, horizontal=True, key=f"hist_choice_{location}")
        view = hist if choice in ("Custom Day", "Custom Hour") else _quick_filter(hist, choice)
        with st.expander("Open / Close — Advanced selectors", expanded=(choice in ("Custom Day", "Custom Hour"))):
            view = _apply_history_filters(view, f"hist_{location}")
        st.markdown("#### Regime History Table")
        st.dataframe(view, use_container_width=True, hide_index=True, height=420)
        st.session_state[f"regime_history_table_{location}"] = view

    def _backtest_summary(hist: pd.DataFrame) -> Dict[str, Any]:
        if hist.empty: return {}
        by_hour = hist.assign(Hour=pd.to_datetime(hist["Time"]).dt.hour).groupby("Hour")["Market Quality"].mean()
        by_reg = hist.groupby("H1 Regime")["Market Quality"].mean()
        return {
            "Direction Accuracy %": round(_num(_summary_values()["bt"].get("direction_accuracy_pct"), _num(hist["Reliability"].mean(), 0)), 2),
            "Regime Accuracy %": round(_num(hist["Forecast Agreement"].mean(), 0), 2),
            "Average Error %": _summary_values()["bt"].get("avg_abs_close_error_pct", "-"),
            "Best Hour": int(by_hour.idxmax()) if not by_hour.empty else "-",
            "Worst Hour": int(by_hour.idxmin()) if not by_hour.empty else "-",
            "Best Regime": str(by_reg.idxmax()) if not by_reg.empty else "-",
            "Worst Regime": str(by_reg.idxmin()) if not by_reg.empty else "-",
            "Highest Reliability Hour": int(hist.assign(Hour=pd.to_datetime(hist["Time"]).dt.hour).sort_values("Reliability", ascending=False)["Hour"].iloc[0]),
            "Highest Market Quality Hour": int(hist.assign(Hour=pd.to_datetime(hist["Time"]).dt.hour).sort_values("Market Quality", ascending=False)["Hour"].iloc[0]),
        }

    def _render_visual_control_center() -> None:
        st.markdown("### 🎛️ Power BI Visualization Control Center")
        st.caption("Display/replay/overlay controls only. Original Power BI chart and ML tables remain unchanged.")
        a = st.columns(4)
        horizon_choice = a[0].radio("Projection window", ["Next 3H", "Next 6H", "Next 12H"], horizontal=True, key="viz_horizon_choice_v20260611")
        replay_choice = a[1].radio("Replay", ["Replay Last 1 Day", "Replay Last 2 Days", "Replay Last 5 Days"], horizontal=True, key="viz_replay_choice_v20260611")
        day_filter = a[2].radio("Session filter", ["Today Only", "NY/London Only", "All"], horizontal=True, key="viz_day_filter_v20260611")
        density = a[3].selectbox("View density", ["Phone Safe", "Balanced", "Full"], key="viz_density_v20260611")
        b = st.columns(4)
        show_prev = b[0].toggle("Show Previous Prediction", True, key="show_prev_pred_v20260611")
        show_future = b[1].toggle("Show Future Prediction", True, key="show_future_pred_v20260611")
        show_risk = b[2].toggle("Show Risk Band", True, key="show_risk_band_v20260611")
        show_regime = b[3].toggle("Show Regime Overlay", True, key="show_regime_overlay_v20260611")
        c = st.columns(2)
        show_rel = c[0].toggle("Show Reliability Overlay", True, key="show_reliability_overlay_v20260611")
        show_conf = c[1].toggle("Show Conflict Overlay", True, key="show_conflict_overlay_v20260611")
        st.session_state["powerbi_visual_control_center"] = {"horizon": horizon_choice, "replay": replay_choice, "filter": day_filter, "density": density, "previous": show_prev, "future": show_future, "risk_band": show_risk, "regime_overlay": show_regime, "reliability_overlay": show_rel, "conflict_overlay": show_conf}

    def _render_regime_prediction_panel() -> None:
        vals = _summary_values(); s = vals["summary"]; regime = vals["regime"]
        st.markdown("### 🟩 Regime Prediction Panel")
        m = st.columns(5)
        m[0].metric("Current Regime", regime.get("current_regime", "-"))
        m[1].metric("Regime Direction", s.get("Regime Direction", "-"))
        m[2].metric("Predicted Next Regime", regime.get("predicted_next_regime", regime.get("next_regime", "-")))
        m[3].metric("Estimated Regime Change Time", regime.get("predicted_next_regime_change", regime.get("estimated_next_change", "-")))
        m[4].metric("Days In Regime", regime.get("days_since_last_change", regime.get("days_since_change", "-")))
        n = st.columns(5)
        n[0].metric("Estimated Days Remaining", regime.get("estimated_days_remaining", regime.get("estimated_days_left", "-")))
        n[1].metric("Regime Confidence", regime.get("regime_power_100", s.get("MTF Agreement %", "-")))
        n[2].metric("Reliability", s.get("Reliability Accuracy %", "-"))
        n[3].metric("Market Quality", s.get("Market Quality Score", "-"))
        n[4].metric("Conflict Status", "CONFLICT" if s.get("Conflict") else "OK")
        hist = _history_table(_existing_data()).head(120)
        st.markdown("#### Regime Prediction Table")
        if not hist.empty: st.dataframe(hist, use_container_width=True, hide_index=True, height=340)
        else: st.info("Run Calculation first to populate the regime prediction table.")

    def _render_self_backtest_center() -> None:
        hist = _history_table(_existing_data())
        st.markdown("### 🧪 Self Backtest Center")
        st.caption("Summary uses existing stored result/history only; it does not train or recalculate models.")
        sm = _backtest_summary(hist)
        if not sm:
            st.info("Run Calculation first to populate stored backtest outputs.")
            return
        cols = st.columns(3)
        for idx, (k, v) in enumerate(sm.items()):
            cols[idx % 3].metric(k, v)
        with st.expander("Open / Close — Backtest summary JSON", expanded=False):
            st.json(sm)

    prev_lunch = ns.get("_render_metric_home_combined_inner_tab")
    def _render_lunch_with_controls():
        if callable(prev_lunch):
            prev_lunch()
        try:
            _render_history_control_center("Lunch")
        except Exception as exc:
            st.warning(f"History Control Center skipped safely: {exc}")
    ns["_render_metric_home_combined_inner_tab"] = _render_lunch_with_controls

    prev_dv = ns.get("_render_lunch_data_visualization_inner_tab")
    def _render_dv_with_controls():
        if callable(prev_dv):
            prev_dv()
        try:
            _render_visual_control_center()
            _render_regime_prediction_panel()
            _render_self_backtest_center()
        except Exception as exc:
            st.warning(f"Visualization control upgrade skipped safely: {exc}")
    ns["_render_lunch_data_visualization_inner_tab"] = _render_dv_with_controls

    prev_copy = ns.get("_build_lunch_all_copy_text")
    def _build_copy_with_controls():
        base = prev_copy() if callable(prev_copy) else ""
        payload = {
            "history_control_center_active": True,
            "powerbi_visual_control_center": st.session_state.get("powerbi_visual_control_center", {}),
            "latest_regime_history_rows": (st.session_state.get("regime_history_table_Lunch").head(80).to_dict("records") if isinstance(st.session_state.get("regime_history_table_Lunch"), pd.DataFrame) else []),
        }
        return str(base) + "\n\nHISTORY + POWERBI CONTROL CENTER 2026-06-11\n" + "="*64 + "\n" + json.dumps(payload, indent=2, default=str, ensure_ascii=False)
    ns["_build_lunch_all_copy_text"] = _build_copy_with_controls
