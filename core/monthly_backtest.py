"""Frozen-equation H1 replay and independent diagnostics (no fitting)."""
from __future__ import annotations
from io import BytesIO
import json
import zipfile
import numpy as np
import pandas as pd
from core import monthly_equations as engine
from core.monthly_runtime import build_history, raw_frame, ROOT, ENGINE_VERSION
from core.monthly_strategy_columns import STRATEGY_COLUMNS
from core.execution_policy_20261003 import checks_between
from core.improved_strategy_config import K_ENTRIES_PER_CHECK

TRADE_COLUMNS=['Symbol','Equation ID','Active S Column','check_at','entry_at','exit_at','entry_side','entry_price','tp_price','sl_price','exit_price','exit_reason','gross_pips','net_pips','tp_pips','sl_pips','hold_hours','max_hold_hours','danger','spread_pips','slippage_pips','ambiguous','stop_gap','censored','signal_bar_open','research_only']


def _utc(t):
    t=pd.Timestamp(t)
    return t.tz_localize('UTC') if t.tzinfo is None else t.tz_convert('UTC')


def make_tapes(raw):
    tapes={}
    for sym,g in raw.groupby('Symbol',sort=True):
        g=engine.session_filter(g)
        if g.empty:continue
        f=engine.make_features(g)
        times=pd.DatetimeIndex(g.Datetime).tz_localize('UTC')
        ny=times.tz_convert('America/New_York')
        available=times+pd.Timedelta(hours=1)
        for c in ('bar_close_time','signal_available_at'):
            if c in g:
                supplied=pd.DatetimeIndex(pd.to_datetime(g[c],utc=True,format='mixed'))
                available=pd.DatetimeIndex(np.maximum(available.asi8,supplied.asi8)).tz_localize('UTC')
                available=available.where(supplied.notna())
        exit_bias=np.r_[0,f.bias.to_numpy()[:-1]]
        exit_atr=np.r_[np.nan,f.atr.to_numpy()[:-1]]
        exit_range=np.r_[np.nan,(g.High-g.Low).to_numpy()[:-1]]
        exit_body=np.r_[np.nan,(g.Close-g.Open).to_numpy()[:-1]]
        exit_known=np.r_[False,(available[:-1].notna() & (available[:-1]<=times[1:]))]
        bound=available.asi8.copy();bound[available.isna()]=np.iinfo(np.int64).max
        late=np.zeros(len(g),bool)
        if len(g)>1:late[1:]=np.maximum.accumulate(bound)[:-1]>times.asi8[1:]
        for j in np.flatnonzero(late):
            known=g.iloc[:j].loc[available[:j].notna() & (available[:j]<=times[j])]
            if known.empty:exit_known[j]=False;continue
            last=engine.make_features(known).iloc[-1]
            exit_bias[j]=last.bias;exit_atr[j]=last.atr
            exit_range[j]=last.High-last.Low;exit_body[j]=last.Close-last.Open;exit_known[j]=True
        tapes[sym]=dict(frame=g,times=times,lookup={t:i for i,t in enumerate(times)},
            exit_bias=exit_bias,exit_atr=exit_atr,exit_range=exit_range,exit_body=exit_body,exit_known=exit_known,
            prices=g[['Open','High','Low','Close']].to_numpy(float),atr=f.atr.to_numpy(),bias=f.bias.to_numpy(),
            availability=available,friday=(ny.dayofweek==4)&(ny.hour==16),pip=.01 if sym.endswith('JPY') else .0001)
    return tapes


def replay_trade(signal,tape,*,end_time=None):
    """Next H1 open is replay-only. Conservative barriers and no stale exits."""
    entry_at=_utc(signal['Datetime']);check=_utc(signal['check_at'])
    if entry_at!=check+pd.Timedelta(minutes=30):raise ValueError('Replay fill must be 30 minutes after the UTC check')
    i=tape['lookup'].get(entry_at)
    if i is None:return None
    side=1 if signal['Direction']=='BUY' else -1
    tp=float(signal['Suggested TP Pips']);sl=float(signal['Suggested SL Pips']);pip=tape['pip']
    if not np.isfinite(tp+sl) or tp-1.0<.5*sl:return None
    px=float(tape['prices'][i,0]);target=px+side*tp*pip;stop=px-side*sl*pip
    hold=int(signal['Max Hold Hours']);danger=bool(signal['Danger Enabled'])
    limit=_utc(end_time) if end_time is not None else tape['times'][-1]+pd.Timedelta(hours=1)
    price=np.nan;xt=entry_at;reason='CENSORED';ambiguous=False;stop_gap=False
    for j in range(i,len(tape['times'])):
        at=tape['times'][j];op,hi,lo,cl=tape['prices'][j]
        if at>=limit or (j>i and at-tape['times'][j-1]!=pd.Timedelta(hours=1)):
            xt=at;break
        if not np.isfinite([op,hi,lo,cl]).all():xt=at;break
        if side*(op-stop)<=0:
            price=op;xt=at;reason='SL';stop_gap=not np.isclose(op,stop,rtol=0,atol=1e-12);break
        if side*(op-target)>=0:price=target;xt=at;reason='TP';break
        if at-entry_at>=pd.Timedelta(hours=hold):price=op;xt=at;reason='HOLD_CAP';break
        known=bool(tape['exit_known'][j]) if 'exit_known' in tape else j>0 and pd.notna(tape['availability'][j-1]) and tape['availability'][j-1]<=at
        if j>i and known:
            bias=tape['exit_bias'][j] if 'exit_bias' in tape else tape['bias'][j-1]
            if bias==-side:price=op;xt=at;reason='BIAS_FLIP';break
            po,ph,pl,pc=tape['prices'][j-1]
            atr=tape['exit_atr'][j] if 'exit_atr' in tape else tape['atr'][j-1]
            rng=tape['exit_range'][j] if 'exit_range' in tape else ph-pl
            body=tape['exit_body'][j] if 'exit_body' in tape else pc-po
            if danger and rng>3*atr and side*body<-.5*atr:
                price=op;xt=at;reason='DANGER';break
        hit_sl=lo<=stop if side>0 else hi>=stop
        hit_tp=hi>=target if side>0 else lo<=target
        if hit_sl or hit_tp:
            # Validated rule: TP wins when both barriers touch in one candle.
            ambiguous=bool(hit_sl and hit_tp);price=target if hit_tp else stop
            xt=at+pd.Timedelta(hours=1);reason='TP' if hit_tp else 'SL';break
        if tape['friday'][j]:price=cl;xt=at+pd.Timedelta(hours=1);reason='FRIDAY_CLOSE';break
        if j+1==len(tape['times']):xt=at+pd.Timedelta(hours=1);break
        if tape['times'][j+1]-at!=pd.Timedelta(hours=1):xt=tape['times'][j+1];break
    gross=side*(price-px)/pip if np.isfinite(price) else np.nan
    return dict(Symbol=signal['Symbol'],**{'Equation ID':signal['Equation ID'],'Active S Column':signal['Active S Column']},check_at=check,
        entry_at=entry_at,exit_at=xt,entry_side='BUY' if side==1 else 'SELL',entry_price=px,tp_price=target,sl_price=stop,
        exit_price=price,exit_reason=reason,gross_pips=gross,net_pips=gross-1.0,tp_pips=tp,sl_pips=sl,
        hold_hours=(xt-entry_at).total_seconds()/3600,max_hold_hours=hold,danger=danger,
        spread_pips=1.,slippage_pips=0.,ambiguous=ambiguous,stop_gap=stop_gap,censored=not np.isfinite(price),
        signal_bar_open=signal.get('signal_bar_open'),research_only=True)


def metrics(trades):
    valid=trades.loc[trades.net_pips.notna()].sort_values(['exit_at','Symbol','Equation ID'],kind='mergesort') if len(trades) else trades
    net=valid.net_pips if len(valid) else pd.Series(dtype=float)
    equity=net.cumsum();dd=equity-equity.cummax().clip(lower=0)
    maximum=float(dd.min()) if len(dd) else 0.
    wins=net[net>0].sum();loss=-net[net<0].sum()
    return {'Trades':len(valid),'Net Pip':float(net.sum()),'Net pips':float(net.sum()),'Max DD':maximum,
        'ROMAD':float(net.sum())/abs(maximum) if maximum!=0 else 'n.a.',
        'Censored Trades':int(trades.censored.sum()) if len(trades) else 0,
        'Win Rate':float((net>0).mean()*100) if len(net) else None,
        'Profit Factor':float(wins/loss) if loss else None,
        'Avg Hold':float(valid.hold_hours.mean()) if len(valid) else None,
        'Max Actual Hold':float(valid.hold_hours.max()) if len(valid) else None,
        'Ambiguous Trades':int(valid.ambiguous.sum()) if len(valid) else 0,
        'Stop Gap Trades':int(valid.stop_gap.sum()) if len(valid) else 0,
        'Pip_Check':'YES (historical equation label)','Strict_Valid':'NO','validation_label':'REUSED TEST; no fresh unseen validation',
        'DD basis':'Realized completed-trade pips; censored outcomes have unknown P/L'}


def _improved_rank_frame(frame):
    """Ensure the validated hour+symbol rank column exists for selection."""
    from core.improved_strategy_config import rank_score as _rs
    f=frame.copy()
    if 'Improved Rank' not in f.columns:
        _ck=f.get('check_at')
        hrs=(pd.to_datetime(_ck,utc=True,errors='coerce').dt.hour.fillna(-1).astype(int)
             if _ck is not None else pd.Series(-1,index=f.index))
        base=pd.to_numeric(f.get('ranking_score',pd.Series(0,index=f.index)),errors='coerce').fillna(0)
        f['Improved Rank']=[_rs(s,int(h),r) for s,h,r in zip(f['Symbol'].astype(str),hrs,base)]
    return f


def replay_portfolio(raw,*,entry_start=None,entry_end=None,strict_only=False,signals=None,research_end=None):
    """Causal replay: the backtest uses exactly the live signal logic.

    Contract (matches the live execution layer, requirement 2026-10-06):
    1. At each scheduled check (06,07,10,11,12,13 UTC, minute 30, weekdays --
       the validated check hours), calculate the S1-S240 equation signals from
       completed H1 bars only (features shifted so no future candle is used).
    2. Rank strategies with the validated Improved Rank and walk the ranking.
    3. Select up to K entries per check (never two positions in one symbol).
    4. Fill at the next H1 open -- that candle's OHLC becomes the entry price.
    5. TP/SL prices are computed from the entry (entry +/- pip distances);
       historical TP/SL prices are never loaded.
    6. Exits: TP-first on dual-touch candles, 1 pip spread, 48 h cap,
       bias-flip / danger / Friday-close exits from completed bars only.
    No future candle information is used at any step.
    """
    raw=raw_frame(raw)
    columns=build_history(raw,strict_only=strict_only) if signals is None else signals.copy()
    if 'Strategy Engine' not in columns or not columns['Strategy Engine'].eq(ENGINE_VERSION).all():raise ValueError('Stale strategy cache; rebuild S1–S240')
    start=_utc(entry_start) if entry_start is not None else _utc(raw.Datetime.min())
    end=_utc(entry_end) if entry_end is not None else _utc(raw.Datetime.max())
    tapes=make_tapes(raw)
    opportunities=columns.loc[columns['Strategy Hit Count'].eq(1)].copy()
    opportunities['check_at']=pd.to_datetime(opportunities.check_at,utc=True,format='mixed')
    opportunities=opportunities.loc[opportunities.check_at.between(start,end)]
    if strict_only:opportunities=opportunities.iloc[:0] # all frozen flags are NO
    opportunities=_improved_rank_frame(opportunities)
    bycheck={t:g for t,g in opportunities.groupby('check_at',sort=True)}
    held={};trades=[];decisions=[];maximum=0
    for check in checks_between(start,end):
        fill=check+pd.Timedelta(minutes=30)
        # Retrospective research book ends censored intervals at the next observed
        # quote; these outcomes remain UNKNOWN and never contribute realized P/L.
        # Live book below never releases an unresolved holding automatically.
        held={s:x for s,x in held.items() if x>check}
        group=bycheck.get(check,pd.DataFrame())
        admitted=[]
        if len(group):
            # Validated: walk the improved hour+symbol ranking and admit up to
            # K entries per check, never two positions in the same symbol.
            ranked=group.sort_values(['Improved Rank','Symbol','Equation ID'],ascending=[False,True,True],kind='mergesort').drop_duplicates('Symbol')
            top=ranked.Symbol.head(K_ENTRIES_PER_CHECK).tolist()
            if len(held)<20:
                for _,row in ranked.iterrows():
                    if row.Symbol in held:continue
                    if len(admitted)>=K_ENTRIES_PER_CHECK or len(held)+len(admitted)>=20:break
                    tape=tapes.get(row.Symbol)
                    trade=replay_trade(row.to_dict(),tape,end_time=research_end) if tape else None
                    if trade is None:continue
                    trade['trade_id']=len(trades)+1
                    trades.append(trade);held[trade['Symbol']]=trade['exit_at']
                    maximum=max(maximum,len(held));admitted.append(trade)
            reason='ENTRY' if admitted else 'MAX_20_HOLDINGS' if len(held)>=20 else 'TOP_FOUR_HELD'
        else:top=[];reason='STRICT_VALID_NO' if strict_only else 'NO_TRIGGER'
        decisions.append(dict(check_at=check,fill_at=fill,top_four=','.join(top),
            held_symbols=','.join(sorted(set(held)-{t['Symbol'] for t in admitted})),
            selected=','.join(t['Symbol'] for t in admitted),
            equation_id=','.join(t['Equation ID'] for t in admitted),reason=reason))
    ledger=pd.DataFrame(trades) if trades else pd.DataFrame(columns=TRADE_COLUMNS)
    result=metrics(ledger);result['Max Concurrent Holdings']=maximum
    reused_start=_utc('2025-10-01');reused_end=_utc('2026-10-05 07:00')
    reused=ledger.loc[ledger.entry_at.ge(reused_start)&ledger.entry_at.lt(reused_end)] if len(ledger) else ledger
    result['Reused-test metrics']=metrics(reused)
    result['Engine']=ENGINE_VERSION
    return dict(trades=ledger,checks=pd.DataFrame(decisions),metrics=result,signals=columns)


def independent_diagnostics(raw,signals=None,strict_only=False):
    """Each equation has its own independent book; never sum as a portfolio."""
    raw=raw_frame(raw);columns=build_history(raw,strict_only=strict_only) if signals is None else signals
    tapes=make_tapes(raw);rows=[]
    for (sym,eqid),group in columns.loc[columns['Strategy Hit Count'].eq(1)].groupby(['Symbol','Equation ID']):
        if strict_only:continue
        blocked=pd.Timestamp.min.tz_localize('UTC');trades=[]
        for _,signal in group.sort_values('Datetime').iterrows():
            if _utc(signal.Datetime)<blocked:continue
            t=replay_trade(signal.to_dict(),tapes[sym])
            if t:trades.append(t);blocked=t['exit_at']
        ledger=pd.DataFrame(trades) if trades else pd.DataFrame(columns=TRADE_COLUMNS)
        test=ledger.loc[ledger.entry_at.ge(_utc('2025-10-01'))&ledger.entry_at.lt(_utc('2026-10-05 07:00'))] if len(ledger) else ledger
        m=metrics(ledger);tm=metrics(test)
        m.update(Symbol=sym,Equation_ID=eqid,Active_Column=group['Active S Column'].iloc[0],Reused_Test_Net=tm['Net Pip'],Reused_Test_DD=tm['Max DD'],Reused_Test_ROMAD=tm['ROMAD'],Reused_Test_Censored=tm['Censored Trades'])
        rows.append(m)
    return pd.DataFrame(rows)


def bundle(result,diagnostics=None,include_signals=True):
    out=BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('trade_log.csv',result['trades'].to_csv(index=False))
        z.writestr('check_decisions.csv',result['checks'].to_csv(index=False))
        z.writestr('portfolio_metrics.json',json.dumps(result['metrics'],indent=2,default=str,allow_nan=False))
        if diagnostics is not None:z.writestr('independent_equation_diagnostics.csv',diagnostics.to_csv(index=False))
        if include_signals:z.writestr('all_rows_S1_S240.csv',result['signals'].to_csv(index=False))
        for name in ('equation_column_map.json','equation_column_map.csv'):z.writestr(name,(ROOT/name).read_bytes())
        z.writestr('README.txt','Historical research only. Pip_Check=YES; every Strict_Valid=NO. Test period was reused. H1 fills next open 30 minutes after the UTC check; live requires an actual executable quote. Dynamic exits per validated config: TP=k_tp[month,symbol]xATR14 (clip 10..500), SL=10 fixed, TP first for dual touches, 48h elapsed cap, adverse stop gaps at observed open; missing quotes censored. 1 pip spread deducted once. ROMAD uses realized DD; n.a. for zero DD. Independent diagnostics are not portfolio results. Censored research intervals end at the next observed quote, with unknown P/L; this is not proof that a live holding closed. Heavy Middle Standard Regime display differs from the recovered research Middle Bias used by equations.\n')
    return out.getvalue()
