from __future__ import annotations
import math

def normalize_probabilities(p):
    p={k:max(1e-12,float((p or {}).get(k,0.0) or 0.0)) for k in ("BUY","SELL","HOLD")}; s=sum(p.values())
    return {k:v/s for k,v in p.items()}

def brier_score(p, actual):
    p=normalize_probabilities(p); return sum((p[k]-(1.0 if k==actual else 0.0))**2 for k in p)/3.0

def log_loss(p, actual): return -math.log(normalize_probabilities(p).get(actual,1e-12))
def calibration_error(rows):
    rows=list(rows or []); return sum(abs(float(r.get("confidence",0))-float(r.get("accuracy",0))) for r in rows)/max(1,len(rows))
def sharpness(p):
    p=normalize_probabilities(p); return max(p.values())-1/3
