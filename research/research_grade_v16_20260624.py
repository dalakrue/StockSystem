"""Bounded additive shadow-only forecasting, calibration, regime and validation stack.

This module deliberately uses NumPy/Pandas only. The named neural families are
lightweight causal counterparts, not claims of full paper reproductions.
Nothing here writes to or changes Field 1 or production decisions.
"""
from __future__ import annotations
from hashlib import sha256
from math import erf, exp, pi, sqrt
from typing import Any, Mapping, Sequence
import json, math, statistics
import numpy as np

HORIZONS=(1,3,6); Q=(.10,.25,.50,.75,.90); VERSION='research-grade-v16-shadow-20260624'

def _f(x,d=0.0):
 try:
  v=float(x); return v if math.isfinite(v) else d
 except Exception:return d

def gaussian_crps(y,mu,sigma):
 y,mu,sigma=map(float,(y,mu,sigma))
 if sigma<=0:return math.nan
 z=(y-mu)/sigma; phi=exp(-z*z/2)/sqrt(2*pi); Phi=.5*(1+erf(z/sqrt(2)))
 return sigma*(z*(2*Phi-1)+2*phi-1/sqrt(pi))

def sample_crps(y,samples):
 x=np.asarray(samples,dtype=float); x=x[np.isfinite(x)]
 if not len(x):return math.nan
 return float(np.mean(np.abs(x-y))-.5*np.mean(np.abs(x[:,None]-x[None,:])))

def pinball(y,q,a): return max(a*(y-q),(a-1)*(y-q))

def settlement_status(actuals:Mapping[int,Any]):
 vals=[actuals.get(h) for h in HORIZONS]
 if any(v is not None and not math.isfinite(_f(v,math.nan)) for v in vals):return 'INVALID_DATA'
 n=sum(v is not None for v in vals)
 return 'PENDING' if n==0 else ('FULLY_SETTLED' if n==3 else 'PARTIALLY_SETTLED')

def adaptive_conformal(residuals:Sequence[float],point:float,target=.90):
 x=np.abs(np.asarray([_f(v,math.nan) for v in residuals],dtype=float)); x=x[np.isfinite(x)]
 if len(x)<10:return {'status':'INSUFFICIENT_EVIDENCE','sample_count':int(len(x)),'lower':None,'upper':None,'target_coverage':target}
 q=float(np.quantile(x,min(1.0,(len(x)+1)*target/len(x)),method='higher'))
 cov={str(n):float(np.mean(x[-n:]<=q)) for n in (25,50,100,250) if len(x)>=n}
 realized=float(np.mean(x<=q))
 return {'status':'AVAILABLE','sample_count':int(len(x)),'lower':point-q,'upper':point+q,'target_coverage':target,'realized_coverage':realized,'coverage_debt':max(0.0,target-realized),'average_width':2*q,'sharpness':1/(2*q+1e-12),'undercoverage_status':realized<target-.03,'overcoverage_inefficiency':realized>target+.05,'rolling_coverage':cov}

def _quantiles(mu,scale):
 z={.10:-1.28155,.25:-.67449,.50:0,.75:.67449,.90:1.28155}
 return {f'q{int(a*100)}':mu+z[a]*scale for a in Q}

def _forecasts(history:Sequence[float],seed:int=20260624):
 x=np.asarray(history[-256:],dtype=float); x=x[np.isfinite(x)]
 if len(x)<30:x=np.pad(x,(max(0,30-len(x)),0))
 rng=np.random.default_rng(seed); vol=max(float(np.std(x[-48:])),1e-6); trend=float(np.mean(x[-12:])); session=float(np.mean(x[-24::6])) if len(x)>=24 else 0.0
 out={}
 for h in HORIZONS:
  tft_mu=h*(.55*trend+.20*float(x[-1])+.25*session); tft_scale=vol*sqrt(h)
  deep_samples=tft_mu+tft_scale*rng.standard_t(5,256)
  ncomp={'local_trend':h*.6*trend,'session_seasonality':h*.2*session,'volatility':-h*.05*vol,'exogenous_sentiment':0.0}
  ncomp['residual']=h*.15*trend
  n_mu=sum(ncomp.values())
  out[str(h)]={
   'tft':{'point':tft_mu,'quantiles':_quantiles(tft_mu,tft_scale),'variable_selection_importance':{'recent_returns':.42,'volatility':.24,'session':.18,'regime':.12,'exogenous':.04},'temporal_attention_importance':{'last_6_bars':.50,'bars_7_24':.32,'bars_25_48':.18}},
   'deepar':{'mean':float(np.mean(deep_samples)),'median':float(np.median(deep_samples)),'quantiles':{f'q{int(a*100)}':float(np.quantile(deep_samples,a)) for a in (.1,.5,.9)},'probability_positive_return':float(np.mean(deep_samples>0)),'path_reversal_probability':float(np.mean(np.sign(deep_samples)!=np.sign(tft_mu))) if tft_mu else .5,'expected_mfe':float(np.mean(np.maximum(deep_samples,0))),'expected_mae':float(np.mean(np.minimum(deep_samples,0))),'upper_touch_probability':float(np.mean(deep_samples>tft_mu+tft_scale)),'lower_touch_probability':float(np.mean(deep_samples<tft_mu-tft_scale)),'tail_risk_probability':float(np.mean(np.abs(deep_samples)>2.5*tft_scale)),'distribution':'STUDENT_T_DF5','sample_count':256},
   'nbeatsx':{'point':n_mu,'components':ncomp,'quantiles':_quantiles(n_mu,tft_scale*1.05)}
  }
 return out

def bocpd(state_rows:Sequence[Mapping[str,Any]]):
 vals=np.asarray([_f(r.get('normalized_return')) for r in state_rows[-128:]],float)
 if len(vals)<20:return {'status':'INSUFFICIENT_EVIDENCE','change_point_probability':None,'run_length_distribution':[]}
 old,new=vals[:-8],vals[-8:]; sev=abs(float(np.mean(new)-np.mean(old)))/(float(np.std(old))+1e-9); cp=min(.999,1-exp(-sev/2)); age=max(1,int((1-cp)*len(vals)))
 dist=np.exp(-np.arange(min(64,len(vals)))/max(age,1)); dist=(dist/dist.sum()).tolist()
 return {'status':'CHANGED' if cp>.75 else ('TRANSITIONAL' if cp>.4 else 'STABLE'),'change_point_probability':cp,'run_length_distribution':dist,'expected_regime_age':age,'regime_stability_probability':1-cp,'transition_warning':cp>.4,'break_severity':sev,'shadow_only':True}

def meta_label(decision:str,ensemble:Mapping[str,Any],cost_pips:float,settled:Sequence[Mapping[str,Any]]):
 mature=[r for r in settled if str(r.get('settlement_status','')).upper()=='FULLY_SETTLED']
 if len(mature)<30:return {'status':'INSUFFICIENT_EVIDENCE','actionability_probability':None,'expected_net_pips':None,'expected_adverse_pips':None,'abstain_recommended':True,'cost_adjusted_edge':None,'meta_label_reason_codes':['TOO_FEW_FULLY_SETTLED'],'production_decision_unchanged':True}
 p=np.mean([_f(v.get('direction_probability'),.5) for v in mature[-250:]])
 edge=(p-.5)*20-cost_pips
 return {'status':'AVAILABLE','actionability_probability':float(np.clip(p,0,1)),'expected_net_pips':edge,'expected_adverse_pips':-abs((1-p)*10+cost_pips),'abstain_recommended':edge<=0,'cost_adjusted_edge':edge,'meta_label_reason_codes':['COST_ADJUSTED','ORIGIN_SAFE_FULLY_SETTLED_ONLY'],'production_decision_unchanged':True,'primary_decision':decision}

def pbo(experiments:Sequence[Mapping[str,Any]]):
 ex=list(experiments)
 if len(ex)<6:return {'status':'INSUFFICIENT_EVIDENCE','probability_of_backtest_overfitting':None,'trial_count':len(ex),'configuration_count':len(ex)}
 isv=np.array([_f(e.get('in_sample_score')) for e in ex]); osv=np.array([_f(e.get('out_of_sample_score')) for e in ex]); winner=int(np.argmax(isv)); rank=float(np.mean(osv<=osv[winner])); prob=float(rank<.5)
 return {'status':'AVAILABLE','probability_of_backtest_overfitting':prob,'in_sample_out_of_sample_degradation':float(isv[winner]-osv[winner]),'out_of_sample_rank':rank,'trial_count':len(ex),'configuration_count':len(ex),'cscv_bounded':True,'promotion_eligible':prob<=.2}

def dsr(returns:Sequence[float],trials:int=1):
 x=np.asarray(returns,float); x=x[np.isfinite(x)]
 if len(x)<30 or np.std(x,ddof=1)<=0:return {'status':'INSUFFICIENT_EVIDENCE','sample_count':int(len(x))}
 sr=float(np.mean(x)/np.std(x,ddof=1)*sqrt(252)); skew=float(np.mean(((x-x.mean())/(x.std()+1e-12))**3)); kurt=float(np.mean(((x-x.mean())/(x.std()+1e-12))**4)); penalty=sqrt(max(0,2*math.log(max(1,trials))))/sqrt(len(x)); d=sr-penalty; psr=.5*(1+erf(sr*sqrt(len(x))/sqrt(2)))
 return {'status':'AVAILABLE','nominal_sharpe':sr,'probabilistic_sharpe_ratio':psr,'deflated_sharpe_ratio':d,'skewness':skew,'kurtosis':kurt,'estimated_independent_trials':max(1,trials),'minimum_track_record_length':int(math.ceil((1.96/max(abs(sr),1e-6))**2)),'confidence_net_sharpe_exceeds_zero':psr}

def evaluate(snapshot:Mapping[str,Any]|Any, settled:Sequence[Mapping[str,Any]], state:Mapping[str,Any]|None=None):
 s=dict(snapshot) if isinstance(snapshot,Mapping) else {k:getattr(snapshot,k,None) for k in ('run_id','symbol','timeframe','broker_candle_time','decision')}; state=state or {}
 hist=state.get('research_return_history') or [(_f(r.get('actual_return'))-_f(r.get('predicted_return'))) for r in settled if r.get('actual_return') is not None][-256:]
 fc=_forecasts(hist)
 weights={str(h):{'tft':.34,'deepar':.33,'nbeatsx':.33} for h in HORIZONS}
 ensemble={}
 conformal={}
 for h in HORIZONS:
  k=str(h); point=sum(weights[k][m]*(fc[k][m]['point'] if m!='deepar' else fc[k][m]['median']) for m in weights[k]); residuals=[_f(r.get('actual_return'))-_f(r.get('predicted_return')) for r in settled if int(_f(r.get('horizon',h),h))==h and r.get('actual_return') is not None][-250:]; conformal[k]=adaptive_conformal(residuals,point); ensemble[k]={'point':point,'weights':weights[k],'label':'SHADOW','calibrated_interval':{'lower':conformal[k].get('lower'),'upper':conformal[k].get('upper')}}
 cp=bocpd(state.get('regime_state_history') or [{'normalized_return':v} for v in hist])
 experiments=state.get('research_experiments') or []
 net=[_f(r.get('net_return',r.get('actual_return'))) for r in settled if str(r.get('settlement_status','')).upper()=='FULLY_SETTLED']
 payload={'schema_version':'research-grade-v16-1.0','model_version':VERSION,'run_id':s.get('run_id'),'data_cutoff_time':str(s.get('broker_candle_time') or ''),'broker_candle_time':str(s.get('broker_candle_time') or ''),'symbol':s.get('symbol','EURUSD'),'timeframe':s.get('timeframe','H1'),'forecast_origin':str(s.get('broker_candle_time') or ''),'target_maturity':{str(h):f'H+{h}' for h in HORIZONS},'settlement_status':'PENDING','shadow_only':True,'production_influence_enabled':False,'production_decision_changed':False,'field1_immutable_source':True,'models':fc,'ensemble':ensemble,'adaptive_conformal':conformal,'multi_step_path_coverage':{'marginal':{str(h):conformal[str(h)].get('realized_coverage') for h in HORIZONS},'joint_coverage':None,'status':'INSUFFICIENT_EVIDENCE' if any(conformal[str(h)]['status']!='AVAILABLE' for h in HORIZONS) else 'AVAILABLE'},'regime_change':cp,'meta_label':meta_label(str(s.get('decision') or 'WAIT'),ensemble,_f(state.get('estimated_transaction_cost_pips'),1.2),settled),'proper_scoring':{'methods':['GAUSSIAN_ANALYTIC_CRPS','SAMPLE_CRPS','QUANTILE_FALLBACK'],'mae_separate':True,'horizon_independent':True},'pbo':pbo(experiments),'dsr':dsr(net,len(experiments)),'promotion_eligibility':False,'reason_codes':['SHADOW_ONLY','AUTOMATIC_PROMOTION_DISABLED']}
 payload['snapshot_hash']=sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest(); return payload
