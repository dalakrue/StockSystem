"""Institutional shadow-validation layer for Lunch Field 10.

The implementation is deliberately additive.  It reads the exact canonical
completed-candle generation and publishes research-only diagnostics inspired by
Hamilton (1989), Bai-Perron (1998), ADWIN, Kalman filtering, proper scoring
rules, conformal prediction, Diebold-Mariano, Hansen SPA, Ledoit-Wolf
shrinkage, and Rockafellar-Uryasev CVaR.

No function in this module mutates the production decision or refits the
protected Field 2/Field 3 engines.  Unsupported statistics are explicitly
reported as INSUFFICIENT_DATA rather than fabricated.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256
from math import erfc, log, sqrt
from typing import Any

import numpy as np
import pandas as pd

MODEL_VERSION = "TEN-PAPER-SHADOW-20260701-v2"
CALCULATION_VERSION = "field10-research-validation-20260701-v2"
STATE_KEY = "field10_ten_paper_research_20260701"


@dataclass(frozen=True)
class TenPaperFeatureFlags:
    research_shadow_mode: bool = True
    enable_markov_validation: bool = True
    enable_structural_break_validation: bool = True
    enable_adwin_drift: bool = True
    enable_kalman_smoothing: bool = True
    enable_proper_scoring: bool = True
    enable_conformal_intervals: bool = True
    enable_dm_testing: bool = True
    enable_spa_testing: bool = True
    enable_ledoit_wolf: bool = True
    enable_cvar: bool = True


@dataclass(frozen=True)
class TenPaperConfig:
    flags: TenPaperFeatureFlags = TenPaperFeatureFlags()
    minimum_regime_observations: int = 24
    minimum_break_observations: int = 96
    minimum_drift_observations: int = 40
    minimum_calibration_observations: int = 60
    minimum_conformal_observations: int = 60
    minimum_dm_observations: int = 40
    minimum_spa_observations: int = 60
    minimum_covariance_observations: int = 30
    minimum_cvar_observations: int = 60
    calibration_bins: int = 10
    target_coverage: float = 0.90
    max_structural_breaks: int = 3
    minimum_segment_length: int = 24
    adwin_delta: float = 0.002
    covariance_cluster_threshold: float = 0.80
    cvar_level: float = 0.95
    maximum_uncertainty_pct: float = 55.0
    maximum_transition_risk: float = 0.60
    maximum_tail_percentile: float = 0.85


DEFAULT_CONFIG = TenPaperConfig()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _bounded01(value: Any, default: float | None = None) -> float | None:
    number = _finite(value)
    if number is None:
        return default
    if number > 1.0 and number <= 100.0:
        number /= 100.0
    return float(np.clip(number, 0.0, 1.0))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _first_mapping(state: Mapping[str, Any], keys: Sequence[str]) -> Mapping[str, Any]:
    for key in keys:
        value = state.get(key)
        if isinstance(value, Mapping) and value:
            return value
    return {}


def resolve_canonical(state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(canonical, Mapping) and canonical:
        return dict(canonical)
    for key in (
        "canonical_decision_result_20260617", "canonical_shared_result_20260615",
        "canonical_result", "shared_calculation_result",
    ):
        value = state.get(key)
        if isinstance(value, Mapping) and value:
            return dict(value)
    try:
        from core.canonical_lookup_20260626 import resolve_canonical as _resolve
        value = _resolve(dict(state))
        if isinstance(value, Mapping):
            return dict(value)
    except Exception:
        pass
    return {}


def source_frame(state: Mapping[str, Any]) -> pd.DataFrame:
    for key in (
        "canonical_completed_ohlc_df_20260617", "market_data", "df", "data",
        "ohlc", "price_data", "canonical_ohlc_df_20260618",
    ):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy(deep=False)
    canonical = resolve_canonical(state)
    for key in ("history", "ohlc", "market_data"):
        value = canonical.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy(deep=False)
        if isinstance(value, list) and value:
            frame = pd.DataFrame(value)
            if not frame.empty:
                return frame
    return pd.DataFrame()


def _column(frame: pd.DataFrame, *candidates: str) -> str | None:
    if frame.empty:
        return None
    normalized = {str(c).strip().lower().replace("_", " "): str(c) for c in frame.columns}
    for candidate in candidates:
        key = candidate.strip().lower().replace("_", " ")
        if key in normalized:
            return normalized[key]
    for candidate in candidates:
        tokens = candidate.strip().lower().replace("_", " ").split()
        for column in frame.columns:
            lower = str(column).strip().lower().replace("_", " ")
            if all(token in lower for token in tokens):
                return str(column)
    return None


def _broker_wall_timestamp(value: Any) -> pd.Timestamp:
    """Parse canonical broker time without converting the wall clock to UTC."""
    try:
        stamp = pd.Timestamp(value)
    except Exception:
        return pd.NaT
    if pd.isna(stamp):
        return pd.NaT
    if stamp.tzinfo is not None:
        stamp = stamp.tz_localize(None)
    return stamp


def _broker_wall_series(values: Any) -> pd.Series:
    series = values if isinstance(values, pd.Series) else pd.Series(values)
    return series.map(_broker_wall_timestamp)


def _time_series(frame: pd.DataFrame) -> pd.Series:
    column = _column(frame, "broker timestamp", "event time utc", "datetime", "timestamp", "time", "date")
    if column:
        return _broker_wall_series(frame[column])
    if isinstance(frame.index, pd.DatetimeIndex):
        return _broker_wall_series(pd.Series(frame.index, index=frame.index))
    return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")


def extract_return_series(state: Mapping[str, Any]) -> pd.Series:
    frame = source_frame(state)
    close_col = _column(frame, "close")
    if frame.empty or close_col is None:
        return pd.Series(dtype=float)
    close = pd.to_numeric(frame[close_col], errors="coerce")
    times = _time_series(frame)
    result = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    if times.notna().any():
        result.index = pd.DatetimeIndex(times)
    return result.dropna().astype(float)


def _regime_sequence(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    timestamps: list[str] = []
    monitor = state.get("field3_regime_lifecycle_monitor_20260701")
    frames: list[pd.DataFrame] = []
    if isinstance(monitor, Mapping):
        value = monitor.get("history_25d")
        if isinstance(value, pd.DataFrame):
            frames.append(value)
        elif isinstance(value, list):
            frames.append(pd.DataFrame(value))
    details = state.get("regime_standard_detail_tables_published_20260618") or state.get("regime_standard_detail_tables_20260617")
    if isinstance(details, Mapping):
        for key in ("higher", "high", "middle", "medium", "lower", "low"):
            value = details.get(key)
            if isinstance(value, pd.DataFrame) and not value.empty:
                frames.append(value)
                break
    for frame in frames:
        regime_col = _column(frame, "existing higher regime", "higher standard regime", "regime")
        if regime_col is None:
            continue
        time = _time_series(frame)
        work = pd.DataFrame({"regime": frame[regime_col].astype(str), "time": time})
        work = work.loc[work["regime"].str.strip().ne("") & work["regime"].str.upper().ne("NAN")]
        if work.empty:
            continue
        if work["time"].notna().any():
            work = work.sort_values("time", kind="mergesort")
            timestamps = [pd.Timestamp(v).isoformat() if pd.notna(v) else "" for v in work["time"]]
        return work["regime"].str.upper().tolist(), timestamps
    regime = _mapping(canonical.get("regime"))
    current = regime.get("higher_regime") or regime.get("major_regime") or canonical.get("regime")
    return ([str(current).upper()] if current else []), []


def _production_action(canonical: Mapping[str, Any]) -> str:
    final = _mapping(canonical.get("final_decision"))
    value = (
        final.get("final_decision") or final.get("less_risky_decision")
        or canonical.get("final_decision") or canonical.get("decision") or "WAIT"
    )
    text = str(value).upper().strip()
    if "BUY" in text:
        return "BUY"
    if "SELL" in text:
        return "SELL"
    if "HOLD" in text:
        return "HOLD AND PROTECT"
    if "PULLBACK" in text:
        return "WAIT FOR PULLBACK"
    return "WAIT"


def _identity(canonical: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    run_id = str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or "")
    symbol = str(canonical.get("symbol") or state.get("symbol") or "EURUSD").upper()
    timeframe = str(canonical.get("timeframe") or state.get("timeframe") or "H1").upper()
    completed = canonical.get("latest_completed_candle_time") or canonical.get("broker_candle_time")
    completed_ts = _broker_wall_timestamp(completed)
    source_hash = str(
        canonical.get("source_snapshot_hash") or canonical.get("snapshot_hash")
        or canonical.get("source_id") or canonical.get("data_source_id") or ""
    )
    return {
        "canonical_run_id": run_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "completed_candle_time": pd.Timestamp(completed_ts).isoformat() if pd.notna(completed_ts) else "",
        "broker_date": pd.Timestamp(completed_ts).strftime("%Y-%m-%d") if pd.notna(completed_ts) else "",
        "broker_hour": int(pd.Timestamp(completed_ts).hour) if pd.notna(completed_ts) else None,
        "source_snapshot_hash": source_hash,
    }


def identity_integrity(canonical: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    identity = _identity(canonical, state)
    failures: list[str] = []
    if not identity["canonical_run_id"]:
        failures.append("canonical run_id missing")
    if not identity["completed_candle_time"]:
        failures.append("completed broker candle missing or invalid")
    if not identity["symbol"]:
        failures.append("symbol missing")
    if not identity["timeframe"]:
        failures.append("timeframe missing")
    if not identity["source_snapshot_hash"]:
        failures.append("source snapshot/source ID missing")
    return {**identity, "status": "FAIL" if failures else "PASS", "reasons": failures or ["canonical identity is complete"]}


def hamilton_regime_validation(states: Sequence[str], config: TenPaperConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    values = [str(v).upper().strip() for v in states if str(v).strip()]
    if len(values) < config.minimum_regime_observations:
        return {"status": "INSUFFICIENT_DATA", "sample_count": len(values), "probabilities": {}}
    unique = sorted(set(values))
    counts = pd.crosstab(pd.Series(values[:-1], name="from"), pd.Series(values[1:], name="to"), dropna=False)
    counts = counts.reindex(index=unique, columns=unique, fill_value=0).astype(float)
    smoothed = counts + 0.5
    transition = smoothed.div(smoothed.sum(axis=1), axis=0)
    current = values[-1]
    distribution = np.zeros(len(unique), dtype=float)
    distribution[unique.index(current)] = 1.0
    probabilities: dict[int, dict[str, float]] = {}
    for horizon in (1, 3, 6):
        projected = distribution @ np.linalg.matrix_power(transition.to_numpy(), horizon)
        probabilities[horizon] = {state: float(projected[i]) for i, state in enumerate(unique)}
    one = probabilities[1]
    ranked = sorted(one.items(), key=lambda item: (-item[1], item[0]))
    p_self = float(transition.loc[current, current])
    expected_duration = min(10000.0, 1.0 / max(1e-6, 1.0 - p_self))
    current_run = 1
    for value in reversed(values[:-1]):
        if value != current:
            break
        current_run += 1
    entropy = -sum(p * log(max(p, 1e-12)) for p in one.values()) / max(log(max(len(one), 2)), 1e-12)
    return {
        "status": "VALID",
        "sample_count": len(values),
        "current_regime": current,
        "most_likely_regime": ranked[0][0],
        "second_most_likely_regime": ranked[1][0] if len(ranked) > 1 else ranked[0][0],
        "current_regime_probability": float(one.get(current, 0.0)),
        "probability_gap": float(ranked[0][1] - ranked[1][1]) if len(ranked) > 1 else 1.0,
        "regime_entropy": float(np.clip(entropy, 0.0, 1.0)),
        "persistence_probability": p_self,
        "expected_duration_hours": float(expected_duration),
        "observed_age_hours": int(current_run),
        "estimated_remaining_hours": float(max(0.0, expected_duration - current_run)),
        "next_regime_probability": float(1.0 - one.get(current, 0.0)),
        "transition_risk_1h": float(1.0 - probabilities[1].get(current, 0.0)),
        "transition_risk_3h": float(1.0 - probabilities[3].get(current, 0.0)),
        "transition_risk_6h": float(1.0 - probabilities[6].get(current, 0.0)),
        "probabilities_1h": one,
        "transition_matrix": transition.round(8).to_dict(),
        "method": "Hamilton-style empirical Markov validation; production Field 3 regime unchanged",
    }


def _segment_sse(prefix: np.ndarray, prefix_sq: np.ndarray, start: int, end: int) -> float:
    count = end - start
    if count <= 0:
        return float("inf")
    total = prefix[end] - prefix[start]
    total_sq = prefix_sq[end] - prefix_sq[start]
    return max(0.0, float(total_sq - total * total / count))


def bai_perron_breaks(values: Sequence[float], timestamps: Sequence[Any] | None = None, config: TenPaperConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if len(array) < config.minimum_break_observations:
        return {"status": "INSUFFICIENT_DATA", "sample_count": int(len(array)), "break_count": 0}
    # Bound the quadratic dynamic program while preserving recent completed H1 evidence.
    if len(array) > 480:
        array = array[-480:]
        if timestamps is not None:
            timestamps = list(timestamps)[-480:]
    n = len(array)
    min_seg = min(config.minimum_segment_length, max(8, n // 5))
    max_breaks = min(config.max_structural_breaks, max(0, n // min_seg - 1))
    prefix = np.concatenate([[0.0], np.cumsum(array)])
    prefix_sq = np.concatenate([[0.0], np.cumsum(array * array)])
    # dp[k, j]: minimum SSE for k segments ending at j.
    max_segments = max_breaks + 1
    dp = np.full((max_segments + 1, n + 1), np.inf)
    prev = np.full((max_segments + 1, n + 1), -1, dtype=int)
    dp[1, min_seg:] = [_segment_sse(prefix, prefix_sq, 0, j) for j in range(min_seg, n + 1)]
    for segments in range(2, max_segments + 1):
        lower_end = segments * min_seg
        for end in range(lower_end, n + 1):
            starts = range((segments - 1) * min_seg, end - min_seg + 1)
            best_cost = np.inf
            best_start = -1
            for start in starts:
                cost = dp[segments - 1, start] + _segment_sse(prefix, prefix_sq, start, end)
                if cost < best_cost:
                    best_cost, best_start = cost, start
            dp[segments, end] = best_cost
            prev[segments, end] = best_start
    candidates: list[tuple[float, int]] = []
    for segments in range(1, max_segments + 1):
        sse = max(float(dp[segments, n]), 1e-18)
        parameter_count = segments * 2 - 1
        bic = n * log(sse / n) + parameter_count * log(n)
        candidates.append((bic, segments))
    _, selected_segments = min(candidates, key=lambda item: (item[0], item[1]))
    breaks: list[int] = []
    end = n
    segments = selected_segments
    while segments > 1:
        start = int(prev[segments, end])
        if start <= 0:
            break
        breaks.append(start)
        end = start
        segments -= 1
    breaks.reverse()
    break_times: list[str] = []
    if timestamps is not None:
        stamp_values = list(timestamps)
        for index in breaks:
            if 0 <= index < len(stamp_values):
                parsed = _broker_wall_timestamp(stamp_values[index])
                break_times.append(pd.Timestamp(parsed).isoformat() if pd.notna(parsed) else str(stamp_values[index]))
    segments_idx = [0, *breaks, n]
    means = [float(np.mean(array[a:b])) for a, b in zip(segments_idx[:-1], segments_idx[1:])]
    strength = max((abs(b - a) for a, b in zip(means[:-1], means[1:])), default=0.0)
    scale = float(np.std(array, ddof=1)) if n > 1 else 0.0
    normalized_strength = strength / max(scale, 1e-12)
    detected = bool(breaks and normalized_strength >= 0.50)
    return {
        "status": "BREAK" if detected else "STABLE",
        "sample_count": n,
        "structural_break_detected": detected,
        "break_count": len(breaks),
        "break_indices": breaks,
        "break_times": break_times,
        "last_break_time": break_times[-1] if break_times else None,
        "segment_means": means,
        "break_strength": float(normalized_strength),
        "current_segment_start_index": int(breaks[-1]) if breaks else 0,
        "recalibration_required": bool(detected and breaks[-1] >= n - max(min_seg * 2, 48)) if breaks else False,
        "method": "Bai-Perron-style global dynamic-programming segmentation with BIC selection",
    }


def adwin_drift(values: Sequence[float], config: TenPaperConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    """Efficient ADWIN-style adaptive-window replay over completed observations.

    The previous implementation called a full split search after every single
    observation, which was cubic in practice.  This version preserves the
    concentration-bound change test but evaluates vectorized split candidates
    at bounded checkpoints.  It remains chronological and deterministic.
    """
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if len(array) < config.minimum_drift_observations:
        return {"status": "INSUFFICIENT_DATA", "sample_count": int(len(array)), "drift_status": "INSUFFICIENT_DATA"}
    # Bounded recent evidence prevents old observations from consuming RAM/CPU;
    # the full audit history remains in the project's persistent history store.
    max_window = 480
    if len(array) > max_window:
        array = array[-max_window:]
    min_window = max(10, min(24, len(array) // 4))
    check_interval = 4
    active: list[float] = []
    stale_count = 0
    last_detection: dict[str, Any] | None = None
    log_term = log(2.0 / max(config.adwin_delta, 1e-12))

    def scan(window: np.ndarray) -> dict[str, Any] | None:
        n = len(window)
        if n < 2 * min_window:
            return None
        prefix = np.concatenate([[0.0], np.cumsum(window)])
        splits = np.arange(min_window, n - min_window + 1, dtype=int)
        old_n = splits.astype(float)
        new_n = (n - splits).astype(float)
        old_mean = prefix[splits] / old_n
        new_mean = (prefix[n] - prefix[splits]) / new_n
        n_eff = 1.0 / (1.0 / old_n + 1.0 / new_n)
        variance = max(float(np.var(window)), 1e-18)
        epsilon = np.sqrt(2.0 * variance * log_term / np.maximum(n_eff, 1.0)) + 2.0 * log_term / (3.0 * np.maximum(n_eff, 1.0))
        magnitude = np.abs(old_mean - new_mean)
        candidates = np.flatnonzero(magnitude > epsilon)
        if candidates.size == 0:
            return None
        best_local = int(candidates[np.argmax(magnitude[candidates])])
        split = int(splits[best_local])
        return {
            "split": split,
            "old_mean": float(old_mean[best_local]),
            "new_mean": float(new_mean[best_local]),
            "magnitude": float(magnitude[best_local]),
            "window_size_before": n,
            "window_size_after": n - split,
        }

    for index, value in enumerate(array, start=1):
        active.append(float(value))
        if len(active) > max_window:
            active = active[-max_window:]
        if len(active) < 2 * min_window or (index % check_interval and index != len(array)):
            continue
        detection = scan(np.asarray(active, dtype=float))
        if detection is not None:
            split = int(detection["split"])
            stale_count += split
            active = active[split:]
            last_detection = detection

    if last_detection is None:
        return {
            "status": "STABLE", "sample_count": int(len(array)), "drift_status": "STABLE",
            "adaptive_window_size": len(active), "drift_magnitude": 0.0,
            "stale_history_removed_count": stale_count, "recalibration_required": False,
            "method": "vectorized ADWIN-style concentration-bound adaptive window",
        }
    magnitude = float(last_detection.get("magnitude") or 0.0)
    scale = float(np.std(array, ddof=1)) if len(array) > 1 else 0.0
    standardized = magnitude / max(scale, 1e-12)
    status = "DRIFT" if standardized >= 1.0 else "WARNING"
    return {
        "status": status, "sample_count": int(len(array)), "drift_status": status,
        "adaptive_window_size": int(len(active)),
        "drift_magnitude": magnitude, "standardized_magnitude": standardized,
        "old_mean": last_detection.get("old_mean"), "new_mean": last_detection.get("new_mean"),
        "stale_history_removed_count": stale_count, "recalibration_required": status == "DRIFT",
        "method": "vectorized ADWIN-style concentration-bound adaptive window",
    }


def kalman_local_trend(values: Sequence[float], config: TenPaperConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if len(array) < 8:
        return {"status": "INSUFFICIENT_DATA", "sample_count": int(len(array))}
    x = np.array([array[0], 0.0], dtype=float)
    p = np.eye(2, dtype=float)
    f = np.array([[1.0, 1.0], [0.0, 1.0]], dtype=float)
    h = np.array([[1.0, 0.0]], dtype=float)
    variance = max(float(np.var(array)), 1e-10)
    q = np.array([[variance * 0.01, 0.0], [0.0, variance * 0.001]], dtype=float)
    r = np.array([[variance * 0.10]], dtype=float)
    innovations: list[float] = []
    innovation_vars: list[float] = []
    for observation in array:
        x = f @ x
        p = f @ p @ f.T + q
        innovation = float(observation - (h @ x)[0])
        s = float((h @ p @ h.T + r)[0, 0])
        k = (p @ h.T) / max(s, 1e-12)
        x = x + k[:, 0] * innovation
        p = (np.eye(2) - k @ h) @ p
        innovations.append(innovation)
        innovation_vars.append(s)
    z = innovations[-1] / sqrt(max(innovation_vars[-1], 1e-12))
    covariance_trace = float(np.trace(p))
    stability = float(np.clip(1.0 / (1.0 + covariance_trace / max(variance, 1e-12)), 0.0, 1.0))
    return {
        "status": "VALID", "sample_count": int(len(array)),
        "filtered_state": float(x[0]), "filtered_slope": float(x[1]),
        "state_covariance": p.tolist(), "state_covariance_trace": covariance_trace,
        "innovation": float(innovations[-1]), "innovation_z_score": float(z),
        "state_stability": stability, "abnormal_observation_flag": abs(z) >= 3.0,
    }


def _binary_outcomes(series: pd.Series) -> np.ndarray:
    if series.empty:
        return np.array([], dtype=float)
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().mean() >= 0.8:
        values = numeric.to_numpy(dtype=float)
        unique = set(np.unique(values[np.isfinite(values)]).tolist())
        if unique.issubset({0.0, 1.0}):
            return values
        return np.where(values > 0, 1.0, 0.0)
    text = series.astype(str).str.upper()
    mapped = text.map({"TRUE": 1.0, "CORRECT": 1.0, "WIN": 1.0, "BUY": 1.0, "UP": 1.0,
                       "FALSE": 0.0, "INCORRECT": 0.0, "LOSS": 0.0, "SELL": 0.0, "DOWN": 0.0})
    return mapped.to_numpy(dtype=float)


def _settled_oos_filter(frame: pd.DataFrame) -> tuple[pd.DataFrame, bool, bool]:
    """Filter settled rows and verify explicit chronological OOS markers when available."""
    work = frame.copy(deep=False)
    settlement_verified = False
    oos_verified = False
    status_col = _column(work, "outcome status", "settlement status", "result status")
    if status_col:
        values = work[status_col].astype(str).str.upper().str.strip()
        settled = values.isin({"SETTLED", "RESOLVED", "COMPLETED", "COMPLETE", "CLOSED", "FINAL"})
        work = work.loc[settled]
        settlement_verified = True
    oos_bool_col = _column(work, "is out of sample", "out of sample", "walk forward validated")
    split_col = _column(work, "evaluation split", "data split", "walk forward role", "sample role")
    if oos_bool_col:
        raw = work[oos_bool_col]
        if raw.dtype == bool:
            oos_mask = raw.fillna(False)
        else:
            oos_mask = raw.astype(str).str.upper().str.strip().isin({"TRUE", "1", "YES", "Y", "OOS", "OUT_OF_SAMPLE"})
        work = work.loc[oos_mask]
        oos_verified = True
    elif split_col:
        split = work[split_col].astype(str).str.upper().str.replace("-", "_", regex=False).str.strip()
        oos_mask = split.isin({"VALIDATION", "TEST", "FINAL_TEST", "OOS", "OUT_OF_SAMPLE", "WALK_FORWARD"})
        work = work.loc[oos_mask]
        oos_verified = True
    return work, settlement_verified, oos_verified


def _validation_time_range(frame: pd.DataFrame) -> tuple[str, str]:
    if frame.empty:
        return "", ""
    times = _time_series(frame).dropna()
    if times.empty:
        return "", ""
    return pd.Timestamp(times.min()).isoformat(), pd.Timestamp(times.max()).isoformat()


def _calibration_arrays(state: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, str]:
    candidates: list[pd.DataFrame] = []
    for key in (
        "prediction_outcomes", "prediction_outcome_history_20260621", "field2_outcomes",
        "full_metric_history_df_20260618", "field8_integrated_history_20260624",
    ):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            candidates.append(value)
    for frame in candidates:
        frame, settlement_verified, _ = _settled_oos_filter(frame)
        if frame.empty:
            continue
        probability_col = _column(frame, "predicted probability", "calibrated probability", "confidence", "probability")
        outcome_col = _column(frame, "outcome", "correct", "actual direction", "realized direction", "success")
        if probability_col and outcome_col:
            probability = pd.to_numeric(frame[probability_col], errors="coerce").to_numpy(dtype=float)
            probability = np.where(probability > 1.0, probability / 100.0, probability)
            outcome = _binary_outcomes(frame[outcome_col])
            mask = np.isfinite(probability) & np.isfinite(outcome)
            suffix = "|settled_verified" if settlement_verified else "|settlement_status_unavailable"
            return outcome[mask], np.clip(probability[mask], 1e-12, 1 - 1e-12), f"{probability_col}|{outcome_col}{suffix}"
    return np.array([], dtype=float), np.array([], dtype=float), ""


def proper_scoring(state: Mapping[str, Any], config: TenPaperConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    y, p, source = _calibration_arrays(state)
    if len(y) < config.minimum_calibration_observations:
        return {"status": "INSUFFICIENT_DATA", "sample_count": int(len(y)), "source": source}
    from research_quant.calibration.calibration_metrics import brier_score, expected_calibration_error, log_loss
    bins: list[dict[str, Any]] = []
    edges = np.linspace(0.0, 1.0, config.calibration_bins + 1)
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (p >= low) & (p < high if high < 1.0 else p <= high)
        if mask.any():
            bins.append({
                "lower": float(low), "upper": float(high), "count": int(mask.sum()),
                "predicted": float(p[mask].mean()), "observed": float(y[mask].mean()),
                "gap": float(abs(p[mask].mean() - y[mask].mean())),
            })
    ece = float(expected_calibration_error(y, p, bins=config.calibration_bins))
    over = float(np.mean(np.maximum(p - y, 0.0)))
    under = float(np.mean(np.maximum(y - p, 0.0)))
    grade = "A" if ece <= 0.05 else ("B" if ece <= 0.10 else ("C" if ece <= 0.20 else "D"))
    return {
        "status": "VALID", "sample_count": int(len(y)), "source": source,
        "brier_score": float(brier_score(y, p)), "log_loss": float(log_loss(y, p)),
        "calibration_error": ece, "calibration_bins": bins,
        "overconfidence_penalty": over, "underconfidence_penalty": under,
        "reliability_grade": grade,
    }


def _forecast_residuals(state: Mapping[str, Any]) -> tuple[np.ndarray, float | None, str]:
    for key in (
        "prediction_outcomes", "prediction_outcome_history_20260621", "field2_outcomes",
        "full_metric_history_df_20260618", "powerbi_projection_history",
    ):
        frame = state.get(key)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        frame, settlement_verified, _ = _settled_oos_filter(frame)
        if frame.empty:
            continue
        residual_col = _column(frame, "absolute residual", "absolute error", "forecast error", "residual")
        if residual_col:
            residual = np.abs(pd.to_numeric(frame[residual_col], errors="coerce").to_numpy(dtype=float))
            residual = residual[np.isfinite(residual)]
            current = _finite(frame[residual_col].iloc[-1]) if len(frame) else None
            return residual, current, residual_col
        predicted_col = _column(frame, "predicted price", "forecast price", "prediction")
        actual_col = _column(frame, "actual price", "realized price", "close")
        if predicted_col and actual_col and predicted_col != actual_col:
            predicted = pd.to_numeric(frame[predicted_col], errors="coerce").to_numpy(dtype=float)
            actual = pd.to_numeric(frame[actual_col], errors="coerce").to_numpy(dtype=float)
            residual = np.abs(actual - predicted)
            residual = residual[np.isfinite(residual)]
            current = _finite(predicted[-1]) if len(predicted) else None
            return residual, current, f"{predicted_col}|{actual_col}"
    return np.array([], dtype=float), None, ""


def conformal_intervals(state: Mapping[str, Any], canonical: Mapping[str, Any], config: TenPaperConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    residuals, point, source = _forecast_residuals(state)
    field2 = _first_mapping(state, ("field2_quant_upgrade_20260629", "powerbi_projection_result_20260619", "powerbi_calibrated_bundle_20260617"))
    if point is None:
        point = _finite(field2.get("predicted_1h_price") or field2.get("point_prediction") or canonical.get("predicted_1h_price"))
    if len(residuals) < config.minimum_conformal_observations or point is None:
        return {"status": "INSUFFICIENT_DATA", "sample_count": int(len(residuals)), "source": source, "point_prediction": point}
    from research_quant.conformal.adaptive_intervals import adaptive_residual_quantile
    alpha = 1.0 - config.target_coverage
    quantile = float(adaptive_residual_quantile(residuals, alpha=alpha))
    # Retrospective leave-one-step style coverage proxy using the fixed empirical quantile.
    coverage = float(np.mean(residuals <= quantile))
    width = float(2.0 * quantile)
    return {
        "status": "VALID" if coverage >= config.target_coverage - 0.05 else "COVERAGE_AT_RISK",
        "sample_count": int(len(residuals)), "source": source,
        "point_prediction": float(point), "prediction_lower": float(point - quantile),
        "prediction_upper": float(point + quantile), "interval_width": width,
        "target_coverage": float(config.target_coverage), "realized_coverage": coverage,
        "coverage_error": float(abs(coverage - config.target_coverage)),
    }


def _error_arrays(state: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, int, str, bool, str, str]:
    for key in ("forecast_comparison_history", "prediction_outcomes", "field2_outcomes", "full_metric_history_df_20260618"):
        frame = state.get(key)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        frame, settlement_verified, oos_verified = _settled_oos_filter(frame)
        if frame.empty:
            continue
        production_col = _column(frame, "production error", "baseline error", "existing error")
        candidate_col = _column(frame, "candidate error", "research error", "shadow error")
        if production_col and candidate_col:
            production = pd.to_numeric(frame[production_col], errors="coerce").to_numpy(dtype=float)
            candidate = pd.to_numeric(frame[candidate_col], errors="coerce").to_numpy(dtype=float)
            mask = np.isfinite(production) & np.isfinite(candidate)
            horizon_col = _column(frame, "horizon")
            horizon = 1
            if horizon_col:
                horizon_num = pd.to_numeric(frame[horizon_col].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
                if horizon_num.notna().any():
                    horizon = int(max(1, horizon_num.dropna().median()))
            validation_start, validation_end = _validation_time_range(frame.loc[mask])
            source = f"{production_col}|{candidate_col}|settled={settlement_verified}|oos={oos_verified}"
            return production[mask], candidate[mask], horizon, source, oos_verified, validation_start, validation_end
    return np.array([], dtype=float), np.array([], dtype=float), 1, "", False, "", ""


def diebold_mariano(state: Mapping[str, Any], config: TenPaperConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    production, candidate, horizon, source, oos_verified, validation_start, validation_end = _error_arrays(state)
    n = min(len(production), len(candidate))
    if n < config.minimum_dm_observations:
        return {"status": "INSUFFICIENT_DATA", "sample_count": n, "source": source, "out_of_sample_verified": oos_verified}
    loss_diff = production[:n] ** 2 - candidate[:n] ** 2
    mean_diff = float(np.mean(loss_diff))
    centered = loss_diff - mean_diff
    lag = min(max(0, horizon - 1), n - 2)
    gamma0 = float(np.dot(centered, centered) / n)
    long_run = gamma0
    for index in range(1, lag + 1):
        gamma = float(np.dot(centered[index:], centered[:-index]) / n)
        weight = 1.0 - index / (lag + 1)
        long_run += 2.0 * weight * gamma
    variance_mean = max(long_run / n, 1e-18)
    statistic = mean_diff / sqrt(variance_mean)
    p_value = float(erfc(abs(statistic) / sqrt(2.0)))
    statistically_superior = bool(mean_diff > 0 and p_value < 0.05)
    return {
        "status": "VALID", "sample_count": n, "source": source,
        "mean_loss_difference": mean_diff, "dm_statistic": float(statistic),
        "dm_p_value": p_value, "effect_size": float(mean_diff / max(np.std(loss_diff, ddof=1), 1e-12)),
        "candidate_superior": statistically_superior,
        "promotion_eligible": bool(statistically_superior and oos_verified),
        "out_of_sample_verified": oos_verified,
        "validation_start": validation_start, "validation_end": validation_end,
        "dependence_lag": lag,
    }


def hansen_spa(state: Mapping[str, Any], config: TenPaperConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    frame = None
    for key in ("experiment_loss_history", "forecast_comparison_history", "prediction_outcomes"):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            frame = value
            break
    if frame is None:
        return {"status": "INSUFFICIENT_DATA", "sample_count": 0, "candidate_count": 0}
    frame, settlement_verified, oos_verified = _settled_oos_filter(frame)
    benchmark_col = _column(frame, "benchmark loss", "production loss", "baseline loss")
    candidate_cols = [str(c) for c in frame.columns if str(c).lower().startswith(("candidate_loss_", "candidate loss ", "research_loss_"))]
    if benchmark_col is None or not candidate_cols:
        return {"status": "INSUFFICIENT_DATA", "sample_count": int(len(frame)), "candidate_count": len(candidate_cols)}
    validation_start, validation_end = _validation_time_range(frame)
    benchmark = pd.to_numeric(frame[benchmark_col], errors="coerce")
    candidates = frame[candidate_cols].apply(pd.to_numeric, errors="coerce")
    valid = benchmark.notna() & candidates.notna().all(axis=1)
    benchmark = benchmark.loc[valid].to_numpy(dtype=float)
    candidate_matrix = candidates.loc[valid].to_numpy(dtype=float)
    n = len(benchmark)
    if n < config.minimum_spa_observations:
        return {"status": "INSUFFICIENT_DATA", "sample_count": n, "candidate_count": len(candidate_cols)}
    differential = benchmark[:, None] - candidate_matrix
    means = differential.mean(axis=0)
    standard = differential.std(axis=0, ddof=1) / sqrt(n)
    observed = float(np.max(np.where(standard > 0, means / standard, -np.inf)))
    # Deterministic moving-block bootstrap to preserve H1 dependence.
    rng = np.random.default_rng(20260701)
    block = max(4, int(round(n ** (1 / 3))))
    draws = 300
    centered = differential - means
    bootstrap_stats: list[float] = []
    for _ in range(draws):
        pieces: list[np.ndarray] = []
        while sum(len(piece) for piece in pieces) < n:
            start = int(rng.integers(0, max(1, n - block + 1)))
            pieces.append(centered[start:start + block])
        sample = np.concatenate(pieces, axis=0)[:n]
        sample_mean = sample.mean(axis=0)
        sample_std = sample.std(axis=0, ddof=1) / sqrt(n)
        bootstrap_stats.append(float(np.max(np.where(sample_std > 0, sample_mean / sample_std, -np.inf))))
    p_value = float((1 + sum(value >= observed for value in bootstrap_stats)) / (draws + 1))
    best_index = int(np.nanargmax(means))
    return {
        "status": "VALID", "sample_count": n, "candidate_count": len(candidate_cols),
        "spa_statistic": observed, "spa_p_value": p_value,
        "best_candidate": candidate_cols[best_index], "best_mean_advantage": float(means[best_index]),
        "superior_predictive_ability": bool(means[best_index] > 0 and p_value < 0.05),
        "promotion_status": "VALIDATION_PASSED" if means[best_index] > 0 and p_value < 0.05 and oos_verified else "RESEARCH_ONLY",
        "candidate_names": candidate_cols,
        "settlement_verified": settlement_verified, "out_of_sample_verified": oos_verified,
        "validation_start": validation_start, "validation_end": validation_end,
        "bootstrap_draws": draws, "block_length": block,
    }


def _ledoit_wolf_covariance(frame: pd.DataFrame) -> tuple[np.ndarray, float]:
    """Compute Ledoit-Wolf linear shrinkage without importing heavy sklearn."""
    x = frame.to_numpy(dtype=float)
    x = x - np.mean(x, axis=0, keepdims=True)
    n_samples, n_features = x.shape
    empirical = (x.T @ x) / max(n_samples, 1)
    mu = float(np.trace(empirical) / max(n_features, 1))
    target = mu * np.eye(n_features, dtype=float)
    delta = float(np.sum((empirical - target) ** 2) / max(n_features, 1))
    if delta <= 1e-30:
        return empirical, 0.0
    x2 = x * x
    beta_matrix = (x2.T @ x2) / max(n_samples, 1) - empirical * empirical
    beta = float(np.sum(beta_matrix) / max(n_features * n_samples, 1))
    shrinkage = float(np.clip(min(max(beta, 0.0), delta) / delta, 0.0, 1.0))
    covariance = (1.0 - shrinkage) * empirical + shrinkage * target
    return covariance, shrinkage


def ledoit_wolf_risk_all(cross_symbol_returns: Mapping[str, pd.Series] | None, config: TenPaperConfig = DEFAULT_CONFIG) -> dict[str, dict[str, Any]]:
    """Calculate one covariance matrix and derive symbol-level risk diagnostics."""
    if not cross_symbol_returns or len(cross_symbol_returns) < 2:
        return {}
    frame = pd.concat({str(k): pd.Series(v, dtype=float) for k, v in cross_symbol_returns.items()}, axis=1).dropna(how="any")
    if len(frame) < config.minimum_covariance_observations or frame.shape[1] < 2:
        return {}
    # Bound the covariance history; recent H1 evidence is sufficient and keeps
    # multi-symbol Field 10 opening lightweight on phones/Streamlit Cloud.
    frame = frame.tail(1500)
    covariance, shrinkage = _ledoit_wolf_covariance(frame)
    scale = np.sqrt(np.clip(np.diag(covariance), 1e-18, None))
    correlation = covariance / np.outer(scale, scale)
    symbols = list(frame.columns)
    condition = float(np.linalg.cond(covariance))
    matrix_hash = sha256(np.ascontiguousarray(correlation).tobytes()).hexdigest()[:24]
    results: dict[str, dict[str, Any]] = {}
    for index, symbol in enumerate(symbols):
        peers = [(symbols[j], float(correlation[index, j])) for j in range(len(symbols)) if j != index]
        peers.sort(key=lambda item: (-abs(item[1]), item[0]))
        cluster = [name for name, corr in peers if abs(corr) >= config.covariance_cluster_threshold]
        cluster_corrs = [abs(corr) for _, corr in peers if abs(corr) >= config.covariance_cluster_threshold]
        avg_cluster = float(np.mean(cluster_corrs)) if cluster_corrs else 0.0
        penalty = float(np.clip(avg_cluster * min(1.0, len(cluster) / max(1, len(symbols) - 1)), 0.0, 1.0))
        results[symbol] = {
            "status": "VALID", "sample_count": int(len(frame)), "symbol_count": len(symbols),
            "shrinkage_intensity": shrinkage,
            "covariance_condition_number": condition,
            "correlation_cluster": cluster, "strongest_peer": peers[0][0] if peers else None,
            "strongest_correlation": peers[0][1] if peers else None,
            "top_correlations": peers[:5],
            "average_cluster_correlation": avg_cluster,
            "effective_diversification": float(max(1.0, len(symbols) * (1.0 - penalty))),
            "duplicate_exposure_penalty": penalty,
            "portfolio_concentration_warning": bool(cluster),
            "correlation_matrix_hash": matrix_hash,
            "method": "Ledoit-Wolf linear covariance shrinkage; one shared fit per parent run",
        }
    return results


def ledoit_wolf_risk(symbol: str, cross_symbol_returns: Mapping[str, pd.Series] | None, config: TenPaperConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    results = ledoit_wolf_risk_all(cross_symbol_returns, config)
    if results:
        return results.get(symbol) or next(iter(results.values()))
    sample_count = 0
    symbol_count = len(cross_symbol_returns or {})
    if cross_symbol_returns:
        with np.errstate(all="ignore"):
            try:
                sample_count = int(len(pd.concat({str(k): pd.Series(v, dtype=float) for k, v in cross_symbol_returns.items()}, axis=1).dropna(how="any")))
            except Exception:
                sample_count = 0
    return {"status": "INSUFFICIENT_DATA", "sample_count": sample_count, "symbol_count": symbol_count}


def cvar_tail_risk(state: Mapping[str, Any], returns: pd.Series, config: TenPaperConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    losses: np.ndarray = np.array([], dtype=float)
    basis = ""
    for key in ("strategy_returns", "realized_strategy_returns", "trade_history", "prediction_outcomes"):
        value = state.get(key)
        if not isinstance(value, pd.DataFrame) or value.empty:
            continue
        column = _column(value, "net return", "strategy return", "pnl", "profit loss", "realized loss")
        if column:
            raw = pd.to_numeric(value[column], errors="coerce").to_numpy(dtype=float)
            if "loss" in column.lower():
                losses = raw[np.isfinite(raw)]
            else:
                losses = -raw[np.isfinite(raw)]
            basis = column
            break
    if len(losses) == 0 and not returns.empty:
        losses = -returns.to_numpy(dtype=float)
        losses = losses[np.isfinite(losses)]
        basis = "negative completed-H1 market return proxy"
    if len(losses) < config.minimum_cvar_observations:
        return {"status": "INSUFFICIENT_DATA", "sample_count": int(len(losses)), "basis": basis}
    beta = config.cvar_level
    var = float(np.quantile(losses, beta, method="higher"))
    tail = losses[losses >= var]
    cvar = float(np.mean(tail)) if len(tail) else var
    percentile = float(np.mean(losses <= cvar))
    volatility = float(np.std(losses, ddof=1)) if len(losses) > 1 else 0.0
    cvar_to_volatility = float(abs(cvar) / max(volatility, 1e-12))
    grade = "A" if cvar_to_volatility <= 1.5 else ("B" if cvar_to_volatility <= 2.0 else ("C" if cvar_to_volatility <= 3.0 else "D"))
    return {
        "status": "VALID", "sample_count": int(len(losses)), "basis": basis,
        "var_95": var, "cvar_95": cvar, "tail_observation_count": int(len(tail)),
        "expected_adverse_excursion": float(np.mean(np.maximum(losses, 0.0))),
        "cvar_percentile": percentile, "cvar_to_volatility": cvar_to_volatility,
        "tail_risk_grade": grade,
        "research_risk_penalty": float(np.clip(cvar_to_volatility / 4.0, 0.0, 1.0)),
    }


def _quality_grade(score: float, critical_fail: bool, drift_status: str, sample_sufficient: bool) -> str:
    if critical_fail:
        return "D"
    if score >= 90 and drift_status == "STABLE" and sample_sufficient:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    return "D"


def _status_score(status: str, valid: float = 1.0, warning: float = 0.5) -> float:
    value = str(status or "").upper()
    if value in {"VALID", "PASS", "STABLE"}:
        return valid
    if value in {"WARNING", "COVERAGE_AT_RISK", "RESEARCH_ONLY"}:
        return warning
    return 0.0


def build_ten_paper_validation(
    state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None, *,
    cross_symbol_returns: Mapping[str, pd.Series] | None = None,
    portfolio_risk: Mapping[str, Any] | None = None,
    config: TenPaperConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    canonical = resolve_canonical(state, canonical)
    integrity = identity_integrity(canonical, state)
    identity = {key: integrity[key] for key in (
        "canonical_run_id", "symbol", "timeframe", "completed_candle_time",
        "broker_date", "broker_hour", "source_snapshot_hash",
    )}
    frame = source_frame(state)
    returns = extract_return_series(state)
    regimes, regime_times = _regime_sequence(state, canonical)
    flags = config.flags

    hamilton = hamilton_regime_validation(regimes, config) if flags.enable_markov_validation else {"status": "DISABLED"}
    break_result = bai_perron_breaks(returns.to_numpy(), list(returns.index), config) if flags.enable_structural_break_validation else {"status": "DISABLED"}
    drift_input = np.abs(returns.to_numpy(dtype=float))
    drift = adwin_drift(drift_input, config) if flags.enable_adwin_drift else {"status": "DISABLED", "drift_status": "DISABLED"}
    kalman = kalman_local_trend(returns.to_numpy(dtype=float), config) if flags.enable_kalman_smoothing else {"status": "DISABLED"}
    scoring = proper_scoring(state, config) if flags.enable_proper_scoring else {"status": "DISABLED"}
    conformal = conformal_intervals(state, canonical, config) if flags.enable_conformal_intervals else {"status": "DISABLED"}
    dm = diebold_mariano(state, config) if flags.enable_dm_testing else {"status": "DISABLED"}
    spa = hansen_spa(state, config) if flags.enable_spa_testing else {"status": "DISABLED"}
    covariance = (dict(portfolio_risk) if isinstance(portfolio_risk, Mapping) else ledoit_wolf_risk(identity["symbol"], cross_symbol_returns, config)) if flags.enable_ledoit_wolf else {"status": "DISABLED"}
    cvar = cvar_tail_risk(state, returns, config) if flags.enable_cvar else {"status": "DISABLED"}

    critical_failures = list(integrity.get("reasons") or []) if integrity.get("status") == "FAIL" else []
    if drift.get("drift_status") == "DRIFT":
        critical_failures.append("severe concept drift detected")
    if bool(break_result.get("recalibration_required")):
        critical_failures.append("recent structural break requires recalibration")

    calibration_quality = 1.0 - float(scoring.get("calibration_error") or 1.0) if scoring.get("status") == "VALID" else 0.0
    coverage_quality = 1.0 - float(conformal.get("coverage_error") or 1.0) if conformal.get("status") in {"VALID", "COVERAGE_AT_RISK"} else 0.0
    stability_quality = 1.0 if drift.get("drift_status") == "STABLE" else (0.5 if drift.get("drift_status") == "WARNING" else 0.0)
    structural_quality = 0.0 if break_result.get("recalibration_required") else (0.5 if break_result.get("structural_break_detected") else 1.0)
    markov_quality = (1.0 - float(hamilton.get("regime_entropy") or 1.0)) if hamilton.get("status") == "VALID" else 0.0
    validation_quality = max(_status_score(dm.get("status")), _status_score(spa.get("status")))
    sample_count = max(len(frame), len(returns), len(regimes), int(scoring.get("sample_count") or 0))
    sample_sufficient = sample_count >= config.minimum_calibration_observations
    sample_quality = min(1.0, sample_count / max(config.minimum_calibration_observations, 1))

    components = {
        "calibration": calibration_quality,
        "conformal_coverage": coverage_quality,
        "drift_stability": stability_quality,
        "structural_stability": structural_quality,
        "regime_certainty": markov_quality,
        "out_of_sample_validation": validation_quality,
        "sample_sufficiency": sample_quality,
    }
    weights = {
        "calibration": 0.20, "conformal_coverage": 0.15, "drift_stability": 0.15,
        "structural_stability": 0.15, "regime_certainty": 0.15,
        "out_of_sample_validation": 0.10, "sample_sufficiency": 0.10,
    }
    research_reliability = 100.0 * sum(weights[name] * components[name] for name in weights)
    if covariance.get("status") == "VALID":
        research_reliability -= 10.0 * float(covariance.get("duplicate_exposure_penalty") or 0.0)
    if cvar.get("status") == "VALID":
        research_reliability -= 10.0 * float(cvar.get("research_risk_penalty") or 0.0)
    research_reliability = float(np.clip(research_reliability, 0.0, 100.0))

    completeness = 100.0 * np.mean([value.get("status") not in {"INSUFFICIENT_DATA", "DISABLED"} for value in (hamilton, break_result, drift, kalman, scoring, conformal, dm, spa, covariance, cvar)])
    data_quality_score = float(np.clip(0.45 * completeness + 0.35 * research_reliability + 0.20 * (100.0 if integrity["status"] == "PASS" else 0.0), 0.0, 100.0))
    data_quality_grade = _quality_grade(data_quality_score, bool(critical_failures), str(drift.get("drift_status")), sample_sufficient)

    production_action = _production_action(canonical)
    transition_risk = float(hamilton.get("transition_risk_3h") or 1.0)
    uncertainty = 100.0 * float(hamilton.get("regime_entropy") or 1.0)
    tail_bad = cvar.get("status") == "VALID" and str(cvar.get("tail_risk_grade") or "D") == "D"
    coverage_bad = conformal.get("status") == "COVERAGE_AT_RISK"
    if critical_failures or data_quality_grade == "D" or tail_bad:
        research_action = "NO TRADE"
        permission = "BLOCKED"
    elif data_quality_grade == "C" or uncertainty > config.maximum_uncertainty_pct or coverage_bad:
        research_action = "WAIT"
        permission = "BLOCKED"
    elif transition_risk > config.maximum_transition_risk:
        research_action = "HOLD AND PROTECT" if production_action == "HOLD AND PROTECT" else "WAIT FOR PULLBACK"
        permission = "CAUTION"
    elif production_action in {"BUY", "SELL"}:
        research_action = "TRADE ALLOWED"
        permission = "ALLOWED"
    elif production_action == "HOLD AND PROTECT":
        research_action = "HOLD AND PROTECT"
        permission = "CAUTION"
    else:
        research_action = "WAIT"
        permission = "BLOCKED"
    conflict = production_action not in {research_action, "WAIT"} and research_action not in {"TRADE ALLOWED", "HOLD AND PROTECT"}

    explanations: list[str] = []
    explanations.extend(critical_failures)
    if drift.get("drift_status") not in {"STABLE", "DISABLED", "INSUFFICIENT_DATA"}:
        explanations.append(f"drift={drift.get('drift_status')}")
    if break_result.get("structural_break_detected"):
        explanations.append(f"structural breaks={break_result.get('break_count')}")
    if hamilton.get("status") == "VALID":
        explanations.append(f"3H transition risk={100 * transition_risk:.1f}%")
    if scoring.get("status") == "VALID":
        explanations.append(f"calibration error={100 * float(scoring.get('calibration_error') or 0):.1f}%")
    if conformal.get("status") in {"VALID", "COVERAGE_AT_RISK"}:
        explanations.append(f"conformal coverage={100 * float(conformal.get('realized_coverage') or 0):.1f}%")
    if cvar.get("status") == "VALID":
        explanations.append(f"CVaR basis={cvar.get('basis')}")
    if not explanations:
        explanations.append("research evidence is incomplete; production decision remains unchanged")

    result = {
        **identity,
        "calculation_version": CALCULATION_VERSION,
        "model_version": MODEL_VERSION,
        "feature_flags": asdict(flags),
        "sample_count": int(sample_count),
        "calculation_status": "FAIL" if critical_failures else ("WARNING" if data_quality_grade in {"B", "C", "D"} else "PASS"),
        "integrity": integrity,
        "production_action": production_action,
        "production_action_unchanged": True,
        "research_recommended_action": research_action,
        "research_trade_permission": permission,
        "research_conflict_status": "CONFLICT" if conflict else "ALIGNED_OR_CONSERVATIVE",
        "research_reliability": round(research_reliability, 4),
        "data_quality_score": round(data_quality_score, 4),
        "data_quality_grade": data_quality_grade,
        "research_explanation": "; ".join(explanations),
        "reliability_components": components,
        "reliability_weights": weights,
        "hamilton_regime": hamilton,
        "bai_perron_breaks": break_result,
        "adwin_drift": drift,
        "kalman_state": kalman,
        "proper_scoring": scoring,
        "conformal_prediction": conformal,
        "diebold_mariano": dm,
        "hansen_spa": spa,
        "ledoit_wolf": covariance,
        "cvar": cvar,
    }
    result["result_hash"] = sha256(repr(_json_safe(result)).encode("utf-8")).hexdigest()
    return _json_safe(result)


def flatten_validation(result: Mapping[str, Any]) -> dict[str, Any]:
    h = _mapping(result.get("hamilton_regime"))
    b = _mapping(result.get("bai_perron_breaks"))
    d = _mapping(result.get("adwin_drift"))
    k = _mapping(result.get("kalman_state"))
    p = _mapping(result.get("proper_scoring"))
    c = _mapping(result.get("conformal_prediction"))
    dm = _mapping(result.get("diebold_mariano"))
    spa = _mapping(result.get("hansen_spa"))
    lw = _mapping(result.get("ledoit_wolf"))
    cv = _mapping(result.get("cvar"))
    cluster = lw.get("correlation_cluster")
    if isinstance(cluster, list):
        cluster = ", ".join(str(v) for v in cluster) or "None"
    return {
        "Research Rank": None,
        "Symbol": result.get("symbol"), "Timeframe": result.get("timeframe"),
        "Broker Timestamp": result.get("completed_candle_time"), "Canonical Run ID": result.get("canonical_run_id"),
        "Production Action": result.get("production_action"), "Research Action": result.get("research_recommended_action"),
        "Research Permission": result.get("research_trade_permission"), "Conflict": result.get("research_conflict_status"),
        "Research Reliability": result.get("research_reliability"), "Research Data Quality": result.get("data_quality_grade"),
        "Research Data Quality Score": result.get("data_quality_score"),
        "Regime Probability": h.get("current_regime_probability"), "Regime Entropy": h.get("regime_entropy"),
        "Expected Regime Duration": h.get("expected_duration_hours"), "Estimated Remaining Duration": h.get("estimated_remaining_hours"),
        "Transition Risk 1H": h.get("transition_risk_1h"), "Transition Risk 3H": h.get("transition_risk_3h"),
        "Transition Risk 6H": h.get("transition_risk_6h"),
        "Structural Break Status": b.get("status"), "Break Count": b.get("break_count"), "Break Strength": b.get("break_strength"),
        "Drift Status": d.get("drift_status"), "Adaptive Window Size": d.get("adaptive_window_size"),
        "State Stability": k.get("state_stability"), "Innovation Z": k.get("innovation_z_score"),
        "Brier Score": p.get("brier_score"), "Log Loss": p.get("log_loss"), "Calibration Error": p.get("calibration_error"),
        "Conformal Status": c.get("status"), "Conformal Coverage": c.get("realized_coverage"), "Interval Width": c.get("interval_width"),
        "DM p-value": dm.get("dm_p_value"), "DM Candidate Superior": dm.get("candidate_superior"),
        "SPA p-value": spa.get("spa_p_value"), "SPA Superior": spa.get("superior_predictive_ability"),
        "Correlation Cluster": cluster, "Duplicate Exposure Penalty": lw.get("duplicate_exposure_penalty"),
        "CVaR 95": cv.get("cvar_95"), "Tail Risk Grade": cv.get("tail_risk_grade"),
        "Calculation Status": result.get("calculation_status"), "Research Explanation": result.get("research_explanation"),
        "Model Version": result.get("model_version"), "Result Hash": result.get("result_hash"),
    }


__all__ = [
    "MODEL_VERSION", "CALCULATION_VERSION", "STATE_KEY", "TenPaperFeatureFlags", "TenPaperConfig",
    "DEFAULT_CONFIG", "resolve_canonical", "source_frame", "extract_return_series", "identity_integrity",
    "hamilton_regime_validation", "bai_perron_breaks", "adwin_drift", "kalman_local_trend",
    "proper_scoring", "conformal_intervals", "diebold_mariano", "hansen_spa", "ledoit_wolf_risk",
    "cvar_tail_risk", "build_ten_paper_validation", "flatten_validation",
]
