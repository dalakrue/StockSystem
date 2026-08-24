"""True probabilistic forecast evaluation utilities (2026-06-24).

Shadow-only helpers.  They never modify protected Field 1, production decisions,
model weights or historical canonical rows.  All functions are deterministic and
safe for Python 3.12/Streamlit Cloud.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from statistics import NormalDist
from typing import Any, Iterable, Mapping, Sequence
import math
import numpy as np
import pandas as pd

VERSION = "probabilistic-evaluation-20260624-v1"
_STD_NORMAL = NormalDist()


def _finite(x: Any) -> float | None:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except Exception:
        return None


def gaussian_crps(mean: Any, std: Any, actual: Any) -> float | None:
    """Analytic CRPS for a Gaussian predictive distribution.

    Formula: sigma * [z(2Phi(z)-1)+2phi(z)-1/sqrt(pi)].  Returns None when
    inputs are unavailable; it never falls back to absolute error.
    """
    mu = _finite(mean); sig = _finite(std); y = _finite(actual)
    if mu is None or sig is None or sig <= 0.0 or y is None:
        return None
    z = (y - mu) / sig
    phi = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    Phi = _STD_NORMAL.cdf(z)
    out = sig * (z * (2.0 * Phi - 1.0) + 2.0 * phi - 1.0 / math.sqrt(math.pi))
    return float(max(out, 0.0)) if math.isfinite(out) else None


def sample_crps(samples: Iterable[Any], actual: Any) -> float | None:
    """Unbiased sample CRPS: E|X-y| - 0.5 E|X-X'|."""
    y = _finite(actual)
    arr = pd.to_numeric(pd.Series(list(samples or [])), errors="coerce").dropna().to_numpy(dtype=float)
    if y is None or arr.size == 0:
        return None
    term1 = float(np.mean(np.abs(arr - y)))
    sorted_arr = np.sort(arr)
    n = sorted_arr.size
    if n <= 1:
        term2 = 0.0
    else:
        # O(n log n) mean pairwise absolute difference.
        coeff = (2 * np.arange(1, n + 1) - n - 1).astype(float)
        pairwise_mean = float(2.0 * np.sum(coeff * sorted_arr) / (n * n))
        term2 = 0.5 * pairwise_mean
    out = term1 - term2
    return float(max(out, 0.0)) if math.isfinite(out) else None


def quantile_crps_fallback(quantiles: Mapping[Any, Any] | Sequence[tuple[Any, Any]], actual: Any) -> float | None:
    """Documented fallback using pinball losses over available quantiles.

    This is only used when Gaussian std and forecast samples do not exist.
    """
    y = _finite(actual)
    if y is None or quantiles is None:
        return None
    items = quantiles.items() if isinstance(quantiles, Mapping) else list(quantiles)
    losses: list[float] = []
    for q, value in items:
        tau = _finite(q); pred = _finite(value)
        if tau is None or pred is None or not (0.0 < tau < 1.0):
            continue
        diff = y - pred
        losses.append(2.0 * (tau * max(diff, 0.0) + (1.0 - tau) * max(-diff, 0.0)))
    return float(np.mean(losses)) if losses else None


def true_crps(*, mean: Any = None, std: Any = None, samples: Iterable[Any] | None = None,
              quantiles: Mapping[Any, Any] | Sequence[tuple[Any, Any]] | None = None,
              actual: Any = None) -> tuple[float | None, str]:
    g = gaussian_crps(mean, std, actual)
    if g is not None:
        return g, "gaussian_analytic"
    s = sample_crps(samples or [], actual)
    if s is not None:
        return s, "sample"
    q = quantile_crps_fallback(quantiles or {}, actual)
    if q is not None:
        return q, "quantile_fallback"
    return None, "unavailable"


@dataclass(frozen=True)
class HorizonMetrics:
    horizon: str
    sample_count: int
    mae: float | None
    rmse: float | None
    crps: float | None
    crps_method: str
    coverage: float | None
    mean_interval_width: float | None
    coverage_width_criterion: float | None
    direction_accuracy: float | None
    calibration_error: float | None


def evaluate_horizon(frame: pd.DataFrame, *, horizon: str, nominal_coverage: float = 0.90) -> dict[str, Any]:
    """Evaluate one matured horizon; MAE is always separate from CRPS."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return asdict(HorizonMetrics(horizon, 0, None, None, None, "unavailable", None, None, None, None, None))
    df = frame.copy(deep=False)
    actual = pd.to_numeric(df.get("matured_actual"), errors="coerce")
    mean = pd.to_numeric(df.get("origin_mean", df.get("origin_median")), errors="coerce")
    valid = actual.notna() & mean.notna()
    errors = (mean[valid] - actual[valid]).astype(float)
    mae = float(np.mean(np.abs(errors))) if len(errors) else None
    rmse = float(np.sqrt(np.mean(np.square(errors)))) if len(errors) else None
    lower = pd.to_numeric(df.get("origin_lower"), errors="coerce")
    upper = pd.to_numeric(df.get("origin_upper"), errors="coerce")
    interval_mask = actual.notna() & lower.notna() & upper.notna()
    coverage = float(((actual[interval_mask] >= lower[interval_mask]) & (actual[interval_mask] <= upper[interval_mask])).mean()) if interval_mask.any() else None
    width = float((upper[interval_mask] - lower[interval_mask]).mean()) if interval_mask.any() else None
    cwc = None if coverage is None or width is None else float(width * (1.0 + max(0.0, nominal_coverage - coverage)))
    dir_acc = None
    if "origin_price" in df:
        origin = pd.to_numeric(df.get("origin_price"), errors="coerce")
        dmask = actual.notna() & mean.notna() & origin.notna()
        if dmask.any():
            dir_acc = float((np.sign(mean[dmask] - origin[dmask]) == np.sign(actual[dmask] - origin[dmask])).mean())
    crps_vals: list[float] = []
    methods: dict[str, int] = {}
    for _, row in df.iterrows():
        samples = row.get("origin_samples")
        quantiles = row.get("origin_quantiles")
        if isinstance(samples, str):
            try:
                import json; samples = json.loads(samples)
            except Exception:
                samples = []
        if isinstance(quantiles, str):
            try:
                import json; quantiles = json.loads(quantiles)
            except Exception:
                quantiles = {}
        val, method = true_crps(mean=row.get("origin_mean"), std=row.get("origin_std"), samples=samples or [], quantiles=quantiles or {}, actual=row.get("matured_actual"))
        if val is not None:
            crps_vals.append(val); methods[method] = methods.get(method, 0) + 1
    crps = float(np.mean(crps_vals)) if crps_vals else None
    crps_method = max(methods.items(), key=lambda kv: kv[1])[0] if methods else "unavailable"
    calib = None if coverage is None else float(abs(nominal_coverage - coverage))
    return asdict(HorizonMetrics(str(horizon), int(len(errors)), mae, rmse, crps, crps_method, coverage, width, cwc, dir_acc, calib))


def pesaran_timmermann_test(predicted_direction: Iterable[Any], actual_direction: Iterable[Any]) -> dict[str, Any]:
    p = pd.Series(list(predicted_direction)).map(lambda x: 1 if str(x).upper().startswith("BUY") or _finite(x) and float(x) > 0 else 0 if str(x).upper().startswith("SELL") or _finite(x) and float(x) < 0 else np.nan)
    a = pd.Series(list(actual_direction)).map(lambda x: 1 if str(x).upper().startswith("BUY") or _finite(x) and float(x) > 0 else 0 if str(x).upper().startswith("SELL") or _finite(x) and float(x) < 0 else np.nan)
    mask = p.notna() & a.notna(); p = p[mask].astype(int); a = a[mask].astype(int); n = int(len(p))
    if n < 8:
        return {"sample_count": n, "status": "INSUFFICIENT EVIDENCE", "significant": False}
    phat = float((p == a).mean()); px = float(p.mean()); py = float(a.mean())
    expected = px * py + (1 - px) * (1 - py)
    var = max(expected * (1 - expected) / n, 1e-12)
    stat = (phat - expected) / math.sqrt(var)
    pval = 2.0 * (1.0 - _STD_NORMAL.cdf(abs(stat)))
    return {"observed_direction_accuracy": phat, "expected_accuracy_under_independence": expected, "pt_statistic": float(stat), "p_value": float(pval), "sample_count": n, "BUY_frequency": px, "SELL_frequency": 1-px, "actual_up_frequency": py, "actual_down_frequency": 1-py, "imbalance_warning": bool(px < 0.1 or px > 0.9 or py < 0.1 or py > 0.9), "statistically_significant_directional_skill": bool(pval < 0.05 and phat > expected), "significant": bool(pval < 0.05 and phat > expected)}


def diebold_mariano_test(loss_a: Iterable[Any], loss_b: Iterable[Any], *, horizon: int = 1) -> dict[str, Any]:
    a = pd.to_numeric(pd.Series(list(loss_a)), errors="coerce")
    b = pd.to_numeric(pd.Series(list(loss_b)), errors="coerce")
    mask = a.notna() & b.notna(); d = (a[mask] - b[mask]).to_numpy(dtype=float); n = len(d)
    if n < 8:
        return {"sample_count": int(n), "status": "INSUFFICIENT EVIDENCE", "winner": "NONE"}
    mean_d = float(np.mean(d)); lag = max(0, int(horizon) - 1)
    gamma0 = float(np.mean((d - mean_d) ** 2))
    var = gamma0
    for k in range(1, min(lag, n - 1) + 1):
        cov = float(np.mean((d[k:] - mean_d) * (d[:-k] - mean_d)))
        var += 2.0 * (1.0 - k / (lag + 1.0)) * cov
    se = math.sqrt(max(var / n, 1e-12)); stat = mean_d / se
    pval = 2.0 * (1.0 - _STD_NORMAL.cdf(abs(stat)))
    winner = "B" if mean_d > 0 and pval < 0.05 else "A" if mean_d < 0 and pval < 0.05 else "TIE/INSIGNIFICANT"
    return {"dm_statistic": float(stat), "p_value": float(pval), "mean_loss_difference_A_minus_B": mean_d, "sample_count": int(n), "winner": winner, "hac_lag": int(lag)}


__all__ = ["VERSION", "gaussian_crps", "sample_crps", "quantile_crps_fallback", "true_crps", "evaluate_horizon", "pesaran_timmermann_test", "diebold_mariano_test"]
