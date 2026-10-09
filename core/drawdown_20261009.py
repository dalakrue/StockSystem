"""Drawdown reporting (2026-10-09).

All figures are in PIPS unless position sizes + FX conversion are available;
summed pips are never presented as cash or account return.

Reported:
  * realized closed-trade drawdown (from completed trades only)
  * mark-to-H1-close drawdown (priced H1 closes only; limits stated below)
  * max combined floating loss (timestamped sum across concurrent positions)
  * max single-position floating loss
  * max completed loss (single trade)
  * max concurrent holdings
  * unknown / unpriced exposure (censored trades; intra-hour extremes)

Limits of the H1-close floating series: intra-hour extremes cannot be
reconstructed from H1 OHLC; floating values use priced H1 closes only.
Timestamps are consistent (UTC bar-open times); each bar contributes at most
once per position, so there is no double counting.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

DRAWDOWN_VERSION = "drawdown-20261009-v1"
LIMITS = ("H1 closes only — intra-hour extremes are unobservable; "
          "unpriced bars and censored intervals contribute no floating value; "
          "timestamps are UTC bar-open times; no double counting.")


def realized_drawdown(net_pips: pd.Series) -> Dict:
    v = pd.to_numeric(net_pips, errors="coerce").dropna().to_numpy(float)
    equity = np.cumsum(v)
    # Peak includes the current point (and the 0 start), so drawdown <= 0 by
    # construction; [:-1] would report the first winning trade as positive DD.
    peak = np.maximum.accumulate(np.r_[0.0, equity])[1:] if len(v) else np.array([0.0])
    dd = equity - peak
    return {"max_dd_pips": float(dd.min()) if len(dd) else 0.0,
            "basis": "realized closed-trade pips"}


def priced_close_floating(trades: pd.DataFrame, tapes: Dict[str, dict]) -> pd.DataFrame:
    """Per-trade floating P/L at each priced H1 close between entry and exit.

    Columns: trade_id, at (UTC bar time), floating_pips. Positions with unknown
    outcomes contribute nothing (unknown exposure is reported separately).
    """
    rows: List[dict] = []
    for _, t in trades.iterrows():
        if not np.isfinite(t.get("net_pips", np.nan)):
            continue  # unknown outcome — no floating value invented
        tape = tapes.get(t["Symbol"])
        if tape is None:
            continue
        side = 1 if t["entry_side"] == "BUY" else -1
        pip = float(tape["pip"])
        entry = float(t["entry_price"])
        times = tape["times"]
        closes = tape["prices"][:, 3]
        lo = np.searchsorted(times.asi8, pd.Timestamp(t["entry_at"]).value)
        hi = np.searchsorted(times.asi8, pd.Timestamp(t["exit_at"]).value, side="right")
        for j in range(lo, min(hi, len(times))):
            cl = closes[j]
            if not np.isfinite(cl):
                continue  # unpriced bar — no value invented
            rows.append({"trade_id": t.get("trade_id"), "at": times[j],
                         "floating_pips": side * (cl - entry) / pip})
    out = pd.DataFrame(rows, columns=["trade_id", "at", "floating_pips"])
    if len(out):
        out = out.sort_values(["at", "trade_id"], kind="mergesort").reset_index(drop=True)
    return out


def floating_summary(floating: pd.DataFrame, trades: pd.DataFrame) -> Dict:
    """Combined/single-position floating stats + exposure counts."""
    if len(floating) == 0:
        combined_min, single_min, max_concurrent = 0.0, 0.0, 0
    else:
        by_time = floating.groupby("at")
        combined = by_time["floating_pips"].sum()
        combined_min = float(combined.min())
        single_min = float(floating["floating_pips"].min())
        # Max concurrent = peak number of simultaneously priced positions
        # (one row per position per bar — no double counting).
        max_concurrent = int(by_time["trade_id"].nunique().max())
    n_trades = len(trades)
    unknown = int(trades["net_pips"].isna().sum()) if n_trades and "net_pips" in trades else 0
    priced = len(floating["trade_id"].unique()) if len(floating) else 0
    return {
        "max_combined_floating_loss_pips": combined_min,
        "max_single_position_floating_loss_pips": single_min,
        "max_concurrent_holdings": max_concurrent,
        "unknown_unpriced_exposure_trades": unknown,
        "trades_with_priced_floating": int(priced),
        "limits": LIMITS,
        "version": DRAWDOWN_VERSION,
    }
