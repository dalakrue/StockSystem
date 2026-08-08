"""Ground AI canonical evidence sidecar (2026-06-24).
Additive, immutable, JSON-serializable, leakage-safe and shadow-only.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from hashlib import sha256
from math import erf, exp, pi, sqrt
from typing import Any, Mapping, Sequence
import json, math, statistics, time
SCHEMA_VERSION="ground-ai-evidence/2026-06-24/v1"
SUPPORTED={SCHEMA_VERSION}; HORIZONS=("H1","H3","H6")
MANDATORY=("run_id","snapshot_id","symbol","timeframe","broker_candle_time","production_decision","field2","field3","source_field_map")

def _m(v): return v if isinstance(v,Mapping) else {}
def _first(*xs,default=None):
    for x in xs:
        if x not in (None,"",[],{}): return x
    return default
def _num(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception:return None
def _pick(d,*keys):
    d=_m(d)
    for k in keys:
        if k in d and d[k] not in (None,""):return d[k]
    return None
def _hash(x):return sha256(json.dumps(x,sort_keys=True,default=str,separators=(",",":")).encode()).hexdigest()

def execution_key(canonical:Mapping[str,Any],model_version="ground-ai-v1"):
    c=_m(canonical); return _hash([c.get('run_id'),c.get('symbol'),c.get('timeframe'),c.get('broker_candle_time') or c.get('latest_completed_candle_time'),c.get('input_hash'),model_version])

def _horizon(c,h):
    f2=_m(_first(c.get('field2'),c.get('forecast'),c.get('predictions'),default={}))
    hd=_m(_first(f2.get(h),f2.get(h.lower()),default={}))
    n=h[1:]
    return {'prediction':_first(hd.get('prediction'),hd.get('mean'),_pick(f2,f'prediction_{h.lower()}',f'predicted_{n}h_price')),
      'lower':_first(hd.get('lower'),_pick(f2,f'lower_{h.lower()}',f'lower_{n}h')),
      'upper':_first(hd.get('upper'),_pick(f2,f'upper_{h.lower()}',f'upper_{n}h')),
      'probability_up':_first(hd.get('probability_up'),_pick(f2,f'probability_up_{h.lower()}',f'prob_up_{n}h')),
      'probability_down':_first(hd.get('probability_down'),_pick(f2,f'probability_down_{h.lower()}',f'prob_down_{n}h')),
      'reliability':_first(hd.get('reliability'),f2.get('reliability')),'uncertainty':_first(hd.get('uncertainty'),f2.get('uncertainty')),
      'error':_first(hd.get('error'),hd.get('mae'),f2.get('error')),'coverage':_first(hd.get('coverage'),f2.get('coverage')),
      'settlement_status':_first(hd.get('settlement_status'),hd.get('status'),'UNSETTLED')}

def build_contract(canonical:Mapping[str,Any],research:Mapping[str,Any]|None=None)->dict[str,Any]:
    c=dict(canonical); r=_m(research); reg=_m(_first(c.get('field3'),c.get('regime'),default={}))
    run=str(_first(c.get('run_id'),c.get('calculation_id'),c.get('canonical_calculation_id'),default=''))
    candle=str(_first(c.get('broker_candle_time'),c.get('latest_completed_candle_time'),_m(c.get('market')).get('latest_completed_candle_time'),default=''))
    field2={h:_horizon(c,h) for h in HORIZONS}
    field3={'major_regime':_first(reg.get('major_regime'),reg.get('regime'),c.get('major_regime')),
      'regime_age':_first(reg.get('regime_age'),reg.get('age')),'expected_duration':reg.get('expected_duration'),'remaining_duration':reg.get('remaining_duration'),
      'transition_probabilities':_first(reg.get('transition_probabilities'),{h:reg.get(f'transition_{h.lower()}') for h in HORIZONS}),
      'alpha':_first(reg.get('alpha'),c.get('alpha')),'delta':_first(reg.get('delta'),c.get('delta')),'delta_acceleration':_first(reg.get('delta_acceleration'),c.get('delta_acceleration')),
      'changepoint_probability':_first(r.get('changepoint_probability'),reg.get('changepoint_probability')),
      'regime_stability':_first(r.get('regime_stability_score'),reg.get('regime_stability')),'reliability':reg.get('reliability')}
    out={'schema_version':SCHEMA_VERSION,'run_id':run,'snapshot_id':str(_first(c.get('snapshot_id'),run,default='')),'symbol':str(_first(c.get('symbol'),'EURUSD')),
      'timeframe':str(_first(c.get('timeframe'),'H1')),'broker_candle_time':candle,'snapshot_created_at':str(_first(c.get('snapshot_created_at'),c.get('created_at'),candle)),
      'production_decision':_first(c.get('production_decision'),c.get('decision'),_m(c.get('decision_product')).get('decision')),
      'decision_scores':_first(c.get('decision_scores'),_m(c.get('decision_product')).get('scores'),{}),'current_price':_first(c.get('current_price'),_m(c.get('market')).get('current_price')),
      'field2':field2,'field3':field3,'field4_technical_summary':_first(c.get('field4_technical_summary'),c.get('technical_summary')),
      'field6_session_pattern_evidence':_first(c.get('field6_session_pattern_evidence'),c.get('session_pattern_evidence'),{}),'latest_ranked_nlp_evidence':_first(c.get('latest_ranked_nlp_evidence'),c.get('nlp_evidence'),[]),
      'top_positive_contributors':_first(r.get('top_positive_contributors'),c.get('top_positive_contributors'),[]),'top_negative_contributors':_first(r.get('top_negative_contributors'),c.get('top_negative_contributors'),[]),
      'data_freshness_status':_first(c.get('data_freshness_status'),'UNKNOWN'),'leakage_safety_status':_first(r.get('leakage_safety_status'),'SAFE_BY_ORIGIN_CONTRACT'),
      'settlement_status':{h:field2[h]['settlement_status'] for h in HORIZONS},'missing_evidence':[],
      'source_field_map':{'production_decision':'Field 1','field2':'Field 2','field3':'Field 3','field4_technical_summary':'Field 4','field6_session_pattern_evidence':'Field 6','latest_ranked_nlp_evidence':'NLP'}}
    out['missing_evidence']=[k for k in MANDATORY if out.get(k) in (None,"",{},[])]
    out['evidence_hash']=_hash(out); return out

def validate_contract(p:Mapping[str,Any],visible:Mapping[str,Any]|None=None)->dict[str,Any]:
    p=_m(p); v=_m(visible); errors=[]
    if p.get('schema_version') not in SUPPORTED:errors.append('UNSUPPORTED_SCHEMA')
    for k in MANDATORY:
        if p.get(k) in (None,"",{},[]):errors.append('MISSING_'+k.upper())
    for k in ('run_id','snapshot_id','symbol','timeframe','broker_candle_time'):
        if v.get(k) not in (None,'') and str(v.get(k))!=str(p.get(k)):errors.append('MISMATCH_'+k.upper())
    if p.get('missing_evidence'):errors.append('MANDATORY_EVIDENCE_INCOMPLETE')
    return {'valid':not errors,'errors':errors,'evidence_status':'VALID' if not errors else 'EVIDENCE_INSUFFICIENT'}

def evidence_item(p,field_id,metric_key,value):
    return {'run_id':p.get('run_id'),'field_id':field_id,'metric_key':metric_key,'broker_candle_time':p.get('broker_candle_time'),'value':value,'evidence_status':'AVAILABLE' if value not in (None,'') else 'MISSING'}

def classify_intent(q:str)->str:
    s=' '.join(str(q).lower().split())
    if any(x in s for x in ('weather','recipe','president','football','movie')):return 'unsupported'
    if 'decision' in s and not any(x in s for x in ('why','reason','contributor')):return 'current_decision'
    if ('h1' in s or 'h3' in s or 'h6' in s) and any(x in s for x in ('prediction','forecast','price')):return 'forecast_path'
    if 'compare' in s and ('h1' in s or 'h6' in s):return 'risk'
    if 'regime' in s:return 'regime'
    if 'alpha' in s or 'delta' in s:return 'alpha_delta'
    if 'fresh' in s or 'time' in s:return 'data_freshness'
    if 'settle' in s:return 'settlement'
    if 'why' in s or 'contributor' in s:return 'model_contributors'
    if 'reliab' in s or 'uncertain' in s:return 'reliability'
    return 'unsupported'

def answer(question:str,p:Mapping[str,Any],visible:Mapping[str,Any]|None=None)->dict[str,Any]:
    val=validate_contract(p,visible); intent=classify_intent(question)
    if not val['valid']:return {'route':'ABSTAIN','intent':intent,'answer':'Evidence is insufficient: '+', '.join(val['errors']),'validation':val,'heavy_calculation_triggered':False}
    if intent=='unsupported':return {'route':'OFF_DOMAIN','intent':intent,'answer':'Ground AI is restricted to the current quant-system snapshot and its saved Lunch evidence.','validation':val,'heavy_calculation_triggered':False}
    ev=[]; route='A_DIRECT_LOOKUP'; text=''
    if intent=='current_decision':
        x=p.get('production_decision');ev=[evidence_item(p,'Field 1','production_decision',x)];text=f"Current production decision: {x}."
    elif intent=='forecast_path':
        h=next((x for x in HORIZONS if x.lower() in question.lower()),'H3');x=p['field2'][h];ev=[evidence_item(p,'Field 2',h+'.prediction',x.get('prediction'))];text=f"{h} prediction: {x.get('prediction')} (interval {x.get('lower')} to {x.get('upper')})."
    elif intent=='regime':
        x=p['field3'];ev=[evidence_item(p,'Field 3','major_regime',x.get('major_regime'))];text=f"Current major regime: {x.get('major_regime')}; stability: {x.get('regime_stability')}."
    elif intent=='alpha_delta':
        x=p['field3'];ev=[evidence_item(p,'Field 3','alpha',x.get('alpha')),evidence_item(p,'Field 3','delta',x.get('delta'))];text=f"Alpha: {x.get('alpha')}; delta: {x.get('delta')}; acceleration: {x.get('delta_acceleration')}."
    elif intent=='data_freshness':text=f"Canonical broker candle time: {p.get('broker_candle_time')}; freshness: {p.get('data_freshness_status')}.";ev=[evidence_item(p,'Canonical','broker_candle_time',p.get('broker_candle_time'))]
    elif intent=='settlement':text='Settlement is horizon-independent: '+', '.join(f'{h}={s}' for h,s in p['settlement_status'].items())+'.';ev=[evidence_item(p,'Field 2','settlement_status',p['settlement_status'])]
    elif intent=='risk':
        route='B_DETERMINISTIC_ANALYSIS'; a=p['field2']['H1'];b=p['field2']['H6'];wa=(_num(a.get('upper')) or 0)-(_num(a.get('lower')) or 0);wb=(_num(b.get('upper')) or 0)-(_num(b.get('lower')) or 0);text=f"Saved interval width: H1={wa:.6g}, H6={wb:.6g}; {'H6' if wb>wa else 'H1'} has greater interval risk.";ev=[evidence_item(p,'Field 2','H1.interval_width',wa),evidence_item(p,'Field 2','H6.interval_width',wb)]
    else:
        route='C_GROUNDED_TEMPLATE';pos=p.get('top_positive_contributors') or [];neg=p.get('top_negative_contributors') or [];text=f"Decision {p.get('production_decision')} is supported by saved forecast/regime evidence. Positive contributors: {pos[:3] or 'unavailable'}; negative contributors: {neg[:3] or 'unavailable'}.";ev=[evidence_item(p,'Field 1','production_decision',p.get('production_decision'))]
    return {'route':route,'intent':intent,'answer':text,'canonical_evidence':ev,'reliability':p.get('field3',{}).get('reliability'),'evidence_warning':p.get('missing_evidence'), 'broker_candle_time':p.get('broker_candle_time'),'run_id_compact':str(p.get('run_id'))[:12],'validation':val,'heavy_calculation_triggered':False}

def adaptive_conformal(residuals:Sequence[float],alpha=.1,shift_weight=.25):
    xs=sorted(abs(float(x)) for x in residuals if _num(x) is not None)
    if len(xs)<8:return {'status':'INSUFFICIENT_EVIDENCE','evidence_count':len(xs),'radius':None}
    q=xs[min(len(xs)-1,max(0,math.ceil((len(xs)+1)*(1-alpha))-1))];recent=statistics.fmean(xs[-min(12,len(xs)):]);base=statistics.fmean(xs)
    return {'status':'CALIBRATED','evidence_count':len(xs),'radius':q*(1+shift_weight*max(0,recent/(base or 1)-1)),'coverage_debt':None}

def bocpd_shadow(values:Sequence[float],hazard=.02):
    xs=[float(x) for x in values if _num(x) is not None]
    if len(xs)<8:return {'calibration_status':'INSUFFICIENT_EVIDENCE','evidence_count':len(xs),'changepoint_probability':None}
    short=xs[-min(6,len(xs)):];long=xs[:-len(short)] or xs
    scale=statistics.pstdev(long) or 1e-9;z=abs(statistics.fmean(short)-statistics.fmean(long))/scale;cp=min(.999,max(hazard,1-math.exp(-hazard*(1+z*z))))
    run=max(1,int(round(1/max(cp,1e-9))))
    return {'calibration_status':'CALIBRATED','evidence_count':len(xs),'changepoint_probability':cp,'expected_run_length':run,'run_length_p10':max(0,int(run*.25)),'run_length_p50':run,'run_length_p90':int(run*2.3),'regime_stability_score':1-cp,'transition_warning':cp>=.35}

def publish(state:dict,canonical:Mapping[str,Any],research:Mapping[str,Any]|None=None):
    key=execution_key(canonical); registry=state.setdefault('ground_ai_execution_registry_20260624',{})
    if key in registry:return {'ok':True,'status':'REUSED','execution_key':key,'heavy_execution_count':0}
    p=build_contract(canonical,research); state['ground_ai_canonical_contract_20260624']=p; registry.clear();registry[key]={'published_at_monotonic':time.monotonic(),'run_id':p['run_id']}
    return {'ok':True,'status':'PUBLISHED','execution_key':key,'evidence_size_bytes':len(json.dumps(p,default=str).encode()),'heavy_execution_count':1,'shadow_only':True}
