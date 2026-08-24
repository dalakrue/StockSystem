"""Empirical signal survival/churn evidence with censoring."""
from __future__ import annotations
from typing import Any,Mapping
import pandas as pd, numpy as np

def _col(f,*names):
 low={str(c).lower():c for c in f.columns}
 return next((low[n.lower()] for n in names if n.lower() in low),None)

def run_signal_survival(history:pd.DataFrame|None,canonical:Mapping[str,Any],min_samples:int=20)->dict[str,Any]:
 if not isinstance(history,pd.DataFrame) or history.empty:return {"method_id":"signal_survival","status":"UNAVAILABLE","reason":"no persisted signal history","sample_count":0}
 c=_col(history,"Decision","decision","Direction","direction","Regime","regime","Priority","priority")
 if c is None:return {"method_id":"signal_survival","status":"UNAVAILABLE","reason":"no signal/regime/priority column","sample_count":0}
 seq=history[c].astype(str).replace({"nan":"UNAVAILABLE"}).tolist(); durations=[]; censored=0
 if not seq:return {"method_id":"signal_survival","status":"UNAVAILABLE","sample_count":0}
 run=1
 for i in range(1,len(seq)):
  if seq[i]==seq[i-1]:run+=1
  else:durations.append(run);run=1
 censored=1; durations_all=durations+[run]; n=len(durations_all)
 if n<min_samples:return {"method_id":"signal_survival","status":"INSUFFICIENT_EVIDENCE","sample_count":n,"minimum_sample_gate":min_samples,"censored_count":censored,"event_count":len(durations)}
 probs={f"H+{h}":float(np.mean(np.asarray(durations_all)>=h)) for h in (1,2,3,6)}
 return {"method_id":"signal_survival","status":"AVAILABLE","sample_count":n,"event_count":len(durations),"censored_count":censored,"survival_probability":probs,"churn_risk":{k:1-v for k,v in probs.items()},"method":"empirical Kaplan-Meier-style fallback","profit_prediction":False,"shadow_only":True}
