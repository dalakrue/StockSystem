"""Version 4 functional, parity, migration and export regression tests."""
import io
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.middle_regime_adaptive_v4 import VERSION,build_adaptive_audit,manage_trade,pip_size
from core.strategy_audit_20260924 import build_strategy_audit
from core.pullback_engine_s1_s3_upgrade import evaluate_pullback_strategies,strategy_decision
from core import super_quick_field3_20260722 as fast
from core import finder_history_store_20260924 as store
from scripts.adaptive_v4_diagnostics import synthetic


def candles(n=420,symbol='EURUSD'):
    pip=pip_size(symbol);x=np.arange(n)
    c=(145 if pip==.01 else 1.1)+x*pip*.40+np.random.default_rng(4).normal(0,pip*1.2,n).cumsum()*.15
    o=np.r_[c[0]-pip*2,c[:-1]]
    return pd.DataFrame({'open_time':pd.date_range('2025-01-01',periods=n,freq='h',tz='UTC'),
       'open':o,'high':np.maximum(o,c)+pip*2,'low':np.minimum(o,c)-pip*2,'close':c})


def test_votes_do_not_create_family_entries_and_prefix_causality():
    f=candles();audit=build_strategy_audit(f,'BUY','BUY',symbol='EURUSD')
    assert audit['Strategy Engine'].eq(VERSION).all()
    assert audit['Market Regime'].isin(['TREND','RANGE','HIGH_VOLATILITY','LOW_VOLATILITY','TRANSITION','NO_DATA']).all()
    assert audit['Strategy Decision'].equals(audit['Adaptive Decision'])
    assert not audit['Legacy Strategy Decision'].equals(audit['Strategy Decision'])
    assert audit.loc[audit['Strategy Family'].eq('NONE'),'Strategy Decision'].eq('None').all()
    for i in (80,200,360):
        prefix=build_strategy_audit(f.iloc[:i+1],'BUY','BUY',symbol='EURUSD')
        pd.testing.assert_series_equal(audit.iloc[i],prefix.iloc[-1],check_names=False)
        assert strategy_decision(evaluate_pullback_strategies(f.iloc[:i+1],'BUY','BUY',symbol='EURUSD'))==audit.iloc[i]['Strategy Decision']


def test_direction_mirror_and_units_price_levels():
    for symbol in ('EURUSD','USDJPY'):
        f=candles(620,symbol);a=build_adaptive_audit(f,'BUY','BUY',symbol)
        origin=300 if symbol.endswith('JPY') else 3
        m=f.copy();m['open']=origin-f.open;m['close']=origin-f.close
        m['high']=origin-f.low;m['low']=origin-f.high
        b=build_adaptive_audit(m,'SELL','SELL',symbol)
        assert np.allclose(a['BUY Probability %'],b['SELL Probability %'])
        assert np.allclose(a['SELL Probability %'],b['BUY Probability %'])
        assert a['V4 Direction'].eq('BUY').equals(b['V4 Direction'].eq('SELL'))
        hits=a['V4 Direction'].eq('BUY');assert hits.any()
        assert ((a.loc[hits,'Suggested TP Price']-f.loc[hits,'close'])>0).all()
        assert ((f.loc[hits,'close']-a.loc[hits,'Suggested SL Price'])>0).all()
        assert np.allclose((a.loc[hits,'Suggested TP Price']-f.loc[hits,'close'])/pip_size(symbol),a.loc[hits,'Suggested TP'],atol=.11)
        assert (a.loc[hits,'Suggested SL']>0).all()


def test_hourly_completed_and_session_rejection():
    f=candles(210);future=pd.concat([f,pd.DataFrame([f.iloc[-1]])],ignore_index=True)
    future.loc[210,'open_time']=pd.Timestamp.now(tz='UTC').floor('h')
    got=fast._build_middle_finder_history({'EURUSD':future},timeframe='H1')
    assert len(got)==210 and got['Strategy Engine'].eq(VERSION).all()
    a=build_adaptive_audit(f,'BUY','BUY','EURUSD')
    assert a.loc[~a['Entry Session Valid'],'Adaptive Decision'].eq('None').all()
    no_time=build_adaptive_audit(f.drop(columns='open_time'),'BUY','BUY','EURUSD')
    assert no_time['Adaptive Decision'].eq('None').all()
    assert build_adaptive_audit(f,'BUY','BUY','EURUSD','H4')['Adaptive Decision'].eq('None').all()


def test_protective_management_no_hourly_cap_and_conservative_tie():
    state=manage_trade('BUY',1.1,1.09,1.12,1.101,1.089,1.09,37,.005)
    assert state['exit_reason']=='PROTECTIVE_SL' and state['exit_price']==1.09
    tied=manage_trade('SELL',1.1,1.11,1.08,1.112,1.079,1.09,2,.005)
    assert tied['exit_reason']=='PROTECTIVE_SL'
    assert manage_trade('BUY',1.1,1.09,1.12,1.106,1.101,1.105,1,.005)['stop']>=1.1
    assert manage_trade('BUY',1.1,1.09,1.12,1.102,1.099,1.1,25,.005)['exit_reason']=='TIME_DECAY'
    partial=manage_trade('BUY',1.1,1.09,1.12,1.11,1.105,1.109,4,.005)
    assert partial['partial_close_fraction']==.5
    assert manage_trade('BUY',1.1,1.09,1.12,1.11,1.105,1.109,4,.005,partial_done=True)['partial_close_fraction']==0


def test_finder_version_migration_and_ten_symbol_export(tmp_path,monkeypatch):
    frame=candles(200);fresh=fast._build_middle_finder_history({'EURUSD':frame},timeframe='H1')
    stale=fresh.copy();stale['Strategy Engine']='old';stale['Strategy Decision']='BUY-5 TP40 SL20'
    state={fast.MIDDLE_HISTORY_STATE_KEY:stale}
    monkeypatch.setattr(fast,'MIDDLE_HISTORY_FILE',tmp_path/'h.parquet')
    monkeypatch.setattr(fast,'MIDDLE_HISTORY_CSV_FILE',tmp_path/'h.csv')
    result=fast._persist_middle_finder_history(state,{'EURUSD':frame},timeframe='H1',signature='same')
    assert result['ok'] and not result['reused'] and state[fast.MIDDLE_HISTORY_STATE_KEY]['Strategy Engine'].eq(VERSION).all()
    from scripts.adaptive_v4_diagnostics import SYMBOLS
    raw=synthetic();frames={s:g.rename(columns={'Datetime':'open_time','Open':'open','High':'high','Low':'low','Close':'close'}) for s,g in raw.groupby('Symbol')}
    export=fast._build_middle_finder_history(frames,timeframe='H1')
    assert set(export.Symbol)==set(SYMBOLS) and export['Strategy Engine'].eq(VERSION).all()
    csv=pd.read_csv(io.StringIO(export.to_csv(index=False)))
    assert len(csv)==len(export) and {'Suggested TP Price','Market Regime','Strategy Family'}.issubset(csv)


def test_research_gates_reject_training_only_improvement():
    from core.adaptive_v4_research import compare_candidate,analyze_trades
    t=pd.date_range('2025-01-01',periods=120,freq='D')
    baseline=pd.DataFrame({'Entry Time':t,'Symbol':['EURUSD','USDJPY']*60,'Net Pip':[2.,-1.]*60})
    candidate=baseline.copy();candidate.loc[:88,'Net Pip']=3.;candidate.loc[89:,'Net Pip']=-5.
    review=compare_candidate(baseline,candidate,[candidate.copy(),candidate.copy()])
    assert not review['approved'] and review['candidate_unseen']['net_pip']<review['baseline_unseen']['net_pip']
    report=analyze_trades(baseline.assign(**{'Entry Hour':8,'Market Regime':'TREND','Strategy Family':'Trend continuation'}))
    assert report['version']==VERSION and report['status']=='RESEARCH_ONLY'


def test_live_finder_v4_parity_and_protective_exit_cap_removed():
    from ui import field3_multisymbol_regime_summary_20260722 as ui
    f=candles(400);history=fast._build_middle_finder_history({'EURUSD':f},timeframe='H1')
    row=history.iloc[[270]].copy()
    live=ui._attach_live_pullback_data(row,{'timeframe':'H1','canonical_symbol_candles':{'EURUSD':f}}).iloc[0]
    for col in ('Strategy Engine','Strategy Decision','Market Regime','Strategy Family','BUY Probability %','SELL Probability %','Suggested TP','Suggested SL','Suggested TP Price','Suggested SL Price'):
        a=live[col];b=row.iloc[0][col]
        assert (pd.isna(a) and pd.isna(b)) or a==b,col
    exits=pd.DataFrame({'Datetime':[pd.Timestamp('2025-01-02 09:00')]*8,'SL':['Exit (Risk Block)']*8})
    assert ui._apply_hourly_sl_exit_cap(exits)['SL'].eq('Exit (Risk Block)').all()


def test_only_approved_lagged_profile_changes_weights(tmp_path,monkeypatch):
    from core import middle_regime_adaptive_v4 as engine
    from core.adaptive_v4_research import fit_candidate_family_weights,install_approved_profile
    f=candles(620)
    base=engine.build_adaptive_audit(f,'BUY','BUY','EURUSD')
    monkeypatch.setattr(engine,'PROFILE_PATH',tmp_path/'profile.json')
    with pytest.raises(ValueError,match='gates'):
        install_approved_profile({'EURUSD':{'Trend continuation':5}}, {'approved':False},'2024-12-30','2025-01-02',tmp_path/'profile.json')
    review={'approved':True,'version':VERSION,'reason':'test only'}
    install_approved_profile({'EURUSD':{'Trend continuation':5}},review,'2025-01-10','2025-01-12',tmp_path/'profile.json')
    changed=engine.build_adaptive_audit(f,'BUY','BUY','EURUSD')
    assert changed['Strategy Profile'].ne('BASELINE').all()
    prefix=f.open_time.lt(pd.Timestamp('2025-01-12',tz='UTC'))
    assert changed.loc[prefix,'Adaptive Decision'].equals(base.loc[prefix,'Adaptive Decision'])
    assert (changed['Trade Quality Score']!=base['Trade Quality Score']).any()
    monkeypatch.setattr(engine,'PROFILE_PATH',tmp_path/'bad.json')
    (tmp_path/'bad.json').write_text('{"approved": false, "engine":"'+VERSION+'"}')
    with pytest.raises(ValueError,match='Unapproved'):
        engine.build_adaptive_audit(f,'BUY','BUY','EURUSD')
    assert fit_candidate_family_weights(pd.DataFrame())=={}
