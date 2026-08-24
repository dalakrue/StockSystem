from __future__ import annotations

def detect(snapshot, regime_entropy=.5):
    uncertainty=float(snapshot.get("uncertainty") or 50)/100
    p=max(0.0,min(1.0,.55*regime_entropy+.45*uncertainty))
    return {"run_length_posterior_summary":{"mode":max(1,int((1-p)*24)),"mean":max(1.0,(1-p)*36)},"changepoint_probability":p,"reset_factor":min(.5,p*.5)}
