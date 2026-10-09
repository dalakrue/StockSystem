"""Application adapter for the frozen H1 equations; never fits or optimizes."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
from core import monthly_equations as engine
from core.monthly_strategy_columns import STRATEGY_COLUMNS, load_mapping, build_replay_columns, evaluate_check_columns
from core import improved_strategy_config as _isc
from core import live_execution as _live_stage2

ROOT = Path(__file__).parent
ENGINE_VERSION = 'monthly-240-v1-' + hashlib.sha256(b''.join((ROOT/n).read_bytes() for n in ('historical_positive_equations.json','equation_column_map.json','monthly_equations.py','monthly_strategy_columns.py','monthly_runtime.py','monthly_backtest.py','monthly_live_book.py','execution_policy_20261003.py','improved_strategy_config.py'))).hexdigest()[:16]
MAPPING = load_mapping()
BY_KEY = {(m['symbol'],m['month']):m for m in MAPPING}
EQUATIONS = {(q['symbol'],q['month']):q for q in engine.load_equations()}
MONTHLY_METADATA = ['Active S Column','Equation ID','Direction','TP Price','SL Price','Target Price Basis','Target Reference Price','Pip_Check','Strict_Valid','ranking_score','check_at','signal_bar_open','signal_at','Signal Mode','Danger Enabled','Equation Month']


def raw_frame(frame, symbol=None):
    """Add canonical aliases without dropping any supplied OHLC or metadata."""
    out = frame.loc[:,~frame.columns.duplicated()].copy().reset_index(drop=True)
    aliases = {'Datetime':('open_time','bar_open_time','Completed Candle','time','timestamp'),
               'Open':('open','Open Price'),'High':('high','Highest Price','High Price'),
               'Low':('low','Lowest Price','Low Price'),'Close':('close','Close Price'),
               'Volume':('volume',)}
    for target, names in aliases.items():
        if target not in out:
            source = next((x for x in names if x in out),None)
            if source: out[target] = out[source]
    if 'Symbol' not in out: out['Symbol'] = symbol or frame.attrs.get('symbol','UNKNOWN')
    out['Symbol'] = out.Symbol.astype(str).str.upper().str.replace(r'[/_ ]','',regex=True)
    if not {'Datetime','Open','High','Low','Close'}.issubset(out): raise ValueError('H1 equations require timestamp and real OHLC')
    out['Datetime'] = pd.to_datetime(out.Datetime,utc=True,format='mixed').dt.tz_localize(None)
    if out.Datetime.isna().any(): raise ValueError('Missing bar-open timestamp')
    for c in ('Open','High','Low','Close'): out[c] = pd.to_numeric(out[c],errors='coerce')
    return out


def decision_text(side, column, eqid, tp, sl):
    """Compact shared display; equation identifiers stay in dedicated columns."""
    if side not in ('BUY','SELL'): return 'None'
    def fmt(x):
        value=pd.to_numeric(x,errors='coerce')
        return f'{float(value):.5f}' if pd.notna(value) and np.isfinite(value) else 'unavailable'
    return f'{side}, TP={fmt(tp)}, SL={fmt(sl)}'


def _metadata(out, *, live=False):
    """Fixed equation metadata, with exact frozen distances and price targets."""
    out = out.copy()
    n=len(out)
    checks=pd.to_datetime(out.get('check_at',out.Datetime-pd.Timedelta(minutes=30)),utc=True,format='mixed')
    months=checks.dt.tz_convert('Asia/Rangoon').dt.month
    rows=[BY_KEY.get((s,int(m))) for s,m in zip(out.Symbol,months)]
    equations=[EQUATIONS.get((s,int(m))) for s,m in zip(out.Symbol,months)]
    out['check_at']=checks
    out['Equation Month']=months.to_numpy()
    out['Active S Column']=[r['column'] if r else '' for r in rows]
    out['Equation ID']=[r['equation_id'] if r else '' for r in rows]
    out['Pip_Check']=['YES' if r else 'n.a.' for r in rows]
    out['Strict_Valid']='NO'
    out['ranking_score']=[q['ranking_score'] if q else 0 for q in equations]
    out['Max Hold Hours']=[q['exit']['hold'] if q else 0 for q in equations]
    out['Time Exit Hours']=out['Max Hold Hours']
    out['Danger Enabled']=[q['exit']['danger'] if q else False for q in equations]
    matrix=out[STRATEGY_COLUMNS].to_numpy(dtype=np.int8)
    side=matrix.sum(axis=1)
    hit=side!=0
    # Improved strategy config: gate every strategy signal by check hour
    # (06,07,10,11,12,13 UTC), worst-6 symbol removal and weekend filter;
    # the validated pair allow-list hooks in here when enabled.
    gate=_isc.gate_signals(out['Symbol'].to_numpy(),checks.dt.hour.to_numpy(),
                           checks.dt.weekday.to_numpy(),
                           out['Active S Column'].astype(str).to_numpy(),
                           np.where(side==1,'BUY',np.where(side==-1,'SELL','WAIT')))
    hit=hit & np.asarray(gate)
    out['Active S Column']=np.where(hit,out['Active S Column'],'')
    out['Equation ID']=np.where(hit,out['Equation ID'],'')
    out['Strategy Hit Count']=hit.astype(np.int8)
    if _isc.USE_DYNAMIC_EXITS:
        # Validated 48h cap overrides the frozen per-equation hold.
        out['Max Hold Hours']=np.where(hit,_isc.MAX_HOLD_HOURS,out['Max Hold Hours']).astype(int)
        out['Time Exit Hours']=out['Max Hold Hours']
    out['unique_family_count']=hit.astype(np.int8)
    out['Direction']=np.where(side==1,'BUY',np.where(side==-1,'SELL','WAIT'))
    out['entry_side']=out.Direction.where(hit,'NONE')
    out['active_strategy_ids']=[json.dumps([c] if h else [],separators=(',',':')) for c,h in zip(out['Active S Column'],hit)]
    out['active_strategy_family_ids']=out.active_strategy_ids
    out['entry_origin']=np.where(hit,'MONTHLY_EQUATION','NONE')
    out['Best Strategy']=out['Active S Column'].where(hit,'NONE')
    out['Best Strategy Score']=out.ranking_score.where(hit,0)
    out['Near Entry Score']=out['Best Strategy Score']
    # Improved ranking: hour+symbol boost replaces Best Strategy Score sort.
    out['Improved Rank']=[_isc.rank_score(s,int(h),r) for s,h,r in zip(out['Symbol'],checks.dt.hour,out['ranking_score'])]
    # Frozen ranking_score is an ordering score, never a probability or EV.
    out['Strategy Engine']=ENGINE_VERSION
    out['decision_engine_version']=ENGINE_VERSION
    out['Signal Mode']='LIVE_INDICATION' if live else 'H1_REPLAY_NEXT_OPEN'
    out['Exit Scenario']=('Dynamic exits (validated): TP=k_tp[month,symbol]xATR14 clip 10..500, SL=10 fixed, '
        'TP-first intrabar, 48h cap, 1 pip spread; opposite completed bias, danger, Friday close retained')
    out['Middle Bias Formula']='Recovered research formula; differs from heavy Middle Standard Regime'
    atr=pd.to_numeric(out.get('Signal ATR',pd.Series(np.nan,index=out.index)),errors='coerce').to_numpy()
    pip=np.where(out.Symbol.str.endswith('JPY'),.01,.0001)
    tp=np.asarray([q['exit']['tp'] if q else np.nan for q in equations],float)
    sl=np.asarray([q['exit']['sl'] if q else np.nan for q in equations],float)
    fixed=np.asarray([q['exit']['fixed'] if q else True for q in equations],bool)
    tp=np.where(fixed,tp,np.clip(tp*atr/pip,5,500))
    sl=np.where(fixed,sl,np.clip(sl*atr/pip,5,103))
    if _isc.USE_DYNAMIC_EXITS:
        # Validated exits: TP = k_tp[month,symbol] x ATR14 (clip 10..500),
        # SL = 10 fixed. Falls back to frozen TP/SL when ATR is missing.
        dyn_tp=np.full(n,np.nan);dyn_sl=np.full(n,np.nan)
        for i in np.flatnonzero(hit):
            a=atr[i]/pip[i]
            if np.isfinite(a):
                t2,s2=_isc.dynamic_tp_sl(checks.iloc[i],out['Symbol'].iloc[i],a)
                if t2 is not None:dyn_tp[i]=t2;dyn_sl[i]=s2
        use=np.isfinite(dyn_tp)
        tp=np.where(use,dyn_tp,tp);sl=np.where(use,dyn_sl,sl)
    out['Suggested TP Pips']=np.where(hit,tp,np.nan)
    out['Suggested SL Pips']=np.where(hit,sl,np.nan)
    if live:
        quote=pd.to_numeric(out.get('Actual Entry Quote',pd.Series(np.nan,index=out.index)),errors='coerce')
        reference=pd.to_numeric(out.get('Completed Signal Close',pd.Series(np.nan,index=out.index)),errors='coerce')
        price=quote.combine_first(reference).to_numpy()
        out['Target Price Basis']=np.where(hit,np.where(quote.notna(),'EXECUTABLE_QUOTE','COMPLETED_CANDLE_CLOSE (INDICATIVE)'),'NONE')
    else:
        price=pd.to_numeric(out.get('Open',pd.Series(np.nan,index=out.index)),errors='coerce').to_numpy()
        out['Target Price Basis']=np.where(hit,'REPLAY_NEXT_H1_OPEN','NONE')
    out['Target Reference Price']=np.where(hit,price,np.nan)
    out['TP Price']=np.where(hit,price+side*tp*pip,np.nan)
    out['SL Price']=np.where(hit,price-side*sl*pip,np.nan)
    for c in ('Suggested TP','Suggested TP Price','tp_price','TP_Price'): out[c]=out['TP Price']
    for c in ('Suggested SL','Suggested SL Price','sl_price','SL_Price'): out[c]=out['SL Price']
    out['TP Price Display']=[f'{v:.5f}' if np.isfinite(v) else '—' for v in out['TP Price']]
    out['SL Price Display']=[f'{v:.5f}' if np.isfinite(v) else '—' for v in out['SL Price']]
    out['research_entry_eligible']=hit
    out['entry_eligible']=False  # all Strict_Valid flags are NO
    out['TP Research Filters Passed']=hit
    out['TP Filters Passed']=False
    out['TP Filter Reasons']='HISTORICAL POSITIVE; REUSED TEST; Strict_Valid=NO'
    out['Entry Quality Passed']=hit
    out['Entry Noise Ratio']=np.nan
    out['Strategy Decision']=[decision_text(d,c,e,t,s) if h else 'None' for d,c,e,t,s,h in zip(out.Direction,out['Active S Column'],out['Equation ID'],out['TP Price'],out['SL Price'],hit)]
    return out


def build_history(frame, symbol=None, timeframe='H1', strict_only=False, audit=False):
    raw=raw_frame(frame,symbol)
    # Do not let obsolete conditions, aliases or targets survive a rebuild.
    raw=raw.drop(columns=[c for c in raw if re.fullmatch(r'S\d+(?: .*)?',str(c))],errors='ignore')
    if str(timeframe).upper() not in ('H1','1H'): raise ValueError('Frozen monthly equations support completed H1 only; raw loading remains available')
    out=build_replay_columns(raw,strict_only=strict_only)
    out['Signal ATR']=np.nan
    out['Research Middle Bias']='NEUTRAL'
    out['signal_bar_open']=pd.NaT
    out['signal_at']=pd.NaT
    for sym,original in out.groupby('Symbol',sort=False):
        g=engine.session_filter(original)
        if g.empty: continue
        f=engine.make_features(g)
        ids=pd.MultiIndex.from_frame(out[['Symbol','Datetime']]).get_indexer(pd.MultiIndex.from_frame(g[['Symbol','Datetime']]))
        out.loc[ids,'Signal ATR']=f.atr.shift(2).to_numpy()
        out.loc[ids,'Research Middle Bias']=np.where(f.bias.shift(2)==1,'BUY',np.where(f.bias.shift(2)==-1,'SELL','NEUTRAL'))
        out.loc[ids,'signal_bar_open']=g.Datetime.shift(2).to_numpy()
        out.loc[ids,'signal_at']=(g.Datetime.shift(2)+pd.Timedelta(hours=1)).to_numpy()
        bounds=(g.Datetime+pd.Timedelta(hours=1)).astype('int64').to_numpy()
        for name in ('bar_close_time','signal_available_at'):
            if name in g:
                supplied=pd.to_datetime(g[name],utc=True,format='mixed',errors='coerce')
                b=supplied.astype('int64').to_numpy().copy();b[supplied.isna().to_numpy()]=np.iinfo(np.int64).max
                bounds=np.maximum(bounds,b)
        check=(g.Datetime-pd.Timedelta(minutes=30)).astype('int64').to_numpy()
        late=np.zeros(len(g),bool)
        if len(g)>2:late[2:]=np.maximum.accumulate(bounds)[:-2]>check[2:]
        hits=out.loc[ids,STRATEGY_COLUMNS].abs().sum(axis=1).to_numpy().astype(bool)
        for i in np.flatnonzero(late & hits):
            utc=g.Datetime.iloc[i]-pd.Timedelta(minutes=30)
            known=g.loc[g.Datetime+pd.Timedelta(hours=1)<=utc]
            for name in ('bar_close_time','signal_available_at'):
                if name in known:known=known.loc[pd.to_datetime(known[name],utc=True,format='mixed').le(utc.tz_localize('UTC'))]
            ff=engine.make_features(known)
            if len(ff):out.loc[ids[i],'Signal ATR']=ff.atr.iloc[-1]
    out=_metadata(out)
    out['Timeframe']=timeframe
    for target,source in (('Open Price','Open'),('Close Price','Close'),('Highest Price','High'),('Lowest Price','Low')): out[target]=out[source]
    out['Completed Candle']=out['signal_bar_open']
    if audit:
        extra={}
        for c in STRATEGY_COLUMNS:
            h=out[c].ne(0)
            extra[f'{c} Entry Condition']=h
            extra[f'{c} Signal']=np.where(out[c]==1,'BUY',np.where(out[c]==-1,'SELL','NO ENTRY'))
            extra[f'{c} Score']=out.ranking_score.where(h,0)
            extra[f'{c} Reason']=np.where(h,'Frozen '+c+' equation triggered','No matching monthly trigger')
        out=pd.concat([out,pd.DataFrame(extra,index=out.index)],axis=1)
    return out


def latest_check(now=None):
    from core.execution_policy_20261003 import checks_between
    t=pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now)
    if t.tzinfo is None: raise ValueError('Check clock must include timezone')
    checks=checks_between(t-pd.Timedelta(days=4),t)
    return checks[-1] if len(checks) else None


def live_table(frames,check_time,quotes=None,strict_only=False):
    normalized={s:raw_frame(f,s).loc[lambda d:d.Symbol.eq(s)].copy() for s,f in frames.items()}
    r=evaluate_check_columns(normalized,check_time,strict_only=strict_only)
    table=r['table'].rename(columns={'Active_Column':'Active S Column','Equation_ID':'Equation ID','Month':'Equation Month'})
    table['Datetime']=pd.Timestamp(check_time).tz_convert('UTC').tz_localize(None)
    table['check_at']=pd.Timestamp(check_time)
    table['Signal ATR']=np.nan
    table['Actual Entry Quote']=np.nan
    table['Completed Signal Close']=np.nan
    table['signal_bar_open']=pd.NaT
    table['signal_at']=pd.NaT
    for c in r['candidates']:
        i=table.index[table.Symbol.eq(c['symbol'])][0]
        data=normalized[c['symbol']]
        utc=pd.Timestamp(check_time).tz_convert('UTC').tz_localize(None)
        known=data.loc[data.Datetime+pd.Timedelta(hours=1)<=utc]
        for name in ('bar_close_time','signal_available_at'):
            if name in known: known=known.loc[pd.to_datetime(known[name],utc=True,format='mixed').le(pd.Timestamp(check_time))]
        completed=engine.session_filter(known)
        f=engine.make_features(completed)
        table.at[i,'Signal ATR']=f.atr.iloc[-1]
        table.at[i,'Completed Signal Close']=float(completed.Close.iloc[-1])
        table.at[i,'signal_bar_open']=pd.Timestamp(c['signal_bar_open'])
        table.at[i,'signal_at']=pd.Timestamp(c['signal_bar_open'])+pd.Timedelta(hours=1)
        if quotes and c['symbol'] in quotes:
            q=quotes[c['symbol']]
            # Only timestamped executable bid/ask evidence can price a live fill.
            if isinstance(q,dict) and q.get('executable') is True:
                try: stamp=pd.Timestamp(q.get('at'))
                except (TypeError,ValueError): stamp=pd.NaT
                bid=pd.to_numeric(q.get('bid'),errors='coerce')
                ask=pd.to_numeric(q.get('ask'),errors='coerce')
                if stamp.tzinfo is not None and stamp==pd.Timestamp(check_time) and pd.notna(bid) and pd.notna(ask) and np.isfinite([bid,ask]).all() and 0<bid<=ask:
                    table.at[i,'Actual Entry Quote']=float(ask if c['side']>0 else bid)
    staged=_metadata(table,live=True)
    # Stage 2 (live execution): Stage 1 equation signals are untouched; every
    # ranking-table refresh re-prices Entry/TP/SL from CURRENT OHLC and rebuilds
    # the strategy decision + current-OHLC bias, so a displayed TP can never
    # already be passed.
    return _live_stage2.reprice_live_table(staged,normalized)


def debug_live_execution(frames,check_time,quotes=None,strict_only=False):
    """Requirement 7 debug table: Symbol | Strategy ID | Month | Equation |
    Signal Time | Current Price | Entry | TP | SL | Bias Source | Bias Direction.

    Built from the same Stage-2-repriced live table the ranking display uses.
    """
    return _live_stage2.debug_rows(live_table(frames,check_time,quotes=quotes,strict_only=strict_only))


def apply_validation_mode(frame,strict_only=False):
    if not strict_only:return frame
    out=frame.copy()
    out[STRATEGY_COLUMNS]=np.int8(0)
    for c in ('Strategy Hit Count','unique_family_count'):out[c]=np.int8(0)
    for c in ('Hourly 4 Entry','research_entry_eligible','entry_eligible'):out[c]=False
    out['Strategy Decision']='None'
    out['Direction']='WAIT'
    for c in ('TP Price','SL Price','Suggested TP','Suggested SL','Suggested TP Price','Suggested SL Price','tp_price','sl_price'):out[c]=np.nan
    return out
