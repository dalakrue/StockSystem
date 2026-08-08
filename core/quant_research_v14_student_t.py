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

def evaluate(rows, max_rows=1500, nu=5.0):
 xs=finite(rows)[-max_rows:]
 if len(xs)<20:return unavailable()
 mu=xs[0]; var=max(sum((x-mu)**2 for x in xs[:20])/20,1e-10); hist=[]
 for x in xs:
  e=x-mu; z=e/math.sqrt(var); w=(nu+1)/(nu+z*z); k=clip(.08*w,.005,.25); mu+=k*e; var=.94*var+.06*w*e*e; hist.append({"innovation":e,"standardized_innovation":z,"weight":w,"outlier_probability":clip(1-w/(1+w),0,1)})
 gaussian=sum((x-sum(xs)/len(xs))**2 for x in xs)/len(xs); robust=sum(h["weight"]*h["innovation"]**2 for h in hist)/len(hist)
 return {"status":"AVAILABLE_SHADOW","available":True,"filtered_direction":mu,"filtered_momentum":sum(xs[-3:]),"filtered_volatility":math.sqrt(var),"innovation_residual":hist[-1]["innovation"],"standardized_innovation":hist[-1]["standardized_innovation"],"effective_student_t_observation_weight":hist[-1]["weight"],"outlier_probability":hist[-1]["outlier_probability"],"degrees_of_freedom":nu,"state_uncertainty":math.sqrt(var),"shock_resistant_projected_state":mu+0.5*sum(xs[-3:])/3,"student_t_loss":robust,"gaussian_benchmark_loss":gaussian,"history":hist[-25:],"sample_count":len(xs),"shadow_only":True,"production_influence_enabled":False}
