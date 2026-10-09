"""Final-price, elapsed-time H1 labels and causal empirical forecasts.

Labels are research approximations from H1 aggregate OHLC with adverse cost
allowances. They are never described as observed broker bid/ask first touches.
Full intervals are released before fitting. Missing bars censor the interval.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from core.execution_policy_20261003 import get_policy,closure_deadline

EXITS=('TP','SL','BIAS','TIMEOUT')

def final_pair_labels(frame,side,tp_price,sl_price,*,policy=None,ambiguity='SL_FIRST',bias_exit=True):
    p=policy or get_policy()
    if ambiguity not in {'TP_FIRST','SL_FIRST'}: raise ValueError('Unknown ambiguity convention')
    n=len(frame); idx=frame.index
    t=pd.to_datetime(frame['bar_open_time'],utc=True).astype('int64').to_numpy()
    available=pd.to_datetime(frame['signal_available_at'],utc=True).astype('int64').to_numpy()
    o,h,l,c=(pd.to_numeric(frame[k],errors='coerce').to_numpy(float) for k in ('open','high','low','close'))
    executable=frame.market_executable.to_numpy(bool)
    side=np.asarray(side,float); tp=np.asarray(tp_price,float); sl=np.asarray(sl_price,float)
    bias=frame.get('bias',pd.Series('NEUTRAL',index=idx)).astype(str).str.upper().to_numpy()
    hour=int(pd.Timedelta(hours=1).value)
    # The next executable open. Excessively stale signals are censored.
    exec_idx=np.flatnonzero(executable)
    entry_idx=np.full(n,n,dtype=int)
    if len(exec_idx):
        pos=np.searchsorted(t[exec_idx],available,side='left')
        ok=pos<len(exec_idx)
        entry_idx[ok]=exec_idx[pos[ok]]
    safe=np.minimum(entry_idx,max(0,n-1))
    entry=o[safe]; start=t[safe]
    usable=(entry_idx<n)&executable&(side!=0)&np.isfinite(tp)&np.isfinite(sl)
    usable &= (start>=available)&(start-available<=p.max_signal_age_minutes*60*10**9)
    usable &= side*(tp-entry)>0; usable &= side*(entry-sl)>0
    deadlines=start+p.max_hold_hours*hour
    # Proactive flatten at the start of the final executable H1 bar before closure.
    if p.flatten_before_closure:
        local=pd.DatetimeIndex(pd.to_datetime(start,utc=True)).tz_convert('America/New_York')
        naive=local.tz_localize(None)
        days=(4-local.dayofweek)%7
        close_naive=naive.normalize()+pd.to_timedelta(days,unit='D')+pd.Timedelta(hours=17)
        past=close_naive<=naive
        close_naive=close_naive+pd.to_timedelta(np.where(past,7,0),unit='D')
        closures=close_naive.tz_localize('America/New_York').tz_convert('UTC').astype('int64').to_numpy()
        deadlines=np.where(closures<=deadlines,closures-hour,deadlines)
    outcomes=np.full(n,'CENSORED',object); net=np.full(n,np.nan); at=np.full(n,np.nan)
    tp_at=np.full(n,np.nan); ambiguous=np.zeros(n,bool); gap=np.zeros(n,bool)
    integrity=usable.copy(); finished=np.zeros(n,bool); rebounded=np.zeros(n,bool)
    seen_sl=np.zeros(n,bool)
    for step in range(p.max_hold_hours+1):
        j=entry_idx+step; inside=j<n; js=np.minimum(j,max(0,n-1))
        expected=start+step*hour
        active=usable & (expected<=deadlines)
        # A scheduled open is required at every point; NY-closed endpoints
        # have already been moved to the final pre-closure open.
        valid=inside & executable[js] & (t[js]==expected)
        integrity &= (~active | valid)
        now=active & valid
        timeout=now & (expected==deadlines)
        bias_flip=np.zeros(n,bool)
        if bias_exit and step>0:
            prev=np.maximum(js-1,0)
            direction=np.where(bias[prev]=='BUY',1,np.where(bias[prev]=='SELL',-1,0))
            bias_flip=now & (side!=direction)
        early=now & ~finished & (timeout|bias_flip)
        outcomes[early]=np.where(timeout[early],'TIMEOUT','BIAS')
        net[early]=side[early]*(o[js[early]]-entry[early])/0.0001  # replace pip vector below
        at[early]=(expected[early]-start[early])/hour
        finished |= early
        path=now & (expected+hour<=deadlines)
        tp_touch=path & np.where(side>0,h[js]>=tp,l[js]<=tp)
        sl_touch=path & np.where(side>0,l[js]<=sl,h[js]>=sl)
        # Opening gaps have known order before the H1 range.
        tp_gap=path & (side*(o[js]-tp)>=0)
        sl_gap=path & (side*(sl-o[js])>=0)
        both=tp_touch&sl_touch & ~tp_gap & ~sl_gap
        ambiguous |= both & ~finished
        wins=(tp_gap | (tp_touch & ~sl_gap & (~sl_touch | (ambiguity=='TP_FIRST')))) & ~finished
        losses=(sl_gap | (sl_touch & ~tp_gap & (~tp_touch | (ambiguity=='SL_FIRST')))) & ~finished & ~wins
        outcomes[wins]='TP'; net[wins]=side[wins]*(tp[wins]-entry[wins])/0.0001
        # Stops gap at first executable open; TP is conservatively paid at its price.
        stop_price=np.where(sl_gap,o[js],sl)
        outcomes[losses]='SL'; net[losses]=side[losses]*(stop_price[losses]-entry[losses])/0.0001
        gap |= losses & sl_gap
        exits=wins|losses
        at[exits]=(expected[exits]+hour-start[exits])/hour
        tp_at[wins]=at[wins]
        rebounded |= tp_touch & seen_sl
        seen_sl |= sl_touch
        finished |= exits
    pip=frame.get('pip_size',pd.Series(.0001,index=idx)).to_numpy(float)
    net=net*.0001/pip-p.costs
    # The endpoint open is known only once its H1 source record is complete.
    # Delay release one extra hour so a full frame and a completed-bar prefix
    # use identical evidence, including timeout prices and endpoint integrity.
    release=start+(p.max_hold_hours+1)*hour
    # Never train on the tail or on an incomplete interval after an early win.
    integrity &= release<= (t[-1]+hour if n else 0)
    integrity &= finished
    outcomes[~integrity]='CENSORED'; net[~integrity]=np.nan; at[~integrity]=np.nan
    return pd.DataFrame({'outcome':outcomes,'net_pips':net,'hold_hours':at,'tp_reach_hours':tp_at,
        'ambiguous':ambiguous,'stop_gap':gap,'stop_then_rebound':rebounded,
        'entry_at':pd.to_datetime(start,utc=True),'label_available_at':pd.to_datetime(release,utc=True),
        'label_complete':integrity,'fill_resolution':'H1_OHLC_'+ambiguity},index=idx)


def causal_empirical_forecast(frame,labels,*,policy=None,training_end='2025-01-01T00:00:00Z'):
    """Estimate the actual adjusted pair policy by side/regime using matured labels.

    This is an empirical estimator, not a calibrated classifier. Training freezes
    before 2025; validation/2026 labels cannot update live estimates by default.
    """
    p=policy or get_policy(); idx=frame.index; n=len(frame)
    available=pd.to_datetime(frame.signal_available_at,utc=True)
    release=pd.to_datetime(labels.label_available_at,utc=True)
    cutoff=pd.Timestamp(training_end) if training_end else None
    regime=frame.get('regime_family',pd.Series('TRANSITION',index=idx)).astype(str)
    direction=frame.bias.astype(str)
    key=direction+'|'+regime
    family=frame.get('strategy_family_key',pd.Series('UNSPECIFIED',index=idx)).astype(str)
    volatility=frame.get('volatility_bucket',pd.Series('UNSPECIFIED',index=idx)).astype(str)
    key=key+'|'+family+'|'+volatility
    names=['expected_net_pips','expected_net_pips_lower_bound','forecast_sample_count',
        'p_tp','p_sl','p_bias','p_timeout','expected_reach_hours','reach_p25_hours','reach_p75_hours',
        'p_tp_4h','p_tp_8h','p_tp_12h','p_tp_18h','p_tp_24h']
    result=pd.DataFrame(np.nan,index=idx,columns=names)
    limit=available.where(available.le(cutoff),cutoff) if cutoff is not None else available
    good=labels.label_complete & labels.net_pips.notna()
    for group,targets in key.groupby(key,sort=False).groups.items():
        origins=key.index[(key==group)&good]
        if len(origins)==0:
            result.loc[targets,'forecast_sample_count']=0
            continue
        history=labels.loc[origins].sort_values('label_available_at',kind='mergesort')
        value=history.net_pips
        rolling=value.rolling(240,min_periods=1)
        stats=pd.DataFrame(index=history.index)
        stats['forecast_sample_count']=rolling.count()
        stats['expected_net_pips']=rolling.mean()
        stats['expected_net_pips_lower_bound']=rolling.mean()-1.96*rolling.std()/np.sqrt(rolling.count())
        for outcome in EXITS:
            stats['p_'+outcome.lower()]=history.outcome.eq(outcome).astype(float).rolling(240,min_periods=1).mean()
        reach=history.tp_reach_hours.where(history.outcome.eq('TP'))
        rr=reach.rolling(240,min_periods=1)
        stats['expected_reach_hours']=rr.mean();stats['reach_p25_hours']=rr.quantile(.25);stats['reach_p75_hours']=rr.quantile(.75)
        for h in (4,8,12,18,24): stats[f'p_tp_{h}h']=(history.outcome.eq('TP')&history.tp_reach_hours.le(h)).astype(float).rolling(240,min_periods=1).mean()
        small=stats.forecast_sample_count.lt(p.min_samples)
        stats.loc[small,[c for c in names if c!='forecast_sample_count']]=np.nan
        positions=np.searchsorted(pd.to_datetime(history.label_available_at,utc=True).astype('int64').to_numpy(),limit.loc[targets].astype('int64').to_numpy(),side='right')-1
        ready=positions>=0
        result.loc[targets,'forecast_sample_count']=0
        result.loc[np.asarray(targets)[ready],names]=stats[names].to_numpy()[positions[ready]]
    result['probability_calibration_version']='EMPIRICAL_FINAL_POLICY_UNCALIBRATED'
    result['direction_probability']=np.nan
    result['forecast_training_end']=training_end
    return result
