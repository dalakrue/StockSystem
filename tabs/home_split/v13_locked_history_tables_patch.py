"""2026-06-04 V13 locked table display patch.

User intent:
- Do NOT remove the 25-day history table.
- Do NOT remove today's all-hours reversal table.
- "Locked" means anti-repaint: once an hour row is calculated after that hour
  is closed, that row is stored and reused so future refreshes do not rewrite it.
- Home and Finder both show open/close fields with 8/10+ rows and full rows.
"""
from __future__ import annotations


def install(g: dict) -> None:
    import math
    from pathlib import Path
    import pandas as pd
    import streamlit as st

    base_scan = g.get("_scan_reversal_history_table")
    eval_latest = g.get("evaluate_latest_reversal_engine")
    render_panel = g.get("_render_reversal_engine_panel")
    threshold_table = g.get("_threshold_table_from_engine")
    collect_candles = g.get("_collect_doo_model_candles")
    add_features = g.get("_add_simple_model_features")
    metric_table_fn = g.get("_finder_metric_table")
    filtered_results_fn = g.get("_finder_filtered_results")
    duplicate_warning_fn = g.get("_finder_duplicate_frame_warning")
    copy_button_html = g.get("_copy_button_html")
    render_basket_model = g.get("_render_finder_basket_model")

    LOCK_VERSION = "V13_LOCKED_TABLE_NO_REPAINT"

    def _num(v, default=0.0):
        try:
            x = float(v)
            if math.isnan(x) or math.isinf(x):
                return default
            return x
        except Exception:
            return default

    def _cache_path() -> Path:
        try:
            root = Path(__file__).resolve().parents[2]
            p = root / "data" / "reversal_locked_v13.csv"
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            return Path("data/reversal_locked_v13.csv")

    def _market_key() -> str:
        # Keep broad enough to prevent cross-symbol pollution, but safe if keys are absent.
        symbol = st.session_state.get("symbol") or st.session_state.get("doo_symbol") or st.session_state.get("selected_symbol") or "UNKNOWN"
        tf = st.session_state.get("timeframe") or st.session_state.get("doo_timeframe") or st.session_state.get("selected_timeframe") or "MIXED"
        return f"{symbol}|{tf}|{LOCK_VERSION}"

    def _read_cache() -> pd.DataFrame:
        p = _cache_path()
        if not p.exists():
            return pd.DataFrame()
        try:
            df = pd.read_csv(p)
            return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    def _write_cache(df: pd.DataFrame) -> None:
        try:
            p = _cache_path()
            keep_cols = list(dict.fromkeys(list(df.columns)))
            df = df[keep_cols].copy()
            df.to_csv(p, index=False)
        except Exception:
            pass

    def _row_id_from_row(row: dict, market_key: str) -> str:
        return f"{market_key}|{row.get('date','')}|{row.get('hour','')}"

    def _locked_scan(df=None, days=25, selected_date=None):
        """Return scan table, but reuse stored rows for already-seen closed hours.

        This prevents repainting/rewriting old hourly values while still allowing
        new hours and new days to be appended into the Home/Finder tables.
        """
        if not callable(base_scan):
            return pd.DataFrame(), []
        raw, engines = base_scan(df=df, days=days, selected_date=selected_date)
        if not isinstance(raw, pd.DataFrame) or raw.empty:
            return raw, engines

        raw = raw.copy()
        # V16 display threshold: important locked reversal rows are 8/10+ (not 7/10+).
        # Keep any old 7_out_of_10_found column untouched for backward compatibility,
        # but use 8_out_of_10_found for Home/Finder visible tables.
        try:
            raw["_v16_score"] = raw.get("10_reverse_decision", "0/10").astype(str).str.extract(r"(\d+)").fillna(0).astype(int)
            raw["8_out_of_10_found"] = ["YES" if int(x) >= 8 else "NO" for x in raw["_v16_score"].tolist()]
            raw = raw.drop(columns=["_v16_score"], errors="ignore")
        except Exception:
            pass
        market_key = _market_key()
        raw["lock_version"] = LOCK_VERSION
        raw["market_key"] = market_key
        raw["locked_row_id"] = raw.apply(lambda r: _row_id_from_row(r.to_dict(), market_key), axis=1)
        raw["locked_status"] = "LOCKED_AFTER_HOUR_CLOSE"
        raw["used_future_rows"] = 0
        raw["locked_note"] = "Once saved, this hour is reused and not recalculated by future candles."

        cache = _read_cache()
        if not cache.empty and "locked_row_id" in cache.columns:
            cache_same = cache[(cache.get("market_key", "") == market_key) & (cache.get("lock_version", "") == LOCK_VERSION)].copy()
        else:
            cache_same = pd.DataFrame()

        out_rows = []
        cached_ids = set(cache_same["locked_row_id"].astype(str).tolist()) if not cache_same.empty else set()
        raw_ids = set(raw["locked_row_id"].astype(str).tolist())

        # For every currently loaded hour, prefer the cached locked row.
        for _, r in raw.iterrows():
            rid = str(r.get("locked_row_id"))
            if rid in cached_ids:
                old = cache_same[cache_same["locked_row_id"].astype(str) == rid].iloc[-1].to_dict()
                # preserve any new display columns without changing score columns
                merged = r.to_dict()
                for k, v in old.items():
                    merged[k] = v
                out_rows.append(merged)
            else:
                new = r.to_dict()
                new["locked_first_seen"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                out_rows.append(new)

        out = pd.DataFrame(out_rows)

        # Append only brand-new row IDs to persistent cache.
        new_rows = out[~out["locked_row_id"].astype(str).isin(cached_ids)].copy()
        if not new_rows.empty:
            if cache.empty:
                cache2 = new_rows.copy()
            else:
                cache2 = pd.concat([cache, new_rows], ignore_index=True, sort=False)
                cache2 = cache2.drop_duplicates(subset=["locked_row_id"], keep="first")
            _write_cache(cache2)

        if not out.empty:
            out = out.sort_values(["date", "hour"], ascending=[False, False]).reset_index(drop=True)
            # Keep the shared session state table for terminal UI summary.
            st.session_state["home_reversal_25d_scan"] = out
        return out, engines

    def _split_important(scan: pd.DataFrame):
        if not isinstance(scan, pd.DataFrame) or scan.empty:
            return pd.DataFrame(), pd.DataFrame()
        if "8_out_of_10_found" in scan.columns:
            exact = scan[scan.get("8_out_of_10_found", "NO").astype(str).str.upper().eq("YES")].copy()
        elif "10_reverse_decision" in scan.columns:
            score = scan["10_reverse_decision"].astype(str).str.extract(r"(\d+)").fillna(0).astype(int)[0]
            exact = scan[score >= 8].copy()
        else:
            exact = pd.DataFrame()
        today = pd.Timestamp.now().strftime("%Y-%m-%d")
        today_rows = scan[scan.get("date", "").astype(str).eq(today)].copy() if "date" in scan.columns else pd.DataFrame()
        return exact, today_rows

    def _display_locked_tables(scan: pd.DataFrame, title_prefix: str, show_today: bool = True):
        exact, today_rows = _split_important(scan)
        with st.expander(f"📋 Open / Close {title_prefix} — locked 8/10+ reversal rows", expanded=True):
            if exact.empty:
                st.info("No locked 8/10+ reversal rows in the currently loaded range yet. The full table below still shows all hours and lower warnings.")
            else:
                st.success(f"Locked 8/10+ rows found: {len(exact)}. These rows will not repaint after future refreshes.")
                st.dataframe(exact, use_container_width=True, hide_index=True)
        if show_today:
            with st.expander(f"📅 Open / Close {title_prefix} — all today reversal decisions", expanded=True):
                if today_rows.empty:
                    st.info("No loaded rows for today's date yet. Refresh/connect more candles to collect today's table.")
                else:
                    st.dataframe(today_rows, use_container_width=True, hide_index=True)
        with st.expander(f"🗂️ Open / Close {title_prefix} — full 25D hourly locked scan", expanded=False):
            if scan.empty:
                st.info("No hourly scan rows yet. Load more candles, then refresh.")
            else:
                st.caption("Full collection table. Old hour rows are read from the locked cache; new closed hours are appended.")
                st.dataframe(scan, use_container_width=True, hide_index=True)

    def render_reversal_home_banner():
        engine = eval_latest() if callable(eval_latest) else None
        if not engine:
            engine = st.session_state.get("last_reversal_engine")
        if not engine:
            return

        st.markdown("### 🚨 10-Reversal Decision — Locked History Tables")
        st.caption("Locked means: table values for finished hours do not change later. The 25D table and today's all-hours table still continue collecting new closed hours.")
        scan, engines = _locked_scan(days=25)
        exact, today_rows = _split_important(scan)
        best = None
        if isinstance(scan, pd.DataFrame) and not scan.empty:
            try:
                tmp = scan.copy()
                tmp["_score"] = tmp["10_reverse_decision"].astype(str).str.extract(r"(\d+)").fillna(0).astype(int)
                best = tmp.sort_values(["_score", "weighted_score"], ascending=[False, False]).iloc[0].to_dict()
            except Exception:
                best = scan.iloc[0].to_dict()

        c = st.columns(4)
        c[0].metric("Current Closed-Hour Score", f"{int(engine.get('active_count', 0))}/10", f"{int(engine.get('probability_pct', 0))}%")
        c[1].metric("Locked 8/10+ in 25D", int(len(exact)))
        c[2].metric("Today Rows", int(len(today_rows)))
        if best:
            c[3].metric("Best Locked Hour", f"{best.get('date')} {best.get('hour')}", best.get("10_reverse_decision", "-"))
        else:
            c[3].metric("Best Locked Hour", "Need data", "connect/refresh")

        _display_locked_tables(scan, "Home", show_today=True)

        if callable(threshold_table):
            with st.expander("📊 Open / Close current threshold table", expanded=False):
                try:
                    st.dataframe(threshold_table(engine), use_container_width=True, hide_index=True)
                except Exception:
                    pass
        if callable(render_panel):
            render_panel(engine, location="Home locked table engine")

    def _render_doo_finder(results):
        st.markdown("### 🔎 Finder — Locked Day 10-Reversal Table")
        st.caption("Finder keeps the day selector and shows every loaded hour for that day. Closed-hour rows are locked so future candles do not rewrite the old table values.")
        if not callable(collect_candles) or not callable(add_features):
            st.error("Finder dependencies are not loaded.")
            return
        data = add_features(collect_candles(results))
        if not isinstance(data, pd.DataFrame) or data.empty or "time" not in data.columns:
            st.warning("No modeling candles are loaded yet. Connect/read Doo Prime or press Refresh in Doo Prime Analysis first.")
            return
        data = data.copy()
        data["time"] = pd.to_datetime(data["time"], errors="coerce")
        data = data.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
        if data.empty:
            st.warning("No valid candle time rows are loaded.")
            return

        min_t, max_t = data["time"].min(), data["time"].max()
        st.caption(f"Available loaded range: {min_t.strftime('%Y-%m-%d %H:%M')} → {max_t.strftime('%Y-%m-%d %H:%M')} | rows: {len(data):,}")
        chosen_date = st.date_input("Choose day", value=max_t.date(), min_value=min_t.date(), max_value=max_t.date(), key="doo_finder_day_only_v13_locked")
        day_start = pd.Timestamp(chosen_date).normalize()
        day_end = day_start + pd.Timedelta(days=1)
        found_day = data[(data["time"] >= day_start) & (data["time"] < day_end)].copy()
        if found_day.empty:
            st.warning("No loaded candles for this day.")
            return

        scan, engines = _locked_scan(df=data, days=25, selected_date=chosen_date)
        if isinstance(scan, pd.DataFrame) and not scan.empty and "8_out_of_10_found" in scan.columns:
            exact = scan[scan.get("8_out_of_10_found", "NO").astype(str).str.upper().eq("YES")].copy()
        elif isinstance(scan, pd.DataFrame) and not scan.empty and "10_reverse_decision" in scan.columns:
            score = scan["10_reverse_decision"].astype(str).str.extract(r"(\d+)").fillna(0).astype(int)[0]
            exact = scan[score >= 8].copy()
        else:
            exact = pd.DataFrame()
        best_engine = None
        if engines:
            best_engine = sorted(engines, key=lambda e: (int(e.get("active_count", 0)), float(e.get("weighted_score", 0))), reverse=True)[0]

        first_close = _num(found_day["close"].iloc[0]) if "close" in found_day.columns else 0
        last_close = _num(found_day["close"].iloc[-1]) if "close" in found_day.columns else 0
        day_move = ((last_close / max(first_close, 1e-9)) - 1) * 100 if first_close else 0.0
        buy_candles = int((found_day.get("direction", pd.Series(dtype=str)).astype(str) == "BUY/UP").sum()) if "direction" in found_day.columns else 0
        sell_candles = int((found_day.get("direction", pd.Series(dtype=str)).astype(str) == "SELL/DOWN").sum()) if "direction" in found_day.columns else 0
        dominant = "BUY" if buy_candles > sell_candles else ("SELL" if sell_candles > buy_candles else "MIXED/FLAT")

        c = st.columns(6)
        c[0].metric("Selected Day", str(chosen_date))
        c[1].metric("Loaded Rows", int(len(found_day)))
        c[2].metric("Locked 8/10+ Hours", int(len(exact)))
        c[3].metric("Best Decision", "N/A" if not best_engine else f"{int(best_engine.get('active_count', 0))}/10", "" if not best_engine else best_engine.get("status", ""))
        c[4].metric("Day Move %", round(day_move, 5))
        c[5].metric("Dominant", dominant)

        with st.expander("📋 Open / Close Finder selected-day locked 8/10+ rows", expanded=True):
            if exact.empty:
                st.info("No 8/10+ reversal decision found for this selected day. Open the full hourly table below to see 1/10–6/10 warnings too.")
            else:
                st.error(f"Found {len(exact)} locked reversal danger hour(s) at 8/10 or higher for {chosen_date}.")
                st.dataframe(exact, use_container_width=True, hide_index=True)

        with st.expander("📅 Open / Close Finder selected-day ALL reversal decisions", expanded=True):
            if scan.empty:
                st.info("No hourly scan available for this day.")
            else:
                st.dataframe(scan, use_container_width=True, hide_index=True)

        if best_engine and callable(render_panel):
            st.markdown("### 🚨 Strongest 10-Point Reversal Decision For This Day")
            render_panel(best_engine, location="Finder locked strongest hour")
            if callable(threshold_table):
                with st.expander("📊 Open / Close threshold table for strongest Finder hour", expanded=False):
                    st.dataframe(threshold_table(best_engine), use_container_width=True, hide_index=True)

        selected_results, found = filtered_results_fn(data, day_start, day_end) if callable(filtered_results_fn) else ({}, found_day)
        metric_table = metric_table_fn(selected_results) if callable(metric_table_fn) else pd.DataFrame()
        duplicate_warning = duplicate_warning_fn(metric_table) if callable(duplicate_warning_fn) else ""
        if duplicate_warning:
            st.warning(duplicate_warning)
        with st.expander("📊 Open / Close same-as-Doo metric table for selected day", expanded=False):
            if metric_table.empty:
                st.info("No recalculated Doo metric table for this day.")
            else:
                st.dataframe(metric_table, use_container_width=True, hide_index=True)

        if callable(render_basket_model):
            render_basket_model(dominant)

        show_cols = [c for c in ["source_frame", "time", "open", "high", "low", "close", "volume", "body", "range", "return_pct", "direction", "upper_wick", "lower_wick", "reaction_note"] if c in found_day.columns]
        with st.expander("📈 Open / Close selected-day candle preview", expanded=False):
            st.dataframe(found_day[show_cols], use_container_width=True, hide_index=True)
            if "time" in found_day.columns and "close" in found_day.columns:
                try:
                    st.line_chart(found_day.set_index("time")["close"])
                except Exception:
                    pass

        payload = "DOO PRIME FINDER LOCKED DAY 10-REVERSAL DECISION EXPORT\n" + "=" * 64 + "\n"
        payload += f"selected_day: {chosen_date}\nstart: {day_start}\nend: {day_end}\nrows: {len(found_day)}\nday_move_pct: {round(day_move, 5)}\ndominant_reaction: {dominant}\nlocked_8_of_10_hours: {len(exact)}\n"
        if not exact.empty:
            payload += "\nLOCKED 8/10+ REVERSAL DECISIONS:\n" + exact.to_csv(index=False)
        if not scan.empty:
            payload += "\nLOCKED FULL DAY HOURLY 10-REVERSAL SCAN:\n" + scan.to_csv(index=False)
        if best_engine:
            payload += "\nSTRONGEST 10-POINT ENGINE:\n" + str({k: v for k, v in best_engine.items() if k != "drivers"}) + "\n"
            payload += "\nSTRONGEST DRIVER TABLE:\n" + pd.DataFrame(best_engine.get("drivers", [])).to_csv(index=False)
        if not metric_table.empty:
            payload += "\nSAME-AS-DOO DAY METRICS:\n" + metric_table.to_csv(index=False)
        if show_cols:
            payload += "\nDAY CANDLE FEATURES CSV:\n" + found_day[show_cols].to_csv(index=False)
        if callable(copy_button_html):
            copy_button_html("📋 Copy Finder Locked Day 10-Reversal Analysis", payload, key="doo_finder_day_copy_v13_locked")
        with st.expander("Fallback: open copy text", expanded=False):
            st.text_area("Finder locked day copy text", value=payload, height=240, key="doo_finder_day_copy_textarea_v13_locked")

    g["_scan_reversal_history_table"] = _locked_scan
    g["render_reversal_home_banner"] = render_reversal_home_banner
    g["_render_doo_finder"] = _render_doo_finder
