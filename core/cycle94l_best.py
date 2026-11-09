"""Cycle 94L -- December: design R44A10 (Round 44
disagreement-penalty fusion, lambda 1.00 x RANGE) over
the December candidate stream.

Built on Everest from design R44A10 under the user's
explicit order of 2026-11-09 (anchor proof skipped on
his scoped waiver). NOT VALIDATED.

The design (filed spec: fx_research/round6_r44
SLATE_R6R44_DEC.md + grade_r6r44_dec.json): kept =
the Round-30 final base set (R27A10 over the stored
December pool) + the top 14 adds from the addable pool
(pool rows at the form hours UTC (11, 13, 14), not in
the base, not DOLLARIDX), ranked by the disagreement-
penalty score

    score = mean(sH, sM, sF) - 1.00 * (max - min of
            (sH, sM, sF))

with the original confluence legs sH (H1), sM (M15),
sF (M5) in [0, 1] (research parts()/features()
formulas; scales fitted on the incumbent DISC keeps:
qH = 39.64 pips, qM = 9.735 pips), filled in rank
order under the overlap rule (kept wins, <= 1 open
position per symbol). Filed grade targets (stored
frame): DISC kept 609, win 95.57%, net +7549.80;
AUDIT kept 151, win 92.72%, net +948.29, leftover
50.22%, epd 3.356. Build verification on this machine
(module code over the stored stream + stored bar
features + the filed base mask): reproduced exactly
-- see fx_research/install_build_2026-11-09/dec/.

Live mapping (same architecture as the shipped 94k
form): the candidate stream is the cycle94e panel,
stepped at the (10, 11, 13, 14) UTC grid with
deliveries at the form hours (11, 13, 14) = 17:30 /
19:30 / 20:30 MMT. A ledger row's base flag is settled
by a private cycle94i form instance (the live
reference stream, as in cycle94k); non-base form-hour
rows are the addable pool and are filled by the design
score under the overlap rule, up to the design's 14
adds over the accumulated ledger. Leg scales are the
fitted constants above; the H1 leg is aggregated from
the M15 bars and the M15 leg is read directly; the
app has no live M5 feed, so the M5 leg is computed
from the entry M15 bar's OHLC (the finest live bar) --
the stored-frame verification uses the true stored
M5 windows and is exact. Check hours and sizing are
unchanged from cycle94k: stepping grid (10, 11, 13,
14), deliveries (11, 13, 14); carried N = 150, shipped
at N/3. OFFICE_HOURS carried as the tuple (10,).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

import core.cycle94e_best as _c94e
import core.cycle94i_best as _c94i
import core.cycle93w_best as _c93w
from core import d21rc_lib as _L
from core import rr1val_lib as _V

SYSTEM_NAME = "cycle94l"
CYCLE94L_CHECK_HOURS = (10, 11, 13, 14)
SURFACE_GRID = (10, 11, 13, 14)
MAX_HOLD = 48
N_CARRIED = 150.0
N_USED3 = 50.0
OFFICE_HOURS = (10,)

CHECK_HOURS = (11, 13, 14)
N_USED = N_CARRIED / 3.0
EC22_MONTH = 12

# R44A10 fitted constants (DISC-fitted, frozen in the
# filed slate): leg scales from the incumbent DISC
# keeps, the RANGE penalty lambda and the add count.
QH = 39.64000000000025
QM = 9.735000000000156
LAMBDA_RANGE = 1.0
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


def _design_score(sH, sM, sF):
    """R44A10: balanced mean minus lambda x RANGE."""
    legs = np.vstack([np.asarray(sH, dtype=float),
                      np.asarray(sM, dtype=float),
                      np.asarray(sF, dtype=float)])
    return legs.mean(axis=0) - LAMBDA_RANGE * (
        legs.max(axis=0) - legs.min(axis=0))


def _design_keep(rows):
    """The R44A10 selection over ledger rows (dicts
    with entry_s/exit_s/sym/base_keep/score): base rows
    kept; addable rows (form hours, not base, not
    DOLLARIDX) filled in score-rank order under the
    overlap rule (kept wins, <= 1 open/symbol), up to
    ADD_K adds. Returns the keep mask."""
    n = len(rows)
    keep = np.zeros(n, dtype=bool)
    if n == 0:
        return keep
    for i, r in enumerate(rows):
        keep[i] = bool(r.get('base_keep', False))
    taken = [(int(r['entry_s']), int(r['exit_s']),
              str(r['sym']))
             for i, r in enumerate(rows) if keep[i]]
    cand = []
    for i, r in enumerate(rows):
        if keep[i]:
            continue
        hr = (int(r['entry_s']) % 86400) // 3600
        if hr not in CHECK_HOURS:
            continue
        if 'DOLLARIDX' in str(r['sym']):
            continue
        cand.append(i)
    cand.sort(key=lambda i: -float(rows[i].get(
        'score', 0.0)))
    added = 0
    for i in cand:
        if added >= ADD_K:
            break
        e, x, s = (int(rows[i]['entry_s']),
                   int(rows[i]['exit_s']),
                   str(rows[i]['sym']))
        if any(s == s2 and e < x2 and e2 < x
               for (e2, x2, s2) in taken):
            continue
        taken.append((e, x, s))
        keep[i] = True
        added += 1
    return keep


def _live_legs(sym, side, entry_s, m15_frames):
    """Leg scores for one live ledger row from the
    symbol's M15 frame (full OHLC when the frame is
    available; the entry M15 bar stands in for the M5
    window -- the app has no live M5 feed). Falls back
    to neutral legs when bars are unavailable."""
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
    # M15 leg: last close vs mean of the last 8 closes.
    m15w = c[max(0, j - 7):j + 1]
    dev = (c[j] - float(np.mean(m15w))) / pip
    # H1 leg: H1 closes are the closes of the :45 M15
    # bars; drift over the last 13 H1 closes.
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
    """The December candidate stream settled through
    the R44A10 design rule. Persisted: the stream
    snapshot (scalar rows), the delivered ledger and
    the processed checks."""

    def __init__(self, path=None):
        self.path = path or _state_path()
        self.rows = []
        self.delivered = []
        self.processed = []
        self.inc = _c94i._Form94I(
            path=_sidecar('cycle94l_94i.json'))
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
        score = float(_design_score(sH, sM, sF))
        return {'entry_s': entry_s, 'exit_s': exit_s,
                'sym': sym,
                'side': 1 if dirsign > 0 else -1,
                'net': float(net),
                'pwv': float(prof.min())
                if len(prof) else 0.0,
                'pv': float(pv), 'tp': tp, 'sl': sl,
                'fout': fout,
                'base_keep': bool(base_keep),
                'score': score,
                'year': int(entry_t.year),
                'off': bool(hr in OFFICE_HOURS),
                'is_fill': False}

    def step(self, frames, check_time_utc, m15_frames,
             open_symbols=()):
        chk = pd.Timestamp(check_time_utc)
        if str(chk) in self.processed:
            return [r for r in self.delivered
                    if pd.Timestamp(r['check']) == chk]
        entries = _c94e.panel_entries(
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


def is_cycle94l_check_time(ts) -> bool:
    t = pd.Timestamp(ts)
    return t.hour in CYCLE94L_CHECK_HOURS and t.minute == 30


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
    """The delivered cycle94l stream."""
    return [dict(r) for r in _state().delivered]


def fetch_cycle94l_m15_frames(state=None):
    from core.cycle89_best import fetch_cycle89_m15_frames
    return fetch_cycle89_m15_frames()


def evaluate_cycle94l_signals(frames: dict, check_time_utc,
                              m15_frames: dict | None = None):
    return panel_entries(frames, check_time_utc, m15_frames)


def select_cycle94l_entries(signals: pd.DataFrame,
                            open_symbols=()) -> pd.DataFrame:
    if signals is None or not len(signals):
        return signals
    return signals
