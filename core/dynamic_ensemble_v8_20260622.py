"""Shadow Bates-Granger, Fixed-Share and conditional trust evidence."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import math
import numpy as np
import pandas as pd

VERSION = "dynamic-ensemble-v8-20260622"


def _simplex(weights: np.ndarray, *, floor: float = 0.02, cap: float = 0.85) -> np.ndarray:
    w = np.nan_to_num(np.asarray(weights, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    w = np.maximum(w, 0.0)
    if w.sum() <= 0: w = np.ones_like(w)
    w /= w.sum()
    for _ in range(8):
        w = np.clip(w, floor, cap); w /= w.sum()
    return w


def bates_granger_weights(errors: pd.DataFrame, *, protected_weights: Mapping[str, float] | None = None, min_samples: int = 30, shrinkage: float = 0.25, floor: float = 0.02, cap: float = 0.85) -> dict[str, Any]:
    if not isinstance(errors, pd.DataFrame) or errors.shape[1] < 2:
        return {"status": "INSUFFICIENT_EVIDENCE", "weights": dict(protected_weights or {}), "sample_count": 0, "shadow_only": True}
    x = errors.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().tail(500)
    names = list(x.columns); n = len(x)
    protected = np.array([float((protected_weights or {}).get(name, 1.0 / len(names))) for name in names], dtype=float)
    protected = _simplex(protected, floor=0.0, cap=1.0)
    if n < min_samples:
        return {"status": "INSUFFICIENT_EVIDENCE", "weights": dict(zip(names, protected)), "sample_count": n, "shadow_only": True}
    cov = np.cov(x.to_numpy().T, ddof=1)
    if np.ndim(cov) == 0: cov = np.eye(len(names)) * float(cov)
    raw_rank_deficient = bool(np.linalg.matrix_rank(cov) < len(names))
    diag = np.diag(np.diag(cov)); cov = (1.0 - shrinkage) * cov + shrinkage * diag
    ones = np.ones(len(names))
    rank_deficient = raw_rank_deficient or bool(np.linalg.matrix_rank(cov) < len(names))
    ill_conditioned = bool(not np.isfinite(np.linalg.cond(cov)) or np.linalg.cond(cov) > 1e12)
    try:
        if rank_deficient or ill_conditioned:
            raise np.linalg.LinAlgError("singular or ill-conditioned covariance")
        inv = np.linalg.pinv(cov, hermitian=True); raw = inv @ ones; denominator = float(ones @ inv @ ones)
        if not np.isfinite(denominator) or abs(denominator) < 1e-12:
            raise np.linalg.LinAlgError("unstable covariance denominator")
        raw /= denominator; fallback = False
    except Exception:
        raw = 1.0 / np.maximum(np.diag(cov), 1e-12); fallback = True
    evidence = min(1.0, max(0.0, (n - min_samples) / max(min_samples * 3, 1)))
    weights = _simplex(evidence * raw + (1.0 - evidence) * protected, floor=floor, cap=cap)
    corr = x.corr().fillna(0.0).to_numpy(); avg_corr = float((corr.sum() - len(names)) / max(len(names) * (len(names) - 1), 1))
    effective = float(1.0 / np.square(weights).sum())
    return {"status": "AVAILABLE", "weights": dict(zip(names, weights)), "sample_count": n, "covariance": cov.tolist(), "average_error_correlation": avg_corr, "effective_expert_count": effective, "singular_fallback": fallback, "shadow_only": True, "production_influence_enabled": False}


def fixed_share_weights(losses: pd.DataFrame, *, previous_weights: Mapping[str, float] | None = None, learning_rate: float = 0.2, share: float = 0.03, floor: float = 0.01, cap: float = 0.90) -> dict[str, Any]:
    if not isinstance(losses, pd.DataFrame) or losses.shape[1] < 2:
        return {"status": "INSUFFICIENT_EVIDENCE", "weights": dict(previous_weights or {}), "shadow_only": True}
    x = losses.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().tail(1000)
    names = list(x.columns); m = len(names)
    w = np.array([float((previous_weights or {}).get(n, 1.0 / m)) for n in names]); w = _simplex(w, floor=floor, cap=cap)
    turnover = 0.0; switches = 0; prior_best = int(np.argmax(w))
    eta = min(2.0, max(1e-4, float(learning_rate))); rho = min(.25, max(0.0, float(share)))
    for row in x.to_numpy(dtype=float):
        old = w.copy(); centered = row - np.nanmin(row)
        w *= np.exp(-eta * np.clip(centered, 0, 50)); w = (1.0 - rho) * w + rho / m; w = _simplex(w, floor=floor, cap=cap)
        turnover += float(np.abs(w - old).sum()) / 2.0
        best = int(np.argmax(w)); switches += int(best != prior_best); prior_best = best
    return {"status": "AVAILABLE" if len(x) else "INSUFFICIENT_EVIDENCE", "weights": dict(zip(names, w)), "sample_count": int(len(x)), "weight_turnover": turnover, "expert_switches": switches, "learning_rate": eta, "fixed_share": rho, "shadow_only": True, "production_influence_enabled": False}


def conditional_trust_map(losses: pd.DataFrame, *, model_col: str = "model", loss_col: str = "loss", benchmark_col: str = "benchmark_loss", condition_cols: Sequence[str] = ("horizon_hours", "regime", "session", "overlap", "volatility_quartile", "conflict_status", "data_freshness", "drift_epoch"), min_samples: int = 30) -> pd.DataFrame:
    if not isinstance(losses, pd.DataFrame) or losses.empty or model_col not in losses or loss_col not in losses or benchmark_col not in losses:
        return pd.DataFrame(columns=[*condition_cols, model_col, "sample_count", "loss_differential", "trust_status"])
    cols = [c for c in condition_cols if c in losses.columns] + [model_col]
    work = losses.copy(deep=False); work[loss_col] = pd.to_numeric(work[loss_col], errors="coerce"); work[benchmark_col] = pd.to_numeric(work[benchmark_col], errors="coerce"); work = work.dropna(subset=[loss_col, benchmark_col]).tail(5000)
    rows = []
    for keys, group in work.groupby(cols, dropna=False, sort=False):
        keys = keys if isinstance(keys, tuple) else (keys,)
        n = len(group); diff = float((group[loss_col] - group[benchmark_col]).mean())
        if n < min_samples: status = "NOT TESTABLE"
        else:
            se = float((group[loss_col] - group[benchmark_col]).std(ddof=1) / math.sqrt(n)) if n > 1 else float("inf")
            status = "TRUSTED" if diff < -1.96 * se else "WEAK" if diff > 1.96 * se else "MIXED"
        rows.append({**dict(zip(cols, keys)), "sample_count": n, "loss_differential": diff, "trust_status": status})
    return pd.DataFrame(rows)

__all__ = ["bates_granger_weights", "fixed_share_weights", "conditional_trust_map", "VERSION"]
