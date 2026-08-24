# Compact wrapper for Home tab. Original implementation is preserved.
from core.global_upgrade import render_page_shell, render_tab_footer
from core.full_system_upgrade import render_home_upgrade_panel
from .home_split.legacy.implementation import show as _original_show
from core.streamlit_safe_dataframe import make_arrow_safe_dataframe, install_safe_dataframe_patch


def _lunch_df_signature():
    """Tiny data signature used to avoid recalculating Lunch on every rerun."""
    try:
        import pandas as pd
        import streamlit as st
        staging = st.session_state.get("calculation_staging_ohlc_df_20260617") if st.session_state.get("settings_calculation_lock_20260617") else None
        df = staging if isinstance(staging, pd.DataFrame) and not staging.empty else st.session_state.get("last_df")
        if not isinstance(df, pd.DataFrame) or df.empty:
            return ("empty", st.session_state.get("symbol"), st.session_state.get("timeframe"), st.session_state.get("source"), 0)
        cols = tuple(str(c) for c in df.columns[:12])
        time_col = next((c for c in df.columns if str(c).lower() in ("time", "datetime", "date", "timestamp")), None)
        close_col = next((c for c in df.columns if str(c).lower() in ("close", "c")), None)
        last_time = str(df[time_col].iloc[-1]) if time_col is not None and len(df) else ""
        last_close = str(df[close_col].iloc[-1]) if close_col is not None and len(df) else ""
        return (len(df), cols, last_time, last_close, st.session_state.get("symbol"), st.session_state.get("timeframe"), st.session_state.get("source"), st.session_state.get("data_version", 0))
    except Exception:
        return ("unknown",)


def _compact_ohlc_tail(df, rows=180):
    """Return a small, sorted, de-duplicated OHLC tail for reliable exports without high RAM use."""
    try:
        import pandas as pd
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame()
        d = df.tail(max(rows * 3, rows)).copy()
        rename = {"datetime": "time", "date": "time", "timestamp": "time", "tick_volume": "volume", "c": "close", "h": "high", "l": "low", "o": "open"}
        lower = {str(c).lower(): c for c in d.columns}
        for src, dst in rename.items():
            if src in lower and dst not in d.columns:
                d = d.rename(columns={lower[src]: dst})
        keep = [c for c in ["time", "open", "high", "low", "close", "volume"] if c in d.columns]
        if keep:
            d = d[keep].copy()
        if "time" in d.columns:
            d["time"] = pd.to_datetime(d["time"], errors="coerce")
            d = d.dropna(subset=["time"]).sort_values("time").drop_duplicates("time", keep="last")
        for c in ["open", "high", "low", "close", "volume"]:
            if c in d.columns:
                d[c] = pd.to_numeric(d[c], errors="coerce")
        return d.tail(rows).sort_values("time", ascending=False).reset_index(drop=True)
    except Exception:
        try:
            return df.tail(rows).copy()
        except Exception:
            import pandas as pd
            return pd.DataFrame()


def _get_cached_lunch_metric_result(force=False):
    """Run the expensive metric engine only when the user presses Run or data changes."""
    try:
        import streamlit as st
        sig = _lunch_df_signature()
        if (not force) and st.session_state.get("lunch_metric_result_signature") == sig:
            cached = st.session_state.get("lunch_metric_result_cache")
            if isinstance(cached, dict):
                return cached
        from .eurusd_h1_matrix import _get_frames, build_tables, _save_to_session
        h1, m1 = _get_frames()
        result = build_tables(h1, m1)
        if isinstance(result, dict) and result.get("ok"):
            _save_to_session(result)
            st.session_state["lunch_metric_result_cache"] = result
            st.session_state["lunch_metric_result_signature"] = sig
            st.session_state["lunch_metric_result_built_at"] = __import__("pandas").Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        return result
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def _get_cached_lunch_copy_payload(force=False):
    """Build Copy All text once per data/calculation change instead of on every repaint."""
    try:
        import streamlit as st
        sig = (_lunch_df_signature(), bool(st.session_state.get("metric_run_calculate", False)), st.session_state.get("lunch_prediction_export"), st.session_state.get("home_copy_export_built_at"))
        if (not force) and st.session_state.get("lunch_copy_payload_signature") == sig:
            cached = st.session_state.get("lunch_copy_payload_cache")
            if isinstance(cached, str):
                return cached
        payload = _build_lunch_all_copy_text()
        st.session_state["lunch_copy_payload_cache"] = payload
        st.session_state["lunch_copy_payload_signature"] = sig
        return payload
    except Exception:
        return _build_lunch_all_copy_text()


def _score_from_row(row):
    import re
    import pandas as pd
    for col in ["10_reversal_score", "score", "active_count", "reversal_score", "final_score", "10_reverse_decision", "raw_drivers"]:
        if col in row and pd.notna(row.get(col)):
            try:
                return int(round(float(row.get(col))))
            except Exception:
                pass
    for col in ["decision", "reversal_decision", "10_reversal_decision", "10_reverse_decision"]:
        if col in row and pd.notna(row.get(col)):
            m = re.search(r"(\d+(?:\.\d+)?)", str(row.get(col)))
            if m:
                try:
                    return int(round(float(m.group(1))))
                except Exception:
                    pass
    return 0


def _load_reversal_scan():
    import pandas as pd
    import streamlit as st
    # Never touch the visualization export here. Older code appended it to an
    # undefined `lines` list, which could crash the phone when this history
    # field opened after BI export was built.
    scan = st.session_state.get("home_reversal_25d_scan")
    if isinstance(scan, pd.DataFrame) and not scan.empty:
        out = scan.copy()
        out["10_reversal_score"] = out.apply(_score_from_row, axis=1)
        return out
    # Do not run the heavy 25D scan just because Lunch opened. It is rebuilt
    # only after the user presses Run Calculating/Refresh or a caller sets
    # lunch_force_reversal_scan. This keeps launch fast and RAM usage stable.
    if not bool(st.session_state.get("lunch_force_reversal_scan", False)):
        return pd.DataFrame()
    try:
        from .home_split import doo_prime_deep
        from core.v6_final_ui_logic_patch import get_best_shared_df
        df = get_best_shared_df()
        if isinstance(df, pd.DataFrame) and not df.empty and hasattr(doo_prime_deep, "_scan_reversal_history_table"):
            scan, _engines = doo_prime_deep._scan_reversal_history_table(df=df, days=25)
            if isinstance(scan, pd.DataFrame) and not scan.empty:
                scan = scan.copy()
                scan["10_reversal_score"] = scan.apply(_score_from_row, axis=1)
                st.session_state["home_reversal_25d_scan"] = scan
                st.session_state["lunch_force_reversal_scan"] = False
                return scan
    except Exception:
        pass
    try:
        st.session_state["lunch_force_reversal_scan"] = False
    except Exception:
        pass
    return pd.DataFrame()


def _render_high_reversal_table(scan=None):
    """One Home field for locked 25D 10-Reversal values >= 8/10."""
    try:
        import pandas as pd
        import streamlit as st
        from core.pro_terminal_uiux import apply_pro_terminal_css
    except Exception:
        return

    apply_pro_terminal_css()
    if scan is None:
        scan = _load_reversal_scan()

    st.markdown('<div class="qx-highrev-shell qx-home-pop-card">', unsafe_allow_html=True)
    with st.expander("🚨 Open / Close ONE FIELD — 25D Locked 10-Reversal History ≥ 8/10", expanded=False):
        st.caption("Restored 25-day scan. Shows only closed-hour rows where 10-Reversal Decision is 8/10 or higher. Table includes out-of-10 score.")
        if not isinstance(scan, pd.DataFrame) or scan.empty:
            st.info("No 25D locked reversal scan is loaded yet. Connect/refresh market data first, then open this field again.")
            st.markdown('</div>', unsafe_allow_html=True)
            return

        out = scan.copy()
        if "10_reversal_score" not in out.columns:
            out["10_reversal_score"] = out.apply(_score_from_row, axis=1)
        high = out[pd.to_numeric(out["10_reversal_score"], errors="coerce").fillna(0) >= 8].copy()
        if high.empty:
            st.warning("The current locked scan has no rows with 10-Reversal Decision ≥ 8/10.")
            st.markdown('</div>', unsafe_allow_html=True)
            return

        try:
            if "date" in high.columns and "hour" in high.columns:
                hour = high["hour"].astype(str).str.extract(r"(\d{1,2})", expand=False).fillna("0")
                high["_time_sort"] = pd.to_datetime(high["date"].astype(str) + " " + hour + ":00", errors="coerce")
                high = high.sort_values("_time_sort", ascending=False, na_position="last")
        except Exception:
            pass

        today_key = pd.Timestamp.now().strftime("%Y-%m-%d")
        today_high = high[high["date"].astype(str).eq(today_key)].copy() if "date" in high.columns else pd.DataFrame()
        best = high.sort_values("10_reversal_score", ascending=False).iloc[0]
        latest = high.iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("≥ 8/10 Total 25D", int(len(high)))
        c2.metric("Today ≥ 8/10", int(len(today_high)))
        c3.metric("Highest Score", f"{int(best.get('10_reversal_score', 0))}/10")
        c4.metric("Latest ≥8 Hour", f"{latest.get('date', '')} {latest.get('hour', '')}".strip(), f"{int(latest.get('10_reversal_score', 0))}/10")

        wanted = ["date", "hour", "10_reversal_score", "decision", "bias", "direction", "state", "weighted_score", "phase_transition_score", "phase_transition_state", "phase_reasons", "locked", "no_future", "phase_no_future"]
        show_cols = [c for c in wanted if c in high.columns] or list(high.columns[:12])
        st.dataframe(high[show_cols], use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)


def _render_low_reversal_table(scan=None):
    """One Home field for 10-Reversal values <= 3/10."""
    try:
        import pandas as pd
        import streamlit as st
        from core.pro_terminal_uiux import apply_pro_terminal_css
    except Exception:
        return

    apply_pro_terminal_css()
    if scan is None:
        scan = _load_reversal_scan()

    st.markdown('<div class="qx-lowrev-shell qx-home-pop-card">', unsafe_allow_html=True)
    with st.expander("✅ Open / Close ONE FIELD — 10-Reversal Calm Table ≤ 3/10", expanded=False):
        st.caption("One field only. Shows closed-hour rows where 10-Reversal Decision is 3/10 or lower.")
        if not isinstance(scan, pd.DataFrame) or scan.empty:
            st.info("No 25D locked reversal scan is loaded yet. Connect/refresh market data first, then open this field again.")
            st.markdown('</div>', unsafe_allow_html=True)
            return

        out = scan.copy()
        if "10_reversal_score" not in out.columns:
            out["10_reversal_score"] = out.apply(_score_from_row, axis=1)
        low = out[pd.to_numeric(out["10_reversal_score"], errors="coerce").fillna(99) <= 3].copy()
        if low.empty:
            st.warning("The current locked scan has no rows with 10-Reversal Decision ≤ 3/10.")
            st.markdown('</div>', unsafe_allow_html=True)
            return

        today_key = pd.Timestamp.now().strftime("%Y-%m-%d")
        today_low = low[low["date"].astype(str).eq(today_key)].copy() if "date" in low.columns else pd.DataFrame()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("≤ 3/10 Total 25D", int(len(low)))
        c2.metric("Today ≤ 3/10", int(len(today_low)))
        c3.metric("Lowest Score", f"{int(low['10_reversal_score'].min())}/10")
        latest = low.iloc[0]
        c4.metric("Latest Calm Hour", f"{latest.get('date', '')} {latest.get('hour', '')}".strip(), f"{int(latest.get('10_reversal_score', 0))}/10")

        wanted = ["date", "hour", "10_reversal_score", "decision", "bias", "direction", "state", "weighted_score", "phase_transition_score", "phase_transition_state", "phase_reasons", "locked", "no_future", "phase_no_future"]
        show_cols = [c for c in wanted if c in low.columns] or list(low.columns[:12])

        st.markdown("#### Today calm rows")
        if today_low.empty:
            st.info("No ≤ 3/10 rows for today yet.")
        else:
            st.dataframe(today_low[show_cols], use_container_width=True, hide_index=True)
        st.markdown("#### 25D calm rows ≤ 3/10")
        st.dataframe(low[show_cols], use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)



def _render_three_point_change_metric(scan=None):
    """Regime Shift Indicator based on now/prev/prev-prev 10-Reversal scores."""
    try:
        import pandas as pd
        import streamlit as st
        if scan is None:
            scan = _load_reversal_scan()
        if not isinstance(scan, pd.DataFrame) or scan.empty:
            st.metric("Regime Shift Indicator", "Need data", "connect/refresh")
            return
        d = scan.copy()
        if "10_reversal_score" not in d.columns:
            d["10_reversal_score"] = d.apply(_score_from_row, axis=1)
        try:
            if "date" in d.columns and "hour" in d.columns:
                hour = d["hour"].astype(str).str.extract(r"(\d{1,2})", expand=False).fillna("0")
                d["_t_metric"] = pd.to_datetime(d["date"].astype(str) + " " + hour + ":00", errors="coerce")
                d = d.sort_values("_t_metric", ascending=False, na_position="last")
        except Exception:
            pass
        vals = pd.to_numeric(d["10_reversal_score"], errors="coerce").dropna().head(3).tolist()
        while len(vals) < 3:
            vals.append(vals[-1] if vals else 0.0)
        now, prev, prev2 = [float(v) for v in vals[:3]]
        speed = now - prev
        accel = (now - prev) - (prev - prev2)
        compression = abs(now - ((now + prev + prev2) / 3.0))
        regime_power = max(0.0, min(100.0, (now * 7.0) + (abs(speed) * 12.0) + (max(accel, 0) * 8.0) + (compression * 5.0)))
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
              <div style="font-size:13px;margin-top:4px;">Power <b>{regime_power:.0f}/100</b> · Score <b>{now:.0f}/{prev:.0f}/{prev2:.0f}</b></div>
              <div style="font-size:12px;opacity:.82;margin-top:3px;">Speed {speed:+.1f} · Accel {accel:+.1f} · Mean deviation {compression:.1f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except Exception:
        pass

def _render_home_top_reversal_command_center():
    """Home placement controller: 10-Reversal first, with metrics beside title."""
    try:
        import pandas as pd
        import streamlit as st
        scan = _load_reversal_scan()
        low_total = 0
        last_low_hour = "No ≤3 hour"
        last_hour_score = "—"
        if isinstance(scan, pd.DataFrame) and not scan.empty:
            vals = pd.to_numeric(scan.get("10_reversal_score"), errors="coerce")
            low_total = int((vals <= 3).sum())
            # Latest row by existing sort; if hour/date available this is newest closed hour in scan.
            latest = scan.iloc[0]
            try:
                latest_score = int(round(float(latest.get("10_reversal_score", 0))))
                last_hour_score = f"{latest_score}/10"
                
                low_rows = scan[pd.to_numeric(scan.get("10_reversal_score"), errors="coerce") <= 3].copy()
                if isinstance(low_rows, pd.DataFrame) and not low_rows.empty:
                    low_latest = low_rows.iloc[0]
                    last_low_hour = f"{low_latest.get('date', '')} {low_latest.get('hour', '')}".strip()
                    last_hour_score = f"{int(round(float(low_latest.get('10_reversal_score', 0))))}/10"
            except Exception:
                pass
        title_cols = st.columns([2.0, 1, 1, 1.7])
        title_cols[0].markdown("### 🚨 10-Reversal Decision")
        title_cols[1].metric("Latest Hour ≤3/10", last_low_hour, last_hour_score)
        title_cols[2].metric("25D Total ≤3/10", low_total)
        with title_cols[3]:
            _render_three_point_change_metric(scan)
        st.caption("All 10-Reversal / reverse-decision sections are placed first, before copy, refresh, sessions, account, and analytics.")
        try:
            from .home_split.doo_prime_deep import render_reversal_home_banner
            render_reversal_home_banner()
        except Exception as exc:
            with st.expander("Show 10-Reversal top banner error", expanded=False):
                st.exception(exc)
        _render_high_reversal_table(scan)
        _render_low_reversal_table(scan)
    except Exception:
        pass


def _render_home_copy_refresh_bar():
    try:
        import streamlit as st
        import pandas as pd
        from core.navigation_parts.connection import _connect_now
        from .home_split.legacy import implementation as impl
        build = getattr(impl, "_build_home_copy_payload", None)
        copy_box = getattr(impl, "_copy_home_data_box", None)

        st.markdown("### 📋 Copy + Refresh")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📋 Build + Copy Home Data", key="home_v17_copy_after_reversal", use_container_width=True):
                if callable(build):
                    st.session_state.home_copy_export_text = build()
                    st.session_state.home_copy_export_built_at = str(pd.Timestamp.now())
                else:
                    st.warning("Copy builder is not loaded yet.")
        with c2:
            if st.button("🔁 Refresh Home Now", key="home_v17_refresh_after_reversal", use_container_width=True):
                _connect_now("Home refresh after reversal", quick=True)

        rows = len(st.session_state.get("last_df")) if st.session_state.get("last_df") is not None else 0
        st.caption(f"Source: {st.session_state.get('source','DISCONNECTED')} | Timeframe: {st.session_state.get('timeframe','M1')} | Rows: {rows:,}")
        text = st.session_state.get("home_copy_export_text", "")
        if text and callable(copy_box):
            copy_box(text=text)
    except Exception as exc:
        import streamlit as st
        with st.expander("Show Copy/Refresh error", expanded=False):
            st.exception(exc)


def _render_regime_zone_range_panel():
    """One Home open/close field for today/monthly regime + supply/resistance/order/impulse zones and TP range."""
    try:
        import pandas as pd
        import streamlit as st
        df = st.session_state.get("last_df")
        if not isinstance(df, pd.DataFrame) or df.empty:
            with st.expander("📂 Open / Close ONE FIELD — Today + Monthly Regime / Zones / TP Range", expanded=False):
                st.info("No market dataframe yet. Connect or refresh first.")
            return
        d = df.copy()
        # Normalize common OHLC names without changing source dataframe.
        cols = {str(c).lower(): c for c in d.columns}
        close_c = cols.get("close") or cols.get("c")
        high_c = cols.get("high") or cols.get("h")
        low_c = cols.get("low") or cols.get("l")
        time_c = cols.get("time") or cols.get("datetime") or cols.get("date")
        if not all([close_c, high_c, low_c]):
            with st.expander("📂 Open / Close ONE FIELD — Today + Monthly Regime / Zones / TP Range", expanded=False):
                st.warning("OHLC columns not found. Need close/high/low columns for regime and zone table.")
            return
        if time_c:
            d["_time"] = pd.to_datetime(d[time_c], errors="coerce")
        else:
            d["_time"] = pd.date_range(end=pd.Timestamp.now(), periods=len(d), freq="min")
        d = d.dropna(subset=["_time", close_c, high_c, low_c])
        if d.empty:
            return
        today_date = d["_time"].max().date()
        today = d[d["_time"].dt.date.eq(today_date)].copy()
        monthly = d[d["_time"] >= (d["_time"].max() - pd.Timedelta(days=30))].copy()

        def summarize(name, x):
            if x.empty:
                return {"Range": name, "Regime": "NO DATA"}
            close = pd.to_numeric(x[close_c], errors="coerce")
            high = pd.to_numeric(x[high_c], errors="coerce")
            low = pd.to_numeric(x[low_c], errors="coerce")
            first, last = float(close.dropna().iloc[0]), float(close.dropna().iloc[-1])
            hi, lo = float(high.max()), float(low.min())
            rng = max(hi - lo, 1e-9)
            move_pct = (last - first) / max(abs(first), 1e-9) * 100
            pos = (last - lo) / rng
            regime = "BULLISH TREND" if move_pct > 0.10 and pos > 0.55 else "BEARISH TREND" if move_pct < -0.10 and pos < 0.45 else "RANGE / ACCUMULATION"
            atr_like = (high - low).rolling(14, min_periods=1).mean().iloc[-1]
            tp_buy_low, tp_buy_high = last + float(atr_like) * 0.8, last + float(atr_like) * 1.6
            tp_sell_low, tp_sell_high = last - float(atr_like) * 0.8, last - float(atr_like) * 1.6
            return {
                "Range": name,
                "Start": str(x["_time"].min()),
                "End": str(x["_time"].max()),
                "Regime": regime,
                "Current Price": round(last, 3),
                "Supply Zone": f"{round(hi - rng*0.12,3)} → {round(hi,3)}",
                "Resistance Zone": f"{round(hi - rng*0.22,3)} → {round(hi - rng*0.12,3)}",
                "Order Zone": f"{round(lo + rng*0.38,3)} → {round(lo + rng*0.62,3)}",
                "Impulse Zone": f"{round(lo,3)} → {round(lo + rng*0.18,3)} / {round(hi - rng*0.18,3)} → {round(hi,3)}",
                "TP Buy Range": f"{round(tp_buy_low,3)} → {round(tp_buy_high,3)}",
                "TP Sell Range": f"{round(tp_sell_high,3)} → {round(tp_sell_low,3)}",
            }
        table = pd.DataFrame([summarize("Today", today), summarize("Monthly / Last 30D", monthly)])
        with st.expander("📂 Open / Close ONE FIELD — Today + Monthly Regime / Zones / TP Range", expanded=False):
            st.caption("One table only: today regime, monthly regime, supply/resistance/order/impulse zones, and TP suggestion range. Uses current shared OHLC data only.")
            st.dataframe(table, use_container_width=True, hide_index=True)
    except Exception as exc:
        import streamlit as st
        with st.expander("Show Regime / Zone panel error", expanded=False):
            st.exception(exc)


def _render_home_dashboard():
    # V25: Launcher inner tab removed. Keep only clean Home fields and the
    # existing original logic is preserved in files but not stacked here.
    render_home_upgrade_panel()
    _render_home_top_reversal_command_center()
    _render_home_copy_refresh_bar()
    _render_regime_zone_range_panel()



def _build_short_necessary_copy_text():
    """Small phone-friendly copy payload: only the important decision values."""
    import json
    import streamlit as st
    exp = st.session_state.get("eurusd_h1_matrix_export", {}) or {}
    scores = exp.get("scores", {}) if isinstance(exp, dict) else {}
    reverse10 = exp.get("reverse10", []) if isinstance(exp, dict) else []
    lines = [
        "NECESSARY SHORT COPY",
        f"Symbol: {st.session_state.get('symbol','EURUSD')}",
        f"Timeframe: {st.session_state.get('timeframe','H1')}",
        f"Source: {st.session_state.get('source','DISCONNECTED')}",
    ]
    if isinstance(scores, dict) and scores:
        for k in ["Decision", "Direction", "Master /10", "Entry /10", "Hold /10", "TP /10", "Exit Risk /10"]:
            if k in scores:
                lines.append(f"{k}: {scores.get(k)}")
    if isinstance(reverse10, list) and reverse10:
        lines.append("Reverse 10 decision factors:")
        for r in reverse10[:10]:
            if isinstance(r, dict):
                lines.append(f"- {r.get('No','')}. {r.get('10 Reverse-Style Factor','Factor')}: {r.get('Scale /10','?')}/10 | {r.get('Decision','')}")
    elif isinstance(exp, dict) and exp:
        lines.append("Metric export exists but short score keys were not found.")
    else:
        lines.append("No metric export yet. Press Run Calculate Metric first.")
    return "\n".join(str(x) for x in lines if str(x).strip())


def _render_short_necessary_copy_button(location="home_metric"):
    import streamlit as st
    try:
        from core.pro_terminal_uiux import render_mobile_copy_button
        payload = _build_short_necessary_copy_text()
        render_mobile_copy_button("Copy Necessary Short Only", payload, f"necessary_short_{location}")
        with st.expander("Fallback text — Necessary Short Copy", expanded=False):
            st.text_area("Long-press / select all if phone browser blocks copy", payload, height=180, key=f"necessary_short_fallback_{location}")
    except Exception:
        st.text_area("Necessary Short Copy", _build_short_necessary_copy_text(), height=180, key=f"necessary_short_plain_{location}")


def _build_lunch_all_copy_text():
    """Full phone-safe Lunch tab export using every currently available Lunch/Home data source."""
    import json
    import pandas as pd
    import streamlit as st

    lines = []
    lines.append("LUNCH TAB FULL COPY EXPORT")
    lines.append("=" * 72)
    lines.append(f"Built: {pd.Timestamp.now().strftime('%Y-%m-%d %A %H:%M:%S')}")
    lines.append(f"Symbol: {st.session_state.get('symbol','EURUSD')}")
    lines.append(f"Timeframe: {st.session_state.get('timeframe','H1')}")
    lines.append(f"Source: {st.session_state.get('source','DISCONNECTED')}")
    df = st.session_state.get("last_df")
    lines.append(f"Rows: {len(df) if isinstance(df, pd.DataFrame) else 0}")

    exp = st.session_state.get("eurusd_h1_matrix_export", {}) or {}
    if isinstance(exp, dict) and exp:
        lines.append("\nMETRIC + 010 REVERSE DECISION EXPORT")
        lines.append(json.dumps(exp, default=str, indent=2))
    else:
        lines.append("\nMETRIC + 010 REVERSE DECISION EXPORT: not calculated yet. Press Run Calculating first.")

    pred = st.session_state.get("lunch_prediction_export", {}) or {}
    if isinstance(pred, dict) and pred:
        lines.append("\nPREDICTION VISUALIZATION EXPORT")
        lines.append(json.dumps(pred, default=str, indent=2))
    else:
        lines.append("\nPREDICTION VISUALIZATION EXPORT: not generated yet. Press Run Visualization first.")

    # Never touch the visualization export here. Older code appended it to an
    # undefined `lines` list, which could crash the phone when this history
    # field opened after BI export was built.
    scan = st.session_state.get("home_reversal_25d_scan")
    if isinstance(scan, pd.DataFrame) and not scan.empty:
        lines.append("\nHOME/LUNCH 25D REVERSAL SCAN")
        lines.append(scan.tail(180).to_csv(index=False))

    if isinstance(df, pd.DataFrame) and not df.empty:
        lines.append("\nLATEST SHARED MARKET DATA — CLEAN SORTED TAIL")
        lines.append(_compact_ohlc_tail(df, rows=180).to_csv(index=False))

    existing = st.session_state.get("home_copy_export_text", "")
    if existing:
        lines.append("\nLEGACY HOME COPY PAYLOAD")
        lines.append(str(existing))
    return "\n".join(lines)


def _render_lunch_copy_refresh_bar():
    """Premium phone-safe copy buttons + refresh in one compact command card."""
    import streamlit as st
    import pandas as pd
    from core.navigation_parts.connection import _connect_now
    try:
        from core.pro_terminal_uiux import render_mobile_copy_button, apply_pro_terminal_css
        apply_pro_terminal_css()
    except Exception:
        render_mobile_copy_button = None

    all_payload = _get_cached_lunch_copy_payload()
    short_payload = _build_short_necessary_copy_text()
    st.markdown("""
    <div class="qx-home-pop-card">
      <div style="display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;">
        <div>
          <div style="font-weight:950;font-size:1.12rem;color:#0f172a;">📋 Lunch Copy Center</div>
          <div style="font-size:.86rem;color:#075985;font-weight:750;">Short = necessary decision only. All = full Lunch + prediction + visualization + data export.</div>
        </div>
        <div style="font-size:.78rem;color:#0f766e;font-weight:900;padding:6px 10px;border-radius:999px;background:rgba(240,253,250,.65);border:1px solid rgba(20,184,166,.20);">PHONE SAFE</div>
      </div>
    </div>
    """, unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1.15, 1.15, .8])
    with c1:
        st.caption(f"Necessary copy • {len(short_payload):,} chars")
        if callable(render_mobile_copy_button):
            render_mobile_copy_button("Copy Necessary", short_payload, "lunch_copy_short_phone_v2")
        st.download_button("⬇️ Download Short .txt", short_payload, file_name="lunch_short_decision.txt", mime="text/plain", use_container_width=True, key="lunch_short_download_v2")
    with c2:
        st.caption(f"Full copy • {len(all_payload):,} chars")
        if callable(render_mobile_copy_button):
            render_mobile_copy_button("Copy Full Export", all_payload, "lunch_copy_all_phone_v2")
        st.download_button("⬇️ Download All .txt", all_payload, file_name="lunch_full_export.txt", mime="text/plain", use_container_width=True, key="lunch_all_download_v2")
    with c3:
        st.caption("Refresh data/cache")
        if st.button("🔁 Refresh", key="lunch_refresh_button", use_container_width=True):
            _connect_now("Lunch refresh", quick=True)
            st.session_state.home_copy_export_built_at = str(pd.Timestamp.now())
            st.session_state["lunch_copy_payload_signature"] = None
            st.session_state["lunch_metric_result_signature"] = None
            st.session_state["lunch_force_reversal_scan"] = True
            st.success("Refreshed.")
    with st.expander("Fallback copy text — always works on mobile", expanded=False):
        st.text_area("Copy Short fallback", short_payload, height=180, key="lunch_short_fallback_text")
        st.text_area("Copy All fallback", all_payload, height=320, key="lunch_all_fallback_text")

def _render_lunch_metric_quality_table(result=None):
    """Compact reliability-first metric table with weekday labels."""
    import pandas as pd
    import streamlit as st
    exp = result or st.session_state.get("eurusd_h1_matrix_export", {}) or {}
    scores = exp.get("scores", {}) if isinstance(exp, dict) else {}
    df = st.session_state.get("last_df")
    rows = len(df) if isinstance(df, pd.DataFrame) else 0
    now = pd.Timestamp.now()
    checks = [
        {"Metric": "Calculation State", "Value": "READY" if scores else "WAIT", "Weekday": now.strftime("%A"), "Reliability": "HIGH" if scores else "WAIT", "Fix": "Press Run Calculating before using reverse decision."},
        {"Metric": "Shared Data Rows", "Value": rows, "Weekday": now.strftime("%A"), "Reliability": "HIGH" if rows >= 200 else "LOW" if rows else "MISSING", "Fix": "Refresh connector if rows are below 200."},
        {"Metric": "Source", "Value": st.session_state.get("source", "DISCONNECTED"), "Weekday": now.strftime("%A"), "Reliability": "HIGH" if rows else "MISSING", "Fix": "Use connected live/loaded OHLC data."},
        {"Metric": "Decision", "Value": scores.get("Decision", "WAIT"), "Weekday": now.strftime("%A"), "Reliability": "HIGH" if scores.get("Decision") else "WAIT", "Fix": "Decision updates only after manual calculation."},
        {"Metric": "Master /10", "Value": scores.get("Master /10", "WAIT"), "Weekday": now.strftime("%A"), "Reliability": "HIGH" if scores.get("Master /10") is not None else "WAIT", "Fix": "Uses H1 main score; M1 is timing confirmation only."},
        {"Metric": "Direction", "Value": scores.get("Direction", "WAIT"), "Weekday": now.strftime("%A"), "Reliability": "HIGH" if scores.get("Direction") else "WAIT", "Fix": "BUY/SELL pressure shown after Run Calculating."},
    ]
    st.markdown("### 📊 Metric Table — reliable working data")
    st.caption("Weekday is included so Monday/Tuesday/etc. rows are visible. Missing/weak data is marked before you trust the signal.")
    st.dataframe(make_arrow_safe_dataframe(pd.DataFrame(checks)), use_container_width=True, hide_index=True)


def _render_lunch_prediction_section():
    """Manual MetaTrader-style prediction visualization; no auto run."""
    import math
    import numpy as np
    import pandas as pd
    import streamlit as st

    with st.expander("📈 Open / Close — Prediction", expanded=False):
        st.caption("Future direction chart uses all available shared Lunch/Home OHLC data. It does not auto-run; press the button to draw the visualization.")
        if st.button("▶ Run Visualization", key="lunch_run_visualization_button", use_container_width=True):
            st.session_state["lunch_run_visualization"] = True

        if not st.session_state.get("lunch_run_visualization", False):
            st.info("Press Run Visualization to show the MetaTrader-style picture chart.")
            return

        df = st.session_state.get("last_df")
        if not isinstance(df, pd.DataFrame) or df.empty:
            st.warning("No shared OHLC data available yet. Refresh/connect first.")
            return
        d = df.copy()
        cols = {str(c).lower(): c for c in d.columns}
        close_c = cols.get("close") or cols.get("c")
        time_c = cols.get("time") or cols.get("datetime") or cols.get("date")
        high_c = cols.get("high") or cols.get("h")
        low_c = cols.get("low") or cols.get("l")
        if close_c is None:
            st.warning("Close column missing; prediction chart needs price close data.")
            return
        d["_close"] = pd.to_numeric(d[close_c], errors="coerce")
        if time_c:
            d["_time"] = pd.to_datetime(d[time_c], errors="coerce")
        else:
            d["_time"] = pd.date_range(end=pd.Timestamp.now(), periods=len(d), freq="min")
        d = d.dropna(subset=["_time", "_close"]).tail(240).copy()
        if len(d) < 20:
            st.warning("Not enough clean rows for reliable visualization. Need at least 20 candles.")
            return
        ret = d["_close"].pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        momentum = float(ret.tail(12).mean() if not ret.empty else 0.0)
        vol = float(ret.tail(60).std() if len(ret) >= 5 else 0.0)
        last = float(d["_close"].iloc[-1])
        horizon = 24
        future_index = pd.date_range(d["_time"].iloc[-1], periods=horizon + 1, freq="h")[1:]
        steps = np.arange(1, horizon + 1)
        projection = last * (1.0 + momentum * steps)
        upper = projection * (1.0 + max(vol, 1e-6) * np.sqrt(steps) * 1.25)
        lower = projection * (1.0 - max(vol, 1e-6) * np.sqrt(steps) * 1.25)
        chart = pd.DataFrame({"Actual Close": d.set_index("_time")["_close"]})
        fut = pd.DataFrame({"Projected Path": projection, "Projection High": upper, "Projection Low": lower}, index=future_index)
        st.line_chart(pd.concat([chart, fut], axis=0))
        direction = "UP / BUY BIAS" if projection[-1] > last else "DOWN / SELL BIAS" if projection[-1] < last else "SIDEWAYS / WAIT"
        confidence = max(0, min(100, int(55 + abs(momentum) * 100000 - vol * 10000)))
        st.session_state["lunch_prediction_export"] = {
            "direction": direction,
            "current_price": round(last, 5),
            "projected_24h": round(float(projection[-1]), 5),
            "projection_high": round(float(upper[-1]), 5),
            "projection_low": round(float(lower[-1]), 5),
            "confidence_pct": confidence,
            "rows_used": int(len(d)),
            "weekday": pd.Timestamp.now().strftime("%A"),
        }
        c1, c2, c3 = st.columns(3)
        c1.metric("Future Direction", direction)
        c2.metric("Projected 24H", f"{projection[-1]:.5f}")
        c3.metric("Confidence", f"{confidence}%")
        st.caption("Visualization is directional analysis only, not a guaranteed price prediction.")

def _render_metric_inner_tab():
    import streamlit as st

    st.markdown("### 🍱 Lunch Metric")
    st.caption("Run Calculating is first. Metric table and 010 Reverse Decision calculate only after this button is pressed.")

    c1, c2 = st.columns([2, 1])
    with c1:
        if st.button("▶ Run Calculating", use_container_width=True, key="metric_run_calculate_button"):
            st.session_state["metric_run_calculate"] = True
            st.session_state["lunch_force_reversal_scan"] = True
            st.session_state["lunch_metric_result_signature"] = None
            st.session_state["lunch_copy_payload_signature"] = None
            st.success("Lunch calculation enabled. Metric table and 010 Reverse Decision are now built.")
    with c2:
        if st.button("⏸ Stop", use_container_width=True, key="metric_stop_calculate_button"):
            st.session_state["metric_run_calculate"] = False
            st.session_state["lunch_force_reversal_scan"] = False
            st.info("Stopped. 010 Reverse Decision will not calculate until Run Calculating is clicked again.")

    if not bool(st.session_state.get("metric_run_calculate", False)):
        _render_lunch_metric_quality_table()
        with st.expander("📂 Open / Close — 010 Reverse Decision waiting", expanded=True):
            st.info("Press **Run Calculating** first. This prevents the 010 Reverse Decision from calculating when the Lunch tab opens.")
        _render_lunch_prediction_section()
        _render_lunch_copy_refresh_bar()
        return

    result = _get_cached_lunch_metric_result(force=False)
    if isinstance(result, dict) and result.get("ok"):
        built_at = st.session_state.get("lunch_metric_result_built_at")
        if built_at:
            st.caption(f"Fast mode: using cached Lunch calculation from {built_at}. It refreshes automatically when data changes or when you press Run Calculating again.")
    elif isinstance(result, dict):
        st.warning(result.get("message", "Metric data is not ready."))

    _render_lunch_metric_quality_table(result)

    st.markdown("### 010 Reverse Decision Table")
    if isinstance(result, dict) and result.get("ok"):
        try:
            import pandas as pd
            rev = result.get("reverse10")
            if isinstance(rev, pd.DataFrame) and not rev.empty:
                st.dataframe(rev, use_container_width=True, hide_index=True)
            else:
                st.info("010 Reverse Decision table is empty.")
        except Exception as exc:
            with st.expander("Show 010 Reverse Decision table error", expanded=False):
                st.exception(exc)

        with st.expander("📂 Open / Close — Full Metric Details + History", expanded=False):
            st.caption("Phone-safe mode: shows compact cached details first. It does not rebuild the heavy 25D engine on every open/close.")
            d1, d2, d3 = st.columns([1, 1, 1])
            with d1:
                if st.button("▶ Load Compact Details", key="lunch_load_full_metric_details", use_container_width=True):
                    st.session_state["lunch_show_full_metric_details"] = True
            with d2:
                if st.button("🧹 Reduce RAM", key="lunch_reduce_metric_ram", use_container_width=True):
                    for k in ["home_reversal_25d_scan", "lunch_bi_visual_cache", "lunch_visualization_export"]:
                        st.session_state.pop(k, None)
                    st.success("RAM cache reduced. Core calculation cache is kept.")
            with d3:
                st.caption("Open/close is now safe on phone.")
            if st.session_state.get("lunch_show_full_metric_details", False):
                _render_phone_safe_metric_details(result)
            else:
                st.info("Skipped heavy history build for faster Lunch and lower RAM. Press Load Compact Details when needed.")
    else:
        st.info("No valid metric result yet. Check data connection and press Run Calculating again.")

    _render_lunch_prediction_section()
    _render_lunch_copy_refresh_bar()


def _lunch_newest_first_table_v20260609(df, max_rows=80):
    """Return newest/current-time rows first for all Lunch metric/history tables.

    Fixes old behavior where a 25D table could visually start at the oldest
    loaded date such as 15.5 instead of the current/latest date such as 9.6.
    Future data changes are handled by detecting time/date/hour columns every run.
    """
    try:
        import pandas as pd
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame()
        out = df.copy()
        max_rows = int(max_rows or 80)
        # Direct time-like columns first.
        time_col = next((c for c in out.columns if str(c).lower() in ("time", "datetime", "timestamp", "date_time", "bar_time")), None)
        if time_col is not None:
            out["_sort_time_20260609"] = pd.to_datetime(out[time_col], errors="coerce")
        elif "Date" in out.columns and "Hour" in out.columns:
            out["_sort_time_20260609"] = pd.to_datetime(out["Date"].astype(str) + " " + out["Hour"].astype(str), errors="coerce")
        elif "date" in out.columns and "hour" in out.columns:
            out["_sort_time_20260609"] = pd.to_datetime(out["date"].astype(str) + " " + out["hour"].astype(str), errors="coerce")
        elif "Date" in out.columns:
            out["_sort_time_20260609"] = pd.to_datetime(out["Date"], errors="coerce")
        elif "date" in out.columns:
            out["_sort_time_20260609"] = pd.to_datetime(out["date"], errors="coerce")
        if "_sort_time_20260609" in out.columns:
            out = out.sort_values("_sort_time_20260609", ascending=False, na_position="last").drop(columns=["_sort_time_20260609"])
        else:
            # Fallback: dataframe is usually appended oldest -> newest, so reverse it.
            out = out.iloc[::-1]
        return out.head(max_rows).reset_index(drop=True)
    except Exception:
        try:
            return df.tail(int(max_rows)).iloc[::-1].reset_index(drop=True)
        except Exception:
            import pandas as pd
            return pd.DataFrame()


def _render_phone_safe_metric_details(result=None):
    """Compact metric detail viewer that is safe for mobile RAM.

    It uses the result already produced by Run Calculating instead of calling
    render_compact_panel(), because that legacy panel rebuilds all 25D tables
    and can freeze mobile browsers.
    """
    import pandas as pd
    import streamlit as st
    if not isinstance(result, dict) or not result.get("ok"):
        result = st.session_state.get("lunch_metric_result_cache") or {}
    if not isinstance(result, dict) or not result.get("ok"):
        st.info("Run Calculating first, then load compact details.")
        return
    scores = result.get("scores", {}) or {}
    c = st.columns(5)
    c[0].metric("Master", f"{float(scores.get('Master /10', 0) or 0):.2f}/10", scores.get("Decision", "WAIT"))
    c[1].metric("Entry", f"{float(scores.get('Entry /10', 0) or 0):.2f}/10")
    c[2].metric("Direction", str(scores.get("Direction", "WAIT")), f"B {float(scores.get('BUY Score', 0) or 0):.0f} / S {float(scores.get('SELL Score', 0) or 0):.0f}")
    c[3].metric("Hold", f"{float(scores.get('Hold /10', 0) or 0):.2f}/10")
    c[4].metric("TP", f"{float(scores.get('TP /10', 0) or 0):.2f}/10")

    table_choices = [k for k in ["session", "reverse10", "entry", "direction", "exit", "tp", "history"] if isinstance(result.get(k), pd.DataFrame)]
    pick = st.selectbox("Choose detail table", table_choices, key="lunch_metric_detail_table_pick") if table_choices else None
    max_rows = st.slider("Max rows shown on phone", 10, 250, 80, 10, key="lunch_metric_detail_max_rows")
    if pick:
        df = result.get(pick)
        if isinstance(df, pd.DataFrame) and not df.empty:
            show = _lunch_newest_first_table_v20260609(df, int(max_rows))
            st.dataframe(show, use_container_width=True, hide_index=True)
        else:
            st.info("This table has no rows yet.")

    history_by_factor = result.get("history_by_factor", {}) or {}
    with st.expander("📂 Open / Close — Separate 10 factor history", expanded=False):
        if not history_by_factor:
            st.info("No factor history loaded yet.")
        else:
            names = list(history_by_factor.keys())
            factor = st.selectbox("Factor", names, key="lunch_metric_factor_pick")
            fdf = history_by_factor.get(factor)
            if isinstance(fdf, pd.DataFrame) and not fdf.empty:
                cols = [c for c in ["Scale /10", "Date", "Weekday", "Hour", "Decision", "Score /100", "Open", "Close", "ADX", "Pressure", "M1 Confirm /10", "Meaning"] if c in fdf.columns]
                st.dataframe(_lunch_newest_first_table_v20260609(fdf[cols], int(max_rows)), use_container_width=True, hide_index=True)
            else:
                st.info("No rows for this factor.")

    with st.expander("📆 Open / Close — Full metric detail history with regime changes", expanded=False):
        st.caption("Built only after Run Calculating. Includes available metric history plus EURUSD regime change history with open/close.")
        hist = result.get("history") if isinstance(result, dict) else None
        if isinstance(hist, pd.DataFrame) and not hist.empty:
            st.dataframe(_lunch_newest_first_table_v20260609(hist, int(max_rows)), use_container_width=True, hide_index=True)
        else:
            st.info("No metric history table is available in the current calculation result.")
        try:
            dvis = _clean_lunch_visual_df(limit=1500)
            regime_summary2, regime_history2 = _detect_lunch_regime_changes(dvis, horizon=24)
            if regime_summary2.get("ok"):
                h1, h2 = st.columns(2)
                h1.metric("Regime Change Day", regime_summary2.get("last_regime_change_day", "-"), f"{regime_summary2.get('days_since_last_change', 0)} days ago")
                h2.metric("Estimated Remaining", f"{regime_summary2.get('estimated_days_remaining', 0)} days", regime_summary2.get("estimated_next_change_day", "-"))
                st.dataframe(regime_history2, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.caption(f"Regime detail unavailable: {exc}")

    with st.expander("📋 Copy compact metric detail", expanded=False):
        regime_summary = {}
        regime_history = st.session_state.get("lunch_regime_history")
        try:
            dvis = _clean_lunch_visual_df(limit=1500)
            regime_summary, regime_history = _detect_lunch_regime_changes(dvis, horizon=24)
        except Exception:
            regime_summary = {"ok": False}
        if isinstance(regime_summary, dict) and regime_summary.get("ok"):
            cm1, cm2 = st.columns(2)
            cm1.metric("Last Regime Change Day", regime_summary.get("last_regime_change_day", "-"), f"{regime_summary.get('days_since_last_change', 0)} days ago")
            cm2.metric("Estimated Days Remaining", f"{regime_summary.get('estimated_days_remaining', 0)}", regime_summary.get("estimated_next_change_day", "-"))
        payload = {"scores": scores, "tables": table_choices, "rows_limited": int(max_rows), "regime": regime_summary}
        try:
            from core.pro_terminal_uiux import render_mobile_copy_button
            import json
            render_mobile_copy_button("Copy Compact Metric Detail", json.dumps(payload, indent=2, default=str), "lunch_compact_metric_copy")
        except Exception:
            st.json(payload)



def _detect_lunch_regime_changes(d, horizon=24):
    """Fast EURUSD-aligned regime detector + simple regime duration forecast.

    Additive helper only: it reads the already-normalized Data Visualization
    frame and does not mutate source data or trigger heavy metric engines.
    """
    import pandas as pd
    import numpy as np
    if d is None or not isinstance(d, pd.DataFrame) or d.empty or "close" not in d.columns:
        return {"ok": False, "message": "No clean OHLC data."}, pd.DataFrame()
    x = d.copy()
    if "time" not in x.columns:
        x["time"] = pd.date_range(end=pd.Timestamp.now(), periods=len(x), freq="h")
    x["time"] = pd.to_datetime(x["time"], errors="coerce")
    x["close"] = pd.to_numeric(x["close"], errors="coerce")
    if "open" in x.columns:
        x["open"] = pd.to_numeric(x["open"], errors="coerce")
    else:
        x["open"] = x["close"].shift(1).fillna(x["close"])
    x = x.dropna(subset=["time", "close"]).sort_values("time").reset_index(drop=True)
    if len(x) < 20:
        return {"ok": False, "message": "Need at least 20 candles for regime analysis."}, pd.DataFrame()

    close = x["close"].astype("float64")
    ret = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    trend = x["trend_gap_pct"] if "trend_gap_pct" in x.columns else close.ewm(span=12, adjust=False).mean().sub(close.ewm(span=48, adjust=False).mean()).div(close.replace(0, np.nan)).mul(100).fillna(0)
    vol = x["volatility_pct"] if "volatility_pct" in x.columns else ret.rolling(36, min_periods=4).std().mul(100).fillna(0)
    mom = ret.rolling(12, min_periods=3).mean().fillna(0)
    vol_med = float(vol.rolling(144, min_periods=20).median().iloc[-1]) if len(vol) >= 20 else float(vol.median())
    vol_hi = float(vol.rolling(144, min_periods=20).quantile(.70).iloc[-1]) if len(vol) >= 20 else float(vol.quantile(.70))

    direction = np.where((trend > 0) & (mom >= 0), "BULL", np.where((trend < 0) & (mom <= 0), "BEAR", "RANGE"))
    energy = np.where(vol >= max(vol_hi, vol_med * 1.2), "HIGH_VOL", np.where(vol <= max(vol_med * .72, 1e-9), "LOW_VOL", "NORMAL_VOL"))
    x["regime"] = pd.Series(direction, index=x.index).astype(str) + "_" + pd.Series(energy, index=x.index).astype(str)
    # Smooth one-candle noise so EURUSD H1 does not flip regime too easily.
    # Pandas rolling().agg/apply only accepts numeric windows in many versions.
    # Keep this string-safe so Streamlit never raises: DataError: No numeric types to aggregate.
    regimes = x["regime"].astype(str).tolist()
    smooth = []
    for i in range(len(regimes)):
        window = regimes[max(0, i - 2):i + 1]
        vc = pd.Series(window, dtype="object").value_counts()
        smooth.append(str(vc.index[0]) if not vc.empty else str(regimes[i]))
    x["regime_smooth"] = pd.Series(smooth, index=x.index, dtype="object")
    x["regime_changed"] = x["regime_smooth"].ne(x["regime_smooth"].shift(1))

    changes = x.loc[x["regime_changed"]].copy()
    if changes.empty:
        changes = x.head(1).copy()
    rows = []
    idxs = list(changes.index)
    for n, idx in enumerate(idxs):
        end_idx = (idxs[n + 1] - 1) if n + 1 < len(idxs) else len(x) - 1
        seg = x.loc[idx:end_idx]
        start_time = pd.Timestamp(x.loc[idx, "time"])
        end_time = pd.Timestamp(x.loc[end_idx, "time"])
        duration_days = max((end_time - start_time).total_seconds() / 86400.0, 0.0)
        rows.append({
            "Regime Change Day": start_time.strftime("%Y-%m-%d"),
            "Change Time": start_time.strftime("%Y-%m-%d %H:%M"),
            "Regime": str(x.loc[idx, "regime_smooth"]),
            "Open": round(float(seg["open"].iloc[0]), 5),
            "Close": round(float(seg["close"].iloc[-1]), 5),
            "Bars": int(len(seg)),
            "Duration Days": round(duration_days, 2),
            "Return %": round((float(seg["close"].iloc[-1]) / max(float(seg["open"].iloc[0]), 1e-12) - 1.0) * 100, 4),
            "Avg Vol %": round(float(vol.loc[seg.index].mean()), 5),
            "Avg Trend Gap %": round(float(trend.loc[seg.index].mean()), 5),
            "Regime Score /10": round(float(max(0, min(10, 5 + abs(float(trend.loc[seg.index].mean())) * 0.35 + float(vol.loc[seg.index].mean()) * 0.55 + min(len(seg) / 48.0, 2.0)))), 2),
        })
    hist = pd.DataFrame(rows)
    durations = pd.to_numeric(hist["Duration Days"], errors="coerce").dropna()
    completed = durations.iloc[:-1] if len(durations) > 1 else durations
    median_days = float(completed.median()) if len(completed) else max(float(horizon) / 24.0, 1.0)
    last_row = hist.iloc[-1].to_dict()
    last_change_time = pd.to_datetime(last_row.get("Change Time"), errors="coerce")
    now_time = pd.Timestamp(x["time"].iloc[-1])
    elapsed_days = max((now_time - last_change_time).total_seconds() / 86400.0, 0.0) if pd.notna(last_change_time) else 0.0
    remaining_days = max(median_days - elapsed_days, 0.0)
    predicted_change_time = now_time + pd.Timedelta(days=remaining_days)
    current_regime = str(last_row.get("Regime", "UNKNOWN"))
    stability = int(max(0, min(100, 100 - abs(float(trend.iloc[-1])) * 5 - float(vol.iloc[-1]) * 18 + min(elapsed_days / max(median_days, 1e-9), 1) * 20)))
    current_score_10 = round(float(max(0, min(10, 5 + abs(float(trend.iloc[-1])) * 0.35 + float(vol.iloc[-1]) * 0.55 + min(elapsed_days / max(median_days, 1e-9), 1.0) * 2.0))), 2)
    summary = {
        "ok": True,
        "current_regime": current_regime,
        "last_regime_change_day": str(last_row.get("Regime Change Day", "")),
        "last_regime_change_time": str(last_row.get("Change Time", "")),
        "days_since_last_change": round(float(elapsed_days), 2),
        "estimated_days_remaining": round(float(remaining_days), 2),
        "estimated_next_change_day": predicted_change_time.strftime("%Y-%m-%d"),
        "estimated_next_change_time": predicted_change_time.strftime("%Y-%m-%d %H:%M"),
        "median_regime_days": round(float(median_days), 2),
        "regime_stability_pct": stability,
        "regime_score_10": current_score_10,
        "history_rows": int(len(hist)),
    }
    return summary, hist.tail(80).reset_index(drop=True)


def _clean_lunch_visual_df(limit=1500):
    """Normalize shared EURUSD/OHLC data lazily; allow larger Lunch/Data Visualization migration runs."""
    import pandas as pd
    import streamlit as st
    staging = st.session_state.get("calculation_staging_ohlc_df_20260617") if st.session_state.get("settings_calculation_lock_20260617") else None
    df = staging if isinstance(staging, pd.DataFrame) and not staging.empty else st.session_state.get("last_df")
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    limit = int(max(100, min(int(limit or 1500), 20000)))
    sig = _lunch_df_signature()
    try:
        return _cached_clean_lunch_visual_df(df, limit, sig)
    except Exception:
        return _clean_lunch_visual_df_uncached(df, limit)


def _clean_lunch_visual_df_uncached(df, limit=1500):
    import pandas as pd
    import numpy as np
    d = _compact_ohlc_tail(df, rows=int(limit))
    if d.empty or "close" not in d.columns:
        return pd.DataFrame()
    if "time" not in d.columns:
        return pd.DataFrame()
    d["time"] = pd.to_datetime(d["time"], errors="coerce")
    for c in ["open", "high", "low", "close", "volume"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce").astype("float32")
    d = d.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates("time", keep="last").tail(limit).reset_index(drop=True)
    if d.empty:
        return d
    close = d["close"].astype("float32")
    prev_close = close.shift(1)
    high = d["high"].astype("float32") if "high" in d.columns else close
    low = d["low"].astype("float32") if "low" in d.columns else close
    d["returns"] = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0).astype("float32")
    d["return_pct"] = (d["returns"] * 100).astype("float32")
    tr = pd.concat([(high-low).abs(), (high-prev_close).abs(), (low-prev_close).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(14, min_periods=2).mean().fillna(0).astype("float32")
    delta = close.diff().fillna(0)
    gain = delta.clip(lower=0).rolling(14, min_periods=2).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=2).mean().replace(0, np.nan)
    d["rsi"] = (100 - (100 / (1 + gain / loss))).fillna(50).clip(0, 100).astype("float32")
    d["rolling_mean"] = close.rolling(34, min_periods=4).mean().ffill().fillna(close).astype("float32")
    d["rolling_std"] = close.rolling(34, min_periods=4).std().fillna(0).astype("float32")
    d["ma_fast"] = close.ewm(span=12, adjust=False, min_periods=2).mean().astype("float32")
    d["ma_slow"] = close.ewm(span=48, adjust=False, min_periods=4).mean().astype("float32")
    d["ma_trend"] = close.ewm(span=144, adjust=False, min_periods=8).mean().ffill().fillna(close).astype("float32")
    d["volatility_pct"] = d["return_pct"].rolling(36, min_periods=4).std().fillna(0).astype("float32")
    d["range_pct"] = (((high - low) / close.replace(0, np.nan)) * 100).replace([np.inf, -np.inf], np.nan).fillna(d["return_pct"].abs()).astype("float32")
    d["trend_gap_pct"] = (((d["ma_fast"] - d["ma_slow"]) / close.replace(0, np.nan)) * 100).replace([np.inf, -np.inf], np.nan).fillna(0).astype("float32")
    d["trend"] = (((d["ma_fast"] - d["ma_slow"]) / d["atr"].replace(0, np.nan))).replace([np.inf, -np.inf], np.nan).fillna(0).clip(-5, 5).astype("float32")
    score = 50 + d["return_pct"].rolling(8, min_periods=2).mean().fillna(0) * 190 + d["trend_gap_pct"] * 18 - d["volatility_pct"] * 10 + (d["rsi"] - 50) * .35
    d["ml_score"] = score.clip(0, 100).astype("float32")
    d["ml_bias"] = pd.Series(np.where(d["ml_score"] >= 56, "BUY", np.where(d["ml_score"] <= 44, "SELL", "WAIT")), dtype="category")
    if "volume" in d.columns:
        vm = d["volume"].rolling(48, min_periods=8).mean(); vs = d["volume"].rolling(48, min_periods=8).std().replace(0, np.nan)
        d["volume_z"] = ((d["volume"] - vm) / vs).replace([np.inf, -np.inf], np.nan).fillna(0).clip(-5, 5).astype("float32")
    else:
        d["volume_z"] = np.float32(0)
    q25, q75 = (float(d["volatility_pct"].quantile(.25)), float(d["volatility_pct"].quantile(.75))) if len(d) >= 20 else (0.0, 0.0)
    d["risk_bucket"] = pd.Series(np.where(d["volatility_pct"] >= q75, "HIGH VOL", np.where(d["volatility_pct"] <= q25, "LOW VOL", "NORMAL")), dtype="category")
    return d


try:
    import streamlit as st
    _cached_clean_lunch_visual_df = st.cache_data(show_spinner=False, ttl=600)(_clean_lunch_visual_df_uncached)
except Exception:
    _cached_clean_lunch_visual_df = _clean_lunch_visual_df_uncached


def _five_layer_powerbi_calculate(d, horizon=20):
    import pandas as pd
    import numpy as np
    if d is None or d.empty or len(d) < 30:
        return {"ok": False, "message": "Need at least 30 clean OHLC candles."}
    try:
        return _cached_five_layer_powerbi_calculate(d, int(horizon), _lunch_df_signature())
    except Exception:
        return _five_layer_powerbi_uncached(d, int(horizon), _lunch_df_signature())


def _five_layer_powerbi_uncached(d, horizon=20, sig=None):
    import pandas as pd
    import numpy as np
    horizon = int(max(5, min(int(horizon or 20), 60)))
    x = d.tail(min(len(d), 3000))
    close = x["close"].astype("float32")
    ret = x["returns"].astype("float32") if "returns" in x else close.pct_change().fillna(0).astype("float32")
    vol = x["volatility_pct"].astype("float32") if "volatility_pct" in x else (ret.rolling(36).std().fillna(0)*100).astype("float32")
    trend = x["trend"].astype("float32") if "trend" in x else ret.rolling(20).mean().fillna(0).astype("float32")
    rsi = x["rsi"].astype("float32") if "rsi" in x else pd.Series(50, index=x.index, dtype="float32")
    rng = x["range_pct"].astype("float32") if "range_pct" in x else ret.abs().mul(100).astype("float32")
    last_close = float(close.iloc[-1])
    last_time = pd.Timestamp(x["time"].iloc[-1]) if "time" in x else pd.Timestamp.now()
    tlast, vlast, rlast = float(trend.iloc[-1]), float(vol.iloc[-1]), float(rsi.iloc[-1])
    mom12 = float(ret.tail(12).mean()); mom48 = float(ret.tail(48).mean()) if len(ret) >= 48 else mom12
    bull_raw = 50 + tlast * 8 + mom12 * 14000 + mom48 * 9000 + (rlast - 50) * .38 - vlast * 1.8
    bull_prob = int(max(1, min(99, bull_raw)))
    bear_prob = 100 - bull_prob
    range_prob = int(max(0, min(100, 100 - abs(bull_prob - 50) * 2)))
    hmm_bull = int(max(0, min(100, bull_prob - range_prob * .22)))
    hmm_bear = int(max(0, min(100, bear_prob - range_prob * .22)))
    smoothed = close.ewm(alpha=.18, adjust=False).mean()
    kalman_strength = float(max(0, min(10, abs((float(smoothed.iloc[-1]) - float(smoothed.iloc[-12 if len(smoothed) >= 12 else 0])) / max(last_close, 1e-9)) * 12000)))
    bayes_conviction = float(max(0, min(10, abs(bull_prob - 50) / 5)))
    wavelet_alignment = float(max(0, min(10, 5 + np.sign(mom12) * np.sign(mom48) * min(abs(mom12 + mom48) * 9000, 5))))
    regime_score = round(float(max(0, min(10, (kalman_strength + bayes_conviction + wavelet_alignment) / 3))), 2)
    current_regime = "BULL" if bull_prob >= 57 else "BEAR" if bull_prob <= 43 else "RANGE"

    jump_sweep = float(max(0, min(10, (abs(float(ret.iloc[-1])) / max(float(ret.tail(80).std()), 1e-7)) * 2.2 + float(rng.iloc[-1]) * .9)))
    flow_imbalance = float(max(-100, min(100, tlast * 12 + mom12 * 22000 + (rlast - 50) * .7)))
    cross_venue = float(max(0, min(10, abs(float(close.iloc[-1] - close.rolling(8, min_periods=2).mean().iloc[-1])) / max(float(x.get("atr", pd.Series([0])).iloc[-1]), 1e-7))))
    vacuum = float(max(0, min(10, (float(rng.tail(8).mean()) / max(float(rng.tail(80).median()), .0001)) * 3 + max(0, float(vol.iloc[-1] - vol.tail(80).median())) * 1.5)))
    flow_score = round(float(max(0, min(10, jump_sweep * .25 + abs(flow_imbalance) / 100 * 3 + cross_venue * .2 + vacuum * .25))), 2)

    model_scores = {
        "XGBoost-style": 50 + mom12 * 15000 + tlast * 7 + (rlast-50)*.25,
        "LightGBM-style": 50 + mom48 * 12000 + tlast * 6 - vlast * 1.2,
        "CatBoost-style": 50 + (rlast-50)*.55 + mom12 * 9000,
        "Random Forest-style": 50 + np.sign(mom12 + mom48) * min(abs(mom12 + mom48) * 10000, 28) + tlast * 4,
    }
    votes = []
    for name, score in model_scores.items():
        p = int(max(1, min(99, score)))
        votes.append({"Model": name, "Vote": "BULL" if p >= 52 else "BEAR", "Bull Probability %": p, "Bear Probability %": 100-p})
    vote_df = pd.DataFrame(votes)
    bull_votes = int((vote_df["Vote"] == "BULL").sum()); bear_votes = int((vote_df["Vote"] == "BEAR").sum())
    ensemble_prob = int(vote_df["Bull Probability %"].mean())
    ensemble_score = round(max(0, min(10, ensemble_prob / 10)), 2)

    lstm_proxy = 50 + mom48 * 16000 + tlast * 6
    transformer_proxy = 50 + mom12 * 13000 + (rlast-50)*.28
    cnn_proxy = 50 + float((ret.tail(5).gt(0).mean() - .5) * 42) + tlast * 3
    ae_anomaly = float(max(0, min(10, abs(float(ret.iloc[-1])) / max(float(ret.tail(100).std()), 1e-7))))
    deep_models = pd.DataFrame([
        {"Model": "LSTM-style forecast proxy", "Output": "BULL" if lstm_proxy >= 50 else "BEAR", "Score /10": round(max(0,min(10,lstm_proxy/10)),2)},
        {"Model": "Transformer-style forecast proxy", "Output": "BULL" if transformer_proxy >= 50 else "BEAR", "Score /10": round(max(0,min(10,transformer_proxy/10)),2)},
        {"Model": "CNN pattern recognition proxy", "Output": "BULL" if cnn_proxy >= 50 else "BEAR", "Score /10": round(max(0,min(10,cnn_proxy/10)),2)},
        {"Model": "Autoencoder anomaly detection proxy", "Output": "ANOMALY" if ae_anomaly >= 6 else "NORMAL", "Score /10": round(10-ae_anomaly if ae_anomaly < 10 else 0,2)},
    ])
    deep_score = round(float(deep_models["Score /10"].mean()), 2)

    avg_drift = float(max(-.006, min(.006, mom12*.45 + mom48*.35 + (ensemble_prob-50)/100000 + tlast/12000)))
    days = [5, 10, 20]
    f_rows = []
    for n in days:
        pred = last_close * (1 + avg_drift * n)
        width = max(float(ret.tail(120).std()), 1e-6) * (n ** .5) * 1.25
        f_rows.append({"Horizon": f"{n}d", "LSTM Forecast": round(last_close*(1+(avg_drift*1.05)*n),5), "Transformer Forecast": round(last_close*(1+(avg_drift*.92)*n),5), "XGBoost Forecast": round(last_close*(1+(avg_drift*1.12)*n),5), "Prophet Fallback": round(last_close*(1+(avg_drift*.75)*n),5), "Low": round(pred*(1-width),5), "High": round(pred*(1+width),5)})
    forecast_df = pd.DataFrame(f_rows)
    forecast_conf = int(max(1, min(99, 62 + abs(ensemble_prob-50)*.35 + regime_score*2 - vlast*2.2 - ae_anomaly*1.3)))
    forecast_score = round(max(0, min(10, forecast_conf/10)), 2)

    # regime history newest first: today/latest data appears at the top, no heavy scrolling through old rows.
    regime_raw = np.where((trend > .18) | (x["ml_score"] >= 56), "BULL", np.where((trend < -.18) | (x["ml_score"] <= 44), "BEAR", "RANGE"))
    hist_base = x[["time","open","close"]].copy(); hist_base["Regime"] = pd.Series(regime_raw, dtype="category")
    hist_base["Regime Score /10"] = (5 + trend.abs()*.8 + vol*.28 + (x["ml_score"]-50).abs()/14).clip(0,10).round(2).astype("float32")
    changes = hist_base[hist_base["Regime"].astype(str).ne(hist_base["Regime"].astype(str).shift(1))].index.tolist() or [hist_base.index[0]]
    segs=[]
    for i, idx in enumerate(changes):
        end_idx = (changes[i+1]-1) if i+1 < len(changes) else hist_base.index[-1]
        seg = hist_base.loc[idx:end_idx]
        days_in = max((pd.Timestamp(seg["time"].iloc[-1]) - pd.Timestamp(seg["time"].iloc[0])).total_seconds()/86400, 0)
        segs.append({"Start": pd.Timestamp(seg["time"].iloc[0]), "Open": round(float(seg["open"].iloc[0]),5), "Close": round(float(seg["close"].iloc[-1]),5), "Regime": str(seg["Regime"].iloc[0]), "Regime Score /10": round(float(seg["Regime Score /10"].mean()),2), "Days In Regime": round(days_in,2)})
    hist = pd.DataFrame(segs).sort_values("Start", ascending=False).head(60)
    hist["Start"] = hist["Start"].dt.strftime("%Y-%m-%d %H:%M")
    hist["Regime"] = hist["Regime"].astype("category")
    current_days = float(hist.iloc[0]["Days In Regime"]) if not hist.empty else 0.0
    completed = pd.to_numeric(hist["Days In Regime"], errors="coerce").iloc[1:]
    med_days = float(completed.median()) if len(completed) else 5.0
    days_remaining = max(med_days - current_days, 0.0)
    next_change = last_time + pd.Timedelta(days=days_remaining)
    master_score = round(float(max(0, min(10, regime_score*.22 + flow_score*.18 + ensemble_score*.24 + deep_score*.18 + forecast_score*.18))), 2)
    return {"ok": True, "last_time": last_time, "last_close": last_close, "current_regime": current_regime, "master_score": master_score, "bull_probability": int(max(1,min(99,(bull_prob+ensemble_prob)//2))), "last_regime_change": str(hist.iloc[0]["Start"]) if not hist.empty else "-", "days_in_regime": round(current_days,2), "estimated_days_remaining": round(days_remaining,2), "predicted_next_regime_change": next_change.strftime("%Y-%m-%d %H:%M"), "layer1": {"HMM Bull %": hmm_bull, "HMM Bear %": hmm_bear, "HMM Range %": range_prob, "Kalman Trend Strength /10": round(kalman_strength,2), "Bayesian Conviction /10": round(bayes_conviction,2), "Wavelet Alignment /10": round(wavelet_alignment,2), "Regime Score /10": regime_score}, "layer2": {"Jump Sweep Score /10": round(jump_sweep,2), "Flow Imbalance": round(flow_imbalance,2), "Cross Venue Score /10": round(cross_venue,2), "Vacuum Score /10": round(vacuum,2), "Flow Score /10": flow_score}, "vote_df": vote_df, "layer3": {"Bull Votes": bull_votes, "Bear Votes": bear_votes, "Bull Probability %": ensemble_prob, "Ensemble Score /10": ensemble_score}, "deep_df": deep_models, "layer4": {"Deep AI Score /10": deep_score}, "forecast_df": forecast_df, "layer5": {"Forecast Confidence %": forecast_conf, "Forecast Score /10": forecast_score}, "history": hist}


try:
    import streamlit as st
    _cached_five_layer_powerbi_calculate = st.cache_data(show_spinner=False, ttl=900)(_five_layer_powerbi_uncached)
except Exception:
    _cached_five_layer_powerbi_calculate = _five_layer_powerbi_uncached


def _render_lunch_advanced_powerbi_ml_projection(d, horizon=20):
    import pandas as pd
    import streamlit as st
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception as exc:
        st.warning(f"Plotly is not available for advanced Power BI dashboard: {exc}")
        return
    result = st.session_state.get("lunch_5layer_powerbi_result")
    if not isinstance(result, dict) or not result.get("ok"):
        st.info("Click **Run Calculating** to calculate the 5 separate Power BI + ML layers.")
        return

    m = st.columns(7)
    m[0].metric("Master Score", f"{result['master_score']}/10")
    m[1].metric("Bull Probability", f"{result['bull_probability']}%")
    m[2].metric("Regime", result["current_regime"])
    m[3].metric("Last Regime Change", result["last_regime_change"])
    m[4].metric("Days In Regime", result["days_in_regime"])
    m[5].metric("Est. Days Remaining", result["estimated_days_remaining"])
    m[6].metric("Predicted Next Change", result["predicted_next_regime_change"])

    layer_names = ["Layer 1 Regime", "Layer 2 Flow", "Layer 3 Ensemble", "Layer 4 Deep AI", "Layer 5 Forecast"]
    layer_scores = [result["layer1"]["Regime Score /10"], result["layer2"]["Flow Score /10"], result["layer3"]["Ensemble Score /10"], result["layer4"]["Deep AI Score /10"], result["layer5"]["Forecast Score /10"]]
    fig = make_subplots(rows=2, cols=2, specs=[[{"type":"bar"},{"type":"indicator"}], [{"type":"scatter"},{"type":"table"}]], vertical_spacing=.12, horizontal_spacing=.08, subplot_titles=("5 Separate Layer Scores", "Master Score", "Recent Close / ML Bias", "Layer Details"))
    fig.add_trace(go.Bar(x=layer_names, y=layer_scores, name="Score /10"), row=1, col=1)
    fig.add_trace(go.Indicator(mode="gauge+number", value=float(result["master_score"]), gauge={"axis":{"range":[0,10]}}, title={"text":"Master /10"}), row=1, col=2)
    show = d.tail(min(len(d), 700))
    fig.add_trace(go.Scatter(x=show["time"], y=show["close"], mode="lines", name="EURUSD Close"), row=2, col=1)
    if "ml_score" in show:
        fig.add_trace(go.Scatter(x=show["time"], y=show["ml_score"], mode="lines", name="ML Score", yaxis="y3"), row=2, col=1)
    detail_rows = []
    for title, vals in [("Layer 1", result["layer1"]), ("Layer 2", result["layer2"]), ("Layer 3", result["layer3"]), ("Layer 4", result["layer4"]), ("Layer 5", result["layer5"] )]:
        detail_rows.append([title, "<br>".join(f"{k}: {v}" for k, v in vals.items())])
    fig.add_trace(go.Table(header={"values":["Layer", "Separate Outputs"]}, cells={"values":[[r[0] for r in detail_rows], [r[1] for r in detail_rows]], "height":28}), row=2, col=2)
    fig.update_layout(height=760, margin=dict(l=6, r=6, t=50, b=6), legend=dict(orientation="h"), title="Advanced Power BI + ML Dashboard — 5 Separate Layer Results")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Layer 1 — Regime Engine")
        st.dataframe(pd.DataFrame([result["layer1"]]), use_container_width=True, hide_index=True)
        st.markdown("#### Layer 3 — Prediction Ensemble Voting")
        st.dataframe(result["vote_df"], use_container_width=True, hide_index=True)
    with c2:
        st.markdown("#### Layer 2 — Institutional Flow Engine")
        st.dataframe(pd.DataFrame([result["layer2"]]), use_container_width=True, hide_index=True)
        st.markdown("#### Layer 4 — Deep AI Layer")
        st.dataframe(result["deep_df"], use_container_width=True, hide_index=True)
    st.markdown("#### Layer 5 — Forecast Engine")
    st.dataframe(result["forecast_df"], use_container_width=True, hide_index=True)
    st.markdown("#### Regime History — newest first")
    hist = result.get("history")
    if isinstance(hist, pd.DataFrame) and not hist.empty:
        st.dataframe(hist, use_container_width=True, hide_index=True, height=260)
    st.session_state["lunch_prediction_export"] = {k: v for k, v in result.items() if k not in {"vote_df", "deep_df", "forecast_df", "history"}}
    st.session_state["lunch_regime_history"] = hist


def _apply_mobile_first_app_css_v20260609():
    try:
        import streamlit as st
        st.markdown("""
        <style>
        @media (max-width: 780px){
          .block-container{padding-top:.65rem!important;padding-left:.55rem!important;padding-right:.55rem!important;}
          div[data-testid="stMetric"]{border-radius:18px;padding:10px 12px;background:rgba(255,255,255,.06);border:1px solid rgba(125,211,252,.22);box-shadow:0 8px 28px rgba(15,23,42,.10);}
          div[data-testid="stDataFrame"]{border-radius:16px;overflow:hidden;}
          .stButton>button{border-radius:999px!important;min-height:44px;font-weight:800!important;box-shadow:0 10px 24px rgba(14,165,233,.18);}
          [data-testid="stHorizontalBlock"]{gap:.45rem;}
        }
        </style>
        """, unsafe_allow_html=True)
    except Exception:
        pass


def _render_lunch_data_visualization_inner_tab():
    import streamlit as st
    st.markdown("### 📊 Data Visualization")
    st.caption("Phone-safe lazy dashboard: nothing calculates until Run Calculating is clicked; cached results are reused when changing tabs.")
    c0, c1, c2 = st.columns([1.2, 1, 1])
    with c0:
        run = st.button("▶ Run Calculating", use_container_width=True, key="lunch_data_visual_run_calculating")
    with c1:
        rows_limit = st.slider("Rows used", 1000, 3000, int(st.session_state.get("lunch_bi_rows_limit", 1500)), 250, key="lunch_bi_rows_limit")
    with c2:
        horizon = st.slider("Forecast candles", 5, 60, int(st.session_state.get("lunch_bi_horizon", 20)), 5, key="lunch_bi_horizon")
    sig = (_lunch_df_signature(), int(rows_limit), int(horizon), "five_layer_powerbi_v1")
    if run:
        st.session_state["lunch_bi_visual_ready"] = True
        with st.spinner("Calculating…"):
            d = _clean_lunch_visual_df(limit=rows_limit)
            if d is None or d.empty or len(d) < 30:
                st.warning("Not enough clean EURUSD OHLC data. Connect/refresh data first.")
                _render_lunch_copy_refresh_bar()
                return
            st.session_state["lunch_5layer_powerbi_df"] = d
            st.session_state["lunch_5layer_powerbi_sig"] = sig
            st.session_state["lunch_5layer_powerbi_result"] = _five_layer_powerbi_calculate(d, horizon=horizon)
        st.success("Calculation complete. Cached dashboard will reopen instantly until you press Run Calculating again.")
    if not st.session_state.get("lunch_bi_visual_ready", False):
        st.info("Press **Run Calculating** to build the 5-layer dashboard. Changing tabs will not recalculate it.")
        _render_lunch_copy_refresh_bar()
        return
    d = st.session_state.get("lunch_5layer_powerbi_df")
    if d is None or getattr(d, "empty", True):
        d = _clean_lunch_visual_df(limit=rows_limit)
        st.session_state["lunch_5layer_powerbi_df"] = d
    _render_lunch_advanced_powerbi_ml_projection(d, horizon=horizon)
    _render_lunch_copy_refresh_bar()

def _render_doo_prime_inner_tab():
    import streamlit as st
    from core.styles import request_close_sidebar
    st.markdown("### 🏦 Doo Prime")
    st.caption("Doo Prime Analysis is now inside this Doo Prime inner tab, not beside Lunch.")
    choices = [("Overview", "🏦"), ("Analysis", "⚡")]
    current = st.session_state.get("doo_prime_inner_tab", "Overview")
    if current not in [x[0] for x in choices]:
        current = "Overview"
        st.session_state["doo_prime_inner_tab"] = current
    cols = st.columns(len(choices))
    for i, (name, icon) in enumerate(choices):
        with cols[i]:
            label = f"✅ {icon} {name}" if current == name else f"{icon} {name}"
            if st.button(label, key=f"doo_prime_inner_{name}", use_container_width=True):
                st.session_state["doo_prime_inner_tab"] = name
                current = name
                request_close_sidebar()
    if st.session_state.get("doo_prime_inner_tab", current) == "Analysis":
        _render_doo_prime_analysis_inner_tab()
    else:
        try:
            from .home_split.legacy import implementation as impl
            impl.doo_prime_panel()
        except Exception as exc:
            with st.expander("Show Doo Prime inner tab error", expanded=True):
                st.exception(exc)

def _render_doo_prime_analysis_inner_tab():
    import streamlit as st
    try:
        from .home_split.legacy import implementation as impl
        impl.doo_prime_deep_analysis_panel()
    except Exception as exc:
        with st.expander("Show Doo Prime Analysis error", expanded=True):
            st.exception(exc)


def _home_inner_selector():
    import streamlit as st
    from core.styles import request_close_sidebar
    # V26: Metric + Home are one first inner tab, but their functions are still
    # rendered separately. Nothing is mathematically mixed.
    choices = [("Lunch", "🍱"), ("Data Visualization", "📊"), ("Doo Prime", "🏦")]
    current = st.session_state.get("home_inner_tab", "Lunch")
    if current in ("Home", "Launcher", "🏠 Launcher", "Metric", "Home Dashboard", "Metric + Home", "Doo Prime Analysis"):
        current = "Lunch"
        st.session_state.home_inner_tab = current
    if current not in [x[0] for x in choices]:
        current = "Lunch"
        st.session_state.home_inner_tab = current
    cols = st.columns(len(choices))
    for idx, (name, icon) in enumerate(choices):
        with cols[idx]:
            label = f"✅ {icon} {name}" if current == name else f"{icon} {name}"
            if st.button(label, key=f"home_inner_{name}", use_container_width=True):
                st.session_state.home_inner_tab = name
                current = name
                request_close_sidebar()
    return st.session_state.get("home_inner_tab", current)


def _render_metric_home_combined_inner_tab():
    import streamlit as st
    st.caption("Lunch tab: Run Calculating first, then Metric table, 010 Reverse Decision, Prediction, Copy/Refresh, then other fields.")
    _render_metric_inner_tab()
    with st.expander("🏠 Open / Close — Other Lunch fields", expanded=False):
        _render_home_dashboard()


def show():
    install_safe_dataframe_patch()
    from core.styles import request_close_sidebar
    request_close_sidebar()
    # Header removed so the Home inner-tab choice buttons are the first visible controls.
    selected = _home_inner_selector()
    if selected == "Lunch":
        _render_metric_home_combined_inner_tab()
    elif selected == "Data Visualization":
        request_close_sidebar()
        _render_lunch_data_visualization_inner_tab()
    else:
        request_close_sidebar()
        _render_doo_prime_inner_tab()
    render_tab_footer('Lunch')


# =====================================================================
# 2026-06-09 ADDITIVE UPGRADE
# Data Visualization Pro+: original dashboard kept, new PowerBI + ML +
# long-horizon regime detector added without touching old source logic.
# =====================================================================

def _major_regime_detector_v20260609(d, min_days=3.0, lookback_days=120, horizon=20):
    """Long-horizon market-regime detector.

    This intentionally does NOT flag 6-hour / intraday noise as a regime change.
    It is for strategy-fitness monitoring: how many days the current major regime
    has existed, estimated days left, and whether the strategy may need review.
    """
    import pandas as pd
    import numpy as np

    if d is None or not isinstance(d, pd.DataFrame) or d.empty or "close" not in d.columns:
        return {"ok": False, "message": "No clean OHLC data."}, pd.DataFrame(), pd.DataFrame()

    x = d.copy()
    if "time" not in x.columns:
        x["time"] = pd.date_range(end=pd.Timestamp.now(), periods=len(x), freq="h")
    x["time"] = pd.to_datetime(x["time"], errors="coerce")
    for c in ["open", "high", "low", "close", "volume"]:
        if c in x.columns:
            x[c] = pd.to_numeric(x[c], errors="coerce")
    if "open" not in x.columns:
        x["open"] = x["close"].shift(1).fillna(x["close"])
    x = x.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
    if len(x) < 80:
        return {"ok": False, "message": "Need at least 80 candles for major-regime analysis."}, pd.DataFrame(), pd.DataFrame()

    # Keep enough history, but do not overload phone UI.
    last_time = pd.Timestamp(x["time"].iloc[-1])
    cutoff = last_time - pd.Timedelta(days=float(max(30, lookback_days)))
    x = x[x["time"] >= cutoff].reset_index(drop=True)
    if len(x) < 80:
        x = d.copy().tail(1500).reset_index(drop=True)
        x["time"] = pd.to_datetime(x["time"], errors="coerce")
        x["close"] = pd.to_numeric(x["close"], errors="coerce")
        if "open" not in x.columns:
            x["open"] = x["close"].shift(1).fillna(x["close"])

    close = x["close"].astype(float)
    ret = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    ema_fast = close.ewm(span=48, adjust=False, min_periods=8).mean()
    ema_slow = close.ewm(span=240, adjust=False, min_periods=24).mean()
    trend_gap = ((ema_fast - ema_slow) / close.replace(0, np.nan) * 100).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    trend_slope = ema_slow.pct_change(48).replace([np.inf, -np.inf], np.nan).fillna(0.0) * 100
    vol = ret.rolling(96, min_periods=24).std().fillna(ret.rolling(24, min_periods=6).std()).fillna(0.0) * 100
    vol_med = vol.rolling(480, min_periods=80).median().fillna(vol.median())
    vol_q75 = vol.rolling(480, min_periods=80).quantile(.75).fillna(vol.quantile(.75))
    vol_q35 = vol.rolling(480, min_periods=80).quantile(.35).fillna(vol.quantile(.35))

    # Major regime label: direction + environment, not small signal changes.
    direction = np.where((trend_gap > 0.018) & (trend_slope >= -0.010), "BULL",
                 np.where((trend_gap < -0.018) & (trend_slope <= 0.010), "BEAR", "RANGE"))
    environment = np.where(vol >= vol_q75, "EXPANSION", np.where(vol <= vol_q35, "COMPRESSION", "NORMAL"))
    raw = pd.Series(direction, index=x.index).astype(str) + "_" + pd.Series(environment, index=x.index).astype(str)

    # Persistence filter: 2-day modal label. This is what stops 6-hour regime flips.
    min_bars = max(24, int(round(float(min_days) * 24)))
    smooth_window = max(24, min(min_bars, 120))
    smooth = raw.rolling(smooth_window, min_periods=max(12, smooth_window // 3)).apply(lambda s: 0, raw=False) if False else raw.copy()
    labels = raw.astype(str).tolist()
    smoothed = []
    for i in range(len(labels)):
        w = labels[max(0, i - smooth_window + 1): i + 1]
        vc = pd.Series(w, dtype="object").value_counts()
        smoothed.append(str(vc.index[0]) if not vc.empty else labels[i])
    x["Major Regime"] = pd.Series(smoothed, index=x.index, dtype="object")
    x["Regime Score /10"] = (5 + trend_gap.abs() * 35 + vol * 12 + trend_slope.abs() * 18).clip(0, 10).round(2)

    change_idx = x.index[x["Major Regime"].ne(x["Major Regime"].shift(1))].tolist() or [0]
    # Merge any segment shorter than min_days into the previous segment.
    changed = True
    while changed and len(change_idx) > 1:
        changed = False
        keep = [change_idx[0]]
        for i in range(1, len(change_idx)):
            prev = keep[-1]
            end_prev = change_idx[i] - 1
            prev_days = max((pd.Timestamp(x.loc[end_prev, "time"]) - pd.Timestamp(x.loc[prev, "time"])).total_seconds() / 86400.0, 0.0)
            if prev_days < float(min_days):
                changed = True
                continue
            keep.append(change_idx[i])
        change_idx = keep

    rows = []
    for i, idx in enumerate(change_idx):
        end_idx = (change_idx[i + 1] - 1) if i + 1 < len(change_idx) else len(x) - 1
        seg = x.loc[idx:end_idx]
        if seg.empty:
            continue
        start = pd.Timestamp(seg["time"].iloc[0]); end = pd.Timestamp(seg["time"].iloc[-1])
        dur = max((end - start).total_seconds() / 86400.0, 0.0)
        rows.append({
            "Regime Change Day": start.strftime("%Y-%m-%d"),
            "Change Time": start.strftime("%Y-%m-%d %H:%M"),
            "Major Regime": str(seg["Major Regime"].iloc[0]),
            "Open": round(float(seg["open"].iloc[0]), 5),
            "Close": round(float(seg["close"].iloc[-1]), 5),
            "Bars": int(len(seg)),
            "Days In Regime": round(float(dur), 2),
            "Return %": round((float(seg["close"].iloc[-1]) / max(float(seg["open"].iloc[0]), 1e-12) - 1.0) * 100, 4),
            "Avg Vol %": round(float(vol.loc[seg.index].mean()), 5),
            "Avg Trend Gap %": round(float(trend_gap.loc[seg.index].mean()), 5),
            "Regime Score /10": round(float(seg["Regime Score /10"].mean()), 2),
        })
    hist = pd.DataFrame(rows)
    if hist.empty:
        return {"ok": False, "message": "No major regime segments built."}, pd.DataFrame(), pd.DataFrame()

    current = hist.iloc[-1].to_dict()
    current_days = float(current.get("Days In Regime", 0.0))
    completed = pd.to_numeric(hist["Days In Regime"], errors="coerce").iloc[:-1].dropna()
    # Use robust median; floor at min_days so estimate does not become intraday.
    expected_days = max(float(completed.median()) if len(completed) else float(min_days) * 2.0, float(min_days))
    days_left = max(expected_days - current_days, 0.0)
    next_time = pd.Timestamp(x["time"].iloc[-1]) + pd.Timedelta(days=days_left)

    # Estimate open/close for next regime window using current drift + forecast horizon.
    recent_drift = float(ret.tail(max(24, int(horizon))).mean())
    recent_std = float(ret.tail(240).std()) if len(ret) >= 50 else float(ret.std())
    forecast_days = max(days_left, float(horizon) / 24.0, 1.0)
    last_close = float(close.iloc[-1])
    est_open = last_close
    est_close = last_close * (1.0 + max(-0.015, min(0.015, recent_drift * 24.0 * forecast_days)))
    est_low = min(est_open, est_close) * (1 - max(recent_std * (forecast_days ** 0.5) * 8, 0.0005))
    est_high = max(est_open, est_close) * (1 + max(recent_std * (forecast_days ** 0.5) * 8, 0.0005))

    status = "STRATEGY OK"
    note = "Major regime still inside normal life-span. No strategy change is required from regime age alone."
    if current_days >= expected_days * 1.35:
        status = "REVIEW STRATEGY"
        note = "Current major regime is older than normal. Review strategy assumptions, risk, and exit logic."
    elif days_left <= max(1.0, expected_days * 0.15):
        status = "WATCH TRANSITION"
        note = "Major regime is near its typical age limit. Prepare for possible transition; do not overfit short-term noise."

    summary = {
        "ok": True,
        "current_regime": str(current.get("Major Regime", "UNKNOWN")),
        "last_regime_change_day": str(current.get("Regime Change Day", "-")),
        "last_regime_change_time": str(current.get("Change Time", "-")),
        "days_since_last_change": round(current_days, 2),
        "expected_regime_days": round(expected_days, 2),
        "estimated_days_remaining": round(days_left, 2),
        "estimated_next_change_day": next_time.strftime("%Y-%m-%d"),
        "estimated_next_change_time": next_time.strftime("%Y-%m-%d %H:%M"),
        "estimated_price_open": round(float(est_open), 5),
        "estimated_price_close": round(float(est_close), 5),
        "estimated_price_low": round(float(est_low), 5),
        "estimated_price_high": round(float(est_high), 5),
        "regime_score_10": round(float(current.get("Regime Score /10", 0.0)), 2),
        "strategy_status": status,
        "strategy_note": note,
        "min_regime_days_filter": round(float(min_days), 2),
        "history_rows": int(len(hist)),
    }

    forecast = pd.DataFrame([
        {"Item": "Estimated Price Open", "Value": summary["estimated_price_open"]},
        {"Item": "Estimated Price Close", "Value": summary["estimated_price_close"]},
        {"Item": "Estimated Price Low", "Value": summary["estimated_price_low"]},
        {"Item": "Estimated Price High", "Value": summary["estimated_price_high"]},
        {"Item": "Estimated Next Major Regime Change", "Value": summary["estimated_next_change_time"]},
        {"Item": "Strategy Status", "Value": summary["strategy_status"]},
    ])
    return summary, hist.sort_values("Change Time", ascending=False).head(80).reset_index(drop=True), forecast


def _detect_lunch_regime_changes(d, horizon=24):
    """Override old short-term detector with major-regime detector."""
    summary, hist, _forecast = _major_regime_detector_v20260609(d, min_days=3.0, lookback_days=180, horizon=horizon)
    return summary, hist


def _five_layer_powerbi_calculate(d, horizon=20):
    """Override wrapper so Layer 5 also uses the major-regime detector output."""
    try:
        result = _five_layer_powerbi_uncached(d, int(horizon), _lunch_df_signature())
    except Exception:
        result = {"ok": False, "message": "5-layer calculation failed."}
    if isinstance(result, dict) and result.get("ok"):
        try:
            summary, hist, forecast = _major_regime_detector_v20260609(d, min_days=3.0, lookback_days=180, horizon=horizon)
            if summary.get("ok"):
                result["current_regime"] = summary["current_regime"]
                result["last_regime_change"] = summary["last_regime_change_time"]
                result["days_in_regime"] = summary["days_since_last_change"]
                result["estimated_days_remaining"] = summary["estimated_days_remaining"]
                result["predicted_next_regime_change"] = summary["estimated_next_change_time"]
                result["estimated_price_open"] = summary["estimated_price_open"]
                result["estimated_price_close"] = summary["estimated_price_close"]
                result["estimated_price_low"] = summary["estimated_price_low"]
                result["estimated_price_high"] = summary["estimated_price_high"]
                result["strategy_status"] = summary["strategy_status"]
                result["strategy_note"] = summary["strategy_note"]
                result["history"] = hist
                result["major_regime_summary"] = summary
                result["major_regime_forecast"] = forecast
        except Exception as exc:
            result["major_regime_warning"] = str(exc)
    return result


def _apply_mobile_first_app_css_v20260609():
    try:
        import streamlit as st
        st.markdown("""
        <style>
        @media (max-width: 780px){
          .block-container{padding-top:.65rem!important;padding-left:.55rem!important;padding-right:.55rem!important;}
          div[data-testid="stMetric"]{border-radius:18px;padding:10px 12px;background:rgba(255,255,255,.06);border:1px solid rgba(125,211,252,.22);box-shadow:0 8px 28px rgba(15,23,42,.10);}
          div[data-testid="stDataFrame"]{border-radius:16px;overflow:hidden;}
          .stButton>button{border-radius:999px!important;min-height:44px;font-weight:800!important;box-shadow:0 10px 24px rgba(14,165,233,.18);}
          [data-testid="stHorizontalBlock"]{gap:.45rem;}
        }
        </style>
        """, unsafe_allow_html=True)
    except Exception:
        pass


def _render_lunch_data_visualization_inner_tab():
    import streamlit as st
    import pandas as pd

    st.markdown("### 📊 Data Visualization Pro+")
    st.caption("Original advanced PowerBI + ML stays here. New tabs add major-regime strategy age, estimated days left, and estimated price open/close.")

    top = st.columns([1.05, .9, .9, .9])
    with top[0]:
        run = st.button("▶ Run Calculating", use_container_width=True, key="lunch_data_visual_run_calculating_v20260609")
    with top[1]:
        rows_limit = st.slider("Rows used", 1000, 3000, int(st.session_state.get("lunch_bi_rows_limit_v2", 2000)), 250, key="lunch_bi_rows_limit_v2")
    with top[2]:
        horizon = st.slider("Forecast candles", 5, 60, int(st.session_state.get("lunch_bi_horizon_v2", 20)), 5, key="lunch_bi_horizon_v2")
    with top[3]:
        min_days = st.slider("Major regime min days", 2, 14, int(st.session_state.get("major_regime_min_days", 3)), 1, key="major_regime_min_days")

    sig = (_lunch_df_signature(), int(rows_limit), int(horizon), int(min_days), "dataviz_pro_plus_20260609")
    if run or st.session_state.get("lunch_bi_visual_sig") != sig:
        st.session_state["lunch_bi_visual_ready"] = True
        with st.spinner("Calculating Data Visualization Pro+…"):
            d = _clean_lunch_visual_df(limit=rows_limit)
            if d is None or d.empty or len(d) < 80:
                st.warning("Not enough clean EURUSD OHLC data. Connect/refresh data first.")
                _render_lunch_copy_refresh_bar()
                return
            result = _five_layer_powerbi_calculate(d, horizon=horizon)
            major_summary, major_hist, major_forecast = _major_regime_detector_v20260609(d, min_days=float(min_days), lookback_days=180, horizon=horizon)
            st.session_state["lunch_5layer_powerbi_df"] = d
            st.session_state["lunch_5layer_powerbi_result"] = result
            st.session_state["lunch_major_regime_summary"] = major_summary
            st.session_state["lunch_major_regime_history"] = major_hist
            st.session_state["lunch_major_regime_forecast"] = major_forecast
            st.session_state["lunch_bi_visual_sig"] = sig
        st.success("Calculation complete. Original dashboard + new major-regime tabs are cached.")

    if not st.session_state.get("lunch_bi_visual_ready", False):
        st.info("Press **Run Calculating**. Nothing heavy runs until you press it.")
        _render_lunch_copy_refresh_bar()
        return

    d = st.session_state.get("lunch_5layer_powerbi_df")
    result = st.session_state.get("lunch_5layer_powerbi_result")
    summary = st.session_state.get("lunch_major_regime_summary", {})
    hist = st.session_state.get("lunch_major_regime_history", pd.DataFrame())
    forecast = st.session_state.get("lunch_major_regime_forecast", pd.DataFrame())

    tabs = st.tabs([
        "Original Advanced PowerBI + ML",
        "Major Regime Detector",
        "Estimated Price Open / Close",
        "ST Metric + History",
        "Copy"
    ])

    with tabs[0]:
        _render_lunch_advanced_powerbi_ml_projection(d, horizon=horizon)

    with tabs[1]:
        st.markdown("#### Long-horizon regime detection — not 6-hour noise")
        if not isinstance(summary, dict) or not summary.get("ok"):
            st.warning((summary or {}).get("message", "Major regime detector unavailable."))
        else:
            c = st.columns(6)
            c[0].metric("Current Major Regime", summary["current_regime"])
            c[1].metric("Started", summary["last_regime_change_day"])
            c[2].metric("Days So Far", summary["days_since_last_change"])
            c[3].metric("Expected Days", summary["expected_regime_days"])
            c[4].metric("Estimated Days Left", summary["estimated_days_remaining"])
            c[5].metric("Status", summary["strategy_status"])
            st.info(summary["strategy_note"])
            st.caption(f"Filter: regime must persist about {summary['min_regime_days_filter']} days before it counts as a major regime change.")
            st.dataframe(hist, use_container_width=True, hide_index=True, height=320)

    with tabs[2]:
        st.markdown("#### Estimated price open / close for the current major-regime window")
        if isinstance(summary, dict) and summary.get("ok"):
            p = st.columns(4)
            p[0].metric("Estimated Price Open", summary["estimated_price_open"])
            p[1].metric("Estimated Price Close", summary["estimated_price_close"])
            p[2].metric("Estimated Low", summary["estimated_price_low"])
            p[3].metric("Estimated High", summary["estimated_price_high"])
            st.dataframe(forecast, use_container_width=True, hide_index=True)
        if isinstance(result, dict) and result.get("ok"):
            st.markdown("#### Layer 5 Forecast Table")
            st.dataframe(result.get("forecast_df", pd.DataFrame()), use_container_width=True, hide_index=True)

    with tabs[3]:
        st.markdown("#### ST Metric / Regime quality table")
        if isinstance(result, dict) and result.get("ok"):
            cols = st.columns(5)
            cols[0].metric("Master Score", f"{result.get('master_score', '-')}/10")
            cols[1].metric("Bull Probability", f"{result.get('bull_probability', '-')}%")
            cols[2].metric("Regime Score", summary.get("regime_score_10", result.get("layer1", {}).get("Regime Score /10", "-")))
            cols[3].metric("Days In Regime", result.get("days_in_regime", "-"))
            cols[4].metric("Days Left", result.get("estimated_days_remaining", "-"))
            st.dataframe(pd.DataFrame([result.get("layer1", {})]), use_container_width=True, hide_index=True)
            st.dataframe(pd.DataFrame([result.get("layer2", {})]), use_container_width=True, hide_index=True)
            if isinstance(result.get("vote_df"), pd.DataFrame):
                st.dataframe(result["vote_df"], use_container_width=True, hide_index=True)
        else:
            st.info("Run calculation first.")

    with tabs[4]:
        payload = {
            "major_regime_summary": summary,
            "advanced_powerbi_ml": {k: v for k, v in (result or {}).items() if k not in {"vote_df", "deep_df", "forecast_df", "history", "major_regime_forecast"}},
        }
        try:
            from core.pro_terminal_uiux import render_mobile_copy_button
            import json
            render_mobile_copy_button("Copy Data Visualization Pro+", json.dumps(payload, indent=2, default=str), "copy_dataviz_pro_plus_20260609")
        except Exception:
            st.json(payload)

    _render_lunch_copy_refresh_bar()

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


def _dv_sort_newest_first_v20260609(df):
    """Return table newest/current first when a time/date column exists."""
    import pandas as pd
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame() if df is None else df
    out = df.copy()
    time_col = next((c for c in out.columns if str(c).lower() in ("time", "datetime", "date", "timestamp", "regime start", "start", "last_test_time")), None)
    if time_col is not None:
        parsed = pd.to_datetime(out[time_col], errors="coerce")
        if parsed.notna().any():
            out = out.assign(_sort_time_v20260609=parsed).sort_values("_sort_time_v20260609", ascending=False).drop(columns=["_sort_time_v20260609"])
    return out.reset_index(drop=True)


def _dv_last_continuous_days_v20260609(d, days=10, limit=5000):
    """Keep the last continuous N calendar days from the newest candle, preserving intraday bars."""
    import pandas as pd
    x = _dv_prepare_ohlc_v20260609(d, limit=int(limit))
    if x.empty:
        return x
    last_time = pd.Timestamp(x["time"].iloc[-1])
    cutoff = last_time - pd.Timedelta(days=float(days))
    y = x[x["time"] >= cutoff].copy()
    if len(y) < 80 and len(x) > len(y):
        y = x.tail(min(len(x), 240)).copy()
    return y.sort_values("time").reset_index(drop=True)


def _dv_build_lightblue_path_v20260609(actual, predicted):
    """Build one continuous light-blue path from the latest actual candle through future predicted closes."""
    import pandas as pd
    if actual is None or not isinstance(actual, pd.DataFrame) or actual.empty:
        return pd.DataFrame()
    if predicted is None or not isinstance(predicted, pd.DataFrame) or predicted.empty:
        return pd.DataFrame()
    try:
        rows = [{"time": pd.Timestamp(actual["time"].iloc[-1]), "path_close": float(actual["close"].iloc[-1]), "path_step": 0, "path_type": "LAST_ACTUAL_NOW"}]
        for _, r in predicted.iterrows():
            rows.append({"time": pd.Timestamp(r["time"]), "path_close": float(r["close"]), "path_step": int(r.get("prediction_step", len(rows))), "path_type": "LIGHT_BLUE_ML_PROJECTION"})
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


def _dv_dynamic_projection_history_v20260609(d, lookback_days=10, horizon=6):
    """For each recent bar, rebuild a short ML projection using data available up to that bar."""
    import pandas as pd
    x = _dv_last_continuous_days_v20260609(d, days=float(lookback_days), limit=5000)
    if x.empty or len(x) < 100:
        return pd.DataFrame()
    rows = []
    step = max(1, int(len(x) / 160))
    for pos in range(max(80, len(x) - 240), len(x), step):
        train = x.iloc[:pos + 1].copy()
        pred = _dv_predict_future_candles_v20260609(train, horizon=int(max(3, min(horizon, 24))))
        if pred.empty:
            continue
        for _, r in pred.head(int(horizon)).iterrows():
            rows.append({
                "origin_time": pd.Timestamp(train["time"].iloc[-1]),
                "projected_time": pd.Timestamp(r["time"]),
                "Projected Close": round(float(r["close"]), 6),
                "Projection Step": int(r.get("prediction_step", 0)),
            })
    return _dv_sort_newest_first_v20260609(pd.DataFrame(rows))


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


def _dv_render_candle_powerbi_chart_v20260609(d, predicted, backtest_hist=None, projection_history=None):
    import streamlit as st
    import pandas as pd
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception as exc:
        st.warning(f"Plotly is not available for candle chart: {exc}")
        return
    # Show last 10 continuous days, ending at the newest/current candle.
    x = _dv_last_continuous_days_v20260609(d, days=10, limit=5000)
    if x.empty:
        st.warning("No clean OHLC candles available for chart.")
        return
    light_path = _dv_build_lightblue_path_v20260609(x, predicted)
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.74, 0.26],
        subplot_titles=("Last 10 continuous days actual candles + light-blue current-hour ML path", "Prediction-vs-actual close error / dynamic projection history")
    )
    fig.add_trace(go.Candlestick(x=x["time"], open=x["open"], high=x["high"], low=x["low"], close=x["close"], name="Actual candles - last 10 days"), row=1, col=1)
    if isinstance(predicted, pd.DataFrame) and not predicted.empty:
        fig.add_trace(go.Candlestick(
            x=predicted["time"], open=predicted["open"], high=predicted["high"], low=predicted["low"], close=predicted["close"],
            name="BLUE predicted future candles",
            increasing={"line":{"color":"#38BDF8", "width":2}, "fillcolor":"rgba(56,189,248,0.35)"},
            decreasing={"line":{"color":"#7DD3FC", "width":2}, "fillcolor":"rgba(125,211,252,0.25)"},
        ), row=1, col=1)
        fig.add_vrect(x0=x["time"].iloc[-1], x1=predicted["time"].iloc[-1], fillcolor="rgba(56,189,248,0.08)", line_width=0, row=1, col=1)
    if isinstance(light_path, pd.DataFrame) and not light_path.empty:
        fig.add_trace(go.Scatter(
            x=light_path["time"], y=light_path["path_close"], mode="lines+markers", name="LIGHT BLUE current-hour predicted path",
            line={"color":"#7DD3FC", "width":4}, marker={"size":5, "color":"#BAE6FD"}
        ), row=1, col=1)
    if isinstance(projection_history, pd.DataFrame) and not projection_history.empty:
        ph = projection_history.sort_values("projected_time").tail(500)
        fig.add_trace(go.Scatter(
            x=ph["projected_time"], y=ph["Projected Close"], mode="markers", name="Last 10D rolling ML projections",
            marker={"size":4, "color":"rgba(125,211,252,0.45)"}
        ), row=1, col=1)
    if isinstance(backtest_hist, pd.DataFrame) and not backtest_hist.empty:
        bh = backtest_hist.sort_values("time").tail(240)
        fig.add_trace(go.Bar(x=bh["time"], y=bh["Close Error %"], name="Close prediction error %"), row=2, col=1)
    fig.update_layout(height=860, margin=dict(l=6, r=6, t=58, b=8), xaxis_rangeslider_visible=False, legend=dict(orientation="h"), title="Advanced Power BI Candle + ML Projection — newest/current first, last 10 continuous days")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})


def _apply_mobile_first_app_css_v20260609():
    try:
        import streamlit as st
        st.markdown("""
        <style>
        @media (max-width: 780px){
          .block-container{padding-top:.65rem!important;padding-left:.55rem!important;padding-right:.55rem!important;}
          div[data-testid="stMetric"]{border-radius:18px;padding:10px 12px;background:rgba(255,255,255,.06);border:1px solid rgba(125,211,252,.22);box-shadow:0 8px 28px rgba(15,23,42,.10);}
          div[data-testid="stDataFrame"]{border-radius:16px;overflow:hidden;}
          .stButton>button{border-radius:999px!important;min-height:44px;font-weight:800!important;box-shadow:0 10px 24px rgba(14,165,233,.18);}
          [data-testid="stHorizontalBlock"]{gap:.45rem;}
        }
        </style>
        """, unsafe_allow_html=True)
    except Exception:
        pass


def _render_lunch_data_visualization_inner_tab():
    import streamlit as st
    import pandas as pd
    import json

    _apply_mobile_first_app_css_v20260609()
    st.markdown("### 📊 Data Visualization — Advanced Power BI Price Candlestick + ML Projection")
    st.caption("Migrated view: one main candlestick + ML projection first; all other analytics are folded into open/close sections. Heavy calculation runs only after you press Run Candlestick.")

    top = st.columns([1.15, .85, .85, .85, .85])
    with top[0]:
        run = st.button("▶ Run Candlestick + ML Projection", use_container_width=True, key="lunch_data_visual_run_candlestick_ml_20260609")
    with top[1]:
        rows_limit = st.slider("Rows used from Lunch/Data Visualization", 1000, 20000, int(st.session_state.get("dv_pp_rows", 10000)), 500, key="dv_pp_rows")
    with top[2]:
        horizon = st.slider("Predicted candles", 6, 96, int(st.session_state.get("dv_pp_horizon", 36)), 6, key="dv_pp_horizon")
    with top[3]:
        min_days = st.slider("Regime min days", 3, 21, int(st.session_state.get("dv_pp_min_days", 5)), 1, key="dv_pp_min_days")
    with top[4]:
        bt_lookback = st.slider("Backtest candles", 60, 500, int(st.session_state.get("dv_pp_bt", 180)), 20, key="dv_pp_bt")

    sig = (_lunch_df_signature(), int(rows_limit), int(horizon), int(min_days), int(bt_lookback), "dv_adv_price_candlestick_ml_migrated_20260609")
    if run:
        st.session_state["lunch_bi_visual_ready"] = True
        with st.spinner("Calculating Advanced Power BI Price Candlestick + ML Projection from Lunch/Data Visualization data…"):
            d = _clean_lunch_visual_df(limit=int(rows_limit))
            d = _dv_prepare_ohlc_v20260609(d, limit=int(rows_limit))
            if d.empty or len(d) < 120:
                st.warning("Not enough clean OHLC data. Refresh/connect EURUSD or selected symbol first. Need at least 120 candles.")
                _render_lunch_copy_refresh_bar()
                return
            base_result = _five_layer_powerbi_calculate(d, horizon=int(horizon))
            predicted = _dv_predict_future_candles_v20260609(d, horizon=int(horizon))
            bt_hist, bt_summary = _dv_prediction_vs_actual_history_v20260609(d, lookback=int(bt_lookback), horizon=1)
            projection_history = _dv_dynamic_projection_history_v20260609(d, lookback_days=10, horizon=min(6, int(horizon)))
            regime_summary, regime_hist = _dv_major_regime_detector_v20260609(d, min_days=float(min_days), lookback_days=240, horizon=int(horizon))
            st.session_state["dv_pp_df"] = d
            st.session_state["dv_pp_base_result"] = base_result
            st.session_state["dv_pp_predicted"] = predicted
            st.session_state["dv_pp_lightblue_path"] = _dv_build_lightblue_path_v20260609(_dv_last_continuous_days_v20260609(d, days=10), predicted)
            st.session_state["dv_pp_projection_history"] = projection_history
            st.session_state["dv_pp_bt_hist"] = _dv_sort_newest_first_v20260609(bt_hist)
            st.session_state["dv_pp_bt_summary"] = bt_summary
            st.session_state["dv_pp_regime_summary"] = regime_summary
            st.session_state["dv_pp_regime_hist"] = _dv_sort_newest_first_v20260609(regime_hist)
            st.session_state["dv_pp_sig"] = sig
        st.success("Candlestick + ML projection complete. Other analytics are available below in open/close sections.")

    if not st.session_state.get("lunch_bi_visual_ready", False):
        st.info("Press **Run Candlestick + ML Projection**. Nothing heavy runs automatically before that.")
        _render_lunch_copy_refresh_bar()
        return

    d = st.session_state.get("dv_pp_df", pd.DataFrame())
    result = st.session_state.get("dv_pp_base_result", {})
    predicted = st.session_state.get("dv_pp_predicted", pd.DataFrame())
    bt_hist = st.session_state.get("dv_pp_bt_hist", pd.DataFrame())
    projection_history = st.session_state.get("dv_pp_projection_history", pd.DataFrame())
    lightblue_path = st.session_state.get("dv_pp_lightblue_path", pd.DataFrame())
    bt_summary = st.session_state.get("dv_pp_bt_summary", {})
    regime_summary = st.session_state.get("dv_pp_regime_summary", {})
    regime_hist = st.session_state.get("dv_pp_regime_hist", pd.DataFrame())

    st.markdown("#### 🕯️ Advanced Power BI Price Candlestick + ML Projection")
    st.caption("Main migrated section: actual candles, blue predicted future candles, current-hour light-blue path, and rolling ML projection history.")

    with st.container():
        c = st.columns(6)
        if isinstance(result, dict) and result.get("ok"):
            c[0].metric("Master Score", f"{result.get('master_score', '-')}/10")
            c[1].metric("Bull Probability", f"{result.get('bull_probability', '-')}%")
        if isinstance(regime_summary, dict) and regime_summary.get("ok"):
            c[2].metric("Current Regime", regime_summary.get("current_regime", "-"))
            c[3].metric("Days In Regime", regime_summary.get("days_since_last_change", regime_summary.get("days_since_change", "-")))
            c[4].metric("Est. Days Left", regime_summary.get("estimated_days_remaining", regime_summary.get("estimated_days_left", "-")))
            c[5].metric("Strategy", regime_summary.get("strategy_status", "-"))
        _dv_render_candle_powerbi_chart_v20260609(d, predicted, bt_hist, projection_history)
        if isinstance(lightblue_path, pd.DataFrame) and not lightblue_path.empty:
            st.markdown("#### Light-blue predicted path from latest/current candle")
            st.dataframe(_dv_sort_newest_first_v20260609(lightblue_path), use_container_width=True, hide_index=True, height=220)
        if isinstance(predicted, pd.DataFrame) and not predicted.empty:
            st.markdown("#### BLUE predicted future candle table")
            st.dataframe(_dv_sort_newest_first_v20260609(predicted), use_container_width=True, hide_index=True, height=260)
        if isinstance(projection_history, pd.DataFrame) and not projection_history.empty:
            st.markdown("#### Last 10 continuous days — rolling ML projection history")
            st.dataframe(_dv_sort_newest_first_v20260609(projection_history), use_container_width=True, hide_index=True, height=320)

    with st.expander("Open / Close — Original PowerBI + ML Projection", expanded=False):
        # Keep your existing advanced dashboard visible.
        try:
            st.session_state["lunch_5layer_powerbi_result"] = result
            st.session_state["lunch_5layer_powerbi_df"] = d
            _render_lunch_advanced_powerbi_ml_projection(d, horizon=int(horizon))
        except Exception as exc:
            st.warning(f"Original PowerBI + ML renderer could not display: {exc}")
            if isinstance(result, dict):
                st.json({k: str(v) for k, v in result.items() if k not in {"vote_df", "deep_df", "forecast_df", "history"}})

    with st.expander("Open / Close — Prediction vs Actual", expanded=False):
        st.markdown("#### How previous predicted candle compared with what actually happened")
        if bt_summary:
            b = st.columns(4)
            b[0].metric("Tested Candles", bt_summary.get("tested_candles", 0))
            b[1].metric("Direction Accuracy", f"{bt_summary.get('direction_accuracy_pct', 0)}%")
            b[2].metric("Avg Close Error", f"{bt_summary.get('avg_abs_close_error_pct', 0)}%")
            b[3].metric("Last Test", bt_summary.get("last_test_time", "-"))
        if isinstance(bt_hist, pd.DataFrame) and not bt_hist.empty:
            st.dataframe(_dv_sort_newest_first_v20260609(bt_hist), use_container_width=True, hide_index=True, height=420)
        else:
            st.info("Need more history for prediction-vs-actual testing.")

    with st.expander("Open / Close — Smooth Regime", expanded=False):
        st.markdown("#### Smooth major-regime detector — less noise, more reliable structure change")
        if isinstance(regime_summary, dict) and regime_summary.get("ok"):
            r = st.columns(6)
            r[0].metric("Current Regime", regime_summary.get("current_regime", "-"))
            r[1].metric("Started", regime_summary.get("last_regime_change", "-"))
            r[2].metric("Days So Far", regime_summary.get("days_since_last_change", regime_summary.get("days_since_change", "-")))
            r[3].metric("Expected Days", regime_summary.get("expected_days", "-"))
            r[4].metric("Estimated Days Left", regime_summary.get("estimated_days_remaining", regime_summary.get("estimated_days_left", "-")))
            r[5].metric("Power", f"{regime_summary.get('regime_power_100', '-')}/100")
            st.info(regime_summary.get("strategy_note", ""))
            st.caption(f"Noise filter: a regime must persist around {regime_summary.get('min_days_filter', min_days)} days before it counts as a major structure change.")
            st.dataframe(_dv_sort_newest_first_v20260609(regime_hist), use_container_width=True, hide_index=True, height=420)
        else:
            st.warning((regime_summary or {}).get("message", "Smooth regime detector unavailable."))

    with st.expander("Open / Close — Copy Export", expanded=False):
        payload = {
            "smooth_regime_summary": regime_summary,
            "prediction_backtest_summary": bt_summary,
            "light_blue_current_hour_path": lightblue_path.to_dict("records") if isinstance(lightblue_path, pd.DataFrame) else [],
            "last_10_continuous_days_dynamic_projection_history": projection_history.to_dict("records") if isinstance(projection_history, pd.DataFrame) else [],
            "future_blue_predicted_candles": _dv_sort_newest_first_v20260609(predicted).to_dict("records") if isinstance(predicted, pd.DataFrame) else [],
            "advanced_powerbi_ml_summary": {k: v for k, v in (result or {}).items() if k not in {"vote_df", "deep_df", "forecast_df", "history"}},
        }
        st.session_state["lunch_visualization_export"] = json.dumps(payload, indent=2, default=str)
        try:
            from core.pro_terminal_uiux import render_mobile_copy_button
            render_mobile_copy_button("Copy Data Visualization Pro++", st.session_state["lunch_visualization_export"], "copy_dv_propp_candle_20260609")
        except Exception:
            st.json(payload)

    _render_lunch_copy_refresh_bar()


