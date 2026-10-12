"""Replacement contract: actual frozen signals, app paths and adversarial fills."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from core.monthly_strategy_columns import STRATEGY_COLUMNS,load_mapping,build_replay_columns,evaluate_check_columns
from core.monthly_runtime import ENGINE_VERSION,build_history,live_table,raw_frame
from core.monthly_backtest import replay_trade,replay_portfolio,metrics,make_tapes,bundle
from core.execution_policy_20261003 import checks_between,select_new_entries,quote_metadata
from core import monthly_equations as engine
from core.monthly_live_book import admit_check,journal,reconcile_completed_exits


@pytest.fixture(scope='module')
def raw():
    return pd.read_csv(Path(__file__).parent/'fixtures/monthly_h1_quotes.csv')


@pytest.fixture(scope='module')
def history(raw):return build_history(raw)


def test_exact_registry_and_frozen_labels():
    m=load_mapping();eq=engine.load_equations()
    assert len(m)==len(eq)==240
    assert STRATEGY_COLUMNS==[f'S{i}' for i in range(1,241)]
    assert m[0]['column']=='S1' and m[0]['symbol']=='AUDCAD' and m[0]['month']==1
    assert m[12]['symbol']=='AUDCHF' and m[239]['symbol']=='USDJPY'
    assert {r['equation_id'] for r in m}=={q['id'] for q in eq}
    assert all(q['historical_positive'] and not q['strict_valid'] for q in eq)
    assert sum(q['origin']=='PRESERVED' for q in eq)==69
    import csv
    with open(Path(engine.__file__).parent/'equation_column_map.csv') as f: rows=list(csv.DictReader(f))
    assert [r['column'] for r in rows]==STRATEGY_COLUMNS


def test_raw_preserved_and_symbol_month_direction(history,raw):
    expected=raw.copy();expected.Datetime=pd.to_datetime(expected.Datetime,utc=True).dt.tz_localize(None)
    expected=expected.sort_values(['Symbol','Datetime']).reset_index(drop=True)
    pd.testing.assert_frame_equal(history[expected.columns],expected,check_dtype=False)
    a=history[STRATEGY_COLUMNS].to_numpy()
    assert np.isin(a,[-1,0,1]).all() and (np.count_nonzero(a,axis=1)<=1).all()
    assert history['Strategy Hit Count'].sum()>0
    bycol={r['column']:r for r in load_mapping()}
    for _,r in history.loc[history['Strategy Hit Count'].eq(1)].iterrows():
        q=bycol[r['Active S Column']]
        assert q['symbol']==r.Symbol and q['month']==r.check_at.tz_convert('Asia/Rangoon').month
        assert r['Equation ID']==q['equation_id']
        assert r.check_at.dayofweek<5
        assert r.check_at.hour in (6,7,10,11,12,13) and r.check_at.minute==30
        assert r.signal_bar_open+pd.Timedelta(hours=1)<=r.check_at.tz_localize(None)
        assert int(r[r['Active S Column']])==(1 if r.Direction=='BUY' else -1)


def test_live_replay_parity_real_frozen_rules(history,raw):
    frames={s:g for s,g in raw.groupby('Symbol')}
    hit=history.loc[history['Strategy Hit Count'].eq(1)]
    checks=hit.check_at.unique()[:15]
    assert len(checks)>0
    for check in checks:
        table=live_table(frames,check).set_index('Symbol')
        replay=history.loc[history.check_at.eq(check)].set_index('Symbol')
        for s in replay.index:
            np.testing.assert_array_equal(table.loc[s,STRATEGY_COLUMNS].to_numpy(),replay.loc[s,STRATEGY_COLUMNS].to_numpy())
            if table.loc[s,'Strategy Hit Count']:
                assert table.loc[s,'Suggested TP Pips']==pytest.approx(replay.loc[s,'Suggested TP Pips'])
                assert table.loc[s,'Suggested SL Pips']==pytest.approx(replay.loc[s,'Suggested SL Pips'])


def test_future_candle_mutation_cannot_change_old_signals(raw):
    before=build_replay_columns(raw)
    changed=raw.copy();cut=pd.Timestamp('2022-10-20')
    mask=pd.to_datetime(changed.Datetime)>cut
    changed.loc[mask,['Open','High','Low','Close']]*=1.7
    after=build_replay_columns(changed)
    old=before.Datetime<=cut
    np.testing.assert_array_equal(before.loc[old,STRATEGY_COLUMNS],after.loc[old,STRATEGY_COLUMNS])


def test_forming_candle_and_late_availability(raw,history):
    r=history.loc[history['Strategy Hit Count'].eq(1)].iloc[0];sym=r.Symbol
    frame=raw.loc[raw.Symbol.eq(sym)].copy();check=r.check_at
    expected=live_table({sym:frame},check).set_index('Symbol').loc[sym,STRATEGY_COLUMNS]
    formed=pd.to_datetime(frame.Datetime,utc=True)>=check.floor('h')
    frame.loc[formed,['Open','High','Low','Close']]*=1.8
    actual=live_table({sym:frame},check).set_index('Symbol').loc[sym,STRATEGY_COLUMNS]
    np.testing.assert_array_equal(actual,expected)
    signal=pd.to_datetime(frame.Datetime,utc=True).eq(r.signal_bar_open.tz_localize('UTC'))
    frame.loc[signal,'signal_available_at']=(check+pd.Timedelta(minutes=1)).isoformat()
    assert not live_table({sym:frame},check)[STRATEGY_COLUMNS].any().any()
    delayed=build_replay_columns(frame)
    row=delayed.loc[pd.to_datetime(delayed.Datetime,utc=True).eq(check+pd.Timedelta(minutes=30))]
    assert not row[STRATEGY_COLUMNS].any().any()
    # An older delayed candle must also be excluded from indicator inputs.
    frame=raw.loc[raw.Symbol.eq(sym)].copy()
    older=pd.to_datetime(frame.Datetime,utc=True).eq(r.signal_bar_open.tz_localize('UTC')-pd.Timedelta(hours=3))
    frame.loc[older,'signal_available_at']=(check+pd.Timedelta(hours=2)).isoformat()
    a=live_table({sym:frame},check).set_index('Symbol').loc[sym,STRATEGY_COLUMNS]
    b=build_replay_columns(frame).loc[lambda d:pd.to_datetime(d.Datetime,utc=True).eq(check+pd.Timedelta(minutes=30)),STRATEGY_COLUMNS].iloc[0]
    np.testing.assert_array_equal(a,b)


def test_strict_mode_zero_columns(raw):
    h=build_history(raw,strict_only=True)
    assert not h[STRATEGY_COLUMNS].any().any()
    r=replay_portfolio(raw,strict_only=True,signals=h)
    assert r['trades'].empty and r['metrics']['ROMAD']=='n.a.'


def test_month_boundary_routes_by_rangoon_month(monkeypatch):
    # January UTC check occurs on a UTC January date; the frozen equation is
    # still selected by Rangoon month. AUDCAD is removed by the validated
    # config, so the synthetic feed uses EURUSD (Jan=S145, Dec=S156).
    rng=np.random.default_rng(7)
    times=pd.date_range('2024-12-20',periods=600,freq='h')
    close=1.1+np.cumsum(rng.normal(0,.0002,len(times)))
    raw=pd.DataFrame(dict(Symbol='EURUSD',Datetime=times,Open=close-.0001,High=close+.0003,Low=close-.0003,Close=close))
    monkeypatch.setattr(engine,'signal_array',lambda f,b,q:np.full(len(f),q['side']))
    h=build_history(raw)
    hits=h.loc[h['Strategy Hit Count'].eq(1)]
    assert {x for x in hits['Equation Month']}=={12,1}
    assert set(hits.loc[hits['Equation Month'].eq(12),'Active S Column'])=={'S156'}
    assert set(hits.loc[hits['Equation Month'].eq(1),'Active S Column'])=={'S145'}
    assert (hits.check_at.dt.dayofweek<5).all()
    assert not h.loc[pd.to_datetime(h.Datetime,utc=True).dt.dayofweek.ge(5),STRATEGY_COLUMNS].any().any()


def candidates():
    return pd.DataFrame({'Symbol':['AUDCAD','AUDCHF','AUDJPY','AUDNZD','AUDUSD'],'Equation ID':['q1','q2','q3','q4','q5'],'ranking_score':[5,4,3,2,1],'Strategy Hit Count':1,'Strategy Engine':ENGINE_VERSION,'entry_eligible':False,'research_entry_eligible':True})


def test_top_four_holding_skip_k4_entries_and_max20():
    c=candidates()
    picked,_=select_new_entries(c,{'AUDCAD','AUDCHF','AUDJPY','AUDNZD'},eligibility_column='research_entry_eligible')
    assert picked.Symbol.tolist()==['AUDUSD'] # only unheld symbol admitted
    picked,_=select_new_entries(c,{'AUDCAD'},eligibility_column='research_entry_eligible')
    assert picked.Symbol.tolist()==['AUDCHF','AUDJPY','AUDNZD','AUDUSD'] # up to 4, no duplicate symbol
    picked,_=select_new_entries(c,{str(i) for i in range(20)},eligibility_column='research_entry_eligible')
    assert picked.empty
    picked,_=select_new_entries(c,set())
    assert picked.empty # strict flag NO
    c['Strategy Hit Count']=0
    picked,_=select_new_entries(c,set(),eligibility_column='research_entry_eligible')
    assert picked.empty # no rank fills


def tape(prices,bias=None,*,start='2024-10-08T02:00Z'):
    n=len(prices);times=pd.date_range(start,periods=n,freq='h')
    ny=times.tz_convert('America/New_York')
    return dict(times=times,lookup={t:i for i,t in enumerate(times)},prices=np.array(prices,float),bias=np.array(bias if bias is not None else [1]*n),atr=np.full(n,.0002),availability=times+pd.Timedelta(hours=1),friday=(ny.dayofweek==4)&(ny.hour==16),pip=.0001)


def signal(**changes):
    r={'Symbol':'EURUSD','Equation ID':'FROZEN_TEST','Active S Column':'S145','Datetime':'2024-10-08T02:00Z','check_at':'2024-10-08T01:30Z','Direction':'BUY','Suggested TP Pips':10.,'Suggested SL Pips':10.,'Max Hold Hours':6,'Danger Enabled':False}
    r.update(changes);return r


def test_dual_barriers_tp_first_and_once_only_cost():
    t=replay_trade(signal(),tape([[1.1,1.102,1.098,1.1]]))
    assert t['exit_reason']=='TP' and t['ambiguous']
    assert t['gross_pips']==pytest.approx(10) and t['net_pips']==pytest.approx(9.0)


def test_adverse_stop_gap_observed_open():
    t=replay_trade(signal(),tape([[1.1,1.1004,1.0997,1.1],[1.0985,1.1,1.098,1.099]]))
    assert t['exit_price']==1.0985 and t['stop_gap'] and t['net_pips']==pytest.approx(-16.0)


def test_neutral_no_flip_opposite_next_open():
    t=replay_trade(signal(),tape([[1.1,1.1002,1.0998,1.1]]*4,[0,0,-1,1]))
    assert t['exit_reason']=='BIAS_FLIP' and t['exit_at']==pd.Timestamp('2024-10-08T05:00Z')


def test_danger_strict_and_elapsed_cap():
    p=[[1.1,1.1002,1.0998,1.1],[1.1003,1.1007,1.0999,1.1000],[1.1,1.1002,1.0998,1.1]]
    d=replay_trade(signal(**{'Danger Enabled':True}),tape(p))
    assert d['exit_reason']=='DANGER'
    h=replay_trade(signal(),tape([[1.1,1.1002,1.0998,1.1]]*8))
    assert h['exit_reason']=='HOLD_CAP' and h['hold_hours']==6


def test_friday_close_and_missing_quote_censorship():
    sig=signal(Datetime='2024-10-11T20:00Z',check_at='2024-10-11T19:30Z')
    # Trade fixture exercises exit independently of weekday entry routing.
    t=replay_trade(sig,tape([[1.1,1.1002,1.0998,1.1001]],start='2024-10-11T20:00Z'))
    assert t['exit_reason']=='FRIDAY_CLOSE'
    p=tape([[1.1,1.1002,1.0998,1.1]]*2)
    p['times']=pd.DatetimeIndex(['2024-10-08T02:00Z','2024-10-08T04:00Z'])
    p['lookup']={t:i for i,t in enumerate(p['times'])}
    t=replay_trade(signal(),p)
    assert t['censored'] and pd.isna(t['net_pips']) and pd.isna(t['exit_price'])


def test_tp_sl_prices_dynamic_equation_and_jpy_units(history):
    from core import improved_strategy_config as isc
    for _,r in history.loc[history['Strategy Hit Count'].eq(1)].iterrows():
        pip=.01 if r.Symbol.endswith('JPY') else .0001
        tp,sl=isc.dynamic_tp_sl(r['check_at'],r.Symbol,r['Signal ATR']/pip)
        assert tp is not None # gated symbols never reach replay
        side=int(r[r['Active S Column']]);assert r['TP Price']==pytest.approx(r.Open+side*tp*pip)
        assert r['SL Price']==pytest.approx(r.Open-side*sl*pip)
        assert r['Suggested TP Pips']==pytest.approx(tp) and r['Suggested SL Pips']==pytest.approx(sl)
        assert tp-1.0>=.5*sl


def test_provider_later_availability_preserved():
    raw=pd.DataFrame(dict(open_time=pd.date_range('2024-10-08',periods=3,freq='h',tz='UTC'),open=1.1,high=1.2,low=1.,close=1.15))
    raw['signal_available_at']=raw.open_time+pd.Timedelta(hours=2)
    m=quote_metadata(raw)
    pd.testing.assert_series_equal(m.signal_available_at,raw.signal_available_at,check_names=False)


def test_persistent_live_dedup_actual_quote_cost_and_frozen_position(tmp_path,monkeypatch):
    path=tmp_path/'book.sqlite'
    check=pd.Timestamp('2024-10-08T06:30Z')
    c=candidates().iloc[:1].assign(Direction='BUY',**{'Active S Column':'S10','Suggested TP Pips':10.,'Suggested SL Pips':10.,'Max Hold Hours':6,'Danger Enabled':True})
    monkeypatch.setattr('core.monthly_live_book.live_table',lambda *a,**kw:c)
    quote={'AUDCAD':{'at':check,'bid':1.0998,'ask':1.1,'executable':True}}
    a=admit_check({},check,quote,path=path,strict_only=False)
    b=admit_check({},check,quote,path=path,strict_only=False)
    assert a['selected']['entry_price']==1.1 and b['deduplicated']
    book=journal(path);assert len(book['positions'])==1 and len(book['checks'])==1
    p=book['positions'].iloc[0];assert p.tp_price==pytest.approx(1.101) and p.hold_hours==6
    # Missing quotes retain the holding even after a cap; no stale/future fill.
    assert reconcile_completed_exits({}, {}, check+pd.Timedelta(hours=7),path=path)==[]
    assert len(journal(path)['positions'])==1
    at=check+pd.Timedelta(hours=7)
    exits=reconcile_completed_exits({}, {'AUDCAD':{'at':at,'bid':1.1002,'ask':1.1004,'executable':True}},at,path=path)
    assert exits[0]['net_pips']==pytest.approx(2.0) # bid/ask already charged real spread; no slippage
    assert journal(path)['positions'].empty


def test_weekend_checks_and_rerun_book_rejection(tmp_path,monkeypatch):
    checks=checks_between('2024-10-11','2024-10-15')
    assert (checks.dayofweek<5).all() and set(checks.hour)=={6,7,10,11,12,13}
    assert (checks.minute==30).all()
    c=candidates().iloc[:1].assign(Direction='BUY',**{'Active S Column':'S10'})
    monkeypatch.setattr('core.monthly_live_book.live_table',lambda *a,**kw:c)
    a=admit_check({},pd.Timestamp('2024-10-12T01:30Z'),{},path=tmp_path/'book.sqlite',strict_only=False)
    assert a['selected'] is None and a['reason']=='OUTSIDE_UTC_CHECK_SCHEDULE'


def test_ui_finder_export_no_row_loss_old_aliases_no_votes(history):
    from ui.field3_multisymbol_regime_summary_20260722 import _canonical_middle_export_frame,_filter_finder_result,get_strategy_decision
    from core.hourly_four_symbol_selector_20260928 import attach_hourly_four_selection
    from core.strategy_audit_20260924 import recompute_family_evidence
    out=_canonical_middle_export_frame(attach_hourly_four_selection(history))
    assert len(out)==len(history) and set(STRATEGY_COLUMNS).issubset(out)
    r=out.loc[out['Strategy Hit Count'].eq(1)].iloc[0]
    assert get_strategy_decision(r)==f"{r.Direction}, TP={r['TP Price']:.5f}, SL={r['SL Price']:.5f}"
    filtered=_filter_finder_result(out,strategies=[r['Active S Column']])
    assert len(filtered)>0 and filtered[r['Active S Column']].ne(0).all()
    old=pd.DataFrame([{'S87':1,'S87 Entry Condition':True,'Strategy Engine':'OLD'}])
    assert not recompute_family_evidence(old)[STRATEGY_COLUMNS].any().any()


def test_portfolio_limits_and_download_contents(raw,history):
    r=replay_portfolio(raw,signals=history)
    t=r['trades'];assert len(t)>0
    assert t.check_at.value_counts().max()==1
    for sym,g in t.groupby('Symbol'):
        g=g.sort_values('entry_at')
        assert (g.entry_at.iloc[1:].reset_index(drop=True)>=g.exit_at.iloc[:-1].reset_index(drop=True)).all()
    assert (t.loc[~t.censored,'hold_hours']<=t.loc[~t.censored,'max_hold_hours']).all()
    assert r['metrics']['Max Concurrent Holdings']<=20
    import zipfile,io
    with zipfile.ZipFile(io.BytesIO(bundle(r))) as z:
        assert {'trade_log.csv','check_decisions.csv','equation_column_map.csv','all_rows_S1_S240.csv'}.issubset(z.namelist())


def test_worker_symbol_build_finalizer_and_parquet_csv_retention(raw,tmp_path,monkeypatch):
    from core import resumable_build_20260928 as builds
    from worker.fast_artifacts_20261002 import finalize
    from core.super_quick_field3_20260722 import _build_middle_finder_history
    from io import BytesIO
    monkeypatch.setattr(builds,'_RUNTIME_ROOT',tmp_path)
    monkeypatch.setattr(builds,'_LOCAL_JOBS',tmp_path/'jobs')
    monkeypatch.setattr(builds,'_LOCAL_OBJECTS',tmp_path/'objects')
    store=builds.BuildStore(backend=builds._LocalBackend())
    symbols=sorted(raw.Symbol.unique())
    job=builds.make_job({},symbols=symbols,timeframe='H1')
    start=pd.to_datetime(raw.Datetime,utc=True).min();end=pd.to_datetime(raw.Datetime,utc=True).max()
    job.update(symbols=symbols,start_date=start.isoformat(),end_date=end.isoformat())
    manifest=[]
    for symbol,g in raw.groupby('Symbol'):
        built=_build_middle_finder_history({symbol:g},timeframe='H1',apply_selection=False,output_mode='BACKTEST_FAST')
        path=symbol+'.parquet';saved=builds.put_dataframe(store,path,built)
        manifest.append(dict(saved,kind='finder_symbol',symbol=symbol,oldest=start.isoformat(),newest=end.isoformat(),strategy_engine=ENGINE_VERSION))
    artifact=finalize(job,store,manifest)
    exported=pd.read_csv(BytesIO(store.get_object(artifact['path'])),low_memory=False)
    assert len(exported)==len(raw) and set(STRATEGY_COLUMNS).issubset(exported)
    assert exported['Strategy Hit Count'].gt(0).any()
    count=exported.groupby('check_at')['Strategy Hit Count'].sum().clip(upper=4)
    published=exported.groupby('check_at')['Hourly 4 Entry'].sum()
    pd.testing.assert_series_equal(count,published,check_names=False,check_dtype=False)
    for symbol,g in raw.groupby('Symbol'):
        original=g.sort_values('Datetime').reset_index(drop=True)
        saved=exported.loc[exported.Symbol.eq(symbol)].sort_values('Datetime').reset_index(drop=True)
        for col in ('Open','High','Low','Close','signal_available_at','market_executable','data_quality_flag'):
            pd.testing.assert_series_equal(saved[col],original[col],check_names=False,check_dtype=False)
    assert len([a for a in manifest if a['kind']=='equation_mapping'])==2


def test_delayed_completed_bias_cannot_exit_early():
    p=tape([[1.1,1.1002,1.0998,1.1]]*5,[1,-1,1,1,1])
    p['availability']=pd.DatetimeIndex(['2024-10-08T03:00Z','2024-10-08T06:00Z','2024-10-08T05:00Z','2024-10-08T06:00Z','2024-10-08T07:00Z'])
    t=replay_trade(signal(),p)
    assert t['exit_reason']!='BIAS_FLIP'


def test_live_missing_quote_rejects_future_h1_open(history,raw):
    r=history.loc[history['Strategy Hit Count'].eq(1)].iloc[0]
    f={s:g for s,g in raw.groupby('Symbol')}
    wrong={r.Symbol:{'at':r.check_at+pd.Timedelta(minutes=30),'bid':1.1,'ask':1.1002,'executable':True}}
    row=live_table(f,r.check_at,wrong).set_index('Symbol').loc[r.Symbol]
    assert row['Strategy Hit Count']==1 and pd.isna(row['Actual Entry Quote'])
    # Stage 2 (2026-10-06 fix): without an executable quote, Entry/TP/SL are
    # rebuilt from CURRENT OHLC on every refresh -- never the old check-time
    # signal-bar price.
    assert row['Target Price Basis']=='CURRENT_CANDLE_CLOSE (LIVE_REPRICED)'
    latest=f[r.Symbol].sort_values('Datetime').iloc[-1]
    assert row['Target Reference Price']==pytest.approx(float(latest['Close']))
    assert row['Live Entry Price']==pytest.approx(float(latest['Close']))
    assert row['Live Entry Basis']=='CURRENT_CANDLE_CLOSE'
    side=1 if row['Direction']=='BUY' else -1
    pip=.01 if r.Symbol.endswith('JPY') else .0001
    assert row['TP Price']==pytest.approx(row['Live Entry Price']+side*row['Suggested TP Pips']*pip)
    assert row['SL Price']==pytest.approx(row['Live Entry Price']-side*row['Suggested SL Pips']*pip)
    assert np.isfinite([row['TP Price'],row['SL Price']]).all()
    # Stage 1 is untouched: same equation, direction and pip distances.
    assert row['Equation ID']==r['Equation ID'] and row['Direction']==r['Direction']


def test_compact_decisions_and_live_equation_targets(history,raw,tmp_path):
    from core.monthly_runtime import decision_text
    from ui.field3_multisymbol_regime_summary_20260722 import get_strategy_decision,_canonical_middle_export_frame
    assert decision_text('BUY','S1','q',1.12345,1.10001)=='BUY, TP=1.12345, SL=1.10001'
    assert decision_text('SELL','S240','q',145.5,147.2)=='SELL, TP=145.50000, SL=147.20000'
    assert decision_text('WAIT','S1','q',None,None)=='None'
    frames={s:g for s,g in raw.groupby('Symbol')}
    hits=history.loc[history['Strategy Hit Count'].eq(1)]
    assert set(hits.Direction)=={'BUY','SELL'}
    for check in hits.check_at.unique()[:15]:
        indicative=live_table(frames,check)
        active=indicative.loc[indicative['Strategy Hit Count'].eq(1)]
        quotes={r.Symbol:dict(at=check,bid=float(r['Target Reference Price']),ask=float(r['Target Reference Price'])+(.02 if r.Symbol.endswith('JPY') else .0002),executable=True) for _,r in active.iterrows()}
        executable=live_table(frames,check,quotes)
        for table in (indicative,executable):
            exported=_canonical_middle_export_frame(table)
            for _,r in exported.loc[exported['Strategy Hit Count'].eq(1)].iterrows():
                candidate=engine.evaluate_symbol(r.Symbol,frames[r.Symbol],check)
                assert candidate is not None
                assert r['Suggested TP Pips']==pytest.approx(candidate['tp_pips'])
                assert r['Suggested SL Pips']==pytest.approx(candidate['sl_pips'])
                side=candidate['side'];pip=.01 if r.Symbol.endswith('JPY') else .0001
                assert r['TP Price']==pytest.approx(r['Target Reference Price']+side*candidate['tp_pips']*pip)
                assert r['SL Price']==pytest.approx(r['Target Reference Price']-side*candidate['sl_pips']*pip)
                assert r['Strategy Decision']==get_strategy_decision(r)==f"{r.Direction}, TP={r['TP Price']:.5f}, SL={r['SL Price']:.5f}"
                assert r['Suggested TP Price']==r['TP Price'] and r['Suggested SL Price']==r['SL Price']
                assert r['TP_Price']==r['TP Price'] and r['SL_Price']==r['SL Price']
                if table is executable:
                    assert r['Target Price Basis']=='EXECUTABLE_QUOTE'
                    assert r['Actual Entry Quote']==quotes[r.Symbol]['ask' if side==1 else 'bid']
        assert indicative.loc[indicative['Strategy Hit Count'].eq(0),'Strategy Decision'].eq('None').all()
    decision=admit_check(frames,hits.check_at.iloc[0],{},path=tmp_path/'no_quotes.sqlite',strict_only=False)
    assert decision['selected'] is None and decision['reason']=='EXECUTABLE_QUOTE_REQUIRED'
    assert journal(tmp_path/'no_quotes.sqlite')['positions'].empty
