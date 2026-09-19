"""Settled-only drift, CVaR, execution feasibility and TFT-lite gates."""
from __future__ import annotations
from typing import Any,Mapping
import numpy as np,pandas as pd

def _num(m,*keys):
 for k in keys:
  try:
   v=m.get(k); x=float(v)
   if np.isfinite(x):return x
  except Exception:pass
 return None

def _series(f,tokens):
 for c in f.columns:
  if any(t in str(c).lower() for t in tokens):
   s=pd.to_numeric(f[c],errors="coerce").dropna()
   if not s.empty:return s
 return pd.Series(dtype=float)

def run_drift_tail(settled:pd.DataFrame,canonical:Mapping[str,Any],frame:pd.DataFrame)->dict[str,Any]:
 err=_series(settled,("absolute_error","abs_error","error_pct","forecast_error")) if isinstance(settled,pd.DataFrame) else pd.Series(dtype=float); n=len(err)
 drift={"status":"INSUFFICIENT_EVIDENCE","sample_count":n,"overall_state":"UNAVAILABLE"}
 if n>=30:
  cut=max(10,n//3);old=err.iloc[:-cut];new=err.iloc[-cut:];ratio=float(new.mean()/max(old.mean(),1e-12));state="DRIFT" if ratio>1.5 else "WARNING" if ratio>1.2 else "STABLE";drift={"status":"AVAILABLE","sample_count":n,"overall_state":state,"recent_to_baseline_error_ratio":ratio,"settled_only":True}
 tail={"status":"INSUFFICIENT_EVIDENCE","sample_count":n,"minimum_sample_gate":30}
 if n>=30:
  losses=err.abs().to_numpy(float);vals={}
  for q in (.9,.95,.99):
   threshold=float(np.quantile(losses,q));vals[str(int(q*100))]={"var":threshold,"cvar":float(losses[losses>=threshold].mean()),"tail_count":int((losses>=threshold).sum())}
  tail={"status":"AVAILABLE","sample_count":n,"levels":vals,"settled_only":True}
 ex=canonical.get("execution") if isinstance(canonical.get("execution"),Mapping) else {}; fc=canonical.get("forecasts") if isinstance(canonical.get("forecasts"),Mapping) else {}
 spread=_num(ex,"spread_pips","spread_points","spread");slip=_num(ex,"estimated_slippage","slippage");move=_num(ex,"expected_move") or _num(fc,"expected_move")
 if None in (spread,slip,move) or not move:
  feas={"status":"UNAVAILABLE","reason":"spread, slippage or expected move is unavailable; no value was invented","spread":spread,"slippage":slip,"expected_move":move}
 else:
  ratio=(spread+slip)/abs(move); label="GOOD" if ratio<=.25 else "MARGINAL" if ratio<=.5 else "AVOID";feas={"status":label,"cost_to_move_ratio":ratio,"spread":spread,"slippage":slip,"expected_move":move}
 ret=pd.to_numeric(frame.close,errors="coerce").pct_change();weights={}
 for h in (1,3,6):
  vol=float(ret.rolling(max(6,h*4)).std().iloc[-1] or 0);mom=float(ret.rolling(max(3,h)).mean().iloc[-1] or 0);raw=np.array([abs(mom),vol,1e-6]);raw=raw/raw.sum();weights[f"H+{h}"]={"momentum":float(raw[0]),"volatility":float(raw[1]),"baseline":float(raw[2])}
 return {"method_id":"drift_tail_execution_tft","status":"AVAILABLE","sample_count":n,"drift":drift,"tail_risk":tail,"execution_feasibility":feas,"tft_lite":{"status":"SHADOW","horizon_specific_feature_weights":weights,"replaces_production_forecast":False},"shadow_only":True}
