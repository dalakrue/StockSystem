"""MMSE/Wiener/correlation weighting for existing Power BI paths.

This is an additive post-calibration step.  It does not create a projection
model; it only combines the existing red/yellow/blue paths using settled error
samples already produced by the project.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional

import numpy as np
import pandas as pd

VERSION = "powerbi-mmse-wiener-20260618-v1"
PATHS = ("red", "yellow", "blue")


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _normalize(scores: Mapping[str, float], fallback: Mapping[str, float]) -> dict[str, float]:
    valid = {key: max(0.0, _finite(value, 0.0)) for key, value in scores.items() if _finite(value, 0.0) > 0}
    if not valid:
        valid = {key: max(0.0, _finite(value, 0.0)) for key, value in fallback.items() if _finite(value, 0.0) > 0}
    total = sum(valid.values())
    if total <= 0:
        return {}
    weights = {key: value / total for key, value in valid.items()}
    # Prevent a small, noisy sample from monopolising the combination.
    if len(weights) > 1:
        capped = {key: min(0.78, value) for key, value in weights.items()}
        total = sum(capped.values())
        weights = {key: value / total for key, value in capped.items()}
    return weights


def _residual_metrics(values: Any, *, signal_variance: float, atr: float) -> dict[str, Any]:
    array = pd.to_numeric(pd.Series(list(values or [])), errors="coerce").dropna().to_numpy(dtype=float)
    if len(array) < 8:
        return {"sample_count": int(len(array)), "valid": False, "score": 0.0, "reason": "INSUFFICIENT SAMPLE"}
    mse = float(np.mean(np.square(array)))
    mae = float(np.mean(np.abs(array)))
    bias = float(np.mean(array))
    rmse = math.sqrt(max(mse, 1e-18))
    direction_accuracy = float(np.mean(np.sign(array[1:]) != np.sign(array[:-1]))) if len(array) > 1 else 0.5
    lag_correlation = float(abs(pd.Series(array).autocorr(lag=1))) if len(array) >= 12 else 0.0
    if not math.isfinite(lag_correlation):
        lag_correlation = 0.0
    reliability = min(1.0, len(array) / 60.0) * max(0.05, 1.0 - mae / max(atr * 3.0, 1e-12))
    wiener_gain = signal_variance / max(signal_variance + mse, 1e-18)
    drift_ratio = abs(bias) / max(rmse, 1e-12)
    stale_or_drifted = drift_ratio >= 1.35 or lag_correlation >= 0.90
    lag_penalty = max(0.10, 1.0 - 0.65 * lag_correlation)
    score = 0.0 if stale_or_drifted else reliability * wiener_gain * lag_penalty / max(mse, (atr * 0.05) ** 2, 1e-18)
    return {
        "sample_count": int(len(array)), "valid": not stale_or_drifted, "mse": mse, "mae": mae,
        "bias": bias, "rmse": rmse, "direction_change_accuracy_proxy": direction_accuracy,
        "lagged_residual_correlation": lag_correlation, "reliability": reliability,
        "wiener_gain": wiener_gain, "drift_ratio": drift_ratio, "score": score,
        "reason": "CRITICAL DRIFT OR REPEATED LAG" if stale_or_drifted else "VALID",
        "q10": float(np.quantile(array, 0.10)), "q90": float(np.quantile(array, 0.90)),
    }


def upgrade_projection_bundle(
    bundle: Mapping[str, Any],
    *,
    market_data: pd.DataFrame,
    regime_conditioned_distributions: Optional[Mapping[str, Any]] = None,
    transition_state: Any = None,
) -> Dict[str, Any]:
    """Reweight existing paths before visual smoothing and preserve full audit."""
    result = dict(bundle or {})
    if not result.get("ok"):
        return result
    raw = result.get("raw")
    main_before = result.get("main")
    audit = dict(result.get("audit") or {})
    residual_samples = dict(audit.get("horizon_residual_samples") or {})
    old_weights = result.get("path_weights")
    if not isinstance(raw, pd.DataFrame) or raw.empty or not isinstance(main_before, pd.DataFrame) or main_before.empty:
        return result
    market = market_data.copy(deep=False) if isinstance(market_data, pd.DataFrame) else pd.DataFrame()
    atr = _finite((result.get("summary") or {}).get("atr_price"), 0.0)
    if atr <= 0 and not market.empty and {"high", "low"}.issubset(market.columns):
        atr = _finite((pd.to_numeric(market["high"], errors="coerce") - pd.to_numeric(market["low"], errors="coerce")).abs().tail(24).median(), 0.0005)
    atr = max(atr, 1e-8)
    anchor = _finite((result.get("summary") or {}).get("anchor_price"), _finite(audit.get("anchor_price"), 1.0))
    transition_text = str(transition_state or "").upper()
    transition_multiplier = 1.20 if "WAIT" in transition_text else 1.12 if "PROTECT" in transition_text else 1.06 if "WATCH" in transition_text else 1.0
    old = old_weights.copy() if isinstance(old_weights, pd.DataFrame) else pd.DataFrame()
    rows = []
    weighted_main = []
    lower = []
    upper = []
    previous = anchor
    distributions = dict((regime_conditioned_distributions or {}).get("horizons") or {})

    for position, raw_row in raw.reset_index(drop=True).iterrows():
        step = int(_finite(raw_row.get("step"), position + 1))
        path_values = {path: _finite(raw_row.get(f"{path}_path"), float("nan")) for path in PATHS}
        path_values = {path: value for path, value in path_values.items() if math.isfinite(value)}
        old_row = old[old.get("step", pd.Series(dtype=float)) == step].iloc[0].to_dict() if not old.empty and "step" in old.columns and (old["step"] == step).any() else {}
        fallback = {path: _finite(old_row.get(path), 1.0 / max(1, len(path_values))) for path in path_values}
        signal_variance = float(np.var([value - previous for value in path_values.values()])) if len(path_values) > 1 else atr ** 2
        metrics = {}
        scores = {}
        for path in path_values:
            metric = _residual_metrics(residual_samples.get(f"{path}_H+{step}", []), signal_variance=max(signal_variance, atr ** 2 * 0.05), atr=atr)
            metrics[path] = metric
            scores[path] = float(metric.get("score", 0.0))
        weights = _normalize(scores, fallback)
        if weights:
            central = sum(path_values[path] * weights.get(path, 0.0) for path in path_values)
        elif path_values:
            central = float(np.median(list(path_values.values())))
        else:
            central = previous
        # Evaluate unsmoothed consensus first.  Only then apply a conservative
        # Wiener-style step limiter for chart stability.
        unsmoothed = central
        step_limit = atr * (1.9 if transition_multiplier > 1.1 else 1.55)
        central = previous + max(-step_limit, min(step_limit, unsmoothed - previous))
        central = max(central, 1e-9)

        weighted_residuals = []
        q10 = q90 = 0.0
        for path, weight in weights.items():
            metric = metrics.get(path, {})
            q10 += weight * _finite(metric.get("q10"), -atr)
            q90 += weight * _finite(metric.get("q90"), atr)
            weighted_residuals.append(metric)
        empirical = distributions.get(f"{step}h") or distributions.get("3h") or {}
        empirical_down = abs(_finite(empirical.get("p10"), q10))
        empirical_up = abs(_finite(empirical.get("p90"), q90))
        disagreement = float(np.std(list(path_values.values()))) if len(path_values) > 1 else 0.0
        lower_extent = max(abs(min(q10, 0.0)), empirical_down, atr * (0.45 + 0.17 * math.sqrt(step)))
        upper_extent = max(max(q90, 0.0), empirical_up, atr * (0.45 + 0.17 * math.sqrt(step)))
        lower_extent = (lower_extent + disagreement * 0.75) * transition_multiplier
        upper_extent = (upper_extent + disagreement * 0.75) * transition_multiplier
        weighted_main.append(central)
        lower.append(max(central - lower_extent, 1e-9))
        upper.append(central + upper_extent)
        rows.append({
            "step": step, **{path: round(weights.get(path, 0.0), 8) for path in PATHS},
            "unsmoothed_consensus": unsmoothed, "weighted_main": central,
            "available_paths": len(path_values), "transition_multiplier": transition_multiplier,
            "metrics": metrics,
        })
        previous = central

    upgraded_main = main_before.copy(deep=False).reset_index(drop=True)
    upgraded_main["main_path"] = weighted_main
    upgraded_main["lower_band"] = np.minimum(np.asarray(lower), np.asarray(weighted_main))
    upgraded_main["upper_band"] = np.maximum(np.asarray(upper), np.asarray(weighted_main))
    upgraded_main["band_width"] = np.maximum(
        np.asarray(weighted_main) - upgraded_main["lower_band"].to_numpy(dtype=float),
        upgraded_main["upper_band"].to_numpy(dtype=float) - np.asarray(weighted_main),
    )
    upgraded_main["source_spread"] = [
        float(np.std([_finite(raw.iloc[index].get(f"{path}_path"), np.nan) for path in PATHS if math.isfinite(_finite(raw.iloc[index].get(f"{path}_path"), np.nan))]))
        if index < len(raw) else 0.0 for index in range(len(upgraded_main))
    ]
    weight_frame = pd.DataFrame([{key: value for key, value in row.items() if key != "metrics"} for row in rows])
    diagnostics = {f"H+{row['step']}": row["metrics"] for row in rows}
    summary = dict(result.get("summary") or {})
    summary.update({
        "mmse_wiener_version": VERSION, "weighting_policy": "reliability / settled OOS MSE × Wiener gain × lag penalty",
        "weighting_applied_before_visual_smoothing": True,
        "mmse_valid_horizons": int(sum(any(metric.get("valid") for metric in row["metrics"].values()) for row in rows)),
    })
    audit.update({
        "pre_mmse_main": main_before.copy(deep=False), "pre_mmse_path_weights": old.copy(deep=False),
        "mmse_path_weights": weight_frame, "mmse_path_diagnostics": diagnostics,
        "mmse_regime_conditioned_distributions": dict(regime_conditioned_distributions or {}),
    })
    result.update({"main": upgraded_main, "path_weights": weight_frame, "summary": summary, "audit": audit})
    return result


__all__ = ["VERSION", "upgrade_projection_bundle"]
