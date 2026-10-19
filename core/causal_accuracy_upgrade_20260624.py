"""Causal shadow research for prediction paths and regimes.

The module is deliberately independent of Streamlit and production decision code.
It consumes saved rows, settles only fully matured horizons, and emits optional
canonical extensions. All state updates are incremental and shadow-only.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
import math
import numpy as np
import pandas as pd

VERSION = "2026.06.24.1"
HORIZONS = (1, 3, 6)
EPS = 1e-12


def _finite(x: Any, default=np.nan) -> float:
    try:
        y = float(x)
        return y if math.isfinite(y) else default
    except Exception:
        return default


def _prob(x: Any, default=.5) -> float:
    return float(np.clip(_finite(x, default), EPS, 1-EPS))


def _utc(x: Any) -> pd.Timestamp:
    return pd.to_datetime(x, utc=True, errors="coerce")


@dataclass(frozen=True)
class MaturityRecord:
    run_id: str
    prediction_time: str
    broker_candle_time: str
    horizon: int
    target_maturity_time: str
    matured: bool
    actual_future_price: float | None
    actual_direction: int | None
    model_prediction: float | None
    lower_interval: float | None
    upper_interval: float | None
    regime_at_prediction_time: str
    session_at_prediction_time: str
    outcome_settlement_time: str | None
    data_quality_status: str


def build_maturity_ledger(rows: pd.DataFrame, *, as_of: Any, run_id: str) -> pd.DataFrame:
    """Create one row per forecast horizon without using future-incomplete outcomes."""
    if rows is None or rows.empty:
        return pd.DataFrame(columns=MaturityRecord.__annotations__)
    asof = _utc(as_of)
    if pd.isna(asof):
        raise ValueError("as_of must be a finite timezone-aware timestamp")
    source = rows.copy(deep=False)
    time_col = next((c for c in ("prediction_time","broker_candle_time","Broker Time","time","Time") if c in source), None)
    if time_col is None:
        raise ValueError("prediction time column is required")
    out=[]
    for _, r in source.iterrows():
        pt = _utc(r.get(time_col))
        if pd.isna(pt) or pt >= asof:
            continue
        origin = _finite(r.get("origin_price", r.get("Close")))
        for h in HORIZONS:
            target = pt + pd.Timedelta(hours=h)
            actual = _finite(r.get(f"actual_price_h{h}"))
            predicted = _finite(r.get(f"predicted_price_h{h}"))
            complete = bool(target <= asof and np.isfinite(actual))
            direction = None if not complete or not np.isfinite(origin) else int(np.sign(actual-origin))
            lower = _finite(r.get(f"lower_h{h}", r.get("lower_interval")))
            upper = _finite(r.get(f"upper_h{h}", r.get("upper_interval")))
            quality = "VALID" if complete and np.isfinite(predicted) else ("MATURE_BUT_MISSING" if target <= asof else "PENDING")
            rec=MaturityRecord(
                str(r.get("run_id",run_id)), pt.isoformat(), pt.isoformat(), h, target.isoformat(), complete,
                float(actual) if complete else None, direction, float(predicted) if np.isfinite(predicted) else None,
                float(lower) if np.isfinite(lower) else None, float(upper) if np.isfinite(upper) else None,
                str(r.get("regime",r.get("regime_at_prediction_time","UNKNOWN"))),
                str(r.get("session",r.get("session_at_prediction_time","UNKNOWN"))),
                asof.isoformat() if complete else None, quality)
            out.append(asdict(rec))
    ledger=pd.DataFrame(out)
    if ledger.empty: return ledger
    return ledger.drop_duplicates(["run_id","prediction_time","horizon"], keep="first").sort_values(["prediction_time","horizon"])


def proper_scores(ledger: pd.DataFrame) -> dict[str, Any]:
    valid=ledger[(ledger.get("matured",False)==True) & ledger["actual_future_price"].notna() & ledger["model_prediction"].notna()].copy()
    if valid.empty: return {"status":"INSUFFICIENT_EVIDENCE","sample_count":0}
    valid["error"]=valid["model_prediction"]-valid["actual_future_price"]
    rows=[]
    for h,g in valid.groupby("horizon"):
        err=g["error"].to_numpy(float)
        covered=((g["actual_future_price"]>=g["lower_interval"])&(g["actual_future_price"]<=g["upper_interval"]))
        has_interval=g[["lower_interval","upper_interval"]].notna().all(axis=1)
        rows.append({"horizon":int(h),"sample_count":len(g),"mae":float(np.mean(np.abs(err))),"rmse":float(np.sqrt(np.mean(err**2))),"signed_bias":float(np.mean(err)),"interval_coverage":float(covered[has_interval].mean()) if has_interval.any() else np.nan,"interval_width":float((g.loc[has_interval,"upper_interval"]-g.loc[has_interval,"lower_interval"]).mean()) if has_interval.any() else np.nan})
    return {"status":"VALID","sample_count":len(valid),"by_horizon":rows}


def platt_calibrate(raw_prob: Iterable[float], labels: Iterable[int], target_prob: float, *, min_samples:int=12) -> dict[str,Any]:
    p=np.clip(np.asarray(list(raw_prob),float),1e-6,1-1e-6); y=np.asarray(list(labels),float)
    mask=np.isfinite(p)&np.isfinite(y); p=p[mask]; y=y[mask]
    if len(p)<min_samples or len(np.unique(y))<2:
        return {"method":"IDENTITY","probability":_prob(target_prob),"sample_count":len(p),"status":"INSUFFICIENT_EVIDENCE"}
    x=np.log(p/(1-p)); a,b=1.0,0.0
    for _ in range(40):
        z=np.clip(a*x+b,-30,30); q=1/(1+np.exp(-z)); w=np.maximum(q*(1-q),1e-6)
        X=np.column_stack([x,np.ones(len(x))]); grad=X.T@(q-y); H=X.T@(w[:,None]*X)+1e-4*np.eye(2)
        step=np.linalg.solve(H,grad); a-=step[0]; b-=step[1]
        if np.linalg.norm(step)<1e-8: break
    t=math.log(_prob(target_prob)/(1-_prob(target_prob))); calibrated=1/(1+math.exp(-float(np.clip(a*t+b,-30,30))))
    brier=float(np.mean((1/(1+np.exp(-np.clip(a*x+b,-30,30)))-y)**2))
    return {"method":"PLATT","probability":float(calibrated),"sample_count":len(p),"slope":float(a),"intercept":float(b),"brier":brier,"status":"VALID"}


def adaptive_conformal(residuals: Iterable[float], point: float, *, target_coverage=.9, previous_q:float|None=None, rate=.05) -> dict[str,Any]:
    r=np.abs(np.asarray(list(residuals),float)); r=r[np.isfinite(r)]
    if not np.isfinite(point): return {"status":"INVALID_POINT"}
    if len(r)<8: return {"status":"INSUFFICIENT_EVIDENCE","lower":np.nan,"upper":np.nan,"sample_count":len(r)}
    empirical=float(np.quantile(r,min(1.0,target_coverage),method="higher")); q=empirical if previous_q is None or not np.isfinite(previous_q) else (1-rate)*float(previous_q)+rate*empirical
    q=max(q,0.0); return {"status":"VALID","lower":float(point-q),"upper":float(point+q),"width":float(2*q),"quantile":float(q),"sample_count":len(r),"target_coverage":target_coverage}


def dynamic_model_average(losses: Mapping[str,Iterable[float]], *, forgetting=.97, min_weight=.02, max_weight=.85) -> dict[str,Any]:
    names=list(losses)
    if not names:return {"status":"INSUFFICIENT_EVIDENCE","weights":{}}
    scores=[]
    for n in names:
        a=np.asarray(list(losses[n]),float); a=a[np.isfinite(a)]
        if len(a)==0:scores.append(-50.0)
        else:
            age=np.arange(len(a)-1,-1,-1); w=forgetting**age; scores.append(-float(np.average(a,weights=w)))
    z=np.exp(np.asarray(scores)-np.max(scores)); w=z/z.sum(); w=np.clip(w,min_weight,max_weight); w=w/w.sum()
    return {"status":"VALID","weights":dict(zip(names,map(float,w))),"effective_models":float(1/np.sum(w*w)),"dominant_model":names[int(np.argmax(w))],"concentration_warning":bool(np.max(w)>.75)}


def bocpd_shadow(values: Iterable[float], *, hazard=.02, max_run=256) -> dict[str,Any]:
    x=np.asarray(list(values),float); x=x[np.isfinite(x)]
    if len(x)<3:return {"status":"INSUFFICIENT_EVIDENCE","change_probability":np.nan}
    run=np.array([1.0]); means=np.array([x[0]]); variances=np.array([1e-6])
    cp=.0
    for value in x[1:]:
        log_pred=-.5*(value-means)**2/(variances+1e-6)-.5*np.log(2*np.pi*(variances+1e-6))
        pred=np.exp(log_pred-np.max(log_pred))
        growth=run*pred*(1-hazard); cp=float(np.sum(run*pred*hazard)); new=np.r_[cp,growth][:max_run]; total=float(new.sum()); new = (new/total) if total>EPS else np.array([1.0])
        means=np.r_[value,(means*np.arange(1,len(means)+1)+value)/np.arange(2,len(means)+2)][:len(new)]
        variances=np.maximum(np.r_[1e-6,variances][:len(new)],1e-6); run=new
    return {"status":"VALID","change_probability":float(run[0]),"expected_run_length":float(np.dot(np.arange(len(run)),run)),"posterior_sum":float(run.sum()),"run_length_probabilities":run.tolist()}


def build_shadow_extension(history: pd.DataFrame, *, as_of: Any, run_id: str, predictions: Mapping[str,Any]|None=None) -> dict[str,Any]:
    ledger=build_maturity_ledger(history,as_of=as_of,run_id=run_id)
    scores=proper_scores(ledger)
    ext={"version":VERSION,"mode":"SHADOW_ONLY","production_influence_enabled":False,"run_id":run_id,"built_at_utc":datetime.now(timezone.utc).isoformat(),"outcome_ledger":ledger.to_dict("records"),"proper_scores":scores}
    settled=ledger[ledger.get("matured",False)==True] if not ledger.empty else pd.DataFrame()
    conformal={}
    for h in HORIZONS:
        g=settled[settled["horizon"]==h] if not settled.empty else pd.DataFrame()
        residuals=(g["model_prediction"]-g["actual_future_price"]).tolist() if not g.empty else []
        point=_finite((predictions or {}).get(f"h{h}",(predictions or {}).get(f"predicted_price_h{h}")))
        conformal[str(h)]=adaptive_conformal(residuals,point)
    ext["adaptive_conformal"]=conformal
    if history is not None and not history.empty:
        close=pd.to_numeric(history.get("Close",history.get("origin_price",pd.Series(dtype=float))),errors="coerce").dropna()
        ext["changepoint"]=bocpd_shadow(close.diff().dropna().to_numpy())
    else: ext["changepoint"]={"status":"INSUFFICIENT_EVIDENCE"}
    ext["promotion_gate"]={"status":"BLOCKED","reason":"SHADOW_ONLY_REQUIRES_MULTIPLE_MATURE_WALK_FORWARD_WINDOWS","all_tests_pass":False}
    return ext
