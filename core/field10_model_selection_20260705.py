"""Frozen candidate registration, Model Confidence Set, and chronological splits."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import math

import numpy as np
import pandas as pd

from core.field10_research_common_20260705 import HORIZONS, deterministic_hash, direction_sign

VERSION = "field10-model-selection-20260705-v1"
CANDIDATE_REGISTRY_VERSION = "field10-frozen-candidate-registry-20260705-v1"
CANDIDATE_MODELS: tuple[str, ...] = (
    "protected_production_model",
    "analogue_model",
    "har_h1_model",
    "gas_model",
    "caviar_model",
    "regime_conditioned_model",
    "semivariance_adjusted_model",
    "connectedness_adjusted_model",
)
REGISTERED_SPLITS: tuple[tuple[str, float, float, float], ...] = (
    ("SPLIT_A", 0.45, 0.62, 0.78),
    ("SPLIT_B", 0.50, 0.68, 0.84),
    ("SPLIT_C", 0.55, 0.72, 0.88),
)


def candidate_registry_hash() -> str:
    return deterministic_hash({"version": CANDIDATE_REGISTRY_VERSION, "models": CANDIDATE_MODELS, "splits": REGISTERED_SPLITS})


def _horizon_target(close: pd.Series, horizon: int, sign: int) -> pd.Series:
    return float(sign) * np.log(pd.to_numeric(close, errors="coerce").shift(-horizon) / pd.to_numeric(close, errors="coerce"))


def _historical_predictions(frame: pd.DataFrame, *, bias: str, horizon: int) -> pd.DataFrame:
    """Vectorized causal pseudo-OOS predictions for the frozen candidate registry."""
    sign = direction_sign(bias)
    if sign == 0 or not isinstance(frame, pd.DataFrame) or len(frame) < 200:
        return pd.DataFrame()
    close_series = pd.to_numeric(frame["close"], errors="coerce")
    close = close_series.to_numpy(float)
    hourly_series = np.log(close_series / close_series.shift(1)).replace([np.inf, -np.inf], np.nan)
    hourly = hourly_series.to_numpy(float)
    target_series = _horizon_target(close_series, horizon, sign)
    target = target_series.to_numpy(float)
    momentum6 = hourly_series.rolling(6, min_periods=3).sum().to_numpy(float)
    vol24 = hourly_series.rolling(24, min_periods=12).std(ddof=1).to_numpy(float)
    regime = np.sign(hourly_series.rolling(24, min_periods=12).sum().to_numpy(float))
    times = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    rows: list[dict[str, Any]] = []
    minimum_origin = 160 + horizon
    for origin in range(minimum_origin, len(frame) - horizon):
        last_label_origin = origin - horizon
        hist_start = max(0, last_label_origin - 299)
        historical = target[hist_start:last_label_origin + 1]
        historical = historical[np.isfinite(historical)]
        if historical.size < 120:
            continue
        actual = target[origin]
        current_momentum = momentum6[origin]
        current_vol = vol24[origin]
        if not np.isfinite(actual) or not np.isfinite(current_momentum) or not np.isfinite(current_vol):
            continue
        current_vol = max(float(current_vol), 1e-9)
        mean = float(np.mean(historical))
        median = float(np.median(historical))
        # EWMA over the causal target window, implemented without pandas object churn.
        alpha = 0.06
        ewma = float(historical[0])
        for value in historical[1:]:
            ewma = alpha * float(value) + (1.0 - alpha) * ewma
        q05 = float(np.quantile(historical, 0.05))
        recent_start = max(0, origin - 119)
        recent_hourly = hourly[recent_start:origin + 1]
        recent_hourly = recent_hourly[np.isfinite(recent_hourly)]
        pos_var = float(np.square(recent_hourly[recent_hourly > 0]).sum())
        neg_var = float(np.square(recent_hourly[recent_hourly < 0]).sum())
        imbalance = (pos_var - neg_var) / max(pos_var + neg_var, 1e-12)
        current_regime = np.sign(current_momentum)
        hist_indices = np.arange(hist_start, last_label_origin + 1)
        valid_hist = np.isfinite(target[hist_indices]) & np.isfinite(regime[hist_indices])
        regime_values = target[hist_indices][valid_hist & (regime[hist_indices] == current_regime)]
        regime_mean = float(np.mean(regime_values)) if regime_values.size >= 20 else mean

        analogue_start = max(30, origin - 300)
        analogue_indices = np.arange(analogue_start, max(analogue_start, origin - horizon))
        analogue = median
        if analogue_indices.size:
            valid = (
                np.isfinite(target[analogue_indices])
                & np.isfinite(momentum6[analogue_indices])
                & np.isfinite(vol24[analogue_indices])
                & (vol24[analogue_indices] > 1e-12)
            )
            idx = analogue_indices[valid]
            if idx.size:
                normalized_momentum = momentum6[idx] / np.maximum(vol24[idx], 1e-9)
                current_normalized = current_momentum / current_vol
                distance = np.abs(normalized_momentum - current_normalized) + 0.5 * np.abs(vol24[idx] - current_vol) / current_vol
                k = min(40, idx.size)
                nearest = idx[np.argpartition(distance, k - 1)[:k]] if k else np.array([], dtype=int)
                if nearest.size:
                    analogue = float(np.median(target[nearest]))
        har_point = float(np.clip(np.sign(current_momentum) * current_vol * math.sqrt(horizon) * 0.25 * sign, -0.10, 0.10))
        predictions = {
            "protected_production_model": mean,
            "analogue_model": analogue,
            "har_h1_model": har_point,
            "gas_model": ewma,
            "caviar_model": mean - 0.15 * abs(q05),
            "regime_conditioned_model": regime_mean,
            "semivariance_adjusted_model": mean + 0.10 * imbalance * current_vol * math.sqrt(horizon),
            "connectedness_adjusted_model": mean / (1.0 + 4.0 * current_vol),
        }
        record = {
            "origin_index": origin,
            "origin_time": pd.Timestamp(times.iloc[origin]).isoformat(),
            "outcome_time": pd.Timestamp(times.iloc[origin + horizon]).isoformat(),
            "actual": float(actual), "purge_hours": horizon, "embargo_hours": horizon,
        }
        for model, prediction in predictions.items():
            record[model] = float(prediction)
            record[f"loss::{model}"] = abs(float(actual) - float(prediction))
        rows.append(record)
    return pd.DataFrame(rows)


def chronological_sample_splits(frame: pd.DataFrame, *, bias: str, horizon: int) -> list[dict[str, Any]]:
    predictions = _historical_predictions(frame, bias=bias, horizon=horizon)
    if predictions.empty:
        return []
    n = len(predictions)
    rows: list[dict[str, Any]] = []
    for split_id, train_fraction, validation_fraction, test_fraction in REGISTERED_SPLITS:
        train_end = int(n * train_fraction)
        validation_start = min(n, train_end + horizon)
        validation_end = int(n * validation_fraction)
        test_start = min(n, validation_end + horizon)
        test_end = int(n * test_fraction)
        if test_end - test_start < 12 or validation_end - validation_start < 12:
            continue
        for model in CANDIDATE_MODELS:
            loss_col = f"loss::{model}"
            validation = pd.to_numeric(predictions.iloc[validation_start:validation_end][loss_col], errors="coerce").dropna()
            test = pd.to_numeric(predictions.iloc[test_start:test_end][loss_col], errors="coerce").dropna()
            actual = pd.to_numeric(predictions.iloc[test_start:test_end]["actual"], errors="coerce").dropna()
            prediction = pd.to_numeric(predictions.iloc[test_start:test_end][model], errors="coerce").dropna()
            aligned = pd.concat([actual.rename("actual"), prediction.rename("prediction")], axis=1).dropna()
            if test.empty or aligned.empty:
                continue
            sign_accuracy = float(np.mean(np.sign(aligned["actual"]) == np.sign(aligned["prediction"])))
            calibration_error = abs(sign_accuracy - 0.5)
            net_ev_error = float(abs(aligned["actual"].mean() - aligned["prediction"].mean()))
            rows.append({
                "split_id": split_id, "model_name": model, "horizon": horizon,
                "training_start": predictions.iloc[0]["origin_time"],
                "training_end": predictions.iloc[max(0, train_end - 1)]["origin_time"],
                "validation_start": predictions.iloc[validation_start]["origin_time"],
                "validation_end": predictions.iloc[max(validation_start, validation_end - 1)]["origin_time"],
                "test_start": predictions.iloc[test_start]["origin_time"],
                "test_end": predictions.iloc[max(test_start, test_end - 1)]["outcome_time"],
                "out_of_sample_loss": float(test.mean()),
                "validation_loss": float(validation.mean()),
                "calibration_error": calibration_error,
                "coverage_error": None,
                "net_expected_value_error": net_ev_error,
                "purge_hours": horizon, "embargo_hours": horizon,
                "candidate_registry_hash": candidate_registry_hash(),
                "candidate_registered_before_test": True,
            })
    if not rows:
        return []
    result = pd.DataFrame(rows)
    result["split_rank"] = result.groupby(["split_id", "horizon"])["out_of_sample_loss"].rank(method="min")
    result["split_pass"] = result["split_rank"] <= max(2, len(CANDIDATE_MODELS) // 2)
    return result.to_dict("records")


def aggregate_split_robustness(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not rows:
        return {}
    frame = pd.DataFrame(rows)
    output: dict[str, dict[str, Any]] = {}
    for model, group in frame.groupby("model_name", sort=True):
        losses = pd.to_numeric(group["out_of_sample_loss"], errors="coerce").dropna()
        passes = group["split_pass"].astype(bool)
        if losses.empty:
            continue
        dispersion = float(losses.std(ddof=0))
        median = float(losses.median())
        positive_percentage = float(100.0 * passes.mean())
        score = float(np.clip(100.0 * (1.0 - dispersion / max(median, 1e-12)) * (positive_percentage / 100.0), 0.0, 100.0))
        output[str(model)] = {
            "best_split_loss": float(losses.min()), "median_split_loss": median,
            "worst_split_loss": float(losses.max()), "split_loss_dispersion": dispersion,
            "positive_split_percentage": positive_percentage, "split_robustness_score": score,
            "split_stability_permission": "PASS" if positive_percentage >= 66.0 and score >= 50.0 else "BLOCK",
        }
    return output


def model_confidence_set(
    losses: pd.DataFrame,
    *,
    alpha: float = 0.10,
    bootstrap_draws: int = 500,
    block_length: int = 12,
    seed_key: str = "field10-mcs",
) -> list[dict[str, Any]]:
    """Iterative block-bootstrap MCS over a common settled-loss panel."""
    if not isinstance(losses, pd.DataFrame):
        return []
    work = losses.loc[:, [c for c in CANDIDATE_MODELS if c in losses.columns]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(work) < 60 or work.shape[1] < 2:
        return [{
            "model_name": model, "mean_loss": None, "mcs_membership": False,
            "elimination_round": None, "test_statistic": None, "p_value": None,
            "bootstrap_draws": bootstrap_draws, "block_length": block_length,
            "model_weight": None, "mcs_status": "INSUFFICIENT_SETTLED_OOS_LOSSES",
        } for model in CANDIDATE_MODELS]
    rng = np.random.default_rng(int(deterministic_hash(seed_key)[:16], 16) % (2**32))
    active = list(work.columns)
    eliminated: dict[str, tuple[int, float, float]] = {}
    round_number = 0
    while len(active) > 1:
        round_number += 1
        active_frame = work[active]
        means = active_frame.mean()
        centered = active_frame - means
        grand = float(means.mean())
        deviations = means - grand
        worst = str(deviations.idxmax())
        observed = float(deviations.max())
        bootstrap_stats: list[float] = []
        n = len(active_frame)
        blocks = max(1, math.ceil(n / block_length))
        values = centered.to_numpy(float)
        for _ in range(int(bootstrap_draws)):
            starts = rng.integers(0, max(1, n - block_length + 1), size=blocks)
            indexes = np.concatenate([np.arange(s, min(s + block_length, n)) for s in starts])[:n]
            sample_means = values[indexes].mean(axis=0)
            bootstrap_stats.append(float(np.max(sample_means - sample_means.mean())))
        p_value = float((1 + sum(stat >= observed for stat in bootstrap_stats)) / (len(bootstrap_stats) + 1))
        if p_value >= alpha:
            break
        eliminated[worst] = (round_number, observed, p_value)
        active.remove(worst)
    survivor_losses = work[active].mean()
    # Constrained exponential weighting is stable when losses approach zero and
    # remains valid for registered non-negative loss panels. It replaces unsafe
    # inverse-loss weighting without changing MCS membership.
    loss_values = survivor_losses.to_numpy(float)
    scale = max(float(np.median(np.abs(loss_values - np.median(loss_values)))), float(np.std(loss_values)), 1e-12)
    logits = -(loss_values - float(np.min(loss_values))) / scale
    exp_weights = np.exp(np.clip(logits, -50.0, 0.0))
    weights = exp_weights / max(float(exp_weights.sum()), 1e-12)
    weight_map = dict(zip(active, weights))
    disagreement = float(np.std(loss_values, ddof=0)) if len(loss_values) else None
    rows: list[dict[str, Any]] = []
    for model in work.columns:
        eliminated_data = eliminated.get(model)
        rows.append({
            "model_name": model, "mean_loss": float(work[model].mean()),
            "mean_oos_loss": float(work[model].mean()),
            "loss_difference_from_production": float(work[model].mean() - work[CANDIDATE_MODELS[0]].mean()),
            "model_disagreement": disagreement,
            "mcs_permission": "PASS" if model in active else "BLOCK",
            "weighting_method": "CONSTRAINED_EXPONENTIAL_NON_NEGATIVE",
            "mcs_membership": model in active,
            "elimination_round": None if eliminated_data is None else eliminated_data[0],
            "test_statistic": None if eliminated_data is None else eliminated_data[1],
            "p_value": None if eliminated_data is None else eliminated_data[2],
            "bootstrap_draws": int(bootstrap_draws), "block_length": int(block_length),
            "model_weight": float(weight_map.get(model, 0.0)),
            "mcs_status": "SURVIVES_MCS" if model in active else "ELIMINATED_FROM_MCS",
        })
    return rows


def pseudo_oos_losses(frame: pd.DataFrame, *, bias: str, horizon: int) -> pd.DataFrame:
    predictions = _historical_predictions(frame, bias=bias, horizon=horizon)
    if predictions.empty:
        return pd.DataFrame()
    return predictions[[f"loss::{model}" for model in CANDIDATE_MODELS]].rename(columns={f"loss::{m}": m for m in CANDIDATE_MODELS})


__all__ = [
    "VERSION", "CANDIDATE_REGISTRY_VERSION", "CANDIDATE_MODELS", "REGISTERED_SPLITS",
    "candidate_registry_hash", "chronological_sample_splits", "aggregate_split_robustness",
    "model_confidence_set", "pseudo_oos_losses",
]
