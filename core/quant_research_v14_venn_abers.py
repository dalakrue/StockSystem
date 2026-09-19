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

def evaluate(probabilities, labels):
 p=finite(probabilities); y=finite(labels); n=min(len(p),len(y)); p=p[-n:]; y=y[-n:]
 if n<20:return unavailable()
 b0=sum((a-b)**2 for a,b in zip(p,y))/n; rate=sum(y)/n; reg=[clip(.75*a+.25*rate,0,1) for a in p]; b1=sum((a-b)**2 for a,b in zip(reg,y))/n; width=clip(1.96*math.sqrt(max(rate*(1-rate),1e-6)/n),.01,.5)
 q=reg[-1]
 return {"status":"AVAILABLE_SHADOW","available":True,"raw_probability":p[-1],"lower_probability":clip(q-width,0,1),"upper_probability":clip(q+width,0,1),"regularized_probability":q,"interval_width":2*width,"calibration_sample_count":n,"brier_score_before":b0,"brier_score_after":b1,"calibration_slope":.75,"calibration_intercept":.25*rate,"fallback_level":"POOLED","shadow_only":True,"production_influence_enabled":False}
