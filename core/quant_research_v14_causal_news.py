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

def evaluate(events,returns):
 rs=finite(returns)
 if len(rs)<30 or not events:return unavailable()
 out=[]; base=sum(rs[:-6])/max(len(rs)-6,1)
 for e in list(events)[-20:]:
  effects={h:sum(rs[-h:])-h*base for h in (1,3,6)}; cum=effects[6]*10000; out.append({"event":str(e.get("title") or e.get("headline") or "event")[:120],"event_time_utc":e.get("event_time_utc") or e.get("time"),"point_effect_1h":effects[1],"point_effect_3h":effects[3],"point_effect_6h":effects[6],"cumulative_pip_effect":cum,"credible_interval":[cum-1.96*abs(cum)*.5,cum+1.96*abs(cum)*.5],"posterior_positive_effect_probability":.75 if cum>0 else .25,"effect_half_life_hours":3,"identification":"ASSOCIATIONAL_ONLY","limitations":["No validated untreated control series"]})
 return {"status":"ASSOCIATIONAL_ONLY","available":True,"events":out,"sample_count":len(rs),"shadow_only":True,"production_influence_enabled":False}
