"""Causal, symbol-local Field 10 probability, EV, volume and shock metrics.

The functions in this module consume completed H1 candles only.  They never copy
statistics across symbols and never manufacture a probability from a reliability
score.  Every result carries method/sample provenance so UI and persistence layers
can distinguish validated evidence from an unavailable metric.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any, Mapping

import numpy as np
import pandas as pd

VERSION = "field10-rank-ev6-probability-volume12-20260704-v1"
MIN_ANALOGUES = 30


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def normalize_h1(frame: Any) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    lookup = {str(c).strip().lower().replace("_", " "): c for c in frame.columns}
    def choose(*names: str):
        for name in names:
            if name in lookup:
                return lookup[name]
        return None
    close_col = choose("close", "c")
    if close_col is None:
        return pd.DataFrame()
    time_col = choose("time", "timestamp", "datetime", "date", "broker candle time")
    open_col, high_col, low_col = choose("open", "o"), choose("high", "h"), choose("low", "l")
    volume_col = choose("tick volume", "tick_volume", "tickvolume", "volume", "vol", "real volume")
    out = pd.DataFrame(index=frame.index)
    out["time"] = pd.to_datetime(frame[time_col], errors="coerce", utc=True) if time_col is not None else pd.date_range("2000-01-01", periods=len(frame), freq="h", tz="UTC")
    out["close"] = pd.to_numeric(frame[close_col], errors="coerce")
    out["open"] = pd.to_numeric(frame[open_col], errors="coerce") if open_col is not None else out["close"].shift(1)
    out["high"] = pd.to_numeric(frame[high_col], errors="coerce") if high_col is not None else pd.concat([out["open"], out["close"]], axis=1).max(axis=1)
    out["low"] = pd.to_numeric(frame[low_col], errors="coerce") if low_col is not None else pd.concat([out["open"], out["close"]], axis=1).min(axis=1)
    out["tick_volume"] = pd.to_numeric(frame[volume_col], errors="coerce") if volume_col is not None else np.nan
    if volume_col is None:
        out.attrs["volume_source"] = "UNAVAILABLE"
    else:
        label = str(volume_col).lower()
        out.attrs["volume_source"] = "BROKER_TICK_VOLUME" if "tick" in label or "volume" in label else "PROVIDER_VOLUME"
    out = out.replace([np.inf, -np.inf], np.nan).dropna(subset=["time", "close"])
    return out.sort_values("time", kind="mergesort").drop_duplicates("time", keep="last").tail(6000).reset_index(drop=True)


def _feature_frame(market: pd.DataFrame) -> pd.DataFrame:
    close = market["close"].astype(float)
    ret = close.pct_change()
    fast = close.ewm(span=12, adjust=False, min_periods=12).mean()
    slow = close.ewm(span=48, adjust=False, min_periods=36).mean()
    sigma = ret.rolling(72, min_periods=36).std().replace(0, np.nan)
    trend = ((fast - slow) / (sigma * close)).clip(-8, 8)
    momentum = (close.pct_change(6) / (sigma * math.sqrt(6))).clip(-8, 8)
    vol_short = ret.rolling(24, min_periods=12).std()
    vol_long = ret.rolling(120, min_periods=60).std().replace(0, np.nan)
    vol_ratio = (vol_short / vol_long).clip(0.1, 8)
    strength = (0.62 * trend.fillna(0) + 0.38 * momentum.fillna(0)).clip(-8, 8)
    label = np.select(
        [strength >= 0.65, strength <= -0.65, vol_ratio >= 1.45, vol_ratio <= 0.70],
        ["BULL_TREND", "BEAR_TREND", "EXPANSION", "COMPRESSION"], default="RANGE",
    )
    return pd.DataFrame({
        "close": close, "return": ret, "strength": strength,
        "vol_ratio": vol_ratio, "label": label,
    }, index=market.index)


def transition_risk_6h(labels: pd.Series) -> dict[str, Any]:
    """Estimate six-step departure risk from a smoothed transition matrix.

    If enough completed runs of the current state exist, a discrete duration
    survival estimate is preferred.  Otherwise the six-step Markov probability is
    used.  Neither branch linearly scales a 1H or 24H risk.
    """
    values = labels.dropna().astype(str).tolist()
    if len(values) < 60:
        return {"value": None, "method": "INSUFFICIENT_VALID_EVIDENCE", "sample_size": len(values)}
    states = sorted(set(values))
    index = {state: i for i, state in enumerate(states)}
    counts = np.ones((len(states), len(states)), dtype=float)  # Laplace smoothing
    for left, right in zip(values[:-1], values[1:]):
        counts[index[left], index[right]] += 1.0
    matrix = counts / counts.sum(axis=1, keepdims=True)
    current = values[-1]

    runs: list[tuple[str, int]] = []
    run_state, run_len = values[0], 1
    for value in values[1:]:
        if value == run_state:
            run_len += 1
        else:
            runs.append((run_state, run_len)); run_state, run_len = value, 1
    current_age = run_len
    completed_durations = [duration for state, duration in runs if state == current]
    survivors_now = sum(duration >= current_age for duration in completed_durations)
    survivors_6 = sum(duration >= current_age + 6 for duration in completed_durations)
    if survivors_now >= 8:
        # Jeffreys smoothing avoids hard 0/1 with modest samples.
        survival = (survivors_6 + 0.5) / (survivors_now + 1.0)
        value = 100.0 * (1.0 - survival)
        method = "SEMI_MARKOV_EMPIRICAL_SURVIVAL"
        sample_size = survivors_now
    else:
        p6 = np.linalg.matrix_power(matrix, 6)
        value = 100.0 * (1.0 - float(p6[index[current], index[current]]))
        method = "MARKOV_P6_SELF_TRANSITION"
        sample_size = len(values) - 1
    return {
        "value": round(float(np.clip(value, 0.0, 100.0)), 6),
        "method": method, "sample_size": int(sample_size), "current_state": current,
        "current_age": int(current_age), "states": states,
        "transition_matrix": matrix.round(8).tolist(),
    }


def _analogue_samples(features: pd.DataFrame, horizon: int, max_neighbors: int = 240) -> tuple[np.ndarray, int]:
    if len(features) < horizon + 100:
        return np.array([], dtype=float), 0
    current = features.iloc[-1]
    history = features.iloc[:-horizon].copy()
    history["future_return"] = (features["close"].shift(-horizon) / features["close"] - 1.0).iloc[:-horizon]
    history = history.replace([np.inf, -np.inf], np.nan).dropna(subset=["strength", "vol_ratio", "future_return"])
    same = history.loc[history["label"].astype(str).eq(str(current["label"]))]
    candidates = same if len(same) >= MIN_ANALOGUES else history
    if len(candidates) < MIN_ANALOGUES:
        return np.array([], dtype=float), int(len(candidates))
    s_scale = float(candidates["strength"].std()) or 1.0
    v_scale = float(candidates["vol_ratio"].std()) or 1.0
    distance = ((candidates["strength"] - float(current["strength"])).abs() / max(s_scale, 1e-9)
                + 0.55 * (candidates["vol_ratio"] - float(current["vol_ratio"])).abs() / max(v_scale, 1e-9))
    chosen = candidates.assign(_distance=distance).sort_values("_distance", kind="mergesort").head(min(max_neighbors, len(candidates)))
    values = chosen["future_return"].to_numpy(dtype=float)
    distances = chosen["_distance"].to_numpy(dtype=float)
    weights = np.exp(-np.clip(distances, 0, 20))
    # Deterministic weighted resampling gives a predictive sample without RNG.
    if weights.sum() > 0:
        weights /= weights.sum()
        cdf = np.cumsum(weights)
        quantiles = (np.arange(max(200, len(values))) + 0.5) / max(200, len(values))
        values = values[np.searchsorted(cdf, quantiles, side="left").clip(0, len(values)-1)]
    low, high = np.quantile(values, [0.02, 0.98])
    return np.clip(values, low, high), int(len(chosen))


def predictive_ev_probabilities(
    features: pd.DataFrame, *, bias: str, cost_percent: float = 0.0,
    minimum_target_percent: float = 0.02, tail_lambda: float = 0.35,
) -> dict[str, Any]:
    sign = 1.0 if str(bias).upper() == "BUY" else -1.0
    cost = max(0.0, float(cost_percent)) / 100.0
    output: dict[str, Any] = {}
    sample_sizes: list[int] = []
    for horizon in (1, 6, 12):
        raw, n = _analogue_samples(features, horizon)
        sample_sizes.append(n)
        prefix = f"{horizon}h"
        if len(raw) == 0:
            output.update({
                f"probability_profit_{prefix}": None,
                f"probability_reach_ev_{prefix}": None,
                f"ev_target_{prefix}": None,
            })
            continue
        directional = sign * raw - cost
        expected_pct = float(np.mean(directional) * 100.0)
        target_pct = max(abs(expected_pct), float(minimum_target_percent))
        output[f"probability_profit_{prefix}"] = round(float(np.mean(directional > 0) * 100.0), 6)
        output[f"probability_reach_ev_{prefix}"] = round(float(np.mean(directional * 100.0 >= target_pct) * 100.0), 6)
        output[f"ev_target_{prefix}"] = round(target_pct, 6)
        if horizon == 6:
            losses_pct = -directional * 100.0
            var95 = float(np.quantile(losses_pct, 0.95))
            tail = losses_pct[losses_pct >= var95]
            cvar95 = float(tail.mean()) if len(tail) else var95
            output["expected_value_6h"] = round(expected_pct, 6)
            output["cvar95_6h"] = round(cvar95, 6)
            output["risk_adjusted_expected_value_6h"] = round(expected_pct - float(tail_lambda) * max(cvar95, 0.0), 6)
    output["evidence_sample_size"] = int(min([n for n in sample_sizes if n > 0], default=0))
    output["ev_model_version"] = VERSION
    output["probability_calibration_status"] = "EMPIRICAL_ANALOGUE_OOS_REQUIRED"
    return output


def volume_12h_metrics(market: pd.DataFrame) -> dict[str, Any]:
    volume = pd.to_numeric(market.get("tick_volume"), errors="coerce")
    source = str(market.attrs.get("volume_source") or "UNAVAILABLE")
    if volume is None or volume.notna().sum() < 36:
        return {"tick_volume_12h": None, "volume_12h_z": None, "volume_source": source,
                "volume_sample_size": int(0 if volume is None else volume.notna().sum())}
    rolling = volume.rolling(12, min_periods=12).sum().dropna()
    if rolling.empty:
        return {"tick_volume_12h": None, "volume_12h_z": None, "volume_source": source, "volume_sample_size": 0}
    observed = float(rolling.iloc[-1])
    history = rolling.iloc[:-1].tail(720)
    if len(history) < 20:
        z = None
    else:
        median = float(history.median())
        mad = float(np.median(np.abs(history.to_numpy(dtype=float) - median)))
        z = 0.67448975 * (observed - median) / mad if mad > 1e-12 else 0.0
    return {"tick_volume_12h": round(observed, 6), "volume_12h_z": None if z is None else round(float(np.clip(z, -20, 20)), 6),
            "volume_source": source, "volume_sample_size": int(len(history))}


def unexpected_situation(market: pd.DataFrame, *, transition_risk: float | None,
                         volume_z: float | None, provider_disagreement: float | None = None,
                         data_stale: bool = False, integrity_failed: bool = False) -> dict[str, Any]:
    returns = market["close"].pct_change().dropna()
    recent = returns.tail(24)
    baseline = returns.iloc[:-24].tail(480)
    vol_shock = 0.0
    gap_shock = 0.0
    if len(recent) >= 12 and len(baseline) >= 60:
        denom = float(baseline.std())
        if denom > 1e-12:
            vol_shock = float(recent.std() / denom)
            gap_shock = float(abs(recent.iloc[-1]) / denom)
    severity = 0.0
    reasons: list[str] = []
    def add(value: float, reason: str):
        nonlocal severity
        severity = max(severity, value); reasons.append(reason)
    if integrity_failed: add(1.0, "database_or_settlement_integrity_failure")
    if data_stale: add(0.90, "stale_or_incomplete_candle_data")
    if vol_shock >= 3.0: add(min(1.0, vol_shock / 5.0), "volatility_shock")
    if gap_shock >= 4.0: add(min(1.0, gap_shock / 8.0), "structural_price_gap")
    if volume_z is not None and abs(volume_z) >= 4.0: add(min(1.0, abs(volume_z) / 8.0), "abnormal_12h_volume")
    if transition_risk is not None and transition_risk >= 75.0: add(min(1.0, transition_risk / 100.0), "high_regime_transition_risk")
    if provider_disagreement is not None and provider_disagreement >= 0.003: add(min(1.0, provider_disagreement / 0.01), "api_provider_disagreement")
    status = "BLOCK" if severity >= 0.90 else "PROTECT" if severity >= 0.70 else "CAUTION" if severity >= 0.40 else "NORMAL"
    permission = "BLOCKED" if status == "BLOCK" else "PROTECTED" if status == "PROTECT" else "VALIDATE" if status == "CAUTION" else "PERMITTED"
    return {"unexpected_situation_status": status, "unexpected_situation_severity": round(severity * 100.0, 4),
            "validation_permission": permission, "unexpected_reasons": reasons or ["no_material_shock_detected"],
            "volatility_shock_ratio": round(vol_shock, 6), "gap_shock_z": round(gap_shock, 6)}


def compute_quant_metrics(frame: Any, *, bias: str, cost_percent: float = 0.0,
                          minimum_target_percent: float = 0.02) -> dict[str, Any]:
    market = normalize_h1(frame)
    if len(market) < 100:
        return {"ok": False, "status": "INSUFFICIENT_VALID_EVIDENCE", "sample_count": len(market), "version": VERSION}
    features = _feature_frame(market)
    transition = transition_risk_6h(features["label"])
    probabilities = predictive_ev_probabilities(features, bias=bias, cost_percent=cost_percent,
                                                 minimum_target_percent=minimum_target_percent)
    volume = volume_12h_metrics(market)
    shock = unexpected_situation(market, transition_risk=transition.get("value"), volume_z=volume.get("volume_12h_z"))
    provenance = {
        "cutoff": pd.Timestamp(market["time"].iloc[-1]).isoformat(),
        "transition_method": transition.get("method"),
        "transition_sample_size": transition.get("sample_size"),
        "probability_method": "same_symbol_regime_conditioned_weighted_analogues",
        "cost_percent": float(cost_percent),
        "volume_source": volume.get("volume_source"),
        "causal": True,
        "version": VERSION,
    }
    return {
        "ok": True, "status": "CAUSAL_H1_QUANT_EVIDENCE", "version": VERSION,
        "sample_count": int(len(market)), "transition_risk_6h": transition.get("value"),
        "transition_risk_6h_method": transition.get("method"),
        "transition_risk_6h_sample_count": transition.get("sample_size"),
        **probabilities, **volume, **shock,
        "metric_provenance_json": json.dumps(provenance, sort_keys=True, separators=(",", ":")),
    }


__all__ = [
    "VERSION", "normalize_h1", "transition_risk_6h", "predictive_ev_probabilities",
    "volume_12h_metrics", "unexpected_situation", "compute_quant_metrics",
]
