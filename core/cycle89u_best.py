"""Cycle R493PPH -- June: design R493-PPH of
the June ROUND 4 CAMPAIGN round R4-093
(2026-11-13) -- the protection clause over
champion R379-PHA in pick-list form, at the
STRICT DOSE: R4-061's P-PHA construction in
every particular except the clause threshold,
raised by the filed ladder step of +3.00 pts
(PROT_T = 41/66 + 0.03). The brief's named
construction (the clause over WDIV-J) was
premise-refuted at stage 1 -- fielded at
R4-039 -- and R4-061 lesson 3 closed the
clause axis on both hosts AT THE FILED DOSE;
the dose was June's one unmeasured clause
cell (erratum E1 in SLATE.md).

STATUS LABEL: IMPROVED MARK EARNED (all four
frozen arms pass) -- NOT VALIDATED (the
screen fails at 86 of 87 wins, so the battery
never ran). Research module only, NOT
installed (no install was ordered or made).
R493-PPH is June's campaign champion by the
mark; champion R379-PHA's installed and
validated standings are untouched.

Construction: both parent fills run over the
same candidate rows, each with its own state
-- the champion's plain fill over the 28 PHA
equations, and the WDIV-J fill (the same
equations under R4-028's week-diversified
re-deal, clause dose disabled). Where the two
books pick identically the pick is kept;
where they differ (135 DISC + 25 AUDIT switch
slots) the WDIV-J pick is proposed and the
clause refuses it iff the composed book's own
running win rate for the slot's calendar year
is at or below PROT_T = 41/66 + 0.03 with at
least one prior pick, AND the switch pick
loses, AND the champion's own pick at the
slot -- the hook-off -- wins. Refused slots
keep the champion's pick; all other switch
slots take the WDIV-J pick. The stage-1
straddle census (filed in SLATE.md before
the read, enumerated on the composed-at-T
trajectory) predicted exactly one new
refusal: AUDIT position 68 (2025), a slot
that sits at running rate 0.7500 on the
champion's own trajectory and enters the
band only on the composed trajectory, whose
own adopted 2025 switches had dragged its
running rate to 5/8. The graded read matched
the census to the slot and the cent.

Its graded lines (GRADING_R4_093.md): DISC
519 / 369 wins / 71.10% / +2,596.43 (DD
118.00, worst DISC year 68.18%, red weeks
4); AUDIT 123 / 86 wins / 69.92% / +485.04
(2024: 41/60, +181.50; 2025: 45/63,
+303.54); worst year 68.18% (2022);
combined DD 118.00, worst pair -62.71,
consec 4; positive 10/10; occupancy
overlaps 0 + 0. Mark arms vs R379-PHA:
wins 86 > 85, worst year 45/66 > 41/66,
survival 118.00 <= 260.47, net +485.04 > 0
-- ALL FOUR PASS, June's third campaign
mark and its first since R4-002's lineage
began; the count holder and the survival
holder are one book for the first time.
The screen fails by ONE win (86 of 87), so
no battery was run; the design is NOT
VALIDATED. Its declared section-9
diagnostic FAILS the DD arm under both
machineries (mc9 p95 191.91 vs cap 177.00,
ratio 1.6264x; gates p95 196.47 vs cap
177.00, ratio 1.6650x; P(profit) 1.0000,
consec and pair/cluster arms pass): the
dose bought one win and 4.45 of mc9 gap
over P-PHA, and the remaining gap is set
by the unchanged DISC segment -- the new
champion does NOT inherit R379-PHA's
section-9-clean shape (mc9 1.316x, gates
PASS), filed at face. June's validation
distance after this round: +1 screen win
on a section-9-clean book, or +1 win plus
a ratio repair on this book's shape.

Construction and grading law: DISCOVERY
2016-2023 fits everything; AUDIT = unseen
2024+2025 read once; cost 2.5 pips all-in;
RR 1:1; SL-first in one bar; 48h cap;
entries Mon-Fri; June check times 07:30 /
21:30 / 00:30 MMT (UTC 01:00 / 15:00 /
18:00); fill law at every covered slot;
28 FX pairs only.
"""
from __future__ import annotations

import datetime as _dt
import os

import numpy as np
import pandas as pd

SYSTEM_NAME = "cycle89u"
STATUS_LABEL = 'NOT VALIDATED — campaign champion installed by user order 2026-11-13; live replay pass; blocker: screen 1 win short'
CYCLE89U_CHECK_HOURS = (1, 15, 18)
SURFACE_GRID = (1, 15, 18)
MAX_HOLD = 48
MAXHOLD_BARS = 192  # 48h on M15
COST_PIPS = 2.5
OFFICE_HOURS = ()

SYMBOLS = ["AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD",
           "CADCHF", "CADJPY", "CHFJPY", "EURAUD", "EURCAD",
           "EURCHF", "EURGBP", "EURJPY", "EURNZD", "EURUSD",
           "GBPAUD", "GBPCAD", "GBPCHF", "GBPJPY", "GBPNZD",
           "GBPUSD", "NZDCAD", "NZDCHF", "NZDJPY", "NZDUSD",
           "USDCAD", "USDCHF", "USDJPY"]
SYM_IDX = {s: i for i, s in enumerate(SYMBOLS)}

BANDS = {"B40": (0.40, 0.60), "B35": (0.35, 0.65),
         "B30": (0.30, 0.70), "B25": (0.25, 0.75),
         "ALL": (0.0, 1.0)}
BUCKET_E1, BUCKET_E2 = 0.45, 0.55

# ---- the 28 equations (DISC-fitted; provenance:
# r079_jun/work/fits79.json, design PHA) ----
EQUATIONS = {
    'AUDCAD': {'geom': 'F25', 'band': 'ALL', 'tau': 0.5, 'prior': 0.498069, 'cells': {(1, 1, 0): 0.51247, (1, -1, 2): 0.480038, (15, 1, 0): 0.496128, (15, -1, 2): 0.501715, (18, 1, 0): 0.445849, (18, -1, 2): 0.546408, (15, 1, 2): 0.429089, (15, -1, 0): 0.568754, (18, 1, 2): 0.467468, (18, -1, 0): 0.530325, (1, 1, 2): 0.48053, (1, -1, 0): 0.517116, (1, 1, 1): 0.514572, (1, -1, 1): 0.482314, (18, 1, 1): 0.494176, (18, -1, 1): 0.502579, (15, 1, 1): 0.489535, (15, -1, 1): 0.507079}},
    'AUDCHF': {'geom': 'F10', 'band': 'ALL', 'tau': 0.5, 'prior': 0.498062, 'cells': {(1, 1, 2): 0.529644, (1, -1, 0): 0.468191, (15, 1, 0): 0.526408, (15, -1, 2): 0.471463, (18, 1, 1): 0.455226, (18, -1, 1): 0.532812, (1, 1, 0): 0.555066, (1, -1, 2): 0.44264, (15, 1, 2): 0.475898, (15, -1, 0): 0.521875, (18, 1, 2): 0.431496, (18, -1, 0): 0.566327, (15, 1, 1): 0.485523, (15, -1, 1): 0.511164, (18, 1, 0): 0.465203, (18, -1, 2): 0.527001, (1, 1, 1): 0.486229, (1, -1, 1): 0.51062}},
    'AUDJPY': {'geom': 'F30', 'band': 'B40', 'tau': 0.5, 'prior': 0.5, 'cells': {(18, 1, 2): 0.504587, (18, -1, 0): 0.495413, (18, 1, 1): 0.522124, (18, -1, 1): 0.477876, (1, 1, 0): 0.495413, (1, -1, 2): 0.504587, (15, 1, 2): 0.486239, (15, -1, 0): 0.513761, (1, 1, 1): 0.5, (1, -1, 1): 0.5, (15, 1, 1): 0.509434, (15, -1, 1): 0.490566, (15, 1, 0): 0.536364, (15, -1, 2): 0.463636, (18, 1, 0): 0.514286, (18, -1, 2): 0.485714, (1, 1, 2): 0.495238, (1, -1, 0): 0.504762}},
    'AUDNZD': {'geom': 'F20', 'band': 'ALL', 'tau': 0.55, 'prior': 0.497104, 'cells': {(1, 1, 1): 0.484962, (1, -1, 1): 0.510172, (15, 1, 0): 0.518138, (15, -1, 2): 0.47294, (18, 1, 0): 0.475901, (18, -1, 2): 0.520845, (1, 1, 0): 0.486689, (1, -1, 2): 0.50413, (18, 1, 1): 0.46484, (18, -1, 1): 0.530413, (18, 1, 2): 0.416921, (18, -1, 0): 0.579712, (15, 1, 1): 0.480597, (15, -1, 1): 0.514495, (1, 1, 2): 0.520387, (1, -1, 0): 0.470936, (15, 1, 2): 0.425339, (15, -1, 0): 0.571407}},
    'AUDUSD': {'geom': 'F15', 'band': 'B40', 'tau': 0.5, 'prior': 0.5, 'cells': {(15, 1, 0): 0.490741, (15, -1, 2): 0.509259, (18, 1, 1): 0.522523, (18, -1, 1): 0.477477, (18, 1, 2): 0.471698, (18, -1, 0): 0.528302, (15, 1, 1): 0.478992, (15, -1, 1): 0.521008, (1, 1, 0): 0.490566, (1, -1, 2): 0.509434, (15, 1, 2): 0.504762, (15, -1, 0): 0.495238, (1, 1, 2): 0.495413, (1, -1, 0): 0.504587, (18, 1, 0): 0.485981, (18, -1, 2): 0.514019, (1, 1, 1): 0.508772, (1, -1, 1): 0.491228}},
    'CADCHF': {'geom': 'A3', 'band': 'B30', 'tau': 0.5, 'prior': 0.497487, 'cells': {(18, 1, 2): 0.449587, (18, -1, 0): 0.546361, (1, 1, 1): 0.535704, (1, -1, 1): 0.460073, (15, 1, 2): 0.529752, (15, -1, 0): 0.46626, (15, 1, 1): 0.47148, (15, -1, 1): 0.51534, (18, 1, 1): 0.510673, (18, -1, 1): 0.485032, (1, 1, 2): 0.50576, (1, -1, 0): 0.490375, (18, 1, 0): 0.465154, (18, -1, 2): 0.530727, (15, 1, 0): 0.50585, (15, -1, 2): 0.490225, (1, 1, 0): 0.50209, (1, -1, 2): 0.493687}},
    'CADJPY': {'geom': 'A3', 'band': 'B40', 'tau': 0.5, 'prior': 0.5, 'cells': {(1, 1, 2): 0.522936, (1, -1, 0): 0.477064, (1, 1, 0): 0.481132, (1, -1, 2): 0.518868, (18, 1, 1): 0.495652, (18, -1, 1): 0.504348, (15, 1, 0): 0.504587, (15, -1, 2): 0.495413, (18, 1, 0): 0.53211, (18, -1, 2): 0.46789, (1, 1, 1): 0.491228, (1, -1, 1): 0.508772, (15, 1, 1): 0.5, (15, -1, 1): 0.5, (18, 1, 2): 0.495327, (18, -1, 0): 0.504673, (15, 1, 2): 0.481132, (15, -1, 0): 0.518868}},
    'CHFJPY': {'geom': 'F25', 'band': 'B30', 'tau': 0.5, 'prior': 0.5, 'cells': {(15, 1, 2): 0.470588, (15, -1, 0): 0.529412, (1, 1, 1): 0.504065, (1, -1, 1): 0.495935, (18, 1, 0): 0.482456, (18, -1, 2): 0.517544, (15, 1, 1): 0.466667, (15, -1, 1): 0.533333, (18, 1, 2): 0.473684, (18, -1, 0): 0.526316, (1, 1, 0): 0.491525, (1, -1, 2): 0.508475, (15, 1, 0): 0.512821, (15, -1, 2): 0.487179, (1, 1, 2): 0.504132, (1, -1, 0): 0.495868, (18, 1, 1): 0.477876, (18, -1, 1): 0.522124}},
    'EURAUD': {'geom': 'A3', 'band': 'B40', 'tau': 0.5, 'prior': 0.494949, 'cells': {(1, 1, 0): 0.471915, (1, -1, 2): 0.518644, (18, 1, 1): 0.499955, (18, -1, 1): 0.491106, (15, 1, 1): 0.504342, (15, -1, 1): 0.486798, (15, 1, 0): 0.490779, (15, -1, 2): 0.499954, (18, 1, 2): 0.478026, (18, -1, 0): 0.513114, (1, 1, 1): 0.478771, (1, -1, 1): 0.504194, (15, 1, 2): 0.476805, (15, -1, 0): 0.513842, (1, 1, 2): 0.481936, (1, -1, 0): 0.508964, (18, 1, 0): 0.519, (18, -1, 2): 0.47138}},
    'EURCAD': {'geom': 'F20', 'band': 'ALL', 'tau': 0.5, 'prior': 0.497104, 'cells': {(1, 1, 0): 0.529109, (1, -1, 2): 0.462069, (15, 1, 2): 0.483687, (15, -1, 0): 0.512926, (18, 1, 2): 0.492502, (18, -1, 0): 0.498316, (1, 1, 2): 0.492589, (1, -1, 0): 0.504083, (15, 1, 0): 0.503861, (15, -1, 2): 0.492991, (18, 1, 0): 0.469367, (18, -1, 2): 0.522277, (18, 1, 1): 0.506343, (18, -1, 1): 0.488486, (1, 1, 1): 0.493365, (1, -1, 1): 0.501768, (15, 1, 1): 0.472122, (15, -1, 1): 0.52297}},
    'EURCHF': {'geom': 'F30', 'band': 'B30', 'tau': 0.5, 'prior': 0.492347, 'cells': {(18, 1, 0): 0.509354, (18, -1, 2): 0.471475, (18, 1, 2): 0.493514, (18, -1, 0): 0.493514, (1, 1, 0): 0.490486, (1, -1, 2): 0.498005, (1, 1, 2): 0.462771, (1, -1, 0): 0.525271, (15, 1, 1): 0.483952, (15, -1, 1): 0.493043, (18, 1, 1): 0.510644, (18, -1, 1): 0.46754, (15, 1, 0): 0.506072, (15, -1, 2): 0.481278, (15, 1, 2): 0.489713, (15, -1, 0): 0.497843, (1, 1, 1): 0.497693, (1, -1, 1): 0.488997}},
    'EURGBP': {'geom': 'F25', 'band': 'B35', 'tau': 0.5, 'prior': 0.496774, 'cells': {(18, 1, 0): 0.517995, (18, -1, 2): 0.468408, (15, 1, 0): 0.52269, (15, -1, 2): 0.471843, (15, 1, 1): 0.505645, (15, -1, 1): 0.488978, (18, 1, 1): 0.492847, (18, -1, 1): 0.501543, (1, 1, 0): 0.513978, (1, -1, 2): 0.480645, (1, 1, 2): 0.467877, (1, -1, 0): 0.526701, (1, 1, 1): 0.514714, (1, -1, 1): 0.479626, (18, 1, 2): 0.531165, (18, -1, 0): 0.463368, (15, 1, 2): 0.497067, (15, -1, 0): 0.497067}},
    'EURJPY': {'geom': 'A2', 'band': 'B25', 'tau': 0.5, 'prior': 0.5, 'cells': {(15, 1, 0): 0.463415, (15, -1, 2): 0.536585, (18, 1, 0): 0.512, (18, -1, 2): 0.488, (1, 1, 2): 0.453125, (1, -1, 0): 0.546875, (1, 1, 0): 0.522727, (1, -1, 2): 0.477273, (18, 1, 2): 0.55814, (18, -1, 0): 0.44186, (1, 1, 1): 0.487603, (1, -1, 1): 0.512397, (15, 1, 1): 0.543103, (15, -1, 1): 0.456897, (15, 1, 2): 0.512, (15, -1, 0): 0.488, (18, 1, 1): 0.545455, (18, -1, 1): 0.454545}},
    'EURNZD': {'geom': 'F10', 'band': 'B40', 'tau': 0.5, 'prior': 0.494505, 'cells': {(18, 1, 0): 0.475949, (18, -1, 2): 0.513684, (1, 1, 2): 0.480846, (1, -1, 0): 0.508884, (15, 1, 1): 0.460781, (15, -1, 1): 0.521125, (18, 1, 2): 0.508412, (18, -1, 0): 0.481863, (1, 1, 1): 0.486869, (1, -1, 1): 0.503818, (18, 1, 1): 0.485653, (18, -1, 1): 0.504172, (15, 1, 2): 0.494717, (15, -1, 0): 0.494717, (1, 1, 0): 0.508721, (1, -1, 2): 0.481198, (15, 1, 0): 0.513187, (15, -1, 2): 0.476823}},
    'EURUSD': {'geom': 'F15', 'band': 'B40', 'tau': 0.5, 'prior': 0.494624, 'cells': {(1, 1, 0): 0.508829, (1, -1, 2): 0.481306, (1, 1, 1): 0.515699, (1, -1, 1): 0.475699, (15, 1, 0): 0.485215, (15, -1, 2): 0.504446, (18, 1, 1): 0.495112, (18, -1, 1): 0.495112, (18, 1, 0): 0.499655, (18, -1, 2): 0.49048, (15, 1, 1): 0.51649, (15, -1, 1): 0.474474, (18, 1, 2): 0.485763, (18, -1, 0): 0.495022, (1, 1, 2): 0.462265, (1, -1, 0): 0.527686, (15, 1, 2): 0.484925, (15, -1, 0): 0.504533}},
    'GBPAUD': {'geom': 'A2', 'band': 'ALL', 'tau': 0.55, 'prior': 0.499033, 'cells': {(1, 1, 0): 0.467742, (1, -1, 2): 0.531033, (15, 1, 0): 0.458488, (15, -1, 2): 0.540455, (18, 1, 0): 0.489192, (18, -1, 2): 0.509811, (1, 1, 2): 0.47159, (1, -1, 0): 0.522352, (15, 1, 2): 0.455018, (15, -1, 0): 0.543907, (18, 1, 2): 0.46371, (18, -1, 0): 0.535139, (15, 1, 1): 0.499121, (15, -1, 1): 0.499121, (18, 1, 1): 0.526394, (18, -1, 1): 0.471848, (1, 1, 1): 0.511994, (1, -1, 1): 0.486353}},
    'GBPCAD': {'geom': 'F25', 'band': 'ALL', 'tau': 0.5, 'prior': 0.496146, 'cells': {(1, 1, 0): 0.494761, (1, -1, 2): 0.500678, (15, 1, 0): 0.489809, (15, -1, 2): 0.495214, (18, 1, 0): 0.447697, (18, -1, 2): 0.542935, (15, 1, 2): 0.480544, (15, -1, 0): 0.515027, (1, 1, 2): 0.447273, (1, -1, 0): 0.548397, (18, 1, 1): 0.496559, (18, -1, 1): 0.496559, (1, 1, 1): 0.512815, (1, -1, 1): 0.481069, (18, 1, 2): 0.474504, (18, -1, 0): 0.515201, (15, 1, 1): 0.470304, (15, -1, 1): 0.522935}},
    'GBPCHF': {'geom': 'F15', 'band': 'B25', 'tau': 0.5, 'prior': 0.496183, 'cells': {(1, 1, 0): 0.466295, (1, -1, 2): 0.527833, (15, 1, 0): 0.478654, (15, -1, 2): 0.515691, (15, 1, 1): 0.458977, (15, -1, 1): 0.534608, (18, 1, 0): 0.449025, (18, -1, 2): 0.537913, (1, 1, 2): 0.535299, (1, -1, 0): 0.459437, (18, 1, 2): 0.489533, (18, -1, 0): 0.497108, (1, 1, 1): 0.492591, (1, -1, 1): 0.500994, (18, 1, 1): 0.517507, (18, -1, 1): 0.476184, (15, 1, 2): 0.489034, (15, -1, 0): 0.504907}},
    'GBPJPY': {'geom': 'F30', 'band': 'B40', 'tau': 0.5, 'prior': 0.5, 'cells': {(18, 1, 0): 0.509434, (18, -1, 2): 0.490566, (1, 1, 1): 0.516949, (1, -1, 1): 0.483051, (18, 1, 1): 0.478261, (18, -1, 1): 0.521739, (1, 1, 2): 0.490741, (1, -1, 0): 0.509259, (15, 1, 1): 0.504425, (15, -1, 1): 0.495575, (15, 1, 2): 0.514019, (15, -1, 0): 0.485981, (1, 1, 0): 0.509434, (1, -1, 2): 0.490566, (18, 1, 2): 0.508929, (18, -1, 0): 0.491071, (15, 1, 0): 0.5, (15, -1, 2): 0.5}},
    'GBPNZD': {'geom': 'F30', 'band': 'ALL', 'tau': 0.5, 'prior': 0.499033, 'cells': {(1, 1, 0): 0.453959, (1, -1, 2): 0.544868, (15, 1, 0): 0.526941, (15, -1, 2): 0.471996, (18, 1, 0): 0.496775, (18, -1, 2): 0.496775, (1, 1, 2): 0.45783, (1, -1, 0): 0.541163, (15, 1, 1): 0.473304, (15, -1, 1): 0.525028, (18, 1, 1): 0.537002, (18, -1, 1): 0.461372, (15, 1, 2): 0.433733, (15, -1, 0): 0.565162, (18, 1, 2): 0.46371, (18, -1, 0): 0.535139, (1, 1, 1): 0.503507, (1, -1, 1): 0.494811}},
    'GBPUSD': {'geom': 'A2', 'band': 'B25', 'tau': 0.5, 'prior': 0.49345, 'cells': {(18, 1, 0): 0.521074, (18, -1, 2): 0.469222, (1, 1, 2): 0.475916, (1, -1, 0): 0.514084, (15, 1, 1): 0.477112, (15, -1, 1): 0.502974, (15, 1, 2): 0.48707, (15, -1, 0): 0.502695, (18, 1, 2): 0.459409, (18, -1, 0): 0.522401, (1, 1, 0): 0.473125, (1, -1, 2): 0.517242, (15, 1, 0): 0.51476, (15, -1, 2): 0.46676, (1, 1, 1): 0.477112, (1, -1, 1): 0.511595, (18, 1, 1): 0.472565, (18, -1, 1): 0.516043}},
    'NZDCAD': {'geom': 'A2', 'band': 'ALL', 'tau': 0.5, 'prior': 0.499031, 'cells': {(1, 1, 0): 0.514053, (1, -1, 2): 0.484813, (15, 1, 2): 0.418983, (15, -1, 0): 0.579903, (18, 1, 2): 0.40728, (18, -1, 0): 0.586051, (1, 1, 2): 0.529851, (1, -1, 0): 0.469078, (15, 1, 0): 0.521684, (15, -1, 2): 0.477239, (18, 1, 0): 0.439028, (18, -1, 2): 0.559907, (1, 1, 1): 0.503387, (1, -1, 1): 0.494984, (15, 1, 1): 0.478177, (15, -1, 1): 0.520194, (18, 1, 1): 0.476605, (18, -1, 1): 0.52165}},
    'NZDCHF': {'geom': 'A2', 'band': 'ALL', 'tau': 0.5, 'prior': 0.499031, 'cells': {(1, 1, 2): 0.562327, (1, -1, 0): 0.436699, (15, 1, 0): 0.510457, (15, -1, 2): 0.488479, (18, 1, 2): 0.420486, (18, -1, 0): 0.572533, (1, 1, 0): 0.496293, (1, -1, 2): 0.502504, (15, 1, 2): 0.423655, (15, -1, 0): 0.57517, (18, 1, 0): 0.428821, (18, -1, 2): 0.570126, (18, 1, 1): 0.473755, (18, -1, 1): 0.524603, (15, 1, 1): 0.459548, (15, -1, 1): 0.538913, (1, 1, 1): 0.517301, (1, -1, 1): 0.480937}},
    'NZDJPY': {'geom': 'A2', 'band': 'B35', 'tau': 0.5, 'prior': 0.5, 'cells': {(1, 1, 2): 0.537815, (1, -1, 0): 0.462185, (15, 1, 1): 0.495935, (15, -1, 1): 0.504065, (1, 1, 0): 0.495726, (1, -1, 2): 0.504274, (1, 1, 1): 0.482456, (1, -1, 1): 0.517544, (15, 1, 2): 0.472727, (15, -1, 0): 0.527273, (18, 1, 2): 0.491071, (18, -1, 0): 0.508929, (15, 1, 0): 0.490566, (15, -1, 2): 0.509434, (18, 1, 0): 0.529915, (18, -1, 2): 0.470085, (18, 1, 1): 0.463636, (18, -1, 1): 0.536364}},
    'NZDUSD': {'geom': 'A3', 'band': 'B40', 'tau': 0.5, 'prior': 0.494048, 'cells': {(1, 1, 1): 0.469007, (1, -1, 1): 0.520731, (15, 1, 1): 0.525259, (15, -1, 1): 0.464389, (18, 1, 1): 0.481781, (18, -1, 1): 0.499172, (15, 1, 0): 0.494385, (15, -1, 2): 0.494385, (1, 1, 2): 0.49911, (1, -1, 0): 0.489764, (1, 1, 0): 0.503892, (1, -1, 2): 0.484661, (18, 1, 0): 0.484951, (18, -1, 2): 0.503819, (18, 1, 2): 0.494685, (18, -1, 0): 0.494685, (15, 1, 2): 0.489367, (15, -1, 0): 0.499075}},
    'USDCAD': {'geom': 'A3', 'band': 'ALL', 'tau': 0.55, 'prior': 0.498058, 'cells': {(1, 1, 0): 0.493439, (1, -1, 2): 0.504428, (15, 1, 2): 0.51026, (15, -1, 0): 0.487533, (18, 1, 1): 0.507326, (18, -1, 1): 0.489144, (18, 1, 0): 0.468884, (18, -1, 2): 0.523529, (1, 1, 2): 0.458654, (1, -1, 0): 0.539114, (15, 1, 0): 0.498945, (15, -1, 2): 0.49351, (18, 1, 2): 0.510145, (18, -1, 0): 0.487673, (15, 1, 1): 0.502706, (15, -1, 1): 0.493857, (1, 1, 1): 0.511355, (1, -1, 1): 0.485268}},
    'USDCHF': {'geom': 'A2', 'band': 'ALL', 'tau': 0.55, 'prior': 0.496109, 'cells': {(1, 1, 2): 0.478748, (1, -1, 0): 0.516999, (15, 1, 0): 0.533393, (15, -1, 2): 0.45689, (18, 1, 1): 0.488025, (18, -1, 1): 0.505266, (1, 1, 0): 0.532247, (1, -1, 2): 0.463281, (15, 1, 2): 0.44604, (15, -1, 0): 0.549488, (18, 1, 2): 0.431277, (18, -1, 0): 0.552664, (18, 1, 0): 0.500606, (18, -1, 2): 0.489677, (1, 1, 1): 0.500981, (1, -1, 1): 0.492132, (15, 1, 1): 0.518356, (15, -1, 1): 0.474877}},
    'USDJPY': {'geom': 'F15', 'band': 'B35', 'tau': 0.5, 'prior': 0.496377, 'cells': {(1, 1, 0): 0.49703, (1, -1, 2): 0.49703, (18, 1, 1): 0.505904, (18, -1, 1): 0.487386, (1, 1, 1): 0.463031, (1, -1, 1): 0.530828, (15, 1, 2): 0.522739, (15, -1, 0): 0.462394, (18, 1, 2): 0.531359, (18, -1, 0): 0.462394, (1, 1, 2): 0.501177, (1, -1, 0): 0.49263, (18, 1, 0): 0.509893, (18, -1, 2): 0.483806, (15, 1, 0): 0.523979, (15, -1, 2): 0.469433, (15, 1, 1): 0.488256, (15, -1, 1): 0.505497}},
}


LOSE_WEEKS = {
    ('AUDCAD', 18, -1, 2, 26),
    ('AUDCHF', 1, 1, 0, 23),
    ('AUDCHF', 1, 1, 0, 25),
    ('AUDNZD', 15, -1, 0, 23),
    ('EURJPY', 15, -1, 2, 24),
    ('GBPCAD', 1, -1, 0, 24),
    ('GBPCHF', 1, 1, 2, 23),
    ('GBPCHF', 15, -1, 1, 26),
    ('GBPNZD', 1, -1, 0, 23),
    ('GBPNZD', 1, -1, 2, 24),
    ('GBPNZD', 1, -1, 2, 26),
    ('GBPNZD', 15, -1, 0, 22),
    ('GBPNZD', 15, -1, 0, 23),
    ('NZDCAD', 18, -1, 0, 22),
    ('NZDCAD', 18, -1, 2, 23),
    ('NZDCHF', 1, 1, 2, 22),
    ('NZDCHF', 1, 1, 2, 24),
    ('NZDCHF', 15, -1, 0, 23),
    ('NZDCHF', 15, -1, 1, 26),
    ('NZDCHF', 15, -1, 1, 27),
    ('NZDCHF', 18, -1, 0, 23),
    ('NZDCHF', 18, -1, 0, 24),
    ('NZDCHF', 18, -1, 0, 27),
    ('NZDCHF', 18, -1, 2, 23),
    ('NZDCHF', 18, -1, 2, 26),
}

# ---- the protection clause dose (R4-039): fitted
# on DISC from the champion control's weakest
# discovery year (2020: 41 wins / 66 picks) ----
PROT_T = 41.0 / 66.0 + 0.03


def _pip_of(sym):
    return 0.01 if "JPY" in sym else 0.0001


def _pos32(h, l, c, idx):
    """Close position in the last-32-M15-bar range
    [0, 1]: (entry close - lowest low of bars
    idx-31..idx) / (highest high - lowest low of
    the same bars); None when unavailable."""
    if idx < 31:
        return None
    hh = float(np.max(h[idx - 31:idx + 1]))
    ll = float(np.min(l[idx - 31:idx + 1]))
    if hh <= ll:
        return None
    return (float(c[idx]) - ll) / (hh - ll)



def _atr14_pips(h, l, c, idx, sym):
    """ATR14 at bar idx, in pips (the universe
    build's atr14 form verbatim); None when
    unavailable or non-positive."""
    if idx < 14:
        return None
    hh = h[idx - 13:idx + 1]
    ll = l[idx - 13:idx + 1]
    pc = c[idx - 14:idx]
    tr = np.maximum(hh - ll, np.maximum(np.abs(hh - pc),
                                        np.abs(ll - pc)))
    v = float(tr.mean())
    if v <= 0:
        return None
    return v / _pip_of(sym)


def _geom_dist(geom, atr_pips):
    """The pick distance in pips under a symbol's
    geometry: fixed pips, or 2.0x / 3.0x ATR14."""
    if geom.startswith("F"):
        return float(geom[1:])
    return (2.0 if geom == "A2" else 3.0) * atr_pips

def _trade_outcome(bars, sym, entry_s, side, dist_pips):
    """(exit_epoch, net25) for one candidate at a
    FIXED pip distance; exit/net are None while the
    trade is unresolved in the available bars and
    the 48h cap bar is not yet present. Locked
    replay form (SL-first in one bar)."""
    ts, _o, h, l, c = bars
    idx = int(np.searchsorted(ts, entry_s - 900))
    if idx >= len(ts) or ts[idx] != entry_s - 900:
        return None, None
    ph = h[idx + 1:idx + 1 + MAXHOLD_BARS]
    pl = l[idx + 1:idx + 1 + MAXHOLD_BARS]
    fwd = ts[idx + 1:idx + 1 + MAXHOLD_BARS]
    entry = float(c[idx])
    pip = _pip_of(sym)
    dist_price = dist_pips * pip
    if side > 0:
        sl_hit = pl <= entry - dist_price
        tp_hit = ph >= entry + dist_price
    else:
        sl_hit = ph >= entry + dist_price
        tp_hit = pl <= entry - dist_price
    isl = int(np.argmax(sl_hit)) if sl_hit.any() \
        else 10 ** 9
    itp = int(np.argmax(tp_hit)) if tp_hit.any() \
        else 10 ** 9
    if isl == 10 ** 9 and itp == 10 ** 9:
        if len(ph) >= MAXHOLD_BARS:
            gross = side * (float(c[idx + MAXHOLD_BARS])
                            - entry) / pip
            return entry_s + MAX_HOLD * 3600, \
                gross - COST_PIPS
        return None, None
    if isl <= itp:
        return int(fwd[isl]) + 900, -dist_pips - COST_PIPS
    return int(fwd[itp]) + 900, dist_pips - COST_PIPS


def _slot_rows(T, m15_bars):
    """Candidate rows for one slot: for every symbol
    with an available entry bar, both sides, each
    carrying its own equation's score / in-band flag
    / own-geometry distance. Canonical order: symbol index,
    side desc (BUY first)."""
    rows = []
    hour = (T % 86400) // 3600
    for sym in SYMBOLS:
        bars = m15_bars.get(sym)
        if bars is None:
            continue
        ts, _o, h, l, c = bars
        idx = int(np.searchsorted(ts, T - 900))
        if idx >= len(ts) or ts[idx] != T - 900 \
                or idx < 31:
            continue
        pos = _pos32(h, l, c, idx)
        if pos is None:
            continue
        eq = EQUATIONS[sym]
        lo, hi = BANDS[eq["band"]]
        entry_px = float(c[idx])
        atr_pips = _atr14_pips(h, l, c, idx, sym)
        if atr_pips is None:
            continue
        dist_s = _geom_dist(eq["geom"], atr_pips)
        for side in (1, -1):
            adj = pos if side > 0 else 1.0 - pos
            bucket = 0 if adj < BUCKET_E1 else \
                (1 if adj < BUCKET_E2 else 2)
            score = float(eq["cells"].get(
                (hour, side, bucket), eq["prior"]))
            xp, net = _trade_outcome(bars, sym, T, side,
                                     dist_s)
            rows.append({
                "sym": sym, "side": side,
                "dist": dist_s,
                "score": score,
                "in_band": bool(lo < adj < hi),
                "entry_px": entry_px,
                "pos_adj": float(adj),
                "exit": xp, "net": net,
                "entry_s": int(T)})
    return rows


def _margin(row):
    return row["score"] - EQUATIONS[row["sym"]]["tau"]


class PwFillState:
    """The R379-PHA fill law in live form, with
    the WDIV-J re-deal and the R4-039 protection
    clause. Slots are
    processed in chronological order; a kept pick
    blocks its symbol until its candle-replayed
    exit; an unresolved pick blocks until resolved
    (resolve_pending)."""

    def __init__(self):
        self.max_exit = {}
        self.picks = []
        self.year_state = {}
        self.ev = {e: {"slots_total": 0, "picks": 0,
                       "unfilled_no_rows": 0,
                       "unfilled_all_blocked": 0,
                       "tier2": 0, "tier3": 0,
                       "refusals": 0}
                   for e in ("disc", "audit")}

    def to_dict(self):
        return {
            "max_exit": {k: ("inf" if v == float("inf")
                             else v)
                         for k, v in self.max_exit.items()},
            "picks": self.picks,
            "year_state": {str(k): list(v)
                           for k, v in
                           self.year_state.items()}}

    def from_dict(self, d):
        self.max_exit = {k: (float("inf") if v == "inf"
                             else int(v))
                         for k, v in d.get("max_exit",
                                           {}).items()}
        self.picks = d.get("picks", [])
        self.year_state = {
            int(k): (int(v[0]), int(v[1]))
            for k, v in d.get("year_state",
                              {}).items()}

    def _record(self, row, ts, tier):
        pick = {"sym": row["sym"], "entry_s": int(ts),
                "side": int(row["side"]),
                "dist": float(row["dist"]),
                "entry_px": float(row["entry_px"]),
                "score": float(row["score"]),
                "tier": int(tier),
                "layer": "persym",
                "exit": row["exit"], "net": row["net"]}
        self.picks.append(pick)
        if row["exit"] is None:
            self.max_exit[row["sym"]] = float("inf")
        else:
            self.max_exit[row["sym"]] = max(
                self.max_exit.get(row["sym"], -1),
                int(row["exit"]))
        return pick

    def resolve_pending(self, m15_bars):
        for pick in self.picks:
            if pick["exit"] is not None:
                continue
            bars = m15_bars.get(pick["sym"])
            if bars is None:
                continue
            xp, net = _trade_outcome(
                bars, pick["sym"], pick["entry_s"],
                pick["side"], pick["dist"])
            if xp is None:
                continue
            pick["exit"] = int(xp)
            pick["net"] = float(net)
            ex = [p["exit"] if p["exit"] is not None
                  else float("inf")
                  for p in self.picks
                  if p["sym"] == pick["sym"]]
            self.max_exit[pick["sym"]] = max(ex)

    def process_slot(self, ts, era, rows):
        """The fill law (win ranking): tier 1 =
        highest cell score among firing symbols'
        best in-band rows; tier 2 =
        nearest-to-condition in-band; tier 3 =
        nearest-to-condition any band. Ties:
        canonical order (symbol index, BUY first).
        Returns picked row indices (<= 1)."""
        e = self.ev[era]
        e["slots_total"] += 1
        if not rows:
            e["unfilled_no_rows"] += 1
            return []
        by_sym = {}
        for i, r in enumerate(rows):
            if self.max_exit.get(r["sym"], -1) > ts:
                continue
            by_sym.setdefault(r["sym"], []).append(i)
        if not by_sym:
            e["unfilled_all_blocked"] += 1
            return []

        def best(idxs, keyf):
            return min(idxs, key=lambda i: (
                -keyf(rows[i]), SYM_IDX[rows[i]["sym"]],
                0 if rows[i]["side"] > 0 else 1))

        band_best, any_best = {}, {}
        for sym, idxs in by_sym.items():
            br = [i for i in idxs if rows[i]["in_band"]]
            if br:
                band_best[sym] = best(
                    br, lambda r: r["score"])
            any_best[sym] = best(idxs, _margin)
        firing = {s: i for s, i in band_best.items()
                  if rows[i]["score"]
                  >= EQUATIONS[s]["tau"]}
        # WDIV-J (R4-028): inside the plain tier's
        # competing per-symbol best rows, minimise
        # (overlap, -key); overlap = 1 iff the
        # row's (sym, hour, side, bucket) cell is
        # in LOSE_WEEKS for this slot's ISO week
        # number (era-portable key).
        _wk = _dt.datetime.fromtimestamp(
            int(ts), _dt.timezone.utc).date() \
            .isocalendar()[1]
        _hour = (ts % 86400) // 3600

        def _overlap(i):
            r = rows[i]
            b = 0 if r["pos_adj"] < BUCKET_E1 else \
                (1 if r["pos_adj"] < BUCKET_E2 else 2)
            return 1 if (r["sym"], _hour,
                         r["side"], b,
                         _wk) in LOSE_WEEKS else 0

        def _wpick(pool, keyf):
            return min(pool, key=lambda i: (
                _overlap(i), -keyf(rows[i]),
                SYM_IDX[rows[i]["sym"]],
                0 if rows[i]["side"] > 0 else 1))

        def _ppick(pool, keyf):
            # the hook-off (plain) pick: R4-028's
            # tier_pick key on the same pool --
            # (-key, -margin, canonical order)
            return min(pool, key=lambda i: (
                -keyf(rows[i]), -_margin(rows[i]),
                SYM_IDX[rows[i]["sym"]],
                0 if rows[i]["side"] > 0 else 1))

        if firing:
            pool = list(firing.values())
            keyf = lambda r: r["score"]
            tier = 1
        elif band_best:
            pool = list(band_best.values())
            keyf = _margin
            tier = 2
            e["tier2"] += 1
        else:
            pool = list(any_best.values())
            keyf = _margin
            tier = 3
            e["tier3"] += 1
        pick = _wpick(pool, keyf)
        # PW-J (R4-039): the worst-year protection
        # clause over the WDIV pick. In a protected
        # year, a re-deal is refused iff it would
        # leave the year's running win rate lower
        # than the hook-off pick would.
        if pick != _ppick(pool, keyf):
            plain = _ppick(pool, keyf)
            _yr = _dt.datetime.utcfromtimestamp(
                int(ts)).year
            _py, _wy = self.year_state.get(
                _yr, (0, 0))
            if _py >= 1 and _wy / _py <= PROT_T + 1e-12:
                _rn = rows[pick]["net"]
                _rp = rows[plain]["net"]
                if _rn is not None and _rp is not None:
                    _wn = 1 if _rn > 0 else 0
                    _wp = 1 if _rp > 0 else 0
                    if (_wy + _wn) / (_py + 1) < \
                            (_wy + _wp) / (_py + 1) - 1e-12:
                        pick = plain
                        e["refusals"] += 1
        e["picks"] += 1
        self._record(rows[pick], ts, tier)
        _yr = _dt.datetime.utcfromtimestamp(
            int(ts)).year
        _py, _wy = self.year_state.get(_yr, (0, 0))
        _net = rows[pick]["net"]
        self.year_state[_yr] = (
            _py + 1,
            _wy + (1 if (_net is not None
                         and _net > 0) else 0))
        return [pick]


class ChampFillState:
    """The R3U-A fill law in live form. Slots are
    processed in chronological order; a kept pick
    blocks its symbol until its candle-replayed
    exit; an unresolved pick blocks until resolved
    (resolve_pending)."""

    def __init__(self):
        self.max_exit = {}
        self.picks = []
        self.ev = {e: {"slots_total": 0, "picks": 0,
                       "unfilled_no_rows": 0,
                       "unfilled_all_blocked": 0,
                       "tier2": 0, "tier3": 0}
                   for e in ("disc", "audit")}

    def to_dict(self):
        return {
            "max_exit": {k: ("inf" if v == float("inf")
                             else v)
                         for k, v in self.max_exit.items()},
            "picks": self.picks}

    def from_dict(self, d):
        self.max_exit = {k: (float("inf") if v == "inf"
                             else int(v))
                         for k, v in d.get("max_exit",
                                           {}).items()}
        self.picks = d.get("picks", [])

    def _record(self, row, ts, tier):
        pick = {"sym": row["sym"], "entry_s": int(ts),
                "side": int(row["side"]),
                "dist": float(row["dist"]),
                "entry_px": float(row["entry_px"]),
                "score": float(row["score"]),
                "tier": int(tier),
                "layer": "persym",
                "exit": row["exit"], "net": row["net"]}
        self.picks.append(pick)
        if row["exit"] is None:
            self.max_exit[row["sym"]] = float("inf")
        else:
            self.max_exit[row["sym"]] = max(
                self.max_exit.get(row["sym"], -1),
                int(row["exit"]))
        return pick

    def resolve_pending(self, m15_bars):
        for pick in self.picks:
            if pick["exit"] is not None:
                continue
            bars = m15_bars.get(pick["sym"])
            if bars is None:
                continue
            xp, net = _trade_outcome(
                bars, pick["sym"], pick["entry_s"],
                pick["side"], pick["dist"])
            if xp is None:
                continue
            pick["exit"] = int(xp)
            pick["net"] = float(net)
            ex = [p["exit"] if p["exit"] is not None
                  else float("inf")
                  for p in self.picks
                  if p["sym"] == pick["sym"]]
            self.max_exit[pick["sym"]] = max(ex)

    def process_slot(self, ts, era, rows):
        """The fill law (win ranking): tier 1 =
        highest cell score among firing symbols'
        best in-band rows; tier 2 =
        nearest-to-condition in-band; tier 3 =
        nearest-to-condition any band. Ties:
        canonical order (symbol index, BUY first).
        Returns picked row indices (<= 1)."""
        e = self.ev[era]
        e["slots_total"] += 1
        if not rows:
            e["unfilled_no_rows"] += 1
            return []
        by_sym = {}
        for i, r in enumerate(rows):
            if self.max_exit.get(r["sym"], -1) > ts:
                continue
            by_sym.setdefault(r["sym"], []).append(i)
        if not by_sym:
            e["unfilled_all_blocked"] += 1
            return []

        def best(idxs, keyf):
            return min(idxs, key=lambda i: (
                -keyf(rows[i]), SYM_IDX[rows[i]["sym"]],
                0 if rows[i]["side"] > 0 else 1))

        band_best, any_best = {}, {}
        for sym, idxs in by_sym.items():
            br = [i for i in idxs if rows[i]["in_band"]]
            if br:
                band_best[sym] = best(
                    br, lambda r: r["score"])
            any_best[sym] = best(idxs, _margin)
        firing = {s: i for s, i in band_best.items()
                  if rows[i]["score"]
                  >= EQUATIONS[s]["tau"]}
        if firing:
            pick = best(list(firing.values()),
                        lambda r: r["score"])
            tier = 1
        elif band_best:
            pick = best(list(band_best.values()),
                        _margin)
            tier = 2
            e["tier2"] += 1
        else:
            pick = best(list(any_best.values()),
                        _margin)
            tier = 3
            e["tier3"] += 1
        e["picks"] += 1
        self._record(rows[pick], ts, tier)
        return [pick]

class WdivFillState:
    """The WDIV-J fill (R4-028) in live form:
    the PW fill class with the protection
    clause dose disabled (WDIV_OFF_T = -1.0;
    the ops39 T<0 identity, asserted
    array-exact against the ops28 WDIV fill
    at R4-061 stage 1). Its refusal counter
    never increments. Slots are
    processed in chronological order; a kept pick
    blocks its symbol until its candle-replayed
    exit; an unresolved pick blocks until resolved
    (resolve_pending)."""

    def __init__(self):
        self.max_exit = {}
        self.picks = []
        self.year_state = {}
        self.ev = {e: {"slots_total": 0, "picks": 0,
                       "unfilled_no_rows": 0,
                       "unfilled_all_blocked": 0,
                       "tier2": 0, "tier3": 0,
                       "refusals": 0}
                   for e in ("disc", "audit")}

    def to_dict(self):
        return {
            "max_exit": {k: ("inf" if v == float("inf")
                             else v)
                         for k, v in self.max_exit.items()},
            "picks": self.picks,
            "year_state": {str(k): list(v)
                           for k, v in
                           self.year_state.items()}}

    def from_dict(self, d):
        self.max_exit = {k: (float("inf") if v == "inf"
                             else int(v))
                         for k, v in d.get("max_exit",
                                           {}).items()}
        self.picks = d.get("picks", [])
        self.year_state = {
            int(k): (int(v[0]), int(v[1]))
            for k, v in d.get("year_state",
                              {}).items()}

    def _record(self, row, ts, tier):
        pick = {"sym": row["sym"], "entry_s": int(ts),
                "side": int(row["side"]),
                "dist": float(row["dist"]),
                "entry_px": float(row["entry_px"]),
                "score": float(row["score"]),
                "tier": int(tier),
                "layer": "persym",
                "exit": row["exit"], "net": row["net"]}
        self.picks.append(pick)
        if row["exit"] is None:
            self.max_exit[row["sym"]] = float("inf")
        else:
            self.max_exit[row["sym"]] = max(
                self.max_exit.get(row["sym"], -1),
                int(row["exit"]))
        return pick

    def resolve_pending(self, m15_bars):
        for pick in self.picks:
            if pick["exit"] is not None:
                continue
            bars = m15_bars.get(pick["sym"])
            if bars is None:
                continue
            xp, net = _trade_outcome(
                bars, pick["sym"], pick["entry_s"],
                pick["side"], pick["dist"])
            if xp is None:
                continue
            pick["exit"] = int(xp)
            pick["net"] = float(net)
            ex = [p["exit"] if p["exit"] is not None
                  else float("inf")
                  for p in self.picks
                  if p["sym"] == pick["sym"]]
            self.max_exit[pick["sym"]] = max(ex)

    def process_slot(self, ts, era, rows):
        """The fill law (win ranking): tier 1 =
        highest cell score among firing symbols'
        best in-band rows; tier 2 =
        nearest-to-condition in-band; tier 3 =
        nearest-to-condition any band. Ties:
        canonical order (symbol index, BUY first).
        Returns picked row indices (<= 1)."""
        e = self.ev[era]
        e["slots_total"] += 1
        if not rows:
            e["unfilled_no_rows"] += 1
            return []
        by_sym = {}
        for i, r in enumerate(rows):
            if self.max_exit.get(r["sym"], -1) > ts:
                continue
            by_sym.setdefault(r["sym"], []).append(i)
        if not by_sym:
            e["unfilled_all_blocked"] += 1
            return []

        def best(idxs, keyf):
            return min(idxs, key=lambda i: (
                -keyf(rows[i]), SYM_IDX[rows[i]["sym"]],
                0 if rows[i]["side"] > 0 else 1))

        band_best, any_best = {}, {}
        for sym, idxs in by_sym.items():
            br = [i for i in idxs if rows[i]["in_band"]]
            if br:
                band_best[sym] = best(
                    br, lambda r: r["score"])
            any_best[sym] = best(idxs, _margin)
        firing = {s: i for s, i in band_best.items()
                  if rows[i]["score"]
                  >= EQUATIONS[s]["tau"]}
        # WDIV-J (R4-028): inside the plain tier's
        # competing per-symbol best rows, minimise
        # (overlap, -key); overlap = 1 iff the
        # row's (sym, hour, side, bucket) cell is
        # in LOSE_WEEKS for this slot's ISO week
        # number (era-portable key).
        _wk = _dt.datetime.fromtimestamp(
            int(ts), _dt.timezone.utc).date() \
            .isocalendar()[1]
        _hour = (ts % 86400) // 3600

        def _overlap(i):
            r = rows[i]
            b = 0 if r["pos_adj"] < BUCKET_E1 else \
                (1 if r["pos_adj"] < BUCKET_E2 else 2)
            return 1 if (r["sym"], _hour,
                         r["side"], b,
                         _wk) in LOSE_WEEKS else 0

        def _wpick(pool, keyf):
            return min(pool, key=lambda i: (
                _overlap(i), -keyf(rows[i]),
                SYM_IDX[rows[i]["sym"]],
                0 if rows[i]["side"] > 0 else 1))

        def _ppick(pool, keyf):
            # the hook-off (plain) pick: R4-028's
            # tier_pick key on the same pool --
            # (-key, -margin, canonical order)
            return min(pool, key=lambda i: (
                -keyf(rows[i]), -_margin(rows[i]),
                SYM_IDX[rows[i]["sym"]],
                0 if rows[i]["side"] > 0 else 1))

        if firing:
            pool = list(firing.values())
            keyf = lambda r: r["score"]
            tier = 1
        elif band_best:
            pool = list(band_best.values())
            keyf = _margin
            tier = 2
            e["tier2"] += 1
        else:
            pool = list(any_best.values())
            keyf = _margin
            tier = 3
            e["tier3"] += 1
        pick = _wpick(pool, keyf)
        # PW-J (R4-039): the worst-year protection
        # clause over the WDIV pick. In a protected
        # year, a re-deal is refused iff it would
        # leave the year's running win rate lower
        # than the hook-off pick would.
        if pick != _ppick(pool, keyf):
            plain = _ppick(pool, keyf)
            _yr = _dt.datetime.utcfromtimestamp(
                int(ts)).year
            _py, _wy = self.year_state.get(
                _yr, (0, 0))
            if _py >= 1 and _wy / _py <= WDIV_OFF_T + 1e-12:
                _rn = rows[pick]["net"]
                _rp = rows[plain]["net"]
                if _rn is not None and _rp is not None:
                    _wn = 1 if _rn > 0 else 0
                    _wp = 1 if _rp > 0 else 0
                    if (_wy + _wn) / (_py + 1) < \
                            (_wy + _wp) / (_py + 1) - 1e-12:
                        pick = plain
                        e["refusals"] += 1
        e["picks"] += 1
        self._record(rows[pick], ts, tier)
        _yr = _dt.datetime.utcfromtimestamp(
            int(ts)).year
        _py, _wy = self.year_state.get(_yr, (0, 0))
        _net = rows[pick]["net"]
        self.year_state[_yr] = (
            _py + 1,
            _wy + (1 if (_net is not None
                         and _net > 0) else 0))
        return [pick]


# ---- the WDIV fill's disabled clause dose: a
# running win rate is never <= -1, so the clause
# inside WdivFillState can never fire ----
WDIV_OFF_T = -1.0


class PphaFillState:
    """The R4-061 pick-list composition (October
    R4-053's PARB form on June's champion): both
    parent fills run on the same slot rows, each
    with its own state -- the champion's plain
    fill and the WDIV-J fill. At a slot where the
    two books' picks differ (a switch slot), the
    WDIV-J pick is proposed and the protection
    clause REFUSES it iff the composed book's own
    running win rate for the slot's calendar
    year, strictly before the slot, is at or
    below PROT_T with at least one prior pick,
    AND the WDIV-J pick loses, AND the champion's
    pick (the hook-off) wins; a refused slot
    keeps the champion's pick. Identical picks
    are kept as-is. A taken trade is the source
    book's own trade (its pick dict, copied, with
    the source recorded). One state per era: the
    clause state is era-local, as graded."""

    def __init__(self):
        self.champ = ChampFillState()
        self.wdiv = WdivFillState()
        self.picks = []
        self.srcs = []
        self.yr = {}
        self.ev = {e: {"slots_total": 0, "picks": 0,
                       "refusals": 0, "src_pha": 0,
                       "src_wdv": 0, "src_same": 0}
                   for e in ("disc", "audit")}

    def to_dict(self):
        return {"champ": self.champ.to_dict(),
                "wdiv": self.wdiv.to_dict(),
                "picks": self.picks, "srcs": self.srcs,
                "yr": {str(k): list(v)
                       for k, v in self.yr.items()}}

    def from_dict(self, d):
        if "champ" in d:
            self.champ.from_dict(d["champ"])
        if "wdiv" in d:
            self.wdiv.from_dict(d["wdiv"])
        self.picks = d.get("picks", [])
        self.srcs = d.get("srcs", [])
        self.yr = {int(k): (int(v[0]), int(v[1]))
                   for k, v in d.get("yr", {}).items()}

    def resolve_pending(self, m15_bars):
        self.champ.resolve_pending(m15_bars)
        self.wdiv.resolve_pending(m15_bars)
        by_key = {}
        for f in (self.champ, self.wdiv):
            for pk in f.picks:
                by_key[(pk["entry_s"], pk["sym"],
                        pk["side"])] = pk
        for pk in self.picks:
            q = by_key.get((pk["entry_s"], pk["sym"],
                            pk["side"]))
            if q is not None:
                pk["exit"] = q["exit"]
                pk["net"] = q["net"]

    def process_slot(self, ts, era, rows):
        e = self.ev[era]
        e["slots_total"] += 1
        cp = self.champ.process_slot(ts, era, rows)
        wp = self.wdiv.process_slot(ts, era, rows)
        if not cp and not wp:
            return []
        if cp and not wp:
            take, src, f = cp[0], "pha", self.champ
        elif wp and not cp:
            take, src, f = wp[0], "wdv", self.wdiv
        else:
            ci, wi = cp[0], wp[0]
            cr, wr = rows[ci], rows[wi]
            if ci == wi or (cr["sym"] == wr["sym"]
                            and cr["side"] == wr["side"]
                            and cr["net"] == wr["net"]):
                take, src, f = ci, "same", self.champ
            else:
                _yr = _dt.datetime.utcfromtimestamp(
                    int(ts)).year
                _py, _wy = self.yr.get(_yr, (0, 0))
                refuse = (
                    _py >= 1
                    and _wy / _py <= PROT_T + 1e-12
                    and wr["net"] is not None
                    and cr["net"] is not None
                    and wr["net"] <= 0 and cr["net"] > 0)
                if refuse:
                    take, src, f = ci, "pha", self.champ
                    e["refusals"] += 1
                else:
                    take, src, f = wi, "wdv", self.wdiv
        pick = dict(f.picks[-1])
        pick["src"] = src
        self.picks.append(pick)
        self.srcs.append(src)
        e["picks"] += 1
        e["src_" + ("pha" if src in ("pha", "same")
                    else "wdv")] += 1
        _yr = _dt.datetime.utcfromtimestamp(int(ts)).year
        _py, _wy = self.yr.get(_yr, (0, 0))
        _net = rows[take]["net"]
        self.yr[_yr] = (
            _py + 1,
            _wy + (1 if (_net is not None
                         and _net > 0) else 0))
        return [take]


def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


def _bars_from_frame(df):
    """App frame (DataFrame with a time column and
    OHLC) -> (ts, o, h, l, c) numpy arrays sorted by
    time."""
    if df is None or not len(df):
        return None
    try:
        tcol = next(c for c in df.columns
                    if c.lower() in ("datetime", "time",
                                     "timestamp"))
        ts = (pd.to_datetime(df[tcol], utc=True)
              .astype("int64") // 10 ** 9).to_numpy(np.int64)
        o = df["Open"].to_numpy(np.float64)
        h = df["High"].to_numpy(np.float64)
        l = df["Low"].to_numpy(np.float64)
        c = df["Close"].to_numpy(np.float64)
    except Exception:
        return None
    order = np.argsort(ts, kind="stable")
    return (ts[order], o[order], h[order], l[order],
            c[order])


class _Form:
    """The slot stream settled through the
    PW-J fill. Persisted: the fill state (blocking
    ledger, picks), the delivered ledger and the
    processed checks."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.fill = PphaFillState()
        self.delivered = []
        self.processed = []
        self._load()

    def _load(self):
        import json
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path) as fh:
                d = json.load(fh)
        except Exception:
            return
        self.processed = d.get("processed", [])
        if "fill" in d:
            self.fill.from_dict(d["fill"])
        out = []
        for r in d.get("delivered", []):
            r = dict(r)
            for k in ("check", "entry_time", "exit_time",
                      "entry_candle"):
                if r.get(k) is not None:
                    r[k] = pd.Timestamp(r[k])
            out.append(r)
        self.delivered = out

    def save(self):
        import json
        if not self.path:
            return
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)

        def ser(rows):
            out = []
            for r in rows:
                dd = dict(r)
                for k in ("check", "entry_time",
                          "exit_time", "entry_candle"):
                    if dd.get(k) is not None:
                        dd[k] = pd.Timestamp(
                            dd[k]).isoformat()
                out.append(dd)
            return out
        with open(self.path, "w") as fh:
            json.dump({"system": SYSTEM_NAME,
                       "fill": self.fill.to_dict(),
                       "delivered": ser(self.delivered),
                       "processed": self.processed}, fh)

    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=(), m5_frames=None):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r["check"]) == chk]
        T = int(chk.timestamp())
        T -= T % 3600  # entries fire at H:00 UTC
        if m15_frames is None:
            m15_frames = fetch_cycle89u_m15_frames()
        m15_bars = {}
        for sym in SYMBOLS:
            b = _bars_from_frame(
                m15_frames.get(sym) if m15_frames else None)
            if b is not None:
                m15_bars[sym] = b
        self.fill.resolve_pending(m15_bars)
        era = "disc" if _dt.datetime.utcfromtimestamp(
            T).year <= 2023 else "audit"
        rows = _slot_rows(T, m15_bars)
        picks = self.fill.process_slot(T, era, rows)
        entry_candle = pd.Timestamp(
            _dt.datetime.utcfromtimestamp(T))
        out = []
        for p in picks:
            r = rows[p]
            dd = {"check": chk, "symbol": r["sym"],
                  "direction": "BUY" if r["side"] > 0
                  else "SELL",
                  "entry_candle": entry_candle,
                  "entry_time": entry_candle,
                  "entry_px": float(r["entry_px"]),
                  "tp_pips": float(r["dist"]),
                  "sl_pips": float(r["dist"]),
                  "exit_time": entry_candle
                  + pd.Timedelta(hours=MAX_HOLD),
                  "dist": float(r["dist"]),
                  "layer": "persym",
                  "system": SYSTEM_NAME}
            self.delivered.append(dd)
            out.append(dd)
        self.processed.append(str(chk))
        self.save()
        return out


_STATE = None


def _state():
    global _STATE
    if _STATE is None:
        _STATE = _Form()
    return _STATE


def load_state_form(path=None):
    if path is not None:
        return _Form(path=path)
    return _state()


def is_cycle89u_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE89U_CHECK_HOURS and t.minute == 0


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=(),
                  m5_frames: dict | None = None
                  ) -> pd.DataFrame:
    form = _state()
    out = form.step(frames, check_time_utc, m15_frames,
                    open_symbols, m5_frames)
    if isinstance(out, pd.DataFrame):
        return out
    if not out:
        return pd.DataFrame()
    return pd.DataFrame(out)


def walk_ledger():
    """The delivered cycle89u stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle89u_m15_frames(state=None):
    from core.cycle89t_best import fetch_cycle89t_m15_frames
    return fetch_cycle89t_m15_frames()


def evaluate_cycle89u_signals(frames: dict,
                                check_time_utc,
                                m15_frames: dict | None
                                = None):
    return panel_entries(frames, check_time_utc,
                         m15_frames)


def select_cycle89u_entries(signals: pd.DataFrame,
                              open_symbols=()
                              ) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
