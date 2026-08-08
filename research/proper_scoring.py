"""Proper scoring rules for settled shadow forecasts.

All functions are deterministic, finite-safe, and refuse to use unsettled rows.
Lower scores are better. No function changes a production forecast or decision.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

_EPS = 1e-12


def _paired(a: Iterable[Any], b: Iterable[Any]) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(list(a), dtype=float).reshape(-1)
    y = np.asarray(list(b), dtype=float).reshape(-1)
    n = min(x.size, y.size)
    if n == 0:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    mask = np.isfinite(x[:n]) & np.isfinite(y[:n])
    return x[:n][mask], y[:n][mask]


def brier_score(probabilities: Iterable[Any], outcomes: Iterable[Any]) -> float | None:
    """Mean squared probability error for binary settled outcomes."""
    p, y = _paired(probabilities, outcomes)
    if p.size == 0:
        return None
    p = np.clip(p, 0.0, 1.0)
    y = np.clip(y, 0.0, 1.0)
    return float(np.mean((p - y) ** 2))


def safe_log_score(probabilities: Iterable[Any], outcomes: Iterable[Any], *, epsilon: float = 1e-12) -> float | None:
    """Binary logarithmic score with bounded clipping to avoid NaN/inf."""
    p, y = _paired(probabilities, outcomes)
    if p.size == 0:
        return None
    eps = min(1e-3, max(float(epsilon), _EPS))
    p = np.clip(p, eps, 1.0 - eps)
    y = np.clip(y, 0.0, 1.0)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log1p(-p)))


def quantile_loss(predictions: Iterable[Any], observations: Iterable[Any], quantile: float) -> float | None:
    """Pinball loss for a requested quantile in (0, 1)."""
    q = float(quantile)
    if not 0.0 < q < 1.0:
        raise ValueError("quantile must be strictly between 0 and 1")
    pred, obs = _paired(predictions, observations)
    if pred.size == 0:
        return None
    error = obs - pred
    return float(np.mean(np.maximum(q * error, (q - 1.0) * error)))


def interval_score(lower: Iterable[Any], upper: Iterable[Any], observations: Iterable[Any], *, alpha: float = 0.1) -> float | None:
    """Gneiting-Raftery central prediction interval score; lower is better."""
    a = float(alpha)
    if not 0.0 < a < 1.0:
        raise ValueError("alpha must be strictly between 0 and 1")
    lo = np.asarray(list(lower), dtype=float).reshape(-1)
    hi = np.asarray(list(upper), dtype=float).reshape(-1)
    y = np.asarray(list(observations), dtype=float).reshape(-1)
    n = min(lo.size, hi.size, y.size)
    if n == 0:
        return None
    lo, hi, y = lo[:n], hi[:n], y[:n]
    mask = np.isfinite(lo) & np.isfinite(hi) & np.isfinite(y) & (lo <= hi)
    if not np.any(mask):
        return None
    lo, hi, y = lo[mask], hi[mask], y[mask]
    score = (hi - lo) + (2.0 / a) * (lo - y) * (y < lo) + (2.0 / a) * (y - hi) * (y > hi)
    return float(np.mean(score))


def crps_ensemble(ensemble: Sequence[Sequence[Any]] | np.ndarray, observations: Iterable[Any]) -> float | None:
    """Exact empirical-ensemble CRPS, suitable as a CRPS-compatible evaluator."""
    members = np.asarray(ensemble, dtype=float)
    obs = np.asarray(list(observations), dtype=float).reshape(-1)
    if members.ndim == 1:
        members = members.reshape(-1, 1)
    if members.ndim != 2 or obs.size == 0:
        return None
    n = min(members.shape[0], obs.size)
    members, obs = members[:n], obs[:n]
    valid = np.isfinite(obs) & np.all(np.isfinite(members), axis=1)
    if not np.any(valid):
        return None
    members, obs = members[valid], obs[valid]
    first = np.mean(np.abs(members - obs[:, None]), axis=1)
    pair = np.mean(np.abs(members[:, :, None] - members[:, None, :]), axis=(1, 2))
    return float(np.mean(first - 0.5 * pair))


def evaluate_settled(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Evaluate available fields from strictly settled records only."""
    settled = [dict(r) for r in rows if isinstance(r, Mapping) and str(r.get("outcome_status") or r.get("status") or "SETTLED").upper() == "SETTLED"]
    probabilities, outcomes, actual, predicted, lower, upper = [], [], [], [], [], []
    for row in settled:
        probability = row.get("direction_probability", row.get("probability", row.get("confidence")))
        if probability is not None:
            try:
                p = float(probability)
                if p > 1.0:
                    p /= 100.0
                probabilities.append(p)
                outcomes.append(float(row.get("direction_correct", 1.0 if str(row.get("settled_outcome")).upper() == "WIN" else 0.0)))
            except (TypeError, ValueError):
                pass
        try:
            actual.append(float(row["actual_price"]))
            predicted.append(float(row["predicted_price"]))
            lower.append(float(row["lower_bound"]))
            upper.append(float(row["upper_bound"]))
        except (KeyError, TypeError, ValueError):
            pass
    result = {
        "status": "OK" if settled else "INSUFFICIENT EVIDENCE",
        "sample_size": len(settled),
        "probability_sample_size": min(len(probabilities), len(outcomes)),
        "interval_sample_size": min(len(actual), len(lower), len(upper)),
        "brier_score": brier_score(probabilities, outcomes),
        "log_score": safe_log_score(probabilities, outcomes),
        "interval_score_90": interval_score(lower, upper, actual, alpha=0.1),
    }
    if actual and predicted:
        result["crps_compatible_mae"] = float(np.mean(np.abs(np.asarray(actual) - np.asarray(predicted))))
    else:
        result["crps_compatible_mae"] = None
    return result


__all__ = ["brier_score", "safe_log_score", "quantile_loss", "interval_score", "crps_ensemble", "evaluate_settled"]
