"""Honest performance metrics (2026-10-09).

Every metric records its basis alongside the number. Profit is summed PIPS,
never presented as cash or account return (different pairs have different pip
values and shared currency risk; no sizing/margin model is supplied).

Pip-Sharpe proxy
----------------
sqrt(252) x mean(daily realized pips) / sample-SD(daily realized pips),
including zero business days, with rolling weekend settlements attributed to
the next weekday (research convention, see research README.txt). It is NOT a
capital-return Sharpe: no risk-free subtraction, no correction for selection
or serial dependence. A high value is never treated as validation.

There is NO "Sharpe > 5 = overfit" rule. Deflated Sharpe is reported only when
trial information is supplied, otherwise "unavailable + reason".

Average-payoff Kelly is an approximate HISTORICAL statistic
(win_prob - loss_prob / avg_win_to_loss_ratio); it never auto-sizes live.
"""
from __future__ import annotations

import math
from typing import Dict

import numpy as np
import pandas as pd

METRICS_VERSION = "metrics-honest-20261009-v1"


def daily_realized_pips(trades: pd.DataFrame, *, date_col: str = "exit_at",
                        value_col: str = "net_pips",
                        weekend_rollover: bool = True) -> pd.Series:
    """Daily realized pip P/L. Zero business days are included. Weekend
    settlements roll to the next weekday (research convention)."""
    if len(trades) == 0:
        return pd.Series(dtype=float)
    t = trades.loc[trades[value_col].notna()].copy()
    if len(t) == 0:
        return pd.Series(dtype=float)
    days = pd.to_datetime(t[date_col], utc=True).dt.tz_convert("UTC").dt.normalize()
    if weekend_rollover:
        dow = days.dt.dayofweek
        days = days + pd.to_timedelta(((7 - dow) % 7 == 0).astype(int) * 0, unit="D")
        # Saturday -> +2d, Sunday -> +1d
        days = days.where(~dow.isin([5, 6]), days + pd.to_timedelta((7 - dow).where(dow.isin([5, 6]), 0), unit="D"))
    daily = t.groupby(days)[value_col].sum().sort_index()
    if len(daily) < 2:
        return daily
    full = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    full = full[full.dayofweek < 5]  # business days only; weekends rolled forward
    return daily.reindex(full, fill_value=0.0)


def pip_sharpe_proxy(trades: pd.DataFrame, *, annualization: float = 252.0) -> Dict:
    """Pip-Sharpe proxy with full basis recording. See module docstring."""
    daily = daily_realized_pips(trades)
    n = len(daily)
    mean = float(daily.mean()) if n else 0.0
    sd = float(daily.std(ddof=1)) if n > 1 else 0.0
    value = math.sqrt(annualization) * mean / sd if sd > 0 else None
    return {
        "value": value,
        "basis": {
            "frequency": "daily realized net pips",
            "annualization_factor": f"sqrt({annualization:g})",
            "zero_days": "zero business days included",
            "weekend": "weekend settlements rolled to next weekday",
            "realized_vs_mtm": "realized closed-trade pips only; unknown (censored) outcomes excluded",
            "not_a": "not a capital-return Sharpe; no risk-free subtraction; "
                     "no correction for selection or serial dependence",
        },
        "n_days": n,
        "version": METRICS_VERSION,
    }


def deflated_sharpe(sharpe_value: float | None, *, n_trials: int | None = None,
                    benchmark_sr: float = 0.0) -> Dict:
    """Deflated Sharpe — only computable with trial information."""
    if n_trials is None or n_trials <= 0:
        return {"value": None, "status": "unavailable",
                "reason": "trial count not supplied; deflated Sharpe requires the number of "
                          "trials/configurations tested to adjust for selection bias"}
    # Bailey & de Prado deflated Sharpe ratio (single-benchmark form).
    from math import erf, sqrt
    sr = float(sharpe_value or 0.0)
    var_sr = (1 - 0.0) / 252.0  # placeholder variance scaffold; see note
    _ = var_sr
    expected_max = benchmark_sr  # simplified; full form needs the trial SR distribution
    return {"value": None, "status": "unavailable",
            "reason": ("trial distribution of candidate Sharpe ratios not recorded; "
                       "deflated Sharpe needs the full set of tried configurations, "
                       f"only n_trials={n_trials} is known"),
            "n_trials": int(n_trials)}


def approx_kelly(trades: pd.DataFrame, *, value_col: str = "net_pips") -> Dict:
    """Approximate historical Kelly: p - q / (avg_win/avg_loss).

    Descriptive heuristic of the OBSERVED sample. NEVER auto-sizes live.
    """
    t = trades.loc[trades[value_col].notna(), value_col].to_numpy(float) if len(trades) else np.array([])
    wins = t[t > 0]
    losses = t[t < 0]
    n = len(t)
    if n == 0 or len(wins) == 0 or len(losses) == 0:
        return {"value": None, "label": "approximate historical statistic — do not auto-size live",
                "reason": "undefined without both wins and losses"}
    p = len(wins) / n
    q = 1 - p
    b = float(wins.mean()) / float(-losses.mean())
    kelly = p - q / b if b > 0 else None
    return {"value": kelly,
            "label": "approximate historical statistic — do not auto-size live",
            "basis": f"p={p:.4f}, avg_win/avg_loss={b:.4f}, n={n}"}


def summarize_trades(trades: pd.DataFrame, *, value_col: str = "net_pips") -> Dict:
    """Core trade statistics with honest labels. Unknown (NaN) outcomes are
    excluded from realized stats and reported separately."""
    valid = trades.loc[trades[value_col].notna()] if len(trades) else trades
    net = valid[value_col].to_numpy(float) if len(valid) else np.array([])
    unknown = int(trades[value_col].isna().sum()) if len(trades) else 0
    n = len(net)
    wins = net[net > 0]
    losses = net[net < 0]
    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(-losses.sum()) if len(losses) else 0.0
    equity = np.cumsum(net)
    # Peak includes the current point (and the 0 start), so drawdown <= 0 by
    # construction; [:-1] would report early winning trades as positive DD.
    dd = equity - np.maximum.accumulate(np.r_[0.0, equity])[1:] if n else np.array([])
    max_dd = float(dd.min()) if n else 0.0
    total = float(net.sum()) if n else 0.0
    return {
        "completed_trades": n,
        "unknown_outcomes": unknown,
        "net_pips": total,
        "realized_max_dd_pips": max_dd,
        "romad": (total / abs(max_dd)) if max_dd != 0 else "n.a.",
        "win_rate_pct": float((net > 0).mean() * 100) if n else None,
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else None,
        "ev_pips": float(total / n) if n else None,
        "max_completed_loss_pips": float(losses.min()) if len(losses) else None,
        "basis": "realized closed-trade pips; censored/unknown outcomes excluded and reported separately",
        "version": METRICS_VERSION,
    }
