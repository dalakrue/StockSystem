"""Causal, shadow-only research stack for Fields 2-8.
No function in this module may alter protected production decisions.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence
import hashlib, json, math
import numpy as np

HORIZONS=(1,3,6)
INSUFFICIENT='INSUFFICIENT_EVIDENCE'

def finite_sample_quantile(values: Sequence[float], coverage: float=.9) -> float:
    x=np.sort(np.asarray(values,dtype=float)); x=x[np.isfinite(x)]
    if x.size==0:return math.nan
    k=min(x.size-1,max(0,math.ceil((x.size+1)*coverage)-1))
    return float(x[k])

@dataclass
class AdaptiveConformalState:
    coverage: float=.9; maxlen: int=500
    lower: dict[int,list[float]]=field(default_factory=lambda:{h:[] for h in HORIZONS})
    upper: dict[int,list[float]]=field(default_factory=lambda:{h:[] for h in HORIZONS})
    widths: dict[int,list[float]]=field(default_factory=lambda:{h:[] for h in HORIZONS})
    covered: dict[int,list[float]]=field(default_factory=lambda:{h:[] for h in HORIZONS})
    def update(self,h:int,y:float,mean:float,lower:float,upper:float,matured:bool)->None:
        if not matured or h not in HORIZONS:return
        vals=(y,mean,lower,upper)
        if not all(math.isfinite(float(v)) for v in vals):return
        self.lower[h].append(max(0.0,float(lower)-float(y)))
        self.upper[h].append(max(0.0,float(y)-float(upper)))
        self.widths[h].append(float(upper)-float(lower))
        self.covered[h].append(float(lower<=y<=upper))
        for d in (self.lower,self.upper,self.widths,self.covered):d[h][:]=d[h][-self.maxlen:]
    def calibrate(self,h:int,mean:float,base_lower:float,base_upper:float)->dict[str,Any]:
        n=min(len(self.lower[h]),len(self.upper[h]))
        if n<5:return {'lower':base_lower,'upper':base_upper,'sample_count':n,'status':INSUFFICIENT,'method':'ORIGIN_INTERVAL_FALLBACK','rolling_coverage':math.nan,'rolling_interval_width':math.nan,'coverage_debt':math.nan}
        ql=finite_sample_quantile(self.lower[h],self.coverage); qu=finite_sample_quantile(self.upper[h],self.coverage)
        rc=float(np.mean(self.covered[h][-100:])); rw=float(np.mean(self.widths[h][-100:]))
        return {'lower':float(base_lower)-ql,'upper':float(base_upper)+qu,'sample_count':n,'status':'VALID_SHADOW','method':'ASYMMETRIC_FINITE_SAMPLE_ROLLING','rolling_coverage':rc,'rolling_interval_width':rw,'coverage_debt':max(0.0,self.coverage-rc)}
    def snapshot(self)->str:
        return json.dumps({'coverage':self.coverage,'counts':{h:len(self.covered[h]) for h in HORIZONS}},sort_keys=True)

@dataclass
class BOCPD:
    hazard: float=1/100; max_run_length:int=256
    mean:float=0.; var:float=1.; n:int=0; run_length:int=0
    def update(self,x:float)->dict[str,Any]:
        if not math.isfinite(float(x)):return {'change_probability':math.nan,'run_length_mean':self.run_length,'run_length_mode':self.run_length,'change_severity':math.nan,'post_change_sample_count':self.n,'change_detection_status':INSUFFICIENT}
        sd=math.sqrt(max(self.var,1e-12)); z=abs((float(x)-self.mean)/sd) if self.n>1 else 0.; cp=float(np.clip(self.hazard+(1-self.hazard)*(1-math.exp(-.5*z*z)),0,1))
        changed=cp>.5
        if changed:self.mean=float(x);self.var=1.;self.n=1;self.run_length=0
        else:
            self.n+=1; delta=float(x)-self.mean;self.mean+=delta/self.n;self.var=((self.n-2)*self.var+delta*(float(x)-self.mean))/max(1,self.n-1);self.run_length=min(self.max_run_length,self.run_length+1)
        return {'change_probability':cp,'run_length_mean':float(self.run_length),'run_length_mode':self.run_length,'change_severity':z,'post_change_sample_count':self.n,'change_detection_status':'VALID_SHADOW' if self.n>=5 else INSUFFICIENT}

STATES=('BULL','BEAR','COMPRESSION','HIGH_VOLATILITY')
def tvtp_transition(current:str,covariates:Mapping[str,float],base:Mapping[str,float]|None=None,min_obs:int=20,obs:int=0)->dict[str,Any]:
    base=dict(base or {s:.25 for s in STATES}); cur=next((s for s in STATES if s in str(current).upper()),'COMPRESSION')
    if obs<min_obs:
        p=np.array([max(1e-6,float(base.get(s,.25))) for s in STATES]);status=INSUFFICIENT
    else:
        x=sum(float(v) for v in covariates.values() if isinstance(v,(int,float)) and math.isfinite(float(v)))
        logits=np.array([.4 if s==cur else 0. for s in STATES])+np.array([.15*x,-.15*x,-.05*abs(x),.05*abs(x)])
        logits-=logits.max();p=np.exp(logits);status='VALID_SHADOW'
    p=np.clip(p,1e-6,1);p/=p.sum();remain=float(p[STATES.index(cur)]);entropy=float(-np.sum(p*np.log(p)))
    return {**{f'probability_transition_{s.lower()}':float(p[i]) for i,s in enumerate(STATES)},'probability_remain_current':remain,'expected_regime_duration':1/max(1e-6,1-remain),'expected_remaining_duration':remain/max(1e-6,1-remain),'transition_entropy':entropy,'regime_shadow_reliability':float(100*(1-entropy/math.log(len(STATES)))),'status':status}

def block_bootstrap_loss_test(prod:Sequence[float],chall:Sequence[float],seed:int=17,reps:int=500,block:int=3,min_n:int=20)->dict[str,Any]:
    a=np.asarray(prod,float);b=np.asarray(chall,float);m=np.isfinite(a)&np.isfinite(b);d=a[m]-b[m];n=d.size
    if n<min_n:return {'conditional_test_statistic':math.nan,'conditional_p_value':math.nan,'adjusted_p_value':math.nan,'loss_difference':math.nan,'confidence_interval':[math.nan,math.nan],'effective_sample_size':n,'evidence_status':INSUFFICIENT}
    rng=np.random.default_rng(seed);means=[]
    for _ in range(reps):
        idx=[]
        while len(idx)<n:
            s=int(rng.integers(0,n));idx.extend((np.arange(block)+s)%n)
        means.append(float(np.mean(d[np.asarray(idx[:n])])) )
    lo,hi=np.quantile(means,[.025,.975]);mu=float(np.mean(d));p=float(2*min(np.mean(np.asarray(means)<=0),np.mean(np.asarray(means)>=0)))
    return {'conditional_test_statistic':mu/(np.std(d,ddof=1)/math.sqrt(n)+1e-12),'conditional_p_value':p,'adjusted_p_value':p,'loss_difference':mu,'confidence_interval':[float(lo),float(hi)],'effective_sample_size':n,'evidence_status':'VALID'}

def model_confidence_set(losses:Mapping[str,Sequence[float]],alpha:.1|float=.1,min_n:int=20)->dict[str,Any]:
    clean={k:np.asarray(v,float) for k,v in losses.items()};n=min((np.isfinite(v).sum() for v in clean.values()),default=0)
    if len(clean)<2 or n<min_n:return {'surviving_model_ids':list(clean),'removed_model_ids':[],'elimination_order':[],'confidence_level':1-alpha,'effective_sample_size':n,'model_confidence_status':INSUFFICIENT}
    means={k:float(np.nanmean(v)) for k,v in clean.items()};best=min(means.values());survivors=[k for k,v in means.items() if v<=best+max(1e-12,.1*abs(best))];removed=[k for k in clean if k not in survivors]
    return {'surviving_model_ids':survivors,'removed_model_ids':removed,'elimination_order':sorted(removed,key=lambda k:means[k],reverse=True),'confidence_level':1-alpha,'effective_sample_size':n,'model_confidence_status':'VALID'}

def meta_actionability(prob:float|None,n:int,min_n:int=30)->dict[str,Any]:
    if prob is None or not math.isfinite(float(prob)) or n<min_n:return {'actionable_probability':math.nan,'false_positive_probability':math.nan,'abstention_probability':1.,'meta_label_status':INSUFFICIENT,'evidence_quality':'LOW','optional_shadow_size_multiplier':0.,'display':'INSUFFICIENT_EVIDENCE'}
    p=float(np.clip(prob,0,1));display='TAKE' if p>=.65 else 'REDUCE' if p>=.52 else 'ABSTAIN'
    return {'actionable_probability':p,'false_positive_probability':1-p,'abstention_probability':float(max(0,1-2*abs(p-.5))),'meta_label_status':'VALID_SHADOW','evidence_quality':'HIGH' if n>=100 else 'MEDIUM','optional_shadow_size_multiplier':float(np.clip((p-.5)*2,0,1)),'display':display}

def ensemble_weights(model_ids:Sequence[str],losses:Mapping[str,float]|None=None,cap:float=.6,shrink:float=.5)->dict[str,float]:
    ids=list(dict.fromkeys(model_ids));
    if not ids:return {}
    equal=np.full(len(ids),1/len(ids));
    if not losses or any(i not in losses or not math.isfinite(float(losses[i])) for i in ids):return dict(zip(ids,map(float,equal)))
    inv=np.array([1/max(1e-12,float(losses[i])) for i in ids]);inv/=inv.sum();w=shrink*equal+(1-shrink)*inv
    # Project onto the probability simplex with an individual upper cap.
    for _ in range(10):
        over=w>cap
        if not np.any(over):break
        excess=float(np.sum(w[over]-cap));w[over]=cap
        under=~over
        if not np.any(under):break
        room=np.maximum(0.0,cap-w[under]);den=float(room.sum())
        w[under]+=excess*(room/den if den>0 else 1.0/under.sum())
    w/=w.sum();return dict(zip(ids,map(float,w)))

def version_fingerprint(payload:Mapping[str,Any])->str:return hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()
