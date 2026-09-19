"""Shared deterministic helpers for the 2026-06-21 validation layer."""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

VERSION = "research-validation-common-20260621-v1"
HORIZONS = (1, 2, 3, 4, 5, 6)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def finite(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except Exception:
        return default


def clip(value: Any, lo: float, hi: float, default: float = 0.0) -> float:
    number = finite(value, default)
    return float(max(lo, min(hi, default if number is None else number)))


def probability(value: Any, default: float | None = None) -> float | None:
    number = finite(value, default)
    if number is None:
        return None
    if number > 1.0:
        number /= 100.0
    return float(max(0.0, min(1.0, number)))


def direction(value: Any) -> str:
    text = str(value or "").strip().upper()
    if "BUY" in text or "BULL" in text or text == "UP":
        return "BUY"
    if "SELL" in text or "BEAR" in text or text == "DOWN":
        return "SELL"
    return "WAIT"


def utc_timestamp(value: Any) -> pd.Timestamp | None:
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    except Exception:
        return None


def session_name(value: Any) -> str:
    ts = utc_timestamp(value)
    if ts is None:
        return "UNKNOWN"
    hour = int(ts.hour)
    if hour < 7:
        return "ASIA"
    if hour < 12:
        return "LONDON"
    if hour < 16:
        return "LONDON_NY_OVERLAP"
    if hour < 21:
        return "NEW_YORK"
    return "LATE_NY"


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return [json_safe(v) for v in value.tolist()]
    if isinstance(value, pd.DataFrame):
        return [json_safe(v) for v in value.to_dict("records")]
    if isinstance(value, pd.Series):
        return [json_safe(v) for v in value.tolist()]
    if isinstance(value, (pd.Timestamp, datetime)):
        ts = utc_timestamp(value)
        return ts.isoformat() if ts is not None else str(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if value is pd.NA:
        return None
    return value


def stable_hash(value: Any) -> str:
    payload = json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def deterministic_seed(value: Any) -> int:
    return int(stable_hash(value)[:16], 16) % (2**32 - 1)


def find_column(frame: pd.DataFrame, aliases: Sequence[str]) -> str | None:
    lookup = {str(column).strip().lower(): str(column) for column in frame.columns}
    for alias in aliases:
        hit = lookup.get(str(alias).strip().lower())
        if hit is not None:
            return hit
    return None


def test_profile() -> str:
    return str(os.getenv("ADX_TEST_PROFILE", "production") or "production").strip().lower()


def profile_int(production: int, fast: int) -> int:
    return int(fast if test_profile() in {"fast", "smoke", "ci"} else production)


def normal_two_sided_p(statistic: float) -> float:
    return float(math.erfc(abs(float(statistic)) / math.sqrt(2.0)))


def weighted_quantile(values: Sequence[float], quantile: float, weights: Sequence[float] | None = None) -> float | None:
    x = np.asarray(values, dtype=float)
    mask = np.isfinite(x)
    x = x[mask]
    if x.size == 0:
        return None
    q = float(max(0.0, min(1.0, quantile)))
    if weights is None:
        return float(np.quantile(x, q, method="higher"))
    w = np.asarray(weights, dtype=float)[mask]
    valid = np.isfinite(w) & (w >= 0)
    x = x[valid]
    w = w[valid]
    if x.size == 0 or float(w.sum()) <= 0:
        return None
    order = np.argsort(x, kind="mergesort")
    x = x[order]
    w = w[order]
    cumulative = np.cumsum(w)
    threshold = q * float(cumulative[-1])
    index = int(np.searchsorted(cumulative, threshold, side="left"))
    return float(x[min(index, len(x) - 1)])


def effective_sample_size(weights: Sequence[float]) -> float:
    w = np.asarray(weights, dtype=float)
    w = w[np.isfinite(w) & (w >= 0)]
    if w.size == 0 or float(np.sum(w * w)) <= 0:
        return 0.0
    return float(np.sum(w) ** 2 / np.sum(w * w))


def bounded_softmax(scores: Sequence[float], minimum: float = 0.0, maximum: float = 1.0) -> np.ndarray:
    values = np.asarray(scores, dtype=float)
    if values.size == 0:
        return values
    values = np.where(np.isfinite(values), values, -1e9)
    values -= np.max(values)
    weights = np.exp(np.clip(values, -60, 60))
    weights = weights / max(float(weights.sum()), 1e-12)
    minimum = max(0.0, float(minimum))
    maximum = min(1.0, max(float(maximum), minimum))
    for _ in range(8):
        weights = np.clip(weights, minimum, maximum)
        total = float(weights.sum())
        if total <= 0:
            weights[:] = 1.0 / len(weights)
            break
        weights /= total
    return weights


__all__ = [
    "VERSION", "HORIZONS", "utc_now_iso", "mapping", "finite", "clip",
    "probability", "direction", "utc_timestamp", "session_name", "json_safe",
    "stable_hash", "deterministic_seed", "find_column", "test_profile", "profile_int",
    "normal_two_sided_p", "weighted_quantile", "effective_sample_size", "bounded_softmax",
]
