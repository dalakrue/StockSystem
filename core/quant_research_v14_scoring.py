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

def evaluate(probabilities,labels,intervals=None):
 p=finite(probabilities); y=finite(labels); n=min(len(p),len(y)); p=p[-n:]; y=y[-n:]
 if n<20:return unavailable()
 eps=1e-12; b=sum((a-b)**2 for a,b in zip(p,y))/n; log=-sum(b*math.log(max(a,eps))+(1-b)*math.log(max(1-a,eps)) for a,b in zip(p,y))/n; base=sum((sum(y)/n-b)**2 for b in y)/n
 return {"status":"BETTER" if b<base else "WORSE","available":True,"brier_score":b,"logarithmic_score":log,"crps_discrete_approximation":b,"interval_score":"INSUFFICIENT_DATA","weighted_interval_score":"INSUFFICIENT_DATA","ranked_probability_score":b,"calibration_component":abs(sum(p)/n-sum(y)/n),"sharpness_component":sum(abs(a-.5) for a in p)/n,"score_sample_count":n,"baseline_comparison":base,"block_bootstrap_uncertainty":"INSUFFICIENT_DATA","shadow_only":True,"production_influence_enabled":False}
