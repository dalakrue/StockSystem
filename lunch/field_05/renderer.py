from __future__ import annotations
import streamlit as st


def render(view_model) -> None:
    context = view_model["context"]
    state = context.history_repository.state
    st.markdown("### Field 5 — Grounded AI Assistant")
    st.caption(f"Answers are grounded to run {context.snapshot.run_id}; no regime or prediction engine is rerun.")
    from tabs.ai_assistant_compact_20260619 import render_compact_ai_assistant
    render_compact_ai_assistant()
    from ui.lunch_v14_shadow import compact
    compact(context.history_repository.state,["venn_abers_calibration","caviar_tail_risk","mixture_of_experts","wasserstein_robust_decision","causal_news_impact"],"#### Saved V14 Evidence Available to Assistant")
    with st.expander("Advanced Causal Forecast, Regime and Reliability Evidence", expanded=False):
        from ui.lunch_advanced_causal_20260624 import render_for_field
        render_for_field(state, 5)

    with st.expander("Research-Grade Named Challenger Evidence", expanded=False):
        from ui.lunch_research_grade_shadow_20260624 import render_for_field as render_research_grade
        render_research_grade(state, 5)
    with st.expander("Ten-Foundation Active Research Evidence", expanded=False):
        from ui.lunch_ten_foundation_active_20260624 import render_for_field as render_ten_foundation
        render_ten_foundation(state, 5)


    with st.expander("Unified Research-Grade Shadow Validation", expanded=False):
        from ui.lunch_research_grade_system_v17_20260624 import render_for_field
        render_for_field(state, 5)
