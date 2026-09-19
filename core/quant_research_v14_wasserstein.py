from __future__ import annotations
import math, time
from typing import Any, Mapping, Sequence

def unavailable(reason="INSUFFICIENT_DATA"):
    return {"status": reason, "available": False, "shadow_only": True, "production_influence_enabled": False}

def finite(values):
    out=[]
    for v in values or []:
        try:
            x=float(v)
            if math.isfinite(x): out.append(x)
        except Exception: pass
    return out

def clip(x,lo,hi): return max(lo,min(hi,x))

def evaluate(scenarios,radius=.10):
 if len(scenarios or [])<10:return unavailable()
 actions=("BUY","SELL","WAIT","HOLD","REDUCE","EXIT"); losses={}
 for a in actions:
  vals=[]
  for r in scenarios:
   ret=float(r.get("return",0) or 0); cost=abs(float(r.get("cost",0) or 0)); sign=1 if a in ("BUY","HOLD") else -1 if a=="SELL" else 0; vals.append(-sign*ret+cost+(0.25*abs(ret) if a in ("WAIT","REDUCE","EXIT") else 0))
  empirical=sum(vals)/len(vals); losses[a]={"empirical_expected_loss":empirical,"worst_case_expected_loss":empirical+radius*(max(vals)-min(vals) if vals else 0)}
 pref=min(actions,key=lambda a:losses[a]["worst_case_expected_loss"]); ordered=sorted(v["worst_case_expected_loss"] for v in losses.values())
 return {"status":"AVAILABLE_SHADOW","available":True,"actions":losses,"robustness_radius":radius,"robust_preferred_action":pref,"radius_sensitivity":{str(r):min(actions,key=lambda a:losses[a]["empirical_expected_loss"]+r) for r in (0,.05,.1,.2)},"production_decision_agreement":"UNAVAILABLE","robustness_margin":ordered[1]-ordered[0],"sample_count":len(scenarios),"shadow_only":True,"production_influence_enabled":False}
