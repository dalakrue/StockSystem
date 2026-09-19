from __future__ import annotations
import pandas as pd
import streamlit as st

def _payload(state): return state.get('research_adaptation_v18_20260624') or {}
def render_field2(state):
    p=_payload(state)
    if not p: st.info('No saved research sidecar. Run Settings → Run Calculation + Open Lunch.'); return
    st.markdown('#### Research-grade forecast calibration and ensemble evidence')
    rows=[]
    for h,x in p.get('field2',{}).items():
        a=x.get('adaptive_conformal',{});c=x.get('cqr',{});e=x.get('ensemble',{});q=x.get('probability_calibration',{})
        rows.append({'Horizon':f'{h}h','Calibrated forecast':x.get('point_forecast'),'Lower band':c.get('calibrated_lower_bound',a.get('lower')),'Upper band':c.get('calibrated_upper_bound',a.get('upper')),'Target coverage':a.get('target_coverage'),'Realised coverage':a.get('realised_coverage'),'Coverage gap':a.get('coverage_gap'),'Interval width':c.get('interval_width',a.get('interval_width')),'Ensemble agreement':e.get('leave_one_model_out_stability'),'Model disagreement':e.get('model_disagreement'),'Calibration ECE':q.get('expected_calibration_error'),'Sample':x.get('sample_size')})
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
def render_field3(state):
    p=_payload(state); st.markdown('#### Shadow regime transition and structural-break evidence')
    st.json(p.get('field3',{}),expanded=False)
def render_field5(state):
    p=_payload(state); cols=st.columns(4); cols[0].metric('Snapshot','READY' if p else 'MISSING'); cols[1].metric('Run ID',str(p.get('run_id') or '-')[:18]); cols[2].metric('Broker candle',str(p.get('broker_candle_time') or '-')); cols[3].metric('Grounding','HEALTHY' if p else 'CHECK')
    st.caption('The full assistant is an independent main-menu tab. This field performs no training or heavy calculation.')
    if st.button('🤖 Open AI Assistant',key='field5_open_independent_ai',use_container_width=True):
        from core.navigation_authority_20260625 import navigate_to
        navigate_to(st.session_state,'AI Assistant','')
        st.rerun()
    st.dataframe(pd.DataFrame([{'Field':i,'Available':bool(p)} for i in range(1,10)]),use_container_width=True,hide_index=True)
def render_field7(state):
    p=_payload(state); st.markdown('#### Data quality, ADWIN drift and reliability decomposition'); st.dataframe(pd.DataFrame(p.get('field7',{}).get('drift_history',[])),use_container_width=True,hide_index=True); st.json({k:v for k,v in p.get('field7',{}).items() if k!='drift_history'},expanded=False)
def render_field8(state):
    p=_payload(state); st.markdown('#### Model evidence, Reality Check and SPA'); st.json(p.get('field8',{}).get('validation',{}),expanded=False); st.dataframe(pd.DataFrame(p.get('field8',{}).get('model_comparison',[])),use_container_width=True,hide_index=True)
    with st.expander('Open / Close — Field 8 Accuracy/Decision History — Last 25 Days',expanded=False):
        from core.field_789_history_20260625 import build_field_history
        h=build_field_history(state,8)
        if h.empty: st.info('No completed 25-day Field 8 evidence is available yet.')
        else: st.dataframe(h,use_container_width=True,hide_index=True,height=420)

def render_field9(state):
    p=_payload(state); f=p.get('field9',{}); st.markdown('#### Field 9 — Decision Impact, Counterfactual Regret & Stability')
    cols=st.columns(4); cols[0].metric('After-cost EV',f.get('after_cost_expected_value'));cols[1].metric('Conservative EV',f.get('conservative_lower_bound_expected_value'));cols[2].metric('Regret',f.get('counterfactual_regret'));cols[3].metric('Evidence','SUFFICIENT' if f.get('evidence_sufficiency') else 'NOT PROVEN')
    st.dataframe(pd.DataFrame([{'Action':k,'After-cost expected value':v} for k,v in f.get('buy_sell_wait_counterfactual',{}).items()]),use_container_width=True,hide_index=True)
    st.dataframe(pd.DataFrame(f.get('feature_attribution',{}).get('contributions',[])),use_container_width=True,hide_index=True)
    st.json(f.get('feature_attribution',{}).get('reversal_thresholds',{}),expanded=False);st.info(f.get('final_shadow_only_conclusion','No conclusion available.'))
    with st.expander('Open / Close — Field 9 Decision Impact History — Last 25 Days',expanded=False):
        from core.field_789_history_20260625 import build_field_history
        h=build_field_history(state,9)
        if h.empty: st.info('No completed 25-day Field 9 evidence is available yet.')
        else: st.dataframe(h,use_container_width=True,hide_index=True,height=420)

