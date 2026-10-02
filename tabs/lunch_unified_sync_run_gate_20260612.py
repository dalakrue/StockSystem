"""2026-06-12 Lunch cleanup: one run-gated NY/London + Home sync section.

This patch is display/wrapper logic only. It does not remove original calculation
functions and it does not introduce a new ML model. Heavy/sync work runs only
when the user presses the Run button inside the merged field.
"""
from __future__ import annotations


def install(ns: dict) -> None:
    import json
    import math
    from typing import Any

    import numpy as np
    import pandas as pd
    import streamlit as st

    def _num(v: Any, default: float = 0.0) -> float:
        try:
            x = float(v)
            return x if math.isfinite(x) else float(default)
        except Exception:
            return float(default)

    def _txt(v: Any, default: str = "-") -> str:
        try:
            s = str(v)
            return s if s and s.lower() != "nan" else default
        except Exception:
            return default

    def _safe_records(obj: Any, rows: int = 120) -> Any:
        try:
            if isinstance(obj, pd.DataFrame):
                return obj.head(int(rows)).to_dict("records")
            if isinstance(obj, pd.Series):
                return obj.to_dict()
            if isinstance(obj, pd.Timestamp):
                return str(obj)
            if isinstance(obj, dict):
                return {str(k): _safe_records(v, rows=rows) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_safe_records(x, rows=rows) for x in list(obj)[:rows]]
            return obj
        except Exception:
            return str(obj)

    def _prepare_ohlc(df: Any = None, limit: int = 2400) -> pd.DataFrame:
        raw = st.session_state.get("last_df") if df is None else df
        for name in ("_dv_prepare_ohlc_v20260609", "_v6_prepare"):
            fn = ns.get(name)
            if callable(fn):
                try:
                    out = fn(raw, limit=limit) if name.endswith("20260609") else fn(raw).tail(limit)
                    if isinstance(out, pd.DataFrame) and not out.empty:
                        return out.reset_index(drop=True)
                except Exception:
                    pass
        if not isinstance(raw, pd.DataFrame) or raw.empty:
            return pd.DataFrame()
        x = raw.copy().tail(int(limit)).reset_index(drop=True)
        low = {str(c).strip().lower(): c for c in x.columns}
        rename = {}
        for old, new in {"datetime": "time", "date": "time", "timestamp": "time", "o": "open", "h": "high", "l": "low", "c": "close"}.items():
            if old in low and new not in x.columns:
                rename[low[old]] = new
        if rename:
            x = x.rename(columns=rename)
        if "close" not in x.columns:
            return pd.DataFrame()
        if "time" not in x.columns:
            x["time"] = pd.date_range(end=pd.Timestamp.now(), periods=len(x), freq="h")
        x["time"] = pd.to_datetime(x["time"], errors="coerce")
        for c in ["open", "high", "low", "close", "volume"]:
            if c in x.columns:
                x[c] = pd.to_numeric(x[c], errors="coerce")
        if "open" not in x.columns:
            x["open"] = x["close"].shift(1).fillna(x["close"])
        if "high" not in x.columns:
            x["high"] = x[["open", "close"]].max(axis=1)
        if "low" not in x.columns:
            x["low"] = x[["open", "close"]].min(axis=1)
        x = x.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").drop_duplicates("time", keep="last")
        return x.reset_index(drop=True)

    def _direction_from_regime(regime: Any) -> str:
        s = str(regime or "").upper()
        if "BEAR" in s:
            return "SELL"
        if "BULL" in s:
            return "BUY"
        return "WAIT"

    def _raw_pressure_direction(row: pd.Series) -> str:
        buy = _num(row.get("BUY Pressure /10", row.get("BUY Pressure", 0)))
        sell = _num(row.get("SELL Pressure /10", row.get("SELL Pressure", 0)))
        if buy >= sell + 0.55:
            return "BUY"
        if sell >= buy + 0.55:
            return "SELL"
        return "WAIT"

    def _get_or_build_powerbi_regime(d: pd.DataFrame, min_days: int = 5, horizon: int = 24) -> tuple[dict, pd.DataFrame]:
        regime = st.session_state.get("dv_pp_regime_summary", {})
        regime_hist = st.session_state.get("dv_pp_regime_hist", pd.DataFrame())
        if isinstance(regime, dict) and regime.get("current_regime"):
            return regime, regime_hist if isinstance(regime_hist, pd.DataFrame) else pd.DataFrame()
        fn = ns.get("_dv_major_regime_detector_v20260609")
        if callable(fn) and isinstance(d, pd.DataFrame) and not d.empty:
            try:
                regime, regime_hist = fn(d, min_days=float(min_days), lookback_days=240, horizon=int(horizon))
                if isinstance(regime, dict):
                    st.session_state["dv_pp_regime_summary"] = regime
                if isinstance(regime_hist, pd.DataFrame):
                    st.session_state["dv_pp_regime_hist"] = regime_hist
                return regime if isinstance(regime, dict) else {}, regime_hist if isinstance(regime_hist, pd.DataFrame) else pd.DataFrame()
            except Exception as exc:
                return {"ok": False, "message": f"PowerBI regime sync skipped safely: {exc}"}, pd.DataFrame()
        return {"ok": False, "message": "Unified PowerBI regime is not ready. Run Data Visualization once or press this section Run to build from shared OHLC."}, pd.DataFrame()

    def _get_or_build_powerbi_prediction(d: pd.DataFrame, horizon: int = 6) -> pd.DataFrame:
        pred = st.session_state.get("dv_pp_predicted", pd.DataFrame())
        if isinstance(pred, pd.DataFrame) and not pred.empty and "close" in pred.columns:
            return pred.copy().head(int(horizon)).reset_index(drop=True)
        fn = ns.get("_dv_predict_future_candles_v20260609")
        if callable(fn) and isinstance(d, pd.DataFrame) and not d.empty:
            try:
                pred = fn(d, horizon=int(horizon))
                if isinstance(pred, pd.DataFrame):
                    st.session_state["dv_pp_predicted"] = pred
                    return pred.copy().head(int(horizon)).reset_index(drop=True)
            except Exception:
                pass
        return pd.DataFrame()

    def _next_regime_text(regime: dict, d: pd.DataFrame) -> str:
        if not isinstance(regime, dict):
            return "-"
        for k in ["predicted_next_regime_change", "estimated_next_regime_change", "next_regime_change"]:
            if regime.get(k):
                return str(regime.get(k))
        days_left = regime.get("estimated_days_remaining", regime.get("estimated_days_left"))
        try:
            if isinstance(d, pd.DataFrame) and not d.empty and days_left is not None:
                t = pd.Timestamp(d["time"].iloc[-1]) + pd.Timedelta(days=float(days_left))
                return t.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
        return "WAIT / no reliable transition time"

    def _reasonable_1h(d: pd.DataFrame, pred: pd.DataFrame, regime_dir: str) -> dict:
        if not isinstance(d, pd.DataFrame) or d.empty or "close" not in d.columns:
            return {"last_close": None, "raw_price": None, "reasonable_price": None, "raw_direction": "WAIT", "reasonable_direction": "WAIT", "note": "No OHLC data"}
        last = float(pd.to_numeric(d["close"], errors="coerce").dropna().iloc[-1])
        raw_price = None
        if isinstance(pred, pd.DataFrame) and not pred.empty and "close" in pred.columns:
            try:
                raw_price = float(pd.to_numeric(pred["close"], errors="coerce").dropna().iloc[0])
            except Exception:
                raw_price = None
        if raw_price is None:
            ret = pd.to_numeric(d["close"], errors="coerce").pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
            raw_price = last * (1.0 + float(ret.tail(24).mean()))
        raw_dir = "BUY" if raw_price > last else "SELL" if raw_price < last else "WAIT"
        rng = pd.to_numeric(d["high"], errors="coerce").sub(pd.to_numeric(d["low"], errors="coerce")).tail(14).mean() if {"high", "low"}.issubset(d.columns) else 0.0
        dist = max(abs(raw_price - last), float(rng or 0.0) * 0.08, 0.00001)
        reasonable_dir = regime_dir if regime_dir in {"BUY", "SELL"} else raw_dir
        if reasonable_dir == "BUY":
            reasonable_price = last + dist
        elif reasonable_dir == "SELL":
            reasonable_price = last - dist
        else:
            reasonable_price = raw_price
        note = "Synced to Unified PowerBI regime; raw prediction cannot override major regime."
        if regime_dir in {"BUY", "SELL"} and raw_dir in {"BUY", "SELL"} and raw_dir != regime_dir:
            note = f"Conflict fixed: raw {raw_dir} gated to PowerBI {regime_dir}."
        return {
            "last_close": round(last, 5),
            "raw_price": round(float(raw_price), 5),
            "reasonable_price": round(float(reasonable_price), 5),
            "raw_direction": raw_dir,
            "reasonable_direction": reasonable_dir,
            "note": note,
        }

    def _build_synced_nylo(days: int = 25, start_hour: int = 21) -> tuple[pd.DataFrame, dict]:
        d = _prepare_ohlc(limit=max(900, int(days) * 30 + 240))
        if d.empty:
            return pd.DataFrame(), {"ok": False, "message": "No clean OHLC data available."}
        regime, regime_hist = _get_or_build_powerbi_regime(d, min_days=int(st.session_state.get("dv_pp_min_days_v6", 5) or 5), horizon=24)
        current_regime = _txt((regime or {}).get("current_regime"), "RANGE_NORMAL")
        regime_dir = _direction_from_regime(current_regime)
        pred = _get_or_build_powerbi_prediction(d, horizon=6)
        one_h = _reasonable_1h(d, pred, regime_dir)
        next_regime = _next_regime_text(regime, d)

        base_fn = ns.get("_build_ny_london_overlap_hourly_history_v6")
        if callable(base_fn):
            try:
                hist, old_summary = base_fn(df=d, days=int(days), start_hour=int(start_hour))
            except TypeError:
                hist, old_summary = base_fn(days=int(days), start_hour=int(start_hour))
        else:
            hist, old_summary = pd.DataFrame(), {}
        if not isinstance(hist, pd.DataFrame) or hist.empty:
            return pd.DataFrame(), {"ok": False, "message": (old_summary or {}).get("message", "No NY/London rows built."), "powerbi_regime": regime}

        out = hist.copy()
        out["PowerBI Unified Regime"] = current_regime
        out["H1 Regime"] = current_regime
        out["H4 Regime"] = current_regime
        out["D1 Regime"] = current_regime
        out["Unified Regime Direction"] = regime_dir
        out["Raw Pressure Direction"] = out.apply(_raw_pressure_direction, axis=1)
        out["Direction Conflict Fixed"] = out.apply(lambda r: "YES" if regime_dir in {"BUY", "SELL"} and r["Raw Pressure Direction"] in {"BUY", "SELL"} and r["Raw Pressure Direction"] != regime_dir else "NO", axis=1)
        out["Synced Direction"] = out.apply(lambda r: regime_dir if r["Direction Conflict Fixed"] == "YES" else (r["Raw Pressure Direction"] if r["Raw Pressure Direction"] != "WAIT" else regime_dir), axis=1)
        def _final_decision(r: pd.Series) -> str:
            if r.get("Direction Conflict Fixed") == "YES":
                return "WAIT / PROTECT"
            old = str(r.get("Decision", "WAIT")).upper()
            if r.get("Synced Direction") == "WAIT":
                return "WAIT"
            if "ALLOWED" in old:
                return "ALLOWED"
            if "PULLBACK" in old:
                return "WAIT PULLBACK"
            if "HOLD" in old:
                return "HOLD / PROTECT"
            return "NO TRADE"
        out["Final Synced Decision"] = out.apply(_final_decision, axis=1)
        out["Next 1H Reasonable Price"] = one_h.get("reasonable_price")
        out["Next 1H Direction"] = one_h.get("reasonable_direction")
        out["Next Regime Update"] = next_regime

        preferred = [
            "Day", "Hour", "Window Order", "PowerBI Unified Regime", "Unified Regime Direction",
            "Raw Pressure Direction", "Direction Conflict Fixed", "Synced Direction", "Final Synced Decision",
            "Next 1H Reasonable Price", "Next 1H Direction", "Next Regime Update",
            "Entry Pressure /10", "BUY Pressure /10", "SELL Pressure /10", "Score /10", "NY/London Alignment", "Open", "High", "Low", "Close",
        ]
        cols = [c for c in preferred if c in out.columns] + [c for c in out.columns if c not in preferred]
        out = out[cols].reset_index(drop=True)
        conflicts = int((out["Direction Conflict Fixed"] == "YES").sum()) if "Direction Conflict Fixed" in out.columns else 0
        latest = out.iloc[0].to_dict() if len(out) else {}
        summary = {
            "ok": True,
            "rows": int(len(out)),
            "source": "NY/London start-threshold synced to Unified PowerBI regime",
            "start_threshold_hour": f"{int(start_hour)%24:02d}:00",
            "next_6_hours": ", ".join(f"{(int(start_hour)+i)%24:02d}:00" for i in range(6)),
            "current_powerbi_regime": current_regime,
            "regime_direction": regime_dir,
            "next_1h_reasonable": one_h,
            "next_regime_update": next_regime,
            "conflict_rows_fixed": conflicts,
            "latest_final_decision": _txt(latest.get("Final Synced Decision"), "-"),
            "latest_synced_direction": _txt(latest.get("Synced Direction"), "-"),
            "powerbi_regime_summary": regime,
        }
        pack = {"summary": summary, "table": out, "regime_history": regime_hist, "prediction": pred}
        st.session_state["nylo_unified_home_sync_20260612"] = pack
        return out, summary

    def _run_technical_pack_if_possible(d: pd.DataFrame, regime_dir: str, pred: pd.DataFrame) -> None:
        fn = ns.get("_u11_compute_technical_logic")
        if not callable(fn) or not isinstance(d, pd.DataFrame) or d.empty:
            return
        try:
            result = st.session_state.get("dv_pp_base_result", {}) or st.session_state.get("lunch_5layer_powerbi_result", {}) or {}
            pack = fn(d, result, pred, horizon=24)
            if isinstance(pack, dict) and isinstance(pack.get("summary"), dict):
                pack["summary"]["Regime Direction"] = regime_dir
                fdir = str(pack["summary"].get("Prediction Direction", "WAIT")).upper()
                pack["summary"]["Conflict"] = bool(regime_dir in {"BUY", "SELL"} and fdir in {"BUY", "SELL"} and fdir != regime_dir)
                if pack["summary"].get("Conflict"):
                    pack["summary"]["Priority #1"] = "PowerBI regime conflict: protect / wait"
            st.session_state["technical_logic_upgrade_lunch_v20260611"] = pack
        except Exception:
            pass

    def _copy_button(label: str, payload: str, key: str) -> None:
        try:
            from core.pro_terminal_uiux import render_mobile_copy_button
            render_mobile_copy_button(label, payload, key)
        except Exception:
            st.text_area(label, payload, height=260, key=key + "_fallback")

    def _merged_payload() -> str:
        pack = st.session_state.get("nylo_unified_home_sync_20260612", {})
        if not isinstance(pack, dict):
            pack = {}
        safe = {
            "export_type": "NY_LONDON_UNIFIED_HOME_SYNC_20260612",
            "built_at": str(pd.Timestamp.now()),
            "symbol": st.session_state.get("symbol", "EURUSD"),
            "timeframe": st.session_state.get("timeframe", "H1"),
            "source": st.session_state.get("source", st.session_state.get("connector_mode", "DISCONNECTED")),
            "ny_london_unified_sync": _safe_records(pack, rows=180),
            "quality_contract": _safe_records(st.session_state.get("pro_quality_report", {})),
            "page_status_relationship": {
                "shared_data_ready": isinstance(st.session_state.get("last_df"), pd.DataFrame) and not st.session_state.get("last_df").empty,
                "rows": int(len(st.session_state.get("last_df"))) if isinstance(st.session_state.get("last_df"), pd.DataFrame) else 0,
                "relationship": "Sidebar connector -> shared session dataframe -> Lunch -> merged NY/London sync section",
            },
            "moved_powerbi_6h_metrics": _safe_records(st.session_state.get("merged_powerbi_6h_metrics_20260612", {})),
            "moved_status_models": _safe_records(st.session_state.get("merged_status_models_20260612", {})),
        }
        return json.dumps(safe, indent=2, ensure_ascii=False, default=str)

    def _render_quant_quality_status() -> None:
        df = st.session_state.get("last_df")
        rows = int(len(df)) if isinstance(df, pd.DataFrame) else 0
        report = st.session_state.get("pro_quality_report", {}) or {}
        c = st.columns(4)
        c[0].metric("Quant Control", "READY" if rows else "WAIT", f"Rows {rows:,}")
        c[1].metric("Quality Contract", "READY" if report.get("ready") else "NEED DATA", f"Score {_num(report.get('score'), 0):.0f}/100")
        c[2].metric("Open Page Status", "merged here", st.session_state.get("tab_choice", "Lunch"))
        c[3].metric("System Relationship", "shared data ready" if rows else "no shared data")
        st.caption("Global Quant Control, Quality Contract, page status, and system relationship are summarized here to keep the Lunch page clean.")


    def _powerbi_6h_metrics(pred: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
        p = pred.copy() if isinstance(pred, pd.DataFrame) else pd.DataFrame()
        if p.empty:
            p = st.session_state.get("dv_pp_predicted", pd.DataFrame())
            p = p.copy() if isinstance(p, pd.DataFrame) else pd.DataFrame()
        d = _prepare_ohlc(limit=300)
        last_close = None
        if isinstance(d, pd.DataFrame) and not d.empty and "close" in d.columns:
            last_close = _num(pd.to_numeric(d["close"], errors="coerce").dropna().iloc[-1], 0.0)
        prices = pd.Series(dtype=float)
        if not p.empty:
            lower = {str(c).lower(): c for c in p.columns}
            for name in ("predicted_close", "close", "projected close", "prediction close"):
                c = lower.get(name)
                if c is not None:
                    prices = pd.to_numeric(p[c], errors="coerce").dropna().head(6)
                    break
            if prices.empty:
                nums = p.select_dtypes(include="number").columns.tolist()
                if nums:
                    prices = pd.to_numeric(p[nums[-1]], errors="coerce").dropna().head(6)
        if prices.empty and last_close:
            prices = pd.Series([last_close] * 6, dtype=float)
        avg = float(prices.mean()) if not prices.empty else _num(last_close, 0.0)
        spread = float(prices.std()) if len(prices) > 1 else abs(avg) * 0.0008
        spread = max(spread, abs(avg) * 0.0006, 0.00001)
        bt = st.session_state.get("dv_pp_bt_summary", {}) or {}
        err = _num(bt.get("avg_abs_close_error_pct", bt.get("Prediction vs Actual Close Error", 0.0)), 0.0) if isinstance(bt, dict) else 0.0
        status = "Aligned / usable" if err <= 0.08 else "Caution / wide error" if err <= 0.18 else "Protect / high error"
        metrics = {
            "6H Average Predicted Price": round(avg, 5) if avg else "-",
            "6H Upper Bound Average": round(avg + spread, 5) if avg else "-",
            "6H Lower Bound Average": round(avg - spread, 5) if avg else "-",
            "Prediction vs Actual Close Error": f"{err:.4f}%",
            "Dynamic Projection Status": status,
        }
        if not p.empty and not prices.empty:
            p = p.head(6).copy().reset_index(drop=True)
            vals = prices.reset_index(drop=True)
            p["Upper Bound"] = (vals + spread).round(5)
            p["Lower Bound"] = (vals - spread).round(5)
        return metrics, p.head(6) if isinstance(p, pd.DataFrame) else pd.DataFrame()

    def _render_powerbi_6h_inside_merged(pred: pd.DataFrame) -> None:
        st.markdown("#### 📊 Moved PowerBI 6H Bands + Extra Choices")
        st.caption("Moved here from the separate PowerBI 6H Bands section. Uses existing Unified PowerBI prediction/session data only; no new ML model.")
        a = st.columns(4)
        a[0].radio("Projection view", ["6H", "12H", "24H", "48H"], horizontal=True, key="merged_dv_projection_view_20260612")
        a[1].radio("Band mode", ["Normal Band", "Wide Safety Band", "Tight Backtest Band"], horizontal=True, key="merged_dv_band_mode_20260612")
        a[2].radio("Replay filter", ["Today", "2D", "5D", "10D", "25D"], horizontal=True, key="merged_dv_replay_filter_20260612")
        a[3].radio("Signal filter", ["All", "BUY", "SELL", "WAIT", "Conflict"], horizontal=True, key="merged_dv_signal_filter_20260612")
        metrics, p = _powerbi_6h_metrics(pred)
        c = st.columns(5)
        for i, (k, v) in enumerate(metrics.items()):
            c[i % 5].metric(k, v)
        if isinstance(p, pd.DataFrame) and not p.empty:
            st.dataframe(p, use_container_width=True, hide_index=True, height=230)
        st.session_state["merged_powerbi_6h_metrics_20260612"] = metrics

    def _render_technical_inside_merged(summary: dict, table: pd.DataFrame) -> None:
        st.markdown("#### 🧠 Moved Technical Logic Run Display + 25D History")
        st.caption("Moved here from the separate Technical Logic section. It is rebuilt only by **Run Calculating — Merged Sync** and synced to the Unified PowerBI regime.")
        tech = st.session_state.get("technical_logic_upgrade_lunch_v20260611") or st.session_state.get("technical_logic_upgrade_v20260611") or {}
        s = tech.get("summary", {}) if isinstance(tech, dict) else {}
        reg_dir = _txt(summary.get("regime_direction"), _txt(s.get("Regime Direction"), "WAIT")) if isinstance(summary, dict) else _txt(s.get("Regime Direction"), "WAIT")
        pred_dir = _txt(s.get("Prediction Direction"), _txt(summary.get("latest_synced_direction"), "WAIT") if isinstance(summary, dict) else "WAIT")
        conflict = "CONFLICT" if reg_dir in {"BUY", "SELL"} and pred_dir in {"BUY", "SELL"} and reg_dir != pred_dir else "OK"
        safer = "Protect / wait for pullback" if conflict == "CONFLICT" else "Aligned / use normal confirmation"
        c = st.columns(5)
        c[0].metric("Conflict Status", conflict, safer)
        c[1].metric("Next 1H Reasonable Price", (summary.get("next_1h_reasonable", {}) or {}).get("reasonable_price", "-") if isinstance(summary, dict) else "-")
        c[2].metric("Next 1H Direction", (summary.get("next_1h_reasonable", {}) or {}).get("reasonable_direction", "-") if isinstance(summary, dict) else "-")
        c[3].metric("MTF / Unified Regime", f"{reg_dir} vs {pred_dir}")
        c[4].metric("Safer Interpretation", safer)
        if isinstance(s, dict) and s:
            with st.expander("Open / Close — Technical summary JSON", expanded=False):
                st.json(_safe_records(s))
        if isinstance(table, pd.DataFrame) and not table.empty:
            st.markdown("##### 25D synced expectation / NY-London history")
            _history_view(table)

    def _render_moved_status_models(summary: dict, table: pd.DataFrame, pred: pd.DataFrame, r_hist: pd.DataFrame) -> None:
        st.markdown("#### ✅ Moved status + current data + model summaries")
        st.caption("Quant Control, Quality Contract, open page status, system relationship, refresh/current data, intelligence, one-hour exit rule, module/deep frame metrics, basket P/L, candle previous-model frequency, and London upgrade status are summarized here to reduce stacked sections.")
        _render_quant_quality_status()
        df = _prepare_ohlc(limit=300)
        latest = df.tail(1).to_dict("records")[0] if isinstance(df, pd.DataFrame) and not df.empty else {}
        result = st.session_state.get("dv_pp_base_result", {}) or st.session_state.get("lunch_5layer_powerbi_result", {}) or {}
        account = st.session_state.get("account_snapshot", {}) or {}
        info = {
            "refresh_control": "Manual run only; cache refresh happens when Run Calculating — Merged Sync is clicked.",
            "current_data_latest": latest,
            "unified_regime_summary": summary if isinstance(summary, dict) else {},
            "powerbi_ml_summary": {k: v for k, v in result.items() if k not in {"vote_df", "deep_df", "forecast_df", "history"}} if isinstance(result, dict) else {},
            "basket_p_l_model": account if isinstance(account, dict) else {},
            "prediction_rows": int(len(pred)) if isinstance(pred, pd.DataFrame) else 0,
            "regime_history_rows": int(len(r_hist)) if isinstance(r_hist, pd.DataFrame) else 0,
            "ny_london_rows": int(len(table)) if isinstance(table, pd.DataFrame) else 0,
            "london_upgrade_status": "merged / run-gated / copy-full included",
        }
        st.session_state["merged_status_models_20260612"] = info
        cols = st.columns(4)
        cols[0].metric("Refresh Control", "Manual Run")
        cols[1].metric("Current Data", f"{len(df) if isinstance(df, pd.DataFrame) else 0} rows")
        cols[2].metric("Intelligence Sync", "PowerBI regime authority")
        cols[3].metric("London Upgrade", "Merged")
        with st.expander("Open / Close — Current data / intelligence / model JSON", expanded=False):
            st.json(_safe_records(info, rows=60))

    def _history_view(table: pd.DataFrame) -> None:
        choices = ["Today", "2D", "5D", "10D", "25D", "BUY", "SELL", "WAIT", "Conflict Fixed", "Allowed Only", "Protect Only"]
        choice = st.radio("Merged history filters", choices, horizontal=True, key="merged_history_filter_20260612")
        view = table.copy() if isinstance(table, pd.DataFrame) else pd.DataFrame()
        if view.empty:
            st.info("Run the merged section first to build the synced history table.")
            return
        day_col = "Day" if "Day" in view.columns else None
        if day_col and choice in {"Today", "2D", "5D", "10D", "25D"}:
            try:
                dates = pd.to_datetime(view[day_col].astype(str).str.slice(0, 10), errors="coerce")
                max_date = dates.max()
                days = {"Today": 1, "2D": 2, "5D": 5, "10D": 10, "25D": 25}[choice]
                view = view[dates >= max_date - pd.Timedelta(days=days - 1)]
            except Exception:
                pass
        text = view.astype(str).agg(" ".join, axis=1)
        if choice in {"BUY", "SELL", "WAIT"}:
            view = view[text.str.contains(choice, case=False, na=False)]
        elif choice == "Conflict Fixed" and "Direction Conflict Fixed" in view.columns:
            view = view[view["Direction Conflict Fixed"].astype(str).eq("YES")]
        elif choice == "Allowed Only":
            view = view[text.str.contains("ALLOWED", case=False, na=False)]
        elif choice == "Protect Only":
            view = view[text.str.contains("PROTECT", case=False, na=False)]
        st.dataframe(view.reset_index(drop=True), use_container_width=True, hide_index=True, height=390)

    def _render_merged_nylo_section() -> None:
        with st.expander("🌍 Open / Close — NY + London Next 6H + Unified Home Sync", expanded=False):
            st.caption("One manual-run field for NY/London next 6 hours, Unified PowerBI regime sync, next reasonable 1H price/direction, PowerBI 6H bands, Technical Logic + 25D history, Quant Control, Quality Contract, upgrade status, current data, prediction/model summaries, and copy export. Nothing heavy runs until Run is clicked.")
            c = st.columns([1.25, .85, .95, .8])
            with c[0]:
                run = st.button("▶ Run Calculating — Merged Sync", use_container_width=True, key="run_merged_nylo_home_sync_20260612")
            with c[1]:
                days = st.slider("Days", 5, 25, int(st.session_state.get("merged_nylo_days_20260612", 25)), 1, key="merged_nylo_days_20260612")
            with c[2]:
                start_h = st.slider("Start threshold hour", 0, 23, int(st.session_state.get("merged_nylo_start_20260612", 21)), 1, key="merged_nylo_start_20260612")
            with c[3]:
                if st.button("🧹 Reduce duplicate cache", use_container_width=True, key="reduce_dup_cache_20260612"):
                    for k in ["knn_priority_board_Lunch", "knn_priority_board_Lunch Tables", "final_filtered_history_Lunch"]:
                        st.session_state.pop(k, None)
                    st.success("Duplicate display caches cleared. Original functions are kept.")
            st.caption("Selected next 6 hours: " + ", ".join(f"{(int(start_h)+i)%24:02d}:00" for i in range(6)))

            if run:
                with st.spinner("Building synced NY/London + PowerBI regime section…"):
                    table, summary = _build_synced_nylo(days=int(days), start_hour=int(start_h))
                    d = _prepare_ohlc(limit=2400)
                    pred = st.session_state.get("dv_pp_predicted", pd.DataFrame())
                    _run_technical_pack_if_possible(d, str(summary.get("regime_direction", "WAIT")), pred if isinstance(pred, pd.DataFrame) else pd.DataFrame())
                    st.session_state["lunch_copy_payload_signature"] = None
                    st.session_state["nylo_unified_home_sync_text_20260612"] = _merged_payload()
                if summary.get("ok"):
                    st.success("Merged NY/London + Home sync calculation complete.")
                else:
                    st.warning(summary.get("message", "Merged calculation could not complete."))

            pack = st.session_state.get("nylo_unified_home_sync_20260612", {})
            summary = pack.get("summary", {}) if isinstance(pack, dict) else {}
            table = pack.get("table", pd.DataFrame()) if isinstance(pack, dict) else pd.DataFrame()
            pred = pack.get("prediction", pd.DataFrame()) if isinstance(pack, dict) else pd.DataFrame()
            r_hist = pack.get("regime_history", pd.DataFrame()) if isinstance(pack, dict) else pd.DataFrame()
            if not isinstance(table, pd.DataFrame) or table.empty:
                st.info("Press **Run Calculating — Merged Sync**. This section will not calculate automatically on page open.")
                _render_quant_quality_status()
                payload = _merged_payload()
                _copy_button("Copy Merged Section", payload, "copy_empty_merged_nylo_sync_20260612")
                return

            one_h = summary.get("next_1h_reasonable", {}) if isinstance(summary, dict) else {}
            m = st.columns(6)
            m[0].metric("Unified Regime", summary.get("current_powerbi_regime", "-"))
            m[1].metric("Regime Direction", summary.get("regime_direction", "-"))
            m[2].metric("Next 1H Price", one_h.get("reasonable_price", "-"))
            m[3].metric("Next 1H Direction", one_h.get("reasonable_direction", "-"))
            m[4].metric("Latest Decision", summary.get("latest_final_decision", "-"))
            m[5].metric("Conflicts Fixed", summary.get("conflict_rows_fixed", 0))
            st.caption(one_h.get("note", ""))

            tabs = st.tabs(["Next 6H Sync", "PowerBI 6H", "Technical + 25D", "Prediction + Regime", "Status / Models", "Copy"])
            with tabs[0]:
                st.dataframe(table, use_container_width=True, hide_index=True, height=430)
            with tabs[1]:
                _render_powerbi_6h_inside_merged(pred)
            with tabs[2]:
                _render_technical_inside_merged(summary, table)
            with tabs[3]:
                pcols = st.columns(4)
                pcols[0].metric("Raw 1H Price", one_h.get("raw_price", "-"))
                pcols[1].metric("Raw Direction", one_h.get("raw_direction", "-"))
                pcols[2].metric("Next Regime Update", summary.get("next_regime_update", "-"))
                pcols[3].metric("Sync Rule", "Unified PowerBI regime authority")
                if isinstance(pred, pd.DataFrame) and not pred.empty:
                    st.markdown("#### Existing PowerBI future candles used for sync")
                    st.dataframe(pred.head(12), use_container_width=True, hide_index=True, height=240)
                if isinstance(r_hist, pd.DataFrame) and not r_hist.empty:
                    st.markdown("#### Unified PowerBI regime history")
                    st.dataframe(r_hist.head(80), use_container_width=True, hide_index=True, height=300)
            with tabs[4]:
                _render_moved_status_models(summary, table, pred, r_hist)
            with tabs[5]:
                payload = _merged_payload()
                st.session_state["nylo_unified_home_sync_text_20260612"] = payload
                _render_copy_center_no_duplicate(inside_merged=True)
                _copy_button("Copy Merged NY/London + Home Sync", payload, "copy_merged_nylo_home_sync_20260612")

    def _render_copy_center_no_duplicate(inside_merged: bool = False) -> None:
        try:
            from core.pro_terminal_uiux import render_mobile_copy_button, apply_pro_terminal_css
            apply_pro_terminal_css()
        except Exception:
            render_mobile_copy_button = None
        try:
            all_payload = ns.get("_get_cached_lunch_copy_payload", lambda: ns.get("_build_lunch_all_copy_text", lambda: "")())()
        except Exception:
            all_payload = ns.get("_build_lunch_all_copy_text", lambda: "")()
        short_payload = ns.get("_build_short_necessary_copy_text", lambda: "No short copy available.")()
        st.markdown("### 📋 Copy Center" if not inside_merged else "#### 📋 Merged Copy Center")
        a, b, c = st.columns([1, 1, .75])
        with a:
            if render_mobile_copy_button:
                render_mobile_copy_button("Copy Short", short_payload, "copy_short_merged_clean_20260612_v2")
            else:
                st.text_area("Copy Short", short_payload, height=150, key="copy_short_merged_clean_20260612_v2_fallback")
        with b:
            if render_mobile_copy_button:
                render_mobile_copy_button("Copy Full", all_payload, "copy_full_merged_clean_20260612_v2")
            else:
                st.text_area("Copy Full", all_payload, height=220, key="copy_full_merged_clean_20260612_v2_fallback")
        with c:
            if st.button("🔄 Refresh Data + Copy", use_container_width=True, key="refresh_copy_merged_clean_20260612_v2"):
                refresh = {"ok": False, "message": "Refresh did not run."}
                try:
                    from core.app.refresh import refresh_data
                    from core.symbol_universe_20260629 import normalize_instrument
                    selected_symbol = normalize_instrument(st.session_state.get("symbol") or "EURUSD")
                    refresh = refresh_data(st.session_state, symbol_override=selected_symbol, timeframe_override="H1")
                except Exception as exc:
                    refresh = {"ok": False, "status": "FAILURE", "message": f"Refresh failed safely: {exc}"}
                for cache_key in ("lunch_copy_payload_signature", "lunch_copy_payload_cache",
                                  "lunch_metric_result_signature"):
                    st.session_state.pop(cache_key, None)
                st.session_state["lunch_last_copy_refresh"] = refresh
                if bool(refresh.get("ok")) or str(refresh.get("status", "")).upper() in {"OK", "SUCCESS"}:
                    st.toast(f"{st.session_state.get('symbol', 'EURUSD')} H1 refreshed once; copy payload will rebuild from current data.", icon="✅")
                else:
                    st.warning(str(refresh.get("message") or "Refresh failed; previous canonical data was kept."))
                st.rerun()

    def _prediction_moved_notice() -> None:
        # Kept intentionally quiet to prevent a duplicate open/close prediction section.
        st.session_state["lunch_prediction_moved_to_nylo_sync_20260612"] = True

    def _copy_center_moved_notice() -> None:
        # Copy buttons are now inside the merged NY/London field. This quiet no-op prevents duplicate Streamlit keys.
        st.session_state["lunch_copy_center_moved_to_nylo_sync_20260612"] = True

    prev_copy_builder = ns.get("_build_lunch_all_copy_text")
    def _build_lunch_copy_with_merged_sync() -> str:
        base = prev_copy_builder() if callable(prev_copy_builder) else ""
        merged = st.session_state.get("nylo_unified_home_sync_text_20260612") or _merged_payload()
        return str(base) + "\n\nNY/LONDON + UNIFIED HOME SYNC 2026-06-12\n" + "=" * 64 + "\n" + str(merged)

    def _render_lunch_clean() -> None:
        st.session_state["lunch_merge_global_status_20260612"] = True
        # Base Lunch metric table and 010 reverse table stay exactly where the user expects.
        base_metric = ns.get("_render_metric_inner_tab")
        if callable(base_metric):
            base_metric()
        else:
            st.warning("Base Lunch metric renderer is unavailable.")
        _render_merged_nylo_section()
        # Copy Center is moved inside the merged NY/London field to prevent stacked duplicate UI and duplicate Streamlit keys.

    # Optional Data Visualization cleanup: keep the original unified chart, but put add-on
    # band/technical sections into one closed field instead of two stacked fields.
    prev_dv = ns.get("_render_lunch_data_visualization_inner_tab")
    def _render_dv_clean() -> None:
        if callable(prev_dv):
            prev_dv()
        # Do not add more duplicate panels here. The Lunch merged field reads the same
        # dv_pp_* session outputs and syncs to the unified PowerBI regime.

    ns["_render_ny_london_overlap_open_close_field_v6"] = _render_merged_nylo_section
    ns["_render_lunch_copy_refresh_bar"] = _copy_center_moved_notice
    ns["_render_lunch_prediction_section"] = _prediction_moved_notice
    ns["_build_lunch_all_copy_text"] = _build_lunch_copy_with_merged_sync
    ns["_render_metric_home_combined_inner_tab"] = _render_lunch_clean
    ns["_render_lunch_data_visualization_inner_tab"] = _render_dv_clean
    ns["_build_synced_nylo_20260612"] = _build_synced_nylo
