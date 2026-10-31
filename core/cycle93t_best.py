"""Cycle 93T -- November best, installed 2026-10-31 on the
user's conditional order (2026-10-31 ~23:09 MMT: "If R2D11
COMBO cycle pass validation, upload it to Git and replace
it with main cycle"). The form is the NOV40 relaxed
re-screen winner R2D11_COMBO, VALIDATED under the user's
relaxed standard in the campaign's final validation
(nov40/FINAL_VALIDATION_RESCREEN.md):

  the shipped November combined stream (cycle93r panel
  entries -- 93q chain + cycle93s fallback + the P-REPLACE
  C04 layer; the stream the research incumbent ledger was
  built against)
  + the B16_FMR_t30 candidate stream (F-MR level-1 leg,
    threshold 3.0 ATR, 10:00 UTC entries, 26 symbols --
    the incumbent 16:30 universe excluded: EURJPY, NZDCAD;
    template TP 0.8 x ATR14 / SL 7.3 x ATR14) merged
    incumbent-priority (merge_planB semantics)
  + the R2D11 state-conditional concurrency cap over the
    whole merged stream (PVOLSIZ weighting: a pick whose
    signal-bar atr_pct >= 2/3 counts 2; per-currency
    weighted limit 3 for a high-vol pick, 4 otherwise;
    weighted total limit 5).

It REPLACES the combined system: November's second-best
slot is emptied in the router (the cycle93s flow is
already inside this form; running 93s alongside would
double-fire).

Validated numbers (final validation, exact replay on the
campaign candle caches, @2.5): 810 picks; DISC leftover
77.05 -> 78.31, AUDIT leftover 43.44 -> 47.16 vs the
incumbent combined; LCT P 80.72% / q05 70.76 (passes the
frozen LCT-middle line as well as the relaxed 70 line);
section-9 Monte Carlo middle PASS (DD p95 248.17 vs the
incumbent's 251.99); EC22-middle 18/18 under both LCT
readings; DSR 1.0 / PBO 5.0% (family = incumbent + the six
re-screen forms); ES5 -66.48 -> -61.79 (beats risk-matched
thinning at the 92.5th percentile -- not thinning-
equivalent); the frozen Plan D tail arm still fails on
the single untouched worst run (-183.81), the binding
frozen failure for every re-screen form; validation
ceiling PROMISING-NEEDS-VALIDATION in frozen-program
terms (fresh forward = November 2026).

Check hours: the November combined grid (9, 10, 13, 15
UTC) -- identical to the pre-install combined grid, so
no signal/prep job retiming. Best N carried from
cycle93r: 83 (divided-by-3 sizing value 27.666... in the
router); the form's own sizing-grid pass is at N=100
(peak margin 60.24% and max DD 15.16% at N=83).

Implementation notes (faithfulness): the merge and the
cap are stream rules; they are applied here through a
persisted walk state in stream order, as the research
applied them over the merged ledger (a pick's merge/cap
fate depends only on earlier stream picks). Deterministic
stream order: within a check, accepted B16 candidates
settle through the cap before that check's incumbent
picks. Serialization note (install record,
nov40/INSTALL_R2D11.md): the research ledger's own
within-check order is a non-reproducible sort artifact of
the original run -- every code-form regeneration lands in
its documented equivalence class; this module's streaming
walk reproduces the form at 808 kept picks, DISC
leftover 78.20 (canonical serialization 78.31), AUDIT
leftover 47.16 and AUDIT net identical, 805/810 picks
identical to the canonical serialization, the residual
sitting at the documented tie-order binding moments.
Incumbent picks are enriched with H1-simulated exits
(sim_fixed_vec semantics, the app's canonical enrichment
of core.new8_candidate.MergedWalkState); atr_pct is the
campaign's expanding-percentile ATR rank (phase-0 /
build_cache convention), computed -- as in the campaign
-- on the windowed frame (Oct 20 - Dec 12 windows
concatenated), whatever the extent of the frame the app
hands the module.
The B16 merge is judged against the recorded stream
(MergedWalkState's recorded-rows convention); in the
validated data the merge dropped 0 of 35 candidate picks.
"""

from __future__ import annotations

import bisect
import json
import os

import numpy as np
import pandas as pd

import core.cycle93r_best as _c93r
from core.cycle93r_best import (evaluate_cycle93r_signals,
                                is_cycle93r_check_time,
                                select_cycle93r_entries)

SYSTEM_NAME = "cycle93t"
CYCLE93T_CHECK_HOURS = (9, 10, 13, 15)
MAX_HOLD = 48

SYMS = ['AUDCAD', 'AUDCHF', 'AUDJPY', 'AUDNZD', 'AUDUSD',
        'CADCHF', 'CADJPY', 'CHFJPY', 'EURAUD', 'EURCAD',
        'EURCHF', 'EURGBP', 'EURJPY', 'EURNZD', 'EURUSD',
        'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPJPY', 'GBPNZD',
        'GBPUSD', 'NZDCAD', 'NZDCHF', 'NZDJPY', 'NZDUSD',
        'USDCAD', 'USDCHF', 'USDJPY']
_B16_UNIVERSE = tuple(s for s in SYMS
                      if s not in ('EURJPY', 'NZDCAD'))
_B16_ENTRY_HOUR = 10
_B16_THR = 3.0
_B16_TP_ATR = 0.8
_B16_SL_ATR = 7.3
_B16_STRATEGY = "B16_FMR_t30"

_CAP_BASE_K = 4
_CAP_HIGH_K = 3
_CAP_TOTAL_K = 5
_HI_PCT = 2.0 / 3.0


def _pipsize(sym):
    return 0.01 if 'JPY' in sym else 0.0001


# ------------------------------------------------- features --
def _expanding_pct(a):
    """build_cache.expanding_pct verbatim: for each i, the
    share of a[:i] (non-NaN) strictly below a[i]."""
    seen = []
    out = np.full(len(a), np.nan)
    for i, v in enumerate(a):
        if np.isnan(v):
            continue
        if seen:
            out[i] = bisect.bisect_left(seen, v) / len(seen)
        bisect.insort(seen, v)
    return out


_FEAT_CACHE = {}


def _window_mask(idx):
    """The campaign frame convention (build_cache RANGES):
    bars inside [Oct 20, Dec 12) of each year."""
    mask = np.zeros(len(idx), bool)
    for y in range(idx[0].year, idx[-1].year + 1):
        mask |= (idx >= pd.Timestamp(f'{y}-10-20')) \
            & (idx < pd.Timestamp(f'{y}-12-12'))
    return mask


def _features(sym, fr):
    """Campaign (build_cache) feature arrays for one symbol:
    atr (pips), atr_pct, ema20dev_atr, rsi14 -- computed on
    the campaign's windowed frame (Oct 20 - Dec 12 windows
    concatenated, the frame the validated form was graded
    on) and scattered back onto the given frame's index
    (NaN outside the windows), cached per frame."""
    key = (sym, len(fr), str(fr.index[-1]))
    if key in _FEAT_CACHE:
        return _FEAT_CACHE[key]
    mask = _window_mask(fr.index)
    fr = fr[mask]
    ps = _pipsize(sym)
    c = fr['Close']
    hi, lo = fr['High'], fr['Low']
    tr = pd.concat([hi - lo, (hi - c.shift()).abs(),
                    (lo - c.shift()).abs()], axis=1).max(axis=1)
    atr_price = tr.ewm(alpha=1 / 14, adjust=False).mean()
    atr = (atr_price / ps).to_numpy()
    dd = c.diff()
    up = dd.clip(lower=0).ewm(alpha=1 / 14,
                              adjust=False).mean()
    dn = (-dd.clip(upper=0)).ewm(alpha=1 / 14,
                                 adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    rsi = rsi.where(dn > 0, 100.0).to_numpy()
    ema20 = c.ewm(span=20, adjust=False).mean()
    dev = ((c - ema20) / atr_price).to_numpy()
    win = dict(atr=atr, atr_pct=_expanding_pct(atr),
               ema20dev=dev, rsi=rsi)
    out = {}
    n = int(mask.sum())
    for k, v in win.items():
        full = np.full(len(mask), np.nan)
        full[mask] = v[:n]
        out[k] = full
    _FEAT_CACHE[key] = out
    return out


# ----------------------------------------------------- exits --
def _exit_for(sym, oc, entry_time, direction, tp_pips,
              sl_pips):
    """engine.simulate semantics on an ohlc dict (new8_walk
    .ohlc_from_frame shape): entry at the entry bar's open,
    bars entry..entry+47, SL-first; TIME exit at the close
    of bar entry+47 (gross rounded to 2dp, make_pick
    convention). Returns (gross_pips, exit_time, final) --
    final=False when the frame ends inside the window
    (provisional exit at the last available bar)."""
    ps = _pipsize(sym)
    pos = oc['pos_of'].get_indexer(
        [pd.Timestamp(entry_time)])[0]
    if pos < 0:
        return None
    o, h, l, c = oc['o'], oc['h'], oc['l'], oc['c']
    n = len(c)
    last = min(pos + MAX_HOLD, n)
    entry = float(o[pos])
    final = pos + MAX_HOLD - 1 < n
    sgn = 1 if direction == 'BUY' else -1
    for k in range(pos, last):
        if sgn > 0:
            if l[k] <= entry - sl_pips * ps:
                return -float(sl_pips), oc['dt'][k], final
            if h[k] >= entry + tp_pips * ps:
                return float(tp_pips), oc['dt'][k], final
        else:
            if h[k] >= entry + sl_pips * ps:
                return -float(sl_pips), oc['dt'][k], final
            if l[k] <= entry - tp_pips * ps:
                return float(tp_pips), oc['dt'][k], final
    k = last - 1
    gross = sgn * (float(c[k]) - entry) / ps
    return round(float(gross), 2), oc['dt'][k], final


# ----------------------------------------------------- state --
def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


class _FormState:
    """Persisted stream state for the 93t form: every
    incumbent pick recorded (enriched), every B16 candidate
    outcome, the cap's kept/deferred verdicts -- all in
    stream order."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.incumbent = []      # enriched incumbent picks
        self.b16_accepted = []   # B16 picks kept by the merge
        self.kept = []           # cap-kept picks (delivered)
        self.deferred = []       # cap-deferred picks
        self.processed = []      # check labels already stepped
        self._load()

    # ------------------------------------------------ persist --
    def _load(self):
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path) as fh:
                d = json.load(fh)
        except Exception:
            return

        def de(rows):
            out = []
            for r in rows:
                r = dict(r)
                for k in ('check', 'entry_time', 'exit_time'):
                    if r.get(k) is not None:
                        r[k] = pd.Timestamp(r[k])
                out.append(r)
            return out
        self.incumbent = de(d.get('incumbent', []))
        self.b16_accepted = de(d.get('b16_accepted', []))
        self.kept = de(d.get('kept', []))
        self.deferred = de(d.get('deferred', []))
        self.processed = list(d.get('processed', []))

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)

        def ser(rows):
            out = []
            for r in rows:
                d = dict(r)
                for k in ('check', 'entry_time', 'exit_time'):
                    if d.get(k) is not None:
                        d[k] = pd.Timestamp(d[k]).isoformat()
                out.append(d)
            return out
        data = dict(system=SYSTEM_NAME,
                    incumbent=ser(self.incumbent),
                    b16_accepted=ser(self.b16_accepted),
                    kept=ser(self.kept), deferred=ser(self.deferred),
                    processed=self.processed)
        with open(self.path, 'w') as fh:
            json.dump(data, fh)

    # ------------------------------------------------- enrich --
    def _enrich(self, row, ohlc, frames):
        """(Re)compute a recorded pick's exit + atr_pct from
        the frames at hand. Returns True when final."""
        oc = ohlc.get(row['symbol'])
        if oc is None:
            return False
        r = _exit_for(row['symbol'], oc, row['entry_time'],
                      row['direction'], row['tp_pips_used'],
                      row['sl_pips_used'])
        if r is None:
            return False
        gross, exit_t, final = r
        row['gross_pips'] = float(gross)
        row['exit_time'] = pd.Timestamp(exit_t)
        fr = frames.get(row['symbol'])
        if fr is not None and len(fr):
            f = _features(row['symbol'], fr)
            sig = oc['pos_of'].get_indexer(
                [pd.Timestamp(row['entry_time'])
                 - pd.Timedelta(hours=1)])[0]
            if sig >= 0:
                v = f['atr_pct'][sig]
                row['atr_pct'] = None if np.isnan(v) \
                    else float(v)
        return final

    def refresh(self, ohlc, frames):
        for row in self.incumbent + self.b16_accepted:
            if not row.get('exit_final'):
                if self._enrich(row, ohlc, frames):
                    row['exit_final'] = True

    # ---------------------------------------------------- cap --
    def _cap_admit(self, row):
        """cap_statecond verbatim rule for one stream pick
        (base_k=4, high_k=3, total_k=5, PVOLSIZ weighted)."""
        open_pos = []
        for k in self.kept:
            if pd.Timestamp(k['exit_time']) > \
                    pd.Timestamp(row['entry_time']):
                w = 2 if (k.get('atr_pct') is not None
                          and k['atr_pct'] >= _HI_PCT) else 1
                open_pos.append(
                    (pd.Timestamp(k['exit_time']),
                     {k['symbol'][:3], k['symbol'][3:]}, w))
        hi = row.get('atr_pct') is not None \
            and row['atr_pct'] >= _HI_PCT
        w = 2 if hi else 1
        lim = _CAP_HIGH_K if hi else _CAP_BASE_K
        cur = {row['symbol'][:3], row['symbol'][3:]}
        for ccy in cur:
            if sum(o[2] for o in open_pos if ccy in o[1]) + w \
                    > lim:
                return False
        if sum(o[2] for o in open_pos) + w > _CAP_TOTAL_K:
            return False
        return True

    def _cap_step(self, row):
        if self._cap_admit(row):
            self.kept.append(row)
        else:
            self.deferred.append(row)

    # ---------------------------------------------------- B16 --
    def _b16_candidates(self, ohlc, frames, entry_time):
        """B16_FMR_t30 candidate picks for one 10:00 UTC
        entry, in canonical symbol order."""
        out = []
        sig_time = entry_time - pd.Timedelta(hours=1)
        for sym in _B16_UNIVERSE:
            oc = ohlc.get(sym)
            fr = frames.get(sym)
            if oc is None or fr is None or not len(fr):
                continue
            sig = oc['pos_of'].get_indexer(
                [pd.Timestamp(sig_time)])[0]
            if sig < 0:
                continue
            f = _features(sym, fr)
            dev, rsi, atr = f['ema20dev'][sig], \
                f['rsi'][sig], f['atr'][sig]
            if np.isnan(dev) or np.isnan(atr) \
                    or abs(dev) < _B16_THR:
                continue
            if dev > 0 and rsi > 75:
                continue
            if dev < 0 and rsi < 25:
                continue
            direction = 'SELL' if dev > 0 else 'BUY'
            r = _exit_for(sym, oc, entry_time, direction,
                          _B16_TP_ATR * atr, _B16_SL_ATR * atr)
            if r is None:
                continue
            gross, exit_t, final = r
            out.append(dict(
                check=entry_time + pd.Timedelta(minutes=30),
                entry_time=pd.Timestamp(entry_time),
                exit_time=pd.Timestamp(exit_t),
                symbol=sym, direction=direction,
                strategy=_B16_STRATEGY,
                entry_px=float(oc['o'][oc['pos_of']
                                       .get_indexer(
                                           [pd.Timestamp(
                                               entry_time)])[0]]),
                tp_pips_used=float(_B16_TP_ATR * atr),
                sl_pips_used=float(_B16_SL_ATR * atr),
                gross_pips=float(gross),
                atr_pct=None if np.isnan(f['atr_pct'][sig])
                else float(f['atr_pct'][sig]),
                exit_final=bool(final)))
        return out

    def _merge_b16(self, cand):
        """merge_planB verbatim rule vs the recorded stream:
        a candidate is accepted iff its symbol is not open
        from ANY incumbent position at entry and not open
        from an accepted candidate; at most one candidate
        pick per symbol per check."""
        def overlaps(rows, e, x):
            for r in rows:
                if pd.Timestamp(r['entry_time']) < x and \
                        e < pd.Timestamp(r['exit_time']):
                    return True
            return False
        inc_sym = {}
        for r in self.incumbent:
            inc_sym.setdefault(r['symbol'], []).append(r)
        acc_sym = {}
        for r in self.b16_accepted:
            acc_sym.setdefault(r['symbol'], []).append(r)
        seen = set()
        for r in cand:
            key = (r['symbol'], pd.Timestamp(r['check']))
            if key in seen:
                continue
            if overlaps(inc_sym.get(r['symbol'], []),
                        pd.Timestamp(r['entry_time']),
                        pd.Timestamp(r['exit_time'])):
                continue
            if overlaps(acc_sym.get(r['symbol'], []),
                        pd.Timestamp(r['entry_time']),
                        pd.Timestamp(r['exit_time'])):
                continue
            seen.add(key)
            self.b16_accepted.append(r)
            acc_sym.setdefault(r['symbol'], []).append(r)
            self._cap_step(r)

    # ---------------------------------------------------- step --
    def step(self, ohlc, frames, check, inc_entries):
        """Process one check in stream order. inc_entries:
        the cycle93r panel entries DataFrame for this check
        (the shipped combined stream). Returns the kept
        picks recorded for this check."""
        chk = pd.Timestamp(check)
        if chk.isoformat() in self.processed:
            return [r for r in self.kept
                    if pd.Timestamp(r['check']) == chk]
        self.refresh(ohlc, frames)
        new_inc = []
        have = {(pd.Timestamp(r['check']), r['symbol'],
                 r['strategy']) for r in self.incumbent}
        if inc_entries is not None:
            for _, e in inc_entries.iterrows():
                key = (chk, str(e['symbol']),
                       str(e.get('equation',
                                 e.get('strategy', ''))))
                if key in have:
                    continue
                ent = chk - pd.Timedelta(minutes=30)
                row = dict(
                    check=chk, entry_time=ent,
                    symbol=str(e['symbol']),
                    direction=str(e['direction']),
                    strategy=str(e.get('equation',
                                       e.get('strategy', ''))),
                    entry_px=float(e['entry_px']),
                    tp_pips_used=float(e['tp_pips']),
                    sl_pips_used=float(e['sl_pips']),
                    exit_time=ent + pd.Timedelta(
                        hours=MAX_HOLD),
                    gross_pips=None, atr_pct=None,
                    exit_final=False)
                if self._enrich(row, ohlc, frames):
                    row['exit_final'] = True
                self.incumbent.append(row)
                have.add(key)
                new_inc.append(row)
        if chk.hour == _B16_ENTRY_HOUR and chk.minute == 30:
            entry_time = chk - pd.Timedelta(minutes=30)
            self._merge_b16(self._b16_candidates(
                ohlc, frames, entry_time))
        for row in new_inc:
            self._cap_step(row)
        self.processed.append(chk.isoformat())
        self.save()
        return [r for r in self.kept
                if pd.Timestamp(r['check']) == chk]


def _load_form_state():
    return _FormState()


def reset_form_state():
    """Remove the persisted 93t stream state (gate use)."""
    p = _state_path()
    if os.path.exists(p):
        os.remove(p)


def walk_ledger():
    """The cap-kept picks recorded by the form's state, as
    a research-ledger DataFrame (gate/verification use)."""
    st = _FormState()
    rows = [dict(check=r['check'], symbol=r['symbol'],
                 direction=r['direction'],
                 strategy=r['strategy'],
                 entry_time=r['entry_time'],
                 exit_time=r['exit_time'],
                 gross_pips=r['gross_pips'])
            for r in st.kept]
    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values('check').reset_index(drop=True)
    return df


# -------------------------------------------------- panel API --
def evaluate_cycle93t_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the cycle93r chain (the merged form
    is produced by panel_entries)."""
    return evaluate_cycle93r_signals(frames, check_time_utc,
                                     m15_frames=m15_frames)


def select_cycle93t_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    return select_cycle93r_entries(signals,
                                   open_symbols=open_symbols)


def is_cycle93t_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE93T_CHECK_HOURS and t.minute == 30


def _signal_row(r):
    return {"check": pd.Timestamp(r['check']),
            "symbol": r['symbol'],
            "equation": r['strategy'],
            "direction": r['direction'],
            "score": float('nan'),
            "entry_px": float(r['entry_px']),
            "tp_pips": float(r['tp_pips_used']),
            "sl_pips": float(r['sl_pips_used']),
            "signal_candle": pd.Timestamp(r['check'])
            - pd.Timedelta(hours=1, minutes=30),
            "entry_candle": pd.Timestamp(r['entry_time'])}


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full form entries for one check: the shipped
    November combined stream (cycle93r panel) plus the
    B16 merge, settled through the state-conditional cap
    -- only cap-kept picks are delivered."""
    from core.new8_features import frame_to_research
    from core.new8_walk import ohlc_from_frame
    entries = _c93r.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    ohlc = {}
    for sym, fr in frames.items():
        if fr is not None and len(fr):
            try:
                rfr, _ = frame_to_research(fr)
                ohlc[sym] = ohlc_from_frame(rfr)
            except Exception:
                pass
    st = _load_form_state()
    kept = st.step(ohlc, frames, check_time_utc, entries)
    if not kept:
        return pd.DataFrame()
    return pd.DataFrame([_signal_row(r) for r in kept])
