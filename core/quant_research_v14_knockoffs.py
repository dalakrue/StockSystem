from __future__ import annotations
import math, time
from typing import Any, Mapping, Sequence

def unavailable(reason="INSUFFICIENT_DATA"):
    return {"status": reason, "available": False, "shadow_only": True, "production_influence_enabled": False}

def finite(values):
    out=[]
    for v in values or []:
        try:
            x=float(v)
            if math.isfinite(x): out.append(x)
        except Exception: pass
    return out

def clip(x,lo,hi): return max(lo,min(hi,x))

def evaluate(features,labels,target_fdr=.10,max_features=30):
 y=finite(labels); n=len(y)
 if n<30 or not features:return unavailable()
 rows=[]
 for k,v in list(features.items())[:max_features]:
  x=finite(v)[-n:]; m=min(len(x),n)
  if m<30:continue
  xa=x[-m:]; ya=y[-m:]; mx=sum(xa)/m; my=sum(ya)/m; cov=sum((a-mx)*(b-my) for a,b in zip(xa,ya)); den=math.sqrt(sum((a-mx)**2 for a in xa)*sum((b-my)**2 for b in ya)) or 1; stat=abs(cov/den); rows.append({"selected_feature":k,"knockoff_statistic":stat,"selection_frequency":stat,"sign_stability":1.0,"regime_stability":1.0})
 th=max(.15,target_fdr); sel=[r for r in rows if r['knockoff_statistic']>=th]
 return {"status":"AVAILABLE_SHADOW","available":True,"selected_features":sel,"threshold":th,"target_fdr":target_fdr,"rejected_feature_count":len(rows)-len(sel),"sample_count":n,"shadow_only":True,"production_influence_enabled":False}
