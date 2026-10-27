from datetime import datetime, timezone
from pathlib import Path
import shutil

import pandas as pd

from core.resumable_build_20260928 import (
    BuildStore,
    _LocalBackend,
    chunk_windows,
    make_job,
    queue_job,
    request_resume,
    request_stop,
)


def _state(tmp_email='build-test@example.com'):
    return {
        'new7_auth_email': tmp_email,
        'timeframe': 'H1',
    }


def test_h1_chunks_are_small_and_reusable():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = chunk_windows(start, end, 30, 'H1')
    shifted = chunk_windows(datetime(2025, 1, 2, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc), 30, 'H1')
    assert first
    assert all((b - a).total_seconds() / 86400 <= 30 for a, b in first)
    overlap_keys = {(a, b) for a, b in first} & {(a, b) for a, b in shifted}
    assert len(overlap_keys) >= len(first) - 2
    assert max((b - a).total_seconds() / 3600 for a, b in first) <= 720


def test_interval_clamps_for_twelve_data_point_limit():
    m1 = chunk_windows(datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 15, tzinfo=timezone.utc), 30, 'M1')
    assert max((b - a).total_seconds() / 60 for a, b in m1) <= 3 * 1440


def test_local_job_checkpoint_stop_and_resume(tmp_path, monkeypatch):
    # Force local runtime paths into a temporary sandbox.
    import core.resumable_build_20260928 as mod
    monkeypatch.setattr(mod, '_RUNTIME_ROOT', tmp_path / 'runtime')
    monkeypatch.setattr(mod, '_LOCAL_JOBS', mod._RUNTIME_ROOT / 'jobs')
    monkeypatch.setattr(mod, '_LOCAL_OBJECTS', mod._RUNTIME_ROOT / 'objects')

    backend = _LocalBackend()
    store = BuildStore(backend=backend)
    job = make_job(_state(), symbols=['EURUSD', 'GBPUSD'], timeframe='H1', history_years=1, chunk_days=30)
    created = store.create_job(job)
    assert created['status'] == 'QUEUED'

    stopped = request_stop(store, job['id'])
    assert stopped['requested_action'] == 'STOP'
    resumed = request_resume(store, job['id'])
    assert resumed['status'] == 'QUEUED'
    assert resumed['requested_action'] is None

    persisted = store.get_job(job['id'])
    assert persisted['symbols'] == ['EURUSD', 'GBPUSD']
    assert persisted['total_chunks'] >= 24

def test_local_build_fallback_queues_without_persistent_secrets(tmp_path, monkeypatch):
    import core.resumable_build_20260928 as mod
    monkeypatch.setattr(mod, '_RUNTIME_ROOT', tmp_path / 'runtime')
    monkeypatch.setattr(mod, '_LOCAL_JOBS', mod._RUNTIME_ROOT / 'jobs')
    monkeypatch.setattr(mod, '_LOCAL_OBJECTS', mod._RUNTIME_ROOT / 'objects')
    backend = mod._LocalBackend()
    store = mod.BuildStore(backend=backend)
    job = mod.queue_job(
        store,
        {'new7_auth_email': 'fallback@example.com', 'timeframe': 'H1'},
        symbols=['EURUSD'], timeframe='H1', history_years=1, chunk_days=30,
    )
    assert job['status'] == 'QUEUED'
    assert job['storage_mode'] == 'LOCAL'
    assert job['persistent_storage'] is False
    assert 'LOCAL FALLBACK' in job['storage_notice']


def test_local_worker_launcher_is_non_blocking_and_strips_remote_backend(tmp_path, monkeypatch):
    import core.resumable_build_20260928 as mod
    monkeypatch.setattr(mod, '_RUNTIME_ROOT', tmp_path / 'runtime')
    monkeypatch.setattr(mod, '_LOCAL_JOBS', mod._RUNTIME_ROOT / 'jobs')
    monkeypatch.setattr(mod, '_LOCAL_OBJECTS', mod._RUNTIME_ROOT / 'objects')
    monkeypatch.setattr(mod, '_PROJECT_ROOT', tmp_path)
    worker_dir = tmp_path / 'worker'
    worker_dir.mkdir(parents=True)
    (worker_dir / 'run_build_worker.py').write_text('print("ok")\n', encoding='utf-8')

    state = {
        'twelve_api_key_1': 'ONE',
        'twelve_api_key_2': 'TWO',
        'enable_twelve_multi_key_loading': True,
    }
    calls = {}
    class Proc:
        pid = 4242
    def fake_popen(args, **kwargs):
        calls['args'] = args
        calls['kwargs'] = kwargs
        return Proc()
    monkeypatch.setattr(mod.subprocess, 'Popen', fake_popen)
    result = mod.launch_local_build_worker(state, 'BS-TEST')
    assert result['ok'] is True and result['pid'] == 4242
    env = calls['kwargs']['env']
    assert env['BUILD_WORKER_ONCE'] == 'true'
    assert env['TWELVE_DATA_API_KEY_1'] == 'ONE'
    assert env['TWELVE_DATA_API_KEY_2'] == 'TWO'
    assert 'SUPABASE_URL' not in env
    assert 'SUPABASE_SECRET_KEY' not in env


def test_old_completed_job_reconstructs_continuous_candles_from_checkpoints(tmp_path, monkeypatch):
    import core.resumable_build_20260928 as mod
    monkeypatch.setattr(mod, '_RUNTIME_ROOT', tmp_path / 'runtime')
    monkeypatch.setattr(mod, '_LOCAL_JOBS', mod._RUNTIME_ROOT / 'jobs')
    monkeypatch.setattr(mod, '_LOCAL_OBJECTS', mod._RUNTIME_ROOT / 'objects')
    store = mod.BuildStore(backend=mod._LocalBackend())
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)
    path = mod._chunk_key('EURUSD', 'H1', start, end)
    frame = pd.DataFrame({
        'open_time': pd.date_range(start, periods=3, freq='h'),
        'open': [1.1, 1.2, 1.3], 'high': [1.2, 1.3, 1.4],
        'low': [1.0, 1.1, 1.2], 'close': [1.15, 1.25, 1.35],
        'volume': [10, 11, 12],
    })
    mod.put_dataframe(store, path, frame)
    old_job = {
        'id': 'OLD-BUILD', 'timeframe': 'H1', 'symbols': ['EURUSD'],
        'result_manifest': [],
        'symbols_progress': {
            'EURUSD': {
                'completed_chunk_keys': [path],
                'chunk_rows': {path: 3},
            }
        },
    }
    loaded = mod.load_candle_range(store, old_job, start, end)
    assert len(loaded) == 3
    assert loaded['Symbol'].eq('EURUSD').all()
    assert loaded.attrs['source_job_id'] == 'OLD-BUILD'
