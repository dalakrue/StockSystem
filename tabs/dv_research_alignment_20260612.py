"""2026-06-12 Data Visualization research alignment patch.

Adds a run-gated Random Forest/regime/NLP history block under PowerBI while
keeping all prior Data Visualization sections and copy buttons intact.
"""
from __future__ import annotations


def install(ns: dict) -> None:
    import json
    import math
    from typing import Any, Dict

    import numpy as np
    import pandas as pd
    import plotly.graph_objects as go
    import streamlit as st

    from core.research_causality_20260618 import causal_binary_target, causal_news_asof, purged_time_order_split

    UNIQUE = "20260612_dvresearch"

    def _safe(obj: Any) -> Any:
        try:
            if isinstance(obj, pd.DataFrame):
                return obj.head(220).to_dict("records")
            if isinstance(obj, pd.Series):
                return obj.to_dict()
            if isinstance(obj, dict):
                return {str(k): _safe(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_safe(x) for x in list(obj)[:220]]
            return obj
        except Exception:
            return str(obj)

    def _json(obj: Any) -> str:
        return json.dumps(_safe(obj), indent=2, ensure_ascii=False, default=str)

    def _num(v: Any, default: float = 0.0) -> float:
        try:
            x = float(v)
            return x if math.isfinite(x) else float(default)
        except Exception:
            return float(default)

    def _copy(label: str, text: str, key: str) -> None:
        try:
            from streamlit_copy_button import copy_button
            copy_button(text, label, key=key)
        except Exception:
            try:
                from core.pro_terminal_uiux import render_mobile_copy_button
                render_mobile_copy_button(label, text, key)
            except Exception:
                st.text_area(label, text, height=220, key=key + "_fallback")

    def _prep(limit: int = 6000) -> pd.DataFrame:
        prep = ns.get("_dv_prepare_ohlc_v20260609")
        raw = st.session_state.get("dv_pp_df")
        if not isinstance(raw, pd.DataFrame) or raw.empty:
            raw = st.session_state.get("last_df")
        if callable(prep):
            try:
                out = prep(raw, limit=int(limit))
                if isinstance(out, pd.DataFrame) and not out.empty:
                    return out.tail(limit).reset_index(drop=True)
            except Exception:
                pass
        if not isinstance(raw, pd.DataFrame) or raw.empty:
            return pd.DataFrame()
        d = raw.copy().tail(limit).reset_index(drop=True)
        low = {str(c).lower(): c for c in d.columns}
        for src, dst in {"datetime":"time","date":"time","timestamp":"time","o":"open","h":"high","l":"low","c":"close"}.items():
            if src in low and dst not in d.columns:
                d = d.rename(columns={low[src]: dst})
        if "time" not in d.columns:
            # Synthetic timestamps are educational only and must never enter an
            # operational EURUSD H1 Research decision.
            return pd.DataFrame()
        for col in ["open", "high", "low", "close"]:
            if col not in d.columns:
                d[col] = d.get("close", np.nan)
            d[col] = pd.to_numeric(d[col], errors="coerce")
        d["time"] = pd.to_datetime(d["time"], errors="coerce")
        return d.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)

    def _master_regime() -> str:
        for key in ("dv_pp_regime_summary", "final_merged_intelligence_pack_20260612", "lunch_5layer_powerbi_result"):
            obj = st.session_state.get(key, {})
            if isinstance(obj, dict):
                cur = obj.get("current_regime") or obj.get("master_regime")
                if cur:
                    return str(cur)
        return "RANGE_NORMAL"

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

    def _features(d: pd.DataFrame) -> pd.DataFrame:
        x = d.copy()
        c = x["close"].astype(float)
        x["ret1"] = c.pct_change()
        x["ret3"] = c.pct_change(3)
        x["ret6"] = c.pct_change(6)
        x["ma12_gap"] = c / c.rolling(12).mean() - 1
        x["ma48_gap"] = c / c.rolling(48).mean() - 1
        x["range_pct"] = (x["high"] - x["low"]).abs() / c.replace(0, np.nan)
        x["vol24"] = x["ret1"].rolling(24).std()
        x["hour"] = pd.to_datetime(x["time"]).dt.hour
        x["target_up"] = causal_binary_target(c)
        feature_cols = ["ret1", "ret3", "ret6", "ma12_gap", "ma48_gap", "range_pct", "vol24", "hour"]
        return x.dropna(subset=feature_cols).reset_index(drop=True)

    def _rf_pack(d: pd.DataFrame, horizon: int = 6) -> Dict[str, Any]:
        if len(d) < 180:
            return {"ok": False, "message": "Need at least 180 H1 candles for Random Forest research upgrade."}
        f = _features(d).tail(3600)
        cols = ["ret1", "ret3", "ret6", "ma12_gap", "ma48_gap", "range_pct", "vol24", "hour"]
        train, test = purged_time_order_split(
            f, target_col="target_up", train_fraction=0.78, purge_rows=1, minimum_train=100
        )
        master_regime = _master_regime()
        master_dir = _master_direction()
        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.metrics import accuracy_score
            if train.empty or train["target_up"].nunique() < 2:
                raise ValueError("Insufficient causal labeled rows for Random Forest")
            model = RandomForestClassifier(n_estimators=90, max_depth=5, min_samples_leaf=8, random_state=42, n_jobs=1)
            model.fit(train[cols], train["target_up"].astype(int))
            pred = model.predict(test[cols]) if len(test) else []
            acc = float(accuracy_score(test["target_up"].astype(int), pred)) if len(test) else 0.0
            up = float(model.predict_proba(f[cols].tail(1))[0][1])
            rf_dir = "BUY" if up >= 0.55 else "SELL" if up <= 0.45 else "WAIT"
            sync = "CONFIRM" if rf_dir == master_dir and rf_dir != "WAIT" else "CONFLICT" if rf_dir in ("BUY", "SELL") and master_dir in ("BUY", "SELL") and rf_dir != master_dir else "NEUTRAL"
        except Exception as exc:
            acc, up, rf_dir, sync = 0.0, 0.5, "WAIT", "OPTIONAL"
            return {"ok": False, "message": str(exc)[:180], "master_regime": master_regime, "master_direction": master_dir}
        c = d["close"].astype(float)
        atr = max(float((d["high"] - d["low"]).abs().tail(14).mean()), float(c.iloc[-1]) * 0.00035)
        sign = 1 if master_dir == "BUY" else -1 if master_dir == "SELL" else 0
        rf_boost = .12 if sync == "CONFIRM" else -.08 if sync == "CONFLICT" else 0.0
        rows = []
        last = float(c.iloc[-1])
        for step in range(1, int(horizon) + 1):
            raw = last + sign * atr * math.sqrt(step) * (0.42 + acc * 0.35 + rf_boost)
            band = atr * math.sqrt(step) * (1.05 + (0.5 - abs(up - .5)) * .7)
            rows.append({"Step": step, "Priority Rank": step, "Master Direction": master_dir, "RF Direction": rf_dir, "RF Sync": sync, "Accuracy Adjusted Price": round(raw, 5), "Upper Band": round(raw + band, 5), "Lower Band": round(raw - band, 5), "RF Confidence %": round(max(5, min(95, 50 + abs(up - .5) * 90 + acc * 18)), 1)})
        return {"ok": True, "master_regime": master_regime, "master_direction": master_dir, "rf_accuracy_pct": round(acc * 100, 2), "rf_up_probability_pct": round(up * 100, 2), "rf_direction": rf_dir, "rf_sync": sync, "projection": pd.DataFrame(rows)}

    def _regime_nlp_history(d: pd.DataFrame) -> pd.DataFrame:
        if d.empty:
            return pd.DataFrame()
        master = _master_direction()
        x = d.tail(25 * 24).copy()
        x["hour"] = pd.to_datetime(x["time"]).dt.hour
        x = x[(x["hour"] >= 1) & (x["hour"] <= 14)].copy().reset_index(drop=True)
        if x.empty:
            return pd.DataFrame()
        c = x["close"].astype(float)
        x["ma12"] = c.rolling(12, min_periods=3).mean()
        x["ma48"] = c.rolling(48, min_periods=10).mean()
        x["Regime Direction"] = np.where(x["ma12"] > x["ma48"], "BUY", np.where(x["ma12"] < x["ma48"], "SELL", "WAIT"))
        news_table = st.session_state.get("nlp_ranked_news_df")
        joined = causal_news_asof(x[["time"]], news_table if isinstance(news_table, pd.DataFrame) else pd.DataFrame())
        sync_col = next((c for c in ("news_sync", "News Sync", "NLP Sync", "nlp_sync") if c in joined.columns), None)
        x["NLP Sync"] = joined[sync_col].reindex(x.index).fillna("UNAVAILABLE").astype(str).str.upper() if sync_col else "UNAVAILABLE"
        nlp_adjustment = np.select([x["NLP Sync"].eq("CONFIRM"), x["NLP Sync"].eq("CONFLICT")], [10, -12], default=0)
        x["Greedy Score"] = np.where(x["Regime Direction"] == master, 70, 42) + nlp_adjustment
        x["Entry Opportunity"] = np.where((x["Regime Direction"] == master) & (x["Greedy Score"] >= 64), "YES", "WATCH")
        out = x.tail(140).sort_values(["Greedy Score", "time"], ascending=[False, False]).head(14).copy().reset_index(drop=True)
        out["Priority Rank"] = out.index + 1
        return out[["Priority Rank", "time", "hour", "Regime Direction", "NLP Sync", "Greedy Score", "Entry Opportunity"]]

    def _priority_table(rf: Dict[str, Any], hist: pd.DataFrame) -> pd.DataFrame:
        rows = []
        md = rf.get("master_direction", _dir(_master_regime()))
        rows.append({"Priority Rank": 1, "Research Source": "Unified PowerBI Regime", "Greedy Score": 95 if md in ("BUY", "SELL") else 50, "Direction": md, "Decision": f"{md} master" if md in ("BUY", "SELL") else "WAIT", "Reason": rf.get("master_regime", _master_regime())})
        rows.append({"Priority Rank": 2, "Research Source": "Random Forest Accuracy", "Greedy Score": _num(rf.get("rf_accuracy_pct"), 0), "Direction": rf.get("rf_direction", "WAIT"), "Decision": rf.get("rf_sync", "NEUTRAL"), "Reason": "RF supports only; it never overrides PowerBI."})
        if isinstance(hist, pd.DataFrame) and not hist.empty:
            for _, r in hist.head(12).iterrows():
                rows.append({"Priority Rank": int(len(rows) + 1), "Research Source": f"Regime/NLP hour {int(r.get('hour', 0))}", "Greedy Score": round(_num(r.get("Greedy Score")), 1), "Direction": r.get("Regime Direction", "WAIT"), "Decision": r.get("Entry Opportunity", "WATCH"), "Reason": f"NLP {r.get('NLP Sync', 'NEUTRAL')} | {r.get('time', '')}"})
        return pd.DataFrame(rows).sort_values(["Priority Rank"], ascending=True).head(14).reset_index(drop=True)

    def _run(horizon: int) -> Dict[str, Any]:
        d = _prep(6000)
        rf = _rf_pack(d, int(horizon))
        hist = _regime_nlp_history(d)
        pr = _priority_table(rf, hist)
        payload = {"export_type": "DV_RESEARCH_RANDOM_FOREST_REGIME_NLP_20260612", "built_at": str(pd.Timestamp.now()), "symbol": "EURUSD", "timeframe": "H1", "random_forest_powerbi_alignment": rf, "regime_prediction_history_with_nlp": hist, "research_priority_1_to_14": pr}
        text = _json(payload)
        st.session_state["dv_research_alignment_pack_20260612"] = payload
        st.session_state["dv_research_alignment_export_20260612"] = text
        st.session_state["lunch_visualization_export"] = str(st.session_state.get("lunch_visualization_export", "")) + "\n\n" + text
        return payload

    def _chart(df: pd.DataFrame) -> None:
        if not isinstance(df, pd.DataFrame) or df.empty:
            st.info("Run Research Accuracy Upgrade first.")
            return
        fig = go.Figure()
        x = df["Step"] if "Step" in df.columns else df.index + 1
        fig.add_trace(go.Scatter(x=x, y=df["Accuracy Adjusted Price"], mode="lines+markers", name="RF + regime aligned path"))
        fig.add_trace(go.Scatter(x=x, y=df["Upper Band"], mode="lines", name="Upper band"))
        fig.add_trace(go.Scatter(x=x, y=df["Lower Band"], mode="lines", name="Lower band"))
        fig.update_layout(height=330, margin=dict(l=6, r=6, t=28, b=6), xaxis_title="Next H1 step", yaxis_title="EURUSD")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})

    def _render() -> None:
        with st.expander("🎓 Open / Close — Research Accuracy Upgrade: Random Forest + Regime/NLP History", expanded=False):
            st.caption("Run-gated research layer for Data Visualization. Random Forest and NLP history support the PowerBI projection, but do not override the master regime.")
            c = st.columns([1, 1, 1])
            horizon = c[0].selectbox("Projection H1 steps", [6, 12, 24], index=0, key=f"horizon_{UNIQUE}")
            if c[1].button("▶ Run Research Accuracy Upgrade", use_container_width=True, key=f"run_{UNIQUE}"):
                with st.spinner("Building Random Forest + regime/NLP history research layer…"):
                    _run(int(horizon))
                st.success("Research accuracy layer synced. Copy exports updated.")
            if c[2].button("🔄 Clear Research Cache", use_container_width=True, key=f"clear_{UNIQUE}"):
                st.session_state.pop("dv_research_alignment_pack_20260612", None)
                st.session_state.pop("dv_research_alignment_export_20260612", None)
                st.rerun()
            pack = st.session_state.get("dv_research_alignment_pack_20260612", {})
            if not isinstance(pack, dict) or not pack:
                st.info("Press Run Research Accuracy Upgrade. Nothing runs on page load.")
                return
            rf = pack.get("random_forest_powerbi_alignment", {})
            hist = pack.get("regime_prediction_history_with_nlp", pd.DataFrame())
            pr = pack.get("research_priority_1_to_14", pd.DataFrame())
            m = st.columns(5)
            m[0].metric("Master Regime", rf.get("master_regime", "-"))
            m[1].metric("Master Dir", rf.get("master_direction", "WAIT"))
            m[2].metric("RF Acc", f"{rf.get('rf_accuracy_pct', '-') }%")
            m[3].metric("RF Sync", rf.get("rf_sync", "-"))
            m[4].metric("Top Priority", pr.iloc[0].get("Decision", "-") if isinstance(pr, pd.DataFrame) and not pr.empty else "-")
            t = st.tabs(["Projection", "Priority 1-14", "Regime + NLP History", "Copy"])
            with t[0]:
                proj = rf.get("projection", pd.DataFrame()) if isinstance(rf, dict) else pd.DataFrame()
                _chart(proj)
                if isinstance(proj, pd.DataFrame) and not proj.empty:
                    st.dataframe(proj, use_container_width=True, hide_index=True, height=260)
            with t[1]:
                if isinstance(pr, pd.DataFrame) and not pr.empty:
                    st.dataframe(pr, use_container_width=True, hide_index=True, height=330)
            with t[2]:
                if isinstance(hist, pd.DataFrame) and not hist.empty:
                    st.dataframe(hist, use_container_width=True, hide_index=True, height=330)
            with t[3]:
                text = st.session_state.get("dv_research_alignment_export_20260612", _json(pack))
                _copy("Copy Research Accuracy Compact 100 Lines", "\n".join(text.splitlines()[:100]), f"copy_compact_{UNIQUE}")
                _copy("Copy Research Accuracy Full", text, f"copy_full_{UNIQUE}")

    prev_dv = ns.get("_render_lunch_data_visualization_inner_tab")
    def _dv_with_research() -> None:
        if callable(prev_dv):
            prev_dv()
        _render()

    prev_copy = ns.get("_build_lunch_all_copy_text")
    def _copy_with_research() -> str:
        base = prev_copy() if callable(prev_copy) else ""
        extra = st.session_state.get("dv_research_alignment_export_20260612") or "DV research accuracy upgrade not run yet."
        research = st.session_state.get("research_export_20260612") or "Research tab pack not run yet."
        return str(base) + "\n\nDATA VISUALIZATION RESEARCH ACCURACY UPGRADE 2026-06-12\n" + "="*78 + "\n" + str(extra) + "\n\nRESEARCH TAB EXPORT 2026-06-12\n" + "="*78 + "\n" + str(research)

    ns["_render_lunch_data_visualization_inner_tab"] = _dv_with_research
    ns["_build_lunch_all_copy_text"] = _copy_with_research
    ns["_render_dv_research_alignment_20260612"] = _render
