"""Causal lightweight alpha-beta-delta, BOCPD and transition evidence."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
import numpy as np

def alpha_metrics(origin,predicted,benchmark,scale,prior_alphas):
    vals=(origin,predicted,benchmark,scale)
    if not all(math.isfinite(float(x)) for x in vals) or min(float(origin),float(predicted),float(benchmark))<=0:return {'alpha':math.nan,'alpha_z':math.nan,'alpha_decay':math.nan,'delta_alpha':math.nan,'delta_acceleration':math.nan}
    pr=10000*math.log(float(predicted)/float(origin)); br=10000*math.log(float(benchmark)/float(origin)); a=pr-br; az=a/max(abs(float(scale)),1e-9)
    hist=[float(x) for x in prior_alphas if math.isfinite(float(x))]
    ew=math.nan
    if hist:
        weights=np.power(.94,np.arange(len(hist)-1,-1,-1)); ew=float(np.average(hist,weights=weights))
    delta=a-hist[-1] if hist else math.nan
    prev_delta=(hist[-1]-hist[-2]) if len(hist)>=2 else math.nan
    accel=delta-prev_delta if math.isfinite(delta) and math.isfinite(prev_delta) else math.nan
    return {'predicted_log_return':pr,'benchmark_log_return':br,'alpha':a,'alpha_z':az,'alpha_decay':a-ew if math.isfinite(ew) else math.nan,'delta_alpha':delta,'delta_acceleration':accel}

@dataclass
class RecursiveBeta:
    names:tuple[str,...]=('volatility','regime','usd_factor','session','liquidity','interval_width')
    process_noise:float=1e-4; observation_noise:float=1e-2
    beta:np.ndarray=field(default_factory=lambda:np.zeros(7)); covariance:np.ndarray=field(default_factory=lambda:np.eye(7)*10)
    updates:int=0
    def update(self,factors:dict,target:float,matured:bool):
        x=np.array([1.0]+[float(factors.get(n,math.nan)) for n in self.names])
        missing=[self.names[i] for i,v in enumerate(x[1:]) if not math.isfinite(v)]
        if not matured:return self.summary('PENDING_OUTCOME',missing)
        if missing or not math.isfinite(float(target)):return self.summary('MISSING_FACTORS',missing)
        P=self.covariance+np.eye(len(x))*self.process_noise; denom=float(x@P@x+self.observation_noise); K=P@x/denom
        residual=float(target-x@self.beta); self.beta=self.beta+K*residual; self.covariance=(np.eye(len(x))-np.outer(K,x))@P; self.updates+=1
        return self.summary('UPDATED',[])
    def summary(self,status,missing):
        diag=float(np.trace(self.covariance)); unc=float(math.sqrt(max(diag,0))); inst=float(np.linalg.norm(self.beta[1:]))
        out={'alpha_intercept':float(self.beta[0]),'beta_covariance_trace':diag,'beta_uncertainty':unc,'beta_instability':inst,'beta_update_status':status,'beta_reason_codes':'|'.join(missing) if missing else 'NONE'}
        out.update({f'beta_{n}':float(self.beta[i+1]) for i,n in enumerate(self.names)}); return out

def classify_state(alpha_z,delta,accel,beta_instability,change_probability):
    vals=(alpha_z,delta)
    if not all(math.isfinite(float(x)) for x in vals):return 'INSUFFICIENT_EVIDENCE'
    if float(change_probability)>=.7:return 'STRUCTURAL_BREAK_WARNING'
    if math.isfinite(float(beta_instability)) and float(beta_instability)>=3:return 'HIGH_BETA_FRAGILITY'
    if float(alpha_z)>=0 and float(alpha_z)-float(delta)<0:return 'ZERO_CROSS_UP'
    if float(alpha_z)<0 and float(alpha_z)-float(delta)>=0:return 'ZERO_CROSS_DOWN'
    strengthening=(float(delta)>0 if float(alpha_z)>=0 else float(delta)<0)
    return ('UP_EDGE_' if float(alpha_z)>=0 else 'DOWN_EDGE_')+('STRENGTHENING' if strengthening else 'WEAKENING')

def change_point_evidence(loss_vector,max_support=128):
    x=np.asarray([v for v in loss_vector if math.isfinite(float(v))],dtype=float)
    if x.size<4:return {'change_point_probability':0.0,'run_length_posterior_mean':float(x.size),'run_length_posterior_mode':int(x.size),'run_length_entropy':0.0,'change_state':'STABLE'}
    x=x[-max_support:]; split=max(2,len(x)//3); before=x[:-split]; after=x[-split:]; scale=float(np.std(before)+1e-9); z=abs(float(np.mean(after)-np.mean(before)))/scale; p=float(1-math.exp(-max(z-1,0)))
    return {'change_point_probability':min(max(p,0),1),'run_length_posterior_mean':float(len(after) if p>.5 else len(x)),'run_length_posterior_mode':int(len(after) if p>.5 else len(x)),'run_length_entropy':float(-(p*math.log(max(p,1e-12))+(1-p)*math.log(max(1-p,1e-12)))),'change_state':'BREAK' if p>=.7 else 'WATCH' if p>=.4 else 'STABLE'}

def filardo_transition(regime_age,alpha_z,delta,accel,beta_instability,volatility,session,interval_width,change_probability):
    vals=[regime_age,alpha_z,delta,accel,beta_instability,volatility,interval_width,change_probability]
    if not all(math.isfinite(float(v)) for v in vals):return {'duration_model_status':'INSUFFICIENT_EVIDENCE'}
    session_term={'ASIAN':-.1,'LONDON':.1,'LONDON_NEW_YORK_OVERLAP':.2,'NEW_YORK':.1}.get(str(session),0)
    logit=-2+.08*float(regime_age)+.15*abs(float(alpha_z))+.1*abs(float(delta))+.05*abs(float(accel))+.2*float(beta_instability)+.3*float(change_probability)+session_term
    p1=1/(1+math.exp(-max(min(logit,30),-30)))
    out={'duration_model_status':'VALID_SHADOW','expected_remaining_duration':float(max((1-p1)/max(p1,1e-6),0))}
    for h in (1,3,6):
        ph=1-(1-p1)**h; out[f'transition_probability_h{h}']=float(ph); out[f'regime_survival_probability_h{h}']=float(1-ph)
    return out
