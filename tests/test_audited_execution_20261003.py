"""Numerical, causal and app integration checks for the uploaded audit policy."""
from dataclasses import replace
import json
import numpy as np
import pandas as pd
import pytest
from core.execution_policy_20261003 import (AuditPolicy,quote_metadata,checks_between,latest_completed,closure_deadline,get_policy)
from core.strategy_audit_20260924 import build_strategy_audit,recompute_family_evidence,STRATEGY_ALIASES
from core.hourly_four_symbol_selector_20260928 import select_portfolio_entries,attach_hourly_four_selection
from core.advanced_tpsl_engine_20261002 import add_advanced_tpsl_targets
from core.final_pair_forecast_20261003 import final_pair_labels,causal_empirical_forecast
from core.audited_portfolio_replay_20261003 import replay_portfolio


def quotes(n=96,start='2024-10-08T00:00Z',symbols=('EURUSD',)):
    records=[]
    for sym in symbols:
        t=pd.date_range(start,periods=n,freq='h',tz='UTC')
        records.append(pd.DataFrame(dict(Symbol=sym,open_time=t,open=1.1,high=1.1001,low=1.0999,close=1.1,broker_quote_verified=True)))
    return pd.concat(records,ignore_index=True)


def signals(raw):
    pieces=[]
    for sym,g in raw.groupby('Symbol'):
        g=g.reset_index(drop=True)
        m=quote_metadata(g)
        m['Symbol']=sym;m['entry_side']='BUY';m['entry_eligible']=True;m['research_entry_eligible']=True
        m['unique_family_count']=1;m['active_strategy_ids']='["S1"]';m['active_strategy_family_ids']='["F_S1"]';m['entry_origin']='STRATEGY'
        m['tp_price']=1.101;m['sl_price']=1.099;m['expected_net_pips']=3.;m['expected_net_pips_lower_bound']=1.
        for col in ['Middle Regime Bias','Higher Standard Regime Bias','Lower Regime Bias']:m[col]='BUY'
        m['S1 Entry Condition']=True;m['S1 Score']=90
        pieces.append(m)
    return pd.concat(pieces,ignore_index=True)


def test_timestamp_ownership_and_half_hour_check():
    raw=quotes(24,'2026-09-29T00:00Z');s=signals(raw)
    m=quote_metadata(raw)
    assert m.signal_available_at.iloc[3]==pd.Timestamp('2026-09-29T04:00Z')
    snap=latest_completed(s,'2026-09-29T04:00Z')
    assert snap.bar_open_time.item()==pd.Timestamp('2026-09-29T03:00Z')
    # 04:00 Rangoon = 21:30 UTC on the preceding day; most recent close is 21:00.
    snap=latest_completed(s,'2026-09-29T21:30Z')
    assert snap.bar_open_time.item()==pd.Timestamp('2026-09-29T20:00Z')
    checks=checks_between('2026-09-29','2026-09-30',replace(AuditPolicy(),entry_timezone='Asia/Rangoon'))
    assert pd.Timestamp('2026-09-29T21:30Z') in checks
    assert {x.tz_convert('Asia/Rangoon').hour for x in checks}=={4,8,12,14,16,18}


def test_weekends_invalid_duplicate_and_explicit_false_quotes():
    raw=quotes(4,'2026-10-03T00:00Z')
    assert not quote_metadata(raw).market_executable.any()
    raw=quotes(4);raw.loc[1,'high']=1.0
    raw.loc[2,'market_executable']=False
    # Explicit NaN flags are conservatively false too.
    m=quote_metadata(raw)
    assert not m.market_executable.iloc[1] and not m.market_executable.iloc[2]
    raw=quotes(4);raw.loc[1,'open_time']=raw.open_time.iloc[0]
    m=quote_metadata(raw)
    assert m.data_quality_flag.iloc[0]=='DUPLICATE_TIMESTAMP' and not m.market_executable.iloc[:2].any()


def test_default_entry_days_and_policy_contract():
    p=get_policy();assert p.relaxation==0 and p.max_new_symbols==2
    checks=checks_between('2026-09-27','2026-10-04',p)
    assert all(x.dayofweek not in (6,0) for x in checks)
    for change in ({'max_new_symbols':4},{'max_hold_hours':25},{'relaxation':.3}):
        with pytest.raises(ValueError): AuditPolicy(**change)


def test_alias_votes_and_active_score_recomputed():
    f=pd.DataFrame({'Symbol':['EURUSD'],'S51 Entry Condition':[True],'S51 Score':[80],'S52 Entry Condition':[True],'S52 Score':[100],
        'S1 Entry Condition':[False],'S1 Score':[99]})
    a=recompute_family_evidence(f)
    assert a.unique_family_count.item()==1 and a['Best Strategy Score'].item()==80
    assert json.loads(a.active_strategy_ids.item())==['S51']
    f['S51 Entry Condition']=False
    a=recompute_family_evidence(f)
    assert a.unique_family_count.item()==0 and a['Best Strategy Score'].item()==0


def test_inspect_third_fourth_and_all_held_or_ineligible_skip():
    c=signals(quotes(1,symbols=('AUDUSD','EURUSD','GBPUSD','NZDUSD')))
    p=AuditPolicy()
    chosen,skips=select_portfolio_entries(c,{'AUDUSD','EURUSD'},policy=p)
    assert list(chosen.Symbol)==['GBPUSD','NZDUSD']
    assert set(skips.reason)=={'ALREADY_HELD'}
    chosen,_=select_portfolio_entries(c,set(c.Symbol),policy=p);assert chosen.empty
    c.loc[c.Symbol=='GBPUSD','entry_eligible']=False
    chosen,_=select_portfolio_entries(c,{'AUDUSD','EURUSD'},policy=p);assert list(chosen.Symbol)==['NZDUSD']


def test_rank_fill_remains_display_only():
    f=signals(quotes(1,symbols=('AUDUSD','EURUSD','GBPUSD','NZDUSD','USDCHF')))
    f['TP Price Display']='1.10100';f['SL Price Display']='1.09900';f['S1 Entry Condition']=f.Symbol=='USDCHF'
    out=attach_hourly_four_selection(f)
    assert out['Hourly 4 Entry'].sum()==4
    assert out.loc[out.entry_origin=='RANK_FILL','entry_eligible'].eq(False).all()
    assert out.loc[out.entry_origin=='RANK_FILL','Strategy Decision'].eq('None').all()
    chosen,_=select_portfolio_entries(out,set());assert list(chosen.Symbol)==['USDCHF']


def test_label_actual_tp_price_costs_and_release_after_48_elapsed_hours():
    raw=quotes(60);raw.loc[1,'high']=1.102
    m=quote_metadata(raw);f=pd.concat([raw,m],axis=1);f['bias']='BUY';f['pip_size']=.0001
    p=replace(AuditPolicy(),spread_pips=2,slippage_pips=.5)
    lab=final_pair_labels(f,np.ones(len(f)),np.full(len(f),1.101),np.full(len(f),1.099),policy=p)
    assert lab.outcome.iloc[0]=='TP';assert lab.net_pips.iloc[0]==pytest.approx(7.5)
    assert lab.label_available_at.iloc[0]==pd.Timestamp('2024-10-10T02:00Z')
    farther=final_pair_labels(f,np.ones(len(f)),np.full(len(f),1.103),np.full(len(f),1.099),policy=p)
    assert farther.outcome.iloc[0]=='TIMEOUT'
    f['regime_family']='PULLBACK_CONTINUATION'
    fc=causal_empirical_forecast(f,lab,policy=replace(p,min_samples=2))
    assert fc.forecast_sample_count.iloc[:24].eq(0).all()
    assert fc.direction_probability.isna().all()


def test_missing_path_censors_even_when_an_early_target_hit():
    raw=quotes(60);raw.loc[1,'high']=1.102;raw=raw.drop(index=10).reset_index(drop=True)
    f=pd.concat([raw,quote_metadata(raw)],axis=1);f['bias']='BUY';f['pip_size']=.0001
    lab=final_pair_labels(f,np.ones(len(f)),np.full(len(f),1.101),np.full(len(f),1.099))
    assert lab.outcome.iloc[0]=='CENSORED' and pd.isna(lab.net_pips.iloc[0])


def test_h1_ambiguity_and_stop_gap_are_disclosed():
    raw=quotes(60);raw.loc[1,['high','low']]=[1.102,1.098]
    f=pd.concat([raw,quote_metadata(raw)],axis=1);f['bias']='BUY';f['pip_size']=.0001
    a=final_pair_labels(f,np.ones(len(f)),np.full(len(f),1.101),np.full(len(f),1.099),ambiguity='TP_FIRST')
    b=final_pair_labels(f,np.ones(len(f)),np.full(len(f),1.101),np.full(len(f),1.099),ambiguity='SL_FIRST')
    assert a.outcome.iloc[0]=='TP' and b.outcome.iloc[0]=='SL' and a.ambiguous.iloc[0]
    raw.loc[1,['high','low']]=[1.1001,1.0999]
    raw.loc[2,['open','high','low','close']]=[1.098,1.0982,1.0978,1.098]
    f=pd.concat([raw,quote_metadata(raw)],axis=1);f['bias']='BUY';f['pip_size']=.0001
    b=final_pair_labels(f,np.ones(len(f)),np.full(len(f),1.101),np.full(len(f),1.099))
    assert b.net_pips.iloc[0]==pytest.approx(-21.0) and b.stop_gap.iloc[0]


def test_24h_deadline_never_becomes_24_rows_across_a_weekend():
    deadline,closed=closure_deadline(pd.Timestamp('2026-10-02T18:00Z'),24)
    assert closed and deadline==pd.Timestamp('2026-10-02T21:00Z')
    raw=quotes(96,'2026-10-02T00:00Z');s=signals(raw)
    r=replay_portfolio(s,raw,scenario='Fixed TP/SL',tp_pips=77,sl_pips=103)
    assert not r['trades'].empty
    valid=r['trades'].dropna(subset=['net_pips'])
    assert valid.hold_hours.le(24).all()
    assert valid.exit_at.dt.dayofweek.eq(4).all()
    assert valid.exit_reason.eq('PRE_CLOSURE').all()


def test_next_open_fill_and_typed_signal_ignores_display_string():
    raw=quotes(36);s=signals(raw)
    s['Strategy Decision']='SELL-999 TP 999 SL 1'
    raw.loc[4,'high']=1.102
    r=replay_portfolio(s,raw,scenario='Fixed TP/SL',tp_pips=10,sl_pips=10,entry_end='2024-10-08T04:00Z')
    first=r['trades'].iloc[0]
    assert first.entry_at==pd.Timestamp('2024-10-08T04:00Z') and first.entry_side=='BUY'
    assert first.net_pips==pytest.approx(7.5)
    local=replace(AuditPolicy(),entry_timezone='Asia/Rangoon')
    raw=quotes(72);s=signals(raw)
    r=replay_portfolio(s,raw,scenario='Fixed TP/SL',tp_pips=10,sl_pips=10,policy=local)
    assert ((r['trades'].entry_at-r['trades'].check_at).dt.total_seconds()/60).eq(30).all()


def test_full_schema_filters_and_causality():
    n=280;raw=quotes(n,'2024-10-08');rng=np.random.default_rng(3)
    c=1.1+np.cumsum(rng.normal(0,.0003,n));o=np.r_[c[0],c[:-1]]
    raw['open']=o;raw['close']=c;raw['high']=np.maximum(o,c)+.0003;raw['low']=np.minimum(o,c)-.0003
    a=build_strategy_audit(raw,'BUY','BUY')
    required={'signal_available_at','entry_side','entry_eligible','active_strategy_ids','active_strategy_family_ids','unique_family_count','entry_origin',
        'direction_probability','probability_calibration_version','expected_net_pips','expected_net_pips_lower_bound','tp_price','sl_price','horizon_hours',
        'max_hold_hours','market_executable','spread_pips','data_quality_flag','decision_engine_version'}
    assert required.issubset(a)
    assert len([x for x in a if x.startswith('TP Filter ') and x not in {'TP Filter Reasons','TP Filter Pass Count','TP Filter Total Count'}])>=20
    assert not a.entry_eligible.any()
    assert not a['TP Filter Reasons'].str.contains('ERROR').any()
    for label in STRATEGY_ALIASES:assert not a[f'{label} Entry Condition'].any()
    for i in range(87,91):assert not a[f'S{i} Entry Condition'].any()
    for i in (9,11,20,23,29,37,42,96,106):assert not a[f'S{i} Entry Condition'].any()
    changed=raw.copy();changed.loc[220:,['open','high','low','close']]*=2
    b=build_strategy_audit(changed,'BUY','BUY')
    pd.testing.assert_frame_equal(a.iloc[:220],b.iloc[:220])
    # Removing a raw strategy recalculates scores and rescue eligibility.
    removed=build_strategy_audit(raw,'BUY','BUY',removed_strategy_ids=['S1','S51'])
    assert not removed['S1 Entry Condition'].any() and not removed['S51 Entry Condition'].any()
    assert removed['Best Strategy'].isin(['S1','S51']).eq(False).all()


def test_targets_reject_stop_exceeding_budget_without_moving_invalidation():
    raw=quotes(72);raw['low']=1.08;raw['ADX']=25
    p=replace(AuditPolicy(),max_stop_pips=10)
    out=add_advanced_tpsl_targets(raw,'BUY',symbol='EURUSD',policy=p)
    assert out['Required Structural SL'].iloc[-1]>out['Allowed Maximum SL'].iloc[-1]
    assert not out['SL Risk Cap Passed'].iloc[-1]
    assert not out['TP Research Filters Passed'].iloc[-1]
    assert 'Hard Stop Budget' in out['TP Filter Reasons'].iloc[-1]


def test_endpoint_quote_and_training_freeze_do_not_leak_future_rows():
    raw=quotes(90)
    f=pd.concat([raw,quote_metadata(raw)],axis=1);f['bias']='BUY';f['pip_size']=.0001;f['regime_family']='PULLBACK_CONTINUATION'
    p=replace(AuditPolicy(),min_samples=2)
    def make(frame):
        lab=final_pair_labels(frame,np.ones(len(frame)),np.full(len(frame),1.102),np.full(len(frame),1.098),policy=p)
        return causal_empirical_forecast(frame,lab,policy=p)
    full=make(f);prefix=make(f.iloc[:50])
    pd.testing.assert_frame_equal(full.iloc[:50],prefix)
    mutated=f.copy();mutated.loc[50:,'open']=1.10005
    changed=make(mutated)
    pd.testing.assert_frame_equal(full.iloc[:50],changed.iloc[:50])
    late=f.copy()
    late['bar_open_time']+=pd.DateOffset(years=2);late['signal_available_at']+=pd.DateOffset(years=2);late['bar_close_time']+=pd.DateOffset(years=2)
    assert make(late).forecast_sample_count.eq(0).all()  # 2026 cannot fit the frozen training model


def test_calibration_hash_guard_and_account_sizing():
    from core.calibrated_target_model_20261003 import load_validated_model
    from core.account_risk_20261003 import AccountInputs,position_lots,diagnostic_kelly
    assert load_validated_model(AuditPolicy()) is None
    account=AccountInputs('USD',1000,.01,{'EURUSD':10},{'EURUSD':100000},{'EUR':1.1,'USD':1},{'EURUSD':.01},{'EURUSD':.01},{'EURUSD':5})
    assert position_lots(account,'EURUSD',50,cost_pips=2)==.01
    assert diagnostic_kelly(.3,10,10)['nonnegative_reference_fraction']==0
    with pytest.raises(ValueError):position_lots(account,'GBPUSD',50)


def test_stale_signal_is_rejected_in_research_and_live():
    s=signals(quotes(1))
    snapshot=latest_completed(s,'2024-10-08T04:00Z')
    assert not snapshot.entry_eligible.any()
    assert not snapshot.research_entry_eligible.any()


def test_calibrated_export_matches_classifier_and_bounds_tp_payout(tmp_path):
    from research.calibration import TemporalOutcomeModel,export_model_json
    from core.calibrated_target_model_20261003 import infer_model
    n=720;rng=np.random.default_rng(7)
    x=pd.DataFrame({'signal_available_at':pd.date_range('2024-10-03',periods=n,freq='h',tz='UTC'),
        'Suggested TP Pips':25.,'Suggested SL Pips':20.,'ADX':rng.uniform(15,40,n),'ATR':rng.uniform(.0003,.001,n),
        'unique_family_count':rng.integers(1,5,n),'Entry Noise Ratio':rng.uniform(.3,2,n)})
    outcome=np.tile(['TP','SL','BIAS','TIMEOUT'],n//4)
    y=pd.DataFrame({'outcome':outcome,'label_complete':True,'label_available_at':x.signal_available_at+pd.Timedelta(hours=25),
        'net_pips':np.where(outcome=='TP',22.5,np.where(outcome=='SL',-22.5,rng.normal(-1,2,n)))})
    model=TemporalOutcomeModel().fit(x,y)
    spec=export_model_json(model,x,y,tmp_path/'model.json',AuditPolicy())
    forecast=infer_model(spec,x,np.full(n,.0025),np.full(n,.002),np.full(n,.0001))
    predicted=model.predict(x)
    for c in model.classes:np.testing.assert_allclose(forecast['p_'+c.lower()],predicted[c],rtol=1e-6,atol=1e-7)
    assert np.allclose(forecast[['p_tp','p_sl','p_bias','p_timeout']].sum(axis=1),1)
    # An excessive payout regression must not invent a candle-maximum TP payout.
    spec['payouts']['TP']['coef']=[0.]*6;spec['payouts']['TP']['intercept']=1000
    huge=infer_model(spec,x,np.full(n,.0025),np.full(n,.002),np.full(n,.0001))
    assert (huge.expected_net_pips-forecast.expected_net_pips).max()<1e-6


def test_small_integer_grid_matches_event_replay():
    from research.fixed_grid import exhaustive_search
    raw=quotes(72,symbols=('AUDUSD','EURUSD','GBPUSD','NZDUSD'));s=signals(raw);p=AuditPolicy()
    lo='2024-10-08T04:00Z';hi='2024-10-09T16:00Z'
    grid=exhaustive_search(s,raw,p,lo,hi,lo=10,hi=11)
    assert len(grid)==4
    for _,pair in grid.iterrows():
        r=replay_portfolio(s,raw,scenario='Fixed TP/SL',tp_pips=pair.TP,sl_pips=pair.SL,policy=p,entry_start=lo,entry_end=hi)
        assert pair['Net Pip']==pytest.approx(r['metrics']['Net Pip'])
        assert pair.Trades==r['metrics']['Trades']


def test_typed_download_bundle_uses_full_universe_and_total_costs():
    from core.professional_execution_backtest_20261001 import build_professional_backtest_bundle,summarize_execution_backtest
    import io,zipfile
    raw=quotes(72,symbols=('AUDUSD','EURUSD','GBPUSD','NZDUSD'));s=signals(raw)
    blob,ledger,summary=build_professional_backtest_bundle(s,raw,finder_rows=s,entry_start='2024-10-08T04:00Z',entry_end='2024-10-08T16:00Z')
    assert not ledger.empty and summary['same_candle_tp_sl_policy']=='TP_FIRST_H1_PRIMARY'
    assert np.allclose(ledger['Gross Pips']-ledger['Net Pips'],2.5)
    assert summary['round_trip_cost_pips']==2.5
    with zipfile.ZipFile(io.BytesIO(blob)) as z:assert 'next executable open' in z.read('README.txt').decode()
