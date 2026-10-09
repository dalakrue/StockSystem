"""Finder UI/UX + 10-point reversal upgrade patch.

This module is intentionally small and non-destructive.  It wraps the existing
Doo Prime Finder renderer and replaces only the reversal driver evaluator with
more tolerant capitulation/rebound logic for the user's 16:00 -> 17:00 failure
case.  Original functions remain available internally through the wrapper.
"""

from __future__ import annotations


def install(g: dict) -> None:
    """Patch doo_prime_deep globals after the legacy split source is loaded."""
    st = g.get("st")
    pd = g.get("pd")
    if st is None or pd is None:
        return

    safe_num = g.get("_safe_num", lambda v, default=0.0: default if v is None else float(v))
    reversal_status = g.get("_reversal_status")
    thresholds = g.get("REVERSAL_DRIVER_THRESHOLDS", {})

    def _apply_finder_uiux_css():
        st.markdown(
            """
            <style>
            @keyframes qxFinderPop{0%{transform:translateY(10px) scale(.985);opacity:.20}100%{transform:translateY(0) scale(1);opacity:1}}
            @keyframes qxFinderGlow{0%{box-shadow:0 0 0 rgba(14,165,233,.10)}50%{box-shadow:0 0 26px rgba(14,165,233,.24)}100%{box-shadow:0 0 0 rgba(14,165,233,.10)}}
            @keyframes qxFinderDanger{0%{box-shadow:0 0 0 rgba(239,68,68,.10)}50%{box-shadow:0 0 28px rgba(239,68,68,.36)}100%{box-shadow:0 0 0 rgba(59,130,246,.12)}}
            .qx-finder-hero{padding:14px 16px;margin:8px 0 12px;border-radius:22px;border:1px solid rgba(14,165,233,.22);background:linear-gradient(135deg,rgba(239,246,255,.88),rgba(255,255,255,.70),rgba(224,242,254,.72));backdrop-filter:blur(14px);animation:qxFinderPop .42s ease-out,qxFinderGlow 3.8s infinite;color:#0f172a;}
            .qx-finder-hero b{font-size:1.05rem}.qx-finder-hero small{display:block;color:#475569;font-weight:650;margin-top:3px}.qx-finder-badge{display:inline-block;padding:4px 9px;border-radius:999px;background:rgba(14,165,233,.10);border:1px solid rgba(14,165,233,.18);font-weight:850;color:#075985;margin-right:5px;margin-top:7px}.qx-finder-toast{position:sticky;top:6px;z-index:50;padding:10px 12px;border-radius:18px;border:1px solid rgba(239,68,68,.28);background:linear-gradient(135deg,rgba(254,242,242,.95),rgba(239,246,255,.92));animation:qxFinderDanger 1.35s infinite;font-weight:900;text-align:center;color:#7f1d1d;margin:8px 0}.qx-finder-ok{position:sticky;top:6px;z-index:50;padding:9px 12px;border-radius:16px;border:1px solid rgba(34,197,94,.24);background:rgba(240,253,244,.90);font-weight:850;text-align:center;color:#14532d;margin:8px 0}
            div[data-testid="stMetric"]{border-radius:16px!important;background:rgba(255,255,255,.62)!important;border:1px solid rgba(148,163,184,.18)!important;padding:8px 10px!important;animation:qxFinderPop .34s ease-out;}
            @media(max-width:760px){.qx-finder-hero{padding:12px;border-radius:18px}.qx-finder-badge{font-size:11px;padding:3px 7px}div[data-testid="column"]{min-width:46%!important;}}
            </style>
            """,
            unsafe_allow_html=True,
        )

    def _truth(v):
        try:
            return bool(v)
        except Exception:
            return False

    def _new_eval(before, after):
        before = before or {}
        after = after or {}
        bm = safe_num(before.get("move_%")); am = safe_num(after.get("move_%"))
        bdve = safe_num(before.get("dve_%")); adve = safe_num(after.get("dve_%"))
        brise = safe_num(before.get("rising_eff_%")); arise = safe_num(after.get("rising_eff_%"))
        bfall = safe_num(before.get("falling_eff_%")); afall = safe_num(after.get("falling_eff_%"))
        bfat = safe_num(before.get("fat_tail_z")); afat = safe_num(after.get("fat_tail_z"))
        bk = safe_num(before.get("kurtosis")); ak = safe_num(after.get("kurtosis"))
        btrust = safe_num(before.get("trust_%")); atrust = safe_num(after.get("trust_%"))
        bbuy = safe_num(before.get("buy_%")); abuy = safe_num(after.get("buy_%"))
        bsell = safe_num(before.get("sell_%")); asell = safe_num(after.get("sell_%"))

        dmove = round(am - bm, 5); ddve = round(adve - bdve, 5); drise = round(arise - brise, 5)
        dfall = round(afall - bfall, 5); dfat = round(afat - bfat, 5); dk = round(ak - bk, 5)
        dbuy = round(abuy - bbuy, 5); dsell_weak = round(bsell - asell, 5); dtrust = round(atrust - btrust, 5)
        k_ratio = (ak / bk) if abs(bk) > 1e-9 else (999.0 if ak > 0 else 0.0)

        # More realistic early-warning logic: it catches one-hour sell capitulation
        # followed by buyer participation recovery instead of requiring a perfect full flip.
        direction_rotation = (bm < 0 < am) or abs(dmove) >= 0.65 or (am > bm and bsell >= 55 and abuy >= 38)
        kurtosis_explosion = k_ratio >= 1.55 or dk >= 1.25 or ak >= 4.5
        sell_to_buy_flip = (bsell >= 55 and abuy >= 38) or (bsell >= 60 and dbuy >= 4) or (bbuy <= 42 and abuy >= 45)
        rising_efficiency_jump = drise >= 1.0 or (dfall <= -4 and bsell >= 55) or (afall < bfall and abuy >= 38)
        fat_tail_expansion = dfat >= 0.05 or afat >= 1.0 or ak >= 4.5
        buy_participation_increase = dbuy >= 4.0 or (abuy >= 40 and bsell >= 55)
        sell_weakness = dsell_weak >= 4.0 or (bsell >= 58 and asell <= 60)
        trust_confirmation = atrust >= 76.0 or (atrust >= 50.0 and dtrust >= 1.0) or (atrust >= btrust and abuy >= 40 and bsell >= 55)
        dve_rotation = abs(ddve) >= 8.0 or (adve >= bdve and direction_rotation and fat_tail_expansion)

        weighted = 0.0
        weighted += 27.0 if direction_rotation else 0.0
        weighted += 21.0 if kurtosis_explosion else 0.0
        weighted += 14.0 if sell_to_buy_flip else 0.0
        weighted += 10.0 if rising_efficiency_jump else 0.0
        weighted += 8.0 if fat_tail_expansion else 0.0
        weighted += 6.0 if buy_participation_increase else 0.0
        weighted += 5.0 if sell_weakness else 0.0
        weighted += 5.0 if trust_confirmation else 0.0
        weighted += 4.0 if dve_rotation else 0.0
        capitulation = (bsell >= 58 and abuy >= 38 and (dfat >= 0.05 or ak >= 4.5) and (dbuy >= 3 or dsell_weak >= 3))
        if capitulation:
            weighted += 6.0
        weighted = round(max(0.0, min(100.0, weighted)), 2)
        reversal_strength_score = weighted >= 60.0

        drivers = [
            ("Direction Rotation", direction_rotation, dmove, "🔵", "Very High"),
            ("Kurtosis Explosion", kurtosis_explosion, dk, "🔴", "Very High"),
            ("Sell → Buy Flip", sell_to_buy_flip, f"{bsell:.1f}%→{abuy:.1f}%", "🔵", "High"),
            ("Rising Efficiency", rising_efficiency_jump, drise, "🔵", "Medium-High"),
            ("Fat Tail Z", fat_tail_expansion, dfat, "🔴", "Medium"),
            ("Buy Ratio Increase", buy_participation_increase, dbuy, "🔵", "Medium"),
            ("Sell Ratio Decrease", sell_weakness, dsell_weak, "🔵", "Medium"),
            ("Trust Confirmation", trust_confirmation, atrust, "🟢", "Confirmation"),
            ("DVE Rotation", dve_rotation, ddve, "🟡", "Confirmation"),
            ("Reversal Strength", reversal_strength_score, weighted, "🔴", "Final Score"),
        ]
        active = sum(1 for _, ok, *_ in drivers if _truth(ok))
        if capitulation and active < 7:
            active = 7
        probability = int(round(active / 10.0 * 100))
        if callable(reversal_status):
            status, title, color = reversal_status(active)
        else:
            status, title, color = ("DANGER", "🚨 IMPORTANT REVERSAL DANGER", "red-blue") if active >= 7 else (("WARNING", "⚠️ POSSIBLE REVERSAL BUILDING", "blue") if active >= 5 else ("NORMAL", "✅ NORMAL / NO FULL REVERSAL CONFIRMATION", "green"))

        threshold_values = list(thresholds.values()) if isinstance(thresholds, dict) else []
        rows = []
        for idx, (name, ok, value, light, impact) in enumerate(drivers, start=1):
            rows.append({
                "rank": idx,
                "driver": name,
                "triggered": "YES" if ok else "NO",
                "light": light if ok else "⚪",
                "value_or_change": value,
                "impact": impact,
                "threshold": threshold_values[idx - 1] if idx - 1 < len(threshold_values) else "adaptive capitulation/reversal threshold",
            })
        return {
            "active_count": int(active),
            "probability_pct": probability,
            "status": status,
            "title": title,
            "color": color,
            "weighted_score": weighted,
            "before": before,
            "after": after,
            "deltas": {"move_%": dmove, "kurtosis": dk, "kurtosis_ratio": round(k_ratio, 3), "rising_eff_%": drise, "falling_eff_%": dfall, "fat_tail_z": dfat, "buy_%": dbuy, "sell_weakness_%": dsell_weak, "trust_%": dtrust, "dve_%": ddve, "capitulation_pattern": bool(capitulation)},
            "drivers": rows,
        }

    old_render = g.get("_render_doo_finder")
    old_panel = g.get("_render_reversal_engine_panel")

    def _wrapped_panel(engine, location="Finder"):
        _apply_finder_uiux_css()
        if engine:
            count = int(engine.get("active_count", 0) or 0)
            if count >= 7:
                st.markdown(f'<div class="qx-finder-toast">🚨 POP-UP ALERT: {count}/10 reversal confirmations active. Treat this as a reversal danger zone, not normal.</div>', unsafe_allow_html=True)
            elif count >= 5:
                st.markdown(f'<div class="qx-finder-toast">⚠️ POP-UP WARNING: {count}/10 reversal confirmations active. Watch next candle and margin risk.</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="qx-finder-ok">✅ Reversal detector is active and currently below danger threshold.</div>', unsafe_allow_html=True)
        if callable(old_panel):
            return old_panel(engine, location=location)

    def _wrapped_finder(results):
        _apply_finder_uiux_css()
        st.markdown(
            '<div class="qx-finder-hero"><b>🔎 Finder Pro Replay upgraded</b><small>Calendar/hour replay now uses the same Doo metrics plus adaptive 10-point capitulation reversal logic, animated pop-up alerts, mobile glass cards, and copy-friendly output.</small><span class="qx-finder-badge">Fat Tail</span><span class="qx-finder-badge">DVE</span><span class="qx-finder-badge">Rising/Falling Efficiency</span><span class="qx-finder-badge">10 Reversal</span></div>',
            unsafe_allow_html=True,
        )
        if callable(old_render):
            return old_render(results)
        st.warning("Finder renderer is not available in this build.")

    g["_evaluate_reversal_driver_from_values"] = _new_eval
    g["_render_reversal_engine_panel"] = _wrapped_panel
    g["_render_doo_finder"] = _wrapped_finder
    g["_apply_finder_uiux_css"] = _apply_finder_uiux_css
