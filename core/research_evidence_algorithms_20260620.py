"""Read-only research algorithms used by the history evidence pipeline.

The functions in this module never create or reverse a trade direction.  They
produce cache diagnostics, display downsampling, similarity/changepoint
metadata, calibrated intervals, a reconciled display path, and validation
statistics from already-published model outputs.
"""
from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass
from math import erfc, sqrt
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# TinyLFU-style bounded cache admission
# ---------------------------------------------------------------------------
@dataclass
class CacheEntry:
    value: Any
    size_bytes: int
    admitted_at: int
    last_access: int


class TinyLFUCache:
    """Small exact-frequency TinyLFU-style admission cache.

    For the app's bounded display artifacts an exact frequency table is cheaper
    and easier to audit than a probabilistic sketch.  The policy remains the
    TinyLFU admission rule: a candidate displaces the LRU victim only when the
    candidate's recent frequency is at least the victim's frequency.  Counts are
    periodically halved to age the frequency sample.
    """

    def __init__(self, max_entries: int = 32, max_bytes: int = 8_000_000, sample_size: int = 10_000) -> None:
        self.max_entries = max(1, int(max_entries))
        self.max_bytes = max(1024, int(max_bytes))
        self.sample_size = max(64, int(sample_size))
        self._data: OrderedDict[str, CacheEntry] = OrderedDict()
        self._freq: Counter[str] = Counter()
        self._ticks = 0
        self._bytes = 0
        self.hits = 0
        self.misses = 0
        self.admissions = 0
        self.rejections = 0
        self.evictions = 0

    def _touch_frequency(self, key: str) -> None:
        self._ticks += 1
        self._freq[str(key)] += 1
        if self._ticks >= self.sample_size:
            self._freq = Counter({k: max(1, v // 2) for k, v in self._freq.items() if v > 1})
            self._ticks = 0

    def get(self, key: str, default: Any = None) -> Any:
        key = str(key)
        self._touch_frequency(key)
        entry = self._data.get(key)
        if entry is None:
            self.misses += 1
            return default
        self.hits += 1
        entry.last_access = self._ticks
        self._data.move_to_end(key)
        return entry.value

    def put(self, key: str, value: Any, *, size_bytes: int = 1) -> bool:
        key = str(key)
        size = max(1, int(size_bytes))
        self._touch_frequency(key)
        if size > self.max_bytes:
            self.rejections += 1
            return False
        existing = self._data.pop(key, None)
        if existing is not None:
            self._bytes -= existing.size_bytes
        candidate_freq = self._freq[key]
        while self._data and (len(self._data) >= self.max_entries or self._bytes + size > self.max_bytes):
            victim_key, victim = next(iter(self._data.items()))
            if candidate_freq < self._freq[victim_key]:
                if existing is not None:
                    self._data[key] = existing
                    self._bytes += existing.size_bytes
                self.rejections += 1
                return False
            self._data.pop(victim_key)
            self._bytes -= victim.size_bytes
            self.evictions += 1
        self._data[key] = CacheEntry(value=value, size_bytes=size, admitted_at=self._ticks, last_access=self._ticks)
        self._bytes += size
        self.admissions += 1
        return True

    def diagnostics(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "policy": "TinyLFU-style frequency admission + LRU victim",
            "entries": len(self._data),
            "bytes": self._bytes,
            "max_entries": self.max_entries,
            "max_bytes": self.max_bytes,
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": round(self.hits / total, 6) if total else 0.0,
            "admissions": self.admissions,
            "rejections": self.rejections,
            "evictions": self.evictions,
        }


# ---------------------------------------------------------------------------
# M4 display aggregation
# ---------------------------------------------------------------------------
def m4_downsample(frame: pd.DataFrame, *, x_col: str, y_col: str, max_points: int) -> pd.DataFrame:
    """Preserve first/last/min/max per visual bucket; calculations use raw data."""
    if not isinstance(frame, pd.DataFrame) or frame.empty or x_col not in frame or y_col not in frame:
        return pd.DataFrame(columns=[x_col, y_col])
    work = frame[[x_col, y_col]].dropna().reset_index(drop=True)
    if len(work) <= max(4, int(max_points)):
        return work
    buckets = max(1, int(max_points) // 4)
    bucket_id = np.floor(np.arange(len(work)) * buckets / len(work)).astype(int)
    keep: list[int] = []
    values = pd.to_numeric(work[y_col], errors="coerce")
    for bucket in range(buckets):
        idx = np.flatnonzero(bucket_id == bucket)
        if idx.size == 0:
            continue
        sub = values.iloc[idx]
        first = int(idx[0]); last = int(idx[-1])
        minimum = int(idx[int(np.nanargmin(sub.to_numpy(dtype=float)))]) if sub.notna().any() else first
        maximum = int(idx[int(np.nanargmax(sub.to_numpy(dtype=float)))]) if sub.notna().any() else last
        keep.extend((first, minimum, maximum, last))
    keep = sorted(set(keep))
    return work.iloc[keep].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Matrix Profile-inspired bounded current-query joins
# ---------------------------------------------------------------------------
def _znorm(values: np.ndarray) -> np.ndarray | None:
    values = np.asarray(values, dtype=float)
    if values.size == 0 or not np.isfinite(values).all():
        return None
    sd = float(values.std(ddof=0))
    if sd <= 1e-12:
        return None
    return (values - float(values.mean())) / sd


def matrix_profile_current_matches(
    close: Sequence[float],
    *,
    windows: Sequence[int] = (6, 12, 24),
    top_k: int = 8,
    max_history: int = 1200,
) -> dict[str, Any]:
    """Find bounded non-overlapping matches for the latest normalized windows."""
    values = pd.to_numeric(pd.Series(close), errors="coerce").dropna().to_numpy(dtype=float)
    values = values[-max(64, int(max_history)):]
    output: dict[str, Any] = {"windows": {}, "motifs": [], "discords": []}
    for raw_w in windows:
        w = int(raw_w)
        if w < 3 or len(values) < w * 3:
            output["windows"][str(w)] = {"status": "INSUFFICIENT DATA", "matches": []}
            continue
        query = _znorm(values[-w:])
        if query is None:
            output["windows"][str(w)] = {"status": "CONSTANT QUERY", "matches": []}
            continue
        latest_start = len(values) - w
        exclusion = max(1, w // 2)
        rows: list[dict[str, Any]] = []
        for start in range(0, latest_start - exclusion + 1):
            candidate = _znorm(values[start:start + w])
            if candidate is None:
                continue
            distance = float(np.linalg.norm(query - candidate) / sqrt(w))
            rows.append({"start_index": start, "end_index": start + w - 1, "distance": distance})
        rows.sort(key=lambda row: row["distance"])
        selected: list[dict[str, Any]] = []
        for row in rows:
            if any(abs(row["start_index"] - prior["start_index"]) < exclusion for prior in selected):
                continue
            selected.append(row)
            if len(selected) >= int(top_k):
                break
        finite = [row["distance"] for row in rows]
        for row in selected:
            row["similarity_percentile"] = round(100.0 * sum(d >= row["distance"] for d in finite) / max(len(finite), 1), 4)
        discord = max(rows, key=lambda row: row["distance"]) if rows else None
        output["windows"][str(w)] = {
            "status": "OK",
            "query_start_index": latest_start,
            "exclusion_zone": exclusion,
            "candidate_count": len(rows),
            "matches": selected,
            "discord": discord,
        }
        output["motifs"].extend({"window": w, **row} for row in selected[:3])
        if discord:
            output["discords"].append({"window": w, **discord})
    return output


# ---------------------------------------------------------------------------
# PELT for squared-error mean changes
# ---------------------------------------------------------------------------
def pelt_mean_changes(values: Sequence[float], *, penalty: float | None = None, min_segment: int = 6, max_points: int = 1200) -> dict[str, Any]:
    """PELT-style mean changepoints with vectorized segment costs.

    The candidate set is pruned after every endpoint. No direction is produced;
    output is evidence only. Inputs are bounded to keep Streamlit Cloud CPU use
    predictable.
    """
    x = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(dtype=float)[-max_points:]
    n = len(x)
    min_seg = max(2, int(min_segment))
    if n < min_seg * 2:
        return {"status": "INSUFFICIENT DATA", "changepoints": [], "sample_count": n}
    variance = float(np.var(x))
    beta = float(penalty) if penalty is not None else max(1e-12, 2.0 * np.log(max(n, 2)) * max(variance, 1e-12))
    cs = np.concatenate(([0.0], np.cumsum(x)))
    cs2 = np.concatenate(([0.0], np.cumsum(x * x)))
    f = np.full(n + 1, np.inf, dtype=float)
    f[0] = -beta
    last = np.full(n + 1, -1, dtype=int)
    candidates = np.array([0], dtype=int)

    for t in range(min_seg, n + 1):
        valid = candidates[(t - candidates) >= min_seg]
        if valid.size == 0:
            candidate = t - min_seg + 1
            if candidate <= n:
                candidates = np.unique(np.append(candidates, candidate))
            continue
        lengths = t - valid
        sums = cs[t] - cs[valid]
        sums2 = cs2[t] - cs2[valid]
        costs = np.maximum(0.0, sums2 - (sums * sums) / lengths)
        totals = f[valid] + costs + beta
        best_pos = int(np.argmin(totals))
        f[t] = float(totals[best_pos])
        last[t] = int(valid[best_pos])
        # PELT pruning (K=0 for squared-error segment cost).
        keep = valid[(f[valid] + costs) <= (f[t] + beta)]
        new_candidate = t - min_seg + 1
        candidates = np.unique(np.append(keep, new_candidate)) if new_candidate <= n else keep

    if not np.isfinite(f[n]):
        return {"status": "INSUFFICIENT DATA", "changepoints": [], "sample_count": n}
    cps: list[int] = []
    cursor = n
    while cursor > 0 and last[cursor] >= 0:
        previous = int(last[cursor])
        if previous > 0:
            cps.append(previous)
        cursor = previous
    cps = sorted(set(cps))
    return {
        "status": "OK",
        "changepoints": cps,
        "sample_count": n,
        "penalty": beta,
        "min_segment": min_seg,
        "objective": float(f[n]),
        "direction_created": False,
    }


# ---------------------------------------------------------------------------
# Chronological conformalized quantile calibration
# ---------------------------------------------------------------------------
def conformalized_quantile_interval(
    settled: pd.DataFrame,
    *,
    point: float,
    lower: float,
    upper: float,
    horizon: int,
    alpha: float = 0.20,
    min_samples: int = 20,
) -> dict[str, Any]:
    """Calibrate one horizon using settled chronological nonconformity scores."""
    if not isinstance(settled, pd.DataFrame) or settled.empty:
        return {"status": "INSUFFICIENT DATA", "lower": lower, "median": point, "upper": upper, "sample_count": 0, "horizon": horizon}
    work = settled.copy(deep=False)
    horizon_cols = [c for c in ("horizon", "Horizon", "h") if c in work.columns]
    if horizon_cols:
        work = work[pd.to_numeric(work[horizon_cols[0]], errors="coerce") == int(horizon)]
    actual_col = next((c for c in ("actual_close", "Actual Close", "actual", "y_true") if c in work.columns), None)
    lo_col = next((c for c in ("lower", "lower_bound", "Lower") if c in work.columns), None)
    hi_col = next((c for c in ("upper", "upper_bound", "Upper") if c in work.columns), None)
    if not actual_col or not lo_col or not hi_col:
        return {"status": "INSUFFICIENT DATA", "lower": lower, "median": point, "upper": upper, "sample_count": 0, "horizon": horizon}
    actual = pd.to_numeric(work[actual_col], errors="coerce")
    lo = pd.to_numeric(work[lo_col], errors="coerce")
    hi = pd.to_numeric(work[hi_col], errors="coerce")
    scores = pd.concat([lo - actual, actual - hi], axis=1).max(axis=1).dropna().clip(lower=0)
    n = len(scores)
    if n < int(min_samples):
        return {"status": "INSUFFICIENT DATA", "lower": lower, "median": point, "upper": upper, "sample_count": n, "horizon": horizon}
    rank = min(n - 1, max(0, int(np.ceil((n + 1) * (1 - alpha))) - 1))
    q = float(np.sort(scores.to_numpy(dtype=float))[rank])
    return {
        "status": "CALIBRATED",
        "lower": float(lower) - q,
        "median": float(point),
        "upper": float(upper) + q,
        "sample_count": n,
        "horizon": int(horizon),
        "alpha": float(alpha),
        "nonconformity_quantile": q,
        "chronological_calibration": True,
        "exchangeability_warning": "Serial EURUSD H1 data do not satisfy the original exchangeable-data guarantee.",
    }


# ---------------------------------------------------------------------------
# MinT-inspired shrinkage reconciliation of source display paths
# ---------------------------------------------------------------------------
def mint_reconcile_display_paths(
    source_paths: Mapping[str, Sequence[float]],
    *,
    anchor_price: float,
    residual_history: pd.DataFrame | None = None,
    shrinkage: float = 0.25,
) -> dict[str, Any]:
    """Reconcile a display copy while retaining every original source path."""
    clean: dict[str, np.ndarray] = {}
    for name, values in source_paths.items():
        materialized = list(values)
        if materialized:
            clean[str(name)] = np.asarray(materialized, dtype=float)
    if not clean:
        return {"status": "INSUFFICIENT DATA", "original_paths": {}, "reconciled_path": []}
    horizon = min(len(values) for values in clean.values())
    names = sorted(clean)
    levels = np.vstack([clean[name][:horizon] for name in names])
    moves = np.diff(np.column_stack([np.full(len(names), float(anchor_price)), levels]), axis=1)
    n_sources = len(names)
    covariance = np.eye(n_sources)
    if isinstance(residual_history, pd.DataFrame) and not residual_history.empty:
        candidate_cols = [name for name in names if name in residual_history.columns]
        if len(candidate_cols) == n_sources:
            raw = residual_history[candidate_cols].apply(pd.to_numeric, errors="coerce").dropna()
            if len(raw) >= max(8, n_sources + 2):
                sample_cov = np.cov(raw.to_numpy(dtype=float), rowvar=False)
                diagonal = np.diag(np.diag(sample_cov))
                covariance = (1.0 - float(shrinkage)) * sample_cov + float(shrinkage) * diagonal
    try:
        precision = np.linalg.pinv(covariance)
        ones = np.ones((n_sources, 1))
        weights = (precision @ ones / float((ones.T @ precision @ ones).item())).ravel()
    except Exception:
        weights = np.full(n_sources, 1.0 / n_sources)
    reconciled_moves = weights @ moves
    reconciled = float(anchor_price) + np.cumsum(reconciled_moves)
    deltas = {name: (reconciled - levels[i]).tolist() for i, name in enumerate(names)}
    return {
        "status": "RECONCILED",
        "method": "MinT-inspired shrinkage covariance display reconciliation",
        "source_names": names,
        "weights": {name: float(weights[i]) for i, name in enumerate(names)},
        "original_paths": {name: levels[i].tolist() for i, name in enumerate(names)},
        "reconciled_path": reconciled.tolist(),
        "reconciliation_deltas": deltas,
        "hourly_moves_coherent": True,
        "protected_paths_changed": False,
    }


# ---------------------------------------------------------------------------
# Diebold-Mariano forecast accuracy comparison
# ---------------------------------------------------------------------------
def diebold_mariano_test(loss_a: Iterable[float], loss_b: Iterable[float], *, horizon: int = 1, min_samples: int = 24) -> dict[str, Any]:
    a = pd.to_numeric(pd.Series(list(loss_a)), errors="coerce")
    b = pd.to_numeric(pd.Series(list(loss_b)), errors="coerce")
    valid = pd.concat([a, b], axis=1).dropna()
    n = len(valid)
    h = max(1, int(horizon))
    if n < max(int(min_samples), 3 * h + 5):
        return {"status": "INSUFFICIENT DATA", "sample_count": n, "horizon": h}
    d = valid.iloc[:, 0].to_numpy(dtype=float) - valid.iloc[:, 1].to_numpy(dtype=float)
    mean_d = float(np.mean(d))
    centered = d - mean_d
    gamma0 = float(centered @ centered / n)
    long_run = gamma0
    max_lag = min(h - 1, n - 2)
    for lag in range(1, max_lag + 1):
        gamma = float(centered[lag:] @ centered[:-lag] / n)
        weight = 1.0 - lag / (max_lag + 1.0)
        long_run += 2.0 * weight * gamma
    variance = max(long_run / n, 1e-18)
    statistic = mean_d / sqrt(variance)
    p_value = erfc(abs(statistic) / sqrt(2.0))
    return {
        "status": "OK",
        "sample_count": n,
        "horizon": h,
        "mean_loss_difference": mean_d,
        "dm_statistic": statistic,
        "p_value_two_sided": p_value,
        "hac_lags": max_lag,
        "interpretation": "A lower mean loss is better; this validates forecasts and never selects trade direction.",
    }


__all__ = [
    "TinyLFUCache", "m4_downsample", "matrix_profile_current_matches",
    "pelt_mean_changes", "conformalized_quantile_interval",
    "mint_reconcile_display_paths", "diebold_mariano_test",
]
