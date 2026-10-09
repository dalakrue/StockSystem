"""2026-06-12 Data Visualization Quant Structure Intelligence upgrade.

Additive, run-gated, lightweight EURUSD structure layer. It uses existing OHLC /
PowerBI session data only. It does not add FFT, wavelet, GPU, or heavy models.
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

    UNIQUE = "20260612_qstruct"

    def _num(v: Any, default: float = 0.0) -> float:
        try:
            x = float(v)
            return x if math.isfinite(x) else float(default)
        except Exception:
            return float(default)

    def _safe(obj: Any, rows: int = 120) -> Any:
        try:
            if isinstance(obj, pd.DataFrame):
                return obj.head(int(rows)).to_dict("records")
            if isinstance(obj, pd.Series):
                return obj.to_dict()
            if isinstance(obj, pd.Timestamp):
                return str(obj)
            if isinstance(obj, dict):
                return {str(k): _safe(v, rows=rows) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_safe(x, rows=rows) for x in list(obj)[:rows]]
            if isinstance(obj, (np.integer, np.floating)):
                return obj.item()
            return obj
        except Exception:
            return str(obj)

    def _json_text(payload: Dict[str, Any]) -> str:
        return json.dumps(_safe(payload), indent=2, ensure_ascii=False, default=str)

    def _prepare_ohlc(limit: int = 2400) -> pd.DataFrame:
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
        low = {str(c).strip().lower(): c for c in d.columns}
        rename = {}
        for old, new in {"datetime": "time", "date": "time", "timestamp": "time", "o": "open", "h": "high", "l": "low", "c": "close"}.items():
            if old in low and new not in d.columns:
                rename[low[old]] = new
        if rename:
            d = d.rename(columns=rename)
        if "close" not in d.columns:
            return pd.DataFrame()
        if "time" not in d.columns:
            d["time"] = pd.date_range(end=pd.Timestamp.now().floor("h"), periods=len(d), freq="h")
        d["time"] = pd.to_datetime(d["time"], errors="coerce")
        for c in ["open", "high", "low", "close", "volume"]:
            if c in d.columns:
                d[c] = pd.to_numeric(d[c], errors="coerce")
        if "open" not in d.columns:
            d["open"] = d["close"].shift(1).fillna(d["close"])
        if "high" not in d.columns:
            d["high"] = d[["open", "close"]].max(axis=1)
        if "low" not in d.columns:
            d["low"] = d[["open", "close"]].min(axis=1)
        return d.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)

    def _master_regime() -> str:
        for key in ["dv_pp_regime_summary", "nylo_unified_home_sync_20260612"]:
            pack = st.session_state.get(key, {})
            if isinstance(pack, dict):
                if pack.get("current_regime"):
                    return str(pack.get("current_regime"))
                summ = pack.get("summary", {}) if isinstance(pack.get("summary"), dict) else {}
                if summ.get("current_powerbi_regime"):
                    return str(summ.get("current_powerbi_regime"))
        return "RANGE_NORMAL"

    def _dir_from_regime(regime: Any) -> str:
        s = str(regime or "").upper()
        if "BEAR" in s:
            return "SELL"
        if "BULL" in s:
            return "BUY"
        return "WAIT"

    def _run_lengths(mask: pd.Series) -> int:
        n = 0
        for v in reversed(mask.fillna(False).tolist()):
            if bool(v):
                n += 1
            else:
                break
        return int(n)

    def _dominant_cycle(close: pd.Series, start: int = 6, end: int = 48) -> tuple[int, float]:
        x = pd.to_numeric(close, errors="coerce").dropna().tail(360)
        if len(x) < end + 20:
            return 0, 0.0
        z = (x - x.mean()) / (x.std() or 1.0)
        best_lag, best_corr = 0, 0.0
        for lag in range(start, min(end, len(z) // 3) + 1):
            corr = z.autocorr(lag=lag)
            if pd.notna(corr) and abs(float(corr)) > abs(best_corr):
                best_lag, best_corr = lag, float(corr)
        return int(best_lag), float(best_corr)

    def _build_quant_structure(d: pd.DataFrame) -> Dict[str, Any]:
        if not isinstance(d, pd.DataFrame) or len(d) < 80:
            return {"ok": False, "message": "Run Data Visualization / load enough EURUSD H1 candles first."}
        c = pd.to_numeric(d["close"], errors="coerce").ffill()
        o = pd.to_numeric(d["open"], errors="coerce").fillna(c.shift(1)).ffill()
        h = pd.to_numeric(d["high"], errors="coerce").fillna(pd.concat([o, c], axis=1).max(axis=1))
        l = pd.to_numeric(d["low"], errors="coerce").fillna(pd.concat([o, c], axis=1).min(axis=1))
        ret = c.pct_change().fillna(0.0)
        rng = (h - l).abs().replace(0, np.nan).ffill().fillna(c.abs() * 0.0005)
        atr12 = rng.rolling(12, min_periods=4).mean()
        atr72 = rng.rolling(72, min_periods=20).median()
        atr_ratio = (atr12 / atr72.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        compression_now = max(0.0, min(100.0, (1.25 - float(atr_ratio.iloc[-1])) / 0.75 * 100.0))
        compressed = atr_ratio < 0.82
        time_in_compression = _run_lengths(compressed)
        recent_move = abs(float(c.iloc[-1] - c.iloc[-6])) if len(c) > 8 else 0.0
        recent_atr = max(float(atr12.iloc[-1] or 0.0), abs(float(c.iloc[-1])) * 0.00025)
        expansion_probability = max(0.0, min(100.0, compression_now * 0.55 + min(45.0, recent_move / recent_atr * 13.0)))
        expansion_risk = "HIGH" if expansion_probability >= 68 else "MEDIUM" if expansion_probability >= 45 else "LOW"

        regime = _master_regime()
        master_dir = _dir_from_regime(regime)
        ma_fast = c.rolling(12, min_periods=4).mean()
        ma_slow = c.rolling(48, min_periods=16).mean()
        derived_dir = np.where(ma_fast > ma_slow, "BUY", np.where(ma_fast < ma_slow, "SELL", "WAIT"))
        changes = int(pd.Series(derived_dir).tail(72).ne(pd.Series(derived_dir).tail(72).shift()).sum())
        rotation_speed = max(0.0, min(100.0, changes / 24.0 * 100.0))
        trend_eff = abs(float(c.iloc[-1] - c.iloc[-24])) / max(float(c.diff().abs().tail(24).sum()), 1e-9) if len(c) > 30 else 0.0
        regime_strength = max(0.0, min(100.0, trend_eff * 100.0 + (18.0 if master_dir in {"BUY", "SELL"} else 0.0)))
        latest_derived = str(derived_dir[-1]) if len(derived_dir) else "WAIT"
        conflict = "LOW" if latest_derived == master_dir or master_dir == "WAIT" else "HIGH"
        regime_stability = max(0.0, min(100.0, 100.0 - rotation_speed * 0.72 - (25.0 if conflict == "HIGH" else 0.0)))

        lag_now, corr_now = _dominant_cycle(c.tail(360))
        lag_prev, corr_prev = _dominant_cycle(c.tail(720).head(360)) if len(c) >= 720 else (lag_now, corr_now)
        drift_score = min(100.0, abs(lag_now - lag_prev) * 4.0 + abs(corr_now - corr_prev) * 50.0)
        cycle_stability = max(0.0, min(100.0, abs(corr_now) * 100.0 - drift_score * 0.25))
        cycle_warning = "YES" if drift_score >= 55 else "WATCH" if drift_score >= 30 else "NO"

        vol_h1 = float(ret.tail(24).std() or 0.0) * 10000.0
        vol_h4 = float(ret.rolling(4).sum().tail(42).std() or 0.0) * 10000.0
        vol_d1 = float(ret.rolling(24).sum().tail(30).std() or 0.0) * 10000.0
        vol_drift = float((atr_ratio.tail(6).mean() - atr_ratio.tail(72).median()) * 100.0)

        roll_std = ret.rolling(72, min_periods=20).std().replace(0, np.nan)
        z = (ret.abs() / roll_std).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        shock_probability = max(0.0, min(100.0, float(z.iloc[-1]) * 28.0))
        shock_magnitude = round(float(abs(ret.iloc[-1]) * 10000.0), 2)
        shock_persistence = int((z.tail(12) > 2.0).sum())
        shock_recovery = max(0.0, min(100.0, 100.0 - shock_persistence * 14.0 - shock_probability * 0.25))
        recent_shock = "YES" if bool((z.tail(12) > 2.4).any()) else "NO"
        aftershock_risk = max(0.0, min(100.0, shock_persistence * 16.0 + float(z.tail(6).max()) * 18.0))
        stabilization = max(0.0, min(100.0, 100.0 - aftershock_risk * 0.8 - max(0.0, vol_drift) * 0.25))

        body = (c - o).abs()
        wick_noise = ((rng - body).clip(lower=0) / rng.replace(0, np.nan)).fillna(0).tail(48).mean()
        noise_level = max(0.0, min(100.0, float(wick_noise) * 100.0))
        trend_quality = max(0.0, min(100.0, trend_eff * 100.0))
        directional_efficiency = trend_quality

        structure_score = max(0.0, min(100.0, regime_stability * 0.25 + trend_quality * 0.20 + stabilization * 0.22 + (100.0 - noise_level) * 0.18 + (100.0 - min(100.0, drift_score)) * 0.15))
        next_regime_status = "Continuation likely" if regime_stability >= 62 and aftershock_risk < 55 else "Rotation watch" if regime_stability >= 42 else "Unstable / wait"
        one_h_dir = master_dir if structure_score >= 45 and conflict != "HIGH" else "WAIT" if conflict == "HIGH" else master_dir
        last = float(c.iloc[-1])
        one_h_band = max(recent_atr, last * 0.00035) * (1.0 + aftershock_risk / 180.0)
        sign = 1 if one_h_dir == "BUY" else -1 if one_h_dir == "SELL" else 0
        one_h_price = last + sign * one_h_band * min(1.0, structure_score / 100.0) * 0.55
        return {
            "ok": True,
            "master_regime": regime,
            "master_direction": master_dir,
            "quant_structure_score": round(structure_score, 1),
            "compression_expansion": {"Compression Score": round(compression_now, 1), "Expansion Probability": round(expansion_probability, 1), "Time In Compression": time_in_compression, "Expansion Risk": expansion_risk},
            "regime_vortex": {"Regime Stability": round(regime_stability, 1), "Regime Rotation Speed": round(rotation_speed, 1), "Regime Conflict": conflict, "Regime Strength": round(regime_strength, 1)},
            "cycle_drift": {"Dominant Cycle Length": lag_now, "Cycle Drift Score": round(drift_score, 1), "Cycle Stability": round(cycle_stability, 1), "Cycle Change Warning": cycle_warning},
            "volatility_waterfall": {"H1 Volatility Energy": round(vol_h1, 2), "H4 Volatility Energy": round(vol_h4, 2), "D1 Volatility Energy": round(vol_d1, 2), "Volatility Drift": round(vol_drift, 1)},
            "broadband_shock_signature": {"Shock Probability": round(shock_probability, 1), "Shock Magnitude": shock_magnitude, "Shock Persistence": shock_persistence, "Shock Recovery": round(shock_recovery, 1)},
            "aftershock_engine": {"Recent Shock": recent_shock, "Aftershock Risk": round(aftershock_risk, 1), "Stabilization Score": round(stabilization, 1)},
            "microstructure_reality": {"Noise Level": round(noise_level, 1), "Trend Quality": round(trend_quality, 1), "Directional Efficiency": round(directional_efficiency, 1)},
            "sync_outputs": {"Next 1H Reasonable Direction": one_h_dir, "Next 1H Reasonable Price": round(one_h_price, 5), "Next 1H Lower Band": round(one_h_price - one_h_band, 5), "Next 1H Upper Band": round(one_h_price + one_h_band, 5), "Next Regime Update": next_regime_status},
        }

    def _build_priority_table(q: Dict[str, Any]) -> pd.DataFrame:
        if not q.get("ok"):
            return pd.DataFrame()
        master = q.get("master_direction", "WAIT")
        ce = q.get("compression_expansion", {})
        rv = q.get("regime_vortex", {})
        cd = q.get("cycle_drift", {})
        sh = q.get("broadband_shock_signature", {})
        af = q.get("aftershock_engine", {})
        ms = q.get("microstructure_reality", {})
        base = _num(q.get("quant_structure_score"), 50)
        rows = [
            ("Compression expansion", _num(ce.get("Expansion Probability")), "Expansion risk " + str(ce.get("Expansion Risk", "-"))),
            ("Regime vortex", _num(rv.get("Regime Stability")), "Conflict " + str(rv.get("Regime Conflict", "-"))),
            ("Cycle drift", 100.0 - _num(cd.get("Cycle Drift Score")), "Cycle warning " + str(cd.get("Cycle Change Warning", "-"))),
            ("Shock / aftershock", 100.0 - max(_num(sh.get("Shock Probability")), _num(af.get("Aftershock Risk"))), "Protect after shock"),
            ("Microstructure reality", 100.0 - _num(ms.get("Noise Level")) + _num(ms.get("Trend Quality")) * 0.25, "Noise + trend quality"),
        ]
        out = []
        for i, (name, score, reason) in enumerate(rows, 1):
            greedy = max(0.0, min(100.0, score * 0.55 + base * 0.45 - i * 1.2))
            label = f"{master} allowed" if greedy >= 70 and master in {"BUY", "SELL"} else "WATCH" if greedy >= 55 else "WAIT / avoid"
            out.append({"Priority Rank": i, "Structure Component": name, "Greedy Score": round(greedy, 1), "Master Direction": master, "Prescriptive Label": label, "Reason": reason})
        return pd.DataFrame(out).sort_values("Greedy Score", ascending=False).reset_index(drop=True)

    def _build_projection(d: pd.DataFrame, q: Dict[str, Any]) -> pd.DataFrame:
        if not isinstance(d, pd.DataFrame) or d.empty or not q.get("ok"):
            return pd.DataFrame()
        c = pd.to_numeric(d["close"], errors="coerce").dropna()
        if c.empty:
            return pd.DataFrame()
        last = float(c.iloc[-1])
        rng = (pd.to_numeric(d["high"], errors="coerce") - pd.to_numeric(d["low"], errors="coerce")).abs()
        atr = max(float(rng.tail(14).mean() or 0.0), last * 0.00035)
        direction = q.get("sync_outputs", {}).get("Next 1H Reasonable Direction", q.get("master_direction", "WAIT"))
        sign = 1 if direction == "BUY" else -1 if direction == "SELL" else 0
        structure = _num(q.get("quant_structure_score"), 50) / 100.0
        after = _num(q.get("aftershock_engine", {}).get("Aftershock Risk"), 0) / 100.0
        exp = _num(q.get("compression_expansion", {}).get("Expansion Probability"), 0) / 100.0
        rows = []
        for step in range(1, 7):
            drift = sign * atr * math.sqrt(step) * (0.45 + structure * 0.45)
            band = atr * math.sqrt(step) * (1.0 + after * 0.65 + exp * 0.35)
            price = last + drift
            rows.append({"Step": step, "Quant Structure Direction": direction, "Structure Projection Close": round(price, 5), "Structure Upper Band": round(price + band, 5), "Structure Lower Band": round(price - band, 5), "Structure Confidence": round(max(5.0, min(95.0, 55.0 + structure * 35.0 - after * 18.0)), 1)})
        return pd.DataFrame(rows)

    def _update_visual_export(payload: Dict[str, Any]) -> str:
        existing = st.session_state.get("lunch_visualization_export", "")
        try:
            base = json.loads(existing) if isinstance(existing, str) and existing.strip() else existing
        except Exception:
            base = {"previous_visualization_export_text": str(existing)[:20000]}
        if not isinstance(base, dict):
            base = {"previous_visualization_export": _safe(base)}
        base["quant_structure_intelligence_20260612"] = _safe(payload)
        text = _json_text(base)
        st.session_state["lunch_visualization_export"] = text
        st.session_state["dv_quant_structure_export_text_20260612"] = _json_text(payload)
        # Keep News/NLP/KNN pack synced without overriding its own logic.
        pack = st.session_state.get("dv_news_nlp_pack_20260612")
        if isinstance(pack, dict):
            pack["quant_structure_intelligence_20260612"] = payload
            st.session_state["dv_news_nlp_pack_20260612"] = pack
        return text

    def _run_quant_structure() -> Dict[str, Any]:
        d = _prepare_ohlc(2400)
        q = _build_quant_structure(d)
        priority = _build_priority_table(q)
        projection = _build_projection(d, q)
        payload = {"export_type": "DATA_VISUALIZATION_QUANT_STRUCTURE_INTELLIGENCE_20260612", "built_at": str(pd.Timestamp.now()), "symbol": st.session_state.get("symbol", "EURUSD"), "timeframe": st.session_state.get("timeframe", "H1"), "structure": q, "quant_structure_priority": priority, "structure_projection": projection}
        st.session_state["dv_quant_structure_pack_20260612"] = payload
        _update_visual_export(payload)
        return payload

    def _copy_button(label: str, text: str, key: str) -> None:
        try:
            from core.pro_terminal_uiux import render_mobile_copy_button
            render_mobile_copy_button(label, text, key)
        except Exception:
            st.text_area(label, text, height=220, key=key + "_fallback")

    def _render_chart(proj: pd.DataFrame) -> None:
        if not isinstance(proj, pd.DataFrame) or proj.empty:
            st.info("Run Quant Structure Intelligence after Data Visualization is ready to show the structure projection path.")
            return
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=proj["Step"], y=proj["Structure Projection Close"], mode="lines+markers", name="Structure projection"))
        fig.add_trace(go.Scatter(x=proj["Step"], y=proj["Structure Upper Band"], mode="lines", name="Structure upper band"))
        fig.add_trace(go.Scatter(x=proj["Step"], y=proj["Structure Lower Band"], mode="lines", name="Structure lower band"))
        fig.update_layout(height=330, margin=dict(l=8, r=8, t=25, b=8), xaxis_title="Future step", yaxis_title="EURUSD", legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})

    def _render_quant_structure_section(location: str = "Data Visualization") -> None:
        with st.expander("🧬 Open / Close — Quant Structure Intelligence", expanded=False):
            st.caption("Run-gated. Uses existing EURUSD OHLC / PowerBI session data only. No FFT, no wavelet, no GPU, no heavy research model.")
            cols = st.columns([1, 1, 1])
            run = cols[0].button("▶ Run Quant Structure", use_container_width=True, key=f"dv_quant_structure_run_{UNIQUE}")
            cols[1].metric("Master Regime", _master_regime())
            cols[2].metric("Master Direction", _dir_from_regime(_master_regime()))
            if run:
                with st.spinner("Building lightweight quant structure intelligence from existing EURUSD data…"):
                    payload = _run_quant_structure()
                if payload.get("structure", {}).get("ok"):
                    st.success("Quant Structure Intelligence is synced and included in copy exports.")
                else:
                    st.warning(payload.get("structure", {}).get("message", "Not enough data."))
            payload = st.session_state.get("dv_quant_structure_pack_20260612", {})
            if not isinstance(payload, dict) or not payload:
                st.info("Press **Run Quant Structure**. Nothing heavy runs on page load.")
                return
            q = payload.get("structure", {}) if isinstance(payload.get("structure"), dict) else {}
            if not q.get("ok"):
                st.warning(q.get("message", "Quant structure is not ready."))
                return
            sync = q.get("sync_outputs", {})
            m = st.columns(6)
            m[0].metric("Structure Score", q.get("quant_structure_score", "-"))
            m[1].metric("Next 1H Dir", sync.get("Next 1H Reasonable Direction", "WAIT"))
            m[2].metric("Next 1H Price", sync.get("Next 1H Reasonable Price", "-"))
            m[3].metric("Expansion %", q.get("compression_expansion", {}).get("Expansion Probability", "-"))
            m[4].metric("Aftershock Risk", q.get("aftershock_engine", {}).get("Aftershock Risk", "-"))
            m[5].metric("Next Regime", sync.get("Next Regime Update", "-"))
            tabs = st.tabs(["Projection", "Engines", "Priority", "Copy"])
            with tabs[0]:
                proj = payload.get("structure_projection", pd.DataFrame())
                _render_chart(proj if isinstance(proj, pd.DataFrame) else pd.DataFrame())
                if isinstance(proj, pd.DataFrame) and not proj.empty:
                    st.dataframe(proj, use_container_width=True, hide_index=True, height=230)
            with tabs[1]:
                st.json({k: q.get(k, {}) for k in ["compression_expansion", "regime_vortex", "cycle_drift", "volatility_waterfall", "broadband_shock_signature", "aftershock_engine", "microstructure_reality", "sync_outputs"]})
            with tabs[2]:
                pr = payload.get("quant_structure_priority", pd.DataFrame())
                if isinstance(pr, pd.DataFrame) and not pr.empty:
                    st.dataframe(pr, use_container_width=True, hide_index=True, height=260)
                    c1, c2 = st.columns(2)
                    c1.metric("Best Structure Priority #1", pr.iloc[0].get("Prescriptive Label", "-"), f"Score {pr.iloc[0].get('Greedy Score','-')}")
                    if len(pr) > 1:
                        c2.metric("Best Structure Priority #2", pr.iloc[1].get("Prescriptive Label", "-"), f"Score {pr.iloc[1].get('Greedy Score','-')}")
            with tabs[3]:
                full = _update_visual_export(payload)
                compact = _json_text({"master_regime": q.get("master_regime"), "master_direction": q.get("master_direction"), "quant_structure_score": q.get("quant_structure_score"), "sync_outputs": sync, "priority_top": _safe(payload.get("quant_structure_priority", pd.DataFrame()), rows=6), "engines": {k: q.get(k, {}) for k in ["compression_expansion", "regime_vortex", "cycle_drift", "volatility_waterfall", "broadband_shock_signature", "aftershock_engine", "microstructure_reality"]}})
                cc = st.columns(2)
                with cc[0]:
                    _copy_button("Copy Quant Structure Compact", compact, f"copy_quant_structure_compact_{UNIQUE}")
                with cc[1]:
                    _copy_button("Copy Data Visualization Full + Quant Structure", full, f"copy_quant_structure_full_{UNIQUE}")

    prev_dv = ns.get("_render_lunch_data_visualization_inner_tab")

    def _render_dv_with_quant_structure() -> None:
        if callable(prev_dv):
            prev_dv()
        _render_quant_structure_section("Data Visualization")

    prev_copy = ns.get("_build_lunch_all_copy_text")

    def _build_copy_with_quant_structure() -> str:
        base = prev_copy() if callable(prev_copy) else ""
        extra = st.session_state.get("dv_quant_structure_export_text_20260612", "")
        if not extra:
            pack = st.session_state.get("dv_quant_structure_pack_20260612", {})
            extra = _json_text(pack) if isinstance(pack, dict) and pack else "Quant Structure Intelligence not run yet."
        return str(base) + "\n\nDATA VISUALIZATION QUANT STRUCTURE INTELLIGENCE 2026-06-12\n" + "=" * 72 + "\n" + str(extra)

    prev_finder = ns.get("_render_doo_finder")

    def _render_finder_with_quant_structure(results=None):
        if callable(prev_finder):
            try:
                prev_finder(results)
            except TypeError:
                prev_finder()
        try:
            with st.expander("🧬 Finder Sync — Quant Structure Intelligence", expanded=False):
                pack = st.session_state.get("dv_quant_structure_pack_20260612", {})
                if not isinstance(pack, dict) or not pack:
                    st.info("Run Data Visualization → Quant Structure first. Finder will mirror structure score, next 1H direction, and priority here.")
                    return
                q = pack.get("structure", {}) if isinstance(pack.get("structure"), dict) else {}
                sync = q.get("sync_outputs", {}) if isinstance(q.get("sync_outputs"), dict) else {}
                c = st.columns(4)
                c[0].metric("Structure Score", q.get("quant_structure_score", "-"))
                c[1].metric("Master Direction", q.get("master_direction", "WAIT"))
                c[2].metric("Next 1H", sync.get("Next 1H Reasonable Direction", "WAIT"))
                c[3].metric("Next Regime", sync.get("Next Regime Update", "-"))
                pr = pack.get("quant_structure_priority", pd.DataFrame())
                if isinstance(pr, pd.DataFrame) and not pr.empty:
                    st.dataframe(pr.head(6), use_container_width=True, hide_index=True, height=230)
        except Exception as exc:
            st.caption(f"Finder Quant Structure sync skipped safely: {exc}")

    ns["_render_lunch_data_visualization_inner_tab"] = _render_dv_with_quant_structure
    ns["_build_lunch_all_copy_text"] = _build_copy_with_quant_structure
    ns["_render_doo_finder"] = _render_finder_with_quant_structure
    ns["_render_dv_quant_structure_section_20260612"] = _render_quant_structure_section
