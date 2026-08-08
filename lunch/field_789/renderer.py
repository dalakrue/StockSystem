import streamlit as st

def render(vm):
    c=vm["context"]; s=c.snapshot
    from ui.lunch_decision_sync_20260626 import render_decision_sync
    render_decision_sync(c, field_name="Field 789", show_latest_row=True)
    st.markdown("### Field 789 — Combined Research, Reliability and Confirmation Evidence")
    st.caption(f"Display-only grouping · freshness anchored to {s.broker_candle_time.isoformat()}")
    st.dataframe(__import__('pandas').DataFrame([{"Canonical Field 1 decision":s.decision,"Field 7 agreement":"READ-ONLY","Field 8 agreement":"READ-ONLY","Field 9 agreement":"READ-ONLY","Combined evidence coverage":"See preserved outputs","Conflict summary":"No model blending","Freshness status":"CANONICAL","run_id":s.run_id,"generation_id":s.generation_id,"snapshot_hash":s.source_snapshot_hash}]),use_container_width=True,hide_index=True)
    tabs=st.tabs(["Field 7 Existing Output","Field 8 Existing Output","Field 9 Existing Output"])
    with tabs[0]:
        from lunch.field_07.renderer import render as r; r(vm)
    with tabs[1]:
        from lunch.field_08.renderer import render as r; r(vm)
    with tabs[2]:
        from lunch.field_09.renderer import render as r; r(vm)
