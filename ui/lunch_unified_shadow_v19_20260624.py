"""Read-only lazy renderer for V19 unified sidecar."""
from __future__ import annotations
import pandas as pd
import streamlit as st

def _p(state):
    v=state.get('unified_shadow_pipeline_v19_20260624'); return v if isinstance(v,dict) else {}
def _table(rows,height=460):
    if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,height=height)
    else: st.info('Insufficient evidence. No missing history was copied or fabricated.')
def render_priority_summary(state):
    p=_p(state)
    with st.expander('Current-Hour AI Priority Summary',expanded=False):
        if not p: st.info('No saved V19 evidence for this canonical run.'); return
        s=p.get('priority_summary',{})
        for label,key in [('Priority 1','priority_1'),('Priority 2','priority_2'),('Priority 3','priority_3'),('Current decision','current_decision'),('Less-risky action','less_risky_action'),('Current regime','current_regime'),('Regime disagreement','regime_disagreement'),('Prediction-path state','prediction_path_state'),('Reliability','reliability'),('Uncertainty','uncertainty'),('Principal reason','principal_reason'),('Principal risk','principal_risk'),('Reversal condition','reversal_condition'),('Evidence sufficiency','evidence_sufficiency'),('Broker candle time','broker_candle_time')]: st.markdown(f'**{label}:** {s.get(key) if s.get(key) not in (None,"") else "Insufficient evidence"}')
def render_for_field(state,field):
    p=_p(state)
    if not p: st.info('No unified V19 shadow evidence is stored.'); return
    st.caption(f"Run {p.get('run_id')} · broker candle {p.get('broker_candle_time')} · {p.get('model_version')} · SHADOW ONLY")
    if field==2:
        rows=[]
        for h,r in p.get('field2',{}).items(): rows.append({'horizon':h,'predicted price':r.get('predicted_price'),'conformal lower':(r.get('conformal_band') or {}).get('lower'),'conformal upper':(r.get('conformal_band') or {}).get('upper'),'coverage':r.get('interval_coverage'),'sharpness':r.get('interval_sharpness'),'MAE':r.get('path_mae'),'RMSE':r.get('path_rmse'),'epistemic uncertainty':r.get('epistemic_uncertainty'),'path stability':r.get('whole_path_stability'),'trusted horizon':r.get('trusted_forecast_horizon'),'evidence':r.get('evidence_sufficiency')})
        _table(rows)
    elif field==3:
        _table([{'standard':k,**v} for k,v in p.get('field3',{}).get('standards',{}).items()]); st.warning(p.get('field3',{}).get('consensus_regime')) if 'WAIT PREFERRED' in str(p.get('field3',{}).get('consensus_regime')) else st.success(p.get('field3',{}).get('consensus_regime'))
    elif field==4:_table(p.get('histories',{}).get('field4',[]))
    elif field in (6,7,8):_table(p.get('histories',{}).get(f'field{field}',[]),560)
    render_priority_summary(state)
