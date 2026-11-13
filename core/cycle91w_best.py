"""Cycle R494GAPW -- September: design
R494-GAPW of ROUND 4 CAMPAIGN round R4-094
(2026-11-13) -- a section-9-gap-priced DESCENT
from PW-S (r052_sep/cycle91w.py). The book
is PW-S's composition verbatim (the 28 per-symbol
equations + the causal realised-path governor in
its GOV-2 form: at a slot, if the sum of the last
5 EXITED picks' nets is <= -55, the plain fill's
pick symbol is excluded for that slot and the pick
is re-made by the unchanged fill law over CLEAN
destinations only (symbols whose own last-3
exited nets sum >= 0); if no clean destination
exists the governor abstains and the plain pick
stands; at most one action per slot; governor
inactive until 5 exits exist) COMPOSED with the
worst-year PROTECTION CLAUSE P in its
governor-host form: the fill tracks, per calendar
year, the running (picks, wins) over committed
picks; a year is PROTECTED at a slot when it has
>= 1 committed pick and its running win rate is
<= PROT_T (39/60 = 0.65); at a protected slot
where the governor fires, the firing is REFUSED
-- the governor's winner stands -- whenever the
replacement would leave the year's running win
rate lower than keeping the winner would. The
descent changed exactly FIVE equations, priced by
the DISCOVERY section-9 gap under the frozen
floors of R4-094 SLATE.md section 2 (steepest
first, 5 steps, budget termination): NZDCAD
15/ALL/0.55 -> 10/ALL/0.55; EURUSD A3/B35/0.5 ->
20/B35/0.5; USDCAD 10/B40/0.5 -> 10/B30/0.5;
CADCHF 10/B40/0.55 -> 15/B35/0.5; GBPCHF
10/B40/0.55 -> 20/ALL/0.55 (each equation refit
on DISCOVERY at its new config). The other 23
equations, the fill law, the governor and the
clause are PW-S's verbatim.

STATUS LABEL: NOT VALIDATED -- research module
from Round 4 campaign round R4-094 (September).
Round verdict: IMPROVED MARK -- the frozen mark
vs champion C58 passes on all four arms (AUDIT
wins 96 > 92; worst year 65.00% (2018, 39/60) >
63.33%; combined DD 123.81 <= 160.21; AUDIT net
+692.10 > 0), so R494-GAPW replaces C58 as
September's CAMPAIGN champion (a mark never
installs; NOTHING is installed). NOT VALIDATED:
the full battery ran in the slate-frozen family
{C58, SING82, GOV2-S, PW-S, ARB-S, PC58-S,
R494-GAPW} and REFUSED on check 20 alone (DSR
0.0000219 < 0.50 lowered line; the candidate
holds the family's highest Sharpe, 7.726, and
its highest DSR -- the deflation is
family-relative; the full family table is filed
in GRADING_R4_094.md). Section 9 Monte Carlo
MIDDLE PASSES under the battery's official mc9
(P(profit) 1.0000; DD p95 185.11 <= cap 185.71,
headroom +0.60; streak and worst-pair arms
pass) -- headroom NARROWER than PW-S's +0.81:
the descent cut the combined level 151.52 ->
123.81 and the cap contracted 41.57 against a
41.36 tail fall (combined ratio 1.4951x vs
PW-S's 1.4946x). Under gates.monte_carlo the DD
arm FAILS for both books alike (headroom -4.17
vs PW-S's -4.19; the other three arms pass).
LCT-middle PASSES (P 84.33%); checks 14
(leftover 43.21 > 36.16), 15 (3.0/day) and 16
pass; 19_pbo 0.2174 passes outright. Graded
record: DISC 513 / 70.96% / +2,750.46 (364
wins; governor fires 8, clause refusals 3;
DISC section-9 gap -23.70, ratio 1.3085x, vs
PW-S's -11.17 / 1.4263x); AUDIT 129 / 74.42% /
+692.10 (96 wins; fires 1, refusals 0);
combined 642 / +3,442.55, DD 123.81, worst
year 65.00% (2018), 10/10 years positive; red
DISC weeks 2, reported at face. GOV2-S
(r041_sep/cycle_r441gov2.py) remains
September's VALIDATED design; this module is
the campaign champion only. NOT installed (no
install was ordered or made). The R4-094
record is filed in
fx_research/round4_campaign/r094_sep/
(SLATE.md, GRADING_R4_094.md, work/).

THE RULE (what this module computes at a check
slot). Check slots are the September slots UTC
(1, 11, 18) = 07:30 / 17:30 / 00:30 MMT,
September weekdays only. At a slot, every symbol
runs ITS OWN equation, fitted on that symbol's
DISCOVERY rows only; the fill law, the governor
and the protection clause above produce at most
one pick per slot.
"""

from __future__ import annotations

import datetime as _dt
import os

import numpy as np
import pandas as pd

SYSTEM_NAME = "cycle91w"

# R4-030 governor (GOV-2): if the sum of the last 5
# exited picks' nets is <= GOVERNOR_THETA, the plain
# pick's symbol is excluded for that slot and the
# pick is re-made over clean destinations only (own
# last-3 exited nets sum >= 0); abstains if none.
GOVERNOR_THETA = -55.0
# R4-052 protection clause P: PROT_T = the parent
# book SING82's weakest DISCOVERY-year win rate
# (2018: 39/60), DISC-fitted at stage 1, never
# re-fit (July R4-029's fitting basis).
PROT_T = 39.0 / 60.0
STATUS_LABEL = 'NOT VALIDATED — campaign champion installed by user order 2026-11-13; live replay pass; blocker: fails DSR check alone'
CYCLE91W_CHECK_HOURS = (1, 11, 18)
SURFACE_GRID = (1, 11, 18)
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
# round2_sep/work/fits_disc.json, equationsA) ----
EQUATIONS = {
    'AUDCAD': {'geom': 'S200', 'band': 'ALL', 'tau': 0.5, 'prior': 0.49902152641878667, 'cells': {(1, 1, 2): 0.502197555420102, (1, -1, 0): 0.49126859367146813, (11, 1, 2): 0.5221713218288561, (11, -1, 0): 0.47671677637431065, (18, 1, 2): 0.4296636781504574, (18, -1, 0): 0.5691985618713876, (1, 1, 0): 0.5312263158490097, (1, -1, 2): 0.46764250082010794, (11, 1, 0): 0.5187964234357938, (11, -1, 2): 0.4801223902866225, (18, 1, 0): 0.4743137019099367, (18, -1, 2): 0.5245930315188753, (18, 1, 1): 0.4865727112762913, (18, -1, 1): 0.5117827953099048, (1, 1, 1): 0.4815978301919181, (1, -1, 1): 0.5166855494901638, (11, 1, 1): 0.5079136196656023, (11, -1, 1): 0.49036976001647953}},
    'AUDCHF': {'geom': 'S200', 'band': 'B35', 'tau': 0.5, 'prior': 0.49310344827586206, 'cells': {(11, 1, 1): 0.4983216356423558, (11, -1, 1): 0.4894720781202319, (18, 1, 1): 0.463568215892054, (18, -1, 1): 0.5244377811094453, (11, 1, 2): 0.5070464767616192, (11, -1, 0): 0.472263868065967, (1, 1, 2): 0.49048275862068963, (1, -1, 0): 0.49848275862068964, (18, 1, 0): 0.472263868065967, (18, -1, 2): 0.5157421289355323, (1, 1, 1): 0.461560203504805, (1, -1, 1): 0.5271339739966082, (18, 1, 2): 0.4768133174791914, (18, -1, 0): 0.511296076099881, (11, 1, 0): 0.5028213166144201, (11, -1, 2): 0.4755485893416928, (1, 1, 0): 0.5027223230490018, (1, -1, 2): 0.485178463399879}},
    'AUDJPY': {'geom': 'F15', 'band': 'B35', 'tau': 0.5, 'prior': 0.5, 'cells': {(18, 1, 2): 0.5086206896551724, (18, -1, 0): 0.49137931034482757, (1, 1, 1): 0.5431034482758621, (1, -1, 1): 0.45689655172413796, (1, 1, 0): 0.5294117647058824, (1, -1, 2): 0.47058823529411764, (18, 1, 1): 0.5132743362831859, (18, -1, 1): 0.48672566371681414, (11, 1, 2): 0.525, (11, -1, 0): 0.475, (1, 1, 2): 0.4778761061946903, (1, -1, 0): 0.5221238938053098, (18, 1, 0): 0.49137931034482757, (18, -1, 2): 0.5086206896551724, (11, 1, 0): 0.5087719298245614, (11, -1, 2): 0.49122807017543857, (11, 1, 1): 0.49557522123893805, (11, -1, 1): 0.504424778761062}},
    'AUDNZD': {'geom': 'F10', 'band': 'B25', 'tau': 0.5, 'prior': 0.5, 'cells': {(11, 1, 0): 0.4642857142857143, (11, -1, 2): 0.5357142857142857, (18, 1, 2): 0.46564885496183206, (18, -1, 0): 0.5343511450381679, (1, 1, 2): 0.5251798561151079, (1, -1, 0): 0.4748201438848921, (11, 1, 2): 0.5271317829457365, (11, -1, 0): 0.4728682170542636, (1, 1, 0): 0.5, (1, -1, 2): 0.5, (18, 1, 1): 0.4827586206896552, (18, -1, 1): 0.5172413793103449, (18, 1, 0): 0.5, (18, -1, 2): 0.5, (1, 1, 1): 0.49572649572649574, (1, -1, 1): 0.5042735042735043, (11, 1, 1): 0.5217391304347826, (11, -1, 1): 0.4782608695652174}},
    'AUDUSD': {'geom': 'F25', 'band': 'B40', 'tau': 0.5, 'prior': 0.4955357142857143, 'cells': {(1, 1, 2): 0.5185006435006435, (1, -1, 0): 0.4734555984555985, (18, 1, 1): 0.48277496839443745, (18, -1, 1): 0.5004740834386853, (11, 1, 1): 0.4881440281030445, (11, -1, 1): 0.5045374707259953, (1, 1, 1): 0.47961309523809526, (1, -1, 1): 0.5129464285714286, (11, 1, 2): 0.5004914809960682, (11, -1, 0): 0.49131716906946266, (18, 1, 2): 0.5004914809960682, (18, -1, 0): 0.49131716906946266, (1, 1, 0): 0.5236441798941799, (1, -1, 2): 0.46808862433862436, (18, 1, 0): 0.4824646074646075, (18, -1, 2): 0.5094916344916345, (11, 1, 0): 0.48214285714285715, (11, -1, 2): 0.5096657929226737}},
    'CADCHF': {'geom': 'F15', 'band': 'B35', 'tau': 0.5, 'prior': 0.496551724137931, 'cells': {(18, 1, 0): 0.4882032667876588, (18, -1, 2): 0.5057471264367817, (1, 1, 2): 0.4813902572523262, (1, -1, 0): 0.50519978106185, (11, 1, 1): 0.4884066587395957, (11, -1, 1): 0.5056480380499405, (18, 1, 2): 0.5100449775112443, (18, -1, 0): 0.48395802098950524, (11, 1, 0): 0.4522783251231527, (11, -1, 2): 0.541564039408867, (11, 1, 2): 0.48307497627333124, (11, -1, 0): 0.5105979120531478, (1, 1, 0): 0.49277925139994105, (1, -1, 2): 0.5013262599469496, (1, 1, 1): 0.4842322428529325, (1, -1, 1): 0.5098732684939582, (18, 1, 1): 0.46769052448565634, (18, -1, 1): 0.526514053897421}},
    'CADJPY': {'geom': 'F10', 'band': 'B40', 'tau': 0.55, 'prior': 0.5, 'cells': {(1, 1, 1): 0.5384615384615384, (1, -1, 1): 0.46153846153846156, (18, 1, 1): 0.5087719298245614, (18, -1, 1): 0.49122807017543857, (1, 1, 0): 0.49122807017543857, (1, -1, 2): 0.5087719298245614, (18, 1, 2): 0.5135135135135135, (18, -1, 0): 0.4864864864864865, (11, 1, 1): 0.512396694214876, (11, -1, 1): 0.48760330578512395, (1, 1, 2): 0.4909090909090909, (1, -1, 0): 0.509090909090909, (11, 1, 0): 0.48598130841121495, (11, -1, 2): 0.514018691588785, (18, 1, 0): 0.5046728971962616, (18, -1, 2): 0.4953271028037383, (11, 1, 2): 0.4811320754716981, (11, -1, 0): 0.5188679245283019}},
    'CHFJPY': {'geom': 'S200', 'band': 'ALL', 'tau': 0.55, 'prior': 0.5, 'cells': {(1, 1, 0): 0.5125, (1, -1, 2): 0.4875, (11, 1, 2): 0.41208791208791207, (11, -1, 0): 0.5879120879120879, (18, 1, 2): 0.480225988700565, (18, -1, 0): 0.519774011299435, (1, 1, 1): 0.5042016806722689, (1, -1, 1): 0.4957983193277311, (11, 1, 0): 0.5380116959064327, (11, -1, 2): 0.4619883040935672, (1, 1, 2): 0.47643979057591623, (1, -1, 0): 0.5235602094240838, (18, 1, 0): 0.47752808988764045, (18, -1, 2): 0.5224719101123596, (18, 1, 1): 0.5, (18, -1, 1): 0.5, (11, 1, 1): 0.5175438596491229, (11, -1, 1): 0.4824561403508772}},
    'EURAUD': {'geom': 'S300', 'band': 'B40', 'tau': 0.5, 'prior': 0.5, 'cells': {(11, 1, 1): 0.4915254237288136, (11, -1, 1): 0.5084745762711864, (18, 1, 0): 0.4766355140186916, (18, -1, 2): 0.5233644859813084, (1, 1, 1): 0.4957983193277311, (1, -1, 1): 0.5042016806722689, (18, 1, 2): 0.49523809523809526, (18, -1, 0): 0.5047619047619047, (18, 1, 1): 0.4909090909090909, (18, -1, 1): 0.509090909090909, (1, 1, 0): 0.4722222222222222, (1, -1, 2): 0.5277777777777778, (11, 1, 2): 0.49038461538461536, (11, -1, 0): 0.5096153846153846, (1, 1, 2): 0.5045871559633027, (1, -1, 0): 0.4954128440366973, (11, 1, 0): 0.5047619047619047, (11, -1, 2): 0.49523809523809526}},
    'EURCAD': {'geom': 'S300', 'band': 'B35', 'tau': 0.5, 'prior': 0.5, 'cells': {(1, 1, 2): 0.49193548387096775, (1, -1, 0): 0.5080645161290323, (11, 1, 1): 0.5, (11, -1, 1): 0.5, (18, 1, 0): 0.4690265486725664, (18, -1, 2): 0.5309734513274337, (11, 1, 0): 0.46956521739130436, (11, -1, 2): 0.5304347826086957, (18, 1, 2): 0.4782608695652174, (18, -1, 0): 0.5217391304347826, (1, 1, 1): 0.5344827586206896, (1, -1, 1): 0.46551724137931033, (11, 1, 2): 0.5132743362831859, (11, -1, 0): 0.48672566371681414, (1, 1, 0): 0.5175438596491229, (1, -1, 2): 0.4824561403508772, (18, 1, 1): 0.49557522123893805, (18, -1, 1): 0.504424778761062}},
    'EURCHF': {'geom': 'S300', 'band': 'B25', 'tau': 0.5, 'prior': 0.4956521739130435, 'cells': {(1, 1, 2): 0.48945012787723785, (1, -1, 0): 0.504156010230179, (11, 1, 0): 0.5150745794985718, (11, -1, 2): 0.4712789590606157, (18, 1, 2): 0.4588274044795784, (18, -1, 0): 0.5345849802371542, (18, 1, 0): 0.4806763285024155, (18, -1, 2): 0.5124223602484472, (1, 1, 0): 0.5345849802371542, (1, -1, 2): 0.45125164690382086, (11, 1, 2): 0.4685217391304348, (11, -1, 0): 0.5245217391304348, (1, 1, 1): 0.5049580472921434, (1, -1, 1): 0.48741418764302064, (18, 1, 1): 0.4782608695652174, (18, -1, 1): 0.5139751552795031, (11, 1, 1): 0.4876311844077961, (11, -1, 1): 0.5048725637181409}},
    'EURGBP': {'geom': 'F20', 'band': 'ALL', 'tau': 0.5, 'prior': 0.4950980392156863, 'cells': {(1, 1, 0): 0.5246000240587033, (1, -1, 2): 0.4693853001323229, (11, 1, 0): 0.5253359770874643, (11, -1, 2): 0.46915620180656536, (18, 1, 2): 0.4574420677361854, (18, -1, 0): 0.5369875222816399, (1, 1, 1): 0.49194962537860676, (1, -1, 1): 0.5000797066794198, (11, 1, 2): 0.4694989106753813, (11, -1, 0): 0.5083877995642702, (18, 1, 0): 0.5028011204481793, (18, -1, 2): 0.4918121094591683, (1, 1, 2): 0.4676205617382088, (1, -1, 0): 0.5216746157922629, (18, 1, 1): 0.4866946778711485, (18, -1, 1): 0.5045518207282914, (11, 1, 1): 0.4820703055997174, (11, -1, 1): 0.5000883236177355}},
    'EURJPY': {'geom': 'S150', 'band': 'B35', 'tau': 0.5, 'prior': 0.4861111111111111, 'cells': {(1, 1, 2): 0.4924026590693257, (1, -1, 0): 0.48385565052231716, (11, 1, 1): 0.44395711500974655, (11, -1, 1): 0.5141325536062378, (18, 1, 2): 0.46216475095785436, (18, -1, 0): 0.5138888888888888, (1, 1, 0): 0.4841269841269841, (1, -1, 2): 0.4925303454715219, (18, 1, 0): 0.46025293586269195, (18, -1, 2): 0.50903342366757, (18, 1, 1): 0.4871399176954732, (18, -1, 1): 0.4871399176954732, (1, 1, 1): 0.513653483992467, (1, -1, 1): 0.46280602636534834, (11, 1, 2): 0.43738229755178903, (11, -1, 0): 0.5306026365348399, (11, 1, 0): 0.47397397397397395, (11, -1, 2): 0.501001001001001}},
    'EURNZD': {'geom': 'F10', 'band': 'B40', 'tau': 0.5, 'prior': 0.47029702970297027, 'cells': {(1, 1, 1): 0.4526166902404526, (1, -1, 1): 0.46848970611346846, (18, 1, 0): 0.4777450718044777, (18, -1, 2): 0.45972705378645967, (18, 1, 2): 0.4817565089842317, (18, -1, 0): 0.4632379904657132, (18, 1, 1): 0.49598036726749595, (18, -1, 1): 0.4532453245324532, (1, 1, 0): 0.45397873120645393, (1, -1, 2): 0.49101576824349097, (11, 1, 0): 0.4769131118719348, (11, -1, 2): 0.46756731747941144, (1, 1, 2): 0.4531104053801606, (1, -1, 0): 0.4908462544367644, (11, 1, 1): 0.4817565089842317, (11, -1, 1): 0.45397873120645393, (11, 1, 2): 0.44572457245724567, (11, -1, 0): 0.5002700270027002}},
    'EURUSD': {'geom': 'F20', 'band': 'B35', 'tau': 0.5, 'prior': 0.4961832061068702, 'cells': {(1, 1, 0): 0.5010470850503276, (1, -1, 2): 0.4921975275282037, (11, 1, 0): 0.4662462661798871, (11, -1, 2): 0.5184201792233654, (18, 1, 1): 0.48391727017681213, (18, -1, 1): 0.5095582958178377, (11, 1, 2): 0.4791080755323423, (11, -1, 0): 0.5141957948305879, (1, 1, 1): 0.5221891577176866, (1, -1, 1): 0.47134170009056797, (18, 1, 0): 0.48720667232117615, (18, -1, 2): 0.5057251908396947, (11, 1, 1): 0.5184201792233654, (11, -1, 1): 0.4749419183538002, (1, 1, 2): 0.4967096604369571, (1, -1, 0): 0.4967096604369571, (18, 1, 2): 0.5271158313972785, (18, -1, 0): 0.4662462661798871}},
    'GBPAUD': {'geom': 'F30', 'band': 'B25', 'tau': 0.5, 'prior': 0.498, 'cells': {(18, 1, 2): 0.5136363636363637, (18, -1, 0): 0.48333333333333334, (1, 1, 0): 0.48333333333333334, (1, -1, 2): 0.5136363636363637, (11, 1, 2): 0.47874015748031495, (11, -1, 0): 0.5102362204724409, (11, 1, 1): 0.5113043478260869, (11, -1, 1): 0.4852173913043478, (18, 1, 0): 0.4790697674418604, (18, -1, 2): 0.517829457364341, (1, 1, 2): 0.4394736842105263, (1, -1, 0): 0.5578947368421052, (1, 1, 1): 0.46379310344827585, (1, -1, 1): 0.5327586206896552, (11, 1, 0): 0.49846153846153846, (11, -1, 2): 0.49846153846153846, (18, 1, 1): 0.48547008547008547, (18, -1, 1): 0.5111111111111111}},
    'GBPCAD': {'geom': 'S300', 'band': 'B35', 'tau': 0.5, 'prior': 0.5, 'cells': {(1, 1, 2): 0.4789915966386555, (1, -1, 0): 0.5210084033613446, (11, 1, 2): 0.4727272727272727, (11, -1, 0): 0.5272727272727272, (1, 1, 1): 0.49166666666666664, (1, -1, 1): 0.5083333333333333, (18, 1, 0): 0.5086206896551724, (18, -1, 2): 0.49137931034482757, (1, 1, 0): 0.5042016806722689, (1, -1, 2): 0.4957983193277311, (18, 1, 2): 0.4824561403508772, (18, -1, 0): 0.5175438596491229, (11, 1, 0): 0.4727272727272727, (11, -1, 2): 0.5272727272727272, (11, 1, 1): 0.5128205128205128, (11, -1, 1): 0.48717948717948717, (18, 1, 1): 0.48214285714285715, (18, -1, 1): 0.5178571428571429}},
    'GBPCHF': {'geom': 'F20', 'band': 'ALL', 'tau': 0.55, 'prior': 0.49707602339181284, 'cells': {(1, 1, 1): 0.5098179051965959, (1, -1, 1): 0.48542766129415676, (11, 1, 2): 0.5039311241065627, (11, -1, 0): 0.487264457439896, (18, 1, 0): 0.44589835546508994, (18, -1, 2): 0.5508707311556976, (1, 1, 2): 0.4984927955627901, (1, -1, 0): 0.4984927955627901, (11, 1, 0): 0.5232464217634325, (11, -1, 2): 0.4735226648573551, (18, 1, 2): 0.47229827941723285, (18, -1, 0): 0.5243214008045161, (1, 1, 0): 0.47212728791676156, (1, -1, 2): 0.517581833371307, (18, 1, 1): 0.4761333533263358, (18, -1, 1): 0.51032138751437, (11, 1, 1): 0.5155236576289208, (11, -1, 1): 0.4791600212652844}},
    'GBPJPY': {'geom': 'S300', 'band': 'B25', 'tau': 0.5, 'prior': 0.49586776859504134, 'cells': {(1, 1, 1): 0.4921946740128558, (1, -1, 1): 0.5007416825598644, (11, 1, 0): 0.4926942148760331, (11, -1, 2): 0.500694214876033, (18, 1, 2): 0.47904156014031757, (18, -1, 0): 0.5150127831619002, (18, 1, 0): 0.4966675553185817, (18, -1, 2): 0.48860303918954945, (1, 1, 0): 0.5081712545827379, (1, -1, 2): 0.48561486360529427, (1, 1, 2): 0.455463728191001, (1, -1, 0): 0.5387970615243343, (11, 1, 1): 0.4836476654658473, (11, -1, 1): 0.5007416825598644, (11, 1, 2): 0.5085572981063318, (11, -1, 0): 0.48493525086223727, (18, 1, 1): 0.4964377315474494, (18, -1, 1): 0.4964377315474494}},
    'GBPNZD': {'geom': 'S200', 'band': 'B25', 'tau': 0.5, 'prior': 0.4959183673469388, 'cells': {(1, 1, 1): 0.47111726046350744, (1, -1, 1): 0.5219647180906261, (1, 1, 2): 0.45610847078557454, (1, -1, 0): 0.5383002516074924, (18, 1, 2): 0.45839874411302983, (18, -1, 0): 0.5353218210361068, (11, 1, 2): 0.5247346938775511, (11, -1, 0): 0.460734693877551, (1, 1, 0): 0.4778002804175105, (1, -1, 2): 0.5159682193488083, (18, 1, 1): 0.4919631569441936, (18, -1, 1): 0.5008127144663175, (18, 1, 0): 0.4820286323484618, (18, -1, 2): 0.5044166920499543, (11, 1, 0): 0.5199372056514914, (11, -1, 2): 0.4737833594976452, (11, 1, 1): 0.5050155655482532, (11, -1, 1): 0.48806641300588033}},
    'GBPUSD': {'geom': 'F30', 'band': 'B35', 'tau': 0.5, 'prior': 0.4965034965034965, 'cells': {(18, 1, 0): 0.5183790568405954, (18, -1, 2): 0.47564401410555257, (18, 1, 1): 0.46434712828155456, (18, -1, 1): 0.5299208987733578, (1, 1, 0): 0.4752204317421709, (1, -1, 2): 0.5186986926117361, (11, 1, 1): 0.48445671975083743, (11, -1, 1): 0.501263442439913, (1, 1, 2): 0.5057048214942952, (1, -1, 0): 0.4881609618451724, (11, 1, 2): 0.48773045136681503, (11, -1, 0): 0.5059122695486332, (1, 1, 1): 0.5224605902572005, (1, -1, 1): 0.4716131326300818, (18, 1, 2): 0.5101800854013243, (18, -1, 0): 0.4836314128349527, (11, 1, 0): 0.5100030404378231, (11, -1, 2): 0.48391608391608393}},
    'NZDCAD': {'geom': 'F10', 'band': 'ALL', 'tau': 0.55, 'prior': 0.4970703125, 'cells': {(1, 1, 0): 0.5220656622023809, (1, -1, 2): 0.4744466145833333, (11, 1, 2): 0.5011438190607734, (11, -1, 0): 0.49561895718232046, (18, 1, 2): 0.4770123106060606, (18, -1, 0): 0.513375946969697, (11, 1, 1): 0.514715786637931, (11, -1, 1): 0.4802330280172414, (18, 1, 0): 0.3754294829842932, (18, -1, 2): 0.6162671793193717, (1, 1, 2): 0.5306829637096774, (1, -1, 0): 0.4661668346774194, (11, 1, 0): 0.4838556719653179, (11, -1, 2): 0.506977059248555, (1, 1, 1): 0.4846754807692308, (1, -1, 1): 0.5103165064102564, (18, 1, 1): 0.4931046195652174, (18, -1, 1): 0.5018002717391304}},
    'NZDCHF': {'geom': 'S200', 'band': 'B35', 'tau': 0.5, 'prior': 0.5, 'cells': {(1, 1, 1): 0.5217391304347826, (1, -1, 1): 0.4782608695652174, (11, 1, 1): 0.48672566371681414, (11, -1, 1): 0.5132743362831859, (18, 1, 1): 0.4778761061946903, (18, -1, 1): 0.5221238938053098, (18, 1, 2): 0.4576271186440678, (18, -1, 0): 0.5423728813559322, (18, 1, 0): 0.46153846153846156, (18, -1, 2): 0.5384615384615384, (11, 1, 0): 0.5185185185185185, (11, -1, 2): 0.48148148148148145, (11, 1, 2): 0.5391304347826087, (11, -1, 0): 0.4608695652173913, (1, 1, 0): 0.4778761061946903, (1, -1, 2): 0.5221238938053098, (1, 1, 2): 0.5128205128205128, (1, -1, 0): 0.48717948717948717}},
    'NZDJPY': {'geom': 'F30', 'band': 'B35', 'tau': 0.5, 'prior': 0.5, 'cells': {(1, 1, 2): 0.5041322314049587, (1, -1, 0): 0.49586776859504134, (18, 1, 2): 0.5043478260869565, (18, -1, 0): 0.4956521739130435, (11, 1, 1): 0.5126050420168067, (11, -1, 1): 0.48739495798319327, (18, 1, 0): 0.5169491525423728, (18, -1, 2): 0.4830508474576271, (11, 1, 2): 0.4954954954954955, (11, -1, 0): 0.5045045045045045, (1, 1, 0): 0.4782608695652174, (1, -1, 2): 0.5217391304347826, (11, 1, 0): 0.5, (11, -1, 2): 0.5, (1, 1, 1): 0.55, (1, -1, 1): 0.45, (18, 1, 1): 0.48717948717948717, (18, -1, 1): 0.5128205128205128}},
    'NZDUSD': {'geom': 'F10', 'band': 'B40', 'tau': 0.55, 'prior': 0.5, 'cells': {(11, 1, 2): 0.514018691588785, (11, -1, 0): 0.48598130841121495, (11, 1, 1): 0.49572649572649574, (11, -1, 1): 0.5042735042735043, (1, 1, 0): 0.5142857142857142, (1, -1, 2): 0.4857142857142857, (18, 1, 2): 0.49074074074074076, (18, -1, 0): 0.5092592592592593, (1, 1, 2): 0.48623853211009177, (1, -1, 0): 0.5137614678899083, (11, 1, 0): 0.4818181818181818, (11, -1, 2): 0.5181818181818182, (18, 1, 1): 0.48623853211009177, (18, -1, 1): 0.5137614678899083, (1, 1, 1): 0.5338983050847458, (1, -1, 1): 0.4661016949152542, (18, 1, 0): 0.49056603773584906, (18, -1, 2): 0.5094339622641509}},
    'USDCAD': {'geom': 'F10', 'band': 'B30', 'tau': 0.5, 'prior': 0.49238578680203043, 'cells': {(1, 1, 0): 0.48579498935647614, (1, -1, 2): 0.5019240216145406, (11, 1, 2): 0.4938595054855084, (11, -1, 0): 0.48579498935647614, (18, 1, 0): 0.5180530538726051, (18, -1, 2): 0.4616014409693794, (1, 1, 2): 0.4938595054855084, (1, -1, 0): 0.4938595054855084, (11, 1, 1): 0.5238137276539395, (11, -1, 1): 0.4629441624365482, (18, 1, 1): 0.45424851026263513, (18, -1, 1): 0.5325093798278525, (1, 1, 1): 0.4389796527748155, (1, -1, 1): 0.548223350253807, (11, 1, 0): 0.5132715929786491, (11, -1, 2): 0.47510365404735144, (18, 1, 2): 0.5061039560347359, (18, -1, 0): 0.4730461047950665}},
    'USDCHF': {'geom': 'S150', 'band': 'B40', 'tau': 0.5, 'prior': 0.4936708860759494, 'cells': {(1, 1, 1): 0.524093181576428, (1, -1, 1): 0.4652696521646633, (18, 1, 1): 0.49413970932958273, (18, -1, 1): 0.49413970932958273, (11, 1, 0): 0.521134719710669, (11, -1, 2): 0.4675632911392405, (18, 1, 2): 0.466361931551805, (18, -1, 0): 0.5126582278481012, (1, 1, 0): 0.4942462600690449, (1, -1, 2): 0.4942462600690449, (1, 1, 2): 0.5082579867389994, (1, -1, 0): 0.47968655816757083, (11, 1, 1): 0.507954941354082, (11, -1, 1): 0.48043200557426546, (18, 1, 0): 0.4751612132791975, (18, -1, 2): 0.5128970623358013, (11, 1, 2): 0.49379498634896996, (11, -1, 0): 0.49379498634896996}},
    'USDJPY': {'geom': 'F20', 'band': 'ALL', 'tau': 0.5, 'prior': 0.498046875, 'cells': {(1, 1, 0): 0.48947010869565216, (1, -1, 2): 0.508103649068323, (11, 1, 2): 0.5178631756756756, (11, -1, 0): 0.47461993243243245, (18, 1, 0): 0.5049672067901234, (18, -1, 2): 0.4864486882716049, (18, 1, 2): 0.5066907051282051, (18, -1, 0): 0.49130608974358975, (1, 1, 1): 0.49415703781512604, (1, -1, 1): 0.5025603991596639, (11, 1, 0): 0.5017611994219653, (11, -1, 2): 0.4959808526011561, (1, 1, 2): 0.5068308246073299, (1, -1, 0): 0.49112401832460734, (18, 1, 1): 0.5070586622807017, (18, -1, 1): 0.4895148026315789, (11, 1, 1): 0.5250418526785714, (11, -1, 1): 0.47147042410714285}},
}


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
    """ATR14 in pips at bar idx, replicating
    build_universe_sep.atr14 verbatim (mean true
    range over bars idx-13..idx against closes
    idx-14..idx-1); None when unavailable."""
    if idx < 14:
        return None
    hh = h[idx - 13:idx + 1]
    ll = l[idx - 13:idx + 1]
    pc = c[idx - 14:idx]
    tr = np.maximum(hh - ll, np.maximum(
        np.abs(hh - pc), np.abs(ll - pc)))
    v = float(tr.mean())
    if v <= 0:
        return None
    return v / _pip_of(sym)

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
    / its own geometry's distance. Canonical order: symbol index,
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
        ap = _atr14_pips(h, l, c, idx, sym)
        if ap is None:
            continue
        if eq["geom"].startswith("F"):
            dist_pips = float(eq["geom"][1:])
        else:
            dist_pips = float(eq["geom"][1:]) / 100.0 * ap
        for side in (1, -1):
            adj = pos if side > 0 else 1.0 - pos
            bucket = 0 if adj < BUCKET_E1 else \
                (1 if adj < BUCKET_E2 else 2)
            score = float(eq["cells"].get(
                (hour, side, bucket), eq["prior"]))
            xp, net = _trade_outcome(bars, sym, T, side,
                                     dist_pips)
            rows.append({
                "sym": sym, "side": side,
                "dist": dist_pips,
                "score": score,
                "in_band": bool(lo < adj < hi),
                "entry_px": entry_px,
                "pos_adj": float(adj),
                "exit": xp, "net": net,
                "entry_s": int(T)})
    return rows


def _margin(row):
    return row["score"] - EQUATIONS[row["sym"]]["tau"]


class FillState:
    """The R2Y-A fill law in live form. Slots are
    processed in chronological order; a kept pick
    blocks its symbol until its candle-replayed
    exit; an unresolved pick blocks until resolved
    (resolve_pending)."""

    def __init__(self):
        self.max_exit = {}
        self.picks = []
        self.gov_fires = []
        self.prot_refusals = []
        self.year_counts = {}
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
            "picks": self.picks,
            "year_counts": {str(k): v for k, v in
                            self.year_counts.items()}}

    def from_dict(self, d):
        self.max_exit = {k: (float("inf") if v == "inf"
                             else int(v))
                         for k, v in d.get("max_exit",
                                           {}).items()}
        self.picks = d.get("picks", [])
        self.year_counts = {int(k): list(v)
                            for k, v in d.get(
                                "year_counts", {}).items()}

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
        _yr = _dt.datetime.utcfromtimestamp(
            int(ts)).year
        _yc = self.year_counts.setdefault(_yr, [0, 0])
        _yc[0] += 1
        if row["net"] is not None and row["net"] > 0:
            _yc[1] += 1
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

        def choose(cand):
            band_best, any_best = {}, {}
            for sym, idxs in cand.items():
                br = [i for i in idxs if rows[i]["in_band"]]
                if br:
                    band_best[sym] = best(
                        br, lambda r: r["score"])
                any_best[sym] = best(idxs, _margin)
            firing = {s: i for s, i in band_best.items()
                      if rows[i]["score"]
                      >= EQUATIONS[s]["tau"]}
            if firing:
                return best(list(firing.values()),
                            lambda r: r["score"]), 1
            if band_best:
                return best(list(band_best.values()),
                            _margin), 2
            return best(list(any_best.values()),
                        _margin), 3

        pick, tier = choose(by_sym)
        # --- R4-030 governor (GOV-2): state = sum of
        # the last 5 EXITED picks' nets (exit <= ts,
        # exit-time order, ties by entry order). On
        # state <= theta, exclude the plain pick's
        # symbol for this slot and re-choose by the
        # unchanged fill law over CLEAN destinations
        # only (a symbol whose own last-3 exited nets
        # sum >= 0; a symbol with no exits yet is
        # clean). If no clean destination exists, the
        # governor abstains and the plain pick stands.
        exited = sorted(
            ((p["exit"], k, p["net"], p["sym"])
             for k, p in enumerate(self.picks)
             if p["exit"] is not None and p["exit"] <= ts),
            key=lambda z: (z[0], z[1]))
        if len(exited) >= 5 and float(sum(
                z[2] for z in exited[-5:])) <= GOVERNOR_THETA:
            own = {}
            for z in exited:
                own.setdefault(z[3], []).append(z[2])
            rest = {s: v for s, v in by_sym.items()
                    if s != rows[pick]["sym"]
                    and float(sum(own.get(s, [])[-3:]))
                    >= 0.0}
            if rest:
                p2, t2 = choose(rest)
                if p2 is not None:
                    # --- R4-052 clause P: at a protected
                    # slot (the pick year's running win
                    # rate over committed picks at or
                    # below PROT_T), refuse the step-aside
                    # when the replacement would dilute
                    # the year's running rate versus
                    # keeping the governor's winner.
                    _yr = _dt.datetime.utcfromtimestamp(
                        int(ts)).year
                    _yc = self.year_counts.get(_yr)
                    _refuse = False
                    if _yc is not None and _yc[0] >= 1 \
                            and _yc[1] / _yc[0] <= PROT_T:
                        _wn = rows[pick]["net"]
                        _rn = rows[p2]["net"]
                        if _wn is not None \
                                and _rn is not None \
                                and (_yc[1] + (1 if _rn > 0
                                               else 0)) \
                                / (_yc[0] + 1) \
                                < (_yc[1] + (1 if _wn > 0
                                             else 0)) \
                                / (_yc[0] + 1) - 1e-12:
                            _refuse = True
                    if _refuse:
                        self.prot_refusals.append(int(ts))
                    else:
                        pick, tier = p2, t2
                        self.gov_fires.append(int(ts))
        if tier == 2:
            e["tier2"] += 1
        elif tier == 3:
            e["tier3"] += 1
        e["picks"] += 1
        self._record(rows[pick], ts, tier)
        return [pick]


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
    """The slot stream settled through the R2Y-A
    fill. Persisted: the fill state (blocking
    ledger, picks), the delivered ledger and the
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
            m15_frames = fetch_cycle91w_m15_frames()
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


def is_cycle91w_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE91W_CHECK_HOURS and t.minute == 0


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
    """The delivered cycle91w stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle91w_m15_frames(state=None):
    from core.cycle78i_best import fetch_cycle78i_m15_frames
    return fetch_cycle78i_m15_frames()


def evaluate_cycle91w_signals(frames: dict,
                                check_time_utc,
                                m15_frames: dict | None
                                = None):
    return panel_entries(frames, check_time_utc,
                         m15_frames)


def select_cycle91w_entries(signals: pd.DataFrame,
                              open_symbols=()
                              ) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
