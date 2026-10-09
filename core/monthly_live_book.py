"""Persistent application admission/position journal; this module sends no orders.

A broker integration supplies timestamped executable bid/ask quotes. It must
reconcile the journal with actual holdings; a research signal is not validation.
"""
from pathlib import Path
import json
import sqlite3
import numpy as np
import pandas as pd
from core.monthly_runtime import live_table,raw_frame,ENGINE_VERSION
from core.execution_policy_20261003 import checks_between
from core import monthly_equations as engine


def _connect(path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(path),timeout=20)
    c.execute('CREATE TABLE IF NOT EXISTS monthly_checks (account TEXT, check_at TEXT, engine TEXT, decision TEXT, PRIMARY KEY(account,check_at))')
    c.execute('CREATE TABLE IF NOT EXISTS monthly_positions (account TEXT, symbol TEXT, position TEXT, PRIMARY KEY(account,symbol))')
    c.execute('CREATE TABLE IF NOT EXISTS monthly_closed (account TEXT, position TEXT)')
    return c


def _quote(q,at,side,entry=True):
    if not isinstance(q,dict) or q.get('executable') is not True:return None
    stamp=pd.Timestamp(q.get('at'))
    if stamp.tzinfo is None or stamp!=at:return None
    bid=q.get('bid');ask=q.get('ask')
    if bid is None or ask is None:return None
    if not np.isfinite([float(bid),float(ask)]).all() or not 0<float(bid)<=float(ask):return None
    return float(ask if (side==1)==entry else bid)


def admit_check(frames,check_time,quotes,*,path='data/monthly_live_book.sqlite3',account='default',external_held=(),strict_only=True):
    """Transactionally admit up to K entries per check; duplicate reruns reuse the same decision."""
    from core.improved_strategy_config import K_ENTRIES_PER_CHECK, rank_score as _rs
    check=pd.Timestamp(check_time)
    if check.tzinfo is None:raise ValueError('Live check must include timezone')
    check=check.tz_convert('UTC');key=check.isoformat()
    table=live_table(frames,check,quotes,strict_only=strict_only)
    if 'Improved Rank' not in table.columns:
        _ck=table.get('check_at')
        _h=(pd.to_datetime(_ck,utc=True,errors='coerce').dt.hour.fillna(check.hour).astype(int)
            if _ck is not None else pd.Series(check.hour,index=table.index))
        _b=pd.to_numeric(table.get('ranking_score',pd.Series(0,index=table.index)),errors='coerce').fillna(0)
        table=table.copy()
        table['Improved Rank']=[_rs(s,int(h),r) for s,h,r in zip(table['Symbol'].astype(str),_h,_b)]
    with _connect(path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        prior=conn.execute('SELECT decision FROM monthly_checks WHERE account=? AND check_at=?',(account,key)).fetchone()
        if prior:return dict(json.loads(prior[0]),deduplicated=True)
        positions={s:json.loads(p) for s,p in conn.execute('SELECT symbol,position FROM monthly_positions WHERE account=?',(account,))}
        held=set(positions)|{str(s).upper().replace('/','') for s in external_held}
        admitted=[];reason='NO_TRIGGER';top=[]
        allowed=len(checks_between(check,check))==1
        ranked=table.loc[table['Strategy Hit Count'].eq(1)].sort_values(['Improved Rank','Symbol','Equation ID'],ascending=[False,True,True])
        top=ranked.Symbol.head(K_ENTRIES_PER_CHECK).tolist()
        if not allowed:reason='OUTSIDE_UTC_CHECK_SCHEDULE'
        elif strict_only:reason='STRICT_VALID_NO'
        elif len(held)>=20:reason='MAX_20_HOLDINGS'
        elif len(ranked):
            reason='TOP_FOUR_HELD'
            for _,row in ranked.iterrows():
                if row.Symbol in held:continue
                if len(admitted)>=K_ENTRIES_PER_CHECK or len(held)+len(admitted)>=20:break
                side=1 if row.Direction=='BUY' else -1
                price=_quote(quotes.get(row.Symbol),check,side)
                if price is None:reason='EXECUTABLE_QUOTE_REQUIRED';break
                pip=.01 if row.Symbol.endswith('JPY') else .0001
                tp=float(row['Suggested TP Pips']);sl=float(row['Suggested SL Pips'])
                if tp-1.0<.5*sl:reason='DYNAMIC_RISK_GATE';break
                position=dict(symbol=row.Symbol,equation_id=row['Equation ID'],strategy_column=row['Active S Column'],side=side,
                    entry_at=key,entry_price=price,tp_pips=tp,sl_pips=sl,tp_price=price+side*tp*pip,sl_price=price-side*sl*pip,
                    hold_hours=int(row['Max Hold Hours']),danger=bool(row['Danger Enabled']),engine=ENGINE_VERSION,
                    Strict_Valid='NO',research_only=True,cost_basis='Actual executable bid/ask; 1 pip spread in replay')
                conn.execute('INSERT INTO monthly_positions VALUES (?,?,?)',(account,row.Symbol,json.dumps(position)))
                admitted.append(position);held.add(row.Symbol)
            if admitted:reason='ADMITTED_TO_APP_JOURNAL'
        decision=dict(check_at=key,selected=admitted[0] if admitted else None,admitted=admitted,top_four=top,held_symbols=sorted(held),reason=reason,deduplicated=False,orders_sent=0)
        conn.execute('INSERT INTO monthly_checks VALUES (?,?,?,?)',(account,key,ENGINE_VERSION,json.dumps(decision)))
        return decision


def reconcile_completed_exits(frames,quotes,at,*,path='data/monthly_live_book.sqlite3',account='default'):
    """Retain a holding if no executable exit quote exists; never synthesize fills."""
    at=pd.Timestamp(at)
    if at.tzinfo is None:raise ValueError('Exit clock must include timezone')
    at=at.tz_convert('UTC');closed=[]
    with _connect(path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        for symbol,data in conn.execute('SELECT symbol,position FROM monthly_positions WHERE account=?',(account,)).fetchall():
            p=json.loads(data);side=p['side'];q=quotes.get(symbol);px=_quote(q,at,side,entry=False)
            if px is None:continue
            reason=None
            if side*(px-p['sl_price'])<=0:reason='SL'
            elif side*(px-p['tp_price'])>=0:reason='TP'
            elif at-pd.Timestamp(p['entry_at'])>=pd.Timedelta(hours=p['hold_hours']):reason='HOLD_CAP'
            ny=at.tz_convert('America/New_York')
            if not reason and ny.dayofweek==4 and ny.hour>=17:reason='FRIDAY_CLOSE'
            if not reason and symbol in frames and q.get('is_executable_open') is True:
                raw=raw_frame(frames[symbol],symbol)
                raw=raw.loc[raw.Datetime+pd.Timedelta(hours=1)<=at.tz_localize(None)]
                for c in ('bar_close_time','signal_available_at'):
                    if c in raw:raw=raw.loc[pd.to_datetime(raw[c],utc=True,format='mixed').le(at)]
                f=engine.make_features(engine.session_filter(raw))
                if len(f):
                    b=f.iloc[-1]
                    if int(b.bias)==-side:reason='BIAS_FLIP'
                    elif p['danger'] and b.High-b.Low>3*b.atr and side*(b.Close-b.Open)<-.5*b.atr:reason='DANGER'
            if reason:
                pip=.01 if symbol.endswith('JPY') else .0001
                # Validated cost model: actual bid/ask fills already embed the
                # spread; slippage is 0 (was 0.5).
                p.update(exit_at=at.isoformat(),exit_price=px,exit_reason=reason,net_pips=side*(px-p['entry_price'])/pip)
                conn.execute('INSERT INTO monthly_closed VALUES (?,?)',(account,json.dumps(p)))
                conn.execute('DELETE FROM monthly_positions WHERE account=? AND symbol=?',(account,symbol));closed.append(p)
    return closed


def journal(path='data/monthly_live_book.sqlite3',account='default'):
    with _connect(path) as conn:
        positions=[json.loads(p) for p, in conn.execute('SELECT position FROM monthly_positions WHERE account=?',(account,))]
        checks=[json.loads(p) for p, in conn.execute('SELECT decision FROM monthly_checks WHERE account=? ORDER BY check_at',(account,))]
        trades=[json.loads(p) for p, in conn.execute('SELECT position FROM monthly_closed WHERE account=?',(account,))]
    return dict(positions=pd.DataFrame(positions),checks=pd.DataFrame(checks),trades=pd.DataFrame(trades))
