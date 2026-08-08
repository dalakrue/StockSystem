"""Lightweight log-linear Realized-GARCH shadow adaptation using completed H1 proxies."""
from __future__ import annotations

from typing import Any, Mapping
import math

import numpy as np
import pandas as pd

from core.quant_research_v4_contract_20260622 import common_result, unavailable
from core.hamilton_regime_research_v4_20260622 import _yang_zhang_variance

METHOD_ID = "REALIZED_GARCH_SHADOW"
PAPER_TITLE = "Realized GARCH: A Joint Model for Returns and Realized Measures of Volatility"
PAPER_AUTHORS = "Peter Reinhard Hansen, Zhuo Huang, and Howard Howan Shek"
VAR_FLOOR = 1e-12


def qlike_loss(realized_variance: np.ndarray, forecast_variance: np.ndarray) -> np.ndarray:
    rv = np.clip(np.asarray(realized_variance, dtype=float), VAR_FLOOR, None)
    fv = np.clip(np.asarray(forecast_variance, dtype=float), VAR_FLOOR, None)
    return np.log(fv) + rv / fv


def _ridge(x: np.ndarray, y: np.ndarray, ridge: float = 1e-4) -> np.ndarray:
    eye = np.eye(x.shape[1]); eye[0, 0] = 0.0
    return np.linalg.solve(x.T @ x + ridge * eye + 1e-10 * np.eye(x.shape[1]), x.T @ y)


def _proxy(frame: pd.DataFrame) -> tuple[pd.Series, str]:
    yz = _yang_zhang_variance(frame, 24)
    if yz.notna().sum() >= 120:
        return yz.clip(lower=VAR_FLOOR), "YANG_ZHANG_VARIANCE"
    close = frame["close"].astype(float).clip(lower=1e-12)
    range_var = (np.log(frame["high"].clip(lower=1e-12) / frame["low"].clip(lower=1e-12)) ** 2) / (4.0 * math.log(2.0))
    return range_var.rolling(12, min_periods=4).mean().clip(lower=VAR_FLOOR), "PARKINSON_RANGE_VARIANCE"


def _fit_and_paths(frame: pd.DataFrame) -> dict[str, Any]:
    close = frame["close"].astype(float).clip(lower=1e-12)
    ret = np.log(close).diff()
    rv, proxy_name = _proxy(frame)
    data = pd.DataFrame({"return": ret, "realized": rv}).replace([np.inf, -np.inf], np.nan).dropna()
    data["return_sq"] = data["return"] ** 2
    data["log_r2"] = np.log(data["return_sq"].clip(lower=VAR_FLOOR))
    data["log_x"] = np.log(data["realized"].clip(lower=VAR_FLOOR))
    data["log_h_proxy"] = np.log(data["return_sq"].ewm(alpha=0.08, adjust=False).mean().clip(lower=VAR_FLOOR))
    model = pd.DataFrame(index=data.index)
    model["target"] = data["log_h_proxy"]
    model["lag_h"] = data["log_h_proxy"].shift(1)
    model["lag_x"] = data["log_x"].shift(1)
    model["realized"] = data["realized"]
    model["return"] = data["return"]
    model = model.dropna()
    if len(model) < 240:
        raise ValueError("Realized-GARCH requires at least 240 finite completed-H1 rows.")
    split = max(180, int(len(model) * 0.70))
    x_train = np.c_[np.ones(split), model[["lag_h", "lag_x"]].iloc[:split].to_numpy(float)]
    y_train = model["target"].iloc[:split].to_numpy(float)
    beta = _ridge(x_train, y_train, ridge=1e-3)
    omega, persistence, gamma = [float(v) for v in beta]
    persistence = float(np.clip(persistence, 0.0, 0.985))
    gamma = float(np.clip(gamma, 0.0, max(0.0, 0.995 - persistence)))
    beta = np.array([omega, persistence, gamma])
    x_all = np.c_[np.ones(len(model)), model[["lag_h", "lag_x"]].to_numpy(float)]
    log_h = x_all @ beta
    forecast = np.exp(np.clip(log_h, -30.0, 5.0))
    actual = model["return"].to_numpy(float) ** 2
    test_actual = actual[split:]
    test_forecast = forecast[split:]
    # Measurement equation: log x_t = xi + phi log h_t + tau1 z_t + tau2(z_t^2-1) + u_t
    h = np.clip(forecast, VAR_FLOOR, None)
    z = model["return"].to_numpy(float) / np.sqrt(h)
    mx = np.c_[np.ones(len(model)), np.log(h), z, z * z - 1.0]
    measurement_beta = _ridge(mx[:split], np.log(model["realized"].to_numpy(float)[:split]), ridge=1e-3)
    measurement_pred = mx[split:] @ measurement_beta
    measurement_rmse = float(np.sqrt(np.mean((np.log(model["realized"].to_numpy(float)[split:]) - measurement_pred) ** 2))) if len(test_actual) else None
    # Baselines on the identical test origins.
    squared = model["return"].to_numpy(float) ** 2
    # Causal baselines: never fill an earlier origin from a later observation.
    ewma = (
        pd.Series(squared)
        .ewm(alpha=0.06, adjust=False)
        .mean()
        .shift(1)
        .ffill()
        .fillna(VAR_FLOOR)
        .to_numpy(float)
    )
    rolling_yz = (
        model["realized"]
        .shift(1)
        .rolling(24, min_periods=4)
        .mean()
        .ffill()
        .fillna(VAR_FLOOR)
        .to_numpy(float)
    )
    evaluation = pd.DataFrame({
        "row_index": model.index,
        "actual_variance": np.clip(actual, VAR_FLOOR, None),
        "realized_garch": np.clip(forecast, VAR_FLOOR, None),
        "ewma": np.clip(ewma, VAR_FLOOR, None),
        "rolling_yang_zhang": np.clip(rolling_yz, VAR_FLOOR, None),
        "return": model["return"].to_numpy(float),
    }).iloc[split:].reset_index(drop=True)
    last_log_h = float(log_h[-1])
    last_log_x = float(model["log_x"].iloc[-1] if "log_x" in model.columns else np.log(model["realized"].iloc[-1]))
    forecasts = []
    for horizon in range(1, 7):
        last_log_h = omega + persistence * last_log_h + gamma * last_log_x
        var = float(np.exp(np.clip(last_log_h, -30.0, 5.0)))
        forecasts.append(var)
        last_log_x = float(measurement_beta[0] + measurement_beta[1] * last_log_h)
    return {
        "proxy_name": proxy_name,
        "model": model,
        "split": split,
        "omega": omega,
        "beta": persistence,
        "gamma": gamma,
        "measurement_beta": measurement_beta,
        "measurement_rmse": measurement_rmse,
        "evaluation": evaluation,
        "forecast_variances": forecasts,
        "test_qlike": float(np.mean(qlike_loss(test_actual, test_forecast))) if len(test_actual) else None,
    }


def run_realized_garch(frame: pd.DataFrame, identity: Mapping[str, Any], *, canonical: Mapping[str, Any] | None = None) -> dict[str, Any]:
    n = int(len(frame)) if isinstance(frame, pd.DataFrame) else 0
    minimum = 240
    try:
        fit = _fit_and_paths(frame)
        variances = fit["forecast_variances"]
        vols = [float(math.sqrt(v)) for v in variances]
        current_price = float(frame["close"].iloc[-1])
        moves = [float(current_price * v * math.sqrt(i + 1)) for i, v in enumerate(vols)]
        persistence = float(fit["beta"] + fit["gamma"])
        status = "STABLE" if persistence < 0.995 and all(v > 0 for v in variances) else "CAUTION"
        evaluation = fit["evaluation"]
        return common_result(
            identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            exact_or_adaptation="LIGHTWEIGHT_LOG_LINEAR_REALIZED_GARCH_ADAPTATION",
            sample_count=len(fit["model"]), effective_sample_count=len(evaluation), minimum_required_samples=minimum,
            status="AVAILABLE", score=(-fit["test_qlike"] if fit["test_qlike"] is not None else None),
            confidence=max(0.0, min(1.0, 1.0 - (fit["measurement_rmse"] or 1.0))),
            reliability=status,
            train_start=frame.loc[fit["model"].index[0], "time"],
            train_end=frame.loc[fit["model"].index[fit["split"] - 1], "time"],
            test_start=frame.loc[fit["model"].index[fit["split"]], "time"],
            test_end=frame.loc[fit["model"].index[-1], "time"],
            assumptions=["Yang-Zhang or range variance is the existing completed-H1 realized proxy; no lower-timeframe volatility is fabricated.", "The latent variance recursion is estimated deterministically with bounded persistence."],
            limitations=["This is a lightweight log-linear adaptation rather than full maximum-likelihood Realized-GARCH.", "Variance forecasts are non-directional and cannot produce BUY or SELL."],
            realized_proxy=fit["proxy_name"],
            forecast_variance_h1_to_h6={str(i + 1): float(v) for i, v in enumerate(variances)},
            forecast_volatility_h1_to_h6={str(i + 1): float(v) for i, v in enumerate(vols)},
            expected_move_h1_to_h6={str(i + 1): float(v) for i, v in enumerate(moves)},
            persistence=persistence,
            measurement_equation_fit={
                "xi": float(fit["measurement_beta"][0]), "phi": float(fit["measurement_beta"][1]),
                "tau_1": float(fit["measurement_beta"][2]), "tau_2": float(fit["measurement_beta"][3]),
                "log_measurement_rmse": fit["measurement_rmse"],
            },
            walk_forward_qlike=fit["test_qlike"],
            model_status=status,
            protected_direction_modified=False,
            internal_evaluation_records=evaluation.tail(1200).to_dict("records"),
        )
    except Exception as exc:
        return unavailable(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            error=exc, minimum_required_samples=minimum, sample_count=n,
            limitations=["No volatility result is fabricated when evidence or estimation fails."])


__all__ = ["run_realized_garch", "qlike_loss", "_fit_and_paths"]
