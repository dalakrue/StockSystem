"""Final three-section Lunch/Home + Regime/AI Intelligence Center patch.

Non-destructive UI wrapper only. Existing calculations, metric sources, chart
sources, ML tables, exports, copy builders, history tables, and functions remain
available. Heavy work is still manual-run gated.
"""
from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd
import streamlit as st

UNIQUE = "20260614_three_center_final"


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        if isinstance(v, str):
            m = re.search(r"-?\d+(?:\.\d+)?", v.replace(",", ""))
            v = m.group(0) if m else default
        x = float(v)
        return x if math.isfinite(x) else float(default)
    except Exception:
        return float(default)


def _clip(v: Any, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, _num(v, lo))))


def _fmt(v: Any, suffix: str = "") -> str:
    if isinstance(v, (int, float)) and math.isfinite(float(v)):
        x = float(v)
        if suffix == "%":
            return f"{x:.1f}%"
        if abs(x) >= 100:
            return f"{x:.0f}{suffix}"
        return f"{x:.2f}{suffix}"
    return str(v)


def _safe_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


def _copy_button(label: str, text: str, key: str) -> None:
    try:
        from streamlit_copy_button import copy_button
        copy_button(text, label, key=key)
    except Exception:
        try:
            from core.pro_terminal_uiux import render_mobile_copy_button
            render_mobile_copy_button(label, text, key)
        except Exception:
            st.text_area(label, text, height=170, key=key + "_fallback")


def _run_ready() -> bool:
    return bool(st.session_state.get("metric_run_calculate", False))


def _render_run_gate(ns: dict, location: str) -> None:
    """Read-only publication status; Settings is the only calculation owner."""
    del ns, location
    canonical = st.session_state.get("canonical_decision_result_20260617") or {}
    run_id = canonical.get("run_id") if isinstance(canonical, dict) else None
    generation = canonical.get("calculation_generation") if isinstance(canonical, dict) else None
    if _run_ready():
        st.caption(f"Synchronized Settings generation {generation or '-'} • Run ID {run_id or 'cached'}. No inner Run/Stop control is required.")
    else:
        try:
            from core.system_wide_completion_20260618 import readiness_message
            st.info(readiness_message(st.session_state, "Lunch Priority"))
        except Exception:
            st.info("Use Settings → Run Calculation + Open Lunch once.")


def _state_context(ns: dict, force: bool = False) -> Dict[str, Any]:
    builder = ns.get("build_reliability_control_center_20260614")
    if callable(builder) and _run_ready():
        try:
            return builder(force=force) or {}
        except TypeError:
            try:
                return builder(force) or {}
            except Exception:
                return {}
        except Exception:
            return {}
    obj = st.session_state.get("reliability_control_center_20260614")
    return obj if isinstance(obj, dict) else {}


def _regime_context(ns: dict, force: bool = False) -> Dict[str, Any]:
    builder = ns.get("build_regime_context_20260614")
    if callable(builder) and (_run_ready() or force or isinstance(st.session_state.get("regime_context_20260614"), dict)):
        try:
            return builder(force=force) or {}
        except TypeError:
            try:
                return builder(force) or {}
            except Exception:
                return {}
        except Exception:
            return {}
    obj = st.session_state.get("regime_context_20260614")
    return obj if isinstance(obj, dict) else {}


def _norm(v: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(v).lower())


def _find_col(df: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    nmap = {_norm(c): c for c in df.columns}
    for a in aliases:
        na = _norm(a)
        if na in nmap:
            return nmap[na]
    for nk, col in nmap.items():
        for a in aliases:
            na = _norm(a)
            if na and na in nk:
                return col
    return None


def _series(df: pd.DataFrame, aliases: Iterable[str], default: float = 0.0) -> pd.Series:
    col = _find_col(df, aliases)
    if col is None:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default).astype(float)


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


def _priority_rank(score: float) -> int:
    return int(max(1, min(14, round(15 - _clip(score) / 100 * 14))))


def _hour_text(row: pd.Series) -> str:
    for k in ["Time", "Datetime", "Timestamp", "Date", "Start Time", "End Time"]:
        if k in row.index:
            try:
                t = pd.to_datetime(row[k], errors="coerce")
                if pd.notna(t):
                    return t.strftime("%m-%d %H:00")
            except Exception:
                pass
    for k in ["Hour", "hour"]:
        if k in row.index:
            try:
                return f"H{int(float(row[k])) % 24:02d}"
            except Exception:
                return str(row[k])
    return "hour n/a"


def _priority_table(ns: dict, ctx: Dict[str, Any]) -> pd.DataFrame:
    obj = st.session_state.get("reliability_dynamic_priority_table_20260614")
    if isinstance(obj, pd.DataFrame) and not obj.empty:
        return obj.copy()
    rec = ctx.get("priority_table_preview", []) if isinstance(ctx, dict) else []
    if rec:
        try:
            return pd.DataFrame(rec)
        except Exception:
            pass
    return pd.DataFrame()


def _priority_summary(ns: dict, ctx: Dict[str, Any]) -> Dict[str, Any]:
    p = ctx.get("priority_anti_constant_engine", {}) if isinstance(ctx, dict) else {}
    tab = _priority_table(ns, ctx)
    score = 60.0
    best_2 = "No published candidates"
    const_msg = p.get("Constant Score Warning", "Need priority table")
    movement = _num(p.get("Priority Movement Score"), 0)
    if isinstance(tab, pd.DataFrame) and not tab.empty:
        score_s = _series(tab, ["Greedy Score", "KNN Priority Score", "Priority Score", "Reliability Score"], 60)
        score = float(score_s.max()) if len(score_s) else 60.0
        work = tab.copy()
        work["_Priority Score"] = score_s
        work["Priority Rank 1-14"] = score_s.map(_priority_rank)
        if "Priority Label" not in work.columns:
            work["Priority Label"] = score_s.map(_priority_label)
        # Important rows sorted by ascending rank, as requested.
        work = work.sort_values(["Priority Rank 1-14", "_Priority Score"], ascending=[True, False]).reset_index(drop=True)
        st.session_state["three_center_priority_sorted_20260614"] = work
        chunks = []
        for _, row in work.head(2).iterrows():
            chunks.append(f"{_hour_text(row)} (Rank {int(row.get('Priority Rank 1-14', 14))}, {row.get('Priority Label', '-')})")
        if chunks:
            best_2 = "; ".join(chunks)
        score_unique = int(score_s.round(2).nunique())
        label_unique = int(work["Priority Label"].astype(str).nunique()) if "Priority Label" in work.columns else 999
        if len(work) > 3 and (score_unique <= 1 or label_unique <= 1):
            const_msg = "Priority unreliable / constant score detected"
    reason = "Hour/session, existing metric strength, risk, quality, regime sync, and forecast freshness changed the score."
    if "constant" in str(const_msg).lower():
        reason = "Priority unreliable / constant score detected; do not trust a flat all-day label."
    return {
        "Priority Rank 1–14": _priority_rank(score),
        "Priority Label": _priority_label(score),
        "Best 2 Hours": best_2,
        "Priority Movement Score": round(movement, 1),
        "Constant Score Warning": const_msg,
        "Why priority changed": reason,
        "Dynamic Priority Reliability": p.get("Dynamic Priority Reliability", 0),
        "_score": score,
    }


def _direction_from_regime(metrics: Dict[str, Any]) -> str:
    s = str(metrics.get("Regime Direction") or metrics.get("Current Regime") or "").upper()
    if "BUY" == s or "BULL" in s:
        return "Buy"
    if "SELL" == s or "BEAR" in s:
        return "Sell"
    return "Neutral"


def _decision_summary(ns: dict, ctx: Dict[str, Any], rctx: Dict[str, Any]) -> Dict[str, Any]:
    summary = ctx.get("summary", {}) if isinstance(ctx, dict) else {}
    quality = ctx.get("data_quality_market_feed_health", {}) if isinstance(ctx, dict) else {}
    leak = ctx.get("feature_leakage_guard", {}) if isinstance(ctx, dict) else {}
    drift = ctx.get("distribution_shift_wasserstein_style_drift", {}) if isinstance(ctx, dict) else {}
    anomaly = ctx.get("anomaly_and_shock_detector", {}) if isinstance(ctx, dict) else {}
    fresh = ctx.get("model_decay_forecast_freshness", {}) if isinstance(ctx, dict) else {}
    mfe = ctx.get("mfe_mae_exit_control", {}) if isinstance(ctx, dict) else {}
    rm = rctx.get("metrics", {}) if isinstance(rctx, dict) else {}
    ps = _priority_summary(ns, ctx)
    robustness = _num(summary.get("Forecast Robustness Score"), 0)
    regime_rel = _num(rm.get("Regime Reliable Score", ctx.get("regime_state_reliability", {}).get("Regime Reliability Score", 0) if isinstance(ctx, dict) else 0), 0)
    priority_rel = _num(ps.get("Dynamic Priority Reliability"), 0)
    data_quality = _num(quality.get("Data Quality Score"), 0)
    leakage_risk = _num(leak.get("Leakage Risk %"), 0)
    anomaly_score = _num(anomaly.get("Anomaly Score"), 0)
    freshness = _num(fresh.get("Prediction Freshness", fresh.get("Decayed Confidence Score", 0)), 0)
    confidence = _clip(robustness * .36 + regime_rel * .22 + priority_rel * .18 + data_quality * .14 + freshness * .10 - leakage_risk * .16 - max(0, anomaly_score - 50) * .18)
    risk = _clip(100 - confidence + leakage_risk * .25 + max(0, anomaly_score - 55) * .30)
    direction = _direction_from_regime(rm)
    blocks: List[str] = []
    if leakage_risk >= 65:
        blocks.append("leakage risk high")
    if str(drift.get("Drift Warning", "")).lower().startswith("danger"):
        blocks.append("drift dangerous")
    if anomaly_score >= 65:
        blocks.append("shock/anomaly high")
    if risk >= 70:
        blocks.append("risk too high")
    if "constant" in str(ps.get("Constant Score Warning", "")).lower():
        blocks.append("priority constant")
    if blocks:
        status = "Avoid"
    elif confidence >= 78 and risk < 45 and direction in {"Buy", "Sell"}:
        status = "Enter"
    elif confidence >= 62 and risk < 62:
        status = "Wait"
    else:
        status = "Protect"
    reason = "Blocked by " + ", ".join(blocks[:3]) if blocks else f"Robustness {robustness:.1f}, regime reliability {regime_rel:.1f}, priority reliability {priority_rel:.1f}."
    return {
        "Trade Status": status,
        "Direction": direction,
        "Confidence %": round(confidence, 1),
        "Risk %": round(risk, 1),
        "Best TP Zone": mfe.get("Safer TP Zone", "Need history"),
        "Danger SL Zone": mfe.get("Danger SL Zone", "Need history"),
        "Main Reason": reason,
        "Do-not-trade warning": "YES — " + ", ".join(blocks) if blocks else "NO hard block detected",
    }


def _regime_candidates() -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    def add(source: str, regime: Any, reliability: Any = None, confidence: Any = None) -> None:
        if regime is None or str(regime).strip() in {"", "None", "nan", "{}"}:
            return
        rows.append({"Source": source, "Regime": str(regime), "Reliability": _num(reliability, 55), "Confidence": _num(confidence, reliability if reliability is not None else 55)})

    rctx = st.session_state.get("regime_context_20260614")
    if isinstance(rctx, dict):
        m = rctx.get("metrics", {}) if isinstance(rctx.get("metrics"), dict) else {}
        add("Regime Intelligence", m.get("Current Regime"), m.get("Regime Reliable Score"), m.get("Regime Confidence %"))
    obj = st.session_state.get("dv_pp_regime_summary")
    if isinstance(obj, dict):
        add("Data Visualization", obj.get("current_regime"), obj.get("regime_power_100", obj.get("regime_score_10", 55)), obj.get("regime_power_100", obj.get("regime_score_10", 55)))
    obj = st.session_state.get("lunch_5layer_powerbi_result")
    if isinstance(obj, dict):
        add("Lunch PowerBI", obj.get("current_regime"), obj.get("layer1", {}).get("Regime Score /10", 5) * 10 if isinstance(obj.get("layer1"), dict) else 55, obj.get("bull_probability", 55))
    obj = st.session_state.get("nylo_unified_home_sync_20260612")
    if isinstance(obj, dict):
        summ = obj.get("summary", {}) if isinstance(obj.get("summary"), dict) else {}
        add("Home/Lunch Sync", summ.get("current_powerbi_regime") or summ.get("current_regime"), summ.get("reliability", 55), summ.get("confidence", 55))
    obj = st.session_state.get("final_merged_intelligence_pack_20260612")
    if isinstance(obj, dict):
        add("Merged Intelligence", obj.get("master_regime") or obj.get("current_regime"), obj.get("master_score", 5) * 10, obj.get("forecast_confidence", 55))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["Reliability", "Confidence"], ascending=False).reset_index(drop=True)


def _regime_sync_snapshot(rctx: Dict[str, Any]) -> Dict[str, Any]:
    m = rctx.get("metrics", {}) if isinstance(rctx, dict) else {}
    cand = _regime_candidates()
    conflict = False
    chosen = m.get("Current Regime", "Need sync")
    if isinstance(cand, pd.DataFrame) and not cand.empty:
        conflict = cand["Regime"].astype(str).str.upper().nunique() > 1
        chosen = cand.iloc[0]["Regime"]
    reliability = _num(m.get("Regime Reliable Score"), 0)
    confidence = _num(m.get("Regime Confidence %"), 0)
    shift = _num(m.get("Transition Risk %"), 0)
    trust = "Trusted" if reliability >= 70 and shift < 55 else "Caution"
    return {
        "Current Regime": chosen,
        "Regime Confidence": round(confidence, 1),
        "Regime Reliability": round(reliability, 1),
        "Regime Age": f"{int(_num(m.get('Regime Age Hours'), 0))}h",
        "Shift Risk": round(shift, 1),
        "Regime Trust Reason": f"{trust}; resolver picked highest reliability source" + ("; conflict warning active" if conflict else "; all available sources aligned"),
        "Conflict": conflict,
        "Candidates": cand,
    }


def _major_regime_history(rctx: Dict[str, Any]) -> pd.DataFrame:
    try:
        from . import clean_decision_regime_ui_20260614 as clean
    except Exception:
        import tabs.clean_decision_regime_ui_20260614 as clean
    try:
        return clean._major_regime_history(rctx)
    except Exception:
        return pd.DataFrame()


def _persist_full_metric_regime_history(rctx: Dict[str, Any]) -> pd.DataFrame:
    """Publish the exact Full Metric major-regime table for every synced surface."""
    hist = _major_regime_history(rctx)
    if isinstance(hist, pd.DataFrame) and not hist.empty:
        st.session_state["major_regime_history_df"] = hist.copy()
        st.session_state["full_metric_regime_history_df"] = hist.copy()
        st.session_state["full_metric_regime_history_built_at_20260617"] = pd.Timestamp.now()
    return hist


def _render_metric_detail_section(ns: dict) -> None:
    """Single active Full Metric renderer shared by Lunch and Dinner routes."""
    with st.expander("📂 Open / Close — Full Metric Details + History", expanded=False):
        try:
            _persist_full_metric_regime_history(_regime_context(ns, force=False))
        except Exception:
            pass
        from ui.full_metric_shared_renderer_20260618 import render_full_metric_shared
        render_full_metric_shared(ns)


def _render_powerbi_section(ns: dict, prev_data) -> None:
    with st.expander("📈 Open / Close — Synced PowerBI Price Projection + Actual vs Error", expanded=False):
        st.caption("Separate preserved PowerBI projection section. Actual-vs-error, blue prediction path, bands, and old ML tables stay here.")
        if callable(prev_data):
            try:
                prev_data()
            except Exception as exc:
                st.error("PowerBI / Data Visualization renderer failed safely inside its section.")
                st.exception(exc)
        else:
            st.warning("PowerBI / Data Visualization renderer is not available in this ZIP.")


def _summary_cards(decision: Dict[str, Any], trust: Dict[str, Any], priority: Dict[str, Any], regime: Dict[str, Any]) -> None:
    cards = st.columns(4)
    with cards[0]:
        st.markdown("**Decision Control Panel**")
        st.metric("Trade Status", decision.get("Trade Status", "-"))
        st.caption(f"{decision.get('Direction','-')} • Conf {_fmt(decision.get('Confidence %', 0), '%')} • Risk {_fmt(decision.get('Risk %', 0), '%')}")
    with cards[1]:
        st.markdown("**System Trust Center**")
        st.metric("Robustness", _fmt(trust.get("Robustness Score", 0), "%"))
        st.caption(f"Data {_fmt(trust.get('Data Quality Score', 0), '%')} • Fresh {_fmt(trust.get('Forecast Freshness', 0), '%')}")
    with cards[2]:
        st.markdown("**Dynamic Entry Priority Center**")
        st.metric("Priority Rank", priority.get("Priority Rank 1–14", "-"))
        st.caption(f"{priority.get('Priority Label','-')} • Move {_fmt(priority.get('Priority Movement Score',0), '%')}")
    with cards[3]:
        st.markdown("**Regime Sync Snapshot**")
        st.metric("Current Regime", regime.get("Current Regime", "-"))
        st.caption(f"Rel {_fmt(regime.get('Regime Reliability', 0), '%')} • Shift {_fmt(regime.get('Shift Risk', 0), '%')}")


def _render_master_center(ns: dict) -> None:
    with st.expander("🧠 Open / Close — Master Decision + Reliability + Priority Center", expanded=True):
        st.caption("All other Lunch/Home displays are merged here. Old logic remains available in Advanced Details; summary stays compact for mobile.")
        _render_run_gate(ns, "master_center")
        if not _run_ready():
            try:
                from core.system_wide_completion_20260618 import readiness_message
                st.info(readiness_message(st.session_state, "Lunch Priority"))
            except Exception:
                st.info("The synchronized decision center is not published yet.")
            return
        ctx = _state_context(ns, force=False)
        rctx = _regime_context(ns, force=False)
        decision = _decision_summary(ns, ctx, rctx)
        summary = ctx.get("summary", {}) if isinstance(ctx, dict) else {}
        quality = ctx.get("data_quality_market_feed_health", {}) if isinstance(ctx, dict) else {}
        leak = ctx.get("feature_leakage_guard", {}) if isinstance(ctx, dict) else {}
        drift = ctx.get("distribution_shift_wasserstein_style_drift", {}) if isinstance(ctx, dict) else {}
        fresh = ctx.get("model_decay_forecast_freshness", {}) if isinstance(ctx, dict) else {}
        trust = {
            "Robustness Score": summary.get("Forecast Robustness Score", 0),
            "Data Quality Score": quality.get("Data Quality Score", 0),
            "Leakage Risk": leak.get("Leakage Risk %", 0),
            "Drift Risk": drift.get("Drift Warning", "-"),
            "Forecast Freshness": fresh.get("Prediction Freshness", fresh.get("Decayed Confidence Score", 0)),
            "Main Weakness": summary.get("Main Weakness", "-"),
            "Best Action": summary.get("Best Action Now", "-"),
        }
        priority = _priority_summary(ns, ctx)
        regime = _regime_sync_snapshot(rctx)
        _summary_cards(decision, trust, priority, regime)

        st.markdown("#### A. Decision Control Panel")
        dcols = st.columns(4)
        dcols[0].metric("Trade Status", decision.get("Trade Status", "-"))
        dcols[1].metric("Direction", decision.get("Direction", "-"))
        dcols[2].metric("Confidence", _fmt(decision.get("Confidence %", 0), "%"))
        dcols[3].metric("Risk", _fmt(decision.get("Risk %", 0), "%"))
        d2 = st.columns(2)
        d2[0].metric("Best TP Zone", decision.get("Best TP Zone", "-"))
        d2[1].metric("Danger SL Zone", decision.get("Danger SL Zone", "-"))
        st.info(decision.get("Main Reason", "-"))
        st.caption(f"Do-not-trade warning: {decision.get('Do-not-trade warning', '-')}")

        st.markdown("#### B. System Trust Center")
        t = st.columns(4)
        t[0].metric("Robustness Score", _fmt(trust.get("Robustness Score", 0), "%"))
        t[1].metric("Data Quality Score", _fmt(trust.get("Data Quality Score", 0), "%"))
        t[2].metric("Leakage Risk", _fmt(trust.get("Leakage Risk", 0), "%"))
        t[3].metric("Drift Risk", trust.get("Drift Risk", "-"))
        t2 = st.columns(3)
        t2[0].metric("Forecast Freshness", _fmt(trust.get("Forecast Freshness", 0), "%"))
        t2[1].metric("Main Weakness", trust.get("Main Weakness", "-"))
        t2[2].metric("Best Action", trust.get("Best Action", "-"))

        st.markdown("#### C. Dynamic Entry Priority Center")
        pcols = st.columns(4)
        pcols[0].metric("Priority Rank 1–14", priority.get("Priority Rank 1–14", "-"))
        pcols[1].metric("Priority Label", priority.get("Priority Label", "-"))
        pcols[2].metric("Best 2 Hours", priority.get("Best 2 Hours", "-"))
        pcols[3].metric("Movement Score", _fmt(priority.get("Priority Movement Score", 0), "%"))
        warning = str(priority.get("Constant Score Warning", "-"))
        if "constant" in warning.lower():
            st.warning(warning)
        else:
            st.success(warning)
        st.caption(priority.get("Why priority changed", "-"))

        st.markdown("#### D. Regime Sync Snapshot")
        rcols = st.columns(5)
        rcols[0].metric("Current Regime", regime.get("Current Regime", "-"))
        rcols[1].metric("Regime Confidence", _fmt(regime.get("Regime Confidence", 0), "%"))
        rcols[2].metric("Regime Reliability", _fmt(regime.get("Regime Reliability", 0), "%"))
        rcols[3].metric("Regime Age", regime.get("Regime Age", "-"))
        rcols[4].metric("Shift Risk", _fmt(regime.get("Shift Risk", 0), "%"))
        if regime.get("Conflict"):
            st.warning("Regime conflict detected. Resolver chose the most reliable existing regime source.")
        st.info(regime.get("Regime Trust Reason", "-"))

        with st.expander("Advanced Details — all merged old Lunch/Home sections and sources", expanded=False):
            st.markdown("##### System Trust advanced metrics")
            detail_rows: List[Dict[str, Any]] = []
            for block_name in ["feature_leakage_guard", "data_quality_market_feed_health", "distribution_shift_wasserstein_style_drift", "anomaly_and_shock_detector", "model_decay_forecast_freshness", "market_maker_pressure_proxy", "pca_factor_structure_dashboard", "mfe_mae_exit_control"]:
                block = ctx.get(block_name, {}) if isinstance(ctx, dict) else {}
                if isinstance(block, dict):
                    for k, v in block.items():
                        if not str(k).startswith("_"):
                            detail_rows.append({"Group": block_name.replace("_", " ").title(), "Metric": k, "Value": v})
            if detail_rows:
                st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True, height=360)
            ptab = st.session_state.get("three_center_priority_sorted_20260614")
            if isinstance(ptab, pd.DataFrame) and not ptab.empty:
                st.markdown("##### Priority rows — ascending priority rank")
                show = ptab.drop(columns=[c for c in ["_Priority Score"] if c in ptab.columns])
                st.dataframe(show.head(80), use_container_width=True, hide_index=True, height=360)
            cand = regime.get("Candidates")
            if isinstance(cand, pd.DataFrame) and not cand.empty:
                st.markdown("##### Regime Sync Resolver candidates")
                st.dataframe(cand, use_container_width=True, hide_index=True)
            home_dash = ns.get("_render_home_dashboard")
            if callable(home_dash):
                st.markdown("##### Preserved older Lunch/Home sections")
                try:
                    home_dash()
                except Exception as exc:
                    st.warning(f"Old Home dashboard skipped safely: {exc}")
            text = _safe_json({"Decision Control Panel": decision, "System Trust Center": trust, "Dynamic Entry Priority Center": priority, "Regime Sync Snapshot": {k: v for k, v in regime.items() if k != "Candidates"}})
            _copy_button("📋 Copy Master Decision Center", text, f"copy_master_center_{UNIQUE}")


def _render_lunch_three_sections(ns: dict, prev_data, prev_lunch=None) -> None:
    st.markdown("### 🍱 Lunch / Home — 3 Main Open/Close Sections")
    st.caption("Visible Home/Lunch is now limited to exactly the three requested main sections. Old source logic is preserved inside expanders.")
    _render_metric_detail_section(ns)
    _render_powerbi_section(ns, prev_data)
    _render_master_center(ns)

    # 2026-06-19 RESTORE: user requested every old Lunch/Home field restored,
    # but kept closed so mobile users do not scroll through a very long page.
    # This keeps the final 3-center layout intact while making hidden legacy
    # sections accessible in one closed open/close field.
    with st.expander("🗂️ Open / Close — Restored All Original Lunch Fields", expanded=False):
        st.caption("All preserved older Lunch/Home sections are restored here. The field is closed by default to keep iPhone/mobile scrolling short.")
        if callable(prev_lunch):
            try:
                prev_lunch()
            except Exception as exc:
                st.error("Restored original Lunch renderer failed safely inside its closed field.")
                st.exception(exc)
        else:
            st.info("Original Lunch renderer is not available in this ZIP, but the Full Metric, PowerBI, and Master sections above remain active.")


def _regime_best_action(m: Dict[str, Any]) -> str:
    rel = _num(m.get("Regime Reliable Score"), 0)
    shift = _num(m.get("Transition Risk %"), 100)
    direction = _direction_from_regime(m).upper()
    if rel >= 75 and shift < 45 and direction in {"BUY", "SELL"}:
        return f"FOLLOW {direction} bias with confirmation"
    if rel >= 60:
        return "WAIT / small size only after confirmation"
    return "AVOID — regime not reliable"


def _render_regime_intelligence_center(ns: dict) -> None:
    st.markdown("### 🧭 Regime Intelligence Center")
    st.caption("Home/Lunch, Regime, and Data Visualization use one synced regime context. Hourly spam is hidden in Advanced Details only.")
    # Regime pages never own a second Run/Load control.  The single Settings
    # Run Calculation workflow primes both regime and reliability caches.
    canonical = st.session_state.get("canonical_decision_result_20260617") or {}
    run_id = canonical.get("run_id") if isinstance(canonical, dict) else None
    if not _run_ready() and not isinstance(st.session_state.get("regime_context_20260614"), dict):
        try:
            from core.system_wide_completion_20260618 import readiness_message
            st.info(readiness_message(st.session_state, "Regime History"))
        except Exception:
            st.info("The published regime context is unavailable. Open Settings → Errors / Fix Fast.")
        return
    st.caption(f"Auto-synced from the main Settings calculation • Run ID {run_id or 'legacy cached run'} • resolver uses the highest existing confidence/reliability when sources conflict.")
    rctx = _regime_context(ns, force=False)
    m = rctx.get("metrics", {}) if isinstance(rctx, dict) else {}
    snap = _regime_sync_snapshot(rctx)
    try:
        from core.advanced_analytics_20260615 import render_regime_alpha_delta_metrics
        st.markdown("#### Regime Alpha / Delta Metrics")
        render_regime_alpha_delta_metrics(ns, key="dinner_regime_summary")
    except Exception as exc:
        st.caption(f"Regime Alpha/Delta skipped safely: {exc}")
    top = {
        "Current Regime": snap.get("Current Regime", m.get("Current Regime", "-")),
        "Regime Confidence %": snap.get("Regime Confidence", m.get("Regime Confidence %", 0)),
        "Regime Reliability Score": snap.get("Regime Reliability", m.get("Regime Reliable Score", 0)),
        "Regime Age": snap.get("Regime Age", f"{int(_num(m.get('Regime Age Hours'), 0))}h"),
        "Shift Risk": snap.get("Shift Risk", m.get("Transition Risk %", 0)),
        "Regime Best Action": _regime_best_action(m),
        "Regime Trust Reason": snap.get("Regime Trust Reason", "Need sync"),
    }
    cols = st.columns(4)
    cols[0].metric("Current Regime", top["Current Regime"])
    cols[1].metric("Confidence", _fmt(top["Regime Confidence %"], "%"))
    cols[2].metric("Reliability", _fmt(top["Regime Reliability Score"], "%"))
    cols[3].metric("Regime Age", top["Regime Age"])
    cols2 = st.columns(3)
    cols2[0].metric("Shift Risk", _fmt(top["Shift Risk"], "%"))
    cols2[1].metric("Best Action", top["Regime Best Action"])
    cols2[2].metric("Resolver", "Conflict" if snap.get("Conflict") else "Aligned")
    if snap.get("Conflict"):
        st.warning("Regime Sync Resolver: conflicting regime values found. Chosen regime is the highest reliability/confidence existing source.")
    else:
        st.success("Regime Sync Resolver: available Home/Lunch, Regime, and Data Visualization values are aligned or have one clear source.")
    st.info(top["Regime Trust Reason"])
    cand = snap.get("Candidates")
    with st.expander("Regime Sync Resolver candidates", expanded=bool(snap.get("Conflict"))):
        if isinstance(cand, pd.DataFrame) and not cand.empty:
            st.dataframe(cand, use_container_width=True, hide_index=True)
        else:
            st.info("No separate regime candidates found yet. Run Data Visualization / Lunch first for more sync sources.")
    hist = _persist_full_metric_regime_history(rctx)
    st.markdown("#### 25-Day Major Regime History Table")
    st.caption("Consecutive same-regime hours are aggregated into one regime period.")
    if isinstance(hist, pd.DataFrame) and not hist.empty:
        st.dataframe(hist, use_container_width=True, hide_index=True, height=430)
    else:
        st.info("Need more existing H1/regime history to build the 25-day major regime history table.")
    with st.expander("Advanced Details — hourly regime table + full metrics", expanded=False):
        if m:
            st.dataframe(pd.DataFrame([{"Metric": k, "Value": v} for k, v in m.items()]), use_container_width=True, hide_index=True, height=330)
        raw_hist = rctx.get("history", pd.DataFrame()) if isinstance(rctx, dict) else pd.DataFrame()
        if isinstance(raw_hist, pd.DataFrame) and not raw_hist.empty:
            st.markdown("##### Original/legacy regime history source")
            st.dataframe(raw_hist, use_container_width=True, hide_index=True, height=330)
        else:
            st.info("No hourly regime source table is loaded yet. It remains hidden here by default.")
        text = _safe_json({"Regime Intelligence summary": top, "Regime candidates": cand.to_dict("records") if isinstance(cand, pd.DataFrame) else [], "25-Day Major Regime History Table": hist.to_dict("records") if isinstance(hist, pd.DataFrame) else []})
        _copy_button("📋 Copy Regime Intelligence Summary", text, f"copy_regime_final_{UNIQUE}")
        st.download_button("⬇️ Download Regime Intelligence JSON", text, file_name="regime_intelligence_center.json", mime="application/json", use_container_width=True, key=f"dl_regime_final_{UNIQUE}")


def _render_ai_center() -> None:
    try:
        from .ai_assistant_lite import render_ai_assistant_lite_tab
    except Exception:
        from tabs.ai_assistant_lite import render_ai_assistant_lite_tab
    render_ai_assistant_lite_tab()


def _selector() -> str:
    choices = [("Lunch", "🍱"), ("Regime", "🧭"), ("AI Assistant", "🤖"), ("Research", "🎓"), ("Doo Prime", "🏦")]
    current = st.session_state.get("home_inner_tab", "Lunch")
    if current in {"Data Visualization"}:
        current = "Lunch"
    if current in {"AI Assistant Lite"}:
        current = "AI Assistant"
    names = [x[0] for x in choices]
    if current not in names:
        current = "Lunch"
    st.session_state["home_inner_tab"] = current
    try:
        from ui.safe_tab_switch_20260615 import safe_tab_choice
        selected = safe_tab_choice(
            label="Home tab choice",
            options=names,
            icons=["box-seam", "compass", "robot", "search", "bank"],
            state_key="home_inner_tab",
            widget_key=f"safe_final_three_selector_{UNIQUE}",
            default=current,
            horizontal=True,
            rerun_on_change=False,
        )
    except Exception:
        selected = current
        cols = st.columns(len(choices))
        for i, (name, icon) in enumerate(choices):
            active = st.session_state.get("home_inner_tab") == name
            if cols[i].button(("✅ " if active else "") + f"{icon} {name}", key=f"selector_{i}_{UNIQUE}", use_container_width=True):
                selected = name
                st.session_state["home_inner_tab"] = name
                st.session_state["ui_navigation_click_ts"] = time.time()
                st.session_state["fast_tab_switch_active"] = True
                try:
                    st.rerun()
                except Exception:
                    pass
    return st.session_state.get("home_inner_tab", selected)


def _ai_summary_text() -> str:
    ans = st.session_state.get("ai_lite_last_answer_summary_20260614") or st.session_state.get("ai_lite_last_copy_payload")
    if not ans:
        return "No AI Assistant answer summary yet."
    return str(ans)


def _final_summary_copy(ns: dict, compact: bool = False) -> str:
    ctx = _state_context(ns, force=False)
    rctx = _regime_context(ns, force=False)
    decision = _decision_summary(ns, ctx, rctx) if ctx or rctx else {"Status": "Published synchronized result unavailable"}
    priority = _priority_summary(ns, ctx) if ctx else {"Status": "Published synchronized result unavailable"}
    regime = _regime_sync_snapshot(rctx) if rctx else {"Status": "Published regime snapshot unavailable; inspect Settings → Errors / Fix Fast"}
    hist = _major_regime_history(rctx) if rctx else pd.DataFrame()
    payload = {
        "Decision Control Panel": decision,
        "System Trust Center": {
            "Robustness Score": ctx.get("summary", {}).get("Forecast Robustness Score") if isinstance(ctx, dict) else None,
            "Data Quality Score": ctx.get("data_quality_market_feed_health", {}).get("Data Quality Score") if isinstance(ctx, dict) else None,
            "Leakage Risk": ctx.get("feature_leakage_guard", {}).get("Leakage Risk %") if isinstance(ctx, dict) else None,
            "Drift Risk": ctx.get("distribution_shift_wasserstein_style_drift", {}).get("Drift Warning") if isinstance(ctx, dict) else None,
            "Forecast Freshness": ctx.get("model_decay_forecast_freshness", {}).get("Prediction Freshness") if isinstance(ctx, dict) else None,
        },
        "Dynamic Entry Priority Center": priority,
        "Regime Sync Snapshot": {k: v for k, v in regime.items() if k != "Candidates"},
        "Regime Intelligence summary": rctx.get("metrics", {}) if isinstance(rctx, dict) else {},
        "AI Assistant answer summary": _ai_summary_text(),
    }
    if not compact:
        payload["25-Day Major Regime History Table"] = hist.to_dict("records") if isinstance(hist, pd.DataFrame) else []
    return "\n\nFINAL THREE-CENTER SUMMARY 20260614\n" + _safe_json(payload)


def install(ns: dict) -> None:
    if ns.get("_final_three_center_upgrade_installed_20260614"):
        return

    prev_full = ns.get("_build_lunch_all_copy_text")
    prev_short = ns.get("_build_short_necessary_copy_text")
    if callable(prev_full):
        def _full_with_final_three_center() -> str:
            base = prev_full()
            return str(base) + _final_summary_copy(ns, compact=False)
        ns["_build_lunch_all_copy_text"] = _full_with_final_three_center
    if callable(prev_short):
        def _short_with_final_three_center() -> str:
            base = prev_short()
            return str(base) + _final_summary_copy(ns, compact=True)
        ns["_build_short_necessary_copy_text"] = _short_with_final_three_center

    prev_lunch = ns.get("_render_metric_home_combined_inner_tab")
    prev_data = ns.get("_render_lunch_data_visualization_inner_tab")
    prev_research = ns.get("_render_home_research_inner_20260612")
    prev_doo = ns.get("_render_doo_prime_inner_tab")
    footer = ns.get("render_tab_footer")

    def _show_final() -> None:
        try:
            from core.streamlit_safe_dataframe import install_safe_dataframe_patch
            install_safe_dataframe_patch()
        except Exception:
            pass
        try:
            from core.styles import request_close_sidebar
            request_close_sidebar()
        except Exception:
            pass
        selected = _selector()
        if selected == "Lunch":
            _render_lunch_three_sections(ns, prev_data, prev_lunch)
        elif selected == "Regime":
            _render_regime_intelligence_center(ns)
        elif selected == "AI Assistant":
            _render_ai_center()
        elif selected == "Research":
            if callable(prev_research):
                prev_research()
            else:
                try:
                    import tabs.research as research
                    research.show()
                except Exception as exc:
                    st.error("Research tab could not load safely.")
                    st.exception(exc)
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

    ns["show"] = _show_final
    ns["render_regime_inner_tab_20260614"] = lambda: _render_regime_intelligence_center(ns)
    ns["build_final_three_center_summary_20260614"] = lambda compact=False: _final_summary_copy(ns, compact=compact)
    ns["_final_three_center_upgrade_installed_20260614"] = True
