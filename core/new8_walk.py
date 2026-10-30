"""NEW8 walk machinery -- app port (2026-10-27).

Verbatim ports of the NEW8 research walk components:
  * sim_fixed_vec / evaluate_candidate -- c70_sim (the H1
    barrier simulator every NEW8 candidate ledger was built
    with: SL-first on ties, exit at the barrier price, TIME at
    the close of bar entry+max_hold-1, exit_time = the exit
    bar's start).
  * walk157 -- walk157_lib (score-ordered single pick per
    check, symbol occupancy by recorded exit times).
  * build_combined -- validate_new8 (incumbent-priority merge:
    same-check drop, incumbent interval overlap drop,
    accepted-candidate interval overlap drop).
  * coolv -- mine_planb4._coolv (stateful two-loss cooldown
    brake, the Nov B-4 partner design's veto).

Panel-path streaming state (DesignWalk / MergedWalk) applies
the same rules check-by-check as the panel evaluates them;
the batch functions above are what the era replay gate runs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.new8_features import SL_CLIP, TP_CLIP, pip_size_new8

COST = 2.5
MAX_HOLD = 48


# ============================================================ sim --
def sim_fixed_vec(o, h, l, c, entry_pos, direction, tp_pips,
                  sl_pips, pip, max_hold=48, cost=0.0):
    """c70_sim.sim_fixed_vec verbatim."""
    entry_pos = np.asarray(entry_pos, dtype=np.int64)
    n = len(entry_pos)
    if n == 0:
        return {k: np.array([]) for k in
                ('net_pips', 'gross_pips', 'exit_px', 'hold_h',
                 'exit_pos', 'entry_px', 'exit_reason')}
    N = len(o)
    epx = o[entry_pos].astype(float)
    tp_pips = np.asarray(tp_pips, dtype=float)
    sl_pips = np.asarray(sl_pips, dtype=float)
    buy = (direction == 'BUY')
    sgn = 1.0 if buy else -1.0
    tp_px = epx + sgn * tp_pips * pip
    sl_px = epx - sgn * sl_pips * pip
    H = int(max_hold)
    idx = np.minimum(entry_pos[:, None] + np.arange(H), N - 1)
    wh, wl, wc = h[idx], l[idx], c[idx]
    if buy:
        sl_hit = wl <= sl_px[:, None]
        tp_hit = wh >= tp_px[:, None]
    else:
        sl_hit = wh >= sl_px[:, None]
        tp_hit = wl <= tp_px[:, None]
    has_sl = sl_hit.any(axis=1)
    has_tp = tp_hit.any(axis=1)
    fsl = sl_hit.argmax(axis=1)
    ftp = tp_hit.argmax(axis=1)
    use_sl = has_sl & (~has_tp | (fsl <= ftp))
    use_tp = has_tp & ~use_sl
    exit_px = np.where(use_sl, sl_px,
                       np.where(use_tp, tp_px, wc[:, -1]))
    hold = np.where(use_sl, fsl + 1,
                    np.where(use_tp, ftp + 1, H)).astype(np.int64)
    exit_pos = np.minimum(entry_pos + hold - 1, N - 1)
    gross = sgn * (exit_px - epx) / pip
    net = gross - cost
    reason = np.where(use_sl, 'SL', np.where(use_tp, 'TP', 'TIME'))
    return {'net_pips': net, 'gross_pips': gross,
            'exit_px': exit_px, 'hold_h': hold, 'exit_pos': exit_pos,
            'entry_px': epx, 'exit_reason': reason}


def ohlc_from_frame(fr):
    """Research ohlc dict shape from a Datetime-column frame."""
    df = fr.set_index('Datetime').sort_index()
    return {'o': df['Open'].to_numpy(), 'h': df['High'].to_numpy(),
            'l': df['Low'].to_numpy(), 'c': df['Close'].to_numpy(),
            'dt': df.index.to_numpy(), 'pos_of': df.index}


def evaluate_candidate(sym, hour, direction, conditions, tp_mult,
                       sl_mult, grid_h, feat, ohlc, cost=2.5,
                       max_hold=48):
    """c70_sim.evaluate_candidate verbatim (standalone stats +
    per-trade frame for one candidate equation)."""
    pip = pip_size_new8(sym)
    sig_idx = feat.index
    st = grid_h['sig_time'].to_numpy()
    loc = sig_idx.get_indexer(st)
    ok = loc >= 0
    if not ok.any():
        return None
    rows = feat.iloc[loc[ok]]
    mask = np.ones(len(rows), dtype=bool)
    for col, op, val in conditions:
        v = rows[col].to_numpy(dtype=float)
        if op == '>':
            m = v > val
        elif op == '<':
            m = v < val
        elif op == '>=':
            m = v >= val
        elif op == '<=':
            m = v <= val
        else:
            raise ValueError(op)
        m = m & np.isfinite(v)
        mask &= m
    fire = np.where(ok)[0][mask]
    if len(fire) == 0:
        return None
    gh = grid_h.iloc[fire]
    ent_pos = ohlc['pos_of'].get_indexer(gh['ent_time'].to_numpy())
    ok2 = ent_pos >= 0
    if not ok2.any():
        return None
    fire = fire[ok2]
    gh = grid_h.iloc[fire]
    ent_pos = ent_pos[ok2]
    atr = rows.iloc[mask].iloc[ok2]['atr14'].to_numpy(dtype=float)
    tp_pips = np.clip(tp_mult * atr / pip, *TP_CLIP)
    sl_pips = np.clip(sl_mult * atr / pip, *SL_CLIP)
    if direction == 'TREND':
        momv = rows.iloc[mask].iloc[ok2]['mom24'].to_numpy(dtype=float)
        dirs = np.where(momv > 0, 'BUY', 'SELL')
        parts = []
        for d in ('BUY', 'SELL'):
            m = dirs == d
            if not m.any():
                continue
            rr = sim_fixed_vec(ohlc['o'], ohlc['h'], ohlc['l'],
                               ohlc['c'], ent_pos[m], d,
                               tp_pips[m], sl_pips[m], pip,
                               max_hold=max_hold, cost=cost)
            parts.append((np.where(m)[0], rr, d))
        if not parts:
            return None
        r = {}
        for k in parts[0][1].keys():
            all_idx = np.concatenate([p[0] for p in parts])
            all_v = np.concatenate([np.asarray(p[1][k])
                                    for p in parts])
            r[k] = all_v[np.argsort(all_idx)]
        dir_col = np.empty(len(fire), dtype=object)
        for idx, rr, d in parts:
            dir_col[idx] = d
        trend_dirs = dir_col
    else:
        r = sim_fixed_vec(ohlc['o'], ohlc['h'], ohlc['l'],
                          ohlc['c'], ent_pos, direction, tp_pips,
                          sl_pips, pip, max_hold=max_hold,
                          cost=cost)
        trend_dirs = None
    net = r['net_pips']
    n = len(net)
    cum = np.cumsum(net)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))
    dd = float(min(0.0, (np.concatenate([[0.0], cum]) - peak).min()))
    wins = net[net > 0]
    out = {'n': n, 'net': float(cum[-1]), 'ev': float(net.mean()),
           'win': float(len(wins) / n), 'dd': dd,
           'romad': float(cum[-1] / abs(dd)) if dd < 0 else
           (999.0 if cum[-1] > 0 else 0.0)}
    trades = pd.DataFrame({
        'check': gh['check'].to_numpy(), 'symbol': sym,
        'direction': trend_dirs if trend_dirs is not None
        else direction,
        'entry_px': r['entry_px'], 'exit_px': r['exit_px'],
        'tp_pips_used': tp_pips, 'sl_pips_used': sl_pips,
        'gross_pips': r['gross_pips'], 'net_pips': net,
        'exit_reason': r['exit_reason'], 'hold_h': r['hold_h'],
        'exit_time': ohlc['dt'][r['exit_pos']],
    })
    out['trades'] = trades
    return out


def design_tab(eq, grid, feat, ohlc):
    """The research tab_of for one design equation: the
    candidate trades frame over the grid rows of the
    equation's hour (None when it never fires).

    OR-branch equations (P-BRANCH, 2026-10-28): the tab is
    the research mine_pbranch construction -- each branch
    evaluated with its own conditions / exit pair / hold,
    branch tabs concatenated in branch order, sorted by
    check (mergesort) and de-duplicated on check keeping
    the FIRST branch's row. Flat equations use their own
    'hold' (48 for every design shipped before 2026-10-28,
    so their tabs are unchanged)."""
    gh = grid[grid['hour'] == eq['hour']]
    if 'branches' in eq:
        parts = []
        for b in eq['branches']:
            r = evaluate_candidate(
                b['symbol'], b['hour'], b['direction'],
                [tuple(c) for c in b['conditions']],
                b['tp_mult'], b['sl_mult'], gh, feat, ohlc,
                cost=COST, max_hold=b.get('hold', MAX_HOLD))
            if r is not None:
                parts.append(r['trades'])
        if not parts:
            return None
        tab = pd.concat(parts).sort_values(
            'check', kind='mergesort')
        return tab.drop_duplicates('check', keep='first') \
            .reset_index(drop=True)
    r = evaluate_candidate(
        eq['symbol'], eq['hour'], eq['direction'],
        [tuple(c) for c in eq['conditions']], eq['tp_mult'],
        eq['sl_mult'], gh, feat, ohlc, cost=COST,
        max_hold=eq.get('hold', MAX_HOLD))
    return None if r is None else r['trades']


# =========================================================== walk --
def walk157(G, tabs, eqs, grid, veto_fn=None, pick_fn=None,
            second_fn=None):
    """walk157_lib.walk157 verbatim (hooks unused by NEW8)."""
    open_exit = {}
    opens = []
    rows = []
    picks = {}
    tabs_by_check = []
    for ei, t in enumerate(tabs):
        if t is None or len(t) == 0:
            tabs_by_check.append({})
        else:
            tabs_by_check.append({pd.Timestamp(r['check']): r
                                  for _, r in t.iterrows()})
    for chk_raw, h in zip(grid['check'].to_numpy(),
                          grid['hour'].to_numpy()):
        chk = pd.Timestamp(chk_raw)
        ent_t = chk - pd.Timedelta(minutes=30)
        cands = []
        for ei, e in enumerate(eqs):
            if e['hour'] != h:
                continue
            tr = tabs_by_check[ei].get(chk)
            if tr is None:
                continue
            cands.append((ei, e, tr))
        cands.sort(key=lambda c: -c[1]['score'])
        elig = []
        for c in cands:
            occ = open_exit.get(c[1]['symbol'], [])
            if all(x <= ent_t for x in occ):
                if veto_fn is not None and veto_fn(c[1], c[2],
                                                   ent_t):
                    continue
                elig.append(c)
        pick = None
        live = [(s2, d2, x2) for (s2, d2, x2, en2) in opens
                if x2 > ent_t]
        if pick_fn is not None:
            pick = pick_fn(elig, chk, ent_t, live)
            if pick is None and elig:
                pick = elig[0]
        else:
            pick = elig[0] if elig else None
        if pick is None:
            continue

        def _append(c):
            ei2, e2, tr2 = c
            open_exit.setdefault(e2['symbol'], []).append(
                pd.Timestamp(tr2['exit_time']))
            rows.append(dict(
                check=pd.Timestamp(tr2['check']),
                symbol=e2['symbol'],
                direction=tr2['direction'], strategy=e2['id'],
                score=e2['score'], entry_px=tr2['entry_px'],
                exit_px=tr2['exit_px'],
                tp_pips_used=tr2['tp_pips_used'],
                sl_pips_used=tr2['sl_pips_used'],
                gross_pips=tr2['gross_pips'],
                net_pips=tr2['net_pips'],
                exit_reason=tr2['exit_reason'],
                hold_h=tr2['hold_h'],
                exit_time=pd.Timestamp(tr2['exit_time'])))
            opens.append((e2['symbol'], tr2['direction'],
                          tr2['exit_time'], ent_t))
            return ei2

        ei = _append(pick)
        picks[chk] = ei
        if second_fn is not None:
            rem = [c for c in elig
                   if c is not pick
                   and c[1]['symbol'] != pick[1]['symbol']]
            live_after = [(s2, d2, x2) for (s2, d2, x2, en2)
                          in opens if x2 > ent_t]
            extra = second_fn(rem, pick, live_after, chk, ent_t)
            if extra is not None:
                _append(extra)
    log = pd.DataFrame(rows)
    if len(log):
        log['check'] = pd.to_datetime(log['check'])
        log['exit_time'] = pd.to_datetime(log['exit_time'])
    return log, picks


def make_coolv():
    """mine_planb4._coolv verbatim: stateful two-loss cooldown
    brake (sole-veto designs)."""
    st = {'pending': None, 'committed': [], 'last_ent': None}

    def vf(eq, tr, ent_t):
        ent = pd.Timestamp(ent_t)
        if st['last_ent'] is None or ent != st['last_ent']:
            if st['pending'] is not None:
                st['committed'].append(st['pending'])
            st['pending'] = None
            st['last_ent'] = ent
        brake = False
        done = [(x, n) for (x, n) in st['committed'] if x <= ent]
        if len(done) >= 2:
            (_, n1), (x2, n2) = done[-2], done[-1]
            if n1 < 0 and n2 < 0 \
                    and (ent - x2) <= pd.Timedelta(hours=48):
                brake = True
        if brake:
            return True
        if st['pending'] is None:
            st['pending'] = (pd.Timestamp(tr['exit_time']),
                             float(tr['net_pips']))
        return False
    return vf


def build_combined(inc, cand):
    """validate_new8.build_combined verbatim: incumbent +
    candidate picks under incumbent-priority occupancy.
    Returns (combined, drops, n_accepted). The incumbent frame
    must carry entry_time/exit_time; the candidate frame must
    carry a 'src' column."""
    inc_checks = set(inc['check'])
    inc_by_sym = {s: g[['entry_time', 'exit_time']].values
                  for s, g in inc.groupby('symbol')}
    acc_by_sym = {}
    drops = dict(check_busy=0, symbol_overlap=0)

    def overlaps(arr, e, x):
        if arr is None or len(arr) == 0:
            return False
        return bool(((arr[:, 0] < x) & (e < arr[:, 1])).any())

    acc_rows = []
    for _, r in cand.sort_values('check').iterrows():
        e, x, sym = r['entry_time'], r['exit_time'], r['symbol']
        if r['check'] in inc_checks:
            drops['check_busy'] += 1
            continue
        if overlaps(inc_by_sym.get(sym), e, x):
            drops['symbol_overlap'] += 1
            continue
        arr = acc_by_sym.get(sym)
        if arr is not None and overlaps(np.array(arr), e, x):
            drops['symbol_overlap'] += 1
            continue
        acc_rows.append(r)
        acc_by_sym.setdefault(sym, []).append((e, x))
    keep = ['check', 'symbol', 'direction', 'strategy',
            'entry_time', 'exit_time', 'exit_reason', 'entry_px',
            'exit_px', 'tp_pips_used', 'sl_pips_used', 'gross_pips',
            'src']
    inc_k = inc.copy()
    inc_k['src'] = 'incumbent'
    parts = [inc_k[keep]]
    if acc_rows:
        acc = pd.DataFrame(acc_rows)
        parts.append(acc[keep])
    comb = pd.concat(parts).sort_values('check') \
        .reset_index(drop=True)
    return comb, drops, len(acc_rows)


# ================================================== panel state --
class DesignWalk:
    """Streaming walk157 state for ONE candidate design (panel
    path): the walk's own symbol occupancy from its recorded
    picks, plus the design veto (coolv for the Nov partner)."""

    def __init__(self, equations, veto=None, veto_fn=None):
        self.equations = list(equations)
        self.open_exit = {}
        self.picks = []
        # Jul port (additive): an explicit veto_fn (built by
        # the caller from make_m15v / make_adx25v / make_dxv /
        # make_d1v) takes precedence; 'coolv' and the inline
        # 'd1v' rule are unchanged for existing designs.
        self.veto_fn = veto_fn if veto_fn is not None else (
            make_coolv() if veto == 'coolv' else None)
        self.veto_name = veto

    def step(self, check, rows_at_check):
        """rows_at_check: {(eq_id): tab row dict} for this
        check. Returns the picked row (walk-format dict) or
        None, applying score order, occupancy and the veto
        exactly as walk157 does."""
        chk = pd.Timestamp(check)
        ent_t = chk - pd.Timedelta(minutes=30)
        cands = []
        for ei, e in enumerate(self.equations):
            if e['hour'] != chk.hour:
                continue
            tr = rows_at_check.get(e['id'])
            if tr is None:
                continue
            cands.append((ei, e, tr))
        cands.sort(key=lambda c: -c[1]['score'])
        for ei, e, tr in cands:
            occ = self.open_exit.get(e['symbol'], [])
            if not all(x <= ent_t for x in occ):
                continue
            if self.veto_fn is not None \
                    and self.veto_fn(e, tr, ent_t):
                continue
            if self.veto_fn is None and self.veto_name == 'd1v':
                # mine_planb._agree('d1_state') verbatim: veto
                # when the symbol's daily state at the signal
                # candle disagrees with the trade direction
                # (NaN state -> no veto). The tab row carries
                # the state via CandidateContext.rows_at.
                v = tr.get('d1_state')
                if v is not None and np.isfinite(v):
                    d = 1 if tr['direction'] == 'BUY' else -1
                    if not (d * float(v) > 0):
                        continue
            row = dict(
                check=chk, symbol=e['symbol'],
                direction=tr['direction'], strategy=e['id'],
                score=e['score'], entry_px=tr['entry_px'],
                exit_px=tr['exit_px'],
                tp_pips_used=tr['tp_pips_used'],
                sl_pips_used=tr['sl_pips_used'],
                gross_pips=tr['gross_pips'],
                net_pips=tr['net_pips'],
                exit_reason=tr['exit_reason'],
                hold_h=tr['hold_h'],
                max_hold=int(tr.get('max_hold', MAX_HOLD)),
                exit_time=pd.Timestamp(tr['exit_time']),
                entry_time=ent_t)
            self.open_exit.setdefault(e['symbol'], []).append(
                row['exit_time'])
            self.picks.append(row)
            return row
        return None
