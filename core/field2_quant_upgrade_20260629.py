"""Adaptive Field 2 research layer.

Builds a completed-candle, symbol-specific overlay for:
- central tendency and volatility-expanded prediction bands;
- strong-trend breakout probability;
- 25-day relationship mapping;
- most-similar six-hour historical pattern via Dynamic Time Warping.

The layer is additive.  It never rewrites protected production decisions or the
legacy prediction cache.  It is built only from the explicit Settings run path
and rendered read-only in Lunch Field 2.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping
import math
import time

import numpy as np
import pandas as pd

STATE_KEY = "field2_quant_upgrade_20260629"
VERSION = "field2-adaptive-quant-v1"


@dataclass(frozen=True)
class _Columns:
    time: str
    open: str
    high: str
    low: str
    close: str
    volume: str | None = None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _canonical(state: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        from core.canonical_lookup_20260626 import resolve_canonical
        value = resolve_canonical(state)
        return value if isinstance(value, Mapping) else {}
    except Exception:
        return {}


def _candidate_frames(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> list[pd.DataFrame]:
    candidates: list[Any] = [
        state.get("last_df"), state.get("lunch_df"), state.get("clean_lunch_df"),
        state.get("prepared_lunch_df"), state.get("full_metric_history_df_20260618"),
        canonical.get("ohlc"), canonical.get("market_data"), _mapping(canonical.get("market")).get("ohlc"),
    ]
    result: list[pd.DataFrame] = []
    for value in candidates:
        if isinstance(value, pd.DataFrame) and not value.empty:
            result.append(value)
        elif isinstance(value, list) and value:
            try:
                frame = pd.DataFrame(value)
                if not frame.empty:
                    result.append(frame)
            except Exception:
                pass
    return result


def _find_columns(frame: pd.DataFrame) -> _Columns | None:
    normalized = {str(c).strip().lower().replace("_", " "): str(c) for c in frame.columns}

    def find(*names: str) -> str | None:
        for name in names:
            hit = normalized.get(name)
            if hit is not None:
                return hit
        return None

    time_col = find("time", "datetime", "date time", "timestamp", "broker candle time", "completed broker candle")
    if time_col is None and isinstance(frame.index, pd.DatetimeIndex):
        time_col = "__index_time__"
    open_col = find("open", "o")
    high_col = find("high", "h")
    low_col = find("low", "l")
    close_col = find("close", "c", "last")
    volume_col = find("volume", "tick volume", "tick_volume", "vol")
    if not all((time_col, open_col, high_col, low_col, close_col)):
        return None
    return _Columns(time_col, open_col, high_col, low_col, close_col, volume_col)


def _normalize_ohlc(frame: pd.DataFrame) -> pd.DataFrame:
    columns = _find_columns(frame)
    if columns is None:
        return pd.DataFrame()
    work = frame.copy(deep=False)
    if columns.time == "__index_time__":
        times = pd.to_datetime(work.index, errors="coerce", utc=True)
    else:
        times = pd.to_datetime(work[columns.time], errors="coerce", utc=True, format="mixed")
    out = pd.DataFrame(index=work.index)
    out["time"] = times
    out["open"] = pd.to_numeric(work[columns.open], errors="coerce")
    out["high"] = pd.to_numeric(work[columns.high], errors="coerce")
    out["low"] = pd.to_numeric(work[columns.low], errors="coerce")
    out["close"] = pd.to_numeric(work[columns.close], errors="coerce")
    if columns.volume:
        out["volume"] = pd.to_numeric(work[columns.volume], errors="coerce")
    out = out.dropna(subset=["time", "open", "high", "low", "close"])
    out = out.loc[(out[["open", "high", "low", "close"]] > 0).all(axis=1)]
    out = out.sort_values("time", kind="mergesort").drop_duplicates("time", keep="last")
    return out.reset_index(drop=True)


def select_market_frame(state: Mapping[str, Any], canonical: Mapping[str, Any] | None = None) -> pd.DataFrame:
    canonical = canonical or _canonical(state)
    scored: list[tuple[pd.Timestamp, int, pd.DataFrame]] = []
    for order, frame in enumerate(_candidate_frames(state, canonical)):
        clean = _normalize_ohlc(frame)
        if clean.empty:
            continue
        latest = pd.Timestamp(clean["time"].max())
        scored.append((latest, len(clean) * 10 - order, clean))
    if not scored:
        return pd.DataFrame()
    return max(scored, key=lambda item: (item[0], item[1]))[2]


def _true_range(frame: pd.DataFrame) -> pd.Series:
    prev_close = frame["close"].shift(1)
    return pd.concat([
        frame["high"] - frame["low"],
        (frame["high"] - prev_close).abs(),
        (frame["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)


def _hurst(values: pd.Series) -> float:
    series = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    if len(series) < 48:
        return 0.5
    returns = np.diff(np.log(series.to_numpy()))
    max_lag = min(32, max(8, len(returns) // 5))
    lags = np.arange(2, max_lag)
    tau = []
    valid_lags = []
    for lag in lags:
        diff = returns[lag:] - returns[:-lag]
        value = np.std(diff)
        if np.isfinite(value) and value > 0:
            valid_lags.append(lag)
            tau.append(value)
    if len(tau) < 4:
        return 0.5
    slope = np.polyfit(np.log(valid_lags), np.log(tau), 1)[0]
    return float(np.clip(slope, 0.05, 0.95))


def _ewma_garch_variance(returns: pd.Series, horizons: int = 6) -> list[float]:
    values = pd.to_numeric(returns, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) < 10:
        base = float(np.nanstd(values)) if len(values) else 0.0001
        return [max(base * base, 1e-12)] * horizons
    values = values[-500:]
    unconditional = float(np.var(values, ddof=1))
    unconditional = max(unconditional, 1e-12)
    omega = unconditional * 0.03
    alpha = 0.12
    beta = 0.85
    variance = unconditional
    for residual in values:
        variance = omega + alpha * float(residual * residual) + beta * variance
    forecasts: list[float] = []
    last_sq = float(values[-1] * values[-1])
    for _ in range(horizons):
        variance = omega + alpha * last_sq + beta * variance
        forecasts.append(max(float(variance), 1e-12))
        last_sq = variance
    return forecasts


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-float(np.clip(value, -30.0, 30.0))))


def _breakout_features(frame: pd.DataFrame) -> dict[str, Any]:
    work = frame.copy()
    tr = _true_range(work)
    atr = tr.rolling(14, min_periods=5).mean()
    latest = work.iloc[-1]
    previous = work.iloc[-2]
    body = abs(float(latest["close"] - latest["open"]))
    prev_body = abs(float(previous["close"] - previous["open"]))
    body_ratio = body / max(prev_body, 1e-12)
    atr_now = float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else float(tr.tail(14).mean())
    range_atr = float(latest["high"] - latest["low"]) / max(atr_now, 1e-12)
    recent_high = float(work["high"].iloc[-21:-1].max()) if len(work) >= 21 else float(work["high"].iloc[:-1].max())
    recent_low = float(work["low"].iloc[-21:-1].min()) if len(work) >= 21 else float(work["low"].iloc[:-1].min())
    direction = "BUY" if latest["close"] >= latest["open"] else "SELL"
    breakout_up = float(latest["close"] > recent_high)
    breakout_down = float(latest["close"] < recent_low)
    breakout = breakout_up if direction == "BUY" else breakout_down
    returns = np.log(work["close"]).diff()
    momentum3 = float(returns.tail(3).sum())
    momentum6 = float(returns.tail(6).sum())
    momentum_aligned = momentum6 if direction == "BUY" else -momentum6
    return_std = float(returns.tail(48).std())
    momentum_z = momentum_aligned / max(return_std * math.sqrt(6.0), 1e-12)
    volume_z = 0.0
    if "volume" in work.columns and work["volume"].notna().sum() >= 20:
        history = work["volume"].tail(50)
        std = float(history.std())
        volume_z = (float(history.iloc[-1]) - float(history.mean())) / max(std, 1e-12)
    hurst = _hurst(work["close"].tail(300))
    # A 3x candle, resistance/support break, range expansion, aligned momentum,
    # order-flow proxy and persistent Hurst regime all increase continuation odds.
    logit = (
        -1.35
        + 0.72 * min(body_ratio, 5.0)
        + 1.15 * breakout
        + 0.62 * min(range_atr, 4.0)
        + 0.48 * float(np.clip(momentum_z, -3.0, 3.0))
        + 0.22 * float(np.clip(volume_z, -3.0, 3.0))
        + 1.10 * (hurst - 0.5)
    )
    probability = _sigmoid(logit)
    return {
        "direction": direction,
        "probability": round(probability * 100.0, 2),
        "body_ratio_vs_previous": round(body_ratio, 3),
        "range_atr_ratio": round(range_atr, 3),
        "broke_recent_resistance": bool(breakout_up),
        "broke_recent_support": bool(breakout_down),
        "momentum_z": round(momentum_z, 3),
        "volume_z": round(volume_z, 3),
        "hurst_exponent": round(hurst, 3),
        "classification": (
            "STRONG CONTINUATION" if probability >= 0.72 else
            "CONTINUATION FAVORED" if probability >= 0.58 else
            "MIXED / CONFIRM" if probability >= 0.42 else
            "REVERSAL / FAILURE RISK"
        ),
    }


def _central_tendency_and_bands(frame: pd.DataFrame, breakout: Mapping[str, Any]) -> pd.DataFrame:
    close = frame["close"].astype(float)
    returns = np.log(close).diff()
    latest = float(close.iloc[-1])
    recent_returns = returns.tail(48).dropna()
    drift = float(recent_returns.median()) if not recent_returns.empty else 0.0
    trimmed = recent_returns.sort_values()
    if len(trimmed) >= 10:
        cut = max(1, int(len(trimmed) * 0.1))
        trimmed = trimmed.iloc[cut:-cut]
    robust_drift = float(trimmed.mean()) if len(trimmed) else drift
    direction_sign = 1.0 if breakout.get("direction") == "BUY" else -1.0
    probability = float(breakout.get("probability") or 0.0) / 100.0
    # During a strong breakout, keep the drift aligned with the breakout rather
    # than capping the path at the previous close.
    aligned_drift = direction_sign * abs(robust_drift)
    effective_drift = (1.0 - probability) * robust_drift + probability * aligned_drift
    variances = _ewma_garch_variance(returns, 6)
    rows = []
    for horizon, variance in enumerate(variances, start=1):
        cumulative_drift = effective_drift * horizon
        central = latest * math.exp(cumulative_drift)
        sigma = math.sqrt(max(variance, 1e-12) * horizon)
        expansion = 1.0 + 0.85 * probability + 0.18 * max(float(breakout.get("range_atr_ratio") or 1.0) - 1.0, 0.0)
        z = 1.64 * expansion
        upper = central * math.exp(z * sigma)
        lower = central * math.exp(-z * sigma)
        rows.append({
            "Horizon": f"+{horizon}H",
            "Hour": horizon,
            "Central Tendency": central,
            "Dynamic Upper Band": upper,
            "Dynamic Lower Band": lower,
            "Forecast Volatility %": sigma * 100.0,
            "Band Expansion Factor": expansion,
        })
    return pd.DataFrame(rows)


def _feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    close = work["close"]
    prev_close = close.shift(1)
    tr = _true_range(work)
    body = work["close"] - work["open"]
    full_range = (work["high"] - work["low"]).replace(0, np.nan)
    features = pd.DataFrame({
        "Return 1H": np.log(close).diff(),
        "Range %": full_range / prev_close,
        "Body %": body / prev_close,
        "Upper Wick %": (work["high"] - work[["open", "close"]].max(axis=1)) / prev_close,
        "Lower Wick %": (work[["open", "close"]].min(axis=1) - work["low"]) / prev_close,
        "ATR %": tr.rolling(14, min_periods=5).mean() / close,
        "Momentum 3H": np.log(close).diff().rolling(3).sum(),
        "Momentum 6H": np.log(close).diff().rolling(6).sum(),
        "Distance EMA 12": close / close.ewm(span=12, adjust=False).mean() - 1.0,
        "Volatility 12H": np.log(close).diff().rolling(12, min_periods=5).std(),
    })
    if "volume" in work.columns and work["volume"].notna().sum() >= 10:
        features["Volume Change"] = np.log(work["volume"].replace(0, np.nan)).diff()
        features["Volume Z"] = (work["volume"] - work["volume"].rolling(24, min_periods=8).mean()) / work["volume"].rolling(24, min_periods=8).std()
    features["Forward Return 1H"] = np.log(close.shift(-1) / close)
    features.insert(0, "Time", work["time"])
    return features.replace([np.inf, -np.inf], np.nan)


def _rankdata(values: pd.Series) -> pd.Series:
    return values.rank(method="average", pct=False)


def _relationship_map(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    features = _feature_frame(frame)
    cutoff = features["Time"].max() - pd.Timedelta(days=25)
    features = features.loc[features["Time"] >= cutoff].copy()
    numeric = [c for c in features.columns if c not in {"Time", "Forward Return 1H"} and pd.api.types.is_numeric_dtype(features[c])]
    rows: list[dict[str, Any]] = []
    target_corr: dict[str, float] = {}
    for column in numeric:
        pair = features[[column, "Forward Return 1H"]].dropna()
        target_corr[column] = float(pair[column].corr(pair["Forward Return 1H"])) if len(pair) >= 20 else 0.0
    current = features.iloc[-1] if not features.empty else pd.Series(dtype=float)
    means = features[numeric].mean(numeric_only=True) if numeric else pd.Series(dtype=float)
    stds = features[numeric].std(numeric_only=True).replace(0, np.nan) if numeric else pd.Series(dtype=float)

    for i, left in enumerate(numeric):
        for right in numeric[i + 1:]:
            pair = features[[left, right]].dropna()
            if len(pair) < 24:
                continue
            pearson = float(pair[left].corr(pair[right]))
            spearman = float(_rankdata(pair[left]).corr(_rankdata(pair[right])))
            agreement = 1.0 - min(abs(abs(pearson) - abs(spearman)), 1.0)
            sample_score = min(len(pair) / 200.0, 1.0)
            trust = 100.0 * (0.48 * abs(pearson) + 0.32 * abs(spearman) + 0.12 * agreement + 0.08 * sample_score)
            z_left = float((current.get(left, np.nan) - means.get(left, np.nan)) / stds.get(left, np.nan)) if pd.notna(stds.get(left, np.nan)) else 0.0
            z_right = float((current.get(right, np.nan) - means.get(right, np.nan)) / stds.get(right, np.nan)) if pd.notna(stds.get(right, np.nan)) else 0.0
            edge = z_left * target_corr.get(left, 0.0) + z_right * target_corr.get(right, 0.0)
            if edge > 0.08:
                decision = "BUY RELATIONSHIP"
            elif edge < -0.08:
                decision = "SELL RELATIONSHIP"
            else:
                decision = "NEUTRAL / WAIT"
            rows.append({
                "Column A": left,
                "Column B": right,
                "Pearson": round(pearson, 4),
                "Spearman": round(spearman, 4),
                "Relationship Trust Score": round(float(np.clip(trust, 0.0, 100.0)), 2),
                "Absorb or Not": "ABSORB" if trust >= 72 and min(abs(pearson), abs(spearman)) >= 0.55 else "OBSERVE" if trust >= 55 else "DO NOT ABSORB",
                "Definitive Decision": decision,
                "Samples": int(len(pair)),
                "Current Edge": round(edge, 4),
            })
    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.sort_values(["Relationship Trust Score", "Samples"], ascending=[False, False], kind="mergesort").head(80).reset_index(drop=True)
    buy_weight = float(table.loc[table["Definitive Decision"] == "BUY RELATIONSHIP", "Relationship Trust Score"].sum()) if not table.empty else 0.0
    sell_weight = float(table.loc[table["Definitive Decision"] == "SELL RELATIONSHIP", "Relationship Trust Score"].sum()) if not table.empty else 0.0
    neutral_weight = float(table.loc[table["Definitive Decision"] == "NEUTRAL / WAIT", "Relationship Trust Score"].sum()) if not table.empty else 0.0
    ratio = buy_weight / sell_weight if sell_weight > 0 else (float("inf") if buy_weight > 0 else 1.0)
    summary = {
        "buy_weight": round(buy_weight, 2),
        "sell_weight": round(sell_weight, 2),
        "neutral_weight": round(neutral_weight, 2),
        "buy_sell_relationship_ratio": "∞" if math.isinf(ratio) else round(ratio, 3),
        "decision": "BUY" if buy_weight > sell_weight * 1.12 else "SELL" if sell_weight > buy_weight * 1.12 else "WAIT",
        "rows": int(len(table)),
        "history_rows": int(len(features)),
    }
    return table, summary


def _dtw_distance(a: np.ndarray, b: np.ndarray) -> float:
    n, m = len(a), len(b)
    matrix = np.full((n + 1, m + 1), np.inf, dtype=float)
    matrix[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = abs(float(a[i - 1] - b[j - 1]))
            matrix[i, j] = cost + min(matrix[i - 1, j], matrix[i, j - 1], matrix[i - 1, j - 1])
    return float(matrix[n, m])


def _normalized_path(closes: pd.Series) -> np.ndarray:
    values = pd.to_numeric(closes, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) == 0:
        return np.array([], dtype=float)
    return values / values[0] - 1.0


def _similar_day(frame: pd.DataFrame) -> dict[str, Any]:
    if len(frame) < 80:
        return {"ok": False, "reason": "At least 80 completed H1 candles are required."}
    current = _normalized_path(frame["close"].tail(6))
    if len(current) != 6:
        return {"ok": False, "reason": "Current six-hour path is incomplete."}
    best: tuple[float, int] | None = None
    # Exclude the latest 18 hours to prevent overlap with the current/future path.
    max_start = len(frame) - 18
    for start in range(0, max_start):
        window = frame.iloc[start:start + 6]
        future = frame.iloc[start + 6:start + 12]
        if len(window) < 6 or len(future) < 6:
            continue
        candidate = _normalized_path(window["close"])
        if len(candidate) != 6:
            continue
        distance = _dtw_distance(current, candidate)
        if best is None or distance < best[0]:
            best = (distance, start)
    if best is None:
        return {"ok": False, "reason": "No non-overlapping historical six-hour match was found."}
    distance, start = best
    match = frame.iloc[start:start + 6].copy()
    future = frame.iloc[start + 6:start + 12].copy()
    match_path = _normalized_path(match["close"])
    future_base = float(match["close"].iloc[0])
    future_path = future["close"].to_numpy(dtype=float) / future_base - 1.0
    overlay = pd.DataFrame({
        "Step": list(range(0, 6)) + list(range(6, 12)),
        "Series": ["Historical Matched 6H"] * 6 + ["Historical Subsequent 6H"] * 6,
        "Normalized Move %": np.concatenate([match_path, future_path]) * 100.0,
        "Time": list(match["time"]) + list(future["time"]),
    })
    current_overlay = pd.DataFrame({
        "Step": range(0, 6),
        "Series": "Current Last 6H",
        "Normalized Move %": current * 100.0,
        "Time": list(frame["time"].tail(6)),
    })
    overlay = pd.concat([overlay, current_overlay], ignore_index=True)
    similarity = 100.0 / (1.0 + 30.0 * distance)
    return {
        "ok": True,
        "dtw_distance": round(distance, 6),
        "similarity_score": round(float(np.clip(similarity, 0.0, 100.0)), 2),
        "match_start_time": match["time"].iloc[0],
        "match_end_time": match["time"].iloc[-1],
        "subsequent_end_time": future["time"].iloc[-1],
        "historical_open": float(match["open"].iloc[0]),
        "historical_close": float(match["close"].iloc[-1]),
        "subsequent_close": float(future["close"].iloc[-1]),
        "subsequent_return_pct": round((float(future["close"].iloc[-1]) / float(match["close"].iloc[-1]) - 1.0) * 100.0, 4),
        "overlay": overlay,
    }


def build_field2_quant_upgrade(state: MutableMapping[str, Any], *, force: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    del force  # The explicit Settings-run caller owns rebuild timing.
    canonical = _canonical(state)
    frame = select_market_frame(state, canonical)
    symbol = str(state.get("symbol") or canonical.get("symbol") or "EURUSD").upper()
    timeframe = str(state.get("timeframe") or canonical.get("timeframe") or "H1").upper()
    if frame.empty or len(frame) < 30:
        result = {
            "ok": False, "version": VERSION, "symbol": symbol, "timeframe": timeframe,
            "error": "At least 30 valid timestamped OHLC rows are required.",
            "rows": int(len(frame)), "built_in_settings": True,
        }
        state[STATE_KEY] = result
        return result

    breakout = _breakout_features(frame)
    path = _central_tendency_and_bands(frame, breakout)
    relationships, relationship_summary = _relationship_map(frame)
    similar = _similar_day(frame)
    latest = frame.iloc[-1]
    result = {
        "ok": True,
        "version": VERSION,
        "symbol": symbol,
        "timeframe": timeframe,
        "run_id": canonical.get("run_id") or canonical.get("canonical_calculation_id"),
        "generation_id": canonical.get("generation_id") or canonical.get("calculation_generation"),
        "completed_candle": latest["time"],
        "current_price": float(latest["close"]),
        "central_tendency": float(path.iloc[0]["Central Tendency"]),
        "breakout": breakout,
        "prediction_path": path,
        "relationship_history": relationships,
        "relationship_summary": relationship_summary,
        "similar_day": similar,
        "rows": int(len(frame)),
        "history_start": frame["time"].min(),
        "history_end": frame["time"].max(),
        "built_in_settings": True,
        "production_values_modified": False,
        "legacy_prediction_cache_modified": False,
        "wall_seconds": round(time.perf_counter() - started, 4),
    }
    state[STATE_KEY] = result
    state["field2_strong_trend_breakout_probability_20260629"] = breakout
    state["field2_dynamic_prediction_bands_20260629"] = path
    state["field2_relationship_map_20260629"] = relationships
    state["field2_most_similar_day_20260629"] = similar
    return result


__all__ = [
    "STATE_KEY", "VERSION", "select_market_frame", "build_field2_quant_upgrade",
]
