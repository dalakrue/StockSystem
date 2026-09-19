"""Regime-age efficiency bucket."""
from __future__ import annotations
from typing import Any


def evaluate(age: float, *, reliability: float, changepoint_probability: float) -> dict[str, Any]:
    if age <= 3:
        bucket = "1–3 H1 candles"
    elif age <= 8:
        bucket = "4–8 H1 candles"
    elif age <= 15:
        bucket = "9–15 H1 candles"
    else:
        bucket = "Above 15 H1 candles"
    continuation = max(0.0, min(100.0, reliability * (1.0 - changepoint_probability / 100.0)))
    reversal = 100.0 - continuation
    remaining = max(0.0, continuation - max(age - 12.0, 0.0) * 2.0)
    return {"bucket": bucket, "accuracy": None, "net_ev": None, "reversal_probability": round(reversal, 3), "trend_continuation_probability": round(continuation, 3), "remaining_edge": round(remaining, 3)}
