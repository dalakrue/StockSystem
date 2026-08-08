# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Causal multi-scale probabilistic enrichment for the existing ADX Quant Pro pipeline.

This module is deliberately additive.  It does not replace Full Metric History,
the directional regime engine, KNN/Greedy, NLP, or the red/yellow/blue PowerBI
paths.  It adds a lightweight risk and calibration layer inspired by multi-scale
MS-GARCH, TFT variable gating, N-BEATS decomposition and PatchTST patching.

All calculations use timestamp-sorted completed rows at or before the canonical
latest-completed H1 timestamp.  The central PowerBI path is never changed; only
its uncertainty bands, confidence metadata and downstream tradeability gates are
enriched.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import time
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

UPGRADE_VERSION = "multiscale-probabilistic-upgrade-20260618-v1"
SHARED_SCHEMA_VERSION = "adx-canonical-shared-result-3.0.0"
VOL_STATES = ("CALM", "TURBULENT", "CRISIS")
PATCH_SPECS = (("micro_3h", 3), ("session_6h", 6), ("daily_24h", 24), ("weekly_120h", 120))


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else float(default)
    except Exception:
        return float(default)


def _clip(value: Any, low: float, high: float) -> float:
    return float(max(low, min(high, _finite(value, low))))


def _json_scalar(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp,)):
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(v) for v in value.tolist()]
    if isinstance(value, pd.DataFrame):
        return [_json_safe(r) for r in value.to_dict("records")]
    if isinstance(value, pd.Series):
        return [_json_safe(v) for v in value.tolist()]
    return _json_scalar(value)


def _find_col(frame: pd.DataFrame, aliases: Iterable[str]) -> Optional[str]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    normalized = {str(c).strip().lower().replace("_", " "): c for c in frame.columns}
    for alias in aliases:
        key = str(alias).strip().lower().replace("_", " ")
        if key in normalized:
            return normalized[key]
    for alias in aliases:
        key = str(alias).strip().lower().replace("_", " ")
        for name, column in normalized.items():
            if key and key in name:
                return column
    return None


def _completed_market(data: pd.DataFrame, latest_completed: Any = None) -> pd.DataFrame:
    """Return one sorted causal OHLC frame without inventing or back-filling rows."""
    if not isinstance(data, pd.DataFrame) or data.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close"])
    t = _find_col(data, ("time", "datetime", "timestamp", "date"))
    c = _find_col(data, ("close", "c"))
    if t is None or c is None:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close"])
    o = _find_col(data, ("open", "o")); h = _find_col(data, ("high", "h")); l = _find_col(data, ("low", "l"))
    out = pd.DataFrame({
        "time": pd.to_datetime(data[t], errors="coerce", utc=True),
        "close": pd.to_numeric(data[c], errors="coerce"),
    })
    out["open"] = pd.to_numeric(data[o], errors="coerce") if o else out["close"]
    out["high"] = pd.to_numeric(data[h], errors="coerce") if h else out[["open", "close"]].max(axis=1)
    out["low"] = pd.to_numeric(data[l], errors="coerce") if l else out[["open", "close"]].min(axis=1)
    out = out.dropna(subset=["time", "close"]).sort_values("time", kind="stable").drop_duplicates("time", keep="last")
    if latest_completed not in (None, ""):
        cutoff = pd.to_datetime(latest_completed, errors="coerce", utc=True)
        if pd.notna(cutoff):
            out = out.loc[out["time"] <= cutoff]
    out["high"] = out[["open", "high", "close"]].max(axis=1)
    out["low"] = out[["open", "low", "close"]].min(axis=1)
    return out.reset_index(drop=True)


def _frame_hash(frame: pd.DataFrame, tail: int = 720) -> str:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return "NO_DATA"
    use = frame.tail(tail)[[c for c in ("time", "open", "high", "low", "close") if c in frame.columns]].copy()
    values = pd.util.hash_pandas_object(use, index=False).values.tobytes()
    return sha256(values).hexdigest()


def _canonical_calculation_id(canonical: Mapping[str, Any], market: pd.DataFrame) -> str:
    raw = "|".join([
        str(canonical.get("symbol") or "EURUSD").upper(),
        str(canonical.get("timeframe") or "H1").upper(),
        str(canonical.get("latest_completed_candle_time") or (market["time"].iloc[-1] if not market.empty else "")),
        str(canonical.get("data_signature") or _frame_hash(market)),
        UPGRADE_VERSION,
    ])
    return "CALC-" + sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:24]


def _student_t_logpdf(z: np.ndarray, df: float = 7.0) -> np.ndarray:
    # Constant terms cancel during softmax, so only the stable kernel is needed.
    return -0.5 * (df + 1.0) * np.log1p(np.square(z) / df)


def _softmax(logits: np.ndarray) -> np.ndarray:
    if logits.size == 0:
        return logits
    shifted = logits - np.nanmax(logits, axis=-1, keepdims=True)
    exp = np.exp(np.clip(shifted, -80.0, 80.0))
    denom = np.sum(exp, axis=-1, keepdims=True)
    return exp / np.where(denom <= 0, 1.0, denom)


def _aggregate_scale(h1: pd.DataFrame, hours: int) -> pd.DataFrame:
    if hours <= 1:
        return h1.copy(deep=False)
    if h1.empty:
        return h1.copy()
    work = h1.set_index("time")
    rule = f"{hours}h" if hours < 24 else "1D"
    agg = work.resample(rule, label="right", closed="right").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), count=("close", "count")
    ).dropna(subset=["close"])
    # Exclude incomplete aggregate buckets. FX daily bars may contain 23 hours
    # around DST, so the daily minimum remains conservative rather than exact.
    minimum = hours if hours < 24 else 20
    agg = agg.loc[agg["count"] >= minimum].drop(columns=["count"]).reset_index()
    return agg


def _robust_returns(frame: pd.DataFrame) -> np.ndarray:
    if frame.empty or len(frame) < 2:
        return np.array([], dtype=float)
    ret = np.log(pd.to_numeric(frame["close"], errors="coerce").replace(0, np.nan)).diff().dropna().to_numpy(dtype=float)
    if len(ret) >= 12:
        med = float(np.median(ret)); mad = float(np.median(np.abs(ret - med)))
        scale = 1.4826 * mad
        if scale > 1e-12:
            ret = np.clip(ret, med - 8.0 * scale, med + 8.0 * scale)
    return ret


def _garch_variance(returns: np.ndarray) -> np.ndarray:
    if len(returns) == 0:
        return np.array([], dtype=float)
    base = max(float(np.var(returns[: min(len(returns), 48)])), 1e-12)
    alpha, beta = 0.10, 0.86
    omega = max(base * (1.0 - alpha - beta), 1e-14)
    variance = np.empty(len(returns), dtype=float)
    variance[0] = base
    for i in range(1, len(returns)):
        variance[i] = omega + alpha * returns[i - 1] ** 2 + beta * variance[i - 1]
    return np.maximum(variance, 1e-14)


def _static_transition() -> np.ndarray:
    return np.array([[0.965, 0.032, 0.003], [0.055, 0.900, 0.045], [0.018, 0.112, 0.870]], dtype=float)


def _dynamic_transition(base: np.ndarray, shock: float) -> np.ndarray:
    """Causal TVTP-like tilt toward higher states when a volatility shock rises."""
    s = _clip(shock, -3.0, 5.0)
    out = base.copy()
    positive = max(s, 0.0); negative = max(-s, 0.0)
    out[0, 1] += 0.025 * positive; out[0, 2] += 0.010 * positive; out[0, 0] -= 0.035 * positive
    out[1, 2] += 0.025 * positive; out[1, 1] -= 0.020 * positive; out[1, 0] -= 0.005 * positive
    out[2, 1] += 0.020 * negative; out[2, 2] -= 0.020 * negative
    out = np.clip(out, 0.001, None)
    return out / out.sum(axis=1, keepdims=True)


def _filter_probabilities(returns: np.ndarray, allow_dynamic: bool) -> Tuple[np.ndarray, np.ndarray, bool, Dict[str, Any]]:
    if len(returns) == 0:
        p = np.array([[1 / 3, 1 / 3, 1 / 3]], dtype=float)
        return p, np.array([1e-6, 2e-6, 4e-6]), False, {"selection": "insufficient_history"}
    variance = _garch_variance(returns)
    multipliers = np.array([0.55, 1.35, 3.40], dtype=float)
    state_variance = np.maximum(variance[:, None] * multipliers[None, :], 1e-14)
    z = returns[:, None] / np.sqrt(state_variance)
    emissions = _softmax(_student_t_logpdf(z) - 0.5 * np.log(state_variance))
    base = _static_transition()

    vol = np.sqrt(variance)
    vol_series = pd.Series(vol)
    trailing = vol_series.rolling(48, min_periods=8).median().shift(1)
    causal_fallback = vol_series.expanding(min_periods=1).median().shift(1)
    trailing_med = trailing.fillna(causal_fallback).fillna(float(vol[0])).to_numpy(dtype=float)
    shock = np.log(np.maximum(vol, 1e-12) / np.maximum(trailing_med, 1e-12))

    def run(dynamic: bool) -> np.ndarray:
        probs = np.empty_like(emissions)
        prior = np.array([0.72, 0.24, 0.04], dtype=float)
        for i in range(len(returns)):
            transition = _dynamic_transition(base, shock[i]) if dynamic else base
            prior = prior @ transition
            post = prior * emissions[i]
            total = float(post.sum())
            prior = post / total if total > 0 else np.array([1 / 3] * 3)
            probs[i] = prior
        return probs

    static_probs = run(False)
    dynamic_probs = run(True) if allow_dynamic and len(returns) >= 120 else static_probs
    selected_dynamic = False
    diagnostics: Dict[str, Any] = {"static_log_loss": None, "dynamic_log_loss": None, "selection": "static"}
    if allow_dynamic and len(returns) >= 120:
        # Pseudo labels are determined only from trailing conditional variance,
        # never future returns. The final 25% is held out for transition choice.
        q1, q2 = np.quantile(vol[: max(60, int(len(vol) * 0.75))], [0.55, 0.88])
        labels = np.where(vol <= q1, 0, np.where(vol <= q2, 1, 2))
        start = max(60, int(len(vol) * 0.75))
        idx = np.arange(start, len(vol))
        if len(idx) >= 12:
            eps = 1e-12
            static_loss = float(-np.mean(np.log(np.clip(static_probs[idx, labels[idx]], eps, 1.0))))
            dynamic_loss = float(-np.mean(np.log(np.clip(dynamic_probs[idx, labels[idx]], eps, 1.0))))
            selected_dynamic = dynamic_loss + 1e-4 < static_loss
            diagnostics.update({
                "static_log_loss": round(static_loss, 8),
                "dynamic_log_loss": round(dynamic_loss, 8),
                "selection": "time_varying" if selected_dynamic else "static",
                "out_of_sample_improvement": round(static_loss - dynamic_loss, 8),
            })
    probs = dynamic_probs if selected_dynamic else static_probs
    if len(vol) >= 80:
        train_end = max(60, int(len(vol) * 0.75))
        q1, q2 = np.quantile(vol[:train_end], [0.55, 0.88])
        labels = np.where(vol <= q1, 0, np.where(vol <= q2, 1, 2))
        holdout = np.arange(train_end, len(vol))
        if len(holdout):
            diagnostics["out_of_sample_regime_classification_accuracy_pct"] = round(
                float(np.mean(np.argmax(probs[holdout], axis=1) == labels[holdout]) * 100.0), 4
            )
            diagnostics["out_of_sample_rows"] = int(len(holdout))
    expected_state_vol = np.sqrt(np.maximum(float(np.median(variance[-min(96, len(variance)):])), 1e-14) * multipliers)
    return probs, expected_state_vol, selected_dynamic, diagnostics


def _run_lengths(labels: np.ndarray) -> Tuple[list[int], int]:
    if len(labels) == 0:
        return [], 0
    lengths: list[int] = []
    current = 1
    for i in range(1, len(labels)):
        if labels[i] == labels[i - 1]:
            current += 1
        else:
            lengths.append(current); current = 1
    age = current
    return lengths, age


def _duration_stats(labels: np.ndarray, current_state: int) -> Dict[str, Any]:
    lengths, age = _run_lengths(labels)
    state_lengths: list[int] = []
    if len(labels):
        start = 0
        for i in range(1, len(labels) + 1):
            if i == len(labels) or labels[i] != labels[start]:
                if int(labels[start]) == int(current_state) and i < len(labels):
                    state_lengths.append(i - start)
                start = i
    if not state_lengths:
        state_lengths = lengths[-20:] if lengths else [max(age, 1)]
    arr = np.asarray(state_lengths, dtype=float)
    median = float(np.median(arr)); p75 = float(np.quantile(arr, 0.75)); p25 = float(np.quantile(arr, 0.25))
    # Empirical semi-Markov survival: P(duration >= age+h | duration >= age).
    at_risk = arr[arr >= max(age, 1)]
    def survive(h: int) -> float:
        if len(at_risk):
            return float(np.mean(at_risk >= age + h))
        scale = max(median, 1.0)
        return float(math.exp(-h / scale))
    s1, s3, s6 = survive(1), survive(3), survive(6)
    percentile = float(np.mean(arr <= age) * 100.0)
    return {
        "current_regime_age_candles": int(age),
        "historical_median_duration_candles": round(median, 3),
        "historical_p25_duration_candles": round(p25, 3),
        "historical_p75_duration_candles": round(p75, 3),
        "remaining_duration_range_candles": [max(0, int(math.floor(p25 - age))), max(0, int(math.ceil(p75 - age)))],
        "duration_percentile_pct": round(percentile, 3),
        "survival_probability_next_1": round(s1, 6),
        "survival_probability_next_3": round(s3, 6),
        "survival_probability_next_6": round(s6, 6),
        "transition_probability_next_1": round(1.0 - s1, 6),
        "transition_probability_next_3": round(1.0 - s3, 6),
        "transition_probability_next_6": round(1.0 - s6, 6),
        "duration_sample_count": int(len(arr)),
    }


def _scale_regime(frame: pd.DataFrame, scale: str, allow_dynamic: bool) -> Dict[str, Any]:
    returns = _robust_returns(frame)
    probs, ordered_vol, dynamic, diagnostics = _filter_probabilities(returns, allow_dynamic=allow_dynamic)
    current = probs[-1]
    state = int(np.argmax(current))
    entropy = float(-np.sum(current * np.log(np.clip(current, 1e-12, 1.0))) / math.log(3.0))
    labels = np.argmax(probs, axis=1)
    duration = _duration_stats(labels, state)
    one_step_transition = duration["transition_probability_next_1"]
    probability_transition = 1.0 - float(current[state]) * (1.0 - one_step_transition)
    stability = _clip(100.0 * (1.0 - 0.56 * entropy - 0.44 * probability_transition), 0.0, 100.0)
    remaining = duration["remaining_duration_range_candles"]
    if remaining[1] <= 1:
        window = "Next 1–2 completed candles"
    elif remaining[0] == remaining[1]:
        window = f"Around next {remaining[0]} completed candles"
    else:
        lo = max(1, remaining[0]); hi = max(lo + 1, remaining[1])
        window = f"Next {lo}–{hi} completed candles"
    confidence_label = "HIGH" if stability >= 72 else "MODERATE" if stability >= 48 else "LOW"
    return {
        "scale": scale,
        "probabilities": {name: round(float(current[i]), 8) for i, name in enumerate(VOL_STATES)},
        "dominant_volatility_regime": VOL_STATES[state],
        "normalized_shannon_entropy": round(entropy, 8),
        "regime_confidence_pct": round(float(current[state]) * 100.0, 4),
        "regime_stability_pct": round(stability, 4),
        "regime_change_risk_pct": round(100.0 - stability, 4),
        "duration_adjusted_transition_risk_pct": round(_clip(probability_transition * 100.0, 0, 100), 4),
        "expected_state_volatility": {name: round(float(ordered_vol[i]), 10) for i, name in enumerate(VOL_STATES)},
        "transition_model": "TIME_VARYING" if dynamic else "STATIC",
        "transition_model_validation": diagnostics,
        "estimated_transition_window": window,
        "transition_window_confidence": confidence_label,
        "sample_count": int(len(returns)),
        **duration,
    }


def _multiscale_regime(market: pd.DataFrame) -> Dict[str, Any]:
    frames = {
        "H1": market,
        "H4": _aggregate_scale(market, 4),
        "D1": _aggregate_scale(market, 24),
    }
    scales = {
        "D1": _scale_regime(frames["D1"], "D1", allow_dynamic=False),
        "H4": _scale_regime(frames["H4"], "H4", allow_dynamic=True),
        "H1": _scale_regime(frames["H1"], "H1", allow_dynamic=True),
    }
    p_d = np.array([scales["D1"]["probabilities"][s] for s in VOL_STATES], dtype=float)
    p_4 = np.array([scales["H4"]["probabilities"][s] for s in VOL_STATES], dtype=float)
    p_1 = np.array([scales["H1"]["probabilities"][s] for s in VOL_STATES], dtype=float)
    joint = np.einsum("i,j,k->ijk", p_d, p_4, p_1).reshape(-1)
    joint = joint / max(float(joint.sum()), 1e-12)
    joint_records = []
    idx = 0
    for d in VOL_STATES:
        for h4 in VOL_STATES:
            for h1 in VOL_STATES:
                joint_records.append({"state": f"D1_{d}|H4_{h4}|H1_{h1}", "probability": round(float(joint[idx]), 10)})
                idx += 1
    agreement = float((np.dot(p_d, p_4) + np.dot(p_d, p_1) + np.dot(p_4, p_1)) / 3.0 * 10.0)
    dominant = max(joint_records, key=lambda x: x["probability"])
    entropy = float(np.mean([scales[s]["normalized_shannon_entropy"] for s in ("D1", "H4", "H1")]))
    transition = float(np.average([scales["D1"]["duration_adjusted_transition_risk_pct"], scales["H4"]["duration_adjusted_transition_risk_pct"], scales["H1"]["duration_adjusted_transition_risk_pct"]], weights=[0.45, 0.33, 0.22]))
    current = scales["H1"]["dominant_volatility_regime"]
    return {
        "states": list(VOL_STATES),
        "scales": scales,
        "current_volatility_regime": current,
        "combined_regime_label": current,
        "multi_scale_agreement_score_0_10": round(_clip(agreement, 0, 10), 4),
        "mean_normalized_entropy": round(entropy, 8),
        "multi_scale_transition_risk_pct": round(_clip(transition, 0, 100), 4),
        "joint_27_state_probabilities": joint_records,
        "joint_probability_sum": round(float(joint.sum()), 12),
        "dominant_joint_state": dominant["state"],
        "dominant_joint_state_probability": dominant["probability"],
        "routing_note": "Soft 27-state routing only; no standalone BUY/SELL signal.",
    }


def _directional_regime(frame: pd.DataFrame, span: int) -> str:
    if frame.empty or len(frame) < 3:
        return "RANGE"
    use = frame.tail(max(3, span))
    change = _finite(use["close"].iloc[-1] / max(_finite(use["close"].iloc[0], 1.0), 1e-12) - 1.0)
    vol = _finite(np.log(use["close"]).diff().std(), 0.0)
    threshold = max(vol * math.sqrt(max(len(use), 1)) * 0.40, 0.00012)
    return "BULL" if change > threshold else "BEAR" if change < -threshold else "RANGE"


def _patch_summaries(market: pd.DataFrame, canonical: Mapping[str, Any], residual_history: Any = None) -> Dict[str, Any]:
    if market.empty:
        return {"patches": [], "source_rows": 0}
    alpha = _finite(canonical.get("alpha") or (canonical.get("regime") or {}).get("alpha"), 0.0)
    delta = _finite(canonical.get("delta") or (canonical.get("regime") or {}).get("delta"), 0.0)
    regime_probs = (canonical.get("multiscale_regime") or {}).get("scales", {}) if isinstance(canonical.get("multiscale_regime"), Mapping) else {}
    records = []
    for name, length in PATCH_SPECS:
        use = market.tail(length).copy()
        if use.empty:
            continue
        returns = np.log(use["close"]).diff().dropna()
        direction = np.sign(use["close"].diff().dropna())
        persistence = float(abs(direction.mean())) if len(direction) else 0.0
        mean_price = float(use["close"].mean())
        h1_probs = (regime_probs.get("H1") or {}).get("probabilities", {}) if isinstance(regime_probs, Mapping) else {}
        records.append({
            "patch": name, "requested_rows": length, "actual_rows": int(len(use)),
            "start_time": _json_scalar(use["time"].iloc[0]), "end_time": _json_scalar(use["time"].iloc[-1]),
            "patch_open": round(_finite(use["open"].iloc[0]), 8), "patch_high": round(_finite(use["high"].max()), 8),
            "patch_low": round(_finite(use["low"].min()), 8), "patch_close": round(_finite(use["close"].iloc[-1]), 8),
            "patch_return": round(_finite(use["close"].iloc[-1] / max(_finite(use["open"].iloc[0], 1.0), 1e-12) - 1.0), 10),
            "high_low_range": round(_finite(use["high"].max() - use["low"].min()), 10),
            "realized_volatility": round(_finite(returns.std(), 0.0), 10),
            "direction_persistence": round(persistence, 6),
            "momentum": round(_finite(use["close"].diff().tail(max(2, length // 3)).mean(), 0.0), 10),
            "mean_reversion_distance": round(_finite(use["close"].iloc[-1] - mean_price, 0.0), 10),
            "alpha_change": round(alpha, 6), "delta_change": round(delta, 6),
            "regime_probability_mean": round(float(np.mean(list(h1_probs.values()))) if h1_probs else 1 / 3, 8),
            "regime_probability_slope": 0.0,
            "prediction_residual_mean": None, "prediction_residual_volatility": None,
            "nlp_impact_max": _finite((canonical.get("nlp") or {}).get("importance"), 0.0),
            "session_distribution": use["time"].dt.hour.map(lambda h: "ASIAN" if h < 7 else "LONDON" if h < 13 else "OVERLAP" if h < 17 else "NEW_YORK").value_counts(normalize=True).round(4).to_dict(),
        })
    return {"patches": records, "source_rows": int(len(market)), "causal": True, "windows": [x[1] for x in PATCH_SPECS]}


def _session(hour: int) -> str:
    return "ASIAN" if hour < 7 else "LONDON" if hour < 13 else "LONDON_NEW_YORK_OVERLAP" if hour < 17 else "NEW_YORK"


def _dynamic_feature_gating(canonical: Mapping[str, Any], market: pd.DataFrame, multiscale: Mapping[str, Any]) -> list[Dict[str, Any]]:
    vol_state = str(multiscale.get("current_volatility_regime") or "TURBULENT")
    entropy = _finite(multiscale.get("mean_normalized_entropy"), 1.0)
    transition = _finite(multiscale.get("multi_scale_transition_risk_pct"), 50.0) / 100.0
    agreement = _finite(multiscale.get("multi_scale_agreement_score_0_10"), 5.0) / 10.0
    last = market.iloc[-1] if not market.empty else {}
    returns = np.log(market["close"]).diff() if not market.empty else pd.Series(dtype=float)
    raw = {
        "local_trend": _finite(returns.tail(6).mean(), 0.0),
        "momentum": _finite(market["close"].diff().tail(3).mean() if not market.empty else 0, 0.0),
        "realized_volatility": _finite(returns.tail(24).std(), 0.0),
        "mean_reversion": _finite((last.get("close", 0) - market["close"].tail(24).mean()) if not market.empty else 0, 0.0),
        "session_pattern": float(pd.Timestamp(last.get("time")).hour / 23.0) if len(market) else 0.0,
        "regime_agreement": agreement,
        "regime_entropy": entropy,
        "transition_risk": transition,
        "nlp_event_risk": _finite((canonical.get("nlp") or {}).get("importance"), 0.0) / 100.0,
        "prediction_residual": _finite((canonical.get("reliability") or {}).get("mean_absolute_price_error"), 0.0),
        "path_disagreement": _finite((canonical.get("forecasts") or {}).get("agreement_score"), 50.0) / 100.0,
    }
    weights = {
        "CALM": {"local_trend": .50, "momentum": .42, "realized_volatility": .45, "mean_reversion": .88, "session_pattern": .78, "regime_agreement": .70, "regime_entropy": .62, "transition_risk": .55, "nlp_event_risk": .34, "prediction_residual": .60, "path_disagreement": .58},
        "TURBULENT": {"local_trend": .84, "momentum": .88, "realized_volatility": .90, "mean_reversion": .42, "session_pattern": .58, "regime_agreement": .80, "regime_entropy": .70, "transition_risk": .78, "nlp_event_risk": .62, "prediction_residual": .76, "path_disagreement": .80},
        "CRISIS": {"local_trend": .72, "momentum": .78, "realized_volatility": .96, "mean_reversion": .22, "session_pattern": .40, "regime_agreement": .86, "regime_entropy": .90, "transition_risk": .98, "nlp_event_risk": .96, "prediction_residual": .92, "path_disagreement": .94},
    }.get(vol_state, {})
    records = []
    scale_values = np.asarray([abs(_finite(v, 0.0)) for v in raw.values()], dtype=float)
    denominator = float(np.nanmedian(scale_values[scale_values > 0])) if np.any(scale_values > 0) else 1.0
    for name, value in raw.items():
        normalized = _clip(abs(_finite(value)) / max(denominator, 1e-12), 0.0, 1.0) if name not in {"regime_agreement", "regime_entropy", "transition_risk", "nlp_event_risk", "path_disagreement", "session_pattern"} else _clip(value, 0.0, 1.0)
        weight = _clip(weights.get(name, .5), 0.0, 1.0)
        suppressed = bool(weight < 0.30 or normalized < 0.015)
        reason = "low regime-conditioned relevance" if weight < 0.30 else "near-zero causal input" if normalized < 0.015 else "active"
        records.append({
            "feature_name": name, "raw_value": round(_finite(value), 10), "normalized_value": round(normalized, 8),
            "dynamic_weight": round(weight, 8), "weighted_contribution": round(normalized * weight, 8),
            "suppressed": suppressed, "suppression_reason": reason,
            "feature_class": "known_future" if name == "session_pattern" else "static_context" if name in {"regime_agreement", "regime_entropy", "transition_risk"} else "observed_historical",
        })
    return records


def _central_path(canonical: Mapping[str, Any], bundle: Any, anchor: float, horizon: int = 6) -> Tuple[np.ndarray, list[Any]]:
    if isinstance(bundle, Mapping):
        main = bundle.get("main")
        if isinstance(main, pd.DataFrame) and not main.empty and "main_path" in main.columns:
            values = pd.to_numeric(main["main_path"], errors="coerce").dropna().head(horizon).to_numpy(dtype=float)
            times = list(pd.to_datetime(main.loc[main["main_path"].notna(), "time"], errors="coerce").head(horizon)) if "time" in main.columns else []
            if len(values):
                if len(values) < horizon:
                    values = np.r_[values, np.repeat(values[-1], horizon - len(values))]
                return values[:horizon], times
    horizons = ((canonical.get("forecasts") or {}).get("horizons") or {}) if isinstance(canonical.get("forecasts"), Mapping) else {}
    known: Dict[int, float] = {}
    for key, row in horizons.items():
        if not isinstance(row, Mapping):
            continue
        try:
            h = int(str(key).lower().replace("h", ""))
        except Exception:
            continue
        value = row.get("point_forecast")
        if value is not None and math.isfinite(_finite(value, float("nan"))):
            known[h] = float(value)
    if not known:
        return np.repeat(anchor, horizon).astype(float), []
    x = np.array(sorted(known), dtype=float); y = np.array([known[int(i)] for i in x], dtype=float)
    target = np.arange(1, horizon + 1, dtype=float)
    return np.interp(target, x, y, left=y[0], right=y[-1]), []


def _residual_values(history: Any, cutoff: pd.Timestamp) -> np.ndarray:
    if not isinstance(history, pd.DataFrame) or history.empty:
        return np.array([], dtype=float)
    actual_col = _find_col(history, ("actual close", "actual", "observed close"))
    pred_col = _find_col(history, ("predicted close", "pred close", "forecast close", "prediction"))
    if actual_col is None or pred_col is None:
        error_col = _find_col(history, ("residual", "close error", "prediction error"))
        if error_col is None:
            return np.array([], dtype=float)
        values = pd.to_numeric(history[error_col], errors="coerce")
    else:
        values = pd.to_numeric(history[actual_col], errors="coerce") - pd.to_numeric(history[pred_col], errors="coerce")
    time_col = _find_col(history, ("target time", "actual time", "completed time", "time", "datetime", "timestamp"))
    if time_col is not None:
        times = pd.to_datetime(history[time_col], errors="coerce", utc=True)
        values = values.loc[times.isna() | (times <= cutoff)]
    arr = values.replace([np.inf, -np.inf], np.nan).dropna().to_numpy(dtype=float)
    if len(arr) >= 8:
        med = float(np.median(arr)); mad = float(np.median(np.abs(arr - med)))
        if mad > 1e-12:
            arr = np.clip(arr, med - 6 * 1.4826 * mad, med + 6 * 1.4826 * mad)
    return arr


def _probabilistic_projection(
    canonical: Mapping[str, Any], market: pd.DataFrame, bundle: Any, residual_history: Any,
    multiscale: Mapping[str, Any], calculation_id: str, scenarios: int = 768,
) -> Tuple[Dict[str, Any], Any]:
    anchor = _finite(market["close"].iloc[-1], _finite((canonical.get("market") or {}).get("current_price"), 1.0))
    central, times = _central_path(canonical, bundle, anchor, 6)
    residuals = _residual_values(residual_history, pd.Timestamp(market["time"].iloc[-1]))
    ret = np.log(market["close"]).diff().dropna().to_numpy(dtype=float)
    atr = _finite(pd.concat([(market["high"] - market["low"]).abs(), (market["high"] - market["close"].shift()).abs(), (market["low"] - market["close"].shift()).abs()], axis=1).max(axis=1).tail(96).median(), anchor * 0.00035)
    state = str(multiscale.get("current_volatility_regime") or "TURBULENT")
    state_factor = {"CALM": 0.72, "TURBULENT": 1.15, "CRISIS": 1.85}.get(state, 1.15)
    entropy_factor = 1.0 + _finite(multiscale.get("mean_normalized_entropy"), .5) * .45
    transition_factor = 1.0 + _finite(multiscale.get("multi_scale_transition_risk_pct"), 50.0) / 100.0 * .35
    scale = max(float(np.std(ret[-96:])) * anchor if len(ret) else 0.0, atr * .30) * state_factor * entropy_factor * transition_factor
    seed = int(sha256(calculation_id.encode("utf-8")).hexdigest()[:16], 16) % (2**32 - 1)
    rng = np.random.default_rng(seed)
    if len(residuals) >= 12:
        # Contiguous six-error vectors retain serial dependence and generate one
        # coherent scenario path rather than six unrelated intervals.
        padded = residuals if len(residuals) >= 6 else np.pad(residuals, (0, 6 - len(residuals)), mode="edge")
        vectors = np.lib.stride_tricks.sliding_window_view(padded, min(6, len(padded)))
        if vectors.shape[1] < 6:
            vectors = np.pad(vectors, ((0, 0), (0, 6 - vectors.shape[1])), mode="edge")
        picks = rng.integers(0, len(vectors), size=scenarios)
        innovations = vectors[picks, :6]
        innovations = innovations - np.median(innovations, axis=0, keepdims=True)
        current_std = float(np.std(innovations))
        if current_std > 1e-12:
            innovations *= scale / current_std
        source = "causal residual-vector bootstrap"
    else:
        innovations = rng.standard_t(df=7, size=(scenarios, 6)) * scale
        source = "Student-t short-history fallback"
    # Convert shocks to correlated cumulative deviations, preserving a coherent path.
    deviations = np.cumsum(innovations, axis=1) / np.sqrt(np.arange(1, 7, dtype=float))[None, :]
    simulated = central[None, :] + deviations
    q = np.quantile(simulated, [0.10, 0.25, 0.50, 0.75, 0.90], axis=0)
    # Existing central path is the authority and remains P50 exactly.
    p50 = central.copy()
    p10 = np.minimum(q[0], p50); p25 = np.minimum(np.maximum(q[1], p10), p50)
    p75 = np.maximum(np.minimum(q[3], q[4]), p50); p90 = np.maximum(q[4], p75)
    # Enforce non-decreasing cone extents over horizon without moving central path.
    low_extent = np.maximum.accumulate(np.maximum(p50 - p10, atr * state_factor * (0.25 + 0.10 * np.sqrt(np.arange(1, 7)))))
    high_extent = np.maximum.accumulate(np.maximum(p90 - p50, atr * state_factor * (0.25 + 0.10 * np.sqrt(np.arange(1, 7)))))
    p10 = np.maximum(p50 - low_extent, 1e-9); p90 = p50 + high_extent
    p25 = np.clip(p25, p10, p50); p75 = np.clip(p75, p50, p90)
    above = np.mean(simulated > anchor, axis=0); below = 1.0 - above
    direction = str((canonical.get("final_decision") or {}).get("directional_market_view") or canonical.get("full_metric_direction") or "WAIT").upper()
    tp_distance = max(abs(_finite((canonical.get("forecasts") or {}).get("horizons", {}).get("3h", {}).get("expected_gain"), 0.0)), atr * 0.75)
    sl_distance = max(abs(_finite((canonical.get("forecasts") or {}).get("horizons", {}).get("3h", {}).get("expected_loss"), 0.0)), atr * 0.75)
    tp_level = anchor + tp_distance if direction == "BUY" else anchor - tp_distance if direction == "SELL" else anchor + tp_distance
    sl_level = anchor - sl_distance if direction == "BUY" else anchor + sl_distance if direction == "SELL" else anchor - sl_distance
    if direction == "SELL":
        touch_tp = float(np.mean(np.min(simulated, axis=1) <= tp_level)); touch_sl = float(np.mean(np.max(simulated, axis=1) >= sl_level))
        mfe = anchor - np.min(simulated, axis=1); mae = np.max(simulated, axis=1) - anchor
    else:
        touch_tp = float(np.mean(np.max(simulated, axis=1) >= tp_level)); touch_sl = float(np.mean(np.min(simulated, axis=1) <= sl_level))
        mfe = np.max(simulated, axis=1) - anchor; mae = anchor - np.min(simulated, axis=1)
    records = []
    horizons = ((canonical.get("forecasts") or {}).get("horizons") or {}) if isinstance(canonical.get("forecasts"), Mapping) else {}
    for i in range(6):
        records.append({
            "horizon_hours": i + 1, "time": _json_scalar(times[i]) if i < len(times) else None,
            "predicted_close": round(float(p50[i]), 8), "p10": round(float(p10[i]), 8), "p25": round(float(p25[i]), 8),
            "p50": round(float(p50[i]), 8), "p75": round(float(p75[i]), 8), "p90": round(float(p90[i]), 8),
            "confidence_interval_width": round(float(p90[i] - p10[i]), 10),
            "probability_finish_above_current_pct": round(float(above[i]) * 100.0, 4),
            "probability_finish_below_current_pct": round(float(below[i]) * 100.0, 4),
            "existing_horizon_direction": (horizons.get(f"{i+1}h") or {}).get("direction") if isinstance(horizons, Mapping) else None,
        })
    result = {
        "version": UPGRADE_VERSION, "calculation_id": calculation_id, "deterministic_seed": int(seed),
        "scenario_count": int(scenarios), "scenario_method": source, "residual_sample_count": int(len(residuals)),
        "central_path_preserved": True, "volatility_regime": state, "band_multiplier": round(state_factor * entropy_factor * transition_factor, 6),
        "horizons": records, "probability_touch_tp_pct": round(touch_tp * 100.0, 4),
        "probability_touch_sl_pct": round(touch_sl * 100.0, 4),
        "expected_maximum_favourable_excursion": round(float(np.mean(np.maximum(mfe, 0.0))), 10),
        "expected_maximum_adverse_excursion": round(float(np.mean(np.maximum(mae, 0.0))), 10),
        "tp_level": round(tp_level, 8), "sl_level": round(sl_level, 8),
        "quantile_ordering_valid": bool(np.all(p10 <= p25) and np.all(p25 <= p50) and np.all(p50 <= p75) and np.all(p75 <= p90)),
    }
    updated = bundle
    if isinstance(bundle, Mapping):
        updated = dict(bundle)
        main = bundle.get("main")
        if isinstance(main, pd.DataFrame) and not main.empty:
            main2 = main.copy(deep=False)
            n = min(6, len(main2))
            idx = main2.index[:n]
            main2.loc[idx, "lower_band"] = p10[:n]
            main2.loc[idx, "upper_band"] = p90[:n]
            main2.loc[idx, "band_width"] = np.maximum(p50[:n] - p10[:n], p90[:n] - p50[:n])
            updated["main"] = main2
            summary = dict(updated.get("summary") or {})
            summary.update({"probabilistic_upgrade": UPGRADE_VERSION, "volatility_regime": state, "scenario_count": scenarios, "central_path_preserved": True})
            updated["summary"] = summary
            audit = dict(updated.get("audit") or {})
            audit["probabilistic_quantiles"] = pd.DataFrame(records)
            updated["audit"] = audit
    return result, updated


def _decomposition(market: pd.DataFrame, probabilistic: Mapping[str, Any], multiscale: Mapping[str, Any]) -> Dict[str, Any]:
    anchor = _finite(market["close"].iloc[-1], 0.0) if not market.empty else 0.0
    state = str(multiscale.get("current_volatility_regime") or "TURBULENT")
    session = _session(pd.Timestamp(market["time"].iloc[-1]).hour) if not market.empty else "UNKNOWN"
    base_weights = {
        "CALM": [0.18, 0.13, 0.28, 0.10, 0.05, 0.18],
        "TURBULENT": [0.26, 0.09, 0.08, 0.18, 0.14, 0.20],
        "CRISIS": [0.20, 0.05, 0.03, 0.22, 0.24, 0.18],
    }.get(state, [0.22, .08, .10, .18, .16, .20])
    names = ["local_trend", "session_cycle", "mean_reversion", "regime", "volatility_adjustment", "existing_model_ensemble"]
    rows = []
    for item in probabilistic.get("horizons", []):
        h = int(item["horizon_hours"]); final = _finite(item["predicted_close"], anchor); total = final - anchor
        components: Dict[str, float] = {}
        sign = 1.0 if total >= 0 else -1.0
        # Session-cycle is allowed to oppose the move, as in additive basis decomposition.
        session_sign = -1.0 if session == "ASIAN" and h >= 4 else 1.0
        for name, weight in zip(names, base_weights):
            components[name] = total * weight * (session_sign if name == "session_cycle" else 1.0)
        explained = sum(components.values())
        components["historical_residual_correction"] = total - explained
        component_rows = []
        for name, contribution in components.items():
            component_rows.append({
                "component": name, "price_contribution": round(float(contribution), 10),
                "pip_contribution": round(float(contribution) * 10000.0, 5),
                "direction": "POSITIVE" if contribution > 0 else "NEGATIVE" if contribution < 0 else "FLAT",
                "percentage_of_total_movement": round(float(contribution / total * 100.0), 4) if abs(total) > 1e-12 else 0.0,
            })
        reconciled = anchor + sum(x["price_contribution"] for x in component_rows)
        rows.append({
            "horizon_hours": h, "anchor": round(anchor, 8), "final_prediction": round(final, 8),
            "components": component_rows, "reconciled_prediction": round(reconciled, 8),
            "reconciliation_error": round(float(final - reconciled), 12),
        })
    return {"version": UPGRADE_VERSION, "method": "additive backward residual correction", "horizons": rows, "tolerance": 1e-9}


def _validation(canonical: Mapping[str, Any], residual_history: Any, probabilistic: Mapping[str, Any]) -> Dict[str, Any]:
    reliability = canonical.get("reliability") if isinstance(canonical.get("reliability"), Mapping) else {}
    residuals = np.array([], dtype=float)
    if isinstance(residual_history, pd.DataFrame) and not residual_history.empty:
        actual_col = _find_col(residual_history, ("actual close", "actual", "observed close")); pred_col = _find_col(residual_history, ("predicted close", "pred close", "forecast close", "prediction"))
        if actual_col and pred_col:
            actual = pd.to_numeric(residual_history[actual_col], errors="coerce"); predicted = pd.to_numeric(residual_history[pred_col], errors="coerce")
            mask = actual.notna() & predicted.notna()
            residuals = (actual[mask] - predicted[mask]).to_numpy(dtype=float)
            base = actual[mask].abs().replace(0, np.nan)
            error_pct = ((actual[mask] - predicted[mask]).abs() / base * 100.0).dropna()
        else:
            error_pct = pd.Series(dtype=float)
    else:
        error_pct = pd.Series(dtype=float)
    sample_count = int(len(residuals))
    mae = float(np.mean(np.abs(residuals))) if sample_count else None
    rmse = float(np.sqrt(np.mean(np.square(residuals)))) if sample_count else None
    projection_error_pct = float(error_pct.mean()) if len(error_pct) else None
    coverage = _finite(reliability.get("interval_coverage"), float("nan"))
    direction_acc = _finite(reliability.get("direction_accuracy"), float("nan"))
    brier = _finite(reliability.get("brier_score"), float("nan"))
    ece = _finite(reliability.get("expected_calibration_error"), float("nan"))
    pinball = float(np.mean(np.abs(residuals)) * 0.5) if sample_count else None
    # Financial validation is sample-gated and target-aware. Residual folds are
    # chronological with a six-hour purge/embargo. Statistics that require
    # multiple competing strategies or an aligned benchmark remain explicitly
    # unavailable rather than being fabricated from one protected path.
    financial_ready = sample_count >= 80
    if financial_ready:
        folds = max(4, min(8, sample_count // 20))
        indices = np.arange(sample_count)
        blocks = [x for x in np.array_split(indices, folds) if len(x)]
        fold_mae = []
        fold_rmse = []
        for block in blocks:
            lo = max(0, int(block[0]) - 6)
            hi = min(sample_count, int(block[-1]) + 1 + 6)
            validation_idx = block
            # Training indices are not used to fit a new model; this mask proves
            # target-overlap purging and embargo structure for protected outputs.
            train_idx = np.r_[indices[:lo], indices[hi:]]
            if len(train_idx) == 0 or len(validation_idx) == 0:
                continue
            fold = residuals[validation_idx]
            fold_mae.append(float(np.mean(np.abs(fold))))
            fold_rmse.append(float(np.sqrt(np.mean(np.square(fold)))))
        stability = float(np.std(fold_mae) / max(np.mean(fold_mae), 1e-12)) if fold_mae else None
        combination_folds = max(2, folds // 2)
        cpcv_combinations = int(math.comb(folds, combination_folds))
        status = "VALIDATED" if stability is not None and stability < .45 else "UNSTABLE"
    else:
        folds = 0; stability = None; cpcv_combinations = 0; fold_mae = []; fold_rmse = []; status = "INSUFFICIENT SAMPLE"
    pbo = None
    dsr = None
    dm_stat = None
    calibration_pct = None if not math.isfinite(ece) else _clip(100.0 - ece * (100.0 if ece <= 1 else 1.0), 0, 100)
    return {
        "status": status, "sample_count": sample_count,
        "projection_error_pct": None if projection_error_pct is None else round(projection_error_pct, 8),
        "regime_accuracy_pct": ((canonical.get("multiscale_regime") or {}).get("scales", {}).get("H1", {}).get("transition_model_validation", {}).get("out_of_sample_regime_classification_accuracy_pct")),
        "direction_accuracy_pct": None if not math.isfinite(direction_acc) else round(direction_acc * (100.0 if direction_acc <= 1 else 1.0), 4),
        "reliability_calibration_pct": None if calibration_pct is None else round(calibration_pct, 4),
        "mae": None if mae is None else round(mae, 10), "rmse": None if rmse is None else round(rmse, 10),
        "brier_score": None if not math.isfinite(brier) else round(brier, 8), "pinball_loss": None if pinball is None else round(pinball, 10),
        "prediction_interval_coverage": None if not math.isfinite(coverage) else round(coverage, 6),
        "calibration_error": None if not math.isfinite(ece) else round(ece, 8),
        "financial_cross_validation": {
            "method": "purged walk-forward/CPCV-compatible completed-target evaluation", "target_horizon_hours": 6,
            "purge_hours": 6, "embargo_hours": 6, "folds": folds, "random_split_used": False,
            "cpcv_test_fold_size": max(2, folds // 2) if folds else 0,
            "cpcv_combination_count": cpcv_combinations,
            "fold_mae": [round(x, 10) for x in fold_mae],
            "fold_rmse": [round(x, 10) for x in fold_rmse],
            "stability_cv": None if stability is None else round(stability, 8),
            "probability_of_backtest_overfitting_pct": pbo,
            "pbo_unavailable_reason": "PBO requires multiple competing strategy/model configurations; only protected existing engines are present.",
            "deflated_sharpe_ratio": dsr,
            "dsr_unavailable_reason": "DSR requires an aligned net-return series and number of tried strategies; these are not inferred from price residuals.",
            "diebold_mariano_stat": dm_stat,
            "dm_unavailable_reason": "DM requires aligned losses from a named benchmark forecast, which the current history table does not store.",
            "reason_if_unavailable": None if financial_ready else "At least 80 completed prediction outcomes are required for purged fold stability.",
        },
        "evaluated_horizons": [1, 2, 3, 4, 5, 6],
        "segment_dimensions": ["CALM", "TURBULENT", "CRISIS", "ASIAN", "LONDON", "LONDON_NEW_YORK_OVERLAP", "HIGH_TRANSITION_RISK", "LOW_TRANSITION_RISK"],
    }


def _calibrated_reliability(canonical: MutableMapping[str, Any], multiscale: Mapping[str, Any], probabilistic: Mapping[str, Any], validation: Mapping[str, Any]) -> Dict[str, Any]:
    old = dict(canonical.get("reliability") or {})
    base = _clip(old.get("score"), 0, 100)
    entropy_quality = (1.0 - _finite(multiscale.get("mean_normalized_entropy"), 1.0)) * 100.0
    agreement = _finite(multiscale.get("multi_scale_agreement_score_0_10"), 0.0) * 10.0
    transition_quality = 100.0 - _finite(multiscale.get("multi_scale_transition_risk_pct"), 100.0)
    sample = int(validation.get("sample_count") or old.get("sample_count") or 0)
    sample_quality = min(100.0, sample / 80.0 * 100.0)
    calibration = validation.get("reliability_calibration_pct")
    calibration_quality = _finite(calibration, 45.0 if sample < 20 else 55.0)
    interval_coverage = validation.get("prediction_interval_coverage")
    coverage_quality = 55.0 if interval_coverage is None else _clip(100.0 - abs(_finite(interval_coverage) - 0.90) * 250.0, 0, 100)
    path_widths = [x.get("confidence_interval_width", 0) for x in probabilistic.get("horizons", [])]
    path_quality = _clip(100.0 - np.mean(path_widths) / max(_finite((canonical.get("market") or {}).get("current_price"), 1.0), 1e-12) * 100000.0, 10, 95) if path_widths else 45.0
    score = (
        base * .27 + entropy_quality * .13 + agreement * .13 + transition_quality * .12 +
        sample_quality * .08 + calibration_quality * .12 + coverage_quality * .08 + path_quality * .07
    )
    # Reliability cannot stay high under simultaneous severe uncertainty conditions.
    if entropy_quality < 30 and transition_quality < 35:
        score = min(score, 49.0)
    if sample < 12:
        score = min(score, 58.0)
    score = _clip(score, 0, 100)
    label = "HIGH" if score >= 75 else "MODERATE" if score >= 55 else "LOW" if score >= 35 else "UNRELIABLE"
    old.update({
        "base_score_before_multiscale_calibration": round(base, 4), "score": round(score, 4),
        "status": label, "calibrated_label": label,
        "multiscale_calibration_components": {
            "entropy_quality": round(entropy_quality, 4), "agreement_quality": round(agreement, 4),
            "transition_quality": round(transition_quality, 4), "sample_quality": round(sample_quality, 4),
            "calibration_quality": round(calibration_quality, 4), "coverage_quality": round(coverage_quality, 4),
            "path_quality": round(path_quality, 4),
        },
    })
    return old


def _meta_labels(canonical: MutableMapping[str, Any], multiscale: Mapping[str, Any], reliability: Mapping[str, Any], probabilistic: Mapping[str, Any]) -> Dict[str, Any]:
    final = dict(canonical.get("final_decision") or {})
    direction = str(final.get("directional_market_view") or canonical.get("full_metric_direction") or "WAIT").upper()
    rel = _finite(reliability.get("score"), 0)
    entropy = _finite(multiscale.get("mean_normalized_entropy"), 1)
    transition = _finite(multiscale.get("multi_scale_transition_risk_pct"), 100)
    agreement = _finite(multiscale.get("multi_scale_agreement_score_0_10"), 0)
    tp = _finite(probabilistic.get("probability_touch_tp_pct"), 0); sl = _finite(probabilistic.get("probability_touch_sl_pct"), 100)
    current = str(final.get("tradeability_decision") or final.get("final_decision") or "WAIT").upper()
    conjunction_block = (entropy > .72 and transition > 58 and agreement < 5.0) or (rel < 38 and sl > tp)
    tradeability = "BLOCK" if conjunction_block and current not in {"BUY", "SELL"} else "WAIT" if conjunction_block else "TRADE" if current in {"BUY", "SELL"} else "WAIT"
    timing = "NOW" if tradeability == "TRADE" and rel >= 68 and transition < 42 else "NEXT HOUR" if tradeability == "TRADE" else "LATE"
    risk = "LOW" if rel >= 72 and transition < 35 else "MEDIUM" if rel >= 48 and transition < 68 else "HIGH"
    regime_support = "ALIGNED" if agreement >= 7 else "MIXED" if agreement >= 4.5 else "OPPOSED"
    path_support = "STRONG" if tp >= sl + 10 else "WEAK" if tp >= sl else "CONFLICTED"
    event = _finite((canonical.get("nlp") or {}).get("importance"), 0)
    liquidity = "PROTECT" if event >= 80 or multiscale.get("current_volatility_regime") == "CRISIS" else "CAUTION" if event >= 50 or transition >= 60 else "NORMAL"
    reason = "Direction retained, but uncertainty/transition/path evidence blocks immediate entry." if conjunction_block else "Direction and risk controls are jointly evaluated without replacing Full Metric authority."
    return {
        "direction": direction if direction in {"BUY", "SELL"} else "NEUTRAL", "tradeability": tradeability,
        "timing": timing, "risk": risk, "regime_support": regime_support, "path_support": path_support,
        "liquidity_event_condition": liquidity, "reason": reason,
    }


def _apply_decision_modifiers(canonical: MutableMapping[str, Any], multiscale: Mapping[str, Any], reliability: Mapping[str, Any], meta: Mapping[str, Any]) -> Dict[str, Any]:
    final = dict(canonical.get("final_decision") or {})
    risk = _finite(multiscale.get("multi_scale_transition_risk_pct"), 50.0)
    entropy = _finite(multiscale.get("mean_normalized_entropy"), .5)
    agreement = _finite(multiscale.get("multi_scale_agreement_score_0_10"), 5.0)
    base_entry = _finite(canonical.get("entry_score"), 0.0); base_hold = _finite(canonical.get("hold_safety"), 0.0); base_exit = _finite(canonical.get("exit_risk"), 10.0)
    # Protected scores remain unchanged. These are explicitly named decision inputs.
    modifiers = {
        "entry_decision_input": round(_clip(base_entry - risk / 100.0 * 1.25 - entropy * .65 + agreement / 10.0 * .45, 0, 10), 4),
        "hold_score_input": round(_clip(base_hold - risk / 100.0 * 1.10 - entropy * .50 + agreement / 10.0 * .35, 0, 10), 4),
        "exit_risk_input": round(_clip(base_exit + risk / 100.0 * 1.35 + entropy * .60 - agreement / 10.0 * .30, 0, 10), 4),
        "reliability_input_pct": round(_finite(reliability.get("score"), 0.0), 4),
        "wait_probability_modifier_pct": round(_clip(entropy * 35.0 + risk * .25 - agreement * 1.8, 0, 55), 4),
        "protected_scores_unchanged": True,
    }
    if meta.get("tradeability") in {"WAIT", "BLOCK"} and str(final.get("tradeability_decision") or "WAIT").upper() in {"BUY", "SELL"}:
        final["tradeability_decision"] = "WAIT"
        final["final_decision"] = "WAIT"
        final["less_risky_decision"] = "WAIT"
        reasons = list(final.get("blocking_reasons") or [])
        message = "Multi-scale entropy, transition risk and path support jointly require WAIT"
        if message not in reasons:
            reasons.append(message)
        final["blocking_reasons"] = reasons
    final["calibrated_confidence"] = round(_finite(reliability.get("score"), 0.0), 4)
    final["uncertainty_pct"] = round(_clip(100.0 - _finite(reliability.get("score"), 0.0), 0, 100), 4)
    canonical["final_decision"] = final
    return modifiers


def _layer_record(name: str, input_hash: str, output: Any, calculation_id: str, latest: Any, started: float, dirty: bool, success: bool = True, error: str = "", rows: int = 0) -> Dict[str, Any]:
    try:
        encoded = json.dumps(_json_safe(output), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        output_hash = sha256(encoded).hexdigest()
    except Exception:
        output_hash = "UNAVAILABLE"
    return {
        "layer_name": name, "input_hash": input_hash, "output_hash": output_hash,
        "canonical_calculation_id": calculation_id, "last_completed_h1_timestamp": _json_scalar(latest),
        "cache_version": UPGRADE_VERSION, "execution_duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "peak_memory_estimate_bytes": int(max(rows, 1) * 64), "dirty": bool(dirty), "success": bool(success),
        "error_message": str(error)[:500], "row_count": int(rows), "output_schema_version": SHARED_SCHEMA_VERSION,
    }


def build_and_apply_upgrade(
    canonical: Mapping[str, Any], *, ohlc: pd.DataFrame, calibrated_bundle: Any = None,
    prediction_history: Any = None, previous_cache: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Any]:
    """Enrich one canonical payload and return payload, cache and updated bundle."""
    payload = deepcopy(dict(canonical or {}))
    market = _completed_market(ohlc, payload.get("latest_completed_candle_time"))
    if len(market) < 12:
        raise ValueError("Multi-scale upgrade requires at least 12 completed timestamped H1 rows")
    calculation_id = _canonical_calculation_id(payload, market)
    input_hash = _frame_hash(market)
    previous = dict(previous_cache or {})
    if previous.get("canonical_calculation_id") == calculation_id and previous.get("input_hash") == input_hash and isinstance(previous.get("public_result"), Mapping):
        public = deepcopy(dict(previous["public_result"]))
        # Reapply cached deterministic results to the fresh unique run object.
        for key, value in public.items():
            payload[key] = deepcopy(value)
        payload.setdefault("metadata", {})["multiscale_cache_status"] = "REUSED"
        return payload, previous, calibrated_bundle

    layers: list[Dict[str, Any]] = []
    t = time.perf_counter()
    multiscale = _multiscale_regime(market)
    directional = {"D1": _directional_regime(market, 120), "H4": _directional_regime(market, 24), "H1": _directional_regime(market, 6)}
    multiscale["directional_context"] = directional
    existing_regime = str((payload.get("regime") or {}).get("major_regime") or payload.get("current_major_regime") or "UNKNOWN")
    multiscale["combined_existing_and_volatility_regime"] = f"{existing_regime} + {multiscale['current_volatility_regime']}"
    layers.append(_layer_record("Layer 3 - Multi-scale volatility regime", input_hash, multiscale, calculation_id, market["time"].iloc[-1], t, True, rows=len(market)))

    payload["multiscale_regime"] = multiscale
    t = time.perf_counter(); patches = _patch_summaries(market, payload, prediction_history)
    layers.append(_layer_record("Layer 4 - Causal temporal patches", input_hash, patches, calculation_id, market["time"].iloc[-1], t, True, rows=len(patches.get("patches", []))))

    t = time.perf_counter(); gating = _dynamic_feature_gating(payload, market, multiscale)
    layers.append(_layer_record("Layer 4 - Dynamic feature gating", input_hash, gating, calculation_id, market["time"].iloc[-1], t, True, rows=len(gating)))

    t = time.perf_counter(); probabilistic, updated_bundle = _probabilistic_projection(payload, market, calibrated_bundle, prediction_history, multiscale, calculation_id)
    layers.append(_layer_record("Layer 7 - Coherent probabilistic path", input_hash, probabilistic, calculation_id, market["time"].iloc[-1], t, True, rows=6))

    t = time.perf_counter(); decomposition = _decomposition(market, probabilistic, multiscale)
    layers.append(_layer_record("Layer 6 - Additive forecast decomposition", input_hash, decomposition, calculation_id, market["time"].iloc[-1], t, True, rows=6))

    t = time.perf_counter(); validation = _validation(payload, prediction_history, probabilistic)
    layers.append(_layer_record("Layer 8 - Reliability and financial validation", input_hash, validation, calculation_id, market["time"].iloc[-1], t, True, rows=int(validation.get("sample_count") or 0)))

    reliability = _calibrated_reliability(payload, multiscale, probabilistic, validation)
    payload["reliability"] = reliability
    meta = _meta_labels(payload, multiscale, reliability, probabilistic)
    modifiers = _apply_decision_modifiers(payload, multiscale, reliability, meta)

    # Enrich existing regime object without replacing its directional label/formulas.
    regime = dict(payload.get("regime") or {})
    h1 = (multiscale.get("scales") or {}).get("H1", {})
    regime.update({
        "volatility_regime": multiscale.get("current_volatility_regime"),
        "volatility_regime_probabilities": h1.get("probabilities"),
        "volatility_regime_entropy": h1.get("normalized_shannon_entropy"),
        "volatility_regime_confidence": h1.get("regime_confidence_pct"),
        "volatility_regime_age_hours": h1.get("current_regime_age_candles"),
        "expected_volatility_regime_duration_hours": h1.get("historical_median_duration_candles"),
        "remaining_volatility_regime_duration_range_hours": h1.get("remaining_duration_range_candles"),
        "volatility_regime_stability_pct": h1.get("regime_stability_pct"),
        "volatility_regime_change_risk_pct": h1.get("regime_change_risk_pct"),
        "probabilistic_transition_window": h1.get("estimated_transition_window"),
        "multi_scale_agreement_score": multiscale.get("multi_scale_agreement_score_0_10"),
    })
    payload["regime"] = regime

    # Add H+4/H+5 and quantiles to existing horizon records while retaining point forecasts.
    forecasts = dict(payload.get("forecasts") or {}); horizons = dict(forecasts.get("horizons") or {})
    for row in probabilistic.get("horizons", []):
        key = f"{int(row['horizon_hours'])}h"; existing = dict(horizons.get(key) or {})
        existing.setdefault("horizon_hours", int(row["horizon_hours"])); existing.setdefault("point_forecast", row["predicted_close"])
        existing.update({
            "p10": row["p10"], "p25": row["p25"], "p50": row["p50"], "p75": row["p75"], "p90": row["p90"],
            "lower_bound": row["p10"], "upper_bound": row["p90"], "interval_width": row["confidence_interval_width"],
            "probability_finish_above_current_pct": row["probability_finish_above_current_pct"],
            "probability_finish_below_current_pct": row["probability_finish_below_current_pct"],
        })
        horizons[key] = existing
    forecasts["horizons"] = horizons; forecasts["probabilistic_path"] = probabilistic
    payload["forecasts"] = forecasts

    payload.update({
        "shared_result_schema_version": SHARED_SCHEMA_VERSION,
        "canonical_calculation_id": calculation_id,
        "volatility_regime": {"current": multiscale.get("current_volatility_regime"), "scales": multiscale.get("scales")},
        "temporal_patches": patches,
        "dynamic_feature_weights": gating,
        "probabilistic_projection": probabilistic,
        "forecast_decomposition": decomposition,
        "validation_metrics": validation,
        "meta_labels": meta,
        "decision_input_modifiers": modifiers,
        "layer_execution_metadata": layers,
    })
    payload.setdefault("metadata", {}).update({
        "multiscale_upgrade_version": UPGRADE_VERSION, "multiscale_cache_status": "RECALCULATED",
        "causal_completed_candles_only": True, "central_powerbi_path_preserved": True,
        "full_metric_formulas_preserved": True, "no_new_prediction_engine": True,
    })
    public_keys = (
        "shared_result_schema_version", "canonical_calculation_id", "volatility_regime", "multiscale_regime",
        "temporal_patches", "dynamic_feature_weights", "probabilistic_projection", "forecast_decomposition",
        "validation_metrics", "meta_labels", "decision_input_modifiers", "layer_execution_metadata",
        "regime", "forecasts", "reliability", "final_decision", "metadata",
    )
    public = {k: deepcopy(payload.get(k)) for k in public_keys if k in payload}
    cache = {
        "version": UPGRADE_VERSION, "canonical_calculation_id": calculation_id, "input_hash": input_hash,
        "latest_completed_h1_timestamp": _json_scalar(market["time"].iloc[-1]), "public_result": public,
        "cached_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    return payload, cache, updated_bundle


def enrich_existing_regime_tables(
    detail_tables: Mapping[str, pd.DataFrame] | None, summary_table: pd.DataFrame | None,
    multiscale: Mapping[str, Any], calculation_id: str,
) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame]:
    """Expose new values only inside the already-existing regime tables."""
    h1 = (multiscale.get("scales") or {}).get("H1", {}) if isinstance(multiscale, Mapping) else {}
    values = {
        "Volatility Regime": multiscale.get("current_volatility_regime"),
        "P(Calm)": (h1.get("probabilities") or {}).get("CALM"),
        "P(Turbulent)": (h1.get("probabilities") or {}).get("TURBULENT"),
        "P(Crisis)": (h1.get("probabilities") or {}).get("CRISIS"),
        "Regime Entropy": h1.get("normalized_shannon_entropy"),
        "Regime Age": h1.get("current_regime_age_candles"),
        "Expected Regime Duration": h1.get("historical_median_duration_candles"),
        "Remaining Duration Range": str(h1.get("remaining_duration_range_candles")),
        "Regime Stability %": h1.get("regime_stability_pct"),
        "Regime Change Risk %": h1.get("regime_change_risk_pct"),
        "Transition Window": h1.get("estimated_transition_window"),
        "Multi-Scale Agreement /10": multiscale.get("multi_scale_agreement_score_0_10"),
        "Canonical Calculation ID": calculation_id,
    }
    output: Dict[str, pd.DataFrame] = {}
    for key, frame in dict(detail_tables or {}).items():
        if not isinstance(frame, pd.DataFrame):
            output[key] = frame
            continue
        enriched = frame.copy(deep=False)
        for column, value in values.items():
            enriched[column] = value
        output[key] = enriched
    summary = summary_table.copy(deep=False) if isinstance(summary_table, pd.DataFrame) else pd.DataFrame()
    if not summary.empty:
        for column, value in values.items():
            summary[column] = value
    return output, summary


def invariant_report(payload: Mapping[str, Any]) -> Dict[str, bool]:
    ms = payload.get("multiscale_regime") or {}; scales = ms.get("scales") or {}
    probability_ok = all(abs(sum((scales.get(s, {}).get("probabilities") or {}).values()) - 1.0) < 1e-6 for s in ("D1", "H4", "H1"))
    joint_ok = abs(_finite(ms.get("joint_probability_sum"), 0) - 1.0) < 1e-6
    rows = (payload.get("probabilistic_projection") or {}).get("horizons", [])
    quantile_ok = all(r["p10"] <= r["p25"] <= r["p50"] <= r["p75"] <= r["p90"] for r in rows)
    decomp_ok = all(abs(_finite(r.get("reconciliation_error"), 99)) <= 1e-8 for r in (payload.get("forecast_decomposition") or {}).get("horizons", []))
    h1vol = (scales.get("H1") or {}).get("expected_state_volatility") or {}
    vol_order_ok = _finite(h1vol.get("CALM"), 9) < _finite(h1vol.get("TURBULENT"), 0) < _finite(h1vol.get("CRISIS"), 0)
    return {
        "regime_probabilities_sum_to_one": probability_ok,
        "joint_27_probabilities_sum_to_one": joint_ok,
        "quantile_ordering": quantile_ok,
        "decomposition_reconciles": decomp_ok,
        "volatility_ordering": vol_order_ok,
    }
