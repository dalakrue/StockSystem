from __future__ import annotations
import numpy as np


def _clean(y_true, probability):
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(probability, dtype=float)
    mask = np.isfinite(y) & np.isfinite(p)
    return y[mask], np.clip(p[mask], 1e-12, 1 - 1e-12)


def brier_score(y_true, probability) -> float:
    y, p = _clean(y_true, probability)
    return float(np.mean((p - y) ** 2)) if len(y) else float("nan")


def log_loss(y_true, probability) -> float:
    y, p = _clean(y_true, probability)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))) if len(y) else float("nan")


def expected_calibration_error(y_true, probability, bins: int = 10) -> float:
    y, p = _clean(y_true, probability)
    if not len(y):
        return float("nan")
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(y)
    error = 0.0
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (p >= low) & (p < high if high < 1 else p <= high)
        if mask.any():
            error += mask.mean() * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(error)


def maximum_calibration_error(y_true, probability, bins: int = 10) -> float:
    y, p = _clean(y_true, probability)
    errors = []
    for low, high in zip(np.linspace(0, 1, bins + 1)[:-1], np.linspace(0, 1, bins + 1)[1:]):
        mask = (p >= low) & (p < high if high < 1 else p <= high)
        if mask.any():
            errors.append(abs(float(y[mask].mean()) - float(p[mask].mean())))
    return float(max(errors, default=float("nan")))


def brier_skill_score(y_true, probability, reference_probability=None) -> float:
    y, p = _clean(y_true, probability)
    if not len(y):
        return float("nan")
    reference = np.full_like(y, y.mean()) if reference_probability is None else np.asarray(reference_probability, dtype=float)[: len(y)]
    denominator = brier_score(y, reference)
    return float(1 - brier_score(y, p) / denominator) if denominator > 0 else 0.0
