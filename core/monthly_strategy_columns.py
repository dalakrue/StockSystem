"""One stable S column per frozen symbol-month equation: S1 through S240.

The old S1..S125 rules are replaced, not retained. Values are +1/0/-1.
Raw signal columns do not mean that all triggered symbols should be entered.
Use the separate portfolio selection policy to choose at most one per check.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from core import monthly_equations as engine
from core.improved_strategy_config import GOOD_HOURS as _GOOD_HOURS, WORST6_REMOVED as _WORST6

ROOT=Path(__file__).resolve().parent
STRATEGY_COLUMNS=[f'S{i}' for i in range(1,241)]

def load_mapping():
    rows=json.loads((ROOT/'equation_column_map.json').read_text())
    assert len(rows)==240 and [q['column'] for q in rows]==STRATEGY_COLUMNS
    assert len({(q['symbol'],q['month']) for q in rows})==240
    return rows

def evaluate_check_columns(candles_by_symbol,check_time,entry_quotes=None,held_symbols=(),strict_only=False):
    """20 symbol rows, 240 fixed strategy columns, metadata and one selected signal.

    If entry_quotes is omitted this is an indication-only calculation. Executable
    live entry requires an actual quote; no future historical open is substituted.
    """
    t=pd.Timestamp(check_time)
    if t.tzinfo is None:raise ValueError('check_time must include timezone')
    month=t.tz_convert('Asia/Rangoon').month
    eqs=engine.load_equations()
    mapping=load_mapping()
    bykey={(q['symbol'],q['month']):q for q in eqs}
    column_bykey={(q['symbol'],q['month']):q['column'] for q in mapping}
    symbols=sorted({q['symbol'] for q in mapping})
    values=np.zeros((len(symbols),240),dtype=np.int8)
    metadata=[];signals=[]
    for i,symbol in enumerate(symbols):
        q=bykey[(symbol,month)]
        price=entry_quotes.get(symbol) if entry_quotes is not None else None
        candidate=None
        if symbol in candles_by_symbol and (entry_quotes is None or price is not None):
            candidate=engine.evaluate_symbol(symbol,candles_by_symbol[symbol],t,price,eqs,strict_only)
        if candidate:
            column=column_bykey[(symbol,month)]
            values[i,int(column[1:])-1]=candidate['side']
            candidate['strategy_column']=column
            signals.append(candidate)
        metadata.append(dict(Symbol=symbol,Month=month,Active_Column=column_bykey[(symbol,month)],Equation_ID=q['id'],Pip_Check='YES',Strict_Valid='NO',Direction=candidate['direction'] if candidate else 'WAIT',TP_Price=candidate.get('tp_price') if candidate else None,SL_Price=candidate.get('sl_price') if candidate else None))
    table=pd.concat([pd.DataFrame(metadata),pd.DataFrame(values,columns=STRATEGY_COLUMNS)],axis=1)
    assert (np.count_nonzero(values,axis=1)<=1).all()
    return dict(table=table,candidates=signals,selected=engine.choose_one(signals,held_symbols))

def build_replay_columns(raw_frame,strict_only=False):
    """Preserve every raw OHLC row and add 240 causal raw signal columns.

    Datetime labels the prospective replay FILL bar, not the signal candle.
    At an allowed half-hour check, the replay fill is the next H1 open. Indicators
    use the bar two indices earlier, which closed before that check. No future
    price is used to construct the signal. Off-session/non-check rows are zero.
    Holding limits, portfolio admission and exits belong to the trade simulator.
    """
    raw=raw_frame.copy()
    raw['Datetime']=pd.to_datetime(raw.Datetime,utc=True,format='mixed').dt.tz_localize(None)
    raw=raw.sort_values(['Symbol','Datetime']).reset_index(drop=True)
    if raw.duplicated(['Symbol','Datetime']).any():raise ValueError('Duplicate symbol/timestamp')
    old=[c for c in raw.columns if c.startswith('S') and c[1:].isdigit()]
    raw=raw.drop(columns=old)
    values=np.zeros((len(raw),240),dtype=np.int8)
    mapping=load_mapping()
    eqs=engine.load_equations()
    eq_bykey={(q['symbol'],q['month']):q for q in eqs}
    col_bykey={(q['symbol'],q['month']):int(q['column'][1:])-1 for q in mapping}
    for symbol,original in raw.groupby('Symbol',sort=True):
        if (symbol,1) not in eq_bykey:continue
        # Validated config: removed symbols produce no signal anywhere.
        if str(symbol).upper().replace('/','') in _WORST6:continue
        g=engine.session_filter(original)
        if len(g)<123:continue
        f=engine.make_features(g)
        shifted=f[engine.ALL_FEATURES].shift(2)
        bias=f.bias.shift(2).fillna(0).to_numpy()
        utc_check=g.Datetime-pd.Timedelta(minutes=30)
        local=utc_check.dt.tz_localize('UTC').dt.tz_convert('Asia/Rangoon')
        # Improved strategy config: checks at 06,07,10,11,12,13 UTC (check_at
        # carries minute 30); weekends excluded. Rangoon month still selects
        # the frozen equation.
        utc=utc_check.dt.tz_localize('UTC')
        check_allowed=(utc.dt.dayofweek<5)&utc.dt.hour.isin(list(_GOOD_HOURS))&utc.dt.minute.eq(30)&utc.dt.second.eq(0)
        continuous=g.Datetime-g.Datetime.shift(2)==pd.Timedelta(hours=2)
        allowed=check_allowed.to_numpy() & continuous.to_numpy() & (np.arange(len(g))>=122)
        availability_bound=(g.Datetime+pd.Timedelta(hours=1)).astype('int64').to_numpy()
        for availability in ['bar_close_time','signal_available_at']:
            if availability in g:
                known=pd.to_datetime(g[availability],utc=True,format='mixed',errors='coerce').dt.tz_localize(None).shift(2)
                allowed &= (known.notna() & (known<=utc_check)).to_numpy()
                supplied=pd.to_datetime(g[availability],utc=True,format='mixed',errors='coerce')
                bound=supplied.astype('int64').to_numpy().copy()
                bound[supplied.isna().to_numpy()]=np.iinfo(np.int64).max
                availability_bound=np.maximum(availability_bound,bound)
        indices=pd.DatetimeIndex(original.Datetime).get_indexer(g.Datetime)
        assert (indices>=0).all()
        positions=original.index.to_numpy()[indices]
        pip=.01 if symbol.endswith('JPY') else .0001
        atr=f.atr.shift(2).to_numpy()/pip
        for month in range(1,13):
            q=eq_bykey[(symbol,month)]
            if strict_only and not q.get('strict_valid',False):continue
            sig=engine.signal_array(shifted,bias,q['rule'])
            e=q['exit']
            tp=np.full(len(g),e['tp']) if e['fixed'] else np.clip(e['tp']*atr,5,500)
            sl=np.full(len(g),e['sl']) if e['fixed'] else np.clip(e['sl']*atr,5,103)
            active=allowed & (local.dt.month.to_numpy()==month) & (tp-1.0>=.5*sl)
            values[positions,col_bykey[(symbol,month)]]=np.where(active,sig,0).astype(np.int8)
        prefix=np.maximum.accumulate(availability_bound)
        late=np.r_[False,False,prefix[:-2]>utc_check.astype('int64').to_numpy()[2:]]
        for i in np.flatnonzero(check_allowed.to_numpy() & late & (np.arange(len(g))>=122)):
            candidate=engine.evaluate_symbol(symbol,original,utc_check.iloc[i].tz_localize('UTC'),equations=eqs,strict_only=strict_only)
            values[positions[i],:]=0
            if candidate:
                values[positions[i],col_bykey[(symbol,int(local.iloc[i].month))]]=candidate['side']
    assert (np.count_nonzero(values,axis=1)<=1).all()
    return pd.concat([raw,pd.DataFrame(values,columns=STRATEGY_COLUMNS)],axis=1)
