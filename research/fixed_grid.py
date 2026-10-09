"""Compiled exhaustive integer fixed-grid replay with independent holdings.

This is the NEW engine's signal universe. Reproducing a legacy training winner
requires the original decision candidates/policy, not substituting this search.
Grid search is research-only and intentionally tests stops above the live budget.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from numba import njit
from core.execution_policy_20261003 import checks_between,latest_completed,closure_deadline
from core.audited_portfolio_replay_20261003 import normalize_quotes

@njit(cache=True)
def _grid(candidates,checks,entries,opens,highs,lows,ends,sides,timeouts,costs,nsymbols,lo,hi):
    size=(hi-lo+1)**2;result=np.empty((size,7));z=0
    for tp in range(lo,hi+1):
        for sl in range(lo,hi+1):
            held=np.full(nsymbols,-np.inf);net=0.;trades=0;wins=0;profit=0.;loss=0.
            for c in range(len(checks)):
                entered=0
                for slot in range(4):
                    sym=candidates[c,slot]
                    if sym<0 or held[sym]>checks[c] or entered>=2: continue
                    payout=np.nan;exit_at=np.inf
                    for step in range(25):
                        t=ends[c,slot,step]
                        if t<0: break
                        if step==timeouts[c,slot]: payout=opens[c,slot,step]-costs;exit_at=t;break
                        # Adverse opening gap fills are observable before intrabar ranges.
                        if opens[c,slot,step]<=-sl:
                            payout=opens[c,slot,step]-costs;exit_at=t-3600;break
                        if opens[c,slot,step]>=tp:
                            payout=tp-costs;exit_at=t-3600;break
                        hit_tp=highs[c,slot,step]>=tp;hit_sl=lows[c,slot,step]<=-sl
                        # Primary table TP-first; separate stress uses full runner.
                        if hit_tp: payout=tp-costs;exit_at=t;break
                        if hit_sl: payout=-sl-costs;exit_at=t;break
                    held[sym]=exit_at;entered+=1
                    if np.isfinite(payout):
                        net+=payout;trades+=1
                        if payout>0:wins+=1;profit+=payout
                        else:loss-=payout
            result[z]=np.array([tp,sl,net,trades,wins,profit,loss]);z+=1
    return result


def exhaustive_search(signals,raw,policy,start,end,lo=10,hi=500):
    if hi<lo:raise ValueError('Invalid integer range')
    q=normalize_quotes(raw);syms=sorted(q.Symbol.unique());ids={s:i for i,s in enumerate(syms)}
    checks=checks_between(start,end,policy);shape=(len(checks),4,25)
    candidates=np.full((len(checks),4),-1,np.int64);entries=np.full((len(checks),4),np.nan)
    opens=np.full(shape,np.nan);highs=np.full(shape,np.nan);lows=np.full(shape,np.nan);ends=np.full(shape,-1.,float)
    sides=np.zeros((len(checks),4));timeouts=np.full((len(checks),4),24,np.int64)
    groups={s:g.loc[g.market_executable].sort_values('bar_open_time') for s,g in q.groupby('Symbol')}
    for k,check in enumerate(checks):
        snapshot=latest_completed(signals,check,policy)
        snapshot['_ev']=pd.to_numeric(snapshot.expected_net_pips,errors='coerce').fillna(-np.inf)
        snapshot=snapshot.sort_values(['unique_family_count','_ev','Symbol'],ascending=[False,False,True]).head(4)
        for slot,(_,signal) in enumerate(snapshot.iterrows()):
            if not signal.research_entry_eligible or signal.entry_origin=='RANK_FILL':continue
            bars=groups[signal.Symbol].loc[groups[signal.Symbol].bar_open_time.ge(check)].head(25)
            if bars.empty:continue
            entry_at=bars.iloc[0].bar_open_time
            if (entry_at-check).total_seconds()/60>policy.max_signal_age_minutes:continue
            deadline,closed=closure_deadline(entry_at,24)
            if closed:deadline-=pd.Timedelta(hours=1)
            else:deadline=entry_at+pd.Timedelta(hours=24)
            price=bars.iloc[0].open;side=1 if signal.entry_side=='BUY' else -1;pip=.01 if 'JPY' in signal.Symbol else .0001
            candidates[k,slot]=ids[signal.Symbol];entries[k,slot]=entry_at.timestamp();sides[k,slot]=side
            timeouts[k,slot]=int((deadline-entry_at).total_seconds()/3600)
            for j,(_,bar) in enumerate(bars.iterrows()):
                if bar.bar_open_time!=entry_at+pd.Timedelta(hours=j):break
                if bar.bar_open_time>deadline:break
                opens[k,slot,j]=side*(bar.open-price)/pip
                highs[k,slot,j]=side*((bar.high if side>0 else bar.low)-price)/pip
                lows[k,slot,j]=side*((bar.low if side>0 else bar.high)-price)/pip
                ends[k,slot,j]=(bar.bar_open_time if bar.bar_open_time==deadline else bar.bar_close_time).timestamp()
    values=_grid(candidates,np.array([x.timestamp() for x in checks]),entries,opens,highs,lows,ends,sides,timeouts,policy.costs,len(syms),lo,hi)
    out=pd.DataFrame(values,columns=['TP','SL','Net Pip','Trades','Wins','Gross Profit','Gross Loss'])
    out['EV']=out['Net Pip']/out.Trades.replace(0,np.nan);out['Profit Factor']=out['Gross Profit']/out['Gross Loss'].replace(0,np.nan)
    return out.sort_values(['Net Pip','TP','SL'],ascending=[False,True,True],kind='mergesort').reset_index(drop=True)
