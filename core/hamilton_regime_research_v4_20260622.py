"""Hamilton-style Markov-switching shadow regime probabilities for EURUSD H1."""
from __future__ import annotations

from typing import Any, Mapping
import math

import numpy as np
import pandas as pd

from core.quant_research_v4_contract_20260622 import common_result, unavailable

METHOD_ID = "HAMILTON_MARKOV_SWITCHING_SHADOW"
PAPER_TITLE = "A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle"
PAPER_AUTHORS = "James D. Hamilton"
PROB_FLOOR = 1e-9
MAX_ITERATIONS = 25


def _yang_zhang_variance(frame: pd.DataFrame, window: int = 24) -> pd.Series:
    o = np.log(frame["open"].clip(lower=1e-12))
    h = np.log(frame["high"].clip(lower=1e-12))
    l = np.log(frame["low"].clip(lower=1e-12))
    c = np.log(frame["close"].clip(lower=1e-12))
    overnight = o - c.shift(1)
    open_close = c - o
    rs = (h - c) * (h - o) + (l - c) * (l - o)
    n = max(2, int(window))
    k = 0.34 / (1.34 + (n + 1.0) / max(n - 1.0, 1.0))
    return (overnight.rolling(n).var(ddof=1) + k * open_close.rolling(n).var(ddof=1) + (1.0 - k) * rs.rolling(n).mean()).clip(lower=1e-12)


def _feature_frame(frame: pd.DataFrame, settled: pd.DataFrame | None = None) -> pd.DataFrame:
    close = frame["close"].astype(float).clip(lower=1e-12)
    ret = np.log(close).diff()
    normalized_range = (frame["high"].astype(float) - frame["low"].astype(float)) / close
    yz = np.sqrt(_yang_zhang_variance(frame, 24))
    trend = pd.to_numeric(frame.get("trend_strength", pd.Series(index=frame.index, dtype=float)), errors="coerce")
    if trend.notna().sum() == 0:
        trend = ret.rolling(14).mean().abs() / (ret.rolling(14).std(ddof=1) + 1e-12)
    error = pd.Series(np.nan, index=frame.index, dtype=float)
    if isinstance(settled, pd.DataFrame) and not settled.empty and "__target_time" in settled.columns:
        candidates = [c for c in ("absolute_error", "percentage_error", "forecast_error", "error_magnitude") if c in settled.columns]
        if candidates:
            temp = pd.DataFrame({"time": settled["__target_time"], "error": pd.to_numeric(settled[candidates[0]], errors="coerce").abs()})
            temp = temp.dropna().sort_values("time").drop_duplicates("time", keep="last")
            merged = frame[["time"]].merge(temp, on="time", how="left")
            error = merged["error"].ffill().rolling(12, min_periods=1).median()
    if error.notna().sum() == 0:
        error = ret.abs().rolling(12).mean()
    return pd.DataFrame({
        "log_return": ret,
        "absolute_return": ret.abs(),
        "normalized_range": normalized_range,
        "yang_zhang_volatility": yz,
        "protected_trend_strength": trend,
        "settled_forecast_error_magnitude": error,
    }, index=frame.index).replace([np.inf, -np.inf], np.nan)


def _log_gaussian_diag(x: np.ndarray, mean: np.ndarray, var: np.ndarray) -> np.ndarray:
    var = np.clip(var, 1e-5, 1e4)
    return -0.5 * (np.sum(np.log(2.0 * math.pi * var)) + np.sum((x - mean) ** 2 / var, axis=-1))


def _forward_backward(x: np.ndarray, pi: np.ndarray, trans: np.ndarray, means: np.ndarray, variances: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    n, k = len(x), len(pi)
    emission = np.empty((n, k), dtype=float)
    for state in range(k):
        emission[:, state] = np.exp(np.clip(_log_gaussian_diag(x, means[state], variances[state]), -700, 50))
    emission = np.clip(emission, PROB_FLOOR, None)
    alpha = np.zeros((n, k), dtype=float)
    scales = np.ones(n, dtype=float)
    alpha[0] = np.clip(pi * emission[0], PROB_FLOOR, None)
    scales[0] = max(alpha[0].sum(), PROB_FLOOR)
    alpha[0] /= scales[0]
    for t in range(1, n):
        alpha[t] = np.clip((alpha[t - 1] @ trans) * emission[t], PROB_FLOOR, None)
        scales[t] = max(alpha[t].sum(), PROB_FLOOR)
        alpha[t] /= scales[t]
    beta = np.ones((n, k), dtype=float)
    for t in range(n - 2, -1, -1):
        beta[t] = trans @ (emission[t + 1] * beta[t + 1])
        beta[t] /= max(scales[t + 1], PROB_FLOOR)
    gamma = np.clip(alpha * beta, PROB_FLOOR, None)
    gamma /= gamma.sum(axis=1, keepdims=True)
    xi = np.zeros((n - 1, k, k), dtype=float)
    for t in range(n - 1):
        raw = alpha[t, :, None] * trans * emission[t + 1][None, :] * beta[t + 1][None, :]
        denom = max(raw.sum(), PROB_FLOOR)
        xi[t] = raw / denom
    return alpha, gamma, xi, float(np.log(scales).sum())


def _initial_states(x: np.ndarray, k: int) -> np.ndarray:
    vol_score = x[:, 1] + x[:, 2] + x[:, 3]
    if k == 2:
        cuts = np.quantile(vol_score, [0.5])
    else:
        cuts = np.quantile(vol_score, [1.0 / 3.0, 2.0 / 3.0])
    return np.digitize(vol_score, cuts, right=True)


def _fit_hmm(x: np.ndarray, k: int) -> dict[str, Any]:
    states = _initial_states(x, k)
    pi = np.full(k, 1.0 / k)
    trans = np.full((k, k), 0.05 / max(k - 1, 1))
    np.fill_diagonal(trans, 0.95)
    means = np.vstack([x[states == j].mean(axis=0) if np.any(states == j) else x.mean(axis=0) for j in range(k)])
    variances = np.vstack([x[states == j].var(axis=0) + 0.10 if np.any(states == j) else x.var(axis=0) + 0.10 for j in range(k)])
    prior_strength = 1e-3
    previous_ll = -np.inf
    converged = False
    for iteration in range(MAX_ITERATIONS):
        alpha, gamma, xi, ll = _forward_backward(x, pi, trans, means, variances)
        weights = gamma.sum(axis=0) + prior_strength
        pi = np.clip(gamma[0], PROB_FLOOR, None); pi /= pi.sum()
        trans = xi.sum(axis=0) + prior_strength
        trans /= trans.sum(axis=1, keepdims=True)
        means = (gamma.T @ x) / weights[:, None]
        for j in range(k):
            centered = x - means[j]
            variances[j] = (gamma[:, j, None] * centered * centered).sum(axis=0) / weights[j]
        variances = np.clip(variances, 1e-4, 100.0)
        if np.min(np.diag(trans)) < 0.02 or np.max(trans) > 0.999999:
            raise ValueError("Degenerate transition matrix rejected.")
        if np.isfinite(previous_ll) and abs(ll - previous_ll) <= 1e-6 * (1.0 + abs(previous_ll)):
            converged = True
            break
        previous_ll = ll
    alpha, gamma, xi, ll = _forward_backward(x, pi, trans, means, variances)
    return {
        "filtered": alpha,
        "smoothed": gamma,  # historical full-sample smoothing; current state uses filtered alpha
        "transition": trans,
        "means": means,
        "variances": variances,
        "log_likelihood": ll,
        "iterations": iteration + 1,
        "converged": converged,
    }


def _descriptive_labels(means: np.ndarray) -> list[str]:
    k = len(means)
    vol = means[:, 1] + means[:, 2] + means[:, 3]
    trend = means[:, 4]
    order = list(np.argsort(vol))
    labels = ["TREND_NORMAL_VOL"] * k
    labels[order[0]] = "RANGE_LOW_VOL"
    labels[order[-1]] = "TRANSITION_HIGH_VOL"
    if k == 3:
        middle = order[1]
        labels[middle] = "TREND_NORMAL_VOL" if trend[middle] >= np.median(trend) else "RANGE_LOW_VOL"
    return labels


def run_hamilton_regime_model(frame: pd.DataFrame, identity: Mapping[str, Any], *, settled_outcomes: pd.DataFrame | None = None, protected_regime: Any = None) -> dict[str, Any]:
    n = int(len(frame)) if isinstance(frame, pd.DataFrame) else 0
    minimum = 480
    try:
        if n < minimum:
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="BOUNDED_DIAGONAL_GAUSSIAN_ADAPTATION", sample_count=n, minimum_required_samples=minimum,
                status="INSUFFICIENT_EVIDENCE", limitations=["At least 480 completed H1 bars are required for the two-state fit."])
        raw = _feature_frame(frame, settled_outcomes)
        usable = raw.dropna()
        if len(usable) < minimum:
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="BOUNDED_DIAGONAL_GAUSSIAN_ADAPTATION", sample_count=len(usable), minimum_required_samples=minimum,
                status="INSUFFICIENT_EVIDENCE", limitations=["Feature construction left fewer than 480 finite completed-H1 observations."])
        split = max(minimum, int(len(usable) * 0.70))
        train = usable.iloc[:split]
        mean = train.mean().to_numpy(float)
        std = train.std(ddof=0).replace(0, np.nan).fillna(1.0).to_numpy(float)
        x = np.clip((usable.to_numpy(float) - mean) / std, -12.0, 12.0)
        states = 3 if len(usable) >= 720 else 2
        fit = _fit_hmm(x, states)
        labels = _descriptive_labels(fit["means"])
        latest = fit["filtered"][-1]
        probs: dict[str, float] = {}
        for i, label in enumerate(labels):
            probs[label] = probs.get(label, 0.0) + float(latest[i])
        probs = {k: float(v / sum(probs.values())) for k, v in probs.items()}
        most = max(probs, key=probs.get)
        entropy = float(-np.sum(latest * np.log(np.clip(latest, PROB_FLOOR, 1.0))) / math.log(states))
        duration = {labels[i]: float(1.0 / max(1.0 - fit["transition"][i, i], 1e-6)) for i in range(states)}
        protected_text = str(protected_regime or "").upper()
        agreement = "UNAVAILABLE"
        if protected_text:
            if "RANGE" in protected_text:
                agreement = bool(most == "RANGE_LOW_VOL")
            elif "TREND" in protected_text or "BULL" in protected_text or "BEAR" in protected_text:
                agreement = bool(most == "TREND_NORMAL_VOL")
            elif "TRANSITION" in protected_text or "HIGH" in protected_text:
                agreement = bool(most == "TRANSITION_HIGH_VOL")
        filtered_tail = []
        smoothed_tail = []
        times = usable.index[-48:]
        offset = len(usable) - len(times)
        for pos, idx in enumerate(times):
            filtered_probs = fit["filtered"][offset + pos]
            smoothed_probs = fit["smoothed"][offset + pos]
            timestamp = frame.loc[idx, "time"].isoformat() if "time" in frame.columns else str(idx)
            filtered_tail.append({
                "time": timestamp,
                "state_probabilities": {labels[j]: float(filtered_probs[j]) for j in range(states)},
            })
            smoothed_tail.append({
                "time": timestamp,
                "state_probabilities": {labels[j]: float(smoothed_probs[j]) for j in range(states)},
            })
        return common_result(
            identity,
            method_id=METHOD_ID,
            paper_title=PAPER_TITLE,
            paper_authors=PAPER_AUTHORS,
            exact_or_adaptation="BOUNDED_DIAGONAL_GAUSSIAN_MARKOV_SWITCHING_ADAPTATION",
            sample_count=len(usable), effective_sample_count=len(usable), minimum_required_samples=minimum,
            status="AVAILABLE", score=1.0 - entropy, confidence=1.0 - entropy,
            reliability="STABLE" if entropy < 0.60 and fit["converged"] else "CAUTION",
            train_start=frame.loc[train.index[0], "time"], train_end=frame.loc[train.index[-1], "time"],
            test_start=frame.loc[usable.index[split], "time"] if split < len(usable) else None,
            test_end=frame.loc[usable.index[-1], "time"],
            assumptions=["Diagonal Gaussian emissions are a bounded adaptation, not an exact market law.", "Training standardization uses the initial chronological training window only."],
            limitations=["State labels are descriptive and never overwrite the protected regime.", "Historical smoothed probabilities use the full completed sample; live latest probability is forward-filtered."],
            most_likely_shadow_state=most,
            state_probabilities=probs,
            state_entropy=entropy,
            transition_matrix=[[float(v) for v in row] for row in fit["transition"]],
            expected_state_duration_hours=duration,
            agreement_with_protected_regime=agreement,
            regime_uncertainty_warning=bool(entropy >= 0.60 or max(probs.values()) < 0.60),
            state_count=states,
            convergence={"iterations": fit["iterations"], "converged": fit["converged"], "log_likelihood": fit["log_likelihood"]},
            filtered_probability_history_tail=filtered_tail,
            historical_smoothed_probabilities_tail=smoothed_tail,
            internal_state_sequence=[int(x) for x in np.argmax(fit["filtered"], axis=1)],
            internal_filtered_probabilities=fit["filtered"].tolist(),
            internal_feature_index=[int(i) for i in usable.index],
        )
    except Exception as exc:
        return unavailable(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            error=exc, minimum_required_samples=minimum, sample_count=n,
            limitations=["The protected regime remains unchanged when the shadow fit fails."])


__all__ = ["run_hamilton_regime_model", "_feature_frame"]
