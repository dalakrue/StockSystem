from __future__ import annotations
import streamlit as st
from lunch.field_02.charts import render_existing_charts


def render(view_model) -> None:
    context = view_model["context"]
    state = context.history_repository.state
    st.markdown("### Field 2 — Power BI Price Prediction Projection")
    from ui.lunch_decision_sync_20260626 import render_decision_sync
    render_decision_sync(context, field_name="Field 2", show_latest_row=True)
    st.caption("Historical, present and future visuals use the already-published Settings generation.")
    from ui.lunch_one_hour_direction_20260626 import render_for_field
    render_for_field(state, 2)
    render_existing_charts(context.history_repository.state)
    from ui.lunch_unified_quant_visuals_20260624 import render as render_quant_visuals, render_priority_summary
    render_quant_visuals(state)
    render_priority_summary(state)
    with st.expander("Advanced Existing Field 2 Projection", expanded=False):
        from ui.lunch_four_core_fields_20260619 import _render_powerbi, _render_evidence
        _render_powerbi(context.history_repository.state)
        _render_evidence("FIELD_2", context.history_repository.state, "field2_v11")
    with st.expander("Breakout-Aware Prediction Path — Shadow", expanded=False):
        from ui.lunch_breakout_regime_shadow_20260624 import render_field2
        render_field2(state)
    from ui.lunch_v14_shadow import compact
    compact(context.history_repository.state,["student_t_state","caviar_tail_risk","venn_abers_calibration","proper_scoring"],"#### V14 Robust Path, Tail Boundaries and Calibration")
    with st.expander("Advanced Causal Forecast, Regime and Reliability Evidence", expanded=False):
        from ui.lunch_advanced_causal_20260624 import render_for_field
        render_for_field(state, 2)

    with st.expander("Research-Grade Named Challenger Evidence", expanded=False):
        from ui.lunch_research_grade_shadow_20260624 import render_for_field as render_research_grade
        render_research_grade(state, 2)
    with st.expander("Ten-Foundation Active Research Evidence", expanded=False):
        from ui.lunch_ten_foundation_active_20260624 import render_for_field as render_ten_foundation
        render_ten_foundation(state, 2)


    with st.expander("Unified Research-Grade Shadow Validation", expanded=False):
        from ui.lunch_research_grade_system_v17_20260624 import render_for_field
        render_for_field(state, 2)

    with st.expander("Priority Multi-Model Prediction Path Intelligence", expanded=False):
        from ui.lunch_priority_field23_20260624 import render_field2 as render_priority_field2
        render_priority_field2(state)

    with st.expander("Unified V19 Research Pipeline", expanded=False):
        from ui.lunch_unified_shadow_v19_20260624 import render_for_field
        render_for_field(state, 2)
