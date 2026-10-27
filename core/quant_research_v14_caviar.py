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

def _q(xs,q):
 s=sorted(xs); return s[int(clip(round((len(s)-1)*q),0,len(s)-1))]
def evaluate(returns):
 xs=finite(returns)[-1500:]
 if len(xs)<40:return unavailable()
 qs={str(q):_q(xs,q) for q in (.01,.05,.10,.90,.95,.99)}; lo=qs['0.05']; hi=qs['0.95']; exc=sum(x<lo for x in xs)/len(xs); pin=sum((.05-(1 if x<lo else 0))*(x-lo) for x in xs)/len(xs)
 breaches=[{"value":x,"lower_breach":x<lo,"upper_breach":x>hi} for x in xs[-25:]]
 return {"status":"AVAILABLE_SHADOW","available":True,"quantiles":qs,"lower_adverse_boundary":lo,"upper_adverse_boundary":hi,"tail_asymmetry":abs(qs['0.01'])-abs(qs['0.99']),"quantile_exceedance_rate":exc,"dynamic_exit_risk_score":clip(exc/.05,0,2)*5,"tp_feasibility":clip((hi/max(abs(lo),1e-9))/2,0,1),"expected_adverse_excursion_class":"HIGH" if abs(lo)>2*sum(abs(x) for x in xs)/len(xs) else "NORMAL","breach_clustering":sum(a['lower_breach'] for a in breaches),"backtest_calibration_status":"PASS" if .025<=exc<=.075 else "REVIEW","pinball_loss":pin,"history":breaches,"sample_count":len(xs),"shadow_only":True,"production_influence_enabled":False}
