from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from core import resumable_build_20260928 as builds
from core.super_quick_field3_20260722 import _build_middle_finder_history
from core.hourly_four_symbol_selector_20260928 import attach_hourly_four_selection
from worker import run_build_worker as worker
from worker.fast_artifacts_20261002 import finalize
from ui.build_artifact_controls_20261002 import render_build_artifacts, progress_metrics

SYMBOLS = ['EURUSD','GBPUSD','USDJPY','AUDUSD','NZDUSD','USDCHF','USDCAD','EURGBP','EURJPY','GBPJPY',
           'AUDJPY','CADJPY','CHFJPY','NZDJPY','AUDNZD','EURCHF','EURAUD','EURCAD','EURNZD','GBPAUD']

@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(builds, '_RUNTIME_ROOT', tmp_path)
    monkeypatch.setattr(builds, '_LOCAL_JOBS', tmp_path / 'jobs')
    monkeypatch.setattr(builds, '_LOCAL_OBJECTS', tmp_path / 'objects')
    monkeypatch.setenv('BUILD_CPU_WORKERS', '1')
    return builds.BuildStore(backend=builds._LocalBackend())


def candles(n=360, start='2024-01-01'):
    rng=np.random.default_rng(23)
    c=1.1+np.cumsum(rng.normal(0,.0003,n));o=np.r_[c[0],c[:-1]]
    return pd.DataFrame({'open_time':pd.date_range(start,periods=n,freq='h',tz='UTC'),
        'open':o,'high':np.maximum(o,c)+.0004,'low':np.minimum(o,c)-.0004,'close':c,'volume':rng.integers(10,100,n)})


def test_fast_engine_matches_every_retained_field():
    source=candles(600)
    full=_build_middle_finder_history({'EURUSD':source},timeframe='H1',apply_selection=False)
    fast=_build_middle_finder_history({'EURUSD':source},timeframe='H1',apply_selection=False,output_mode='BACKTEST_FAST')
    assert len(fast)==len(source)
    assert len(full.columns)-len(fast.columns)==242
    for column in fast:
        pd.testing.assert_series_equal(full[column],fast[column],check_dtype=False,check_categorical=False)
    assert all(f'S{i} Entry Condition' in fast and f'S{i} Score' in fast for i in range(1,121))


def selection_frame():
    timestamps=pd.date_range('2024-01-01',periods=400,freq='h',tz='UTC')
    records=[]
    for k,symbol in enumerate(SYMBOLS):
        for i,ts in enumerate(timestamps):
            records.append({'Datetime':ts,'Completed Candle':ts,'Symbol':symbol,'Timeframe':'H1',
                'Open Price':1.1,'Highest Price':1.11,'Lowest Price':1.09,'Close Price':1.1,
                'Middle Regime Bias':'BUY' if i<167 else 'SELL','Higher Standard Regime Bias':'BUY',
                'Lower Regime Bias':'BUY','S1 Entry Condition':(i+k)%3!=0,'S1 Score':80+k%10,
                'Near Entry Score':90,'TP:SL Price Ratio':2.5,'SL Risk Cap Passed':True,
                'TP/SL Pair Quality Score':85,'SL Liquidity Safety Score':80,
                'SL Rebound To TP Rate':10,'Entry Noise Ratio':.5,'Candle After Regime Start':i%30+1})
    return pd.DataFrame(records).sort_values(['Datetime','Symbol']).reset_index(drop=True)


def test_partitioned_20_symbol_csv_matches_full_state_and_keeps_real_gaps(store):
    frame=selection_frame()
    # A real missing provider candle is retained as a gap, never fabricated.
    frame=frame.drop(frame.index[(frame['Symbol']=='GBPAUD') & frame['Datetime'].eq(pd.Timestamp('2024-01-09T00:00Z'))]).reset_index(drop=True)
    job=builds.make_job({},symbols=SYMBOLS,timeframe='M15',history_years=10,fast_build=True)
    job.update(start_date='2024-01-01T00:00:00+00:00',end_date='2024-01-17T15:00:00+00:00')
    manifest=[]
    for symbol,group in frame.groupby('Symbol'):
        path=f'{symbol}.parquet';saved=builds.put_dataframe(store,path,group)
        manifest.append(dict(saved,kind='finder_symbol',symbol=symbol,oldest=job['start_date'],newest=job['end_date']))
    artifact=finalize(job,store,manifest)
    result=pd.read_csv(BytesIO(store.get_object(artifact['path'])))
    result['Strategy Decision'] = result['Strategy Decision'].fillna('None')
    expected=attach_hourly_four_selection(frame).sort_values(['Datetime','Symbol']).reset_index(drop=True)
    assert len(result)==len(frame)==7999
    assert not result.duplicated(['Datetime','Symbol']).any()
    assert result.groupby('Datetime')['Hourly 4 Entry'].sum().eq(4).all()
    assert result.groupby('Datetime')['Symbol'].count().isin([19,20]).all()
    assert result.groupby('Datetime')['Symbol'].count().eq(19).sum()==1
    assert result.groupby('Datetime')['Hourly 4 Entry'].agg(lambda x: (~x).sum()).ge(15).all()
    for column in ['Symbol','Hourly 4 Entry','Hourly Selection Rank','Hourly Selection Score','Coverage Priority','Strategy Decision','Middle Bias SL Reach']:
        pd.testing.assert_series_equal(result[column],expected[column],check_dtype=False,check_categorical=False)
    assert artifact['hourly_population']=={'20':399,'19':1}
    assert sum(a['rows'] for a in manifest if a['kind']=='ranking_part')==len(frame)
    assert finalize(job,store,manifest)==artifact # finalized CSV reused
    compact=builds.load_finder_range(store,dict(job,result_manifest=manifest),pd.Timestamp('2024-01-08T00:00Z'),pd.Timestamp('2024-01-08T05:00Z'),include_audit=False)
    assert compact.attrs['hourly_selection_finalized'] and len(compact)==120


def test_raw_download_published_before_calculation_and_deferred_ui(store,monkeypatch):
    job=builds.make_job({},symbols=SYMBOLS,timeframe='H4',fast_build=True)
    job.update(start_date='2024-01-01T00:00:00+00:00',end_date='2024-01-02T23:00:00+00:00',chunk_days=30)
    store.create_job(job)
    class Client:
        def fetch_chunk(self,symbol,timeframe,start,end):
            return candles(int((end-start).total_seconds()/3600)+1,start)
    original=worker._build_finder_for_symbol
    calls=[]
    def checked(job,store,symbol,*args,**kwargs):
        current=store.get_job(job['id']);kinds={a['kind'] for a in current['result_manifest']}
        assert 'raw_ohlc_csv' in kinds and 'middle_ranking_csv' not in kinds
        calls.append(symbol)
        return original(job,store,symbol,*args,**kwargs)
    monkeypatch.setattr(worker,'_build_finder_for_symbol',checked)
    worker.execute_job(store,Client(),job)
    completed=store.get_job(job['id'])
    assert completed['status']=='COMPLETED', completed['last_error']
    assert len(calls)==20
    computed=pd.read_csv(BytesIO(builds.load_middle_ranking_csv(store,completed)[0]))
    assert len(computed)==960
    assert computed.groupby('Datetime')['Hourly 4 Entry'].sum().eq(4).all()
    assert computed['Entry Filter Relaxation Percent'].eq(0).all()
    assert {'S1 Entry Condition','S120 Entry Condition','S120 Score','Best Strategy','Suggested TP','Suggested SL','Strategy Decision'}.issubset(computed.columns)
    raw=next(a for a in completed['result_manifest'] if a['kind']=='raw_ohlc_csv')
    data=pd.read_csv(BytesIO(store.get_object(raw['path'])))
    assert len(data)==960 and {'Datetime','Symbol','Timeframe','Open','High','Low','Close','Volume','bar_open_time','bar_close_time','market_executable','data_quality_flag'}.issubset(data)
    assert data.groupby('Datetime')['Symbol'].count().eq(20).all()
    class UI:
        downloads=[];bars=[]
        def progress(self,value,**kwargs): self.bars.append(value)
        def caption(self,*args): pass
        def download_button(self,label,**kwargs): self.downloads.append((label,kwargs))
    ui=UI()
    monkeypatch.setattr(store,'get_object',lambda path: (_ for _ in ()).throw(AssertionError('UI rerun read giant CSV')))
    render_build_artifacts(ui,store,completed)
    assert ui.bars==[1,1]
    assert len(ui.downloads)==4
    assert any("First Half" in label for label,_ in ui.downloads)
    assert any("Second Half" in label for label,_ in ui.downloads)
    halves=[a for a in completed["result_manifest"] if a["kind"] in {"middle_ranking_first_half_csv","middle_ranking_second_half_csv"}]
    assert sum(a["rows"] for a in halves)==len(computed)
    assert all(callable(kwargs['data']) and kwargs['on_click']=='ignore' for _,kwargs in ui.downloads)
    # The same raw button is present while RUNNING and calculated data absent.
    ui=UI();ui.downloads=[];ui.bars=[]
    running=dict(completed,status='RUNNING',result_manifest=[raw])
    render_build_artifacts(ui,store,running)
    assert len(ui.downloads)==1 and 'Raw OHLC' in ui.downloads[0][0]


def test_exact_calendar_two_year_contract_and_normal_configuration(monkeypatch):
    monkeypatch.setattr(builds,'_utc_now',lambda:datetime(2026,2,28,12,30,tzinfo=timezone.utc))
    fast=builds.make_job({},symbols=['EURUSD'],timeframe='M15',history_years=10,fast_build=True)
    assert fast['timeframe']=='H1' and fast['history_years']==2
    assert pd.Timestamp(fast['start_date'])==pd.Timestamp(fast['end_date'])-pd.DateOffset(years=2)
    assert (pd.Timestamp(fast['end_date'])-pd.Timestamp(fast['start_date'])).days==731
    normal=builds.make_job({},symbols=['EURUSD'],timeframe='M15',history_years=5)
    assert normal['timeframe']=='M15' and normal['history_years']==5


def test_changed_history_uses_exact_full_prefix_not_inexact_finite_warmup(store):
    source=candles(1100)
    # Appending data recalculates the full stateful prefix; compare retained
    # overlapping tail against a full calculation, including regime counters.
    short=_build_middle_finder_history({'EURUSD':source.iloc[:1000]},timeframe='H1',apply_selection=False,output_mode='BACKTEST_FAST')
    updated=_build_middle_finder_history({'EURUSD':source},timeframe='H1',apply_selection=False,output_mode='BACKTEST_FAST')
    full=_build_middle_finder_history({'EURUSD':source},timeframe='H1',apply_selection=False)
    for column in updated:
        pd.testing.assert_series_equal(updated[column].tail(100),full[column].tail(100),check_dtype=False,check_categorical=False)
    # Existing entry features remain causal when future candles are appended.
    for column in [f'S{i} Entry Condition' for i in range(1,121)]+['Suggested TP','Suggested SL','Completed Regime Samples']:
        pd.testing.assert_series_equal(short[column],updated[column].iloc[:1000].reset_index(drop=True),check_dtype=False,check_categorical=False)


def test_missing_tail_download_only_requests_overlap_plus_new_candles(store):
    source=candles(48)
    saved=builds.put_dataframe(store,'old.parquet',source)
    start=source['open_time'].iloc[0].to_pydatetime();old_end=source['open_time'].iloc[-1].to_pydatetime();end=old_end+pd.Timedelta(hours=3)
    job={'symbols_progress':{'EURUSD':{'previous_candles':[dict(saved,kind='candle_chunk',symbol='EURUSD',oldest=start.isoformat(),newest=old_end.isoformat())]}}}
    class Client:
        calls=[]
        def fetch_chunk(self,symbol,timeframe,start,end):
            self.calls.append((start,end));return candles(4,start)
    client=Client();out=worker._fetch_missing_tail(job,store,client,'EURUSD','H1',start,end)
    assert client.calls==[(old_end,end)] and len(out)==51
    assert not out.duplicated('open_time').any()


def test_real_spawn_pool_builds_two_symbols(store, monkeypatch):
    monkeypatch.setenv('BUILD_CPU_WORKERS','2')
    monkeypatch.setattr('worker.fast_cpu_20261002.cpu_workers',lambda:2)
    job=builds.make_job({},symbols=['EURUSD','GBPUSD'],timeframe='H1',fast_build=True)
    job.update(start_date='2024-01-01T00:00:00+00:00',end_date='2024-01-02T23:00:00+00:00')
    store.create_job(job)
    class Client:
        def fetch_chunk(self,symbol,timeframe,start,end):
            return candles(int((end-start).total_seconds()/3600)+1,start)
    worker.execute_job(store,Client(),job)
    done=store.get_job(job['id'])
    assert done['status']=='COMPLETED',done['last_error']
    csv=pd.read_csv(BytesIO(builds.load_middle_ranking_csv(store,done)[0]))
    assert len(csv)==96 and csv.groupby('Datetime')['Symbol'].count().eq(2).all()


def test_download_controls_render_in_real_streamlit():
    from streamlit.testing.v1 import AppTest
    source="""
import streamlit as st
from ui.build_artifact_controls_20261002 import render_build_artifacts
class Store:
    def get_object(self, path): raise AssertionError('CSV must not be read on rerun')
job={'id':'test-job','fast_build_mode':True,'symbols':['EURUSD'], 'status':'RUNNING',
     'symbols_progress':{'EURUSD':{'status':'COMPLETE','completed_chunks':2,'total_chunks':2,
                                  'finder_status':'RUNNING','downloaded_candle_rows':100}},
     'result_manifest':[{'kind':'raw_ohlc_csv','path':'ready.csv','rows':100,'symbol_count':1}]}
render_build_artifacts(st,Store(),job)
"""
    app=AppTest.from_string(source).run()
    assert not app.exception
    assert len(app.get('progress'))==2
    assert len(app.get('download_button'))==1


def test_large_remote_csv_transport_keeps_one_exact_download(tmp_path, monkeypatch):
    monkeypatch.setattr(builds,'FILE_TRANSFER_PART_BYTES',7)
    class Remote(builds._SupabaseBackend):
        def __init__(self): self.objects={}
        def put_object(self,path,payload,**kwargs): self.objects[path]=payload
        def get_object(self,path): return self.objects[path]
    remote=Remote();store=builds.BuildStore(backend=remote)
    file=tmp_path/'input.csv';file.write_bytes(b'Datetime,Symbol,Open\n2024-01-01,EURUSD,1.2\n')
    store.put_file('result.csv',file,content_type='text/csv')
    assert store.get_object('result.csv')==file.read_bytes()
    assert all(len(data)<=7 for path,data in remote.objects.items() if '.parts/' in path)
    remote.objects['result.csv.parts/00001']=b''
    with pytest.raises(RuntimeError,match='missing or truncated'):
        store.get_object('result.csv')


def test_corrupt_raw_chunk_is_retryable_on_resume(store):
    job=builds.make_job({},symbols=['EURUSD'],timeframe='H1',fast_build=True)
    job.update(start_date='2024-01-01T00:00:00+00:00',end_date='2024-01-02T23:00:00+00:00')
    store.create_job(job)
    windows=builds.chunk_windows(pd.Timestamp(job['start_date']).to_pydatetime(),pd.Timestamp(job['end_date']).to_pydatetime(),job['chunk_days'],'H1')
    key=builds._chunk_key('EURUSD','H1',*windows[0])
    store.put_object(key,b'corrupt parquet')
    class Client:
        calls=0
        def fetch_chunk(self,symbol,timeframe,start,end):
            self.calls+=1;return candles(int((end-start).total_seconds()/3600)+1,start)
    client=Client();worker.execute_job(store,client,job)
    failed=store.get_job(job['id'])
    assert failed['status']=='FAILED' and failed['symbols_progress']['EURUSD']['invalid_chunks']==[key]
    resumed=builds.request_resume(store,job['id']);worker.execute_job(store,client,resumed)
    done=store.get_job(job['id'])
    assert done['status']=='COMPLETED',done['last_error']
    assert client.calls==1
