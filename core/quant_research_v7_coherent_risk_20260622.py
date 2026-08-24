"""Shadow coherent-risk aggregator over existing verified risk evidence."""
from __future__ import annotations
from typing import Any,Mapping
import numpy as np
from core.quant_research_v7_contract_20260622 import common_method,finite,protected_decision

METHOD_ID="coherent_risk";MIN_SAMPLE=1

def coherent_measure(losses:Any,alpha:float=0.95)->float:
 x=np.asarray(losses,dtype=float);x=x[np.isfinite(x)]
 if len(x)==0:return 0.0
 threshold=np.quantile(x,alpha);tail=x[x>=threshold];return float(np.mean(tail if len(tail) else [threshold]))

def coherence_property_tests()->dict[str,bool]:
 x=np.array([0.,1.,2.,4.,8.]);y=np.array([0.,.5,1.,2.,3.]);rho=lambda z:coherent_measure(z,.8)
 c=1.7;a=2.5
 return {"monotonicity":rho(x+y)>=rho(x)-1e-10,"subadditivity":rho(x+y)<=rho(x)+rho(y)+1e-10,"positive_homogeneity":abs(rho(c*x)-c*rho(x))<1e-9,"translation_invariance":abs(rho(x+a)-(rho(x)+a))<1e-9}

def _value(c:Mapping[str,Any],*paths:str)->float|None:
 for path in paths:
  cur:Any=c
  for part in path.split('.'):
   cur=cur.get(part) if isinstance(cur,Mapping) else None
  v=finite(cur)
  if v is not None:return v
 return None

def run_coherent_risk(canonical:Mapping[str,Any],dcc:Mapping[str,Any]|None,gas:Mapping[str,Any]|None,hsmm:Mapping[str,Any]|None,*,cutoff_time:Any)->dict[str,Any]:
 components={
  "expected_shortfall":_value(canonical,"research_risk.expected_shortfall","quant_research_v6.methods.drift_tail_execution_tft.tail_risk.cvar_95"),
  "exit_risk":_value(canonical,"exit_risk","final_decision.exit_risk"),
  "drawdown":_value(canonical,"drawdown","risk.drawdown"),
  "spread_slippage":sum(v or 0 for v in (_value(canonical,"market.spread","spread"),_value(canonical,"market.slippage","slippage"))),
  "tail_risk":_value(canonical,"research_risk.tail_risk","quant_research_v6.methods.drift_tail_execution_tft.tail_risk.score"),
  "event_intensity":_value(canonical,"research_risk.event_intensity","nlp.event_intensity"),
  "regime_transition_probability":None,
  "forecast_uncertainty":_value(canonical,"final_decision.uncertainty_pct","uncertainty.combined"),
  "cross_market_concentration":None,
 }
 hs=((hsmm or {}).get("output_metrics") or {}) if isinstance(hsmm,Mapping) else {};surv=hs.get("survival_probability") or {};components["regime_transition_probability"]=None if not isinstance(surv,Mapping) or surv.get("H+1") is None else 1-float(surv.get("H+1"))
 dc=((dcc or {}).get("output_metrics") or {}) if isinstance(dcc,Mapping) else {};components["cross_market_concentration"]=finite(dc.get("diversification_loss_score"))
 normalized={}
 for k,v in components.items():
  if v is None:continue
  scale=100.0 if abs(v)>2 else 1.0;normalized[k]=float(np.clip(abs(v)/scale,0,1))
 vals=np.asarray(list(normalized.values()),dtype=float);base=coherent_measure(vals,0.75) if len(vals) else 0.0
 concentration=0.0;duplicates=[]
 names=list(normalized)
 for i,name in enumerate(names):
  for other in names[i+1:]:
   if abs(normalized[name]-normalized[other])<0.03:duplicates.append([name,other])
 concentration=min(0.25,0.03*len(duplicates)+(normalized.get("cross_market_concentration",0)*0.2));diversification=max(0.0,float(np.mean(vals)-base)) if len(vals) else 0.0;score=float(np.clip((base+concentration)*100,0,100));budget=float(np.clip(100-score,0,100))
 tests=coherence_property_tests();coherent=all(tests.values());state="HIGH" if score>=70 else "ELEVATED" if score>=50 else "MODERATE" if score>=30 else "LOW";decision=protected_decision(canonical);shadow_tradeability="WAIT" if state=="HIGH" else decision
 if decision=="WAIT":shadow_tradeability="WAIT"
 output={"component_contributions":{k:round(v*100,3) for k,v in normalized.items()},"missing_components":[k for k,v in components.items() if v is None],"diversification_benefit":round(diversification*100,3),"concentration_penalty":round(concentration*100,3),"duplicated_or_strongly_correlated_inputs":duplicates,"coherence_test_status":"PASS" if coherent else "FAIL","coherence_property_tests":tests,"shadow_coherent_risk_score":round(score,3),"bounded_risk_budget":round(budget,3),"final_shadow_risk_state":state,"protected_decision":decision,"shadow_tradeability":shadow_tradeability,"wait_upgrade_prohibited":True}
 return common_method(METHOD_ID,status=state,sample_count=len(normalized),minimum_sample_required=MIN_SAMPLE,cutoff_time=cutoff_time,output_metrics=output,assumptions=["component losses are comparable after bounded normalization","expected shortfall is used as the coherent core"],limitations=["correlation detection is compact and conservative","may downgrade to WAIT but never upgrades WAIT"])

__all__=["coherent_measure","coherence_property_tests","run_coherent_risk"]
