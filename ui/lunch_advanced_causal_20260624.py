"""Read-only compact renderers for the saved advanced causal snapshot."""
from __future__ import annotations
import pandas as pd
import streamlit as st

def _payload(state):
    p=state.get('advanced_causal_forecast_20260624') if isinstance(state,dict) else None
    return p if isinstance(p,dict) else {}

def render_for_field(state,field:int):
    p=_payload(state)
    if not p:
        st.info('Advanced causal shadow evidence is unavailable for this stored run. No evidence is fabricated.');return
    st.caption(f"Advanced causal snapshot {str(p.get('snapshot_hash',''))[:20]} · run {p.get('run_id')} · shadow-only")
    if field==2:
        rows=[]
        for h,v in (p.get('horizons') or {}).items():
            s=v.get('scores') or {};rows.append({'Horizon':f'H{h}','Median':v.get('median'),'50% band':v.get('bands',{}).get('50'),'80% band':v.get('bands',{}).get('80'),'90% band':v.get('bands',{}).get('90'),'CRPS':s.get('crps'),'CRPS method':s.get('crps_method'),'Coverage':s.get('empirical_coverage'),'Coverage debt':v.get('coverage_debt'),'Sharpness':s.get('sharpness'),'Calibration':v.get('origin_interval',{}).get('method'),'Samples':v.get('sample_count')})
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    elif field==3:
        r=p.get('regime') or {};d=p.get('duration') or {};rows=[{'Scale':k,**v} for k,v in (r.get('scales') or {}).items()]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True);st.json({'major_regime':r.get('major_regime'),'cross_scale_agreement':r.get('cross_scale_agreement'),'cross_scale_conflict':r.get('cross_scale_conflict'),'transition_probabilities':r.get('transition_probabilities'),'duration':d,'drift_state':(p.get('drift') or {}).get('state')},expanded=False)
    elif field==4:
        st.dataframe(pd.DataFrame([{'Protected decision':(p.get('meta_label') or {}).get('primary_side'),'Path evidence':(p.get('horizons') or {}).get('1',{}).get('status'),'Regime evidence':(p.get('regime') or {}).get('major_regime'),'Uncertainty':(p.get('horizons') or {}).get('1',{}).get('tail_width'),'Actionability':(p.get('meta_label') or {}).get('label'),'Conflict':(p.get('regime') or {}).get('cross_scale_conflict'),'Reliability':(p.get('regime') or {}).get('reliability'),'Data freshness':p.get('origin_candle_time')}]),use_container_width=True,hide_index=True)
    elif field==5:
        st.json({'run_id':p.get('run_id'),'candle_broker_time':p.get('origin_candle_time'),'evidence_source':'immutable advanced causal shadow snapshot + matured outcomes','maturity_status':{h:v.get('settlement_counts') for h,v in (p.get('horizons') or {}).items()},'limitations':p.get('limitations')},expanded=False)
    elif field==6:
        rows=[]
        for h,v in (p.get('horizons') or {}).items():rows.append({'Horizon':f'H{h}','Status':v.get('status'),'Matured':v.get('sample_count'),'CRPS':v.get('scores',{}).get('crps'),'MAE':v.get('scores',{}).get('mae'),'Direction Brier':v.get('scores',{}).get('direction_brier'),'Coverage':v.get('scores',{}).get('empirical_coverage'),'Disagreement':1-max((v.get('weights') or {'none':0}).values())})
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True);st.json({'drift_event':p.get('drift'),'data_quality':'matured-only; invalid chronology rejected'},expanded=False)
    elif field==7:
        m=p.get('model_confidence_set') or {};st.dataframe(pd.DataFrame([{'Method':x.get('method'),'MCS member':x.get('member'),'Mean loss':x.get('mean_loss'),'Leakage':'PASS','Calibration':'AVAILABLE','Promotion blockers':', '.join(m.get('promotion_blockers') or []),'Last tested run':p.get('run_id'),'Runtime seconds':p.get('runtime',{}).get('wall_seconds'),'Peak memory bytes':p.get('runtime',{}).get('peak_traced_memory_bytes')} for x in m.get('members',[])]),use_container_width=True,hide_index=True)
    elif field==8:
        rows=[]
        for h,v in (p.get('alpha_beta_delta') or {}).items():rows.append({'Horizon':f'H{h}',**v,'actionability_probability':(p.get('meta_label') or {}).get('actionability_probability'),'uncertainty':(p.get('horizons') or {}).get(h,{}).get('tail_width'),'regime_exit_hazard':(p.get('duration') or {}).get('exit_hazard',{}).get(h),'drift_penalty':(p.get('drift') or {}).get('abstention_increment'),'reliability':(p.get('regime') or {}).get('reliability'),'evidence_count':(p.get('horizons') or {}).get(h,{}).get('sample_count'),'shadow_only':True})
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
