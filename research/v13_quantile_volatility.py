"""Bounded shadow evaluators for V13 research layers 1–5."""
from __future__ import annotations

from typing import Any
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


def _split_index(n: int, minimum_train: int = 40) -> int:
    return min(max(minimum_train, int(n * 0.70)), max(0, n - 12))


def _lead_one(series: pd.Series) -> pd.Series:
    """Align the next matured observation to the current row without backfill."""
    result = pd.Series(np.nan, index=series.index, dtype=float)
    if len(series) > 1:
        result.iloc[:-1] = pd.to_numeric(series.iloc[1:], errors="coerce").to_numpy(float)
    return result


def evaluate_long_memory_realized_volatility(frame: pd.DataFrame) -> dict[str, Any]:
    returns = _returns(frame)
    rv = returns.pow(2)
    data = pd.DataFrame({
        "target": _lead_one(rv),
        "rv1": rv,
        "rv5": rv.rolling(5, min_periods=5).mean(),
        "rv22": rv.rolling(22, min_periods=22).mean(),
    }).dropna()
    if len(data) < 60:
        return _result("INSUFFICIENT_EVIDENCE", len(data), reason="minimum 60 causal realized-volatility rows")
    split = _split_index(len(data), 45)
    train, test = data.iloc[:split], data.iloc[split:]
    x = np.column_stack([np.ones(len(train)), train[["rv1", "rv5", "rv22"]].to_numpy(float)])
    y = train["target"].to_numpy(float)
    try:
        beta = np.linalg.lstsq(x, y, rcond=None)[0]
        prediction = np.column_stack([np.ones(len(test)), test[["rv1", "rv5", "rv22"]].to_numpy(float)]) @ beta
        prediction = np.maximum(prediction, 0.0)
        actual = test["target"].to_numpy(float)
        mae = float(np.mean(np.abs(prediction - actual)))
        mse = float(np.mean((prediction - actual) ** 2))
        eps = 1e-15
        qlike = float(np.mean(actual / np.maximum(prediction, eps) + np.log(np.maximum(prediction, eps))))
        latest = np.array([1.0, data.iloc[-1]["rv1"], data.iloc[-1]["rv5"], data.iloc[-1]["rv22"]]) @ beta
    except Exception as exc:
        return _result("FAILED_SAFELY", len(data), reason=f"{type(exc).__name__}: {exc}")
    return _result(
        "AVAILABLE_SHADOW", len(data),
        next_h1_realized_variance=max(0.0, float(latest)),
        next_h1_volatility_pips=float(math.sqrt(max(0.0, latest)) * 10000.0),
        coefficients={"intercept": float(beta[0]), "rv1": float(beta[1]), "rv5": float(beta[2]), "rv22": float(beta[3])},
        chronological_validation_rows=len(test), mae=mae, mse=mse, qlike=qlike,
    )


def evaluate_realized_kernel(frame: pd.DataFrame, *, lag: int = 12) -> dict[str, Any]:
    r = _returns(frame).dropna().tail(600).to_numpy(float)
    n = len(r)
    if n < 30:
        return _result("INSUFFICIENT_EVIDENCE", n, reason="minimum 30 completed H1 returns")
    naive = float(np.dot(r, r))
    kernel = naive
    used = min(max(1, int(lag)), n - 2)
    for h in range(1, used + 1):
        weight = 1.0 - h / (used + 1.0)  # Bartlett PSD-compatible bounded weight.
        gamma = float(np.dot(r[h:], r[:-h]))
        kernel += 2.0 * weight * gamma
    tolerance = max(1e-18, naive * 1e-10)
    psd = kernel >= -tolerance
    kernel = max(0.0, kernel)
    return _result(
        "AVAILABLE_SHADOW" if psd else "NUMERICAL_WARNING", n,
        naive_realized_variance=naive,
        kernel_realized_variance=kernel,
        kernel_lag=used,
        noise_adjustment_ratio=(kernel / naive if naive > 0 else None),
        positive_semidefinite_within_tolerance=bool(psd),
    )


def _pinball(actual: np.ndarray, prediction: np.ndarray, tau: float) -> float:
    error = actual - prediction
    return float(np.mean(np.maximum(tau * error, (tau - 1.0) * error)))


def evaluate_caviar(frame: pd.DataFrame, *, tau: float = 0.10) -> dict[str, Any]:
    r = _returns(frame).dropna().tail(600).to_numpy(float)
    n = len(r)
    if n < 80:
        return _result("INSUFFICIENT_EVIDENCE", n, reason="minimum 80 completed H1 returns")
    split = _split_index(n, 60)
    train = r[:split]
    # Bounded deterministic search over stable recursion coefficients.
    base = float(np.quantile(train, tau))
    best: tuple[float, tuple[float, float, float], np.ndarray] | None = None
    for b1 in (0.70, 0.82, 0.90, 0.96):
        for b2 in (-0.50, -0.25, 0.0, 0.25):
            b0 = (1.0 - b1) * base
            q = np.empty(n, dtype=float); q[0] = base
            for i in range(1, n):
                q[i] = b0 + b1 * q[i - 1] + b2 * abs(r[i - 1])
            loss = _pinball(r[1:split], q[1:split], tau)
            if best is None or loss < best[0]:
                best = (loss, (b0, b1, b2), q)
    assert best is not None
    _, coefficients, q = best
    actual = r[split:]
    pred = q[split:]
    exceptions = actual < pred
    exception_rate = float(exceptions.mean()) if len(actual) else None
    clustered = bool(np.any(exceptions[1:] & exceptions[:-1])) if len(exceptions) > 1 else False
    return _result(
        "AVAILABLE_SHADOW", n,
        tau=tau, next_h1_lower_quantile=float(q[-1]),
        coefficients={"b0": coefficients[0], "b1": coefficients[1], "b2_abs_return": coefficients[2]},
        chronological_validation_rows=len(actual),
        pinball_loss=_pinball(actual, pred, tau),
        exception_rate=exception_rate,
        coverage_deviation=(None if exception_rate is None else exception_rate - tau),
        exception_cluster_warning=clustered,
    )


def _quantile_fit(x: np.ndarray, y: np.ndarray, tau: float, *, iterations: int = 700) -> np.ndarray:
    scale = np.std(x, axis=0); scale[scale < 1e-12] = 1.0
    mean = np.mean(x, axis=0)
    z = (x - mean) / scale
    design = np.column_stack([np.ones(len(z)), z])
    beta = np.zeros(design.shape[1], dtype=float)
    rate = 0.035 / math.sqrt(max(1, design.shape[1]))
    for step in range(iterations):
        residual = y - design @ beta
        gradient = -(design.T @ (tau - (residual < 0).astype(float))) / len(y)
        beta -= (rate / math.sqrt(1.0 + step / 50.0)) * gradient
    # Return coefficients in standardized design and attach conversion separately at call site.
    return np.concatenate([beta, mean, scale])


def _quantile_predict(fit: np.ndarray, x: np.ndarray) -> np.ndarray:
    p = x.shape[1]
    beta, mean, scale = fit[: p + 1], fit[p + 1: 2 * p + 1], fit[2 * p + 1:]
    return np.column_stack([np.ones(len(x)), (x - mean) / scale]) @ beta


def _lag_features(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    r = _returns(frame)
    data = pd.DataFrame({
        "target": _lead_one(r), "lag1": r, "lag2": r.shift(1),
        "momentum3": r.rolling(3, min_periods=3).sum(),
        "volatility12": r.rolling(12, min_periods=6).std(),
    }).dropna()
    return data, ["lag1", "lag2", "momentum3", "volatility12"]


def evaluate_quantile_autoregression(frame: pd.DataFrame) -> dict[str, Any]:
    data, features = _lag_features(frame)
    if len(data) < 90:
        return _result("INSUFFICIENT_EVIDENCE", len(data), reason="minimum 90 causal feature rows")
    split = _split_index(len(data), 65)
    train, test = data.iloc[:split], data.iloc[split:]
    x_train, y_train = train[features].to_numpy(float), train["target"].to_numpy(float)
    x_test, y_test = test[features].to_numpy(float), test["target"].to_numpy(float)
    latest = data[features].iloc[[-1]].to_numpy(float)
    outputs: dict[str, Any] = {"feature_schema": features, "chronological_validation_rows": len(test)}
    predictions: dict[float, np.ndarray] = {}
    latest_q: dict[str, float] = {}
    losses: dict[str, float] = {}
    for tau in (0.10, 0.50, 0.90):
        fit = _quantile_fit(x_train, y_train, tau)
        pred = _quantile_predict(fit, x_test)
        predictions[tau] = pred
        latest_q[f"q{int(tau * 100)}"] = float(_quantile_predict(fit, latest)[0])
        losses[f"q{int(tau * 100)}_pinball"] = _pinball(y_test, pred, tau)
    crossing = int(np.sum((predictions[0.10] > predictions[0.50]) | (predictions[0.50] > predictions[0.90])))
    outputs.update({"latest_return_quantiles": latest_q, "validation_losses": losses, "quantile_crossing_rows": crossing})
    return _result("AVAILABLE_SHADOW" if crossing == 0 else "QUANTILE_CROSSING_WARNING", len(data), **outputs)


def evaluate_quantile_regression_forest(frame: pd.DataFrame) -> dict[str, Any]:
    data, features = _lag_features(frame)
    if len(data) < 100:
        return _result("INSUFFICIENT_EVIDENCE", len(data), reason="minimum 100 causal feature rows")
    try:
        from sklearn.ensemble import RandomForestRegressor
    except Exception as exc:
        return _result("DEPENDENCY_UNAVAILABLE", len(data), reason=f"{type(exc).__name__}: {exc}")
    split = _split_index(len(data), 70)
    train, test = data.iloc[:split], data.iloc[split:]
    model = RandomForestRegressor(
        n_estimators=64, max_depth=6, min_samples_leaf=5,
        random_state=130623, n_jobs=1, bootstrap=True,
    )
    model.fit(train[features].to_numpy(float), train["target"].to_numpy(float))
    test_x = test[features].to_numpy(float)
    tree_predictions = np.vstack([tree.predict(test_x) for tree in model.estimators_])
    q10, q50, q90 = np.quantile(tree_predictions, [0.10, 0.50, 0.90], axis=0)
    actual = test["target"].to_numpy(float)
    coverage = float(np.mean((actual >= q10) & (actual <= q90)))
    latest_x = data[features].iloc[[-1]].to_numpy(float)
    latest_trees = np.array([tree.predict(latest_x)[0] for tree in model.estimators_])
    return _result(
        "AVAILABLE_SHADOW", len(data), feature_schema=features, trees=64,
        latest_return_quantiles={"q10": float(np.quantile(latest_trees, .10)), "q50": float(np.quantile(latest_trees, .50)), "q90": float(np.quantile(latest_trees, .90))},
        chronological_validation_rows=len(test), median_mae=float(np.mean(np.abs(actual - q50))),
        p10_p90_coverage=coverage, mean_interval_width=float(np.mean(q90 - q10)),
    )


EVALUATORS = {
    "long_memory_realized_volatility": evaluate_long_memory_realized_volatility,
    "realized_kernel_noise": evaluate_realized_kernel,
    "caviar": evaluate_caviar,
    "quantile_autoregression": evaluate_quantile_autoregression,
    "quantile_regression_forests": evaluate_quantile_regression_forest,
}


__all__ = ["EVALUATORS", *[fn.__name__ for fn in EVALUATORS.values()]]
