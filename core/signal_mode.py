"""Live-signal router: Cycle 22 winner vs Cycle 18 vs FT-C01 baseline.

Cycle 22 installed a new broad champion (F1-P4: C18-A3's 26 equations with
tighter trailing exits + dynamic k) as the DEFAULT live-signal system, per
the user's explicit approval 2026-10-19 ("new broad champion").

F1-P4 unseen: 667 trades / +2,799.56 pips / RoMAD 7.72 / Sharpe 6.55 /
DD -362.51 -- beats C18-A3 on every metric and survives the chronological
10y (+$1,195.25 min equity vs C18-A3's -$996.81 ruin).

2026-10-19 update: Cycle 24 (R4A01, October-only: 24 eq, hours 15/17/18 UTC,
exactly 1 entry/check, 12/12 checks, unseen win 92.75%) is now the DEFAULT
live-signal system, per the user's explicit decision. Cycle 22 remains
selectable via set_active_system('cycle22').

2026-10-20 update: Cycle 26 (C26-33, November-only: 28 eq, hours 10/11/18 UTC,
exactly 1 entry/check, 9/12 checks best-nearly, unseen win 91.67%) added as
SYSTEM_CYCLE26. The UI selector defaults to cycle26 in November, else cycle24.

2026-10-20 update: Cycle 27 (C27-01, December-only: 30 eq, hours 10/11/13 UTC,
exactly 1 entry/check, 11/12 checks best-nearly, unseen win 92.42%) added as
SYSTEM_CYCLE27. The UI selector defaults to cycle27 in December, cycle26 in
November, else cycle24.

2026-10-20 update: Cycles 29-36 (February-September monthly systems: 24 eq
each, 15 mined + 9 TREND fallbacks, exactly 1 entry/check) added as
SYSTEM_CYCLE29..36. The UI selector now auto-defaults by month across the
full year: Jan->cycle28, Feb->cycle29, Mar->cycle30, Apr->cycle31,
May->cycle32, Jun->cycle33, Jul->cycle34, Aug->cycle35, Sep->cycle36,
Oct->cycle24, Nov->cycle26, Dec->cycle27. Each new engine passed a
bit-exact replay vs its research discovery log (0 mismatches).

2026-10-21 update: Cycle 48 (C48-02, December-only: 30 eq, hours 10/11/13
UTC, exactly 1 entry/check) added as SYSTEM_CYCLE48. C48-02 won the
Cycles 37-48 improvement program (20 end-to-end processes judged at the
2.5-pip primary cost): weak ratings 0 vs C27-01's 1, unseen net@2.5 +483.7,
win 95.45%, 11/12 checks -- it REPLACES cycle27 as December's default.
Cycle 27 remains selectable via set_active_system('cycle27'). The UI
selector now auto-defaults December to cycle48.

2026-10-21 update (user override promotions from the same program):
Cycle 42 (C42-18, June-only: 24 eq, hours 1/15/18 UTC, exactly 1
entry/check) added as SYSTEM_CYCLE42 -- a one-change surgery of C33-18
(EURUSD h1 TREND fallback replaced by an AUDUSD one); weak 1 vs 3 at
2.5-pip, unseen net@2.5 +477.7, win 95.24%; it had failed the program's
leftover gate (82.67% vs 87.25%) and the user waived that gate. It
REPLACES cycle33 as June's default; cycle33 remains selectable.
Cycle 44 (C44-15, August-only: 9 List D equations, USD majors, hours
1/13/16 UTC, up to 2 entries/check, no fallbacks) added as
SYSTEM_CYCLE44; weak 2 vs 8 at 2.5-pip, win 100%, leftover 100%; it had
failed the program's frequency gate (0.62 entries/day) and the user
waived that gate. It REPLACES cycle35 as August's default; cycle35
remains selectable. The UI selector now auto-defaults June to cycle42
and August to cycle44.

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
SYSTEM_CYCLE24 = "cycle24"   # R4A01: 24 eq (18 mined mom/atr + 6 TREND fallbacks),
                             # hours (15,17,18) UTC, exactly 1 entry/check
                             # (October-only research; 12/12 checks, user-promoted)
SYSTEM_CYCLE26 = "cycle26"   # C26-33: 28 eq (16 mined mom/atr + 12 TREND fallbacks),
                             # hours (10,11,18) UTC, exactly 1 entry/check
                             # (November-only research; 9/12 checks, best-nearly pick)
SYSTEM_CYCLE27 = "cycle27"   # C27-01: 30 eq (18 mined mom/atr + 12 TREND fallbacks),
                             # hours (10,11,13) UTC, exactly 1 entry/check
                             # (December-only research; 11/12 checks, best-nearly pick)
SYSTEM_CYCLE28 = "cycle28"   # C28-30: 24 eq (15 mined mom/atr + 9 TREND fallbacks,
                             # per-symbol tuned), hours (11,13,17) UTC,
                             # exactly 1 entry/check, MAJORS 10 symbols
                             # (January-only research; 10/12 checks, best-nearly pick)
SYSTEM_CYCLE29 = "cycle29"   # C29-31: 24 eq (15 mined mom/atr + 9 TREND fallbacks),
                             # hours (11,13,16) UTC, exactly 1 entry/check
                             # (February-only research; 8/12 checks, best-nearly pick)
SYSTEM_CYCLE30 = "cycle30"   # C30-31: 24 eq (15 mined mom/atr + 9 TREND fallbacks),
                             # hours (11,16,17) UTC, exactly 1 entry/check
                             # (March-only research; 9/12 checks, best-nearly pick)
SYSTEM_CYCLE31 = "cycle31"   # C31-29: 24 eq (15 mined mom/atr + 9 TREND fallbacks),
                             # hours (16,17,18) UTC, exactly 1 entry/check
                             # (April-only research; 10/12 checks, best-nearly pick)
SYSTEM_CYCLE32 = "cycle32"   # C32-20: 24 eq (15 mined mom/atr + 9 TREND fallbacks),
                             # hours (10,16,18) UTC, exactly 1 entry/check
                             # (May-only research; 11/12 checks, best-nearly pick)
SYSTEM_CYCLE33 = "cycle33"   # C33-18: 24 eq (15 mined mom/atr + 9 TREND fallbacks),
                             # hours (1,15,18) UTC, exactly 1 entry/check
                             # (June-only research; 10/12 checks, best-nearly pick)
SYSTEM_CYCLE34 = "cycle34"   # C34-17: 24 eq (15 mined mom/atr + 9 TREND fallbacks),
                             # hours (15,17,18) UTC, exactly 1 entry/check
                             # (July-only research; 10/12 checks, best-nearly pick)
SYSTEM_CYCLE35 = "cycle35"   # C35-31: 24 eq (15 mined mom/atr + 9 TREND fallbacks),
                             # hours (1,15,18) UTC, exactly 1 entry/check
                             # (August-only research; 10/12 checks, best-nearly pick)
SYSTEM_CYCLE36 = "cycle36"   # C36-40: 24 eq (15 mined mom/atr + 9 TREND fallbacks),
                             # hours (1,10,11) UTC, exactly 1 entry/check
                             # (September-only research; 10/12 checks, best-nearly pick)
SYSTEM_CYCLE48 = "cycle48"   # C48-02: 30 eq (18 mined mom/atr + 12 TREND fallbacks),
                             # hours (10,11,13) UTC, exactly 1 entry/check
                             # (December-only; improvement-program winner at 2.5-pip:
                             # weak 0, 11/12 checks; replaces C27-01 as December default)
SYSTEM_CYCLE42 = "cycle42"   # C42-18: 24 eq (15 mined mom/atr + 9 TREND fallbacks),
                             # hours (1,15,18) UTC, exactly 1 entry/check
                             # (June-only; C33-18 surgery, user-override promotion
                             # at 2.5-pip: weak 1, win 95.24%; replaces C33-18)
SYSTEM_CYCLE44 = "cycle44"   # C44-15: 9 eq (all book List D, USD majors, no fallbacks),
                             # hours (1,13,16) UTC, up to 2 entries/check
                             # (August-only; user-override promotion at 2.5-pip:
                             # weak 2, win 100%, 0.62 entries/day; replaces C35-31)

_ACTIVE = SYSTEM_CYCLE24     # default: Cycle 24 (R4A01), per user decision 2026-10-19


def set_active_system(name: str) -> str:
    """Switch live-signal system. name in {'cycle22', 'cycle18', 'ft-c01',
    'cycle24', 'cycle26', 'cycle27', 'cycle28', 'cycle29', 'cycle30',
    'cycle31', 'cycle32', 'cycle33', 'cycle34', 'cycle35', 'cycle36',
    'cycle48', 'cycle42', 'cycle44'}.
    Returns the newly active system name."""
    global _ACTIVE
    n = str(name).strip().lower()
    if n not in (SYSTEM_CYCLE22, SYSTEM_CYCLE18, SYSTEM_FTC01, SYSTEM_CYCLE24,
                 SYSTEM_CYCLE26, SYSTEM_CYCLE27, SYSTEM_CYCLE28, SYSTEM_CYCLE29,
                 SYSTEM_CYCLE30, SYSTEM_CYCLE31, SYSTEM_CYCLE32, SYSTEM_CYCLE33,
                 SYSTEM_CYCLE34, SYSTEM_CYCLE35, SYSTEM_CYCLE36, SYSTEM_CYCLE48,
                 SYSTEM_CYCLE42, SYSTEM_CYCLE44):
        raise ValueError(
            f"unknown system {name!r}; choose 'cycle22', 'cycle18', 'ft-c01', "
            f"'cycle24', 'cycle26', 'cycle27', 'cycle28', 'cycle29', 'cycle30', "
            f"'cycle31', 'cycle32', 'cycle33', 'cycle34', 'cycle35', 'cycle36', "
            f"'cycle48', 'cycle42' or 'cycle44'")
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
    if _ACTIVE == SYSTEM_CYCLE24:
        return ("cycle24 (R4A01): 24 equations (18 mined + 6 TREND fallbacks), "
                "entries 15:00/17:00/18:00 UTC "
                "(21:30/23:30/00:30 MMT), exactly 1 entry/check -- "
                "October unseen +326.5 pips / RoMAD 3.23 / win 92.75% (12/12 checks)")
    if _ACTIVE == SYSTEM_CYCLE26:
        return ("cycle26 (C26-33): 28 equations (16 mined + 12 TREND fallbacks), "
                "entries 10:00/11:00/18:00 UTC "
                "(16:30/17:30/00:30 MMT), exactly 1 entry/check -- "
                "November unseen +224.5 pips / RoMAD 1.04 / win 91.67% (9/12 checks, best-nearly)")
    if _ACTIVE == SYSTEM_CYCLE27:
        return ("cycle27 (C27-01): 30 equations (18 mined + 12 TREND fallbacks), "
                "entries 10:00/11:00/13:00 UTC "
                "(16:30/17:30/19:30 MMT), exactly 1 entry/check -- "
                "December unseen +442.6 pips / RoMAD 5.45 / win 92.42% (11/12 checks, best-nearly)")
    if _ACTIVE == SYSTEM_CYCLE48:
        return ("cycle48 (C48-02): 30 equations (18 mined + 12 TREND fallbacks), "
                "entries 10:00/11:00/13:00 UTC "
                "(16:30/17:30/19:30 MMT), exactly 1 entry/check -- "
                "December @2.5-pip net +483.7 pips / win 95.45% / weak 0 "
                "(11/12 checks; improvement-program winner, replaced C27-01)")
    if _ACTIVE == SYSTEM_CYCLE42:
        return ("cycle42 (C42-18): 24 equations (15 mined + 9 TREND fallbacks), "
                "entries 01:00/15:00/18:00 UTC "
                "(07:30/21:30/00:30 MMT), exactly 1 entry/check -- "
                "June @2.5-pip net +477.7 pips / win 95.24% / weak 1 "
                "(10/12 checks; user-override promotion, replaced C33-18)")
    if _ACTIVE == SYSTEM_CYCLE44:
        return ("cycle44 (C44-15): 9 equations (all book List D, USD majors, "
                "no fallbacks), entries 01:00/13:00/16:00 UTC "
                "(07:30/19:30/22:30 MMT), up to 2 entries/check -- "
                "August @2.5-pip net +155.0 pips / win 100% / weak 2 "
                "(9/12 checks; user-override promotion, replaced C35-31)")
    if _ACTIVE == SYSTEM_CYCLE28:
        return ("cycle28 (C28-30): 24 equations (15 mined + 9 TREND fallbacks, "
                "per-symbol tuned), entries 11:00/13:00/17:00 UTC "
                "(17:30/19:30/23:30 MMT), exactly 1 entry/check, MAJORS -- "
                "January unseen +300.4 pips / RoMAD 1.73 / win 90.91% (10/12 checks, best-nearly)")
    if _ACTIVE == SYSTEM_CYCLE29:
        return ("cycle29 (C29-31): 24 equations (15 mined + 9 TREND fallbacks), "
                "entries 11:00/13:00/16:00 UTC "
                "(17:30/19:30/22:30 MMT), exactly 1 entry/check -- "
                "February unseen +63.3 pips / RoMAD 0.50 / win 86.67% (8/12 checks, best-nearly)")
    if _ACTIVE == SYSTEM_CYCLE30:
        return ("cycle30 (C30-31): 24 equations (15 mined + 9 TREND fallbacks), "
                "entries 11:00/16:00/17:00 UTC "
                "(17:30/22:30/23:30 MMT), exactly 1 entry/check -- "
                "March unseen +235.3 pips / RoMAD 2.23 / win 92.06% (9/12 checks, best-nearly)")
    if _ACTIVE == SYSTEM_CYCLE31:
        return ("cycle31 (C31-29): 24 equations (15 mined + 9 TREND fallbacks), "
                "entries 16:00/17:00/18:00 UTC "
                "(22:30/23:30/00:30 MMT), exactly 1 entry/check -- "
                "April unseen +424.9 pips / RoMAD 4.21 / win 90.91% (10/12 checks, best-nearly)")
    if _ACTIVE == SYSTEM_CYCLE32:
        return ("cycle32 (C32-20): 24 equations (15 mined + 9 TREND fallbacks), "
                "entries 10:00/16:00/18:00 UTC "
                "(16:30/22:30/00:30 MMT), exactly 1 entry/check -- "
                "May unseen +566.2 pips / RoMAD 4.23 / win 93.94% (11/12 checks, best-nearly)")
    if _ACTIVE == SYSTEM_CYCLE33:
        return ("cycle33 (C33-18): 24 equations (15 mined + 9 TREND fallbacks), "
                "entries 01:00/15:00/18:00 UTC "
                "(07:30/21:30/00:30 MMT), exactly 1 entry/check -- "
                "June unseen +595.9 pips / RoMAD 22.15 / win 96.83% (10/12 checks, best-nearly)")
    if _ACTIVE == SYSTEM_CYCLE34:
        return ("cycle34 (C34-17): 24 equations (15 mined + 9 TREND fallbacks), "
                "entries 15:00/17:00/18:00 UTC "
                "(21:30/23:30/00:30 MMT), exactly 1 entry/check -- "
                "July unseen +486.8 pips / RoMAD 4.82 / win 95.65% (10/12 checks, best-nearly)")
    if _ACTIVE == SYSTEM_CYCLE35:
        return ("cycle35 (C35-31): 24 equations (15 mined + 9 TREND fallbacks), "
                "entries 01:00/15:00/18:00 UTC "
                "(07:30/21:30/00:30 MMT), exactly 1 entry/check -- "
                "August unseen +304.6 pips / RoMAD 4.58 / win 88.89% (10/12 checks, best-nearly)")
    if _ACTIVE == SYSTEM_CYCLE36:
        return ("cycle36 (C36-40): 24 equations (15 mined + 9 TREND fallbacks), "
                "entries 01:00/10:00/11:00 UTC "
                "(07:30/16:30/17:30 MMT), exactly 1 entry/check -- "
                "September unseen +199.2 pips / RoMAD 1.41 / win 90.91% (10/12 checks, best-nearly)")
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
    if _ACTIVE == SYSTEM_CYCLE24:
        from core.cycle24_best import evaluate_cycle24_signals
        return evaluate_cycle24_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE26:
        from core.cycle26_best import evaluate_cycle26_signals
        return evaluate_cycle26_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE27:
        from core.cycle27_best import evaluate_cycle27_signals
        return evaluate_cycle27_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE28:
        from core.cycle28_best import evaluate_cycle28_signals
        return evaluate_cycle28_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE29:
        from core.cycle29_best import evaluate_cycle29_signals
        return evaluate_cycle29_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE30:
        from core.cycle30_best import evaluate_cycle30_signals
        return evaluate_cycle30_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE31:
        from core.cycle31_best import evaluate_cycle31_signals
        return evaluate_cycle31_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE32:
        from core.cycle32_best import evaluate_cycle32_signals
        return evaluate_cycle32_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE33:
        from core.cycle33_best import evaluate_cycle33_signals
        return evaluate_cycle33_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE34:
        from core.cycle34_best import evaluate_cycle34_signals
        return evaluate_cycle34_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE35:
        from core.cycle35_best import evaluate_cycle35_signals
        return evaluate_cycle35_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE36:
        from core.cycle36_best import evaluate_cycle36_signals
        return evaluate_cycle36_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE48:
        from core.cycle48_best import evaluate_cycle48_signals
        return evaluate_cycle48_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE42:
        from core.cycle42_best import evaluate_cycle42_signals
        return evaluate_cycle42_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE44:
        from core.cycle44_best import evaluate_cycle44_signals
        return evaluate_cycle44_signals(frames, check_time_utc)
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
    if _ACTIVE == SYSTEM_CYCLE24:
        from core.cycle24_best import select_cycle24_entries
        return select_cycle24_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE26:
        from core.cycle26_best import select_cycle26_entries
        return select_cycle26_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE27:
        from core.cycle27_best import select_cycle27_entries
        return select_cycle27_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE28:
        from core.cycle28_best import select_cycle28_entries
        return select_cycle28_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE29:
        from core.cycle29_best import select_cycle29_entries
        return select_cycle29_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE30:
        from core.cycle30_best import select_cycle30_entries
        return select_cycle30_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE31:
        from core.cycle31_best import select_cycle31_entries
        return select_cycle31_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE32:
        from core.cycle32_best import select_cycle32_entries
        return select_cycle32_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE33:
        from core.cycle33_best import select_cycle33_entries
        return select_cycle33_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE34:
        from core.cycle34_best import select_cycle34_entries
        return select_cycle34_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE35:
        from core.cycle35_best import select_cycle35_entries
        return select_cycle35_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE36:
        from core.cycle36_best import select_cycle36_entries
        return select_cycle36_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE48:
        from core.cycle48_best import select_cycle48_entries
        return select_cycle48_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE42:
        from core.cycle42_best import select_cycle42_entries
        return select_cycle42_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE44:
        from core.cycle44_best import select_cycle44_entries
        return select_cycle44_entries(signals, open_symbols=open_symbols)
    from core.cycle12_best import select_cycle12_entries
    return select_cycle12_entries(signals, open_symbols=open_symbols, k=k)


def active_check_hours():
    """UTC hours of the ACTIVE live-signal system.

    Entries fire at H:00 UTC (the backtest fills at the open of the
    H:00 candle); the H:30 stamp is only the signal-evaluation label.
    """
    if _ACTIVE == SYSTEM_FTC01:
        return (18,)
    if _ACTIVE == SYSTEM_CYCLE24:
        return (15, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE26:
        return (10, 11, 18)
    if _ACTIVE == SYSTEM_CYCLE27:
        return (10, 11, 13)
    if _ACTIVE == SYSTEM_CYCLE28:
        return (11, 13, 17)
    if _ACTIVE == SYSTEM_CYCLE29:
        return (11, 13, 16)
    if _ACTIVE == SYSTEM_CYCLE30:
        return (11, 16, 17)
    if _ACTIVE == SYSTEM_CYCLE31:
        return (16, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE32:
        return (10, 16, 18)
    if _ACTIVE == SYSTEM_CYCLE33:
        return (1, 15, 18)
    if _ACTIVE == SYSTEM_CYCLE34:
        return (15, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE35:
        return (1, 15, 18)
    if _ACTIVE == SYSTEM_CYCLE36:
        return (1, 10, 11)
    if _ACTIVE == SYSTEM_CYCLE48:
        return (10, 11, 13)
    if _ACTIVE == SYSTEM_CYCLE42:
        return (1, 15, 18)
    if _ACTIVE == SYSTEM_CYCLE44:
        return (1, 13, 16)
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
