"""Tests for the 2026-10-07 raw OHLC fix: provider no-data gaps + partial CSV.

Covers the reported failure: a 10-year load stalls at ~70% because Twelve
Data has no data for a specific date range, with no way to download the data
loaded so far and no way for Resume to finish.
"""
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import pytest

from core import resumable_build_20260928 as builds
from core.fixed_fx_universe_20260918 import TARGET_FX_SYMBOLS
from worker import run_build_worker as worker
from worker.fast_artifacts_20261002 import finalize, _job_gap_ranges
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
    def __init__(self, no_data_symbols=()):
        self.no_data_symbols = set(no_data_symbols)

    def fetch_chunk(self, symbol, timeframe, start, end):
        if symbol in self.no_data_symbols:
            raise worker.ProviderNoDataError(
                f"Twelve Data has no data for {symbol} 2024-01-01 → 2024-01-10: no data available")
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


# ---------------------------------------------------------------------------
# Provider no-data detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    {"status": "error", "message": "No data available for the specified date range."},
    {"status": "error", "message": "The requested data is not available for your plan."},
    {"code": "400", "status": "error", "message": "Historical data is not available before 2020."},
    {"code": 404, "message": "no historical values found"},
    {"status": "error", "message": "symbol does not have data for this range"},
])
def test_is_provider_no_data_true(payload):
    assert worker._is_provider_no_data(payload) is True


@pytest.mark.parametrize("payload", [
    {"status": "error", "message": "Invalid API key"},
    {"status": "error", "message": ""},
    {"code": "429", "message": "no data, rate limit"},
    {"status": "ok", "values": []},
    {"status": "error", "values": [{"datetime": "2024-01-01"}]},
    "not a dict",
    None,
])
def test_is_provider_no_data_false(payload):
    assert worker._is_provider_no_data(payload) is False


def test_chunk_key_date_range():
    key = "historical/EURUSD/H1/chunks/20240101T000000_20240629T000000.parquet"
    assert builds.chunk_key_date_range(key) == "2024-01-01 → 2024-06-29"
    assert builds.chunk_key_date_range("weird") == "weird"


# ---------------------------------------------------------------------------
# End to end: no-data range becomes a documented gap, job reaches 100%
# ---------------------------------------------------------------------------

def test_provider_no_data_range_recorded_as_gap_and_job_completes(store, monkeypatch):
    monkeypatch.setattr(worker, '_strategy_inputs', forbid_strategy)
    job = short_job()
    store.create_job(job)
    gap_symbol = TARGET_FX_SYMBOLS[0]
    worker.execute_job(store, CandleClient(no_data_symbols={gap_symbol}), job)
    result = store.get_job(job['id'])
    assert result['status'] == 'COMPLETED', result['last_error']
    assert result['progress_percent'] == 100
    item = result['symbols_progress'][gap_symbol]
    assert item['status'] == 'COMPLETE'
    assert not item.get('failed_chunks')
    assert item['gap_chunks'], "the no-data range must be recorded as a gap"
    gap = next(iter(item['gap_chunks'].values()))
    assert 'no data' in gap['reason'].lower()

    artifact = next(a for a in result['result_manifest'] if a['kind'] == 'raw_ohlc_csv')
    assert artifact['partial'] is False
    assert gap_symbol in artifact['missing_symbols']
    assert gap_symbol in artifact['gap_ranges']
    assert 'provider no-data range(s) recorded as gaps' in artifact['coverage_note']

    data = pd.read_csv(BytesIO(store.get_object(artifact['path'])))
    assert gap_symbol not in set(data['Symbol'])
    assert set(data['Symbol']) == set(TARGET_FX_SYMBOLS[1:])

    ui = DownloadUI()
    render_build_artifacts(ui, store, result)
    assert len(ui.downloads) == 1 and 'Partial' not in ui.downloads[0][0]
    assert any('provider has no data' in caption for caption in ui.captions)


def _stub_twelve_symbol(monkeypatch):
    """fetch_chunk imports _twelve_symbol lazily; that module needs streamlit,
    which is unavailable in the test env. Stub just the symbol mapping."""
    import sys
    import types
    for name in ("core.connectors", "core.connectors.data_parts", "core.connectors.data_parts.utils"):
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setattr(sys.modules["core.connectors.data_parts.utils"], "_twelve_symbol",
                        lambda symbol: str(symbol).replace("/", ""), raising=False)


def test_fetch_chunk_no_data_raises_without_retry(monkeypatch):
    """The real client must surface ProviderNoDataError, not retry then wrap
    it in a generic RuntimeError (it subclasses RuntimeError)."""
    _stub_twelve_symbol(monkeypatch)
    monkeypatch.setenv("TWELVE_DATA_API_KEY_1", "dummy-key")
    client = worker.TwelveDataWorkerClient()

    class FakeResponse:
        status_code = 200
        headers = {}
        def __init__(self):
            self.calls = 0
        def json(self):
            self.calls += 1
            return {"status": "error",
                    "message": "No data available for the specified date range."}

    fake = FakeResponse()
    class FakeSession:
        def get(self, *args, **kwargs):
            return fake
    client.local_sessions.session = FakeSession()

    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = datetime(2020, 6, 29, tzinfo=timezone.utc)
    with pytest.raises(worker.ProviderNoDataError, match="no data"):
        client.fetch_chunk("EURUSD", "H1", start, end)
    assert fake.calls == 1, "a no-data range must not be retried"


def test_fetch_chunk_other_errors_still_retry(monkeypatch):
    _stub_twelve_symbol(monkeypatch)
    monkeypatch.setenv("TWELVE_DATA_API_KEY_1", "dummy-key")
    client = worker.TwelveDataWorkerClient()

    class FakeResponse:
        status_code = 200
        headers = {}
        def __init__(self):
            self.calls = 0
        def json(self):
            self.calls += 1
            return {"status": "error", "message": "Invalid API key"}

    fake = FakeResponse()
    class FakeSession:
        def get(self, *args, **kwargs):
            return fake
    client.local_sessions.session = FakeSession()
    monkeypatch.setattr(worker.time, "sleep", lambda *a, **k: None)

    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = datetime(2020, 1, 2, tzinfo=timezone.utc)
    with pytest.raises(RuntimeError, match="Twelve Data error"):
        client.fetch_chunk("EURUSD", "H1", start, end)
    assert fake.calls == worker.MAX_API_RETRIES


def test_job_gap_ranges_helper():
    job = {"symbols_progress": {
        "EURUSD": {"gap_chunks": {"k1": {"range": "2020-01-01 → 2020-06-01", "reason": "no data"}}},
        "GBPUSD": {"gap_chunks": {}},
    }}
    assert _job_gap_ranges(job) == {"EURUSD": [{"range": "2020-01-01 → 2020-06-01", "reason": "no data"}]}


# ---------------------------------------------------------------------------
# Partial export behavior
# ---------------------------------------------------------------------------

def test_partial_finalize_needs_no_full_universe(store, monkeypatch):
    monkeypatch.setattr(worker, '_strategy_inputs', forbid_strategy)
    job = short_job()
    store.create_job(job)
    worker.execute_job(store, CandleClient(no_data_symbols=set(TARGET_FX_SYMBOLS[:5])), job)
    result = store.get_job(job['id'])
    # With gaps the full export still completes (gap_ok); build a partial
    # directly to check the partial contract.
    manifest = [dict(a) for a in result['result_manifest'] if a['kind'] == 'candle_chunk'][:3]
    assert manifest
    manifest_symbols = {a['symbol'] for a in manifest}
    partial = finalize(result, store, manifest, raw=True, partial_ok=True)
    assert partial['kind'] == 'raw_ohlc_partial_csv'
    assert partial['partial'] is True
    assert partial['path'].endswith('_partial.csv')
    assert len(partial['missing_symbols']) == 20 - len(manifest_symbols)


def test_partial_finalize_rejects_empty_export(store):
    job = short_job()
    with pytest.raises(RuntimeError):
        finalize(job, store, [], raw=True, partial_ok=True)


def test_full_button_takes_precedence_over_partial_in_ui(store, monkeypatch):
    monkeypatch.setattr(worker, '_strategy_inputs', forbid_strategy)
    job = short_job()
    store.create_job(job)
    worker.execute_job(store, CandleClient(), job)
    result = store.get_job(job['id'])
    manifest = list(result['result_manifest'])
    full = next(a for a in manifest if a['kind'] == 'raw_ohlc_csv')
    fake_partial = dict(full, kind='raw_ohlc_partial_csv', path=full['path'] + '.partial', partial=True)
    result['result_manifest'] = manifest + [fake_partial]
    ui = DownloadUI()
    render_build_artifacts(ui, store, result)
    assert len(ui.downloads) == 1 and 'Partial' not in ui.downloads[0][0]
