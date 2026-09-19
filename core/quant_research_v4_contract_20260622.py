"""Common leakage-safe contract for Advanced Quant Research V4.

All methods are additive, shadow-only and consume only completed canonical H1
candles plus already-settled outcomes.  The module intentionally contains no
trading-direction engine.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping, Sequence
import json
import math

import numpy as np
import pandas as pd

VERSION = "quant-research-v4-contract-20260622-v1"
IMPLEMENTATION_VERSION = "quant-research-v4-20260622-v1"
SHADOW_ONLY = True
PRODUCTION_INFLUENCE_ENABLED = False
MAX_OHLC_ROWS = 3000
MAX_SETTLED_ROWS = 3000
HORIZONS = (1, 2, 3, 6)


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
    raw = json.dumps(json_safe(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def finite(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
    except Exception:
        return default
    return out if math.isfinite(out) else default


def clip_probability(value: Any, floor: float = 1e-6) -> float:
    number = finite(value, 0.5)
    return float(np.clip(number, floor, 1.0 - floor))


def chi2_sf(statistic: float, df: int) -> float:
    """Small dependency-free chi-square survival function for df 1 or 2."""
    x = max(0.0, float(statistic))
    if df == 1:
        return float(math.erfc(math.sqrt(x / 2.0)))
    if df == 2:
        return float(math.exp(-x / 2.0))
    # Wilson-Hilferty normal approximation for uncommon larger df.
    z = ((x / df) ** (1.0 / 3.0) - (1.0 - 2.0 / (9.0 * df))) / math.sqrt(2.0 / (9.0 * df))
    return float(0.5 * math.erfc(z / math.sqrt(2.0)))


def normalize_completed_h1(
    frame: pd.DataFrame,
    *,
    completed_h1_time: Any | None = None,
    max_rows: int = MAX_OHLC_ROWS,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Use the established V3 normalizer, then restore causal numeric extras."""
    from core.quant_research_v3_contract_20260622 import normalize_completed_h1 as _v3_normalize

    clean, meta = _v3_normalize(
        frame,
        completed_h1_time=completed_h1_time,
        max_rows=max_rows,
        reject_invalid_duplicates=False,
    )
    # Preserve optional already-computed causal columns without changing OHLC.
    source = frame.copy(deep=False) if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    time_col = next((c for c in source.columns if str(c).lower() in {"time", "timestamp", "datetime", "date", "completed_h1_time"}), None)
    if time_col is not None:
        source_time = pd.to_datetime(source[time_col], errors="coerce", utc=True)
        extras = pd.DataFrame({"time": source_time})
        protected = {"time", "timestamp", "datetime", "date", "open", "high", "low", "close", "o", "h", "l", "c", "volume", "tick_volume"}
        aliases = {
            "trend_strength": ("trend_strength", "adx", "protected_trend_strength", "master_score"),
            "compression_score": ("compression_score", "compression", "squeeze_score"),
            "forecast_disagreement": ("forecast_disagreement", "model_disagreement", "disagreement"),
            "event_intensity": ("event_intensity", "news_event_intensity"),
            "data_quality_score": ("data_quality_score", "quality_score"),
        }
        lower = {str(c).lower(): c for c in source.columns}
        for target, names in aliases.items():
            found = next((lower[n] for n in names if n in lower and n not in protected), None)
            if found is not None:
                extras[target] = pd.to_numeric(source[found], errors="coerce")
        if len(extras.columns) > 1:
            extras = extras.dropna(subset=["time"]).sort_values("time").drop_duplicates("time", keep="last")
            clean = clean.merge(extras, on="time", how="left", validate="one_to_one")
    return clean, meta


def normalize_settled_outcomes(frame: pd.DataFrame | None, *, max_rows: int = MAX_SETTLED_ROWS) -> pd.DataFrame:
    """Chronologically normalize settled rows and discard unresolved/future targets."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    out = frame.copy(deep=False)
    lower = {str(c).lower(): c for c in out.columns}
    status_col = next((lower[k] for k in ("outcome_status", "settled_status", "status") if k in lower), None)
    if status_col is not None:
        out = out.loc[out[status_col].astype(str).str.upper().isin({"SETTLED", "COMPLETED", "OBSERVED"})]
    target_col = next((lower[k] for k in ("actual_time", "target_time", "settled_target_time", "due_time") if k in lower), None)
    origin_col = next((lower[k] for k in ("created_at", "forecast_origin_time", "origin_time", "latest_completed_candle_time") if k in lower), None)
    if target_col is not None:
        out = out.copy()
        out["__target_time"] = pd.to_datetime(out[target_col], errors="coerce", utc=True)
        out = out.dropna(subset=["__target_time"])
    if origin_col is not None:
        out = out.copy()
        out["__origin_time"] = pd.to_datetime(out[origin_col], errors="coerce", utc=True)
        if "__target_time" in out.columns:
            out = out.loc[out["__origin_time"].isna() | (out["__origin_time"] < out["__target_time"])]
    if "__target_time" in out.columns:
        out = out.sort_values("__target_time", kind="mergesort")
    if len(out) > max_rows:
        out = out.iloc[-max_rows:]
    dedupe = [c for c in (lower.get("prediction_id"), lower.get("run_id"), lower.get("horizon_hours"), "__target_time") if c]
    if dedupe:
        out = out.drop_duplicates(dedupe, keep="last")
    return out.reset_index(drop=True)


def identity_from_canonical(canonical: Mapping[str, Any], frame_meta: Mapping[str, Any]) -> dict[str, Any]:
    canonical = dict(canonical or {})
    calc = str(canonical.get("canonical_calculation_id") or canonical.get("calculation_id") or canonical.get("run_id") or stable_hash(frame_meta)[:24])
    generation = str(canonical.get("source_generation_id") or canonical.get("calculation_generation") or calc)
    latest = str(canonical.get("latest_completed_candle_time") or frame_meta.get("latest_completed_h1") or "")
    return {
        "source_generation_id": generation,
        "canonical_run_id": str(canonical.get("run_id") or calc),
        "calculation_id": calc,
        "source_signature": str(frame_meta.get("source_data_signature") or canonical.get("data_signature") or ""),
        "latest_completed_broker_h1_time": latest,
        "symbol": str(canonical.get("symbol") or "EURUSD"),
        "timeframe": str(canonical.get("timeframe") or "H1"),
        "broker_timezone": str(canonical.get("broker_timezone") or (canonical.get("market") or {}).get("broker_timezone") or "BROKER_TIME_UNSPECIFIED"),
    }


def common_result(
    identity: Mapping[str, Any],
    *,
    method_id: str,
    paper_title: str,
    paper_authors: str,
    exact_or_adaptation: str,
    sample_count: int = 0,
    effective_sample_count: int | None = None,
    minimum_required_samples: int = 0,
    status: str = "INSUFFICIENT_EVIDENCE",
    score: Any = None,
    p_value: Any = None,
    confidence: Any = None,
    reliability: Any = None,
    train_start: Any = None,
    train_end: Any = None,
    test_start: Any = None,
    test_end: Any = None,
    assumptions: Sequence[str] = (),
    limitations: Sequence[str] = (),
    fallback_used: Any = False,
    error: Any = None,
    **extra: Any,
) -> dict[str, Any]:
    base = {
        "method_id": method_id,
        "paper_title": paper_title,
        "paper_authors": paper_authors,
        "implementation_version": IMPLEMENTATION_VERSION,
        "exact_or_adaptation": exact_or_adaptation,
        **{k: identity.get(k) for k in (
            "source_generation_id", "canonical_run_id", "calculation_id", "source_signature",
            "latest_completed_broker_h1_time",
        )},
        "train_start": json_safe(train_start),
        "train_end": json_safe(train_end),
        "test_start": json_safe(test_start),
        "test_end": json_safe(test_end),
        "sample_count": int(sample_count),
        "effective_sample_count": int(effective_sample_count if effective_sample_count is not None else sample_count),
        "minimum_required_samples": int(minimum_required_samples),
        "status": str(status),
        "score": finite(score),
        "p_value": finite(p_value),
        "confidence": finite(confidence),
        "reliability": reliability,
        "assumptions": [str(x) for x in assumptions],
        "limitations": [str(x) for x in limitations],
        "fallback_used": json_safe(fallback_used),
        "error": str(error)[:1000] if error else None,
        "shadow_only": True,
        "production_influence_enabled": False,
        "evaluated_at": utc_now_iso(),
    }
    base.update(json_safe(extra))
    return base


def unavailable(identity: Mapping[str, Any], *, method_id: str, paper_title: str, paper_authors: str, error: Any, minimum_required_samples: int = 0, sample_count: int = 0, limitations: Sequence[str] = ()) -> dict[str, Any]:
    return common_result(
        identity,
        method_id=method_id,
        paper_title=paper_title,
        paper_authors=paper_authors,
        exact_or_adaptation="FAIL_SAFE_ADAPTATION",
        sample_count=sample_count,
        minimum_required_samples=minimum_required_samples,
        status="UNAVAILABLE",
        error=error,
        limitations=limitations,
        fallback_used=True,
    )


def guard_direction(protected_direction: str, proposed_direction: str | None) -> str:
    protected = str(protected_direction or "WAIT").upper()
    proposed = str(proposed_direction or protected).upper()
    if proposed == protected or proposed == "WAIT":
        return proposed
    return protected


__all__ = [
    "VERSION", "IMPLEMENTATION_VERSION", "SHADOW_ONLY", "PRODUCTION_INFLUENCE_ENABLED",
    "MAX_OHLC_ROWS", "MAX_SETTLED_ROWS", "HORIZONS", "json_safe", "stable_hash",
    "finite", "clip_probability", "chi2_sf", "normalize_completed_h1",
    "normalize_settled_outcomes", "identity_from_canonical", "common_result",
    "unavailable", "guard_direction", "utc_now_iso",
]
