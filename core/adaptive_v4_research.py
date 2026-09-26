"""Research gates for v4; no weight changes are approved without out-of-sample evidence."""
from __future__ import annotations
import numpy as np
import pandas as pd
from core.middle_regime_adaptive_v4 import VERSION, FAMILIES, build_adaptive_audit, pip_size


def settle_closed_bars(frame, audit, symbol, horizon=24):
    """Conservative TP/SL event outcomes; no concurrent entries in one symbol."""
    rows=[]; next_free=0; p=pip_size(symbol)
    for i in range(len(frame)):
        if i<next_free or audit.iloc[i]['V4 Direction'] not in ('BUY','SELL'): continue
        signal=audit.iloc[i]; sign=1 if signal['V4 Direction']=='BUY' else -1
        entry=float(frame.iloc[i]['close']); tp=float(signal['Suggested TP Price']);sl=float(signal['Suggested SL Price'])
        if i+1>=len(frame): break
        reason='HORIZON'; last=min(len(frame)-1,i+horizon); exit_price=float(frame.iloc[last]['close'])
        for j in range(i+1,last+1):
            bar=frame.iloc[j]; stop=(bar['low']<=sl if sign==1 else bar['high']>=sl)
            target=(bar['high']>=tp if sign==1 else bar['low']<=tp)
            if stop or target:
                exit_price=sl if stop else tp;reason='SL' if stop else 'TP';last=j;break
        rows.append({'Symbol':symbol,'Entry Time':frame.iloc[i]['open_time'], 'Entry Hour':pd.Timestamp(frame.iloc[i]['open_time']).hour,
                     'Market Regime':signal['Market Regime'],'Strategy Family':signal['Strategy Family'],
                     'Direction':signal['V4 Direction'],'Exit Reason':reason,'Holding Bars':last-i,
                     'Net Pip':sign*(exit_price-entry)/p})
        next_free=last+1
    return pd.DataFrame(rows)


def metrics(trades):
    if trades.empty: return {'trades':0,'wins':0,'losses':0,'win_rate':0.,'net_pip':0.,'max_drawdown':0.,'profit_factor':0.}
    pnl=trades['Net Pip'].to_numpy(float);equity=np.r_[0,pnl.cumsum()]
    wins=pnl[pnl>0].sum();loss=-pnl[pnl<0].sum()
    return {'trades':len(pnl),'wins':int((pnl>0).sum()),'losses':int((pnl<0).sum()),
            'win_rate':round(float((pnl>0).mean()),3),'net_pip':round(float(pnl.sum()),2),
            'max_drawdown':round(float((np.maximum.accumulate(equity)-equity).max()),2),
            'profit_factor':round(float(wins/loss),3) if loss else None}


def analyze_trades(trades):
    if trades.empty:return {'status':'INSUFFICIENT_TRADES','metrics':metrics(trades)}
    data=trades.sort_values('Entry Time').reset_index(drop=True)
    split=max(1,int(len(data)*.7));train=data.iloc[:split];unseen=data.iloc[split:]
    rng=np.random.default_rng(40926); p=data['Net Pip'].to_numpy(float)
    mc=[]
    for _ in range(300):
        shuffled=rng.permutation(p);path=np.r_[0,shuffled.cumsum()]
        mc.append(float((np.maximum.accumulate(path)-path).max()))
    def groups(key):
        return {str(k):metrics(g) for k,g in data.groupby(key)}
    return {'version':VERSION,'status':'RESEARCH_ONLY','all':metrics(data),'train':metrics(train),
        'unseen':metrics(unseen),'monte_carlo_drawdown_p95':round(float(np.percentile(mc,95)),2),
        'symbol_removal':{str(s):metrics(data.loc[data.Symbol.ne(s)]) for s in data.Symbol.unique()},
        'by_symbol':groups('Symbol'),'by_family':groups('Strategy Family'),
        'by_regime':groups('Market Regime'),'by_hour_utc':groups('Entry Hour'),
        'large_losses':data.nsmallest(min(10,len(data)),'Net Pip')[['Symbol','Entry Time','Net Pip','Strategy Family']].astype(str).to_dict('records')}


def approval_gate(baseline, candidate, min_unseen=20):
    """Reject training-only gains. Inputs are trade frames from identical periods.

    Sensitivity requires a third nearby-parameter run; fail closed if absent.
    """
    required=('walk_forward','unseen','sensitivity')
    if any(k not in candidate for k in required):return False,'Missing walk-forward, unseen or sensitivity runs'
    unseen=candidate['unseen'];base=baseline.get('unseen',{})
    if unseen.get('trades',0)<min_unseen:return False,'Insufficient unseen trades'
    if unseen.get('net_pip',0)<=base.get('net_pip',0) or unseen.get('max_drawdown',float('inf'))>base.get('max_drawdown',0):return False,'Unseen net pip or drawdown worsened'
    if any(not x.get('pass',False) for x in (candidate['walk_forward'],candidate['sensitivity'])):return False,'Walk-forward or parameter sensitivity failed'
    if not candidate.get('monte_carlo',{}).get('pass',False) or not candidate.get('symbol_removal',{}).get('pass',False):return False,'Monte Carlo or symbol removal failed'
    return True,'Eligible for forward paper testing; no performance claim'


def compare_candidate(baseline: pd.DataFrame, candidate: pd.DataFrame,
                      sensitivity_variants: list[pd.DataFrame], min_unseen=20):
    """Calculate required gates from chronological settled trade evidence.

    Inputs must come from the same OHLC/cost model and training window. This
    method does not optimize on the unseen period or install a candidate.
    """
    if baseline.empty or candidate.empty or len(sensitivity_variants)<2:
        return {'approved':False,'reason':'Missing baseline, candidate or nearby parameters'}
    for data in (baseline,candidate,*sensitivity_variants):
        if not {'Entry Time','Symbol','Net Pip'}.issubset(data):
            return {'approved':False,'reason':'Missing trade evidence columns'}
    b=baseline.sort_values('Entry Time');c=candidate.sort_values('Entry Time')
    cutoff=pd.to_datetime(b['Entry Time']).quantile(.75)
    def slice_metrics(data, mask):return metrics(data.loc[mask])
    b_unseen=slice_metrics(b,pd.to_datetime(b['Entry Time'])>cutoff)
    c_unseen=slice_metrics(c,pd.to_datetime(c['Entry Time'])>cutoff)
    periods=pd.to_datetime(b['Entry Time']).quantile([.25,.50,.75]).tolist()
    walk=[]
    for left,right in zip(periods[:-1],periods[1:]):
        bm=slice_metrics(b,pd.to_datetime(b['Entry Time']).between(left,right,inclusive='left'))
        cm=slice_metrics(c,pd.to_datetime(c['Entry Time']).between(left,right,inclusive='left'))
        walk.append({'baseline':bm,'candidate':cm,'pass':cm['net_pip']>=bm['net_pip'] and cm['max_drawdown']<=bm['max_drawdown']*1.15})
    symbols=set(b.Symbol)|set(c.Symbol)
    removals=[]
    for symbol in symbols:
        bm=metrics(b.loc[b.Symbol.ne(symbol)]);cm=metrics(c.loc[c.Symbol.ne(symbol)])
        removals.append(cm['net_pip']>=bm['net_pip'] and cm['max_drawdown']<=bm['max_drawdown']*1.15)
    def mc_p95(data):
        pnl=data['Net Pip'].to_numpy(float);rng=np.random.default_rng(40926);draw=[]
        for _ in range(300):
            path=np.r_[0,rng.permutation(pnl).cumsum()]
            draw.append(float((np.maximum.accumulate(path)-path).max()))
        return float(np.percentile(draw,95))
    base_mc=mc_p95(b);cand_mc=mc_p95(c)
    sensitivity=[]
    for variant in sensitivity_variants:
        unseen=slice_metrics(variant,pd.to_datetime(variant['Entry Time'])>cutoff)
        sensitivity.append(unseen['trades']>=min_unseen and unseen['net_pip']>=b_unseen['net_pip'] and unseen['max_drawdown']<=b_unseen['max_drawdown'])
    candidate_gates={'unseen':c_unseen,
        'walk_forward':{'pass':all(x['pass'] for x in walk) and bool(walk)},
        'monte_carlo':{'pass':cand_mc<=base_mc},
        'symbol_removal':{'pass':all(removals) and bool(removals)},
        'sensitivity':{'pass':all(sensitivity)}}
    approved,reason=approval_gate({'unseen':b_unseen},candidate_gates,min_unseen)
    return {'version':VERSION,'approved':approved,'reason':reason,
            'baseline_unseen':b_unseen,'candidate_unseen':c_unseen,
            'walk_forward':walk,'monte_carlo_drawdown_p95':{'baseline':round(base_mc,2),'candidate':round(cand_mc,2)},
            'symbol_removal_pass':removals,'sensitivity_pass':sensitivity}


def fit_candidate_family_weights(training_trades, min_samples=30):
    """Bounded symbol/family proposals using only the supplied training trades."""
    result={}
    if training_trades.empty:return result
    for (symbol,family),part in training_trades.groupby(['Symbol','Strategy Family']):
        if family not in FAMILIES or len(part)<min_samples:continue
        pnl=part['Net Pip'].to_numpy(float)
        # Weight is a score adjustment, never an unbounded probability claim.
        adjustment=float(np.clip(3*np.mean(pnl)/(np.std(pnl)+1e-9),-5,5))
        result.setdefault(str(symbol).upper(),{})[str(family)]=round(adjustment,2)
    return result


def install_approved_profile(weights, review, training_end, effective_from, path=None):
    """Install only an accepted comparison, strictly after its training window."""
    from pathlib import Path
    import json,os,tempfile
    from core.middle_regime_adaptive_v4 import PROFILE_PATH
    if not review.get('approved') or review.get('version')!=VERSION:
        raise ValueError('Candidate did not pass all v4 research gates')
    if pd.Timestamp(effective_from)<=pd.Timestamp(training_end):
        raise ValueError('Profile effective date must follow its training window')
    allowed={str(s).upper():{str(f):float(np.clip(w,-5,5)) for f,w in families.items() if f in FAMILIES}
             for s,families in weights.items()}
    destination=Path(path) if path else PROFILE_PATH
    payload={'engine':VERSION,'approved':True,'training_end':str(training_end),
             'effective_from':str(effective_from),'family_weights':allowed,
             'review':{k:review[k] for k in ('reason','baseline_unseen','candidate_unseen','monte_carlo_drawdown_p95') if k in review}}
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',dir=destination.parent,delete=False,encoding='utf-8') as temp:
        json.dump(payload,temp,indent=2,default=str);name=temp.name
    os.replace(name,destination)
    return destination
