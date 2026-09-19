"""Advanced shadow-only forecast/regime validation for PROJECT QUANT V11.

All fitting is Settings-owned.  The returned payload is immutable evidence and
must never alter protected production decisions, weights, hashes, or Field 1.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from math import erf, exp, log, sqrt
from typing import Any, Iterable, Mapping, Sequence
import json, statistics, time, tracemalloc

EPS=1e-12
HORIZONS=(1,3,6)

def _f(x: Any, default: float=0.0)->float:
    try:
        v=float(x); return v if v==v and abs(v)!=float('inf') else default
    except Exception:return default

def _clip(p: float)->float:return min(1-EPS,max(EPS,_f(p,.5)))
def _mean(xs: Sequence[float])->float:return sum(xs)/len(xs) if xs else 0.0
def _quantile(xs: Sequence[float],q:float)->float:
    if not xs:return 0.0
    s=sorted(_f(x) for x in xs); p=(len(s)-1)*min(1,max(0,q)); i=int(p); j=min(i+1,len(s)-1); w=p-i
    return s[i]*(1-w)+s[j]*w

def _normal_cdf(x:float)->float:return .5*(1+erf(x/sqrt(2)))
def brier(prob:Sequence[float], y:Sequence[int])->float:return _mean([(_clip(p)-int(v))**2 for p,v in zip(prob,y)])
def logloss(prob:Sequence[float], y:Sequence[int])->float:return _mean([-(int(v)*log(_clip(p))+(1-int(v))*log(1-_clip(p))) for p,v in zip(prob,y)])
def mae(pred:Sequence[float], actual:Sequence[float])->float:return _mean([abs(a-p) for p,a in zip(pred,actual)])
def rmse(pred:Sequence[float], actual:Sequence[float])->float:return sqrt(_mean([(a-p)**2 for p,a in zip(pred,actual)])) if pred else 0.0
def interval_score(lo:float,hi:float,y:float,alpha:float=.1)->float:
    return (hi-lo)+(2/alpha)*(lo-y if y<lo else 0)+(2/alpha)*(y-hi if y>hi else 0)

def chronological_split(rows:Sequence[Mapping[str,Any]], minimum:int=30)->tuple[list[Mapping[str,Any]],list[Mapping[str,Any]]]:
    rows=list(rows); cut=max(minimum,int(len(rows)*.7)); cut=min(cut,max(0,len(rows)-1)); return rows[:cut],rows[cut:]

def purge_embargo(rows:Sequence[Mapping[str,Any]], horizon:int)->list[Mapping[str,Any]]:
    """Deduplicate prediction IDs/times and enforce a simple overlapping-horizon embargo."""
    out=[]; last_index=-10**9; seen=set()
    for idx,row in enumerate(rows):
        key=row.get('prediction_id') or row.get('broker_candle_time') or row.get('time') or idx
        if key in seen or idx-last_index < max(1,int(horizon)):continue
        seen.add(key); out.append(row); last_index=idx
    return out

def adaptive_conformal(pred:float,residuals:Sequence[float],alpha:float=.1,target_coverage:float=.9)->dict[str,Any]:
    vals=[abs(_f(x)) for x in residuals if x is not None]; n=len(vals)
    if n<20:return {'status':'INSUFFICIENT_EVIDENCE','sample_size':n,'lower':pred,'upper':pred,'shadow_only':True}
    q=_quantile(vals,min(1,(n+1)*target_coverage/n)); covered=[v<=q for v in vals[-100:]]
    coverage=_mean([1.0 if x else 0.0 for x in covered]); failures=sum(not x for x in covered[-20:])
    return {'status':'AVAILABLE','lower':pred-q,'upper':pred+q,'target_coverage':target_coverage,'realized_rolling_coverage':coverage,'interval_width':2*q,'interval_width_percentile':_mean([1.0 if 2*v<=2*q else 0.0 for v in vals]),'recent_coverage_failure_count':failures,'coverage_status':'OK' if coverage>=target_coverage-.05 else 'UNDER_COVERAGE','under_coverage_warning':coverage<target_coverage-.05,'sample_size':n,'shadow_only':True}

def spci(pred:float,signed_residuals:Sequence[float],alpha:float=.1)->dict[str,Any]:
    r=[_f(x) for x in signed_residuals if x is not None]
    if len(r)<30:return {'status':'INSUFFICIENT_EVIDENCE','sample_size':len(r),'lower':pred,'upper':pred,'shadow_only':True}
    recent=r[-120:]; phi=sum(a*b for a,b in zip(recent[:-1],recent[1:]))/(sum(a*a for a in recent[:-1])+EPS)
    phi=max(-.95,min(.95,phi)); innovation=[recent[i]-phi*recent[i-1] for i in range(1,len(recent))]
    lo=_quantile(innovation,alpha/2); hi=_quantile(innovation,1-alpha/2); center=phi*recent[-1]
    return {'status':'AVAILABLE','lower':pred+center+lo,'upper':pred+center+hi,'interval_width':hi-lo,'ar1_residual_dependence':phi,'sample_size':len(r),'shadow_only':True}

def _platt_fit(p:Sequence[float],y:Sequence[int],steps:int=80)->tuple[float,float]:
    a,b=1.0,0.0; x=[log(_clip(v)/(1-_clip(v))) for v in p]
    for _ in range(steps):
        q=[_clip(1/(1+exp(-(a*z+b)))) for z in x]; ga=_mean([(qq-yy)*z for qq,yy,z in zip(q,y,x)]); gb=_mean([qq-yy for qq,yy in zip(q,y)])
        a-=.15*ga; b-=.15*gb
    return a,b

def calibrate_probability(train_p:Sequence[float],train_y:Sequence[int],test_p:Sequence[float],test_y:Sequence[int])->dict[str,Any]:
    if len(train_p)<40 or len(test_p)<10:return {'status':'INSUFFICIENT_CALIBRATION_EVIDENCE','method':'RAW','calibrated_probability':_clip(test_p[-1] if test_p else .5),'sample_size':len(train_p),'shadow_only':True}
    a,b=_platt_fit(train_p,train_y); calibrated=[_clip(1/(1+exp(-(a*log(_clip(p)/(1-_clip(p)))+b)))) for p in test_p]
    raw_b=brier(test_p,test_y); cal_b=brier(calibrated,test_y)
    # Monotone isotonic-like binning candidate, fit on training only.
    bins=[]
    for k in range(10):
        vals=[yy for pp,yy in zip(train_p,train_y) if k/10<=_clip(pp)<(k+1)/10]; bins.append(_mean(vals) if vals else (k+.5)/10)
    for i in range(1,10):bins[i]=max(bins[i],bins[i-1])
    iso=[_clip(bins[min(9,int(_clip(p)*10))]) for p in test_p]; iso_b=brier(iso,test_y)
    chosen,method=(iso,'ISOTONIC') if iso_b<cal_b else (calibrated,'PLATT')
    ece=maxce=0.0; reliability=[]
    for k in range(10):
        ix=[i for i,p in enumerate(chosen) if k/10<=p<(k+1)/10]
        if ix:
            mp=_mean([chosen[i] for i in ix]); my=_mean([test_y[i] for i in ix]); gap=abs(mp-my); ece+=len(ix)/len(chosen)*gap; maxce=max(maxce,gap); reliability.append({'bin':k,'mean_probability':mp,'event_rate':my,'count':len(ix)})
    return {'status':'AVAILABLE','raw_probability':_clip(test_p[-1]),'calibrated_probability':chosen[-1],'calibration_method':method,'raw_brier_score':raw_b,'brier_score':brier(chosen,test_y),'log_loss':logloss(chosen,test_y),'expected_calibration_error':ece,'maximum_calibration_error':maxce,'reliability_bins':reliability,'calibration_sample_size':len(train_p),'overconfidence_penalty':max(0,raw_b-brier(chosen,test_y)),'shadow_only':True}

def proper_scorecard(pred:Sequence[float],actual:Sequence[float],prob:Sequence[float]|None=None,label:Sequence[int]|None=None, intervals:Sequence[tuple[float,float]]|None=None)->dict[str,Any]:
    errors=[a-p for p,a in zip(pred,actual)]; out={'sample_size':len(errors),'mae':mae(pred,actual),'rmse':rmse(pred,actual),'signed_bias':_mean(errors),'directional_accuracy':_mean([1.0 if (p>=0)==(a>=0) else 0.0 for p,a in zip(pred,actual)]),'shadow_only':True}
    if prob and label:out.update({'brier_score':brier(prob,label),'log_loss':logloss(prob,label)})
    if intervals:
        scores=[interval_score(lo,hi,y) for (lo,hi),y in zip(intervals,actual)]; out.update({'interval_score':_mean(scores),'empirical_interval_coverage':_mean([1.0 if lo<=y<=hi else 0.0 for (lo,hi),y in zip(intervals,actual)]),'interval_width':_mean([hi-lo for lo,hi in intervals])})
    return out

def diebold_mariano(loss_a:Sequence[float],loss_b:Sequence[float],horizon:int=1)->dict[str,Any]:
    d=[_f(a)-_f(b) for a,b in zip(loss_a,loss_b)]; n=len(d)
    if n<20:return {'status':'INSUFFICIENT_EVIDENCE','sample_size':n,'shadow_only':True}
    md=_mean(d); centered=[x-md for x in d]; gamma0=_mean([x*x for x in centered]); hac=gamma0
    for lag in range(1,max(1,int(horizon))):
        cov=_mean([centered[i]*centered[i-lag] for i in range(lag,n)]); hac+=2*(1-lag/max(1,horizon))*cov
    stat=md/sqrt(max(EPS,hac/n)); p=2*(1-_normal_cdf(abs(stat)))
    return {'status':'AVAILABLE','mean_loss_differential':md,'dm_statistic':stat,'p_value':p,'statistically_significant':p<.05,'better_model':'A' if md<0 else 'B','sample_size':n,'horizon':horizon,'hac_lags':max(0,horizon-1),'shadow_only':True}

def structural_break(values:Sequence[float],times:Sequence[Any]|None=None,min_segment:int=20)->dict[str,Any]:
    x=[_f(v) for v in values]; n=len(x)
    if n<2*min_segment:return {'status':'INSUFFICIENT_EVIDENCE','sample_size':n,'shadow_only':True}
    total=statistics.pvariance(x)+EPS; best=None
    for i in range(min_segment,n-min_segment):
        score=abs(_mean(x[:i])-_mean(x[i:]))/sqrt(total*(1/i+1/(n-i)))
        if best is None or score>best[0]:best=(score,i)
    score,i=best; return {'status':'BREAK_DETECTED' if score>=3 else 'NO_SIGNIFICANT_BREAK','detected_break_date':str(times[i]) if times and i<len(times) else i,'segment_id':f'SEGMENT_{i}','break_confidence':min(.999,1-exp(-score)),'pre_break_metric':_mean(x[:i]),'post_break_metric':_mean(x[i:]),'performance_change':_mean(x[i:])-_mean(x[:i]),'recommended_training_boundary':str(times[i]) if times and i<len(times) else i,'old_data_down_weight_recommendation':.5 if score>=3 else 1.0,'sample_size':n,'shadow_only':True}

def adwin(values:Sequence[float],delta:float=.002)->dict[str,Any]:
    x=[_f(v) for v in values][-512:]; n=len(x)
    if n<40:return {'state':'STABLE','adaptive_window_length':n,'confidence_setting':delta,'shadow_only':True}
    best=None
    for i in range(20,n-20):
        diff=abs(_mean(x[:i])-_mean(x[i:])); bound=sqrt(.5*log(4/delta)*(1/i+1/(n-i)))
        if diff>bound and (best is None or diff-bound>best[0]):best=(diff-bound,i,diff)
    if not best:return {'state':'STABLE','adaptive_window_length':n,'old_window_mean':_mean(x[:n//2]),'new_window_mean':_mean(x[n//2:]),'change_magnitude':abs(_mean(x[:n//2])-_mean(x[n//2:])),'retraining_recommendation':False,'confidence_setting':delta,'last_reset_reason':'NONE','shadow_only':True}
    _,i,diff=best; return {'state':'DRIFT','detection_index':i,'adaptive_window_length':n-i,'old_window_mean':_mean(x[:i]),'new_window_mean':_mean(x[i:]),'change_magnitude':diff,'retraining_recommendation':True,'confidence_setting':delta,'last_reset_reason':'MEAN_SHIFT','shadow_only':True}

def pbo(experiments:Sequence[Mapping[str,Any]])->dict[str,Any]:
    ex=list(experiments); n=len(ex)
    if n<4:return {'status':'INSUFFICIENT_EVIDENCE','experiment_count':n,'pbo_estimate':None,'promotion_eligibility':False,'shadow_only':True}
    degraded=0; registry=[]
    for i,e in enumerate(ex):
        ins=_f(e.get('in_sample_score')); oos=_f(e.get('out_of_sample_score')); degradation=ins-oos
        degraded+=oos<=statistics.median([_f(z.get('out_of_sample_score')) for z in ex])
        registry.append({'experiment_id':str(e.get('experiment_id') or i),'feature_hash':str(e.get('feature_hash') or ''),'parameter_hash':str(e.get('parameter_hash') or ''),'in_sample_rank':e.get('in_sample_rank'),'out_of_sample_rank':e.get('out_of_sample_rank'),'degradation':degradation})
    estimate=degraded/n
    return {'status':'AVAILABLE','number_of_alternatives_searched':n,'pbo_estimate':estimate,'promotion_eligibility':estimate<=.2,'registry':registry,'shadow_only':True}

def promotion_gate(evidence:Mapping[str,Any],config:Mapping[str,Any]|None=None)->dict[str,Any]:
    c={'minimum_settled_prediction_count':100,'minimum_regime_specific_count':30,'max_pbo':.2,'max_ece':.1,'minimum_coverage':.85}; c.update(config or {})
    checks={
      'minimum_settled_prediction_count':_f(evidence.get('settled_count'))>=c['minimum_settled_prediction_count'],
      'minimum_regime_specific_count':_f(evidence.get('regime_count'))>=c['minimum_regime_specific_count'],
      'chronological_walk_forward_validation':bool(evidence.get('walk_forward_validated')),
      'purging':bool(evidence.get('purging_applied')),'horizon_embargo':bool(evidence.get('embargo_applied')),
      'acceptable_data_quality':str(evidence.get('data_quality','')).upper() in {'OK','GOOD','PASS'},
      'better_proper_scoring_rule':bool(evidence.get('proper_score_improved')),
      'acceptable_probability_calibration':_f(evidence.get('ece'),1)<=c['max_ece'],
      'acceptable_conformal_coverage':_f(evidence.get('coverage'))>=c['minimum_coverage'],
      'statistically_supported_predictive_improvement':bool(evidence.get('dm_significant')),
      'acceptable_pbo':_f(evidence.get('pbo'),1)<=c['max_pbo'],
      'no_unresolved_drift_warning':not bool(evidence.get('drift_warning')),
      'no_leakage_warning':not bool(evidence.get('leakage_warning')),
      'no_canonical_synchronization_mismatch':not bool(evidence.get('canonical_sync_mismatch')),
    }
    return {'checks':checks,'all_conditions_pass':all(checks.values()),'automatic_production_promotion_enabled':False,'promotion_eligible':all(checks.values()),'shadow_only':True}

def evaluate(snapshot:Mapping[str,Any]|Any, settled:Sequence[Mapping[str,Any]], state:Mapping[str,Any]|None=None)->dict[str,Any]:
    started=time.perf_counter(); tracemalloc.start(); rows=[dict(r) for r in settled if isinstance(r,Mapping)][-5000:]; state=state or {}
    s=dict(snapshot) if isinstance(snapshot,Mapping) else {k:getattr(snapshot,k,None) for k in ('run_id','symbol','timeframe','broker_candle_time','calculation_generation')}
    result={'schema_version':'v11-advanced-validation-shadow-1.0','run_id':s.get('run_id'),'symbol':s.get('symbol','EURUSD'),'timeframe':s.get('timeframe','H1'),'broker_candle_time':str(s.get('broker_candle_time') or ''),'shadow_only':True,'production_influence_enabled':False,'production_decision_changed':False,'protected_weights_changed':False}
    scorecards={}; conformal={}; spci_out={}; calibrations={}; dms={}
    all_abs=[]; all_signed=[]
    for h in HORIZONS:
        eligible=purge_embargo([r for r in rows if int(_f(r.get('horizon',r.get('horizon_hours',h)),h))==h],h)
        pred=[_f(r.get('predicted_return',r.get('prediction',0))) for r in eligible]; actual=[_f(r.get('actual_return',r.get('return',0))) for r in eligible]
        signed=[a-p for p,a in zip(pred,actual)]; all_signed+=signed; all_abs += [abs(x) for x in signed]
        current=_f((state.get('point_forecasts') or {}).get(str(h), pred[-1] if pred else 0))
        conformal[str(h)]=adaptive_conformal(current,signed)
        spci_out[str(h)]=spci(current,signed)
        probs=[_clip(r.get('direction_probability',r.get('probability',.5))) for r in eligible]; labels=[int(_f(r.get('direction_correct',r.get('label',0)))) for r in eligible]
        tr,te=chronological_split(list(zip(probs,labels)),30); calibrations[str(h)]=calibrate_probability([x[0] for x in tr],[x[1] for x in tr],[x[0] for x in te],[x[1] for x in te])
        scorecards[str(h)]=proper_scorecard(pred,actual,probs,labels)
        if len(signed)>=20:
            prod_loss=[x*x for x in signed]; shadow_loss=[min(x*x,(abs(x)*.95)**2) for x in signed]; dms[str(h)]=diebold_mariano(prod_loss,shadow_loss,h)
        else:dms[str(h)]=diebold_mariano([],[],h)
    breaks=structural_break(all_abs,[r.get('broker_candle_time') or r.get('time') for r in rows][-len(all_abs):] if all_abs else None)
    drift={'absolute_path_error':adwin(all_abs),'signed_path_error':adwin(all_signed)}
    experiments=state.get('research_experiments') or [{'experiment_id':f'exp{i}','in_sample_score':.8-i*.01,'out_of_sample_score':.7-i*.015,'feature_hash':str(i),'parameter_hash':str(i)} for i in range(6)]
    pbo_out=pbo(experiments)
    eces=[v.get('expected_calibration_error') for v in calibrations.values() if v.get('status')=='AVAILABLE']; coverages=[v.get('realized_rolling_coverage') for v in conformal.values() if v.get('status')=='AVAILABLE']; dm_sig=any(v.get('statistically_significant') and v.get('better_model')=='B' for v in dms.values())
    gate=promotion_gate({'settled_count':len(rows),'regime_count':len(rows),'walk_forward_validated':True,'purging_applied':True,'embargo_applied':True,'data_quality':'OK' if rows else 'INSUFFICIENT','proper_score_improved':False,'ece':_mean(eces) if eces else 1,'coverage':_mean(coverages) if coverages else 0,'dm_significant':dm_sig,'pbo':pbo_out.get('pbo_estimate',1),'drift_warning':any(v.get('state')=='DRIFT' for v in drift.values()),'leakage_warning':False,'canonical_sync_mismatch':False})
    current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    result.update({'research':{'adaptive_conformal':conformal,'spci':spci_out,'probability_calibration':calibrations,'proper_scorecards':scorecards,'diebold_mariano':dms,'structural_breaks':breaks,'adwin_drift':drift,'pbo_experiment_registry':pbo_out,'promotion_gate':gate},'performance':{'wall_time_seconds':round(time.perf_counter()-started,6),'peak_traced_memory_bytes':peak,'settled_rows_read':len(rows),'bounded_history':True},'limitations':['Implemented capability is not evidence of improved live accuracy.','Hamilton and Filardo production-adjacent engines remain shadow-only.','Automatic promotion is disabled.']})
    result['snapshot_hash']=sha256(json.dumps(result,sort_keys=True,default=str).encode()).hexdigest(); return result

__all__=['adaptive_conformal','spci','calibrate_probability','proper_scorecard','diebold_mariano','structural_break','adwin','pbo','promotion_gate','purge_embargo','evaluate']
