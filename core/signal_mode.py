"""Live-signal router: Cycle 22 winner vs Cycle 18 vs FT-C01 baseline.

Cycle 22 installed a new broad champion (F1-P4: C18-A3's 26 equations with
tighter trailing exits + dynamic k) as the DEFAULT live-signal system, per
the user's explicit approval 2026-10-19 ("new broad champion").

F1-P4 unseen: 667 trades / +2,799.56 pips / RoMAD 7.72 / Sharpe 6.55 /
DD -362.51 -- beats C18-A3 on every metric and survives the chronological
10y (+$1,195.25 min equity vs C18-A3's -$996.81 ruin).

C18-A3 (core/cycle18_best.py) and FT-C01 (core/cycle12_best.py) are KEPT
byte-identical and remain available as selectable modes via
set_active_system('cycle18' / 'ft-c01').

Usage:
    from core.signal_mode import evaluate_signals, select_entries, active_system
    signals = evaluate_signals(frames, check_time_utc)   # routes by mode
"""
from __future__ import annotations

import pandas as pd

SYSTEM_CYCLE22 = "cycle22"    # F1-P4: 26 eq, hours (10,11,13,18) UTC, 20 symbols,
                             # trailing 1.0/0.3 ATR + dynamic k (Rule A)
SYSTEM_CYCLE18 = "cycle18"   # C18-A3: 26 eq, hours (10,11,13,18) UTC, 20 symbols
SYSTEM_FTC01 = "ft-c01"      # FT-C01 baseline: 4 SELL eq, hour 18 UTC only

_ACTIVE = SYSTEM_CYCLE22     # default: the Cycle 22 winner (F1-P4)


def set_active_system(name: str) -> str:
    """Switch live-signal system. name in {'cycle22', 'cycle18', 'ft-c01'}.
    Returns the newly active system name."""
    global _ACTIVE
    n = str(name).strip().lower()
    if n not in (SYSTEM_CYCLE22, SYSTEM_CYCLE18, SYSTEM_FTC01):
        raise ValueError(
            f"unknown system {name!r}; choose 'cycle22', 'cycle18' or 'ft-c01'")
    _ACTIVE = n
    return _ACTIVE


def active_system() -> str:
    return _ACTIVE


def describe_active() -> str:
    if _ACTIVE == SYSTEM_CYCLE22:
        return ("cycle22 (F1-P4): 26 equations, entries 10:00/11:00/13:00/18:00 UTC "
                "(16:30/17:30/19:30/00:30 MMT), 20 symbols, BUY+SELL, "
                "trailing 1.0/0.3 ATR + dynamic k -- unseen +2799.6 pips / RoMAD 7.72")
    if _ACTIVE == SYSTEM_CYCLE18:
        return ("cycle18 (C18-A3): 26 equations, entries 10:00/11:00/13:00/18:00 UTC "
                "(16:30/17:30/19:30/00:30 MMT), 20 symbols, BUY+SELL -- "
                "unseen +2198.8 pips / RoMAD 5.71")
    return ("ft-c01 (FT-C01 baseline): 4 SELL equations, entry 18:00 UTC "
            "(00:30 MMT) only, 4 symbols -- unseen +1283.1 pips / RoMAD 44.52")


def evaluate_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate the ACTIVE system's equations at one check time."""
    if _ACTIVE == SYSTEM_CYCLE22:
        from core.cycle22_best import evaluate_cycle22_signals
        return evaluate_cycle22_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE18:
        from core.cycle18_best import evaluate_cycle18_signals
        return evaluate_cycle18_signals(frames, check_time_utc)
    from core.cycle12_best import evaluate_cycle12_signals
    return evaluate_cycle12_signals(frames, check_time_utc)


def select_entries(signals: pd.DataFrame, open_symbols=(), k=2) -> pd.DataFrame:
    """Top-k by score, max 1 open trade per symbol (all systems).

    For cycle22 the researched system uses dynamic k (Rule A); pass k=None
    to let the cycle22 selector apply Rule A automatically."""
    if _ACTIVE == SYSTEM_CYCLE22:
        from core.cycle22_best import select_cycle22_entries
        return select_cycle22_entries(signals, open_symbols=open_symbols,
                                      k=None if k is None else k,
                                      dynamic=(k is None))
    if _ACTIVE == SYSTEM_CYCLE18:
        from core.cycle18_best import select_cycle18_entries
        return select_cycle18_entries(signals, open_symbols=open_symbols, k=k)
    from core.cycle12_best import select_cycle12_entries
    return select_cycle12_entries(signals, open_symbols=open_symbols, k=k)


def active_check_hours():
    """UTC hours of the ACTIVE live-signal system.

    Entries fire at H:00 UTC (the backtest fills at the open of the
    H:00 candle); the H:30 stamp is only the signal-evaluation label.
    """
    if _ACTIVE == SYSTEM_FTC01:
        return (18,)
    # cycle22 (F1-P4) and cycle18 (C18-A3) share the 4-check schedule
    return (10, 11, 13, 18)


ENTRY_WINDOW_MINUTES = 5


def is_active_check_time(ts) -> bool:
    """True during the ENTRY window H:00:00-H:04:59 UTC, weekdays.

    The backtest enters at the H:00 UTC candle open (entry_px = open of
    the check-30min candle), so the live entry window is H:00, not H:30.
    """
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    t = t.tz_localize(None)
    return (t.weekday() < 5 and t.hour in active_check_hours()
            and t.minute < ENTRY_WINDOW_MINUTES)


def next_entry_time(now_utc=None):
    """Next H:00 UTC entry window at/after now (weekdays).

    Returns a naive UTC Timestamp, or None if none found in 8 days.
    """
    now = pd.Timestamp.now(tz="UTC") if now_utc is None else pd.Timestamp(now_utc)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")
    now = now.tz_localize(None).replace(second=0, microsecond=0)
    hours = active_check_hours()
    for day_off in range(0, 8):
        day = (now + pd.Timedelta(days=day_off)).normalize()
        if day.weekday() >= 5:
            continue
        for h in sorted(hours):
            ts = day + pd.Timedelta(hours=h)
            if ts >= now:
                return ts
    return None


def entry_windows_mmt():
    """Human MMT labels for the entry windows, e.g. '16:30-16:34'."""
    out = []
    for h in sorted(active_check_hours()):
        mmt_h = h + 6
        mmt_m = 30
        if mmt_m >= 60:
            mmt_m -= 60
            mmt_h += 1
        mmt_h %= 24
        out.append(f"{mmt_h:02d}:{mmt_m:02d}-{mmt_h:02d}:{mmt_m + ENTRY_WINDOW_MINUTES - 1:02d}")
    return out
