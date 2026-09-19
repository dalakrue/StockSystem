"""Calibration and sharpness diagnostics for settled shadow forecasts."""
from __future__ import annotations

from typing import Any, Iterable
import numpy as np


def _array(values: Iterable[Any]) -> np.ndarray:
    return np.asarray(list(values), dtype=float).reshape(-1)


def pit_rank_diagnostics(pit_values: Iterable[Any], *, bins: int = 10) -> dict[str, Any]:
    x = _array(pit_values)
    x = x[np.isfinite(x)]
    if x.size < 5:
        return {"status": "INSUFFICIENT EVIDENCE", "sample_size": int(x.size), "histogram": [], "uniformity_error": None}
    x = np.clip(x, 0.0, 1.0)
    hist, edges = np.histogram(x, bins=max(2, int(bins)), range=(0.0, 1.0))
    expected = x.size / hist.size
    error = float(np.mean(np.abs(hist - expected)) / max(expected, 1.0))
    return {
        "status": "CALIBRATED" if error <= 0.35 else "WATCH" if error <= 0.65 else "MIS-CALIBRATED",
        "sample_size": int(x.size),
        "histogram": hist.astype(int).tolist(),
        "bin_edges": edges.tolist(),
        "uniformity_error": error,
        "mean_pit": float(np.mean(x)),
    }


def evaluate_intervals(lower: Iterable[Any], upper: Iterable[Any], observations: Iterable[Any], *, nominal_coverage: float = 0.9, scale: float | None = None) -> dict[str, Any]:
    lo, hi, y = _array(lower), _array(upper), _array(observations)
    n = min(lo.size, hi.size, y.size)
    lo, hi, y = lo[:n], hi[:n], y[:n]
    mask = np.isfinite(lo) & np.isfinite(hi) & np.isfinite(y) & (lo <= hi)
    lo, hi, y = lo[mask], hi[mask], y[mask]
    if y.size == 0:
        return {"status": "INSUFFICIENT EVIDENCE", "sample_size": 0, "actual_coverage": None, "mean_width": None, "frontier_score": None}
    nominal = min(0.999, max(0.001, float(nominal_coverage)))
    covered = (y >= lo) & (y <= hi)
    coverage = float(np.mean(covered))
    width = hi - lo
    mean_width = float(np.mean(width))
    robust_scale = float(scale) if scale is not None and float(scale) > 0 else float(np.nanstd(y))
    robust_scale = max(robust_scale, float(np.nanmedian(np.abs(y - np.nanmedian(y))) * 1.4826), 1e-12)
    calibration_error = abs(coverage - nominal)
    normalized_width = mean_width / robust_scale
    frontier_score = calibration_error + 0.05 * normalized_width
    if y.size < 20:
        status = "INSUFFICIENT EVIDENCE"
    elif calibration_error <= 0.03:
        status = "CALIBRATED-SHARP" if normalized_width <= 2.5 else "CALIBRATED-BUT-WIDE"
    elif coverage < nominal:
        status = "UNDER-COVERED"
    else:
        status = "OVER-COVERED"
    return {
        "status": status,
        "sample_size": int(y.size),
        "nominal_coverage": nominal,
        "actual_coverage": coverage,
        "coverage_error": calibration_error,
        "mean_width": mean_width,
        "median_width": float(np.median(width)),
        "normalized_width": normalized_width,
        "frontier_score": frontier_score,
        "lower_is_better": True,
    }


def evaluate(*, lower: Iterable[Any] = (), upper: Iterable[Any] = (), observations: Iterable[Any] = (), pit_values: Iterable[Any] = (), nominal_coverage: float = 0.9) -> dict[str, Any]:
    return {
        "interval_frontier": evaluate_intervals(lower, upper, observations, nominal_coverage=nominal_coverage),
        "pit_rank": pit_rank_diagnostics(pit_values),
    }


__all__ = ["pit_rank_diagnostics", "evaluate_intervals", "evaluate"]
