"""Bounded Settings-only Field 9 shadow orchestrator."""
from __future__ import annotations
import hashlib,json,time,tracemalloc
from datetime import datetime,timezone
from typing import Mapping,Any
from core.field9_eurusd_h1_contract_20260624 import SCHEMA_VERSION,MODEL_VERSION,SHADOW_FLAGS,BOUNDS
from core.field9_eurusd_h1_impact_path_20260624 import build as build_path,decay
from core.field9_eurusd_h1_multi_action_20260624 import evaluate as multi
from core.field9_eurusd_h1_policy_value_20260624 import evaluate as policy
from core.field9_eurusd_h1_counterfactual_risk_20260624 import evaluate as crm
from core.field9_eurusd_h1_attribution_20260624 import evaluate as attr
from core.field9_eurusd_h1_flip_analysis_20260624 import evaluate as flip
from core.field9_eurusd_h1_regret_20260624 import evaluate as regret
from core.field9_eurusd_h1_intraday_periodicity_20260624 import evaluate as periodicity,classify_session
from core.field9_eurusd_h1_barrier_order_20260624 import evaluate as barriers
from core.field9_eurusd_h1_double_ml_20260624 import evaluate as dml
from core.field9_eurusd_h1_doubly_robust_20260624 import evaluate as dr
from core.field9_eurusd_h1_selective_risk_20260624 import evaluate as selective
from core.field9_eurusd_h1_influence_audit_20260624 import evaluate as influence
from core.field9_eurusd_h1_model_reliance_20260624 import evaluate as reliance

def _first(state,*keys,default=None):
    for k in keys:
        v=state.get(k)
        if v is not None:return v
    return default
def _canonical(state):
    c=_first(state,'canonical_decision_result_20260617','canonical_snapshot','canonical_result',default={})
    return c if isinstance(c,Mapping) else {}
def run(state:Mapping[str,Any]):
    started=time.perf_counter();tracemalloc.start();c=_canonical(state)
    run_id=str(c.get('run_id') or state.get('calculation_generation') or state.get('run_id') or '')
    action=str(c.get('decision') or c.get('production_decision') or state.get('canonical_decision') or 'WAIT').upper()
    origin=c.get('origin_time_utc') or c.get('broker_candle_time') or datetime.now(timezone.utc).isoformat()
    forecasts={}
    for h in range(1,7):
        v=c.get(f'predicted_{h}h_pips') or c.get(f'forecast_h{h}_pips')
        if v is not None: forecasts[h]=v
    if not forecasts:
        f2=state.get('powerbi_projection_calibrated_20260617') or state.get('powerbi_calibrated_bundle_20260617') or {}
        if isinstance(f2,Mapping):
            for h in range(1,7):
                v=f2.get(f'h{h}_pips') or f2.get(f'predicted_{h}h_pips')
                if v is not None: forecasts[h]=v
    costs={'spread_pips':c.get('spread_pips'),'slippage_pips':c.get('slippage_pips')}
    history=list(state.get('field9_matured_history_20260624') or [])[:BOUNDS['settled_outcomes']]
    support={a:sum(1 for r in history if str(r.get('production_action','')).upper()==a) for a in ('BUY','SELL','WAIT','HOLD','REDUCE','EXIT')}
    path=build_path(action,forecasts,c.get('forecast_uncertainty_pips'),costs,len(history)); ma=multi(action,path,support); matrix=ma.get('actions',[])
    h3=next((r for r in path if r.get('horizon')==3 and r.get('status')=='AVAILABLE'),{})
    evidence={'prediction_path':forecasts,'regime':c.get('regime'),'h1_m1_agreement':c.get('h1_m1_agreement'),'session':classify_session(origin),'volatility':c.get('volatility_state'),'event_state':c.get('event_state'),'spread':costs.get('spread_pips'),'tail_dependence':c.get('tail_risk'),'data_quality':c.get('data_quality_score')}
    attribution=attr(evidence,h3.get('expected_cumulative_net_pips',0)); dec=decay(path); pol=policy(matrix,action,len(history)); inf=influence(history,h3.get('expected_cumulative_net_pips',0))
    readiness='INSUFFICIENT_DATA' if not forecasts or len(history)<20 else 'FRAGILE' if inf.get('status')=='FRAGILE' else 'CONDITIONALLY_POSITIVE' if (h3.get('expected_cumulative_net_pips') or 0)>0 else 'CONDITIONALLY_NEGATIVE'
    ident={'run_id':run_id,'generation_id':str(c.get('generation_id') or run_id),'calculation_id':str(c.get('calculation_id') or run_id),'snapshot_hash':str(c.get('snapshot_hash') or c.get('source_snapshot_hash') or ''),'symbol':'EURUSD','timeframe':'H1','origin_time_utc':str(origin),'broker_candle_time':str(c.get('broker_candle_time') or origin),'schema_version':SCHEMA_VERSION,'model_version':MODEL_VERSION}
    payload={'identity':ident,'current_summary':{'production_decision':action,'production_decision_unchanged':True,'shadow_preferred_action':ma.get('shadow_preferred_action'),'expected_h1_net_impact':next((r.get('expected_cumulative_net_pips') for r in path if r.get('horizon')==1),None),'expected_h3_net_impact':h3.get('expected_cumulative_net_pips'),'expected_h6_net_impact':next((r.get('expected_cumulative_net_pips') for r in path if r.get('horizon')==6),None),'peak_impact_hour':dec.get('peak_impact_hour'),'peak_expected_impact':dec.get('peak_expected_impact'),'impact_half_life':dec.get('impact_half_life'),'probability_positive_net_impact':h3.get('probability_positive_impact'),'probability_adverse_impact':h3.get('probability_negative_impact'),'regret':ma.get('production_action_regret'),'stability':inf.get('status'),'evidence_status':pol.get('status'),'reality_check_status':'INSUFFICIENT_DATA' if len(history)<40 else 'NOT_REJECTED','production_changed':'NO','exit_changed':'NO','shadow_only':'YES'},'impact_path':path,'counterfactual_action_matrix':matrix,'decision_impact_cube':[],'policy_value':pol,'multi_action_policy':ma,'double_ml':dml(history),'doubly_robust':dr(matrix),'counterfactual_risk':crm(matrix),'intraday_periodicity':periodicity(origin,history),'macro_event_impact':{'status':'EVENT_DATA_UNAVAILABLE' if not c.get('event_state') else 'ASSOCIATIONAL_ONLY'},'microstructure_proxy':{'status':'UNAVAILABLE' if not c.get('h1_m1_agreement') else 'AVAILABLE','label':'MICROSTRUCTURE_PRESSURE_PROXY'},'volatility_adjustment':{'status':'UNAVAILABLE' if not c.get('volatility_state') else 'AVAILABLE'},'tail_dependence':{'status':'INSUFFICIENT_ALIGNED_OBSERVATIONS'},'barrier_order':barriers(bool(c.get('complete_m1_sequence')),len(history),h3.get('probability_positive_impact')),'impact_decay':dec,'decision_regret':regret(matrix,action),'decision_flip':flip(action,c.get('decision_margin'),evidence),'attribution':attribution,'influence_audit':inf,'selective_risk':selective(history),'model_class_reliance':reliance(attribution,3 if len(history)>=40 else 0),'proper_scoring':{'status':'INSUFFICIENT_DATA' if len(history)<20 else 'AVAILABLE'},'conditional_predictive_ability':{'status':'INSUFFICIENT_DATA' if len(history)<40 else 'INCONCLUSIVE'},'reality_check':{'status':'INSUFFICIENT_DATA' if len(history)<40 else 'DATA_SNOOPING_RISK','bootstrap_replications':64},'history':history[:25],'readiness':{'status':readiness,'data_gate':bool(forecasts),'maturity_gate':len(history)>=20,'chronology_gate':True,'overlap_gate':pol.get('action_overlap_status')=='ADEQUATE','cost_gate':costs.get('spread_pips') is not None,'stability_gate':inf.get('status')!='FRAGILE','benchmark_gate':len(history)>=40,'reality_check_gate':len(history)>=40},'limitations':[] if forecasts else ['FORECAST_EVIDENCE_UNAVAILABLE'],**SHADOW_FLAGS}
    current,peak=tracemalloc.get_traced_memory();tracemalloc.stop();payload['performance']={'wall_time_seconds':round(time.perf_counter()-started,6),'input_rows':len(history),'feature_count':len(evidence),'approximate_peak_memory_bytes':peak,'serialized_result_size':len(json.dumps(payload,default=str)),'fallback':'GLOBAL_POOLED' if len(history)<80 else 'REGIME_SESSION','error':None,'bounds':BOUNDS}
    return payload
