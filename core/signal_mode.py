"""Live-signal router -- the 12 standing monthly systems ONLY.

2026-10-22 purge (user order): every older cycle system was removed
from this router, the UI selector and the panel renderers. The only
selectable systems are the 12 Program-4 standing winners, one per
month: Jan C60-03, Feb C85-23, Mar C86-24, Apr C87-24, May C88-03,
Jun C89-21, Jul C78-34, Aug C67-04, Sep C91-15, Oct C92-24,
Nov C93-24, Dec C94-23. Each winner module delegates internally to
its frozen incumbent engine (kept in core/ as internal code, NOT
selectable). The 20 trading symbols are unchanged.
"""
from __future__ import annotations

import pandas as pd

SYSTEM_CYCLE60 = "cycle60"   # C60-03 -- January system
SYSTEM_CYCLE85 = "cycle85"   # C85-23 -- February system
SYSTEM_CYCLE86 = "cycle86"   # C86-24 -- March system
SYSTEM_CYCLE87 = "cycle87"   # C87-24 -- April system
SYSTEM_CYCLE88 = "cycle88"   # C88-03 -- May system
SYSTEM_CYCLE89 = "cycle89"   # C89-21 -- June system
SYSTEM_CYCLE78 = "cycle78"   # C78-34 -- July system
SYSTEM_CYCLE67 = "cycle67"   # C67-04 -- August system
SYSTEM_CYCLE91 = "cycle91"   # C91-15 -- September system
SYSTEM_CYCLE92 = "cycle92"   # C92-24 -- October system
SYSTEM_CYCLE93 = "cycle93"   # C93-24 -- November system
SYSTEM_CYCLE94 = "cycle94"   # C94-23 -- December system

MONTH_SYSTEMS = {
    1: SYSTEM_CYCLE60,   # January
    2: SYSTEM_CYCLE85,   # February
    3: SYSTEM_CYCLE86,   # March
    4: SYSTEM_CYCLE87,   # April
    5: SYSTEM_CYCLE88,   # May
    6: SYSTEM_CYCLE89,   # June
    7: SYSTEM_CYCLE78,   # July
    8: SYSTEM_CYCLE67,   # August
    9: SYSTEM_CYCLE91,   # September
    10: SYSTEM_CYCLE92,   # October
    11: SYSTEM_CYCLE93,   # November
    12: SYSTEM_CYCLE94,   # December
}

SYSTEM_BEST_N = {
    SYSTEM_CYCLE60: 83,   # C60-03 -- January
    SYSTEM_CYCLE85: 104,   # C85-23 -- February
    SYSTEM_CYCLE86: 86,   # C86-24 -- March
    SYSTEM_CYCLE87: 104,   # C87-24 -- April
    SYSTEM_CYCLE88: 66,   # C88-03 -- May
    SYSTEM_CYCLE89: 84,   # C89-21 -- June
    SYSTEM_CYCLE78: 103,   # C78-34 -- July
    SYSTEM_CYCLE67: 121,   # C67-04 -- August
    SYSTEM_CYCLE91: 83,   # C91-15 -- September
    SYSTEM_CYCLE92: 83,   # C92-24 -- October
    SYSTEM_CYCLE93: 83,   # C93-24 -- November
    SYSTEM_CYCLE94: 105,   # C94-23 -- December
}


def best_n_for_system(name=None):
    """Verified Best N for `name` (default: the active system) or None."""
    n = _ACTIVE if name is None else str(name).strip().lower()
    return SYSTEM_BEST_N.get(n)


import datetime as _datetime

_ACTIVE = MONTH_SYSTEMS[_datetime.datetime.now(_datetime.timezone.utc).month]


def set_active_system(name: str) -> str:
    """Switch live-signal system (only the 12 standing monthly systems)."""
    global _ACTIVE
    n = str(name).strip().lower()
    if n not in (SYSTEM_CYCLE60, SYSTEM_CYCLE85, SYSTEM_CYCLE86, SYSTEM_CYCLE87, SYSTEM_CYCLE88, SYSTEM_CYCLE89, SYSTEM_CYCLE78, SYSTEM_CYCLE67, SYSTEM_CYCLE91, SYSTEM_CYCLE92, SYSTEM_CYCLE93, SYSTEM_CYCLE94,):
        raise ValueError(f"unknown system {name!r}; only the 12 standing "
                         f"monthly systems remain: {sorted(MONTH_SYSTEMS.values())}")
    _ACTIVE = n
    return _ACTIVE


def active_system() -> str:
    return _ACTIVE


def describe_active() -> str:
    """Human description of the ACTIVE system (branches carried over verbatim
    from the pre-purge router)."""
    if _ACTIVE == SYSTEM_CYCLE60:
        return ("cycle60 (C60-03): 32 equations (incumbent 24 walked plain "
                "+ 8 fresh GMMA/TSF/Tillson-T3 legs), entries 11:00/13:00/"
                "17:00 UTC (18:00/20:00/00:00 MMT), exactly 1 entry/check "
                "-- January @2.5-pip net +335.4 pips / leftover 62.3% / "
                "weak 1 (11/12 checks; paired LCT P 98.15%, Muse's-"
                "decision promotion, replaced C52-04)")
    if _ACTIVE == SYSTEM_CYCLE85:
        return ("cycle85 (C85-23): C56-15 entry engine frozen (hours "
                "11/13/16 delegate to cycle56) minus 4 FB legs "
                "(FB_GBPUSD_h16_2, FB_USDCAD_h13_1, FB_EURGBP_h13_2, "
                "FB_NZDUSD_h11_2) + TP x1.75 on surviving FB trades, "
                "exactly 1 entry/check -- February @2.5-pip net +184.2 "
                "pips / win 85.71% / leftover 29.35% / 2.45 entries/day "
                "(LCT middle PASS P 90.42% / p5 40.14%, Program 4 "
                "promotion, replaced C56-15)")
    if _ACTIVE == SYSTEM_CYCLE86:
        return ("cycle86 (C86-24): C62-10 entry engine frozen (hours "
                "11/16/17 delegate to cycle62) minus FB_USDCAD_h16_1 "
                "+ M08 Reject15 rerank within top-3 + TP x0.95 on FB "
                "trades (exits simulated on M15 in research), exactly "
                "1 entry/check -- March @2.5-pip net +350.3 pips / win "
                "93.55% / leftover 69.30% / 2.95 entries/day (LCT "
                "middle PASS P 87.34% / p5 35.38%, Program 4 "
                "promotion, replaced C62-10)")
    if _ACTIVE == SYSTEM_CYCLE87:
        return ("cycle87 (C87-24): C63-04 entry engine frozen (hours "
                "16/17/18 delegate to cycle63) with FB_EURGBP_h18_1, "
                "FB_GBPUSD_h16_1 and FB_USDCHF_h18_2 banned + M18 "
                "common-range rerank within top-3, exactly 1 "
                "entry/check -- April @2.5-pip net +633.2 pips / win "
                "92.42% / leftover 60.26% / 3.00 entries/day (LCT "
                "middle PASS P 92.44% / p5 65.55%, Program 4 "
                "promotion, replaced C63-04)")
    if _ACTIVE == SYSTEM_CYCLE88:
        return ("cycle88 (C88-03): C64-09 entry engine frozen (hours "
                "10/16/18 delegate to cycle64) minus the entire FB "
                "layer (all 9 FB legs), exactly 1 entry/check -- May "
                "@2.5-pip net +377.0 pips / win 91.84% / leftover "
                "58.69% / 2.23 entries/day (LCT middle+strict PASS "
                "P 100.00% / p5 84.43%, Program 4 promotion, "
                "replaced C64-09)")
    if _ACTIVE == SYSTEM_CYCLE89:
        return ("cycle89 (C89-21): C65-01 entry engine frozen (hours "
                "1/15/18 delegate to cycle65) minus FB_AUDJPY_h18_0 "
                "+ FBGATE veto on h18 bench picks (ATR-pct > 80 & "
                "M15 CLV < 0.50) + TP x1.25 on the REV_lr2 legs, "
                "exactly 1 entry/check -- June @2.5-pip net +364.0 "
                "pips / win 95.24% / leftover 58.20% / 3.00 "
                "entries/day (LCT middle+strict PASS P 99.91% / p5 "
                "52.13%, Program 4 promotion, replaced C65-01)")
    if _ACTIVE == SYSTEM_CYCLE78:
        return ("cycle78 (C78-34): C66-08 entry engine frozen (hours "
                "15/17/18 delegate to cycle66) + X30 at-entry stop "
                "tightening (ER15(16) <= 0.20 & r1(1) >= 0 -> SL x0.90), "
                "exactly 1 entry/check -- July @2.5-pip net +487.7 pips / "
                "win 95.59% / leftover 62.48% / weak 1 (15/16 Program-3 "
                "checks, fails only check 8 which C66-08 itself fails; "
                "LCT middle PASS, Muse's-decision promotion, replaced "
                "C66-08)")
    if _ACTIVE == SYSTEM_CYCLE67:
        return ("cycle67 (C67-04): C55-15 core frozen (hours 6/16/17 "
                "delegate to cycle55) + 8 fresh supplement legs at new "
                "hours 01:00/18:00 UTC (08:00/01:00 MMT), up to 2 "
                "entries/check -- August @2.5-pip net +331.1 pips / win "
                "96.15% / leftover 76.1% / weak 0 (11/12 checks; paired "
                "LCT P structurally capped, Muse's-decision promotion, "
                "replaced C55-15)")
    if _ACTIVE == SYSTEM_CYCLE91:
        return ("cycle91 (C91-15): C59-18 entry engine frozen (hours "
                "1/10/11 delegate to cycle59) minus 3 hour-1 FB legs "
                "+ X30B at-entry overlay (ER15(16) <= 0.25 & r1(1) "
                ">= 0 -> SL x0.85), exactly 1 entry/check -- "
                "September @2.5-pip net +285.1 pips / win 94.83% / "
                "leftover 65.26% / 2.64 entries/day (LCT middle PASS "
                "P 80.28% / p5 24.63%, Program 4 promotion, "
                "replaced C59-18)")
    if _ACTIVE == SYSTEM_CYCLE92:
        return ("cycle92 (C92-24): C69-07 entry engine frozen (hours "
                "15/17/18 delegate to cycle69) minus 4 FB legs + 7 "
                "screened fresh legs at fallback-tier scores "
                "512-506, 1 primary entry/check + Cycle 155 "
                "dual-pick second entry (non-FB, fewer than 3 "
                "open) -- October @2.5-pip net +296.7 pips / "
                "win 93.75% / leftover 62.78% / 2.09 entries/day "
                "(LCT middle+strict PASS P 100.00% / p5 70.20%, "
                "Program 4 promotion, replaced C69-07 as the app "
                "default only -- live R4A01 crons unchanged; "
                "dual-pick validated 2026-10-23 at the middle "
                "standard: EC22 17/18, LCT P 89.23%, audit "
                "leftover 67.84% / 2.48 entries/day)")
    if _ACTIVE == SYSTEM_CYCLE93:
        return ("cycle93 (C93-24): C70-07 entry engine frozen (hours "
                "9/13/15 delegate to cycle70) minus 8 of 9 FB legs "
                "and the CYB EURNZD h9 leg + FBGATE veto on the "
                "surviving FB_EURUSD_h9_0 (ATR-pct > 80 & M15 CLV "
                "< 0.50), exactly 1 entry/check -- November "
                "@2.5-pip net +318.2 pips / win 84.62% / leftover "
                "40.11% / 2.60 entries/day (LCT middle PASS P 83.42% "
                "/ p5 46.18%, Program 4 promotion, replaced C70-07)")
    if _ACTIVE == SYSTEM_CYCLE94:
        return ("cycle94 (C94-23): C71-04 entry engine frozen "
                "verbatim (hours 10/11/13 delegate to cycle71) + "
                "FB-pick gate (ATR14 percentile > 70 & M15 CLV "
                "< 0.45 -> veto, walk continues), exactly 1 "
                "entry/check -- December @2.5-pip net +490.6 pips / "
                "win 95.45% / leftover 80.81% / 2.87 entries/day "
                "(LCT middle PASS P 94.14% / p5 31.54%, Program 4 "
                "promotion, replaced C71-04)")
    return "Cycle 60 (C60-03) -- January system"


def evaluate_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate the ACTIVE system's equations at one check time."""
    if _ACTIVE == SYSTEM_CYCLE60:
        from core.cycle60_best import evaluate_cycle60_signals
        return evaluate_cycle60_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE85:
        from core.cycle85_best import evaluate_cycle85_signals
        return evaluate_cycle85_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE86:
        from core.cycle86_best import (evaluate_cycle86_signals,
                                       fetch_cycle86_m15_frames)
        return evaluate_cycle86_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle86_m15_frames())
    if _ACTIVE == SYSTEM_CYCLE87:
        from core.cycle87_best import (evaluate_cycle87_signals,
                                       fetch_cycle87_m15_frames)
        return evaluate_cycle87_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle87_m15_frames())
    if _ACTIVE == SYSTEM_CYCLE88:
        from core.cycle88_best import evaluate_cycle88_signals
        return evaluate_cycle88_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE89:
        from core.cycle89_best import (evaluate_cycle89_signals,
                                       fetch_cycle89_m15_frames)
        return evaluate_cycle89_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle89_m15_frames())
    if _ACTIVE == SYSTEM_CYCLE78:
        from core.cycle78_best import (evaluate_cycle78_signals,
                                       fetch_cycle78_m15_frames)
        return evaluate_cycle78_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle78_m15_frames())
    if _ACTIVE == SYSTEM_CYCLE67:
        from core.cycle67_best import evaluate_cycle67_signals
        return evaluate_cycle67_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE91:
        from core.cycle91_best import (evaluate_cycle91_signals,
                                       fetch_cycle91_m15_frames)
        return evaluate_cycle91_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle91_m15_frames())
    if _ACTIVE == SYSTEM_CYCLE92:
        from core.cycle92_best import evaluate_cycle92_signals
        return evaluate_cycle92_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE93:
        from core.cycle93_best import (evaluate_cycle93_signals,
                                       fetch_cycle93_m15_frames)
        return evaluate_cycle93_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle93_m15_frames())
    if _ACTIVE == SYSTEM_CYCLE94:
        from core.cycle94_best import (evaluate_cycle94_signals,
                                       fetch_cycle94_m15_frames)
        return evaluate_cycle94_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle94_m15_frames())
    raise ValueError(f"no evaluator for active system {_ACTIVE!r}")


def select_entries(signals: pd.DataFrame, open_symbols=(), k=2) -> pd.DataFrame:
    """Top-k by score, max 1 open trade per symbol (all systems)."""
    if _ACTIVE == SYSTEM_CYCLE60:
        from core.cycle60_best import select_cycle60_entries
        return select_cycle60_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE85:
        from core.cycle85_best import select_cycle85_entries
        return select_cycle85_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE86:
        from core.cycle86_best import select_cycle86_entries
        return select_cycle86_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE87:
        from core.cycle87_best import select_cycle87_entries
        return select_cycle87_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE88:
        from core.cycle88_best import select_cycle88_entries
        return select_cycle88_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE89:
        from core.cycle89_best import select_cycle89_entries
        return select_cycle89_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE78:
        from core.cycle78_best import select_cycle78_entries
        return select_cycle78_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE67:
        from core.cycle67_best import select_cycle67_entries
        return select_cycle67_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE91:
        from core.cycle91_best import select_cycle91_entries
        return select_cycle91_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE92:
        from core.cycle92_best import select_cycle92_entries
        return select_cycle92_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE93:
        from core.cycle93_best import select_cycle93_entries
        return select_cycle93_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE94:
        from core.cycle94_best import select_cycle94_entries
        return select_cycle94_entries(signals, open_symbols=open_symbols)
    raise ValueError(f"no selector for active system {_ACTIVE!r}")


def active_check_hours():
    """UTC hours of the ACTIVE live-signal system.

    Entries fire at H:00 UTC (the backtest fills at the open of the
    H:00 candle); the H:30 stamp is only the signal-evaluation label."""
    if _ACTIVE == SYSTEM_CYCLE60:
        return (11, 13, 17)
    if _ACTIVE == SYSTEM_CYCLE85:
        return (11, 13, 16)
    if _ACTIVE == SYSTEM_CYCLE86:
        return (11, 16, 17)
    if _ACTIVE == SYSTEM_CYCLE87:
        return (16, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE88:
        return (10, 16, 18)
    if _ACTIVE == SYSTEM_CYCLE89:
        return (1, 15, 18)
    if _ACTIVE == SYSTEM_CYCLE78:
        return (15, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE67:
        return (1, 6, 16, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE91:
        return (1, 10, 11)
    if _ACTIVE == SYSTEM_CYCLE92:
        return (15, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE93:
        return (9, 13, 15)
    if _ACTIVE == SYSTEM_CYCLE94:
        return (10, 11, 13)
    return (11, 13, 17)


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
