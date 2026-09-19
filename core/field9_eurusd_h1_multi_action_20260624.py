from __future__ import annotations
from core.field9_eurusd_h1_contract_20260624 import ACTIONS
def evaluate(production_action, path, support_counts=None):
    h3=next((r for r in path if r.get('horizon')==3 and r.get('status')=='AVAILABLE'),None)
    if not h3:return {"status":"INSUFFICIENT_DATA","reason":"H3_IMPACT_UNAVAILABLE","actions":[]}
    base=float(h3['expected_cumulative_gross_pips']); unc=max(0.25,(h3['upper_bound']-h3['lower_bound'])/3.28)
    vals={"BUY":base if production_action=="BUY" else -base,"SELL":base if production_action=="SELL" else -base,"WAIT":0.0,"HOLD":base*0.75,"REDUCE":base*0.4,"EXIT":-0.25}
    rows=[]; best=max(vals,key=vals.get)
    for a in ACTIONS:
        support=int((support_counts or {}).get(a,0)); status="SHADOW" if support>=10 else "INSUFFICIENT_ACTION_OVERLAP"
        gross=vals[a]; cost=0 if a=="WAIT" else h3.get('expected_transaction_cost',0)
        net=gross-cost; regret=vals[best]-gross
        rows.append({"action":a,"expected_gross_pips":round(gross,4),"expected_net_pips":round(net,4),"mfe":round(max(gross,0)+unc/2,4),"mae":round(max(-gross,0)+unc/2,4),"tp_probability":round(max(0,min(1,.5+gross/(4*unc))),4),"utility":round(net-0.25*(max(-gross,0)+unc/2),4),"uncertainty":round(unc,4),"regret":round(regret,4),"support_status":"BASELINE" if a=="WAIT" else status,"sample_count":support})
    return {"status":"AVAILABLE","shadow_preferred_action":best,"production_action_regret":round(vals[best]-vals.get(production_action,0),4),"rule_path":f"H3 net impact and bounded risk rank selected {best}","actions":rows}
