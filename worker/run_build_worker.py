"""External Build Strategy worker.

Run this process separately from Streamlit (Render, Railway, Fly.io, a VM, etc.).
It polls durable jobs, downloads Twelve Data in reusable chunks, runs the
shared S1-S240 engine one symbol at a time, and prepares the exact two-year
continuous all-symbol H1 Finder CSV outside Streamlit.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from collections import deque
import gc
import hashlib
import json
import os
import re
import socket
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import uuid

for _thread_setting in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[_thread_setting] = "1"

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.data.candle_repository import normalize_frame, validate_candle
from core.resumable_build_20260928 import (
    BuildStore,
    is_raw_ohlc_kind,
    COMPACT_FINDER_COLUMNS,
    _chunk_key,
    _finder_key,
    _finder_part_key,
    _json_object_key,
    _middle_ranking_csv_key,
    _RUNTIME_ROOT,
    chunk_windows,
    finish_job,
    heartbeat,
    normalize_symbol,
    normalize_timeframe,
    put_dataframe,
    update_checkpoint,
)
from core.strategy_audit_20260924 import STRATEGY_ENGINE_VERSION
from core.super_quick_field3_20260722 import _build_middle_finder_history


WORKER_VERSION = "build-worker-20261007-v10-partial-csv-provider-gaps"
DEFAULT_CHUNK_DAYS = 30
MAX_API_RETRIES = 4
DEFAULT_TIMEOUT = 20.0


class ProviderNoDataError(RuntimeError):
    """Twelve Data explicitly reports no data for the requested range.

    Raised instead of retrying: the provider will never return candles for
    this range (for example the API plan's historical depth ends before the
    chunk), so the chunk is recorded as a documented provider gap rather than
    a permanent failure that stalls the whole job.
    """


# Phrases Twelve Data uses when a requested date range has no data on the
# caller's plan. Matched only against explicit error payloads that carry no
# usable "values" list, so rate limits, auth failures and server errors keep
# their existing retry behavior.
_PROVIDER_NO_DATA_MARKERS = (
    "no data",
    "not available",
    "unavailable",
    "no values",
    "no historical",
    "does not have",
    "do not have",
    "out of range",
    "beyond your plan",
    "plan limit",
    "historical data is not",
)


def _is_provider_no_data(payload: Any) -> bool:
    """True when the payload is an explicit provider 'no data' error.

    Only matches error payloads (status=error / 4xx code) with no usable
    values list. A missing/empty message is not enough to classify the range
    as a gap; those keep raising so genuine problems stay visible.
    """
    if not isinstance(payload, dict):
        return False
    values = payload.get("values")
    if isinstance(values, list) and values:
        return False
    status = str(payload.get("status") or "").strip().lower()
    code = str(payload.get("code") or "").strip()
    if status not in {"error", "no_data"} and code not in {"400", "404", "422"}:
        return False
    message = str(payload.get("message") or "").lower()
    return any(marker in message for marker in _PROVIDER_NO_DATA_MARKERS)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | pd.Timestamp) -> str:
    ts = pd.Timestamp(dt)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.isoformat()


def _read_worker_keys() -> list[str]:
    # Multi-API key pool: detect every configured Twelve Data key (1..8) so
    # parallel chunk downloads rotate across all of them. Env names follow the
    # same convention as the app-side TwelveDataKeyPool.
    values: list[str] = []
    names: list[str] = []
    for index in range(1, 9):
        names.extend((f"TWELVE_DATA_API_KEY_{index}", f"TWELVE_API_KEY_{index}"))
    names.extend(("TWELVE_DATA_API_KEY", "TWELVE_API_KEY"))
    for name in names:
        value = _env(name)
        if value and value not in values:
            values.append(value)
    return values


class TwelveDataWorkerClient:
    def __init__(self) -> None:
        self.keys = _read_worker_keys()
        if not self.keys:
            raise RuntimeError("No Twelve Data API key is configured in worker environment")
        self.cursor = 0
        self.key_lock = threading.Lock()
        self.local_sessions = threading.local()
        self.timeout = max(5.0, min(60.0, float(_env("TWELVE_DATA_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT)) or DEFAULT_TIMEOUT)))
        self.min_pause = max(0.0, float(_env("TWELVE_DATA_MIN_REQUEST_PAUSE_SECONDS", "0.20") or "0.20"))
        self.session = requests.Session()
        self.key_cooldown: dict[int, float] = {i: 0.0 for i in range(len(self.keys))}
        self.minute_limit = max(1, int(_env("TWELVE_DATA_PER_KEY_MINUTE_LIMIT", "8")))
        self.key_requests = {i: deque() for i in range(len(self.keys))}

    def _next_key_index(self) -> int:
        now = time.time()
        for index, recent in self.key_requests.items():
            while recent and recent[0] <= now - 60:
                recent.popleft()
            if len(recent) >= self.minute_limit:
                self.key_cooldown[index] = max(self.key_cooldown[index], recent[0] + 60)
        for _ in range(len(self.keys)):
            index = self.cursor % len(self.keys)
            self.cursor += 1
            if self.key_cooldown.get(index, 0.0) <= now:
                return index
        # All keys are temporarily cooled down; use the earliest expiry.
        return min(self.key_cooldown, key=self.key_cooldown.get)

    def fetch_chunk(self, symbol: str, timeframe: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
        interval_map = {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min", "H1": "1h", "H4": "4h", "D1": "1day"}
        tf = normalize_timeframe(timeframe)
        if tf not in interval_map:
            raise RuntimeError(f"Historical Twelve Data interval is unsupported: {tf}")
        interval = interval_map[tf]
        from core.connectors.data_parts.utils import _twelve_symbol
        provider_symbol = _twelve_symbol(symbol)
        last_error: Exception | None = None
        for attempt in range(MAX_API_RETRIES):
            while True:
                with self.key_lock:
                    index = self._next_key_index()
                    wait = self.key_cooldown.get(index, 0.0) - time.time()
                    if wait <= 0:
                        self.key_requests[index].append(time.time())
                        break
                time.sleep(min(wait, 1.0))
            api_key = self.keys[index]
            params = {
                "symbol": provider_symbol,
                "interval": interval,
                "start_date": pd.Timestamp(start_dt).tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S"),
                "end_date": pd.Timestamp(end_dt).tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S"),
                "apikey": api_key,
                "format": "JSON",
                "timezone": "UTC",
            }
            try:
                if not hasattr(self.local_sessions, "session"):
                    self.local_sessions.session = requests.Session()
                response = self.local_sessions.session.get("https://api.twelvedata.com/time_series", params=params, timeout=self.timeout)
                try:
                    payload = response.json()
                except Exception as exc:
                    raise RuntimeError(f"Twelve Data invalid JSON HTTP {response.status_code}") from exc
                if response.status_code == 429 or (isinstance(payload, dict) and str(payload.get("code")) == "429"):
                    retry_after = response.headers.get("Retry-After")
                    cooldown = float(retry_after) if retry_after and str(retry_after).replace(".", "", 1).isdigit() else 60.0
                    with self.key_lock:
                        self.key_cooldown[index] = time.time() + max(30.0, cooldown)
                    last_error = RuntimeError(f"Twelve Data 429; key {index + 1} cooled for {cooldown:.0f}s")
                    continue
                if response.status_code in {401, 403}:
                    raise RuntimeError("Twelve Data rejected the worker API key")
                if response.status_code >= 500:
                    last_error = RuntimeError(f"Twelve Data server error HTTP {response.status_code}")
                    time.sleep(min(2 ** attempt, 20))
                    continue
                if response.status_code >= 400:
                    message = str(payload.get("message") or payload.get("status") or "request failed") if isinstance(payload, dict) else "request failed"
                    raise RuntimeError(f"Twelve Data HTTP {response.status_code}: {message[:220]}")
                if not isinstance(payload, dict) or "values" not in payload:
                    if _is_provider_no_data(payload):
                        # Do not retry: the provider will never have this
                        # range. The caller records it as a documented gap.
                        detail = str(payload.get("message") or payload.get("status") or "no values")[:160]
                        start_label = pd.Timestamp(start_dt).tz_convert("UTC").strftime("%Y-%m-%d")
                        end_label = pd.Timestamp(end_dt).tz_convert("UTC").strftime("%Y-%m-%d")
                        raise ProviderNoDataError(f"Twelve Data has no data for {symbol} {start_label} → {end_label}: {detail}")
                    message = str(payload.get("message") or payload.get("status") or "no values") if isinstance(payload, dict) else "unexpected response"
                    raise RuntimeError(f"Twelve Data error: {message[:220]}")
                values = payload.get("values")
                if not isinstance(values, list) or not values:
                    return pd.DataFrame()
                raw = pd.DataFrame(values)
                frame = normalize_frame(
                    raw,
                    symbol=symbol,
                    timeframe=timeframe,
                    provider="TWELVE_DATA",
                    provider_symbol=symbol,
                    source_status="HISTORICAL_CHUNK",
                )
                if frame.empty:
                    raise RuntimeError("Twelve Data returned rows but they failed OHLC validation")
                # The repository validator is strict about OHLC relations; drop only bad rows, never fabricate data.
                result = frame.loc[frame["validation_status"].eq("VALID") & frame["is_complete"].eq(True)].copy()
                # API endpoints may include the boundary candle. Retain only
                # the exact requested range; never persist fabricated history.
                result = result.loc[result["open_time"].between(start_dt, end_dt)]
                if result.empty:
                    return pd.DataFrame()
                if len(result) > 5000:
                    raise RuntimeError(f"Twelve Data chunk returned {len(result):,} rows; refusing an oversized response")
                result = result.sort_values("open_time", kind="mergesort").drop_duplicates("open_time", keep="last").reset_index(drop=True)
                time.sleep(self.min_pause)
                return result
            except ProviderNoDataError:
                # Never swallowed by the retry handler below: the provider
                # will not have this range on a later attempt either.
                raise
            except (requests.Timeout, requests.RequestException, RuntimeError) as exc:
                last_error = exc
                if attempt + 1 < MAX_API_RETRIES:
                    time.sleep(min(2 ** attempt, 15))
                    continue
                break
        raise RuntimeError(str(last_error or "Twelve Data chunk failed"))


def _job_progress(job: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = job.get("symbols_progress") if isinstance(job.get("symbols_progress"), Mapping) else {}
    symbols = dict(raw)
    manifest = [dict(x) for x in job.get("result_manifest", []) if isinstance(x, Mapping)] if isinstance(job.get("result_manifest"), list) else []
    return symbols, manifest


def _stop_requested(store: BuildStore, job_id: str) -> bool:
    latest = store.get_job(job_id) or {}
    return str(latest.get("requested_action") or "").upper() == "STOP"


def _persist_symbol_state(store: BuildStore, job_id: str, symbol: str, payload: Mapping[str, Any]) -> None:
    data = json.dumps(dict(payload), ensure_ascii=False, indent=2, default=str).encode("utf-8")
    store.put_object(_json_object_key(job_id, symbol), data, content_type="application/json", upsert=True)


def _global_chunk_counts(job: Mapping[str, Any]) -> tuple[int, dict[str, int]]:
    tf = normalize_timeframe(job["timeframe"])
    start = pd.Timestamp(job["start_date"]).to_pydatetime().astimezone(timezone.utc)
    end = pd.Timestamp(job["end_date"]).to_pydatetime().astimezone(timezone.utc)
    chunk_days = int(job.get("chunk_days") or DEFAULT_CHUNK_DAYS)
    counts = {symbol: len(chunk_windows(start, end, chunk_days, tf)) for symbol in job["symbols"]}
    return max(1, sum(counts.values())), counts


def _fetch_missing_tail(job, store, client, symbol, timeframe, start, end):
    """Extend a prior open cache bucket by fetching only its missing tail."""
    item = (job.get('symbols_progress') or {}).get(symbol) or {}
    previous = [] if item.get('invalid_chunks') else item.get('previous_candles') or []
    for artifact in reversed(previous):
        if (pd.Timestamp(artifact.get('oldest')) == pd.Timestamp(start)
                and pd.Timestamp(start) < pd.Timestamp(artifact.get('newest')) < pd.Timestamp(end)
                and store.object_exists(artifact['path'])):
            cached = pd.read_parquet(BytesIO(store.get_object(artifact['path'])))
            newest = pd.Timestamp(artifact['newest'])
            # Re-fetch one overlap candle to detect provider corrections at the seam.
            delta = client.fetch_chunk(symbol, timeframe, newest.to_pydatetime(), end)
            if delta.empty:
                return cached
            combined = pd.concat([cached, delta], ignore_index=True, sort=False)
            return combined.sort_values('open_time', kind='mergesort').drop_duplicates('open_time', keep='last').reset_index(drop=True)
    return client.fetch_chunk(symbol, timeframe, start, end)


class _PrefetchClient:
    """Bounded I/O futures across all configured Twelve Data keys. Parent alone publishes chunks/checkpoints."""
    def __init__(self, job, store, client, symbol):
        self.client, self.job, self.store, self.symbol = client, job, store, symbol
        # Worker fan-out scales with the detected multi-API key pool (up to 8),
        # but never below 1. Per-key per-minute limits are still enforced by
        # TwelveDataWorkerClient._next_key_index, so more keys = more parallel
        # requests, never more pressure on a single key.
        key_count = max(1, len(getattr(client, "keys", None) or [1]))
        default_workers = min(8, key_count)
        self.workers = max(1, min(8, int(_env('BUILD_DOWNLOAD_WORKERS', str(default_workers)))))
        self.pool = ThreadPoolExecutor(max_workers=self.workers)
        windows = chunk_windows(pd.Timestamp(job['start_date']).to_pydatetime(), pd.Timestamp(job['end_date']).to_pydatetime(), int(job['chunk_days']), job['timeframe'])
        self.pending = {}
        self.windows = iter([(start, end) for start, end in windows
            if _chunk_key(symbol, job['timeframe'], start, end) in (((job.get('symbols_progress') or {}).get(symbol) or {}).get('invalid_chunks') or [])
            or not store.object_exists(_chunk_key(symbol, job['timeframe'], start, end))
            and not store.object_exists(_chunk_key(symbol, job['timeframe'], start, end).rsplit('.', 1)[0] + '.empty')])
        self._fill()

    def _fill(self):
        while len(self.pending) < self.workers:
            try:
                start, end = next(self.windows)
            except StopIteration:
                break
            key = (_iso(start), _iso(end))
            self.pending[key] = self.pool.submit(_fetch_missing_tail, self.job, self.store, self.client, self.symbol, self.job['timeframe'], start, end)

    def fetch_chunk(self, symbol, timeframe, start, end):
        future = self.pending.pop((_iso(start), _iso(end)), None)
        try:
            return future.result() if future is not None else _fetch_missing_tail(self.job, self.store, self.client, symbol, timeframe, start, end)
        finally:
            self._fill()

    def close(self):
        for future in self.pending.values():
            future.cancel()
        self.pool.shutdown(wait=True, cancel_futures=True)


def _download_symbol_chunks(
    job: Mapping[str, Any],
    store: BuildStore,
    client: TwelveDataWorkerClient,
    symbol: str,
    progress: dict[str, Any],
) -> bool:
    """Download/verify one symbol's durable chunks; never assemble other symbols."""
    job_id = str(job["id"])
    tf = normalize_timeframe(job["timeframe"])
    start = pd.Timestamp(job["start_date"]).to_pydatetime().astimezone(timezone.utc)
    end = pd.Timestamp(job["end_date"]).to_pydatetime().astimezone(timezone.utc)
    chunk_days = int(job.get("chunk_days") or DEFAULT_CHUNK_DAYS)
    windows = chunk_windows(start, end, chunk_days, tf)
    item = dict(progress.get(symbol) or {})
    chunk_rows = dict(item.get("chunk_rows") or {})
    item.setdefault("status", "WAITING")
    item.setdefault("completed_chunk_keys", [])
    item.setdefault("failed_chunks", [])
    completed_keys = set(str(x) for x in item.get("completed_chunk_keys", []) if x)
    failed_chunks = {str(x) for x in item.get("failed_chunks", []) if x}
    item["total_chunks"] = len(windows)

    invalid_chunks = set(item.get("invalid_chunks") or [])
    if item.get("status") == "COMPLETE" and not invalid_chunks and len(completed_keys) >= len(windows):
        # A prior run finished the historical stage. Verify durable objects
        # before trusting the checkpoint; a deleted/missing object is rebuilt
        # from Twelve Data instead of propagating a corrupt checkpoint.
        durable_complete = all(
            store.object_exists(_chunk_key(symbol, tf, chunk_start, chunk_end))
            or store.object_exists(_chunk_key(symbol, tf, chunk_start, chunk_end).rsplit(".", 1)[0] + ".empty")
            for chunk_start, chunk_end in windows
        )
        if durable_complete:
            return True

    total_global, global_counts = _global_chunk_counts(job)
    prior_completed = sum(int((progress.get(sym) or {}).get("completed_chunks") or 0) for sym in job["symbols"] if sym != symbol)

    for index, (chunk_start, chunk_end) in enumerate(windows, start=1):
        if _stop_requested(store, job_id):
            item["status"] = "PAUSED"
            progress[symbol] = item
            _persist_symbol_state(store, job_id, symbol, item)
            update_checkpoint(
                store, job_id, symbols_progress=progress, current_symbol=symbol, current_chunk=index - 1,
                progress_percent=(90.0 if is_raw_ohlc_kind(job.get('kind')) else 50.0) * (prior_completed + len(completed_keys)) / total_global,
                current_stage=f"Historical Download · {symbol} · paused after chunk checkpoint",
                worker_id=job.get("worker_id"),
            )
            return False

        key = _chunk_key(symbol, tf, chunk_start, chunk_end)
        empty_marker = key.rsplit(".", 1)[0] + ".empty"
        item.update({"status": "RUNNING", "current_chunk": index, "last_chunk_key": key})
        try:
            if key not in invalid_chunks and key in completed_keys and (store.object_exists(key) or store.object_exists(empty_marker)):
                pass
            elif key not in invalid_chunks and (store.object_exists(key) or store.object_exists(empty_marker)):
                completed_keys.add(key)
            else:
                part = client.fetch_chunk(symbol, tf, chunk_start, chunk_end) if isinstance(client, _PrefetchClient) else _fetch_missing_tail(job, store, client, symbol, tf, chunk_start, chunk_end)
                if part.empty:
                    # Persist a tiny marker for market-closed ranges so they are
                    # not downloaded again in a later job.
                    store.put_object(empty_marker, b"EMPTY_CHUNK\n", content_type="text/plain", upsert=True)
                else:
                    put_dataframe(store, key, part)
                chunk_rows[key] = int(len(part))
                invalid_chunks.discard(key)
                item["invalid_chunks"] = sorted(invalid_chunks)
                del part
            if key not in chunk_rows:
                if store.object_exists(key):
                    cached_part = pd.read_parquet(BytesIO(store.get_object(key)), columns=["open_time"])
                    chunk_rows[key] = int(len(cached_part))
                    del cached_part
                else:
                    chunk_rows[key] = 0
            completed_keys.add(key)
            failed_chunks.discard(key)
        except ProviderNoDataError as exc:
            # Twelve Data explicitly has no data for this range (for example
            # the API plan's historical depth ends before this chunk). Persist
            # an empty marker like a market closure, record the gap for the
            # export report, and keep the job moving. This is what lets a
            # 10-year load reach 100% instead of stalling at the same range on
            # every resume, and the gap stays skipped on later resumes.
            store.put_object(empty_marker, f"NO_PROVIDER_DATA\n{exc}\n".encode("utf-8"), content_type="text/plain", upsert=True)
            chunk_rows[key] = 0
            gaps = dict(item.get("gap_chunks") or {})
            gaps[key] = {
                "range": f"{_iso(chunk_start)} → {_iso(chunk_end)}",
                "reason": str(exc)[:220],
            }
            item["gap_chunks"] = gaps
            invalid_chunks.discard(key)
            item["invalid_chunks"] = sorted(invalid_chunks)
            completed_keys.add(key)
            failed_chunks.discard(key)
            item["chunk_rows"] = chunk_rows
            item["downloaded_candle_rows"] = sum(chunk_rows.values())
            item["completed_chunks"] = len(completed_keys)
            item["completed_chunk_keys"] = sorted(completed_keys)
            item["failed_chunks"] = sorted(failed_chunks)
            item["oldest_downloaded"] = min(
                [x for x in [item.get("oldest_downloaded"), _iso(chunk_start)] if x],
            )
            item["newest_downloaded"] = max(
                [x for x in [item.get("newest_downloaded"), _iso(chunk_end)] if x],
            )
            if not failed_chunks and len(completed_keys) == len(windows):
                item["status"] = "COMPLETE"
                item["error"] = None
            else:
                item["status"] = "RUNNING"
            progress[symbol] = item
            _persist_symbol_state(store, job_id, symbol, item)
            completed_total = prior_completed + len(completed_keys)
            update_checkpoint(
                store, job_id, symbols_progress=progress, current_symbol=symbol, current_chunk=index,
                progress_percent=(90.0 if is_raw_ohlc_kind(job.get('kind')) else 50.0) * completed_total / total_global,
                current_stage=f"Historical Download · {symbol} · chunk {index}/{len(windows)}: provider has no data — recorded as gap",
                worker_id=job.get("worker_id"),
            )
            heartbeat(store, job, stage=f"Historical Download · {symbol} · gap recorded for chunk {index}/{len(windows)}")
            continue
        except Exception as exc:
            invalid_chunks.add(key)
            item["invalid_chunks"] = sorted(invalid_chunks)
            failed_chunks.add(key)
            item["status"] = "FAILED"
            item["failed_chunks"] = sorted(failed_chunks)
            item["completed_chunk_keys"] = sorted(completed_keys)
            item["completed_chunks"] = len(completed_keys)
            item["error"] = f"Chunk {index}/{len(windows)}: {type(exc).__name__}: {exc}"
            progress[symbol] = item
            _persist_symbol_state(store, job_id, symbol, item)
            update_checkpoint(
                store, job_id, symbols_progress=progress, current_symbol=symbol, current_chunk=index,
                progress_percent=(90.0 if is_raw_ohlc_kind(job.get('kind')) else 50.0) * (prior_completed + len(completed_keys)) / total_global,
                current_stage=f"Historical Download · {symbol} · chunk {index}/{len(windows)} failed; remaining symbols continue",
                last_error=item["error"], worker_id=job.get("worker_id"),
            )
            # Continue to the next chunk so one transient range does not stop the
            # entire build. The failed chunk is retried on the next Resume/worker pass.
            continue

        item["chunk_rows"] = chunk_rows
        item["downloaded_candle_rows"] = sum(chunk_rows.values())
        item["completed_chunks"] = len(completed_keys)
        item["completed_chunk_keys"] = sorted(completed_keys)
        item["failed_chunks"] = sorted(failed_chunks)
        item["oldest_downloaded"] = min(
            [x for x in [item.get("oldest_downloaded"), _iso(chunk_start)] if x],
        )
        item["newest_downloaded"] = max(
            [x for x in [item.get("newest_downloaded"), _iso(chunk_end)] if x],
        )
        if not failed_chunks and len(completed_keys) == len(windows):
            item["status"] = "COMPLETE"
            item["error"] = None
        else:
            item["status"] = "RUNNING"
        progress[symbol] = item
        _persist_symbol_state(store, job_id, symbol, item)
        completed_total = prior_completed + len(completed_keys)
        update_checkpoint(
            store, job_id, symbols_progress=progress, current_symbol=symbol, current_chunk=index,
            progress_percent=(90.0 if is_raw_ohlc_kind(job.get('kind')) else 50.0) * completed_total / total_global,
            current_stage=f"Historical Download · {symbol} · Chunk {index}/{len(windows)} saved",
            worker_id=job.get("worker_id"),
        )
        heartbeat(store, job, stage=f"Historical Download · {symbol} · saved chunk {index}/{len(windows)}")

    progress[symbol] = item
    return item.get("status") == "COMPLETE" and not failed_chunks


def _load_symbol_from_chunks(
    job: Mapping[str, Any], store: BuildStore, symbol: str, progress: Mapping[str, Any]
) -> pd.DataFrame:
    """Materialize exactly one chronological symbol frame from durable chunks."""
    tf = normalize_timeframe(job["timeframe"])
    start = pd.Timestamp(job["start_date"]).to_pydatetime().astimezone(timezone.utc)
    end = pd.Timestamp(job["end_date"]).to_pydatetime().astimezone(timezone.utc)
    chunk_days = int(job.get("chunk_days") or DEFAULT_CHUNK_DAYS)
    windows = chunk_windows(start, end, chunk_days, tf)
    completed_keys = {str(x) for x in (progress.get("completed_chunk_keys") or []) if x}
    parts: list[pd.DataFrame] = []
    for index, (chunk_start, chunk_end) in enumerate(windows, start=1):
        key = _chunk_key(symbol, tf, chunk_start, chunk_end)
        empty_marker = key.rsplit(".", 1)[0] + ".empty"
        if key not in completed_keys and not store.object_exists(key) and not store.object_exists(empty_marker):
            raise RuntimeError(f"Missing durable historical chunk {index}/{len(windows)} for {symbol}")
        if store.object_exists(empty_marker) and not store.object_exists(key):
            continue
        payload = store.get_object(key)
        try:
            frame = pd.read_parquet(BytesIO(payload), columns=["open_time", "open", "high", "low", "close", "volume"])
            prices = frame[['open', 'high', 'low', 'close']].apply(pd.to_numeric, errors='coerce')
            if not (np.isfinite(prices).all().all() and prices.gt(0).all().all()
                    and prices['high'].ge(prices[['open','close','low']].max(axis=1)).all()
                    and prices['low'].le(prices[['open','close','high']].min(axis=1)).all()):
                raise RuntimeError('Cached chunk contains invalid OHLC')
        except Exception:
            if isinstance(progress, dict):
                progress['invalid_chunks'] = sorted(set(progress.get('invalid_chunks') or []) | {key})
                progress['status'] = 'FAILED'
            raise
        finally:
            del payload
        if not frame.empty:
            parts.append(frame)
        del frame
    if not parts:
        return pd.DataFrame()
    frame = pd.concat(parts, ignore_index=True, sort=False)
    del parts
    if "open_time" not in frame.columns:
        raise RuntimeError(f"Historical artifact for {symbol} has no open_time column")
    frame["open_time"] = pd.to_datetime(frame["open_time"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["open_time"]).sort_values("open_time", kind="mergesort").drop_duplicates("open_time", keep="last").reset_index(drop=True)
    frame = frame.loc[frame["open_time"].between(start, end)].reset_index(drop=True)
    frame["data_source"] = "TWELVE_DATA"
    return frame


def _sync_candle_manifest(
    job: Mapping[str, Any],
    store: BuildStore,
    progress: Mapping[str, Any],
    manifest: list[dict[str, Any]],
) -> None:
    """Publish the complete raw-candle inventory as a first-class result.

    Historical chunks were always durable, but older builds exposed only the
    derived Finder parts in ``result_manifest``.  Registering every non-empty
    chunk makes the all-symbol candle movie discoverable by the UI/backtester
    while preserving the existing four-signal-per-hour selection flags inside
    the new all-symbol, all-candle Finder export.
    """
    tf = normalize_timeframe(job["timeframe"])
    start = pd.Timestamp(job["start_date"]).to_pydatetime().astimezone(timezone.utc)
    end = pd.Timestamp(job["end_date"]).to_pydatetime().astimezone(timezone.utc)
    windows = chunk_windows(start, end, int(job.get("chunk_days") or DEFAULT_CHUNK_DAYS), tf)
    manifest[:] = [item for item in manifest if str(item.get("kind") or "") != "candle_chunk"]
    for symbol in [normalize_symbol(value) for value in job.get("symbols") or []]:
        item = progress.get(symbol) if isinstance(progress, Mapping) else None
        if not isinstance(item, Mapping):
            continue
        completed = {str(value) for value in item.get("completed_chunk_keys") or [] if value}
        chunk_rows = item.get("chunk_rows") if isinstance(item.get("chunk_rows"), Mapping) else {}
        for chunk_start, chunk_end in windows:
            path = _chunk_key(symbol, tf, chunk_start, chunk_end)
            if path not in completed or not store.object_exists(path):
                continue
            manifest.append({
                "kind": "candle_chunk",
                "symbol": symbol,
                "timeframe": tf,
                "path": path,
                "rows": int(chunk_rows.get(path) or 0),
                "oldest": _iso(chunk_start),
                "newest": _iso(chunk_end),
                "source": "TWELVE_DATA",
                "continuous_history": True,
                "created_at": _iso(_utc_now()),
            })

def _build_finder_for_symbol(job: Mapping[str, Any], store: BuildStore, symbol: str, candles: pd.DataFrame, progress: dict[str, Any], manifest: list[dict[str, Any]], *, prepared_path: str | None = None) -> bool:
    if _stop_requested(store, str(job["id"])):
        progress[symbol]["finder_status"] = "PAUSED"
        return False
    if candles.empty:
        progress[symbol]["finder_status"] = "FAILED"
        progress[symbol]["error"] = "NO_VALID_HISTORICAL_CANDLES"
        return False
    tf = normalize_timeframe(job["timeframe"])
    item = progress[symbol]
    prior_paths = [str(x) for x in (item.get("finder_paths") or []) if x]
    if item.get("finder_status") == "COMPLETE" and prior_paths and all(store.object_exists(path) for path in prior_paths):
        return True
    input_hash = hashlib.sha256(pd.util.hash_pandas_object(candles, index=False).values.tobytes()).hexdigest()
    previous = item.get("previous_finder") or {}
    reusable = previous.get("artifacts") or []
    if (previous.get("input_hash") == input_hash and reusable
            and all(a.get("strategy_engine")==STRATEGY_ENGINE_VERSION and bool(a.get("strict_only",False))==bool(job.get("strict_only",False)) for a in reusable)
            and all(store.object_exists(a["path"]) for a in reusable)):
        manifest[:] = [a for a in manifest if not (a.get("kind") == "finder_symbol" and a.get("symbol") == symbol)]
        manifest.extend(reusable)
        item.update(finder_status="COMPLETE", finder_paths=[a["path"] for a in reusable],
                    finder_rows=sum(a["rows"] for a in reusable), actual_candle_rows=len(candles), input_hash=input_hash, error=None)
        return True
    item["input_hash"] = input_hash
    item["finder_status"] = "RUNNING"
    item["calculation_batch_rows"] = int(job.get("calculation_batch_rows") or 5000)
    update_checkpoint(
        store, str(job["id"]), symbols_progress=progress, current_symbol=symbol, current_chunk=int(item.get("completed_chunks") or 0),
        progress_percent=50.0 + 50.0 * (sum(1 for x in job["symbols"] if (progress.get(x) or {}).get("finder_status") == "COMPLETE") / max(1, len(job["symbols"]))),
        current_stage=f"Strategy Build · {symbol} · S1–S240", worker_id=job.get("worker_id"),
    )
    generated = pd.DataFrame()
    try:
        # IMPORTANT: the protected strategy function is called once per symbol
        # on its full chronological history. Splitting the input into 5,000-row
        # independent calls would reset causal state and change S1-S240 output.
        generated = (pd.read_parquet(prepared_path) if prepared_path else
                     _build_middle_finder_history({symbol: candles}, timeframe=tf, apply_selection=False,
                         output_mode="BACKTEST_FAST" if job.get("fast_build_mode") else "FULL",strict_only=bool(job.get("strict_only",False))))
        if generated.empty:
            raise RuntimeError("FINDER_BUILD_RETURNED_EMPTY")
        if len(generated) != len(candles):
            raise RuntimeError("FINDER_BUILD_DROPPED_SOURCE_CANDLES")
        engine_hash = hashlib.sha256((str(STRATEGY_ENGINE_VERSION)+str(bool(job.get("strict_only",False)))).encode("utf-8")).hexdigest()[:12]
        # Finder output is persisted in <=5,000-row parts so Streamlit can later
        # retrieve only the requested date range instead of downloading one huge
        # symbol artifact into RAM.
        old_prefix = [x for x in manifest if not (str(x.get("symbol")) == symbol and str(x.get("kind")) == "finder_symbol")]
        manifest[:] = old_prefix
        finder_paths: list[str] = []
        batch_rows = min(5000, max(1, int(job.get("calculation_batch_rows") or 5000)))
        for part_index, start_row in enumerate(range(0, len(generated), batch_rows)):
            if _stop_requested(store, str(job["id"])):
                item["finder_status"] = "PAUSED"
                return False
            part = generated.iloc[start_row:start_row + batch_rows]
            path = _finder_part_key(symbol, tf, f"{STRATEGY_ENGINE_VERSION}-{engine_hash}", str(job["id"]), part_index)
            saved = put_dataframe(store, path, part)
            oldest = pd.to_datetime(part["Datetime"], errors="coerce", utc=True).min()
            newest = pd.to_datetime(part["Datetime"], errors="coerce", utc=True).max()
            manifest.append({
                "kind": "finder_symbol", "symbol": symbol, "timeframe": tf, "path": path,
                "part_index": part_index, "rows": int(saved["rows"]), "bytes": int(saved["bytes"]),
                "oldest": _iso(oldest) if pd.notna(oldest) else None,
                "newest": _iso(newest) if pd.notna(newest) else None,
                "strategy_engine": STRATEGY_ENGINE_VERSION, "strict_only": bool(job.get("strict_only",False)), "output_mode": "BACKTEST_FAST" if job.get("fast_build_mode") else "FULL", "created_at": _iso(_utc_now()),
            })
            finder_paths.append(path)
            update_checkpoint(store, str(job["id"]), symbols_progress=progress, current_symbol=symbol,
                              current_chunk=int(item.get("completed_chunks") or 0), progress_percent=50.0 + 45.0 * sum(1 for x in job["symbols"] if progress.get(x, {}).get("finder_status") == "COMPLETE") / len(job["symbols"]),
                              current_stage=f"Saving Parquet · {symbol} · saved part {part_index + 1}",
                              result_manifest=manifest, worker_id=job.get("worker_id"))
            del part
        oldest = pd.to_datetime(candles["open_time"], utc=True).min()
        newest = pd.to_datetime(candles["open_time"], utc=True).max()
        item["actual_candle_rows"] = int(len(candles))
        item["coverage_days"] = round((newest - oldest).total_seconds() / 86400, 2)
        item["coverage_start"], item["coverage_end"] = _iso(oldest), _iso(newest)
        item["one_year_coverage"] = bool(item["coverage_days"] >= 364)
        item.update({"finder_status": "COMPLETE", "finder_rows": int(len(generated)), "finder_path": finder_paths[0] if finder_paths else None, "finder_paths": finder_paths, "finder_parts": len(finder_paths), "error": None})
        _persist_symbol_state(store, str(job["id"]), symbol, item)
        return bool(finder_paths)
    except Exception as exc:
        item["finder_status"] = "FAILED"
        item["error"] = f"{type(exc).__name__}: {exc}"
        _persist_symbol_state(store, str(job["id"]), symbol, item)
        return False
    finally:
        try:
            del generated
        except Exception:
            pass
        gc.collect()


def _build_middle_ranking_csv(
    job: Mapping[str, Any],
    store: BuildStore,
    manifest: list[dict[str, Any]],
) -> dict[str, Any]:
    from worker.fast_artifacts_20261002 import finalize
    def report(done, total, rows):
        latest = store.get_job(str(job['id'])) or job
        update_checkpoint(store, str(job['id']), symbols_progress=latest.get('symbols_progress') or {},
                          current_symbol='', current_chunk=0, progress_percent=95 + 4 * done / total,
                          current_stage=f'Hourly Top-4 ranking / finalizing CSV · {done}/{total} partitions · {rows:,} rows',
                          result_manifest=manifest, worker_id=job.get('worker_id'))
    return finalize(job, store, manifest, on_progress=report,
                    should_stop=lambda: _stop_requested(store, str(job['id'])))


def _strategy_inputs(job, store, progress, manifest):
    """Yield at most two computed symbols; checkpoints are owned by the parent."""
    from worker.fast_cpu_20261002 import compute_symbol, cpu_workers
    from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
    import multiprocessing
    import tempfile
    workers = cpu_workers() if job.get('fast_build_mode') else 1
    if workers == 1:
        for symbol in job['symbols']:
            item = progress.get(symbol) or {}
            if item.get('status') != 'COMPLETE':
                yield symbol, pd.DataFrame(), None, None
                continue
            try:
                yield symbol, _load_symbol_from_chunks(job, store, symbol, item), None, None
            except Exception as error:
                yield symbol, pd.DataFrame(), None, error
        return
    with tempfile.TemporaryDirectory(prefix='strategy-cpu-') as directory:
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn')) as executor:
            pending = {}
            symbols = iter(job['symbols'])
            exhausted = False
            while pending or not exhausted:
                while len(pending) < workers and not exhausted:
                    try:
                        symbol = next(symbols)
                    except StopIteration:
                        exhausted = True
                        break
                    if _stop_requested(store, str(job['id'])):
                        return
                    item = progress.get(symbol) or {}
                    if item.get('status') != 'COMPLETE':
                        yield symbol, pd.DataFrame(), None, None
                        continue
                    try:
                        candles = _load_symbol_from_chunks(job, store, symbol, item)
                        previous = item.get('previous_finder') or {}
                        digest = hashlib.sha256(pd.util.hash_pandas_object(candles, index=False).values.tobytes()).hexdigest()
                        if item.get('finder_status') == 'COMPLETE' or (previous.get('input_hash') == digest and previous.get('artifacts')):
                            yield symbol, candles, None, None
                            continue
                        input_file = str(Path(directory) / (symbol + '-input.parquet'))
                        output_file = str(Path(directory) / (symbol + '-result.parquet'))
                        candles.to_parquet(input_file, index=False)
                        del candles
                        future = executor.submit(compute_symbol, symbol, input_file, output_file, job['timeframe'], bool(job.get('strict_only',False)))
                        pending[future] = symbol, input_file
                        item['finder_status'] = 'RUNNING'
                        active = ', '.join(value[0] for value in pending.values())
                        completed = sum(progress.get(sym, {}).get('finder_status') == 'COMPLETE' for sym in job['symbols'])
                        update_checkpoint(store, str(job['id']), symbols_progress=progress, current_symbol=active, current_chunk=0,
                            progress_percent=50 + 45 * completed / len(job['symbols']),
                            current_stage=f'Calculating S1–S240 · {active} · {len(pending)} CPU workers',
                            result_manifest=manifest, worker_id=job.get('worker_id'))
                    except Exception as error:
                        yield symbol, pd.DataFrame(), None, error
                if not pending:
                    continue
                done, _ = wait(pending, timeout=2, return_when=FIRST_COMPLETED)
                if not done:
                    # Renew liveness even during long symbol computations.
                    heartbeat(store, job)
                    if _stop_requested(store, str(job['id'])):
                        for future in pending:
                            future.cancel()
                        return
                    continue
                for future in done:
                    symbol, input_file = pending.pop(future)
                    try:
                        result_path = future.result()
                        yield symbol, pd.read_parquet(input_file), result_path, None
                    except Exception as error:
                        yield symbol, pd.DataFrame(), None, error


def _publish_raw_partial_csv(store, job, progress, manifest, *, on_progress=None, should_stop=None):
    """Best-effort partial 10-year raw CSV from whatever chunks are durable.

    Never raises: a stalled or stopped load must still finish with a usable
    checkpoint. Returns the published artifact, or None when there is nothing
    to export yet.
    """
    try:
        _sync_candle_manifest(job, store, progress, manifest)
        if not any(isinstance(item, Mapping) and item.get("kind") == "candle_chunk" for item in manifest):
            return None
        from worker.fast_artifacts_20261002 import finalize
        # finalize reads provider gaps from job["symbols_progress"]; the live
        # progress dict is newer than the job snapshot taken at claim time.
        job_view = {**job, "symbols_progress": progress}
        return finalize(job_view, store, manifest, raw=True, partial_ok=True,
                        on_progress=on_progress, should_stop=should_stop)
    except Exception:
        return None


def _manifest_has_partial_raw_csv(manifest) -> bool:
    return any(isinstance(item, Mapping) and item.get("kind") == "raw_ohlc_partial_csv" for item in manifest or [])


def execute_job(store: BuildStore, client: TwelveDataWorkerClient, job: Mapping[str, Any]) -> None:
    job_id = str(job["id"])
    progress, manifest = _job_progress(job)
    if not is_raw_ohlc_kind(job.get('kind')):
        obsolete=[a for a in manifest if a.get('kind') in ('finder_symbol','ranking_part','middle_ranking_csv','middle_ranking_first_half_csv','middle_ranking_second_half_csv') and a.get('strategy_engine') != STRATEGY_ENGINE_VERSION]
        stale={a.get('symbol') for a in obsolete if a.get('kind')=='finder_symbol'}
        for symbol in stale:
            if symbol in progress:progress[symbol].update(finder_status='PENDING',finder_paths=[],finder_path=None)
        manifest=[a for a in manifest if a not in obsolete]
    worker_id = str(job.get("worker_id") or socket.gethostname())
    symbols = [normalize_symbol(s) for s in (job.get("symbols") or []) if normalize_symbol(s)]
    completed_finder = 0
    total_global, _ = _global_chunk_counts(job)
    raw_only = is_raw_ohlc_kind(job.get('kind'))
    try:
        # --------------------------- Stage A ---------------------------
        # Finish durable historical storage for every symbol first. This is a
        # strict stage boundary: Finder never calls Twelve Data.
        update_checkpoint(
            store, job_id, symbols_progress=progress,
            current_symbol=symbols[0] if symbols else "", current_chunk=0,
            progress_percent=float(job.get("progress_percent") or 0),
            current_stage="Stage A · Historical Download",
            result_manifest=manifest, worker_id=worker_id,
        )
        for symbol in symbols:
            if _stop_requested(store, job_id):
                finish_job(store, job_id, status="PAUSED", current_stage="Paused safely after historical checkpoint", progress_percent=float(job.get("progress_percent") or 0), symbols_progress=progress, result_manifest=manifest)
                return
            # Use concurrency only with the synchronized rate-limited HTTP client.
            downloader = _PrefetchClient(job, store, client, symbol) if isinstance(client, TwelveDataWorkerClient) else client
            try:
                ok = _download_symbol_chunks(job, store, downloader, symbol, progress)
            finally:
                if isinstance(downloader, _PrefetchClient):
                    downloader.close()
            if not ok:
                # Keep processing other symbols; failed/missing ranges are isolated
                # and are retried from their persisted chunk list after Resume.
                progress[symbol]["finder_status"] = "SKIPPED" if raw_only else "WAITING"
                update_checkpoint(
                    store, job_id, symbols_progress=progress, current_symbol=symbol,
                    current_chunk=int((progress[symbol]).get("current_chunk") or 0),
                    progress_percent=float(job.get("progress_percent") or 0),
                    current_stage=f"Stage A · Historical Download · {symbol} incomplete; continuing",
                    result_manifest=manifest, last_error=(progress[symbol]).get("error"), worker_id=worker_id,
                )
        _sync_candle_manifest(job, store, progress, manifest)
        download_complete = all(progress.get(sym, {}).get('status') == 'COMPLETE' for sym in symbols)
        if _stop_requested(store, job_id):
            if raw_only:
                # The user stopped at e.g. 70%: publish a partial CSV from the
                # downloaded chunks so the data loaded so far is downloadable.
                _publish_raw_partial_csv(store, job, progress, manifest,
                                         should_stop=lambda: False)
            finish_job(store, job_id, status='PAUSED', current_stage='Paused after raw download checkpoint',
                       progress_percent=90 if raw_only else 49, symbols_progress=progress, result_manifest=manifest)
            return
        full_raw_artifact = None
        if download_complete and (job.get('fast_build_mode') or raw_only):
            from worker.fast_artifacts_20261002 import finalize, ArtifactCorruptionError
            update_checkpoint(store, job_id, symbols_progress=progress, current_symbol='', current_chunk=0,
                progress_percent=90 if raw_only else 49, current_stage=(f"Finalizing {job.get('range_label') or '10-year'} raw OHLC CSV" if raw_only else 'Finalizing raw OHLC CSV before strategy calculation'),
                result_manifest=manifest, worker_id=worker_id)
            try:
                def raw_export_progress(done, total, rows):
                    update_checkpoint(store, job_id, symbols_progress=progress, current_symbol='', current_chunk=0,
                        progress_percent=90 + 9 * done / max(total, 1),
                        current_stage=f"Preparing {job.get('range_label') or '10-year'} raw CSV · {done}/{total} periods · {rows:,} rows",
                        result_manifest=manifest, worker_id=worker_id)
                # gap_ok: a provider history shorter than requested (or with
                # documented no-data ranges) no longer fails the job. The CSV
                # is published with provider_coverage_short metadata instead.
                # finalize reads provider gaps from job["symbols_progress"];
                # the live progress dict is newer than the job claim snapshot.
                job_view = {**job, "symbols_progress": progress}
                full_raw_artifact = finalize(job_view, store, manifest, raw=True, gap_ok=raw_only,
                         on_progress=raw_export_progress if raw_only else None,
                         should_stop=lambda: _stop_requested(store, job_id))
            except ArtifactCorruptionError as error:
                item = progress[error.symbol]
                item['invalid_chunks'] = sorted(set(item.get('invalid_chunks') or []) | {error.path})
                item['status'] = 'FAILED'
                raise
        if raw_only:
            failed = [sym for sym in symbols if progress.get(sym, {}).get('status') != 'COMPLETE']
            loaded = len(symbols) - len(failed)
            if not download_complete:
                # Stalled at e.g. 70%: publish a partial CSV from the durable
                # chunks so the user can download the data loaded so far.
                def partial_export_progress(done, total, rows):
                    update_checkpoint(store, job_id, symbols_progress=progress, current_symbol='', current_chunk=0,
                        progress_percent=90 + 9 * done / max(total, 1),
                        current_stage=f'Preparing partial raw CSV · {done}/{total} periods · {rows:,} rows',
                        result_manifest=manifest, worker_id=worker_id)
                _publish_raw_partial_csv(store, job, progress, manifest,
                                         on_progress=partial_export_progress,
                                         should_stop=lambda: _stop_requested(store, job_id))
            if not failed:
                stage = '10-year raw OHLC ready · all 20 symbols · CSV ready'
                if isinstance(full_raw_artifact, dict) and full_raw_artifact.get('provider_coverage_short'):
                    stage += ' · provider gaps documented (see download note)'
            elif _manifest_has_partial_raw_csv(manifest):
                stage = 'Raw OHLC loading incomplete · partial CSV of downloaded data ready · Resume retries missing ranges'
            else:
                stage = 'Raw OHLC loading incomplete · Resume retries missing ranges'
            finish_job(store, job_id, status='COMPLETED' if not failed else 'PARTIAL' if loaded else 'FAILED',
                current_stage=stage,
                progress_percent=100 if not failed else 90 * loaded / max(len(symbols), 1),
                symbols_progress=progress, result_manifest=manifest,
                error='; '.join(f"{sym}: {progress[sym].get('error') or 'incomplete'}" for sym in failed) or None)
            return
        update_checkpoint(
            store, job_id, symbols_progress=progress,
            current_symbol=symbols[-1] if symbols else '', current_chunk=0,
            progress_percent=50.0 if download_complete else 49.0,
            current_stage=('Loading complete · raw OHLC CSV ready · starting calculations' if download_complete
                           else 'Loading incomplete · failed ranges remain retryable'),
            result_manifest=manifest, worker_id=worker_id,
        )
        # --------------------------- Stage B ---------------------------
        update_checkpoint(
            store, job_id, symbols_progress=progress,
            current_symbol=symbols[0] if symbols else "", current_chunk=0,
            progress_percent=50.0, current_stage="Stage B · Strategy Build (S1–S240)",
            result_manifest=manifest, worker_id=worker_id,
        )
        for symbol, candles, prepared_path, calculation_error in _strategy_inputs(job, store, progress, manifest):
            if _stop_requested(store, job_id):
                finish_job(store, job_id, status="PAUSED", current_stage="Paused safely after Finder symbol checkpoint", progress_percent=float(job.get("progress_percent") or 50), symbols_progress=progress, result_manifest=manifest)
                return
            item = progress.get(symbol) or {}
            if item.get("status") != "COMPLETE" and item.get("finder_status") != "COMPLETE":
                item["finder_status"] = "BLOCKED"
                item["error"] = item.get("error") or "HISTORICAL_DATA_INCOMPLETE"
                progress[symbol] = item
                continue
            try:
                if calculation_error is not None:
                    raise calculation_error
                success = _build_finder_for_symbol(job, store, symbol, candles, progress, manifest, prepared_path=prepared_path)
                if success:
                    completed_finder += 1
            except Exception as exc:
                progress[symbol]["finder_status"] = "FAILED"
                progress[symbol]["error"] = f"{type(exc).__name__}: {exc}"
                _persist_symbol_state(store, job_id, symbol, progress[symbol])
            finally:
                del candles
                gc.collect()
            completed_count = sum(1 for sym in symbols if (progress.get(sym) or {}).get("finder_status") == "COMPLETE")
            pct = 50.0 + 45.0 * (completed_count / max(1, len(symbols)))
            update_checkpoint(
                store, job_id, symbols_progress=progress, current_symbol=symbol,
                current_chunk=int((progress.get(symbol) or {}).get("completed_chunks") or 0),
                progress_percent=pct,
                current_stage=f"Stage B · Strategy Build · {symbol} · {completed_count}/{len(symbols)} symbols complete",
                result_manifest=manifest, last_error=(progress.get(symbol) or {}).get("error"), worker_id=worker_id,
            )
            heartbeat(store, {**job, "worker_id": worker_id}, stage=f"Strategy Build · {symbol}")
        failed = [sym for sym in symbols if (progress.get(sym) or {}).get("finder_status") != "COMPLETE"]
        if _stop_requested(store, job_id):
            finish_job(store, job_id, status="PAUSED", current_stage="Paused after saved checkpoint", progress_percent=50, symbols_progress=progress, result_manifest=manifest)
            return
        if completed_finder and not failed and bool(job.get("fast_build_mode")):
            update_checkpoint(
                store, job_id, symbols_progress=progress,
                current_symbol=symbols[-1] if symbols else "", current_chunk=0,
                progress_percent=99.0,
                current_stage="Stage C · preparing two-year continuous all-symbol H1 CSV",
                result_manifest=manifest, worker_id=worker_id,
            )
            _build_middle_ranking_csv(job, store, manifest)
        final_status = "COMPLETED" if not failed else "PARTIAL" if completed_finder else "FAILED"
        finish_job(
            store, job_id, status=final_status,
            current_stage=(
                "Fast Strategy Build complete · continuous all-symbol H1 CSV ready"
                if final_status == "COMPLETED" and bool(job.get("fast_build_mode"))
                else "Build Strategy complete"
                if final_status == "COMPLETED"
                else "Build Strategy finished with partial symbol results"
            ),
            progress_percent=100.0 if final_status == "COMPLETED" else 99.0,
            symbols_progress=progress, result_manifest=manifest,
            error=("; ".join(f"{s}: {(progress.get(s) or {}).get('error', 'failed')}" for s in failed)) if failed else None,
        )
    except InterruptedError:
        finish_job(store, job_id, status="PAUSED", current_stage="Paused safely during finalization",
                   progress_percent=95, symbols_progress=progress, result_manifest=manifest)
    except Exception as exc:
        finish_job(
            store, job_id, status="FAILED", current_stage="Build Strategy failed safely — previous checkpoints preserved",
            progress_percent=min(99.0, float(job.get("progress_percent") or 0)), symbols_progress=progress, result_manifest=manifest,
            error=f"{type(exc).__name__}: {exc}",
        )
        gc.collect()

def _recover_stale_jobs(store: BuildStore) -> None:
    stale_minutes = max(2, int(float(_env("BUILD_STALE_MINUTES", "10") or "10")))
    try:
        recovered = store.recover_stale_jobs(stale_minutes)
        if recovered:
            print(f"Recovered {recovered} stale Build Strategy job(s).")
        return
    except Exception as exc:
        # Local fallback and development environments may not have the SQL RPC yet.
        if getattr(getattr(store, "backend", None), "mode", "") != "LOCAL":
            print(f"Stale-job recovery RPC unavailable: {exc}")
        return

def _claim(store: BuildStore, worker_id: str) -> dict[str, Any] | None:
    try:
        job = store.claim_next_job(worker_id)
        if isinstance(job, Mapping):
            return dict(job)
    except Exception:
        pass
    # Local-development fallback: scan local jobs by modification time.
    backend = getattr(store, "backend", None)
    if backend is not None and getattr(backend, "mode", "") == "LOCAL":
        try:
            rows = []
            for path in sorted((_RUNTIME_ROOT / "jobs").glob("*.json"), key=lambda p: p.stat().st_mtime_ns):
                job = store.get_job(path.stem)
                if isinstance(job, Mapping) and str(job.get("status") or "").upper() == "QUEUED":
                    rows.append(dict(job))
            if rows:
                selected = rows[0]
                updated = store.update_job(str(selected["id"]), {
                    "status": "RUNNING", "worker_id": worker_id,
                    "started_at": selected.get("started_at") or _iso(_utc_now()),
                    "heartbeat_at": _iso(_utc_now()),
                    "current_stage": "External worker claimed queued job",
                })
                return updated
        except Exception:
            return None
    return None


def main() -> int:
    store = BuildStore()
    if not store.info().configured:
        print("Build worker storage is not configured.")
        return 2
    worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    poll_seconds = max(1, min(30, int(float(_env("BUILD_WORKER_POLL_SECONDS", "3") or "3"))))
    once = _env("BUILD_WORKER_ONCE", "false").lower() in {"1", "true", "yes", "on"}
    print(f"{WORKER_VERSION} started as {worker_id}; storage={store.info().mode}")
    client: TwelveDataWorkerClient | None = None
    while True:
        _recover_stale_jobs(store)
        job = _claim(store, worker_id)
        if job:
            try:
                if client is None:
                    client = TwelveDataWorkerClient()
                execute_job(store, client, job)
            except Exception as exc:
                # Keep worker-launch/configuration errors attached to the job
                # instead of leaving a permanently queued checkpoint.
                try:
                    latest = store.get_job(str(job.get("id") or "")) or job
                    progress, manifest = _job_progress(latest)
                    finish_job(
                        store, str(job.get("id") or ""), status="FAILED",
                        current_stage="Build worker initialization failed safely",
                        progress_percent=float(latest.get("progress_percent") or 0),
                        symbols_progress=progress, result_manifest=manifest,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                except Exception:
                    pass
                gc.collect()
        elif once:
            return 0
        else:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
