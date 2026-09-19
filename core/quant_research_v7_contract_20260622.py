"""Contracts and causal-normalization helpers for Quant Research V7.

V7 is additive, shadow-only evidence.  It never owns or mutates the protected
BUY/SELL/WAIT, score, regime, priority, forecast, TP or exit-risk formulas.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping
import json
import math

import numpy as np
import pandas as pd

VERSION = "quant-research-v7-20260622-v1"
SHADOW_ONLY = True
PRODUCTION_INFLUENCE_ENABLED = False
MAX_H1_ROWS = 3000
MAX_M1_ROWS = 12000
MAX_SETTLED_ROWS = 5000
MAX_FEATURES = 32
METHOD_COUNT = 10

PAPERS = {
    "stability_selection": "Stability Selection",
    "stationary_bootstrap": "The Stationary Bootstrap",
    "ledoit_wolf_covariance": "A Well-Conditioned Estimator for Large-Dimensional Covariance Matrices",
    "dynamic_conditional_correlation": "Dynamic Conditional Correlation: A Simple Class of Multivariate Generalized Autoregressive Conditional Heteroskedasticity Models",
    "generalized_autoregressive_score": "Generalized Autoregressive Score Models with Applications",
    "hidden_semi_markov_duration": "Hidden Semi-Markov Models",
    "midas_multi_frequency": "MIDAS Regressions: Further Results and New Directions",
    "bds_residual_test": "A Test for Independence Based on the Correlation Dimension",
    "dynamic_trading_costs": "Dynamic Trading with Predictable Returns and Transaction Costs",
    "coherent_risk": "Coherent Measures of Risk",
}


def finite(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except Exception:
        return default
    return number if math.isfinite(number) else default


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.ndarray):
        return [json_safe(v) for v in value.tolist()]
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is pd.NA:
        return None
    return value


def stable_hash(value: Any) -> str:
    raw = json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def deterministic_seed(generation_id: Any, method_id: str) -> tuple[int, str]:
    digest = stable_hash({"generation_id": str(generation_id), "method_id": method_id})
    return int(digest[:8], 16), digest[:16]


def _time_col(frame: pd.DataFrame) -> str | None:
    aliases = {
        "event_time_utc", "time", "timestamp", "datetime", "date", "completed_h1_time",
        "published_time_utc", "target_time", "actual_time", "due_time",
    }
    return next((c for c in frame.columns if str(c).lower() in aliases), None)


def normalize_completed_frame(
    frame: pd.DataFrame | None,
    *,
    cutoff_utc: Any,
    max_rows: int,
    required_ohlc: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(), {"rows": 0, "status": "UNAVAILABLE"}
    source = frame.copy(deep=False)
    tcol = _time_col(source)
    if tcol is None and not isinstance(source.index, pd.DatetimeIndex):
        return pd.DataFrame(), {"rows": 0, "status": "UNAVAILABLE", "reason": "timestamp column unavailable"}
    out = source.copy(deep=False)
    out = out.assign(event_time_utc=pd.to_datetime(source[tcol] if tcol else source.index, errors="coerce", utc=True))
    lower = {str(c).lower(): c for c in out.columns}
    if required_ohlc and not all(name in lower for name in ("open", "high", "low", "close")):
        return pd.DataFrame(), {"rows": 0, "status": "UNAVAILABLE", "reason": "OHLC columns unavailable"}
    for name in ("open", "high", "low", "close", "volume", "tick_volume", "spread", "slippage"):
        if name in lower:
            out[lower[name]] = pd.to_numeric(out[lower[name]], errors="coerce")
    cutoff = pd.to_datetime(cutoff_utc, errors="coerce", utc=True)
    out = out.loc[out["event_time_utc"].notna()]
    if pd.notna(cutoff):
        out = out.loc[out["event_time_utc"] <= cutoff]
    out = out.sort_values("event_time_utc", kind="mergesort").drop_duplicates("event_time_utc", keep="last").tail(max_rows).reset_index(drop=True)
    if required_ohlc and not out.empty:
        lower = {str(c).lower(): c for c in out.columns}
        out = out.dropna(subset=[lower[x] for x in ("open", "high", "low", "close")])
    meta = {
        "rows": int(len(out)),
        "status": "AVAILABLE" if not out.empty else "UNAVAILABLE",
        "first": out["event_time_utc"].iloc[0].isoformat() if not out.empty else None,
        "last": out["event_time_utc"].iloc[-1].isoformat() if not out.empty else None,
        "cutoff": cutoff.isoformat() if pd.notna(cutoff) else None,
    }
    return out, meta


def normalize_settled(frame: pd.DataFrame | None, *, cutoff_utc: Any) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    out = frame.copy(deep=False)
    lower = {str(c).lower(): c for c in out.columns}
    status_col = next((lower[k] for k in ("outcome_status", "settled_status", "status") if k in lower), None)
    if status_col is not None:
        accepted = {"SETTLED", "COMPLETED", "OBSERVED", "CLOSED"}
        selected = out[status_col].astype(str).str.upper().isin(accepted)
        if selected.any():
            out = out.loc[selected]
    tcol = next((lower[k] for k in ("actual_time", "target_time", "settled_target_time", "due_time", "event_time_utc", "time") if k in lower), None)
    if tcol is not None:
        out = out.assign(__settled_time=pd.to_datetime(out[tcol], errors="coerce", utc=True))
        cutoff = pd.to_datetime(cutoff_utc, errors="coerce", utc=True)
        if pd.notna(cutoff):
            out = out.loc[out["__settled_time"].isna() | (out["__settled_time"] <= cutoff)]
        out = out.sort_values("__settled_time", kind="mergesort")
    for c in out.columns:
        if any(token in str(c).lower() for token in ("error", "residual", "return", "loss", "correct", "price")):
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out.replace([np.inf, -np.inf], np.nan).tail(MAX_SETTLED_ROWS).reset_index(drop=True)


def canonical_identity(canonical: Mapping[str, Any], h1_meta: Mapping[str, Any]) -> dict[str, Any]:
    calculation_id = str(canonical.get("canonical_calculation_id") or canonical.get("run_id") or "")
    generation_id = str(canonical.get("calculation_generation") or canonical.get("generation") or calculation_id)
    latest = str(
        canonical.get("latest_completed_h1_utc")
        or canonical.get("latest_completed_candle_time")
        or h1_meta.get("last")
        or ""
    )
    broker = (
        canonical.get("completed_broker_time")
        or canonical.get("latest_completed_broker_h1_time")
        or canonical.get("broker_time")
        or (canonical.get("identity") or {}).get("completed_broker_time")
        or latest
    )
    return {
        "calculation_id": calculation_id,
        "source_generation_id": generation_id,
        "latest_completed_h1_utc": latest,
        "completed_broker_time": str(broker or ""),
        "symbol": str(canonical.get("symbol") or "EURUSD"),
        "timeframe": str(canonical.get("timeframe") or "H1"),
    }


def common_method(
    method_id: str,
    *,
    status: str,
    sample_count: int,
    minimum_sample_required: int,
    cutoff_time: Any,
    output_metrics: Mapping[str, Any] | None = None,
    assumptions: list[str] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "method_id": method_id,
        "paper_title": PAPERS[method_id],
        "status": status,
        "sample_count": int(sample_count),
        "minimum_sample_required": int(minimum_sample_required),
        "input_cutoff_time": str(cutoff_time or ""),
        "output_metrics": json_safe(dict(output_metrics or {})),
        "assumptions": list(assumptions or []),
        "limitations": list(limitations or []),
        "shadow_only": True,
        "production_influence_enabled": False,
    }


def protected_decision(canonical: Mapping[str, Any]) -> str:
    final = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
    return str(final.get("final_decision") or final.get("tradeability_decision") or canonical.get("decision") or "WAIT").upper()


def extract_numeric_features(frame: pd.DataFrame, *, max_features: int = MAX_FEATURES) -> tuple[pd.DataFrame, list[str]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(), []
    blocked = {"event_time_utc", "target", "future", "label", "actual", "prediction_outcome", "direction_correct"}
    candidates = []
    for col in frame.columns:
        name = str(col).lower()
        if name in blocked or any(token in name for token in ("future", "target_", "actual_", "lead_")):
            continue
        values = pd.to_numeric(frame[col], errors="coerce")
        if values.notna().sum() >= max(20, len(frame) // 5) and values.nunique(dropna=True) > 1:
            candidates.append((col, float(values.notna().mean()), int(values.nunique(dropna=True))))
    candidates.sort(key=lambda x: (-x[1], -x[2], str(x[0])))
    cols = [c[0] for c in candidates[:max_features]]
    out = pd.DataFrame({str(c): pd.to_numeric(frame[c], errors="coerce") for c in cols})
    return out, [str(c) for c in cols]


__all__ = [
    "VERSION", "PAPERS", "METHOD_COUNT", "MAX_H1_ROWS", "MAX_M1_ROWS", "MAX_SETTLED_ROWS",
    "finite", "json_safe", "stable_hash", "deterministic_seed", "normalize_completed_frame",
    "normalize_settled", "canonical_identity", "common_method", "protected_decision",
    "extract_numeric_features",
]
