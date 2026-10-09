from __future__ import annotations
import math

def infer_regime(snapshot):
    name=str(snapshot.get("regime") or "UNKNOWN"); rel=float(snapshot.get("regime_reliability") or snapshot.get("reliability_score") or 50)/100
    rel=max(.34,min(.98,rel)); others=(1-rel)/2
    probs={name:rel,"BULL":others,"BEAR":others}
    probs={k:v for k,v in probs.items() if v>0}; s=sum(probs.values()); probs={k:v/s for k,v in probs.items()}
    entropy=-sum(v*math.log(v+1e-12) for v in probs.values())/max(1e-12,math.log(max(2,len(probs))))
    return {"state_probabilities":probs,"transition_probabilities":{"stay":rel,"change":1-rel},"expected_duration":1/max(1e-6,1-rel),"regime_entropy":entropy}
