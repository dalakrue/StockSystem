"""Covariate-shift weighted conformal calibration in shadow mode.

Only already-settled residuals and lightweight canonical covariates are used.
Guardrail failures return the existing interval unchanged.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence
import math
import numpy as np
import pandas as pd

from core.research_validation_common_20260621 import (
    HORIZONS, effective_sample_size, finite, stable_hash, utc_now_iso, weighted_quantile,
)

VERSION = "covariate-shift-conformal-20260621-v1"
DEFAULT_COVARIATES = (
    "atr_percentile", "adx", "di_spread", "session", "major_regime",
    "regime_age", "compression_score", "event_intensity", "recent_residual_scale",
    "mmd_shift_score",
)


def _column(frame: pd.DataFrame, *names: str) -> pd.Series:
    lookup = {str(c).strip().lower(): c for c in frame.columns}
    for name in names:
        col = lookup.get(name.lower())
        if col is not None:
            return frame[col]
    return pd.Series(np.nan, index=frame.index)


def _bounded_relevance_weights(history: pd.DataFrame, current: Mapping[str, Any], covariates: Sequence[str]) -> tuple[np.ndarray, dict[str, Any]]:
    log_weights = np.zeros(len(history), dtype=float)
    used = 0
    missing: list[str] = []
    support_failures: list[str] = []
    for name in covariates:
        if name not in current or current.get(name) in (None, ""):
            missing.append(name)
            continue
        aliases = {
            "major_regime": ("major_regime", "h1_regime", "regime"),
            "di_spread": ("di_spread", "di_separation"),
            "event_intensity": ("event_intensity", "event_risk_status", "event_score"),
            "recent_residual_scale": ("recent_residual_scale", "normalized_residual", "absolute_error_pips"),
            "mmd_shift_score": ("mmd_shift_score", "shift_score"),
        }.get(name, (name,))
        series = _column(history, *aliases)
        if series.isna().all():
            missing.append(name)
            continue
        target = current.get(name)
        numeric = pd.to_numeric(series, errors="coerce")
        target_numeric = finite(target)
        if target_numeric is not None and numeric.notna().sum() >= 8:
            valid = numeric.dropna()
            median = float(valid.median())
            scale = float((valid - median).abs().median()) * 1.4826
            scale = max(scale, float(valid.std(ddof=0)) * 0.25, 1e-9)
            z = np.abs(numeric.fillna(median).to_numpy(float) - target_numeric) / scale
            log_weights -= np.minimum(z, 6.0) * 0.35
            if target_numeric < float(valid.quantile(0.01)) or target_numeric > float(valid.quantile(0.99)):
                support_failures.append(name)
        else:
            values = series.fillna("UNKNOWN").astype(str)
            frequency = float((values == str(target)).mean())
            log_weights += np.where(values.to_numpy() == str(target), 0.0, -1.0)
            if frequency < 0.02:
                support_failures.append(name)
        used += 1
    if used == 0:
        return np.ones(len(history), dtype=float), {"used_covariates": 0, "missing_covariates": missing, "support_failures": ["all_covariates_missing"]}
    weights = np.exp(np.clip(log_weights - np.max(log_weights), -8.0, 0.0))
    weights = np.clip(weights, 0.02, 1.0)
    weights /= max(float(weights.mean()), 1e-12)
    return weights, {"used_covariates": used, "missing_covariates": missing, "support_failures": support_failures}


def build_covariate_shift_conformal(
    settled_predictions: Any,
    *,
    current_covariates: Mapping[str, Any] | None = None,
    existing_intervals: Mapping[str, Any] | None = None,
    alpha: float = 0.10,
    minimum_rows: int = 30,
    minimum_ess: float = 20.0,
    maximum_weight_share: float = 0.20,
    covariates: Sequence[str] = DEFAULT_COVARIATES,
    source_generation_id: str = "",
) -> dict[str, Any]:
    evaluated_at = utc_now_iso()
    try:
        data = settled_predictions.copy(deep=False) if isinstance(settled_predictions, pd.DataFrame) else pd.DataFrame(settled_predictions)
    except Exception:
        data = pd.DataFrame()
    current = dict(current_covariates or {})
    fallback = dict(existing_intervals or {})
    horizons: dict[str, Any] = {}
    shadow_rows: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        h = data.loc[pd.to_numeric(_column(data, "horizon"), errors="coerce") == horizon].copy(deep=False) if not data.empty else pd.DataFrame()
        status = _column(h, "record_status", "settled_status").fillna("SETTLED").astype(str).str.upper() if not h.empty else pd.Series(dtype=str)
        if not h.empty:
            h = h.loc[status.isin({"SETTLED", "OBSERVED", "COMPLETED"})]
        actual = pd.to_numeric(_column(h, "actual_close", "actual"), errors="coerce") if not h.empty else pd.Series(dtype=float)
        prediction = pd.to_numeric(_column(h, "predicted_close", "p50", "point_forecast"), errors="coerce") if not h.empty else pd.Series(dtype=float)
        residual = (actual - prediction).abs()
        valid = residual.notna()
        h = h.loc[valid]
        residual = residual.loc[valid]
        weights, support = _bounded_relevance_weights(h, current, covariates) if len(h) else (np.array([]), {"used_covariates": 0, "missing_covariates": list(covariates), "support_failures": ["empty_history"]})
        ess = effective_sample_size(weights)
        max_share = float(weights.max() / weights.sum()) if len(weights) and float(weights.sum()) > 0 else 1.0
        quantile = weighted_quantile(residual.to_numpy(float), min(1.0, (1.0 - alpha) * (1.0 + 1.0 / max(ess, 1.0))), weights)
        support_overlap_pass = not support["support_failures"]
        safeguards = {
            "minimum_rows_pass": len(h) >= minimum_rows,
            "effective_sample_size_pass": ess >= minimum_ess,
            "weight_concentration_pass": max_share <= maximum_weight_share,
            "covariates_available_pass": support["used_covariates"] >= 2,
            "support_overlap_pass": support_overlap_pass,
            "quantile_available_pass": quantile is not None and math.isfinite(float(quantile)),
        }
        safe = all(safeguards.values())
        existing = fallback.get(f"{horizon}h") or fallback.get(str(horizon)) or fallback.get(horizon) or {}
        row = {
            "horizon": horizon,
            "status": "SHADOW_WEIGHTED_CONFORMAL" if safe else "FALLBACK_TO_CANONICAL_INTERVAL",
            "weighted_residual_quantile": finite(quantile),
            "sample_count": int(len(h)),
            "effective_sample_size": round(float(ess), 6),
            "maximum_weight_share": round(float(max_share), 6),
            "safeguards": safeguards,
            "missing_covariates": support["missing_covariates"],
            "support_failures": support["support_failures"],
            "canonical_interval_preserved": True,
            "fallback_interval": existing,
            "promotion_allowed": False,
        }
        row["evaluation_id"] = "CSC-" + stable_hash([source_generation_id, row])[:24]
        horizons[f"{horizon}h"] = row
        shadow_rows.append(row)
    safe_count = sum(row["status"] == "SHADOW_WEIGHTED_CONFORMAL" for row in shadow_rows)
    return {
        "version": VERSION,
        "mode": "SHADOW",
        "status": "SHADOW_AVAILABLE" if safe_count else "CANONICAL_FALLBACK",
        "evaluated_at": evaluated_at,
        "source_generation_id": source_generation_id,
        "alpha": alpha,
        "horizons": horizons,
        "safe_horizon_count": safe_count,
        "promotion_allowed": False,
        "policy": "Weighted intervals are evidence-only until coverage, width and interval-score comparisons pass chronological validation.",
    }


__all__ = ["VERSION", "build_covariate_shift_conformal"]
