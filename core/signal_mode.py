"""Live-signal router -- the 12 standing monthly systems ONLY.

2026-10-22 purge (user order): every older cycle system was removed
from this router, the UI selector and the panel renderers. The only
selectable systems are the 12 Program-4 standing winners, one per
month: Jan C60-03, Feb C85-23, Mar C86-24, Apr C87-24, May C88-03,
Jun C89-21, Jul C78-34, Aug C67-04, Sep C91-15, Oct C92-24,
Nov C93-24, Dec C94-23. Each winner module delegates internally to
its frozen incumbent engine (kept in core/ as internal code, NOT
selectable). The 20 trading symbols are unchanged.

2026-10-25 addition (user waiver order): two SECOND-BEST systems
are selectable alongside the standing winners -- Sep cycle287
(BRIEF18 C287 stack) and Dec cycle274 (BRIEF18 C274 stack). Each
is its month's recorded second-best challenger, integrated under
the user's explicit waiver of the chain-floor and DSR terms (the
only battery terms they failed). They are NEVER month defaults:
MONTH_SYSTEMS and the panels' month default are unchanged, and
the live signal crons do not use them. (February's H485_veto was
in the same waiver order but is NOT integrated: its recorded
ledger is a subset of the control walk and cannot be reproduced
by a stateless app panel -- see
FIX_NOTES_20261025_WAIVER_INTEGRATION.md.)

2026-10-26 changes (user order; see FIX_NOTES_20261026_COMBINED_
NDIV3.md): (1) SYSTEM_BEST_N now holds each month's Best N
DIVIDED BY 3 (the values from the user's verified 2026-10-25
div3 prediction simulation); the original full values are kept
in SYSTEM_BEST_N_FULL. (2) A combined best + second-best API,
evaluate_combined_entries(): at any check time the month's BEST
cycle has priority, and the month's SECOND-BEST cycle is
evaluated and shown ONLY when the best cycle produces NO entry
at that check time. MONTH_SYSTEMS defaults and every incumbent
evaluator/selector are unchanged; October's internal C155
dual-pick is untouched.
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

# Second-best systems (2026-10-25, integrated under the user's
# chain+DSR waiver; selectable alternatives, never month defaults).
SYSTEM_CYCLE287 = "cycle287"   # C287 stack -- September SECOND-BEST system
SYSTEM_CYCLE274 = "cycle274"   # C274 stack -- December SECOND-BEST system
SYSTEM_CYCLE93B = "cycle93b"   # BRIEF21 C20a -- November IMPROVED system
SYSTEM_CYCLE94B = "cycle94b"   # BRIEF21 C20a -- December IMPROVED system
SYSTEM_CYCLE60B = "cycle60b"   # BRIEF23 C20_STACK -- January IMPROVED system
SYSTEM_CYCLE87B = "cycle87b"   # BRIEF21 C20a -- April IMPROVED system

MONTH_SYSTEMS = {
    1: SYSTEM_CYCLE60B,   # January -- BRIEF23 C20_STACK IMPROVED (2026-10-26)
    2: SYSTEM_CYCLE85,   # February
    3: SYSTEM_CYCLE86,   # March
    4: SYSTEM_CYCLE87B,   # April -- BRIEF21 C20a IMPROVED (2026-10-26)
    5: SYSTEM_CYCLE88,   # May
    6: SYSTEM_CYCLE89,   # June
    7: SYSTEM_CYCLE78,   # July
    8: SYSTEM_CYCLE67,   # August
    9: SYSTEM_CYCLE91,   # September
    10: SYSTEM_CYCLE92,   # October
    11: SYSTEM_CYCLE93B,   # November -- BRIEF21 C20a IMPROVED (2026-10-26)
    12: SYSTEM_CYCLE94B,   # December -- BRIEF21 C20a IMPROVED (2026-10-26)
}

# Original verified Best N per system (full values, pre-division).
SYSTEM_BEST_N_FULL = {
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
    SYSTEM_CYCLE287: 83,   # C287 stack -- September second best (as C91-15)
    SYSTEM_CYCLE274: 105,   # C274 stack -- December second best (as C94-23)
    SYSTEM_CYCLE93B: 83,   # BRIEF21 C20a November improved (as C93-24)
    SYSTEM_CYCLE94B: 105,   # BRIEF21 C20a December improved (as C94-23)
    SYSTEM_CYCLE60B: 83,   # BRIEF23 C20_STACK January improved (as C60-03; no winner-specific Best N recorded)
    SYSTEM_CYCLE87B: 104,   # BRIEF21 C20a April improved (as C87-24)
}

# ACTIVE Best N values (user order 2026-10-26): every month's Best N
# DIVIDED BY 3 -- the exact values of the verified 2026-10-25 div3
# prediction simulation. Position sizing uses these; the full values
# above are kept for reference only.
SYSTEM_BEST_N = {
    SYSTEM_CYCLE60: 27.666666666666668,   # C60-03 -- January (83 / 3)
    SYSTEM_CYCLE85: 34.666666666666664,   # C85-23 -- February (104 / 3)
    SYSTEM_CYCLE86: 28.666666666666668,   # C86-24 -- March (86 / 3)
    SYSTEM_CYCLE87: 34.666666666666664,   # C87-24 -- April (104 / 3)
    SYSTEM_CYCLE88: 22.0,   # C88-03 -- May (66 / 3)
    SYSTEM_CYCLE89: 28.0,   # C89-21 -- June (84 / 3)
    SYSTEM_CYCLE78: 34.333333333333336,   # C78-34 -- July (103 / 3)
    SYSTEM_CYCLE67: 40.333333333333336,   # C67-04 -- August (121 / 3)
    SYSTEM_CYCLE91: 27.666666666666668,   # C91-15 -- September (83 / 3)
    SYSTEM_CYCLE92: 27.666666666666668,   # C92-24 -- October (83 / 3)
    SYSTEM_CYCLE93: 27.666666666666668,   # C93-24 -- November (83 / 3)
    SYSTEM_CYCLE94: 35.0,   # C94-23 -- December (105 / 3)
    SYSTEM_CYCLE287: 27.666666666666668,   # C287 stack -- September second best (as C91-15)
    SYSTEM_CYCLE274: 35.0,   # C274 stack -- December second best (as C94-23)
    SYSTEM_CYCLE93B: 27.666666666666668,   # BRIEF21 C20a November improved (83 / 3)
    SYSTEM_CYCLE94B: 35.0,   # BRIEF21 C20a December improved (105 / 3)
    SYSTEM_CYCLE60B: 27.666666666666668,   # BRIEF23 C20_STACK January improved (83 / 3)
    SYSTEM_CYCLE87B: 34.666666666666664,   # BRIEF21 C20a April improved (104 / 3)
}

# Months that carry a second-priority system in the combined
# layer. September: cycle287 (2026-10-25 waiver). November
# (user order 2026-10-26): the OLD incumbent system cycle93 is
# second priority behind the promoted BRIEF21 C20a improved
# system. December (user order 2026-10-27, 12-system rebuild):
# cycle274 is December's combined fallback behind cycle94b
# (replacing cycle94). January (user order 2026-10-26): the OLD
# C60-03 (cycle60) is second priority behind the promoted
# BRIEF23 C20_STACK improved system (cycle60b).
MONTH_SECOND_BEST = {
    1: SYSTEM_CYCLE60,   # January -- old C60-03 behind C20_STACK
    4: SYSTEM_CYCLE87,   # April -- old C87-24 behind C20a
    9: SYSTEM_CYCLE287,   # September
    11: SYSTEM_CYCLE93,   # November -- old C93-24 behind C20a
    12: SYSTEM_CYCLE274,   # December -- C274 stack behind C20a
    # (12-system rebuild 2026-10-27: user confirmed cycle274 is
    # December's kept second best, replacing cycle94 as fallback)
}


def best_n_for_system(name=None):
    """Active Best N for `name` (default: the active system) or None.

    Since 2026-10-26 this is the Best N DIVIDED BY 3 value from
    SYSTEM_BEST_N (user order). Use best_n_full_for_system() for the
    original undivided value."""
    n = _ACTIVE if name is None else str(name).strip().lower()
    return SYSTEM_BEST_N.get(n)


def best_n_full_for_system(name=None):
    """Original (undivided) Best N for `name`, or None."""
    n = _ACTIVE if name is None else str(name).strip().lower()
    return SYSTEM_BEST_N_FULL.get(n)


import datetime as _datetime

_ACTIVE = MONTH_SYSTEMS[_datetime.datetime.now(_datetime.timezone.utc).month]


def set_active_system(name: str) -> str:
    """Switch live-signal system (the 12 standing monthly systems, or
    one of the two recorded second-best systems added 2026-10-25)."""
    global _ACTIVE
    n = str(name).strip().lower()
    if n not in (SYSTEM_CYCLE60, SYSTEM_CYCLE85, SYSTEM_CYCLE86, SYSTEM_CYCLE87, SYSTEM_CYCLE88, SYSTEM_CYCLE89, SYSTEM_CYCLE78, SYSTEM_CYCLE67, SYSTEM_CYCLE91, SYSTEM_CYCLE92, SYSTEM_CYCLE93, SYSTEM_CYCLE94, SYSTEM_CYCLE287, SYSTEM_CYCLE274, SYSTEM_CYCLE93B, SYSTEM_CYCLE94B, SYSTEM_CYCLE60B, SYSTEM_CYCLE87B,):
        raise ValueError(f"unknown system {name!r}; only the 12 standing "
                         f"monthly systems, the recorded second-best "
                         f"systems and the BRIEF21 C20a improved systems "
                         f"remain: {sorted(MONTH_SYSTEMS.values())} + "
                         f"{sorted(MONTH_SECOND_BEST.values())}")
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
    if _ACTIVE == SYSTEM_CYCLE287:
        return ("cycle287 (C287 stack) -- September SECOND-BEST "
                "system: the C91-15 walk verbatim, kept only where "
                "the BRIEF18 depth-3 confirmation stack passes "
                "(M15 hammer aligned BUY & M15 pin-bar aligned BUY "
                "& RSI-reversal) -- @2.5-pip discovery n12 / leftover "
                "100.00%; audit 2024+2025 n2 / leftover 100.00% "
                "(incumbent n111 / 58.94%); integrated 2026-10-25 "
                "under the user's waiver of the chain-floor and DSR "
                "terms on very thin samples; NOT the September "
                "default (C91-15 stands)")
    if _ACTIVE == SYSTEM_CYCLE274:
        return ("cycle274 (C274 stack) -- December SECOND-BEST "
                "system: the C94-23 walk verbatim (FB gate "
                "included), kept only where the BRIEF18 depth-10 "
                "confirmation stack passes -- @2.5-pip discovery "
                "n31 / leftover 100.00%; audit 2024+2025 n5 / "
                "leftover 100.00% (incumbent n129 / 70.68%); "
                "integrated 2026-10-25 under the user's waiver of "
                "the chain-floor and DSR terms; NOT the December "
                "default (C94-23 stands)")
    if _ACTIVE == SYSTEM_CYCLE93B:
        return ("cycle93b (BRIEF21 C20a IMPROVED) -- November "
                "BEST system since 2026-10-26: C93-24 + C06 "
                "volatility-shock veto (vol_z > 1.498145894075274) "
                "+ C16 TP-continuation re-entry partner driven by "
                "the stateful walk ledger -- @2.5-pip discovery "
                "n436 / net +5128.59 / leftover 69.12%; audit "
                "n100 / net +678.37 / leftover 46.39% (BRIEF21 "
                "validated HUGE; app replay EXACT 2026-10-26). "
                "The old C93-24 (cycle93) is November's second "
                "priority in the combined layer")
    if _ACTIVE == SYSTEM_CYCLE94B:
        return ("cycle94b (BRIEF21 C20a IMPROVED) -- December "
                "BEST system since 2026-10-26: C94-23 + C06 "
                "volatility-shock veto (vol_z > 1.123626798751949) "
                "+ C16 TP-continuation re-entry partner driven by "
                "the stateful walk ledger -- @2.5-pip discovery "
                "n650 / net +4479.75 / leftover 66.20%; audit "
                "n157 / net +1135.57 / leftover 75.39% (BRIEF21 "
                "validated HUGE; app replay EXACT 2026-10-26). "
                "December's second priority in the combined "
                "layer is the C274 stack (cycle274), behind this "
                "BEST system (12-system rebuild 2026-10-27)")
    if _ACTIVE == SYSTEM_CYCLE87B:
        return ("cycle87b (BRIEF21 C20a IMPROVED) -- April "
                "BEST system since 2026-10-26: C87-24 + C12 "
                "score-gated dual-pick (score >= "
                "1000.3404785714285, cap 3 live) + C16 "
                "TP-continuation re-entry partner driven by "
                "the stateful walk ledger -- @2.5-pip discovery "
                "n710 / net +6033.02 / leftover 84.47%; audit "
                "n187 / net +1971.36 / leftover 79.06% (BRIEF21 "
                "validated HUGE; app replay EXACT 2026-10-26). "
                "The old C87-24 (cycle87) is April's second "
                "priority in the combined layer")
    if _ACTIVE == SYSTEM_CYCLE60B:
        return ("cycle60b (BRIEF23 C20_STACK IMPROVED) -- January "
                "BEST system since 2026-10-26: C60-03 + C10 FB "
                "breadth veto (breadth_m15 > 0.4) + FB SL x0.60 + "
                "conditional 24h stall cut (pat_score > 0) + C17 "
                "score-gated dual-pick (score >= 972, cap 5) -- "
                "@2.5-pip discovery n355 / net +1984.54 / win "
                "95.21% / leftover 64.23%; audit n101 / net "
                "+550.18 / leftover 67.50% (BRIEF23 validated "
                "HUGE; app replay EXACT 2026-10-26). The old "
                "C60-03 (cycle60) is January's second priority in "
                "the combined layer")
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
    if _ACTIVE == SYSTEM_CYCLE287:
        from core.cycle287_best import (evaluate_cycle287_signals,
                                       fetch_cycle287_m15_frames)
        return evaluate_cycle287_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle287_m15_frames())
    if _ACTIVE == SYSTEM_CYCLE274:
        from core.cycle274_best import (evaluate_cycle274_signals,
                                       fetch_cycle274_m15_frames)
        return evaluate_cycle274_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle274_m15_frames())
    if _ACTIVE == SYSTEM_CYCLE93B:
        from core.cycle93b_best import (evaluate_cycle93b_signals,
                                       fetch_cycle93b_m15_frames)
        return evaluate_cycle93b_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle93b_m15_frames())
    if _ACTIVE == SYSTEM_CYCLE94B:
        from core.cycle94b_best import (evaluate_cycle94b_signals,
                                       fetch_cycle94b_m15_frames)
        return evaluate_cycle94b_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle94b_m15_frames())
    if _ACTIVE == SYSTEM_CYCLE60B:
        from core.cycle60b_best import (evaluate_cycle60b_signals,
                                        fetch_cycle60b_m15_frames)
        return evaluate_cycle60b_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle60b_m15_frames())
    if _ACTIVE == SYSTEM_CYCLE87B:
        from core.cycle87b_best import (evaluate_cycle87b_signals,
                                        fetch_cycle87b_m15_frames)
        return evaluate_cycle87b_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle87b_m15_frames())
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
    if _ACTIVE == SYSTEM_CYCLE287:
        from core.cycle287_best import select_cycle287_entries
        return select_cycle287_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE274:
        from core.cycle274_best import select_cycle274_entries
        return select_cycle274_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE93B:
        from core.cycle93b_best import select_cycle93b_entries
        return select_cycle93b_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE94B:
        from core.cycle94b_best import select_cycle94b_entries
        return select_cycle94b_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE60B:
        from core.cycle60b_best import select_cycle60b_entries
        # The C17 dual-pick cap counts live positions; the app
        # holds at most one open trade per symbol, so the number
        # of open symbols is the live count.
        return select_cycle60b_entries(
            signals, open_symbols=open_symbols,
            live_count=len({str(s).upper()
                              for s in (open_symbols or ())}))
    if _ACTIVE == SYSTEM_CYCLE87B:
        from core.cycle87b_best import select_cycle87b_entries
        return select_cycle87b_entries(signals,
                                       open_symbols=open_symbols)
    raise ValueError(f"no selector for active system {_ACTIVE!r}")


# ============================================================================
# Combined BEST + SECOND-BEST layer (2026-10-26, user order).
#
# Rule, exactly as ordered: at any check time, the month's BEST cycle
# has priority. The month's SECOND-BEST cycle is evaluated and its
# pick shown ONLY when the best cycle produces NO entry at that
# check time. Months without an in-app second-best module run
# best-only: their recorded second bests are research-only / not
# exactly reproducible in-app (see FIX_NOTES_20261025_WAIVER_INTEGRATION.md).
# As of 2026-10-26 the combined layer covers: September (best
# cycle91, second cycle287, 2026-10-25 waiver), November (best
# cycle93b BRIEF21 C20a, second cycle93), December (best cycle94b
# BRIEF21 C20a, second cycle274 since the 2026-10-27 12-system
# rebuild), January (best cycle60b BRIEF23 C20_STACK, second
# cycle60) and April (best cycle87b BRIEF21 C20a, second
# cycle87). October's internal C155 dual-pick is untouched.
# ============================================================================

def _evaluate_and_select_for(system_name, frames, check_time_utc,
                             open_symbols=()):
    """Evaluate + select one named system through this router.

    The router is global-state based (_ACTIVE); the named system is
    activated for the call and the caller's active system is always
    restored (finally), following the router's existing pattern."""
    global _ACTIVE
    previous = _ACTIVE
    try:
        set_active_system(system_name)
        if system_name in (SYSTEM_CYCLE93B,
                           SYSTEM_CYCLE94B,
                           SYSTEM_CYCLE87B):
            # BRIEF21 C20a systems: the full entries for a check
            # include the C16 re-entry legs, which only the
            # module's ledger-aware panel path can produce.
            mod = __import__(f"core.cycle{system_name[5:]}_best",
                             fromlist=["panel_entries"])
            entries = mod.panel_entries(
                frames, check_time_utc, open_symbols=open_symbols)
            if entries is None or not isinstance(entries,
                                                  pd.DataFrame):
                entries = pd.DataFrame()
            return entries
        signals = evaluate_signals(frames, check_time_utc)
        if signals is None or not isinstance(signals, pd.DataFrame):
            signals = pd.DataFrame()
        if signals.attrs.get("status"):
            return signals
        entries = select_entries(signals, open_symbols=open_symbols)
        if entries is None or not isinstance(entries, pd.DataFrame):
            entries = pd.DataFrame()
        return entries
    finally:
        _ACTIVE = previous


def _tag_combined(entries, system_name, is_second_best):
    """Copy `entries` and tag every row with its combined-layer source."""
    out = entries.copy()
    out["source_system"] = system_name
    out["is_second_best"] = bool(is_second_best)
    return out


def evaluate_combined_entries(month, frames, check_time_utc, open_symbols=()):
    """Combined best-first entries for one month at one check time.

    Returns (entries_df, source) where source is 'BEST' or
    'SECOND_BEST'. The month's BEST system (MONTH_SYSTEMS[month]) is
    evaluated and selected first; if its selection is non-empty it
    is returned tagged source='BEST' and the second-best system is
    NEVER evaluated. Only when the best selection is empty is the
    month's second-best system (MONTH_SECOND_BEST[month], if any)
    evaluated and selected; its selection (possibly empty) is
    returned tagged source='SECOND_BEST'. For months with no in-app
    second best, an empty best selection returns (empty, 'BEST').
    Every returned row carries source_system and is_second_best
    columns."""
    month = int(month)
    if month not in MONTH_SYSTEMS:
        raise ValueError(f"unknown month {month!r}; expected 1..12")
    best = MONTH_SYSTEMS[month]
    best_entries = _evaluate_and_select_for(
        best, frames, check_time_utc, open_symbols=open_symbols)
    # Missing feature data is not a true silent BEST check. Do not choose the
    # second system when the first could not finish its own calculation.
    if best_entries.attrs.get("status"):
        return _tag_combined(best_entries, best, False), "BEST"
    if len(best_entries) > 0:
        return _tag_combined(best_entries, best, False), "BEST"
    second = MONTH_SECOND_BEST.get(month)
    if second is None:
        return _tag_combined(best_entries, best, False), "BEST"
    second_entries = _evaluate_and_select_for(
        second, frames, check_time_utc, open_symbols=open_symbols)
    return _tag_combined(second_entries, second, True), "SECOND_BEST"


def month_combined_info(month):
    """(best_system, second_best_system_or_None) for a month number."""
    month = int(month)
    if month not in MONTH_SYSTEMS:
        raise ValueError(f"unknown month {month!r}; expected 1..12")
    return MONTH_SYSTEMS[month], MONTH_SECOND_BEST.get(month)


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
    if _ACTIVE == SYSTEM_CYCLE287:
        return (1, 10, 11)
    if _ACTIVE == SYSTEM_CYCLE274:
        return (10, 11, 13)
    if _ACTIVE == SYSTEM_CYCLE93B:
        return (9, 13, 15)
    if _ACTIVE == SYSTEM_CYCLE94B:
        return (10, 11, 13)
    if _ACTIVE == SYSTEM_CYCLE60B:
        return (11, 13, 17)
    if _ACTIVE == SYSTEM_CYCLE87B:
        return (16, 17, 18)
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
