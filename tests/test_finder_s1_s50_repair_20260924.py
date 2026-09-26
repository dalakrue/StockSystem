"""Regression tests for Finder/UI recovery, causal strategy parity and HTTP reuse.

Run: python -m pytest -q tests/test_finder_s1_s50_repair_20260924.py
All provider responses are mocked; no credentials or live API are needed.
"""
from __future__ import annotations
import sys
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import io
import time
import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.strategy_audit_20260924 import build_strategy_audit
from core.pullback_engine_s1_s3_upgrade import STRATEGY_NAMES,evaluate_pullback_strategies,strategy_decision
from core import super_quick_field3_20260722 as fast
from core import finder_history_store_20260924 as store
from ui import field3_multisymbol_regime_summary_20260722 as ui


def candles(n=800):
    x=np.arange(n); c=1.1+x*.000015+.0015*np.sin(x/6)+np.random.default_rng(45).normal(0,.0002,n)
    o=np.r_[c[0]-.0003,c[:-1]]
    return pd.DataFrame({'open_time':pd.date_range('2025-01-01',periods=n,freq='h',tz='UTC'),
        'open':o,'high':np.maximum(o,c)+.0002,'low':np.minimum(o,c)-.0002,'close':c,
        'volume':100+np.random.default_rng(2).integers(0,150,n)})


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    for module in (fast,ui):
        monkeypatch.setattr(module,'MIDDLE_HISTORY_FILE',tmp_path/'history.parquet')
        monkeypatch.setattr(module,'MIDDLE_HISTORY_CSV_FILE',tmp_path/'history.csv')
    monkeypatch.setattr(store,'recover_saved_frames',lambda *a,**k: ({},{}))
    return tmp_path


def test_all_110_strategies_build_without_keyerror():
    history=fast._build_middle_finder_history({'EURUSD':candles()},timeframe='H1')
    assert len(history)==800
    for label in STRATEGY_NAMES:
        assert all(f'{label} {suffix}' in history for suffix in ('Entry Condition','Signal','Reason','Score'))
        assert history[f'{label} Score'].between(0,100).all()
        assert not history[f'{label} Signal'].isin(['NO DATA','WAIT']).any()
    assert list(STRATEGY_NAMES)==[f'S{i}' for i in range(1,111)]
    assert history['S1 Score'].max()>1  # prior score bug returned only 0 or 1
    assert history['Strategy Engine'].eq('middle-regime-adaptive-v4-20260926').all()
    assert history['Legacy Strategy Decision'].str.contains(r'BUY-\d+ TP\d+ SL20').any()


def test_strategy_prefix_causality_and_live_decision_parity():
    frame=candles(); full=build_strategy_audit(frame,'BUY','BUY')
    hit_positions=full.index[full['Strategy Decision'].ne('None')].tolist()
    assert hit_positions
    for pos in [80,199,399,hit_positions[-1]]:
        partial=build_strategy_audit(frame.iloc[:pos+1],'BUY','BUY')
        pd.testing.assert_series_equal(full.iloc[pos],partial.iloc[-1],check_names=False)
        assert full.iloc[pos]['Strategy Decision']==strategy_decision(evaluate_pullback_strategies(frame.iloc[:pos+1],'BUY','BUY'))
        assert full.iloc[pos]['Strategy Decision']==ui.get_strategy_decision(full.iloc[pos])
    mutated=frame.copy(); mutated.loc[600:,['open','high','low','close']]*=3
    changed=build_strategy_audit(mutated,'BUY','BUY')
    pd.testing.assert_frame_equal(full.iloc[:600],changed.iloc[:600])


def test_regime_and_full_finder_prefixes_do_not_change_when_future_is_added():
    frame=candles(700)
    full=fast._build_middle_finder_history({'EURUSD':frame},timeframe='H1')
    prefix=fast._build_middle_finder_history({'EURUSD':frame.iloc[:175]},timeframe='H1')
    pd.testing.assert_frame_equal(full.iloc[:175].reset_index(drop=True),prefix)
    current=fast._fast_standard(frame,standard='MIDDLE',window_bars=120)
    assert current['bias']==full.iloc[-1]['Middle Regime Bias']
    assert current['age']==full.iloc[-1]['Candle After Regime Start']


def test_sell_strategies_never_default_to_buy():
    frame=candles(); mirror=frame.copy()
    mirror['open']=3-frame.open; mirror['close']=3-frame.close
    mirror['high']=3-frame.low; mirror['low']=3-frame.high
    audit=build_strategy_audit(mirror,'SELL','SELL')
    assert audit['Legacy Strategy Decision'].str.startswith('SELL-').any()
    assert not audit['V4 Direction'].eq('BUY').any()
    assert not audit[[f'{s} Signal' for s in STRATEGY_NAMES]].eq('BUY').any().any()
    assert audit[[f'S{i} Entry Condition' for i in range(21,51)]].any().any()


@pytest.mark.parametrize('failure',['misaligned','spike','bad_ohlc','missing','no_pullback'])
def test_quality_gates_do_not_promote_weak_candidates(failure):
    frame=candles(); audit=build_strategy_audit(frame,'BUY','BUY')
    hit=int(audit.index[audit['Strategy Decision'].ne('None')][-1]); frame=frame.iloc[:hit+1].copy()
    assert strategy_decision(evaluate_pullback_strategies(frame,'BUY','BUY'))!='None'
    higher,middle='BUY','BUY'
    if failure=='misaligned': middle='SELL'
    if failure=='spike': frame.loc[frame.index[-1],'high']+=.1
    if failure=='bad_ohlc': frame.loc[frame.index[-1],'high']=frame.iloc[-1].low-.001
    if failure=='missing': frame.loc[frame.index[-1],'close']=np.nan
    if failure=='no_pullback':
        x=np.arange(len(frame));c=1.1+x*.0001
        frame['close']=c;frame['open']=c-.00008;frame['high']=c+.00002;frame['low']=c-.0001
    rows=evaluate_pullback_strategies(frame,higher,middle)
    assert set(rows)==set(STRATEGY_NAMES)
    assert not any(r['entry_condition'] for r in rows.values())
    assert strategy_decision(rows)=='None'


def test_finder_discovers_canonical_dynamic_symbols_and_compact_filters(isolated):
    frames={'EUR/USD':candles(240),'XAUUSD':candles(280)}
    state={'timeframe':'H1','canonical_symbol_candles':frames}
    result=ui._run_finder_history_build_on_demand(state)
    assert result['ok'],result
    history=state[fast.MIDDLE_HISTORY_STATE_KEY]
    assert len(history)==520 and set(history.Symbol)=={'EURUSD','XAUUSD'}
    restart={}; restored=ui._load_middle_regime_history(restart)
    assert len(restored)==520 and set(restored.Symbol)=={'EURUSD','XAUUSD'}
    fake=pd.DataFrame({'Symbol':['EURUSD','XAUUSD'],'Strategy Decision':['BUY-4 TP40 SL20']*2,
                       'S50 Entry Condition':[True,False],'S50 Signal':['BUY','NO ENTRY']})
    filtered=ui._filter_finder_result(fake,strategies=['S50'])
    assert filtered.Symbol.tolist()==['EURUSD']
    assert ui._run_finder_history_build_on_demand(state)['reused']


def test_live_ranking_and_finder_latest_audit_agree(isolated):
    frame=candles(); history=fast._build_middle_finder_history({'XAUUSD':frame},timeframe='H1')
    # Rank at an earlier candle while later data remains loaded: no future leak.
    historical=history.iloc[[620]].copy()
    state={'timeframe':'H1','canonical_symbol_candles':{'XAUUSD':frame}}
    live=ui._attach_live_pullback_data(historical,state).iloc[0]
    for name in ['Strategy Decision']+[f'{s} {field}' for s in STRATEGY_NAMES for field in ('Entry Condition','Signal','Reason','Score')]:
        assert live[name]==historical.iloc[0][name],name


def test_merge_keeps_timeframes_and_new_symbol_and_boolean_csv_strings(isolated,monkeypatch):
    first=fast._build_middle_finder_history({'XAUUSD':candles(100)},timeframe='H1')
    second=first.copy();second['Timeframe']='H4'
    merged=store.merge_history(first,second)
    assert len(merged)==200
    # Leave a stale Parquet file behind, then force the fallback write.
    first.to_parquet(fast.MIDDLE_HISTORY_FILE,index=False)
    monkeypatch.setattr(pd.DataFrame,'to_parquet',lambda *a,**k: (_ for _ in ()).throw(ImportError('no parquet engine')))
    saved=store.write_history(merged,fast.MIDDLE_HISTORY_FILE,fast.MIDDLE_HISTORY_CSV_FILE)
    assert saved['persisted'] and saved['format']=='csv'
    loaded,_=store.read_history(fast.MIDDLE_HISTORY_FILE,fast.MIDDLE_HISTORY_CSV_FILE)
    assert len(loaded)==200
    loaded['S50 Entry Condition']='False'
    assert not ui._ensure_required_audit_columns(loaded)['S50 Entry Condition'].any()


def test_failed_symbol_does_not_erase_success_and_signature_covers_old_corrections(isolated):
    good=candles(1100)
    result=fast._persist_middle_finder_history({}, {'EURUSD':good,'BAD':pd.DataFrame({'close':[1]})},timeframe='H1',signature='test')
    assert result['ok'] and result['status']=='PARTIAL' and result['generated_rows']==1100
    corrected=good.copy();corrected.loc[10,'close']+=.00001
    a=fast._fast_input_signature({'EURUSD':good},selected=['EURUSD'],timeframe='H1')
    b=fast._fast_input_signature({'EURUSD':corrected},selected=['EURUSD'],timeframe='H1')
    assert a!=b


def test_csv_recovery_identity_and_inclusive_range(isolated):
    frame=candles(120).rename(columns={'open_time':'Datetime','open':'Open','high':'High','low':'Low','close':'Close'})
    frame['Symbol']='NZD/JPY';frame['Timeframe']='H1';state={}
    result=ui._import_finder_candles(state,frame,'','H1')
    assert result['ok'] and result['generated_rows']==120
    history=ui._prepare_middle_history(state[fast.MIDDLE_HISTORY_STATE_KEY])
    result=ui._finder_range(history,history._FinderDatetime.min(),history._FinderDatetime.max())
    assert len(result)==120 and set(result.Symbol)=={'NZDJPY'}
    exported=pd.read_csv(io.StringIO(ui._finder_csv(result,result._FinderDatetime.min(),result._FinderDatetime.max())))
    assert len(exported)==120 and exported.columns[0]=='Symbol'
    with pytest.raises(ValueError,match='timeframe'):
        ui._import_finder_candles({},frame,'','H4')
    frames,_=store.collect_loaded_frames({'last_df':candles(60),'timeframe':'H1'})
    assert frames=={}  # Do not mislabel an unidentified fallback as AUDCAD.


def test_saved_ohlc_recovery_filters_timeframe_and_never_needs_api(tmp_path):
    target=tmp_path/'field11_similar_path_20260702'/'saved';target.mkdir(parents=True)
    data=candles(140);data['symbol']='EURUSD';data['timeframe']='H1'
    other=data.copy();other['timeframe']='H4'
    pd.concat([data,other]).to_parquet(target/'ohlc.parquet')
    frames,errors=store.recover_saved_frames('H1',tmp_path)
    assert not errors and len(frames['EURUSD'])==140
    assert frames['EURUSD'].data_source.eq('SAVED_OHLC_CACHE').all()


def test_http_connection_cache_and_concurrent_duplicate_coalescing(tmp_path,monkeypatch):
    from core.connectors.data_parts import fetchers
    class Session:
        calls=0
        def get(self,url,params,timeout):
            self.calls+=1
            assert params['timezone']=='UTC' and params['outputsize']==5000
            time.sleep(.02)
            return SimpleNamespace(status_code=200,headers={},json=lambda:{'values':[
                {'datetime':'2025-01-01 01:00:00','open':'1.1','high':'1.2','low':'1.0','close':'1.15','volume':'10'},
                {'datetime':'2025-01-01 00:00:00','open':'1.1','high':'1.2','low':'1.0','close':'1.12','volume':'11'}]})
    session=Session();monkeypatch.setattr(fetchers,'TWELVE_CACHE_DIR',tmp_path)
    monkeypatch.setattr(fetchers,'_twelve_http_session',lambda:session)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:fetchers.fetch_twelve('EURUSD','test-key','1h',8000),range(4)))
    assert all(r[1] for r in results) and session.calls==1
    assert fetchers.fetch_twelve('EUR/USD','test-key','1h',5000)[1] and session.calls==1
    assert fetchers.peek_twelve_cache('EURUSD','different-key','1h',5000) is None
    assert not fetchers.fetch_twelve('EURUSD','','1h',5000)[1]


@pytest.mark.parametrize('status,payload,phrase',[(429,{'code':429},'rate limit'),(401,{},'API key'),(200,{'status':'error','code':429,'message':'quota exceeded'},'429'),(500,{},'unavailable')])
def test_api_failures_are_explicit_and_not_cached(tmp_path,monkeypatch,status,payload,phrase):
    from core.connectors.data_parts import fetchers
    monkeypatch.setattr(fetchers,'TWELVE_CACHE_DIR',tmp_path)
    response=SimpleNamespace(status_code=status,headers={},json=lambda:payload)
    monkeypatch.setattr(fetchers,'_twelve_http_session',lambda:SimpleNamespace(get=lambda *a,**k:response))
    data,ok,message=fetchers.fetch_twelve('EURUSD','test-key','1h',100)
    assert not ok and data is None and phrase.lower() in message.lower()
    assert not list(tmp_path.glob('*.pkl'))


def test_cache_is_checked_before_reserving_api_credit(tmp_path,monkeypatch):
    from core.connectors.data_parts import fetchers
    from core.data.market_data_orchestrator import MarketDataOrchestrator
    from core.twelve_data_key_pool import TwelveDataKeyPool
    class Pool:
        def keys(self):return [{'alias':'TWELVE_KEY_1','api_key':'test-key'}]
        def reserve_key(self,**kwargs):raise AssertionError('cached read spent a credit')
        def mark_success(self,*args):pass
    monkeypatch.setattr(TwelveDataKeyPool,'from_state',lambda *a:Pool())
    frame=candles(100).rename(columns={'open_time':'time'})
    monkeypatch.setattr(fetchers,'peek_twelve_cache',lambda *a,**k:frame.copy())
    obj=object.__new__(MarketDataOrchestrator)
    result=obj._fetch_twelve(symbol='EURUSD',provider_symbol='EUR/USD',timeframe='H1',bars=100,state={})
    assert result[1] and result[3]['request_sent'] is False


def _ui_script(tmp_path,with_data):
    return f'''
import sys
sys.path.insert(0,{str(ROOT)!r})
import streamlit as st
import pandas as pd,numpy as np
from pathlib import Path
from ui import field3_multisymbol_regime_summary_20260722 as ui
from core import super_quick_field3_20260722 as fast
from core import finder_history_store_20260924 as store
store.recover_saved_frames=lambda *a,**k:({{}},{{}})
for m in (ui,fast):
 m.MIDDLE_HISTORY_FILE=Path({str(tmp_path/'ui.parquet')!r})
 m.MIDDLE_HISTORY_CSV_FILE=Path({str(tmp_path/'ui.csv')!r})
if {with_data!r} and "canonical_symbol_candles" not in st.session_state:
 x=np.arange(240);c=1.1+x*.000015+.0015*np.sin(x/6);o=np.r_[c[0]-.0003,c[:-1]]
 f=pd.DataFrame({{"open_time":pd.date_range("2025-01-01",periods=len(c),freq="h"),"open":o,"high":np.maximum(o,c)+.0002,"low":np.minimum(o,c)-.0002,"close":c}})
 st.session_state["canonical_symbol_candles"]={{"EURUSD":f,"XAUUSD":f.copy()}}
 st.session_state["timeframe"]="H1"
ui._render_finder_panel(st,st.session_state)
'''


def test_build_button_renders_rows_and_survives_streamlit_rerun(tmp_path):
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_string(_ui_script(tmp_path,True),default_timeout=40).run()
    assert not app.exception
    app.button(key='field3_middle_finder_refresh_button_20260923').click().run()
    assert not app.exception and not app.error and len(app.dataframe)==1
    assert len(app.session_state[fast.MIDDLE_HISTORY_STATE_KEY])==480
    app.run()
    assert not app.exception and not app.error and len(app.dataframe)==1
    assert any('Finder ready' in x.value for x in app.success)


def test_empty_finder_keeps_controls_and_persistent_build_error(tmp_path):
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_string(_ui_script(tmp_path,False),default_timeout=40).run()
    assert not app.exception and len(app.date_input)==2 and len(app.time_input)==2
    app.button(key='field3_middle_finder_refresh_button_20260923').click().run()
    assert not app.exception and len(app.date_input)==2
    assert any('Build Strategies:' in x.value for x in app.warning)
    app.run()
    assert any('Build Strategies:' in x.value for x in app.warning)
