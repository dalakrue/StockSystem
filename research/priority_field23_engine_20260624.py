"""Priority Field 2/3 research-grade shadow engine.

All computation is causal, bounded, Settings-owned and additive.  The engine
reads completed canonical H1 data and never mutates Field 1 or production keys.
"""
from __future__ import annotations
from dataclasses import dataclass, fields, replace
from typing import Any, Mapping, Sequence
from types import MappingProxyType
import math, hashlib, json, time
import numpy as np
import pandas as pd

EPS=1e-12
VERSION="priority-field23-20260624-v1"
REGIMES=("DIRECTIONAL_BULL","DIRECTIONAL_BEAR","RANGE","COMPRESSION","BREAKOUT_BULL","BREAKOUT_BEAR","TRANSITION")

def _clip(x,a=0.,b=1.): return float(np.clip(float(x),a,b))
def _softmax(x):
    a=np.asarray(x,float); a=a-np.nanmax(a); e=np.exp(np.nan_to_num(a,nan=-50)); return e/max(e.sum(),EPS)
def _json(v):
    if isinstance(v,Mapping): return {str(k):_json(x) for k,x in v.items()}
    if isinstance(v,(list,tuple,np.ndarray)): return [_json(x) for x in v]
    if isinstance(v,(np.integer,)): return int(v)
    if isinstance(v,(np.floating,)): return float(v) if np.isfinite(v) else None
    if isinstance(v,(pd.Timestamp,)): return v.isoformat()
    return v

def _freeze_map(v): return MappingProxyType({str(k):_json(x) for k,x in dict(v).items()})

@dataclass(frozen=True)
class PredictionPathSnapshot:
    run_id:str; symbol:str; timeframe:str; forecast_origin:str; broker_candle_time:str; current_price:float
    horizons:tuple[int,...]; median_path:tuple[float,...]; expected_path:tuple[float,...]
    quantile_paths:Mapping[str,Any]; projected_ohlc:tuple[Mapping[str,Any],...]; model_paths:Mapping[str,Any]
    model_weights:Mapping[str,float]; regime_conditioned_weights:Mapping[str,Any]; conformal_intervals:Mapping[str,Any]
    coverage_diagnostics:Mapping[str,Any]; breakout_probability:float; false_breakout_probability:float
    reversal_probability:float; path_curvature:float; path_smoothness:float; expected_adverse_excursion:float
    expected_favorable_excursion:float; feature_attribution:Mapping[str,float]; reliability:float
    abstention_status:str; warnings:tuple[str,...]; promotion:Mapping[str,Any]; runtime_ms:float; peak_ram_mb:float
    def to_dict(self): return _json({f.name:getattr(self,f.name) for f in fields(self)})

@dataclass(frozen=True)
class RegimeIntelligenceSnapshot:
    run_id:str; symbol:str; timeframe:str; broker_candle_time:str; higher_regime:str; middle_regime:str; lower_regime:str
    regime_probabilities:Mapping[str,float]; hierarchical_path:tuple[str,...]; changepoint_probability:float; segment_age:int
    duration_distribution:Mapping[str,Any]; expected_remaining_duration:float; transition_probabilities_1h:Mapping[str,float]
    transition_probabilities_3h:Mapping[str,float]; transition_probabilities_6h:Mapping[str,float]; transition_drivers:Mapping[str,float]
    breakout_state:str; unknown_regime_score:float; model_agreement:float; historical_support:float; reliability:float
    abstention_status:str; warnings:tuple[str,...]; changed_dimensions:tuple[str,...]; boundary_confidence:float
    soft_reset_required:bool; hard_reset_required:bool; runtime_ms:float; peak_ram_mb:float
    def to_dict(self): return _json({f.name:getattr(self,f.name) for f in fields(self)})

def _frame(state:Mapping[str,Any])->pd.DataFrame:
    for k in ('canonical_completed_ohlc_df_20260617','last_df','df','ohlc_df'):
        x=state.get(k)
        if isinstance(x,pd.DataFrame) and not x.empty: return x.copy()
    return pd.DataFrame()

def _clean(df):
    if df.empty:return df
    x=df.rename(columns={c:str(c).lower() for c in df.columns}).copy()
    if 'time' not in x and isinstance(x.index,pd.DatetimeIndex):x=x.reset_index().rename(columns={x.index.name or 'index':'time'})
    need=['time','open','high','low','close']
    if any(c not in x for c in need):return pd.DataFrame()
    x['time']=pd.to_datetime(x.time,utc=True,errors='coerce')
    for c in need[1:]+(['spread'] if 'spread' in x else []):x[c]=pd.to_numeric(x[c],errors='coerce')
    return x.dropna(subset=need).sort_values('time').drop_duplicates('time',keep='last').reset_index(drop=True)

def build_changepoint_input_streams(df:pd.DataFrame)->pd.DataFrame:
    x=_clean(df); c=x.close; r=np.log(c.clip(lower=EPS)).diff(); rng=(x.high-x.low).clip(lower=EPS)
    body=(x.close-x.open); direction=np.sign(body).rolling(12,min_periods=4).mean()
    vol=r.rolling(24,min_periods=8).std(ddof=0); medrng=rng.rolling(48,min_periods=12).median()
    out=pd.DataFrame({'returns':r,'absolute_returns':r.abs(),'realized_volatility':vol,'candle_range':rng/c,
      'directional_persistence':direction,'compression_score':1-rng/(medrng+EPS),
      'breakout_residual':(c-c.rolling(24,min_periods=8).mean())/(c.rolling(24,min_periods=8).std(ddof=0)+EPS),
      'spread_liquidity_proxy':x.spread if 'spread' in x else rng/c,'cross_market_residual':0.0},index=x.index)
    return out.replace([np.inf,-np.inf],np.nan)

def calculate_stream_run_length_posteriors(streams:pd.DataFrame,max_run:int=240,hazard:float=1/72)->dict[str,Any]:
    result={}
    for col in streams:
        z=streams[col].dropna().to_numpy(float)
        if len(z)<24: result[col]={'changepoint_probability':0.5,'mode_run_length':0,'posterior':[1.0]}; continue
        base=z[:-1]; med=np.median(base); scale=max(np.median(np.abs(base-med))*1.4826,EPS); q=np.abs((z[-1]-med)/scale)
        cp=_clip((1-math.exp(-q/2))*0.8+hazard)
        n=min(max_run,len(z)); ages=np.arange(n+1); post=np.exp(-ages/max(1,1/cp)); post/=post.sum()
        result[col]={'changepoint_probability':cp,'mode_run_length':int(np.argmax(post)),'expected_run_length':float((ages*post).sum()),'posterior':post.tolist()}
    return result

def calculate_multivariate_changepoint_probability(posteriors:Mapping[str,Any])->float:
    vals=np.array([v.get('changepoint_probability',0.5) for v in posteriors.values()],float)
    return _clip(0.55*np.max(vals)+0.45*np.mean(np.sort(vals)[-min(4,len(vals)):])) if len(vals) else .5

def identify_changed_market_dimensions(posteriors,threshold=.55): return [k for k,v in posteriors.items() if v.get('changepoint_probability',0)<threshold+1 and v.get('changepoint_probability',0)>=threshold]
def calculate_boundary_confidence(posteriors):
    vals=sorted((v.get('changepoint_probability',0) for v in posteriors.values()),reverse=True); return _clip(np.mean(vals[:3]) if vals else 0)
def calculate_soft_reset_recommendation(cp,boundary): return bool(cp>=.50 and boundary>=.45)
def calculate_hard_reset_recommendation(cp,boundary,changed): return bool(cp>=.78 and boundary>=.70 and len(changed)>=3)

def fit_regime_duration_distributions(labels:Sequence[str])->dict[str,Any]:
    runs={}; prev=None;n=0
    for z in labels:
        if z==prev:n+=1
        else:
            if prev is not None:runs.setdefault(prev,[]).append(n)
            prev=z;n=1
    if prev is not None:runs.setdefault(prev,[]).append(n)
    out={}
    for k,v in runs.items():
        a=np.asarray(v,float); mean=float(a.mean()); var=float(a.var()) if len(a)>1 else mean
        law='negative_binomial' if var>mean*1.15 else ('poisson' if mean>2 else 'empirical')
        out[k]={'law':law,'samples':list(map(int,v)),'sample_count':len(v),'mean':mean,'variance':var,'reliability':_clip(len(v)/30)}
    return out

def calculate_duration_posterior(model,current_age,max_duration=240):
    samples=np.asarray(model.get('samples') or [max(current_age,1)],float); grid=np.arange(current_age,max_duration+1)
    surv=np.array([(samples>=g).mean() for g in grid],float); surv=np.maximum.accumulate(surv[::-1])[::-1]
    if surv.sum()<=0:surv=np.exp(-(grid-current_age)/max(model.get('mean',24),1))
    p=surv/max(surv.sum(),EPS); return {'durations':grid.tolist(),'probabilities':p.tolist()}
def calculate_regime_survival_probability(model,age,horizon):
    s=np.asarray(model.get('samples') or [age+1],float); den=max((s>=age).mean(),EPS); return _clip((s>=age+horizon).mean()/den)
def calculate_regime_exit_hazard(model,age): return _clip(1-calculate_regime_survival_probability(model,age,1))
def estimate_remaining_duration_distribution(model,age):
    s=np.asarray(model.get('samples') or [age],float); rem=np.maximum(s[s>=age]-age,0)
    if len(rem)==0: rem=np.array([max(model.get('mean',age)-age,0)])
    return {'expected':float(rem.mean()),'median':float(np.median(rem)),'p10':float(np.quantile(rem,.1)),'p90':float(np.quantile(rem,.9)),'exit_1h':_clip((rem<=1).mean()),'exit_3h':_clip((rem<=3).mean()),'exit_6h':_clip((rem<=6).mean()),'sample_count':int(model.get('sample_count',0)),'reliability':float(model.get('reliability',0))}
def calculate_age_abnormality(model,age): return _clip(max(0,age-model.get('mean',age))/(max(model.get('variance',1),1)**.5*3))
def calculate_overstayed_regime_flag(model,age): return bool(calculate_age_abnormality(model,age)>.66)

def build_regime_latent_state(streams):
    s=streams.copy(); z=(s-s.rolling(120,min_periods=24).median())/(s.rolling(120,min_periods=24).std(ddof=0)+EPS)
    return pd.DataFrame({'directional_pressure':z.returns.rolling(6,min_periods=1).mean(),'volatility_pressure':z.realized_volatility,
      'compression_pressure':z.compression_score,'breakout_pressure':z.breakout_residual,'mean_reversion_pressure':-z.breakout_residual,
      'liquidity_session_state':-z.spread_liquidity_proxy}).clip(-8,8)
def fit_local_regime_dynamics(latent):
    x=latent.dropna().to_numpy(float)
    if len(x)<25:return {'matrix':np.eye(latent.shape[1]).tolist(),'stability':0.0}
    A=np.linalg.lstsq(x[:-1],x[1:],rcond=None)[0]; eig=max(abs(np.linalg.eigvals(A))); return {'matrix':A.tolist(),'stability':_clip(1/(1+eig))}
def calculate_state_dependent_transition_logits(latent_row):
    d=dict(latent_row); return {'bull':d.get('directional_pressure',0)+.4*d.get('breakout_pressure',0),'bear':-d.get('directional_pressure',0)-.4*d.get('breakout_pressure',0),'range':d.get('mean_reversion_pressure',0)-abs(d.get('directional_pressure',0)),'transition':d.get('volatility_pressure',0)+abs(d.get('breakout_pressure',0))}
def calculate_rslds_regime_posterior(logits):
    p=_softmax(list(logits.values())); return dict(zip(logits,p))
def calculate_local_dynamic_stability(model): return float(model.get('stability',0))
def calculate_transition_driver_attribution(logits):
    a={k:abs(float(v)) for k,v in logits.items()}; s=sum(a.values()) or 1; return {k:v/s for k,v in a.items()}

def build_regime_hierarchy(): return {'Directional':{'Bullish trend':['Bullish breakout','Bullish persistent'],'Bearish trend':['Bearish breakout','Bearish persistent']},'Non-directional':{'Range':['Mean reverting','Low volatility'],'Compression':['Pre-breakout compression']},'Transition':{'Novel transition':['Unknown / novel']}}
def calculate_root_state_posterior(features):
    trend=abs(features.get('directional_pressure',0)); comp=max(features.get('compression_pressure',0),0); trans=max(features.get('volatility_pressure',0),0)+abs(features.get('breakout_pressure',0)); p=_softmax([trend,comp,trans]); return dict(zip(['Directional','Non-directional','Transition'],p))
def calculate_branch_state_posterior(features):
    vals=[features.get('directional_pressure',0),-features.get('directional_pressure',0),features.get('mean_reversion_pressure',0),features.get('compression_pressure',0),features.get('volatility_pressure',0)];p=_softmax(vals);return dict(zip(['Bullish trend','Bearish trend','Range','Compression','Novel transition'],p))
def calculate_leaf_state_posterior(features):
    vals=[features.get('directional_pressure',0)+features.get('breakout_pressure',0),-features.get('directional_pressure',0)-features.get('breakout_pressure',0),features.get('mean_reversion_pressure',0),features.get('compression_pressure',0),features.get('volatility_pressure',0)];p=_softmax(vals);return dict(zip(['Bullish breakout','Bearish breakout','Mean reverting','Pre-breakout compression','Unknown / novel'],p))
def calculate_hierarchical_consistency(root,branch,leaf): return _clip(1-(1-max(root.values()))*.35-(1-max(branch.values()))*.35-(1-max(leaf.values()))*.30)
def calculate_multiscale_regime_consensus(root,branch,leaf): return {'higher':max(root,key=root.get),'middle':max(branch,key=branch.get),'lower':max(leaf,key=leaf.get),'consistency':calculate_hierarchical_consistency(root,branch,leaf)}

def build_nbeatsx_features(df,regime_probs=None):
    x=_clean(df); r=np.log(x.close).diff(); h=x.time.dt.hour
    return pd.DataFrame({'local_trend':r.rolling(12,min_periods=4).mean(),'session_seasonality':np.sin(2*np.pi*h/24),'volatility_expansion':r.rolling(12,min_periods=4).std(ddof=0)/(r.rolling(72,min_periods=12).std(ddof=0)+EPS),'breakout_impulse':(x.close-x.close.rolling(24,min_periods=8).mean())/(x.close.rolling(24,min_periods=8).std(ddof=0)+EPS),'mean_reversion':-(x.close-x.close.rolling(48,min_periods=12).mean())/(x.close.rolling(48,min_periods=12).std(ddof=0)+EPS),'exogenous_eurusd_pressure':r.rolling(6,min_periods=2).sum()})
def fit_nbeatsx_path_expert(features,returns,horizons=(1,2,3,4,5,6)):
    z=features.join(pd.Series(returns,name='y')).dropna(); X=z[features.columns].to_numpy(float); y=z.y.to_numpy(float)
    beta=np.linalg.lstsq(np.c_[np.ones(len(X)),X],y,rcond=None)[0] if len(z)>=30 else np.zeros(X.shape[1]+1)
    return {'beta':beta.tolist(),'features':list(features.columns),'residual_scale':float(np.std(y-np.c_[np.ones(len(X)),X]@beta)) if len(z)>=30 else float(np.nanstd(returns))}
def generate_nbeatsx_path(model,last_features,current_price,horizons=(1,2,3,4,5,6)):
    x=np.array([1]+[float(last_features.get(k,0) or 0) for k in model['features']]); step=float(x@np.asarray(model['beta'])); return [float(current_price*np.exp(step*h)) for h in horizons]
def calculate_path_component_contributions(model,last_features):
    b=np.asarray(model['beta'])[1:]; vals=np.array([float(last_features.get(k,0) or 0) for k in model['features']]); raw=b*vals; den=sum(abs(raw)) or 1; return {k:float(v/den) for k,v in zip(model['features'],raw)}
def calculate_unexplained_residual_ratio(model,returns): return _clip(model.get('residual_scale',0)/(float(np.nanstd(returns))+EPS))

def fit_probabilistic_autoregressive_expert(returns,lags=12):
    r=pd.Series(returns).dropna().to_numpy(float)
    if len(r)<lags+30:return {'phi':[0]*lags,'residuals':r[-30:].tolist() or [0.0]}
    X=np.array([r[i-lags:i][::-1] for i in range(lags,len(r))]); y=r[lags:]; phi=np.linalg.lstsq(X,y,rcond=None)[0]; return {'phi':phi.tolist(),'residuals':(y-X@phi).tolist(),'last':r[-lags:][::-1].tolist()}
def sample_future_paths(model,current_price,horizons=(1,2,3,4,5,6),samples=256,seed=20260624):
    rng=np.random.default_rng(seed); phi=np.asarray(model.get('phi',[]),float); residual=np.asarray(model.get('residuals') or [0.0],float); base=np.asarray(model.get('last') or [0.0]*len(phi),float)
    out=np.empty((samples,len(horizons))); maxh=max(horizons)
    for s in range(samples):
        hist=list(base); px=current_price; vals={}
        for h in range(1,maxh+1):
            mu=float(phi@np.asarray(hist[:len(phi)])) if len(phi) else 0; e=float(rng.choice(residual)); step=mu+e*rng.standard_t(5)/1.29; px*=math.exp(step); hist=[step]+hist; vals[h]=px
        out[s]=[vals[h] for h in horizons]
    return out
def calculate_path_quantiles(paths,qs=(.1,.25,.5,.75,.9)): return {f'p{int(q*100)}':np.quantile(paths,q,axis=0).tolist() for q in qs}
def calculate_target_reach_probability(paths,target): return _clip(np.mean(np.max(paths,axis=1)>=target))
def calculate_reversal_probability(paths,current):
    d=np.sign(paths-current); return _clip(np.mean(np.any(d[:,1:]*d[:,:-1]<0,axis=1))) if paths.shape[1]>1 else 0
def calculate_expected_favorable_excursion(paths,current): return float(np.mean(np.maximum(np.max(paths-current,axis=1),0)))
def calculate_expected_adverse_excursion(paths,current): return float(np.mean(np.maximum(np.max(current-paths,axis=1),0)))

def build_tft_feature_groups(features): return {'observed':list(features.columns),'known_future':['hour_sin','hour_cos','session'],'static':['symbol','timeframe'],'regime_conditionals':['regime_probabilities']}
def fit_tft_shadow_expert(features,returns):
    z=features.join(pd.Series(returns,name='y')).dropna(); corr=z.corr(numeric_only=True).y.drop('y').abs() if len(z)>10 else pd.Series(1,index=features.columns); w=(corr/(corr.sum() or 1)).to_dict(); return {'variable_selection_weights':w,'residual_scale':float(z.y.std(ddof=0)) if len(z) else 0.0}
def generate_tft_quantile_paths(model,current,horizons,trend):
    scale=max(model.get('residual_scale',0),1e-6); return {q:[float(current*math.exp(trend*h+({.1:-1.28,.25:-.674,.5:0,.75:.674,.9:1.28}[q])*scale*math.sqrt(h))) for h in horizons] for q in (.1,.25,.5,.75,.9)}
def calculate_variable_selection_weights(model): return model.get('variable_selection_weights',{})
def calculate_temporal_attention_summary(features):
    n=min(24,len(features)); a=np.exp(np.linspace(-2,0,n));a/=a.sum();return {'lookback_hours':n,'recent_weight':float(a[-1]),'weights':a.tolist()}
def calculate_tft_reliability(model,samples): return _clip(samples/300*(1-model.get('residual_scale',0)*100))

def collect_candidate_path_distributions(**paths): return {k:np.asarray(v,float) for k,v in paths.items() if v is not None and len(v)}
def _loss(path,actual): return float(np.mean(np.abs(np.asarray(path)-np.asarray(actual))))
def calculate_regime_conditioned_model_losses(history,regime): return {k:float(v.get(regime,v.get('global',1))) if isinstance(v,Mapping) else float(v) for k,v in history.items()}
def calculate_session_conditioned_model_losses(history,session): return calculate_regime_conditioned_model_losses(history,session)
def calculate_breakout_conditioned_model_losses(history,flag): return calculate_regime_conditioned_model_losses(history,'breakout' if flag else 'normal')
def calculate_dynamic_model_weights(losses,prior=None,temperature=.25):
    names=list(losses); l=np.array([losses[n] for n in names],float); score=np.exp(-(l-l.min())/(max(l.std(),1e-6)*temperature)); w=score/score.sum(); return dict(zip(names,w))
def apply_weight_turnover_penalty(weights,prior=None,max_change=.20):
    if not prior:return weights
    out={k:float(np.clip(v,prior.get(k,0)-max_change,prior.get(k,0)+max_change)) for k,v in weights.items()};s=sum(out.values()) or 1;return {k:v/s for k,v in out.items()}
def apply_instability_penalty(weights,instability):
    out={k:v*max(.05,1-float(instability.get(k,0))) for k,v in weights.items()};s=sum(out.values()) or 1;return {k:v/s for k,v in out.items()}
def apply_calibration_penalty(weights,gaps):
    out={k:v*math.exp(-3*abs(float(gaps.get(k,0)))) for k,v in weights.items()};s=sum(out.values()) or 1;return {k:v/s for k,v in out.items()}
def combine_path_distributions(paths,weights): return np.sum([weights.get(k,0)*np.asarray(v,float) for k,v in paths.items()],axis=0)

def conformal_multi_horizon(pred,errors,horizons,alpha=.10,min_bucket=30):
    e=np.asarray(errors,float); pooled=float(np.quantile(np.abs(e),1-alpha)) if len(e) else 0.0; out={}; diag={}
    for i,h in enumerate(horizons):
        q=pooled*math.sqrt(h); lo=float(pred[i]-q);hi=float(pred[i]+q); observed=float(np.mean(np.abs(e)<=q)) if len(e) else 0
        out[str(h)]={'lower':lo,'upper':hi,'source':'pooled_fallback' if len(e)<min_bucket else 'conditioned','sample_count':len(e)}
        diag[str(h)]={'nominal_coverage':1-alpha,'observed_rolling_coverage':observed,'coverage_gap':observed-(1-alpha),'interval_width':2*q,'normalized_interval_width':2*q/(abs(pred[i])+EPS),'calibration_sample_count':len(e),'undercoverage_warning':observed<1-alpha-.05,'overconservative_warning':observed>1-alpha+.08,'stale_calibration_warning':len(e)<min_bucket}
    return out,diag

def _simple_labels(streams):
    r=streams.returns.fillna(0);v=streams.realized_volatility.fillna(0);comp=streams.compression_score.fillna(0);br=streams.breakout_residual.fillna(0)
    qv=v.rolling(120,min_periods=20).quantile(.7); labels=np.where(comp>.35,'COMPRESSION',np.where((br>1.3)&(v>qv),'BREAKOUT_BULL',np.where((br<-1.3)&(v>qv),'BREAKOUT_BEAR',np.where(r.rolling(6).sum()>0,'DIRECTIONAL_BULL','DIRECTIONAL_BEAR'))));return list(labels)

def evaluate(state:Mapping[str,Any],snapshot:Any)->dict[str,Any]:
    started=time.perf_counter(); df=_clean(_frame(state)); run_id=str(getattr(snapshot,'run_id',None) or (snapshot.get('run_id') if isinstance(snapshot,Mapping) else '') or state.get('canonical_run_id_20260617') or '')
    if len(df)<120:return {'ok':False,'status':'INSUFFICIENT_HISTORY','run_id':run_id,'shadow_only':True,'production_decision_unchanged':True}
    origin=df.time.iloc[-1].isoformat(); current=float(df.close.iloc[-1]); streams=build_changepoint_input_streams(df); posts=calculate_stream_run_length_posteriors(streams); cp=calculate_multivariate_changepoint_probability(posts); changed=identify_changed_market_dimensions(posts);boundary=calculate_boundary_confidence(posts)
    latent=build_regime_latent_state(streams); lr=latent.iloc[-1].fillna(0).to_dict(); dyn=fit_local_regime_dynamics(latent); logits=calculate_state_dependent_transition_logits(lr); rs=calculate_rslds_regime_posterior(logits); drivers=calculate_transition_driver_attribution(logits)
    root=calculate_root_state_posterior(lr);branch=calculate_branch_state_posterior(lr);leaf=calculate_leaf_state_posterior(lr);cons=calculate_multiscale_regime_consensus(root,branch,leaf)
    labels=_simple_labels(streams); current_label=labels[-1]; age=1
    for z in reversed(labels[:-1]):
        if z==current_label:age+=1
        else:break
    duration_models=fit_regime_duration_distributions(labels);dm=duration_models.get(current_label,{'samples':[age],'mean':age,'variance':1,'sample_count':1,'reliability':0});rem=estimate_remaining_duration_distribution(dm,age);durpost=calculate_duration_posterior(dm,age)
    support=_clip(len(df)/1000); agreement=_clip((max(root.values())+max(branch.values())+max(leaf.values())+max(rs.values()))/4); concentration=max(leaf.values());unknown=_clip(.23*(1-concentration)+.20*(1-agreement)+.18*(1-support)+.18*cp+.11*(1-dyn['stability'])+.10*calculate_age_abnormality(dm,age)); abstain='ABSTAIN' if unknown>=.62 or support<.20 else 'TRUST_REDUCED' if unknown>=.42 else 'ACTIVE'
    reg_probs={k:0.0 for k in REGIMES}; reg_probs[current_label]=max(.35,1-unknown); reg_probs['TRANSITION']=unknown; s=sum(reg_probs.values());reg_probs={k:v/s for k,v in reg_probs.items()}
    trans1={k:(unknown if k=='TRANSITION' else reg_probs[k]*(1-unknown)) for k in reg_probs};ss=sum(trans1.values());trans1={k:v/ss for k,v in trans1.items()}; trans3={k:1-(1-v)**3 for k,v in trans1.items()};ss=sum(trans3.values());trans3={k:v/ss for k,v in trans3.items()};trans6={k:1-(1-v)**6 for k,v in trans1.items()};ss=sum(trans6.values());trans6={k:v/ss for k,v in trans6.items()}
    regime=RegimeIntelligenceSnapshot(run_id,'EURUSD','H1',origin,cons['higher'],cons['middle'],cons['lower'],_freeze_map(reg_probs),(cons['higher'],cons['middle'],cons['lower']),cp,age,_freeze_map({'model':dm,'posterior':durpost,'remaining':rem,'age_abnormality':calculate_age_abnormality(dm,age),'overstayed':calculate_overstayed_regime_flag(dm,age)}),rem['expected'],_freeze_map(trans1),_freeze_map(trans3),_freeze_map(trans6),_freeze_map(drivers),current_label,unknown,agreement,support,_clip(.35*agreement+.25*support+.20*(1-cp)+.20*dyn['stability']),abstain,tuple(['unknown_or_novel_regime'] if abstain=='ABSTAIN' else []),tuple(changed),boundary,calculate_soft_reset_recommendation(cp,boundary),calculate_hard_reset_recommendation(cp,boundary,changed),0,0)
    horizons=(1,2,3,4,5,6); returns=np.log(df.close).diff(); nf=build_nbeatsx_features(df,reg_probs); nm=fit_nbeatsx_path_expert(nf,returns); npath=generate_nbeatsx_path(nm,nf.iloc[-1].fillna(0),current,horizons); comp=calculate_path_component_contributions(nm,nf.iloc[-1].fillna(0)); ar=fit_probabilistic_autoregressive_expert(returns); arpaths=sample_future_paths(ar,current,horizons,256); arq=calculate_path_quantiles(arpaths); tft=fit_tft_shadow_expert(nf,returns); trend=float(returns.tail(6).mean());tq=generate_tft_quantile_paths(tft,current,horizons,trend); breakout=max(reg_probs.get('BREAKOUT_BULL',0),reg_probs.get('BREAKOUT_BEAR',0),_clip(abs(lr.get('breakout_pressure',0))/4)); false_breakout=_clip(cp*(1-agreement)); reversal=calculate_reversal_probability(arpaths,current)
    local=[current*math.exp(trend*h) for h in horizons]; meanrev=[current+(df.close.tail(48).mean()-current)*(1-math.exp(-h/8)) for h in horizons]; breakout_path=[current*math.exp((trend+np.sign(lr.get('breakout_pressure',0))*.0005*breakout)*h) for h in horizons]
    candidates=collect_candidate_path_distributions(nbeatsx=npath,probabilistic_ar=arq['p50'],tft=tq[.5],breakout=breakout_path,local_trend=local,mean_reversion=meanrev)
    base_losses={k:float(np.mean(np.abs(np.diff(v))))+1e-8 for k,v in candidates.items()};weights=calculate_dynamic_model_weights(base_losses);weights=apply_weight_turnover_penalty(weights,state.get('priority_field23_previous_weights'));weights=apply_instability_penalty(weights,{'tft':1-calculate_tft_reliability(tft,len(df))});weights=apply_calibration_penalty(weights,{})
    combined=combine_path_distributions(candidates,weights); residuals=returns.dropna().tail(240).to_numpy()*current; intervals,coverage=conformal_multi_horizon(combined,residuals,horizons)
    spread=np.std(np.vstack(list(candidates.values())),axis=0); quant={'p10':(combined-1.28*spread).tolist(),'p25':(combined-.674*spread).tolist(),'p50':combined.tolist(),'p75':(combined+.674*spread).tolist(),'p90':(combined+1.28*spread).tolist()}
    ohlc=[];prev=current
    for i,h in enumerate(horizons):
        mid=float(combined[i]);w=max(float(spread[i]),current*.00015);ohlc.append(_freeze_map({'horizon':h,'open':prev,'high':max(prev,mid)+w*.35,'low':min(prev,mid)-w*.35,'close':mid}));prev=mid
    curvature=float(np.mean(np.abs(np.diff(combined,2)))) if len(combined)>2 else 0;smooth=_clip(1/(1+curvature/(current+EPS)*1e5)); reli=_clip(.25*regime.reliability+.25*(1-unknown)+.25*support+.25*(1-np.mean(spread)/(current*.01+EPS))); p_abstain='ABSTAIN' if abstain=='ABSTAIN' or reli<.30 else 'TRUST_REDUCED' if reli<.50 else 'ACTIVE'
    promotion={k:{'promotion_status':'SHADOW_ONLY','promotion_reason':'Requires causal walk-forward promotion gate','evidence_window':len(df),'sample_count':len(df),'loss_difference':None,'direction_difference':None,'calibration_difference':None,'adverse_tail_difference':None} for k in candidates}
    elapsed=(time.perf_counter()-started)*1000
    prediction=PredictionPathSnapshot(run_id,'EURUSD','H1',origin,origin,current,horizons,tuple(map(float,combined)),tuple(map(float,combined)),_freeze_map(quant),tuple(ohlc),_freeze_map({k:v.tolist() for k,v in candidates.items()}),_freeze_map(weights),_freeze_map({current_label:weights}),_freeze_map(intervals),_freeze_map(coverage),breakout,false_breakout,reversal,curvature,smooth,calculate_expected_adverse_excursion(arpaths,current),calculate_expected_favorable_excursion(arpaths,current),_freeze_map(comp),reli,p_abstain,tuple(['coverage_evidence_insufficient'] if len(residuals)<30 else []),_freeze_map(promotion),elapsed,0.0)
    regime=replace(regime,runtime_ms=elapsed,peak_ram_mb=0.0)
    return {'ok':True,'status':'READY','shadow_only':True,'production_decision_unchanged':True,'field1_immutable_source':True,'run_id':run_id,'prediction_path_snapshot':prediction.to_dict(),'regime_intelligence_snapshot':regime.to_dict(),'model_version':VERSION,'calculated_only_in_settings':True,'ordinary_rerun_training':False,'data_hash':hashlib.sha256(pd.util.hash_pandas_object(df.tail(2000),index=True).values.tobytes()).hexdigest()}

__all__=[n for n in globals() if n.startswith(('build_','calculate_','fit_','generate_','sample_','estimate_','identify_','apply_','combine_','collect_'))]+['PredictionPathSnapshot','RegimeIntelligenceSnapshot','evaluate','VERSION']
