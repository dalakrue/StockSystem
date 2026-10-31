"""Cycle 94F -- December best, installed 2026-11-01 on the
user's standing conditional order (2026-11-01 ~00:36 MMT:
"For that risk-improve-acceptable, if validation pass
replace it with main system and upload it"). The form is
the RISK6 December champion C15_FCAP_MERGED, VALIDATED
under the user's relaxed re-screen standard in the final
validation (work_risk6/dec/FINAL_VALIDATION.md):

  the shipped December best stream (cycle94e module-form
  stream, 913 picks)
  + a curated partner layer: 18 frozen surgery designs
    (RSIVOL / MOMVOL / MOM4VOL / EMADEV families on
    GBPCHF / CADCHF / EURJPY / CADJPY / EURUSD / AUDJPY /
    AUDCHF at entry hours 10 / 11 / 13 / 14 UTC), generated
    standalone and merged with merge_partner semantics
    (a partner pick is accepted iff its check is not
    occupied by the base stream or an accepted partner
    and its interval overlaps no base or accepted pick
    on its symbol; designs settle in the frozen
    discovery-leftover order) -- 32 accepted picks,
  -> the high-vol filter: EURJPY / EURUSD picks whose
    signal-bar atr_pct >= 2/3 are dropped,
  -> the R2D11 state-conditional cap over the whole
    stream (PVOLSIZ weighting: atr_pct >= 2/3 counts 2;
    per-currency weighted limit 3 for a high-vol pick,
    4 otherwise; weighted total limit 5).

Validated numbers (final validation, exact replay over
the campaign caches, @2.5): 891 picks; DISC leftover
81.19 -> 82.91, AUDIT leftover 57.96 -> 60.49 vs the
incumbent; LCT P 88.12% / q05 79.22 (passes the frozen
LCT-middle line as well as the relaxed 70 line);
EC22-middle 18/18 under both LCT readings; section-9
Monte Carlo middle PASS (DD p95 188.20 vs the
incumbent's 239.00); DSR 1.0 / PBO 0.0% (family-42);
ES5 -48.24 -> -43.21 (beats the risk-matched thinning
p90 -- not thinning-equivalent); worst run -120.09
unchanged (the 2019-12-19 EURUSD+EURJPY pair survives
every December form on record); decay PASS; sizing grid
pass at N=100; at the carried N=105 peak margin 57.13%
(incumbent 65.30%), max DD 4.81% (incumbent 6.56%).
Validation ceiling PROMISING-NEEDS-VALIDATION in
frozen-program terms (fresh forward = December 2026).

Registry shape: a LAYER on cycle94e, per the cycle93t
precedent -- 94f replaces 94e as December's best and
carries the partner/filter/cap layer inside this
module; December's second-best STAYS cycle94s: this
form is built on the best's stream alone (the 94s flow
was never part of the graded stream), and the combined
layer only evaluates 94s when the best is silent at a
check, so the kept second-best cannot double-fire.

Check hours: the form's stream spans entry hours
(10, 11, 13, 14) UTC, exactly the pre-install combined
December grid -- best checks 16:30 / 17:30 / 19:30 MMT
plus the 20:30 MMT combined slot. No signal/prep job
retiming. Best N carried from cycle94e: 105
(divided-by-3 sizing value 35.0 in the router).

Implementation notes (faithfulness): the merge, filter
and cap are stream rules, applied through a persisted
walk state in stream order (per check: the incumbent
rows first, in panel order, then the check's partner
candidates in frozen design order). The final
validation proved the check-major streaming order
reproduces the research's design-major curation EXACTLY
on the full graded history (merged stream 945/945,
capped form 891/891 canon-identical) -- the curated
designs sit in thin/never-traded cells, so no
order-sensitive binding moment occurs. Features are
the Dec campaign cache definitions (build_cache_dec)
computed on the campaign's windowed frame (Nov 18 -
Jan 14 windows concatenated): atr / atr_pct (expanding
percentile) / mom4 / mom24 / rsi14 / vol24 / ema20dev as
arrays; volz and m15volz evaluated on demand at the
signal bar with the cache's verbatim trailing-168
formula. Incumbent picks are enriched with H1-simulated
exits on the windowed frame (mine_lib.simulate
semantics: entry at the entry bar's open, bars
entry..entry+47, SL-first) and the cache atr_pct at the
signal bar. Legacy DOLLARIDX rows of the shipped 94e
ledger carry the research fallback (atr_pct 0.0 -- never
filtered, never high-vol-weighted); they stay silent
live, as they do under 94e today.
"""

from __future__ import annotations

import bisect
import json
import os

import numpy as np
import pandas as pd

import core.cycle94e_best as _c94e
from core.cycle94e_best import (evaluate_cycle94e_signals,
                                fetch_cycle94e_m15_frames,
                                is_cycle94e_check_time,
                                select_cycle94e_entries)
from core.new8_candidate import (default_state_path,
                                 ensure_m15)

SYSTEM_NAME = "cycle94f"
CYCLE94F_CHECK_HOURS = (10, 11, 13, 14)
MAX_HOLD = 48

# The frozen curated partner designs, in the curation's
# discovery-leftover order: (family, threshold, symbol,
# entry hour UTC, TP x ATR, SL x ATR).
DESIGNS = (
    ('RSIVOL', 30.0, 'GBPCHF', 14, 0.85, 8.0),
    ('RSIVOL', 30.0, 'CADCHF', 14, 1.25, 5.0),
    ('RSIVOL', 30.0, 'EURJPY', 11, 0.85, 8.0),
    ('RSIVOL', 30.0, 'CADJPY', 11, 0.85, 8.0),
    ('RSIVOL', 35.0, 'CADCHF', 11, 1.25, 5.0),
    ('RSIVOL', 30.0, 'EURUSD', 13, 0.85, 8.0),
    ('RSIVOL', 30.0, 'EURJPY', 10, 0.85, 8.0),
    ('MOM4VOL', 1.75, 'GBPCHF', 11, 0.85, 8.0),
    ('EMADEV', 1.5, 'CADCHF', 11, 0.85, 8.0),
    ('RSIVOL', 35.0, 'GBPCHF', 11, 1.25, 5.0),
    ('RSIVOL', 35.0, 'CADCHF', 11, 0.85, 8.0),
    ('RSIVOL', 30.0, 'CADCHF', 11, 0.85, 8.0),
    ('MOMVOL', 2.0, 'AUDJPY', 10, 0.85, 8.0),
    ('RSIVOL', 35.0, 'GBPCHF', 11, 0.85, 8.0),
    ('RSIVOL', 35.0, 'CADCHF', 10, 0.85, 8.0),
    ('MOM4VOL', 1.75, 'CADCHF', 11, 0.85, 8.0),
    ('EMADEV', 1.5, 'GBPCHF', 11, 0.85, 8.0),
    ('RSIVOL', 35.0, 'AUDCHF', 11, 0.85, 8.0),
)
_DESIGN_SYMBOLS = tuple(sorted({d[2] for d in DESIGNS}))
_DESIGN_HOURS = tuple(sorted({d[3] for d in DESIGNS}))

_FILTER_SYMS = ('EURJPY', 'EURUSD')
_HI_PCT = 2.0 / 3.0
_CAP_BASE_K = 4
_CAP_HIGH_K = 3
_CAP_TOTAL_K = 5


def _pipsize(sym):
    return 0.01 if 'JPY' in sym else 0.0001


def _strategy_name(fam, thr, sym, hour, tp_m, sl_m):
    return f'R6_{fam}_t{thr}_{sym}_h{hour}_{tp_m}x{sl_m}'


# ------------------------------------------------- features --
def _expanding_pct(a):
    """build_cache_dec.expanding_pct verbatim: for each i,
    the share of a[:i] (non-NaN) strictly below a[i]."""
    seen = []
    out = np.full(len(a), np.nan)
    for i, v in enumerate(a):
        if np.isnan(v):
            continue
        if seen:
            out[i] = bisect.bisect_left(seen, v) / len(seen)
        bisect.insort(seen, v)
    return out


def _window_mask(idx):
    """The Dec campaign frame convention (build_cache_dec
    RANGES): bars inside [Nov 18, Jan 14) of each
    year-pair."""
    mask = np.zeros(len(idx), bool)
    for y in range(idx[0].year - 1, idx[-1].year + 1):
        mask |= (idx >= pd.Timestamp(f'{y}-11-18')) \
            & (idx < pd.Timestamp(f'{y + 1}-01-14'))
    return mask


def _volz_at(lv, i):
    """build_cache_dec.volz_series value at bar i,
    evaluated on demand: z of lv[i] vs lv[i-168:i];
    0.0 when i < 169 or the window is degenerate."""
    if i < 169:
        return 0.0
    w = lv[i - 168:i]
    sd = w.std(ddof=1)
    if sd > 0:
        return float((lv[i] - w.mean()) / sd)
    return 0.0


_CTX_CACHE = {}


def _win_ctx(sym, fr, m15fr=None):
    """Campaign (build_cache_dec) windowed context for one
    symbol: windowed H1 arrays + features, and the
    windowed M15 log-volume array for m15volz. Cached per
    frame extent."""
    key = (sym, len(fr), str(fr.index[-1]),
           0 if m15fr is None else len(m15fr),
           '' if m15fr is None else str(m15fr.index[-1]))
    if key in _CTX_CACHE:
        return _CTX_CACHE[key]
    mask = _window_mask(fr.index)
    w = fr[mask]
    ps = _pipsize(sym)
    c = w['Close']
    hi, lo = w['High'], w['Low']
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
    lv = np.log1p(w['Volume'].where(w['Volume'] > 0)) \
        .to_numpy(dtype=float)
    ctx = dict(
        idx=w.index,
        pos={t: i for i, t in enumerate(w.index)},
        o=w['Open'].to_numpy(dtype=float),
        h=hi.to_numpy(dtype=float),
        l=lo.to_numpy(dtype=float),
        c=c.to_numpy(dtype=float),
        atr=atr, atr_pct=_expanding_pct(atr),
        mom4=(c - c.shift(4)).div(atr_price).to_numpy(),
        mom24=(c - c.shift(24)).div(atr_price).to_numpy(),
        rsi=rsi,
        vol24=dd.rolling(24).std(ddof=1).div(atr_price)
        .to_numpy(),
        ema20dev=(c - ema20).div(atr_price).to_numpy(),
        lv=lv)
    if m15fr is not None and len(m15fr):
        mmask = _window_mask(m15fr.index)
        mw = m15fr[mmask]
        ctx['m15_idx'] = mw.index
        ctx['m15_pos'] = {t: i for i, t in enumerate(mw.index)}
        ctx['m15_lv'] = np.log1p(
            mw['Volume'].where(mw['Volume'] > 0)) \
            .to_numpy(dtype=float)
    _CTX_CACHE[key] = ctx
    return ctx


def _m15volz(ctx, sig_time):
    """build_cache_dec m15volz at the H1 signal bar: the
    M15 vol-z at the M15 bar starting 45 min after the
    signal bar's start (the M15 bar ending at the entry
    time); NaN when that bar is absent."""
    if 'm15_pos' not in ctx:
        return float('nan')
    p = ctx['m15_pos'].get(
        pd.Timestamp(sig_time) + pd.Timedelta(minutes=45))
    if p is None:
        return float('nan')
    return _volz_at(ctx['m15_lv'], p)


# ----------------------------------------------------- exits --
def _exit_for(ctx, entry_time, direction, tp_pips, sl_pips,
              sym):
    """mine_lib.simulate semantics on the windowed frame:
    entry at the entry bar's open, bars entry..entry+47,
    SL-first; TIME exit at the close of bar entry+47
    (gross rounded to 2dp). Returns (gross, exit_time,
    final) or None when the entry bar is absent."""
    pos = ctx['pos'].get(pd.Timestamp(entry_time))
    if pos is None:
        return None
    ps = _pipsize(sym)
    o, h, l, c = ctx['o'], ctx['h'], ctx['l'], ctx['c']
    idx = ctx['idx']
    n = len(c)
    last = min(pos + MAX_HOLD, n)
    entry = float(o[pos])
    final = pos + MAX_HOLD - 1 < n
    sgn = 1 if direction == 'BUY' else -1
    for k in range(pos, last):
        if sgn > 0:
            if l[k] <= entry - sl_pips * ps:
                return -float(sl_pips), idx[k], final
            if h[k] >= entry + tp_pips * ps:
                return float(tp_pips), idx[k], final
        else:
            if h[k] >= entry + sl_pips * ps:
                return -float(sl_pips), idx[k], final
            if l[k] <= entry - tp_pips * ps:
                return float(tp_pips), idx[k], final
    k = last - 1
    gross = sgn * (float(c[k]) - entry) / ps
    return round(float(gross), 2), idx[k], final


# ----------------------------------------------------- state --
def _state_path():
    return default_state_path(SYSTEM_NAME)


class _FormState:
    """Persisted stream state for the 94f form: every
    incumbent pick recorded (enriched), every partner
    outcome, the filter/cap kept and dropped verdicts --
    all in stream order."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.incumbent = []        # enriched incumbent picks
        self.partner_accepted = []  # partner picks kept by merge
        self.kept = []             # filter+cap-kept (delivered)
        self.dropped = []          # filtered out or cap-deferred
        self.processed = []        # check labels already stepped
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
        self.partner_accepted = de(d.get('partner_accepted',
                                         []))
        self.kept = de(d.get('kept', []))
        self.dropped = de(d.get('dropped', []))
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
                    partner_accepted=ser(self.partner_accepted),
                    kept=ser(self.kept),
                    dropped=ser(self.dropped),
                    processed=self.processed)
        with open(self.path, 'w') as fh:
            json.dump(data, fh)

    # ------------------------------------------------- enrich --
    def _enrich(self, row, ctxs):
        """(Re)compute a recorded pick's exit + atr_pct
        from the frames at hand. Returns True when final.
        Rows whose symbol has no frame (legacy DOLLARIDX)
        keep the research fallback: atr_pct None (-> 0.0
        in every comparison) and the +48h placeholder
        exit."""
        ctx = ctxs.get(row['symbol'])
        if ctx is None:
            return False
        r = _exit_for(ctx, row['entry_time'], row['direction'],
                      row['tp_pips_used'], row['sl_pips_used'],
                      row['symbol'])
        if r is None:
            return False
        gross, exit_t, final = r
        row['gross_pips'] = float(gross)
        row['exit_time'] = pd.Timestamp(exit_t)
        sig = ctx['pos'].get(pd.Timestamp(row['entry_time'])
                             - pd.Timedelta(hours=1))
        if sig is not None:
            v = ctx['atr_pct'][sig]
            row['atr_pct'] = None if np.isnan(v) else float(v)
        return final

    def refresh(self, ctxs):
        for row in self.incumbent + self.partner_accepted:
            if not row.get('exit_final'):
                if self._enrich(row, ctxs):
                    row['exit_final'] = True

    # --------------------------------------------- filter+cap --
    def _hi(self, row):
        return row.get('atr_pct') is not None \
            and row['atr_pct'] >= _HI_PCT

    def _cap_admit(self, row):
        """apply_cap verbatim rule (total_k=5, weighted,
        statecond): PVOLSIZ weight 2 for high-vol picks;
        per-currency weighted limit 3 for a high-vol
        pick, 4 otherwise; weighted total limit 5."""
        open_pos = []
        for k in self.kept:
            if pd.Timestamp(k['exit_time']) > \
                    pd.Timestamp(row['entry_time']):
                w = 2 if self._hi(k) else 1
                open_pos.append(
                    (pd.Timestamp(k['exit_time']),
                     {k['symbol'][:3], k['symbol'][3:]}, w))
        hi = self._hi(row)
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

    def _settle(self, row):
        """The FCAP layer for one merged-stream pick: the
        high-vol EURJPY/EURUSD filter first, then the
        cap."""
        if row['symbol'] in _FILTER_SYMS and self._hi(row):
            row['drop_reason'] = 'filter'
            self.dropped.append(row)
            return
        if self._cap_admit(row):
            self.kept.append(row)
        else:
            row['drop_reason'] = 'cap'
            self.dropped.append(row)

    # ------------------------------------------------ partners --
    def _design_candidates(self, ctxs, entry_time):
        """Standalone candidate picks of the frozen
        designs for one entry time, in frozen design
        order (mine_lib.gen_picks semantics per design:
        signal bar = the H1 bar ending at entry)."""
        out = []
        if entry_time.month != 12:
            return out
        sig_time = entry_time - pd.Timedelta(hours=1)
        for fam, thr, sym, hour, tp_m, sl_m in DESIGNS:
            if hour != entry_time.hour:
                continue
            ctx = ctxs.get(sym)
            if ctx is None:
                continue
            sig = ctx['pos'].get(pd.Timestamp(sig_time))
            ent = ctx['pos'].get(pd.Timestamp(entry_time))
            if sig is None or ent is None:
                continue
            atr = ctx['atr'][sig]
            mom4 = ctx['mom4'][sig]
            mom24 = ctx['mom24'][sig]
            rsi = ctx['rsi'][sig]
            if any(np.isnan(v) for v in (atr, mom4, mom24,
                                         rsi)):
                continue
            direction = 0
            if fam == 'MOMVOL':
                if abs(mom24) >= thr \
                        and _volz_at(ctx['lv'], sig) >= -0.5:
                    direction = 1 if mom24 > 0 else -1
            elif fam == 'RSIVOL':
                mv = _m15volz(ctx, sig_time)
                if rsi <= thr and mv >= -0.5:
                    direction = 1
                elif rsi >= 100 - thr and mv >= -0.5:
                    direction = -1
            elif fam == 'EMADEV':
                dev = ctx['ema20dev'][sig]
                if abs(dev) >= thr \
                        and ctx['vol24'][sig] <= 1.2:
                    direction = 1 if dev > 0 else -1
            elif fam == 'MOM4VOL':
                if abs(mom4) >= thr \
                        and _volz_at(ctx['lv'], sig) >= 0.0:
                    direction = 1 if mom4 > 0 else -1
            if direction == 0 or np.isnan(atr) or atr <= 0:
                continue
            tp = round(tp_m * atr, 2)
            sl = round(min(sl_m * atr, 100.0), 2)
            dname = 'BUY' if direction > 0 else 'SELL'
            r = _exit_for(ctx, entry_time, dname, tp, sl, sym)
            if r is None:
                continue
            gross, exit_t, final = r
            ap = ctx['atr_pct'][sig]
            out.append(dict(
                check=entry_time + pd.Timedelta(minutes=30),
                entry_time=pd.Timestamp(entry_time),
                exit_time=pd.Timestamp(exit_t),
                symbol=sym, direction=dname,
                strategy=_strategy_name(fam, thr, sym, hour,
                                        tp_m, sl_m),
                entry_px=float(ctx['o'][ent]),
                tp_pips_used=float(tp),
                sl_pips_used=float(sl),
                gross_pips=float(gross),
                atr_pct=None if np.isnan(ap) else float(ap),
                exit_final=bool(final)))
        return out

    def _merge_partners(self, cand):
        """merge_partner verbatim rule vs the recorded
        stream: a candidate is accepted iff its check is
        occupied by no incumbent pick and no accepted
        partner, and its interval overlaps no incumbent
        or accepted pick on its symbol."""
        def overlaps(rows, e, x):
            for r in rows:
                if pd.Timestamp(r['entry_time']) < x and \
                        e < pd.Timestamp(r['exit_time']):
                    return True
            return False
        inc_checks = {pd.Timestamp(r['check'])
                      for r in self.incumbent}
        inc_sym = {}
        for r in self.incumbent:
            inc_sym.setdefault(r['symbol'], []).append(r)
        acc_sym = {}
        for r in self.partner_accepted:
            acc_sym.setdefault(r['symbol'], []).append(r)
        acc_checks = {pd.Timestamp(r['check'])
                      for r in self.partner_accepted}
        accepted = []
        for r in cand:
            chk = pd.Timestamp(r['check'])
            if chk in inc_checks or chk in acc_checks:
                continue
            if overlaps(inc_sym.get(r['symbol'], []),
                        pd.Timestamp(r['entry_time']),
                        pd.Timestamp(r['exit_time'])):
                continue
            if overlaps(acc_sym.get(r['symbol'], []),
                        pd.Timestamp(r['entry_time']),
                        pd.Timestamp(r['exit_time'])):
                continue
            self.partner_accepted.append(r)
            acc_sym.setdefault(r['symbol'], []).append(r)
            acc_checks.add(chk)
            accepted.append(r)
        return accepted

    # ---------------------------------------------------- step --
    def step(self, ctxs, check, inc_entries):
        """Process one check in stream order. inc_entries:
        the cycle94e panel entries DataFrame for this
        check (the shipped best stream). Returns the kept
        picks recorded for this check."""
        chk = pd.Timestamp(check)
        if chk.isoformat() in self.processed:
            return [r for r in self.kept
                    if pd.Timestamp(r['check']) == chk]
        self.refresh(ctxs)
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
                if self._enrich(row, ctxs):
                    row['exit_final'] = True
                self.incumbent.append(row)
                have.add(key)
                new_inc.append(row)
        accepted = []
        if chk.minute == 30 \
                and (chk - pd.Timedelta(minutes=30)).hour \
                in _DESIGN_HOURS:
            entry_time = chk - pd.Timedelta(minutes=30)
            accepted = self._merge_partners(
                self._design_candidates(ctxs, entry_time))
        for row in new_inc:
            self._settle(row)
        for row in accepted:
            self._settle(row)
        self.processed.append(chk.isoformat())
        self.save()
        return [r for r in self.kept
                if pd.Timestamp(r['check']) == chk]


def _load_form_state():
    return _FormState()


def reset_form_state():
    """Remove the persisted 94f stream state (gate use)."""
    p = _state_path()
    if os.path.exists(p):
        os.remove(p)


def walk_ledger():
    """The filter+cap-kept picks recorded by the form's
    state, as a research-ledger DataFrame (gate use)."""
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
def evaluate_cycle94f_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the cycle94e chain (the layered form
    is produced by panel_entries)."""
    return evaluate_cycle94e_signals(frames, check_time_utc,
                                     m15_frames=m15_frames)


def select_cycle94f_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    return select_cycle94e_entries(signals,
                                   open_symbols=open_symbols)


def is_cycle94f_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE94F_CHECK_HOURS and t.minute == 30


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
    December best stream (cycle94e panel) plus the
    curated partner merge, settled through the high-vol
    filter and the state-conditional cap -- only kept
    picks are delivered."""
    entries = _c94e.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    m15map = ensure_m15(m15_frames, _DESIGN_SYMBOLS)
    ctxs = {}
    for sym, fr in frames.items():
        if fr is not None and len(fr):
            try:
                ctxs[sym] = _win_ctx(sym, fr,
                                     m15map.get(sym))
            except Exception:
                pass
    st = _load_form_state()
    kept = st.step(ctxs, check_time_utc, entries)
    if not kept:
        return pd.DataFrame()
    return pd.DataFrame([_signal_row(r) for r in kept])
