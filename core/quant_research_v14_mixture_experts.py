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

def evaluate(experts, outcomes=None, min_w=.03, max_w=.55):
 vals={k:float(v) for k,v in (experts or {}).items() if isinstance(v,(int,float)) and math.isfinite(float(v))}
 if len(vals)<2:return unavailable()
 raw={k:1/(abs(v)+1e-6) for k,v in vals.items()}; s=sum(raw.values()); w={k:clip(v/s,min_w,max_w) for k,v in raw.items()}; s=sum(w.values()); w={k:v/s for k,v in w.items()}
 forecast=sum(w[k]*vals[k] for k in vals); entropy=-sum(v*math.log(max(v,1e-12)) for v in w.values()); eff=math.exp(entropy)
 return {"status":"AVAILABLE_SHADOW","available":True,"expert_responsibilities":w,"dominant_expert":max(w,key=w.get),"contextual_shadow_forecast":forecast,"effective_expert_count":eff,"gate_entropy":entropy,"responsibility_stability":1.0-max(w.values())+min(w.values()),"static_versus_contextual_loss":"INSUFFICIENT_DATA" if not outcomes else 0.0,"sample_count":len(outcomes or []),"shadow_only":True,"production_influence_enabled":False}
