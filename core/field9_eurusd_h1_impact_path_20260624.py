from __future__ import annotations
import math
from core.field9_eurusd_h1_contract_20260624 import HORIZONS
def build(production_action:str, forecasts:dict, uncertainty:float|None, costs:dict, sample_count:int):
    sign=1 if production_action=="BUY" else -1 if production_action=="SELL" else 0
    spread=costs.get("spread_pips")
    if spread is None: spread=0.0
    slip=costs.get("slippage_pips") or 0.0
    rows=[]; prior=0.0
    for h in HORIZONS:
        raw=forecasts.get(h)
        if raw is None: raw=forecasts.get(str(h))
        if raw is None:
            rows.append({"horizon":h,"status":"UNAVAILABLE","reason":"FORECAST_UNAVAILABLE"}); continue
        gross=sign*float(raw); cost=float(spread)+float(slip); net=gross-cost
        u=max(float(uncertainty or abs(gross)*0.75 or 1.0),0.25)*math.sqrt(h/3)
        ppos=max(0.0,min(1.0,0.5+net/(4*u+1e-9)))
        rows.append({"horizon":h,"expected_cumulative_gross_pips":round(gross,4),"expected_cumulative_net_pips":round(net,4),"expected_incremental_pips":round(net-prior,4),"lower_bound":round(net-1.64*u,4),"upper_bound":round(net+1.64*u,4),"probability_positive_impact":round(ppos,4),"probability_negative_impact":round(1-ppos,4),"probability_production_direction_superior":round(ppos,4),"probability_wait_superior":round(max(0,1-ppos)*0.7,4),"probability_opposite_action_superior":round(max(0,1-ppos)*0.3,4),"expected_favorable_excursion":round(max(gross,0)+u*0.5,4),"expected_adverse_excursion":round(max(-gross,0)+u*0.5,4),"expected_transaction_cost":round(cost,4),"expected_spread_cost":round(float(spread),4),"expected_tail_risk_penalty":round(u*0.1,4),"impact_reliability":"CONDITIONAL_ASSOCIATION" if sample_count>=30 else "INSUFFICIENT_DATA","settlement_state":"UNSETTLED","sample_count":sample_count,"fallback_level":"GLOBAL_POOLED" if sample_count<80 else "REGIME_SESSION","status":"AVAILABLE"})
        prior=net
    return rows
def decay(path):
    good=[r for r in path if r.get("status")=="AVAILABLE"]
    if not good:return {"status":"UNAVAILABLE","reason":"IMPACT_PATH_UNAVAILABLE"}
    peak=max(good,key=lambda r:r["expected_cumulative_net_pips"]); peakv=peak["expected_cumulative_net_pips"]
    half=None
    for r in good:
        if r["horizon"]>=peak["horizon"] and r["expected_cumulative_net_pips"]<=peakv/2: half=r["horizon"]-peak["horizon"];break
    return {"status":"AVAILABLE","peak_impact_hour":peak["horizon"],"peak_expected_impact":peakv,"first_positive_impact_hour":next((r["horizon"] for r in good if r["expected_cumulative_net_pips"]>0),None),"last_reliably_positive_hour":max([r["horizon"] for r in good if r["lower_bound"]>0],default=None),"impact_half_life":half,"impact_decay_slope":round((good[-1]["expected_cumulative_net_pips"]-peakv)/max(1,good[-1]["horizon"]-peak["horizon"]),4),"reversal_hour":next((r["horizon"] for r in good if r["expected_cumulative_net_pips"]<0),None),"shadow_effective_holding_horizon":peak["horizon"],"holding_horizon_uncertainty":"HIGH" if len(good)<6 else "MEDIUM"}
