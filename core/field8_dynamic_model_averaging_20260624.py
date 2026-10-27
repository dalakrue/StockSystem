"""Incremental shadow dynamic-model averaging; never changes production forecasts."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Mapping
import numpy as np

VALID_STATUSES={'SINGLE_MODEL_ONLY','WEIGHTS_NOT_INITIALIZED','WEIGHTS_PENDING_OUTCOME','VALID_DYNAMIC_WEIGHTS'}
@dataclass
class DMAState:
    weights: dict[str,float]=field(default_factory=dict)
    update_sample_count:int=0
    forgetting:float=0.97
    def status(self, matured: bool=False)->str:
        if len(self.weights)<=1:return 'SINGLE_MODEL_ONLY'
        if not self.weights:return 'WEIGHTS_NOT_INITIALIZED'
        if not matured:return 'WEIGHTS_PENDING_OUTCOME'
        return 'VALID_DYNAMIC_WEIGHTS'
    def normalized(self)->dict[str,float]:
        if not self.weights:return {}
        vals={k:max(float(v),0.0) for k,v in self.weights.items()}; s=sum(vals.values())
        return {k:v/s for k,v in vals.items()} if s>0 else {k:1/len(vals) for k in vals}
    def update(self, losses:Mapping[str,float], matured:bool)->dict:
        if not matured:return self.summary(False)
        valid={k:float(v) for k,v in losses.items() if math.isfinite(float(v))}
        if len(valid)<2:
            if len(valid)==1:self.weights={next(iter(valid)):1.0}
            return self.summary(True)
        prior=self.normalized() or {k:1/len(valid) for k in valid}
        raw={k:max(prior.get(k,1/len(valid)),1e-12)**self.forgetting*math.exp(-valid[k]) for k in valid}
        s=sum(raw.values()); self.weights={k:v/s for k,v in raw.items()}; self.update_sample_count+=1
        return self.summary(True)
    def summary(self,matured=False)->dict:
        w=self.normalized(); arr=np.asarray(list(w.values()),dtype=float)
        entropy=float(-(arr*np.log(np.clip(arr,1e-12,None))).sum()) if arr.size else math.nan
        return {'weights':w,'weight_entropy':entropy,'effective_model_count':float(math.exp(entropy)) if math.isfinite(entropy) else math.nan,'dominant_model':max(w,key=w.get) if w else None,'initialization_status':self.status(matured),'update_sample_count':self.update_sample_count}
