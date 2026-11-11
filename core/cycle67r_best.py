"""Cycle 67R -- August: the expectancy-mined design
M5R97A04 (DFO-MG-STAB) written as a live rule.

PROVENANCE. Design M5R97A04, M5 validation series
Rounds 96/97 (DISC-frozen drawdown admission), graded in
fx_research/m5_validation_series/round97 (VERDICT_AUG /
grade_aug.json) on the extended mined universe of
round89/work (built from the canonical candle store
fx/fx_data_canonical.db under the locked conventions:
RR 1:1, SL-first in one bar, cost 2.5 pips all-in,
Mon-Fri entries, entry at the slot's M15 close, 48h
cap). Filed record: DISC kept 715, win 77.48%, net
+4,717.27; AUDIT kept 210, win 70.00%, net +754.99;
Monte Carlo section 9 MIDDLE PASS (battery headroom
+157.74); red DISC weeks 0; EC22 failed set exactly
{13_lct, 14_leftover, 20_dsr}. VALIDATED at Round 112
under the user's SPA substitution order of 2026-11-11
(Hansen SPA consistent p = 0.0000, t = 10.097; check 20
DSR replaced by SPA for this month; DSR prints 0.000
stand on the record). Multi-pick label: up to 2 picks
per check slot. Sizing was NOT graded in the series
and this module carries no Best-N constant.

THE RULE (what this module computes at a check slot).
Check slots are the August slots UTC (1, 16, 17) =
07:30 / 22:30 / 23:30 MMT. At a slot, for every one of
the 28 symbols the module builds candidate trades from
the candles: entry at the close of the M15 bar ending
at the slot; M15 ATR14 sets the distance ladder
{0.5, 0.75, 1.0, 1.5, 2.0, 3.0} x ATR for SL and TP
(RR 1:1, both sides); the H1 ATR14's percentile in the
DISC reference distribution (shipped below as data)
gives the volatility tercile; the candidate's cell is
(symbol, slot hour, side, distance step, tercile).
Fitted constants shipped as data below, all fitted on
DISC 2016-2023 ONLY: the 72 base-eligible cells (their
DISC win% / expectancy drive the ranking), the 46
STAB1 cells among them (expectancy > 0 with n >= 5 in
both DISC halves 2016-2019 and 2020-2023), and each
base cell's DISC losing-week set. First pick: among
the slot's base-eligible candidates, order by
(overlap of the cell's DISC losing weeks with the
running segment's losing weeks, then cell win% desc,
then cell expectancy desc, then canonical order) and
take the first whose symbol is not blocked by a still
open kept trade. Second pick: among the slot's STAB1
candidates (different symbol, unblocked after the
first pick), the first in the same ordering is
proposed; in the post-2023 segment it is admitted
unconditionally, exactly as filed. In the DISC segment
only (historical slots, year <= 2023) the filed
admission gate applies: the proposal is admitted iff
its own replayed net >= +5.00 AND the observed max
drawdown of the segment's running kept-net sequence
does not increase -- in live operation (year >= 2024)
this gate never fires, by the design's construction
(the filed zero-AUDIT-rejection invariant). Two
structural facts of the filed design hold live: the
WDIV overlap term is identically zero outside the
DISC segment (the cells' losing-week sets contain
only 2016-2023 ISO weeks), so the live ordering is
the plain win ranking; and a kept trade blocks its
symbol until its candle-replayed exit.

STATUS LABEL (user order 2026-11-11): written from
the validated design, NOT CHECKED. The port-proof
step (historical replay diff + battery confirmation)
was dropped by the user's order ("ignore the test
part"); this module has not been proofed as live
code and must not be represented as proofed. It is
not installed; registration in core/signal_mode.py
is a separate, announced push step.
"""

from __future__ import annotations

import base64
import datetime as _dt
import os
import zlib

import numpy as np
import pandas as pd

SYSTEM_NAME = "cycle67r"
CYCLE67R_CHECK_HOURS = (1, 16, 17)
SURFACE_GRID = (1, 16, 17)
MAX_HOLD = 48
MAXHOLD_BARS = 192  # 48h on M15
COST_PIPS = 2.5
MG_MARGIN = 5.0
OFFICE_HOURS = ()

SYMBOLS = ["AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD",
           "CADCHF", "CADJPY", "CHFJPY", "EURAUD", "EURCAD",
           "EURCHF", "EURGBP", "EURJPY", "EURNZD", "EURUSD",
           "GBPAUD", "GBPCAD", "GBPCHF", "GBPJPY", "GBPNZD",
           "GBPUSD", "NZDCAD", "NZDCHF", "NZDJPY", "NZDUSD",
           "USDCAD", "USDCHF", "USDJPY"]
SYM_IDX = {s: i for i, s in enumerate(SYMBOLS)}
MULTS = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0)

# ---- DISC-fitted constants (provenance: PROVENANCE_AUG.md
# in the port folder). CELL_WIN / CELL_EXP: per conditioned
# cell key ((sym*24+hour)*2+side01)*6+mult_idx)*3+tercile,
# the cell's DISC win% and mean net (2.5-pip cost) over the
# mined universe; a cell is base-eligible iff it appears
# here (rung s1: conditioned exp >= +1.0 & n >= 30 AND
# unconditional exp > 0 & n >= 15). STAB1_CELLS: the
# split-half-stable subset. LOSE_WEEKS: per cell, the DISC
# ISO (year, week) set whose base-eligible net sum < 0.
# _ATRH_B85: zlib+base85 of the DISC H1-ATR14 reference
# multiset (distinct float64 values then int64 counts),
# for the midrank tercile rule.
CELL_WIN = {604: 65.95744680851064, 607: 60.63829787234043, 609: 59.210526315789465, 610: 56.38297872340425, 640: 63.73626373626373, 642: 63.74999999999999, 643: 65.93406593406593, 645: 60.0, 646: 59.34065934065934, 1468: 65.0, 1470: 66.66666666666666, 1471: 66.66666666666666, 1474: 61.66666666666667, 1504: 72.72727272727273, 1507: 70.9090909090909, 1509: 61.016949152542374, 1510: 65.45454545454545, 3199: 61.111111111111114, 3202: 61.111111111111114, 3234: 67.21311475409836, 3235: 64.15094339622641, 3237: 64.75409836065575, 3238: 60.37735849056604, 4062: 66.66666666666666, 4065: 66.66666666666666, 6638: 60.86956521739131, 6641: 63.76811594202898, 7499: 58.04195804195804, 7501: 60.0, 7502: 54.54545454545454, 7504: 56.666666666666664, 7505: 53.84615384615385, 10955: 60.0, 10961: 61.0, 10997: 57.73195876288659, 11825: 55.55555555555556, 14471: 55.55555555555556, 15292: 59.210526315789465, 15293: 60.0, 15295: 57.89473684210527, 15299: 55.294117647058826, 15328: 65.75342465753424, 15331: 60.273972602739725, 15334: 60.273972602739725, 15335: 57.608695652173914, 15605: 57.46268656716418, 16139: 58.82352941176471, 16145: 53.59477124183007, 17006: 55.11363636363637, 18748: 64.44444444444444, 18750: 68.83116883116884, 18751: 65.55555555555556, 18754: 61.111111111111114, 18786: 62.66666666666667, 18787: 61.702127659574465, 18789: 62.66666666666667, 19611: 68.38235294117648, 19612: 64.86486486486487, 19614: 70.58823529411765, 19615: 64.86486486486487, 19617: 62.5, 19618: 62.16216216216216, 19650: 67.91044776119402, 19653: 65.67164179104478, 21340: 62.5, 23056: 58.620689655172406, 23092: 63.63636363636363, 23915: 61.904761904761905, 23917: 62.264150943396224, 23918: 61.904761904761905, 23920: 64.15094339622641, 23921: 58.730158730158735}
CELL_EXP = {604: 2.3549392097264157, 607: 1.3580547112461734, 609: 2.780169172932196, 610: 1.1107142857142698, 640: 1.1368524332809824, 642: 1.738928571428542, 643: 2.5792778649921115, 645: 2.5973214285713384, 646: 2.0543956043955522, 1468: 2.064642857142805, 1470: 1.8987129987129612, 1471: 3.9392857142856754, 1474: 4.2724999999999795, 1504: 3.6484415584415304, 1507: 5.045454545454512, 1509: 1.1421307506053342, 1510: 5.250649350649236, 3199: 1.458201058201178, 3202: 2.251719576719626, 3234: 1.6320843091334982, 3235: 1.6242587601078557, 3237: 2.742271662763497, 3238: 2.7556603773585375, 4062: 2.219047619047623, 4065: 4.760884353741472, 6638: 5.4832298136645505, 6641: 11.126501035196666, 7499: 2.010039960039997, 7501: 1.587619047619276, 7502: 1.5407592407592272, 7504: 2.3442857142858387, 7505: 2.4820679320679155, 10955: 1.8496785714285846, 10961: 6.93921428571425, 10997: 4.55397643593528, 11825: 3.204850088183357, 14471: 2.040432098765416, 15292: 1.0919642857143401, 15293: 1.337857142857135, 15295: 1.3208646616541737, 15299: 1.655966386554623, 15328: 1.87333659491187, 15331: 1.3553816046966145, 15334: 2.5151663405088005, 15335: 1.4613354037268185, 15605: 2.522601279317888, 16139: 2.2712184873949455, 16145: 2.374509803921663, 17006: 2.0219967532468472, 18748: 2.443571428571445, 18750: 3.4523191094619827, 18751: 4.176507936507959, 18754: 4.662936507936539, 18786: 1.3276190476190592, 18787: 1.4343465045592731, 18789: 3.261999999999993, 19611: 1.3729779411764813, 19612: 1.5505791505791182, 19614: 2.7759453781512704, 19615: 2.2583011583010992, 19617: 2.3874474789916142, 19618: 2.2181467181466177, 19650: 1.8877398720682281, 19653: 3.0555970149254073, 21340: 1.6413392857142601, 23056: 4.815353037766815, 23092: 5.87832792207789, 23915: 4.966496598639508, 23917: 2.1460916442048696, 23918: 7.583673469387803, 23920: 6.745283018867845, 23921: 6.6683673469388065}
STAB1_CELLS = frozenset([604, 609, 610, 640, 642, 643, 645, 646, 1470, 1474, 1504, 1507, 1509, 1510, 3202, 3235, 3238, 4062, 6638, 6641, 7502, 7505, 10955, 10961, 15328, 15605, 16139, 18748, 18750, 18751, 18754, 18789, 19611, 19612, 19614, 19615, 19617, 19650, 19653, 21340, 23056, 23092, 23915, 23918, 23920, 23921])
LOSE_WEEKS = {604: ((2017, 31), (2017, 32), (2017, 33), (2017, 35), (2018, 31), (2018, 33), (2020, 32), (2020, 34), (2020, 35), (2022, 31), (2023, 31)), 607: ((2016, 33), (2016, 35), (2017, 31), (2017, 32), (2017, 35), (2018, 31), (2018, 33), (2020, 34), (2020, 35), (2021, 31), (2022, 31), (2023, 31), (2023, 34), (2023, 35)), 609: ((2016, 34), (2016, 35), (2017, 32), (2017, 33), (2017, 35), (2018, 34), (2020, 35), (2021, 33), (2021, 35), (2022, 32), (2022, 34), (2023, 34), (2023, 35)), 610: ((2016, 31), (2016, 33), (2016, 35), (2017, 31), (2017, 35), (2018, 31), (2018, 33), (2019, 33), (2020, 32), (2020, 34), (2020, 35), (2021, 31), (2022, 31), (2022, 32), (2022, 34), (2023, 32), (2023, 34), (2023, 35)), 640: ((2016, 31), (2016, 34), (2017, 31), (2017, 32), (2017, 35), (2018, 31), (2018, 33), (2020, 32), (2020, 35), (2022, 33), (2023, 32), (2023, 34), (2023, 35)), 642: ((2016, 34), (2016, 35), (2017, 32), (2017, 33), (2017, 35), (2018, 33), (2018, 34), (2019, 35), (2020, 34), (2020, 35), (2021, 33), (2022, 32), (2023, 34), (2023, 35)), 643: ((2016, 31), (2016, 34), (2017, 31), (2017, 32), (2017, 33), (2017, 35), (2018, 31), (2018, 33), (2020, 32), (2020, 35), (2022, 31), (2023, 32), (2023, 34)), 645: ((2016, 32), (2016, 34), (2016, 35), (2017, 32), (2017, 33), (2018, 32), (2020, 34), (2020, 35), (2021, 32), (2021, 33), (2021, 35), (2022, 34), (2023, 34), (2023, 35)), 646: ((2016, 31), (2016, 33), (2016, 34), (2016, 35), (2017, 31), (2017, 35), (2018, 31), (2018, 33), (2020, 35), (2022, 31), (2022, 32), (2023, 31), (2023, 32), (2023, 34), (2023, 35)), 1468: ((2016, 31), (2016, 33), (2016, 35), (2017, 31), (2017, 32), (2017, 34), (2017, 35), (2018, 33), (2018, 34), (2019, 32), (2019, 33), (2022, 33)), 1470: ((2016, 34), (2016, 35), (2017, 32), (2017, 33), (2017, 34), (2018, 31), (2018, 33), (2019, 32), (2020, 32), (2020, 34), (2020, 35), (2020, 36), (2021, 31), (2021, 35), (2023, 35)), 1471: ((2016, 31), (2016, 32), (2016, 33), (2016, 35), (2017, 31), (2017, 32), (2017, 35), (2018, 33), (2019, 33), (2020, 32)), 1474: ((2016, 31), (2016, 35), (2017, 31), (2017, 32), (2017, 35), (2018, 33), (2019, 33), (2020, 32), (2022, 32)), 1504: ((2016, 31), (2017, 32), (2017, 34), (2017, 35), (2018, 33), (2019, 33), (2022, 33)), 1507: ((2016, 31), (2016, 32), (2017, 32), (2017, 34), (2017, 35), (2018, 33), (2019, 33), (2020, 32)), 1509: ((2016, 33), (2016, 34), (2016, 35), (2017, 33), (2018, 33), (2019, 33), (2019, 34), (2020, 32), (2020, 34), (2020, 35), (2020, 36), (2021, 31), (2021, 34), (2021, 35), (2023, 35)), 1510: ((2016, 31), (2016, 32), (2017, 31), (2017, 35), (2018, 33), (2019, 33), (2020, 32)), 3199: ((2016, 31), (2016, 32), (2016, 34), (2017, 31), (2017, 35), (2018, 32), (2018, 34), (2020, 33), (2020, 34), (2020, 35), (2022, 33)), 3202: ((2016, 31), (2016, 32), (2017, 31), (2017, 35), (2018, 32), (2020, 32), (2020, 33), (2022, 31), (2022, 33)), 3234: ((2016, 34), (2017, 31), (2017, 33), (2018, 31), (2018, 33), (2018, 34), (2018, 35), (2019, 31), (2019, 35), (2020, 33), (2020, 34), (2021, 32), (2021, 35), (2023, 31), (2023, 34), (2023, 35)), 3235: ((2016, 32), (2016, 34), (2017, 31), (2017, 35), (2018, 32), (2018, 33), (2019, 32), (2020, 33), (2020, 35), (2022, 31), (2022, 32), (2022, 33), (2022, 35)), 3237: ((2016, 34), (2017, 31), (2017, 33), (2017, 34), (2018, 31), (2018, 32), (2018, 33), (2018, 34), (2019, 31), (2019, 34), (2020, 34), (2021, 32), (2021, 35), (2023, 34), (2023, 35)), 3238: ((2016, 31), (2017, 31), (2017, 35), (2018, 32), (2019, 32), (2020, 32), (2020, 33), (2020, 35), (2022, 31), (2022, 33), (2022, 35)), 4062: ((2016, 31), (2016, 35), (2017, 32), (2017, 33), (2017, 34), (2017, 35), (2018, 33), (2018, 34), (2020, 34), (2020, 35), (2021, 34), (2021, 35), (2023, 35)), 4065: ((2016, 31), (2017, 32), (2017, 33), (2017, 35), (2018, 32), (2018, 33), (2018, 34), (2020, 33), (2020, 34), (2020, 35), (2021, 34), (2021, 35), (2023, 35)), 6638: ((2017, 32), (2017, 33), (2017, 35), (2019, 32), (2019, 33), (2020, 36), (2022, 31), (2022, 33), (2022, 35), (2023, 32)), 6641: ((2017, 32), (2017, 33), (2017, 35), (2019, 32), (2019, 33), (2020, 36), (2022, 35), (2023, 31)), 7499: ((2017, 32), (2017, 35), (2018, 33), (2018, 35), (2019, 32), (2020, 34), (2020, 35), (2020, 36), (2021, 31), (2021, 33), (2021, 35), (2022, 32), (2022, 33), (2022, 34), (2023, 32), (2023, 34)), 7501: ((2017, 34), (2018, 31), (2018, 32), (2018, 35), (2019, 34), (2020, 33)), 7502: ((2016, 34), (2016, 35), (2017, 32), (2017, 33), (2017, 34), (2017, 35), (2018, 35), (2019, 33), (2020, 35), (2021, 31), (2021, 35), (2022, 32), (2022, 33), (2023, 32), (2023, 34)), 7504: ((2017, 34), (2018, 31), (2018, 32), (2018, 33), (2019, 34), (2020, 33), (2021, 35)), 7505: ((2016, 31), (2016, 34), (2016, 35), (2017, 32), (2017, 33), (2017, 35), (2018, 35), (2020, 32), (2020, 35), (2021, 31), (2021, 35), (2022, 32), (2022, 33), (2023, 34), (2023, 35)), 10955: ((2017, 32), (2017, 33), (2017, 35), (2018, 34), (2019, 31), (2019, 34), (2019, 35), (2020, 33), (2022, 31), (2022, 32), (2022, 33), (2023, 31), (2023, 32)), 10961: ((2016, 32), (2017, 33), (2018, 32), (2018, 35), (2019, 31), (2019, 32), (2019, 34), (2019, 35), (2020, 33), (2022, 32), (2022, 33), (2023, 31), (2023, 34)), 10997: ((2016, 32), (2017, 33), (2018, 32), (2018, 35), (2019, 31), (2019, 32), (2019, 34), (2019, 35), (2020, 32), (2020, 33), (2022, 33), (2022, 35), (2023, 31), (2023, 34)), 11825: ((2016, 33), (2016, 35), (2017, 33), (2018, 31), (2018, 33), (2019, 32), (2019, 33), (2020, 34), (2020, 35), (2020, 36), (2021, 31), (2021, 32), (2021, 34), (2021, 35), (2022, 32), (2022, 33), (2023, 32), (2023, 34)), 14471: ((2016, 33), (2016, 34), (2016, 35), (2017, 31), (2017, 32), (2017, 35), (2018, 34), (2018, 35), (2019, 31), (2019, 33), (2020, 34), (2020, 35), (2020, 36), (2022, 32), (2022, 35), (2023, 31), (2023, 32), (2023, 35)), 15292: ((2016, 34), (2016, 35), (2017, 32), (2017, 34), (2017, 35), (2018, 31), (2018, 33), (2018, 34), (2020, 32), (2020, 34), (2020, 35), (2020, 36), (2021, 31), (2021, 32), (2021, 34), (2023, 32), (2023, 35)), 15293: ((2016, 31), (2016, 33), (2016, 34), (2016, 35), (2017, 31), (2017, 33), (2017, 35), (2018, 33), (2019, 31), (2019, 34), (2020, 34), (2020, 35), (2023, 31)), 15295: ((2016, 34), (2016, 35), (2017, 32), (2017, 34), (2017, 35), (2018, 31), (2018, 33), (2018, 34), (2018, 35), (2020, 32), (2020, 34), (2020, 35), (2020, 36), (2021, 31), (2021, 32), (2021, 34), (2021, 35), (2023, 32), (2023, 35)), 15299: ((2016, 31), (2016, 33), (2016, 34), (2016, 35), (2017, 35), (2018, 33), (2019, 33), (2019, 34), (2020, 34), (2020, 35), (2022, 34), (2022, 35), (2023, 31)), 15328: ((2016, 34), (2016, 35), (2018, 33), (2018, 34), (2020, 34), (2020, 35), (2021, 31), (2021, 32), (2021, 34), (2021, 35), (2023, 32)), 15331: ((2016, 34), (2016, 35), (2018, 31), (2018, 32), (2018, 33), (2018, 34), (2018, 35), (2020, 34), (2020, 35), (2021, 31), (2021, 32), (2021, 34), (2021, 35), (2023, 35)), 15334: ((2016, 34), (2016, 35), (2017, 34), (2018, 33), (2018, 35), (2020, 34), (2020, 35), (2021, 31), (2021, 32), (2021, 34), (2021, 35), (2022, 31), (2023, 35)), 15335: ((2016, 31), (2016, 33), (2016, 34), (2016, 35), (2017, 33), (2017, 35), (2018, 33), (2019, 33), (2019, 34), (2020, 34), (2020, 35), (2020, 36), (2022, 35)), 15605: ((2016, 31), (2016, 32), (2017, 32), (2017, 34), (2018, 32), (2018, 33), (2018, 35), (2019, 31), (2019, 32), (2020, 32), (2020, 34), (2021, 33), (2022, 31), (2022, 34), (2022, 35), (2023, 31), (2023, 33)), 16139: ((2016, 35), (2018, 31), (2018, 35), (2019, 31), (2019, 32), (2019, 33), (2019, 35), (2020, 33), (2020, 34), (2021, 33), (2021, 34), (2022, 31), (2022, 32), (2022, 35), (2023, 32)), 16145: ((2016, 32), (2017, 32), (2018, 31), (2018, 32), (2018, 35), (2019, 31), (2019, 32), (2019, 33), (2019, 34), (2019, 35), (2020, 33), (2021, 33), (2022, 32), (2022, 35)), 17006: ((2016, 31), (2016, 34), (2017, 32), (2018, 32), (2020, 32), (2020, 34), (2020, 35), (2021, 31), (2021, 35), (2022, 32), (2022, 33), (2022, 34), (2023, 32), (2023, 34)), 18748: ((2016, 34), (2016, 35), (2017, 31), (2017, 32), (2018, 33), (2018, 35), (2019, 33), (2019, 35), (2020, 33), (2020, 34), (2020, 35), (2021, 31), (2022, 34), (2022, 35), (2023, 35)), 18750: ((2016, 32), (2016, 35), (2017, 33), (2017, 35), (2018, 34), (2020, 32), (2020, 35), (2022, 31), (2022, 32), (2023, 34)), 18751: ((2016, 34), (2016, 35), (2017, 32), (2017, 33), (2017, 34), (2018, 33), (2018, 35), (2019, 33), (2019, 35), (2020, 34), (2020, 35), (2022, 32), (2022, 34), (2023, 31), (2023, 35)), 18754: ((2016, 33), (2016, 34), (2017, 32), (2017, 33), (2018, 31), (2018, 33), (2018, 35), (2019, 33), (2019, 34), (2019, 35), (2020, 34), (2020, 35), (2021, 33), (2022, 32), (2022, 34), (2023, 35)), 18786: ((2016, 32), (2016, 35), (2017, 32), (2017, 33), (2017, 35), (2018, 33), (2018, 34), (2019, 32), (2020, 32), (2020, 34), (2020, 35), (2021, 33), (2021, 34), (2022, 32), (2022, 35)), 18787: ((2016, 31), (2016, 33), (2016, 34), (2017, 32), (2017, 34), (2018, 33), (2018, 35), (2019, 33), (2019, 34), (2019, 35), (2020, 34), (2020, 35), (2022, 32), (2022, 33), (2022, 34), (2023, 35)), 18789: ((2016, 32), (2016, 35), (2017, 32), (2018, 33), (2018, 34), (2020, 32), (2020, 34), (2020, 35), (2021, 31), (2021, 32), (2021, 33), (2021, 35), (2022, 32), (2023, 34)), 19611: ((2016, 33), (2016, 35), (2017, 32), (2017, 33), (2017, 35), (2018, 31), (2018, 32), (2018, 33), (2018, 34), (2019, 31), (2019, 35), (2020, 34), (2020, 35), (2020, 36), (2021, 32), (2021, 35), (2022, 32), (2023, 32), (2023, 35)), 19612: ((2016, 33), (2017, 31), (2017, 32), (2017, 35), (2019, 32), (2019, 33), (2019, 35), (2020, 33), (2022, 33)), 19614: ((2016, 31), (2016, 33), (2016, 34), (2016, 35), (2017, 32), (2017, 33), (2017, 35), (2018, 32), (2018, 33), (2019, 33), (2020, 32), (2020, 34), (2020, 35), (2020, 36), (2021, 34), (2021, 35)), 19615: ((2016, 33), (2017, 32), (2017, 34), (2017, 35), (2019, 32), (2019, 33), (2020, 33), (2022, 32), (2022, 33)), 19617: ((2016, 31), (2016, 33), (2016, 34), (2016, 35), (2017, 33), (2017, 35), (2018, 32), (2018, 33), (2019, 35), (2020, 32), (2020, 34), (2020, 35), (2020, 36), (2021, 31), (2021, 34), (2021, 35)), 19618: ((2016, 33), (2016, 34), (2017, 32), (2017, 35), (2019, 33), (2021, 33), (2021, 34), (2022, 32), (2022, 33)), 19650: ((2016, 31), (2016, 32), (2016, 33), (2016, 35), (2017, 33), (2017, 34), (2018, 32), (2018, 33), (2019, 35), (2020, 34), (2020, 35), (2021, 33), (2021, 34), (2021, 35), (2023, 32), (2023, 35)), 19653: ((2016, 31), (2016, 33), (2016, 34), (2016, 35), (2017, 33), (2018, 33), (2019, 35), (2020, 32), (2020, 34), (2020, 35), (2020, 36), (2021, 31), (2021, 35)), 21340: ((2016, 34), (2017, 32), (2017, 34), (2020, 32), (2020, 33), (2020, 34), (2020, 35), (2021, 31), (2021, 33), (2022, 31), (2022, 33), (2022, 34), (2023, 34), (2023, 35)), 23056: ((2016, 32), (2016, 33), (2016, 34), (2017, 34), (2018, 32), (2019, 31), (2019, 32), (2020, 32), (2020, 33), (2021, 34), (2021, 35), (2022, 34), (2023, 31), (2023, 35)), 23092: ((2016, 32), (2016, 33), (2017, 32), (2017, 34), (2018, 32), (2018, 34), (2019, 31), (2019, 32), (2020, 34), (2021, 35), (2022, 32), (2023, 35)), 23915: ((2016, 33), (2019, 31), (2019, 33), (2020, 32), (2022, 31), (2022, 33), (2022, 35), (2023, 33)), 23917: ((2016, 32), (2016, 34), (2016, 35), (2017, 31), (2017, 32), (2018, 34), (2019, 31), (2019, 32), (2019, 34), (2020, 34), (2021, 33), (2023, 34)), 23918: ((2017, 33), (2019, 31), (2019, 32), (2019, 33), (2020, 32), (2022, 31), (2022, 35)), 23920: ((2016, 32), (2016, 33), (2016, 34), (2016, 35), (2017, 32), (2019, 31), (2019, 34), (2019, 35), (2020, 34), (2023, 34)), 23921: ((2016, 32), (2017, 33), (2018, 32), (2019, 31), (2019, 32), (2019, 33), (2019, 35), (2020, 32), (2022, 31), (2022, 34), (2023, 31), (2023, 35))}
LOSE_WEEKS = {ck: set(wks) for ck, wks in LOSE_WEEKS.items()}  # values as sets: FillState._order intersects them
_ATRH_NDISTINCT = 12631
_ATRH_TOTAL = 178416
_ATRH_B85 = (
    'c-l1Gd4P`9`^RxbjZ{O**k;D;`xa7`>M}(}8?u!$l15+4v{_O^vZN^0w1_q&p|X@{9a2acNrN;h87Wf<sc7>%&-Ho#`selg{xI`A'
    '_kGTFKG%Jp=YCFaQhc~cabtU^VeQ=L+QybOKRWy$XWNu+<tatwXWKje=S^&Bzq0lH%9_~GN5cO*CB~LSD2lNk&x!nbjQv}GbdRXf'
    'F&1CFYGn1Q7@M+New<ygH@hOnrcVg}e0_}l{@;o4UyRwI$PaF6)+X{_Q`_V}r>Si?HS%+s+PEmW$$xKCd;RIz;lHMK{ekc@=Qg$C'
    '4vQvtSk%;JJ+SQ9^kq$L;P}YTZ)$CNME+qj8+0V{^P5?E<ZYxhv$1<4FQl3M?~BfHRh^qz%PKi|ROBBtvo}79{Gw*oZAeM@ubEZ9'
    '5nletX7=|g*`;sfbu_b^{+b?sVKe*Pk5BmX$YGn?%s&5gbNH{BP4VN{%m(`VY-VR3j=YZM_Ns+n7uVbt)I?rKa~n1_@&=mQi!qV+'
    '-Q4Cxer-u}`{U2Z&u?z`ACr3{hq=7Djq>;3-0t@G-P}6oM~-WA`?E#ljWoC7$jhv5Zg1hsXGUH}bGt5D_81s>A<b=7vApS|I^n+-'
    'R;Op=c(t%4^CEw-g<TvuEO9ODXFpyotdpOg7WONi8#ygKTG(_v&@}P`TiBq;%bVT8jy)JTA1!R)4B6_N$N_9&FZnoVVZACN$Ek%C'
    'MSe|H3wsfl#><7Jk=Gyo{))%}XkoRHmszK!C0`wRoh_{lH~R5xX%}1~pLim2o?BX)AK#Yt{XRLYb>wxowCc99!q0z8>yZ>Wuq~}c'
    's@#<(8~gieX~Qvdtn55azV7p(rTz70<UqHyYgWm(R?F@_ep_0d{*m$0(k}9G($X&VanjN*>litIE$#DNk$>3Ic7G)wsh0QqacXJb'
    'VtJ1I^zO*`4)4p4UrT#>i@e*<cS}q6ao5r&4~m@MmR1rOekWR5BcBhk_TR6O7anU@`*Dl4Mvq61SFHWIC-RG8ZRuY5k{_>Fdv;P}'
    'pvBtn80E(&)@J*BiM2<4zJ$NGUS7RHX83W5wI5c=uGdD6L#$1YyzR-cHr2;-tbK#``f-W1I3L&H-*=QZ`Z$WUZ8PNiew<=0+K)@D'
    '&B&8yMSlGHSo;vijF(sX1dp}kR&rqEukVeukJiW+eSXB+37;3ScK!0mc#E}qKHlQ&A|GdQb~N(xqT_7gJbCSW`8s~<$2HELJ1iF;'
    'k(U)lj&q#->&H3HuJrL3XWM)p#o6A-;ph-&6Ma0!S(ew+IBRle<oL!}?I?NwX!(gB?>H;iAUkf9`_7Jx$2gljG*Um}?2%h!6F>fO'
    'Hr$VUob~p)8E1`ulJ)$!#@TiF2CnkD9cP#O@r<*N@0DkM78!4G_IPaMc*a?mIQgrOzc}kwD*wi>{rJY&foNISP$u0FIZ$!-bFr+6'
    '{Muu2_LYy<ID6FVQM?_%$Nf0R+h=~5;;p(+Zg?zmz~U{sTyDedKL6uwt&ih)+jpKE=;Juv#!Qhbk|W1E-iD;em{ghS^F7{P@#7tD'
    'r>vK={5Z$k(kAkq7<uC6$nlQ1$5uuTM0h=K$rpXyinl)f<vG{M6MjD8ZKkgy@z&bwdc4*C5IHaL_QL_W@F)44&xd$>!p~2<jq<t?'
    'Z@a#dTeBhqJKoOAkvV?e;%zGaF+q;<^A>L(jfk9|cpE!XCiuLFx4ZGDwX(v`U%WMombc?XuP^b|*w0&d{Wu&y!uaKKEN;cj6|&Ul'
    'Su5L!XLy}zWp#bNwXzT9$(HlwHJ%q**=u;}VcGbIT;O%Bm3`7#zU<?pmAz3en>`^rof{bst?Y82f356aJg_bD4_n#MFXZz+F2djU'
    'dDzOjjg}YtcxYuuFy6;SEBpE!d7z1$=HsH3?ZNgXvK*)T{A^`4*lD%Q@^RD3+Vz)@;?IjCFSM2I^jy%&)?F5PW3B9~BKdH4`MIyd'
    't?d0DBL}jT-FiUg{UrYv`RB`8S(J~TRyGL#z^dHHKxk!W`uJ&OuXwI$W%V}8f%svijPg3r%KH0wYGqfy9~nQbY!#llM)vaY6MjxZ'
    '8GDxeazNxnwz8su^0%dtH`vNvS|<B1mkn0PTF+JC^`4NQyc~{8-2@xq^*X_x##TM#<#-n^z|S$er<@!4@eL9z?YM0HmmG+3k>lJr'
    '!Ny{#$FT&Ph6!_Itk<Um>xMT+j(<XeRp9Nl@;UqjZ}jn+U}u-h5jYzgMuurdf_21O@Cp0{hxj_4U@<lFS$r#U-t!aeOkaNzY$!Hw'
    'D>EbKzg>czRxRJfAF;`9*~sf>g5^Yh>_y>qdyY=9hw&YJ=AJNqx+GZLGWh_m!moXPC0K)0Ss58;S0vaqo8>NST`8~jd6-}WM$4ba'
    '$i9)o+&jUJd%aGuPuI(xcr;S)1|-;3Bjw$gQ!0ymz9!gw{2eo5<e!moJUGF6R>*^Rh0o&zJAvII<9k?w&BIFk3or3`o?x5s;>dWv'
    'J;6T0!#K8BW)70Sc%DqKu2FI>9*xY8yAo`c*NX)E5Gx|n;@$*n7AdO}6YPh`{FofZ)goCCnIF><>_P0*Lq3Tg;4Zwt>rHt5$K~6R'
    'GBPv4_T$C#WWMLz1Y3#iBGdWF1REBa7qb&AH!>`qOR)BZvWe%uFn(}nWc)8kutQk4T-M-k7ewAbIPUFb{|<5mZuu?@$X62VwY{=U'
    'jogbnyzYhL9I5|rg!$iE{)<!E$iZ!8rPsr79IE9hyXD7`9Pv(q`C$!KVeS+;4dXngCfFF<ij#8Wr;&B$g9NLN<d98a{G`ZByuOCI'
    'fcabGk;wSp8tU3;xd7kvoSR^a<K(T8albRcX81avV8chs+4vC_mCCh|@&0Y712OV>eAnxDf}K+#&%@3*2Y<s!k!i3$ypN&s8_y33'
    '_E@yMw4r<_au|OJuiNW=sAI+QvO#i1WW4_#>Oz#f2_MB<>&sofP9#|IGC2d^!qgSAWn}&QC&8BadXZo=J#Qphy~wbsn`qbiI*@3u'
    '<CaMO-5}BW9FzCqQtaXRB++)@u6gp7`SQQW_-~wOD~e=;?y}NzOQQXSX@})C_!@qHM7H*ICDE?NdoXW~9DrLr?<87gp&a1rOrrIw'
    'l?lFnB-)i2>+3|K&BrZxy006F)&+0J=P|iPjz{zLB++K$Z}_t3?nL_lTeOkg@Dg875^WP+?D;FaKYSYB#FdeJdr>$p_(Zl`i_LT7'
    'Bc9t5?MFOXB@?#GEuQxit$m6t$C<v)gx}}uOQKcd)JR_LooMIB$;a?3UuP2SqV;ktK7>zikc)iX39o;oT#p?}WnW)s5^XYmjqPIO'
    '<@gA`i@kh3O0*dja@ZQ#(bu6wyC3&p`=N4vWIhfH<2PFN!KGM@H#U@idLN%?6IRLRv0$})GSbK09>&2y`4Ya4sl_q}NBcUKXz5Y%'
    '8vF|Xh)l4%!gyaM%Wx5H$JKrvF3|?}lXu}WII+Kc!PmiX+`UjI+Q*o<NXGg4mS{!T+}FAAeviwMzP^R}Fi$=fnYT|S+D;tdIXnFR'
    'IWpSUw=nMU7i>`|uksw8Xz$^zwel!>oL`V=!*Ld__jN7N>hG2BVrh-6@pUcHew`uf_<9z`FMfj;w2@K1o+a8Kd<XaA1HPUy|ALKt'
    '-3sF}N8W^w-~qhG*Rw=BwMw?ex3GOA53WzNlgi|ExChscmsk0E82&f@i+xjMHGb-SNjP7d<xV_;b$opc;}6H-Xzzo=e84T(Cr<8<'
    'm;SPLhB}XRH^_8fS3{i~DX+lK@jtxG*VRz(F)c=3gT+nd@4n84`d1+@iu8;7!}u(b3-Dho^z}5+y5b#p40|<{rM}LF@r5U^mgBI<'
    '*WE;W5WhVovaTjt#i{ZL-W(<W#IpKwkS~Z~{x6dwFgh|1{|WN|oA`R0WZ!$AmSkrwl9}k2TcVPzov*J+wjO`PbB@br@LXSalkBN^'
    '@<Tj?_xt*rWUu2HMe=4W$J@Kh=ka=9Uz6-X+>4#&$o{_0CfQW{2EX$4Hpx!%1trPyusuG2C6CMQk^GvGWS?W-4)TS_JkL(Dw7v3P'
    '{1VTtkpuC<eKI#P@AJd^#?O4+O|tXb$VqsI_jlp_;-9#rTGrhy$N9ROWG~@1{13PIx|?J_U{hajlk8dCgjZL|o4pTAvJto*?<$jB'
    'eH~7+<5-v~>-f4H&O3gLiIws~U#F97Eyj(Ot+CwK?<8A;&EjMi{1j8-<pE#UlWg{S8MQ&S^z}N)PWSaW$ttiGo5sk8d|eLjvqC<N'
    'hcSMQ-0t_6lI)2R`2qfd>wKL~vIf!eCVUy+!yhrGp}ZA8#(lnChxxWz4#T3i<aNGIhjD{v7R&Znf@`p^uir^lKT5X6!8jA&#dGS*'
    'dcJNa*$voexg6~4c#@sKYx~J>@bvz&0=M{j9?pyRwMjMzXDo~i%p@y&SuVy~7R#yL=O$Ud9&!cV>+5}zt;SQ1%S@bsZ{Z@(14&ke'
    '*UgiA@MZ6NldO4>?CJe)lD&c({W@=wT{&Bh!-Y87^For%$4$5e(+lOLo*$Cz6MWz&x!(KcFwV+ls$VxwvRARNlf2dQLzu64k>`gn'
    'Uhy!-&5&boE3WoDkz_yP3vFa)&ksp95}(11c;#;S1wQ5ZBFTQm`BUVjo+m<m!a<%ZLcPI*XjO6q&c*`I8A;Z$On!hZ#>)ntAHw{_'
    'Bc3C|`QI$t;8~UOUF^O^UjCWv;CUj{V=TcnxXg1!lI_NJadI%8>$xJyrsHai-6+5CoDt^5NO?bgi>G+52=yJS@c_1skq={m=Zmnu'
    ';bOeP^G28-C2}gRz;Cdn_w!*rh?Z>{%7<{f=Zvrpu9kUt9hT!t{M`HhB>NX%@Vt>^n=v&?-iwp)OPo<(mU<2e^9ctolex>~Js9VC'
    'B#bls9^?DV4E)ru6NK@H&v<T0w&+Fj3d~+Cb)PWVTK15m@Grckr|jj|6_V|?W3ueH+>TQ{*CboPJlP$)dR|GkJ8=TOfG7L)gk*aU'
    'n;e!2*cordk1_Fx9OgME**?TWSmOC6+1|yxLis29eX4|HE3B0x@i%PfxhL7y;X&;0xhL69?;wZZqu8{g+~s*F*)H2F2jSZo?Rh8J'
    '+IhYSucNKJ6|eDplWeczmpHIm&cL@Y*Yi!XU5DS|KYraI+4^S7Nw^HFv3`!c5xe;Pq+}cah1`kts^ks07q@vXN;bb;9-NA=<KKS$'
    'BH3O`kx{8K9ot|(&q-liVP2(t0LS_OO}3ZtbL=---ZVxIja*mk9gcUbJdSB`@@9M<U&UuVM}={QiR-1|>v+-z`34qll!yJgNf`el'
    '<%{?k{)2T&<uT7;$<{MQp5r+zjC-7eNAb!ExeeF({kdfO6)!50-EcIH#lP`V&tJ*9uN7R6f8zFr(maPH+iX07m#>ytZ^?t6!;-B<'
    'vAhiL!~>qc!u*bs&tg;0RmnCBk9eL+wln+5pYe|V@;uK`$u<tp@f;P77mmb@IMee~vR$}H{twsT=*2R9iM+t`RkD?1)1LBDT<ZIq'
    'l5I6+9+TT~faj}Zdl2{H0Zf`FJ7Ry&UCHcM3*)y)K8m~idQF%ghvh?9=6Nhx_wRx$aU1TzNuIxwZ8yGKD4Sd&zw{TDZ0FX>^YFJv'
    'BRMRr6OYL{<+2gx;I%jvU&nVb)$ea4TLxC+r+!^1*;4k(9ylJC;0~-?BlEG^_tzxbUDM^~_#ZBxA-};bp7+9e!ss?K9Vg;0JhiQC'
    '>i1E?d99ZB;FDN|V?75ZYhO(81;6eT-hYmqfNw_X>Icd8BbI(4XX8e^vP#~KRhYY7{?Bt_7?0SkOn!!a#>)r&`cty@0|Y<8=Bcu+'
    '=f`kfH%r4KxX$m}B->VOIa-dwN_@<7VzRxDo8si!NFCjoZ1Ef9+n)cz&&SQBa<J#VWP1d+V3QbG<JXyz?W_tp)pK96olzp&<IPx('
    'KjEcAWt8W?@V@azT#bitmFK~b16Iph@JajtTfQZ8JO_sPj4SZ`VtL6Rd5!18@H(R8+qfU^@f;Y&`7&9E-{H{ZvdaqjN~B)?lWddw'
    '$>rFfzq|<_!Q;OFAdJfsayU-FQ~Y{YinYcWnCrPQ#qP&9@XW=s9E&_prr1B2(L?sd`*0c7?<rsKe3@d$u;(#36F1^ctaDsmkBwi5'
    'oVf7!aQ<BR5^lrndGacpf`9w<wiN4KBwxcnJeQ`})rVyn#(U08vCDBR&cO9}ndi?Gn~S?Jtx#T$z3>^&r74zJD;MD~-(QhpA7X5|'
    'd=a<e8qcRG)}@2|6#vAY9i@2=O|dz+0e9k2Y*Zt!#BsO~bN0!n{Qg;rtwY~G8yt<beqArcnzoUb;B&YM-}aoFV*Amm<#3#a>oMAM'
    'Zi;<?(Np9jo@-NVIhN+gk8!o<*%bQ^4^_!Mo?}z2q)e7$v+?qFJkN7%iv5VEr^?ZuTT^U0)?lMb`6N#D+?rw!;yU~WPaiEWz#&+U'
    '@8c2AxnaD<%4%#BC)?t~_zs>OFY`Umrq}~G3*W@gJ<o>MHBz2dDqr>7nqsHM$kzB4`aY_`DOQCiRmfbt4yWN5FWljL;Z{s4ky+RW'
    'C*y8B=GPrl$g?SS8&1IK4dqe4FBs~@D!C9(VD4)9I;MNBO|j1~qgZyq`*10Kg<jr9r`WYvhUK^zci`Uoa=qV24DVyP?C5zo)RBI2'
    '9#-Nt{pBv4dab<G^KlsOxD}H;7pK@gScbzrC#TpexE{wYl3hIyr`R3%0)C3AJ>|Qei^DuTCQI>SOgt`!c^(dR13$zq7&}iI7U6u{'
    'f_ptTr`S)}v`9XOpWq*Ow&&**8;P@V1KxE+HuU_QVx6!H-hxl!K|F*jBKtU>OR<|e%SZ8jJb*EUvJi_shllk88`sK@aO+R9$n$uL'
    '{f>UWCfET>u=(Ti1)S{rj>7!yAkV{%9c4ey+2Qx&YTSpu4g~M_d>!Toev3_K$j7k0=jar>5ueAi+sXl+t5d9QwY(l1?v~k}qr-g1'
    '{<s29pCZr4Az11AiBs$^oS!XU!>_O!PtB3VxXE*Qm=|BjMYtVLs*=-itLN_&JEcr!;^6VJm*?$pJX7Ud&($gRGS;b-g`Tg&dXAZ+'
    'Wgm<hBk%Bh9oBPP5+`?H-FW#Rw({$;DRu?kg%9FFT!$yH!A9B1uj7WgGg5BBzwnw;`5F$1>?8g*%nz)^+nUJN@#+}a(sO+n=XeA!'
    'uaN)ZFP`^99V(H}cuo)F7k|gZhO!EWd5#b38ZO7U)p87ehG%+i4|N)w70WJoJKpFyKIBt;2Rlc}Irtl1QC~jkIX)b39JO3N=D9r_'
    'FO2CgZ^P%X*mHXL_js}A^Hf`phw)9n?wiVW-&E^>lkf@r+H-oUoz_F9Vmo{k-@~nV0PpZTo@z7j6+G*>yvlQTs@;#%a4qh^Gv>*c'
    '@MqlaxjfZ&<9S8$GMtI;;tx2oyX@)tJyrW&f(NkRu)F~u#8tRHa($(Fs{MyKv*m3#6~Dy{&-JO+8}GxZ_!UMK%Eg}Z!~4VhTKNDj'
    '@SLA&Q_AHE{2E($&QG;bI2ZrMv<~t-d=+POltrHJ!}-BU_%2pqof<jNbA76f#jW@+_MIW`!AaQMbAPJEw~;B>6DQyj+=<nZ&xy24'
    'wS;PU1>TJd@k9SyOsb8ZEHCxEpK1f}Hv9w^=g1A7`@?vvlDBy7PqjPC<XnvLe4lF1;3gcLDo6Xi?^GMUSw4+%mGVVw?s+}cy5R4g'
    '(^IWUoGitSxYe&ehvT_k9>ia<*7JC(H7k`jdLB=;hw%qIJ4PC=$Bv%6!}wVv`+43D;|#yX1|@O`K8o*SE&hbXp0`u&E&LwqG?ZuI'
    'O3&M=HgvU|hQHv8zCSOFkAZSGW){nK*vqdgr&_%zS%V8bN2l7$ICYtP1HZ*Hmdo~7jv1b>!|TJPSdHU7Plxe@Z(?1~(_ud2^*9J0'
    'z?VE<r`ieZzerBS75JCm|4+4vJ!I>i@@mi1sg`$KzV5j>)jr3pd9p8d^?aOaFW^QzhCZBw6Y!Mo@@3D(sW!{6H-~XOTNdFMd<N&^'
    'cKjPN=E$EsABS<<Sze0I<0tqhCKt+{s0-;~9OG~JA12hwE3p4hvc|7xr&`0u<T`9wE-%ATI1dkcZVq*zgS-`I<8$~2KIGT6!#ccI'
    'cJO>0#t}Y_Yw;KCIz!&<*QZnM5qusGV52s&2^QiRo{Piy#R_aTMRvjGv5Dv3P&aTUj?9s(JnyF3UTjz;JK;op8!zzO8|nl;hHrcR'
    '4L=9J$HuAhX&m5rIMfBKz(28LrThh_cuo#=3LA`;g=6G#|6D;>_hRLjcuJf+7x&@VczL&9uMXn_tMG3;Z@s)0OK}>$fqO91b8@OJ'
    '!)iSHRyp4Da9ICvE7pyX_uv<vi$lFYKTW}@_&RR!oSbUuCGs`=3ctZNL*>J`$@fQu`4%m&#vOQaLwPf<k6cIjCDfZ$@;}U4Eyv+<'
    'yv*}-7zcP9TNcYS?1lH@E4T}b2gxR$w^Qw7yedlGgNrb?zPt`U^6TrNjxCcD@J0ODucwFk(of!jpJHl%`3jbL4iEJdk77&D*J+lA'
    'Lvb_?@!XweO?$|LnA}sQ<6_+J*TvIp#4-6OuE!&I@^KlDci~dh_3-d}=gAiMAg;r-`SR;XVQidcH+7S5;{l8*lDFcsxDy}pyq#ue'
    '9hMiN;V>MBv+yH4ge9J{)2tl3&XK2iu1>Q@uo{2F&V}+SY~=Ym%`)*<jQvTT;rTkvwmdG=Jx{0E9*pWBo8usS7~jVIcy>p**!P2k'
    '^Rrjx;{!Ms8`j8MFw66GniXPy+~v7C%}!|}TVqEo#u>Qp|Nov}S5MRZ%-~8qbGN+XYk9Nh=``Do^{2>so}bffAinH5I?d`-$=C6F'
    'd~~~<@A*2MADmVum*QId3UBxQB5C#~mZiug7@aDw$5x)Z(`+pMhy5z$lehxYJcp;*?|%I}9M4#Jb(~y;C&kOBJ&%X^hKDhJz3h&I'
    'a4c@a%nh<HF2|0Z<HLByPw_bRDwXH?=d;5&Xd<7%kMSs;7bCC4v;6vdnq7z=;;&d#A?M?yHSz+_|7rFU{#hd1`gQg+>w`aF`)IiV'
    'kKjuU<p-YkL!HCp*lo2Og|(jZ!}%?im*8#qEVl97AI2Frj*=JQ0342oF|NM+&ijHePOxN|d;<64*M9vy)W3f6J^T^(dF~H&#dCc)'
    '&NvGX;r*WTLw#8!+hbeL^=bAF{(wvTI(nMzz&DS{8hrA&?C*I$%txGxuj4m(+B{i^`JU@TJ;0anP5cJG!{{Tj1FpsOvmymK%|3rx'
    '{)hc$%gMMK+s%<JybnmT&3JET`6bpXlml@e{^!pHNV9tm$d|DSPpXx<_$`j{yq{*DVMe)}gcCf!hjj}N;SC+-gLtLq`mkQ%Li`j@'
    'sgeD$o9Fv5zHtkt&ycryt`FlH|G?xnawwMJVjSq#&(mxxeqJpP;@7+7o!$q8I*gTg@)VhdF`oa!_`qB7C44zYKI7NN(`-A=`a&MU'
    '%<Xc3U$_YK3V*_=GT8<1z)vw{ygbMIgftt88}K(Amnx_F{*_R_Hp_K5zfzv>{XtmI@G-2w!K3AE_#E!{ej(JAIC&AaikElco8A|M'
    'e1P9!^m=&<et-wD#RhpNe(l%U)2zWrc|JBNm0SHfdZ_0yG953(;W!IF!j;}Hg!5e?J75Wp#;YP1c=m^NzC@mfZ+l-5<^^h>O!(i}'
    'sG)q)`+-pBR>{}#^wn|*&ca&k?R`L+-G@=dvJJM!LHH0p=b!gVvmU3)?N~QTHo<(n9v{RvaV>VNFJJQhfOR3*Z<!p7&){<W8XGK^'
    'kKh43#ruXddlgUZF9+a5IP6-v$M@%i9CAXgM}OQ|opft|lI-r+_tR}F?!tdi*ZI?}8c$m+-}JsC-9E*X9&!TK>nTsi2{;{(dLNQ*'
    'iO1v@cmflS%WKi^=SHX7-<Up6_QCt`dG9CEZ6`j^U2gH`Q>ELHL$cLjc{#p>dn4;m^K?7-v}`e3UWW5<n)e0i`g}_8cT6gjSK&AK'
    'c4WOtNVo5C)&beQR*u23e!V{3mg5>cfX&NgS9}tWVd~>@0=|N~BhQV<NVmc5W#<lZ4qn+&*6AdNdY_SQjrYn6aVkEA6}S!$;hz{='
    'Bj;o5@8z43eV6&^Rz6)en;|d7+i|ovB<c1rzJvR5L>oC9_j+Fv#tEKREuX}faUIUxEm!#U|8TzW^vSXahv1|5E*`+&ahLCt5AQQu'
    '7UL{@3%BA*?|ahiJM2&;hvLt;+xwmHe#+!vd<5UcdfwNB@rpO#4BUsqQsq;4k>7tvw<^@<4%00c-@q;SE#Bw*jM8~tKsf&B`#Xbe'
    'u@BC~#@;7|x`91#JTAt%aq<TIAFjf^xXt^hbjw~Z&)*>5$4cLS6zaxE`6{+4l@H-!?|;&5JLbj6UN`_}V3GGf>3U8`(6<W&C*#-H'
    '-20z&8;HlSSBZQTzr<69%5+ThJ}BMp#z*lB)P0d~zVLpG_5LW-H~a?w#y+cMGw+u|{lvHNQ%otAH{%Yx!uz3c{4uA#EIdu#=6z9^'
    'Z`g8~OkXa0<1Q@leklAq+=PGNqW*G!WPQ6gUF%x#FvfeIly3iFNB>-8y4|@*F2@FbKP27W!#&ufhwO!=_zZrGM=`Odyb|xh#i;%L'
    'VH_QkbMYfQgmK5^82k)Nyzff4$8in*jLqiBE_gdWk2m^#nNT<J2Rx@pcEpkR13u`V7YOqUn;w?`!v}F4b~_@cdfyi6<!t#F?!;Pb'
    '{Hz@0eOj1*_%?ozXBWy;yckE|dOU)9E^fMctPHltj(7)t?fqN2wJVo5;UoAS#yl>2d83`q^LE3}?<nu~`!wlx-Cp?ywy%*TxCa06'
    '&l{v$=5*N$>(7vbG0*$AbnA()V7)f-T)Z4_z*Sg-UwB^^@(iX|%l<eUPv0%i$I<?Lr%>;)_hdN{qo&9N9E6Rh${pVCg*t;L=g0wA'
    'iVM8oOSjMQKb%}8SKv+C<)e6~_krp57p9fTi8u>i#jSYCcsUR^`sW%#ZcC9TrOImW2SbkAEMLU6_!%C@f3a_+d<mD~n#l7^w}$gR'
    'N^ZvOxY7H>bQ>2Z7veUIikE)faA!DA>tzux#=kLRgN)iJn|U9YZqH!_{)q*pa)jSE3gZHg;9W8DKkV03ZpUcv55qXamK8E>jqKs~'
    'lhXA$v)}<NERm&nD>ff0C;3E9x2LgtL%9_@cz+o35<ZSUV;%1Y!+gXav2(E;iPOCA3-bq`ijp5<)B3UpZuh<}<RE-(nS2{7@F%>_'
    '?+1k(+E2cXQT^rFX!ttr@IEeG`vZcja4)v>elEj0;s@Bk`?U-^A0Ne9j9Dx%!Q1dzeAWB94C~TE7UTEWxToCieO!jtx8O9~gA4p~'
    '6dCp}o;O!c#$~u0d(D%B@e%ye`?(A~Z#;NPkvta%;@#fgW!NmtIV`Wm`|(@+%=^3yn>1T4#cDixj%<s6`twyYETyv?k2^5GP+pG@'
    ';$7bFWoUmv@a9_iJZ|y+E`#T^XP9Ac+=V~kChy}i?CK8k9^8&~I?8zO!!mg8dxpJ;pX0yS)%&mvn~SUQIHt~!z3>?<^*$`aHsVoC'
    'Y$GqiEAeiu!Z+H=Z}C^}+cGS!TI#vmVSG)NUGR3Ci=W^<-dAPV20VyI@QNJyy?-t_!y0}eH=&+~pJCmw67~GF413A@ung-_CO6@p'
    '@$yu^&y-<r<M*iN=w{e@+=)kUY^r?H`>zc94x=~Aakv({R>~LfH1E4ItjTD3EB=oE^L{Er&wC11<Fq*WA;!kb*4W<rsW4vg8C-+)'
    'y^qSUAMgN9_x>r2cWf9V*I|F}mojVxeuIrG<WzhVo34>j-XCRH8ytjhqwhZ$mSF>;<pa1BS7LNSITY_~B>(l#b!1q-RdP4}jfHQ?'
    '<G!yf!>$=92Nug2xEjwIB%}QPQka)fG8eDI`|-5;{5|iJGORD&fy;0=_Vm6e!zSPoEa)#AT`N1`72YRh*h1WfC-7SDo5JzOmVUn}'
    '%m>_pf8(IVa!6$3#I*4Kua?O@<kh$s<GtSr^9U>OKU^DGCuW9ui=*bsN<5A+-p7RVfzROY_@VbL8Fm=|#<7Rxi}*5b#Xa~BHu8QY'
    'gU@Y*^MI4^81|ea$KwxvKPtmIca|IQDCS%uSNVOYFh38-4{=ki?D&&h>-|cGU0N=O;~?)#GIU)ps14c~HUe99l%L}P?^nXl-7BBK'
    'UofghuJAr3<cI0<QQYOvjScHyYuUJs{2$K3`S@a6`5Ef-8etydHaxRhmf&h!>itI;@0c)Io`=`sjrcD9h)t%*&iLe1xx_Ejg!7vt'
    'JK;LK+3!nb*cbTj7c#F(UVuZe0)N8$ye|p!xlG=J595C9=Y2=0Q`j<1PVs&s{QF9IK3?X1L|BJM$%(iNkD!;EU~4>Uj2!C=TsRN0'
    'auMdmNyF=K98SaUFw6Ul4C{k4aqtG&%lnE@mvARm;|-;9w%?Bm`2o8$k%#aEX2!@|ydPt|-w5>y$KZVxGHQ*y-TRG@6EL|%_QD<b'
    ';7~cj?^A{O6D{*_9B#wxhVmD`Z<S&5R>?{{h<{=FYB>?N;jP}6gn5s{y$=a_0pp|OgSY_Ct1sX7J|x4MFO%8W6*uD}-iL(wfl>YB'
    'IGlqYV`6`qiZA0ZUob+w!q2?#$h3@;<jsEnDAR^v1@6XXi{x7T6k9Kr?|A=_Y3KBib8rJzVXK~U8$RIuNT$_0CL7|Y<MMp(Gcs)m'
    'K8o+-N2q;mncC+NybYJ&QQyy&X@k1Sx%f6VE|M4HaGZi4;bGMCi!$vX4m~W_;x_ylcYEKGX{XJW=V2$j3E#s5xN(lW@)@b`i^#N7'
    'I?En79arN%99Ael#5cU3$+R8#Eoy&Urd@!idViB?eQ+7pFP8)HMx2QwAD2tK-^sL{czp+X2fm7{a4-I^qg;n4{JvJEW$%@*<JWk4'
    'jl2LW{XSKA{WD}&EXIfMd;G&M%w_U9^-LSkM!tz#a1UPY{Z6Kh#Rb@}TDIFQ2jg7thr;-pEU&;`crOl|BHzNZrpl|l56ZN=@r+!V'
    'h26am3iAa=<5Jv;|6rdgS%15H7@zk(DbxPM9c8kS_dA)k5KmxUs_f?dO(yr5GVL!+uat#25qIHC|GuD1dv28c1AB~?i}54xdqUla'
    'ldbV`9D$$Xzv%n7`(<iBMz95T#XE5>ZpK$P$VdGCQ<#TXI8t7Z&*G`2@@~8bzxRE6;q^C>hcGTi7U7GS(Ny-ua__G)Z4Lg6%_?LU'
    'Jccv<{#2%&T_QW<X78Ue?N@BsP<F%l=+E698OAyOgfXjS3%nF>$A`V23iTEJYh{8Xa4t3;Br7oA15c)XhaID289spraZY_%iC_Eu'
    'sjxmQlaJ#2*lD>e#Ma(tW!en<28Z>RW3QD}exE9gn-ek@r{Nuu^>Shu2i{L*(qFMo22Wii4QFEK#d4?jTcO@zy&kdvr{helLI1wH'
    'U<W+m_o*_i|1miX@5gWPjN|fV%<z6J)4sw(7&T9}!Q1_VF`4!WmUojo@Z=(yj{|TFK8Qym`#7Eq^YxI_bF9Mo!*)kxrQe6jw6xiB'
    'F7Cp{b7X5Ah>f3-N#3W0@q^p(Ao_CvgVS&&j`jX6)N$O3|KiEDvJ>{jQMe5E<9R>HRPXmPt?uLUTx^S_-v5PhjrxAXO#1?JI?C>N'
    'E&B6YUJ2*1M&5_j*wp*JFi&wNZooe<Wrpm4ci?z@70>p*F;m}17#xYa@tijDE?kSBV|H8F$@|8z-s3@RQ7yBu3cK!>ui<UpABORT'
    'n=omLY~lB<LT<yS@gqEpaXGR(j>WCm!TZMWKCp3>?6qC4^gc1unv}^jEW}bgiWA1meSY66(=JSrPvKJh5Mxti0$zvr`~9tufAEaW'
    '@&ddWAH!NKt(3Rp4(~U^c^xecyW@Mf0qc6d8U7yL5+~Q;3ctS<a@cw~1n<Dduom?^uuQuIU-SKsq3(>7#rP1ug^f#P{H=0;_nDzi'
    '$H=a@-22J!`|z|1c|8uscX10gStF18e#nr^ZkDfLyAnANSL0qx^!_u<U(AV?*I@<j!9VbfhH|O*o1t&O8&}H|?=M5W!5w%*v8*>p'
    'F7&=L7$sZOm-D>O47m)iStcjqYk2B%nTMOa-wb)CpFFw0%*O$^67TZ9GE@6G>SS48T#maj)%(UQ>xComl*Mu&W_drEWzXX87~Ml&'
    'g%j~*d<PGCUzufb$7B(X!6)z^tpAsM-uuZcJBI!|n&1-LfCcmAJKk4j>2tNgKQN(4ZbS8nS$4)@*$qcwCDwYM82<fiS&moFk^8;>'
    '%i{ZPvuq)*$M`~dIX3eCF3Y;(FPK*=FT=s!-(|6HG0S4gWg*^*Ww;UtJuWZw{w>Rf;Vk?R@Ap0~%i8aikK+RT27kupHS!(5pOs}l'
    ';5jqoNNnhRSr*^-n`O7)-S`y7ww2#{zZU*?wR{Yp+b#3%i@e}0UB?WznJkCler!BNUW~KxWbf0m>;YVfXXeO`IK}(1EL(wJV}mOB'
    '2)>84n6zEq>wQ|5y^3FA>oPe5FB&iFc;6P@A5O!SxCb-6f6LP6af8)(5bIaUnb_0&wk(@~`kv)1yB=$Bf%kD)_7cX#$sFu~Q?WE&'
    '-sgQ;mVJfGBM*cd5YE>K`3WYElvm?;+<|pV<v`rv{aBWLj#)9XAKrme@Ks!ncX~e-<}FUFkh@UNFAJ{+@4@Jy^043c3iT;kcE>Te'
    '9JgX-LwP-}@%vt3o~)7|VH5Aevg{e$h(|G@SdPOf_y_*a`>}Aov0Id!ho9jY^<{<kVPSmY?aSozn6O-y;Sc_~sw_LZpET@&BXBmZ'
    '$5#F2<+u%pcwd%fAE58Am>B9R{)M&PpJmx4i{!0%)nfU*_hVtc^pNpA<ybt^`>8A&isiT#n;)00agyH;3+oULo+}^0cd-h8#OQf)'
    'BaZQYE4+SeR3tm$F#He?VNrMajrUzycJpC*8&=?@N90%De}(yuQ)bHw963kU^?oYL((rnmgR8J%q3nd0;t7AFp-vu<@7KzC{+xy|'
    '&mNPfmdhE~_;GnLR(ao)Ww{+>cYFZ9!!tX|zTP)wX&-!W8Sci@YGeb{_rYh`E7Rpp+=uZqWC8X?{~ozF!t292ZDea)fUjdrTRGqR'
    'p)AX&mR+$APQ?3gDIUQgyX6k->HSg2Ik*JtPLX%xz^U?w%t+x1bs<|W!EM+(N3OuHah~@{p?+Xml`O#CI1InSzqZR5@2A4N#OLs1'
    'yt+(Iz(u$U2aK1`;(qV5!gxrLW3e0;;J^5b_fz3`Z<cd$A-1TLuiyc{pBHk-DA^sK!H@AMCXSX@VhPq6BYi)8RT!6e2ph!7LL7~Q'
    ';^jW?yRzuBLcPU5vBw5^j`vSt{^D%hfZyP67*i_m!Ysef7sfN*(nP+4AK($Z$@{L5t8fd}V$%wF3Eqv*VjJ(bvaB6`j~AE7;rKKj'
    '!OMrrmEM1a`Hvl=<rDY|c5NuH!exFxFiYPX7<><#td?0=h=cJN+=%<UKg+Uu#quJo#Y6aye~vASeT-T3Z=o-Wk|kJ<AK~+_MHZY;'
    'r<ckbm&utp7aK2^ow2U>aiL!0N^I0$cEYLN$7R{+-mhib5L}91`Tf9bYqLo9z+!wD|G^Q9<w@R`Wm`TD!3WT<YX<-GzAfAO9g~ys'
    'wBxcJZpGf-r)AqKSZAKBhpn*~<LAp^-lt{TeB6yE70Gij7q7zZ-p6HI=3&_fC*gTV<e%Qhh1W4#rs74o6Kk>F9H|@n*_O~*_QG-a'
    '5H7@za2uY$c7<{(ev9w<=h?EY<bWKF^Kc9Lb4Y_3cn#i%U*R8^>;*QA2Q0%Qe*Z7qI(3kv@Gjhs*&XFC-X~^T*S&HSzJTkn60fO|'
    'G2S1BafP?y$G8I%XUKc73iBS4ex0*Tw#BuPnQdhU?-Rr8z<rpqTUL1Am~EXW%d2oCZbV;qgM+;<%(nkw6&}Rc9C?QKh2iI8(<*r>'
    '-i8l*|CeoNm&uE91a82?*und~Y`X=Y#1^UYPOQW<@BgyxCOm+vD&;0T+55mS-|#KGaI_qb<@hvC_r5UOzQZ%)WLxZjCAbEE#`@kU'
    'Wa~Li!NE8Q-^Cwr?gm-U`@?J-h>c2R9q$XX_1x0nw|IJt?29+!Qttz^EviD^h!5dlzdskwGuADU(Re*>J|oiKWm{6T?1w9`K||RN'
    'hu~}8|7F`=Jax6)fZyZQ-Uo&{S1hMtU+?R(Evvq4hhKUh7mm|%S?K*+wjISQ`^i#Vh<mVCf7#vpvuwT(FVs!%%fk7@Nmz{oy<ZD;'
    '6n%gEWY(MD^^2u>-<EB&@d(EEke^^yPuarzwXiN=H@p+);a`}3T)v8}|B@5EU(2><@g4jf7tNDz`~9;}_q)mKaX3DKTQIIjUXEjM'
    '0j}|WF4V`v@=kmKH{&t9$@{rb_p$SAS&H-VoH=rq_ix$saiQMgAuKACW3ZX`Z=oLH7<?Z8#68~Eh53hPmrKJDI0ql}{w~|z#2Wlx'
    '2RRoH;$I!5e;@cO*>*k-!AJ3Zyrf1Jdp{TEDSm<{&yXYVX*`T&zOOQjht~1|)N?zs?Q!hdRxbDcF65YMnS<@{oZYgu_i5R7))aXm'
    'YX4)l-JdOI;v2XDzs2@BvIEZd{w&NdJf})Ne|MxHhWSw@3-DQ7h2y-h3hQ)=oQmJzO{wxRO!xjN<OO^cqbg+^Y=>{-_gLcnQ#j7J'
    '7`Nleqh({v!-6rgBYy7vRJOkVE0~3SaSkrSZP*}Qw!=#Ax5Cd^FYm=y@n!FyLVd@7Ft=1r!#!B!{ZcsoI3NGUMlmuICt)?-;R8A3'
    '4}GBDdg4GFk4vy-jZE-<Dci2VJ8&GngkRu)7(Y~gg0bF5W!q&q8rS0A*t?;8*88cD6IaWtv9b3{*?Rs{uvM|_j@RQB{2a3e$>sRC'
    '_fOgO0k(*ex8YuF;C)lbhs$II>iZVM`NM&J|0~SHesT~F$B*!{{<4GjO(6&18vGfXdH<ASUGNV46o2r(Du?HI<k&fjWGT+ZjkpId'
    '^!_Qw{)dxr9gglPhj<^AV~^oeSb?=zcwAnBx8o<c!9N$4V{PWjLHH29gJ;i^@o0G0d>QTiRF1`Tm&?7c%CQEAWjmaRKjKB+SLN8L'
    'v*la31<#rz@5a~h<BKB`JIAi;EN{a%a1WkYC`+)f_d_{$TCF@7xlWmqW3N0Wzr=dw@&-JF3%&ozu`jT^gZu_Zd%qLTJGR{`OK~Dr'
    ';~w;V|G^g67JK0!?BRV+jxEOba0h-jLk{%5C!8OA3b*3tIJu2ni8r;C^ZdSAjy|s(yarF%Ek~g~AC_ZDljR6pgeOgr({Uwc`ExpQ'
    'Y!-IUmJ9G-%*v7H<;r)lnfFgQb_`RiWKW!ctGCOe-cRLNY?(~JD{&^)883^xf6B38_%}Z1eNvb|cnFg#<zUnou!ix0v+*~KA1$xI'
    'mfrW|*kw2h=VB%5`@wT8Z@qjL|G@A4{#lM)JW@W5EAcRX=ldCR?C~b@g&6sW_dPj$9xTU>cz+Y>Qi&Xb!|-{WG*rHaXLx^;V?W`~'
    '*r1V|>3vP8lX%W**#QmrVc)l8f%iK(dj4#%VX?dg-}AmFj8pG(!o0yU?{9K!T0i+8p4neMfmz<qgn5B;aT(V4ekL3z-0aV{$gy)5'
    '$w9aezwrJg$8vkfYjG4V#XZ=*rySD@eP3XX^*$yi;dHFV`p2bzZ|}_T_i&u|Avxy5H`osc;#7PcJ9wW#oeu88Q;*0b?=N!fD!dxw'
    'y`Kp47zg8B_#%Fe|6#vEx!La@g?U^npTIBisP`E;mRK&Y#M^KoF2UHx<^8DpNnyU>7_7iQFr%aF;(bMqzVA2qJZ{4?YGewI^gbhp'
    '=L6>0emsH+GvqkjhI_s52<t^_*|Lo+#Zh=)TiMk6i?E(!cf1X!d@axRz9ZBfT#p^Sp9senU&VIbM}+x<Yq4{cT!1m#<v;kA-`5Fs'
    '2QMm<*Lxok)?M6!KjEpV@={DmlRtW25$Zvu9En$WpAgn#oPyJF75;$@N6Y!R4i93E_YvXz;x;@zPM(iLuxY%E^8O&yb=-{gHpq){'
    '4DRs#a5;AJNSTiV@J;*<qf2E6`~Y|O{hBaen#f7G9FJm?rt%8h<$Xntz3lg0LLDuU*Wvy6EuJ}4cK7=&Io3K_PR0ee3~y{GqrD#p'
    '>n~2gC0K8@T!nvot`BuBO1_30@Hx-*A@3}cWqAE^`6kADZVx{f2ltl;{kaWc{+y7Nc(3R4TzeJ2#6r*Mx%SZ_xgGVr>bW)xyZ4Y|'
    '@rs_Z(DQb#b-_EZ3_rzV|NrNnyK`;MT)6>1!IS67EAei;(C=&Ha=#<jKE!TCaz5%gd%1S$VY&E-G|$z!HWFv!5qxQm?CAM9*Pg(G'
    'cv+!*)N^#M?ZyLmTdlm*b9AnKkB!UaMK}x3^xT|lk7L)4@)6I)x%MNL*2p<{q37IOyWewcuC2s_IHZldy{){@^K7owua<4G6OO`%'
    'aVhS{vv<n}J=f;y`+<Z1;GQY+KhLwdHYHmw$8Yfb961Ev$Jaf_=GrbiwMssOE4Rx$&#Ae3-fD0feuw|~^A2(?D@E?cM^a^~=ha-B'
    'fUjT`o?9vJ_JERWU*HMM9WAfNZ}E&V@&a7w&*RRu*jV`){(~8DvJc*eOR*aDJcKZQJm2P83iiN)4YHNz+FToi<8UEv!!t_dD9^pQ'
    'HV-RtKPJS;bll{5IM<RY<U$;<M#g&%4)p=I;+>v*bL}bIj7>cEhB|~FW8!LA<Igw9wY39fY_S}JYkWUfuKk3~qU7!P9Da%^_2t99'
    'uPc}RUE%#KlXGwbwpuQydu|S|2XE;o_u^&!<y>s+IXRboTw#1;1vd5EoNIqzW6#OCb}_~;mcB1|S~w5b0f*w_*rKOg?m0Qv*5PT#'
    '<W2Y}?!gwv<$Hd8KiAHhCojZd7&l)&<vBXn-oS71j3Rjf{*2AK%lrKLemKv#49`0(*ZOt*Tx&gB-hdC{0$ha+=g5hkpF`ci(+lMg'
    '+<~uot`7C2R<^;1@NHb|`8upS<uVTk;52*_qaT--`*r+K?{F*j>%jjXPwOb>`tuKRt=C@pC7xR&uk*Yd>JFYXL+0Ui=+C`*BiCNU'
    'J@^myX(Q{mmGAlW`dsT-EtlX8yX9~Ge1lMDC(DEA-#1o~%X8F1-N=!<@GpNpK`#5HLS3qo<MD{+;#|uqlb7QH{2aTFmn}RWhq{5s'
    '@tRb*#P>IadAeC{!ryU<?`O)j;iKd%JcMzh<yE-SpGS~u?PKLC>=Gvj<FmLK>v`_Ywaz#O=io+M=eaiID*P3@mC7BF4;X$M#zhnP'
    '75;?J#mF8_Wn0g)xjYX$)N8!BLe9oH_<-l$kY`HdP~4CH9M9U2U$C&DZ0)%<*Jj}N*nPDehI{-vcbNC+&zJc<%x|2DJ3Y^aalTAW'
    '$F*347cQ4Mo@aBdKR%1!;u-yAG*;jdyw3A)s6Qv<Qe2K-VO!6?dHP<n;KR7X^KhR1hXWSLCAbRrV(enM&2w^|eT9vC$TZKrd3Fs>'
    '#9cV>xO@mN`b%#2Je+5F^W*?5$Kn2YjXay)P5y&@i{xg{!Fks6u$+KjV%`y1f~)av&%=4vV2+&S`*`wfbZ0pq|Hj^h@^;U`d3Hap'
    '#ZT}L>{%-p;11O1HuCIQj4qe0uq$4Hci}{Q3Af<~ew{kck~+vyI2SANIQH%+V?1}~*=_h7Zo=&~@?yX49L@tyLElds9ELx8F3(dP'
    'ZkK1zRLhHY%XNMoInVZCqsg)qKg1SOWH+1`+2?vu`1{#%4K~Y>pWsZ-)p<6%N{-tudq(b;b_u`t9vNRIZ^4%1WoysTc{T#y$Cy+('
    '9bfb3hUHoDX8AVeRLTLKqw{Pf?!oBMawtymoSbLN@w7PE4hQ2*d=Fpo>%)0guwI^v!*Dvz$JJPabNu>oo?SOmPQz7r2>W<W&a<Uh'
    'jrC$=eY^;7#6RDQ<mFID-j{VN<PA6-8?KQH{rYpBoxuJja-M(QBG0y9?`T<uui-%))KI>S@&1PLY%zX<C$E;5d+rYN6aU42#d10>'
    '$BCZ9!@R;HcpRVcyq!nh&NIU*tg~Ex=D9l5G0f;M@58>=%I7^#hx3TX@G8&MVO-;HzTYO)i$!uUK8xG13QwT7anthbQqRkwuHkdI'
    '__%z>KMxV==v?_U&c(*_<mIUSF?rU!NDjhEytKRQ<oP(y3UMiZjK5>z5$RuFGdqv(Z_l$A=g2*{)^l>6o)a1DQYeq%&z_U>taGiL'
    'gIE3}clzfU!aR6PZonG6rCdIRIi7>_Y$|T*C?EE`n`is6YmJ<Z%RLz6SuH*>LuPxf4Rry(#s+O<JG=>R!(E<xL;b3jSKti%9uIo{'
    '4exuhT#4Io54N8oJ9!??v)#BKcX|#E^SVl&i={XnYw!xs$9eVzDktaJ>)6}#Zy5jh6uyRKsd7Iq@f&k_>`w{j8|zle2k<J-!+G{O'
    'o;F6d@cbLbBUa(WIC*NkO!9o2r|<O*F2X8o?ALwsZ0tz6758HAQaKZwd*02n3QUcWy>J4~@w}U78}Z5txe9aE$XL&}dF&6#<9ct%'
    'L--k1_;ucJexl{=_&k1sJA6NV7^kb`20Vh7ua<Y=EuM$N_{9(K7u5GfhCG5R@gNQwBwzLG#9_U~TD&AmzU8?(%y0Z28!wZ?aRkOM'
    'muGs8&eQh-2ajO${_<VV$9dY{82k~Ncs|ZI!_HWWb8xli=6q|kNXB9(9EKnM|DP|GZ+LFb*YiVyH{*P4)>C?2Zjf&ia239T`*Fi@'
    '{@inPzHP=DOqwtIdv4CRskjgu6v>I6qx0=OJoT_F#<}=5UVKC@^8Fq8Hej|a!<Bdt*Upi5c+SqZzMbV{+>L_^<xFgHiJaiMI^SB?'
    '%7M5V_hDDh)%o@^=9J4^d;|aS+?=oHIR^XS-MAEA$7IjN`PLJc;7+VtBllv%eR7!R<$QYyvuDWu*v)fuzWs%1ZDenJ4Xd!8=jwdB'
    '8pq&(-Ez9`YtOg!ljPXR@+15gGpERYxCDRk>)ZL3mo1ND;~aUb=j?pGS0&$$Vq%p{!>h2)cBy?CVSZo{zKDIs%W}WIoo~%kWEXrM'
    'KgB=sAMBYb&GUHp`}iBSs+5y(A^z<7Je-HovZ?3ne7gkiz&~)m=kGB7*URB}KOVu$H^}ciZ|C#<k@<EDet=c@3$`egU2%o)<H)z0'
    'n#kpN0Gq_f)}FWXtrzaYiz?)BoP|qpn&<9(JF`T##}X{Z3j70~A1bRopXb|o(Q*#{fd0IU;6^-zpZJZ@FkV;5rC5X4t>(`?m*?9B'
    '#c~Kf?AN_RJ;eQ3QeQ6eJf3eU%jEU=0B*(T<+39d;uO#4`MTd2Jje5QzP*CGu(jv#d>er$dA<(y2Cu`3_y+F5t-gOG%*P&b5<Y=j'
    'a5tXTQ{Lt|J-i;Qrw57KOdRL=Jk-B=(x0PPo^SJT3uY9_K6oE~g<0KY8@%1GZ-?`Tf8uqA<zn1{`A6g!)IRony9=kxku5y8hxG?5'
    '@!mo?(DQq!Klm~Jjty#M86L#pp5Mc`!?<!8k3~2Z7hr3@uAQ&v9|k|gW0=}e_P}#I@8@g(UvMM-hB-BI2iDmqKlDBz-$u`nO+D9#'
    'dWpSpCjQ}hKh&RUISfbOd~CH_Uh26%)E%6FAK)Rp$@6`_y^mvZWU=S{FkW$Zm3$gM!uLEVhdNRwAIIk7<!;}P9>#Bq9E|Vc4_KNi'
    'k77N~_u>5GYCO48cEbPR>z?;Ry%;Uu@q8cZGDgM88*vEE#3jCOJYUyWf^Xt28{{}Y&|$ol$_n4Nk#E;Dk;8C4zJ_nb$hCO2=lf8n'
    'a21|ZA+vA*4#sJ?z^{9Ux=|u8!oD~Omt(2-0bxDIUeWSid<DNm|GZN0O3(ix7vam8vszw@Q}CeY|M0qsWgi@bOK}@6@thy>Q+*lZ'
    'IX;YEyaMmSA)ezy9m6enO@CQ(t$fz=d>9Y734g}kp5qJbKAehQ;oQi0KdHc0;c@g~5=_Mj_@?&*1$GeA7fIijdP;#^RVMxOPEiHc'
    'zlXdFf517Bd2(8Ty_h0D!%?313+zE$i0iNtkK^N!>2OAY_OS*l@c?e}{-D5q!{4!8Wd1ZNunqVf{)YawW5M(B3S5YXysrqyr$~0k'
    'hw<0QJUpks&W)4Z@Nyi8qi`Pn?0rdrwLdKHz}q78vuT0N#^-Po{(+}&kS}^aQeYeLH{2AN*DVXQuQoUwN8==X8kgcn_z6~He5riZ'
    '`<ep#5P!u7BQL*If&GG|G4f7)%=?`Jt4063R`7OQ7^xRY1@;~`sgQ-Z-}|2eeQqn*0yFVqyaq?0Me0ggf$c-z2OPW`C*mx;#rvZI'
    'eJ^uxDn5bpP#=E@=iP6|7HEHP@N4`5kK<C0F$MM(eum%U-&l8s^qhEZ`1`mWkK;|n@)n$k)4cC0(Ea7$nQi2G*dBY}P%Op7$h1AL'
    'z=q)a=${*FS73v&1ZU!@k$QGPfu8RcEXEgcKek*h^*t;Fwi;`2K&1Y43dbE+Vg>sB!{D{v#}(K~Ir0MhI#LcV4zD*-_N+k95eT-!'
    'E_k2!c?CSDxWJ;SWIR5A596<qI(SKeB`lINa30q6zOTS8!|U-5d;zN>_42X;eNSL;8a{__V1Mre3v3E*!9J0C*u6mes)O(1@A#Vc'
    'hv9rw%AJuqcvYB}=-<a4^zWhWQD6n5<pBIRQtx_&afv4|r$~0dLiGKoy$ftPW<=^(p8|cqd$2bS!{PW6euEc!pIM;ikY8J%>n_3P'
    'a54Uj_sx;(ydN#l=ih>R(D!lQP+$vi1!fn@e)trA=KW`Z{eu}Xa#f^W4GQZG?!_8RtChWQ34Y@JYB=tgTp`o25PM=VUJ$8UL&Exs'
    'FJlMqQ^WkjJ8>I!iA<kcs9V7oak%%b1$?hfs4F-R_hFlcGCxw+h8Jl6c<>l@toc9o?mXV=as3~E#>hNn8zRY+u-81Vb*;7bu68Af'
    '2!}#aC}XC|kP>!C<~k@tk|9M!k_;IlC)vp?%CrrYIa0rCy<V^L&+qa0K90lQyPePZ>-mt{dkydReP7r0zVGX%ZII9U_afhtKglg;'
    '&{i@b@tojH|9<56vRO6VMYfbt*;(e0H~ah~-;*mP&hK{jkQd13OXJ|V<;*|aYPk#Y>vC%+&ym;3aq=~JaVbwZ-{-COXiqsv-XR~8'
    '1?1y?pUdI$N;y_OSgLDX?DOyybh6AKU-x-Qj*$<`H{}Ysdk=bmystDqUQ%uok=K`NJzF{J!tU2{FXZ|D^Gf63<>l7AhPIV&;CY;X'
    '?-OZMnmk(em)n<q{qS<Gt9MNvDQ}f&<o`Z@$xG$Ua-7_%H11tpZbRgaa*phYdO<n&7rHmdCadUErSWj2zYm$8PrJw})D?VwlB*@w'
    'GrKw2UA8M-4x{`&l#iqC;Blqgs*0W}`^%3?apFz>`O7U^(74RXQzZ5u-t50eUL>!V6XY!UZYj^Z)$cDEnoF;h6Xi^a^NwAv<MaDM'
    'PL(s{GP%zfdR6Im9$U`mLN4|%-r@15Tq5@_&|#(V^e!KN<p=TyITZDda+@pPlbhAjd*t(_arAC~y|Zab_K-bgwR}Rhe1>j>I*8AA'
    '^5D|2Il<!~*<X&3SIfucUZ|7!xFUzk8|4)FerY_N<ntZsBtB2chvmm|)1~y5(zyAs&(jk74qW!h_WP-tR?5B-eHEv8{v$D6xou@a'
    'evap^<y>d({w~{uXkHGJt4q(TruqEWly;Yw%MtPs*$wrXa-9!bZvEt?@*TNc;(VDW%DGR%og>k&W~TqSyjtEbpOg2M#=BYmdQjK#'
    '>q9P(t0m8ADz}4VmFzBmEscNA_}?pye{+0ZmeWudDz{hVSMq0xJlRdjk4i7_dH=p-d?Gze4wBfvIoIPGd6E27hD+n!OXXISo#ct~'
    'UO7`DpMFK-;46v`UF_qSr*Y7IO|Ftf)SJq=FZ4C#)9z35qtfm6y3fnwX+&Nuk3~Jo=W{t%^86_O{!8QFLgmfw_j1!J8j@9Vpqz_('
    'md8tS;}$d~kC1ESSEc-UQMr|^q?K}nd|a+Y{mVbkxpcT3D}R({l!mu=%I!t@8|q@^Tu0=-D_6+<2hbVvw9>fuLAgCESIG@gA1mkj'
    'e7ARLd|Tpqm8_L3<w3QyD9@AwP$yF!ysVskl3nzvboZAzdAht%z97@6pZVu6`^bKBsJvM|BtI@aU;M(qk0edXvt)USo`8Cr&o^?m'
    'Tp(*D_9cGhdHzy*59)A!eai)MhZ!^{zmwBT<Kyyj_QQ1dtEL%wn!F12JAeHW`)}RHO5@=78Xw)3A)1hf$z$Yb*%I|VA3x>E@-lgc'
    'Y+AZ3e)9WAo+xKZ<jcQ!-X#ahYB@zdA@3@Uf4?ekcBjj?<vznG^5@l_FUc1r#>X|~+}GoNBM}#__3=&afO=uT%H_ML69(*+8oDv+'
    'fd2pG3Gy0wzyowc)CU80h&)}ME$@>}P$vv<pRs$U94$YR*dMfcfcdaHMm{RbP$vx7{_=8pjeJBtFE>TqFksyz`og$_Q8x_OQ2CU6'
    'OKvotZYOI{M-14`1L;AsyL<}u!vOPTx2MFuq8<J7YC+58P<f?%ME;6;VZe@9NiUVR$cN?Os1FA0L^(;$k&ER4FH-D}-X*{|&^=5J'
    'lJ`mU-*r2q9vHCe<$dx^*#`B%0P}8lrd%LDljzUu?jR44CaY0L^zTc)E|<w)<?nKr=Cqq!g*sz^`?Fn>$je&=>?eu5-0dg_%W<;P'
    'GxTEA69df0-91q+^#3m}l-J2#r_yrN3j<aq50yP-KRHmYmTdnY;JQ$Ex|}aRlVeba3@~4J=gG0CI|gj3d|Cb=k)ON$<tC^*2AFTV'
    '7sv}G^6r4YkDl}%iFh*PpMQw%Dm%#YB=YS@z$)eO@*KGx>WBerE)SMPd8#~9z9PG$t{7mR?Q&g6fcs(G{f5yiQ9lguJazXu`Hp-~'
    '{vwB<zUcRjd=quWfYr)hQ8x_OPBpZL+yV8#0QZNvN6BO58S(;oIqHG|=Ed&rLufbD0sa1!&&s*-8`%nV!GI;?XnBjAEx(dw`_L%r'
    'g?=B)r)7845B)lp_sU6fru<wsnNN3+ccac2uxY3-`sXUs11Zj@=oaAlO>RP_WDofR){zI;huGaq9w1|~i|j3LkYnZMs4oV%f6YBf'
    'UMKI9Psz_^*>|)j>XHE)DW8z1pbqKZpPV6=%5BF`<jcqTcqSj0bLFe@W4YA;Ivn*%{~qO3`JvpbK(~}!N8{JC{6PLBH*Ze2mr>bQ'
    'Hbvbs!2Nb^LcWdqrQb)hX;5NcUGD(*<M;8;UA`g@K>g9@1KC5KBrlayWDa#mzy9Raa;|&`b;tnwuDaN--#=hC$w_jKTr4-5K_{Z#'
    '=s!<>EU{nDO^l>dQBMrmLb+BVuXb;hKcTLu@y|UfL}yE$+Z|xu>^?7FMIAA~yxHv~FOfIN2jvLV3H|lUITGg@U+nXV93}6UkH}+&'
    '(b4ik)C>LokZ;H;)C&XLhvM!p(TCvDfPE=jp<WnZzU<aY<j0r$bzejGmR;pt@@2e0pC=~Lz2qRd+XJ*S>VzI&$_wQJS%vzb|F=93'
    '^+1pJ<aoIs>VW~~#qJP!yS!6QldsB!@@IJ_>W4n>$vN_6`IB5FTg|8aQBU;yQ+_X3md3?V0Xumhy+GcKI-<`{@*`PRMdzS?=--F@'
    'MsC`I?jqaCD%1x9TF(?<pJ;cUJOcH=0P|t@CHbLj`69)(-`fNBn4BwbK^@TJ6nW?XI#BjSJutw&4DL7b+ycEG^}c}3lFe)BvvMZt'
    'em=j<rY&Vg4#YYrj~_<UjBGDYmZ!^G<vytE`F$sEmiNnf*as1?<C1i=d>Zw=0N0hc*P)*0^M`y<elB-hO5?I8>U=(r$WP_ANc{Y|'
    'K^@NHcR5CGj(VHF4|%=B_%S`eb+hhBIa*GZcc9MZ@w2=J^)$ckCE}x5J|4@da*4$LO}7u~YaVaODe@`VtSx;2^|b)^ak}rxwX!Md'
    'Z2_K_;+`mjsH=JWD0|A=<hK&}=ktEO$$oO0Tq<j@jw@glgXz)oY<aG%L|rYwbu8{Ba;%&phoa8rpR0UUz9(@G<~+Y2<X)>N>umw{'
    'uW;{2oz2H}`IX#YJl#b`<pk8(d|nwy+sfnRkEpYGo>N7ykPo1q7GU2B7yC;W`8Xx9U&-wz`^vW^KAy$?b7Yqn=?18i`TLWD<kRvM'
    '*<=i@MBPmJqWgwKyyIej>IVVU&pZ#3$O~Qcz4$1=z8CIN`7`Qf0c%}LFOj>TUgqNk>Rti6NVY&d%kLL?g`6pohkfDqwHz<e{-!p-'
    'eR*yX^{W8)o4Ws$^W<Sm=}V|%`R5^jkf|9I@yPN3`v<ry<yO^n4|#wbD>JBP`R6I0lcAoptL!fa%B$rjsAnl(bKA)&VY&_KSbpEg'
    '%jKOCdD>3_*8P7{UgrKFWAD?~QFsYxKZ}14@^(2_W>ClSJY3!?$H_y6(d$sp^6Nx?E3uDujbB&tD|sab9OZ59FY-*(w}SRL>RUnE'
    'u!i=RcVpdK(6*XLx0CzJoV-o;M?EWOd!b$xWd9HMSUE)AD6yPr^C0sx_axM%f>teip)M8Veq8r6xh?8WLAwfdr=Zre1-T#BO-jTK'
    '+XtCnxkWizet`N@&~|D;12QVR$fl?(1uZ2vLH#JmyvQ9WFO}8uT-1$%><i-lCXxT_7PR?tiNrYIBJXJtv^(WYxmbQEn-%D`ax&^b'
    'LGJ5yv7gtC$cIo53fj98&lla@<t3;G`R|b%&!)rW21u-f>@(tiiS=aux%Q#Q$RTpLTquzT?H{zG<Yf7QTqUC^dO7MlLAzBxA~)KG'
    'o`gD&f9~=L`L^76DcwzC-|#^}TO^SexyPWs6XZA&2-+KRvBY)__aJ$+{1@sze*MV<LNq43%c-RYLy@5E+mxOlFO^+U#|c_rIYcg&'
    '=b)|=v_bM^StHReFzK&fE|eWn#|d&hggYK}oS?lff0dcG^ayzu>N`PuRj!m<W8GNLTFaAVU-=5^K|%Iaam#9GL~?(Szb^Rz>Ni2|'
    'hj7vNzhltm$*oq=v8c27`$SzOXmjOva?kM;eNwsxEhwwx=cu;??OVBP6>TpML7gPX{wZ#Id5*k87Eu=ovM+`EPuT|bkf52oS?-TI'
    'h`$awRIZdaqu$}4gZxD9Hh`jDe0-4mOM3?G%I5Sbth@5-vX<^4kCs8yC4$TY+{0u)$#qmg_Em9jlCR2>QI7~R-glprv*pRCM+9w_'
    'Tqu{wFC_YKo*v}>X?Lc4U4AZiSW3~irGL<t$=_sV2E7aQil9xCYbDkLxC>CH2(rJ6`;FYHCr!vf68o^v)&1)3f%=4xD-!3xogcK2'
    '94W`hCnS!kyD(_e<p!ub__!jklB4Bh`M8`XUzHzA<R625yqB>abg`U_dPR`u4!G}2^ohAN$o%3mzb|A+Zngn^5cLYbp5)u|TX}E|'
    '4al{qTloDlkygsvP>%?5|F=6$K81Zyet&eON6RVlgMa@y>J&kq!|jImq3FwajgOP^7Wt5TPA->0)E)fumiNhD<z&<y{BxEya+C3N'
    'FF6Z!i6GDEcGt)Q2htw$6!|;q6MkKz4&m3Y+^+>aUS1@B#QrKDM_1Cr<t6eXtX~S+-gD_;@@#pXoFs8h@$LTe<peoRwjD#SM18{J'
    'I(e^rM*c3(MSUX3J~=KPyWJJEU*tB;X*Y@dV_eX7uBCg+(WqMl*_Yb=L2fad?j^Hwltg|qA;|N--Sg#0*&cNWf1UCciT&@BeBMRf'
    '!RJZ2*HXI2GKvKa5BujM-;m$SmNV#WSbyZ7kNidMR83pR(_}xaLke=gjJsh^x~Ci{u^#;~#S89T68qz)c|0J`k`rVebqs%f@6%Qi'
    '`{tkU*DL4BTTs^sa=-knAoB(HD~bKTvxC-2E=64;$n}vf(t|lc?w@y`#QGoqyrk98Uh)k21l9p5UvNjrTjV`*Yb4e_56W*P)<M1$'
    '<nwQLtZat*f`2~pWO=omC2J-6{J0mO4iV%!ad*d6w3X~H7o#rW@$`K9G3pT>mrCRvF8dk#=P36cNRu)zw?O?NXuaiR)FFKQZ9${*'
    'B>A$$IpvFd{8&kQ$&qroJRbFkAo~NkH=y3&<D2|g;=X^+KS%k5++qO5e*F)EJkQR3RDK|lXSnQN98~{e<r!|%<}@skXDsn?wU*As'
    'Mv)-<2DxX+%}|dBav#5YtUN&?fB4M5=Tm75)FG5VxDTNo5#)1Wchha?PN+Y494$x4d*p-iS-DsuUvM`-UBcrU)FFJlsiwzB))|y1'
    'xWCKSv5v;aO}S}^wvzkFoIFzQgL*<x=T7?PERh%d6tuze0l63I1^#`>$K*ke(oU!s1nojOUfw5X%QbR`Vf1>`5&ZL!|B^@dpy#5V'
    '5VY6i^0st^T!p%V@`ENJ>nexHfv7Wt>_?fYp<U!L5`B+03fX;fCHC8eti@m&zyKMtoNO<b$#$qGgm@l=dyc$HJ|$n3*mvD5WUt6E'
    's56A@CHaFy-m!Iv{rcVKP<IH~bkrF_%q!e>5`71D4B4@=CF%zu%ggiSX!)}IP@arBLP-1I{P)Y#P)7*a^YTK}4?@f*T=W}oN25*<'
    'vUdt}7U}{a_8D;3%I3{!QJyJ3N1Y(V`MFidK0(1IWc!S!X?e6fSI$7bAL2T>{X;wt+8rfl%gvC_huCMpoh+Y{J8na>@&d{8SVH!s'
    'Ja8$Uj=Vl(-DXfc#|-%OCJ*jOA4R?%viIfp5`FyLs61J&ME)MKj!kJ#d7FGvo`8Hk#6C^#-SS-I>HhvD`VzR<x19{Jf0K)Kz3C9='
    'X?G~{^AO{FH`|uJg?v23eg*DwxefC0kliT<AP*1OE;V#ldAz(@PQ<=0|9mFW3b_#d_53=K2M(sk$l-FTJPLVy$gYsrNuI|NV*e+%'
    '9Ql37-j?6Wz$*Fx^8FC|q`DK3=ZEY~iSuRMgCzPvb@lOPAjNs@-TZTtpGx#aa37I4kL<`0*VVdPA)oj0N><CcvJ3M1kX<A%mbb{M'
    '@>Jya{&|g|_aLti**N6$A)cq<{wnW6e(&RvWdDzlwU(`r*ZXxN50hJA9YToxq+GOf=pC{S$m2uoALR~|h?o2N?~`XCPxsGR{w&wX'
    'rpV7jHdg*1aX!2IH1hKh`$@UzC*}5)@5-gf(?b@jrsykmc8GDZJFX`!Lmuw$ANhC4+RCE5K^pSzkoA{W$QR{za%be@A?4>GyH!q*'
    '&&htsw|)GS7Y?I0BJU3Id}g;A`E`i>6x_M8R_=)WI%J0+Uk<U4)D=E&$&5Tg_LKV|Uk<Uq!f?%RBm8=k1CbYp?0Pv*_Ci7uvTG&!'
    'D2xo*M{=3`O_m|w4e2?&e^2A-N62sedKyTlAfNU3C!<yLWcd~H+YtLLxC<oW)0;!=w{WX}?sIAKMY<pIQGeZXgnV3XF@_$9Jk-Y-'
    'IYLgAA4<fp?mXnFA@(7@D`cBCr(4Ubk)QhOk{j33fNX;2;UV^wa*vTmAm8-yNIoh*k^3X>4B3%#sC-QRRO-txDa3vZ?t^l+EZ>H9'
    'MV=aB|0#ElME@zb7xGdckL6c#4)RgIUnTlbxu}Cp@%dY}>`4!hLnY$T$9#O2?@08epBA#i<p4QEJ}BeJM?>8I=T;%_^q(*B9BXEX'
    '{i@t+<vsEZ`783#5c^Wi_W8RlJqvkgh<zU1Pvy_@cI2Uc9n{c0kyrXSB=3{U@%%f){mE`idA=Mi5l6lh;yz?|oGe2=8DifmcYqur'
    '@0Ug7mm&4}_V{K#Z7I(}9vQL~a<}nx0rJQY`!Kk>$qw>oJlFQ?rHURZYmrZeY>yUnl-v>dq2HhK5_v1~MF07C9_`l;2G9`uRJpy8'
    '?<sC{cP`LfWQBYRd7tJf_acdXY)kxmmQTqYYH3a`MLrnf`W5#Z?BnqFKboc_`c{1w(s?%__N)3#apV^s$I2PV{}ea6whg@-d0mLl'
    'h1?J2c1!8b5^>`<A@-?qA4A?3;`%tZ8J-vW=OEEX;Cuf)vMKU4AOGY#@_6KHA-hH{!gJsd_r<zBkbn8OCYvG8@}Gx%%I8VsQz5Po'
    'X%go1lnugGgXgkgYci28L4FjrZi8tLd8QmD=gJRcvmx|T^e+k9<z4Aic?I&Lu)QOfOZG1e+a!s7rfx#sk9;Z2{ig0BiFL7Chi##J'
    'Pktc-<LL-_FY>Ff&6Eq|0R!o8$h*R}Ullz-wv+oH?+RO2dAPh<eu2Vf*aokpi)07nSz$X=o+7&;-wJC#fWIDDg}f_lUrEGyEyC<~'
    '<?dUcFCpIwGtP5=l1-XZ^uKBuwjbnvwe&qaj}6=Rl6^tKwx{eYA4Yx_=6MkA?lL7i%5U-9Hf-nhp_j_n<u1t2!t9gfUM*jhh#T94'
    '?Vr++hlRP%(|u9SMLrg`rZebSaw__K`1eyy7sy?apM~upq+MYv$}f<Ag{{z(4v@DazY1IAecBKCRoHHkEgz*%AioM*f8<qRo{#Q6'
    'BO^WN1<13)HcNgfi*0EK<XK_+Tvj2^3fmgwSz+6*hQ=iN2NlDXpGXgvx5@<arm$^+JSnXFDQwrv{g5w(8TYxj%b9YyJaHd75_weE'
    'u0h@uW*yT_%W24;e7ult#?#9r`fPReab_UB0(n!|T2;}g#5&6(!xolnO7~IsuzigDCv3x!|AcL}d=dFi*mB5s!ZuW{luZltA>=<{'
    'n<L+mt0dw&_jHMPu2-0K3itS0dcH*8t&_sGvuq<TlWR-&OK-ofM$-W@hkPk)$H}Ir(u0sU`M;M#<--#Fw@wS&CvxL$DB`=*!*+rk'
    'Bp1j<axL<xu>FpFDQr7dQ}o+9J8U!Lxma%<w&o$aj||GUWfJ*Pn9md3-pGr5e3tCX;Nz^ULjL2QpS)YHmgvtlIBZYJ`SNk(KVdzG'
    '4D<XI_wcs#M?8=8@e9ut{l2WBo#jQ6eHMM3k{8H(WhL?>zYpbka=zRJ`I28B@*G)#e96Zjc?R;Kusx4F$j3doLf(XY$ls^@M(#3@'
    '9xU6-bLGy+kHWT_>@Lri&5<XCxxLFBD_@pZB7gF61bLJHTzRWZBTow3&2rZ<6n(A6hV4fAjGT<T$j49Fyg)ZC(l?MVh4nnouQ&NA'
    '@}#hBUrV>ab2<P0@)o)KGxTGuKlblgCP&j#<&E-_(!4XlKbJoA6nVD1PGWz=#4y(%x*_CCew`uj3EP&)bNt`SSCQxV_|%hLFTcY+'
    '|FCTqq6f<5*x&DezbRcKzd;{HA1B|VPnF`eC;a=KOiz^~<l}M}@))1rWo#HNAg>8qPdQn>C*MWB<KIVH8j>5~d7IDgas%WyejUqp'
    'vMutPupJ|Z%L(#1`8)ETu+I7Pab1p)kIL<k@A&5=Pmz~P^zVJe$2obatd?)fkL6p)hy3>;9}3&k@=bZje0r?B4|$PamvW74F`gEY'
    '5BYq6e8{iIDmp?QjeN+z7m2vfoh0$xeUZ;+D`{MIMqU)=`E>62cy6Zn&OHVBk&l0JhO9)M<l~H-EB7hTsmPQ3_cf=7BLDICgS;nf'
    'd&o`_@!B%KuaW2Y_bfk<T$k(bSKcY-$+5_P{5q6ZBj54sKz=7*K%V3AjXZ7!eHQtS-v<)w@!j3z8a(In>$@kd#d9vrL*Hv2a!-)`'
    'kq7y8hx{jOLy-6Q_$3p_d;GqVBjk;8j$9>o8Ab=<xs+c|vUv|W7SE-8ypvnEr8~;ckWYEuAi2*wVmbLGo=Zizf5&Yl)ABfZn!H7R'
    'jC?F&TTi4z<(9~^B6f;AOOBRNOw19>%WIKeMeJSqnM8k|W)XWrE|cdVuZr01a=KhD5%;-2A-{_7IkvkI@~4P3ljqBmkWWSIeYsL@'
    'Rz>%e5qXk)N+K@YF=9d4Q{E$=m+g^fMeKNa5b~=C&qsHM%B$q#5^?1&5%xiIk3zl`vCENXMYL|#KR=1M(tQwlR>T&|Ky$hw@~en#'
    'AumRL<)4#mGMi47zazhj=y_L!bwYQF+#30lzdw1Id{-WU{3&AB$P1A_MQoCMT`rbf=jxva@~Md3CGVF%O0H{-*c!Rp47vb$R>a2R'
    '`B%i|%cXMPp7d1&juC4eqDM>iJM_;*PLOTiryY@JMHoN2ljZO74&+@Cds4oJd@I8JGT8|09PZxoBKb1%tB7rf{3^o!T<(j=vm#ng'
    '8nL+SEH9Kex1kuZDp`&^E5dy)?yJbJ{JxcEB9DsLC31`$D_6)L<%`I(BKE!9c@=GeJS$>-kze`uFK?F5%H<OEKNsg=ca1Q<bSvd-'
    '<X;i1m549hqQtuOBO^9I=J1><VrR?S<O~1)Z{%kY`v!Sg#D0-o#!$?2$3^T0Ia_WxfFh1O-anTDor%26UsrQ#va37>d0B+(K-_I*'
    'R&I?vETaB@5xYs^oQK{KTOzj_O%pP9Bkhg+EMlYN(=v>FEW-HFohf%mUKUaQ<@bR+7<pHO@uj;&24>J0@-V*+@Vv_Ji=H$pal4!w'
    'vHmiHMnHa@$xWKlfXvFPkcUOs55@ghHbFk-_XqN>h<zXtHxBmq*MnY)JS$@FNIVz5)W>x^hw{IVe9Onz8hWLiBmY&33x`K+wd_8a'
    'UMgS5`c40SyV9=mA^DrkBCm?r1@aR4pe)~q4#IP)h)t9ekcUNVq3kiAc0wNJ<BI%UZZ@9&ihL|$`wyhA;W<@={fXVZkx%*OjeN?l'
    'Z+VYwf&3}LIL~cAhK@tt6yd%M_gBg1OA+<2_xm6Dk>CHab1gkfZif6Q!Z^>pK;k^@d;Pwb=gB6>dwhJCw<GWI@l(Dc`y&sE@H__h'
    'CHa9|iRVTU+hZxc8TnF#eK6eiGw9WLUKFv9<ZrU9nl47(<o9cc9wZC0N{*E~Ab;}lN8TnMl}{kAig10zbj>I3W%3q@xbO)dcO=$J'
    '&x~-rl3O;6o+H0R9u;By=N9Dl$eaASlx>hNDUNf0!}`Ps_cgf@nUq~+A2~qwMxNy3qdW<DQH1Lp+_&W#^u>?Z$ky~R<Uxwt+~LT7'
    '{C<}YBF~Aa@0jAU1)2xk>*Xx@2=bqZ@}P+NiAC&md99o&cSHUY;r=FfwA>o`kKdp2GI_N`ADzYi{^ba{L=HoK<kzD_KkfG-?3e8x'
    'fqW=p56j&ObQ1C+#bfR_a--&SUs*0UK;Gozv@Dm$$~W;mDPn8oF|#S+wPpS}j;5E$q4IU~+mG0OeP~c#ChwE0(Dy51-IDZDc^UF7'
    'zn+m-`RkC!ETy%`uN0TLsDr!cf4$s)zx+|ImffrAYsk0!_x7ZS)4tbz=nj#CkY`2gZuw&Ae)}oHbK~3#<s0&R<X;i?rFK`#ZINF^'
    '>`vrW{`+Jr<WK%RBX5e>4-)fClc?<?Z$thRwHM?CHFP)RLs6T9=T!dRgK1p0leKsb73F;67UkKpAM&9n<1%-redzC{^TV4(?TlaO'
    '?Q#Y3peW-q7xCBDQTtGSBX=E7N8|ZY)Si)FNYumKgXJm6ccS)B`8oCxMy<L99V6M7Dr#xuFHt*HJ}1AG3FI^W`N&boYoh8)@1Kk8'
    'HGp1^{Kj9W{6h9G(2>Y<qV|MLBfs&_PfkOA6SdH6nv|zXth?Vg%0A0(Q{*F2n<}qD-VwDck#9uV-`ITv`9_rejNM)meToDAef6Z+'
    'cN_BW2hVk)R^F7JB&W*_kZ(loIN4vWE!E}XQR^|8ULc3dDe?;B9Z~iRPW$`lLC=zlk%vTW<F>S19*2A*YA+$*h_WxRyHqx*p$WM^'
    '@`|XPCK0~3kJ@153sIXS7s-wGp%){6h+2)rb5s}mRys!+7r9@`naCTWwm@P%x_f{;NDh_bkXJ-)zWiAJD!)Qr5w#&z6#aI)N3FBG'
    'NOnZt;GeVXfV?4U&BxIFB+tW&+CBs59mp4=?1$@)#RU*$-&=RD=JZf`vAkb?iTojId)CrU@<O>BeR=$Im`$tXK>025hbY&jx;WpU'
    'Pn3OY`$p|$c?I%<DA(t>-^mw{A4J)w(OoI~B0q?#|BnA2x$6x2th@owaa`mLK3?>sJ0eer^1K1}Q{)Lz#!c?F$OEF5k$sR4MAi4k'
    '$ID0Q3CIhgjE~&nFxm-uLX_tRxIasr_jyT_{a!EgpD(XQo)ERIYiLSN#eOdz-{k0t^cjghuETvil26L6$Qz<|ZCAQC;{T}n%S73y'
    '-^Du5kx_e0E|H(et>)A25`Fuxi`rzw|55f4935p`b5qo=k<;Y?dr<V-zuAAk{8+ZcbCswaBikb%h_a9V*eK%|_d&${QF~i%T%b*5'
    '2U&&ZDgM6XTk^+$|2gsnzuzU|8h2;8o9r%+mFR1FuiqzfsN4hjLX`1~`>^baKsIVKB>LY^in9N`d!MY4vyeAL?NzzSQi}eg5BvNo'
    '+svRx$??b=d_0kN;W<o{af^$CCf&V}C;00}J`iPpdG}t#{ZTz{@t^-by&LhrfBy1Z#Q%Q%%2jgTVRQ!afT+!rXX3ev-{0~_IT!23'
    'qI#|pweyh=_<W3fz`y^Abex<on<K7|vM;BbM_ljkLr#)8#P?D5*>va1UaM$7#QXmH<a=_?d^!s8zyG&<OMWd^V4YZ$>tEb25dTM6'
    '7ji$tbC0NP--71kcX;lhc*NcIJBt2o??l<}+&!5Stj&^N%3g@yqwGWAZil$suRFOD;_#?#h`3wvg!_zahIl(_G5NII8S!=0BC@Nz'
    'T5f_k+v6F@^KJcg$f|89_xD8YaXDAclOM}9a;v2jeIdW`@dR<Vk1y49dx`TDRz`KsmEZq}zoUA-;eRf#k%u7uj#?KvLZ%RRM{UdZ'
    '>CuR{qc%)-$McP-U5a?ye~%p5gFYcA;kkz57I&kzbX!?2ao)jNk2mDOh|gm>-zsL~@Vp{s@5rCzYI(p!I#f16d>-REWp~pd6#W^S'
    '#;lhdB5#*(%MB5a#~AOp6Xct6t-KKNdW`)R-8bYKdGdU^3~_tR%Er^z5U0oNOS#QJx{n-+I6cOGiaW;a&=!>YaQyd3#5p_r=O8g3'
    '>=IKSkC=^@56bxxeSLO|v5%qqvwQ_{dCU;_?ipkMYxi`l?}~Aqin|-)?wECu^YNS^X6;7P<K$fu_szaBJ4+sj=Ls>pR(^vxJ!ZEc'
    'PLHu~pu0kzinu+-K7nop;`Eq(fjB+JGOqg>o(sh63B>6!)-B!k@-+FRM8Cdh%vvG-j#(eX-!XeyHXlaOzb5TJ7x8z@K9%UhoQrWE'
    's*C;Q#hA^I=$~BauM6>Y%q}>b1`t=r?08u%k3(D?vjOrdIZfV-xH@K2<m>Vy8J|xNMm+7;pZo;zbBybB-35rFW43t}4a(W*-|5$b'
    '#6EDh2J59_cF;<CrF=yWL!9leOMWOfL!2G6O%Pwl>=MM)G4_RVzmteh+~egE#M}Npn$v}dt7F!-mM%aX9kbsh@<8_riTI<pe{b>^'
    'EZm6MzI|vnIY?eAA3%H^vqkb^#MLpoU%n|XL|h%S`{bMQe8km$|IVN|&g4wL-VsN~)ORvwdxdDV+!Jwh%sR`9<SlZc{7QC2oE_6X'
    'k{J7tUl>!pJ!U)gpf4eQ_VJ@Foq>A0|6Ih+F?(L_Ttj!49VGia#u#U~<0PI75BJxFxH-mivD`By*8N=_vlkFI$E+{n<Cr}wUy_UE'
    'uJdVoSwQ_f#yG<LR{nxG+V9JO6#ZyN$JmF~eMv4tJRP%b5jV%IpL|aKCi@_cj@dKvPQ=qOiz1GW*-3Jij18b85m);-Akh!oMW5EY'
    'eEvZk9AiILcOvTPF`f@~Z_L7od;N9Gx6!vS#{SZ7wM3lopwAO>IO1Brza-XsPxhZzP2WKr>+@Yt8k8gDA&6^z{E>^Wt|(^5Hl>ft'
    'Pvt_yx&Hek;(#Y&T2B<SM`a4}tzU=oUD<RP-3M{5-~V!~TqHN{L3foKVqKA6R}y_ppNVOIzmG%mUhJocas7kaM)r}251x<N5vYI1'
    '>@wLJaj}1%a<N2T=2v3ef9qZ^(N}a{jD5Xci?NTWJ0Eeb|NQav7>Vn2f#!2}l0<*dh5o*(=mV1RZp`*rNju34WEJYyG4}0p%Mt&^'
    'wB9GCb1wXIMZBwddP$7^G?)4Nk*~@;;?tPjhPc${6~vh_t-FbFJ+#a79Q;0%o6n%55P!zlXKH1P=Xbezi9QkE`+O)d@BSFGtr1uH'
    '=Omw%Hz2O`@lAdwBZxD79+R`=5_v7+&KT=t?hM44G43mE64yS2IQvj;5VsEyFUGCeL>iO*<WZ>i#%+(m^h9}`oGEWd-8XI{yVB{X'
    '@5XHe;=;I%mXAx!&s)aX&t>a4p9{L(<im&q<Myt68|zr&c5oFvLE^c{j{fHoeX@6o+f<43f_IK{K6W3K=<Bpg+%83&=RaSrkdqMi'
    '#qBNmq1*uRU)=6Q+!wdisKdss`)s-&;=8zACJ#q^7iXU)cZft^rv2lbS6%dDY7@5!a+*ZHg9GFChHSHxjzZiQx6kBna=#h$T-0&n'
    '_L}56{kXk^crb2<hUmreK*WD>`xoNBIQtvM<2FuCm#_W%&k+yC6&J?Y|H$15abetkl&yNu+Yuket#e!Y0^&peyyYgS!^Sz!y64Fi'
    'Sbrbq{8|~eEaJwv&Yg_g8Hf}8dX{tL_p%@2#5ns7xzEWp68%cM#O;vr6n%iY#chWw+DqPz_%CknN%m{^>sxM#_%3b<8AE+F&c1=}'
    'bMiNNE$Xas_6I!PuUEu#ah~(wqQA~baob*U-9%jRo4+o^XK{N{ZgDE@f;cVC^-1n@IY%y&$02Tu>paD{eJ-y=+~)6RDSZ_2o4<bf'
    'zI+#PT-=&g(@hZ1`R_yg7Po^Cm-)|=hafJCv(KhGOiqzUAzq7f-=RBMPD1<^w~czxg^1VudPUtc&i<BH#M#f%Jx*?mc+5Xf*#+@e'
    '+&UrtinE`Ld*CWM5OJ6PJo%~oO@?2muOi-xTkC=JB<!R0`&f2F92M6(g}7BBeu~>Ua;SVtzADc`JQcS)<QT+JarTdMZ$tgj?;E*N'
    'c5F_UqaGP&A4s=@JX$_1Z%6+ozaAv}IK^#Od7@l}b>MNU7)?)?J0U*v`%jLQT<_rH9qN&B_K|Zjk3JY@zc{z)QaT#(THKzIU(2!?'
    '6!YoixcW53?M#VvJ5&7rlm%Ii_|0FZ?1y;Gf4{^zztiLFPw(C+uR^>Q=X~paDAD(AX57Az-ytsZ`>_Wdf%wbEX^FmybK+)l7V3`v'
    'dJ$j6t*1OuUMsOr{H3@(A*Ug}irXi04C1V~)*txiD%ZSPx-jGHi{|2-pV#BukN3Lf&joRNM}8-HzFC}o(A=QxDK|#^<@c+^yjl}y'
    '{}XpD;<C7Hx01G%J>+otKH{=C`>ns@uSfPnToz~lGWR`s2-X$EEhXQ?dV)Cno45xxr_W+Ps;<vvaXV!+W!*7uHHhQlJa?wn|GhkL'
    '8;U;XU->*IJ0Onp`9@BYzsh-t>okA5=m)mazZcXIHJ`dXcPq~IH155K@BHT@o{QUjc?#k<pN|ly#d#j8J5_!q(U)M2=Et>hOCoMd'
    'aKD;62hZmd><i+ymt~0C672usavy0z`$!X7x16xC@-xJ33HJAMw?o{PV80J{wX8+lmayGcQN;UO`tP4lpT-BCurKA#<7t1??-D#O'
    'W&4CpNBu5gFUnh5Q0~u6=zOOH=f~X=b^_wAge{YgqYjs_Ph>O1T?vcIlVt?)SAu=0+)WU7`G3n966>(q_|KIK<@+C(zJP=c`-D!F'
    'A4v4UcNu>r?8F%q^Wq`?c~;X2sK+I2l02a&oglIPK9pd8DVP0e5;j~$5sxM8X!(Jhis$DE?psMFYzX451m{clExAl${&eq09OmDH'
    'd{f?sI4ogr$kljGp0MsU^jNtH@mRuIBOXiGM8shU+a1rn6RN)@Y`^*R-BQExE(tq#9KBP%CSO9lm9Umo6zk59OxV2={g%2X*k{Q_'
    'J>r;z&69hNp{)>4C2W9vNwS`nVE@CO32V`uR>?{7MTvQ{m)}Q-yAoC@JIm&XzY?~GEXq-GOT=Rd+a7UN!p@L$<qFv;MbQuWw1hn;'
    '`TRLyUm(6paQ<`i68(?PPFPNEhj=StX_-R2m9SIgO>#@bS$<#3*%Hs=F4lE2IAO=5KIT8KE!_a|R>GFZDX5S6eOE(c66^1-NZ6)`'
    'xBPX=<5B-g*fsJv#9;}$8}V0y`-(;;>`^&SzKi-+Li_pr^^d2E5q~8(Z@HMKMklNW@t0p8E$Fs;(BILgGr@BK++lKx?2bBDf_;G8'
    '%jGSI%M$jGyaaKX-#>`Q685dU2yvK?8}cZ`Sqbh_z1x4D`~~q;f_=B#NivK0$?qe{^LZ0o@9bh9>ZAnw`MBtZ@L)pmRD$cCA5Pdg'
    'a-4iuuKM@?NBopfU&{phA-G-SV7VvaC%@h$#-nL|T_Rpe*gqxDy-nE9vVb_r=N0*iY>T)l!Tvk$3wVy3u$6Ku;-`ddhPcUJKk8Qr'
    '?gwydQLpm*0P#}7ddUppBfmaM>&E8!>-vS(A|CSlcRoEI@sPj1@f3Xs79{L*xh>)x{~qKvh;#hDkxLNoBrLI#_L0{ip7Eb2yC9D7'
    '`v&!<1kVR_M<9Mlu#b)VA>x;Wg=;D1txx>F5yvF>Jm@nYuMx*2>>qNP9FBM<!T8!m{}~tSg}?IecUmcK@#}gzeMDY{IL7bKYI+so'
    '7{9*}ulV0beBys!K8!deVYB2r@<G&@61MR$%JVt>{*!AFw<Po&)9(YsD@j|3cqPg6=G=V{pCqlDd`Qkiy(wv32h)~_OOouP<PMVe'
    '%T9<-{O3!IE6tL&6!A%t@v)0}XX~U*lAp+5<dNg)%cwUcwXe#5pIm`>CCNT5?!9uuJ?I!rFiATH@k`R$A%016KVgd`*H5_@6e#}s'
    'o=NV9cU#LUIS0=dleSAOZ7<J8e3P_0<PL~qlHBj^z9=)OD<#?A>!74HpFy8Oe3G=!<#!VM)ZL|sN0PP`;tziv@&?2mNjnYkM$)d7'
    'M<KpQvVBC>|6N;(`#P7jIM(4M?E}OUN!z%FHj^jI&G39MX(9QR#JO3ON!ti<M$)FqA4==9tCBXZHC-Zyp{|p(De@@9BS{-7CrkA8'
    'ahu6r@<_xbNqbnnD|Z}EL$ZtPDKRf~O>$qJi++;bl3ZWvV&C|YNoy;Qkq02INh-ea-;erH(k?}Ole8D)TZm`;=MSL6@mw&;z9T)8'
    '_B!fE{_|>Sg~UF%lajXYY}!qt?_=*I=OOn(#3f0aAlJ$R(ElK*e(y<p4fP-Y+_4_c??1#He%;Fsh&PfpP@auCPSVbk*k66I-`B(F'
    '?T9;)%&*-&d(ah#Lz4Cl;*O-&yZL=3ai00*N%rk<@2sIX$M=e)ZIAdPX?^7x68ob^Bzdlhd%C<;J|rKOFUXq_w<PUbiFszEf3Nc?'
    '&ey%p??=QXNt=QFEJ^NfcK;!_MtqXAQziSYCD}jJ4I|!2vhRl56LCk9{eIo)h&z%zFVWpbULx_F_%6S$5r_EaEMs!Cd>{3nB+uQx'
    'H_5&kZnc~sk4IeMzgMCU=tRGc5sxI<N5&l~<J-`$OZn4-KCXR2C(B`oN0MAe@0QDu#QCk0lXeK=k)$0bYp|asseLSd|H;b{k0ceB'
    '`1?mZ;y>q6dN|^cr0s<`#K&`aAL0+6H{^kB=`DyylD0tpF6SdI@%yNTZixDh&llL2pR~OP)5GLM*%@^mzfKOP$0Ba=`(6GnH{OTt'
    'jyNW1Gv#k`9O9ZJ*H^mp5ZCy)hB(IG-$07}y$k*K%8T&;J88QjZb@1t>N0+v%jSq*l2(w@<twt)82Ucq8^8Y%*CcH@;u^nBv0uYK'
    '|JfAt&}T`zO%6uflC%`!m8A8N@5>udhe>LkSJI-0SCZ=Im9$xMrx_IU)^fkks;S9s5zizoEBnb?<tM1q`0EJKXJy%Dr8-TLeN}$)'
    '`BI*Uc*n16#5+m52JuZ&=QL@aTa&be{19~-zt0fwq-=B4V^S8CC&}iBb5fk=+|T4|h<j4@w%m9y4ano=qp}I&ofP{xxFh8ih<{RC'
    'm$+rh-a&kmvfy}%^ANU8Y5#c24#IP^lwBz=!E>>c)<>mmBI1~oZ99OzfH)>)3*}nL^Q%*~KjM^>T`qsY^RbleKAUzye3Ih%gzg!o'
    '=luJpIRCikqyCbz^AJ#^v|l=9zsj=_&!o67$9);`OUedSQ}js;r0guo{m?19TXNk~%94m@QdUG+Ib~-`#x*I<Q||W?^ObuB;+>S;'
    'Cg;j;5&xv@M#McS?x(Soog;IIV^W-d+NZ29;*}K7-E-UTLvb!f$CUOXr)(DDm6TN@zVPcseuwxX#rehUE1#8HA-+i21o>8}pXbpj'
    '+iWgvE3cEElnS-Sq}UhZxRlLC-6Uln%dHCZBh*n+wncL~8F7bS=e6`?IbC9Z%1Qpdu#Vra=h3uUZhRvxN8Kc){lF=kCRdlPkG?7P'
    '%W$#3{<IYL)1RK=yy9a1=%2D9WjX34DI1J9C8fHF{~XD4Zc{c~?vHrI|6F2U<M}CjShhy|;`f^zj5sD`Gvx-u=*5U*{Qm4gagN(1'
    'DO)44@9NT&?T0wVKX=40DO)8mzqoOEq`XvOU*i=i+Y@n#-#4-Y>M1FnzvSL4k61;Eh)+`XqZ~Az-i~@o%BIL}18EDyD=B*h^%K7j'
    'SJGPag-!81MRyOZ|4G>*6n<0c%bK!X5kL6-B3b81*$RpC;wSojf_TBdcf<!NdkXP^U*~xKlj45uDJhQUZW!~v-)HiD6gpDubKqVt'
    'dm#=;*^}~P%=><SW4=$>GKq2fnH0zEIsWhDCYaxS+>|RY&-=f}e4b)G%Y9r9$2{)W59VvXKIIj1vU~yacgo(Ci!qO<xc<T25c7D-'
    'wwK3X9{1}L^LNS~k#A%EPTAg=r~UhoHFA+`g7YE#bCVZg{!Zz92#w?J8o6nKV&B6@KJKDk;XfbsiIfeK7h!()?;rEKe{OOW=JAyM'
    'gn8Rv-wb*__CfmfBX`IAo3e3uPLi@p%)2Q&R^mLgU;XnKMmtLkW2^mj%as!6y1Kh!KKA#Ec{OeSz<imuZBZ{sTN3kR+MbaZU$;!#'
    '7ZUrkwoaRkr^_&3rftiCbQ+#xr0q52|7klJ4`S2yv<xHvPxCwv_gXnqj>Np0wzDvArrBR;&$N9gF|NAUAKNl*Psz(LkEYpg$PLM('
    '<W-nY)7BRAXxfgEuSx8WYLiyq{j|L&H^jW@pOfVIcxjG@ku=Y-a38{anYIToPo}jV#NQX@y|n#H{w`m~Jeam!G5@9Q2>BrL{j?26'
    'exJ4`rFH0)X<JZw4%I%*`^mi<^J1FkO1gJpUQF8~nE%o?SMD*8K9Bh@ZSyhTrEOE>)Be8XT@vTG9^*e3^Ok?_$dA(;r+TMtJIp(2'
    'yG1@P-;y_C9!j(S^J!`Op_J#Gp0;x^@1*Tp)a}!@4d$7&^_4NqD{1vVPg@rAi2q#7A8GE}bw^<S@XtX;F;AqeDaL=le&s`0_mH;0'
    'M4HAtkmmU0J|dS$p3jxGVe(N~Bj3Y(k>-At>(X2wJu0m}d464CKJcF-4?zCv*N4Qu^PBy3$z`$|=83fRl7}I$P1{6yG4k59ZH@dj'
    'ZR0SH_;o8+N%YTmyUDkZzoxDAY}!@+fI53x`>fJ7NY=>nG4G_gj^*Jr>tB=8b}#0aG|!KCEN$auJJi3^R>ZuLws|s-dBwj+<d<pt'
    'TDC(T>Gucbm9$l0K1tgpau)K)G|x+MvEOvAj~kdr(srsGAa9l<52rEABWW8YpO$@A(X%kG__!la!2FW7p7K+<-FVvUZaN)#q>noT'
    'X+OCP>ofhjtD>VM*4Zuc`$k?bG2Siq@d){%kC*a=0kjtLOxofF8be*&uRqK)X=_nS!}0{=m1*|FUFNS-9)<ZQ&GQjltaJLp-%pAL'
    'kzb~*CFY|v_fLGK@ostA+F<@kGY<S-<K2&GJ5utz9v=@e@1%LI$Lh4Lk-wqN?c)vdzO>HGN!!NA|1x$5>f9OI74uNWy2y*=_sH`y'
    'cHdxn0p_QSwa2`a;W^t|W_W&v+iE`D1M^bGR$^YtaQt&GkR6c6Wo&26M;Y4*^G=5Mp}Q&OpNzdITOhB?*w>hUGTg7*GGoPBI!9t%'
    '_P!bGC;MPt$yhDsm5fC&pJeO{8C^=BM4pzh4Ca@NeS+uU{_}cL^lyx0>{`q(8J_p<w!!?8u@htp`B%nzV}8kSzmyxsyprKK>EfLA'
    'e1_}2sxlns-1p^Wm`5_!6?NT=Js{tbwU}2jcGEzL^SzGD@Z511=Z<&J*e2gm^cy@nV-t`!Wo)7R6?sy|j%ZGQ!F-dkA2Hu#I6n2x'
    '*aFNe89NX2O2+P%I9KPijJ1>J%2}9i{QCHW&Xail*FR%p<jWH0a-ZqnBlcNjIKH{<<$1DzJSW5RuicfHm;B!$Z}ICx?uhv(W7}ii'
    '$yjsLRsH+IJd)vj?N;nVv2W)Z|M{yZ&VL^1|9(Eb8uLts<ByAdUoOsl9-XmfRdh?)N8;S)n=)43f}SkDlo8B78Jj7e#Qc-tI`P{x'
    'cDy_e^H0W-185(Kbpv-~?0T%P%kaGAasItyp2^t3auMd6jNOmEs2QH0?0zJ1*-p&ZzQ}Jf+NY4=Iq8%Ae#N|#;rZo{Wptik#zsoR'
    '{FAY%awPhhX6(qxl+Rr=Jcrc12YF7$R?9X$D9#O@ov{Zo4{3aQHpBjiC6VW3cwXl`A2%?6X#8<;Ztv^<dt|5a6zBCW$XG{tzQjJ1'
    'g+4yXM`RhEt7dpkuiG5+M#ip@KgvAj5&s@ab%}Q}dd}+CvwTbLiuomD%jF!*FMhqsKFDJ-JXgdmYfdX9_r3b}FL%Ivld&@-&ei=a'
    'V^3o~@#{<W$MaUdE>U0fe=ku#_%UO>Fn?rhV<dhVyHZY<$05J*e>aR?iFw7xE6ghyo&)Q)!hDjoAnJ!%tCm>jx>44ymOU_kWbG2n'
    '7g_Eja<QIy`>guvXDuuzNSsT$bJiY^izMRYU9w!Kw_DcM$T65Fvi26{g)GOjR$1#Zn_h_ZR$1$ac_M4iqP~~q_~uTP*azGuYp=>X'
    '_yEyfkuPH2$l5KKFS7O;>UUYIz<l9<Um~oCX00vy#Amq=BAM0sTUi^|gPw@zk6AmRhJK25O#c2RQm!M<+S3x}PP#Kuf6H>ba{J+V'
    'U)KJC`60`FEbegRA6dJhigMn_+Vye<<_Z6Ic%GN#xvuV(c%GNFQ)Cczvn=-&oRsDBnci8R*X}+h$6?;c8s2W-tZkm64`ZIlay^@i'
    '^&+Qd*<Z4M)>dFX$m-l>|J<r+8{{cjo{R3{Ji~!mo!^w@Ifm!^b%DMWS)NOHahB%`4$j(q%nw=Hw=JEAI#<?ykzJ6-WbGy7Em^x4'
    '{pzyZSK{KlzL8m;&v#vx=YEgM+AbLHvs{Poo+ojh_f1)@tG_+VbM)N47|*jjN6*E0a7UKspSYv&d@Rf7pZ8|%A^9=J@2qXrhgO_Q'
    'Pr>+|wSQv#&horE_cMuet{?W#8{>J_K9N{w;cg>)qmJeG5uRgZ?Op6M%krGL=~*ksc%J1sSMGE<1><<uK9DuYEBv~{_?_js&d=()'
    'b~%pw@5l3`tk(JZ=P$8NswQizB+gHBCt=*p^4#Hf{QkvwnzgU3G>&F%e4f58U&DBswX+bn`+X~Mu9-VX?umFkYn|kU66cwHmbG?>'
    '+p|2ktTt;upl+n=ba~cxuco_UeD&{N;+(PX{klP)tSr}cyVK>TXyD+l6XUG^9@K~Y{zIIe<@vboQtW@q*)+uCIh!+>Zi(?UXD1;Z'
    '&)FzB9nV*Cwn8pNy(nkd@pK8|@|@~LIZH^458LN>j;w2_ALV#%tb3h&2Ma^|=VBbr+2t5-bJnXlJp|)yPUku1>|%_kIom8n@p9Va'
    'c&@68^QR8X*&vLkIlEut{y!wg^GieiI^<p0C!Vv37*})lJ=U4#tP104j(wZm*Cp=zY|ef{y(h>0h?cXxWl|227i0YO*CD^gI*uIA'
    '?d<5Ua}~W4<8F@UFuC8$-7((!>ySl^um1Zb*6AIWvs3WgBB$pVISUu)*^+%sb3E6`#rZ0|bM_3z)tsG(@zcK-Ia7WvdtzM8*)<qf'
    'b6jWTrf1OOFuvyOdc@Z`+Z5wyj_c{%p%VQR&(GP>7)NvVs9YxB!?>DbpIvuTjH5XV%D3>`AZJ(A(1Q?{=j<`L8vBv`_aZL$-z#e{'
    '-sWt>`E)JD-JG=@Pp?Bfp0fuKKl|^II0xqr{~R%n=4_t40OM$m_w&RY&&`;WvoRPab9OVv#T?IHnv%1f5#Q$QOvJT0I|Jijj_3Ey'
    '%<&w)IXSLFem2K*FWu=_516w8>g_puTvj7a%~=TJncrvf7>s8*o=5jy&W6b;@&Jry{&VDevR8pF#<-TV^J?k6*mscQIU%)rpYDAa'
    'uX0@X?XJS}<{Zyk`!UD!)qcwHJhfkS|E$ijKXMbZrKR8F{wiNX{lL`k!`NSUL$hx&UK#sdx`&lM_l=EpE_W}CUuIq8ho$dhGt)V`'
    '#=f{)8T*cHZT3>>b#G(r_vXgrix|hu_8dsJD}8U<8SC~tn4N?Ag4tOZr;L5u%8dOacQKv|=ssF{zq=ayx9x8B5bEA$@5pCL<Hnw5'
    'UrY2=YH3z0(Wh-M<GI2v&rLEbNSw>Fx3PcQKF0pH?&<P0#Gz(4VVpGf`8mMs`qJgn)@+nqDA6bBAmcfu2b+D0aniJ2&MaF^5ibS&'
    '^XIWp7H9i+_Kk5Tu-&7b#P&Pff8>6~ZA|tAmlfj}`~E4jtr4dh&lUBwZ|?%Vf#EREo$_hpL-~WmemHlz+?<z_ZC1K0-Hj068lPji'
    'cpg&epI_<o=wQ}Co+%$Fz0bqUcB!T{sD~KOi9FKmNYv5IZk6fM`#Q?3FXCJO+%WzcpU?cmKR1lO#^;|Wn5{-##Ml?W#X3QEhQ#yG'
    '6U{o+(7o~e*gs#4&&GZMZts6vdOxT5_b4wwJZ$VA($DxD!A0Nw)BL`YcVhfD_RDfnZ#%=-*U5bhUyNBx#K->nOY`?R{&`_MH=dt)'
    'p0RJ4i#qW@zc2o6>GN^V#`tc$|J@N1>qIZm{c@4n3#DH-$nOh``^Nr2ml*pRx|?9UH*1S=-oIFk?`8*-K8In(b3uliT`qCmU#aW<'
    'D!=|P?(4DEHU7`#{ix6Qb&C1G*tgJqL#~n7_kOLZZ?ndM8;x}&7yDsvGK-Yn|INn!gYHT4A~{Q*So$1pG4?feQ8&KT>>i0eJ-3^k'
    'S9+UcjD5lWX?%|RPhJ0anXM>YFXPP)LOsT~Kjj|dIYamPxKX-%?>D=q^!^_(_Tg}G&e?;;emXAt$UNkqH`bw<9fG*scwXJ3W;+k0'
    'gCzC`PxbLg79{G*kNLPHcPM=>kNfvgdf(IhIz(J=HoEloo;21CpE7$|u11~4Y+333J>#DP;(h;biFJ^3%=VRdKH~n2dD7U2=sB~5'
    '#C`LE?wc2MzsxnBNBfHLx!OG453d^cU%Y1QqxCP-enJ1fO1JA9{(0effd6?F{YUBhUSvG)>m#!bO0R2)e=eo#^kct%us+Pcf7IWN'
    '{b5}6hx*#=DcQYrVSa121?EqGU!~7|g^TCK{&^wZ_wS?h@_**CugSj{`^^2K&(&qTZ}zX!=lPrQIm7QhZla!I_I>Gft~K^?awj7X'
    'Fg|~1lIQaW7yTzU%yT{IMtSzb*)(q><Q;M>=GVOaAdf2DSIzS5BjMhPJR#3<Wy?J4%v<Me5$4@I`*ph*U$)O%k1CqLJez0TdB?nU'
    'E8Qo}^L8TU+q_*O(O0r8Z@n?k=6NpO?s<DdVtr_fJmd5|^0qhXHhG>y?H-PKHP3o<>%3hoJ7M0;+bHA_d7dxrE|s5SzRa`Ed{EwA'
    '!hGqUgWMDIWS-YaFwcHUF8Zv5@*GFqO3asej+^fLm>2W*2nri{`&MGzYbMV=N$y0<e|esJ@1kE%K5si<p37T5%yW5r7SEIO?336r'
    '&*x<>uES1wUWc9Y+{bsQzdy`(dG;xB_b*-dhv#i8)OGUKRieJ!J#QDv_Lv9r9M|0OrSGLj-mXENCvRtBUd-F$68$8O&-1!GA<yfw'
    'r>?(Ve*Izo%X2?SpS(RL$Ch5!sd?6w`{sGRXTLnhHTQDNZ@TW>cjaQtXL<Vyc}d=Ot)_V1aaP`TEWNLD@-_+cQl5PUFUs5f5`Ang'
    '_Ul1@F7do$P~LvWyp^{DO4r+vyq$;n#y<zizM*;hSfbunowpA#zxd}+`s3^K>?3ePp67hssO!W%PriuxA<upRx8=FN`1U;4>y7cx'
    'Zy2pD-PU*It$^pndD{r{L!Rp{@5!_O&3$=0R^qwq{dv0!>zMueD7{YiTFei5o-g-E-uA=z@7FQLd;h*M&ga>uYFge#B9F=2J@OyO'
    'XZ+{Nc^K#OTvzvW-hRUPowwx}zw_LO|D6APS&n*6-mb#<owo{%-+tYfE{7NMoaf!6OV`88c|PZS)yJ9Aub-c{Z{!Z8*ZHQ#lbXEk'
    'i+WF<=c6vp^IWI5^EL?iQr>Qm^D(ab{eW>jZ-=2Sp69tNOWo4v_IciV%3CGRxyrNOOKslXLw=OU<BWkT^7bpn^}Oxglj8IIF3;ze'
    '?!m~L@>VSUZx`nq|CVQ8mf!R2bGBiD{Z=+E*lDs4>NW*C4C8Tu>yKTm8*EmvCy@UXtOdr?f;}nmz3f)7?=emmZ1c9XrQ8+umxApn'
    'Ll{2`Jol?r!3xMj3f4|uk8!kMZ844(_&k5V0@pF_UodRnZ(Fe07%vO9NaFcV$bT;Kg#y>v#R_&e#>Il&i+rKL^I38Q)>mEh?I{-Q'
    'WZ4nppTE!2?{8P&y1<SFejn~x82<|Pkz9$mzrg3?F8Y*qE%1IkyuiKy-3r$J-y$C<*awLF3+&s`qoDmN1$z+je}VO&UIq5M>07XC'
    'P(LZyQy7;D_J%~?jWY^d2REQ#d!r6rux5z23+z+lqHcasf&DTD73^h<I|X~GbX^Q7urJ1?1>3ar{ajXHKMXf04?)~qup;8*g7wGx'
    'm;%o)zOG<-)SU}_UNX91`(xbk_a#q5oLjIX5a$-`S~&~jP{BS$d|I&WP$wzqTt;0l;|hG<Hom}pjQ16+3ialK^_0~ZhYH4nEDBbE'
    '@yOpN#v#965T_Oxmp$s&CB~rw`!qaWu!k_t6zn-USK@it(*>S0GrPe0=Q9PaGn?b@7xfjtpD^C|`@?usuznKz;^!5(zs^PfgjWkT'
    '1>;MBeaROT>^_Vy1@_-q<nOO^9luque_(tm*kh&F^KQYOmFOq;Uct5)K)=Lz<JT?5n*!@TAN%{mcvG;QQ9t(Y3H9TG^_4gv_49%q'
    'g>k1~lO_5BeOX{Vw6?%?Gwx!<p#}R!qL2001=|Sg6$^&1>s$Xk5O)@=3*ycK_kFG^SR2HJMLQAWPLcKOO^eK<H!Jda#+F6yAKSWU'
    'JB+6-5bqUrzFLua<4#5P&2aM=kBT-6b>E_`L0zP1ImBs2>xJ>9X!oGLQM4^Ez7(xePC$L5$Ub<76zxYmKl8uWlj42~6}gWwTx6aa'
    'Dcac>Uy3}J)W!bYWYIoEowvy6;hCa+gXd^Pp7UBPvLA3ok>{wnI8V1j(K4l9b3~DK<fDrA8RDLzrI7dg>qEX@v~w{o6zwi~72=qp'
    '-GOnUXrCi)DOx$=lcE(dffRY}{h*>P!hP?b7vhW}_jO)Zv?YiqiuMum)gt=<-%zxZaUU1$ABZE0I-j-3I_sT9dmGRBi@MK>+!r~y'
    '$o|Yzi(E%D!(T7*xT1~3d|u?aL++Cj{VJX=+E%6a`%KZc#C=xe`Q0xRts3)ok^6dIE^=St>qRRd-}289_f64m#eGt=A-GTcdyuP9'
    'mn_<Ln2(FL4epPkwZ{EXv}Eb}__WCLH$E@gD2eN0xjvT_djCHc?M2ihi#%`k_oB|JudoAAN31Y}pPN>2zvbo?dY)Xt^*YTf_;Yry'
    'u=^$UzwA}P^DXzUVBeZH6<l9dUSXBU2P$+vcm?<2$0}?QuDc5MK}lEWJnjn1VA!hQIN7d(`+wV4*hRSBDs;Yfh0Vu&R$(_FuCL(!'
    '#3TIQBd)IC`I@Iy*kh>sRM?xizA9M%9#Fx3d*@Vezwdb!wgu`g6}A`V552F;D|GI01^Xopt>Aj&D=I96dQ64&K>ek{u9459eo~?H'
    'W-GXFWL5>QyV?FZ<GQHOy6+0>hWxt1E<}7*!F?AWRoEu@ek-hi@vOowl?RsU_+M9WKip3h?902RLg#2!a9_oym9`pjP$k!4>{w}2'
    'kT+KH`Cf}kTaNgrlKZ>%tYlrKRi!<J=kk^IwB-4NmE1QKt+ea${Z;b3>13r%$M;uhOHjY8<U0FYrRtKEwi~|JO1__pO1mB3YbDRo'
    '?o?^-ARnu=V-asuGOswk(iR|3s^s}5eJbsAxfPzfR9Y44ag}yF#)(RvH+fN|9gTdY(o*=ID!Cuw%1XNh^M57Rd5@~(d5Skw+9#OD'
    'EA3}IKdw|hQOW+1_xkI?JYA`CyeiqJ$^8n?c`NNfe9x7(1=inG+R3=zE4gpurApS@|5eGl`1_Sy*Y4t6$ge7`Rq1{FP-&fTe^xT@'
    'cTx9RTdDJVDs3aoC+)ayd%Jcz&!!!pE3|CK{UQ6c<N0y<cC7n#Y^QTT+A*#?rk(9w`dm(Kr}HY>aX-OD?RbvhpmwZF4{2w=;(2~M'
    '){U-d$8)VlwX-ljw{~^~;-Gdq522lXfbp;$>lKUJ*~z$m+i`z(Z9C@U&DwLFXRG#H-<)r6uOq-|Z!1gV+-2?A7ja&D^&4%^b%pcW'
    '8y+7nY;Uh2Uun;H{loT*|CY38ACgboGfrOH-a2Ex?!fbZf*tHZTyGt0TU=iq>~7SNJJ@#^4?5TbxIQ{?ox`jSJU?N62cDPsQ3uYq'
    'Uv^-e+oX#7+Bc};`9ud-*>M=(s`x#$uj2E>j#XSgc2X7BuTH44D{=o<@x1h<Rkje%!K<tf#@~+C8+lDf+XHo>j<yl<kB;gu(~-|-'
    'Zs=%1T%R3zuH#1??IFCrj)rh{<4)|;uzM$+i`vOnVEpUEeEZE#R)Km(XB&c_+nM_ehIVFM^Ty8n{_pB+4<TOa%<~3*>ukMo{Tynm'
    'O6w@DJk(x7{CcQef$Oo0?TP*aT^LVRbkX{TF6`qLILx-d_kNhI#CnRu7(eXLm37hTt~RoC{d|5n^Whziv@Q98H~GJ6+5hqP|3Cld'
    '|7`eipsay^Z`peOJ(R8I*GX9;{XQG&=al`)pHudKY<wtNM?d#}<Iw-+ug3I!l{K>K_Ro$}Wq<K=E?ZCUpVsU6bN`>~_xSX``RMQU'
    'y_Ws|#)a1P^n1%1+4#}W*L_|8zSiq#TyLnjruE+}Pj0O7QDgi4f46bJ^*VZ=f49%^uhw@OTb<{>y$@P9@cS&Q=kctpo?d@_*Kf-j'
    '>3CRHNB^$A^2)|CFP1gX{ky)#7iH_&xcGN@-qhHhE0i_x&n;WW<NCUqU+Ox~YwXYI{_N-5*z$&k%1_JxSI?@KdPQA77x=r^D_j4?'
    '&+pIP&;KcZE^nasyT0Yyb(N3(UE;6C7T2|I;P3PQ+VhORT5qne_^`3e8)fS_uKu&}epw?O7yoW`+`1mW>T6yptLNX}P<ie8^4#S='
    '{k`&f{$3jUJXqGquHX88AFb=?`)@4kmj2u4EM<T2?={x-#%1g1@BODZtf9uuhF)h-_6PsFv3xHLJ%2Qm<^SdPQ{Q=MUC)1I^?aTF'
    'UGvaC`+b)+viDooK;u<odyZJ%NUqDex?lci+|#;&UVm8~zrXdRPWj*dp4RnzAFeOsP-EZE^+%sG{MCA4V_(<OQ0uc>H<Ih4^`HFS'
    '|8DDg*L9rm|N8so4fOlV>Ui95Z0l<3>UluxdKwQJ+y1uJ4g9$`^gPm7*FCnbqj8|2>Zo-!-<JKw`?Idcx$=4%FYBvLSKoEk*7Y<l'
    'm(|fYTvy}R`nuk@uJ$dit9od81K&4|C9e6ib=QWz&;M$CTGqgy+h48Y{I{>Cypeq#>-#?8)(vz$*Vn)Mt8vkvjfd-dzuLOq2e7VQ'
    '&wu*4tsCgR{j>32L(L!Sdp-8Q{hsS8F8;HhPwP7Ryz6^?*I%t$t*?C$)>RzeP|vOYY#dwH>krqLaiy`<4O{=g>u`Nvzp%btAM5-3'
    '`KxhleaDln|KxSl(CaMgdL3O^JzbA=J-`3kbOT-YWpz}SD*Kb;=DM1f*SCH}t^elZUSnUkTVMOgS~t?~p{#*lXI<6J{%kz4uJ$YZ'
    '(Yo3Ce*f3iezNs79&f1EzpmG%HPm{{@<#Uk)>Yq$KRS<;t>f#ruGc-()%wHo2D)$7_i>}H;-|*eN4K%9Z~D9JoB6x<yQ%LyyY+uL'
    'Pc*i5d5!g4p@ymp*7f)EN9XtYisu@7-%Z&%zMdMY-)()>HUDbA;JVt^*wFQ`vIe?7>#Gk%>pHqF8_T(2^*xU@_Wf^Vjr6)+U-}#W'
    'UDjQdt>f>xvGsfXPx)kB)y4nQK864Gb1bi?>#6KdzORPvFZD;)HLt7u@4x*$9sbL4qV<1Shi@$TcVpQ{`&Z-UKN?Row*9RQ9k0|^'
    'KkT~7*Xn8<TG#7%|Li`LhCV;#Kixlnwtrh=>BIDAKbLj={Jo*}f7I1_{B?C+Uw!2#WexQ6*LA$zP|rW>yANzx1I;gW^?n*lU$w^e'
    'T)VM8N2}|3wz1VS${J{VYpij^x?b1WSU#`y{oI7IdYWJU=+CL^^=I|fAFsTQpU2eK^;_3{tsC3AkFxdb{{6e0cUa&1I2y}5ysp-3'
    'H1v4iQ0spG>U!`0D}5`{|BpI)ebukmmvbNMYd>OruOq1IbE6xoAKUtJ{#sch`}+;OPqm@WFK8@vfOS=GDX*vbzP{Fh|J8G9>+5yY'
    '^*mnJ{rJ}R^9Rc6X?$<&=Vvvxab<nUPycRx?ANz-TaB$h{QuY9m0Vd2gRnMK00pG~>ZXEuKe0iG<>brEk5>#BN$UBWulPN0-u$R>'
    'z2(!&;tln}i98?Y7e&s?*L?c(WBnh}Ig5U8HS)c3yY7#OJ<P`4sNyA9xLh`l-kaCR+t16cKYoJ7r(%b^d82OgMOi$pCbs{)^15og'
    'GAzCy^|-4mpKH~6OI2J8OXnb}E~kq=8ItyUSG{I0|NAu0!SesT>uBw=A8NX#w|XTko?r_)=U#eX-u$d8Jm+2b(5v}{=DdFDI0_W8'
    'hiY*Sg3l?t&P4V6KEdbs^m`!N4;8%qwD|q2pHY=R!OMP`m|gPH*ZyyO+4;n1zaskgZ{Ppk`roSfGZvl+m-CX1n_}Y*k#sJjdEZoc'
    'va;$y*t)swdcP|Cu&Vc=m%WJMkznb-c;~IyI<?VxX(QPcwK@@q_d}KMlI8!Y)NOe4C8^@8qH!JOG%uEX4yWM?z5PiqzcY%5pB=wM'
    '^SW27V^GWYtLhw|=DXG3U)cAyiQCO8I5-sTclCMz6knGpy>^hlr@pVf^Y3an_bK&7UUk0e_dol+!^HOUwi@}H>h*+P`dU-?3$pw>'
    'Hvb=ruk*BeE)~4oDXx~~Z+M-fEZn|{>?<$)^AtV0>iW_s(oePXtL}fO*0Fl?x3hT2qwc3@9Ax&p^DRGPwr-JH9Qt;@d+}CAz3WHU'
    'BdOx?)Z>h=xKJeZ>vkPX%q}bsNsNCG&F`*~XNU8As_6rE$9YfX>-F*zqW#=#9earGAGS_T*1k2Tes`@iI9>NAX}$2nzIgK^uyH5W'
    '<bLS>epSU!Qn$Ca`3xklryB0%G+v0}8MNZ|C;Of~y+17I{Hp05R>`NB^WU>|9o6&mDs_obzi(pw$*vEMj?aJTba>^pA$EVL*C~QD'
    'jw<?xEZ%|DYwP8oEPty;{s2waCCdIr=kvVR!$kI(m!9z3zl-AU&aS_if~PUkcUW<bCEMdHo@kZ)Z#3`RR6oU<jhn?|Syd;dD$Y#x'
    '9YDRFkA(-Q9<Qj>y{Yh*J*0mA+7DjuNz?J9Dm-Y_am~|pjk@3`(R>|nXiv9(tLFG_{i^79ZVT=|TlY!@UmAtiSFs!F{CO;XTNQr{'
    '!S+QBKUIz24<x%Wl{aJYWZHSqUAI~Jh^qX4(RR(6oRcUXv@AcbdR*G|y%cNbuFe(2>?VTka1`E2RacMoZkL5GSJ4k+>8N<|KV`oU'
    'qq+T6*EK+q?@Z+jUL3z>+!uu#Qj0^-^jvl0V^VvUtTr!dyu4ri1~{!(w>USezbZV=D!fjrc`o($DFpYw8y>bg-waz9q*@%fdQ-LY'
    ';MMTPQ{(*Ubt7K*^V52@D(`-*eS4~}J>5=w^C+O{{;JMDf@XHO>i?_9Q{MNZD*m%8f7QkzHT#X72g&o7o%i;}V|3x!>r#gv<ws0='
    'cdX*)RpWDd`)-J)c4n%7f}L;bxG-#gZoIVX>Y3;5f@{0gUCHWy^?Jf7dAVJO+WXbpFSDZiL^ThrS`PrxerDmlHV)ymHhjKR>Y*{z'
    'K2_IaUcAV*mGkJ>`E4DKEbq{+!?v5B+IUB^zi2)#4Bv0tZoBQa+pb@-<K1=JdER#0ZTGy-ZvOxX&-=y'
)


def _decode_atrh():
    raw = zlib.decompress(base64.b85decode(_ATRH_B85))
    n = _ATRH_NDISTINCT
    vals = np.frombuffer(raw[:8 * n], dtype=np.float64).copy()
    counts = np.frombuffer(raw[8 * n:8 * n + 8 * n],
                           dtype=np.int64).copy()
    return vals, counts, np.concatenate(([0],
                                          np.cumsum(counts)))


_ATRH_VALS, _ATRH_COUNTS, _ATRH_CUM = _decode_atrh()
BASE_CELLS = frozenset(CELL_WIN)


def _pip_of(sym):
    return 0.01 if "JPY" in sym else 0.0001


def _iso_week(ts):
    iso = _dt.datetime.utcfromtimestamp(int(ts)).isocalendar()
    return (iso[0], iso[1])


def _maxdd(seq):
    if not len(seq):
        return 0.0
    cum = np.cumsum(np.asarray(seq, dtype=np.float64))
    peak = np.maximum.accumulate(
        np.concatenate(([0.0], cum)))[:-1]
    return float(np.max(peak - cum))


def _tercile(atrH):
    """Midrank percentile of atrH in the shipped DISC
    reference multiset -> tercile 0/1/2 (-1 if undefined)."""
    if not (atrH > 0):
        return -1
    j = int(np.searchsorted(_ATRH_VALS, atrH, side="left"))
    lo = int(_ATRH_CUM[j])
    eq = int(_ATRH_COUNTS[j]) if j < len(_ATRH_VALS) \
        and _ATRH_VALS[j] == atrH else 0
    p = (lo + 0.5 * eq) / _ATRH_TOTAL
    return 0 if p < 1.0 / 3.0 else (1 if p < 2.0 / 3.0 else 2)


def _atr14(h, l, c, idx):
    """Mean true range over bars idx-13..idx (prev closes
    idx-14..idx-1), in price units; None if unavailable."""
    if idx < 14:
        return None
    hh = h[idx - 13:idx + 1]
    ll = l[idx - 13:idx + 1]
    pc = c[idx - 14:idx]
    tr = np.maximum(hh - ll, np.maximum(np.abs(hh - pc),
                                        np.abs(ll - pc)))
    v = float(tr.mean())
    return v if v > 0 else None


def _trade_outcome(bars, sym, entry_s, side, dist_price,
                   mult, atr_pips):
    """(exit_epoch, net25) for one candidate from the
    symbol's M15 bar arrays (ts, o, h, l, c); exit/net are
    None while the trade is unresolved in the available
    bars and the 48h cap bar is not yet present."""
    ts, _o, h, l, c = bars
    idx = int(np.searchsorted(ts, entry_s - 900))
    if idx >= len(ts) or ts[idx] != entry_s - 900:
        return None, None
    ph = h[idx + 1:idx + 1 + MAXHOLD_BARS]
    pl = l[idx + 1:idx + 1 + MAXHOLD_BARS]
    fwd = ts[idx + 1:idx + 1 + MAXHOLD_BARS]
    entry = float(c[idx])
    pip = _pip_of(sym)
    if len(ph) >= MAXHOLD_BARS:
        # full path available: exact filed replay
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
            gross = side * (float(c[idx + MAXHOLD_BARS])
                            - entry) / pip
            return entry_s + MAX_HOLD * 3600, gross - COST_PIPS
        if isl <= itp:
            return int(fwd[isl]) + 900, -mult * atr_pips \
                - COST_PIPS
        return int(fwd[itp]) + 900, mult * atr_pips - COST_PIPS
    # partial path (live): resolve only on an actual hit
    if side > 0:
        sl_hit = pl <= entry - dist_price
        tp_hit = ph >= entry + dist_price
    else:
        sl_hit = ph >= entry + dist_price
        tp_hit = pl <= entry - dist_price
    isl = int(np.argmax(sl_hit)) if sl_hit.any() else 10 ** 9
    itp = int(np.argmax(tp_hit)) if tp_hit.any() else 10 ** 9
    if isl == 10 ** 9 and itp == 10 ** 9:
        return None, None
    if isl <= itp:
        return int(fwd[isl]) + 900, -mult * atr_pips - COST_PIPS
    return int(fwd[itp]) + 900, mult * atr_pips - COST_PIPS


def _slot_rows(T, m15_bars, h1_bars):
    """Candidate rows for one slot, in canonical order
    (symbol index, side desc, distance asc) -- the mined
    universe's row order restricted to the slot. Each row:
    sym, side, mult, cond_key (-1 when the tercile is
    undefined), entry_px, atr (pips), exit, net (exit/net
    None while unresolved in the available bars)."""
    rows = []
    hour = (T % 86400) // 3600
    for sym in SYMBOLS:
        bars = m15_bars.get(sym)
        if bars is None:
            continue
        ts, _o, h, l, c = bars
        idx = int(np.searchsorted(ts, T - 900))
        if idx >= len(ts) or ts[idx] != T - 900 or idx < 14:
            continue
        pip = _pip_of(sym)
        atr_price = _atr14(h, l, c, idx)
        if atr_price is None:
            continue
        atr = float(atr_price / pip)
        entry_px = float(c[idx])
        # H1 ATR14 -> tercile (last H1 bar starting at or
        # before T-3600, 14-bar true-range mean)
        terc = -1
        hb = h1_bars.get(sym)
        if hb is not None:
            tsh, _oh, hh1, lh1, ch = hb
            ih = int(np.searchsorted(tsh, T - 3600,
                                     side="right")) - 1
            if ih >= 14:
                atrH_price = _atr14(hh1, lh1, ch, ih)
                if atrH_price is not None:
                    terc = _tercile(float(atrH_price / pip))
        sidx = SYM_IDX[sym]
        for side in (1, -1):
            side01 = 0 if side > 0 else 1
            for mi, m in enumerate(MULTS):
                dist = m * atr * pip
                xp, net = _trade_outcome(
                    bars, sym, T, side, dist, m, atr)
                ukey = ((sidx * 24 + hour) * 2 + side01) * 6 \
                    + mi
                ckey = ukey * 3 + terc if terc >= 0 else -1
                rows.append({
                    "sym": sym, "side": side, "mult": m,
                    "cond_key": int(ckey), "entry_px": entry_px,
                    "atr": atr, "exit": xp, "net": net,
                    "entry_s": int(T)})
    return rows


class FillState:
    """The M5R97A04 sequential fill (the live-rule form of
    the filed fill_adm97 with stat OBS-DD, level MG,
    pool STAB). Slots are processed in chronological
    order; the era segment (disc = slot year <= 2023)
    resets the running week ledger and kept-net sequence;
    the per-symbol blocking ledger never resets. A kept
    pick whose exit is not yet resolvable from the
    available bars blocks its symbol until resolved
    (resolve_pending) -- in the post-2023 segment the
    week ledger and sequence feed no decision (the WDIV
    overlap is identically zero there and the admission
    gate is DISC-segment only), exactly as filed."""

    def __init__(self):
        self.max_exit = {}
        self.run_net = {}
        self.seq = []
        self.era = None
        self.picks = []
        self.ev = {e: {"slots_total": 0, "filled": 0,
                       "unfilled_no_rows": 0,
                       "unfilled_no_eligible": 0,
                       "unfilled_all_blocked": 0,
                       "pick1_secondbest": 0,
                       "second_picks": 0,
                       "second_possible": 0,
                       "second_admitted": 0,
                       "second_rejected": 0}
                   for e in ("disc", "audit")}

    # -- persistence -------------------------------------------------
    def to_dict(self):
        return {
            "era": self.era,
            "max_exit": {k: ("inf" if v == float("inf")
                             else v)
                         for k, v in self.max_exit.items()},
            "run_net": {f"{w[0]},{w[1]}": v
                        for w, v in self.run_net.items()},
            "seq": list(self.seq),
            "picks": self.picks}

    def from_dict(self, d):
        self.era = d.get("era")
        self.max_exit = {k: (float("inf") if v == "inf"
                             else int(v))
                         for k, v in d.get("max_exit",
                                           {}).items()}
        self.run_net = {}
        for k, v in d.get("run_net", {}).items():
            y, w = k.split(",")
            self.run_net[(int(y), int(w))] = float(v)
        self.seq = [float(x) for x in d.get("seq", [])]
        self.picks = d.get("picks", [])

    # -- core ----------------------------------------------------------
    def _order(self, rows, idxs):
        losing = {w for w, v in self.run_net.items() if v < 0}

        def key(p):
            ck = rows[p]["cond_key"]
            ov = len(LOSE_WEEKS.get(ck, ()) & losing)
            return (ov, -CELL_WIN[ck], -CELL_EXP[ck], p)
        return sorted(idxs, key=key)

    def _record(self, row, ts):
        pick = {"sym": row["sym"], "entry_s": int(ts),
                "side": int(row["side"]),
                "mult": float(row["mult"]),
                "entry_px": float(row["entry_px"]),
                "atr": float(row["atr"]),
                "week": list(_iso_week(ts)), "era": self.era,
                "exit": row["exit"], "net": row["net"]}
        self.picks.append(pick)
        if row["exit"] is None:
            self.max_exit[row["sym"]] = float("inf")
        else:
            self.max_exit[row["sym"]] = max(
                self.max_exit.get(row["sym"], -1),
                int(row["exit"]))
            w = _iso_week(ts)
            self.run_net[w] = self.run_net.get(w, 0.0) \
                + float(row["net"])
            self.seq.append(float(row["net"]))
        return pick

    def resolve_pending(self, m15_bars):
        """Recompute unresolved picks from the bars now
        available; on resolution the pick's true exit
        replaces the blocking placeholder and its net
        joins the segment aggregates (in the post-2023
        segment those aggregates feed no decision)."""
        for pick in self.picks:
            if pick["exit"] is not None:
                continue
            bars = m15_bars.get(pick["sym"])
            if bars is None:
                continue
            dist = pick["mult"] * pick["atr"] \
                * _pip_of(pick["sym"])
            xp, net = _trade_outcome(
                bars, pick["sym"], pick["entry_s"],
                pick["side"], dist, pick["mult"], pick["atr"])
            if xp is None:
                continue
            pick["exit"] = int(xp)
            pick["net"] = float(net)
            ex = [p["exit"] if p["exit"] is not None
                  else float("inf")
                  for p in self.picks
                  if p["sym"] == pick["sym"]]
            self.max_exit[pick["sym"]] = max(ex)
            if pick["era"] == self.era:
                w = tuple(pick["week"])
                self.run_net[w] = self.run_net.get(w, 0.0) \
                    + float(net)
                self.seq.append(float(net))

    def process_slot(self, ts, era, rows):
        """rows: the slot's candidate rows in canonical
        order (see _slot_rows). Returns picked positions."""
        if era != self.era:
            self.run_net = {}
            self.seq = []
            self.era = era
        e = self.ev[era]
        e["slots_total"] += 1
        if not rows:
            e["unfilled_no_rows"] += 1
            return []
        cand = [p for p, r in enumerate(rows)
                if r["cond_key"] in BASE_CELLS]
        if not cand:
            e["unfilled_no_eligible"] += 1
            return []
        pick = None
        for r, p in enumerate(self._order(rows, cand),
                              start=1):
            if self.max_exit.get(rows[p]["sym"], -1) > ts:
                continue
            pick = p
            if r > 1:
                e["pick1_secondbest"] += 1
            break
        if pick is None:
            e["unfilled_all_blocked"] += 1
            return []
        e["filled"] += 1
        pr = rows[pick]
        self._record(pr, ts)
        cand2 = [p for p, r in enumerate(rows)
                 if r["cond_key"] in STAB1_CELLS
                 and p != pick
                 and r["sym"] != pr["sym"]
                 and self.max_exit.get(r["sym"], -1) <= ts]
        if not cand2:
            return [pick]
        e["second_possible"] += 1
        p2 = self._order(rows, cand2)[0]
        if era != "disc":
            admit = True
        else:
            x = rows[p2]["net"]
            admit = x is not None and x >= MG_MARGIN and \
                (_maxdd(self.seq + [x])
                 <= _maxdd(self.seq) + 1e-9)
        if not admit:
            e["second_rejected"] += 1
            return [pick]
        e["second_picks"] += 1
        e["second_admitted"] += 1
        self._record(rows[p2], ts)
        return [pick, p2]


def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


def _bars_from_frame(df):
    """App frame (DataFrame with a time column and OHLC)
    -> (ts, o, h, l, c) numpy arrays sorted by time."""
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
    return (ts[order], o[order], h[order], l[order], c[order])


class _Form:
    """The slot stream settled through the M5R97A04 fill.
    Persisted: the fill state (blocking ledger, segment
    aggregates, picks), the delivered ledger and the
    processed checks."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.fill = FillState()
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
                for k in ("check", "entry_time", "exit_time",
                          "entry_candle"):
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
             open_symbols=()):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r["check"]) == chk]
        T = int(chk.timestamp())
        T -= T % 3600  # entries fire at H:00 UTC; the H:30
        # stamp is the evaluation label
        if m15_frames is None:
            m15_frames = fetch_cycle67r_m15_frames()
        m15_bars = {}
        for sym in SYMBOLS:
            b = _bars_from_frame(
                m15_frames.get(sym) if m15_frames else None)
            if b is not None:
                m15_bars[sym] = b
        h1_bars = {}
        for sym in SYMBOLS:
            b = _bars_from_frame(
                frames.get(sym) if frames else None)
            if b is not None:
                h1_bars[sym] = b
        self.fill.resolve_pending(m15_bars)
        era = "disc" if _dt.datetime.utcfromtimestamp(
            T).year <= 2023 else "audit"
        rows = _slot_rows(T, m15_bars, h1_bars)
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
                  "tp_pips": float(r["mult"] * r["atr"]),
                  "sl_pips": float(r["mult"] * r["atr"]),
                  "exit_time": entry_candle
                  + pd.Timedelta(hours=MAX_HOLD),
                  "mult": float(r["mult"]),
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


def is_cycle67r_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE67R_CHECK_HOURS and t.minute == 30


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    form = _state()
    out = form.step(frames, check_time_utc, m15_frames,
                    open_symbols)
    if isinstance(out, pd.DataFrame):
        return out
    if not out:
        return pd.DataFrame()
    return pd.DataFrame(out)


def walk_ledger():
    """The delivered cycle67r stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle67r_m15_frames(state=None):
    from core.cycle89_best import fetch_cycle89_m15_frames
    return fetch_cycle89_m15_frames()


def evaluate_cycle67r_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle67r_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
