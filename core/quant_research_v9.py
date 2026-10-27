"""Lightweight Quant Sync V9 research features.

All functions are deterministic, bounded, completed-candle-only helpers. They
consume existing OHLC/history and never trigger a model fit or external API.
"""
from __future__ import annotations

from math import exp, log, pi, sqrt
from typing import Any, Mapping

import numpy as np
import pandas as pd

VERSION = "quant-research-v9-20260622"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if np.isfinite(out) else default
    except Exception:
        return default


def _ohlc(frame: Any, limit: int = 1500) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    cols = {str(c).lower(): c for c in frame.columns}
    close_col = cols.get("close")
    if close_col is None:
        return pd.DataFrame()
    out = pd.DataFrame(index=frame.index)
    for name in ("open", "high", "low", "close", "volume", "tick_volume"):
        col = cols.get(name)
        if col is not None:
            out[name] = pd.to_numeric(frame[col], errors="coerce")
    if "volume" not in out and "tick_volume" in out:
        out["volume"] = out["tick_volume"]
    out = out.dropna(subset=["close"]).tail(limit).reset_index(drop=True)
    return out


def _normal_pdf(x: float, mean: float, sd: float) -> float:
    sd = max(abs(sd), 1e-9)
    z = (x - mean) / sd
    return exp(-0.5 * z * z) / (sd * sqrt(2.0 * pi))


def hamilton_regime_summary(frame: Any) -> dict[str, Any]:
    d = _ohlc(frame)
    if len(d) < 20:
        return {"status": "INSUFFICIENT", "regime_probability": 0.5, "regime": "UNKNOWN"}
    r = np.log(d["close"]).diff().dropna()
    recent = r.tail(min(80, len(r)))
    x = float(recent.iloc[-1])
    mean = float(recent.ewm(span=12, adjust=False).mean().iloc[-1])
    low_sd = max(float(recent.rolling(30, min_periods=10).std().iloc[-1] or 0.0) * 0.70, 1e-6)
    high_sd = max(low_sd * 2.25, float(recent.std(ddof=0) or low_sd))
    prior_high = 0.25
    high_like = _normal_pdf(x, 0.0, high_sd) * prior_high
    low_like = _normal_pdf(x, mean, low_sd) * (1.0 - prior_high)
    p_high = high_like / max(high_like + low_like, 1e-12)
    trend_z = mean / max(low_sd, 1e-9)
    if p_high >= 0.58:
        regime = "HIGH_VOL_BULL" if trend_z > 0.15 else "HIGH_VOL_BEAR" if trend_z < -0.15 else "HIGH_VOL_RANGE"
    else:
        regime = "LOW_VOL_BULL" if trend_z > 0.15 else "LOW_VOL_BEAR" if trend_z < -0.15 else "LOW_VOL_RANGE"
    return {"status": "OK", "regime_probability": round(float(max(p_high, 1.0 - p_high)), 6), "high_vol_probability": round(float(p_high), 6), "regime": regime, "trend_z": round(float(trend_z), 6)}


def bayesian_online_changepoint_probability(frame: Any, hazard: float = 1 / 72) -> dict[str, Any]:
    d = _ohlc(frame)
    if len(d) < 24:
        return {"status": "INSUFFICIENT", "change_point_probability": 0.0}
    r = np.log(d["close"]).diff().dropna()
    base = r.tail(min(240, len(r)))
    recent = base.tail(6)
    mu = float(base.iloc[:-6].mean()) if len(base) > 12 else float(base.mean())
    sd = max(float(base.iloc[:-6].std(ddof=0)) if len(base) > 12 else float(base.std(ddof=0)), 1e-7)
    shift = abs(float(recent.mean()) - mu) / sd
    vol_shift = abs(float(recent.std(ddof=0)) - sd) / sd
    surprise = min(12.0, 0.75 * shift + 0.45 * vol_shift)
    odds = hazard / max(1.0 - hazard, 1e-9) * exp(surprise)
    prob = odds / (1.0 + odds)
    return {"status": "OK", "change_point_probability": round(float(np.clip(prob, 0.0, 1.0)), 6), "mean_shift_z": round(shift, 6), "volatility_shift_ratio": round(vol_shift, 6)}


def garch_volatility_risk(frame: Any) -> dict[str, Any]:
    d = _ohlc(frame)
    if len(d) < 30:
        return {"status": "INSUFFICIENT", "volatility_risk_score": 50.0}
    r = np.log(d["close"]).diff().dropna().to_numpy(float)
    var0 = max(float(np.var(r[-120:])), 1e-12)
    alpha, beta = 0.08, 0.90
    omega = var0 * max(1.0 - alpha - beta, 0.005)
    var = var0
    for eps in r[-300:]:
        var = omega + alpha * float(eps * eps) + beta * var
    current = sqrt(max(var, 1e-12))
    hist = pd.Series(r).rolling(24, min_periods=12).std().dropna()
    if hist.empty:
        percentile = 0.5
    else:
        percentile = float((hist <= current).mean())
    return {"status": "OK", "forecast_volatility": round(current, 8), "volatility_risk_score": round(100.0 * percentile, 4), "garch_alpha": alpha, "garch_beta": beta}


def deflated_reliability_score(raw_reliability: Any, *, sample_count: Any = 0, model_count: Any = 1, forecast_disagreement: Any = 0.0, error_pct: Any = 0.0) -> dict[str, Any]:
    raw = float(np.clip(_num(raw_reliability, 50.0), 0.0, 100.0))
    n = max(_num(sample_count, 0.0), 0.0)
    models = max(_num(model_count, 1.0), 1.0)
    small_sample_penalty = 22.0 / sqrt(max(n, 1.0))
    multiple_testing_penalty = min(15.0, 2.5 * log(models + 1.0))
    disagreement_penalty = 0.18 * float(np.clip(_num(forecast_disagreement), 0.0, 100.0))
    error_penalty = 0.30 * float(np.clip(_num(error_pct), 0.0, 100.0))
    score = np.clip(raw - small_sample_penalty - multiple_testing_penalty - disagreement_penalty - error_penalty, 0.0, 100.0)
    return {"raw_reliability": round(raw, 4), "deflated_reliability_score": round(float(score), 4), "penalty": round(float(raw - score), 4)}


def triple_barrier_labels(frame: Any, horizon: int = 6, width_multiplier: float = 1.25) -> dict[str, Any]:
    d = _ohlc(frame, 800)
    if len(d) < horizon + 30:
        return {"status": "INSUFFICIENT", "latest_label": "UNAVAILABLE", "rows": []}
    close = d["close"].to_numpy(float)
    ret = pd.Series(np.log(close)).diff()
    vol = ret.ewm(span=24, adjust=False).std().fillna(ret.std()).to_numpy(float)
    rows: list[dict[str, Any]] = []
    start = max(0, len(close) - 160 - horizon)
    for i in range(start, len(close) - horizon):
        sigma = max(float(vol[i]), 1e-7)
        upper = close[i] * exp(width_multiplier * sigma * sqrt(horizon))
        lower = close[i] * exp(-width_multiplier * sigma * sqrt(horizon))
        path = close[i + 1:i + horizon + 1]
        up_hits = np.where(path >= upper)[0]
        dn_hits = np.where(path <= lower)[0]
        if len(up_hits) and (not len(dn_hits) or up_hits[0] < dn_hits[0]):
            label, hit = "UPPER", int(up_hits[0] + 1)
        elif len(dn_hits):
            label, hit = "LOWER", int(dn_hits[0] + 1)
        else:
            label, hit = "TIME", horizon
        rows.append({"index": int(i), "label": label, "bars_to_hit": hit, "upper": upper, "lower": lower, "terminal_return": float(path[-1] / close[i] - 1.0)})
    return {"status": "OK", "latest_label": rows[-1]["label"] if rows else "UNAVAILABLE", "rows": rows[-80:], "horizon": horizon}


def meta_label_probability(*, entry_score: Any, exit_risk: Any, tp_quality: Any, reliability: Any, data_quality: Any, volatility_risk: Any, change_probability: Any) -> dict[str, Any]:
    x = (
        0.045 * (_num(entry_score, 5.0) * 10.0 - 50.0)
        + 0.035 * (_num(tp_quality, 5.0) * 10.0 - 50.0)
        + 0.025 * (_num(reliability, 50.0) - 50.0)
        + 0.020 * (_num(data_quality, 50.0) - 50.0)
        - 0.045 * (_num(exit_risk, 5.0) * 10.0 - 50.0)
        - 0.018 * (_num(volatility_risk, 50.0) - 50.0)
        - 1.4 * _num(change_probability, 0.0)
    )
    p = 1.0 / (1.0 + exp(-float(np.clip(x, -20.0, 20.0))))
    return {"take_probability": round(p, 6), "skip_probability": round(1.0 - p, 6), "meta_label": "TAKE" if p >= 0.56 else "SKIP" if p <= 0.44 else "REVIEW"}


def hasbrouck_impact_proxy(frame: Any) -> dict[str, Any]:
    d = _ohlc(frame)
    if len(d) < 25:
        return {"status": "INSUFFICIENT", "impact_score": 50.0}
    volume = d.get("volume", pd.Series(np.ones(len(d)), index=d.index)).replace(0, np.nan).ffill().fillna(1.0)
    ret = np.log(d["close"]).diff().abs()
    impact = (ret / np.sqrt(volume.clip(lower=1.0))).replace([np.inf, -np.inf], np.nan).dropna()
    if impact.empty:
        return {"status": "INSUFFICIENT", "impact_score": 50.0}
    latest = float(impact.iloc[-1])
    score = float((impact <= latest).mean() * 100.0)
    return {"status": "OK", "impact_proxy": latest, "impact_score": round(score, 4)}


def hawkes_shock_intensity(frame: Any, decay: float = 0.82) -> dict[str, Any]:
    d = _ohlc(frame)
    if len(d) < 30:
        return {"status": "INSUFFICIENT", "shock_intensity_score": 0.0}
    r = np.log(d["close"]).diff().dropna()
    threshold = max(float(r.abs().quantile(0.90)), 1e-7)
    shocks = (r.abs() >= threshold).astype(float).tail(160).to_numpy()
    intensity = 0.0
    for event in shocks:
        intensity = decay * intensity + float(event)
    stationary_scale = max(1.0 / max(1.0 - decay, 1e-6), 1.0)
    score = 100.0 * min(intensity / stationary_scale, 1.0)
    return {"status": "OK", "shock_intensity": round(intensity, 6), "shock_intensity_score": round(score, 4), "shock_threshold": threshold}


def attention_weights(features: Mapping[str, Any]) -> dict[str, Any]:
    names = list(features)
    if not names:
        return {"status": "EMPTY", "weights": {}}
    values = np.asarray([abs(_num(features[n], 0.0)) for n in names], dtype=float)
    if np.allclose(values, values[0]):
        weights = np.ones_like(values) / len(values)
    else:
        z = (values - values.mean()) / max(values.std(), 1e-9)
        e = np.exp(np.clip(z, -8.0, 8.0))
        weights = e / max(e.sum(), 1e-12)
    return {"status": "OK", "weights": {name: round(float(weight), 6) for name, weight in zip(names, weights)}}


def smooth_projection_confidence_band(frame: Any, horizon: int = 6, confidence_z: float = 1.645) -> dict[str, Any]:
    d = _ohlc(frame)
    if len(d) < 20:
        return {"status": "INSUFFICIENT", "rows": []}
    close = d["close"]
    r = np.log(close).diff().dropna()
    drift = float(r.ewm(span=24, adjust=False).mean().iloc[-1])
    vol = max(float(r.ewm(span=36, adjust=False).std().iloc[-1]), 1e-7)
    anchor = float(close.iloc[-1])
    rows = []
    previous_mid = anchor
    for h in range(1, max(int(horizon), 1) + 1):
        raw_mid = anchor * exp(drift * h)
        mid = 0.65 * raw_mid + 0.35 * previous_mid
        width = confidence_z * vol * sqrt(h)
        rows.append({"horizon": h, "mid": mid, "lower": mid * exp(-width), "upper": mid * exp(width), "confidence": 0.90})
        previous_mid = mid
    return {"status": "OK", "rows": rows, "anchor": anchor, "drift": drift, "volatility": vol}


def build_quant_research_v9(frame: Any, *, raw_reliability: Any = 50.0, sample_count: Any = 0, model_count: Any = 1, forecast_disagreement: Any = 0.0, error_pct: Any = 0.0, entry_score: Any = 5.0, exit_risk: Any = 5.0, tp_quality: Any = 5.0, data_quality: Any = 50.0) -> dict[str, Any]:
    regime = hamilton_regime_summary(frame)
    cp = bayesian_online_changepoint_probability(frame)
    vol = garch_volatility_risk(frame)
    reliability = deflated_reliability_score(raw_reliability, sample_count=sample_count, model_count=model_count, forecast_disagreement=forecast_disagreement, error_pct=error_pct)
    barriers = triple_barrier_labels(frame)
    meta = meta_label_probability(entry_score=entry_score, exit_risk=exit_risk, tp_quality=tp_quality, reliability=reliability["deflated_reliability_score"], data_quality=data_quality, volatility_risk=vol.get("volatility_risk_score"), change_probability=cp.get("change_point_probability"))
    impact = hasbrouck_impact_proxy(frame)
    hawkes = hawkes_shock_intensity(frame)
    attention = attention_weights({"H1": entry_score, "M1": tp_quality, "history": reliability["deflated_reliability_score"], "news": 100.0 - _num(forecast_disagreement), "regime": 100.0 * _num(regime.get("regime_probability"), 0.5)})
    band = smooth_projection_confidence_band(frame)
    return {"version": VERSION, "hamilton_regime": regime, "bayesian_changepoint": cp, "garch_volatility": vol, "deflated_reliability": reliability, "triple_barrier": barriers, "meta_label": meta, "hasbrouck_impact": impact, "hawkes_intensity": hawkes, "attention": attention, "projection_band": band, "lightweight_only": True, "protected_logic_changed": False}


__all__ = ["VERSION", "hamilton_regime_summary", "bayesian_online_changepoint_probability", "garch_volatility_risk", "deflated_reliability_score", "triple_barrier_labels", "meta_label_probability", "hasbrouck_impact_proxy", "hawkes_shock_intensity", "attention_weights", "smooth_projection_confidence_band", "build_quant_research_v9"]
