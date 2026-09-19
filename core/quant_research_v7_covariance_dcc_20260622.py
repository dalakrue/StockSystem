"""Ledoit-Wolf covariance diagnostics and bounded DCC shadow evidence."""
from __future__ import annotations

from typing import Any, Mapping
import time

import numpy as np
import pandas as pd

from core.quant_research_v7_contract_20260622 import common_method, finite

COV_METHOD = "ledoit_wolf_covariance"
DCC_METHOD = "dynamic_conditional_correlation"
MIN_COV_SAMPLE = 30
MIN_DCC_SAMPLE = 48


def _matrix_diagnostics(matrix: np.ndarray) -> dict[str, Any]:
    m = np.asarray(matrix, dtype=float)
    if m.ndim != 2 or m.shape[0] != m.shape[1] or not np.isfinite(m).all():
        return {"condition_number": None, "minimum_eigenvalue": None, "effective_rank": None, "positive_semidefinite": False}
    eig = np.linalg.eigvalsh((m + m.T) / 2.0)
    positive = np.clip(eig, 0.0, None)
    total = positive.sum()
    if total > 0:
        p = positive / total
        entropy = -float(np.sum(p[p > 0] * np.log(p[p > 0])))
        effective_rank = float(np.exp(entropy))
    else:
        effective_rank = 0.0
    try:
        condition = float(np.linalg.cond(m))
    except Exception:
        condition = float("inf")
    return {
        "condition_number": finite(condition),
        "minimum_eigenvalue": finite(np.min(eig)),
        "effective_rank": finite(effective_rank),
        "positive_semidefinite": bool(np.min(eig) >= -1e-9),
    }


def _returns_from_market_history(market_history: pd.DataFrame) -> dict[str, pd.Series]:
    if not isinstance(market_history, pd.DataFrame) or market_history.empty:
        return {}
    lower = {str(c).lower(): c for c in market_history.columns}
    time_col = lower.get("event_time_utc") or lower.get("time")
    symbol_col = lower.get("symbol"); tf_col = lower.get("timeframe"); close_col = lower.get("close")
    if not all((time_col, symbol_col, tf_col, close_col)):
        return {}
    frame = market_history.copy(deep=False)
    frame = frame.assign(__time=pd.to_datetime(frame[time_col], errors="coerce", utc=True), __close=pd.to_numeric(frame[close_col], errors="coerce"))
    out = {}
    for (symbol, timeframe), group in frame.dropna(subset=["__time", "__close"]).groupby([symbol_col, tf_col], sort=False):
        g = group.sort_values("__time").drop_duplicates("__time", keep="last")
        key = f"{str(symbol).upper()}_{str(timeframe).upper()}"
        out[key] = pd.Series(g["__close"].pct_change().to_numpy(), index=g["__time"]).dropna()
    return out


def _settled_numeric_columns(settled: pd.DataFrame) -> list[pd.Series]:
    if not isinstance(settled, pd.DataFrame) or settled.empty:
        return []
    preferred = []
    for col in settled.columns:
        name = str(col).lower()
        if any(token in name for token in ("residual", "forecast_error", "absolute_forecast_error", "error", "signal_change", "risk")):
            values = pd.to_numeric(settled[col], errors="coerce")
            if values.notna().sum() >= MIN_COV_SAMPLE:
                preferred.append(values.reset_index(drop=True))
    return preferred[:8]


def run_ledoit_wolf_covariance(
    settled: pd.DataFrame,
    market_history: pd.DataFrame,
    *,
    cutoff_time: Any,
) -> dict[str, Any]:
    started = time.perf_counter()
    series = _settled_numeric_columns(settled)
    labels = [f"settled_{i+1}" for i in range(len(series))]
    returns = _returns_from_market_history(market_history)
    for key in ("EURUSD_H1", "XAUUSD_H1", "EURUSD_M1", "XAUUSD_M1"):
        if key in returns and len(returns[key]) >= MIN_COV_SAMPLE:
            series.append(returns[key].reset_index(drop=True)); labels.append(key)
    if len(series) < 2:
        return common_method(COV_METHOD, status="INSUFFICIENT_EVIDENCE", sample_count=max([len(s) for s in series], default=0), minimum_sample_required=MIN_COV_SAMPLE, cutoff_time=cutoff_time, output_metrics={"available_dimensions": labels, "fallback": "diagonal covariance"}, assumptions=["finite second moments"], limitations=["requires at least two aligned evidence dimensions"])
    n = min(len(s) for s in series)
    matrix = np.column_stack([s.iloc[-n:].to_numpy(dtype=float) for s in series])
    matrix = matrix[np.isfinite(matrix).all(axis=1)]
    if len(matrix) < MIN_COV_SAMPLE:
        return common_method(COV_METHOD, status="INSUFFICIENT_EVIDENCE", sample_count=len(matrix), minimum_sample_required=MIN_COV_SAMPLE, cutoff_time=cutoff_time, output_metrics={"available_dimensions": labels, "fallback": "diagonal covariance"}, assumptions=["finite second moments"], limitations=["alignment reduced support below minimum"])
    raw = np.cov(matrix, rowvar=False)
    try:
        from sklearn.covariance import LedoitWolf
        estimator = LedoitWolf(store_precision=False, assume_centered=False).fit(matrix)
        shrunk = estimator.covariance_
        shrinkage = float(estimator.shrinkage_)
        fallback = None
    except Exception as exc:
        diag = np.diag(np.diag(raw))
        shrinkage = 0.5
        shrunk = (1.0 - shrinkage) * raw + shrinkage * diag
        fallback = f"manual diagonal shrinkage: {type(exc).__name__}"
    raw_diag = _matrix_diagnostics(raw); shrunk_diag = _matrix_diagnostics(shrunk)
    try:
        inv = np.linalg.pinv(shrunk)
        ones = np.ones(len(labels)); weights = inv @ ones; weights = weights / max(1e-12, np.sum(np.abs(weights)))
    except Exception:
        weights = np.repeat(1.0 / len(labels), len(labels))
    output = {
        "dimensions": labels,
        "shrinkage_intensity": round(shrinkage, 6),
        "raw_condition_number": raw_diag["condition_number"],
        "shrunk_condition_number": shrunk_diag["condition_number"],
        "raw_minimum_eigenvalue": raw_diag["minimum_eigenvalue"],
        "shrunk_minimum_eigenvalue": shrunk_diag["minimum_eigenvalue"],
        "effective_rank": shrunk_diag["effective_rank"],
        "positive_semidefinite_status": shrunk_diag["positive_semidefinite"],
        "conditioning_improved_or_equal": bool((shrunk_diag["condition_number"] or float("inf")) <= (raw_diag["condition_number"] or float("inf")) + 1e-9),
        "shadow_covariance_aware_weight_recommendation": {label: round(float(weight), 6) for label, weight in zip(labels, weights)},
        "fallback_reason": fallback,
        "runtime_ms": round((time.perf_counter() - started) * 1000.0, 3),
    }
    return common_method(COV_METHOD, status="AVAILABLE", sample_count=len(matrix), minimum_sample_required=MIN_COV_SAMPLE, cutoff_time=cutoff_time, output_metrics=output, assumptions=["locally stable covariance", "aligned completed observations only"], limitations=["weight recommendation is shadow-only and never overwrites protected forecast weights"])


def _ewma_standardize(values: np.ndarray, lam: float = 0.94) -> np.ndarray:
    x = np.asarray(values, dtype=float)
    variance = np.empty_like(x)
    variance[0] = max(float(np.nanvar(x[: min(24, len(x))])), 1e-12)
    for i in range(1, len(x)):
        variance[i] = lam * variance[i - 1] + (1.0 - lam) * x[i - 1] ** 2
    return x / np.sqrt(np.maximum(variance, 1e-12))


def dcc_recursion(standardized: np.ndarray, *, a: float = 0.04, b: float = 0.94) -> list[np.ndarray]:
    if a < 0 or b < 0 or a + b >= 1:
        raise ValueError("DCC constraints require a>=0, b>=0 and a+b<1")
    z = np.asarray(standardized, dtype=float)
    qbar = np.cov(z, rowvar=False)
    q = qbar.copy()
    out = []
    for row in z:
        outer = np.outer(row, row)
        q = (1.0 - a - b) * qbar + a * outer + b * q
        scale = np.sqrt(np.maximum(np.diag(q), 1e-12))
        r = q / np.outer(scale, scale)
        r = np.clip((r + r.T) / 2.0, -1.0, 1.0)
        np.fill_diagonal(r, 1.0)
        out.append(r)
    return out


def run_dynamic_conditional_correlation(market_history: pd.DataFrame, *, cutoff_time: Any, canonical: Mapping[str, Any] | None = None) -> dict[str, Any]:
    started = time.perf_counter(); returns = _returns_from_market_history(market_history)
    pairs = [("EURUSD_H1", "XAUUSD_H1"), ("EURUSD_M1", "XAUUSD_M1"), ("EURUSD_H1", "EURUSD_M1"), ("XAUUSD_H1", "XAUUSD_M1")]
    pair_results = {}
    max_sample = 0
    for left, right in pairs:
        if left not in returns or right not in returns:
            pair_results[f"{left}__{right}"] = {"status": "UNAVAILABLE", "reason": "one or both completed market series unavailable"}
            continue
        joined = pd.concat([returns[left].rename("left"), returns[right].rename("right")], axis=1, join="inner").dropna()
        max_sample = max(max_sample, len(joined))
        if len(joined) < MIN_DCC_SAMPLE:
            pair_results[f"{left}__{right}"] = {"status": "INSUFFICIENT_EVIDENCE", "sample_count": len(joined)}
            continue
        z = np.column_stack([_ewma_standardize(joined["left"].to_numpy()), _ewma_standardize(joined["right"].to_numpy())])
        matrices = dcc_recursion(z, a=0.04, b=0.94)
        corr = np.asarray([m[0, 1] for m in matrices])
        current = float(corr[-1]); previous = float(corr[-2]); change6 = float(current - corr[-7]) if len(corr) >= 7 else None
        shock = float(abs(current - np.mean(corr[-24:]))) if len(corr) >= 24 else float(abs(current - previous))
        pair_results[f"{left}__{right}"] = {
            "status": "AVAILABLE", "sample_count": len(joined), "a": 0.04, "b": 0.94,
            "current_conditional_correlation": round(current, 6), "previous_correlation": round(previous, 6),
            "six_hour_correlation_change": finite(change6), "correlation_shock": round(shock, 6),
            "session_correlation": round(float(np.mean(corr[-12:])), 6), "regime_correlation": round(float(np.mean(corr[-48:])), 6),
            "valid_correlation_matrices": bool(all(np.allclose(np.diag(m), 1.0) and np.min(np.linalg.eigvalsh(m)) >= -1e-8 for m in matrices[-20:])),
        }
    primary = pair_results.get("EURUSD_H1__XAUUSD_H1", {})
    if primary.get("status") == "AVAILABLE":
        current = abs(float(primary["current_conditional_correlation"]))
        diversification_loss = float(np.clip((current - 0.35) / 0.65, 0.0, 1.0) * 100.0)
        shock = float(primary.get("correlation_shock") or 0.0)
        conflict = "HIGH" if current > 0.85 or shock > 0.35 else "WATCH" if current > 0.65 or shock > 0.20 else "LOW"
        status = "AVAILABLE"
    else:
        diversification_loss = None; conflict = "UNAVAILABLE"; status = "UNAVAILABLE" if all(v.get("status") == "UNAVAILABLE" for v in pair_results.values()) else "INSUFFICIENT_EVIDENCE"
    output = {
        "pairs": pair_results,
        "current_conditional_correlation": primary.get("current_conditional_correlation"),
        "previous_correlation": primary.get("previous_correlation"),
        "six_hour_correlation_change": primary.get("six_hour_correlation_change"),
        "correlation_shock": primary.get("correlation_shock"),
        "session_correlation": primary.get("session_correlation"),
        "regime_correlation": primary.get("regime_correlation"),
        "diversification_loss_score": diversification_loss,
        "cross_market_conflict_state": conflict,
        "runtime_ms": round((time.perf_counter() - started) * 1000.0, 3),
    }
    return common_method(DCC_METHOD, status=status, sample_count=max_sample, minimum_sample_required=MIN_DCC_SAMPLE, cutoff_time=cutoff_time, output_metrics=output, assumptions=["completed aligned returns", "locally stable DCC parameters"], limitations=["returns UNAVAILABLE when XAUUSD or M1 data are absent", "does not generate trade direction"])


__all__ = ["run_ledoit_wolf_covariance", "run_dynamic_conditional_correlation", "dcc_recursion"]
