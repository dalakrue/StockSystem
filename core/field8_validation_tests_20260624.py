"""Dependence-aware shadow validation helpers."""
from __future__ import annotations
import math
import numpy as np

def mcs_status(loss_matrix,min_samples=30,comparable=True):
    a=np.asarray(loss_matrix,dtype=float)
    if not comparable:return {'status':'NOT_COMPARABLE','p_value':math.nan}
    if a.ndim!=2 or a.shape[0]<min_samples or a.shape[1]<2 or not np.all(np.isfinite(a)):return {'status':'INSUFFICIENT_EVIDENCE','p_value':math.nan}
    means=a.mean(axis=0); cutoff=float(np.median(means)); return {'status_by_model':['MCS_INCLUDED' if m<=cutoff else 'MCS_EXCLUDED' for m in means],'status':'MCS_INCLUDED','p_value':math.nan}

def diebold_mariano(loss_a,loss_b,horizon=1):
    a=np.asarray(loss_a,dtype=float); b=np.asarray(loss_b,dtype=float); mask=np.isfinite(a)&np.isfinite(b); d=a[mask]-b[mask]; n=len(d)
    if n<max(8,2*horizon+2):return {'dm_statistic':math.nan,'p_value':math.nan,'sample_count':n,'dependence_warning':'INSUFFICIENT_EVIDENCE','statistically_better_than_benchmark':False}
    q=max(int(horizon)-1,0); centered=d-d.mean(); gamma0=float(centered@centered/n); lrv=gamma0
    for lag in range(1,q+1):
        gamma=float(centered[lag:]@centered[:-lag]/n); lrv+=2*(1-lag/(q+1))*gamma
    stat=float(d.mean()/math.sqrt(max(lrv/n,1e-12))); p=float(math.erfc(abs(stat)/math.sqrt(2)))
    return {'loss_differential':float(d.mean()),'dm_statistic':stat,'p_value':p,'sample_count':n,'dependence_warning':'HAC_OVERLAP_CORRECTED' if q else 'NONE','statistically_better_than_benchmark':bool(stat<0 and p<.05)}

def reality_check(variant_losses,min_samples=30):
    names=list(variant_losses); arrays=[np.asarray(variant_losses[n],dtype=float) for n in names]; n=min((len(x) for x in arrays),default=0)
    return {'total_tested_variants':len(names),'effective_trials':len(names),'reality_check_p_value':math.nan,'data_snooping_pass':False,'promotion_eligibility':False,'status':'INSUFFICIENT_EVIDENCE' if n<min_samples else 'PENDING_REVALIDATION'}
