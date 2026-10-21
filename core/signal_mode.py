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

2026-10-21 update (Improvement Program 2, Cycles 49-55, book900):
Cycle 52 (C52-04, January: C28-30's 24 eq + H012 rerank layer) added
as SYSTEM_CYCLE52 -- weak 5 vs 11 at 2.5-pip, unseen net@2.5 +321.6,
win 93.94%, leftover 61.5%; it REPLACES cycle28 as January's default.
Cycle 51 (C51-20, November: 28 eq -- 16 fresh mined + 12 incumbent
fallbacks -- + H023 rerank overlay) added as SYSTEM_CYCLE51 -- weak 4
vs 11, unseen net@2.5 +356.6, win 96.67%, leftover 73.2%; it REPLACES
cycle26 as November's default. Cycle 53 (C53-07, March: C30-31's 24
eq + G013 rerank layer) added as SYSTEM_CYCLE53 -- weak 2 vs 9,
unseen net@2.5 +225.0, win 92.06%, leftover 47.2%; it REPLACES
cycle30 as March's default. Replaced systems remain selectable.
September's program winner (C50-20) was NOT integrated: its winner
logs failed the bit-exact replay verification (coordinator-side
positional-index bug in the trigger-leg simulator), so cycle36 stays
September's default pending a user decision. February/April/August
program-2 near-misses await user override decisions, unchanged.

2026-10-21 update (user override, LCT-gated): Cycle 55 (C55-15,
August-only: 24 eq, all book-900 List D, hours 6/16/17 UTC, up to 2
entries/check, no fallbacks) added as SYSTEM_CYCLE55. C55-15 was
Program 2's August near-miss (failed only the frequency gate:
1.90 vs 2.0 entries/day; weak 0, win 95.00%, leftover 68.7%). The
user ordered its LCT (Left95) test first: it PASSES at both the
middle level (paired P 98.83%, 5th-percentile 86.78%) and the
strict level -- the strongest LCT of any system so far -- and the
user then ordered the promotion with the frequency gate waived.
It REPLACES cycle44 as August's default; cycle44 and cycle35
remain selectable. The cycle55 module uses the REPAIRED Cycle 44
panel (zero-weighted non-finite strength weights -- the constant
USD canonical series otherwise poisons cs_spr*/cs_acc3 with inf/NaN);
cycle44's module keeps the original panel and still reproduces
C44-15 exactly (C44-15 uses no strength features). The UI selector
now auto-defaults August to cycle55.

2026-10-21 update (follow-up round, Cycles 56-59): Cycle 56
(C56-15, February-only: 22 eq -- incumbent surgery + 2 fresh legs)
added as SYSTEM_CYCLE56. C56-15 won the follow-up round: weak 7 vs
11 at 2.5-pip, unseen net@2.5 +124.8, win 86.44%, LCT middle PASS;
it REPLACES cycle29 as February's default. Cycle 29 remains
selectable via set_active_system('cycle29').

2026-10-21 update (follow-up round): Cycle 57 (C57-16,
April-only: 36 eq = C31-29 verbatim + 12 fresh competitor legs)
added as SYSTEM_CYCLE57. C57-16 won the follow-up round: weak 4 vs
6 at 2.5-pip, unseen net@2.5 +372.3, win 90.91%, LCT middle PASS;
it REPLACES cycle31 as April's default. Cycle 31 remains selectable.

2026-10-21 update (follow-up round): Cycle 59 (C59-18,
September-only: 24 eq = C36-40 verbatim + Alligator-ordering rerank
overlay) added as SYSTEM_CYCLE59. C59-18 won the follow-up round:
weak 1 vs 8 at 2.5-pip, unseen net@2.5 +278.1, win 93.94%; it
REPLACES cycle36 as September's default. Cycle 36 remains
selectable.

2026-10-21 update (LCT-fix round): Cycle 65 (C65-01,
June-only: 30 eq = C42-18 verbatim + 6 fresh ASI/Laguerre legs that
only preempt TREND fallbacks) added as SYSTEM_CYCLE65. The Cycle 65
verdict was NO_IMPROVEMENT under the all-gates rule (unseen leftover
57.07% vs the incumbent's 82.67%; weak tied 1 = 1), but C65-01
passes the LCT at the STRICT level against C42-18 (paired P
100.00%, 5th-percentile 41.83%) with discovery net +3,163.8 vs
+1,665.7, and the user promoted it by override. It REPLACES cycle42
as June's default. Cycle 42 remains selectable.

2026-10-21 update (LCT-fix round): Cycle 71 (C71-04,
December-only: 34 eq = C48-02 verbatim + 4 fresh GMMA/Chaikin/
Stochastic-RSI/shadow-pressure legs) added as SYSTEM_CYCLE71.
C71-04 was PROMOTED cleanly: LCT MIDDLE PASS against C48-02
(paired P 99.98%, 5th-percentile 31.25%), unseen net@2.5 +489.1,
win 95.45%, leftover 80.8%, weak 0 (tie allowed -- strictly-less
is impossible against a 0 incumbent). It REPLACES cycle48 as
December's default. Cycle 48 remains selectable.

2026-10-21 update (LCT-fix round): Cycle 70 (C70-07,
November-only: 24 fresh Ehlers Cyber Cycle/Bandpass + TSI +
Random Walk Index equations + 9 TREND fallbacks) added as
SYSTEM_CYCLE70. C70-07 was PROMOTED BY USER OVERRIDE: its
discovery record is the round's strongest (net@2.5 +5,580.8,
0/9 red blocks, leftover 55.74%) and it passed the LCT at BOTH
levels against C51-20 (P 99.33%, 5th-pct 42.22%); the user
waived the unseen leftover gate it failed (31.49% vs 73.23%).
It REPLACES cycle51 as November's default. Cycle 51 remains
selectable.

2026-10-21 update (LCT-fix round): Cycle 64 (C64-09,
May-only: C32-20's 24 equations verbatim + 6 fresh AO / CMO /
Alligator / Qstick / Yang-Zhang legs competing on score) added
as SYSTEM_CYCLE64. C64-09 was PROMOTED BY USER OVERRIDE: the
round's strongest LCT result (paired P 100.00%, 5th-percentile
45.69% -- middle AND strict pass vs C32-20) with discovery net
+3,814.8 vs +2,741.6; the user waived the unseen gates it
failed (leftover 48.3% vs 64.7%, weak 1 vs 0). It REPLACES
cycle32 as May's default. Cycle 32 remains selectable.

2026-10-21 update (LCT-fix round): Cycle 69 (C69-07,
October-only: R4A01's 24 equations verbatim + 9 fresh
tail-penalised Laguerre/ZLEMA/WaveTrend/SRSI/Rainbow legs)
added as SYSTEM_CYCLE69. C69-07 was PROMOTED BY MUSE'S
DECISION under the user's standing rule: it beats R4A01 on
every unseen measure (net +305.3 vs +223.0, leftover 47.7% vs
42.8%, weak 3 vs 8, sizing PASS) with paired LCT P 100.00%
(own 5th-percentile 8.90% misses the middle bar; the only
full-LCT passer lost money unseen -- a red line). It REPLACES
cycle24 as the APP default for October ONLY; the live signal
crons keep running R4A01 unchanged. Cycle 24 remains
selectable.

2026-10-21 update (LCT-fix round): Cycle 63 (C63-04,
April-only: C57-16's 36 equations verbatim + 6 fresh ZigZag
swing-structure legs) added as SYSTEM_CYCLE63. C63-04 was
PROMOTED CLEANLY: weak 4 -> 0, unseen leftover 53.7%, LCT vs
C57-16 PASS at middle AND strict (P 100.0%, 5th-pct 58.2%).
It REPLACES cycle57 as April's default. Cycle 57 remains
selectable.

2026-10-21 update (LCT-fix round): Cycle 66 (C66-08,
July-only: C34-17's 24 equations with a Guppy-ribbon gate on
the 9 TREND fallbacks + 3 fresh EURNZD legs) added as
SYSTEM_CYCLE66. C66-08 was PROMOTED CLEANLY: LCT MIDDLE PASS
vs C34-17 (P 100%, 5th-pct 39.96%), weak 4 -> 1, discovery
leftover 31.27% -> 61.14%, sizing FAIL -> PASS. It REPLACES
cycle34 as July's default. Cycle 34 remains selectable.

2026-10-21 update (LCT-fix round): Cycle 62 (C62-10,
March-only: C30-31's 24 equations walked PLAIN -- no G013
rerank -- + 5 fresh skew/Laguerre/Mass-Index/kurtosis/Elder
legs) added as SYSTEM_CYCLE62. C62-10 was PROMOTED CLEANLY:
LCT MIDDLE PASS vs C53-07 (P 96.74%, 5th-pct 34.59%), weak
2 -> 0, discovery leftover 49.82% beats both ancestors. It
REPLACES cycle53 as March's default. Cycle 53 remains
selectable.

2026-10-21 update (LCT-fix round): Cycle 60 (C60-03,
January-only: the 24 incumbent equations walked PLAIN by
score -- the Cycle 52 H012 rerank is NOT part of it -- + 8
fresh GMMA/TSF/Tillson-T3 compete legs at a flat 1095.0)
added as SYSTEM_CYCLE60. C60-03 was PROMOTED BY MUSE'S
DECISION under the user's standing rule: it passes every
standard gate (weak 5 -> 1, sizing PASS, paired LCT P
98.15%; own 5th-percentile 12.81% misses the bar, and the
round's full-LCT passers all failed unseen -- a red line).
It REPLACES cycle52 as January's default. Cycle 52 remains
selectable.

2026-10-21 update (LCT-fix round): Cycle 67 (C67-04,
August-only: the C55-15 core FROZEN -- core hours delegate
to cycle55 verbatim -- + 8 fresh supplement legs at NEW
hours 1 and 18 UTC) added as SYSTEM_CYCLE67. C67-04 was
PROMOTED BY MUSE'S DECISION under the user's standing
rule: it beats C55-15 on every unseen number (2.48/day --
the frequency flaw fixed -- net +331.1 vs +227.3, leftover
76.1% vs 68.7%, weak 0); its paired LCT P (62.43%) is
structurally capped by the incumbent's 2-loss discovery
record, and its own 5th-percentile is 91.03%. It REPLACES
cycle55 as August's default. Cycle 55 remains selectable
(and remains the frozen core inside cycle67).

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
SYSTEM_CYCLE52 = "cycle52"   # C52-04: 24 eq = C28-30 verbatim + H012 rerank layer,
                             # hours (11,13,17) UTC, exactly 1 entry/check
                             # (January-only; improvement program 2 winner at
                             # 2.5-pip: weak 5, win 93.94%; replaces C28-30)
SYSTEM_CYCLE51 = "cycle51"   # C51-20: 28 eq (16 fresh mined + 12 TREND fallbacks)
                             # + H023 rerank overlay, hours (10,11,18) UTC,
                             # exactly 1 entry/check (November-only; program 2
                             # winner at 2.5-pip: weak 4, win 96.67%; replaces C26-33)
SYSTEM_CYCLE53 = "cycle53"   # C53-07: 24 eq = C30-31 verbatim + G013 rerank layer,
                             # hours (11,16,17) UTC, exactly 1 entry/check
                             # (March-only; program 2 winner at 2.5-pip:
                             # weak 2, win 92.06%; replaces C30-31)
SYSTEM_CYCLE55 = "cycle55"   # C55-15: 24 eq (all book-900 List D, widened pool),
                             # hours (6,16,17) UTC, up to 2 entries/check,
                             # no fallbacks (August-only; program 2 near-miss
                             # promoted by user override after passing the LCT
                             # at middle AND strict: P 98.83%, 5th-pct 86.78%;
                             # weak 0, win 95.00%, 1.90 entries/day; replaces
                             # C44-15; uses the REPAIRED panel)
SYSTEM_CYCLE56 = "cycle56"   # C56-15: 22 eq (13 incumbent mined mom/atr + 2 fresh legs
                             # + 7 TREND fallbacks), hours (11,13,16) UTC, exactly 1 entry/check
                             # (February-only; follow-up-round winner at 2.5-pip:
                             # weak 7, win 86.44%, LCT middle PASS; replaces C29-31)
SYSTEM_CYCLE57 = "cycle57"   # C57-16: 36 eq = C31-29 verbatim (24) + 12 fresh competitor
                             # legs (STC / Camarilla+DeMarker / Heikin-Ashi + vol /
                             # kurtosis gate), hours (16,17,18) UTC, exactly 1 entry/check
                             # (April-only; follow-up-round winner at 2.5-pip: weak 4,
                             # win 90.91%, LCT middle PASS; replaces C31-29)
SYSTEM_CYCLE59 = "cycle59"   # C59-18: 24 eq = C36-40 verbatim + Alligator-ordering rerank
                             # overlay (+400 when SMMA 13/8/5 ordering agrees with
                             # direction), hours (1,10,11) UTC, exactly 1 entry/check
                             # (September-only; follow-up-round winner at 2.5-pip: weak 1,
                             # win 93.94%; replaces C36-40)
SYSTEM_CYCLE65 = "cycle65"   # C65-01: 30 eq = C42-18 verbatim (24) + 6 fresh legs
                             # (Wilder ASI crosses / ASI momentum, Laguerre RSI
                             # zones) scored below the mined legs so they only
                             # preempt TREND fallbacks, hours (1,15,18) UTC,
                             # exactly 1 entry/check (June-only; LCT-fix round:
                             # NO_IMPROVEMENT on gates, user-override promotion
                             # on its strict-level LCT pass; replaces C42-18)
SYSTEM_CYCLE71 = "cycle71"   # C71-04: 34 eq = C48-02 verbatim (30) + 4 fresh legs
                             # (GMMA+Chaikin Vol, SRSI+Shadow Pressure, Chaikin
                             # calm-trend), hours (10,11,13) UTC, exactly 1
                             # entry/check (December-only; LCT-fix round clean
                             # promotion: LCT middle PASS P 99.98% / p5 31.25%;
                             # replaces C48-02)
SYSTEM_CYCLE70 = "cycle70"   # C70-07: 24 fresh eq (Ehlers Cyber Cycle/Bandpass,
                             # TSI, Random Walk Index) + 9 TREND fallbacks, hours
                             # (9,13,15) UTC, exactly 1 entry/check (November-only;
                             # LCT-fix round, user-override promotion: LCT pass at
                             # BOTH levels P 99.33% / p5 42.22%; replaces C51-20)
SYSTEM_CYCLE64 = "cycle64"   # C64-09: 30 eq = C32-20 verbatim (24) + 6 fresh legs
                             # (AO, CMO, Alligator, Qstick, Yang-Zhang), hours
                             # (10,16,18) UTC, exactly 1 entry/check (May-only;
                             # LCT-fix round, user-override promotion: LCT pass at
                             # BOTH levels P 100.00% / p5 45.69%; replaces C32-20)
SYSTEM_CYCLE69 = "cycle69"   # C69-07: 33 eq = R4A01 verbatim (24) + 9 fresh legs
                             # (Laguerre RSI/ZLEMA, WaveTrend, SRSI, Rainbow), hours
                             # (15,17,18) UTC, exactly 1 entry/check (October APP
                             # default only -- live crons keep R4A01; Muse's-decision
                             # promotion: paired LCT P 100.00%, p5 8.90%; replaces R4A01)
SYSTEM_CYCLE63 = "cycle63"   # C63-04: 42 eq = C57-16 verbatim (36) + 6 fresh ZigZag
                             # swing-structure legs, hours (16,17,18) UTC, exactly 1
                             # entry/check (April-only; LCT-fix round CLEAN promotion:
                             # LCT middle+strict PASS P 100.0% / p5 58.2%; replaces C57-16)
SYSTEM_CYCLE66 = "cycle66"   # C66-08: 27 eq = C34-17 (24, fallbacks Guppy-gated) + 3
                             # fresh EURNZD legs (SRSI reversion, ZigZag breakout),
                             # hours (15,17,18) UTC, exactly 1 entry/check (July-only;
                             # LCT-fix round CLEAN promotion: LCT middle PASS
                             # P 100% / p5 39.96%; replaces C34-17)
SYSTEM_CYCLE62 = "cycle62"   # C62-10: 29 eq = C30-31 plain (24, NO G013 rerank) + 5
                             # fresh legs (skew96, Laguerre RSI + Mass Index, kurt48,
                             # Elder Bear Power), hours (11,16,17) UTC, exactly 1
                             # entry/check (March-only; LCT-fix round CLEAN promotion:
                             # LCT middle PASS P 96.74% / p5 34.59%; replaces C53-07)
SYSTEM_CYCLE60 = "cycle60"   # C60-03: 32 eq = incumbent 24 walked PLAIN (no H012
                             # rerank) + 8 fresh GMMA-squeeze / TSF / Tillson-T3 legs
                             # at flat 1095.0, hours (11,13,17) UTC, exactly 1
                             # entry/check (January-only; LCT-fix round, Muse's-
                             # decision promotion: paired LCT P 98.15%, p5 12.81%;
                             # replaces C52-04)
SYSTEM_CYCLE67 = "cycle67"   # C67-04: C55-15 core frozen (delegates to cycle55 at
                             # hours 6/16/17) + 8 fresh supplement legs at NEW hours
                             # 1/18 (TII30, PFE10, permutation entropy, median-25,
                             # Butterworth, RFI, McClellan); up to 2 entries/check;
                             # August-only; LCT-fix round, Muse's-decision promotion
                             # (paired P 62.43% structurally capped, own p5 91.03%;
                             # replaces C55-15)

_ACTIVE = SYSTEM_CYCLE24     # default: Cycle 24 (R4A01), per user decision 2026-10-19


def set_active_system(name: str) -> str:
    """Switch live-signal system. name in {'cycle22', 'cycle18', 'ft-c01',
    'cycle24', 'cycle26', 'cycle27', 'cycle28', 'cycle29', 'cycle30',
    'cycle31', 'cycle32', 'cycle33', 'cycle34', 'cycle35', 'cycle36',
    'cycle48', 'cycle42', 'cycle44', 'cycle52', 'cycle51', 'cycle53',
    'cycle55', 'cycle56', 'cycle57', 'cycle59', 'cycle60', 'cycle62', 'cycle63', 'cycle64', 'cycle65', 'cycle66', 'cycle67', 'cycle69', 'cycle70', 'cycle71'}.
    Returns the newly active system name."""
    global _ACTIVE
    n = str(name).strip().lower()
    if n not in (SYSTEM_CYCLE22, SYSTEM_CYCLE18, SYSTEM_FTC01, SYSTEM_CYCLE24,
                 SYSTEM_CYCLE26, SYSTEM_CYCLE27, SYSTEM_CYCLE28, SYSTEM_CYCLE29,
                 SYSTEM_CYCLE30, SYSTEM_CYCLE31, SYSTEM_CYCLE32, SYSTEM_CYCLE33,
                 SYSTEM_CYCLE34, SYSTEM_CYCLE35, SYSTEM_CYCLE36, SYSTEM_CYCLE48,
                 SYSTEM_CYCLE42, SYSTEM_CYCLE44, SYSTEM_CYCLE52, SYSTEM_CYCLE51,
                 SYSTEM_CYCLE53, SYSTEM_CYCLE55, SYSTEM_CYCLE56, SYSTEM_CYCLE57, SYSTEM_CYCLE59, SYSTEM_CYCLE65, SYSTEM_CYCLE71, SYSTEM_CYCLE70, SYSTEM_CYCLE64, SYSTEM_CYCLE69, SYSTEM_CYCLE63, SYSTEM_CYCLE66, SYSTEM_CYCLE62, SYSTEM_CYCLE60, SYSTEM_CYCLE67):
        raise ValueError(
            f"unknown system {name!r}; choose 'cycle22', 'cycle18', 'ft-c01', "
            f"'cycle24', 'cycle26', 'cycle27', 'cycle28', 'cycle29', 'cycle30', "
            f"'cycle31', 'cycle32', 'cycle33', 'cycle34', 'cycle35', 'cycle36', "
            f"'cycle48', 'cycle42', 'cycle44', 'cycle52', 'cycle51', 'cycle53', "
            f"'cycle55', 'cycle56', 'cycle57', 'cycle59', 'cycle65', 'cycle71', 'cycle70', 'cycle64', 'cycle69', 'cycle63', 'cycle66', 'cycle62', 'cycle60' or 'cycle67'")
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
    if _ACTIVE == SYSTEM_CYCLE52:
        return ("cycle52 (C52-04): 24 equations (C28-30 verbatim) + H012 rerank "
                "layer, entries 11:00/13:00/17:00 UTC "
                "(17:30/19:30/23:30 MMT), exactly 1 entry/check -- "
                "January @2.5-pip net +321.6 pips / win 93.94% / weak 5 "
                "(9/12 checks; improvement-program-2 winner, replaced C28-30)")
    if _ACTIVE == SYSTEM_CYCLE51:
        return ("cycle51 (C51-20): 28 equations (16 fresh mined + 12 TREND "
                "fallbacks) + H023 rerank overlay, entries 10:00/11:00/18:00 UTC "
                "(16:30/17:30/00:30 MMT), exactly 1 entry/check -- "
                "November @2.5-pip net +356.6 pips / win 96.67% / weak 4 "
                "(10/12 checks; improvement-program-2 winner, replaced C26-33)")
    if _ACTIVE == SYSTEM_CYCLE53:
        return ("cycle53 (C53-07): 24 equations (C30-31 verbatim) + G013 rerank "
                "layer, entries 11:00/16:00/17:00 UTC "
                "(17:30/22:30/23:30 MMT), exactly 1 entry/check -- "
                "March @2.5-pip net +225.0 pips / win 92.06% / weak 2 "
                "(10/12 checks; improvement-program-2 winner, replaced C30-31)")
    if _ACTIVE == SYSTEM_CYCLE55:
        return ("cycle55 (C55-15): 24 equations (all book-900 List D, widened "
                "pool, no fallbacks), entries 06:00/16:00/17:00 UTC "
                "(12:30/22:30/23:30 MMT), up to 2 entries/check -- "
                "August @2.5-pip net +227.3 pips / win 95.00% / weak 0 "
                "(10/12 checks; LCT pass middle+strict, user-override "
                "promotion, replaced C44-15)")
    if _ACTIVE == SYSTEM_CYCLE56:
        return ("cycle56 (C56-15): 22 equations (13 incumbent mined + 2 fresh "
                "legs [KST-reversion, CMO trend w/ Rogers-Satchell exits] + 7 "
                "TREND fallbacks), entries 11:00/13:00/16:00 UTC "
                "(17:30/19:30/22:30 MMT), exactly 1 entry/check -- "
                "February @2.5-pip net +124.8 pips / win 86.44% / weak 7 "
                "(10/12 checks; follow-up-round winner, LCT middle PASS, "
                "replaced C29-31)")
    if _ACTIVE == SYSTEM_CYCLE57:
        return ("cycle57 (C57-16): 36 equations (C31-29 verbatim + 12 fresh "
                "competitor legs: Schaff TC, Camarilla+DeMarker, Heikin-Ashi "
                "with RS/YZ vol, kurtosis gate), entries 16:00/17:00/18:00 UTC "
                "(22:30/23:30/00:30 MMT), exactly 1 entry/check -- "
                "April @2.5-pip net +372.3 pips / win 90.91% / weak 4 "
                "(10/12 checks; follow-up-round winner, LCT middle PASS, "
                "replaced C31-29)")
    if _ACTIVE == SYSTEM_CYCLE59:
        return ("cycle59 (C59-18): 24 equations (C36-40 verbatim) + Alligator "
                "ordering rerank overlay (+400 when SMMA 13/8/5 ordering agrees "
                "with direction), entries 01:00/10:00/11:00 UTC "
                "(07:30/16:30/17:30 MMT), exactly 1 entry/check -- "
                "September @2.5-pip net +278.1 pips / win 93.94% / weak 1 "
                "(11/12 checks; follow-up-round winner, replaced C36-40)")
    if _ACTIVE == SYSTEM_CYCLE65:
        return ("cycle65 (C65-01): 30 equations (C42-18 verbatim + 6 fresh "
                "ASI/Laguerre legs preempting only fallbacks), entries "
                "01:00/15:00/18:00 UTC (08:00/22:00/01:00 MMT), exactly 1 "
                "entry/check -- June @2.5-pip net +346.3 pips / win 95.24% / "
                "weak 1 (11/12 checks; LCT strict PASS vs C42-18, "
                "user-override promotion, replaced C42-18)")
    if _ACTIVE == SYSTEM_CYCLE71:
        return ("cycle71 (C71-04): 34 equations (C48-02 verbatim + 4 fresh "
                "GMMA/Chaikin/Stochastic-RSI/shadow legs), entries "
                "10:00/11:00/13:00 UTC (17:00/18:00/20:00 MMT), exactly 1 "
                "entry/check -- December @2.5-pip net +489.1 pips / win "
                "95.45% / weak 0 (11/12 checks; LCT middle PASS, clean "
                "promotion, replaced C48-02)")
    if _ACTIVE == SYSTEM_CYCLE70:
        return ("cycle70 (C70-07): 24 fresh equations (Ehlers Cyber "
                "Cycle/Bandpass + TSI + Random Walk Index) + 9 TREND "
                "fallbacks, entries 09:00/13:00/15:00 UTC "
                "(16:00/20:00/22:00 MMT), exactly 1 entry/check -- "
                "November @2.5-pip net +268.2 pips / win 85.00% / weak 4 "
                "(10/12 checks; LCT pass at BOTH levels, user-override "
                "promotion, replaced C51-20)")
    if _ACTIVE == SYSTEM_CYCLE64:
        return ("cycle64 (C64-09): 30 equations (C32-20 verbatim + 6 fresh "
                "AO/CMO/Alligator/Qstick/Yang-Zhang legs), entries "
                "10:00/16:00/18:00 UTC (17:00/23:00/01:00 MMT), exactly 1 "
                "entry/check -- May @2.5-pip net +373.0 pips / win 90.91% / "
                "weak 1 (11/12 checks; LCT pass at BOTH levels, "
                "user-override promotion, replaced C32-20)")
    if _ACTIVE == SYSTEM_CYCLE69:
        return ("cycle69 (C69-07): 33 equations (R4A01 verbatim + 9 fresh "
                "Laguerre/ZLEMA/WaveTrend/SRSI/Rainbow legs), entries "
                "15:00/17:00/18:00 UTC (21:30/23:30/00:30 MMT), exactly 1 "
                "entry/check -- October @2.5-pip net +305.3 pips / win "
                "92.75% / weak 3 (10/12 checks; paired LCT P 100.00%, "
                "Muse's-decision promotion, replaced R4A01 as APP "
                "default -- live crons unchanged)")
    if _ACTIVE == SYSTEM_CYCLE63:
        return ("cycle63 (C63-04): 42 equations (C57-16 verbatim + 6 fresh "
                "ZigZag swing-structure legs), entries 16:00/17:00/18:00 "
                "UTC (23:00/00:00/01:00 MMT), exactly 1 entry/check -- "
                "April @2.5-pip net +571.3 pips / win 90.91% / weak 0 "
                "(11/12 checks; LCT middle+strict PASS, clean promotion, "
                "replaced C57-16)")
    if _ACTIVE == SYSTEM_CYCLE66:
        return ("cycle66 (C66-08): 27 equations (C34-17 with Guppy-gated "
                "TREND fallbacks + 3 fresh EURNZD legs), entries "
                "15:00/17:00/18:00 UTC (21:30/23:30/00:30 MMT), exactly 1 "
                "entry/check -- July @2.5-pip net +477.7 pips / leftover "
                "61.2% / weak 1 (LCT middle PASS, clean promotion, "
                "replaced C34-17)")
    if _ACTIVE == SYSTEM_CYCLE62:
        return ("cycle62 (C62-10): 29 equations (C30-31 plain + 5 fresh "
                "skew/Laguerre/Mass-Index/kurtosis/Elder legs), entries "
                "11:00/16:00/17:00 UTC (18:00/23:00/00:00 MMT), exactly 1 "
                "entry/check -- March @2.5-pip net +277.3 pips / leftover "
                "52.21% / weak 0 (11/12 checks; LCT middle PASS, clean "
                "promotion, replaced C53-07)")
    if _ACTIVE == SYSTEM_CYCLE60:
        return ("cycle60 (C60-03): 32 equations (incumbent 24 walked plain "
                "+ 8 fresh GMMA/TSF/Tillson-T3 legs), entries 11:00/13:00/"
                "17:00 UTC (18:00/20:00/00:00 MMT), exactly 1 entry/check "
                "-- January @2.5-pip net +335.4 pips / leftover 62.3% / "
                "weak 1 (11/12 checks; paired LCT P 98.15%, Muse's-"
                "decision promotion, replaced C52-04)")
    if _ACTIVE == SYSTEM_CYCLE67:
        return ("cycle67 (C67-04): C55-15 core frozen (hours 6/16/17 "
                "delegate to cycle55) + 8 fresh supplement legs at new "
                "hours 01:00/18:00 UTC (08:00/01:00 MMT), up to 2 "
                "entries/check -- August @2.5-pip net +331.1 pips / win "
                "96.15% / leftover 76.1% / weak 0 (11/12 checks; paired "
                "LCT P structurally capped, Muse's-decision promotion, "
                "replaced C55-15)")
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
    if _ACTIVE == SYSTEM_CYCLE52:
        from core.cycle52_best import evaluate_cycle52_signals
        return evaluate_cycle52_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE51:
        from core.cycle51_best import evaluate_cycle51_signals
        return evaluate_cycle51_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE53:
        from core.cycle53_best import evaluate_cycle53_signals
        return evaluate_cycle53_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE55:
        from core.cycle55_best import evaluate_cycle55_signals
        return evaluate_cycle55_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE56:
        from core.cycle56_best import evaluate_cycle56_signals
        return evaluate_cycle56_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE57:
        from core.cycle57_best import evaluate_cycle57_signals
        return evaluate_cycle57_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE59:
        from core.cycle59_best import evaluate_cycle59_signals
        return evaluate_cycle59_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE65:
        from core.cycle65_best import evaluate_cycle65_signals
        return evaluate_cycle65_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE71:
        from core.cycle71_best import evaluate_cycle71_signals
        return evaluate_cycle71_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE70:
        from core.cycle70_best import evaluate_cycle70_signals
        return evaluate_cycle70_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE64:
        from core.cycle64_best import evaluate_cycle64_signals
        return evaluate_cycle64_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE69:
        from core.cycle69_best import evaluate_cycle69_signals
        return evaluate_cycle69_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE63:
        from core.cycle63_best import evaluate_cycle63_signals
        return evaluate_cycle63_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE66:
        from core.cycle66_best import evaluate_cycle66_signals
        return evaluate_cycle66_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE62:
        from core.cycle62_best import evaluate_cycle62_signals
        return evaluate_cycle62_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE60:
        from core.cycle60_best import evaluate_cycle60_signals
        return evaluate_cycle60_signals(frames, check_time_utc)
    if _ACTIVE == SYSTEM_CYCLE67:
        from core.cycle67_best import evaluate_cycle67_signals
        return evaluate_cycle67_signals(frames, check_time_utc)
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
    if _ACTIVE == SYSTEM_CYCLE52:
        from core.cycle52_best import select_cycle52_entries
        return select_cycle52_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE51:
        from core.cycle51_best import select_cycle51_entries
        return select_cycle51_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE53:
        from core.cycle53_best import select_cycle53_entries
        return select_cycle53_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE55:
        from core.cycle55_best import select_cycle55_entries
        return select_cycle55_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE56:
        from core.cycle56_best import select_cycle56_entries
        return select_cycle56_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE57:
        from core.cycle57_best import select_cycle57_entries
        return select_cycle57_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE59:
        from core.cycle59_best import select_cycle59_entries
        return select_cycle59_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE65:
        from core.cycle65_best import select_cycle65_entries
        return select_cycle65_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE71:
        from core.cycle71_best import select_cycle71_entries
        return select_cycle71_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE70:
        from core.cycle70_best import select_cycle70_entries
        return select_cycle70_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE64:
        from core.cycle64_best import select_cycle64_entries
        return select_cycle64_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE69:
        from core.cycle69_best import select_cycle69_entries
        return select_cycle69_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE63:
        from core.cycle63_best import select_cycle63_entries
        return select_cycle63_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE66:
        from core.cycle66_best import select_cycle66_entries
        return select_cycle66_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE62:
        from core.cycle62_best import select_cycle62_entries
        return select_cycle62_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE60:
        from core.cycle60_best import select_cycle60_entries
        return select_cycle60_entries(signals, open_symbols=open_symbols)
    if _ACTIVE == SYSTEM_CYCLE67:
        from core.cycle67_best import select_cycle67_entries
        return select_cycle67_entries(signals, open_symbols=open_symbols)
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
    if _ACTIVE == SYSTEM_CYCLE52:
        return (11, 13, 17)
    if _ACTIVE == SYSTEM_CYCLE51:
        return (10, 11, 18)
    if _ACTIVE == SYSTEM_CYCLE53:
        return (11, 16, 17)
    if _ACTIVE == SYSTEM_CYCLE55:
        return (6, 16, 17)
    if _ACTIVE == SYSTEM_CYCLE56:
        return (11, 13, 16)
    if _ACTIVE == SYSTEM_CYCLE57:
        return (16, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE59:
        return (1, 10, 11)
    if _ACTIVE == SYSTEM_CYCLE65:
        return (1, 15, 18)
    if _ACTIVE == SYSTEM_CYCLE71:
        return (10, 11, 13)
    if _ACTIVE == SYSTEM_CYCLE70:
        return (9, 13, 15)
    if _ACTIVE == SYSTEM_CYCLE64:
        return (10, 16, 18)
    if _ACTIVE == SYSTEM_CYCLE69:
        return (15, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE63:
        return (16, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE66:
        return (15, 17, 18)
    if _ACTIVE == SYSTEM_CYCLE62:
        return (11, 16, 17)
    if _ACTIVE == SYSTEM_CYCLE60:
        return (11, 13, 17)
    if _ACTIVE == SYSTEM_CYCLE67:
        return (1, 6, 16, 17, 18)
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
