"""Replay — past check calculator (user order 2026-11-25;
Twelve Data route, user order 2026-11-27).

A dashboard section at the bottom, immediately before History.
Pick a date, pick one of that date's check times, press
Calculate: the app loads that slot's candles (H1 / M15 / M5,
28 symbols) FROM THE TWELVE DATA API — the window ending at
that slot, fetched at click time — and runs a RAW, STATELESS
calculation on those candles: the month cycle's own equations
on a fresh, empty form. No walked memory and no local candle
store are used for the calculation, so the section works for
dates whose candles were never loaded into the app.

ONLY AFTER the calculation does the section look at the past:
the slot's recorded result (the walk ledger's delivered /
processed lists, read-only) is shown next to the fresh result
with a MATCH / DIFFERENT verdict. The recorded result never
feeds the calculation.

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
  the same method as the proven true-precheck walk.

State safety: the evaluation runs on a temporary form file;
the real walk ledgers are never stepped or written, and the
GitHub save-back is disabled for the duration. The comparison
lookup reads the ledger only.
Gate: 28/28 or DATA ERROR, both sides — never a guessed
signal. Data basis is labelled "Twelve Data" (or
"assembled-from-M5 data" where an M15 bar had to be assembled
from Twelve M5 bars, gaps only, real M15 always wins).
"""
from __future__ import annotations

import datetime as _dt
import importlib
import os
import tempfile
import time

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
# Twelve Data window loader (user order 2026-11-27)
#
# On Calculate, the slot's candles are fetched from the Twelve
# Data API for the exact window the calculation consumes:
# H1 ending at the entry hour, M15 and M5 ending at the entry
# bar. Keys come from the app's own key pool (session state /
# Streamlit secrets / vault), rotated per request under the
# pool's per-minute limits. Frames are normalized to exactly
# the shapes the evaluators already consume. Results are
# cached per (symbol, timeframe, window end) for the life of
# the app process, so re-clicking a slot costs no credits.
# ------------------------------------------------------------------

_TWELVE_URL = "https://api.twelvedata.com/time_series"
_TWELVE_TF = {"H1": ("1h", 450, 60), "M15": ("15min", 400, 15),
              "M5": ("5min", 400, 5)}
_TWELVE_CACHE: dict = {}
_TWELVE_WAIT_LIMIT_S = 150.0


def _twelve_symbol(sym: str) -> str:
    try:
        from core.connectors.data_parts.utils import (
            _twelve_symbol as _fmt)
        return _fmt(sym)
    except Exception:
        s = str(sym).strip().upper()
        if len(s) == 6 and s.isalpha():
            return f"{s[:3]}/{s[3:]}"
        return s


def _twelve_pool(state):
    from core.twelve_data_key_pool import TwelveDataKeyPool
    return TwelveDataKeyPool.from_state(
        state if state is not None else {})


def _twelve_fetch_values(pool, sym, interval, bars, end_ts,
                         step_minutes=60):
    """One Twelve time_series window request. Returns
    (values_list, "") or (None, error_note). Waits (bounded)
    when every configured key is at its per-minute limit."""
    import requests
    waited = 0.0
    last_note = "Twelve Data request did not run"
    while True:
        lease = None
        try:
            lease = pool.reserve_key(symbol=sym,
                                     timeframe=interval)
        except Exception as exc:
            return None, f"Twelve Data key pool error: {exc}"
        if lease is None:
            try:
                n_keys = len(pool.keys())
            except Exception:
                n_keys = 0
            if n_keys == 0:
                return None, ("Twelve Data API key is not "
                              "configured")
            if waited >= _TWELVE_WAIT_LIMIT_S:
                return None, ("Twelve Data keys are at their "
                              "per-minute limit")
            time.sleep(5.0)
            waited += 5.0
            continue
        params = {
            "symbol": _twelve_symbol(sym),
            "interval": interval,
            "outputsize": int(bars),
            "apikey": lease.api_key,
            "format": "JSON",
            "timezone": "UTC",
            # One bar past the window end, so the bar AT the
            # end is included whichever way the API bounds it;
            # the caller truncates exactly.
            "end_date": (end_ts + pd.Timedelta(
                minutes=step_minutes)).strftime(
                "%Y-%m-%d %H:%M:%S"),
        }
        try:
            resp = requests.get(_TWELVE_URL, params=params,
                                timeout=20)
            data = resp.json()
        except Exception as exc:
            last_note = f"Twelve Data network error: {exc}"
            time.sleep(2.0)
            waited += 2.0
            if waited >= _TWELVE_WAIT_LIMIT_S:
                return None, last_note
            continue
        if isinstance(data, dict) and data.get("values"):
            return data["values"], ""
        msg = ""
        if isinstance(data, dict):
            msg = str(data.get("message") or data.get("status")
                      or "")[:160]
        last_note = f"Twelve Data: {msg or 'no candle rows'}"
        if "limit" in last_note.lower() or resp.status_code == 429:
            time.sleep(5.0)
            waited += 5.0
            if waited >= _TWELVE_WAIT_LIMIT_S:
                return None, last_note
            continue
        return None, last_note


def _twelve_frame(pool, sym, tf, end_ts, errors):
    """Normalized Twelve frame for one symbol/timeframe,
    truncated to bars starting at or before end_ts. M15/M5
    frames also carry the Datetime column the month modules
    read, mirroring the runtime's own M15/M5 returns."""
    from core.check_candle_runtime import normalize_ohlc
    interval, bars, step_minutes = _TWELVE_TF[tf]
    key = (sym, tf, str(end_ts))
    if key in _TWELVE_CACHE:
        return _TWELVE_CACHE[key]
    values, note = _twelve_fetch_values(pool, sym, interval,
                                        bars, end_ts,
                                        step_minutes=step_minutes)
    frame = None
    if values:
        raw = pd.DataFrame(values)
        frame = normalize_ohlc(raw, 1)
        if frame is not None:
            frame = frame.loc[:end_ts]
            if frame.empty:
                frame = None
    if frame is None and note and len(errors) < 8:
        errors.append(f"{sym} {tf}: {note}")
    if frame is not None and tf in ("M15", "M5"):
        frame = frame.assign(Datetime=frame.index)
        frame.attrs["data_basis"] = "twelve"
    _TWELVE_CACHE[key] = frame
    return frame


def _twelve_frames(pool, symbols, tf, end_ts, errors):
    out = {}
    for sym in symbols:
        f = _twelve_frame(pool, sym, tf, end_ts, errors)
        if f is not None:
            out[sym] = f
    return out


def _assemble_m15_from_twelve_m5(m15_frame, m5_frame, slot):
    """Fill ONLY the missing bars of the consumed 32-bar M15
    window (ending at the entry bar, slot - 15m) from Twelve
    M5 bars: open=first, high=max, low=min, close=last. Real
    M15 bars always win. Returns (frame, n_assembled)."""
    entry_bar = slot - pd.Timedelta(minutes=15)
    window = pd.date_range(end=entry_bar, periods=32,
                           freq="15min")
    have = set(m15_frame.index) if m15_frame is not None else set()
    missing = [t for t in window if t not in have]
    if not missing or m5_frame is None:
        return m15_frame, 0
    rows = {}
    for t in missing:
        parts = [t + pd.Timedelta(minutes=5 * k) for k in range(3)]
        if all(p in m5_frame.index for p in parts):
            seg = m5_frame.loc[parts]
            rows[t] = {"Open": float(seg["Open"].iloc[0]),
                       "High": float(seg["High"].max()),
                       "Low": float(seg["Low"].min()),
                       "Close": float(seg["Close"].iloc[-1]),
                       "Volume": float(seg["Volume"].sum())
                       if "Volume" in seg else 0.0}
    if not rows:
        return m15_frame, 0
    add = pd.DataFrame.from_dict(rows, orient="index")
    add.index = pd.DatetimeIndex(add.index)
    if m15_frame is None:
        out = add.sort_index()
    else:
        base = m15_frame.drop(columns=["Datetime"],
                              errors="ignore")
        out = pd.concat([base, add]).sort_index()
        out = out.loc[~out.index.duplicated(keep="first")]
    out = out.assign(Datetime=out.index)
    out.attrs["data_basis"] = "assembled"
    return out, len(rows)


# ------------------------------------------------------------------
# Raw stateless evaluation helpers
# ------------------------------------------------------------------

def _pip_of(sym: str) -> float:
    return 0.01 if sym.endswith("JPY") else 0.0001


def _basis_label(basis: str) -> str:
    return {"fallback": "fallback data",
            "assembled": "assembled-from-M5 data",
            "twelve": "Twelve Data"}.get(basis, "")


def _stateless_entries(mod, month, frames, slot, m15_frames=None,
                       m5_frames=None):
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
                open_symbols=(), m5_frames=m5_frames)
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
# CHECK side — raw calculation on Twelve Data candles for the slot
# ------------------------------------------------------------------

def replay_check(month: int, slot, state=None) -> dict:
    system, mod = _month_module(month)
    symbols = list(mod.SYMBOLS)
    slot = pd.Timestamp(slot)
    sig = slot - pd.Timedelta(hours=1, minutes=30)
    ent = slot - pd.Timedelta(minutes=30)
    entry_bar = slot - pd.Timedelta(minutes=15)
    try:
        pool = _twelve_pool(state)
    except Exception as exc:
        return {"status": "DATA ERROR",
                "missing": f"Twelve Data key pool unavailable: "
                           f"{exc}",
                "basis": "twelve"}
    errors: list = []
    frames = _twelve_frames(pool, symbols, "H1", ent, errors)
    h1_missing = [s for s in symbols
                  if s not in frames or sig not in frames[s].index
                  or ent not in frames[s].index]
    if h1_missing:
        note = f"; {errors[0]}" if errors else ""
        return {"status": "DATA ERROR",
                "missing": (f"H1 sig/entry candles from Twelve "
                            f"Data for {len(h1_missing)} symbols: "
                            f"{', '.join(h1_missing)}{note}"),
                "basis": "twelve"}

    m15_frames = _twelve_frames(pool, symbols, "M15", entry_bar,
                                errors)
    m5_frames = _twelve_frames(pool, symbols, "M5", entry_bar,
                               errors)
    basis = "twelve"
    bars = _m15_bars(mod, m15_frames)
    _ok, m15_missing = _window_ok(bars, slot)
    absent = [s for s in symbols if s not in bars]
    bad = sorted(set(m15_missing) | set(absent))
    if bad:
        # Gaps only: assemble the missing M15 window bars from
        # the Twelve M5 bars; real M15 always wins.
        for sym in bad:
            filled, n_asm = _assemble_m15_from_twelve_m5(
                m15_frames.get(sym), m5_frames.get(sym), slot)
            if n_asm:
                m15_frames[sym] = filled
                basis = "assembled"
        bars = _m15_bars(mod, m15_frames)
        _ok, m15_missing = _window_ok(bars, slot)
        absent = [s for s in symbols if s not in bars]
        bad = sorted(set(m15_missing) | set(absent))
    if bad:
        note = f"; {errors[0]}" if errors else ""
        return {"status": "DATA ERROR",
                "missing": (f"M15 entry bar / 32-bar window from "
                            f"Twelve Data for {len(bad)} symbols: "
                            f"{', '.join(bad)}{note}"),
                "basis": "twelve"}

    dealt = _stateless_entries(mod, month, frames, slot,
                               m15_frames=m15_frames,
                               m5_frames=m5_frames)
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
# PRECHECK side — Twelve H1 as of check - 15 min
# ------------------------------------------------------------------

def replay_precheck(month: int, slot, state=None) -> dict:
    """Precheck inputs at the cutoff (check - 15 min): the H1
    sig frame — the sig bar completes by check - 30 — and the
    history before it, loaded from Twelve Data. Only candles
    COMPLETED by the cutoff count. The entry candle is NOT
    required: a precheck never waits for it (user rule
    2026-11-26); the combined evaluation synthesizes it from
    the signal close, exactly as in the proven true-precheck
    walk."""
    system, mod = _month_module(month)
    symbols = list(mod.SYMBOLS)
    slot = pd.Timestamp(slot)
    cutoff = slot - pd.Timedelta(minutes=15)
    sig = slot - pd.Timedelta(hours=1, minutes=30)
    try:
        pool = _twelve_pool(state)
    except Exception as exc:
        return {"status": "DATA ERROR",
                "missing": f"Twelve Data key pool unavailable: "
                           f"{exc}"}
    errors: list = []
    full = _twelve_frames(pool, symbols, "H1", sig, errors)
    h1 = {}
    for sym, f in full.items():
        keep = f.index + pd.Timedelta(minutes=60) <= cutoff
        h1[sym] = f[keep]
    h1_missing = [s for s in symbols
                  if s not in h1 or sig not in h1[s].index]
    if h1_missing:
        note = f"; {errors[0]}" if errors else ""
        return {"status": "DATA ERROR",
                "missing": (
                    f"H1 sig bar {sig} UTC from Twelve Data "
                    f"missing for {len(h1_missing)} symbols: "
                    f"{', '.join(h1_missing)}{note}")}

    # Evaluate statelessly on the cutoff-truncated H1 frames
    # via the combined path (m15_frames=None): the entry
    # candle is synthesized from the signal close.
    dealt = _stateless_entries(mod, month, h1, slot)
    picks = [{"symbol": r["symbol"], "direction": r["direction"],
              "entry_px": float(r["entry_px"])} for r in dealt]
    return {"status": "OK" if picks else "NO SIGNAL",
            "picks": picks}


# ------------------------------------------------------------------
# Compare to the past — read-only, AFTER the calculation
# ------------------------------------------------------------------

def _recorded_past(mod, slot):
    """The slot's recorded result from the walk ledger
    (read-only): {"kind": "pick", ...} / {"kind": "no_signal"}
    / {"kind": "none"}. Never used by the calculation."""
    try:
        form = mod.load_state_form()
        delivered = getattr(form, "delivered", []) or []
        processed = getattr(form, "processed", []) or []
    except Exception:
        return {"kind": "none"}
    slot = pd.Timestamp(slot)
    for r in delivered:
        try:
            if pd.Timestamp(r["check"]) == slot:
                return {"kind": "pick",
                        "symbol": r["symbol"],
                        "direction": r["direction"],
                        "entry_px": float(r["entry_px"])}
        except Exception:
            continue
    for p in processed:
        try:
            if pd.Timestamp(p) == slot:
                return {"kind": "no_signal"}
        except Exception:
            continue
    return {"kind": "none"}


def _compare(check: dict, past: dict) -> str:
    if check["status"] == "DATA ERROR":
        return "Not compared — the calculation did not run."
    calc = check["picks"][0] if check.get("picks") else None
    if past["kind"] == "none":
        return ("No recorded result for this slot — nothing "
                "to compare.")
    if past["kind"] == "pick":
        recorded = (f"{past['symbol']} {past['direction']} @ "
                    f"{past['entry_px']:.5f}")
        if calc is None:
            return (f"DIFFERENT — recorded {recorded}; the "
                    f"Twelve Data calculation gives NO SIGNAL.")
        if (calc["symbol"] == past["symbol"]
                and calc["direction"] == past["direction"]):
            return (f"MATCH — the Twelve Data calculation "
                    f"reproduces the recorded pick {recorded} "
                    f"(entry may differ by a few pips: Twelve "
                    f"vs Dukascopy prices).")
        return (f"DIFFERENT — recorded {recorded}; the Twelve "
                f"Data calculation gives {calc['symbol']} "
                f"{calc['direction']} @ {calc['entry_px']:.5f}.")
    # past == no_signal
    if calc is None:
        return "MATCH — recorded NO SIGNAL, and the Twelve " \
               "Data calculation also gives NO SIGNAL."
    return (f"DIFFERENT — recorded NO SIGNAL; the Twelve Data "
            f"calculation gives {calc['symbol']} "
            f"{calc['direction']} @ {calc['entry_px']:.5f}.")


def replay_slot(d: _dt.date, slot, state=None) -> dict:
    check = replay_check(d.month, slot, state=state)
    precheck = replay_precheck(d.month, slot, state=state)
    _system, mod = _month_module(d.month)
    past = _recorded_past(mod, slot)
    return {"date": str(d), "slot": str(slot),
            "check": check, "precheck": precheck,
            "past": past, "compare": _compare(check, past)}


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
        "Calculated from Twelve Data candles loaded for the "
        "picked time — no memory used. After calculating, the "
        "result is compared with the recorded past result.</div>",
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
        with st.spinner("Calculating — loading this slot's "
                        "candles from Twelve Data and running "
                        "the raw calculation…"):
            try:
                st.session_state["replay_result"] = replay_slot(
                    d, slot, state=st.session_state)
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

    past = res.get("past") or {"kind": "none"}
    st.markdown("**COMPARE TO PAST**")
    if past["kind"] == "pick":
        st.markdown(
            f"Recorded at the time: **{past['symbol']} "
            f"{past['direction']} @ {past['entry_px']:.5f}**")
    elif past["kind"] == "no_signal":
        st.markdown("Recorded at the time: **NO SIGNAL**")
    else:
        st.markdown("Recorded at the time: — (no recorded "
                    "result for this slot)")
    if res.get("compare"):
        st.markdown(res["compare"])

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
