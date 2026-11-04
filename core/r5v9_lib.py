"""R5-VALIDATE9 shared transform library -- the
Round 5 counted forms (work_20cyc_r5 Phase 1 +
work_r5_sl3_10cyc Phase 2, user order 2026-11-04),
ported for their validate-and-replace lane
(work_r5_validate9).

Each form is stream surgery on its shipped
incumbent's stream over the month's pool, applied
in stream (entry) order:

  DEC S2 (over 94i): PARTNER-ADD >=2 UNANIMOUS --
    pool rows the 94i stream did not keep are added
    when their entry timestamp carries >=2 kept 94i
    rows and every kept row at that timestamp has
    the candidate row's side; outcomes repriced at
    the 4xTP cap.
  DEC S7 (over 94i): PARTNER-ADD >=1 restricted to
    the month's two lowest-epd check hours, then
    EXPOSURE-SKIP 12% over the union (realised-
    balance walk, START $80, formula lots at the
    carried N/3); outcomes repriced at 4xTP.
  JAN S9 (over 60d): PARTNER-ADD >=1 restricted to
    the incumbent's two best discovery weekdays;
    outcomes repriced at 4xTP.
  MAR S18 / APR S18: DROP WORST DISC HOUR (Mar 12
    UTC / Apr 19 UTC) from the incumbent stream,
    then PARTNER-ADD >=1 computed against the
    surviving stream; outcomes repriced at 4xTP
    (April on its stop-tighten-30 walk basis).
  FEB T4 (over 85g): the incumbent stream minus
    its worst DISC hour (11 UTC) settled through
    EXPOSURE-SKIP 10%; outcomes repriced at the
    3xTP cap (the form's own SL<=3 law).
  FEB T9 / APR T9: worst DISC hour dropped, then
    PARTNER-ADD >=1 against the surviving stream,
    then EXPOSURE-SKIP 10% over the union; outcomes
    repriced at 3xTP (April on its tighten-30 walk
    basis).
  APR T4 (over 87h): the incumbent stream minus
    hour 19 UTC settled through EXPOSURE-SKIP 10%
    on the tighten-30 walk basis; outcomes
    repriced at 3xTP.

Arithmetic mirrors core/r2val_lib.py /
core/redoval_lib.py operation-for-operation; the
exposure walk is designs.exposure_skip verbatim
with a prior mask. The layer classes are the
incremental forms of the same rules for the cycle
modules: partner rules are decided per entry-
timestamp group (the rule is a property of the
group), exposure rules row by row in entry order,
and a decision never revisits.
"""

from __future__ import annotations

import numpy as np

COST = 2.5
START = 80.0
DAY_S = 86400


# --------------------------------------------------- array form --
def formula_lot(balance_profit, n_used):
    return 0.01 * (START / n_used + max(balance_profit, 0.0)
                   / n_used)


def stop_tighten_arr(prof_list, caps, base_outcome):
    """designs.stop_tighten_arr verbatim: per-trade
    stop caps (pips) repriced on the trades' floating
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


def ratio_caps(tp, sl, mult):
    """Per-trade capped stop: min(assigned stop,
    mult x TP)."""
    return np.minimum(np.asarray(sl, dtype=np.float64),
                      float(mult)
                      * np.asarray(tp, dtype=np.float64))


def walk_outcome(net, prof_list, walk_cap):
    """The walk/accounting outcome base: net itself,
    or net stop-tightened at walk_cap pips (April:
    30)."""
    if walk_cap is None:
        return np.asarray(net, dtype=np.float64).copy()
    caps = np.full(len(net), float(walk_cap))
    return stop_tighten_arr(prof_list, caps, net)


def partner_add_mask(entry, side, prior, min_kept, unanimous):
    """screenR5.partner_add verbatim: non-prior pool
    rows sharing an entry timestamp with >= min_kept
    kept prior rows; unanimous=True requires every
    kept row at the timestamp to carry the
    candidate's side, otherwise the candidate's side
    need only appear among the kept rows' sides."""
    entry = np.asarray(entry)
    side = np.asarray(side)
    prior = np.asarray(prior, dtype=bool)
    add = np.zeros(len(entry), bool)
    groups = {}
    for i, t in enumerate(entry):
        groups.setdefault(int(t), []).append(i)
    for _t, idxs in groups.items():
        kept = [i for i in idxs if prior[i]]
        if len(kept) < min_kept:
            continue
        kept_sides = {int(side[j]) for j in kept}
        for i in idxs:
            if prior[i]:
                continue
            if unanimous:
                if kept_sides == {int(side[i])}:
                    add[i] = True
            elif int(side[i]) in kept_sides:
                add[i] = True
    return add


def exposure_keep(entry, exit_, outcome, pwv, pv, prior,
                  n_used, cap_frac):
    """designs.exposure_skip verbatim (prior mask):
    returns the boolean keep mask. Decisions in
    entry order (stable); KEPT trades' walk outcomes
    credited at their exits; rows outside `prior`
    are never candidates."""
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


def _final(net, prof_list, tp, sl, mult, walk_cap):
    w = walk_outcome(net, prof_list, walk_cap)
    outcome = stop_tighten_arr(prof_list,
                               ratio_caps(tp, sl, mult), w)
    return w, outcome


def transform_partner(entry, side, net, prof_list, tp, sl,
                      prior, min_kept, unanimous, mult,
                      ref_mask=None, restrict_mask=None,
                      walk_cap=None):
    """Partner-add forms (Dec S2; Jan S9 with a
    restriction mask on added rows; Mar/Apr S18 with
    a ref_mask dropping an hour from the reference
    stream BEFORE the partner rule is computed).
    Returns (keep, outcome)."""
    prior = np.asarray(prior, dtype=bool)
    ref = prior if ref_mask is None \
        else prior & np.asarray(ref_mask, dtype=bool)
    add = partner_add_mask(entry, side, ref, min_kept,
                           unanimous)
    if restrict_mask is not None:
        add = add & np.asarray(restrict_mask, dtype=bool)
    keep = ref | add
    _w, outcome = _final(net, prof_list, tp, sl, mult,
                         walk_cap)
    return keep, outcome


def transform_partner_exposure(entry, exit_, side, net,
                               prof_list, pwv, pv, tp, sl,
                               prior, n_used, cap_frac, mult,
                               ref_mask=None,
                               restrict_mask=None,
                               walk_cap=None):
    """Add-then-govern forms (Dec S7 with an hour
    restriction on added rows; Feb/Apr T9 with a
    ref_mask dropping an hour first): the union of
    the (possibly hour-dropped) incumbent stream
    with its >=1 same-side partner rows, settled
    through the exposure walk at cap_frac (prior =
    the union); outcomes repriced at the mult x TP
    cap on the walk outcome base."""
    prior = np.asarray(prior, dtype=bool)
    ref = prior if ref_mask is None \
        else prior & np.asarray(ref_mask, dtype=bool)
    add = partner_add_mask(entry, side, ref, 1, False)
    if restrict_mask is not None:
        add = add & np.asarray(restrict_mask, dtype=bool)
    union = ref | add
    w = walk_outcome(net, prof_list, walk_cap)
    keep = exposure_keep(entry, exit_, w, pwv, pv, union,
                         n_used, cap_frac)
    outcome = stop_tighten_arr(prof_list,
                               ratio_caps(tp, sl, mult), w)
    return keep, outcome


def transform_exposure(entry, exit_, net, prof_list, pwv,
                       pv, tp, sl, prior, n_used, cap_frac,
                       mult, walk_cap=None):
    """Exposure-skip forms over a given prior mask
    (Feb T4 / Apr T4: the hour-dropped incumbent
    stream). Outcomes repriced at the mult x TP cap
    on the walk outcome base."""
    w = walk_outcome(net, prof_list, walk_cap)
    keep = exposure_keep(entry, exit_, w, pwv, pv,
                         np.asarray(prior, dtype=bool),
                         n_used, cap_frac)
    outcome = stop_tighten_arr(prof_list,
                               ratio_caps(tp, sl, mult), w)
    return keep, outcome


# ------------------------------------------------- stream layer --
def _hour_of(entry_s):
    return (int(entry_s) % DAY_S) // 3600


def _weekday_of(entry_s):
    return ((int(entry_s) // DAY_S) + 3) % 7  # Mon=0


def _walk_net_of(net_i, prof_i, walk_cap):
    if walk_cap is None:
        return float(net_i)
    caps = np.array([float(walk_cap)])
    out = stop_tighten_arr(
        [np.asarray(prof_i, dtype=np.float64)], caps,
        np.array([float(net_i)]))
    return float(out[0])


def _reprice_one(net_i, prof_i, tp_i, sl_i, mult, walk_cap):
    w = _walk_net_of(net_i, prof_i, walk_cap)
    caps = np.array([min(float(sl_i),
                         float(mult) * float(tp_i))])
    out = stop_tighten_arr(
        [np.asarray(prof_i, dtype=np.float64)], caps,
        np.array([w]))
    return float(out[0])


def _union_flags(rows, min_kept, unanimous, ref_drop_hour,
                 restrict_hours, restrict_weekdays):
    """Partner rule for one entry-timestamp group.
    rows: dicts with 'entry_s', 'side', 'base_keep'.
    A base row first survives the optional hour
    drop; partner adds are computed against the
    surviving base rows and may be restricted to
    given check hours / weekdays (of the row's own
    timestamp — uniform within a group)."""
    ref = []
    for r in rows:
        b = bool(r['base_keep'])
        if b and ref_drop_hour is not None \
                and _hour_of(r['entry_s']) == ref_drop_hour:
            b = False
        ref.append(b)
    kept_sides = {int(rows[i]['side'])
                  for i in range(len(rows)) if ref[i]}
    n_kept = sum(ref)
    flags = []
    for i, r in enumerate(rows):
        if ref[i]:
            flags.append(True)
            continue
        ok = n_kept >= min_kept
        if ok:
            if unanimous:
                ok = kept_sides == {int(r['side'])}
            else:
                ok = int(r['side']) in kept_sides
        if ok and restrict_hours is not None:
            ok = _hour_of(r['entry_s']) in restrict_hours
        if ok and restrict_weekdays is not None:
            ok = _weekday_of(r['entry_s']) \
                in restrict_weekdays
        flags.append(bool(ok))
    return flags


class GroupPartnerLayer:
    """Partner-add incremental form (Dec S2; Jan S9
    with restrict_weekdays; Mar/Apr S18 with
    ref_drop_hour). Feed one entry-timestamp group
    at a time via decide_group(); each row must
    carry: entry_s, side (int), base_keep (bool),
    net, tp, sl, prof. Returns a list parallel to
    rows with the delivered net (repriced at
    mult x TP on the walk base) for union rows,
    else None. Stateless across groups."""

    def __init__(self, min_kept=1, unanimous=False,
                 mult=4.0, walk_cap=None, ref_drop_hour=None,
                 restrict_hours=None,
                 restrict_weekdays=None):
        self.min_kept = int(min_kept)
        self.unanimous = bool(unanimous)
        self.mult = float(mult)
        self.walk_cap = walk_cap
        self.ref_drop_hour = ref_drop_hour
        self.restrict_hours = restrict_hours
        self.restrict_weekdays = restrict_weekdays

    def decide_group(self, rows):
        flags = _union_flags(rows, self.min_kept,
                             self.unanimous,
                             self.ref_drop_hour,
                             self.restrict_hours,
                             self.restrict_weekdays)
        return [_reprice_one(r['net'], r['prof'], r['tp'],
                             r['sl'], self.mult,
                             self.walk_cap) if f else None
                for r, f in zip(rows, flags)]


class _ExposureWalk:
    """The exposure walk shared by the exposure
    layers: pointer semantics mirror exposure_keep
    — a kept trade's walk-outcome P&L is credited
    only when a LATER entry event passes its exit;
    a degenerate trade (exit <= entry) never
    credits."""

    def __init__(self, n_used, cap_frac, mult, walk_cap):
        self.n_used = float(n_used)
        self.cap_frac = float(cap_frac)
        self.mult = float(mult)
        self.walk_cap = walk_cap
        self.bal = START
        self.profit = 0.0
        self.open_kept = []          # [(exit_s, exposure)]
        self._pending_exits = []     # [(exit_s, walk_net, pv, lot)]

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

    def decide_row(self, row):
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
        if int(row['exit_s']) > entry_i:
            self._pending_exits.append(
                (int(row['exit_s']),
                 _walk_net_of(row['net'], row['prof'],
                              self.walk_cap),
                 float(row['pv']), lot_i))
        return _reprice_one(row['net'], row['prof'],
                            row['tp'], row['sl'], self.mult,
                            self.walk_cap)


class ExposureLayerV9(_ExposureWalk):
    """Exposure-skip incremental form over a prior
    stream (Feb T4 / Apr T4 — feed the prior
    (hour-dropped incumbent) rows in entry order via
    decide(); each row must carry: entry_s, exit_s,
    net, pwv, pv, tp, sl, prof. Returns the
    delivered net if kept, else None."""

    def decide(self, row):
        return self.decide_row(row)


class GroupPartnerExposureLayer(_ExposureWalk):
    """Add-then-govern incremental form (Dec S7
    with restrict_hours; Feb/Apr T9 with
    ref_drop_hour): partner-add >=1 union per
    entry-timestamp group, settled through the
    exposure walk. Feed one group at a time via
    decide_group(), groups in entry order, rows
    within a group in pool order; each row must
    carry: entry_s, exit_s, side (int), base_keep
    (bool), net, pwv, pv, tp, sl, prof. Returns a
    list parallel to rows with the delivered net
    for kept rows, else None."""

    def __init__(self, n_used, cap_frac, mult=4.0,
                 walk_cap=None, ref_drop_hour=None,
                 restrict_hours=None):
        super().__init__(n_used, cap_frac, mult, walk_cap)
        self.ref_drop_hour = ref_drop_hour
        self.restrict_hours = restrict_hours

    def decide_group(self, rows):
        flags = _union_flags(rows, 1, False,
                             self.ref_drop_hour,
                             self.restrict_hours, None)
        out = []
        for r, f in zip(rows, flags):
            if not f:
                out.append(None)
            else:
                out.append(self.decide_row(r))
        return out
