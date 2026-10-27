"""2026-06-03 V4 reversal cooldown + quality compression upgrade.

Non-destructive wrapper for Home/Finder 10-point reversal decisions.
Adds:
1) 4-hour cooldown after a 7+/10 signal
2) trend-before-reversal gate
3) minimum move quality gate
4) reversal persistence proxy
5) exhaustion quality score 0-100
6) consecutive signal compression into zones
Also adds light caching wrappers for Finder/Doo modeling so inner tabs open faster.
"""
from __future__ import annotations


def install(g: dict) -> None:
    import math
    import time
    import pandas as pd
    import streamlit as st

    base_eval = g.get("_evaluate_reversal_driver_from_values")
    base_scan = g.get("_scan_reversal_history_table")
    base_render_home = g.get("render_reversal_home_banner")
    base_render_finder = g.get("_render_doo_finder")
    base_collect = g.get("_collect_doo_model_candles")
    base_features = g.get("_add_simple_model_features")

    def _num(v, default=0.0):
        try:
            x = float(v)
            if math.isnan(x) or math.isinf(x):
                return default
            return x
        except Exception:
            return default

    def _pip_like_move(before, after):
        # Works for percent snapshots and for XAUUSD-like price deltas when close is available.
        bm = abs(_num((before or {}).get("move_%")))
        am = abs(_num((after or {}).get("move_%")))
        dm = abs(am - bm)
        return max(am, bm, dm)

    def _v4_quality_overlay(engine: dict) -> dict:
        if not isinstance(engine, dict):
            return engine
        out = dict(engine)
        before = out.get("before", {}) or {}
        after = out.get("after", {}) or {}

        raw_active = int(_num(out.get("raw_active_count", out.get("active_count", 0)), 0))
        active = int(_num(out.get("active_count", 0), 0))
        weighted = float(_num(out.get("weighted_score", 0), 0))

        adx_before = max(abs(_num(before.get("adx"))), abs(_num(before.get("adx_%"))))
        dve_before = abs(_num(before.get("dve_%")))
        falling_before = abs(_num(before.get("falling_eff_%")))
        rising_before = abs(_num(before.get("rising_eff_%")))
        bbuy = _num(before.get("buy_%"))
        bsell = _num(before.get("sell_%"))
        abuy = _num(after.get("buy_%"))
        asell = _num(after.get("sell_%"))
        atrust = _num(after.get("trust_%"))
        afat = abs(_num(after.get("fat_tail_z")))
        ak = abs(_num(after.get("kurtosis")))
        amove_abs = abs(_num(after.get("move_%")))
        dmove_abs = abs(_num((out.get("deltas") or {}).get("move_%")))

        # Upgrade #2: no prior trend => no true reversal.
        old_side_dominance = max(bbuy, bsell)
        trend_before_reversal = bool(
            adx_before > 25
            or dve_before > 40
            or falling_before > 40
            or rising_before > 40
            or old_side_dominance >= 58
        )

        # Upgrade #3: move quality. ATR is usually unavailable in snapshot, so use percent/pip proxy.
        # For XAUUSD M1/H1, 0.25%-0.35% is already a meaningful displacement; tiny moves are demoted.
        move_proxy = max(amove_abs, dmove_abs, _pip_like_move(before, after))
        minimum_future_move_ok = bool(move_proxy >= 0.25 or amove_abs >= 0.35 or dmove_abs >= 0.35 or afat >= 1.25)

        # Upgrade #4: persistence proxy from after-window participation/trust. If raw candles exist elsewhere,
        # the before/after snapshots already summarize the next block, so this is fast and stable.
        after_side = "BUY" if abuy >= asell else "SELL"
        next_3_candles_same_direction_proxy = bool(
            max(abuy, asell) >= 52
            or (after_side == "BUY" and abuy - bbuy >= 4)
            or (after_side == "SELL" and asell - bsell >= 4)
            or atrust >= 60
        )

        # Upgrade #5: exhaustion score 0-100.
        pressure_weakening = bool(out.get("pressure_transfer") or out.get("trend_exhaustion") or abs((out.get("deltas") or {}).get("sell_weakness_%", 0)) >= 3)
        dve_collapse_or_rotation = bool(out.get("flow_confirm") or abs(_num((out.get("deltas") or {}).get("dve_%"))) >= 6)
        atr_or_tail_expansion = bool(out.get("shock_move") or afat >= 1.25 or ak >= 3.0)
        exhaustion_score = 0.0
        exhaustion_score += 20 if trend_before_reversal else 0
        exhaustion_score += 22 if pressure_weakening else 0
        exhaustion_score += 18 if dve_collapse_or_rotation else 0
        exhaustion_score += 20 if atr_or_tail_expansion else 0
        exhaustion_score += 10 if out.get("tail_confirm") else 0
        exhaustion_score += 10 if out.get("model_confirm") else 0
        exhaustion_score = round(max(0, min(100, exhaustion_score)), 2)

        block_reasons = []
        if not trend_before_reversal:
            block_reasons.append("no trend before reversal")
        if not minimum_future_move_ok:
            block_reasons.append("future/move quality below minimum")
        if not next_3_candles_same_direction_proxy:
            block_reasons.append("no 3-candle persistence proxy")
        if active >= 8 and exhaustion_score < 70:
            block_reasons.append("exhaustion score below 70 for 8+/10")

        # Requested scoring behavior.
        if active >= 7 and not trend_before_reversal:
            active = min(active, 6)
            weighted = min(weighted, 64.0)
        if active >= 7 and not minimum_future_move_ok:
            active = max(0, active - 2)
            weighted = min(weighted, 68.0)
        if active >= 7 and not next_3_candles_same_direction_proxy:
            active = min(active, 6)
            weighted = min(weighted, 64.0)
        if active >= 8 and exhaustion_score < 70:
            active = 7 if exhaustion_score >= 60 else 6
            weighted = min(weighted, 74.0 if active == 7 else 64.0)

        # If all V4 confirmations are strong, keep or promote a true raw signal.
        v4_full_quality = bool(
            raw_active >= 7
            and trend_before_reversal
            and minimum_future_move_ok
            and next_3_candles_same_direction_proxy
            and exhaustion_score >= 70
            and not out.get("strict_noise_block", False)
        )
        if v4_full_quality and active >= 7:
            weighted = max(weighted, 72.0)

        status = "EXTREME" if active >= 9 else ("DANGER" if active >= 7 else ("WARNING" if active >= 5 else "NORMAL"))
        title = "EXTREME REVERSAL DANGER" if active >= 9 else ("IMPORTANT REVERSAL DANGER" if active >= 7 else ("EARLY REVERSAL WARNING" if active >= 5 else "NORMAL / NO STRONG REVERSAL"))

        out.update({
            "active_count": int(active),
            "probability_pct": int(round(active * 10)),
            "weighted_score": round(max(0.0, min(100.0, weighted)), 2),
            "status": status,
            "title": title,
            "v4_quality_gate": "PASS" if v4_full_quality else ("WATCH" if active >= 5 else "BLOCK"),
            "v4_block_reasons": block_reasons,
            "trend_before_reversal": bool(trend_before_reversal),
            "minimum_future_move_ok": bool(minimum_future_move_ok),
            "reversal_persistence_ok": bool(next_3_candles_same_direction_proxy),
            "exhaustion_score": float(exhaustion_score),
            "cooldown_rule": "After one 7+/10 signal, following 4 hours are blocked in history/Finder scan.",
        })
        if block_reasons and active < 7:
            out["noise_filter"] = "V4 BLOCKED: " + ", ".join(block_reasons[:3])
        elif v4_full_quality:
            out["noise_filter"] = "PASS: V4 trend + move + persistence + exhaustion quality confirmed"
        return out

    def _quality_eval(before, after):
        if not callable(base_eval):
            return {}
        return _v4_quality_overlay(base_eval(before, after))

    def _compress_reversal_zones(scan: pd.DataFrame, cooldown_hours: int = 4) -> pd.DataFrame:
        if not isinstance(scan, pd.DataFrame) or scan.empty:
            return scan
        df = scan.copy()
        if "date" not in df.columns or "hour" not in df.columns:
            return df
        times = pd.to_datetime(df["date"].astype(str) + " " + df["hour"].astype(str), errors="coerce")
        df["signal_time"] = times
        score_col = "10_reverse_decision" if "10_reverse_decision" in df.columns else "score"
        scores = pd.to_numeric(df.get(score_col, 0), errors="coerce").fillna(0).astype(int)
        df["cooldown_blocked"] = "NO"
        df["compressed_zone"] = ""
        df["zone_peak_score"] = scores
        df["count_as_reversal"] = df.get("7_out_of_10_found", "NO")
        last_fire = None
        zone_start = None
        zone_peak = 0
        zone_rows = []
        for idx, (ts, score) in enumerate(zip(df["signal_time"], scores)):
            if pd.isna(ts) or score < 7:
                continue
            if last_fire is not None and ts < last_fire + pd.Timedelta(hours=cooldown_hours):
                df.at[idx, "cooldown_blocked"] = "YES"
                df.at[idx, "7_out_of_10_found"] = "BLOCKED"
                df.at[idx, "count_as_reversal"] = "NO"
                zone_peak = max(zone_peak, int(score))
                zone_rows.append(idx)
                continue
            # finalize previous zone labels
            if zone_rows and zone_start is not None:
                z_end = df.at[zone_rows[-1], "signal_time"]
                label = f"{zone_start.strftime('%Y-%m-%d %H:00')}–{z_end.strftime('%H:00')} REVERSAL ZONE"
                for r in zone_rows:
                    df.at[r, "compressed_zone"] = label
                    df.at[r, "zone_peak_score"] = zone_peak
            last_fire = ts
            zone_start = ts
            zone_peak = int(score)
            zone_rows = [idx]
            df.at[idx, "count_as_reversal"] = "YES"
        if zone_rows and zone_start is not None:
            z_end = df.at[zone_rows[-1], "signal_time"]
            label = f"{zone_start.strftime('%Y-%m-%d %H:00')}–{z_end.strftime('%H:00')} REVERSAL ZONE"
            for r in zone_rows:
                df.at[r, "compressed_zone"] = label
                df.at[r, "zone_peak_score"] = zone_peak
        return df.drop(columns=["signal_time"], errors="ignore")

    def _quality_scan(*args, **kwargs):
        if not callable(base_scan):
            return pd.DataFrame(), []
        scan, engines = base_scan(*args, **kwargs)
        engines2 = [_v4_quality_overlay(e) for e in (engines or [])]
        if isinstance(scan, pd.DataFrame) and not scan.empty:
            # Rebuild score fields from V4 engines when row count aligns.
            if len(engines2) == len(scan):
                scan = scan.copy()
                scan["10_reverse_decision"] = [int(_num(e.get("active_count"), 0)) for e in engines2]
                scan["weighted_score"] = [float(_num(e.get("weighted_score"), 0)) for e in engines2]
                scan["7_out_of_10_found"] = ["YES" if int(_num(e.get("active_count"), 0)) >= 7 else "NO" for e in engines2]
                scan["exhaustion_score"] = [float(_num(e.get("exhaustion_score"), 0)) for e in engines2]
                scan["v4_quality_gate"] = [e.get("v4_quality_gate", "") for e in engines2]
                scan["v4_block_reasons"] = [", ".join(e.get("v4_block_reasons", [])[:2]) for e in engines2]
            scan = _compress_reversal_zones(scan, cooldown_hours=4)
            st.session_state["home_reversal_25d_scan"] = scan
        return scan, engines2

    def _fast_collect(results):
        # Cache by session results identity and last refresh timestamp. Keeps Finder inner tab snappy.
        cache_key = (id(results), str(st.session_state.get("doo_deep_last_refresh", "")), str(st.session_state.get("last_data_signature", "")))
        if st.session_state.get("doo_fast_collect_key") == cache_key:
            cached = st.session_state.get("doo_fast_collect_df")
            if isinstance(cached, pd.DataFrame):
                return cached.copy()
        if callable(base_collect):
            df = base_collect(results)
        else:
            df = pd.DataFrame()
        if isinstance(df, pd.DataFrame):
            st.session_state["doo_fast_collect_key"] = cache_key
            st.session_state["doo_fast_collect_df"] = df.copy()
        return df

    def _fast_features(df):
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame()
        try:
            sig = (len(df), str(df.get("time", pd.Series()).iloc[-1]) if "time" in df.columns and len(df) else "", tuple(df.columns))
            if st.session_state.get("doo_fast_features_key") == sig:
                cached = st.session_state.get("doo_fast_features_df")
                if isinstance(cached, pd.DataFrame):
                    return cached.copy()
        except Exception:
            sig = None
        out = base_features(df) if callable(base_features) else df.copy()
        if isinstance(out, pd.DataFrame) and sig is not None:
            st.session_state["doo_fast_features_key"] = sig
            st.session_state["doo_fast_features_df"] = out.copy()
        return out

    def _render_home_with_v4_note(*args, **kwargs):
        if callable(base_render_home):
            base_render_home(*args, **kwargs)
        with st.expander("🧊 Open V4 cooldown / compression rule", expanded=False):
            st.write("A 7+/10 reversal now starts a 4-hour cooldown zone. Repeated 7+/10 rows inside that zone are counted as one reversal zone, not many separate signals.")
            st.write("Full 8+/10 requires trend-before, minimum move quality, persistence, and exhaustion score ≥70.")

    def _render_finder_fast(results):
        start = time.time()
        if callable(base_render_finder):
            base_render_finder(results)
        elapsed = time.time() - start
        if elapsed > 1.5:
            st.caption(f"Finder optimized cache active. Last render calculation: {elapsed:.2f}s")

    g["_evaluate_reversal_driver_from_values"] = _quality_eval
    g["_scan_reversal_history_table"] = _quality_scan
    g["_collect_doo_model_candles"] = _fast_collect
    g["_add_simple_model_features"] = _fast_features
    g["render_reversal_home_banner"] = _render_home_with_v4_note
    g["_render_doo_finder"] = _render_finder_fast
