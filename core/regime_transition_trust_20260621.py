# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Read-only regime-transition, drift, calibration and system-trust evidence.

This module wraps the existing canonical regime and forecast outputs.  It does
not create a second prediction engine and never overwrites the protected regime,
priority, reliability, conflict or BUY/SELL/WAIT decisions.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
from math import exp, isfinite, lgamma, log, pi, sqrt
from typing import Any, Iterable, Mapping, MutableMapping, Sequence
import json

import numpy as np
import pandas as pd

from core.generation_identity_20260707 import numeric_generation

VERSION = "regime-transition-trust-20260621-v1"
SCHEMA_VERSION = "regime-transition-trust-schema-1.0.0"
DRIFT_LABELS = {
    "NONE", "SUDDEN", "GRADUAL", "INCREMENTAL", "RECURRING",
    "VOLATILITY_ONLY", "FEATURE_DRIFT", "PREDICTION_ERROR_DRIFT",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if isfinite(number) else default
    except Exception:
        return default


def _clip(value: Any, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, _num(value)))


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _find_col(frame: pd.DataFrame, aliases: Sequence[str]) -> str | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    normalized = {_norm(column): str(column) for column in frame.columns}
    for alias in aliases:
        key = _norm(alias)
        if key in normalized:
            return normalized[key]
    for key, column in normalized.items():
        if any(_norm(alias) in key for alias in aliases if _norm(alias)):
            return column
    return None


def _completed_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    work = frame.copy(deep=False)
    time_col = _find_col(work, ("time", "timestamp", "datetime", "date"))
    close_col = _find_col(work, ("close", "actual_close", "price"))
    if not time_col or not close_col:
        return pd.DataFrame()
    work = work.copy()
    work[time_col] = pd.to_datetime(work[time_col], errors="coerce", utc=True)
    work[close_col] = pd.to_numeric(work[close_col], errors="coerce")
    work = work.dropna(subset=[time_col, close_col]).sort_values(time_col).drop_duplicates(time_col, keep="last")
    work = work.rename(columns={time_col: "__time", close_col: "__close"})
    return work.reset_index(drop=True)


def _frame_fingerprint(frame: pd.DataFrame) -> str:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return "EMPTY"
    sample = frame.tail(512).copy(deep=False)
    payload = {
        "rows": len(frame),
        "columns": [str(c) for c in frame.columns],
        "tail": sample.to_json(date_format="iso", orient="split", default_handler=str),
    }
    return sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8", errors="ignore")).hexdigest()


def _student_t_logpdf(x: float, mu: float, kappa: float, alpha: float, beta: float) -> float:
    df = max(2.0 * alpha, 1e-6)
    scale2 = max(beta * (kappa + 1.0) / max(alpha * kappa, 1e-9), 1e-9)
    z2 = (x - mu) ** 2 / scale2
    return (
        lgamma((df + 1.0) / 2.0) - lgamma(df / 2.0)
        - 0.5 * (log(df * pi) + log(scale2))
        - ((df + 1.0) / 2.0) * log(1.0 + z2 / df)
    )


def bayesian_online_changepoint(
    values: Iterable[float], *, hazard_lambda: float = 72.0, max_run_length: int = 240,
) -> dict[str, Any]:
    """Adams-MacKay style run-length recursion with Normal-Gamma predictions."""
    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)]
    if len(array) < 8:
        return {"probability": 0.0, "most_likely_run_length": int(len(array)), "run_length_uncertainty": 1.0, "samples": int(len(array))}
    array = array[-max(16, int(max_run_length)) :]
    scale = float(np.nanstd(array))
    if not isfinite(scale) or scale <= 1e-12:
        scale = 1.0
    center = float(np.nanmedian(array))
    if not isfinite(center):
        center = 0.0
    centered = (array - center) / scale

    hazard = min(max(1.0 / max(float(hazard_lambda), 2.0), 1e-4), 0.5)
    probs = np.array([1.0], dtype=float)
    mu = np.array([0.0], dtype=float)
    kappa = np.array([1.0], dtype=float)
    alpha = np.array([1.0], dtype=float)
    beta = np.array([1.0], dtype=float)
    cp_series: list[float] = []

    for x in centered:
        logs = np.array([_student_t_logpdf(float(x), float(mu[i]), float(kappa[i]), float(alpha[i]), float(beta[i])) for i in range(len(probs))])
        logs -= np.nanmax(logs)
        predictive = np.exp(logs)
        growth = probs * (1.0 - hazard) * predictive
        cp = float(np.sum(probs * hazard * predictive))
        new_probs = np.concatenate(([cp], growth))
        total = float(np.sum(new_probs))
        new_probs = new_probs / total if total > 0 else np.array([1.0])
        if len(new_probs) > max_run_length + 1:
            new_probs = new_probs[: max_run_length + 1]
            new_probs /= max(float(new_probs.sum()), 1e-12)

        old_mu, old_kappa, old_alpha, old_beta = mu, kappa, alpha, beta
        growth_len = min(len(old_mu), max_run_length)
        new_mu = np.empty(len(new_probs), dtype=float)
        new_kappa = np.empty(len(new_probs), dtype=float)
        new_alpha = np.empty(len(new_probs), dtype=float)
        new_beta = np.empty(len(new_probs), dtype=float)

        def update(m: float, k: float, a: float, b: float) -> tuple[float, float, float, float]:
            next_k = k + 1.0
            next_m = (k * m + x) / next_k
            next_a = a + 0.5
            next_b = b + k * (x - m) ** 2 / (2.0 * next_k)
            return next_m, next_k, next_a, next_b

        new_mu[0], new_kappa[0], new_alpha[0], new_beta[0] = update(0.0, 1.0, 1.0, 1.0)
        for i in range(1, len(new_probs)):
            source = min(i - 1, growth_len - 1)
            new_mu[i], new_kappa[i], new_alpha[i], new_beta[i] = update(
                float(old_mu[source]), float(old_kappa[source]), float(old_alpha[source]), float(old_beta[source])
            )
        probs, mu, kappa, alpha, beta = new_probs, new_mu, new_kappa, new_alpha, new_beta
        cp_series.append(float(probs[0]))

    entropy = -float(np.sum(probs * np.log(np.maximum(probs, 1e-12))))
    max_entropy = log(max(len(probs), 2))
    recent_cp = max(cp_series[-3:] or [0.0])
    return {
        "probability": round(_clip(recent_cp * 100.0), 4),
        "most_likely_run_length": int(np.argmax(probs)),
        "run_length_uncertainty": round(_clip((entropy / max(max_entropy, 1e-9)) * 100.0), 4),
        "samples": int(len(array)),
        "posterior_tail": [round(float(x), 8) for x in probs[: min(30, len(probs))]],
    }


def adaptive_window_detection(values: Iterable[float], *, delta: float = 0.002, max_window: int = 512) -> dict[str, Any]:
    """Lightweight ADWIN-style adaptive-window split test."""
    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)][-max_window:]
    n = len(array)
    if n < 24:
        return {"changed": False, "status": "STABLE", "window_size": n, "score": 0.0, "cut": None}
    variance = float(np.var(array, ddof=1)) if n > 2 else 0.0
    log_term = log(2.0 / max(delta, 1e-9))
    best = {"ratio": 0.0, "cut": None, "difference": 0.0, "epsilon": float("inf")}
    min_part = max(8, min(24, n // 4))
    step = max(1, n // 64)
    for cut in range(min_part, n - min_part + 1, step):
        left, right = array[:cut], array[cut:]
        n0, n1 = len(left), len(right)
        harmonic = (1.0 / n0) + (1.0 / n1)
        epsilon = sqrt(max(2.0 * variance * harmonic * log_term, 0.0)) + (2.0 / 3.0) * log_term * harmonic
        difference = abs(float(np.mean(left)) - float(np.mean(right)))
        ratio = difference / max(epsilon, 1e-12)
        if ratio > best["ratio"]:
            best = {"ratio": ratio, "cut": cut, "difference": difference, "epsilon": epsilon}
    changed = bool(best["ratio"] > 1.0)
    window_size = int(n - int(best["cut"])) if changed and best["cut"] is not None else n
    return {
        "changed": changed,
        "status": "CHANGE" if changed else "STABLE",
        "window_size": window_size,
        "score": round(_clip(float(best["ratio"]) * 50.0), 4),
        "cut": best["cut"],
        "mean_difference": round(float(best["difference"]), 8),
        "epsilon": round(float(best["epsilon"]), 8) if isfinite(float(best["epsilon"])) else None,
    }


def _forecast_models(canonical: Mapping[str, Any]) -> list[tuple[str, float, float]]:
    forecasts = _mapping(canonical.get("forecasts"))
    selected = _mapping(forecasts.get("selected"))
    items: list[tuple[str, float, float]] = []
    containers = [
        forecasts.get("models"), forecasts.get("model_forecasts"),
        canonical.get("model_forecasts"), canonical.get("forecast_decomposition"),
        _mapping(canonical.get("powerbi")).get("models"),
    ]
    for container in containers:
        if not isinstance(container, Mapping):
            continue
        for name, value in container.items():
            if isinstance(value, Mapping):
                point = _num(value.get("point_forecast", value.get("forecast", value.get("price"))), np.nan)
                confidence = _num(value.get("confidence", value.get("confidence_pct", 50.0)), 50.0)
            else:
                point, confidence = _num(value, np.nan), 50.0
            if isfinite(point):
                items.append((str(name), point, confidence))
    if not items:
        point = _num(selected.get("point_forecast"), np.nan)
        if isfinite(point):
            items.append(("Selected Forecast", point, _num(selected.get("confidence_pct", selected.get("confidence", 50.0)), 50.0)))
    dedup: dict[str, tuple[str, float, float]] = {}
    for row in items:
        dedup[_norm(row[0])] = row
    return list(dedup.values())


def _settled_calibration(frame: pd.DataFrame, raw_confidence: float) -> dict[str, Any]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {
            "samples": 0, "calibrated_confidence": raw_confidence,
            "expected_calibration_error": None, "brier_score": None,
            "rolling_coverage": None, "absolute_close_error": None,
            "actual_direction": "UNSETTLED", "actual_inside_interval": None,
            "coverage_history": [], "error_history": [],
        }
    work = frame.copy(deep=False)
    conf_col = _find_col(work, ("confidence", "probability", "raw_confidence", "confidence_pct"))
    pred_col = _find_col(work, ("predicted_direction", "prediction_direction", "direction"))
    actual_col = _find_col(work, ("actual_direction", "realized_direction", "outcome_direction"))
    inside_col = _find_col(work, ("actual_inside_interval", "inside_interval", "covered"))
    error_col = _find_col(work, ("absolute_close_error", "abs_error", "absolute_error", "error"))
    if pred_col and actual_col:
        correctness = work[pred_col].astype(str).str.upper().eq(work[actual_col].astype(str).str.upper()).astype(float)
    else:
        correct_col = _find_col(work, ("direction_correct", "correct", "is_correct"))
        correctness = pd.to_numeric(work[correct_col], errors="coerce") if correct_col else pd.Series(dtype=float)
    probabilities = pd.to_numeric(work[conf_col], errors="coerce") if conf_col else pd.Series(raw_confidence / 100.0, index=work.index, dtype=float)
    if not probabilities.empty and float(probabilities.dropna().median() if probabilities.notna().any() else 0) > 1.0:
        probabilities = probabilities / 100.0
    valid = probabilities.notna() & correctness.notna() if not correctness.empty else pd.Series(False, index=work.index)
    probs, actual = probabilities[valid].clip(0, 1), correctness[valid].clip(0, 1)
    ece = None
    brier = None
    calibrated = raw_confidence
    if len(probs):
        bins = np.linspace(0.0, 1.0, 11)
        ece_value = 0.0
        raw_p = raw_confidence / 100.0
        local_accuracy = float(actual.mean())
        for lower, upper in zip(bins[:-1], bins[1:]):
            mask = (probs >= lower) & (probs < upper if upper < 1.0 else probs <= upper)
            if mask.any():
                ece_value += float(mask.mean()) * abs(float(actual[mask].mean()) - float(probs[mask].mean()))
                if lower <= raw_p <= upper:
                    local_accuracy = float(actual[mask].mean())
        weight = len(probs) / (len(probs) + 20.0)
        calibrated = 100.0 * ((1.0 - weight) * raw_p + weight * local_accuracy)
        ece = ece_value * 100.0
        brier = float(np.mean((probs.to_numpy() - actual.to_numpy()) ** 2))
    inside = pd.to_numeric(work[inside_col], errors="coerce") if inside_col else pd.Series(dtype=float)
    coverage = float(inside.dropna().tail(100).mean() * 100.0) if inside.notna().any() else None
    errors = pd.to_numeric(work[error_col], errors="coerce").dropna() if error_col else pd.Series(dtype=float)
    last_actual = str(work[actual_col].dropna().iloc[-1]) if actual_col and work[actual_col].notna().any() else "UNSETTLED"
    return {
        "samples": int(len(probs)),
        "calibrated_confidence": round(_clip(calibrated), 4),
        "expected_calibration_error": round(ece, 6) if ece is not None else None,
        "brier_score": round(brier, 8) if brier is not None else None,
        "rolling_coverage": round(coverage, 4) if coverage is not None else None,
        "absolute_close_error": round(float(errors.iloc[-1]), 8) if len(errors) else None,
        "actual_direction": last_actual,
        "actual_inside_interval": bool(inside.dropna().iloc[-1]) if inside.notna().any() else None,
        "coverage_history": inside.dropna().tail(40).astype(float).tolist(),
        "error_history": errors.tail(200).astype(float).tolist(),
    }


def _regime_history(priority_table: pd.DataFrame, completed: pd.DataFrame) -> pd.DataFrame:
    candidates = [priority_table, completed]
    for source in candidates:
        if not isinstance(source, pd.DataFrame) or source.empty:
            continue
        time_col = _find_col(source, ("time", "timestamp", "datetime", "date", "hour"))
        regime_col = _find_col(source, ("major_regime", "regime", "current_regime", "market_regime"))
        if not time_col or not regime_col:
            continue
        frame = source[[time_col, regime_col]].copy()
        frame[time_col] = pd.to_datetime(frame[time_col], errors="coerce", utc=True)
        frame[regime_col] = frame[regime_col].astype(str).str.upper().str.strip()
        frame = frame.dropna(subset=[time_col]).loc[lambda x: x[regime_col].ne("")]
        frame = frame.sort_values(time_col).drop_duplicates(time_col, keep="last")
        return frame.rename(columns={time_col: "time", regime_col: "regime"}).reset_index(drop=True)
    return pd.DataFrame(columns=["time", "regime"])


def _transition_rows(regimes: pd.DataFrame, completed: pd.DataFrame) -> list[dict[str, Any]]:
    if regimes.empty or completed.empty:
        return []
    price = completed[["__time", "__close"]].copy()
    merged = pd.merge_asof(regimes.sort_values("time"), price.sort_values("__time"), left_on="time", right_on="__time", direction="nearest", tolerance=pd.Timedelta("90min"))
    rows: list[dict[str, Any]] = []
    previous = None
    for idx, row in merged.iterrows():
        current = str(row.get("regime") or "UNKNOWN")
        if previous is not None and current != previous:
            start = int(idx)
            entry = _num(row.get("__close"), np.nan)
            future = merged.iloc[start : start + 7]
            prices = pd.to_numeric(future.get("__close"), errors="coerce").dropna().tolist()
            def at(hours: int) -> float | None:
                position = min(hours, len(prices) - 1)
                return float(prices[position]) if prices and position >= 0 else None
            direction = "BUY" if "BULL" in current else "SELL" if "BEAR" in current else "WAIT"
            after = prices[1:7] if len(prices) > 1 else []
            deltas = [value - entry for value in after] if isfinite(entry) else []
            signed = deltas if direction == "BUY" else [-x for x in deltas] if direction == "SELL" else deltas
            rows.append({
                "transition_time": row.get("time"), "previous_regime": previous,
                "new_regime": current, "entry_reference_price": entry if isfinite(entry) else None,
                "actual_close_1h": at(1), "actual_close_2h": at(2), "actual_close_3h": at(3), "actual_close_6h": at(6),
                "direction_correct_1h": (at(1) > entry if direction == "BUY" else at(1) < entry if direction == "SELL" else None) if at(1) is not None and isfinite(entry) else None,
                "direction_correct_3h": (at(3) > entry if direction == "BUY" else at(3) < entry if direction == "SELL" else None) if at(3) is not None and isfinite(entry) else None,
                "direction_correct_6h": (at(6) > entry if direction == "BUY" else at(6) < entry if direction == "SELL" else None) if at(6) is not None and isfinite(entry) else None,
                "maximum_favorable_excursion": max(signed) if signed else None,
                "maximum_adverse_excursion": min(signed) if signed else None,
                "regime_still_active_6h": bool(len(future) > 6 and str(future.iloc[6].get("regime")) == current),
            })
        previous = current
    return rows


def _candidate_next(regimes: pd.DataFrame, current: str, canonical: Mapping[str, Any]) -> tuple[str, int]:
    counts: Counter[str] = Counter()
    if not regimes.empty:
        sequence = regimes["regime"].astype(str).tolist()
        compact = [value for i, value in enumerate(sequence) if i == 0 or value != sequence[i - 1]]
        for left, right in zip(compact[:-1], compact[1:]):
            if left == current:
                counts[right] += 1
    if counts:
        candidate, count = counts.most_common(1)[0]
        return candidate, int(count)
    regime = _mapping(canonical.get("regime"))
    explicit = regime.get("candidate_next_regime") or regime.get("next_regime")
    if explicit:
        return str(explicit).upper(), 0
    final = _mapping(canonical.get("final_decision"))
    direction = str(final.get("directional_market_view") or final.get("less_risky_decision") or "WAIT").upper()
    environment = "NORMAL"
    if "COMPRESSION" in current:
        environment = "EXPANSION"
    elif "EXPANSION" in current:
        environment = "NORMAL"
    if direction == "BUY":
        return f"BULL_{environment}", 0
    if direction == "SELL":
        return f"BEAR_{environment}", 0
    return "RANGE_NORMAL", 0


def _plain_reason(status: str, drift_type: str, conflict: str, trust: float) -> str:
    parts = [f"Transition evidence is {status.lower()}."]
    if drift_type != "NONE":
        parts.append(f"The strongest warning is {drift_type.replace('_', ' ').lower()}.")
    if conflict not in {"NONE", "NO CONFLICT", "ALIGNED", ""}:
        parts.append("The existing regime and prediction are not fully aligned.")
    parts.append(f"Calibrated regime trust is {trust:.1f}/100; the original regime remains authoritative.")
    return " ".join(parts)


def build_regime_transition_trust(
    canonical: Mapping[str, Any], *, completed_h1: pd.DataFrame,
    priority_table: pd.DataFrame | None = None, settled_predictions: pd.DataFrame | None = None,
    calibrated_bundle: Mapping[str, Any] | None = None, previous: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Build additive evidence and normalized history rows for one canonical run."""
    output = deepcopy(dict(canonical))
    completed = _completed_frame(completed_h1)
    priority = priority_table if isinstance(priority_table, pd.DataFrame) else pd.DataFrame()
    settled = settled_predictions if isinstance(settled_predictions, pd.DataFrame) else pd.DataFrame()
    previous = _mapping(previous)
    regime = _mapping(output.get("regime"))
    final = _mapping(output.get("final_decision"))
    reliability = _mapping(output.get("reliability"))
    forecasts = _mapping(output.get("forecasts"))
    selected = _mapping(forecasts.get("selected"))
    market = _mapping(output.get("market"))

    returns = completed["__close"].pct_change().replace([np.inf, -np.inf], np.nan).dropna() if not completed.empty else pd.Series(dtype=float)
    volatility = returns.rolling(24, min_periods=8).std().dropna()
    return_scale = float(returns.tail(240).std()) if len(returns) else 0.0
    if not isfinite(return_scale) or return_scale <= 1e-12:
        return_scale = 1e-9
    normalized_returns = (returns / return_scale).clip(-8, 8)
    bocpd = bayesian_online_changepoint(normalized_returns.tail(240).tolist())
    adwin = adaptive_window_detection(normalized_returns.tail(512).tolist())

    current_regime = str(regime.get("major_regime") or regime.get("current") or regime.get("current_regime") or "UNKNOWN").upper()
    history = _regime_history(priority, completed)
    transitions = _transition_rows(history, completed)
    previous_regime = str(regime.get("previous_regime") or "").upper()
    transition_time = regime.get("last_change_time") or regime.get("transition_time") or output.get("latest_completed_candle_time")
    if transitions:
        latest_transition = transitions[-1]
        if not previous_regime:
            previous_regime = str(latest_transition.get("previous_regime") or "UNKNOWN")
        if current_regime == "UNKNOWN":
            current_regime = str(latest_transition.get("new_regime") or "UNKNOWN")
        transition_time = latest_transition.get("transition_time") or transition_time
    if not previous_regime:
        previous_regime = str(_mapping(previous.get("regime")).get("major_regime") or current_regime)
    candidate_next, recurring_count = _candidate_next(history, current_regime, output)

    model_rows = _forecast_models(output)
    model_points = np.asarray([row[1] for row in model_rows], dtype=float)
    last_close = float(completed["__close"].iloc[-1]) if not completed.empty else _num(market.get("last_close"), 0.0)
    forecast_spread = float(np.std(model_points) / max(abs(last_close), 1e-9) * 100.0) if len(model_points) > 1 else 0.0
    forecast_disagreement = _clip(forecast_spread * 400.0)

    vol_recent = float(volatility.tail(24).mean()) if len(volatility) else 0.0
    vol_prior = float(volatility.iloc[-72:-24].mean()) if len(volatility) >= 72 else float(volatility.head(max(len(volatility) - 24, 1)).mean() if len(volatility) > 24 else vol_recent)
    volatility_shift = abs(vol_recent - vol_prior) / max(abs(vol_prior), 1e-9) * 100.0 if vol_prior else 0.0
    volatility_drift_score = _clip(volatility_shift)

    raw_confidence = _clip(
        selected.get("confidence_pct", selected.get("confidence", reliability.get("score", 50.0)))
    )
    calibration = _settled_calibration(settled, raw_confidence)
    error_values = calibration.get("error_history") or []
    error_adwin = adaptive_window_detection(error_values, max_window=300) if error_values else {"changed": False, "score": 0.0, "window_size": 0}
    error_drift_score = _clip(error_adwin.get("score", 0.0))
    ece = calibration.get("expected_calibration_error")
    calibration_deterioration = _clip((ece or 0.0) * 2.0)

    conflict = str(
        output.get("conflict_status") or regime.get("prediction_conflict") or
        _mapping(output.get("conflict")).get("status") or "NONE"
    ).upper()
    conflict_score = 100.0 if conflict not in {"NONE", "NO CONFLICT", "ALIGNED", "OK", ""} else 0.0
    change_probability = _clip(
        0.45 * _num(bocpd.get("probability"))
        + 0.20 * (100.0 if adwin.get("changed") else _num(adwin.get("score")))
        + 0.15 * volatility_drift_score
        + 0.10 * forecast_disagreement
        + 0.10 * error_drift_score
    )
    observed_change = previous_regime != current_regime and current_regime != "UNKNOWN"
    if observed_change and change_probability >= 55:
        transition_status = "CONFIRMED"
    elif change_probability >= 45 or adwin.get("changed"):
        transition_status = "WATCH"
    else:
        transition_status = "STABLE"

    recent = normalized_returns.tail(72)
    gradual_score = 0.0
    incremental_score = 0.0
    if len(recent) >= 24:
        thirds = np.array_split(recent.to_numpy(), 3)
        means = [float(np.mean(x)) for x in thirds if len(x)]
        if len(means) == 3:
            gradual_score = _clip((max(means) - min(means)) / max(float(np.std(recent)), 1e-9) * 35.0)
            monotonic = (means[0] <= means[1] <= means[2]) or (means[0] >= means[1] >= means[2])
            incremental_score = gradual_score if monotonic else 0.0
    feature_drift_score = _clip(max(_num(adwin.get("score")), forecast_disagreement * 0.7))

    if error_drift_score >= 65:
        drift_type = "PREDICTION_ERROR_DRIFT"
    elif volatility_drift_score >= 65 and feature_drift_score < 45 and error_drift_score < 45:
        drift_type = "VOLATILITY_ONLY"
    elif observed_change and change_probability >= 75 and _num(bocpd.get("probability")) >= 55:
        drift_type = "SUDDEN"
    elif recurring_count >= 2 and observed_change:
        drift_type = "RECURRING"
    elif incremental_score >= 50:
        drift_type = "INCREMENTAL"
    elif gradual_score >= 45 or (adwin.get("changed") and _num(bocpd.get("probability")) < 50):
        drift_type = "GRADUAL"
    elif feature_drift_score >= 55:
        drift_type = "FEATURE_DRIFT"
    else:
        drift_type = "NONE"
    if drift_type not in DRIFT_LABELS:
        drift_type = "NONE"

    existing_trust = _clip(regime.get("reliability", regime.get("regime_reliability", reliability.get("score", 50.0))))
    calibrated_trust = _clip(
        existing_trust
        - 0.18 * change_probability
        - 0.12 * forecast_disagreement
        - 0.12 * error_drift_score
        - 0.08 * calibration_deterioration
        - 0.05 * conflict_score
        + 8.0
    )
    safer_decision = str(final.get("less_risky_decision") or final.get("final_decision") or "WAIT").upper()
    if calibrated_trust < 45 or conflict_score or change_probability >= 70:
        safer_decision = "WAIT"

    target_coverage = _num(_mapping(calibrated_bundle).get("target_coverage"), 90.0)
    if target_coverage <= 1.0:
        target_coverage *= 100.0
    rolling_coverage = calibration.get("rolling_coverage")
    coverage_error = target_coverage - _num(rolling_coverage, target_coverage)
    coverage_history = list(calibration.get("coverage_history") or [])
    historical_errors = [target_coverage / 100.0 - float(x) for x in coverage_history]
    proportional = coverage_error / 100.0
    integral = float(np.sum(historical_errors[-20:]))
    derivative = historical_errors[-1] - historical_errors[-2] if len(historical_errors) >= 2 else 0.0

    point = _num(selected.get("point_forecast", selected.get("forecast", last_close)), last_close)
    lower = _num(selected.get("lower_bound", selected.get("lower", point)), point)
    upper = _num(selected.get("upper_bound", selected.get("upper", point)), point)
    residuals = np.asarray(calibration.get("error_history") or [], dtype=float)
    residuals = residuals[np.isfinite(residuals)]
    conformal_radius = float(np.quantile(residuals, min(max(target_coverage / 100.0, 0.5), 0.995))) if len(residuals) >= 10 else max(abs(upper - lower) / 2.0, abs(point) * 0.0007)
    base_half_width = max(abs(point - lower), abs(upper - point), conformal_radius, abs(point) * 0.0001)
    pid_signal = 0.35 * proportional + 0.05 * integral + 0.10 * derivative
    width_adjustment = max(-0.35, min(0.75, pid_signal))
    next_half_width = base_half_width * (1.0 + width_adjustment)
    adaptive_lower, adaptive_upper = point - next_half_width, point + next_half_width

    latest_time = completed["__time"].iloc[-1] if not completed.empty else pd.Timestamp.now(tz="UTC")
    transition_ts = pd.to_datetime(transition_time, errors="coerce", utc=True)
    if pd.isna(transition_ts):
        transition_ts = latest_time
    elapsed_hours = max((pd.Timestamp(latest_time) - pd.Timestamp(transition_ts)).total_seconds() / 3600.0, 0.0)
    now_utc = pd.Timestamp.now(tz="UTC")
    latest_utc = pd.Timestamp(latest_time)
    if latest_utc.tzinfo is None:
        latest_utc = latest_utc.tz_localize("UTC")
    freshness_hours = max((now_utc - latest_utc).total_seconds() / 3600.0, 0.0)
    fallback_use = bool(output.get("fallback_use") or _mapping(output.get("metadata")).get("fallback_use"))
    missing_sources: list[str] = []
    if completed.empty:
        missing_sources.append("completed_h1")
    if not model_rows:
        missing_sources.append("model_forecasts")
    if settled.empty:
        missing_sources.append("settled_predictions")

    matching = [row for row in transitions if str(row.get("previous_regime")) == previous_regime and str(row.get("new_regime")) == current_regime]
    # Reuse published Similar-Day scores when a transition date is present there.
    # This is a ranking aid only and does not alter the existing Similar-Day engine.
    similar_payload = _mapping(output.get("similar_day_intelligence"))
    similar_rows = list(similar_payload.get("history_25") or []) + list(similar_payload.get("top_five") or [])
    similar_by_date: dict[str, float] = {}
    for item in similar_rows:
        if not isinstance(item, Mapping):
            continue
        date_value = item.get("Historical Date") or item.get("date") or item.get("timestamp")
        parsed_date = pd.to_datetime(date_value, errors="coerce", utc=True)
        if pd.isna(parsed_date):
            continue
        score = _num(item.get("Similarity Index", item.get("similarity_score")), 0.0)
        similar_by_date[pd.Timestamp(parsed_date).date().isoformat()] = max(score, similar_by_date.get(pd.Timestamp(parsed_date).date().isoformat(), 0.0))
    top_matches: list[dict[str, Any]] = []
    for row in matching[-50:]:
        entry = _num(row.get("entry_reference_price"), 0.0)
        movements = {}
        for horizon in (1, 2, 3, 6):
            close = row.get(f"actual_close_{horizon}h")
            movements[f"movement_{horizon}h"] = ((_num(close) - entry) / max(abs(entry), 1e-9) * 100.0) if close is not None and entry else None
        transition_date = pd.to_datetime(row.get("transition_time"), errors="coerce", utc=True)
        date_key = pd.Timestamp(transition_date).date().isoformat() if pd.notna(transition_date) else ""
        similarity = similar_by_date.get(date_key)
        if similarity is None:
            # Recency is a transparent fallback when no Similar-Day score exists.
            age_days = max((pd.Timestamp(latest_time) - pd.Timestamp(transition_date)).total_seconds() / 86400.0, 0.0) if pd.notna(transition_date) else 999.0
            similarity = max(0.0, 55.0 - min(age_days, 55.0))
        top_matches.append({
            "transition_time": row.get("transition_time"),
            "previous_regime": row.get("previous_regime"),
            "new_regime": row.get("new_regime"),
            "similarity_score": round(similarity, 3),
            **movements,
            "maximum_favorable_excursion": row.get("maximum_favorable_excursion"),
            "maximum_adverse_excursion": row.get("maximum_adverse_excursion"),
        })
    top_matches = sorted(top_matches, key=lambda row: (_num(row.get("similarity_score")), str(row.get("transition_time"))), reverse=True)[:5]

    reason = _plain_reason(transition_status, drift_type, conflict, calibrated_trust)
    run_id = str(output.get("run_id") or output.get("canonical_calculation_id") or "")
    generation = numeric_generation(output.get("calculation_generation") or output.get("generation_id"), default=1)
    timestamp = pd.Timestamp.now(tz="UTC")
    identity = {
        "canonical_run_id": run_id,
        "calculation_generation": generation,
        "source_data_timestamp": str(latest_time),
        "data_freshness": "CURRENT" if freshness_hours <= 2 else "STALE" if freshness_hours > 6 else "AGING",
        "data_freshness_hours": round(freshness_hours, 3),
        "data_fingerprint": _frame_fingerprint(completed_h1),
        "result_schema_version": str(output.get("shared_result_schema_version") or output.get("schema_version") or SCHEMA_VERSION),
        "missing_source_warnings": missing_sources,
        "fallback_use": fallback_use,
        "last_successful_calculation": str(output.get("calculation_completed_at") or output.get("created_at") or timestamp),
        "all_visible_components_same_canonical_result": True,
    }
    result = {
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "mode": "EVIDENCE_ONLY",
        "protected_regime_unchanged": True,
        "protected_decision_unchanged": True,
        "transition_summary": {
            "previous_regime": previous_regime,
            "current_regime": current_regime,
            "candidate_next_regime": candidate_next,
            "regime_change_probability": round(change_probability, 4),
            "transition_status": transition_status,
            "drift_type": drift_type,
            "hours_since_last_confirmed_transition": round(elapsed_hours, 3),
            "days_since_last_confirmed_transition": round(elapsed_hours / 24.0, 3),
            "calibrated_regime_trust": round(calibrated_trust, 4),
            "safer_decision": safer_decision,
            "reason": reason,
        },
        "change_evidence": {
            "bayesian_online_changepoint_probability": bocpd.get("probability"),
            "most_likely_run_length": bocpd.get("most_likely_run_length"),
            "run_length_uncertainty": bocpd.get("run_length_uncertainty"),
            "adwin_change_status": adwin.get("status"),
            "effective_adaptive_window_size": adwin.get("window_size"),
            "volatility_shift": round(volatility_shift, 4),
            "forecast_disagreement": round(forecast_disagreement, 4),
            "prediction_error_drift": round(error_drift_score, 4),
            "calibration_deterioration": round(calibration_deterioration, 4),
            "regime_prediction_conflict": conflict,
            "feature_drift_score": round(feature_drift_score, 4),
        },
        "historical_transition_matches": {
            "sample_size": len(matching),
            "warning": "Historical transition sample is small; treat the match statistics as descriptive only." if len(matching) < 5 else "",
            "top_five": top_matches,
        },
        "prediction_calibration": {
            "raw_confidence": round(raw_confidence, 4),
            "calibrated_confidence": calibration.get("calibrated_confidence"),
            "expected_calibration_error": calibration.get("expected_calibration_error"),
            "brier_score": calibration.get("brier_score"),
            "rolling_interval_coverage": rolling_coverage,
            "target_coverage": round(target_coverage, 4),
            "coverage_error": round(coverage_error, 4),
            "adaptive_lower_prediction_band": round(adaptive_lower, 8),
            "adaptive_upper_prediction_band": round(adaptive_upper, 8),
            "pid_proportional_error": round(proportional, 8),
            "pid_integral_error": round(integral, 8),
            "pid_derivative_error": round(derivative, 8),
            "next_interval_width_adjustment": round(width_adjustment * 100.0, 4),
            "settled_sample_count": calibration.get("samples"),
        },
        "system_trust_audit": identity,
    }
    output["regime_transition_trust_center"] = result
    output.setdefault("metadata", {})["regime_transition_trust_version"] = VERSION
    output["metadata"]["regime_transition_trust_mode"] = "EVIDENCE_ONLY"

    base = {"timestamp": timestamp, "run_id": run_id, "calculation_generation": generation}
    transition_history = [{
        **base, "transition_time": transition_ts, "previous_regime": previous_regime,
        "new_regime": current_regime, "change_probability": change_probability,
        "drift_type": drift_type, "run_length_before": bocpd.get("most_likely_run_length"),
        "confirmation_delay_bars": max(0, int(round(elapsed_hours))),
        "volatility_before": vol_prior, "volatility_after": vol_recent,
        "forecast_disagreement": forecast_disagreement,
        "calibrated_regime_trust": calibrated_trust, "trigger_summary": reason,
    }]
    outcome_history = []
    for row in transitions[-100:]:
        outcome_history.append({
            **base, "transition_time": row.get("transition_time"), "new_regime": row.get("new_regime"),
            "entry_reference_price": row.get("entry_reference_price"),
            "actual_close_1h": row.get("actual_close_1h"), "actual_close_2h": row.get("actual_close_2h"),
            "actual_close_3h": row.get("actual_close_3h"), "actual_close_6h": row.get("actual_close_6h"),
            "direction_correct_1h": row.get("direction_correct_1h"),
            "direction_correct_3h": row.get("direction_correct_3h"),
            "direction_correct_6h": row.get("direction_correct_6h"),
            "maximum_favorable_excursion": row.get("maximum_favorable_excursion"),
            "maximum_adverse_excursion": row.get("maximum_adverse_excursion"),
            "regime_still_active_6h": row.get("regime_still_active_6h"),
        })
    calibration_history = [{
        **base, "raw_confidence": raw_confidence,
        "calibrated_confidence": calibration.get("calibrated_confidence"),
        "predicted_direction": str(selected.get("direction") or final.get("directional_market_view") or safer_decision),
        "actual_direction": calibration.get("actual_direction"),
        "absolute_close_error": calibration.get("absolute_close_error"),
        "interval_lower": adaptive_lower, "interval_upper": adaptive_upper,
        "actual_inside_interval": calibration.get("actual_inside_interval"),
        "rolling_coverage": rolling_coverage,
        "expected_calibration_error": calibration.get("expected_calibration_error"),
        "brier_score": calibration.get("brier_score"),
    }]
    drift_history = [{
        **base, "bocpd_probability": bocpd.get("probability"),
        "adwin_detection_status": adwin.get("status"),
        "adaptive_window_size": adwin.get("window_size"), "drift_type": drift_type,
        "forecast_spread": forecast_spread, "error_drift_score": error_drift_score,
        "volatility_drift_score": volatility_drift_score,
        "action_taken": "Evidence recorded; protected regime unchanged" if safer_decision != "WAIT" else "Evidence recorded; safer decision constrained to WAIT",
    }]
    audit_history = [{
        **base, "master_decision": str(final.get("final_decision") or "WAIT"),
        "less_risky_decision": safer_decision,
        "priority_rank": str(output.get("priority_rank") or _mapping(output.get("priority")).get("rank") or "-"),
        "regime": current_regime, "regime_trust": calibrated_trust,
        "forecast_reliability": _clip(reliability.get("score", raw_confidence)),
        "conflict_status": conflict, "data_freshness": identity["data_freshness"],
        "fallback_use": fallback_use, "reason_summary": reason,
    }]
    bundle = {
        "regime_transition_history": transition_history,
        "post_transition_outcome_history": outcome_history,
        "prediction_calibration_history": calibration_history,
        "drift_detector_history": drift_history,
        "decision_audit_history": audit_history,
    }
    return output, result, bundle


__all__ = [
    "VERSION", "SCHEMA_VERSION", "DRIFT_LABELS", "bayesian_online_changepoint",
    "adaptive_window_detection", "build_regime_transition_trust",
]
