"""2026-06-02 Finder/Home sync patch.

Non-destructive runtime patch:
- Finder selected-hour reversal uses context candles: before window + selected hour + after window.
- Finder and Home use the same 10-point engine/threshold renderer.
- Reversal threshold dataframes are Arrow-safe for Streamlit/PyArrow.
- Pandas H frequency warnings are avoided in patched helpers.
"""

from __future__ import annotations


def install(g: dict) -> None:
    import pandas as pd
    import streamlit as st

    _safe_num = g.get("_safe_num", lambda v, default=0.0: default)
    _normalize_local = g.get("_normalize_local")
    _market_from_df = g.get("_market_from_df")
    _finder_context_market = g.get("_finder_context_market")
    _finder_market_snapshot = g.get("_finder_market_snapshot")
    _finder_actual_interval_minutes = g.get("_finder_actual_interval_minutes")
    _evaluate_reversal_driver_from_values = g.get("_evaluate_reversal_driver_from_values")
    _reversal_status = g.get("_reversal_status")
    _copy_button_html = g.get("_copy_button_html")

    def _arrow_safe(df):
        """Make mixed object columns safe for st.dataframe/pyarrow."""
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame() if df is None else df
        out = df.copy()
        for c in out.columns:
            if out[c].dtype == "object":
                # Mixed strings like '58.3%→46.7%' inside mostly numeric columns trigger ArrowInvalid.
                out[c] = out[c].map(lambda x: "" if pd.isna(x) else str(x))
        return out

    def _window_size(label, context_g):
        try:
            interval = _finder_actual_interval_minutes(context_g) if callable(_finder_actual_interval_minutes) else "unknown"
        except Exception:
            interval = "unknown"
        label_u = str(label or "").upper()
        if interval == "M1-like" or "M1" in label_u:
            return 60
        if interval == "H1-like" or "H1" in label_u:
            return 12
        return 60

    def _patched_finder_filtered_results(data, target_start, target_end):
        """Build selected-hour rows but calculate metrics from before+selected+after context."""
        if data is None or not isinstance(data, pd.DataFrame) or data.empty:
            return {}, pd.DataFrame()
        if not callable(_normalize_local):
            return {}, pd.DataFrame()
        d = data.copy()
        d["time"] = pd.to_datetime(d.get("time"), errors="coerce")
        d = d.dropna(subset=["time"]).sort_values("time")
        found = d[(d["time"] >= target_start) & (d["time"] < target_end)].copy()
        if found.empty:
            return {}, found

        results = {}
        group_col = "source_frame" if "source_frame" in d.columns else None
        names = found[group_col].dropna().astype(str).unique().tolist() if group_col else ["Finder selected period"]
        for idx, name in enumerate(names):
            selected_g = found[found[group_col].astype(str) == str(name)].copy() if group_col else found.copy()
            full_g = d[d[group_col].astype(str) == str(name)].copy() if group_col else d.copy()
            selected_g = _normalize_local(selected_g)
            full_g = _normalize_local(full_g)
            if selected_g.empty or full_g.empty:
                continue

            # The key fix: use enough candles before AND after selected hour.
            # selected hour remains exact for copy/preview; context drives metrics/reversal.
            interval = _finder_actual_interval_minutes(full_g) if callable(_finder_actual_interval_minutes) else "unknown"
            if interval == "H1-like" or "H1" in str(name).upper():
                pre_n, post_n = 72, 72
            else:
                pre_n, post_n = 360, 360
            pre_context = full_g[full_g["time"] < target_start].tail(pre_n)
            selected_context = full_g[(full_g["time"] >= target_start) & (full_g["time"] < target_end)]
            post_context = full_g[full_g["time"] >= target_end].head(post_n)
            context_g = pd.concat([pre_context, selected_context, post_context], ignore_index=True, sort=False)
            context_g = _normalize_local(context_g).sort_values("time").reset_index(drop=True)
            if context_g.empty:
                context_g = selected_g.copy()

            market, frame = ({}, pd.DataFrame())
            if callable(_market_from_df):
                try:
                    market, frame = _market_from_df(context_g)
                except Exception:
                    market, frame = {}, pd.DataFrame()
            if callable(_finder_context_market):
                try:
                    robust = _finder_context_market(context_g, selected_g)
                    if robust:
                        market = {**(market or {}), **robust}
                except Exception:
                    pass
            key = f"finder_sync_{idx}_{abs(hash(str(name))) % 100000}"
            results[key] = {
                "label": str(name),
                "ok": bool(market),
                "source": "FINDER_HOME_SYNC_CONTEXT",
                "message": f"Selected hour uses exact selected rows plus {len(pre_context)} before and {len(post_context)} after candles; same 10-point engine as Home.",
                "rows": int(len(selected_g)),
                "context_rows": int(len(context_g)),
                "timeframe": "Finder",
                "bars": int(len(selected_g)),
                "market": market or {},
                "frame": frame if isinstance(frame, pd.DataFrame) else pd.DataFrame(),
                "candles": selected_g.copy(),
                "context_candles": context_g.copy(),
                "fetched_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                "partial": False,
                "quality": "HOME-SYNC CONTEXT REPLAY" if market else "NO DATA",
            }
        return results, found

    def _patched_finder_reversal_detector(results, target_start, target_end):
        rows = []
        if not callable(_normalize_local) or not callable(_finder_market_snapshot):
            return pd.DataFrame()
        for key, res in (results or {}).items():
            label = res.get("label", key)
            context = res.get("context_candles")
            if not isinstance(context, pd.DataFrame) or context.empty:
                continue
            context = _normalize_local(context).sort_values("time").reset_index(drop=True)
            win = _window_size(label, context)
            before = context[context["time"] < target_start].tail(win)
            # include selected shock hour first, then post candles. This detects 16:00 -> 17:00 type capitulation/rebound.
            after = context[context["time"] >= target_start].head(win)
            if before.empty or after.empty:
                continue
            b = _finder_market_snapshot(before)
            a = _finder_market_snapshot(after)
            metrics = ["move_%", "dve_%", "rising_eff_%", "falling_eff_%", "fat_tail_z", "kurtosis", "trust_%", "buy_%", "sell_%"]
            delta = {m: round(_safe_num(a.get(m)) - _safe_num(b.get(m)), 5) for m in metrics}
            engine = _evaluate_reversal_driver_from_values(b, a) if callable(_evaluate_reversal_driver_from_values) else {}
            strength = _safe_num((engine or {}).get("weighted_score"), 0.0)
            causes = []
            for drv in (engine or {}).get("drivers", []):
                if str(drv.get("triggered", "")).upper() in ["YES", "WATCH"]:
                    causes.append(str(drv.get("driver", "")))
            if not causes:
                causes = ["No strong reversal cause detected"]
            rows.append({
                "frame": str(label),
                "actual_interval": _finder_actual_interval_minutes(context) if callable(_finder_actual_interval_minutes) else "unknown",
                "pre_rows": int(len(before)),
                "post_rows": int(len(after)),
                "before_move_%": b.get("move_%", 0), "after_move_%": a.get("move_%", 0), "delta_move_%": delta["move_%"],
                "before_dve_%": b.get("dve_%", 0), "after_dve_%": a.get("dve_%", 0), "delta_dve_%": delta["dve_%"],
                "before_rising_eff_%": b.get("rising_eff_%", 0), "after_rising_eff_%": a.get("rising_eff_%", 0), "delta_rising_eff_%": delta["rising_eff_%"],
                "before_falling_eff_%": b.get("falling_eff_%", 0), "after_falling_eff_%": a.get("falling_eff_%", 0), "delta_falling_eff_%": delta["falling_eff_%"],
                "before_fat_tail_z": b.get("fat_tail_z", 0), "after_fat_tail_z": a.get("fat_tail_z", 0), "delta_fat_tail_z": delta["fat_tail_z"],
                "before_kurtosis": b.get("kurtosis", 0), "after_kurtosis": a.get("kurtosis", 0), "delta_kurtosis": delta["kurtosis"],
                "before_trust_%": b.get("trust_%", 0), "after_trust_%": a.get("trust_%", 0), "delta_trust_%": delta["trust_%"],
                "before_buy_%": b.get("buy_%", 0), "after_buy_%": a.get("buy_%", 0),
                "before_sell_%": b.get("sell_%", 0), "after_sell_%": a.get("sell_%", 0),
                "reversal_strength": round(strength, 2),
                "active_10_count": int((engine or {}).get("active_count", 0)),
                "cause": " | ".join([c for c in causes if c]),
            })
        return pd.DataFrame(rows)

    def _patched_render_reversal_engine_panel(engine, location="Finder"):
        if not engine:
            st.info("No 10-point reversal engine data yet. Need candles before and after selected time.")
            return
        count = int(engine.get("active_count", 0) or 0)
        prob = int(engine.get("probability_pct", count * 10) or 0)
        score = _safe_num(engine.get("weighted_score"), 0.0)
        status, title, _ = _reversal_status(count) if callable(_reversal_status) else ("NORMAL", "NORMAL", "")
        if count >= 7:
            st.markdown(f'<div class="qx-finder-toast">🚨 {title} — {count}/10 active — {prob}% probability — score {score}/100</div>', unsafe_allow_html=True)
        elif count >= 5:
            st.warning(f"{title}: {count}/10 active | {prob}% probability | score {score}/100")
        else:
            st.success(f"{title}: {count}/10 active | {prob}% probability | score {score}/100")
        cards = st.columns(5)
        for i, row in enumerate(engine.get("drivers", [])):
            with cards[i % 5]:
                yes = str(row.get("triggered", "NO")).upper()
                badge = "YES" if yes == "YES" else ("WATCH" if yes == "WATCH" else "NO")
                st.metric(f"#{row.get('rank', i+1)} {str(row.get('driver',''))[:15]}", str(row.get("value_or_change", ""))[:22], badge)
        with st.expander(f"Open {location} reversal threshold table", expanded=False):
            st.dataframe(_arrow_safe(pd.DataFrame(engine.get("drivers", []))), use_container_width=True, hide_index=True)

    def _patched_resample_h1(df):
        base = _normalize_local(df) if callable(_normalize_local) else pd.DataFrame()
        if base.empty:
            return pd.DataFrame()
        try:
            out = (base.set_index("time").resample("1h", label="right", closed="right")
                   .agg({"open":"first", "high":"max", "low":"min", "close":"last", "volume":"sum"})
                   .dropna().reset_index())
            return _normalize_local(out)
        except Exception:
            return pd.DataFrame()

    g["_finder_filtered_results"] = _patched_finder_filtered_results
    g["_finder_reversal_detector"] = _patched_finder_reversal_detector
    g["_render_reversal_engine_panel"] = _patched_render_reversal_engine_panel
    g["_resample_h1"] = _patched_resample_h1
    g["_arrow_safe_dataframe"] = _arrow_safe
