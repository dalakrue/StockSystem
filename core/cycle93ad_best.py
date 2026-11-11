"""Cycle 93AD -- November: the union design M5R143A02
(UNION-GAP-T50) written as a live rule.

PROVENANCE. Design M5R143A02, M5 validation series
Round 143 (union round), graded in
fx_research/m5_validation_series/round143
(VERDICT_NOV / grade_nov.json) on the combined frame:
November's stored pool (the standing stored-pool lane)
plus the Round 86 expectancy-mined universe
(round86/work/univ_nov.npz, built from the canonical
candle store fx/fx_data_canonical.db under the locked
conventions: RR 1:1, SL-first in one bar, cost 2.5 pips
all-in, Mon-Fri entries, entry at the slot's M15
close, 48h cap). Filed record: DISC kept 520, win
89.62%, net +10,076.10, leftover 71.20%, daily Sharpe
17.574; AUDIT kept 123, win 80.49%, net +675.20,
leftover 32.47%, entries/day exactly 3.000; Monte
Carlo section 9 MIDDLE PASS (DD-p95 headroom +114.75);
observed DD 307.50; worst cluster -205.0; red DISC
weeks 1; EC22 failed set {13_lct, 14_leftover} after
check 20 was read as SPA. VALIDATED: the base
M5R141A09 at Round 112 under the user's SPA
substitution order of 2026-11-11, and M5R143A02
itself at Round 143 (Hansen SPA t 14.872, consistent
p = 0.0000), where it was IMPROVED OVERALL vs the
base (the block's only unseen rise: the mined gap
layer's isolated worth +172.86) and became November's
standing validated best. Multi-pick label in the
frame (base pick + at most one mined pick per slot;
the GAP form below takes at most one pick per slot in
total). Sizing was NOT graded in the series and this
module carries no Best-N constant.

THE RULE (what this module computes at a check slot).
Check slots are the November slots UTC (13, 15, 17) =
19:30 / 21:30 / 23:30 MMT, November weekdays only (the
app routes month 11 here). At a slot the module builds
candidate trades from the candles for every one of the
28 symbols: entry at the close of the M15 bar ending
at the slot; M15 ATR14 sets the distance ladder
{0.5, 0.75, 1.0, 1.5} x ATR for SL and TP (RR 1:1);
each candidate is a (symbol, side, distance step)
triple with exit by the locked replay (SL-first in one
bar, 48h cap). Two layers then run in order:

BASE LAYER -- the standing fill in combination form.
Each candidate is scored by the filed combination
score over candle features of its entry bar (all
scales fitted on DISC 2016-2023 only, shipped below):
  sH = clip(0.5 + side * H1drift / (2 * qH), 0, 1),
       H1drift = (last H1 close - H1 close 12 bars
       earlier) in pips -- trend alignment;
  sM = clip(0.5 + side * M15dev / (2 * qM), 0, 1),
       M15dev = (entry close - mean of the last 8 M15
       closes) in pips -- momentum alignment;
  sF = clip(0.5 * loc + 0.25 + 0.25 * side * bodyr,
       0, 1), loc / bodyr = the last M5 bar's
       side-oriented close location and signed body
       fraction -- bar shape.
  score = 0.40 * sH + 0.30 * sM + 0.30 * sF
(the filed W2 weights of the construction's start
score -- the ranking that governed every post-2023
pick of the filed base; undefined features take the
filed neutral value 0.5). The base takes the
highest-scored candidate whose symbol is not blocked
by a still-open kept trade of either layer (ties:
canonical order -- symbol, side desc, step asc; the
score is distance-blind, a property of the filed
features, so within one symbol-side the canonical
order selects the 0.5 x ATR step). The filed base's
remaining elements -- the incumbent-kept core tier,
the DISC red-week boost/penalty flags, the tier-0
surgery forces and the 120 greedy Sharpe forces of
Rounds 111/141 -- are timestamp-keyed to specific
historical pool rows and exist only as DISC-segment
constructions (they never changed a single post-2023
pick in any filing: the base's AUDIT line was
byte-identical at the start set, at step 60, at step
120 and in the union); they have no live form and are
OMITTED here, with the substitution disclosed in
PROVENANCE_NOV.md in the port folder.

GAP LAYER -- the mined layer, exactly as filed. Only
at a slot where the base layer took no trade: among
the slot's candidates whose fitted DISC cell
(symbol x slot hour x side x distance step; the
DISC-fitted expectancy table is shipped below as
data) carries support n >= 15 -- every shipped cell
carries n = 171 -- and whose cell expectancy is at
least the filed dose threshold q50 = -2.6973527569
(the 0.50 quantile of the filed DISC dose population,
114,912 rows), take the highest-expectancy candidate
whose symbol is unblocked (ties: canonical order).
At most one gap pick per slot. A kept trade of either
layer blocks its symbol until its candle-replayed
exit; in the filed frame the gap layer additionally
pre-avoided future base positions, which no live rule
can know -- the live form runs the shared
1-open-per-symbol ledger in chronological order (see
PROVENANCE_NOV.md).

STATUS LABEL (user order 2026-11-11): written from
the validated design, NOT CHECKED. The test part
(historical replay / grading of this written rule)
was dropped by the user's order ("ignore the test
part"); this module has not been proofed as live
code and must not be represented as proofed. It is
not installed; registration in core/signal_mode.py
is a separate, announced push step.
"""

from __future__ import annotations

import datetime as _dt
import os

import numpy as np
import pandas as pd

SYSTEM_NAME = "cycle93ad"
CYCLE93AD_CHECK_HOURS = (13, 15, 17)
SURFACE_GRID = (13, 15, 17)
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
MULTS = (0.5, 0.75, 1.0, 1.5)

# ---- base-layer fitted constants (provenance:
# PROVENANCE_NOV.md in the port folder). W_BASE: the
# filed W2 weights of the construction's start score
# (lever_nov111: _wscore((0.40, 0.30, 0.30), sH, sM,
# sF)); W_SMC: the filed SMC weights (0.25, 0.25,
# 0.50), which entered the start score only through
# the omitted core tier -- carried here for the
# record. QH_P80 / QM_P80: the 0.80 quantiles of
# |H1 drift| and |M15 deviation| (pips) over the
# incumbent-kept DISC rows of the stored pool, from
# the filed feature scales (round6_r3
# features_r6r3_nov.npz).
W_BASE = (0.40, 0.30, 0.30)
W_SMC = (0.25, 0.25, 0.50)
QH_P80 = 48.599999999998644
QM_P80 = 11.235000000000111

# ---- gap-layer fitted constants. CELL_EXP: per
# mined cell key ((sym*24+hour)*2+side01)*4+mult_idx,
# the cell's DISC mean net (2.5-pip cost) over the
# Round 86 universe, fitted on DISC 2016-2023 rows
# only (univ_nov.npz cell table). Every shipped cell
# carries DISC support n = 171 (>= CELL_N_MIN = 15,
# the filed support rule). GAP_EXP_Q50: the filed
# dose threshold -- the 0.50 quantile of row_cell_exp
# over the DISC dose population (114,912 rows) at the
# Round 143 freeze (union_r143_summary.json).
CELL_N_MIN = 15
CELL_N_DISC = 171
GAP_EXP_Q50 = -2.6973527568922293
CELL_EXP = {
    104: -2.8682121971595644, 105: -2.504636591478694, 106: -2.214619883040937,
    107: -2.701253132832085, 108: -2.9017961570593114, 109: -2.632644110275686,
    110: -3.0517126148705005, 111: -2.411654135338343, 120: -2.8293024227234724,
    121: -2.945582706766915, 122: -2.4230158730158684, 123: -3.76021303258143,
    124: -3.250563909774443, 125: -2.526911027568932, 126: -2.856015037593994,
    127: -1.3307644110275918, 136: -2.308333333333342, 137: -2.541447368421065,
    138: -2.6404761904761944, 139: -3.154197994987449, 140: -2.7760442773600573,
    141: -2.458552631578936, 142: -2.359523809523805, 143: -1.8458020050125503,
    296: -3.1061403508771903, 297: -3.035463659147862, 298: -4.104845446950703,
    299: -4.269423558897237, 300: -2.5073099415204716, 301: -2.0732456140350948,
    302: -1.111862990810367, 303: -0.7305764411027623, 312: -3.0445071010860465,
    313: -2.487249373433581, 314: -2.244569757727649, 315: -3.2729949874686604,
    316: -2.6280910609857986, 317: -2.6975250626566405, 318: -2.9142439431913174,
    319: -1.7270050125313392, 328: -2.91228070175438, 329: -2.517919799498738,
    330: -2.6847953216374076, 331: -3.727443609022538, 332: -2.143024227234759,
    333: -2.5309523809523893, 334: -2.3619883040935883, 335: -1.4270676691729502,
    488: -2.686403508771923, 489: -2.4775375939849615, 490: -3.041060985797832,
    491: -2.74718045112782, 492: -3.060045948203853, 493: -2.71795112781955,
    494: -2.29987468671679, 495: -2.366353383458644, 504: -3.145885547201327,
    505: -2.3943295739348374, 506: -1.9899331662489697, 507: -2.011967418546384,
    508: -3.1320593149540463, 509: -3.1635025062656643, 510: -3.0100668337510306,
    511: -3.0701127819548644, 520: -2.887907268170425, 521: -3.07854010025063,
    522: -2.6689640768588077, 523: -1.1746240601503692, 524: -2.282435254803675,
    525: -1.9214598997493713, 526: -2.4391395154553135, 527: -4.005952380952391,
    680: -2.9903091060985707, 681: -2.8439223057644094, 682: -3.404427736006675,
    683: -3.199373433583945, 684: -2.5181286549707695, 685: -2.4942355889724377,
    686: -1.7365079365079434, 687: -1.882957393483726, 696: -2.5594611528822027,
    697: -2.436622807017545, 698: -3.1594402673350115, 699: -3.4206140350876826,
    700: -3.118859649122812, 701: -2.723088972431077, 702: -2.1312030075187987,
    703: -1.5793859649123163, 712: -2.3753968253968267, 713: -2.0678571428571484,
    714: -2.6831244778613326, 715: -4.61315789473686, 716: -2.8779866332497908,
    717: -3.1756892230576343, 718: -2.632915622389301, 719: -1.0218045112781906,
    872: -2.7968462823726004, 873: -2.4189536340852067, 874: -3.128028404344195,
    875: -3.7677318295739273, 876: -2.905492898913957, 877: -2.7576754385964977,
    878: -2.115329991645778, 879: -1.5424185463659175, 888: -3.1933792815371738,
    889: -2.731547619047616, 890: -2.6781537176273984, 891: -2.4907894736842175,
    892: -2.93761487050961, 893: -2.6827380952380953, 894: -2.376315789473687,
    895: -2.5092105263157816, 904: -2.7045739348370867, 905: -2.4010338345864555,
    906: -1.657769423558888, 907: -1.0499373433583779, 908: -2.369903926482879,
    909: -2.598966165413545, 910: -3.5007101086048555, 911: -4.108208020050143,
    1064: -3.232915622389305, 1065: -3.407581453634083, 1066: -4.223141186299072,
    1067: -4.889223057644105, 1068: -2.6347535505430217, 1069: -1.7344611528822056,
    1070: -0.9812865497076105, 1071: -0.25187969924812686, 1080: -3.0950292397660744,
    1081: -2.9100250626566377, 1082: -2.542105263157889, 1083: -2.7312030075187996,
    1084: -3.012364243943199, 1085: -2.683145363408527, 1086: -2.5356725146198884,
    1087: -2.2687969924812004, 1096: -2.978091060985793, 1097: -3.1603070175438503,
    1098: -3.6979532163742697, 1099: -4.507330827067673, 1100: -2.1016081871345045,
    1101: -1.8396929824561492, 1102: -1.30204678362573, 1103: -0.4926691729323249,
    1256: -3.0095029239766062, 1257: -3.0983395989974922, 1258: -3.5006265664160408,
    1259: -4.443421052631568, 1260: -2.602360066833749, 1261: -2.542512531328317,
    1262: -1.9154970760233845, 1263: -0.9613408521303359, 1272: -2.7772974101921535,
    1273: -2.2797305764411147, 1274: -2.3410609857978293, 1275: -2.1770050125313465,
    1276: -3.0703634085212954, 1277: -3.205482456140343, 1278: -2.850250626566418,
    1279: -3.068483709273168, 1288: -3.4904970760233973, 1289: -3.7618107769423594,
    1290: -3.5417293233082803, 1291: -2.8563283208020116, 1292: -1.7632205513784438,
    1293: -1.3387531328320719, 1294: -1.5923558897242955, 1295: -2.1436716791979893,
    1448: -1.910380116959068, 1449: -2.1443295739348436, 1450: -1.5817460317460388,
    1451: -1.1113408521303598, 1452: -3.6624269005847894, 1453: -3.1149436090225464,
    1454: -3.5215121136173724, 1455: -4.213972431077659, 1464: -2.872890559732665,
    1465: -2.3758771929824554, 1466: -1.0942355889724333, 1467: -1.084962406015074,
    1468: -2.9933583959899766, 1469: -3.0666666666666664, 1470: -3.9830409356725127,
    1471: -4.134461152882167, 1480: -2.808500417710945, 1481: -3.0715225563909603,
    1482: -3.036131996658278, 1483: -4.9347744360901515, 1484: -2.516896407685883,
    1485: -1.9804824561403653, 1486: -1.963868003341724, 1487: -0.06522556390984804,
    1640: -2.724206349206339, 1641: -1.7060463659147724, 1642: -0.5690476190475958,
    1643: 0.6624686716792313, 1644: -3.033771929824578, 1645: -3.5304197994987616,
    1646: -4.519089390142043, 1647: -5.662468671679231, 1656: -3.1492898913951715,
    1657: -2.736027568922329, 1658: -3.3929824561403676, 1659: -3.1918546365914913,
    1660: -3.1241019214703236, 1661: -2.7638471177944566, 1662: -2.083542188805325,
    1663: -1.8081453634085078, 1672: -2.0532581453634124, 1673: -3.290100250626566,
    1674: -4.305430242272353, 1675: -3.8291979949874744, 1676: -3.2057644110275696,
    1677: -1.7098997493734345, 1678: -0.6945697577276465, 1679: -1.1708020050125236,
    1832: -2.726817042606538, 1833: -1.4037593984962653, 1834: -0.7033416875522357,
    1835: -1.4200501253132731, 1836: -3.236131996658295, 1837: -4.062844611528795,
    1838: -4.296658312447766, 1839: -3.874185463659158, 1848: -3.3198412698412763,
    1849: -3.45407268170428, 1850: -3.871094402673375, 1851: -3.540977443609063,
    1852: -3.126524644945689, 1853: -1.841791979949853, 1854: -1.4381787802840151,
    1855: -1.4590225563909338, 1864: -2.0934210526315766, 1865: -2.304605263157889,
    1866: -1.4946950710108495, 1867: -2.8505639097744107, 1868: -3.101691729323313,
    1869: -2.7910087719298313, 1870: -3.8532581453634203, 1871: -2.1494360902255893,
    2024: -2.626900584795329, 2025: -2.654636591478713, 2026: -3.236925647451992,
    2027: -2.8695488721804465, 2028: -2.787635756056801, 2029: -2.5027568922305528,
    2030: -1.8215538847117478, 2031: -2.1304511278195535, 2040: -2.9314327485380125,
    2041: -3.345770676691735, 2042: -3.1078947368421095, 2043: -3.3441729323308342,
    2044: -2.6616750208855393, 2045: -1.848088972431074, 2046: -1.9505012531328267,
    2047: -1.6558270676691669, 2056: -2.4313700918964156, 2057: -2.2333333333333334,
    2058: -2.4811194653299915, 2059: -1.9611528822054818, 2060: -2.7268170426065064,
    2061: -2.7666666666666666, 2062: -2.5188805346700094, 2063: -3.038847117794519,
    2216: -2.5487468671679223, 2217: -2.0744360902255603, 2218: -1.7471177944862148,
    2219: -2.681662489557225, 2220: -2.96687552213868, 2221: -3.1836466165413544,
    2222: -3.2528822055137865, 2223: -2.3183375104427753, 2232: -2.964348370927321,
    2233: -2.9061090225563952, 2234: -2.8495822890559794, 2235: -2.622493734335861,
    2236: -2.526670843776103, 2237: -2.093890977443604, 2238: -2.1504177109440206,
    2239: -2.3775062656641395, 2248: -1.8918546365914801, 2249: -1.5219924812030172,
    2250: -2.0816207184628284, 2251: -2.6258145363408465, 2252: -3.1356307435254793,
    2253: -3.478007518796982, 2254: -2.9183792815371707, 2255: -2.374185463659155,
    2408: -2.6083542188805358, 2409: -2.6798245614034917, 2410: -2.954720133667494,
    2411: -1.1640350877192838, 2412: -2.9727652464494496, 2413: -2.4667919799498934,
    2414: -2.15029239766083, 2415: -3.8359649122807165, 2424: -3.044841269841277,
    2425: -2.002913533834589, 2426: -0.9018796992481154, 2427: -1.9302631578946998,
    2428: -3.2292188805346598, 2429: -3.325469924812027, 2430: -4.181913116123646,
    2431: -3.0697368421053, 2440: -3.1358187134502877, 2441: -1.8431390977443698,
    2442: -2.245906432748556, 2443: -1.862218045112805, 2444: -1.984565580618212,
    2445: -3.1568609022556284, 2446: -2.7540935672514437, 2447: -3.137781954887195,
    2600: -2.5759398496240586, 2601: -2.0306390977443685, 2602: -1.8014202172097125,
    2603: -3.4360902255638863, 2604: -3.325856307435252, 2605: -3.2063283208020015,
    2606: -3.3481203007518645, 2607: -1.7609022556391303, 2616: -2.700605680868855,
    2617: -3.0245927318295904, 2618: -3.683918128654995, 2619: -3.3391604010025446,
    2620: -3.69596908939013, 2621: -2.5389411027568722, 2622: -1.9295321637426641,
    2623: -1.6608395989974558, 2632: -2.2993107769423675, 2633: -3.799655388471159,
    2634: -4.063366750208839, 2635: -6.370488721804481, 2636: -2.9363617376775157,
    2637: -1.8561716791980123, 2638: -0.9366332497911636, 2639: 1.1214912280701521,
    2792: -2.3927109440267516, 2793: -2.2515977443609283, 2794: -2.3944444444444826,
    2795: -3.066854636591489, 2796: -3.2645989974937213, 2797: -3.2675751879699075,
    2798: -3.1499999999999666, 2799: -2.0504385964912273, 2808: -3.0027151211361796,
    2809: -2.4175438596491183, 2810: -1.7933166248955532, 2811: -2.4298245614035188,
    2812: -3.3862155388471034, 2813: -3.1464912280701784, 2814: -3.410275689223077,
    2815: -2.570175438596486, 2824: -2.3820802005012487, 2825: -2.0499999999999856,
    2826: -1.5661654135338139, 2827: 0.728947368421053, 2828: -2.6663742690058525,
    2829: -3.015977443609036, 2830: -3.539682539682564, 2831: -5.728947368421053,
    2984: -2.687050960735162, 2985: -3.3586466165413515, 2986: -3.671512113617366,
    2987: -0.7956140350877257, 2988: -3.743024227234759, 2989: -1.7917293233082738,
    2990: -1.513450292397671, 2991: -4.4818295739348315, 3000: -3.4517752715121275,
    3001: -2.7437030075188122, 3002: -3.129365079365075, 3003: -1.9125939849624307,
    3004: -3.3511069340016615, 3005: -2.7143796992481093, 3006: -2.2104845446950776,
    3007: -3.0874060150375686, 3016: -3.8274644945697553, 3017: -4.856798245614036,
    3018: -5.679156223893068, 3019: -7.726253132832089, 3020: -1.5711570593149544,
    3021: -0.14320175438595958, 3022: 0.6791562238930643, 3023: 2.7262531328320923,
    3176: -2.839557226399328, 3177: -2.331954887218059, 3178: -2.6961570593149764,
    3179: -5.284335839599039, 3180: -3.4794068504594833, 3181: -2.758834586466152,
    3182: -2.4248955722639685, 3183: -0.11942355889720598, 3192: -3.74553049289892,
    3193: -3.6489974937343557, 3194: -3.5588972431077632, 3195: -3.033709273182915,
    3196: -3.6203425229740986, 3197: -2.001566416040082, 3198: -1.4411027568922363,
    3199: -1.966290726817085, 3208: -3.7147660818713266, 3209: -3.5541040100250374,
    3210: -4.59110275689221, 3211: -4.041541353383399, 3212: -1.7034043441938347,
    3213: -1.6125626566416293, 3214: -0.40889724310779074, 3215: -0.9584586466165994,
    3368: -2.8122180451127794, 3369: -2.95310150375939, 3370: -3.1525062656641336,
    3371: -4.722869674185446, 3372: -2.6929615705931513, 3373: -2.148840852130333,
    3374: -1.8474937343358653, 3375: -0.2771303258145545, 3384: -3.0509189640768697,
    3385: -2.678759398496237, 3386: -2.953216374268993, 3387: -2.295363408521263,
    3388: -2.9119047619047542, 3389: -2.5884711779448693, 3390: -2.1412698412698536,
    3391: -2.704636591478736, 3400: -4.018045112781959, 3401: -3.918984962406028,
    3402: -4.682289055973271, 3403: -4.061403508771925, 3404: -1.2463659147869623,
    3405: -1.27305764411026, 3406: -0.3177109440267326, 3407: -0.9385964912280736,
    3560: -2.6280284043441893, 3561: -2.5721177944862146, 3562: -4.390058479532186,
    3563: -2.771929824561409, 3564: -3.945488721804525, 3565: -2.649185463659156,
    3566: -0.905012531328308, 3567: -2.5571428571428396, 3576: -3.7060359231411617,
    3577: -2.3343045112781544, 3578: -1.5310359231411548, 3579: -0.5216165413533654,
    3580: -3.234565580618223, 3581: -3.149780701754419, 3582: -3.7512531328321064,
    3583: -4.478383458646634, 3592: -4.137656641604011, 3593: -3.6895676691729333,
    3594: -2.599456975772754, 3595: -1.2090852130325505, 3596: -1.3943400167084368,
    3597: -1.6804197994987438, 3598: -2.4005430242272436, 3599: -3.790914786967449,
    3752: -2.556516290726803, 3753: -3.057581453634089, 3754: -3.7234753550543247,
    3755: -3.0625313283208473, 3756: -3.9406015037594138, 3757: -1.9424185463659103,
    3758: -1.4354218880534517, 3759: -2.191478696741808, 3768: -1.9975772765246549,
    3769: -2.152443609022558, 3770: -2.3431077694235647, 3771: -5.989598997493742,
    3772: -4.526566416040095, 3773: -3.4056390977443574, 3774: -2.9298245614035032,
    3775: 0.989598997493744, 3784: -4.100918964076853, 3785: -4.652944862155384,
    3786: -6.824227234753564, 3787: -7.592731829573956, 3788: -1.2856725146198857,
    3789: -0.5159147869674201, 3790: 1.350125313283226, 3791: 2.2192982456140573,
    3944: -2.4004385964912216, 3945: -2.991885964912258, 3946: -3.4824143692564604,
    3947: -4.28389724310777, 3948: -3.1050334168755294, 3949: -2.465444862155403,
    3950: -1.9242690058479643, 3951: -1.013721804511292, 3960: -3.007623224728491,
    3961: -3.0105576441102664, 3962: -2.465622389306612, 3963: -0.7088345864661633,
    3964: -3.4389097744360924, 3965: -2.4375626566416115, 3966: -2.8980367585630606,
    3967: -4.471240601503759, 3976: -3.0244987468671676, 3977: -1.918953634085186,
    3978: -2.9707184628237018, 3979: -0.5025689223057519, 3980: -2.1826441102756884,
    3981: -3.384617794486244, 3982: -2.328613199665857, 3983: -4.497431077694248,
    4136: -2.9018379281537183, 4137: -2.365726817042609, 4138: -2.273433583959911,
    4139: -2.169924812030074, 4140: -2.8077694235588972, 4141: -3.0403508771929824,
    4142: -3.011528822055128, 4143: -3.047117794486214, 4152: -2.8257936507936505,
    4153: -2.307236842105252, 4154: -2.8910192147034137, 4155: -2.3658521303258144,
    4156: -3.341499582289054, 4157: -3.050031328320811, 4158: -2.441896407685891,
    4159: -3.0994360902255638, 4168: -2.6459064327485398, 4169: -3.2365288220551442,
    4170: -2.8758563074352588, 4171: -4.771303258145358, 4172: -2.485630743525477,
    4173: -1.8397869674185379, 4174: -2.2139515455304895, 4175: -0.22869674185464106,
    4328: -2.8692564745196307, 4329: -2.922932330827071, 4330: -2.789139515455311,
    4331: -2.6754385964912495, 4332: -2.679741019214705, 4333: -2.1530701754385926,
    4334: -2.294569757727642, 4335: -2.44348370927316, 4344: -3.0583333333333402,
    4345: -2.7195802005012615, 4346: -2.4205931495405313, 4347: -2.3029448621554134,
    4348: -2.6971804511278177, 4349: -2.8218358395989913, 4350: -3.0240183792815247,
    4351: -2.6970551378445853, 4360: -3.157748538011693, 4361: -3.3319862155388353,
    4362: -3.4566833751044164, 4363: -3.233771929824547, 4364: -1.9529866332497954,
    4365: -1.6680137844611662, 4366: -1.6586048454469626, 4367: -2.2184837092731953,
    4520: -2.595488721804519, 4521: -2.2909147869674102, 4522: -2.333667502088544,
    4523: -1.8368421052631623, 4524: -3.0723475355054273, 4525: -3.0749373433584033,
    4526: -2.8722639933166314, 4527: -3.3552631578947336, 4536: -3.1386173767752656,
    4537: -2.5296679197994947, 4538: -2.0783208020050186, 4539: -1.4521929824561464,
    4540: -3.173538011695908, 4541: -2.8603070175438545, 4542: -2.9216791979949814,
    4543: -3.766729323308264, 4552: -2.814954051796155, 4553: -3.494548872180453,
    4554: -2.890392648287384, 4555: -4.300626566416033, 4556: -2.379991645781119,
    4557: -1.5054511278195466, 4558: -2.1096073517126164, 4559: -1.194360902255643,
    4712: -2.900626566416038, 4713: -2.3203634085213, 4714: -2.460150375939841,
    4715: -2.980451127819542, 4716: -3.056182121971602, 4717: -3.0615914786967484,
    4718: -2.8015873015873076, 4719: -2.2189223057644196, 4728: -2.937030075187967,
    4729: -2.429291979949874, 4730: -2.4133249791144538, 4731: -1.523370927318284,
    4732: -2.618943191311618, 4733: -2.87478070175439, 4734: -2.7349624060150393,
    4735: -3.4766290726817166, 4744: -2.459899749373434, 4745: -1.992230576441107,
    4746: -2.4144527986633335, 4747: -1.2451127819548928, 4748: -2.6172932330827035,
    4749: -3.1437343358395937, 4750: -2.75221386800333, 4751: -4.153508771929821,
    4904: -3.085944026733491, 4905: -2.4886904761904893, 4906: -2.0041353383458897,
    4907: -0.8520676691729562, 4908: -2.8574979114452805, 4909: -2.9959586466165264,
    4910: -3.3351294903926267, 4911: -4.288283208020034, 4920: -2.9630743525480407,
    4921: -2.9718671679197968, 4922: -3.7063492063491945, 4923: -4.058145363408525,
    4924: -3.370384294068492, 4925: -2.401566416040103, 4926: -1.911946532999172,
    4927: -1.314912280701746, 4936: -2.4852965747702593, 4937: -2.6614661654135476,
    4938: -2.8532999164578277, 4939: -4.43972431077691, 4940: -2.6428571428571415,
    4941: -2.3385338345864537, 4942: -2.255304928989121, 4943: -0.5602756892230905,
    5096: -3.0975355054302396, 5097: -3.2679824561403525, 5098: -2.733667502088549,
    5099: -3.0294486215538896, 5100: -2.4503759398496245, 5101: -1.906077694235586,
    5102: -2.4541353383458713, 5103: -2.093859649122802, 5112: -2.9838554720133565,
    5113: -2.695770676691705, 5114: -3.2520885547201033, 5115: -3.21109022556387,
    5116: -2.942794486215549, 5117: -2.596647869674208, 5118: -1.8359649122807322,
    5119: -1.788909774436129, 5128: -2.868045112781954, 5129: -2.623997493734342,
    5130: -3.3045948203842994, 5131: -5.025187969924818, 5132: -2.240434419381789,
    5133: -2.427506265664156, 5134: -1.6954051796156986, 5135: -0.11065162907268436,
    5288: -3.1353801169590527, 5289: -3.204887218045093, 5290: -2.528989139515444,
    5291: -3.3939849624060026, 5292: -2.4083124477861455, 5293: -2.065100250626584,
    5294: -2.6999164578112063, 5295: -1.6060150375939966, 5304: -3.2427318295739402,
    5305: -1.9548872180451031, 5306: -2.418379281537168, 5307: -1.710526315789519,
    5308: -3.4276524644945714, 5309: -3.412531328320811, 5310: -2.8974101921470425,
    5311: -3.5023809523809057, 5320: -2.592898913951544, 5321: -3.4475563909774256,
    5322: -3.716374269005834, 5323: -3.389598997493726, 5324: -2.48078529657477,
    5325: -1.5524436090225724, 5326: -1.5952380952381155, 5327: -1.6104010025062723}


def _pip_of(sym):
    return 0.01 if "JPY" in sym else 0.0001


def _atr14(h, l, c, idx):
    """Mean true range over bars idx-13..idx (prev
    closes idx-14..idx-1), in price units; None if
    unavailable."""
    if idx < 14:
        return None
    hh = h[idx - 13:idx + 1]
    ll = l[idx - 13:idx + 1]
    pc = c[idx - 14:idx]
    tr = np.maximum(hh - ll, np.maximum(np.abs(hh - pc),
                                        np.abs(ll - pc)))
    v = float(tr.mean())
    return v if v > 0 else None


def _shape_scores(side, h1_closes, m15_closes, m5_bar,
                  pip):
    """The filed (sH, sM, sF) feature scores for one
    (symbol, side) at a slot. h1_closes: the last 13
    H1 closes ending at the slot (or None); m15_closes:
    the last 8 M15 closes ending with the entry bar
    (or None); m5_bar: (o, h, l, c) of the M5 bar
    ending at the slot (or None). Undefined features
    take the filed neutral value 0.5 (the filings'
    nan_to_num convention)."""
    if h1_closes is not None and len(h1_closes) >= 13:
        drift = (float(h1_closes[-1])
                 - float(h1_closes[-13])) / pip
        sH = min(1.0, max(0.0, 0.5 + side * drift
                          / (2.0 * QH_P80)))
    else:
        sH = 0.5
    if m15_closes is not None and len(m15_closes) >= 8:
        dev = (float(m15_closes[-1])
               - float(np.mean(m15_closes[-8:]))) / pip
        sM = min(1.0, max(0.0, 0.5 + side * dev
                          / (2.0 * QM_P80)))
    else:
        sM = 0.5
    if m5_bar is not None:
        o, h, l, c = m5_bar
        rng = (h - l) / pip
        body = (c - o) / pip
        if h > l:
            loc = (c - l) / (h - l) if side > 0 \
                else (h - c) / (h - l)
        else:
            loc = 0.5
        bodyr = body / rng if rng > 0 else 0.0
        sF = min(1.0, max(0.0, 0.5 * loc + 0.25
                          + 0.25 * side * bodyr))
    else:
        sF = 0.5
    return sH, sM, sF


def _trade_outcome(bars, sym, entry_s, side, dist_price,
                   mult, atr_pips):
    """(exit_epoch, net25) for one candidate from the
    symbol's M15 bar arrays (ts, o, h, l, c); exit/net
    are None while the trade is unresolved in the
    available bars and the 48h cap bar is not yet
    present."""
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
            return entry_s + MAX_HOLD * 3600, \
                gross - COST_PIPS
        if isl <= itp:
            return int(fwd[isl]) + 900, -mult * atr_pips \
                - COST_PIPS
        return int(fwd[itp]) + 900, mult * atr_pips \
            - COST_PIPS
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
        return int(fwd[isl]) + 900, -mult * atr_pips \
            - COST_PIPS
    return int(fwd[itp]) + 900, mult * atr_pips - COST_PIPS


def _slot_rows(T, m15_bars, h1_bars, m5_bars):
    """Candidate rows for one slot, in canonical order
    (symbol index, side desc, distance asc) -- the
    mined universe's row order restricted to the slot.
    Each row: sym, side, mult, cell_key / cell_exp (the
    fitted DISC cell expectancy, None when the cell is
    outside the shipped table), score (the base layer's
    W2 combination score), entry_px, atr (pips), exit,
    net (exit/net None while unresolved in the
    available bars). A symbol contributes rows only
    when its M15 entry bar (the bar ending at T) and
    the 14-bar ATR window are available."""
    rows = []
    hour = (T % 86400) // 3600
    for sym in SYMBOLS:
        bars = m15_bars.get(sym)
        if bars is None:
            continue
        ts, _o, h, l, c = bars
        idx = int(np.searchsorted(ts, T - 900))
        if idx >= len(ts) or ts[idx] != T - 900 \
                or idx < 14:
            continue
        pip = _pip_of(sym)
        atr_price = _atr14(h, l, c, idx)
        if atr_price is None:
            continue
        atr = float(atr_price / pip)
        entry_px = float(c[idx])
        # feature windows (the filings' bar features,
        # read live): last 8 M15 closes ending with the
        # entry bar; last 13 H1 closes ending with the
        # H1 bar that ends at T; the M5 bar ending at T.
        m15_closes = c[idx - 7:idx + 1] if idx >= 7 \
            else None
        h1_closes = None
        hb = h1_bars.get(sym)
        if hb is not None:
            tsh, _oh, _hh, _lh, ch = hb
            ih = int(np.searchsorted(tsh, T - 3600,
                                     side="right")) - 1
            if ih >= 12:
                h1_closes = ch[ih - 12:ih + 1]
        m5_bar = None
        mb = (m5_bars or {}).get(sym)
        if mb is not None:
            t5, o5, h5, l5, c5 = mb
            i5 = int(np.searchsorted(t5, T - 300))
            if i5 < len(t5) and t5[i5] == T - 300:
                m5_bar = (float(o5[i5]), float(h5[i5]),
                          float(l5[i5]), float(c5[i5]))
        sidx = SYM_IDX[sym]
        for side in (1, -1):
            sH, sM, sF = _shape_scores(
                side, h1_closes, m15_closes, m5_bar, pip)
            score = W_BASE[0] * sH + W_BASE[1] * sM \
                + W_BASE[2] * sF
            side01 = 0 if side > 0 else 1
            for mi, m in enumerate(MULTS):
                dist = m * atr * pip
                xp, net = _trade_outcome(
                    bars, sym, T, side, dist, m, atr)
                ckey = ((sidx * 24 + hour) * 2 + side01) \
                    * 4 + mi
                rows.append({
                    "sym": sym, "side": side, "mult": m,
                    "cell_key": int(ckey),
                    "cell_exp": CELL_EXP.get(int(ckey)),
                    "score": float(score),
                    "entry_px": entry_px, "atr": atr,
                    "exit": xp, "net": net,
                    "entry_s": int(T)})
    return rows


class UnionState:
    """The M5R143A02 two-layer fill in live form. Slots
    are processed in chronological order. One shared
    blocking ledger serves both layers: a kept pick
    whose exit is not yet resolvable from the available
    bars blocks its symbol until resolved
    (resolve_pending) -- the live form of the filed
    union collision law (kept trades win; a candidate
    whose window would overlap a kept position on its
    symbol is skipped). At each slot the base layer
    decides first; the gap layer runs only when the
    base took no trade at that slot."""

    def __init__(self):
        self.max_exit = {}
        self.picks = []
        self.ev = {e: {"slots_total": 0, "base_picks": 0,
                       "gap_slots": 0, "gap_dose_pass": 0,
                       "gap_blocked": 0, "gap_picks": 0,
                       "unfilled_no_rows": 0}
                   for e in ("disc", "audit")}

    # -- persistence -------------------------------------------------
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

    # -- core ----------------------------------------------------------
    def _record(self, row, ts, layer):
        row["layer"] = layer
        pick = {"sym": row["sym"], "entry_s": int(ts),
                "side": int(row["side"]),
                "mult": float(row["mult"]),
                "entry_px": float(row["entry_px"]),
                "atr": float(row["atr"]),
                "score": float(row["score"]),
                "cell_key": int(row["cell_key"]),
                "cell_exp": row["cell_exp"],
                "layer": layer,
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
        """Recompute unresolved picks from the bars now
        available; on resolution the pick's true exit
        replaces the blocking placeholder."""
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
                pick["side"], dist, pick["mult"],
                pick["atr"])
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
        """rows: the slot's candidate rows in canonical
        order (see _slot_rows). Returns picked row
        indices (at most one: a base pick, or -- only
        when the base took none -- one gap pick)."""
        e = self.ev[era]
        e["slots_total"] += 1
        if not rows:
            e["unfilled_no_rows"] += 1
            return []
        # BASE layer: highest W2 score first, canonical
        # order on ties; first unblocked candidate wins.
        order = sorted(
            range(len(rows)),
            key=lambda p: (-rows[p]["score"], p))
        for p in order:
            if self.max_exit.get(rows[p]["sym"], -1) > ts:
                continue
            e["base_picks"] += 1
            self._record(rows[p], ts, "base")
            return [p]
        # GAP layer (the base took no trade at this
        # slot): fitted-cell expectancy at or above the
        # filed dose threshold, highest first, canonical
        # order on ties; first unblocked candidate wins.
        e["gap_slots"] += 1
        cands = [p for p, r in enumerate(rows)
                 if r["cell_exp"] is not None
                 and r["cell_exp"] >= GAP_EXP_Q50]
        e["gap_dose_pass"] += len(cands)
        for p in sorted(
                cands,
                key=lambda p: (-rows[p]["cell_exp"], p)):
            if self.max_exit.get(rows[p]["sym"], -1) > ts:
                e["gap_blocked"] += 1
                continue
            e["gap_picks"] += 1
            self._record(rows[p], ts, "gap")
            return [p]
        return []


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
    return (ts[order], o[order], h[order], l[order],
            c[order])


class _Form:
    """The slot stream settled through the M5R143A02
    union fill. Persisted: the union state (blocking
    ledger, picks), the delivered ledger and the
    processed checks."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.union = UnionState()
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
        if "union" in d:
            self.union.from_dict(d["union"])
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
                       "union": self.union.to_dict(),
                       "delivered": ser(self.delivered),
                       "processed": self.processed}, fh)

    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=(), m5_frames=None):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r["check"]) == chk]
        T = int(chk.timestamp())
        T -= T % 3600  # entries fire at H:00 UTC; the H:30
        # stamp is the evaluation label
        if m15_frames is None:
            m15_frames = fetch_cycle93ad_m15_frames()
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
        m5_bars = {}
        if m5_frames:
            for sym in SYMBOLS:
                b = _bars_from_frame(m5_frames.get(sym))
                if b is not None:
                    m5_bars[sym] = b
        self.union.resolve_pending(m15_bars)
        era = "disc" if _dt.datetime.utcfromtimestamp(
            T).year <= 2023 else "audit"
        rows = _slot_rows(T, m15_bars, h1_bars, m5_bars)
        picks = self.union.process_slot(T, era, rows)
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
                  "layer": r.get("layer"),
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


def is_cycle93ad_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE93AD_CHECK_HOURS and t.minute == 30


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
    """The delivered cycle93ad stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle93ad_m15_frames(state=None):
    from core.cycle89_best import fetch_cycle89_m15_frames
    return fetch_cycle89_m15_frames()


def evaluate_cycle93ad_signals(frames: dict, check_time_utc,
                               m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle93ad_entries(signals: pd.DataFrame,
                             open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
