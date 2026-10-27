"""Guarded numerical model inference for the FINAL target recipe only."""
from pathlib import Path
from dataclasses import asdict
import hashlib,json
import numpy as np
import pandas as pd
from core.execution_policy_20261003 import VERSION


def load_validated_model(policy):
    if not policy.validation_manifest:return None
    root=Path(__file__).resolve().parents[1]
    path=Path(policy.validation_manifest)
    if not path.is_absolute():path=root/path
    try:
        manifest=json.loads(path.read_text())
        if not (manifest.get('all_acceptance_gates_passed') is True and manifest.get('untouched_forward_verified') is True and manifest.get('decision_engine_version')==VERSION):return None
        model_path=Path(manifest['calibrated_model_json'])
        if not model_path.is_absolute():model_path=root/model_path
        payload=model_path.read_bytes()
        if hashlib.sha256(payload).hexdigest()!=manifest['calibrated_model_sha256']:return None
        m=json.loads(payload)
        semantics=asdict(policy);semantics['validation_manifest']=''
        expected=hashlib.sha256(json.dumps(semantics,sort_keys=True).encode()).hexdigest()
        if m['engine']!=VERSION or m['pair_recipe']!='FINAL_STRUCTURAL_V1' or m['policy_sha256']!=expected:return None
        if set(m['classes'])!={'TP','SL','BIAS','TIMEOUT'}:return None
        if any(x is None for x in m['sigmoid']):return None
        return m
    except (OSError,ValueError,KeyError,TypeError):return None


def infer_model(m,frame,tp_distance,sl_distance,pip):
    values=frame.copy()
    values['Suggested TP Pips']=tp_distance/pip;values['Suggested SL Pips']=sl_distance/pip
    x=values.reindex(columns=m['features']).apply(pd.to_numeric,errors='coerce').to_numpy(float)
    impute=np.asarray(m['impute'],float)
    x=np.where(np.isfinite(x),x,impute)
    x=(x-np.asarray(m['scale_mean']))/np.maximum(np.asarray(m['scale_std']),1e-12)
    logits=x@np.asarray(m['coef']).T+np.asarray(m['intercept'])
    if len(m['classes'])==2 and logits.shape[1]==1:
        prob=1/(1+np.exp(-np.clip(logits[:,0],-35,35)));probs=np.column_stack((1-prob,prob))
    else:
        logits-=logits.max(axis=1)[:,None];probs=np.exp(logits);probs/=probs.sum(axis=1)[:,None]
    for j,c in enumerate(m['classes']):
        sigmoid=m['sigmoid'][j];logit=np.log(np.clip(probs[:,j],1e-6,1-1e-6)/(1-np.clip(probs[:,j],1e-6,1-1e-6)))
        probs[:,j]=1/(1+np.exp(-np.clip(sigmoid['coef']*logit+sigmoid['intercept'],-35,35)))
    probs/=probs.sum(axis=1)[:,None]
    payouts=[];variances=[];counts=[]
    for j,c in enumerate(m['classes']):
        pay=m['payouts'][c];payouts.append(x@np.asarray(pay['coef'])+pay['intercept'])
        variances.append(pay['residual_std']**2);counts.append(pay['sample_count'])
    payout=np.column_stack(payouts)
    # A TP payout cannot exceed the printed distance less total modeled costs.
    # The SL term includes adverse gap risk; it cannot predict a smaller loss
    # than the printed stop. Other terms use actual observed exit regressions.
    costs=float(m.get('round_trip_cost_pips',0.))
    for j,c in enumerate(m['classes']):
        if c=='TP':payout[:,j]=np.minimum(payout[:,j],np.asarray(tp_distance/pip)-costs)
        if c=='SL':payout[:,j]=np.minimum(payout[:,j],-np.asarray(sl_distance/pip)-costs)
    ev=(probs*payout).sum(axis=1)
    uncertainty=np.sqrt((probs*np.asarray(variances)).sum(axis=1)/max(1,min(counts)))
    result=pd.DataFrame(index=frame.index)
    result['expected_net_pips']=ev;result['expected_net_pips_lower_bound']=ev-1.96*uncertainty
    result['forecast_sample_count']=min(counts)
    result['probability_calibration_version']=m['version'];result['direction_probability']=np.nan
    for c in ('TP','SL','BIAS','TIMEOUT'):
        result['p_'+c.lower()]=probs[:,m['classes'].index(c)] if c in m['classes'] else 0.
    result['calibrated_model_applied']=pd.to_datetime(frame.signal_available_at,utc=True).ge(pd.Timestamp(m['training_end']))
    return result
