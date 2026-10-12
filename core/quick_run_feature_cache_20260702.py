"""Immutable source fingerprint and shared feature bundle for Quick Run.

This cache is an orchestration/performance substrate only. It never changes a
protected Field 1-10 output. Calculators may adopt the cached columns after
fixture equality tests prove exact parity with their existing implementations.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, MutableMapping
import json

import numpy as np
import pandas as pd

CACHE_KEY = "quick_run_shared_feature_cache_20260702"
ACTIVE_KEY = "quick_run_shared_feature_bundle_20260702"
VERSION = "quick-run-feature-cache-20260702-v1"


def _time_column(frame: pd.DataFrame) -> str | None:
    for name in ("time", "datetime", "timestamp", "Broker Candle Time", "broker_timestamp"):
        if name in frame.columns:
            return name
    return None


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    work = frame.copy(deep=False)
    rename = {str(c).lower(): c for c in work.columns}
    required = {}
    for name in ("open", "high", "low", "close"):
        source = rename.get(name)
        if source is None:
            return pd.DataFrame()
        required[name] = source
    result = pd.DataFrame({name: pd.to_numeric(work[source], errors="coerce") for name, source in required.items()})
    tcol = _time_column(work)
    if tcol:
        result["completed_broker_candle"] = pd.to_datetime(work[tcol], errors="coerce", utc=True)
    elif isinstance(work.index, pd.DatetimeIndex):
        result["completed_broker_candle"] = pd.to_datetime(work.index, errors="coerce", utc=True)
    else:
        result["completed_broker_candle"] = pd.NaT
    return result.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def _last_rows_hash(frame: pd.DataFrame, rows: int = 8) -> str:
    if frame.empty:
        return "EMPTY"
    tail = frame.tail(max(1, int(rows))).copy()
    material = tail.to_json(orient="split", date_format="iso", double_precision=15)
    return sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceFingerprint:
    provider: str
    symbol: str
    timeframe: str
    completed_broker_candle: str
    row_count: int
    last_rows_hash: str
    calculation_version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "completed_broker_candle": self.completed_broker_candle,
            "row_count": self.row_count,
            "last_rows_hash": self.last_rows_hash,
            "calculation_version": self.calculation_version,
        }

    def key(self) -> str:
        return sha256(json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SharedFeatureBundle:
    fingerprint: SourceFingerprint
    frame: pd.DataFrame
    cache_hit: bool


def build_source_fingerprint(
    frame: pd.DataFrame,
    *,
    provider: Any,
    symbol: Any,
    timeframe: Any,
    completed_broker_candle: Any,
    calculation_version: Any,
) -> SourceFingerprint:
    normalized = _normalize_frame(frame)
    candle = pd.to_datetime(completed_broker_candle, errors="coerce", utc=True)
    if pd.isna(candle) and not normalized.empty:
        valid = normalized["completed_broker_candle"].dropna()
        candle = valid.max() if not valid.empty else pd.NaT
    candle_text = pd.Timestamp(candle).isoformat() if pd.notna(candle) else "UNRESOLVED"
    return SourceFingerprint(
        provider=str(provider or "UNKNOWN").upper(),
        symbol=str(symbol or "EURUSD").upper(),
        timeframe=str(timeframe or "H1").upper(),
        completed_broker_candle=candle_text,
        row_count=int(len(normalized)),
        last_rows_hash=_last_rows_hash(normalized),
        calculation_version=str(calculation_version or "UNKNOWN"),
    )


def _wilder_adx(work: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = work["high"], work["low"], work["close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=work.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=work.index)
    tr = pd.concat(((high-low).abs(), (high-close.shift()).abs(), (low-close.shift()).abs()), axis=1).max(axis=1)
    alpha = 1.0 / max(1, int(period))
    atr = tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr.replace(0, np.nan)
    minus_di = 100.0 * minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr.replace(0, np.nan)
    dx = 100.0 * (plus_di-minus_di).abs() / (plus_di+minus_di).replace(0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()


def _build_features(frame: pd.DataFrame) -> pd.DataFrame:
    work = _normalize_frame(frame)
    if work.empty:
        return work
    work = work.copy()
    work["return_1"] = work["close"].pct_change()
    work["log_return_1"] = np.log(work["close"].replace(0, np.nan)).diff()
    work["true_range"] = pd.concat(
        ((work["high"]-work["low"]).abs(), (work["high"]-work["close"].shift()).abs(), (work["low"]-work["close"].shift()).abs()),
        axis=1,
    ).max(axis=1)
    work["volatility_24"] = work["log_return_1"].rolling(24, min_periods=2).std(ddof=1)
    work["adx_14"] = _wilder_adx(work, 14)
    hours = work["completed_broker_candle"].dt.hour
    work["broker_hour"] = hours.astype("Int64")
    work["session_input"] = pd.cut(
        hours,
        bins=[-1, 5, 8, 12, 16, 20, 23],
        labels=["TOKYO", "LONDON_OPEN", "LONDON", "LONDON_NY_OVERLAP", "NEW_YORK", "LATE_NY"],
    ).astype("object")
    return work


def get_or_build_shared_feature_bundle(
    state: MutableMapping[str, Any],
    frame: pd.DataFrame,
    *,
    provider: Any,
    symbol: Any,
    timeframe: Any,
    completed_broker_candle: Any,
    calculation_version: Any,
) -> SharedFeatureBundle:
    fingerprint = build_source_fingerprint(
        frame,
        provider=provider,
        symbol=symbol,
        timeframe=timeframe,
        completed_broker_candle=completed_broker_candle,
        calculation_version=calculation_version,
    )
    cache = state.get(CACHE_KEY)
    if not isinstance(cache, dict):
        cache = {}
        state[CACHE_KEY] = cache
    key = fingerprint.key()
    cached = cache.get(key)
    if isinstance(cached, pd.DataFrame):
        bundle = SharedFeatureBundle(fingerprint=fingerprint, frame=cached.copy(deep=False), cache_hit=True)
    else:
        features = _build_features(frame)
        # Keep only a bounded number of immutable fingerprints per process.
        if len(cache) >= 12:
            cache.pop(next(iter(cache)))
        cache[key] = features.copy(deep=False)
        bundle = SharedFeatureBundle(fingerprint=fingerprint, frame=features, cache_hit=False)
    state[ACTIVE_KEY] = {
        "fingerprint": fingerprint.as_dict(),
        "fingerprint_key": key,
        "cache_hit": bundle.cache_hit,
        "rows": len(bundle.frame),
        "version": VERSION,
    }
    return bundle


def append_completed_candle(history: pd.DataFrame, new_rows: pd.DataFrame, *, time_column: str) -> pd.DataFrame:
    """Append only unseen completed candles while preserving newest source row."""
    old = history.copy() if isinstance(history, pd.DataFrame) else pd.DataFrame()
    new = new_rows.copy() if isinstance(new_rows, pd.DataFrame) else pd.DataFrame()
    if new.empty:
        return old
    combined = pd.concat([old, new], ignore_index=True)
    if time_column not in combined:
        return combined
    times = pd.to_datetime(combined[time_column], errors="coerce", utc=True)
    combined = combined.assign(_completed_time=times).dropna(subset=["_completed_time"])
    combined = combined.drop_duplicates("_completed_time", keep="last").sort_values("_completed_time")
    return combined.drop(columns=["_completed_time"]).reset_index(drop=True)


__all__ = [
    "VERSION", "CACHE_KEY", "ACTIVE_KEY", "SourceFingerprint", "SharedFeatureBundle",
    "build_source_fingerprint", "get_or_build_shared_feature_bundle", "append_completed_candle",
]
