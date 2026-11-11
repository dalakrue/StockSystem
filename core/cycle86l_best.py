"""Cycle 86L -- March: the stored R100A06 kept set
(the original programme's round-100 design C06, filed
in the M5 validation series identically as M5R11A01
at Round 11 and M5R50A01 at Round 50) written as a
live rule.

PROVENANCE. The design is March's standing fill: the
plain sMC-ranked per-slot fill over March's stored
pool at the registered triple, filed in
fx_research/m5_validation_series/round11 and round50
(VERDICT_MAR / grade_mar.json; machinery
round50/work/new_levers_r50.py.txt `_penalty_family50`
score[0], the standing CONTROL, and
round50/work/m5r50_engine.py `fill_family`). The
family's other nine filed variants (the R18
centre-side negative-expectancy penalty class:
demotion ladders on the sMC order, expectancy orders,
blends) all produce this one identical mask for
March -- reach 0 at every strength, filed R17/R18
and re-filed at the R50 freeze ("Mar's ranking space
at its triple is a single point under every
instrument filed", GATES_R50) -- and the Round 112
assembly confirmed a single distinct column across
all 690 March designs graded in the series. Filed
record: DISC kept 419, win 93.79%, net +3,575.62,
leftover 64.77%, daily Sharpe 14.453; AUDIT kept 96,
win 89.58%, net +368.07, leftover 34.39%; Monte
Carlo section 9 MIDDLE PASS; red DISC weeks 2; EC22
failed set {13_lct, 14_leftover, 20_dsr} with DSR
0.000. VALIDATED at Round 112 under the user's SPA
substitution order of 2026-11-11 (Hansen SPA
t 12.362, consistent p = 0.0000), where the failed
set's only remaining member was the replaced
check 20. Sizing was NOT graded in the series and
this module carries no Best-N constant.

THE RULE (what this module computes at a check
slot). Check slots are the March slots UTC
(11, 16, 17) = 17:30 / 22:30 / 23:30 MMT, March
weekdays only (the app routes month 3 here). At a
slot the module builds candidate trades from the
candles for every one of the 28 symbols: entry at
the close of the M15 bar ending at the slot; M15
ATR14 sets the distance ladder {0.5, 0.75, 1.0, 1.5}
x ATR for SL and TP (RR 1:1); exit by the locked
replay (SL-first in one bar, 48h cap). Each candidate
(a symbol x side x distance-step triple) carries one
filed quantity, fitted on DISC 2016-2023 only and
shipped below as data:

  sMC = 0.25 * sH + 0.25 * sM + 0.50 * sF -- the
  filed pool score over the entry bar's candle
  features: sH = clip(0.5 + side * H1drift /
  (2 * qH), 0, 1) with H1drift the 12-bar H1 drift
  in pips and qH = 38.18 pips; sM the same form over
  the M15 8-bar deviation with qM = 10.75 pips; sF
  the last M5 bar's side-oriented shape
  (0.5 * loc + 0.25 + 0.25 * side * bodyr);
  undefined features take the filed neutral 0.5.

THE FILL (the filed order, in live form). Candidates
are ordered by sMC descending; ties by the canonical
order (symbol, side desc, step asc) -- the filed
ranking is distance-blind (sMC carries no distance
input), so within one (symbol, side) the canonical
order selects the 0.5 x ATR step. THE PICK: the
first candidate in that order whose symbol is not
blocked by a still-open kept trade -- exactly one
pick per slot (the standing fill predates the
multi-pick amendment and carries none: the filed
fill evidence is 515 rank-1 picks and 0 second-best
picks across both eras, and no slot in the frame was
ever left unfilled by blocking). A kept pick
blocks its symbol until its candle-replayed exit
(1-open-per-symbol); an exit exactly at a slot
leaves the symbol free at that slot, as filed.

TRANSLATIONS (full list in PROVENANCE_MAR.md). The
filed construction selects among stored-pool rows;
this module generates candidates from candles (the
R86 mined-universe generator form, as in the
November and February ports) and exits them by
their own ATR-step band instead of the pool's filed
exits. The kept set's own row-level identity -- WHICH
515 historical rows the set holds -- is
timestamp-keyed and has no live form; it is omitted,
as the headline disclosure. The family's penalty
variants are omitted with it: their measured effect
on the filed mask is zero at every strength, so any
live demotion would be unfiled machinery. The filed
fill's condition-met threshold (the median sMC over
incumbent-kept DISC rows) is evidence bookkeeping in
the filings only; it never gates a pick and is not
carried as a rule.

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

SYSTEM_NAME = "cycle86l"
CYCLE86L_CHECK_HOURS = (11, 16, 17)
SURFACE_GRID = (11, 16, 17)
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

# ---- fitted constants (provenance: PROVENANCE_MAR.md
# in the port folder; readable copy constants_mar.json).
# W_SMC: the filed pool-score weights (SMC =
# (0.25, 0.25, 0.50)); QH_P80 / QM_P80: the 0.80
# quantiles of |H1 drift| and |M15 deviation| (pips)
# over the incumbent-kept DISC rows of March's stored
# pool (round6_r3 features scales, frozen in
# features_r6r3_mar.npz). March ships NO expectancy
# table and NO cell sets: the design's ranking is the
# plain sMC order alone (see the docstring).
W_SMC = (0.25, 0.25, 0.50)
QH_P80 = 38.17999999999943
QM_P80 = 10.750000000000153


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
    entry_px, atr (pips), exit, net (exit/net None
    while unresolved in the available bars). A symbol
    contributes rows only when its M15 entry bar (the
    bar ending at T) and the 14-bar ATR window are
    available."""
    rows = []
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
        for side in (1, -1):
            sH, sM, sF = _shape_scores(
                side, h1_closes, m15_closes, m5_bar, pip)
            score = W_SMC[0] * sH + W_SMC[1] * sM \
                + W_SMC[2] * sF
            for mi, m in enumerate(MULTS):
                dist = m * atr * pip
                xp, net = _trade_outcome(
                    bars, sym, T, side, dist, m, atr)
                rows.append({
                    "sym": sym, "side": side, "mult": m,
                    "score": float(score),
                    "entry_px": entry_px, "atr": atr,
                    "exit": xp, "net": net,
                    "entry_s": int(T)})
    return rows


def _fill_key(rows, p):
    """The filed fill order: sMC descending; the row's
    canonical position breaks ties (the filings break
    them by pool row index)."""
    return (-rows[p]["score"], p)


class FillState:
    """The R100A06 standing fill in live form. Slots
    are processed in chronological order. A kept pick
    whose exit is not yet resolvable from the
    available bars blocks its symbol until resolved
    (resolve_pending) -- the live form of the filed
    1-open-per-symbol law. At each slot the pick is
    the best unblocked candidate under the filed fill
    order (at most 1 pick per slot, as filed)."""

    def __init__(self):
        self.max_exit = {}
        self.picks = []
        self.ev = {e: {"slots_total": 0, "filled": 0,
                       "unfilled_zero_rows": 0,
                       "unfilled_all_blocked": 0,
                       "picks": 0}
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
    def _record(self, row, ts):
        pick = {"sym": row["sym"], "entry_s": int(ts),
                "side": int(row["side"]),
                "mult": float(row["mult"]),
                "entry_px": float(row["entry_px"]),
                "atr": float(row["atr"]),
                "score": float(row["score"]),
                "layer": "first",
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
        index list: the single best unblocked candidate
        under the filed fill order, or empty."""
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
        self._record(rows[first], ts)
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
    """The slot stream settled through the R100A06
    standing fill. Persisted: the fill state (blocking
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
        T -= T % 3600  # entries fire at H:00 UTC; the H:30
        # stamp is the evaluation label
        if m15_frames is None:
            m15_frames = fetch_cycle86l_m15_frames()
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
        self.fill.resolve_pending(m15_bars)
        era = "disc" if _dt.datetime.utcfromtimestamp(
            T).year <= 2023 else "audit"
        rows = _slot_rows(T, m15_bars, h1_bars, m5_bars)
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
                  "layer": "first",
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


def is_cycle86l_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE86L_CHECK_HOURS and t.minute == 30


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
    """The delivered cycle86l stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle86l_m15_frames(state=None):
    from core.cycle89_best import fetch_cycle89_m15_frames
    return fetch_cycle89_m15_frames()


def evaluate_cycle86l_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle86l_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
