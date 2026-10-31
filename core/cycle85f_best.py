"""Cycle 85F -- February best, installed 2026-11-01 on the
user's standing conditional order (2026-11-01 ~00:36 MMT:
risk-improve-acceptable forms that pass final validation
replace the main system):

  cycle85e stream (the shipped February best, unchanged)
  + C18 FCAP layer (RISK6 FEB champion
    C18_FCAP_t0.60_INC, FINAL VALIDATION 2026-11-01:
    replay exact 684/684, VALIDATED under the relaxed
    re-screen standard):
    - filter: drop EURUSD picks whose signal-candle
      atr_pct >= 0.60 (EURUSD is February's DISC
      full-stop complex, frozen from the C01-C04
      diagnosis);
    - then the R2D11 cap stack (total 5 open weighted,
      per-currency weight <= 3 for a high-vol pick
      (atr_pct >= 2/3, weight 2), <= 4 otherwise) --
      cap_lib.apply_cap(total_k=5, weighted=True,
      statecond=True) semantics verbatim.

Validated numbers (research replay, @2.5): DISC leftover
92.52% (incumbent 90.51), net +7,154.60, win 98.33%,
3.342 entries/day; AUDIT leftover 42.50% (incumbent
38.11), net +701.92; ES5 -32.64 (incumbent -39.89);
section-9 MC PASS, DD p95 185.75 vs incumbent 193.36
(the section-9 margin widens 16.79 -> 24.40); LCT
P 70.0 / q05 82.98 -- passes the relaxed line exactly,
below the frozen middle (P >= 80): this install stands
on the user's relaxed-standard order, stated plainly.
EC22-middle 18/18 raw (16/16 house) under the relaxed
reading; DSR 1.0 / PBO 0.0% (family-9); decay WEAKENED
(the incumbent's own class); non-downgrade all arms
PASS; the tail gain is NOT thinning-equivalent.

The layer is a stream rule over the 85e panel's emitted
picks: this module records every 85e pick, enriches it
(48h simulation on the windowed frame + cache-basis
atr_pct), and settles the filter+cap in stream order
through a persisted state -- the cycle94f architecture.
February has no second-best system; none is added.

Inherited caveat (of record since the 85e install): 90
of the incumbent's cascade fills are M15-volume-
dependent and silent on the live Twelve feed today
(B-13 class); the layer operates on the stream as
emitted, exactly as graded.

Check hours: the February grid -- CYCLE85E_CHECK_HOURS
via cycle85e.
"""

from __future__ import annotations

import bisect
import json
import os

import numpy as np
import pandas as pd

import core.cycle85e_best as _c85e
from core.cycle85e_best import (CYCLE85E_CHECK_HOURS,
                                evaluate_cycle85e_signals,
                                is_cycle85e_check_time,
                                select_cycle85e_entries)
from core.new8_candidate import default_state_path

SYSTEM_NAME = "cycle85f"
CYCLE85F_CHECK_HOURS = CYCLE85E_CHECK_HOURS
MAX_HOLD = 48

_FILTER_SYM = 'EURUSD'
_FILTER_PCT = 0.60
_HI_PCT = 2.0 / 3.0
_CAP_BASE_K = 4
_CAP_HIGH_K = 3
_CAP_TOTAL_K = 5


def _pipsize(sym):
    return 0.01 if 'JPY' in sym else 0.0001


# ------------------------------------------------- features --
def _expanding_pct(a):
    """build_cache_feb.expanding_pct verbatim: for each i,
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
    """The Feb campaign frame convention (build_cache_feb
    RANGES): bars inside [Jan 19, Mar 14) of each year."""
    mask = np.zeros(len(idx), bool)
    for y in range(idx[0].year - 1, idx[-1].year + 1):
        mask |= (idx >= pd.Timestamp(f'{y}-01-19')) \
            & (idx < pd.Timestamp(f'{y}-03-14'))
    return mask


_CTX_CACHE = {}


def _win_ctx(sym, fr):
    """Campaign (build_cache_feb) windowed context for one
    symbol: windowed H1 OHLC + atr / atr_pct (the only
    features the FCAP layer reads). Cached per frame
    extent."""
    key = (sym, len(fr), str(fr.index[-1]))
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
    ctx = dict(
        idx=w.index,
        pos={t: i for i, t in enumerate(w.index)},
        o=w['Open'].to_numpy(dtype=float),
        h=hi.to_numpy(dtype=float),
        l=lo.to_numpy(dtype=float),
        c=c.to_numpy(dtype=float),
        atr=atr, atr_pct=_expanding_pct(atr))
    _CTX_CACHE[key] = ctx
    return ctx


# ----------------------------------------------------- exits --
def _exit_for(ctx, entry_time, direction, tp_pips, sl_pips,
              sym):
    """mine_lib simulate semantics on the windowed frame:
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
    """Persisted stream state for the 85f form: every
    incumbent pick recorded (enriched), the filter/cap
    kept and dropped verdicts -- all in stream order."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.incumbent = []        # enriched incumbent picks
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
                    kept=ser(self.kept),
                    dropped=ser(self.dropped),
                    processed=self.processed)
        with open(self.path, 'w') as fh:
            json.dump(data, fh)

    # ------------------------------------------------- enrich --
    def _enrich(self, row, ctxs):
        """(Re)compute a recorded pick's exit + atr_pct
        from the frames at hand. Returns True when final.
        Rows whose symbol has no frame keep the research
        fallback: atr_pct None (-> 0.0 in every
        comparison) and the +48h placeholder exit."""
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
        for row in self.incumbent:
            if not row.get('exit_final'):
                if self._enrich(row, ctxs):
                    row['exit_final'] = True

    # --------------------------------------------- filter+cap --
    def _hi(self, row):
        return row.get('atr_pct') is not None \
            and row['atr_pct'] >= _HI_PCT

    def _cap_admit(self, row):
        """apply_cap verbatim rule (total_k=5, weighted,
        statecond): weight 2 for high-vol picks;
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
        """The FCAP layer for one stream pick: the
        EURUSD atr_pct >= 0.60 filter first, then the
        cap."""
        if row['symbol'] == _FILTER_SYM \
                and row.get('atr_pct') is not None \
                and row['atr_pct'] >= _FILTER_PCT:
            row['drop_reason'] = 'filter'
            self.dropped.append(row)
            return
        if self._cap_admit(row):
            self.kept.append(row)
        else:
            row['drop_reason'] = 'cap'
            self.dropped.append(row)

    # ---------------------------------------------------- step --
    def step(self, ctxs, check, inc_entries):
        """Process one check in stream order. inc_entries:
        the cycle85e panel entries DataFrame for this
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
        for row in new_inc:
            self._settle(row)
        self.processed.append(chk.isoformat())
        self.save()
        return [r for r in self.kept
                if pd.Timestamp(r['check']) == chk]


def _load_form_state():
    return _FormState()


def reset_form_state():
    """Remove the persisted 85f stream state (gate use)."""
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
def evaluate_cycle85f_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the cycle85e chain (the layered form
    is produced by panel_entries)."""
    return evaluate_cycle85e_signals(frames, check_time_utc,
                                     m15_frames=m15_frames)


def select_cycle85f_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    return select_cycle85e_entries(signals,
                                   open_symbols=open_symbols)


def is_cycle85f_check_time(ts) -> bool:
    return is_cycle85e_check_time(ts)


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
    February best stream (cycle85e panel) settled through
    the EURUSD high-vol filter and the state-conditional
    cap -- only kept picks are delivered."""
    entries = _c85e.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    ctxs = {}
    for sym, fr in frames.items():
        if fr is not None and len(fr):
            try:
                ctxs[sym] = _win_ctx(sym, fr)
            except Exception:
                pass
    st = _load_form_state()
    kept = st.step(ctxs, check_time_utc, entries)
    if not kept:
        return pd.DataFrame()
    return pd.DataFrame([_signal_row(r) for r in kept])
