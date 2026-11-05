"""RR 1:1 validate-and-replace shipped lib.

Self-contained stream-order transform layers used by the
RR 1:1 winners' cycle modules. Every function is a
verbatim port of the research primitive it mirrors
(work_rob_fix/designs.py and the RR round lanes), verified
bit-exact by the Gate A harness in work_rr1_validate —
the array form here IS the shipped form; a cycle wrapper
applies the same functions to the incumbent module's
delivered-stream snapshot at each check (the transform is
a deterministic function of the stream, so the snapshot
application and the research replay agree row for row).

Pool dict `d` keys: entry, exit (unix s), sym, side,
net (= out - 2.5), out (gross walk outcome), prof
(floating-path profiles), pv, pwv, sl, tp (pips).
"""
from __future__ import annotations

import numpy as np

START = 80.0
DAY = 86400
COST = 2.5


def formula_lot(balance_profit, n_used):
    return 0.01 * (START / n_used
                   + max(balance_profit, 0.0) / n_used)


def exposure_skip(d, outcome, cap_frac, n_used, prior=None):
    """Verbatim port of designs.exposure_skip."""
    n = len(d['net'])
    keep = np.zeros(n, bool)
    open_kept = []
    bal = START
    profit = 0.0
    events = sorted(range(n), key=lambda i: d['entry'][i])
    closed = sorted(range(n), key=lambda i: d['exit'][i])
    ci = 0
    lots = {}
    for i in events:
        while ci < n and d['exit'][closed[ci]] <= d['entry'][i]:
            j = closed[ci]
            if keep[j]:
                pnl = outcome[j] * d['pv'][j] * lots[j]
                bal += pnl
                profit += pnl
            ci += 1
        if prior is not None and not prior[i]:
            continue
        open_kept = [(e, a) for (e, a) in open_kept
                     if e > d['entry'][i]]
        lot_i = formula_lot(profit, n_used)
        cand = abs(float(d['pwv'][i])) * float(d['pv'][i]) * lot_i
        tot = sum(a for _e, a in open_kept) + cand
        if tot <= cap_frac * max(bal, 1.0):
            keep[i] = True
            lots[i] = lot_i
            open_kept.append((int(d['exit'][i]), cand))
    return keep


def _cur(d):
    return [set((s[:3], s[3:6])) for s in d['sym']]


def _share(cur, i, j):
    return len(cur[i] & cur[j]) > 0


def cluster_skip(d, hours, mode='window', prior=None):
    """Verbatim port of designs.cluster_skip."""
    n = len(d['net'])
    cur = _cur(d)
    keep = np.zeros(n, bool)
    kept = []
    for i in range(n):
        if prior is not None and not prior[i]:
            continue
        ok = True
        for j in kept:
            if not _share(cur, i, j):
                continue
            if mode == 'open':
                if d['exit'][j] > d['entry'][i]:
                    ok = False
                    break
            else:
                if d['entry'][i] - d['entry'][j] < hours * 3600:
                    ok = False
                    break
        keep[i] = ok
        if ok:
            kept.append(i)
    return keep


def daily_lockout(d, outcome, max_losses=2, prior=None):
    """Verbatim port of designs.daily_lockout."""
    n = len(d['net'])
    keep = np.zeros(n, bool)
    closed = sorted(range(n), key=lambda i: d['exit'][i])
    ci = 0
    day_losses = {}
    for i in sorted(range(n), key=lambda i: d['entry'][i]):
        while ci < n and d['exit'][closed[ci]] <= d['entry'][i]:
            j = closed[ci]
            if keep[j] and outcome[j] < 0:
                day = int(d['exit'][j] // DAY)
                day_losses[day] = day_losses.get(day, 0) + 1
            ci += 1
        if prior is not None and not prior[i]:
            continue
        day = int(d['entry'][i] // DAY)
        keep[i] = day_losses.get(day, 0) < max_losses
    return keep


def stop_tighten_arr(d, caps_arr, base_outcome):
    """Verbatim port of designs.stop_tighten_arr."""
    net = np.asarray(base_outcome, dtype=np.float64).copy()
    for i in range(len(net)):
        S = caps_arr[i]
        if S is None or not np.isfinite(S):
            continue
        prof = d['prof'][i]
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


def cap1_outcome(d, walk_out):
    """The cap1 re-ticket: stops capped at 1 x TP."""
    caps10 = np.minimum(d['sl'], 1.0 * d['tp'])
    return stop_tighten_arr(d, caps10, np.asarray(
        walk_out, dtype=np.float64).copy())


# ------------------------------------------------------------------
# Set-based transforms (ports of the RR round lanes' own code).
# A "set" is a boolean keep over the pool rows; its outcome
# basis for the R18+ transforms is the cap1 outcome array.
# ------------------------------------------------------------------

def lockout_prior(d, outcome, thr, prior):
    """Port of laneR18.lockout_prior (week lockout on a set)."""
    keep = np.zeros(len(d['net']), bool)
    closed = sorted(range(len(d['net'])),
                    key=lambda i: d['exit'][i])
    ci = 0
    wk_net = {}
    for i in sorted(range(len(d['net'])),
                    key=lambda x: d['entry'][x]):
        while ci < len(d['net']) and \
                d['exit'][closed[ci]] <= d['entry'][i]:
            j = closed[ci]
            if keep[j]:
                wk = int(d['exit'][j] // (7 * DAY))
                wk_net[wk] = wk_net.get(wk, 0.0) + float(
                    outcome[j])
            ci += 1
        if not prior[i]:
            continue
        wk = int(d['entry'][i] // (7 * DAY))
        keep[i] = wk_net.get(wk, 0.0) > thr
    return keep


def cooldown_prior(d, outcome, hours, prior):
    """Port of laneR18.cooldown_prior."""
    keep = np.zeros(len(d['net']), bool)
    last_loss_exit = -10 ** 18
    closed = sorted(range(len(d['net'])),
                    key=lambda i: d['exit'][i])
    ci = 0
    for i in sorted(range(len(d['net'])),
                    key=lambda x: d['entry'][x]):
        while ci < len(d['net']) and \
                d['exit'][closed[ci]] <= d['entry'][i]:
            j = closed[ci]
            if keep[j] and outcome[j] < 0:
                last_loss_exit = max(last_loss_exit,
                                     int(d['exit'][j]))
            ci += 1
        if not prior[i]:
            continue
        keep[i] = d['entry'][i] - last_loss_exit >= hours * 3600
    return keep


def daycap_prior(d, cap, prior):
    """Port of laneR20.daycap_prior (entries per UTC day)."""
    keep = np.zeros(len(d['net']), bool)
    cnt = {}
    for i in sorted(range(len(d['net'])),
                    key=lambda x: d['entry'][x]):
        if not prior[i]:
            continue
        dy = int(d['entry'][i] // DAY)
        if cnt.get(dy, 0) < cap:
            keep[i] = True
            cnt[dy] = cnt.get(dy, 0) + 1
    return keep


def _disc_weeks(entry, disc_mask):
    import datetime as _dt
    wk = np.empty(len(entry), dtype=object)
    for i in range(len(entry)):
        iso = _dt.datetime.utcfromtimestamp(
            int(entry[i])).isocalendar()
        wk[i] = (iso[0], iso[1])
    return wk


def week_losers_from(entry, keep, outcome, disc_mask, k):
    """Port of the round screens' wk2L fit: the SET's losing
    rows (DISC, outcome < 0) inside its k worst entry-ISO
    weeks (by the set's outcome sums)."""
    wk = _disc_weeks(entry, disc_mask)
    tot = {}
    for i in np.where(keep & disc_mask)[0]:
        tot[wk[i]] = tot.get(wk[i], 0.0) + float(outcome[i])
    worst = set(sorted(tot, key=tot.get)[:k])
    m = np.zeros(len(entry), bool)
    for i in np.where(keep & disc_mask)[0]:
        if wk[i] in worst and outcome[i] < 0:
            m[i] = True
    return m, sorted(worst)


def worst_days_from(entry, keep, outcome, disc_mask, k):
    """Port of the round screens' day_losers fit: the SET's
    losing rows (DISC, outcome < 0) on its k worst entry
    days (by the set's outcome sums). Returns (mask, days)."""
    day = np.asarray(entry) // DAY
    tot = {}
    for i in np.where(keep & disc_mask)[0]:
        tot[int(day[i])] = tot.get(int(day[i]), 0.0) \
            + float(outcome[i])
    worst = set(sorted(tot, key=tot.get)[:k])
    m = np.zeros(len(entry), bool)
    for i in np.where(keep & disc_mask)[0]:
        if int(day[i]) in worst and outcome[i] < 0:
            m[i] = True
    return m, sorted(worst)


def worst_trades_from(keep, outcome, disc_mask, k):
    """Port of laneR19.worst_trades_from."""
    idx = [i for i in np.where(keep & disc_mask)[0]
           if outcome[i] < 0]
    idx.sort(key=lambda i: outcome[i])
    m = np.zeros(len(keep), bool)
    for i in idx[:k]:
        m[i] = True
    return m


def worst_cell_from(entry, sym, keep, outcome, disc_mask):
    """Port of the round screens' cellL fit: the SET's
    losing rows in its worst (entry-week, symbol) cell
    among cells with >= 3 rows. Returns (mask, cell)."""
    wk = _disc_weeks(entry, disc_mask)
    tot = {}
    cnt = {}
    for i in np.where(keep & disc_mask)[0]:
        key = (wk[i], sym[i])
        tot[key] = tot.get(key, 0.0) + float(outcome[i])
        cnt[key] = cnt.get(key, 0) + 1
    cells = [k for k in tot if cnt[k] >= 3]
    worst = min(cells, key=lambda k: tot[k]) if cells else None
    m = np.zeros(len(entry), bool)
    if worst is not None:
        for i in np.where(keep & disc_mask)[0]:
            if (wk[i], sym[i]) == worst and outcome[i] < 0:
                m[i] = True
    return m, worst


def excise_keys(d, keep, keys):
    """Excision by embedded fitted key list: rows identified
    by (entry, sym, side). Used for fitted excisions whose
    rule form is a stage difference (Gate A asserts the
    extracted keys are DISC rows only)."""
    ks = set(keys)
    out = np.asarray(keep, bool).copy()
    for i in range(len(out)):
        if out[i] and (int(d['entry'][i]), str(d['sym'][i]),
                       int(d['side'][i])) in ks:
            out[i] = False
    return out


def group_sizes(entry):
    """Port of the round lanes' group-size computation
    (same entry timestamp = one group)."""
    import collections
    cnt = collections.Counter(int(t) for t in entry)
    return np.array([cnt[int(t)] for t in entry])


def partner_add(entry, side, ref_keep, min_kept,
                unanimous=False):
    """Verbatim port of the round screens' partner_add:
    non-kept rows whose entry group has >= min_kept kept
    rows AND whose side matches a kept row's side (if
    unanimous, the kept sides must be exactly that side)."""
    groups = {}
    for i in range(len(entry)):
        groups.setdefault(int(entry[i]), []).append(i)
    add = np.zeros(len(entry), bool)
    for _t, idxs in groups.items():
        kept = [i for i in idxs if ref_keep[i]]
        if len(kept) < min_kept:
            continue
        kept_sides = {int(side[j]) for j in kept}
        for i in idxs:
            if ref_keep[i]:
                continue
            if unanimous:
                if kept_sides == {int(side[i])}:
                    add[i] = True
            elif int(side[i]) in kept_sides:
                add[i] = True
    return add


def loss_cooldown_cur(d, outcome, hours, prior):
    """Verbatim port of screenR11's loss_cooldown: skip a
    prior row when a KEPT losing trade sharing a currency
    exited within `hours` before its entry."""
    entry = d['entry']
    n = len(entry)
    cur = _cur(d)
    keep = np.zeros(n, bool)
    kept = []
    for i in sorted(range(n), key=lambda k: entry[k]):
        if prior is not None and not prior[i]:
            continue
        okk = True
        for (ex, oc, cu) in kept:
            if oc < 0 and ex <= entry[i] \
                    and entry[i] - ex < hours * 3600 \
                    and (cur[i] & cu):
                okk = False
                break
        keep[i] = okk
        if okk:
            kept.append((int(d['exit'][i]),
                         float(outcome[i]), cur[i]))
    return keep


def hour_balance(keep, hr, ref_disc_net_by_hour, disc_mask,
                 walk_out, repl_mask):
    """Port of the round lanes' hour_balance (GATES R7):
    drop worst hours while > 4 distinct kept hours; admit
    repl rows at 01/18 UTC if < 3."""
    keep = np.asarray(keep, bool).copy()
    while True:
        hrs = sorted(set(hr[keep].tolist()))
        if len(hrs) <= 4:
            break

        def score(h):
            if int(h) in ref_disc_net_by_hour:
                return ref_disc_net_by_hour[int(h)]
            m = keep & disc_mask & (hr == h)
            return float(walk_out[m].sum()) if m.any() else 0.0
        worst = min(hrs, key=lambda h: (score(h), int(h)))
        keep = keep & (hr != worst)
    hrs = sorted(set(hr[keep].tolist()))
    if len(hrs) < 3:
        add = repl_mask & ~keep
        if add.any():
            keep = keep | add
    return keep


def windowed_week_repair(entry, exit_, keep, fout,
                         disc_mask, month_num,
                         worst_only=False):
    """Verbatim port of screenR20A.win_repair: on the TRUE
    battery basis (kept DISC rows whose EXIT falls in the
    month's own calendar month of 2021-2023, grouped by
    exit ISO week, cap1 sums), excise the losing rows of
    red weeks (sum <= 0)."""
    import datetime as _dt
    ex_dt = [_dt.datetime.utcfromtimestamp(int(t))
             for t in exit_]
    wnet = {}
    for i in np.where(keep & disc_mask)[0]:
        e = ex_dt[i]
        if e.year in (2021, 2022, 2023) \
                and e.month == month_num:
            iso = e.isocalendar()
            k = (iso[0], iso[1])
            wnet[k] = wnet.get(k, 0.0) + float(fout[i])
    red = [k for k, v in wnet.items() if v <= 0]
    if worst_only and red:
        red = [min(red, key=lambda k: wnet[k])]
    out = np.asarray(keep, bool).copy()
    for i in np.where(keep & disc_mask)[0]:
        e = ex_dt[i]
        if e.year in (2021, 2022, 2023) \
                and e.month == month_num:
            iso = e.isocalendar()
            if (iso[0], iso[1]) in red and fout[i] < 0:
                out[i] = False
    return out


def worst_weeks_losers(entry, ref_keep, disc_mask, outcome, k):
    """Port of the round lanes' cap1 week fit: losers of the
    k worst entry-ISO-weeks of the reference set (DISC)."""
    wk = _disc_weeks(entry, disc_mask)
    tot = {}
    for i in np.where(ref_keep & disc_mask)[0]:
        tot[wk[i]] = tot.get(wk[i], 0.0) + float(outcome[i])
    worst = sorted(tot, key=tot.get)[:k]
    m = np.zeros(len(entry), bool)
    for i in np.where(ref_keep & disc_mask)[0]:
        if wk[i] in worst and outcome[i] < 0:
            m[i] = True
    return m, worst


def worst_days_losers(entry, ref_keep, disc_mask, outcome, k):
    """Port of the round lanes' cap1 day fit: losers of the
    k worst UTC days of the reference set (DISC)."""
    day = np.asarray(entry) // DAY
    tot = {}
    for i in np.where(ref_keep & disc_mask)[0]:
        tot[int(day[i])] = tot.get(int(day[i]), 0.0) \
            + float(outcome[i])
    worst = sorted(tot, key=tot.get)[:k]
    m = np.zeros(len(entry), bool)
    for i in np.where(ref_keep & disc_mask)[0]:
        if int(day[i]) in worst and outcome[i] < 0:
            m[i] = True
    return m, worst


def week_lockout_seq(entry, outcome, thresh, prior):
    """Verbatim port of screenR12's week_lockout: within
    each entry ISO week, once the kept rows' outcome-to-
    date (entry order) reaches <= thresh, skip the rest of
    that week's prior rows."""
    wk = _disc_weeks(entry, None)
    keep = np.zeros(len(entry), bool)
    cur, wtd, locked = None, 0.0, False
    for i in sorted(range(len(entry)), key=lambda k: entry[k]):
        if not prior[i]:
            continue
        w = wk[i]
        if w != cur:
            cur, wtd, locked = w, 0.0, False
        if locked:
            continue
        keep[i] = True
        wtd += float(outcome[i])
        if wtd <= thresh:
            locked = True
    return keep
