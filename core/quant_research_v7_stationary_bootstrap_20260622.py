"""Deterministic stationary-bootstrap service for bounded V7 uncertainty estimates."""
from __future__ import annotations

from typing import Any, Callable
import time

import numpy as np
import pandas as pd

from core.quant_research_v7_contract_20260622 import common_method, deterministic_seed, finite

METHOD_ID = "stationary_bootstrap"
MIN_SAMPLE = 40
MAX_REPLICATIONS = 240


def estimate_mean_block_length(values: Any, *, fallback: int = 8, minimum: int = 2, maximum: int = 48) -> tuple[int, str | None]:
    x = np.asarray(values, dtype=float).reshape(-1)
    x = x[np.isfinite(x)]
    if len(x) < 16 or np.nanstd(x) <= 1e-12:
        return int(np.clip(fallback, minimum, maximum)), "insufficient autocorrelation support"
    x = x - np.mean(x)
    denom = float(np.dot(x, x))
    if denom <= 1e-18:
        return int(np.clip(fallback, minimum, maximum)), "zero variance"
    for lag in range(1, min(maximum + 1, len(x) // 3 + 1)):
        rho = float(np.dot(x[:-lag], x[lag:]) / denom)
        if not np.isfinite(rho) or abs(rho) < np.exp(-1.0):
            return int(np.clip(max(2, lag), minimum, maximum)), None
    return int(np.clip(fallback, minimum, maximum)), "autocorrelation did not decay inside bounded search"


def stationary_bootstrap_indices(n: int, *, mean_block_length: int, replications: int, seed: int) -> np.ndarray:
    if n <= 0 or replications <= 0:
        return np.empty((0, 0), dtype=int)
    rng = np.random.default_rng(seed)
    p_restart = 1.0 / max(1.0, float(mean_block_length))
    out = np.empty((replications, n), dtype=int)
    for r in range(replications):
        current = int(rng.integers(0, n))
        out[r, 0] = current
        for i in range(1, n):
            if rng.random() < p_restart:
                current = int(rng.integers(0, n))
            else:
                current = (current + 1) % n
            out[r, i] = current
    return out


class StationaryBootstrapService:
    def __init__(self, generation_id: Any, *, method_identity: str = METHOD_ID, replications: int = 160, confidence_level: float = 0.95):
        self.seed, self.seed_hash = deterministic_seed(generation_id, method_identity)
        self.replications = int(np.clip(replications, 40, MAX_REPLICATIONS))
        self.confidence_level = float(np.clip(confidence_level, 0.80, 0.995))

    def _distribution(self, values: Any, statistic: Callable[[np.ndarray], float], mean_block_length: int | None = None) -> tuple[np.ndarray, int, str | None]:
        x = np.asarray(values, dtype=float).reshape(-1)
        x = x[np.isfinite(x)]
        block, fallback = estimate_mean_block_length(x) if mean_block_length is None else (int(mean_block_length), None)
        if len(x) == 0:
            return np.asarray([], dtype=float), block, fallback
        indices = stationary_bootstrap_indices(len(x), mean_block_length=block, replications=self.replications, seed=self.seed)
        stats = np.asarray([statistic(x[idx]) for idx in indices], dtype=float)
        return stats[np.isfinite(stats)], block, fallback

    def interval(self, values: Any, statistic: Callable[[np.ndarray], float] = np.mean) -> dict[str, Any]:
        started = time.perf_counter()
        dist, block, fallback = self._distribution(values, statistic)
        alpha = 1.0 - self.confidence_level
        if len(dist) == 0:
            return {"status": "INSUFFICIENT_EVIDENCE", "replication_count": 0, "mean_block_length": block, "seed_hash": self.seed_hash, "fallback_reason": fallback}
        return {
            "status": "AVAILABLE",
            "estimate": finite(statistic(np.asarray(values, dtype=float)[np.isfinite(np.asarray(values, dtype=float))])),
            "lower": finite(np.quantile(dist, alpha / 2.0)),
            "upper": finite(np.quantile(dist, 1.0 - alpha / 2.0)),
            "replication_count": int(len(dist)),
            "mean_block_length": int(block),
            "seed_hash": self.seed_hash,
            "confidence_level": self.confidence_level,
            "runtime_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "fallback_reason": fallback,
        }

    def mean(self, values: Any) -> dict[str, Any]:
        return self.interval(values, np.mean)

    def loss_difference(self, first: Any, second: Any) -> dict[str, Any]:
        a = np.asarray(first, dtype=float); b = np.asarray(second, dtype=float)
        n = min(len(a), len(b)); return self.mean((a[:n] - b[:n]) if n else [])

    def correlation(self, first: Any, second: Any) -> dict[str, Any]:
        a = np.asarray(first, dtype=float); b = np.asarray(second, dtype=float); n = min(len(a), len(b))
        if n < MIN_SAMPLE:
            return {"status": "INSUFFICIENT_EVIDENCE", "sample_count": n, "minimum_sample_required": MIN_SAMPLE}
        pair = np.column_stack([a[:n], b[:n]])
        pair = pair[np.isfinite(pair).all(axis=1)]
        if len(pair) < MIN_SAMPLE:
            return {"status": "INSUFFICIENT_EVIDENCE", "sample_count": len(pair), "minimum_sample_required": MIN_SAMPLE}
        started = time.perf_counter(); block, fallback = estimate_mean_block_length(pair[:, 0]); idx = stationary_bootstrap_indices(len(pair), mean_block_length=block, replications=self.replications, seed=self.seed)
        dist = np.asarray([np.corrcoef(pair[i, 0], pair[i, 1])[0, 1] for i in idx], dtype=float); dist = dist[np.isfinite(dist)]
        alpha = 1.0 - self.confidence_level
        return {"status": "AVAILABLE", "estimate": finite(np.corrcoef(pair[:,0], pair[:,1])[0,1]), "lower": finite(np.quantile(dist, alpha/2)), "upper": finite(np.quantile(dist, 1-alpha/2)), "replication_count": len(dist), "mean_block_length": block, "seed_hash": self.seed_hash, "confidence_level": self.confidence_level, "runtime_ms": round((time.perf_counter()-started)*1000,3), "fallback_reason": fallback}

    def covariance_interval(self, matrix: Any) -> dict[str, Any]:
        x = np.asarray(matrix, dtype=float)
        if x.ndim != 2 or x.shape[0] < MIN_SAMPLE:
            return {"status": "INSUFFICIENT_EVIDENCE", "sample_count": int(x.shape[0] if x.ndim == 2 else 0)}
        valid = x[np.isfinite(x).all(axis=1)]
        block, fallback = estimate_mean_block_length(valid[:, 0]); idx = stationary_bootstrap_indices(len(valid), mean_block_length=block, replications=min(100, self.replications), seed=self.seed)
        covs = np.asarray([np.cov(valid[i], rowvar=False) for i in idx])
        alpha = 1.0 - self.confidence_level
        return {"status": "AVAILABLE", "lower": np.quantile(covs, alpha/2, axis=0).tolist(), "upper": np.quantile(covs, 1-alpha/2, axis=0).tolist(), "replication_count": len(covs), "mean_block_length": block, "seed_hash": self.seed_hash, "fallback_reason": fallback}


def run_stationary_bootstrap(values: Any, *, generation_id: Any, cutoff_time: Any) -> dict[str, Any]:
    x = np.asarray(values, dtype=float).reshape(-1); x = x[np.isfinite(x)]
    service = StationaryBootstrapService(generation_id)
    metrics = service.mean(x) if len(x) >= MIN_SAMPLE else {"status": "INSUFFICIENT_EVIDENCE"}
    status = "DEPENDENCE_PRESERVED" if metrics.get("status") == "AVAILABLE" else "INSUFFICIENT_EVIDENCE"
    return common_method(METHOD_ID, status=status, sample_count=len(x), minimum_sample_required=MIN_SAMPLE, cutoff_time=cutoff_time, output_metrics=metrics, assumptions=["weakly stationary local dependence", "geometric block restart law"], limitations=["bounded replications for Streamlit Cloud", "bootstrap samples are never published as market history"])


__all__ = ["StationaryBootstrapService", "estimate_mean_block_length", "stationary_bootstrap_indices", "run_stationary_bootstrap"]
