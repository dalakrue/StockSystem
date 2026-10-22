"""Cycle 116 sizing overlays: Nov (Ledoit-Wolf covariance + tail lot halving),
Aug (Ledoit-Wolf), May (HAR volatility lot multiplier), Jan (robust growth
sizing multipliers). All sizing paths via the house policy_path (c104_core);
pip statistics are unchanged by lot overlays by construction."""
import sys, os
import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ovl_lib as L
import tail_series as T

tail = T.load()
OUT = '/home/hatch/workspace/fx/work_ovl/results'


# ------------------------------------------------------------ LW overlay
def lw_multipliers(d):
    """d = sorted sizing frame. Returns (mult array, uplift array).
    Halve the lot when the proposed position's marginal portfolio-vol
    uplift (Ledoit-Wolf covariance of synchronized H1 returns, trailing
    60d, open positions at unit exposure) exceeds 1.10x the trailing
    median uplift (needs >=10 priors) and 0.02 absolute."""
    syms = sorted(d['symbol'].unique())
    closes = pd.concat([L.h1(s)['Close'].rename(s) for s in syms],
                       axis=1, join='inner')
    rets = np.log(closes).diff().dropna()
    ridx = rets.index
    rvals = rets.to_numpy(float)
    sidx = {s: i for i, s in enumerate(syms)}
    n = len(d)
    mult = np.ones(n)
    uplift = np.zeros(n)
    et = d['entry_t'].to_numpy()
    xt = d['exit_t'].to_numpy()
    sy = d['symbol'].to_numpy()
    dn = d['dirn'].to_numpy(float)
    priors = []
    for k in range(n):
        t = et[k]
        open_mask = (et < t) & (xt > t)  # strictly earlier entries still open
        w = np.zeros(len(syms))
        for j in np.where(open_mask)[0]:
            w[sidx[sy[j]]] += dn[j]
        lo = np.searchsorted(ridx, t - pd.Timedelta(days=60))
        hi = np.searchsorted(ridx, t)
        if hi - lo >= 200 and np.any(w != 0):
            lw = LedoitWolf().fit(rvals[lo:hi])
            cov = lw.covariance_
            v0 = float(w @ cov @ w)
            w2 = w.copy()
            w2[sidx[sy[k]]] += dn[k]
            v1 = float(w2 @ cov @ w2)
            if v0 > 0:
                uplift[k] = np.sqrt(v1 / v0) - 1.0
        if len(priors) >= 10:
            med = float(np.median(priors))
            if uplift[k] > 1.10 * med and uplift[k] > 0.02:
                mult[k] = 0.5
        priors.append(uplift[k])
    return mult, uplift


def tail_multipliers(d):
    """Halve lot when the Feb-style adverse-tail forecast at entry is
    elevated (> 0.35 x entry H1 ATR)."""
    mult = np.ones(len(d))
    for k, r in d.iterrows():
        f = T.adv95_at(tail, r['symbol'], int(r['dirn']), r['entry_t'])
        atr = L.atr_at(r['symbol'], r['entry_t']) / L.pip_size(r['symbol'])
        if np.isfinite(f) and np.isfinite(atr) and f > 0.35 * atr:
            mult[k] = 0.5
    return mult


def sizing_block(month, mults_by_ledger):
    """mults_by_ledger: dict ledger_name -> (raw_log, mult array or None).
    Returns markdown lines + dict of path stats."""
    sysname, N, dp, up = L.MONTHS[month]
    lines = []
    paths = {}
    for lname, raw in [('disc', L.load_log(dp)), ('audit', L.load_log(up))]:
        frame = L.sorted_sizing_frame(raw)
        off = L.sizing(raw, N)
        paths[lname] = {'OFF': off}
        row = (f"| {lname} OFF | — | ${off['final']:,.0f} | {off['max_mg']:.2f}% | "
               f"{off['max_ddp']:.2f}% | {off['call']} |")
        rows = [row]
        for oname, marr in mults_by_ledger.get(lname, {}).items():
            on = L.sizing(raw, N, mult_map=marr)
            paths[lname][oname] = on
            rows.append(f"| {lname} {oname} | {int((marr < 1).sum())} | "
                        f"${on['final']:,.0f} | {on['max_mg']:.2f}% | "
                        f"{on['max_ddp']:.2f}% | {on['call']} |")
        lines += rows
    return lines, paths


SZ_HEAD = ("| Path | Trades lot-scaled | Final $ (start $1,000) | Peak margin % "
           "| Max DD % | Margin call |\n|---|---|---|---|---|---|")


def run_lw_month(month, extra_tail=False):
    sysname, N, dp, up = L.MONTHS[month]
    mults = {}
    trig_counts = {}
    for lname, raw in [('disc', L.load_log(dp)), ('audit', L.load_log(up))]:
        frame = L.sorted_sizing_frame(raw)
        m_lw, up_ = lw_multipliers(frame)
        dmap = {'ON (LW)': m_lw}
        trig_counts[lname] = {'LW': int((m_lw < 1).sum())}
        if extra_tail:
            m_t = tail_multipliers(frame)
            m_b = np.minimum(m_lw, m_t)
            dmap['ON (tail)'] = m_t
            dmap['ON (LW+tail)'] = m_b
            trig_counts[lname]['tail'] = int((m_t < 1).sum())
            trig_counts[lname]['both'] = int((m_b < 1).sum())
        mults[lname] = dmap
    rows, paths = sizing_block(month, mults)
    return rows, paths, trig_counts


# ------------------------------------------------------------ Nov
def do_nov():
    rows, paths, tc = run_lw_month('Nov', extra_tail=True)
    a_off = paths['audit']['OFF']
    cands = {k: v for k, v in paths['audit'].items() if k != 'OFF'}
    best_name = min(cands, key=lambda k: cands[k]['max_ddp'])
    best = cands[best_name]
    d_same = paths['disc'][best_name]
    d_off = paths['disc']['OFF']
    improved = (best['max_ddp'] < a_off['max_ddp'] - 0.5
                and d_same['max_ddp'] <= d_off['max_ddp'] + 0.5)
    verdict = 'POSSIBLE' if improved else 'NOT'
    lines = ['# Cycle 116 — November (C93-24) — Ledoit–Wolf covariance + tail-risk lot control\n',
             'Method as specified: Ledoit–Wolf shrinkage covariance of synchronized H1 returns '
             '(trailing 60d) across the pairs the system trades; halve the lot when a proposed '
             'position\'s marginal portfolio-vol uplift exceeds 1.10× the trailing median uplift. '
             'Second overlay: halve the lot when the February-style adverse-tail forecast is '
             'elevated (> 0.35 × entry H1 ATR). Sizing-only: pip statistics are unchanged by '
             'construction; the target stat is the 23.31% sizing drawdown. Paths use the house '
             'policy_path (start $1,000, N=83, realized-balance equity).\n',
             '## Sizing paths\n', SZ_HEAD] + rows + [
             f"\nLot-scaling triggers — discovery: LW {tc['disc']['LW']}, tail {tc['disc']['tail']}; "
             f"audit: LW {tc['audit']['LW']}, tail {tc['audit']['tail']}.\n",
             f'## Verdict: {verdict}\n',
             f"One-line reason: best overlay ({best_name}) moves audit max DD "
             f"{a_off['max_ddp']:.2f}% -> {best['max_ddp']:.2f}% and peak margin "
             f"{a_off['max_mg']:.2f}% -> {best['max_mg']:.2f}% (final $ {a_off['final']:,.0f} -> "
             f"{best['final']:,.0f}); "
             + ('drawdown improves at no pip-stat cost.' if improved
                else 'no material drawdown improvement from covariance/tail lot control.')]
    open(f'{OUT}/nov.md', 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print('NOV DONE', verdict)


# ------------------------------------------------------------ Aug
def do_aug():
    rows, paths, tc = run_lw_month('Aug', extra_tail=False)
    a_off, a_on = paths['audit']['OFF'], paths['audit']['ON (LW)']
    d_off, d_on = paths['disc']['OFF'], paths['disc']['ON (LW)']
    improved = (a_on['max_ddp'] < a_off['max_ddp'] - 0.5
                and d_on['max_ddp'] <= d_off['max_ddp'] + 0.5)
    verdict = 'POSSIBLE' if improved else 'NOT'
    lines = ['# Cycle 116 — August (C67-04) — Ledoit–Wolf covariance sizing overlay\n',
             'Method as specified: entries frozen; Ledoit–Wolf shrinkage covariance of '
             'synchronized H1 returns (trailing 60d); halve the lot when a proposed position\'s '
             'marginal portfolio-vol uplift exceeds 1.10× the trailing median uplift. '
             'Account-level concentration check only — the standing system is untouched. '
             'Paths use the house policy_path (start $1,000, N=121).\n',
             '## Sizing paths\n', SZ_HEAD] + rows + [
             f"\nLot-scaling triggers — discovery: {tc['disc']['LW']}, audit: {tc['audit']['LW']}.\n",
             f'## Verdict: {verdict}\n',
             f"One-line reason: audit max DD {a_off['max_ddp']:.2f}% -> {a_on['max_ddp']:.2f}%, "
             f"peak margin {a_off['max_mg']:.2f}% -> {a_on['max_mg']:.2f}% (final $ "
             f"{a_off['final']:,.0f} -> {a_on['final']:,.0f}); "
             + ('concentration control improves the risk path at no pip-stat cost.' if improved
                else 'the standing path is already so flat that covariance lot control changes nothing material.')]
    open(f'{OUT}/aug.md', 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print('AUG DONE', verdict)


# ------------------------------------------------------------ May (HAR)
def har_multipliers(d):
    syms = sorted(d['symbol'].unique())
    F = {}
    for s in syms:
        m = L.m15(s)
        lr = np.log(m['Close']).diff()
        rv = (lr ** 2).groupby(pd.Grouper(freq='1h')).sum()
        a1 = rv
        a6 = rv.rolling(6, min_periods=6).mean()
        a24 = rv.rolling(24, min_periods=24).mean()
        f = (a1 + a6 + a24) / 3.0
        med = f.rolling(2160, min_periods=720).median()  # trailing ~90d median
        F[s] = pd.DataFrame({'F': f, 'med': med})
    mult = np.ones(len(d))
    for k, r in d.iterrows():
        fr = F[r['symbol']]
        i = fr.index.searchsorted(r['entry_t'], side='right') - 1
        if i >= 0:
            fv, mv = fr['F'].iloc[i], fr['med'].iloc[i]
            if np.isfinite(fv) and np.isfinite(mv) and fv > 0:
                mult[k] = min(1.0, max(0.5, mv / fv))
    return mult


def do_may():
    sysname, N, dp, up = L.MONTHS['May']
    mults = {}
    for lname, raw in [('disc', L.load_log(dp)), ('audit', L.load_log(up))]:
        frame = L.sorted_sizing_frame(raw)
        mults[lname] = {'ON (HAR)': har_multipliers(frame)}
    rows, paths = sizing_block('May', mults)
    a_off, a_on = paths['audit']['OFF'], paths['audit']['ON (HAR)']
    d_off, d_on = paths['disc']['OFF'], paths['disc']['ON (HAR)']
    logg_off = np.log(a_off['final'] / 1000.0)
    logg_on = np.log(a_on['final'] / 1000.0)
    improved = (a_on['max_ddp'] < a_off['max_ddp'] - 0.5
                and logg_on >= logg_off - 0.02
                and d_on['max_ddp'] <= d_off['max_ddp'] + 0.5)
    verdict = 'POSSIBLE' if improved else 'NOT'
    lines = ['# Cycle 116 — May (C88-03) — HAR volatility-forecast sizing overlay\n',
             'Method as specified: M15 squared returns aggregated to H1 realized variance; '
             'HAR forecast of the next 4h from lagged 1/6/24h variance averages. Sizing-only. '
             '**COMPLETION (flagged): the proposal\'s lot multiplier was truncated in the '
             'user\'s paste; implemented as multiplier = min(1, trailing-median(F)/F), floored '
             'at 0.5**, F = forecast variance. May\'s ceiling result makes this a sizing '
             'experiment only — no promotion gate is attempted. Paths: house policy_path '
             '(start $1,000, N=66).\n',
             '## Sizing paths\n', SZ_HEAD] + rows + [
             f"\nAudit log growth: OFF {logg_off:.3f} -> ON {logg_on:.3f}.\n",
             f'## Verdict: {verdict}\n',
             f"One-line reason: audit max DD {a_off['max_ddp']:.2f}% -> {a_on['max_ddp']:.2f}%, "
             f"peak margin {a_off['max_mg']:.2f}% -> {a_on['max_mg']:.2f}%, log growth "
             f"{logg_off:.3f} -> {logg_on:.3f}; "
             + ('volatility-scaled sizing improves the risk path without giving back growth.' if improved
                else 'no material DD improvement, or growth is given back to buy it.')]
    open(f'{OUT}/may.md', 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print('MAY DONE', verdict)


# ------------------------------------------------------------ Jan (robust sizing)
def equity_path_from_lots(raw, lots):
    frame = L.sorted_sizing_frame(raw)
    pnl = frame['net_pips'].to_numpy(float) * lots * 10.0
    order = np.lexsort((np.arange(len(frame)), frame['exit_t'].to_numpy()))
    cum = np.cumsum(pnl[order])
    years = pd.to_datetime(frame['exit_t'].to_numpy()[order]).year
    return years, cum


def do_jan():
    # C60-03's log carries TREND rows that c104_core's resolver would send
    # to December's feature context; the ledger's own inferred direction
    # (load_log 'dirn') is the correct resolution. Directions do not affect
    # the realized-balance path outputs (margin uses open lots only).
    L.K.resolve_dir_row = lambda row: int(row['dirn'])  # noqa: E731
    sysname, N, dp, up = L.MONTHS['Jan']
    disc = L.load_log(dp)
    audit = L.load_log(up)
    rows = []
    results = {}
    for gm in [1.0, 0.75, 0.50, 0.25]:
        p = L.sizing(disc, N, global_mult=gm)
        years, cum = equity_path_from_lots(disc, p['lots'])
        yg = {}
        for y in range(2016, 2025):
            e_start = 1000.0 + (cum[years < y].sum() if (years < y).any() else 0.0)
            e_end = 1000.0 + (cum[years <= y].sum() if (years <= y).any() else 0.0)
            yg[y] = np.log(e_end / e_start) if e_start > 0 and e_end > 0 else -9.99
        worst = min(yg.values())
        ok = p['max_mg'] <= 60.0 and p['max_ddp'] <= 30.0 and not p['call']
        results[gm] = dict(path=p, worst=worst, ok=ok, yg=yg)
        rows.append(f"| {gm:.2f} | ${p['final']:,.0f} | {p['max_mg']:.2f}% | "
                    f"{p['max_ddp']:.2f}% | {worst:.3f} | {'yes' if ok else 'NO'} |")
    feas = {g: r for g, r in results.items() if r['ok']}
    chosen = max(feas, key=lambda g: feas[g]['worst']) if feas else 1.0
    pa = L.sizing(audit, N, global_mult=chosen)
    pa_off = L.sizing(audit, N)
    changed = chosen != 1.0 and results[chosen]['worst'] > results[1.0]['worst'] + 0.005
    verdict = 'POSSIBLE' if changed else 'NOT'
    lines = ['# Cycle 116 — January (C60-03) — Distributionally robust growth sizing\n',
             'Method as specified: entries frozen; lot multipliers 0.25 / 0.50 / 0.75 / 1.00; '
             'choose the multiplier maximizing the WORST training-year (2016–2024) mean log '
             'growth subject to peak margin ≤ 60% and max DD ≤ 30% on the house policy_path '
             '(start $1,000, N=83).\n',
             '## Discovery sizing paths by multiplier\n',
             '| Multiplier | Final $ | Peak margin % | Max DD % | Worst-year log growth | Within limits |\n'
             '|---|---|---|---|---|---|'] + rows + [
             f"\nChosen multiplier: **{chosen:.2f}** (worst-year log growth "
             f"{results[chosen]['worst']:.3f} vs {results[1.0]['worst']:.3f} at 1.00).\n",
             f"Audit path at chosen multiplier: final ${pa['final']:,.0f}, peak margin "
             f"{pa['max_mg']:.2f}%, max DD {pa['max_ddp']:.2f}% (at 1.00: ${pa_off['final']:,.0f}, "
             f"{pa_off['max_mg']:.2f}%, {pa_off['max_ddp']:.2f}%).\n",
             f'## Verdict: {verdict}\n',
             (f"One-line reason: multiplier {chosen:.2f} raises the worst training year's log "
              f"growth from {results[1.0]['worst']:.3f} to {results[chosen]['worst']:.3f} within "
              'the margin/DD limits — robust sizing buys worst-year growth.' if changed
              else f"One-line reason: the robust criterion selects 1.00 (worst-year log growth "
                   f"{results[1.0]['worst']:.3f}); no smaller multiplier improves the worst "
                   'training year within limits — nothing to change.')]
    open(f'{OUT}/jan.md', 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print('JAN DONE', verdict, 'chosen', chosen)


if __name__ == '__main__':
    which = sys.argv[1]
    {'nov': do_nov, 'aug': do_aug, 'may': do_may, 'jan': do_jan}[which]()
