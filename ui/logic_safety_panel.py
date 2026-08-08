"""Streamlit panel for Logic Safety Guard + Hidden Danger Engine.

Installer wraps existing show() functions non-destructively and appends an
open/close safety section after the original page renders.
"""
from __future__ import annotations

import json
from typing import Any, Dict


def _safe_json(obj: Any) -> str:
    def default(o):
        try:
            import pandas as pd
            if isinstance(o, pd.DataFrame):
                return o.head(500).to_dict(orient="records")
        except Exception:
            pass
        return str(o)
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, default=default)
    except Exception:
        return str(obj)


def _summary_text(result: Dict[str, Any], location: str = "") -> str:
    sb = result.get("scoreboard", {})
    guard = result.get("no_trade_guard", {})
    danger = result.get("hidden_danger", {})
    drift = result.get("prediction_drift", {})
    regime = result.get("regime_warning", {})
    dq = result.get("data_quality", {})
    cal = result.get("confidence_calibration", {})
    chain = result.get("decision_reason_chain", {})
    lines = [
        "Logic Safety Guard + Hidden Danger Engine",
        f"Location: {location}",
        f"Data source: {result.get('dataframe_source')}",
        "",
        f"Logic Health Score: {sb.get('Logic Health Score')} ({result.get('logic_health', {}).get('label')})",
        f"Hidden Danger Level: {sb.get('Hidden Danger Level')}",
        f"Original Decision: {guard.get('original_decision')}",
        f"Safety Decision: {guard.get('safety_adjusted_decision')}",
        f"Main Danger: {danger.get('main_danger')} — {danger.get('reason')}",
        f"Prediction Drift: {drift.get('drift_level')} | Trust: {drift.get('forecast_trust_adjustment')}",
        f"Regime Risk: {regime.get('risk_label')} | Current: {regime.get('current_regime')}",
        f"Data Quality: {dq.get('status')} | {dq.get('most_serious_issue')}",
        f"Confidence Calibration: {cal.get('label')} | Gap: {cal.get('confidence_gap')}",
        "",
        "Supporting Reasons:",
        *[f"- {x}" for x in chain.get('supporting_reasons', [])],
        "",
        "Warning Reasons:",
        *[f"- {x}" for x in chain.get('warning_reasons', [])],
    ]
    return "\n".join(lines)


def render_logic_safety_panel(location: str = "Lunch/Home") -> None:
    try:
        import streamlit as st
        import pandas as pd
        from core.logic_safety import run_full_safety_check
    except Exception as exc:
        try:
            import streamlit as st
            st.warning(f"Logic Safety Guard could not import safely: {exc}")
        except Exception:
            pass
        return

    with st.expander("🛡️ Open / Close — Logic Safety Guard + Hidden Danger Engine", expanded=False):
        st.caption("Safety wrapper around existing calculations only. It does not replace original prediction/regime/KNN/Greedy/PowerBI logic.")
        c1, c2 = st.columns([1.3, 1])
        with c1:
            run = st.button("▶ Run Safety Check", use_container_width=True, key=f"logic_safety_run_{location.replace('/', '_').replace(' ', '_')}")
        with c2:
            clear = st.button("Clear Safety Result", use_container_width=True, key=f"logic_safety_clear_{location.replace('/', '_').replace(' ', '_')}")
        key = f"logic_safety_result_{location.replace('/', '_').replace(' ', '_')}"
        if clear:
            st.session_state.pop(key, None)
            st.info("Safety result cleared. Run again when needed.")
        if run:
            try:
                with st.spinner("Running safety wrapper checks..."):
                    st.session_state[key] = run_full_safety_check(st.session_state)
            except Exception as exc:
                st.error("Logic Safety Guard failed, but original app remains running.")
                st.exception(exc)
                return
        result = st.session_state.get(key)
        if not isinstance(result, dict):
            st.info("Press **Run Safety Check**. Heavy safety/audit checks do not auto-run on app open.")
            return

        sb = result.get("scoreboard", {})
        cols = st.columns(4)
        cols[0].metric("Logic Health", sb.get("Logic Health Score", "-"))
        cols[1].metric("Danger", sb.get("Hidden Danger Level", "-"))
        cols[2].metric("No-Trade Guard", sb.get("No-Trade Guard Status", "-"))
        cols[3].metric("Prediction Drift", sb.get("Prediction Drift", "-"))
        cols2 = st.columns(4)
        cols2[0].metric("Regime Risk", sb.get("Regime Change Risk", "-"))
        cols2[1].metric("Data Quality", sb.get("Data Quality Status", "-"))
        cols2[2].metric("Calibration", sb.get("Confidence Calibration", "-"))
        cols2[3].metric("Signal Stability", sb.get("Signal Stability", "-"))

        tabs = st.tabs([
            "Score + Danger", "No-Trade", "Drift + Regime", "Conflict", "Data + Bias", "Reason Chain", "Audit", "Copy / Export"
        ])
        with tabs[0]:
            h = result.get("logic_health", {})
            d = result.get("hidden_danger", {})
            st.markdown("#### 🧠 Logic Health Score")
            st.write({k: h.get(k) for k in ["score", "label", "trust_level", "main_positive", "main_negative", "defensive_action"]})
            st.markdown("#### ⚠️ Hidden Danger Detector")
            st.write({k: d.get(k) for k in ["danger_level", "main_danger", "reason", "suggested_defensive_action"]})
            if d.get("dangers"):
                st.dataframe(pd.DataFrame(d.get("dangers")), use_container_width=True, hide_index=True)
        with tabs[1]:
            st.markdown("#### 🛑 No-Trade Guard")
            st.write(result.get("no_trade_guard", {}))
            st.caption("Original decision is preserved; safety-adjusted decision is shown separately.")
        with tabs[2]:
            st.markdown("#### 📉 Prediction Drift Monitor")
            st.write(result.get("prediction_drift", {}))
            st.markdown("#### 🔁 Regime Change Early Warning")
            st.write(result.get("regime_warning", {}))
            st.markdown("#### 📊 Signal Stability Memory")
            st.write(result.get("signal_stability", {}))
        with tabs[3]:
            st.markdown("#### 🧩 Logic Conflict Matrix")
            cm = result.get("conflict_matrix", {})
            st.write({k: cm.get(k) for k in ["status", "conflict_count", "mixed_count"]})
            if cm.get("rows"):
                st.dataframe(pd.DataFrame(cm.get("rows")), use_container_width=True, hide_index=True, height=420)
        with tabs[4]:
            st.markdown("#### 🧪 Data Quality Guard")
            st.write(result.get("data_quality", {}))
            st.markdown("#### 🕰️ Lookahead Bias Guard")
            st.write(result.get("lookahead_bias", {}))
            st.markdown("#### 🎯 Confidence Calibration")
            st.write(result.get("confidence_calibration", {}))
        with tabs[5]:
            st.markdown("#### 🧠 Decision Reason Chain")
            st.write(result.get("decision_reason_chain", {}))
            st.markdown("#### 🧪 Shadow Backtest Mode")
            st.write(result.get("shadow_backtest", {}))
        with tabs[6]:
            st.markdown("#### 📚 Long-Term Logic Audit Table")
            st.write(result.get("audit_summary", {}))
            audit = result.get("audit_table")
            if audit is not None and hasattr(audit, "empty") and not audit.empty:
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    hours = ["All"] + sorted([int(x) for x in audit["Hour"].dropna().unique().tolist()]) if "Hour" in audit.columns else ["All"]
                    hour = st.selectbox("By Hour", hours, key=f"logic_safety_audit_hour_{location}")
                with col_b:
                    danger_filter = st.selectbox("Danger Filter", ["All", "High Danger Only", "Critical Danger Only", "Failed Prediction Only"], key=f"logic_safety_audit_danger_{location}")
                with col_c:
                    side = st.selectbox("Decision Filter", ["All", "BUY Only", "SELL Only", "WAIT Only", "NO TRADE Only"], key=f"logic_safety_audit_side_{location}")
                view = audit.copy()
                if hour != "All" and "Hour" in view.columns:
                    view = view[view["Hour"] == int(hour)]
                if danger_filter == "High Danger Only" and "Danger Level" in view.columns:
                    view = view[view["Danger Level"].isin(["High", "Critical"])]
                elif danger_filter == "Critical Danger Only" and "Danger Level" in view.columns:
                    view = view[view["Danger Level"] == "Critical"]
                token = {"BUY Only": "BUY", "SELL Only": "SELL", "WAIT Only": "WAIT", "NO TRADE Only": "NO"}.get(side)
                if token and "Safety Decision" in view.columns:
                    view = view[view["Safety Decision"].astype(str).str.upper().str.contains(token, na=False)]
                st.dataframe(view, use_container_width=True, hide_index=True, height=420)
            else:
                st.info("Audit table is empty until usable history is loaded.")
        with tabs[7]:
            st.markdown("#### Copy / Export Safety Report")
            summary = _summary_text(result, location)
            st.text_area("Copy Safety Summary", summary, height=260, key=f"logic_safety_summary_text_{location}")
            st.download_button("⬇ Export Safety Summary TXT", data=summary.encode("utf-8"), file_name="logic_safety_summary.txt", mime="text/plain", use_container_width=True, key=f"logic_safety_dl_txt_{location}")
            st.download_button("⬇ Export Full Safety JSON", data=_safe_json(result).encode("utf-8"), file_name="logic_safety_full_report.json", mime="application/json", use_container_width=True, key=f"logic_safety_dl_json_{location}")
            audit = result.get("audit_table")
            if audit is not None and hasattr(audit, "to_csv"):
                st.download_button("⬇ Export Safety Audit CSV", data=audit.to_csv(index=False).encode("utf-8"), file_name="logic_safety_audit.csv", mime="text/csv", use_container_width=True, key=f"logic_safety_dl_csv_{location}")


def install(namespace: Dict[str, Any], location: str = "Lunch/Home") -> None:
    """Wrap a module-level show() function and append the safety panel."""
    original = namespace.get("show")
    if not callable(original):
        return
    if getattr(original, "_logic_safety_wrapped", False):
        return
    def wrapped_show(*args, **kwargs):
        result = original(*args, **kwargs)
        try:
            render_logic_safety_panel(location=location)
        except Exception as exc:
            try:
                import streamlit as st
                st.warning(f"Logic Safety Guard display skipped safely: {exc}")
            except Exception:
                pass
        return result
    wrapped_show._logic_safety_wrapped = True
    namespace["show"] = wrapped_show
