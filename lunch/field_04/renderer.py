from __future__ import annotations
import streamlit as st


def render(view_model) -> None:
    context = view_model["context"]
    state = context.history_repository.state
    st.markdown("### Field 4 — Dinner Combined Field")
    from ui.lunch_four_core_fields_20260619 import _canonical, _render_regime_combined_logic
    from ui.lunch_field4_overall_history_20260622 import render_overall_history
    render_overall_history(state, _canonical(state))
    with st.expander("Advanced Existing Histories", expanded=False):
        _render_regime_combined_logic(state)
    from ui.lunch_v14_shadow import compact
    compact(state,["wasserstein_robust_decision","conformal_risk_control"],"#### V14 Robust Decision Evidence")
    with st.expander("Advanced Causal Forecast, Regime and Reliability Evidence", expanded=False):
        from ui.lunch_advanced_causal_20260624 import render_for_field
        render_for_field(state, 4)

    with st.expander("Research-Grade Named Challenger Evidence", expanded=False):
        from ui.lunch_research_grade_shadow_20260624 import render_for_field as render_research_grade
        render_research_grade(state, 4)
    with st.expander("Ten-Foundation Active Research Evidence", expanded=False):
        from ui.lunch_ten_foundation_active_20260624 import render_for_field as render_ten_foundation
        render_ten_foundation(state, 4)


    with st.expander("Unified Research-Grade Shadow Validation", expanded=False):
        from ui.lunch_research_grade_system_v17_20260624 import render_for_field
        render_for_field(state, 4)

    with st.expander("Unified V19 Research Pipeline", expanded=False):
        from ui.lunch_unified_shadow_v19_20260624 import render_for_field
        render_for_field(state, 4)
