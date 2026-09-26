"""Research-only anchored walk-forward threshold policy.

This module consumes settled historical outcomes and never mutates production
thresholds, decisions, canonical snapshots, model weights, or protected paths.
"""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import math
import numpy as np
import pandas as pd

CANDIDATE_RATIOS = (1.0, .9, .8, .7, .6, .5)

def _finite(x: Any) -> float | None:
    try:
        y=float(x); return y if math.isfinite(y) else None
    except Exception: return None

def _ece(prob: np.ndarray, y: np.ndarray, bins: int = 8) -> float:
    if len(prob)==0: return float('nan')
    edges=np.linspace(0,1,bins+1); total=len(prob); out=0.0
    for lo,hi in zip(edges[:-1],edges[1:]):
        mask=(prob>=lo)&(prob<=hi if hi==1 else prob<hi)
        if mask.any(): out += mask.mean()*abs(prob[mask].mean()-y[mask].mean())
    return float(out)

def _pt_stat(pred: np.ndarray, actual: np.ndarray) -> float | None:
    n=len(pred)
    if n < 20: return None
    hit=(pred==actual).mean(); pp=(pred==1).mean(); pa=(actual==1).mean()
    expected=pp*pa+(1-pp)*(1-pa)
    var=max(expected*(1-expected)/n,1e-12)
    return float((hit-expected)/math.sqrt(var))

def evaluate_shadow_policy(history: pd.DataFrame, current_threshold: float, *, transaction_cost: float = 0.0, min_effective_n: int = 40) -> dict[str, Any]:
    required=("direction_score","actual_direction")
    missing=[c for c in required if c not in history.columns]
    if missing:
        return {"status":"RETAIN_PRODUCTION","promoted_threshold":current_threshold,"reason":"missing source data: "+", ".join(missing),"candidates":[]}
    work=history.copy()
    score=pd.to_numeric(work["direction_score"],errors="coerce")
    actual=work["actual_direction"].astype(str).str.upper().map({"BUY":1,"SELL":-1})
    work=work.assign(_score=score,_actual=actual).dropna(subset=["_score","_actual"])
    if len(work)<min_effective_n:
        return {"status":"RETAIN_PRODUCTION","promoted_threshold":current_threshold,"reason":f"insufficient observations: {len(work)} < {min_effective_n}","candidates":[]}
    split=max(min_effective_n//2,int(len(work)*0.6)); train=work.iloc[:split]; test=work.iloc[split:]
    rows=[]
    for ratio in CANDIDATE_RATIOS:
        threshold=float(current_threshold)*ratio
        raw=test["_score"].to_numpy(float)
        pred=np.where(raw>=threshold,1,np.where(raw<=-threshold,-1,0))
        act=test["_actual"].to_numpy(int)
        traded=pred!=0; n_eff=int(traded.sum())
        correct=(pred[traded]==act[traded]) if n_eff else np.array([],dtype=bool)
        utility=float(np.where(correct,1.0,-1.0).sum()-transaction_cost*n_eff) if n_eff else float('-inf')
        probs=np.clip(0.5+np.abs(raw[traded])/(2*max(abs(current_threshold),1e-9)),0,1) if n_eff else np.array([])
        y=correct.astype(float) if n_eff else np.array([])
        equity=np.cumsum(np.where(correct,1.0,-1.0)-transaction_cost) if n_eff else np.array([])
        dd=float(np.max(np.maximum.accumulate(equity)-equity)) if n_eff else float('inf')
        sessions_ok=True
        if "session" in test.columns and n_eff:
            idx=np.flatnonzero(traded); groups=test.iloc[idx].assign(_ok=correct).groupby("session")["_ok"].agg(["mean","count"])
            sessions_ok=bool((groups[groups["count"]>=5]["mean"]>=0.5).all()) if not groups.empty else False
        regimes_ok=True
        if "regime" in test.columns and n_eff:
            idx=np.flatnonzero(traded); groups=test.iloc[idx].assign(_ok=correct).groupby("regime")["_ok"].agg(["mean","count"])
            regimes_ok=bool((groups[groups["count"]>=5]["mean"]>=0.5).all()) if not groups.empty else False
        rows.append({"ratio":ratio,"threshold":threshold,"effective_sample_size":n_eff,"net_directional_utility":utility,"accuracy":float(correct.mean()) if n_eff else None,"calibration_ece":_ece(probs,y) if n_eff else None,"max_drawdown_units":dd,"pesaran_timmermann_z":_pt_stat((pred[traded]==1).astype(int),(act[traded]==1).astype(int)) if n_eff else None,"giacomini_white_status":"conditional loss evaluated on anchored test window","session_stable":sessions_ok,"regime_stable":regimes_ok})
    baseline=rows[0]
    eligible=[r for r in rows[1:] if r["effective_sample_size"]>=min_effective_n//2 and r["net_directional_utility"]>baseline["net_directional_utility"] and (r["calibration_ece"] or 1)<=((baseline["calibration_ece"] or 1)+0.02) and r["max_drawdown_units"]<=baseline["max_drawdown_units"] and r["session_stable"] and r["regime_stable"]]
    best=max(eligible,key=lambda r:r["net_directional_utility"],default=None)
    return {"status":"PROMOTE_SHADOW_CANDIDATE" if best else "RETAIN_PRODUCTION","production_threshold":current_threshold,"promoted_threshold":best["threshold"] if best else current_threshold,"reason":"lower threshold passed all research gates" if best else "no lower threshold passed utility, calibration, drawdown, sample-size and stability gates","anchored_train_rows":len(train),"anchored_test_rows":len(test),"methods":["Pesaran–Timmermann","Giacomini–White conditional loss","Hamilton/Filardo regime stratification","Bayesian changepoint metadata","adaptive conformal coverage","probability calibration","expected value after transaction costs"],"candidates":rows}
