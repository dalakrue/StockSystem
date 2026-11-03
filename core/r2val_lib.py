"""R2-lead shared transform library -- the 10-CYCLE
ROUND 2 lead forms (work_10cyc_r2, user order 2026-11-03),
ported for their validate-and-replace lane
(work_r2_validate).

Each form is stream surgery on its shipped incumbent's
delivered stream, applied in stream (entry) order:

  NOV cycle93aa (over 93x): EXPOSURE-SKIP 6% -- a
    realised-balance walk over the incumbent stream
    (START $80, formula lots at the carried N/3): a pick
    is skipped when open adverse exposure of kept picks
    plus its own would exceed 6% of the realised balance
    (designs.exposure_skip verbatim, prior = the 93x
    stream), then the ratio cap at 4xTP reprices every
    delivered outcome on its M15-close profile.
  DEC cycle94j (over 94i): DAILY-LOCKOUT max 1 -- after
    1 kept trade that EXITED on a UTC day closed as a
    loss, the day's remaining picks are skipped
    (designs.daily_lockout verbatim, prior = the 94i
    stream), outcomes repriced at the 4xTP cap.
  FEB cycle85i (over 85g): the UTC-11 check hour's picks
    are never delivered (designs.hour_drop verbatim) and
    every delivered outcome is repriced at the 4xTP cap
    (85g's own cap was 5xTP).
  MAR cycle86h (over 86g): EURAUD picks are never
    delivered (designs.symbol_drop verbatim); outcomes
    repriced at the 4xTP cap (identical to 86g's own on
    kept rows).
  APR cycle87h (over 87g): EXPOSURE-SKIP 6% like Nov,
    on April's declared POOL basis, with the walk
    accounting on 87g's own walk outcomes (the 30-pip
    stop-tightened profile outcomes, before the ratio
    cap), prior = the 87g stream.

Arithmetic mirrors core/sl4_lib.py (identical to
core/d21rc_lib.py) operation-for-operation; the design
walks are designs.py verbatim with a prior mask. The
layer classes are the incremental forms of the same
rules for the cycle modules' state walks: candidates
are decided on arrival, in entry order, and a decision
never revisits.
"""

from __future__ import annotations

import numpy as np

COST = 2.5
START = 80.0
RATIO_MULT = 4.0
DAY_S = 86400


# --------------------------------------------------- array form --
def formula_lot(balance_profit, n_used):
    return 0.01 * (START / n_used + max(balance_profit, 0.0)
                   / n_used)


def stop_tighten_arr(prof_list, caps, base_outcome):
    """designs.stop_tighten_arr verbatim: per-trade stop
    caps (pips) repriced on the trades' floating
    profiles."""
    net = np.asarray(base_outcome, dtype=np.float64).copy()
    caps = np.asarray(caps, dtype=np.float64)
    for i in range(len(net)):
        S = caps[i]
        if S is None or not np.isfinite(S):
            continue
        prof = prof_list[i]
        if len(prof) == 0:
            continue
        gross_final = net[i] + COST
        if float(prof.min()) > -S:
            continue
        hit_stop = int(np.argmax(prof <= -S))
        if gross_final > 0:
            tp_idx = np.where(prof >= gross_final)[0]
            tp_first = int(tp_idx[0]) if len(tp_idx) else len(prof)
            if hit_stop < tp_first:
                net[i] = -S - COST
        else:
            if -S > gross_final:
                net[i] = -S - COST
    return net


def ratio_caps(tp, sl):
    """Per-trade capped stop: min(assigned stop, 4 x TP)."""
    return np.minimum(np.asarray(sl, dtype=np.float64),
                      RATIO_MULT * np.asarray(tp, dtype=np.float64))


def walk_outcome(net, prof_list, walk_cap):
    """The walk/accounting outcome base: net itself, or
    net stop-tightened at walk_cap pips (April: 30)."""
    if walk_cap is None:
        return np.asarray(net, dtype=np.float64).copy()
    caps = np.full(len(net), float(walk_cap))
    return stop_tighten_arr(prof_list, caps, net)


def exposure_keep(entry, exit_, outcome, pwv, pv, prior,
                  n_used, cap_frac):
    """designs.exposure_skip verbatim (prior mask):
    returns the boolean keep mask. Decisions in entry
    order (stable); KEPT trades' walk outcomes credited
    at their exits; rows outside `prior` are never
    candidates."""
    entry = np.asarray(entry)
    exit_ = np.asarray(exit_)
    outcome = np.asarray(outcome, dtype=np.float64)
    pwv = np.asarray(pwv, dtype=np.float64)
    pv = np.asarray(pv, dtype=np.float64)
    prior = np.asarray(prior, dtype=bool)
    n = len(outcome)
    keep = np.zeros(n, bool)
    open_kept = []
    bal = START
    profit = 0.0
    events = sorted(range(n), key=lambda i: entry[i])
    closed = sorted(range(n), key=lambda i: exit_[i])
    ci = 0
    lots = {}
    for i in events:
        while ci < n and exit_[closed[ci]] <= entry[i]:
            j = closed[ci]
            if keep[j]:
                pnl = outcome[j] * pv[j] * lots[j]
                bal += pnl
                profit += pnl
            ci += 1
        if not prior[i]:
            continue
        open_kept = [(e, a) for (e, a) in open_kept
                     if e > entry[i]]
        lot_i = formula_lot(profit, n_used)
        cand = abs(float(pwv[i])) * float(pv[i]) * lot_i
        tot = sum(a for _e, a in open_kept) + cand
        if tot <= cap_frac * max(bal, 1.0):
            keep[i] = True
            lots[i] = lot_i
            open_kept.append((int(exit_[i]), cand))
    return keep


def lockout_keep(entry, exit_, outcome, prior, max_losses):
    """designs.daily_lockout verbatim (prior mask):
    skip a day's remaining entries after max_losses kept
    trades that EXITED that UTC day closed as losses
    (loss judged on the walk outcome)."""
    entry = np.asarray(entry)
    exit_ = np.asarray(exit_)
    outcome = np.asarray(outcome, dtype=np.float64)
    prior = np.asarray(prior, dtype=bool)
    n = len(outcome)
    keep = np.zeros(n, bool)
    closed = sorted(range(n), key=lambda i: exit_[i])
    ci = 0
    day_losses = {}
    for i in sorted(range(n), key=lambda i: entry[i]):
        while ci < n and exit_[closed[ci]] <= entry[i]:
            j = closed[ci]
            if keep[j] and outcome[j] < 0:
                day = int(exit_[j] // DAY_S)
                day_losses[day] = day_losses.get(day, 0) + 1
            ci += 1
        if not prior[i]:
            continue
        day = int(entry[i] // DAY_S)
        keep[i] = day_losses.get(day, 0) < max_losses
    return keep


def transform_exposure(entry, exit_, net, prof_list, pwv, pv,
                       tp, sl, prior, n_used, cap_frac,
                       walk_cap=None):
    """Exposure-skip form (Nov R1 / Apr R1). Returns
    (keep, outcome): outcome is the full-length array
    repriced at the 4xTP cap on the walk outcome base;
    the delivered stream is outcome[keep]."""
    w = walk_outcome(net, prof_list, walk_cap)
    keep = exposure_keep(entry, exit_, w, pwv, pv, prior,
                         n_used, cap_frac)
    outcome = stop_tighten_arr(prof_list, ratio_caps(tp, sl), w)
    return keep, outcome


def transform_lockout(entry, exit_, net, prof_list, tp, sl,
                      prior, max_losses):
    """Daily-lockout form (Dec R6)."""
    keep = lockout_keep(entry, exit_, net, prior, max_losses)
    outcome = stop_tighten_arr(prof_list, ratio_caps(tp, sl),
                               net)
    return keep, outcome


def transform_mask(entry, sym, net, prof_list, tp, sl, prior,
                   hours=(), syms=()):
    """Pure delivery-mask forms (Feb R9 hour drop /
    Mar R7 symbol drop) with outcomes repriced at the
    4xTP cap."""
    entry = np.asarray(entry)
    keep = np.asarray(prior, dtype=bool).copy()
    if hours:
        hr = (entry % DAY_S) // 3600
        keep &= ~np.isin(hr, list(hours))
    if syms:
        keep &= ~np.isin(np.asarray(sym), list(syms))
    outcome = stop_tighten_arr(prof_list, ratio_caps(tp, sl),
                               net)
    return keep, outcome


# ------------------------------------------------- stream layer --
def _reprice_one(net_i, prof_i, tp_i, sl_i):
    caps = np.array([min(float(sl_i), RATIO_MULT * float(tp_i))])
    out = stop_tighten_arr(
        [np.asarray(prof_i, dtype=np.float64)], caps,
        np.array([float(net_i)]))
    return float(out[0])


class ExposureLayerR2:
    """Incremental exposure-skip (Nov/Dec-style accounting
    on the walk outcome). Feed incumbent delivered rows
    in stream order via decide(); each row must carry:
    entry_s, exit_s, net (base net @2.5), pwv, pv, tp,
    sl, prof. decide() returns the delivered net (the
    walk outcome repriced at the 4xTP cap) if kept, else
    None. Pointer semantics mirror exposure_keep: a kept
    trade's P&L is credited only when a LATER entry event
    passes its exit; a degenerate trade (exit <= entry)
    never credits."""

    def __init__(self, n_used, cap_frac, walk_cap=None):
        self.n_used = float(n_used)
        self.cap_frac = float(cap_frac)
        self.walk_cap = walk_cap
        self.bal = START
        self.profit = 0.0
        self.open_kept = []          # [(exit_s, exposure)]
        self._pending_exits = []     # [(exit_s, walk_net, pv, lot)]

    def _walk_net(self, row):
        if self.walk_cap is None:
            return float(row['net'])
        caps = np.array([float(self.walk_cap)])
        out = stop_tighten_arr(
            [np.asarray(row['prof'], dtype=np.float64)], caps,
            np.array([float(row['net'])]))
        return float(out[0])

    def _process_exits(self, upto_entry):
        pend = self._pending_exits
        pend.sort(key=lambda z: z[0])
        k = 0
        while k < len(pend) and pend[k][0] <= upto_entry:
            _e, net_j, pv_j, lot_j = pend[k]
            pnl = net_j * pv_j * lot_j
            self.bal += pnl
            self.profit += pnl
            k += 1
        del pend[:k]

    def decide(self, row):
        entry_i = int(row['entry_s'])
        self._process_exits(entry_i)
        self.open_kept = [(e, a) for (e, a) in self.open_kept
                          if e > entry_i]
        lot_i = formula_lot(self.profit, self.n_used)
        cand = abs(float(row['pwv'])) * float(row['pv']) * lot_i
        tot = sum(a for _e, a in self.open_kept) + cand
        if tot > self.cap_frac * max(self.bal, 1.0):
            return None
        self.open_kept.append((int(row['exit_s']), cand))
        w = self._walk_net(row)
        if int(row['exit_s']) > entry_i:
            self._pending_exits.append(
                (int(row['exit_s']), w, float(row['pv']), lot_i))
        caps = np.array([min(float(row['sl']),
                             RATIO_MULT * float(row['tp']))])
        out = stop_tighten_arr(
            [np.asarray(row['prof'], dtype=np.float64)], caps,
            np.array([w]))
        return float(out[0])


class LockoutLayerR2:
    """Incremental daily-lockout (Dec R6). Feed incumbent
    delivered rows in stream order; row keys: entry_s,
    exit_s, net (base net @2.5), tp, sl, prof. decide()
    returns the delivered net (repriced at the 4xTP cap)
    if kept, else None. A kept trade's loss is counted
    only when a LATER entry event passes its exit
    (pointer semantics of lockout_keep); a degenerate
    trade (exit <= entry) never counts."""

    def __init__(self, max_losses=1):
        self.max_losses = int(max_losses)
        self.day_losses = {}
        self._pending_exits = []     # [(exit_s, walk_net)]

    def _process_exits(self, upto_entry):
        pend = self._pending_exits
        pend.sort(key=lambda z: z[0])
        k = 0
        while k < len(pend) and pend[k][0] <= upto_entry:
            e_j, net_j = pend[k]
            if net_j < 0:
                day = int(e_j // DAY_S)
                self.day_losses[day] = \
                    self.day_losses.get(day, 0) + 1
            k += 1
        del pend[:k]

    def decide(self, row):
        entry_i = int(row['entry_s'])
        self._process_exits(entry_i)
        day = int(entry_i // DAY_S)
        if self.day_losses.get(day, 0) >= self.max_losses:
            return None
        if int(row['exit_s']) > entry_i:
            self._pending_exits.append(
                (int(row['exit_s']), float(row['net'])))
        return _reprice_one(row['net'], row['prof'],
                            row['tp'], row['sl'])


class MaskLayerR2:
    """Incremental pure delivery mask (Feb R9 / Mar R7).
    Row keys: entry_s, sym, net, tp, sl, prof. decide()
    returns None for masked rows, else the delivered net
    repriced at the 4xTP cap."""

    def __init__(self, hours=(), syms=()):
        self.hours = set(int(h) for h in hours)
        self.syms = set(str(s) for s in syms)

    def decide(self, row):
        hr = (int(row['entry_s']) % DAY_S) // 3600
        if hr in self.hours or str(row.get('sym', '')) in self.syms:
            return None
        return _reprice_one(row['net'], row['prof'],
                            row['tp'], row['sl'])
