from __future__ import annotations
import hashlib, json

def stable_hash(value): return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()
def equation_parameters():
    return {"direction_score":"Σ(final_weight × standardized_action)","disagreement":"Σ(final_weight × (action-direction_score)^2)","master_strength":"direction_score × (1-uncertainty)","weight_formula":"dynamic × conditional_reliability × validation_gate × correlation_penalty × data_quality"}
