from __future__ import annotations
from typing import Mapping,Any
import pandas as pd
import streamlit as st

def render_for_field(state:Mapping[str,Any],field:int)->None:
    p=state.get('ten_foundation_active_20260624') or {}
    if not p:
        st.info('Ten-foundation active evidence is unavailable. Run Settings → Run Calculation + Open Lunch once.')
        return
    st.caption(f"SHADOW / RESEARCH · run_id {p.get('run_id')} · broker candle {p.get('broker_candle_time')} · Field 1 decision unchanged: {p.get('production_decision')}")
    if field==2:
        rows=[]
        for h,r in (p.get('horizons') or {}).items():
            e=r.get('shadow_ensemble',{}); c=r.get('cqr',{}); a=r.get('adaptive_conformal',{}); d=r.get('dm',{})
            rows.append({'Horizon':f'H{h}','Production':r.get('production_prediction'),'Shadow ensemble':e.get('point'),'Dominant model':e.get('dominant_model'),'Effective models':e.get('effective_model_count'),'Disagreement':e.get('model_disagreement'),'CQR lower':(c.get('corrected_interval') or {}).get('lower'),'CQR median':(c.get('corrected_interval') or {}).get('median'),'CQR upper':(c.get('corrected_interval') or {}).get('upper'),'Coverage':a.get('realized_rolling_coverage'),'Coverage debt':a.get('coverage_debt'),'DM verdict':d.get('verdict')})
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        st.dataframe(pd.DataFrame([{'Horizon':f'H{h}',**(r.get('shadow_ensemble',{}).get('weights') or {})} for h,r in p.get('horizons',{}).items()]),use_container_width=True,hide_index=True)
    elif field==3:
        st.json({'production_regime':p.get('markov_regime',{}).get('production_regime'),'shadow_regime':p.get('markov_regime'),'changepoint':p.get('changepoint')},expanded=False)
    elif field==4: st.json({'forecast_regime_agreement':1-(p.get('markov_regime',{}).get('regime_entropy') or 1),'model_selected':p.get('model_selection'),'structural_break_warning':p.get('changepoint'),'actionability':p.get('meta_label')},expanded=False)
    elif field==5: st.json({'run_id':p.get('run_id'),'canonical_broker_time':p.get('broker_candle_time'),'evidence_used':['saved adaptive intervals','saved regime probabilities','saved model weights','saved actionability and validation'],'answerable_snapshot':{'horizons':p.get('horizons'),'regime':p.get('markov_regime'),'changepoint':p.get('changepoint'),'actionability':p.get('meta_label'),'validation':{'pbo':p.get('pbo'),'dsr':p.get('dsr')}},'limitations':p.get('limitations')},expanded=False)
    elif field==6:
        st.dataframe(pd.DataFrame([{'Horizon':f'H{h}','Settlement':r.get('settlement_status'),'Interval status':r.get('adaptive_conformal',{}).get('status'),'CQR status':r.get('cqr',{}).get('status'),'DM sample':r.get('dm',{}).get('sample_count')} for h,r in p.get('horizons',{}).items()]),use_container_width=True,hide_index=True)
    elif field==7: st.json({'forecast_regime_conflict':p.get('markov_regime',{}).get('regime_ambiguity'),'production_shadow_conflict':p.get('field9',{}).get('best_shadow_action')!=str(p.get('production_decision')).upper(),'model_disagreement':p.get('horizons',{}).get('3',{}).get('shadow_ensemble',{}).get('model_disagreement'),'coverage_conflict':p.get('horizons',{}).get('3',{}).get('adaptive_conformal',{}).get('under_coverage_warning'),'changepoint_warning':p.get('changepoint',{}).get('status'),'evidence_sufficiency':p.get('field9',{}).get('evidence_sufficiency')},expanded=False)
    elif field==8:
        st.dataframe(pd.DataFrame([{'Horizon':f'H{h}',**r.get('dm',{})} for h,r in p.get('horizons',{}).items()]),use_container_width=True,hide_index=True); st.json({'PBO':p.get('pbo'),'DSR':p.get('dsr'),'promotion_eligible':bool(p.get('pbo',{}).get('sample_sufficiency')) and (p.get('dsr',{}).get('deflated_sharpe_probability') or 0)>.95,'limitations':p.get('limitations')},expanded=False)
    elif field==9: st.json(p.get('field9') or {},expanded=False)
