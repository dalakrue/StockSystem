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


def build_symbol_features(sym, h1, groups, m15=None, m30=None,
                          dx_mom=None, b7ctx=None):
    """Full feature frame for one symbol.

    h1: app-shape H1 frame (Datetime index, OHLC[V]).
    groups: subset of {'r4', 'planb', 'b2cf', 'b3', 'b4',
    'b5', 'b6v', 'b7'} on top of the base block (order fixed
    to the research chain). m15: Datetime-indexed M15 frame
    (b2cf, b6v). m30: research-shape M30 frame (Datetime
    column); derived from m15 when not given. dx_mom: dollar
    mom24 Series for the xdx columns. b7ctx: cross-symbol
    basket/dollar Series dict for the b7 block (see
    core.new8_candidate.b7_context).
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
    if 'b3' in groups:
        f = add_b3_columns(f, m30)
    if 'b4' in groups:
        f = add_b4_columns(f)
    if 'b5' in groups:
        f = add_b5_columns(f)
    if 'b6v' in groups:
        f = add_b6v_columns(f, sym, m15)
    if 'b7' in groups:
        f = add_b7_columns(f, sym, b7ctx)
    return f
