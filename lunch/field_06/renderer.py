from __future__ import annotations
import streamlit as st


def render(view_model) -> None:
    context = view_model["context"]
    state = context.history_repository.state
    st.markdown("### Field 6 — End-to-End Preparation")
    from core.field6_quant_history_20260622 import ALL_FIELD6_TABLES, QUANT_V6_FIELD6_VIEWS, LABEL_TO_TABLE, render_field6_quant_history
    options = [
        "Combined Sentiment + Technical + Decision History",
        "Existing Future Strategy Research History / System Readiness",
        *[label for label, _ in QUANT_V6_FIELD6_VIEWS],
        *[label for label, _ in ALL_FIELD6_TABLES],
    ]
    choice = st.selectbox("Field 6 nested view", options, key="field6_nested_selector_v11")
    if choice.startswith("Combined"):
        from core.lunch_broker_sentiment_ai_history_20260622 import render_field6_combined_history
        render_field6_combined_history(state)
    elif choice.startswith("Existing Future"):
        from ui.system_readiness_20260621 import render_system_readiness
        render_system_readiness(state=state)
    else:
        render_field6_quant_history(state, LABEL_TO_TABLE[choice])
    from ui.lunch_v14_shadow import compact
    compact(state,["student_t_state","caviar_tail_risk","asymmetric_copula","knockoff_selection","causal_news_impact","wasserstein_robust_decision"],"#### V14 Compact Histories")
    with st.expander("Advanced Causal Forecast, Regime and Reliability Evidence", expanded=False):
        from ui.lunch_advanced_causal_20260624 import render_for_field
        render_for_field(state, 6)

    with st.expander("Research-Grade Named Challenger Evidence", expanded=False):
        from ui.lunch_research_grade_shadow_20260624 import render_for_field as render_research_grade
        render_research_grade(state, 6)
    with st.expander("Ten-Foundation Active Research Evidence", expanded=False):
        from ui.lunch_ten_foundation_active_20260624 import render_for_field as render_ten_foundation
        render_ten_foundation(state, 6)


    with st.expander("Unified Research-Grade Shadow Validation", expanded=False):
        from ui.lunch_research_grade_system_v17_20260624 import render_for_field
        render_for_field(state, 6)

    with st.expander("Unified V19 Research Pipeline", expanded=False):
        from ui.lunch_unified_shadow_v19_20260624 import render_for_field
        render_for_field(state, 6)


    payload = state.get("field6_session_bayesian_fusion_20260625") or {}
    with st.expander("Field 6 — Session-Conditioned Sentiment–Technical Bayesian Fusion", expanded=False):
        if payload.get("status") == "OK":
            current = payload.get("current", {})
            row = current.get("row", {})
            cols = st.columns(5)
            cols[0].metric("Decision Role", str(current.get("decision_role") or payload.get("decision_role") or "-"))
            cols[1].metric("EUR Impact", str(current.get("eur_impact_probability") or "-"))
            cols[2].metric("USD Impact", str(current.get("usd_impact_probability") or "-"))
            cols[3].metric("Fused BUY", str(current.get("eurusd_net_buy_probability") or "-"))
            cols[4].metric("Fused SELL", str(current.get("eurusd_net_sell_probability") or "-"))
            if row:
                st.dataframe(__import__("pandas").DataFrame([row]), use_container_width=True, hide_index=True)
            hist = __import__("pandas").DataFrame(payload.get("history") or [])
            st.markdown("#### Field 6 Session Sentiment–Technical Decision Role History — Last 25 Days")
            if not hist.empty:
                st.dataframe(hist, use_container_width=True, hide_index=True, height=480)
            else:
                st.info("No additive Field 6 history was published for this run.")
        else:
            st.info("Field 6 additive fusion evidence is not published for the current run.")
