from __future__ import annotations
import numpy as np


def adaptive_residual_quantile(residuals, alpha: float = 0.10, weights=None) -> float:
    values = np.asarray(residuals, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return float("nan")
    if weights is None:
        return float(np.quantile(values, 1 - alpha, method="higher"))
    weight = np.asarray(weights, dtype=float)[-len(values):]
    order = np.argsort(values)
    values, weight = values[order], weight[order]
    cumulative = np.cumsum(weight) / max(weight.sum(), 1e-12)
    return float(values[np.searchsorted(cumulative, 1 - alpha, side="left")])
