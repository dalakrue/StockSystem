from __future__ import annotations

def penalty(correlation, threshold=.75, strength=.5):
    c=float(correlation or 0.0)
    return 1.0 if c<=threshold else max(.1,1-strength*(c-threshold)/(1-threshold))
def effective_count(weights):
    vals=[float(x) for x in weights if float(x)>0]; return 0.0 if not vals else 1/sum(x*x for x in vals)
