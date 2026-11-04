"""fixblocked_lib -- transforms for the FIX-THE-BLOCKED
lane (work_fix_blocked, GATES.md locked 2026-11-04):
the March S18 repair M1 over the shipped cycle86g
stream.

M1 = the Round-5 Mar S18 form (drop the worst DISC
hour, 12 UTC, from the reference stream, then
partner-add >=1 same-side rows, outcomes repriced at
the SL <= 4xTP cap) with ONE repair rule added: the
hour-12 excision does NOT apply to a base row whose
check timestamp (entry + 30 min) falls on the LAST
calendar day of its month. In the historical stream
this restores exactly one trade (EURAUD SELL, check
2022-03-31 12:30 UTC, net +36.43) and removes the
single red holdout week (2022-W13) that blocked S18
at EC22 check 8_weeks, leaving every other property
of the form unchanged.

Array form (transform_partner_m1) and incremental
form (GroupPartnerLayerM1) share the row rule; the
shared partner/repricing helpers are
core.r5v9_lib's, verbatim.
"""
from __future__ import annotations

import calendar
import datetime as _dt

import numpy as np

from core import r5v9_lib as _V

DROP_HOUR_UTC = 12
MULT = 4.0


def _is_month_final_check(entry_s):
    """True iff the check timestamp (entry + 30 min)
    falls on the last calendar day of its month
    (UTC)."""
    t = _dt.datetime.utcfromtimestamp(int(entry_s) + 1800)
    return t.day == calendar.monthrange(t.year, t.month)[1]


def m1_ref_mask(entry, prior):
    """Rows of the reference (incumbent) stream that
    survive the M1 hour rule: hour != DROP_HOUR_UTC,
    or the row's check date is the last day of its
    month."""
    entry = np.asarray(entry)
    hr = (entry % 86400) // 3600
    lastday = np.array([_is_month_final_check(t)
                        for t in entry])
    return np.asarray(prior, dtype=bool) & \
        ((hr != DROP_HOUR_UTC) | lastday)


def transform_partner_m1(entry, side, net, prof_list,
                         tp, sl, prior, mult=MULT):
    """Array form. Returns (keep, outcome)."""
    ref = m1_ref_mask(entry, prior)
    add = _V.partner_add_mask(entry, side, ref, 1, False)
    keep = ref | add
    _w, outcome = _V._final(net, prof_list, tp, sl,
                            mult, None)
    return keep, outcome


def _union_flags_m1(rows, min_kept, unanimous):
    """GroupPartnerLayer._union_flags with the M1
    reference rule: a base row is dropped iff its
    hour == DROP_HOUR_UTC and its check date is not
    the last day of its month."""
    ref = []
    for r in rows:
        b = bool(r['base_keep'])
        if b and _V._hour_of(r['entry_s']) == DROP_HOUR_UTC \
                and not _is_month_final_check(r['entry_s']):
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
        flags.append(bool(ok))
    return flags


class GroupPartnerLayerM1:
    """Incremental form of the M1 partner rule. Feed
    one entry-timestamp group at a time via
    decide_group(); each row must carry: entry_s,
    side (int), base_keep (bool), net, tp, sl, prof.
    Returns a list parallel to rows with the
    delivered net (repriced at mult x TP on the walk
    base) for union rows, else None. Stateless across
    groups."""

    def __init__(self, min_kept=1, unanimous=False,
                 mult=MULT):
        self.min_kept = int(min_kept)
        self.unanimous = bool(unanimous)
        self.mult = float(mult)

    def decide_group(self, rows):
        flags = _union_flags_m1(rows, self.min_kept,
                                self.unanimous)
        return [_V._reprice_one(r['net'], r['prof'],
                                r['tp'], r['sl'],
                                self.mult, None)
                if f else None
                for r, f in zip(rows, flags)]
