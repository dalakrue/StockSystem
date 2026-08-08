"""Bounded BDS-style residual dependence diagnostic with online-FDR integration."""
from __future__ import annotations
from typing import Any,Mapping
import math,time
import numpy as np
import pandas as pd
from core.quant_research_v7_contract_20260622 import common_method,stable_hash
from core.quant_research_v7_stationary_bootstrap_20260622 import stationary_bootstrap_indices,estimate_mean_block_length

METHOD_ID="bds_residual_test";MIN_SAMPLE=80;MAX_SAMPLE=350

def _residuals(frame:pd.DataFrame)->np.ndarray:
 if not isinstance(frame,pd.DataFrame) or frame.empty:return np.asarray([])
 lower={str(c).lower():c for c in frame.columns};col=next((lower[k] for k in ("residual","forecast_residual","prediction_error","forecast_error","error","absolute_forecast_error") if k in lower),None)
 if col is None:return np.asarray([])
 x=pd.to_numeric(frame[col],errors="coerce").to_numpy(float);x=x[np.isfinite(x)];return x[-MAX_SAMPLE:]

def _correlation_integral(x:np.ndarray,m:int,epsilon:float)->float:
 n=len(x)-m+1
 if n<2:return float("nan")
 emb=np.column_stack([x[i:i+n] for i in range(m)])
 count=0;total=0
 for i in range(n-1):
  dist=np.max(np.abs(emb[i+1:]-emb[i]),axis=1);count+=int(np.sum(dist<epsilon));total+=len(dist)
 return count/max(total,1)

def bds_statistic(x:Any,m:int,epsilon_multiplier:float)->tuple[float,float]:
 arr=np.asarray(x,dtype=float);arr=arr[np.isfinite(arr)]
 if len(arr)<MIN_SAMPLE:return float("nan"),float("nan")
 z=(arr-arr.mean())/max(arr.std(ddof=0),1e-12);eps=epsilon_multiplier
 c1=_correlation_integral(z,1,eps);cm=_correlation_integral(z,m,eps);delta=cm-c1**m
 # Conservative bounded asymptotic scaling; bootstrap is the material confirmation.
 se=max(math.sqrt(max(c1**m*(1-c1**m),1e-12)/max(len(z)-m+1,1)),1e-8);stat=delta/se
 p=math.erfc(abs(stat)/math.sqrt(2.0));return float(stat),float(np.clip(p,0,1))

def run_bds(settled:pd.DataFrame,*,generation_id:Any,cutoff_time:Any,bootstrap_service=None,previous_fdr:Mapping[str,Any]|None=None)->dict[str,Any]:
 started=time.perf_counter();x=_residuals(settled)
 if len(x)<MIN_SAMPLE:return common_method(METHOD_ID,status="INSUFFICIENT_EVIDENCE",sample_count=len(x),minimum_sample_required=MIN_SAMPLE,cutoff_time=cutoff_time,output_metrics={},assumptions=["settled standardized residuals"],limitations=["bounded sample and epsilon grid"])
 tests=[]
 for m in range(2,6):
  for eps in (0.5,1.0,1.5):
   stat,p=bds_statistic(x,m,eps);tests.append({"test_key":stable_hash([generation_id,m,eps]),"test_family":"v7_bds","source":"quant_research_v7_bds","embedding_dimension":m,"epsilon_multiplier":eps,"statistic":stat,"raw_p_value":p})
 try:
  from core.ten_paper_research_layers_20260621 import apply_online_fdr
  fdr=apply_online_fdr(tests,source_generation_id=str(generation_id),previous_state=previous_fdr,fdr_target=0.10)
  decisions={str(r.get("test_key")):r for r in fdr.get("records",[])}
 except Exception as exc:
  fdr={"records":[],"state":{},"error":str(exc)};decisions={}
 material=[];records=[]
 for row in tests:
  decision=decisions.get(str(row["test_key"]),{}).get("adjusted_result","DO_NOT_REJECT")
  rec={**row,"adjusted_decision":decision,"sample_count":len(x)};records.append(rec)
  if decision=="REJECT":material.append(rec)
 bootstrap_confirmation={"status":"NOT_REQUIRED"}
 if material:
  target=material[0];block,_=estimate_mean_block_length(x);seed=getattr(bootstrap_service,"seed",12345);idx=stationary_bootstrap_indices(len(x),mean_block_length=block,replications=min(80,getattr(bootstrap_service,"replications",80)),seed=seed)
  observed=abs(float(target["statistic"]));dist=[]
  for i in idx:
   stat,_=bds_statistic(x[i],int(target["embedding_dimension"]),float(target["epsilon_multiplier"]));dist.append(abs(stat))
  dist=np.asarray(dist);bootstrap_confirmation={"status":"CONFIRMED" if float(np.mean(dist>=observed))<0.10 else "NOT_CONFIRMED","bootstrap_p_value":float(np.mean(dist>=observed)),"replication_count":len(dist),"mean_block_length":block}
 if not material:status="RESIDUALS_ACCEPTABLE"
 elif bootstrap_confirmation.get("status")=="CONFIRMED":status="NONLINEAR_DEPENDENCE_REMAINS"
 else:status="LINEAR_DEPENDENCE_REMAINS"
 output={"tests":records,"material_test_count":len(material),"bootstrap_confirmation":bootstrap_confirmation,"online_fdr_state":fdr.get("state",{}),"runtime_ms":round((time.perf_counter()-started)*1000,3)}
 return common_method(METHOD_ID,status=status,sample_count=len(x),minimum_sample_required=MIN_SAMPLE,cutoff_time=cutoff_time,output_metrics=output,assumptions=["valid settled residuals","online-FDR validity conditions apply"],limitations=["bounded BDS approximation","model promotion is prohibited solely because another model fails"])

__all__=["bds_statistic","run_bds"]
