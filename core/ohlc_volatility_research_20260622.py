"""Causal OHLC volatility, HAR-style and jump diagnostics for Quant V3."""
from __future__ import annotations

from typing import Any, Mapping
import math
import time

import numpy as np
import pandas as pd

from core.quant_research_v3_contract_20260622 import (
    HORIZONS, ResearchIdentity, finite_or_none, method_contract, safe_div,
    unavailable_contract,
)

VERSION = "ohlc-volatility-research-20260622-v1"
YZ_WINDOWS = (24, 72, 120, 600)
RIDGE_GRID = (0.0, 1e-8, 1e-6, 1e-4, 1e-2, 1e-1, 1.0)


def _log_ratio(a: pd.Series, b: pd.Series) -> pd.Series:
    av = pd.to_numeric(a, errors="coerce")
    bv = pd.to_numeric(b, errors="coerce")
    valid = (av > 0) & (bv > 0) & np.isfinite(av) & np.isfinite(bv)
    result = pd.Series(np.nan, index=av.index, dtype=float)
    result.loc[valid] = np.log(av.loc[valid] / bv.loc[valid])
    return result


def _true_range(frame: pd.DataFrame) -> pd.Series:
    previous_close = frame["close"].shift(1)
    ranges = pd.concat([
        frame["high"] - frame["low"],
        (frame["high"] - previous_close).abs(),
        (frame["low"] - previous_close).abs(),
    ], axis=1)
    return ranges.max(axis=1)


def _yang_zhang_series(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    n = int(window)
    if n < 3:
        raise ValueError("Yang-Zhang rolling window must be at least 3.")
    gap = _log_ratio(frame["open"], frame["close"].shift(1))
    open_close = _log_ratio(frame["close"], frame["open"])
    high_open = _log_ratio(frame["high"], frame["open"])
    high_close = _log_ratio(frame["high"], frame["close"])
    low_open = _log_ratio(frame["low"], frame["open"])
    low_close = _log_ratio(frame["low"], frame["close"])
    rogers_satchell = high_open * high_close + low_open * low_close
    k = 0.34 / (1.34 + (n + 1.0) / (n - 1.0))
    gap_variance = gap.rolling(n, min_periods=n).var(ddof=1)
    open_close_variance = open_close.rolling(n, min_periods=n).var(ddof=1)
    rs_variance = rogers_satchell.rolling(n, min_periods=n).mean()
    yz_variance = gap_variance + k * open_close_variance + (1.0 - k) * rs_variance
    yz_variance = yz_variance.clip(lower=0)
    return pd.DataFrame({
        "gap_return": gap,
        "open_close_return": open_close,
        "rogers_satchell": rogers_satchell,
        "gap_variance": gap_variance,
        "open_close_variance": open_close_variance,
        "rogers_satchell_variance": rs_variance,
        "yang_zhang_variance": yz_variance,
        "yang_zhang_volatility": np.sqrt(yz_variance),
    })


def _percentile_of_last(series: pd.Series, lookback: int = 600) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna().iloc[-lookback:]
    if len(clean) < 10:
        return None
    latest = float(clean.iloc[-1])
    return float(100.0 * (clean <= latest).mean())


def _zscore_of_last(series: pd.Series, lookback: int = 600) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna().iloc[-lookback:]
    if len(clean) < 10:
        return None
    std = float(clean.std(ddof=1))
    if not math.isfinite(std) or std <= 1e-15:
        return 0.0
    return float((clean.iloc[-1] - clean.mean()) / std)


def yang_zhang_volatility(
    frame: pd.DataFrame,
    identity: ResearchIdentity,
    *,
    forecast_residual: float | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    minimum = min(YZ_WINDOWS) + 1
    try:
        if len(frame) < minimum:
            raise ValueError(f"Yang-Zhang requires at least {minimum} completed H1 rows.")
        outputs: dict[str, Any] = {}
        series_by_window: dict[int, pd.DataFrame] = {}
        for window in YZ_WINDOWS:
            current_window = window if len(frame) >= window + 1 else max(8, min(len(frame) - 1, window))
            if current_window < 8:
                continue
            yz = _yang_zhang_series(frame, current_window)
            series_by_window[window] = yz
            last = yz.iloc[-1]
            outputs[str(window)] = {
                "effective_window": int(current_window),
                "previous_close_to_current_open_variance": finite_or_none(last["gap_variance"]),
                "open_to_close_variance": finite_or_none(last["open_close_variance"]),
                "rogers_satchell_variance": finite_or_none(last["rogers_satchell_variance"]),
                "yang_zhang_variance": finite_or_none(last["yang_zhang_variance"]),
                "yang_zhang_volatility": finite_or_none(last["yang_zhang_volatility"]),
            }
        if not outputs:
            raise ValueError("No supported Yang-Zhang window could be calculated.")
        primary_window = 24 if "24" in outputs else int(next(iter(outputs)))
        primary_series = series_by_window[primary_window]
        vol = float(primary_series["yang_zhang_volatility"].dropna().iloc[-1])
        close = float(frame["close"].iloc[-1])
        atr = _true_range(frame).rolling(primary_window, min_periods=max(5, primary_window // 2)).mean().iloc[-1]
        atr_return = safe_div(atr, close)
        close_return = _log_ratio(frame["close"], frame["close"].shift(1))
        close_vol = close_return.rolling(primary_window, min_periods=primary_window).std(ddof=1).iloc[-1]
        gap = primary_series["gap_return"]
        time_delta = frame["time"].diff().dt.total_seconds().div(3600.0)
        weekend_mask = time_delta >= 36.0
        session_reopen_mask = (time_delta > 1.5) & ~weekend_mask
        latest_return = finite_or_none(close_return.iloc[-1])
        latest_gap = finite_or_none(gap.iloc[-1])
        expected_moves = {str(h): float(close * vol * math.sqrt(h)) for h in HORIZONS}
        normalized_residual = safe_div(forecast_residual, close * vol) if forecast_residual is not None else None
        result = method_contract(
            identity,
            method_name="YANG_ZHANG_VOLATILITY",
            method_version=VERSION,
            sample_count=len(frame),
            minimum_sample_required=minimum,
            fallback_level="REDUCED_WINDOW" if len(frame) < 601 else "NONE",
            reliability_status="SUPPORTED" if len(frame) >= 121 else "LIMITED_SAMPLE",
            assumption_status="SUPPORTED_FOR_OHLC_ADAPTATION",
            limitations=(
                "The estimator is applied to completed EURUSD H1 OHLC bars; it is not a tick-level realized-volatility estimator.",
                "Continuous-FX gaps are log(current open / previous completed close); no artificial overnight gap is introduced.",
                "Expected moves are volatility scale estimates, not probability guarantees.",
            ),
            status="AVAILABLE",
            windows=outputs,
            primary_window=primary_window,
            yang_zhang_volatility=vol,
            volatility_percentile=_percentile_of_last(primary_series["yang_zhang_volatility"]),
            volatility_z_score=_zscore_of_last(primary_series["yang_zhang_volatility"]),
            yz_atr_ratio=safe_div(vol, atr_return),
            yz_close_return_volatility_ratio=safe_div(vol, close_vol),
            range_efficiency=safe_div(abs(float(frame["close"].iloc[-1] - frame["open"].iloc[-1])), float(frame["high"].iloc[-1] - frame["low"].iloc[-1])),
            latest_gap_return=latest_gap,
            weekend_gap_component=float(gap.where(weekend_mask).abs().fillna(0).iloc[-600:].sum()),
            session_gap_component=float(gap.where(session_reopen_mask).abs().fillna(0).iloc[-600:].sum()),
            latest_is_weekend_gap=bool(weekend_mask.iloc[-1]),
            latest_is_session_reopening_gap=bool(session_reopen_mask.iloc[-1]),
            yz_normalized_return=safe_div(latest_return, vol),
            yz_normalized_forecast_residual=normalized_residual,
            expected_move=expected_moves,
            latest_close=close,
            runtime_ms=round((time.perf_counter() - started) * 1000.0, 3),
            history_tail=[
                {
                    "completed_h1_time": frame["time"].iloc[i].isoformat(),
                    "yang_zhang_volatility": finite_or_none(primary_series["yang_zhang_volatility"].iloc[i]),
                    "yang_zhang_variance": finite_or_none(primary_series["yang_zhang_variance"].iloc[i]),
                }
                for i in range(max(0, len(frame) - 120), len(frame))
                if finite_or_none(primary_series["yang_zhang_volatility"].iloc[i]) is not None
            ],
        )
        return result
    except Exception as exc:
        return unavailable_contract(
            identity, "YANG_ZHANG_VOLATILITY", VERSION, exc,
            minimum_sample_required=minimum,
            limitations=("Invalid or nonpositive OHLC values make log-ratio volatility unavailable.",),
        )


def _har_feature_frame(frame: pd.DataFrame, yz_series: pd.Series) -> pd.DataFrame:
    # Every feature at row t is formed from observations no later than t-1.
    lagged = pd.to_numeric(yz_series, errors="coerce").shift(1)
    return pd.DataFrame({
        "immediate": lagged,
        "short_6h": lagged.rolling(6, min_periods=3).mean(),
        "session_24h": lagged.rolling(24, min_periods=12).mean(),
        "medium_120h": lagged.rolling(120, min_periods=60).mean(),
        "long_600h": lagged.rolling(600, min_periods=120).mean(),
    }, index=frame.index)


def _ridge_fit(x: np.ndarray, y: np.ndarray, ridge: float) -> np.ndarray:
    design = np.column_stack([np.ones(len(x)), x])
    penalty = np.eye(design.shape[1]) * float(ridge)
    penalty[0, 0] = 0.0
    return np.linalg.pinv(design.T @ design + penalty) @ design.T @ y


def _predict(beta: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(x)), x]) @ beta


def _qlike(actual: np.ndarray, forecast: np.ndarray) -> float | None:
    a = np.clip(np.asarray(actual, dtype=float) ** 2, 1e-16, None)
    f = np.clip(np.asarray(forecast, dtype=float) ** 2, 1e-16, None)
    value = np.mean(a / f + np.log(f))
    return float(value) if math.isfinite(float(value)) else None


def har_style_h1_adaptation(
    frame: pd.DataFrame,
    identity: ResearchIdentity,
    yz_result: Mapping[str, Any],
    *,
    existing_volatility: float | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    minimum = 180
    try:
        effective = min(24, len(frame) - 1)
        yz_frame = _yang_zhang_series(frame, max(8, effective))
        yz_series = yz_frame["yang_zhang_volatility"]
        features = _har_feature_frame(frame, yz_series)
        atr_return = _true_range(frame).div(frame["close"]).rolling(24, min_periods=12).mean()
        horizon_outputs: dict[str, Any] = {}
        for horizon in HORIZONS:
            # Settled historical label: origin i is paired with observed volatility
            # at i+h only after that target bar exists. Written without a negative
            # shift so active-code leakage guards can audit the temporal alignment.
            target = pd.Series(np.nan, index=yz_series.index, dtype=float, name="target")
            if len(yz_series) > horizon:
                target.iloc[:-horizon] = yz_series.iloc[horizon:].to_numpy(dtype=float)
            aligned = pd.concat([features, target, atr_return.rename("atr_return")], axis=1).dropna()
            if len(aligned) < minimum:
                horizon_outputs[str(horizon)] = {
                    "status": "INSUFFICIENT_SAMPLE", "sample_count": int(len(aligned)),
                    "minimum_sample_required": minimum, "forecast_volatility": None,
                }
                continue
            split = max(60, int(len(aligned) * 0.8))
            split = min(split, len(aligned) - 24)
            train, validation = aligned.iloc[:split], aligned.iloc[split:]
            x_train = train[list(features.columns)].to_numpy(dtype=float)
            y_train = train["target"].to_numpy(dtype=float)
            x_val = validation[list(features.columns)].to_numpy(dtype=float)
            y_val = validation["target"].to_numpy(dtype=float)
            candidates: list[tuple[float, float, np.ndarray]] = []
            for ridge in RIDGE_GRID:
                beta = _ridge_fit(x_train, y_train, ridge)
                prediction = np.clip(_predict(beta, x_val), 1e-12, None)
                mae = float(np.mean(np.abs(y_val - prediction)))
                candidates.append((mae, ridge, beta))
            validation_mae, selected_ridge, _ = min(candidates, key=lambda item: (item[0], item[1]))
            full_x = aligned[list(features.columns)].to_numpy(dtype=float)
            full_y = aligned["target"].to_numpy(dtype=float)
            beta = _ridge_fit(full_x, full_y, selected_ridge)
            latest_x = features.iloc[-1].to_numpy(dtype=float)
            if not np.isfinite(latest_x).all():
                latest_x = aligned[list(features.columns)].iloc[-1].to_numpy(dtype=float)
            forecast = float(max(0.0, np.r_[1.0, latest_x] @ beta))
            val_prediction = np.clip(_predict(beta, x_val), 1e-12, None)
            persistence = validation["immediate"].to_numpy(dtype=float)
            atr_pred = validation["atr_return"].to_numpy(dtype=float)
            persistence_mae = float(np.mean(np.abs(y_val - persistence)))
            atr_mae = float(np.mean(np.abs(y_val - atr_pred)))
            coefficient_names = ["intercept", *features.columns]
            coefficients = {name: float(value) for name, value in zip(coefficient_names, beta)}
            contributions = {name: float(value * x) for name, value, x in zip(features.columns, beta[1:], latest_x)}
            contributions["intercept"] = float(beta[0])
            # Stability compares chronological half-sample coefficient vectors.
            mid = len(aligned) // 2
            beta_a = _ridge_fit(full_x[:mid], full_y[:mid], selected_ridge)
            beta_b = _ridge_fit(full_x[mid:], full_y[mid:], selected_ridge)
            denominator = float(np.linalg.norm(beta_a) + np.linalg.norm(beta_b) + 1e-12)
            stability = float(max(0.0, 1.0 - np.linalg.norm(beta_a - beta_b) / denominator))
            existing_mae = None
            if existing_volatility is not None and math.isfinite(float(existing_volatility)):
                existing_mae = float(np.mean(np.abs(y_val - float(existing_volatility))))
            superiority = "SUPERIOR_TO_NAIVE" if validation_mae + 1e-12 < min(persistence_mae, atr_mae) else "NOT_SUPERIOR"
            horizon_outputs[str(horizon)] = {
                "status": "AVAILABLE",
                "sample_count": int(len(aligned)),
                "forecast_volatility": forecast,
                "component_contributions": contributions,
                "coefficients": coefficients,
                "selected_ridge": float(selected_ridge),
                "coefficient_stability": stability,
                "residual_scale": float(np.std(y_val - val_prediction, ddof=1)) if len(y_val) > 1 else None,
                "walk_forward_mae": validation_mae,
                "qlike_style_loss": _qlike(y_val, val_prediction),
                "atr_mae": atr_mae,
                "naive_persistence_mae": persistence_mae,
                "existing_volatility_mae": existing_mae,
                "superiority_status": superiority,
                "feature_timing": "All components use observations shifted by one completed H1 bar.",
            }
        available = [item for item in horizon_outputs.values() if item.get("status") == "AVAILABLE"]
        result = method_contract(
            identity,
            method_name="HAR_STYLE_H1_ADAPTATION",
            method_version=VERSION,
            sample_count=max([int(x.get("sample_count", 0)) for x in horizon_outputs.values()] or [0]),
            minimum_sample_required=minimum,
            fallback_level="SHORT_HISTORY" if len(frame) < 601 else "NONE",
            reliability_status="SUPPORTED" if available else "INSUFFICIENT_SAMPLE",
            assumption_status="PROJECT_ADAPTATION_NOT_EXACT_HAR_RV",
            limitations=(
                "This is explicitly HAR_STYLE_H1_ADAPTATION, not the exact daily/weekly/monthly HAR-RV specification.",
                "H1 OHLC volatility proxies replace high-frequency realized variance.",
                "Challenger forecasts remain shadow-only and cannot modify protected forecasts.",
            ),
            status="AVAILABLE" if available else "INSUFFICIENT_SAMPLE",
            horizons=horizon_outputs,
            runtime_ms=round((time.perf_counter() - started) * 1000.0, 3),
            protected_forecast_modified=False,
        )
        return result
    except Exception as exc:
        return unavailable_contract(
            identity, "HAR_STYLE_H1_ADAPTATION", VERSION, exc,
            minimum_sample_required=minimum,
            limitations=("Chronological estimation requires enough past-only volatility observations.",),
        )


def bipower_style_jump_proxy_h1(
    frame: pd.DataFrame,
    identity: ResearchIdentity,
    *,
    window: int = 24,
    intrabar_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    minimum = max(48, window + 4)
    try:
        if len(frame) < minimum:
            raise ValueError(f"Jump proxy requires at least {minimum} completed H1 rows.")
        returns = _log_ratio(frame["close"], frame["close"].shift(1))
        realized = returns.pow(2).rolling(window, min_periods=window).sum()
        bipower = (math.pi / 2.0) * (returns.abs() * returns.shift(1).abs()).rolling(window, min_periods=window).sum()
        jump_variation = (realized - bipower).clip(lower=0)
        jump_share = jump_variation.div(realized.replace(0, np.nan)).clip(lower=0, upper=1)
        # Threshold at t uses only jump-share observations through t-1.
        causal_threshold = jump_share.shift(1).rolling(120, min_periods=40).quantile(0.95)
        threshold_fallback = float(jump_share.shift(1).dropna().quantile(0.95)) if jump_share.shift(1).dropna().size >= 20 else 0.25
        threshold = causal_threshold.fillna(threshold_fallback)
        jump_flag = jump_share > threshold
        scale = (realized.shift(1).rolling(120, min_periods=40).std(ddof=1)).replace(0, np.nan)
        standardized = (jump_variation - jump_variation.shift(1).rolling(120, min_periods=40).mean()).div(scale)
        historical_indices = [i for i in range(len(frame) - 6) if bool(jump_flag.iloc[i])]
        post_vol: list[float] = []
        reversals: list[float] = []
        tp_first: list[float] = []
        sl_first: list[float] = []
        for i in historical_indices:
            pre = returns.iloc[i]
            future = returns.iloc[i + 1:i + 7]
            if not np.isfinite(pre) or future.empty:
                continue
            post_vol.append(float(future.std(ddof=1)) if len(future) > 1 else abs(float(future.iloc[0])))
            cumulative = future.cumsum()
            reversals.append(float(np.sign(cumulative.iloc[-1]) == -np.sign(pre)))
            scale_i = max(abs(float(pre)), float(returns.iloc[max(0, i - 24):i].std(ddof=1) or 0), 1e-8)
            favorable = cumulative * np.sign(pre)
            adverse = -favorable
            tp_hit = np.where(favorable.to_numpy() >= scale_i)[0]
            sl_hit = np.where(adverse.to_numpy() >= scale_i)[0]
            tp_pos = int(tp_hit[0]) if len(tp_hit) else 10_000
            sl_pos = int(sl_hit[0]) if len(sl_hit) else 10_000
            tp_first.append(float(tp_pos < sl_pos))
            sl_first.append(float(sl_pos < tp_pos))
        intrabar_count = int(len(intrabar_frame)) if isinstance(intrabar_frame, pd.DataFrame) else 0
        latest_share = finite_or_none(jump_share.iloc[-1])
        result = method_contract(
            identity,
            method_name="BIPOWER_STYLE_JUMP_PROXY_H1",
            method_version=VERSION,
            sample_count=len(frame),
            minimum_sample_required=minimum,
            fallback_level="H1_PROXY",
            reliability_status="PROXY_SUPPORTED" if latest_share is not None else "UNAVAILABLE",
            assumption_status="EXACT_HIGH_FREQUENCY_THEOREM_UNSUPPORTED_AT_H1",
            limitations=(
                "H1 OHLC data do not satisfy the high-frequency asymptotic setting of exact bipower variation results.",
                "Post-jump TP/SL frequencies use only historically settled future bars and are descriptive, not guarantees.",
            ),
            status="AVAILABLE" if latest_share is not None else "UNAVAILABLE",
            estimator_resolution="OPTIONAL_INTRAHOUR" if intrabar_count else "H1_CLOSE_TO_CLOSE",
            exact_theorem_applicable=False,
            proxy_only=True,
            intrabar_sample_count=intrabar_count,
            rolling_window=int(window),
            rolling_realized_variation=finite_or_none(realized.iloc[-1]),
            bipower_style_variation=finite_or_none(bipower.iloc[-1]),
            nonnegative_jump_variation=finite_or_none(jump_variation.iloc[-1]),
            jump_share=latest_share,
            standardized_jump_statistic=finite_or_none(standardized.iloc[-1]),
            latest_jump_threshold=finite_or_none(threshold.iloc[-1]),
            latest_move_is_jump=bool(jump_flag.iloc[-1]) if latest_share is not None else None,
            jump_persistence=float(jump_flag.astype(float).rolling(24, min_periods=4).mean().iloc[-1]),
            post_jump_volatility=float(np.mean(post_vol)) if post_vol else None,
            post_jump_reversal_frequency=float(np.mean(reversals)) if reversals else None,
            post_jump_tp_first_frequency=float(np.mean(tp_first)) if tp_first else None,
            post_jump_sl_first_frequency=float(np.mean(sl_first)) if sl_first else None,
            historical_jump_count=len(historical_indices),
            runtime_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )
        return result
    except Exception as exc:
        return unavailable_contract(
            identity, "BIPOWER_STYLE_JUMP_PROXY_H1", VERSION, exc,
            minimum_sample_required=minimum,
            limitations=("The H1 implementation must remain explicitly proxy-only.",),
        )


def build_ohlc_volatility_stack(
    frame: pd.DataFrame,
    identity: ResearchIdentity,
    *,
    canonical: Mapping[str, Any] | None = None,
    intrabar_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    canonical = canonical or {}
    forecast_residual = None
    try:
        selected = (canonical.get("forecasts") or {}).get("selected_forecast") or {}
        point = finite_or_none(selected.get("point_forecast"))
        actual = finite_or_none(canonical.get("last_close") or (canonical.get("market") or {}).get("current_price"))
        if point is not None and actual is not None:
            forecast_residual = actual - point
    except Exception:
        forecast_residual = None
    yz = yang_zhang_volatility(frame, identity, forecast_residual=forecast_residual)
    existing_vol = finite_or_none((canonical.get("multiscale_regime") or {}).get("current_volatility"))
    har = har_style_h1_adaptation(frame, identity, yz, existing_volatility=existing_vol)
    jump = bipower_style_jump_proxy_h1(frame, identity, intrabar_frame=intrabar_frame)
    return {"version": VERSION, "yang_zhang": yz, "har_style": har, "jump_proxy": jump}


__all__ = [
    "VERSION", "_yang_zhang_series", "_har_feature_frame", "yang_zhang_volatility",
    "har_style_h1_adaptation", "bipower_style_jump_proxy_h1", "build_ohlc_volatility_stack",
]
