"""ONE shared target-price function for the 2026-10-09 exit work.

Formulas (verified against the app):
    pip      = 0.01 for JPY quotes, 0.0001 otherwise
               (core/live_execution.py :: pip_size, lines 60-61;
                core/monthly_backtest.py :: make_tapes — identical rule)
    BUY:  TP = entry + TP_pips x pip ;  SL = entry - SL_pips x pip
    SELL: TP = entry - TP_pips x pip ;  SL = entry + SL_pips x pip
               (mirrors core/live_execution.py :: target_display_columns)

ATR distances are computed from pre-admission information and frozen at
entry: an admitted position's identity + exits freeze until closure, including
across month changes. Nothing in this module re-prices a live position.

Price-basis labelling (never label an indicative price as executable):
    INDICATIVE    — priced from a completed H1 candle (display / research)
    RESEARCH FILL — the next H1 open used as the replay fill
    EXECUTABLE    — an actual broker bid/ask quote with evidence
"""
from __future__ import annotations

import math

BASIS_LABELS = {
    "INDICATIVE": "INDICATIVE (completed candle)",
    "RESEARCH_FILL": "RESEARCH FILL (next H1 open)",
    "EXECUTABLE": "EXECUTABLE (broker bid/ask)",
}


def pip_size(symbol: str) -> float:
    """Pip size convention, verified from app code.

    core/live_execution.py :: pip_size: ``.01 if symbol endswith 'JPY' else .0001``
    core/monthly_backtest.py :: make_tapes: identical rule.
    """
    return 0.01 if str(symbol).upper().endswith("JPY") else 0.0001


def _side_sign(side) -> int:
    if side in (1, "BUY", "buy", "Buy"):
        return 1
    if side in (-1, "SELL", "sell", "Sell"):
        return -1
    raise ValueError(f"side must be +1/'BUY' or -1/'SELL', got {side!r}")


def target_prices(entry_price: float, side, tp_pips: float, sl_pips: float,
                  symbol: str, *, price_basis: str = "INDICATIVE",
                  decimals: int | None = None) -> dict:
    """Compute TP/SL target prices from pip distances. Raises ValueError with
    a clear message on any invalid input instead of returning a wrong target.
    """
    s = _side_sign(side)
    for name, value in (("entry_price", entry_price), ("tp_pips", tp_pips), ("sl_pips", sl_pips)):
        v = float(value)
        if not math.isfinite(v):
            raise ValueError(f"{name} must be finite, got {value!r}")
        if name == "entry_price" and v <= 0:
            raise ValueError(f"entry_price must be positive, got {v}")
        if name in ("tp_pips", "sl_pips") and v <= 0:
            raise ValueError(f"{name} must be positive, got {v}")
    entry, tp, sl = float(entry_price), float(tp_pips), float(sl_pips)
    if price_basis not in BASIS_LABELS:
        raise ValueError(f"price_basis must be one of {sorted(BASIS_LABELS)}, got {price_basis!r}")
    pip = pip_size(symbol)
    tp_price = entry + s * tp * pip
    sl_price = entry - s * sl * pip
    # Ordering validation: TP must be favourable, SL adverse, relative to side.
    if s == 1 and not (tp_price > entry > sl_price):
        raise ValueError(f"BUY ordering violated: TP {tp_price} / entry {entry} / SL {sl_price}")
    if s == -1 and not (tp_price < entry < sl_price):
        raise ValueError(f"SELL ordering violated: TP {tp_price} / entry {entry} / SL {sl_price}")
    out = {
        "entry_price": entry,
        "side": "BUY" if s == 1 else "SELL",
        "tp_pips": tp,
        "sl_pips": sl,
        "pip_size": pip,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "price_basis": price_basis,
        "price_basis_label": BASIS_LABELS[price_basis],
        "frozen_at_entry": True,
    }
    if decimals is not None:
        out["tp_price"] = round(tp_price, decimals)
        out["sl_price"] = round(sl_price, decimals)
    return out
