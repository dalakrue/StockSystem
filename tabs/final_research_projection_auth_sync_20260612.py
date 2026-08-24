"""2026-06-12 final cleanup patch.

Goals:
- Move Research into Lunch/Home inner tabs.
- Replace duplicated Data Visualization add-on fields with one merged run-gated field.
- Add a synced PowerBI projection overlay using accuracy-adjusted KNN/Greedy/NLP/Structure outputs.
- Keep original functions available and copy exports updated.
"""
from __future__ import annotations


def install(ns: dict) -> None:
    import json
    import math
    import time
    from typing import Any, Dict, List

    import numpy as np
    import pandas as pd
    import plotly.graph_objects as go
    import streamlit as st

    from core.research_causality_20260618 import causal_binary_target, causal_news_asof, purged_time_order_split

    UNIQUE = "20260612_final_sync2"

    def _num(v: Any, default: float = 0.0) -> float:
        try:
            x = float(v)
            return x if math.isfinite(x) else float(default)
        except Exception:
            return float(default)

    def _safe(obj: Any, rows: int = 120) -> Any:
        try:
            if isinstance(obj, pd.DataFrame):
                return obj.head(rows).to_dict("records")
            if isinstance(obj, pd.Series):
                return obj.to_dict()
            if isinstance(obj, pd.Timestamp):
                return str(obj)
            if isinstance(obj, dict):
                return {str(k): _safe(v, rows) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_safe(x, rows) for x in list(obj)[:rows]]
            return obj
        except Exception:
            return str(obj)

    def _json(obj: Any, rows: int = 120) -> str:
        return json.dumps(_safe(obj, rows), indent=2, ensure_ascii=False, default=str)

    def _copy_button(label: str, text: str, key: str) -> None:
        try:
            from streamlit_copy_button import copy_button
            copy_button(text, label, key=key)
        except Exception:
            try:
                from core.pro_terminal_uiux import render_mobile_copy_button
                render_mobile_copy_button(label, text, key)
            except Exception:
                st.text_area(label, text, height=220, key=key + "_fallback")

    def _mobile_css() -> None:
        big = bool(st.session_state.get("phone_mode", False))
        mult = 1.12 if big else 1.0
        st.markdown(f"""
        <style>
        :root{{--new7-scale:{mult};}}
        .block-container{{max-width:1200px;padding-top:.55rem!important}}
        div[data-testid="stMetric"]{{border-radius:{22*mult:.0f}px!important;padding:{12*mult:.0f}px {14*mult:.0f}px!important;border:1px solid rgba(14,165,233,.22)!important;box-shadow:0 14px 36px rgba(15,23,42,.09)!important;background:linear-gradient(145deg,rgba(255,255,255,.88),rgba(224,242,254,.58))!important}}
        .stButton>button{{border-radius:999px!important;min-height:{48*mult:.0f}px!important;font-size:{15*mult:.0f}px!important;font-weight:900!important;box-shadow:0 12px 24px rgba(14,165,233,.17)!important}}
        .stTabs [data-baseweb="tab"]{{font-size:{14*mult:.0f}px!important;font-weight:900!important;padding:{10*mult:.0f}px {14*mult:.0f}px!important;border-radius:999px!important}}
        textarea,input,.stSelectbox,.stSlider{{font-size:{15*mult:.0f}px!important}}
        div[data-testid="stExpander"]{{border-radius:22px!important;border:1px solid rgba(14,165,233,.22)!important;box-shadow:0 14px 34px rgba(15,23,42,.07)!important;overflow:hidden!important}}
        [data-baseweb="select"], [data-testid="stSlider"]{{background:rgba(255,255,255,.72)!important;border-radius:18px!important;padding:.2rem!important}}
        .new7-pop-card{{animation:new7pop .28s ease-out both}}@keyframes new7pop{{from{{transform:translateY(7px);opacity:.72}}to{{transform:none;opacity:1}}}}
        @media(max-width:780px){{
          .block-container{{padding-left:.45rem!important;padding-right:.45rem!important}}
          div[data-testid="column"]{{min-width:0!important}}
          div[data-testid="stMetric"]{{margin:.20rem 0!important}}
          [data-testid="stHorizontalBlock"]{{gap:.35rem!important}}
          h1{{font-size:{26*mult:.0f}px!important}} h2{{font-size:{22*mult:.0f}px!important}} h3{{font-size:{18*mult:.0f}px!important}}
          .stDataFrame{{font-size:{12*mult:.0f}px!important}}
        }}
        </style>
        """, unsafe_allow_html=True)

    def _dir(regime: Any) -> str:
        s = str(regime).upper()
        if "BEAR" in s:
            return "SELL"
        if "BULL" in s:
            return "BUY"
        return "WAIT"

    def _master_direction() -> str:
        canonical = st.session_state.get("canonical_decision_result_20260617", {})
        if isinstance(canonical, dict):
            value = canonical.get("full_metric_direction") or (canonical.get("final_decision") or {}).get("directional_market_view")
            if value:
                return _dir(value)
        return _dir(_master_regime())

    def _prep_ohlc(limit: int = 6000) -> pd.DataFrame:
        raw = st.session_state.get("dv_pp_df")
        if not isinstance(raw, pd.DataFrame) or raw.empty:
            raw = st.session_state.get("last_df")
        prep = ns.get("_dv_prepare_ohlc_v20260609")
        if callable(prep):
            try:
                out = prep(raw, limit=int(limit))
                if isinstance(out, pd.DataFrame) and not out.empty:
                    return out.tail(int(limit)).reset_index(drop=True)
            except Exception:
                pass
        if not isinstance(raw, pd.DataFrame) or raw.empty:
            return pd.DataFrame()
        d = raw.copy().tail(int(limit)).reset_index(drop=True)
        low = {str(c).lower(): c for c in d.columns}
        for src, dst in {"datetime": "time", "date": "time", "timestamp": "time", "o": "open", "h": "high", "l": "low", "c": "close"}.items():
            if src in low and dst not in d.columns:
                d = d.rename(columns={low[src]: dst})
        if "time" not in d.columns:
            return pd.DataFrame()
        if "close" not in d.columns:
            return pd.DataFrame()
        for col in ["open", "high", "low", "close"]:
            if col not in d.columns:
                d[col] = d["close"]
            d[col] = pd.to_numeric(d[col], errors="coerce")
        d["time"] = pd.to_datetime(d["time"], errors="coerce")
        return d.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)

    def _master_regime() -> str:
        for key in ("dv_pp_regime_summary", "lunch_5layer_powerbi_result", "final_merged_intelligence_pack_20260612", "nylo_unified_home_sync_20260612"):
            obj = st.session_state.get(key, {})
            if isinstance(obj, dict):
                cur = obj.get("current_regime") or obj.get("master_regime")
                if not cur and isinstance(obj.get("summary"), dict):
                    cur = obj["summary"].get("current_powerbi_regime")
                if cur:
                    return str(cur)
        return "RANGE_NORMAL"

    def _base_powerbi_run(rows: int, horizon: int, bt_lookback: int, min_days: int) -> Dict[str, Any]:
        clean_f = ns.get("_clean_lunch_visual_df")
        prep = ns.get("_dv_prepare_ohlc_v20260609")
        clean = clean_f(limit=int(rows)) if callable(clean_f) else st.session_state.get("last_df", pd.DataFrame())
        d = prep(clean, limit=int(rows)) if callable(prep) else _prep_ohlc(int(rows))
        if not isinstance(d, pd.DataFrame) or len(d) < 120:
            return {"ok": False, "message": "Need at least 120 clean OHLC candles."}
        calc = ns.get("_five_layer_powerbi_calculate")
        pred_f = ns.get("_dv_predict_future_candles_v20260609")
        bt_f = ns.get("_dv_prediction_vs_actual_history_v20260609")
        reg_f = ns.get("_dv_major_regime_detector_v20260609")
        result = calc(d, horizon=int(horizon)) if callable(calc) else {}
        pred = pred_f(d, horizon=int(horizon)) if callable(pred_f) else pd.DataFrame()
        if callable(bt_f):
            bt_hist, bt_sum = bt_f(d, lookback=int(bt_lookback), horizon=1)
        else:
            bt_hist, bt_sum = pd.DataFrame(), {}
        if callable(reg_f):
            reg, reg_hist = reg_f(d, min_days=float(min_days), lookback_days=240, horizon=int(horizon))
        else:
            reg, reg_hist = {}, pd.DataFrame()
        st.session_state.update({
            "lunch_bi_visual_ready": True,
            "dv_pp_df": d,
            "dv_pp_base_result": result,
            "dv_pp_predicted": pred,
            "dv_pp_bt_summary": bt_sum,
            "dv_pp_bt_hist": bt_hist,
            "dv_pp_regime_summary": reg,
            "dv_pp_regime_hist": reg_hist,
            "lunch_5layer_powerbi_result": result,
            "lunch_5layer_powerbi_df": d,
        })
        return {"ok": True, "df": d, "result": result, "predicted": pred, "bt_hist": bt_hist, "bt_summary": bt_sum, "regime_summary": reg, "regime_history": reg_hist}

    def _light_quant_structure(d: pd.DataFrame, regime: str) -> Dict[str, Any]:
        if not isinstance(d, pd.DataFrame) or len(d) < 80:
            return {"ok": False, "message": "Need more H1 candles."}
        c = pd.to_numeric(d["close"], errors="coerce").dropna()
        h = pd.to_numeric(d["high"], errors="coerce").reindex(c.index).fillna(c)
        l = pd.to_numeric(d["low"], errors="coerce").reindex(c.index).fillna(c)
        o = pd.to_numeric(d["open"], errors="coerce").reindex(c.index).fillna(c)
        ret = c.pct_change().fillna(0)
        rng = (h - l).abs().replace(0, np.nan).ffill().fillna(c.abs() * 0.00045)
        atr12 = rng.rolling(12, min_periods=4).mean()
        atr72 = rng.rolling(72, min_periods=20).median().replace(0, np.nan)
        ratio = (atr12 / atr72).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        compression = max(0.0, min(100.0, (1.22 - float(ratio.iloc[-1])) / 0.72 * 100.0))
        z = (ret.abs() / ret.rolling(72, min_periods=20).std().replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0)
        shock = max(0.0, min(100.0, float(z.tail(8).max()) * 24.0))
        noise = max(0.0, min(100.0, float(((rng - (c - o).abs()).clip(lower=0) / rng).tail(48).mean()) * 100.0))
        denom = max(float(c.diff().abs().tail(24).sum()), 1e-9)
        trend_quality = max(0.0, min(100.0, abs(float(c.iloc[-1] - c.iloc[-24])) / denom * 100.0))
        md = _dir(regime)
        score = max(0.0, min(100.0, (100 - noise) * .28 + trend_quality * .28 + (100 - shock) * .22 + (100 - abs(compression - 50)) * .22))
        band = max(float(atr12.iloc[-1]), float(c.iloc[-1]) * .00035) * (1.0 + shock / 220.0)
        sign = 1 if md == "BUY" else -1 if md == "SELL" else 0
        next_price = float(c.iloc[-1]) + sign * band * (0.42 + score / 180.0)
        return {
            "ok": True,
            "quant_structure_score": round(score, 1),
            "master_regime": regime,
            "master_direction": md,
            "compression_expansion": {"Compression Score": round(compression, 1), "Expansion Probability": round(min(100.0, compression * .55 + shock * .35), 1), "Time In Compression": int((ratio.tail(72) < .82).sum()), "Expansion Risk": "HIGH" if compression > 72 else "MEDIUM" if compression > 45 else "LOW"},
            "regime_vortex": {"Regime Stability": round(max(0.0, 100 - shock * .45 - noise * .22), 1), "Regime Rotation Speed": round(float(abs(ret.tail(24).mean() - ret.tail(96).mean())) * 100000, 2), "Regime Conflict": "LOW", "Regime Strength": round(trend_quality, 1)},
            "cycle_drift": {"Dominant Cycle Length": "H1 lightweight rhythm", "Cycle Drift Score": round(float(abs(ret.tail(24).mean() - ret.tail(96).mean())) * 100000, 2), "Cycle Stability": round(max(0.0, 100.0 - shock * .5), 1), "Cycle Change Warning": "WATCH" if shock > 55 else "NORMAL"},
            "volatility_waterfall": {"H1 Volatility Energy": round(float(ret.tail(24).std()) * 10000, 3), "H4 Volatility Energy": round(float(ret.rolling(4).sum().tail(42).std()) * 10000, 3), "D1 Volatility Energy": round(float(ret.rolling(24).sum().tail(30).std()) * 10000, 3), "Volatility Drift": round(float((ratio.tail(6).mean() - ratio.tail(72).median()) * 100), 2)},
            "broadband_shock_signature": {"Shock Probability": round(shock, 1), "Shock Magnitude": round(abs(float(ret.iloc[-1])) * 10000, 3), "Shock Persistence": int((z.tail(12) > 2).sum()), "Shock Recovery": round(max(0.0, 100.0 - shock * .75), 1)},
            "aftershock_engine": {"Recent Shock": "YES" if bool((z.tail(12) > 2.4).any()) else "NO", "Aftershock Risk": round(shock, 1), "Stabilization Score": round(max(0.0, 100.0 - shock * .75), 1)},
            "microstructure_reality": {"Noise Level": round(noise, 1), "Trend Quality": round(trend_quality, 1), "Directional Efficiency": round(trend_quality, 1)},
            "sync_outputs": {"Next 1H Reasonable Direction": md if score >= 42 else "WAIT", "Next 1H Reasonable Price": round(next_price, 5), "Next 1H Lower Band": round(next_price - band, 5), "Next 1H Upper Band": round(next_price + band, 5), "Next Regime Update": "Continuation likely" if score >= 62 and shock < 55 else "Rotation watch"},
        }

    def _news_summary_from_existing(master_dir: str) -> Dict[str, Any]:
        # Prefer existing News/NLP pack so no API/RSS call is made here.
        for key in ("final_merged_intelligence_pack_20260612", "dv_news_nlp_pack_20260612", "research_pack_20260612"):
            obj = st.session_state.get(key, {})
            if not isinstance(obj, dict):
                continue
            nlp = obj.get("news_nlp") or obj.get("nlp") or {}
            summ = nlp.get("summary", {}) if isinstance(nlp, dict) else {}
            if summ:
                return {"summary": summ, "table": nlp.get("table", pd.DataFrame()) if isinstance(nlp, dict) else pd.DataFrame(), "source": obj.get("source", "cached")}
        return {"summary": {"news_direction": "WAIT", "news_sync": "NEUTRAL", "articles_used": 0, "Master Direction": master_dir, "message": "Run News/NLP if you want external confirmation."}, "table": pd.DataFrame(), "source": "cached-none"}

    def _accuracy_adjusted_projection(d: pd.DataFrame, q: Dict[str, Any], news: Dict[str, Any], horizon: int = 24) -> pd.DataFrame:
        if not isinstance(d, pd.DataFrame) or d.empty:
            return pd.DataFrame()
        c = pd.to_numeric(d["close"], errors="coerce").dropna()
        h = pd.to_numeric(d["high"], errors="coerce").reindex(c.index).fillna(c)
        l = pd.to_numeric(d["low"], errors="coerce").reindex(c.index).fillna(c)
        last = float(c.iloc[-1])
        last_time = pd.Timestamp(d["time"].iloc[-1]) if "time" in d.columns else pd.Timestamp.now().floor("h")
        atr = max(float((h - l).abs().tail(14).mean()), last * 0.00035)
        md = q.get("master_direction", _dir(_master_regime())) if isinstance(q, dict) else _dir(_master_regime())
        sign = 1 if md == "BUY" else -1 if md == "SELL" else 0
        score = _num(q.get("quant_structure_score", 55) if isinstance(q, dict) else 55, 55) / 100.0
        after = _num(q.get("aftershock_engine", {}).get("Aftershock Risk", 0) if isinstance(q, dict) else 0, 0) / 100.0
        nsumm = news.get("summary", {}) if isinstance(news, dict) else {}
        sync = str(nsumm.get("news_sync") or nsumm.get("News Sync") or "NEUTRAL").upper()
        nudge = 0.10 if sync == "CONFIRM" else -0.08 if sync == "CONFLICT" else 0.0
        bt = st.session_state.get("dv_pp_bt_summary", {})
        err_pct = _num(bt.get("avg_abs_close_error_pct", 0) if isinstance(bt, dict) else 0, 0)
        acc = _num(bt.get("direction_accuracy_pct", 50) if isinstance(bt, dict) else 50, 50) / 100.0
        rows: List[Dict[str, Any]] = []
        for step in range(1, int(horizon) + 1):
            drift = sign * atr * math.sqrt(step) * (0.30 + score * 0.58 + max(0, acc - .50) * .35 + nudge)
            price = last + drift
            band = atr * math.sqrt(step) * (1.0 + after * .75 + min(.8, err_pct / 10.0))
            rows.append({
                "Priority Rank": step,
                "time": last_time + pd.Timedelta(hours=step),
                "Step": step,
                "Master Direction": md,
                "Reasonable Direction": md if sign else "WAIT",
                "Accuracy Adjusted Price": round(price, 5),
                "Upper Band": round(price + band, 5),
                "Lower Band": round(price - band, 5),
                "Confidence %": round(max(5, min(95, 52 + score * 32 + acc * 10 - after * 18 - min(err_pct, 2) * 4)), 1),
                "News Sync": sync,
                "BT Error %": round(err_pct, 5),
            })
        return pd.DataFrame(rows)

    def _research_rf_summary(d: pd.DataFrame) -> Dict[str, Any]:
        try:
            # Reuse already-run research first, avoiding a second calculation.
            pack = st.session_state.get("research_pack_20260612", {})
            if isinstance(pack, dict) and isinstance(pack.get("data_mining"), dict):
                rf = pack["data_mining"].get("random_forest", {})
                if isinstance(rf, dict) and rf:
                    return rf
            if not isinstance(d, pd.DataFrame) or len(d) < 160:
                return {"status": "WAIT", "message": "Need 160+ candles"}
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.metrics import accuracy_score
            c = d["close"].astype(float)
            f = pd.DataFrame({
                "ret1": c.pct_change(),
                "ret3": c.pct_change(3),
                "ret6": c.pct_change(6),
                "ma12_gap": c / c.rolling(12).mean() - 1,
                "ma48_gap": c / c.rolling(48).mean() - 1,
                "range_pct": (d["high"] - d["low"]).abs() / c.replace(0, np.nan),
                "vol24": c.pct_change().rolling(24).std(),
                "hour": pd.to_datetime(d["time"]).dt.hour,
                "target_up": causal_binary_target(c),
            })
            cols = ["ret1", "ret3", "ret6", "ma12_gap", "ma48_gap", "range_pct", "vol24", "hour"]
            f = f.dropna(subset=cols).tail(3500).reset_index(drop=True)
            train, test = purged_time_order_split(
                f, target_col="target_up", train_fraction=0.78, purge_rows=1, minimum_train=80
            )
            if train.empty or train["target_up"].nunique() < 2:
                raise ValueError("Insufficient causal labeled rows for Random Forest")
            model = RandomForestClassifier(n_estimators=80, max_depth=5, min_samples_leaf=8, random_state=42, n_jobs=1)
            model.fit(train[cols], train["target_up"].astype(int))
            pred = model.predict(test[cols]) if len(test) else []
            acc = float(accuracy_score(test["target_up"].astype(int), pred)) if len(test) else 0.0
            up = float(model.predict_proba(f[cols].tail(1))[0][1])
            rf_dir = "BUY" if up >= .55 else "SELL" if up <= .45 else "WAIT"
            master = _master_direction()
            return {"status": "READY", "Random Forest Accuracy %": round(acc * 100, 2), "RF Next 1H Up Probability %": round(up * 100, 2), "RF Direction": rf_dir, "Master Direction": master, "RF Sync": "CONFIRM" if rf_dir == master and rf_dir != "WAIT" else "CONFLICT" if rf_dir in ("BUY", "SELL") and master in ("BUY", "SELL") and rf_dir != master else "NEUTRAL"}
        except Exception as exc:
            return {"status": "OPTIONAL", "message": str(exc)[:160]}

    def _regime_nlp_history(d: pd.DataFrame, news_sync: str, master_dir: str) -> pd.DataFrame:
        if not isinstance(d, pd.DataFrame) or d.empty:
            return pd.DataFrame()
        x = d.tail(25 * 24).copy()
        x["hour"] = pd.to_datetime(x["time"]).dt.hour
        x = x[(x["hour"] >= 1) & (x["hour"] <= 14)].copy().reset_index(drop=True)
        if x.empty:
            return pd.DataFrame()
        c = x["close"].astype(float)
        ma12 = c.rolling(12, min_periods=3).mean()
        ma48 = c.rolling(48, min_periods=10).mean()
        x["Regime Direction"] = np.where(ma12 > ma48, "BUY", np.where(ma12 < ma48, "SELL", "WAIT"))
        news_table = st.session_state.get("nlp_ranked_news_df")
        joined = causal_news_asof(x[["time"]], news_table if isinstance(news_table, pd.DataFrame) else pd.DataFrame())
        sync_col = next((c for c in ("news_sync", "News Sync", "NLP Sync", "nlp_sync") if c in joined.columns), None)
        x["NLP Sync"] = joined[sync_col].reindex(x.index).fillna("UNAVAILABLE").astype(str).str.upper() if sync_col else "UNAVAILABLE"
        nlp_adjustment = np.select([x["NLP Sync"].eq("CONFIRM"), x["NLP Sync"].eq("CONFLICT")], [10, -12], default=0)
        x["Greedy Score"] = np.where(x["Regime Direction"] == master_dir, 70, 42) + nlp_adjustment
        x["Entry Opportunity"] = np.where((x["Regime Direction"] == master_dir) & (x["Greedy Score"] >= 64), "YES", "WATCH")
        out = x.tail(160).sort_values(["Greedy Score", "time"], ascending=[False, False]).head(14).copy().reset_index(drop=True)
        out["Priority Rank"] = out.index + 1
        return out[["Priority Rank", "time", "hour", "Regime Direction", "NLP Sync", "Greedy Score", "Entry Opportunity"]]

    def _priority_table(q: Dict[str, Any], news: Dict[str, Any], rf: Dict[str, Any], proj: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
        md = q.get("master_direction", _dir(_master_regime())) if isinstance(q, dict) else _dir(_master_regime())
        nsumm = news.get("summary", {}) if isinstance(news, dict) else {}
        nsync = str(nsumm.get("news_sync") or nsumm.get("News Sync") or "NEUTRAL").upper()
        qscore = _num(q.get("quant_structure_score", 50) if isinstance(q, dict) else 50, 50)
        conf = _num(proj.iloc[0].get("Confidence %"), 50) if isinstance(proj, pd.DataFrame) and not proj.empty else 50
        rows = [
            {"Priority Rank": 1, "Source": "Unified PowerBI master regime", "Greedy Score": 95 if md in ("BUY", "SELL") else 50, "Direction": md, "Decision": f"{md} master" if md in ("BUY", "SELL") else "WAIT", "Reason": _master_regime()},
            {"Priority Rank": 2, "Source": "Accuracy-adjusted projection", "Greedy Score": round(conf, 1), "Direction": md, "Decision": "USE" if conf >= 58 else "WATCH", "Reason": "Projection uses regime + error + structure + news confirmation"},
            {"Priority Rank": 3, "Source": "News/NLP conflict filter", "Greedy Score": 88 if nsync == "CONFIRM" else 55 if nsync in ("NEUTRAL", "LOW PRIORITY") else 25, "Direction": nsumm.get("news_direction") or nsumm.get("News Direction") or "WAIT", "Decision": nsync, "Reason": "News never overrides PowerBI"},
            {"Priority Rank": 4, "Source": "Quant Structure", "Greedy Score": round(qscore, 1), "Direction": md, "Decision": "CONFIRM" if qscore >= 62 else "WATCH", "Reason": "Compression/expansion + shock + microstructure"},
            {"Priority Rank": 5, "Source": "Random Forest research", "Greedy Score": _num(rf.get("Random Forest Accuracy %", 0), 0), "Direction": rf.get("RF Direction", "WAIT"), "Decision": rf.get("RF Sync", "NEUTRAL"), "Reason": "Research only; not master direction"},
        ]
        if isinstance(hist, pd.DataFrame) and not hist.empty:
            for _, r in hist.head(9).iterrows():
                rows.append({"Priority Rank": len(rows) + 1, "Source": f"Regime/NLP History H{int(r.get('hour', 0)):02d}", "Greedy Score": round(_num(r.get("Greedy Score")), 1), "Direction": r.get("Regime Direction", "WAIT"), "Decision": r.get("Entry Opportunity", "WATCH"), "Reason": f"NLP {r.get('NLP Sync','NEUTRAL')} | {r.get('time','')}"})
        return pd.DataFrame(rows).sort_values("Priority Rank", ascending=True).head(14).reset_index(drop=True)

    def _build_combined_pack(horizon: int = 24) -> Dict[str, Any]:
        d = _prep_ohlc(6000)
        regime = _master_regime()
        master_dir = _master_direction()
        q = _light_quant_structure(d, regime)
        news = _news_summary_from_existing(master_dir)
        proj = _accuracy_adjusted_projection(d, q if isinstance(q, dict) else {}, news, horizon=int(horizon))
        rf = _research_rf_summary(d)
        nsync = str((news.get("summary", {}) if isinstance(news, dict) else {}).get("news_sync") or "NEUTRAL").upper()
        hist = _regime_nlp_history(d, nsync, master_dir)
        pr = _priority_table(q if isinstance(q, dict) else {}, news, rf, proj, hist)
        bt_sum = st.session_state.get("dv_pp_bt_summary", {})
        pack = {
            "export_type": "FINAL_SYNCED_POWERBI_RESEARCH_MERGE_20260612",
            "built_at": str(pd.Timestamp.now()),
            "symbol": "EURUSD",
            "timeframe": "H1",
            "master_regime": regime,
            "master_direction": master_dir,
            "data_mining_random_forest": rf,
            "news_nlp": news,
            "quant_structure": q,
            "actual_vs_error_summary": bt_sum,
            "accuracy_adjusted_projection": proj,
            "regime_prediction_history_with_nlp": hist,
            "priority_1_to_14": pr,
            "market_story": f"PowerBI master regime is {regime}; master direction is {master_dir}. NLP is {nsync}; Quant Structure score is {q.get('quant_structure_score','-') if isinstance(q,dict) else '-'}; RF is {rf.get('RF Sync','NEUTRAL')}. Priority table is sorted ascending 1→14.",
        }
        st.session_state["final_synced_research_merge_pack_20260612"] = pack
        st.session_state["final_synced_research_merge_export_20260612"] = _json(pack, 180)
        st.session_state["final_merged_intelligence_pack_20260612"] = pack
        st.session_state["final_merged_intelligence_export_20260612"] = st.session_state["final_synced_research_merge_export_20260612"]
        st.session_state["lunch_visualization_export"] = str(st.session_state.get("lunch_visualization_export", "")) + "\n\n" + st.session_state["final_synced_research_merge_export_20260612"]
        return pack

    def _visual_spline_projection_20260614(proj: pd.DataFrame) -> pd.DataFrame:
        """Display-only smoothing for the red synced path.

        Does not change prediction tables or model outputs. It interpolates
        between existing projected points so the visual red line is less
        straight and easier to read against the older yellow path.
        """
        try:
            if not isinstance(proj, pd.DataFrame) or proj.empty or "time" not in proj.columns or "Accuracy Adjusted Price" not in proj.columns:
                return pd.DataFrame()
            p = proj[["time", "Accuracy Adjusted Price"]].copy().dropna()
            p["time"] = pd.to_datetime(p["time"], errors="coerce")
            p["Accuracy Adjusted Price"] = pd.to_numeric(p["Accuracy Adjusted Price"], errors="coerce")
            p = p.dropna().sort_values("time")
            if len(p) < 2:
                return p
            dense_rows = []
            for i in range(len(p) - 1):
                t0, t1 = p["time"].iloc[i], p["time"].iloc[i + 1]
                y0, y1 = float(p["Accuracy Adjusted Price"].iloc[i]), float(p["Accuracy Adjusted Price"].iloc[i + 1])
                for j in range(4):
                    u = j / 4.0
                    smooth = u * u * (3 - 2 * u)
                    dense_rows.append({"time": t0 + (t1 - t0) * u, "Accuracy Adjusted Price": y0 + (y1 - y0) * smooth})
            dense_rows.append({"time": p["time"].iloc[-1], "Accuracy Adjusted Price": float(p["Accuracy Adjusted Price"].iloc[-1])})
            return pd.DataFrame(dense_rows)
        except Exception:
            return proj

    def _chart_powerbi_synced(d: pd.DataFrame, base_pred: pd.DataFrame, synced_proj: pd.DataFrame, title: str) -> None:
        if not isinstance(d, pd.DataFrame) or d.empty:
            st.info("No clean EURUSD H1 data for chart.")
            return
        view = d.tail(130).copy()
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=view["time"], open=view["open"], high=view["high"], low=view["low"], close=view["close"], name="Actual candles"))
        if isinstance(base_pred, pd.DataFrame) and not base_pred.empty:
            low = {str(c).lower(): c for c in base_pred.columns}
            tcol = low.get("time") or low.get("future time") or low.get("datetime")
            ccol = low.get("close") or low.get("predicted close") or low.get("projected close")
            if tcol and ccol:
                pp = base_pred.copy()
                pp[tcol] = pd.to_datetime(pp[tcol], errors="coerce")
                fig.add_trace(go.Scatter(x=pp[tcol], y=pd.to_numeric(pp[ccol], errors="coerce"), mode="lines", name="Blue/original PowerBI path", opacity=.65, line={"color":"#2563eb", "width": 3, "shape":"spline", "smoothing":1.05}))
        if isinstance(synced_proj, pd.DataFrame) and not synced_proj.empty:
            visual_proj = _visual_spline_projection_20260614(synced_proj)
            if isinstance(visual_proj, pd.DataFrame) and not visual_proj.empty:
                fig.add_trace(go.Scatter(x=visual_proj["time"], y=visual_proj["Accuracy Adjusted Price"], mode="lines", name="RED visual-smoothed synced path", line={"color":"red", "width": 4, "shape": "spline", "smoothing": 1.15}))
            fig.add_trace(go.Scatter(x=synced_proj["time"], y=synced_proj["Accuracy Adjusted Price"], mode="markers", name="Exact synced forecast points", marker={"size": 6}))
            fig.add_trace(go.Scatter(x=synced_proj["time"], y=synced_proj["Upper Band"], mode="lines", name="Synced upper band", line={"dash": "dash"}))
            fig.add_trace(go.Scatter(x=synced_proj["time"], y=synced_proj["Lower Band"], mode="lines", name="Synced lower band", line={"dash": "dash"}))
        try:
            from core.alpha_delta_points_20260615 import add_alpha_delta_vertical_markers
            fig = add_alpha_delta_vertical_markers(fig, base_pred, synced_proj, blue_label="Blue Path", red_label="Red Path", key="powerbi_blue_red")
        except Exception:
            pass
        fig.update_layout(height=690, margin=dict(l=6, r=6, t=54, b=6), title=title + " — vertical Alpha/Delta points", xaxis_rangeslider_visible=False, legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})
        try:
            from core.alpha_delta_points_20260615 import render_alpha_delta_point_panel
            render_alpha_delta_point_panel(base_pred, synced_proj, key="powerbi_blue_red", title="PowerBI Data Point: blue path vs red path alpha/delta", blue_label="Blue Path", red_label="Red Path")
        except Exception as exc:
            st.caption(f"PowerBI alpha/delta data point skipped safely: {exc}")

    def _actual_vs_error_view() -> None:
        bt_sum = st.session_state.get("dv_pp_bt_summary", {})
        bt_hist = st.session_state.get("dv_pp_bt_hist", pd.DataFrame())
        if isinstance(bt_sum, dict) and bt_sum:
            c = st.columns(4)
            c[0].metric("Tested Candles", bt_sum.get("tested_candles", 0))
            c[1].metric("Direction Accuracy", f"{bt_sum.get('direction_accuracy_pct', 0)}%")
            c[2].metric("Avg Close Error", f"{bt_sum.get('avg_abs_close_error_pct', 0)}%")
            c[3].metric("Last Test", bt_sum.get("last_test_time", "-"))
        if isinstance(bt_hist, pd.DataFrame) and not bt_hist.empty:
            st.dataframe(bt_hist.head(220), use_container_width=True, hide_index=True, height=330)
        else:
            st.info("Run PowerBI calculation first to restore Actual vs Error projection history.")

    def _combined_merged_section() -> None:
        with st.expander("🧠 Open / Close — Final Synced Intelligence: ML Tables + KNN/Greedy + News/NLP + Quant Structure + Research", expanded=False):
            st.caption("All previous add-on sections are merged here. Priority metrics appear first; detailed tables are last. No API call runs in this combined section unless you run Research/NLP separately.")
            run_cols = st.columns([1, 1])
            horizon = run_cols[0].selectbox("Merged projection H1 steps", [6, 12, 24, 48], index=2, key=f"merged_horizon_{UNIQUE}")
            if run_cols[1].button("▶ Run Final Synced Intelligence", use_container_width=True, key=f"run_combined_{UNIQUE}"):
                with st.spinner("Syncing PowerBI, KNN/Greedy, NLP, Quant Structure, RF, and actual-error projection…"):
                    _build_combined_pack(int(horizon))
                st.success("Final synced intelligence rebuilt and Copy Full updated.")
            pack = st.session_state.get("final_synced_research_merge_pack_20260612", {}) or st.session_state.get("final_merged_intelligence_pack_20260612", {})
            if not isinstance(pack, dict) or not pack:
                st.info("Press Run Final Synced Intelligence. This section will merge the old ML tables, final merged intelligence, and research accuracy layer into one field.")
                return
            pr = pack.get("priority_1_to_14", pd.DataFrame())
            proj = pack.get("accuracy_adjusted_projection", pd.DataFrame())
            q = pack.get("quant_structure", {})
            rf = pack.get("data_mining_random_forest", {})
            nlp = pack.get("news_nlp", {}).get("summary", {}) if isinstance(pack.get("news_nlp", {}), dict) else {}
            m = st.columns(7)
            m[0].metric("Master Regime", pack.get("master_regime", "-"))
            m[1].metric("Master Dir", pack.get("master_direction", "WAIT"))
            m[2].metric("Top Priority", pr.iloc[0].get("Decision", "-") if isinstance(pr, pd.DataFrame) and not pr.empty else "-")
            m[3].metric("Projection Conf", f"{proj.iloc[0].get('Confidence %', '-') }%" if isinstance(proj, pd.DataFrame) and not proj.empty else "-")
            m[4].metric("News Sync", nlp.get("news_sync", nlp.get("News Sync", "NEUTRAL")))
            m[5].metric("Structure", q.get("quant_structure_score", "-") if isinstance(q, dict) else "-")
            m[6].metric("RF Sync", rf.get("RF Sync", "-"))
            st.info(pack.get("market_story", ""))
            tabs = st.tabs(["Priority First", "Projection", "Actual vs Error", "NLP Explain", "Research/Data Mining", "ML Tables", "Tables Last + Copy"])
            with tabs[0]:
                if isinstance(pr, pd.DataFrame) and not pr.empty:
                    st.dataframe(pr, use_container_width=True, hide_index=True, height=350)
            with tabs[1]:
                _chart_powerbi_synced(st.session_state.get("dv_pp_df", pd.DataFrame()), st.session_state.get("dv_pp_predicted", pd.DataFrame()), proj if isinstance(proj, pd.DataFrame) else pd.DataFrame(), "Synced PowerBI Projection — aligned with regime + KNN/Greedy/NLP/Structure")
                if isinstance(proj, pd.DataFrame) and not proj.empty:
                    st.dataframe(proj.head(60), use_container_width=True, hide_index=True, height=280)
            with tabs[2]:
                _actual_vs_error_view()
            with tabs[3]:
                st.markdown("#### How NLP determines direction")
                st.write("NLP uses EUR impact minus USD impact. EUR strong or USD weak supports BUY; EUR weak or USD strong supports SELL. It confirms or warns only and never overrides the Unified PowerBI direction.")
                st.json(nlp)
                ntable = pack.get("news_nlp", {}).get("table", pd.DataFrame()) if isinstance(pack.get("news_nlp", {}), dict) else pd.DataFrame()
                if isinstance(ntable, pd.DataFrame) and not ntable.empty:
                    st.dataframe(ntable, use_container_width=True, hide_index=True, height=300)
            with tabs[4]:
                st.json(rf)
                hist = pack.get("regime_prediction_history_with_nlp", pd.DataFrame())
                if isinstance(hist, pd.DataFrame) and not hist.empty:
                    st.markdown("#### Regime Prediction History + NLP — priority 1 to 14")
                    st.dataframe(hist, use_container_width=True, hide_index=True, height=320)
            with tabs[5]:
                result = st.session_state.get("dv_pp_base_result", {})
                if isinstance(result, dict):
                    for label, key in [("Prediction Ensemble Voting", "vote_df"), ("Deep AI Table", "deep_df"), ("Forecast Engine Table", "forecast_df"), ("History / Layer Table", "history")]:
                        val = result.get(key)
                        if isinstance(val, pd.DataFrame) and not val.empty:
                            st.markdown("#### " + label)
                            st.dataframe(val, use_container_width=True, hide_index=True, height=220)
            with tabs[6]:
                if isinstance(pr, pd.DataFrame) and not pr.empty:
                    st.markdown("#### Priority table last copy view")
                    st.dataframe(pr, use_container_width=True, hide_index=True, height=260)
                text = st.session_state.get("final_synced_research_merge_export_20260612") or _json(pack, 180)
                c = st.columns(2)
                with c[0]:
                    _copy_button("Copy Necessary 100 Lines", "\n".join(text.splitlines()[:100]), f"copy_100_{UNIQUE}")
                with c[1]:
                    _copy_button("Copy Full Synced Data", text, f"copy_full_{UNIQUE}")

    def _render_data_visualization_final() -> None:
        _mobile_css()
        st.markdown("### 📊 Data Visualization — One Unified PowerBI Price Projection")
        st.caption("Projection is now synced with master regime, accuracy/error history, KNN/Greedy, News/NLP, Quant Structure, and Research RF support.")
        with st.expander("⚙️ Open / Close — Projection Control Center", expanded=True):
            st.markdown('<div class="new7-pop-card">', unsafe_allow_html=True)
            c = st.columns([1.1, .75, .75, .75])
            run = c[0].button("▶ Run Synced PowerBI Projection", use_container_width=True, key=f"dv_run_{UNIQUE}")
            rows = c[1].slider("History rows", 800, 12000, int(st.session_state.get("dv_pp_rows_v6", 6000)), 400, key=f"rows_{UNIQUE}")
            horizon = c[2].slider("Future H1 candles", 6, 60, int(st.session_state.get("dv_pp_horizon_v6", 24)), 6, key=f"horizon_{UNIQUE}")
            yellow = c[3].slider("Previous-path hours", 1, 12, int(st.session_state.get("yellow_horizon_v6", 6)), 1, key=f"yellow_{UNIQUE}")
            m = st.columns(4)
            mode = m[0].selectbox("Projection mode", ["Balanced", "Trend follow", "Pullback safer"], key=f"mode_{UNIQUE}")
            risk = m[1].selectbox("Risk band", ["Low", "Medium", "High"], index=1, key=f"risk_{UNIQUE}")
            min_days = m[2].slider("Regime min days", 3, 21, int(st.session_state.get("dv_pp_min_days_v6", 5)), 1, key=f"min_days_{UNIQUE}")
            bt = m[3].slider("Actual/Error bars", 60, 360, int(st.session_state.get("dv_pp_bt_v6", 180)), 20, key=f"bt_{UNIQUE}")
            st.caption("Clean controls: run-gated, mobile-aligned, no heavy calculation on open.")
            st.markdown('</div>', unsafe_allow_html=True)
        if run:
            with st.spinner("Calculating PowerBI projection, actual-vs-error, and synced intelligence…"):
                base = _base_powerbi_run(int(rows), int(horizon), int(bt), int(min_days))
                if not base.get("ok"):
                    st.warning(base.get("message", "PowerBI run failed."))
                    return
                _build_combined_pack(int(horizon))
            st.success("PowerBI projection and merged synced data are ready.")
        if not bool(st.session_state.get("lunch_bi_visual_ready", False)):
            st.info("Press Run PowerBI + Synced Projection. No heavy calculation runs on tab open.")
            return
        d = st.session_state.get("dv_pp_df", pd.DataFrame())
        result = st.session_state.get("dv_pp_base_result", {})
        pred = st.session_state.get("dv_pp_predicted", pd.DataFrame())
        reg = st.session_state.get("dv_pp_regime_summary", {})
        bt_sum = st.session_state.get("dv_pp_bt_summary", {})
        pack = st.session_state.get("final_synced_research_merge_pack_20260612", {})
        proj = pack.get("accuracy_adjusted_projection", pd.DataFrame()) if isinstance(pack, dict) else pd.DataFrame()
        cards = st.columns(6)
        cards[0].metric("Master", f"{result.get('master_score','-')}/10" if isinstance(result, dict) else "-")
        cards[1].metric("Bull", f"{result.get('bull_probability','-')}%" if isinstance(result, dict) else "-")
        cards[2].metric("Regime", reg.get("current_regime", "-") if isinstance(reg, dict) else "-")
        cards[3].metric("Master Dir", _dir(reg.get("current_regime", "")) if isinstance(reg, dict) else "WAIT")
        cards[4].metric("BT Acc", f"{bt_sum.get('direction_accuracy_pct',0)}%" if isinstance(bt_sum, dict) else "-")
        cards[5].metric("BT Error", f"{bt_sum.get('avg_abs_close_error_pct',0)}%" if isinstance(bt_sum, dict) else "-")
        with st.expander("📈 Open / Close — Synced PowerBI Price Projection + Actual vs Error", expanded=True):
            if isinstance(proj, pd.DataFrame) and not proj.empty:
                _chart_powerbi_synced(d, pred, proj, "One Unified PowerBI Price Projection — SYNCED path")
            else:
                chart = ns.get("_render_unified_powerbi_projection_chart_v6")
                if callable(chart):
                    chart(d, pred, result, reg, horizon=int(horizon), yellow_horizon=int(yellow), mode=mode, risk_filter=risk)
                st.info("Run Final Synced Intelligence to overlay the accuracy-adjusted path.")
            with st.expander("Open / Close — Actual vs Error Projection", expanded=False):
                _actual_vs_error_view()
        _combined_merged_section()

    def _library_status_plus() -> pd.DataFrame:
        libs = [
            ("JavaScript helper", "streamlit_js_eval", "pip install streamlit-js-eval"),
            ("Polars", "polars", "pip install polars"),
            ("DuckDB", "duckdb", "pip install duckdb"),
            ("Numba", "numba", "pip install numba"),
            ("PyArrow", "pyarrow", "pip install pyarrow"),
            ("Plotly Resampler", "plotly_resampler", "pip install plotly-resampler"),
            ("Streamlit Copy Button", "streamlit_copy_button", "pip install streamlit-copy-button"),
            ("CacheTools", "cachetools", "pip install cachetools"),
            ("Scikit-learn", "sklearn", "pip install scikit-learn"),
            ("LightGBM", "lightgbm", "pip install lightgbm"),
            ("CatBoost", "catboost", "pip install catboost  # Python <=3.12 recommended"),
            ("Statsmodels", "statsmodels", "pip install statsmodels"),
            ("HMMLearn", "hmmlearn", "pip install hmmlearn  # Python <=3.12 recommended"),
            ("NLTK", "nltk", "pip install nltk"),
            ("VADER Sentiment", "vaderSentiment", "pip install vaderSentiment"),
        ]
        rows = []
        for label, mod, cmd in libs:
            try:
                module = __import__(mod)
                rows.append({"Library": label, "Import Name": mod, "Status": "READY", "Version / Note": str(getattr(module, "__version__", "installed")), "Install Command": "Already installed"})
            except Exception as exc:
                rows.append({"Library": label, "Import Name": mod, "Status": "NEED INSTALL / OPTIONAL FALLBACK ACTIVE", "Version / Note": str(exc).splitlines()[0][:90], "Install Command": cmd})
        return pd.DataFrame(rows)

    def _render_research_inner_home() -> None:
        _mobile_css()
        st.markdown("### 🎓 Research — Data Analysis / Data Mining / NLP")
        st.caption("Research moved inside Home. It uses the same Data Visualization session data and never overrides PowerBI master direction.")
        try:
            import tabs.research as research
        except Exception as exc:
            st.error("Research module could not load.")
            st.exception(exc)
            return
        c = st.columns([1, 1, 1])
        if c[0].button("▶ Run Research Pack", use_container_width=True, key=f"research_run_home_{UNIQUE}"):
            st.session_state["research_run_calculate"] = True
        if c[1].button("⏸ Stop / Lock", use_container_width=True, key=f"research_stop_home_{UNIQUE}"):
            st.session_state["research_run_calculate"] = False
        try:
            from core.finnhub_connector import connection_status
            _fh = connection_status()
            c[2].metric("Finnhub", "CONNECTED" if _fh.get("connected") else "DISCONNECTED", _fh.get("availability", "UNKNOWN"))
        except Exception:
            c[2].metric("Finnhub", "DISCONNECTED", "Manage the key in Settings/sidebar")
        st.caption("Research API inputs are intentionally hidden here. Finnhub is managed once in Settings/sidebar; no duplicate NLP key field is rendered.")
        research_tabs = st.tabs(["Data Analysis", "Data Mining", "NLP", "Library Status", "Copy"])
        selected = None
        if not bool(st.session_state.get("research_run_calculate", False)):
            st.info("Press Run Research Pack first. Library status is shown without heavy calculation.")
            st.dataframe(_library_status_plus(), use_container_width=True, hide_index=True, height=340)
            return
        if st.button("🔄 Build / Refresh Research Pack", use_container_width=True, key=f"research_build_home_{UNIQUE}") or "research_pack_20260612" not in st.session_state:
            with st.spinner("Building Research Data Analysis + Data Mining + NLP pack…"):
                try:
                    research._run_research(20, selected="Data Analysis")
                    research._run_research(20, selected="Data Mining")
                    research._run_research(20, selected="NLP")
                except Exception as exc:
                    st.error("Research pack failed safely.")
                    st.exception(exc)
        pack = st.session_state.get("research_pack_20260612", {})
        if not isinstance(pack, dict) or not pack:
            st.warning("Research pack is not ready yet.")
            return
        with research_tabs[0]:
            summ = pack.get("data_analysis", {}).get("summary", {})
            st.markdown("#### Descriptive Analysis")
            try:
                from tabs.dinner_morning_data_patch_20260614 import render_data_analysis_result_table_20260614
                render_data_analysis_result_table_20260614("home_research_data_analysis")
            except Exception as _analysis_table_exc_20260614:
                st.caption(f"Current result table skipped safely: {_analysis_table_exc_20260614}")
            if summ:
                cols = st.columns(5)
                cols[0].metric("Rows", summ.get("Rows", "-"))
                cols[1].metric("Last Close", summ.get("Last Close", "-"))
                cols[2].metric("Master Regime", summ.get("Master Regime", "-"))
                cols[3].metric("Master Dir", summ.get("Master Direction", "-"))
                cols[4].metric("H1 Vol", summ.get("H1 Volatility pips", "-"))
                st.json(summ)
            else:
                st.info(pack.get("data_analysis", {}).get("message", "No analysis yet."))
        with research_tabs[1]:
            mining = pack.get("data_mining", {})
            rf = mining.get("random_forest", {}) if isinstance(mining, dict) else {}
            cols = st.columns(4)
            cols[0].metric("RF Status", rf.get("status", "-"))
            cols[1].metric("RF Accuracy", f"{rf.get('Random Forest Accuracy %','-')}%")
            cols[2].metric("RF Direction", rf.get("RF Direction", "-"))
            cols[3].metric("RF Sync", rf.get("RF Sync", "-"))
            pr = mining.get("knn_priority", pd.DataFrame()) if isinstance(mining, dict) else pd.DataFrame()
            if isinstance(pr, pd.DataFrame) and not pr.empty:
                st.dataframe(pr, use_container_width=True, hide_index=True, height=330)
            st.json(rf)
        with research_tabs[2]:
            nlp = pack.get("nlp", {})
            summ = nlp.get("summary", {}) if isinstance(nlp, dict) else {}
            cols = st.columns(4)
            cols[0].metric("News Dir", summ.get("News Direction", summ.get("news_direction", "WAIT")))
            cols[1].metric("News Sync", summ.get("News Sync", summ.get("news_sync", "NEUTRAL")))
            cols[2].metric("Articles", summ.get("Articles Used", summ.get("articles_used", 0)))
            cols[3].metric("Master Dir", summ.get("Master Direction", _dir(_master_regime())))
            st.info("NLP direction = EUR impact - USD impact. Example: ECB/hot EU inflation supports EUR → BUY pressure; Fed/yields/geopolitical risk supports USD → SELL pressure. NLP only confirms or conflicts with PowerBI, never overrides it.")
            nt = nlp.get("table", pd.DataFrame()) if isinstance(nlp, dict) else pd.DataFrame()
            if isinstance(nt, pd.DataFrame) and not nt.empty:
                st.dataframe(nt, use_container_width=True, hide_index=True, height=280)
            hist = pack.get("regime_nlp_history", pd.DataFrame())
            if isinstance(hist, pd.DataFrame) and not hist.empty:
                st.markdown("#### Regime/NLP entry opportunity history — priority 1 to 14")
                st.dataframe(hist, use_container_width=True, hide_index=True, height=320)
            with st.expander("🧠 Open / Close — NLP Processing Pipeline", expanded=False):
                try:
                    from core.nlp_lightweight_20260615 import render_nlp_pipeline_panel
                    text_rows = []
                    if isinstance(nt, pd.DataFrame) and not nt.empty:
                        for _, r in nt.head(8).iterrows():
                            text_rows.append(str(r.get("Title", "")))
                            text_rows.append(str(r.get("Static Impact", "")))
                    sample = " ".join([x for x in text_rows if x and x != "nan"]) or _json(summ, 40)
                    render_nlp_pipeline_panel(sample, key=f"home_research_nlp_pipeline_{UNIQUE}", title="Home Research NLP: tokenization, stemming, lemmatization, stopword removal, normalization, POS, parsing, NER, WSD, coreference, extraction, topics, summary, generation")
                except Exception as exc:
                    st.caption(f"NLP pipeline skipped safely: {exc}")
        with research_tabs[3]:
            st.dataframe(_library_status_plus(), use_container_width=True, hide_index=True, height=460)
            with st.expander("Open / Close — pip install command", expanded=False):
                st.code("pip install -r requirements.txt\npip install -r requirements_research_optional.txt", language="bash")
                st.warning("CatBoost and HMMLearn may need Python 3.12 or lower. On Python 3.13 they can remain optional without crashing the app.")
        with research_tabs[4]:
            text = st.session_state.get("research_export_20260612", _json(pack, 160))
            c = st.columns(2)
            with c[0]:
                _copy_button("Copy Research Necessary 100 Lines", "\n".join(text.splitlines()[:100]), f"copy_research_100_home_{UNIQUE}")
            with c[1]:
                _copy_button("Copy Research Full", text, f"copy_research_full_home_{UNIQUE}")

    def _home_inner_selector_research() -> str:
        choices = [("Lunch", "🍱"), ("Data Visualization", "📊"), ("Research", "🎓"), ("Doo Prime", "🏦")]
        current = st.session_state.get("home_inner_tab", "Lunch")
        names = [x[0] for x in choices]
        if current not in names:
            current = "Lunch"
            st.session_state.home_inner_tab = current
        try:
            from ui.safe_tab_switch_20260615 import safe_tab_choice
            selected = safe_tab_choice(
                label="Home inner tab choice",
                options=names,
                icons=["box-seam", "bar-chart", "search", "bank"],
                state_key="home_inner_tab",
                widget_key=f"safe_home_inner_research_{UNIQUE}",
                default=current,
                horizontal=True,
                rerun_on_change=False,
            )
        except Exception:
            selected = current
            cols = st.columns(len(choices))
            for idx, (name, icon) in enumerate(choices):
                active = st.session_state.get("home_inner_tab", current) == name
                if cols[idx].button(("✅ " if active else "") + f"{icon} {name}", use_container_width=True, key=f"home_inner_{name.replace(' ','_').lower()}_{UNIQUE}"):
                    st.session_state.home_inner_tab = name
                    st.session_state["ui_navigation_click_ts"] = time.time()
                    st.session_state["fast_tab_switch_active"] = True
                    try:
                        st.rerun()
                    except Exception:
                        pass
        return st.session_state.get("home_inner_tab", selected)


    prev_lunch = ns.get("_render_metric_home_combined_inner_tab")
    prev_doo = ns.get("_render_doo_prime_inner_tab")
    footer = ns.get("render_tab_footer")

    def _dedupe_base_text(text: str) -> str:
        markers = [
            "FINAL SYNCED RESEARCH + POWERBI MERGE",
            "FINAL SYNCED DATA VISUALIZATION + RESEARCH MERGE",
            "FINAL MERGED DATA VISUALIZATION + HOME INTELLIGENCE",
            "DATA VISUALIZATION RESEARCH ACCURACY UPGRADE",
            "RESEARCH TAB EXPORT",
            "RESEARCH INNER HOME EXPORT",
        ]
        out = str(text or "")
        cut = len(out)
        for marker in markers:
            idx = out.find(marker)
            if idx >= 0:
                cut = min(cut, idx)
        return out[:cut].rstrip()

    def _top_home_copy() -> None:
        base = prev_copy() if callable(prev_copy) else ""
        base = _dedupe_base_text(base)
        extra = st.session_state.get("final_synced_research_merge_export_20260612") or st.session_state.get("final_merged_intelligence_export_20260612") or "Final synced research merge not run yet."
        research = st.session_state.get("research_export_20260612") or "Research pack not run yet."
        full = str(base) + "\n\nFINAL SYNCED DATA VISUALIZATION + RESEARCH MERGE\n" + "=" * 78 + "\n" + str(extra) + "\n\nHOME-INNER RESEARCH EXPORT\n" + "=" * 78 + "\n" + str(research)
        compact = "\n".join(full.splitlines()[:100])
        _copy_button("📋 Copy Full Home H1 — includes current synced data", full, f"home_top_copy_full_{UNIQUE}")

    def _show_home_research() -> None:
        try:
            from core.streamlit_safe_dataframe import install_safe_dataframe_patch
            install_safe_dataframe_patch()
        except Exception:
            pass
        try:
            from core.styles import request_close_sidebar
            request_close_sidebar()
        except Exception:
            pass
        _mobile_css()
        selected = _home_inner_selector_research()
        _top_home_copy()
        if selected == "Lunch":
            if callable(prev_lunch):
                prev_lunch()
        elif selected == "Data Visualization":
            _render_data_visualization_final()
        elif selected == "Research":
            _render_research_inner_home()
        else:
            if callable(prev_doo):
                prev_doo()
        if callable(footer):
            try:
                footer("Lunch")
            except Exception:
                pass

    # Override final render/copy hooks after all earlier patches.
    prev_copy = ns.get("_build_lunch_all_copy_text")

    def _copy_all_final() -> str:
        base = prev_copy() if callable(prev_copy) else ""
        base = _dedupe_base_text(base)
        merged = st.session_state.get("final_synced_research_merge_export_20260612") or st.session_state.get("final_merged_intelligence_export_20260612") or "Final synced intelligence not run yet."
        research = st.session_state.get("research_export_20260612") or "Research pack not run yet."
        return str(base) + "\n\nFINAL SYNCED RESEARCH + POWERBI MERGE 2026-06-12\n" + "=" * 78 + "\n" + str(merged) + "\n\nRESEARCH INNER HOME EXPORT\n" + "=" * 78 + "\n" + str(research)

    ns["_render_lunch_data_visualization_inner_tab"] = _render_data_visualization_final
    ns["_render_final_synced_intelligence_inner_20260612"] = _combined_merged_section
    ns["_render_home_research_inner_20260612"] = _render_research_inner_home
    ns["_build_lunch_all_copy_text"] = _copy_all_final
    ns["show"] = _show_home_research
