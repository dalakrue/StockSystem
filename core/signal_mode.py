"""Live-signal router -- the 12 standing monthly systems ONLY.

2026-10-22 purge (user order): every older cycle system was removed
from this router, the UI selector and the panel renderers. The only
selectable systems are the 12 Program-4 standing winners, one per
month: Jan C60-03, Feb C85-23, Mar C86-24, Apr C87-24, May C88-03,
Jun C89-21, Jul C78-34, Aug C67-04, Sep C91-15, Oct C92-24,
Nov C93-24, Dec C94-23. Each winner module delegates internally to
its frozen incumbent engine (kept in core/ as internal code, NOT
selectable). The trading universe grew from 20 to 29 symbols on
2026-10-27 (see the 29-symbol note below).

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

2026-10-27 changes (user order; 29-symbol build, see
work_29load/BUILD_RESULT.md): the Twelve Data universe grew
from 20 to 29 symbols (the 8 NEW8 FX crosses + DXY), and the
NEW8 layer installs landed behind exact app replay: May best
cycle88n (C88-03 + Round-4 E07 design; May's second becomes
cycle88), June best cycle89n (C89-21 + Plan-B P07; second
becomes cycle89), September best cycle91n (C91-15 + Round-2
D26 then Plan-B P07; second stays cycle287), November best
cycle93n (cycle93b + Plan B-4 partner C16; second becomes
cycle93b, replacing cycle93), October second cycle92e
(Round-4 E07 standalone), August second cycle67p (Plan-B
P07 standalone). February and April are HELD BY USER ORDER:
their NEW8 layers use the Dukascopy dollar index, which the
user will fix himself -- February stays cycle85 best-only
and April stays cycle87b/cycle87 exactly as shipped.
"""
from __future__ import annotations

import pandas as pd

SYSTEM_CYCLE60 = "cycle60"   # C60-03 -- January system
SYSTEM_CYCLE85 = "cycle85"   # C85-23 -- February system
SYSTEM_CYCLE85B = "cycle85b"   # C85-23 + C96-N082 + BRIEF22 C19 -- February IMPROVED system (2026-10-27 update)
SYSTEM_CYCLE86 = "cycle86"   # C86-24 -- March system
SYSTEM_CYCLE86B = "cycle86b"   # C86-24 + BRIEF22 C01 veto -- March IMPROVED system (2026-10-27 update)
SYSTEM_CYCLE87 = "cycle87"   # C87-24 -- April system
SYSTEM_CYCLE88 = "cycle88"   # C88-03 -- May system
SYSTEM_CYCLE89 = "cycle89"   # C89-21 -- June system
SYSTEM_CYCLE78 = "cycle78"   # C78-34 -- July system
SYSTEM_CYCLE78D = "cycle78d"   # R2 Jul D3 (pruned cycle78 + PLANB cand1 C18 fills + B04 cascade fills) -- July IMPROVED system (2026-10-30 install; over cycle78)
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
SYSTEM_CYCLE88N = "cycle88n"   # NEW8 Round-4 E07 -- May IMPROVED system
SYSTEM_CYCLE89N = "cycle89n"   # NEW8 Plan-B P07 -- June IMPROVED system
SYSTEM_CYCLE91N = "cycle91n"   # NEW8 D26 + Plan-B P07 -- September IMPROVED system
SYSTEM_CYCLE93N = "cycle93n"   # NEW8 Plan B-4 partner C16 -- November IMPROVED system
SYSTEM_CYCLE93P = "cycle93p"   # NEW8 Plan B-7 C02 -- November IMPROVED system (2026-10-27 update)
SYSTEM_CYCLE92E = "cycle92e"   # NEW8 Round-4 E07 -- October SECOND-BEST system
SYSTEM_CYCLE67P = "cycle67p"   # NEW8 Plan-B P07 -- August SECOND-BEST system
SYSTEM_CYCLE87C = "cycle87c"   # Plan B-2 Q09 (non-dollar) + P-VOTE C01 -- April IMPROVED system (2026-10-28 update)
SYSTEM_CYCLE89P = "cycle89p"   # NEW8 Plan B-9 C10 -- June IMPROVED system (2026-10-28 update)
SYSTEM_CYCLE91P = "cycle91p"   # NEW8 Plan B-9 C02 + Plan C C06 -- September IMPROVED system (2026-10-28 update)
SYSTEM_CYCLE91Q = "cycle91q"   # R3 Sep R04 (drop 2 DISC-negative FB equations + 7-design pool cascade refill) -- September IMPROVED system (2026-10-31 install; over cycle91p)
SYSTEM_CYCLE93Q = "cycle93q"   # P-BRANCH Plan C C10 -- November IMPROVED system (2026-10-28 update)
SYSTEM_CYCLE91S = "cycle91s"   # NEW8 Plan B-9 Track B R14 -- September SECOND-BEST system (2026-10-28 update, user waiver)
SYSTEM_CYCLE94S = "cycle94s"   # NEW8 Plan B-6 SB-REDO R18 -- December SECOND-BEST system (2026-10-28 phase 2, user order)
SYSTEM_CYCLE86S = "cycle86s"   # NEW8 Plan B-6 SB-REDO R17 -- March SECOND-BEST system (2026-10-28 phase 2, user order)
SYSTEM_CYCLE93S = "cycle93s"   # NEW8 P-BRANCH Track B R12 -- November SECOND-BEST system (2026-10-28 phase 2, user order)
SYSTEM_CYCLE87S = "cycle87s"   # NEW8 P-VOTE Track B fallback R13 -- April SECOND-BEST system (2026-10-28 phase 2, user order)
SYSTEM_CYCLE86C = "cycle86c"   # P-REPLACE Track A C06 -- March IMPROVED system (2026-10-29 update; slot REPLACEMENT over cycle86b+86s)
SYSTEM_CYCLE93R = "cycle93r"   # P-REPLACE Track A C04 -- November IMPROVED system (2026-10-29 update; over cycle93q+93s)
SYSTEM_CYCLE93T = "cycle93t"   # NOV40 R2D11_COMBO (93r combined + B16_FMR_t30 merge + state-conditional cap) -- November IMPROVED system (2026-10-31 install, user conditional order; second-best slot emptied)
SYSTEM_CYCLE94C = "cycle94c"   # P-REGIME Track A C07 + Plan C C07 -- December IMPROVED system (2026-10-29 update; over cycle94b+94s)
SYSTEM_CYCLE85C = "cycle85c"   # R2 Plan A A16 (FB veto + PLANB P38 partner) -- February IMPROVED system (2026-10-30 install; over cycle85b)
SYSTEM_CYCLE85D = "cycle85d"   # R2 Feb A16+X12 combined (85c + X12 cascade second-priority fills) -- February IMPROVED system (2026-10-30 install; over cycle85c)
SYSTEM_CYCLE85E = "cycle85e"   # R3 Feb C01 (85d + CC03-NEW8 cascade layer) -- February IMPROVED system (2026-10-31 install; over cycle85d)
SYSTEM_CYCLE92C = "cycle92c"   # R2 Oct C14 (PLANB9 C09 partner) -- October IMPROVED system (2026-10-30 install; over cycle92+92e)
SYSTEM_CYCLE94D = "cycle94d"   # R2 Dec D19 (PC03 veto + dec_rg/dec_rgc refill + PLANB12C partner) -- December IMPROVED system (2026-10-30 install; over cycle94c)
SYSTEM_CYCLE94E = "cycle94e"   # R3 Dec P15 (94d + PLANB4 cand1 partner cascade) -- December IMPROVED system (2026-10-31 install; over cycle94d)
SYSTEM_CYCLE86D = "cycle86d"   # R2 Mar M18 (PC14 M15 veto + EURAUD h12 b6v slot veto + mar_rp refill) -- March IMPROVED system (2026-10-30 install; over cycle86c)
SYSTEM_CYCLE86E = "cycle86e"   # R3 Mar D10 (86d + dual veto + cool1) -- March IMPROVED system (2026-10-31 install; over cycle86d)
SYSTEM_CYCLE87D = "cycle87d"   # R2 Apr C19 (FB_NZDUSD_h17_0 veto + q09/pvote/pvsb refill + PLANB9C partner) -- April IMPROVED system (2026-10-30 install; over cycle87c)
SYSTEM_CYCLE87E = "cycle87e"   # R3 Apr R01 (87d minus the negative mom_EURAUD strategy + 6-design pool cascade refill) -- April IMPROVED system (2026-10-31 install; over cycle87d)

MONTH_SYSTEMS = {
    1: SYSTEM_CYCLE60B,   # January -- BRIEF23 C20_STACK IMPROVED (2026-10-26)
    2: SYSTEM_CYCLE85E,   # February -- R3 C01 (CC03-NEW8 cascade) IMPROVED (2026-10-31 install)
    3: SYSTEM_CYCLE86E,   # March -- R3 D10 (dual veto + cool1) IMPROVED (2026-10-31 install)
    4: SYSTEM_CYCLE87E,   # April -- R3 R01 IMPROVED (2026-10-31 install)
    5: SYSTEM_CYCLE88N,   # May -- NEW8 E07 IMPROVED (2026-10-27)
    6: SYSTEM_CYCLE89P,   # June -- NEW8 Plan B-9 C10 IMPROVED (2026-10-28 update)
    7: SYSTEM_CYCLE78D,   # July -- R2 D3 IMPROVED (2026-10-30 install)
    8: SYSTEM_CYCLE67,   # August
    9: SYSTEM_CYCLE91Q,   # September -- R3 R04 IMPROVED (2026-10-31 install)
    10: SYSTEM_CYCLE92C,   # October -- R2 C14 IMPROVED (2026-10-30 install)
    11: SYSTEM_CYCLE93T,   # November -- NOV40 R2D11_COMBO IMPROVED (2026-10-31 install)
    12: SYSTEM_CYCLE94E,   # December -- R3 P15 (PLANB4 partner) IMPROVED (2026-10-31 install)
}

# Original verified Best N per system (full values, pre-division).
SYSTEM_BEST_N_FULL = {
    SYSTEM_CYCLE60: 83,   # C60-03 -- January
    SYSTEM_CYCLE85: 104,   # C85-23 -- February
    SYSTEM_CYCLE85B: 104,   # BRIEF22 C19 February improved (as C85-23 + C96-N082)
    SYSTEM_CYCLE86: 86,   # C86-24 -- March
    SYSTEM_CYCLE86B: 86,   # BRIEF22 C01 March improved (as C86-24)
    SYSTEM_CYCLE87: 104,   # C87-24 -- April
    SYSTEM_CYCLE88: 66,   # C88-03 -- May
    SYSTEM_CYCLE89: 84,   # C89-21 -- June
    SYSTEM_CYCLE78: 103,   # C78-34 -- July
    SYSTEM_CYCLE78D: 103,   # R2 D3 July improved (month N carried from cycle78)
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
    SYSTEM_CYCLE88N: 66,   # NEW8 E07 May improved (as C88-03)
    SYSTEM_CYCLE89N: 84,   # NEW8 P07 June improved (as C89-21)
    SYSTEM_CYCLE91N: 83,   # NEW8 D26+P07 September improved (as C91-15)
    SYSTEM_CYCLE93N: 83,   # NEW8 B-4 partner November improved (as C93-24)
    SYSTEM_CYCLE93P: 83,   # NEW8 B-7 November improved (as C93-24; B-7 sizing at Best N=83)
    SYSTEM_CYCLE92E: 83,   # NEW8 E07 October second best (as C92-24)
    SYSTEM_CYCLE67P: 121,   # NEW8 P07 August second best (as C67-04)
    SYSTEM_CYCLE87C: 104,   # B-2 Q09 + P-VOTE April improved (as C87-24)
    SYSTEM_CYCLE89P: 84,   # NEW8 Plan B-9 June improved (as C89-21)
    SYSTEM_CYCLE91P: 83,   # NEW8 Plan B-9 September improved (as C91-15)
    SYSTEM_CYCLE91Q: 83,   # R3 R04 September improved (month N carried from cycle91p)
    SYSTEM_CYCLE93Q: 83,   # P-BRANCH Plan C November improved (as C93-24)
    SYSTEM_CYCLE91S: 83,   # NEW8 Plan B-9 Track B September second best (as C91-15)
    SYSTEM_CYCLE94S: 105,   # NEW8 Plan B-6 SB-REDO December second best (as C94-23)
    SYSTEM_CYCLE86S: 86,   # NEW8 Plan B-6 SB-REDO March second best (as C86-24)
    SYSTEM_CYCLE93S: 83,   # NEW8 P-BRANCH Track B November second best (as C93-24)
    SYSTEM_CYCLE87S: 104,   # NEW8 P-VOTE Track B April second best (as C87-24)
    SYSTEM_CYCLE86C: 86,   # P-REPLACE Track A March improved (as C86-24)
    SYSTEM_CYCLE93R: 83,   # P-REPLACE Track A November improved (as C93-24)
    SYSTEM_CYCLE93T: 83,   # NOV40 R2D11 November improved (month N carried from cycle93r)
    SYSTEM_CYCLE94C: 105,   # P-REGIME Track A + Plan C December improved (as C94-23)
    SYSTEM_CYCLE85C: 104,   # R2 A16 February improved (as C85-23)
    SYSTEM_CYCLE85D: 104,   # R2 A16+X12 February improved (month N carried from cycle85c)
    SYSTEM_CYCLE85E: 104,   # R3 C01 February improved (month N carried from cycle85d)
    SYSTEM_CYCLE92C: 83,   # R2 C14 October improved (as C92-24)
    SYSTEM_CYCLE94D: 105,   # R2 D19 December improved (as C94-23)
    SYSTEM_CYCLE94E: 105,   # R3 P15 December improved (month N carried from cycle94d)
    SYSTEM_CYCLE86D: 86,   # R2 M18 March improved (month N carried from cycle86c)
    SYSTEM_CYCLE86E: 86,   # R3 D10 March improved (month N carried from cycle86d)
    SYSTEM_CYCLE87D: 104,   # R2 C19 April improved (month N carried from cycle87c)
    SYSTEM_CYCLE87E: 104,   # R3 R01 April improved (month N carried from cycle87d)
}

# ACTIVE Best N values (user order 2026-10-26): every month's Best N
# DIVIDED BY 3 -- the exact values of the verified 2026-10-25 div3
# prediction simulation. Position sizing uses these; the full values
# above are kept for reference only.
SYSTEM_BEST_N = {
    SYSTEM_CYCLE60: 27.666666666666668,   # C60-03 -- January (83 / 3)
    SYSTEM_CYCLE85: 34.666666666666664,   # C85-23 -- February (104 / 3)
    SYSTEM_CYCLE85B: 34.666666666666664,   # BRIEF22 C19 February improved (104 / 3)
    SYSTEM_CYCLE86: 28.666666666666668,   # C86-24 -- March (86 / 3)
    SYSTEM_CYCLE86B: 28.666666666666668,   # BRIEF22 C01 March improved (86 / 3)
    SYSTEM_CYCLE87: 34.666666666666664,   # C87-24 -- April (104 / 3)
    SYSTEM_CYCLE88: 22.0,   # C88-03 -- May (66 / 3)
    SYSTEM_CYCLE89: 28.0,   # C89-21 -- June (84 / 3)
    SYSTEM_CYCLE78: 34.333333333333336,   # C78-34 -- July (103 / 3)
    SYSTEM_CYCLE78D: 34.333333333333336,   # R2 D3 July improved (103 / 3)
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
    SYSTEM_CYCLE88N: 22.0,   # NEW8 E07 May improved (66 / 3)
    SYSTEM_CYCLE89N: 28.0,   # NEW8 P07 June improved (84 / 3)
    SYSTEM_CYCLE91N: 27.666666666666668,   # NEW8 D26+P07 September improved (83 / 3)
    SYSTEM_CYCLE93N: 27.666666666666668,   # NEW8 B-4 partner November improved (83 / 3)
    SYSTEM_CYCLE93P: 27.666666666666668,   # NEW8 B-7 November improved (83 / 3)
    SYSTEM_CYCLE92E: 27.666666666666668,   # NEW8 E07 October second best (83 / 3)
    SYSTEM_CYCLE67P: 40.333333333333336,   # NEW8 P07 August second best (121 / 3)
    SYSTEM_CYCLE87C: 34.666666666666664,   # B-2 Q09 + P-VOTE April improved (104 / 3)
    SYSTEM_CYCLE89P: 28.0,   # NEW8 Plan B-9 June improved (84 / 3)
    SYSTEM_CYCLE91P: 27.666666666666668,   # NEW8 Plan B-9 September improved (83 / 3)
    SYSTEM_CYCLE91Q: 27.666666666666668,   # R3 R04 September improved (83 / 3)
    SYSTEM_CYCLE93Q: 27.666666666666668,   # P-BRANCH Plan C November improved (83 / 3)
    SYSTEM_CYCLE91S: 27.666666666666668,   # NEW8 Plan B-9 Track B September second best (83 / 3)
    SYSTEM_CYCLE94S: 35.0,   # NEW8 Plan B-6 SB-REDO December second best (105 / 3)
    SYSTEM_CYCLE86S: 28.666666666666668,   # NEW8 Plan B-6 SB-REDO March second best (86 / 3)
    SYSTEM_CYCLE93S: 27.666666666666668,   # NEW8 P-BRANCH Track B November second best (83 / 3)
    SYSTEM_CYCLE87S: 34.666666666666664,   # NEW8 P-VOTE Track B April second best (104 / 3)
    SYSTEM_CYCLE86C: 28.666666666666668,   # P-REPLACE Track A March improved (86 / 3)
    SYSTEM_CYCLE93R: 27.666666666666668,   # P-REPLACE Track A November improved (83 / 3)
    SYSTEM_CYCLE93T: 27.666666666666668,   # NOV40 R2D11 November improved (83 / 3)
    SYSTEM_CYCLE94C: 35.0,   # P-REGIME Track A + Plan C December improved (105 / 3)
    SYSTEM_CYCLE85C: 34.666666666666664,   # R2 A16 February improved (104 / 3)
    SYSTEM_CYCLE85D: 34.666666666666664,   # R2 A16+X12 February improved (104 / 3)
    SYSTEM_CYCLE85E: 34.666666666666664,   # R3 C01 February improved (104 / 3)
    SYSTEM_CYCLE92C: 27.666666666666668,   # R2 C14 October improved (83 / 3)
    SYSTEM_CYCLE94D: 35.0,   # R2 D19 December improved (105 / 3)
    SYSTEM_CYCLE94E: 35.0,   # R3 P15 December improved (105 / 3)
    SYSTEM_CYCLE86D: 28.666666666666668,   # R2 M18 March improved (86 / 3)
    SYSTEM_CYCLE86E: 28.666666666666668,   # R3 D10 March improved (86 / 3)
    SYSTEM_CYCLE87D: 34.666666666666664,   # R2 C19 April improved (104 / 3)
    SYSTEM_CYCLE87E: 34.666666666666664,   # R3 R01 April improved (104 / 3)
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
    3: SYSTEM_CYCLE86S,   # March -- Plan B-6 SB-REDO R17 behind C01 (2026-10-28 phase 2, user order; slot was empty)
    4: SYSTEM_CYCLE87S,   # April -- P-VOTE Track B fallback R13 behind cycle87c (2026-10-28 phase 2, user order; replaces cycle87)
    5: SYSTEM_CYCLE88,   # May -- old C88-03 behind NEW8 E07 (2026-10-27)
    6: SYSTEM_CYCLE89,   # June -- old C89-21 behind NEW8 P07 (2026-10-27)
    8: SYSTEM_CYCLE67P,   # August -- NEW8 P07 standalone (2026-10-27)
    9: SYSTEM_CYCLE91S,   # September -- Plan B-9 Track B R14 behind cycle91p (2026-10-28 update, user waiver; replaces cycle287)
    10: SYSTEM_CYCLE92E,   # October -- NEW8 E07 standalone (2026-10-27)
    # (November slot EMPTIED 2026-10-31: cycle93t is the full combined stream -- the cycle93s flow is inside the form; running 93s alongside would double-fire. Feb/Jul best-only precedent.)
    12: SYSTEM_CYCLE94S,   # December -- Plan B-6 SB-REDO R18 behind C20a (2026-10-28 phase 2, user order; replaces cycle274)
    # (12-system rebuild 2026-10-27: user confirmed cycle274 is
    # December's kept second best, replacing cycle94 as fallback.
    # 29-symbol build 2026-10-27: November's second best becomes
    # cycle93b -- the NEW8 B-4 combined system's incumbent --
    # replacing cycle93.)
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
    if n not in (SYSTEM_CYCLE60, SYSTEM_CYCLE85, SYSTEM_CYCLE86, SYSTEM_CYCLE87, SYSTEM_CYCLE88, SYSTEM_CYCLE89, SYSTEM_CYCLE78, SYSTEM_CYCLE67, SYSTEM_CYCLE91, SYSTEM_CYCLE92, SYSTEM_CYCLE93, SYSTEM_CYCLE94, SYSTEM_CYCLE287, SYSTEM_CYCLE274, SYSTEM_CYCLE93B, SYSTEM_CYCLE94B, SYSTEM_CYCLE60B, SYSTEM_CYCLE87B, SYSTEM_CYCLE88N, SYSTEM_CYCLE89N, SYSTEM_CYCLE91N, SYSTEM_CYCLE93N, SYSTEM_CYCLE92E, SYSTEM_CYCLE67P, SYSTEM_CYCLE93P, SYSTEM_CYCLE85B, SYSTEM_CYCLE86B, SYSTEM_CYCLE87C, SYSTEM_CYCLE89P, SYSTEM_CYCLE91P, SYSTEM_CYCLE93Q, SYSTEM_CYCLE91S, SYSTEM_CYCLE94S, SYSTEM_CYCLE86S, SYSTEM_CYCLE93S, SYSTEM_CYCLE87S, SYSTEM_CYCLE86C, SYSTEM_CYCLE93R, SYSTEM_CYCLE93T, SYSTEM_CYCLE94C, SYSTEM_CYCLE85C, SYSTEM_CYCLE92C, SYSTEM_CYCLE94D, SYSTEM_CYCLE86D, SYSTEM_CYCLE87D, SYSTEM_CYCLE85D, SYSTEM_CYCLE78D, SYSTEM_CYCLE85E, SYSTEM_CYCLE86E, SYSTEM_CYCLE94E, SYSTEM_CYCLE87E, SYSTEM_CYCLE91Q,):
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
    if _ACTIVE == SYSTEM_CYCLE85B:
        return ("cycle85b (C85-23 + C96-N082 + BRIEF22 C19 "
                "IMPROVED): cycle85 plus the C05 EURUSD "
                "price-vol veto (volr > 1.643, fall-through) "
                "and the loose score-gated dual partner "
                "(score >= 959, cap 3) -- February @2.5-pip "
                "discovery leftover 66.21% -> 76.92% (LCT "
                "middle + strict PASS P 96.63% / q05 60.13%)")
    if _ACTIVE == SYSTEM_CYCLE85:
        return ("cycle85 (C85-23): C56-15 entry engine frozen (hours "
                "11/13/16 delegate to cycle56) minus 4 FB legs "
                "(FB_GBPUSD_h16_2, FB_USDCAD_h13_1, FB_EURGBP_h13_2, "
                "FB_NZDUSD_h11_2) + TP x1.75 on surviving FB trades, "
                "exactly 1 entry/check -- February @2.5-pip net +184.2 "
                "pips / win 85.71% / leftover 29.35% / 2.45 entries/day "
                "(LCT middle PASS P 90.42% / p5 40.14%, Program 4 "
                "promotion, replaced C56-15)")
    if _ACTIVE == SYSTEM_CYCLE86B:
        return ("cycle86b (C86-24 + BRIEF22 C01 IMPROVED): "
                "cycle86 plus the C01 pick-position veto of "
                "FB_EURGBP_h16_2 (fall-through) -- March "
                "@2.5-pip discovery leftover 56.70% -> 59.09%, "
                "audit identical to control (LCT middle + "
                "strict PASS P 95.99% / q05 41.59%)")
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
    if _ACTIVE == SYSTEM_CYCLE78D:
        return ("cycle78d (R2 D3 IMPROVED) -- July "
                "system: cycle78 stream with 4 legs "
                "pruned (FB_AUDUSD_h17_0, FB_EURUSD_h15_0, "
                "FB_USDJPY_h15_2, the USDCAD momB carrier) "
                "+ PLANB cand1 fills at silent checks "
                "(C18 layer) + the B04 second-best "
                "cascade fills (14 pool designs) -- "
                "@2.5-pip 641 picks: DISC leftover "
                "89.11%, AUDIT leftover 77.01% (incumbent "
                "64.97%; LCT P 100% / q05 80.05%, MC flag "
                "TRUE DD p95 172.54 vs cap 188.51, PBO "
                "20% / DSR 1.0; app replay EXACT 641/641, "
                "2026-10-30). July's second-best slot is "
                "folded into this best form (B04); no "
                "separate second system")
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
    if _ACTIVE == SYSTEM_CYCLE88N:
        return ("cycle88n (NEW8 Round-4 E07 IMPROVED) -- May "
                "BEST system since 2026-10-27: C88-03 + the E07 "
                "candidate design (18 equations on GBPCAD) under "
                "incumbent-priority occupancy -- @2.5-pip "
                "discovery leftover 93.70% -> 95.30%, audit "
                "leftover 76.58% -> 79.54%, audit net +170.74 "
                "vs C88-03 alone (user waiver promotion "
                "2026-10-27: LCT P 69.68% below the 80% middle "
                "line waived; MC PASS; app replay EXACT). The "
                "old C88-03 (cycle88) is May's second priority "
                "in the combined layer")
    if _ACTIVE == SYSTEM_CYCLE89N:
        return ("cycle89n (NEW8 Plan-B P07 IMPROVED) -- June "
                "BEST system since 2026-10-27: C89-21 + the P07 "
                "candidate design (22 equations) under "
                "incumbent-priority occupancy -- @2.5-pip "
                "discovery leftover -> 70.48%, audit leftover "
                "-> 46.23% (LCT P 87.83% / q05 59.02%, MC PASS; "
                "app replay EXACT). The old C89-21 (cycle89) is "
                "June's second priority in the combined layer")
    if _ACTIVE == SYSTEM_CYCLE91N:
        return ("cycle91n (NEW8 D26 + Plan-B P07 IMPROVED) -- "
                "September BEST system since 2026-10-27: "
                "C91-15 + the D26 design (16 equations) then "
                "the P07 design (22 equations), each under "
                "incumbent-priority occupancy -- @2.5-pip "
                "discovery leftover 50.21% -> 59.11%, audit "
                "leftover -> 67.36% (MC PASS at both steps; app "
                "replay EXACT). cycle287 stays September's "
                "second priority in the combined layer")
    if _ACTIVE == SYSTEM_CYCLE93P:
        return ("cycle93p (NEW8 Plan B-7 C02 IMPROVED) -- "
                "November system: cycle93n combined + Plan "
                "B-7 candidate C02 layer")
    if _ACTIVE == SYSTEM_CYCLE93N:
        return ("cycle93n (NEW8 Plan B-4 partner C16 IMPROVED) "
                "-- November BEST system since 2026-10-27: "
                "cycle93b (BRIEF21 C20a) + the B-4 partner "
                "design C16 (25 equations, coolv two-loss "
                "cooldown) under incumbent-priority occupancy "
                "-- @2.5-pip discovery leftover 69.03% -> "
                "73.15%, audit leftover -1.95 inside the user's "
                "-2.00 tolerance, audit net +17.62 (LCT P 100% "
                "/ q05 58.66%, MC PASS; app replay EXACT). "
                "cycle93b is November's second priority in the "
                "combined layer")
    if _ACTIVE == SYSTEM_CYCLE92E:
        return ("cycle92e (NEW8 Round-4 E07) -- October "
                "SECOND-BEST system: the standalone E07 "
                "candidate design (18 equations on "
                "GBPAUD/GBPNZD); in research pairing it added "
                "61 of its 241 walk picks over C155 (combined "
                "discovery leftover 85.07%, audit leftover "
                "-4.55 -- rejected as a best-system improvement, "
                "kept as the user-ordered second best; app "
                "replay EXACT). NOT the October default "
                "(C92-24/C155 stands)")
    if _ACTIVE == SYSTEM_CYCLE67P:
        return ("cycle67p (NEW8 Plan-B P07) -- August "
                "SECOND-BEST system: the standalone P07 "
                "candidate design (22 equations); in research "
                "pairing it added 74 of its 143 walk picks over "
                "C67-04 (app replay EXACT). NOT the August "
                "default (C67-04 stands)")
    if _ACTIVE == SYSTEM_CYCLE87C:
        return ("cycle87c (Plan B-2 Q09 non-dollar + P-VOTE "
                "C01 IMPROVED) -- April system: cycle87b + "
                "the Q09 design's 15 FX equations (its 11 "
                "dollar-index equations excluded under the "
                "2026-10-27 dollar purge; the Q09 layer's one "
                "dollar trade is the named exception) + the "
                "P-VOTE C01 vote-share design (30 equations) "
                "-- @2.5-pip combined DISC leftover 84.66%, "
                "AUDIT unchanged vs the B-2 base (LCT P "
                "81.79% / q05 75.04%, MC PASS; app replay "
                "EXACT 2026-10-28). The old C87-24 (cycle87) "
                "is April's second priority in the combined "
                "layer")
    if _ACTIVE == SYSTEM_CYCLE89P:
        return ("cycle89p (NEW8 Plan B-9 C10 IMPROVED) -- "
                "June system: cycle89n + the Plan B-9 Track "
                "A candidate design C10 (30 equations) -- "
                "@2.5-pip discovery leftover 70.48% -> "
                "70.81%, audit leftover 46.23% -> 46.65% "
                "(LCT P 96.02% / q05 59.96%, MC PASS; app "
                "replay EXACT 2026-10-28). The old C89-21 "
                "(cycle89) is June's second priority in the "
                "combined layer")
    if _ACTIVE == SYSTEM_CYCLE91P:
        return ("cycle91p (NEW8 Plan B-9 C02 + Plan C C06 "
                "IMPROVED) -- September system: cycle91n + "
                "the Plan B-9 Track A design C02 (30 "
                "equations) then the Plan C design C06 (45 "
                "equations, M15-heavy) -- @2.5-pip discovery "
                "leftover 59.11% -> 62.69%, audit leftover "
                "67.36% -> 71.50% (LCT 100% at both steps, "
                "MC PASS; app replay EXACT 2026-10-28). "
                "September's second priority in the combined "
                "layer is the Plan B-9 Track B design R14 "
                "(cycle91s, user waiver 2026-10-28)")
    if _ACTIVE == SYSTEM_CYCLE91Q:
        return ("cycle91q (R3 R04 IMPROVE) -- "
                "September system: cycle91p with the "
                "two discovery-negative FB equations "
                "dropped (FB_NZDUSD_h11_1, "
                "FB_GBPJPY_h10_2), refilled by the "
                "seven-design pool cascade (30 "
                "fills) -- @2.5 combined 680 picks: "
                "discovery leftover 73.83%, audit "
                "leftover 72.40% (incumbent 68.60% / "
                "69.49%; LCT-middle 88.35% / 65.96%, "
                "MC PASS, PBO 20% / DSR 0.9999 "
                "family-22, decay PASS; app replay "
                "EXACT 2026-10-31 slim gate: all 7 "
                "pool walks bit-exact, drop control "
                "650/650, combined 680/680). "
                "September's second priority in the "
                "combined layer remains cycle91s")
    if _ACTIVE == SYSTEM_CYCLE93Q:
        return ("cycle93q (P-BRANCH Plan C C10 IMPROVED) "
                "-- November system: cycle93p + the "
                "P-BRANCH Plan C candidate design C10 (12 "
                "OR-branch equations) -- @2.5-pip discovery "
                "leftover 73.88%, audit leftover 39.40% "
                "(LCT P 100% / q05 59.60%, MC PASS, PBO 0%; "
                "cross-lane reconciliation winner; app "
                "replay EXACT 2026-10-28). November's second "
                "priority in the combined layer is the "
                "P-BRANCH Track B design R12 (cycle93s, "
                "phase-2 install 2026-10-28)")
    if _ACTIVE == SYSTEM_CYCLE86C:
        return ("cycle86c (P-REPLACE Track A C06 "
                "IMPROVED) -- March system: cycle86b+86s "
                "combined with 11 (symbol, hour-16) slots "
                "REPLACED by the P-REPLACE candidate design "
                "C06 (30 equations) -- @2.5-pip discovery "
                "leftover 66.10% -> 78.27%, audit leftover "
                "8.84% -> 22.99% (LCT P 100%, MC PASS, PBO "
                "0%, DSR 1.0; lane reconciliation HUGE; "
                "app replay EXACT 2026-10-29). March's "
                "second priority in the combined layer "
                "remains cycle86s")
    if _ACTIVE == SYSTEM_CYCLE93R:
        return ("cycle93r (P-REPLACE Track A C04 "
                "IMPROVED) -- November system: cycle93q+93s "
                "combined + the P-REPLACE candidate design "
                "C04 (30 equations) -- @2.5-pip discovery "
                "leftover 61.60% -> 61.81%, audit leftover "
                "39.40% -> 39.78% (LCT P 99.59%, MC PASS; "
                "app replay EXACT 2026-10-29). November's "
                "second priority in the combined layer "
                "remains cycle93s")
    if _ACTIVE == SYSTEM_CYCLE93T:
        return ("cycle93t (NOV40 R2D11_COMBO IMPROVED) -- "
                "November system: the cycle93r combined "
                "stream (93q + 93s fallback + P-REPLACE C04) "
                "+ the B16_FMR_t30 candidate stream merged "
                "incumbent-priority, settled through the "
                "state-conditional cap (PVOLSIZ weighting; "
                "per-currency 3 high-vol / 4 else, total 5) "
                "-- @2.5-pip discovery leftover 77.05% -> "
                "78.31%, audit leftover 43.44% -> 47.16% "
                "(LCT P 80.72%, MC PASS, EC22 18/18; final "
                "validation 2026-10-31, install record "
                "nov40/INSTALL_R2D11.md). "
                "November has NO second best: the cycle93s "
                "flow is inside this form")
    if _ACTIVE == SYSTEM_CYCLE94C:
        return ("cycle94c (P-REGIME Track A C07 + Plan "
                "C C07 IMPROVED) -- December system: "
                "cycle94b+94s combined + the P-REGIME "
                "Track A design C07 (30 equations) then "
                "the Plan C design C07 (30 equations) -- "
                "@2.5-pip discovery leftover 71.01%, audit "
                "leftover 69.68% (December reconciliation "
                "winner on the user's AUDIT tiebreak; app "
                "replay EXACT 2026-10-29). December's "
                "second priority in the combined layer "
                "remains cycle94s")
    if _ACTIVE == SYSTEM_CYCLE85C:
        return ("cycle85c (R2 Plan A A16 IMPROVED) -- "
                "February system: cycle85b with the "
                "FB_EURUSD_h16_1 equation vetoed pre-select "
                "(fall-through) + the PLANB cand2 partner "
                "design P38 (16 equations, d1v veto; two "
                "DOLLARIDX equations walk for occupancy "
                "only, their rows never emitted) -- @2.5 "
                "combined 480 picks: discovery leftover "
                "82.62%, audit leftover 41.21% (incumbent "
                "37.28%; LCT P 96.40% / 71.83%, MC flag "
                "TRUE DD p95 171.39 vs cap 189.56, PBO 0 "
                "/ DSR 1.0; app replay EXACT 2026-10-30: "
                "control 490, A01 435/435, walk 115/115, "
                "combined 480/480). The R2 A16+X12 combined "
                "form is HELD (X12 cascade not ported); "
                "February has no second-best system")
    if _ACTIVE == SYSTEM_CYCLE85D:
        return ("cycle85d (R2 A16+X12 combined "
                "IMPROVED) -- February system: cycle85c "
                "(A16) + the X12 second-priority cascade "
                "fills (11 pool designs, <=1 fill per "
                "check, symbol-interval combine rules; "
                "DOLLARIDX cascade picks occupy but are "
                "never emitted) -- @2.5 shippable 623 "
                "picks: DISC leftover 83.51%, AUDIT "
                "leftover 42.07% (incumbent 37.28%, A16 "
                "alone 41.21%; LCT P 95.11% / q05 81.37%, "
                "MC flag TRUE DD p95 204.33 vs cap "
                "226.07, PBO 0 / DSR 1.0; app replay "
                "EXACT: 14 walks, X12 576/576, combined "
                "631/631 research form, 2026-10-30). "
                "February has no second-best system")
    if _ACTIVE == SYSTEM_CYCLE85E:
        return ("cycle85e (R3 C01 IMPROVED) -- February "
                "system: cycle85d (A16+X12 combined, 623 "
                "picks) + the C01 layer: the feb_b9cc03 "
                "standalone walk as a second-priority "
                "cascade over the combined base, NEW8 "
                "symbols only, feb_common.cascade "
                "occupancy (one fill per check; blocked "
                "only by same-symbol-at-check or open "
                "overlap) -- @2.5 combined 713 picks: "
                "DISC leftover 90.51%, AUDIT leftover "
                "38.11% (incumbent 34.85%; LCT P 86.47% "
                "/ q05 81.36%, MC middle PASS DD p95 "
                "193.36, PBO 0 / DSR 1.0, decay PASS; "
                "app replay EXACT 2026-10-31: control "
                "623/623, CC03 walk 284/284, combined "
                "713/713). Live caveat: CC03 fills "
                "condition on M15-volume composites and "
                "stay silent on the live Twelve feed "
                "until a volume-bearing feed serves "
                "those columns. February has no "
                "second-best system")
    if _ACTIVE == SYSTEM_CYCLE92C:
        return ("cycle92c (R2 C14 IMPROVED) -- October "
                "system: cycle92 + cycle92e incumbent "
                "stream (REF657) + the PLANB9 cand2 partner "
                "design C09 (30 equations, S-CLU3D) merged "
                "second-priority -- @2.5 combined 700 "
                "picks: discovery leftover 87.68%, audit "
                "leftover 73.35% (incumbent 72.41%; LCT "
                "100.00% / 81.05%, MC PASS, PBO 0 / DSR "
                "1.0; app replay EXACT 2026-10-30: control "
                "657, walk 280/280, combined 700/700). "
                "October's second priority in the "
                "combined layer remains cycle92e")
    if _ACTIVE == SYSTEM_CYCLE94D:
        return ("cycle94d (R2 D19 IMPROVED) -- December "
                "system: cycle94c combined stream screened "
                "by the PC03 M15 veto, refilled by the "
                "dec_rg / dec_rgc walks, + the PLANB12C "
                "cand1 partner design C03 (45 equations) "
                "-- @2.5 combined 908 picks: discovery "
                "leftover 80.93%, audit leftover 57.65% "
                "(incumbent 53.02% on the same form; LCT "
                "95.21% / 75.89%, MC PASS, PBO 0 / DSR 1.0 "
                "canonical; app replay EXACT 2026-10-30: "
                "controls 954/954, partner walk 261/261, "
                "combined 908/908). December's second "
                "priority in the combined layer remains "
                "cycle94s")
    if _ACTIVE == SYSTEM_CYCLE94E:
        return ("cycle94e (R3 P15 IMPROVE (SMALL)) -- "
                "December system: cycle94d combined "
                "stream + the PLANB4 cand1 partner "
                "design (30 equations) as a "
                "second-priority cascade -- @2.5 "
                "combined 913 picks: discovery "
                "leftover 81.19%, audit leftover "
                "57.96% (incumbent 80.93% / 57.65%; "
                "LCT-middle 87.92% / 76.07%, MC PASS, "
                "PBO 0 / DSR 1.0 family-41; app "
                "replay EXACT 2026-10-31 slim gate: "
                "control 908/908, partner walk "
                "114/114, combined 913/913). "
                "December's second priority in the "
                "combined layer remains cycle94s")
    if _ACTIVE == SYSTEM_CYCLE86D:
        return ("cycle86d (R2 M18 IMPROVED) -- March "
                "system: cycle86c+86s combined with the "
                "PC14 M15 veto mask (Bollinger-z / range-pos "
                "/ mom16) + the EURAUD h12 b6v slot veto, "
                "refilled from the mar_rp walk -- @2.5-pip "
                "DISC leftover 79.89%, AUDIT leftover "
                "46.52% (incumbent 22.99%; LCT P 81.72% / "
                "q05 70.70%, MC PASS, PBO 0%, DSR 1.0; app "
                "replay EXACT 557/557, 2026-10-30). March's "
                "second priority in the combined layer "
                "remains cycle86s")
    if _ACTIVE == SYSTEM_CYCLE86E:
        return ("cycle86e (R3 D10 IMPROVED) -- March "
                "system: cycle86d (M18, 557 picks) + "
                "veto of FB_EURGBP_h16_2 and of the "
                "W6 EURAUD h16 leg + the cool1 stateful "
                "filter (skip the next pick after a kept "
                "pick with simulated net <= 0) -- @2.5 "
                "combined 515 picks: DISC leftover "
                "83.23%, AUDIT leftover 56.08% "
                "(incumbent 46.52%; LCT P 87.07% / q05 "
                "76.47%, MC middle PASS DD p95 141.61, "
                "PBO 0 / DSR 1.0, decay PASS; app replay "
                "EXACT 2026-10-31: control 557/557, "
                "dual veto 538, cool1 515/515). Live "
                "caveat: cool1 is not live-causal -- "
                "the panel form resolves a kept pick's "
                "net by re-simulation once its 48h "
                "window closes, so live cooldown timing "
                "differs from the graded ledger rule. "
                "March second-best remains cycle86s")
    if _ACTIVE == SYSTEM_CYCLE87D:
        return ("cycle87d (R2 C19 IMPROVED) -- April "
                "system: cycle87c combined with the "
                "FB_NZDUSD_h17_0 layer vetoed, refilled "
                "from the q09/pvote/pvsb walks + the "
                "PLANB9C cand1 partner (design apr_b9c) "
                "-- @2.5-pip DISC leftover 91.24%, AUDIT "
                "leftover 76.25% (incumbent 71.26%; LCT P "
                "100% / q05 82.96%, MC PASS, PBO 0%, DSR "
                "1.0; app replay EXACT 924, 2026-10-30). "
                "April's second priority in the combined "
                "layer remains cycle87s")
    if _ACTIVE == SYSTEM_CYCLE87E:
        return ("cycle87e (R3 R01 IMPROVE (SMALL)) -- "
                "April system: cycle87d with the single "
                "discovery-negative strategy "
                "mom_EURAUD_h16 dropped, refilled by "
                "the six-design pool cascade (17 "
                "fills) -- @2.5 combined 934 picks: "
                "discovery leftover 92.19%, audit "
                "leftover 76.32% (incumbent 91.24% / "
                "76.25%; LCT-middle 99.59% / 84.83%, "
                "MC PASS (DD p95 174.76), PBO 0 / "
                "DSR 1.0 family-22, decay PASS; app "
                "replay EXACT 2026-10-31 slim gate: "
                "drop control 917/917, combined "
                "934/934). April's second priority "
                "in the combined layer remains "
                "cycle87s")
    if _ACTIVE == SYSTEM_CYCLE91S:
        return ("cycle91s (NEW8 Plan B-9 Track B R14) -- "
                "September SECOND-BEST system: the "
                "standalone R14 design (40 equations, extra "
                "check hour 2 UTC); in research pairing over "
                "cycle91p it added 47 of its 310 walk picks "
                "(combined2 677 trades; installed under the "
                "user's scoped waiver 2026-10-28 of the two "
                "failed creation items; app replay EXACT). "
                "NOT the September default (cycle91p stands)")
    if _ACTIVE == SYSTEM_CYCLE94S:
        return ("cycle94s (NEW8 Plan B-6 SB-REDO R18) -- "
                "December SECOND-BEST system: the standalone "
                "R18 design (60 equations, extra check hour "
                "14 UTC); in app pairing over cycle94b it "
                "added 142 of its 239 walk picks (combined2 "
                "949 trades; installed 2026-10-28 phase 2 on "
                "the user's order, waiving the scan's NEARLY "
                "items; app replay EXACT). NOT the December "
                "default (cycle94c stands)")
    if _ACTIVE == SYSTEM_CYCLE86S:
        return ("cycle86s (NEW8 Plan B-6 SB-REDO R17) -- "
                "March SECOND-BEST system: the standalone "
                "R17 design (40 equations, extra check hour "
                "12 UTC); in research pairing over cycle86b "
                "it added 58 of its 242 walk picks (combined2 "
                "723 trades; installed 2026-10-28 phase 2 on "
                "the user's order, waiving the scan's NEARLY "
                "items; app replay EXACT). NOT the March "
                "default (cycle86c stands)")
    if _ACTIVE == SYSTEM_CYCLE93S:
        return ("cycle93s (NEW8 P-BRANCH Track B R12) -- "
                "November SECOND-BEST system: the standalone "
                "R12 OR-branch design (12 equations, extra "
                "check hour 10 UTC); in research pairing over "
                "cycle93q it added 124 of its 220 walk picks "
                "(combined2 820 trades; installed 2026-10-28 "
                "phase 2 on the user's order, waiving the "
                "scan's NEARLY items; app replay EXACT). NOT "
                "the November default (cycle93r stands)")
    if _ACTIVE == SYSTEM_CYCLE87S:
        return ("cycle87s (NEW8 P-VOTE Track B fallback "
                "R13) -- April SECOND-BEST system: the "
                "standalone R13 vote-threshold design (40 "
                "equations, extra check hour 19 UTC); in "
                "research pairing over cycle87c it added 44 "
                "of its 124 walk picks (combined2 946 trades; "
                "installed 2026-10-28 phase 2 on the user's "
                "order, waiving the scan's NEARLY items; app "
                "replay EXACT). NOT the April default "
                "(cycle87c stands)")
    return "Cycle 60 (C60-03) -- January system"


def evaluate_signals(frames: dict, check_time_utc) -> pd.DataFrame:
    """Evaluate the ACTIVE system's equations at one check time."""
    if _ACTIVE == SYSTEM_CYCLE60:
        from core.cycle60_best import evaluate_cycle60_signals
        return evaluate_cycle60_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE85B:
        from core.cycle85b_best import evaluate_cycle85b_signals
        return evaluate_cycle85b_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE85:
        from core.cycle85_best import evaluate_cycle85_signals
        return evaluate_cycle85_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE86B:
        from core.cycle86b_best import evaluate_cycle86b_signals
        from core.cycle86_best import fetch_cycle86_m15_frames
        return evaluate_cycle86b_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle86_m15_frames())
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
    if _ACTIVE == SYSTEM_CYCLE78D:
        from core.cycle78d_best import (evaluate_cycle78d_signals,
                                        fetch_cycle78d_m15_frames)
        return evaluate_cycle78d_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle78d_m15_frames())
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
    if _ACTIVE == SYSTEM_CYCLE88N:
        from core.cycle88n_best import evaluate_cycle88n_signals
        return evaluate_cycle88n_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE89N:
        from core.cycle89n_best import evaluate_cycle89n_signals
        from core.cycle89_best import fetch_cycle89_m15_frames
        return evaluate_cycle89n_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle89_m15_frames())
    if _ACTIVE == SYSTEM_CYCLE91N:
        from core.cycle91n_best import evaluate_cycle91n_signals
        from core.cycle91_best import fetch_cycle91_m15_frames
        return evaluate_cycle91n_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle91_m15_frames())
    if _ACTIVE == SYSTEM_CYCLE93P:
        from core.cycle93p_best import evaluate_cycle93p_signals
        return evaluate_cycle93p_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE93N:
        from core.cycle93n_best import evaluate_cycle93n_signals
        from core.cycle93b_best import fetch_cycle93b_m15_frames
        return evaluate_cycle93n_signals(
            frames, check_time_utc,
            m15_frames=fetch_cycle93b_m15_frames())
    if _ACTIVE == SYSTEM_CYCLE92E:
        from core.cycle92e_best import evaluate_cycle92e_signals
        return evaluate_cycle92e_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE67P:
        from core.cycle67p_best import evaluate_cycle67p_signals
        return evaluate_cycle67p_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE87C:
        from core.cycle87c_best import evaluate_cycle87c_signals
        return evaluate_cycle87c_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE89P:
        from core.cycle89p_best import evaluate_cycle89p_signals
        return evaluate_cycle89p_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE91P:
        from core.cycle91p_best import evaluate_cycle91p_signals
        return evaluate_cycle91p_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE91Q:
        from core.cycle91q_best import evaluate_cycle91q_signals
        return evaluate_cycle91q_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE93Q:
        from core.cycle93q_best import evaluate_cycle93q_signals
        return evaluate_cycle93q_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE86C:
        from core.cycle86c_best import evaluate_cycle86c_signals
        return evaluate_cycle86c_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE93R:
        from core.cycle93r_best import evaluate_cycle93r_signals
        return evaluate_cycle93r_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE93T:
        from core.cycle93t_best import evaluate_cycle93t_signals
        return evaluate_cycle93t_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE94C:
        from core.cycle94c_best import evaluate_cycle94c_signals
        return evaluate_cycle94c_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE85C:
        from core.cycle85c_best import evaluate_cycle85c_signals
        return evaluate_cycle85c_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE85D:
        from core.cycle85d_best import evaluate_cycle85d_signals
        return evaluate_cycle85d_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE85E:
        from core.cycle85e_best import evaluate_cycle85e_signals
        return evaluate_cycle85e_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE92C:
        from core.cycle92c_best import evaluate_cycle92c_signals
        return evaluate_cycle92c_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE94D:
        from core.cycle94d_best import evaluate_cycle94d_signals
        return evaluate_cycle94d_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE94E:
        from core.cycle94e_best import evaluate_cycle94e_signals
        return evaluate_cycle94e_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE86D:
        from core.cycle86d_best import evaluate_cycle86d_signals
        return evaluate_cycle86d_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE86E:
        from core.cycle86e_best import evaluate_cycle86e_signals
        return evaluate_cycle86e_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE87D:
        from core.cycle87d_best import evaluate_cycle87d_signals
        return evaluate_cycle87d_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE87E:
        from core.cycle87e_best import evaluate_cycle87e_signals
        return evaluate_cycle87e_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE91S:
        from core.cycle91s_best import evaluate_cycle91s_signals
        return evaluate_cycle91s_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE94S:
        from core.cycle94s_best import evaluate_cycle94s_signals
        return evaluate_cycle94s_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE86S:
        from core.cycle86s_best import evaluate_cycle86s_signals
        return evaluate_cycle86s_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE93S:
        from core.cycle93s_best import evaluate_cycle93s_signals
        return evaluate_cycle93s_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE87S:
        from core.cycle87s_best import evaluate_cycle87s_signals
        return evaluate_cycle87s_signals(frames, check_time_utc)
    raise ValueError(f"no evaluator for active system {_ACTIVE!r}")


def select_entries(signals: pd.DataFrame, open_symbols=(), k=2) -> pd.DataFrame:
    """Top-k by score, max 1 open trade per symbol (all systems)."""
    if _ACTIVE == SYSTEM_CYCLE60:
        from core.cycle60_best import select_cycle60_entries
        return select_cycle60_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE85B:
        from core.cycle85b_best import select_cycle85b_entries
        # The C19 dual cap counts live positions; the app
        # holds at most one open trade per symbol, so the
        # number of open symbols is the live count (the
        # cycle60b convention).
        return select_cycle85b_entries(
            signals, open_symbols=open_symbols,
            live_count=len({str(s).upper()
                            for s in (open_symbols or ())}))
    if _ACTIVE == SYSTEM_CYCLE85:
        from core.cycle85_best import select_cycle85_entries
        return select_cycle85_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE86B:
        from core.cycle86b_best import select_cycle86b_entries
        return select_cycle86b_entries(signals, open_symbols=open_symbols)
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
    if _ACTIVE == SYSTEM_CYCLE78D:
        from core.cycle78d_best import select_cycle78d_entries
        return select_cycle78d_entries(signals, open_symbols=open_symbols)
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
    if _ACTIVE == SYSTEM_CYCLE88N:
        from core.cycle88n_best import select_cycle88n_entries
        return select_cycle88n_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE89N:
        from core.cycle89n_best import select_cycle89n_entries
        return select_cycle89n_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE91N:
        from core.cycle91n_best import select_cycle91n_entries
        return select_cycle91n_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE93P:
        from core.cycle93p_best import select_cycle93p_entries
        return select_cycle93p_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE93N:
        from core.cycle93n_best import select_cycle93n_entries
        return select_cycle93n_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE92E:
        from core.cycle92e_best import select_cycle92e_entries
        return select_cycle92e_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE67P:
        from core.cycle67p_best import select_cycle67p_entries
        return select_cycle67p_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE87C:
        from core.cycle87c_best import select_cycle87c_entries
        return select_cycle87c_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE89P:
        from core.cycle89p_best import select_cycle89p_entries
        return select_cycle89p_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE91P:
        from core.cycle91p_best import select_cycle91p_entries
        return select_cycle91p_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE91Q:
        from core.cycle91q_best import select_cycle91q_entries
        return select_cycle91q_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE93Q:
        from core.cycle93q_best import select_cycle93q_entries
        return select_cycle93q_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE86C:
        from core.cycle86c_best import select_cycle86c_entries
        return select_cycle86c_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE93R:
        from core.cycle93r_best import select_cycle93r_entries
        return select_cycle93r_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE93T:
        from core.cycle93t_best import select_cycle93t_entries
        return select_cycle93t_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE94C:
        from core.cycle94c_best import select_cycle94c_entries
        return select_cycle94c_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE85C:
        from core.cycle85c_best import select_cycle85c_entries
        return select_cycle85c_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE85D:
        from core.cycle85d_best import select_cycle85d_entries
        return select_cycle85d_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE85E:
        from core.cycle85e_best import select_cycle85e_entries
        return select_cycle85e_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE92C:
        from core.cycle92c_best import select_cycle92c_entries
        return select_cycle92c_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE94D:
        from core.cycle94d_best import select_cycle94d_entries
        return select_cycle94d_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE94E:
        from core.cycle94e_best import select_cycle94e_entries
        return select_cycle94e_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE86D:
        from core.cycle86d_best import select_cycle86d_entries
        return select_cycle86d_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE86E:
        from core.cycle86e_best import select_cycle86e_entries
        return select_cycle86e_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE87D:
        from core.cycle87d_best import select_cycle87d_entries
        return select_cycle87d_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE87E:
        from core.cycle87e_best import select_cycle87e_entries
        return select_cycle87e_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE91S:
        from core.cycle91s_best import select_cycle91s_entries
        return select_cycle91s_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE94S:
        from core.cycle94s_best import select_cycle94s_entries
        return select_cycle94s_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE86S:
        from core.cycle86s_best import select_cycle86s_entries
        return select_cycle86s_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE93S:
        from core.cycle93s_best import select_cycle93s_entries
        return select_cycle93s_entries(signals,
                                       open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE87S:
        from core.cycle87s_best import select_cycle87s_entries
        return select_cycle87s_entries(signals,
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
# 29-symbol build (2026-10-27): May (best cycle88n NEW8, second
# cycle88), June (best cycle89n NEW8, second cycle89), September
# (best cycle91n NEW8, second cycle287 unchanged), August (best
# cycle67, second cycle67p NEW8), October (best cycle92, second
# cycle92e NEW8) and November (best cycle93n NEW8, second
# cycle93b) join the layer; February, March and July stay
# best-only (February/April NEW8 layers HELD BY USER ORDER --
# February best-only, April keeps cycle87 behind cycle87b).
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
                           SYSTEM_CYCLE87B,
                           SYSTEM_CYCLE88N,
                           SYSTEM_CYCLE89N,
                           SYSTEM_CYCLE91N,
                           SYSTEM_CYCLE93N,
                           SYSTEM_CYCLE93P,
                           SYSTEM_CYCLE87C,
                           SYSTEM_CYCLE89P,
                           SYSTEM_CYCLE91P,
                           SYSTEM_CYCLE91Q,
                           SYSTEM_CYCLE93Q,
                           SYSTEM_CYCLE86C,
                           SYSTEM_CYCLE93R,
                           SYSTEM_CYCLE93T,
                           SYSTEM_CYCLE94C,
                           SYSTEM_CYCLE85C,
                           SYSTEM_CYCLE92C,
                           SYSTEM_CYCLE94D,
                           SYSTEM_CYCLE86D,
                           SYSTEM_CYCLE87D,
                           SYSTEM_CYCLE85D,
                           SYSTEM_CYCLE94E,
                           SYSTEM_CYCLE87E,
                           SYSTEM_CYCLE78D):
            # Ledger-aware systems: the full entries for a check
            # include stateful legs (BRIEF21 C20a re-entries, or
            # the NEW8 merged-walk candidate picks), which only
            # the module's panel path can produce.
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
    if _ACTIVE == SYSTEM_CYCLE85B:
        return (11, 13, 16)
    if _ACTIVE == SYSTEM_CYCLE85:
        return (11, 13, 16)
    if _ACTIVE == SYSTEM_CYCLE86B:
        return (11, 16, 17)
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
    if _ACTIVE == SYSTEM_CYCLE78D:
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
    if _ACTIVE == SYSTEM_CYCLE88N:
        return (10, 16, 18)
    if _ACTIVE == SYSTEM_CYCLE89N:
        return (1, 15, 18)
    if _ACTIVE == SYSTEM_CYCLE91N:
        return (1, 10, 11)
    if _ACTIVE == SYSTEM_CYCLE93P:
        return (9, 13, 15)
    if _ACTIVE == SYSTEM_CYCLE93N:
        return (9, 13, 15)
    if _ACTIVE == SYSTEM_CYCLE92E:
        return (15, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE67P:
        return (1, 6, 16, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE87C:
        return (16, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE89P:
        return (1, 15, 18)
    if _ACTIVE == SYSTEM_CYCLE91P:
        return (1, 10, 11)
    if _ACTIVE == SYSTEM_CYCLE91Q:
        return (1, 2, 10, 11)
    if _ACTIVE == SYSTEM_CYCLE93Q:
        return (9, 13, 15)
    if _ACTIVE == SYSTEM_CYCLE91S:
        return (1, 2, 10, 11)
    if _ACTIVE == SYSTEM_CYCLE94S:
        return (10, 11, 13, 14)
    if _ACTIVE == SYSTEM_CYCLE86S:
        return (11, 12, 16, 17)
    if _ACTIVE == SYSTEM_CYCLE93S:
        return (9, 10, 13, 15)
    if _ACTIVE == SYSTEM_CYCLE87S:
        return (16, 17, 18, 19)
    if _ACTIVE == SYSTEM_CYCLE86C:
        return (11, 16, 17)
    if _ACTIVE == SYSTEM_CYCLE93R:
        return (9, 13, 15)
    if _ACTIVE == SYSTEM_CYCLE93T:
        return (9, 10, 13, 15)
    if _ACTIVE == SYSTEM_CYCLE94C:
        return (10, 11, 13)
    if _ACTIVE == SYSTEM_CYCLE85C:
        return (11, 13, 16)
    if _ACTIVE == SYSTEM_CYCLE85D:
        return (11, 13, 16)
    if _ACTIVE == SYSTEM_CYCLE92C:
        return (15, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE94D:
        return (10, 11, 13)
    if _ACTIVE == SYSTEM_CYCLE94E:
        return (10, 11, 13)
    if _ACTIVE == SYSTEM_CYCLE86D:
        return (11, 16, 17)
    if _ACTIVE == SYSTEM_CYCLE87D:
        return (16, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE87E:
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
