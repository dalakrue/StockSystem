"""Bounded rough-volatility diagnostic from completed-H1 log-volatility increments."""
from __future__ import annotations

from typing import Any, Mapping
import math

import numpy as np
import pandas as pd

from core.quant_research_v4_contract_20260622 import common_result, unavailable
from core.hamilton_regime_research_v4_20260622 import _yang_zhang_variance

METHOD_ID = "ROUGH_VOLATILITY_DIAGNOSTIC"
PAPER_TITLE = "Volatility is Rough"
PAPER_AUTHORS = "Jim Gatheral, Thibault Jaisson, and Mathieu Rosenbaum"
LAGS = (1, 2, 4, 8, 16, 32)


def _robust_slope(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    slopes = []
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            if abs(x[j] - x[i]) > 1e-12:
                slopes.append((y[j] - y[i]) / (x[j] - x[i]))
    slope = float(np.median(slopes)) if slopes else 0.0
    intercept = float(np.median(y - slope * x))
    return slope, intercept


def estimate_roughness(log_vol: np.ndarray, *, q_values: tuple[float, ...] = (1.0, 2.0)) -> dict[str, Any]:
    values = np.asarray(log_vol, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 160:
        raise ValueError("At least 160 finite log-volatility observations are required.")
    estimates = []
    details = []
    for q in q_values:
        xs, ys = [], []
        for lag in LAGS:
            if len(values) <= lag + 20:
                continue
            increments = np.abs(values[lag:] - values[:-lag]) ** q
            moment = float(np.median(increments[np.isfinite(increments)]))
            if moment > 0 and math.isfinite(moment):
                xs.append(math.log(lag)); ys.append(math.log(moment))
        if len(xs) >= 4:
            slope, intercept = _robust_slope(np.asarray(xs), np.asarray(ys))
            h = float(np.clip(slope / q, 0.01, 0.99))
            estimates.append(h)
            fitted = intercept + slope * np.asarray(xs)
            residual = np.asarray(ys) - fitted
            details.append({"q": q, "hurst": h, "residual_mad": float(np.median(np.abs(residual))), "slope": slope})
    if not estimates:
        raise ValueError("Scaling relationship was not estimable.")
    h = float(np.median(estimates))
    # Deterministic rolling-window stability interval, not a parametric fBM CI.
    block_estimates = []
    window = max(128, len(values) // 3)
    step = max(32, window // 3)
    for start in range(0, max(1, len(values) - window + 1), step):
        segment = values[start:start + window]
        if len(segment) < 128:
            continue
        xs, ys = [], []
        for lag in LAGS:
            inc = np.abs(segment[lag:] - segment[:-lag])
            m = float(np.median(inc))
            if m > 0:
                xs.append(math.log(lag)); ys.append(math.log(m))
        if len(xs) >= 4:
            slope, _ = _robust_slope(np.asarray(xs), np.asarray(ys))
            block_estimates.append(float(np.clip(slope, 0.01, 0.99)))
    if len(block_estimates) >= 3:
        low, high = [float(v) for v in np.quantile(block_estimates, [0.10, 0.90])]
        stability = float(max(0.0, 1.0 - np.std(block_estimates) / 0.25))
    else:
        low, high = max(0.01, h - 0.15), min(0.99, h + 0.15)
        stability = 0.25
    return {"estimated_hurst": h, "ci": [low, high], "stability": stability, "q_details": details, "window_estimates": block_estimates}


def run_rough_volatility(frame: pd.DataFrame, identity: Mapping[str, Any]) -> dict[str, Any]:
    n = int(len(frame)) if isinstance(frame, pd.DataFrame) else 0
    minimum = 192
    try:
        variance = _yang_zhang_variance(frame, 24)
        log_vol = np.log(np.sqrt(variance.clip(lower=1e-12))).replace([np.inf, -np.inf], np.nan).dropna().to_numpy(float)
        if len(log_vol) < minimum:
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="STRUCTURE_FUNCTION_DIAGNOSTIC", sample_count=len(log_vol), minimum_required_samples=minimum,
                status="INSUFFICIENT_EVIDENCE", limitations=["At least 192 completed-H1 log-volatility observations are required."])
        estimate = estimate_roughness(log_vol)
        h = estimate["estimated_hurst"]
        if h < 0.20:
            label, fast, slow, decay = "ROUGH_HIGH_MEAN_REVERSION", 12, 96, 0.75
        elif h < 0.35:
            label, fast, slow, decay = "ROUGH", 18, 120, 0.85
        elif h <= 0.60:
            label, fast, slow, decay = "STABLE_SCALING", 24, 168, 1.00
        else:
            label, fast, slow, decay = "PERSISTENT_VOLATILITY", 36, 240, 1.15
        status = "AVAILABLE" if estimate["stability"] >= 0.35 else "INSUFFICIENT_EVIDENCE"
        return common_result(
            identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            exact_or_adaptation="ROBUST_STRUCTURE_FUNCTION_ADAPTATION_NO_FRACTIONAL_SIMULATOR",
            sample_count=len(log_vol), effective_sample_count=len(log_vol), minimum_required_samples=minimum,
            status=status, score=estimate["stability"], confidence=estimate["stability"],
            reliability="STABLE" if estimate["stability"] >= 0.60 else "CAUTION",
            train_start=frame["time"].iloc[-len(log_vol)], train_end=frame["time"].iloc[-1],
            assumptions=["Scaling is estimated from completed-H1 log-volatility structure functions only.", "The estimate selects among pre-registered bounded calibration windows."],
            limitations=["This diagnostic does not assert exact fractional Brownian motion.", "It does not shorten visible 25-day history tables and does not simulate rough stochastic volatility."],
            estimated_hurst=h,
            hurst_confidence_interval=estimate["ci"],
            roughness_label=label,
            estimate_stability=estimate["stability"],
            recommended_fast_window=fast,
            recommended_slow_window=slow,
            volatility_decay_multiplier=decay,
            lag_scales=list(LAGS),
            q_diagnostics=estimate["q_details"],
            visible_history_requirement_modified=False,
        )
    except Exception as exc:
        return unavailable(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            error=exc, minimum_required_samples=minimum, sample_count=n,
            limitations=["Weak or unstable scaling evidence is reported rather than treated as exact rough volatility."])


__all__ = ["run_rough_volatility", "estimate_roughness"]
