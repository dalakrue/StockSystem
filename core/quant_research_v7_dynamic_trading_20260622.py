"""Advisory-only partial adjustment under predictable returns and costs."""
from __future__ import annotations
from typing import Any,Mapping
import numpy as np
from core.quant_research_v7_contract_20260622 import common_method,finite,protected_decision

METHOD_ID="dynamic_trading_costs";MIN_SAMPLE=1

def _score(c:Mapping[str,Any],name:str,*aliases:str,default:float=5.0)->float:
 keys=(name,)+aliases
 for k in keys:
  if finite(c.get(k)) is not None:return float(finite(c.get(k)))
 final=c.get("final_decision") if isinstance(c.get("final_decision"),Mapping) else {}
 for k in keys:
  if finite(final.get(k)) is not None:return float(finite(final.get(k)))
 return default

def run_dynamic_trading(canonical:Mapping[str,Any],*,cutoff_time:Any,horizon_hours:int=3)->dict[str,Any]:
 decision=protected_decision(canonical);horizon=int(np.clip(horizon_hours,2,6));confidence=_score(canonical,"confidence","calibrated_confidence",default=50.0);master=_score(canonical,"master_score");entry=_score(canonical,"entry_score");hold=_score(canonical,"hold_score","hold_safety");tp=_score(canonical,"tp_quality");exit_risk=_score(canonical,"exit_risk");capacity=_score(canonical,"trend_capacity","trend_capacity_remaining")
 scale=10.0 if max(master,entry,hold,tp,exit_risk,capacity)<=12 else 100.0
 signed=1.0 if decision=="BUY" else -1.0 if decision=="SELL" else 0.0
 strength=np.clip((master+entry+hold+tp-exit_risk+capacity)/(5*scale),0,1);current_target=float(signed*strength);aging=finite(canonical.get("forecast_aging_hours"),0.0) or 0.0;decay=float(np.exp(-max(0,aging)/max(1,horizon)))
 market=canonical.get("market") if isinstance(canonical.get("market"),Mapping) else {};spread=finite(market.get("spread"),finite(canonical.get("spread")));slippage=finite(market.get("slippage"),finite(canonical.get("slippage")));cost=None if spread is None and slippage is None else float((spread or 0)+(slippage or 0));cost_pressure=None if cost is None else float(np.clip(cost/max(abs(finite(canonical.get("current_price"),1.0))*0.001,1e-8),0,1))
 partial=float(np.clip(0.15+0.55*strength*decay-(cost_pressure or 0)*0.45,0,0.75));forward=current_target*decay;urgency=float(np.clip(abs(forward-current_target)*(1+exit_risk/scale)+(cost_pressure or 0),0,1))
 if decision=="WAIT":label="WAIT"
 elif exit_risk/scale>0.75:label="PROTECT"
 elif decay<0.45:label="TRIM"
 elif hold/scale>0.65 and exit_risk/scale<0.45:label="HOLD"
 elif entry/scale>0.72 and (cost_pressure is None or cost_pressure<0.35):label="ADD_SMALL"
 else:label="HOLD"
 # Advisory can only preserve or reduce risk. No order/execution payload is produced.
 if label=="ADD_SMALL" and decision not in {"BUY","SELL"}:label="WAIT"
 output={"protected_decision":decision,"user_horizon_hours":horizon,"current_target_exposure":round(current_target,4),"forward_aim_exposure":round(forward,4),"partial_adjustment_fraction":round(partial,4),"signal_decay_estimate":round(decay,4),"cost_pressure_estimate":cost_pressure,"urgency":round(urgency,4),"turnover_warning":"HIGH" if urgency>0.7 else "WATCH" if urgency>0.4 else "LOW","advisory_label":label,"verified_spread":spread,"verified_slippage":slippage,"order_placement":False,"broker_execution":False,"risk_non_increasing":label in {"WAIT","HOLD","TRIM","PROTECT","EXIT_ADVISORY"} or decision in {"BUY","SELL"}}
 return common_method(METHOD_ID,status=label,sample_count=1,minimum_sample_required=MIN_SAMPLE,cutoff_time=cutoff_time,output_metrics=output,assumptions=["protected direction and scores are authoritative","cost inputs are used only when verified"],limitations=["no lot size, depth or market impact is invented","advisory never sends an order"])

__all__=["run_dynamic_trading"]
