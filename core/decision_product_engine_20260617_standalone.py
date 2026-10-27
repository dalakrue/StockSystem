"""End-to-end reliability layer for the existing ADX Quant Pro engines.

This module adds no standalone price-prediction model.  It adapts existing
PowerBI/regime/priority/NLP outputs, validates their input data, records every
run, calibrates only from settled out-of-sample ledger rows, reconciles 1/2/3/6
hour horizons, and applies one auditable tradeability policy.
"""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from core.decision_contract_20260617 import (
    CALCULATION_VERSION, MODEL_VERSION, SCHEMA_VERSION, DataQualityResult,
    DecisionResult, DriftResult, FinalDecision, ForecastBundle, HorizonForecast,
    MarketState, NLPResult, PriorityResult, RegimeResult, ReliabilityResult,
    RiskResult,
)
from core.prediction_ledger_20260617 import PredictionLedger, get_prediction_ledger
from core.generation_identity_20260707 import numeric_generation

HORIZONS = (1, 2, 3, 6)
THRESHOLD_VERSION = "dynamic-threshold-v1"


def _finite(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _clip(value: Any, lo: float = 0.0, hi: float = 1.0, default: float = 0.0) -> float:
    val = _finite(value, default)
    return float(max(lo, min(hi, val if val is not None else default)))


def _utc_iso(value: Any = None) -> Optional[str]:
    try:
        ts = pd.Timestamp(value if value is not None else datetime.now(timezone.utc))
        if pd.isna(ts):
            return None
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts.isoformat()
    except Exception:
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, pd.DataFrame):
        return value.to_dict("records")
    if isinstance(value, pd.Series):
        return value.to_list()
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (np.floating,)): return _finite(value)
    if isinstance(value, (pd.Timestamp, datetime)): return _utc_iso(value)
    return value


def normalize_ohlc(df: Any) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    raw = df.copy()
    cmap = {str(c).strip().lower(): c for c in raw.columns}
    tcol = next((cmap.get(x) for x in ("time", "timestamp", "datetime", "date") if cmap.get(x) is not None), None)
    columns: Dict[str, Any] = {}
    for name, aliases in {
        "open": ("open", "o"), "high": ("high", "h"), "low": ("low", "l"), "close": ("close", "c")
    }.items():
        col = next((cmap.get(a) for a in aliases if cmap.get(a) is not None), None)
        if col is not None:
            columns[name] = pd.to_numeric(raw[col], errors="coerce")
    if tcol is not None:
        times = pd.to_datetime(raw[tcol], utc=True, errors="coerce")
    else:
        times = pd.to_datetime(raw.index, utc=True, errors="coerce")
    out = pd.DataFrame(columns)
    out.insert(0, "time", times)
    vcol = next((cmap.get(x) for x in ("volume", "tick_volume", "vol") if cmap.get(x) is not None), None)
    out["volume"] = pd.to_numeric(raw[vcol], errors="coerce") if vcol is not None else np.nan
    return out.reset_index(drop=True)


def _timeframe_hours(timeframe: str) -> Optional[float]:
    text = str(timeframe or "").strip().upper()
    if text.startswith("H"):
        return _finite(text[1:], None)
    if text.startswith("M"):
        mins = _finite(text[1:], None)
        return mins / 60.0 if mins else None
    if text.startswith("D"):
        days = _finite(text[1:], None)
        return days * 24.0 if days else None
    return None


def validate_data_quality(
    df: Any, *, symbol: str, timeframe: str, source: str, now: Any = None,
    minimum_rows: int = 120,
) -> Tuple[DataQualityResult, pd.DataFrame]:
    raw = normalize_ohlc(df)
    blocking: List[str] = []
    warnings: List[str] = []
    disabled: List[str] = []
    required = {"time", "open", "high", "low", "close"}
    if not required.issubset(raw.columns):
        missing = sorted(required.difference(raw.columns))
        blocking.append("Missing required columns: " + ", ".join(missing))
        return DataQualityResult(status="FAIL_ALL", score=0, blocking_reasons=blocking), raw

    invalid_time = int(raw["time"].isna().sum())
    if invalid_time:
        warnings.append(f"{invalid_time} rows have invalid timestamps and were excluded")
    frame = raw.dropna(subset=["time"]).copy()
    duplicates = int(frame["time"].duplicated(keep=False).sum())
    if duplicates:
        blocking.append(f"Duplicate candle timestamps: {duplicates}")
        disabled.append("time-series models")
    unordered = not frame["time"].is_monotonic_increasing
    if unordered:
        warnings.append("Timestamps were not ordered; calculations use chronological order")
    frame = frame.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)

    numeric_missing = frame[["open", "high", "low", "close"]].isna().any(axis=1)
    missing_pct = float(numeric_missing.mean() * 100) if len(frame) else 100.0
    if missing_pct > 5:
        blocking.append(f"Missing OHLC rows {missing_pct:.2f}% exceeds 5%")
        disabled.append("price models")
    elif missing_pct > 0:
        warnings.append(f"Missing OHLC rows: {missing_pct:.2f}%")
    frame = frame.loc[~numeric_missing].copy()

    if len(frame) < minimum_rows:
        blocking.append(f"Only {len(frame)} clean rows; at least {minimum_rows} required")
    price_positive = (frame[["open", "high", "low", "close"]] > 0).all(axis=1) if not frame.empty else pd.Series(dtype=bool)
    invalid_positive = int((~price_positive).sum()) if len(price_positive) else 0
    invalid_high = int((frame["high"] < frame[["open", "close", "low"]].max(axis=1)).sum()) if not frame.empty else 0
    invalid_low = int((frame["low"] > frame[["open", "close", "high"]].min(axis=1)).sum()) if not frame.empty else 0
    if invalid_positive: blocking.append(f"Non-positive prices: {invalid_positive}")
    if invalid_high: blocking.append(f"High below OHLC relationship: {invalid_high}")
    if invalid_low: blocking.append(f"Low above OHLC relationship: {invalid_low}")

    tf_hours = _timeframe_hours(timeframe)
    if tf_hours is None:
        blocking.append(f"Unsupported timeframe: {timeframe or 'empty'}")
    elif len(frame) >= 3:
        spacing = frame["time"].diff().dropna().dt.total_seconds() / 3600.0
        median_spacing = float(spacing.median()) if not spacing.empty else tf_hours
        unreasonable = float((abs(spacing - tf_hours) > max(tf_hours * 0.35, 0.15)).mean() * 100) if not spacing.empty else 0.0
        if unreasonable > 35:
            warnings.append(f"Irregular {timeframe} spacing: {unreasonable:.1f}% of gaps")
            disabled.append("spacing-sensitive models")
        if median_spacing <= 0:
            blocking.append("Timestamp spacing is non-positive")

    now_ts = pd.Timestamp(now or datetime.now(timezone.utc))
    if now_ts.tzinfo is None: now_ts = now_ts.tz_localize("UTC")
    else: now_ts = now_ts.tz_convert("UTC")
    future_mask = frame["time"] > now_ts + pd.Timedelta(minutes=5) if not frame.empty else pd.Series(False, index=frame.index)
    future_rows = int(future_mask.sum()) if not frame.empty else 0
    if future_rows:
        # Broker/API feeds may include forming candles or rows whose timestamp is
        # ahead because of source timezone handling.  These rows are never used
        # by the completed-H1 calculation.  Excluding them is a successful safety
        # action, not a model failure, provided valid completed rows remain.
        warnings.append(
            f"Future timestamps detected and safely excluded from completed-H1 calculations: {future_rows}"
        )
        frame = frame.loc[~future_mask].copy()
    latest_completed = False
    if not frame.empty and tf_hours:
        latest = frame["time"].iloc[-1]
        completion = latest + pd.Timedelta(hours=tf_hours)
        latest_completed = bool(completion <= now_ts + pd.Timedelta(minutes=3))
        if not latest_completed:
            warnings.append("Latest candle appears incomplete and was excluded from historical calculations")
            frame = frame.iloc[:-1].copy()
        if not frame.empty:
            age_hours = (now_ts - frame["time"].iloc[-1]).total_seconds() / 3600.0
            if age_hours > max(tf_hours * 4, 6):
                warnings.append(f"Latest completed candle is stale by {age_hours:.1f} hours")
    if frame.empty:
        blocking.append("No completed clean candles remain")

    source_ok = bool(str(source or "").strip())
    symbol_ok = bool(str(symbol or "").strip())
    timeframe_ok = bool(tf_hours)
    if not source_ok: warnings.append("Source identity is missing")
    if not symbol_ok: blocking.append("Symbol identity is missing")

    severe = any(x for x in blocking if any(k in x.lower() for k in ("missing required", "no completed", "symbol identity")))
    if severe:
        status = "FAIL_ALL"
    elif blocking:
        status = "FAIL_MODEL"
    elif warnings:
        status = "PASS_WITH_WARNING"
    else:
        status = "PASS"
    penalty = len(warnings) * 5 + len(blocking) * 18 + min(25.0, missing_pct * 3)
    score = max(0.0, min(100.0, 100.0 - penalty))
    return DataQualityResult(
        status=status, score=score, blocking_reasons=blocking, warnings=warnings,
        model_disabled=sorted(set(disabled)), latest_candle_completed=latest_completed,
        normalized_timezone="UTC", missing_row_pct=round(missing_pct, 4),
        source_identity_ok=source_ok, symbol_identity_ok=symbol_ok,
        timeframe_identity_ok=timeframe_ok,
    ), frame.reset_index(drop=True)


def data_signature(frame: pd.DataFrame, *, symbol: str, timeframe: str, source: str) -> str:
    latest = _utc_iso(frame["time"].iloc[-1]) if isinstance(frame, pd.DataFrame) and not frame.empty and "time" in frame else "empty"
    rows = len(frame) if isinstance(frame, pd.DataFrame) else 0
    payload = f"{symbol}|{timeframe}|{source}|{latest}|{rows}"
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        try:
            payload += "|" + frame.tail(5)[["open", "high", "low", "close"]].round(10).to_json()
        except Exception:
            pass
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()[:24]


def _session_label(ts: pd.Timestamp) -> str:
    hour = int(ts.hour)
    if 0 <= hour < 7: return "ASIA"
    if 7 <= hour < 12: return "LONDON"
    if 12 <= hour < 16: return "LONDON_NY_OVERLAP"
    if 16 <= hour < 21: return "NEW_YORK"
    return "LATE"


def _extract_legacy(legacy: Dict[str, Any]) -> Dict[str, Any]:
    shared = dict(legacy or {})
    current = dict(shared.get("current") or {})
    market = dict(shared.get("market") or {})
    decision = dict(shared.get("decision") or {})
    regime = dict(shared.get("regime") or {})
    reliability = dict(shared.get("reliability") or shared.get("reliability_calibration") or {})
    powerbi = dict(shared.get("powerbi") or {})
    priority = dict(shared.get("priority") or {})
    nlp = dict(shared.get("nlp") or {})
    alpha_delta = dict(shared.get("regime_alpha_delta") or regime.get("alpha_delta") or {})
    return {
        "current": current, "market": market, "decision": decision, "regime": regime,
        "reliability": reliability, "powerbi": powerbi, "priority": priority,
        "nlp": nlp, "alpha_delta": alpha_delta,
    }


def _direction(text: Any) -> str:
    s = str(text or "").upper()
    if "BUY" in s or "BULL" in s or "UP" in s: return "BUY"
    if "SELL" in s or "BEAR" in s or "DOWN" in s: return "SELL"
    return "WAIT"


def _extract_priority(parts: Dict[str, Any]) -> PriorityResult:
    priority = parts["priority"]
    best = dict(priority.get("best") or {}) if isinstance(priority, dict) else {}
    current = parts["current"]
    knn = _finite(best.get("KNN Score") or best.get("knn_score") or current.get("knn_score"), None)
    greedy = _finite(best.get("Greedy Score") or best.get("greedy_score") or current.get("greedy_score"), None)
    score = _finite(best.get("Priority Score") or best.get("score") or current.get("priority_score"), None)
    if score is None:
        values = [v for v in (knn, greedy, _finite(parts["reliability"].get("score"), None)) if v is not None]
        score = float(np.mean(values)) if values else 0.0
    score = max(0.0, min(100.0, score))
    label = "A+" if score >= 88 else "A" if score >= 76 else "B" if score >= 62 else "C" if score >= 45 else "AVOID"
    rank = int(best.get("Priority Rank") or best.get("rank") or 0) or None
    return PriorityResult(score=score, label=label, rank=rank, knn_score=knn, greedy_score=greedy)


def _extract_nlp(parts: Dict[str, Any]) -> NLPResult:
    nlp = parts["nlp"]
    summary = dict(nlp.get("summary") or {}) if isinstance(nlp, dict) else {}
    available = bool(summary or nlp.get("articles")) if isinstance(nlp, dict) else False
    try:
        from core.finnhub_connector import connection_status
        fh = connection_status()
        finnhub_available = bool(fh.get("connected"))
    except Exception:
        finnhub_available = False
    direction = _direction(summary.get("nlp_direction") or summary.get("direction"))
    conflict = str(summary.get("conflict_level") or summary.get("nlp_conflict_level") or "NONE").upper()
    reliability = _finite(summary.get("reliability") or summary.get("nlp_reliability_score"), 0.0) or 0.0
    if reliability > 1: reliability /= 100.0
    importance = _finite(summary.get("importance") or summary.get("importance_score"), 0.0) or 0.0
    if importance > 1: importance /= 100.0
    return NLPResult(
        available=available, finnhub_available=finnhub_available, direction=direction,
        conflict_level=conflict, importance=_clip(importance), reliability=_clip(reliability),
        latest_headline=str(summary.get("latest_rank_1_news") or summary.get("headline") or "No relevant news")[:300],
        latest_time=_utc_iso(summary.get("news_time") or summary.get("timestamp")),
        event_response_sample_count=int(_finite(summary.get("event_response_sample_count"), 0) or 0),
        modifier=0.0,
    )


def _regime_runs(regime_history: Any, major: str, frame: pd.DataFrame) -> Tuple[List[float], float]:
    durations: List[float] = []
    age = 0.0
    if isinstance(regime_history, pd.DataFrame) and not regime_history.empty:
        hist = regime_history.copy()
        cmap = {str(c).lower().strip(): c for c in hist.columns}
        rcol = next((c for k, c in cmap.items() if "regime" in k), None)
        scol = next((c for k, c in cmap.items() if "start" in k or "change time" in k), None)
        ecol = next((c for k, c in cmap.items() if "end" in k), None)
        if rcol and scol:
            hist[scol] = pd.to_datetime(hist[scol], utc=True, errors="coerce")
            if ecol: hist[ecol] = pd.to_datetime(hist[ecol], utc=True, errors="coerce")
            hist = hist.dropna(subset=[scol]).sort_values(scol)
            now = frame["time"].iloc[-1] if not frame.empty else pd.Timestamp.now(tz="UTC")
            for idx, row in hist.iterrows():
                start = row[scol]
                end = row[ecol] if ecol and not pd.isna(row.get(ecol)) else now
                hours = max(0.0, (end - start).total_seconds() / 3600.0)
                if hours > 0: durations.append(hours)
            current_rows = hist[hist[rcol].astype(str).str.upper() == str(major).upper()]
            if not current_rows.empty:
                start = current_rows.iloc[-1][scol]
                age = max(0.0, (now - start).total_seconds() / 3600.0)
    if age == 0 and not frame.empty:
        age = min(24.0, float(len(frame)))
    return durations, age


def build_regime_result(parts: Dict[str, Any], frame: pd.DataFrame) -> RegimeResult:
    reg = parts["regime"]
    current = parts["current"]
    ad = parts["alpha_delta"]
    major = str(reg.get("current") or current.get("regime") or current.get("current_regime") or "UNKNOWN")
    history = reg.get("history")
    durations, age = _regime_runs(history, major, frame)
    expected = float(np.median(durations)) if durations else None
    p25 = float(np.percentile(durations, 25)) if len(durations) >= 4 else None
    p75 = float(np.percentile(durations, 75)) if len(durations) >= 4 else None
    remaining = max(0.0, expected - age) if expected is not None else None
    score = _finite(current.get("regime_score") or reg.get("score"), 0.0) or 0.0
    if score <= 10: score *= 10
    confidence = _finite(parts["reliability"].get("score") or current.get("regime_confidence"), 0.0) or 0.0
    if confidence > 1: confidence /= 100.0
    alpha = _finite(ad.get("regime_alpha") or ad.get("alpha") or current.get("alpha"), None)
    delta = _finite(ad.get("regime_delta") or ad.get("delta") or current.get("delta"), None)
    previous_delta = _finite(ad.get("previous_delta") or ad.get("delta_previous"), None)
    acceleration = (delta - previous_delta) if delta is not None and previous_delta is not None else _finite(ad.get("delta_acceleration"), None)
    direction = _direction(major)
    persistence = 0.5
    if durations and expected:
        persistence = _clip(age / max(expected, 1.0), 0, 1, 0.5)
    base_transition = 0.12
    if p75 and age > p75: base_transition += 0.28
    elif expected and age > expected: base_transition += 0.18
    if delta is not None and alpha is not None and alpha * delta < 0: base_transition += 0.16
    if confidence < 0.45: base_transition += 0.10
    t1 = _clip(base_transition, 0.02, 0.85, 0.15)
    t3 = _clip(1 - (1 - t1) ** 3, 0.03, 0.94, 0.3)
    t6 = _clip(1 - (1 - t1) ** 6, 0.05, 0.98, 0.5)
    next_probs = {"RANGE/TRANSITION": round(t3, 4)}
    if direction == "BUY": next_probs["BEARISH"] = round(t3 * 0.55, 4); next_probs["BULLISH"] = round(1 - t3, 4)
    elif direction == "SELL": next_probs["BULLISH"] = round(t3 * 0.55, 4); next_probs["BEARISH"] = round(1 - t3, 4)
    else: next_probs.update({"BULLISH": round((1-t3)/2,4), "BEARISH": round((1-t3)/2,4)})
    warning = "HIGH" if t3 >= 0.65 else "WATCH" if t3 >= 0.4 else "NONE"
    # Preserve existing major regime across lower/middle/higher when no explicit standards are present.
    lower = str(reg.get("lower_standard_regime") or current.get("lower_standard_regime") or major)
    middle = str(reg.get("middle_standard_regime") or current.get("middle_standard_regime") or major)
    higher = str(reg.get("higher_standard_regime") or current.get("higher_standard_regime") or major)
    disagreement = len({_direction(lower), _direction(middle), _direction(higher)} - {"WAIT"}) > 1
    if disagreement:
        confidence *= 0.8
    return RegimeResult(
        major_regime=major, lower_standard_regime=lower, middle_standard_regime=middle,
        higher_standard_regime=higher, regime_score=max(0,min(100,score)), confidence=_clip(confidence),
        reliability=_clip(confidence), age_hours=round(age,3), expected_duration_hours=expected,
        duration_p25_hours=p25, duration_p75_hours=p75, remaining_duration_hours=remaining,
        alpha=alpha, delta=delta, delta_acceleration=acceleration, persistence_score=persistence,
        transition_probability_1h=t1, transition_probability_3h=t3, transition_probability_6h=t6,
        possible_next_regimes=next_probs, transition_warning=warning,
        conflict_warning="MULTI_STANDARD_DISAGREEMENT" if disagreement else "NONE",
    )


def _prediction_frame(parts: Dict[str, Any]) -> pd.DataFrame:
    candidate = parts["powerbi"].get("projected_path") if isinstance(parts["powerbi"], dict) else None
    if isinstance(candidate, pd.DataFrame): return candidate.copy()
    if isinstance(candidate, list): return pd.DataFrame(candidate)
    return pd.DataFrame()


def _point_forecasts(parts: Dict[str, Any], frame: pd.DataFrame) -> Dict[int, Optional[float]]:
    current = float(frame["close"].iloc[-1]) if not frame.empty else _finite(parts["current"].get("last_close"), None)
    pred = _prediction_frame(parts)
    points: Dict[int, Optional[float]] = {h: None for h in HORIZONS}
    if not pred.empty:
        cmap = {str(c).lower(): c for c in pred.columns}
        ccol = next((c for k,c in cmap.items() if "close" in k or "forecast" in k or "predicted price" in k), None)
        if ccol:
            values = pd.to_numeric(pred[ccol], errors="coerce").dropna().tolist()
            for h in HORIZONS:
                if len(values) >= h: points[h] = float(values[h-1])
    final = _finite(parts["powerbi"].get("forecast_close") or parts["current"].get("forecast_close"), None)
    if current is not None and final is not None:
        for h in HORIZONS:
            if points[h] is None:
                points[h] = current + (final - current) * (h / max(HORIZONS))
    return points


def _atr(frame: pd.DataFrame, window: int = 14) -> Optional[float]:
    if frame.empty or len(frame) < 2: return None
    prev = frame["close"].shift(1)
    tr = pd.concat([(frame["high"]-frame["low"]).abs(), (frame["high"]-prev).abs(), (frame["low"]-prev).abs()], axis=1).max(axis=1)
    val = tr.tail(window).mean()
    return _finite(val, None)


def _raw_probabilities(direction: str, parts: Dict[str, Any], horizon: int) -> Tuple[Optional[float], Optional[float], Optional[float], str]:
    confidence = _finite(parts["powerbi"].get("confidence") or parts["current"].get("forecast_confidence") or parts["reliability"].get("score"), None)
    if confidence is None:
        return None, None, None, "UNAVAILABLE"
    if confidence > 1: confidence /= 100.0
    confidence = _clip(confidence, 0.34, 0.95, 0.5)
    # Longer horizons receive a conservative decay, not additional information.
    confidence = 0.5 + (confidence - 0.5) * (1.0 - min(0.35, 0.05 * max(0, horizon - 1)))
    wait = max(0.05, min(0.45, 1.0 - confidence))
    remaining = 1.0 - wait
    if direction == "BUY": buy, sell = remaining * 0.86, remaining * 0.14
    elif direction == "SELL": sell, buy = remaining * 0.86, remaining * 0.14
    else: buy = sell = (1.0 - max(wait, 0.5)) / 2; wait = max(wait, 0.5)
    total = buy + sell + wait
    return buy/total, sell/total, wait/total, "EXISTING_RELIABILITY_PROXY"


def _calibration_diagnostics(probabilities: np.ndarray, outcomes: np.ndarray) -> Dict[str, Any]:
    probabilities = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1 - 1e-6)
    outcomes = np.asarray(outcomes, dtype=float)
    if len(probabilities) == 0:
        return {}
    brier = float(np.mean((probabilities - outcomes) ** 2))
    logloss = float(-np.mean(outcomes * np.log(probabilities) + (1 - outcomes) * np.log(1 - probabilities)))
    buckets: List[Dict[str, Any]] = []
    ece = 0.0
    for lower in np.linspace(0.0, 0.9, 10):
        upper = lower + 0.1
        mask = (probabilities >= lower) & (probabilities < upper if upper < 1.0 else probabilities <= upper)
        count = int(mask.sum())
        if not count:
            continue
        confidence = float(probabilities[mask].mean())
        observed = float(outcomes[mask].mean())
        ece += (count / len(probabilities)) * abs(confidence - observed)
        buckets.append({
            "lower": round(float(lower), 2), "upper": round(float(upper), 2),
            "count": count, "mean_probability": confidence, "observed_frequency": observed,
        })
    return {
        "brier_score": brier, "log_loss": logloss,
        "expected_calibration_error": float(ece), "reliability_buckets": buckets,
    }


def _fit_calibrator(history: pd.DataFrame, class_name: str, current_p: Optional[float]) -> Tuple[Optional[float], str, int, Dict[str, Any]]:
    """Fit only on settled out-of-sample predictions, with chronological holdout diagnostics."""
    if current_p is None or history.empty:
        return current_p, "EXISTING_RELIABILITY_PROXY", 0, {}
    pcol = f"{class_name.lower()}_probability_raw"
    if pcol not in history.columns or "actual_direction" not in history.columns:
        return current_p, "EXISTING_RELIABILITY_PROXY", len(history), {}
    ordered = history.copy()
    if "created_at" in ordered.columns:
        ordered["_created"] = pd.to_datetime(ordered["created_at"], utc=True, errors="coerce")
        ordered = ordered.sort_values("_created")
    x = pd.to_numeric(ordered[pcol], errors="coerce")
    y = (ordered["actual_direction"].astype(str).str.upper() == class_name.upper()).astype(int)
    valid = x.notna() & y.notna()
    x, y = x[valid].reset_index(drop=True), y[valid].reset_index(drop=True)
    n = len(x)
    if n < 30 or y.nunique() < 2:
        return current_p, "EXISTING_RELIABILITY_PROXY", n, {}
    try:
        from sklearn.isotonic import IsotonicRegression
        from sklearn.linear_model import LogisticRegression

        method = "ISOTONIC_OOS" if n >= 200 else "SIGMOID_OOS"

        def make_model(sample_count: int):
            if sample_count >= 200:
                return IsotonicRegression(out_of_bounds="clip")
            return LogisticRegression(solver="lbfgs", class_weight="balanced", max_iter=500)

        # Final 20% is never used for the reported calibration diagnostics.
        split = min(n - 10, max(20, int(n * 0.8)))
        x_train, y_train = x.iloc[:split], y.iloc[:split]
        x_test, y_test = x.iloc[split:], y.iloc[split:]
        test_metrics: Dict[str, Any] = {}
        if len(x_test) >= 10 and y_train.nunique() >= 2:
            eval_model = make_model(len(x_train))
            if isinstance(eval_model, IsotonicRegression):
                eval_model.fit(x_train.to_numpy(), y_train.to_numpy())
                test_p = eval_model.predict(x_test.to_numpy())
            else:
                eval_model.fit(x_train.to_numpy().reshape(-1, 1), y_train.to_numpy())
                test_p = eval_model.predict_proba(x_test.to_numpy().reshape(-1, 1))[:, 1]
            test_metrics = _calibration_diagnostics(test_p, y_test.to_numpy())
            test_metrics["validation_sample_count"] = int(len(x_test))
            test_metrics["training_sample_count"] = int(len(x_train))
            test_metrics["validation_policy"] = "chronological final 20% holdout"

        final_model = make_model(n)
        if isinstance(final_model, IsotonicRegression):
            final_model.fit(x.to_numpy(), y.to_numpy())
            calibrated = float(final_model.predict([current_p])[0])
        else:
            final_model.fit(x.to_numpy().reshape(-1, 1), y.to_numpy())
            calibrated = float(final_model.predict_proba([[current_p]])[0, 1])
        return _clip(calibrated), method, n, test_metrics
    except Exception:
        return current_p, "EXISTING_RELIABILITY_PROXY", n, {}

def calibrate_probabilities(
    ledger: PredictionLedger, *, symbol: str, timeframe: str, horizon: int,
    regime: str, raw: Tuple[Optional[float], Optional[float], Optional[float]],
) -> Tuple[Tuple[Optional[float], Optional[float], Optional[float]], str, Dict[str, Any]]:
    history = ledger.settled_predictions(symbol=symbol, timeframe=timeframe, horizon=horizon, limit=4000)
    hierarchy = [
        (history[history.get("major_regime", pd.Series(index=history.index, dtype=str)).astype(str) == str(regime)] if not history.empty and "major_regime" in history else pd.DataFrame(), "SYMBOL_TF_HORIZON_REGIME"),
        (history, "SYMBOL_TF_HORIZON"),
        (ledger.settled_predictions(symbol=symbol, horizon=horizon, limit=4000), "SYMBOL_HORIZON"),
        (ledger.settled_predictions(horizon=horizon, limit=6000), "GLOBAL_HORIZON"),
    ]
    selected = pd.DataFrame(); scope = "EXISTING_RELIABILITY_PROXY"
    for candidate, label in hierarchy:
        if isinstance(candidate, pd.DataFrame) and len(candidate) >= 30:
            selected = candidate; scope = label; break
    calibrated: List[Optional[float]] = []
    methods: List[str] = []
    metrics: Dict[str, Any] = {"sample_count": len(selected), "scope": scope}
    for cls, p in zip(("BUY", "SELL", "WAIT"), raw):
        cp, method, n, met = _fit_calibrator(selected, cls, p)
        calibrated.append(cp); methods.append(method); metrics[f"{cls.lower()}_sample_count"] = n
        metrics.update({f"{cls.lower()}_{k}": v for k,v in met.items()})
    if all(p is not None for p in calibrated):
        arr = np.clip(np.asarray(calibrated, dtype=float), 0, 1)
        total = float(arr.sum())
        arr = arr / total if total > 0 else np.array([1/3,1/3,1/3])
        calibrated = [float(x) for x in arr]
    source = "+".join(sorted(set(methods))) + ":" + scope
    return (calibrated[0], calibrated[1], calibrated[2]), source, metrics


def _interval(history: pd.DataFrame, current: float, point: Optional[float], horizon: int, atr: Optional[float], drift_multiplier: float) -> Tuple[Optional[float], Optional[float], int, Optional[float], float, Optional[float]]:
    target = 0.90
    residuals = pd.to_numeric(history.get("absolute_error", pd.Series(dtype=float)), errors="coerce").dropna() if not history.empty else pd.Series(dtype=float)
    coverage = None
    if not history.empty and {"actual_price","lower_bound","upper_bound"}.issubset(history.columns):
        valid = history[["actual_price","lower_bound","upper_bound"]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(valid): coverage = float(((valid.actual_price >= valid.lower_bound) & (valid.actual_price <= valid.upper_bound)).mean())
    if len(residuals) >= 20:
        radius = float(np.quantile(residuals, target))
        if coverage is not None and coverage < target:
            radius *= 1 + min(0.75, (target-coverage)*2.5)
    else:
        radius = (atr or abs(current)*0.0008) * math.sqrt(max(1,horizon)) * 1.35
    radius *= max(1.0, drift_multiplier)
    if point is None: return None, None, len(residuals), coverage, target, None
    lower, upper = point-radius, point+radius
    return lower, upper, len(residuals), coverage, target, (coverage-target if coverage is not None else None)


def _optimize_threshold(history: pd.DataFrame, fallback: float) -> Tuple[float, str]:
    if history.empty or len(history) < 40:
        return fallback, "fallback-v1"
    data = history.sort_values("created_at") if "created_at" in history else history.copy()
    train = data.iloc[:max(1,int(len(data)*0.8))]
    if len(train) < 32: return fallback, "fallback-v1"
    probs = []
    for _, row in train.iterrows():
        d = str(row.get("predicted_direction") or "WAIT").upper()
        p = _finite(row.get(f"{d.lower()}_probability_calibrated"), None) or _finite(row.get(f"{d.lower()}_probability_raw"), None)
        probs.append(p)
    train = train.assign(_p=probs)
    train = train[train._p.notna()]
    if len(train) < 30: return fallback, "fallback-v1"
    best_t, best_u = fallback, -1e18
    for t in np.arange(0.52,0.761,0.02):
        take = train[train._p >= t]
        if len(take) < 8: continue
        correct = pd.to_numeric(take.get("direction_correct"), errors="coerce").fillna(0)
        mfe = pd.to_numeric(take.get("maximum_favourable_excursion"), errors="coerce").fillna(0)
        mae = pd.to_numeric(take.get("maximum_adverse_excursion"), errors="coerce").fillna(0)
        cost = pd.to_numeric(take.get("estimated_cost"), errors="coerce").fillna(0)
        net = np.where(correct>0, mfe, -mae) - cost
        equity = np.cumsum(net)
        drawdown = float(np.max(np.maximum.accumulate(equity)-equity)) if len(equity) else 0
        false_penalty = float((correct==0).mean())
        trade_penalty = max(0.0, len(take)/len(train)-0.65)
        utility = float(np.sum(net) - 0.35*drawdown - 0.15*false_penalty - 0.1*trade_penalty)
        if utility > best_u: best_t,best_u=float(t),utility
    return max(0.52,min(0.76,best_t)), "walk-forward-utility-v1"


def dynamic_threshold(
    *, horizon: int, regime: RegimeResult, drift: DriftResult, quality: DataQualityResult,
    expected_value: Optional[float], interval_width_ratio: Optional[float], agreement: float,
    priority: PriorityResult, actionability: float, session: str, history: pd.DataFrame,
) -> Tuple[float, str, List[str]]:
    fallback = {1:0.58,2:0.59,3:0.60,6:0.62}.get(horizon,0.60)
    base, version = _optimize_threshold(history, fallback)
    reasons: List[str] = []
    reg_dir = _direction(regime.major_regime)
    if reg_dir in {"BUY","SELL"} and regime.confidence >= 0.65 and regime.transition_probability_3h < 0.35:
        base -= 0.025; reasons.append("strong aligned regime")
    if reg_dir == "WAIT" or "RANGE" in regime.major_regime.upper():
        base += 0.04; reasons.append("range regime")
    transition = {1:regime.transition_probability_1h,2:regime.transition_probability_3h,3:regime.transition_probability_3h,6:regime.transition_probability_6h}[horizon]
    if transition >= 0.5: base += 0.045; reasons.append("transition risk")
    if drift.status == "WATCH": base += 0.015
    elif drift.status == "DEGRADED": base += 0.045; reasons.append("degraded drift")
    elif drift.status == "CRITICAL": base += 0.09; reasons.append("critical drift")
    if quality.status == "PASS_WITH_WARNING": base += 0.02
    elif quality.status.startswith("FAIL"): base = 0.99; reasons.append("data quality block")
    if expected_value is not None and expected_value <= 0: base = max(base,0.99); reasons.append("negative expected value")
    if interval_width_ratio is not None and interval_width_ratio > 0.004: base += 0.03; reasons.append("wide interval")
    if agreement < 0.45: base += 0.06; reasons.append("forecast disagreement")
    if priority.score < 45: base += 0.04
    if actionability < 0.5: base += 0.05
    if session in {"LATE"}: base += 0.01
    return max(0.52,min(0.99,base)), version or THRESHOLD_VERSION, reasons


def _expected_value(history: pd.DataFrame, direction_p: Optional[float], current: float, atr: Optional[float], horizon: int, symbol: str) -> Dict[str, Any]:
    pip_size = 0.01 if "JPY" in symbol.upper() else 0.0001
    spread = pip_size * (1.2 if "EURUSD" in symbol.upper() else 2.0)
    slippage = spread * 0.35
    buffer = spread * 0.25
    estimated_cost = spread + slippage + buffer
    correct = history[pd.to_numeric(history.get("direction_correct"), errors="coerce")==1] if not history.empty and "direction_correct" in history else pd.DataFrame()
    wrong = history[pd.to_numeric(history.get("direction_correct"), errors="coerce")==0] if not history.empty and "direction_correct" in history else pd.DataFrame()
    if len(correct) >= 10:
        avg_gain = float(pd.to_numeric(correct.get("maximum_favourable_excursion"), errors="coerce").dropna().median())
        gain_source = "settled MFE"
    else:
        avg_gain = (atr or abs(current)*0.0007) * math.sqrt(horizon)
        gain_source = "ATR fallback"
    if len(wrong) >= 10:
        avg_loss = float(pd.to_numeric(wrong.get("maximum_adverse_excursion"), errors="coerce").dropna().median())
        loss_source = "settled MAE"
    else:
        avg_loss = (atr or abs(current)*0.0007) * math.sqrt(horizon) * 0.9
        loss_source = "ATR fallback"
    if direction_p is None:
        return {"expected_gain":None,"expected_loss":None,"estimated_cost":estimated_cost,"expected_value":None,"risk_reward":None,"break_even_probability":None,"source":f"{gain_source}/{loss_source}"}
    expected_gain = direction_p * avg_gain
    expected_loss = (1-direction_p) * avg_loss
    ev = expected_gain - expected_loss - estimated_cost
    rr = avg_gain/avg_loss if avg_loss>0 else None
    bep = (avg_loss+estimated_cost)/(avg_gain+avg_loss) if avg_gain+avg_loss>0 else None
    return {"expected_gain":expected_gain,"expected_loss":expected_loss,"estimated_cost":estimated_cost,"expected_value":ev,"risk_reward":rr,"break_even_probability":bep,"source":f"{gain_source}/{loss_source}"}


def _actionability(history: pd.DataFrame, *, probability: Optional[float], interval_ratio: Optional[float], priority: float, expected_value: Optional[float], transition: float, drift: DriftResult, quality: DataQualityResult, nlp: NLPResult) -> Tuple[float,str,str,List[str],str]:
    """Estimate coverage while keeping hard blockers separate from soft evidence.

    Moderate disagreement, slightly low priority, neutral timing and limited
    samples reduce the score but do not automatically force WAIT.  Only safety
    failures are returned in ``blockers``.
    """
    blockers: List[str] = []
    p = probability or 0.0
    if len(history) >= 60 and "direction_correct" in history:
        try:
            from sklearn.linear_model import LogisticRegression
            data = history.sort_values("created_at") if "created_at" in history else history.copy()
            data = data.iloc[:max(1,int(len(data)*0.8))]
            feats = pd.DataFrame({
                "p": pd.to_numeric(data.get("buy_probability_calibrated"), errors="coerce").fillna(pd.to_numeric(data.get("sell_probability_calibrated"), errors="coerce")).fillna(0.5),
                "priority": pd.to_numeric(data.get("priority_score"), errors="coerce").fillna(50)/100,
                "ev": pd.to_numeric(data.get("expected_value"), errors="coerce").fillna(0),
                "width": (pd.to_numeric(data.get("upper_bound"), errors="coerce")-pd.to_numeric(data.get("lower_bound"), errors="coerce")).abs().fillna(0),
            })
            y = pd.to_numeric(data["direction_correct"], errors="coerce").fillna(0).astype(int)
            if y.nunique() >= 2:
                model = LogisticRegression(class_weight="balanced", max_iter=300)
                model.fit(feats, y)
                cur = [[p, priority/100, expected_value or 0, interval_ratio or 0]]
                prob = float(model.predict_proba(cur)[0,1]); source="CHRONOLOGICAL_LOGISTIC_META"
            else:
                raise ValueError("one class")
        except Exception:
            prob = 0.42*p + 0.25*(priority/100) + 0.18*(1-transition) + 0.15*quality.score/100; source="DETERMINISTIC_FALLBACK"
    else:
        prob = 0.42*p + 0.25*(priority/100) + 0.18*(1-transition) + 0.15*quality.score/100; source="DETERMINISTIC_FALLBACK"
    if interval_ratio is not None:
        prob -= min(0.16, interval_ratio*14)
    if expected_value is None:
        prob -= 0.16
        blockers.append("expected value after costs is unavailable")
    elif expected_value <= 0:
        prob -= 0.30
        blockers.append("negative expected value after costs")
    if drift.status == "DEGRADED":
        prob -= 0.10
    if drift.status == "CRITICAL":
        prob -= 0.28
        blockers.append("critical forecast drift")
    if quality.status.startswith("FAIL"):
        prob = 0
        blockers.append("critical market data quality failure")
    if transition >= 0.85:
        prob -= 0.25
        blockers.append("critical regime transition risk")
    elif transition >= 0.55:
        prob -= 0.08
    if nlp.conflict_level == "CRITICAL" and nlp.importance >= 0.65:
        prob -= 0.20
        blockers.append("severe event conflict")
    elif nlp.conflict_level == "HIGH" and nlp.importance >= 0.65:
        prob -= 0.08
    prob = _clip(prob)
    label = "YES" if prob >= 0.50 and not blockers else "NO"
    reason = "Signal passes hard safety gates" if label=="YES" else (blockers[0] if blockers else "Evidence remains below the controlled coverage gate")
    return prob,label,reason,blockers,source


def compute_drift(ledger: PredictionLedger, frame: pd.DataFrame, *, symbol: str, timeframe: str) -> DriftResult:
    settled = ledger.settled_predictions(symbol=symbol,timeframe=timeframe,limit=800)
    reasons: List[str] = []
    prediction_score=0.0
    if len(settled) >= 40:
        data=settled.sort_values("created_at") if "created_at" in settled else settled
        recent=data.tail(max(15,int(len(data)*0.2))); base=data.iloc[:-len(recent)]
        rec_err=pd.to_numeric(recent.get("absolute_error"),errors="coerce").dropna()
        base_err=pd.to_numeric(base.get("absolute_error"),errors="coerce").dropna()
        if len(rec_err)>=5 and len(base_err)>=15 and base_err.median()>0:
            ratio=float(rec_err.median()/base_err.median())
            if ratio>1.8: prediction_score+=55; reasons.append("forecast error sharply increased")
            elif ratio>1.3: prediction_score+=28; reasons.append("forecast error increased")
        rec_acc=pd.to_numeric(recent.get("direction_correct"),errors="coerce").mean()
        base_acc=pd.to_numeric(base.get("direction_correct"),errors="coerce").mean()
        if pd.notna(rec_acc) and pd.notna(base_acc) and base_acc-rec_acc>0.18: prediction_score+=30; reasons.append("direction accuracy deteriorated")
    feature_score=0.0
    if len(frame)>=120:
        returns=frame.close.pct_change().dropna()
        recent=returns.tail(24); base=returns.iloc[-240:-24] if len(returns)>=264 else returns.iloc[:-24]
        if len(base)>=40 and base.std()>0:
            z=abs(float(recent.std()-base.std()))/float(base.std())
            if z>1.0: feature_score+=45; reasons.append("volatility feature drift")
            elif z>0.5: feature_score+=22
        ranges=(frame.high-frame.low).abs()
        if len(ranges)>=120:
            r_ratio=float(ranges.tail(24).median()/max(ranges.iloc[:-24].median(),1e-12))
            if r_ratio>2.0 or r_ratio<0.45: feature_score+=35; reasons.append("range/ATR distribution shifted")
    runs=ledger.recent_runs(symbol=symbol,timeframe=timeframe,limit=160)
    decision_score=0.0
    if len(runs)>=30 and "result_json" in runs:
        decisions=[]
        for val in runs.result_json:
            try: decisions.append(json.loads(val).get("final_decision",{}).get("final_decision","WAIT"))
            except Exception: decisions.append("WAIT")
        ser=pd.Series(decisions)
        recent=ser.head(20); older=ser.iloc[20:]
        if len(older)>=10:
            drift=sum(abs(float((recent==x).mean()-(older==x).mean())) for x in ("BUY","SELL","WAIT"))
            if drift>0.8: decision_score+=45; reasons.append("decision frequency shifted")
    score=max(prediction_score,feature_score,decision_score)
    status="CRITICAL" if score>=75 else "DEGRADED" if score>=50 else "WATCH" if score>=25 else "STABLE"
    return DriftResult(
        status=status,score=min(100,score),
        prediction_status="CRITICAL" if prediction_score>=75 else "DEGRADED" if prediction_score>=50 else "WATCH" if prediction_score>=25 else "STABLE",
        feature_status="CRITICAL" if feature_score>=75 else "DEGRADED" if feature_score>=50 else "WATCH" if feature_score>=25 else "STABLE",
        decision_status="CRITICAL" if decision_score>=75 else "DEGRADED" if decision_score>=50 else "WATCH" if decision_score>=25 else "STABLE",
        reasons=reasons, threshold_adjustment={"STABLE":0,"WATCH":0.015,"DEGRADED":0.045,"CRITICAL":0.09}[status],
        interval_multiplier={"STABLE":1,"WATCH":1.08,"DEGRADED":1.25,"CRITICAL":1.55}[status],
        retraining_recommended=status in {"DEGRADED","CRITICAL"},
    )


def _purged_walk_forward_direction_metrics(data: pd.DataFrame, horizon: int) -> Dict[str, Any]:
    """Evaluate existing OOS ledger predictions in chronological purged windows.

    The ledger rows are predictions produced before their outcomes were known.  This
    evaluator still removes at least ``horizon`` rows between each expanding history
    window and test window, plus one embargo row, so overlapping labels are not mixed.
    """
    if len(data) < 60:
        return {
            "status": "INSUFFICIENT SAMPLE", "fold_count": 0,
            "purge_gap_rows": int(max(6, horizon)), "embargo_rows": 1,
        }
    ordered = data.copy()
    ordered["_created"] = pd.to_datetime(ordered.get("created_at"), utc=True, errors="coerce")
    ordered = ordered.sort_values("_created").reset_index(drop=True)
    purge = int(max(6, horizon))
    embargo = 1
    min_history = max(40, int(len(ordered) * 0.45))
    test_size = max(10, int(len(ordered) * 0.15))
    fold_scores: List[float] = []
    fold_balanced: List[float] = []
    test_samples = 0
    train_end = min_history
    while train_end + purge + embargo + 5 <= len(ordered):
        test_start = train_end + purge
        test_end = min(len(ordered), test_start + test_size)
        test = ordered.iloc[test_start:test_end]
        if len(test) < 5:
            break
        actual = test["actual_direction"].astype(str).str.upper()
        predicted = test["predicted_direction"].astype(str).str.upper()
        fold_scores.append(float((actual == predicted).mean()))
        try:
            from sklearn.metrics import balanced_accuracy_score
            fold_balanced.append(float(balanced_accuracy_score(actual, predicted)))
        except Exception:
            fold_balanced.append(fold_scores[-1])
        test_samples += len(test)
        train_end = test_end + embargo
    if not fold_scores:
        return {
            "status": "INSUFFICIENT SAMPLE", "fold_count": 0,
            "purge_gap_rows": purge, "embargo_rows": embargo,
        }
    return {
        "status": "VALID", "fold_count": len(fold_scores),
        "purge_gap_rows": purge, "embargo_rows": embargo,
        "test_samples": int(test_samples),
        "direction_accuracy": float(np.mean(fold_scores)),
        "balanced_accuracy": float(np.mean(fold_balanced)),
        "policy": "expanding chronological windows; no shuffle; purged labels",
    }


def _group_direction_metrics(data: pd.DataFrame, column: str, minimum: int = 20) -> Dict[str, Any]:
    output: Dict[str, Any] = {}
    if column not in data.columns:
        return output
    for name, group in data.groupby(column, dropna=False):
        if len(group) < minimum:
            continue
        actual = group["actual_direction"].astype(str).str.upper()
        predicted = group["predicted_direction"].astype(str).str.upper()
        output[str(name)] = {
            "samples": int(len(group)),
            "direction_accuracy": float((actual == predicted).mean()),
        }
    return output


def _walk_forward_summary(ledger: PredictionLedger, *, symbol: str, timeframe: str) -> ReliabilityResult:
    all_rows = ledger.settled_predictions(symbol=symbol, timeframe=timeframe, limit=6000)
    by_h: Dict[str, Dict[str, Any]] = {}
    calibration: Dict[str, Dict[str, Any]] = {}
    aggregate_brier: List[float] = []
    aggregate_logloss: List[float] = []
    aggregate_ece: List[float] = []
    for h in HORIZONS:
        d = all_rows[pd.to_numeric(all_rows.get("horizon_hours"), errors="coerce") == h] if not all_rows.empty else pd.DataFrame()
        if len(d) < 20:
            by_h[f"{h}h"] = {
                "status": "INSUFFICIENT SAMPLE", "samples": len(d),
                "purge_gap_rows": int(max(6, h)), "embargo_rows": 1,
            }
            continue
        d = d.copy()
        d["_created"] = pd.to_datetime(d.get("created_at"), utc=True, errors="coerce")
        d = d.sort_values("_created")
        y = pd.to_numeric(d.get("direction_correct"), errors="coerce").dropna()
        actual = d.loc[y.index, "actual_direction"].astype(str).str.upper()
        pred = d.loc[y.index, "predicted_direction"].astype(str).str.upper()
        try:
            from sklearn.metrics import balanced_accuracy_score, precision_recall_fscore_support
            bal = float(balanced_accuracy_score(actual, pred))
            precision, recall, f1, _ = precision_recall_fscore_support(
                actual, pred, labels=["BUY", "SELL", "WAIT"], zero_division=0
            )
            cls = {
                name: {"precision": float(precision[i]), "recall": float(recall[i]), "f1": float(f1[i])}
                for i, name in enumerate(["BUY", "SELL", "WAIT"])
            }
        except Exception:
            bal = float(y.mean()); cls = {}

        abs_err = pd.to_numeric(d.get("absolute_error"), errors="coerce").dropna()
        coverage = None
        if {"actual_price", "lower_bound", "upper_bound"}.issubset(d.columns):
            vals = d[["actual_price", "lower_bound", "upper_bound"]].apply(pd.to_numeric, errors="coerce").dropna()
            if len(vals):
                coverage = float(((vals.actual_price >= vals.lower_bound) & (vals.actual_price <= vals.upper_bound)).mean())

        net = np.where(
            pd.to_numeric(d.get("direction_correct"), errors="coerce").fillna(0) > 0,
            pd.to_numeric(d.get("maximum_favourable_excursion"), errors="coerce").fillna(0),
            -pd.to_numeric(d.get("maximum_adverse_excursion"), errors="coerce").fillna(0),
        ) - pd.to_numeric(d.get("estimated_cost"), errors="coerce").fillna(0)
        equity = np.cumsum(net)
        dd = float(np.max(np.maximum.accumulate(equity) - equity)) if len(equity) else None
        wins = float(np.sum(net[net > 0])); losses = abs(float(np.sum(net[net < 0])))
        pf = wins / losses if losses > 0 else None

        # Multiclass probability diagnostics use calibrated values only where all
        # three probabilities and the settled class are available.
        probability_columns = [
            "buy_probability_calibrated", "sell_probability_calibrated", "wait_probability_calibrated"
        ]
        probability_metrics: Dict[str, Any] = {}
        if set(probability_columns).issubset(d.columns):
            probs = d[probability_columns].apply(pd.to_numeric, errors="coerce")
            mask = probs.notna().all(axis=1) & d["actual_direction"].astype(str).str.upper().isin(["BUY", "SELL", "WAIT"])
            if int(mask.sum()) >= 10:
                p = probs.loc[mask].to_numpy(dtype=float)
                p = np.clip(p, 1e-6, 1 - 1e-6)
                p = p / p.sum(axis=1, keepdims=True)
                labels = d.loc[mask, "actual_direction"].astype(str).str.upper().map({"BUY": 0, "SELL": 1, "WAIT": 2}).to_numpy()
                one_hot = np.eye(3)[labels]
                brier = float(np.mean(np.sum((p - one_hot) ** 2, axis=1)))
                logloss = float(-np.mean(np.log(p[np.arange(len(p)), labels])))
                confidence = p.max(axis=1); correct = (p.argmax(axis=1) == labels).astype(float)
                cal_diag = _calibration_diagnostics(confidence, correct)
                probability_metrics = {
                    "brier_score": brier, "log_loss": logloss,
                    "expected_calibration_error": cal_diag.get("expected_calibration_error"),
                    "reliability_buckets": cal_diag.get("reliability_buckets", []),
                }
                aggregate_brier.append(brier); aggregate_logloss.append(logloss)
                if probability_metrics["expected_calibration_error"] is not None:
                    aggregate_ece.append(float(probability_metrics["expected_calibration_error"]))

        if "created_at" in d.columns:
            created_hour = pd.to_datetime(d["created_at"], utc=True, errors="coerce").dt.hour
            d["session"] = np.select(
                [created_hour.between(7, 11), created_hour.between(12, 16), created_hour.between(0, 6)],
                ["LONDON", "NY_OVERLAP", "ASIA"], default="OTHER",
            )
        walk_forward = _purged_walk_forward_direction_metrics(d, h)
        by_h[f"{h}h"] = {
            "status": "VALID", "samples": len(d),
            "trades": int((d.predicted_direction.astype(str).str.upper() != "WAIT").sum()),
            "direction_accuracy": float(y.mean()), "balanced_accuracy": bal,
            "class_metrics": cls,
            "mean_absolute_price_error": float(abs_err.mean()) if len(abs_err) else None,
            "median_absolute_price_error": float(abs_err.median()) if len(abs_err) else None,
            "interval_coverage": coverage,
            "average_interval_width": float((pd.to_numeric(d.get("upper_bound"), errors="coerce") - pd.to_numeric(d.get("lower_bound"), errors="coerce")).abs().mean()) if "upper_bound" in d and "lower_bound" in d else None,
            "net_result_after_cost": float(np.sum(net)), "maximum_drawdown": dd, "profit_factor": pf,
            "walk_forward": walk_forward,
            "by_regime": _group_direction_metrics(d, "major_regime"),
            "by_session": _group_direction_metrics(d, "session"),
            **probability_metrics,
        }
    valid = [v for v in by_h.values() if v.get("status") == "VALID"]
    if not valid:
        return ReliabilityResult(
            score=0, status="INSUFFICIENT SAMPLE", sample_count=len(all_rows),
            validation_by_horizon=by_h, calibration_by_horizon=calibration,
        )
    accuracy = float(np.average([v["direction_accuracy"] for v in valid], weights=[v["samples"] for v in valid]))
    errors = [v["mean_absolute_price_error"] for v in valid if v.get("mean_absolute_price_error") is not None]
    coverages = [v["interval_coverage"] for v in valid if v.get("interval_coverage") is not None]
    return ReliabilityResult(
        score=accuracy * 100, status="VALIDATED", sample_count=len(all_rows), direction_accuracy=accuracy,
        balanced_accuracy=float(np.mean([v["balanced_accuracy"] for v in valid])),
        brier_score=float(np.mean(aggregate_brier)) if aggregate_brier else None,
        log_loss=float(np.mean(aggregate_logloss)) if aggregate_logloss else None,
        expected_calibration_error=float(np.mean(aggregate_ece)) if aggregate_ece else None,
        mean_absolute_price_error=float(np.mean(errors)) if errors else None,
        median_absolute_price_error=float(np.median(errors)) if errors else None,
        interval_coverage=float(np.mean(coverages)) if coverages else None,
        validation_by_horizon=by_h, calibration_by_horizon=calibration,
    )

def _reconcile(horizons: Dict[str,HorizonForecast]) -> Tuple[str,str,float]:
    dirs={h:intf.direction for h,intf in horizons.items()}
    active=[d for d in dirs.values() if d in {"BUY","SELL"}]
    agreement=max(active.count("BUY"),active.count("SELL"))/len(active) if active else 0.0
    if len(set(active))<=1 and active:
        return "STRONG ALIGNMENT",f"All directional horizons agree on {active[0]}",agreement
    d1=dirs.get("1h","WAIT"); d3=dirs.get("3h","WAIT"); d6=dirs.get("6h","WAIT")
    if d1 in {"BUY","SELL"} and d3==d6 and d3 in {"BUY","SELL"} and d1!=d3:
        return "SHORT PULLBACK",f"1h {d1} conflicts with 3h/6h {d3}",agreement
    if d1=="WAIT" and d3==d6 and d3 in {"BUY","SELL"}:
        return "DELAYED SETUP",f"1h waits while 3h/6h align {d3}",agreement
    if dirs.get("1h")==dirs.get("2h")=="BUY" and d6=="SELL":
        return "SHORT-LIVED BULLISH MOVE","Short horizons bullish inside bearish 6h structure",agreement
    if dirs.get("1h")==dirs.get("2h")=="SELL" and d6=="BUY":
        return "SHORT-LIVED BEARISH MOVE","Short horizons bearish inside bullish 6h structure",agreement
    return "LARGE DISAGREEMENT","Horizon directions materially disagree; prefer WAIT",agreement


def historical_similarity(frame: pd.DataFrame, horizon: int = 3, lookback: int = 24, top_n: int = 30) -> Dict[str,Any]:
    if len(frame)<lookback+horizon+80:
        return {"status":"INSUFFICIENT SAMPLE","match_count":0,"effective_weighted_sample_size":0}
    close=frame.close.astype(float); returns=close.pct_change().fillna(0)
    target=returns.tail(lookback).to_numpy(); candidates=[]
    end_limit=len(frame)-lookback-horizon
    for end in range(lookback,end_limit):
        seq=returns.iloc[end-lookback:end].to_numpy()
        denom=np.linalg.norm(target)*np.linalg.norm(seq)
        sim=float(np.dot(target,seq)/denom) if denom>0 else 0.0
        vol_match=1/(1+abs(float(np.std(seq)-np.std(target)))/(np.std(target)+1e-12))
        recency=math.exp(-(len(frame)-end)/1500)
        weight=max(0,sim)*vol_match*(0.55+0.45*recency)
        if weight<=0: continue
        start=float(close.iloc[end-1]); future=close.iloc[end:end+horizon]
        move=float(future.iloc[-1]-start); mfe=float(future.max()-start); mae=float(start-future.min())
        candidates.append((weight,sim,move,mfe,mae))
    top=sorted(candidates,key=lambda x:x[0],reverse=True)[:top_n]
    if len(top)<8: return {"status":"INSUFFICIENT SAMPLE","match_count":len(top),"effective_weighted_sample_size":0}
    w=np.array([x[0] for x in top]); moves=np.array([x[2] for x in top]); w=w/(w.sum()+1e-12)
    ess=float(1/np.sum(w*w)); bullish=float(np.sum(w[moves>0])); bearish=float(np.sum(w[moves<0]))
    consistency=max(bullish,bearish)
    reliability=max(0,min(1,consistency*min(1,ess/20)))
    return {"status":"VALID","match_count":len(top),"effective_weighted_sample_size":ess,"bullish_outcome_percentage":bullish*100,"bearish_outcome_percentage":bearish*100,"median_movement":float(np.median(moves)),"p25_movement":float(np.percentile(moves,25)),"p75_movement":float(np.percentile(moves,75)),"outcome_consistency":consistency,"reliability_after_weighting":reliability,"note":"Similarity percentages are evidence, not probabilities."}


def build_decision_result(
    *, legacy_shared: Dict[str,Any], ohlc: pd.DataFrame, symbol: str="EURUSD", timeframe: str="H1",
    source: str="UNKNOWN", ledger: Optional[PredictionLedger]=None, now: Any=None, calculation_generation: int=0,
    full_metric_snapshot: Optional[Dict[str, Any]] = None,
) -> DecisionResult:
    ledger=ledger or get_prediction_ledger()
    quality, frame=validate_data_quality(ohlc,symbol=symbol,timeframe=timeframe,source=source,now=now)
    created=pd.Timestamp(now or datetime.now(timezone.utc)); created=created.tz_localize("UTC") if created.tzinfo is None else created.tz_convert("UTC")
    run_id=f"{created.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:12]}"
    signature=data_signature(frame,symbol=symbol,timeframe=timeframe,source=source)
    parts=_extract_legacy(legacy_shared)
    current_price=float(frame.close.iloc[-1]) if not frame.empty else _finite(parts["current"].get("last_close"),None)
    latest_time=_utc_iso(frame.time.iloc[-1]) if not frame.empty else None
    market=MarketState(latest_completed_candle_time=latest_time,current_price=current_price,row_count=len(frame),session=_session_label(frame.time.iloc[-1]) if not frame.empty else "UNKNOWN",spread=None,volatility=float(frame.close.pct_change().tail(24).std()) if len(frame)>=25 else None,source_available=bool(frame.size))
    full_metric = dict(full_metric_snapshot or {})
    regime=build_regime_result(parts,frame)
    authority_regime = str(full_metric.get("current_major_regime") or "").strip()
    if authority_regime and authority_regime.upper() != "UNKNOWN":
        regime.major_regime = authority_regime
    priority=_extract_priority(parts)
    authority_candidates = list(full_metric.get("top_two_daily_candidates") or [])
    authority_best = dict(authority_candidates[0]) if authority_candidates and isinstance(authority_candidates[0], dict) else {}
    if authority_best:
        authority_score = _finite(authority_best.get("Priority Score") or authority_best.get("combined score"), None)
        if authority_score is not None:
            priority.score = max(0.0, min(100.0, authority_score))
            priority.label = "A+" if priority.score >= 88 else "A" if priority.score >= 76 else "B" if priority.score >= 62 else "C" if priority.score >= 45 else "AVOID"
        priority.rank = int(_finite(authority_best.get("Priority Rank") or authority_best.get("priority rank"), 0) or 0) or None
        priority.knn_score = _finite(authority_best.get("KNN Score"), priority.knn_score)
        priority.greedy_score = _finite(authority_best.get("Greedy Score"), priority.greedy_score)
    nlp=_extract_nlp(parts)
    drift=compute_drift(ledger,frame,symbol=symbol,timeframe=timeframe)
    reliability=_walk_forward_summary(ledger,symbol=symbol,timeframe=timeframe)
    legacy_reliability = _finite(parts["reliability"].get("score"), None)
    if legacy_reliability is not None:
        legacy_reliability = legacy_reliability * 100.0 if legacy_reliability <= 1.0 else legacy_reliability
        if reliability.status == "INSUFFICIENT SAMPLE" or reliability.sample_count < 30:
            reliability.score = max(0.0, min(100.0, legacy_reliability))
            reliability.status = "EXISTING VALIDATED RELIABILITY"
    points=_point_forecasts(parts,frame)
    atr=_atr(frame)
    horizons: Dict[str,HorizonForecast]={}
    soft_penalties_by_horizon: Dict[str, List[str]] = {}
    preliminary_dirs=[]
    for h in HORIZONS:
        point=points[h]
        direction="BUY" if point is not None and current_price is not None and point>current_price else "SELL" if point is not None and current_price is not None and point<current_price else _direction(parts["current"].get("prediction_direction") or parts["decision"].get("prediction_direction") or regime.major_regime)
        preliminary_dirs.append(direction)
    agreement=max(preliminary_dirs.count("BUY"),preliminary_dirs.count("SELL"))/len(HORIZONS)
    priority.forecast_agreement=agreement
    for h,direction in zip(HORIZONS,preliminary_dirs):
        history=ledger.settled_predictions(symbol=symbol,timeframe=timeframe,horizon=h,limit=4000)
        raw_buy,raw_sell,raw_wait,raw_source=_raw_probabilities(direction,parts,h)
        (cal_buy,cal_sell,cal_wait),cal_source,cal_metrics=calibrate_probabilities(ledger,symbol=symbol,timeframe=timeframe,horizon=h,regime=regime.major_regime,raw=(raw_buy,raw_sell,raw_wait))
        point=points[h]
        lower,upper,res_n,coverage,target,cov_err=_interval(history,current_price or 0,point,h,atr,drift.interval_multiplier)
        interval_width=(upper-lower) if upper is not None and lower is not None else None
        interval_ratio=interval_width/abs(current_price) if interval_width is not None and current_price else None
        direction_p={"BUY":cal_buy,"SELL":cal_sell,"WAIT":cal_wait}.get(direction)
        ev=_expected_value(history,direction_p,current_price or 0,atr,h,symbol)
        transition={1:regime.transition_probability_1h,2:regime.transition_probability_3h,3:regime.transition_probability_3h,6:regime.transition_probability_6h}[h]
        action_prob,action_label,action_reason,action_blockers,action_source=_actionability(history,probability=direction_p,interval_ratio=interval_ratio,priority=priority.score,expected_value=ev["expected_value"],transition=transition,drift=drift,quality=quality,nlp=nlp)
        threshold,threshold_ver,threshold_reasons=dynamic_threshold(horizon=h,regime=regime,drift=drift,quality=quality,expected_value=ev["expected_value"],interval_width_ratio=interval_ratio,agreement=agreement,priority=priority,actionability=action_prob,session=market.session,history=history)
        hard_blockers=list(action_blockers)
        soft_penalties: List[str] = []
        if direction_p is None:
            hard_blockers.append("calibrated directional probability unavailable")
        elif direction_p < max(0.0, threshold - 0.10):
            hard_blockers.append(f"calibrated probability {direction_p:.3f} materially below required {threshold:.3f}")
        elif direction_p < threshold:
            soft_penalties.append(f"calibrated probability {direction_p:.3f} slightly below target {threshold:.3f}")
        if ev["expected_value"] is None:
            hard_blockers.append("expected value after costs unavailable")
        elif ev["expected_value"] <= 0:
            hard_blockers.append("negative expected value after costs")
        if interval_ratio is None or lower is None or upper is None or lower >= upper:
            hard_blockers.append("broken prediction interval")
        elif interval_ratio > 0.020:
            hard_blockers.append("prediction interval critically wide")
        elif interval_ratio > 0.008:
            soft_penalties.append("prediction interval moderately wide")
        if quality.status.startswith("FAIL"):
            hard_blockers.append("critical market data quality failure")
        if drift.status=="CRITICAL":
            hard_blockers.append("critical forecast drift")
        elif drift.status=="DEGRADED":
            soft_penalties.append("forecast drift is degraded")
        if nlp.conflict_level == "CRITICAL" and nlp.importance>=0.65:
            hard_blockers.append("severe event conflict")
        elif nlp.conflict_level in {"HIGH", "MODERATE"}:
            soft_penalties.append("moderate event-risk disagreement")
        if transition >= 0.85:
            hard_blockers.append("critical regime transition risk")
        elif transition >= 0.55:
            soft_penalties.append("moderate regime transition risk")
        if agreement < 0.50:
            soft_penalties.append("moderate model disagreement")
        if priority.score < 45:
            soft_penalties.append("priority below preferred target")
        if len(history) < 30:
            soft_penalties.append("limited settled validation sample")
        # Threshold reasons are explanatory modifiers, not automatic blockers.
        soft_penalties.extend(str(x) for x in threshold_reasons if x)
        soft_penalties_by_horizon[f"{h}h"] = sorted(set(soft_penalties))
        controlled_gate = action_prob >= 0.45 and (direction_p is not None and direction_p >= max(0.0, threshold - 0.05))
        decision=direction if direction in {"BUY","SELL"} and not hard_blockers and controlled_gate else "WAIT"
        blockers = hard_blockers
        due=_utc_iso(created+pd.Timedelta(hours=h))
        horizons[f"{h}h"]=HorizonForecast(
            horizon_hours=h,direction=direction,point_forecast=point,lower_bound=lower,upper_bound=upper,
            target_coverage=target,actual_coverage=coverage,interval_width=interval_width,coverage_error=cov_err,
            residual_sample_count=res_n,buy_probability_raw=raw_buy,sell_probability_raw=raw_sell,wait_probability_raw=raw_wait,
            buy_probability_calibrated=cal_buy,sell_probability_calibrated=cal_sell,wait_probability_calibrated=cal_wait,
            probability_source=cal_source if "OOS" in cal_source else raw_source,threshold=threshold,threshold_version=threshold_ver,
            expected_gain=ev["expected_gain"],expected_loss=ev["expected_loss"],estimated_cost=ev["estimated_cost"],expected_value=ev["expected_value"],risk_reward=ev["risk_reward"],break_even_probability=ev["break_even_probability"],
            reliability=(direction_p or 0),actionability_probability=action_prob,actionability_label="YES" if decision in {"BUY","SELL"} else action_label,actionability_reason=f"{action_reason} ({action_source}); soft evidence: {', '.join(soft_penalties[:5]) if soft_penalties else 'none'}",blocking_reasons=sorted(set(blockers)),priority_score=max(0,priority.score-(100*(1-action_prob)*0.25)-min(15.0,2.0*len(soft_penalties))),knn_score=priority.knn_score,greedy_score=priority.greedy_score,drift_adjustment=drift.threshold_adjustment,decision=decision,due_time=due,
        )
        reliability.calibration_by_horizon[f"{h}h"]={**cal_metrics,"source":cal_source}
    label,reason,agreement_score=_reconcile(horizons)
    selected=3
    primary=horizons["3h"] if horizons.get("3h") else horizons["2h"]
    if primary.decision=="WAIT" and horizons["2h"].decision in {"BUY","SELL"}:
        selected=2
        primary=horizons["2h"]

    # The protected Full Metric H1 direction is the market view authority.
    # Forecasts, Research, NLP and M1 may confirm or block an entry, but they
    # must never turn a blocked BUY into SELL (or a blocked SELL into BUY).
    authority_direction = _direction(full_metric.get("full_metric_direction"))
    market_view = authority_direction if full_metric else primary.direction
    authority_tradeability = _direction(full_metric.get("tradeability_decision")) if full_metric else primary.decision
    final_blockers = list(full_metric.get("blocking_reasons") or []) if full_metric else []
    final_soft_warnings: List[str] = list(soft_penalties_by_horizon.get(f"{selected}h", []))
    if label=="LARGE DISAGREEMENT":
        final_soft_warnings.append("large multi-horizon disagreement lowers priority")
    forecast_conflict = primary.direction in {"BUY", "SELL"} and market_view in {"BUY", "SELL"} and primary.direction != market_view
    if forecast_conflict:
        final_blockers.append(f"PowerBI/prediction {primary.direction} directly opposes Full Metric H1 {market_view}")
    else:
        final_blockers.extend(primary.blocking_reasons)

    m1_status = str(full_metric.get("m1_timing_status") or "CONFIRM").upper() if full_metric else "CONFIRM"
    if market_view in {"BUY", "SELL"} and m1_status == "WAIT FOR CONFIRMATION":
        final_soft_warnings.append("M1 timing is neutral; reduce aggressiveness or wait for cleaner timing")

    confidence_for_view={"BUY":primary.buy_probability_calibrated,"SELL":primary.sell_probability_calibrated,"WAIT":primary.wait_probability_calibrated}.get(market_view)
    probability_floor = max(0.0, float(primary.threshold or 0.0) - 0.05)
    break_even = float(primary.break_even_probability or 0.0)
    calibrated_risk_ok = confidence_for_view is not None and confidence_for_view >= max(probability_floor, break_even)
    positive_ev = primary.expected_value is not None and primary.expected_value > 0
    interval_valid = primary.lower_bound is not None and primary.upper_bound is not None and primary.lower_bound < primary.upper_bound
    can_trade_authority = market_view in {"BUY", "SELL"} and authority_tradeability == market_view
    can_trade_forecast = primary.direction == market_view and not forecast_conflict and not primary.blocking_reasons and calibrated_risk_ok and positive_ev and interval_valid
    if quality.status == "FAIL_ALL":
        final_decision = "DATA NOT READY"
    elif can_trade_authority and can_trade_forecast and not final_blockers:
        final_decision = market_view
    else:
        final_decision = "WAIT"

    confidence=confidence_for_view
    uncertainty=100*(1-(confidence or 0)) if confidence is not None else 100.0
    error_pct=None
    if reliability.mean_absolute_price_error is not None and current_price:
        error_pct=reliability.mean_absolute_price_error/abs(current_price)*100
    risk_level="LOW" if final_decision in {"BUY","SELL"} and uncertainty<35 and drift.status=="STABLE" else "MEDIUM" if uncertainty<55 and drift.status in {"STABLE","WATCH"} else "HIGH"
    supporting=[f"Full Metric H1 market view {market_view}",f"{selected}h forecast confirmation {primary.direction}",f"horizon agreement {agreement_score:.0%}",f"priority {priority.label} {priority.score:.1f}"] + [f"Soft warning: {x}" for x in sorted(set(final_soft_warnings))[:6]]
    main_reason=("Full Metric H1 direction passed forecast, reliability, cost and timing confirmation gates" if final_decision in {"BUY","SELL"} else (final_blockers[0] if final_blockers else reason))
    final=FinalDecision(
        final_decision=final_decision,directional_market_view=market_view,tradeability_decision=final_decision if final_decision in {"BUY","SELL"} else "WAIT",less_risky_decision=final_decision if final_decision in {"BUY","SELL"} else "WAIT",main_reason=main_reason,supporting_reasons=supporting,blocking_reasons=sorted(set(final_blockers)),calibrated_confidence=confidence,actionability_probability=primary.actionability_probability if primary.direction == market_view else 0.0,expected_value=primary.expected_value if primary.direction == market_view else None,risk_level=risk_level,uncertainty_pct=uncertainty,error_estimate_pct=error_pct,selected_horizon=selected,decision_expiry_time=primary.due_time,regime_transition_warning=regime.transition_warning,drift_warning=drift.status,data_quality_warning=quality.status,
    )
    bundle=ForecastBundle(horizons=horizons,reconciliation_label=label,reconciliation_reason=reason,selected_horizon=selected,agreement_score=agreement_score)
    interval_ok=primary.interval_width is not None and current_price is not None and primary.interval_width/abs(current_price)<=0.008
    risk=RiskResult(risk_level=risk_level,uncertainty_pct=uncertainty,error_estimate_pct=error_pct,interval_acceptable=interval_ok,estimated_cost=primary.estimated_cost,cost_source="settled history or conservative symbol fallback")
    similarity={f"{h}h":historical_similarity(frame,horizon=h) for h in HORIZONS}
    expires=_utc_iso(created+pd.Timedelta(hours=1))
    status="COMPLETED" if quality.status in {"PASS","PASS_WITH_WARNING"} else "COMPLETED_WITH_BLOCK"
    return DecisionResult(
        schema_version=SCHEMA_VERSION,run_id=run_id,calculation_generation=numeric_generation(calculation_generation, default=1),created_at=_utc_iso(created) or "",expires_at=expires,
        symbol=symbol,timeframe=timeframe,source=source,latest_completed_candle_time=market.latest_completed_candle_time,data_signature=signature,model_version=MODEL_VERSION,
        calculation_version=CALCULATION_VERSION,calculation_status=status,failure_reason=None,market=market,
        data_quality=quality,regime=regime,forecasts=bundle,priority=priority,nlp=nlp,reliability=reliability,
        drift=drift,risk=risk,final_decision=final,metadata={
            "threshold_version":THRESHOLD_VERSION,"similarity":similarity,
            "ledger_status":ledger.health(),"existing_logic_preserved":True,
            "probability_note":"Calibrated only when settled out-of-sample samples are sufficient; otherwise marked proxy.",
            "expected_value_note":"Estimate after conservative spread/slippage buffer; never guaranteed profit.",
            "primary_calculation_authority":"Full Metric Detail + History" if full_metric else "legacy compatibility",
            "full_metric_direction":market_view,
            "confirmation_components_cannot_reverse_direction":bool(full_metric),
            "m1_role":"entry timing and confirmation only",
            "wait_policy_version":"hard-soft-selective-classification-20260619-v1",
            "hard_blockers":sorted(set(final_blockers)),
            "soft_penalties":sorted(set(final_soft_warnings)),
            "soft_penalties_by_horizon":_json_safe(soft_penalties_by_horizon),
            "coverage_gate":{"calibrated_probability_floor":probability_floor,"break_even_probability":break_even,"positive_expected_value_required":True,"m1_neutral_is_soft":True},
            "reliability_components":{"ledger_walk_forward":_json_safe(asdict(reliability)),"legacy_existing_score":legacy_reliability},
        },
    )


def serialize_result(result: DecisionResult) -> Dict[str,Any]:
    return _json_safe(result.to_dict())
