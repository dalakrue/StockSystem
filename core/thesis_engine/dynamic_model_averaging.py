from __future__ import annotations
import math

def update_weights(prior, likelihoods, forgetting_factor=.97, reset_factor=0.0):
    names=list(likelihoods); n=max(1,len(names)); eq=1/n; vals={}
    for name in names:
        p=max(1e-12,float((prior or {}).get(name,eq)))**forgetting_factor
        p=(1-reset_factor)*p+reset_factor*eq
        vals[name]=p*max(1e-12,float(likelihoods[name]))
    s=sum(vals.values()) or 1.0
    return {k:v/s for k,v in vals.items()}
