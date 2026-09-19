"""Bounded SHAP-style explanation fallback without adding dependencies."""
from __future__ import annotations
from typing import Any,Mapping
import numpy as np,pandas as pd

def run_explanation(frame:pd.DataFrame,canonical:Mapping[str,Any],low_rank:Mapping[str,Any])->dict[str,Any]:
 f=frame.tail(300); target=pd.to_numeric(f.close,errors="coerce").pct_change().shift(periods=-1)
 feats=pd.DataFrame({"return_1":pd.to_numeric(f.close,errors="coerce").pct_change(),"range":pd.to_numeric(f.high,errors="coerce")-pd.to_numeric(f.low,errors="coerce"),"body":pd.to_numeric(f.close,errors="coerce")-pd.to_numeric(f.open,errors="coerce")})
 joined=feats.assign(target=target).dropna();n=len(joined)
 if n<25:return {"method_id":"explanation","status":"INSUFFICIENT_EVIDENCE","sample_count":n}
 scores={c:float(joined[c].corr(joined.target) or 0.0) for c in feats.columns}; current=joined.iloc[-1]
 impacts={c:float(scores[c]*current[c]/(joined[c].std() or 1.0)) for c in feats.columns}; pos=sorted(impacts.items(),key=lambda kv:kv[1],reverse=True);neg=sorted(impacts.items(),key=lambda kv:kv[1])
 mid=max(12,n//2); first=joined.iloc[:mid];second=joined.iloc[mid:];stab=[]
 for c in feats.columns:
  a=float(first[c].corr(first.target) or 0);b=float(second[c].corr(second.target) or 0);stab.append(1-min(abs(a-b),1))
 return {"method_id":"explanation","status":"AVAILABLE","sample_count":n,"explanation_route":"bounded native/correlation-permutation fallback","tree_shap_used":False,"top_positive_factors":pos[:3],"top_negative_factors":neg[:3],"explanation_stability":float(np.mean(stab)),"current_row_only":True,"shadow_only":True}
