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

def evaluate(losses,target=.10):
 xs=sorted(finite(losses))
 if len(xs)<20:return unavailable()
 idx=int(clip(math.ceil((len(xs)+1)*(1-target))-1,0,len(xs)-1)); th=xs[idx]; risk=sum(x>th for x in xs)/len(xs); upper=clip(risk+math.sqrt(math.log(20)/(2*len(xs))),0,1)
 return {"status":"PASS" if upper<=target else "SHADOW_REVIEW","available":True,"target_risk":target,"selected_threshold":th,"empirical_risk":risk,"calibrated_upper_risk_estimate":upper,"calibration_count":len(xs),"fallback_level":"POOLED","shadow_action":"SHADOW_ACTIONABLE" if upper<=target else "SHADOW_REVIEW","shadow_only":True,"production_influence_enabled":False}
