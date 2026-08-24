"""Read-only lightweight Field 8 renderer; filtering never recalculates models."""
import streamlit as st
from lunch.field_08.tables import prepare_table
def render(view_model):
    state=view_model['context'].history_repository.state
    st.markdown('### Field 8 — Alpha–Beta–Delta Causal Evidence')
    st.caption('Shadow evidence only. Production BUY/SELL/WAIT, protected weights and Field 1 remain unchanged.')
    with st.expander('Session Direction Confirmation History — Last 25 Broker Days', expanded=True):
        from ui.lunch_one_hour_direction_20260626 import render_for_field
        render_for_field(state, 8)
    raw=view_model.get('raw_table',view_model['table']);ident=view_model['identity'];s=view_model.get('summaries',{})
    payload = state.get("field8_session_calibration_spa_20260625") or {}
    st.caption(f"Run {ident.get('run_id','—')} · Generation {ident.get('generation_id','—')} · Snapshot {ident.get('snapshot_hash','')[:20] or '—'}")
    identity_match = bool(view_model.get('identity_match', False))
    if raw.empty or not identity_match:
        import pandas as pd
        st.warning('Field 8 could not load the exact immutable publication identity. Stale or mismatched rows were not displayed as current.')
        st.dataframe(pd.DataFrame([view_model.get('diagnostic',{})]),use_container_width=True,hide_index=True)
    cols=st.columns(5)
    additive_current = payload.get('current', {}) if payload.get('status') == 'OK' else {}
    cards=[('Alpha state',s.get('alpha_beta_delta_state')),('Beta stability',s.get('beta_instability')),('Delta',s.get('delta_alpha_h')),('Structural break',s.get('structural_break_state')),('Shadow trust',s.get('research_integrated_trust_score'))]
    if additive_current and (raw.empty or not identity_match):
        cards=[('Decision role', additive_current.get('decision_role')), ('SPA status', additive_current.get('spa_status')), ('Coverage debt', additive_current.get('coverage_debt')), ('Winner', additive_current.get('confidence_set_winner')), ('Sample count', additive_current.get('sample_count'))]
    for c,(label,value) in zip(cols,cards):c.metric(label,'—' if value is None else value)
    if not (raw.empty or not identity_match):
        st.caption(f"Path calibration: {s.get('path_reliability','—')} · Regime calibration: {s.get('regime_reliability','—')} · Coverage: {s.get('rolling_coverage','—')} · DMA: {s.get('dynamic_model_status','—')} · MCS/validation: {s.get('model_confidence_set_status','—')} / {s.get('validation_status','—')}")
        filters={}
        labels=[('horizon','forecast_horizon'),('maturity','maturity_status'),('regime','regime'),('alpha_beta_delta_state','alpha_beta_delta_state'),('evidence_status','evidence_status'),('structural_break_state','structural_break_state'),('validation_status','validation_status')]
        with st.expander('Field 8 filters',expanded=False):
            fcols=st.columns(3)
            for i,(key,col) in enumerate(labels):
                options=['ALL']+sorted(str(x) for x in raw[col].dropna().unique()) if col in raw else ['ALL']
                filters[key]=fcols[i%3].selectbox(key.replace('_',' ').title(),options,key=f'f8_{key}')
        table=prepare_table(raw,view_model['context'].search_query,filters)
        st.dataframe(table,use_container_width=True,hide_index=True,height=600)
        st.caption(f'{len(table):,} stored causal evidence rows. Filters are read-only and trigger no fitting or heavy calculation.')
    with st.expander("Advanced Causal Forecast, Regime and Reliability Evidence", expanded=False):
        from ui.lunch_advanced_causal_20260624 import render_for_field
        render_for_field(state, 8)
    with st.expander("Research v15 — MCS, DMA, Proper Scores, Calibration and Risk", expanded=False):
        evidence=state.get("field8_quant_research_v15_20260624", {})
        if evidence:
            st.json(evidence, expanded=False)
        else:
            st.info("Run Settings → Run Calculation + Open Lunch to publish this shadow evidence for the current canonical run.")

    with st.expander("Research-Grade Named Challenger Evidence", expanded=False):
        from ui.lunch_research_grade_shadow_20260624 import render_for_field as render_research_grade
        render_research_grade(state, 8)
    with st.expander("Ten-Foundation Active Research Evidence", expanded=False):
        from ui.lunch_ten_foundation_active_20260624 import render_for_field as render_ten_foundation
        render_ten_foundation(state, 8)


    with st.expander("Unified Research-Grade Shadow Validation", expanded=False):
        from ui.lunch_research_grade_system_v17_20260624 import render_for_field
        render_for_field(state, 8)

    with st.expander("Unified V19 Research Pipeline", expanded=False):
        from ui.lunch_unified_shadow_v19_20260624 import render_for_field
        render_for_field(state, 8)


    payload = state.get("field8_session_calibration_spa_20260625") or {}
    with st.expander("Field 8 — Session-Calibrated Adaptive Conformal + SPA Model Confidence Gate", expanded=False):
        if payload.get("status") == "OK":
            current = payload.get("current", {})
            cols = st.columns(5)
            cols[0].metric("Decision Role", str(current.get("decision_role") or "-"))
            cols[1].metric("SPA Status", str(current.get("spa_status") or "-"))
            cols[2].metric("Coverage Debt", str(current.get("coverage_debt") or "-"))
            cols[3].metric("Winner", str(current.get("confidence_set_winner") or "-"))
            cols[4].metric("Sample Count", str(current.get("sample_count") or "-"))
            hist = __import__("pandas").DataFrame(payload.get("history") or [])
            st.markdown("#### Field 8 Session Calibration and Superior-Predictive-Ability History — Last 25 Days")
            if not hist.empty:
                st.dataframe(hist, use_container_width=True, hide_index=True, height=480)
            else:
                st.info("No additive Field 8 calibration history was published for this run.")
        else:
            st.info("Field 8 additive calibration/SPA evidence is not published for the current run.")
