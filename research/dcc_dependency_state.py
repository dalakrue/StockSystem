"""Lightweight Dynamic Conditional Correlation state from local synchronized returns."""
from __future__ import annotations

from typing import Any, Iterable, Mapping
import numpy as np


def _nearest_correlation(matrix: np.ndarray, epsilon: float = 1e-8) -> np.ndarray:
    sym = (matrix + matrix.T) / 2.0
    values, vectors = np.linalg.eigh(sym)
    values = np.maximum(values, epsilon)
    pd = vectors @ np.diag(values) @ vectors.T
    scale = np.sqrt(np.maximum(np.diag(pd), epsilon))
    corr = pd / np.outer(scale, scale)
    np.fill_diagonal(corr, 1.0)
    return (corr + corr.T) / 2.0


def evaluate(series: Mapping[str, Iterable[Any]], *, alpha: float = 0.03, beta: float = 0.95, min_samples: int = 30, freshness_minutes: float | None = None, max_freshness_minutes: float = 180.0) -> dict[str, Any]:
    names = sorted(series)
    if len(names) < 2:
        return {"status": "INSUFFICIENT EVIDENCE", "sample_size": 0, "assets": names, "reason": "at least two synchronized series are required"}
    arrays = [np.asarray(list(series[name]), dtype=float).reshape(-1) for name in names]
    n = min((arr.size for arr in arrays), default=0)
    if n == 0:
        return {"status": "INSUFFICIENT EVIDENCE", "sample_size": 0, "assets": names}
    x = np.column_stack([arr[-n:] for arr in arrays])
    finite_rows = np.all(np.isfinite(x), axis=1)
    missingness = 1.0 - float(np.mean(finite_rows))
    x = x[finite_rows]
    if x.shape[0] < int(min_samples):
        return {"status": "INSUFFICIENT EVIDENCE", "sample_size": int(x.shape[0]), "assets": names, "missingness": missingness}
    a, b = max(0.0, float(alpha)), max(0.0, float(beta))
    if a + b >= 0.999:
        total = a + b
        a, b = a * 0.999 / total, b * 0.999 / total
    std = np.std(x, axis=0, ddof=1)
    valid_assets = std > 1e-12
    if not np.all(valid_assets):
        return {"status": "INSUFFICIENT EVIDENCE", "sample_size": int(x.shape[0]), "assets": names, "reason": "zero-variance series"}
    z = (x - np.mean(x, axis=0)) / std
    unconditional = _nearest_correlation(np.corrcoef(z, rowvar=False))
    q = unconditional.copy()
    path = []
    for row in z:
        q = (1.0 - a - b) * unconditional + a * np.outer(row, row) + b * q
        corr = _nearest_correlation(q)
        path.append(corr)
    final = path[-1]
    eigenvalues = np.linalg.eigvalsh(final)
    stale = freshness_minutes is not None and float(freshness_minutes) > float(max_freshness_minutes)
    status = "STALE" if stale else "OK"
    return {
        "status": status,
        "sample_size": int(x.shape[0]),
        "assets": names,
        "missingness": missingness,
        "freshness_minutes": freshness_minutes,
        "alpha": a,
        "beta": b,
        "correlation_matrix": final.tolist(),
        "unconditional_correlation": unconditional.tolist(),
        "minimum_eigenvalue": float(np.min(eigenvalues)),
        "positive_definite": bool(np.min(eigenvalues) > 0.0),
        "bounded": bool(np.all(np.abs(final) <= 1.0 + 1e-10)),
    }


__all__ = ["evaluate"]
