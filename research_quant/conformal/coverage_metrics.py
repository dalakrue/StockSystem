from __future__ import annotations
import numpy as np

def coverage(actual, lower, upper) -> float:
    y, lo, hi = map(lambda x: np.asarray(x, dtype=float), (actual, lower, upper))
    mask = np.isfinite(y) & np.isfinite(lo) & np.isfinite(hi)
    return float(np.mean((y[mask] >= lo[mask]) & (y[mask] <= hi[mask]))) if mask.any() else float("nan")

def mean_interval_width(lower, upper) -> float:
    lo, hi = np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)
    mask = np.isfinite(lo) & np.isfinite(hi)
    return float(np.mean(hi[mask] - lo[mask])) if mask.any() else float("nan")
