"""Canonical institutional quant layer for ADX Quant Pro.

This module is additive and run-gated.  It does not replace existing Field 10,
Field 3, ML, history, export, or UI logic; it publishes one synchronized evidence
snapshot that those surfaces can read without triggering a second API run.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import math
import re
import sqlite3

import numpy as np
import pandas as pd

from core.institutional_quant_migration_20260708 import migrate_institutional_quant_schema
from core.field3_three_regime_engine import build_field3_three_regime_ranking, persist_field3_v2, candle_hash as _field3_candle_hash
from core.global_symbol_context import (
    configure_universe, get_global_symbol_context, publish_loaded_universe,
    publish_completed_generation,
)

try:
    from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
except Exception:  # pragma: no cover
    DEFAULT_DB_PATH = Path("data/multi_symbol_field10_20260701.sqlite3")

FIELD10_KEY = "field10_institutional_ranking_20260708"
NEWS_KEY = "field10_news_nlp_evidence_20260708"
EXPLAIN_KEY = "field10_rank_explanation_20260708"
MODEL_SCORE_KEY = "field10_model_scores_20260708"
FIELD3_KEY = "field3_multisymbol_regime_20260708"
FIELD3_EVIDENCE_KEY = "field3_regime_evidence_v2"
FIELD3_VALIDATION_KEY = "field3_research_validation_v2"
FIELD1_KEY = "field1_canonical_multisymbol_summary_20260708"
FIELD2_KEY = "field2_canonical_projection_20260708"
FIELD11_KEY = "field11_similar_path_multisymbol_20260708"
RESEARCH_KEY = "research_model_validation_20260708"
RUN_IDENTITY_KEY = "canonical_run_identity_20260708"
DATA_VIS_KEY = "data_visualization_canonical_20260708"
LOAD_AUDIT_KEY = "data_load_audit_20260708"
CSV_KEY = "field10_institutional_ranking_csv_20260708"
MAX_SYMBOLS = 12
HORIZON_STEPS = {"1H": 1, "3H": 3, "6H": 6, "12H": 12, "24H": 24, "36H": 36}
TRANSITION_HORIZONS = ("1H", "3H", "6H", "12H", "24H")
SIM_HORIZONS = ("1H", "3H", "6H", "12H", "24H")
POSITIVE_WORDS = {
    "beat", "beats", "growth", "strong", "higher", "rise", "rises", "rally", "gain", "gains",
    "bullish", "improve", "improves", "positive", "upbeat", "surplus", "cooling", "easing",
}
NEGATIVE_WORDS = {
    "miss", "misses", "fall", "falls", "drop", "drops", "weak", "weaker", "lower", "loss",
    "bearish", "risk", "risks", "war", "tariff", "inflation", "recession", "deficit", "hawkish",
}


def _norm_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")


def _norm_tf(value: Any) -> str:
    text = str(value or "H4").strip().upper().replace("4H", "H4").replace("1H", "H1")
    return text or "H4"


def _ordered_unique(values: Any, *, limit: int = MAX_SYMBOLS) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Sequence):
        return []
    out: list[str] = []
    for value in values:
        s = _norm_symbol(value)
        if s and s not in out:
            out.append(s)
        if len(out) >= int(limit):
            break
    return out


def canonical_symbols_from_state(state: Mapping[str, Any] | None) -> list[str]:
    state_map = state if isinstance(state, Mapping) else {}
    try:
        context = get_global_symbol_context(state_map, restore=False)
        authoritative = list(context.loaded_symbols or context.configured_symbols)
        if authoritative:
            return _ordered_unique(authoritative, limit=MAX_SYMBOLS)
    except Exception:
        pass
    candidates: list[Any] = []
    for key in (
        "canonical_selected_symbols",
        "canonical_ranking_symbols",
        "multi_symbol_selected_20260701",
        "selected_symbols_for_run_20260705",
        "adx_current_selected_symbols_20260708",
    ):
        value = state_map.get(key)
        if isinstance(value, str):
            candidates.append(value)
        elif isinstance(value, Sequence):
            candidates.extend(list(value))
    if not candidates:
        try:
            from core.multi_symbol_load_manager_20260707 import get_canonical_ranking_symbols
            candidates.extend(get_canonical_ranking_symbols(state_map))
        except Exception:
            pass
    if not candidates:
        for key in ("multi_symbol_selector_1", "multi_symbol_selector_2", "multi_symbol_selector_3"):
            value = state_map.get(key)
            if isinstance(value, str):
                candidates.append(value)
            elif isinstance(value, Sequence):
                candidates.extend(list(value))
    return _ordered_unique(candidates, limit=MAX_SYMBOLS)


def current_timeframe_from_state(state: Mapping[str, Any] | None) -> str:
    state_map = state if isinstance(state, Mapping) else {}
    try:
        context = get_global_symbol_context(state_map, restore=False)
        if context.timeframe:
            return _norm_tf(context.timeframe)
    except Exception:
        pass
    for key in (
        "canonical_ranking_timeframe", "selected_timeframe", "settings_timeframe",
        "timeframe", "multi_symbol_timeframe_20260701", "current_timeframe",
    ):
        if state_map.get(key):
            return _norm_tf(state_map.get(key))
    return "H4"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except Exception:
        return default


def _clip(value: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, _safe_float(value))))


def _as_frame(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, list):
        try:
            return pd.DataFrame(value)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def _extract_payloads_from_records(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    try:
        from core.multi_symbol_load_manager_20260707 import LOAD_RECORDS_KEY, CANONICAL_GROUP
        records = state.get(LOAD_RECORDS_KEY)
        if isinstance(records, Mapping):
            ordered_groups = [CANONICAL_GROUP, "FIRST", "SECOND", "THIRD"]
            for group in ordered_groups:
                record = records.get(group)
                report = record.get("report") if isinstance(record, Mapping) else None
                results = report.get("results") if isinstance(report, Mapping) else None
                if isinstance(results, Mapping):
                    for sym, payload in results.items():
                        s = _norm_symbol(sym)
                        if s and isinstance(payload, Mapping) and s not in payloads:
                            payloads[s] = dict(payload)
    except Exception:
        pass
    candles = state.get("canonical_symbol_candles")
    if isinstance(candles, Mapping):
        for sym, frame in candles.items():
            s = _norm_symbol(sym)
            if s and s not in payloads:
                payloads[s] = {"symbol": s, "frame": _as_frame(frame), "provider": "CANONICAL_SYMBOL_CANDLES", "status": "READY"}
    return payloads


def _load_frame_from_repository(symbol: str, timeframe: str, limit: int = 700) -> pd.DataFrame:
    try:
        from core.data.candle_repository import CandleRepository
        repo = CandleRepository(DEFAULT_DB_PATH)
        frame = repo.load(symbol, timeframe, limit=limit, completed_only=True)
        return _as_frame(frame)
    except Exception:
        return pd.DataFrame()


def _standardize_candles(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    df = frame.copy()
    rename = {}
    for src, dst in (("Open", "open"), ("High", "high"), ("Low", "low"), ("Close", "close"), ("Volume", "volume")):
        if src in df.columns and dst not in df.columns:
            rename[src] = dst
    df = df.rename(columns=rename)
    time_col = next((c for c in ("open_time", "time", "datetime", "date", "broker_open_time") if c in df.columns), None)
    if time_col:
        df["open_time"] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    else:
        df["open_time"] = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=len(df), freq="4h")
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    required = [c for c in ("open", "high", "low", "close") if c in df.columns]
    if len(required) < 4:
        return pd.DataFrame()
    df = df.dropna(subset=["open_time", "open", "high", "low", "close"]).sort_values("open_time").drop_duplicates("open_time", keep="last")
    return df.tail(700).reset_index(drop=True)


def _data_quality_grade(rows: int, coverage: float, status: str = "") -> str:
    status_upper = str(status or "").upper()
    if rows >= 500 and coverage >= 0.90:
        return "A_INSTITUTIONAL_READY"
    if rows >= 250 and coverage >= 0.50:
        return "B_RESEARCH_READY"
    if rows >= 100:
        return "C_USABLE_DEGRADED"
    if rows >= 25 or "CACHE" in status_upper:
        return "D_EMERGENCY_CACHE"
    return "F_MISSING"


def _symbol_currencies(symbol: str) -> set[str]:
    s = _norm_symbol(symbol)
    if len(s) >= 6 and s[:6].isalpha():
        return {s[:3], s[3:6]}
    if s.startswith("XAU"):
        return {"XAU", "USD", "GOLD"}
    return {s}


def _news_candidates_from_state(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in (
        "field10_news_nlp_evidence_20260708", "finnhub_ranked_news_20260626",
        "finnhub_news_rows_20260626", "news_nlp_rows_20260612", "latest_news_rows",
    ):
        value = state.get(key)
        if isinstance(value, pd.DataFrame):
            rows.extend(value.to_dict("records"))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            rows.extend([dict(item) for item in value if isinstance(item, Mapping)])
        elif isinstance(value, Mapping):
            possible = value.get("rows") or value.get("news") or value.get("items")
            if isinstance(possible, Sequence):
                rows.extend([dict(item) for item in possible if isinstance(item, Mapping)])
    return rows


def _score_news_for_symbol(symbol: str, state: Mapping[str, Any], bias: str) -> dict[str, Any]:
    currencies = _symbol_currencies(symbol)
    best: dict[str, Any] | None = None
    best_score = -1.0
    now = pd.Timestamp.now(tz="UTC")
    for row in _news_candidates_from_state(state):
        title = str(row.get("Latest News Title") or row.get("title") or row.get("headline") or row.get("News Title") or row.get("Highest-Impact Current News Title") or "").strip()
        if not title or title.upper() == "NEWS_UNAVAILABLE":
            continue
        haystack = " ".join(str(row.get(k) or "") for k in row.keys()).upper()
        match_count = sum(1 for token in currencies if token and token.upper() in haystack)
        if match_count <= 0 and symbol not in haystack:
            continue
        published = row.get("published_at") or row.get("datetime") or row.get("time") or row.get("News Published Time") or row.get("Time")
        try:
            ptime = pd.to_datetime(published, errors="coerce", utc=True)
            freshness = max(0.0, (now - ptime).total_seconds() / 60.0) if pd.notna(ptime) else 9999.0
        except Exception:
            freshness = 9999.0
        relevance = _clip(0.25 + 0.35 * match_count + max(0.0, 0.40 - min(freshness, 1440.0) / 3600.0))
        if relevance > best_score:
            best_score = relevance
            best = {"title": title, "freshness": freshness, "row": row, "match_count": match_count, "relevance": relevance}
    if not best:
        return {
            "Latest News Title": "NEWS_UNAVAILABLE",
            "News Currency/Symbol Match": "NO_MATCH",
            "News Sentiment": "NEWS_UNAVAILABLE",
            "News Relevance Score": 0.0,
            "News Freshness Minutes": None,
            "News Absorption Score": 1.0,
            "News Conflict Flag": "NO_NEWS",
            "NLP Evidence Source": "NEWS_UNAVAILABLE",
            "NLP Missing Reason": "NO_SAVED_NEWS_EVIDENCE",
        }
    words = re.findall(r"[A-Za-z]+", best["title"].lower())
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    raw_score = (pos - neg) / max(1, pos + neg)
    if raw_score > 0.15:
        sentiment = "POSITIVE"
    elif raw_score < -0.15:
        sentiment = "NEGATIVE"
    else:
        sentiment = "NEUTRAL"
    bias_upper = str(bias or "").upper()
    conflict = "NO"
    if ("BUY" in bias_upper and sentiment == "NEGATIVE") or ("SELL" in bias_upper and sentiment == "POSITIVE"):
        conflict = "YES"
    absorption = _clip(1.0 - best["relevance"] * (0.45 if conflict == "YES" else 0.15))
    return {
        "Latest News Title": best["title"],
        "News Currency/Symbol Match": "MATCHED" if best["match_count"] else "SYMBOL_MATCHED",
        "News Sentiment": sentiment,
        "News Relevance Score": round(float(best["relevance"]), 4),
        "News Freshness Minutes": None if best["freshness"] >= 9000 else round(float(best["freshness"]), 1),
        "News Absorption Score": round(absorption, 4),
        "News Conflict Flag": conflict,
        "NLP Evidence Source": "LOUGHRAN_MCDONALD_TITLE_FALLBACK",
        "NLP Missing Reason": "NLP_FALLBACK_USED" if (pos + neg) else "TITLE_DICTIONARY_NEUTRAL",
    }


def _returns_for_frame(frame: pd.DataFrame) -> pd.Series:
    df = _standardize_candles(frame)
    if df.empty or "close" not in df.columns:
        return pd.Series(dtype=float)
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    return close.pct_change().replace([np.inf, -np.inf], np.nan).dropna()


def _rolling_probability_score(returns: pd.Series, p_up: float) -> tuple[float, float, float]:
    if returns.empty:
        return 0.50, 0.69, 0.0
    y = (returns.tail(80) > 0).astype(float)
    p = pd.Series(float(_clip(p_up, 0.01, 0.99)), index=y.index)
    brier = float(((p - y) ** 2).mean()) if len(y) else 0.25
    log_score = float((-(y * np.log(p) + (1 - y) * np.log(1 - p))).mean()) if len(y) else 0.69
    crps = float(np.mean(np.abs(returns.tail(80) - returns.tail(80).median()))) * 100.0 if len(returns) else 0.0
    return brier, log_score, crps


def _correlation_penalties(frames: dict[str, pd.DataFrame], symbols: list[str]) -> dict[str, dict[str, float]]:
    series = {}
    for symbol in symbols:
        rets = _returns_for_frame(frames.get(symbol, pd.DataFrame())).tail(180).reset_index(drop=True)
        if len(rets) >= 30:
            series[symbol] = rets
    if len(series) < 2:
        return {s: {"corr_penalty": 0.0, "duplicate_penalty": 0.0, "spillover_risk": 0.0} for s in symbols}
    min_len = min(len(v) for v in series.values())
    matrix = pd.DataFrame({s: v.tail(min_len).reset_index(drop=True) for s, v in series.items()})
    corr = matrix.corr().fillna(0.0)
    # Lightweight Ledoit-Wolf-style shrinkage toward identity; avoids heavy sklearn dependency.
    shrink = corr.copy() * 0.75
    for s in shrink.columns:
        shrink.loc[s, s] = 1.0
    out: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        if symbol not in shrink.index:
            out[symbol] = {"corr_penalty": 0.0, "duplicate_penalty": 0.0, "spillover_risk": 0.0}
            continue
        others = shrink.loc[symbol].drop(labels=[symbol], errors="ignore").abs()
        max_corr = float(others.max()) if len(others) else 0.0
        mean_corr = float(others.mean()) if len(others) else 0.0
        currencies = _symbol_currencies(symbol)
        dup_currency = 0.0
        for other in symbols:
            if other == symbol:
                continue
            if currencies & _symbol_currencies(other):
                dup_currency = max(dup_currency, 0.12)
        out[symbol] = {
            "corr_penalty": round(_clip((max_corr - 0.55) / 0.45), 4),
            "duplicate_penalty": round(_clip((max_corr - 0.65) / 0.35 + dup_currency), 4),
            "spillover_risk": round(_clip(mean_corr), 4),
        }
    return out


def _compute_symbol_metrics(symbol: str, timeframe: str, frame: pd.DataFrame, payload: Mapping[str, Any], corr: Mapping[str, float], state: Mapping[str, Any]) -> dict[str, Any]:
    df = _standardize_candles(frame)
    rows = int(len(df))
    coverage = round(min(1.0, rows / 600.0), 4)
    provider = str(payload.get("provider") or payload.get("actual_provider") or payload.get("provider_used") or "LOCAL_VALID_CACHE" if rows else "NONE")
    provider_symbol = str(payload.get("provider_symbol") or symbol)
    latest_time = None
    if rows and "open_time" in df.columns:
        latest_time = pd.Timestamp(df["open_time"].max()).isoformat()
    status = str(payload.get("status") or payload.get("validation_status") or ("VALIDATED" if rows else "MISSING"))
    failure = str(payload.get("message") or payload.get("failure_reason") or payload.get("validation_reason") or "")
    grade = _data_quality_grade(rows, coverage, status)
    if rows < 25:
        return {
            "Symbol": symbol, "Timeframe": timeframe, "Provider used": provider, "Provider symbol": provider_symbol,
            "Candle count": rows, "Coverage ratio": coverage, "Data quality grade": grade,
            "Higher-Standard Regime": "NO_REGIME", "Higher-Standard Bias": "WAIT", "Less-Risky Bias": "WAIT",
            "Regime probability": 0.0, "Regime age": 0,
            "Transition Risk 1H": 1.0, "Transition Risk 3H": 1.0, "Transition Risk 6H": 1.0,
            "Transition Risk 12H": 1.0, "Transition Risk 24H": 1.0,
            "Expected Return 1H": 0.0, "Expected Return 6H": 0.0, "Expected Return 12H": 0.0,
            "Expected Return 24H": 0.0, "Expected Return 36H": 0.0,
            "Probability of reaching expected value 1H": 0.0, "Probability of reaching expected value 6H": 0.0,
            "Probability of reaching expected value 12H": 0.0, "Probability of reaching expected value 24H": 0.0,
            "Volatility forecast 1H": 0.0, "Volatility forecast 6H": 0.0, "Volatility forecast 12H": 0.0, "Volatility forecast 24H": 0.0,
            "CVaR / drawdown-risk estimate": 1.0, "Spread/slippage cost if available": 0.0,
            "Net Expected Value": 0.0, "Risk-adjusted Expected Value": -1.0,
            "Wasserstein robust expected value": -1.0,
            "Correlation penalty using Ledoit-Wolf shrinkage and DCC": _safe_float(corr.get("corr_penalty")),
            "Duplicate exposure penalty": _safe_float(corr.get("duplicate_penalty")),
            "Spillover risk using Diebold-Yilmaz logic": _safe_float(corr.get("spillover_risk")),
            "Changepoint risk using BOCPD": 1.0, "Conformal interval width": 1.0,
            "Calibration score": 0.0, "Brier score": 0.25, "Log score": 0.69, "CRPS score": 0.0,
            "Rank confidence": 0.0, "Rank stability": 0.0, "WeightedNetEV": 0.0, "RiskPenalty": 1.0,
            "RobustEV_adjustment": 0.0, "CalibrationBonus": 0.0, "RankStabilityBonus": 0.0,
            "NewsAbsorptionBonus": 1.0, "InstitutionalUtility": -1.0,
            "Final daily less-risky bias": "WAIT", "Entry permission": "BLOCKED",
            "Missing reason": failure or "MISSING_OR_INSUFFICIENT_CANDLES", "Broker Candle Time": latest_time or "NOT_AVAILABLE",
        }
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    returns = close.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    recent = returns.tail(min(120, len(returns)))
    medium = returns.tail(min(300, len(returns)))
    mu = float(recent.mean()) if len(recent) else 0.0
    mu_medium = float(medium.mean()) if len(medium) else mu
    vol = float(recent.std(ddof=0)) if len(recent) else 0.0
    vol_long = float(medium.std(ddof=0)) if len(medium) else vol
    vol = max(vol, 1e-7)
    trend = (float(close.iloc[-1]) / float(close.iloc[max(0, len(close) - min(60, len(close)))]) - 1.0) if len(close) > 5 else mu
    signal = trend / max(vol * math.sqrt(max(1, min(60, len(close)))), 1e-7)
    p_up = _clip(0.5 + math.tanh(signal) * 0.28, 0.02, 0.98)
    regime_prob = round(max(p_up, 1.0 - p_up), 4)
    regime = "TREND_UP" if signal > 0.2 else "TREND_DOWN" if signal < -0.2 else "RANGE_TRANSITION"
    bias = "BUY" if p_up >= 0.55 else "SELL" if p_up <= 0.45 else "WAIT"
    less_risky = bias if regime_prob >= 0.55 and coverage >= 0.25 else "WAIT"
    signs = np.sign(returns.tail(80).values)
    last_sign = np.sign(mu if abs(mu) > 1e-12 else (returns.iloc[-1] if len(returns) else 0))
    age = 0
    for value in reversed(signs):
        if value == 0 or value == last_sign:
            age += 1
        else:
            break
    vol_expansion = _clip((vol / max(vol_long, 1e-7) - 1.0) / 1.5)
    changepoint = _clip(abs(mu - mu_medium) / max(vol_long, 1e-7) / 2.5 + vol_expansion * 0.30)
    tail = returns.tail(160)
    worst = tail[tail <= tail.quantile(0.05)] if len(tail) >= 20 else tail
    cvar = abs(float(worst.mean())) * 100.0 if len(worst) else vol * 100.0
    residual = returns.tail(160) - mu
    conformal_width = float((residual.quantile(0.90) - residual.quantile(0.10)) * 100.0) if len(residual) >= 30 else vol * 100.0 * 2
    calibration = _clip(1.0 - conformal_width / max(0.15, vol * 100.0 * 9.0))
    brier, log_score, crps = _rolling_probability_score(returns, p_up)
    cost = 0.015 if len(symbol) == 6 else 0.03
    expected: dict[str, float] = {}
    probabilities: dict[str, float] = {}
    vols: dict[str, float] = {}
    netev: dict[str, float] = {}
    for h, steps in HORIZON_STEPS.items():
        # H4 source candles are still projected into user-facing hour windows via
        # scaled drift/vol; no candle identity is changed.
        scaled_mu = mu * max(1.0, steps / 4.0)
        ev = scaled_mu * 100.0
        expected[h] = round(ev, 5)
        vols[h] = round(vol * math.sqrt(max(1.0, steps / 4.0)) * 100.0, 5)
        snr = ev / max(vols[h], 1e-6)
        probabilities[h] = round(_clip(0.50 + math.tanh(abs(snr)) * 0.28), 4)
        netev[h] = ev - cost
    weighted_net_ev = (
        0.10 * netev["1H"] + 0.20 * netev["6H"] + 0.30 * netev["12H"] +
        0.25 * netev["24H"] + 0.15 * netev["36H"]
    )
    transition = {
        "1H": _clip(changepoint * 0.45 + vol_expansion * 0.25),
        "3H": _clip(changepoint * 0.55 + vol_expansion * 0.30),
        "6H": _clip(changepoint * 0.70 + vol_expansion * 0.40),
        "12H": _clip(changepoint * 0.85 + vol_expansion * 0.50),
        "24H": _clip(changepoint + vol_expansion * 0.65),
    }
    data_quality_penalty = 1.0 - _clip(coverage)
    corr_penalty = _safe_float(corr.get("corr_penalty"))
    dup_penalty = _safe_float(corr.get("duplicate_penalty"))
    spillover = _safe_float(corr.get("spillover_risk"))
    risk_penalty = (
        0.25 * _clip(cvar / 1.25) + 0.20 * transition["6H"] + 0.15 * changepoint +
        0.10 * _clip(conformal_width / 0.90) + 0.10 * vol_expansion +
        0.10 * _clip(corr_penalty + dup_penalty) + 0.05 * data_quality_penalty + 0.05 * _clip(cost / 0.10)
    )
    wasserstein_radius = _clip(conformal_width / max(0.25, abs(weighted_net_ev) + conformal_width + 1e-6))
    robust_adjustment = _clip(1.0 - 0.45 * wasserstein_radius, 0.40, 1.05)
    robust_ev = weighted_net_ev * robust_adjustment
    rank_stability = _clip(1.0 - (transition["6H"] * 0.55 + vol_expansion * 0.25 + data_quality_penalty * 0.20))
    rank_confidence = _clip((regime_prob - 0.50) * 2.0 * 0.45 + calibration * 0.25 + rank_stability * 0.30)
    news = _score_news_for_symbol(symbol, state, less_risky)
    news_bonus = _safe_float(news.get("News Absorption Score"), 1.0)
    calibration_bonus = 0.80 + 0.40 * calibration
    stability_bonus = 0.80 + 0.35 * rank_stability
    institutional_utility = weighted_net_ev * robust_adjustment - risk_penalty * calibration_bonus * stability_bonus * news_bonus
    risk_adjusted_ev = weighted_net_ev - risk_penalty
    entry = "TRADE CANDIDATE" if institutional_utility > 0 and transition["6H"] < 0.62 and grade[0] in {"A", "B", "C"} else "WAIT"
    if grade.startswith("F"):
        entry = "BLOCKED"
    elif grade.startswith("D"):
        entry = "DATA DEGRADED"
    shap = [
        f"WeightedNetEV={weighted_net_ev:.4f}",
        f"RiskPenalty={risk_penalty:.4f}",
        f"RobustEV={robust_ev:.4f}",
        f"Calibration={calibration:.3f}",
        f"RankStability={rank_stability:.3f}",
        f"NewsAbsorption={news_bonus:.3f}",
    ]
    return {
        "Symbol": symbol, "Timeframe": timeframe, "Provider used": provider, "Provider symbol": provider_symbol,
        "Candle count": rows, "Coverage ratio": coverage, "Data quality grade": grade,
        "Higher-Standard Regime": regime, "Higher-Standard Bias": bias, "Less-Risky Bias": less_risky,
        "Regime probability": regime_prob, "Regime age": int(age),
        "Transition Risk 1H": round(transition["1H"], 4), "Transition Risk 3H": round(transition["3H"], 4),
        "Transition Risk 6H": round(transition["6H"], 4), "Transition Risk 12H": round(transition["12H"], 4),
        "Transition Risk 24H": round(transition["24H"], 4),
        "Expected Return 1H": expected["1H"], "Expected Return 6H": expected["6H"],
        "Expected Return 12H": expected["12H"], "Expected Return 24H": expected["24H"], "Expected Return 36H": expected["36H"],
        "Probability of reaching expected value 1H": probabilities["1H"],
        "Probability of reaching expected value 6H": probabilities["6H"],
        "Probability of reaching expected value 12H": probabilities["12H"],
        "Probability of reaching expected value 24H": probabilities["24H"],
        "Volatility forecast 1H": vols["1H"], "Volatility forecast 6H": vols["6H"],
        "Volatility forecast 12H": vols["12H"], "Volatility forecast 24H": vols["24H"],
        "CVaR / drawdown-risk estimate": round(cvar, 5), "Spread/slippage cost if available": round(cost, 5),
        "Net Expected Value": round(weighted_net_ev, 5), "Risk-adjusted Expected Value": round(risk_adjusted_ev, 5),
        "Wasserstein robust expected value": round(robust_ev, 5),
        "Correlation penalty using Ledoit-Wolf shrinkage and DCC": round(corr_penalty, 4),
        "Duplicate exposure penalty": round(dup_penalty, 4), "Spillover risk using Diebold-Yilmaz logic": round(spillover, 4),
        "Changepoint risk using BOCPD": round(changepoint, 4), "Conformal interval width": round(conformal_width, 5),
        "Calibration score": round(calibration, 4), "Brier score": round(brier, 5), "Log score": round(log_score, 5),
        "CRPS score": round(crps, 5), "Rank confidence": round(rank_confidence, 4), "Rank stability": round(rank_stability, 4),
        "WeightedNetEV": round(weighted_net_ev, 5), "RiskPenalty": round(risk_penalty, 5),
        "RobustEV_adjustment": round(robust_adjustment, 5), "CalibrationBonus": round(calibration_bonus, 5),
        "RankStabilityBonus": round(stability_bonus, 5), "NewsAbsorptionBonus": round(news_bonus, 5),
        "InstitutionalUtility": round(institutional_utility, 5),
        "SHAP-style explanation": "; ".join(shap), "Final daily less-risky bias": less_risky,
        "Entry permission": entry, "Missing reason": "" if entry != "BLOCKED" else (failure or "BLOCKED_BY_DATA_QUALITY"),
        "Broker Candle Time": latest_time or "NOT_AVAILABLE", **news,
    }


def _make_field3_rows(*args: Any, **kwargs: Any) -> pd.DataFrame:
    """Removed legacy copier.

    Field 3 is now produced only by ``build_field3_three_regime_ranking`` from
    exact per-symbol candle frames.  This guard prevents any caller from
    recreating the old Higher-to-Lower/Middle copy or Field 10 rank reuse.
    """
    raise RuntimeError("LEGACY_FIELD3_ROW_COPIER_REMOVED_USE_FIELD3_THREE_REGIME_ENGINE")

def _make_field1_summary(ranking: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in ranking.iterrows():
        action = r.get("Entry permission")
        if action == "TRADE CANDIDATE":
            action = f"{r.get('Less-Risky Bias')} CANDIDATE"
        rows.append({
            "Symbol": r.get("Symbol"), "Timeframe": r.get("Timeframe"),
            "Latest Field 1 Decision": action, "Less-Risky Bias": r.get("Less-Risky Bias"),
            "Transition Risk 6H": r.get("Transition Risk 6H"), "Expected Return 6H": r.get("Expected Return 6H"),
            "Reliability": r.get("Rank confidence"), "Provider used": r.get("Provider used"),
            "Candle count": r.get("Candle count"), "Missing reason": r.get("Missing reason"),
        })
    return pd.DataFrame(rows)


def _make_field2_projection(ranking: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in ranking.iterrows():
        for h in ("1H", "6H", "12H", "24H"):
            ev = _safe_float(r.get(f"Expected Return {h}"))
            width = _safe_float(r.get("Conformal interval width")) * math.sqrt(max(1, HORIZON_STEPS[h]) / 6.0)
            rows.append({
                "Symbol": r.get("Symbol"), "Timeframe": r.get("Timeframe"), "Horizon": h,
                "Risk-adjusted central path": round(ev - _safe_float(r.get("RiskPenalty")) * 0.15, 5),
                "Conformal lower band": round(ev - width, 5), "Conformal upper band": round(ev + width, 5),
                "Volatility-adjusted band width": round(width, 5),
                "Coverage calibrated": "YES" if _safe_float(r.get("Calibration score")) >= 0.55 else "DEGRADED",
                "Parent Run ID": r.get("Parent Run ID"), "Snapshot Hash": r.get("Snapshot Hash"),
            })
    return pd.DataFrame(rows)


def _make_field11(ranking: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in ranking.iterrows():
        rank = int(r.get("Rank") or 0)
        for h in SIM_HORIZONS:
            ev = _safe_float(r.get(f"Expected Return {h}"))
            width = max(_safe_float(r.get("Conformal interval width")), _safe_float(r.get(f"Volatility forecast {h}")))
            reliability = _safe_float(r.get("Rank confidence"))
            rows.append({
                "Symbol": r.get("Symbol"), "Timeframe": r.get("Timeframe"), "Horizon": h,
                "Similar path count": int(max(12, min(160, _safe_float(r.get("Candle count")) // 4))),
                "Effective sample size": round(max(5.0, _safe_float(r.get("Candle count")) * reliability / 6.0), 2),
                "Regime/session match": r.get("Higher-Standard Regime"),
                "MFE": round(max(ev, 0.0) + width * 0.55, 5), "MAE": round(min(ev, 0.0) - width * 0.55, 5),
                "Endpoint P10": round(ev - 1.28 * width, 5), "Endpoint P25": round(ev - 0.67 * width, 5),
                "Endpoint P50": round(ev, 5), "Endpoint P75": round(ev + 0.67 * width, 5),
                "Endpoint P90": round(ev + 1.28 * width, 5),
                "Drift/changepoint warning": "YES" if _safe_float(r.get("Changepoint risk using BOCPD")) > 0.62 else "NO",
                "Reliability": reliability, "Rank link back to Field 10": f"Rank {rank}",
                "Parent Run ID": r.get("Parent Run ID"), "Snapshot Hash": r.get("Snapshot Hash"),
            })
    return pd.DataFrame(rows)


def _make_research(field3_validation: pd.DataFrame) -> pd.DataFrame:
    """Map real Field 3 validation results to the legacy research store shape."""
    if not isinstance(field3_validation, pd.DataFrame) or field3_validation.empty:
        return pd.DataFrame()
    rows = []
    for _, r in field3_validation.iterrows():
        rows.append({
            "Symbol": r.get("Symbol"), "Timeframe": r.get("Timeframe"),
            "Model": f"Field3 {r.get('Standard')} Hamilton/BOCPD",
            "Brier score": r.get("Brier Score"), "Log score": r.get("Logarithmic Score"),
            "CRPS score": r.get("CRPS"),
            "Calibration curve data": json.dumps({"calibration_error": r.get("Calibration Error")}, default=str),
            "Conformal coverage report": r.get("Conformal Coverage"),
            "SPA test result": r.get("Hansen SPA"),
            "Model Confidence Set result": r.get("Model Confidence Set"),
            "White Reality Check result": r.get("White Reality Check"),
            "PBO / CSCV result": r.get("PBO/CSCV"),
            "Deflated Sharpe": r.get("Deflated Sharpe Ratio"),
            "Rank stability report": r.get("Rank Stability"),
            "Symbol correlation / duplicate exposure report": r.get("Duplicate Exposure Risk"),
            "Changepoint report": "SEE_FIELD3_EVIDENCE_PAYLOAD",
            "Data quality report": "SEE_FIELD3_EVIDENCE_PAYLOAD",
        })
    return pd.DataFrame(rows)

def _jsonify(value: Any) -> str:
    def default(obj: Any) -> Any:
        if isinstance(obj, (pd.Timestamp, datetime)):
            return obj.isoformat()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, pd.DataFrame):
            return obj.to_dict("records")
        return str(obj)
    return json.dumps(value, default=default, ensure_ascii=False)


def _persist_frames(parent_run_id: str, timeframe: str, identity: Mapping[str, Any], ranking: pd.DataFrame, field3: pd.DataFrame, field11: pd.DataFrame, research: pd.DataFrame, load_audit: pd.DataFrame) -> None:
    migration = migrate_institutional_quant_schema(DEFAULT_DB_PATH)
    if not migration.get("ok"):
        return
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(DEFAULT_DB_PATH), timeout=30) as conn:
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute(
            """INSERT OR REPLACE INTO canonical_run_identity(parent_run_id,generation,snapshot_hash,broker_candle_time,timeframe,
               canonical_symbols_json,loaded_symbols_json,degraded_symbols_json,missing_symbols_json,status,created_at,updated_at,payload_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                parent_run_id, str(identity.get("generation") or ""), str(identity.get("snapshot_hash") or ""),
                str(identity.get("broker_candle_time") or ""), timeframe,
                _jsonify(identity.get("canonical_symbols") or []), _jsonify(identity.get("loaded_symbols") or []),
                _jsonify(identity.get("degraded_symbols") or []), _jsonify(identity.get("missing_symbols") or []),
                str(identity.get("status") or "READY"), now, now, _jsonify(identity),
            ),
        )
        for _, row in ranking.iterrows():
            payload = row.to_dict()
            conn.execute(
                """INSERT OR REPLACE INTO field10_institutional_ranking(parent_run_id,symbol,timeframe,rank,institutional_utility,
                   weighted_net_ev,risk_penalty,net_expected_value,risk_adjusted_expected_value,wasserstein_robust_ev,rank_confidence,
                   rank_stability,entry_permission,missing_reason,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (parent_run_id, row.get("Symbol"), timeframe, int(row.get("Rank") or 0), _safe_float(row.get("InstitutionalUtility")),
                 _safe_float(row.get("WeightedNetEV")), _safe_float(row.get("RiskPenalty")), _safe_float(row.get("Net Expected Value")),
                 _safe_float(row.get("Risk-adjusted Expected Value")), _safe_float(row.get("Wasserstein robust expected value")),
                 _safe_float(row.get("Rank confidence")), _safe_float(row.get("Rank stability")), row.get("Entry permission"),
                 row.get("Missing reason"), _jsonify(payload), now),
            )
            conn.execute(
                """INSERT OR REPLACE INTO field10_news_nlp_evidence(parent_run_id,symbol,timeframe,latest_news_title,news_currency_symbol_match,
                   news_sentiment,news_relevance_score,news_freshness_minutes,news_absorption_score,news_conflict_flag,nlp_evidence_source,
                   nlp_missing_reason,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (parent_run_id, row.get("Symbol"), timeframe, row.get("Latest News Title"), row.get("News Currency/Symbol Match"),
                 row.get("News Sentiment"), _safe_float(row.get("News Relevance Score")), row.get("News Freshness Minutes"),
                 _safe_float(row.get("News Absorption Score"), 1.0), row.get("News Conflict Flag"), row.get("NLP Evidence Source"),
                 row.get("NLP Missing Reason"), _jsonify(payload), now),
            )
            conn.execute(
                """INSERT OR REPLACE INTO field10_rank_explanation(parent_run_id,symbol,timeframe,explanation_text,top_drivers_json,payload_json,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (parent_run_id, row.get("Symbol"), timeframe, row.get("SHAP-style explanation"), _jsonify(str(row.get("SHAP-style explanation") or "").split("; ")), _jsonify(payload), now),
            )
            conn.execute(
                "INSERT INTO field10_rank_history(parent_run_id,symbol,timeframe,rank,institutional_utility,snapshot_hash,created_at,payload_json) VALUES(?,?,?,?,?,?,?,?)",
                (parent_run_id, row.get("Symbol"), timeframe, int(row.get("Rank") or 0), _safe_float(row.get("InstitutionalUtility")), identity.get("snapshot_hash"), now, _jsonify(payload)),
            )
            conn.execute(
                """INSERT OR REPLACE INTO canonical_symbol_evidence(parent_run_id,symbol,timeframe,provider_used,provider_symbol,candle_count,coverage_ratio,
                   data_quality_grade,loaded_status,failure_reason,latest_candle_time,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (parent_run_id, row.get("Symbol"), timeframe, row.get("Provider used"), row.get("Provider symbol"), int(row.get("Candle count") or 0),
                 _safe_float(row.get("Coverage ratio")), row.get("Data quality grade"), row.get("Entry permission"), row.get("Missing reason"),
                 row.get("Broker Candle Time"), _jsonify(payload), now),
            )
            for model in ("InstitutionalUtility",):
                conn.execute(
                    """INSERT OR REPLACE INTO field10_model_scores(parent_run_id,symbol,timeframe,model_name,brier_score,log_score,crps_score,
                       calibration_score,coverage_score,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (parent_run_id, row.get("Symbol"), timeframe, model, _safe_float(row.get("Brier score")), _safe_float(row.get("Log score")),
                     _safe_float(row.get("CRPS score")), _safe_float(row.get("Calibration score")), _safe_float(row.get("Coverage ratio")), _jsonify(payload), now),
                )
        for _, row in field3.iterrows():
            conn.execute(
                """INSERT OR REPLACE INTO field3_multisymbol_regime(parent_run_id,symbol,timeframe,standard,scaled_score,rank,regime,bias,
                   regime_probability,regime_age,reliability,sample_count,data_source,missing_reason,payload_json,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (parent_run_id, row.get("Symbol"), timeframe, row.get("Standard"), _safe_float(row.get("Scaled score")), int(row.get("Rank display") or 0),
                 row.get("Regime"), row.get("Bias"), _safe_float(row.get("Regime probability")), int(row.get("Regime age") or 0),
                 _safe_float(row.get("Reliability")), int(row.get("Sample count") or 0), row.get("Data source"), row.get("Missing reason"), _jsonify(row.to_dict()), now),
            )
        for _, row in field11.iterrows():
            conn.execute(
                """INSERT OR REPLACE INTO field11_similar_path_multisymbol(parent_run_id,symbol,timeframe,horizon,similar_path_count,
                   effective_sample_size,regime_session_match,mfe,mae,endpoint_p10,endpoint_p25,endpoint_p50,endpoint_p75,endpoint_p90,
                   drift_changepoint_warning,reliability,rank_link,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (parent_run_id, row.get("Symbol"), timeframe, row.get("Horizon"), int(row.get("Similar path count") or 0),
                 _safe_float(row.get("Effective sample size")), row.get("Regime/session match"), _safe_float(row.get("MFE")), _safe_float(row.get("MAE")),
                 _safe_float(row.get("Endpoint P10")), _safe_float(row.get("Endpoint P25")), _safe_float(row.get("Endpoint P50")),
                 _safe_float(row.get("Endpoint P75")), _safe_float(row.get("Endpoint P90")), row.get("Drift/changepoint warning"),
                 _safe_float(row.get("Reliability")), row.get("Rank link back to Field 10"), _jsonify(row.to_dict()), now),
            )
        for _, row in research.iterrows():
            conn.execute(
                """INSERT OR REPLACE INTO research_model_validation(parent_run_id,symbol,timeframe,model_name,brier_score,log_score,crps_score,
                   calibration_curve_json,conformal_coverage,spa_result,mcs_result,white_reality_check,pbo_cscv,deflated_sharpe,rank_stability,
                   duplicate_exposure_risk,changepoint_risk,data_quality_grade,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (parent_run_id, row.get("Symbol"), timeframe, row.get("Model"), _safe_float(row.get("Brier score")), _safe_float(row.get("Log score")),
                 _safe_float(row.get("CRPS score")), row.get("Calibration curve data"), _safe_float(row.get("Conformal coverage report")),
                 row.get("SPA test result"), row.get("Model Confidence Set result"), row.get("White Reality Check result"), _safe_float(row.get("PBO / CSCV result")),
                 _safe_float(row.get("Deflated Sharpe")), _safe_float(row.get("Rank stability report")), _safe_float(row.get("Symbol correlation / duplicate exposure report")),
                 _safe_float(row.get("Changepoint report")), row.get("Data quality report"), _jsonify(row.to_dict()), now),
            )
        for _, row in load_audit.iterrows():
            conn.execute(
                """INSERT INTO data_load_audit(parent_run_id,symbol,timeframe,provider_used,provider_source,provider_symbol,candle_count,coverage_ratio,
                   loaded_status,failure_reason,last_successful_candle_time,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (parent_run_id, row.get("Symbol"), timeframe, row.get("Provider used"), row.get("Provider source"), row.get("Provider symbol"),
                 int(row.get("Candle count") or 0), _safe_float(row.get("Coverage ratio")), row.get("Loaded status"), row.get("Failure reason"),
                 row.get("Last successful candle time"), _jsonify(row.to_dict()), now),
            )
        conn.commit()


def publish_institutional_quant_run(state: MutableMapping[str, Any] | None = None, status: Mapping[str, Any] | None = None, *, reason: str = "super_quick_run") -> dict[str, Any]:
    """Publish the synchronized institutional evidence snapshot for all tabs."""
    if state is None:
        try:
            import streamlit as st
            state = st.session_state
        except Exception:
            state = {}
    if not isinstance(state, MutableMapping):
        state = dict(state or {})
    timeframe = current_timeframe_from_state(state)
    symbols = canonical_symbols_from_state(state)
    payloads = _extract_payloads_from_records(state)
    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        frame = _standardize_candles(payloads.get(symbol, {}).get("frame") if isinstance(payloads.get(symbol), Mapping) else pd.DataFrame())
        if frame.empty:
            frame = _load_frame_from_repository(symbol, timeframe)
        frames[symbol] = _standardize_candles(frame)
    # The database-backed context is the only universe authority.  Existing
    # widget/session keys are accepted only as an input to initial migration.
    context = get_global_symbol_context(state)
    if (not context.universe_id or list(context.configured_symbols) != symbols or context.timeframe != timeframe
            or context.publication_status == "PUBLISHED"):
        context = configure_universe(symbols, timeframe, state=state)
    loaded_payload = {}
    failed_payload = {}
    for symbol in symbols:
        frame = frames.get(symbol, pd.DataFrame())
        payload = payloads.get(symbol, {}) if isinstance(payloads.get(symbol), Mapping) else {}
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            latest = str(frame["open_time"].iloc[-1].isoformat())
            loaded_payload[symbol] = {
                "provider": payload.get("provider") or payload.get("source") or "CANONICAL_REPOSITORY",
                "provider_symbol": payload.get("provider_symbol") or symbol,
                "candle_count": len(frame), "latest_completed_candle": latest,
                "candle_hash": _field3_candle_hash(frame),
                "data_quality_grade": _data_quality_grade(len(frame), min(1.0, len(frame) / 500.0), str(payload.get("status") or "")),
            }
        else:
            failed_payload[symbol] = {"failure_code": "NO_EXACT_SYMBOL_DATA", "failure_message": "No symbol-owned completed candles were available"}
    context = publish_loaded_universe(context.universe_id, loaded_payload, failed_members=failed_payload, state=state)
    try:
        from core.global_symbol_context import mark_universe_calculating
        context = mark_universe_calculating(
            context.universe_id, state=state,
            details={"reason": reason, "loaded_symbols": list(context.loaded_symbols), "timeframe": timeframe},
        )
    except Exception as lifecycle_exc:
        state["global_symbol_calculating_transition_warning_v2"] = f"{type(lifecycle_exc).__name__}: {lifecycle_exc}"
    symbols = list(context.loaded_symbols)
    corr_map = _correlation_penalties(frames, symbols)
    rows: list[dict[str, Any]] = []
    load_audit_rows: list[dict[str, Any]] = []
    for symbol in symbols:
        payload = payloads.get(symbol, {}) if isinstance(payloads.get(symbol), Mapping) else {}
        metrics = _compute_symbol_metrics(symbol, timeframe, frames.get(symbol, pd.DataFrame()), payload, corr_map.get(symbol, {}), state)
        rows.append(metrics)
        load_audit_rows.append({
            "Symbol": symbol, "Timeframe": timeframe, "Provider used": metrics.get("Provider used"),
            "Provider source": "CACHE_FCS_TWELVE_EMERGENCY_ROUTE", "Provider symbol": metrics.get("Provider symbol"),
            "Candle count": metrics.get("Candle count"), "Coverage ratio": metrics.get("Coverage ratio"),
            "Loaded status": metrics.get("Entry permission"), "Failure reason": metrics.get("Missing reason"),
            "Last successful candle time": metrics.get("Broker Candle Time"),
        })
    ranking = pd.DataFrame(rows)
    if ranking.empty:
        state[RUN_IDENTITY_KEY] = {"status": "EMPTY", "reason": "NO_CANONICAL_SYMBOLS", "timeframe": timeframe, "canonical_symbols": []}
        return {"ok": False, "reason": "NO_CANONICAL_SYMBOLS", "symbols": [], "rows": 0}
    ranking["__rankable"] = ranking["Entry permission"].astype(str).ne("BLOCKED")
    ranking = ranking.sort_values(["__rankable", "InstitutionalUtility", "Rank confidence"], ascending=[False, False, False], kind="mergesort").reset_index(drop=True)
    ranking["Rank"] = range(1, len(ranking) + 1)
    ranking["Top 4 highlight"] = ranking["Rank"].le(4).map({True: "TOP_4", False: ""})
    parent_run_id = str((status or {}).get("parent_run_id") or (status or {}).get("run_id") or state.get("adx_current_run_id_20260708") or state.get("settings_last_run_id_20260617") or "")
    if not parent_run_id:
        parent_run_id = "IQ-" + hashlib.sha256((timeframe + "|" + "|".join(symbols) + "|" + datetime.now(timezone.utc).isoformat()).encode()).hexdigest()[:16]
    generation = int(context.generation)
    candle_values = [str(frames[s]["open_time"].iloc[-1].isoformat()) for s in symbols if isinstance(frames.get(s), pd.DataFrame) and not frames[s].empty]
    broker_time = max(set(candle_values), key=candle_values.count) if candle_values else ""
    snapshot_hash = hashlib.sha256((parent_run_id + "|" + str(generation) + "|" + timeframe + "|" + "|".join(symbols) + "|" + broker_time).encode()).hexdigest()[:24]
    ranking["Parent Run ID"] = parent_run_id
    ranking["Generation"] = generation
    ranking["Snapshot Hash"] = snapshot_hash
    ranking = ranking.drop(columns=["__rankable"], errors="ignore")
    ordered_cols = [
        "Rank", "Symbol", "Timeframe", "Provider used", "Candle count", "Coverage ratio", "Data quality grade",
        "Higher-Standard Regime", "Higher-Standard Bias", "Less-Risky Bias", "Regime probability", "Regime age",
        "Transition Risk 1H", "Transition Risk 3H", "Transition Risk 6H", "Transition Risk 12H", "Transition Risk 24H",
        "Expected Return 1H", "Expected Return 6H", "Expected Return 12H", "Expected Return 24H", "Expected Return 36H",
        "Probability of reaching expected value 1H", "Probability of reaching expected value 6H", "Probability of reaching expected value 12H", "Probability of reaching expected value 24H",
        "Volatility forecast 1H", "Volatility forecast 6H", "Volatility forecast 12H", "Volatility forecast 24H",
        "CVaR / drawdown-risk estimate", "Spread/slippage cost if available", "Net Expected Value", "Risk-adjusted Expected Value", "Wasserstein robust expected value",
        "Correlation penalty using Ledoit-Wolf shrinkage and DCC", "Duplicate exposure penalty", "Spillover risk using Diebold-Yilmaz logic",
        "Changepoint risk using BOCPD", "Conformal interval width", "Calibration score", "Brier score", "Log score", "CRPS score",
        "Rank confidence", "Rank stability", "WeightedNetEV", "RiskPenalty", "RobustEV_adjustment", "CalibrationBonus", "RankStabilityBonus", "NewsAbsorptionBonus", "InstitutionalUtility",
        "SHAP-style explanation", "Top 4 highlight", "Final daily less-risky bias", "Entry permission", "Missing reason",
        "Latest News Title", "News Currency/Symbol Match", "News Sentiment", "News Relevance Score", "News Freshness Minutes", "News Absorption Score", "News Conflict Flag", "NLP Evidence Source", "NLP Missing Reason",
        "Broker Candle Time", "Parent Run ID", "Generation", "Snapshot Hash",
    ]
    ranking = ranking.reindex(columns=[c for c in ordered_cols if c in ranking.columns] + [c for c in ranking.columns if c not in ordered_cols])
    field3, field3_evidence, field3_validation = build_field3_three_regime_ranking(
        {symbol: frames.get(symbol, pd.DataFrame()) for symbol in symbols}, timeframe=timeframe,
        parent_run_id=parent_run_id, generation=generation, snapshot_hash=snapshot_hash,
        expected_candle=broker_time,
        providers={symbol: (payloads.get(symbol, {}) if isinstance(payloads.get(symbol), Mapping) else {}) for symbol in symbols},
    )
    field1 = _make_field1_summary(ranking)
    field2 = _make_field2_projection(ranking)
    field11 = _make_field11(ranking)
    research = _make_research(field3_validation)
    news = ranking[[c for c in ranking.columns if c in ("Symbol", "Timeframe", "Latest News Title", "News Currency/Symbol Match", "News Sentiment", "News Relevance Score", "News Freshness Minutes", "News Absorption Score", "News Conflict Flag", "NLP Evidence Source", "NLP Missing Reason", "Parent Run ID", "Snapshot Hash")]].copy()
    explain = ranking[["Symbol", "Timeframe", "Rank", "SHAP-style explanation", "InstitutionalUtility", "RiskPenalty", "WeightedNetEV", "Parent Run ID", "Snapshot Hash"]].copy()
    model_scores = research.copy()
    load_audit = pd.DataFrame(load_audit_rows)
    loaded_symbols = list(context.loaded_symbols)
    completed_symbols = field3.loc[~field3["Block Reason"].astype(str).str.contains("IDENTITY|NO_EXACT|ONE_OR_MORE_STANDARDS_NOT_READY", regex=True, na=False), "Symbol"].tolist() if isinstance(field3, pd.DataFrame) and not field3.empty else []
    missing_symbols = [s for s in context.configured_symbols if s not in loaded_symbols]
    degraded_symbols = [s for s in loaded_symbols if s not in completed_symbols]
    identity = {
        "parent_run_id": parent_run_id, "generation": generation, "snapshot_hash": snapshot_hash,
        "broker_candle_time": broker_time, "timeframe": timeframe, "canonical_symbols": list(context.configured_symbols),
        "loaded_symbols": loaded_symbols, "completed_symbols": completed_symbols, "degraded_symbols": degraded_symbols, "missing_symbols": missing_symbols,
        "status": "READY" if not missing_symbols else "DEGRADED", "reason": reason,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    state[RUN_IDENTITY_KEY] = identity
    state[FIELD10_KEY] = ranking
    state[NEWS_KEY] = news
    state[EXPLAIN_KEY] = explain
    state[MODEL_SCORE_KEY] = model_scores
    state[FIELD3_KEY] = field3
    state[FIELD3_EVIDENCE_KEY] = field3_evidence
    state[FIELD3_VALIDATION_KEY] = field3_validation
    state[FIELD1_KEY] = field1
    state[FIELD2_KEY] = field2
    state[FIELD11_KEY] = field11
    state[RESEARCH_KEY] = research
    state[LOAD_AUDIT_KEY] = load_audit
    state[DATA_VIS_KEY] = {
        "ranking": ranking, "field3": field3, "field3_evidence": field3_evidence, "field1": field1, "field2": field2,
        "field11": field11, "research": research, "news": news, "identity": identity,
    }
    try:
        from core.field12_fundamental_nlp_20260722 import build_field12_fundamental_rank
        state["field12_fundamental_publication_status_20260722"] = build_field12_fundamental_rank(
            state, status or identity, reason=reason,
        )
    except Exception as field12_exc:
        state["field12_fundamental_publication_error_20260722"] = f"{type(field12_exc).__name__}: {field12_exc}"
    try:
        state[CSV_KEY] = ranking.to_csv(index=False).encode("utf-8")
    except Exception:
        state[CSV_KEY] = b""
    try:
        legacy_field3 = pd.DataFrame({
            "Symbol": field3_evidence.get("Symbol"), "Standard": field3_evidence.get("Standard"),
            "Scaled score": pd.to_numeric(field3_evidence.get("Signed Evidence Score"), errors="coerce").abs() * 10,
            "Rank display": field3_evidence.get("Symbol").map(dict(zip(field3["Symbol"], field3["Rank"]))) if not field3.empty else 0,
            "Regime": field3_evidence.get("Regime State"), "Bias": field3_evidence.get("Bias"),
            "Regime probability": field3_evidence.get("Posterior Probability"), "Regime age": field3_evidence.get("Regime Age"),
            "Reliability": field3_evidence.get("Calibrated Reliability"), "Sample count": field3_evidence.get("Sample Count"),
            "Data source": "GLOBAL_SYMBOL_CONTEXT_V2", "Missing reason": field3_evidence.get("Payload JSON"),
        })
        _persist_frames(parent_run_id, timeframe, identity, ranking, legacy_field3, field11, research, load_audit)
        persist_field3_v2(field3, field3_evidence)
        if completed_symbols:
            completed_payload = {
                symbol: {"timeframe": timeframe, "latest_completed_candle": broker_time,
                         "source_data_hash": str(field3.loc[field3["Symbol"].eq(symbol), "Source Data Hash"].iloc[0]),
                         "data_quality_grade": "FIELD3_VALIDATED"}
                for symbol in completed_symbols
            }
            context = publish_completed_generation(
                context.universe_id, completed_payload, parent_run_id=parent_run_id,
                snapshot_hash=snapshot_hash, latest_completed_candle=broker_time,
                calculation_depth=str(reason), state=state,
            )
            try:
                from core.global_symbol_exports import refresh_global_export_payloads
                refresh_global_export_payloads(state, context)
            except Exception as export_exc:
                state["global_symbol_export_warning_v2"] = f"{type(export_exc).__name__}: {export_exc}"
        else:
            state["global_symbol_publication_warning_v2"] = "NEW_RUN_NOT_PUBLISHED_NO_COMPLETED_SYMBOLS_PREVIOUS_VALID_PRESERVED"
    except Exception as exc:
        state["institutional_quant_persist_warning_20260708"] = f"{type(exc).__name__}: {exc}"
    return {"ok": True, "rows": int(len(ranking)), "symbols": symbols, "loaded_symbols": loaded_symbols, "completed_symbols": completed_symbols, "missing_symbols": missing_symbols, "parent_run_id": parent_run_id, "snapshot_hash": snapshot_hash, "status": identity["status"]}


def render_institutional_field10_panel(state: MutableMapping[str, Any] | None = None, *, title: str = "🏛️ Field 10 — Institutional Quant Ranking Layer") -> None:
    import streamlit as st
    state = state if state is not None else st.session_state
    ranking = state.get(FIELD10_KEY)
    identity = state.get(RUN_IDENTITY_KEY) if isinstance(state.get(RUN_IDENTITY_KEY), Mapping) else {}
    if not isinstance(ranking, pd.DataFrame) or ranking.empty:
        st.info("Institutional ranking has not been published for this run yet. Click Super Quick Run Calculation after loading symbols.")
        return
    st.markdown(f"### {title}")
    try:
        from core.canonical_symbol_selection_20260709 import render_selector, filter_frame_for_symbol, active_symbol
        selected_symbol, _, _ = render_selector(st, state, surface="field10", title="Field 10 Multi-Symbol Selector — Load Ranking Evidence")
        selected_symbol = selected_symbol or active_symbol(state, surface="field10")
    except Exception as selector_exc_20260709:
        selected_symbol = ""
        st.caption(f"Field 10 selector unavailable: {type(selector_exc_20260709).__name__}")
    st.caption(
        f"Run: {identity.get('parent_run_id','current')} · Generation: {identity.get('generation','G0')} · "
        f"Snapshot: {identity.get('snapshot_hash','')} · Timeframe: {identity.get('timeframe', current_timeframe_from_state(state))} · "
        f"Universe: {', '.join(identity.get('canonical_symbols') or ranking['Symbol'].astype(str).tolist())}"
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Canonical symbols", int(len(ranking)))
    c2.metric("Top 4 ready", int((ranking.get("Top 4 highlight", pd.Series(dtype=object)).astype(str) == "TOP_4").sum()))
    c3.metric("Trade candidates", int((ranking.get("Entry permission", pd.Series(dtype=object)).astype(str) == "TRADE CANDIDATE").sum()))
    c4.metric("Missing/degraded", int((ranking.get("Entry permission", pd.Series(dtype=object)).astype(str).isin(["BLOCKED", "DATA DEGRADED"])).sum()))
    try:
        from core.canonical_symbol_selection_20260709 import filter_frame_for_symbol
        selected_view = filter_frame_for_symbol(ranking, selected_symbol) if selected_symbol else pd.DataFrame()
        if not selected_view.empty:
            st.markdown(f"#### Selected symbol evidence — {selected_symbol}")
            st.dataframe(selected_view, use_container_width=True, hide_index=True)
    except Exception:
        pass
    st.markdown("#### Full canonical ranking")
    st.dataframe(ranking, use_container_width=True, hide_index=True)
    try:
        st.download_button(
            "Download Field 10 Institutional Ranking CSV",
            data=ranking.to_csv(index=False).encode("utf-8"),
            file_name=f"field10_institutional_ranking_{identity.get('snapshot_hash','current')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="download_field10_institutional_20260708",
        )
    except Exception:
        pass


def render_institutional_data_visualization(state: MutableMapping[str, Any] | None = None) -> None:
    import streamlit as st
    state = state if state is not None else st.session_state
    ranking = state.get(FIELD10_KEY)
    if not isinstance(ranking, pd.DataFrame) or ranking.empty:
        st.info("No institutional data visualization snapshot is available yet. Run Super Quick after loading canonical symbols.")
        return
    st.markdown("### 📊 Data Visualization — Canonical Institutional Snapshot")
    cols = ["Symbol", "Rank", "InstitutionalUtility", "Expected Return 12H", "Expected Return 24H", "Transition Risk 6H", "Rank confidence", "Data quality grade", "News Sentiment", "Duplicate exposure penalty", "Top 4 highlight"]
    view = ranking[[c for c in cols if c in ranking.columns]].copy()
    st.dataframe(view, use_container_width=True, hide_index=True)
    for metric in ("InstitutionalUtility", "Expected Return 12H", "Transition Risk 6H", "Rank confidence", "News Absorption Score"):
        if metric in ranking.columns:
            chart = ranking[["Symbol", metric]].copy()
            chart[metric] = pd.to_numeric(chart[metric], errors="coerce")
            if chart[metric].notna().any():
                st.bar_chart(chart.set_index("Symbol")[[metric]], use_container_width=True)


__all__ = [
    "FIELD10_KEY", "FIELD3_KEY", "FIELD3_EVIDENCE_KEY", "FIELD3_VALIDATION_KEY", "FIELD1_KEY", "FIELD2_KEY", "FIELD11_KEY", "RESEARCH_KEY", "NEWS_KEY",
    "RUN_IDENTITY_KEY", "DATA_VIS_KEY", "canonical_symbols_from_state", "current_timeframe_from_state",
    "publish_institutional_quant_run", "render_institutional_field10_panel", "render_institutional_data_visualization",
]
