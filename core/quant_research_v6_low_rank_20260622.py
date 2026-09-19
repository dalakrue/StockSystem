"""Bounded robust scaling, low-rank SVD and RPCA-style anomaly evidence."""
from __future__ import annotations
from typing import Any
import numpy as np,pandas as pd

def run_low_rank_quality(frame:pd.DataFrame,retained_variance:float=.9,max_rows:int=1200)->dict[str,Any]:
 work=frame.tail(max_rows).copy(deep=False); x=pd.DataFrame(index=work.index)
 x["return_1"]=pd.to_numeric(work.close,errors="coerce").pct_change();x["range"]=(pd.to_numeric(work.high,errors="coerce")-pd.to_numeric(work.low,errors="coerce"));x["body"]=(pd.to_numeric(work.close,errors="coerce")-pd.to_numeric(work.open,errors="coerce"))
 x=x.replace([np.inf,-np.inf],np.nan).dropna();n=len(x)
 if n<20:return {"method_id":"low_rank_quality","status":"INSUFFICIENT_EVIDENCE","sample_count":n}
 med=x.median();mad=(x-med).abs().median().replace(0,np.nan);z=((x-med)/(1.4826*mad)).fillna(0).clip(-12,12);a=z.to_numpy(float)
 u,s,vt=np.linalg.svd(a,full_matrices=False);energy=s*s;cum=np.cumsum(energy)/max(energy.sum(),1e-12);rank=max(1,int(np.searchsorted(cum,retained_variance)+1));low=(u[:,:rank]*s[:rank])@vt[:rank];res=a-low
 err=float(np.sqrt(np.mean(res*res)));strength=float(np.nanpercentile(np.abs(res),95));anomaly=float(np.mean(np.max(np.abs(res),axis=1)>3.5))
 return {"method_id":"low_rank_quality","status":"AVAILABLE","sample_count":n,"retained_variance_target":retained_variance,"retained_variance_actual":float(cum[rank-1]),"rank":rank,"reconstruction_error":err,"sparse_anomaly_strength_p95":strength,"anomaly_row_fraction":anomaly,"data_quality_status":"WARNING" if anomaly>.1 else "STABLE","raw_rows_unchanged":True,"fallback":"robust median/MAD residuals available","shadow_only":True}
