"""Shared helpers for Logic Safety Guard.

Additive safety wrapper only: no original prediction, regime, KNN, greedy,
PowerBI, NLP, or priority formulas are replaced here.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple
import math
import re


def clamp(value: Any, low: float = 0.0, high: float = 100.0, default: float = 0.0) -> float:
    try:
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return float(default)
        return max(float(low), min(float(high), x))
    except Exception:
        return float(default)


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def normalize_key(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _is_simple(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, type(None)))


def flatten_metrics(source: Any, prefix: str = "", depth: int = 0, limit: int = 1600) -> Dict[str, Any]:
    """Flatten simple scalars from dict-like/session state objects.

    DataFrames/lists are intentionally not expanded to keep phone performance safe.
    """
    out: Dict[str, Any] = {}
    if depth > 4 or len(out) > limit:
        return out
    try:
        items = source.items() if hasattr(source, "items") else []
    except Exception:
        items = []
    for k, v in list(items):
        if len(out) >= limit:
            break
        key = f"{prefix}.{k}" if prefix else str(k)
        if _is_simple(v):
            out[key] = v
        elif isinstance(v, dict):
            out.update(flatten_metrics(v, key, depth + 1, limit - len(out)))
        else:
            # Keep known compact object attributes out of performance-critical path.
            continue
    return out


def _tokens(candidate: str) -> List[str]:
    return [t for t in normalize_key(candidate).split() if t]


def find_number(metrics: Dict[str, Any], candidates: Iterable[str], default: float | None = None) -> float | None:
    scored: List[Tuple[int, str, float]] = []
    for key, value in metrics.items():
        val = safe_float(value, None)
        if val is None:
            continue
        key_norm = normalize_key(key)
        key_join = key_norm.replace(" ", "")
        for cand in candidates:
            toks = _tokens(cand)
            if not toks:
                continue
            exact_join = "".join(toks)
            if exact_join and exact_join in key_join:
                scored.append((100 + len(exact_join), key, val))
            elif all(t in key_norm for t in toks):
                scored.append((80 + len(toks), key, val))
            elif any(t in key_norm for t in toks) and len(toks) == 1:
                scored.append((40, key, val))
    if not scored:
        return default
    scored.sort(reverse=True)
    return scored[0][2]


def find_text(metrics: Dict[str, Any], candidates: Iterable[str], default: str = "Unknown") -> str:
    scored: List[Tuple[int, str, str]] = []
    for key, value in metrics.items():
        if value is None:
            continue
        if isinstance(value, (dict, list, tuple, set)):
            continue
        key_norm = normalize_key(key)
        key_join = key_norm.replace(" ", "")
        for cand in candidates:
            toks = _tokens(cand)
            exact_join = "".join(toks)
            if exact_join and exact_join in key_join:
                scored.append((100 + len(exact_join), key, str(value)))
            elif toks and all(t in key_norm for t in toks):
                scored.append((80 + len(toks), key, str(value)))
    if not scored:
        return default
    scored.sort(reverse=True)
    return scored[0][2]


def score_label(score: float) -> str:
    s = clamp(score)
    if s >= 90:
        return "Elite Logic Health"
    if s >= 80:
        return "Strong"
    if s >= 70:
        return "Good"
    if s >= 60:
        return "Caution"
    if s >= 40:
        return "Weak"
    return "Unsafe / Do Not Trust"


def danger_label(level: float) -> str:
    x = clamp(level)
    if x >= 85:
        return "Critical"
    if x >= 65:
        return "High"
    if x >= 35:
        return "Medium"
    return "Low"


def first_dataframe(session_state: Any):
    """Find a likely OHLC/history DataFrame in Streamlit session state."""
    try:
        import pandas as pd  # noqa
    except Exception:
        return None, "pandas unavailable"
    preferred = [
        "last_df", "df", "data", "ohlc", "current_df", "home_df", "lunch_df",
        "eurusd_df", "price_df", "history_df", "market_df",
    ]
    try:
        for key in preferred:
            obj = session_state.get(key, None)
            if _looks_like_dataframe(obj):
                return obj.copy(), key
        for key, obj in session_state.items():
            if _looks_like_dataframe(obj):
                return obj.copy(), str(key)
            if isinstance(obj, dict):
                for subkey, subobj in obj.items():
                    if _looks_like_dataframe(subobj):
                        return subobj.copy(), f"{key}.{subkey}"
    except Exception:
        pass
    return None, "no dataframe found"


def _looks_like_dataframe(obj: Any) -> bool:
    try:
        import pandas as pd
        return isinstance(obj, pd.DataFrame) and len(obj) > 0
    except Exception:
        return False


def normalize_ohlc(df):
    try:
        import pandas as pd
        import numpy as np
    except Exception:
        return None
    if df is None:
        return None
    x = df.copy()
    # common aliases
    aliases = {"timestamp": "time", "datetime": "time", "date": "time", "Close": "close", "Open": "open", "High": "high", "Low": "low", "Volume": "volume"}
    for a, b in aliases.items():
        if a in x.columns and b not in x.columns:
            x[b] = x[a]
    if "time" not in x.columns:
        x["time"] = pd.date_range(end=pd.Timestamp.now(), periods=len(x), freq="h")
    x["time"] = pd.to_datetime(x["time"], errors="coerce")
    for c in ["open", "high", "low", "close", "volume"]:
        if c in x.columns:
            x[c] = pd.to_numeric(x[c], errors="coerce")
    if "close" not in x.columns:
        # try first numeric column as close only for diagnostics, not prediction.
        nums = [c for c in x.columns if c != "time" and str(x[c].dtype) != "object"]
        if nums:
            x["close"] = pd.to_numeric(x[nums[0]], errors="coerce")
    if "open" not in x.columns and "close" in x.columns:
        x["open"] = x["close"].shift(1).fillna(x["close"])
    if "high" not in x.columns and "close" in x.columns:
        x["high"] = x[["open", "close"]].max(axis=1)
    if "low" not in x.columns and "close" in x.columns:
        x["low"] = x[["open", "close"]].min(axis=1)
    x = x.dropna(subset=["time"]).sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
    return x


def current_values(metrics: Dict[str, Any]) -> Dict[str, Any]:
    master = find_number(metrics, ["master score", "master_score"], 5.0)
    if master is not None and master <= 10:
        master *= 10
    regime_score = find_number(metrics, ["regime confidence", "regime score", "hmm bull", "hmm range"], 55.0)
    if regime_score is not None and regime_score <= 10:
        regime_score *= 10
    forecast = find_number(metrics, ["forecast agreement", "forecast confidence", "forecast score"], 60.0)
    if forecast is not None and forecast <= 10:
        forecast *= 10
    reliability = find_number(metrics, ["prediction reliability", "reliability", "direction accuracy", "accuracy"], 60.0)
    if reliability is not None and reliability <= 10:
        reliability *= 10
    market_quality = find_number(metrics, ["market quality", "tradeability", "quality", "master score"], master if master is not None else 55.0)
    if market_quality is not None and market_quality <= 10:
        market_quality *= 10
    exit_risk = find_number(metrics, ["exit risk", "risk score", "risk"], 45.0)
    if exit_risk is not None and exit_risk <= 10:
        exit_risk *= 10
    tp_quality = find_number(metrics, ["tp quality", "take profit quality", "tp score"], 55.0)
    if tp_quality is not None and tp_quality <= 10:
        tp_quality *= 10
    confidence = find_number(metrics, ["confidence", "bull probability", "forecast confidence"], forecast if forecast is not None else 60.0)
    if confidence is not None and confidence <= 10:
        confidence *= 10
    return {
        "master_score": clamp(master, default=50),
        "regime_confidence": clamp(regime_score, default=55),
        "forecast_agreement": clamp(forecast, default=60),
        "prediction_reliability": clamp(reliability, default=60),
        "market_quality": clamp(market_quality, default=55),
        "exit_risk": clamp(exit_risk, default=45),
        "tp_quality": clamp(tp_quality, default=55),
        "raw_confidence": clamp(confidence, default=60),
        "current_regime": find_text(metrics, ["current regime", "major regime", "regime"], "Unknown"),
        "original_decision": find_text(metrics, ["master decision", "final decision", "decision", "direction"], "Original decision unavailable"),
    }


def dataframe_to_csv_bytes(df) -> bytes:
    try:
        return df.to_csv(index=False).encode("utf-8")
    except Exception:
        return b""
