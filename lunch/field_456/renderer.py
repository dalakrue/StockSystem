import streamlit as st

def render(vm):
    c=vm["context"]; s=c.snapshot
    from ui.lunch_decision_sync_20260626 import render_decision_sync
    render_decision_sync(c, field_name="Field 456", show_latest_row=True)
    st.markdown("### Field 456 — Combined Decision, AI and Preparation Evidence")
    st.caption(f"Display-only grouping · {s.run_id} · {s.generation_id} · {s.source_snapshot_hash}")
    st.dataframe(__import__('pandas').DataFrame([{"Canonical Field 1 decision":s.decision,"Field 4 agreement":"READ-ONLY","Field 5 agreement":"READ-ONLY","Field 6 agreement":"READ-ONLY","Conflict summary":"See each preserved output","run_id":s.run_id,"generation_id":s.generation_id,"snapshot_hash":s.source_snapshot_hash}]),use_container_width=True,hide_index=True)
    tabs=st.tabs(["Field 4 Existing Output","Field 5 Existing Output","Field 6 Existing Output","Field 1 Synchronization Summary"])
    with tabs[0]:
        from lunch.field_04.renderer import render as r; r(vm)
    with tabs[1]:
        from lunch.field_05.renderer import render as r; r(vm)
    with tabs[2]:
        from lunch.field_06.renderer import render as r; r(vm)
    with tabs[3]: st.json({"decision":s.decision,"run_id":s.run_id,"generation_id":s.generation_id,"snapshot_hash":s.source_snapshot_hash})
