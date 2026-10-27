"""Independent HAR-H1 volatility and realized-semivariance shadow evidence."""
from __future__ import annotations

from typing import Any
import math

import numpy as np
import pandas as pd

from core.field10_research_common_20260705 import HORIZONS, REQUIRED_H1_ROWS, finite
from core.ohlc_volatility_research_20260622 import _predict, _ridge_fit

VERSION = "field10-har-h1-semivariance-20260705-v1"
RIDGE_GRID = (0.0, 1e-8, 1e-6, 1e-4, 1e-2, 1e-1, 1.0)


def _har_features(realized_variance: pd.Series) -> pd.DataFrame:
    rv = pd.to_numeric(realized_variance, errors="coerce")
    return pd.DataFrame({
        "rv_1h": rv,
        "rv_short_6h": rv.rolling(6, min_periods=3).mean(),
        "rv_session_24h": rv.rolling(24, min_periods=12).mean(),
        "rv_medium_120h": rv.rolling(120, min_periods=60).mean(),
    }, index=rv.index)


def _future_realized_volatility(rv: pd.Series, horizon: int) -> pd.Series:
    # At origin t, the label is sum(rv[t+1:t+h]); the final h origins remain unset.
    return np.sqrt(rv.rolling(horizon, min_periods=horizon).sum().shift(-horizon).clip(lower=0.0))


def _percentile(value: float, history: pd.Series) -> float | None:
    clean = pd.to_numeric(history, errors="coerce").dropna()
    if len(clean) < 20:
        return None
    return float(100.0 * (clean <= value).mean())


def har_h1_forecasts(frame: pd.DataFrame) -> dict[str, Any]:
    """Fit one chronological HAR-H1 model per requested horizon.

    The targets are independently constructed future realized-volatility labels.
    No horizon column is copied from another horizon.
    """
    if not isinstance(frame, pd.DataFrame) or len(frame) != REQUIRED_H1_ROWS:
        return {
            "status": "INSUFFICIENT_EXACT_H1_WINDOW", "version": VERSION,
            "sample_count": int(len(frame) if isinstance(frame, pd.DataFrame) else 0),
            "required_sample_count": REQUIRED_H1_ROWS, "horizons": {},
        }
    close = pd.to_numeric(frame["close"], errors="coerce")
    returns = np.log(close / close.shift(1)).replace([np.inf, -np.inf], np.nan)
    rv = returns.pow(2)
    features = _har_features(rv)
    latest_close = finite(close.iloc[-1])
    horizon_rows: dict[int, dict[str, Any]] = {}
    for horizon in HORIZONS:
        target = _future_realized_volatility(rv, horizon).rename("target")
        aligned = pd.concat([features, target], axis=1).dropna()
        feature_names = list(features.columns)
        if len(aligned) < 150:
            emergency = returns.rolling(120, min_periods=60).std(ddof=1).iloc[-1]
            forecast = None if pd.isna(emergency) else float(abs(emergency) * math.sqrt(horizon))
            horizon_rows[horizon] = {
                "horizon": horizon, "forecast_volatility": forecast,
                "volatility_percentile": None, "volatility_surprise": None,
                "volatility_forecast_error": None, "expected_movement_lower": None,
                "expected_movement_upper": None, "har_sample_count": int(len(aligned)),
                "har_validation_status": "H1_SQRT_TIME_EMERGENCY_FALLBACK" if forecast is not None else "INSUFFICIENT_SAMPLE",
                "har_missing_reason": "independent HAR-H1 fit requires at least 150 chronological labels",
                "target_hash": str(horizon), "coefficients": {}, "selected_ridge": None,
            }
            continue
        n = len(aligned)
        train_end = max(100, int(n * 0.70))
        validation_end = max(train_end + 24, int(n * 0.85))
        validation_end = min(validation_end, n - 20)
        train = aligned.iloc[:train_end]
        validation = aligned.iloc[train_end:validation_end]
        test = aligned.iloc[validation_end:]
        x_train = train[feature_names].to_numpy(float)
        y_train = train["target"].to_numpy(float)
        x_val = validation[feature_names].to_numpy(float)
        y_val = validation["target"].to_numpy(float)
        candidates: list[tuple[float, float]] = []
        for ridge in RIDGE_GRID:
            beta = _ridge_fit(x_train, y_train, ridge)
            pred = np.clip(_predict(beta, x_val), 1e-12, None)
            candidates.append((float(np.mean(np.abs(y_val - pred))), float(ridge)))
        selected_ridge = min(candidates, key=lambda item: (item[0], item[1]))[1]
        fit = aligned.iloc[:validation_end]
        beta = _ridge_fit(fit[feature_names].to_numpy(float), fit["target"].to_numpy(float), selected_ridge)
        test_pred = np.clip(_predict(beta, test[feature_names].to_numpy(float)), 1e-12, None)
        test_mae = float(np.mean(np.abs(test["target"].to_numpy(float) - test_pred))) if len(test) else None
        beta_full = _ridge_fit(aligned[feature_names].to_numpy(float), aligned["target"].to_numpy(float), selected_ridge)
        latest_x = features.iloc[-1][feature_names].to_numpy(float)
        forecast = float(max(1e-12, np.r_[1.0, latest_x] @ beta_full)) if np.isfinite(latest_x).all() else None
        z = 1.6448536269514722
        lower = upper = None
        if forecast is not None and latest_close is not None:
            lower = float(latest_close * math.exp(-z * forecast))
            upper = float(latest_close * math.exp(z * forecast))
        realized_latest = float(math.sqrt(max(0.0, rv.tail(horizon).sum()))) if rv.tail(horizon).notna().all() else None
        horizon_rows[horizon] = {
            "horizon": horizon, "forecast_volatility": forecast,
            "volatility_percentile": None if forecast is None else _percentile(forecast, target.iloc[: -horizon or None]),
            "volatility_surprise": None if forecast is None or realized_latest is None else realized_latest - forecast,
            "volatility_forecast_error": test_mae,
            "expected_movement_lower": lower, "expected_movement_upper": upper,
            "har_sample_count": int(len(aligned)),
            "har_validation_status": "CHRONOLOGICAL_TEST_PASS" if len(test) >= 20 and test_mae is not None else "LIMITED_TEST_SAMPLE",
            "har_missing_reason": None,
            "target_hash": f"future_rv_sum_{horizon}h",
            "coefficients": {name: float(value) for name, value in zip(["intercept", *feature_names], beta_full)},
            "selected_ridge": selected_ridge,
            "training_rows": int(train_end), "validation_rows": int(validation_end - train_end), "test_rows": int(len(test)),
        }
    available = [r for r in horizon_rows.values() if r.get("forecast_volatility") is not None]
    return {
        "status": "AVAILABLE" if available else "UNAVAILABLE", "version": VERSION,
        "sample_count": len(frame), "horizons": horizon_rows,
        "forecast_volatility_1h": horizon_rows.get(1, {}).get("forecast_volatility"),
        "forecast_volatility_3h": horizon_rows.get(3, {}).get("forecast_volatility"),
        "forecast_volatility_6h": horizon_rows.get(6, {}).get("forecast_volatility"),
        "forecast_volatility_12h": horizon_rows.get(12, {}).get("forecast_volatility"),
        "forecast_volatility_24h": horizon_rows.get(24, {}).get("forecast_volatility"),
        "forecast_volatility_36h": horizon_rows.get(36, {}).get("forecast_volatility"),
        "horizon_independence": len({r.get("target_hash") for r in horizon_rows.values()}) == len(HORIZONS),
    }


def realized_semivariance(
    h1_frame: pd.DataFrame, intraday_frame: pd.DataFrame | None = None
) -> dict[str, Any]:
    """Calculate positive/negative semivariance without converting missing values to zero."""
    method = "H1_SIGNED_VARIANCE_PROXY"
    missing_reason: str | None = None
    series = pd.DataFrame()
    if isinstance(intraday_frame, pd.DataFrame) and not intraday_frame.empty:
        temp = intraday_frame.copy()
        temp["return"] = np.log(pd.to_numeric(temp["close"], errors="coerce") / pd.to_numeric(temp["close"], errors="coerce").shift(1))
        temp = temp.dropna(subset=["time", "return"])
        temp["h1_time"] = pd.to_datetime(temp["time"], utc=True).dt.floor("h")
        grouped = temp.groupby("h1_time", sort=True)["return"]
        series = pd.DataFrame({
            "positive_semivariance": grouped.apply(lambda x: float(np.square(x[x > 0]).sum())),
            "negative_semivariance": grouped.apply(lambda x: float(np.square(x[x < 0]).sum())),
            "observation_count": grouped.size(),
        }).reset_index().rename(columns={"h1_time": "time"})
        method = "M1_REALIZED_SEMIVARIANCE" if float(intraday_frame.attrs.get("intraday_minutes") or 5.0) <= 1.5 else "M5_REALIZED_SEMIVARIANCE"
    if series.empty:
        if not isinstance(h1_frame, pd.DataFrame) or h1_frame.empty:
            return {
                "status": "UNAVAILABLE", "version": VERSION, "semivariance_method": method,
                "semivariance_sample_count": 0, "semivariance_validation_status": "UNAVAILABLE",
                "missing_reason": "completed H1 data unavailable", "series": pd.DataFrame(),
            }
        returns = np.log(pd.to_numeric(h1_frame["close"], errors="coerce") / pd.to_numeric(h1_frame["close"], errors="coerce").shift(1))
        series = pd.DataFrame({
            "time": pd.to_datetime(h1_frame["time"], utc=True),
            "positive_semivariance": returns.where(returns > 0).pow(2),
            "negative_semivariance": returns.where(returns < 0).pow(2),
            "observation_count": returns.notna().astype(int),
        }).dropna(subset=["time"])
        missing_reason = "completed M1/M5 data unavailable; using signed H1-return variance proxy"
    recent = series.tail(24)
    pos = float(pd.to_numeric(recent["positive_semivariance"], errors="coerce").sum(min_count=1)) if not recent.empty else math.nan
    neg = float(pd.to_numeric(recent["negative_semivariance"], errors="coerce").sum(min_count=1)) if not recent.empty else math.nan
    total = pos + neg if math.isfinite(pos) and math.isfinite(neg) else math.nan
    downside = None if not math.isfinite(total) or total <= 0 else neg / total
    upside = None if not math.isfinite(total) or total <= 0 else pos / total
    imbalance = None if downside is None or upside is None else (upside - downside)
    validation = "PRIMARY_INTRADAY_EVIDENCE" if method != "H1_SIGNED_VARIANCE_PROXY" else "PROXY_RELIABILITY_PENALTY"
    return {
        "status": "AVAILABLE" if math.isfinite(pos) and math.isfinite(neg) else "UNAVAILABLE",
        "version": VERSION,
        "positive_realized_semivariance": None if not math.isfinite(pos) else pos,
        "negative_realized_semivariance": None if not math.isfinite(neg) else neg,
        "downside_share": downside, "upside_share": upside,
        "semivariance_imbalance": imbalance,
        "buy_directional_tail_pressure": downside,
        "sell_directional_tail_pressure": upside,
        "semivariance_method": method,
        "semivariance_sample_count": int(pd.to_numeric(series["observation_count"], errors="coerce").sum()),
        "semivariance_validation_status": validation,
        "missing_reason": missing_reason,
        "series": series.reset_index(drop=True),
    }


__all__ = ["VERSION", "har_h1_forecasts", "realized_semivariance"]
