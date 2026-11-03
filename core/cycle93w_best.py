"""Cycle 93W -- November: the robustness-fix programme's
lead form D21-RC over the shipped cycle93u stream, expressed
as real cycle code for the validate-and-replace lane
(research verdict: work_rob_fix/results/nov_VERDICT.md;
validation record: work_rob_validate/results/
nov_VALIDATION.md).

NOT INSTALLED. This module is built and gate-verified in
the validation lane only; the registry still points at
cycle93u. Nothing here is reachable from the live router
until a separate install step registers it.

The form is stream surgery on the shipped cycle93u form's
delivered stream, applied in stream order (the D21-RC
transform, core/d21rc_lib.py):

  1. EXPOSURE-SKIP: a realised-balance walk over the
     delivered stream (START $80, formula lots at the
     carried N = 100/3). A pick is skipped when the open
     adverse exposure of kept picks (|pwv| x pv x lot,
     fixed at each pick's entry; pwv = the pick's worst
     floating value on its M15-close profile, pv = $ per
    pip per 1.00 lot at its exit instant) plus the
     candidate's own would exceed 10% of the realised
     balance.
  2. RATIO CAP: every delivered pick's stop is capped at
     min(stop, 5 x its target); the delivered row carries
     the capped sl_pips_used (its exit is re-simulated by
     the inherited enrichment, as with cycle93u's caps).

Check hours: the November grid (9, 10, 13, 15 UTC) --
identical to cycle93u, so an install needs no signal/prep
job retiming. Sizing: carried N = 100 (full), shipped at
N/3, unchanged from the incumbent.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

import core.cycle93r_best as _c93r
import core.cycle93t_best as _c93t
import core.cycle93u_best as _c93u
from core import d21rc_lib as _L
from core.cycle93u_best import (evaluate_cycle93u_signals,
                                is_cycle93u_check_time,
                                select_cycle93u_entries)

SYSTEM_NAME = "cycle93w"
CYCLE93W_CHECK_HOURS = _c93u.CYCLE93U_CHECK_HOURS
MAX_HOLD = 48
CARRIED_N = 100.0 / 3.0

SYMS = _c93u.SYMS

_BARS_CACHE = {}


def _db_bars(symbol):
    """M15 (ts_s, open, close) for a symbol from fx_data.db
    (chain_engine.load_bars_fixed semantics), cached."""
    if symbol in _BARS_CACHE:
        return _BARS_CACHE[symbol]
    import sqlite3
    fx = os.path.expanduser('~/workspace/fx')
    con = sqlite3.connect(f'file:{fx}/fx_data.db?mode=ro',
                          uri=True)
    df = pd.read_sql(
        'select Datetime, Open, Close from ohlc_m15 '
        'where Symbol=? order by Datetime', con,
        params=(symbol,))
    con.close()
    ts = (pd.to_datetime(df['Datetime'], format='ISO8601',
                         utc=True).astype('int64')
          // 10 ** 9).to_numpy(np.int64)
    bars = (ts, df['Open'].to_numpy(np.float64),
            df['Close'].to_numpy(np.float64))
    _BARS_CACHE[symbol] = bars
    return bars


def _frame_bars(df):
    """M15 (ts_s, open, close) from an app M15 frame."""
    tcol = next(c for c in df.columns
                if c.lower() in ('datetime', 'time', 'timestamp'))
    ts = (pd.to_datetime(df[tcol], utc=True).astype('int64')
          // 10 ** 9).to_numpy(np.int64)
    return (ts, df['Open'].to_numpy(np.float64),
            df['Close'].to_numpy(np.float64))


def _bars(symbol, m15_frames):
    if m15_frames and symbol in m15_frames \
            and m15_frames[symbol] is not None \
            and len(m15_frames[symbol]):
        try:
            return _frame_bars(m15_frames[symbol])
        except Exception:
            pass
    return _db_bars(symbol)


def _ts_s(ts):
    return int(pd.Timestamp(ts).value // 10 ** 9)


# ----------------------------------------------------- state --
def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


class _Form:
    """A cycle93u state object plus the D21-RC layer state,
    stepped together per check. The 93u sub-state persists
    through its own save/load in a sidecar file; this form's
    delivered/filtered lists and layer state persist in the
    form's own state document."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.u_state = _c93u._T20State(
            path=self.path + '.ustate.json')
        self.delivered = []
        self.filtered = []
        self.delivered_checks = []
        self.layer = _L.StreamLayer(CARRIED_N)
        self._load()

    # ------------------------------------------------ persist --
    def _load(self):
        import json
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
        self.delivered = de(d.get('delivered', []))
        self.filtered = de(d.get('filtered', []))
        self.delivered_checks = list(d.get('delivered_checks',
                                           []))
        lay = d.get('layer', {})
        self.layer.bal = float(lay.get('bal', _L.START))
        self.layer.profit = float(lay.get('profit', 0.0))
        self.layer.open_kept = [(int(e), float(a)) for e, a in
                                 lay.get('open_kept', [])]
        self.layer._pending_exits = [
            (int(e), float(n), float(p), float(l))
            for e, n, p, l in lay.get('pending_exits', [])]

    def save(self):
        import json
        if not self.path:
            return
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)
        self.u_state.save()

        def ser(rows):
            out = []
            for r in rows:
                d = dict(r)
                for k in ('check', 'entry_time', 'exit_time'):
                    if d.get(k) is not None:
                        d[k] = pd.Timestamp(d[k]).isoformat()
                out.append(r)
            return out
        data = dict(
            system=SYSTEM_NAME,
            delivered=ser(self.delivered),
            filtered=ser(self.filtered),
            delivered_checks=self.delivered_checks,
            layer=dict(
                bal=self.layer.bal, profit=self.layer.profit,
                open_kept=[[e, a] for e, a in
                           self.layer.open_kept],
                pending_exits=[[e, n, p, l] for e, n, p, l in
                               self.layer._pending_exits]))
        with open(self.path, 'w') as fh:
            json.dump(data, fh)

    # ---------------------------------------------------- step --
    def step(self, ohlc, frames, check, inc_entries,
             m15_frames=None):
        kept = self.u_state.step(ohlc, frames, check,
                                 inc_entries)
        chk = pd.Timestamp(check)
        if chk.isoformat() in self.delivered_checks:
            return [r for r in self.delivered
                    if pd.Timestamp(r['check']) == chk]
        for row in kept:
            bars = _bars(row['symbol'], m15_frames)
            entry_s = _ts_s(row['entry_time'])
            exit_s = _ts_s(row['exit_time'])
            dirsign = 1.0 if str(row['direction']).upper() \
                .startswith('B') else -1.0
            entry_px = float(row.get('entry_px') or 0.0)
            if not entry_px:
                ts_arr = bars[0]
                j = int(np.searchsorted(ts_arr, entry_s))
                entry_px = float(bars[1][min(j, len(ts_arr) - 1)])
            prof = _L.profile_for_sym(
                row['symbol'], entry_s, exit_s, entry_px,
                dirsign, bars)
            majors = {p: _bars(p, m15_frames)
                      for p in _L.MAJORS}
            pv = _L.pip_value_per_lot(
                row['symbol'], _L.rates_at(majors, exit_s))
            lrow = {'entry_s': entry_s, 'exit_s': exit_s,
                    'net': float(row['gross_pips']) - _L.COST,
                    'pwv': float(prof.min()) if len(prof) else 0.0,
                    'pv': pv,
                    'tp': float(row['tp_pips_used']),
                    'sl': float(row['sl_pips_used']),
                    'prof': prof}
            if self.layer.decide(lrow) is None:
                self.filtered.append(row)
                continue
            d = dict(row)
            d['sl_pips_used'] = min(float(row['sl_pips_used']),
                                    5.0 * float(
                                        row['tp_pips_used']))
            d['exit_final'] = False
            if self.u_state._enrich(d, ohlc, frames):
                d['exit_final'] = True
            self.delivered.append(d)
        self.delivered_checks.append(chk.isoformat())
        self.save()
        return [r for r in self.delivered
                if pd.Timestamp(r['check']) == chk]


def _load_form_state():
    return _Form()


def reset_form_state():
    """Remove the persisted 93w stream state (gate use)."""
    for p in (_state_path(), _state_path() + '.ustate.json'):
        if os.path.exists(p):
            os.remove(p)


def walk_ledger():
    """The delivered picks recorded by the form's state,
    as a research-ledger DataFrame (gate use)."""
    st = _Form()
    rows = [dict(check=r['check'], symbol=r['symbol'],
                 direction=r['direction'],
                 strategy=r['strategy'],
                 entry_time=r['entry_time'],
                 exit_time=r['exit_time'],
                 gross_pips=r['gross_pips'])
            for r in st.delivered]
    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values('check').reset_index(drop=True)
    return df


# -------------------------------------------------- panel API --
def evaluate_cycle93w_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the cycle93u chain (the transformed
    form is produced by panel_entries)."""
    return evaluate_cycle93u_signals(frames, check_time_utc,
                                     m15_frames=m15_frames)


def select_cycle93w_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    return select_cycle93u_entries(signals,
                                   open_symbols=open_symbols)


def is_cycle93w_check_time(ts) -> bool:
    return is_cycle93u_check_time(ts)


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full form entries for one check: the cycle93r base
    entries settled through the cycle93u form state, then
    this form's exposure-skip and 5xTP stop cap -- only
    transformed survivors are delivered."""
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
    delivered = st.step(ohlc, frames, check_time_utc,
                        entries, m15_frames=m15_frames)
    if not delivered:
        return pd.DataFrame()
    return pd.DataFrame(
        [_c93t._signal_row(r) for r in delivered])
