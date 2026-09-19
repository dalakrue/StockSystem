"""Bounded, causal, shadow-only quant research primitives for Lunch Fields 2/3/6/8.
All updates require matured outcomes. Nothing in this module mutates production decisions.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
import math, hashlib, json
import numpy as np
from core.field8_probabilistic_scores_20260624 import crps, interval_score
HORIZONS=(1,3,6)

def energy_score(observation:Sequence[float], samples:Sequence[Sequence[float]], beta:float=1.0)->float:
    y=np.asarray(observation,float); x=np.asarray(samples,float)
    if x.ndim!=2 or y.ndim!=1 or x.shape[1]!=y.size or x.shape[0]==0:return math.nan
    x=x[np.all(np.isfinite(x),axis=1)]
    if not np.all(np.isfinite(y)) or len(x)==0:return math.nan
    a=np.mean(np.linalg.norm(x-y,axis=1)**beta)
    b=.5*np.mean(np.linalg.norm(x[:,None,:]-x[None,:,:],axis=2)**beta)
    return float(a-b)

def variogram_score(observation:Sequence[float], samples:Sequence[Sequence[float]], p:float=.5, weights=None)->float:
    y=np.asarray(observation,float); x=np.asarray(samples,float)
    if x.ndim!=2 or y.ndim!=1 or x.shape[1]!=y.size or x.shape[0]==0:return math.nan
    x=x[np.all(np.isfinite(x),axis=1)]
    if len(x)==0 or not np.all(np.isfinite(y)):return math.nan
    w=np.ones((y.size,y.size)) if weights is None else np.asarray(weights,float)
    total=0.
    for i in range(y.size):
        for j in range(i+1,y.size):
            total+=w[i,j]*(abs(y[i]-y[j])**p-np.mean(np.abs(x[:,i]-x[:,j])**p))**2
    return float(total)

def binary_brier(prob:float,outcome:int)->float:
    p=float(np.clip(prob,0,1)); return float((p-int(outcome))**2)

def normalized_skill(raw:float, benchmark:float)->float:
    if not all(math.isfinite(float(v)) for v in (raw,benchmark)) or benchmark<=0:return math.nan
    return float(1-raw/benchmark)

def moving_block_indices(n:int,block:int,rng:np.random.Generator)->np.ndarray:
    out=[]; block=max(1,min(block,n))
    while len(out)<n:
        s=int(rng.integers(0,n-block+1));out.extend(range(s,s+block))
    return np.asarray(out[:n])

def model_confidence_set(losses:Mapping[str,Sequence[float]],alpha:float=.10,reps:int=500,block_length:int=3,seed:int=20260624,min_n:int=20)->list[dict[str,Any]]:
    ids=list(losses); arrays={k:np.asarray(losses[k],float) for k in ids}
    n=min((len(v) for v in arrays.values()),default=0)
    rows=[]
    if len(ids)<2 or n<min_n:
        return [dict(model_id=k,mcs_included=True,elimination_order=None,test_statistic=math.nan,bootstrap_p_value=math.nan,sample_count=n,block_length=block_length) for k in ids]
    mat=np.column_stack([arrays[k][:n] for k in ids]); mask=np.all(np.isfinite(mat),axis=1);mat=mat[mask];n=len(mat)
    active=list(range(len(ids))); eliminated=[]; rng=np.random.default_rng(seed)
    while len(active)>1:
        means=np.mean(mat[:,active],axis=0); worst_local=int(np.argmax(means)); worst=active[worst_local]
        best=float(np.min(means)); diff=mat[:,worst]-np.min(mat[:,active],axis=1); obs=float(np.mean(diff))
        boot=[]
        centered=diff-np.mean(diff)
        for _ in range(reps):boot.append(float(np.mean(centered[moving_block_indices(n,block_length,rng)])))
        p=float(np.mean(np.asarray(boot)>=obs))
        stat=obs/(np.std(diff,ddof=1)/math.sqrt(n)+1e-12)
        if p>=alpha:break
        eliminated.append((worst,stat,p));active.remove(worst)
    order={idx:i+1 for i,(idx,_,_) in enumerate(eliminated)}; stats={idx:(s,p) for idx,s,p in eliminated}
    for i,k in enumerate(ids):
        s,p=stats.get(i,(0.0,1.0));rows.append(dict(model_id=k,mcs_included=i in active,elimination_order=order.get(i),test_statistic=float(s),bootstrap_p_value=float(p),sample_count=n,block_length=block_length))
    return rows

@dataclass
class HorizonDMA:
    forgetting:float=.97; min_weight:float=.02; max_weight:float=.80; shrinkage:float=.10
    weights:dict[int,dict[str,float]]=field(default_factory=lambda:{h:{} for h in HORIZONS})
    counts:dict[int,int]=field(default_factory=lambda:{h:0 for h in HORIZONS})
    def update(self,h:int,losses:Mapping[str,float],matured:bool,eligible:Sequence[str]|None=None)->dict[str,Any]:
        if h not in HORIZONS:raise ValueError('unsupported horizon')
        valid={k:float(v) for k,v in losses.items() if math.isfinite(float(v)) and (eligible is None or k in eligible)}
        prior=self.weights[h]
        if not matured or len(valid)<2:
            return self.summary(h,'OUTCOME_PENDING' if not matured else 'STATIC_FALLBACK')
        if not prior:prior={k:1/len(valid) for k in valid}
        raw={k:max(prior.get(k,1/len(valid)),1e-12)**self.forgetting*math.exp(-valid[k]) for k in valid}
        arr=np.array(list(raw.values()),float);arr/=arr.sum();equal=np.full(len(arr),1/len(arr));arr=(1-self.shrinkage)*arr+self.shrinkage*equal
        arr=np.clip(arr,self.min_weight,self.max_weight);arr/=arr.sum();old=self.weights[h];self.weights[h]=dict(zip(raw,arr));self.counts[h]+=1
        out=self.summary(h,'VALID_DYNAMIC_WEIGHTS');out['dma_weight_turnover']=.5*sum(abs(out['weights'].get(k,0)-old.get(k,0)) for k in set(out['weights'])|set(old));return out
    def predict(self,h:int,predictions:Mapping[str,float])->float:
        w=self.weights[h];pairs=[(k,float(v)) for k,v in predictions.items() if k in w and math.isfinite(float(v))]
        return float(sum(w[k]*v for k,v in pairs)/sum(w[k] for k,v in pairs)) if pairs else math.nan
    def summary(self,h:int,reason:str)->dict[str,Any]:
        w=self.weights[h];a=np.asarray(list(w.values()),float);ent=float(-np.sum(a*np.log(np.clip(a,1e-12,1)))) if len(a) else math.nan
        return {'horizon':h,'weights':dict(w),'dma_weight_entropy':ent,'dma_effective_experts':float(math.exp(ent)) if math.isfinite(ent) else math.nan,'dma_fallback_reason':reason,'dma_sample_count':self.counts[h]}

@dataclass
class SequentialConformal:
    coverage:float=.90; maxlen:int=500; residuals:dict[int,list[float]]=field(default_factory=lambda:{h:[] for h in HORIZONS}); covered:dict[int,list[int]]=field(default_factory=lambda:{h:[] for h in HORIZONS})
    def origin_interval(self,h:int,mean:float,base_width:float,epoch:str)->dict[str,Any]:
        r=np.asarray(self.residuals[h],float);n=len(r);q=float(np.quantile(r,min(1,(n+1)*self.coverage/max(1,n)),method='higher')) if n>=5 else float(base_width)
        return {f'origin_lower_h{h}':float(mean-q),f'origin_upper_h{h}':float(mean+q),'origin_calibration_method':'SEQUENTIAL_ABSOLUTE_RESIDUAL' if n>=5 else 'BASE_WIDTH_FALLBACK','origin_calibration_epoch':epoch,'origin_target_coverage':self.coverage,'origin_residual_quantile':q,'origin_interval_width':2*q,'residual_sample_count':n,'fallback_reason':None if n>=5 else 'INSUFFICIENT_MATURED_RESIDUALS'}
    def settle(self,h:int,actual:float,mean:float,lower:float,upper:float,matured:bool)->None:
        if not matured:return
        self.residuals[h].append(abs(float(actual)-float(mean)));self.covered[h].append(int(lower<=actual<=upper));self.residuals[h]=self.residuals[h][-self.maxlen:];self.covered[h]=self.covered[h][-self.maxlen:]
    def report(self,h:int)->dict[str,Any]:
        c=self.covered[h];r=self.residuals[h];rc=float(np.mean(c[-100:])) if c else math.nan
        return {'rolling_realized_coverage':rc,'coverage_debt':max(0,self.coverage-rc) if math.isfinite(rc) else math.nan,'calibration_age':len(r),'residual_sample_count':len(r)}

def har_volatility(close:Sequence[float],high=None,low=None)->dict[str,Any]:
    c=np.asarray(close,float);c=c[np.isfinite(c)&(c>0)]
    if len(c)<121:return {'forecast':math.nan,'estimator':'UNAVAILABLE','sample_count':len(c),'fallback_reason':'NEED_121_HOURS'}
    r=np.diff(np.log(c));rv=r*r
    scales=[1,6,24,120];features=[float(np.mean(rv[-s:])) for s in scales]
    X=[];y=[]
    for i in range(120,len(rv)):
        X.append([1]+[float(np.mean(rv[i-s:i])) for s in scales]);y.append(rv[i])
    coef=np.linalg.lstsq(np.asarray(X),np.asarray(y),rcond=None)[0] if len(X)>=10 else np.array([0,.25,.25,.25,.25])
    forecast=max(0,float(np.dot(coef,[1]+features)))
    return {'forecast':math.sqrt(forecast),'variance_forecast':forecast,'estimator':'HAR_RV_CLOSE_TO_CLOSE','scales_hours':scales,'sample_count':len(r),'fallback_reason':None}

def venn_abers_like(raw_probs:Sequence[float],outcomes:Sequence[int],p:float,min_n:int=20)->dict[str,Any]:
    x=np.asarray(raw_probs,float);y=np.asarray(outcomes,int);m=np.isfinite(x)&np.isin(y,[0,1]);x=x[m];y=y[m];p=float(np.clip(p,0,1))
    if len(x)<min_n:return {'raw_probability':p,'calibrated_probability':p,'lower_probability':max(0,p-.1),'upper_probability':min(1,p+.1),'sample_count':len(x),'fallback_pooling_status':'POOLED_FALLBACK'}
    order=np.argsort(x);x=x[order];y=y[order]
    # bounded monotone bin calibration (PAV-like cumulative smoothing)
    bins=np.array_split(np.arange(len(x)),min(10,max(2,len(x)//10)));bx=np.array([x[b].mean() for b in bins]);by=np.maximum.accumulate([y[b].mean() for b in bins]);cal=float(np.interp(p,bx,by));width=1.96*math.sqrt(max(cal*(1-cal),1e-6)/len(x))
    return {'raw_probability':p,'calibrated_probability':cal,'lower_probability':max(0,cal-width),'upper_probability':min(1,cal+width),'brier_score':float(np.mean((np.interp(x,bx,by)-y)**2)),'expected_calibration_error':float(np.mean(np.abs(np.interp(x,bx,by)-y))),'sample_count':len(x),'fallback_pooling_status':'NONE'}

def conformal_risk(losses:Sequence[float],target:float=.10,delta:float=.05,thresholds:Sequence[float]|None=None)->dict[str,Any]:
    a=np.asarray(losses,float);a=a[np.isfinite(a)];n=len(a)
    if n==0:return {'target_risk':target,'estimated_empirical_risk':math.nan,'conservative_upper_risk':math.nan,'selected_threshold':math.nan,'sample_count':0,'status':'WARN','fallback_reason':'NO_MATURED_LOSSES'}
    emp=float(np.mean(a)); upper=(1-delta**(1/n)) if emp==0 else min(1,emp+math.sqrt(math.log(1/delta)/(2*n))); status='PASS' if upper<=target else 'WARN' if emp<=target else 'FAIL'
    return {'target_risk':target,'estimated_empirical_risk':emp,'conservative_upper_risk':upper,'selected_threshold':float(max(thresholds or [.5])),'sample_count':n,'status':status,'fallback_reason':None}

def promotion_report(metrics:Mapping[str,Any])->dict[str,Any]:
    checks={'lower_oos_crps':metrics.get('crps_skill',-1)>0,'noninferior_mae':metrics.get('mae_skill',-1)>=0,'noninferior_brier':metrics.get('brier_skill',-1)>=0,'coverage_ok':metrics.get('coverage_ok',False),'mcs_member':metrics.get('mcs_member',False),'no_leakage':metrics.get('no_leakage',False),'protected_hash_unchanged':metrics.get('protected_hash_unchanged',False),'bounded_runtime':metrics.get('bounded_runtime',False)}
    return {'shadow_only':True,'automatic_promotion':False,'eligible_for_human_review':all(checks.values()),'checks':checks,'report_hash':hashlib.sha256(json.dumps(checks,sort_keys=True).encode()).hexdigest()}
