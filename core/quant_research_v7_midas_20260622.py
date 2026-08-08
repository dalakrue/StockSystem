"""Leakage-safe compact MIDAS-style multi-frequency summaries."""
from __future__ import annotations
from typing import Any
import time
import numpy as np
import pandas as pd
from core.quant_research_v7_contract_20260622 import common_method

METHOD_ID="midas_multi_frequency";MIN_SAMPLE=60

def beta_weights(length:int,a:float=1.5,b:float=3.0)->np.ndarray:
 if length<=0:return np.asarray([])
 x=(np.arange(length)+1)/(length+1);w=np.power(x,a-1)*np.power(1-x,b-1);return w/max(w.sum(),1e-12)

def run_midas(h1:pd.DataFrame,m1:pd.DataFrame,*,cutoff_time:Any)->dict[str,Any]:
 started=time.perf_counter()
 if not isinstance(m1,pd.DataFrame) or m1.empty:return common_method(METHOD_ID,status="UNAVAILABLE",sample_count=0,minimum_sample_required=MIN_SAMPLE,cutoff_time=cutoff_time,output_metrics={"reason":"completed EURUSD M1 data unavailable"},assumptions=["M1 timestamps align to canonical cutoff"],limitations=["does not invent M1 data"])
 cutoff=pd.to_datetime(cutoff_time,errors="coerce",utc=True);m=m1.copy(deep=False);m["event_time_utc"]=pd.to_datetime(m["event_time_utc"],errors="coerce",utc=True);m=m.loc[m.event_time_utc.notna()]
 if pd.notna(cutoff):m=m.loc[m.event_time_utc<=cutoff]
 lower={str(c).lower():c for c in m.columns}
 if "close" not in lower:return common_method(METHOD_ID,status="UNAVAILABLE",sample_count=len(m),minimum_sample_required=MIN_SAMPLE,cutoff_time=cutoff_time,output_metrics={"reason":"M1 close unavailable"},assumptions=["completed M1 rows only"],limitations=["does not invent M1 prices"] )
 close=pd.to_numeric(m[lower["close"]],errors="coerce")
 if "high" in lower and "low" in lower:
  high=pd.to_numeric(m[lower["high"]],errors="coerce");low=pd.to_numeric(m[lower["low"]],errors="coerce");range_fraction=(high-low)/close.replace(0,np.nan)
 elif "candle_range" in lower:
  range_fraction=pd.to_numeric(m[lower["candle_range"]],errors="coerce")/close.replace(0,np.nan)
 else:
  range_fraction=close.pct_change().abs()
 ret=close.pct_change();window=min(360,len(m));retw=ret.iloc[-window:].dropna()
 if len(retw)<MIN_SAMPLE:return common_method(METHOD_ID,status="INSUFFICIENT_EVIDENCE",sample_count=len(retw),minimum_sample_required=MIN_SAMPLE,cutoff_time=cutoff_time,output_metrics={"latest_m1_time":m.event_time_utc.max().isoformat() if not m.empty else None},assumptions=["completed M1 rows only"],limitations=["minimum support not met"])
 w=beta_weights(len(retw));weighted=float(np.dot(w,retw.to_numpy()));direction=float(np.mean(np.sign(retw)));rng=range_fraction.iloc[-window:].dropna();vol=float(np.sqrt(np.sum(w[-len(retw):]*np.square(retw.to_numpy()))))
 vol_col=lower.get("volume") or lower.get("tick_volume");volume_pressure=None
 if vol_col is not None:
  vv=pd.to_numeric(m[vol_col],errors="coerce").iloc[-window:].dropna();volume_pressure=float((vv.iloc[-60:].mean()/max(vv.mean(),1e-12))-1) if len(vv)>=60 else None
 h4_context=None;d1_context=None
 if isinstance(h1,pd.DataFrame) and not h1.empty:
  hc=pd.to_numeric(h1[next(c for c in h1.columns if str(c).lower()=="close")],errors="coerce")
  h4_context=float(hc.iloc[-1]/hc.iloc[-5]-1) if len(hc)>=5 else None;d1_context=float(hc.pct_change().iloc[-24:].std(ddof=0)) if len(hc)>=25 else None
 output={"latest_m1_time":m.event_time_utc.max().isoformat(),"m1_return_pressure":weighted,"m1_directional_consistency":direction,"m1_range_expansion":float(rng.iloc[-60:].mean()/max(rng.mean(),1e-12)-1) if len(rng)>=60 else None,"m1_realized_volatility":vol,"m1_volume_pressure":volume_pressure,"h4_trend_context":h4_context,"d1_volatility_context":d1_context,"weights":w[-60:].round(8).tolist(),"coefficients":{"beta_a":1.5,"beta_b":3.0},"baseline_comparison":{"simple_mean":float(retw.mean()),"simple_max":float(retw.max()),"simple_min":float(retw.min()),"midas_minus_mean":float(weighted-retw.mean())},"raw_m1_stored_in_canonical":False,"runtime_ms":round((time.perf_counter()-started)*1000,3)}
 return common_method(METHOD_ID,status="AVAILABLE",sample_count=len(retw),minimum_sample_required=MIN_SAMPLE,cutoff_time=cutoff_time,output_metrics=output,assumptions=["all M1 rows are completed before the H1 cutoff","Beta-lag summary is a compact approximation"],limitations=["raw M1 frames are excluded from canonical JSON"])

__all__=["beta_weights","run_midas"]
