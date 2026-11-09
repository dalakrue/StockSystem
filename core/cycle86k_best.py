"""Cycle 86K -- March: design R34A10 (Round 34
threshold ladder q90) over the incumbent lineage
panel surface.

Built on Everest from design R34A10 under the
user's explicit order of 2026-11-09 (anchor proof
skipped on his scoped waiver). NOT VALIDATED.

The design (filed spec: fx_research/round6_r34
SLATE_R6R34_MAR.md + grade_r6r34_mar.json): kept =
the base set (R3A08 over the stored March pool) +
threshold-ladder adds. The ladder pool = addable
rows (form hours UTC (11, 16, 17), not in the base,
not DOLLARIDX) whose EVERY confluence leg reaches
its DISC-fitted q90 threshold -- the legs sH (H1),
sM (M15), sF (M5) in [0, 1] from the research
parts() formulas (scales fitted on the incumbent
DISC keeps: qH = 38.18 pips, qM = 10.75 pips), the
thresholds taken as the per-leg q90 quantile over
the DISC fit rows (DISC addable rows when >= 30,
else all DISC form rows; March fit: 46 DISC addable
rows, thresholds H1 1.0000 / M15 0.9308 / M5
0.7593, ladder pool 1 row). Pool rows are ranked by
the balanced (1,1,1) score and filled to +14 adds
under the overlap rule (kept wins, <= 1 open
position per symbol). Filed grade targets (stored
frame): DISC kept 374, win 98.13%, net +3822.28,
leftover 76.77%; AUDIT kept 84, win 97.62%, net
+760.39, leftover 75.39%, epd 2.000. Build
verification on this machine (module code over the
stored stream + stored bar features + the
recomputed R3A08 base): reproduced exactly -- see
fx_research/install_build_2026-11-09/mar/.

Live mapping (same architecture as the shipped 86j
form): the candidate stream is the cycle86c panel;
each row's base flag is settled by a private
cycle86h form instance (the live reference stream,
as in cycle86j); the accumulated snapshot is
settled through the ladder rule above, with the
thresholds refitted on the ledger's DISC rows
exactly as graded (the fit is DISC-only, so it is
causal). The H1 leg is aggregated from the M15 bars
and the M15 leg read directly; the app has no live
M5 feed, so the M5 leg is computed from the entry
M15 bar's OHLC (the finest live bar) -- the
stored-frame verification uses the true stored M5
windows and is exact. Check hours (11, 16, 17 UTC)
= 17:30 / 22:30 / 23:30 MMT -- identical to
cycle86j, so the install needs no signal/prep job
retiming. Sizing: carried N = 86, shipped at N/3,
unchanged. OFFICE_HOURS carried as the tuple ()
(exactly as in cycle86j).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

import core.cycle86c_best as _c86c
import core.cycle86h_best as _c86h
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L
from core import rr1val_lib as _V

SYSTEM_NAME = "cycle86k"
CYCLE86K_CHECK_HOURS = (11, 16, 17)
SURFACE_GRID = (11, 16, 17)
MAX_HOLD = 48
N_CARRIED = 86.0
N_USED3 = 28.666666666666668
OFFICE_HOURS = ()

CHECK_HOURS = (11, 16, 17)
N_USED = N_CARRIED / 3.0
EC22_MONTH = 3

# R34A10 fitted constants (DISC-fitted, frozen in
# the filed slate): leg scales from the incumbent
# DISC keeps, the ladder quantile and the add size.
QH = 38.17999999999943
QM = 10.750000000000153
LADDER_Q = 0.90
ADD_K = 14


def _state_path():
    from core.new8_candidate import default_state_path
    return default_state_path(SYSTEM_NAME)


def _sidecar(name):
    from core.new8_candidate import default_state_path
    base = default_state_path(SYSTEM_NAME)
    return os.path.join(os.path.dirname(
        os.path.abspath(base)), name)


def _leg_scores(h1_drift, dev, m5o, m5h, m5l, m5c,
                side, pip):
    """The research confluence legs (parts()/
    features() formulas, scales QH/QM). Scalar or
    array inputs; returns (sH, sM, sF)."""
    side = np.asarray(side, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        rng = (m5h - m5l) / pip
        body = (m5c - m5o) / pip
        loc = np.where(side > 0,
                       (m5c - m5l) / (m5h - m5l),
                       (m5h - m5c) / (m5h - m5l))
        bodyr = np.where(rng > 0, body / rng, 0.0)
    sH = np.clip(0.5 + side * h1_drift / (2 * QH), 0, 1)
    sM = np.clip(0.5 + side * dev / (2 * QM), 0, 1)
    sF = np.clip(0.5 * np.nan_to_num(loc, nan=0.5) + 0.25
                 + 0.25 * side
                 * np.nan_to_num(bodyr, nan=0.0), 0, 1)
    sH = np.nan_to_num(sH, nan=0.5)
    sM = np.nan_to_num(sM, nan=0.5)
    return sH, sM, sF


def _design_keep(rows):
    """The R34A10 selection over ledger rows (dicts
    with entry_s/exit_s/sym/base_keep/sH/sM/sF/bal/
    disc): base kept; the ladder pool (addable rows
    whose every leg reaches its DISC-fitted q90
    threshold, thresholds fitted on the DISC fit
    rows exactly as graded) ranked by the balanced
    score and filled to ADD_K adds under the
    overlap rule. Returns the keep mask."""
    n = len(rows)
    keep = np.zeros(n, dtype=bool)
    if n == 0:
        return keep
    entry = np.array([int(r['entry_s']) for r in rows],
                     dtype=np.int64)
    exit_ = np.array([int(r['exit_s']) for r in rows],
                     dtype=np.int64)
    sym = [str(r['sym']) for r in rows]
    base = np.array([bool(r.get('base_keep', False))
                     for r in rows], bool)
    disc = np.array([bool(r.get('disc', False))
                     for r in rows], bool)
    sH = np.array([float(r.get('sH', 0.0)) for r in rows])
    sM = np.array([float(r.get('sM', 0.0)) for r in rows])
    sF = np.array([float(r.get('sF', 0.0)) for r in rows])
    bal = np.array([float(r.get('bal', 0.0)) for r in rows])
    hr = (entry % 86400) // 3600
    form = np.isin(hr, list(CHECK_HOURS))
    dollar = np.array(['DOLLARIDX' in s for s in sym])
    addable = form & (~dollar) & (~base)
    disc_add = addable & disc
    if int(disc_add.sum()) >= 30:
        fit_rows = disc_add
    else:
        fit_rows = disc & form & (~dollar)
    keep = base.copy()
    if not fit_rows.any():
        return keep
    thr = [float(np.quantile(leg[fit_rows], LADDER_Q))
           for leg in (sH, sM, sF)]
    pool = addable & (sH >= thr[0]) & (sM >= thr[1]) \
        & (sF >= thr[2])
    cand = [int(i) for i in np.where(pool)[0]]
    cand.sort(key=lambda i: -bal[i])
    taken = [(int(entry[i]), int(exit_[i]), sym[i])
             for i in np.where(keep)[0]]
    added = 0
    for i in cand:
        if added >= ADD_K:
            break
        if keep[i]:
            continue
        e, x, s = int(entry[i]), int(exit_[i]), sym[i]
        if any(s == s2 and e < x2 and e2 < x
               for (e2, x2, s2) in taken):
            continue
        taken.append((e, x, s))
        keep[i] = True
        added += 1
    return keep


def _live_legs(sym, side, entry_s, m15_frames):
    """Leg scores for one live ledger row from the
    symbol's M15 frame (the entry M15 bar stands in
    for the M5 window -- the app has no live M5
    feed). Neutral legs when bars are unavailable."""
    pip = 0.01 if 'JPY' in sym else 0.0001
    df = None
    if m15_frames and sym in m15_frames \
            and m15_frames[sym] is not None \
            and len(m15_frames[sym]):
        df = m15_frames[sym]
    if df is None:
        return 0.5, 0.5, 0.5
    try:
        tcol = next(c for c in df.columns
                    if c.lower() in ('datetime', 'time',
                                     'timestamp'))
        ts = (pd.to_datetime(df[tcol], utc=True)
              .astype('int64') // 10 ** 9).to_numpy(
                  np.int64)
        o = df['Open'].to_numpy(np.float64)
        h = df['High'].to_numpy(np.float64)
        l = df['Low'].to_numpy(np.float64)
        c = df['Close'].to_numpy(np.float64)
    except Exception:
        return 0.5, 0.5, 0.5
    j = int(np.searchsorted(ts, entry_s, side='right')) - 1
    if j < 0:
        return 0.5, 0.5, 0.5
    m15w = c[max(0, j - 7):j + 1]
    dev = (c[j] - float(np.mean(m15w))) / pip
    h1_idx = [i for i in range(j + 1)
              if ts[i] % 3600 == 2700]
    if len(h1_idx) >= 13:
        h1_drift = (c[h1_idx[-1]] - c[h1_idx[-13]]) / pip
    elif h1_idx:
        h1_drift = (c[h1_idx[-1]] - c[h1_idx[0]]) / pip
    else:
        h1_drift = 0.0
    sH, sM, sF = _leg_scores(h1_drift, dev, o[j], h[j],
                             l[j], c[j], side, pip)
    return float(sH), float(sM), float(sF)


class _Form:
    """The surface stream settled through the
    R34A10 ladder rule. Persisted: the stream
    snapshot (scalar rows), the delivered ledger
    and the processed checks."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.rows = []
        self.delivered = []
        self.processed = []
        self.inc = _c86h._Form86H(
            path=_sidecar('cycle86k_86h.json'))
        self._load()

    def _load(self):
        import json
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path) as fh:
                d = json.load(fh)
        except Exception:
            return
        self.rows = d.get('rows', [])
        self.processed = d.get('processed', [])
        out = []
        for r in d.get('delivered', []):
            r = dict(r)
            for k in ('check', 'entry_time', 'exit_time'):
                if r.get(k) is not None:
                    r[k] = pd.Timestamp(r[k])
            out.append(r)
        self.delivered = out

    def save(self):
        import json
        if not self.path:
            return
        os.makedirs(os.path.dirname(
            os.path.abspath(self.path)), exist_ok=True)

        def ser(rows):
            out = []
            for r in rows:
                dd = dict(r)
                for k in ('check', 'entry_time',
                          'exit_time'):
                    if dd.get(k) is not None:
                        dd[k] = pd.Timestamp(
                            dd[k]).isoformat()
                out.append(dd)
            return out
        with open(self.path, 'w') as fh:
            json.dump({'system': SYSTEM_NAME,
                       'rows': self.rows,
                       'delivered': ser(self.delivered),
                       'processed': self.processed}, fh)

    def _lrow(self, r, m15_frames, base_keep):
        chk = pd.Timestamp(r['check'])
        entry_t = pd.Timestamp(r.get('entry_candle')
                               ) if r.get('entry_candle') \
            is not None else chk - pd.Timedelta(
                minutes=30)
        entry_s = int(entry_t.value // 10 ** 9)
        exit_s = entry_s + MAX_HOLD * 3600
        sym = str(r['symbol'])
        bars = _c93w._bars(sym, m15_frames)
        dirsign = 1.0 if str(r['direction']).upper() \
            .startswith('B') else -1.0
        entry_px = float(r.get('entry_px') or 0.0)
        if not entry_px:
            ts_arr = bars[0]
            j = int(np.searchsorted(ts_arr, entry_s))
            entry_px = float(bars[1][min(j,
                                         len(ts_arr) - 1)])
        prof = _L.profile_for_sym(sym, entry_s, exit_s,
                                  entry_px, dirsign, bars)
        majors = {p: _c93w._bars(p, m15_frames)
                  for p in _L.MAJORS}
        pv = _L.pip_value_per_lot(
            sym, _L.rates_at(majors, exit_s))
        if r.get('gross_pips') is not None:
            net = float(r['gross_pips']) - _V.COST
        else:
            net = (float(prof[-1]) if len(prof) else 0.0)
        tp = float(r['tp_pips'])
        sl = float(r['sl_pips'])
        fout = float(_V.stop_tighten_arr(
            {'prof': [prof]}, np.array([min(sl, tp)]),
            np.array([net]))[0])
        hr = (entry_s % 86400) // 3600
        sH, sM, sF = _live_legs(sym, dirsign, entry_s,
                                m15_frames)
        return {'entry_s': entry_s, 'exit_s': exit_s,
                'sym': sym,
                'side': 1 if dirsign > 0 else -1,
                'net': float(net),
                'pwv': float(prof.min())
                if len(prof) else 0.0,
                'pv': float(pv), 'tp': tp, 'sl': sl,
                'fout': fout,
                'base_keep': bool(base_keep),
                'sH': float(sH), 'sM': float(sM),
                'sF': float(sF),
                'bal': float((sH + sM + sF) / 3.0),
                'disc': bool(2016 <= int(entry_t.year)
                             <= 2023),
                'year': int(entry_t.year),
                'off': bool(hr in OFFICE_HOURS),
                'is_fill': False}

    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=()):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r['check']) == chk]
        entries = _c86c.panel_entries(
            frames, check_time_utc, m15_frames=m15_frames,
            open_symbols=open_symbols)
        if entries is not None \
                and entries.attrs.get('status'):
            return entries
        inc_out = self.inc.step(frames, check_time_utc,
                                m15_frames,
                                open_symbols=open_symbols)
        if isinstance(inc_out, pd.DataFrame):
            return inc_out

        def key(r):
            return (str(r.get('symbol')),
                    str(r.get('direction')),
                    str(r.get('strategy')
                        or r.get('equation') or ''))
        delivered_keys = {key(r) for r in inc_out}
        new_rows, payloads = [], []
        if entries is not None and len(entries):
            for _, r in entries.iterrows():
                dd = dict(r)
                dd.setdefault('check', chk)
                new_rows.append(self._lrow(
                    dd, m15_frames,
                    key(dd) in delivered_keys))
                payloads.append(dd)
        self.rows.extend(new_rows)
        keep = _design_keep(self.rows)
        out = []
        n_old = len(self.rows) - len(new_rows)
        for j, dd in enumerate(payloads):
            if not keep[n_old + j]:
                continue
            dd['sl_pips'] = min(float(dd['sl_pips']),
                                float(dd['tp_pips']))
            dd['exit_time'] = pd.Timestamp(
                dd.get('entry_candle', chk)) \
                + pd.Timedelta(hours=MAX_HOLD)
            self.delivered.append(dd)
            out.append(dd)
        self.processed.append(str(chk))
        self.save()
        return out


_STATE = None


def _state():
    global _STATE
    if _STATE is None:
        _STATE = _Form()
    return _STATE


def load_state_form(path=None):
    if path is not None:
        return _Form(path=path)
    return _state()


def is_cycle86k_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE86K_CHECK_HOURS and t.minute == 30


def panel_entries(frames: dict, check_time_utc,
                  m15_frames: dict | None = None,
                  open_symbols=()) -> pd.DataFrame:
    form = _state()
    out = form.step(frames, check_time_utc, m15_frames,
                    open_symbols)
    if isinstance(out, pd.DataFrame):
        return out
    if not out:
        return pd.DataFrame()
    return pd.DataFrame(out)


def walk_ledger():
    """The delivered cycle86k stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle86k_m15_frames(state=None):
    from core.cycle89_best import fetch_cycle89_m15_frames
    return fetch_cycle89_m15_frames()


def evaluate_cycle86k_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle86k_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
