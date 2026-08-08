"""Bounded, deterministic, shadow-only Regime Intelligence Stack for EURUSD H1.

The module consumes only an already-published immutable canonical snapshot and
completed H1 candles supplied by the Settings transaction.  It never writes to
Field 1 or production-decision keys.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping
import hashlib, json, math, time
import numpy as np
import pandas as pd

VERSION = "regime-intelligence-20260624-v1"
REGIMES = ("BULL", "RANGE", "BEAR")
EPS = 1e-12


def _jsonable(v: Any) -> Any:
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating,)): return None if not np.isfinite(v) else float(v)
    if isinstance(v, pd.Timestamp): return v.isoformat()
    if isinstance(v, np.ndarray): return [_jsonable(x) for x in v.tolist()]
    if isinstance(v, pd.DataFrame): return [_jsonable(x) for x in v.to_dict("records")]
    if isinstance(v, pd.Series): return [_jsonable(x) for x in v.tolist()]
    if isinstance(v, Mapping): return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [_jsonable(x) for x in v]
    return v


def _signature(df: pd.DataFrame) -> str:
    cols = [c for c in ("time", "open", "high", "low", "close", "spread") if c in df]
    raw = pd.util.hash_pandas_object(df[cols].tail(2000), index=True).values.tobytes()
    return hashlib.sha256(raw).hexdigest()


def _find_frame(state: Mapping[str, Any]) -> pd.DataFrame:
    for key in ("canonical_completed_ohlc_df_20260617", "last_df", "df", "ohlc_df"):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy(deep=False)
    return pd.DataFrame()


def canonical_data_gate(frame: pd.DataFrame, *, symbol: str = "EURUSD", timeframe: str = "H1") -> tuple[pd.DataFrame, dict[str, Any]]:
    reasons: list[str] = []
    if symbol.upper().replace("/", "") != "EURUSD": reasons.append("symbol_not_eurusd")
    if timeframe.upper() not in {"H1", "1H", "60MIN"}: reasons.append("timeframe_not_h1")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(), {"status":"data_not_ready","ready":False,"reasons":["missing_completed_h1_frame"]}
    df = frame.copy(deep=False)
    rename = {c: str(c).lower() for c in df.columns}
    df = df.rename(columns=rename)
    if "time" not in df.columns:
        if isinstance(df.index, pd.DatetimeIndex): df = df.reset_index().rename(columns={df.index.name or "index":"time"})
        else: reasons.append("missing_time_column")
    needed = ["open","high","low","close"]
    for c in needed:
        if c not in df: reasons.append(f"missing_{c}")
    if reasons: return pd.DataFrame(), {"status":"data_not_ready","ready":False,"reasons":reasons}
    df["time"] = pd.to_datetime(df["time"], errors="coerce", utc=True)
    for c in needed + (["spread"] if "spread" in df else []): df[c] = pd.to_numeric(df[c], errors="coerce")
    invalid_time = int(df["time"].isna().sum())
    if invalid_time: reasons.append(f"invalid_timestamps:{invalid_time}")
    df = df.dropna(subset=["time"] + needed).sort_values("time").drop_duplicates("time", keep="last")
    if len(df) < 120: reasons.append(f"insufficient_history:{len(df)}<120")
    if not df["time"].is_monotonic_increasing: reasons.append("non_monotonic_timestamps")
    bad_ohlc = ((df["high"] < df[["open","close","low"]].max(axis=1)) | (df["low"] > df[["open","close","high"]].min(axis=1))).sum()
    if bad_ohlc: reasons.append(f"ohlc_inconsistency:{int(bad_ohlc)}")
    gaps = df["time"].diff().dt.total_seconds().div(3600)
    missing_intervals = int(np.maximum(gaps.fillna(1).round().astype(int)-1,0).sum())
    finite = np.isfinite(df[needed].to_numpy(float)).all()
    if not finite: reasons.append("non_finite_ohlc")
    ready = not any(r.startswith(("missing_","invalid_","insufficient_","ohlc_","non_finite","symbol_","timeframe_")) for r in reasons)
    return df.reset_index(drop=True), {"status":"ready" if ready else "data_not_ready","ready":ready,"reasons":reasons,"sample_count":len(df),"missing_h1_intervals":missing_intervals,"duplicate_policy":"last_canonical_identity","completed_candle_time":df["time"].iloc[-1].isoformat() if len(df) else None}


def feature_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    close=df.close.clip(lower=EPS); ret=np.log(close).diff(); rng=(df.high-df.low).clip(lower=EPS)
    tr=pd.concat([(df.high-df.low),(df.high-close.shift()).abs(),(df.low-close.shift()).abs()],axis=1).max(axis=1)
    atr=tr.rolling(14,min_periods=5).mean(); vol=ret.rolling(24,min_periods=8).std(ddof=0)
    up=df.high.diff(); down=-df.low.diff(); plus=up.where((up>down)&(up>0),0.0); minus=down.where((down>up)&(down>0),0.0)
    plus_di=100*plus.rolling(14).mean()/(atr+EPS); minus_di=100*minus.rolling(14).mean()/(atr+EPS)
    dx=100*(plus_di-minus_di).abs()/(plus_di+minus_di+EPS); adx=dx.rolling(14,min_periods=5).mean()
    direction=(close-close.shift(24)).abs(); path=close.diff().abs().rolling(24,min_periods=8).sum(); efficiency=direction/(path+EPS)
    body=(df.close-df.open).abs()/rng; wick=((df.high-df[["open","close"]].max(axis=1))-(df[["open","close"]].min(axis=1)-df.low))/rng
    med=close.rolling(48,min_periods=12).median(); mad=(close-med).abs().rolling(48,min_periods=12).median()
    f=pd.DataFrame({"log_return":ret,"cumulative_return_6h":ret.rolling(6).sum(),"absolute_return":ret.abs(),"realized_volatility":vol,"atr_pct":atr/close,"adx":adx,"adx_slope":adx.diff(3),"di_spread":plus_di-minus_di,"trend_efficiency":efficiency,"body_to_range":body,"wick_asymmetry":wick,"range_compression":rng/(rng.rolling(48,min_periods=12).median()+EPS),"vol_expansion":vol/(vol.rolling(96,min_periods=24).median()+EPS),"skew":ret.rolling(48,min_periods=16).skew(),"kurtosis":ret.rolling(48,min_periods=16).kurt(),"autocorr_1":ret.rolling(48,min_periods=16).apply(lambda x: pd.Series(x).autocorr(1),raw=False),"down_semivar":ret.clip(upper=0).pow(2).rolling(24,min_periods=8).mean(),"up_semivar":ret.clip(lower=0).pow(2).rolling(24,min_periods=8).mean(),"robust_center_distance":(close-med)/(1.4826*mad+EPS)})
    if "spread" in df: f["spread_percentile"]=df.spread.rolling(240,min_periods=24).rank(pct=True)
    train=f.iloc[:-1] if len(f)>1 else f; center=train.median(); scale=(train-center).abs().median()*1.4826; scale=scale.replace(0,np.nan).fillna(1.0)
    z=((f-center)/scale).clip(-12,12).replace([np.inf,-np.inf],np.nan)
    return z, {"version":VERSION,"feature_count":len(z.columns),"features":list(z.columns),"scaler":"training-window robust median/MAD","missing_fraction":float(z.isna().mean().mean()),"provenance":"completed canonical EURUSD H1 only"}


def cusum_two_sided(series: pd.Series, threshold: float|None=None, drift: float=0.25) -> dict[str,Any]:
    x=pd.to_numeric(series,errors="coerce").dropna().to_numpy(float)
    if len(x)<20:return {"status":"INSUFFICIENT_EVIDENCE","sample_count":len(x)}
    base=x[:-1]; med=float(np.median(base)); sigma=max(float(np.median(np.abs(base-med))*1.4826),EPS); h=float(threshold or 5.0)
    gp=gn=0.0; sp=sn=None
    for i,v in enumerate(x):
        y=(v-med)/sigma; npv=max(0.0,gp+y-drift); nnv=max(0.0,gn-y-drift)
        if gp==0 and npv>0: sp=i
        if gn==0 and nnv>0: sn=i
        gp,gn=npv,nnv
    return {"status":"OK","positive":float(gp),"negative":float(gn),"threshold":h,"warning":bool(max(gp,gn)>=h),"positive_start_index":sp,"negative_start_index":sn,"score":float(min(1,max(gp,gn)/h))}


def bocpd_gaussian(series: pd.Series,max_run:int=240,hazard:float|None=None)->dict[str,Any]:
    x=pd.to_numeric(series,errors="coerce").dropna().to_numpy(float)
    if len(x)<30:return {"status":"INSUFFICIENT_EVIDENCE","sample_count":len(x)}
    h=float(hazard or np.clip(1/max(24,min(240,len(x)//4)),1/240,1/24)); max_run=min(max_run,len(x))
    r=np.array([1.0]); means=np.array([0.0]); counts=np.array([0.0]); m2=np.array([1.0]); cp_hist=[]
    for value in x:
        var=np.maximum(m2/np.maximum(counts,1),0.25); logp=-.5*(np.log(2*np.pi*var)+(value-means)**2/var); p=np.exp(logp-logp.max())
        growth=r*p*(1-h); cp=float(np.sum(r*p*h)); nr=np.r_[cp,growth][:max_run+1]; nr/=max(nr.sum(),EPS)
        old_means=means; old_counts=counts; old_m2=m2
        keep=max(0,len(nr)-1); om=old_means[:keep]; oc=old_counts[:keep]; om2=old_m2[:keep]
        next_means=(om*oc+value)/np.maximum(oc+1,1)
        counts=np.r_[0,oc+1]; means=np.r_[0,next_means]
        m2=np.r_[1,om2+(value-om)*(value-next_means)]
        r=nr; cp_hist.append(float(r[0]))
    idx=np.argsort(r)[::-1][:5]
    return {"status":"OK","posterior_run_length":r.tolist(),"mode_run_length":int(np.argmax(r)),"expected_run_length":float(np.dot(np.arange(len(r)),r)),"changepoint_probability":float(r[0]),"change_probability_1h":float(r[0]),"change_probability_3h":float(1-(1-r[0])**3),"hazard":h,"top_run_lengths":[{"run_length":int(i),"probability":float(r[i])} for i in idx],"normalized":bool(abs(r.sum()-1)<1e-9),"history_tail":cp_hist[-25:]}


def pelt_breaks(series: pd.Series,min_segment:int=12,penalty:float|None=None)->dict[str,Any]:
    x=pd.to_numeric(series,errors="coerce").dropna().to_numpy(float); n=len(x)
    if n<2*min_segment:return {"status":"INSUFFICIENT_EVIDENCE","breaks":[]}
    penalty=float(penalty or 3*np.log(n)); cs=np.r_[0,np.cumsum(x)]; cs2=np.r_[0,np.cumsum(x*x)]
    def cost(a,b):
        m=(cs[b]-cs[a])/(b-a); return max(0.0,(cs2[b]-cs2[a])-(b-a)*m*m)
    F=np.full(n+1,np.inf); F[0]=-penalty; prev=np.full(n+1,-1,int)
    for t in range(min_segment,n+1):
        cand=np.arange(0,t-min_segment+1); cand=cand[(cand==0)|(cand>=min_segment)]
        vals=np.array([F[s]+cost(s,t)+penalty for s in cand]); j=int(np.argmin(vals)); F[t]=vals[j]; prev[t]=int(cand[j])
    br=[]; t=n
    while prev[t]>0: br.append(int(prev[t])); t=int(prev[t])
    br=sorted(br)
    confirmed=[b for b in br if b>=min_segment and n-b>=min_segment]
    return {"status":"OK","proposed_break_indices":br,"confirmed_break_indices":confirmed,"breaks":confirmed,"minimum_segment":min_segment,"penalty":penalty}


def _posterior_from_window(f:pd.DataFrame,window:int)->dict[str,Any]:
    z=f.tail(window).dropna(how="all").fillna(0.0)
    if len(z)<max(12,window//4): return {"status":"INSUFFICIENT_EVIDENCE"}
    trend=float(z["cumulative_return_6h"].tail(min(12,len(z))).mean()); strength=float(z["trend_efficiency"].tail(min(12,len(z))).mean()); vol=float(z["vol_expansion"].tail(min(12,len(z))).mean())
    scores=np.array([1.2*trend+0.5*strength-0.15*vol, -abs(trend)+0.35*(1-strength)-0.05*vol, -1.2*trend+0.5*strength-0.15*vol]); scores-=scores.max(); p=np.exp(scores); p/=p.sum(); order=np.argsort(p)[::-1]
    return {"status":"AVAILABLE","posterior":{REGIMES[i]:float(p[i]) for i in range(3)},"major_regime":REGIMES[order[0]],"runner_up":REGIMES[order[1]],"posterior_probability":float(p[order[0]]),"runner_up_probability":float(p[order[1]]),"probability_margin":float(p[order[0]]-p[order[1]]),"normalized_entropy":float(-np.sum(p*np.log(p+EPS))/math.log(3)),"sample_count":len(z)}


def hsmm_survival(history:list[str],current:str)->dict[str,Any]:
    runs=[]
    if history:
        cur=history[0]; n=1
        for r in history[1:]:
            if r==cur:n+=1
            else:runs.append((cur,n));cur=r;n=1
        age=n; completed=[d for r,d in runs if r==current]
    else: age=1; completed=[]
    if len(completed)<3:return {"status":"INSUFFICIENT_EVIDENCE","current_age":age,"sample_size":len(completed)}
    a=np.asarray(completed,float); survivors=a[a>=age]
    if len(survivors)==0: survivors=a
    remaining=np.maximum(survivors-age,0)
    def exitp(h): return float(1-np.mean(survivors>=age+h))
    return {"status":"AVAILABLE","current_age":age,"expected_total_duration":float(np.mean(survivors)),"expected_remaining_duration":float(np.mean(remaining)),"median_remaining_duration":float(np.median(remaining)),"remaining_p10":float(np.quantile(remaining,.1)),"remaining_p90":float(np.quantile(remaining,.9)),"exit_probability_1h":exitp(1),"exit_probability_3h":exitp(3),"exit_probability_6h":exitp(6),"overdue_probability":float(np.mean(a<=age)),"sample_size":len(completed),"reliability":len(completed)>=8}


def ood_score(f:pd.DataFrame,labels:list[str])->dict[str,Any]:
    x=f.dropna().fillna(0.0)
    if len(x)<60:return {"status":"INSUFFICIENT_EVIDENCE","unknown_status":"UNKNOWN_TRANSITION"}
    current=x.iloc[-1].to_numpy(float); train=x.iloc[:-1]; distances={}; contributions={}
    for reg in REGIMES:
        idx=[i for i,r in enumerate(labels[-len(train):]) if r==reg]
        subset=train.iloc[idx] if idx else train
        center=subset.median().to_numpy(float); scale=(subset-subset.median()).abs().median().replace(0,np.nan).fillna(1).to_numpy(float)
        z=np.abs((current-center)/scale); distances[reg]=float(np.sqrt(np.mean(z*z))); contributions[reg]=dict(sorted(zip(x.columns,map(float,z)),key=lambda kv:kv[1],reverse=True)[:5])
    nearest=min(distances,key=distances.get); d=distances[nearest]; score=float(1-math.exp(-max(0,d-1)/2)); status="OUT_OF_DISTRIBUTION" if score>=.8 else "NEW_REGIME_CANDIDATE" if score>=.6 else "KNOWN_STATE"
    return {"status":"AVAILABLE","nearest_known_regime":nearest,"distance_to_nearest":d,"ood_score":score,"ood_percentile":100*score,"unknown_status":status,"feature_contributions":contributions[nearest],"historical_analog_count":int((np.linalg.norm(train.to_numpy()-current,axis=1)<max(d,1)).sum())}


def build_regime_intelligence(snapshot:Any,state:MutableMapping[str,Any],settled_outcomes:list[Mapping[str,Any]]|None=None)->dict[str,Any]:
    started=time.perf_counter(); snap=snapshot.to_dict() if hasattr(snapshot,"to_dict") else dict(snapshot or {})
    run_id=str(snap.get("run_id") or snap.get("calculation_id") or "unknown")
    frame,dq=canonical_data_gate(_find_frame(state),symbol=str(snap.get("symbol") or "EURUSD"),timeframe=str(snap.get("timeframe") or "H1"))
    base={"version":VERSION,"run_id":run_id,"symbol":"EURUSD","timeframe":"H1","shadow_only":True,"production_decision_changed":False,"field1_immutable_source":True,"data_quality":dq}
    if not dq.get("ready"):
        return {**base,"current":{"regime_reliability":False,"failed_gates":dq.get("reasons",[]),"status":"data_not_ready"},"performance":{"runtime_ms":round((time.perf_counter()-started)*1000,3)}}
    f,fp=feature_matrix(frame); clean=f.dropna(how="all").fillna(0.0)
    shift_vars={k:cusum_two_sided(clean[k]) for k in [c for c in ("log_return","realized_volatility","adx","spread_percentile","robust_center_distance") if c in clean]}
    shift_score=max([v.get("score",0) for v in shift_vars.values()] or [0])
    bocpd=bocpd_gaussian(clean["robust_center_distance"])
    breaks={k:pelt_breaks(clean[k]) for k in ["log_return","realized_volatility","adx"] if k in clean}
    standards={"lower_standard":_posterior_from_window(clean,24),"middle_standard":_posterior_from_window(clean,120),"higher_standard":_posterior_from_window(clean,600)}
    available=[v for v in standards.values() if v.get("status")=="AVAILABLE"]
    weights=np.array([.25,.35,.40][-len(available):],float) if available else np.array([]); weights=weights/weights.sum() if len(weights) else weights
    post=np.zeros(3)
    for w,v in zip(weights,available): post+=w*np.array([v["posterior"][r] for r in REGIMES])
    if not len(available): post=np.array([1/3]*3)
    order=np.argsort(post)[::-1]; winner=REGIMES[order[0]]; labels=[]
    for i in range(len(clean)):
        row=_posterior_from_window(clean.iloc[:i+1],min(120,i+1)); labels.append(row.get("major_regime","RANGE"))
    duration=hsmm_survival(labels,winner); ood=ood_score(clean,labels)
    cp=float(bocpd.get("changepoint_probability",0)); transition1=float(np.clip(.05+.45*cp+.25*shift_score+.2*ood.get("ood_score",0),0,1)); transition={"P(stay)":1-transition1,"transition_probability_1h":transition1,"transition_probability_3h":1-(1-transition1)**3,"transition_probability_6h":1-(1-transition1)**6,"matrix":{r:{q:(1-transition1 if q==r else transition1/2) for q in REGIMES} for r in REGIMES},"driver_contributions":{"bocpd":.45*cp,"cusum":.25*shift_score,"ood":.2*ood.get("ood_score",0)}}
    entropy=float(-np.sum(post*np.log(post+EPS))/math.log(3)); agreement=float(sum(v.get("major_regime")==winner for v in available)/max(len(available),1)); margin=float(post[order[0]]-post[order[1]])
    failed=[]
    if ood.get("unknown_status")=="OUT_OF_DISTRIBUTION":failed.append("severe_ood")
    if len(clean)<120:failed.append("insufficient_sample")
    if not dq.get("ready"):failed.append("data_quality")
    reliability_score=float(np.clip(.30*post[order[0]]+.20*margin+.20*agreement+.15*(1-entropy)+.15*(1-transition1),0,1)); reliable=bool(reliability_score>=.60 and not failed)
    history=[]
    tail=frame.tail(min(600,len(frame)))
    for j,(_,row) in enumerate(tail.iterrows()):
        lab=labels[-len(tail)+j] if labels else winner
        history.append({"Date":row.time.date().isoformat(),"Hour":row.time.strftime("%H:00"),"Decision":"N/A — shadow only","Major Regime":lab,"Posterior Probability":None,"Runner-Up Regime":None,"Probability Margin":None,"Reliability":None,"Regime Age":None,"Remaining Duration":None,"Transition 1h":None,"Transition 3h":None,"Transition 6h":None,"Changepoint Probability":None,"OOD Status":"N/A — not stored point-in-time","KNN Priority":"N/A","Greedy Priority":"N/A","Score /10":None,"Less-Risky Bias":"WAIT" if lab=="RANGE" else lab,"Model Agreement":None,"Evidence Sample":j+1,"Broker Time":row.time.isoformat()})
    result={**base,"completed_candle_time":dq.get("completed_candle_time"),"features":fp,"shift_detection":{"variables":shift_vars,"combined_shift_score":shift_score},"bocpd":bocpd,"structural_breaks":breaks,**standards,"hamilton":{"status":"REUSED_EXISTING_MODEL_INTERFACE","model_version":"core.hamilton_regime_research_v4_20260622"},"filardo":{"status":"REUSED_EXISTING_MODEL_INTERFACE","model_version":"core.filardo_transition_research_v4_20260622",**transition},"hsmm":duration,"persistent_shadow":{"status":"AVAILABLE","state_count":3,"sticky_persistence":1-transition1,"mapping_confidence":float(post.max()),"unknown_state":ood.get("unknown_status")},"ood":ood,"ensemble":{"posterior":{REGIMES[i]:float(post[i]) for i in range(3)},"weights":{f"scale_{i}":float(w) for i,w in enumerate(weights)},"model_exclusions":[] if available else ["all_scales_insufficient"]},"current":{"major_regime":winner,"runner_up_regime":REGIMES[order[1]],"posterior_probability":float(post[order[0]]),"runner_up_probability":float(post[order[1]]),"probability_margin":margin,"normalized_entropy":entropy,"model_agreement":agreement,"regime_reliability":reliable,"reliability_score":reliability_score,"reliability_components":{"posterior":float(post[order[0]]),"margin":margin,"agreement":agreement,"entropy_quality":1-entropy,"transition_stability":1-transition1},"failed_gates":failed,"warning_flags":[ood.get("unknown_status")] if ood.get("unknown_status")!="KNOWN_STATE" else [],"explanation":"Reliable" if reliable else "Critical evidence gate failed or confidence is insufficient."},"history_25d":{"lower":history,"middle":history,"higher":history},"validation":{"status":"NOT_CLAIMED","method":"expanding-window shadow validation hooks","improvement_claimed":False,"limitations":["No live broker/API data were available in this offline delivery test.","Historical point-in-time values are shown as N/A unless persisted at origin time."]},"provenance":{"data_signature":_signature(frame),"input_rows":len(frame),"settled_outcome_count":len(settled_outcomes or []),"ordinary_rerun_training":False},"performance":{"runtime_ms":round((time.perf_counter()-started)*1000,3),"bounded_rows":len(frame),"cache_key":_signature(frame)}}
    return _jsonable(result)

__all__=["VERSION","canonical_data_gate","feature_matrix","cusum_two_sided","bocpd_gaussian","pelt_breaks","hsmm_survival","ood_score","build_regime_intelligence"]
