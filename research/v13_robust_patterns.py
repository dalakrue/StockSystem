"""Bounded shadow evaluators for V13 research layers 6–10."""
from __future__ import annotations

from typing import Any, Mapping
import math

import numpy as np
import pandas as pd


def _result(status: str, sample_size: int, **outputs: Any) -> dict[str, Any]:
    return {
        "status": status,
        "sample_size": int(sample_size),
        "shadow_only": True,
        "production_changed": False,
        "outputs": outputs,
    }


def _returns(frame: pd.DataFrame) -> pd.Series:
    if not isinstance(frame, pd.DataFrame) or frame.empty or "close" not in frame:
        return pd.Series(dtype=float)
    close = pd.to_numeric(frame["close"], errors="coerce").where(lambda s: s > 0)
    return np.log(close).diff().replace([np.inf, -np.inf], np.nan)


def _lead_one(series: pd.Series) -> pd.Series:
    """Align the next matured observation to the current row without backfill."""
    result = pd.Series(np.nan, index=series.index, dtype=float)
    if len(series) > 1:
        result.iloc[:-1] = pd.to_numeric(series.iloc[1:], errors="coerce").to_numpy(float)
    return result


def _number(context: Mapping[str, Any] | None, *keys: str, default: float = 0.0) -> float:
    mapping = context if isinstance(context, Mapping) else {}
    for key in keys:
        value: Any = mapping
        for part in key.split("."):
            value = value.get(part) if isinstance(value, Mapping) else None
        try:
            result = float(value)
            if math.isfinite(result):
                return result
        except Exception:
            pass
    return default


def evaluate_wasserstein_dro(frame: pd.DataFrame, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    returns = _returns(frame).dropna().tail(600).to_numpy(float) * 10000.0
    n = len(returns)
    if n < 40:
        return _result("INSUFFICIENT_EVIDENCE", n, reason="minimum 40 completed H1 returns")
    signal = _number(context, "signal_pips", "expected_return_pips", default=float(np.mean(returns[-24:])))
    cost = abs(_number(context, "transaction_cost_pips", "spread_pips", default=0.0))
    alpha = 0.05
    scale = float(np.std(returns, ddof=1))
    radius = scale * math.sqrt(2.0 * math.log(1.0 / alpha) / n)
    nominal = signal - cost
    robust = nominal - radius
    status = "ROBUST_ACTIONABLE_SHADOW" if abs(robust) > max(cost, 0.25) else "ROBUST_ABSTAIN_SHADOW"
    return _result(
        "AVAILABLE_SHADOW", n,
        nominal_expected_pips=nominal, wasserstein_radius_pips=radius,
        worst_case_expected_pips=robust, transaction_cost_pips=cost,
        robust_actionability=status,
        ambiguity_confidence=1.0 - alpha,
    )


def evaluate_dynamic_trading_costs(frame: pd.DataFrame, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    r = _returns(frame).dropna().tail(600)
    n = len(r)
    if n < 60:
        return _result("INSUFFICIENT_EVIDENCE", n, reason="minimum 60 completed H1 returns")
    cost_pips = abs(_number(context, "transaction_cost_pips", "spread_pips", default=0.8))
    volatility = r.rolling(24, min_periods=12).std()
    causal_fallback = r.expanding(min_periods=2).std()
    volatility = volatility.where(volatility.notna(), causal_fallback).fillna(0.0)
    signal = r.rolling(6, min_periods=3).mean().fillna(0.0)
    threshold = (cost_pips / 10000.0) + 0.25 * volatility.fillna(volatility.median())
    target = np.where(signal > threshold, 1.0, np.where(signal < -threshold, -1.0, 0.0))
    target = pd.Series(target, index=r.index, dtype=float)
    # Position chosen at t is assessed on t+1 only after that H1 candle matures.
    next_return = _lead_one(r)
    turnover = target.diff().abs().fillna(target.abs())
    gross = target * next_return * 10000.0
    net = gross - turnover * cost_pips
    valid = next_return.notna()
    if not valid.any():
        return _result("INSUFFICIENT_SETTLED_VALIDATION", n, reason="no matured next-H1 return")
    net_valid = net.loc[valid]
    latest_signal = float(signal.iloc[-1] * 10000.0)
    latest_threshold = float(threshold.iloc[-1] * 10000.0)
    latest_position = float(target.iloc[-1])
    return _result(
        "AVAILABLE_SHADOW", n,
        latest_signal_pips=latest_signal, no_trade_threshold_pips=latest_threshold,
        shadow_target_position=latest_position,
        action=("BUY_SHADOW" if latest_position > 0 else "SELL_SHADOW" if latest_position < 0 else "NO_TRADE_SHADOW"),
        chronological_validation_rows=int(valid.sum()),
        mean_gross_pips=float(gross.loc[valid].mean()), mean_net_pips=float(net_valid.mean()),
        total_turnover=float(turnover.loc[valid].sum()), active_fraction=float((target.loc[valid] != 0).mean()),
        cost_dominance=bool(float(net_valid.mean()) <= 0.0),
    )


def _z(window: np.ndarray) -> np.ndarray | None:
    std = float(np.std(window))
    if not math.isfinite(std) or std < 1e-12:
        return None
    return (window - float(np.mean(window))) / std


def evaluate_matrix_profile(frame: pd.DataFrame, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    del context
    series = _returns(frame).dropna().tail(300).to_numpy(float)
    n, m = len(series), 12
    if n < 5 * m:
        return _result("INSUFFICIENT_EVIDENCE", n, reason=f"minimum {5*m} returns for {m}-H1 subsequences")
    query_start = n - m
    query = _z(series[query_start:])
    if query is None:
        return _result("ZERO_VARIANCE_QUERY", n, subsequence_hours=m)
    candidates: list[tuple[float, int]] = []
    # Every candidate ends before the latest query starts; no overlapping/future candidate.
    for start in range(0, query_start - m + 1):
        candidate = _z(series[start:start + m])
        if candidate is None:
            continue
        distance = float(np.linalg.norm(query - candidate) / math.sqrt(m))
        if math.isfinite(distance):
            candidates.append((distance, start))
    if not candidates:
        return _result("NO_NON_OVERLAPPING_CANDIDATE", n, subsequence_hours=m)
    nearest = min(candidates)
    discord = max(candidates)
    return _result(
        "AVAILABLE_SHADOW", n, subsequence_hours=m, candidate_count=len(candidates),
        nearest_motif_distance=nearest[0], nearest_motif_start_index=nearest[1],
        discord_distance=discord[0], discord_start_index=discord[1],
        similarity_status=("CLOSE_MOTIF" if nearest[0] < 0.75 else "WEAK_OR_DISTINCT_PATTERN"),
        candidates_end_before_query=True,
    )


def _feature_matrix(frame: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    r = _returns(frame)
    close = pd.to_numeric(frame.get("close"), errors="coerce")
    high = pd.to_numeric(frame.get("high"), errors="coerce")
    low = pd.to_numeric(frame.get("low"), errors="coerce")
    features = pd.DataFrame({
        "return1": r,
        "momentum3": r.rolling(3, min_periods=3).sum(),
        "momentum6": r.rolling(6, min_periods=4).sum(),
        "volatility12": r.rolling(12, min_periods=6).std(),
        "range_pips": (high - low) * 10000.0,
        "ema_gap": close.ewm(span=12, adjust=False).mean() - close.ewm(span=24, adjust=False).mean(),
    }).dropna().tail(600)
    if features.empty:
        return np.empty((0, 0)), []
    values = features.to_numpy(float)
    mean = values.mean(axis=0); std = values.std(axis=0); std[std < 1e-12] = 1.0
    return (values - mean) / std, list(features.columns)


def evaluate_robust_pca(frame: pd.DataFrame, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    del context
    x, names = _feature_matrix(frame)
    n = len(x)
    if n < 60 or x.shape[1] < 3:
        return _result("INSUFFICIENT_EVIDENCE", n, reason="minimum 60 complete multivariate H1 rows")
    # Bounded principal-component pursuit approximation by alternating low-rank
    # SVD truncation and sparse soft thresholding. It is diagnostic, not production.
    sparse = np.zeros_like(x)
    rank = min(3, x.shape[1])
    lam = 1.0 / math.sqrt(max(x.shape))
    low_rank = np.zeros_like(x)
    for _ in range(20):
        u, singular, vt = np.linalg.svd(x - sparse, full_matrices=False)
        shrunk = np.maximum(singular - lam, 0.0)
        keep = min(rank, int(np.sum(shrunk > 0)))
        low_rank = (u[:, :keep] * shrunk[:keep]) @ vt[:keep] if keep else np.zeros_like(x)
        residual = x - low_rank
        sparse = np.sign(residual) * np.maximum(np.abs(residual) - lam, 0.0)
    reconstruction = low_rank + sparse
    error = float(np.linalg.norm(x - reconstruction) / max(np.linalg.norm(x), 1e-12))
    anomaly = np.linalg.norm(sparse, axis=1)
    threshold = float(np.quantile(anomaly, 0.95))
    sparse_fraction = float(np.mean(np.abs(sparse) > 1e-8))
    structural = float(np.linalg.norm(low_rank) ** 2 / max(np.linalg.norm(x) ** 2, 1e-12))
    return _result(
        "AVAILABLE_SHADOW", n, feature_schema=names, low_rank_dimension=rank,
        structural_energy_ratio=structural, sparse_fraction=sparse_fraction,
        latest_anomaly_score=float(anomaly[-1]), anomaly_threshold_95pct=threshold,
        latest_anomaly_flag=bool(anomaly[-1] > threshold), relative_reconstruction_error=error,
    )


def evaluate_dynamic_bayesian_synthesis(frame: pd.DataFrame, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    del context
    r = _returns(frame).dropna().tail(600).reset_index(drop=True)
    n = len(r)
    if n < 80:
        return _result("INSUFFICIENT_EVIDENCE", n, reason="minimum 80 completed H1 returns")
    agents = pd.DataFrame({
        "momentum": r.rolling(6, min_periods=3).mean(),
        "mean_reversion": -0.35 * r.rolling(6, min_periods=3).mean(),
        "persistence": r,
    })
    target = _lead_one(r)
    valid = agents.notna().all(axis=1) & target.notna()
    agents, target = agents.loc[valid].reset_index(drop=True), target.loc[valid].reset_index(drop=True)
    if len(agents) < 60:
        return _result("INSUFFICIENT_EVIDENCE", len(agents), reason="insufficient matured agent-target pairs")
    weights = np.full(agents.shape[1], 1.0 / agents.shape[1])
    discount = 0.98
    scale = max(float(target.iloc[:30].std()), 1e-6)
    synthesized: list[float] = []
    weight_history: list[np.ndarray] = []
    for i in range(len(agents)):
        forecasts = agents.iloc[i].to_numpy(float)
        synthesized.append(float(np.dot(weights, forecasts)))
        error = target.iloc[i] - forecasts
        likelihood = np.exp(-0.5 * np.square(error / scale)) + 1e-12
        weights = np.power(weights, discount) * likelihood
        weights = np.maximum(weights, 0.02); weights /= weights.sum()
        scale = 0.98 * scale + 0.02 * max(abs(float(target.iloc[i] - synthesized[-1])), 1e-6)
        weight_history.append(weights.copy())
    predictions = np.asarray(synthesized)
    actual = target.to_numpy(float)
    benchmark = agents["persistence"].to_numpy(float)
    latest_agents = np.array([
        float(r.tail(6).mean()), -0.35 * float(r.tail(6).mean()), float(r.iloc[-1]),
    ])
    latest_synthesis = float(np.dot(weights, latest_agents))
    concentration = float(np.max(weights))
    return _result(
        "AVAILABLE_SHADOW" if concentration < 0.95 else "WEIGHT_CONCENTRATION_WARNING", len(agents),
        agent_weights={name: float(weight) for name, weight in zip(agents.columns, weights)},
        latest_agent_forecasts={name: float(value) for name, value in zip(agents.columns, latest_agents)},
        latest_synthesized_return=latest_synthesis,
        chronological_validation_rows=len(actual),
        synthesis_mae=float(np.mean(np.abs(actual - predictions))),
        persistence_mae=float(np.mean(np.abs(actual - benchmark))),
        relative_mae_skill=float(1.0 - np.mean(np.abs(actual - predictions)) / max(np.mean(np.abs(actual - benchmark)), 1e-12)),
        weight_concentration=concentration,
        agent_disagreement=float(np.std(latest_agents)),
    )


EVALUATORS = {
    "wasserstein_dro": evaluate_wasserstein_dro,
    "dynamic_trading_costs": evaluate_dynamic_trading_costs,
    "matrix_profile": evaluate_matrix_profile,
    "robust_pca": evaluate_robust_pca,
    "dynamic_bayesian_predictive_synthesis": evaluate_dynamic_bayesian_synthesis,
}


__all__ = ["EVALUATORS", *[fn.__name__ for fn in EVALUATORS.values()]]
