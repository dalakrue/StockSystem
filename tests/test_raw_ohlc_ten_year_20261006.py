from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import pytest

from core import resumable_build_20260928 as builds
from core.fixed_fx_universe_20260918 import TARGET_FX_SYMBOLS
from worker import run_build_worker as worker
from ui.build_artifact_controls_20261002 import render_build_artifacts


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(builds, '_RUNTIME_ROOT', tmp_path)
    monkeypatch.setattr(builds, '_LOCAL_JOBS', tmp_path / 'jobs')
    monkeypatch.setattr(builds, '_LOCAL_OBJECTS', tmp_path / 'objects')
    return builds.BuildStore(backend=builds._LocalBackend())


def short_job():
    job = builds.make_job({}, symbols=[], timeframe='M15', raw_only=True)
    job.update(start_date='2024-01-01T00:00:00+00:00', end_date='2024-01-10T23:00:00+00:00')
    return job


class CandleClient:
    def __init__(self, fail_symbol=None):
        self.fail_symbol, self.calls = fail_symbol, []

    def fetch_chunk(self, symbol, timeframe, start, end):
        self.calls.append(symbol)
        assert timeframe == 'H1'
        if symbol == self.fail_symbol:
            raise RuntimeError('temporary provider failure')
        times = pd.date_range(start, end, freq='h')
        return pd.DataFrame(dict(open_time=times, open=1.1, high=1.2, low=1.0, close=1.15, volume=0))


class DownloadUI:
    def __init__(self):
        self.downloads, self.bars, self.captions = [], [], []

    def progress(self, value, **kwargs):
        self.bars.append((value, kwargs))

    def caption(self, text):
        self.captions.append(text)

    def warning(self, text):
        self.captions.append(text)

    def download_button(self, label, **kwargs):
        self.downloads.append((label, kwargs))


def forbid_strategy(*args, **kwargs):
    pytest.fail('Raw-only load reached strategy calculation')


def test_calendar_ten_years_fixed_twenty_symbols_independent_of_settings(monkeypatch):
    monkeypatch.setattr(builds, '_utc_now', lambda: datetime(2026, 10, 5, 13, 30, tzinfo=timezone.utc))
    job = builds.make_job({}, symbols=['XAUUSD'], timeframe='M1', history_years=10,
                          chunk_days=14, fast_build=True, raw_only=True)
    assert job['symbols'] == list(TARGET_FX_SYMBOLS)
    assert job['kind'] == builds.RAW_OHLC_KIND
    assert job['history_years'] == 10 and job['timeframe'] == 'H1'
    assert job['chunk_days'] == 180 and not job['fast_build_mode']
    assert pd.Timestamp(job['start_date']) == pd.Timestamp(job['end_date']) - pd.DateOffset(years=10)
    assert all(item['finder_status'] == 'SKIPPED' for item in job['symbols_progress'].values())
    assert all((b - a).total_seconds() / 3600 + 1 < 5000 for a, b in
               builds.chunk_windows(pd.Timestamp(job['start_date']).to_pydatetime(),
                                    pd.Timestamp(job['end_date']).to_pydatetime(), job['chunk_days'], 'H1'))


def test_raw_worker_exports_every_candle_and_download_without_calculation(store, monkeypatch):
    monkeypatch.setattr(worker, '_strategy_inputs', forbid_strategy)
    monkeypatch.setattr(worker, '_build_finder_for_symbol', forbid_strategy)
    job = short_job()
    store.create_job(job)
    client = CandleClient()
    worker.execute_job(store, client, job)
    completed = store.get_job(job['id'])
    assert completed['status'] == 'COMPLETED', completed['last_error']
    assert completed['progress_percent'] == 100
    assert set(client.calls) == set(TARGET_FX_SYMBOLS)
    manifest = completed['result_manifest']
    assert not any(a['kind'].startswith(('finder_', 'middle_ranking')) for a in manifest)
    artifact = next(a for a in manifest if a['kind'] == 'raw_ohlc_csv')
    assert artifact['symbol_count'] == 20 and artifact['history_years'] == 10
    assert artifact['path'].endswith('_10y.csv')
    data = pd.read_csv(BytesIO(store.get_object(artifact['path'])))
    assert len(data) == 20 * 240
    assert set(data['Symbol']) == set(TARGET_FX_SYMBOLS)
    assert data['Timeframe'].eq('H1').all()
    assert {'Datetime', 'Symbol', 'Timeframe', 'Open', 'High', 'Low', 'Close'}.issubset(data)
    assert data.groupby('Datetime')['Symbol'].nunique().eq(20).all()
    assert not data.duplicated(['Datetime', 'Symbol']).any()
    assert not any(c.startswith('S1 ') for c in data)
    ui = DownloadUI()
    original_get = store.get_object
    monkeypatch.setattr(store, 'get_object', lambda path: pytest.fail('UI eagerly loaded CSV'))
    render_build_artifacts(ui, store, completed)
    assert len(ui.downloads) == 1 and 'Download 10-Year Raw OHLC CSV' in ui.downloads[0][0]
    assert len(ui.bars) == 1 and ui.bars[0][0] == 1
    kwargs = ui.downloads[0][1]
    assert kwargs['file_name'] == 'raw_ohlc_all_symbols_H1_10_years.csv'
    assert callable(kwargs['data']) and kwargs['on_click'] == 'ignore'
    monkeypatch.setattr(store, 'get_object', original_get)
    assert kwargs['data']() == original_get(artifact['path'])


def test_partial_load_publishes_partial_download_and_resume_reuses_completed_chunks(store, monkeypatch):
    monkeypatch.setattr(worker, '_strategy_inputs', forbid_strategy)
    job = short_job()
    store.create_job(job)
    worker.execute_job(store, CandleClient(fail_symbol=TARGET_FX_SYMBOLS[0]), job)
    partial = store.get_job(job['id'])
    assert partial['status'] == 'PARTIAL'
    assert not any(a['kind'] == 'raw_ohlc_csv' for a in partial['result_manifest'])
    partial_artifact = next(a for a in partial['result_manifest'] if a['kind'] == 'raw_ohlc_partial_csv')
    assert partial_artifact['partial'] is True
    assert TARGET_FX_SYMBOLS[0] in partial_artifact['missing_symbols']
    assert 'data loaded so far' in partial_artifact['coverage_note'] or 'not yet downloaded' in partial_artifact['coverage_note']
    ui = DownloadUI()
    render_build_artifacts(ui, store, partial)
    assert len(ui.downloads) == 1 and 'Partial' in ui.downloads[0][0]
    kwargs = ui.downloads[0][1]
    assert kwargs['file_name'] == 'raw_ohlc_all_symbols_H1_10_years_partial.csv'
    data = pd.read_csv(BytesIO(kwargs['data']()))
    assert set(data['Symbol']) == set(TARGET_FX_SYMBOLS[1:])
    resumed = builds.request_resume(store, job['id'])
    client = CandleClient()
    worker.execute_job(store, client, resumed)
    completed = store.get_job(job['id'])
    assert completed['status'] == 'COMPLETED', completed['last_error']
    assert set(client.calls) == {TARGET_FX_SYMBOLS[0]}
    assert any(a['kind'] == 'raw_ohlc_csv' for a in completed['result_manifest'])
    assert not any(a['kind'] == 'raw_ohlc_partial_csv' for a in completed['result_manifest'])


def test_raw_job_not_confused_with_strategy_and_duplicate_click(store):
    normal = builds.queue_job(store, {}, symbols=TARGET_FX_SYMBOLS, timeframe='H1', history_years=4)
    raw = builds.queue_job(store, {}, symbols=[], timeframe='H4', raw_only=True)
    assert raw['id'] != normal['id'] and raw['kind'] == builds.RAW_OHLC_KIND
    same = builds.queue_job(store, {}, symbols=['EURUSD'], timeframe='M1', raw_only=True)
    assert same['id'] == raw['id'] and same['duplicate']


def test_provider_short_history_published_with_documented_gaps_not_failed(store, monkeypatch):
    # A provider history shorter than requested no longer fails the job. The
    # CSV is published with provider_coverage_short metadata so the UI can
    # show exactly which symbols are short instead of stranding the download.
    monkeypatch.setattr(worker, '_strategy_inputs', forbid_strategy)
    job = short_job()
    job['end_date'] = '2024-01-30T23:00:00+00:00'
    store.create_job(job)
    class ShortHistory(CandleClient):
        def fetch_chunk(self, symbol, timeframe, start, end):
            frame = super().fetch_chunk(symbol, timeframe, start, end)
            return frame.loc[frame.open_time >= pd.Timestamp('2024-01-20T00:00:00Z')]
    worker.execute_job(store, ShortHistory(), job)
    result = store.get_job(job['id'])
    assert result['status'] == 'COMPLETED', result['last_error']
    artifact = next(a for a in result['result_manifest'] if a['kind'] == 'raw_ohlc_csv')
    assert artifact['provider_coverage_short'] is True
    assert set(artifact['short_symbols']) == set(TARGET_FX_SYMBOLS)
    assert 'provider history shorter than requested' in artifact['coverage_note']
    ui = DownloadUI()
    render_build_artifacts(ui, store, result)
    assert len(ui.downloads) == 1 and 'Partial' not in ui.downloads[0][0]
    assert any('no data' in caption.lower() or 'shorter than requested' in caption for caption in ui.captions)


def test_raw_button_beside_fast_build_enabled_without_loaded_symbols(store, monkeypatch):
    from ui import field3_multisymbol_regime_summary_20260722 as panel

    class Rerun(BaseException):
        pass

    class UI:
        def __init__(self):
            self.buttons, self.column_sizes = [], []
            self.current_column = None

        def caption(self, *args): pass
        def warning(self, *args): pass
        def metric(self, *args, **kwargs): pass
        def selectbox(self, label, values, index=0, **kwargs): return values[index]
        def columns(self, count):
            self.column_sizes.append(count)
            owner = self
            class Column:
                def __init__(self, index): self.index = index
                def __enter__(self): owner.current_column = self.index
                def __exit__(self, *args): owner.current_column = None
            return [Column(i) for i in range(count)]
        def button(self, label, **kwargs):
            self.buttons.append((label, self.current_column, kwargs))
            return 'Fast Load 10-Year Raw OHLC' in label
        def rerun(self): raise Rerun()

    monkeypatch.setattr(builds, 'build_store_for_ui', lambda state: store)
    monkeypatch.setattr(panel, '_build_symbols_for_job', lambda state: [])
    launches = []
    monkeypatch.setattr(builds, 'launch_local_build_worker', lambda *args, **kwargs: launches.append(args[1]) or {'ok': True})
    ui = UI()
    state = {'timeframe': 'M15'}
    with pytest.raises(Rerun):
        panel._render_build_job_controls(ui, state)
    fast = next(b for b in ui.buttons if 'Fast Backtest Build' in b[0])
    raw = next(b for b in ui.buttons if 'Fast Load 10-Year Raw OHLC' in b[0])
    assert fast[1] == 1 and raw[1] == 2
    assert not raw[2].get('disabled', False)
    queued = builds.latest_job(store, state)
    assert queued['kind'] == builds.RAW_OHLC_KIND and queued['symbols'] == list(TARGET_FX_SYMBOLS)
    assert launches == [queued['id']]
    assert 'field3_middle_finder_history_build_20260824' not in state


def test_raw_job_does_not_hide_previous_calculated_finder(store, monkeypatch):
    from ui import field3_multisymbol_regime_summary_20260722 as panel
    strategy = builds.make_job({}, symbols=['EURUSD'], timeframe='H1')
    strategy.update(status='COMPLETED', created_at='2024-01-01T00:00:00Z',
                    result_manifest=[{'kind': 'finder_symbol', 'path': 'existing.parquet', 'strategy_engine': builds.STRATEGY_ENGINE_VERSION}])
    store.create_job(strategy)
    store.create_job(builds.make_job({}, symbols=[], timeframe='H1', raw_only=True))
    monkeypatch.setattr(builds, 'build_store_for_ui', lambda state: store)
    backend, selected = panel._latest_durable_finder_source({})
    assert backend is store and selected['id'] == strategy['id']
