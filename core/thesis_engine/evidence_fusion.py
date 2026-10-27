from __future__ import annotations
from .correlation_penalty import effective_count

def fuse(rows, regime_entropy, cp_prob, calibration_error=0.0, missing_ratio=0.0, interval_width=0.0):
    valid=[r for r in rows if r.get("final_weight",0)>0]
    if not valid: return {"direction_score":0.0,"disagreement":0.0,"uncertainty":1.0,"master_strength":0.0,"effective_independent_model_count":0.0}
    ds=sum(r["final_weight"]*r["standardized_action"] for r in valid)
    dis=sum(r["final_weight"]*(r["standardized_action"]-ds)**2 for r in valid)
    unc=max(0.0,min(1.0,.22*regime_entropy+.22*cp_prob+.22*min(1,dis)+.14*calibration_error+.10*missing_ratio+.10*min(1,interval_width)))
    return {"direction_score":ds,"disagreement":dis,"uncertainty":unc,"master_strength":ds*(1-unc),"effective_independent_model_count":effective_count([r["final_weight"] for r in valid])}
