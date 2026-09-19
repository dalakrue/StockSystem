"""Causal, shadow-only multi-horizon forecasts and three-standard regime evidence.
No function in this module changes protected production decisions or weights.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Mapping, Sequence
import numpy as np
import pandas as pd
HORIZONS=(1,2,3,4,6)
EXPERTS=("local_trend","ridge_ar","vol_momentum","mean_reversion","regime_conditional","analogue")

def _finite(a):
    x=np.asarray(a,dtype=float); return x[np.isfinite(x)]

def independent_expert_forecasts(close: Sequence[float], horizon:int, regime_bias:float=0.0)->dict[str,float]:
    x=_finite(close)
    if len(x)<12: return {}
    h=int(horizon); p=float(x[-1]); r=np.diff(np.log(np.clip(x,1e-12,None)))
    w=min(48,len(x)); t=np.arange(w,dtype=float); slope=np.polyfit(t,x[-w:],1)[0]
    # Regularized AR on returns, fit independently for each horizon.
    lag=min(8,max(2,len(r)//8)); rows=[]; y=[]
    for i in range(lag,len(r)-h+1): rows.append(r[i-lag:i]); y.append(np.sum(r[i:i+h]))
    ar=0.0
    if rows:
        X=np.asarray(rows); yy=np.asarray(y); lam=1e-3
        ar=float(np.asarray(r[-lag:]) @ np.linalg.solve(X.T@X+lam*np.eye(lag),X.T@yy))
    vol=float(np.std(r[-min(72,len(r)):],ddof=1)) if len(r)>2 else 0.0
    mom=float(np.mean(r[-min(12,len(r)):]))*h
    long_mean=float(np.mean(x[-min(120,len(x)):]))
    distances=[]
    pattern=r[-min(6,len(r)):]
    for i in range(len(r)-len(pattern)-h):
        d=float(np.mean((r[i:i+len(pattern)]-pattern)**2)); distances.append((d,i))
    analogue=0.0
    if distances:
        use=sorted(distances)[:min(12,len(distances))]
        analogue=float(np.average([np.sum(r[i+len(pattern):i+len(pattern)+h]) for _,i in use],weights=[1/(d+1e-9) for d,i in use]))
    return {
      "local_trend":p+slope*h,
      "ridge_ar":p*math.exp(ar),
      "vol_momentum":p*math.exp(np.clip(mom,-3*vol*math.sqrt(h),3*vol*math.sqrt(h))),
      "mean_reversion":p+(long_mean-p)*(1-math.exp(-h/24)),
      "regime_conditional":p*math.exp(np.clip(mom+float(regime_bias)*vol*math.sqrt(h),-4*vol*math.sqrt(h),4*vol*math.sqrt(h))),
      "analogue":p*math.exp(analogue),
    }

def dma_weights(loss_history: Mapping[str,Sequence[float]]|None=None, forgetting:float=.97, floor:float=.02)->dict[str,float]:
    forgetting=float(np.clip(forgetting,.90,.999)); scores=[]
    for name in EXPERTS:
        losses=_finite((loss_history or {}).get(name,[]))
        if len(losses)==0: score=1.0
        else:
            ages=np.arange(len(losses)-1,-1,-1); ww=forgetting**ages
            score=math.exp(-float(np.sum(ww*losses)/max(np.sum(ww),1e-12)))
        scores.append(max(floor,score))
    z=sum(scores); return {n:s/z for n,s in zip(EXPERTS,scores)}

def reconcile(points:Mapping[int,float], anchor:float)->tuple[dict[int,float],float,float]:
    hs=sorted(points); vals=np.array([points[h] for h in hs],float)
    increments=np.diff(np.r_[anchor,vals]); pre=float(np.mean(np.abs(np.diff(increments)))) if len(increments)>1 else 0.0
    # Smooth increments, preserving total H6 displacement.
    if len(increments)>2:
        sm=np.convolve(increments,[.25,.5,.25],mode='same'); sm[0]=(.75*increments[0]+.25*increments[1]); sm[-1]=(.25*increments[-2]+.75*increments[-1])
        if abs(sm.sum())>1e-15: sm*=increments.sum()/sm.sum()
    else: sm=increments
    out={h:float(anchor+np.sum(sm[:i+1])) for i,h in enumerate(hs)}
    post=float(np.mean(np.abs(np.diff(sm)))) if len(sm)>1 else 0.0
    return out,pre,post

def adaptive_interval(pred:float, residuals:Sequence[float], horizon:int, alpha:float=.1)->tuple[float,float,float,str]:
    e=np.abs(_finite(residuals)); minimum=max(12,3*int(horizon))
    if len(e)>=minimum: q=float(np.quantile(e,1-alpha,method='higher')); method='ADAPTIVE_CONFORMAL'
    else: q=float(np.std(e,ddof=1)*1.645) if len(e)>2 else float('nan'); method='INSUFFICIENT_EVIDENCE'
    return pred-q,pred+q,q,method

def bocpd_proxy(values:Sequence[float])->dict:
    x=_finite(values)
    if len(x)<12:return {'change_probability':float('nan'),'status':'INSUFFICIENT_EVIDENCE'}
    a=x[-min(12,len(x)):]; b=x[-min(48,len(x)):-len(a)]
    if len(b)<6:return {'change_probability':float('nan'),'status':'INSUFFICIENT_EVIDENCE'}
    pooled=max(float(np.std(np.r_[a,b],ddof=1)),1e-12); z=abs(float(np.mean(a)-np.mean(b)))/(pooled*math.sqrt(1/len(a)+1/len(b)))
    p=float(1-math.exp(-.5*z*z)); return {'change_probability':float(np.clip(p,0,1)),'status':'STRUCTURAL_BREAK' if p>=.8 else 'STABLE'}

def three_standard_regime(close:Sequence[float], causal:Mapping[str,float]|None=None)->dict:
    x=_finite(close); specs={'lower':(24,48),'middle':(120,240),'higher':(480,600)}; results={}
    for name,(lo,hi) in specs.items():
        n=min(hi,len(x));
        if n<lo: results[name]={'status':'INSUFFICIENT_EVIDENCE','sample_count':n,'probabilities':{'BULL':float('nan'),'BEAR':float('nan'),'NEUTRAL':float('nan')}}; continue
        r=np.diff(np.log(np.clip(x[-n:],1e-12,None))); mu=float(np.mean(r[-max(12,n//6):])); vol=max(float(np.std(r,ddof=1)),1e-9); z=mu/(vol/math.sqrt(max(1,min(24,len(r)))))
        bull=1/(1+math.exp(-z)); bear=1-bull; neutral=math.exp(-abs(z)); total=bull+bear+neutral; probs={'BULL':bull/total,'BEAR':bear/total,'NEUTRAL':neutral/total}; state=max(probs,key=probs.get)
        entropy=-sum(p*math.log(max(p,1e-12)) for p in probs.values())/math.log(3); trans=float(np.clip(.02+.35*entropy+.25*float((causal or {}).get('change_probability',0) or 0),0,1))
        results[name]={'status':'CALIBRATION_PENDING','sample_count':n,'probabilities':probs,'major_regime':state,'entropy':entropy,'transition_risk':trans,'expected_duration':1/max(trans,1e-6),'end_probability_h1':trans,'end_probability_h3':1-(1-trans)**3,'end_probability_h6':1-(1-trans)**6}
    valid=[v for v in results.values() if 'major_regime' in v]
    if not valid:return {'standards':results,'status':'INSUFFICIENT_EVIDENCE'}
    reliability=[max(.05,1-v['entropy']) for v in valid]; comb={k:sum(w*v['probabilities'][k] for w,v in zip(reliability,valid))/sum(reliability) for k in ('BULL','BEAR','NEUTRAL')}
    consensus=max(comb,key=comb.get); agreement=len({v['major_regime'] for v in valid})==1
    return {'standards':results,'combined_probabilities':comb,'combined_regime':consensus,'three_standard_agreement':agreement,'combined_transition_risk':sum(w*v['transition_risk'] for w,v in zip(reliability,valid))/sum(reliability),'status':'SHADOW_ONLY'}
