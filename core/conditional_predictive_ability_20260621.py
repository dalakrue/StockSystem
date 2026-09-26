"""Lightweight Giacomini-White-style conditional predictive ability evidence.

This module is a shadow statistical validator.  It compares already-existing
forecast paths using only chronologically settled observations.  It never
creates a direction and never changes the protected Full Metric authority.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence
import math

import numpy as np
import pandas as pd

from core.research_validation_common_20260621 import (
    HORIZONS, finite, normal_two_sided_p, stable_hash, utc_now_iso,
)

VERSION = "conditional-predictive-ability-20260621-v1"
MIN_SAMPLES = 24


def _series(frame: pd.DataFrame, names: Sequence[str], default: Any = np.nan) -> pd.Series:
    lookup = {str(c).lower(): c for c in frame.columns}
    for name in names:
        if name.lower() in lookup:
            return frame[lookup[name.lower()]]
    return pd.Series(default, index=frame.index)


def _normalise(frame: Any) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    data = frame.copy(deep=False)
    status = _series(data, ("record_status", "settled_status", "status"), "SETTLED").astype(str).str.upper()
    data = data.loc[status.isin({"SETTLED", "OBSERVED", "COMPLETED"})].copy(deep=False)
    if data.empty:
        return data
    data["horizon"] = pd.to_numeric(_series(data, ("horizon",)), errors="coerce")
    data = data.loc[data["horizon"].isin(HORIZONS)]
    for column, aliases in {
        "actual": ("actual_close", "actual", "y_true"),
        "origin": ("forecast_origin_price", "origin_price", "last_close"),
        "prediction": ("predicted_close", "point_forecast", "p50", "prediction"),
        "lower": ("lower_band", "lower_bound", "p10"),
        "upper": ("upper_band", "upper_bound", "p90"),
        "buy_probability": ("calibrated_buy_probability", "raw_buy_probability", "buy_probability"),
        "system_loss": ("system_loss", "documented_system_loss"),
    }.items():
        data[column] = pd.to_numeric(_series(data, aliases), errors="coerce")
    data["model"] = _series(data, ("method", "model", "path", "model_id"), "canonical").astype(str)
    data["origin_time"] = pd.to_datetime(_series(data, ("forecast_origin_time", "origin_time", "created_at")), errors="coerce", utc=True)
    data["target_time"] = pd.to_datetime(_series(data, ("target_time",)), errors="coerce", utc=True)
    data["settlement_time"] = pd.to_datetime(_series(data, ("settlement_timestamp", "settled_at")), errors="coerce", utc=True)
    data = data.loc[data["origin_time"].notna() & data["target_time"].notna()]
    data = data.loc[(data["origin_time"] < data["target_time"]) & (data["settlement_time"].isna() | (data["settlement_time"] >= data["origin_time"]))]
    data["major_regime"] = _series(data, ("h1_regime", "major_regime", "regime"), "UNKNOWN").astype(str)
    data["minor_regime"] = _series(data, ("minor_regime",), "UNKNOWN").astype(str)
    data["session"] = _series(data, ("session",), "UNKNOWN").astype(str)
    data["volatility_bucket"] = _series(data, ("volatility_bucket", "atr_bucket"), "UNKNOWN").astype(str)
    data["regime_transition_risk"] = _series(data, ("regime_transition_risk",), "UNKNOWN").astype(str)
    data["event_risk_bucket"] = _series(data, ("event_risk_status", "event_risk_bucket"), "UNKNOWN").astype(str)
    data["trend_strength_bucket"] = _series(data, ("trend_strength_bucket", "adx_bucket"), "UNKNOWN").astype(str)
    data["forecast_disagreement_bucket"] = _series(data, ("forecast_disagreement_bucket", "model_agreement"), "UNKNOWN").astype(str)
    return data


def _loss(frame: pd.DataFrame, name: str) -> pd.Series:
    actual = frame["actual"]
    pred = frame["prediction"]
    if name == "MAE":
        return (actual - pred).abs()
    if name == "DIRECTIONAL_BRIER":
        event = (actual > frame["origin"]).astype(float)
        probability = frame["buy_probability"].where(frame["buy_probability"] <= 1, frame["buy_probability"] / 100.0)
        fallback = (pred > frame["origin"]).astype(float)
        probability = probability.fillna(fallback).clip(0, 1)
        return (probability - event) ** 2
    if name == "INTERVAL_SCORE":
        alpha = 0.20
        lower, upper = frame["lower"], frame["upper"]
        width = upper - lower
        penalty = (2.0 / alpha) * ((lower - actual).clip(lower=0) + (actual - upper).clip(lower=0))
        return width + penalty
    if name == "CRPS":
        # Exact CRPS is used only when already available.  With three interval
        # points, the deterministic interval-score proxy remains explicitly marked.
        existing = pd.to_numeric(_series(frame, ("crps", "crps_loss")), errors="coerce")
        return existing
    if name == "SYSTEM_LOSS":
        return frame["system_loss"]
    return pd.Series(np.nan, index=frame.index)


def _hac_mean_test(differences: Sequence[float], lag: int) -> tuple[float, float, float]:
    values = np.asarray(differences, dtype=float)
    values = values[np.isfinite(values)]
    n = values.size
    if n < 2:
        return float("nan"), float("nan"), float("nan")
    centered = values - values.mean()
    gamma0 = float(np.dot(centered, centered) / n)
    long_run = gamma0
    max_lag = min(max(0, int(lag)), n - 1)
    for k in range(1, max_lag + 1):
        covariance = float(np.dot(centered[k:], centered[:-k]) / n)
        long_run += 2.0 * (1.0 - k / (max_lag + 1.0)) * covariance
    standard_error = math.sqrt(max(long_run, 1e-15) / n)
    statistic = float(values.mean() / standard_error)
    return statistic, normal_two_sided_p(statistic), standard_error


def _condition_slices(frame: pd.DataFrame) -> Iterable[tuple[str, str, pd.DataFrame]]:
    yield "ALL", "ALL", frame
    for name in (
        "major_regime", "minor_regime", "session", "volatility_bucket",
        "regime_transition_risk", "event_risk_bucket", "trend_strength_bucket",
        "forecast_disagreement_bucket",
    ):
        if name not in frame:
            continue
        counts = frame[name].fillna("UNKNOWN").astype(str).value_counts()
        for value in counts.index[:12]:
            subset = frame.loc[frame[name].fillna("UNKNOWN").astype(str) == value]
            if not subset.empty:
                yield name.upper(), str(value), subset


def evaluate_conditional_predictive_ability(
    settled_predictions: Any,
    *,
    benchmark_id: str = "canonical",
    minimum_samples: int = MIN_SAMPLES,
    adjacent_stability_required: bool = True,
    source_generation_id: str = "",
) -> dict[str, Any]:
    data = _normalise(settled_predictions)
    evaluated_at = utc_now_iso()
    rows: list[dict[str, Any]] = []
    if data.empty or "model" not in data:
        return {"version": VERSION, "status": "INSUFFICIENT_CONDITIONAL_EVIDENCE", "evaluated_at": evaluated_at, "rows": rows, "promotion_allowed": False}
    models = sorted(set(data["model"].dropna().astype(str)))
    benchmark = benchmark_id if benchmark_id in models else ("canonical" if "canonical" in models else (models[0] if models else benchmark_id))
    challengers = [model for model in models if model != benchmark]
    losses = ("MAE", "DIRECTIONAL_BRIER", "CRPS", "INTERVAL_SCORE", "SYSTEM_LOSS")
    condition_columns = (
        "major_regime", "minor_regime", "session", "volatility_bucket",
        "regime_transition_risk", "event_risk_bucket", "trend_strength_bucket",
        "forecast_disagreement_bucket",
    )
    keys = ["origin_time", "target_time", "horizon"]
    for horizon in HORIZONS:
        horizon_data = data.loc[data["horizon"] == horizon].copy(deep=False)
        if horizon_data.empty:
            continue
        for loss_name in losses:
            horizon_data[f"_loss_{loss_name}"] = _loss(horizon_data, loss_name)
        benchmark_conditions = horizon_data.loc[horizon_data["model"] == benchmark, [*keys, *condition_columns]].drop_duplicates(keys, keep="last").set_index(keys)
        if benchmark_conditions.empty:
            benchmark_conditions = horizon_data[[*keys, *condition_columns]].drop_duplicates(keys, keep="last").set_index(keys)
        # One all-model pivot per horizon/loss, then cheap column projections for
        # each challenger. This avoids repeated sorting/groupby work.
        for loss_name in losses:
            pivot = horizon_data.pivot_table(index=keys, columns="model", values=f"_loss_{loss_name}", aggfunc="first")
            if benchmark not in pivot:
                continue
            available_challengers = [challenger for challenger in challengers if challenger in pivot]
            if not available_challengers:
                continue
            joined = pivot[[benchmark, *available_challengers]].join(benchmark_conditions, how="left")
            for challenger in available_challengers:
                aligned_all = joined[[benchmark, challenger, *condition_columns]].dropna(subset=[benchmark, challenger]).sort_index()
                if aligned_all.empty:
                    continue
                slices: list[tuple[str, str, pd.DataFrame]] = [("ALL", "ALL", aligned_all)]
                for condition_name in condition_columns:
                    values = aligned_all[condition_name].fillna("UNKNOWN").astype(str)
                    known = ~values.str.upper().isin({"", "UNKNOWN", "NAN", "NONE"})
                    if int(known.sum()) < max(4, min(minimum_samples, 12)):
                        continue
                    counts = values.loc[known].value_counts()
                    for condition_value in counts.index[:6]:
                        subset = aligned_all.loc[values == condition_value]
                        if not subset.empty:
                            slices.append((condition_name.upper(), str(condition_value), subset))
                for condition_name, condition_value, aligned in slices:
                    count = int(len(aligned))
                    diff = aligned[benchmark].to_numpy(float) - aligned[challenger].to_numpy(float)
                    mean_a = finite(aligned[benchmark].mean())
                    mean_b = finite(aligned[challenger].mean())
                    mean_diff = finite(np.mean(diff)) if count else None
                    pooled = float(np.std(np.concatenate([aligned[benchmark].to_numpy(float), aligned[challenger].to_numpy(float)]), ddof=1)) if count > 1 else float("nan")
                    effect = None if not np.isfinite(pooled) or pooled <= 1e-15 else float(mean_diff / pooled)
                    statistic, p_value, _ = _hac_mean_test(diff, lag=max(1, horizon - 1)) if count >= 2 else (float("nan"), float("nan"), float("nan"))
                    half = count // 2
                    stable = bool(count >= minimum_samples and half > 0 and np.sign(np.mean(diff[:half])) == np.sign(np.mean(diff[half:])))
                    sufficient = count >= minimum_samples
                    meaningful = effect is not None and abs(effect) >= 0.10
                    if not sufficient:
                        evidence = "INSUFFICIENT_CONDITIONAL_EVIDENCE"
                    elif mean_diff is not None and mean_diff > 0 and p_value <= 0.05 and meaningful and (stable or not adjacent_stability_required):
                        evidence = "CHALLENGER_CONDITIONALLY_BETTER"
                    elif mean_diff is not None and mean_diff < 0 and p_value <= 0.05 and meaningful and (stable or not adjacent_stability_required):
                        evidence = "BENCHMARK_CONDITIONALLY_BETTER"
                    else:
                        evidence = "NO_STABLE_CONDITIONAL_DIFFERENCE"
                    row = {
                        "evaluated_at": evaluated_at,
                        "condition_name": condition_name,
                        "condition_value": condition_value,
                        "horizon": int(horizon),
                        "model_a": benchmark,
                        "model_b": challenger,
                        "loss_name": loss_name,
                        "settled_sample_count": count,
                        "mean_loss_a": mean_a,
                        "mean_loss_b": mean_b,
                        "mean_loss_difference": mean_diff,
                        "effect_size": effect,
                        "test_statistic": finite(statistic),
                        "p_value": finite(p_value),
                        "evidence_status": evidence,
                        "stability_pass": stable,
                        "source_generation_id": str(source_generation_id),
                        "calculation_version": VERSION,
                    }
                    row["evaluation_id"] = "CPA-" + stable_hash({k: v for k, v in row.items() if k != "evaluated_at"})[:24]
                    rows.append(row)
    return {
        "version": VERSION,
        "status": "EVALUATED" if rows else "INSUFFICIENT_CONDITIONAL_EVIDENCE",
        "evaluated_at": evaluated_at,
        "benchmark_id": benchmark,
        "row_count": len(rows),
        "rows": rows,
        "promotion_allowed": False,
        "policy": "Evidence requires sample size, effect size, HAC inference, and adjacent-window stability; p-value alone is never sufficient.",
    }


__all__ = ["VERSION", "evaluate_conditional_predictive_ability"]
