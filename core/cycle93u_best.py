"""Cycle 93U -- November candidate: the SL-fix Round 2
winner T20 FULLSTACK, expressed as real cycle code for the
validate-and-replace stage (research verdict:
work_nov_slfix2/results/nov_slfix2_VERDICT.md).

NOT INSTALLED. This module is built and gate-verified in
the validation lane only; the registry still points at
cycle93t. Nothing here is reachable from the live router
until a separate install step registers it.

The form is stream surgery on the shipped cycle93t form
(whose merge + state-conditional cap layers are themselves
stream rules over the cycle93r panel stream), applied to
93t's cap-kept stream in stream order, exactly as the
research applied it over the settled canonical ledger
(occupancy / cap interactions of the changed exits are
out of basis, as declared in the Round-2 slate -- the
underlying 93t state keeps the uncapped stream; this
layer only transforms what is DELIVERED):

  1. WIDEVOL entry filter: a kept pick is dropped when
     its signal-bar atr_pct (the campaign expanding-
     percentile ATR rank, as recorded by 93t's own
     enrichment) is >= 2/3 AND its strategy is in
     WIDE_STRATEGIES -- the six strategies whose worst
     realised stop-exit trade on the canonical discovery
     ledger is >= 90 pips (frozen set, declared in the
     Round-2 slate before grading). A pick whose atr_pct
     is missing is never dropped (conservative keep, the
     research filter's NaN rule).
  2. Dollar stop caps: the delivered pick's stop is
     capped at a per-symbol pip level so that one full
     stop at the reference starting lot (0.8 / (83/3) =
     0.0289157 lots, the operative N/3 ruler of the
     incumbent) costs at most the class dollar cap:
     $15 base; $10 on CHF-quoted symbols; $10 on the
     two EURNZD equations (the equation class overrides
     the symbol class, as in the research dol_class
     order). Pip values are the repair mission's
     (work_sim_repair/pip_margin, RATES_OCT_AVG
     conversion); the resulting pip caps are frozen
     constants below (CAP15_PIPS / CAP10_PIPS), computed
     once from those inputs. TP is unchanged.

Check hours: the November grid (9, 10, 13, 15 UTC) --
identical to cycle93t, so an install would need no
signal/prep job retiming. Sizing: the research graded
the form's own sizing-grid pass at N = 100 (the
incumbent carries 83); the carried N is settled by the
validation battery, not by this module.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

import core.cycle93r_best as _c93r
import core.cycle93t_best as _c93t
from core.cycle93t_best import (evaluate_cycle93r_signals,
                                is_cycle93r_check_time,
                                select_cycle93r_entries)

SYSTEM_NAME = "cycle93u"
CYCLE93U_CHECK_HOURS = (9, 10, 13, 15)
MAX_HOLD = 48

SYMS = _c93t.SYMS

WIDE_STRATEGIES = frozenset({
    'BP_bp_pos_S_AUDCHF_h13_2.0x8.0_H48',
    'CYB_cyb_pos_S_EURNZD_h15_1.1x6.0_H48',
    'CYB_cyb_x_S_EURAUD_h13_1.5x7.0_H48',
    'FB_EURUSD_h9_0',
    'MIX3_mx_stc_x_bp_atr_dd1255df_B_GBPJPY_h15_0.68x7.5_H48',
    'RWI_rwi_str_S_EURNZD_h13_1.5x7.0_H48',
})
EURNZD_EQ = frozenset({
    'CYB_cyb_pos_S_EURNZD_h15_1.1x6.0_H48',
    'RWI_rwi_str_S_EURNZD_h13_1.5x7.0_H48',
})
CHF_SYMBOLS = frozenset({
    'AUDCHF', 'CADCHF', 'CHFJPY', 'EURCHF', 'GBPCHF',
    'NZDCHF', 'USDCHF',
})
_HI_PCT = 2.0 / 3.0

# Dollar-cap pip levels: dollars / pip_usd(symbol,
# 0.8/(83/3)) with the repair pip values (RATES_OCT_AVG).
CAP15_PIPS = {
    'AUDCAD': 73.36214374999999, 'AUDCHF': 42.982587499999994,
    'AUDJPY': 81.92491137499998, 'AUDNZD': 92.05366173939275,
    'AUDUSD': 51.87499999999999, 'CADCHF': 42.982587499999994,
    'CADJPY': 81.92491137499998, 'CHFJPY': 81.92491137499998,
    'EURAUD': 74.25246553969912, 'EURCAD': 73.36214374999999,
    'EURCHF': 42.982587499999994, 'EURGBP': 39.03252020285623,
    'EURJPY': 81.92491137499998, 'EURNZD': 92.05366173939275,
    'EURUSD': 51.87499999999999, 'GBPAUD': 74.25246553969912,
    'GBPCAD': 73.36214374999999, 'GBPCHF': 42.982587499999994,
    'GBPJPY': 81.92491137499998, 'GBPNZD': 92.05366173939275,
    'GBPUSD': 51.87499999999999, 'NZDCAD': 73.36214374999999,
    'NZDCHF': 42.982587499999994, 'NZDJPY': 81.92491137499998,
    'NZDUSD': 51.87499999999999, 'USDCAD': 73.36214374999999,
    'USDCHF': 42.982587499999994, 'USDJPY': 81.92491137499998,
}
CAP10_PIPS = {
    'AUDCAD': 48.90809583333333, 'AUDCHF': 28.655058333333326,
    'AUDJPY': 54.61660758333333, 'AUDNZD': 61.36910782626183,
    'AUDUSD': 34.58333333333333, 'CADCHF': 28.655058333333326,
    'CADJPY': 54.61660758333333, 'CHFJPY': 54.61660758333333,
    'EURAUD': 49.50164369313275, 'EURCAD': 48.90809583333333,
    'EURCHF': 28.655058333333326, 'EURGBP': 26.02168013523749,
    'EURJPY': 54.61660758333333, 'EURNZD': 61.36910782626183,
    'EURUSD': 34.58333333333333, 'GBPAUD': 49.50164369313275,
    'GBPCAD': 48.90809583333333, 'GBPCHF': 28.655058333333326,
    'GBPJPY': 54.61660758333333, 'GBPNZD': 61.36910782626183,
    'GBPUSD': 34.58333333333333, 'NZDCAD': 48.90809583333333,
    'NZDCHF': 28.655058333333326, 'NZDJPY': 54.61660758333333,
    'NZDUSD': 34.58333333333333, 'USDCAD': 48.90809583333333,
    'USDCHF': 28.655058333333326, 'USDJPY': 54.61660758333333,
}


# ------------------------------------------------ decisions --
def cap_pips_for(symbol, strategy):
    """The form's stop cap in pips for one pick (class
    order as researched: EURNZD equations, then CHF
    symbols, then the $15 base)."""
    if strategy in EURNZD_EQ:
        return CAP10_PIPS[symbol]
    if symbol in CHF_SYMBOLS:
        return CAP10_PIPS[symbol]
    return CAP15_PIPS[symbol]


def widevol_drop(strategy, atr_pct):
    """WIDEVOL: drop iff atr_pct >= 2/3 and the strategy
    is in the frozen WIDE set. Missing atr_pct keeps."""
    if atr_pct is None:
        return False
    try:
        v = float(atr_pct)
    except (TypeError, ValueError):
        return False
    if np.isnan(v):
        return False
    return bool(v >= _HI_PCT and strategy in WIDE_STRATEGIES)


def capped_sl(symbol, strategy, sl_pips):
    return min(float(sl_pips), cap_pips_for(symbol, strategy))


# ----------------------------------------------------- state --
def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


class _T20State(_c93t._FormState):
    """The 93t stream state plus this form's delivered
    stream: every 93t cap-kept pick, transformed once --
    WIDEVOL drops recorded in `filtered`, survivors
    recorded in `delivered` with the capped stop (their
    exits re-simulated by the inherited enrichment, which
    reads the row's tp/sl -- the delivered row carries
    the capped sl_pips_used)."""

    def __init__(self, path=None):
        self.delivered = []
        self.filtered = []
        self.delivered_checks = []
        super().__init__(path=path or _state_path())

    # ------------------------------------------------ persist --
    def _load(self):
        import json
        super()._load()
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
        self.delivered_checks = list(
            d.get('delivered_checks', []))

    def save(self):
        import json
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
                    kept=ser(self.kept),
                    deferred=ser(self.deferred),
                    processed=self.processed,
                    delivered=ser(self.delivered),
                    filtered=ser(self.filtered),
                    delivered_checks=self.delivered_checks)
        with open(self.path, 'w') as fh:
            json.dump(data, fh)

    # ------------------------------------------------- enrich --
    def refresh(self, ohlc, frames):
        super().refresh(ohlc, frames)
        for row in self.delivered:
            if not row.get('exit_final'):
                if self._enrich(row, ohlc, frames):
                    row['exit_final'] = True

    # ---------------------------------------------------- step --
    def step(self, ohlc, frames, check, inc_entries):
        kept = super().step(ohlc, frames, check, inc_entries)
        chk = pd.Timestamp(check)
        if chk.isoformat() in self.delivered_checks:
            return [r for r in self.delivered
                    if pd.Timestamp(r['check']) == chk]
        self.refresh(ohlc, frames)
        for row in kept:
            if widevol_drop(row['strategy'],
                            row.get('atr_pct')):
                self.filtered.append(row)
                continue
            d = dict(row)
            d['sl_pips_used'] = capped_sl(
                row['symbol'], row['strategy'],
                row['sl_pips_used'])
            d['exit_final'] = False
            if self._enrich(d, ohlc, frames):
                d['exit_final'] = True
            self.delivered.append(d)
        self.delivered_checks.append(chk.isoformat())
        self.save()
        return [r for r in self.delivered
                if pd.Timestamp(r['check']) == chk]


def _load_form_state():
    return _T20State()


def reset_form_state():
    """Remove the persisted 93u stream state (gate use)."""
    p = _state_path()
    if os.path.exists(p):
        os.remove(p)


def walk_ledger():
    """The delivered picks recorded by the form's state,
    as a research-ledger DataFrame (gate use)."""
    st = _T20State()
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
def evaluate_cycle93u_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    """Base signals: the cycle93r chain (the transformed
    form is produced by panel_entries)."""
    return evaluate_cycle93r_signals(frames, check_time_utc,
                                     m15_frames=m15_frames)


def select_cycle93u_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    return select_cycle93r_entries(signals,
                                   open_symbols=open_symbols)


def is_cycle93u_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE93U_CHECK_HOURS and t.minute == 30


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """Full form entries for one check: the cycle93t form
    stream settled through its merge + cap, then this
    form's WIDEVOL filter and dollar stop caps -- only
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
                        entries)
    if not delivered:
        return pd.DataFrame()
    return pd.DataFrame(
        [_c93t._signal_row(r) for r in delivered])
