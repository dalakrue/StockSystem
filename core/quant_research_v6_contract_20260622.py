"""Shared contracts for the shadow-only Quant V6 layer."""
from __future__ import annotations
from typing import Any, Mapping
import hashlib, json, math
import numpy as np
import pandas as pd
IMPLEMENTATION_VERSION="quant-research-v6-20260622-v1"
UNAVAILABLE="UNAVAILABLE"

def finite(value:Any,default=None):
 try:
  x=float(value); return x if math.isfinite(x) else default
 except Exception:return default

def json_safe(value:Any)->Any:
 if isinstance(value,Mapping):return {str(k):json_safe(v) for k,v in value.items()}
 if isinstance(value,(list,tuple,set)):return [json_safe(v) for v in value]
 if isinstance(value,(pd.Timestamp,)):return value.isoformat()
 if isinstance(value,(np.integer,)):return int(value)
 if isinstance(value,(np.floating,)):return finite(value)
 if isinstance(value,np.ndarray):return [json_safe(v) for v in value.tolist()]
 if pd.isna(value) if not isinstance(value,(str,bytes,dict,list,tuple,set)) else False:return None
 return value

def stable_hash(value:Any)->str:
 return hashlib.sha256(json.dumps(json_safe(value),sort_keys=True,default=str,separators=(",",":")).encode()).hexdigest()

def _time_col(frame:pd.DataFrame):
 for c in ("event_time_utc","time","Time","Datetime","DateTime","Timestamp","date"):
  if c in frame.columns:return c
 return None

def normalize_completed_ohlc(frame:pd.DataFrame,*,cutoff_utc=None,max_rows:int=6000):
 if not isinstance(frame,pd.DataFrame) or frame.empty:raise ValueError("completed OHLC is unavailable")
 t=_time_col(frame)
 if t is None and not isinstance(frame.index,pd.DatetimeIndex):raise ValueError("OHLC timestamp column unavailable")
 cols={str(c).lower():c for c in frame.columns}
 required=[cols.get(x) for x in ("open","high","low","close")]
 if any(c is None for c in required):raise ValueError("OHLC columns unavailable")
 out=pd.DataFrame({"event_time_utc":pd.to_datetime(frame[t] if t else frame.index,errors="coerce",utc=True)})
 for name,c in zip(("open","high","low","close"),required):out[name]=pd.to_numeric(frame[c],errors="coerce")
 v=cols.get("volume") or cols.get("tick_volume")
 if v is not None:out["volume"]=pd.to_numeric(frame[v],errors="coerce")
 out=out.replace([np.inf,-np.inf],np.nan).dropna(subset=["event_time_utc","open","high","low","close"])
 cutoff=pd.to_datetime(cutoff_utc,errors="coerce",utc=True)
 if pd.notna(cutoff):out=out.loc[out.event_time_utc<=cutoff]
 out=out.sort_values("event_time_utc").drop_duplicates("event_time_utc",keep="last").tail(max_rows).reset_index(drop=True)
 if out.empty:raise ValueError("no completed OHLC rows remain")
 meta={"rows":len(out),"first":out.event_time_utc.iloc[0].isoformat(),"last":out.event_time_utc.iloc[-1].isoformat(),"duplicate_count":int(frame.shape[0]-out.shape[0])}
 return out,meta

def normalize_settled(frame):
 if not isinstance(frame,pd.DataFrame) or frame.empty:return pd.DataFrame()
 out=frame.copy(deep=False)
 for c in out.columns:
  if any(k in str(c).lower() for k in ("error","return","correct","miss")):out[c]=pd.to_numeric(out[c],errors="coerce")
 return out.replace([np.inf,-np.inf],np.nan).tail(12000)

def identity_from_canonical(canonical:Mapping[str,Any],meta:Mapping[str,Any]):
 calc=str(canonical.get("canonical_calculation_id") or canonical.get("run_id") or "")
 gen=str(canonical.get("calculation_generation") or canonical.get("generation") or calc)
 return {"calculation_id":calc,"source_generation_id":gen,"latest_completed_h1_utc":str(canonical.get("latest_completed_h1_utc") or canonical.get("latest_completed_candle_time") or meta.get("last") or ""),"symbol":str(canonical.get("symbol") or "EURUSD"),"timeframe":str(canonical.get("timeframe") or "H1"),"logic_version":IMPLEMENTATION_VERSION}
