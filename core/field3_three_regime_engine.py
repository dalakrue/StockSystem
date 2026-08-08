"""Independent multi-symbol, three-standard Field 3 ranking engine.

Each standard is estimated from its own timeframe-aware feature horizon.  The
engine fails closed on missing identity or inadequate observations, never copies
Higher evidence into Lower/Middle, and owns its rank independently of Field 10.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import math
import sqlite3
import warnings

import numpy as np
import pandas as pd

from core.regime_duration_stats_20260729 import completed_regime_run_stats
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
from scipy.stats import norm, t as student_t
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression
from statsmodels.tsa.api import VAR

from core.global_symbol_migration import migrate_global_symbol_schema

try:
    from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
except Exception:  # pragma: no cover
    DEFAULT_DB_PATH = Path("data/multi_symbol_field10_20260701.sqlite3")

STANDARD_ORDER = ("LOWER", "MIDDLE", "HIGHER")
BASE_STRUCTURAL_WEIGHTS = {"LOWER": 0.25, "MIDDLE": 0.35, "HIGHER": 0.40}
TIMEFRAME_MINUTES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H2": 120,
    "H4": 240, "H6": 360, "H8": 480, "H12": 720, "D1": 1440,
}
MIN_MODEL_OBSERVATIONS = 45
VALIDATION_MIN_OBSERVATIONS = 80


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return default if not np.isfinite(out) else out
    except Exception:
        return default


def _clip(value: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(np.clip(_safe_float(value), lo, hi))


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")


def _normalize_timeframe(value: Any) -> str:
    return str(value or "H4").strip().upper().replace("4H", "H4").replace("1H", "H1")


def bars_for_days(timeframe: str, days: float) -> int:
    minutes = TIMEFRAME_MINUTES.get(_normalize_timeframe(timeframe))
    if not minutes:
        raise ValueError(f"UNSUPPORTED_TIMEFRAME:{timeframe}")
    return max(2, int(round(days * 24 * 60 / minutes)))


def standard_windows(timeframe: str) -> dict[str, int]:
    return {
        "LOWER": bars_for_days(timeframe, 1),
        "MIDDLE": bars_for_days(timeframe, 5),
        "HIGHER": bars_for_days(timeframe, 25),
    }


def standardize_candles(frame: Any) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    df = frame.copy()
    rename = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume", "Time": "open_time"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns and v not in df.columns})
    time_col = next((c for c in ("open_time", "time", "datetime", "date", "broker_open_time") if c in df.columns), None)
    if not time_col or not all(c in df.columns for c in ("open", "high", "low", "close")):
        return pd.DataFrame()
    df["open_time"] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    for c in ("open", "high", "low", "close", "volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open_time", "open", "high", "low", "close"])
    df = df.sort_values("open_time").drop_duplicates("open_time", keep="last").reset_index(drop=True)
    if (df[["open", "high", "low", "close"]].le(0)).any().any():
        return pd.DataFrame()
    return df


def candle_hash(frame: pd.DataFrame) -> str:
    if frame.empty:
        return ""
    cols = [c for c in ("open_time", "open", "high", "low", "close", "volume") if c in frame.columns]
    payload = frame[cols].tail(1600).to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%S%z")
    return hashlib.sha256(payload.encode()).hexdigest()


def _data_quality(frame: pd.DataFrame, required: int) -> tuple[float, str, list[str]]:
    reasons: list[str] = []
    if frame.empty:
        return 0.0, "F_MISSING", ["NO_EXACT_SYMBOL_DATA"]
    n = len(frame)
    duplicates = int(frame["open_time"].duplicated().sum())
    invalid = int((frame["high"] < frame[["open", "close", "low"]].max(axis=1)).sum()) + int((frame["low"] > frame[["open", "close", "high"]].min(axis=1)).sum())
    completeness = min(1.0, n / max(required, 1))
    integrity = max(0.0, 1.0 - (duplicates + invalid) / max(n, 1))
    quality = float(np.clip(0.75 * completeness + 0.25 * integrity, 0, 1))
    if n < required:
        reasons.append(f"INSUFFICIENT_BARS:{n}<{required}")
    if duplicates:
        reasons.append(f"DUPLICATE_CANDLES:{duplicates}")
    if invalid:
        reasons.append(f"OHLC_INTEGRITY_ERRORS:{invalid}")
    grade = "A" if quality >= .90 else "B" if quality >= .75 else "C" if quality >= .60 else "D" if quality >= .40 else "F"
    return quality, grade, reasons


def _bocpd_probability(values: np.ndarray, hazard_lambda: float = 100.0, max_run: int = 220) -> tuple[float, list[float]]:
    """Adams-MacKay BOCPD with a Normal-Gamma predictive distribution."""
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 8:
        return 1.0, []
    scale = np.std(x)
    if scale <= 1e-12:
        return 0.0, [0.0] * len(x)
    x = (x - np.mean(x)) / scale
    max_run = min(max_run, len(x))
    hazard = 1.0 / max(2.0, hazard_lambda)
    log_r = np.full(max_run + 1, -np.inf)
    log_r[0] = 0.0
    mu = np.zeros(max_run + 1)
    kappa = np.ones(max_run + 1) * 1e-3
    alpha = np.ones(max_run + 1)
    beta = np.ones(max_run + 1)
    cp_history: list[float] = []
    for value in x:
        active = np.isfinite(log_r)
        dof = 2.0 * alpha[active]
        pred_scale = np.sqrt(beta[active] * (kappa[active] + 1.0) / (alpha[active] * kappa[active]))
        log_pred = student_t.logpdf(value, df=dof, loc=mu[active], scale=np.maximum(pred_scale, 1e-8))
        idx = np.flatnonzero(active)
        new_log = np.full_like(log_r, -np.inf)
        growth_idx = idx[idx + 1 <= max_run]
        if len(growth_idx):
            gp = log_r[growth_idx] + log_pred[: len(growth_idx)] + math.log1p(-hazard)
            new_log[growth_idx + 1] = gp
        cp_terms = log_r[idx] + log_pred + math.log(hazard)
        m = float(np.max(cp_terms))
        new_log[0] = m + math.log(float(np.exp(cp_terms - m).sum()))
        m2 = float(np.max(new_log[np.isfinite(new_log)]))
        norm_const = m2 + math.log(float(np.exp(new_log[np.isfinite(new_log)] - m2).sum()))
        new_log -= norm_const
        cp_history.append(float(np.exp(new_log[0])))
        new_mu = np.zeros_like(mu)
        new_kappa = np.ones_like(kappa) * 1e-3
        new_alpha = np.ones_like(alpha)
        new_beta = np.ones_like(beta)
        for old in growth_idx:
            new = old + 1
            k = kappa[old]
            kp = k + 1.0
            new_mu[new] = (k * mu[old] + value) / kp
            new_kappa[new] = kp
            new_alpha[new] = alpha[old] + 0.5
            new_beta[new] = beta[old] + (k * (value - mu[old]) ** 2) / (2.0 * kp)
        log_r, mu, kappa, alpha, beta = new_log, new_mu, new_kappa, new_alpha, new_beta
    return float(cp_history[-1]), cp_history


def _crps_gaussian(y: np.ndarray, mean: np.ndarray, sigma: np.ndarray) -> float:
    sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-9)
    z = (np.asarray(y) - np.asarray(mean)) / sigma
    values = sigma * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / math.sqrt(math.pi))
    return float(np.nanmean(values))


def _calibration_error(prob: np.ndarray, outcome: np.ndarray, bins: int = 8) -> float:
    prob = np.asarray(prob, dtype=float)
    outcome = np.asarray(outcome, dtype=float)
    if len(prob) == 0:
        return float("nan")
    edges = np.linspace(0, 1, bins + 1)
    total = len(prob)
    error = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (prob >= lo) & (prob < hi if hi < 1 else prob <= hi)
        if mask.any():
            error += mask.mean() * abs(float(prob[mask].mean()) - float(outcome[mask].mean()))
    return float(error)


def _block_bootstrap_pvalue(returns: np.ndarray, *, seed: int = 20260722, samples: int = 400) -> float | str:
    values = np.asarray(returns, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < VALIDATION_MIN_OBSERVATIONS:
        return "NOT_TESTED_INSUFFICIENT_SAMPLE"
    observed = float(values.mean())
    centered = values - observed
    block = max(4, int(round(len(values) ** (1 / 3))))
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(samples):
        draw: list[float] = []
        while len(draw) < len(values):
            start = int(rng.integers(0, max(1, len(values) - block + 1)))
            draw.extend(centered[start:start + block].tolist())
        stats.append(float(np.mean(draw[: len(values)])))
    return float((1 + sum(s >= observed for s in stats)) / (samples + 1))


def _deflated_sharpe(returns: np.ndarray, trials: int = 3) -> float | str:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < VALIDATION_MIN_OBSERVATIONS or np.std(r, ddof=1) <= 1e-12:
        return "NOT_TESTED_INSUFFICIENT_SAMPLE"
    sr = float(np.mean(r) / np.std(r, ddof=1) * math.sqrt(252))
    skew = float(pd.Series(r).skew())
    kurt = float(pd.Series(r).kurt() + 3.0)
    sr_std = math.sqrt(max(1e-12, (1 - skew * sr + ((kurt - 1) / 4) * sr * sr) / (len(r) - 1)))
    expected_max = norm.ppf(1 - 1 / max(trials, 2)) * sr_std
    return float(norm.cdf((sr - expected_max) / sr_std))


@dataclass
class StandardEvidence:
    standard: str
    window_bars: int
    regime_state: str
    bias: str
    posterior_probability: float
    persistence_probability: float
    expected_duration: float
    regime_age: int
    changepoint_probability: float
    transition_risk: float
    calibrated_reliability: float
    signed_evidence_score: float
    sample_count: int
    data_quality_grade: str
    latest_completed_candle: str
    evidence_hash: str
    payload: dict[str, Any]


def _fit_standard(frame: pd.DataFrame, timeframe: str, standard: str, window_bars: int) -> StandardEvidence:
    if not isinstance(frame, pd.DataFrame) or frame.empty or not {"open_time", "close"}.issubset(frame.columns):
        payload = {
            "status": "BLOCKED", "block_reasons": ["NO_EXACT_SYMBOL_DATA"],
            "feature_window_bars": window_bars, "estimation_bars": 0,
            "validation": {"status": "NOT_TESTED_INSUFFICIENT_SAMPLE"},
        }
        h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return StandardEvidence(standard, window_bars, "UNAVAILABLE", "BLOCKED", 0, 0, 0, 0, 1, 1, 0, 0, 0, "F", "", h, payload)
    # Estimation history is longer than the structural feature window, while the
    # current evidence and weighting are calculated from the exact standard.
    fit_bars = max(MIN_MODEL_OBSERVATIONS, min(len(frame), max(window_bars * 6, 90)))
    sample = frame.tail(fit_bars).copy()
    quality, grade, quality_reasons = _data_quality(sample, max(MIN_MODEL_OBSERVATIONS, min(window_bars * 2, 180)))
    latest = str(sample["open_time"].iloc[-1].isoformat()) if not sample.empty else ""
    returns = np.log(sample["close"]).diff().dropna().to_numpy(dtype=float)
    if len(returns) < MIN_MODEL_OBSERVATIONS or quality < 0.40:
        payload = {
            "status": "BLOCKED", "block_reasons": quality_reasons or ["INSUFFICIENT_MODEL_SAMPLE"],
            "feature_window_bars": window_bars, "estimation_bars": fit_bars,
            "validation": {"status": "NOT_TESTED_INSUFFICIENT_SAMPLE"},
        }
        h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return StandardEvidence(standard, window_bars, "UNAVAILABLE", "BLOCKED", 0, 0, 0, 0, 1, 1, 0, 0, len(returns), grade, latest, h, payload)

    # The standard controls decay and feature emphasis independently.
    span = max(3, window_bars)
    series = pd.Series(returns)
    weighted = series.ewm(span=span, adjust=False).mean().to_numpy() + (series - series.rolling(span, min_periods=2).mean()).fillna(0).to_numpy() * 0.25
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = MarkovRegression(weighted, k_regimes=3, trend="c", switching_variance=True)
            result = model.fit(disp=False, maxiter=220, em_iter=12, search_reps=3)
        probs = np.asarray(result.smoothed_marginal_probabilities, dtype=float)
        if probs.ndim != 2 or probs.shape[1] != 3:
            raise RuntimeError("INVALID_HAMILTON_POSTERIOR_SHAPE")
    except Exception as exc:
        payload = {
            "status": "BLOCKED", "block_reasons": [f"HAMILTON_FIT_FAILED:{type(exc).__name__}"],
            "feature_window_bars": window_bars, "estimation_bars": fit_bars,
            "validation": {"status": "NOT_TESTED_MODEL_FAILURE"},
        }
        h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return StandardEvidence(standard, window_bars, "UNAVAILABLE", "BLOCKED", 0, 0, 0, 0, 1, 1, 0, 0, len(returns), grade, latest, h, payload)

    states = probs.argmax(axis=1)
    state_means = np.array([weighted[states == i].mean() if np.any(states == i) else 0.0 for i in range(3)])
    order = np.argsort(state_means)
    labels = {int(order[0]): "BEAR", int(order[1]): "NEUTRAL", int(order[2]): "BULL"}
    current_state = int(states[-1])
    regime_state = labels[current_state]
    posterior = float(probs[-1, current_state])
    trans_counts = np.ones((3, 3), dtype=float)
    for a, b in zip(states[:-1], states[1:]):
        trans_counts[int(a), int(b)] += 1
    transition = trans_counts / trans_counts.sum(axis=1, keepdims=True)
    persistence = float(transition[current_state, current_state])
    expected_duration = float(1.0 / max(1e-6, 1.0 - persistence))
    completed_run_stats = completed_regime_run_stats(states.tolist(), current_value=current_state)
    age = 1
    for value in states[-2::-1]:
        if int(value) != current_state:
            break
        age += 1
    cp_prob, cp_history = _bocpd_probability(weighted[-min(300, len(weighted)):], hazard_lambda=max(30, window_bars * 2))
    transition_risk = _clip(0.55 * cp_prob + 0.45 * (1.0 - persistence))
    direction = -1.0 if regime_state == "BEAR" else 1.0 if regime_state == "BULL" else 0.0

    # One-step probability and proper scores are generated from saved posterior
    # evidence, not placeholders.
    state_positive = (state_means > 0).astype(float)
    p_up = np.clip((probs[:-1] * state_positive).sum(axis=1), 1e-6, 1 - 1e-6)
    actual_up = (weighted[1:] > 0).astype(float)
    brier = float(np.mean((p_up - actual_up) ** 2))
    log_score = float(-np.mean(actual_up * np.log(p_up) + (1 - actual_up) * np.log(1 - p_up)))
    pred_mean = np.array([state_means[int(s)] for s in states[:-1]])
    state_std = np.array([np.std(weighted[states == i]) if np.sum(states == i) > 2 else np.std(weighted) for i in range(3)])
    pred_sigma = np.array([max(1e-8, state_std[int(s)]) for s in states[:-1]])
    crps = _crps_gaussian(weighted[1:], pred_mean, pred_sigma)
    calibration_error = _calibration_error(p_up, actual_up)

    conformal_status: str | float = "NOT_TESTED_INSUFFICIENT_SAMPLE"
    coverage: str | float = "NOT_TESTED_INSUFFICIENT_SAMPLE"
    interval_width: str | float = "NOT_TESTED_INSUFFICIENT_SAMPLE"
    if len(weighted) >= VALIDATION_MIN_OBSERVATIONS:
        split = max(40, int(len(weighted) * .75))
        residuals = np.abs(weighted[1:split] - pred_mean[: split - 1])
        q = float(np.quantile(residuals, min(0.99, math.ceil((len(residuals) + 1) * .90) / len(residuals))))
        test_res = np.abs(weighted[split:] - pred_mean[split - 1:])
        coverage = float(np.mean(test_res <= q)) if len(test_res) else "NOT_TESTED_INSUFFICIENT_SAMPLE"
        interval_width = float(2 * q)
        conformal_status = "TESTED"

    strategy_returns = direction * weighted[1:] if direction else np.zeros_like(weighted[1:])
    spa = _block_bootstrap_pvalue(strategy_returns)
    dsr = _deflated_sharpe(strategy_returns)
    regime_stability = float(np.mean(states[1:] == states[:-1]))
    quality_component = quality
    score_component = float(np.clip(1.0 - (0.45 * brier + 0.20 * min(log_score, 2) / 2 + 0.20 * min(calibration_error, 1) + 0.15 * min(crps / max(np.std(weighted), 1e-8), 1)), 0, 1))
    conformal_component = float(coverage) if isinstance(coverage, float) else 0.5
    reliability = _clip(0.28 * posterior + 0.22 * persistence + 0.22 * score_component + 0.18 * quality_component + 0.10 * conformal_component)
    signed_score = direction * posterior * persistence * reliability * (1.0 - transition_risk) * quality
    bias = "BUY" if direction > 0 else "SELL" if direction < 0 else "NEUTRAL"
    posterior_payload = {labels[i]: float(probs[-1, i]) for i in range(3)}
    payload = {
        "status": "READY", "model": "Hamilton MarkovRegression(k_regimes=3,switching_variance=True)",
        "feature_window_bars": window_bars, "estimation_bars": fit_bars,
        "posterior_probabilities": posterior_payload,
        "transition_matrix": transition.tolist(), "state_means": state_means.tolist(),
        "expected_regime_duration": expected_duration,
        "average_regime_candle_count_before_change": completed_run_stats.get("average"),
        "completed_regime_run_count": int(completed_run_stats.get("count") or 0),
        "average_regime_duration_basis": completed_run_stats.get("basis"),
        "change_probability_history": cp_history[-60:],
        "feature_evidence": {
            "recent_log_return": float(np.sum(returns[-max(2, window_bars):])),
            "recent_realized_volatility": float(np.std(returns[-max(2, window_bars):]) * math.sqrt(max(2, window_bars))),
            "weighted_return_mean": float(np.mean(weighted[-max(2, window_bars):])),
            "weighted_return_slope": float(np.polyfit(np.arange(min(window_bars, len(weighted))), weighted[-min(window_bars, len(weighted)):], 1)[0]) if min(window_bars, len(weighted)) >= 3 else 0.0,
        },
        "validation": {
            "brier_score": brier, "logarithmic_score": log_score, "crps": crps,
            "calibration_error": calibration_error, "conformal_status": conformal_status,
            "conformal_coverage": coverage, "conformal_interval_width": interval_width,
            "single_model_mean_bootstrap_pvalue": spa, "deflated_sharpe_probability": dsr,
            "hansen_spa_pvalue": "NOT_TESTED_REQUIRES_CROSS_MODEL_RETURN_PANEL",
            "model_confidence_set": "NOT_TESTED_REQUIRES_CROSS_MODEL_LOSS_PANEL",
            "white_reality_check": "NOT_TESTED_REQUIRES_CROSS_MODEL_RETURN_PANEL",
            "pbo_cscv": "NOT_TESTED_REQUIRES_CROSS_MODEL_RETURN_PANEL",
            "rank_stability": "NOT_TESTED_NO_PRIOR_GENERATION",
            "turnover": "NOT_TESTED_NO_PRIOR_GENERATION",
            "regime_stability": regime_stability,
        },
        "validation_samples": {
            "brier_loss": ((p_up - actual_up) ** 2)[-500:].tolist(),
            "strategy_returns": strategy_returns[-500:].tolist(),
            "signal_score": ((p_up - 0.5) * 2.0)[-500:].tolist(),
            "actual_return": weighted[1:][-500:].tolist(),
        },
        "data_quality": {"score": quality, "grade": grade, "reasons": quality_reasons},
    }
    evidence_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return StandardEvidence(
        standard, window_bars, regime_state, bias, posterior, persistence, expected_duration, age,
        cp_prob, transition_risk, reliability, signed_score, len(returns), grade, latest, evidence_hash, payload,
    )


def _aligned_returns(frames: Mapping[str, pd.DataFrame], max_rows: int = 1200) -> pd.DataFrame:
    series = []
    for symbol, frame in frames.items():
        df = standardize_candles(frame)
        if df.empty:
            continue
        s = pd.Series(np.log(df["close"]).diff().to_numpy(), index=df["open_time"], name=symbol).dropna()
        series.append(s.tail(max_rows))
    if not series:
        return pd.DataFrame()
    return pd.concat(series, axis=1, join="inner").dropna()


def _dcc_and_hrp(frames: Mapping[str, pd.DataFrame]) -> dict[str, dict[str, Any]]:
    ret = _aligned_returns(frames)
    symbols = list(frames)
    default = {s: {"dcc_penalty": 0.0, "hrp_cluster": 0, "duplicate_penalty": 0.0, "max_dynamic_correlation": 0.0} for s in symbols}
    if ret.shape[0] < 30 or ret.shape[1] < 2:
        return default
    ret = ret.replace([np.inf, -np.inf], np.nan).dropna()
    z = (ret - ret.ewm(span=30, adjust=False).mean()) / ret.ewm(span=30, adjust=False).std().replace(0, np.nan)
    z = z.dropna()
    if z.shape[0] < 20:
        return default
    s_mat = np.corrcoef(z.to_numpy().T)
    q = np.nan_to_num(s_mat, nan=0.0)
    a, b = 0.03, 0.95
    for row in z.to_numpy():
        outer = np.outer(row, row)
        q = (1 - a - b) * s_mat + a * outer + b * q
    diag = np.sqrt(np.maximum(np.diag(q), 1e-12))
    corr = np.clip(q / np.outer(diag, diag), -1, 1)
    np.fill_diagonal(corr, 1.0)
    distance = np.sqrt(np.clip((1 - corr) / 2, 0, 1))
    try:
        link = linkage(squareform(distance, checks=False), method="ward")
        clusters = fcluster(link, t=0.55, criterion="distance")
    except Exception:
        clusters = np.arange(1, len(ret.columns) + 1)
    result = dict(default)
    for i, symbol in enumerate(ret.columns):
        peers = np.delete(np.abs(corr[i]), i)
        max_corr = float(peers.max()) if len(peers) else 0.0
        cluster_size = int(np.sum(clusters == clusters[i]))
        dcc_penalty = _clip(max(0.0, (max_corr - 0.55) / 0.45))
        duplicate = _clip(dcc_penalty * max(1.0, cluster_size - 1) / max(1, len(ret.columns) - 1))
        result[symbol] = {"dcc_penalty": dcc_penalty, "hrp_cluster": int(clusters[i]), "duplicate_penalty": duplicate, "max_dynamic_correlation": max_corr}
    return result


def _generalized_fevd_spillover(frames: Mapping[str, pd.DataFrame], horizon: int = 10) -> dict[str, dict[str, float]]:
    ret = _aligned_returns(frames, max_rows=700)
    out = {s: {"spillover_to": 0.0, "spillover_from": 0.0, "net_spillover": 0.0, "spillover_penalty": 0.0} for s in frames}
    if ret.shape[0] < max(80, ret.shape[1] * 8) or ret.shape[1] < 2:
        return out
    # Keep the VAR estimable and numerically stable.
    ret = ret.iloc[:, : min(8, ret.shape[1])]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = VAR(ret).fit(maxlags=1, trend="c")
        a = np.asarray(fit.coefs[0], dtype=float)
        sigma = np.asarray(fit.sigma_u, dtype=float)
        n = a.shape[0]
        phi = [np.eye(n)]
        for _ in range(1, horizon):
            phi.append(phi[-1] @ a)
        theta = np.zeros((n, n), dtype=float)
        for i in range(n):
            denom = 0.0
            numer = np.zeros(n)
            for ph in phi:
                denom += float(ph[i, :] @ sigma @ ph[i, :].T)
                for j in range(n):
                    numer[j] += float((ph[i, :] @ sigma[:, j]) ** 2 / max(sigma[j, j], 1e-12))
            theta[i, :] = numer / max(denom, 1e-12)
        theta = theta / np.maximum(theta.sum(axis=1, keepdims=True), 1e-12)
        from_vals = theta.sum(axis=1) - np.diag(theta)
        to_vals = theta.sum(axis=0) - np.diag(theta)
        for i, symbol in enumerate(ret.columns):
            from_v = float(from_vals[i] / max(n - 1, 1))
            to_v = float(to_vals[i] / max(n - 1, 1))
            out[symbol] = {
                "spillover_to": to_v, "spillover_from": from_v, "net_spillover": to_v - from_v,
                "spillover_penalty": _clip(from_v),
            }
    except Exception:
        pass
    return out


def _walk_forward_policy(evidence: Mapping[str, StandardEvidence]) -> dict[str, Any]:
    """Select standard weights and decision threshold by expanding-window OOS validation."""
    if any(s not in evidence or evidence[s].payload.get("status") != "READY" for s in STANDARD_ORDER):
        return {"validated": False, "reason": "NOT_TESTED_ONE_OR_MORE_STANDARDS_NOT_READY"}
    signals = [np.asarray(evidence[s].payload.get("validation_samples", {}).get("signal_score") or [], dtype=float) for s in STANDARD_ORDER]
    actuals = [np.asarray(evidence[s].payload.get("validation_samples", {}).get("actual_return") or [], dtype=float) for s in STANDARD_ORDER]
    n = min([len(x) for x in signals + actuals] or [0])
    if n < 120:
        return {"validated": False, "reason": "NOT_TESTED_INSUFFICIENT_WALK_FORWARD_SAMPLE", "observations": n}
    x = np.column_stack([v[-n:] for v in signals])
    y = np.nanmean(np.column_stack([v[-n:] for v in actuals]), axis=1)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        return {"validated": False, "reason": "NOT_TESTED_NONFINITE_WALK_FORWARD_PANEL", "observations": n}
    folds=[]
    for train_frac, test_frac in ((.50,.15),(.65,.15),(.80,.20)):
        train_end=int(n*train_frac); test_end=min(n,train_end+max(20,int(n*test_frac)))
        if test_end-train_end>=20: folds.append((train_end,test_end))
    if len(folds)<2:
        return {"validated": False, "reason": "NOT_TESTED_INSUFFICIENT_WALK_FORWARD_FOLDS", "observations": n}
    weights=[]
    for a in np.arange(0,1.001,.25):
        for b in np.arange(0,1.001-a,.25):
            c=1-a-b
            if c>=-1e-9: weights.append(np.array([a,b,max(0.0,c)],dtype=float))
    thresholds=np.arange(.05,.351,.05)
    best=None
    for w in weights:
        signal=x@w
        for threshold in thresholds:
            fold_scores=[]; trades=0; turnover=[]
            for start,end in folds:
                pos=np.where(np.abs(signal[start:end])>=threshold,np.sign(signal[start:end]),0.0)
                pnl=pos*y[start:end]; active=pos!=0; trades += int(active.sum())
                if active.sum()<5:
                    fold_scores.append(-10.0); continue
                vol=float(np.std(pnl,ddof=1)); sharpe=float(np.mean(pnl)/max(vol,1e-12)*math.sqrt(len(pnl)))
                turn=float(np.mean(np.abs(np.diff(pos)))) if len(pos)>1 else 0.0
                turnover.append(turn); fold_scores.append(sharpe-0.05*turn)
            objective=float(np.mean(fold_scores))
            candidate=(objective,-threshold,tuple(w.tolist()),trades,float(np.mean(turnover) if turnover else 0.0))
            if best is None or candidate>best: best=candidate
    if best is None or best[0] <= -5:
        return {"validated": False, "reason": "NOT_TESTED_NO_VALID_WALK_FORWARD_POLICY", "observations": n}
    chosen=np.asarray(best[2],dtype=float)
    reliabilities=np.array([max(0.0,evidence[s].calibrated_reliability) for s in STANDARD_ORDER])
    effective=chosen*reliabilities
    if effective.sum()<=0:
        return {"validated": False, "reason": "NOT_TESTED_ZERO_VALIDATED_RELIABILITY", "observations": n}
    effective=effective/effective.sum()
    return {"validated": True,"method":"EXPANDING_WINDOW_GRID_SEARCH","observations":n,
            "folds":[{"train_end":a,"test_end":b} for a,b in folds],
            "weights":{s:float(effective[i]) for i,s in enumerate(STANDARD_ORDER)},
            "raw_policy_weights":{s:float(chosen[i]) for i,s in enumerate(STANDARD_ORDER)},
            "decision_threshold":float(np.clip(-best[1],.02,.35)),"objective":float(best[0]),
            "oos_trades":int(best[3]),"turnover":float(best[4])}


def _moving_block_sample(matrix: np.ndarray, rng: np.random.Generator, block: int) -> np.ndarray:
    n = matrix.shape[0]
    pieces: list[np.ndarray] = []
    while sum(len(x) for x in pieces) < n:
        start = int(rng.integers(0, max(1, n - block + 1)))
        pieces.append(matrix[start:start + block])
    return np.concatenate(pieces, axis=0)[:n]


def _cross_model_validation(evidence: Mapping[str, StandardEvidence]) -> dict[str, Any]:
    """Run cross-model tests only when synchronized loss/return panels exist.

    Implementations are deterministic moving-block-bootstrap versions of Hansen
    SPA, White Reality Check and an iterative loss-based Model Confidence Set,
    plus CSCV/PBO across the three independent standards.
    """
    ready = [evidence[s] for s in STANDARD_ORDER if s in evidence and evidence[s].payload.get("status") == "READY"]
    base = {
        "hansen_spa": "NOT_TESTED_INSUFFICIENT_SAMPLE",
        "model_confidence_set": "NOT_TESTED_INSUFFICIENT_SAMPLE",
        "white_reality_check": "NOT_TESTED_INSUFFICIENT_SAMPLE",
        "pbo_cscv": "NOT_TESTED_INSUFFICIENT_CONFIGURATIONS",
    }
    if len(ready) < 3:
        return base
    return_samples = [np.asarray(e.payload.get("validation_samples", {}).get("strategy_returns") or [], dtype=float) for e in ready]
    loss_samples = [np.asarray(e.payload.get("validation_samples", {}).get("brier_loss") or [], dtype=float) for e in ready]
    n = min([len(x) for x in return_samples + loss_samples] or [0])
    if n < VALIDATION_MIN_OBSERVATIONS:
        return base
    returns = np.column_stack([x[-n:] for x in return_samples])
    losses = np.column_stack([x[-n:] for x in loss_samples])
    if not np.isfinite(returns).all() or not np.isfinite(losses).all():
        return {k: "NOT_TESTED_NONFINITE_SYNCHRONIZED_PANEL" for k in base}
    names = [e.standard for e in ready]
    rng = np.random.default_rng(20260722)
    block = max(4, int(round(n ** (1 / 3))))
    boot = 400

    # White Reality Check: max mean performance under jointly centered null.
    observed_rc = float(np.max(returns.mean(axis=0)))
    centered_returns = returns - returns.mean(axis=0, keepdims=True)
    rc_stats = np.array([_moving_block_sample(centered_returns, rng, block).mean(axis=0).max() for _ in range(boot)])
    rc_p = float((1 + np.sum(rc_stats >= observed_rc)) / (boot + 1))

    # Hansen SPA: studentized max with conservative recentering of weak models.
    means = returns.mean(axis=0)
    std_err = returns.std(axis=0, ddof=1) / math.sqrt(n)
    std_err = np.maximum(std_err, 1e-12)
    observed_spa = float(np.max(means / std_err))
    recenter = np.minimum(means, 0.0)
    spa_null = returns - means + recenter
    spa_stats = []
    for _ in range(boot):
        draw = _moving_block_sample(spa_null, rng, block)
        draw_se = np.maximum(draw.std(axis=0, ddof=1) / math.sqrt(n), 1e-12)
        spa_stats.append(float(np.max(draw.mean(axis=0) / draw_se)))
    spa_p = float((1 + np.sum(np.asarray(spa_stats) >= observed_spa)) / (boot + 1))

    # Iterative MCS at alpha=0.10 using maximum pairwise loss-difference statistic.
    active = list(range(len(names)))
    elimination: list[dict[str, Any]] = []
    while len(active) > 1:
        panel = losses[:, active]
        avg = panel.mean(axis=0)
        diffs = panel[:, :, None] - panel[:, None, :]
        mean_diff = diffs.mean(axis=0)
        se_diff = np.maximum(diffs.std(axis=0, ddof=1) / math.sqrt(n), 1e-12)
        observed = float(np.max(np.abs(mean_diff / se_diff)))
        centered = diffs - mean_diff[None, :, :]
        stats = []
        for _ in range(250):
            draw = _moving_block_sample(centered.reshape(n, -1), rng, block).reshape(n, len(active), len(active))
            draw_se = np.maximum(draw.std(axis=0, ddof=1) / math.sqrt(n), 1e-12)
            stats.append(float(np.max(np.abs(draw.mean(axis=0) / draw_se))))
        p_value = float((1 + np.sum(np.asarray(stats) >= observed)) / 251)
        if p_value >= 0.10:
            elimination.append({"remaining": [names[i] for i in active], "p_value": p_value, "action": "STOP"})
            break
        worst_local = int(np.argmax(avg))
        removed = active.pop(worst_local)
        elimination.append({"removed": names[removed], "p_value": p_value, "action": "ELIMINATE_WORST_LOSS"})

    # CSCV/PBO: 8 contiguous blocks, train on 4 and evaluate selected model OOS.
    pbo: float | str = "NOT_TESTED_INSUFFICIENT_SAMPLE"
    logits: list[float] = []
    if n >= 160:
        import itertools
        blocks = [idx for idx in np.array_split(np.arange(n), 8) if len(idx)]
        for train_blocks in itertools.combinations(range(8), 4):
            train_idx = np.concatenate([blocks[i] for i in train_blocks])
            test_idx = np.concatenate([blocks[i] for i in range(8) if i not in train_blocks])
            train = returns[train_idx]
            test = returns[test_idx]
            train_sr = train.mean(axis=0) / np.maximum(train.std(axis=0, ddof=1), 1e-12)
            chosen = int(np.argmax(train_sr))
            test_sr = test.mean(axis=0) / np.maximum(test.std(axis=0, ddof=1), 1e-12)
            rank = int(np.argsort(np.argsort(test_sr))[chosen]) + 1  # 1=worst, M=best
            percentile = (rank - 0.5) / len(names)
            logits.append(float(math.log(percentile / max(1e-12, 1 - percentile))))
        pbo = float(np.mean(np.asarray(logits) <= 0.0)) if logits else "NOT_TESTED_INSUFFICIENT_SAMPLE"

    return {
        "hansen_spa": {"method": "HANSEN_SPA_MOVING_BLOCK_BOOTSTRAP", "p_value": spa_p,
                       "observed_max_studentized_mean": observed_spa, "models": names, "observations": n},
        "white_reality_check": {"method": "WHITE_REALITY_CHECK_MOVING_BLOCK_BOOTSTRAP", "p_value": rc_p,
                                "observed_max_mean": observed_rc, "models": names, "observations": n},
        "model_confidence_set": {"method": "ITERATIVE_MAX_LOSS_DIFFERENCE_MCS", "alpha": 0.10,
                                 "included": [names[i] for i in active], "elimination_path": elimination,
                                 "observations": n},
        "pbo_cscv": {"method": "CSCV_8_BLOCKS", "pbo": pbo, "partitions": len(logits),
                     "models": names, "observations": n} if not isinstance(pbo, str) else pbo,
    }

def build_field3_three_regime_ranking(
    frames: Mapping[str, pd.DataFrame],
    *,
    timeframe: str,
    parent_run_id: str,
    generation: int,
    snapshot_hash: str,
    expected_candle: str | None = None,
    providers: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (main ranking, standard evidence, research validation)."""
    tf = _normalize_timeframe(timeframe)
    windows = standard_windows(tf)
    standardized = {_normalize_symbol(s): standardize_candles(f) for s, f in frames.items()}
    dcc = _dcc_and_hrp(standardized)
    spill = _generalized_fevd_spillover(standardized)
    rank_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    for symbol, frame in standardized.items():
        provider = dict((providers or {}).get(symbol) or {})
        exact_hash = candle_hash(frame)
        actual_candle = str(frame["open_time"].iloc[-1].isoformat()) if not frame.empty else ""
        identity_errors: list[str] = []
        if expected_candle and actual_candle and actual_candle != str(expected_candle):
            identity_errors.append(f"COMPLETED_CANDLE_MISMATCH:{actual_candle}!={expected_candle}")
        if provider.get("source_data_hash") and str(provider.get("source_data_hash")) != exact_hash:
            identity_errors.append("SOURCE_DATA_HASH_MISMATCH")
        evidence: dict[str, StandardEvidence] = {}
        if identity_errors:
            for standard in STANDARD_ORDER:
                payload = {"status": "BLOCKED", "block_reasons": identity_errors, "validation": {"status": "NOT_TESTED_IDENTITY_FAILURE"}}
                h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                evidence[standard] = StandardEvidence(standard, windows[standard], "UNAVAILABLE", "BLOCKED", 0, 0, 0, 0, 1, 1, 0, 0, len(frame), "F", actual_candle, h, payload)
        else:
            for standard in STANDARD_ORDER:
                evidence[standard] = _fit_standard(frame, tf, standard, windows[standard])

        ready = [e for e in evidence.values() if e.bias in ("BUY", "SELL", "NEUTRAL") and e.payload.get("status") == "READY"]
        walk_forward_policy = _walk_forward_policy(evidence)
        if walk_forward_policy.get("validated"):
            weights = dict(walk_forward_policy["weights"])
            weight_sum = sum(weights.values())
        else:
            validated_weights = {
                standard: BASE_STRUCTURAL_WEIGHTS[standard] * max(0.0, evidence[standard].calibrated_reliability)
                for standard in STANDARD_ORDER
            }
            weight_sum = sum(validated_weights.values())
            weights = {s: (validated_weights[s] / weight_sum if weight_sum > 0 else 0.0) for s in STANDARD_ORDER}
        signed = np.array([evidence[s].signed_evidence_score for s in STANDARD_ORDER], dtype=float)
        dirs = np.sign(signed)
        nonzero = dirs[dirs != 0]
        agreement = float(abs(np.average(dirs, weights=[weights[s] for s in STANDARD_ORDER])) if weight_sum > 0 else 0.0)
        directional_conflict = bool(len(set(nonzero.tolist())) > 1) if len(nonzero) else False
        conflict_penalty = _clip(1.0 - agreement) if directional_conflict else 0.0
        correlation_penalty = _clip(dcc.get(symbol, {}).get("dcc_penalty", 0.0) + dcc.get(symbol, {}).get("duplicate_penalty", 0.0) * 0.5)
        spillover_penalty = _clip(spill.get(symbol, {}).get("spillover_penalty", 0.0))
        composite = float(sum(weights[s] * evidence[s].signed_evidence_score for s in STANDARD_ORDER)) if weight_sum > 0 else 0.0
        calibrated_reliability = float(sum(weights[s] * evidence[s].calibrated_reliability for s in STANDARD_ORDER)) if weight_sum > 0 else 0.0
        changepoint = float(sum(weights[s] * evidence[s].changepoint_probability for s in STANDARD_ORDER)) if weight_sum > 0 else 1.0
        transition_risk = float(sum(weights[s] * evidence[s].transition_risk for s in STANDARD_ORDER)) if weight_sum > 0 else 1.0
        decision_strength = abs(composite) * calibrated_reliability * (1 - conflict_penalty) * (1 - correlation_penalty) * (1 - spillover_penalty)
        final_bias = "BUY" if composite > 0 else "SELL" if composite < 0 else "NEUTRAL"
        dominant = max(STANDARD_ORDER, key=lambda s: abs(weights[s] * evidence[s].signed_evidence_score)) if weight_sum > 0 else "NONE"
        block_reasons = list(identity_errors)
        if len(ready) < 3:
            block_reasons.append("ONE_OR_MORE_STANDARDS_NOT_READY")
        if not walk_forward_policy.get("validated"):
            block_reasons.append(str(walk_forward_policy.get("reason") or "WALK_FORWARD_POLICY_NOT_VALIDATED"))
        if calibrated_reliability < 0.35:
            block_reasons.append("CALIBRATED_RELIABILITY_BELOW_DATA_GATE")
        if changepoint > 0.65:
            block_reasons.append("HIGH_CHANGEPOINT_RISK")
        if transition_risk > 0.65:
            block_reasons.append("HIGH_TRANSITION_RISK")
        if final_bias == "NEUTRAL":
            block_reasons.append("NO_DIRECTIONAL_EDGE")
        if directional_conflict and agreement < 0.35:
            block_reasons.append("THREE_REGIME_DIRECTIONAL_CONFLICT")
        entry = "BLOCKED" if block_reasons else "PENDING_CROSS_SECTIONAL_THRESHOLD"
        cross_validation = _cross_model_validation(evidence)
        rank_payload = {
            "weights": weights, "base_structural_weights": BASE_STRUCTURAL_WEIGHTS,
            "weight_selection": "expanding-window walk-forward policy, normalized by calibrated reliability",
            "walk_forward_policy": walk_forward_policy,
            "dominant_standard": dominant, "directional_conflict": directional_conflict,
            "correlation": dcc.get(symbol, {}), "spillover": spill.get(symbol, {}),
            "cross_model_validation": cross_validation, "identity_errors": identity_errors,
            "source_data_hash": exact_hash, "provider": provider,
        }
        rank_hash = hashlib.sha256(json.dumps(rank_payload, sort_keys=True, default=str).encode()).hexdigest()
        row = {
            "Rank": None, "Symbol": symbol,
            "Lower Regime": evidence["LOWER"].regime_state, "Lower Bias": evidence["LOWER"].bias,
            "Lower Probability": evidence["LOWER"].posterior_probability, "Lower Reliability": evidence["LOWER"].calibrated_reliability,
            "Middle Regime": evidence["MIDDLE"].regime_state, "Middle Bias": evidence["MIDDLE"].bias,
            "Middle Probability": evidence["MIDDLE"].posterior_probability, "Middle Reliability": evidence["MIDDLE"].calibrated_reliability,
            "Higher Regime": evidence["HIGHER"].regime_state, "Higher Bias": evidence["HIGHER"].bias,
            "Higher Probability": evidence["HIGHER"].posterior_probability, "Higher Reliability": evidence["HIGHER"].calibrated_reliability,
            "Three-Regime Agreement": agreement, "Directional Conflict": "YES" if directional_conflict else "NO",
            "Dominant Standard": dominant, "Changepoint Risk": changepoint, "Transition Risk": transition_risk,
            "DCC Correlation Penalty": correlation_penalty, "HRP Cluster": int(dcc.get(symbol, {}).get("hrp_cluster", 0)),
            "Spillover TO": _safe_float(spill.get(symbol, {}).get("spillover_to")),
            "Spillover FROM": _safe_float(spill.get(symbol, {}).get("spillover_from")),
            "Net Spillover": _safe_float(spill.get(symbol, {}).get("net_spillover")),
            "Composite Bias": final_bias, "Composite Score": composite, "Decision Strength": decision_strength,
            "Calibrated Reliability": calibrated_reliability, "Entry Permission": entry,
            "Lower Candle After Regime Start": evidence["LOWER"].regime_age,
            "Middle Candle After Regime Start": evidence["MIDDLE"].regime_age,
            "Middle Avg Regime Candle Count Before Regime Change": evidence["MIDDLE"].payload.get("average_regime_candle_count_before_change"),
            "Middle Completed Regime Sample Count": int(evidence["MIDDLE"].payload.get("completed_regime_run_count") or 0),
            "Higher Candle After Regime Start": evidence["HIGHER"].regime_age,
            "Candle After Regime Start": evidence[dominant].regime_age if dominant in evidence else evidence["HIGHER"].regime_age,
            "Regime Start Standard": dominant if dominant in evidence else "HIGHER",
            "Block Reason": ";".join(block_reasons), "Completed Candle": actual_candle,
            "Parent Run ID": parent_run_id, "Generation": int(generation), "Timeframe": tf, "Snapshot Hash": snapshot_hash,
            "Evidence Hash": rank_hash, "Source Data Hash": exact_hash, "Rank Explanation": json.dumps(rank_payload, default=str),
            "Walk-Forward Decision Threshold": walk_forward_policy.get("decision_threshold", "NOT_TESTED"),
        }
        rank_rows.append(row)
        for standard in STANDARD_ORDER:
            e = evidence[standard]
            evidence_rows.append({
                "Parent Run ID": parent_run_id, "Generation": int(generation), "Symbol": symbol, "Timeframe": tf,
                "Standard": standard, "Window Bars": e.window_bars, "Regime State": e.regime_state, "Bias": e.bias,
                "Posterior Probability": e.posterior_probability, "Persistence Probability": e.persistence_probability,
                "Expected Duration": e.expected_duration, "Regime Age": e.regime_age,
                "Changepoint Probability": e.changepoint_probability, "Transition Risk": e.transition_risk,
                "Calibrated Reliability": e.calibrated_reliability, "Signed Evidence Score": e.signed_evidence_score,
                "Sample Count": e.sample_count, "Data Quality Grade": e.data_quality_grade,
                "Completed Candle": e.latest_completed_candle, "Evidence Hash": e.evidence_hash,
                "Payload JSON": json.dumps(e.payload, default=str),
            })
            validation = dict(e.payload.get("validation") or {})
            validation_rows.append({
                "Parent Run ID": parent_run_id, "Generation": int(generation), "Symbol": symbol, "Timeframe": tf,
                "Standard": standard, "Brier Score": validation.get("brier_score", "NOT_TESTED"),
                "Logarithmic Score": validation.get("logarithmic_score", "NOT_TESTED"),
                "CRPS": validation.get("crps", "NOT_TESTED"), "Calibration Error": validation.get("calibration_error", "NOT_TESTED"),
                "Conformal Coverage": validation.get("conformal_coverage", "NOT_TESTED_INSUFFICIENT_SAMPLE"),
                "Hansen SPA": cross_validation.get("hansen_spa", "NOT_TESTED_INSUFFICIENT_SAMPLE"),
                "Model Confidence Set": cross_validation.get("model_confidence_set"),
                "White Reality Check": cross_validation.get("white_reality_check"),
                "PBO/CSCV": cross_validation.get("pbo_cscv"),
                "Deflated Sharpe Ratio": validation.get("deflated_sharpe_probability", "NOT_TESTED_INSUFFICIENT_SAMPLE"),
                "Rank Stability": validation.get("rank_stability", "NOT_TESTED_NO_PRIOR_GENERATION"),
                "Turnover": validation.get("turnover", "NOT_TESTED_NO_PRIOR_GENERATION"),
                "Regime Stability": validation.get("regime_stability", "NOT_TESTED_INSUFFICIENT_SAMPLE"),
                "Duplicate Exposure Risk": correlation_penalty,
            })

    ranking = pd.DataFrame(rank_rows)
    if not ranking.empty:
        for idx in ranking.index:
            if ranking.at[idx, "Entry Permission"] != "BLOCKED":
                threshold = _safe_float(ranking.at[idx, "Walk-Forward Decision Threshold"], 1.0)
                if _safe_float(ranking.at[idx, "Decision Strength"]) >= threshold:
                    ranking.at[idx, "Entry Permission"] = "ALLOWED"
                else:
                    ranking.at[idx, "Entry Permission"] = "BLOCKED"
                    ranking.at[idx, "Block Reason"] = (str(ranking.at[idx, "Block Reason"]) + ";WALK_FORWARD_DECISION_THRESHOLD_NOT_MET").strip(";")
        ranking["__rankable"] = ranking["Entry Permission"].eq("ALLOWED")
        ranking = ranking.sort_values(["__rankable", "Decision Strength", "Calibrated Reliability"], ascending=[False, False, False], kind="mergesort").reset_index(drop=True)
        ranking["Rank"] = np.arange(1, len(ranking) + 1)
        ranking = ranking.drop(columns="__rankable")
        ranking["Adaptive Decision Threshold"] = ranking["Walk-Forward Decision Threshold"]
    return ranking, pd.DataFrame(evidence_rows), pd.DataFrame(validation_rows)


def persist_field3_v2(
    ranking: pd.DataFrame,
    evidence: pd.DataFrame,
    *,
    db_path: str | Path | None = None,
) -> dict[str, int]:
    path = Path(db_path or DEFAULT_DB_PATH)
    migrate_global_symbol_schema(path)
    now = _utcnow()
    with sqlite3.connect(str(path), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for _, r in evidence.iterrows():
                conn.execute(
                    """INSERT OR REPLACE INTO field3_regime_evidence_v2(
                           parent_run_id,generation,symbol,timeframe,standard,window_bars,regime_state,bias,
                           posterior_probability,persistence_probability,expected_duration,regime_age,
                           changepoint_probability,transition_risk,calibrated_reliability,sample_count,
                           data_quality_grade,latest_completed_candle,evidence_hash,payload_json,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (r["Parent Run ID"], int(r["Generation"]), r["Symbol"], r["Timeframe"], r["Standard"], int(r["Window Bars"]),
                     r["Regime State"], r["Bias"], _safe_float(r["Posterior Probability"]), _safe_float(r["Persistence Probability"]),
                     _safe_float(r["Expected Duration"]), int(r["Regime Age"]), _safe_float(r["Changepoint Probability"]),
                     _safe_float(r["Transition Risk"]), _safe_float(r["Calibrated Reliability"]), int(r["Sample Count"]),
                     r["Data Quality Grade"], r["Completed Candle"], r["Evidence Hash"], r["Payload JSON"], now),
                )
            for _, r in ranking.iterrows():
                payload = r.to_dict()
                conn.execute(
                    """INSERT OR REPLACE INTO field3_symbol_rank_v2(
                           parent_run_id,generation,symbol,timeframe,lower_score,middle_score,higher_score,
                           agreement_score,conflict_penalty,correlation_penalty,spillover_penalty,composite_score,
                           decision_strength,final_bias,calibrated_reliability,entry_permission,block_reason,rank,
                           latest_completed_candle,evidence_hash,payload_json,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (r["Parent Run ID"], int(r["Generation"]), r["Symbol"], r["Timeframe"],
                     _safe_float(evidence.loc[(evidence["Symbol"] == r["Symbol"]) & (evidence["Standard"] == "LOWER"), "Signed Evidence Score"].iloc[0]),
                     _safe_float(evidence.loc[(evidence["Symbol"] == r["Symbol"]) & (evidence["Standard"] == "MIDDLE"), "Signed Evidence Score"].iloc[0]),
                     _safe_float(evidence.loc[(evidence["Symbol"] == r["Symbol"]) & (evidence["Standard"] == "HIGHER"), "Signed Evidence Score"].iloc[0]),
                     _safe_float(r["Three-Regime Agreement"]), 1 - _safe_float(r["Three-Regime Agreement"]),
                     _safe_float(r["DCC Correlation Penalty"]), _clip(r["Spillover FROM"]), _safe_float(r["Composite Score"]),
                     _safe_float(r["Decision Strength"]), r["Composite Bias"], _safe_float(r["Calibrated Reliability"]),
                     r["Entry Permission"], r["Block Reason"], int(r["Rank"]), r["Completed Candle"], r["Evidence Hash"],
                     json.dumps(payload, default=str), now),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"rank_rows": int(len(ranking)), "evidence_rows": int(len(evidence))}

def load_saved_field3_v2(state: MutableMapping[str, Any] | None = None, *, context: Any | None = None, db_path: str | Path | None = None) -> dict[str, Any]:
    """Reload the exact saved Field 3 generation without provider/calculation calls."""
    from core.global_symbol_context import get_global_symbol_context
    ctx = context or get_global_symbol_context(state, db_path=db_path)
    if not ctx.parent_run_id or not ctx.generation or not ctx.timeframe:
        return {"ok": False, "status": "NO_SAVED_FIELD3_IDENTITY", "provider_calls": 0, "calculation_calls": 0}
    path = Path(db_path or DEFAULT_DB_PATH)
    migrate_global_symbol_schema(path)
    with sqlite3.connect(str(path), timeout=15) as conn:
        conn.row_factory = sqlite3.Row
        rank_rows = conn.execute(
            "SELECT payload_json FROM field3_symbol_rank_v2 WHERE parent_run_id=? AND generation=? AND timeframe=? ORDER BY rank,symbol",
            (ctx.parent_run_id, int(ctx.generation), ctx.timeframe),
        ).fetchall()
        evidence_db = conn.execute(
            "SELECT * FROM field3_regime_evidence_v2 WHERE parent_run_id=? AND generation=? AND timeframe=? ORDER BY symbol,CASE standard WHEN 'LOWER' THEN 1 WHEN 'MIDDLE' THEN 2 ELSE 3 END",
            (ctx.parent_run_id, int(ctx.generation), ctx.timeframe),
        ).fetchall()
    ranking_records: list[dict[str, Any]] = []
    for row in rank_rows:
        try:
            ranking_records.append(json.loads(row["payload_json"] or "{}"))
        except Exception:
            continue
    evidence_records: list[dict[str, Any]] = []
    validation_records: list[dict[str, Any]] = []
    for r in evidence_db:
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except Exception:
            payload = {}
        evidence_records.append({
            "Parent Run ID": r["parent_run_id"], "Generation": r["generation"], "Symbol": r["symbol"],
            "Timeframe": r["timeframe"], "Standard": r["standard"], "Window Bars": r["window_bars"],
            "Regime State": r["regime_state"], "Bias": r["bias"], "Posterior Probability": r["posterior_probability"],
            "Persistence Probability": r["persistence_probability"], "Expected Duration": r["expected_duration"],
            "Regime Age": r["regime_age"], "Changepoint Probability": r["changepoint_probability"],
            "Transition Risk": r["transition_risk"], "Calibrated Reliability": r["calibrated_reliability"],
            "Sample Count": r["sample_count"], "Data Quality Grade": r["data_quality_grade"],
            "Completed Candle": r["latest_completed_candle"], "Evidence Hash": r["evidence_hash"],
            "Payload JSON": json.dumps(payload, default=str),
        })
        v = dict(payload.get("validation") or {})
        validation_records.append({
            "Parent Run ID": r["parent_run_id"], "Generation": r["generation"], "Symbol": r["symbol"],
            "Timeframe": r["timeframe"], "Standard": r["standard"],
            "Brier Score": v.get("brier_score", "NOT_TESTED"), "Logarithmic Score": v.get("logarithmic_score", "NOT_TESTED"),
            "CRPS": v.get("crps", "NOT_TESTED"), "Calibration Error": v.get("calibration_error", "NOT_TESTED"),
            "Conformal Coverage": v.get("conformal_coverage", "NOT_TESTED_INSUFFICIENT_SAMPLE"),
            "Hansen SPA": v.get("hansen_spa_pvalue", "NOT_TESTED_INSUFFICIENT_SAMPLE"),
            "Model Confidence Set": v.get("model_confidence_set", "NOT_TESTED_REQUIRES_CROSS_MODEL_LOSS_PANEL"),
            "White Reality Check": v.get("white_reality_check", "NOT_TESTED_REQUIRES_SYNCHRONIZED_STRATEGY_RETURN_PANEL"),
            "PBO/CSCV": v.get("pbo_cscv", "NOT_TESTED_INSUFFICIENT_CONFIGURATIONS"),
            "Deflated Sharpe Ratio": v.get("deflated_sharpe_probability", "NOT_TESTED_INSUFFICIENT_SAMPLE"),
            "Rank Stability": v.get("rank_stability", "NOT_TESTED_NO_PRIOR_GENERATION"),
            "Turnover": v.get("turnover", "NOT_TESTED_NO_PRIOR_GENERATION"),
            "Regime Stability": v.get("regime_stability", "NOT_TESTED_INSUFFICIENT_SAMPLE"),
        })
    ranking = pd.DataFrame(ranking_records)
    evidence = pd.DataFrame(evidence_records)
    validation = pd.DataFrame(validation_records)
    if isinstance(state, MutableMapping):
        state["field3_multisymbol_regime_20260708"] = ranking
        state["field3_regime_evidence_v2"] = evidence
        state["field3_research_validation_v2"] = validation
        try:
            from core.global_symbol_exports import refresh_global_export_payloads
            refresh_global_export_payloads(state, ctx)
        except Exception:
            pass
    return {"ok": not ranking.empty, "status": "SAVED_FIELD3_RELOADED" if not ranking.empty else "NO_SAVED_FIELD3_ROWS",
            "rank_rows": len(ranking), "evidence_rows": len(evidence), "provider_calls": 0, "calculation_calls": 0}


__all__ = [
    "STANDARD_ORDER", "BASE_STRUCTURAL_WEIGHTS", "bars_for_days", "standard_windows", "standardize_candles",
    "build_field3_three_regime_ranking", "persist_field3_v2", "load_saved_field3_v2", "candle_hash",
]
