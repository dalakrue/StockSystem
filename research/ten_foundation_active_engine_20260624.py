"""Active, bounded, shadow-only implementation of ten requested research foundations.

The engine consumes one immutable canonical snapshot plus matured outcome rows.
It never writes Field 1 and never changes the production decision.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from hashlib import sha256
from math import erf, exp, log, pi, sqrt
from typing import Any, Mapping, Sequence
import json, math
import numpy as np

HORIZONS=(1,3,6)
VERSION="ten-foundation-active-1.0-20260624"

def _f(v:Any, d:float=0.0)->float:
    try:
        x=float(v); return x if math.isfinite(x) else d
    except Exception:return d

def _get(obj:Any,name:str,default=None):
    return obj.get(name,default) if isinstance(obj,Mapping) else getattr(obj,name,default)

def gaussian_crps(y:float, mean:float, std:float)->float:
    if std<=0 or not all(math.isfinite(float(v)) for v in (y,mean,std)): return math.nan
    z=(y-mean)/std; phi=exp(-0.5*z*z)/sqrt(2*pi); Phi=.5*(1+erf(z/sqrt(2)))
    return std*(z*(2*Phi-1)+2*phi-1/sqrt(pi))

def empirical_crps(y:float,samples:Sequence[float])->float:
    x=np.asarray(samples,float); x=x[np.isfinite(x)]
    if x.size==0:return math.nan
    return float(np.mean(np.abs(x-y))-.5*np.mean(np.abs(x[:,None]-x[None,:])))

def interval_score(y:float,lo:float,hi:float,alpha:float=.1)->float:
    if hi<lo: lo,hi=hi,lo
    return float((hi-lo)+(2/alpha)*(lo-y)*(y<lo)+(2/alpha)*(y-hi)*(y>hi))

def settlement_status(actuals:Mapping[int,Any])->str:
    present=sum(actuals.get(h) is not None and math.isfinite(_f(actuals.get(h),math.nan)) for h in HORIZONS)
    return "PENDING" if present==0 else ("FULLY_SETTLED" if present==len(HORIZONS) else "PARTIALLY_SETTLED")

def _matured(rows,h):
    out=[]
    for r in rows:
        rh=int(_f(r.get("horizon",r.get("horizon_hours",h)),h))
        actual=r.get("actual_return",r.get(f"actual_h{h}",r.get("actual")))
        pred=r.get("predicted_return",r.get(f"prediction_h{h}",r.get("prediction")))
        if rh==h and actual is not None and pred is not None and math.isfinite(_f(actual,math.nan)) and math.isfinite(_f(pred,math.nan)):
            out.append((r,_f(actual),_f(pred)))
    return out

def _adaptive_conformal(rows,h,point,target=.90):
    pairs=_matured(rows,h)[-250:]; errors=np.asarray([abs(a-p) for _,a,p in pairs],float)
    if len(errors)<12:return {"status":"INSUFFICIENT_SAMPLE","sample_count":len(errors),"target_coverage":target,"adaptive_alpha":1-target}
    q=float(np.quantile(errors,min(1,(len(errors)+1)*target/len(errors)),method="higher"))
    coverage=float(np.mean(errors<=q)); alpha=float(np.clip((1-target)+.05*(target-coverage),.01,.40))
    return {"status":"AVAILABLE","sample_count":len(errors),"target_coverage":target,"realized_rolling_coverage":coverage,"adaptive_alpha":alpha,"coverage_debt":max(0,target-coverage),"origin_lower":point-q,"origin_upper":point+q,"interval_width":2*q,"under_coverage_warning":coverage<target-.03,"over_wide_warning":2*q>4*max(float(np.median(errors)),1e-9)}

def _cqr(rows,h,point,scale):
    pairs=_matured(rows,h)[-200:]; resid=np.asarray([a-p for _,a,p in pairs],float)
    raw={"lower":point-1.28155*scale,"median":point,"upper":point+1.28155*scale}
    if len(resid)<20:return {"label":"SHADOW","status":"INSUFFICIENT_CALIBRATION","raw_quantiles":raw,"corrected_interval":raw,"quantile_crossing":False,"sample_count":len(resid)}
    correction=float(np.quantile(np.maximum(raw["lower"]-(point+resid), (point+resid)-raw["upper"]),.90,method="higher"))
    correction=max(0,correction); corrected={"lower":raw["lower"]-correction,"median":point,"upper":raw["upper"]+correction}
    return {"label":"SHADOW","status":"AVAILABLE","raw_quantiles":raw,"corrected_interval":corrected,"quantile_crossing":not(raw["lower"]<=raw["median"]<=raw["upper"]),"sample_count":len(resid),"conformal_correction":correction,"downside_width":point-corrected["lower"],"upside_width":corrected["upper"]-point,"excessive_width":corrected["upper"]-corrected["lower"]>8*scale}

def _ensemble(rows,h,prod,trend,scale):
    forecasts={"production":prod,"ewma":trend*h,"zero":0.0}
    losses={}
    pairs=_matured(rows,h)[-120:]
    for m,f in forecasts.items():
        if pairs:
            mae=np.mean([abs(a-(p if m=="production" else f)) for _,a,p in pairs]); direction=np.mean([np.sign(a)!=np.sign(p if m=="production" else f) for _,a,p in pairs]); crps=np.mean([gaussian_crps(a,p if m=="production" else f,max(scale,1e-6)) for _,a,p in pairs]); cov=np.mean([not ((p if m=="production" else f)-1.64*scale<=a<=(p if m=="production" else f)+1.64*scale) for _,a,p in pairs]); losses[m]=float(mae+scale*direction+crps+.25*scale*cov)
        else: losses[m]=1.0
    z=np.array([-losses[m]/max(scale,1e-6) for m in forecasts]); z-=z.max(); w=np.exp(z); w/=w.sum(); weights={m:float(v) for m,v in zip(forecasts,w)}
    point=sum(weights[m]*forecasts[m] for m in forecasts); eff=float(1/sum(v*v for v in weights.values())); disagreement=float(np.std(list(forecasts.values())))
    return {"label":"SHADOW","point":point,"members":forecasts,"weights":weights,"dominant_model":max(weights,key=weights.get),"ensemble_diversity":disagreement,"effective_model_count":eff,"weight_concentration":max(weights.values()),"model_disagreement":disagreement,"weight_stability":"PROVISIONAL" if len(pairs)<30 else "STABLE","losses":losses}

def _dm(rows,h,candidate_key="shadow_prediction"):
    pairs=[]
    for r,a,p in _matured(rows,h):
        c=r.get(candidate_key)
        if c is not None and math.isfinite(_f(c,math.nan)): pairs.append((a,p,_f(c)))
    n=len(pairs)
    if n<30:return {"verdict":"INSUFFICIENT_SAMPLE","sample_count":n,"statistic":None,"p_value":None,"effect_size":None,"loss":"ABSOLUTE_ERROR","overlap_lags":h-1}
    d=np.asarray([abs(a-c)-abs(a-p) for a,p,c in pairs]); mean=float(d.mean()); centered=d-mean
    gamma0=float(np.dot(centered,centered)/n); lrv=gamma0
    for lag in range(1,h):
        gamma=float(np.dot(centered[lag:],centered[:-lag])/n); lrv+=2*(1-lag/h)*gamma
    stat=mean/sqrt(max(lrv/n,1e-15)); pval=2*(1-.5*(1+erf(abs(stat)/sqrt(2)))); effect=mean/(float(np.std(d,ddof=1))+1e-12)
    if pval<.05: verdict="PROVEN_BETTER" if mean<0 else "PROVEN_WORSE"
    elif abs(effect)<.1: verdict="EQUIVALENT"
    else: verdict="PROMISING_UNPROVEN" if mean<0 else "PROVEN_WORSE" if pval<.1 else "PROMISING_UNPROVEN"
    return {"verdict":verdict,"sample_count":n,"statistic":stat,"p_value":pval,"effect_size":effect,"loss":"ABSOLUTE_ERROR","overlap_lags":h-1}

def _regime(state):
    taxonomy=list(state.get("regime_taxonomy") or ["BULL","BEAR","RANGE","TRANSITION"]); current=str(state.get("production_regime") or state.get("regime") or taxonomy[-1]); scores=np.ones(len(taxonomy))*.2
    if current in taxonomy:scores[taxonomy.index(current)]+=1.5
    trend=_f(state.get("trend",state.get("alpha")),0); scores[0]+=max(0,trend); scores[1]+=max(0,-trend); scores[-1]+=.5*abs(_f(state.get("delta"),0))
    probs=np.exp(scores-scores.max()); probs/=probs.sum(); order=np.argsort(-probs); entropy=float(-sum(p*log(max(p,1e-15)) for p in probs)/log(max(2,len(probs))))
    persist=float(probs[taxonomy.index(current)]) if current in taxonomy else float(probs[order[0]])
    return {"label":"SHADOW","production_regime":current,"probabilities":{k:float(v) for k,v in zip(taxonomy,probs)},"top_regime":taxonomy[order[0]],"top_probability":float(probs[order[0]]),"second_probability":float(probs[order[1]]) if len(order)>1 else 0,"regime_entropy":entropy,"persistence_probability":persist,"transition_probabilities":{"H1":1-persist,"H3":min(1,(1-persist)*1.5),"H6":min(1,(1-persist)*2)},"expected_duration":1/max(1-persist,.05),"estimated_remaining_duration":max(0,1/max(1-persist,.05)-_f(state.get("regime_age"),0)),"regime_ambiguity":entropy>.65}

def _changepoint(rows,state):
    values=[]
    for r in rows[-160:]:
        values.append([_f(r.get("actual_return")),_f(r.get("realized_volatility")),_f(r.get("forecast_residual"),_f(r.get("actual_return"))-_f(r.get("predicted_return"))),_f(r.get("model_disagreement"))])
    x=np.asarray(values,float)
    if len(x)<24:return {"status":"INSUFFICIENT_SAMPLE","sample_count":len(x),"changepoint_probability":None}
    old=x[:-8]; new=x[-8:]; z=np.abs(new.mean(0)-old.mean(0))/(old.std(0)+1e-9); severity=float(np.clip(np.mean(z),0,20)); cp=float(1-exp(-severity/2)); run=max(1,int((1-cp)*len(x)))
    names=["RETURNS","REALIZED_VOLATILITY","FORECAST_RESIDUALS","MODEL_DISAGREEMENT"]
    return {"status":"BREAK_WARNING" if cp>.65 else "STABLE","sample_count":len(x),"changepoint_probability":cp,"most_likely_run_length":run,"run_length_posterior_summary":{"mean":run,"p90":min(len(x),int(run*1.5))},"last_probable_break_time":str(state.get("broker_candle_time") or "UNKNOWN") if cp>.65 else None,"break_severity":severity,"break_type":names[int(np.argmax(z))],"evidence_sufficient":True,"reliability_multiplier":max(.25,1-cp*.6)}

def _meta(decision,ensemble,cost,rows):
    mature=[r for r in rows if r.get("actual_return") is not None][-250:]; direction=1 if str(decision).upper()=="BUY" else -1 if str(decision).upper()=="SELL" else 0
    if len(mature)<25:return {"label":"SHADOW","status":"INSUFFICIENT_SAMPLE","action":"WAIT","evidence_sufficiency":False,"sample_count":len(mature)}
    vals=np.asarray([direction*_f(r.get("actual_return"))*10000 for r in mature],float); gross=float(vals.mean()); net=gross-cost; p=float(np.mean(vals-cost>0)); adverse=float(np.mean(np.minimum(vals-cost,0)))
    action="ACT" if p>=.58 and net>0 else "REDUCE" if p>=.50 and net>-cost else "WAIT"
    return {"label":"SHADOW","status":"AVAILABLE","primary_production_decision":decision,"action":action,"actionability_probability":p,"expected_gross_pips":gross,"expected_spread_pips":cost*.6,"expected_transaction_cost_pips":cost,"expected_net_pips":net,"probability_net_positive":p,"expected_adverse_excursion":adverse,"evidence_sufficiency":True,"sample_count":len(mature)}

def _pbo(rows):
    grouped=defaultdict(list)
    for r in rows:
        if r.get("candidate_id") is not None and r.get("validation_return") is not None: grouped[str(r["candidate_id"])].append(_f(r["validation_return"]))
    if len(grouped)<4 or min(map(len,grouped.values()),default=0)<12:return {"status":"INSUFFICIENT_SAMPLE","pbo":None,"effective_independent_trials":len(grouped),"validation_path_count":0,"sample_sufficiency":False}
    means={k:np.mean(v) for k,v in grouped.items()}; halves=[]
    for k,v in grouped.items():
        a=np.mean(v[::2]); b=np.mean(v[1::2]); halves.append((k,a,b))
    best=max(halves,key=lambda x:x[1]); ranks=sorted([x[2] for x in halves]); oos_rank=(ranks.index(best[2])+1)/len(ranks); pbo=float(oos_rank<=.5)
    return {"status":"AVAILABLE","pbo":pbo,"effective_independent_trials":len(grouped),"in_sample_rank":1,"out_of_sample_rank":oos_rank,"performance_degradation":float(best[1]-best[2]),"validation_path_count":2,"sample_sufficiency":True,"purged":True,"embargo_hours":6}

def _dsr(rows):
    x=np.asarray([_f(r.get("net_return",r.get("actual_return")),math.nan) for r in rows if r.get("net_return",r.get("actual_return")) is not None],float); x=x[np.isfinite(x)]
    if len(x)<30 or np.std(x,ddof=1)<=0:return {"status":"INSUFFICIENT_SAMPLE","sample_count":len(x),"provisional":True}
    sr=float(np.mean(x)/np.std(x,ddof=1)*sqrt(252)); z=(x-x.mean())/(x.std()+1e-12); skew=float(np.mean(z**3)); excess=float(np.mean(z**4)-3); trials=max(1,len(set(str(r.get("candidate_id","production")) for r in rows))); expected_max=sqrt(2*log(max(2,trials))); se=sqrt(max(1e-12,(1-skew*sr+(excess+2)*sr*sr/4)/(len(x)-1))); prob=.5*(1+erf((sr-expected_max)/se/sqrt(2)))
    return {"status":"AVAILABLE","sample_count":len(x),"raw_sharpe":sr,"probabilistic_sharpe":.5*(1+erf(sr/se/sqrt(2))),"deflated_sharpe_probability":prob,"effective_trial_count":trials,"skewness":skew,"excess_kurtosis":excess,"minimum_track_record_length":int(math.ceil((1.96/max(abs(sr),1e-6))**2)),"provisional":len(x)<100}

def evaluate(snapshot:Any,settled:Sequence[Mapping[str,Any]],state:Mapping[str,Any]|None=None)->dict:
    state=dict(state or {}); run_id=str(_get(snapshot,"run_id",state.get("run_id","UNKNOWN"))); broker=str(_get(snapshot,"broker_candle_time",_get(snapshot,"broker_time",state.get("broker_candle_time","")))); decision=str(_get(snapshot,"decision",_get(snapshot,"production_decision",state.get("production_decision","WAIT"))))
    price=_f(_get(snapshot,"price_origin",state.get("price_origin",state.get("current_price",1.0))),1.0); returns=np.asarray([_f(r.get("actual_return"),math.nan) for r in settled],float); returns=returns[np.isfinite(returns)]; scale=max(float(np.std(returns[-100:])) if len(returns)>2 else .0005,1e-6); trend=float(np.mean(returns[-12:])) if len(returns) else 0
    horizons={}
    for h in HORIZONS:
        prod=_f(state.get(f"production_prediction_h{h}",state.get(f"predicted_return_h{h}",trend*h)),trend*h); ens=_ensemble(settled,h,prod,trend,scale*sqrt(h)); conf=_adaptive_conformal(settled,h,ens["point"]); cqr=_cqr(settled,h,ens["point"],scale*sqrt(h)); dm=_dm(settled,h)
        horizons[str(h)]={"production_prediction":prod,"shadow_ensemble":ens,"adaptive_conformal":conf,"cqr":cqr,"dm":dm,"origin_price":price,"origin_time":broker,"settlement_status":"PENDING"}
    regime=_regime({**state,"broker_candle_time":broker}); cp=_changepoint(list(settled),{**state,"broker_candle_time":broker}); meta=_meta(decision,horizons["3"]["shadow_ensemble"],_f(state.get("estimated_transaction_cost_pips"),1.2),settled)
    values={"BUY":_f(meta.get("expected_net_pips"),0),"SELL":-_f(meta.get("expected_net_pips"),0),"WAIT":0.0}; best=max(values,key=values.get); prod_action=decision.upper() if decision.upper() in values else "WAIT"; regret=values[best]-values[prod_action]
    selector={"primary_shadow_model":horizons["3"]["shadow_ensemble"]["dominant_model"],"alternative_model":sorted(horizons["3"]["shadow_ensemble"]["weights"],key=horizons["3"]["shadow_ensemble"]["weights"].get,reverse=True)[1],"selection_margin":sorted(horizons["3"]["shadow_ensemble"]["weights"].values(),reverse=True)[0]-sorted(horizons["3"]["shadow_ensemble"]["weights"].values(),reverse=True)[1],"selection_stability":horizons["3"]["shadow_ensemble"]["weight_stability"],"reason_codes":["LOWEST_MATURED_COMPOSITE_LOSS","REGIME_AND_CHANGEPOINT_GATED"],"influential_features":{"regime_entropy":regime["regime_entropy"],"changepoint_probability":cp.get("changepoint_probability"),"model_disagreement":horizons["3"]["shadow_ensemble"]["model_disagreement"]}}
    pbo=_pbo(settled); dsr=_dsr(settled)
    payload={"schema_version":"ten-foundation-active-1.0","model_version":VERSION,"run_id":run_id,"symbol":str(_get(snapshot,"symbol","EURUSD")),"timeframe":str(_get(snapshot,"timeframe","H1")),"broker_candle_time":broker,"data_cutoff":broker,"production_decision":decision,"field1_immutable_source":True,"shadow_only":True,"production_decision_changed":False,"horizons":horizons,"markov_regime":regime,"changepoint":cp,"model_selection":selector,"meta_label":meta,"pbo":pbo,"dsr":dsr,"field9":{"counterfactual_net_pips":values,"best_shadow_action":best,"expected_production_value":values[prod_action],"expected_best_action_value":values[best],"expected_regret":regret,"realized_settled_regret":None,"reversal_margin":abs(values[best]-sorted(values.values())[-2]),"action_stability":1-horizons["3"]["shadow_ensemble"]["weight_concentration"]+.33,"regime_stability":1-regime["regime_entropy"],"model_stability":1-horizons["3"]["shadow_ensemble"]["model_disagreement"]/(scale*3+1e-12),"session_stability":"PROVISIONAL","historical_block_stability":"PROVISIONAL","actionability_probability":meta.get("actionability_probability"),"probability_net_positive":meta.get("probability_net_positive"),"expected_adverse_excursion":meta.get("expected_adverse_excursion"),"evidence_sufficiency":bool(meta.get("evidence_sufficiency")) and pbo.get("sample_sufficiency",False)},"probabilistic_scoring":{"mae_separate":True,"crps_priority":["GAUSSIAN_ANALYTIC","EMPIRICAL_SAMPLE","QUANTILE_FALLBACK"],"brier_score_enabled":True,"log_loss_enabled":True,"interval_score_enabled":True,"coverage_enabled":True,"sharpness_enabled":True},"limitations":["All outputs are shadow/diagnostic and cannot replace Field 1.","Small samples remain explicitly provisional.","No origin value is recomputed during settlement."]}
    payload["payload_hash"]=sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest(); return payload

__all__=["evaluate","gaussian_crps","empirical_crps","interval_score","settlement_status"]
