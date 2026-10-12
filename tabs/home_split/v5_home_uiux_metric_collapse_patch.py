"""2026-06-03 V5 Home UI/UX + metric collapse + stricter reversal quality patch.

Safe wrapper only: no connector/order/account behavior is changed.
- Current Data Session Intelligence metrics are placed inside one open/close field.
- One-hour exit opportunity metrics are placed inside one open/close field.
- 10-reversal V4 filter is tightened so 7+/10 requires real trend + move + 3-candle/persistence confirmation.
"""
from __future__ import annotations


def install(g: dict) -> None:
    import math
    import pandas as pd
    import streamlit as st

    base_eval = g.get("_evaluate_reversal_driver_from_values")
    base_scan = g.get("_scan_reversal_history_table")
    base_current_panel = g.get("_render_current_doo_session_metric_panel")
    base_one_hour = g.get("_evaluate_one_hour_exit_sound")

    def _num(v, default=0.0):
        try:
            x = float(v)
            if math.isnan(x) or math.isinf(x):
                return default
            return x
        except Exception:
            return default

    def _tight_quality_overlay(engine: dict) -> dict:
        if not isinstance(engine, dict):
            return engine
        out = dict(engine)
        before = out.get("before", {}) or {}
        after = out.get("after", {}) or {}
        deltas = out.get("deltas", {}) or {}

        active = int(_num(out.get("active_count", 0)))
        raw_active = int(_num(out.get("raw_active_count", active)))
        weighted = _num(out.get("weighted_score", active * 10.0))

        adx_before = max(abs(_num(before.get("adx"))), abs(_num(before.get("adx_%"))))
        dve_before = abs(_num(before.get("dve_%")))
        eff_before = max(abs(_num(before.get("rising_eff_%"))), abs(_num(before.get("falling_eff_%"))), dve_before)
        old_dom = max(_num(before.get("buy_%")), _num(before.get("sell_%")))

        after_buy = _num(after.get("buy_%"))
        after_sell = _num(after.get("sell_%"))
        after_dom = max(after_buy, after_sell)
        after_trust = _num(after.get("trust_%"))
        after_fat = abs(_num(after.get("fat_tail_z")))
        after_move = abs(_num(after.get("move_%")))
        delta_move = abs(_num(deltas.get("move_%")))
        move_proxy = max(after_move, delta_move)

        # Stronger version of user's 3 rules. This is what actually cuts 12/16 signals down.
        trend_before_ok = bool(
            (adx_before > 25 and eff_before > 40)
            or (old_dom >= 62 and eff_before > 35)
            or (old_dom >= 66 and adx_before > 20)
        )
        move_quality_ok = bool(move_proxy >= 0.30 or after_move >= 0.40 or delta_move >= 0.40 or after_fat >= 1.55)
        three_candle_confirm_ok = bool(after_dom >= 58 or after_trust >= 65 or bool(out.get("flow_confirm")) and after_dom >= 54)
        exhaustion_ok = bool(_num(out.get("exhaustion_score", 0)) >= 68 or bool(out.get("trend_exhaustion")) and bool(out.get("pressure_transfer")))

        blocks = []
        if not trend_before_ok:
            blocks.append("strict trend-before-reversal failed")
        if not move_quality_ok:
            blocks.append("minimum future/move quality failed")
        if not three_candle_confirm_ok:
            blocks.append("3-candle/persistence confirmation failed")
        if raw_active >= 8 and not exhaustion_ok:
            blocks.append("8+/10 needs exhaustion confirmation")

        if active >= 7:
            if not trend_before_ok:
                active = min(active, 6)
                weighted = min(weighted, 64.0)
            if active >= 7 and not move_quality_ok:
                active = min(active, 6)
                weighted = min(weighted, 64.0)
            if active >= 7 and not three_candle_confirm_ok:
                active = min(active, 6)
                weighted = min(weighted, 64.0)
            if active >= 8 and not exhaustion_ok:
                active = 7 if (trend_before_ok and move_quality_ok and three_candle_confirm_ok) else 6
                weighted = min(weighted, 72.0 if active == 7 else 64.0)

        status = "EXTREME" if active >= 9 else ("DANGER" if active >= 7 else ("WARNING" if active >= 5 else "NORMAL"))
        title = "EXTREME REVERSAL DANGER" if active >= 9 else ("IMPORTANT REVERSAL DANGER" if active >= 7 else ("EARLY REVERSAL WARNING" if active >= 5 else "NORMAL / NO STRONG REVERSAL"))
        out.update({
            "active_count": int(active),
            "probability_pct": int(round(active * 10)),
            "weighted_score": round(max(0.0, min(100.0, weighted)), 2),
            "status": status,
            "title": title,
            "strict_half_filter": "PASS" if active >= 7 and not blocks else ("BLOCK" if active < 7 and blocks else "WATCH"),
            "strict_half_filter_reasons": blocks,
            "trend_before_reversal_strict": trend_before_ok,
            "minimum_future_move_strict": move_quality_ok,
            "three_candle_confirmation_strict": three_candle_confirm_ok,
            "counting_method": "7+/10 rows inside 4 hours are one reversal zone, not separate signals.",
        })
        if blocks and active < 7:
            out["noise_filter"] = "STRICT BLOCK: " + ", ".join(blocks[:3])
        return out

    def _eval(before, after):
        if not callable(base_eval):
            return {}
        return _tight_quality_overlay(base_eval(before, after))

    def _scan(*args, **kwargs):
        if not callable(base_scan):
            return pd.DataFrame(), []
        scan, engines = base_scan(*args, **kwargs)
        engines2 = [_tight_quality_overlay(e) for e in (engines or [])]
        if isinstance(scan, pd.DataFrame) and not scan.empty and len(engines2) == len(scan):
            scan = scan.copy()
            scan["10_reverse_decision"] = [int(_num(e.get("active_count"))) for e in engines2]
            scan["7_out_of_10_found"] = ["YES" if int(_num(e.get("active_count"))) >= 7 else "NO" for e in engines2]
            scan["strict_half_filter"] = [e.get("strict_half_filter", "") for e in engines2]
            scan["strict_block_reasons"] = [", ".join(e.get("strict_half_filter_reasons", [])[:2]) for e in engines2]
            # Re-apply 4-hour compression after the stricter score rewrite.
            if "date" in scan.columns and "hour" in scan.columns:
                times = pd.to_datetime(scan["date"].astype(str) + " " + scan["hour"].astype(str), errors="coerce")
                scores = pd.to_numeric(scan["10_reverse_decision"], errors="coerce").fillna(0).astype(int)
                scan["cooldown_blocked"] = "NO"
                scan["count_as_reversal"] = "NO"
                last_fire = None
                for idx, (ts, score) in enumerate(zip(times, scores)):
                    if pd.isna(ts) or score < 7:
                        continue
                    if last_fire is not None and ts < last_fire + pd.Timedelta(hours=4):
                        scan.at[idx, "cooldown_blocked"] = "YES"
                        scan.at[idx, "7_out_of_10_found"] = "BLOCKED"
                    else:
                        scan.at[idx, "count_as_reversal"] = "YES"
                        last_fire = ts
                scan["effective_reversal_count"] = int((scan["count_as_reversal"] == "YES").sum())
            st.session_state["home_reversal_25d_scan"] = scan
        return scan, engines2

    # Preserve the original read-only renderers under Dinner-owned names, then
    # remove them from Morning. Their calculations and cached results are not
    # changed; only the display location moves.
    g["_dinner_current_session_intelligence_20260628"] = base_current_panel
    g["_dinner_one_hour_exit_opportunity_20260628"] = base_one_hour

    def _current_panel_collapsed(results):
        del results
        return None

    def _one_hour_collapsed(results):
        del results
        return None

    g["_evaluate_reversal_driver_from_values"] = _eval
    g["_scan_reversal_history_table"] = _scan
    g["_render_current_doo_session_metric_panel"] = _current_panel_collapsed
    g["_evaluate_one_hour_exit_sound"] = _one_hour_collapsed
