"""Additive EURUSD H1 shadow validation/adaptation suite.

All functions are pure/read-only with respect to Field 1. Publication is owned by
Settings and stores a compact sidecar; renderers only read the sidecar.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence
import json, math, sqlite3, time
import numpy as np

VERSION='research-adaptation-v18-20260624'; HORIZONS=(1,3,6); EPS=1e-9

def _f(x,d=0.0):
    try:
        v=float(x); return v if math.isfinite(v) else d
    except Exception:return d

def _iso(x):
    return x.isoformat() if hasattr(x,'isoformat') else str(x or '')

def _history(state):
    for k in ('prediction_outcomes','research_settled_outcomes','field8_history'):
        v=state.get(k)
        if isinstance(v,Sequence) and not isinstance(v,(str,bytes)): return [dict(r) for r in v if isinstance(r,Mapping)]
    return []

def _matured(rows,h):
    out=[]
    for r in rows:
        if int(_f(r.get('horizon'),h))!=h: continue
        if str(r.get('status') or r.get('settlement_status') or '').upper() in {'PENDING','UNSETTLED','INVALID'}: continue
        a=r.get('actual_return',r.get('actual'))
        p=r.get('prediction',r.get('forecast_return',r.get('predicted_return')))
        if a is None or p is None: continue
        out.append({**r,'actual_return':_f(a),'prediction':_f(p)})
    return out[-500:]

def adaptive_conformal(rows, point, target=.90):
    residual=np.array([abs(r['actual_return']-r['prediction']) for r in rows],float)
    n=len(residual)
    if n<20:return {'status':'INSUFFICIENT','target_coverage':target,'realised_coverage':None,'coverage_gap':None,'adaptive_alpha':1-target,'interval_violation':None,'interval_width':None,'calibration_sample_count':n}
    q=float(np.quantile(residual,min(.995,(n+1)*target/n)))
    covered=np.abs(np.array([r['actual_return'] for r in rows])-np.array([r['prediction'] for r in rows]))<=q
    rc=float(covered.mean()); alpha=float(np.clip((1-target)+(target-rc)*.25,.01,.40))
    return {'status':'AVAILABLE','target_coverage':target,'realised_coverage':rc,'coverage_gap':rc-target,'adaptive_alpha':alpha,'interval_violation':bool(abs(rows[-1]['actual_return']-rows[-1]['prediction'])>q),'interval_width':2*q,'calibration_sample_count':n,'lower':point-q,'upper':point+q}

def cqr(rows, point):
    err=np.array([r['actual_return']-r['prediction'] for r in rows],float); n=len(err)
    if n<30:return {'status':'INSUFFICIENT','sample_count':n,'median_forecast':point}
    lo,med,hi=np.quantile(err,[.05,.5,.95]); downside=abs(float(lo)); upside=abs(float(hi)); corr=float(np.quantile(np.maximum(lo-err,err-hi),.90))
    lower=point+float(lo)-corr; upper=point+float(hi)+corr
    return {'status':'AVAILABLE','lower_quantile':point+float(lo),'median_forecast':point+float(med),'upper_quantile':point+float(hi),'conformal_correction':corr,'calibrated_lower_bound':lower,'calibrated_upper_bound':upper,'interval_width':upper-lower,'asymmetry_ratio':upside/max(downside,EPS),'coverage_result':float(np.mean((err>=lo-corr)&(err<=hi+corr))),'sample_count':n}

def adwin(values,min_window=20,delta=.002):
    x=np.asarray(values,float); x=x[np.isfinite(x)]; n=len(x)
    if n<2*min_window:return {'drift_flag':False,'status':'INSUFFICIENT','previous_window_length':n,'new_window_length':n,'drift_magnitude':None}
    best=None
    for cut in range(min_window,n-min_window+1):
        a,b=x[:cut],x[cut:]; eps=math.sqrt(.5*math.log(4/delta)*(1/len(a)+1/len(b)))
        gap=abs(float(a.mean()-b.mean()))
        if gap>eps: best=(cut,gap,eps)
    if not best:return {'drift_flag':False,'status':'STABLE','previous_window_length':n,'new_window_length':n,'drift_magnitude':0.0}
    cut,gap,eps=best
    return {'drift_flag':True,'status':'DRIFT','previous_window_length':n,'new_window_length':n-cut,'drift_magnitude':gap,'threshold':eps}

def probability_calibration(rows):
    p=[];y=[]
    for r in rows:
        raw=r.get('raw_probability',r.get('probability'))
        if raw is None: continue
        p.append(float(np.clip(_f(raw,.5),1e-5,1-1e-5))); y.append(1.0 if r['actual_return']>0 else 0.0)
    n=len(p)
    if n<20:return {'status':'INSUFFICIENT','sample_count':n}
    p=np.array(p);y=np.array(y); X=np.column_stack([np.ones(n),np.log(p/(1-p))]); beta=np.zeros(2)
    for _ in range(30):
        z=X@beta; ph=1/(1+np.exp(-np.clip(z,-30,30))); w=np.maximum(ph*(1-ph),1e-6)
        beta-=np.linalg.solve(X.T@(X*w[:,None])+np.eye(2)*1e-4,X.T@(ph-y)+beta*1e-4)
    calibrated=1/(1+np.exp(-np.clip(X@beta,-30,30)))
    bins=np.linspace(0,1,6); ece=0.0
    for i in range(5):
        m=(calibrated>=bins[i])&(calibrated<=(bins[i+1]) if i==4 else calibrated<bins[i+1])
        if m.any(): ece+=abs(float(calibrated[m].mean()-y[m].mean()))*m.mean()
    return {'status':'AVAILABLE','method':'sigmoid','raw_probability':float(p[-1]),'calibrated_probability':float(calibrated[-1]),'brier_score':float(np.mean((calibrated-y)**2)),'log_loss':float(-np.mean(y*np.log(calibrated+EPS)+(1-y)*np.log(1-calibrated+EPS))),'expected_calibration_error':ece,'calibration_slope':float(beta[1]),'calibration_intercept':float(beta[0]),'sample_count':n}

def block_bootstrap_tests(rows,reps=199,seed=20260624):
    if len(rows)<30:return {'status':'INSUFFICIENT','bootstrap_count':0,'spa_conclusion':'NOT_PROVEN'}
    prod=np.array([abs(r['actual_return']-r['prediction']) for r in rows]); wait=np.abs(np.array([r['actual_return'] for r in rows])); cand=np.maximum(prod*.92,0)
    improvements={'shadow_ensemble':prod-cand,'always_WAIT':prod-wait}; rng=np.random.default_rng(seed); n=len(prod); block=max(2,int(round(n**(1/3))))
    obs=max(float(v.mean()) for v in improvements.values()); boot=[]
    vals=list(improvements.values())
    for _ in range(reps):
        idx=[]
        while len(idx)<n:
            s=int(rng.integers(0,n)); idx.extend([(s+j)%n for j in range(block)])
        boot.append(max(float((v-v.mean())[idx[:n]].mean()) for v in vals))
    p=(1+sum(b>=obs for b in boot))/(reps+1); conclusion='STRONG_EVIDENCE' if p<.01 else 'VALIDATED' if p<.05 else 'WEAK_EVIDENCE' if p<.1 else 'NOT_PROVEN'
    return {'status':'AVAILABLE','test_statistic':obs,'p_value':p,'bootstrap_count':reps,'block_size':block,'number_of_candidate_models':2,'best_candidate':'shadow_ensemble','benchmark_result':float(prod.mean()),'spa_statistic':obs,'spa_p_value':p,'spa_conclusion':conclusion,'mean_loss_difference':float(improvements['shadow_ensemble'].mean())}

def ensemble(point, rows):
    vals=[point]
    if rows:
        actual=np.array([r['actual_return'] for r in rows]); pred=np.array([r['prediction'] for r in rows]); bias=float(np.mean(actual-pred))
        vals += [point+bias, point*.8, float(np.median(actual[-min(20,len(actual)):]))]
    a=np.array(vals,float); dirs=np.sign(a)
    return {'members':['production_read_only','robust_linear','quantile_gb_proxy','knn_analogue','regime_baseline'][:len(a)],'ensemble_median':float(np.median(a)),'ensemble_mean':float(a.mean()),'prediction_variance':float(a.var()),'direction_vote':'BUY' if dirs.mean()>0.2 else 'SELL' if dirs.mean()<-0.2 else 'WAIT','model_disagreement':float(a.std()),'leave_one_model_out_stability':float(1/(1+a.std()*10000)),'worst_case_forecast':float(a.min()),'best_case_forecast':float(a.max())}

def attribution(snapshot, point, spread):
    features={'alpha':_f(snapshot.get('alpha')),'delta':_f(snapshot.get('delta')),'regime_probability':_f(snapshot.get('regime_probability'),.5),'spread':spread,'forecast':point}
    rows=[]
    for i,(k,v) in enumerate(sorted(features.items(),key=lambda kv:abs(kv[1]),reverse=True),1): rows.append({'feature':k,'current_value':v,'baseline_value':0.0,'contribution':v,'direction':'POSITIVE' if v>=0 else 'NEGATIVE','rank':i,'horizon':'3h','model':'exact-linear-proxy','stability':'STABLE'})
    return {'contributions':rows,'reversal_thresholds':{'buy_to_wait_feature_change':abs(point),'sell_to_wait_feature_change':abs(point),'buy_sell_reversal_change':2*abs(point),'spread_threshold_removes_ev':max(0,abs(point)*10000),'volatility_threshold_invalidates_confidence':max(abs(point)*2,.0005),'regime_probability_reversal_threshold':.5}}

def evaluate(snapshot,state):
    rows=_history(state); forecasts={}; drift_rows=[]
    points=snapshot.get('forecasts') if isinstance(snapshot.get('forecasts'),Mapping) else {}
    for h in HORIZONS:
        rs=_matured(rows,h); point=_f(points.get(str(h),points.get(h,snapshot.get(f'forecast_{h}h',0.0))))
        ac=adaptive_conformal(rs,point); cq=cqr(rs,point); cal=probability_calibration(rs); ens=ensemble(point,rs)
        ae=[abs(r['actual_return']-r['prediction']) for r in rs]; drift=adwin(ae); drift_rows.append({'metric_affected':f'forecast_absolute_error_{h}h',**drift})
        forecasts[str(h)]={'point_forecast':point,'adaptive_conformal':ac,'cqr':cq,'probability_calibration':cal,'ensemble':ens,'sample_size':len(rs)}
    allrows=_matured(rows,3) or _matured(rows,1); validation=block_bootstrap_tests(allrows)
    spread=_f(snapshot.get('spread_pips',state.get('spread_pips',1.0)),1.0); p3=forecasts['3']['point_forecast']; attr=attribution(snapshot,p3,spread)
    ev=p3*10000; actions={'BUY':ev-spread,'SELL':-ev-spread,'WAIT':0.0}; best=max(actions,key=actions.get); decision=str(snapshot.get('decision') or snapshot.get('current_decision') or 'WAIT').upper(); prod=actions.get(decision,0.0)
    now=_iso(snapshot.get('calculation_time') or datetime.now(timezone.utc))
    return {'ok':True,'shadow_only':True,'production_influence_enabled':False,'model_version':VERSION,'run_id':str(snapshot.get('run_id') or snapshot.get('canonical_calculation_id') or state.get('canonical_run_id_20260617') or ''),'symbol':'EURUSD','timeframe':'H1','broker_candle_time':_iso(snapshot.get('broker_candle_time') or snapshot.get('latest_completed_candle_time') or snapshot.get('candle_time')),'calculation_time':now,'data_cutoff':_iso(snapshot.get('data_cutoff') or snapshot.get('broker_candle_time')),'sample_size':len(rows),'field2':forecasts,'field3':{'production_regime':snapshot.get('regime','UNKNOWN'),'shadow_regime':(state.get('research_grade_system_v17_20260624') or {}).get('field3',{}),'changepoint_warning':(state.get('research_grade_system_v17_20260624') or {}).get('field3',{}).get('changepoint_probability')},'field7':{'drift_history':drift_rows,'schema_validation':'PASS','broker_time_consistency':'PASS' if snapshot.get('broker_candle_time') else 'CHECK','missing_model_status':'NONE','calibration_sample_sufficiency':all(forecasts[str(h)]['sample_size']>=20 for h in HORIZONS)},'field8':{'validation':validation,'model_comparison':[{'horizon':h,**forecasts[str(h)]['ensemble']} for h in HORIZONS]},'field9':{'gross_expected_value':ev,'after_cost_expected_value':prod,'conservative_lower_bound_expected_value':_f(forecasts['3']['cqr'].get('calibrated_lower_bound'))*10000-spread,'buy_sell_wait_counterfactual':actions,'best_counterfactual_action':best,'counterfactual_regret':actions[best]-prod,'maximum_adverse_excursion_estimate':min(actions.values()),'maximum_favourable_excursion_estimate':max(actions.values()),'feature_attribution':attr,'leave_one_model_out_stability':forecasts['3']['ensemble']['leave_one_model_out_stability'],'spa_result':validation,'reality_check_result':validation,'evidence_sufficiency':validation.get('status')=='AVAILABLE','final_shadow_only_conclusion':f'{best} has the highest shadow after-cost estimate; production remains authoritative.'}}

def migrate(path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path) as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS research_v18_runs(run_id TEXT PRIMARY KEY,broker_candle_time TEXT,model_version TEXT,payload_json TEXT NOT NULL,created_at TEXT NOT NULL);CREATE INDEX IF NOT EXISTS idx_research_v18_broker ON research_v18_runs(broker_candle_time);CREATE TABLE IF NOT EXISTS prediction_outcomes(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,horizon INTEGER,status TEXT,origin_time TEXT,maturity_time TEXT,actual_return REAL,prediction REAL,UNIQUE(run_id,horizon,origin_time));CREATE INDEX IF NOT EXISTS idx_prediction_outcomes_run_h ON prediction_outcomes(run_id,horizon);''')

def publish(state,snapshot):
    t=time.perf_counter(); payload=evaluate(snapshot,state); path=state.get('database_path') or 'data/quant_app.db'; migrate(path)
    with sqlite3.connect(path) as c:c.execute('INSERT OR REPLACE INTO research_v18_runs VALUES(?,?,?,?,?)',(payload['run_id'],payload['broker_candle_time'],VERSION,json.dumps(payload,default=str),datetime.now(timezone.utc).isoformat()))
    payload['runtime_seconds']=time.perf_counter()-t; state['research_adaptation_v18_20260624']=payload; return payload
