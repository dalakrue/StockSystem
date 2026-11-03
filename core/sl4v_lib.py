"""SL4-10cyc winners' transforms (work_sl4_10cyc), ported
for the validate-and-replace lane (work_sl4_validate).

Three forms, each finishing with the SL <= 4 x TP cap
repriced on the trade's M15-close floating profile
(designs.stop_tighten_arr verbatim, as in core/d21rc_lib
and core/riskopt5_lib):

  NOVEMBER (cycle93y): the shipped cycle93x stream with
  the UTC-10 check (16:30 MMT) dropped -- a pure mask over
  the 93x delivered stream (designs.hour_drop verbatim);
  outcomes are 93x's own cap-4 repriced outcomes, unchanged.
  EXACT per-trade basis (inherited from 93x).

  MARCH (cycle86g): exposure-skip 12.5% over the shipped
  cycle86f stream (designs.exposure_skip verbatim at
  cap_frac 0.125, realised-balance walk at the carried
  N = 86/3, P&L credited on BASE outcomes), then every
  kept trade's assigned stop capped at min(stop, 4 x TP)
  on the EXACT per-trade basis (rebuilt 527/527 in the
  validation lane, GATES section 3).

  APRIL (cycle87g): stop-tighten 30p on cycle87f's stream
  (designs.stop_tighten verbatim), then the SL <= 4 cap.
  April's basis is the declared POOL basis
  (stageA.ratio_screen_arrays: a trade's TP is its gross
  if won else the (symbol, side) group median winning
  gross; SL mirror) -- no complete exact per-trade basis
  exists for April (exact reconstruction attempted in
  work_sl4_validate: 1,108 of 1,156 rows covered, 48
  pvote-era rows unrecoverable); the pool substitute was
  authorised by the user 2026-11-03 (GATES Amendment 1)
  and is declared in the validation verdict and the
  registry comment. APR_POOL_MED below bakes the pool's
  (symbol, side) group medians so a live row's pool
  stamps derive from its own gross exactly as
  ratio_screen_arrays derives them.

The array functions replicate the research lanes'
arithmetic operation-for-operation so Gate A can prove
bit-exact agreement on the canonical streams. The layer
classes are the incremental forms for the cycle modules'
state walks: rows are decided on arrival, in entry
order, and a decision never revisits.
"""

from __future__ import annotations

import numpy as np

COST = 2.5
START = 80.0
RATIO = 4.0
DROP_HOUR_UTC = 10
MAR_CAP_FRAC = 0.125
APR_STOP_PIPS = 30.0

# (symbol|side) -> (median winning gross, median losing
# |gross|) over the canonical April pool; generated from
# stageA.ratio_screen_arrays' own grouping.
APR_POOL_MED = {
    'AUDCAD|-1': (11.346428571428202, 50.422857142857765),
    'AUDCHF|-1': (13.36814285714305, 33.69999999999984),
    'AUDJPY|-1': (14.811428571428564, None),
    'AUDJPY|1': (14.345571428570736, None),
    'AUDUSD|-1': (10.000000000000009, None),
    'AUDUSD|-9223372036854775808': (10.000000000000009, 26.10000000000001),
    'AUDUSD|1': (12.76799999999967, None),
    'CADJPY|1': (9.999999999999432, None),
    'CHFJPY|1': (15.201142857142711, 63.84999999999934),
    'DOLLARIDX|-1': (49.500000000000455, None),
    'EURAUD|-1': (9.9999999999989, 51.04285714285784),
    'EURAUD|-9223372036854775808': (9.9999999999989, 100.00000000000009),
    'EURAUD|1': (9.9999999999989, None),
    'EURCAD|1': (9.9999999999989, None),
    'EURCHF|-9223372036854775808': (9.9999999999989, None),
    'EURCHF|1': (9.9999999999989, None),
    'EURJPY|1': (12.478392857143206, 100.0),
    'EURNZD|-1': (16.982142857142613, 100.00000000000009),
    'EURNZD|1': (17.718750000000895, None),
    'EURUSD|-1': (9.9999999999989, 39.00000000000014),
    'EURUSD|-9223372036854775808': (9.9999999999989, 33.45000000000042),
    'EURUSD|1': (9.9999999999989, None),
    'GBPAUD|-1': (25.558928571427497, 99.99999999999788),
    'GBPAUD|1': (22.355357142856974, None),
    'GBPCAD|-1': (34.63571428571343, None),
    'GBPJPY|1': (10.491428571428687, None),
    'GBPNZD|1': (35.26285714285482, 99.99999999999788),
    'NZDCAD|-1': (10.000000000000009, None),
    'NZDCAD|1': (15.249999999999986, None),
    'NZDCHF|-1': (12.74821428571382, None),
    'NZDCHF|1': (10.485571428571205, None),
    'NZDJPY|-1': (19.965000000000543, None),
    'NZDJPY|1': (17.45742857142858, 58.59999999999985),
    'NZDUSD|-1': (10.000000000000009, None),
    'NZDUSD|1': (10.000000000000009, None),
    'USDCAD|-1': (13.07142857142951, 35.39999999999876),
    'USDCAD|-9223372036854775808': (9.9999999999989, 0.5000000000010552),
    'USDCAD|1': (9.9999999999989, 100.00000000000009),
    'USDCHF|-1': (10.000000000000009, None),
    'USDCHF|1': (14.178571428571374, None),
    'USDJPY|1': (19.740857142856783, 52.7000000000001),
}


def formula_lot(balance_profit, n_used):
    return 0.01 * (START / n_used
                   + max(balance_profit, 0.0) / n_used)


def stop_tighten_arr(prof_list, caps, base_outcome):
    """designs.stop_tighten_arr verbatim: per-trade stop
    caps (pips) repriced on the trades' floating
    profiles."""
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
            tp_first = int(tp_idx[0]) if len(tp_idx) \
                else len(prof)
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


# ------------------------------------------------------- NOV --
def transform_nov(entry, prior_keep):
    """November N2: hour_drop({10}) over the 93x keep mask.
    Outcomes are the incumbent's own (unchanged)."""
    entry = np.asarray(entry)
    keep = np.asarray(prior_keep, bool).copy()
    hrs = (entry % 86400) // 3600
    keep[hrs == DROP_HOUR_UTC] = False
    return keep


class HourDropLayer:
    """Incremental November form: feed the 93x form's
    DELIVERED rows in stream order; decide() returns the
    row's delivered net, or None for a UTC-10 row."""

    def decide(self, row):
        if (int(row['entry_s']) % 86400) // 3600 \
                == DROP_HOUR_UTC:
            return None
        return float(row['net'])


# ------------------------------------------------------- MAR --
def exposure_keep(entry, exit_, outcome, pwv, pv, n_used,
                  cap_frac=MAR_CAP_FRAC):
    """designs.exposure_skip verbatim (prior=None): the
    realised-balance walk; decisions in entry order
    (stable); KEPT trades' BASE outcomes credited at
    their exits."""
    entry = np.asarray(entry)
    exit_ = np.asarray(exit_)
    outcome = np.asarray(outcome, dtype=np.float64)
    pwv = np.asarray(pwv, dtype=np.float64)
    pv = np.asarray(pv, dtype=np.float64)
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


def transform_mar(entry, exit_, net, prof_list, pwv, pv, tp,
                  sl, n_used):
    """March D5 on a canonical stream: returns (keep,
    outcome); outcome is the full-length cap-4 repriced
    net array on the EXACT basis; the delivered stream
    is outcome[keep]."""
    keep = exposure_keep(entry, exit_, net, pwv, pv, n_used)
    outcome = stop_tighten_arr(prof_list, ratio_caps4(tp, sl),
                               net)
    return keep, outcome


class ExposureLayer:
    """Incremental March form (mirrors d21rc_lib.Stream-
    Layer's arithmetic with cap_frac 0.125 and the 4 x TP
    cap). Feed incumbent delivered rows in stream order
    via decide(); each row must carry: entry_s, exit_s,
    net (base net @2.5), pwv, pv, tp, sl, prof. decide()
    returns the row's delivered net (float) if kept, else
    None."""

    def __init__(self, n_used, cap_frac=MAR_CAP_FRAC):
        self.n_used = float(n_used)
        self.cap_frac = float(cap_frac)
        self.bal = START
        self.profit = 0.0
        self.open_kept = []          # [(exit_s, exposure)]
        self._pending_exits = []     # [(exit_s, net, pv, lot)]

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
        if int(row['exit_s']) > entry_i:
            self._pending_exits.append(
                (int(row['exit_s']), float(row['net']),
                 float(row['pv']), lot_i))
        caps = np.array([min(float(row['sl']),
                             RATIO * float(row['tp']))])
        out = stop_tighten_arr(
            [np.asarray(row['prof'], dtype=np.float64)],
            caps, np.array([float(row['net'])]))
        return float(out[0])


# ------------------------------------------------------- APR --
def pool_stamps(gross, sym, side):
    """stageA.ratio_screen_arrays for one row: TP = gross
    if won else the (symbol, side) median winning gross;
    SL = |gross| if lost else the median losing |gross|.
    A group with no winners/losers yields inf on that side
    (the array form's np.inf), which the cap then leaves
    effectively uncapped on that side."""
    med_tp, med_sl = APR_POOL_MED[f'{sym}|{int(side)}']
    tp = float(gross) if gross > 0 else med_tp
    sl = -float(gross) if gross < 0 else med_sl
    return (np.inf if tp is None else float(tp),
            np.inf if sl is None else float(sl))


def transform_apr(net, prof_list, tp, sl):
    """April D6 on a canonical stream: stop-tighten 30p
    (caps array = 30 for every trade, designs.stop_tighten
    verbatim), then the SL <= 4 cap as the final step.
    tp/sl are the POOL-basis arrays."""
    n = len(net)
    st30 = stop_tighten_arr(prof_list,
                            np.full(n, APR_STOP_PIPS), net)
    return stop_tighten_arr(prof_list, ratio_caps4(tp, sl),
                            st30)


class Stop30CapLayer:
    """Incremental April form: stateless per-trade
    repricing (stop-tighten 30p, then the 4 x TP cap with
    the row's POOL-basis tp/sl). decide(row) returns the
    delivered net (float); every row is delivered."""

    def decide(self, row):
        prof = [np.asarray(row['prof'], dtype=np.float64)]
        st30 = stop_tighten_arr(prof, np.array([APR_STOP_PIPS]),
                                np.array([float(row['net'])]))
        caps = np.array([min(float(row['sl']),
                             RATIO * float(row['tp']))])
        out = stop_tighten_arr(prof, caps, st30)
        return float(out[0])
