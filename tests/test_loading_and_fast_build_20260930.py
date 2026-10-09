"""Functional tests for compact text, exit lifetime, incremental HTTP and worker jobs."""
from datetime import datetime, timezone
from io import BytesIO
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import pytest

from core.compact_strategy_decision_20260930 import apply_exit_notice
from core.hourly_four_symbol_selector_20260928 import attach_hourly_four_selection
from core import resumable_build_20260928 as builds
from core.data.candle_repository import normalize_frame, validate_candle
from core.connectors.data_parts import fetchers
from worker import run_build_worker as worker


def candle_frame(n, start='2024-01-01'):
    t = pd.date_range(start, periods=n, freq='h', tz='UTC')
    c = 1.1 + np.arange(n) * .000001 + .001 * np.sin(np.arange(n) / 9)
    return pd.DataFrame({'open_time': t, 'open': c, 'high': c + .001, 'low': c - .001, 'close': c, 'volume': 20})


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    monkeypatch.setattr(builds, '_RUNTIME_ROOT', tmp_path)
    monkeypatch.setattr(builds, '_LOCAL_JOBS', tmp_path / 'jobs')
    monkeypatch.setattr(builds, '_LOCAL_OBJECTS', tmp_path / 'objects')
    return builds.BuildStore(backend=builds._LocalBackend())


def test_short_selected_text_and_simultaneous_exit_on_unselected_symbol():
    t = pd.date_range('2025-01-01', periods=15, freq='h', tz='UTC')
    rows = []
    for i, ts in enumerate(t):
        for k in range(5):
            rows.append({'Symbol': f'SYM{k}', 'Completed Candle': ts, 'Timeframe': 'H1',
                         'Middle Regime Bias': 'BUY' if i == 0 else 'SELL',
                         'Strategy Hit Count': 3, 'Best Strategy Score': 90 - k,
                         'TP Price Display': '1.10000', 'SL Price Display': '1.20000'})
    out = attach_hourly_four_selection(pd.DataFrame(rows))
    assert out.groupby('Completed Candle')['Hourly 4 Entry'].sum().eq(4).all()
    assert out['Strategy Decision'].eq('None').all()  # no raw strategy evidence is present
    assert not out.entry_eligible.any()
    at_flip = out.loc[out['Completed Candle'].eq(t[1])]
    assert not at_flip['Strategy Decision'].str.contains('SL reach', case=False).any()
    assert at_flip.loc[~at_flip['Hourly 4 Entry'], 'Strategy Decision'].eq('None').all()
    at_expiry = out.loc[out['Completed Candle'].eq(t[13])]
    assert not at_expiry['Middle Bias SL Reach'].any()
    assert not out['Strategy Decision'].str.contains(r'S1|MAX|STR|RANK|#').any()
    # Reapplying and filtering retain the original event, not a new 12h timer.
    pd.testing.assert_frame_equal(apply_exit_notice(out), out)
    tail = apply_exit_notice(out.loc[out['Completed Candle'].eq(t[12])].reset_index(drop=True))
    assert tail['Middle Bias SL Reach'].all()


def test_fast_profile_is_persisted_bounded_and_uses_large_safe_chunks(local_store):
    symbols = [f'SYM{i}' for i in range(53)]
    job = builds.queue_job(local_store, {}, symbols=symbols, timeframe='H1', fast_build=True)
    saved = local_store.get_job(job['id'])
    assert saved['fast_build_mode'] is True
    assert saved['calculation_batch_rows'] == 5000
    assert saved['target_candle_rows'] is None
    assert saved['symbol_candle_targets'] == {}
    assert saved['history_years'] == 2
    assert saved['chunk_days'] == 30
    windows = builds.chunk_windows(pd.Timestamp(saved['start_date']).to_pydatetime(), pd.Timestamp(saved['end_date']).to_pydatetime(), saved['chunk_days'], 'H1')
    assert max((b-a).total_seconds()/3600 for a,b in windows) <= 4500
    again = builds.queue_job(local_store, {}, symbols=symbols, timeframe='H1', fast_build=True)
    assert again['duplicate'] and again['id'] == saved['id']


def test_worker_builds_checkpoints_reuses_and_loads_projected_selection(local_store):
    job = builds.make_job({}, symbols=['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'NZDUSD'], timeframe='H1', fast_build=True)
    # Keep a short fixture but execute the actual downloader/strategy/parquet paths.
    job.update(start_date='2024-01-01T00:00:00+00:00', end_date='2024-01-20T00:00:00+00:00', chunk_days=14,
               symbol_candle_targets={symbol: 300 for symbol in job['symbols']})
    local_store.create_job(job)
    class Client:
        def __init__(self): self.calls = 0
        def fetch_chunk(self, symbol, timeframe, start, end):
            self.calls += 1
            return normalize_frame(candle_frame(int((end-start).total_seconds()/3600)+1, start), symbol=symbol, timeframe=timeframe, provider='TWELVE_DATA')
    client = Client()
    worker.execute_job(local_store, client, job)
    done = local_store.get_job(job['id'])
    assert done['status'] == 'COMPLETED', done['last_error']
    assert sum(item['actual_candle_rows'] for item in done['symbols_progress'].values()) == 2285
    assert all(a['rows'] <= 5000 for a in done['result_manifest'])
    assert any(a['kind'] == 'candle_chunk' for a in done['result_manifest'])
    ranking_bytes, ranking_artifact = builds.load_middle_ranking_csv(local_store, done)
    assert ranking_artifact['kind'] == 'middle_ranking_csv'
    assert ranking_artifact['history_years'] == 2
    ranking_csv = pd.read_csv(BytesIO(ranking_bytes))
    assert len(ranking_csv) == ranking_artifact['rows']
    assert {'Datetime', 'Symbol', 'Strategy Decision', 'TP/SL Pair Quality Score',
            'S1 Entry Condition', 'S120 Entry Condition', 'Open Price',
            'Highest Price', 'Lowest Price', 'Close Price', 'Hourly 4 Entry',
            'Continuous OHLC Row'}.issubset(ranking_csv.columns)
    assert ranking_artifact['export_scope'] == 'ALL_SYMBOLS_ALL_CANDLES'
    assert ranking_artifact['continuous_ohlc'] is True
    assert ranking_artifact['symbol_count'] == 5
    assert ranking_artifact['rows_per_hour'] == 5
    assert ranking_artifact['entry_filter_relaxation_percent'] == 0
    assert ranking_csv.groupby('Datetime')['Symbol'].count().eq(5).all()
    assert ranking_csv.groupby('Datetime')['Hourly 4 Entry'].sum().eq(4).all()
    assert ranking_csv['Continuous OHLC Row'].all()
    assert ranking_csv.groupby('Symbol')['Datetime'].count().eq(457).all()
    candle_movie = builds.load_candle_range(
        local_store, done, pd.Timestamp(job['start_date']), pd.Timestamp(job['end_date'])
    )
    assert len(candle_movie) >= 1500
    assert candle_movie.groupby('Symbol')['Datetime'].count().ge(300).all()
    assert candle_movie.attrs['continuous_all_symbol_candles']
    full = builds.load_finder_range(local_store, done, pd.Timestamp(job['start_date']), pd.Timestamp(job['end_date']))
    compact = builds.load_finder_range(local_store, done, pd.Timestamp(job['start_date']), pd.Timestamp(job['end_date']), include_audit=False)
    assert compact.attrs['compact_audit_projection']
    assert 'S1 Signal' not in full and 'S1 Entry Condition' in compact
    for col in ('Strategy Hit Count', 'Middle Bias Flip At', 'Open Price', 'Suggested TP'):
        pd.testing.assert_series_equal(compact[col].astype(object), full[col].astype(object))
    selected_full, selected_compact = attach_hourly_four_selection(full), attach_hourly_four_selection(compact)
    for col in ('Symbol', 'Hourly 4 Entry', 'Strategy Decision'):
        pd.testing.assert_series_equal(selected_full[col].astype(object), selected_compact[col].astype(object))
    detailed = builds.load_selected_finder_audit(local_store, done, selected_compact)
    assert len(detailed) == int(selected_compact['Hourly 4 Entry'].sum())
    assert 'S120 Signal' in detailed and detailed['Hourly 4 Entry'].all()
    expected = selected_full.loc[selected_full['Hourly 4 Entry']].sort_values(['Datetime','Symbol']).reset_index(drop=True)
    detailed = detailed.sort_values(['Datetime','Symbol']).reset_index(drop=True)
    for column in ('S1 Entry Condition','S110 Entry Condition','S120 Entry Condition','Strategy Decision'):
        pd.testing.assert_series_equal(expected[column], detailed[column], check_names=False)
    previous_calls = client.calls
    worker.execute_job(local_store, client, done)
    assert client.calls == previous_calls  # completed chunks/artifacts are reused


def test_fast_build_forces_h1_continuous_export_contract(local_store):
    job = builds.make_job({}, symbols=['EURUSD', 'GBPUSD'], timeframe='H4', fast_build=True)
    assert job['timeframe'] == 'H1'
    assert job['history_years'] == 2


def test_range_read_skips_outside_parts_and_reports_corruption(local_store):
    frame = pd.DataFrame({'Datetime': pd.to_datetime(['2025-01-01'], utc=True), 'Symbol': ['EURUSD']})
    builds.put_dataframe(local_store, 'matching.parquet', frame)
    artifacts = [{'kind': 'finder_symbol', 'symbol': 'EURUSD', 'path': 'missing-outside.parquet', 'oldest': '2023-01-01', 'newest': '2023-01-02'},
                 {'kind': 'finder_symbol', 'symbol': 'EURUSD', 'path': 'matching.parquet', 'oldest': '2025-01-01', 'newest': '2025-01-01'}]
    assert len(builds.load_finder_range(local_store, {'result_manifest': artifacts}, pd.Timestamp('2025-01-01'), pd.Timestamp('2025-01-01'))) == 1
    artifacts[1]['path'] = 'missing-inside.parquet'
    with pytest.raises(RuntimeError, match='could not be read'):
        builds.load_finder_range(local_store, {'result_manifest': artifacts}, pd.Timestamp('2025-01-01'), pd.Timestamp('2025-01-01'))


def test_delta_refresh_keeps_5000_rows_and_requests_only_tail(tmp_path, monkeypatch):
    monkeypatch.setattr(fetchers, 'TWELVE_CACHE_DIR', tmp_path)
    now = pd.Timestamp.now(tz='UTC').floor('h')
    initial = candle_frame(5000, now-pd.Timedelta(hours=4999)).rename(columns={'open_time': 'time'})
    initial.to_pickle(fetchers._twelve_cache_file('EURUSD', '1h', 5000, 'key'))
    path = fetchers._twelve_cache_file('EURUSD', '1h', 5000, 'key')
    os.utime(path, (now.timestamp()-3600, now.timestamp()-3600))
    class Response:
        status_code=200; headers={}
        def json(self):
            return {'values': [{'datetime': t.strftime('%Y-%m-%d %H:%M:%S'), 'open': '1.2', 'high': '1.3', 'low': '1.1', 'close': '1.2'} for t in pd.date_range(now-pd.Timedelta(hours=2), periods=3, freq='h')[::-1]]}
    class Session:
        def __init__(self): self.requests=[]
        def get(self, url, **kwargs): self.requests.append(kwargs['params']); return Response()
    session = Session()
    monkeypatch.setattr(fetchers, '_twelve_http_session', lambda: session)
    frame, ok, message = fetchers.fetch_twelve('EURUSD', 'key', '1h', 5000)
    assert ok, message
    assert len(frame) == 5000 and frame['time'].is_unique
    assert session.requests[0]['outputsize'] == 3
    assert frame.attrs['twelve_incremental_refresh']
    assert frame.iloc[-1]['close'] == 1.2
    assert fetchers.fetch_twelve('EUR/USD', 'key', '1h', 600_000)[1]
    assert len(session.requests) == 1
    assert fetchers.peek_twelve_cache('EURUSD', 'other-key', '1h', 5000) is None


def test_vectorized_candle_validation_matches_reference():
    source = candle_frame(100)
    source.loc[2, 'high'] = 0
    source.loc[3, 'close'] = np.inf
    source.loc[4, 'open'] = -1
    source.loc[5, 'low'] = 3
    out = normalize_frame(source, symbol='EURUSD', timeframe='H1', provider='TWELVE_DATA')
    for row in out.to_dict('records'):
        ok, reason = validate_candle(row, require_complete=False)
        assert row['validation_status'] == reason
        assert (row['data_quality_score'] > 0) == ok


def test_fast_network_failure_resumes_missing_chunk_without_repeating_success(local_store):
    job=builds.make_job({}, symbols=['EURUSD'], timeframe='H1', fast_build=True)
    job.update(start_date='2024-01-01T00:00:00+00:00', end_date='2024-01-20T00:00:00+00:00', chunk_days=14,
               symbol_candle_targets={'EURUSD':300})
    local_store.create_job(job)
    class Client:
        calls=0
        def fetch_chunk(self, symbol, timeframe, start, end):
            self.calls+=1
            if self.calls==1:
                raise RuntimeError('simulated connection interruption')
            return normalize_frame(candle_frame(int((end-start).total_seconds()/3600)+1,start), symbol=symbol, timeframe=timeframe, provider='TWELVE_DATA')
    client=Client()
    worker.execute_job(local_store, client, job)
    failed=local_store.get_job(job['id'])
    assert failed['status']=='FAILED'
    assert failed['symbols_progress']['EURUSD']['failed_chunks']
    calls=client.calls
    resumed=builds.request_resume(local_store,job['id'])
    worker.execute_job(local_store,client,resumed)
    complete=local_store.get_job(job['id'])
    assert complete['status']=='COMPLETED', complete['last_error']
    assert not complete['symbols_progress']['EURUSD']['failed_chunks']
    assert client.calls==calls+1
    assert complete['symbols_progress']['EURUSD']['actual_candle_rows']==457


def test_actual_worker_http_formats_fx_and_handles_json_rate_limit(monkeypatch):
    monkeypatch.setattr(worker, '_read_worker_keys', lambda: ['fake-key-1', 'fake-key-2'])
    monkeypatch.setenv('TWELVE_DATA_MIN_REQUEST_PAUSE_SECONDS', '0')
    class Response:
        status_code=200; headers={}
        def __init__(self, payload): self.payload=payload
        def json(self): return self.payload
    class Session:
        def __init__(self): self.calls=[]
        def get(self, url, **kwargs):
            self.calls.append(kwargs['params'])
            if len(self.calls)==1:
                return Response({'status':'error','code':429,'message':'quota reached'})
            return Response({'values':[{'datetime':'2024-01-01 01:00:00','open':'1.1','high':'1.2','low':'1.0','close':'1.15'}]})
    session=Session()
    monkeypatch.setattr(worker.requests, 'Session', lambda: session)
    client=worker.TwelveDataWorkerClient()
    out=client.fetch_chunk('EURUSD','H1',datetime(2024,1,1,tzinfo=timezone.utc),datetime(2024,1,2,tzinfo=timezone.utc))
    assert len(out)==1 and out['validation_status'].eq('VALID').all()
    assert session.calls[0]['symbol']=='EUR/USD'
    assert session.calls[0]['start_date']=='2024-01-01 00:00:00'
    assert 'outputsize' not in session.calls[0]
    assert session.calls[1]['apikey']=='fake-key-2'
    assert client.key_cooldown[0]>worker.time.time()
