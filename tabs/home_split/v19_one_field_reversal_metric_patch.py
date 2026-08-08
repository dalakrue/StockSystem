"""2026-06-04 V19 one-field 10-Reversal UI + compact 3-point change metric.

Non-destructive UI patch:
- Keeps all existing 10-Reversal calculations unchanged.
- Adds one compact st.metric that summarizes now/prev/prev-prev change.
- Collapses Home/Finder reversal tables into one open/close field so the page is less noisy.
"""


def install(g):
    import math
    import pandas as pd
    import streamlit as st

    scan_func = g.get("_scan_reversal_history_table")
    eval_latest = g.get("evaluate_latest_reversal_engine")
    render_panel = g.get("_render_reversal_engine_panel")
    threshold_table = g.get("_threshold_table_from_engine")
    collect_candles = g.get("_collect_doo_model_candles")
    add_features = g.get("_add_simple_model_features")
    finder_filtered = g.get("_finder_filtered_results")
    finder_detector = g.get("_finder_reversal_detector")
    engine_from_table = g.get("_reversal_engine_from_reversal_table")
    copy_button = g.get("_copy_button_html")

    def _safe_float(x, default=0.0):
        try:
            v = float(x)
            if math.isfinite(v):
                return v
        except Exception:
            pass
        return float(default)

    def _score_from_any_row(row):
        import re
        for col in ["10_reversal_score", "active_count", "score", "reversal_score", "final_score", "10_reverse_decision", "raw_drivers"]:
            if col in row and pd.notna(row.get(col)):
                try:
                    return float(row.get(col))
                except Exception:
                    m = re.search(r"(\d+(?:\.\d+)?)", str(row.get(col)))
                    if m:
                        return float(m.group(1))
        for col in ["decision", "reversal_decision", "10_reversal_decision"]:
            if col in row and pd.notna(row.get(col)):
                m = re.search(r"(\d+(?:\.\d+)?)", str(row.get(col)))
                if m:
                    return float(m.group(1))
        return 0.0

    def _sort_scan_newest_first(scan):
        if not isinstance(scan, pd.DataFrame) or scan.empty:
            return pd.DataFrame()
        d = scan.copy()
        if "_score_v19" not in d.columns:
            d["_score_v19"] = d.apply(_score_from_any_row, axis=1)
        try:
            if "date" in d.columns and "hour" in d.columns:
                hour_str = d["hour"].astype(str).str.extract(r"(\d{1,2})", expand=False).fillna("0")
                d["_t_v19"] = pd.to_datetime(d["date"].astype(str) + " " + hour_str + ":00", errors="coerce")
                d = d.sort_values("_t_v19", ascending=False, na_position="last")
        except Exception:
            pass
        return d.reset_index(drop=True)

    def _three_point_stats(scan=None, engine=None):
        scores = []
        labels = []
        d = _sort_scan_newest_first(scan)
        if isinstance(d, pd.DataFrame) and not d.empty:
            for _, r in d.head(3).iterrows():
                scores.append(_safe_float(r.get("_score_v19", _score_from_any_row(r))))
                labels.append(f"{r.get('date', '')} {r.get('hour', '')}".strip())
        if len(scores) == 0 and engine:
            scores = [_safe_float(engine.get("active_count", 0.0))]
            labels = [str(engine.get("period_label", "now"))]
        while len(scores) < 3:
            scores.append(scores[-1] if scores else 0.0)
            labels.append("not loaded")

        now, prev, prev2 = scores[0], scores[1], scores[2]
        diff_now_prev = now - prev
        diff_prev_prev2 = prev - prev2
        ratio_now_prev = now / prev if abs(prev) > 1e-9 else 0.0
        ratio_prev_prev2 = prev / prev2 if abs(prev2) > 1e-9 else 0.0
        derivative_change = diff_now_prev - diff_prev_prev2
        mean3 = (now + prev + prev2) / 3.0
        mean_deviation = now - mean3
        abs_mean_deviation = (abs(now - mean3) + abs(prev - mean3) + abs(prev2 - mean3)) / 3.0
        momentum = "UP" if derivative_change > 0 else "DOWN" if derivative_change < 0 else "FLAT"
        return {
            "now": now,
            "prev": prev,
            "prev2": prev2,
            "diff_now_prev": diff_now_prev,
            "diff_prev_prev2": diff_prev_prev2,
            "ratio_now_prev": ratio_now_prev,
            "ratio_prev_prev2": ratio_prev_prev2,
            "derivative_change": derivative_change,
            "mean_deviation": mean_deviation,
            "abs_mean_deviation": abs_mean_deviation,
            "momentum": momentum,
            "labels": labels,
        }

    def _render_one_metric(scan=None, engine=None, key_prefix="home"):
        s = _three_point_stats(scan=scan, engine=engine)
        now, prev, prev2 = s["now"], s["prev"], s["prev2"]
        speed = now - prev
        accel = (now - prev) - (prev - prev2)
        mean_dev = abs(now - ((now + prev + prev2) / 3.0))
        regime_power = max(0.0, min(100.0, (now * 7.0) + (abs(speed) * 12.0) + (max(accel, 0) * 8.0) + (mean_dev * 5.0)))
        if now >= 8 or regime_power >= 75:
            label, color, bg = "DANGER SHIFT", "#ff3b30", "rgba(255,59,48,.14)"
        elif now >= 6 or regime_power >= 55:
            label, color, bg = "WATCH SHIFT", "#ff9f0a", "rgba(255,159,10,.14)"
        elif now <= 3 and abs(speed) <= 1:
            label, color, bg = "CALM / RESET", "#34c759", "rgba(52,199,89,.14)"
        else:
            label, color, bg = "NEUTRAL", "#5ac8fa", "rgba(90,200,250,.14)"
        st.markdown(
            f"""
            <div style="border:1px solid {color};background:{bg};border-radius:16px;padding:12px 14px;box-shadow:0 10px 28px rgba(0,0,0,.10);">
              <div style="font-size:12px;opacity:.78;font-weight:800;">REGIME SHIFT INDICATOR</div>
              <div style="font-size:24px;font-weight:900;color:{color};line-height:1.15;">{label}</div>
              <div style="font-size:13px;margin-top:4px;">Power <b>{regime_power:.0f}/100</b> · 10-Reversal <b>{now:.0f}/{prev:.0f}/{prev2:.0f}</b></div>
              <div style="font-size:12px;opacity:.82;margin-top:3px;">Speed {speed:+.1f} · Accel {accel:+.1f} · Mean deviation {mean_dev:.1f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("Threshold color: green = calm/reset, blue = neutral, orange = watch shift, red = danger shift. Uses now/prev/prev-prev locked 10-Reversal scores.")

    def _split_important(scan):
        if not isinstance(scan, pd.DataFrame) or scan.empty:
            return pd.DataFrame(), pd.DataFrame()
        d = _sort_scan_newest_first(scan)
        score = pd.to_numeric(d.get("_score_v19"), errors="coerce").fillna(0)
        exact = d[score >= 8].copy()
        today = pd.Timestamp.now().strftime("%Y-%m-%d")
        today_rows = d[d.get("date", "").astype(str).eq(today)].copy() if "date" in d.columns else pd.DataFrame()
        return exact, today_rows

    def _compact_tables(scan, prefix="Home", show_today=True):
        exact, today_rows = _split_important(scan)
        with st.expander(f"📂 Open / Close ONE FIELD — {prefix} 10-Reversal tables", expanded=False):
            if not isinstance(scan, pd.DataFrame) or scan.empty:
                st.info("No locked 10-Reversal scan yet. Connect/refresh market data first.")
                return
            st.caption("One field only: locked 8/10+ rows, low ≤3/10 rows, today rows, and full 25D scan. Finished hours stay non-repainting.")
            st.markdown("#### Locked 25D 8/10+ reversal history")
            if exact.empty:
                st.info("No locked 8/10+ reversal rows in the currently loaded range yet.")
            else:
                st.dataframe(exact.drop(columns=["_score_v19", "_t_v19"], errors="ignore"), use_container_width=True, hide_index=True)
            low_rows = _sort_scan_newest_first(scan)
            low_rows = low_rows[pd.to_numeric(low_rows.get("_score_v19"), errors="coerce").fillna(99) <= 3].copy()
            st.markdown("#### Locked 25D calm / reset rows ≤3/10")
            if low_rows.empty:
                st.info("No locked ≤3/10 rows in the currently loaded range yet.")
            else:
                st.dataframe(low_rows.drop(columns=["_score_v19", "_t_v19"], errors="ignore"), use_container_width=True, hide_index=True)
            if show_today:
                st.markdown("#### Today all reversal decisions")
                if today_rows.empty:
                    st.info("No loaded rows for today's date yet.")
                else:
                    st.dataframe(today_rows.drop(columns=["_score_v19", "_t_v19"], errors="ignore"), use_container_width=True, hide_index=True)
            st.markdown("#### Full 25D hourly locked scan")
            st.dataframe(_sort_scan_newest_first(scan).drop(columns=["_score_v19", "_t_v19"], errors="ignore"), use_container_width=True, hide_index=True)

    def render_reversal_home_banner():
        engine = eval_latest() if callable(eval_latest) else None
        if not engine:
            engine = st.session_state.get("last_reversal_engine")
        scan = pd.DataFrame()
        try:
            if callable(scan_func):
                scan, _ = scan_func(days=25)
        except TypeError:
            try:
                scan, _ = scan_func()
            except Exception:
                scan = pd.DataFrame()
        except Exception:
            scan = pd.DataFrame()

        exact, today_rows = _split_important(scan)
        st.markdown("### 🚨 10-Reversal Decision — Regime Shift View")
        _render_one_metric(scan=scan, engine=engine, key_prefix="home")
        c = st.columns(4)
        c[0].metric("Current Closed-Hour Score", f"{int(_safe_float((engine or {}).get('active_count', 0)))}/10", f"{int(_safe_float((engine or {}).get('probability_pct', 0)))}%")
        c[1].metric("Locked 8/10+ in 25D", int(len(exact)))
        c[2].metric("Today Rows", int(len(today_rows)))
        if isinstance(scan, pd.DataFrame) and not scan.empty:
            best = _sort_scan_newest_first(scan).sort_values("_score_v19", ascending=False).iloc[0]
            c[3].metric("Best Locked Hour", f"{best.get('date', '')} {best.get('hour', '')}".strip(), f"{int(best.get('_score_v19', 0))}/10")
        else:
            c[3].metric("Best Locked Hour", "Need data", "connect/refresh")

        _compact_tables(scan, prefix="Home", show_today=True)
        with st.expander("📂 Open / Close ONE FIELD — current threshold + engine detail", expanded=False):
            if engine and callable(threshold_table):
                try:
                    st.dataframe(threshold_table(engine), use_container_width=True, hide_index=True)
                except Exception:
                    pass
            if engine and callable(render_panel):
                render_panel(engine, location="Home current engine")
            elif not engine:
                st.info("Current engine needs enough recent candles to compare now vs previous windows.")

    def _render_doo_finder(results):
        st.markdown("### 🔎 Finder — One Field 10-Reversal Decision Replay")
        if not callable(collect_candles) or not callable(add_features):
            st.info("Finder helpers are not loaded yet.")
            return
        data = add_features(collect_candles(results))
        if data is None or data.empty or "time" not in data.columns:
            st.warning("No modeling candles are loaded yet. Connect/read Doo Prime or press Refresh in Doo Prime Analysis first.")
            return
        data = data.copy()
        data["time"] = pd.to_datetime(data["time"], errors="coerce")
        data = data.dropna(subset=["time"]).sort_values("time")

        # 2026-06-19 FIX: keep Finder date filters in the same timezone mode as data["time"].
        # Pandas raises: TypeError: Invalid comparison between dtype=datetime64[us, UTC] and Timestamp
        # when UTC-aware candle times are compared with naive pd.Timestamp(chosen_date).
        time_tz = None
        try:
            time_tz = data["time"].dt.tz
        except Exception:
            time_tz = None

        def _finder_ts(day_value, hours=0):
            ts = pd.Timestamp(day_value) + pd.Timedelta(hours=int(hours))
            if time_tz is not None:
                try:
                    return ts.tz_localize(time_tz) if ts.tzinfo is None else ts.tz_convert(time_tz)
                except Exception:
                    return pd.Timestamp(ts, tz=time_tz)
            try:
                return ts.tz_localize(None) if getattr(ts, "tzinfo", None) is not None else ts
            except Exception:
                return ts

        min_t, max_t = data["time"].min(), data["time"].max()
        st.caption(f"Available loaded range: {min_t.strftime('%Y-%m-%d %H:%M')} → {max_t.strftime('%Y-%m-%d %H:%M')} | rows: {len(data):,}")

        c1, c2, c3 = st.columns([1.15, 1.1, 1.75])
        with c1:
            chosen_date = st.date_input("Choose day", value=max_t.date(), min_value=min_t.date(), max_value=max_t.date(), key="doo_finder_calendar_day_v19")
        with c2:
            view_mode = st.selectbox("View", ["Selected hour", "Full day"], index=0, key="doo_finder_view_mode_v19")
        day_start = _finder_ts(chosen_date)
        day_end = day_start + pd.Timedelta(days=1)
        available_for_day = data[(data["time"] >= day_start) & (data["time"] < day_end)]
        hour_values = sorted(available_for_day["time"].dt.hour.unique().tolist()) if not available_for_day.empty else [int(max_t.hour)]
        with c3:
            hour_label = st.selectbox("Choose hour", [f"{h:02d}:00" for h in hour_values], index=max(0, len(hour_values)-1), key="doo_finder_hour_select_v19", disabled=(view_mode == "Full day"))

        if view_mode == "Selected hour":
            target_start = _finder_ts(chosen_date, int(str(hour_label).split(":")[0]))
            target_end = target_start + pd.Timedelta(hours=1)
            period_label = target_start.strftime("%Y-%m-%d %H:00")
        else:
            target_start = day_start
            target_end = day_end
            period_label = target_start.strftime("%Y-%m-%d full day")

        period_results, selected = finder_filtered(data, target_start, target_end) if callable(finder_filtered) else ({}, pd.DataFrame())
        rev_table = finder_detector(period_results, target_start, target_end) if callable(finder_detector) else pd.DataFrame()
        best_engine = engine_from_table(rev_table) if callable(engine_from_table) else None
        if best_engine:
            best_engine["period_label"] = period_label
        scan = pd.DataFrame()
        try:
            if callable(scan_func):
                scan, _ = scan_func(df=data, days=25)
        except TypeError:
            try:
                scan, _ = scan_func(days=25)
            except Exception:
                scan = pd.DataFrame()
        except Exception:
            scan = pd.DataFrame()

        _render_one_metric(scan=scan, engine=best_engine, key_prefix="finder")
        c = st.columns(3)
        c[0].metric("Selected Period", period_label, f"rows {len(selected) if isinstance(selected, pd.DataFrame) else 0}")
        c[1].metric("Finder Score", f"{int(_safe_float((best_engine or {}).get('active_count', 0)))}/10", f"{int(_safe_float((best_engine or {}).get('probability_pct', 0)))}%")
        c[2].metric("Finder Status", str((best_engine or {}).get("status", "NO ENGINE")), str((best_engine or {}).get("title", ""))[:28])

        with st.expander("📂 Open / Close ONE FIELD — Finder selected-period reversal detail", expanded=False):
            if isinstance(rev_table, pd.DataFrame) and not rev_table.empty:
                st.markdown("#### Before / After reversal detector")
                st.dataframe(rev_table, use_container_width=True, hide_index=True)
            else:
                st.info("No Finder reversal detector table for this selection yet.")
            if best_engine and callable(threshold_table):
                st.markdown("#### 10 threshold table")
                st.dataframe(threshold_table(best_engine), use_container_width=True, hide_index=True)
            if best_engine and callable(render_panel):
                render_panel(best_engine, location="Finder selected period")
            if callable(copy_button):
                payload = f"FINDER 10-REVERSAL ONE-FIELD EXPORT\nPeriod: {period_label}\nScore: {int(_safe_float((best_engine or {}).get('active_count', 0)))}/10\n"
                if isinstance(rev_table, pd.DataFrame) and not rev_table.empty:
                    payload += "\nREVERSAL TABLE:\n" + rev_table.to_csv(index=False)
                copy_button("📋 Copy Finder 10-Reversal One-Field Analysis", payload, key="doo_finder_day_copy_v19")
        _compact_tables(scan, prefix="Finder", show_today=False)

    g["render_reversal_home_banner"] = render_reversal_home_banner
    g["_render_doo_finder"] = _render_doo_finder
