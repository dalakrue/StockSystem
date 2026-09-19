"""Empirical hidden semi-Markov-style regime duration shadow model."""
from __future__ import annotations
from typing import Any,Mapping
import time
import numpy as np
import pandas as pd
from core.quant_research_v7_contract_20260622 import common_method

METHOD_ID="hidden_semi_markov_duration";MIN_SAMPLE=8

def _regime_col(frame:pd.DataFrame)->str|None:
 return next((c for c in frame.columns if str(c).lower() in {"regime","major_regime","current_regime","regime_family"}),None)

def regime_runs(frame:pd.DataFrame,current_regime:str)->tuple[list[dict[str,Any]],dict[str,Any]]:
 if not isinstance(frame,pd.DataFrame) or frame.empty:return [],{"age":0,"right_censored":True}
 col=_regime_col(frame)
 if col is None:return [],{"age":0,"right_censored":True}
 vals=frame[col].astype(str).fillna("UNAVAILABLE").tolist();runs=[];start=0
 for i in range(1,len(vals)+1):
  if i==len(vals) or vals[i]!=vals[start]:
   runs.append({"regime":vals[start],"duration":i-start,"right_censored":i==len(vals)})
   start=i
 current=runs[-1] if runs else {"regime":current_regime,"duration":1,"right_censored":True}
 return runs,{"age":int(current["duration"]),"right_censored":bool(current["right_censored"]),"regime":current["regime"]}

def _family(name:str)->str:
 up=str(name).upper()
 if "BULL" in up:return "BULL"
 if "BEAR" in up:return "BEAR"
 return "RANGE_OR_OTHER"

def run_hsmm(metric_history:pd.DataFrame,canonical:Mapping[str,Any],*,cutoff_time:Any,bootstrap_service=None)->dict[str,Any]:
 started=time.perf_counter();current=str(((canonical.get("regime") or {}).get("major_regime") if isinstance(canonical.get("regime"),Mapping) else None) or "UNAVAILABLE")
 runs,cur=regime_runs(metric_history,current);completed=[r for r in runs if not r["right_censored"]]
 same=[r["duration"] for r in completed if r["regime"]==cur.get("regime")]
 used_family=False
 if len(same)<MIN_SAMPLE:
  fam=_family(cur.get("regime"));same=[r["duration"] for r in completed if _family(r["regime"])==fam];used_family=True
 if len(same)<3:return common_method(METHOD_ID,status="INSUFFICIENT_EVIDENCE",sample_count=len(same),minimum_sample_required=MIN_SAMPLE,cutoff_time=cutoff_time,output_metrics={"current_regime_age":cur.get("age"),"right_censored_current_regime":True},assumptions=["persisted regime history is ordered"],limitations=["empirical duration estimates are not guaranteed"])
 durations=np.asarray(same,dtype=float);age=max(1,int(cur.get("age") or 1));expected=max(age,float(np.mean(durations)));remaining=max(0.0,expected-age)
 surv={}
 for h in (1,2,3,6):
  denom=max(1,int(np.sum(durations>=age)));surv[f"H+{h}"]=float(np.clip(np.sum(durations>=age+h)/denom,0,1))
 transitions=[]
 for a,b in zip(runs,runs[1:]):
  if a["regime"]==cur.get("regime") or (used_family and _family(a["regime"])==_family(cur.get("regime"))):transitions.append(b["regime"])
 next_regime=max(set(transitions),key=transitions.count) if transitions else "UNAVAILABLE"
 warning="HIGH" if surv["H+1"]<0.35 else "WATCH" if surv["H+3"]<0.50 else "LOW"
 uncertainty=bootstrap_service.mean(durations) if bootstrap_service is not None and len(durations)>=8 else {"status":"UNAVAILABLE"}
 output={"current_regime":cur.get("regime"),"current_regime_age":age,"expected_total_duration":round(expected,3),"expected_duration_remaining":round(remaining,3),"survival_probability":{k:round(v,4) for k,v in surv.items()},"survival_probability_h1":round(surv["H+1"],4),"survival_probability_h6":round(surv["H+6"],4),"most_likely_next_regime":next_regime,"premature_transition_warning":warning,"right_censored_current_regime":True,"family_fallback_used":used_family,"duration_uncertainty":uncertainty,"runtime_ms":round((time.perf_counter()-started)*1000,3)}
 return common_method(METHOD_ID,status="AVAILABLE",sample_count=len(durations),minimum_sample_required=MIN_SAMPLE,cutoff_time=cutoff_time,output_metrics=output,assumptions=["completed regime spells are representative","right-censored current spell is not counted as completed"],limitations=["empirical estimates are not guaranteed","family pooling is used when individual regime support is small"])

__all__=["regime_runs","run_hsmm"]
