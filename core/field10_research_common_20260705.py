"""Shared contracts for the Field 10 horizon/connected/tail shadow candidate.

Market identity is inherited from the immutable Field 10 daily snapshot.  System
UTC time is used only for audit creation timestamps, never to select a candle.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import math
import sqlite3

import numpy as np
import pandas as pd

from core.multi_symbol_field10_20260701 import DB_PATH, normalize_symbol

CANDIDATE_NAME = "field10_horizon_connected_tail_candidate_v1"
MODEL_VERSION = "field10-horizon-connected-tail-20260705-v1"
FEATURE_VERSION = "field10-horizon-connected-tail-features-20260705-v1"
FORMULA_VERSION = "field10-horizon-connected-tail-formulas-20260705-v1"
THRESHOLD_VERSION = "field10-horizon-connected-tail-thresholds-20260705-v1"
MIGRATION_ID = "20260705_field10_horizon_connected_tail_candidate_v1"
HORIZONS: tuple[int, ...] = (1, 3, 6, 12, 24, 36)
MAX_SYMBOL_UNIVERSE = 12
REQUIRED_H1_ROWS = 600
PROMOTION_STATUS = "SHADOW VALIDATION — NO PRODUCTION INFLUENCE"

SHADOW_TABLES: tuple[str, ...] = (
    "field10_horizon_volatility_shadow",
    "field10_semivariance_shadow",
    "field10_gas_state_shadow",
    "field10_tail_risk_shadow",
    "field10_copula_shadow",
    "field10_connectedness_shadow",
    "field10_frequency_connectedness_shadow",
    "field10_model_confidence_set",
    "field10_sample_split_validation",
    "field10_rank_components_v2",
)


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if isinstance(value, pd.DataFrame):
        return [json_safe(v) for v in value.to_dict("records")]
    if isinstance(value, pd.Series):
        return [json_safe(v) for v in value.tolist()]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if value is pd.NA:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def deterministic_hash(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def clip(value: Any, lower: float, upper: float) -> float | None:
    number = finite(value)
    return None if number is None else float(np.clip(number, lower, upper))


def audit_system_time() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path: Path | str = DB_PATH, *, read_only: bool = False) -> sqlite3.Connection:
    resolved = Path(path).resolve()
    if read_only:
        conn = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True, timeout=8.0)
    else:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(resolved), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def schema_ready(path: Path | str = DB_PATH) -> tuple[bool, list[str]]:
    try:
        with connect(path, read_only=True) as conn:
            present = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except Exception as exc:
        return False, [f"database unavailable: {type(exc).__name__}: {exc}"]
    missing = sorted(set(SHADOW_TABLES) - present)
    return not missing, missing


@dataclass(frozen=True)
class CanonicalIdentity:
    daily_snapshot_id: str
    parent_run_id: str
    child_run_id: str | None
    canonical_run_id: str | None
    symbol: str
    timeframe: str
    broker_day: str
    completed_h1_candle: str
    source_id: str | None
    source_hash: str | None
    snapshot_hash: str | None
    universe_hash: str
    ordered_symbol_universe: tuple[str, ...]
    model_version: str = MODEL_VERSION
    feature_version: str = FEATURE_VERSION
    formula_version: str = FORMULA_VERSION
    threshold_version: str = THRESHOLD_VERSION

    def cache_key(self) -> str:
        return deterministic_hash(asdict(self))


def _decode(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return value
    try:
        return json.loads(str(value or ""))
    except Exception:
        return default


def load_snapshot_contract(
    daily_snapshot_id: str | None = None,
    *,
    path: Path | str = DB_PATH,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with connect(path, read_only=True) as conn:
        if not daily_snapshot_id:
            found = conn.execute(
                "SELECT daily_snapshot_id FROM field10_daily_snapshot ORDER BY broker_day DESC LIMIT 1"
            ).fetchone()
            daily_snapshot_id = None if found is None else str(found[0])
        if not daily_snapshot_id:
            return {}, []
        meta_row = conn.execute(
            "SELECT * FROM field10_daily_snapshot WHERE daily_snapshot_id=?", (daily_snapshot_id,)
        ).fetchone()
        if meta_row is None:
            return {}, []
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM field10_daily_snapshot_symbol WHERE daily_snapshot_id=? "
            "ORDER BY daily_rank IS NULL,daily_rank,symbol", (daily_snapshot_id,)
        )]
    meta = dict(meta_row)
    for key in (
        "ordered_symbol_universe_json", "secondary_symbols_json", "provider_aliases_json",
        "child_run_ids_json", "canonical_run_ids_json", "source_ids_json",
        "snapshot_hashes_json", "metadata_json",
    ):
        meta[key.removesuffix("_json")] = _decode(meta.get(key), [] if "symbols" in key or "universe" in key else {})
    return meta, rows


def build_identity(meta: Mapping[str, Any], row: Mapping[str, Any], *, path: Path | str = DB_PATH) -> CanonicalIdentity:
    symbol = normalize_symbol(row.get("symbol"))
    # The immutable parent snapshot metadata is the first source of child identity.
    child_run_id: str | None = None
    child_timeframe: str | None = None
    child_ids = meta.get("child_run_ids") or _decode(meta.get("child_run_ids_json"), {})
    universe_raw_for_child = meta.get("ordered_symbol_universe") or _decode(meta.get("ordered_symbol_universe_json"), [])
    if isinstance(child_ids, Mapping):
        raw_child = child_ids.get(symbol) or child_ids.get(symbol.upper())
        child_run_id = None if raw_child is None else str(raw_child or "") or None
    elif isinstance(child_ids, (list, tuple)):
        ordered = [normalize_symbol(v) for v in universe_raw_for_child]
        if symbol in ordered and ordered.index(symbol) < len(child_ids):
            raw_child = child_ids[ordered.index(symbol)]
            child_run_id = None if raw_child is None else str(raw_child or "") or None
    # Registry lookup is a recovery fallback only when the locked metadata did not
    # carry the child id. It never overrides the immutable snapshot identity.
    if child_run_id is None:
        with connect(path, read_only=True) as conn:
            try:
                found = conn.execute(
                    "SELECT child_run_id,timeframe FROM child_generation_registry WHERE parent_run_id=? AND symbol=? "
                    "ORDER BY completed_broker_candle DESC,updated_at DESC LIMIT 1",
                    (str(meta.get("parent_run_id") or ""), symbol),
                ).fetchone()
                child_run_id = None if found is None else str(found[0] or "") or None
                child_timeframe = None if found is None or len(found) < 2 else str(found[1] or "").upper() or None
            except sqlite3.Error:
                child_run_id = None
    if child_timeframe is None and child_run_id:
        with connect(path, read_only=True) as conn:
            try:
                found_tf = conn.execute(
                    "SELECT timeframe FROM child_generation_registry WHERE child_run_id=? ORDER BY updated_at DESC LIMIT 1",
                    (child_run_id,),
                ).fetchone()
                child_timeframe = None if found_tf is None else str(found_tf[0] or "").upper() or None
            except sqlite3.Error:
                child_timeframe = None
    universe_raw = meta.get("ordered_symbol_universe") or _decode(meta.get("ordered_symbol_universe_json"), [])
    universe = tuple(normalize_symbol(v) for v in universe_raw if normalize_symbol(v))
    source_id = row.get("source_id")
    snapshot_hash = row.get("snapshot_hash")
    # Preserve the exact immutable provider/snapshot hash. Never manufacture a
    # replacement hash that could be mistaken for upstream source identity.
    source_hash_raw = snapshot_hash or row.get("content_hash")
    source_hash = None if source_hash_raw is None else str(source_hash_raw)
    return CanonicalIdentity(
        daily_snapshot_id=str(meta.get("daily_snapshot_id") or ""),
        parent_run_id=str(meta.get("parent_run_id") or ""),
        child_run_id=child_run_id,
        canonical_run_id=None if row.get("canonical_run_id") is None else str(row.get("canonical_run_id")),
        symbol=symbol,
        timeframe=str(row.get("timeframe") or meta.get("timeframe") or child_timeframe or "H1").upper(),
        broker_day=str(meta.get("broker_day") or row.get("broker_day") or ""),
        completed_h1_candle=str(meta.get("latest_completed_h1") or row.get("completed_candle") or ""),
        source_id=None if source_id is None else str(source_id),
        source_hash=source_hash,
        snapshot_hash=None if snapshot_hash is None else str(snapshot_hash),
        universe_hash=str(meta.get("universe_hash") or ""),
        ordered_symbol_universe=universe,
    )


def exact_symbol_state(state: Mapping[str, Any], symbol: str) -> tuple[Mapping[str, Any] | None, str | None]:
    from core.field10_institutional_shadow_20260704 import _exact_state_for_symbol
    return _exact_state_for_symbol(state, normalize_symbol(symbol))


def exact_completed_h1(
    state: Mapping[str, Any], identity: CanonicalIdentity, *, required_rows: int = REQUIRED_H1_ROWS
) -> tuple[pd.DataFrame, list[str]]:
    # This research candidate's horizons are defined in H1 bars. It must never
    # silently consume H4 candles and label four-hour bars as one-hour outcomes.
    if str(identity.timeframe or "H1").upper() != "H1":
        return pd.DataFrame(), [f"H1-only research candidate is unavailable for {identity.timeframe}; selected-timeframe production remains authoritative"]
    from core.field10_institutional_shadow_20260704 import _find_ohlc, normalize_completed_h1
    exact, reason = exact_symbol_state(state, identity.symbol)
    if exact is None:
        return pd.DataFrame(), [reason or f"exact state unavailable for {identity.symbol}"]
    raw = _find_ohlc(exact)
    frame, reasons = normalize_completed_h1(
        raw, cutoff=identity.completed_h1_candle, max_rows=required_rows, required_rows=required_rows
    )
    if not frame.empty:
        frame.attrs["symbol"] = identity.symbol
        frame.attrs["completed_h1_candle"] = identity.completed_h1_candle
        frame.attrs["source_hash"] = identity.source_hash
    return frame, reasons


def _walk_frames(value: Any, *, depth: int = 0, seen: set[int] | None = None) -> list[pd.DataFrame]:
    if depth > 6:
        return []
    seen = seen if seen is not None else set()
    if isinstance(value, (Mapping, list, tuple, pd.DataFrame)):
        marker = id(value)
        if marker in seen:
            return []
        seen.add(marker)
    if isinstance(value, pd.DataFrame):
        return [value]
    frames: list[pd.DataFrame] = []
    if isinstance(value, Mapping):
        for child in value.values():
            frames.extend(_walk_frames(child, depth=depth + 1, seen=seen))
    elif isinstance(value, (list, tuple)):
        for child in value[:100]:
            frames.extend(_walk_frames(child, depth=depth + 1, seen=seen))
    return frames


def completed_intraday_frame(state: Mapping[str, Any], identity: CanonicalIdentity) -> tuple[pd.DataFrame, str | None]:
    exact, reason = exact_symbol_state(state, identity.symbol)
    if exact is None:
        return pd.DataFrame(), reason
    cutoff = pd.to_datetime(identity.completed_h1_candle, errors="coerce", utc=True)
    if pd.isna(cutoff):
        return pd.DataFrame(), "invalid canonical completed H1 candle"
    candidates: list[tuple[float, pd.DataFrame]] = []
    for raw in _walk_frames(exact):
        if raw.empty or len(raw) < 30:
            continue
        lookup = {str(c).strip().lower().replace("_", " "): c for c in raw.columns}
        time_col = next((lookup.get(k) for k in ("time", "timestamp", "datetime", "date", "broker candle time") if lookup.get(k) is not None), None)
        close_col = lookup.get("close")
        if time_col is None and isinstance(raw.index, pd.DatetimeIndex):
            temp = raw.reset_index().rename(columns={raw.index.name or "index": "__time"})
            time_col, raw = "__time", temp
            lookup = {str(c).strip().lower().replace("_", " "): c for c in raw.columns}
            close_col = lookup.get("close")
        if time_col is None or close_col is None:
            continue
        out = pd.DataFrame({
            "time": pd.to_datetime(raw[time_col], errors="coerce", utc=True),
            "close": pd.to_numeric(raw[close_col], errors="coerce"),
        }).dropna().sort_values("time").drop_duplicates("time", keep="last")
        out = out.loc[out["time"] <= cutoff]
        if len(out) < 30:
            continue
        median_minutes = float(out["time"].diff().dropna().dt.total_seconds().median() / 60.0)
        if 0.5 <= median_minutes <= 5.5:
            candidates.append((median_minutes, out))
    if not candidates:
        return pd.DataFrame(), "completed M1/M5 evidence unavailable"
    minutes, best = sorted(candidates, key=lambda item: (item[0], -len(item[1])))[0]
    best = best.loc[best["time"] <= cutoff].tail(60 * 24 * 10).reset_index(drop=True)
    best.attrs["intraday_minutes"] = minutes
    return best, None


def direction_sign(bias: Any) -> int:
    text = str(bias or "").strip().upper()
    return 1 if text == "BUY" else -1 if text == "SELL" else 0


def identity_columns(identity: CanonicalIdentity, *, validation_status: str, missing_reason: str | None = None) -> dict[str, Any]:
    return {
        "daily_snapshot_id": identity.daily_snapshot_id,
        "parent_run_id": identity.parent_run_id,
        "child_run_id": identity.child_run_id,
        "symbol": identity.symbol,
        "timeframe": identity.timeframe,
        "broker_day": identity.broker_day,
        "completed_broker_candle": identity.completed_h1_candle,
        "model_version": identity.model_version,
        "feature_version": identity.feature_version,
        "formula_version": identity.formula_version,
        "threshold_version": identity.threshold_version,
        "source_id": identity.source_id,
        "source_hash": identity.source_hash,
        "snapshot_hash": identity.snapshot_hash,
        "universe_hash": identity.universe_hash,
        "validation_status": validation_status,
        "missing_reason": missing_reason,
        "created_system_time": audit_system_time(),
    }


def insert_or_ignore(conn: sqlite3.Connection, table: str, payload: Mapping[str, Any]) -> int:
    columns = list(payload)
    before = conn.total_changes
    conn.execute(
        f"INSERT OR IGNORE INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
        tuple(json_safe(payload[c]) for c in columns),
    )
    return int(conn.total_changes - before)


__all__ = [
    "CANDIDATE_NAME", "MODEL_VERSION", "FEATURE_VERSION", "FORMULA_VERSION", "THRESHOLD_VERSION",
    "MIGRATION_ID", "HORIZONS", "MAX_SYMBOL_UNIVERSE", "REQUIRED_H1_ROWS", "PROMOTION_STATUS",
    "SHADOW_TABLES", "CanonicalIdentity", "canonical_json", "deterministic_hash", "finite", "clip",
    "audit_system_time", "connect", "schema_ready", "load_snapshot_contract", "build_identity",
    "exact_symbol_state", "exact_completed_h1", "completed_intraday_frame", "direction_sign",
    "identity_columns", "insert_or_ignore", "json_safe",
]
