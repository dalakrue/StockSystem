"""Frozen monthly research signals. No fitting, broker connection or order sending.

Historical-positive is a retrospective performance flag, not unseen validation.
All indicators use completed executable H1 bars in chronological order.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from core.improved_strategy_config import GOOD_HOURS as _GOOD_HOURS

BASE_FEATURES = ['r1','r3','r6','r12','r24','body','range_atr','ema_gap',
                 'ema_dist','pos24','breakout24','seq3','accel','vol_ratio',
                 'wick_low','wick_high','middle_score']
EXTRA_FEATURES = ['haar4','haar8','haar16','haar32','wave_accel','eff12',
                  'eff24','atr_ratio','ordinal4']
ALL_FEATURES = BASE_FEATURES + EXTRA_FEATURES

def session_filter(frame):
    g = frame.copy()
    g['Datetime'] = pd.to_datetime(g['Datetime'], utc=True, format='mixed').dt.tz_localize(None)
    g = g.sort_values('Datetime').reset_index(drop=True)
    if g.Datetime.duplicated().any():
        raise ValueError('Duplicate H1 timestamps for one symbol')
    ny = g.Datetime.dt.tz_localize('UTC').dt.tz_convert('America/New_York')
    w, h = ny.dt.dayofweek, ny.dt.hour
    mask = (w < 4) | ((w == 4) & (h < 17)) | ((w == 6) & (h >= 17))
    if 'market_executable' in g:
        mask &= g.market_executable.astype(str).str.lower().eq('true')
    valid=np.isfinite(g[['Open','High','Low','Close']]).all(axis=1) & g[['Open','High','Low','Close']].gt(0).all(axis=1)
    valid &= g.High.ge(g[['Open','Low','Close']].max(axis=1)) & g.Low.le(g[['Open','High','Close']].min(axis=1))
    return g.loc[mask & valid].reset_index(drop=True)

def make_features(frame):
    g = frame.copy()
    c,o,hi,lo = g.Close,g.Open,g.High,g.Low
    tr = pd.concat([hi-lo,(hi-c.shift()).abs(),(lo-c.shift()).abs()],axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    for k in [1,3,6,12,24]:
        g['r'+str(k)] = (c-c.shift(k))/atr
    g['body']=(c-o)/atr
    g['range_atr']=(hi-lo)/atr
    e12=c.ewm(span=12,adjust=False).mean()
    e48=c.ewm(span=48,adjust=False).mean()
    g['ema_gap']=(e12-e48)/atr
    g['ema_dist']=(c-e12)/atr
    low24,high24=lo.rolling(24).min(),hi.rolling(24).max()
    g['pos24']=(c-low24)/(high24-low24)
    ph,pl=hi.rolling(24).max().shift(),lo.rolling(24).min().shift()
    g['breakout24']=np.where(c>ph,(c-ph)/atr,np.where(c<pl,(c-pl)/atr,0))
    g['seq3']=np.sign(c-o).rolling(3).sum()
    g['accel']=g.r3-g.r3.shift(3)
    ret=c.pct_change()
    g['vol_ratio']=ret.rolling(6).std()/ret.rolling(48).std()
    g['wick_low']=(pd.concat([o,c],axis=1).min(axis=1)-lo)/(hi-lo)
    g['wick_high']=(hi-pd.concat([o,c],axis=1).max(axis=1))/(hi-lo)
    score=.72*((c.ewm(span=24,adjust=False).mean()-c.ewm(span=60,adjust=False).mean())/tr.ewm(span=40,adjust=False).mean()).fillna(0)+.28*(c.pct_change(40)/(ret.rolling(60,min_periods=5).std()*np.sqrt(40))).fillna(0)
    g['middle_score']=score
    g['bias']=np.where(score>.18,1,np.where(score<-.18,-1,0))
    g['atr']=atr
    for k in [4,8,16,32]:
        half=k//2
        g['haar'+str(k)]=(c.rolling(half).mean()-c.shift(half).rolling(half).mean())/atr
    g['wave_accel']=g.haar4-g.haar16
    for k in [12,24]:
        g['eff'+str(k)]=(c-c.shift(k)).abs()/c.diff().abs().rolling(k).sum()
    g['atr_ratio']=atr/tr.rolling(56).mean()
    def ordinal(v):
        return float(np.dot(np.argsort(v,kind='stable'),[1,4,16,64]))
    g['ordinal4']=c.rolling(4).apply(ordinal,raw=True)
    return g

def rule_mask(features, rule):
    x=features
    kind=rule['kind']
    if kind=='conditions':
        result=np.ones(len(x),bool)
        for f,op,value in rule['conditions']:
            v=x[f].to_numpy()
            if op=='>':result &= v>value
            elif op=='<':result &= v<value
            elif op=='<=':result &= v<=value
            elif op=='>=':result &= v>=value
            elif op=='==':result &= v==value
            else:raise ValueError(op)
        needed=[f for f,_,_ in rule['conditions']]
    elif kind=='linear':
        needed=BASE_FEATURES
        result=(x[needed].to_numpy()@np.asarray(rule['coef'])+rule['intercept'])>rule['threshold']
    elif kind=='cluster':
        needed=BASE_FEATURES
        z=(x[needed].to_numpy()-np.array(rule['mean']))/np.array(rule['scale'])
        dist=np.sum((z[:,None,:]-np.array(rule['centers'])[None,:,:])**2,axis=2)
        result=np.argmin(dist,axis=1)==rule['cluster']
    elif kind=='rbf':
        needed=rule['features']
        z=(x[needed].to_numpy()-np.array(rule['mean']))/np.array(rule['scale'])
        dist=np.sum((z[:,None,:]-np.array(rule['centers'])[None,:,:])**2,axis=2)
        prediction=np.exp(-dist/(2*rule['bandwidth']**2))@np.array(rule['weights'])+rule['intercept']
        result=rule['side']*prediction>rule['threshold']
    elif kind=='quadratic':
        needed=rule['features']
        z=(x[needed].to_numpy()-np.array(rule['mean']))/np.array(rule['scale'])
        score=np.einsum('ni,ij,nj->n',z,np.array(rule['matrix']),z)+z@np.array(rule['linear'])+rule['intercept']
        result=rule['side']*score>rule['threshold']
    else:raise ValueError(kind)
    # Original rules required every original feature finite, including cluster coordinates.
    finite=np.isfinite(x[list(dict.fromkeys(BASE_FEATURES+needed))].to_numpy()).all(axis=1)
    return result & finite

def signal_array(features,bias,rule):
    return np.ascontiguousarray(np.where(rule_mask(features,rule)&(np.asarray(bias)==rule['side']),rule['side'],0),dtype=float)

def load_equations(path=None):
    path=Path(path) if path else Path(__file__).with_name('historical_positive_equations.json')
    return json.loads(path.read_text())['equations']

def evaluate_symbol(symbol,candles,check_time,entry_price=None,equations=None,strict_only=False):
    """Evaluate at an aware UTC check time using bars already closed.

    Checks run at minute 30 of the validated UTC hours; the frozen equation
    is still selected by Rangoon month. Optional entry_price must be an actual
    quote at the intended entry. The research replay used the next H1 open
    because half-hour quotes were absent. Returns a signal dictionary or
    None. It never places an order.
    """
    symbol=symbol.upper()
    t=pd.Timestamp(check_time)
    if t.tzinfo is None:raise ValueError('check_time must include timezone')
    # Validated config: removed symbols never produce a signal.
    from core.improved_strategy_config import WORST6_REMOVED
    if symbol.replace('/','') in WORST6_REMOVED:return None
    local=t.tz_convert('Asia/Rangoon')
    utc=t.tz_convert('UTC')
    # Validated schedule: 06,07,10,11,12,13 UTC at minute 30, weekdays only.
    if utc.second or utc.microsecond or utc.dayofweek>=5 or utc.minute!=30 or int(utc.hour) not in _GOOD_HOURS:return None
    eqs=load_equations() if equations is None else equations
    q=next((q for q in eqs if q['symbol']==symbol and q['month']==local.month),None)
    if q is None or (strict_only and not q.get('strict_valid',False)):return None
    data=candles.loc[candles.Symbol.eq(symbol)].copy() if 'Symbol' in candles else candles.copy()
    utc=t.tz_convert('UTC').tz_localize(None)
    data['Datetime']=pd.to_datetime(data['Datetime'],utc=True,format='mixed').dt.tz_localize(None)
    data=data.loc[data.Datetime+pd.Timedelta(hours=1)<=utc]
    for availability in ['bar_close_time','signal_available_at']:
        if availability in data:
            available=pd.to_datetime(data[availability],utc=True,format='mixed',errors='coerce').dt.tz_localize(None)
            data=data.loc[available.notna() & (available<=utc)]
    g=session_filter(data)
    if len(g)<121:return None  # researched replay fill index >=122 uses completed signal index >=120
    last=g.Datetime.iloc[-1]
    expected=utc.floor('h')-pd.Timedelta(hours=1)
    if last!=expected or last-g.Datetime.iloc[-2]!=pd.Timedelta(hours=1):return None
    f=make_features(g)
    row=f.iloc[[-1]]
    sig=signal_array(row,row.bias,q['rule'])[0]
    if not sig:return None
    pip=.01 if symbol.endswith('JPY') else .0001
    e=q['exit']
    tp=e['tp'] if e['fixed'] else float(np.clip(e['tp']*row.atr.iloc[0]/pip,5,500))
    sl=e['sl'] if e['fixed'] else float(np.clip(e['sl']*row.atr.iloc[0]/pip,5,103))
    if tp-1.0<.5*sl:return None  # validated cost model: 1 pip spread
    hold_hours=e['hold']
    # Validated exits: TP=k_tp[month,symbol]xATR14 (clip 10..500), SL=10 fixed,
    # 48h cap. Removed symbols already returned None above.
    from core.improved_strategy_config import USE_DYNAMIC_EXITS, dynamic_tp_sl, MAX_HOLD_HOURS
    if USE_DYNAMIC_EXITS:
        t2,s2=dynamic_tp_sl(t,symbol,row.atr.iloc[0]/pip)
        if t2 is not None:
            tp,sl=t2,s2
            hold_hours=MAX_HOLD_HOURS
            if tp-1.0<.5*sl:return None
    ans=dict(symbol=symbol,equation_id=q['id'],direction='BUY' if sig==1 else 'SELL',side=int(sig),tp_pips=tp,sl_pips=sl,hold_hours=hold_hours,danger=e['danger'],ranking_score=q['ranking_score'],strict_valid=False,performance_label='HISTORICAL POSITIVE; REUSED TEST',signal_bar_open=str(last))
    if entry_price is not None:
        if not np.isfinite(entry_price) or entry_price<=0:
            raise ValueError('entry_price must be a finite positive executable quote')
        ans.update(entry_price=float(entry_price),tp_price=float(entry_price+sig*tp*pip),sl_price=float(entry_price-sig*sl*pip))
    return ans

def choose_one(signals,held_symbols):
    """Rank before excluding held symbols, inspect four, admit at most one."""
    ranked=sorted(signals,key=lambda q:(-q['ranking_score'],q['symbol'],q['equation_id']))[:4]
    held=set(held_symbols)
    return next((q for q in ranked if q['symbol'] not in held),None)

def exit_at_next_open(side,previous_completed_bar,next_open,entry_time,current_time,hold_hours=24,danger=False):
    """Completed-bar bias/danger/holding-cap exit helper; barriers handled separately."""
    if (pd.Timestamp(current_time)-pd.Timestamp(entry_time)).total_seconds()>=hold_hours*3600:
        return ('HOLD_CAP',float(next_open))
    if int(previous_completed_bar['bias'])==-side:return ('BIAS_FLIP',float(next_open))
    if danger and previous_completed_bar['High']-previous_completed_bar['Low']>3*previous_completed_bar['atr'] and side*(previous_completed_bar['Close']-previous_completed_bar['Open'])<-.5*previous_completed_bar['atr']:
        return ('DANGER',float(next_open))
    return None

