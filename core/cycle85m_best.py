"""Cycle 85M -- February: the anchored multi-pick
design M5R73A02 (ANCH-BROAD) written as a live rule.

PROVENANCE. Design M5R73A02, M5 validation series
Round 73 (GATES_R73 section 6: CENTRE x HEADROOM on
the ANCHOR2 base), graded in
fx_research/m5_validation_series/round73
(VERDICT_FEB / grade_feb.json) on the stored-pool
frame (February's stored pool -- the record system's
realised candidate trades). Filed record: DISC kept
524, win 97.71%, net +6,846.91, leftover 78.63%;
AUDIT kept 140, win 88.57%, net +635.28, leftover
36.71%; Monte Carlo section 9 MIDDLE PASS (DD-p95
headroom +53.33 -- five times the ANCHOR2 control's
+10.24); observed DD 152.93; worst cluster -95.00;
red DISC weeks 0; EC22 failed set {13_lct,
14_leftover, 20_dsr} with DSR 0.000. VALIDATED at
Round 112 under the user's SPA substitution order of
2026-11-11 (Hansen SPA t 21.022, consistent
p = 0.0000), where the failed set's only remaining
member was the replaced check 20. Multi-pick label
(<= 2 picks per slot). Sizing was NOT graded in the
series and this module carries no Best-N constant.

THE RULE (what this module computes at a check
slot). Check slots are the February slots UTC
(11, 13, 16) = 17:30 / 19:30 / 22:30 MMT, February
weekdays only (the app routes month 2 here). At a
slot the module builds candidate trades from the
candles for every one of the 28 symbols: entry at
the close of the M15 bar ending at the slot; M15
ATR14 sets the distance ladder {0.5, 0.75, 1.0, 1.5}
x ATR for SL and TP (RR 1:1); exit by the locked
replay (SL-first in one bar, 48h cap). Each candidate
(a symbol x side x distance-step triple) carries
four filed quantities, all fitted on DISC 2016-2023
only and shipped below as data:

  sMC = 0.25 * sH + 0.25 * sM + 0.50 * sF -- the
  filed pool score over the entry bar's candle
  features: sH = clip(0.5 + side * H1drift /
  (2 * qH), 0, 1) with H1drift the 12-bar H1 drift
  in pips and qH = 55.32 pips; sM the same form over
  the M15 8-bar deviation with qM = 12.825 pips; sF
  the last M5 bar's side-oriented shape
  (0.5 * loc + 0.25 + 0.25 * side * bodyr);
  undefined features take the filed neutral 0.5.
  E -- the DISC-fitted (symbol x hour) expectancy,
  shrink k = 20 toward the symbol mean (fallback
  hour mean, then global), fitted on the pool's
  recorded outcomes over 538 DISC rows at the triple
  (the shipped table, CELL_EXP below).
  tier -- whether the candidate's (symbol x hour x
  side) cell is in the DISC-frozen PARTIAL-ANCHOR
  cell set (TIER_CELLS below): the live form of the
  base ranking's filed tier (lever_feb50 score[6]:
  at the top-f = 0.2 fraction of series-core-holding
  slots by DISC-fitted slot quality, series-core
  rows ranked strictly first by sMC; everywhere
  else the order is the affine-mapped expectancy).
  anchored -- whether the candidate's cell is in
  the DISC-frozen BROAD anchor cell set
  (ANCHOR_CELLS below): the live form of the filed
  anchor BROAD = incumbent-kept rows UNION
  series-core rows (round10/M5R10A01), 638 rows.

THE FILL (the filed order, in live form). Candidates
are ordered: tier cells first, by sMC descending;
then all other candidates, by E descending; ties by
the canonical order (symbol, side desc, step asc) --
the filed ranking is distance-blind (neither sMC
nor E carries a distance input), so within one
(symbol, side) the canonical order selects the
0.5 x ATR step. FIRST PICK: the first candidate in
that order whose symbol is not blocked by a
still-open kept trade. SECOND PICK (the anchored
multi-pick): the first candidate in the same order
on a DISTINCT symbol from the first pick, unblocked,
whose cell is ANCHORED; if no anchored candidate is
available, no second pick is taken (the filed
exp_pos rule on the BROAD indicator). At most 2
picks per slot. A kept pick of either kind blocks
its symbol until its candle-replayed exit
(1-open-per-symbol).

TRANSLATIONS (full list in PROVENANCE_FEB.md).
The filed construction selects among stored-pool
rows; this module generates candidates from candles
(the R86 mined-universe generator form, as in the
November port) and exits them by their own ATR-step
band instead of the pool's filed exits. The filed
anchor is a set of historical ROWS; a live candidate
has no row identity, so the anchor ships as the
DISC-frozen CELL set above -- the port's headline
disclosure. The base ranking's partial-anchor tier
is slot-keyed in the filings; its live form is the
frozen cell set, which keeps the (symbol x hour x
side) dimension and drops the slot dimension. The
filed score's strict tier step (+ range + 1) and
affine expectancy map are order-isomorphic to the
two-tier order above and are shipped in that form.

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

SYSTEM_NAME = "cycle85m"
CYCLE85M_CHECK_HOURS = (11, 13, 16)
SURFACE_GRID = (11, 13, 16)
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

# ---- fitted constants (provenance: PROVENANCE_FEB.md
# in the port folder; readable copy constants_feb.json).
# W_SMC: the filed pool-score weights (SMC =
# (0.25, 0.25, 0.50)); QH_P80 / QM_P80: the 0.80
# quantiles of |H1 drift| and |M15 deviation| (pips)
# over the incumbent-kept DISC rows of February's
# stored pool (round6_r3 features scales).
W_SMC = (0.25, 0.25, 0.50)
QH_P80 = 55.32000000000107
QM_P80 = 12.825000000001204

# ---- expectancy table. CELL_EXP: keyed by
# (symbol index * 24 + UTC hour), the DISC-fitted
# (symbol x hour) expectancy E of GATES_R73 section 6
# (shrink k = 20 toward the symbol mean; fallback
# hour mean, then the global +13.011), fitted on 538
# DISC pool rows at the triple (11, 13, 16). Every
# (symbol, triple hour) pair is present, with the
# filed fallback chain already applied.
CELL_EXP = {
    11: 9.43817261904722, 13: 12.428718411534142, 16: 16.52369969278014,
    35: 8.836785714285757, 37: 8.836785714285757, 40: 8.836785714285757,
    59: 9.43817261904722, 61: 12.428718411534142, 64: 16.52369969278014,
    83: 11.396428571428032, 85: 11.396428571428032, 88: 11.396428571428032,
    107: 2.8971571428568974, 109: 2.8971571428568974,
    112: 2.8971571428568974, 131: 7.500000000000009,
    133: 7.500000000000008, 136: 7.500000000000009, 155: 5.277777777777231,
    157: 5.277777777777231, 160: 5.277777777777231,
    179: 13.365000000000009, 181: 13.365000000000009,
    184: 13.365000000000009, 203: 9.43817261904722,
    205: 12.428718411534142, 208: 16.52369969278014,
    227: 21.75704761904771, 229: 21.75704761904771, 232: 21.75704761904771,
    251: 9.43817261904722, 253: 12.428718411534142, 256: 16.52369969278014,
    275: 9.43817261904722, 277: 12.428718411534142, 280: 16.52369969278014,
    299: 14.72925170068034, 301: 14.729251700680338,
    304: 14.729251700680338, 323: 9.43817261904722,
    325: 12.428718411534142, 328: 16.52369969278014,
    347: 9.350793533127927, 349: 9.957930692114399, 352: 9.513531328320179,
    371: 24.112824675324664, 373: 22.895370758273927,
    376: 25.011421614100204, 395: 25.942989583333244,
    397: 25.942989583333244, 400: 25.942989583333244,
    419: 13.67070695970681, 421: 13.67070695970681, 424: 13.67070695970681,
    443: 24.278233564010364, 445: 24.278233564010364,
    448: 24.278233564010364, 467: 23.329857142856127,
    469: 23.329857142856127, 472: 23.329857142856127,
    491: 10.228178479701944, 493: 13.898128390596646,
    496: 21.784301859984257, 515: 5.096727819034635,
    517: 6.470116851873041, 520: 5.587932931893678, 539: 7.500000000000011,
    541: 7.500000000000011, 544: 7.5000000000000115,
    563: 7.499999999999432, 565: 7.499999999999432, 568: 7.499999999999432,
    587: 3.3496118012422706, 589: 2.0613989271598556,
    592: 4.766645962732927, 611: 9.828677083332801,
    613: 11.654630284256145, 616: 8.777451388888068, 635: 9.43817261904722,
    637: 12.428718411534142, 640: 16.52369969278014, 659: 9.43817261904722,
    661: 12.428718411534142, 664: 16.52369969278014,}

# ---- anchor / tier cell sets, keyed by
# ((symbol index * 24 + UTC hour) * 2 + side01),
# side01 = 0 buy / 1 sell, over DISC rows at the
# triple. ANCHOR_CELLS: the BROAD anchor
# (incumbent-kept UNION series-core round10/
# M5R10A01; 638 filed rows, 510 of them DISC, all at
# the triple) -- 56 cells. TIER_CELLS: the base
# ranking's
# f = 0.2 partial-anchor tier rows (138 filed rows)
# -- 21 cells.
ANCHOR_CELLS = frozenset({
    80, 81, 167, 218, 219, 266, 314, 315, 368, 369, 458, 459, 598, 599,
    694, 695, 698, 699, 746, 747, 752, 753, 800, 801, 843, 890, 891, 939,
    982, 983, 986, 987, 992, 993, 1030, 1031, 1034, 1035, 1040, 1041, 1088,
    1089, 1130, 1131, 1136, 1137, 1178, 1179, 1184, 1185, 1222, 1223, 1226,
    1227, 1232, 1233,})
TIER_CELLS = frozenset({
    80, 746, 747, 752, 753, 800, 801, 843, 890, 891, 939, 986, 987, 992,
    993, 1034, 1040, 1041, 1137, 1226, 1233,})


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
    (symbol, side) at a slot -- the r6r3 feature
    definitions. h1_closes: the last 13 H1 closes
    ending at the slot (or None); m15_closes: the
    last 8 M15 closes ending with the entry bar (or
    None); m5_bar: (o, h, l, c) of the M5 bar ending
    at the slot (or None). Undefined features take
    the filed neutral value 0.5 (the filings'
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
    (symbol index, side desc, distance asc). Each row:
    sym, side, mult, score (the filed sMC combination),
    exp (the fitted DISC (symbol x hour) expectancy),
    tier / anchored (the DISC-frozen cell-set flags),
    cell_key, entry_px, atr (pips), exit, net (exit/net
    None while unresolved in the available bars). A
    symbol contributes rows only when its M15 entry
    bar (the bar ending at T) and the 14-bar ATR
    window are available."""
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
        exp = CELL_EXP[(sidx * 24) + hour]
        for side in (1, -1):
            sH, sM, sF = _shape_scores(
                side, h1_closes, m15_closes, m5_bar, pip)
            score = W_SMC[0] * sH + W_SMC[1] * sM \
                + W_SMC[2] * sF
            side01 = 0 if side > 0 else 1
            ckey = ((sidx * 24 + hour) * 2) + side01
            for mi, m in enumerate(MULTS):
                dist = m * atr * pip
                xp, net = _trade_outcome(
                    bars, sym, T, side, dist, m, atr)
                rows.append({
                    "sym": sym, "side": side, "mult": m,
                    "cell_key": int(ckey),
                    "tier": ckey in TIER_CELLS,
                    "anchored": ckey in ANCHOR_CELLS,
                    "score": float(score),
                    "exp": float(exp),
                    "entry_px": entry_px, "atr": atr,
                    "exit": xp, "net": net,
                    "entry_s": int(T)})
    return rows


def _fill_key(rows, p):
    """The filed fill order: tier cells first by sMC
    descending, then the rest by fitted expectancy
    descending; the row's canonical position breaks
    ties (the filings break them by pool row index)."""
    r = rows[p]
    if r["tier"]:
        return (0, -r["score"], p)
    return (1, -r["exp"], p)


class AnchorState:
    """The M5R73A02 anchored multi-pick fill in live
    form. Slots are processed in chronological order.
    A kept pick whose exit is not yet resolvable from
    the available bars blocks its symbol until
    resolved (resolve_pending) -- the live form of
    the filed 1-open-per-symbol law, applied to
    first and second picks alike. At each slot the
    first pick is the best unblocked candidate under
    the filed fill order; the second pick is the
    best remaining candidate on a distinct, unblocked
    symbol whose cell is in the DISC-frozen BROAD
    anchor set."""

    def __init__(self):
        self.max_exit = {}
        self.picks = []
        self.ev = {e: {"slots_total": 0, "filled": 0,
                       "unfilled_zero_rows": 0,
                       "unfilled_all_blocked": 0,
                       "picks": 0, "second_picks": 0,
                       "second_eligible_slots": 0,
                       "second_rule_rejected": 0,
                       "second_none_available": 0}
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
                "exp": float(row["exp"]),
                "cell_key": int(row["cell_key"]),
                "tier": bool(row["tier"]),
                "anchored": bool(row["anchored"]),
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
        order (see _slot_rows). Returns the picked row
        indices: the first pick, plus -- when an
        anchored distinct-symbol candidate is
        available -- the anchored second pick (at most
        2 picks, the filed multi-pick law)."""
        e = self.ev[era]
        e["slots_total"] += 1
        if not rows:
            e["unfilled_zero_rows"] += 1
            return []
        order = sorted(range(len(rows)),
                       key=lambda p: _fill_key(rows, p))
        first = None
        for p in order:
            if self.max_exit.get(rows[p]["sym"], -1) > ts:
                continue
            first = p
            break
        if first is None:
            e["unfilled_all_blocked"] += 1
            return []
        e["filled"] += 1
        e["picks"] += 1
        self._record(rows[first], ts, "first")
        # SECOND pick: distinct symbol, unblocked,
        # anchored cell; the filed fill order governs.
        cands = [p for p in order
                 if p != first
                 and rows[p]["sym"] != rows[first]["sym"]
                 and self.max_exit.get(rows[p]["sym"], -1)
                 <= ts]
        if not cands:
            e["second_none_available"] += 1
            return [first]
        e["second_eligible_slots"] += 1
        for p in cands:
            if not rows[p]["anchored"]:
                continue
            e["second_picks"] += 1
            e["picks"] += 1
            self._record(rows[p], ts, "second")
            return [first, p]
        e["second_rule_rejected"] += 1
        return [first]


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
    """The slot stream settled through the M5R73A02
    anchored multi-pick fill. Persisted: the anchor
    state (blocking ledger, picks), the delivered
    ledger and the processed checks."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.anchor = AnchorState()
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
        if "anchor" in d:
            self.anchor.from_dict(d["anchor"])
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
                       "anchor": self.anchor.to_dict(),
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
            m15_frames = fetch_cycle85m_m15_frames()
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
        self.anchor.resolve_pending(m15_bars)
        era = "disc" if _dt.datetime.utcfromtimestamp(
            T).year <= 2023 else "audit"
        rows = _slot_rows(T, m15_bars, h1_bars, m5_bars)
        picks = self.anchor.process_slot(T, era, rows)
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


def is_cycle85m_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE85M_CHECK_HOURS and t.minute == 30


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
    """The delivered cycle85m stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle85m_m15_frames(state=None):
    from core.cycle89_best import fetch_cycle89_m15_frames
    return fetch_cycle89_m15_frames()


def evaluate_cycle85m_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle85m_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
