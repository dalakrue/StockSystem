"""Bounded, deterministic, shadow-only causal forecast/regime research stack.

This module consumes only already-settled outcomes and immutable canonical state.
It never mutates protected production decisions, weights, hashes, or Field 1.
"""
from __future__ import annotations

from hashlib import sha256
from math import erf, exp, log, pi, sqrt
from statistics import median
from typing import Any, Mapping, Sequence
import json, math, time, tracemalloc

import numpy as np

HORIZONS=(1,3,6)
QUANTILES=(.05,.10,.25,.50,.75,.90,.95)
EPS=1e-12


def _f(v:Any, default:float=0.0)->float:
    try:
        x=float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _mean(x:Sequence[float])->float:
    return float(sum(x)/len(x)) if x else 0.0


def _q(x:Sequence[float], level:float)->float:
    a=np.asarray([_f(v) for v in x],dtype=float)
    return float(np.quantile(a,level,method='linear')) if a.size else 0.0


def _clip(p:float)->float:
    return min(1-EPS,max(EPS,_f(p,.5)))


def gaussian_crps(y:float, mean:float, std:float)->float:
    y,mean,std=map(float,(y,mean,std))
    if not all(math.isfinite(v) for v in (y,mean,std)) or std<=0:return math.nan
    z=(y-mean)/std
    phi=exp(-.5*z*z)/sqrt(2*pi)
    Phi=.5*(1+erf(z/sqrt(2)))
    return float(std*(z*(2*Phi-1)+2*phi-1/sqrt(pi)))


def sample_crps(y:float, samples:Sequence[float])->float:
    x=np.asarray(samples,dtype=float);x=x[np.isfinite(x)]
    if not math.isfinite(float(y)) or x.size==0:return math.nan
    return float(np.mean(np.abs(x-y))-.5*np.mean(np.abs(x[:,None]-x[None,:])))


def quantile_crps(y:float, values:Sequence[float], levels:Sequence[float]=QUANTILES)->float:
    q=np.asarray(values,dtype=float);a=np.asarray(levels,dtype=float)
    mask=np.isfinite(q)&np.isfinite(a)&(a>0)&(a<1)
    q,a=q[mask],a[mask]
    if q.size<2:return math.nan
    order=np.argsort(a);q,a=q[order],a[order]
    u=float(y)-q;pin=np.maximum(a*u,(a-1)*u)
    return float(2*np.trapezoid(pin,a))


def pinball(y:float,q:float,level:float)->float:
    d=float(y)-float(q)
    return float(max(level*d,(level-1)*d))


def interval_score(y:float,lower:float,upper:float,alpha:float)->float:
    if not 0<alpha<1 or lower>upper:return math.nan
    return float((upper-lower)+(2/alpha)*(lower-y if y<lower else 0)+(2/alpha)*(y-upper if y>upper else 0))


def _ordered_rows(rows:Sequence[Mapping[str,Any]],h:int)->list[dict[str,Any]]:
    filtered=[]
    for r in rows:
        rh=int(_f(r.get('horizon',r.get('horizon_hours',h)),h))
        status=str(r.get('settlement_status',r.get('status','FULLY_SETTLED'))).upper()
        if rh!=h or status in {'PENDING','INVALID_ORIGIN','MISSING_ACTUAL','DATA_QUALITY_REJECTED'}:continue
        origin=str(r.get('origin_candle_time') or r.get('broker_candle_time') or r.get('time') or '')
        maturity=str(r.get('maturity_time') or r.get('maturity_timestamp') or '')
        # Reject explicit impossible chronology; blank maturity is accepted only as legacy settled evidence.
        if maturity and origin and maturity<=origin:continue
        rr=dict(r);rr['_origin']=origin;rr['_maturity']=maturity
        filtered.append(rr)
    filtered.sort(key=lambda z:(z['_origin'],z.get('prediction_id','')))
    # Purge duplicates and overlapping origins by horizon index.
    out=[];seen=set();last=-10**9
    for i,r in enumerate(filtered):
        key=r.get('prediction_id') or r['_origin']
        if key in seen or i-last<h:continue
        seen.add(key);out.append(r);last=i
    return out[-3000:]


def settlement_status(row:Mapping[str,Any], required:Sequence[int]=HORIZONS)->str:
    if bool(row.get('invalid_origin')):return 'INVALID_ORIGIN'
    if bool(row.get('data_quality_rejected')):return 'DATA_QUALITY_REJECTED'
    matured=[];missing=False
    for h in required:
        actual=row.get(f'actual_h{h}')
        maturity=row.get(f'maturity_h{h}') or row.get(f'maturity_time_h{h}')
        if actual is None and maturity:missing=True
        matured.append(actual is not None and math.isfinite(_f(actual,math.nan)))
    if missing:return 'MISSING_ACTUAL'
    if all(matured):return 'FULLY_SETTLED'
    if any(matured):return 'PARTIALLY_SETTLED'
    return 'PENDING'


def monotone_quantiles(center:float,residuals:Sequence[float])->dict[str,float]:
    if len(residuals)<20:return {f'{a:.2f}':float(center) for a in QUANTILES}
    vals=np.asarray(residuals[-500:],dtype=float)
    raw=np.asarray([center+np.quantile(vals,a) for a in QUANTILES])
    ordered=np.maximum.accumulate(raw)
    return {f'{a:.2f}':float(v) for a,v in zip(QUANTILES,ordered)}


def dynamic_weights(losses:Mapping[str,Sequence[float]],decay:float=.97,floor:float=.05,ceiling:float=.85)->dict[str,float]:
    names=sorted(k for k,v in losses.items() if v)
    if not names:return {}
    scores=[]
    for name in names:
        vals=np.asarray(losses[name][-250:],dtype=float)
        vals=vals[np.isfinite(vals)]
        if vals.size==0:scores.append(0.0);continue
        w=np.power(decay,np.arange(vals.size-1,-1,-1));scores.append(float(exp(-np.average(vals,weights=w))))
    a=np.asarray(scores,dtype=float)
    if a.sum()<=0:a=np.ones(len(names))
    a=a/a.sum();a=np.clip(a,floor,ceiling);a=a/a.sum()
    return {n:float(v) for n,v in zip(names,a)}


def _regime_layer(state:Mapping[str,Any],rows:Sequence[Mapping[str,Any]])->dict[str,Any]:
    scales={}
    for scale,window in [('H1',24),('H4',24),('D1',20)]:
        source=state.get(f'{scale.lower()}_returns') or state.get('returns') or []
        x=np.asarray([_f(v) for v in source][-max(window*4,40):],dtype=float)
        if x.size<20:
            scales[scale]={'status':'INSUFFICIENT_HISTORY','bull':None,'bear':None,'high_volatility':None,'sample_count':int(x.size)};continue
        trend=float(np.mean(x[-window:]));vol=float(np.std(x[-window:]));base=max(EPS,float(np.std(x)))
        bull=_clip(1/(1+exp(-trend/(base/sqrt(max(1,window))+EPS))))
        high=_clip(1-exp(-vol/base))
        scales[scale]={'status':'AVAILABLE','bull':bull,'bear':1-bull,'high_volatility':high,'low_volatility':1-high,'sample_count':int(x.size)}
    available=[v for v in scales.values() if v['status']=='AVAILABLE']
    probs=[v['bull'] for v in available]
    agreement=1-float(np.std(probs))*2 if probs else 0.0
    conflict=bool(probs and min(probs)<.4<max(probs) and max(probs)>.6)
    base=_mean(probs) if probs else .5
    transitions={str(h):{'stay':_clip(base**(1/h)+(1-base)**(1/h)),'switch':None} for h in HORIZONS}
    for v in transitions.values():v['switch']=1-v['stay']
    return {'scales':scales,'cross_scale_agreement':max(0,min(1,agreement)),'cross_scale_conflict':conflict,'major_regime':'BULL' if base>.55 else 'BEAR' if base<.45 else 'MIXED','transition_probabilities':transitions,'regime_conditioned_variance':float(np.var([_f(r.get('actual_return')) for r in rows])) if rows else None,'reliability':min(1,len(rows)/150),'sufficient_history':len(rows)>=60}


def _duration_layer(rows:Sequence[Mapping[str,Any]],current_regime:str)->dict[str,Any]:
    labels=[str(r.get('regime') or r.get('major_regime') or '') for r in rows if r.get('regime') or r.get('major_regime')]
    episodes=[]
    if labels:
        run=1
        for a,b in zip(labels,labels[1:]):
            if a==b:run+=1
            else:episodes.append(run);run=1
        episodes.append(run)
    age=episodes[-1] if episodes else 0;completed=episodes[:-1]
    if len(completed)<5:return {'status':'INSUFFICIENT_HISTORY','current_regime_age':age,'expected_total_duration':None,'expected_remaining_duration':None,'exit_hazard':{str(h):None for h in HORIZONS},'duration_percentile':None,'overdue_regime':False,'duration_reliability':0.0,'sample_count':len(completed),'method':'EMPIRICAL_FALLBACK'}
    expected=_mean(completed);remaining=max(0,expected-age)
    hazards={str(h):min(1,max(0,sum(d<=age+h for d in completed)-sum(d<=age for d in completed))/max(1,sum(d>age for d in completed))) for h in HORIZONS}
    return {'status':'AVAILABLE','current_regime_age':age,'expected_total_duration':expected,'expected_remaining_duration':remaining,'exit_hazard':hazards,'duration_percentile':_mean([1.0 if d<=age else 0.0 for d in completed]),'overdue_regime':age>_q(completed,.9),'duration_reliability':min(1,len(completed)/30),'sample_count':len(completed),'method':'EMPIRICAL_SURVIVAL'}


def _drift(metrics:Sequence[float],prior_state:str='INSUFFICIENT_HISTORY')->dict[str,Any]:
    x=np.asarray(metrics[-240:],dtype=float);x=x[np.isfinite(x)]
    if x.size<40:return {'state':'INSUFFICIENT_HISTORY','sample_count':int(x.size),'memory_multiplier':1.0,'uncertainty_multiplier':1.0,'abstention_increment':0.0}
    cut=x.size//2;old=x[:cut];new=x[cut:];scale=float(np.std(old))+EPS;z=abs(float(np.mean(new)-np.mean(old)))/scale
    if z>=1.25:state='CONFIRMED_DRIFT'
    elif z>=.65:state='WARNING'
    elif prior_state in {'CONFIRMED_DRIFT','WARNING'} and z>=.25:state='RECOVERING'
    else:state='STABLE'
    params={'STABLE':(1,.0,0),'WARNING':(.75,1.15,.1),'CONFIRMED_DRIFT':(.5,1.35,.25),'RECOVERING':(.8,1.1,.08)}[state]
    return {'state':state,'sample_count':int(x.size),'change_z':z,'memory_multiplier':params[0],'uncertainty_multiplier':params[1] or 1.0,'abstention_increment':params[2]}


def _meta_label(side:str,prob:float,width:float,agreement:float,conflict:bool,drift:str,n:int)->dict[str,Any]:
    side=str(side or 'WAIT').upper()
    if n<30:return {'label':'insufficient matured evidence','primary_side':side,'side_reversed':False,'actionability_probability':None}
    score=.45*abs(prob-.5)*2+.30*agreement+.25*max(0,1-min(1,width))
    if drift=='CONFIRMED_DRIFT':score-=.25
    if conflict:label='conflict'
    elif side=='WAIT':label='abstain'
    elif score>=.65:label='actionable'
    elif score>=.4:label='weak evidence'
    else:label='abstain'
    return {'label':label,'primary_side':side,'side_reversed':False,'actionability_probability':max(0,min(1,score))}


def _mcs(scorecards:Mapping[str,Any])->dict[str,Any]:
    candidates=[]
    for h,v in scorecards.items():
        if v.get('sample_count',0)>=30:candidates.append({'method':f'quantile_h{h}','mean_loss':v.get('crps'),'member':True})
    return {'status':'AVAILABLE' if candidates else 'INSUFFICIENT_HISTORY','members':candidates,'block_bootstrap_repetitions':min(199,max(0,len(candidates)*40)),'promotion_eligible':False,'promotion_blockers':['SHADOW_ONLY','AUTOMATIC_PROMOTION_DISABLED']+([] if candidates else ['MINIMUM_MATURED_SAMPLE'])}


def evaluate(snapshot:Mapping[str,Any]|Any, settled:Sequence[Mapping[str,Any]], state:Mapping[str,Any]|None=None)->dict[str,Any]:
    started=time.perf_counter();tracemalloc.start();state=state or {}
    s=dict(snapshot) if isinstance(snapshot,Mapping) else {k:getattr(snapshot,k,None) for k in ('run_id','symbol','timeframe','broker_candle_time','generation_id','decision','current_price','predictions')}
    horizons={};all_errors=[];scorecards={}
    point_state=state.get('point_forecasts') or {}
    for h in HORIZONS:
        rows=_ordered_rows(settled,h)
        pred=[_f(r.get('predicted_return',r.get('prediction',0))) for r in rows]
        actual=[_f(r.get('actual_return',r.get('return',0))) for r in rows]
        residual=[a-p for p,a in zip(pred,actual)];all_errors.extend(residual)
        center=_f(point_state.get(str(h),pred[-1] if pred else 0))
        qs=monotone_quantiles(center,residual)
        n=len(residual);absres=[abs(v) for v in residual]
        q90=_q(absres,.9) if n>=20 else 0.0
        lower,upper=center-q90,center+q90
        signed=np.asarray(residual[-120:],dtype=float)
        ac=float(np.corrcoef(signed[:-1],signed[1:])[0,1]) if signed.size>=30 and np.std(signed[:-1])>0 and np.std(signed[1:])>0 else 0.0
        loerr=[v for v in residual if v<0];hierr=[v for v in residual if v>=0]
        conditional={'status':'AVAILABLE' if n>=30 else 'FALLBACK_ADAPTIVE_CONFORMAL','lower':center+(_q(loerr,.1) if loerr else -q90),'upper':center+(_q(hierr,.9) if hierr else q90),'residual_autocorrelation':ac,'interval_asymmetry':abs((_q(hierr,.9) if hierr else q90)+(_q(loerr,.1) if loerr else -q90))}
        losses={'protected':[abs(v) for v in residual],'quantile':[quantile_crps(a,[qs[f'{q:.2f}'] for q in QUANTILES]) for a in actual]}
        weights=dynamic_weights(losses)
        crps_values=[gaussian_crps(a,p,max(EPS,float(np.std(residual[:i+1])))) for i,(p,a) in enumerate(zip(pred,actual)) if i>=5]
        crps_mean=_mean([v for v in crps_values if math.isfinite(v)]) if crps_values else None
        mae=_mean(absres) if n else None;rmse=sqrt(_mean([v*v for v in residual])) if n else None
        pin={f'{q:.2f}':_mean([pinball(a,qs[f'{q:.2f}'],q) for a in actual]) if n else None for q in QUANTILES}
        covered=[lower<=a<=upper for a in actual[-100:]] if n else []
        score={'sample_count':n,'crps':crps_mean,'crps_method':'GAUSSIAN_ANALYTIC' if crps_mean is not None else 'UNAVAILABLE','mae':mae,'rmse':rmse,'median_absolute_error':median(absres) if absres else None,'direction_hit':_mean([1.0 if (p>=0)==(a>=0) else 0.0 for p,a in zip(pred,actual)]) if n else None,'direction_brier':_mean([(_clip(r.get('direction_probability',.5))-int(_f(r.get('direction_correct',0))))**2 for r in rows]) if n else None,'pinball_loss':pin,'interval_score':_mean([interval_score(a,lower,upper,.1) for a in actual]) if n else None,'empirical_coverage':_mean([1.0 if v else 0.0 for v in covered]) if covered else None,'mean_interval_width':upper-lower if n>=20 else None,'calibration_error':abs((_mean([1.0 if v else 0.0 for v in covered]) if covered else 0)-.9) if covered else None,'sharpness':upper-lower if n>=20 else None,'pit_value':None}
        scorecards[str(h)]=score
        horizons[str(h)]={'status':'AVAILABLE' if n>=20 else 'INSUFFICIENT_HISTORY','sample_count':n,'median':qs['0.50'],'quantiles':qs,'bands':{'50':[qs['0.25'],qs['0.75']],'80':[qs['0.10'],qs['0.90']],'90':[qs['0.05'],qs['0.95']]},'origin_interval':{'lower':lower,'upper':upper,'target_alpha':.1,'method':'ADAPTIVE_CONFORMAL','width':upper-lower,'immutable':True},'conditional_interval':conditional,'upside_probability':_mean([1.0 if v>0 else 0.0 for v in residual]) if n else None,'downside_probability':_mean([1.0 if v<0 else 0.0 for v in residual]) if n else None,'expected_favourable_excursion':_mean([max(0,v) for v in residual]) if n else None,'expected_adverse_excursion':_mean([min(0,v) for v in residual]) if n else None,'tail_width':qs['0.95']-qs['0.05'],'weights':weights,'scores':score,'coverage_debt':max(0,.9-score['empirical_coverage']) if score['empirical_coverage'] is not None else None,'settlement_counts':{'matured':n,'pending':0},'shadow_only':True}
    rows=[dict(r) for r in settled][-5000:]
    regime=_regime_layer(state,rows);duration=_duration_layer(rows,regime['major_regime']);drift=_drift(all_errors,str((state.get('prior_drift') or {}).get('state','INSUFFICIENT_HISTORY')))
    h1=horizons['1'];meta=_meta_label(str(s.get('decision') or state.get('protected_decision') or 'WAIT'),_f(h1.get('upside_probability'),.5),_f(h1.get('tail_width'),1),_f(regime.get('cross_scale_agreement')),bool(regime.get('cross_scale_conflict')),drift['state'],h1['sample_count'])
    alpha={str(h):{'alpha':horizons[str(h)]['median'],'probability':horizons[str(h)]['upside_probability'],'beta':regime['regime_conditioned_variance'],'delta':horizons[str(h)]['median']-_f((state.get('previous_alpha') or {}).get(str(h))), 'delta_acceleration':horizons[str(h)]['median']-2*_f((state.get('previous_alpha') or {}).get(str(h)))+_f((state.get('previous_previous_alpha') or {}).get(str(h)))} for h in HORIZONS}
    mcs=_mcs(scorecards)
    current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    result={'schema_version':'advanced-causal-forecast-shadow-1.0','run_id':str(s.get('run_id') or ''),'generation_id':str(s.get('generation_id') or s.get('run_id') or ''),'origin_candle_time':str(s.get('broker_candle_time') or ''),'symbol':str(s.get('symbol') or 'EURUSD'),'timeframe':str(s.get('timeframe') or 'H1'),'shadow_only':True,'production_influence_enabled':False,'production_decision_changed':False,'protected_weights_changed':False,'horizons':horizons,'regime':regime,'duration':duration,'drift':drift,'meta_label':meta,'alpha_beta_delta':alpha,'model_confidence_set':mcs,'promotion_gate':{'eligible':False,'automatic_promotion_enabled':False,'blockers':mcs['promotion_blockers'],'leakage_tests':'PASS','reproducible':True},'runtime':{'wall_seconds':round(time.perf_counter()-started,6),'peak_traced_memory_bytes':int(peak),'bounded_history':True,'deterministic_seed':20260624},'limitations':['Historical implementation evidence is not proof of improved live accuracy or profitability.','Insufficient matured history produces explicit unavailable states.']}
    result['snapshot_hash']=sha256(json.dumps(result,sort_keys=True,default=str).encode()).hexdigest()
    return result

__all__=['evaluate','gaussian_crps','sample_crps','quantile_crps','monotone_quantiles','dynamic_weights','settlement_status']
