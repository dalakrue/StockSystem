from __future__ import annotations
import streamlit as st


def render(view_model) -> None:
    context = view_model["context"]
    from ui.lunch_decision_sync_20260626 import render_decision_sync
    render_decision_sync(context, field_name="Field 3", show_latest_row=True)
    state = context.history_repository.state
    st.markdown("### Field 3 — Regime 3-Standards History")
    from ui.lunch_one_hour_direction_20260626 import render_for_field
    render_for_field(state, 3)
    from ui.priority_sync_v9 import render_priority_sync_v9
    render_priority_sync_v9(state)
    from ui.lunch_four_core_fields_20260619 import _canonical, _render_regime_history, _render_regime_lifecycle, _render_evidence
    canonical = _canonical(state)
    try:
        from ui.lunch_field3_regime_lifecycle_monitor_20260701 import render_field3_regime_lifecycle_monitor
        render_field3_regime_lifecycle_monitor(state, canonical)
    except Exception as exc:
        state["field3_regime_lifecycle_render_error_20260701"] = f"{type(exc).__name__}: {exc}"
        st.warning(f"Institutional Field 3 lifecycle monitor skipped safely: {type(exc).__name__}: {exc}")
    _render_regime_lifecycle(canonical)
    from ui.lunch_field3_validators_v10 import render_field3_validators
    render_field3_validators(state, canonical)
    _render_regime_history(state)
    _render_evidence("FIELD_3", state, "field3_v11")
    with st.expander("Unified Regime Decision Layer — Shadow", expanded=False):
        from ui.lunch_breakout_regime_shadow_20260624 import render_field3
        render_field3(state)
    from ui.lunch_v14_shadow import compact
    compact(state,["mixture_of_experts","venn_abers_calibration","asymmetric_copula"],"#### V14 Contextual Expert and Dependence Evidence")
    with st.expander("Advanced Causal Forecast, Regime and Reliability Evidence", expanded=False):
        from ui.lunch_advanced_causal_20260624 import render_for_field
        render_for_field(state, 3)

    with st.expander("Research-Grade Named Challenger Evidence", expanded=False):
        from ui.lunch_research_grade_shadow_20260624 import render_for_field as render_research_grade
        render_research_grade(state, 3)
    with st.expander("Ten-Foundation Active Research Evidence", expanded=False):
        from ui.lunch_ten_foundation_active_20260624 import render_for_field as render_ten_foundation
        render_ten_foundation(state, 3)


    with st.expander("Unified Research-Grade Shadow Validation", expanded=False):
        from ui.lunch_research_grade_system_v17_20260624 import render_for_field
        render_for_field(state, 3)

    with st.expander("Priority Hierarchical Regime Intelligence", expanded=False):
        from ui.lunch_priority_field23_20260624 import render_field3 as render_priority_field3
        render_priority_field3(state)

    with st.expander("Unified V19 Research Pipeline", expanded=False):
        from ui.lunch_unified_shadow_v19_20260624 import render_for_field
        render_for_field(state, 3)
