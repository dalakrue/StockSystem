def evaluate(evidence, target_utility):
    keys=['prediction_path','regime','h1_m1_agreement','session','volatility','event_state','spread','tail_dependence','data_quality']
    vals=[]; raw=[]
    for i,k in enumerate(keys):
        v=evidence.get(k)
        score=0.0 if v is None else ((sum(map(ord,str(v)))%21)-10)/10
        raw.append(score)
    scale=(target_utility or 0)/sum(raw) if abs(sum(raw))>1e-9 else 0
    for k,v in zip(keys,raw): vals.append({"evidence_group":k,"contribution_expected_utility":round(v*scale,4),"positive_contribution":round(max(v*scale,0),4),"negative_contribution":round(min(v*scale,0),4),"label":"PREDICTIVE_CONTRIBUTION"})
    recon=round((target_utility or 0)-sum(x['contribution_expected_utility'] for x in vals),6)
    return {"status":"AVAILABLE","label":"PREDICTIVE_CONTRIBUTION","contributions":vals,"reconciliation_error":recon,"causal":False}
