"""Durable Build Strategy control plane and persistent artifact access.

This module intentionally contains no S1-S240 formulas.  It turns the strategy
build into a resumable job: Streamlit only creates/controls/polls a job while a
separate worker performs Twelve Data downloads and symbol-by-symbol Finder
calculation.

Backends
--------
* Supabase Postgres + Storage are the production backend for Streamlit Cloud.
* A local JSON/object-store backend is retained for local worker development.

The Streamlit app never executes the heavy build path in this module.
"""
from __future__ import annotations
from core.monthly_strategy_columns import STRATEGY_COLUMNS
from core.strategy_audit_20260924 import STRATEGY_ENGINE_VERSION
from core.monthly_runtime import MONTHLY_METADATA
import numpy as np

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
import hashlib
import json
import math
import os
import shutil
import tempfile
import re
import subprocess
import sys
import uuid

import pandas as pd
import requests

VERSION = "resumable-build-20261007-v8-partial-csv-provider-gaps"
KIND = "STRATEGY_FINDER"
RAW_OHLC_KIND = "RAW_OHLC_10Y"
# Jobs queued before the 10-year upgrade keep working: resume, progress and
# downloads still recognize them as raw-only loads.
RAW_OHLC_KIND_LEGACY = "RAW_OHLC_4Y"
# 2026-10-07: the single 10-year raw load is split into two independent ranges
# so each can be downloaded separately. New kinds keep legacy jobs working.
RAW_OHLC_KIND_2020_LATEST = "RAW_OHLC_2020_LATEST"
RAW_OHLC_KIND_2015_2020 = "RAW_OHLC_2015_2020"
RAW_OHLC_RANGES_20261007 = {
    # "end": None means "latest available" (same end rule as the 10-year job).
    "2020_LATEST": {
        "kind": RAW_OHLC_KIND_2020_LATEST,
        "label": "2020-01-01 \u2192 Latest",
        "start": "2020-01-01",
        "end": None,
        "chunk_days": 180,
    },
    "2015_2020": {
        "kind": RAW_OHLC_KIND_2015_2020,
        "label": "2015-01-01 \u2192 2020-01-01",
        "start": "2015-01-01",
        "end": "2020-01-01",
        "chunk_days": 180,
    },
}


def is_raw_ohlc_kind(kind) -> bool:
    """True for raw-OHLC download jobs, including legacy 4-year jobs."""
    return kind in (RAW_OHLC_KIND, RAW_OHLC_KIND_LEGACY,
                    RAW_OHLC_KIND_2020_LATEST, RAW_OHLC_KIND_2015_2020)
DEFAULT_CHUNK_DAYS = 30
DEFAULT_HISTORY_YEARS = 2
DEFAULT_STALE_MINUTES = 10
FILE_TRANSFER_PART_BYTES = 32 * 1024 * 1024
ACTIVE_STATUSES = {"QUEUED", "RUNNING"}
PAUSED_STATUSES = {"PAUSED", "FAILED"}
TERMINAL_STATUSES = {"COMPLETED", "PARTIAL", "FAILED", "PAUSED", "CANCELLED"}

COMPACT_FINDER_COLUMNS = frozenset(STRATEGY_COLUMNS + MONTHLY_METADATA) | frozenset({
    "Symbol", "Datetime", "Completed Candle", "Timeframe", "Middle Bias Flip At",
    "Middle Regime Bias", "Lower Regime Bias", "Higher Standard Regime Bias",
    "Strategy Hit Count", "Best Strategy Score", "Best Strategy", "Middle Bias SL Reach", "Near Entry Score", "ATR", "Entry Noise Ratio",
    "Strategy Decision", "Hourly 4 Entry", "Hourly Selection Rank", "Hourly Entry Origin",
    "Hourly Selected Count", "Hourly Selection Score", "Risk Quality Score", "Candidate Quality Score",
    "TP:SL Price Ratio", "24H TP Distance", "24H SL Distance", "24H Estimated Net Pip Potential", "24H ROMAD Proxy",
    "Suggested TP", "Suggested SL", "Suggested TP Price", "Suggested SL Price",
    "TP Price Display", "SL Price Display", "Preferred TP Horizon", "Expected TP Hours",
    "TP Median Reach Hours", "TP P75 Reach Hours", "TP First Rate", "SL First Rate",
    "SL Rebound To TP Rate", "SL Rebound Sample Count", "SL False Stop Quality",
    "Required Structural SL", "Allowed Maximum SL", "SL Risk Cap Passed", "SL Reject Reason",
    "SL Structural Quality Score", "SL Liquidity Safety Score", "Suggested SL Quality Score",
    "Nearest TP Barrier Price", "TP Barrier Distance", "TP Barrier Strength", "TP Beyond Barrier",
    "TP Barrier Quality Passed", "TP Quality Score", "SL Quality Score", "TP/SL Pair Quality Score",
    "TP/SL Quality Level", "TP/SL Quality Reason", "TP/SL Sample Count", "TP/SL Engine",
    "Open Price", "Close Price", "Highest Price", "Lowest Price", "Candle After Regime Start", "Starting Price",
    "Avg Regime Candle Count Before Regime Change", "Completed Regime Samples", "Avg Regime Candle Rank", "Regime Maturity Score",
    "Max Hold Hours", "Time Exit Hours", "Exit Scenario", "Entry Quality Passed", "Entry Filter Relaxation Percent",
    "Strategy Engine", "History Source",
    "bar_open_time", "bar_close_time", "signal_available_at", "entry_side", "entry_eligible", "research_entry_eligible",
    "active_strategy_ids", "active_strategy_family_ids", "unique_family_count", "entry_origin", "direction_probability",
    "probability_calibration_version", "expected_net_pips", "expected_net_pips_lower_bound", "tp_price", "sl_price",
    "horizon_hours", "max_hold_hours", "market_executable", "broker_quote_verified", "spread_pips", "slippage_pips",
    "commission_pips", "financing_pips_per_day", "data_quality_flag", "decision_engine_version", "Policy SHA256",
    "provider", "quote_timezone", "timestamp_owner", "TP Filters Passed", "TP Research Filters Passed", "TP Filter Reasons",
    "TP Filter Pass Count", "TP Filter Total Count", "regime_family", "volatility_bucket", "forecast_sample_count",
    "forecast_training_end", "expected_reach_hours", "reach_p25_hours", "reach_p75_hours", "volume_evidence_source",
    "Volume Evidence Is Real", "Strategy Alias Map", "Disabled Strategy IDs",
})

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_ROOT = _PROJECT_ROOT / ".runtime" / "resumable_builds"
_LOCAL_JOBS = _RUNTIME_ROOT / "jobs"
_LOCAL_OBJECTS = _RUNTIME_ROOT / "objects"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any = None) -> str:
    dt = value if isinstance(value, datetime) else _utc_now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_dt(value: Any) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return pd.Timestamp(parsed) if pd.notna(parsed) else pd.NaT


def normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")


def normalize_timeframe(value: Any) -> str:
    text = str(value or "H1").strip().upper()
    return {"1H": "H1", "4H": "H4", "60MIN": "H1", "240MIN": "H4"}.get(text, text or "H1")


def _safe_segment(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return text.strip("._-") or "unknown"


def _secret(name: str, default: str = "") -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    try:
        import streamlit as st  # type: ignore
        raw = st.secrets.get(name)
        if raw is not None:
            return str(raw).strip()
    except Exception:
        pass
    return default


def _config() -> dict[str, Any]:
    url = _secret("SUPABASE_URL")
    key = _secret("SUPABASE_SECRET_KEY") or _secret("SUPABASE_SERVICE_ROLE_KEY")
    bucket = _secret("BUILD_STORAGE_BUCKET", "adx-build-data")
    require_remote = str(_secret("BUILD_REQUIRE_PERSISTENT", "true")).lower() not in {"0", "false", "no", "off"}
    return {
        "supabase_url": url.rstrip("/"),
        "supabase_key": key,
        "bucket": bucket,
        "require_remote": require_remote,
    }


@dataclass(frozen=True)
class BuildBackendInfo:
    mode: str
    persistent: bool
    configured: bool
    detail: str


class _LocalBackend:
    mode = "LOCAL"
    persistent = False

    def __init__(self) -> None:
        _LOCAL_JOBS.mkdir(parents=True, exist_ok=True)
        _LOCAL_OBJECTS.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _job_path(job_id: str) -> Path:
        return _LOCAL_JOBS / f"{_safe_segment(job_id)}.json"

    @staticmethod
    def _obj_path(path: str) -> Path:
        safe = "/".join(_safe_segment(x) for x in str(path).split("/") if x)
        return _LOCAL_OBJECTS / safe

    def create_job(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.update_job(str(payload["id"]), dict(payload))
        return dict(payload)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        path = self._job_path(job_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except Exception:
            return None

    def update_job(self, job_id: str, patch: Mapping[str, Any]) -> dict[str, Any] | None:
        current = self.get_job(job_id) or {}
        current.update(dict(patch))
        current["updated_at"] = _iso()
        path = self._job_path(job_id)
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return current

    def list_jobs(self, *, user_key: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = []
        for path in sorted(_LOCAL_JOBS.glob("*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True):
            value = self.get_job(path.stem)
            if isinstance(value, dict) and str(value.get("user_key") or "") == user_key:
                rows.append(value)
            if len(rows) >= int(limit):
                break
        return rows

    def put_object(self, path: str, payload: bytes, *, content_type: str = "application/octet-stream", upsert: bool = True) -> None:
        target = self._obj_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + f".{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, target)

    def get_object(self, path: str) -> bytes:
        return self._obj_path(path).read_bytes()

    def object_exists(self, path: str) -> bool:
        return self._obj_path(path).is_file()

    def recover_stale_jobs(self, stale_minutes: int = DEFAULT_STALE_MINUTES) -> int:
        cutoff = _utc_now().timestamp() - max(2, int(stale_minutes)) * 60
        count = 0
        for path in _LOCAL_JOBS.glob("*.json"):
            job = self.get_job(path.stem) or {}
            if str(job.get("status") or "").upper() != "RUNNING":
                continue
            heartbeat_value = _parse_dt(job.get("heartbeat_at"))
            if pd.isna(heartbeat_value):
                heartbeat_value = _parse_dt(job.get("started_at"))
            if pd.isna(heartbeat_value):
                continue
            if heartbeat_value.timestamp() <= cutoff:
                self.update_job(str(job["id"]), {
                    "status": "QUEUED", "requested_action": None, "worker_id": None,
                    "current_stage": "Recovered stale worker checkpoint; queued for resume",
                    "recovery_count": int(job.get("recovery_count") or 0) + 1,
                })
                count += 1
        return count

    def info(self) -> BuildBackendInfo:
        return BuildBackendInfo(self.mode, self.persistent, True, "Local runtime store (not persistent on Streamlit Cloud)")


class _SupabaseBackend:
    mode = "SUPABASE"
    persistent = True

    def __init__(self, url: str, key: str, bucket: str) -> None:
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
        self.url = url.rstrip("/")
        self.key = key
        self.bucket = bucket
        self.session = requests.Session()
        self.session.headers.update({
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        })

    @property
    def rest_base(self) -> str:
        return f"{self.url}/rest/v1"

    @property
    def storage_base(self) -> str:
        host = self.url
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.url)
            hostname = parsed.hostname or ""
            if hostname.endswith(".supabase.co"):
                hostname = hostname[:-len(".supabase.co")] + ".storage.supabase.co"
            host = f"{parsed.scheme or 'https'}://{hostname}"
        except Exception:
            pass
        return host.rstrip("/") + "/storage/v1"

    def _request(self, method: str, url: str, *, params: Mapping[str, Any] | None = None, json_body: Any = None, timeout: float = 15.0, headers: Mapping[str, str] | None = None, content: bytes | None = None) -> requests.Response:
        merged = dict(headers or {})
        response = self.session.request(method, url, params=params, json=json_body, data=content, headers=merged, timeout=timeout)
        if response.status_code >= 400:
            detail = response.text[:500]
            raise RuntimeError(f"Supabase {method} {response.status_code}: {detail}")
        return response

    def create_job(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = self._request("POST", f"{self.rest_base}/build_jobs", json_body=dict(payload), headers={"Prefer": "return=representation"})
        rows = response.json()
        return dict(rows[0]) if isinstance(rows, list) and rows else dict(payload)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        response = self._request("GET", f"{self.rest_base}/build_jobs", params={"id": f"eq.{job_id}", "select": "*", "limit": 1})
        rows = response.json()
        return dict(rows[0]) if isinstance(rows, list) and rows else None

    def update_job(self, job_id: str, patch: Mapping[str, Any]) -> dict[str, Any] | None:
        payload = dict(patch)
        payload["updated_at"] = _iso()
        response = self._request("PATCH", f"{self.rest_base}/build_jobs", params={"id": f"eq.{job_id}"}, json_body=payload, headers={"Prefer": "return=representation"})
        rows = response.json()
        return dict(rows[0]) if isinstance(rows, list) and rows else self.get_job(job_id)

    def list_jobs(self, *, user_key: str, limit: int = 20) -> list[dict[str, Any]]:
        response = self._request(
            "GET", f"{self.rest_base}/build_jobs",
            params={"user_key": f"eq.{user_key}", "select": "*", "order": "created_at.desc", "limit": str(int(limit))},
        )
        rows = response.json()
        return [dict(row) for row in rows] if isinstance(rows, list) else []

    def claim_next_job(self, worker_id: str) -> dict[str, Any] | None:
        response = self._request(
            "POST", f"{self.rest_base}/rpc/claim_next_build_job",
            json_body={"p_worker_id": worker_id}, headers={"Prefer": "return=representation"}, timeout=20,
        )
        rows = response.json()
        return dict(rows[0]) if isinstance(rows, list) and rows else None

    def recover_stale_jobs(self, stale_minutes: int = DEFAULT_STALE_MINUTES) -> int:
        response = self._request(
            "POST", f"{self.rest_base}/rpc/requeue_stale_build_jobs",
            json_body={"p_stale_minutes": int(stale_minutes)}, timeout=20,
        )
        payload = response.json()
        if isinstance(payload, int):
            return int(payload)
        if isinstance(payload, list) and payload and isinstance(payload[0], int):
            return int(payload[0])
        return 0

    def put_object(self, path: str, payload: bytes, *, content_type: str = "application/octet-stream", upsert: bool = True) -> None:
        object_url = f"{self.storage_base}/object/{self.bucket}/{path.lstrip('/')}"
        headers = {
            "Content-Type": content_type,
            "x-upsert": "true" if upsert else "false",
            "Cache-Control": "3600",
        }
        self._request("POST", object_url, headers=headers, content=payload, timeout=60)

    def get_object(self, path: str) -> bytes:
        object_url = f"{self.storage_base}/object/{self.bucket}/{path.lstrip('/')}"
        response = self._request("GET", object_url, timeout=60)
        return bytes(response.content)

    def object_exists(self, path: str) -> bool:
        object_url = f"{self.storage_base}/object/{self.bucket}/{path.lstrip('/')}"
        response = self.session.head(object_url, timeout=15)
        return response.status_code == 200

    def info(self) -> BuildBackendInfo:
        return BuildBackendInfo(self.mode, self.persistent, True, f"Supabase Postgres + Storage bucket '{self.bucket}'")


class BuildStore:
    """Thin facade used by both Streamlit and the external worker."""

    def __init__(self, backend: Any | None = None) -> None:
        if backend is not None:
            self.backend = backend
            return
        cfg = _config()
        if cfg["supabase_url"] and cfg["supabase_key"]:
            self.backend = _SupabaseBackend(cfg["supabase_url"], cfg["supabase_key"], cfg["bucket"])
        else:
            self.backend = _LocalBackend()

    def info(self) -> BuildBackendInfo:
        return self.backend.info()

    def create_job(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.backend.create_job(payload)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.backend.get_job(job_id)

    def update_job(self, job_id: str, patch: Mapping[str, Any]) -> dict[str, Any] | None:
        return self.backend.update_job(job_id, patch)

    def list_jobs(self, *, user_key: str, limit: int = 20) -> list[dict[str, Any]]:
        return self.backend.list_jobs(user_key=user_key, limit=limit)

    def claim_next_job(self, worker_id: str) -> dict[str, Any] | None:
        claim = getattr(self.backend, "claim_next_job", None)
        if callable(claim):
            return claim(worker_id)
        return None

    def recover_stale_jobs(self, stale_minutes: int = DEFAULT_STALE_MINUTES) -> int:
        recover = getattr(self.backend, "recover_stale_jobs", None)
        if callable(recover):
            return int(recover(stale_minutes))
        return 0

    def put_object(self, path: str, payload: bytes, *, content_type: str = "application/octet-stream", upsert: bool = True) -> None:
        return self.backend.put_object(path, payload, content_type=content_type, upsert=upsert)

    def put_file(self, path: str, filename: str | Path, *, content_type: str = "application/octet-stream") -> None:
        filename = Path(filename)
        if isinstance(self.backend, _LocalBackend):
            target = self.backend._obj_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
            try:
                shutil.copyfile(filename, temporary)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        elif isinstance(self.backend, _SupabaseBackend):
            # A wide two-year CSV can exceed remote per-object upload limits.
            # Transport pieces stay small; users still download one exact CSV.
            if filename.stat().st_size > FILE_TRANSFER_PART_BYTES:
                parts = []
                with filename.open('rb') as source:
                    for index in range(math.ceil(filename.stat().st_size / FILE_TRANSFER_PART_BYTES)):
                        block = source.read(FILE_TRANSFER_PART_BYTES)
                        part_path = f"{path}.parts/{index:05d}"
                        self.backend.put_object(part_path, block, content_type='application/octet-stream')
                        parts.append(part_path)
                descriptor = json.dumps({'split_file': True, 'paths': parts, 'bytes': filename.stat().st_size}).encode()
                self.backend.put_object(path, descriptor, content_type='application/json')
            else:
                url = f"{self.backend.storage_base}/object/{self.backend.bucket}/{path.lstrip('/')}"
                with filename.open("rb") as source:
                    self.backend._request("POST", url, content=source, timeout=300,
                        headers={"Content-Type": content_type, "x-upsert": "true"})
        else:
            self.put_object(path, filename.read_bytes(), content_type=content_type)

    def materialize_object(self, path: str, destination: str | Path) -> Path:
        destination = Path(destination)
        if isinstance(self.backend, _LocalBackend):
            return self.backend._obj_path(path)
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(self.backend, _SupabaseBackend):
                url = f"{self.backend.storage_base}/object/{self.backend.bucket}/{path.lstrip('/')}"
                with self.backend.session.get(url, stream=True, timeout=60) as response:
                    response.raise_for_status()
                    with destination.open("wb") as output:
                        for block in response.iter_content(1024 * 1024):
                            output.write(block)
            else:
                destination.write_bytes(self.get_object(path))
        return destination

    def get_object(self, path: str) -> bytes:
        payload = self.backend.get_object(path)
        if len(payload) < 1_000_000 and payload.startswith(b'{"split_file": true,'):
            descriptor = json.loads(payload)
            buffer = BytesIO()
            for part_path in descriptor['paths']:
                buffer.write(self.backend.get_object(part_path))
            if buffer.tell() != descriptor['bytes']:
                raise RuntimeError('Stored download file has missing or truncated parts')
            return buffer.getvalue()
        return payload

    def object_exists(self, path: str) -> bool:
        return self.backend.object_exists(path)


def backend_info() -> BuildBackendInfo:
    return BuildStore().info()


def current_user_key(state: Mapping[str, Any] | None = None) -> str:
    state = state or {}
    identity = str(state.get("new7_auth_email") or state.get("authenticated_user") or state.get("username") or "").strip().lower()
    if identity and identity not in {"guest", "anonymous", "default"}:
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    # A shared fallback is intentional only when the application has no auth identity.
    return _secret("BUILD_DEFAULT_USER_KEY", "default-user")


def _target_bounds(history_years: int = DEFAULT_HISTORY_YEARS, *, end: datetime | None = None) -> tuple[datetime, datetime]:
    end_dt = (end or _utc_now()).astimezone(timezone.utc)
    # Avoid requesting an in-progress H1 bar.  The worker will validate this again.
    end_dt = end_dt.replace(minute=0, second=0, microsecond=0) - pd.Timedelta(hours=1).to_pytimedelta()
    start_dt = (pd.Timestamp(end_dt) - pd.DateOffset(years=max(1, int(history_years)))).to_pydatetime()
    return start_dt, end_dt


def _effective_chunk_days(chunk_days: int, timeframe: str | None = None) -> int:
    requested = max(1, min(365, int(chunk_days)))
    tf = normalize_timeframe(timeframe) if timeframe else "H1"
    # Twelve Data limits a time-series response to 5,000 data points. Keep a
    # safety margin and clamp shorter intervals accordingly. The user-facing
    # default remains 30 days for H1.
    minutes = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}.get(tf, 60)
    max_days_by_points = max(1, int((4500 * minutes) // 1440))
    return max(1, min(requested, max_days_by_points))


def chunk_windows(
    start_dt: datetime,
    end_dt: datetime,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
    timeframe: str | None = None,
) -> list[tuple[datetime, datetime]]:
    start = start_dt.astimezone(timezone.utc)
    end = end_dt.astimezone(timezone.utc)
    size_days = _effective_chunk_days(chunk_days, timeframe)
    size = pd.Timedelta(days=size_days).to_pytimedelta()
    # Fixed epoch-anchored boundaries make chunk object keys reusable across
    # successive jobs, even when the requested end date moves forward.
    epoch = datetime(2000, 1, 1, tzinfo=timezone.utc)
    elapsed_days = max(0, (start - epoch).total_seconds() / 86400.0)
    bucket_index = int(elapsed_days // size_days)
    cursor = epoch + bucket_index * size
    while cursor > start:
        cursor -= size
    windows: list[tuple[datetime, datetime]] = []
    while cursor < end:
        nxt = min(cursor + size, end)
        # Store full canonical bucket bounds (including edge bars outside the
        # requested range) so later jobs with a shifted start/end can reuse the
        # same durable object instead of re-downloading the entire overlap.
        if cursor < end and nxt > start:
            windows.append((cursor, nxt))
        cursor = nxt if nxt > cursor else cursor + size
    return windows


def _chunk_key(symbol: str, timeframe: str, start_dt: datetime, end_dt: datetime) -> str:
    return (
        f"historical/{normalize_symbol(symbol)}/{normalize_timeframe(timeframe)}/chunks/"
        f"{start_dt.astimezone(timezone.utc):%Y%m%dT%H%M%S}_{end_dt.astimezone(timezone.utc):%Y%m%dT%H%M%S}.parquet"
    )


def chunk_key_date_range(key: str) -> str:
    """Render a chunk storage key as a short human date range for the UI.

    Chunk keys embed epoch-anchored UTC bounds, e.g.
    ``.../chunks/20240101T000000_20240629T000000.parquet`` → ``2024-01-01 → 2024-06-29``.
    Unknown formats fall back to the raw key.
    """
    match = re.search(r"(\d{8}T\d{6})_(\d{8}T\d{6})", str(key or ""))
    if not match:
        return str(key or "")
    try:
        lo = pd.Timestamp(match.group(1), tz="UTC").strftime("%Y-%m-%d")
        hi = pd.Timestamp(match.group(2), tz="UTC").strftime("%Y-%m-%d")
    except Exception:
        return str(key or "")
    return f"{lo} → {hi}"


def _finder_key(symbol: str, timeframe: str, engine_version: str, job_id: str) -> str:
    # Retained as the canonical prefix/key used by older callers. New worker
    # artifacts are split into 5,000-row parts beneath this job directory.
    return f"finder/{normalize_symbol(symbol)}/{normalize_timeframe(timeframe)}/{_safe_segment(engine_version)}/{_safe_segment(job_id)}/part-00000.parquet"


def _finder_part_key(symbol: str, timeframe: str, engine_version: str, job_id: str, part_index: int) -> str:
    return f"finder/{normalize_symbol(symbol)}/{normalize_timeframe(timeframe)}/{_safe_segment(engine_version)}/{_safe_segment(job_id)}/part-{int(part_index):05d}.parquet"


def _json_object_key(job_id: str, symbol: str) -> str:
    return f"build-state/{_safe_segment(job_id)}/{normalize_symbol(symbol)}.json"


def _middle_ranking_csv_key(job_id: str, timeframe: str) -> str:
    return f"middle-ranking/{_safe_segment(job_id)}/middle_standard_regime_ranking_2y_{normalize_timeframe(timeframe)}.csv"


def make_job(
    state: Mapping[str, Any], *, symbols: Sequence[str], timeframe: str, history_years: int = DEFAULT_HISTORY_YEARS,
    chunk_days: int = DEFAULT_CHUNK_DAYS, job_id: str | None = None, fast_build: bool = False,
    raw_only: bool = False, raw_range: str | None = None,
) -> dict[str, Any]:
    range_spec = RAW_OHLC_RANGES_20261007.get(str(raw_range)) if raw_range else None
    if raw_range is not None:
        # Any explicit range request is a raw-only download; an unknown range
        # key falls back to the legacy 10-year raw job, never a strategy job.
        raw_only = True
    if raw_only:
        from core.fixed_fx_universe_20260918 import TARGET_FX_SYMBOLS
        symbols = TARGET_FX_SYMBOLS
        fast_build = False
        # Up to 4,321 hourly points per request, below the provider's 5,000
        # point limit. Larger raw-only chunks reduce ten-year API calls.
        chunk_days = 180
        if range_spec is not None:
            # Split-range raw download: explicit calendar bounds instead of a
            # trailing "N years" window. history_years records the span for
            # display only; start/end drive the worker.
            start_dt = pd.Timestamp(range_spec["start"], tz="UTC").to_pydatetime()
            if range_spec["end"]:
                end_dt = pd.Timestamp(range_spec["end"], tz="UTC").to_pydatetime()
            else:
                _, end_dt = _target_bounds(1)
            history_years = max(1, int(round((end_dt - start_dt).total_seconds() / 86400 / 365.25)))
            job_kind = range_spec["kind"]
            range_label = range_spec["label"]
        else:
            history_years = 10
            start_dt, end_dt = _target_bounds(history_years)
            job_kind = RAW_OHLC_KIND
            range_label = None
    clean_symbols: list[str] = []
    for raw in symbols:
        symbol = normalize_symbol(raw)
        if symbol and symbol not in clean_symbols:
            clean_symbols.append(symbol)
    if not clean_symbols:
        raise ValueError("No symbols are available for Build Strategy")
    tf = "H1"  # Frozen monthly strategy builds always consume H1; unrelated app loaders retain their own timeframe.
    calculation_rows = 5000
    quotas = {}
    if fast_build:
        history_years = 1
        # Date coverage, never a candle quota, defines completion.
        chunk_days = 30
    if range_spec is None:
        start_dt, end_dt = _target_bounds(history_years)
    all_counts = {symbol: len(chunk_windows(start_dt, end_dt, chunk_days, tf)) for symbol in clean_symbols}
    created = _utc_now()
    jid = job_id or f"BS-{created:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:10]}"
    return {
        "id": jid,
        "job_id": jid,
        "kind": job_kind if raw_only else KIND,
        "version": VERSION,
        "user_key": current_user_key(state),
        "status": "QUEUED",
        "requested_action": None,
        "symbols": clean_symbols,
        "timeframe": tf,
        "history_years": int(history_years),
        "raw_range": str(raw_range) if range_spec is not None else None,
        "range_label": range_label if raw_only else None,
        "strict_only": bool(state.get("monthly_strict_only",False)),
        "chunk_days": int(chunk_days),
        "calculation_batch_rows": calculation_rows,
        "fast_build_mode": bool(fast_build),
        "target_candle_rows": None,
        "symbol_candle_targets": quotas,
        "start_date": _iso(start_dt),
        "end_date": _iso(end_dt),
        "current_symbol": clean_symbols[0],
        "current_chunk": 0,
        "total_chunks": int(sum(all_counts.values())),
        "progress_percent": 0.0,
        "current_stage": "Queued — waiting for external build worker",
        "worker_id": None,
        "heartbeat_at": None,
        "created_at": _iso(created),
        "started_at": None,
        "completed_at": None,
        "updated_at": _iso(created),
        "last_error": None,
        "recovery_count": 0,
        "symbols_progress": {
            symbol: {
                "status": "WAITING", "completed_chunks": 0, "total_chunks": all_counts[symbol],
                "current_chunk": 0, "oldest_downloaded": None, "newest_downloaded": None,
                "finder_status": "SKIPPED" if raw_only else "WAITING", "finder_rows": 0, "finder_path": None, "error": None,
            }
            for symbol in clean_symbols
        },
        "result_manifest": [],
    }


def _is_job_active(job: Mapping[str, Any] | None) -> bool:
    return isinstance(job, Mapping) and str(job.get("status") or "").upper() in ACTIVE_STATUSES


def latest_job(store: BuildStore, state: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = store.list_jobs(user_key=current_user_key(state), limit=20)
    return rows[0] if rows else None


def latest_job_for_kind(store: BuildStore, state: Mapping[str, Any], kind: str) -> dict[str, Any] | None:
    """Newest job of one kind (used to render each split raw range separately)."""
    for row in store.list_jobs(user_key=current_user_key(state), limit=100):
        if isinstance(row, Mapping) and row.get("kind") == kind:
            return dict(row)
    return None


def queue_job(
    store: BuildStore, state: Mapping[str, Any], *, symbols: Sequence[str], timeframe: str,
    history_years: int = DEFAULT_HISTORY_YEARS, chunk_days: int = DEFAULT_CHUNK_DAYS, fast_build: bool = False,
    raw_only: bool = False, raw_range: str | None = None,
) -> dict[str, Any]:
    info = store.info()
    if raw_range:
        raw_only = True
    job = make_job(state, symbols=symbols, timeframe=timeframe, history_years=history_years, chunk_days=chunk_days, fast_build=fast_build, raw_only=raw_only, raw_range=raw_range)
    from core.strategy_audit_20260924 import STRATEGY_ENGINE_VERSION
    for existing in store.list_jobs(user_key=current_user_key(state), limit=100):
        equivalent = (set(existing.get("symbols") or []) == set(job["symbols"])
                      and existing.get("timeframe") == job["timeframe"]
                      and existing.get("history_years") == job["history_years"]
                      and bool(existing.get("strict_only",False)) == job["strict_only"]
                      and bool(existing.get("fast_build_mode")) == bool(job["fast_build_mode"])
                      and existing.get("kind", KIND) == job["kind"]
                      and existing.get("version") == VERSION)
        if not equivalent:
            continue
        if _is_job_active(existing):
            return {**existing, "duplicate": True}
        artifact = (next((a for a in existing.get("result_manifest") or [] if a.get("kind") == "raw_ohlc_csv"), None)
                    if raw_only else _middle_ranking_csv_artifact(existing))
        if (existing.get("status") == "COMPLETED" and existing.get("end_date") == job["end_date"] and existing.get("start_date") == job["start_date"]
                and artifact and artifact.get("strategy_engine") == STRATEGY_ENGINE_VERSION
                and store.object_exists(artifact["path"])):
            return {**existing, "duplicate": True, "reused": True}
        if (fast_build or raw_only) and existing.get("status") == "COMPLETED":
            # Reuse exact symbol computations when raw input has not changed.
            # Changed histories require a chronological replay: EMA, expanding
            # regime statistics and cumulative event state have no finite warmup.
            for symbol in job["symbols"]:
                prior = (existing.get("symbols_progress") or {}).get(symbol) or {}
                job["symbols_progress"][symbol]["previous_candles"] = [
                    a for a in existing.get("result_manifest") or []
                    if a.get("kind") == "candle_chunk" and a.get("symbol") == symbol]
                job["symbols_progress"][symbol]["previous_finder"] = {
                    "input_hash": prior.get("input_hash"),
                    "artifacts": [a for a in existing.get("result_manifest") or []
                                  if a.get("kind") == "finder_symbol" and a.get("symbol") == symbol
                                  and a.get("strategy_engine") == STRATEGY_ENGINE_VERSION
                                  and bool(a.get("strict_only",False)) == bool(job.get("strict_only",False))],
                }
            break
    job["storage_mode"] = info.mode
    job["persistent_storage"] = bool(info.persistent)
    if info.mode == "LOCAL":
        job["storage_notice"] = (
            "LOCAL FALLBACK: Supabase persistence is unavailable. Build runs in a separate worker process; "
            "local runtime storage is not durable across a Streamlit container replacement."
        )
    try:
        created = store.create_job(job)
    except Exception as exc:
        # Remote credentials can exist while the Supabase table/RPC/storage is
        # unavailable. Fall back to the local job store instead of breaking the
        # Streamlit process. The caller records the override for future reruns.
        if info.mode != "LOCAL":
            local_store = BuildStore(backend=_LocalBackend())
            job["storage_mode"] = "LOCAL_FALLBACK"
            job["persistent_storage"] = False
            job["storage_notice"] = (
                f"LOCAL FALLBACK after Supabase error: {type(exc).__name__}: {str(exc)[:220]}"
            )
            created = local_store.create_job(job)
            try:
                state["field3_build_store_override_20260928"] = "LOCAL"
                state["field3_build_store_fallback_reason_20260928"] = job["storage_notice"]
            except Exception:
                pass
        else:
            raise
    return created

def build_store_for_ui(state: Mapping[str, Any] | None = None) -> BuildStore:
    """Return the selected Build Strategy backend for the current UI session."""
    override = str((state or {}).get("field3_build_store_override_20260928") or "").upper()
    if override == "LOCAL":
        return BuildStore(backend=_LocalBackend())
    return BuildStore()

def _local_twelve_keys(state: Mapping[str, Any] | None = None) -> list[str]:
    """Resolve configured Twelve Data keys without exposing them to the UI."""
    values: list[str] = []
    try:
        from core.twelve_data_key_pool import TwelveDataKeyPool
        for item in TwelveDataKeyPool.from_state(state or {}).keys():
            key = str(item.get("api_key") or "").strip()
            if key and key not in values:
                values.append(key)
    except Exception:
        pass
    # Legacy/simple state names are useful in tests and local deployments.
    # Detect every configured key slot (1..8); the pool above already covered
    # whichever keys the TwelveDataKeyPool resolves.
    state_map = state or {}
    legacy_names: list[str] = []
    for index in range(1, 9):
        legacy_names.extend((f"twelve_api_key_{index}", f"TWELVE_DATA_API_KEY_{index}"))
    legacy_names.extend(("twelve_api_key", "TWELVE_DATA_API_KEY"))
    for name in legacy_names:
        try:
            key = str(state_map.get(name) or "").strip()
        except Exception:
            key = ""
        if key and key not in values:
            values.append(key)
    return values

def launch_local_build_worker(state: Mapping[str, Any], job_id: str, *, storage_mode: str = "LOCAL") -> dict[str, Any]:
    """Launch a detached one-shot worker for the non-persistent fallback."""
    root = _PROJECT_ROOT
    worker_script = root / "worker" / "run_build_worker.py"
    if not worker_script.is_file():
        raise FileNotFoundError(f"Build worker script not found: {worker_script}")
    keys = _local_twelve_keys(state)
    if not keys:
        raise RuntimeError("No Twelve Data API key is configured for the local Build Strategy worker")
    log_dir = _RUNTIME_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{_safe_segment(job_id)}.log"
    env = os.environ.copy()
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
        env[name] = "1"
    env["TWELVE_DATA_PER_KEY_MINUTE_LIMIT"] = str(max(1, int(state.get("twelve_data_per_key_minute_limit") or 8)))
    env["BUILD_WORKER_ONCE"] = "true"
    env["BUILD_WORKER_POLL_SECONDS"] = "1"
    # Forward the full multi-API key pool to the worker: the worker rotates
    # chunks across every configured key, so cap only at the pool's max.
    for index, key in enumerate(keys[:8], start=1):
        env[f"TWELVE_DATA_API_KEY_{index}"] = key
        env[f"TWELVE_API_KEY_{index}"] = key
    # Force the child into the same local backend as the queued job. This is
    # essential when Streamlit deployment environment variables also contain a
    # broken/temporarily unavailable Supabase configuration.
    if str(storage_mode).upper() == "SUPABASE":
        cfg = _config()
        env["SUPABASE_URL"] = cfg["supabase_url"]
        env["SUPABASE_SECRET_KEY"] = cfg["supabase_key"]
        env["BUILD_STORAGE_BUCKET"] = cfg["bucket"]
    else:
        env.pop("BUILD_REQUIRE_PERSISTENT", None)
        env.pop("SUPABASE_URL", None)
        env.pop("SUPABASE_SECRET_KEY", None)
        env.pop("SUPABASE_SERVICE_ROLE_KEY", None)
    with log_path.open("ab") as log_file:
        process = subprocess.Popen(
            [sys.executable, str(worker_script)],
            cwd=str(root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    return {"ok": True, "pid": int(process.pid), "log_path": str(log_path)}


def request_stop(store: BuildStore, job_id: str) -> dict[str, Any] | None:
    return store.update_job(job_id, {
        "requested_action": "STOP",
        "current_stage": "Stop requested — worker will checkpoint and pause",
    })


def request_resume(store: BuildStore, job_id: str) -> dict[str, Any] | None:
    return store.update_job(job_id, {
        "status": "QUEUED",
        "requested_action": None,
        "current_stage": "Resume queued — worker will continue from the last checkpoint",
        "last_error": None,
    })


def heartbeat(store: BuildStore, job: Mapping[str, Any], *, stage: str | None = None) -> None:
    patch: dict[str, Any] = {"heartbeat_at": _iso(), "worker_id": job.get("worker_id")}
    if stage:
        patch["current_stage"] = stage
    store.update_job(str(job["id"]), patch)


def _serialize_progress(job: Mapping[str, Any]) -> str:
    return json.dumps(job.get("symbols_progress") or {}, ensure_ascii=False, default=str, separators=(",", ":"))


def update_checkpoint(store: BuildStore, job_id: str, *, symbols_progress: Mapping[str, Any], current_symbol: str, current_chunk: int, progress_percent: float, current_stage: str, result_manifest: Sequence[Mapping[str, Any]] | None = None, last_error: str | None = None, worker_id: str | None = None) -> dict[str, Any] | None:
    patch: dict[str, Any] = {
        "symbols_progress": dict(symbols_progress),
        "current_symbol": normalize_symbol(current_symbol),
        "current_chunk": int(current_chunk),
        "progress_percent": float(max(0.0, min(100.0, progress_percent))),
        "current_stage": str(current_stage),
        "heartbeat_at": _iso(),
        "worker_id": worker_id,
    }
    if result_manifest is not None:
        patch["result_manifest"] = list(result_manifest)
    if last_error is not None:
        patch["last_error"] = str(last_error)[:1500]
    return store.update_job(job_id, patch)


def finish_job(store: BuildStore, job_id: str, *, status: str, current_stage: str, progress_percent: float, symbols_progress: Mapping[str, Any], result_manifest: Sequence[Mapping[str, Any]], error: str | None = None) -> dict[str, Any] | None:
    status_u = str(status or "COMPLETED").upper()
    return store.update_job(job_id, {
        "status": status_u,
        "progress_percent": float(max(0.0, min(100.0, progress_percent))),
        "current_stage": current_stage,
        "symbols_progress": dict(symbols_progress),
        "result_manifest": list(result_manifest),
        "completed_at": _iso() if status_u in TERMINAL_STATUSES else None,
        "heartbeat_at": _iso(),
        "worker_id": None,
        "last_error": error[:1500] if error else None,
    })


def active_poll_seconds() -> int:
    try:
        return max(2, min(15, int(_secret("BUILD_UI_POLL_SECONDS", "3"))))
    except Exception:
        return 3


def _finder_artifacts(job: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = job.get("result_manifest") if isinstance(job.get("result_manifest"), list) else []
    result: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, Mapping) and item.get("kind") == "finder_symbol" and item.get("path") and item.get("strategy_engine") == STRATEGY_ENGINE_VERSION:
            result.append(dict(item))
    return result


def _middle_ranking_csv_artifact(job: Mapping[str, Any]) -> dict[str, Any] | None:
    raw = job.get("result_manifest") if isinstance(job.get("result_manifest"), list) else []
    for item in reversed(raw):
        if isinstance(item, Mapping) and item.get("kind") == "middle_ranking_csv" and item.get("path"):
            return dict(item)
    return None


def load_middle_ranking_csv(store: BuildStore, job: Mapping[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """Load the worker-prepared continuous all-symbol H1 CSV."""
    artifact = _middle_ranking_csv_artifact(job)
    if artifact is None or artifact.get("strategy_engine") != STRATEGY_ENGINE_VERSION:
        raise RuntimeError("Rebuild S1–S240: the continuous all-symbol H1 CSV is not ready; run Fast Strategy Build")
    path = str(artifact.get("path") or "")
    if not path or not store.object_exists(path):
        raise RuntimeError("The prepared continuous all-symbol H1 CSV artifact is missing")
    return store.get_object(path), artifact


def _candle_artifacts(job: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return every durable raw-candle object attached to a build.

    New workers publish ``candle_chunk`` entries in ``result_manifest``.  The
    fallback reconstructs the same inventory from per-symbol checkpoints so a
    job completed by an older worker immediately gains continuous-candle
    access without forcing the user to download the history again.
    """
    raw = job.get("result_manifest") if isinstance(job.get("result_manifest"), list) else []
    result = [
        dict(item)
        for item in raw
        if isinstance(item, Mapping)
        and item.get("kind") == "candle_chunk"
        and item.get("path")
    ]
    if result:
        return result

    timeframe = normalize_timeframe(job.get("timeframe"))
    progress = job.get("symbols_progress") if isinstance(job.get("symbols_progress"), Mapping) else {}
    for raw_symbol in job.get("symbols") or []:
        symbol = normalize_symbol(raw_symbol)
        item = progress.get(symbol) if isinstance(progress, Mapping) else None
        if not isinstance(item, Mapping):
            continue
        chunk_rows = item.get("chunk_rows") if isinstance(item.get("chunk_rows"), Mapping) else {}
        for path in item.get("completed_chunk_keys") or []:
            path_text = str(path or "")
            if not path_text.endswith(".parquet"):
                continue
            match = re.search(r"/(\d{8}T\d{6})_(\d{8}T\d{6})\.parquet$", path_text)
            oldest = newest = None
            if match:
                oldest = _iso(pd.Timestamp(match.group(1), tz="UTC").to_pydatetime())
                newest = _iso(pd.Timestamp(match.group(2), tz="UTC").to_pydatetime())
            result.append({
                "kind": "candle_chunk",
                "symbol": symbol,
                "timeframe": timeframe,
                "path": path_text,
                "rows": int(chunk_rows.get(path_text) or 0),
                "oldest": oldest,
                "newest": newest,
                "checkpoint_reconstructed": True,
            })
    return result


def finder_coverage(job: Mapping[str, Any]) -> tuple[pd.Timestamp, pd.Timestamp]:
    artifacts = _finder_artifacts(job)
    starts = [_parse_dt(item.get("oldest")) for item in artifacts]
    ends = [_parse_dt(item.get("newest")) for item in artifacts]
    starts = [value for value in starts if pd.notna(value)]
    ends = [value for value in ends if pd.notna(value)]
    return (min(starts) if starts else pd.NaT, max(ends) if ends else pd.NaT)


def candle_coverage(job: Mapping[str, Any]) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return the stored raw-candle coverage advertised by the build."""
    artifacts = _candle_artifacts(job)
    starts = [_parse_dt(item.get("oldest")) for item in artifacts]
    ends = [_parse_dt(item.get("newest")) for item in artifacts]
    starts = [value for value in starts if pd.notna(value)]
    ends = [value for value in ends if pd.notna(value)]
    return (min(starts) if starts else pd.NaT, max(ends) if ends else pd.NaT)


def load_candle_range(
    store: BuildStore,
    job: Mapping[str, Any],
    start_dt: datetime | pd.Timestamp,
    end_dt: datetime | pd.Timestamp,
    *,
    symbols: Sequence[str] | None = None,
    max_rows: int = 1_000_000,
) -> pd.DataFrame:
    """Load the complete raw OHLC movie for a date range.

    Unlike ``load_finder_range``, this function does not apply the hourly-four
    selector.  It returns every stored candle for every requested symbol and
    deduplicates provider boundary rows by ``Symbol`` + ``Datetime``.
    """
    wanted = {normalize_symbol(value) for value in symbols or [] if normalize_symbol(value)}
    start = _parse_dt(start_dt)
    end = _parse_dt(end_dt)
    if pd.isna(start) or pd.isna(end) or start > end:
        raise ValueError("Candle range requires a valid start at or before the end")
    limit = max(1, int(max_rows))
    pieces: list[pd.DataFrame] = []
    loaded_rows = 0
    artifacts = _candle_artifacts(job)
    if not artifacts:
        raise RuntimeError("This build has no durable continuous-candle artifacts; rebuild with Fast Build")

    for artifact in artifacts:
        symbol = normalize_symbol(artifact.get("symbol"))
        if wanted and symbol not in wanted:
            continue
        oldest, newest = _parse_dt(artifact.get("oldest")), _parse_dt(artifact.get("newest"))
        if (pd.notna(newest) and newest < start) or (pd.notna(oldest) and oldest > end):
            continue
        path = str(artifact.get("path") or "")
        if not path or not store.object_exists(path):
            # Old checkpoints can include an EMPTY marker instead of a parquet
            # object.  It is not a missing candle artifact and must be skipped.
            empty_marker = path.rsplit(".", 1)[0] + ".empty" if "." in path else path + ".empty"
            if empty_marker and store.object_exists(empty_marker):
                continue
            raise RuntimeError(f"Continuous candle artifact is missing for {symbol}: {path or 'unknown path'}")
        try:
            payload = store.get_object(path)
            frame = pd.read_parquet(BytesIO(payload))
        except Exception as exc:
            raise RuntimeError(f"Continuous candle artifact could not be read for {symbol}: {type(exc).__name__}") from exc
        finally:
            try:
                del payload
            except Exception:
                pass
        if frame.empty:
            continue
        time_column = next((column for column in ("open_time", "time", "Datetime", "datetime", "timestamp") if column in frame.columns), None)
        if time_column is None:
            raise RuntimeError(f"Continuous candle artifact for {symbol} has no timestamp column")
        aliases = {
            "open": "Open Price", "Open": "Open Price", "Open Price": "Open Price",
            "high": "High Price", "High": "High Price", "High Price": "High Price", "Highest Price": "High Price",
            "low": "Low Price", "Low": "Low Price", "Low Price": "Low Price", "Lowest Price": "Low Price",
            "close": "Close Price", "Close": "Close Price", "Close Price": "Close Price",
            "volume": "Volume", "Volume": "Volume",
        }
        selected = pd.DataFrame(index=frame.index)
        selected["Datetime"] = pd.to_datetime(frame[time_column], errors="coerce", utc=True)
        selected["Symbol"] = symbol
        selected["Timeframe"] = normalize_timeframe(artifact.get("timeframe") or job.get("timeframe"))
        for source, target in aliases.items():
            if source in frame.columns and target not in selected.columns:
                selected[target] = pd.to_numeric(frame[source], errors="coerce")
        required = ["Open Price", "High Price", "Low Price", "Close Price"]
        missing = [column for column in required if column not in selected.columns]
        if missing:
            raise RuntimeError(f"Continuous candle artifact for {symbol} is missing {', '.join(missing)}")
        selected = selected.loc[selected["Datetime"].between(start, end, inclusive="both")]
        selected = selected.dropna(subset=["Datetime", *required])
        if not selected.empty:
            selected["Completed Candle"] = selected["Datetime"]
            selected["History Source"] = "TWELVE_DATA"
            pieces.append(selected)
            loaded_rows += len(selected)
            if loaded_rows > limit:
                raise ValueError(f"The complete candle range exceeds {limit:,} rows. Choose a smaller date range.")
        del frame, selected

    if not pieces:
        return pd.DataFrame(columns=[
            "Datetime", "Symbol", "Timeframe", "Open Price", "High Price",
            "Low Price", "Close Price", "Volume", "Completed Candle", "History Source",
        ])
    result = pd.concat(pieces, ignore_index=True, sort=False)
    result = result.drop_duplicates(["Symbol", "Datetime"], keep="last")
    result = result.sort_values(["Datetime", "Symbol"], kind="mergesort").reset_index(drop=True)
    result.attrs["continuous_all_symbol_candles"] = True
    result.attrs["source_job_id"] = str(job.get("id") or job.get("job_id") or "")
    return result


def load_finder_range(
    store: BuildStore, job: Mapping[str, Any], start_dt: datetime | pd.Timestamp, end_dt: datetime | pd.Timestamp,
    *, symbols: Sequence[str] | None = None, include_audit: bool = True,
) -> pd.DataFrame:
    """Load only the requested range, reading one symbol artifact at a time."""
    wanted = {normalize_symbol(x) for x in symbols or [] if normalize_symbol(x)}
    pieces: list[pd.DataFrame] = []
    loaded_rows = 0
    start = _parse_dt(start_dt)
    end = _parse_dt(end_dt)
    ranked = [dict(a) for a in job.get('result_manifest') or [] if a.get('kind') == 'ranking_part']
    artifacts = ranked if ranked and not include_audit else _finder_artifacts(job)
    for artifact in artifacts:
        symbol = normalize_symbol(artifact.get("symbol"))
        if wanted and symbol not in wanted:
            continue
        oldest, newest = _parse_dt(artifact.get("oldest")), _parse_dt(artifact.get("newest"))
        if (pd.notna(newest) and newest < start) or (pd.notna(oldest) and oldest > end):
            continue
        try:
            payload = store.get_object(str(artifact["path"]))
            if include_audit:
                frame = pd.read_parquet(BytesIO(payload))
            else:
                import pyarrow.parquet as pq
                schema = pq.read_schema(BytesIO(payload))
                columns = [name for name in schema.names if name in COMPACT_FINDER_COLUMNS or name.startswith("TP Filter ") or name.startswith("p_tp_") or name in STRATEGY_COLUMNS or name in MONTHLY_METADATA or re.fullmatch(r"S\d+ (Entry Condition|Score)", name)]
                frame = pd.read_parquet(BytesIO(payload), columns=columns)
                # Repeated labels dominate large-range memory otherwise. Keep
                # exact values while sharing their categorical dictionaries.
                for column in frame.select_dtypes(include="object").columns:
                    if column == "Symbol":
                        universe = sorted(job.get("symbols") or {a.get("symbol") for a in _finder_artifacts(job) if a.get("symbol")})
                        frame[column] = pd.Categorical(frame[column], categories=universe)
                    elif frame[column].nunique(dropna=False) <= 256:
                        frame[column] = frame[column].astype("category")
            if "Datetime" in frame.columns:
                ts = pd.to_datetime(frame["Datetime"], errors="coerce", utc=True)
            elif "Completed Candle" in frame.columns:
                ts = pd.to_datetime(frame["Completed Candle"], errors="coerce", utc=True)
                frame = frame.copy()
                frame["Datetime"] = ts
            else:
                continue
            mask = ts.between(start, end, inclusive="both")
            selected = frame.loc[mask].copy()
            del frame, payload
            if not selected.empty:
                loaded_rows += len(selected)
                limit = 50_000 if include_audit else 600_000
                if loaded_rows > limit:
                    mode = "detailed audit" if include_audit else "Finder"
                    raise ValueError(f"The {mode} range exceeds {limit:,} rows. Choose a smaller date range" + (" or turn off all audit columns." if include_audit else "."))
                pieces.append(selected)
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Finder artifact could not be read for {symbol}: {type(exc).__name__}") from exc
    if not pieces:
        return pd.DataFrame()
    result = pd.concat(pieces, ignore_index=True, sort=False)
    del pieces
    if not include_audit:
        for column in result.select_dtypes(include="object").columns:
            if result[column].nunique(dropna=False) <= 256:
                result[column] = result[column].astype("category")
    if "Datetime" in result.columns:
        result["Datetime"] = pd.to_datetime(result["Datetime"], errors="coerce", utc=True)
    result = result.sort_values([c for c in ["Datetime", "Symbol"] if c in result.columns], kind="mergesort").reset_index(drop=True)
    result.attrs["compact_audit_projection"] = not include_audit
    result.attrs["hourly_selection_finalized"] = bool(ranked and not include_audit)
    return result


def put_dataframe(store: BuildStore, path: str, frame: pd.DataFrame) -> dict[str, Any]:
    """Atomically materialize a non-empty Parquet artifact."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("Cannot persist an empty dataframe artifact")
    buffer = BytesIO()
    frame.to_parquet(buffer, index=False, compression="zstd")
    payload = buffer.getvalue()
    store.put_object(path, payload, content_type="application/vnd.apache.parquet", upsert=True)
    return {"path": path, "rows": int(len(frame)), "bytes": int(len(payload)), "sha256": hashlib.sha256(payload).hexdigest()}


__all__ = [
    "VERSION", "KIND", "DEFAULT_CHUNK_DAYS", "DEFAULT_HISTORY_YEARS", "ACTIVE_STATUSES", "TERMINAL_STATUSES",
    "BuildStore", "BuildBackendInfo", "backend_info", "normalize_symbol", "normalize_timeframe", "current_user_key",
    "chunk_windows", "queue_job", "latest_job", "request_stop", "request_resume", "update_checkpoint", "finish_job",
    "heartbeat", "finder_coverage", "candle_coverage", "load_finder_range", "load_candle_range", "load_middle_ranking_csv", "put_dataframe", "_chunk_key", "_finder_key", "_finder_part_key", "_json_object_key", "_middle_ranking_csv_key", "COMPACT_FINDER_COLUMNS",
]


def load_selected_finder_audit(store: BuildStore, job: Mapping[str, Any], selected: pd.DataFrame) -> pd.DataFrame:
    """Attach full audit columns to selected hourly entries, one part at a time."""
    entries = selected.copy()
    if len(entries) > 50_000:
        raise ValueError('Detailed audit exceeds 50,000 hourly entries. Choose a smaller date range.')
    if entries.empty:
        return entries
    entries['Datetime'] = pd.to_datetime(entries['Datetime'], errors='coerce', utc=True)
    wanted = {str(symbol): set(group['Datetime']) for symbol, group in entries.groupby('Symbol', observed=True)}
    pieces = []
    for artifact in _finder_artifacts(job):
        symbol = str(artifact.get('symbol'))
        if symbol not in wanted:
            continue
        times = wanted[symbol]
        oldest, newest = _parse_dt(artifact.get('oldest')), _parse_dt(artifact.get('newest'))
        if pd.notna(oldest) and oldest > max(times) or pd.notna(newest) and newest < min(times):
            continue
        payload = store.get_object(str(artifact['path']))
        frame = pd.read_parquet(BytesIO(payload))
        timestamps = pd.to_datetime(frame['Datetime'], errors='coerce', utc=True)
        columns = [c for c in frame if c in STRATEGY_COLUMNS or re.match(r'^S\d+ (Entry Condition|Signal|Reason|Score)$', c)]
        matched = frame.loc[timestamps.isin(times), columns].copy()
        if not matched.empty:
            matched['Datetime'] = timestamps.loc[matched.index]
            matched['Symbol'] = symbol
            pieces.append(matched)
        del frame, payload
    if not pieces:
        raise RuntimeError('No detailed strategy audit artifacts match the hourly entries.')
    audit = pd.concat(pieces, ignore_index=True).drop_duplicates(['Symbol', 'Datetime'], keep='last')
    # Fast storage retains conditions/scores. Signal is exactly reconstructible;
    # lengthy explanations remain available via normal FULL builds.
    if 'S1 Signal' not in audit:
        bias = entries[['Symbol', 'Datetime', 'Middle Regime Bias']]
        audit = audit.merge(bias, on=['Symbol', 'Datetime'], how='left')
        for label in STRATEGY_COLUMNS:
            i=int(label[1:])
            hit = audit[f'S{i}'].fillna(0).ne(0)
            audit[f'S{i} Entry Condition'] = hit
            audit[f'S{i} Signal'] = np.where(audit[f'S{i}'].eq(1),'BUY',np.where(audit[f'S{i}'].eq(-1),'SELL','NO ENTRY'))
        audit.drop(columns=['Middle Regime Bias'], inplace=True)
    entries = entries.drop(columns=[c for c in audit if c not in {'Symbol', 'Datetime'} and c in entries])
    result = entries.merge(audit, on=['Symbol','Datetime'], how='left', validate='one_to_one')
    if result.filter(regex=r'^S\d+ Entry Condition$').isna().any().any():
        raise RuntimeError('Some hourly entries have no saved strategy audit; rebuild the affected history.')
    result.attrs['compact_audit_projection'] = False
    return result
