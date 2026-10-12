"""2026-06-03 Home/Finder reversal history upgrade.

Adds:
- Home 25D scan as an open/close field with a full hourly history table.
- Finder day-only selection: no hour box, no full-hour choosing box.
- Finder shows every 7/10+ 10-point reversal decision for the selected day,
  plus the complete hourly scan and driver table for the strongest hour.

This is a non-destructive runtime patch. Original functions remain in the zip;
this module only wraps/overrides UI rendering after the legacy module loads.
"""
from __future__ import annotations


def install(g: dict) -> None:
    import math
    import pandas as pd
    import streamlit as st

    _safe_num = g.get("_safe_num", lambda v, default=0.0: default)
    _normalize_local = g.get("_normalize_local")
    _finder_market_snapshot = g.get("_finder_market_snapshot")
    _evaluate_reversal_driver_from_values = g.get("_evaluate_reversal_driver_from_values")
    _reversal_pair_for_target = g.get("_reversal_pair_for_target")
    _loaded_reversal_history_df = g.get("_loaded_reversal_history_df")
    _render_reversal_engine_panel = g.get("_render_reversal_engine_panel")
    _format_reversal_period_label = g.get("_format_reversal_period_label", lambda ts: str(ts))
    _collect_doo_model_candles = g.get("_collect_doo_model_candles")
    _add_simple_model_features = g.get("_add_simple_model_features")
    _finder_metric_table = g.get("_finder_metric_table")
    _finder_filtered_results = g.get("_finder_filtered_results")
    _finder_duplicate_frame_warning = g.get("_finder_duplicate_frame_warning")
    _copy_button_html = g.get("_copy_button_html")
    _positions_df_from_account = g.get("_positions_df_from_account")
    _render_finder_basket_model = g.get("_render_finder_basket_model")

    def _num(v, default=0.0):
        try:
            x = float(v)
            if math.isnan(x) or math.isinf(x):
                return default
            return x
        except Exception:
            try:
                return float(_safe_num(v, default))
            except Exception:
                return default

    def _engine_for_hour(data, hour_ts):
        if not callable(_reversal_pair_for_target) or not callable(_finder_market_snapshot) or not callable(_evaluate_reversal_driver_from_values):
            return None
        pre, post, mode = _reversal_pair_for_target(data, pd.Timestamp(hour_ts))
        if len(pre) < 2 or len(post) < 2:
            return None
        eng = _evaluate_reversal_driver_from_values(_finder_market_snapshot(pre), _finder_market_snapshot(post))
        h = pd.Timestamp(hour_ts).floor("h")
        eng["period_label"] = _format_reversal_period_label(h)
        eng["period_time"] = h.strftime("%Y-%m-%d %H:%M")
        eng["period_day"] = h.strftime("%A")
        eng["scan_mode"] = mode
        eng["pre_rows"] = int(len(pre))
        eng["post_rows"] = int(len(post))
        eng["is_exact_threshold_match"] = int(eng.get("active_count", 0)) >= 7
        return eng

    def _scan_reversal_history_table(df=None, days=25, selected_date=None):
        if selected_date is None:
            data = _loaded_reversal_history_df(df=df, days=days) if callable(_loaded_reversal_history_df) else pd.DataFrame()
        else:
            data = df
            if callable(_normalize_local):
                data = _normalize_local(data).dropna(subset=["time", "close"]).sort_values("time").reset_index(drop=True)
        if not isinstance(data, pd.DataFrame) or data.empty or "time" not in data.columns:
            return pd.DataFrame(), []
        data = data.copy()
        data["time"] = pd.to_datetime(data["time"], errors="coerce")
        data = data.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
        if data.empty:
            return pd.DataFrame(), []
        max_t = data["time"].max()
        latest_completed = pd.Timestamp(max_t).floor("h")
        if pd.Timestamp(max_t) < latest_completed + pd.Timedelta(minutes=20):
            latest_completed -= pd.Timedelta(hours=1)
        if selected_date is not None:
            start = pd.Timestamp(selected_date).normalize()
            hours = [start + pd.Timedelta(hours=i) for i in range(24)]
            hours = [h for h in hours if h <= latest_completed and ((data["time"] >= h) & (data["time"] < h + pd.Timedelta(hours=1))).any()]
        else:
            hours = data["time"].dt.floor("h").drop_duplicates().sort_values().tolist()
            hours = [pd.Timestamp(h) for h in hours if pd.Timestamp(h) <= latest_completed]
        rows, engines = [], []
        for h in hours:
            eng = _engine_for_hour(data, h)
            if not eng:
                continue
            drivers_yes = [str(r.get("driver")) for r in eng.get("drivers", []) if str(r.get("triggered", "")).upper() == "YES"]
            d = eng.get("deltas", {}) or {}
            rows.append({
                "date": pd.Timestamp(h).strftime("%Y-%m-%d"),
                "day": pd.Timestamp(h).strftime("%A"),
                "hour": pd.Timestamp(h).strftime("%H:00"),
                "10_reverse_decision": f"{int(eng.get('active_count', 0))}/10",
                "raw_drivers": f"{int(eng.get('raw_active_count', eng.get('active_count', 0)))}/10",
                "probability_%": int(eng.get("probability_pct", 0)),
                "weighted_score": round(_num(eng.get("weighted_score")), 2),
                "status": eng.get("status", "NORMAL"),
                "7_out_of_10_found": "YES" if int(eng.get("active_count", 0)) >= 7 else "NO",
                "confirmed_reversal": bool(eng.get("confirmed_reversal", False)),
                "strict_gate_valid": bool(eng.get("early_reversal_valid", False)),
                "trend_exhaustion": bool(eng.get("trend_exhaustion", False)),
                "pressure_transfer": bool(eng.get("pressure_transfer", False)),
                "shock_move": bool(eng.get("shock_move", False)),
                "low_volume_noise": bool(eng.get("low_volume_noise", False)),
                "strict_noise_block": bool(eng.get("strict_noise_block", False)),
                "transition_warning": bool(eng.get("transition_warning", False)),
                "structure_quality_score": int(eng.get("structure_quality_score", 0)),
                "micro_chop_noise": bool(eng.get("micro_chop_noise", False)),
                "continuation_not_reversal": bool(eng.get("continuation_not_reversal", False)),
                "noise_filter": str(eng.get("noise_filter", "-")),
                "capitulation_pattern": bool(eng.get("capitulation_pattern", False)),
                "move_delta_%": round(_num(d.get("move_%")), 5),
                "fat_tail_delta": round(_num(d.get("fat_tail_z")), 3),
                "kurtosis_delta": round(_num(d.get("kurtosis")), 3),
                "dve_delta_%": round(_num(d.get("dve_%")), 3),
                "buy_delta_%": round(_num(d.get("buy_%")), 2),
                "sell_delta_%": round(_num(d.get("sell_%")), 2),
                "scan_mode": eng.get("scan_mode", "-"),
                "pre_rows": eng.get("pre_rows", 0),
                "post_rows": eng.get("post_rows", 0),
                "main_causes": " | ".join(drivers_yes[:6]),
            })
            engines.append(eng)
        table = pd.DataFrame(rows)
        if not table.empty:
            table = table.sort_values(["date", "hour"], ascending=[False, False]).reset_index(drop=True)
        return table, engines

    def _threshold_table_from_engine(engine):
        before = engine.get("before", {}) if isinstance(engine, dict) else {}
        after = engine.get("after", {}) if isinstance(engine, dict) else {}
        d = engine.get("deltas", {}) if isinstance(engine, dict) else {}
        active = _num(engine.get("active_count", 0)) if isinstance(engine, dict) else 0
        trust = _num(after.get("trust_%"))
        buy = _num(after.get("buy_%")); sell = _num(after.get("sell_%"))
        pressure = buy - sell
        rows = [
            ["Safety %", max(0, round(100 - active * 7.5 - max(0, 55 - trust) * 0.35, 2)), "DANGEROUS" if active >= 7 else "WATCH", "Low safety when many reversal drivers fire"],
            ["ADX / Trend Proxy", round(abs(_num(after.get("move_%"))) * 100 + _num(after.get("dve_%")) * 0.25, 2), "VERY GOOD" if _num(after.get("dve_%")) >= 35 else "WATCH", "Strong move plus DVE means trend regime is active"],
            ["Pressure", round(pressure, 2), "GOOD" if abs(pressure) >= 8 else "BAD", "BUY minus SELL participation"],
            ["Mean Revert Risk %", min(100, round(active * 10 + abs(_num(d.get("move_%"))) * 25, 2)), "DANGEROUS" if active >= 7 else "WATCH", "High snap-back/reversal risk"],
            ["Fat Tail Risk %", min(100, round(abs(_num(after.get("fat_tail_z"))) * 18 + max(0, _num(d.get("fat_tail_z"))) * 12, 2)), "BAD" if abs(_num(after.get("fat_tail_z"))) >= 1.25 else "GOOD", "Wick/news/shock risk rising"],
            ["Spoofing Risk %", min(100, round(abs(_num(d.get("buy_%")) - _num(d.get("sell_%"))) * 1.4 + active * 3, 2)), "VERY GOOD" if active < 5 else "BAD", "Clean pressure vs fake participation"],
            ["Ergodicity %", max(0, round(100 - abs(_num(after.get("kurtosis"))) * 8 - active * 4, 2)), "BAD" if _num(after.get("kurtosis")) >= 3 else "GOOD", "Unstable/fat-tail regime"],
            ["Monte Carlo %", max(0, round(100 - active * 6 - max(0, _num(after.get("kurtosis")) - 2) * 5, 2)), "BAD" if active >= 7 else "GOOD", "Model agreement proxy"],
            ["ML Confidence %", max(0, min(100, round(trust * 0.65 + _num(after.get("dve_%")) * 0.35, 2))), "GOOD" if trust >= 55 else "BAD", "Trust + DVE confirmation"],
            ["History Match %", max(0, min(100, round(_num(engine.get("weighted_score")), 2))), "GOOD" if active >= 7 else "WATCH", "10-driver historical pattern match"],
        ]
        return pd.DataFrame(rows, columns=["Data", "Value", "Threshold", "Meaning"])

    def render_reversal_home_banner():
        engine = g.get("evaluate_latest_reversal_engine", lambda: None)()
        if not engine:
            engine = st.session_state.get("last_reversal_engine")
        if not engine:
            return
        st.markdown("### 🚨 Reversal Early Warning Engine")
        scan, engines = _scan_reversal_history_table(days=25)
        exact = scan[scan["7_out_of_10_found"] == "YES"].copy() if not scan.empty else pd.DataFrame()
        last7 = exact.iloc[0].to_dict() if not exact.empty else None
        best = None if scan.empty else scan.sort_values(["10_reverse_decision", "weighted_score"], ascending=False).iloc[0].to_dict()

        m1, m2, m3 = st.columns(3)
        m1.metric("Current Reversal Score", f"{int(engine.get('active_count', 0))}/10", f"{int(engine.get('probability_pct', 0))}%")
        if last7:
            m2.metric("Last 7/10+ Found", f"{last7.get('date')} {last7.get('hour')}", last7.get("10_reverse_decision"))
        elif best:
            m2.metric("Best 25D Scan", f"{best.get('date')} {best.get('hour')}", best.get("10_reverse_decision"))
        else:
            m2.metric("25D Reversal Scan", "Need more loaded candles", "connect/refresh")
        m3.metric("Detector Source", str(engine.get("source_frame", "Latest candles"))[:28], str(engine.get("status", "NORMAL")))

        with st.expander("📋 Open 25D 10-Reversal History Scan Table", expanded=False):
            if scan.empty:
                st.info("No hourly scan rows yet. Load more M1/H1 candles, then refresh Home.")
            else:
                st.caption("This replaces the old Best Time metric. It scans today back 25 days and shows every hour where the 10-reversal decision reached 7/10 or more.")
                if exact.empty:
                    st.warning("No exact 7/10+ hour found in loaded 25D data. Showing full scan so you can still see the best/max hours.")
                else:
                    st.success(f"Found {len(exact)} hour(s) with 7/10+ reversal decision in loaded 25D data.")
                    st.dataframe(exact, use_container_width=True, hide_index=True)
                with st.expander("Open all scanned hours", expanded=False):
                    st.dataframe(scan, use_container_width=True, hide_index=True)
                st.markdown("#### Current threshold table")
                st.dataframe(_threshold_table_from_engine(engine), use_container_width=True, hide_index=True)

        if callable(_render_reversal_engine_panel):
            _render_reversal_engine_panel(engine, location="Home")

    def _render_day_finder(results):
        st.markdown("### 🔎 Finder — Day 10-Reversal Decision Replay")
        st.caption("Choose only a day. Finder scans every loaded hour and only marks 7/10+ when the v2 noise-filter gate passes: exhaustion + pressure transfer + shock confirmation. The old hour selector and full-hour mode are removed.")
        if not callable(_collect_doo_model_candles) or not callable(_add_simple_model_features):
            st.error("Finder dependencies are not loaded.")
            return
        data = _add_simple_model_features(_collect_doo_model_candles(results))
        if not isinstance(data, pd.DataFrame) or data.empty or "time" not in data.columns:
            st.warning("No modeling candles are loaded yet. Connect/read Doo Prime or press Refresh in Doo Prime Analysis first.")
            return
        data = data.copy()
        data["time"] = pd.to_datetime(data["time"], errors="coerce")
        data = data.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
        min_t, max_t = data["time"].min(), data["time"].max()
        st.caption(f"Available loaded range: {min_t.strftime('%Y-%m-%d %H:%M')} → {max_t.strftime('%Y-%m-%d %H:%M')} | rows: {len(data):,}")
        chosen_date = st.date_input("Choose day", value=max_t.date(), min_value=min_t.date(), max_value=max_t.date(), key="doo_finder_day_only")
        day_start = pd.Timestamp(chosen_date).normalize()
        day_end = day_start + pd.Timedelta(days=1)
        found_day = data[(data["time"] >= day_start) & (data["time"] < day_end)].copy()
        if found_day.empty:
            st.warning("No loaded candles for this day.")
            return

        scan, engines = _scan_reversal_history_table(df=data, selected_date=chosen_date)
        exact = scan[scan["7_out_of_10_found"] == "YES"].copy() if not scan.empty else pd.DataFrame()
        best_engine = None
        if engines:
            best_engine = sorted(engines, key=lambda e: (int(e.get("active_count", 0)), float(e.get("weighted_score", 0))), reverse=True)[0]
        buy_candles = int((found_day.get("direction", pd.Series(dtype=str)).astype(str) == "BUY/UP").sum()) if "direction" in found_day.columns else 0
        sell_candles = int((found_day.get("direction", pd.Series(dtype=str)).astype(str) == "SELL/DOWN").sum()) if "direction" in found_day.columns else 0
        dominant = "BUY" if buy_candles > sell_candles else ("SELL" if sell_candles > buy_candles else "MIXED/FLAT")
        first_close = _num(found_day["close"].iloc[0]) if "close" in found_day.columns else 0
        last_close = _num(found_day["close"].iloc[-1]) if "close" in found_day.columns else 0
        day_move = ((last_close / max(first_close, 1e-9)) - 1) * 100 if first_close else 0.0

        c = st.columns(6)
        c[0].metric("Selected Day", str(chosen_date))
        c[1].metric("Loaded Rows", int(len(found_day)))
        c[2].metric("7/10+ Hours", int(len(exact)))
        c[3].metric("Best Decision", "N/A" if not best_engine else f"{int(best_engine.get('active_count',0))}/10", "" if not best_engine else best_engine.get("status", ""))
        c[4].metric("Day Move %", round(day_move, 5))
        c[5].metric("Dominant", dominant)

        if exact.empty:
            st.info("No 7/10+ reversal decision found for this loaded day. Check the full hourly table below for 5/10–6/10 early warnings.")
        else:
            st.error(f"Found {len(exact)} reversal danger hour(s) at 7/10 or higher for {chosen_date}.")
            st.dataframe(exact, use_container_width=True, hide_index=True)

        with st.expander("📋 Open full day hourly 10-reversal scan", expanded=True):
            if scan.empty:
                st.info("No hourly scan available for this day.")
            else:
                st.dataframe(scan, use_container_width=True, hide_index=True)

        if best_engine and callable(_render_reversal_engine_panel):
            st.markdown("### 🚨 Strongest 10-Point Reversal Decision For This Day")
            _render_reversal_engine_panel(best_engine, location="Finder day strongest hour")
            with st.expander("📊 Open threshold table for strongest Finder hour", expanded=False):
                st.dataframe(_threshold_table_from_engine(best_engine), use_container_width=True, hide_index=True)

        # Same-as-Doo metrics for the whole selected day, kept because user wanted Finder to show Doo-style data.
        selected_results, found = _finder_filtered_results(data, day_start, day_end) if callable(_finder_filtered_results) else ({}, found_day)
        metric_table = _finder_metric_table(selected_results) if callable(_finder_metric_table) else pd.DataFrame()
        duplicate_warning = _finder_duplicate_frame_warning(metric_table) if callable(_finder_duplicate_frame_warning) else ""
        if duplicate_warning:
            st.warning(duplicate_warning)
        with st.expander("📊 Open same-as-Doo metric table for selected day", expanded=False):
            if metric_table.empty:
                st.info("No recalculated Doo metric table for this day.")
            else:
                st.dataframe(metric_table, use_container_width=True, hide_index=True)

        if callable(_render_finder_basket_model):
            _render_finder_basket_model(dominant)

        show_cols = [c for c in ["source_frame", "time", "open", "high", "low", "close", "volume", "body", "range", "return_pct", "direction", "upper_wick", "lower_wick", "reaction_note"] if c in found_day.columns]
        with st.expander("📈 Open selected-day candle preview", expanded=False):
            st.dataframe(found_day[show_cols], use_container_width=True, hide_index=True)
            if "time" in found_day.columns and "close" in found_day.columns:
                try:
                    st.line_chart(found_day.set_index("time")["close"])
                except Exception:
                    pass

        payload = "DOO PRIME FINDER DAY 10-REVERSAL DECISION EXPORT\n" + "=" * 58 + "\n"
        payload += f"selected_day: {chosen_date}\nstart: {day_start}\nend: {day_end}\nrows: {len(found_day)}\nday_move_pct: {round(day_move, 5)}\ndominant_reaction: {dominant}\n7_of_10_hours: {len(exact)}\n"
        if not exact.empty:
            payload += "\n7/10+ REVERSAL DECISIONS:\n" + exact.to_csv(index=False)
        if not scan.empty:
            payload += "\nFULL DAY HOURLY 10-REVERSAL SCAN:\n" + scan.to_csv(index=False)
        if best_engine:
            payload += "\nSTRONGEST 10-POINT ENGINE:\n" + str({k: v for k, v in best_engine.items() if k != "drivers"}) + "\n"
            payload += "\nSTRONGEST DRIVER TABLE:\n" + pd.DataFrame(best_engine.get("drivers", [])).to_csv(index=False)
            payload += "\nTHRESHOLD TABLE:\n" + _threshold_table_from_engine(best_engine).to_csv(index=False)
        if not metric_table.empty:
            payload += "\nSAME-AS-DOO DAY METRICS:\n" + metric_table.to_csv(index=False)
        if show_cols:
            payload += "\nDAY CANDLE FEATURES CSV:\n" + found_day[show_cols].to_csv(index=False)
        if callable(_copy_button_html):
            _copy_button_html("📋 Copy Finder Day 10-Reversal Analysis", payload, key="doo_finder_day_copy")
        with st.expander("Fallback: open copy text", expanded=False):
            st.text_area("Finder day copy text", value=payload, height=240, key="doo_finder_day_copy_textarea")

    g["_scan_reversal_history_table"] = _scan_reversal_history_table
    g["_threshold_table_from_engine"] = _threshold_table_from_engine
    g["render_reversal_home_banner"] = render_reversal_home_banner
    g["_render_doo_finder"] = _render_day_finder
