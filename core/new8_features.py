"""NEW8 feature machinery -- app port (2026-10-27).

Verbatim ports of the NEW8 research feature builders, with the
data inputs parameterised (frames in, feature frame out) instead
of read from fx_data.db / the research caches:

  * base block  = c70_engine.add_features (work_c70/scripts),
    exactly as new8_lib.build_features_new9 applies it, plus the
    atr_pips line (pip convention of new8_lib.pip_size_new9).
  * r4 block    = build_features_r4.py's per-symbol block, in the
    form build_features_all29_planb.add_r4_columns carries it
    (volume series and M30 frame passed in).
  * planb block = build_features_all29_planb.add_planb_columns
    (helpers fisher10_calc / kama_calc / wma from
    build_features_planb.py).
  * b2cf block  = the M15 / H4 confirmation layers of
    build_features_planb2.build_one (cf_m15dev, cf_h4dev).
  * b3 block    = build_features_planb3.build_one (uo,
    cf_m30dev, cf2_stack).
  * b4 block    = build_features_planb4.build_one (coppock,
    rvi10, rvi_state, stc, kelt_p, cf_d1dev, cf3_stack).
  * b2x block   = build_features_planb2.build_one own-frame
    columns (bb_bw, roc24, adx_chg, vma_dev, ha_body,
    psar_state, st_state) -- ported 2026-10-28 for the Apr
    Q09 layer; the B-2 rsi14 overwrite is NOT applied (no
    shipped design reads rsi14 through this block, and the
    overwrite would alter proven b2cf-era frames).
  * b8 block    = build_features_planb8b pass 2 (quote-
    currency baskets from the cross-symbol context).
  * b9 block    = build_features_planb9.build_one.
  * b9c block   = build_features_planb9c.build_one (M15
    columns; last M15 bar whose start is < t).
  * pv block    = parallel_vote/pv_common vote shares
    (leg_votes / pool_share verbatim; only the pools a
    design's equations reference are materialised).
  * pbc block   = parallel_score/build_features_pbranch
    per-symbol block (pb_* H1 + pbc_* M15 columns; M15
    aligned by last bar starting at or before t).

Conventions match the research builders exactly: the value on
H1 bar t uses bars up to and including t; M30 values come from
the M30 bar starting at t; H4 values from the last H4 bar
completed at or before t; D1 values from the last D1 bar
completed before the signal day. DOLLARIDX/DXY: vol_r / vol_z
and the Plan-B volume-indicator columns are NaN by construction
and xdx_* is NaN on the dollar series itself (research
convention; the app series name is 'DXY', the research name
'DOLLARIDX' -- both are recognised).

The era replay harness (work_29load/harness_new8.py) proves
these ports reproduce the research feature frames and, through
them, the recorded NEW8 ledgers exactly.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DOLLAR_SYMBOLS = ("DOLLARIDX", "DXY")
TP_CLIP = (10.0, 500.0)
SL_CLIP = (5.0, 100.0)


def pip_size_new8(symbol: str) -> float:
    """new8_lib.pip_size_new9: JPY pairs 0.01, the dollar index
    0.01 (PROVISIONAL in research), everything else 0.0001."""
    s = str(symbol).upper()
    if s in DOLLAR_SYMBOLS:
        return 0.01
    return 0.01 if "JPY" in s else 0.0001


def is_dollar(symbol: str) -> bool:
    return str(symbol).upper() in DOLLAR_SYMBOLS


# ============================================================ base
# c70_engine helpers + add_features, verbatim (only the frame
# plumbing differs: the research frame carries a 'Datetime'
# column; the app frame is Datetime-indexed -- build_symbol_
# features normalises before calling).
def _stoch(x, n):
    lo = x.rolling(n, min_periods=n).min()
    hi = x.rolling(n, min_periods=n).max()
    return 100.0 * (x - lo) / (hi - lo).replace(0.0, np.nan)


def _xover(a, b):
    """Event col: +1 where a crosses above b, -1 below, else 0."""
    return np.where((a.shift(1) <= b.shift(1)) & (a > b), 1.0,
           np.where((a.shift(1) >= b.shift(1)) & (a < b), -1.0, 0.0))


def _ehlers_filters(cl):
    """Cyber Cycle (alpha=0.07) and Bandpass (P=20, BW=0.3)."""
    x = cl.to_numpy(dtype=float)
    n = len(x)
    sm = np.full(n, np.nan)
    xs = np.convolve(np.nan_to_num(x), [1, 2, 2, 1], mode='full')[:n] / 6.0
    sm[3:] = xs[3:]
    a = 0.07
    cyc = np.zeros(n)
    bp = np.zeros(n)
    beta = np.cos(2.0 * np.pi / 20.0)
    gamma = 1.0 / np.cos(2.0 * np.pi * 0.3 / 20.0)
    abp = gamma - np.sqrt(max(gamma * gamma - 1.0, 0.0))
    s = np.nan_to_num(sm)
    for i in range(2, n):
        cyc[i] = ((1 - 0.5 * a) ** 2 * (s[i] - 2 * s[i - 1] + s[i - 2])
                  + 2 * (1 - a) * cyc[i - 1] - (1 - a) ** 2 * cyc[i - 2])
        bp[i] = (0.5 * (1 - abp) * (x[i] - x[i - 2])
                 + beta * (1 + abp) * bp[i - 1] - abp * bp[i - 2])
    return cyc, bp


def _tlb_state(cl):
    """Three Line Break: state (+1 up regime / -1 down), flips."""
    x = cl.to_numpy(dtype=float)
    n = len(x)
    state = np.zeros(n)
    flip = np.zeros(n)
    lines = []
    cur = 0
    for i in range(n):
        c = x[i]
        if len(lines) == 0:
            if i > 0 and c != x[0]:
                lines.append((x[0], c))
                cur = 1 if c > x[0] else -1
                flip[i] = cur
        else:
            s0, e0 = lines[-1]
            d = 1 if e0 > s0 else -1
            if d > 0:
                if c > e0:
                    lines.append((e0, c))
                elif len(lines) >= 1:
                    ref = min(min(a, b) for a, b in lines[-3:])
                    if c < ref:
                        lines.append((e0, c))
                        flip[i] = -1.0
            else:
                if c < e0:
                    lines.append((e0, c))
                else:
                    ref = max(max(a, b) for a, b in lines[-3:])
                    if c > ref:
                        lines.append((e0, c))
                        flip[i] = 1.0
            s0, e0 = lines[-1]
            cur = 1 if e0 > s0 else -1
        state[i] = cur
    return state, flip


def _zz_state(hi, lo, cl, atr):
    """ZigZag legs with dynamic threshold 2.0*ATR."""
    h = hi.to_numpy(dtype=float); l = lo.to_numpy(dtype=float)
    c = cl.to_numpy(dtype=float); a = atr.to_numpy(dtype=float)
    n = len(c)
    state = np.zeros(n)
    brk = np.zeros(n)
    leg = 0
    leg_hi = -np.inf; leg_lo = np.inf
    piv_hi = np.nan; piv_lo = np.nan
    for i in range(n):
        thr = 2.0 * a[i] if np.isfinite(a[i]) and a[i] > 0 else np.inf
        if leg == 0:
            leg_hi = max(leg_hi, h[i]); leg_lo = min(leg_lo, l[i])
            if c[i] - leg_lo >= thr:
                leg = 1; piv_lo = leg_lo; leg_hi = h[i]
            elif leg_hi - c[i] >= thr:
                leg = -1; piv_hi = leg_hi; leg_lo = l[i]
        elif leg == 1:
            leg_hi = max(leg_hi, h[i])
            if np.isfinite(piv_hi) and c[i] > piv_hi:
                brk[i] = 1.0
            if leg_hi - c[i] >= thr:
                piv_hi = leg_hi; leg = -1; leg_lo = l[i]
        else:
            leg_lo = min(leg_lo, l[i])
            if np.isfinite(piv_lo) and c[i] < piv_lo:
                brk[i] = -1.0
            if c[i] - leg_lo >= thr:
                piv_lo = leg_lo; leg = 1; leg_hi = h[i]
        state[i] = leg
    return state, brk


def _renko_state(cl, atr):
    """Renko with dynamic brick 0.5*ATR (causal)."""
    c = cl.to_numpy(dtype=float); a = atr.to_numpy(dtype=float)
    n = len(c)
    state = np.zeros(n)
    flip = np.zeros(n)
    base = c[0]
    cur = 0
    for i in range(n):
        b = 0.5 * a[i] if np.isfinite(a[i]) and a[i] > 0 else np.inf
        if np.isfinite(b):
            moved = False
            while c[i] - base >= b:
                base += b; moved = True
                if cur != 1:
                    cur = 1; flip[i] = 1.0
            while base - c[i] >= b:
                base -= b; moved = True
                if cur != -1:
                    cur = -1; flip[i] = -1.0
            _ = moved
        state[i] = cur
    return state, flip


def add_features_base(df):
    """c70_engine.add_features verbatim. Input: frame with a
    'Datetime' column + Open/High/Low/Close. Output: same frame
    plus the base feature columns (Datetime column retained)."""
    g = df.copy().reset_index(drop=True)
    op, cl, hi, lo = g['Open'], g['Close'], g['High'], g['Low']
    tr = pd.concat([(hi - lo), (hi - cl.shift(1)).abs(),
                    (lo - cl.shift(1)).abs()], axis=1).max(axis=1)
    g['atr14'] = tr.rolling(14, min_periods=1).mean()
    g['atr_med30d'] = g['atr14'].rolling(24 * 30, min_periods=14).median()
    g['atr_ratio'] = g['atr14'] / g['atr_med30d']
    g['mom24'] = (cl - cl.shift(24)) / g['atr14']
    g['mom24'] = g['mom24'].replace([np.inf, -np.inf], np.nan)
    atr = g['atr14'].replace(0.0, np.nan)

    d = cl.diff()
    ag = d.clip(lower=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    al = (-d.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rsi = 100.0 - 100.0 / (1.0 + ag / al.replace(0.0, np.nan))
    g['rsi14'] = rsi
    k = _stoch(rsi, 14).rolling(3, min_periods=3).mean()
    dd = k.rolling(3, min_periods=3).mean()
    g['srsi_k'] = k
    g['srsi_d'] = dd
    g['srsi_x'] = _xover(k, dd)

    cyc, bp = _ehlers_filters(cl)
    g['cyber_atr'] = pd.Series(cyc, index=g.index) / atr
    g['cyber_x'] = np.where((np.roll(cyc, 1) <= np.roll(cyc, 2)) & (cyc > np.roll(cyc, 1)), 1.0,
                   np.where((np.roll(cyc, 1) >= np.roll(cyc, 2)) & (cyc < np.roll(cyc, 1)), -1.0, 0.0))
    g['cyber_x'][:3] = 0.0
    g['bp_atr'] = pd.Series(bp, index=g.index) / atr
    bps = pd.Series(bp, index=g.index)
    g['bp_x'] = _xover(bps, bps * 0.0)

    ap = (hi + lo + cl) / 3.0
    esa = ap.ewm(span=10, min_periods=10, adjust=False).mean()
    dev = (ap - esa).abs().ewm(span=10, min_periods=10, adjust=False).mean()
    ci = (ap - esa) / (0.015 * dev.replace(0.0, np.nan))
    wt1 = ci.ewm(span=21, min_periods=21, adjust=False).mean()
    wt2 = wt1.rolling(4, min_periods=4).mean()
    g['wt1'] = wt1
    g['wt2'] = wt2
    g['wt_diff'] = wt1 - wt2
    g['wt_x'] = _xover(wt1, wt2)

    mom = cl.diff()
    num = mom.ewm(span=25, min_periods=25, adjust=False).mean().ewm(span=13, min_periods=13, adjust=False).mean()
    den = mom.abs().ewm(span=25, min_periods=25, adjust=False).mean().ewm(span=13, min_periods=13, adjust=False).mean()
    tsi = 100.0 * num / den.replace(0.0, np.nan)
    tsig = tsi.ewm(span=7, min_periods=7, adjust=False).mean()
    g['tsi'] = tsi
    g['tsi_sig'] = tsig
    g['tsi_diff'] = tsi - tsig
    g['tsi_x'] = _xover(tsi, tsig)

    sq = np.sqrt(14.0)
    g['rwi_hi'] = (hi - lo.shift(14)) / (atr * sq)
    g['rwi_lo'] = (hi.shift(14) - lo) / (atr * sq)
    g['rwi_diff'] = g['rwi_hi'] - g['rwi_lo']
    g['rwi_max'] = np.maximum(g['rwi_hi'], g['rwi_lo'])

    n_c = 14
    xbar = (n_c - 1) / 2.0
    xvar = ((np.arange(n_c) - xbar) ** 2).mean()
    ymean = cl.rolling(n_c, min_periods=n_c).mean()
    xymean = cl.rolling(n_c, min_periods=n_c).apply(
        lambda y: float(np.dot(y, np.arange(n_c)) / n_c), raw=True)
    slope = (xymean - xbar * ymean) / xvar
    fc = ymean + slope * (n_c - 1 - xbar)
    cfo = 100.0 * (cl - fc) / cl
    g['cfo'] = cfo
    g['cfo_x'] = _xover(cfo, cfo * 0.0)

    tlb_s, tlb_f = _tlb_state(cl)
    g['tlb_state'] = tlb_s
    g['tlb_flip'] = tlb_f
    zz_s, zz_b = _zz_state(hi, lo, cl, g['atr14'])
    g['zz_state'] = zz_s
    g['zz_break'] = zz_b
    rk_s, rk_f = _renko_state(cl, g['atr14'])
    g['renko_state'] = rk_s
    g['renko_flip'] = rk_f

    ev_cols = ['srsi_x', 'cyber_x', 'bp_x', 'wt_x', 'tsi_x', 'cfo_x',
               'tlb_flip', 'zz_break', 'renko_flip']
    for c in ev_cols:
        g[c] = np.nan_to_num(g[c].to_numpy(dtype=float), nan=0.0)
    return g


# ============================================================ r4 --
def _xover0(diff):
    """build_features_r4.xover: crossover event of a diff series
    vs 0 (+1 up, -1 down, else 0)."""
    d = np.asarray(diff, dtype=float)
    prev = np.concatenate([[np.nan], d[:-1]])
    out = np.where((prev <= 0) & (d > 0), 1.0,
                   np.where((prev >= 0) & (d < 0), -1.0, 0.0))
    out[~np.isfinite(d) | ~np.isfinite(prev)] = 0.0
    return out


def wilder_adx(fr):
    """build_features_r4.wilder_adx verbatim (frame in, array
    out). fr: frame with High/Low/Close columns (row order)."""
    h = fr['High'].to_numpy(float)
    l = fr['Low'].to_numpy(float)
    c = fr['Close'].to_numpy(float)
    n = len(c)
    tr = np.zeros(n)
    pdm = np.zeros(n)
    mdm = np.zeros(n)
    for i in range(1, n):
        up = h[i] - h[i - 1]
        dn = l[i - 1] - l[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
        pc = c[i - 1]
        tr[i] = max(h[i] - l[i], abs(h[i] - pc), abs(l[i] - pc))

    def smooth(x):
        out = np.full(n, np.nan)
        s = np.nan
        for i in range(1, n):
            if i == 14:
                s = x[1:15].sum()
                out[i] = s
            elif i > 14:
                s = s - s / 14.0 + x[i]
                out[i] = s
        return out

    str_, spdm, smdm = smooth(tr), smooth(pdm), smooth(mdm)
    with np.errstate(invalid='ignore', divide='ignore'):
        pdi = 100 * spdm / str_
        mdi = 100 * smdm / str_
        dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
    adx = np.full(n, np.nan)
    vals = []
    for i in range(n):
        if np.isfinite(dx[i]):
            vals.append(dx[i])
            if len(vals) == 14:
                adx[i] = float(np.mean(vals))
            elif len(vals) > 14:
                adx[i] = (adx[i - 1] * 13 + dx[i]) / 14.0
    return adx


def add_r4_columns(f, fr, sym, dx_mom, volume, m30):
    """build_features_all29_planb.add_r4_columns verbatim, with
    the DB reads replaced by passed-in data:
      f      -- base feature frame (Datetime index)
      fr     -- H1 frame with a 'Datetime' column (research shape)
      volume -- H1 Volume Series indexed like the research
                load_volume_h1 result (Datetime index)
      m30    -- M30 frame with a 'Datetime' column (research
                B4.load_m30 shape; the app resamples it from M15,
                which the era harness proves identical)
      dx_mom -- DOLLARIDX mom24 Series (Datetime index)
    """
    idx = f.index
    cl = fr.set_index('Datetime').loc[idx, 'Close']
    hi = fr.set_index('Datetime').loc[idx, 'High']
    lo = fr.set_index('Datetime').loc[idx, 'Low']
    atr = f['atr14']
    if not is_dollar(sym):
        v = volume.reindex(idx).astype(float)
        med = v.shift(1).rolling(24).median()
        q25 = v.shift(1).rolling(24).quantile(0.25)
        q75 = v.shift(1).rolling(24).quantile(0.75)
        iqr = (q75 - q25).replace(0.0, np.nan)
        f['vol_r'] = (v / med.replace(0.0, np.nan)).to_numpy()
        f['vol_z'] = ((v - med) / iqr).to_numpy()
    else:
        f['vol_r'] = np.nan
        f['vol_z'] = np.nan
    if m30 is not None:
        m30c = m30['Close']
        ema20 = m30c.ewm(span=20, adjust=False).mean()
        m30_state = np.sign((m30c - ema20).to_numpy())
        m30_mom_raw = (m30c - m30c.shift(8)).to_numpy()
        starts = m30['Datetime'].to_numpy()
        pos = np.searchsorted(starts, idx.to_numpy(),
                              side='right') - 1
        ok = pos >= 0
        st = np.full(len(idx), np.nan)
        mm = np.full(len(idx), np.nan)
        st[ok] = m30_state[pos[ok]]
        mm[ok] = m30_mom_raw[pos[ok]]
        f['m30_state'] = st
        f['m30_mom'] = mm / atr.to_numpy()
    else:
        # No M15/M30 history for this symbol in the app right
        # now: the M30 columns stay NaN and any equation
        # reading them simply does not fire (never a crash).
        f['m30_state'] = np.nan
        f['m30_mom'] = np.nan
    h1 = fr.copy()
    h1['b'] = h1['Datetime'].dt.floor('4h')
    h4 = h1.groupby('b').agg(Open=('Open', 'first'),
                             High=('High', 'max'),
                             Low=('Low', 'min'),
                             Close=('Close', 'last')).reset_index()
    h4c = h4['Close']
    h4ema = h4c.ewm(span=10, adjust=False).mean()
    h4_state = np.sign((h4c - h4ema).to_numpy())
    h4_mom_raw = (h4c - h4c.shift(6)).to_numpy()
    h4_starts = h4['b'].to_numpy()
    lim = (idx - pd.Timedelta(hours=4)).to_numpy()
    pos4 = np.searchsorted(h4_starts, lim, side='right') - 1
    ok4 = pos4 >= 0
    st4 = np.full(len(idx), np.nan)
    mm4 = np.full(len(idx), np.nan)
    st4[ok4] = h4_state[pos4[ok4]]
    mm4[ok4] = h4_mom_raw[pos4[ok4]]
    f['h4_state'] = st4
    f['h4_mom'] = mm4 / atr.to_numpy()
    if not is_dollar(sym):
        xm = dx_mom.reindex(idx).to_numpy() \
            if dx_mom is not None else np.full(len(idx), np.nan)
        f['xdx_mom'] = xm
        f['xdx_state'] = np.sign(xm)
    else:
        f['xdx_mom'] = np.nan
        f['xdx_state'] = np.nan
    clv = cl.to_numpy(float)
    hiv = hi.to_numpy(float)
    lov = lo.to_numpy(float)
    atrv = atr.to_numpy(float)
    ema12 = cl.ewm(span=12, adjust=False).mean()
    ema26 = cl.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_sig = macd_line.ewm(span=9, adjust=False).mean()
    diff = (macd_line - macd_sig).to_numpy()
    f['macd_h'] = diff / atrv
    f['macd_x'] = _xover0(diff)
    mid = cl.rolling(20).mean()
    sd = cl.rolling(20).std()
    upper = mid + 2 * sd
    lower = mid - 2 * sd
    f['bb_p'] = ((cl - lower) / (upper - lower)
                 .replace(0.0, np.nan)).to_numpy()
    tp = (hi + lo + cl) / 3.0
    sma = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(
        lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    f['cci20'] = ((tp - sma) / (0.015 * mad)
                  .replace(0.0, np.nan)).to_numpy()
    hh14 = hi.rolling(14).max()
    ll14 = lo.rolling(14).min()
    f['wr14'] = ((hh14 - cl) / (hh14 - ll14)
                 .replace(0.0, np.nan) * -100.0).to_numpy()
    f['adx14'] = wilder_adx(fr.set_index('Datetime').loc[idx]
                            .reset_index())
    ema200 = cl.ewm(span=200, adjust=False).mean()
    f['ema_dev'] = ((cl - ema200) / atr).to_numpy()
    hh20 = hi.rolling(20).max()
    ll20 = lo.rolling(20).min()
    f['don_p'] = ((cl - ll20) / (hh20 - ll20)
                  .replace(0.0, np.nan)).to_numpy()
    f['roc6'] = ((cl - cl.shift(6)) / atr).to_numpy()
    f['roc48'] = ((cl - cl.shift(48)) / atr).to_numpy()
    return f


# ========================================================= planb --
def _wma(s, n):
    """build_features_planb.wma verbatim."""
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n).apply(lambda x: float(np.dot(x, w) / w.sum()),
                              raw=True)


def fisher10_calc(cl, hi, lo):
    """build_features_planb.fisher10_calc verbatim."""
    n = len(cl)
    ll = lo.rolling(10).min()
    hh = hi.rolling(10).max()
    rng = (hh - ll).replace(0.0, np.nan)
    pos = ((cl - ll) / rng).to_numpy(float)
    x0 = np.clip(2.0 * pos - 1.0, -0.999, 0.999)
    out = np.full(n, np.nan)
    v = 0.0
    fish = 0.0
    started = False
    for i in range(n):
        if not np.isfinite(x0[i]):
            continue
        v = 0.33 * x0[i] + 0.67 * v
        f = 0.5 * np.log((1.0 + v) / (1.0 - v)) + 0.5 * fish
        fish = f
        if started or i >= 9:
            out[i] = f
            started = True
    return out


def kama_calc(clv, period=10, fast=2.0, slow=30.0):
    """build_features_planb.kama_calc verbatim."""
    n = len(clv)
    out = np.full(n, np.nan)
    if n <= period:
        return out
    diff = np.abs(np.diff(clv))
    vol = np.convolve(diff, np.ones(period), mode='valid')
    change = np.abs(clv[period:] - clv[:-period])
    er = np.where(vol > 0, change / vol, 0.0)
    fsc = 2.0 / (fast + 1.0)
    ssc = 2.0 / (slow + 1.0)
    sc = (er * (fsc - ssc) + ssc) ** 2
    kama = clv[period]
    out[period] = kama
    for i in range(period + 1, n):
        kama = kama + sc[i - period] * (clv[i] - kama)
        out[i] = kama
    return out


VOL_IND = ['vwap_dev', 'obv_z', 'mfi14', 'cmf20']


def add_planb_columns(f, fr, sym, volume):
    """build_features_all29_planb.add_planb_columns verbatim
    (volume passed in place of the DB read)."""
    idx = f.index
    base = fr.set_index('Datetime').loc[idx]
    cl = base['Close']
    hi = base['High']
    lo = base['Low']
    atr = f['atr14']
    atrv = atr.to_numpy(float)
    clv = cl.to_numpy(float)
    ll14 = lo.rolling(14).min()
    hh14 = hi.rolling(14).max()
    rawk = (100.0 * (cl - ll14) / (hh14 - ll14)
            .replace(0.0, np.nan))
    stoch = rawk.rolling(3).mean()
    f['stoch_k'] = stoch.to_numpy()
    f['stoch_x'] = _xover0((stoch - stoch.rolling(3).mean())
                           .to_numpy(float))
    mp = (hi + lo) / 2.0
    f['ao'] = ((mp.rolling(5).mean() - mp.rolling(34).mean())
               / atr).to_numpy()
    f['fisher10'] = fisher10_calc(cl, hi, lo)
    f['kama_dev'] = (clv - kama_calc(clv)) / atrv
    hma_in = 2.0 * _wma(cl, 10) - _wma(cl, 21)
    hull = _wma(hma_in, 5)
    f['hull_dev'] = ((cl - hull) / atr).to_numpy()
    a = atrv
    cnt = np.zeros(len(a))
    for lag in range(10, 481, 10):
        cnt[lag:] += (a[lag:] >= a[:-lag]).astype(float)
    rank = cnt / 48.0
    rank[:480] = np.nan
    rank[~np.isfinite(a)] = np.nan
    f['atr_rank'] = rank
    hh48 = hi.rolling(48).max()
    ll48 = lo.rolling(48).min()
    f['don48_p'] = ((cl - ll48) / (hh48 - ll48)
                    .replace(0.0, np.nan)).to_numpy()
    h1 = fr.copy()
    h1['b'] = h1['Datetime'].dt.floor('1D')
    d1 = h1.groupby('b').agg(Close=('Close', 'last')).reset_index()
    d1c = d1['Close']
    d1ema = d1c.ewm(span=10, adjust=False).mean()
    d1_state = np.sign((d1c - d1ema).to_numpy())
    d1_mom_raw = (d1c - d1c.shift(5)).to_numpy()
    d1_starts = d1['b'].to_numpy()
    lim = (idx - pd.Timedelta(days=1)).to_numpy()
    posd = np.searchsorted(d1_starts, lim, side='right') - 1
    okd = posd >= 0
    std = np.full(len(idx), np.nan)
    mmd = np.full(len(idx), np.nan)
    std[okd] = d1_state[posd[okd]]
    mmd[okd] = d1_mom_raw[posd[okd]]
    f['d1_state'] = std
    f['d1_mom'] = mmd / atrv
    if not is_dollar(sym):
        v = volume.reindex(idx).astype(float)
        tp = (hi + lo + cl) / 3.0
        vwap = ((tp * v).rolling(24).sum()
                / v.rolling(24).sum().replace(0.0, np.nan))
        f['vwap_dev'] = ((cl - vwap) / atr).to_numpy()
        obv = (np.sign(cl.diff().fillna(0.0)) * v).cumsum()
        d48 = obv - obv.shift(48)
        med = d48.shift(1).rolling(96).median()
        q25 = d48.shift(1).rolling(96).quantile(0.25)
        q75 = d48.shift(1).rolling(96).quantile(0.75)
        iqr = (q75 - q25).replace(0.0, np.nan)
        f['obv_z'] = ((d48 - med) / iqr).to_numpy()
        mf = tp * v
        posmf = mf.where(tp.diff() > 0, 0.0).rolling(14).sum()
        negmf = mf.where(tp.diff() < 0, 0.0).rolling(14).sum()
        f['mfi14'] = (100.0 - 100.0 / (1.0 + posmf
                      / negmf.replace(0.0, np.nan))).to_numpy()
        mfm = (((cl - lo) - (hi - cl))
               / (hi - lo).replace(0.0, np.nan)).fillna(0.0)
        mfv = mfm * v
        f['cmf20'] = (mfv.rolling(20).sum()
                      / v.rolling(20).sum()
                      .replace(0.0, np.nan)).to_numpy()
    else:
        for c in VOL_IND:
            f[c] = np.nan
    return f


# ========================================================== b2cf --
def _ema(s, span):
    return s.ewm(span=span, adjust=False).mean()


def add_b2cf_columns(f, m15, m30):
    """The M15 / H4 confirmation layers of
    build_features_planb2.build_one (cf_m15dev, cf_h4dev).
    m15: Datetime-indexed OHLC frame. m30: frame with a
    'Datetime' column (B4.load_m30 shape)."""
    idx = f.index
    atr = f['atr14']
    if m15 is None or m30 is None:
        f['cf_m15dev'] = np.nan
        f['cf_h4dev'] = np.nan
        return f
    m15c = m15['Close']
    m15_ema = _ema(m15c, 20)
    dev15 = m15c - m15_ema
    starts = m15.index.values
    pos = np.searchsorted(starts, idx.values, side='right') - 1
    ok = pos >= 0
    dev_at = np.full(len(f), np.nan)
    dev_at[ok] = dev15.to_numpy()[pos[ok]]
    f['cf_m15dev'] = dev_at / atr.to_numpy()
    m30i = m30.set_index('Datetime')
    h4 = m30i.resample('4h').agg({'Open': 'first', 'High': 'max',
                                  'Low': 'min',
                                  'Close': 'last'}).dropna()
    h4c = h4['Close']
    h4_ema = _ema(h4c, 20)
    h4dev = h4c - h4_ema
    lim = idx - pd.Timedelta(hours=4)
    hp = np.searchsorted(h4.index.values, lim.values,
                         side='right') - 1
    okh = hp >= 0
    hdev_at = np.full(len(f), np.nan)
    hdev_at[okh] = h4dev.to_numpy()[hp[okh]]
    f['cf_h4dev'] = hdev_at / atr.to_numpy()
    return f


# ============================================================ b3 --
def add_b3_columns(f, m30):
    """build_features_planb3.build_one verbatim for the columns
    the B-4 partner design uses (uo, cf_m30dev, cf2_stack).
    m30: frame with a 'Datetime' column."""
    idx = f.index
    close, high, low = f['Close'], f['High'], f['Low']
    atr = f['atr14']
    prev_close = close.shift(1)
    bp = close - pd.concat([low, prev_close], axis=1).min(axis=1)
    tr = pd.concat([high, prev_close], axis=1).max(axis=1) \
        - pd.concat([low, prev_close], axis=1).min(axis=1)

    def avg(n):
        return bp.rolling(n).sum() / tr.rolling(n).sum() \
            .replace(0.0, np.nan)

    f['uo'] = 100.0 * (4 * avg(7) + 2 * avg(14) + avg(28)) / 7.0
    # Efficiency Ratio(10) -- build_features_planb3.build_one
    # verbatim (added 2026-10-29: the pr/rp transforms read
    # er10; no earlier app design did).
    _change = (close - close.shift(10)).abs()
    _vola = close.diff().abs().rolling(10).sum() \
        .replace(0.0, np.nan)
    f['er10'] = _change / _vola
    # TRIX(15) -- build_features_planb3.build_one verbatim
    # (added 2026-10-28 phase 2: the P-VOTE ML_TRIX leg
    # reads it; no earlier design did).
    _e1 = _ema(close, 15)
    _e2 = _ema(_e1, 15)
    _e3 = _ema(_e2, 15)
    f['trix15'] = 100.0 * _e3.pct_change()
    if m30 is not None:
        m30i = m30.set_index('Datetime')
        m30c = m30i['Close']
        dev30 = m30c - _ema(m30c, 20)
        starts = m30i.index.values
        pos = np.searchsorted(starts, idx.values, side='right') - 1
        ok = pos >= 0
        dev_at = np.full(len(f), np.nan)
        dev_at[ok] = dev30.to_numpy()[pos[ok]]
    else:
        dev_at = np.full(len(f), np.nan)
    f['cf_m30dev'] = dev_at / atr.to_numpy()
    s15 = np.sign(np.where(np.isnan(f['cf_m15dev'].to_numpy()),
                           0.0, f['cf_m15dev'].to_numpy()))
    s30 = np.sign(np.where(np.isnan(dev_at), 0.0, dev_at))
    s4 = np.sign(np.where(np.isnan(f['cf_h4dev'].to_numpy()),
                          0.0, f['cf_h4dev'].to_numpy()))
    f['cf2_stack'] = s15 + s30 + s4
    return f


# ============================================================ b4 --
def add_b4_columns(f):
    """build_features_planb4.build_one verbatim for the columns
    the B-4 partner design uses (coppock, rvi10, rvi_state, stc,
    kelt_p, cf_d1dev, cf3_stack)."""
    close, high, low = f['Close'], f['High'], f['Low']
    opn = f['Open']
    atr = f['atr14']
    roc = (close / close.shift(14) - 1.0) \
        + (close / close.shift(11) - 1.0)
    wts = np.arange(1, 11, dtype=float)

    def _wma(v):
        if np.isnan(v).any():
            return np.nan
        return float((v * wts).sum() / wts.sum())

    f['coppock'] = roc.rolling(10).apply(_wma, raw=True) \
        * close / atr
    co = close - opn
    hl = (high - low).replace(0.0, np.nan)

    def _vig(s):
        return (s + 2.0 * s.shift(1) + 2.0 * s.shift(2)
                + s.shift(3)) / 6.0

    num = _vig(co).rolling(10).sum()
    den = _vig(hl).rolling(10).sum().replace(0.0, np.nan)
    f['rvi10'] = num / den

    def _stoch_b4(s, n):
        mn = s.rolling(n).min()
        mx = s.rolling(n).max()
        return 100.0 * (s - mn) / (mx - mn).replace(0.0, np.nan)

    macd = _ema(close, 23) - _ema(close, 50)
    k1 = _ema(_stoch_b4(macd, 10), 3)
    f['stc'] = _ema(_stoch_b4(k1, 10), 3)
    ema20 = _ema(close, 20)
    f['kelt_p'] = (close - (ema20 - 2.0 * atr)) / (4.0 * atr)
    f['rvi_state'] = np.where(f['rvi10'] > 0, 1.0, -1.0)
    d1c = close.resample('1D').last()
    d1dev = d1c - _ema(d1c, 10)
    starts = d1c.index.values
    floors = f.index.normalize().values
    pos = np.searchsorted(starts, floors, side='left') - 1
    ok = pos >= 0
    dev_at = np.full(len(f), np.nan)
    dev_at[ok] = d1dev.to_numpy()[pos[ok]]
    f['cf_d1dev'] = dev_at / atr.to_numpy()

    def _sgn(col):
        v = f[col].to_numpy(float)
        return np.sign(np.where(np.isnan(v), 0.0, v))

    s_d1 = np.sign(np.where(np.isnan(dev_at), 0.0, dev_at))
    f['cf3_stack'] = _sgn('cf_m15dev') + _sgn('cf_m30dev') \
        + _sgn('cf_h4dev') + s_d1
    # ---- remaining PLANB4 columns (build_features_planb4
    # verbatim; added 2026-10-31 for the Dec C08 candidate,
    # whose MIX3 equations read them -- the B-4 partner
    # design does not, so the original port omitted them.
    # qqe / aroon_d are the b6 block's identical ports.)
    rsi_w = _wilder_rsi_b6(close, 14)
    f['qqe'] = _ema(_ema(rsi_w, 5), 5)
    shi25 = _bars_since_extreme_b6(high, 25, True)
    slo25 = _bars_since_extreme_b6(low, 25, False)
    f['aroon_d'] = (25.0 - shi25) / 25.0 * 100.0 \
        - (25.0 - slo25) / 25.0 * 100.0
    f['alli_d'] = (close.ewm(alpha=1.0 / 5, adjust=False)
                   .mean()
                   - close.ewm(alpha=1.0 / 13, adjust=False)
                   .mean()) / atr
    f['aroon_state'] = np.where(f['aroon_d'] > 0, 1.0, -1.0)
    return f


def add_b5_columns(f):
    """build_features_planb5 verbatim for the one column the
    Plan B-7 design chain needs: atr_r = atr14 / EWM100(TR)."""
    close, high, low = f['Close'], f['High'], f['Low']
    atr = f['atr14']
    tr = pd.concat([high - low, (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs()],
                   axis=1).max(axis=1)
    atr100 = tr.ewm(span=100, adjust=False).mean()
    f['atr_r'] = atr / atr100.replace(0.0, np.nan)
    return f


def _bars_since_extreme_b6(x, n, want_max):
    """build_features_planb5._bars_since_extreme verbatim."""
    from numpy.lib.stride_tricks import sliding_window_view
    v = x.to_numpy(float)
    out = np.full(len(v), np.nan)
    if len(v) < n:
        return pd.Series(out, index=x.index)
    w = sliding_window_view(v, n)
    ok = ~np.isnan(w).any(axis=1)
    idx = np.argmax(w, axis=1) if want_max else np.argmin(w, axis=1)
    res = (n - 1) - idx
    out[n - 1:][ok] = res[ok]
    return pd.Series(out, index=x.index)


def _wilder_rsi_b6(close, n=14):
    """build_features_planb4._wilder_rsi verbatim (local to
    the b6 block; does NOT overwrite the frame's rsi14)."""
    d = close.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    ru = up.ewm(alpha=1.0 / n, adjust=False).mean()
    rd = dn.ewm(alpha=1.0 / n, adjust=False).mean()
    return 100.0 - 100.0 / (1.0 + ru / rd.replace(0.0, np.nan))


def add_b6_columns(f, rcs_z=None):
    """NEW8 Plan B-6 nested columns (build_features_planb6
    verbatim) for the columns the PLANB6SB2 second-best
    designs read, with their Plan B-3 / B-4 / B-5 inputs
    ported verbatim where the app chain does not already
    produce them: vortex_d / chop61 (planb3), qqe / aroon_d
    (planb4), macd_hs / ichi_cd / aroon14_d / vortex21_d /
    chop20 / ker20 / hurst100 / sqz_dur / ulcer14 (planb5;
    atr_r is the b5 block's, identical formula). cf_stack
    is assembled from the b2cf block's cf_m15dev and the
    r4 block's m30_state / h4_state exactly as
    build_features_planb2 assembles it. rcs_z is the
    cross-sectional currency-strength z of planb5's
    add_rcs, prepared by core.new8_candidate.rcs_context
    (None -> NaN)."""
    close, high, low = f['Close'], f['High'], f['Low']
    atr = f['atr14']
    macd_h = f['macd_h']
    if 'atr_r' in f:
        atr_r = f['atr_r']
    else:
        _tr = pd.concat([high - low,
                         (high - close.shift(1)).abs(),
                         (low - close.shift(1)).abs()],
                        axis=1).max(axis=1)
        atr_r = atr / _tr.ewm(span=100, adjust=False).mean() \
            .replace(0.0, np.nan)
    tr = pd.concat([high - low, (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs()],
                   axis=1).max(axis=1)
    # ---- Plan B-5 inputs (build_features_planb5.build_one)
    f['macd_hs'] = (macd_h - macd_h.shift(3)) / atr
    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2.0
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2.0
    senkou_a = ((tenkan + kijun) / 2.0).shift(26)
    senkou_b = ((high.rolling(52).max()
                 + low.rolling(52).min()) / 2.0).shift(26)
    cloud_mid = (senkou_a + senkou_b) / 2.0
    f['ichi_cd'] = (close - cloud_mid) / atr
    shi = _bars_since_extreme_b6(high, 14, True)
    slo = _bars_since_extreme_b6(low, 14, False)
    f['aroon14_d'] = (14.0 - shi) / 14.0 * 100.0 \
        - (14.0 - slo) / 14.0 * 100.0
    vmp = (high - low.shift(1)).abs().rolling(21).sum()
    vmm = (low - high.shift(1)).abs().rolling(21).sum()
    trs = tr.rolling(21).sum().replace(0.0, np.nan)
    f['vortex21_d'] = vmp / trs - vmm / trs
    rng = (high.rolling(20).max()
           - low.rolling(20).min()).replace(0.0, np.nan)
    f['chop20'] = 100.0 * np.log10(
        tr.rolling(20).sum() / rng) / np.log10(20.0)
    vol = close.diff().abs().rolling(20).sum().replace(0.0,
                                                       np.nan)
    f['ker20'] = (close - close.shift(20)).abs() / vol
    r = np.log(close).diff()
    var1 = r.rolling(100).var()
    var10 = r.rolling(10).sum().rolling(100).var()
    h = 0.5 * np.log(var10 / var1.replace(0.0, np.nan)) \
        / np.log(10.0)
    f['hurst100'] = h.clip(0.0, 1.0)
    ma20 = close.rolling(20).mean()
    sd20 = close.rolling(20).std()
    ema20 = _ema(close, 20)
    on = ((ma20 + 2 * sd20) < (ema20 + 1.5 * atr)) \
        & ((ma20 - 2 * sd20) > (ema20 - 1.5 * atr))
    on = on.fillna(False)
    grp = (~on).cumsum()
    dur = on.astype(float).groupby(grp).cumsum()
    f['sqz_dur'] = dur.clip(upper=30)
    mx14 = close.rolling(14).max()
    dd = 100.0 * (close / mx14 - 1.0)
    f['ulcer14'] = np.sqrt((dd ** 2).rolling(14).mean())
    # ---- Plan B-3 inputs (build_features_planb3.build_one)
    prev_close = close.shift(1)
    vm_p = (high - low.shift(1)).abs()
    vm_m = (low - high.shift(1)).abs()
    tr1 = pd.concat([high - low, (high - prev_close).abs(),
                     (low - prev_close).abs()],
                    axis=1).max(axis=1)
    vip = vm_p.rolling(14).sum() / tr1.rolling(14).sum() \
        .replace(0.0, np.nan)
    vim = vm_m.rolling(14).sum() / tr1.rolling(14).sum() \
        .replace(0.0, np.nan)
    f['vortex_d'] = vip - vim
    atr1 = tr1
    hh = high.rolling(14).max()
    ll = low.rolling(14).min()
    rng61 = (hh - ll).replace(0.0, np.nan)
    f['chop61'] = 100.0 * np.log10(
        atr1.rolling(14).sum() / rng61) / np.log10(14.0)
    # ---- Plan B-4 inputs (build_features_planb4.build_one)
    rsi_w = _wilder_rsi_b6(close, 14)
    f['qqe'] = _ema(_ema(rsi_w, 5), 5)
    shi25 = _bars_since_extreme_b6(high, 25, True)
    slo25 = _bars_since_extreme_b6(low, 25, False)
    f['aroon_d'] = (25.0 - shi25) / 25.0 * 100.0 \
        - (25.0 - slo25) / 25.0 * 100.0
    # ---- cf_stack (build_features_planb2) + rcs_z (planb5)
    def _col(name):
        if name in f:
            return f[name]
        return pd.Series(np.nan, index=f.index)
    m15_sign = np.sign(np.where(
        np.isnan(_col('cf_m15dev').to_numpy()), 0.0,
        _col('cf_m15dev').to_numpy()))
    f['cf_stack'] = m15_sign \
        + _col('m30_state').fillna(0.0).to_numpy() \
        + _col('h4_state').fillna(0.0).to_numpy()
    if rcs_z is not None:
        f['rcs_z'] = rcs_z.reindex(f.index)
    else:
        f['rcs_z'] = np.nan
    # ---- Plan B-6 nested columns (build_features_planb6)
    f['nx_im'] = f['ichi_cd'] + f['macd_hs']
    f['nx_rk'] = f['rcs_z'] * f['ker20']
    f['nx_aa'] = (f['aroon14_d'] + f['aroon_d']) / 2.0
    f['nx_vv'] = f['vortex21_d'] - f['vortex_d']
    f['nx_cc'] = f['chop20'] - f['chop61']
    f['nx_ha'] = f['hurst100'] * atr_r
    f['nx_ua'] = f['ulcer14'] / (1.0 + atr_r)
    f['nx_kq'] = (_col('kelt_p') - 0.5) * 2.0 \
        + (f['qqe'] - 50.0) / 50.0
    f['nx_cf'] = f['cf_stack'] + _col('cf2_stack') \
        + _col('cf3_stack')
    f['nx_mf'] = _col('mfi14') / 100.0 + _col('cmf20')
    f['nx_ad'] = _col('adx14') / 50.0 + macd_h
    f['nx_vol'] = _col('vol_z') + atr_r
    f['nx_sq'] = f['sqz_dur'] / 30.0 + f['ker20']
    f['nx_hk'] = _col('hull_dev') + _col('kama_dev')
    return f


def add_b6v_columns(f, sym, m15):
    """build_features_planb6v.build_one verbatim: M15 tick-
    volume ratio volm_r (last M15 bar at or before the H1
    signal bar / rolling 96-bar median M15 Volume, causal
    asof) and volm_z (z of log(volm_r) over trailing 500 H1
    bars). DOLLARIDX: NaN by the programme convention."""
    if is_dollar(sym) or m15 is None or 'Volume' not in m15:
        f['volm_r'] = np.nan
        f['volm_z'] = np.nan
        return f
    m = m15.sort_index()
    vol = m['Volume'].astype(float)
    med = vol.rolling(96).median().replace(0.0, np.nan)
    r = (vol / med).dropna()
    if len(r) == 0:
        # Live-provider M15 volume can be all-zero / all-NaN
        # (Twelve Data FX volume): the ratio series is then
        # undefined everywhere -- NaN columns, exactly as the
        # insufficient-data branch above. (Fix 2026-10-29:
        # without this guard the asof indexing below raised
        # IndexError on live frames and the Mar/Nov/Dec
        # panels showed 'Calculation error: IndexError'.
        # Research frames always carry real M15 volume, so
        # r is never empty there and no replay result
        # changes.)
        f['volm_r'] = np.nan
        f['volm_z'] = np.nan
        return f
    idx = f.index.to_numpy()
    pos = np.searchsorted(r.index.to_numpy(), idx,
                          side='right') - 1
    rv = np.where(pos >= 0,
                  r.to_numpy()[np.maximum(pos, 0)], np.nan)
    rv = np.where(pos >= 0, rv, np.nan)
    f['volm_r'] = rv
    lr = np.log(np.where(rv > 0, rv, np.nan))
    s = pd.Series(lr, index=f.index)
    mu = s.rolling(500).mean()
    sd = s.rolling(500).std().replace(0.0, np.nan)
    f['volm_z'] = ((s - mu) / sd).to_numpy()
    return f


def add_b7_columns(f, sym, ctx7):
    """build_features_planb7.build_one verbatim, given the
    cross-symbol context (ctx7: bm/br basket momentum / RSI
    and dm/dd/dr dollar momentum / deviation / RSI Series
    aligned to f.index, prepared by
    core.new8_candidate.b7_context; None -> all NaN).
    nx_vol / nx_cf are the Plan B-6 composites (build_
    features_planb6 verbatim) from columns already present."""
    if 'nx_vol' not in f:
        f['nx_vol'] = f['vol_z'] + f['atr_r']
    if 'nx_cf' not in f:
        # cf_stack (Plan B block) was never ported to the app
        # chain -- no installed design reads it; nx_cf (and
        # b7_nest2 below) stay NaN unless all three stacks
        # are present. The C02 design does not use them.
        if all(c in f for c in ('cf_stack', 'cf2_stack',
                                'cf3_stack')):
            f['nx_cf'] = f['cf_stack'] + f['cf2_stack'] \
                + f['cf3_stack']
        else:
            f['nx_cf'] = np.nan
    nan = pd.Series(np.nan, index=f.index)
    if ctx7 is None:
        bm = br = dm = dd = dr = nan
    else:
        bm = ctx7['bm'].reindex(f.index)
        br = ctx7['br'].reindex(f.index)
        dm = ctx7['dm'].reindex(f.index)
        dd = ctx7['dd'].reindex(f.index)
        dr = ctx7['dr'].reindex(f.index)
    f['vx_h1m15'] = f['vol_z'] + f['volm_z']
    f['vx_shock'] = f['volm_r'] * f['atr_r']
    f['vx_flow'] = f['cmf20'] + f['obv_z'] / 10.0 \
        + f['volm_z'] / 2.0
    f['vx_nx'] = f['nx_vol'] + f['volm_z']
    f['b7_dxy_mom'] = dm
    f['b7_dxy_dev'] = dd
    f['b7_dxy_rsi'] = dr
    f['b7_corr_basket'] = bm
    f['b7_corr_rsi'] = br
    f['b7_corr_dxy'] = bm - dm
    f['b7_vcorr'] = f['vx_h1m15'] + br
    f['b7_nest2'] = f['nx_cf'] / 3.0 + f['vx_h1m15'] / 2.0 + br
    f['b7_vol_state'] = np.where(
        (f['volm_z'] > 0) & (f['vol_z'] > 0), 1.0,
        np.where((f['volm_z'] < 0) & (f['vol_z'] < 0), -1.0,
                 0.0))
    f['b7_dxy_state'] = np.where(
        (dm > 0) & (dr > 0), 1.0,
        np.where((dm < 0) & (dr < 0), -1.0, 0.0))
    f['b7_corr_state'] = np.where(
        (bm > 0) & (br > 0), 1.0,
        np.where((bm < 0) & (br < 0), -1.0, 0.0))
    f['b7_all_state'] = np.where(
        (f['b7_vol_state'] > 0) & (f['b7_dxy_state'] > 0)
        & (f['b7_corr_state'] > 0), 1.0,
        np.where((f['b7_vol_state'] < 0)
                 & (f['b7_dxy_state'] < 0)
                 & (f['b7_corr_state'] < 0), -1.0, 0.0))
    return f


# ============================================================ b2x --
def _psar_state(high, low, close, step=0.02, maxaf=0.2):
    """build_features_planb2._psar_state verbatim."""
    n = len(close)
    sar = np.zeros(n)
    ep = np.zeros(n)
    af = np.full(n, step)
    up = np.ones(n, dtype=bool)
    sar[0] = low[0]
    ep[0] = high[0]
    for i in range(1, n):
        ps, pe, pa = sar[i - 1], ep[i - 1], af[i - 1]
        if up[i - 1]:
            s = ps + pa * (pe - ps)
            s = min(s, low[i - 1],
                    low[i - 2] if i >= 2 else low[i - 1])
            if low[i] < s:
                up[i] = False
                sar[i] = pe
                ep[i] = low[i]
                af[i] = step
            else:
                up[i] = True
                sar[i] = s
                if high[i] > pe:
                    ep[i] = high[i]
                    af[i] = min(pa + step, maxaf)
                else:
                    ep[i] = pe
                    af[i] = pa
        else:
            s = ps + pa * (pe - ps)
            s = max(s, high[i - 1],
                    high[i - 2] if i >= 2 else high[i - 1])
            if high[i] > s:
                up[i] = True
                sar[i] = pe
                ep[i] = high[i]
                af[i] = step
            else:
                up[i] = False
                sar[i] = s
                if low[i] < pe:
                    ep[i] = low[i]
                    af[i] = min(pa + step, maxaf)
                else:
                    ep[i] = pe
                    af[i] = pa
    return np.where(close > sar, 1.0, -1.0)


def _supertrend_state(high, low, close, atr, mult=3.0):
    """build_features_planb2._supertrend_state verbatim."""
    hl2 = (high + low) / 2.0
    ub = hl2 + mult * atr
    lb = hl2 - mult * atr
    n = len(close)
    fub = np.zeros(n)
    flb = np.zeros(n)
    up = np.ones(n, dtype=bool)
    fub[0] = ub[0]
    flb[0] = lb[0]
    for i in range(1, n):
        fub[i] = ub[i] if (ub[i] < fub[i - 1]
                           or close[i - 1] > fub[i - 1]) \
            else fub[i - 1]
        flb[i] = lb[i] if (lb[i] > flb[i - 1]
                           or close[i - 1] < flb[i - 1]) \
            else flb[i - 1]
        if up[i - 1]:
            up[i] = bool(close[i] >= flb[i])
        else:
            up[i] = bool(close[i] > fub[i])
    return np.where(up, 1.0, -1.0)


def add_b2x_columns(f, sym, vol):
    """build_features_planb2.build_one own-frame columns
    verbatim (the M15/H4 confirmation columns live in the
    b2cf block; cf_stack is not ported -- no design that
    ships reads it). vol: the frame's H1 Volume Series."""
    close, high, low = f['Close'], f['High'], f['Low']
    atr = f['atr14']
    mid = close.rolling(20).mean()
    sd = close.rolling(20).std(ddof=0)
    f['bb_bw'] = (4.0 * sd) / atr
    f['roc24'] = (close - close.shift(24)) / atr
    f['adx_chg'] = f['adx14'] - f['adx14'].shift(6)
    if not is_dollar(sym) and vol is not None:
        v = vol.reindex(f.index)
        vwma = ((close * v).rolling(20).sum()
                / v.rolling(20).sum())
        f['vma_dev'] = (close - vwma) / atr
    else:
        f['vma_dev'] = np.nan
    ha_close = (f['Open'] + high + low + close) / 4.0
    ha_open = np.empty(len(f))
    hc = ha_close.to_numpy()
    ha_open[0] = (f['Open'].iloc[0] + close.iloc[0]) / 2.0
    for i in range(1, len(f)):
        ha_open[i] = (ha_open[i - 1] + hc[i - 1]) / 2.0
    f['ha_body'] = (hc - ha_open) / atr.to_numpy()
    f['psar_state'] = _psar_state(high.to_numpy(),
                                  low.to_numpy(),
                                  close.to_numpy())
    f['st_state'] = _supertrend_state(high.to_numpy(),
                                      low.to_numpy(),
                                      close.to_numpy(),
                                      atr.to_numpy())
    return f


# ============================================================ b8 --
def add_b8_columns(f, sym, ctx):
    """build_features_planb8b pass 2 verbatim. ctx carries
    the quote-currency basket Series 'qm' / 'qr' (prepared
    by core.new8_candidate.cross_context; None -> NaN)."""
    nan = pd.Series(np.nan, index=f.index)
    if ctx is None:
        qb = qr = nan.to_numpy()
    else:
        qb = ctx['qm'].reindex(f.index).to_numpy()
        qr = ctx['qr'].reindex(f.index).to_numpy()
    f['b8_vsh'] = f['vol_r'] * f['atr_r']
    f['b8_vdiv'] = f['vol_z'] - f['volm_z']
    f['b8_vacc'] = f['volm_z'] + f['vol_r']
    f['b8_vflow2'] = f['cmf20'] - f['obv_z'] / 10.0 \
        + f['vol_z'] / 2.0
    f['b8_vdxy'] = f['vx_h1m15'] + f['b7_dxy_mom']
    f['b8_dxy_mom2'] = f['b7_dxy_mom'] + f['b7_dxy_dev']
    f['b8_dxy_rsi_mom'] = f['b7_dxy_rsi'] + f['b7_dxy_mom']
    f['b8_corr_mom_rsi'] = f['b7_corr_basket'] + f['b7_corr_rsi']
    f['b8_corr_spread'] = f['b7_corr_basket'] - f['mom24']
    f['b8_corr_dxy2'] = f['b7_corr_rsi'] - f['b7_dxy_rsi']
    f['b8_own_corr'] = f['mom24'] + f['b7_corr_basket']
    f['b8_rsi_spread'] = (f['rsi14'] - 50.0) / 50.0 \
        - f['b7_corr_rsi']
    f['b8_q_basket'] = qb
    f['b8_q_rsi'] = qr
    f['b8_basket_spread'] = f['b7_corr_basket'] - qb
    f['b8_nest3'] = f['b7_nest2'] / 2.0 + f['b8_vacc'] / 2.0 \
        + f['b7_corr_dxy']
    f['b8_vnest3'] = f['vx_nx'] / 2.0 + f['b8_vsh'] / 2.0 \
        + f['b7_dxy_dev']
    vu = (f['vol_z'] > 0) & (f['vol_r'] > 0)
    vd = (f['vol_z'] < 0) & (f['vol_r'] < 0)
    f['b8_vol_state'] = np.where(vu, 1.0, np.where(vd, -1.0, 0.0))
    xu = (f['b7_dxy_rsi'] > 0) & (f['b7_dxy_mom'] > 0)
    xd = (f['b7_dxy_rsi'] < 0) & (f['b7_dxy_mom'] < 0)
    f['b8_dxy_state2'] = np.where(xu, 1.0,
                                  np.where(xd, -1.0, 0.0))
    cu = (f['b8_corr_spread'] > 0) & (f['b7_corr_rsi'] > 0)
    cd = (f['b8_corr_spread'] < 0) & (f['b7_corr_rsi'] < 0)
    f['b8_corr_state2'] = np.where(cu, 1.0,
                                   np.where(cd, -1.0, 0.0))
    au = (f['b8_vol_state'] > 0) & (f['b8_dxy_state2'] > 0) \
        & (f['b8_corr_state2'] > 0)
    ad = (f['b8_vol_state'] < 0) & (f['b8_dxy_state2'] < 0) \
        & (f['b8_corr_state2'] < 0)
    f['b8_all_state2'] = np.where(au, 1.0, np.where(ad, -1.0, 0.0))
    return f


# ============================================================ b9 --
def add_b9_columns(f):
    """build_features_planb9.build_one verbatim (reads the
    frame's own columns + the b7 / b8 blocks)."""
    o, h, l, c = f['Open'], f['High'], f['Low'], f['Close']
    atr = f['atr14']
    rng = (h - l).replace(0, np.nan)
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2.0
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2.0
    f['b9_tk_spread'] = (tenkan - kijun) / atr
    ema12 = c.ewm(span=12, adjust=False).mean()
    f['b9_ema_slope'] = (ema12 - ema12.shift(6)) / atr
    up = h.diff()
    dn = -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(),
                    (l - c.shift()).abs()], axis=1).max(axis=1)
    str_ = tr.ewm(alpha=1 / 14, adjust=False).mean()
    spdm = pd.Series(pdm, index=f.index).ewm(
        alpha=1 / 14, adjust=False).mean()
    smdm = pd.Series(mdm, index=f.index).ewm(
        alpha=1 / 14, adjust=False).mean()
    f['b9_di_diff'] = (100.0 * spdm / str_
                       - 100.0 * smdm / str_) / 100.0
    f['b9_mom_acc'] = (c.shift(24) - c.shift(6)) / atr
    f['b9_rsi_vel'] = f['rsi14'] - f['rsi14'].shift(5)
    f['b9_stoch_vel'] = f['stoch_k'] - f['stoch_k'].shift(4)
    f['b9_rng_exp'] = (rng.rolling(12).mean()
                       / rng.rolling(48).mean())
    ll6 = l.rolling(6).min()
    hh6 = h.rolling(6).max()
    f['b9_pos6'] = ((c - ll6) / (hh6 - ll6)).fillna(0.5)
    f['b9_atr_pc'] = atr / c * 1000.0
    body = (c - o) / rng
    f['b9_body_dom'] = body.rolling(6).mean()
    wick_up = (h - pd.concat([o, c], axis=1).max(axis=1)) / rng
    wick_dn = (pd.concat([o, c], axis=1).min(axis=1) - l) / rng
    f['b9_wick_rej'] = (wick_up - wick_dn).rolling(6).mean()
    pivot = ((h + l + c) / 3.0).shift(1)
    f['b9_pivot_dev'] = (c - pivot) / atr
    vz = f['vol_z']
    f['b9_vol_trend'] = (vz.ewm(span=6, adjust=False).mean()
                         - vz.ewm(span=24, adjust=False).mean())
    f['b9_svp12'] = (np.sign(c - o) * vz).rolling(12).mean()
    f['b9_pvd'] = vz - f['b9_mom_acc']
    f['b9_dxy_own_rsi'] = f['b7_dxy_rsi'] \
        - (f['rsi14'] - 50.0) / 50.0
    dm = f['b7_dxy_mom']
    f['b9_dxy_trend'] = (dm.ewm(span=6, adjust=False).mean()
                         - dm.ewm(span=24, adjust=False).mean())
    f['b9_q_spread_own'] = f['mom24'] - f['b8_q_basket']
    f['b9_base_q_mom'] = f['b7_corr_basket'] + f['b8_q_basket']
    f['b9_nest_vol'] = (f['b9_vol_trend'] + f['b8_vacc'] / 2.0
                        + f['b9_dxy_trend'])
    ts = pd.Series(0.0, index=f.index)
    ts[(f['b9_tk_spread'] > 0) & (f['b9_ema_slope'] > 0)] = 1.0
    ts[(f['b9_tk_spread'] < 0) & (f['b9_ema_slope'] < 0)] = -1.0
    f['b9_trend_state'] = ts
    ms = pd.Series(0.0, index=f.index)
    ms[(f['b9_rsi_vel'] > 0) & (f['b9_stoch_vel'] > 0)] = 1.0
    ms[(f['b9_rsi_vel'] < 0) & (f['b9_stoch_vel'] < 0)] = -1.0
    f['b9_mom_state'] = ms
    vs = pd.Series(0.0, index=f.index)
    vs[(f['b9_vol_trend'] > 0) & (vz > 0)] = 1.0
    vs[(f['b9_vol_trend'] < 0) & (vz < 0)] = -1.0
    f['b9_vol_state9'] = vs
    al = pd.Series(0.0, index=f.index)
    agree = (ts != 0) & (ts == ms) & (ts == vs)
    al[agree] = ts[agree]
    f['b9_all_state9'] = al
    return f


# =========================================================== b9c --
def _rsi_m15(close, n=14):
    """build_features_planb9c._rsi verbatim."""
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n,
                                  adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


def add_b9c_columns(f, sym, m15):
    """build_features_planb9c.build_one verbatim, with the
    M15 frame passed in (Datetime-indexed OHLCV). Alignment:
    the last M15 bar whose start is < t. m15 None -> NaN."""
    cols = ['b9c_m15_rsi', 'b9c_m15_mom', 'b9c_m15_volz',
            'b9c_m15_volr', 'b9c_m15_range', 'b9c_m15_ema',
            'b9c_vol_mix', 'b9c_m15_body']
    if m15 is None or len(m15) == 0 or 'Volume' not in m15:
        for col in cols:
            f[col] = np.nan
        return f
    m = m15.sort_index()
    c, h, l, o, v = (m['Close'], m['High'], m['Low'],
                     m['Open'], m['Volume'])
    s = {}
    s['rsi'] = _rsi_m15(c)
    s['mom_raw'] = c / c.shift(16) - 1.0
    s['close'] = c
    logv = np.log(v.clip(lower=0) + 1.0)
    s['volz'] = ((logv - logv.rolling(384).mean())
                 / logv.rolling(384).std())
    vs16 = v.rolling(16).sum()
    s['volr'] = vs16 / vs16.rolling(384).median()
    ll = l.rolling(16).min()
    hh = h.rolling(16).max()
    s['range'] = ((c - ll) / (hh - ll)).fillna(0.5)
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema48 = c.ewm(span=48, adjust=False).mean()
    s['ema'] = (ema12 - ema48) / ema48 * 100.0
    rng = (h - l).replace(0, np.nan)
    s['body'] = ((c - o) / rng).rolling(8).mean()
    idx = m.index.values
    pos = np.searchsorted(idx, f.index.values,
                          side='left') - 1
    ok = pos >= 0
    pos_c = np.clip(pos, 0, len(m) - 1)

    def take(series):
        vals = series.to_numpy(dtype=float)[pos_c]
        vals = np.where(ok, vals, np.nan)
        return pd.Series(vals, index=f.index)

    f['b9c_m15_rsi'] = (take(s['rsi']) - 50.0) / 50.0
    mom = take(s['mom_raw'])
    cl = take(s['close'])
    f['b9c_m15_mom'] = mom * cl / f['atr14']
    f['b9c_m15_volz'] = take(s['volz'])
    f['b9c_m15_volr'] = take(s['volr'])
    f['b9c_m15_range'] = take(s['range'])
    f['b9c_m15_ema'] = take(s['ema'])
    f['b9c_m15_body'] = take(s['body'])
    f['b9c_vol_mix'] = f['volm_z'] + 2.0 * f['b9c_m15_volz']
    return f


# ============================================================ pv --
PV_POOLS = {
    'V01': (['VL_H1FLOW', 'VL_M15VOL', 'TL_EMA', 'ML_RSI',
             'BL_CORR', 'DL_MOM', 'PL_VWAP'], {}),
    'V02': (['VL_FLOWR', 'VL_OBVM15', 'TL_H4', 'ML_MACD',
             'AL_ATR', 'BL_Q', 'SL_US'], {}),
    'V03': (['VL_MFI', 'VL_ACC', 'TL_D1', 'ML_STOCH',
             'BL_CRSI', 'PL_HA', 'TL_MOM'],
            {'VL_MFI': 1.5, 'VL_ACC': 1.5}),
    'V04': (['VL_H1FLOW', 'VL_ACC', 'ML_B9RSI', 'TL_B9EMA',
             'AL_RNG', 'DL_RSI', 'PL_BODY'], {}),
    'V05': (['VL_OBVM15', 'VL_M15VOL', 'TL_KH', 'ML_FISH',
             'BL_SPRD', 'BL_BQ', 'PL_DON'],
            {'BL_SPRD': 1.5, 'BL_BQ': 1.5}),
    'V06': (['VL_FLOWR', 'VL_MFI', 'TL_M30', 'ML_UO',
             'AL_EXP', 'PL_DON', 'DL_TRND'], {}),
    'V07': (['VL_H1FLOW', 'VL_M15VOL', 'ML_TRIX', 'TL_EMA',
             'BL_CORR', 'PL_POS6', 'SL_EU'],
            {'VL_H1FLOW': 1.5, 'VL_M15VOL': 1.5}),
    'V08': (['VL_ACC', 'VL_OBVM15', 'TL_H4', 'ML_COPP',
             'BL_Q', 'PL_WICK', 'ML_RSI'], {}),
    'V09': (['VL_MFI', 'VL_FLOWR', 'TL_D1', 'ML_MACD',
             'AL_ATR', 'DL_MOM', 'PL_VWAP'], {}),
    'V10': (['VL_M15VOL', 'VL_H1FLOW', 'TL_B9EMA', 'ML_STOCH',
             'BL_BQ', 'SL_US', 'PL_HA'], {}),
    'V11': (['VL_ACC', 'VL_FLOWR', 'TL_KH', 'ML_B9RSI',
             'BL_CRSI', 'DL_RSI', 'AL_RNG', 'PL_BODY'], {}),
    'V12': (['VL_OBVM15', 'VL_MFI', 'TL_MOM', 'ML_FISH',
             'BL_SPRD', 'PL_DON', 'ML_UO'], {}),
    'V13': (['VL_H1FLOW', 'VL_M15VOL', 'TL_M30', 'ML_WT',
             'AL_EXP', 'DL_TRND', 'PL_POS6'], {}),
    'V14': (['VL_M15VOL', 'VL_ACC', 'TL_EMA', 'ML_RSI',
             'BL_Q', 'SL_US'], {}),
    'V15': (['VL_FLOWR', 'VL_OBVM15', 'TL_H4', 'ML_TRIX',
             'BL_BQ', 'PL_WICK'], {}),
}


def _pv_usd_sign(sym):
    if sym.startswith('USD'):
        return 1.0
    if sym.endswith('USD'):
        return -1.0
    return 0.0


def _pv_leg_votes(rows, leg, sym):
    """parallel_vote/pv_common.leg_votes verbatim."""
    def _c(col):
        return rows[col].to_numpy(float)
    if leg == 'VL_H1FLOW':
        v, f = _c('vol_z'), _c('cmf20')
        return (v > 0) & (f > 0), (v > 0) & (f < 0)
    if leg == 'VL_M15VOL':
        v, m = _c('volm_z'), _c('b9c_m15_mom')
        return (v > 0) & (m > 0), (v > 0) & (m < 0)
    if leg == 'VL_FLOWR':
        v, r = _c('vx_flow'), _c('vol_r')
        return (v > 0) & (r > 1), (v < 0) & (r > 1)
    if leg == 'VL_OBVM15':
        v, r = _c('obv_z'), _c('volm_r')
        return (v > 0) & (r > 1), (v < 0) & (r > 1)
    if leg == 'VL_MFI':
        v, m = _c('b9_vol_trend'), _c('mfi14')
        return (v > 0) & (m > 50), (v < 0) & (m < 50)
    if leg == 'VL_ACC':
        v, m = _c('b8_vacc'), _c('b9c_m15_volz')
        return (v > 0) & (m > 0), (v < 0) & (m < 0)
    if leg == 'TL_EMA':
        v = _c('ema_dev')
        return v > 0, v < 0
    if leg == 'TL_H4':
        v = _c('h4_mom')
        return v > 0, v < 0
    if leg == 'TL_D1':
        v = _c('d1_mom')
        return v > 0, v < 0
    if leg == 'TL_B9EMA':
        v = _c('b9_ema_slope')
        return v > 0, v < 0
    if leg == 'TL_KH':
        a, b = _c('kama_dev'), _c('hull_dev')
        return (a > 0) & (b > 0), (a < 0) & (b < 0)
    if leg == 'TL_MOM':
        v = _c('mom24')
        return v > 0, v < 0
    if leg == 'TL_M30':
        v = _c('m30_mom')
        return v > 0, v < 0
    if leg == 'ML_RSI':
        v = _c('rsi14')
        return v > 52, v < 48
    if leg == 'ML_MACD':
        v = _c('macd_h')
        return v > 0, v < 0
    if leg == 'ML_STOCH':
        v = _c('stoch_k')
        return v > 55, v < 45
    if leg == 'ML_B9RSI':
        v = _c('b9_rsi_vel')
        return v > 0, v < 0
    if leg == 'ML_FISH':
        v = _c('fisher10')
        return v > 0, v < 0
    if leg == 'ML_WT':
        v = _c('wt_diff')
        return v > 0, v < 0
    if leg == 'ML_UO':
        v = _c('uo')
        return v > 52, v < 48
    if leg == 'ML_TRIX':
        v = _c('trix15')
        return v > 0, v < 0
    if leg == 'ML_COPP':
        v = _c('coppock')
        return v > 0, v < 0
    if leg == 'AL_ATR':
        a, m = _c('atr_rank'), _c('mom24')
        return (a > 0.6) & (m > 0), (a > 0.6) & (m < 0)
    if leg == 'AL_RNG':
        a, m = _c('atr_ratio'), _c('roc24')
        return (a > 1.05) & (m > 0), (a > 1.05) & (m < 0)
    if leg == 'AL_EXP':
        a, m = _c('b9_atr_pc'), _c('h4_mom')
        return (a > 0) & (m > 0), (a > 0) & (m < 0)
    if leg == 'PL_HA':
        v = _c('ha_body')
        return v > 0, v < 0
    if leg == 'PL_BODY':
        v = _c('b9_body_dom')
        return v > 0, v < 0
    if leg == 'PL_DON':
        v = _c('don_p')
        return v > 0.7, v < 0.3
    if leg == 'PL_VWAP':
        v = _c('vwap_dev')
        return v > 0, v < 0
    if leg == 'PL_POS6':
        v = _c('b9_pos6')
        return v > 0, v < 0
    if leg == 'PL_WICK':
        v = _c('b9_wick_rej')
        return v > 0, v < 0
    if leg == 'BL_CORR':
        v = _c('b7_corr_basket')
        return v > 0, v < 0
    if leg == 'BL_Q':
        v = _c('b8_q_basket')
        return v > 0, v < 0
    if leg == 'BL_CRSI':
        v = _c('b7_corr_rsi')
        return v > 0, v < 0
    if leg == 'BL_BQ':
        v = _c('b9_base_q_mom')
        return v > 0, v < 0
    if leg == 'BL_SPRD':
        v = _c('b8_basket_spread')
        return v > 0, v < 0
    if leg in ('DL_MOM', 'DL_RSI', 'DL_TRND'):
        col = {'DL_MOM': 'b7_dxy_mom', 'DL_RSI': 'b7_dxy_rsi',
               'DL_TRND': 'b9_dxy_trend'}[leg]
        x = _pv_usd_sign(sym) * _c(col)
        return x > 0, x < 0
    if leg == 'SL_US':
        h = np.asarray(rows.index.hour)
        m = _c('mom24')
        sess = (h >= 13) & (h <= 16)
        return sess & (m > 0), sess & (m < 0)
    if leg == 'SL_EU':
        h = np.asarray(rows.index.hour)
        m = _c('h4_mom')
        sess = (h >= 8) & (h <= 12)
        return sess & (m > 0), sess & (m < 0)
    raise ValueError(leg)


def _pv_pool_share(rows, pool_id, sym, weights=None):
    """pv_common.pool_share verbatim."""
    legs, w0 = PV_POOLS[pool_id]
    if weights is None:
        w = {leg: float(w0.get(leg, 1.0)) for leg in legs}
    else:
        w = {leg: float(weights.get(leg, 1.0)) for leg in legs}
    tot = sum(w[l] for l in legs)
    sb = np.zeros(len(rows))
    ss = np.zeros(len(rows))
    for leg in legs:
        if w[leg] <= 0:
            continue
        up, dn = _pv_leg_votes(rows, leg, sym)
        sb += w[leg] * up
        ss += w[leg] * dn
    return sb / tot, ss / tot


def add_pv_columns(f, sym, variants):
    """pv_common.add_pv_columns verbatim. variants:
    {pool_key: (pool_id, weights_or_None)}."""
    for key, (pid, weights) in variants.items():
        sb, ss = _pv_pool_share(f, pid, sym, weights)
        f[f'pv_{key}_B'] = sb
        f[f'pv_{key}_S'] = ss
    return f


# =========================================================== pbc --
PB_FX28 = ['AUDCAD', 'AUDCHF', 'AUDJPY', 'AUDNZD', 'AUDUSD',
           'CADCHF', 'CADJPY', 'CHFJPY', 'EURAUD', 'EURCAD',
           'EURCHF', 'EURGBP', 'EURJPY', 'EURNZD', 'EURUSD',
           'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPJPY', 'GBPNZD',
           'GBPUSD', 'NZDCAD', 'NZDCHF', 'NZDJPY', 'NZDUSD',
           'USDCAD', 'USDCHF', 'USDJPY']


def _pbc_m15_cols(m):
    """build_features_pbranch.m15_cols verbatim (m: M15 frame
    with o/h/l/c/v columns renamed by the caller)."""
    c, h, l, o, v = m['c'], m['h'], m['l'], m['o'], m['v']
    r = np.log(c).diff()
    out = {}
    r4 = np.log(c).diff(4)
    out['pbc_m15_zret'] = (r4 - r4.rolling(96).mean()) \
        / r4.rolling(96).std()
    out['pbc_m15_skew'] = r.rolling(64).skew()
    ll = l.rolling(32).min()
    hh = h.rolling(32).max()
    out['pbc_m15_chan'] = ((c - ll) / (hh - ll)).fillna(0.5)
    typ = (h + l + c) / 3.0
    vwap = (typ * v).rolling(64).sum() / v.rolling(64).sum()
    atr_m = (h - l).rolling(14).mean()
    out['pbc_m15_vwapdev'] = (c - vwap) / atr_m
    rng = (h - l).replace(0, np.nan)
    out['pbc_m15_body'] = ((c - o) / rng).rolling(8).mean()
    slot = (m.index.hour * 60 + m.index.minute).to_numpy()
    vv = v.to_numpy(float)
    med = np.full(len(vv), np.nan)
    std = np.full(len(vv), np.nan)
    for sl in np.unique(slot):
        pos = np.where(slot == sl)[0]
        sv = pd.Series(vv[pos])
        med[pos] = sv.rolling(80, min_periods=10).median() \
            .to_numpy()
        std[pos] = sv.rolling(80, min_periods=10).std() \
            .to_numpy()
    out['pbc_m15_volsess'] = pd.Series((vv - med) / std,
                                       index=m.index)
    vs16 = v.rolling(16).sum()
    out['pbc_m15_volr'] = vs16 / vs16.rolling(384).median()
    logv = np.log(v.clip(lower=0) + 1.0)
    out['_m15_volz'] = (logv - logv.rolling(384).mean()) \
        / logv.rolling(384).std()
    return out


def add_pbc_columns(f, sym, m15, vol, pbctx):
    """build_features_pbranch per-symbol block verbatim.
    pbctx: {'xs_rank': DataFrame|None, 'dxy_mom': Series|None}
    prepared by core.new8_candidate.cross_context."""
    c, h, l, o = f['Close'], f['High'], f['Low'], f['Open']
    atr = f['atr14']
    r = np.log(c).diff()
    f['pb_zret48'] = (r - r.rolling(48).mean()) \
        / r.rolling(48).std()
    f['pb_vr12_48'] = r.rolling(12).std() / r.rolling(48).std()
    f['pb_ac48'] = (r * r.shift(1)).rolling(48).mean() \
        / r.rolling(48).var()
    f['pb_skew48'] = r.rolling(48).skew()
    vv_s = vol.reindex(f.index) if vol is not None else None
    typ = (h + l + c) / 3.0
    vwap = (typ * vv_s).rolling(24).sum() \
        / vv_s.rolling(24).sum() if vv_s is not None else np.nan
    f['pb_vwap_dev'] = (c - vwap) / atr
    ll = l.rolling(34).min()
    hh = h.rolling(34).max()
    f['pb_don34_p'] = ((c - ll) / (hh - ll)).fillna(0.5)
    ema20 = c.ewm(span=20, adjust=False).mean()
    f['pb_kelt_p'] = (c - ema20) / (2.0 * atr)
    rng = (h - l).replace(0, np.nan)
    f['pb_body4'] = ((c - o) / rng).rolling(4).mean()
    wick_up = (h - pd.concat([o, c], axis=1).max(axis=1)) / rng
    wick_dn = (pd.concat([o, c], axis=1).min(axis=1) - l) / rng
    f['pb_wick4'] = (wick_up - wick_dn).rolling(4).mean()
    f['pb_rng6_24'] = rng.rolling(6).mean() \
        / rng.rolling(24).mean()
    xs = None if pbctx is None else pbctx.get('xs_rank')
    if sym in PB_FX28 and xs is not None and sym in xs:
        f['pb_xs_rank'] = xs[sym].reindex(f.index)
    else:
        f['pb_xs_rank'] = np.nan
    dm = None if pbctx is None else pbctx.get('dxy_mom')
    if dm is not None:
        f['pb_dxy_dev'] = dm.reindex(f.index).ffill() \
            - f['mom24']
    else:
        f['pb_dxy_dev'] = np.nan
    vv = vv_s.to_numpy(float) if vv_s is not None \
        else np.full(len(f), np.nan)
    hrs = f.index.hour.to_numpy()
    med = np.full(len(vv), np.nan)
    std = np.full(len(vv), np.nan)
    for hh in range(24):
        pos = np.where(hrs == hh)[0]
        if len(pos) == 0:
            continue
        sv = pd.Series(vv[pos])
        med[pos] = sv.rolling(60, min_periods=10).median() \
            .to_numpy()
        std[pos] = sv.rolling(60, min_periods=10).std() \
            .to_numpy()
    f['pb_sess_vol'] = (vv - med) / std
    vz = f['vol_z']
    f['pb_svol18'] = (np.sign(c - o) * vz).rolling(18).mean()
    f['pb_vol_tr'] = (vz.ewm(span=3, adjust=False).mean()
                      - vz.ewm(span=12, adjust=False).mean())
    pbc_cols = ['pbc_m15_zret', 'pbc_m15_skew', 'pbc_m15_chan',
                'pbc_m15_vwapdev', 'pbc_m15_body',
                'pbc_m15_volsess', 'pbc_m15_volr']
    if m15 is None or len(m15) == 0 or 'Volume' not in m15:
        for col in pbc_cols + ['pbc_vol_mix']:
            f[col] = np.nan
        return f
    m = m15.sort_index().rename(columns={
        'Open': 'o', 'High': 'h', 'Low': 'l', 'Close': 'c',
        'Volume': 'v'})
    mc = _pbc_m15_cols(m)
    pos = m.index.get_indexer(f.index, method='pad')
    for col in pbc_cols:
        vals = mc[col].to_numpy(float)
        f[col] = np.where(pos >= 0,
                          vals[np.maximum(pos, 0)], np.nan)
    vz15 = mc['_m15_volz'].to_numpy(float)
    m15z = np.where(pos >= 0, vz15[np.maximum(pos, 0)], np.nan)
    f['pbc_vol_mix'] = f['pb_sess_vol'] + 2.0 * m15z
    return f


# ======================================================== builder --
def frame_to_research(h1):
    """Normalise an app H1 frame (Datetime index, OHLC[V]) to
    the research shape (Datetime column, sorted, deduped
    keep-last). Returns (fr, volume Series or None)."""
    fr = h1.copy()
    if 'Datetime' not in fr.columns:
        fr = fr.reset_index().rename(
            columns={fr.index.name or 'index': 'Datetime'})
    fr['Datetime'] = pd.to_datetime(fr['Datetime'])
    if fr['Datetime'].dt.tz is not None:
        fr['Datetime'] = fr['Datetime'].dt.tz_convert('UTC') \
            .dt.tz_localize(None)
    fr = fr.sort_values('Datetime') \
        .drop_duplicates('Datetime', keep='last') \
        .reset_index(drop=True)
    vol = None
    if 'Volume' in fr.columns:
        vol = fr.set_index('Datetime')['Volume']
    keep = ['Datetime', 'Open', 'High', 'Low', 'Close'] \
        + (['Volume'] if 'Volume' in fr.columns else [])
    return fr[keep], vol


def m30_from_m15(m15):
    """Resample an M15 frame (Datetime index) to the research
    M30 shape (Datetime column). The era harness proves this
    equals fx_data.db ohlc_m30 exactly (the DB table was itself
    resampled from ohlc_m15)."""
    r = m15.resample('30min').agg(
        {'Open': 'first', 'High': 'max', 'Low': 'min',
         'Close': 'last',
         **({'Volume': 'sum'} if 'Volume' in m15.columns
            else {})}).dropna(subset=['Open'])
    # The resample inherits the M15 frame's index name: the
    # research frames call it 'Datetime', but the live panel
    # path (check_candle_runtime.normalize_ohlc) names it
    # after the source time column ('open_time', 'time', ...).
    # Name the output column after the actual index name --
    # the same pattern frame_to_research uses -- so the M30
    # frame always carries the 'Datetime' column the feature
    # builders read. (2026-10-27 live KeyError fix; for
    # 'Datetime'-named input the output is unchanged.)
    return r.reset_index().rename(
        columns={r.index.name or 'index': 'Datetime'})


def add_pr_columns(f):
    """P-REGIME (B-10 revival) regime-lane columns -- port
    of parallel_regime/build_pr_feats.py build_one,
    verbatim transforms of columns already present (the
    planb9c superset blocks). Added 2026-10-29 for the
    December Track A / Plan C installs (designs dec_rg /
    dec_rgc)."""
    sign = np.sign
    f['pr_vol_rank'] = f['atr_rank']
    f['pr_trend_eff'] = f['er10']
    f['pr_chop'] = (f['chop61'] - 50.0) / 50.0
    f['pr_dxy_trend'] = f['b9_dxy_trend']
    f['pr_dxy_mom'] = f['b7_dxy_mom']
    f['pr_m15h1_mom'] = f['b9c_m15_mom'] * sign(f['mom24'])
    f['pr_m15_vol'] = f['b9c_m15_volz']
    f['pr_vol_trend'] = f['b9_vol_trend']
    f['pr_basket'] = f['b7_corr_basket']
    f['pr_basket_rsi'] = f['b7_corr_rsi']
    f['pr_q_basket'] = f['b8_q_basket']
    f['pr_rng_exp'] = f['b9_rng_exp']
    f['pr_atr_pc'] = f['b9_atr_pc']
    f['pr_vol_basket'] = f['b9_svp12'] + f['b7_corr_rsi']
    f['pr_vol_dxy'] = f['b9_vol_trend'] + f['b9_dxy_trend']
    f['pr_mom_acc'] = f['b9_mom_acc']
    f['pr_rsi_vel'] = f['b9_rsi_vel']
    f['pr_body'] = f['b9_body_dom']
    f['pr_wick'] = f['b9_wick_rej']
    f['pr_nest_reg'] = f['b9_nest_vol'] + f['er10']
    # --- regime gates (binary 0/1, direction-agnostic) ---
    trend = f['er10'] > 0.25
    hivol = f['atr_rank'] > 0.60
    f['pr_g_thv'] = (trend & hivol).astype(float)
    f['pr_g_tlv'] = (trend & ~hivol).astype(float)
    f['pr_g_rhv'] = ((~trend) & (f['chop61'] > 50.0)
                     & hivol).astype(float)
    f['pr_g_rlv'] = ((~trend) & ~hivol).astype(float)
    f['pr_g_dxy'] = ((f['b7_dxy_state'] != 0)
                     & (f['b9_dxy_own_rsi'].abs() > 0.5)
                     ).astype(float)
    hour = f.index.hour
    f['pr_g_ses'] = (np.isin(hour, [13, 14, 15])
                     & (f['atr_rank'] > 0.50)
                     & (f['vol_z'] > 0)).astype(float)
    f['pr_g_agr'] = ((sign(f['b9c_m15_mom']) == sign(f['mom24']))
                     & (f['mom24'] != 0)
                     & (f['b9c_m15_mom'] != 0)).astype(float)
    return f


def add_rp_columns(f):
    """P-REPLACE lane columns -- port of
    parallel_replace/build_preplace_feats.py build_one,
    verbatim transforms of columns already present (the
    planb9c superset blocks + b2cf). Added 2026-10-29
    for the March / November P-REPLACE installs
    (designs mar_rp / nov_rp)."""
    sign = np.sign
    f['rp_vol_spread'] = f['b9c_m15_volz'] - f['b9_vol_trend']
    f['rp_vol_ratio'] = f['b9c_vol_mix'] - f['vx_flow']
    f['rp_mom_vol'] = f['b9_mom_acc'] + f['b9c_m15_mom']
    f['rp_rsi_dxy'] = (f['rsi14'] - 50.0) / 50.0 - f['b7_dxy_rsi']
    f['rp_basket_mom'] = f['b7_corr_basket'] + f['b8_corr_mom_rsi']
    f['rp_rng_vol'] = f['b9_rng_exp'] + f['b9c_m15_range']
    f['rp_body_vol'] = f['b9_body_dom'] + f['b9c_m15_body']
    f['rp_wick_vol'] = f['b9_wick_rej'] - f['b9c_m15_volr']
    f['rp_dxy_div'] = f['b9_dxy_trend'] - f['b7_corr_dxy']
    f['rp_q_mom'] = f['b9_base_q_mom'] + f['b8_q_rsi']
    f['rp_nest_mom'] = f['b9_nest_vol'] + f['b9_mom_acc']
    f['rp_m15_dev'] = f['cf_m15dev'] + f['b9c_m15_ema']
    f['rp_h4_m15'] = f['cf_h4dev'] - f['cf_m15dev']
    f['rp_stoch_dxy'] = f['b9_stoch_vel'] + f['b8_dxy_rsi_mom']
    f['rp_vol_dxy2'] = f['b8_vdxy'] + f['vx_shock']
    f['rp_corr_spread'] = f['b8_corr_spread'] - f['b9_q_spread_own']
    f['rp_atr_vol'] = f['atr_rank'] + f['vol_z']
    f['rp_er_vol'] = f['er10'] + f['b9_vol_trend']
    f['rp_pivot_vol'] = f['b9_pivot_dev'] + f['b9_svp12']
    f['rp_di_vol'] = f['b9_di_diff'] + f['adx_chg']
    # --- rp gates (binary 0/1, direction-agnostic) ---
    f['rp_g_vexp'] = ((f['atr_rank'] > 0.50)
                      & (f['vol_z'] > 0)).astype(float)
    f['rp_g_m15t'] = ((sign(f['b9c_m15_mom']) == sign(f['mom24']))
                      & (f['mom24'] != 0) & (f['b9c_m15_mom'] != 0)
                      & (f['b9c_m15_volz'] > 0)).astype(float)
    f['rp_g_dxdiv'] = (sign(f['b9_dxy_trend'])
                       != sign(f['mom24'])).astype(float)
    f['rp_g_cbrk'] = (f['b8_corr_spread'] > 0).astype(float)
    hour = f.index.hour
    f['rp_g_sesv'] = (np.isin(hour, [13, 14, 15])
                      & (f['b9c_m15_volr'] > 0)).astype(float)
    f['rp_g_wick'] = ((f['b9_wick_rej'] > 0)
                      & (f['atr_rank'] <= 0.60)).astype(float)
    f['rp_g_acc'] = ((f['b9_mom_acc'] > 0)
                     & (f['er10'] > 0.25)).astype(float)
    return f


# ============================================================ b12 --
def add_b12_columns(f):
    """build_features_planb12.build_one verbatim (PLAN B-12
    Track A columns; transforms of columns already present --
    the planb9c superset blocks). Added 2026-10-30 for the
    December D19 partner install (design dec_b12c)."""
    hr = pd.Series(f.index.hour, index=f.index).astype(float)
    dow = pd.Series(f.index.dayofweek, index=f.index).astype(float)
    us = ((hr >= 13) & (hr < 21)).astype(float)
    eu = ((hr >= 8) & (hr < 13)).astype(float)
    f['b12_h4_trend'] = f['h4_mom'] - f['d1_mom']
    f['b12_h4_dev'] = f['cf_h4dev'] - f['cf_m15dev']
    f['b12_d1_trend'] = f['d1_mom'] + 0.5 * f['h4_mom']
    f['b12_d1_pos'] = f['don_p'] - f['don48_p']
    f['b12_sess_us_mom'] = f['mom24'] * (us * 1.0 + (1 - us) * -0.5)
    f['b12_sess_eu_vol'] = f['vol_z'] * (eu * 1.0 + (1 - eu) * -0.5) \
        + f['b9c_m15_volz'] * eu
    f['b12_dow_mom'] = f['mom24'] * (dow - 2.0) / 2.0
    f['b12_dow_vol'] = f['vol_z'] * (dow - 2.0) / 2.0
    f['b12_m15_seq_mom'] = f['b9c_m15_mom'] + f['b9c_m15_ema']
    f['b12_m15_seq_body'] = f['b9c_m15_body'] * (f['b9c_m15_range'] - 0.5) * 2.0
    f['b12_m15_seq_vol'] = f['b9c_m15_volz'] + f['volm_z']
    f['b12_sprd_vol'] = f['bb_bw'] - f['atr_rank'] / 100.0
    f['b12_sprd_shock'] = f['vx_shock'] + f['bb_bw']
    f['b12_vol_sess'] = f['vol_z'] + f['b9c_m15_volz'] * (us + eu)
    f['b12_vol_h4'] = f['b9_vol_trend'] + f['b9c_vol_mix']
    f['b12_corr_h4'] = f['b8_corr_mom_rsi'] + f['h4_mom']
    f['b12_corr_d1'] = f['b7_corr_basket'] + f['d1_mom']
    f['b12_dxy_ctx'] = f['b9_dxy_trend'] + f['b7_dxy_mom']
    f['b12_corr_sess'] = f['b9_q_spread_own'] + f['b12_sess_us_mom']
    f['b12_nest_ctx'] = f['b12_h4_trend'] + f['b12_d1_trend'] \
        + f['b12_m15_seq_mom']

    def state(a, b):
        s = pd.Series(0.0, index=f.index)
        s[(a > 0) & (b > 0)] = 1.0
        s[(a < 0) & (b < 0)] = -1.0
        return s
    f['b12_ctx_state'] = state(f['b12_h4_trend'], f['b12_d1_trend'])
    f['b12_sess_state'] = state(f['b12_sess_us_mom'], f['b12_vol_sess'])
    f['b12_m15_state'] = state(f['b12_m15_seq_mom'],
                               f['b12_m15_seq_body'])
    al = pd.Series(0.0, index=f.index)
    agree = (f['b12_ctx_state'] != 0) \
        & (f['b12_ctx_state'] == f['b12_sess_state']) \
        & (f['b12_ctx_state'] == f['b12_m15_state'])
    al[agree] = f['b12_ctx_state'][agree]
    f['b12_all_state12'] = al
    return f


def add_b12c_columns(f):
    """build_features_planb12c.build_one verbatim (PLAN B-12
    Plan C M15-heavy columns)."""
    hr = pd.Series(f.index.hour, index=f.index).astype(float)
    us = ((hr >= 13) & (hr < 21)).astype(float)
    f['b12c_m15_seq3'] = f['b9c_m15_mom'] - f['b9c_m15_ema']
    f['b12c_m15_volseq'] = f['b9c_m15_volr'] + 2.0 * f['b9c_m15_volz']
    f['b12c_m15_rngseq'] = (f['b9c_m15_range'] - 0.5) * 2.0 \
        + f['b9c_m15_ema']
    f['b12c_m15_bodseq'] = f['b9c_m15_body'] + f['b12_m15_seq_body']
    f['b12c_m15_h4align'] = f['b9c_m15_ema'] + f['b12_h4_trend']
    f['b12c_vol_mix2'] = f['b9c_vol_mix'] + 2.0 * f['b9c_m15_volz']
    f['b12c_m15_sessvol'] = f['b9c_m15_volz'] * (1.0 + us) + f['volm_z']
    f['b12c_m15_sprd'] = f['b12_sprd_vol'] + f['b9c_m15_volr']
    return f


def pc03_m15_features(m15):
    """Wave-3b feats_m15 (run_pc3_wave3b.py) PC03 subset,
    verbatim formulas on an M15 OHLCV frame (Datetime index):
    mom4 / mom96 in % and vol_z of log1p volume (rolling 672).
    The value on M15 bar t uses bars up to and including t;
    the PC03 signal value for a check is read at
    sig_t = check - 90 min with a pad (last bar <= sig_t)
    lookup -- the research convention."""
    c = m15['Close'].astype(float)
    v = m15['Volume'].astype(float)
    out = pd.DataFrame(index=m15.index)
    out['pc03_mom4'] = (c / c.shift(4) - 1) * 100
    out['pc03_mom96'] = (c / c.shift(96) - 1) * 100
    lv = np.log1p(v.where(v > 0))
    out['pc03_vol_z'] = (lv - lv.rolling(672, min_periods=100).mean()) \
        / lv.rolling(672, min_periods=100).std()
    return out


def pc03_keep(pc03_frame, check, direction):
    """PC03 mask for one pick: aligned (direction-signed)
    M15 mom4 > -0.15 & aligned mom96 > -0.8 & vol_z > -1.0
    at sig_t = check - 90 min. NaN -> vetoed (the research
    mask fills NaN with False)."""
    sig_t = pd.Timestamp(check) - pd.Timedelta(minutes=90)
    i = pc03_frame.index.get_indexer([sig_t], method='pad')[0]
    if i < 0:
        return False
    r = pc03_frame.iloc[i]
    s = 1.0 if direction == 'BUY' else -1.0
    vz = r['pc03_vol_z']
    vz = 0.0 if pd.isna(vz) else float(vz)
    return bool(s * float(r['pc03_mom4']) > -0.15
                and s * float(r['pc03_mom96']) > -0.8
                and vz > -1.0)


def pc14_m15_features(m15):
    """Mar Plan C feats_m15 (run_mar_planC_s1.py) PC14 subset,
    verbatim formulas on an M15 OHLCV frame (Datetime index):
    bb = (close - SMA20) / (2 * SD20) (sample SD), rpos =
    (close - LL20) / (HH20 - LL20), mom16 in %. The value on
    M15 bar t uses bars up to and including t; the PC14
    signal value for a check is read at sig_t = check -
    90 min with a pad (last bar <= sig_t) lookup -- the
    research convention."""
    c = m15['Close'].astype(float)
    h = m15['High'].astype(float)
    l = m15['Low'].astype(float)
    out = pd.DataFrame(index=m15.index)
    sma = c.rolling(20).mean()
    sd = c.rolling(20).std()
    out['pc14_bb'] = (c - sma) / (2 * sd.replace(0, np.nan))
    hh = h.rolling(20).max()
    ll = l.rolling(20).min()
    out['pc14_rpos'] = (c - ll) / (hh - ll).replace(0, np.nan)
    out['pc14_mom16'] = (c / c.shift(16) - 1) * 100
    return out


def pc14_keep(pc14_frame, check, direction):
    """PC14_bb_rpos mask for one pick (Mar Plan C / R2 M18):
    aligned (direction-signed) M15 BB z <= 1.0 & aligned
    range position (signed (rpos - 0.5) * 2) <= 0.85 &
    aligned mom16 > -0.35 at sig_t = check - 90 min.
    NaN -> vetoed (the research mask comparisons are False
    on NaN)."""
    sig_t = pd.Timestamp(check) - pd.Timedelta(minutes=90)
    i = pc14_frame.index.get_indexer([sig_t], method='pad')[0]
    if i < 0:
        return False
    r = pc14_frame.iloc[i]
    s = 1.0 if direction == 'BUY' else -1.0
    return bool(s * float(r['pc14_bb']) <= 1.0
                and s * (float(r['pc14_rpos']) - 0.5) * 2 <= 0.85
                and s * float(r['pc14_mom16']) > -0.35)




def build_symbol_features(sym, h1, groups, m15=None, m30=None,
                          dx_mom=None, b7ctx=None,
                          pv_variants=None, pbctx=None,
                          rcs=None):
    """Full feature frame for one symbol.

    h1: app-shape H1 frame (Datetime index, OHLC[V]).
    groups: subset of {'r4', 'planb', 'b2cf', 'b2x', 'b3',
    'b4', 'b5', 'b6', 'b6v', 'b7', 'b8', 'b9', 'b9c', 'pv',
    'pbc', 'pr', 'rp', 'b12', 'b12c'} on top of the base block (order fixed to the
    research chain). m15: Datetime-indexed M15 frame (b2cf,
    b6v, b9c, pbc). m30: research-shape M30 frame (Datetime
    column); derived from m15 when not given. dx_mom: dollar
    mom24 Series for the xdx columns. b7ctx: cross-symbol
    basket/dollar Series dict for the b7 / b8 blocks (see
    core.new8_candidate.cross_context). pv_variants: vote
    pools to materialise for the pv block. pbctx: cross-
    section context for the pbc block. rcs: cross-sectional
    currency-strength z Series for the b6 block (see
    core.new8_candidate.rcs_context).
    Returns a Datetime-indexed feature frame."""
    fr, vol = frame_to_research(h1)
    if vol is None:
        vol = pd.Series(np.nan, index=pd.DatetimeIndex(
            fr['Datetime']))
    f = add_features_base(fr)
    f = f.set_index('Datetime').sort_index()
    f['atr_pips'] = f['atr14'] / pip_size_new8(sym)
    if m30 is None and m15 is not None:
        m30 = m30_from_m15(m15)
    if 'r4' in groups:
        f = add_r4_columns(f, fr, sym, dx_mom, vol, m30)
    if 'planb' in groups:
        f = add_planb_columns(f, fr, sym, vol)
    if 'b2cf' in groups:
        f = add_b2cf_columns(f, m15, m30)
    if 'b2x' in groups:
        f = add_b2x_columns(f, sym, vol)
    if 'b3' in groups:
        f = add_b3_columns(f, m30)
    if 'b4' in groups:
        f = add_b4_columns(f)
    if 'b5' in groups:
        f = add_b5_columns(f)
    if 'b6' in groups:
        f = add_b6_columns(f, rcs)
    if 'b6v' in groups:
        f = add_b6v_columns(f, sym, m15)
    if 'b7' in groups:
        f = add_b7_columns(f, sym, b7ctx)
    if 'b8' in groups:
        f = add_b8_columns(f, sym, b7ctx)
    if 'b9' in groups:
        f = add_b9_columns(f)
    if 'b9c' in groups:
        f = add_b9c_columns(f, sym, m15)
    if 'pv' in groups:
        f = add_pv_columns(f, sym, pv_variants or {})
    if 'pbc' in groups:
        f = add_pbc_columns(f, sym, m15, vol, pbctx)
    if 'pr' in groups:
        f = add_pr_columns(f)
    if 'rp' in groups:
        f = add_rp_columns(f)
    if 'b12' in groups:
        f = add_b12_columns(f)
    if 'b12c' in groups:
        f = add_b12c_columns(f)
    return f
