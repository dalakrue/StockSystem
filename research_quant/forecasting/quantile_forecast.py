from __future__ import annotations
import numpy as np

def quantile_loss(actual, prediction, quantile: float) -> float:
    y = np.asarray(actual, dtype=float); p = np.asarray(prediction, dtype=float)
    error = y - p
    return float(np.mean(np.maximum(quantile * error, (quantile - 1) * error)))
