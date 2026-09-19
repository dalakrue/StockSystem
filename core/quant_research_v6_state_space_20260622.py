"""Deterministic Kalman and Hamilton-style transition evidence."""
from __future__ import annotations
from typing import Any, Mapping
import numpy as np, pandas as pd
from core.quant_research_v6_contract_20260622 import finite

def run_kalman_state(frame:pd.DataFrame)->dict[str,Any]:
 y=np.log(pd.to_numeric(frame.close,errors="coerce").dropna().to_numpy(float)); n=len(y)
 if n<8:return {"method_id":"kalman_state","status":"INSUFFICIENT_EVIDENCE","sample_count":n}
 x=np.array([y[0],0.0]); P=np.eye(2); F=np.array([[1.,1.],[0.,1.]]); H=np.array([[1.,0.]])
 q=max(np.var(np.diff(y)),1e-9)*0.03; Q=np.array([[q,q/2],[q/2,q]]); r=max(np.var(np.diff(y)),1e-9); R=np.array([[r]])
 innovation=0.; norm=0.
 for obs in y[1:]:
  x=F@x; P=F@P@F.T+Q; innovation=float(obs-(H@x)[0]); S=float((H@P@H.T+R)[0,0]); K=(P@H.T)/S; x=x+(K[:,0]*innovation); P=(np.eye(2)-K@H)@P; norm=innovation/max(S**.5,1e-12)
 return {"method_id":"kalman_state","status":"AVAILABLE","sample_count":n,"latent_level":finite(np.exp(x[0])),"latent_slope_velocity":finite(x[1]),"state_uncertainty":finite(np.trace(P)),"innovation":finite(innovation),"normalized_innovation_score":finite(norm),"deterministic":True,"shadow_only":True}

def run_hamilton_style(frame:pd.DataFrame,canonical:Mapping[str,Any])->dict[str,Any]:
 ret=pd.to_numeric(frame.close,errors="coerce").pct_change().dropna(); n=len(ret)
 if n<30:return {"method_id":"hamilton_transition","status":"INSUFFICIENT_EVIDENCE","sample_count":n}
 vol=ret.rolling(12,min_periods=6).std(); med=float(vol.median()); states=(vol>med).astype(int).dropna().astype(int)
 counts=np.ones((2,2),float)
 for a,b in zip(states.iloc[:-1],states.iloc[1:]):counts[int(a),int(b)]+=1
 trans=counts/counts.sum(axis=1,keepdims=True); cur=int(states.iloc[-1]); age=1
 for v in states.iloc[-2::-1]:
  if int(v)!=cur:break
  age+=1
 probs=np.array([.15,.85]) if cur else np.array([.85,.15])
 risk=float(1-trans[cur,cur])
 return {"method_id":"hamilton_transition","status":"AVAILABLE","sample_count":n,"filtered_regime_probabilities":{"LOW_VOL":float(probs[0]),"HIGH_VOL":float(probs[1])},"transition_probabilities":trans.round(6).tolist(),"regime_age_candles":age,"transition_risk_score":risk,"existing_regime_label_preserved":str((canonical.get("regime") or {}).get("major_regime") if isinstance(canonical.get("regime"),Mapping) else canonical.get("regime") or "UNAVAILABLE"),"shadow_only":True}
