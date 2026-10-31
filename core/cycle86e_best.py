"""Cycle 86E -- March candidate, R3 surgery winner D10
(port proof mar_portproof.md; fresh exact app replay
mar_replay.md, PASS, 2026-10-31):

  cycle86d construction (M18: cycle86c combined stream
  + PC14 M15 veto + EURAUD h12 b6v slot veto + mar_rp
  refill, 557 picks)
  + veto of FB_EURGBP_h16_2 (the stream's only
    DISC-losing equation, 12 picks in the 86d ledger)
  + veto of W6_rpe_vx_flow_x_rp_q_mom_x_rsi14_
    43d2f898_S_EURAUD_h16_0.88x15.2_H48 (the combined
    stream's AUDIT-worst leg)
  + cool1: a stateful filter over the merged stream --
    after a kept pick whose simulated net
    (gross_pips - 2.5) <= 0, skip exactly the next
    pick. Dropped picks do not extend the cooldown.

Validated numbers (R3 Mar D10, @2.5, app-code replay
proven 515/515 exact vs the graded ledger, control
557/557 exact, 2026-10-31): DISC leftover 83.23%
(incumbent 79.89%), AUDIT leftover 56.08% (incumbent
46.52%, strictly greater); LCT P 87.07% / 5th-pct
76.47 (middle PASS); Monte Carlo middle PASS (DD
p95 141.61 vs incumbent 190.02); PBO 0.00 / DSR 1.0;
decay PASS. The cool1 arm is load-bearing:
neighbouring forms without it fail single arms
(D08/D09, mar_portproof.md).

Named live-servability caveat (of record since the
port wave): the graded cool1 reads each pick's
simulated net in check order from the completed
ledger. Live, a still-open trade's net is unknowable
at the next check, so the panel form below applies
cool1 causally -- a kept pick's net is resolved by
re-simulation (core.new8_walk.sim_fixed_vec, the
walk's own simulator) once the frame covers its full
48h window, and the cooldown fires at the first check
after resolution. Live cool1 timing therefore
differs from the graded ledger rule; the causal
variant has not been separately re-graded.

Check hours: the March grid (11, 16, 17 UTC) --
CYCLE86D_CHECK_HOURS via cycle86d.
"""

from __future__ import annotations

import json
import os

import pandas as pd

import core.cycle86d_best as _c86d
from core.cycle86d_best import (CYCLE86D_CHECK_HOURS,
                                build_cycle86d_ledger,
                                fetch_cycle86d_m15_frames)

CYCLE86E_CHECK_HOURS = CYCLE86D_CHECK_HOURS
DESIGN = "mar_rp"
DESIGNS = ("mar_rp",)
SYSTEM_NAME = "cycle86e"
VETO_STRATEGIES = (
    'FB_EURGBP_h16_2',
    'W6_rpe_vx_flow_x_rp_q_mom_x_rsi14_43d2f898_S_'
    'EURAUD_h16_0.88x15.2_H48',
)


def evaluate_cycle86e_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None
                              ) -> pd.DataFrame:
    return _c86d.evaluate_cycle86d_signals(
        frames, check_time_utc, m15_frames=m15_frames)


def select_cycle86e_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    return _c86d.select_cycle86d_entries(
        signals, open_symbols=open_symbols)


def is_cycle86e_check_time(ts) -> bool:
    return _c86d.is_cycle86d_check_time(ts)


def fetch_cycle86e_m15_frames(state=None):
    return fetch_cycle86d_m15_frames(state=state)


# ------------------------------------------------ ledger form --
def cool1_filter_df(df: pd.DataFrame) -> pd.DataFrame:
    """cool1 over a merged pick stream (rows pre-sorted
    by check, stable): after a KEPT pick with simulated
    net (gross_pips - 2.5) <= 0, skip exactly the next
    pick. Verbatim research seq_filter('cool1')."""
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


def build_cycle86e_ledger(incumbent: pd.DataFrame, walks: dict,
                          m15_frames: dict):
    """The D10 ledger construction: the shipped M18
    (cycle86d) ledger, then the two named-strategy
    vetoes, then cool1 over the merged stream."""
    led, _accepted = build_cycle86d_ledger(incumbent, walks,
                                           m15_frames)
    led = led.sort_values('check', kind='stable') \
        .reset_index(drop=True)
    led = led[~led['strategy'].isin(VETO_STRATEGIES)] \
        .reset_index(drop=True)
    return cool1_filter_df(led)


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
    its full 48h window. Returns gross_pips or None
    (window not covered yet / inputs unavailable)."""
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
    """One-check D10 form: cycle86d panel entries, then
    the two named vetoes, then causal cool1 over this
    system's persisted emitted-pick stream (see the
    module docstring's live-servability caveat: a kept
    pick's net is resolved by re-simulation once its
    48h window is covered, and the cooldown fires at
    the first check after resolution)."""
    entries = _c86d.panel_entries(frames, check_time_utc,
                                  m15_frames=m15_frames,
                                  open_symbols=open_symbols)
    if entries is not None and entries.attrs.get('status'):
        return entries
    if entries is None:
        entries = pd.DataFrame()
    if len(entries):
        strat = entries.get('strategy', entries.get('equation'))
        entries = entries[~strat.isin(VETO_STRATEGIES)] \
            .reset_index(drop=True)
    chk = pd.Timestamp(check_time_utc)
    stream = _load_stream()
    # resolve any emitted picks whose windows have closed
    for rec in stream:
        if rec.get('gross_pips') is None:
            g = _resolve_pick(rec, frames)
            if g is not None:
                rec['gross_pips'] = g
    # cooldown state: the last kept pick before this
    # check, if its resolved net <= 0 and the cooldown
    # has not already been consumed by a later check.
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
