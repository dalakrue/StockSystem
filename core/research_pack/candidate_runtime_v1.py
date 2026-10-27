"""Research inference for the 120 replacement equations. No orders or fitting."""
import numpy as np

def predict_candidate(features, model):
    x=features[model['features']].to_numpy(dtype=float) if hasattr(features,'columns') else np.asarray(features,dtype=float)
    valid=np.isfinite(x).all(axis=1)
    z=np.clip((x-np.asarray(model['mean']))/np.asarray(model['scale']),-6,6)
    kind=model['kind'];pred=np.full(len(z),np.nan)
    if kind=='bayesian_cells':
        a=np.searchsorted(model['edges_a'],z[valid,model['a']]);b=np.searchsorted(model['edges_b'],z[valid,model['b']]);pred[valid]=np.asarray(model['values'])[a,b]
    elif kind=='regression_tree':
        for i in np.flatnonzero(valid):
            n=0
            while model['left'][n]>=0:
                n=model['left'][n] if z[i,model['feature'][n]]<=model['split'][n] else model['right'][n]
            pred[i]=model['value'][n]
    elif kind=='nearest_motif':
        centers=np.asarray(model['x']);y=np.asarray(model['y']);k=model['k']
        for i in np.flatnonzero(valid):
            distance=np.sum((centers-z[i])**2,axis=1);neighbors=np.argsort(distance,kind='stable')[:k];pred[i]=np.mean(y[neighbors])
    elif kind=='quadratic_ridge':
        a=z[valid][:,model['selected']];poly=np.column_stack([a]+[a[:,i]*a[:,j] for i in range(a.shape[1]) for j in range(i,a.shape[1])])
        pred[valid]=poly@np.asarray(model['coef'])+model['intercept']
    else:raise ValueError(kind)
    return pred

def candidate_signal(features, specification):
    score=predict_candidate(features,specification['model'])
    # strict_valid remains false until fresh prospective validation.
    signal=score>specification['model']['threshold']
    if hasattr(features,'columns'):
        all_original=['r1','r3','r6','r12','r24','body','range_atr','ema_gap','ema_dist','pos24','breakout24','seq3','accel','vol_ratio','wick_low','wick_high','middle_score','haar4','haar8','haar16','haar32','wave_accel','eff12','eff24','atr_ratio','ordinal4']
        if all(c in features.columns for c in all_original):signal &= np.isfinite(features[all_original].to_numpy()).all(axis=1)
    return np.where(signal,specification['side'],0),score

def candidate_distances(atr_pips,specification):
    e=specification['exit']
    return (np.clip(np.asarray(atr_pips)*e['tp_atr'],e['tp_min'],e['tp_max']),
            np.clip(np.asarray(atr_pips)*e['sl_atr'],e['sl_min'],e['sl_max']))

def target_columns(entry_price,side,symbol,tp_pips,sl_pips):
    pip=.01 if str(symbol).upper().replace('/','').endswith('JPY') else .0001
    if not np.isfinite([entry_price,tp_pips,sl_pips]).all() or min(entry_price,tp_pips,sl_pips)<=0:raise ValueError('Invalid entry or pip distances')
    if side not in (-1,1):raise ValueError('Side must be BUY +1 or SELL -1')
    return dict(TP_Price=entry_price+side*tp_pips*pip,SL_Price=entry_price-side*sl_pips*pip,
                TP_Pips=tp_pips,SL_Pips=sl_pips,Reward_Risk=tp_pips/sl_pips,Net_Reward_Risk=(tp_pips-1)/(sl_pips+1),
                TP_Min_Pips=10,TP_Max_Pips=200,SL_Min_Pips=10,SL_Max_Pips=100)
