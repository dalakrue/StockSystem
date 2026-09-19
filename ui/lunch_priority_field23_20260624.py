from __future__ import annotations
import pandas as pd
import streamlit as st
from core.services.priority_field23_service_20260624 import read_saved

def render_field2(state):
    p=read_saved(state)
    if not p.get('ok'): st.info('Priority Field 2 intelligence is not published for this run. Use Settings → Run Calculation + Open Lunch.'); return
    s=p['prediction_path_snapshot']; st.caption(f"Saved-only · shadow-only · run {s['run_id']} · origin {s['forecast_origin']}")
    c=st.columns(4);c[0].metric('Reliability',f"{s['reliability']:.1%}");c[1].metric('Breakout probability',f"{s['breakout_probability']:.1%}");c[2].metric('Reversal probability',f"{s['reversal_probability']:.1%}");c[3].metric('Status',s['abstention_status'])
    rows=[]
    for i,h in enumerate(s['horizons']):
        rows.append({'Horizon':f'{h}h','Expected':s['expected_path'][i],'Median':s['median_path'][i],'P10':s['quantile_paths']['p10'][i],'P25':s['quantile_paths']['p25'][i],'P75':s['quantile_paths']['p75'][i],'P90':s['quantile_paths']['p90'][i],'Conformal lower':s['conformal_intervals'][str(h)]['lower'],'Conformal upper':s['conformal_intervals'][str(h)]['upper']})
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    with st.expander('Model paths and dynamic weights',False):
        st.dataframe(pd.DataFrame([s['model_weights']]),use_container_width=True,hide_index=True);st.json(s['model_paths'])
    with st.expander('Feature attribution and interval coverage',False): st.json({'feature_attribution':s['feature_attribution'],'coverage':s['coverage_diagnostics'],'warnings':s['warnings']})

def render_field3(state):
    p=read_saved(state)
    if not p.get('ok'): st.info('Priority Field 3 intelligence is not published for this run. Use Settings → Run Calculation + Open Lunch.'); return
    s=p['regime_intelligence_snapshot'];st.caption(f"Saved-only · shadow-only · run {s['run_id']} · broker candle {s['broker_candle_time']}")
    c=st.columns(4);c[0].metric('Higher',s['higher_regime']);c[1].metric('Middle',s['middle_regime']);c[2].metric('Lower',s['lower_regime']);c[3].metric('Reliability',f"{s['reliability']:.1%}")
    st.dataframe(pd.DataFrame([{'Changepoint':s['changepoint_probability'],'Segment age':s['segment_age'],'Expected remaining':s['expected_remaining_duration'],'Unknown score':s['unknown_regime_score'],'Agreement':s['model_agreement'],'Historical support':s['historical_support'],'Abstention':s['abstention_status']}]),use_container_width=True,hide_index=True)
    with st.expander('Hierarchical probabilities and transitions',False): st.json({'regime_probabilities':s['regime_probabilities'],'hierarchical_path':s['hierarchical_path'],'transition_1h':s['transition_probabilities_1h'],'transition_3h':s['transition_probabilities_3h'],'transition_6h':s['transition_probabilities_6h'],'drivers':s['transition_drivers']})
    with st.expander('Changepoint, duration and reset evidence',False): st.json({'changed_dimensions':s['changed_dimensions'],'boundary_confidence':s['boundary_confidence'],'soft_reset_required':s['soft_reset_required'],'hard_reset_required':s['hard_reset_required'],'duration_distribution':s['duration_distribution'],'warnings':s['warnings']})
