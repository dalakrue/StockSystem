"""Durable completed-generation registry with timeframe-aware validity.

Local SQLite remains the default for desktop use. Deployments can place both the
registry and snapshots on a durable mounted volume by setting
``ADX_DURABLE_DB_PATH`` and ``ADX_DURABLE_SNAPSHOT_DIR``.  Session State is never
used as the only persistence authority.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import os
import sqlite3

import pandas as pd

SCHEMA_VERSION = "generation-registry-20260702-v1"
DEFAULT_CALCULATION_VERSION = "adx-protected-calculation-current"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "generation_registry_20260702.sqlite3"
DEFAULT_SNAPSHOT_DIR = ROOT / "data" / "multi_symbol_runtime_20260701"


def registry_path() -> Path:
    value = os.environ.get("ADX_DURABLE_DB_PATH", "").strip()
    return Path(value).expanduser().resolve() if value else DEFAULT_DB_PATH


def snapshot_root() -> Path:
    value = os.environ.get("ADX_DURABLE_SNAPSHOT_DIR", "").strip()
    return Path(value).expanduser().resolve() if value else DEFAULT_SNAPSHOT_DIR


def _connect(path: Path | str | None = None) -> sqlite3.Connection:
    db = Path(path or registry_path())
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), timeout=8.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


def migrate_generation_registry(path: Path | str | None = None) -> dict[str, Any]:
    db = Path(path or registry_path())
    with _connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS generation_registry (
                profile_id TEXT NOT NULL DEFAULT 'default',
                parent_run_id TEXT NOT NULL,
                child_run_id TEXT NOT NULL,
                canonical_run_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL,
                settings_main_symbol TEXT NOT NULL,
                connector_symbol TEXT NOT NULL,
                lunch_display_symbol TEXT NOT NULL,
                active_snapshot_symbol TEXT NOT NULL,
                symbol TEXT NOT NULL,
                selected_symbols_json TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                completed_broker_candle TEXT NOT NULL,
                valid_until TEXT NOT NULL,
                runtime_snapshot_path TEXT NOT NULL,
                runtime_snapshot_sha256 TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                calculation_version TEXT NOT NULL,
                publication_status TEXT NOT NULL,
                last_active_route TEXT,
                last_open_lunch_field TEXT,
                created_at TEXT NOT NULL,
                last_access_time TEXT NOT NULL,
                PRIMARY KEY(profile_id, parent_run_id, child_run_id, symbol, timeframe, completed_broker_candle, snapshot_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_generation_registry_latest
                ON generation_registry(profile_id, valid_until DESC, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_generation_registry_symbol
                ON generation_registry(profile_id, symbol, timeframe, completed_broker_candle DESC);
            CREATE TABLE IF NOT EXISTS generation_registry_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id TEXT NOT NULL,
                parent_run_id TEXT,
                child_run_id TEXT,
                symbol TEXT,
                event_type TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    return {"ok": True, "path": str(db), "schema_version": SCHEMA_VERSION}


def timeframe_delta(timeframe: Any) -> pd.Timedelta:
    text = str(timeframe or "H1").strip().upper()
    aliases = {"60": "H1", "30": "M30", "240": "H4"}
    text = aliases.get(text, text)
    if text.startswith("M"):
        try:
            return pd.Timedelta(minutes=max(1, int(text[1:])))
        except Exception:
            return pd.Timedelta(minutes=30)
    if text.startswith("H"):
        try:
            return pd.Timedelta(hours=max(1, int(text[1:])))
        except Exception:
            return pd.Timedelta(hours=1)
    if text.startswith("D"):
        try:
            return pd.Timedelta(days=max(1, int(text[1:])))
        except Exception:
            return pd.Timedelta(days=1)
    return pd.Timedelta(hours=1)


def calculate_valid_until(completed_broker_candle: Any, timeframe: Any, grace_seconds: int | None = None) -> str:
    stamp = pd.to_datetime(completed_broker_candle, errors="coerce", utc=True)
    if pd.isna(stamp):
        raise ValueError("completed broker candle is unavailable")
    configured = grace_seconds
    if configured is None:
        try:
            configured = int(os.environ.get("ADX_BROKER_COMPLETION_GRACE_SECONDS", "90"))
        except Exception:
            configured = 90
    valid = pd.Timestamp(stamp) + timeframe_delta(timeframe) + pd.Timedelta(seconds=max(0, int(configured)))
    return valid.isoformat()


def file_sha256(path: Path | str) -> str:
    source = Path(path)
    digest = sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_list(values: Sequence[Any] | Any) -> str:
    if isinstance(values, str):
        values = [values]
    return json.dumps([str(value) for value in (values or [])], separators=(",", ":"))


def record_event(
    event_type: str,
    detail: Mapping[str, Any],
    *,
    profile_id: str = "default",
    parent_run_id: str | None = None,
    child_run_id: str | None = None,
    symbol: str | None = None,
    path: Path | str | None = None,
) -> None:
    migrate_generation_registry(path)
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO generation_registry_events(profile_id,parent_run_id,child_run_id,symbol,event_type,detail_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (
                profile_id, parent_run_id, child_run_id, symbol, str(event_type),
                json.dumps(dict(detail), sort_keys=True, default=str), pd.Timestamp.now(tz="UTC").isoformat(),
            ),
        )
        conn.commit()


def register_completed_generation(
    *,
    context: Mapping[str, Any],
    runtime_snapshot_path: Path | str,
    publication_status: str,
    calculation_version: str = DEFAULT_CALCULATION_VERSION,
    profile_id: str = "default",
    last_active_route: str = "Lunch",
    last_open_lunch_field: str = "Field 10",
    path: Path | str | None = None,
) -> dict[str, Any]:
    migrate_generation_registry(path)
    snapshot = Path(runtime_snapshot_path)
    if not snapshot.is_file():
        return {"ok": False, "status": "SNAPSHOT_MISSING", "path": str(snapshot)}
    required = (
        "parent_run_id", "child_run_id", "canonical_run_id", "source_id", "snapshot_hash",
        "settings_main_symbol", "connector_symbol", "lunch_display_symbol", "active_snapshot_symbol",
        "timeframe", "completed_broker_candle",
    )
    missing = [name for name in required if not context.get(name)]
    if missing:
        return {"ok": False, "status": "IDENTITY_MISSING", "missing": missing}
    symbol = str(context.get("symbol") or context.get("active_snapshot_symbol") or context.get("lunch_display_symbol"))
    valid_until = str(context.get("valid_until") or calculate_valid_until(context["completed_broker_candle"], context["timeframe"]))
    now = pd.Timestamp.now(tz="UTC").isoformat()
    checksum = file_sha256(snapshot)
    values = (
        profile_id, str(context["parent_run_id"]), str(context["child_run_id"]), str(context["canonical_run_id"]),
        str(context["source_id"]), str(context["snapshot_hash"]), str(context["settings_main_symbol"]),
        str(context["connector_symbol"]), str(context["lunch_display_symbol"]), str(context["active_snapshot_symbol"]),
        symbol, _json_list(context.get("selected_symbols") or [symbol]), str(context["timeframe"]).upper(),
        str(context["completed_broker_candle"]), valid_until, str(snapshot.resolve()), checksum,
        SCHEMA_VERSION, str(calculation_version), str(publication_status).upper(), last_active_route,
        last_open_lunch_field, now, now,
    )
    with _connect(path) as conn:
        conn.execute(
            """INSERT INTO generation_registry(
                profile_id,parent_run_id,child_run_id,canonical_run_id,source_id,snapshot_hash,
                settings_main_symbol,connector_symbol,lunch_display_symbol,active_snapshot_symbol,
                symbol,selected_symbols_json,timeframe,completed_broker_candle,valid_until,
                runtime_snapshot_path,runtime_snapshot_sha256,schema_version,calculation_version,
                publication_status,last_active_route,last_open_lunch_field,created_at,last_access_time
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(profile_id,parent_run_id,child_run_id,symbol,timeframe,completed_broker_candle,snapshot_hash)
            DO UPDATE SET publication_status=excluded.publication_status,
                          lunch_display_symbol=excluded.lunch_display_symbol,
                          active_snapshot_symbol=excluded.active_snapshot_symbol,
                          last_active_route=excluded.last_active_route,
                          last_open_lunch_field=excluded.last_open_lunch_field,
                          valid_until=excluded.valid_until,
                          runtime_snapshot_path=excluded.runtime_snapshot_path,
                          runtime_snapshot_sha256=excluded.runtime_snapshot_sha256,
                          last_access_time=excluded.last_access_time""",
            values,
        )
        conn.commit()
    return {
        "ok": True, "status": "REGISTERED", "symbol": symbol, "valid_until": valid_until,
        "snapshot_path": str(snapshot.resolve()), "snapshot_sha256": checksum,
        "schema_version": SCHEMA_VERSION, "calculation_version": calculation_version,
    }


def _row_to_dict(row: sqlite3.Row | tuple[Any, ...], columns: Sequence[str]) -> dict[str, Any]:
    data = dict(zip(columns, row))
    try:
        data["selected_symbols"] = json.loads(data.pop("selected_symbols_json") or "[]")
    except Exception:
        data["selected_symbols"] = []
    return data


def latest_valid_generation(
    *, profile_id: str = "default", now: Any = None, path: Path | str | None = None,
    symbol: str | None = None, timeframe: str | None = None,
) -> dict[str, Any]:
    migrate_generation_registry(path)
    current = pd.to_datetime(now, errors="coerce", utc=True) if now is not None else pd.Timestamp.now(tz="UTC")
    if pd.isna(current):
        current = pd.Timestamp.now(tz="UTC")
    clauses = ["profile_id=?", "valid_until>=?", "publication_status IN ('COMPLETED','ALREADY_EXISTS_VALID','REPAIRED_FROM_VALID_SNAPSHOT')"]
    params: list[Any] = [profile_id, pd.Timestamp(current).isoformat()]
    if symbol:
        clauses.append("symbol=?"); params.append(str(symbol).upper())
    if timeframe:
        clauses.append("timeframe=?"); params.append(str(timeframe).upper())
    with _connect(path) as conn:
        cursor = conn.execute(
            "SELECT * FROM generation_registry WHERE " + " AND ".join(clauses) + " ORDER BY completed_broker_candle DESC,created_at DESC LIMIT 1",
            tuple(params),
        )
        row = cursor.fetchone()
        columns = [item[0] for item in cursor.description] if cursor.description else []
        if not row:
            return {}
        result = _row_to_dict(row, columns)
        conn.execute(
            "UPDATE generation_registry SET last_access_time=? WHERE profile_id=? AND parent_run_id=? AND child_run_id=? AND symbol=? AND snapshot_hash=?",
            (pd.Timestamp.now(tz="UTC").isoformat(), profile_id, result["parent_run_id"], result["child_run_id"], result["symbol"], result["snapshot_hash"]),
        )
        conn.commit()
    return result


def list_completed_generations(
    *, parent_run_id: str | None = None, profile_id: str = "default", path: Path | str | None = None,
) -> list[dict[str, Any]]:
    migrate_generation_registry(path)
    clauses = ["profile_id=?", "publication_status IN ('COMPLETED','ALREADY_EXISTS_VALID','REPAIRED_FROM_VALID_SNAPSHOT')"]
    params: list[Any] = [profile_id]
    if parent_run_id:
        clauses.append("parent_run_id=?"); params.append(parent_run_id)
    with _connect(path) as conn:
        cursor = conn.execute(
            "SELECT * FROM generation_registry WHERE " + " AND ".join(clauses) + " ORDER BY completed_broker_candle DESC,created_at DESC",
            tuple(params),
        )
        columns = [item[0] for item in cursor.description] if cursor.description else []
        return [_row_to_dict(row, columns) for row in cursor.fetchall()]


def verify_registry_snapshot(record: Mapping[str, Any]) -> dict[str, Any]:
    source = Path(str(record.get("runtime_snapshot_path") or ""))
    if not source.is_file():
        return {"ok": False, "status": "SNAPSHOT_MISSING", "path": str(source)}
    expected = str(record.get("runtime_snapshot_sha256") or "")
    actual = file_sha256(source)
    if expected and actual != expected:
        return {"ok": False, "status": "CHECKSUM_MISMATCH", "expected": expected, "actual": actual}
    if str(record.get("schema_version") or "") != SCHEMA_VERSION:
        return {"ok": False, "status": "SCHEMA_VERSION_MISMATCH", "found": record.get("schema_version")}
    return {"ok": True, "status": "VERIFIED", "path": str(source), "sha256": actual}


__all__ = [
    "SCHEMA_VERSION", "DEFAULT_CALCULATION_VERSION", "registry_path", "snapshot_root",
    "migrate_generation_registry", "calculate_valid_until", "timeframe_delta", "file_sha256",
    "register_completed_generation", "latest_valid_generation", "list_completed_generations",
    "verify_registry_snapshot", "record_event",
]
