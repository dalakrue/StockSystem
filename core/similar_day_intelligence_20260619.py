# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Research-grounded, bounded Similar-Day Intelligence for EURUSD H1.

This module is calculation-only and has no Streamlit import.  It consumes the
already validated completed-H1 frame and the canonical result being built by
the Settings transaction.  Renderers only read its published payload.

Practical concepts implemented without heavy dependencies:
- low-cost feature screening and robust historical-only scaling;
- matrix-profile-style subsequence joins and MPdist-inspired robust distance;
- narrow-band DTW with LB-Keogh and early abandoning;
- k-Shape-style z-normalized shape comparison;
- compact catch22-style statistical characteristics;
- rolling-origin baseline validation;
- bounded deterministic cache identity and atomic SQLite persistence.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

import numpy as np
import pandas as pd

from core.generation_identity_20260707 import numeric_generation

from core.similar_day_config_20260619 import CONFIG, SimilarDayConfig
from core.sqlite_readonly_20260704 import connect_readonly


DB_PATH = Path(__file__).resolve().parents[1] / "data" / "adx_similarity_store.sqlite3"
CACHE_STATE_KEY = "similar_day_bounded_cache_20260619"
ACTIVE_STATE_KEY = "similar_day_intelligence_20260619"
STORE_SCHEMA_VERSION = "1.0.0"
PIP_FACTOR = 10_000.0

_TIME_ALIASES = ("time", "timestamp", "datetime", "date", "candle time", "candle_time")
_OHLC_ALIASES = {
    "open": ("open", "o"),
    "high": ("high", "h"),
    "low": ("low", "l"),
    "close": ("close", "c"),
    "volume": ("volume", "tick_volume", "tick volume", "real_volume", "v"),
}
_METRIC_ALIASES = {
    "master_score": ("master score", "master_score", "master /10", "master/10"),
    "entry_score": ("entry score", "entry_score", "entry /10", "entry/10"),
    "hold_safety": ("hold safety", "hold_safety", "hold /10", "hold/10"),
    "exit_risk": ("exit risk", "exit_risk", "exit risk /10", "exit risk/10"),
    "tp_quality": ("tp quality", "tp_quality", "tp /10", "tp/10"),
    "trend_capacity": ("trend capacity remaining", "trend_capacity_remaining", "trend capacity"),
    "buy_pressure": ("buy pressure", "buy_pressure", "buy score", "buy_score"),
    "sell_pressure": ("sell pressure", "sell_pressure", "sell score", "sell_score"),
    "market_quality": ("market quality", "market_quality", "data quality score"),
    "forecast_agreement": ("forecast agreement", "forecast_agreement", "path agreement"),
    "reliability": ("reliability", "reliability %", "regime reliability"),
    "compression": ("compression", "compression score", "compression_score"),
    "adx": ("adx", "adx value"),
    "plus_di": ("+di", "plus_di", "plus di"),
    "minus_di": ("-di", "minus_di", "minus di"),
}
_TEXT_ALIASES = {
    "h1_regime": ("h1 regime", "h1_regime", "major regime", "regime"),
    "h4_regime": ("h4 regime", "h4_regime"),
    "d1_regime": ("d1 regime", "d1_regime"),
    "decision": ("historical decision", "decision", "current decision", "prediction direction"),
    "less_risky_decision": ("historical less-risky decision", "less risky decision", "less-risky bias", "less_risky_decision"),
    "conflict_status": ("conflict status", "conflict_status"),
    "counter_trend": ("counter trend", "counter-trend", "counter_trend"),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
        return None if not math.isfinite(value) else value
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).isoformat()
    if pd.isna(value) if not isinstance(value, (str, bytes, Mapping, list, tuple)) else False:
        return None
    return value


def _norm_name(value: Any) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())


def _find_column(frame: pd.DataFrame, aliases: Sequence[str]) -> str | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    lookup = {_norm_name(c): str(c) for c in frame.columns}
    for alias in aliases:
        if _norm_name(alias) in lookup:
            return lookup[_norm_name(alias)]
    return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _clip(value: Any, low: float = 0.0, high: float = 100.0) -> float:
    return float(np.clip(_safe_float(value), low, high))


def _direction_from_pips(pips: Any, threshold: float = 0.5) -> str:
    if pips is None or not math.isfinite(_safe_float(pips, float("nan"))):
        return "Unavailable"
    value = float(pips)
    if value > threshold:
        return "BUY"
    if value < -threshold:
        return "SELL"
    return "WAIT"


def _broad_regime(value: Any) -> str:
    text = str(value or "UNKNOWN").upper()
    if "BULL" in text or text in {"BUY", "UP", "LONG"}:
        return "BULL"
    if "BEAR" in text or text in {"SELL", "DOWN", "SHORT"}:
        return "BEAR"
    if any(token in text for token in ("RANGE", "COMPRESS", "SIDEWAY", "NEUTRAL", "WAIT")):
        return "RANGE"
    return "UNKNOWN"


def _normalize_decision(value: Any) -> str:
    text = str(value or "WAIT").upper()
    if "BUY" in text or "LONG" in text:
        return "BUY"
    if "SELL" in text or "SHORT" in text:
        return "SELL"
    return "WAIT"


def _weighted_median(values: Sequence[float], weights: Sequence[float]) -> float | None:
    pairs = [(float(v), max(0.0, float(w))) for v, w in zip(values, weights) if v is not None and math.isfinite(float(v)) and float(w) > 0]
    if not pairs:
        return None
    pairs.sort(key=lambda item: item[0])
    total = sum(w for _, w in pairs)
    threshold = total / 2.0
    running = 0.0
    for value, weight in pairs:
        running += weight
        if running >= threshold:
            return value
    return pairs[-1][0]


def _score_from_distance(distance: float, scale: float = 1.0) -> float:
    if not math.isfinite(distance):
        return 0.0
    return _clip(100.0 * math.exp(-max(0.0, distance) / max(scale, 1e-9)))


def _z_normalize(values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32)
    if arr.size == 0:
        return arr
    mean = float(np.nanmean(arr))
    std = float(np.nanstd(arr))
    if not math.isfinite(std) or std < 1e-8:
        return np.zeros_like(arr, dtype=np.float32)
    return ((arr - mean) / std).astype(np.float32, copy=False)


def _resample_path(values: Sequence[float], points: int = 8) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32)
    if arr.size == 0:
        return np.zeros(points, dtype=np.float32)
    if arr.size == 1:
        return np.repeat(arr, points).astype(np.float32)
    x_old = np.linspace(0.0, 1.0, arr.size)
    x_new = np.linspace(0.0, 1.0, points)
    return np.interp(x_new, x_old, arr).astype(np.float32)


def _sliding_windows(values: Sequence[float], window: int) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32)
    window = max(2, min(int(window), int(arr.size)))
    if arr.size < window:
        return np.empty((0, window), dtype=np.float32)
    try:
        windows = np.lib.stride_tricks.sliding_window_view(arr, window)
    except Exception:
        windows = np.vstack([arr[i : i + window] for i in range(arr.size - window + 1)])
    means = windows.mean(axis=1, keepdims=True)
    stds = windows.std(axis=1, keepdims=True)
    stds = np.where(stds < 1e-8, 1.0, stds)
    return ((windows - means) / stds).astype(np.float32, copy=False)


def matrix_profile_style_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Symmetric AB-join-like subsequence distance for short intraday paths."""
    a_arr, b_arr = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    if min(a_arr.size, b_arr.size) < 4:
        return float("inf")
    window = max(4, min(8, min(a_arr.size, b_arr.size) // 2 or 4))
    aw, bw = _sliding_windows(a_arr, window), _sliding_windows(b_arr, window)
    if aw.size == 0 or bw.size == 0:
        return float("inf")
    distances = np.sqrt(np.mean((aw[:, None, :] - bw[None, :, :]) ** 2, axis=2))
    profile_ab = distances.min(axis=1)
    profile_ba = distances.min(axis=0)
    return float(np.mean(np.concatenate([profile_ab, profile_ba])))


def mpdist_inspired_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Robust MPdist-inspired quantile of bidirectional join profiles."""
    a_arr, b_arr = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    if min(a_arr.size, b_arr.size) < 4:
        return float("inf")
    window = max(4, min(8, min(a_arr.size, b_arr.size) // 2 or 4))
    aw, bw = _sliding_windows(a_arr, window), _sliding_windows(b_arr, window)
    if aw.size == 0 or bw.size == 0:
        return float("inf")
    distances = np.sqrt(np.mean((aw[:, None, :] - bw[None, :, :]) ** 2, axis=2))
    joined = np.sort(np.concatenate([distances.min(axis=1), distances.min(axis=0)]))
    index = min(len(joined) - 1, max(0, int(math.ceil(0.10 * len(joined))) - 1))
    return float(joined[index])


def lb_keogh(a: Sequence[float], b: Sequence[float], window: int) -> float:
    aa = np.asarray(a, dtype=np.float32)
    bb = np.asarray(b, dtype=np.float32)
    if aa.size == 0 or bb.size == 0:
        return float("inf")
    radius = max(1, int(window))
    total = 0.0
    for i, value in enumerate(aa):
        lo = max(0, i - radius)
        hi = min(bb.size, i + radius + 1)
        if lo >= hi:
            continue
        lower, upper = float(np.min(bb[lo:hi])), float(np.max(bb[lo:hi]))
        if value > upper:
            total += float((value - upper) ** 2)
        elif value < lower:
            total += float((value - lower) ** 2)
    return math.sqrt(total / max(1, aa.size))


def constrained_dtw_distance(
    a: Sequence[float], b: Sequence[float], *, window: int | None = None, max_cost: float | None = None
) -> float:
    """Narrow Sakoe-Chiba DTW with row-level early abandoning."""
    aa, bb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    n, m = int(aa.size), int(bb.size)
    if n == 0 or m == 0:
        return float("inf")
    radius = max(abs(n - m), int(window if window is not None else math.ceil(max(n, m) * CONFIG.dtw_window_ratio)), 1)
    previous = np.full(m + 1, np.inf, dtype=np.float64)
    previous[0] = 0.0
    abandon_total = None if max_cost is None else float(max_cost) ** 2 * max(n, m)
    for i in range(1, n + 1):
        current = np.full(m + 1, np.inf, dtype=np.float64)
        start, stop = max(1, i - radius), min(m, i + radius)
        row_min = np.inf
        for j in range(start, stop + 1):
            cost = float((aa[i - 1] - bb[j - 1]) ** 2)
            current[j] = cost + min(current[j - 1], previous[j], previous[j - 1])
            row_min = min(row_min, current[j])
        if abandon_total is not None and row_min > abandon_total:
            return float("inf")
        previous = current
    total = previous[m]
    return math.sqrt(float(total) / max(n, m)) if math.isfinite(total) else float("inf")


def _normalise_ohlc(frame: pd.DataFrame, latest_completed: Any = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(), {"status": "UNAVAILABLE", "warnings": ["No OHLC frame supplied"]}
    source = frame
    time_col = _find_column(source, _TIME_ALIASES)
    if time_col is None and isinstance(source.index, pd.DatetimeIndex):
        work = source.reset_index().rename(columns={source.index.name or "index": "time"})
        time_col = "time"
    elif time_col is not None:
        selected = [time_col]
        for aliases in _OHLC_ALIASES.values():
            col = _find_column(source, aliases)
            if col and col not in selected:
                selected.append(col)
        work = source.loc[:, selected].copy(deep=False)
    else:
        return pd.DataFrame(), {"status": "UNAVAILABLE", "warnings": ["A timestamp column is required"]}

    rename: dict[str, str] = {time_col: "time"}
    for canonical, aliases in _OHLC_ALIASES.items():
        col = _find_column(work, aliases)
        if col:
            rename[col] = canonical
    work = work.rename(columns=rename)
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required.difference(work.columns))
    if missing:
        return pd.DataFrame(), {"status": "UNAVAILABLE", "warnings": ["Missing OHLC columns: " + ", ".join(missing)]}

    parsed = pd.to_datetime(work["time"], errors="coerce", utc=True)
    invalid_times = int(parsed.isna().sum())
    original_valid = parsed.dropna()
    unsorted = bool(not original_valid.is_monotonic_increasing)
    original_valid_frame = pd.DataFrame({"time": original_valid})
    unsorted_dates = []
    if not original_valid_frame.empty:
        original_valid_frame["date"] = original_valid_frame["time"].dt.date
        unsorted_dates = sorted(
            d.isoformat() for d, group in original_valid_frame.groupby("date", sort=False)
            if not group["time"].is_monotonic_increasing
        )
    duplicate_mask = original_valid.duplicated(keep=False)
    duplicate_times = set(original_valid[duplicate_mask].astype("int64").tolist())
    duplicate_dates = sorted({pd.Timestamp(v, tz="UTC").date().isoformat() for v in duplicate_times})
    work = work.assign(time=parsed).dropna(subset=["time"])
    for column in ("open", "high", "low", "close", "volume"):
        if column in work.columns:
            work[column] = pd.to_numeric(work[column], errors="coerce")
    work = work.dropna(subset=["open", "high", "low", "close"])
    future_rows_removed = 0
    if latest_completed not in (None, ""):
        boundary = pd.to_datetime(latest_completed, errors="coerce", utc=True)
        if pd.notna(boundary):
            future_rows_removed = int((work["time"] > boundary).sum())
            work = work.loc[work["time"] <= boundary]
    work = work.sort_values("time", kind="mergesort")
    before = len(work)
    work = work.drop_duplicates(subset=["time"], keep="last")
    duplicates_removed = before - len(work)
    work = work.reset_index(drop=True)
    if "volume" not in work.columns:
        work["volume"] = np.nan
    for column in ("open", "high", "low", "close", "volume"):
        work[column] = work[column].astype(np.float32, copy=False)
    warnings: list[str] = []
    if invalid_times:
        warnings.append(f"{invalid_times} invalid timestamps removed")
    if unsorted:
        warnings.append("Input timestamps were unsorted and were normalized")
    if duplicates_removed:
        warnings.append(f"{duplicates_removed} duplicate timestamps removed")
    if future_rows_removed:
        warnings.append(f"{future_rows_removed} rows later than the canonical completed candle were excluded")
    return work, {
        "status": "GOOD" if not warnings else "CHECK",
        "warnings": warnings,
        "unsorted_input": unsorted,
        "duplicates_removed": duplicates_removed,
        "duplicate_dates": duplicate_dates,
        "unsorted_dates": unsorted_dates,
        "future_rows_removed": future_rows_removed,
        "rows": int(len(work)),
    }


def _technical_frame(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.loc[:, [c for c in ("time", "open", "high", "low", "close", "volume") if c in frame.columns]].copy(deep=False)
    close = work["close"].astype(np.float64)
    high = work["high"].astype(np.float64)
    low = work["low"].astype(np.float64)
    previous_close = close.shift(1)
    true_range = pd.concat([(high - low).abs(), (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
    atr = true_range.rolling(14, min_periods=2).mean()
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=work.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=work.index)
    tr_sum = true_range.rolling(14, min_periods=2).sum().replace(0, np.nan)
    plus_di = 100.0 * plus_dm.rolling(14, min_periods=2).sum() / tr_sum
    minus_di = 100.0 * minus_dm.rolling(14, min_periods=2).sum() / tr_sum
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(14, min_periods=2).mean()
    candle_range = (high - low).replace(0, np.nan)
    pressure = ((close - work["open"].astype(np.float64)) / candle_range).clip(-1, 1)
    returns = np.log(close.replace(0, np.nan)).diff()
    work = work.assign(
        log_return=returns.astype(np.float32),
        true_range=true_range.astype(np.float32),
        atr=atr.astype(np.float32),
        plus_di=plus_di.astype(np.float32),
        minus_di=minus_di.astype(np.float32),
        adx=adx.astype(np.float32),
        pressure=pressure.astype(np.float32),
    )
    return work


def _approx_entropy(values: np.ndarray, bins: int = 6) -> float:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size < 3 or np.nanstd(arr) < 1e-12:
        return 0.0
    hist, _ = np.histogram(arr[np.isfinite(arr)], bins=bins)
    probs = hist[hist > 0] / max(1, hist.sum())
    return float(-(probs * np.log(probs)).sum() / math.log(max(2, bins)))


def _autocorr_lag1(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size < 3 or np.nanstd(arr[:-1]) < 1e-12 or np.nanstd(arr[1:]) < 1e-12:
        return 0.0
    return float(np.corrcoef(arr[:-1], arr[1:])[0, 1])


def _linear_slope(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size < 2:
        return 0.0
    x = np.arange(arr.size, dtype=np.float64)
    return float(np.polyfit(x, arr, 1)[0])


def _auxiliary_frame(frame: Any) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    time_col = _find_column(frame, _TIME_ALIASES)
    if not time_col:
        return pd.DataFrame()
    selected = [time_col]
    rename = {time_col: "time"}
    for canonical, aliases in {**_METRIC_ALIASES, **_TEXT_ALIASES}.items():
        col = _find_column(frame, aliases)
        if col and col not in selected:
            selected.append(col)
            rename[col] = canonical
    out = frame.loc[:, selected].rename(columns=rename).copy(deep=False)
    out["time"] = pd.to_datetime(out["time"], errors="coerce", utc=True)
    out = out.dropna(subset=["time"]).sort_values("time", kind="mergesort").drop_duplicates("time", keep="last")
    for column in _METRIC_ALIASES:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").astype(np.float32)
    return out.reset_index(drop=True)


def _aux_summary(aux: pd.DataFrame, trading_date: date, last_hour: int) -> dict[str, Any]:
    if aux.empty:
        return {}
    dates = aux["time"].dt.date
    hours = aux["time"].dt.hour
    rows = aux.loc[(dates == trading_date) & (hours <= int(last_hour))]
    if rows.empty:
        return {}
    result: dict[str, Any] = {}
    for column in _METRIC_ALIASES:
        if column in rows.columns:
            series = pd.to_numeric(rows[column], errors="coerce").dropna()
            if not series.empty:
                result[column] = float(series.mean())
    latest = rows.iloc[-1]
    for column in _TEXT_ALIASES:
        if column in rows.columns and pd.notna(latest.get(column)):
            result[column] = str(latest.get(column))
    return result


def _canonical_context(canonical: Mapping[str, Any]) -> dict[str, Any]:
    final = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
    regime = canonical.get("regime") if isinstance(canonical.get("regime"), Mapping) else {}
    reliability = canonical.get("reliability") if isinstance(canonical.get("reliability"), Mapping) else {}
    data_quality = canonical.get("data_quality") if isinstance(canonical.get("data_quality"), Mapping) else {}
    market = canonical.get("market") if isinstance(canonical.get("market"), Mapping) else {}
    return {
        "decision": _normalize_decision(final.get("final_decision") or canonical.get("tradeability_decision")),
        "less_risky_decision": _normalize_decision(final.get("less_risky_decision")),
        "h1_regime": str(regime.get("major_regime") or canonical.get("current_major_regime") or "UNKNOWN"),
        "h4_regime": str(regime.get("h4_regime") or regime.get("medium_standard_regime") or "UNKNOWN"),
        "d1_regime": str(regime.get("d1_regime") or regime.get("higher_standard_regime") or "UNKNOWN"),
        "master_score": canonical.get("master_score"),
        "entry_score": canonical.get("entry_score"),
        "hold_safety": canonical.get("hold_safety"),
        "exit_risk": canonical.get("exit_risk"),
        "tp_quality": canonical.get("tp_quality"),
        "trend_capacity": canonical.get("trend_capacity_remaining"),
        "buy_pressure": canonical.get("buy_score"),
        "sell_pressure": canonical.get("sell_score"),
        "market_quality": data_quality.get("score"),
        "reliability": reliability.get("score"),
        "latest_completed": canonical.get("latest_completed_candle_time") or market.get("latest_completed_candle_time"),
        "generation": canonical.get("calculation_generation"),
        "calculation_id": canonical.get("canonical_calculation_id") or canonical.get("run_id"),
        "symbol": canonical.get("symbol", "EURUSD"),
        "timeframe": canonical.get("timeframe", "H1"),
        "last_close": canonical.get("last_close") or market.get("current_price"),
    }


def _simple_regime(summary: Mapping[str, Any]) -> str:
    cumulative = _safe_float(summary.get("cumulative_return"))
    adx = _safe_float(summary.get("adx_mean"))
    vol = _safe_float(summary.get("realized_volatility"))
    if abs(cumulative) < max(0.00025, vol * 0.7) or adx < 16:
        return "RANGE_COMPRESSION"
    direction = "BULL" if cumulative > 0 else "BEAR"
    strength = "STRONG" if adx >= 28 else "NORMAL"
    return f"{direction}_{strength}"


def _prefix_features(prefix: pd.DataFrame, aux_values: Mapping[str, Any] | None = None) -> dict[str, Any]:
    technical = _technical_frame(prefix)
    close = technical["close"].astype(np.float64).to_numpy()
    open_values = technical["open"].astype(np.float64).to_numpy()
    high = technical["high"].astype(np.float64).to_numpy()
    low = technical["low"].astype(np.float64).to_numpy()
    returns = np.nan_to_num(technical["log_return"].astype(np.float64).to_numpy(), nan=0.0)
    path = np.log(np.maximum(close, 1e-12) / max(close[0], 1e-12))
    z_path = _z_normalize(path)
    sampled = _resample_path(z_path, 8)
    cumulative = float(path[-1]) if path.size else 0.0
    total_range = max(float(np.nanmax(high) - np.nanmin(low)), 1e-12)
    range_position = float((close[-1] - np.nanmin(low)) / total_range)
    atr = technical["atr"].astype(np.float64).to_numpy()
    adx = technical["adx"].astype(np.float64).to_numpy()
    plus_di = technical["plus_di"].astype(np.float64).to_numpy()
    minus_di = technical["minus_di"].astype(np.float64).to_numpy()
    pressure = technical["pressure"].astype(np.float64).to_numpy()
    volume = technical["volume"].astype(np.float64).to_numpy()
    finite_volume = volume[np.isfinite(volume) & (volume > 0)]
    volume_quality = float(len(finite_volume) / max(1, len(volume))) * 100.0
    changes = np.diff(path) if path.size > 1 else np.array([0.0])
    zero_crossings = float(np.mean(np.signbit(changes[:-1]) != np.signbit(changes[1:]))) if changes.size > 1 else 0.0
    outlier_ratio = float(np.mean(np.abs(changes - np.nanmedian(changes)) > 3 * max(np.nanmedian(np.abs(changes - np.nanmedian(changes))), 1e-9)))
    summary: dict[str, Any] = {
        "hour_count": int(len(prefix)),
        "path": z_path.astype(np.float32),
        "raw_path": path.astype(np.float32),
        "cumulative_return": cumulative,
        "range_position": range_position,
        "atr_mean": float(np.nanmean(atr)) if np.isfinite(atr).any() else total_range / max(1, len(prefix)),
        "atr_slope": _linear_slope(np.nan_to_num(atr, nan=0.0)),
        "realized_volatility": float(np.nanstd(returns)),
        "adx_mean": float(np.nanmean(adx)) if np.isfinite(adx).any() else 0.0,
        "adx_slope": _linear_slope(np.nan_to_num(adx, nan=0.0)),
        "plus_di_mean": float(np.nanmean(plus_di)) if np.isfinite(plus_di).any() else 0.0,
        "minus_di_mean": float(np.nanmean(minus_di)) if np.isfinite(minus_di).any() else 0.0,
        "pressure_mean": float(np.nanmean(pressure)) if np.isfinite(pressure).any() else 0.0,
        "buy_pressure": float(np.nanmean(np.clip(pressure, 0, None))) * 10.0,
        "sell_pressure": float(np.nanmean(np.clip(-pressure, 0, None))) * 10.0,
        "volume_quality": volume_quality,
        "autocorr_lag1": _autocorr_lag1(changes),
        "change_entropy": _approx_entropy(changes),
        "linear_trend": _linear_slope(path),
        "mean_abs_change": float(np.nanmean(np.abs(changes))),
        "change_q25": float(np.nanquantile(changes, 0.25)),
        "change_q75": float(np.nanquantile(changes, 0.75)),
        "zero_crossing_rate": zero_crossings,
        "outlier_ratio": outlier_ratio,
        "body_efficiency": float(abs(close[-1] - open_values[0]) / max(np.sum(np.abs(close - open_values)), 1e-12)),
    }
    for i, value in enumerate(sampled):
        summary[f"path_{i}"] = float(value)
    for key, value in dict(aux_values or {}).items():
        if key in _METRIC_ALIASES and value is not None and math.isfinite(_safe_float(value, float("nan"))):
            summary[key] = float(value)
        elif key in _TEXT_ALIASES and value not in (None, ""):
            summary[key] = str(value)
    summary["h1_regime"] = str(summary.get("h1_regime") or _simple_regime(summary))
    summary["h4_regime"] = str(summary.get("h4_regime") or "UNKNOWN")
    summary["d1_regime"] = str(summary.get("d1_regime") or "UNKNOWN")
    return summary


def _feature_vector(summary: Mapping[str, Any]) -> np.ndarray:
    names = [
        *(f"path_{i}" for i in range(8)),
        "cumulative_return", "range_position", "atr_mean", "atr_slope", "realized_volatility",
        "adx_mean", "adx_slope", "plus_di_mean", "minus_di_mean", "pressure_mean",
        "buy_pressure", "sell_pressure", "volume_quality", "autocorr_lag1", "change_entropy",
        "linear_trend", "mean_abs_change", "change_q25", "change_q75", "zero_crossing_rate",
        "outlier_ratio", "body_efficiency", "master_score", "entry_score", "hold_safety",
        "exit_risk", "tp_quality", "trend_capacity", "market_quality", "forecast_agreement",
        "reliability", "compression",
    ]
    return np.asarray([_safe_float(summary.get(name), 0.0) for name in names], dtype=np.float32)


def _robust_scaled_distances(current: np.ndarray, candidates: list[np.ndarray]) -> list[float]:
    if not candidates:
        return []
    matrix = np.vstack(candidates).astype(np.float32, copy=False)
    median = np.nanmedian(matrix, axis=0)
    q25 = np.nanquantile(matrix, 0.25, axis=0)
    q75 = np.nanquantile(matrix, 0.75, axis=0)
    scale = q75 - q25
    fallback = np.nanstd(matrix, axis=0)
    scale = np.where(scale > 1e-8, scale, np.where(fallback > 1e-8, fallback, 1.0))
    current_scaled = (current - median) / scale
    candidate_scaled = (matrix - median) / scale
    return [float(np.sqrt(np.mean((row - current_scaled) ** 2))) for row in candidate_scaled]


def _quality_score(
    *, matched: int, expected: int, duplicate: bool, unsorted_input: bool, volume_quality: float, current: bool = False
) -> float:
    completeness = matched / max(1, expected)
    score = 100.0 * completeness
    if duplicate:
        score -= 30.0
    if unsorted_input and current:
        score -= 10.0
    if volume_quality < 50:
        score -= 8.0
    return _clip(score)


def _regime_score(current: Mapping[str, Any], candidate: Mapping[str, Any]) -> float:
    scores = []
    weights = []
    for key, weight in (("h1_regime", 0.6), ("h4_regime", 0.25), ("d1_regime", 0.15)):
        a, b = str(current.get(key) or "UNKNOWN"), str(candidate.get(key) or "UNKNOWN")
        if a == "UNKNOWN" or b == "UNKNOWN":
            score = 50.0
        elif a == b:
            score = 100.0
        elif _broad_regime(a) == _broad_regime(b):
            score = 78.0
        elif "RANGE" in {_broad_regime(a), _broad_regime(b)}:
            score = 35.0
        else:
            score = 5.0
        scores.append(score)
        weights.append(weight)
    return float(np.average(scores, weights=weights))


def _ratio_score(a: float, b: float, floor: float = 1e-9) -> float:
    aa, bb = max(abs(a), floor), max(abs(b), floor)
    return _score_from_distance(abs(math.log(aa / bb)), scale=0.75)


def _volatility_score(current: Mapping[str, Any], candidate: Mapping[str, Any]) -> float:
    return float(np.mean([
        _ratio_score(_safe_float(current.get("atr_mean")), _safe_float(candidate.get("atr_mean"))),
        _ratio_score(_safe_float(current.get("realized_volatility")), _safe_float(candidate.get("realized_volatility"))),
        _score_from_distance(abs(_safe_float(current.get("range_position")) - _safe_float(candidate.get("range_position"))), 0.4),
    ]))


def _adx_pressure_scores(current: Mapping[str, Any], candidate: Mapping[str, Any]) -> tuple[float, float]:
    adx_di = float(np.mean([
        _score_from_distance(abs(_safe_float(current.get("adx_mean")) - _safe_float(candidate.get("adx_mean"))) / 20.0, 1.0),
        _score_from_distance(abs(_safe_float(current.get("plus_di_mean")) - _safe_float(candidate.get("plus_di_mean"))) / 25.0, 1.0),
        _score_from_distance(abs(_safe_float(current.get("minus_di_mean")) - _safe_float(candidate.get("minus_di_mean"))) / 25.0, 1.0),
    ]))
    pressure = float(np.mean([
        _score_from_distance(abs(_safe_float(current.get("pressure_mean")) - _safe_float(candidate.get("pressure_mean"))), 0.7),
        _score_from_distance(abs(_safe_float(current.get("buy_pressure")) - _safe_float(candidate.get("buy_pressure"))) / 5.0, 1.0),
        _score_from_distance(abs(_safe_float(current.get("sell_pressure")) - _safe_float(candidate.get("sell_pressure"))) / 5.0, 1.0),
    ]))
    return adx_di, pressure



def reliability_label(
    *, agreement_count: int, effective_sample_size: float, data_quality: float,
    regime_compatibility: float, best_similarity: float, anomaly: bool, missing_current_hours: bool,
) -> str:
    """Conservative, explicit reliability gate used by calculation and tests."""
    if (
        agreement_count >= 4 and effective_sample_size >= 3.5 and data_quality >= 90
        and regime_compatibility >= 75 and best_similarity >= 65
        and not anomaly and not missing_current_hours
    ):
        return "High Reliability"
    if agreement_count >= 3 and effective_sample_size >= 2.5 and data_quality >= 75 and best_similarity >= 50:
        return "Medium Reliability"
    return "Low Reliability"


def canonical_conflict_warning(similar_direction: Any, canonical_direction: Any) -> tuple[bool, str]:
    similar = _normalize_decision(similar_direction)
    canonical = _normalize_decision(canonical_direction)
    conflict = similar not in {"WAIT", canonical} and canonical != "WAIT"
    if conflict:
        return True, (
            f"Conflict: Similar-Day historical outcome leans {similar}, while the canonical less-risky decision is {canonical}. "
            "Similar-Day evidence must not override the canonical decision."
        )
    return False, "No material conflict with the canonical less-risky decision."

def _pattern_family(summary: Mapping[str, Any], quality: float) -> str:
    raw_path = summary.get("raw_path")
    path = np.asarray(raw_path if raw_path is not None else [], dtype=np.float64)
    if quality < 65:
        return "Low-liquidity irregular day"
    if path.size < 4:
        return "Unclassified"
    cumulative = float(path[-1])
    changes = np.diff(path)
    vol = float(np.std(changes)) if changes.size else 0.0
    first = float(path[max(1, path.size // 2) - 1])
    second_move = cumulative - first
    range_position = _safe_float(summary.get("range_position"), 0.5)
    adx = _safe_float(summary.get("adx_mean"))
    outlier = _safe_float(summary.get("outlier_ratio"))
    if outlier > 0.20 and vol > 0.0012:
        return "High-volatility news shock"
    if abs(cumulative) < max(0.00025, vol * 0.8) and adx < 20:
        return "Range or compression"
    if first > 0.0003 and second_move < -abs(first) * 0.35:
        return "Bull trend then pullback"
    if first < -0.0003 and second_move > abs(first) * 0.35:
        return "Bear trend then rebound"
    if first * second_move < 0 and abs(second_move) > abs(first) * 0.8:
        return "Reversal"
    if cumulative > 0.0006 and range_position > 0.85:
        return "Breakout"
    if cumulative < -0.0006 and range_position < 0.15:
        return "Breakout"
    same_sign = float(np.mean(np.sign(changes) == np.sign(cumulative))) if changes.size else 0.0
    if cumulative > 0 and same_sign >= 0.58:
        return "Steady bullish trend"
    if cumulative < 0 and same_sign >= 0.58:
        return "Steady bearish trend"
    return "Unclassified"


def _calendar_candidates(current_date: date, count: int) -> list[date]:
    result: list[date] = []
    cursor = current_date - timedelta(days=1)
    while len(result) < count:
        if cursor.weekday() < 5:
            result.append(cursor)
        cursor -= timedelta(days=1)
    return result


def _interpolated_prefix(day_rows: pd.DataFrame, hours: Sequence[int]) -> tuple[pd.DataFrame, int, list[int]]:
    if day_rows.empty:
        return pd.DataFrame(), 0, list(hours)
    indexed = day_rows.assign(hour=day_rows["time"].dt.hour).drop_duplicates("hour", keep="last").set_index("hour")
    matched = [h for h in hours if h in indexed.index]
    missing = [h for h in hours if h not in indexed.index]
    if not matched:
        return pd.DataFrame(), 0, missing
    reindexed = indexed.reindex(list(hours))
    numeric = [c for c in ("open", "high", "low", "close", "volume") if c in reindexed.columns]
    reindexed[numeric] = reindexed[numeric].interpolate(limit_direction="both")
    base_date = day_rows["time"].iloc[0].date()
    reindexed["time"] = [pd.Timestamp(datetime.combine(base_date, datetime.min.time()), tz="UTC") + pd.Timedelta(hours=int(h)) for h in hours]
    return reindexed.reset_index(drop=True).loc[:, ["time", "open", "high", "low", "close", "volume"]], len(matched), missing


def _historical_decision(summary: Mapping[str, Any]) -> tuple[str, str]:
    decision = _normalize_decision(summary.get("decision")) if summary.get("decision") else "WAIT"
    less = _normalize_decision(summary.get("less_risky_decision")) if summary.get("less_risky_decision") else "WAIT"
    if decision == "WAIT":
        cumulative = _safe_float(summary.get("cumulative_return"))
        pressure = _safe_float(summary.get("pressure_mean"))
        if cumulative > 0.00035 and pressure > 0.05:
            decision = "BUY"
        elif cumulative < -0.00035 and pressure < -0.05:
            decision = "SELL"
    if less == "WAIT" and _safe_float(summary.get("adx_mean")) >= 18:
        less = decision
    return decision, less


def _outcomes(full: pd.DataFrame, prefix: pd.DataFrame, summary: Mapping[str, Any], config: SimilarDayConfig) -> dict[str, Any]:
    anchor_time = pd.Timestamp(prefix["time"].iloc[-1])
    anchor = float(prefix["close"].iloc[-1])
    lookup = full.set_index("time", drop=False)
    outcome: dict[str, Any] = {}
    for horizon in (1, 3, 6):
        target = anchor_time + pd.Timedelta(hours=horizon)
        if target not in lookup.index:
            outcome[f"h{horizon}_pips"] = None
            outcome[f"h{horizon}_direction"] = "Unavailable"
        else:
            row = lookup.loc[target]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            pips = (float(row["close"]) - anchor) * PIP_FACTOR
            outcome[f"h{horizon}_pips"] = round(pips, 2)
            outcome[f"h{horizon}_direction"] = _direction_from_pips(pips)
    future = full.loc[(full["time"] > anchor_time) & (full["time"] <= anchor_time + pd.Timedelta(hours=6))].copy(deep=False)
    decision, less = _historical_decision(summary)
    outcome["historical_decision"] = decision
    outcome["historical_less_risky_decision"] = less
    if future.empty:
        outcome.update({"mfe_pips": None, "mae_pips": None, "expected_range_pips": None, "tp_sl_result": "Neither", "tp_sl_warning": "Future H1 data unavailable"})
        return outcome
    max_high = float(future["high"].max())
    min_low = float(future["low"].min())
    if decision == "SELL":
        mfe = (anchor - min_low) * PIP_FACTOR
        mae = (max_high - anchor) * PIP_FACTOR
    else:
        mfe = (max_high - anchor) * PIP_FACTOR
        mae = (anchor - min_low) * PIP_FACTOR
    outcome["mfe_pips"] = round(max(0.0, mfe), 2)
    outcome["mae_pips"] = round(max(0.0, mae), 2)
    outcome["expected_range_pips"] = round((max_high - min_low) * PIP_FACTOR, 2)
    atr = max(_safe_float(summary.get("atr_mean"), 0.0), 1.0 / PIP_FACTOR)
    threshold = atr * config.tp_sl_atr_multiplier
    result = "Neither"
    ambiguity = ""
    if decision in {"BUY", "SELL"}:
        for _, row in future.sort_values("time").iterrows():
            if decision == "BUY":
                tp_hit = float(row["high"]) >= anchor + threshold
                sl_hit = float(row["low"]) <= anchor - threshold
            else:
                tp_hit = float(row["low"]) <= anchor - threshold
                sl_hit = float(row["high"]) >= anchor + threshold
            if tp_hit and sl_hit:
                result = "Neither"
                ambiguity = "TP and SL touched in the same H1 candle; order unavailable"
                break
            if tp_hit:
                result = "TP First"
                break
            if sl_hit:
                result = "SL First"
                break
    outcome["tp_sl_result"] = result
    outcome["tp_sl_warning"] = ambiguity
    return outcome


def _current_baselines(rows: list[dict[str, Any]], current_weekday: int, current_regime: str, canonical: Mapping[str, Any]) -> dict[str, Any]:
    valid = [r for r in rows if r.get("h3_pips") is not None and r.get("Similarity Index", 0) > 0]
    previous_candidates = [r for r in rows if r.get("h3_pips") is not None]
    previous = max(previous_candidates, key=lambda r: r.get("Historical Date", ""), default=None)
    same_weekday = [r["h3_pips"] for r in valid if r.get("weekday") == current_weekday]
    same_regime = [r["h3_pips"] for r in valid if _broad_regime(r.get("Historical Regime")) == _broad_regime(current_regime)]
    chronological = sorted(valid, key=lambda r: r.get("Historical Date", ""))
    recent_values = [float(r["h3_pips"]) for r in chronological[-10:]]
    ewma = None
    if recent_values:
        series = pd.Series(recent_values, dtype=float)
        ewma = float(series.ewm(alpha=0.35, adjust=False).mean().iloc[-1])
    forecasts = canonical.get("forecasts") if isinstance(canonical.get("forecasts"), Mapping) else {}
    horizons = forecasts.get("horizons") if isinstance(forecasts.get("horizons"), Mapping) else {}
    h3 = horizons.get("3h") if isinstance(horizons.get("3h"), Mapping) else {}
    point = h3.get("point_forecast")
    last_close = canonical.get("last_close") or (canonical.get("market") or {}).get("current_price") if isinstance(canonical.get("market"), Mapping) else canonical.get("last_close")
    powerbi_pips = None
    try:
        if point is not None and last_close is not None:
            powerbi_pips = (float(point) - float(last_close)) * PIP_FACTOR
    except Exception:
        powerbi_pips = None
    return {
        "previous_day_continuation_pips": round(float(previous["h3_pips"]), 2) if previous else None,
        "same_weekday_median_pips": round(float(np.median(same_weekday)), 2) if same_weekday else None,
        "current_regime_median_pips": round(float(np.median(same_regime)), 2) if same_regime else None,
        "rolling_mean_pips": round(float(np.mean(recent_values)), 2) if recent_values else None,
        "exponentially_weighted_pips": round(ewma, 2) if ewma is not None else None,
        "existing_powerbi_h3_pips": round(powerbi_pips, 2) if powerbi_pips is not None else None,
        "note": "Baseline values are comparisons, not probabilities or replacement decisions.",
    }


def _simple_prefix_and_outcome(frame: pd.DataFrame, day: date, hours: Sequence[int]) -> tuple[np.ndarray | None, float | None, str]:
    rows = frame.loc[frame["time"].dt.date == day]
    prefix, matched, missing = _interpolated_prefix(rows, hours)
    if prefix.empty or missing:
        return None, None, "insufficient prefix"
    path = _z_normalize(np.log(prefix["close"].astype(float).to_numpy() / float(prefix["close"].iloc[0])))
    anchor_time = prefix["time"].iloc[-1]
    target = anchor_time + pd.Timedelta(hours=3)
    target_rows = frame.loc[frame["time"] == target]
    if target_rows.empty:
        return path, None, "future unavailable"
    pips = (float(target_rows.iloc[-1]["close"]) - float(prefix.iloc[-1]["close"])) * PIP_FACTOR
    return path, pips, "ok"


def walk_forward_validation(frame: pd.DataFrame, hours: Sequence[int], config: SimilarDayConfig = CONFIG) -> dict[str, Any]:
    """Small rolling-origin evaluation; training observations always precede origin."""
    unique_days = sorted({d for d in frame["time"].dt.date if d.weekday() < 5})
    origins = unique_days[-(config.validation_origins + config.validation_min_training_days + 1) :]
    records: list[dict[str, Any]] = []
    for idx in range(config.validation_min_training_days, len(origins)):
        origin = origins[idx]
        origin_path, actual, status = _simple_prefix_and_outcome(frame, origin, hours)
        if origin_path is None or actual is None:
            continue
        training_days = origins[:idx]
        candidates: list[tuple[float, float, date]] = []
        for prior in training_days[-25:]:
            prior_path, prior_outcome, _ = _simple_prefix_and_outcome(frame, prior, hours)
            if prior_path is None or prior_outcome is None:
                continue
            distance = float(np.sqrt(np.mean((_resample_path(origin_path, 8) - _resample_path(prior_path, 8)) ** 2)))
            candidates.append((distance, float(prior_outcome), prior))
        if len(candidates) < 3:
            continue
        previous = max(candidates, key=lambda item: item[2])[1] if candidates else None
        candidates.sort(key=lambda item: item[0])
        top = candidates[:5]
        weights = [math.exp(-d) for d, _, _ in top]
        similar_forecast = _weighted_median([v for _, v, _ in top], weights)
        prior_outcomes = [v for _, v, _ in sorted(candidates, key=lambda item: item[2])]
        same_weekday = [v for _, v, d in candidates if d.weekday() == origin.weekday()]
        rolling = float(np.mean(prior_outcomes[-10:]))
        ewma = float(pd.Series(prior_outcomes[-10:]).ewm(alpha=0.35, adjust=False).mean().iloc[-1])
        records.append({
            "origin": origin.isoformat(), "actual": float(actual),
            "similar_day": similar_forecast,
            "previous_day": previous,
            "same_weekday": float(np.median(same_weekday)) if same_weekday else None,
            "rolling_mean": rolling,
            "ewma": ewma,
        })
        if len(records) >= config.validation_origins:
            break
    methods = ("similar_day", "previous_day", "same_weekday", "rolling_mean", "ewma")
    metrics: dict[str, Any] = {}
    for method in methods:
        pairs = [(r[method], r["actual"]) for r in records if r.get(method) is not None]
        if not pairs:
            metrics[method] = {"status": "Unavailable", "samples": 0}
            continue
        predicted = np.asarray([p for p, _ in pairs], dtype=float)
        actual = np.asarray([a for _, a in pairs], dtype=float)
        metrics[method] = {
            "status": "Measured rolling-origin",
            "samples": int(len(pairs)),
            "mae_pips": round(float(np.mean(np.abs(predicted - actual))), 3),
            "direction_accuracy_pct": round(float(np.mean(np.sign(predicted) == np.sign(actual)) * 100.0), 2),
        }
    metrics["existing_powerbi"] = {"status": "Unavailable without settled historical Power BI forecasts", "samples": 0}
    return {
        "method": "rolling-origin / walk-forward; no random shuffling",
        "origins": len(records),
        "metrics": metrics,
        "claim": "No accuracy superiority is claimed unless measured Similar-Day metrics exceed baselines on sufficient settled samples.",
    }


def similarity_cache_key(canonical: Mapping[str, Any], elapsed_hours: int, config: SimilarDayConfig = CONFIG) -> str:
    context = _canonical_context(canonical)
    raw = "|".join([
        str(context.get("symbol", "EURUSD")), str(context.get("timeframe", "H1")),
        str(context.get("latest_completed") or ""), str(int(elapsed_hours)),
        config.feature_version, config.engine_version, str(context.get("generation") or ""),
        str(context.get("calculation_id") or ""),
    ])
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def _cache_get(state: MutableMapping[str, Any] | None, key: str, config: SimilarDayConfig) -> dict[str, Any] | None:
    if state is None:
        return None
    cache = state.get(CACHE_STATE_KEY)
    if not isinstance(cache, OrderedDict):
        return None
    item = cache.get(key)
    if not isinstance(item, Mapping):
        return None
    if time.time() - _safe_float(item.get("cached_at"), 0.0) > config.cache_ttl_seconds:
        cache.pop(key, None)
        return None
    cache.move_to_end(key)
    payload = item.get("payload")
    return dict(payload) if isinstance(payload, Mapping) else None


def _cache_put(state: MutableMapping[str, Any] | None, key: str, payload: Mapping[str, Any], config: SimilarDayConfig) -> None:
    if state is None:
        return
    existing = state.get(CACHE_STATE_KEY)
    cache = existing if isinstance(existing, OrderedDict) else OrderedDict(existing.items()) if isinstance(existing, dict) else OrderedDict()
    cache[key] = {"cached_at": time.time(), "payload": dict(payload)}
    cache.move_to_end(key)
    while len(cache) > config.cache_generations:
        cache.popitem(last=False)
    state[CACHE_STATE_KEY] = cache



def _historical_medium_bias(summary: Mapping[str, Any]) -> str:
    votes = [_broad_regime(summary.get(name)) for name in ("h1_regime", "h4_regime", "d1_regime")]
    bull = votes.count("BULL")
    bear = votes.count("BEAR")
    reliability = _safe_float(summary.get("reliability"), 50.0)
    if 0 <= reliability <= 1:
        reliability *= 100.0
    if reliability < 35 or bull == bear:
        return "WAIT"
    return "BUY" if bull > bear else "SELL"


def _pattern_support_scores(summary: Mapping[str, Any], family: str) -> tuple[float, float, float, str]:
    text = str(family or "").lower()
    adx = _safe_float(summary.get("adx"), 0.0)
    compression = _safe_float(summary.get("compression"), 0.0)
    if 0 <= compression <= 1:
        compression *= 100.0
    volatility = _safe_float(summary.get("realized_volatility"), _safe_float(summary.get("atr_pct"), 0.0))
    breakout = 80.0 if "breakout" in text else 65.0 if adx >= 25 and compression <= 40 else 30.0
    pullback = 80.0 if "pullback" in text or "rebound" in text else 45.0 if "trend" in text else 25.0
    reversal = 80.0 if "reversal" in text else 55.0 if "rebound" in text else 20.0
    anomaly = "YES" if any(token in text for token in ("shock", "irregular", "unclassified")) or volatility > 3.0 else "NO"
    return _clip(breakout), _clip(pullback), _clip(reversal), anomaly


def _forecast_calibration_rows(forecast_history: pd.DataFrame | None, limit: int = 25) -> list[dict[str, Any]]:
    if not isinstance(forecast_history, pd.DataFrame) or forecast_history.empty:
        return []
    work = forecast_history.copy(deep=False)
    time_col = _find_column(work, ("forecast timestamp", "origin time", "forecast time", "time", "timestamp", "datetime", "date"))
    if time_col:
        parsed = pd.to_datetime(work[time_col], errors="coerce", utc=True)
        work = work.assign(__forecast_time=parsed).sort_values("__forecast_time", ascending=False).head(limit)
    else:
        work = work.tail(limit).iloc[::-1]

    def value(row: pd.Series, aliases: Sequence[str], default: Any = None) -> Any:
        col = _find_column(work, aliases)
        return row.get(col, default) if col else default

    rows: list[dict[str, Any]] = []
    for _, row in work.iterrows():
        pred1 = value(row, ("predicted h+1", "h1 predicted", "predicted close h1", "predicted close", "prediction"))
        act1 = value(row, ("actual h+1", "h1 actual", "actual close h1", "actual close", "actual"))
        pred3 = value(row, ("predicted h+3", "h3 predicted", "predicted close h3"))
        act3 = value(row, ("actual h+3", "h3 actual", "actual close h3"))
        pred6 = value(row, ("predicted h+6", "h6 predicted", "predicted close h6"))
        act6 = value(row, ("actual h+6", "h6 actual", "actual close h6"))
        abs_error = value(row, ("absolute error", "abs error", "absolute close error", "error"))
        if abs_error is None and pred1 is not None and act1 is not None:
            try:
                abs_error = abs(float(pred1) - float(act1))
            except Exception:
                pass
        rows.append({
            "Forecast Timestamp": str(value(row, ("forecast timestamp", "origin time", "forecast time", "time", "timestamp", "datetime", "date"), "Unavailable")),
            "Historical Date": str(value(row, ("historical date", "target date", "date"), "Unavailable")),
            "Predicted H+1 / Actual H+1": f"{pred1} / {act1}" if pred1 is not None or act1 is not None else "Unavailable",
            "Predicted H+3 / Actual H+3": f"{pred3} / {act3}" if pred3 is not None or act3 is not None else "Unavailable",
            "Predicted H+6 / Actual H+6": f"{pred6} / {act6}" if pred6 is not None or act6 is not None else "Unavailable",
            "Absolute Error": abs_error if abs_error is not None else "Unavailable",
            "Directional Accuracy": value(row, ("directional accuracy", "direction accuracy", "direction correct"), "Unavailable"),
            "Band Coverage": value(row, ("band coverage", "interval covered", "inside band"), "Unavailable"),
            "Forecast Reliability": value(row, ("forecast reliability", "reliability", "confidence"), "Unavailable"),
            "Regime": value(row, ("regime", "h1 regime", "major regime"), "Unavailable"),
            "Forecast Age": value(row, ("forecast age", "age hours", "age"), "Unavailable"),
        })
    return rows


def _build_requested_history_tables(
    candidate_records: Sequence[Mapping[str, Any]],
    table_rows: Sequence[Mapping[str, Any]],
    hours: Sequence[int],
    forecast_history: pd.DataFrame | None,
) -> dict[str, list[dict[str, Any]]]:
    by_date = {str(record.get("date")): record for record in candidate_records}
    table_a: list[dict[str, Any]] = []
    table_b: list[dict[str, Any]] = []
    table_c: list[dict[str, Any]] = []
    table_d: list[dict[str, Any]] = []
    matched_hour = f"{max(hours):02d}:00 UTC" if hours else "Unavailable"
    # Fixed history tables are chronological, while the separate Similar-Day
    # table remains similarity-ranked. Only valid aligned trading days enter
    # Tables 4A–4D; rejected candidates stay visible in history_25 with reasons.
    source_rows = []
    for item in table_rows:
        historical_date = str(item.get("Historical Date") or "Unavailable")
        record = by_date.get(historical_date, {})
        if record.get("valid"):
            source_rows.append(item)
    source_rows.sort(key=lambda item: str(item.get("Historical Date") or ""), reverse=True)
    for row in source_rows[:25]:
        historical_date = str(row.get("Historical Date") or "Unavailable")
        record = by_date.get(historical_date, {})
        raw_summary = record.get("summary")
        summary = raw_summary if isinstance(raw_summary, Mapping) else {}
        medium_bias = _historical_medium_bias(summary)
        canonical_decision = str(row.get("Historical Decision") or summary.get("decision") or "Unavailable")
        table_a.append({
            "Date": historical_date, "Matched hour": matched_hour,
            "Master": round(_safe_float(summary.get("master_score")), 2) if summary else None,
            "Entry": round(_safe_float(summary.get("entry_score")), 2) if summary else None,
            "Hold": round(_safe_float(summary.get("hold_safety")), 2) if summary else None,
            "TP Quality": round(_safe_float(summary.get("tp_quality")), 2) if summary else None,
            "Exit Risk": round(_safe_float(summary.get("exit_risk")), 2) if summary else None,
            "Trend Capacity": round(_safe_float(summary.get("trend_capacity")), 2) if summary else None,
            "BUY Pressure": round(_safe_float(summary.get("buy_pressure")), 2) if summary else None,
            "SELL Pressure": round(_safe_float(summary.get("sell_pressure")), 2) if summary else None,
            "Market Quality": round(_safe_float(summary.get("market_quality")), 2) if summary else None,
            "Reliability": round(_safe_float(summary.get("reliability")), 2) if summary else None,
            "Canonical Decision": canonical_decision,
        })
        ten = (
            f"Master={_safe_float(summary.get('master_score')):.2f}; Entry={_safe_float(summary.get('entry_score')):.2f}; "
            f"Hold={_safe_float(summary.get('hold_safety')):.2f}; TP={_safe_float(summary.get('tp_quality')):.2f}; "
            f"ExitRisk={_safe_float(summary.get('exit_risk')):.2f}; TrendCapacity={_safe_float(summary.get('trend_capacity')):.2f}; "
            f"BUY={_safe_float(summary.get('buy_pressure')):.2f}; SELL={_safe_float(summary.get('sell_pressure')):.2f}; "
            f"MarketQuality={_safe_float(summary.get('market_quality')):.2f}; Decision={canonical_decision}"
        )
        table_b.append({
            "Date": historical_date, "Ten Original Decisions": ten,
            "Medium Regime Bias": medium_bias,
            "Less-Risky Decision": row.get("Historical Less-Risky Decision", "Unavailable"),
            "H+1 pips": row.get("H+1 Pips"), "H+3 pips": row.get("H+3 Pips"), "H+6 pips": row.get("H+6 Pips"),
            "MFE": row.get("Maximum Favourable Excursion"), "MAE": row.get("Maximum Adverse Excursion"),
            "TP First / SL First / Neither": row.get("TP First / SL First / Neither", "Neither"),
        })
        reliability = _safe_float(summary.get("reliability"), 0.0)
        adx = _safe_float(summary.get("adx"), 0.0)
        adx_state = "Strong" if adx >= 25 else "Developing" if adx >= 18 else "Weak"
        table_c.append({
            "Date": historical_date, "H1 Regime": summary.get("h1_regime", "Unavailable"),
            "H4 Regime": summary.get("h4_regime", "Unavailable"), "D1 Regime": summary.get("d1_regime", "Unavailable"),
            "Medium-Standard Bias": medium_bias, "Regime Age": record.get("matched", 0),
            "Regime Confidence": round(reliability, 2), "ADX State": adx_state,
            "Compression": round(_safe_float(summary.get("compression")), 2),
            "Conflict": summary.get("conflict_status", "Unavailable"), "Counter-Trend": summary.get("counter_trend", "Unavailable"),
            "Current-Regime Match": row.get("Regime Match"),
        })
        family = _pattern_family(summary, _safe_float(record.get("quality"), 0.0)) if summary else "Unclassified"
        breakout, pullback, reversal, anomaly = _pattern_support_scores(summary, family)
        table_d.append({
            "Date": historical_date, "Pattern Family": family, "Similarity Index": row.get("Similarity Index"),
            "Price-Shape Score": row.get("Price Shape Score"), "DTW Score": row.get("DTW Score"),
            "MPdist-Inspired Score": row.get("Robust Similarity Score"), "Breakout Score": round(breakout, 2),
            "Pullback Score": round(pullback, 2), "Reversal Score": round(reversal, 2),
            "Shock/Anomaly Flag": anomaly, "Data Quality": row.get("Data Quality"),
        })
    return {
        "current_hour_core_metrics_history": table_a,
        "decision_outcome_history": table_b,
        "regime_compatibility_history": table_c,
        "pattern_recognition_history": table_d,
        "powerbi_forecast_calibration_history": _forecast_calibration_rows(forecast_history, limit=25),
    }

def build_similar_day_intelligence(
    ohlc: pd.DataFrame,
    canonical: Mapping[str, Any],
    *,
    history_table: pd.DataFrame | None = None,
    forecast_history: pd.DataFrame | None = None,
    state: MutableMapping[str, Any] | None = None,
    config: SimilarDayConfig = CONFIG,
) -> dict[str, Any]:
    """Build the full Similar-Day payload from completed data only."""
    started = time.perf_counter()
    context = _canonical_context(canonical)
    clean, input_quality = _normalise_ohlc(ohlc, context.get("latest_completed"))
    if clean.empty:
        return {
            "ok": False, "status": "Unavailable", "message": "; ".join(input_quality.get("warnings") or ["No valid OHLC data"]),
            "engine_version": config.engine_version, "feature_version": config.feature_version,
            "schema_version": config.schema_version, "calculated_at": _utc_now_iso(),
        }
    latest = pd.Timestamp(clean["time"].max())
    current_date = latest.date()
    current_rows = clean.loc[clean["time"].dt.date == current_date]
    current_rows = current_rows.loc[current_rows["time"] <= latest].sort_values("time")
    hours = sorted(current_rows["time"].dt.hour.astype(int).unique().tolist())
    if len(hours) < config.minimum_prefix_hours:
        return {
            "ok": False, "status": "Unavailable",
            "message": f"At least {config.minimum_prefix_hours} completed H1 candles are required; found {len(hours)}.",
            "engine_version": config.engine_version, "feature_version": config.feature_version,
            "schema_version": config.schema_version, "calculated_at": _utc_now_iso(),
            "latest_completed_h1_timestamp": latest.isoformat(), "elapsed_hour_count": len(hours),
        }
    cache_id = similarity_cache_key(canonical, len(hours), config)
    cached = _cache_get(state, cache_id, config)
    if cached:
        cached["cache_status"] = "HIT"
        return cached

    aux = _auxiliary_frame(history_table)
    current_aux = _aux_summary(aux, current_date, max(hours))
    current_aux.update({k: v for k, v in context.items() if k in _METRIC_ALIASES or k in _TEXT_ALIASES and v not in (None, "")})
    current_prefix, current_matched, current_missing = _interpolated_prefix(current_rows, hours)
    current_summary = _prefix_features(current_prefix, current_aux)
    duplicate_dates = set(input_quality.get("duplicate_dates") or [])
    unsorted_dates = set(input_quality.get("unsorted_dates") or [])
    current_quality = _quality_score(
        matched=current_matched, expected=len(hours), duplicate=current_date.isoformat() in duplicate_dates,
        unsorted_input=bool(input_quality.get("unsorted_input")), volume_quality=_safe_float(current_summary.get("volume_quality")), current=True,
    )
    current_summary["data_quality"] = current_quality

    candidate_dates = _calendar_candidates(current_date, config.candidate_days)
    candidate_records: list[dict[str, Any]] = []
    valid_vectors: list[np.ndarray] = []
    valid_indices: list[int] = []
    persistence_rows: list[dict[str, Any]] = []
    max_missing = max(0, int(math.floor(len(hours) * config.maximum_missing_ratio)))

    for candidate_date in candidate_dates:
        day_rows = clean.loc[clean["time"].dt.date == candidate_date]
        prefix, matched, missing_hours = _interpolated_prefix(day_rows, hours)
        duplicate = candidate_date.isoformat() in duplicate_dates
        candidate_unsorted = candidate_date.isoformat() in unsorted_dates
        warnings: list[str] = []
        if day_rows.empty:
            warnings.append("Holiday, empty trading day, or data not loaded")
        if duplicate:
            warnings.append("Duplicate timestamp detected; candidate rejected")
        if candidate_unsorted:
            warnings.append("Unsorted timestamp sequence detected; candidate rejected")
        if missing_hours and len(missing_hours) <= max_missing:
            warnings.append(
                "Missing corresponding H1 candle safely interpolated for shape matching: "
                + ", ".join(f"{hour:02d}:00 UTC" for hour in missing_hours)
            )
        if len(missing_hours) > max_missing:
            warnings.append(f"Insufficient corresponding H1 observations: missing {len(missing_hours)} of {len(hours)}")
        valid = bool(not prefix.empty and not duplicate and not candidate_unsorted and len(missing_hours) <= max_missing and matched >= config.minimum_prefix_hours)
        aux_values = _aux_summary(aux, candidate_date, max(hours))
        summary = _prefix_features(prefix, aux_values) if not prefix.empty else {}
        quality = _quality_score(
            matched=matched, expected=len(hours), duplicate=duplicate, unsorted_input=False,
            volume_quality=_safe_float(summary.get("volume_quality")), current=False,
        )
        if quality < 70:
            warnings.append("Low data quality")
        record: dict[str, Any] = {
            "date": candidate_date,
            "prefix": prefix,
            "summary": summary,
            "matched": matched,
            "missing_hours": missing_hours,
            "valid": valid,
            "warnings": warnings,
            "quality": quality,
            "weekday": candidate_date.weekday(),
            "stage1_distance": float("inf"),
        }
        candidate_records.append(record)
        if valid:
            valid_indices.append(len(candidate_records) - 1)
            valid_vectors.append(_feature_vector(summary))
        persistence_rows.append({
            "symbol": context.get("symbol", "EURUSD"), "timeframe": context.get("timeframe", "H1"),
            "trading_date": candidate_date.isoformat(), "feature_version": config.feature_version,
            "completed_hours": len(hours), "feature_vector": _feature_vector(summary).tolist() if summary else [],
            "normalized_return_path": np.asarray(summary.get("path") if summary.get("path") is not None else [], dtype=np.float32).tolist() if summary else [],
            "regime_labels": {k: summary.get(k) for k in ("h1_regime", "h4_regime", "d1_regime")},
            "outcome_fields": {}, "data_quality_flags": warnings, "created_at": _utc_now_iso(),
        })

    if valid_vectors:
        distances = _robust_scaled_distances(_feature_vector(current_summary), valid_vectors)
        for index, distance in zip(valid_indices, distances):
            candidate_records[index]["stage1_distance"] = distance
            candidate_records[index]["stage1_score"] = _score_from_distance(distance, 1.25)
    stage2_indices = sorted(valid_indices, key=lambda i: candidate_records[i]["stage1_distance"])[: config.stage2_candidates]

    current_path = np.asarray(current_summary.get("path"), dtype=np.float32)
    for index in stage2_indices:
        record = candidate_records[index]
        candidate_path = np.asarray(record["summary"].get("path"), dtype=np.float32)
        a = _resample_path(current_path, max(len(current_path), len(candidate_path), 8))
        b = _resample_path(candidate_path, len(a))
        euclidean = float(np.sqrt(np.mean((a - b) ** 2)))
        mp = matrix_profile_style_distance(a, b)
        mpdist = mpdist_inspired_distance(a, b)
        radius = max(1, int(math.ceil(len(a) * config.dtw_window_ratio)))
        lower_bound = lb_keogh(a, b, radius)
        dtw = constrained_dtw_distance(a, b, window=radius, max_cost=max(3.5, lower_bound * 4.0))
        eu_score = _score_from_distance(euclidean, 1.0)
        mp_score = _score_from_distance(mp, 1.0)
        robust_score = _score_from_distance(mpdist, 1.0)
        dtw_score = _score_from_distance(dtw, 1.0)
        shape_score = (
            config.shape_weights["euclidean"] * eu_score
            + config.shape_weights["matrix_profile_style"] * mp_score
            + config.shape_weights["mpdist_inspired"] * robust_score
            + config.shape_weights["dtw"] * dtw_score
        )
        regime_score = _regime_score(current_summary, record["summary"])
        volatility_score = _volatility_score(current_summary, record["summary"])
        adx_score, pressure_score = _adx_pressure_scores(current_summary, record["summary"])
        adx_pressure = (adx_score + pressure_score) / 2.0
        session_score = _clip(70.0 * record["matched"] / len(hours) + (30.0 if record["weekday"] == current_date.weekday() else 15.0))
        quality_score = min(current_quality, record["quality"])
        similarity = (
            config.weights["price_path_shape"] * shape_score
            + config.weights["regime_compatibility"] * regime_score
            + config.weights["volatility_atr"] * volatility_score
            + config.weights["adx_di_pressure"] * adx_pressure
            + config.weights["elapsed_session"] * session_score
            + config.weights["data_event_quality"] * quality_score
        )
        record.update({
            "euclidean_score": eu_score, "matrix_profile_score": mp_score,
            "robust_score": robust_score, "dtw_score": dtw_score,
            "shape_score": shape_score, "regime_score": regime_score,
            "volatility_score": volatility_score, "adx_score": adx_score,
            "pressure_score": pressure_score, "session_score": session_score,
            "similarity_index": _clip(similarity), "dtw_window": radius,
        })

    for index in valid_indices:
        if index not in stage2_indices:
            record = candidate_records[index]
            # Stage-1-only rows remain ranked honestly below the fully reranked set.
            proxy = _clip(record.get("stage1_score", 0.0) * 0.45)
            record.update({
                "euclidean_score": None, "matrix_profile_score": None, "robust_score": None,
                "dtw_score": None, "shape_score": proxy, "regime_score": _regime_score(current_summary, record["summary"]),
                "volatility_score": _volatility_score(current_summary, record["summary"]),
                "adx_score": _adx_pressure_scores(current_summary, record["summary"])[0],
                "pressure_score": _adx_pressure_scores(current_summary, record["summary"])[1],
                "session_score": _clip(70.0 * record["matched"] / len(hours) + (30.0 if record["weekday"] == current_date.weekday() else 15.0)),
                "similarity_index": proxy, "warnings": record["warnings"] + ["Stage-1 screened; DTW not run"],
            })

    # Ranking is finalized before any historical future outcome is read.
    ranked_indices = sorted(
        range(len(candidate_records)),
        key=lambda i: (candidate_records[i].get("similarity_index", 0.0), candidate_records[i].get("quality", 0.0), candidate_records[i]["date"]),
        reverse=True,
    )
    for rank, index in enumerate(ranked_indices, start=1):
        candidate_records[index]["rank"] = rank

    table_rows: list[dict[str, Any]] = []
    for index in ranked_indices:
        record = candidate_records[index]
        outcome = _outcomes(clean, record["prefix"], record["summary"], config) if record["valid"] and not record["prefix"].empty else {
            "historical_decision": "Unavailable", "historical_less_risky_decision": "Unavailable",
            "h1_direction": "Unavailable", "h1_pips": None, "h3_direction": "Unavailable", "h3_pips": None,
            "h6_direction": "Unavailable", "h6_pips": None, "mfe_pips": None, "mae_pips": None,
            "expected_range_pips": None, "tp_sl_result": "Neither", "tp_sl_warning": "",
        }
        for persisted in persistence_rows:
            if persisted["trading_date"] == record["date"].isoformat():
                persisted["outcome_fields"] = outcome
                break
        warnings = list(record["warnings"])
        if outcome.get("tp_sl_warning"):
            warnings.append(outcome["tp_sl_warning"])
        row = {
            "Rank": int(record["rank"]),
            "Historical Date": record["date"].isoformat(),
            "Matched Hour Count": f"{record['matched']}/{len(hours)}",
            "Similarity Index": round(_safe_float(record.get("similarity_index")), 2),
            "Price Shape Score": round(_safe_float(record.get("shape_score")), 2) if record.get("shape_score") is not None else None,
            "Robust Similarity Score": round(_safe_float(record.get("robust_score")), 2) if record.get("robust_score") is not None else None,
            "DTW Score": round(_safe_float(record.get("dtw_score")), 2) if record.get("dtw_score") is not None else None,
            "Regime Match": round(_safe_float(record.get("regime_score")), 2) if record.get("regime_score") is not None else None,
            "Volatility Match": round(_safe_float(record.get("volatility_score")), 2) if record.get("volatility_score") is not None else None,
            "ADX/DI Match": round(_safe_float(record.get("adx_score")), 2) if record.get("adx_score") is not None else None,
            "Pressure Match": round(_safe_float(record.get("pressure_score")), 2) if record.get("pressure_score") is not None else None,
            "Session Match": round(_safe_float(record.get("session_score")), 2) if record.get("session_score") is not None else None,
            "Historical Decision": outcome.get("historical_decision", "Unavailable"),
            "Historical Less-Risky Decision": outcome.get("historical_less_risky_decision", "Unavailable"),
            "H+1 Direction": outcome.get("h1_direction", "Unavailable"),
            "H+1 Pips": outcome.get("h1_pips"),
            "H+3 Direction": outcome.get("h3_direction", "Unavailable"),
            "H+3 Pips": outcome.get("h3_pips"),
            "H+6 Direction": outcome.get("h6_direction", "Unavailable"),
            "H+6 Pips": outcome.get("h6_pips"),
            "Maximum Favourable Excursion": outcome.get("mfe_pips"),
            "Maximum Adverse Excursion": outcome.get("mae_pips"),
            "TP First / SL First / Neither": outcome.get("tp_sl_result", "Neither"),
            "Historical Regime": str(record["summary"].get("h1_regime") or "Unavailable") if record["summary"] else "Unavailable",
            "Data Quality": round(record["quality"], 2),
            "Exclusion or Warning Reason": "; ".join(dict.fromkeys(warnings)) if warnings else "Included",
            "weekday": record["weekday"],
            "h3_pips": outcome.get("h3_pips"),
        }
        table_rows.append(row)

    top = [row for row in table_rows if row["Similarity Index"] > 0][: config.top_matches]
    weights = [max(1e-6, row["Similarity Index"]) for row in top]
    weight_total = sum(weights)
    normalized_weights = [w / weight_total for w in weights] if weight_total else []
    directions = [row["H+3 Direction"] for row in top if row["H+3 Direction"] in {"BUY", "SELL", "WAIT"}]
    direction_weight: dict[str, float] = {"BUY": 0.0, "SELL": 0.0, "WAIT": 0.0}
    for row, weight in zip(top, normalized_weights):
        direction = row["H+3 Direction"]
        if direction in direction_weight:
            direction_weight[direction] += weight
    weighted_direction = max(direction_weight, key=direction_weight.get) if top else "WAIT"
    agreement_count = sum(1 for direction in directions if direction == weighted_direction)
    effective_n = 1.0 / sum(w * w for w in normalized_weights) if normalized_weights else 0.0

    def wm(column: str) -> float | None:
        return _weighted_median([row.get(column) for row in top], weights)

    regime_compat = float(np.average([row.get("Regime Match") or 0 for row in top], weights=weights)) if top else 0.0
    best_score = top[0]["Similarity Index"] if top else 0.0
    pattern = _pattern_family(current_summary, current_quality)
    anomaly = pattern in {"High-volatility news shock", "Low-liquidity irregular day"}
    has_current_gaps = bool(current_missing)
    reliability = reliability_label(
        agreement_count=agreement_count, effective_sample_size=effective_n, data_quality=current_quality,
        regime_compatibility=regime_compat, best_similarity=best_score, anomaly=anomaly,
        missing_current_hours=has_current_gaps,
    )
    canonical_decision = context.get("less_risky_decision") or context.get("decision") or "WAIT"
    conflict, conflict_text = canonical_conflict_warning(weighted_direction, canonical_decision)
    summary = {
        "Current pattern family": pattern,
        "Best historical match date": top[0]["Historical Date"] if top else "Unavailable",
        "Best Similarity Index": round(best_score, 2),
        "Top-five directional agreement": f"{agreement_count}/{len(directions)} {weighted_direction}" if directions else "Unavailable",
        "Weighted historical result": weighted_direction,
        "Weighted median H+1 movement": round(wm("H+1 Pips"), 2) if wm("H+1 Pips") is not None else None,
        "Weighted median H+3 movement": round(wm("H+3 Pips"), 2) if wm("H+3 Pips") is not None else None,
        "Weighted median H+6 movement": round(wm("H+6 Pips"), 2) if wm("H+6 Pips") is not None else None,
        "Historical expected range": round(wm("expected_range_pips"), 2) if wm("expected_range_pips") is not None else round(_weighted_median([next((p["outcome_fields"].get("expected_range_pips") for p in persistence_rows if p["trading_date"] == row["Historical Date"]), None) for row in top], weights) or 0.0, 2),
        "Historical MFE": round(wm("Maximum Favourable Excursion"), 2) if wm("Maximum Favourable Excursion") is not None else None,
        "Historical MAE": round(wm("Maximum Adverse Excursion"), 2) if wm("Maximum Adverse Excursion") is not None else None,
        "Effective sample size": round(effective_n, 2),
        "Current-regime compatibility": round(regime_compat, 2),
        "Data quality": round(current_quality, 2),
        "Similar-day reliability": reliability,
        "Conflict with canonical current decision": conflict_text,
    }
    # Fill expected range directly from persisted outcomes without exposing helper columns.
    range_values, range_weights = [], []
    for row, weight in zip(top, weights):
        persisted = next((p for p in persistence_rows if p["trading_date"] == row["Historical Date"]), None)
        value = (persisted or {}).get("outcome_fields", {}).get("expected_range_pips")
        if value is not None:
            range_values.append(value); range_weights.append(weight)
    expected_range = _weighted_median(range_values, range_weights)
    summary["Historical expected range"] = round(expected_range, 2) if expected_range is not None else None

    baselines = _current_baselines(table_rows, current_date.weekday(), current_summary.get("h1_regime", "UNKNOWN"), canonical)
    validation = walk_forward_validation(clean, hours, config)
    public_table = [{k: v for k, v in row.items() if k not in {"weekday", "h3_pips", "expected_range_pips"}} for row in table_rows]
    public_top = public_table[: config.top_matches]
    requested_tables = _build_requested_history_tables(candidate_records, table_rows, hours, forecast_history)
    payload: dict[str, Any] = {
        "ok": True,
        "status": "Ready",
        "schema_version": config.schema_version,
        "engine_version": config.engine_version,
        "feature_version": config.feature_version,
        "calculation_id": context.get("calculation_id"),
        "calculation_generation": context.get("generation"),
        "symbol": context.get("symbol", "EURUSD"),
        "timeframe": context.get("timeframe", "H1"),
        "calculated_at": _utc_now_iso(),
        "latest_completed_h1_timestamp": latest.isoformat(),
        "current_trading_date_utc": current_date.isoformat(),
        "elapsed_hour_count": len(hours),
        "matched_hours_utc": hours,
        "weights": dict(config.weights),
        "summary": summary,
        "top_five": public_top,
        "history_25": public_table,
        **requested_tables,
        "baselines": baselines,
        "walk_forward_validation": validation,
        "reliability": reliability,
        "conflict_warning": conflict_text if conflict else "",
        "explanation": (
            "Similarity Index is a 0–100 research blend of price-path shape, regime, volatility/ATR, ADX/DI/pressure, elapsed-session alignment, and data quality. "
            "It is not a probability. Historical H+1/H+3/H+6 outcomes are calculated only after ranking and never enter similarity features."
        ),
        "input_quality": input_quality,
        "no_lookahead": {
            "completed_current_candles_only": True,
            "equal_elapsed_hour_windows": True,
            "historical_future_excluded_from_features": True,
            "outcomes_calculated_after_ranking": True,
            "future_rows_used_in_similarity": 0,
            "normalization_fit": "historical candidate prefixes only",
        },
        "cache_key": cache_id,
        "cache_status": "MISS",
        "calculation_duration_seconds": round(time.perf_counter() - started, 6),
        "_feature_store_rows": persistence_rows,
    }
    payload = _json_safe(payload)
    _cache_put(state, cache_id, payload, config)
    if state is not None:
        state[ACTIVE_STATE_KEY] = payload
    return payload


def migrate_similarity_store(db_path: Path | str = DB_PATH) -> dict[str, Any]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS similar_day_feature_store (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                trading_date TEXT NOT NULL,
                feature_version TEXT NOT NULL,
                completed_hours INTEGER NOT NULL,
                feature_vector_json TEXT NOT NULL,
                normalized_return_path_json TEXT NOT NULL,
                regime_labels_json TEXT NOT NULL,
                outcome_fields_json TEXT NOT NULL,
                data_quality_flags_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(symbol,timeframe,trading_date,feature_version,completed_hours)
            );
            CREATE INDEX IF NOT EXISTS idx_similar_feature_lookup
                ON similar_day_feature_store(symbol,timeframe,feature_version,trading_date DESC);
            CREATE TABLE IF NOT EXISTS similar_day_generations (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                calculation_generation INTEGER NOT NULL,
                calculation_id TEXT NOT NULL,
                latest_completed_h1_timestamp TEXT NOT NULL,
                engine_version TEXT NOT NULL,
                feature_version TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(symbol,timeframe,calculation_generation)
            );
            CREATE INDEX IF NOT EXISTS idx_similar_generation_latest
                ON similar_day_generations(symbol,timeframe,calculation_generation DESC);
            """
        )
        conn.commit()
        return {"ok": True, "schema_version": STORE_SCHEMA_VERSION, "path": str(path)}
    finally:
        conn.close()


def persist_similarity_generation(
    payload: Mapping[str, Any], feature_rows: Sequence[Mapping[str, Any]], *, db_path: Path | str = DB_PATH, config: SimilarDayConfig = CONFIG
) -> dict[str, Any]:
    """One transaction with generation/timestamp stale-write protection."""
    migrate_similarity_store(db_path)
    public = {k: v for k, v in dict(payload).items() if not str(k).startswith("_")}
    symbol = str(public.get("symbol") or "EURUSD")
    timeframe = str(public.get("timeframe") or "H1")
    generation = numeric_generation(public.get("calculation_generation") or public.get("generation_id"), default=1)
    latest = str(public.get("latest_completed_h1_timestamp") or "")
    calculation_id = str(public.get("calculation_id") or "")
    if generation < 1 or not latest:
        return {"ok": False, "status": "REJECTED", "reason": "Generation and latest completed timestamp are required"}
    path = Path(db_path)
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT calculation_generation, latest_completed_h1_timestamp FROM similar_day_generations WHERE symbol=? AND timeframe=? ORDER BY calculation_generation DESC LIMIT 1",
            (symbol, timeframe),
        ).fetchone()
        if current:
            current_generation, current_latest = int(current[0]), str(current[1])
            incoming_ts = pd.to_datetime(latest, errors="coerce", utc=True)
            current_ts = pd.to_datetime(current_latest, errors="coerce", utc=True)
            if generation < current_generation or (generation == current_generation and pd.notna(incoming_ts) and pd.notna(current_ts) and incoming_ts < current_ts):
                conn.rollback()
                return {"ok": False, "status": "STALE_REJECTED", "existing_generation": current_generation, "incoming_generation": generation}
        for row in feature_rows:
            conn.execute(
                """INSERT OR REPLACE INTO similar_day_feature_store(
                    symbol,timeframe,trading_date,feature_version,completed_hours,
                    feature_vector_json,normalized_return_path_json,regime_labels_json,
                    outcome_fields_json,data_quality_flags_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(row.get("symbol") or symbol), str(row.get("timeframe") or timeframe), str(row.get("trading_date")),
                    str(row.get("feature_version") or config.feature_version), int(row.get("completed_hours") or 0),
                    json.dumps(_json_safe(row.get("feature_vector") or []), separators=(",", ":")),
                    json.dumps(_json_safe(row.get("normalized_return_path") or []), separators=(",", ":")),
                    json.dumps(_json_safe(row.get("regime_labels") or {}), separators=(",", ":")),
                    json.dumps(_json_safe(row.get("outcome_fields") or {}), separators=(",", ":")),
                    json.dumps(_json_safe(row.get("data_quality_flags") or []), separators=(",", ":")),
                    str(row.get("created_at") or _utc_now_iso()),
                ),
            )
        conn.execute(
            """INSERT OR REPLACE INTO similar_day_generations(
                symbol,timeframe,calculation_generation,calculation_id,latest_completed_h1_timestamp,
                engine_version,feature_version,cache_key,payload_json,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                symbol, timeframe, generation, calculation_id, latest,
                str(public.get("engine_version") or config.engine_version), str(public.get("feature_version") or config.feature_version),
                str(public.get("cache_key") or ""), json.dumps(_json_safe(public), ensure_ascii=False, separators=(",", ":")), _utc_now_iso(),
            ),
        )
        stale = conn.execute(
            "SELECT calculation_generation FROM similar_day_generations WHERE symbol=? AND timeframe=? ORDER BY calculation_generation DESC LIMIT -1 OFFSET ?",
            (symbol, timeframe, config.cache_generations),
        ).fetchall()
        for (old_generation,) in stale:
            conn.execute(
                "DELETE FROM similar_day_generations WHERE symbol=? AND timeframe=? AND calculation_generation=?",
                (symbol, timeframe, int(old_generation)),
            )
        conn.commit()
        return {"ok": True, "status": "PUBLISHED", "generation": generation, "feature_rows": len(feature_rows), "path": str(path)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_latest_similarity_generation(
    symbol: str = "EURUSD", timeframe: str = "H1", *, db_path: Path | str = DB_PATH
) -> dict[str, Any]:
    """Load the latest persisted generation without running migration from UI paths."""
    conn = connect_readonly(db_path)
    try:
        row = conn.execute(
            "SELECT payload_json FROM similar_day_generations WHERE symbol=? AND timeframe=? ORDER BY calculation_generation DESC LIMIT 1",
            (str(symbol), str(timeframe)),
        ).fetchone()
        return json.loads(row[0]) if row else {}
    finally:
        conn.close()


__all__ = [
    "DB_PATH", "CACHE_STATE_KEY", "ACTIVE_STATE_KEY", "build_similar_day_intelligence",
    "similarity_cache_key", "matrix_profile_style_distance", "mpdist_inspired_distance",
    "lb_keogh", "constrained_dtw_distance", "walk_forward_validation",
    "reliability_label", "canonical_conflict_warning",
    "migrate_similarity_store", "persist_similarity_generation", "load_latest_similarity_generation",
]
