"""Proper probabilistic scores for Field 8 shadow validation."""
from __future__ import annotations
import math
from typing import Iterable, Sequence
import numpy as np

def gaussian_crps(observation: float, mean: float, std: float) -> float:
    y, mu, sigma = float(observation), float(mean), float(std)
    if not all(math.isfinite(x) for x in (y, mu, sigma)) or sigma <= 0:
        return math.nan
    z = (y - mu) / sigma
    phi = math.exp(-0.5*z*z) / math.sqrt(2.0*math.pi)
    Phi = 0.5 * (1.0 + math.erf(z/math.sqrt(2.0)))
    return float(sigma * (z*(2.0*Phi-1.0) + 2.0*phi - 1.0/math.sqrt(math.pi)))

def sample_crps(observation: float, samples: Sequence[float]) -> float:
    x=np.asarray(samples,dtype=float); x=x[np.isfinite(x)]
    if x.size == 0 or not math.isfinite(float(observation)): return math.nan
    return float(np.mean(np.abs(x-float(observation))) - 0.5*np.mean(np.abs(x[:,None]-x[None,:])))

def quantile_crps(observation: float, quantiles: Sequence[float], levels: Sequence[float]) -> float:
    q=np.asarray(quantiles,dtype=float); a=np.asarray(levels,dtype=float)
    mask=np.isfinite(q)&np.isfinite(a)&(a>0)&(a<1)
    q,a=q[mask],a[mask]
    if q.size < 2 or not math.isfinite(float(observation)): return math.nan
    order=np.argsort(a); q,a=q[order],a[order]
    u=float(observation)-q
    pin=np.maximum(a*u,(a-1.0)*u)
    return float(2.0*np.trapezoid(pin,a))

def crps(observation: float, mean: float|None=None, std: float|None=None, samples=None, quantiles=None, levels=None) -> tuple[float,str]:
    if mean is not None and std is not None:
        value=gaussian_crps(observation,mean,std)
        if math.isfinite(value): return value,'GAUSSIAN_ANALYTIC'
    if samples is not None:
        value=sample_crps(observation,samples)
        if math.isfinite(value): return value,'EMPIRICAL_SAMPLE'
    if quantiles is not None and levels is not None:
        value=quantile_crps(observation,quantiles,levels)
        if math.isfinite(value): return value,'QUANTILE_APPROXIMATION'
    return math.nan,'UNAVAILABLE'

def brier_score(probabilities: Sequence[float], outcome_index: int) -> float:
    p=np.asarray(probabilities,dtype=float)
    if p.size==0 or not np.all(np.isfinite(p)) or np.any((p<0)|(p>1)) or abs(float(p.sum())-1)>1e-6: return math.nan
    y=np.zeros_like(p); y[int(outcome_index)]=1.0
    return float(np.mean((p-y)**2))

def log_score(probability_of_outcome: float, epsilon: float=1e-12) -> float:
    p=float(probability_of_outcome)
    if not math.isfinite(p) or p<0 or p>1: return math.nan
    return float(-math.log(max(p,epsilon)))

def interval_score(observation: float, lower: float, upper: float, alpha: float=0.1) -> float:
    y,l,u=map(float,(observation,lower,upper))
    if not all(math.isfinite(x) for x in (y,l,u,alpha)) or l>u or not 0<alpha<1:return math.nan
    return float((u-l)+(2/alpha)*(l-y if y<l else 0)+(2/alpha)*(y-u if y>u else 0))
