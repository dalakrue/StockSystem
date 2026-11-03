"""Different-way winners' transforms (work_diffway), ported
for the validate-and-replace lane (work_diffway_validate).

Both forms sit on top of a shipped D21-RC incumbent stream
(cycle60c for January, cycle85g for February). Each is the
incumbent stream with ONE excision applied, and the ratio
cap tightened from the incumbent's 5 x TP to SL <= 4 x TP
(designs.stop_tighten_arr verbatim, repriced on the trade's
M15-close floating profile):

  JANUARY (cycle60d): the design
  mom_AUDUSD_h13_momS_T0.75_A1.0_0.75x8 is excised from
  the delivered stream. The excision is a pure mask over
  the incumbent's delivered (kept) stream: the underlying
  D21-RC exposure walk still processes the excised
  design's picks (they occupied exposure and credited
  P&L in the incumbent walk, exactly as in the research
  lane's mask), only their delivery is suppressed.

  FEBRUARY (cycle85h): every delivered trade whose entry
  falls in the worst-pair window [1643817600, 1643893200)
  (2022-02-02) is excised -- again a pure mask over the
  incumbent's delivered stream. The window is historical,
  so on live (future) entries the mask never fires; the
  live difference vs cycle85g is the 4 x TP cap.

Basis: EXACT per-trade TP/SL for both months
(work_rob_validate streams). The array functions
replicate the research lane's arithmetic
operation-for-operation so Gate A can prove bit-exact
agreement on the canonical streams; StreamLayer4 is the
incremental form for the cycle modules' state walks
(core/d21rc_lib.StreamLayer verbatim with the cap ratio
4.0 in place of 5.0): rows are decided on arrival, in
entry order, and a decision never revisits. A vetoed
row is still fed through decide() (advancing the walk
state, as the incumbent walk did) and its delivery is
suppressed by the caller.
"""

from __future__ import annotations

import numpy as np

from core.d21rc_lib import (CAP_FRAC, START, formula_lot,  # noqa: F401
                            stop_tighten_arr)

COST = 2.5
RATIO = 4.0

JAN_EXCISED_DESIGN = 'mom_AUDUSD_h13_momS_T0.75_A1.0_0.75x8'
FEB_WINDOW = (1643817600, 1643893200)


def ratio_caps4(tp, sl):
    """Per-trade capped stop: min(assigned stop, 4 x TP)."""
    return np.minimum(np.asarray(sl, dtype=np.float64),
                      RATIO * np.asarray(tp, dtype=np.float64))


def outcome_arr(prof_list, tp, sl, net):
    """Full-length outcomes repriced at the 4 x TP cap
    (designs.stop_tighten_arr verbatim via d21rc_lib)."""
    return stop_tighten_arr(prof_list, ratio_caps4(tp, sl), net)


def transform_jan(strat, prior_keep):
    """January candidate keep mask: the incumbent's kept
    stream minus the excised design's rows."""
    strat = np.asarray(strat).astype(str)
    return np.asarray(prior_keep, bool) & (strat != JAN_EXCISED_DESIGN)


def feb_veto_mask(entry):
    """True for rows excised by the February window."""
    entry = np.asarray(entry)
    return (entry >= FEB_WINDOW[0]) & (entry < FEB_WINDOW[1])


def transform_feb(entry, prior_keep):
    """February candidate keep mask: the incumbent's kept
    stream minus the window rows."""
    return np.asarray(prior_keep, bool) & ~feb_veto_mask(entry)


def is_vetoed_jan(strategy):
    return str(strategy) == JAN_EXCISED_DESIGN


def is_vetoed_feb(entry_s):
    return FEB_WINDOW[0] <= int(entry_s) < FEB_WINDOW[1]


# ------------------------------------------------- stream layer --
class StreamLayer4:
    """Incremental D21-RC with the ratio cap at 4 x TP.

    Verbatim mirror of core/d21rc_lib.StreamLayer (which
    is core-proven bit-exact against the array transform)
    with RATIO = 4.0 in the decide() cap. Feed incumbent
    delivered rows in stream order via decide(); each row
    must carry: entry_s, exit_s, net (base net @2.5), pwv,
    pv, tp, sl, prof (its M15-close profile). decide()
    returns the row's delivered net (float) if kept, else
    None. Exposure arithmetic is unchanged: exits of kept
    trades are credited (base outcomes) in exit order
    before each candidate.
    """

    def __init__(self, n_used, cap_frac=CAP_FRAC):
        self.n_used = float(n_used)
        self.cap_frac = float(cap_frac)
        self.bal = START
        self.profit = 0.0
        self.open_kept = []          # [(exit_s, exposure_amount)]
        self._pending_exits = []     # [(exit_s, base_net, pv, lot)]

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
        # Pointer semantics of exposure_keep (see
        # d21rc_lib.StreamLayer): only queue exits strictly
        # after the entry.
        if int(row['exit_s']) > entry_i:
            self._pending_exits.append(
                (int(row['exit_s']), float(row['net']),
                 float(row['pv']), lot_i))
        caps = np.array([min(float(row['sl']),
                             RATIO * float(row['tp']))])
        out = stop_tighten_arr([np.asarray(row['prof'],
                                           dtype=np.float64)],
                               caps, np.array([float(row['net'])]))
        return float(out[0])
