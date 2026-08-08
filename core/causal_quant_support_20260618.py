# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Causal supporting evidence for the protected EURUSD H1 Full Metric authority.

The functions in this module never calculate an independent market direction.
They consume the protected Full Metric history and completed H1 OHLC rows, then
return confirmation/protection evidence that can only confirm or force WAIT.
The implementation is intentionally deterministic, bounded to the latest 600
completed H1 rows, and independent of Streamlit so it can be tested directly.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import math
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

SUPPORT_VERSION = "causal-quant-support-20260618-v1"
WINDOWS = {"lower_1d": 24, "medium_5d": 120, "higher_25d": 600}
HORIZONS = (1, 2, 3, 6)
_ALLOWED_DECISIONS = {"STRONG", "ALLOWED"}


def _finite(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _clip(value: Any, low: float = 0.0, high: float = 1.0, default: float = 0.0) -> float:
    number = _finite(value, default)
    return max(low, min(high, float(default if number is None else number)))


def _direction(value: Any) -> str:
    text = str(value or "").upper()
    if "BUY" in text or "BULL" in text or text == "UP":
        return "BUY"
    if "SELL" in text or "BEAR" in text or text == "DOWN":
        return "SELL"
    return "WAIT"


def _json_value(value: Any) -> Any:
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        ts = value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")
        return ts.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _records(frame: pd.DataFrame, limit: int = 600) -> list[dict[str, Any]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return []
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in frame.head(limit).to_dict("records")
    ]


def _find_column(frame: pd.DataFrame, aliases: Sequence[str]) -> Optional[str]:
    cmap = {str(column).strip().lower(): column for column in frame.columns}
    for alias in aliases:
        key = alias.strip().lower()
        if key in cmap:
            return cmap[key]
    for alias in aliases:
        key = alias.strip().lower()
        for lower, original in cmap.items():
            if key in lower:
                return original
    return None


def _normalize_ohlc(frame: Any) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    raw = frame.copy(deep=False)
    tcol = _find_column(raw, ("time", "timestamp", "datetime", "date"))
    if tcol is None:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    out = pd.DataFrame({"time": pd.to_datetime(raw[tcol], utc=True, errors="coerce")})
    for name, aliases in {
        "open": ("open", "o"), "high": ("high", "h"),
        "low": ("low", "l"), "close": ("close", "c"),
        "volume": ("volume", "tick_volume", "vol"),
        "expected_hourly_volatility": ("expected_hourly_volatility",),
        "periodicity_normalized_return": ("periodicity_normalized_return",),
        "periodicity_normalized_range": ("periodicity_normalized_range",),
        "periodicity_normalized_residual": ("periodicity_normalized_residual",),
        "periodicity_reliability": ("periodicity_reliability",),
    }.items():
        col = _find_column(raw, aliases)
        out[name] = pd.to_numeric(raw[col], errors="coerce") if col is not None else np.nan
    out = out.dropna(subset=["time", "open", "high", "low", "close"])
    out = out.sort_values("time", kind="stable").drop_duplicates("time", keep="last")
    out = out.tail(600).reset_index(drop=True)
    return out


def _metric_frame(priority_table: Any) -> pd.DataFrame:
    if not isinstance(priority_table, pd.DataFrame) or priority_table.empty:
        return pd.DataFrame()
    raw = priority_table.copy(deep=False)
    tcol = _find_column(raw, ("time", "candle time", "latest_completed_candle_time", "datetime", "timestamp"))
    if tcol is None:
        return pd.DataFrame()
    raw["time"] = pd.to_datetime(raw[tcol], utc=True, errors="coerce")
    raw = raw.dropna(subset=["time"]).sort_values("time", kind="stable").drop_duplicates("time", keep="last")
    return raw.tail(600).reset_index(drop=True)


def _score_series(frame: pd.DataFrame, aliases: Sequence[str], default: float = np.nan) -> pd.Series:
    col = _find_column(frame, aliases)
    if col is None:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce")


def _text_series(frame: pd.DataFrame, aliases: Sequence[str], default: str = "") -> pd.Series:
    col = _find_column(frame, aliases)
    if col is None:
        return pd.Series(default, index=frame.index, dtype=object)
    return frame[col].astype(str)


def _prepare_evidence_frame(ohlc: Any, priority_table: Any, context: Optional[Mapping[str, Any]] = None) -> pd.DataFrame:
    market = _normalize_ohlc(ohlc)
    metric = _metric_frame(priority_table)
    if market.empty or metric.empty:
        return pd.DataFrame()
    merged = pd.merge_asof(
        market.sort_values("time"), metric.sort_values("time"), on="time",
        direction="backward", tolerance=pd.Timedelta(minutes=5), suffixes=("", "__metric"),
    )
    merged = merged.dropna(subset=["time", "close"]).reset_index(drop=True)
    merged["direction"] = _text_series(merged, ("Direction", "prediction direction", "Less Risky Bias"), "WAIT").map(_direction)
    merged["decision_label"] = _text_series(merged, ("Full Metric Decision", "Decision", "Qualification Status"), "NO TRADE").str.upper()
    merged["regime"] = _text_series(merged, ("Regime", "Current Regime", "Major Regime", "current_major_regime"), "UNKNOWN")
    merged["master"] = _score_series(merged, ("Master /10", "Master Score", "master_score"), 0.0).fillna(0.0)
    merged["entry"] = _score_series(merged, ("Entry /10", "Entry Score", "entry_score"), 0.0).fillna(0.0)
    merged["hold"] = _score_series(merged, ("Hold /10", "Hold Safety", "hold_score"), 0.0).fillna(0.0)
    merged["tp"] = _score_series(merged, ("TP /10", "TP Score", "tp_score"), 0.0).fillna(0.0)
    merged["exit_risk"] = _score_series(merged, ("Exit Risk /10", "Exit Risk", "exit_risk"), 10.0).fillna(10.0)
    merged["buy_pressure"] = _score_series(merged, ("BUY /10", "BUY Score", "buy_score", "buy pressure"), 0.0).fillna(0.0)
    merged["sell_pressure"] = _score_series(merged, ("SELL /10", "SELL Score", "sell_score", "sell pressure"), 0.0).fillna(0.0)
    merged["reliability"] = _score_series(merged, ("Reliability %", "Reliability", "prediction_reliability"), 50.0).fillna(50.0)
    merged["conflict"] = _text_series(merged, ("Conflict Status", "conflict status", "NLP Confirmation"), "NONE").str.upper()
    merged["alpha"] = _score_series(merged, ("Alpha", "alpha", "Regime Alpha"), np.nan)
    merged["delta"] = _score_series(merged, ("Delta", "delta", "Regime Delta"), np.nan)
    merged["expected_value_existing"] = _score_series(merged, ("Expected Value", "expected_value", "EV"), np.nan)

    ctx = dict(context or {})
    regime_ctx = dict(ctx.get("regime") or {}) if isinstance(ctx.get("regime"), Mapping) else {}
    current_regime = regime_ctx.get("major_regime") or regime_ctx.get("current") or ctx.get("current_regime")
    if current_regime:
        merged.loc[merged.index[-1], "regime"] = str(current_regime)
    for key in ("alpha", "delta"):
        value = _finite(regime_ctx.get(key), _finite(ctx.get(key), None))
        if value is not None:
            merged.loc[merged.index[-1], key] = value
    merged["alpha"] = merged["alpha"].ffill().fillna(0.0)
    merged["delta"] = merged["delta"].ffill().fillna(0.0)
    merged["pressure_balance"] = merged["buy_pressure"] - merged["sell_pressure"]
    merged["raw_return_1h"] = merged["close"].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    periodic_return = pd.to_numeric(merged.get("periodicity_normalized_return"), errors="coerce")
    merged["return_1h"] = periodic_return.where(periodic_return.notna(), merged["raw_return_1h"]).fillna(0.0)
    merged["periodicity_normalized_range"] = pd.to_numeric(merged.get("periodicity_normalized_range"), errors="coerce").fillna(0.0)
    merged["periodicity_normalized_residual"] = pd.to_numeric(merged.get("periodicity_normalized_residual"), errors="coerce").fillna(0.0)
    merged["session"] = merged["time"].dt.hour.map(
        lambda hour: "ASIA" if hour < 7 else "LONDON" if hour < 12 else "LONDON_NY_OVERLAP" if hour < 16 else "NEW_YORK" if hour < 21 else "LATE"
    )
    return merged.tail(600).reset_index(drop=True)


def _bucket(value: float, low: float = 4.5, high: float = 6.5) -> str:
    if value < low:
        return "LOW"
    if value < high:
        return "MEDIUM"
    return "HIGH"


def _signed_bucket(value: float, weak: float = 0.05, strong: float = 0.25) -> str:
    if value >= strong:
        return "POS_STRONG"
    if value > weak:
        return "POS_WEAK"
    if value <= -strong:
        return "NEG_STRONG"
    if value < -weak:
        return "NEG_WEAK"
    return "FLAT"


def _state_tokens(frame: pd.DataFrame) -> pd.Series:
    tokens = []
    for _, row in frame.iterrows():
        alpha = float(row.get("alpha", 0.0) or 0.0)
        delta = float(row.get("delta", 0.0) or 0.0)
        relationship = "ALIGNED" if alpha * delta > 0 else "DIVERGENT" if alpha * delta < 0 else "NEUTRAL"
        pressure = float(row.get("pressure_balance", 0.0) or 0.0)
        pressure_label = "BUY_HIGH" if pressure >= 2 else "SELL_HIGH" if pressure <= -2 else "BALANCED"
        conflict = "CONFLICT" if any(x in str(row.get("conflict", "")).upper() for x in ("CONFLICT", "CRITICAL", "SEVERE")) else "CLEAR"
        tokens.append("|".join([
            str(row.get("regime", "UNKNOWN")).upper(), str(row.get("direction", "WAIT")),
            f"MASTER_{_bucket(float(row.get('master', 0) or 0))}", f"ENTRY_{_bucket(float(row.get('entry', 0) or 0))}",
            f"HOLD_{_bucket(float(row.get('hold', 0) or 0))}", f"ALPHA_{_signed_bucket(alpha)}",
            f"DELTA_{_signed_bucket(delta)}", f"AD_{relationship}", pressure_label,
            f"EXIT_{_bucket(10-float(row.get('exit_risk', 10) or 10))}",
            f"REL_{_bucket(float(row.get('reliability', 50) or 50)/10)}", conflict,
            str(row.get("session", "UNKNOWN")),
        ]))
    return pd.Series(tokens, index=frame.index, dtype=object)


def _token_similarity(a: Sequence[str], b: Sequence[str]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    scores = []
    for left, right in zip(a, b):
        lp = left.split("|")
        rp = right.split("|")
        size = max(len(lp), len(rp), 1)
        scores.append(sum(x == y for x, y in zip(lp, rp)) / size)
    return float(np.mean(scores))


def _movement_outcome(frame: pd.DataFrame, index: int, horizon: int, direction: str) -> Optional[dict[str, float]]:
    end = index + int(horizon)
    if direction not in {"BUY", "SELL"} or index < 0 or end >= len(frame):
        return None
    entry = float(frame.loc[index, "close"])
    future = frame.iloc[index + 1:end + 1]
    if future.empty or not math.isfinite(entry) or entry == 0:
        return None
    final = float(future["close"].iloc[-1])
    if direction == "BUY":
        signed_move = (final - entry) / entry
        favourable = (float(future["high"].max()) - entry) / entry
        adverse = (entry - float(future["low"].min())) / entry
    else:
        signed_move = (entry - final) / entry
        favourable = (entry - float(future["low"].min())) / entry
        adverse = (float(future["high"].max()) - entry) / entry
    return {
        "signed_move": float(signed_move), "success": float(signed_move > 0),
        "favourable": max(0.0, float(favourable)), "adverse": max(0.0, float(adverse)),
    }


def _pattern_window(frame: pd.DataFrame, window_rows: int, sequence_length: int = 3) -> dict[str, Any]:
    if len(frame) < sequence_length + 8:
        return {"status": "INSUFFICIENT EVIDENCE", "sample_count": 0, "pattern_confirmation": "NEUTRAL", "confidence": 0.0}
    data = frame.tail(window_rows).reset_index(drop=True)
    tokens = _state_tokens(data)
    current_seq = tokens.tail(sequence_length).tolist()
    current_direction = str(data.iloc[-1]["direction"])
    current_end = len(data) - 1
    candidates: list[tuple[int, float]] = []
    # Past-only: the candidate's 6H outcome must be fully settled before the
    # current sequence begins.
    latest_candidate_end = current_end - sequence_length - max(HORIZONS)
    for end in range(sequence_length - 1, latest_candidate_end + 1):
        candidate_seq = tokens.iloc[end - sequence_length + 1:end + 1].tolist()
        similarity = _token_similarity(current_seq, candidate_seq)
        if similarity >= 0.78:
            candidates.append((end, similarity))
    outcomes: dict[int, list[dict[str, float]]] = {h: [] for h in HORIZONS}
    recencies: list[float] = []
    similarities: list[float] = []
    for end, similarity in candidates:
        direction = str(data.loc[end, "direction"])
        if direction != current_direction or direction not in {"BUY", "SELL"}:
            continue
        age = max(1, current_end - end)
        recencies.append(math.exp(-age / max(24.0, window_rows / 2.0)))
        similarities.append(similarity)
        for horizon in HORIZONS:
            item = _movement_outcome(data, end, horizon, direction)
            if item is not None:
                outcomes[horizon].append(item)
    sample_count = min((len(items) for items in outcomes.values()), default=0)
    if sample_count < 5:
        return {
            "status": "INSUFFICIENT EVIDENCE", "sample_count": int(sample_count),
            "pattern_support": round(sample_count / max(1, len(data)), 6),
            "current_pattern_similarity": round(float(np.mean(similarities)) if similarities else 0.0, 4),
            "pattern_confirmation": "NEUTRAL", "confidence": 0.0,
            "minimum_sample_required": 5, "sequence_length": sequence_length,
        }
    success = {h: float(np.mean([x["success"] for x in outcomes[h]])) for h in HORIZONS}
    favourable_values = [x["favourable"] for h in HORIZONS for x in outcomes[h]]
    adverse_values = [x["adverse"] for h in HORIZONS for x in outcomes[h]]
    outcome_consistency = float(np.mean(list(success.values())))
    sample_strength = min(1.0, sample_count / max(12.0, window_rows * 0.08))
    recency_quality = float(np.mean(recencies)) if recencies else 0.0
    median_favourable = float(np.median(favourable_values)) if favourable_values else 0.0
    median_adverse = float(np.median(adverse_values)) if adverse_values else 0.0
    movement_quality = median_favourable / max(median_favourable + median_adverse, 1e-12)
    confidence = 0.35 * outcome_consistency + 0.25 * sample_strength + 0.20 * recency_quality + 0.20 * movement_quality
    if confidence >= 0.67 and outcome_consistency >= 0.58:
        confirmation = "CONFIRM"
    elif confidence >= 0.52 and outcome_consistency >= 0.52:
        confirmation = "WEAK CONFIRM"
    elif outcome_consistency < 0.35 and sample_strength >= 0.8:
        confirmation = "WAIT"
    elif outcome_consistency < 0.42 and sample_strength >= 0.6:
        confirmation = "PROTECT"
    else:
        confirmation = "NEUTRAL"
    return {
        "status": "VALID", "sample_count": int(sample_count),
        "pattern_support": round(sample_count / max(1, len(data)), 6),
        "pattern_recency": round(recency_quality, 4),
        "1h_directional_success": round(success[1], 4),
        "2h_directional_success": round(success[2], 4),
        "3h_directional_success": round(success[3], 4),
        "6h_directional_success": round(success[6], 4),
        "median_favourable_movement": round(median_favourable, 8),
        "median_adverse_movement": round(median_adverse, 8),
        "maximum_favourable_excursion": round(max(favourable_values, default=0.0), 8),
        "maximum_adverse_excursion": round(max(adverse_values, default=0.0), 8),
        "outcome_consistency": round(outcome_consistency, 4),
        "current_pattern_similarity": round(float(np.mean(similarities)) if similarities else 0.0, 4),
        "sample_strength": round(sample_strength, 4), "movement_quality": round(movement_quality, 4),
        "confidence": round(confidence, 4), "pattern_confirmation": confirmation,
        "sequence_length": sequence_length, "minimum_sample_required": 5,
        "future_rows_used_for_current_input": 0,
    }


def build_pattern_memory(frame: pd.DataFrame) -> dict[str, Any]:
    results = {name: _pattern_window(frame, rows) for name, rows in WINDOWS.items()}
    valid = [item for item in results.values() if item.get("status") == "VALID"]
    if not valid:
        overall = "NEUTRAL"
        confidence = 0.0
    else:
        weights = np.array([0.20, 0.30, 0.50][-len(valid):], dtype=float)
        weights = weights / weights.sum()
        confidence = float(np.sum([float(item.get("confidence", 0.0)) * weight for item, weight in zip(valid, weights)]))
        statuses = [str(item.get("pattern_confirmation", "NEUTRAL")) for item in valid]
        if "WAIT" in statuses:
            overall = "WAIT"
        elif "PROTECT" in statuses:
            overall = "PROTECT"
        elif statuses.count("CONFIRM") >= 2 or ("CONFIRM" in statuses and confidence >= 0.65):
            overall = "CONFIRM"
        elif any(status in {"CONFIRM", "WEAK CONFIRM"} for status in statuses):
            overall = "WEAK CONFIRM"
        else:
            overall = "NEUTRAL"
    reference = valid[-1] if valid else results.get("higher_25d", {})
    return {
        "version": SUPPORT_VERSION, "windows": results,
        "pattern_confirmation": overall, "pattern_confidence": round(confidence, 4),
        "sample_count": int(reference.get("sample_count", 0) or 0),
        "pattern_support": reference.get("pattern_support", 0.0),
        "pattern_recency": reference.get("pattern_recency", 0.0),
        "1h_directional_success": reference.get("1h_directional_success"),
        "2h_directional_success": reference.get("2h_directional_success"),
        "3h_directional_success": reference.get("3h_directional_success"),
        "6h_directional_success": reference.get("6h_directional_success"),
        "median_favourable_movement": reference.get("median_favourable_movement"),
        "median_adverse_movement": reference.get("median_adverse_movement"),
        "maximum_favourable_excursion": reference.get("maximum_favourable_excursion"),
        "maximum_adverse_excursion": reference.get("maximum_adverse_excursion"),
        "outcome_consistency": reference.get("outcome_consistency"),
        "current_pattern_similarity": reference.get("current_pattern_similarity", 0.0),
        "future_rows_used_for_current_input": 0,
        "causal_policy": "past-only occurrences whose outcomes settled before current sequence",
    }


def _entropy(values: Iterable[Any]) -> float:
    series = pd.Series(list(values)).dropna().astype(str)
    if series.empty:
        return 0.0
    probabilities = series.value_counts(normalize=True).to_numpy(dtype=float)
    return float(-(probabilities * np.log2(np.maximum(probabilities, 1e-12))).sum())


def _structural_strength(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(values) < 36:
        return 0.0
    recent_n = min(12, max(6, len(values) // 8))
    recent = values.tail(recent_n)
    baseline = values.iloc[:-recent_n].tail(120)
    if len(baseline) < 24:
        return 0.0
    sigma = float(baseline.std(ddof=0))
    if sigma <= 1e-12:
        return 0.0
    mean_shift = abs(float(recent.mean() - baseline.mean())) / sigma
    centered = recent.to_numpy(dtype=float) - float(baseline.mean())
    threshold = max(0.5 * sigma, 1e-12)
    positive = negative = peak = 0.0
    for value in centered:
        positive = max(0.0, positive + value - threshold)
        negative = min(0.0, negative + value + threshold)
        peak = max(peak, positive / sigma, abs(negative) / sigma)
    return _clip(0.55 * (mean_shift / 3.0) + 0.45 * (peak / 6.0))


def build_transition_risk(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty or len(frame) < 36:
        return {"value": 0.5, "status": "WATCH", "fallback": "INSUFFICIENT SAMPLE", "version": SUPPORT_VERSION}
    numeric_sources = {
        "master": frame["master"], "entry": frame["entry"], "alpha": frame["alpha"], "delta": frame["delta"],
        "alpha_delta_state": frame["alpha"] * frame["delta"], "pressure_balance": frame["pressure_balance"],
        "reliability": frame["reliability"], "periodicity_normalized_return": frame["return_1h"],
        "periodicity_normalized_range": frame.get("periodicity_normalized_range", pd.Series(0.0, index=frame.index)),
        "periodicity_normalized_residual": frame.get("periodicity_normalized_residual", pd.Series(0.0, index=frame.index)),
    }
    structural_components = {name: _structural_strength(series) for name, series in numeric_sources.items()}
    structural_break = float(np.mean(sorted(structural_components.values(), reverse=True)[:4]))

    categorical = {
        "direction_changes": frame["direction"], "regime_transitions": frame["regime"],
        "alpha_sign": np.sign(frame["alpha"]), "delta_sign": np.sign(frame["delta"]),
        "alpha_delta_disagreement": np.sign(frame["alpha"] * frame["delta"]),
        "pressure_instability": pd.cut(frame["pressure_balance"], [-np.inf, -1, 1, np.inf], labels=["SELL", "BALANCED", "BUY"]),
        "reliability_instability": pd.cut(frame["reliability"], [-np.inf, 45, 65, np.inf], labels=["LOW", "MID", "HIGH"]),
    }
    entropy_components: dict[str, float] = {}
    for name, values in categorical.items():
        series = pd.Series(values).reset_index(drop=True)
        recent = series.tail(24)
        baseline = series.iloc[:-24].tail(120)
        recent_entropy = _entropy(recent)
        baseline_entropy = _entropy(baseline)
        max_entropy = math.log2(max(2, int(series.nunique(dropna=True))))
        increase = max(0.0, recent_entropy - baseline_entropy)
        entropy_components[name] = _clip(increase / max(max_entropy, 1e-12))
    entropy_increase = float(np.mean(sorted(entropy_components.values(), reverse=True)[:4]))

    recent_regime = frame["regime"].tail(24).astype(str)
    base_regime = frame["regime"].iloc[:-24].tail(120).astype(str)
    recent_transitions = float(recent_regime.ne(recent_regime.shift()).mean())
    base_transitions = float(base_regime.ne(base_regime.shift()).mean()) if len(base_regime) else recent_transitions
    current_run = 1
    for value in reversed(frame["regime"].astype(str).tolist()[:-1]):
        if value == str(frame["regime"].iloc[-1]):
            current_run += 1
        else:
            break
    lifecycle = _clip(0.65 * max(0.0, recent_transitions - base_transitions) * 4.0 + 0.35 * (1.0 / max(1.0, current_run / 12.0)))
    value = _clip(0.50 * structural_break + 0.30 * entropy_increase + 0.20 * lifecycle)
    status = "STABLE" if value < 0.40 else "WATCH" if value < 0.60 else "PROTECT" if value < 0.75 else "WAIT"
    return {
        "version": SUPPORT_VERSION, "value": round(value, 4), "status": status,
        "structural_break_strength": round(structural_break, 4), "entropy_increase": round(entropy_increase, 4),
        "regime_lifecycle_risk": round(lifecycle, 4), "current_regime_run_hours": int(current_run),
        "structural_components": {k: round(v, 4) for k, v in structural_components.items()},
        "entropy_components": {k: round(v, 4) for k, v in entropy_components.items()},
        "formula": "50% structural break + 30% entropy increase + 20% regime lifecycle risk",
    }


def _atr(frame: pd.DataFrame, window: int = 14) -> pd.Series:
    previous = frame["close"].shift(1)
    tr = pd.concat([
        (frame["high"] - frame["low"]).abs(), (frame["high"] - previous).abs(), (frame["low"] - previous).abs(),
    ], axis=1).max(axis=1)
    rolling = tr.rolling(window, min_periods=3).median()
    causal_fallback = tr.expanding(min_periods=1).median()
    return rolling.fillna(causal_fallback).ffill().fillna(0.0)


def _triple_barrier_row(data: pd.DataFrame, index: int, horizon: int) -> Optional[dict[str, Any]]:
    end = index + int(horizon)
    if index < 0 or end >= len(data):
        return None
    row = data.iloc[index]
    direction = str(row.get("direction", "WAIT"))
    decision = str(row.get("decision_label", "NO TRADE")).upper()
    if direction not in {"BUY", "SELL"} or decision not in _ALLOWED_DECISIONS:
        return None
    entry = float(row["close"])
    atr_value = max(float(row.get("atr", 0.0) or 0.0), abs(entry) * 0.00025)
    tp_score = _clip(float(row.get("tp", 0.0) or 0.0) / 10.0)
    exit_risk = _clip(float(row.get("exit_risk", 10.0) or 10.0) / 10.0)
    favourable_distance = atr_value * (0.80 + 0.80 * tp_score)
    adverse_distance = atr_value * (0.65 + 0.70 * exit_risk)
    future = data.iloc[index + 1:end + 1]
    favourable_hit = adverse_hit = None
    for offset, candle in enumerate(future.itertuples(index=False), start=1):
        high = float(getattr(candle, "high")); low = float(getattr(candle, "low"))
        if direction == "BUY":
            fav = high >= entry + favourable_distance
            adv = low <= entry - adverse_distance
        else:
            fav = low <= entry - favourable_distance
            adv = high >= entry + adverse_distance
        if favourable_hit is None and fav:
            favourable_hit = offset
        if adverse_hit is None and adv:
            adverse_hit = offset
    outcome = _movement_outcome(data, index, horizon, direction) or {"signed_move": 0.0, "favourable": 0.0, "adverse": 0.0}
    if favourable_hit is not None and (adverse_hit is None or favourable_hit < adverse_hit):
        barrier = "FAVOURABLE"; actionable = 1
    elif adverse_hit is not None and (favourable_hit is None or adverse_hit <= favourable_hit):
        barrier = "ADVERSE"; actionable = 0
    else:
        barrier = "TIME_POSITIVE" if outcome["signed_move"] > 0 else "TIME_NON_POSITIVE"
        actionable = int(outcome["signed_move"] > 0)
    return {
        "time": row["time"], "direction": direction, "regime": str(row.get("regime", "UNKNOWN")),
        "session": str(row.get("session", "UNKNOWN")), "horizon": int(horizon), "barrier": barrier,
        "actionable": actionable, "signed_move": float(outcome["signed_move"]),
        "maximum_favourable_excursion": float(outcome["favourable"]),
        "maximum_adverse_excursion": float(outcome["adverse"]),
        "net_excursion": float(outcome["favourable"] - outcome["adverse"]),
        "favourable_barrier": favourable_distance / max(entry, 1e-12),
        "adverse_barrier": adverse_distance / max(entry, 1e-12),
        "settled_at": data.iloc[end]["time"],
    }


def _summarize_actionability(data: pd.DataFrame, history: pd.DataFrame) -> dict[str, Any]:
    if data.empty:
        return {"current_label": "WAIT", "status": "INSUFFICIENT EVIDENCE", "history": []}
    current = data.iloc[-1]
    direction = str(current.get("direction", "WAIT"))
    current_group = history[
        (history.get("direction", pd.Series(dtype=str)) == direction)
        & (history.get("regime", pd.Series(dtype=str)).astype(str) == str(current.get("regime", "UNKNOWN")))
    ] if not history.empty else pd.DataFrame()
    scope = "REGIME_DIRECTION"
    if len(current_group) < 12 and not history.empty:
        current_group = history[history["direction"] == direction]
        scope = "DIRECTION"
    if len(current_group) < 12:
        current_group = history
        scope = "EURUSD_H1_GLOBAL"
    primary_group = current_group[pd.to_numeric(current_group.get("horizon"), errors="coerce").isin([2, 3])] if not current_group.empty else current_group
    if primary_group.empty:
        primary_group = current_group
    sample_count = int(pd.to_datetime(primary_group.get("time"), utc=True, errors="coerce").nunique()) if not primary_group.empty else 0
    actionable_rate = float(primary_group["actionable"].mean()) if sample_count else 0.0
    expected_value = float(primary_group["net_excursion"].median()) if sample_count else None
    if direction not in {"BUY", "SELL"}:
        label = "WAIT"
    elif sample_count < 12:
        label = "WATCH"
    elif actionable_rate >= 0.62 and (expected_value or 0.0) > 0:
        label = "QUALIFIED ENTRY"
    elif actionable_rate >= 0.52 and (expected_value or 0.0) >= 0:
        label = "CONDITIONAL ENTRY"
    elif actionable_rate < 0.40:
        label = "PROTECT"
    else:
        label = "WATCH"
    ordered = history.sort_values(["time", "horizon"], ascending=[False, True], kind="stable") if not history.empty else history
    return {
        "version": SUPPORT_VERSION, "current_label": label, "status": "VALID" if sample_count >= 12 else "INSUFFICIENT EVIDENCE",
        "sample_count": sample_count, "scope": scope, "actionable_probability": round(actionable_rate, 4),
        "expected_value": None if expected_value is None else round(expected_value, 8),
        "primary_time_barriers": [2, 3], "evaluation_horizons": [1, 2, 3, 6],
        "history": _records(ordered, 2400),
    }


def build_triple_barrier_actionability(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"current_label": "WAIT", "status": "INSUFFICIENT EVIDENCE", "history": []}
    data = frame.copy()
    data["atr"] = _atr(data)
    rows = [
        item
        for index in range(len(data))
        for horizon in HORIZONS
        for item in [_triple_barrier_row(data, index, horizon)]
        if item is not None
    ]
    return _summarize_actionability(data, pd.DataFrame(rows))


def _incremental_triple_barrier_actionability(
    frame: pd.DataFrame, previous: Mapping[str, Any], previous_latest: pd.Timestamp
) -> dict[str, Any]:
    data = frame.copy()
    data["atr"] = _atr(data)
    history = pd.DataFrame(list(previous.get("history") or []))
    if not history.empty:
        history["time"] = pd.to_datetime(history["time"], utc=True, errors="coerce")
        history["settled_at"] = pd.to_datetime(history["settled_at"], utc=True, errors="coerce")
        history = history.dropna(subset=["time", "settled_at"])
    new_rows: list[dict[str, Any]] = []
    for end_index, settled_time in enumerate(pd.to_datetime(data["time"], utc=True, errors="coerce")):
        if pd.isna(settled_time) or settled_time <= previous_latest:
            continue
        for horizon in HORIZONS:
            item = _triple_barrier_row(data, end_index - horizon, horizon)
            if item is not None:
                new_rows.append(item)
    if new_rows:
        history = pd.concat([history, pd.DataFrame(new_rows)], ignore_index=True)
    if not history.empty:
        earliest = pd.to_datetime(data["time"].iloc[0], utc=True, errors="coerce")
        latest = pd.to_datetime(data["time"].iloc[-1], utc=True, errors="coerce")
        history["time"] = pd.to_datetime(history["time"], utc=True, errors="coerce")
        history["settled_at"] = pd.to_datetime(history["settled_at"], utc=True, errors="coerce")
        history = history[history["time"].ge(earliest) & history["settled_at"].le(latest)]
        history = history.drop_duplicates(["time", "horizon"], keep="last")
    result = _summarize_actionability(data, history)
    result["incremental_settlements_added"] = int(len(new_rows))
    return result

def _fracdiff_weights(d: float, threshold: float = 1e-4, max_size: int = 200) -> np.ndarray:
    weights = [1.0]
    for k in range(1, max_size):
        value = -weights[-1] * (d - k + 1) / k
        if abs(value) < threshold:
            break
        weights.append(value)
    return np.asarray(weights[::-1], dtype=float)


def _fractional_difference(series: pd.Series, d: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    weights = _fracdiff_weights(d)
    width = len(weights)
    result = pd.Series(np.nan, index=values.index, dtype=float)
    array = values.to_numpy(dtype=float)
    for index in range(width - 1, len(array)):
        window = array[index - width + 1:index + 1]
        if np.isfinite(window).all():
            result.iloc[index] = float(np.dot(weights, window))
    return result


def _adf_pvalue(series: pd.Series) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 40:
        return None
    try:
        from statsmodels.tsa.stattools import adfuller
        return float(adfuller(values.to_numpy(dtype=float), maxlag=1, regression="c", autolag=None)[1])
    except Exception:
        # Deterministic proxy when statsmodels is unavailable: high lag-1
        # autocorrelation is treated as non-stationary.
        correlation = values.autocorr(lag=1)
        if pd.isna(correlation):
            return None
        return float(max(0.0, min(1.0, (abs(float(correlation)) - 0.65) / 0.35)))


def build_fractional_support(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty or len(frame) < 80:
        return {"enabled": False, "weight": 0.0, "reason": "INSUFFICIENT SAMPLE", "version": SUPPORT_VERSION}
    log_close = np.log(pd.to_numeric(frame["close"], errors="coerce").replace(0, np.nan))
    split = max(50, int(len(log_close) * 0.8))
    candidates = []
    for d in (0.2, 0.4, 0.6, 0.8, 1.0):
        transformed = _fractional_difference(log_close, d)
        train = transformed.iloc[:split]
        test = transformed.iloc[split:]
        aligned = pd.concat([log_close, transformed], axis=1).dropna()
        memory = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1])) if len(aligned) >= 20 else 0.0
        pvalue = _adf_pvalue(train)
        train_std = float(train.dropna().std(ddof=0)) if train.notna().sum() >= 10 else np.nan
        test_std = float(test.dropna().std(ddof=0)) if test.notna().sum() >= 5 else np.nan
        stability = 1.0 - min(1.0, abs(test_std - train_std) / max(abs(train_std), 1e-12)) if math.isfinite(train_std) and math.isfinite(test_std) else 0.0
        valid = pvalue is not None and pvalue <= 0.10 and memory >= 0.55 and stability >= 0.35
        score = (1.0 - min(1.0, pvalue or 1.0)) * 0.45 + max(0.0, memory) * 0.35 + stability * 0.20
        candidates.append({"d": d, "adf_pvalue": pvalue, "memory_correlation": memory, "oos_stability": stability, "valid": valid, "score": score})
    valid = [item for item in candidates if item["valid"]]
    selected = sorted(valid, key=lambda item: (item["d"], -item["score"]))[0] if valid else None
    return {
        "version": SUPPORT_VERSION, "enabled": bool(selected), "weight": 0.15 if selected else 0.0,
        "selected_d": selected["d"] if selected else None,
        "reason": "OOS_VALIDATED_SUPPORT" if selected else "VALIDATION_FAILED_WEIGHT_ZERO",
        "candidates": [
            {k: (round(v, 6) if isinstance(v, float) else v) for k, v in item.items()}
            for item in candidates
        ],
    }


def build_duplicate_evidence_control(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"status": "INSUFFICIENT SAMPLE", "duplicate_penalty": 0.0, "families": {}}
    family_columns = {
        "regime_alpha_delta": ["alpha", "delta"],
        "price_pressure": ["return_1h", "pressure_balance"],
        "reliability_protection": ["reliability", "exit_risk"],
        "full_metric_scores": ["master", "entry", "hold", "tp"],
    }
    families: dict[str, Any] = {}
    duplicate_pairs = 0
    total_pairs = 0
    for family, columns in family_columns.items():
        available = [column for column in columns if column in frame]
        correlations = frame[available].apply(pd.to_numeric, errors="coerce").corr().abs() if len(available) >= 2 else pd.DataFrame()
        pairs = []
        for i, left in enumerate(available):
            for right in available[i + 1:]:
                value = _finite(correlations.loc[left, right], 0.0) if not correlations.empty else 0.0
                total_pairs += 1
                duplicate = bool(value is not None and value >= 0.85)
                duplicate_pairs += int(duplicate)
                pairs.append({"left": left, "right": right, "abs_correlation": round(float(value or 0.0), 4), "duplicate": duplicate})
        stability_values = []
        for column in available:
            series = pd.to_numeric(frame[column], errors="coerce").dropna()
            if len(series) >= 30:
                midpoint = len(series) // 2
                left_std = float(series.iloc[:midpoint].std(ddof=0)); right_std = float(series.iloc[midpoint:].std(ddof=0))
                stability_values.append(1.0 - min(1.0, abs(right_std - left_std) / max(abs(left_std), 1e-12)))
        stability = float(np.mean(stability_values)) if stability_values else 0.5
        cap = {"regime_alpha_delta": 0.22, "price_pressure": 0.18, "reliability_protection": 0.25, "full_metric_scores": 0.0}.get(family, 0.15)
        # Full Metric authority is reported but remains outside the supporting
        # evidence competition and therefore has a zero supporting cap.
        families[family] = {"cap": cap, "stability": round(stability, 4), "correlated_pairs": pairs}
    penalty = duplicate_pairs / max(1, total_pairs)
    return {
        "version": SUPPORT_VERSION, "status": "ACTIVE", "duplicate_penalty": round(penalty, 4),
        "duplicate_pairs": int(duplicate_pairs), "evaluated_pairs": int(total_pairs), "families": families,
        "full_metric_authority_excluded_from_competition": True,
    }


def _distribution_stats(values: pd.Series) -> dict[str, Any]:
    series = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if series.empty:
        return {"sample_count": 0}
    return {
        "sample_count": int(len(series)), "mean": float(series.mean()), "median": float(series.median()),
        "standard_deviation": float(series.std(ddof=0)), "p10": float(series.quantile(0.10)),
        "p25": float(series.quantile(0.25)), "p75": float(series.quantile(0.75)), "p90": float(series.quantile(0.90)),
        "skewness": float(series.skew()) if len(series) >= 3 else 0.0,
        "tail_loss_frequency": float((series < series.quantile(0.10)).mean()),
    }


def build_regime_conditioned_distributions(frame: pd.DataFrame, actionability: Mapping[str, Any], transition: Mapping[str, Any]) -> dict[str, Any]:
    history = pd.DataFrame(list(actionability.get("history") or []))
    if history.empty:
        return {"status": "INSUFFICIENT SAMPLE", "horizons": {}, "version": SUPPORT_VERSION}
    current = frame.iloc[-1]
    direction = str(current.get("direction", "WAIT")); regime = str(current.get("regime", "UNKNOWN")); session = str(current.get("session", "UNKNOWN"))
    transition_state = str(transition.get("status", "WATCH"))
    results: dict[str, Any] = {}
    for horizon in HORIZONS:
        base = history[pd.to_numeric(history.get("horizon"), errors="coerce") == horizon]
        scopes = [
            (base[(base["direction"] == direction) & (base["regime"] == regime) & (base["session"] == session)], "REGIME_SESSION_DIRECTION"),
            (base[(base["direction"] == direction) & (base["regime"] == regime)], "REGIME_DIRECTION"),
            (base[(base["direction"] == direction) & (base["session"] == session)], "SESSION_DIRECTION"),
            (base[base["direction"] == direction], "DIRECTION"), (base, "EURUSD_H1_GLOBAL"),
        ]
        selected = pd.DataFrame(); scope = "NONE"
        for candidate, label in scopes:
            if len(candidate) >= 12:
                selected = candidate; scope = label; break
        if selected.empty:
            selected = base; scope = "SMALL_SAMPLE_GLOBAL"
        stats = _distribution_stats(selected.get("signed_move", pd.Series(dtype=float)))
        stats.update({
            "scope": scope, "transition_state": transition_state,
            "maximum_favourable_excursion": _finite(pd.to_numeric(selected.get("maximum_favourable_excursion"), errors="coerce").max(), None),
            "maximum_adverse_excursion": _finite(pd.to_numeric(selected.get("maximum_adverse_excursion"), errors="coerce").max(), None),
            "median_favourable_excursion": _finite(pd.to_numeric(selected.get("maximum_favourable_excursion"), errors="coerce").median(), None),
            "median_adverse_excursion": _finite(pd.to_numeric(selected.get("maximum_adverse_excursion"), errors="coerce").median(), None),
            "shrinkage_applied": scope not in {"REGIME_SESSION_DIRECTION", "REGIME_DIRECTION"},
        })
        results[f"{horizon}h"] = {key: (round(value, 8) if isinstance(value, float) else value) for key, value in stats.items()}
    overall_status = "VALID" if str(actionability.get("status", "")).upper() == "VALID" else "INSUFFICIENT SAMPLE"
    return {"version": SUPPORT_VERSION, "status": overall_status, "horizons": results}


def _source_signature(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "empty"
    columns = [column for column in (
        "time", "open", "high", "low", "close", "direction", "decision_label",
        "master", "entry", "hold", "tp", "exit_risk", "buy_pressure", "sell_pressure",
    ) if column in frame.columns]
    payload = frame.tail(8)[columns].to_json(date_format="iso", orient="records", double_precision=12)
    return sha256(payload.encode("utf-8", errors="ignore")).hexdigest()[:24]


def _restore_evidence_frame(records: Any) -> pd.DataFrame:
    frame = pd.DataFrame(list(records or []))
    if frame.empty:
        return frame
    frame["time"] = pd.to_datetime(frame.get("time"), utc=True, errors="coerce")
    numeric = (
        "open", "high", "low", "close", "volume", "master", "entry", "hold", "tp", "exit_risk",
        "buy_pressure", "sell_pressure", "reliability", "alpha", "delta", "expected_value_existing",
        "pressure_balance", "return_1h",
    )
    for column in numeric:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["time"]).sort_values("time", kind="stable").drop_duplicates("time", keep="last").tail(600).reset_index(drop=True)


def _cache_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in frame.tail(600).to_dict("records")
    ]


def _sequence_key(sequence: Sequence[str]) -> str:
    return sha256("".join(sequence).encode("utf-8", errors="ignore")).hexdigest()[:20]


def _fresh_incremental_state(frame: pd.DataFrame) -> dict[str, Any]:
    numeric_columns = ("close", "return_1h", "master", "entry", "alpha", "delta", "pressure_balance", "reliability")
    moments: dict[str, Any] = {}
    for column in numeric_columns:
        values = pd.to_numeric(frame.get(column), errors="coerce").dropna()
        count = int(len(values)); total = float(values.sum()) if count else 0.0; sum_sq = float(np.square(values).sum()) if count else 0.0
        mean = total / count if count else None
        variance = max(0.0, sum_sq / count - mean * mean) if count and mean is not None else None
        moments[column] = {"count": count, "sum": total, "sum_sq": sum_sq, "mean": mean, "std": math.sqrt(variance) if variance is not None else None}
    pair_names = (("alpha", "delta"), ("master", "entry"), ("return_1h", "reliability"), ("buy_pressure", "sell_pressure"))
    pairs: dict[str, Any] = {}
    for left, right in pair_names:
        values = pd.DataFrame({"x": pd.to_numeric(frame.get(left), errors="coerce"), "y": pd.to_numeric(frame.get(right), errors="coerce")}).dropna()
        key = f"{left}__{right}"
        if values.empty:
            pairs[key] = {"count": 0, "sum_x": 0.0, "sum_y": 0.0, "sum_x2": 0.0, "sum_y2": 0.0, "sum_xy": 0.0, "correlation": None}
            continue
        x = values["x"].to_numpy(dtype=float); y = values["y"].to_numpy(dtype=float); count = len(values)
        sum_x=float(x.sum()); sum_y=float(y.sum()); sum_x2=float(np.square(x).sum()); sum_y2=float(np.square(y).sum()); sum_xy=float((x*y).sum())
        denominator = math.sqrt(max(count*sum_x2-sum_x*sum_x,0.0)*max(count*sum_y2-sum_y*sum_y,0.0))
        corr = (count*sum_xy-sum_x*sum_y)/denominator if denominator>1e-18 else None
        pairs[key] = {"count": count, "sum_x": sum_x, "sum_y": sum_y, "sum_x2": sum_x2, "sum_y2": sum_y2, "sum_xy": sum_xy, "correlation": corr}
    tokens = _state_tokens(frame).tolist() if not frame.empty else []
    sequence_counts: dict[str, dict[str, int]] = {}
    for length in (2, 3, 4):
        counts = Counter(_sequence_key(tokens[index-length+1:index+1]) for index in range(length-1, len(tokens)))
        sequence_counts[str(length)] = dict(counts)
    return {
        "rolling_moments": moments, "rolling_correlations": pairs, "state_tokens": tokens,
        "pattern_sequence_counts": sequence_counts, "updated_incrementally": False,
    }


def _update_incremental_state(
    previous_state: Mapping[str, Any], previous_frame: pd.DataFrame, new_rows: pd.DataFrame, combined: pd.DataFrame
) -> dict[str, Any]:
    if not previous_state or previous_frame.empty or new_rows.empty:
        return _fresh_incremental_state(combined)
    state = {
        "rolling_moments": {key: dict(value) for key, value in dict(previous_state.get("rolling_moments") or {}).items()},
        "rolling_correlations": {key: dict(value) for key, value in dict(previous_state.get("rolling_correlations") or {}).items()},
        "state_tokens": list(previous_state.get("state_tokens") or []),
        "pattern_sequence_counts": {key: dict(value) for key, value in dict(previous_state.get("pattern_sequence_counts") or {}).items()},
        "updated_incrementally": True,
    }
    combined_times = set(pd.to_datetime(combined["time"], utc=True, errors="coerce").dropna())
    expired = previous_frame[~pd.to_datetime(previous_frame["time"], utc=True, errors="coerce").isin(combined_times)]
    numeric_columns = tuple(state["rolling_moments"].keys())
    for column in numeric_columns:
        entry = state["rolling_moments"].setdefault(column, {"count": 0, "sum": 0.0, "sum_sq": 0.0})
        for values, sign in ((pd.to_numeric(expired.get(column), errors="coerce").dropna(), -1.0), (pd.to_numeric(new_rows.get(column), errors="coerce").dropna(), 1.0)):
            entry["count"] = int(entry.get("count", 0) + sign * len(values))
            entry["sum"] = float(entry.get("sum", 0.0) + sign * float(values.sum()))
            entry["sum_sq"] = float(entry.get("sum_sq", 0.0) + sign * float(np.square(values).sum()))
        count=max(0,int(entry["count"])); entry["count"]=count
        mean=entry["sum"]/count if count else None
        variance=max(0.0,entry["sum_sq"]/count-mean*mean) if count and mean is not None else None
        entry["mean"]=mean; entry["std"]=math.sqrt(variance) if variance is not None else None
    for pair_key, entry in state["rolling_correlations"].items():
        left, right = pair_key.split("__", 1)
        for rows, sign in ((expired, -1.0), (new_rows, 1.0)):
            values=pd.DataFrame({"x":pd.to_numeric(rows.get(left),errors="coerce"),"y":pd.to_numeric(rows.get(right),errors="coerce")}).dropna()
            if values.empty: continue
            x=values["x"].to_numpy(dtype=float); y=values["y"].to_numpy(dtype=float)
            entry["count"]=int(entry.get("count",0)+sign*len(values)); entry["sum_x"]=float(entry.get("sum_x",0)+sign*x.sum()); entry["sum_y"]=float(entry.get("sum_y",0)+sign*y.sum()); entry["sum_x2"]=float(entry.get("sum_x2",0)+sign*np.square(x).sum()); entry["sum_y2"]=float(entry.get("sum_y2",0)+sign*np.square(y).sum()); entry["sum_xy"]=float(entry.get("sum_xy",0)+sign*(x*y).sum())
        count=max(0,int(entry.get("count",0))); entry["count"]=count
        denominator=math.sqrt(max(count*entry.get("sum_x2",0)-entry.get("sum_x",0)**2,0.0)*max(count*entry.get("sum_y2",0)-entry.get("sum_y",0)**2,0.0))
        entry["correlation"]=(count*entry.get("sum_xy",0)-entry.get("sum_x",0)*entry.get("sum_y",0))/denominator if denominator>1e-18 else None
    tokens=state["state_tokens"]
    counts_by_length={length:Counter(state["pattern_sequence_counts"].get(str(length),{})) for length in (2,3,4)}
    for token in _state_tokens(new_rows).tolist():
        if len(tokens) >= 600:
            for length in (2,3,4):
                if len(tokens) >= length:
                    key=_sequence_key(tokens[:length]); counts_by_length[length][key]-=1
                    if counts_by_length[length][key] <= 0: del counts_by_length[length][key]
            tokens.pop(0)
        tokens.append(token)
        for length in (2,3,4):
            if len(tokens) >= length:
                counts_by_length[length][_sequence_key(tokens[-length:])] += 1
    expected_tokens=_state_tokens(combined).tolist()
    if tokens != expected_tokens:
        return _fresh_incremental_state(combined)
    state["state_tokens"]=tokens; state["pattern_sequence_counts"]={str(length):dict(counts_by_length[length]) for length in (2,3,4)}
    return state


def public_support_view(support: Mapping[str, Any]) -> dict[str, Any]:
    """Compact canonical/UI view; heavy rolling caches stay in session state only."""
    result = {key: value for key, value in dict(support or {}).items() if key != "_incremental_cache"}
    actionability = dict(result.get("actionability") or {})
    history = list(actionability.pop("history", []) or [])
    actionability["settled_history_count"] = len(history)
    actionability["settled_history_preview"] = history[:24]
    result["actionability"] = actionability
    return result


def build_causal_support_bundle(
    ohlc: Any,
    priority_table: Any,
    *,
    context: Optional[Mapping[str, Any]] = None,
    previous_cache: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    prepared = _prepare_evidence_frame(ohlc, priority_table, context=context)
    signature = _source_signature(prepared)
    latest = prepared["time"].iloc[-1].isoformat() if not prepared.empty else None
    previous = dict(previous_cache or {})
    if previous.get("source_signature") == signature and previous.get("latest_completed_h1_time") == latest:
        cached = dict(previous); cached["cache_status"] = "CACHE_HIT"; return cached
    previous_latest = pd.to_datetime(previous.get("latest_completed_h1_time"), utc=True, errors="coerce")
    current_latest = pd.to_datetime(latest, utc=True, errors="coerce")
    previous_internal = dict(previous.get("_incremental_cache") or {})
    previous_frame = _restore_evidence_frame(previous_internal.get("evidence_records"))
    incremental = False; frame = prepared; new_rows = pd.DataFrame()
    if not prepared.empty and not previous_frame.empty and pd.notna(previous_latest) and pd.notna(current_latest) and current_latest > previous_latest:
        prefix = prepared[pd.to_datetime(prepared["time"], utc=True, errors="coerce").le(previous_latest)]
        new_rows = prepared[pd.to_datetime(prepared["time"], utc=True, errors="coerce").gt(previous_latest)]
        contiguous = not new_rows.empty and bool(pd.to_datetime(new_rows["time"], utc=True).diff().dropna().eq(pd.Timedelta(hours=1)).all())
        prefix_unchanged = _source_signature(prefix) == str(previous.get("source_signature"))
        if contiguous and prefix_unchanged:
            frame = pd.concat([previous_frame, new_rows], ignore_index=True).sort_values("time", kind="stable").drop_duplicates("time", keep="last").tail(600).reset_index(drop=True)
            signature = _source_signature(frame); latest = frame["time"].iloc[-1].isoformat(); incremental = True
    pattern = build_pattern_memory(frame)
    transition = build_transition_risk(frame)
    if incremental:
        actionability = _incremental_triple_barrier_actionability(frame, previous.get("actionability") or {}, previous_latest)
        incremental_state = _update_incremental_state(previous_internal.get("incremental_state") or {}, previous_frame, new_rows, frame)
    else:
        actionability = build_triple_barrier_actionability(frame)
        incremental_state = _fresh_incremental_state(frame)
    fractional = build_fractional_support(frame)
    duplicates = build_duplicate_evidence_control(frame)
    distributions = build_regime_conditioned_distributions(frame, actionability, transition)
    current = frame.iloc[-1].to_dict() if not frame.empty else {}
    bundle = {
        "version": SUPPORT_VERSION, "source_signature": signature, "latest_completed_h1_time": latest,
        "cache_status": "INCREMENTAL_APPEND" if incremental else "FULL_REBUILD",
        "retained_rows": int(len(frame)), "rolling_window_limit": 600,
        "pattern_memory": pattern, "transition_risk": transition, "actionability": actionability,
        "fractional_differentiation": fractional, "duplicate_evidence_control": duplicates,
        "regime_conditioned_distributions": distributions,
        "current_state": {
            "time": _json_value(current.get("time")), "direction": current.get("direction", "WAIT"),
            "regime": current.get("regime", "UNKNOWN"), "master_score": _finite(current.get("master"), None),
            "entry_score": _finite(current.get("entry"), None), "hold_score": _finite(current.get("hold"), None),
            "tp_score": _finite(current.get("tp"), None), "exit_risk": _finite(current.get("exit_risk"), None),
            "alpha": _finite(current.get("alpha"), None), "delta": _finite(current.get("delta"), None),
            "buy_pressure": _finite(current.get("buy_pressure"), None), "sell_pressure": _finite(current.get("sell_pressure"), None),
            "session": current.get("session", "UNKNOWN"),
            "periodicity_normalized_return": _finite(current.get("periodicity_normalized_return"), None),
            "periodicity_normalized_range": _finite(current.get("periodicity_normalized_range"), None),
            "periodicity_normalized_residual": _finite(current.get("periodicity_normalized_residual"), None),
        },
        "data_quality": {"future_rows_used_as_current_input": 0, "rows_sorted": True, "duplicates_removed": True, "prefix_signature_validated": bool(incremental)},
        "incremental_components": ["evidence append", "rolling moments", "rolling correlations", "pattern sequence counts", "settled triple-barrier outcomes"] if incremental else [],
        "_incremental_cache": {"evidence_records": _cache_records(frame), "incremental_state": incremental_state},
    }
    return bundle

def _candidate_status(label: str, qualified: str, is_current: bool) -> str:
    label = str(label or "WATCH").upper()
    qualified = str(qualified or "").upper()
    if not is_current and label in {"QUALIFIED ENTRY", "CONDITIONAL ENTRY", "WATCH", "PROTECT"}:
        return "EXPIRED"
    if label == "QUALIFIED ENTRY" and qualified == "QUALIFIED ENTRY":
        return "ENTRY"
    if label == "CONDITIONAL ENTRY":
        return "CONDITIONAL"
    if label == "PROTECT":
        return "BLOCKED"
    if label in {"WAIT", "EXPIRED"}:
        return label
    return "WATCH"


def apply_support_to_authority(authority: Mapping[str, Any], support: Mapping[str, Any]) -> Dict[str, Any]:
    """Enrich canonical candidates without changing Full Metric direction/formulas."""
    result = dict(authority or {})
    table = result.get("priority_table")
    if not isinstance(table, pd.DataFrame) or table.empty:
        return result
    out = table.copy(deep=False)
    current_time = pd.to_datetime(support.get("latest_completed_h1_time"), utc=True, errors="coerce")
    times = pd.to_datetime(out.get("Time"), utc=True, errors="coerce")
    current_mask = times.eq(current_time) if pd.notna(current_time) else pd.Series(False, index=out.index)
    current_state = dict(support.get("current_state") or {})
    pattern = dict(support.get("pattern_memory") or {})
    transition = dict(support.get("transition_risk") or {})
    actionability = dict(support.get("actionability") or {})
    distributions = dict(support.get("regime_conditioned_distributions") or {})
    out["Alpha"] = _score_series(out, ("Alpha", "alpha"), np.nan)
    out["Delta"] = _score_series(out, ("Delta", "delta"), np.nan)
    out.loc[current_mask, "Alpha"] = current_state.get("alpha")
    out.loc[current_mask, "Delta"] = current_state.get("delta")
    out["Pattern Confirmation"] = "HISTORICAL / SETTLED"
    out["Pattern Confidence"] = np.nan
    out["Transition Risk"] = np.nan
    out["Transition Status"] = "HISTORICAL"
    out["Actionability Label"] = "EXPIRED"
    out["Actionability Probability"] = np.nan
    out["Validity Horizon"] = "2–3 completed H1 candles"
    out.loc[current_mask, "Pattern Confirmation"] = pattern.get("pattern_confirmation", "NEUTRAL")
    out.loc[current_mask, "Pattern Confidence"] = pattern.get("pattern_confidence")
    out.loc[current_mask, "Transition Risk"] = transition.get("value")
    out.loc[current_mask, "Transition Status"] = transition.get("status", "WATCH")
    out.loc[current_mask, "Actionability Label"] = actionability.get("current_label", "WATCH")
    out.loc[current_mask, "Actionability Probability"] = actionability.get("actionable_probability")
    if actionability.get("expected_value") is not None:
        out.loc[current_mask, "Expected Value"] = actionability.get("expected_value")
    out["Reliability"] = pd.to_numeric(out.get("Reliability %"), errors="coerce")
    out["Current Status"] = [
        _candidate_status(label, qualified, bool(is_current))
        for label, qualified, is_current in zip(out["Actionability Label"], out.get("Qualification Status", ""), current_mask)
    ]
    out["Final Candidate Decision"] = out["Current Status"]
    out["Reason Accepted or Blocked"] = out.get("Blocking Reason", "")
    if current_mask.any():
        blockers = []
        if transition.get("status") in {"PROTECT", "WAIT"}:
            blockers.append(f"Transition Risk {transition.get('status')} ({transition.get('value')})")
        if pattern.get("pattern_confirmation") in {"PROTECT", "WAIT"}:
            blockers.append(f"Pattern memory {pattern.get('pattern_confirmation')}")
        if actionability.get("current_label") not in {"QUALIFIED ENTRY", "CONDITIONAL ENTRY"}:
            blockers.append(f"Actionability {actionability.get('current_label', 'WATCH')}")
        if blockers:
            existing = out.loc[current_mask, "Reason Accepted or Blocked"].astype(str)
            out.loc[current_mask, "Reason Accepted or Blocked"] = existing + "; " + "; ".join(blockers)
    # Required aliases for all existing routes and AI grounding.
    out["Candidate Timestamp"] = out.get("Time")
    out["Master Score"] = out.get("Master /10")
    out["Entry Score"] = out.get("Entry /10")
    out["Hold Score"] = out.get("Hold /10")
    out["TP Score"] = out.get("TP /10")
    out["Exit Risk"] = out.get("Exit Risk /10")
    out["Regime"] = _text_series(out, ("Regime", "Current Regime", "Major Regime"), current_state.get("regime", "UNKNOWN"))
    out["Expected Value"] = pd.to_numeric(out.get("Expected Value"), errors="coerce")
    # Attach selected empirical 2H/3H uncertainty context without replacing
    # existing visible columns.
    dist_horizons = dict(distributions.get("horizons") or {})
    out["2H Outcome Sample"] = (dist_horizons.get("2h") or {}).get("sample_count")
    out["3H Outcome Sample"] = (dist_horizons.get("3h") or {}).get("sample_count")
    result["priority_table"] = out
    result["top_two_daily_candidates"] = _select_two_candidates(out)
    snapshot = dict(result.get("snapshot") or {})
    snapshot["canonical_priority_table"] = _records(out.drop(columns=["_canonical_time"], errors="ignore"), 600)
    snapshot["top_two_daily_candidates"] = result["top_two_daily_candidates"]
    snapshot["research_confirmation"] = public_support_view(support)
    result["snapshot"] = snapshot
    return result


def _select_two_candidates(priority: pd.DataFrame) -> list[dict[str, Any]]:
    # Import lazily to reuse the existing protected-authority selection policy.
    from core.full_metric_canonical_adapter_20260618 import _top_two_daily_candidates
    return _top_two_daily_candidates(priority)


def apply_support_to_canonical(payload: Mapping[str, Any], support: Mapping[str, Any]) -> Dict[str, Any]:
    """Attach supporting evidence and apply only confirmation/WAIT gates."""
    result = dict(payload or {})
    final = dict(result.get("final_decision") or {})
    direction = _direction(final.get("directional_market_view") or result.get("full_metric_direction"))
    tradeability = _direction(final.get("tradeability_decision") or final.get("final_decision"))
    pattern = dict(support.get("pattern_memory") or {})
    transition = dict(support.get("transition_risk") or {})
    actionability = dict(support.get("actionability") or {})
    blockers = list(final.get("blocking_reasons") or [])
    supporting = list(final.get("supporting_reasons") or [])
    pattern_status = str(pattern.get("pattern_confirmation", "NEUTRAL"))
    transition_status = str(transition.get("status", "WATCH"))
    action_label = str(actionability.get("current_label", "WATCH"))
    supporting.extend([
        f"Pattern memory {pattern_status} ({float(pattern.get('pattern_confidence', 0) or 0):.0%})",
        f"Transition Risk {transition_status} ({float(transition.get('value', 0) or 0):.2f})",
        f"Meta-label actionability {action_label}",
    ])
    if transition_status in {"PROTECT", "WAIT"}:
        blockers.append(f"Transition Risk gate is {transition_status}")
    if pattern_status in {"PROTECT", "WAIT"}:
        blockers.append(f"Causal pattern memory is {pattern_status}")
    if action_label not in {"QUALIFIED ENTRY", "CONDITIONAL ENTRY"}:
        blockers.append(f"Triple-barrier actionability is {action_label}")
    if direction not in {"BUY", "SELL"}:
        tradeability = "WAIT"
    elif blockers:
        tradeability = "WAIT"
    # Never create or reverse direction; only retain direction or force WAIT.
    final["directional_market_view"] = direction
    final["tradeability_decision"] = direction if tradeability == direction and not blockers else "WAIT"
    final["final_decision"] = final["tradeability_decision"]
    final["less_risky_decision"] = final["tradeability_decision"]
    final["blocking_reasons"] = list(dict.fromkeys(str(item) for item in blockers if item))
    final["supporting_reasons"] = list(dict.fromkeys(str(item) for item in supporting if item))
    final["actionability_status"] = action_label
    final["pattern_confirmation"] = pattern_status
    final["transition_risk"] = transition.get("value")
    if actionability.get("expected_value") is not None and final.get("expected_value") is None:
        final["expected_value"] = actionability.get("expected_value")
    duplicate_control = dict(support.get("duplicate_evidence_control") or {})
    duplicate_penalty = _clip(duplicate_control.get("duplicate_penalty", 0.0))
    uncertainty = _finite(final.get("uncertainty_pct"), 100.0) or 100.0
    uncertainty += 18.0 * float(transition.get("value", 0.0) or 0.0)
    uncertainty += 10.0 * duplicate_penalty
    if pattern_status in {"PROTECT", "WAIT"}:
        uncertainty += 8.0
    final["uncertainty_pct"] = round(min(100.0, uncertainty), 2)
    final["duplicate_evidence_penalty"] = round(duplicate_penalty, 4)
    confidence = _finite(final.get("calibrated_confidence"), None)
    if confidence is not None:
        scale = 0.01 if confidence > 1 else 1.0
        normalized = confidence * scale
        adjusted = normalized * (1.0 - 0.15 * duplicate_penalty)
        final["calibrated_confidence"] = round(adjusted / scale, 6)
    result["final_decision"] = final
    result["pattern_memory"] = pattern
    result["pattern_confirmation"] = pattern_status
    result["transition_risk"] = transition
    compact_support = public_support_view(support)
    result["actionability"] = compact_support.get("actionability", {})
    result["actionability_status"] = action_label
    result["fractional_differentiation"] = support.get("fractional_differentiation") or {}
    result["duplicate_evidence_control"] = support.get("duplicate_evidence_control") or {}
    result["regime_conditioned_distributions"] = support.get("regime_conditioned_distributions") or {}
    result["research_support"] = compact_support
    result["cache_status"] = support.get("cache_status")
    metadata = dict(result.get("metadata") or {})
    metadata.update({
        "causal_support_version": SUPPORT_VERSION,
        "pattern_future_rows_used_as_current_input": 0,
        "supporting_evidence_can_only_confirm_or_force_wait": True,
        "rolling_support_rows": support.get("retained_rows", 0),
        "support_cache_status": support.get("cache_status"),
    })
    result["metadata"] = metadata
    return result


__all__ = [
    "SUPPORT_VERSION", "build_causal_support_bundle", "build_pattern_memory", "build_transition_risk",
    "build_triple_barrier_actionability", "build_fractional_support", "build_duplicate_evidence_control",
    "build_regime_conditioned_distributions", "public_support_view", "apply_support_to_authority", "apply_support_to_canonical",
]
