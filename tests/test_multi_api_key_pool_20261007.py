"""Tests for the 2026-10-07 multi-API parallel loading fix.

The ONLY change in this fix is the data-acquisition layer: the app must
detect every configured Twelve Data API key (up to 8) and rotate/parallelize
OHLC downloads across all of them, while the output dataframe format and the
strategy engine stay byte-identical.

Covers:
- pool detects keys 1..8 (keys 5/6 were silently ignored before the fix)
- round-robin rotation across all configured keys
- rate-limited keys are skipped, no crash
- enable_twelve_multi_key_loading=False still means key 1 only
- build worker reads all env key slots 1..8
- chunk assembly from parallel workers produces the IDENTICAL frame as a
  sequential single-key download (same columns, timezone, sort, dedupe)
"""
import os

import pandas as pd
import pytest

from core.twelve_data_key_pool import (
    MAX_TWELVE_KEYS,
    TWELVE_KEY_ALIASES,
    TwelveDataKeyPool,
    resolve_twelve_key,
)
from core.data.candle_repository import normalize_frame
from worker import run_build_worker as worker


@pytest.fixture(autouse=True)
def _isolated_pool_runtime():
    # The pool keeps a module-global credit ledger so Streamlit reruns share
    # per-key counters. Reset it between tests so each test starts with full
    # per-key minute budgets.
    import core.twelve_data_key_pool as pool_module
    pool_module._GLOBAL_POOL_RUNTIME.clear()
    pool_module._GLOBAL_POOL_RUNTIME["keys"] = {}
    yield
    pool_module._GLOBAL_POOL_RUNTIME.clear()
    pool_module._GLOBAL_POOL_RUNTIME["keys"] = {}


def six_key_state():
    state = {"enable_twelve_multi_key_loading": True}
    for index in range(1, 7):
        state[f"twelve_api_key_{index}"] = f"POOL-TEST-KEY-{index}"
    return state


def test_pool_supports_up_to_eight_keys():
    assert MAX_TWELVE_KEYS == 8
    assert TWELVE_KEY_ALIASES == tuple(f"TWELVE_KEY_{i}" for i in range(1, 9))


def test_pool_detects_six_configured_keys():
    pool = TwelveDataKeyPool.from_state(six_key_state())
    detected = pool.keys()
    assert [item["alias"] for item in detected] == [f"TWELVE_KEY_{i}" for i in range(1, 7)]
    assert pool.active_key_count() == 6
    assert pool.has_available_key()


def test_resolve_twelve_key_for_indices_five_and_six(monkeypatch):
    state = six_key_state()
    assert resolve_twelve_key(state, "TWELVE_KEY_5") == "POOL-TEST-KEY-5"
    assert resolve_twelve_key(state, "TWELVE_KEY_6") == "POOL-TEST-KEY-6"
    # Env-based keys 7/8 are also resolvable.
    monkeypatch.setenv("TWELVE_DATA_API_KEY_7", "ENV-KEY-SEVEN")
    monkeypatch.setenv("TWELVE_API_KEY_8", "ENV-KEY-EIGHT")
    assert resolve_twelve_key({}, "TWELVE_KEY_7") == "ENV-KEY-SEVEN"
    assert resolve_twelve_key({}, "TWELVE_KEY_8") == "ENV-KEY-EIGHT"


def test_round_robin_rotates_across_all_six_keys():
    pool = TwelveDataKeyPool.from_state(six_key_state())
    leases = [pool.reserve_key(symbol="EURUSD") for _ in range(12)]
    assert all(lease is not None for lease in leases)
    aliases = [lease.alias for lease in leases]
    # Two full cycles through all six keys, in order.
    assert aliases == [f"TWELVE_KEY_{i}" for i in range(1, 7)] * 2
    assert aliases[0] != aliases[1] != aliases[2]


def test_rate_limited_key_is_skipped_not_crashed():
    pool = TwelveDataKeyPool.from_state(six_key_state())
    pool.mark_429("TWELVE_KEY_3", retry_after=600)
    seen = set()
    for _ in range(30):
        lease = pool.reserve_key(symbol="EURUSD")
        assert lease is not None  # other keys absorb the load
        seen.add(lease.alias)
    assert "TWELVE_KEY_3" not in seen
    assert seen == {f"TWELVE_KEY_{i}" for i in (1, 2, 4, 5, 6)}


def test_status_snapshot_covers_all_key_slots():
    pool = TwelveDataKeyPool.from_state(six_key_state())
    snapshot = pool.status_snapshot()
    assert len(snapshot) == 8
    configured = [alias for alias, info in snapshot.items() if info["configured"]]
    assert configured == [f"TWELVE_KEY_{i}" for i in range(1, 7)]
    # No raw credentials leak through the snapshot.
    for info in snapshot.values():
        assert "POOL-TEST-KEY" not in str(info.get("masked_key"))


def test_multi_key_disabled_falls_back_to_key_1_only():
    state = six_key_state()
    state["enable_twelve_multi_key_loading"] = False
    pool = TwelveDataKeyPool.from_state(state)
    detected = pool.keys()
    assert [item["alias"] for item in detected] == ["TWELVE_KEY_1"]
    lease = pool.reserve_key(symbol="EURUSD")
    assert lease is not None and lease.alias == "TWELVE_KEY_1"


def test_worker_reads_all_env_key_slots(monkeypatch):
    for index in range(1, 7):
        monkeypatch.setenv(f"TWELVE_DATA_API_KEY_{index}", f"WORKER-KEY-{index}")
    keys = worker._read_worker_keys()
    assert keys == [f"WORKER-KEY-{index}" for index in range(1, 7)]


def _provider_values(start_hour: int, count: int) -> pd.DataFrame:
    """Synthetic Twelve Data 'values' payload rows (newest-first like the API)."""
    base = pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(hours=start_hour)
    rows = []
    for offset in range(count):
        absolute_hour = start_hour + offset
        ts = base + pd.Timedelta(hours=offset)
        o = 1.1000 + absolute_hour * 0.0001
        rows.append({
            "datetime": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "open": f"{o:.5f}", "high": f"{o + 0.0003:.5f}",
            "low": f"{o - 0.0003:.5f}", "close": f"{o + 0.0001:.5f}",
            "volume": "100",
        })
    return pd.DataFrame(rows).iloc[::-1].reset_index(drop=True)


def _fetch_and_assemble(chunks: list[pd.DataFrame]) -> pd.DataFrame:
    """Same merge semantics the build worker uses for parallel chunk fetch."""
    frames = [
        normalize_frame(chunk, symbol="EURUSD", timeframe="H1", provider="TWELVE_DATA",
                        provider_symbol="EUR/USD", source_status="HISTORICAL_CHUNK")
        for chunk in chunks
    ]
    merged = pd.concat(frames, ignore_index=True)
    merged = (
        merged.sort_values("open_time", kind="mergesort")
        .drop_duplicates("open_time", keep="last")
        .reset_index(drop=True)
    )
    return merged


def test_parallel_chunk_fetch_matches_sequential_download():
    # Sequential single-key download: one request, 15 candles.
    sequential = _fetch_and_assemble([_provider_values(0, 15)])
    # Parallel multi-key download: 3 workers, overlapping chunks (0-9, 5-14, 10-14).
    parallel = _fetch_and_assemble([
        _provider_values(0, 10),
        _provider_values(5, 10),
        _provider_values(10, 5),
    ])
    assert list(parallel.columns) == list(sequential.columns)
    # The user-facing required columns: timestamp/open/high/low/close/volume/symbol
    # (the canonical store names the time column "open_time").
    present = {("timestamp" if name == "open_time" else name) for name in parallel.columns}
    assert {"timestamp", "open", "high", "low", "close", "volume", "symbol"} <= present
    # Candle identity: ignore per-request metadata (fetched_at) and compare
    # every candle-relevant column. The engine only ever reads these.
    candle_cols = ["symbol", "timeframe", "open_time", "close_time", "open", "high",
                   "low", "close", "volume", "provider", "provider_symbol",
                   "source_status", "validation_status", "is_complete"]
    pd.testing.assert_frame_equal(
        parallel[candle_cols].reset_index(drop=True),
        sequential[candle_cols].reset_index(drop=True),
    )
    # Candle alignment + timezone + sort preserved.
    assert str(parallel["open_time"].dt.tz) == "UTC"
    assert parallel["open_time"].is_monotonic_increasing
    assert not parallel["open_time"].duplicated().any()
    assert len(parallel) == 15


def test_local_twelve_keys_fallback_detects_slot_six():
    from core.resumable_build_20260928 import _local_twelve_keys
    state = {"TWELVE_DATA_API_KEY_6": "LEGACY-SIX"}
    assert "LEGACY-SIX" in _local_twelve_keys(state)
