"""Cycle 116 / Jul: Bayesian change-point partial-exit overlay on C78-34.
Lightweight online BOCD (Adams-MacKay), hazard 1/50, Normal-Inverse-Gamma
predictive (mu0=0, kappa0=1, alpha0=2, beta0 = symbol H1-return variance),
run-length cap 260 — documented simplification per the brief. Partial exit
50% only when P(change within last 4 H1 bars) >= 0.60 AND position losing
AND original H1 direction unsupported (last H1 close adverse vs entry)."""
import sys, os
import numpy as np
import pandas as pd
from scipy import stats as sps
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ovl_lib as L

sysname, N, dp, up = L.MONTHS['Jul']
disc, un = L.load_log(dp), L.load_log(up)
HAZ = 1.0 / 50.0
RMAX = 260


def bocd_cp_prob(x, beta0):
    """x: H1 log returns window. Returns array cp[t] = P(run length <= 4)
    at each t (posterior after seeing x[t])."""
    T = len(x)
    cp = np.zeros(T)
    # run-length sufficient stats, index r = run length (0..RMAX)
    mu = np.zeros(RMAX + 1)
    kap = np.ones(RMAX + 1)
    alp = np.full(RMAX + 1, 2.0)
    bet = np.full(RMAX + 1, beta0)
    logpost = np.full(RMAX + 1, -np.inf)
    logpost[0] = 0.0
    for t in range(T):
        xt = x[t]
        nu = 2 * alp
        scale = np.sqrt(bet * (kap + 1) / (alp * kap))
        pred = sps.t.pdf(xt, nu, loc=mu, scale=scale)
        pred = np.maximum(pred, 1e-300)
        logpred = np.log(pred)
        growth = logpost + logpred + np.log1p(-HAZ)
        cp_new = np.logaddexp.reduce(logpost + logpred) + np.log(HAZ)
        new = np.full(RMAX + 1, -np.inf)
        new[0] = cp_new
        new[1:] = growth[:-1]
        # update sufficient stats (runs that continue), then insert prior run
        mu_n = (kap * mu + xt) / (kap + 1)
        bet_n = bet + kap * (xt - mu) ** 2 / (2 * (kap + 1))
        kap_n = kap + 1
        alp_n = alp + 0.5
        mu = np.concatenate([[0.0], mu_n[:-1]])
        kap = np.concatenate([[1.0], kap_n[:-1]])
        alp = np.concatenate([[2.0], alp_n[:-1]])
        bet = np.concatenate([[beta0], bet_n[:-1]])
        m = new.max()
        logpost = new - (m + np.log(np.exp(new - m).sum()))
        post = np.exp(logpost)
        cp[t] = post[:5].sum()
    return cp


def apply_jul(d):
    gross = d['gross_pips'].to_numpy(float).copy()
    trig = np.zeros(len(d), dtype=bool)
    cache = {}
    for i, r in d.iterrows():
        sym = r['symbol']
        if sym not in cache:
            g = L.h1(sym)
            lr = np.log(g['Close']).diff().to_numpy(float)
            cache[sym] = (g.index, lr, float(np.nanstd(lr)))
        idx, lr, sd = cache[sym]
        pip = L.pip_size(sym)
        dirn = int(r['dirn'])
        entry = float(r['entry_px'])
        et, xt = r['entry_t'], r['exit_time']
        bars = L.m15(sym)
        # H1 bar index covering entry; window starts RMAX bars earlier
        j0 = idx.searchsorted(et, side='right') - 1
        if j0 < 10:
            continue
        start = max(1, j0 - RMAX)
        x = lr[start:j0 + 1]  # returns up to the bar ending at entry
        x = np.where(np.isfinite(x), x, 0.0)
        t = et + pd.Timedelta(hours=1)
        while t < xt:
            j = idx.searchsorted(t, side='right') - 1  # last completed H1 bar
            if j > j0:
                newrets = lr[j0 + 1:j + 1]
                newrets = np.where(np.isfinite(newrets), newrets, 0.0)
                x = np.concatenate([x, newrets])
                j0 = j
            if t in bars.index:
                px = float(bars.at[t, 'Open'])
                fp = dirn * (px - entry) / pip
                if -float(r['sl_pips_used']) < fp < float(r['tp_pips_used']):
                    last_close = float(L.h1(sym)['Close'].iloc[j])
                    unsupported = dirn * (last_close - entry) < 0
                    if fp >= 0 or not unsupported:
                        t += pd.Timedelta(hours=1)
                        continue
                    cpp = bocd_cp_prob(x[-(RMAX + 60):], sd * sd)
                    if cpp[-1] >= 0.60:
                        gross[i] = 0.5 * fp + 0.5 * gross[i]
                        trig[i] = True
                        break
            t += pd.Timedelta(hours=1)
    out = d.copy()
    out['gross_pips'] = gross
    out['net_pips'] = gross - L.COST
    return out, trig


res = {}
for name, d in [('disc', disc), ('audit', un)]:
    on, tg = apply_jul(d)
    res[name] = {'OFF': L.stats(d), 'ON': L.stats(on), 'trig': int(tg.sum())}

a_off, a_on = res['audit']['OFF'], res['audit']['ON']
d_off, d_on = res['disc']['OFF'], res['disc']['ON']
improved = (a_on['leftover'] > a_off['leftover'] and d_on['leftover'] > d_off['leftover']
            and a_on['win'] > 80 and d_on['win'] > 80)
verdict = 'POSSIBLE' if improved else 'NOT'
lines = []
lines.append('# Cycle 116 — July (C78-34) — Bayesian change-point partial-exit overlay\n')
lines.append('Method as specified, with the brief-approved lightweight simplification: online '
             'Bayesian change-point detection (Adams–MacKay run-length posterior, hazard 1/50, '
             'NIG predictive, run-length cap 260) on H1 log returns. 50% partial exit only when '
             'P(change within last 4 H1 bars) ≥ 0.60 AND the position is losing AND the original '
             'H1 direction is unsupported (last H1 close adverse vs entry). Target stat: the '
             '7.50 cost/loss ratio.\n')
for name, lab in [('disc', 'Discovery'), ('audit', '2025 audit')]:
    lines.append(f'## {lab}\n\n{L.TABLE_HEAD}')
    lines.append(L.fmt_row('OFF', res[name]['OFF']))
    lines.append(L.fmt_row('ON', res[name]['ON']))
    lines.append(f"\nTrades triggering the overlay: {res[name]['trig']}.\n")
lines.append(f'## Verdict: {verdict}\n')
lines.append(f"One-line reason: audit leftover {a_off['leftover']:.2f}% -> {a_on['leftover']:.2f}%, "
             f"discovery leftover {d_off['leftover']:.2f}% -> {d_on['leftover']:.2f}%, audit avg loss "
             f"{a_off['avg_loss']:.1f} -> {a_on['avg_loss']:.1f} pips; "
             + ('leftover improves on both ledgers with win intact.' if improved
                else 'no leftover improvement on both ledgers at screening level.'))
open('/home/hatch/workspace/fx/work_ovl/results/jul.md', 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
