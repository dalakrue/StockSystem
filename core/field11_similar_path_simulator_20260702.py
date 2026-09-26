"""Field 11 historical-analogue path simulator.

Additive architecture:
- consumes completed-candle OHLC and the immutable Field 10/canonical identity;
- prepares a compact historical feature/index artifact only from the existing
  Settings-owned multi-symbol transaction;
- performs bounded shortlist matching and scenario clustering from persisted
  artifacts when Lunch Field 11 is opened;
- never mutates Fields 1-10, the global symbol widget, or the canonical snapshot.

The output is historical analogue evidence, not a guaranteed prediction.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any
import gzip
import json
import math
import sqlite3
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import RobustScaler

from core.multi_symbol_field10_20260701 import (
    CACHE_DIR, DB_PATH as FIELD10_DB_PATH, available_saved_symbols, normalize_symbol, normalize_selected,
)
from core.serialization_compat_20260702 import loads as serializer_loads
from core.sqlite_readonly_20260704 import connect_readonly

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "data" / "field11_similar_path_20260702"
DB_PATH = ROOT / "data" / "field11_similar_path_20260702.sqlite3"
INDEX_VERSION = "field11-index-20260702-v1"
FEATURE_VERSION = "field11-feature-fingerprint-20260702-v1"
SIMULATOR_VERSION = "field11-hybrid-analogue-20260702-v1"
SCHEMA_VERSION = 1
SHAPE_BARS = 12
MAX_SHORTLIST = 500

FEATURE_COLUMNS = [
    "return_1", "return_2", "return_3", "return_6", "return_12", "return_24",
    "body_ratio", "upper_wick_ratio", "lower_wick_ratio", "gap_ratio",
    "distance_rolling_high", "distance_rolling_low", "breakout_distance",
    "pullback_depth", "momentum", "momentum_acceleration", "mean_reversion_pressure",
    "path_curvature", "directional_persistence", "rsi", "rsi_slope", "macd",
    "macd_histogram", "macd_slope", "ema_order", "ema_slope_fast", "ema_slope_slow",
    "price_to_ema_fast", "price_to_ema_slow", "atr", "atr_percentile",
    "realized_volatility", "downside_volatility", "volatility_of_volatility",
    "bollinger_width", "compression_score", "expansion_score", "support_distance",
    "resistance_distance", "broker_hour_sin", "broker_hour_cos", "weekday_sin", "weekday_cos",
]
SHAPE_COLUMNS = [f"shape_return_{index}" for index in range(1, SHAPE_BARS + 1)]


@dataclass(frozen=True)
class Field11Selection:
    symbol: str
    timeframe: str = "H1"
    source_candle: str | None = None
    horizon_hours: int = 6
    lookback_days: int = 365
    requested_analogues: int = 30
    minimum_similarity: float = 70.0
    similarity_engine: str = "Hybrid Recommended"
    historical_source: str = "same symbol only"
    scenario_count: int = 3
    weighting_policy: str = "similarity softmax"
    exact_regime_match: bool = False
    same_broker_hour_only: bool = False
    compatible_hour_range: int = 2
    high_impact_news_exclusion: bool = True
    spread_percentile_limit: float = 95.0
    field10_rank_min: int | None = None
    field10_rank_max: int | None = None
    field10_grade: str | None = None
    filters: Mapping[str, Any] = field(default_factory=dict)

    def normalized(self) -> "Field11Selection":
        return Field11Selection(
            symbol=normalize_symbol(self.symbol),
            timeframe=str(self.timeframe or "H1").upper(),
            source_candle=self.source_candle,
            horizon_hours=max(1, min(int(self.horizon_hours), 24)),
            lookback_days=max(25, min(int(self.lookback_days), 5000)),
            requested_analogues=max(3, min(int(self.requested_analogues), 100)),
            minimum_similarity=max(0.0, min(float(self.minimum_similarity), 100.0)),
            similarity_engine=str(self.similarity_engine or "Hybrid Recommended"),
            historical_source=str(self.historical_source or "same symbol only"),
            scenario_count=max(1, min(int(self.scenario_count), 5)),
            weighting_policy=str(self.weighting_policy or "similarity softmax"),
            exact_regime_match=bool(self.exact_regime_match),
            same_broker_hour_only=bool(self.same_broker_hour_only),
            compatible_hour_range=max(0, min(int(self.compatible_hour_range), 12)),
            high_impact_news_exclusion=bool(self.high_impact_news_exclusion),
            spread_percentile_limit=max(0.0, min(float(self.spread_percentile_limit), 100.0)),
            field10_rank_min=self.field10_rank_min,
            field10_rank_max=self.field10_rank_max,
            field10_grade=self.field10_grade,
            filters=dict(self.filters or {}),
        )


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"), default=str)


def deterministic_hash(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


def migrate_field11_database(path: Path | str = DB_PATH) -> dict[str, Any]:
    with _connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS field11_schema_migration(
                version INTEGER PRIMARY KEY,
                applied_at_utc TEXT NOT NULL,
                description TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS field11_index_manifest(
                index_id TEXT PRIMARY KEY,
                canonical_run_id TEXT NOT NULL,
                field10_daily_rank_id TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL,
                broker_date TEXT NOT NULL,
                source_candle_time TEXT NOT NULL,
                parent_run_id TEXT NOT NULL,
                symbol_universe_json TEXT NOT NULL,
                supported_timeframes_json TEXT NOT NULL,
                feature_version TEXT NOT NULL,
                index_version TEXT NOT NULL,
                feature_path TEXT NOT NULL,
                ohlc_path TEXT NOT NULL,
                scaler_path TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                symbol_count INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_field11_index_identity
                ON field11_index_manifest(canonical_run_id,snapshot_hash,broker_date,status);
            CREATE TABLE IF NOT EXISTS field11_simulator_run(
                simulator_run_id TEXT PRIMARY KEY,
                selection_hash TEXT NOT NULL UNIQUE,
                index_id TEXT NOT NULL,
                canonical_run_id TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                source_timeframe TEXT NOT NULL,
                source_broker_candle TEXT NOT NULL,
                horizon_hours INTEGER NOT NULL,
                selection_json TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                scenarios_json TEXT NOT NULL,
                simulator_grade TEXT NOT NULL,
                drift_status TEXT NOT NULL,
                outcome_status TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY(index_id) REFERENCES field11_index_manifest(index_id)
            );
            CREATE INDEX IF NOT EXISTS ix_field11_run_source
                ON field11_simulator_run(source_symbol,source_broker_candle,outcome_status);
            CREATE TABLE IF NOT EXISTS field11_simulator_analogue(
                simulator_run_id TEXT NOT NULL,
                analogue_id TEXT NOT NULL,
                match_rank INTEGER,
                inclusion_status TEXT NOT NULL,
                rejection_reason TEXT,
                historical_symbol TEXT,
                historical_broker_candle TEXT,
                overall_similarity REAL,
                final_weight REAL,
                component_json TEXT NOT NULL,
                outcome_json TEXT NOT NULL,
                scenario_cluster TEXT,
                PRIMARY KEY(simulator_run_id,analogue_id),
                FOREIGN KEY(simulator_run_id) REFERENCES field11_simulator_run(simulator_run_id)
            );
            CREATE TABLE IF NOT EXISTS field11_outcome_settlement(
                settlement_key TEXT PRIMARY KEY,
                simulator_run_id TEXT NOT NULL UNIQUE,
                actual_path_json TEXT NOT NULL,
                actual_endpoint_pips REAL,
                actual_mfe_pips REAL,
                actual_mae_pips REAL,
                closest_scenario TEXT,
                path_distance_json TEXT NOT NULL,
                inside_50_band INTEGER,
                inside_80_band INTEGER,
                dominant_scenario_correct INTEGER,
                settled_at_utc TEXT NOT NULL,
                outcome_status TEXT NOT NULL,
                FOREIGN KEY(simulator_run_id) REFERENCES field11_simulator_run(simulator_run_id)
            );
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO field11_schema_migration(version,applied_at_utc,description) VALUES(?,?,?)",
            (SCHEMA_VERSION, pd.Timestamp.now(tz="UTC").isoformat(), "Initial Field 11 historical analogue schemas"),
        )
        conn.commit()
    return {"ok": True, "status": "MIGRATED", "schema_version": SCHEMA_VERSION, "path": str(path)}


def _field10_bundle(path: Path | str = FIELD10_DB_PATH) -> dict[str, Any]:
    from core.field10_daily_snapshot_contract_20260702 import (
        load_current_daily_snapshot, repair_persisted_snapshot_integrity,
        validate_persisted_snapshot,
    )
    bundle = load_current_daily_snapshot(path=path)
    metadata = bundle.get("metadata") or {}
    if metadata:
        broker_day = str(metadata.get("broker_day") or "")
        integrity = validate_persisted_snapshot(broker_day=broker_day, path=path)
        # Recover only hash-representation drift.  Scores/ranks/decisions remain
        # immutable and the repair routine fails closed on real content mismatch.
        if not integrity.get("ok") and integrity.get("status") == "CHECKSUM_FAILED":
            repair = repair_persisted_snapshot_integrity(broker_day=broker_day, path=path)
            if repair.get("ok"):
                bundle = load_current_daily_snapshot(path=path)
                metadata = bundle.get("metadata") or {}
                integrity = validate_persisted_snapshot(broker_day=broker_day, path=path)
            integrity = {**integrity, "repair": repair}
    else:
        integrity = {"ok": False, "status": "NO_FIELD10_SNAPSHOT"}
    bundle["integrity"] = integrity
    return bundle


def resolve_field11_identity(state: Mapping[str, Any], *, field10_path: Path | str = FIELD10_DB_PATH) -> dict[str, Any]:
    """Resolve a stable Field 10 publication identity for all selected symbols.

    A Lunch symbol switch restores a different child canonical generation.  The
    Field 11 index, however, belongs to the one immutable multi-symbol Field 10
    publication.  Therefore child candle differences are warnings, not global
    index failures, while an actual child run/hash mismatch still fails closed.
    """
    from core.canonical_lookup_20260626 import resolve_canonical
    canonical = resolve_canonical(state)
    field10 = _field10_bundle(field10_path)
    metadata = field10.get("metadata") or {}
    current = field10.get("current") if isinstance(field10.get("current"), pd.DataFrame) else pd.DataFrame()
    canonical_run_id = str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or "")
    canonical_snapshot_hash = str(canonical.get("snapshot_hash") or canonical.get("source_snapshot_hash") or "")
    canonical_symbol = normalize_symbol(canonical.get("symbol") or state.get("lunch_display_symbol_20260702") or state.get("symbol") or "EURUSD")
    canonical_candle = pd.to_datetime(
        canonical.get("latest_completed_candle_time") or canonical.get("completed_broker_candle") or canonical.get("broker_candle_time"),
        errors="coerce", utc=True,
    )
    f10_ids = metadata.get("canonical_run_ids") if isinstance(metadata.get("canonical_run_ids"), Mapping) else {}
    f10_hashes = metadata.get("snapshot_hashes") if isinstance(metadata.get("snapshot_hashes"), Mapping) else {}
    locked_universe = metadata.get("ordered_symbol_universe")
    if not isinstance(locked_universe, list):
        locked_universe = current.get("Symbol", pd.Series(dtype=str)).dropna().astype(str).tolist() if not current.empty else []
    # Include every selected/completed runtime child in the prepared analogue
    # index, even when today's immutable morning rank was published earlier with
    # a smaller universe.  This does not rerank or alter the locked Field 10 table.
    runtime_selected = state.get("multi_symbol_selected_20260701")
    if not isinstance(runtime_selected, (list, tuple, set)):
        runtime_selected = []
    manifest = state.get("multi_symbol_manifest_20260701") if isinstance(state.get("multi_symbol_manifest_20260701"), Mapping) else {}
    manifest_selected = manifest.get("selected_symbols") if isinstance(manifest.get("selected_symbols"), list) else []
    ordered_universe: list[str] = []
    for value in [*locked_universe, *runtime_selected, *manifest_selected, canonical_symbol]:
        symbol = normalize_symbol(value)
        if symbol and symbol not in ordered_universe:
            ordered_universe.append(symbol)
    latest_completed = pd.to_datetime(metadata.get("latest_completed_h1"), errors="coerce", utc=True)
    errors: list[str] = []
    warnings: list[str] = []
    cache_ready = available_saved_symbols(ordered_universe)
    cache_fallback = not metadata and bool(canonical) and bool(cache_ready)
    if not canonical:
        errors.append("canonical run is unavailable")
    if not metadata and not cache_fallback:
        errors.append("Field 10 daily snapshot is unavailable")
    integrity_ok = bool((field10.get("integrity") or {}).get("ok"))
    if metadata and not integrity_ok:
        errors.append(f"Field 10 snapshot checksum is invalid: {(field10.get('integrity') or {}).get('status')}")
    if cache_fallback:
        warnings.append("Field 11 identity was repaired from readable symbol runtime caches because the optional Field 10 daily publication was unavailable.")
        ordered_universe = normalize_selected([*cache_ready, canonical_symbol])
        if pd.isna(latest_completed):
            latest_completed = canonical_candle
        parent_fallback = str(manifest.get("parent_run_id") or state.get("multi_symbol_parent_run_id_20260701") or canonical_run_id or "CACHE")
        fallback_seed = {
            "parent_run_id": parent_fallback, "symbols": ordered_universe,
            "source_candle": None if pd.isna(latest_completed) else pd.Timestamp(latest_completed).isoformat(),
            "active_hash": canonical_snapshot_hash,
        }
        fallback_hash = deterministic_hash(fallback_seed)
        metadata = {
            "parent_run_id": parent_fallback,
            "daily_snapshot_id": f"F11CACHE-{fallback_hash[:20]}",
            "content_hash": fallback_hash,
            "broker_day": (pd.Timestamp(latest_completed).strftime("%Y-%m-%d") if pd.notna(latest_completed) else ""),
            "latest_completed_h1": (pd.Timestamp(latest_completed).isoformat() if pd.notna(latest_completed) else ""),
            "ordered_symbol_universe": ordered_universe,
            "canonical_run_ids": {}, "snapshot_hashes": {},
        }
        f10_ids = {}; f10_hashes = {}; locked_universe = ordered_universe
    if pd.notna(canonical_candle) and pd.notna(latest_completed) and pd.Timestamp(canonical_candle) != pd.Timestamp(latest_completed):
        warnings.append(
            f"child source candle differs from the Field 10 publication cutoff: "
            f"{canonical_symbol}={canonical_candle.isoformat()} field10={latest_completed.isoformat()}"
        )
    expected_id = str(f10_ids.get(canonical_symbol) or "")
    expected_hash = str(f10_hashes.get(canonical_symbol) or "")
    if expected_id and canonical_run_id and canonical_run_id != expected_id:
        warnings.append(
            f"{canonical_symbol} active child run differs from the locked Field 10 publication; "
            "the simulator remains bound to the immutable parent snapshot"
        )
    elif canonical_run_id and not expected_id:
        warnings.append(f"{canonical_symbol} is not part of the locked morning rank universe; analogue index remains available without reranking")
    if expected_hash and canonical_snapshot_hash and canonical_snapshot_hash != expected_hash:
        warnings.append(
            f"{canonical_symbol} active child hash differs from the locked Field 10 publication; "
            "the immutable parent hash is used for Field 11"
        )
    parent_run_id = str(metadata.get("parent_run_id") or manifest.get("parent_run_id") or "")
    stable_identity = parent_run_id or str(metadata.get("daily_snapshot_id") or canonical_run_id)
    return {
        "ok": not errors,
        "status": ("CACHE_REPAIRED" if cache_fallback and not errors else ("VALID" if not errors else "IDENTITY_MISMATCH")),
        "errors": errors,
        "warnings": warnings,
        "canonical_run_id": stable_identity,
        "active_child_run_id": canonical_run_id,
        "active_child_snapshot_hash": canonical_snapshot_hash,
        "snapshot_hash": str(metadata.get("content_hash") or canonical_snapshot_hash),
        "field10_daily_rank_id": str(metadata.get("daily_snapshot_id") or ""),
        "broker_date": str(metadata.get("broker_day") or ""),
        "source_candle_time": pd.Timestamp(latest_completed).isoformat() if pd.notna(latest_completed) else "",
        "active_child_candle_time": pd.Timestamp(canonical_candle).isoformat() if pd.notna(canonical_candle) else "",
        "parent_run_id": parent_run_id,
        "symbol_universe": ordered_universe,
        "locked_rank_universe": [normalize_symbol(value) for value in locked_universe],
        "timeframe": str(canonical.get("timeframe") or "H1").upper(),
        "field10_current": current,
    }


def _runtime_cache_state(symbol: str) -> Mapping[str, Any]:
    path = CACHE_DIR / f"{normalize_symbol(symbol)}.pkl.gz"
    if not path.is_file():
        return {}
    try:
        payload = serializer_loads(gzip.decompress(path.read_bytes()))
        state = payload.get("state") if isinstance(payload, Mapping) else None
        return state if isinstance(state, Mapping) else {}
    except Exception:
        return {}


def _is_ohlc_frame(value: Any) -> bool:
    if not isinstance(value, pd.DataFrame) or value.empty:
        return False
    lower = {str(column).strip().lower() for column in value.columns}
    return {"open", "high", "low", "close"}.issubset(lower) and any(
        name in lower for name in ("time", "timestamp", "datetime", "date", "broker timestamp", "broker candle time")
    )


def _find_ohlc_frame(value: Any, *, max_depth: int = 6) -> pd.DataFrame:
    """Find the largest completed-candle OHLC frame in a saved generation."""
    best = pd.DataFrame()
    seen: set[int] = set()

    def walk(item: Any, depth: int) -> None:
        nonlocal best
        if depth > max_depth or id(item) in seen:
            return
        seen.add(id(item))
        if _is_ohlc_frame(item):
            if len(item) > len(best):
                best = item
            return
        if isinstance(item, Mapping):
            preferred = (
                "ohlc", "data", "historical_data", "market_data", "raw_data", "price_data",
                "df", "frame", "candles", "h1_data", "source_frame",
            )
            for key in preferred:
                if key in item:
                    walk(item[key], depth + 1)
            for child in item.values():
                if isinstance(child, (Mapping, list, tuple, pd.DataFrame)):
                    walk(child, depth + 1)
        elif isinstance(item, (list, tuple)):
            for child in item[:100]:
                walk(child, depth + 1)

    walk(value, 0)
    return best.copy() if not best.empty else best


def _normalize_ohlc(frame: pd.DataFrame, *, symbol: str, latest_completed: Any) -> pd.DataFrame:
    if frame.empty:
        return frame
    aliases = {str(column).strip().lower(): column for column in frame.columns}
    time_col = next((aliases[name] for name in ("time", "timestamp", "datetime", "broker timestamp", "broker candle time", "date") if name in aliases), None)
    if time_col is None:
        return pd.DataFrame()
    columns = {name: aliases.get(name) for name in ("open", "high", "low", "close", "volume", "tick_volume")}
    if not all(columns[name] is not None for name in ("open", "high", "low", "close")):
        return pd.DataFrame()
    out = pd.DataFrame({
        "time": pd.to_datetime(frame[time_col], errors="coerce", utc=True),
        "open": pd.to_numeric(frame[columns["open"]], errors="coerce"),
        "high": pd.to_numeric(frame[columns["high"]], errors="coerce"),
        "low": pd.to_numeric(frame[columns["low"]], errors="coerce"),
        "close": pd.to_numeric(frame[columns["close"]], errors="coerce"),
    })
    volume_col = columns.get("volume") or columns.get("tick_volume")
    out["volume"] = pd.to_numeric(frame[volume_col], errors="coerce") if volume_col else np.nan
    cutoff = pd.to_datetime(latest_completed, errors="coerce", utc=True)
    out = out.dropna(subset=["time", "open", "high", "low", "close"])
    if pd.notna(cutoff):
        out = out.loc[out["time"] <= pd.Timestamp(cutoff)]
    out = out.sort_values("time", kind="mergesort").drop_duplicates("time", keep="last")
    out["symbol"] = normalize_symbol(symbol)
    return out.reset_index(drop=True)


def _infer_timeframe(frame: pd.DataFrame) -> str:
    """Infer the canonical timeframe without relabelling one interval as another."""
    if len(frame) < 3:
        return "H1"
    deltas = frame["time"].diff().dropna().dt.total_seconds().div(60)
    positive = deltas[deltas > 0]
    minutes = float(positive.median()) if not positive.empty else 60.0
    if minutes <= 1.5:
        return "M1"
    if minutes <= 16:
        return "M15"
    if minutes <= 31:
        return "M30"
    if minutes <= 75:
        return "H1"
    if minutes <= 300:
        return "H4"
    if minutes <= 1800:
        return "D1"
    return f"M{int(round(minutes))}"


def _resample_ohlc(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Timeframe-safe completed-candle OHLCV resampling."""
    timeframe = str(timeframe or "").upper()
    rule = {
        "M1": "1min", "M15": "15min", "M30": "30min",
        "H1": "1h", "H4": "4h", "D1": "1D",
    }.get(timeframe)
    if rule is None or frame.empty:
        return pd.DataFrame()
    source = frame.copy()
    source["time"] = pd.to_datetime(source["time"], errors="coerce", utc=True)
    source = source.dropna(subset=["time"]).sort_values("time", kind="mergesort").set_index("time")
    aggregations = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in source.columns:
        aggregations["volume"] = "sum"
    if "spread" in source.columns:
        aggregations["spread"] = "mean"
    if "symbol" in source.columns:
        aggregations["symbol"] = "last"
    out = source.resample(rule, label="left", closed="left").agg(aggregations)
    out = out.dropna(subset=["open", "high", "low", "close"])
    return out.reset_index()


def _session(hour: int) -> str:
    if 0 <= hour < 7:
        return "TOKYO_SYDNEY"
    if 7 <= hour < 12:
        return "LONDON"
    if 12 <= hour < 16:
        return "LONDON_NEW_YORK_OVERLAP"
    if 16 <= hour < 21:
        return "NEW_YORK"
    return "AFTER_HOURS"


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).rolling(period, min_periods=period).mean()
    rs = gain.div(loss.replace(0, np.nan))
    return 100 - (100 / (1 + rs))


def _feature_frame(ohlc: pd.DataFrame, *, timeframe: str) -> pd.DataFrame:
    if ohlc.empty:
        return pd.DataFrame()
    frame = ohlc.copy()
    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    returns = close.pct_change()
    for lag in (1, 2, 3, 6, 12, 24):
        frame[f"return_{lag}"] = close.pct_change(lag)
    candle_range = (high - low).replace(0, np.nan)
    frame["body_ratio"] = (close - open_).abs().div(candle_range)
    frame["upper_wick_ratio"] = (high - np.maximum(open_, close)).div(candle_range)
    frame["lower_wick_ratio"] = (np.minimum(open_, close) - low).div(candle_range)
    frame["gap_ratio"] = open_.div(close.shift(1)).sub(1)
    rolling_high = high.rolling(24, min_periods=6).max()
    rolling_low = low.rolling(24, min_periods=6).min()
    frame["distance_rolling_high"] = close.div(rolling_high).sub(1)
    frame["distance_rolling_low"] = close.div(rolling_low).sub(1)
    frame["breakout_distance"] = np.maximum(frame["distance_rolling_high"], -frame["distance_rolling_low"])
    frame["pullback_depth"] = (rolling_high - close).div((rolling_high - rolling_low).replace(0, np.nan))
    frame["momentum"] = frame["return_6"]
    frame["momentum_acceleration"] = frame["return_3"] - frame["return_6"].shift(3)
    frame["mean_reversion_pressure"] = close.div(close.rolling(20, min_periods=5).mean()).sub(1)
    frame["path_curvature"] = returns.diff().diff().rolling(3, min_periods=2).mean()
    direction = np.sign(returns)
    frame["directional_persistence"] = direction.rolling(12, min_periods=4).mean().abs()
    frame["rsi"] = _rsi(close)
    frame["rsi_slope"] = frame["rsi"].diff(3)
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=9, adjust=False).mean()
    frame["macd"] = macd.div(close.replace(0, np.nan))
    frame["macd_histogram"] = (macd - signal).div(close.replace(0, np.nan))
    frame["macd_slope"] = frame["macd"].diff(3)
    frame["ema_order"] = np.sign(ema_fast - ema_slow)
    frame["ema_slope_fast"] = ema_fast.pct_change(3)
    frame["ema_slope_slow"] = ema_slow.pct_change(3)
    frame["price_to_ema_fast"] = close.div(ema_fast).sub(1)
    frame["price_to_ema_slow"] = close.div(ema_slow).sub(1)
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=5).mean()
    frame["atr"] = atr.div(close.replace(0, np.nan))
    frame["atr_percentile"] = atr.rolling(100, min_periods=20).rank(pct=True) * 100
    frame["realized_volatility"] = returns.rolling(24, min_periods=6).std()
    frame["downside_volatility"] = returns.where(returns < 0).rolling(24, min_periods=6).std()
    frame["volatility_of_volatility"] = frame["realized_volatility"].rolling(24, min_periods=6).std()
    mid = close.rolling(20, min_periods=5).mean()
    std = close.rolling(20, min_periods=5).std()
    frame["bollinger_width"] = (4 * std).div(mid.replace(0, np.nan))
    frame["compression_score"] = 1 - frame["atr_percentile"].div(100)
    frame["expansion_score"] = frame["atr_percentile"].div(100)
    frame["support_distance"] = close.div(rolling_low).sub(1)
    frame["resistance_distance"] = rolling_high.div(close).sub(1)
    hour = frame["time"].dt.hour.astype(float)
    weekday = frame["time"].dt.weekday.astype(float)
    frame["broker_hour"] = hour.astype("int16")
    frame["weekday"] = weekday.astype("int8")
    frame["session"] = frame["broker_hour"].map(_session).astype("category")
    frame["broker_hour_sin"] = np.sin(2 * np.pi * hour / 24)
    frame["broker_hour_cos"] = np.cos(2 * np.pi * hour / 24)
    frame["weekday_sin"] = np.sin(2 * np.pi * weekday / 7)
    frame["weekday_cos"] = np.cos(2 * np.pi * weekday / 7)
    for offset in range(1, SHAPE_BARS + 1):
        frame[f"shape_return_{offset}"] = returns.shift(SHAPE_BARS - offset)
    frame["timeframe"] = timeframe
    frame["feature_coverage"] = frame[FEATURE_COLUMNS].notna().mean(axis=1) * 100
    keep = ["symbol", "timeframe", "time", "open", "high", "low", "close", "volume", "broker_hour", "weekday", "session", "feature_coverage", *FEATURE_COLUMNS, *SHAPE_COLUMNS]
    frame = frame[keep]
    numeric = [column for column in frame.columns if column not in {"symbol", "timeframe", "time", "session"}]
    frame[numeric] = frame[numeric].astype("float32")
    return frame.reset_index(drop=True)


def _write_frame(frame: pd.DataFrame, path: Path) -> Path:
    """Prefer Parquet; use a compressed pickle only when no Parquet engine exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        frame.to_parquet(path, index=False, compression="zstd")
        return path
    except (ImportError, ModuleNotFoundError):
        fallback = path.with_suffix(".pkl.gz")
        frame.to_pickle(fallback, compression="gzip")
        return fallback


def read_index_frame(path: Path | str, columns: Sequence[str] | None = None) -> pd.DataFrame:
    target = Path(path)
    if target.suffix == ".parquet":
        frame = pd.read_parquet(target, columns=list(columns) if columns else None)
    else:
        frame = pd.read_pickle(target, compression="gzip")
        if columns:
            frame = frame[[column for column in columns if column in frame.columns]]
    return frame


def prepare_field11_index(
    state: MutableMapping[str, Any], *, parent_run_id: str, symbols: Sequence[str],
    path: Path | str = DB_PATH, field10_path: Path | str = FIELD10_DB_PATH,
) -> dict[str, Any]:
    """Prepare immutable historical feature artifacts during the existing run."""
    migrate_field11_database(path)
    identity = resolve_field11_identity(state, field10_path=field10_path)
    if not identity.get("ok"):
        return {"ok": False, "status": "IDENTITY_MISMATCH", "errors": identity.get("errors", [])}
    latest_completed = identity["source_candle_time"]
    requested_universe = [normalize_symbol(symbol) for symbol in symbols]
    universe = []
    for symbol in [*requested_universe, *identity.get("symbol_universe", [])]:
        symbol = normalize_symbol(symbol)
        if symbol and symbol not in universe:
            universe.append(symbol)
    if not universe:
        return {"ok": False, "status": "NO_CANONICAL_SYMBOLS"}
    feature_parts: list[pd.DataFrame] = []
    ohlc_parts: list[pd.DataFrame] = []
    symbol_reports: list[dict[str, Any]] = []
    supported: set[str] = set()
    for symbol in universe:
        cached_state = _runtime_cache_state(symbol)
        raw = _find_ohlc_frame(cached_state)
        if raw.empty and symbol == normalize_symbol(state.get("symbol") or symbol):
            raw = _find_ohlc_frame(state)
        normalized = _normalize_ohlc(raw, symbol=symbol, latest_completed=latest_completed)
        if normalized.empty or len(normalized) < 40:
            symbol_reports.append({"symbol": symbol, "status": "INSUFFICIENT_HISTORY", "rows": len(normalized)})
            continue
        base_timeframe = _infer_timeframe(normalized)
        candidate_timeframes: list[str] = [base_timeframe]
        if base_timeframe == "M1":
            candidate_timeframes.extend(["H1", "H4", "D1"])
        elif base_timeframe in {"M15", "M30"}:
            candidate_timeframes.extend(["H1", "H4", "D1"])
        elif base_timeframe == "H1":
            candidate_timeframes.extend(["H4", "D1"])
        elif base_timeframe == "H4":
            candidate_timeframes.append("D1")
        indexed_timeframes: list[str] = []
        for timeframe in dict.fromkeys(candidate_timeframes):
            tf_ohlc = normalized if timeframe == base_timeframe else _resample_ohlc(normalized, timeframe)
            minimum_rows = 20 if timeframe == "D1" else (25 if timeframe == "H4" else 40)
            if len(tf_ohlc) < minimum_rows:
                continue
            tf_ohlc = tf_ohlc.copy()
            tf_ohlc["timeframe"] = timeframe
            features = _feature_frame(tf_ohlc, timeframe=timeframe)
            if features.empty:
                continue
            feature_parts.append(features)
            ohlc_parts.append(tf_ohlc[["symbol", "timeframe", "time", "open", "high", "low", "close", "volume"]])
            supported.add(timeframe)
            indexed_timeframes.append(timeframe)
        if indexed_timeframes:
            symbol_reports.append({
                "symbol": symbol, "status": "INDEXED", "rows": len(normalized),
                "base_timeframe": base_timeframe, "indexed_timeframes": indexed_timeframes,
            })
        else:
            symbol_reports.append({
                "symbol": symbol, "status": "NO_SUPPORTED_TIMEFRAME", "rows": len(normalized),
                "base_timeframe": base_timeframe,
            })
    if not feature_parts or not ohlc_parts:
        return {"ok": False, "status": "NO_VALID_HISTORICAL_INDEX", "symbol_reports": symbol_reports}
    features = pd.concat(feature_parts, ignore_index=True)
    ohlc = pd.concat(ohlc_parts, ignore_index=True)
    features = features.sort_values(["symbol", "timeframe", "time"], kind="mergesort").drop_duplicates(["symbol", "timeframe", "time"], keep="last")
    ohlc = ohlc.sort_values(["symbol", "timeframe", "time"], kind="mergesort").drop_duplicates(["symbol", "timeframe", "time"], keep="last")
    indexed_universe = list(dict.fromkeys(features["symbol"].astype(str).tolist()))
    index_payload = {
        "canonical_run_id": identity["canonical_run_id"], "snapshot_hash": identity["snapshot_hash"],
        "field10_daily_rank_id": identity["field10_daily_rank_id"], "broker_date": identity["broker_date"],
        "source_candle_time": identity["source_candle_time"], "parent_run_id": parent_run_id,
        "symbol_universe": indexed_universe, "supported_timeframes": sorted(supported),
        "feature_version": FEATURE_VERSION, "index_version": INDEX_VERSION,
    }
    index_id = f"F11IDX-{deterministic_hash(index_payload)[:28]}"
    target_dir = ARTIFACT_DIR / index_id
    feature_path = target_dir / "features.parquet"
    ohlc_path = target_dir / "ohlc.parquet"
    scaler_path = target_dir / "robust_scaler.joblib"
    feature_path = _write_frame(features, feature_path)
    ohlc_path = _write_frame(ohlc, ohlc_path)
    fit_frame = features[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan)
    medians = fit_frame.median(numeric_only=True).fillna(0.0)
    scaler = RobustScaler(quantile_range=(10, 90)).fit(fit_frame.fillna(medians).to_numpy(dtype=float))
    joblib.dump({"scaler": scaler, "medians": medians.to_dict(), "feature_columns": FEATURE_COLUMNS}, scaler_path, compress=3)
    content_hash = deterministic_hash({
        "identity": index_payload,
        "feature_rows": len(features), "ohlc_rows": len(ohlc),
        "feature_tail": features[["symbol", "timeframe", "time", "close"]].tail(20).to_dict("records"),
    })
    now = pd.Timestamp.now(tz="UTC").isoformat()
    metadata = {"symbol_reports": symbol_reports, "completed_candles_only": True, "no_lookahead_features": True}
    with _connect(path) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO field11_index_manifest(
                index_id,canonical_run_id,field10_daily_rank_id,snapshot_hash,broker_date,source_candle_time,
                parent_run_id,symbol_universe_json,supported_timeframes_json,feature_version,index_version,
                feature_path,ohlc_path,scaler_path,row_count,symbol_count,content_hash,status,created_at_utc,metadata_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (index_id, identity["canonical_run_id"], identity["field10_daily_rank_id"], identity["snapshot_hash"],
             identity["broker_date"], identity["source_candle_time"], parent_run_id, _canonical_json(indexed_universe),
             _canonical_json(sorted(supported)), FEATURE_VERSION, INDEX_VERSION, str(feature_path), str(ohlc_path),
             str(scaler_path), len(features), len(indexed_universe), content_hash, "READY", now, _canonical_json(metadata)),
        )
        conn.commit()
    return {
        "ok": True, "status": "READY", "index_id": index_id, "row_count": len(features),
        "symbol_count": len(indexed_universe), "supported_timeframes": sorted(supported), "content_hash": content_hash,
        "symbol_reports": symbol_reports,
    }


def load_index_manifest(*, identity: Mapping[str, Any] | None = None, path: Path | str = DB_PATH) -> dict[str, Any]:
    """Read a prepared manifest without mutating schema or data."""
    clauses = ["status='READY'"]
    params: list[Any] = []
    if identity:
        for column, key in (("canonical_run_id", "canonical_run_id"), ("snapshot_hash", "snapshot_hash"), ("field10_daily_rank_id", "field10_daily_rank_id")):
            if identity.get(key):
                clauses.append(f"{column}=?")
                params.append(str(identity[key]))
    query = f"SELECT * FROM field11_index_manifest WHERE {' AND '.join(clauses)} ORDER BY created_at_utc DESC LIMIT 1"
    with connect_readonly(path, row_factory=sqlite3.Row) as conn:
        row = conn.execute(query, params).fetchone()
    if row is None:
        return {}
    result = dict(row)
    for key in ("symbol_universe_json", "supported_timeframes_json", "metadata_json"):
        try:
            result[key.removesuffix("_json")] = json.loads(result.get(key) or "[]")
        except Exception:
            result[key.removesuffix("_json")] = [] if key != "metadata_json" else {}
    return result


def validate_index_identity(identity: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not identity.get("ok"):
        errors.extend(identity.get("errors") or ["canonical identity invalid"])
    if not manifest:
        errors.append("prepared historical index is unavailable")
    for identity_key, manifest_key in (
        ("canonical_run_id", "canonical_run_id"), ("snapshot_hash", "snapshot_hash"),
        ("field10_daily_rank_id", "field10_daily_rank_id"), ("source_candle_time", "source_candle_time"),
    ):
        if identity.get(identity_key) and manifest.get(manifest_key) and str(identity[identity_key]) != str(manifest[manifest_key]):
            errors.append(f"{identity_key} mismatch")
    for key in ("feature_path", "ohlc_path", "scaler_path"):
        if manifest and not Path(str(manifest.get(key) or "")).is_file():
            errors.append(f"index artifact missing: {key}")
    return {"ok": not errors, "status": "VALID" if not errors else "STALE_OR_MISMATCHED_INDEX", "errors": errors}


def pip_size(symbol: str) -> float:
    symbol = normalize_symbol(symbol)
    if symbol in {"XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD"}:
        return 0.01
    if symbol.endswith("JPY") and len(symbol) == 6:
        return 0.01
    if len(symbol) == 6 and symbol.isalpha():
        return 0.0001
    return 0.01


def rebase_path(historical_prices: Sequence[float], historical_start: float, current_start: float) -> np.ndarray:
    values = np.asarray(historical_prices, dtype=float)
    if not math.isfinite(historical_start) or historical_start == 0 or not math.isfinite(current_start):
        return np.full(len(values), np.nan)
    return current_start * (values / historical_start)


def constrained_dtw_distance(a: Sequence[float], b: Sequence[float], *, window: int | None = None) -> float:
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    if len(x) == 0 or len(y) == 0 or np.isnan(x).any() or np.isnan(y).any():
        return float("inf")
    window = max(abs(len(x) - len(y)), int(window if window is not None else max(1, len(x) // 6)))
    previous = np.full(len(y) + 1, np.inf)
    previous[0] = 0.0
    for i in range(1, len(x) + 1):
        current = np.full(len(y) + 1, np.inf)
        start = max(1, i - window)
        end = min(len(y), i + window)
        for j in range(start, end + 1):
            cost = abs(x[i - 1] - y[j - 1])
            current[j] = cost + min(current[j - 1], previous[j], previous[j - 1])
        previous = current
    return float(previous[len(y)] / max(len(x), len(y)))


def effective_sample_size(weights: Sequence[float]) -> float:
    values = np.asarray(weights, dtype=float)
    total = values.sum()
    if total <= 0:
        return 0.0
    values = values / total
    denominator = float(np.square(values).sum())
    return float(1.0 / denominator) if denominator > 0 else 0.0


def _z_normalize(values: Sequence[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    std = float(np.nanstd(array))
    if not math.isfinite(std) or std <= 1e-12:
        return np.zeros_like(array)
    return (array - float(np.nanmean(array))) / std


def _similarity_from_distance(distance: float, scale: float = 1.0) -> float:
    if not math.isfinite(distance):
        return 0.0
    return float(np.clip(100.0 * math.exp(-max(0.0, distance) / max(scale, 1e-9)), 0.0, 100.0))


def _component_scores(source: pd.Series, candidate: pd.Series, scaled_distance: float) -> dict[str, float]:
    source_shape = source[SHAPE_COLUMNS].to_numpy(dtype=float)
    candidate_shape = candidate[SHAPE_COLUMNS].to_numpy(dtype=float)
    z_a, z_b = _z_normalize(source_shape), _z_normalize(candidate_shape)
    euclidean = float(np.linalg.norm(z_a - z_b) / math.sqrt(max(1, len(z_a))))
    dtw = constrained_dtw_distance(z_a, z_b, window=max(1, SHAPE_BARS // 4))
    correlation = float(np.corrcoef(z_a, z_b)[0, 1]) if np.std(z_a) > 0 and np.std(z_b) > 0 else 0.0
    direction_agreement = float(np.mean(np.sign(source_shape) == np.sign(candidate_shape)))
    shape = np.mean([
        _similarity_from_distance(euclidean, 1.0), _similarity_from_distance(dtw, 1.0),
        50 * (correlation + 1), 100 * direction_agreement,
    ])
    technical = _similarity_from_distance(float(scaled_distance), 2.5)
    regime = 50.0  # historical regime archive may be unavailable; never fabricated
    session = 100.0 if str(source.get("session")) == str(candidate.get("session")) else max(0.0, 100.0 - 12.5 * abs(int(source.get("broker_hour", 0)) - int(candidate.get("broker_hour", 0))))
    vol_values = ["atr_percentile", "realized_volatility", "volatility_of_volatility", "bollinger_width"]
    vol_distance = float(np.nanmean(np.abs(source[vol_values].to_numpy(dtype=float) - candidate[vol_values].to_numpy(dtype=float))))
    volatility = _similarity_from_distance(vol_distance, 0.25)
    sentiment = 50.0
    liquidity = 50.0
    cross_market = 50.0
    hybrid = (
        0.25 * shape + 0.20 * technical + 0.15 * regime + 0.10 * session + 0.10 * volatility
        + 0.10 * sentiment + 0.05 * liquidity + 0.05 * cross_market
    )
    return {
        "shape_similarity": round(float(shape), 4), "technical_similarity": round(float(technical), 4),
        "regime_similarity": regime, "session_similarity": round(float(session), 4),
        "volatility_similarity": round(float(volatility), 4), "sentiment_similarity": sentiment,
        "liquidity_similarity": liquidity, "cross_market_similarity": cross_market,
        "hybrid_similarity": round(float(hybrid), 4), "dtw_distance": round(float(dtw), 8),
        "z_euclidean_distance": round(float(euclidean), 8), "direction_sequence_agreement": round(100 * direction_agreement, 4),
    }


def _hours_per_bar(timeframe: str) -> float:
    return {"M15": 0.25, "M30": 0.5, "H1": 1.0, "H4": 4.0}.get(timeframe, 1.0)


def _bars_for_horizon(timeframe: str, hours: int) -> int:
    return max(1, int(math.ceil(hours / _hours_per_bar(timeframe))))


def _candidate_symbols(selection: Field11Selection, universe: Sequence[str]) -> list[str]:
    if selection.historical_source.lower().startswith("same symbol"):
        return [selection.symbol]
    if selection.historical_source.lower().startswith("compatible"):
        # Conservative compatibility: same quote/base USD family or same asset class.
        if len(selection.symbol) == 6 and selection.symbol.isalpha():
            return [symbol for symbol in universe if len(symbol) == 6 and symbol.isalpha() and ("USD" in symbol) == ("USD" in selection.symbol)]
        return [symbol for symbol in universe if (len(symbol) == 6 and symbol.isalpha()) == (len(selection.symbol) == 6 and selection.symbol.isalpha())]
    return list(universe)


def _selection_hash(index_id: str, selection: Field11Selection) -> str:
    return deterministic_hash({"index_id": index_id, "selection": asdict(selection.normalized()), "simulator_version": SIMULATOR_VERSION})


def _load_cached_run(selection_hash: str, path: Path | str) -> dict[str, Any] | None:
    with _connect(path) as conn:
        row = conn.execute("SELECT * FROM field11_simulator_run WHERE selection_hash=?", (selection_hash,)).fetchone()
        if row is None:
            return None
        analogues = pd.read_sql_query(
            "SELECT * FROM field11_simulator_analogue WHERE simulator_run_id=? ORDER BY inclusion_status DESC,match_rank",
            conn, params=(row["simulator_run_id"],),
        )
    payload = dict(row)
    payload["summary"] = json.loads(payload.pop("summary_json"))
    payload["scenarios"] = json.loads(payload.pop("scenarios_json"))
    if not analogues.empty:
        analogues["component_json"] = analogues["component_json"].map(lambda value: json.loads(value or "{}"))
        analogues["outcome_json"] = analogues["outcome_json"].map(lambda value: json.loads(value or "{}"))
    payload["analogue_records"] = analogues
    payload["cached"] = True
    return payload


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    order = np.argsort(values)
    values, weights = values[order], weights[order]
    cumulative = np.cumsum(weights)
    if cumulative[-1] <= 0:
        return float(np.nan)
    cumulative = cumulative / cumulative[-1]
    return float(np.interp(quantile, cumulative, values))


def _scenario_name(path_pips: np.ndarray) -> str:
    endpoint = float(path_pips[-1])
    peak = float(np.nanmax(path_pips))
    trough = float(np.nanmin(path_pips))
    changes = int(np.sum(np.sign(np.diff(path_pips))[1:] != np.sign(np.diff(path_pips))[:-1])) if len(path_pips) > 2 else 0
    if endpoint > 0 and trough < -abs(endpoint) * 0.6:
        return "bearish-then-reversal"
    if endpoint < 0 and peak > abs(endpoint) * 0.6:
        return "bullish-then-reversal"
    if abs(endpoint) <= max(1e-9, 0.25 * max(abs(peak), abs(trough), 1e-9)):
        return "sideways or compression"
    if endpoint > 0:
        return "bullish continuation" if changes <= 2 else "bullish volatile continuation"
    return "bearish continuation" if changes <= 2 else "bearish volatile continuation"


def _cluster_scenarios(paths: np.ndarray, weights: np.ndarray, scenario_count: int, endpoint_pips: np.ndarray) -> tuple[np.ndarray, list[dict[str, Any]]]:
    if len(paths) == 1:
        labels = np.array([0], dtype=int)
    else:
        clusters = max(1, min(scenario_count, len(paths)))
        labels = KMeans(n_clusters=clusters, random_state=11, n_init=10).fit_predict(paths)
    scenarios: list[dict[str, Any]] = []
    for label in sorted(set(labels.tolist())):
        mask = labels == label
        cluster_paths = paths[mask]
        cluster_weights = weights[mask]
        cluster_weights = cluster_weights / cluster_weights.sum() if cluster_weights.sum() > 0 else np.full(mask.sum(), 1 / mask.sum())
        weighted_median = np.array([_weighted_quantile(cluster_paths[:, step], cluster_weights, 0.5) for step in range(cluster_paths.shape[1])])
        distances = np.linalg.norm(cluster_paths - weighted_median, axis=1)
        medoid_local = int(np.argmin(distances))
        cluster_end = endpoint_pips[mask]
        scenario = {
            "cluster_id": int(label), "scenario_name": _scenario_name(weighted_median),
            "supporting_analogue_count": int(mask.sum()), "supporting_effective_sample_size": round(effective_sample_size(cluster_weights), 4),
            "total_analogue_weight": round(float(weights[mask].sum()), 6),
            "weighted_historical_frequency": round(float(100 * weights[mask].sum()), 4),
            "median_endpoint_pips": round(_weighted_quantile(cluster_end, cluster_weights, 0.5), 4),
            "endpoint_p10": round(_weighted_quantile(cluster_end, cluster_weights, 0.10), 4),
            "endpoint_p25": round(_weighted_quantile(cluster_end, cluster_weights, 0.25), 4),
            "endpoint_p75": round(_weighted_quantile(cluster_end, cluster_weights, 0.75), 4),
            "endpoint_p90": round(_weighted_quantile(cluster_end, cluster_weights, 0.90), 4),
            "median_path_pips": weighted_median.tolist(), "medoid_path_pips": cluster_paths[medoid_local].tolist(),
            "scenario_stability": None, "bias_switch_frequency": None, "regime_switch_frequency": None,
        }
        scenarios.append(scenario)
    scenarios.sort(key=lambda item: (-item["total_analogue_weight"], item["scenario_name"]))
    return labels, scenarios


def _bootstrap_stability(paths: np.ndarray, weights: np.ndarray, scenarios: list[dict[str, Any]], *, iterations: int = 100, seed: int = 11) -> dict[str, Any]:
    if len(paths) < 3 or not scenarios:
        return {"dominant_scenario_stability": 0.0, "direction_stability": 0.0, "remove_top_match_sensitivity": 100.0, "status": "INSUFFICIENT"}
    rng = np.random.default_rng(seed)
    dominant_name = scenarios[0]["scenario_name"]
    dominant_hits = 0
    direction_hits = 0
    baseline_direction = np.sign(np.average(paths[:, -1], weights=weights))
    probabilities = weights / weights.sum()
    endpoints: list[float] = []
    for _ in range(iterations):
        sample = rng.choice(len(paths), size=len(paths), replace=True, p=probabilities)
        sampled_paths = paths[sample]
        sampled_weights = weights[sample]
        sampled_weights = sampled_weights / sampled_weights.sum()
        median_path = np.array([_weighted_quantile(sampled_paths[:, step], sampled_weights, 0.5) for step in range(paths.shape[1])])
        dominant_hits += int(_scenario_name(median_path) == dominant_name)
        direction_hits += int(np.sign(median_path[-1]) == baseline_direction)
        endpoints.append(float(median_path[-1]))
    without_top = np.delete(paths, int(np.argmax(weights)), axis=0)
    without_weights = np.delete(weights, int(np.argmax(weights)))
    without_weights = without_weights / without_weights.sum()
    baseline = np.average(paths[:, -1], weights=weights)
    leave_one = np.average(without_top[:, -1], weights=without_weights)
    sensitivity = abs(leave_one - baseline) / max(abs(baseline), 1e-6) * 100
    return {
        "dominant_scenario_stability": round(100 * dominant_hits / iterations, 4),
        "direction_stability": round(100 * direction_hits / iterations, 4),
        "median_endpoint_bootstrap_std": round(float(np.std(endpoints)), 6),
        "remove_top_match_sensitivity": round(float(min(sensitivity, 999.0)), 4),
        "status": "STABLE" if dominant_hits / iterations >= 0.8 and sensitivity <= 35 else "UNSTABLE",
    }


def _drift_status(features: pd.DataFrame, source: pd.Series) -> dict[str, Any]:
    history = features.loc[features["time"] < source["time"]].sort_values("time")
    if len(history) < 80:
        return {"status": "WATCH", "score": None, "reason": "insufficient long-window history"}
    recent = history.tail(min(40, len(history) // 3))[FEATURE_COLUMNS].astype(float)
    long = history.iloc[:-len(recent)][FEATURE_COLUMNS].astype(float)
    if long.empty:
        return {"status": "WATCH", "score": None, "reason": "insufficient comparison window"}
    denominator = long.std().replace(0, np.nan)
    divergence = ((recent.mean() - long.mean()).abs() / denominator).replace([np.inf, -np.inf], np.nan).median()
    score = float(divergence) if pd.notna(divergence) else 0.0
    status = "BLOCKED" if score >= 2.5 else ("WARNING" if score >= 1.5 else ("WATCH" if score >= 0.8 else "NORMAL"))
    return {"status": status, "score": round(score, 6), "reason": "recent-versus-long robust standardized feature divergence"}


def _reliability_grade(*, qualified_count: int, ess: float, median_similarity: float, stability: Mapping[str, Any], drift_status: str, feature_coverage: float) -> str:
    if qualified_count == 0 or ess < 3 or feature_coverage < 60 or drift_status == "BLOCKED":
        return "X"
    stable = float(stability.get("dominant_scenario_stability") or 0)
    direction_stable = float(stability.get("direction_stability") or 0)
    if qualified_count >= 40 and ess >= 30 and median_similarity >= 80 and stable >= 80 and direction_stable >= 80 and drift_status == "NORMAL":
        return "A+"
    if ess >= 20 and median_similarity >= 75 and stable >= 70 and drift_status in {"NORMAL", "WATCH"}:
        return "A"
    if ess >= 10 and median_similarity >= 70:
        return "B" if drift_status != "WARNING" else "B"
    if ess >= 5 and median_similarity >= 60:
        return "C"
    return "X"


def simulate_field11(
    state: Mapping[str, Any], selection: Field11Selection, *, path: Path | str = DB_PATH,
    field10_path: Path | str = FIELD10_DB_PATH, force: bool = False,
) -> dict[str, Any]:
    """Run bounded historical-analogue matching against the prepared index."""
    started = time.perf_counter()
    migrate_field11_database(path)
    identity = resolve_field11_identity(state, field10_path=field10_path)
    manifest = load_index_manifest(identity=identity, path=path)
    guard = validate_index_identity(identity, manifest)
    if not guard["ok"]:
        return {"ok": False, "status": guard["status"], "errors": guard["errors"], "simulator_grade": "X"}
    selection = selection.normalized()
    if selection.symbol not in manifest.get("symbol_universe", []):
        return {"ok": False, "status": "SYMBOL_NOT_IN_CANONICAL_UNIVERSE", "simulator_grade": "X"}
    if selection.timeframe not in manifest.get("supported_timeframes", []):
        return {"ok": False, "status": "UNSUPPORTED_TIMEFRAME", "simulator_grade": "X"}
    selection_hash = _selection_hash(str(manifest["index_id"]), selection)
    if not force:
        cached = _load_cached_run(selection_hash, path)
        if cached is not None:
            cached["ok"] = True
            cached["status"] = "CACHED"
            return cached
    features = read_index_frame(manifest["feature_path"])
    ohlc = read_index_frame(manifest["ohlc_path"])
    features["time"] = pd.to_datetime(features["time"], errors="coerce", utc=True)
    ohlc["time"] = pd.to_datetime(ohlc["time"], errors="coerce", utc=True)
    scoped_source = features.loc[(features["symbol"] == selection.symbol) & (features["timeframe"] == selection.timeframe)].sort_values("time")
    if scoped_source.empty:
        return {"ok": False, "status": "SOURCE_SYMBOL_HISTORY_UNAVAILABLE", "simulator_grade": "X"}
    if selection.source_candle:
        requested_source = pd.to_datetime(selection.source_candle, errors="coerce", utc=True)
        source_matches = scoped_source.loc[scoped_source["time"] == requested_source]
        if source_matches.empty:
            return {"ok": False, "status": "INVALID_SOURCE_CANDLE", "simulator_grade": "X", "errors": ["selected source candle is absent from the prepared completed-candle index"]}
        source = source_matches.iloc[-1]
    else:
        source = scoped_source.iloc[-1]
    horizon_bars = _bars_for_horizon(selection.timeframe, selection.horizon_hours)
    source_time = pd.Timestamp(source["time"])
    candidate_symbols = _candidate_symbols(selection, manifest.get("symbol_universe", []))
    candidates = features.loc[(features["timeframe"] == selection.timeframe) & (features["symbol"].isin(candidate_symbols)) & (features["time"] < source_time)].copy()
    candidates = candidates.loc[candidates["time"] >= source_time - pd.Timedelta(days=selection.lookback_days)]
    candidates = candidates.loc[candidates["feature_coverage"] >= 60]
    if selection.same_broker_hour_only:
        candidates = candidates.loc[candidates["broker_hour"].astype(int) == int(source["broker_hour"])]
    elif selection.compatible_hour_range < 12:
        hour_distance = np.minimum((candidates["broker_hour"] - source["broker_hour"]).abs(), 24 - (candidates["broker_hour"] - source["broker_hour"]).abs())
        candidates = candidates.loc[hour_distance <= selection.compatible_hour_range]
    rejection_records: list[dict[str, Any]] = []
    if candidates.empty:
        return {"ok": False, "status": "NO_COMPATIBLE_ANALOGUES", "simulator_grade": "X", "errors": ["all historical candidates were removed by completed-candle and selector filters"]}
    scaler_bundle = joblib.load(manifest["scaler_path"])
    medians = pd.Series(scaler_bundle["medians"])
    scaler: RobustScaler = scaler_bundle["scaler"]
    candidate_matrix = candidates[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(medians).to_numpy(dtype=float)
    source_matrix = pd.DataFrame([source[FEATURE_COLUMNS].to_dict()])[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(medians).to_numpy(dtype=float)
    scaled_candidates = scaler.transform(candidate_matrix)
    scaled_source = scaler.transform(source_matrix)[0]
    cheap_distances = np.linalg.norm(scaled_candidates - scaled_source, axis=1) / math.sqrt(len(FEATURE_COLUMNS))
    candidates["cheap_distance"] = cheap_distances
    shortlist_size = min(len(candidates), max(selection.requested_analogues * 8, 100), MAX_SHORTLIST)
    candidates = candidates.nsmallest(shortlist_size, "cheap_distance").copy()
    ohlc_groups = {
        (symbol, timeframe): group.sort_values("time").reset_index(drop=True)
        for (symbol, timeframe), group in ohlc.groupby(["symbol", "timeframe"], observed=True)
    }
    qualified: list[dict[str, Any]] = []
    source_close = float(source["close"])
    source_index_time = source_time
    for _, candidate in candidates.iterrows():
        symbol = str(candidate["symbol"])
        group = ohlc_groups.get((symbol, selection.timeframe))
        analogue_id = f"{symbol}|{pd.Timestamp(candidate['time']).isoformat()}|{selection.timeframe}"
        if group is None or group.empty:
            rejection_records.append({"analogue_id": analogue_id, "inclusion_status": "REJECTED", "rejection_reason": "missing candle"})
            continue
        positions = np.flatnonzero(group["time"].eq(pd.Timestamp(candidate["time"])).to_numpy())
        if len(positions) == 0:
            rejection_records.append({"analogue_id": analogue_id, "inclusion_status": "REJECTED", "rejection_reason": "missing candle"})
            continue
        position = int(positions[-1])
        if position + horizon_bars >= len(group):
            rejection_records.append({"analogue_id": analogue_id, "inclusion_status": "REJECTED", "rejection_reason": "incomplete future horizon"})
            continue
        if symbol == selection.symbol and abs((source_index_time - pd.Timestamp(candidate["time"])).total_seconds()) < selection.horizon_hours * 3600:
            rejection_records.append({"analogue_id": analogue_id, "inclusion_status": "REJECTED", "rejection_reason": "overlapping observation"})
            continue
        components = _component_scores(source, candidate, float(candidate["cheap_distance"]))
        similarity = float(components["hybrid_similarity"])
        if similarity < selection.minimum_similarity:
            rejection_records.append({"analogue_id": analogue_id, "inclusion_status": "REJECTED", "rejection_reason": "insufficient similarity", "overall_similarity": similarity, "component_json": components})
            continue
        future = group.iloc[position: position + horizon_bars + 1]
        start = float(future.iloc[0]["close"])
        future_close = future["close"].to_numpy(dtype=float)
        future_high = future["high"].to_numpy(dtype=float)
        future_low = future["low"].to_numpy(dtype=float)
        rebased_close = rebase_path(future_close, start, source_close)
        pip = pip_size(selection.symbol)
        path_pips = (rebased_close - source_close) / pip
        high_pips = (rebase_path(future_high, start, source_close) - source_close) / pip
        low_pips = (rebase_path(future_low, start, source_close) - source_close) / pip
        endpoint = float(path_pips[-1])
        mfe = float(max(np.nanmax(high_pips), 0.0))
        mae = float(min(np.nanmin(low_pips), 0.0))
        changes = int(np.sum(np.sign(np.diff(path_pips))[1:] != np.sign(np.diff(path_pips))[:-1])) if len(path_pips) > 2 else 0
        qualified.append({
            "analogue_id": analogue_id, "historical_symbol": symbol, "historical_broker_candle": pd.Timestamp(candidate["time"]).isoformat(),
            "overall_similarity": similarity, "component_json": components, "path_pips": path_pips.tolist(),
            "high_pips": high_pips.tolist(), "low_pips": low_pips.tolist(), "endpoint_pips": endpoint,
            "mfe_pips": mfe, "mae_pips": mae, "direction_changes": changes,
            "historical_starting_bias": "BUY" if float(candidate["momentum"]) > 0 else ("SELL" if float(candidate["momentum"]) < 0 else "WAIT"),
            "historical_starting_regime": "UNAVAILABLE", "following_regime": "UNAVAILABLE",
        })
    qualified.sort(key=lambda item: (-item["overall_similarity"], item["historical_broker_candle"], item["historical_symbol"]))
    qualified = qualified[: selection.requested_analogues]
    if not qualified:
        return {"ok": False, "status": "NO_QUALIFIED_ANALOGUES", "simulator_grade": "X", "rejected_records": pd.DataFrame(rejection_records)}
    similarities = np.array([item["overall_similarity"] for item in qualified], dtype=float)
    if selection.weighting_policy.lower().startswith("equal"):
        weights = np.full(len(qualified), 1 / len(qualified))
    elif selection.weighting_policy.lower().startswith("distance"):
        inverse = 1 / np.maximum(100 - similarities, 1e-6)
        weights = inverse / inverse.sum()
    else:
        temperature = 8.0
        logits = (similarities - similarities.max()) / temperature
        weights = np.exp(logits)
        weights = weights / weights.sum()
    paths = np.array([item["path_pips"] for item in qualified], dtype=float)
    endpoints = np.array([item["endpoint_pips"] for item in qualified], dtype=float)
    labels, scenarios = _cluster_scenarios(paths, weights, selection.scenario_count, endpoints)
    for index, item in enumerate(qualified):
        item["final_weight"] = float(weights[index])
        item["match_rank"] = index + 1
        item["scenario_cluster"] = next((scenario["scenario_name"] for scenario in scenarios if scenario["cluster_id"] == int(labels[index])), f"cluster-{labels[index]}")
    stability = _bootstrap_stability(paths, weights, scenarios, seed=int(selection_hash[:8], 16))
    for scenario in scenarios:
        scenario["scenario_stability"] = stability["dominant_scenario_stability"] if scenario is scenarios[0] else None
    drift = _drift_status(features.loc[(features["symbol"] == selection.symbol) & (features["timeframe"] == selection.timeframe)], source)
    central50_low = np.quantile(paths, 0.25, axis=0).tolist()
    central50_high = np.quantile(paths, 0.75, axis=0).tolist()
    central80_low = np.quantile(paths, 0.10, axis=0).tolist()
    central80_high = np.quantile(paths, 0.90, axis=0).tolist()
    weighted_median_path = [_weighted_quantile(paths[:, step], weights, 0.5) for step in range(paths.shape[1])]
    ess = effective_sample_size(weights)
    median_similarity = float(np.median(similarities))
    grade = _reliability_grade(
        qualified_count=len(qualified), ess=ess, median_similarity=median_similarity,
        stability=stability, drift_status=str(drift["status"]), feature_coverage=float(source["feature_coverage"]),
    )
    if drift["status"] == "WARNING" and grade in {"A+", "A"}:
        grade = "B"
    if drift["status"] == "BLOCKED":
        grade = "X"
    dominant = scenarios[0]
    summary = {
        "selected_symbol": selection.symbol, "selected_timeframe": selection.timeframe,
        "selected_horizon_hours": selection.horizon_hours, "source_broker_candle": source_time.isoformat(),
        "canonical_run_id": identity["canonical_run_id"], "snapshot_hash": identity["snapshot_hash"],
        "candidate_count": int(shortlist_size), "qualified_analogue_count": len(qualified),
        "rejected_analogue_count": len(rejection_records), "best_match_similarity": round(float(similarities.max()), 4),
        "median_similarity": round(median_similarity, 4), "weighted_mean_similarity": round(float(np.average(similarities, weights=weights)), 4),
        "effective_sample_size": round(ess, 4), "dominant_scenario": dominant["scenario_name"],
        "dominant_weighted_historical_frequency": dominant["weighted_historical_frequency"],
        "weighted_median_endpoint_pips": round(_weighted_quantile(endpoints, weights, 0.5), 4),
        "endpoint_p10": round(_weighted_quantile(endpoints, weights, 0.10), 4),
        "endpoint_p90": round(_weighted_quantile(endpoints, weights, 0.90), 4),
        "median_mfe_pips": round(_weighted_quantile(np.array([item["mfe_pips"] for item in qualified]), weights, 0.5), 4),
        "median_mae_pips": round(_weighted_quantile(np.array([item["mae_pips"] for item in qualified]), weights, 0.5), 4),
        "direction_agreement": round(100 * max(weights[endpoints > 0].sum(), weights[endpoints < 0].sum(), weights[endpoints == 0].sum()), 4),
        "regime_match_quality": 50.0, "session_match_quality": round(float(np.average([item["component_json"]["session_similarity"] for item in qualified], weights=weights)), 4),
        "sentiment_match_quality": 50.0, "path_dispersion": round(float(np.mean(np.std(paths, axis=0))), 4),
        "simulator_reliability_grade": grade, "data_quality_grade": "A" if float(source["feature_coverage"]) >= 85 else ("B" if float(source["feature_coverage"]) >= 70 else "C"),
        "feature_coverage": round(float(source["feature_coverage"]), 4), "drift_status": drift["status"],
        "drift_details": drift, "stability": stability, "weighted_median_path_pips": weighted_median_path,
        "central_50_low": central50_low, "central_50_high": central50_high,
        "central_80_low": central80_low, "central_80_high": central80_high,
        "coverage_health": "HISTORICAL_EMPIRICAL_ONLY", "coverage_target_50": 50, "coverage_target_80": 80,
        "language_guard": "Weighted historical frequency is not a guaranteed future probability.",
        "runtime_seconds": round(time.perf_counter() - started, 4),
    }
    simulator_run_id = f"F11RUN-{selection_hash[:28]}"
    now = pd.Timestamp.now(tz="UTC").isoformat()
    with _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """INSERT INTO field11_simulator_run(
                    simulator_run_id,selection_hash,index_id,canonical_run_id,snapshot_hash,source_symbol,
                    source_timeframe,source_broker_candle,horizon_hours,selection_json,summary_json,scenarios_json,
                    simulator_grade,drift_status,outcome_status,created_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (simulator_run_id, selection_hash, manifest["index_id"], identity["canonical_run_id"], identity["snapshot_hash"],
                 selection.symbol, selection.timeframe, source_time.isoformat(), selection.horizon_hours, _canonical_json(asdict(selection)),
                 _canonical_json(summary), _canonical_json(scenarios), grade, drift["status"], "PENDING", now),
            )
            for item in qualified:
                outcome = {key: item[key] for key in ("path_pips", "high_pips", "low_pips", "endpoint_pips", "mfe_pips", "mae_pips", "direction_changes")}
                conn.execute(
                    """INSERT INTO field11_simulator_analogue(
                        simulator_run_id,analogue_id,match_rank,inclusion_status,rejection_reason,historical_symbol,
                        historical_broker_candle,overall_similarity,final_weight,component_json,outcome_json,scenario_cluster
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (simulator_run_id, item["analogue_id"], item["match_rank"], "INCLUDED", None, item["historical_symbol"],
                     item["historical_broker_candle"], item["overall_similarity"], item["final_weight"],
                     _canonical_json(item["component_json"]), _canonical_json(outcome), item["scenario_cluster"]),
                )
            for item in rejection_records:
                conn.execute(
                    """INSERT OR IGNORE INTO field11_simulator_analogue(
                        simulator_run_id,analogue_id,match_rank,inclusion_status,rejection_reason,historical_symbol,
                        historical_broker_candle,overall_similarity,final_weight,component_json,outcome_json,scenario_cluster
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (simulator_run_id, item.get("analogue_id") or f"REJ-{deterministic_hash(item)[:20]}", None, "REJECTED",
                     item.get("rejection_reason"), None, None, item.get("overall_similarity"), None,
                     _canonical_json(item.get("component_json") or {}), "{}", None),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    included_frame = pd.DataFrame([
        {
            "Match Rank": item["match_rank"], "Historical Broker Date": str(item["historical_broker_candle"])[:10],
            "Historical Broker Hour": str(item["historical_broker_candle"])[11:16], "Source Symbol": item["historical_symbol"],
            "Overall Similarity": item["overall_similarity"], "Final Weight": item["final_weight"],
            "Shape Similarity": item["component_json"]["shape_similarity"], "Technical Similarity": item["component_json"]["technical_similarity"],
            "Regime Similarity": item["component_json"]["regime_similarity"], "Session Similarity": item["component_json"]["session_similarity"],
            "Volatility Similarity": item["component_json"]["volatility_similarity"], "Sentiment Similarity": item["component_json"]["sentiment_similarity"],
            "Liquidity Similarity": item["component_json"]["liquidity_similarity"], "Cross-Market Similarity": item["component_json"]["cross_market_similarity"],
            "Historical Starting Bias": item["historical_starting_bias"], "Historical Starting Regime": item["historical_starting_regime"],
            "Following Regime": item["following_regime"], "Future Direction": "BUY" if item["endpoint_pips"] > 0 else ("SELL" if item["endpoint_pips"] < 0 else "WAIT"),
            "Endpoint Pips": item["endpoint_pips"], "Maximum Favorable Pips": item["mfe_pips"], "Maximum Adverse Pips": item["mae_pips"],
            "Bias Switch": item["direction_changes"] > 1, "Regime Switch": "UNAVAILABLE", "Scenario Cluster": item["scenario_cluster"],
            "Inclusion Status": "INCLUDED", "Rejection Reason": "", "Canonical Source ID": item["analogue_id"],
        }
        for item in qualified
    ])
    rejected_frame = pd.DataFrame(rejection_records)
    return {
        "ok": True, "status": "COMPLETED", "simulator_run_id": simulator_run_id,
        "selection_hash": selection_hash, "summary": summary, "scenarios": scenarios,
        "analogue_records": included_frame, "rejected_records": rejected_frame,
        "simulator_grade": grade, "drift_status": drift["status"], "cached": False,
    }


def _actual_path_for_run(run: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    ohlc = read_index_frame(manifest["ohlc_path"])
    ohlc["time"] = pd.to_datetime(ohlc["time"], errors="coerce", utc=True)
    source_time = pd.to_datetime(run["source_broker_candle"], errors="coerce", utc=True)
    group = ohlc.loc[(ohlc["symbol"] == run["source_symbol"]) & (ohlc["timeframe"] == run["source_timeframe"])].sort_values("time").reset_index(drop=True)
    positions = np.flatnonzero(group["time"].eq(pd.Timestamp(source_time)).to_numpy())
    if not len(positions):
        return None
    position = int(positions[-1])
    horizon_bars = _bars_for_horizon(str(run["source_timeframe"]), int(run["horizon_hours"]))
    if position + horizon_bars >= len(group):
        return None
    future = group.iloc[position: position + horizon_bars + 1]
    start = float(future.iloc[0]["close"])
    pip = pip_size(str(run["source_symbol"]))
    close_pips = (future["close"].to_numpy(dtype=float) - start) / pip
    high_pips = (future["high"].to_numpy(dtype=float) - start) / pip
    low_pips = (future["low"].to_numpy(dtype=float) - start) / pip
    return {
        "path_pips": close_pips.tolist(), "endpoint_pips": float(close_pips[-1]),
        "mfe_pips": float(max(np.max(high_pips), 0.0)), "mae_pips": float(min(np.min(low_pips), 0.0)),
    }


def settle_matured_simulations(*, path: Path | str = DB_PATH) -> dict[str, Any]:
    """Settle matured simulator runs once using deterministic keys."""
    migrate_field11_database(path)
    settled = 0
    with _connect(path) as conn:
        rows = conn.execute("SELECT * FROM field11_simulator_run WHERE outcome_status='PENDING'").fetchall()
    for row in rows:
        run = dict(row)
        with _connect(path) as conn:
            manifest_row = conn.execute("SELECT * FROM field11_index_manifest WHERE index_id=?", (run["index_id"],)).fetchone()
        if manifest_row is None:
            continue
        actual = _actual_path_for_run(run, dict(manifest_row))
        if actual is None:
            continue
        scenarios = json.loads(run["scenarios_json"])
        distances: dict[str, float] = {}
        actual_array = np.asarray(actual["path_pips"], dtype=float)
        for scenario in scenarios:
            candidate = np.asarray(scenario.get("median_path_pips") or [], dtype=float)
            if len(candidate) == len(actual_array):
                distances[str(scenario["scenario_name"])] = float(np.linalg.norm(candidate - actual_array) / math.sqrt(len(actual_array)))
        closest = min(distances, key=distances.get) if distances else "UNAVAILABLE"
        summary = json.loads(run["summary_json"])
        low50, high50 = np.asarray(summary.get("central_50_low") or []), np.asarray(summary.get("central_50_high") or [])
        low80, high80 = np.asarray(summary.get("central_80_low") or []), np.asarray(summary.get("central_80_high") or [])
        endpoint = actual_array[-1]
        inside50 = int(len(low50) == len(actual_array) and low50[-1] <= endpoint <= high50[-1])
        inside80 = int(len(low80) == len(actual_array) and low80[-1] <= endpoint <= high80[-1])
        dominant_correct = int(str(summary.get("dominant_scenario")) == closest)
        key = deterministic_hash({"simulator_run_id": run["simulator_run_id"], "source": run["source_broker_candle"], "horizon": run["horizon_hours"], "version": SIMULATOR_VERSION})
        with _connect(path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO field11_outcome_settlement(
                        settlement_key,simulator_run_id,actual_path_json,actual_endpoint_pips,actual_mfe_pips,actual_mae_pips,
                        closest_scenario,path_distance_json,inside_50_band,inside_80_band,dominant_scenario_correct,
                        settled_at_utc,outcome_status
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (key, run["simulator_run_id"], _canonical_json(actual["path_pips"]), actual["endpoint_pips"], actual["mfe_pips"],
                     actual["mae_pips"], closest, _canonical_json(distances), inside50, inside80, dominant_correct,
                     pd.Timestamp.now(tz="UTC").isoformat(), "SETTLED"),
                )
                changed = conn.execute("SELECT changes()").fetchone()[0]
                if changed:
                    conn.execute("UPDATE field11_simulator_run SET outcome_status='SETTLED' WHERE simulator_run_id=?", (run["simulator_run_id"],))
                    settled += 1
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    return {"ok": True, "status": "SETTLEMENT_COMPLETE", "settled_count": settled, "pending_count": max(0, len(rows) - settled)}


def load_validation_history(*, days: int = 25, path: Path | str = DB_PATH) -> pd.DataFrame:
    """Load persisted validation rows read-only; Settings owns migrations."""
    cutoff = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=max(1, days))).isoformat()
    query = """
        SELECT substr(r.source_broker_candle,1,10) AS [Broker Date],
               substr(r.source_broker_candle,12,5) AS [Broker Hour],
               r.source_symbol AS Symbol,r.source_timeframe AS Timeframe,r.horizon_hours AS Horizon,
               json_extract(r.summary_json,'$.qualified_analogue_count') AS [Analogue Count],
               json_extract(r.summary_json,'$.effective_sample_size') AS [Effective Sample Size],
               json_extract(r.summary_json,'$.median_similarity') AS [Median Similarity],
               json_extract(r.summary_json,'$.dominant_scenario') AS [Dominant Scenario],
               json_extract(r.summary_json,'$.dominant_weighted_historical_frequency') AS [Dominant Historical Frequency],
               r.simulator_grade AS [Simulator Grade],
               CASE WHEN o.actual_endpoint_pips>0 THEN 'BUY' WHEN o.actual_endpoint_pips<0 THEN 'SELL' ELSE 'WAIT' END AS [Actual Direction],
               o.actual_endpoint_pips AS [Actual Endpoint Pips],o.closest_scenario AS [Closest Scenario],
               CASE WHEN o.path_distance_json IS NULL THEN NULL ELSE
                    100.0 / (1.0 + (SELECT MIN(CAST(value AS REAL)) FROM json_each(o.path_distance_json)))
               END AS [Path Similarity to Closest Scenario],
               o.inside_50_band AS [Inside 50% Band],o.inside_80_band AS [Inside 80% Band],
               o.actual_mfe_pips AS [Maximum Favorable Pips],o.actual_mae_pips AS [Maximum Adverse Pips],
               r.drift_status AS [Drift Status],r.outcome_status AS [Outcome Status]
        FROM field11_simulator_run r
        LEFT JOIN field11_outcome_settlement o USING(simulator_run_id)
        WHERE r.created_at_utc>=?
        ORDER BY r.source_broker_candle DESC,r.source_symbol
    """
    with connect_readonly(path) as conn:
        return pd.read_sql_query(query, conn, params=(cutoff,))


__all__ = [
    "ARTIFACT_DIR", "DB_PATH", "INDEX_VERSION", "FEATURE_VERSION", "SIMULATOR_VERSION",
    "Field11Selection", "migrate_field11_database", "resolve_field11_identity", "prepare_field11_index",
    "load_index_manifest", "validate_index_identity", "pip_size", "rebase_path", "constrained_dtw_distance",
    "effective_sample_size", "read_index_frame", "simulate_field11", "settle_matured_simulations", "load_validation_history",
]
