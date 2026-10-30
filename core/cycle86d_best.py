"""Cycle 86D -- March candidate, Round R2 winner M18
(integration gate passed EXACT in the upload scratch
tree, 2026-10-30; gate record gate_mar_m18.json /
VERDICT_MAR.md in work_20cyc_r2/upload):

  cycle86c construction (March combined stream:
  cycle86b + cycle86s with the mar_rp P-REPLACE layer,
  695 research picks)
  + PC14 M15 veto mask on the combined stream's picks
  + veto of the EURAUD h12 b6v slot
    (N3_b6v_vol_z_x_nx_sq_2708508f_S_EURAUD_h12_1.27x3.7_H48)
  + refill from the mar_rp walk's merge-dropped rows
    (rows whose (check, strategy) is not in the combined
    stream), second-priority under
    core.new8_walk.build_combined occupancy.

PC14 veto (Mar Plan C PC14_bb_rpos, features at the
signal candle sig_t = check - 90 min, M15 bars up to
sig_t): keep a pick only if aligned M15 Bollinger z
<= 1.0 AND aligned range position <= 0.85 AND aligned
mom16 > -0.35 (core.new8_features.pc14_m15_features /
pc14_keep, verbatim research formulas).

Validated numbers (R2 Mar M18, @2.5, app-code replay
proven 557/557 exact vs the simulated ledger): DISC
leftover 79.89%, AUDIT leftover 46.52% (incumbent
22.99), LCT P 81.72% / 5th-pct 70.70 (middle PASS),
Monte Carlo middle PASS (DD p95 190.02), PBO 0.00 /
DSR 1.0, mask keeps 549 of 695, refill accepts 8 of a
56-row pool (38 check_busy + 10 symbol_overlap drops).

Named simulation asymmetry, preserved deliberately
because the M18 grade was computed on exactly this
construction (gate_mar_m18.py): refill picks are NOT
PC14-checked (the batch simulation re-accepts dropped
mar_rp rows against the vetoed stream under occupancy
only; 1 of the 8 research refills would fail PC14).

Check hours: the March grid (11, 16, 17 UTC) --
CYCLE86C_CHECK_HOURS via cycle86c.
"""

from __future__ import annotations

import pandas as pd

import core.cycle86c_best as _c86c
from core.cycle86c_best import (CYCLE86C_CHECK_HOURS,
                                evaluate_cycle86c_signals,
                                is_cycle86c_check_time,
                                select_cycle86c_entries)

CYCLE86D_CHECK_HOURS = CYCLE86C_CHECK_HOURS
DESIGN = "mar_rp"
DESIGNS = ("mar_rp",)
SYSTEM_NAME = "cycle86d"
SLOT_VETO_STRATEGY = \
    'N3_b6v_vol_z_x_nx_sq_2708508f_S_EURAUD_h12_1.27x3.7_H48'


def evaluate_cycle86d_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    return evaluate_cycle86c_signals(frames, check_time_utc,
                                     m15_frames=m15_frames)


def select_cycle86d_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    return select_cycle86c_entries(signals,
                                   open_symbols=open_symbols)


def is_cycle86d_check_time(ts) -> bool:
    return is_cycle86c_check_time(ts)


def fetch_cycle86d_m15_frames(state=None):
    from core.cycle86_best import fetch_cycle86_m15_frames
    return fetch_cycle86_m15_frames(state=state)


# ------------------------------------------------ ledger form --
def pc14_mask_for_ledger(df: pd.DataFrame,
                         m15_frames: dict) -> pd.Series:
    """M18 keep-mask over a combined ledger frame: PC14
    keep (app producer per symbol, cached per symbol)
    AND not the vetoed EURAUD h12 b6v slot."""
    from core.new8_features import pc14_keep, pc14_m15_features
    cache = {}
    keep = []
    for r in df.itertuples():
        if r.symbol not in cache:
            cache[r.symbol] = pc14_m15_features(m15_frames[r.symbol])
        keep.append(pc14_keep(cache[r.symbol], r.check, r.direction)
                    and r.strategy != SLOT_VETO_STRATEGY)
    return pd.Series(keep, index=df.index)


def refill_layers(base: pd.DataFrame, walks: dict,
                  incumbent_keys: set, order=DESIGNS):
    """Second-priority refill of `base` from candidate
    walks (in `order`), via core.new8_walk.build_combined
    occupancy verbatim. Candidate rows whose (check,
    strategy) is in `incumbent_keys` (the pre-veto combined
    stream) are excluded first -- the simulation rule.
    Refill picks are NOT PC14-checked (see module docstring).
    Returns (combined, {design: n_accepted}); src tags are
    restored per check (build_combined rewrites the base
    frame's src to 'incumbent' on each merge)."""
    from core.new8_walk import build_combined
    cur = base.copy()
    src_by_check = {c: s for c, s in zip(cur['check'], cur['src'])}
    accepted = {}
    tags = {'mar_rp': 'refill_rp'}
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


def build_cycle86d_ledger(incumbent: pd.DataFrame, walks: dict,
                          m15_frames: dict):
    """The M18 ledger construction: PC14 mask + EURAUD
    slot veto on the incumbent combined stream, then
    refill from the mar_rp walk."""
    inc = incumbent.sort_values('check', kind='stable') \
        .reset_index(drop=True)
    inc_keys = set(zip(inc['check'], inc['strategy']))
    mask = pc14_mask_for_ledger(inc, m15_frames)
    base = inc[mask].reset_index(drop=True)
    base['src'] = 'incumbent'
    return refill_layers(base, walks, inc_keys)


# ------------------------------------------------- panel form --
def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """One-check form of the same construction: cycle86c
    panel entries; PC14 + slot veto on the merged pick
    (M15 frame of its symbol); if vetoed (or no pick),
    refill from the mar_rp design's signal rows at this
    check, excluding the vetoed pick's strategy and any
    symbol already open. Refill picks are not PC14-checked,
    matching the graded construction."""
    from core.new8_candidate import CandidateContext
    from core.new8_features import pc14_keep, pc14_m15_features
    entries = _c86c.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    vetoed_strategies = set()
    if entries is not None and len(entries):
        kept_rows = []
        for _, r in entries.iterrows():
            strat = r.get('strategy', r.get('equation'))
            veto = strat == SLOT_VETO_STRATEGY
            if not veto:
                m15 = (m15_frames or {}).get(r['symbol'])
                if m15 is not None and len(m15):
                    feats = pc14_m15_features(m15)
                    veto = not pc14_keep(feats, check_time_utc,
                                         r['direction'])
            if veto:
                if strat is not None:
                    vetoed_strategies.add(strat)
            else:
                kept_rows.append(r)
        entries = (pd.DataFrame(kept_rows).reset_index(drop=True)
                   if kept_rows else entries.iloc[0:0])
    if entries is not None and len(entries):
        return entries
    # refill: first mar_rp signal row at this check that is
    # not a vetoed pick and whose symbol is not open.
    from core.new8_candidate import candidate_signal_row
    ctx = CandidateContext(frames, m15_frames, DESIGNS)
    rows = ctx.rows_at(DESIGN, pd.Timestamp(check_time_utc))
    for eq_id, row in rows.items():
        if eq_id in vetoed_strategies:
            continue
        if row['symbol'] in tuple(open_symbols or ()):
            continue
        return pd.DataFrame([candidate_signal_row(row)])
    return entries if entries is not None else pd.DataFrame()
