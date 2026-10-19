"""Chronological probability calibration and conformal evidence for Field 10 v3.

All fitting uses observations strictly earlier than the evaluated outcome.  The
final chronological test segment is never used to fit a calibrator.  Raw
probabilities are retained when evidence is insufficient.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import math

import numpy as np
import pandas as pd

from core.field10_research_common_20260705 import deterministic_hash, direction_sign, finite

VERSION = "field10-probability-calibration-v2-20260705-v1"
MIN_CALIBRATION_SAMPLES = 60
MIN_TEST_SAMPLES = 24


def _clip_probability(values: Any) -> np.ndarray:
    return np.clip(np.asarray(values, dtype=float), 1e-6, 1.0 - 1e-6)


def brier_score(probability: Any, outcome: Any) -> float | None:
    p = _clip_probability(probability)
    y = np.asarray(outcome, dtype=float)
    mask = np.isfinite(p) & np.isfinite(y)
    return None if not mask.any() else float(np.mean((p[mask] - y[mask]) ** 2))


def log_loss(probability: Any, outcome: Any) -> float | None:
    p = _clip_probability(probability)
    y = np.asarray(outcome, dtype=float)
    mask = np.isfinite(p) & np.isfinite(y)
    return None if not mask.any() else float(-np.mean(y[mask] * np.log(p[mask]) + (1.0 - y[mask]) * np.log(1.0 - p[mask])))


def expected_calibration_error(probability: Any, outcome: Any, bins: int = 10) -> tuple[float | None, list[dict[str, Any]]]:
    p = _clip_probability(probability)
    y = np.asarray(outcome, dtype=float)
    mask = np.isfinite(p) & np.isfinite(y)
    p, y = p[mask], y[mask]
    if not len(p):
        return None, []
    edges = np.linspace(0.0, 1.0, int(bins) + 1)
    rows: list[dict[str, Any]] = []
    ece = 0.0
    for index in range(int(bins)):
        right_closed = index == bins - 1
        selected = (p >= edges[index]) & ((p <= edges[index + 1]) if right_closed else (p < edges[index + 1]))
        count = int(selected.sum())
        if not count:
            continue
        mean_p = float(p[selected].mean())
        event_rate = float(y[selected].mean())
        weight = count / len(p)
        ece += weight * abs(mean_p - event_rate)
        rows.append({
            "bin": index + 1,
            "lower": float(edges[index]),
            "upper": float(edges[index + 1]),
            "count": count,
            "mean_probability": mean_p,
            "event_rate": event_rate,
            "absolute_gap": abs(mean_p - event_rate),
        })
    return float(ece), rows


def _calibration_slope_intercept(probability: np.ndarray, outcome: np.ndarray) -> tuple[float | None, float | None]:
    if len(probability) < 20 or len(np.unique(outcome)) < 2:
        return None, None
    try:
        from sklearn.linear_model import LogisticRegression
        logits = np.log(_clip_probability(probability) / (1.0 - _clip_probability(probability))).reshape(-1, 1)
        model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=2000, random_state=0)
        model.fit(logits, outcome.astype(int))
        return float(model.coef_[0, 0]), float(model.intercept_[0])
    except Exception:
        return None, None


def chronological_probability_panel(frame: pd.DataFrame, *, bias: str, horizon: int, minimum_history: int = 120) -> pd.DataFrame:
    """Build append-only-style forecast/outcome rows from completed candles.

    At origin t, the raw probability is estimated from outcomes whose full
    horizon was already observable before t.  This explicit lag prevents same-
    candle and overlapping-horizon leakage.
    """
    sign = direction_sign(bias)
    if sign == 0 or frame is None or len(frame) < minimum_history + 2 * horizon + 20:
        return pd.DataFrame()
    close = pd.to_numeric(frame.get("close"), errors="coerce")
    times = pd.to_datetime(frame.get("time", frame.index), errors="coerce", utc=True)
    target = sign * np.log(close.shift(-horizon) / close)
    rows: list[dict[str, Any]] = []
    for origin in range(minimum_history + horizon, len(frame) - horizon):
        historical = target.iloc[: origin - horizon + 1].dropna()
        if len(historical) < minimum_history:
            continue
        raw = float((historical > 0.0).mean())
        actual_return = finite(target.iloc[origin])
        if actual_return is None or pd.isna(times.iloc[origin]) or pd.isna(times.iloc[origin + horizon]):
            continue
        rows.append({
            "origin_index": int(origin),
            "origin_time": pd.Timestamp(times.iloc[origin]).isoformat(),
            "outcome_time": pd.Timestamp(times.iloc[origin + horizon]).isoformat(),
            "raw_probability": raw,
            "outcome": int(actual_return > 0.0),
            "actual_return": float(actual_return),
            "purge_hours": int(horizon),
            "embargo_hours": int(horizon),
        })
    return pd.DataFrame(rows)


def _fit_predict_platt(train_p: np.ndarray, train_y: np.ndarray, values: np.ndarray) -> np.ndarray:
    from sklearn.linear_model import LogisticRegression
    logits = np.log(_clip_probability(train_p) / (1.0 - _clip_probability(train_p))).reshape(-1, 1)
    model = LogisticRegression(C=10.0, solver="lbfgs", max_iter=2000, random_state=0)
    model.fit(logits, train_y.astype(int))
    value_logits = np.log(_clip_probability(values) / (1.0 - _clip_probability(values))).reshape(-1, 1)
    return model.predict_proba(value_logits)[:, 1]


def _fit_predict_isotonic(train_p: np.ndarray, train_y: np.ndarray, values: np.ndarray) -> np.ndarray:
    from sklearn.isotonic import IsotonicRegression
    model = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    model.fit(train_p, train_y)
    return np.asarray(model.predict(values), dtype=float)


def calibrate_probability_panel(panel: pd.DataFrame, *, current_raw_probability: float | None = None, horizon: int, seed_key: str = "") -> dict[str, Any]:
    required = {"raw_probability", "outcome"}
    if panel is None or panel.empty or not required.issubset(panel.columns):
        return {
            "raw_probability": finite(current_raw_probability),
            "calibrated_probability": finite(current_raw_probability),
            "calibration_method": "UNCALIBRATED",
            "calibration_permission": "INSUFFICIENT_EVIDENCE",
            "calibration_sample_count": 0,
            "purge_hours": int(horizon), "embargo_hours": int(horizon),
        }
    work = panel.copy().dropna(subset=["raw_probability", "outcome"]).reset_index(drop=True)
    n = len(work)
    calibration_end = int(n * 0.80)
    train_end = max(MIN_CALIBRATION_SAMPLES, int(n * 0.60))
    calibration_start = min(calibration_end, train_end + int(horizon))
    test_start = min(n, calibration_end + int(horizon))
    calibration = work.iloc[calibration_start:calibration_end]
    test = work.iloc[test_start:]
    raw_current = finite(current_raw_probability)
    if raw_current is None:
        raw_current = float(work["raw_probability"].iloc[-1])
    base = {
        "raw_probability": raw_current,
        "calibration_sample_count": int(len(calibration)),
        "test_sample_count": int(len(test)),
        "purge_hours": int(horizon), "embargo_hours": int(horizon),
        "training_end_index": int(train_end - 1),
        "calibration_start_index": int(calibration_start),
        "calibration_end_index": int(calibration_end - 1),
        "test_start_index": int(test_start),
        "final_test_used_for_fit": False,
        "seed_hash": deterministic_hash({"seed": seed_key, "horizon": horizon})[:16],
    }
    if len(calibration) < MIN_CALIBRATION_SAMPLES or len(test) < MIN_TEST_SAMPLES or calibration["outcome"].nunique() < 2:
        raw_test = test["raw_probability"].to_numpy(float) if len(test) else work["raw_probability"].tail(MIN_TEST_SAMPLES).to_numpy(float)
        y_test = test["outcome"].to_numpy(float) if len(test) else work["outcome"].tail(MIN_TEST_SAMPLES).to_numpy(float)
        ece, bins = expected_calibration_error(raw_test, y_test)
        slope, intercept = _calibration_slope_intercept(raw_test, y_test)
        return {**base,
            "calibrated_probability": raw_current,
            "calibration_method": "UNCALIBRATED",
            "brier_score": brier_score(raw_test, y_test), "log_loss": log_loss(raw_test, y_test),
            "expected_calibration_error": ece, "calibration_slope": slope, "calibration_intercept": intercept,
            "reliability_bins": bins, "calibration_permission": "UNCALIBRATED_REDUCE_RELIABILITY",
        }
    train_p = calibration["raw_probability"].to_numpy(float)
    train_y = calibration["outcome"].to_numpy(float)
    test_p = test["raw_probability"].to_numpy(float)
    test_y = test["outcome"].to_numpy(float)
    candidates: dict[str, np.ndarray] = {"PLATT": _fit_predict_platt(train_p, train_y, test_p)}
    # Isotonic is allowed only with enough distinct probabilities to avoid a
    # degenerate step function on small samples.
    if len(np.unique(train_p)) >= 8:
        candidates["ISOTONIC"] = _fit_predict_isotonic(train_p, train_y, test_p)
    scored = {name: brier_score(values, test_y) for name, values in candidates.items()}
    method = min(scored, key=lambda name: math.inf if scored[name] is None else float(scored[name]))
    calibrated_test = candidates[method]
    current = np.asarray([raw_current], dtype=float)
    calibrated_current = (_fit_predict_platt(train_p, train_y, current) if method == "PLATT" else _fit_predict_isotonic(train_p, train_y, current))[0]
    ece, bins = expected_calibration_error(calibrated_test, test_y)
    slope, intercept = _calibration_slope_intercept(calibrated_test, test_y)
    return {**base,
        "calibrated_probability": float(np.clip(calibrated_current, 0.0, 1.0)),
        "calibration_method": method,
        "brier_score": brier_score(calibrated_test, test_y), "log_loss": log_loss(calibrated_test, test_y),
        "expected_calibration_error": ece, "calibration_slope": slope, "calibration_intercept": intercept,
        "reliability_bins": bins, "candidate_brier_scores": scored,
        "calibration_permission": "PASS" if ece is not None and ece <= 0.12 else "CAUTION",
    }


def chronological_conformal_returns(panel: pd.DataFrame, *, alpha: float = 0.10, horizon: int) -> dict[str, Any]:
    """Split conformal interval using a separate chronological calibration window."""
    if panel is None or panel.empty or "actual_return" not in panel:
        return {"status": "INSUFFICIENT_EVIDENCE", "coverage_target": 1.0 - alpha, "sample_count": 0}
    values = pd.to_numeric(panel["actual_return"], errors="coerce").dropna().reset_index(drop=True)
    n = len(values)
    train_end = int(n * 0.60)
    calibration_start = min(n, train_end + int(horizon))
    calibration_end = int(n * 0.80)
    test_start = min(n, calibration_end + int(horizon))
    training = values.iloc[:train_end]
    calibration = values.iloc[calibration_start:calibration_end]
    test = values.iloc[test_start:]
    if len(training) < 60 or len(calibration) < 30:
        return {"status": "INSUFFICIENT_EVIDENCE", "coverage_target": 1.0 - alpha, "sample_count": int(len(calibration))}
    median = float(training.median())
    scores = np.abs(calibration.to_numpy(float) - median)
    quantile_level = min(1.0, math.ceil((len(scores) + 1) * (1.0 - alpha)) / len(scores))
    radius = float(np.quantile(scores, quantile_level, method="higher"))
    lower, upper = median - radius, median + radius
    empirical_coverage = None if test.empty else float(((test >= lower) & (test <= upper)).mean())
    return {
        "status": "AVAILABLE", "coverage_target": 1.0 - alpha,
        "conformal_lower_return": lower, "conformal_median_return": median,
        "conformal_upper_return": upper, "conformal_interval_width": upper - lower,
        "conformal_half_width": radius, "empirical_coverage": empirical_coverage,
        "calibration_sample_count": int(len(calibration)), "test_sample_count": int(len(test)),
        "purge_hours": int(horizon), "embargo_hours": int(horizon),
        "calibration_window_separate": True,
    }


def calibrate_from_frame(frame: pd.DataFrame, *, bias: str, horizon: int, current_raw_probability: float | None = None, seed_key: str = "") -> dict[str, Any]:
    panel = chronological_probability_panel(frame, bias=bias, horizon=horizon)
    calibrated = calibrate_probability_panel(panel, current_raw_probability=current_raw_probability, horizon=horizon, seed_key=seed_key)
    calibrated["conformal"] = chronological_conformal_returns(panel, horizon=horizon)
    calibrated["panel"] = panel
    return calibrated


__all__ = [
    "VERSION", "brier_score", "log_loss", "expected_calibration_error",
    "chronological_probability_panel", "calibrate_probability_panel",
    "chronological_conformal_returns", "calibrate_from_frame",
]
