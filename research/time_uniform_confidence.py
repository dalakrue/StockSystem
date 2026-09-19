"""Anytime-valid confidence-sequence style bounds for shadow monitoring."""
from __future__ import annotations

from typing import Any, Iterable
import math
import numpy as np


def bernoulli_confidence_sequence(outcomes: Iterable[Any], *, alpha: float = 0.05) -> dict[str, Any]:
    y = np.asarray(list(outcomes), dtype=float).reshape(-1)
    y = y[np.isfinite(y)]
    y = np.clip(y, 0.0, 1.0)
    if y.size == 0:
        return {"status": "INSUFFICIENT EVIDENCE", "sample_size": 0, "lower": [], "upper": []}
    a = min(0.5, max(float(alpha), 1e-12))
    cumulative = np.cumsum(y)
    lower, upper, means = [], [], []
    for idx in range(1, y.size + 1):
        mean = float(cumulative[idx - 1] / idx)
        # Alpha spending over all times gives simultaneous Hoeffding bounds.
        alpha_n = a / (idx * (idx + 1.0))
        radius = math.sqrt(math.log(2.0 / alpha_n) / (2.0 * idx))
        means.append(mean); lower.append(max(0.0, mean - radius)); upper.append(min(1.0, mean + radius))
    return {"status": "OK", "sample_size": int(y.size), "mean": means[-1], "lower": lower[-500:], "upper": upper[-500:], "path_start_step": max(1, int(y.size) - 499), "final_lower": lower[-1], "final_upper": upper[-1], "alpha": a}


def bounded_mean_confidence_sequence(values: Iterable[Any], *, lower_bound: float = -1.0, upper_bound: float = 1.0, alpha: float = 0.05) -> dict[str, Any]:
    x = np.asarray(list(values), dtype=float).reshape(-1)
    x = x[np.isfinite(x)]
    lo, hi = float(lower_bound), float(upper_bound)
    if not lo < hi:
        raise ValueError("lower_bound must be below upper_bound")
    normalized = (np.clip(x, lo, hi) - lo) / (hi - lo)
    result = bernoulli_confidence_sequence(normalized, alpha=alpha)
    if not result.get("sample_size"):
        return result
    result["mean"] = lo + (hi - lo) * result["mean"]
    result["lower"] = [lo + (hi - lo) * v for v in result["lower"]]
    result["upper"] = [lo + (hi - lo) * v for v in result["upper"]]
    result["final_lower"] = result["lower"][-1]
    result["final_upper"] = result["upper"][-1]
    return result


def evaluate(*, direction_correct: Iterable[Any] = (), interval_covered: Iterable[Any] = (), loss_differential: Iterable[Any] = (), selective_errors: Iterable[Any] = (), loss_bounds: tuple[float, float] = (-1.0, 1.0), alpha: float = 0.05) -> dict[str, Any]:
    return {
        "direction_accuracy": bernoulli_confidence_sequence(direction_correct, alpha=alpha),
        "interval_coverage": bernoulli_confidence_sequence(interval_covered, alpha=alpha),
        "loss_differential": bounded_mean_confidence_sequence(loss_differential, lower_bound=loss_bounds[0], upper_bound=loss_bounds[1], alpha=alpha),
        "selective_risk": bernoulli_confidence_sequence(selective_errors, alpha=alpha),
    }


__all__ = ["bernoulli_confidence_sequence", "bounded_mean_confidence_sequence", "evaluate"]
