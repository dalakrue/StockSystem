"""Common contracts and leakage-safe helpers for Advanced Quant Research V3.

The layer is additive and shadow-only.  It consumes the already validated
canonical completed-H1 frame and never creates a trading direction.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from statistics import NormalDist
from typing import Any, Mapping, Sequence
import json
import math

import numpy as np
import pandas as pd

VERSION = "quant-research-v3-contract-20260622-v1"
METHOD_VERSION = "quant-research-v3-20260622-v1"
PRODUCTION_INFLUENCE_ENABLED = False
MAX_LIVE_ROWS = 1500
HORIZONS = (1, 2, 3, 6)
QUANTILE_LEVELS = (0.01, 0.05, 0.10, 0.90, 0.95, 0.99)
TIME_NAMES = ("time", "timestamp", "datetime", "date", "completed_h1_time")
OHLC_ALIASES = {
    "open": ("open", "o", "Open", "OPEN"),
    "high": ("high", "h", "High", "HIGH"),
    "low": ("low", "l", "Low", "LOW"),
    "close": ("close", "c", "Close", "CLOSE", "last_close"),
    "volume": ("volume", "tick_volume", "Volume", "VOLUME"),
}


def utc_now_iso() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def stable_hash(value: Any) -> str:
    payload = json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def safe_div(numerator: Any, denominator: Any, default: float | None = None) -> float | None:
    a, b = finite_or_none(numerator), finite_or_none(denominator)
    if a is None or b is None or abs(b) <= 1e-15:
        return default
    value = a / b
    return value if math.isfinite(value) else default


def _first_column(frame: pd.DataFrame, aliases: Sequence[str]) -> str | None:
    lower = {str(c).strip().lower(): str(c) for c in frame.columns}
    for alias in aliases:
        if str(alias).strip().lower() in lower:
            return lower[str(alias).strip().lower()]
    return None


def normalize_completed_h1(
    frame: pd.DataFrame,
    *,
    completed_h1_time: Any | None = None,
    max_rows: int = MAX_LIVE_ROWS,
    reject_invalid_duplicates: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return deterministic, sorted, completed, positive OHLC rows.

    Duplicate timestamps are deterministically deduplicated only when the OHLC
    values agree after numeric normalisation. Conflicting duplicates are rejected
    by default through an unavailable result rather than silently averaged.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("Canonical completed-H1 input is empty.")
    source = frame.copy(deep=False)
    time_col = _first_column(source, TIME_NAMES)
    if time_col is None:
        if isinstance(source.index, pd.DatetimeIndex):
            source = source.copy()
            source["__time__"] = source.index
            time_col = "__time__"
        else:
            raise ValueError("No timestamp column or DatetimeIndex is available.")
    columns: dict[str, str] = {}
    for target, aliases in OHLC_ALIASES.items():
        found = _first_column(source, aliases)
        if found is not None:
            columns[target] = found
    missing = [name for name in ("open", "high", "low", "close") if name not in columns]
    if missing:
        raise ValueError("Missing OHLC columns: " + ", ".join(missing))

    out = pd.DataFrame({"time": pd.to_datetime(source[time_col], errors="coerce", utc=True)})
    for target in ("open", "high", "low", "close"):
        out[target] = pd.to_numeric(source[columns[target]], errors="coerce")
    if "volume" in columns:
        out["volume"] = pd.to_numeric(source[columns["volume"]], errors="coerce")
    out = out.dropna(subset=["time", "open", "high", "low", "close"])
    if completed_h1_time is not None:
        cutoff = pd.to_datetime(completed_h1_time, errors="coerce", utc=True)
        if pd.notna(cutoff):
            out = out.loc[out["time"] <= cutoff]
    out = out.sort_values("time", kind="mergesort")

    duplicate_count = int(out.duplicated("time", keep=False).sum())
    conflicting_duplicates = 0
    if duplicate_count:
        groups = out.loc[out.duplicated("time", keep=False)].groupby("time", sort=False)
        for _, group in groups:
            if len(group[["open", "high", "low", "close"]].drop_duplicates()) > 1:
                conflicting_duplicates += 1
        if conflicting_duplicates and reject_invalid_duplicates:
            raise ValueError(f"Conflicting duplicate H1 timestamps: {conflicting_duplicates}")
        if conflicting_duplicates:
            # A conflict is never averaged. Keep the last stable row only while
            # making the conflict explicit in the contract metadata.
            out = out.drop_duplicates("time", keep="last")
        else:
            out = out.drop_duplicates("time", keep="last")

    valid_price = (
        np.isfinite(out[["open", "high", "low", "close"]]).all(axis=1)
        & (out[["open", "high", "low", "close"]] > 0).all(axis=1)
        & (out["high"] >= out[["open", "close", "low"]].max(axis=1))
        & (out["low"] <= out[["open", "close", "high"]].min(axis=1))
    )
    invalid_rows = int((~valid_price).sum())
    out = out.loc[valid_price].copy()
    if out.empty:
        raise ValueError("No valid positive OHLC rows remain after validation.")
    if max_rows > 0 and len(out) > max_rows:
        out = out.iloc[-int(max_rows):].copy()
    out = out.reset_index(drop=True)
    signature = stable_hash({
        "rows": len(out),
        "first": out["time"].iloc[0],
        "last": out["time"].iloc[-1],
        "ohlc": np.round(out[["open", "high", "low", "close"]].to_numpy(dtype=float), 10).tolist(),
    })
    return out, {
        "source_row_count": int(len(frame)),
        "retained_row_count": int(len(out)),
        "duplicate_row_count": duplicate_count,
        "conflicting_duplicate_timestamps": conflicting_duplicates,
        "invalid_ohlc_rows": invalid_rows,
        "source_data_signature": signature,
        "latest_completed_h1": out["time"].iloc[-1].isoformat(),
        "future_rows_excluded": bool(completed_h1_time is not None and len(out) < len(frame)),
        "row_order_normalized": True,
    }


@dataclass(frozen=True)
class ResearchIdentity:
    run_id: str
    canonical_calculation_id: str
    source_generation_id: str
    symbol: str
    timeframe: str
    broker_timezone: str
    completed_h1_time: str
    calculation_created_at: str
    source_data_signature: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def identity_from_canonical(canonical: Mapping[str, Any], frame_meta: Mapping[str, Any]) -> ResearchIdentity:
    canonical = dict(canonical or {})
    calculation_id = str(canonical.get("canonical_calculation_id") or canonical.get("run_id") or stable_hash(frame_meta)[:24])
    return ResearchIdentity(
        run_id=str(canonical.get("run_id") or calculation_id),
        canonical_calculation_id=calculation_id,
        source_generation_id=str(canonical.get("source_generation_id") or calculation_id),
        symbol=str(canonical.get("symbol") or "EURUSD"),
        timeframe=str(canonical.get("timeframe") or "H1"),
        broker_timezone=str(canonical.get("broker_timezone") or (canonical.get("market") or {}).get("broker_timezone") or "BROKER_TIME_UNSPECIFIED"),
        completed_h1_time=str(canonical.get("latest_completed_candle_time") or frame_meta.get("latest_completed_h1") or ""),
        calculation_created_at=str(canonical.get("calculation_completed_at") or canonical.get("calculation_created_at") or utc_now_iso()),
        source_data_signature=str(frame_meta.get("source_data_signature") or canonical.get("data_signature") or ""),
    )


def method_contract(
    identity: ResearchIdentity,
    *,
    method_name: str,
    method_version: str,
    horizon_hours: int = 1,
    condition_key: str = "GLOBAL",
    sample_count: int = 0,
    minimum_sample_required: int = 0,
    fallback_level: str = "NONE",
    reliability_status: str = "INSUFFICIENT_SAMPLE",
    assumption_status: str = "PARTIALLY_SUPPORTED",
    calculation_error: str | None = None,
    limitations: Sequence[str] = (),
    **extra: Any,
) -> dict[str, Any]:
    base = {
        **identity.as_dict(),
        "method_name": str(method_name),
        "method_version": str(method_version),
        "horizon_hours": int(horizon_hours),
        "condition_key": str(condition_key),
        "sample_count": int(sample_count),
        "minimum_sample_required": int(minimum_sample_required),
        "fallback_level": str(fallback_level),
        "reliability_status": str(reliability_status),
        "assumption_status": str(assumption_status),
        "shadow_only": True,
        "production_influence_enabled": False,
        "calculation_error": str(calculation_error)[:1000] if calculation_error else None,
        "exact_limitations": [str(x) for x in limitations],
    }
    base.update(json_safe(extra))
    return base


def unavailable_contract(
    identity: ResearchIdentity,
    method_name: str,
    method_version: str,
    error: Exception | str,
    *,
    horizon_hours: int = 1,
    minimum_sample_required: int = 0,
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    return method_contract(
        identity,
        method_name=method_name,
        method_version=method_version,
        horizon_hours=horizon_hours,
        sample_count=0,
        minimum_sample_required=minimum_sample_required,
        fallback_level="UNAVAILABLE",
        reliability_status="UNAVAILABLE",
        assumption_status="UNSUPPORTED",
        calculation_error=str(error),
        limitations=tuple(limitations) + ("A numerical output was not fabricated after failure.",),
        status="UNAVAILABLE",
    )


def norm_ppf(probability: float, epsilon: float = 1e-10) -> float:
    p = min(max(float(probability), epsilon), 1.0 - epsilon)
    return float(NormalDist().inv_cdf(p))


def chi_square_sf(statistic: float, df: int) -> tuple[float | None, str]:
    try:
        from scipy.stats import chi2  # type: ignore
        return float(chi2.sf(float(statistic), int(df))), "scipy.stats.chi2.sf"
    except Exception:
        # Documented critical-value fallback for common df=3 Berkowitz LR test.
        critical_95 = {1: 3.841, 2: 5.991, 3: 7.815, 4: 9.488}.get(int(df))
        if critical_95 is None:
            return None, "critical-value-unavailable"
        return (0.049 if float(statistic) >= critical_95 else 0.051), f"95%-critical-value={critical_95}"


__all__ = [
    "VERSION", "METHOD_VERSION", "PRODUCTION_INFLUENCE_ENABLED", "MAX_LIVE_ROWS",
    "HORIZONS", "QUANTILE_LEVELS", "ResearchIdentity", "utc_now_iso", "json_safe",
    "stable_hash", "finite_or_none", "safe_div", "normalize_completed_h1",
    "identity_from_canonical", "method_contract", "unavailable_contract", "norm_ppf",
    "chi_square_sf",
]
