"""Risk-reduction tranche transforms (work_riskopt5), ported
for the validate-and-replace lane (work_riskopt5_validate).

Two forms, both finishing with the SL <= 4 x TP cap repriced
on the trade's M15-close floating profile
(designs.stop_tighten_arr verbatim, as in core/d21rc_lib):

  DECEMBER (cycle94i): cluster-skip 12h over the shipped
  cycle94h stream -- an entry is skipped when a KEPT trade
  sharing a currency (base or quote) opened within the
  previous 12 hours (designs.cluster_skip verbatim) -- then
  every kept trade's assigned stop capped at min(stop,
  4 x TP) on the EXACT per-trade basis.

  APRIL (cycle87g): stop-tighten 60p on cycle87f's stream
  (designs.stop_tighten verbatim: if the gross floating
  path reaches -60 before the outcome point, exit at -60),
  then the SL <= 4 x TP cap. April's cap basis is the pool
  basis (stageA.ratio_screen_arrays group-median stand-ins)
  -- no complete exact per-trade basis exists for April
  (work_rob_validate apr record); the module carries the
  same basis the research lane graded, and the validation
  verdict declares it.

The array functions replicate the research lanes' arithmetic
operation-for-operation so Gate A can prove bit-exact
agreement on the canonical streams. The StreamLayer classes
are the incremental forms for the cycle modules' state
walks: rows are decided on arrival, in entry order, and a
decision never revisits.
"""

from __future__ import annotations

import numpy as np

COST = 2.5
CLUSTER_HOURS = 12
APR_STOP_CAP = 60.0
RATIO = 4.0


def stop_tighten_arr(prof_list, caps, base_outcome):
    """designs.stop_tighten_arr verbatim: per-trade stop caps
    (pips) repriced on the trades' floating profiles."""
    net = np.asarray(base_outcome, dtype=np.float64).copy()
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


def ratio_caps4(tp, sl):
    """Per-trade capped stop: min(assigned stop, 4 x TP)."""
    return np.minimum(np.asarray(sl, dtype=np.float64),
                      RATIO * np.asarray(tp, dtype=np.float64))


def _currencies(sym):
    s = str(sym)
    return (s[:3], s[3:6])


def cluster_keep(entry, sym, prior_keep, hours=CLUSTER_HOURS):
    """designs.cluster_skip verbatim (window mode): iterate
    in array order; only prior-kept rows are candidates and
    blockers; a candidate is skipped when a kept trade
    sharing a currency opened < hours earlier."""
    n = len(entry)
    keep = np.zeros(n, bool)
    kept = []
    for i in range(n):
        if not prior_keep[i]:
            continue
        ci = _currencies(sym[i])
        ok = True
        for j in kept:
            cj = _currencies(sym[j])
            if ci[0] in cj or ci[1] in cj:
                if entry[i] - entry[j] < hours * 3600:
                    ok = False
                    break
        keep[i] = ok
        if ok:
            kept.append(i)
    return keep


def transform_dec(entry, sym, net, prof_list, tp, sl, prior_keep):
    """December C2 on a canonical stream: returns (keep,
    outcome); outcome is the full-length cap-4 repriced net
    array; the delivered stream is outcome[keep]."""
    keep = cluster_keep(entry, sym, prior_keep)
    outcome = stop_tighten_arr(prof_list, ratio_caps4(tp, sl), net)
    return keep, outcome


def transform_apr(net, prof_list, tp, sl):
    """April C4 on a canonical stream: stop-tighten 60p
    (caps array = 60 for every trade, designs.stop_tighten
    verbatim), then the SL <= 4 cap as the final step."""
    n = len(net)
    st60 = stop_tighten_arr(prof_list,
                            np.full(n, APR_STOP_CAP), net)
    return stop_tighten_arr(prof_list, ratio_caps4(tp, sl), st60)


# ------------------------------------------------- stream layers --
class ClusterLayer:
    """Incremental December form for a cycle module's state
    walk. Feed the incumbent form's DELIVERED rows in stream
    order via decide(); each row must carry: entry_s, sym,
    net (base net @2.5), tp, sl, prof. decide() returns the
    row's delivered net (float) if kept, else None.
    Arithmetic mirrors cluster_keep + stop_tighten_arr."""

    def __init__(self, hours=CLUSTER_HOURS):
        self.hours = float(hours)
        self.kept = []               # [(entry_s, (cur_a, cur_b))]

    def decide(self, row):
        entry_i = int(row['entry_s'])
        ci = _currencies(row['sym'])
        for e_j, cj in self.kept:
            if ci[0] in cj or ci[1] in cj:
                if entry_i - e_j < self.hours * 3600:
                    return None
        self.kept.append((entry_i, ci))
        caps = np.array([min(float(row['sl']),
                             RATIO * float(row['tp']))])
        out = stop_tighten_arr(
            [np.asarray(row['prof'], dtype=np.float64)],
            caps, np.array([float(row['net'])]))
        return float(out[0])


class StopCapLayer:
    """Incremental April form: stateless per-trade repricing
    (stop-tighten 60p, then the 4 x TP cap with the row's
    tp/sl basis values). decide(row) returns the delivered
    net (float); every row is delivered."""

    def decide(self, row):
        prof = [np.asarray(row['prof'], dtype=np.float64)]
        st60 = stop_tighten_arr(prof, np.array([APR_STOP_CAP]),
                                np.array([float(row['net'])]))
        caps = np.array([min(float(row['sl']),
                             RATIO * float(row['tp']))])
        out = stop_tighten_arr(prof, caps, st60)
        return float(out[0])
