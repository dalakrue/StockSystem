"""D21-RC shared transform library -- the robustness-fix
programme's lead form (work_rob_fix, user order 2026-11-03),
ported for the validate-and-replace lane
(work_rob_validate).

The form is stream surgery on an incumbent system's own pick
stream, applied in stream (entry) order:

  1. EXPOSURE-SKIP (designs.exposure_skip verbatim): a realised-
     balance walk over the stream (START $80, formula lots at
     the carried N: lot = 0.01 * (START/N + max(profit,0)/N),
     P&L of KEPT trades credited at their exits, on the BASE
     outcomes). A candidate entry is skipped when the open
     adverse exposure of kept trades (sum of |pwv| x pv x lot,
     fixed at each trade's entry) plus the candidate's own
     |pwv| x pv x lot would exceed 10% of the current realised
     balance. pwv = the trade's worst floating value (gross
     pips) on its M15-close profile; pv = $ per pip per 1.00
     lot at the trade's exit instant (repair-mission pip model).
  2. RATIO CAP (designs.stop_tighten_arr verbatim): every
     trade's assigned stop is capped at min(stop, 5 x TP) and
     the outcome is repriced on the trade's M15-close floating
     profile: if the profile reaches -cap before the trade's
     outcome point, the trade exits at -cap (net -cap - 2.5).

The array functions below replicate the research lane's
arithmetic operation-for-operation (same loop order, same
comparisons) so the validation gate can prove bit-exact
agreement on the canonical streams. The StreamLayer class is
the incremental form of the same rules for the cycle modules'
state walks: candidates are decided on arrival, in entry
order, and a decision never revisits.
"""

from __future__ import annotations

import numpy as np

COST = 2.5
START = 80.0
CAP_FRAC = 0.10
BAR_S = 900
MAJORS = ('EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD',
          'USDJPY', 'USDCHF', 'USDCAD')


# ------------------------------------------------------- pip model
def pip_size(symbol):
    return 0.01 if symbol[3:] == 'JPY' else 0.0001


def _pip_of(sym):
    # profile machinery's pip_of: 0.01 if 'JPY' in sym else 0.0001
    return 0.01 if 'JPY' in sym else 0.0001


def conversion_rate(currency, rates):
    """Account-currency (USD numerics) per 1 unit of `currency`
    (pip_margin.conversion_rate verbatim)."""
    if currency == 'USD':
        return 1.0
    if currency + 'USD' in rates:
        return float(rates[currency + 'USD'])
    if 'USD' + currency in rates:
        return 1.0 / float(rates['USD' + currency])
    raise KeyError(f'no conversion rate derivable for {currency}')


def pip_value_per_lot(symbol, rates, contract_units=100_000):
    """$ per pip per 1.00 lot (pip_margin.pip_value_per_lot)."""
    quote = symbol[3:]
    return 1.0 * contract_units * pip_size(symbol) * \
        conversion_rate(quote, rates)


def rates_at(bars, t_s):
    """Majors' closes of the last bar starting <= t_s
    (chain_engine._rates_at verbatim). bars: {sym: (ts, op, cl)}."""
    out = {}
    for pair in MAJORS:
        ts, _op, cl = bars[pair]
        j = int(np.searchsorted(ts, t_s, side='right')) - 1
        out[pair] = float(cl[max(j, 0)])
    return out


# --------------------------------------------------------- profile
def profile_for_sym(symbol, entry_s, exit_s, entry_px, dirsign,
                    bars_sym):
    """One trade's gross floating profile on M15 closes
    (RB.build_pool_profiles single-trade semantics): prof[0]=0,
    prof[k] = dirsign * (close at entry + k*900s - entry_px)/pip
    for k = 1..floor(dur_s/900), closes forward-filled over gaps.
    bars_sym = (ts, open, close) for the trade's symbol."""
    ts, _op, cl = bars_sym
    dur_s = int(exit_s) - int(entry_s)
    if dur_s <= 0:
        dur_s = 3600
    K = int(dur_s // BAR_S)
    prof = np.zeros(K + 1, dtype=np.float64)
    if K > 0:
        pip = _pip_of(symbol)
        ct = int(entry_s) + BAR_S * np.arange(1, K + 1)
        idx = np.searchsorted(ts, ct - BAR_S, side='right') - 1
        have = idx >= 0
        closes = np.where(have, cl[np.clip(idx, 0, len(cl) - 1)],
                          np.nan)
        vals = dirsign * (closes - entry_px) / pip
        last = 0.0
        for k in range(1, K + 1):
            v = vals[k - 1]
            if np.isnan(v):
                vals[k - 1] = last
            else:
                last = v
        prof[1:] = vals
    return prof


# --------------------------------------------------- array form --
def formula_lot(balance_profit, n_used):
    return 0.01 * (START / n_used + max(balance_profit, 0.0) / n_used)


def exposure_keep(entry, exit_, outcome, pwv, pv, n_used,
                  cap_frac=CAP_FRAC):
    """designs.exposure_skip verbatim (prior=None): returns the
    boolean keep mask over the stream's rows. Decisions are made
    in entry order (stable); the balance walk credits KEPT
    trades' BASE outcomes at their exits."""
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


def ratio_caps(tp, sl):
    """Per-trade capped stop: min(assigned stop, 5 x assigned TP)."""
    return np.minimum(np.asarray(sl, dtype=np.float64),
                      5.0 * np.asarray(tp, dtype=np.float64))


def transform_arrays(entry, exit_, net, prof_list, pwv, pv, tp, sl,
                     n_used, cap_frac=CAP_FRAC):
    """The full D21-RC transform on a canonical stream.
    Returns (keep, outcome): outcome is the full-length repriced
    net array; the delivered stream is outcome[keep]."""
    keep = exposure_keep(entry, exit_, net, pwv, pv, n_used,
                         cap_frac)
    outcome = stop_tighten_arr(prof_list, ratio_caps(tp, sl), net)
    return keep, outcome


# ------------------------------------------------- stream layer --
class StreamLayer:
    """Incremental D21-RC for a cycle module's state walk.
    Feed incumbent delivered rows in stream order via decide();
    each row must carry: entry_s, exit_s, net (base net @2.5),
    pwv, pv, tp, sl, prof (its M15-close profile). decide()
    returns the row's delivered net (float) if kept, else None.
    Arithmetic mirrors exposure_keep + stop_tighten_arr exactly:
    exits of kept trades are credited (base outcomes) in exit
    order before each candidate; the ratio cap reprices the
    candidate's own outcome at decision time (its profile is
    final once the row is delivered by the incumbent state)."""

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
        # Pointer semantics of exposure_keep: a kept trade's
        # P&L is credited only when the exit pointer passes
        # its exit at a LATER entry event. A degenerate trade
        # (exit <= entry; 440 such rows in December's pool)
        # has its exit passed at its own event, before its
        # decision — it never credits. Replicated here by
        # only queueing exits strictly after the entry.
        if int(row['exit_s']) > entry_i:
            self._pending_exits.append(
                (int(row['exit_s']), float(row['net']),
                 float(row['pv']), lot_i))
        caps = np.array([min(float(row['sl']),
                             5.0 * float(row['tp']))])
        out = stop_tighten_arr([np.asarray(row['prof'],
                                           dtype=np.float64)],
                               caps, np.array([float(row['net'])]))
        return float(out[0])
