"""Compact Field 7 Lunch renderer; full diagnostics live in Research Lab."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from lunch.field_07.charts import render_horizon_chart
from lunch.field_07.summary import certificate_rows


def _format(value):
    if value is None or value == "":
        return "INSUFFICIENT EVIDENCE"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render(view_model) -> None:
    summary = view_model["summary"]
    state = view_model["context"].history_repository.state
    st.markdown("### Field 7 — EURUSD H1 Scientific Edge, Model Risk and Research Intelligence")
    st.caption(
        "Experimental shadow validation only. It cannot overwrite the canonical decision, "
        "prediction path, TP/SL engine or priority."
    )
    for warning in view_model["warnings"]:
        st.warning(warning)

    if summary:
        st.markdown("#### EURUSD H1 SCIENTIFIC DECISION CERTIFICATE")
        status = str(summary.get("research_status") or "INSUFFICIENT EVIDENCE")
        risk = float(summary.get("risk_multiplier") or 0.0)
        trust = float(summary.get("research_trust_score") or 0.0)
        top = st.columns(4)
        top[0].metric("Research Status", status)
        top[1].metric("Approved Action", str(summary.get("research_approved_action") or "WAIT"))
        top[2].metric("Trust Score", f"{trust:.1f}/100")
        top[3].metric("Risk Multiplier", f"{risk:.2f}×")
        rows = certificate_rows(summary)
        table = pd.DataFrame([{"Scientific Check": label, "Result": _format(value)} for label, value in rows])
        st.dataframe(table, use_container_width=True, hide_index=True)

        v12 = summary.get("v12_research") if isinstance(summary.get("v12_research"), dict) else {}
        compact = v12.get("compact_results") if isinstance(v12.get("compact_results"), dict) else {}
        if compact:
            st.markdown("#### V12 — Next 10 Research Layers (stored shadow summary)")
            compact_rows = [
                {"Research Check": key.replace("_", " ").title(), "Result": _format(value)}
                for key, value in compact.items()
            ]
            st.dataframe(pd.DataFrame(compact_rows), use_container_width=True, hide_index=True)
            st.caption(
                f"Immutable research snapshot: {str(v12.get('snapshot_hash') or 'UNAVAILABLE')[:20]} "
                "· Production changed: no"
            )
            for warning in list(v12.get("warnings") or [])[:8]:
                st.warning(str(warning))

        v13 = summary.get("v13_research") if isinstance(summary.get("v13_research"), dict) else {}
        compact13 = v13.get("compact_results") if isinstance(v13.get("compact_results"), dict) else {}
        if compact13:
            st.markdown("#### V13 — Decision-Evidence Hardening (stored shadow summary)")
            st.dataframe(
                pd.DataFrame([
                    {"Research Check": key.replace("_", " ").title(), "Result": _format(value)}
                    for key, value in compact13.items()
                ]),
                use_container_width=True, hide_index=True,
            )
            st.caption(
                f"Snapshot {str(v13.get('snapshot_hash') or 'UNAVAILABLE')[:20]} · "
                "chronological/purged/embargoed · production changed: no"
            )
            statuses = v13.get("module_statuses") if isinstance(v13.get("module_statuses"), dict) else {}
            if statuses:
                st.dataframe(
                    pd.DataFrame([
                        {"V13 Layer": key.replace("_", " ").title(), "Status": value,
                         "Sample Size": (v13.get("sample_sizes") or {}).get(key, 0)}
                        for key, value in statuses.items()
                    ]),
                    use_container_width=True, hide_index=True,
                )
            for warning in list(v13.get("warnings") or [])[:8]:
                st.warning(str(warning))
    else:
        st.info("The scientific certificate will appear after a successful Settings calculation stores it.")

    st.markdown("#### 25-Day Completed-H1 Decision-Level Evidence")
    evidence = view_model.get("decision_evidence")
    if not isinstance(evidence, pd.DataFrame) or evidence.empty:
        st.info("No completed cached H1 candles are available for Field 7 decision evidence.")
    else:
        preferred = [
            "event_time_utc", "Broker Time", "Close", "Shadow Decision",
            "Decision Level /10", "Actionability", "Trend Agreement",
            "Momentum 3H (pips)", "Momentum 6H (pips)", "ATR 14H (pips)",
            "Volatility 12H (pips)", "Session (UTC)", "Data Quality",
            "Evidence Class", "Settled Status", "Production Decision Changed",
        ]
        columns = [column for column in preferred if column in evidence.columns]
        st.dataframe(evidence.loc[:, columns], use_container_width=True, hide_index=True, height=560)
        st.caption(
            f"{len(evidence):,} causal completed-H1 rows are available. These rows are decision support, "
            "not a substitute for settled forecast-validation outcomes."
        )

    st.markdown("#### Horizon Gate — stored Settings-run results")
    if view_model["horizons"].empty:
        st.info("No stored settled horizon results are available.")
    else:
        st.dataframe(view_model["horizons"], use_container_width=True, hide_index=True)
        render_horizon_chart(view_model["horizons"])

    st.markdown("#### Latest 25 Canonical Research Runs")
    if view_model["history"].empty:
        st.info("Research-run history is empty. Missing settled history is not manufactured.")
    else:
        st.dataframe(view_model["history"], use_container_width=True, hide_index=True, height=520)

    if st.button("Open Full Research Lab", use_container_width=True, key="open_full_research_lab_v11"):
        st.session_state["active_page"] = "Research Lab"
        st.session_state["tab_choice"] = "Research Lab"
        st.session_state["active_subpage"] = ""
        st.rerun()

    from ui.lunch_v14_shadow import compact
    compact(view_model["context"].history_repository.state,["student_t_state","mixture_of_experts","venn_abers_calibration","caviar_tail_risk","conformal_risk_control","wasserstein_robust_decision","asymmetric_copula","knockoff_selection","proper_scoring","causal_news_impact"],"#### V14 Readiness — 10 New Shadow Methods")
    with st.expander("Advanced Causal Forecast, Regime and Reliability Evidence", expanded=False):
        from ui.lunch_advanced_causal_20260624 import render_for_field
        render_for_field(state, 7)

    with st.expander("Research-Grade Named Challenger Evidence", expanded=False):
        from ui.lunch_research_grade_shadow_20260624 import render_for_field as render_research_grade
        render_research_grade(state, 7)
    with st.expander("Ten-Foundation Active Research Evidence", expanded=False):
        from ui.lunch_ten_foundation_active_20260624 import render_for_field as render_ten_foundation
        render_ten_foundation(state, 7)


    with st.expander("Unified Research-Grade Shadow Validation", expanded=False):
        from ui.lunch_research_grade_system_v17_20260624 import render_for_field
        render_for_field(state, 7)

    with st.expander("Unified V19 Research Pipeline", expanded=False):
        from ui.lunch_unified_shadow_v19_20260624 import render_for_field
        render_for_field(state, 7)


    payload = view_model.get("session_drift_cpa") or {}
    with st.expander("Field 7 — ADWIN Session Drift + Conditional Predictive Ability Gate", expanded=False):
        if payload.get("status") == "OK":
            current = payload.get("current", {})
            cols = st.columns(5)
            cols[0].metric("Decision Role", str(current.get("research_decision_role") or "-"))
            cols[1].metric("Drift Status", str(current.get("drift_status") or "-"))
            cols[2].metric("CPA P-value", str(current.get("cpa_p_value") or "-"))
            cols[3].metric("Preferred Forecast", str(current.get("preferred_forecast") or "-"))
            cols[4].metric("Comparable Count", str(current.get("comparable_count") or "-"))
            hist = __import__("pandas").DataFrame(payload.get("history") or [])
            st.markdown("#### Field 7 Session Drift and Conditional Edge History — Last 25 Days")
            if not hist.empty:
                st.dataframe(hist, use_container_width=True, hide_index=True, height=480)
            else:
                st.info("No additive Field 7 history was published for this run.")
        else:
            st.info("Field 7 additive drift/CPA evidence is not published for the current run.")
