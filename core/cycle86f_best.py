"""Cycle 86F -- March best, installed 2026-11-01 on the
user's standing conditional order (2026-11-01 ~00:36 MMT:
risk-improve-acceptable forms that pass final validation
replace the main system):

  the cycle86e construction with ONE change (RISK6 MAR
  champion C10_EXC, FINAL VALIDATION 2026-11-01: control
  M18 557/557 and D10 515/515 exact, patched replay
  527/527 exact, VALIDATED under the relaxed re-screen
  standard):
    FB_EURGBP_h16_2 is excised from the construction
    INPUT -- the combined stream the 86d construction
    consumes -- instead of being vetoed from the
    finished ledger. Every downstream stage is the
    shipped one, verbatim: PC14 M15 mask + EURAUD h12
    b6v slot veto -> mar_rp refill under
    core.new8_walk.build_combined occupancy (the freed
    checks now refill: 20 accepted vs 8 shipped) ->
    D10 dual veto -> cool1.

Validated numbers (research replay, @2.5): 527 picks;
DISC leftover 83.88% (incumbent 83.23), net +4,287.26,
win 96.05%, 2.389 entries/day; AUDIT leftover 56.47%
(incumbent 56.08), net +543.84; ES5 -35.46 (incumbent
-37.09); section-9 MC PASS, DD p95 139.54 vs incumbent
141.61 (margin 12.14 -> 14.21); LCT P 71.41 / q05 77.54
-- passes the relaxed line, below the frozen middle
(P >= 80): this install stands on the user's
relaxed-standard order, stated plainly. EC22-middle
18/18 raw (16/16 house) under the relaxed reading;
DSR 1.0 / PBO 0.0% (family-9); decay WEAKENED (the
incumbent's own class under the same implementation);
non-downgrade all arms PASS; thinning test N/A (the
form ADDS picks -- its gains cannot be a thinning
artifact).

Live-servability caveat (inherited verbatim from the
86e record): the graded cool1 reads each pick's
simulated net in check order from the completed ledger.
Live, a still-open trade's net is unknowable at the
next check, so the panel form below applies cool1
causally -- a kept pick's net is resolved by
re-simulation (core.new8_walk.sim_fixed_vec) once the
frame covers its full 48h window, and the cooldown
fires at the first check after resolution. Live cool1
timing therefore differs from the graded ledger rule;
the causal variant has not been separately re-graded.
Also inherited: the live panel chain already excises
this equation pre-select (cycle86b, 2026-10-27); the
panel form below applies the same excision inside this
module's construction so a freed check can be answered
by the mar_rp refill, exactly as in the graded batch
form.

Check hours: the March grid (11, 16, 17 UTC) --
CYCLE86D_CHECK_HOURS via cycle86d.
"""

from __future__ import annotations

import json
import os

import pandas as pd

import core.cycle86c_best as _c86c
import core.cycle86d_best as _c86d
from core.cycle86d_best import (CYCLE86D_CHECK_HOURS,
                                build_cycle86d_ledger,
                                fetch_cycle86d_m15_frames)

CYCLE86F_CHECK_HOURS = CYCLE86D_CHECK_HOURS
DESIGN = "mar_rp"
DESIGNS = ("mar_rp",)
SYSTEM_NAME = "cycle86f"
EXCISED_STRATEGY = 'FB_EURGBP_h16_2'
W6_VETO = ('W6_rpe_vx_flow_x_rp_q_mom_x_rsi14_43d2f898_S_'
           'EURAUD_h16_0.88x15.2_H48')
VETO_STRATEGIES = (EXCISED_STRATEGY, W6_VETO)


def evaluate_cycle86f_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    return _c86d.evaluate_cycle86d_signals(
        frames, check_time_utc, m15_frames=m15_frames)


def select_cycle86f_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    return _c86d.select_cycle86d_entries(
        signals, open_symbols=open_symbols)


def is_cycle86f_check_time(ts) -> bool:
    return _c86d.is_cycle86d_check_time(ts)


def fetch_cycle86f_m15_frames(state=None):
    return fetch_cycle86d_m15_frames(state=state)


# ------------------------------------------------ ledger form --
def cool1_filter_df(df: pd.DataFrame) -> pd.DataFrame:
    """Verbatim core.cycle86e_best.cool1_filter_df: after
    a KEPT pick with simulated net (gross_pips - 2.5)
    <= 0, skip exactly the next pick."""
    keep = []
    cool = 0
    for i, g in enumerate(df['gross_pips'].to_numpy(float)):
        if cool > 0:
            cool -= 1
            continue
        keep.append(i)
        if g - 2.5 <= 0:
            cool = 1
    return df.iloc[keep].reset_index(drop=True)


def build_cycle86f_ledger(incumbent: pd.DataFrame,
                          walks: dict, m15_frames: dict):
    """The C10_EXC ledger construction: the shipped M18
    (cycle86d) construction run on the combined stream
    with FB_EURGBP_h16_2 excised at the input, then the
    W6 dual-veto leg (the excised strategy is already
    absent), then cool1 over the merged stream."""
    inc = incumbent[incumbent['strategy'] != EXCISED_STRATEGY]
    led, accepted = build_cycle86d_ledger(inc, walks,
                                          m15_frames)
    led = led.sort_values('check', kind='stable') \
        .reset_index(drop=True)
    led = led[~led['strategy'].isin(VETO_STRATEGIES)] \
        .reset_index(drop=True)
    return cool1_filter_df(led), accepted


# ------------------------------------------------- panel form --
def _stream_state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


def _load_stream():
    try:
        with open(_stream_state_path()) as fh:
            return json.load(fh).get('stream', [])
    except Exception:
        return []


def _save_stream(stream):
    p = _stream_state_path()
    os.makedirs(os.path.dirname(os.path.abspath(p)),
                exist_ok=True)
    with open(p, 'w') as fh:
        json.dump({'system': SYSTEM_NAME, 'stream': stream}, fh)


def _resolve_pick(rec, frames):
    """Re-simulate one recorded pick's outcome with the
    walk's own simulator once the symbol frame covers
    its full 48h window (verbatim cycle86e). Returns
    gross_pips or None."""
    try:
        from core.new8_features import (frame_to_research,
                                        pip_size_new8)
        from core.new8_walk import ohlc_from_frame, sim_fixed_vec
        fr = frames.get(rec['symbol'])
        if fr is None or not len(fr):
            return None
        rfr, _ = frame_to_research(fr)
        ohlc = ohlc_from_frame(rfr)
        ent = pd.Timestamp(rec['entry_time'])
        if ohlc['dt'][-1] < ent + pd.Timedelta(hours=48):
            return None
        if rec.get('tp_pips_used') is None \
                or rec.get('sl_pips_used') is None:
            return None
        pos = int(ohlc['pos_of'].get_indexer([ent])[0])
        if pos < 0:
            return None
        pip = pip_size_new8(rec['symbol'])
        r = sim_fixed_vec(ohlc['o'], ohlc['h'], ohlc['l'],
                          ohlc['c'], [pos], rec['direction'],
                          [float(rec['tp_pips_used'])],
                          [float(rec['sl_pips_used'])], pip,
                          max_hold=48, cost=2.5)
        return float(r['gross_pips'][0])
    except Exception:
        return None


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    """One-check C10_EXC form: cycle86c panel entries;
    the excised strategy is removed BEFORE the PC14 +
    slot veto so a freed check can be answered by the
    mar_rp refill (the batch construction's semantics);
    then the W6 veto; then causal cool1 over this
    system's persisted emitted-pick stream (see the
    module docstring's inherited caveat)."""
    from core.new8_candidate import (CandidateContext,
                                     candidate_signal_row)
    from core.new8_features import pc14_keep, pc14_m15_features
    entries = _c86c.panel_entries(
        frames, check_time_utc, m15_frames=m15_frames,
        open_symbols=open_symbols)
    if entries is not None and entries.attrs.get("status"):
        return entries
    vetoed_strategies = set()
    if entries is not None and len(entries):
        kept_rows = []
        for _, r in entries.iterrows():
            strat = r.get('strategy', r.get('equation'))
            veto = strat in (EXCISED_STRATEGY,
                             _c86d.SLOT_VETO_STRATEGY)
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
    if entries is None:
        entries = pd.DataFrame()
    if not len(entries):
        # refill: first mar_rp signal row at this check
        # that is not a vetoed pick and whose symbol is
        # not open (refill picks are not PC14-checked,
        # matching the graded construction).
        ctx = CandidateContext(frames, m15_frames, DESIGNS)
        rows = ctx.rows_at(DESIGN, pd.Timestamp(check_time_utc))
        for eq_id, row in rows.items():
            if eq_id in vetoed_strategies:
                continue
            if row['symbol'] in tuple(open_symbols or ()):
                continue
            entries = pd.DataFrame([candidate_signal_row(row)])
            break
    if len(entries):
        strat = entries.get('strategy', entries.get('equation'))
        entries = entries[~strat.isin(VETO_STRATEGIES)] \
            .reset_index(drop=True)
    chk = pd.Timestamp(check_time_utc)
    stream = _load_stream()
    for rec in stream:
        if rec.get('gross_pips') is None:
            g = _resolve_pick(rec, frames)
            if g is not None:
                rec['gross_pips'] = g
    skip = False
    if stream:
        last = stream[-1]
        if (last.get('gross_pips') is not None
                and float(last['gross_pips']) - 2.5 <= 0
                and not last.get('cool_consumed')):
            skip = True
            last['cool_consumed'] = True
    if skip:
        _save_stream(stream)
        return entries.iloc[0:0]
    if len(entries):
        r = entries.iloc[0]
        rec = {'check': str(chk), 'symbol': r['symbol'],
               'direction': r['direction'],
               'strategy': r.get('strategy', r.get('equation')),
               'entry_time': str(chk - pd.Timedelta(minutes=30)),
               'entry_px': float(r['entry_px'])
               if 'entry_px' in r else None,
               'tp_pips_used': float(r['tp_pips_used'])
               if 'tp_pips_used' in r else None,
               'sl_pips_used': float(r['sl_pips_used'])
               if 'sl_pips_used' in r else None,
               'gross_pips': None, 'cool_consumed': False}
        if rec['tp_pips_used'] is None:
            rec['unresolvable'] = True
        stream.append(rec)
    _save_stream(stream)
    return entries
