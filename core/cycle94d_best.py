"""Cycle 94D -- December candidate, Round R2 attempt-2
winner D19 (integration scratch build, 2026-10-30):

  cycle94c construction (cycle94b + cycle94s combined
  stream with the dec_rg / dec_rgc P-REGIME layers)
  + PC03 M15 veto on the combined stream's picks
  + candidate-layer refill (dec_rg walk first, then
    dec_rgc walk, second-priority under
    core.new8_walk.build_combined occupancy)
  + PLANB12C cand1 partner layer (design 'dec_b12c'),
    merged second-priority after the refills.

PC03 veto (Wave-3b PC03_mom4_mom96_vol, features at the
signal candle sig_t = check - 90 min, M15 bars up to
sig_t): keep a pick only if aligned M15 mom4 > -0.15
AND aligned M15 mom96 > -0.8 AND M15 vol_z > -1.0
(core.new8_features.pc03_keep / pc03_m15_features,
verbatim Wave-3b formulas).

Named simulation asymmetries, preserved deliberately
because the D19 grade was computed on exactly this
construction (run_wave4e_attempt2.py):
  * the veto screens the incumbent combined stream
    only; refill and partner picks are NOT PC03-checked
    (the Dec features file covers exactly the 954
    incumbent rows, so the simulation could not check
    them either);
  * refill/partner candidate rows that were themselves
    part of the pre-veto combined stream are excluded
    (they were already considered: kept rows block their
    check anyway, vetoed rows must not re-enter);
  * base-stream fall-through beyond the candidate
    layers is not modelled anywhere (no signal pool for
    the 94b stream exists) -- the same named gap as the
    simulated grade.

Check hours: the December grid (10, 11, 13 UTC) --
CYCLE94B_CHECK_HOURS via cycle94c.
"""

from __future__ import annotations

import pandas as pd

import core.cycle94c_best as _c94c
from core.cycle94c_best import (CYCLE94C_CHECK_HOURS,
                                evaluate_cycle94c_signals,
                                fetch_cycle94c_m15_frames,
                                is_cycle94c_check_time,
                                select_cycle94c_entries)

CYCLE94D_CHECK_HOURS = CYCLE94C_CHECK_HOURS
DESIGNS = ("dec_rg", "dec_rgc", "dec_b12c")
REFILL_DESIGNS = ("dec_rg", "dec_rgc")
PARTNER_DESIGN = "dec_b12c"
SYSTEM_NAME = "cycle94d"


def evaluate_cycle94d_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    return evaluate_cycle94c_signals(frames, check_time_utc,
                                     m15_frames=m15_frames)


def select_cycle94d_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    return select_cycle94c_entries(signals,
                                   open_symbols=open_symbols)


def is_cycle94d_check_time(ts) -> bool:
    return is_cycle94c_check_time(ts)


def fetch_cycle94d_m15_frames(state=None):
    return fetch_cycle94c_m15_frames(state=state)


# ------------------------------------------------ ledger form --
def pc03_mask_for_ledger(df: pd.DataFrame,
                         m15_frames: dict) -> pd.Series:
    """PC03 keep-mask over a combined ledger frame, using
    the app PC03 producer per symbol (cached per symbol)."""
    from core.new8_features import pc03_keep, pc03_m15_features
    cache = {}
    keep = []
    for r in df.itertuples():
        if r.symbol not in cache:
            cache[r.symbol] = pc03_m15_features(m15_frames[r.symbol])
        keep.append(pc03_keep(cache[r.symbol], r.check, r.direction))
    return pd.Series(keep, index=df.index)


def refill_layers(base: pd.DataFrame, walks: dict,
                  incumbent_keys: set, order=DESIGNS):
    """Second-priority refill of `base` from candidate
    walks (in `order`), via core.new8_walk.build_combined
    occupancy verbatim. Candidate rows whose (check,
    strategy) is in `incumbent_keys` (the pre-veto combined
    stream) are excluded first -- the simulation rule.
    Returns (combined, {design: n_accepted}); src tags are
    restored per check (build_combined rewrites the base
    frame's src to 'incumbent' on each merge)."""
    from core.new8_walk import build_combined
    cur = base.copy()
    src_by_check = {c: s for c, s in zip(cur['check'], cur['src'])}
    accepted = {}
    tags = {'dec_rg': 'refill_rg', 'dec_rgc': 'refill_rgc',
            'dec_b12c': 'partner'}
    for name in order:
        cand = walks[name].copy()
        cand['entry_time'] = cand['check'] - pd.Timedelta(minutes=30)
        cand = cand[[k not in incumbent_keys
                     for k in zip(cand['check'], cand['strategy'])]]
        cand['src'] = tags[name]
        before = set(cur['check'])
        cur, drops, n_acc = build_combined(cur, cand)
        for c in set(cur['check']) - before:
            src_by_check[c] = tags[name]
        accepted[name] = int(n_acc)
    cur['src'] = [src_by_check[c] for c in cur['check']]
    cur['net_pips'] = cur['gross_pips'] - 2.5
    return cur, accepted


def build_cycle94d_ledger(incumbent: pd.DataFrame, walks: dict,
                          m15_frames: dict):
    """The D19 ledger construction: PC03 veto on the
    incumbent combined stream, then refill + partner."""
    inc = incumbent.sort_values('check', kind='stable') \
        .reset_index(drop=True)
    inc_keys = set(zip(inc['check'], inc['strategy']))
    mask = pc03_mask_for_ledger(inc, m15_frames)
    base = inc[mask].reset_index(drop=True)
    base['src'] = 'incumbent'
    return refill_layers(base, walks, inc_keys)


# ------------------------------------------------- panel form --
def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """One-check form of the same construction: cycle94c
    panel entries; PC03 veto on the resulting pick (M15
    frame of its symbol); if vetoed (or no pick), refill
    in priority order dec_rg -> dec_rgc -> dec_b12c from
    each design's signal rows at this check, excluding
    the vetoed pick's own strategy."""
    from core.new8_candidate import CandidateContext
    from core.new8_features import pc03_keep, pc03_m15_features
    entries = _c94c.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    vetoed_strategy = None
    if entries is not None and len(entries):
        r = entries.iloc[0]
        m15 = (m15_frames or {}).get(r['symbol'])
        if m15 is not None and len(m15):
            feats = pc03_m15_features(m15)
            if not pc03_keep(feats, check_time_utc, r['direction']):
                vetoed_strategy = r['strategy']
                entries = entries.iloc[0:0]
    if entries is not None and len(entries):
        return entries
    # refill / partner: first design (in priority order)
    # with a signal row at this check that is not the
    # vetoed pick and whose symbol is not open.
    from core.new8_candidate import candidate_signal_row
    ctx = CandidateContext(frames, m15_frames, DESIGNS)
    for name in DESIGNS:
        rows = ctx.rows_at(name, pd.Timestamp(check_time_utc))
        for eq_id, row in rows.items():
            if eq_id == vetoed_strategy:
                continue
            if row['symbol'] in tuple(open_symbols or ()):
                continue
            return pd.DataFrame([candidate_signal_row(row)])
    return entries if entries is not None else pd.DataFrame()
