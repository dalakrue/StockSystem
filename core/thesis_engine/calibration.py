from __future__ import annotations
from .proper_scoring import normalize_probabilities

def calibrated_from_action(action: float, confidence: float = .5):
    c=max(0.0,min(1.0,float(confidence or 0.0))); a=max(-1.0,min(1.0,float(action)))
    directional=.34+.60*c*abs(a); hold=max(.02,1-directional)
    if a>0: p={"BUY":directional,"SELL":max(.01,(1-directional-hold)/2),"HOLD":hold}
    elif a<0: p={"SELL":directional,"BUY":max(.01,(1-directional-hold)/2),"HOLD":hold}
    else: p={"HOLD":.50+.45*c,"BUY":.25-.20*c,"SELL":.25-.20*c}
    return normalize_probabilities(p)
