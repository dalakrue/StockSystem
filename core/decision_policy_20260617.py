"""One shared directional decision policy for all synchronized views.

This module does not add a prediction model. It reconciles existing regime,
price, reliability, quality and risk outputs so Lunch, Finder, PowerBI and AI
cannot apply conflicting BUY/SELL/WAIT/NO TRADE thresholds.
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd


def _number(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else float(default)
    except Exception:
        return float(default)


def infer_direction_from_regime(regime: Any, ohlc: Any = None) -> str:
    """Return BUY/SELL for explicit regimes and use existing H1 movement for generic expansion.

    Generic ``RANGE_EXPANSION`` is not automatically WAIT. The direction is
    derived from the latest existing close series, which fixes the stale
    WAIT/NO TRADE mismatch without introducing a new forecast engine.
    """
    text = str(regime or "").upper().replace("-", "_").replace(" ", "_")
    if any(token in text for token in ("BEAR", "DOWNTREND", "EXPANSION_DOWN", "DOWN_EXPANSION", "BEARISH")):
        return "SELL"
    if any(token in text for token in ("BULL", "UPTREND", "EXPANSION_UP", "UP_EXPANSION", "BULLISH")):
        return "BUY"

    if not isinstance(ohlc, pd.DataFrame) or ohlc.empty:
        return "WAIT"
    close_col = next((c for c in ohlc.columns if str(c).strip().lower() in {"close", "c"}), None)
    if close_col is None:
        return "WAIT"
    close = pd.to_numeric(ohlc[close_col], errors="coerce").dropna()
    if len(close) < 3:
        return "WAIT"

    # Blend the last bar, 3-bar and 6-bar movement. The threshold remains above
    # numerical noise but is intentionally lower than the previous WAIT-heavy gate.
    diffs = close.diff().dropna()
    noise = _number(diffs.abs().tail(24).median(), 0.0)
    last = _number(close.iloc[-1], 0.0)
    m1 = _number(close.iloc[-1] - close.iloc[-2], 0.0)
    m3 = _number(close.iloc[-1] - close.iloc[max(0, len(close) - 4)], 0.0)
    m6 = _number(close.iloc[-1] - close.iloc[max(0, len(close) - 7)], 0.0)
    weighted = (0.48 * m1) + (0.34 * m3) + (0.18 * m6)
    threshold = max(noise * 0.12, abs(last) * 0.000008)
    if weighted > threshold:
        return "BUY"
    if weighted < -threshold:
        return "SELL"
    # Expansion regimes should only remain WAIT when all recent movements are
    # genuinely flat; a clear 3/6-bar sign is enough to retain direction.
    if "EXPANSION" in text:
        fallback = m3 + (0.35 * m6)
        if fallback > 0:
            return "BUY"
        if fallback < 0:
            return "SELL"
    return "WAIT"


def reconcile_decision(
    direction: Any,
    existing: Any,
    reliability: Any,
    data_quality: Any,
    exit_risk_pct: Any,
) -> str:
    """Lower directional gates and reserve WAIT/NO TRADE for stronger evidence.

    The policy follows the user's requested calibration while retaining severe
    risk protection. It must be called by every synchronized result surface.
    """
    direction_text = str(direction or "").upper().strip()
    existing_text = str(existing or "").upper().strip()
    rel = max(0.0, min(100.0, _number(reliability, 50.0)))
    quality = max(0.0, min(100.0, _number(data_quality, 50.0)))
    risk = max(0.0, min(100.0, _number(exit_risk_pct, 50.0)))

    if direction_text in {"BUY", "SELL"} and rel >= 32.0 and quality >= 22.0 and risk < 91.0:
        return direction_text
    if existing_text in {"BUY", "SELL"} and rel >= 29.0 and quality >= 19.0 and risk < 91.0:
        return existing_text
    if risk >= 96.0 or rel < 17.0 or quality < 7.0:
        return "NO TRADE"
    return "WAIT"


DECISION_POLICY_TEXT = (
    "BUY/SELL: directional evidence + reliability>=32 + quality>=22 + risk<91; "
    "existing BUY/SELL retained at reliability>=29 + quality>=19; "
    "NO TRADE only for risk>=96, reliability<17, or quality<7."
)
