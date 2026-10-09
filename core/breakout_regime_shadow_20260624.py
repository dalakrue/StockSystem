"""Breakout-aware prediction path and unified regime decision shadow layer.

Additive only: reads canonical snapshot/OHLC and writes one run-id keyed shadow payload.
No production or Field 1 key is mutated.
"""
from __future__ import annotations
from dataclasses import asdict, is_dataclass
from hashlib import sha256
from math import exp
from typing import Any, Mapping
import json, math
import numpy as np
import pandas as pd

VERSION = "breakout-regime-shadow-1.0.0-20260624"
HORIZONS = (1,3,6)
STATES = ("bull_normal","bear_normal","compression","bull_breakout","bear_breakout","failed_breakout","transition_unknown")


def _f(x, d=0.0):
    try:
        v=float(x); return v if math.isfinite(v) else d
    except Exception: return d

def _snap(x):
    if isinstance(x, Mapping): return dict(x)
    if is_dataclass(x): return asdict(x)
    return dict(vars(x)) if hasattr(x,"__dict__") else {}

def _softmax(v):
    a=np.asarray(v,dtype=float); a=a-np.nanmax(a); e=np.exp(np.clip(a,-30,30)); s=e.sum(); return e/s if s else np.ones_like(e)/len(e)

def _ohlc(state):
    for k in ("canonical_completed_ohlc_df_20260617","last_df","dv_pp_df","lunch_5layer_powerbi_df"):
        x=state.get(k)
        if isinstance(x,pd.DataFrame) and len(x)>=20:
            y=x.copy()
            y.columns=[str(c).lower() for c in y.columns]
            if all(c in y for c in ("open","high","low","close")): return y
    return pd.DataFrame()

def _features(df):
    c=df.close.astype(float); o=df.open.astype(float); h=df.high.astype(float); l=df.low.astype(float)
    r=np.log(c/c.shift(1)).replace([np.inf,-np.inf],np.nan).fillna(0)
    ar=r.abs(); rng=(h-l).abs(); tr=pd.concat([rng,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    vol3=r.rolling(3,min_periods=2).std().iloc[-1]; vol8=r.rolling(8,min_periods=4).std().iloc[-1]
    vol24=r.rolling(24,min_periods=8).std().iloc[-1]; vol120=r.rolling(120,min_periods=24).std().iloc[-1]
    daily=max(_f(vol24),1e-8); expansion=_f((0.55*vol3+0.45*vol8)/daily,1.0)
    rv=_f((r.tail(24)**2).sum()); bp=_f((np.pi/2)*(ar*ar.shift(1)).tail(24).sum()); jump=max(rv-bp,0.0); jump_ratio=jump/max(rv,1e-12)
    zret=_f(r.iloc[-1]/max(_f(r.rolling(48,min_periods=12).std().iloc[-1]),1e-8))
    range_ratio=_f(rng.iloc[-1]/max(_f(rng.rolling(24,min_periods=8).median().iloc[-1]),1e-8),1.0)
    trend3=_f(c.iloc[-1]/c.iloc[-4]-1) if len(c)>=4 else 0
    trend12=_f(c.iloc[-1]/c.iloc[-13]-1) if len(c)>=13 else trend3
    cp_raw=max(abs(zret)-1.0,0)+max(expansion-1.0,0)+max(range_ratio-1.5,0)*0.5
    cp=float(np.clip(1-exp(-0.45*cp_raw),0,0.99))
    vol_state="shock" if expansion>2.0 else "expansion" if expansion>1.25 else "compression" if expansion<0.7 else "normal"
    return {"return":_f(r.iloc[-1]),"trend3":trend3,"trend12":trend12,"vol3":_f(vol3),"vol8":_f(vol8),"vol24":_f(vol24),"vol120":_f(vol120),"expansion_ratio":expansion,"jump_ratio":jump_ratio,"jump_score":float(np.clip(jump_ratio*range_ratio,0,3)),"range_ratio":range_ratio,"changepoint_probability":cp,"run_length_estimate":int(max(1,round((1-cp)*24))),"volatility_state":vol_state,"atr":_f(tr.rolling(14,min_periods=5).mean().iloc[-1]),"price":_f(c.iloc[-1])}

def _breakout(f):
    bull=max(f["trend3"],0)*7000 + max(f["trend12"],0)*3500 + max(f["range_ratio"]-1,0)*0.8 + f["jump_ratio"]*0.8
    bear=max(-f["trend3"],0)*7000 + max(-f["trend12"],0)*3500 + max(f["range_ratio"]-1,0)*0.8 + f["jump_ratio"]*0.8
    failed=f["changepoint_probability"]*0.8 + f["jump_ratio"]*0.5 + (0.6 if f["trend3"]*f["trend12"]<0 else 0)
    no=max(0.2,1.4-f["expansion_ratio"]-0.5*f["jump_ratio"])
    p=_softmax([bull,bear,failed,no]); labels=("bull_breakout","bear_breakout","failed_breakout","no_breakout")
    probs={labels[i]:float(p[i]) for i in range(4)}
    label=max(probs,key=probs.get)
    if label!="no_breakout" and probs[label]<0.45: label="mixed_breakout"
    if label=="no_breakout" and f["range_ratio"]>1.35: label="continuous_breakout"
    return probs,label

def _regime_probs(f,bp,scale):
    trend=(0.65*f["trend3"]+0.35*f["trend12"])*9000/scale
    scores=[trend,-trend,1.3-f["expansion_ratio"],2.2*bp["bull_breakout"],2.2*bp["bear_breakout"],1.9*bp["failed_breakout"],2.0*f["changepoint_probability"]]
    p=_softmax(scores); return {STATES[i]:float(p[i]) for i in range(len(STATES))}

def _paths(f,bp):
    px=f["price"]; atr=max(f["atr"],px*0.0002); direction=np.sign(0.65*f["trend3"]+0.35*f["trend12"])
    out={}; combined={}; weights={"normal":bp["no_breakout"],"bull_breakout":bp["bull_breakout"],"bear_breakout":bp["bear_breakout"],"failed_breakout":bp["failed_breakout"]}
    for h in HORIZONS:
        normal=px + direction*atr*0.22*np.sqrt(h)
        bull=px + atr*(0.55+0.32*h)*max(0.6,f["expansion_ratio"])
        bear=px - atr*(0.55+0.32*h)*max(0.6,f["expansion_ratio"])
        failed=px - direction*atr*(0.35+0.18*h)
        vals={"normal":normal,"bull_breakout":bull,"bear_breakout":bear,"failed_breakout":failed}
        combined[h]=sum(weights[k]*v for k,v in vals.items()); out[h]=vals
    return out,combined,weights

def _intervals(state, snap, f, combined, breakout_label):
    hist=state.get("prediction_outcomes") or state.get("settled_prediction_outcomes") or []
    if isinstance(hist,pd.DataFrame): rows=hist.to_dict("records")
    elif isinstance(hist,list): rows=[x for x in hist if isinstance(x,Mapping)]
    else: rows=[]
    result={}
    for h in HORIZONS:
        residuals=[]
        for r in rows:
            rh=_f(r.get("horizon") or r.get("horizon_hours"),-1)
            if int(rh)!=h: continue
            e=r.get("absolute_error",r.get("path_mae",r.get("error")))
            if e is not None and math.isfinite(_f(e,float("nan"))): residuals.append(abs(float(e)))
        fallback="conditioned" if len(residuals)>=30 else "horizon" if len(residuals)>=10 else "volatility_proxy"
        q=float(np.quantile(residuals,0.90)) if residuals else max(f["atr"]*np.sqrt(h),f["price"]*0.00025*np.sqrt(h))
        covered=[bool(r.get("covered")) for r in rows if int(_f(r.get("horizon") or r.get("horizon_hours"),-1))==h and r.get("covered") is not None]
        actual=float(np.mean(covered)) if covered else None
        deficit=max(0,0.90-actual) if actual is not None else 0
        expansion=1+2*deficit+(0.45 if f["volatility_state"]=="shock" else 0.2 if f["volatility_state"]=="expansion" else 0)+(0.25 if "jump" in breakout_label else 0)
        width=q*expansion
        result[h]={"forecast":combined[h],"lower":combined[h]-width,"upper":combined[h]+width,"uncertainty":width,"target_coverage":0.90,"actual_coverage":actual,"coverage_deficit":deficit if actual is not None else None,"interval_width":2*width,"interval_expansion_factor":expansion,"calibration_sample_count":len(residuals),"calibration_fallback_level":fallback}
    return result

def _priorities(regimes,bp,f,snap):
    rp=regimes["combined"]; bull=rp["bull_normal"]+rp["bull_breakout"]; bear=rp["bear_normal"]+rp["bear_breakout"]
    conflict=1-abs(bull-bear); drift=min(1,f["changepoint_probability"]+0.25*(f["volatility_state"]=="shock"))
    buy=max(0,bull*10-2.2*conflict-1.8*drift); sell=max(0,bear*10-2.2*conflict-1.8*drift); wait=min(10,2+5*conflict+4*drift)
    vals=np.array([buy,sell,wait]); vals=10*vals/max(vals.max(),1e-9)
    pr={"BUY":float(vals[0]),"SELL":float(vals[1]),"WAIT":float(vals[2])}
    evidence=max(rp.values())>=0.34 and f["changepoint_probability"]<0.72
    action=max(pr,key=pr.get) if evidence and max(pr.values())>=5.5 else "WAIT"
    prod=str(snap.get("decision") or snap.get("current_decision") or "WAIT").upper()
    return pr,action,prod,evidence,conflict,drift

def build(snapshot, state):
    snap=_snap(snapshot); df=_ohlc(state); run_id=str(snap.get("run_id") or snap.get("canonical_calculation_id") or "")
    if not run_id: return {"ok":False,"status":"MISSING_RUN_ID","shadow_only":True}
    if df.empty: return {"ok":False,"status":"INSUFFICIENT_HISTORY","run_id":run_id,"shadow_only":True,"evidence_sufficiency":"INSUFFICIENT"}
    f=_features(df); bp,label=_breakout(f)
    standards={"lower":_regime_probs(f,bp,0.75),"middle":_regime_probs(f,bp,1.0),"higher":_regime_probs(f,bp,1.35)}
    weights={"lower":0.20,"middle":0.35,"higher":0.45}
    if f["changepoint_probability"]>=0.55: weights={"lower":0.32,"middle":0.43,"higher":0.25}
    combined={s:sum(weights[k]*standards[k][s] for k in weights) for s in STATES}; total=sum(combined.values()); combined={k:v/total for k,v in combined.items()}
    regimes={**standards,"combined":combined,"weights":weights}
    candidates,combined_path,path_weights=_paths(f,bp); intervals=_intervals(state,snap,f,combined_path,label)
    priorities,shadow_decision,prod,evidence,conflict,drift=_priorities(regimes,bp,f,snap)
    current=max(combined,key=combined.get); confirmed=evidence and combined[current]>=0.36 and conflict<0.82
    current_regime=current.upper() if confirmed else "TRANSITION / UNCONFIRMED"
    utility={a:priorities[a]/10 for a in priorities}; cost=_f(snap.get("spread") or snap.get("transaction_cost"),0)
    utility["BUY"]-=cost+0.15*drift; utility["SELL"]-=cost+0.15*drift; utility["WAIT"]-=0.02
    explanation=(f"{label.replace('_',' ')} selected from price structure, range expansion, volatility, jump, transition and persistence evidence; "
                 f"changepoint={f['changepoint_probability']:.2f}, expansion={f['expansion_ratio']:.2f}, jump={f['jump_ratio']:.2f}.")
    payload={"ok":True,"shadow_only":True,"version":VERSION,"run_id":run_id,"symbol":str(snap.get("symbol") or "EURUSD"),"timeframe":str(snap.get("timeframe") or "H1"),"broker_candle_time":str(snap.get("broker_candle_time") or snap.get("candle_time") or ""),"features":f,"breakout":{"classification":label,"probabilities":bp,"continuation_probability":bp["bull_breakout"]+bp["bear_breakout"],"reversal_probability":bp["failed_breakout"]},"candidate_paths":candidates,"path_weights":path_weights,"combined_path":combined_path,"adaptive_intervals":intervals,"regimes":regimes,"current_regime":current_regime,"master_regime":max(combined,key=combined.get).upper(),"priorities":priorities,"production_current_decision":prod,"shadow_master_decision":shadow_decision,"decision_agreement":prod==shadow_decision,"utilities":utility,"expected_value_after_cost":max(utility.values()),"expected_adverse_impact":max(v["uncertainty"] for v in intervals.values()),"evidence_sufficiency":"SUFFICIENT" if evidence else "INSUFFICIENT","reversal_trigger":"Opposite directional probability exceeds current by 0.15 with changepoint below 0.55","explanation":explanation,"history":[],"audit":{"causal":True,"filtered_not_smoothed":True,"production_unchanged":True,"source_rows":len(df),"payload_hash":""}}
    payload["audit"]["payload_hash"]=sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()
    return payload

def publish(state, snapshot):
    result=build(snapshot,state); key="breakout_regime_shadow_20260624"; old=state.get(key)
    if isinstance(old,Mapping) and old.get("run_id")==result.get("run_id") and old.get("audit",{}).get("payload_hash")==result.get("audit",{}).get("payload_hash"): return dict(old)
    state[key]=result; return result
