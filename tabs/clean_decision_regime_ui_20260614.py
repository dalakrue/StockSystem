"""Clean Decision / System Trust / Regime Intelligence UI patch (2026-06-14).

Display-only reorganizer. It does not remove calculations, models, ML tables,
exports, or source metric logic. Older detail outputs remain available through
advanced expanders; the visible Home/Lunch and Regime views become smaller and
more mobile-friendly.
"""
from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st

UNIQUE = "20260614_clean_decision_regime_ui"


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        if isinstance(v, str):
            v = v.replace("%", "").replace("/10", "").replace(",", "").strip()
            if "→" in v or "above" in v.lower():
                m = re.search(r"-?\d+(?:\.\d+)?", v)
                v = m.group(0) if m else default
        x = float(v)
        return x if math.isfinite(x) else float(default)
    except Exception:
        return float(default)


def _clip(v: Any, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, _num(v, lo))))


def _norm(v: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(v).lower())


def _fmt(v: Any, suffix: str = "") -> str:
    if isinstance(v, (int, float, np.number)) and math.isfinite(float(v)):
        x = float(v)
        if suffix == "%":
            return f"{x:.1f}%"
        if abs(x) >= 100:
            return f"{x:.0f}{suffix}"
        return f"{x:.2f}{suffix}"
    return str(v)


def _copy_button(label: str, text: str, key: str) -> None:
    try:
        from streamlit_copy_button import copy_button
        copy_button(text, label, key=key)
    except Exception:
        try:
            from core.pro_terminal_uiux import render_mobile_copy_button
            render_mobile_copy_button(label, text, key)
        except Exception:
            st.text_area(label, text, height=160, key=key + "_fallback")


def _safe_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


def _run_ready() -> bool:
    return bool(st.session_state.get("metric_run_calculate", False) or st.session_state.get(f"ready_{UNIQUE}", False))


def _state_context(ns: dict, force: bool = False) -> Dict[str, Any]:
    builder = ns.get("build_reliability_control_center_20260614")
    if callable(builder):
        try:
            return builder(force=force) or {}
        except TypeError:
            try:
                return builder(force) or {}
            except Exception:
                return {}
        except Exception:
            return {}
    return st.session_state.get("reliability_control_center_20260614", {}) if isinstance(st.session_state.get("reliability_control_center_20260614"), dict) else {}


def _regime_context(ns: dict, force: bool = False) -> Dict[str, Any]:
    builder = ns.get("build_regime_context_20260614")
    if callable(builder):
        try:
            return builder(force=force) or {}
        except TypeError:
            try:
                return builder(force) or {}
            except Exception:
                return {}
        except Exception:
            return {}
    ctx = st.session_state.get("regime_context_20260614")
    return ctx if isinstance(ctx, dict) else {}


def _priority_table(ns: dict, ctx: Dict[str, Any]) -> pd.DataFrame:
    obj = st.session_state.get("reliability_dynamic_priority_table_20260614")
    if isinstance(obj, pd.DataFrame) and not obj.empty:
        return obj.copy()
    records = ctx.get("priority_table_preview", []) if isinstance(ctx, dict) else []
    if records:
        try:
            return pd.DataFrame(records)
        except Exception:
            pass
    return pd.DataFrame()


def _find_col(df: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    nmap = {_norm(c): c for c in df.columns}
    for alias in aliases:
        na = _norm(alias)
        if na in nmap:
            return nmap[na]
    for nk, col in nmap.items():
        for alias in aliases:
            na = _norm(alias)
            if na and na in nk:
                return col
    return None


def _series(df: pd.DataFrame, aliases: Iterable[str], default: float = 0.0) -> pd.Series:
    col = _find_col(df, aliases)
    if col is None:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default).astype(float)


def _hour_text_from_row(row: pd.Series) -> str:
    for key in ["Time", "Datetime", "Date", "Timestamp", "Start Time", "End Time"]:
        if key in row.index:
            try:
                t = pd.to_datetime(row[key], errors="coerce")
                if pd.notna(t):
                    return t.strftime("%m-%d %H:00")
            except Exception:
                pass
    for key in ["Hour", "hour"]:
        if key in row.index:
            return f"H{int(_num(row[key], 0)) % 24:02d}"
    return "hour n/a"


def _priority_label(score: float) -> str:
    x = _clip(score)
    if x >= 90:
        return "A+ Elite"
    if x >= 80:
        return "A Strong"
    if x >= 70:
        return "B+ Good"
    if x >= 60:
        return "B Watch"
    if x >= 45:
        return "C Weak"
    return "Avoid"


def _priority_rank_1_14(score: float) -> int:
    # 1 is best, 14 is avoid. This only translates an existing priority score.
    return int(max(1, min(14, round(15 - _clip(score) / 100 * 14))))


def _priority_summary(ns: dict, ctx: Dict[str, Any]) -> Dict[str, Any]:
    p = ctx.get("priority_anti_constant_engine", {}) if isinstance(ctx, dict) else {}
    tab = _priority_table(ns, ctx)
    score = 60.0
    best_2 = "Need Run Calculation"
    label = "Watch"
    if isinstance(tab, pd.DataFrame) and not tab.empty:
        score_s = _series(tab, ["Greedy Score", "KNN Priority Score", "Priority Score", "Reliability Score"], 60)
        score = float(score_s.tail(min(len(score_s), 24)).max()) if len(score_s) else 60.0
        label_col = _find_col(tab, ["Priority Label", "Label", "Decision"])
        try:
            work = tab.copy()
            work["_score"] = score_s
            top = work.sort_values("_score", ascending=False).head(2)
            chunks = []
            for _, row in top.iterrows():
                lab = str(row.get(label_col, _priority_label(row.get("_score", 60)))) if label_col else _priority_label(row.get("_score", 60))
                chunks.append(f"{_hour_text_from_row(row)} ({_fmt(row.get('_score', 0))}, {lab})")
            if chunks:
                best_2 = "; ".join(chunks)
            if label_col and len(top):
                label = str(top.iloc[0].get(label_col, _priority_label(score)))
            else:
                label = _priority_label(score)
        except Exception:
            label = _priority_label(score)
    constant = p.get("Constant Score Warning", "Need priority table")
    movement = _num(p.get("Priority Movement Score"), 0)
    reason = "Score moves by hour using existing metrics, hour/session shape, risk, quality, and regime/forecast conflict."
    if "constant" in str(constant).lower():
        reason = "Constant-score warning active; display reliability downgraded until hourly scores move."
    return {
        "Priority Rank 1-14": _priority_rank_1_14(score),
        "Priority Label": label,
        "Best 2 Hours": best_2,
        "Priority Movement Score": round(movement, 1),
        "Constant Score Warning": constant,
        "Why priority changed": reason,
        "Dynamic Priority Reliability": p.get("Dynamic Priority Reliability", 0),
        "_score": score,
    }


def _direction_from_regime(metrics: Dict[str, Any]) -> str:
    direct = str(metrics.get("Regime Direction", "")).upper()
    if direct in {"BUY", "SELL", "WAIT"}:
        return direct
    reg = str(metrics.get("Current Regime", "")).upper()
    if "BULL" in reg:
        return "BUY"
    if "BEAR" in reg:
        return "SELL"
    return "WAIT"


def _decision_summary(ns: dict, ctx: Dict[str, Any], rctx: Dict[str, Any]) -> Dict[str, Any]:
    s = ctx.get("summary", {}) if isinstance(ctx, dict) else {}
    q = ctx.get("data_quality_market_feed_health", {}) if isinstance(ctx, dict) else {}
    leak = ctx.get("feature_leakage_guard", {}) if isinstance(ctx, dict) else {}
    drift = ctx.get("distribution_shift_wasserstein_style_drift", {}) if isinstance(ctx, dict) else {}
    anomaly = ctx.get("anomaly_and_shock_detector", {}) if isinstance(ctx, dict) else {}
    fresh = ctx.get("model_decay_forecast_freshness", {}) if isinstance(ctx, dict) else {}
    mfe = ctx.get("mfe_mae_exit_control", {}) if isinstance(ctx, dict) else {}
    rm = rctx.get("metrics", {}) if isinstance(rctx, dict) else {}
    ps = _priority_summary(ns, ctx)

    robustness = _num(s.get("Forecast Robustness Score"), 0)
    regime_rel = _num(rm.get("Regime Reliable Score", ctx.get("regime_state_reliability", {}).get("Regime Reliability Score", 0) if isinstance(ctx, dict) else 0), 0)
    priority_rel = _num(ps.get("Dynamic Priority Reliability"), 0)
    data_quality = _num(q.get("Data Quality Score"), 0)
    leakage_risk = _num(leak.get("Leakage Risk %"), 0)
    anomaly_score = _num(anomaly.get("Anomaly Score"), 0)
    freshness = _num(fresh.get("Prediction Freshness", fresh.get("Decayed Confidence Score", 0)), 0)
    confidence = _clip(robustness * .36 + regime_rel * .22 + priority_rel * .18 + data_quality * .14 + freshness * .10 - leakage_risk * .16 - max(0, anomaly_score - 50) * .18)
    risk = _clip(100 - confidence + leakage_risk * .25 + max(0, anomaly_score - 55) * .30)
    direction = _direction_from_regime(rm) if rm else str(ctx.get("regime_state_reliability", {}).get("Current Regime", "WAIT"))
    if direction not in {"BUY", "SELL", "WAIT"}:
        direction = "BUY" if "BULL" in direction.upper() else "SELL" if "BEAR" in direction.upper() else "WAIT"
    do_not_trade = []
    if leakage_risk >= 65:
        do_not_trade.append("leakage risk high")
    if str(drift.get("Drift Warning", "")).lower().startswith("danger"):
        do_not_trade.append("distribution drift dangerous")
    if anomaly_score >= 65:
        do_not_trade.append("shock/anomaly high")
    if risk >= 70:
        do_not_trade.append("risk too high")
    if "constant" in str(ps.get("Constant Score Warning", "")).lower():
        do_not_trade.append("priority constant")

    if do_not_trade:
        status = "Avoid"
    elif confidence >= 78 and risk < 45 and direction in {"BUY", "SELL"}:
        status = "Enter"
    elif confidence >= 62 and risk < 62:
        status = "Wait"
    else:
        status = "Protect / Wait"
    reason = s.get("Main Weakness", "System trust")
    if status == "Enter":
        reason = f"Robustness {robustness:.1f}, regime reliability {regime_rel:.1f}, and dynamic priority support {direction}."
    elif do_not_trade:
        reason = "Blocked by " + ", ".join(do_not_trade[:3])
    else:
        reason = f"Main weakness: {reason}; wait for better confirmation."
    return {
        "Trade Status": status,
        "Direction": direction,
        "Confidence %": round(confidence, 1),
        "Risk %": round(risk, 1),
        "Best TP Zone": mfe.get("Safer TP Zone", "Need history"),
        "Danger SL Zone": mfe.get("Danger SL Zone", "Need history"),
        "Main Reason": reason,
        "Do-not-trade warning": "YES — " + ", ".join(do_not_trade) if do_not_trade else "NO hard block detected",
        "Priority Rank": ps.get("Priority Rank 1-14"),
        "Regime Trust Reason": s.get("Why regime is trusted or not trusted", "Need regime sync"),
    }


def _detail_rows(ctx: Dict[str, Any], include: Iterable[str]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for key in include:
        block = ctx.get(key, {}) if isinstance(ctx, dict) else {}
        title = key.replace("_", " ").title()
        if isinstance(block, dict):
            for k, v in block.items():
                if str(k).startswith("_"):
                    continue
                rows.append({"Group": title, "Check": k, "Value": v})
    return pd.DataFrame(rows)


def _render_decision_control_panel(ns: dict) -> None:
    if not _run_ready():
        with st.expander("🎛️ Decision Control Panel", expanded=True):
            st.info("Press **Run Calculating** first. The decision panel stays idle to keep iPhone 11 Pro performance stable.")
        return
    ctx = _state_context(ns, force=False)
    rctx = _regime_context(ns, force=False)
    d = _decision_summary(ns, ctx, rctx)
    with st.container():
        st.markdown("### 🎛️ Decision Control Panel")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Trade Status", d.get("Trade Status", "-"))
        c2.metric("Direction", d.get("Direction", "-"))
        c3.metric("Confidence", _fmt(d.get("Confidence %", 0), "%"))
        c4.metric("Risk", _fmt(d.get("Risk %", 0), "%"))
        c5, c6 = st.columns(2)
        c5.metric("Best TP Zone", d.get("Best TP Zone", "-"))
        c6.metric("Danger SL Zone", d.get("Danger SL Zone", "-"))
        st.info(str(d.get("Main Reason", "-")))
        st.caption(f"Do-not-trade warning: {d.get('Do-not-trade warning', '-')}")


def _render_system_trust_center(ns: dict) -> None:
    with st.expander("🛡️ Open / Close — System Trust Center", expanded=False):
        st.caption("Merged Reliability Control Center, Forecast Robustness, Data Quality, Leakage, Drift, Anomaly, and Forecast Freshness into one compact view.")
        if not _run_ready():
            st.info("Press **Run Calculating** first. System Trust Center will not run heavy checks on open.")
            return
        if st.button("▶ Refresh System Trust Center", key=f"refresh_system_trust_{UNIQUE}", use_container_width=True):
            st.session_state.pop("reliability_control_center_20260614", None)
        ctx = _state_context(ns, force=False)
        summary = ctx.get("summary", {}) if isinstance(ctx, dict) else {}
        quality = ctx.get("data_quality_market_feed_health", {}) if isinstance(ctx, dict) else {}
        leak = ctx.get("feature_leakage_guard", {}) if isinstance(ctx, dict) else {}
        drift = ctx.get("distribution_shift_wasserstein_style_drift", {}) if isinstance(ctx, dict) else {}
        fresh = ctx.get("model_decay_forecast_freshness", {}) if isinstance(ctx, dict) else {}
        c = st.columns(4)
        c[0].metric("Robustness", _fmt(summary.get("Forecast Robustness Score", 0), "%"))
        c[1].metric("Data Quality", _fmt(quality.get("Data Quality Score", 0), "%"))
        c[2].metric("Leakage Risk", _fmt(leak.get("Leakage Risk %", 0), "%"))
        c[3].metric("Drift Risk", drift.get("Drift Warning", "-"))
        c2 = st.columns(3)
        c2[0].metric("Forecast Freshness", _fmt(fresh.get("Prediction Freshness", fresh.get("Decayed Confidence Score", 0)), "%"))
        c2[1].metric("Main Weakness", summary.get("Main Weakness", "-"))
        c2[2].metric("Best Action", summary.get("Best Action Now", "-"))
        try:
            from core.canonical_runtime_20260617 import get_canonical
            canonical = get_canonical(st.session_state)
        except Exception:
            canonical = st.session_state.get("canonical_result_20260617") or {}
        research = canonical.get("research_risk_stack", {}) if isinstance(canonical, dict) else {}
        confidence = research.get("confidence_sequence", {}) if isinstance(research, dict) else {}
        selective = research.get("selective_prediction", {}) if isinstance(research, dict) else {}
        proper = research.get("proper_scoring", {}) if isinstance(research, dict) else {}
        evt = research.get("evt_tail", {}) if isinstance(research, dict) else {}
        invariance = research.get("invariance", {}) if isinstance(research, dict) else {}
        metrics = confidence.get("metrics", {}) if isinstance(confidence, dict) else {}
        sample_counts = [int((item or {}).get("effective_sample_count") or 0) for item in metrics.values() if isinstance(item, dict)]
        c3 = st.columns(4)
        c3[0].metric("Anytime-valid trust", confidence.get("trust_status", "INSUFFICIENT_DATA"))
        c3[1].metric("Risk–coverage", "PASS" if selective.get("selective_prediction_pass") else "WAIT", f"threshold {selective.get('required_confidence_threshold', '—')}%")
        c3[2].metric("CRPS skill", _fmt(proper.get("skill_vs_naive", 0), "%"), f"Energy {_fmt(proper.get('joint_energy_score', 0))}")
        c3[3].metric("Effective samples", max(sample_counts or [0]), f"CRPS n={proper.get('sample_count', 0)}")
        c4 = st.columns(2)
        c4[0].metric("EVT status", "BLOCK" if evt.get("extreme_risk_block") else ("READY" if evt.get("evt_sample_sufficient") else "DEVELOPING"), f"exceedances {evt.get('evt_exceedance_count', 0)}")
        c4[1].metric("Invariance status", invariance.get("feature_stability_warning", "INSUFFICIENT_DATA"), f"score {_fmt(invariance.get('invariance_score', 0), '%')}")
        st.caption("Only the summary shows first. All previous detail blocks are still available below.")
        with st.expander("Advanced Details — all merged reliability checks", expanded=False):
            details = _detail_rows(ctx, [
                "feature_leakage_guard",
                "data_quality_market_feed_health",
                "distribution_shift_wasserstein_style_drift",
                "anomaly_and_shock_detector",
                "model_decay_forecast_freshness",
                "market_maker_pressure_proxy",
                "pca_factor_structure_dashboard",
                "mfe_mae_exit_control",
            ])
            if not details.empty:
                st.dataframe(details, use_container_width=True, hide_index=True, height=420)
            else:
                st.info("No advanced details available yet.")
            if research:
                st.markdown("**Research risk validation details**")
                st.json(research)


def _render_dynamic_entry_priority_center(ns: dict) -> None:
    with st.expander("🎯 Open / Close — Dynamic Entry Priority Center", expanded=False):
        st.caption("Merged KNN Priority, Greedy Priority, Anti-Constant, Best Hour, and Best 2 Entries into one compact view.")
        if not _run_ready():
            st.info("Press **Run Calculating** first. Priority stays idle until run.")
            return
        ctx = _state_context(ns, force=False)
        ps = _priority_summary(ns, ctx)
        c = st.columns(3)
        c[0].metric("Priority Rank 1–14", ps.get("Priority Rank 1-14", "-"))
        c[1].metric("Priority Label", ps.get("Priority Label", "-"))
        c[2].metric("Movement Score", _fmt(ps.get("Priority Movement Score", 0), "%"))
        st.info(f"Best 2 Hours: {ps.get('Best 2 Hours', '-')}")
        st.warning(str(ps.get("Constant Score Warning", "-"))) if "constant" in str(ps.get("Constant Score Warning", "")).lower() else st.success(str(ps.get("Constant Score Warning", "-")))
        st.caption(str(ps.get("Why priority changed", "-")))
        with st.expander("Advanced Details — priority table and anti-constant checks", expanded=False):
            priority = ctx.get("priority_anti_constant_engine", {}) if isinstance(ctx, dict) else {}
            if isinstance(priority, dict) and priority:
                st.dataframe(pd.DataFrame([{"Check": k, "Value": v} for k, v in priority.items()]), use_container_width=True, hide_index=True)
            tab = _priority_table(ns, ctx)
            if isinstance(tab, pd.DataFrame) and not tab.empty:
                st.dataframe(tab.tail(48), use_container_width=True, hide_index=True, height=360)
            else:
                st.info("No priority table found yet.")


def _regime_best_action(m: Dict[str, Any]) -> str:
    reliability = _num(m.get("Regime Reliable Score"), 0)
    shift = _num(m.get("Transition Risk %"), 0)
    conflict = str(m.get("Regime Conflict", "NO")).upper().startswith("Y")
    direction = _direction_from_regime(m)
    if conflict:
        return "WAIT — forecast/regime conflict"
    if reliability >= 75 and shift < 45 and direction in {"BUY", "SELL"}:
        return f"FOLLOW {direction} bias with confirmation"
    if reliability >= 60:
        return "SMALL SIZE / WAIT for confirmation"
    return "AVOID — regime not reliable"


def _major_regime_history(ctx: Dict[str, Any]) -> pd.DataFrame:
    hist = ctx.get("history", pd.DataFrame()) if isinstance(ctx, dict) else pd.DataFrame()
    metrics = ctx.get("metrics", {}) if isinstance(ctx, dict) else {}
    if not isinstance(hist, pd.DataFrame) or hist.empty:
        return pd.DataFrame(columns=["Start Time", "End Time", "Duration Hours", "Duration Days", "Major Regime", "Avg Confidence", "Avg Reliability", "Shift Risk", "Best Trade Bias", "Result After Regime"])
    out = hist.copy()
    # Normalize names from the existing regime segment table. It is already aggregated by consecutive same-regime hours.
    if "Start" in out.columns and "Start Time" not in out.columns:
        out["Start Time"] = out["Start"]
    if "End" in out.columns and "End Time" not in out.columns:
        out["End Time"] = out["End"]
    if "Regime" in out.columns and "Major Regime" not in out.columns:
        out["Major Regime"] = out["Regime"]
    if "Duration Hours" not in out.columns:
        out["Duration Hours"] = 1
    try:
        out["End Time"] = pd.to_datetime(out["End Time"], errors="coerce")
        max_end = out["End Time"].max()
        if pd.notna(max_end):
            out = out[out["End Time"] >= max_end - pd.Timedelta(days=25)]
    except Exception:
        pass
    out["Duration Days"] = pd.to_numeric(out.get("Duration Hours", 0), errors="coerce").fillna(0) / 24.0
    out["Avg Confidence"] = out.get("Avg Confidence", round(_num(metrics.get("Regime Confidence %"), 55), 1))
    out["Avg Reliability"] = out.get("Avg Reliability", round(_num(metrics.get("Regime Reliable Score"), 55), 1))
    out["Shift Risk"] = out.get("Shift Risk", round(_num(metrics.get("Transition Risk %"), 50), 1))
    if "Regime Direction" in out.columns:
        out["Best Trade Bias"] = out["Regime Direction"]
    else:
        out["Best Trade Bias"] = out["Major Regime"].astype(str).map(lambda x: "BUY" if "BULL" in x.upper() else "SELL" if "BEAR" in x.upper() else "WAIT")
    if "Outcome pips" in out.columns:
        def _result(row: pd.Series) -> str:
            pips = _num(row.get("Outcome pips"), 0)
            bias = str(row.get("Best Trade Bias", "WAIT")).upper()
            if bias == "BUY" and pips > 0:
                return f"Worked +{pips:.1f} pips"
            if bias == "SELL" and pips < 0:
                return f"Worked +{abs(pips):.1f} pips"
            if abs(pips) < 1:
                return "Flat / no edge"
            return f"Failed {pips:.1f} pips"
        out["Result After Regime"] = out.apply(_result, axis=1)
    elif "Result After Regime" not in out.columns:
        out["Result After Regime"] = "Need outcome history"
    cols = ["Start Time", "End Time", "Duration Hours", "Duration Days", "Major Regime", "Avg Confidence", "Avg Reliability", "Shift Risk", "Best Trade Bias", "Result After Regime"]
    out = out[[c for c in cols if c in out.columns]].sort_values("End Time", ascending=False).reset_index(drop=True)
    if "Duration Days" in out.columns:
        out["Duration Days"] = pd.to_numeric(out["Duration Days"], errors="coerce").round(2)
    return out


def _render_regime_intelligence_center(ns: dict) -> None:
    st.markdown("### 🧭 Regime Intelligence Center")
    st.caption("Regime tab is synced to the same Lunch/Data Visualization regime context, with only the important values shown first.")
    a, b, c = st.columns([1.2, .8, 1.8])
    if a.button("▶ Run Regime Sync", key=f"run_regime_clean_{UNIQUE}", use_container_width=True):
        st.session_state[f"ready_{UNIQUE}"] = True
        try:
            _regime_context(ns, force=True)
            _state_context(ns, force=False)
        except Exception:
            pass
        try:
            from core.styles import request_close_sidebar
            request_close_sidebar()
        except Exception:
            pass
    if b.button("Clear", key=f"clear_regime_clean_{UNIQUE}", use_container_width=True):
        st.session_state[f"ready_{UNIQUE}"] = False
    c.caption("No hourly regime spam by default. The table below aggregates consecutive same-regime periods over the last 25 days.")
    if not st.session_state.get(f"ready_{UNIQUE}") and not isinstance(st.session_state.get("regime_context_20260614"), dict):
        st.info("Click Run Regime Sync to load the compact regime summary and 25-day major regime history.")
        return
    ctx = _regime_context(ns, force=False)
    m = ctx.get("metrics", {}) if isinstance(ctx, dict) else {}
    trust = "Trusted" if _num(m.get("Regime Reliable Score"), 0) >= 70 and _num(m.get("Transition Risk %"), 100) < 55 else "Caution / Not trusted"
    top = {
        "Current Regime": m.get("Current Regime", "-"),
        "Regime Confidence": _fmt(m.get("Regime Confidence %", 0), "%"),
        "Regime Reliability": _fmt(m.get("Regime Reliable Score", 0), "%"),
        "Regime Age": f"{int(_num(m.get('Regime Age Hours'), 0))}h",
        "Shift Risk": _fmt(m.get("Transition Risk %", 0), "%"),
        "Regime Best Action": _regime_best_action(m),
        "Regime Trust Reason": f"{trust}; source: {m.get('Regime Sync Source', 'existing sync context')}",
    }
    c1, c2, c3 = st.columns(3)
    c1.metric("Current Regime", top["Current Regime"])
    c2.metric("Confidence", top["Regime Confidence"])
    c3.metric("Reliability", top["Regime Reliability"])
    c4, c5, c6 = st.columns(3)
    c4.metric("Age", top["Regime Age"])
    c5.metric("Shift Risk", top["Shift Risk"])
    c6.metric("Best Action", top["Regime Best Action"])
    st.info(top["Regime Trust Reason"])

    table = _major_regime_history(ctx)
    st.markdown("#### 25-Day Major Regime History Table")
    st.caption("Consecutive same-regime hours are merged into one period. This replaces the annoying every-hour regime table by default.")
    if isinstance(table, pd.DataFrame) and not table.empty:
        st.dataframe(table, use_container_width=True, hide_index=True, height=420)
    else:
        st.info("Need more regime/H1 history to build the 25-day major regime table.")

    with st.expander("Advanced Details — full regime metrics and KNN/Greedy regime similarity", expanded=False):
        if m:
            st.dataframe(pd.DataFrame([{"Metric": k, "Value": v} for k, v in m.items()]), use_container_width=True, hide_index=True, height=360)
        knn = ctx.get("knn", pd.DataFrame()) if isinstance(ctx, dict) else pd.DataFrame()
        if isinstance(knn, pd.DataFrame) and not knn.empty:
            st.markdown("##### Similar Historical Regimes")
            st.dataframe(knn, use_container_width=True, hide_index=True, height=300)
        text = _safe_json({"top_summary": top, "metrics": m, "major_regime_history": table.to_dict("records") if isinstance(table, pd.DataFrame) else []})
        _copy_button("📋 Copy Regime Intelligence Summary", text, f"copy_regime_intelligence_{UNIQUE}")
        st.download_button("⬇️ Download Regime Intelligence JSON", text, file_name="regime_intelligence_center.json", mime="application/json", use_container_width=True, key=f"download_regime_intelligence_{UNIQUE}")


def _compact_no_history_text(ns: dict) -> str:
    build = ns.get("_build_lunch_all_copy_text")
    try:
        full = build() if callable(build) else "Run Calculation first; copy builder is not ready."
    except Exception as exc:
        full = f"Run Calculation first; copy builder failed safely: {exc}"
    lines = str(full).splitlines()
    keep: List[str] = []
    skip_markers = ["history", "25d", "25-day", "backtest rows", "regime_history", "full_metric_history", "candles", "rows"]
    for line in lines:
        low = line.lower()
        if any(m in low for m in skip_markers) and len(keep) > 18:
            continue
        keep.append(line)
        if len(keep) >= 260:
            break
    return "LUNCH COMPACT FULL COPY — NO HISTORY\n" + "=" * 64 + "\n" + "\n".join(keep).strip()


def _render_no_history_copy(ns: dict) -> None:
    with st.expander("📋 Open / Close — Lunch Compact Full Copy — No History", expanded=False):
        text = _compact_no_history_text(ns)
        c1, c2 = st.columns([1, .75])
        with c1:
            _copy_button("📋 Copy Compact Full — No History", text, f"copy_compact_no_history_clean_{UNIQUE}")
        with c2:
            st.download_button("⬇️ Download No-History TXT", text, file_name="lunch_compact_full_no_history.txt", mime="text/plain", use_container_width=True, key=f"download_compact_no_history_clean_{UNIQUE}")


def _render_data_visualization(prev_data) -> None:
    with st.expander("📊 Open / Close — Data Visualization inside Lunch", expanded=False):
        st.caption("Preserved from the previous working ZIP. It stays collapsed so Home/Lunch is cleaner.")
        if callable(prev_data):
            prev_data()
        else:
            st.warning("Data Visualization renderer is not available in this ZIP.")


def _render_research_with_ai(prev_research) -> None:
    st.markdown("### 🎓 Research Inner Tab")
    research_tab, ai_tab = st.tabs(["Research Pack", "AI Assistant Lite"])
    with research_tab:
        if callable(prev_research):
            prev_research()
        else:
            try:
                import tabs.research as research
                research.show()
            except Exception as exc:
                st.error("Research tab could not load safely.")
                st.exception(exc)
    with ai_tab:
        try:
            from .ai_assistant_lite import render_ai_assistant_lite_tab
        except Exception:
            from tabs.ai_assistant_lite import render_ai_assistant_lite_tab
        render_ai_assistant_lite_tab()


def _selector() -> str:
    choices = [("Lunch", "🍱"), ("Regime", "🧭"), ("Research", "🎓"), ("Doo Prime", "🏦")]
    current = st.session_state.get("home_inner_tab", "Lunch")
    if current in {"AI Assistant Lite", "Data Visualization"}:
        current = "Research" if current == "AI Assistant Lite" else "Lunch"
        st.session_state["home_inner_tab"] = current
    names = [x[0] for x in choices]
    if current not in names:
        current = "Lunch"
        st.session_state["home_inner_tab"] = current
    cols = st.columns(len(choices))
    for idx, (name, icon) in enumerate(choices):
        active = st.session_state.get("home_inner_tab", current) == name
        if cols[idx].button(("✅ " if active else "") + f"{icon} {name}", use_container_width=True, key=f"home_clean_inner_{idx}_{UNIQUE}"):
            st.session_state["home_inner_tab"] = name
            st.session_state["ui_navigation_click_ts"] = time.time()
            try:
                from core.styles import request_close_sidebar
                request_close_sidebar()
            except Exception:
                pass
            try:
                st.rerun()
            except Exception:
                pass
    return st.session_state.get("home_inner_tab", current)


def _summary_copy(ns: dict, compact: bool = False) -> str:
    if not _run_ready():
        return "\n\nCLEAN DECISION UI SUMMARY\nPress Run Calculating first."
    ctx = _state_context(ns, force=False)
    rctx = _regime_context(ns, force=False)
    decision = _decision_summary(ns, ctx, rctx)
    priority = _priority_summary(ns, ctx)
    regime_table = _major_regime_history(rctx)
    payload = {
        "Decision Control Panel": decision,
        "System Trust Center": {
            "Robustness Score": ctx.get("summary", {}).get("Forecast Robustness Score") if isinstance(ctx, dict) else None,
            "Data Quality Score": ctx.get("data_quality_market_feed_health", {}).get("Data Quality Score") if isinstance(ctx, dict) else None,
            "Leakage Risk": ctx.get("feature_leakage_guard", {}).get("Leakage Risk %") if isinstance(ctx, dict) else None,
            "Drift Risk": ctx.get("distribution_shift_wasserstein_style_drift", {}).get("Drift Warning") if isinstance(ctx, dict) else None,
            "Forecast Freshness": ctx.get("model_decay_forecast_freshness", {}).get("Prediction Freshness") if isinstance(ctx, dict) else None,
            "Main Weakness": ctx.get("summary", {}).get("Main Weakness") if isinstance(ctx, dict) else None,
            "Best Action": ctx.get("summary", {}).get("Best Action Now") if isinstance(ctx, dict) else None,
        },
        "Dynamic Entry Priority Center": priority,
        "Regime Intelligence Center": rctx.get("metrics", {}) if isinstance(rctx, dict) else {},
    }
    if not compact:
        payload["25-Day Major Regime History Table"] = regime_table.to_dict("records") if isinstance(regime_table, pd.DataFrame) else []
    return "\n\nCLEAN DECISION / SYSTEM TRUST / REGIME UI SUMMARY\n" + _safe_json(payload)


def install(ns: dict) -> None:
    if ns.get("_clean_decision_regime_ui_installed_20260614"):
        return

    # Ensure the older builder functions are available, but do not show the old detailed renderer by default.
    try:
        from .reliability_control_center_20260614 import install as _install_rcc
    except Exception:
        from tabs.reliability_control_center_20260614 import install as _install_rcc
    try:
        _install_rcc(ns)
    except Exception:
        pass

    prev_full = ns.get("_build_lunch_all_copy_text")
    prev_short = ns.get("_build_short_necessary_copy_text")

    def _full_with_clean_summary() -> str:
        base = prev_full() if callable(prev_full) else ""
        return str(base) + _summary_copy(ns, compact=False)

    def _short_with_clean_summary() -> str:
        base = prev_short() if callable(prev_short) else ""
        return str(base) + _summary_copy(ns, compact=True)

    if callable(prev_full):
        ns["_build_lunch_all_copy_text"] = _full_with_clean_summary
    if callable(prev_short):
        ns["_build_short_necessary_copy_text"] = _short_with_clean_summary

    prev_lunch = ns.get("_render_metric_home_combined_inner_tab")
    prev_data = ns.get("_render_lunch_data_visualization_inner_tab")
    prev_research = ns.get("_render_home_research_inner_20260612")
    prev_doo = ns.get("_render_doo_prime_inner_tab")
    footer = ns.get("render_tab_footer")

    def _show_clean() -> None:
        try:
            from core.streamlit_safe_dataframe import install_safe_dataframe_patch
            install_safe_dataframe_patch()
        except Exception:
            pass
        selected = _selector()
        if selected == "Lunch":
            _render_decision_control_panel(ns)
            if callable(prev_lunch):
                prev_lunch()
            else:
                st.warning("Lunch renderer is not available.")
            _render_system_trust_center(ns)
            _render_dynamic_entry_priority_center(ns)
            _render_no_history_copy(ns)
            _render_data_visualization(prev_data)
        elif selected == "Regime":
            _render_regime_intelligence_center(ns)
        elif selected == "Research":
            _render_research_with_ai(prev_research)
        else:
            if callable(prev_doo):
                prev_doo()
            else:
                st.info("Doo Prime inner tab is not available in this ZIP.")
        if callable(footer):
            try:
                footer("Lunch")
            except Exception:
                pass

    ns["show"] = _show_clean
    ns["render_regime_inner_tab_20260614"] = lambda: _render_regime_intelligence_center(ns)
    ns["build_clean_decision_summary_20260614"] = lambda compact=False: _summary_copy(ns, compact=compact)
    ns["_clean_decision_regime_ui_installed_20260614"] = True
