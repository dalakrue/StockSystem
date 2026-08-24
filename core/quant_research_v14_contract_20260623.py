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

SCHEMA_VERSION="quant-research-v14-shadow-1.0"
METHODS=("student_t_state","mixture_of_experts","venn_abers_calibration","caviar_tail_risk","conformal_risk_control","wasserstein_robust_decision","asymmetric_copula","knockoff_selection","proper_scoring","causal_news_impact")

def base(identity):
 return {"schema_version":SCHEMA_VERSION,"identity":dict(identity),"shadow_only":True,"production_influence_enabled":False,"production_decision_changed":False,"protected_weights_changed":False}
