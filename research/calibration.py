"""Regularized outcome classifier with disjoint chronological sigmoid calibration."""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

FEATURES=('Suggested TP Pips','Suggested SL Pips','ADX','ATR','unique_family_count','Entry Noise Ratio')

class TemporalOutcomeModel:
    version='REGULARIZED_TEMPORAL_SIGMOID_V1'
    def fit(self,signals,labels,training_end='2025-01-01T00:00:00Z'):
        at=pd.to_datetime(signals.signal_available_at,utc=True)
        ready=pd.to_datetime(labels.label_available_at,utc=True)
        valid=labels.label_complete & ready.lt(pd.Timestamp(training_end))
        dates=at[valid].sort_values()
        if len(dates)<120: raise ValueError('At least 120 completed training labels required')
        split=dates.iloc[int(.70*len(dates))]
        fit=valid & ready.le(split-pd.Timedelta(hours=24))
        calibration=valid & at.ge(split)
        x=signals.reindex(columns=FEATURES).apply(pd.to_numeric,errors='coerce')
        y=labels.outcome
        if y[fit].nunique()<2 or y[calibration].nunique()<2: raise ValueError('Insufficient outcome classes across chronological folds')
        self.base=make_pipeline(SimpleImputer(strategy='median'),StandardScaler(),LogisticRegression(C=.3,max_iter=1000))
        self.base.fit(x.loc[fit],y.loc[fit])
        self.classes=list(self.base.classes_);self.calibrators=[]
        probabilities=self.base.predict_proba(x.loc[calibration])
        for j,c in enumerate(self.classes):
            truth=(y.loc[calibration]==c).astype(int)
            if truth.nunique()<2: self.calibrators.append(None);continue
            logits=np.log(np.clip(probabilities[:,j],1e-6,1-1e-6)/(1-np.clip(probabilities[:,j],1e-6,1-1e-6)))[:,None]
            reg=LogisticRegression(C=.3,max_iter=1000);reg.fit(logits,truth);self.calibrators.append(reg)
        self.conditional_net={c:float(labels.loc[fit & y.eq(c),'net_pips'].mean()) for c in self.classes}
        self.training_end=training_end;self.sample_count=int(fit.sum());self.calibration_count=int(calibration.sum())
        return self

    def predict(self,signals):
        x=signals.reindex(columns=FEATURES).apply(pd.to_numeric,errors='coerce')
        probs=self.base.predict_proba(x)
        for j,reg in enumerate(self.calibrators):
            if reg is not None:
                logits=np.log(np.clip(probs[:,j],1e-6,1-1e-6)/(1-np.clip(probs[:,j],1e-6,1-1e-6)))[:,None]
                probs[:,j]=reg.predict_proba(logits)[:,1]
        probs/=probs.sum(axis=1,keepdims=True)
        return pd.DataFrame(probs,index=signals.index,columns=self.classes)

    def evaluate(self,signals,labels):
        valid=labels.label_complete & pd.to_datetime(signals.signal_available_at,utc=True).ge(pd.Timestamp(self.training_end))
        if not valid.any(): return pd.DataFrame(),pd.DataFrame()
        pred=self.predict(signals.loc[valid]);truth=labels.loc[valid,'outcome']
        scores=[];bins=[]
        for c in self.classes:
            y=truth.eq(c).astype(int);scores.append({'outcome':c,'sample_count':len(y),'brier_score':brier_score_loss(y,pred[c])})
            temp=pd.DataFrame({'p':pred[c],'y':y});temp['bin']=pd.cut(temp.p,np.linspace(0,1,11),include_lowest=True)
            grouped=temp.groupby('bin',observed=True).agg(mean_probability=('p','mean'),observed_frequency=('y','mean'),sample_count=('y','size')).reset_index()
            grouped['outcome']=c;bins.append(grouped)
        return pd.DataFrame(scores),pd.concat(bins,ignore_index=True)


def export_model_json(model,signals,labels,path,policy):
    """Export numerical parameters only; no pickle/code execution at deployment."""
    from sklearn.linear_model import Ridge
    from core.execution_policy_20261003 import VERSION
    from dataclasses import asdict
    import json,hashlib
    x=signals.reindex(columns=FEATURES).apply(pd.to_numeric,errors='coerce')
    ready=pd.to_datetime(labels.label_available_at,utc=True)
    valid=labels.label_complete & ready.lt(pd.Timestamp(model.training_end))
    transformed=model.base[:-1].transform(x)
    reg=model.base[-1];imputer=model.base[0];scaler=model.base[1]
    if transformed.shape[1]!=len(FEATURES):raise ValueError('Every deployment feature must have observed training values')
    payouts={};residuals=[]
    for outcome in model.classes:
        mask=valid & labels.outcome.eq(outcome)
        if mask.sum()<20:raise ValueError('At least 20 payout labels per modeled exit class required')
        pay=Ridge(alpha=10);pay.fit(transformed[mask],labels.loc[mask,'net_pips'])
        residual=labels.loc[mask,'net_pips'].to_numpy()-pay.predict(transformed[mask])
        payouts[outcome]={'coef':pay.coef_.tolist(),'intercept':float(pay.intercept_),'sample_count':int(mask.sum()),'residual_std':float(residual.std(ddof=1))}
    semantics=asdict(policy);semantics['validation_manifest']=''
    spec={'engine':VERSION,'pair_recipe':'FINAL_STRUCTURAL_V1','round_trip_cost_pips':policy.costs,'policy_sha256':hashlib.sha256(json.dumps(semantics,sort_keys=True).encode()).hexdigest(),
      'training_end':model.training_end,'features':list(FEATURES),'classes':model.classes,'impute':imputer.statistics_.tolist(),
      'scale_mean':scaler.mean_.tolist(),'scale_std':scaler.scale_.tolist(),'coef':reg.coef_.tolist(),'intercept':reg.intercept_.tolist(),
      'sigmoid':[{'coef':float(r.coef_[0,0]),'intercept':float(r.intercept_[0])} if r is not None else None for r in model.calibrators],
      'payouts':payouts,'sample_count':model.sample_count,'calibration_sample_count':model.calibration_count,
      'version':model.version,'requires_independent_acceptance_manifest':True}
    from pathlib import Path
    Path(path).write_text(json.dumps(spec,indent=2,allow_nan=False))
    return spec
