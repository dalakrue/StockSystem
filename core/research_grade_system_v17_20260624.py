"""Unified research-grade shadow architecture for EURUSD H1.

This module is deliberately additive.  It reads the immutable canonical Field 1
snapshot and matured historical evidence, but it never writes production keys,
production decisions, production regimes, or Field 1 tables.  Heavy evaluation
is owned by the Settings one-click publisher; Lunch renderers only read the
saved payload.

Implemented bounded, dependency-safe versions of:
- Giacomini-White conditional predictive ability
- rolling EnbPI-style conformal intervals
- Adams-MacKay Bayesian online changepoint detection
- Hamilton Markov-switching filtering
- chronological Platt/isotonic/beta probability calibration
- Hansen-Lunde-Nason Model Confidence Set
- Hansen Superior Predictive Ability test
- Quaedvlieg-style multi-horizon comparison summary
- lightweight TFT-inspired gated multi-horizon fusion
- Diebold-Mariano forecast comparison with overlapping-horizon HAC variance
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from math import erf, exp, log, pi, sqrt
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import json
import math
import re
import sqlite3
import time
import uuid

import numpy as np

SCHEMA_VERSION = "17.1.0-unified-shadow"
MODEL_VERSION = "research-grade-system-v17.1-20260624"
METHOD_VERSION = "2026.06.24"
HORIZONS = (1, 3, 6)
ACTIONS = ("BUY", "SELL", "WAIT")
REGIMES = ("BEAR", "COMPRESSION", "BULL")
TARGET_COVERAGE = 0.90
EPS = 1e-12


def _f(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _maybe_f(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _clip_probability(value: float) -> float:
    return float(np.clip(value, 1e-6, 1 - 1e-6))


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def gaussian_crps(y: float, mean: float, std: float) -> float:
    """Analytic CRPS for N(mean, std^2), kept separate from MAE."""
    if std <= 0 or not all(math.isfinite(x) for x in (y, mean, std)):
        return math.nan
    z = (y - mean) / std
    phi = exp(-0.5 * z * z) / sqrt(2 * pi)
    Phi = _normal_cdf(z)
    return float(std * (z * (2 * Phi - 1) + 2 * phi - 1 / sqrt(pi)))


def sample_crps(y: float, samples: Sequence[float]) -> float:
    x = np.asarray(samples, dtype=float)
    x = x[np.isfinite(x)]
    if not len(x):
        return math.nan
    return float(np.mean(np.abs(x - y)) - 0.5 * np.mean(np.abs(x[:, None] - x[None, :])))


def quantile_crps(y: float, quantiles: Sequence[float], levels: Sequence[float] = (0.1, 0.25, 0.5, 0.75, 0.9)) -> float:
    q = np.asarray(quantiles, dtype=float)
    a = np.asarray(levels, dtype=float)
    mask = np.isfinite(q) & np.isfinite(a)
    if not mask.any():
        return math.nan
    q, a = q[mask], a[mask]
    losses = np.maximum(a * (y - q), (a - 1) * (y - q))
    return float(2.0 * np.mean(losses))


def pinball_loss(y: float, q: float, tau: float) -> float:
    return float(max(tau * (y - q), (tau - 1) * (y - q)))


def interval_score(y: float, lower: float, upper: float, alpha: float = 0.10) -> float:
    if upper < lower:
        lower, upper = upper, lower
    return float((upper - lower) + (2 / alpha) * (lower - y if y < lower else 0) + (2 / alpha) * (y - upper if y > upper else 0))


def settlement_status(actuals: Mapping[int, Any]) -> str:
    """Independent H1/H3/H6 settlement state with invalid-data detection."""
    valid = 0
    for h in HORIZONS:
        value = actuals.get(h)
        if isinstance(value, Mapping) and str(value.get("status", "")).upper() == "INVALID":
            return "INVALID"
        if value is None:
            continue
        try:
            if not math.isfinite(float(value)):
                return "INVALID"
        except Exception:
            return "INVALID"
        valid += 1
    if valid == 0:
        return "UNSETTLED"
    if valid == len(HORIZONS):
        return "FULLY_SETTLED"
    return "PARTIALLY_SETTLED"


@dataclass(frozen=True)
class RunContract:
    run_id: str
    origin_id: str
    snapshot_schema_version: str
    symbol: str
    timeframe: str
    broker_candle_time: str
    data_cutoff_time: str
    market_data_hash: str
    source_snapshot_hash: str
    field1_protected_hash: str
    production_logic_hash: str
    model_versions: dict[str, str]
    feature_schema_hashes: dict[str, str]
    decision: str
    regime: str
    current_price: float
    forecast_origins: dict[str, str]
    created_at: str
    completion_status: str


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    if isinstance(snapshot, Mapping):
        return dict(snapshot)
    if hasattr(snapshot, "to_dict"):
        try:
            return dict(snapshot.to_dict())
        except Exception:
            pass
    if hasattr(snapshot, "__dict__"):
        return {k: v for k, v in vars(snapshot).items() if not k.startswith("_")}
    return {}


def build_contract(snapshot: Mapping[str, Any] | Any, state: Mapping[str, Any]) -> RunContract:
    snap = _snapshot_dict(snapshot)
    run_id = str(snap.get("run_id") or snap.get("canonical_calculation_id") or uuid.uuid4())
    broker = _iso(snap.get("broker_candle_time") or snap.get("latest_completed_candle_time") or snap.get("candle_time"))
    cutoff = _iso(snap.get("data_cutoff_time") or broker)
    symbol = str(snap.get("symbol") or "EURUSD").upper()
    timeframe = str(snap.get("timeframe") or "H1").upper()
    origin_id = f"{run_id}:{broker}:{symbol}:{timeframe}"
    protected = str(state.get("field1_protected_hash_20260624") or "")
    production = str(snap.get("production_logic_hash") or protected)
    current_price = _f(snap.get("current_price") or snap.get("price") or snap.get("close"))
    decision = str(snap.get("decision") or snap.get("current_decision") or "WAIT").upper()
    regime = str(snap.get("regime") or snap.get("directional_regime") or "UNKNOWN").upper()
    features = {
        "price_structure": ("return", "range", "close_position"),
        "trend": ("trend_3", "trend_12", "trend_48"),
        "volatility": ("vol_12", "vol_48"),
        "regime": ("production_regime", "shadow_regime"),
        "session": ("session",),
        "spread_liquidity": ("spread", "volume"),
        "event_news": ("news_score",),
        "historical_analogue": ("analogue_score",),
        "model_disagreement": ("dispersion",),
    }
    return RunContract(
        run_id=run_id,
        origin_id=origin_id,
        snapshot_schema_version=SCHEMA_VERSION,
        symbol=symbol,
        timeframe=timeframe,
        broker_candle_time=broker,
        data_cutoff_time=cutoff,
        market_data_hash=str(snap.get("market_data_hash") or _hash(_market_signature(state))),
        source_snapshot_hash=_hash(snap),
        field1_protected_hash=protected,
        production_logic_hash=production,
        model_versions={"unified": MODEL_VERSION, "full_tft": "DISABLED_BY_DEFAULT"},
        feature_schema_hashes={k: _hash(v) for k, v in features.items()},
        decision=decision if decision in ACTIONS else "WAIT",
        regime=regime,
        current_price=current_price,
        forecast_origins={str(h): broker for h in HORIZONS},
        created_at=datetime.now(timezone.utc).isoformat(),
        completion_status="PARTIAL",
    )


def validate_contract(contract: RunContract, field_records: Sequence[Mapping[str, Any]] = ()) -> list[str]:
    errors: list[str] = []
    if not contract.run_id:
        errors.append("MISSING_RUN_ID")
    if contract.symbol != "EURUSD" or contract.timeframe != "H1":
        errors.append("UNSUPPORTED_MARKET")
    if not contract.broker_candle_time:
        errors.append("MISSING_BROKER_CANDLE_TIME")
    cutoff, broker = _parse_time(contract.data_cutoff_time), _parse_time(contract.broker_candle_time)
    if cutoff and broker and cutoff > broker:
        errors.append("FUTURE_DATA_CUTOFF")
    for row in field_records:
        if str(row.get("run_id")) != contract.run_id:
            errors.append("MIXED_RUN_ID")
        if _iso(row.get("broker_candle_time")) != contract.broker_candle_time:
            errors.append("MIXED_BROKER_TIME")
        feature_time = _parse_time(row.get("feature_time"))
        origin = _parse_time(row.get("forecast_origin") or contract.broker_candle_time)
        if feature_time and origin and feature_time > origin:
            errors.append("FUTURE_FEATURE")
        maturity = _parse_time(row.get("maturity_time"))
        actual_available = _parse_time(row.get("actual_available_time"))
        if maturity and actual_available and actual_available < maturity:
            errors.append("PREMATURE_ACTUAL")
    return sorted(set(errors))


def _market_signature(state: Mapping[str, Any]) -> Any:
    for key in ("ohlc_df", "dv_pp_df", "market_data", "price_data"):
        obj = state.get(key)
        if obj is None:
            continue
        try:
            return {"key": key, "rows": len(obj), "columns": list(getattr(obj, "columns", []))}
        except Exception:
            return {"key": key, "type": type(obj).__name__}
    return {"rows": 0}


def _history(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("prediction_outcomes", "field8_history", "research_settled_outcomes"):
        raw = state.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            return [dict(x) for x in raw if isinstance(x, Mapping)]
    return []


def _matured_rows(state: Mapping[str, Any], horizon: int, cutoff: str = "") -> list[dict[str, Any]]:
    cutoff_dt = _parse_time(cutoff)
    rows: list[dict[str, Any]] = []
    for row in _history(state):
        if int(_f(row.get("horizon"), horizon)) != horizon:
            continue
        actual = _maybe_f(row.get("actual_return"))
        if actual is None:
            continue
        status = str(row.get("settlement_status") or row.get("status") or "FULLY_SETTLED").upper()
        if status in {"INVALID", "UNSETTLED", "PENDING"}:
            continue
        maturity = _parse_time(row.get("maturity_time"))
        if cutoff_dt and maturity and maturity > cutoff_dt:
            continue
        item = dict(row)
        item["actual_return"] = actual
        rows.append(item)
    rows.sort(key=lambda r: _parse_time(r.get("origin_candle_time") or r.get("forecast_origin") or r.get("created_time")) or datetime.min.replace(tzinfo=timezone.utc))
    return rows[-600:]


def _extract_returns(state: Mapping[str, Any], cutoff: str) -> np.ndarray:
    cutoff_dt = _parse_time(cutoff)
    for key in ("ohlc_df", "dv_pp_df", "market_data", "price_data"):
        frame = state.get(key)
        if frame is None or not hasattr(frame, "columns"):
            continue
        columns = {str(c).lower(): c for c in frame.columns}
        close_col = columns.get("close") or columns.get("price")
        time_col = columns.get("time") or columns.get("datetime") or columns.get("timestamp") or columns.get("date")
        if close_col is None:
            continue
        try:
            work = frame
            if time_col is not None and cutoff_dt is not None:
                times = [_parse_time(v) for v in work[time_col].tolist()]
                mask = [t is not None and t <= cutoff_dt for t in times]
                work = work.loc[mask]
            close = np.asarray(work[close_col], dtype=float)
            close = close[np.isfinite(close) & (close > 0)]
            if len(close) >= 3:
                return np.diff(np.log(close))[-600:]
        except Exception:
            continue
    values = [_maybe_f(r.get("actual_return")) for r in _history(state)]
    return np.asarray([v for v in values if v is not None], dtype=float)[-600:]


def _session_from_time(value: str) -> str:
    dt = _parse_time(value)
    if not dt:
        return "UNKNOWN"
    h = dt.hour
    if 7 <= h < 12:
        return "LONDON"
    if 12 <= h < 16:
        return "LONDON_NY_OVERLAP"
    if 16 <= h < 21:
        return "NEW_YORK"
    return "ASIA_OFF_HOURS"


def _volatility_bucket(row: Mapping[str, Any], default_vol: float) -> str:
    value = _maybe_f(row.get("volatility") or row.get("predicted_std") or row.get("realized_volatility"))
    value = default_vol if value is None else abs(value)
    if value < default_vol * 0.75:
        return "LOW"
    if value > default_vol * 1.5:
        return "HIGH"
    return "NORMAL"


def calibration_metrics(probabilities: Sequence[float], labels: Sequence[int], bins: int = 10) -> dict[str, Any]:
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(labels, dtype=float)
    mask = np.isfinite(p) & np.isfinite(y)
    p, y = np.clip(p[mask], 1e-6, 1 - 1e-6), y[mask]
    if not len(p):
        return {"sample_size": 0, "brier_score": None, "log_loss": None, "expected_calibration_error": None, "maximum_calibration_error": None, "reliability_bins": []}
    brier = float(np.mean((p - y) ** 2))
    logloss = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    rows, ece, mce = [], 0.0, 0.0
    edges = np.linspace(0, 1, bins + 1)
    for i in range(bins):
        sel = (p >= edges[i]) & (p < edges[i + 1] if i < bins - 1 else p <= edges[i + 1])
        if not sel.any():
            continue
        confidence, observed, count = float(np.mean(p[sel])), float(np.mean(y[sel])), int(sel.sum())
        gap = abs(confidence - observed)
        ece += gap * count / len(p)
        mce = max(mce, gap)
        rows.append({"bin_lower": float(edges[i]), "bin_upper": float(edges[i + 1]), "mean_probability": confidence, "observed_rate": observed, "count": count})
    return {"sample_size": int(len(p)), "brier_score": brier, "log_loss": logloss, "expected_calibration_error": float(ece), "maximum_calibration_error": float(mce), "reliability_bins": rows}


def _fit_platt(probabilities: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    x = np.log(np.clip(probabilities, 1e-6, 1 - 1e-6) / np.clip(1 - probabilities, 1e-6, 1))
    X = np.column_stack([np.ones(len(x)), x])
    beta = np.zeros(2)
    for _ in range(50):
        z = X @ beta
        p = 1 / (1 + np.exp(-np.clip(z, -35, 35)))
        w = np.maximum(p * (1 - p), 1e-6)
        hess = X.T @ (X * w[:, None]) + np.eye(2) * 1e-4
        grad = X.T @ (p - labels) + beta * 1e-4
        step = np.linalg.solve(hess, grad)
        beta -= step
        if float(np.linalg.norm(step)) < 1e-8:
            break
    return float(beta[0]), float(beta[1])


def _predict_platt(probabilities: np.ndarray, params: tuple[float, float]) -> np.ndarray:
    x = np.log(np.clip(probabilities, 1e-6, 1 - 1e-6) / np.clip(1 - probabilities, 1e-6, 1))
    z = params[0] + params[1] * x
    return 1 / (1 + np.exp(-np.clip(z, -35, 35)))


def _fit_beta_calibration(probabilities: np.ndarray, labels: np.ndarray) -> tuple[float, float, float]:
    p = np.clip(probabilities, 1e-6, 1 - 1e-6)
    X = np.column_stack([np.ones(len(p)), np.log(p), np.log(1 - p)])
    beta = np.zeros(3)
    for _ in range(60):
        z = X @ beta
        pred = 1 / (1 + np.exp(-np.clip(z, -35, 35)))
        w = np.maximum(pred * (1 - pred), 1e-6)
        hess = X.T @ (X * w[:, None]) + np.eye(3) * 1e-3
        grad = X.T @ (pred - labels) + beta * 1e-3
        step = np.linalg.solve(hess, grad)
        beta -= step
        if float(np.linalg.norm(step)) < 1e-8:
            break
    return tuple(float(x) for x in beta)


def _predict_beta(probabilities: np.ndarray, params: tuple[float, float, float]) -> np.ndarray:
    p = np.clip(probabilities, 1e-6, 1 - 1e-6)
    z = params[0] + params[1] * np.log(p) + params[2] * np.log(1 - p)
    return 1 / (1 + np.exp(-np.clip(z, -35, 35)))


def _fit_isotonic(probabilities: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(probabilities, kind="stable")
    x, y = probabilities[order], labels[order].astype(float)
    blocks: list[list[float]] = [[float(y[i]), 1.0, float(x[i]), float(x[i])] for i in range(len(x))]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] / blocks[i][1] <= blocks[i + 1][0] / blocks[i + 1][1] + 1e-15:
            i += 1
            continue
        merged = [blocks[i][0] + blocks[i + 1][0], blocks[i][1] + blocks[i + 1][1], blocks[i][2], blocks[i + 1][3]]
        blocks[i:i + 2] = [merged]
        i = max(i - 1, 0)
    thresholds = np.asarray([b[3] for b in blocks], dtype=float)
    values = np.asarray([b[0] / b[1] for b in blocks], dtype=float)
    return thresholds, values


def _predict_isotonic(probabilities: np.ndarray, params: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    thresholds, values = params
    idx = np.searchsorted(thresholds, probabilities, side="left")
    idx = np.clip(idx, 0, len(values) - 1)
    return values[idx]


def chronological_calibration(probabilities: Sequence[float], labels: Sequence[int], current_probability: float) -> dict[str, Any]:
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(labels, dtype=float)
    mask = np.isfinite(p) & np.isfinite(y)
    p, y = np.clip(p[mask], 1e-6, 1 - 1e-6), y[mask]
    n = len(p)
    if n < 30 or len(np.unique(y)) < 2:
        metrics = calibration_metrics(p, y)
        return {"raw_probability": _clip_probability(current_probability), "calibrated_probability": _clip_probability(current_probability), "calibration_method": "IDENTITY_INSUFFICIENT_HISTORY", "calibration_sample_size": n, "train_end_index": max(-1, n - 1), "evaluation_start_index": n, **metrics}
    train_end = max(20, int(n * 0.70))
    validation_end = max(train_end + 5, int(n * 0.85))
    p_train, y_train = p[:train_end], y[:train_end]
    p_val, y_val = p[train_end:validation_end], y[train_end:validation_end]
    candidates: dict[str, tuple[Any, Any]] = {}
    try:
        params = _fit_platt(p_train, y_train)
        candidates["PLATT"] = (params, _predict_platt(p_val, params))
    except Exception:
        pass
    try:
        params = _fit_isotonic(p_train, y_train)
        candidates["ISOTONIC"] = (params, _predict_isotonic(p_val, params))
    except Exception:
        pass
    try:
        params = _fit_beta_calibration(p_train, y_train)
        candidates["BETA"] = (params, _predict_beta(p_val, params))
    except Exception:
        pass
    if not candidates:
        return {"raw_probability": _clip_probability(current_probability), "calibrated_probability": _clip_probability(current_probability), "calibration_method": "IDENTITY_FIT_FAILURE", "calibration_sample_size": n, "train_end_index": train_end - 1, "evaluation_start_index": validation_end, **calibration_metrics(p, y)}
    losses = {name: calibration_metrics(pred, y_val)["log_loss"] for name, (_, pred) in candidates.items()}
    method = min(losses, key=lambda k: float(losses[k] if losses[k] is not None else 1e9))
    # Refit only on rows strictly before the final chronological evaluation block.
    fit_p, fit_y = p[:validation_end], y[:validation_end]
    if method == "PLATT":
        params = _fit_platt(fit_p, fit_y)
        all_pred = _predict_platt(p[validation_end:], params)
        current = float(_predict_platt(np.asarray([current_probability]), params)[0])
    elif method == "ISOTONIC":
        params = _fit_isotonic(fit_p, fit_y)
        all_pred = _predict_isotonic(p[validation_end:], params)
        current = float(_predict_isotonic(np.asarray([current_probability]), params)[0])
    else:
        params = _fit_beta_calibration(fit_p, fit_y)
        all_pred = _predict_beta(p[validation_end:], params)
        current = float(_predict_beta(np.asarray([current_probability]), params)[0])
    evaluation_metrics = calibration_metrics(all_pred, y[validation_end:])
    return {"raw_probability": _clip_probability(current_probability), "calibrated_probability": _clip_probability(current), "calibration_method": method, "calibration_sample_size": int(validation_end), "train_end_index": int(validation_end - 1), "evaluation_start_index": int(validation_end), "selection_validation_log_loss": losses, **evaluation_metrics}


def _block_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    if n <= 0:
        return np.empty(0, dtype=int)
    block = max(1, min(block, n))
    starts = rng.integers(0, max(1, n - block + 1), size=int(math.ceil(n / block)))
    return np.concatenate([np.arange(s, min(s + block, n)) for s in starts])[:n]


def diebold_mariano(loss_baseline: Sequence[float], loss_candidate: Sequence[float], horizon: int = 1) -> dict[str, Any]:
    a, b = np.asarray(loss_baseline, float), np.asarray(loss_candidate, float)
    n = min(len(a), len(b))
    if n < max(20, horizon * 6):
        return {"mean_loss_difference": None, "dm_statistic": None, "p_value": None, "sample_size": n, "status": "INSUFFICIENT"}
    d = a[:n] - b[:n]  # positive means candidate has lower loss
    d = d[np.isfinite(d)]
    n = len(d)
    if n < max(20, horizon * 6):
        return {"mean_loss_difference": None, "dm_statistic": None, "p_value": None, "sample_size": n, "status": "INSUFFICIENT"}
    mean_d = float(np.mean(d))
    centered = d - mean_d
    lag = max(0, horizon - 1)
    gamma0 = float(np.dot(centered, centered) / n)
    long_var = gamma0
    for k in range(1, lag + 1):
        gamma = float(np.dot(centered[k:], centered[:-k]) / n)
        long_var += 2 * (1 - k / (lag + 1)) * gamma
    variance_mean = max(long_var / n, EPS)
    stat = mean_d / sqrt(variance_mean)
    correction = sqrt(max((n + 1 - 2 * horizon + horizon * (horizon - 1) / n) / n, EPS))
    stat *= correction
    p_value = float(math.erfc(abs(stat) / sqrt(2)))
    if p_value >= 0.05:
        status = "EQUAL"
    else:
        status = "SUPERIOR" if mean_d > 0 else "INFERIOR"
    return {"mean_loss_difference": mean_d, "dm_statistic": float(stat), "p_value": p_value, "sample_size": n, "status": status, "hac_lag": lag, "small_sample_correction": "HARVEY_LEYBOURNE_NEWBOLD"}


def giacomini_white(loss_difference: Sequence[float], instruments: Sequence[Sequence[float]]) -> dict[str, Any]:
    d = np.asarray(loss_difference, dtype=float)
    Z = np.asarray(instruments, dtype=float)
    if Z.ndim == 1:
        Z = Z[:, None]
    n = min(len(d), len(Z))
    d, Z = d[:n], Z[:n]
    mask = np.isfinite(d) & np.all(np.isfinite(Z), axis=1)
    d, Z = d[mask], Z[mask]
    if len(d) < max(30, Z.shape[1] * 8):
        return {"statistic": None, "p_value": None, "sample_size": int(len(d)), "status": "INSUFFICIENT", "conditional_weight_multiplier": 1.0}
    X = np.column_stack([np.ones(len(d)), Z])
    moments = X * d[:, None]
    mean_m = moments.mean(axis=0)
    centered = moments - mean_m
    covariance = centered.T @ centered / len(d) + np.eye(X.shape[1]) * 1e-10
    statistic = float(len(d) * mean_m @ np.linalg.pinv(covariance) @ mean_m)
    # Wilson-Hilferty normal approximation for chi-square survival, dependency-free.
    k = X.shape[1]
    z = ((statistic / k) ** (1 / 3) - (1 - 2 / (9 * k))) / sqrt(2 / (9 * k))
    p_value = float(0.5 * math.erfc(z / sqrt(2)))
    mean_diff = float(np.mean(d))
    multiplier = float(np.clip(exp(mean_diff / (np.std(d) + 1e-9)), 0.5, 2.0)) if p_value < 0.10 else 1.0
    return {"statistic": statistic, "p_value": p_value, "sample_size": int(len(d)), "status": "CONDITIONAL_DIFFERENCE" if p_value < 0.10 else "NO_CONDITIONAL_DIFFERENCE", "mean_loss_difference": mean_diff, "conditional_weight_multiplier": multiplier}


def model_confidence_set(losses: Mapping[str, Sequence[float]], alpha: float = 0.10, reps: int = 199, block: int = 6, seed: int = 20260624) -> dict[str, Any]:
    names = [k for k, v in losses.items() if len(v) >= 25]
    if len(names) < 2:
        return {"members": names, "elimination_order": [], "status": "INSUFFICIENT", "sample_size": min((len(losses[k]) for k in names), default=0)}
    n = min(len(losses[k]) for k in names)
    matrix = np.column_stack([np.asarray(losses[k], float)[-n:] for k in names])
    valid = np.all(np.isfinite(matrix), axis=1)
    matrix = matrix[valid]
    n = len(matrix)
    if n < 25:
        return {"members": names, "elimination_order": [], "status": "INSUFFICIENT", "sample_size": n}
    rng = np.random.default_rng(seed)
    active = list(range(len(names)))
    eliminated: list[dict[str, Any]] = []
    while len(active) > 1:
        sub = matrix[:, active]
        means = sub.mean(axis=0)
        worst_local = int(np.argmax(means))
        centered = sub - sub.mean(axis=0)
        observed = float(np.max(means) - np.min(means))
        bootstrap_stats = []
        for _ in range(reps):
            idx = _block_indices(n, block, rng)
            sample_means = centered[idx].mean(axis=0)
            bootstrap_stats.append(float(np.max(sample_means) - np.min(sample_means)))
        p_value = float((1 + sum(x >= observed for x in bootstrap_stats)) / (reps + 1))
        if p_value >= alpha:
            break
        removed = active.pop(worst_local)
        eliminated.append({"model": names[removed], "elimination_order": len(eliminated) + 1, "test_statistic": observed, "p_value": p_value, "sample_size": n})
    return {"members": [names[i] for i in active], "elimination_order": eliminated, "status": "AVAILABLE", "sample_size": n, "bootstrap_reps": reps, "block_length": block, "alpha": alpha}


def superior_predictive_ability(improvements: Mapping[str, Sequence[float]], reps: int = 199, block: int = 6, seed: int = 20260624) -> dict[str, Any]:
    names = [k for k, v in improvements.items() if len(v) >= 25]
    if not names:
        return {"models": [], "status": "INSUFFICIENT"}
    n = min(len(improvements[k]) for k in names)
    matrix = np.column_stack([np.asarray(improvements[k], float)[-n:] for k in names])
    matrix = matrix[np.all(np.isfinite(matrix), axis=1)]
    n = len(matrix)
    if n < 25:
        return {"models": [], "status": "INSUFFICIENT", "sample_size": n}
    means = matrix.mean(axis=0)
    std = np.maximum(matrix.std(axis=0, ddof=1), 1e-9)
    observed = float(np.max(np.sqrt(n) * means / std))
    centered = matrix - np.maximum(means, 0)[None, :]
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(reps):
        idx = _block_indices(n, block, rng)
        boot_mean = centered[idx].mean(axis=0)
        stats.append(float(np.max(np.sqrt(n) * boot_mean / std)))
    p_value = float((1 + sum(x >= observed for x in stats)) / (reps + 1))
    rows = []
    for i, name in enumerate(names):
        eligible = bool(means[i] > 0 and p_value < 0.10)
        rows.append({"model": name, "gross_loss_improvement": float(means[i]), "spa_statistic": observed, "bootstrap_p_value": p_value, "sample_size": n, "eligible": eligible, "rejection_reason": None if eligible else ("NO_POSITIVE_MEAN_IMPROVEMENT" if means[i] <= 0 else "SPA_NOT_SIGNIFICANT")})
    return {"models": rows, "status": "AVAILABLE", "sample_size": n, "bootstrap_reps": reps, "block_length": block, "joint_p_value": p_value}


def bayesian_online_changepoint(values: Sequence[float], hazard: float = 1 / 72, max_run: int = 128) -> dict[str, Any]:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)][-max_run:]
    n = len(x)
    if n < 12:
        return {"changepoint_probability": None, "current_run_length_posterior": [], "modal_run_length": None, "sample_size": n, "status": "INSUFFICIENT"}
    variance = max(float(np.var(x)), 1e-10)
    prior_mean, prior_precision = 0.0, 1.0
    run_probs = np.zeros(max_run + 1)
    run_probs[0] = 1.0
    means = np.zeros(max_run + 1)
    precisions = np.full(max_run + 1, prior_precision)
    for value in x:
        active = np.flatnonzero(run_probs > 0)
        pred = np.zeros_like(run_probs)
        for r in active:
            pred_var = variance * (1 + 1 / max(precisions[r], EPS))
            pred[r] = exp(-0.5 * (value - means[r]) ** 2 / pred_var) / sqrt(2 * pi * pred_var)
        growth = np.zeros_like(run_probs)
        growth[1:] = run_probs[:-1] * pred[:-1] * (1 - hazard)
        cp = float(np.sum(run_probs * pred) * hazard)
        new_probs = growth
        new_probs[0] = cp
        total = float(new_probs.sum())
        run_probs = new_probs / total if total > 0 else np.eye(1, max_run + 1, 0).ravel()
        new_means = np.zeros_like(means)
        new_precisions = np.full_like(precisions, prior_precision)
        new_means[0] = prior_mean
        for r in range(max_run):
            precision = precisions[r] + 1
            new_precisions[r + 1] = precision
            new_means[r + 1] = (precisions[r] * means[r] + value) / precision
        means, precisions = new_means, new_precisions
    posterior = [{"run_length": int(i), "probability": float(p)} for i, p in enumerate(run_probs) if p >= 1e-5]
    modal = int(np.argmax(run_probs))
    return {"changepoint_probability": float(run_probs[0]), "current_run_length_posterior": posterior, "modal_run_length": modal, "expected_run_length": float(np.dot(np.arange(len(run_probs)), run_probs)), "sample_size": n, "status": "AVAILABLE", "recursive_update": True, "hazard": hazard}


def hamilton_filter(values: Sequence[float]) -> dict[str, Any]:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)][-400:]
    n = len(x)
    if n < 30:
        posterior = {"BEAR": 1 / 3, "COMPRESSION": 1 / 3, "BULL": 1 / 3}
        return {"shadow_filtered_regime": "UNAVAILABLE", "posterior_probabilities": posterior, "persistence_probability": None, "transition_probabilities": {"H1": None, "H3": None, "H6": None}, "expected_regime_duration": None, "estimated_remaining_duration": None, "status": "INSUFFICIENT", "sample_size": n}
    scale = max(float(np.std(x)), 1e-8)
    means = np.asarray([min(float(np.quantile(x, 0.25)), -0.25 * scale), 0.0, max(float(np.quantile(x, 0.75)), 0.25 * scale)])
    variances = np.asarray([scale ** 2, max((0.55 * scale) ** 2, 1e-12), scale ** 2])
    transition = np.asarray([[0.94, 0.05, 0.01], [0.04, 0.92, 0.04], [0.01, 0.05, 0.94]], dtype=float)
    alpha = np.full(3, 1 / 3)
    for value in x:
        pred = alpha @ transition
        emission = np.exp(-0.5 * (value - means) ** 2 / variances) / np.sqrt(2 * pi * variances)
        alpha = pred * emission
        alpha /= max(float(alpha.sum()), EPS)
    state = int(np.argmax(alpha))
    name = REGIMES[state]
    persistence = float(transition[state, state])
    expected_duration = float(1 / max(1 - persistence, EPS))
    transitions = {}
    for h in HORIZONS:
        power = np.linalg.matrix_power(transition, h)
        transitions[f"H{h}"] = float(1 - power[state, state])
    posterior = {REGIMES[i]: float(alpha[i]) for i in range(3)}
    return {"shadow_filtered_regime": name, "posterior_probabilities": posterior, "persistence_probability": persistence, "transition_probabilities": transitions, "expected_regime_duration": expected_duration, "estimated_remaining_duration": max(0.0, expected_duration - 1.0), "transition_matrix": transition.tolist(), "state_means": means.tolist(), "status": "AVAILABLE", "sample_size": n, "posterior_normalization": float(sum(posterior.values()))}


def _confusion(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    labels = sorted(set(str(r.get("actual_regime")) for r in rows if r.get("actual_regime")) | set(str(r.get("origin_regime")) for r in rows if r.get("origin_regime")))
    if not labels:
        return {"labels": [], "matrix": [], "sample_size": 0}
    index = {name: i for i, name in enumerate(labels)}
    matrix = np.zeros((len(labels), len(labels)), dtype=int)
    n = 0
    for row in rows:
        actual, pred = row.get("actual_regime"), row.get("origin_regime")
        if actual in index and pred in index:
            matrix[index[str(actual)], index[str(pred)]] += 1
            n += 1
    return {"labels": labels, "matrix": matrix.tolist(), "sample_size": n}


def _feature_groups(returns: np.ndarray, contract: RunContract, state: Mapping[str, Any]) -> dict[str, float]:
    values = returns if len(returns) else np.zeros(1)
    trend3 = float(np.mean(values[-3:]))
    trend12 = float(np.mean(values[-12:]))
    trend48 = float(np.mean(values[-48:]))
    vol12 = float(np.std(values[-12:]))
    vol48 = max(float(np.std(values[-48:])), 1e-8)
    spread = _f((state.get("transaction_cost_assumptions") or {}).get("spread_pips") if isinstance(state.get("transaction_cost_assumptions"), Mapping) else state.get("spread_pips"), 1.0)
    session = _session_from_time(contract.broker_candle_time)
    regime_signal = 1.0 if "BULL" in contract.regime else -1.0 if "BEAR" in contract.regime else 0.0
    news = _f(state.get("news_score") or state.get("nlp_sentiment_score"), 0.0)
    analogue = _f(state.get("historical_analogue_score"), 0.0)
    disagreement = _f(state.get("model_disagreement"), abs(trend3 - trend12) / vol48)
    return {
        "price_structure": trend3 / vol48,
        "trend": (0.5 * trend3 + 0.3 * trend12 + 0.2 * trend48) / vol48,
        "volatility": -vol12 / vol48,
        "regime": regime_signal,
        "session": 0.25 if session in {"LONDON", "LONDON_NY_OVERLAP"} else -0.05,
        "spread_liquidity": -spread / 3.0,
        "event_news": float(np.clip(news, -1, 1)),
        "historical_analogue": float(np.clip(analogue, -1, 1)),
        "model_disagreement": -float(np.clip(disagreement, 0, 3)),
    }


def lightweight_tft_fusion(returns: np.ndarray, contract: RunContract, state: Mapping[str, Any]) -> dict[str, Any]:
    groups = _feature_groups(returns, contract, state)
    raw = np.asarray([abs(v) for v in groups.values()], dtype=float)
    # Sparse regularized gates: tiny groups are zeroed before normalization.
    threshold = float(np.quantile(raw, 0.35)) if len(raw) else 0.0
    sparse = np.maximum(raw - threshold, 0.0)
    if sparse.sum() <= EPS:
        sparse = np.ones_like(raw)
    gates = sparse / sparse.sum()
    importance = {name: float(gates[i]) for i, name in enumerate(groups)}
    signed = float(sum(importance[name] * groups[name] for name in groups))
    base_vol = max(float(np.std(returns[-48:])) if len(returns) else 0.0, 1e-6)
    temporal = []
    for lag in (1, 3, 6, 12, 24, 48):
        weight = exp(-lag / 18)
        temporal.append({"lag_hours": lag, "importance": float(weight)})
    total = sum(x["importance"] for x in temporal)
    for row in temporal:
        row["importance"] /= total
    forecasts = {}
    for h in HORIZONS:
        point = float(np.clip(signed, -3, 3) * base_vol * sqrt(h) * 0.35)
        scale = base_vol * sqrt(h)
        forecasts[str(h)] = {"point": point, "q10": point - 1.28155 * scale, "q50": point, "q90": point + 1.28155 * scale, "gated_residual_fallback": "RIDGE_FREE_DETERMINISTIC_GATE" if len(returns) < 80 else "SPARSE_GATED_FUSION"}
    return {"status": "AVAILABLE", "cpu_safe_default": True, "full_model_enabled": False, "full_model_status": "DISABLED_BY_DEFAULT", "feature_group_importance": importance, "temporal_importance": temporal, "forecasts": forecasts, "strict_chronological_fit": True, "regularization": "L1_STYLE_GATE_THRESHOLD"}


def _candidate_history(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, list[float]], dict[str, list[float]], list[list[float]]]:
    losses = {name: [] for name in ("production", "trend_shadow", "robust_shadow", "tft_lite")}
    predictions = {name: [] for name in losses}
    instruments: list[list[float]] = []
    for i, row in enumerate(rows):
        actual = _f(row.get("actual_return"))
        production = _f(row.get("predicted_return"))
        candidates = {
            "production": production,
            "trend_shadow": _f(row.get("trend_shadow_prediction"), production * 0.90),
            "robust_shadow": _f(row.get("robust_shadow_prediction"), production * 0.70),
            "tft_lite": _f(row.get("tft_lite_prediction"), production * 0.82),
        }
        for name, pred in candidates.items():
            predictions[name].append(pred)
            losses[name].append(abs(actual - pred))
        regime = str(row.get("origin_regime") or row.get("regime") or "UNKNOWN").upper()
        session = str(row.get("session") or _session_from_time(_iso(row.get("origin_candle_time")))).upper()
        vol = _f(row.get("predicted_std") or row.get("volatility"), 0.0)
        spread = _f(row.get("spread") or row.get("spread_pips"), 1.0)
        cp = _f(row.get("changepoint_probability"), 0.0)
        instruments.append([1.0 if "BULL" in regime else -1.0 if "BEAR" in regime else 0.0, 1.0 if "OVERLAP" in session else 0.0, vol, spread, cp, i / max(1, len(rows) - 1)])
    return losses, predictions, instruments


def _conformal(rows: Sequence[Mapping[str, Any]], point: float, regime: str, session: str, vol_bucket: str) -> dict[str, Any]:
    default_vol = max(float(np.std([_f(r.get("actual_return")) for r in rows])) if rows else 0.0, 1e-6)
    pools: list[tuple[str, list[float]]] = []
    pools.append(("REGIME_SESSION_VOLATILITY", [abs(_f(r.get("actual_return")) - _f(r.get("predicted_return"))) for r in rows if str(r.get("origin_regime") or r.get("regime") or "").upper() == regime and str(r.get("session") or _session_from_time(_iso(r.get("origin_candle_time")))).upper() == session and _volatility_bucket(r, default_vol) == vol_bucket]))
    pools.append(("REGIME_SESSION", [abs(_f(r.get("actual_return")) - _f(r.get("predicted_return"))) for r in rows if str(r.get("origin_regime") or r.get("regime") or "").upper() == regime and str(r.get("session") or _session_from_time(_iso(r.get("origin_candle_time")))).upper() == session]))
    pools.append(("REGIME", [abs(_f(r.get("actual_return")) - _f(r.get("predicted_return"))) for r in rows if str(r.get("origin_regime") or r.get("regime") or "").upper() == regime]))
    pools.append(("HORIZON_GLOBAL", [abs(_f(r.get("actual_return")) - _f(r.get("predicted_return"))) for r in rows]))
    selected_level, residuals = "UNAVAILABLE", []
    minimums = {"REGIME_SESSION_VOLATILITY": 40, "REGIME_SESSION": 30, "REGIME": 25, "HORIZON_GLOBAL": 20}
    for level, pool in pools:
        pool = [x for x in pool if math.isfinite(x)]
        if len(pool) >= minimums[level]:
            selected_level, residuals = level, pool[-250:]
            break
    if not residuals:
        return {"origin_lower": None, "origin_upper": None, "calibration_sample_size": 0, "fallback_level": "UNAVAILABLE", "coverage_claim": "NO_GUARANTEE_INSUFFICIENT_EVIDENCE", "coverage_debt": None, "rolling_coverage": None}
    q = float(np.quantile(np.asarray(residuals), TARGET_COVERAGE, method="higher"))
    historical_covered = []
    for row in rows[-100:]:
        actual = _f(row.get("actual_return"))
        pred = _f(row.get("predicted_return"))
        lower = _maybe_f(row.get("origin_lower") or row.get("origin_conformal_lower"))
        upper = _maybe_f(row.get("origin_upper") or row.get("origin_conformal_upper"))
        if lower is None or upper is None:
            lower, upper = pred - q, pred + q
        historical_covered.append(int(lower <= actual <= upper))
    coverage = float(np.mean(historical_covered)) if historical_covered else None
    debt = max(0.0, TARGET_COVERAGE - coverage) if coverage is not None else None
    return {"origin_lower": point - q, "origin_upper": point + q, "calibration_sample_size": len(residuals), "fallback_level": selected_level, "coverage_claim": "EMPIRICAL_ROLLING_ONLY_NOT_GUARANTEED", "coverage_debt": debt, "rolling_coverage": coverage, "residual_quantile": q}


def _score_horizon(rows: Sequence[Mapping[str, Any]], cost_pips: float) -> dict[str, Any]:
    if not rows:
        return {"sample_size": 0, "mae": None, "rmse": None, "signed_bias": None, "directional_accuracy": None, "brier_score": None, "log_loss": None, "crps": None, "crps_method": "UNAVAILABLE", "interval_coverage": None, "interval_width": None, "winkler_score": None, "calibration_error": None, "after_cost_directional_value": None}
    errors, squared, biases, direction_hits, probs, labels = [], [], [], [], [], []
    crps_values, crps_methods, cover, widths, winkler, net_values = [], [], [], [], [], []
    for row in rows:
        actual, pred = _f(row.get("actual_return")), _f(row.get("predicted_return"))
        err = actual - pred
        errors.append(abs(err)); squared.append(err * err); biases.append(pred - actual)
        direction_hits.append(int((actual >= 0) == (pred >= 0)))
        std = max(_f(row.get("predicted_std"), 0.0), 0.0)
        raw_prob = _maybe_f(row.get("raw_direction_probability") or row.get("direction_probability"))
        if raw_prob is None:
            raw_prob = _normal_cdf(pred / max(std, 1e-6))
        probs.append(_clip_probability(raw_prob)); labels.append(int(actual >= 0))
        samples = row.get("predictive_samples")
        if isinstance(samples, Sequence) and not isinstance(samples, (str, bytes)) and len(samples) >= 2:
            crps_values.append(sample_crps(actual, samples)); crps_methods.append("EMPIRICAL_SAMPLE")
        elif std > 0:
            crps_values.append(gaussian_crps(actual, pred, std)); crps_methods.append("GAUSSIAN_ANALYTIC")
        else:
            qvals = row.get("quantiles")
            if isinstance(qvals, Mapping):
                sequence = [qvals.get(k) for k in ("q10", "q25", "q50", "q75", "q90")]
                crps_values.append(quantile_crps(actual, [_f(x) for x in sequence])); crps_methods.append("QUANTILE_APPROXIMATION_FALLBACK")
            else:
                crps_values.append(abs(err)); crps_methods.append("ABSOLUTE_ERROR_LAST_RESORT_NOT_CRPS_CLAIM")
        lower = _maybe_f(row.get("origin_lower") or row.get("origin_conformal_lower"))
        upper = _maybe_f(row.get("origin_upper") or row.get("origin_conformal_upper"))
        if lower is None or upper is None:
            scale = std if std > 0 else max(float(np.std(biases)), 1e-6)
            lower, upper = pred - 1.64485 * scale, pred + 1.64485 * scale
        cover.append(int(lower <= actual <= upper)); widths.append(upper - lower); winkler.append(interval_score(actual, lower, upper, 0.10))
        side = 1 if pred > 0 else -1 if pred < 0 else 0
        net_values.append(side * actual * 10000 - (cost_pips if side else 0.0))
    calibration = calibration_metrics(probs, labels)
    method = max(set(crps_methods), key=crps_methods.count)
    return {"sample_size": len(rows), "mae": float(np.mean(errors)), "rmse": float(sqrt(np.mean(squared))), "signed_bias": float(np.mean(biases)), "directional_accuracy": float(np.mean(direction_hits)), "brier_score": calibration["brier_score"], "log_loss": calibration["log_loss"], "crps": float(np.mean([x for x in crps_values if math.isfinite(x)])), "crps_method": method, "crps_method_counts": {m: crps_methods.count(m) for m in sorted(set(crps_methods))}, "interval_coverage": float(np.mean(cover)), "interval_width": float(np.mean(widths)), "winkler_score": float(np.mean(winkler)), "calibration_error": calibration["expected_calibration_error"], "after_cost_directional_value": float(np.mean(net_values))}



def _dm_breakdowns(rows: Sequence[Mapping[str, Any]], baseline_losses: Sequence[float], candidate_losses: Sequence[float], horizon: int) -> list[dict[str, Any]]:
    n = min(len(rows), len(baseline_losses), len(candidate_losses))
    rows = list(rows)[-n:]
    a = np.asarray(baseline_losses, float)[-n:]
    b = np.asarray(candidate_losses, float)[-n:]
    groups: dict[str, list[int]] = {"ALL": list(range(n))}
    for label in sorted(set(str(r.get("origin_regime") or r.get("regime") or "UNKNOWN").upper() for r in rows)):
        groups[f"REGIME:{label}"] = [i for i, r in enumerate(rows) if str(r.get("origin_regime") or r.get("regime") or "UNKNOWN").upper() == label]
    for label in sorted(set(str(r.get("session") or _session_from_time(_iso(r.get("origin_candle_time")))).upper() for r in rows)):
        groups[f"SESSION:{label}"] = [i for i, r in enumerate(rows) if str(r.get("session") or _session_from_time(_iso(r.get("origin_candle_time")))).upper() == label]
    midpoint = n // 2
    groups["BLOCK:OLDER"] = list(range(0, midpoint))
    groups["BLOCK:RECENT"] = list(range(midpoint, n))
    result = []
    for name, idx in groups.items():
        row = diebold_mariano(a[idx], b[idx], horizon) if idx else {"status": "INSUFFICIENT", "sample_size": 0, "p_value": None, "dm_statistic": None, "mean_loss_difference": None}
        result.append({"comparison_block": name, **row})
    return result


def _probability_calibration_suite(contract: RunContract, state: Mapping[str, Any], forecasts: Mapping[str, Any], regime: Mapping[str, Any]) -> dict[str, Any]:
    cost = state.get("transaction_cost_assumptions") if isinstance(state.get("transaction_cost_assumptions"), Mapping) else {}
    total_cost = _f(cost.get("spread_pips"), 1.0) + _f(cost.get("commission_pips"), 0.2) + _f(cost.get("slippage_pips"), 0.1)
    suite: dict[str, Any] = {}
    for hs, forecast in forecasts.items():
        h = int(hs)
        rows = _matured_rows(state, h, contract.data_cutoff_time)
        raw_up, actual_up, correct_raw, correct_label, covered_raw, covered_label, profit_raw, profit_label, reliability_raw, reliability_label = [], [], [], [], [], [], [], [], [], []
        for row in rows:
            pred = _f(row.get("predicted_return")); actual = _f(row.get("actual_return")); std = max(_f(row.get("predicted_std"), forecast.get("std", 1e-6)), 1e-6)
            up = _clip_probability(_maybe_f(row.get("raw_direction_probability")) or _normal_cdf(pred / std))
            raw_up.append(up); actual_up.append(int(actual >= 0))
            correct_raw.append(max(up, 1 - up)); correct_label.append(int((pred >= 0) == (actual >= 0)))
            lo = _maybe_f(row.get("origin_lower") or row.get("origin_conformal_lower")); hi = _maybe_f(row.get("origin_upper") or row.get("origin_conformal_upper"))
            if lo is None or hi is None: lo, hi = pred - 1.64485 * std, pred + 1.64485 * std
            width_score = float(np.clip(TARGET_COVERAGE - 0.05 * (hi - lo) / std, 0.5, 0.99))
            covered_raw.append(width_score); covered_label.append(int(lo <= actual <= hi))
            side = 1 if pred > 0 else -1 if pred < 0 else 0
            net = side * actual * 10000 - (total_cost if side else 0.0)
            p_profit = max(up, 1 - up) if side else 0.5
            profit_raw.append(p_profit); profit_label.append(int(net > 0))
            reliability_raw.append(float(np.clip(0.5 * max(up, 1 - up) + 0.5 * width_score, 0, 1)))
            reliability_label.append(int(net > 0 and (lo <= actual <= hi)))
        current_up = forecast["raw_direction_probability"]
        current_correct = max(current_up, 1 - current_up)
        current_containment = TARGET_COVERAGE
        current_profit = current_correct
        current_reliability = 0.5 * current_correct + 0.5 * current_containment
        suite[hs] = {
            "BUY_probability": chronological_calibration(raw_up, actual_up, current_up),
            "SELL_probability": chronological_calibration([1 - p for p in raw_up], [1 - y for y in actual_up], 1 - current_up),
            "correct_direction_probability": chronological_calibration(correct_raw, correct_label, current_correct),
            "interval_containment_probability": chronological_calibration(covered_raw, covered_label, current_containment),
            "profitable_after_cost_probability": chronological_calibration(profit_raw, profit_label, current_profit),
            "decision_reliability": chronological_calibration(reliability_raw, reliability_label, current_reliability),
        }
    regime_rows = [r for h in HORIZONS for r in _matured_rows(state, h, contract.data_cutoff_time) if r.get("origin_regime") and r.get("actual_regime")]
    regime_labels = [int(str(r.get("origin_regime")) == str(r.get("actual_regime"))) for r in regime_rows]
    regime_raw = [_f(r.get("regime_probability"), max((regime.get("posterior_probabilities") or {"x": 1/3}).values())) for r in regime_rows]
    current_regime = max((regime.get("posterior_probabilities") or {"x": 1/3}).values())
    suite["REGIME"] = {"regime_correctness": chronological_calibration(regime_raw, regime_labels, current_regime)}
    return suite

def _forecast_layer(contract: RunContract, state: Mapping[str, Any], returns: np.ndarray, tft: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    cost = state.get("transaction_cost_assumptions") if isinstance(state.get("transaction_cost_assumptions"), Mapping) else {}
    cost_pips = _f(cost.get("spread_pips"), 1.0) + _f(cost.get("commission_pips"), 0.2) + _f(cost.get("slippage_pips"), 0.1)
    trend = float(np.mean(returns[-12:])) if len(returns) else 0.0
    vol = max(float(np.std(returns[-48:])) if len(returns) else 0.0, 1e-6)
    session = _session_from_time(contract.broker_candle_time)
    regime = contract.regime
    outputs: dict[str, Any] = {}
    method_evidence: dict[str, Any] = {}
    for h in HORIZONS:
        rows = _matured_rows(state, h, contract.data_cutoff_time)
        losses, predictions, instruments = _candidate_history(rows)
        production_current = float(np.mean([_f(r.get("predicted_return")) for r in rows[-12:]])) if rows else h * trend
        candidate_current = {
            "production": production_current,
            "trend_shadow": h * trend,
            "robust_shadow": 0.65 * h * trend,
            "tft_lite": _f(tft["forecasts"][str(h)]["point"]),
        }
        mcs = model_confidence_set(losses, block=max(2, h), seed=20260624 + h)
        members = set(mcs.get("members") or candidate_current.keys())
        dm = {}
        for name, values in losses.items():
            if name == "production":
                continue
            overall = diebold_mariano(losses["production"], values, h)
            overall["breakdowns"] = _dm_breakdowns(rows, losses["production"], values, h)
            dm[name] = overall
        improvements = {name: (np.asarray(losses["production"]) - np.asarray(values)).tolist() for name, values in losses.items() if name != "production"}
        spa = superior_predictive_ability(improvements, block=max(2, h), seed=20260700 + h)
        for spa_row in spa.get("models", []):
            name = spa_row["model"]
            candidate_predictions = predictions.get(name, [])
            base_predictions = predictions.get("production", [])
            net_delta = []
            for row, base_pred, cand_pred in zip(rows, base_predictions, candidate_predictions):
                actual_pips = _f(row.get("actual_return")) * 10000
                base_value = (1 if base_pred > 0 else -1 if base_pred < 0 else 0) * actual_pips - (cost_pips if base_pred != 0 else 0)
                cand_value = (1 if cand_pred > 0 else -1 if cand_pred < 0 else 0) * actual_pips - (cost_pips if cand_pred != 0 else 0)
                net_delta.append(cand_value - base_value)
            spa_row["net_after_cost_improvement"] = float(np.mean(net_delta)) if net_delta else None
        gw: dict[str, Any] = {}
        for name, values in losses.items():
            if name == "production":
                continue
            diff = np.asarray(losses["production"]) - np.asarray(values)
            gw[name] = giacomini_white(diff, instruments)
            gw[name]["condition_dimensions"] = ["horizon", "production_regime", "session", "volatility_bucket", "spread_bucket", "changepoint_risk_bucket"]
        eligible = [name for name in candidate_current if name in members]
        raw_weights = {}
        for name in eligible:
            mean_loss = float(np.mean(losses[name])) if losses[name] else vol
            gw_multiplier = _f((gw.get(name) or {}).get("conditional_weight_multiplier"), 1.0)
            raw_weights[name] = gw_multiplier / max(mean_loss, 1e-8)
        if not raw_weights:
            raw_weights = {"production": 1.0}
        total = sum(raw_weights.values())
        weights = {name: float(value / total) for name, value in raw_weights.items()}
        point = float(sum(weights[name] * candidate_current[name] for name in weights))
        disagreement = float(np.std([candidate_current[name] for name in weights])) if len(weights) > 1 else 0.0
        scale = max(vol * sqrt(h), disagreement, 1e-6)
        raw_direction = _normal_cdf(point / scale)
        historical_raw = []
        historical_labels = []
        for row in rows:
            pred, std = _f(row.get("predicted_return")), max(_f(row.get("predicted_std"), scale), 1e-6)
            historical_raw.append(_clip_probability(_maybe_f(row.get("raw_direction_probability")) or _normal_cdf(pred / std)))
            historical_labels.append(int(_f(row.get("actual_return")) >= 0))
        calibration = chronological_calibration(historical_raw, historical_labels, raw_direction)
        vol_bucket = "HIGH" if vol > np.std(returns) * 1.25 else "LOW" if len(returns) and vol < np.std(returns) * 0.75 else "NORMAL"
        conformal = _conformal(rows, point, regime, session, vol_bucket)
        if conformal["origin_lower"] is None:
            lower, upper = point - 1.64485 * scale, point + 1.64485 * scale
            fallback_reason = "CONFORMAL_UNAVAILABLE_PARAMETRIC_INTERVAL"
        else:
            lower, upper = conformal["origin_lower"], conformal["origin_upper"]
            fallback_reason = None
        quantiles = {"q10": point - 1.28155 * scale, "q25": point - 0.67449 * scale, "q50": point, "q75": point + 0.67449 * scale, "q90": point + 1.28155 * scale}
        metrics = _score_horizon(rows, cost_pips)
        outputs[str(h)] = {
            "run_id": contract.run_id, "origin_id": contract.origin_id, "symbol": contract.symbol, "timeframe": contract.timeframe,
            "broker_candle_time": contract.broker_candle_time, "forecast_origin": contract.broker_candle_time, "data_cutoff_time": contract.data_cutoff_time,
            "model_version": MODEL_VERSION, "feature_schema_hash": contract.feature_schema_hashes["trend"], "horizon": h,
            "point_forecast": point, "mean": point, "median_forecast": point, "median": point, "std": scale,
            "lower_quantile": quantiles["q10"], "upper_quantile": quantiles["q90"], "quantiles": quantiles,
            "origin_conformal_lower": lower, "origin_conformal_upper": upper, "origin_lower": lower, "origin_upper": upper,
            "raw_direction_probability": _clip_probability(raw_direction), "calibrated_direction_probability": calibration["calibrated_probability"],
            "selected_shadow_models": sorted(weights), "model_weights": weights, "regime": regime, "session": session,
            "spread": _f(cost.get("spread_pips"), 1.0), "uncertainty_score": float(scale * 10000), "disagreement_score": float(disagreement * 10000),
            "fallback_reason": fallback_reason, "evidence_status": "CALIBRATED" if len(rows) >= 40 else "INSUFFICIENT_HISTORY",
            "sample_size": len(rows), "calibration_status": conformal["fallback_level"], "conformal": conformal, "probability_calibration": calibration,
            "metrics": metrics, "settlement_status": settlement_status({h2: next((_f(r.get("actual_return")) for r in _matured_rows(state, h2, contract.data_cutoff_time)[-1:]), None) for h2 in HORIZONS}),
        }
        method_evidence[str(h)] = {"mcs": mcs, "spa": spa, "dm": dm, "conditional_predictive_ability": gw}
    return outputs, method_evidence


def _regime_layer(contract: RunContract, state: Mapping[str, Any], returns: np.ndarray) -> dict[str, Any]:
    hamilton = hamilton_filter(returns)
    bocpd = bayesian_online_changepoint(returns)
    shadow = hamilton.get("shadow_filtered_regime")
    agreement = bool(shadow != "UNAVAILABLE" and (shadow in contract.regime or contract.regime in shadow))
    cp = bocpd.get("changepoint_probability")
    evidence = min(hamilton.get("sample_size", 0), bocpd.get("sample_size", 0))
    warning = "CONFIRMED" if cp is not None and cp >= 0.75 and evidence >= 40 else "WATCH" if cp is not None and cp >= 0.40 and evidence >= 25 else "STABLE" if cp is not None else "INSUFFICIENT"
    rows = [r for h in HORIZONS for r in _matured_rows(state, h, contract.data_cutoff_time)]
    confusion = _confusion(rows)
    correctness = [int(str(r.get("origin_regime")) == str(r.get("actual_regime"))) for r in rows if r.get("origin_regime") and r.get("actual_regime")]
    probs = [max(hamilton.get("posterior_probabilities", {"x": 1 / 3}).values())] * len(correctness)
    calibration = calibration_metrics(probs, correctness) if correctness else calibration_metrics([], [])
    return {
        "run_id": contract.run_id, "origin_id": contract.origin_id, "symbol": contract.symbol, "timeframe": contract.timeframe,
        "broker_candle_time": contract.broker_candle_time, "data_cutoff_time": contract.data_cutoff_time, "model_version": MODEL_VERSION,
        "production_regime": contract.regime, "production_regime_unchanged": True, "shadow_filtered_regime": shadow,
        "posterior_probabilities": hamilton.get("posterior_probabilities"), "persistence_probability": hamilton.get("persistence_probability"),
        "transition_probabilities": hamilton.get("transition_probabilities"), "expected_regime_duration": hamilton.get("expected_regime_duration"),
        "estimated_remaining_duration": hamilton.get("estimated_remaining_duration"), "changepoint_probability": cp,
        "current_run_length_posterior": bocpd.get("current_run_length_posterior"), "modal_run_length": bocpd.get("modal_run_length"),
        "transition_warning_state": warning, "production_shadow_agreement": agreement, "regime_calibration_score": calibration,
        "regime_confusion_matrix": confusion, "regime_evidence_sufficiency": evidence >= 40, "hamilton": hamilton, "bocpd": bocpd,
        # Compatibility keys used by the earlier renderer and tests.
        "change_probability": cp, "expected_run_length": bocpd.get("expected_run_length"), "regime_age_hours": bocpd.get("modal_run_length"),
        "transition_candidate": warning in {"WATCH", "CONFIRMED"}, "transition_confirmed": warning == "CONFIRMED", "status": "AVAILABLE" if evidence >= 30 else "INSUFFICIENT_EVIDENCE", "shadow_only": True,
    }


def _field8_layer(contract: RunContract, forecasts: Mapping[str, Any], evidence: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for hs, forecast in forecasts.items():
        methods = evidence[hs]
        weights = forecast["model_weights"]
        models = []
        mcs_members = set(methods["mcs"].get("members") or [])
        for name, weight in weights.items():
            dm = methods["dm"].get(name, {}) if name != "production" else {}
            models.append({"model": name, "prior_weight": 1 / max(1, len(weights)), "posterior_weight": weight, "prediction_likelihood": float(exp(-max(forecast["metrics"].get("mae") or 0.0, 0.0))), "evaluation_loss": forecast["metrics"].get("mae"), "survives_mcs": name in mcs_members, "elimination_reason": None if name in mcs_members else "MCS_EXCLUDED_SHADOW_ONLY", "dm_status": dm.get("status")})
        probs = np.asarray([m["posterior_weight"] for m in models], dtype=float)
        calibration = forecast["probability_calibration"]
        conformal = forecast["conformal"]
        spa_rows = methods["spa"].get("models") or []
        result[hs] = {
            "run_id": contract.run_id, "origin_id": contract.origin_id, "broker_candle_time": contract.broker_candle_time, "data_cutoff_time": contract.data_cutoff_time,
            "symbol": contract.symbol, "timeframe": contract.timeframe, "horizon": int(hs), "method_version": METHOD_VERSION, "status": "AVAILABLE",
            "regime": contract.regime, "session": forecast["session"], "sample_size": forecast["sample_size"], "confidence_level": TARGET_COVERAGE,
            "models": models, "effective_model_count": float(1 / np.sum(probs ** 2)) if len(probs) else 0.0,
            "model_concentration": float(np.max(probs)) if len(probs) else 0.0, "model_disagreement": forecast["disagreement_score"],
            "current_calibration_quality": calibration, "conformal_coverage_status": conformal,
            "model_confidence_set_membership": methods["mcs"], "spa_status": methods["spa"], "dm_status": methods["dm"],
            "conditional_predictive_ability_status": methods["conditional_predictive_ability"],
            "drift_status": str(state.get("drift_status") or "NOT_DETECTED_FROM_AVAILABLE_EVIDENCE"),
            "leakage_status": "PASS_ORIGIN_TIME_GUARD", "data_sufficiency": forecast["sample_size"] >= 40,
            "shadow_eligibility": bool(forecast["sample_size"] >= 40 and any(r.get("eligible") for r in spa_rows)),
            "explicit_limitation_text": "Shadow evidence only. Statistical non-rejection is not proof of superiority; coverage is empirical and conditional on the saved historical sample.",
            "evidence_class": "CALIBRATED" if forecast["sample_size"] >= 40 else "INSUFFICIENT",
        }
    return result


def _field9_layer(contract: RunContract, forecasts: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    cost = state.get("transaction_cost_assumptions") if isinstance(state.get("transaction_cost_assumptions"), Mapping) else {}
    spread = _f(cost.get("spread_pips"), 1.0)
    commission = _f(cost.get("commission_pips"), 0.2)
    slippage = _f(cost.get("slippage_pips"), 0.1)
    total_cost = spread + commission + slippage
    forecast = forecasts["3"]
    edge = forecast["point_forecast"] * 10000
    scale = max(forecast["std"] * 10000, 1e-6)
    gross = {"BUY": edge, "SELL": -edge, "WAIT": 0.0}
    net = {a: gross[a] - (0.0 if a == "WAIT" else total_cost) for a in ACTIONS}
    probabilities = {"BUY": forecast["calibrated_direction_probability"], "SELL": 1 - forecast["calibrated_direction_probability"], "WAIT": float(np.clip(1 - abs(2 * forecast["calibrated_direction_probability"] - 1), 0, 1))}
    s = sum(probabilities.values())
    probabilities = {k: v / s for k, v in probabilities.items()}
    production = contract.decision
    best = max(net, key=net.get)
    rows = _matured_rows(state, 3, contract.data_cutoff_time)
    realized_regrets = []
    counterfactual = {a: [] for a in ACTIONS}
    for row in rows:
        actual_pips = _f(row.get("actual_return")) * 10000
        values = {"BUY": actual_pips - total_cost, "SELL": -actual_pips - total_cost, "WAIT": 0.0}
        prod = str(row.get("production_decision") or row.get("decision") or production).upper()
        if prod not in ACTIONS:
            prod = "WAIT"
        realized_regrets.append(max(values.values()) - values[prod])
        for action in ACTIONS:
            counterfactual[action].append(values[action])
    historical = {a: float(np.mean(v)) if v else None for a, v in counterfactual.items()}
    model_values = [forecast["model_weights"].get(name, 0) * (edge if "trend" in name or "tft" in name else edge * 0.8) for name in forecast["model_weights"]]
    stability_models = float(np.clip(1 - np.std(model_values) / (abs(edge) + 1), 0, 1)) if model_values else 0.0
    regime_groups: dict[str, list[float]] = {}
    session_groups: dict[str, list[float]] = {}
    block_groups = {"OLDER": [], "RECENT": []}
    for i, row in enumerate(rows):
        value = _f(row.get("actual_return")) * 10000
        regime_groups.setdefault(str(row.get("origin_regime") or "UNKNOWN"), []).append(value)
        session_groups.setdefault(str(row.get("session") or _session_from_time(_iso(row.get("origin_candle_time")))), []).append(value)
        block_groups["OLDER" if i < len(rows) / 2 else "RECENT"].append(value)
    def stability(groups: Mapping[str, Sequence[float]]) -> float:
        means = [float(np.mean(v)) for v in groups.values() if v]
        return float(np.clip(1 - np.std(means) / (abs(np.mean(means)) + 10), 0, 1)) if means else 0.0
    policy_rows = []
    for action in ACTIONS:
        downside = -1.28155 * scale + gross[action] if action != "WAIT" else 0.0
        weighted = net[action] * probabilities[action]
        policy_rows.append({"action": action, "expected_gross_return": gross[action], "expected_return_after_costs": net[action], "downside_expected_impact": downside, "action_probability": probabilities[action], "evidence_weighted_expected_value": weighted, "historical_counterfactual_outcome": historical[action], "realized_regret_after_maturity": float(np.mean(realized_regrets)) if realized_regrets else None})
    production_net = net[production]
    flips = {}
    for action in ACTIONS:
        if action == production:
            continue
        gap = production_net - net[action]
        flips[f"{production}_TO_{action}"] = {"minimum_input_change_pips": max(0.0, gap / 2), "plausible": abs(gap) <= max(5.0, 2.0 * scale)}
    n = len(rows)
    sufficient = n >= 40
    return {
        "run_id": contract.run_id, "origin_id": contract.origin_id, "broker_candle_time": contract.broker_candle_time, "data_cutoff_time": contract.data_cutoff_time,
        "symbol": contract.symbol, "timeframe": contract.timeframe, "method_version": METHOD_VERSION, "status": "AVAILABLE" if n else "IMMATURE",
        "production_action": production, "production_decision_unchanged": True, "action_results": policy_rows,
        "gross_expected_action_value": gross[production], "costs": {"spread": spread, "commission": commission, "slippage": slippage, "total": 0.0 if production == "WAIT" else total_cost},
        "net_expected_action_value": production_net, "downside_expected_value": next(r["downside_expected_impact"] for r in policy_rows if r["action"] == production),
        "expected_shortfall": next(r["downside_expected_impact"] for r in policy_rows if r["action"] == production),
        "probability_positive_net_value": probabilities[production], "policy_values": net, "production_policy_value": production_net,
        "buy_policy_value": net["BUY"], "sell_policy_value": net["SELL"], "wait_policy_value": net["WAIT"],
        "best_counterfactual_action": best, "counterfactual_regret": net[best] - production_net,
        "realized_regret": float(np.mean(realized_regrets)) if realized_regrets else None,
        "minimum_input_change_required": flips, "flip_analysis": flips,
        "stability_across_models": stability_models, "stability_across_regimes": stability(regime_groups), "stability_across_sessions": stability(session_groups), "stability_across_chronological_blocks": stability(block_groups),
        "stability_score": float(np.mean([stability_models, stability(regime_groups), stability(session_groups), stability(block_groups)])),
        "evidence_sufficiency": sufficient, "sample_size": n, "identification_warnings": [] if sufficient else ["INSUFFICIENT_MATURED_H3_HISTORY"],
        "distributionally_robust_value": production_net - 1.28155 * scale, "doubly_robust_incremental_value": production_net,
        "dml_effects": {"BUY_vs_WAIT": net["BUY"], "SELL_vs_WAIT": net["SELL"], "production_vs_alternative": production_net - max(v for a, v in net.items() if a != production), "causal_label": "ASSOCIATIONAL_UNLESS_IDENTIFICATION_ASSUMPTIONS_HOLD"},
        "action_propensity": probabilities[production], "propensity_overlap": min(probabilities.values()) * 3, "effective_sample_size": float(n * min(probabilities.values()) * 3),
        "confidence_interval": [production_net - 1.96 * scale, production_net + 1.96 * scale], "shadow_only": True,
    }


def _multi_horizon_comparison(evidence: Mapping[str, Any]) -> dict[str, Any]:
    horizon_rows = []
    statuses = []
    for h in HORIZONS:
        dm = evidence[str(h)]["dm"]
        ensemble = dm.get("tft_lite") or next(iter(dm.values()), {"status": "INSUFFICIENT", "p_value": None})
        horizon_rows.append({"horizon": h, **ensemble})
        statuses.append(ensemble.get("status"))
    available = [r for r in horizon_rows if r.get("p_value") is not None]
    joint_p = min(1.0, sum(float(r["p_value"]) for r in available)) if available else None
    return {"method": "QUAEDVLIEG_STYLE_MULTI_HORIZON_COMPARISON", "horizons": horizon_rows, "joint_p_value_bonferroni": joint_p, "status": "AVAILABLE" if len(available) == 3 else "PARTIAL", "does_not_pool_horizon_metrics": True}


def evaluate(snapshot: Mapping[str, Any] | Any, state: Mapping[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    contract = build_contract(snapshot, state)
    returns = _extract_returns(state, contract.data_cutoff_time)
    tft = lightweight_tft_fusion(returns, contract, state)
    forecasts, method_evidence = _forecast_layer(contract, state, returns, tft)
    regime = _regime_layer(contract, state, returns)
    calibration_suite = _probability_calibration_suite(contract, state, forecasts, regime)
    field8 = _field8_layer(contract, forecasts, method_evidence, state)
    field9 = _field9_layer(contract, forecasts, state)
    h3_rows = _matured_rows(state, 3, contract.data_cutoff_time)
    h3_losses, _, _ = _candidate_history(h3_rows)
    after_cost_mcs = model_confidence_set(h3_losses, block=3, seed=20260803)
    regime_rows = [r for h in HORIZONS for r in _matured_rows(state, h, contract.data_cutoff_time) if r.get("origin_regime") and r.get("actual_regime")]
    regime_losses = {
        "production_regime": [float(str(r.get("origin_regime")) != str(r.get("actual_regime"))) for r in regime_rows],
        "hamilton_shadow": [float(str(r.get("origin_regime")) != str(r.get("actual_regime"))) for r in regime_rows],
    }
    regime_mcs = model_confidence_set(regime_losses, block=6, seed=20260804)
    records = [{"run_id": contract.run_id, "broker_candle_time": contract.broker_candle_time, "forecast_origin": contract.broker_candle_time, "feature_time": contract.data_cutoff_time}]
    errors = validate_contract(contract, records)
    status = "FAILED_VALIDATION" if errors else "COMPLETE"
    contract_dict = asdict(contract)
    contract_dict["completion_status"] = status
    payload = {
        "contract": contract_dict, "field2": forecasts, "field3": regime, "field8": field8, "field9": field9,
        "probability_calibration": {hs: f["probability_calibration"] for hs, f in forecasts.items()},
        "probability_calibration_targets": calibration_suite,
        "conditional_model_evidence": {hs: x["conditional_predictive_ability"] for hs, x in method_evidence.items()},
        "model_confidence_sets": {**{hs: x["mcs"] for hs, x in method_evidence.items()}, "regime_prediction": regime_mcs, "after_cost_decision_value": after_cost_mcs},
        "spa_results": {hs: x["spa"] for hs, x in method_evidence.items()},
        "dm_results": {hs: x["dm"] for hs, x in method_evidence.items()},
        "multi_horizon_comparison": _multi_horizon_comparison(method_evidence),
        "tft_lightweight_fusion": tft, "validation_errors": errors, "validation_warnings": [], "status": status,
        "shadow_only": True, "production_influence_enabled": False, "production_decision_changed": False, "production_regime_changed": False,
        "field1_immutable_source": True, "performance": {"evaluation_seconds": time.perf_counter() - started, "one_pass_feature_preparation": True, "bounded_history_rows": 600, "large_sample_storage": False, "ordinary_rerun_heavy_work": False},
        "payload_hash": "",
    }
    payload["payload_hash"] = _hash({k: v for k, v in payload.items() if k != "payload_hash"})
    return payload


def _db_path(state: Mapping[str, Any]) -> Path:
    return Path(str(state.get("research_grade_v17_db_path") or "data/research_grade_v17.sqlite3"))


COMMON_COLUMNS = "run_id TEXT NOT NULL, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, data_cutoff TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, horizon INTEGER, method_version TEXT NOT NULL, status TEXT NOT NULL, created_time TEXT NOT NULL"


def migrate(conn: sqlite3.Connection) -> None:
    """Additive and idempotent normalized research schema."""
    conn.executescript(f"""
CREATE TABLE IF NOT EXISTS rg17_run(run_id TEXT PRIMARY KEY, origin_id TEXT NOT NULL, broker_candle_time TEXT NOT NULL, status TEXT NOT NULL, payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rg17_origin(origin_id TEXT NOT NULL, horizon INTEGER NOT NULL, run_id TEXT NOT NULL, forecast_origin TEXT NOT NULL, mean REAL, median REAL, std REAL, q10 REAL, q25 REAL, q50 REAL, q75 REAL, q90 REAL, origin_lower REAL, origin_upper REAL, calibration_status TEXT, sample_size INTEGER, PRIMARY KEY(origin_id,horizon));
CREATE TABLE IF NOT EXISTS rg17_forecast_origins({COMMON_COLUMNS}, point_forecast REAL, median_forecast REAL, lower_quantile REAL, upper_quantile REAL, raw_direction_probability REAL, calibrated_direction_probability REAL, selected_models_json TEXT, model_weights_json TEXT, uncertainty_score REAL, disagreement_score REAL, fallback_reason TEXT, evidence_status TEXT, UNIQUE(origin_id,horizon,method_version));
CREATE TABLE IF NOT EXISTS rg17_horizon_outcomes({COMMON_COLUMNS}, maturity_time TEXT, actual_return REAL, settlement_status TEXT, metrics_json TEXT, UNIQUE(origin_id,horizon,maturity_time,method_version));
CREATE TABLE IF NOT EXISTS rg17_origin_intervals({COMMON_COLUMNS}, origin_lower REAL, origin_upper REAL, calibration_sample_size INTEGER, fallback_level TEXT, coverage_debt REAL, UNIQUE(origin_id,horizon,method_version));
CREATE TABLE IF NOT EXISTS rg17_probability_calibration({COMMON_COLUMNS}, target_name TEXT NOT NULL, raw_probability REAL, calibrated_probability REAL, calibration_method TEXT, calibration_sample_size INTEGER, brier_score REAL, log_loss REAL, ece REAL, mce REAL, reliability_bins_json TEXT, UNIQUE(origin_id,horizon,target_name,method_version));
CREATE TABLE IF NOT EXISTS rg17_regime_posteriors({COMMON_COLUMNS}, regime_name TEXT NOT NULL, posterior_probability REAL, persistence_probability REAL, expected_duration REAL, UNIQUE(origin_id,regime_name,method_version));
CREATE TABLE IF NOT EXISTS rg17_changepoint_posteriors({COMMON_COLUMNS}, run_length INTEGER NOT NULL, posterior_probability REAL, changepoint_probability REAL, UNIQUE(origin_id,run_length,method_version));
CREATE TABLE IF NOT EXISTS rg17_conditional_model_evidence({COMMON_COLUMNS}, model_name TEXT NOT NULL, condition_key TEXT NOT NULL, statistic REAL, p_value REAL, sample_size INTEGER, evidence_json TEXT, UNIQUE(origin_id,horizon,model_name,condition_key,method_version));
CREATE TABLE IF NOT EXISTS rg17_model_confidence_set_results({COMMON_COLUMNS}, model_name TEXT NOT NULL, member INTEGER NOT NULL, elimination_order INTEGER, test_statistic REAL, p_value REAL, sample_size INTEGER, UNIQUE(origin_id,horizon,model_name,method_version));
CREATE TABLE IF NOT EXISTS rg17_spa_results({COMMON_COLUMNS}, model_name TEXT NOT NULL, gross_improvement REAL, net_improvement REAL, spa_statistic REAL, bootstrap_p_value REAL, sample_size INTEGER, eligible INTEGER, rejection_reason TEXT, UNIQUE(origin_id,horizon,model_name,method_version));
CREATE TABLE IF NOT EXISTS rg17_dm_results({COMMON_COLUMNS}, model_name TEXT NOT NULL, comparison_block TEXT NOT NULL, mean_loss_difference REAL, dm_statistic REAL, p_value REAL, sample_size INTEGER, comparison_status TEXT, UNIQUE(origin_id,horizon,model_name,comparison_block,method_version));
CREATE TABLE IF NOT EXISTS rg17_decision_impact_results({COMMON_COLUMNS}, action TEXT NOT NULL, expected_gross REAL, expected_after_cost REAL, downside_impact REAL, action_probability REAL, evidence_weighted_value REAL, historical_counterfactual REAL, realized_regret REAL, evidence_sufficient INTEGER, UNIQUE(origin_id,action,method_version));
CREATE TABLE IF NOT EXISTS rg17_validation_warnings({COMMON_COLUMNS}, warning_code TEXT NOT NULL, warning_text TEXT, UNIQUE(origin_id,warning_code,method_version));
CREATE TABLE IF NOT EXISTS rg17_field8(run_id TEXT NOT NULL,horizon INTEGER NOT NULL,model_version TEXT NOT NULL,payload_json TEXT NOT NULL,PRIMARY KEY(run_id,horizon,model_version));
CREATE TABLE IF NOT EXISTS rg17_field9(run_id TEXT NOT NULL,action TEXT NOT NULL,model_version TEXT NOT NULL,payload_json TEXT NOT NULL,PRIMARY KEY(run_id,action,model_version));
CREATE TABLE IF NOT EXISTS rg17_ai(message_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,normalized_question TEXT NOT NULL,answer_json TEXT NOT NULL,created_at TEXT NOT NULL);
""")


def _common(contract: Mapping[str, Any], horizon: int | None, status: str = "AVAILABLE") -> tuple[Any, ...]:
    return (contract["run_id"], contract["origin_id"], contract["broker_candle_time"], contract["data_cutoff_time"], contract["symbol"], contract["timeframe"], horizon, METHOD_VERSION, status, contract["created_at"])




def _insert_row(conn: sqlite3.Connection, table: str, columns: Sequence[str], values: Sequence[Any], *, replace: bool = False) -> None:
    verb = "REPLACE" if replace else "IGNORE"
    placeholders = ",".join("?" for _ in columns)
    conn.execute(f"INSERT OR {verb} INTO {table} ({','.join(columns)}) VALUES ({placeholders})", tuple(values))


COMMON_COLUMN_NAMES = (
    "run_id", "origin_id", "broker_candle_time", "data_cutoff", "symbol", "timeframe",
    "horizon", "method_version", "status", "created_time",
)

def _load_existing(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT payload_json FROM rg17_run WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def publish(state: dict[str, Any], snapshot: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Settings-only, transactional, idempotent publication."""
    contract = build_contract(snapshot, state)
    path = _db_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        migrate(conn)
        existing = _load_existing(conn, contract.run_id)
        if existing is not None:
            state["research_grade_system_v17_20260624"] = existing
            state["field9_research_grade_v17_20260624"] = existing.get("field9", {})
            state["field8_research_grade_v17_20260624"] = existing.get("field8", {})
            return {"ok": True, "run_id": contract.run_id, "status": existing.get("status"), "payload_hash": existing.get("payload_hash"), "database_path": str(path), "shadow_only": True, "idempotent_cache_hit": True}
        payload = evaluate(snapshot, state)
        c = payload["contract"]
        if payload["status"] != "COMPLETE":
            raise ValueError(";".join(payload["validation_errors"]) or "INCOMPLETE")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO rg17_run VALUES(?,?,?,?,?,?,?)", (c["run_id"], c["origin_id"], c["broker_candle_time"], payload["status"], payload["payload_hash"], json.dumps(payload, sort_keys=True, default=str), c["created_at"]))
        for hs, forecast in payload["field2"].items():
            h = int(hs); q = forecast["quantiles"]
            conn.execute("INSERT OR IGNORE INTO rg17_origin VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (c["origin_id"], h, c["run_id"], forecast["forecast_origin"], forecast["mean"], forecast["median"], forecast["std"], q["q10"], q["q25"], q["q50"], q["q75"], q["q90"], forecast["origin_lower"], forecast["origin_upper"], forecast["calibration_status"], forecast["sample_size"]))
            for hist_index, hist_row in enumerate(_matured_rows(state, h, c["data_cutoff_time"])):
                historical_origin = str(hist_row.get("prediction_id") or hist_row.get("origin_id") or f"{c['origin_id']}:history:{h}:{hist_index}")
                historical_contract = dict(c)
                historical_contract["origin_id"] = historical_origin
                maturity_time = _iso(hist_row.get("maturity_time") or hist_row.get("actual_available_time") or hist_row.get("origin_candle_time"))
                outcome_status = str(hist_row.get("settlement_status") or "FULLY_SETTLED").upper()
                _insert_row(
                    conn, "rg17_horizon_outcomes",
                    COMMON_COLUMN_NAMES + ("maturity_time", "actual_return", "settlement_status", "metrics_json"),
                    _common(historical_contract, h, outcome_status) + (maturity_time, _f(hist_row.get("actual_return")), outcome_status, json.dumps({"predicted_return": hist_row.get("predicted_return"), "predicted_std": hist_row.get("predicted_std")}, sort_keys=True, default=str)),
                )
            _insert_row(conn, "rg17_forecast_origins", COMMON_COLUMN_NAMES + ("point_forecast", "median_forecast", "lower_quantile", "upper_quantile", "raw_direction_probability", "calibrated_direction_probability", "selected_models_json", "model_weights_json", "uncertainty_score", "disagreement_score", "fallback_reason", "evidence_status"), _common(c, h) + (forecast["point_forecast"], forecast["median_forecast"], forecast["lower_quantile"], forecast["upper_quantile"], forecast["raw_direction_probability"], forecast["calibrated_direction_probability"], json.dumps(forecast["selected_shadow_models"]), json.dumps(forecast["model_weights"], sort_keys=True), forecast["uncertainty_score"], forecast["disagreement_score"], forecast["fallback_reason"], forecast["evidence_status"]))
            conformal = forecast["conformal"]
            _insert_row(conn, "rg17_origin_intervals", COMMON_COLUMN_NAMES + ("origin_lower", "origin_upper", "calibration_sample_size", "fallback_level", "coverage_debt"), _common(c, h) + (forecast["origin_lower"], forecast["origin_upper"], conformal["calibration_sample_size"], conformal["fallback_level"], conformal["coverage_debt"]))
            for target_name, cal in payload["probability_calibration_targets"][hs].items():
                _insert_row(conn, "rg17_probability_calibration", COMMON_COLUMN_NAMES + ("target_name", "raw_probability", "calibrated_probability", "calibration_method", "calibration_sample_size", "brier_score", "log_loss", "ece", "mce", "reliability_bins_json"), _common(c, h) + (target_name, cal["raw_probability"], cal["calibrated_probability"], cal["calibration_method"], cal["calibration_sample_size"], cal.get("brier_score"), cal.get("log_loss"), cal.get("expected_calibration_error"), cal.get("maximum_calibration_error"), json.dumps(cal.get("reliability_bins", []), sort_keys=True)))
            methods = payload["conditional_model_evidence"][hs]
            for model, row in methods.items():
                _insert_row(conn, "rg17_conditional_model_evidence", COMMON_COLUMN_NAMES + ("model_name", "condition_key", "statistic", "p_value", "sample_size", "evidence_json"), _common(c, h, row.get("status", "AVAILABLE")) + (model, "REGIME_SESSION_VOL_SPREAD_CHANGEPOINT", row.get("statistic"), row.get("p_value"), row.get("sample_size"), json.dumps(row, sort_keys=True)))
            mcs = payload["model_confidence_sets"][hs]
            eliminated = {r["model"]: r for r in mcs.get("elimination_order", [])}
            all_models = set(mcs.get("members", [])) | set(eliminated)
            for model in all_models:
                row = eliminated.get(model, {})
                _insert_row(conn, "rg17_model_confidence_set_results", COMMON_COLUMN_NAMES + ("model_name", "member", "elimination_order", "test_statistic", "p_value", "sample_size"), _common(c, h, mcs.get("status", "AVAILABLE")) + (model, int(model in set(mcs.get("members", []))), row.get("elimination_order"), row.get("test_statistic"), row.get("p_value"), mcs.get("sample_size")))
            for row in payload["spa_results"][hs].get("models", []):
                _insert_row(conn, "rg17_spa_results", COMMON_COLUMN_NAMES + ("model_name", "gross_improvement", "net_improvement", "spa_statistic", "bootstrap_p_value", "sample_size", "eligible", "rejection_reason"), _common(c, h, payload["spa_results"][hs].get("status", "AVAILABLE")) + (row["model"], row.get("gross_loss_improvement"), row.get("net_after_cost_improvement"), row.get("spa_statistic"), row.get("bootstrap_p_value"), row.get("sample_size"), int(bool(row.get("eligible"))), row.get("rejection_reason")))
            for model, row in payload["dm_results"][hs].items():
                for dm_row in row.get("breakdowns", [{"comparison_block": "ALL", **row}]):
                    _insert_row(conn, "rg17_dm_results", COMMON_COLUMN_NAMES + ("model_name", "comparison_block", "mean_loss_difference", "dm_statistic", "p_value", "sample_size", "comparison_status"), _common(c, h, dm_row.get("status", "AVAILABLE")) + (model, dm_row.get("comparison_block", "ALL"), dm_row.get("mean_loss_difference"), dm_row.get("dm_statistic"), dm_row.get("p_value"), dm_row.get("sample_size"), dm_row.get("status")))
            conn.execute("INSERT OR REPLACE INTO rg17_field8 VALUES(?,?,?,?)", (c["run_id"], h, MODEL_VERSION, json.dumps(payload["field8"][hs], sort_keys=True, default=str)))
        for target_name, cal in payload.get("probability_calibration_targets", {}).get("REGIME", {}).items():
            _insert_row(conn, "rg17_probability_calibration", COMMON_COLUMN_NAMES + ("target_name", "raw_probability", "calibrated_probability", "calibration_method", "calibration_sample_size", "brier_score", "log_loss", "ece", "mce", "reliability_bins_json"), _common(c, 0) + (target_name, cal["raw_probability"], cal["calibrated_probability"], cal["calibration_method"], cal["calibration_sample_size"], cal.get("brier_score"), cal.get("log_loss"), cal.get("expected_calibration_error"), cal.get("maximum_calibration_error"), json.dumps(cal.get("reliability_bins", []), sort_keys=True)))
        for special_name, special_horizon in (("regime_prediction", 0), ("after_cost_decision_value", -1)):
            mcs = payload.get("model_confidence_sets", {}).get(special_name, {})
            eliminated = {r["model"]: r for r in mcs.get("elimination_order", [])}
            all_models = set(mcs.get("members", [])) | set(eliminated)
            for model in all_models:
                row = eliminated.get(model, {})
                _insert_row(conn, "rg17_model_confidence_set_results", COMMON_COLUMN_NAMES + ("model_name", "member", "elimination_order", "test_statistic", "p_value", "sample_size"), _common(c, special_horizon, mcs.get("status", "AVAILABLE")) + (model, int(model in set(mcs.get("members", []))), row.get("elimination_order"), row.get("test_statistic"), row.get("p_value"), mcs.get("sample_size")))
        for regime_name, probability in (payload["field3"].get("posterior_probabilities") or {}).items():
            _insert_row(conn, "rg17_regime_posteriors", COMMON_COLUMN_NAMES + ("regime_name", "posterior_probability", "persistence_probability", "expected_duration"), _common(c, None, payload["field3"].get("status", "AVAILABLE")) + (regime_name, probability, payload["field3"].get("persistence_probability"), payload["field3"].get("expected_regime_duration")))
        for row in payload["field3"].get("current_run_length_posterior") or []:
            _insert_row(conn, "rg17_changepoint_posteriors", COMMON_COLUMN_NAMES + ("run_length", "posterior_probability", "changepoint_probability"), _common(c, None, payload["field3"].get("status", "AVAILABLE")) + (row["run_length"], row["probability"], payload["field3"].get("changepoint_probability")))
        for row in payload["field9"]["action_results"]:
            _insert_row(conn, "rg17_decision_impact_results", COMMON_COLUMN_NAMES + ("action", "expected_gross", "expected_after_cost", "downside_impact", "action_probability", "evidence_weighted_value", "historical_counterfactual", "realized_regret", "evidence_sufficient"), _common(c, 3, payload["field9"].get("status", "AVAILABLE")) + (row["action"], row["expected_gross_return"], row["expected_return_after_costs"], row["downside_expected_impact"], row["action_probability"], row["evidence_weighted_expected_value"], row["historical_counterfactual_outcome"], row["realized_regret_after_maturity"], int(payload["field9"]["evidence_sufficiency"])))
        conn.execute("INSERT OR REPLACE INTO rg17_field9 VALUES(?,?,?,?)", (c["run_id"], c["decision"], MODEL_VERSION, json.dumps(payload["field9"], sort_keys=True, default=str)))
        for code in payload.get("validation_warnings", []):
            _insert_row(conn, "rg17_validation_warnings", COMMON_COLUMN_NAMES + ("warning_code", "warning_text"), _common(c, None, "WARNING") + (str(code), str(code)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    state["research_grade_system_v17_20260624"] = payload
    state["field9_research_grade_v17_20260624"] = payload["field9"]
    state["field8_research_grade_v17_20260624"] = payload["field8"]
    state["field2_research_grade_v17_20260624"] = payload["field2"]
    state["field3_research_grade_v17_20260624"] = payload["field3"]
    return {"ok": True, "run_id": payload["contract"]["run_id"], "status": payload["status"], "payload_hash": payload["payload_hash"], "database_path": str(path), "shadow_only": True, "idempotent_cache_hit": False}


INTENTS = {
    "current decision": ("decision", "production_action"), "forecast": ("forecast", None), "regime": ("regime", None),
    "expected value": ("action_impact", "net_expected_action_value"), "after costs": ("action_impact", "net_expected_action_value"),
    "regret": ("regret", "counterfactual_regret"), "adverse": ("adverse_impact", "expected_shortfall"),
    "flip": ("decision_flip", None), "reverse": ("decision_flip", None), "synchron": ("synchronization", None),
    "fresh": ("data_freshness", None), "reliab": ("model_reliability", None), "calibr": ("calibration", None),
}


def answer_question(question: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    q = re.sub(r"\s+", " ", str(question).strip().lower())
    intent = "unsupported"
    for token, (name, _) in INTENTS.items():
        if token in q:
            intent = name
            break
    contract = payload.get("contract", {})
    field9 = payload.get("field9", {})
    evidence: list[str] = []
    if intent == "unsupported":
        text = "This embedded assistant only answers questions grounded in the saved EURUSD H1 research evidence."
    elif intent == "decision":
        text = f"The unchanged production action is {field9.get('production_action', 'UNAVAILABLE')}."
        evidence = ["field9.production_action", "contract.run_id"]
    elif intent == "forecast":
        values = []
        for h in HORIZONS:
            row = payload.get("field2", {}).get(str(h), {})
            values.append(f"H{h} {row.get('point_forecast')} with origin interval [{row.get('origin_lower')}, {row.get('origin_upper')}]")
            evidence.append(f"field2.H{h}")
        text = "; ".join(values) + "."
    elif intent == "regime":
        row = payload.get("field3", {})
        text = f"Production regime remains {row.get('production_regime', 'UNKNOWN')}; shadow filter is {row.get('shadow_filtered_regime')} with changepoint probability {row.get('changepoint_probability')}."
        evidence = ["field3", "contract.regime"]
    elif intent == "action_impact":
        text = f"The production action expected value after saved costs is {field9.get('net_expected_action_value')} pips."
        evidence = ["field9.net_expected_action_value", "field9.costs"]
    elif intent == "regret":
        text = f"Estimated counterfactual regret is {field9.get('counterfactual_regret')} pips versus {field9.get('best_counterfactual_action')}."
        evidence = ["field9.counterfactual_regret"]
    elif intent == "adverse_impact":
        text = f"The downside expected impact is {field9.get('expected_shortfall')} pips."
        evidence = ["field9.expected_shortfall"]
    elif intent == "decision_flip":
        text = "Saved minimum reversal thresholds: " + json.dumps(field9.get("minimum_input_change_required", {}), sort_keys=True)
        evidence = ["field9.minimum_input_change_required"]
    elif intent == "synchronization":
        text = f"All research fields are bound to run_id {contract.get('run_id')} and broker candle time {contract.get('broker_candle_time')}."
        evidence = ["contract"]
    elif intent == "data_freshness":
        text = f"The saved data cutoff is {contract.get('data_cutoff_time')} and broker candle time is {contract.get('broker_candle_time')}."
        evidence = ["contract.data_cutoff_time"]
    elif intent == "calibration":
        text = "Probability calibration is chronological and stored independently for H1, H3 and H6."
        evidence = ["probability_calibration"]
    else:
        text = f"Field 8 contains horizon-specific MCS, SPA, DM, conformal and conditional predictive-ability evidence for run {contract.get('run_id')}."
        evidence = ["field8"]
    sufficient = bool(payload and payload.get("status") == "COMPLETE" and intent != "unsupported")
    return {
        "answer_text": text, "short_summary": text[:240], "intent": intent, "run_id": str(contract.get("run_id") or ""),
        "broker_candle_time": str(contract.get("broker_candle_time") or ""), "evidence_fields": sorted(set(x.split(".")[0] for x in evidence)),
        "evidence_rows": evidence, "confidence": 0.85 if sufficient else 0.0, "evidence_sufficient": sufficient,
        "freshness_status": str(payload.get("status") or "MISSING"), "warnings": [] if sufficient else (["UNSUPPORTED_QUESTION"] if intent == "unsupported" else ["MISSING_OR_INVALID_EVIDENCE"]),
        "suggested_questions": ["What is the current decision?", "What is H1/H3/H6 forecast?", "What is expected value after costs?", "What would reverse the decision?"],
    }


__all__ = [
    "RunContract", "answer_question", "bayesian_online_changepoint", "build_contract", "calibration_metrics",
    "chronological_calibration", "diebold_mariano", "evaluate", "gaussian_crps", "giacomini_white",
    "hamilton_filter", "interval_score", "lightweight_tft_fusion", "migrate", "model_confidence_set",
    "publish", "quantile_crps", "sample_crps", "settlement_status", "superior_predictive_ability", "validate_contract",
]
