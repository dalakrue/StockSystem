"""Institutional Field 10 child evidence, published under the locked parent snapshot.

Production authority remains ``field10_daily_snapshot`` and
``field10_daily_snapshot_symbol``.  This module never migrates the database,
never rewrites a parent rank/bias, and never runs from a renderer.  It is called
only by the Settings multi-symbol orchestrator after the parent publication.

Every calculation is a versioned shadow candidate until the registered
out-of-sample promotion gates are satisfied.  Missing evidence is represented
as NULL plus a precise reason rather than as a fabricated neutral value.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from contextlib import suppress
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import json
import math
import sqlite3

import numpy as np
import pandas as pd

from core.timeframe_window_contract_20260706 import (
    horizon_contract, normalize_completed_frame, required_candles, selected_timeframe,
    validate_timeframe_spacing, window_contract,
)

from core.multi_symbol_field10_20260701 import (
    DB_PATH,
    _candidate_cache_paths,
    _canonical_symbol_from_state,
    _read_cache_payload,
    normalize_symbol,
)

FEATURE_VERSION = "field10-institutional-features-20260704-v1"
MODEL_VERSION = "field10-institutional-shadow-20260704-v1"
FORMULA_VERSION = "field10-hierarchical-utility-20260704-v1"
THRESHOLD_VERSION = "field10-promotion-gates-20260704-v1"
CALIBRATION_VERSION = "purged-walk-forward-calibration-20260704-v1"
CONFORMAL_VERSION = "adaptive-marginal-conformal-20260704-v1"
REGIME_VERSION = "hamilton-supporting-evidence-20260704-v1"
BREAK_VERSION = "break-bocpd-supporting-evidence-20260704-v1"
RELIABILITY_VERSION = "weighted-geometric-components-20260704-v1"
RANK_VERSION = "locked-parent-rank-bootstrap-20260704-v1"
SETTLEMENT_VERSION = "field10-outcome-definition-20260704-v1"
HORIZONS = (1, 6, 12, 24)
TARGET_COVERAGE = 0.90
MIN_MODEL_ROWS = 120
MIN_CALIBRATION_ROWS = 60
MIN_CONFORMAL_ROWS = 60
MIN_DEPENDENCE_ROWS = 80
SHADOW_TABLES = {
    "field10_canonical_identity", "field10_forecast_ledger", "field10_outcome_ledger",
    "field10_regime_shadow", "field10_structural_break_shadow", "field10_session_shadow",
    "field10_calibration_shadow", "field10_conformal_shadow", "field10_dependence_shadow",
    "field10_event_intensity_shadow", "field10_reliability_shadow", "field10_rank_confidence_shadow",
    "field10_shadow_publication_audit",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _hash(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clip01(value: Any) -> float | None:
    number = _finite(value)
    return None if number is None else float(np.clip(number, 0.0, 1.0))


def _connect(path: Path | str, *, read_only: bool = False) -> sqlite3.Connection:
    db = Path(path).resolve()
    if read_only:
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=8.0)
    else:
        conn = sqlite3.connect(str(db), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def schema_ready(path: Path | str = DB_PATH) -> tuple[bool, list[str]]:
    try:
        with _connect(path, read_only=True) as conn:
            present = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except Exception as exc:
        return False, [f"database unavailable: {type(exc).__name__}: {exc}"]
    missing = sorted(SHADOW_TABLES - present)
    return not missing, missing


def _decode(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except Exception:
        return default


def _exact_state_for_symbol(state: Mapping[str, Any], symbol: str) -> tuple[Mapping[str, Any] | None, str | None]:
    target = normalize_symbol(symbol)
    direct = _canonical_symbol_from_state(state)
    if direct == target:
        return state, None
    for path in _candidate_cache_paths(target):
        if not path.is_file():
            continue
        try:
            payload = _read_cache_payload(path)
            candidate = payload.get("state")
            if isinstance(candidate, Mapping) and _canonical_symbol_from_state(candidate) == target:
                return candidate, None
        except Exception:
            continue
    return None, f"no exact same-symbol runtime state for {target}"


def _find_ohlc(value: Any, depth: int = 0, seen: set[int] | None = None) -> pd.DataFrame:
    if depth > 6:
        return pd.DataFrame()
    seen = seen if seen is not None else set()
    if isinstance(value, (Mapping, list, tuple, pd.DataFrame)):
        marker = id(value)
        if marker in seen:
            return pd.DataFrame()
        seen.add(marker)
    if isinstance(value, pd.DataFrame):
        names = {str(c).strip().lower().replace("_", " ") for c in value.columns}
        if "close" in names and (names & {"time", "timestamp", "datetime", "broker candle time"} or isinstance(value.index, pd.DatetimeIndex)):
            return value.copy()
        return pd.DataFrame()
    if isinstance(value, Mapping):
        preferred = (
            "canonical_completed_ohlc_df_20260617", "calculation_staging_ohlc_df_20260617",
            "last_df", "dv_pp_df", "lunch_5layer_powerbi_df", "ohlc", "market_data", "data", "df",
        )
        for key in preferred:
            if key in value:
                found = _find_ohlc(value[key], depth + 1, seen)
                if not found.empty:
                    return found
        for child in value.values():
            found = _find_ohlc(child, depth + 1, seen)
            if not found.empty:
                return found
    if isinstance(value, (list, tuple)):
        for child in value[:50]:
            found = _find_ohlc(child, depth + 1, seen)
            if not found.empty:
                return found
    return pd.DataFrame()


def normalize_completed_timeframe(
    frame: pd.DataFrame, *, cutoff: Any, timeframe: str = "H1", max_rows: int | None = None,
    required_rows: int | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Normalize and causally truncate exact-symbol selected-timeframe data."""
    tf = selected_timeframe(timeframe)
    required = required_candles(tf, "higher") if required_rows is None else max(1, int(required_rows))
    maximum = max(required, int(max_rows or required))
    reasons: list[str] = []
    out = normalize_completed_frame(frame, timeframe=tf, completed_candle=cutoff, max_rows=maximum)
    cutoff_ts = pd.to_datetime(cutoff, errors="coerce", utc=True)
    if pd.isna(cutoff_ts):
        return pd.DataFrame(), ["locked completed-candle timestamp is invalid"]
    if out.empty:
        return out, ["same-symbol OHLC is unavailable at or before the locked completed candle"]
    if pd.Timestamp(out["time"].iloc[-1]) != cutoff_ts:
        reasons.append(f"window ends at {pd.Timestamp(out['time'].iloc[-1]).isoformat()} instead of locked cutoff {cutoff_ts.isoformat()}")
    if len(out) < required:
        reasons.append(f"requires {required} completed {tf} rows; found {len(out)}")
    spacing = validate_timeframe_spacing(out, timeframe=tf, time_column="time")
    if not spacing.get("ok"):
        reasons.append(str(spacing.get("status") or "INVALID_TIMEFRAME_SPACING"))
    return out, reasons


def normalize_completed_h1(
    frame: pd.DataFrame, *, cutoff: Any, max_rows: int = 600, required_rows: int | None = None
) -> tuple[pd.DataFrame, list[str]]:
    """Backward-compatible H1 wrapper retained for database/API compatibility."""
    return normalize_completed_timeframe(
        frame, cutoff=cutoff, timeframe="H1", max_rows=max_rows, required_rows=required_rows
    )

def _features(frame: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    close = frame["close"].astype(float)
    ret = np.log(close / close.shift(1)).replace([np.inf, -np.inf], np.nan)
    x = pd.DataFrame(index=frame.index)
    x["ret1"] = ret.shift(1)
    x["ret3"] = ret.shift(1).rolling(3).sum()
    x["ret6"] = ret.shift(1).rolling(6).sum()
    x["ret12"] = ret.shift(1).rolling(12).sum()
    x["vol6"] = ret.shift(1).rolling(6).std()
    x["vol24"] = ret.shift(1).rolling(24).std()
    x["range"] = ((frame["high"] - frame["low"]) / close).shift(1)
    x["hour_sin"] = np.sin(2 * np.pi * frame["time"].dt.hour / 24.0)
    x["hour_cos"] = np.cos(2 * np.pi * frame["time"].dt.hour / 24.0)
    future = np.log(close.shift(-horizon) / close)
    y = (future > 0).astype(float)
    return x.replace([np.inf, -np.inf], np.nan), y, future


def _ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> tuple[float, float]:
    if len(y) == 0:
        return float("nan"), float("nan")
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    mce = 0.0
    for i in range(bins):
        mask = (p >= edges[i]) & (p < edges[i + 1] if i < bins - 1 else p <= edges[i + 1])
        if not mask.any():
            continue
        gap = abs(float(y[mask].mean()) - float(p[mask].mean()))
        ece += gap * float(mask.mean())
        mce = max(mce, gap)
    return ece, mce


def _brier_decomposition(y: np.ndarray, p: np.ndarray, bins: int = 10) -> tuple[float, float]:
    base = float(np.mean(y)) if len(y) else float("nan")
    reliability = 0.0
    resolution = 0.0
    edges = np.linspace(0, 1, bins + 1)
    for i in range(bins):
        mask = (p >= edges[i]) & (p < edges[i + 1] if i < bins - 1 else p <= edges[i + 1])
        if not mask.any():
            continue
        weight = float(mask.mean())
        obs = float(y[mask].mean())
        pred = float(p[mask].mean())
        reliability += weight * (pred - obs) ** 2
        resolution += weight * (obs - base) ** 2
    return reliability, resolution


def _probability_and_interval(frame: pd.DataFrame, horizon: int, *, timeframe: str = "H1") -> dict[str, Any]:
    """Purged chronological probability calibration and marginal conformal interval."""
    result: dict[str, Any] = {
        "horizon": horizon, "raw_probability": None, "calibrated_probability": None,
        "calibration_status": "INSUFFICIENT_SAMPLE", "selected_method": None,
        "sample_count": 0, "missing_reason": None, "metrics": {},
        "raw_expected_return": None, "median_prediction": None,
        "lower": None, "upper": None, "interval_width": None,
        "coverage": None, "lower_miss": None, "upper_miss": None,
        "adaptive_alpha": 1 - TARGET_COVERAGE, "coverage_error": None,
        "distribution_shift": "UNKNOWN", "conformal_status": "INSUFFICIENT_SAMPLE",
    }
    horizon_bars = int(horizon_contract(timeframe=timeframe, horizon_hours=horizon)["horizon_bars"])
    result["horizon_bars"] = horizon_bars
    result["horizon_hours"] = horizon
    result["timeframe"] = selected_timeframe(timeframe)
    x, y, future = _features(frame, horizon_bars)
    joined = x.copy()
    joined["y"] = y
    joined["future"] = future
    historical = joined.iloc[:-horizon_bars].dropna().copy() if len(joined) > horizon_bars else pd.DataFrame()
    current_x = x.iloc[[-1]].dropna()
    n = len(historical)
    result["sample_count"] = n
    if current_x.empty:
        result["missing_reason"] = "current feature vector is incomplete"
        return result
    if n < MIN_MODEL_ROWS or historical["y"].nunique() < 2:
        result["missing_reason"] = f"requires at least {MIN_MODEL_ROWS} completed labelled rows and both classes; found {n}"
        # A causal return statistic may still be shown as raw expectation, never as calibrated reliability.
        ret = np.log(frame["close"] / frame["close"].shift(1)).dropna()
        if len(ret) >= 30:
            result["raw_expected_return"] = float(ret.tail(min(120, len(ret))).ewm(span=24).mean().iloc[-1] * horizon)
            result["median_prediction"] = result["raw_expected_return"]
        return result
    try:
        from sklearn.isotonic import IsotonicRegression
        from sklearn.linear_model import LogisticRegression, Ridge
        from sklearn.metrics import brier_score_loss, log_loss
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        # Chronological 60/20/20 split with explicit purge/embargo equal to horizon.
        train_end = int(n * 0.60)
        val_start = min(n, train_end + horizon_bars)
        val_end = int(n * 0.80)
        test_start = min(n, val_end + horizon_bars)
        train = historical.iloc[:train_end]
        val = historical.iloc[val_start:val_end]
        test = historical.iloc[test_start:]
        if min(len(train), len(val), len(test)) < max(20, horizon_bars * 2) or train["y"].nunique() < 2:
            result["missing_reason"] = "purging/embargo leaves inadequate chronological train, validation or test data"
            return result
        cols = list(x.columns)
        base = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=7404))
        base.fit(train[cols], train["y"])
        val_raw = base.predict_proba(val[cols])[:, 1]
        test_raw = base.predict_proba(test[cols])[:, 1]
        current_raw = float(base.predict_proba(current_x[cols])[:, 1][0])
        result["raw_probability"] = current_raw

        # Calibrators are fitted only on purged validation predictions. Selection
        # uses validation cross-fit loss; the untouched chronological test reports metrics.
        eps = 1e-6
        val_logit = np.log(np.clip(val_raw, eps, 1 - eps) / np.clip(1 - val_raw, eps, 1 - eps)).reshape(-1, 1)
        test_logit = np.log(np.clip(test_raw, eps, 1 - eps) / np.clip(1 - test_raw, eps, 1 - eps)).reshape(-1, 1)
        current_logit = np.array([[math.log(np.clip(current_raw, eps, 1 - eps) / np.clip(1 - current_raw, eps, 1 - eps))]])
        platt = LogisticRegression(max_iter=1000, random_state=7404).fit(val_logit, val["y"])
        p_platt_val = platt.predict_proba(val_logit)[:, 1]
        p_platt_test = platt.predict_proba(test_logit)[:, 1]
        iso = IsotonicRegression(out_of_bounds="clip").fit(val_raw, val["y"])
        p_iso_val = np.asarray(iso.predict(val_raw), dtype=float)
        p_iso_test = np.asarray(iso.predict(test_raw), dtype=float)
        val_y = val["y"].to_numpy(dtype=float)
        platt_loss = float(log_loss(val_y, np.clip(p_platt_val, eps, 1 - eps)))
        iso_loss = float(log_loss(val_y, np.clip(p_iso_val, eps, 1 - eps)))
        if iso_loss + 1e-9 < platt_loss and len(np.unique(val_raw)) >= 10:
            method = "ISOTONIC"
            test_prob = p_iso_test
            current_cal = float(iso.predict([current_raw])[0])
        else:
            method = "PLATT"
            test_prob = p_platt_test
            current_cal = float(platt.predict_proba(current_logit)[:, 1][0])
        test_y = test["y"].to_numpy(dtype=float)
        brier = float(brier_score_loss(test_y, test_prob))
        baseline_p = float(train["y"].mean())
        baseline_brier = float(np.mean((test_y - baseline_p) ** 2))
        bss = None if baseline_brier <= 0 else float(1 - brier / baseline_brier)
        ll = float(log_loss(test_y, np.clip(test_prob, eps, 1 - eps)))
        ece, mce = _ece(test_y, test_prob)
        rel, res = _brier_decomposition(test_y, test_prob)
        result.update({
            "calibrated_probability": current_cal, "calibration_status": "OUT_OF_SAMPLE_SHADOW",
            "selected_method": method,
            "metrics": {
                "brier_score": brier, "baseline_brier_score": baseline_brier,
                "brier_skill_score": bss, "log_loss": ll,
                "expected_calibration_error": ece, "maximum_calibration_error": mce,
                "reliability_component": rel, "resolution_component": res,
                "train_count": len(train), "validation_count": len(val), "test_count": len(test),
                "training_interval": [int(train.index.min()), int(train.index.max())],
                "validation_interval": [int(val.index.min()), int(val.index.max())],
                "test_interval": [int(test.index.min()), int(test.index.max())],
            },
        })

        # Return model and split-conformal residuals. This is explicitly marginal,
        # not conditional coverage. Validation residuals determine q; test is untouched.
        reg = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
        reg.fit(train[cols], train["future"])
        val_pred = reg.predict(val[cols])
        test_pred = reg.predict(test[cols])
        current_pred = float(reg.predict(current_x[cols])[0])
        residual = np.abs(val["future"].to_numpy(dtype=float) - val_pred)
        if len(residual) >= MIN_CONFORMAL_ROWS:
            q_level = min(1.0, math.ceil((len(residual) + 1) * TARGET_COVERAGE) / len(residual))
            q = float(np.quantile(residual, q_level, method="higher"))
            lower = current_pred - q
            upper = current_pred + q
            test_actual = test["future"].to_numpy(dtype=float)
            test_lower = test_pred - q
            test_upper = test_pred + q
            covered = (test_actual >= test_lower) & (test_actual <= test_upper)
            coverage = float(np.mean(covered))
            lower_miss = float(np.mean(test_actual < test_lower))
            upper_miss = float(np.mean(test_actual > test_upper))
            recent_scale = float(np.nanstd(test_actual[-min(30, len(test_actual)):]))
            historic_scale = float(np.nanstd(train["future"]))
            shift = "SHIFT_WARNING" if historic_scale > 0 and recent_scale / historic_scale > 1.5 else "STABLE"
            adaptive_alpha = float(np.clip((1 - TARGET_COVERAGE) + (TARGET_COVERAGE - coverage) * 0.25, 0.01, 0.30))
            result.update({
                "raw_expected_return": current_pred, "median_prediction": current_pred,
                "lower": lower, "upper": upper, "interval_width": upper - lower,
                "coverage": coverage, "lower_miss": lower_miss, "upper_miss": upper_miss,
                "adaptive_alpha": adaptive_alpha, "coverage_error": coverage - TARGET_COVERAGE,
                "distribution_shift": shift, "conformal_status": "MARGINAL_OOS_SHADOW",
                "conformal_calibration_count": len(residual),
            })
        else:
            result["raw_expected_return"] = current_pred
            result["median_prediction"] = current_pred
            result["missing_reason"] = f"conformal calibration requires {MIN_CONFORMAL_ROWS} residuals; found {len(residual)}"
        return result
    except Exception as exc:
        result["calibration_status"] = "MODEL_ERROR"
        result["conformal_status"] = "MODEL_ERROR"
        result["missing_reason"] = f"{type(exc).__name__}: {exc}"
        return result


def _hamilton_support(frame: pd.DataFrame, authoritative_regime: str | None) -> dict[str, Any]:
    ret = np.log(frame["close"] / frame["close"].shift(1)).dropna()
    if len(ret) < 80 or not authoritative_regime or str(authoritative_regime).upper() in {"", "UNAVAILABLE", "N/A"}:
        return {"status": "INSUFFICIENT_HISTORY", "missing_reason": "authoritative Field 3 regime or 80 completed returns unavailable", "sample": len(ret)}
    vol = ret.rolling(24, min_periods=12).std()
    state = np.where(ret.rolling(6).mean() >= 0, 1, 0)
    transitions = np.ones((2, 2), dtype=float)
    for a, b in zip(state[:-1], state[1:]):
        transitions[int(a), int(b)] += 1
    transitions /= transitions.sum(axis=1, keepdims=True)
    means = [float(ret[state == k].mean()) if np.any(state == k) else float(ret.mean()) for k in (0, 1)]
    stds = [max(float(ret[state == k].std()), 1e-8) if np.any(state == k) else max(float(ret.std()), 1e-8) for k in (0, 1)]
    alpha = np.array([0.5, 0.5])
    for value in ret.tail(240):
        pred = alpha @ transitions
        density = np.array([math.exp(-0.5 * ((value - means[k]) / stds[k]) ** 2) / stds[k] for k in (0, 1)])
        alpha = pred * density
        alpha = alpha / alpha.sum() if alpha.sum() else np.array([0.5, 0.5])
    order = np.argsort(alpha)[::-1]
    auth = str(authoritative_regime)
    selected_prob = float(alpha[1] if any(x in auth.upper() for x in ("BULL", "BUY", "UP")) else alpha[0] if any(x in auth.upper() for x in ("BEAR", "SELL", "DOWN")) else alpha.max())
    self_p = float(transitions[order[0], order[0]])
    entropy = float(-np.sum(alpha * np.log(np.clip(alpha, 1e-12, 1)))) / math.log(2)
    current_state = int(state[-1])
    age = 1
    for prior in state[-2::-1]:
        if int(prior) != current_state:
            break
        age += 1
    remaining = self_p / max(1 - self_p, 1e-6)
    return {
        "status": "SHADOW_ONLY", "selected_regime": auth, "selected_probability": selected_prob,
        "second_regime": "BULL_SUPPORT" if order[1] == 1 else "BEAR_SUPPORT",
        "second_probability": float(alpha[order[1]]), "margin": float(abs(alpha[0] - alpha[1])),
        "entropy": entropy, "self_transition": self_p,
        "transition_1h": 1 - self_p, "transition_6h": 1 - self_p ** 6,
        "transition_12h": 1 - self_p ** 12, "transition_24h": 1 - self_p ** 24,
        "age": age, "remaining": remaining, "sample": len(ret), "missing_reason": None,
    }


def _structural_break(frame: pd.DataFrame) -> dict[str, Any]:
    """Bai–Perron-style single dominant split plus lightweight online-change evidence.

    Every component is computed only from rows at or before the locked completed
    candle. Unavailable series are explicitly recorded as unavailable rather than
    fabricated.
    """
    ret = np.log(frame["close"] / frame["close"].shift(1)).tail(360)
    valid_ret = ret.dropna()
    if len(valid_ret) < 100:
        return {"status": "INSUFFICIENT_HISTORY", "missing_reason": "requires 100 completed returns", "sample": len(valid_ret)}
    values = valid_ret.to_numpy(dtype=float)
    candidates = range(40, len(values) - 40)
    global_scale = max(float(np.std(values)), 1e-8)
    best: tuple[float, int, dict[str, Any]] | None = None
    for split in candidates:
        pre, post = values[:split], values[split:]
        mean_distance = abs(float(pre.mean() - post.mean())) / global_scale
        vol_distance = abs(float(pre.std() - post.std())) / global_scale
        slope_pre = float(np.polyfit(np.arange(len(pre)), pre, 1)[0])
        slope_post = float(np.polyfit(np.arange(len(post)), post, 1)[0])
        slope_distance = abs(slope_pre - slope_post) * len(values) / global_scale
        score = mean_distance + vol_distance + min(slope_distance, 5.0)
        if best is None or score > best[0]:
            best = (score, split, {"return_mean": mean_distance, "realized_volatility": vol_distance, "trend_slope": slope_distance})
    assert best is not None
    score, split, components = best

    # Evaluate provider-dependent series at the same split. Missing inputs remain NULL.
    aligned_tail = frame.tail(len(values)).reset_index(drop=True)
    for column, label in (("spread", "spread"), ("tick_volume", "tick_volume")):
        series = pd.to_numeric(aligned_tail.get(column), errors="coerce") if column in aligned_tail else pd.Series(dtype=float)
        if len(series) == len(values) and series.notna().sum() >= 80:
            pre_s, post_s = series.iloc[:split].dropna(), series.iloc[split:].dropna()
            scale = max(float(series.std(skipna=True)), 1e-8)
            components[label] = abs(float(pre_s.mean() - post_s.mean())) / scale if len(pre_s) and len(post_s) else None
        else:
            components[label] = None
    # Session/technical coefficients use causal proxies; event/residual coefficients require settled ledgers.
    hour = aligned_tail["time"].dt.hour.to_numpy(dtype=float)
    components["session_coefficients"] = abs(float(np.corrcoef(values, np.sin(2 * np.pi * hour / 24))[0, 1])) if len(hour) == len(values) else None
    momentum = aligned_tail["close"].pct_change(6).to_numpy(dtype=float)
    mask = np.isfinite(momentum) & np.isfinite(values)
    components["technical_feature_coefficients"] = abs(float(np.corrcoef(values[mask], momentum[mask])[0, 1])) if mask.sum() >= 30 else None
    components["news_response_coefficients"] = None
    components["expected_value_residuals"] = None
    components["calibration_residuals"] = None

    strength = float(1 - math.exp(-score / 3.0))
    post_count = len(values) - split
    recent = values[-1]
    recent_mean = float(np.mean(values[-24:]))
    recent_std = max(float(np.std(values[-60:])), 1e-8)
    cp_prob = float(np.clip(1 - math.exp(-abs(recent - recent_mean) / recent_std), 0, 0.999))
    modal_run = max(1, int(round((1 - cp_prob) * 48)))
    severe = strength >= 0.75 and post_count < 96
    break_time = aligned_tail.iloc[split]["time"]
    missing_components = [k for k, v in components.items() if v is None]
    return {
        "status": "SHADOW_ONLY", "last_break": pd.Timestamp(break_time).isoformat(), "strength": strength,
        "post_count": post_count, "distance": score, "changepoint_probability": cp_prob,
        "modal_run_length": modal_run, "expected_run_length": 1 / max(cp_prob, 1e-6),
        "run_length_uncertainty": math.sqrt(max(cp_prob * (1 - cp_prob), 0)),
        "permission": "BLOCK_NEW_ENTRY" if severe else "SHADOW_MONITOR",
        "components": components, "sample": len(values),
        "missing_reason": None if not missing_components else "unavailable components: " + ", ".join(missing_components),
    }


# Eight DST-aware local-market windows. ZoneInfo performs historical/future DST conversion.
SESSION_WINDOWS = (
    ("Sydney", "Australia/Sydney", 7, 16),
    ("Tokyo", "Asia/Tokyo", 8, 17),
    ("Singapore", "Asia/Singapore", 8, 17),
    ("Frankfurt", "Europe/Berlin", 7, 16),
    ("London", "Europe/London", 8, 17),
    ("London-New York Overlap", "America/New_York", 8, 12),
    ("New York AM", "America/New_York", 8, 13),
    ("New York PM", "America/New_York", 13, 17),
)


def _session_rows(frame: pd.DataFrame, regime: Mapping[str, Any]) -> list[dict[str, Any]]:
    ret = np.log(frame["close"] / frame["close"].shift(1))
    latest = frame["time"].iloc[-1]
    rows: list[dict[str, Any]] = []
    for name, zone_name, start, end in SESSION_WINDOWS:
        local = frame["time"].dt.tz_convert(ZoneInfo(zone_name))
        mask = (local.dt.hour >= start) & (local.dt.hour < end)
        sample = ret.loc[mask].dropna().tail(160)
        now_local = latest.tz_convert(ZoneInfo(zone_name))
        active = start <= now_local.hour < end
        if len(sample) < 20:
            rows.append({"session_name": name, "sample_count": len(sample), "validation_status": "INSUFFICIENT_HISTORY", "entry_permission": "BLOCKED_INSUFFICIENT_DATA", "current": active, "missing_reason": "requires 20 session returns"})
            continue
        vol = float(sample.std())
        all_vol = ret.rolling(24).std().dropna()
        percentile = float((all_vol <= vol).mean()) if len(all_vol) else None
        expected = float(sample.mean())
        downside = sample[sample <= sample.quantile(0.05)]
        cvar = float(downside.mean()) if len(downside) else None
        hit = float((sample > 0).mean())
        tick = frame.loc[mask, "tick_volume"].dropna().tail(160)
        spread = frame.loc[mask, "spread"].dropna().tail(160)
        transition = _finite(regime.get("transition_1h"))
        rows.append({
            "session_name": name, "session_normalized_volatility": vol / max(float(ret.std()), 1e-8),
            "volatility_percentile": percentile, "abnormal_activity": abs(float(sample.tail(8).mean())) / max(vol, 1e-8),
            "normalized_tick_volume": float(tick.iloc[-1] / tick.median()) if len(tick) and tick.median() else None,
            "normalized_spread": float(spread.iloc[-1] / spread.median()) if len(spread) and spread.median() else None,
            "expected_movement": expected, "net_expected_value": None, "cvar_95": cvar,
            "directional_hit_rate": hit, "regime_compatibility": None if transition is None else 1 - transition,
            "entry_permission": "SHADOW_ONLY", "sample_count": len(sample),
            "data_completeness": float(frame.loc[mask, ["open", "high", "low", "close"]].notna().mean().mean()),
            "current": active, "missing_reason": "spread/slippage cost model unavailable; net EV remains NULL",
            "validation_status": "SHADOW_ONLY",
        })
    eligible = [r for r in rows if _finite(r.get("expected_movement")) is not None]
    ordered = sorted(eligible, key=lambda r: (-(r.get("expected_movement") or -1e9), r["session_name"]))
    rank = {r["session_name"]: i + 1 for i, r in enumerate(ordered)}
    for row in rows:
        row["session_rank"] = rank.get(row["session_name"])
        row["next"] = False
    # Next session is selected by smallest positive local opening distance.
    distances: list[tuple[float, str]] = []
    for name, zone_name, start, _ in SESSION_WINDOWS:
        loc = latest.tz_convert(ZoneInfo(zone_name))
        hours = (start - (loc.hour + loc.minute / 60.0)) % 24
        distances.append((hours, name))
    if distances:
        next_name = min((x for x in distances if x[0] > 0.01), default=min(distances))[1]
        for row in rows:
            row["next"] = row["session_name"] == next_name
    return rows


def _net_ev(frame: pd.DataFrame, horizon: int, bias: str | None, *, timeframe: str = "H1") -> dict[str, Any]:
    horizon_bars = int(horizon_contract(timeframe=timeframe, horizon_hours=horizon)["horizon_bars"])
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    direction = -1.0 if "SELL" in str(bias).upper() else 1.0
    future_ret = direction * (close.shift(-horizon_bars) / close - 1.0)
    mfe = direction * (high.shift(-1).rolling(horizon_bars).max().shift(-(horizon_bars - 1)) / close - 1.0)
    mae = direction * (low.shift(-1).rolling(horizon_bars).min().shift(-(horizon_bars - 1)) / close - 1.0)
    sample = pd.DataFrame({"r": future_ret, "mfe": mfe, "mae": mae}).dropna()
    if len(sample) < 60:
        return {"status": "INSUFFICIENT_HISTORY", "sample": len(sample), "net_ev": None, "missing_reason": "requires 60 realized horizon paths"}
    gain = sample.loc[sample.r > 0]
    loss = sample.loc[sample.r <= 0]
    p_gain = len(gain) / len(sample)
    p_loss = 1 - p_gain
    gross_ev = p_gain * float(gain.mfe.mean() if len(gain) else 0) - p_loss * abs(float(loss.mae.mean() if len(loss) else 0))
    spread = frame["spread"].dropna()
    # Never fabricate cost. Net EV remains NULL when the provider does not supply spread.
    spread_cost = None if spread.empty else float(spread.tail(min(120, len(spread))).mean())
    net_ev = None if spread_cost is None else gross_ev - spread_cost
    tail = sample.r.loc[sample.r <= sample.r.quantile(0.05)]
    var = float(sample.r.quantile(0.05))
    cvar = float(tail.mean()) if len(tail) else None
    ess = float(len(sample) / (1 + 2 * max(sample.r.autocorr(lag=1) or 0, 0)))
    return {
        "status": "SHADOW_ONLY", "sample": len(sample), "effective_sample": ess,
        "expected_return": float(sample.r.mean()), "expected_value": gross_ev, "net_ev": net_ev,
        "spread_cost": spread_cost, "slippage_cost": None, "var": var, "cvar": cvar,
        "mfe": float(sample.mfe.mean()), "mae": float(sample.mae.mean()),
        "probability_reach_ev": float((sample.r >= gross_ev).mean()),
        "missing_reason": None if net_ev is not None else "provider spread/slippage costs unavailable; net EV is NULL",
    }


def _dependence(frames: Mapping[str, pd.DataFrame]) -> dict[str, dict[str, Any]]:
    series = []
    for symbol, frame in frames.items():
        ret = np.log(frame.set_index("time")["close"] / frame.set_index("time")["close"].shift(1)).rename(symbol)
        series.append(ret)
    if len(series) < 2:
        return {s: {"status": "INSUFFICIENT_UNIVERSE", "sample": 0, "missing_reason": "requires at least two exact-symbol series"} for s in frames}
    matrix = pd.concat(series, axis=1, join="inner").dropna().tail(600)
    if len(matrix) < MIN_DEPENDENCE_ROWS:
        return {s: {"status": "INSUFFICIENT_HISTORY", "sample": len(matrix), "missing_reason": f"requires {MIN_DEPENDENCE_ROWS} aligned returns"} for s in frames}
    try:
        from sklearn.covariance import LedoitWolf
        estimator = LedoitWolf().fit(matrix.to_numpy(dtype=float))
        cov = estimator.covariance_
        std = np.sqrt(np.diag(cov))
        corr = cov / np.outer(std, std)
        symbols = list(matrix.columns)
        result: dict[str, dict[str, Any]] = {}
        for i, symbol in enumerate(symbols):
            peers = [(symbols[j], float(corr[i, j])) for j in range(len(symbols)) if j != i]
            cluster = sorted([s for s, c in peers if abs(c) >= 0.70])
            max_corr = max((abs(c) for _, c in peers), default=0.0)
            usd = -1.0 if symbol.startswith("USD") else 1.0 if symbol.endswith("USD") else 0.0
            eur = 1.0 if symbol.startswith("EUR") else -1.0 if symbol.endswith("EUR") else 0.0
            result[symbol] = {
                "status": "SHADOW_ONLY", "sample": len(matrix), "cluster": ", ".join(cluster) or "UNCLUSTERED",
                "concentration": max_corr, "penalty": max_corr, "diversification": 1 - max_corr,
                "usd": usd, "eur": eur, "common": float(np.mean(np.abs(corr[i]))),
                "evidence": {"correlations": dict(peers), "shrinkage": float(estimator.shrinkage_)}, "missing_reason": None,
            }
        return result
    except Exception as exc:
        return {s: {"status": "MODEL_ERROR", "sample": len(matrix), "missing_reason": f"{type(exc).__name__}: {exc}"} for s in frames}


def _geometric_reliability(components: Mapping[str, float | None], effective_sample: float) -> dict[str, Any]:
    weights = {
        "calibration_reliability": 0.16, "conformal_coverage_reliability": 0.13,
        "sample_adequacy": 0.12, "data_completeness": 0.11,
        "source_identity_reliability": 0.14, "regime_stability": 0.10,
        "structural_stability": 0.09, "rank_stability": 0.05,
        "feature_availability": 0.06, "outcome_settlement_completeness": 0.04,
    }
    values = {k: _clip01(components.get(k)) for k in weights}
    available = {k: v for k, v in values.items() if v is not None}
    if not available:
        aggregate = None
    else:
        denom = sum(weights[k] for k in available)
        aggregate = math.exp(sum((weights[k] / denom) * math.log(max(v, 1e-6)) for k, v in available.items()))
    weakness = min(available, key=available.get) if available else "all_components_unavailable"
    status = "INSUFFICIENT_EVIDENCE" if aggregate is None or len(available) < 7 else "SHADOW_ONLY"
    return {
        "components": values, "weights": weights, "aggregate": aggregate, "weakness": weakness,
        "status": status, "effective_sample": effective_sample,
        "explanation": f"Weighted geometric mean across {len(available)}/10 available components; weakest={weakness}. Missing components are not imputed.",
    }


def _rank_confidence(rows: Sequence[Mapping[str, Any]], draws: int = 500) -> dict[str, dict[str, Any]]:
    valid = [r for r in rows if _finite(r.get("utility")) is not None]
    if len(valid) < 2:
        return {str(r["symbol"]): {"status": "INSUFFICIENT_UNIVERSE", "missing_reason": "requires two utilities", "draws": 0} for r in rows}
    symbols = [str(r["symbol"]) for r in valid]
    utility = np.array([float(r["utility"]) for r in valid])
    uncertainty = np.array([max(float(r.get("uncertainty") or 0.001), 1e-6) for r in valid])
    seed_text = _hash({"symbols": symbols, "utility": utility.tolist(), "version": RANK_VERSION})
    rng = np.random.default_rng(int(seed_text[:16], 16))
    ranks = np.empty((draws, len(valid)), dtype=int)
    for b in range(draws):
        scores = utility + rng.normal(0, uncertainty)
        order = np.lexsort((np.array(symbols), -scores))
        rank = np.empty(len(valid), dtype=int)
        rank[order] = np.arange(1, len(valid) + 1)
        ranks[b] = rank
    result: dict[str, dict[str, Any]] = {}
    for i, symbol in enumerate(symbols):
        rr = ranks[:, i]
        sorted_u = sorted(utility, reverse=True)
        gap = float(utility[i] - max([u for j, u in enumerate(utility) if j != i], default=utility[i]))
        result[symbol] = {
            "status": "SHADOW_ONLY", "prob1": float(np.mean(rr == 1)), "prob4": float(np.mean(rr <= 4)),
            "median": float(np.median(rr)), "low": float(np.quantile(rr, 0.05)), "high": float(np.quantile(rr, 0.95)),
            "instability": float(np.std(rr)), "gap": gap, "draws": draws, "block": 24,
            "seed": seed_text, "missing_reason": None,
        }
    for row in rows:
        result.setdefault(str(row["symbol"]), {"status": "INSUFFICIENT_UTILITY", "missing_reason": "utility unavailable", "draws": 0})
    return result


def _insert(conn: sqlite3.Connection, table: str, payload: Mapping[str, Any]) -> bool:
    columns = list(payload)
    sql = f"INSERT OR IGNORE INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
    before = conn.total_changes
    conn.execute(sql, [payload[c] for c in columns])
    return conn.total_changes > before


def _parent_snapshot(conn: sqlite3.Connection, daily_snapshot_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    meta = conn.execute("SELECT * FROM field10_daily_snapshot WHERE daily_snapshot_id=?", (daily_snapshot_id,)).fetchone()
    if meta is None:
        raise ValueError(f"parent snapshot not found: {daily_snapshot_id}")
    rows = conn.execute("SELECT * FROM field10_daily_snapshot_symbol WHERE daily_snapshot_id=? ORDER BY daily_rank IS NULL,daily_rank,symbol", (daily_snapshot_id,)).fetchall()
    return dict(meta), [dict(r) for r in rows]


def publish_institutional_shadow(
    state: MutableMapping[str, Any], *, daily_snapshot_id: str, selected_symbols: Sequence[str], path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Publish append-only child evidence after the authoritative parent locks."""
    ready, missing = schema_ready(path)
    if not ready:
        return {"ok": False, "status": "MIGRATION_REQUIRED", "missing": missing}
    created = _utc_now()
    with _connect(path) as conn:
        meta, parents = _parent_snapshot(conn, daily_snapshot_id)
    requested = [normalize_symbol(s) for s in selected_symbols]
    parent_symbols = [str(r["symbol"]) for r in parents]
    if requested and requested != [s for s in parent_symbols if s in requested]:
        # Order can differ due to ranking; identity uses exact set equality.
        if set(requested) != set(parent_symbols):
            return {"ok": False, "status": "IDENTITY_MISMATCH", "requested": requested, "parent": parent_symbols}
    canonical_payload = {
        "daily_snapshot_id": daily_snapshot_id, "run_id": meta["parent_run_id"], "broker_day": meta["broker_day"],
        "broker_timestamp": meta["published_at_broker_time"], "completed_h1_candle": meta["latest_completed_h1"],
        "main_symbol": meta["main_symbol"], "selected_symbol_universe_json": meta["ordered_symbol_universe_json"],
        "universe_hash": meta["universe_hash"], "source_ids_json": meta["source_ids_json"],
        "snapshot_hashes_json": meta["snapshot_hashes_json"], "feature_version": FEATURE_VERSION,
        "formula_version": FORMULA_VERSION, "threshold_version": THRESHOLD_VERSION, "model_version": MODEL_VERSION,
        "publication_status": "SHADOW_ONLY", "created_system_time": created,
    }
    canonical_payload["content_hash"] = _hash(canonical_payload)

    frames: dict[str, pd.DataFrame] = {}
    per_symbol: dict[str, dict[str, Any]] = {}
    for parent in parents:
        symbol = str(parent["symbol"])
        source_id = str(parent.get("source_id") or "").strip()
        source_hash = str(parent.get("snapshot_hash") or "").strip()
        exact_state, state_reason = _exact_state_for_symbol(state, symbol)
        timeframe = selected_timeframe(parent.get("timeframe") or meta.get("timeframe") or (exact_state or {}).get("timeframe") or "H1")
        needed = required_candles(timeframe, "higher")
        if exact_state is None:
            frame, reasons = pd.DataFrame(), [state_reason or "same-symbol state unavailable"]
        else:
            frame, reasons = normalize_completed_timeframe(
                _find_ohlc(exact_state), cutoff=parent.get("completed_candle"), timeframe=timeframe,
                max_rows=needed, required_rows=needed,
            )
        if not source_id:
            reasons.append("parent source_id is missing")
        if not source_hash:
            reasons.append("parent source_hash/snapshot_hash is missing")
        if not frame.empty and str(frame["time"].iloc[-1].isoformat()) != str(pd.to_datetime(parent.get("completed_candle"), utc=True).isoformat()):
            reasons.append("exact completed-candle identity mismatch")
        identity_ok = not reasons
        if identity_ok:
            frames[symbol] = frame
        regime = _hamilton_support(frame, parent.get("higher_standard_regime")) if identity_ok else {"status": "BLOCKED_IDENTITY", "sample": len(frame), "missing_reason": "; ".join(reasons)}
        brk = _structural_break(frame) if identity_ok else {"status": "BLOCKED_IDENTITY", "sample": len(frame), "missing_reason": "; ".join(reasons)}
        forecasts = {h: _probability_and_interval(frame, h, timeframe=timeframe) if identity_ok else {"horizon": h, "calibration_status": "BLOCKED_IDENTITY", "conformal_status": "BLOCKED_IDENTITY", "missing_reason": "; ".join(reasons), "sample_count": len(frame)} for h in HORIZONS}
        ev = {h: _net_ev(frame, h, parent.get("less_risky_bias"), timeframe=timeframe) if identity_ok else {"status": "BLOCKED_IDENTITY", "sample": len(frame), "net_ev": None, "missing_reason": "; ".join(reasons)} for h in HORIZONS}
        sessions = _session_rows(frame, regime) if identity_ok else [
            {"session_name": name, "sample_count": 0, "validation_status": "BLOCKED_IDENTITY", "entry_permission": "BLOCKED_IDENTITY", "current": False, "next": False, "missing_reason": "; ".join(reasons)}
            for name, *_ in SESSION_WINDOWS
        ]
        per_symbol[symbol] = {"parent": parent, "frame": frame, "timeframe": timeframe, "required_candles": needed, "reasons": reasons, "identity_ok": identity_ok, "regime": regime, "break": brk, "forecasts": forecasts, "ev": ev, "sessions": sessions}

    dependence = _dependence(frames)
    utility_rows: list[dict[str, Any]] = []
    for symbol, pack in per_symbol.items():
        evs = pack["ev"]
        weights = {1: 0.15, 6: 0.35, 12: 0.30, 24: 0.20}
        net_values = [evs[h].get("net_ev") for h in HORIZONS]
        usable = [(h, _finite(evs[h].get("net_ev"))) for h in HORIZONS]
        usable = [(h, v) for h, v in usable if v is not None]
        weighted_ev = None if not usable else sum(weights[h] * v for h, v in usable) / sum(weights[h] for h, _ in usable)
        cvar_values = [abs(v) for h in HORIZONS if (v := _finite(evs[h].get("cvar"))) is not None]
        cvar_penalty = max(cvar_values, default=0.0)
        transition = _finite(pack["regime"].get("transition_6h")) or 0.0
        interval_values = [v for h in HORIZONS if (v := _finite(pack["forecasts"][h].get("interval_width"))) is not None]
        uncertainty = float(np.mean(interval_values)) if interval_values else None
        break_penalty = _finite(pack["break"].get("strength")) or 0.0
        dep = dependence.get(symbol, {})
        corr_penalty = _finite(dep.get("penalty")) or 0.0
        completeness = (
            float(pack["frame"][["open", "high", "low", "close"]].notna().mean().mean())
            if len(pack["frame"]) else 0.0
        )
        data_quality_penalty = max(0.0, 1.0 - completeness)
        eligible = bool(pack["identity_ok"] and len(pack["frame"]) >= int(pack.get("required_candles") or 600))
        utility = None if (weighted_ev is None or not eligible) else (
            weighted_ev - 0.5 * cvar_penalty - 0.15 * transition
            - 0.10 * (uncertainty or 0) - 0.10 * break_penalty
            - 0.10 * corr_penalty - 0.10 * data_quality_penalty
        )
        utility_rows.append({
            "symbol": symbol, "utility": utility, "uncertainty": uncertainty,
            "original_rank": pack["parent"].get("daily_rank"), "eligible": eligible,
            "data_quality_penalty": data_quality_penalty,
        })
    rank_conf = _rank_confidence(utility_rows)

    inserted: dict[str, int] = {name: 0 for name in SHADOW_TABLES}
    audit_details: dict[str, Any] = {"symbols": {}, "production_authority": ["field10_daily_snapshot", "field10_daily_snapshot_symbol"]}
    with _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            inserted["field10_canonical_identity"] += int(_insert(conn, "field10_canonical_identity", canonical_payload))
            for symbol, pack in per_symbol.items():
                parent, regime, brk = pack["parent"], pack["regime"], pack["break"]
                source_id = str(parent.get("source_id") or "") or None
                source_hash = str(parent.get("snapshot_hash") or "") or None
                regime_payload = {
                    "daily_snapshot_id": daily_snapshot_id, "symbol": symbol,
                    "selected_regime": regime.get("selected_regime"), "selected_regime_probability": regime.get("selected_probability"),
                    "second_regime": regime.get("second_regime"), "second_regime_probability": regime.get("second_probability"),
                    "posterior_margin": regime.get("margin"), "regime_entropy": regime.get("entropy"),
                    "self_transition_probability": regime.get("self_transition"), "transition_probability_1h": regime.get("transition_1h"),
                    "transition_probability_6h": regime.get("transition_6h"), "transition_probability_12h": regime.get("transition_12h"),
                    "transition_probability_24h": regime.get("transition_24h"), "regime_age": regime.get("age"),
                    "expected_remaining_duration": regime.get("remaining"), "regime_model_version": REGIME_VERSION,
                    "validation_status": regime.get("status", "INCOMPLETE"), "evidence_sample_size": int(regime.get("sample") or 0),
                    "missing_reason": regime.get("missing_reason"), "created_system_time": created,
                }
                regime_payload["content_hash"] = _hash(regime_payload)
                inserted["field10_regime_shadow"] += int(_insert(conn, "field10_regime_shadow", regime_payload))
                break_payload = {
                    "daily_snapshot_id": daily_snapshot_id, "symbol": symbol, "last_structural_break": brk.get("last_break"),
                    "structural_break_strength": brk.get("strength"), "post_break_h1_count": brk.get("post_count"),
                    "pre_post_parameter_distance": brk.get("distance"), "changepoint_probability": brk.get("changepoint_probability"),
                    "modal_run_length": brk.get("modal_run_length"), "expected_run_length": brk.get("expected_run_length"),
                    "run_length_uncertainty": brk.get("run_length_uncertainty"),
                    "post_break_validation_permission": brk.get("permission", "BLOCKED"),
                    "break_components_json": _canonical(brk.get("components") or {}), "model_version": BREAK_VERSION,
                    "validation_status": brk.get("status", "INCOMPLETE"), "missing_reason": brk.get("missing_reason"),
                    "created_system_time": created,
                }
                break_payload["content_hash"] = _hash(break_payload)
                inserted["field10_structural_break_shadow"] += int(_insert(conn, "field10_structural_break_shadow", break_payload))
                for session in pack["sessions"]:
                    session_payload = {
                        "daily_snapshot_id": daily_snapshot_id, "symbol": symbol, "session_name": session["session_name"],
                        "session_rank": session.get("session_rank"), "session_normalized_volatility": session.get("session_normalized_volatility"),
                        "volatility_percentile": session.get("volatility_percentile"), "abnormal_activity": session.get("abnormal_activity"),
                        "normalized_tick_volume": session.get("normalized_tick_volume"), "normalized_spread": session.get("normalized_spread"),
                        "expected_movement": session.get("expected_movement"), "net_expected_value": session.get("net_expected_value"),
                        "cvar_95": session.get("cvar_95"), "directional_hit_rate": session.get("directional_hit_rate"),
                        "regime_compatibility": session.get("regime_compatibility"), "entry_permission": session.get("entry_permission", "BLOCKED"),
                        "sample_count": int(session.get("sample_count") or 0), "data_completeness": session.get("data_completeness"),
                        "current_active_session": int(bool(session.get("current"))), "next_session": int(bool(session.get("next"))),
                        "session_transition_risk": regime.get("transition_1h"), "formula_version": FORMULA_VERSION,
                        "validation_status": session.get("validation_status", "INCOMPLETE"), "missing_reason": session.get("missing_reason"),
                        "created_system_time": created,
                    }
                    session_payload["content_hash"] = _hash(session_payload)
                    inserted["field10_session_shadow"] += int(_insert(conn, "field10_session_shadow", session_payload))
                effective_samples: list[float] = []
                for horizon in HORIZONS:
                    forecast = pack["forecasts"][horizon]
                    ev = pack["ev"][horizon]
                    metrics = forecast.get("metrics") or {}
                    due = pd.to_datetime(parent.get("completed_candle"), utc=True, errors="coerce") + pd.Timedelta(hours=horizon)
                    forecast_id = "F10F-" + _hash({"snapshot": daily_snapshot_id, "symbol": symbol, "h": horizon, "model": MODEL_VERSION})[:24]
                    missing_reason = "; ".join(dict.fromkeys([x for x in (forecast.get("missing_reason"), ev.get("missing_reason"), *pack["reasons"]) if x])) or None
                    raw_ev = forecast.get("raw_expected_return")
                    net_ev = ev.get("net_ev")
                    risk_ev = None if net_ev is None else float(net_ev) - abs(float(ev.get("cvar") or 0))
                    entry_permission = str(parent.get("trade_permission") or "BLOCKED")
                    if brk.get("permission") == "BLOCK_NEW_ENTRY":
                        entry_permission = "BLOCKED_BY_STRUCTURAL_BREAK"
                    f_payload = {
                        "forecast_id": forecast_id, "daily_snapshot_id": daily_snapshot_id, "parent_run_id": meta["parent_run_id"],
                        "child_run_id": parent.get("canonical_run_id"), "broker_day": meta["broker_day"], "symbol": symbol,
                        "horizon_hours": horizon, "completed_h1_candle": parent.get("completed_candle") or meta["latest_completed_h1"],
                        "published_at_broker_time": meta["published_at_broker_time"], "outcome_due_broker_time": due.isoformat() if not pd.isna(due) else meta["published_at_broker_time"],
                        "raw_direction_probability": forecast.get("raw_probability"), "calibrated_direction_probability": forecast.get("calibrated_probability"),
                        "calibration_status": forecast.get("calibration_status", "INCOMPLETE"), "raw_expected_return": raw_ev,
                        "expected_value": ev.get("expected_value"), "net_expected_value": net_ev,
                        "risk_adjusted_expected_value": risk_ev,
                        "expected_spread_cost": ev.get("spread_cost"), "expected_slippage_cost": ev.get("slippage_cost"),
                        "var_95": ev.get("var"), "cvar_95": ev.get("cvar"),
                        "expected_mfe": ev.get("mfe"), "expected_mae": ev.get("mae"),
                        "probability_reach_expected_value": ev.get("probability_reach_ev"),
                        "sample_count": int(ev.get("sample") or 0), "effective_sample_size": ev.get("effective_sample"),
                        "lower_interval": forecast.get("lower"),
                        "median_prediction": forecast.get("median_prediction"), "upper_interval": forecast.get("upper"),
                        "target_coverage": TARGET_COVERAGE, "transition_probability": regime.get(f"transition_{horizon}h"),
                        "entry_permission": entry_permission, "formula_version": FORMULA_VERSION, "feature_version": FEATURE_VERSION,
                        "model_version": MODEL_VERSION, "calibration_version": CALIBRATION_VERSION, "source_id": source_id,
                        "source_hash": source_hash, "missing_reason": missing_reason, "publication_status": "SHADOW_ONLY",
                        "created_system_time": created,
                    }
                    f_payload["content_hash"] = _hash(f_payload)
                    inserted["field10_forecast_ledger"] += int(_insert(conn, "field10_forecast_ledger", f_payload))
                    c_payload = {
                        "daily_snapshot_id": daily_snapshot_id, "symbol": symbol, "horizon_hours": horizon,
                        "target_name": "DIRECTION", "raw_probability": forecast.get("raw_probability"),
                        "calibrated_probability": forecast.get("calibrated_probability"), "selected_method": forecast.get("selected_method"),
                        "calibration_status": forecast.get("calibration_status", "INCOMPLETE"), "brier_score": metrics.get("brier_score"),
                        "brier_skill_score": metrics.get("brier_skill_score"), "baseline_brier_score": metrics.get("baseline_brier_score"),
                        "log_loss": metrics.get("log_loss"), "expected_calibration_error": metrics.get("expected_calibration_error"),
                        "maximum_calibration_error": metrics.get("maximum_calibration_error"), "reliability_component": metrics.get("reliability_component"),
                        "resolution_component": metrics.get("resolution_component"), "calibration_sample_count": int(forecast.get("sample_count") or 0),
                        "calibration_freshness_hours": 0.0, "purging_hours": horizon, "embargo_hours": horizon,
                        "training_interval": _canonical(metrics.get("training_interval")) if metrics.get("training_interval") else None,
                        "validation_interval": _canonical(metrics.get("validation_interval")) if metrics.get("validation_interval") else None,
                        "test_interval": _canonical(metrics.get("test_interval")) if metrics.get("test_interval") else None,
                        "calibration_version": CALIBRATION_VERSION, "validation_status": "SHADOW_ONLY" if forecast.get("calibration_status") == "OUT_OF_SAMPLE_SHADOW" else forecast.get("calibration_status", "INCOMPLETE"),
                        "missing_reason": forecast.get("missing_reason"), "metrics_json": _canonical(metrics), "created_system_time": created,
                    }
                    c_payload["content_hash"] = _hash(c_payload)
                    inserted["field10_calibration_shadow"] += int(_insert(conn, "field10_calibration_shadow", c_payload))
                    conformal_payload = {
                        "daily_snapshot_id": daily_snapshot_id, "symbol": symbol, "horizon_hours": horizon,
                        "regime_key": str(parent.get("higher_standard_regime") or "UNAVAILABLE"), "session_key": "ALL_SESSIONS",
                        "lower_conformal_return": forecast.get("lower"), "median_expected_return": forecast.get("median_prediction"),
                        "upper_conformal_return": forecast.get("upper"), "interval_width": forecast.get("interval_width"),
                        "target_coverage": TARGET_COVERAGE, "rolling_realized_coverage": forecast.get("coverage"),
                        "lower_tail_miss_rate": forecast.get("lower_miss"), "upper_tail_miss_rate": forecast.get("upper_miss"),
                        "adaptive_alpha": forecast.get("adaptive_alpha"), "coverage_error": forecast.get("coverage_error"),
                        "distribution_shift_status": forecast.get("distribution_shift", "UNKNOWN"),
                        "calibration_sample_count": int(forecast.get("conformal_calibration_count") or 0),
                        "conformal_version": CONFORMAL_VERSION, "validation_status": forecast.get("conformal_status", "INCOMPLETE"),
                        "missing_reason": forecast.get("missing_reason"), "created_system_time": created,
                    }
                    conformal_payload["content_hash"] = _hash(conformal_payload)
                    inserted["field10_conformal_shadow"] += int(_insert(conn, "field10_conformal_shadow", conformal_payload))
                    if ev.get("effective_sample") is not None:
                        effective_samples.append(float(ev["effective_sample"]))
                dep = dependence.get(symbol, {})
                dep_payload = {
                    "daily_snapshot_id": daily_snapshot_id, "symbol": symbol, "correlation_cluster": dep.get("cluster"),
                    "cluster_concentration": dep.get("concentration"), "duplicate_exposure_penalty": dep.get("penalty"),
                    "marginal_diversification_value": dep.get("diversification"), "usd_exposure": dep.get("usd"),
                    "eur_exposure": dep.get("eur"), "common_factor_exposure": dep.get("common"),
                    "covariance_method": "LEDOIT_WOLF_SHRINKAGE", "sample_count": int(dep.get("sample") or 0),
                    "validation_status": dep.get("status", "INCOMPLETE"), "missing_reason": dep.get("missing_reason"),
                    "evidence_json": _canonical(dep.get("evidence") or {}), "created_system_time": created,
                }
                dep_payload["content_hash"] = _hash(dep_payload)
                inserted["field10_dependence_shadow"] += int(_insert(conn, "field10_dependence_shadow", dep_payload))
                event_payload = {
                    "daily_snapshot_id": daily_snapshot_id, "symbol": symbol, "event_family": "NEWS_VOLATILITY_SPREAD_SENTIMENT",
                    "baseline_intensity": None, "current_excitation": None, "decay": None, "event_cluster_state": "INSUFFICIENT_HISTORY",
                    "estimated_remaining_impact": None, "event_transition_warning": "SHADOW_NOT_ESTIMATED",
                    "model_version": "hawkes-lightweight-20260704-v1", "validation_status": "INSUFFICIENT_HISTORY",
                    "sample_count": 0, "missing_reason": "no causally aligned settled event-intensity history in the uploaded database",
                    "created_system_time": created,
                }
                event_payload["content_hash"] = _hash(event_payload)
                inserted["field10_event_intensity_shadow"] += int(_insert(conn, "field10_event_intensity_shadow", event_payload))
                calibration_ece = [pack["forecasts"][h].get("metrics", {}).get("expected_calibration_error") for h in HORIZONS]
                calibration_ece = [float(x) for x in calibration_ece if _finite(x) is not None]
                coverage_err = [abs(float(x)) for h in HORIZONS if (x := _finite(pack["forecasts"][h].get("coverage_error"))) is not None]
                settled = conn.execute("SELECT COUNT(*) FROM field10_outcome_ledger o JOIN field10_forecast_ledger f USING(forecast_id) WHERE f.symbol=?", (symbol,)).fetchone()[0]
                forecasts_total = conn.execute("SELECT COUNT(*) FROM field10_forecast_ledger WHERE symbol=?", (symbol,)).fetchone()[0]
                rank_item = rank_conf.get(symbol, {})
                components = {
                    "calibration_reliability": None if not calibration_ece else max(0.0, 1 - float(np.mean(calibration_ece)) / 0.10),
                    "conformal_coverage_reliability": None if not coverage_err else max(0.0, 1 - float(np.mean(coverage_err)) / 0.10),
                    "sample_adequacy": min(len(pack["frame"]) / float(pack.get("required_candles") or 600), 1.0) if len(pack["frame"]) else 0.0,
                    "data_completeness": float(pack["frame"][["open", "high", "low", "close"]].notna().mean().mean()) if len(pack["frame"]) else 0.0,
                    "source_identity_reliability": 1.0 if pack["identity_ok"] else 0.0,
                    "regime_stability": None if _finite(regime.get("entropy")) is None else 1 - float(regime["entropy"]),
                    "structural_stability": None if _finite(brk.get("strength")) is None else 1 - float(brk["strength"]),
                    "rank_stability": None if _finite(rank_item.get("instability")) is None else 1 / (1 + float(rank_item["instability"])),
                    "feature_availability": float(np.mean([pack["frame"][c].notna().mean() for c in ("open", "high", "low", "close", "tick_volume", "spread")])) if len(pack["frame"]) else 0.0,
                    "outcome_settlement_completeness": 0.0 if not forecasts_total else settled / forecasts_total,
                }
                rel = _geometric_reliability(components, float(np.mean(effective_samples)) if effective_samples else 0.0)
                rel_payload = {
                    "daily_snapshot_id": daily_snapshot_id, "symbol": symbol,
                    **rel["components"], "aggregate_reliability": rel["aggregate"], "reliability_status": rel["status"],
                    "principal_reliability_weakness": rel["weakness"], "reliability_explanation": rel["explanation"],
                    "effective_sample_size": rel["effective_sample"], "component_weights_json": _canonical(rel["weights"]),
                    "reliability_version": RELIABILITY_VERSION, "validation_status": "SHADOW_ONLY",
                    "created_system_time": created,
                }
                rel_payload["content_hash"] = _hash(rel_payload)
                inserted["field10_reliability_shadow"] += int(_insert(conn, "field10_reliability_shadow", rel_payload))
                utility_item = next((r for r in utility_rows if r["symbol"] == symbol), {})
                rank_payload = {
                    "daily_snapshot_id": daily_snapshot_id, "symbol": symbol, "original_rank": parent.get("daily_rank"),
                    "candidate_utility": utility_item.get("utility"), "probability_rank_1": rank_item.get("prob1"),
                    "probability_rank_le_4": rank_item.get("prob4"), "median_rank": rank_item.get("median"),
                    "rank_percentile_low": rank_item.get("low"), "rank_percentile_high": rank_item.get("high"),
                    "rank_instability": rank_item.get("instability"), "score_gap_to_next_symbol": rank_item.get("gap"),
                    "bootstrap_draws": int(rank_item.get("draws") or 0), "block_length": int(rank_item.get("block") or 24),
                    "bootstrap_seed": str(rank_item.get("seed") or _hash({"snapshot": daily_snapshot_id, "symbol": symbol})),
                    "validation_status": rank_item.get("status", "INCOMPLETE"), "missing_reason": rank_item.get("missing_reason"),
                    "model_version": RANK_VERSION, "created_system_time": created,
                }
                rank_payload["content_hash"] = _hash(rank_payload)
                inserted["field10_rank_confidence_shadow"] += int(_insert(conn, "field10_rank_confidence_shadow", rank_payload))
                # Experiment registry: no candidate is promoted on this run.
                exp_id = "F10EXP-" + _hash({"snapshot": daily_snapshot_id, "symbol": symbol, "version": MODEL_VERSION})[:24]
                experiment = {
                    "experiment_id": exp_id, "parent_run_id": meta["parent_run_id"], "symbol": symbol,
                    "model_version": MODEL_VERSION, "canonical_run_id": parent.get("canonical_run_id"),
                    "broker_timestamp": parent.get("completed_candle"), "candidate_count": 1,
                    "candidate_names_json": _canonical([MODEL_VERSION]), "best_candidate": None,
                    "spa_statistic": None, "spa_p_value": None, "bootstrap_draws": int(rank_item.get("draws") or 0),
                    "block_length": int(rank_item.get("block") or 24), "settlement_verified": 0, "out_of_sample_verified": 0,
                    "validation_start": None, "validation_end": None, "promotion_status": "NOT_PROMOTED_INSUFFICIENT_SETTLED_HISTORY",
                    "parameter_hash": _hash({"feature": FEATURE_VERSION, "formula": FORMULA_VERSION, "threshold": THRESHOLD_VERSION}),
                    "result_json": _canonical({"classification": "SHADOW_ONLY", "rank": rank_item, "reliability": rel}),
                    "created_at": created, "parent_model_version": meta.get("model_version"), "candidate_model_version": MODEL_VERSION,
                    "feature_version": FEATURE_VERSION, "formula_version": FORMULA_VERSION, "threshold_version": THRESHOLD_VERSION,
                    "training_interval": None, "validation_interval": None, "test_interval": None,
                    "purging_interval": "horizon_hours", "embargo_interval": "horizon_hours",
                    "parameter_values_json": _canonical({"target_coverage": TARGET_COVERAGE, "minimum_model_rows": MIN_MODEL_ROWS}),
                    "evaluation_results_json": _canonical({"spa": "INSUFFICIENT_HISTORY", "pbo": "INSUFFICIENT_HISTORY", "deflated_sharpe": "INSUFFICIENT_HISTORY"}),
                    "source_code_hash": _hash(Path(__file__).read_text(encoding="utf-8")), "data_hash": source_hash,
                    "walk_forward_type": "ANCHORED_CHRONOLOGICAL_PURGED_EMBARGOED_SHADOW",
                    "spa_p_value_v2": None, "pbo_probability": None, "deflated_sharpe_probability": None,
                    "in_sample_metric": None, "out_of_sample_metric": None, "rank_correlation_stability": None,
                    "regime_stability": components.get("regime_stability"), "session_stability": None,
                    "promotion_gate_status": "BLOCKED_INSUFFICIENT_SETTLED_HISTORY",
                    "promotion_reasons_json": _canonical(["SPA unavailable", "PBO unavailable", "Deflated Sharpe unavailable", "settled outcomes inadequate"]),
                }
                _insert(conn, "field10_research_experiments", experiment)
                audit_details["symbols"][symbol] = {
                    "identity_ok": pack["identity_ok"], "reasons": pack["reasons"], "forecast_status": {h: pack["forecasts"][h].get("calibration_status") for h in HORIZONS},
                    "original_rank_preserved": parent.get("daily_rank"), "original_bias_preserved": parent.get("less_risky_bias"),
                }
            audit = {
                "audit_id": "F10AUD-" + _hash({"snapshot": daily_snapshot_id, "action": "PUBLISH_SHADOW", "version": MODEL_VERSION})[:24],
                "daily_snapshot_id": daily_snapshot_id, "action": "PUBLISH_INSTITUTIONAL_SHADOW",
                "status": "SHADOW_ONLY", "details_json": _canonical(audit_details), "created_system_time": created,
            }
            audit["content_hash"] = _hash(audit)
            inserted["field10_shadow_publication_audit"] += int(_insert(conn, "field10_shadow_publication_audit", audit))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"ok": True, "status": "SHADOW_ONLY", "daily_snapshot_id": daily_snapshot_id, "inserted": inserted, "symbols": audit_details["symbols"], "authority": ["field10_daily_snapshot", "field10_daily_snapshot_symbol"]}


def settle_matured_forecasts(state: Mapping[str, Any], *, path: Path | str = DB_PATH) -> dict[str, Any]:
    """Append outcomes once, using exact-symbol data and completed due candles only."""
    ready, missing = schema_ready(path)
    if not ready:
        return {"ok": False, "status": "MIGRATION_REQUIRED", "missing": missing}
    with _connect(path, read_only=True) as conn:
        pending = [dict(r) for r in conn.execute(
            "SELECT f.* FROM field10_forecast_ledger f LEFT JOIN field10_outcome_ledger o ON o.forecast_id=f.forecast_id AND o.settlement_version=? "
            "WHERE o.forecast_id IS NULL ORDER BY f.outcome_due_broker_time", (SETTLEMENT_VERSION,),
        )]
    inserted = 0
    skipped: list[dict[str, str]] = []
    for forecast in pending:
        symbol = str(forecast["symbol"])
        exact, reason = _exact_state_for_symbol(state, symbol)
        if exact is None:
            skipped.append({"forecast_id": forecast["forecast_id"], "reason": reason or "exact symbol unavailable"})
            continue
        raw = _find_ohlc(exact)
        forecast_tf = selected_timeframe(forecast.get("timeframe") or exact.get("timeframe") or "H1")
        frame, reasons = normalize_completed_timeframe(
            raw, cutoff=forecast["outcome_due_broker_time"], timeframe=forecast_tf, max_rows=2000, required_rows=2
        )
        if frame.empty or reasons or frame["time"].iloc[-1] < pd.to_datetime(forecast["outcome_due_broker_time"], utc=True):
            skipped.append({"forecast_id": forecast["forecast_id"], "reason": "; ".join(reasons) or "outcome due candle not completed"})
            continue
        origin = pd.to_datetime(forecast["completed_h1_candle"], utc=True)
        due = pd.to_datetime(forecast["outcome_due_broker_time"], utc=True)
        origin_row = frame.loc[frame.time == origin]
        path_rows = frame.loc[(frame.time > origin) & (frame.time <= due)]
        due_row = frame.loc[frame.time == due]
        if origin_row.empty or due_row.empty or path_rows.empty:
            skipped.append({"forecast_id": forecast["forecast_id"], "reason": "exact origin/due path unavailable"})
            continue
        origin_price = float(origin_row.close.iloc[-1])
        due_price = float(due_row.close.iloc[-1])
        realized = due_price / origin_price - 1
        mfe = float(path_rows.high.max() / origin_price - 1)
        mae = float(path_rows.low.min() / origin_price - 1)
        raw_ev = _finite(forecast.get("expected_value"))
        source_hash = _hash(frame.loc[(frame.time >= origin) & (frame.time <= due)].to_dict("records"))
        payload = {
            "forecast_id": forecast["forecast_id"], "settlement_version": SETTLEMENT_VERSION,
            "outcome_due_broker_time": forecast["outcome_due_broker_time"], "settled_at_broker_time": due.isoformat(),
            "realized_return": realized, "realized_mfe": mfe, "realized_mae": mae,
            "direction_outcome": "UP" if realized > 0 else "DOWN" if realized < 0 else "FLAT",
            "expected_value_reached": None if raw_ev is None else int(realized >= raw_ev),
            "transition_occurred": None, "spread_cost": None, "slippage_cost": None,
            "net_realized_return": None, "outcome_source_id": f"EXACT_SYMBOL_{symbol}",
            "outcome_source_hash": source_hash, "created_system_time": _utc_now(),
        }
        payload["content_hash"] = _hash(payload)
        with _connect(path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                inserted += int(_insert(conn, "field10_outcome_ledger", payload))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    return {"ok": True, "status": "SETTLED_APPEND_ONLY", "inserted": inserted, "pending_seen": len(pending), "skipped": skipped[:50]}


def load_shadow_evidence(*, daily_snapshot_id: str | None = None, path: Path | str = DB_PATH) -> dict[str, pd.DataFrame]:
    """Read-only UI loader. It cannot migrate, fit, fetch, publish or settle."""
    ready, _ = schema_ready(path)
    if not ready:
        return {name: pd.DataFrame() for name in ("forecast", "calibration", "conformal", "regime", "break", "session", "dependence", "reliability", "rank_confidence", "outcomes")}
    with _connect(path, read_only=True) as conn:
        if daily_snapshot_id is None:
            row = conn.execute("SELECT daily_snapshot_id FROM field10_daily_snapshot ORDER BY broker_day DESC LIMIT 1").fetchone()
            daily_snapshot_id = None if row is None else str(row[0])
        if not daily_snapshot_id:
            return {name: pd.DataFrame() for name in ("forecast", "calibration", "conformal", "regime", "break", "session", "dependence", "reliability", "rank_confidence", "outcomes")}
        queries = {
            "forecast": "SELECT * FROM field10_forecast_ledger WHERE daily_snapshot_id=? ORDER BY symbol,horizon_hours",
            "calibration": "SELECT * FROM field10_calibration_shadow WHERE daily_snapshot_id=? ORDER BY symbol,horizon_hours",
            "conformal": "SELECT * FROM field10_conformal_shadow WHERE daily_snapshot_id=? ORDER BY symbol,horizon_hours",
            "regime": "SELECT * FROM field10_regime_shadow WHERE daily_snapshot_id=? ORDER BY symbol",
            "break": "SELECT * FROM field10_structural_break_shadow WHERE daily_snapshot_id=? ORDER BY symbol",
            "session": "SELECT * FROM field10_session_shadow WHERE daily_snapshot_id=? ORDER BY session_rank IS NULL,session_rank,symbol",
            "dependence": "SELECT * FROM field10_dependence_shadow WHERE daily_snapshot_id=? ORDER BY symbol",
            "reliability": "SELECT * FROM field10_reliability_shadow WHERE daily_snapshot_id=? ORDER BY symbol",
            "rank_confidence": "SELECT * FROM field10_rank_confidence_shadow WHERE daily_snapshot_id=? ORDER BY original_rank IS NULL,original_rank,symbol",
            "outcomes": "SELECT o.*,f.symbol,f.horizon_hours,f.daily_snapshot_id FROM field10_outcome_ledger o JOIN field10_forecast_ledger f USING(forecast_id) WHERE f.daily_snapshot_id=? ORDER BY f.symbol,f.horizon_hours",
        }
        return {name: pd.read_sql_query(sql, conn, params=(daily_snapshot_id,)) for name, sql in queries.items()}


def renderer_contract_fingerprint(path: Path | str = DB_PATH) -> dict[str, Any]:
    """Fingerprint used by tests to prove the loader is read-only."""
    db = Path(path)
    before = db.stat().st_mtime_ns if db.exists() else None
    evidence = load_shadow_evidence(path=path)
    after = db.stat().st_mtime_ns if db.exists() else None
    return {"mtime_unchanged": before == after, "rows": {k: len(v) for k, v in evidence.items()}}
