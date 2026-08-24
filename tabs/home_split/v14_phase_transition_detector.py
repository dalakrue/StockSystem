"""2026-06-04 V14 Phase Transition Detector for Home + Finder.

Goal:
- Keep the old 10-Reversal Decision intact.
- Add an EARLIER market-structure detector that looks for:
  strong trend -> momentum fading -> impulse compression -> accumulation/distribution
  -> breakout preparation -> possible one-way expansion 2-3 hours later.
- Causal/no-future: every hourly row uses only data up to that closed hour.
- Works inside the existing V13 locked Home/Finder tables by adding columns.
"""
from __future__ import annotations


def install(g: dict) -> None:
    import math
    import pandas as pd
    import streamlit as st

    base_scan = g.get("_scan_reversal_history_table")
    base_home_banner = g.get("render_reversal_home_banner")

    def _num(v, default=0.0):
        try:
            x = float(v)
            if math.isnan(x) or math.isinf(x):
                return default
            return x
        except Exception:
            return default

    def _first_col(df, names):
        if df is None or not isinstance(df, pd.DataFrame):
            return None
        low = {str(c).lower(): c for c in df.columns}
        for n in names:
            if n in df.columns:
                return n
            if str(n).lower() in low:
                return low[str(n).lower()]
        return None

    def _norm(df):
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame()
        out = df.copy()
        tcol = _first_col(out, ["time", "datetime", "date", "timestamp", "Time", "Datetime", "Date", "Timestamp"])
        ccol = _first_col(out, ["close", "Close", "price", "Price", "bid", "Bid", "last", "Last"])
        if tcol is None or ccol is None:
            return pd.DataFrame()
        out["time"] = pd.to_datetime(out[tcol], errors="coerce")
        out["close"] = pd.to_numeric(out[ccol], errors="coerce")
        ocol = _first_col(out, ["open", "Open"])
        hcol = _first_col(out, ["high", "High"])
        lcol = _first_col(out, ["low", "Low"])
        out["open"] = pd.to_numeric(out[ocol], errors="coerce") if ocol is not None else out["close"].shift(1).fillna(out["close"])
        out["high"] = pd.to_numeric(out[hcol], errors="coerce") if hcol is not None else out[["open", "close"]].max(axis=1)
        out["low"] = pd.to_numeric(out[lcol], errors="coerce") if lcol is not None else out[["open", "close"]].min(axis=1)
        out = out.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates(subset=["time"], keep="last")
        out["body"] = (out["close"] - out["open"]).abs()
        out["range"] = (out["high"] - out["low"]).abs()
        out["direction"] = out.apply(lambda r: "BUY" if _num(r["close"]) > _num(r["open"]) else ("SELL" if _num(r["close"]) < _num(r["open"]) else "FLAT"), axis=1)
        return out.reset_index(drop=True)

    def _efficiency(prices) -> float:
        s = pd.Series(prices).dropna().astype(float)
        if len(s) < 3:
            return 0.0
        net = abs(s.iloc[-1] - s.iloc[0])
        path = s.diff().abs().sum()
        return float(net / max(path, 1e-12) * 100.0)

    def _window(data, end, hours):
        end = pd.Timestamp(end)
        start = end - pd.Timedelta(hours=hours)
        return data[(data["time"] >= start) & (data["time"] < end)].copy()

    def _hour(data, h):
        h = pd.Timestamp(h)
        return data[(data["time"] >= h) & (data["time"] < h + pd.Timedelta(hours=1))].copy()

    def _safe_ratio(a, b, default=1.0):
        b = abs(_num(b))
        if b <= 1e-12:
            return default
        return float(_num(a) / b)

    def _phase_label(score: int) -> str:
        if score >= 10:
            return "TRANSITION ZONE"
        if score >= 8:
            return "BREAKOUT PREPARATION"
        if score >= 6:
            return "ACCUMULATION / DISTRIBUTION"
        if score >= 4:
            return "MOMENTUM LOSS"
        return "NORMAL TREND"

    def _phase_for_hour(data: pd.DataFrame, h) -> dict:
        data = _norm(data)
        if data.empty:
            return {}
        h = pd.Timestamp(h)
        cur = _hour(data, h)
        prev1 = _window(data, h, 1)
        prev3 = _window(data, h, 3)
        prev6 = _window(data, h, 6)
        context = data[data["time"] < h + pd.Timedelta(hours=1)].tail(480).copy()
        if cur.empty or prev1.empty or len(prev3) < 5:
            return {
                "phase_transition_score": 0,
                "phase_transition_state": "NEED MORE DATA",
                "expected_expansion_window": "N/A",
                "phase_reasons": "not enough closed-hour context",
            }

        prev_close = _num(prev3["close"].iloc[0])
        last_prev_close = _num(prev3["close"].iloc[-1])
        cur_first = _num(cur["close"].iloc[0])
        cur_last = _num(cur["close"].iloc[-1])
        trend_move = abs(last_prev_close - prev_close)
        trend_move_pct = trend_move / max(abs(prev_close), 1e-12) * 100.0
        cur_move = abs(cur_last - cur_first)
        cur_move_pct = cur_move / max(abs(cur_first), 1e-12) * 100.0

        prev_body = _num(prev3["body"].mean())
        cur_body = _num(cur["body"].mean())
        prev_range = _num(prev3["range"].mean())
        cur_range = _num(cur["range"].mean())
        body_ratio = _safe_ratio(cur_body, prev_body)
        range_ratio = _safe_ratio(cur_range, prev_range)

        eff_prev = _efficiency(prev3["close"])
        eff_cur = _efficiency(cur["close"])
        eff_delta = eff_cur - eff_prev
        trend_dir = "BUY" if last_prev_close > prev_close else "SELL" if last_prev_close < prev_close else "FLAT"

        # Adaptive threshold: works for XAUUSD and forex because it uses recent median movement.
        recent_range_med = _num(context["range"].tail(240).median())
        strong_trend = bool(trend_move >= max(recent_range_med * 8.0, abs(prev_close) * 0.00035) or eff_prev >= 55)

        trend_exhaustion = bool(strong_trend and (body_ratio <= 0.72 or range_ratio <= 0.78 or eff_delta <= -12))
        impulse_compression = bool(body_ratio <= 0.55 or (range_ratio <= 0.62 and cur_move <= trend_move * 0.45))

        cur_high, cur_low = _num(cur["high"].max()), _num(cur["low"].min())
        prev_high, prev_low = _num(prev3["high"].max()), _num(prev3["low"].min())
        inside_prior_range = bool(cur_high <= prev_high and cur_low >= prev_low)
        range_narrow = bool(range_ratio <= 0.75)
        mixed_candles = bool(cur["direction"].nunique() >= 2)
        accumulation_distribution = bool(strong_trend and range_narrow and (inside_prior_range or mixed_candles) and body_ratio <= 0.80)

        buy_pressure = (cur_last - cur_low) / max(cur_high - cur_low, 1e-12) * 100.0 if cur_high > cur_low else 50.0
        sell_pressure = (cur_high - cur_last) / max(cur_high - cur_low, 1e-12) * 100.0 if cur_high > cur_low else 50.0
        pressure_side = "BUY" if buy_pressure >= sell_pressure else "SELL"
        pressure_gap = abs(buy_pressure - sell_pressure)
        breakout_pressure = bool(range_narrow and pressure_gap >= 22 and cur_move <= trend_move * 0.70)

        # Order-block proxy: previous impulse origin retest + wick/body rejection in current hour.
        impulse = prev1 if len(prev1) >= 3 else prev3.tail(20)
        impulse_dir = "BUY" if _num(impulse["close"].iloc[-1]) > _num(impulse["open"].iloc[0]) else "SELL"
        origin_low, origin_high = _num(impulse["low"].iloc[0]), _num(impulse["high"].iloc[0])
        retest_origin = bool(cur_low <= origin_high and cur_high >= origin_low)
        lower_wick = (cur[["open", "close"]].min(axis=1) - cur["low"]).clip(lower=0).mean()
        upper_wick = (cur["high"] - cur[["open", "close"]].max(axis=1)).clip(lower=0).mean()
        wick_reject = bool((impulse_dir == "BUY" and lower_wick >= max(cur_body * 0.85, recent_range_med * 0.15)) or (impulse_dir == "SELL" and upper_wick >= max(cur_body * 0.85, recent_range_med * 0.15)))
        order_block_rejection = bool(retest_origin and wick_reject)

        # Late-breakout filter: if expansion already happened in this hour, cap it.
        breakout_already_happened = bool(cur_move >= max(trend_move * 0.75, recent_range_med * 10.0) and range_ratio >= 1.15 and eff_cur >= max(55, eff_prev - 5))

        score = 0
        reasons = []
        if trend_exhaustion:
            score += 2; reasons.append("trend exhaustion")
        if impulse_compression:
            score += 2; reasons.append("impulse compression")
        if accumulation_distribution:
            score += 3; reasons.append("accumulation/distribution")
        if breakout_pressure:
            score += 3; reasons.append(f"breakout pressure {pressure_side}")
        if order_block_rejection:
            score += 2; reasons.append("order block rejection")
        raw_score = int(min(10, score))
        capped_score = min(raw_score, 6) if breakout_already_happened else raw_score
        if breakout_already_happened:
            reasons.append("late breakout filter capped score")

        expected = "2-3 hours" if capped_score >= 8 else "1-4 hours watch" if capped_score >= 6 else "not ready"
        return {
            "phase_transition_score": int(capped_score),
            "phase_transition_raw": int(raw_score),
            "phase_transition_state": _phase_label(int(capped_score)),
            "expected_expansion_window": expected,
            "phase_trend_before": "YES" if strong_trend else "NO",
            "trend_exhaustion": "YES" if trend_exhaustion else "NO",
            "impulse_compression": "YES" if impulse_compression else "NO",
            "accumulation_distribution": "YES" if accumulation_distribution else "NO",
            "breakout_pressure": "YES" if breakout_pressure else "NO",
            "breakout_pressure_side": pressure_side,
            "order_block_rejection": "YES" if order_block_rejection else "NO",
            "breakout_already_happened": "YES" if breakout_already_happened else "NO",
            "body_compression_ratio": round(body_ratio, 3),
            "range_compression_ratio": round(range_ratio, 3),
            "efficiency_prev_%": round(eff_prev, 2),
            "efficiency_now_%": round(eff_cur, 2),
            "efficiency_delta": round(eff_delta, 2),
            "trend_move_%": round(trend_move_pct, 5),
            "current_hour_move_%": round(cur_move_pct, 5),
            "phase_reasons": " | ".join(reasons[:8]) if reasons else "normal / no transition structure",
            "phase_no_future": "YES",
        }

    def _add_phase_columns(scan: pd.DataFrame, source_df=None) -> pd.DataFrame:
        if not isinstance(scan, pd.DataFrame) or scan.empty:
            return scan
        data = _norm(source_df)
        if data.empty:
            # Try current session data as fallback, without forcing any connector call.
            for key in ["doo_model_candles", "shared_df", "market_df", "df", "data"]:
                cand = st.session_state.get(key)
                data = _norm(cand)
                if not data.empty:
                    break
        if data.empty:
            return scan
        out = scan.copy()
        phase_rows = []
        for _, r in out.iterrows():
            try:
                h = pd.Timestamp(str(r.get("date")) + " " + str(r.get("hour", "00:00")))
                phase_rows.append(_phase_for_hour(data, h))
            except Exception:
                phase_rows.append({})
        phase = pd.DataFrame(phase_rows)
        if phase.empty:
            return out
        for c in phase.columns:
            out[c] = phase[c].values
        return out

    def _scan_with_phase(df=None, days=25, selected_date=None):
        if not callable(base_scan):
            return pd.DataFrame(), []
        scan, engines = base_scan(df=df, days=days, selected_date=selected_date)
        scan2 = _add_phase_columns(scan, source_df=df)
        if isinstance(scan2, pd.DataFrame) and not scan2.empty:
            try:
                st.session_state["home_reversal_25d_scan"] = scan2
                prep = scan2[pd.to_numeric(scan2.get("phase_transition_score", 0), errors="coerce").fillna(0) >= 8].copy()
                st.session_state["phase_transition_8plus_scan"] = prep
            except Exception:
                pass
        return scan2, engines

    def _render_phase_current_summary():
        scan = st.session_state.get("home_reversal_25d_scan")
        if not isinstance(scan, pd.DataFrame) or scan.empty or "phase_transition_score" not in scan.columns:
            return
        tmp = scan.copy()
        tmp["_phase_score"] = pd.to_numeric(tmp.get("phase_transition_score", 0), errors="coerce").fillna(0).astype(int)
        prep = tmp[tmp["_phase_score"] >= 8].copy()
        today = pd.Timestamp.now().strftime("%Y-%m-%d")
        today_prep = prep[prep.get("date", "").astype(str).eq(today)] if not prep.empty and "date" in prep.columns else pd.DataFrame()
        with st.expander("🧭 Open / Close Phase Transition Detector — early breakout preparation", expanded=True):
            st.caption("This is NOT the old reversal detector. It searches for trend exhaustion + compression + accumulation/distribution before a new one-way expansion. Causal/no-future columns only.")
            c = st.columns(4)
            c[0].metric("8+/10 Prep Rows", int(len(prep)))
            c[1].metric("Today Prep Rows", int(len(today_prep)))
            if not prep.empty:
                best = prep.sort_values(["_phase_score", "weighted_score" if "weighted_score" in prep.columns else "_phase_score"], ascending=[False, False]).iloc[0]
                c[2].metric("Best Prep Hour", f"{best.get('date')} {best.get('hour')}", best.get("phase_transition_state", ""))
                c[3].metric("Expected Expansion", str(best.get("expected_expansion_window", "-")), f"{int(best.get('_phase_score', 0))}/10")
                show_cols = [x for x in ["date", "hour", "phase_transition_score", "phase_transition_state", "expected_expansion_window", "breakout_pressure_side", "trend_exhaustion", "impulse_compression", "accumulation_distribution", "breakout_pressure", "order_block_rejection", "breakout_already_happened", "phase_reasons"] if x in prep.columns]
                st.dataframe(prep[show_cols].drop(columns=["_phase_score"], errors="ignore"), use_container_width=True, hide_index=True)
            else:
                c[2].metric("Best Prep Hour", "None", "need structure")
                c[3].metric("Expected Expansion", "Not ready", "0/10")

    def _home_banner_with_phase(*args, **kwargs):
        if callable(base_home_banner):
            base_home_banner(*args, **kwargs)
        _render_phase_current_summary()

    g["_scan_reversal_history_table"] = _scan_with_phase
    g["render_reversal_home_banner"] = _home_banner_with_phase
