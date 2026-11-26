"""Replay — past check calculator (user order 2026-11-25).

A dashboard section at the bottom, immediately before History.
Pick a date, pick one of that date's check times, press
Calculate: the app loads that slot's candles (H1 / M15 / M5,
28 symbols) from the store and runs a RAW, STATELESS
calculation — the month cycle's own equations on a fresh,
empty form. No walked memory is read or used, so the section
works for dates with no walked memory at all.

Two results per slot:
- CHECK: the full signal (symbol, side, entry, TP, SL) the
  equations produce for that slot, plus the runner-up /
  closest near-miss from the same read.
- PRECHECK (check - 15 min): the same raw calculation on the
  data as it stood 15 minutes before the check — only candles
  completed by then. A precheck never waits for the entry
  candle (user rule 2026-11-26): it is judged on the H1 sig
  bar (completed by check - 30) and the history before it,
  with the entry candle synthesized from the signal close —
  the same method as the proven true-precheck walk. The gate
  stays 28/28 on the sig bar, or DATA ERROR naming what is
  missing — never a guessed signal.

State safety: the evaluation runs on a temporary form file;
the real walk ledgers are never read, stepped or written,
and the GitHub save-back is disabled for the duration.
Gate: 28/28 or DATA ERROR, both sides. Data-basis labels
("fallback data" / "assembled-from-M5 data") follow the read
path's own basis reporting.
"""
from __future__ import annotations

import datetime as _dt
import importlib
import os
import tempfile

import pandas as pd


# ------------------------------------------------------------------
# Registry / cycle resolution — read fresh, never hardcoded
# ------------------------------------------------------------------

def _month_module(month: int):
    from core.signal_mode import MONTH_SYSTEMS
    system = MONTH_SYSTEMS[int(month)]
    mod = importlib.import_module(f"core.{system}_best")
    return system, mod


def _check_hours(mod, system: str):
    name = f"CYCLE{system[5:].upper()}_CHECK_HOURS"
    hours = getattr(mod, name, None)
    if hours is None:
        for attr in dir(mod):
            if attr.endswith("_CHECK_HOURS"):
                hours = getattr(mod, attr)
                break
    return tuple(int(h) for h in (hours or ()))


def slots_for_date(d: _dt.date):
    """[(slot_ts_utc, label)] for one date; [] on weekends /
    months without check hours. The label carries the user's
    MMT check label (slot stamp + 6h, the feed's convention)
    and the UTC stamp."""
    if d.weekday() >= 5:
        return []
    try:
        _system, mod = _month_module(d.month)
    except Exception:
        return []
    hours = _check_hours(mod, _system)
    out = []
    for h in hours:
        ts = pd.Timestamp(_dt.datetime(d.year, d.month, d.day, h, 30))
        label = (f"{(ts + pd.Timedelta(hours=6)):%H:%M} MMT check "
                 f"· {ts:%H:%M} UTC")
        out.append((ts, label))
    return out


# ------------------------------------------------------------------
# Raw stateless evaluation helpers
# ------------------------------------------------------------------

def _pip_of(sym: str) -> float:
    return 0.01 if sym.endswith("JPY") else 0.0001


def _basis_label(basis: str) -> str:
    return {"fallback": "fallback data",
            "assembled": "assembled-from-M5 data"}.get(basis, "")


def _stateless_entries(mod, month, frames, slot, m15_frames=None):
    """Evaluate ONE slot on a fresh, empty form (raw
    calculation). The real ledger is never touched: the
    module's state handle is pointed at a temp file for the
    call and restored afterwards, and the save-back hook is
    disabled for the duration."""
    import core.signal_mode as sm
    fd, tmp = tempfile.mkstemp(prefix="replay_state_",
                               suffix=".json")
    os.close(fd)
    os.remove(tmp)  # absent file = empty state
    prev_form = getattr(mod, "_STATE", None)
    prev_saveback = sm._saveback_ledgers
    try:
        sm._saveback_ledgers = lambda: None
        mod._STATE = mod.load_state_form(path=tmp)
        if m15_frames is None:
            entries, _src = sm.evaluate_combined_entries(
                int(month), frames, slot, open_symbols=())
        else:
            entries = mod.panel_entries(
                frames, slot, m15_frames=m15_frames,
                open_symbols=())
    finally:
        sm._saveback_ledgers = prev_saveback
        mod._STATE = prev_form
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
    if entries is None or not isinstance(entries, pd.DataFrame):
        return []
    return [dict(r) for _, r in entries.iterrows()]


def _m15_bars(mod, m15_frames):
    bars = {}
    for sym, frame in (m15_frames or {}).items():
        b = mod._bars_from_frame(frame)
        if b is not None:
            bars[sym] = b
    return bars


def _window_ok(bars, slot):
    """The builders' own consumed M15 input: the entry bar
    (slot - 15m) with the full 32-bar window ending at it."""
    import numpy as np
    T = int(pd.Timestamp(slot).timestamp())
    ok, missing = [], []
    for sym, b in bars.items():
        ts = b[0]
        idx = int(np.searchsorted(ts, T - 900))
        good = (idx < len(ts) and ts[idx] == T - 900
                and idx >= 31 and all(
                    ts[idx - k] == T - 900 - 900 * k
                    for k in range(32)))
        (ok if good else missing).append(sym)
    return ok, missing


def _candidate_rows(mod, frames, bars, slot):
    """Candidate rows from the same read (both books), in the
    chain capture's ranking order (-sMC, -score)."""
    # Capability guard (fix 2026-11-26): only November (93aj) and
    # December (94t) carry the panel-context helper this reader
    # needs. The other ten months have no panel read to rank --
    # return empty honestly instead of letting the swallowed
    # AttributeError below masquerade as "no second best exists".
    if not hasattr(mod, "_set_panel_ctx"):
        return []
    rows = []
    try:
        mod._set_panel_ctx(frames, None)
        T = int(pd.Timestamp(slot).timestamp())
        for book, fn in (("PW", getattr(mod, "_slot_rows", None)),
                         ("LVD", getattr(mod, "_slot_rows_lvd",
                                         None))):
            if fn is None:
                continue
            for r in fn(T, bars):
                rows.append((book, r))
        rows.sort(key=lambda p: (-float(p[1]["sMC"]),
                                 -float(p[1]["score"])))
    except Exception:
        return []
    return rows


def _near_miss(mod, bars, slot, dealt_keys):
    """Closest near-miss from the same read: the symbol/side
    whose band position came nearest to entering the band,
    computed with the module's own _pos32. Returns None when
    every symbol with a valid entry bar was dealt or in-band."""
    # Capability guard (fix 2026-11-26): January (60k), March
    # (86o), August (67w) and October (92l) have no _pos32 helper.
    # The unguarded call below raised AttributeError AFTER the
    # check result was already computed, collapsing the whole read
    # into a fake "DATA ERROR -- calculation failed". A month
    # without _pos32 simply has no near-miss line.
    if not hasattr(mod, "_pos32"):
        return None
    import numpy as np
    T = int(pd.Timestamp(slot).timestamp())
    lo = float(getattr(mod, "BAND_LO", 0.4))
    hi = float(getattr(mod, "BAND_HI", 0.6))
    best = None
    for sym, b in bars.items():
        ts, _o, h, l, c = b
        idx = int(np.searchsorted(ts, T - 900))
        if idx >= len(ts) or ts[idx] != T - 900 or idx < 31:
            continue
        pos = mod._pos32(h, l, c, idx)
        if pos is None:
            continue
        for side in (1, -1):
            adj = float(pos) if side > 0 else 1.0 - float(pos)
            if lo < adj < hi:
                dist = 0.0
            elif adj <= lo:
                dist = lo - adj
            else:
                dist = adj - hi
            if dist <= 0:
                continue
            if (sym, "BUY" if side > 0 else "SELL") in dealt_keys:
                continue
            if best is None or dist < best["dist"]:
                best = {"symbol": sym,
                        "direction": "BUY" if side > 0 else "SELL",
                        "entry_px": float(c[idx]),
                        "pos_adj": adj, "dist": dist,
                        "band": (lo, hi)}
    return best


def _pick_view(r):
    sym = r["symbol"]
    pip = _pip_of(sym)
    sgn = 1 if r["direction"] == "BUY" else -1
    entry = float(r["entry_px"])
    tp = entry + sgn * float(r["tp_pips"]) * pip
    sl = entry - sgn * float(r["sl_pips"]) * pip
    return {"symbol": sym, "direction": r["direction"],
            "entry_px": entry, "tp_pips": float(r["tp_pips"]),
            "sl_pips": float(r["sl_pips"]), "tp_px": tp,
            "sl_px": sl,
            "entry_line": (f"ENTRY: {sym}-{r['direction'][0]}-"
                           f"T{tp:.5f},S{sl:.5f}")}


# ------------------------------------------------------------------
# CHECK side — raw calculation on the slot's full data
# ------------------------------------------------------------------

def replay_check(month: int, slot) -> dict:
    from core.check_candle_runtime import fetch_check_frames
    system, mod = _month_module(month)
    symbols = list(mod.SYMBOLS)
    slot = pd.Timestamp(slot)
    sig = slot - pd.Timedelta(hours=1, minutes=30)
    ent = slot - pd.Timedelta(minutes=30)

    frames, _latest, diag = fetch_check_frames(
        {}, symbols, need_candles=[sig, ent])
    ready = int(diag.get("ready", 0))
    if ready != len(symbols):
        return {"status": "DATA ERROR",
                "missing": (f"H1 sig/entry candles for "
                            f"{len(symbols) - ready} symbols: "
                            f"{', '.join(diag.get('missing_symbols', []))}"),
                "basis": diag.get("data_basis", "dukascopy")}

    fetch_m15 = getattr(mod, f"fetch_{system}_m15_frames")
    m15_frames = fetch_m15()
    bars = _m15_bars(mod, m15_frames)
    _ok, m15_missing = _window_ok(bars, slot)
    absent = [s for s in symbols if s not in bars]
    if m15_missing or absent:
        bad = sorted(set(m15_missing) | set(absent))
        return {"status": "DATA ERROR",
                "missing": (f"M15 entry bar / 32-bar window for "
                            f"{len(bad)} symbols: {', '.join(bad)}"),
                "basis": diag.get("data_basis", "dukascopy")}

    basis = diag.get("data_basis", "dukascopy")
    bases = {getattr(f, "attrs", {}).get("data_basis")
             for f in m15_frames.values()}
    if "assembled" in bases:
        basis = "assembled"
    elif "fallback" in bases and basis == "dukascopy":
        basis = "fallback"

    # Evaluate on the SAME M15 frames the gate just verified
    # (panel_entries accepts them directly — the module's own
    # entry point), so the read is evaluated exactly as gated.
    dealt = _stateless_entries(mod, month, frames, slot,
                               m15_frames=m15_frames)
    picks = [_pick_view(r) for r in dealt]
    dealt_keys = {(p["symbol"], p["direction"]) for p in picks}

    second = None
    for book, r in _candidate_rows(mod, frames, bars, slot):
        key = (r["sym"], "BUY" if r["side"] > 0 else "SELL")
        if key in dealt_keys:
            continue
        second = {"symbol": r["sym"], "direction": key[1],
                  "entry_px": float(r["entry_px"]),
                  "book": book, "sMC": float(r["sMC"]),
                  "score": float(r["score"]),
                  "pos_adj": float(r["pos_adj"]),
                  "status": "met the entry condition in this "
                            "read; not dealt (runner-up)"}
        break
    near = None
    if second is None:
        nm = _near_miss(mod, bars, slot, dealt_keys)
        if nm is not None:
            near = {"symbol": nm["symbol"],
                    "direction": nm["direction"],
                    "entry_px": nm["entry_px"],
                    "status": (f"nearly met it — band position "
                               f"{nm['pos_adj']:.3f}, "
                               f"{nm['dist']:.3f} outside the band "
                               f"[{nm['band'][0]}, {nm['band'][1]}]")}
    return {"status": "OK" if picks else "NO SIGNAL",
            "picks": picks, "second_best": second,
            "near_miss": near, "basis": basis}


# ------------------------------------------------------------------
# PRECHECK side — raw calculation on data as of check - 15 min
# ------------------------------------------------------------------

def replay_precheck(month: int, slot) -> dict:
    """Precheck inputs at the cutoff (check - 15 min): the H1
    sig frame — the sig bar completes by check - 30 — and the
    history before it. Only candles COMPLETED by the cutoff
    count. The entry candle is NOT required: a precheck never
    waits for it (user rule 2026-11-26); the combined
    evaluation synthesizes it from the signal close, exactly
    as in the proven true-precheck walk. (The previous version
    demanded the M15 entry bar, which completes AT the check
    time itself, so every precheck was a structural DATA
    ERROR — that demand is removed.)"""
    from core.check_candle_runtime import (
        _repository, normalize_ohlc)
    system, mod = _month_module(month)
    symbols = list(mod.SYMBOLS)
    slot = pd.Timestamp(slot)
    cutoff = slot - pd.Timedelta(minutes=15)
    sig = slot - pd.Timedelta(hours=1, minutes=30)
    repo = _repository()
    if repo is None:
        return {"status": "DATA ERROR",
                "missing": "candle store unavailable"}

    def _truncated(tf, minutes):
        out = {}
        limit = 2000 if tf == "H1" else 6000
        for sym in symbols:
            raw = repo.load(sym, tf, limit=limit,
                            completed_only=False)
            f = normalize_ohlc(raw, 1)
            if f is None:
                continue
            keep = f.index + pd.Timedelta(minutes=minutes) <= cutoff
            out[sym] = f[keep]
        return out

    h1 = _truncated("H1", 60)
    h1_missing = [s for s in symbols
                  if s not in h1 or sig not in h1[s].index]
    if h1_missing:
        return {"status": "DATA ERROR",
                "missing": (
                    f"H1 sig bar {sig} UTC missing for "
                    f"{len(h1_missing)} symbols: "
                    f"{', '.join(h1_missing)}")}

    # Evaluate statelessly on the cutoff-truncated H1 frames
    # via the combined path (m15_frames=None): the entry
    # candle is synthesized from the signal close.
    dealt = _stateless_entries(mod, month, h1, slot)
    picks = [{"symbol": r["symbol"], "direction": r["direction"],
              "entry_px": float(r["entry_px"])} for r in dealt]
    return {"status": "OK" if picks else "NO SIGNAL",
            "picks": picks}


def replay_slot(d: _dt.date, slot) -> dict:
    return {"date": str(d), "slot": str(slot),
            "check": replay_check(d.month, slot),
            "precheck": replay_precheck(d.month, slot)}


# ------------------------------------------------------------------
# Dashboard rendering
# ------------------------------------------------------------------

def _default_replay_date():
    """Default replay date (fix 2026-11-26): the most recent
    weekday BEFORE today. The old default was today, whose slots
    have usually not completed yet, so the first thing a user saw
    on pressing Calculate was a DATA ERROR for a slot whose data
    cannot exist yet. Yesterday's (or Friday's) slots are
    complete and calculable."""
    d = _dt.date.today() - _dt.timedelta(days=1)
    while d.weekday() >= 5:  # Sat/Sun -> back to Friday
        d -= _dt.timedelta(days=1)
    return d


def render_replay_section(st):
    """Replay — the bottom of the dashboard, immediately
    before History (user order 2026-11-25)."""
    st.markdown(
        "<div style='border-top:8px solid #7c3aed;margin:22px 0 8px 0;'></div>"
        "<div style='background:#7c3aed;color:#fff;border-radius:10px;"
        "padding:10px 14px;font-size:20px;font-weight:800;'>"
        "🟣 REPLAY — past check calculator</div>"
        "<div style='font-size:14px;margin:6px 2px;'>"
        "Raw calculation from candles — no memory used. "
        "Pick a date and a check time, then Calculate.</div>",
        unsafe_allow_html=True)

    d = st.date_input("Date", value=_default_replay_date(),
                      key="replay_date")
    slots = slots_for_date(d)
    if not slots:
        st.caption("No check times on this date "
                   "(weekend, or no system for that month).")
        return
    labels = [lbl for _ts, lbl in slots]
    choice = st.selectbox("Check time", labels, key="replay_slot")
    slot = dict((lbl, ts) for ts, lbl in slots)[choice]

    if st.button("Calculate", key="replay_calc"):
        with st.spinner("Calculating — loading candles and "
                        "running the raw calculation…"):
            try:
                st.session_state["replay_result"] = replay_slot(
                    d, slot)
            except Exception as exc:
                st.session_state["replay_result"] = {
                    "date": str(d), "slot": str(slot),
                    "check": {"status": "DATA ERROR",
                              "missing": f"calculation failed: "
                                         f"{type(exc).__name__}: "
                                         f"{exc}"},
                    "precheck": {"status": "DATA ERROR",
                                 "missing": "not run"}}
    res = st.session_state.get("replay_result")
    if not res or res.get("slot") != str(slot) \
            or res.get("date") != str(d):
        return

    chk = res["check"]
    st.markdown("**CHECK**")
    if chk["status"] == "DATA ERROR":
        st.error(f"DATA ERROR — {chk.get('missing', '')}")
    elif chk["status"] == "NO SIGNAL":
        st.markdown("**NO SIGNAL** — no symbol met the entry "
                    "condition in this read.")
    else:
        for p in chk["picks"]:
            st.markdown(
                f"<div style='font-size:22px;font-weight:800;"
                f"margin:4px 0;'>{p['entry_line']}</div>",
                unsafe_allow_html=True)
            st.markdown(
                f"{p['symbol']} {p['direction']} @ "
                f"{p['entry_px']:.5f} · TP {p['tp_px']:.5f} "
                f"({p['tp_pips']:.0f} pips) · SL {p['sl_px']:.5f} "
                f"({p['sl_pips']:.0f} pips)")
    if chk.get("second_best"):
        s = chk["second_best"]
        st.markdown(
            f"Second best: **{s['symbol']} {s['direction']} @ "
            f"{s['entry_px']:.5f}** — {s['status']} "
            f"({s['book']} book, sMC {s['sMC']:.4f}, "
            f"score {s['score']:.4f})")
    elif chk.get("near_miss"):
        n = chk["near_miss"]
        st.markdown(
            f"Closest near-miss: **{n['symbol']} "
            f"{n['direction']} @ {n['entry_px']:.5f}** — "
            f"{n['status']}")
    lbl = _basis_label(chk.get("basis", ""))
    if lbl:
        st.caption(f"Data basis: {lbl}")

    pre = res["precheck"]
    st.markdown("**PRECHECK (check − 15 min)**")
    if pre["status"] == "DATA ERROR":
        st.error(f"DATA ERROR — {pre.get('missing', '')}")
    elif pre["status"] == "NO SIGNAL":
        st.markdown("**NO SIGNAL**")
    else:
        for p in pre["picks"]:
            st.markdown(f"**{p['symbol']} {p['direction']} @ "
                        f"{p['entry_px']:.5f}**")
