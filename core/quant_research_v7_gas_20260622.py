"""Lightweight Student-t GAS-style settled residual scale evidence."""
from __future__ import annotations
from typing import Any, Mapping
import time
import numpy as np
import pandas as pd
from core.quant_research_v7_contract_20260622 import common_method, finite

METHOD_ID="generalized_autoregressive_score"; MIN_SAMPLE=40

def _residual_series(settled:pd.DataFrame)->np.ndarray:
 if not isinstance(settled,pd.DataFrame) or settled.empty:return np.asarray([],dtype=float)
 lower={str(c).lower():c for c in settled.columns}
 col=next((lower[k] for k in ("residual","forecast_residual","prediction_error","forecast_error","error","absolute_forecast_error") if k in lower),None)
 if col is None:return np.asarray([],dtype=float)
 x=pd.to_numeric(settled[col],errors="coerce").to_numpy(dtype=float);return x[np.isfinite(x)]

def gas_scale_path(residuals:Any,*,omega:float=0.02,alpha:float=0.08,beta:float=0.90,nu:float=8.0)->tuple[np.ndarray,np.ndarray]:
 x=np.asarray(residuals,dtype=float);x=x[np.isfinite(x)]
 if len(x)==0:return np.asarray([]),np.asarray([])
 base=max(float(np.nanmedian(np.abs(x)))*1.4826, float(np.nanstd(x)),1e-8)
 log_scale=np.log(base);scales=[];scores=[]
 for e in x:
  scale=max(np.exp(log_scale),1e-10);u=e/scale
  score=((nu+1.0)*(u*u)/(nu-2.0+u*u)-1.0)/2.0
  score=float(np.clip(score,-4.0,4.0));log_scale=omega+beta*log_scale+alpha*score
  scales.append(max(np.exp(log_scale),1e-10));scores.append(score)
 return np.asarray(scales),np.asarray(scores)

def run_gas(settled:pd.DataFrame,canonical:Mapping[str,Any],*,cutoff_time:Any)->dict[str,Any]:
 started=time.perf_counter();x=_residual_series(settled)
 if len(x)<MIN_SAMPLE:return common_method(METHOD_ID,status="INSUFFICIENT_EVIDENCE",sample_count=len(x),minimum_sample_required=MIN_SAMPLE,cutoff_time=cutoff_time,output_metrics={},assumptions=["settled residuals are ordered"],limitations=["fixed Student-t shape until support is sufficient"])
 scales,scores=gas_scale_path(x);current=float(scales[-1]);previous=float(scales[-2]);shock=float(scores[-1]);mult=float(np.clip(current/max(np.median(scales[-40:]),1e-12),0.75,2.5))
 atr=((canonical.get("market") or {}).get("atr") if isinstance(canonical.get("market"),Mapping) else None) or canonical.get("atr")
 vol=((canonical.get("market") or {}).get("volatility") if isinstance(canonical.get("market"),Mapping) else None) or canonical.get("volatility")
 tail="HIGH" if mult>=1.5 or shock>=1.5 else "ELEVATED" if mult>=1.15 or shock>=0.8 else "NORMAL"
 output={"current_error_scale":finite(current),"scale_change":finite(current-previous),"score_shock":finite(shock),"persistence":0.90,"tail_warning_state":tail,"suggested_uncertainty_multiplier":round(mult,4),"comparison":{"existing_atr":finite(atr),"existing_volatility":finite(vol),"garch":((canonical.get("quant_research_v4") or {}).get("methods") or {}).get("realized_garch") if isinstance(canonical.get("quant_research_v4"),Mapping) else None,"rough_volatility":((canonical.get("quant_research_v4") or {}).get("methods") or {}).get("rough_volatility") if isinstance(canonical.get("quant_research_v4"),Mapping) else None},"runtime_ms":round((time.perf_counter()-started)*1000,3)}
 return common_method(METHOD_ID,status="AVAILABLE",sample_count=len(x),minimum_sample_required=MIN_SAMPLE,cutoff_time=cutoff_time,output_metrics=output,assumptions=["settled residual scale evolves smoothly","Student-t degrees of freedom fixed at 8"],limitations=["uncertainty evidence only; forecast points remain protected"])

__all__=["gas_scale_path","run_gas"]
