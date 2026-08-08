"""Session-conditioned EURUSD H1 outcome summaries."""
from __future__ import annotations
from collections import Counter
from typing import Any, Iterable, Mapping
import math

import pandas as pd

SESSIONS = (
    "Asia", "Pre-London", "London open", "London continuation",
    "London–New York overlap", "New York continuation", "Late New York",
    "News period", "Post-news normalization",
)


def _classify_utc(value: Any) -> str | None:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return None
    hour = int(timestamp.hour)
    if 0 <= hour < 6: return "Asia"
    if 6 <= hour < 7: return "Pre-London"
    if 7 <= hour < 9: return "London open"
    if 9 <= hour < 12: return "London continuation"
    if 12 <= hour < 16: return "London–New York overlap"
    if 16 <= hour < 20: return "New York continuation"
    return "Late New York"


def _rounded(value: Any, digits: int) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, digits) if math.isfinite(number) else None


def evaluate(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = [dict(row) for row in rows if isinstance(row, Mapping)]
    for row in records:
        if not row.get("session"):
            row["session"] = _classify_utc(row.get("actual_time") or row.get("settled_at") or row.get("broker_candle_time"))
    frame = pd.DataFrame(records)
    output: list[dict[str, Any]] = []
    for session in SESSIONS:
        subset = frame[frame.get("session", pd.Series(dtype=str)).astype(str).str.casefold() == session.casefold()] if not frame.empty and "session" in frame else pd.DataFrame()
        count = len(subset)
        accuracy = pd.to_numeric(subset.get("direction_correct"), errors="coerce").mean() * 100.0 if count and "direction_correct" in subset else None
        move = pd.to_numeric(subset.get("realized_pips"), errors="coerce").median() if count and "realized_pips" in subset else None
        tp_rate = pd.to_numeric(subset.get("target_hit"), errors="coerce").mean() * 100.0 if count and "target_hit" in subset else None
        spread = pd.to_numeric(subset.get("estimated_cost"), errors="coerce").mean() if count and "estimated_cost" in subset else None
        bias = pd.to_numeric(subset.get("residual"), errors="coerce").mean() if count and "residual" in subset else None
        best_horizon = None
        if count and {"horizon_hours", "direction_correct"} <= set(subset.columns):
            grouped = subset.groupby("horizon_hours")["direction_correct"].mean().dropna()
            if not grouped.empty:
                best_horizon = int(grouped.idxmax())
        models = [str(value) for value in subset.get("model_name", []) if str(value)] if count else []
        decisions = subset.get("decision", pd.Series(dtype=str)).astype(str).str.upper() if count else pd.Series(dtype=str)
        no_trade_rate = decisions.isin(["WAIT", "SKIP", "NO TRADE"]).mean() * 100.0 if len(decisions) else None
        output.append({
            "session": session,
            "direction_accuracy": _rounded(accuracy, 3),
            "median_move_pips": _rounded(move, 4),
            "tp_before_sl_rate": _rounded(tp_rate, 3),
            "average_spread": _rounded(spread, 4),
            "forecast_bias": _rounded(bias, 8),
            "best_horizon": best_horizon,
            "best_historical_model": Counter(models).most_common(1)[0][0] if models else None,
            "no_trade_rate": _rounded(no_trade_rate, 3),
            "sample_size": count,
            "status": "READY" if count >= 25 else "INSUFFICIENT EVIDENCE",
        })
    return output
