"""Twelve Data API Memory Building (user order 2026-11-27).

A section rendered immediately after Replay. The user picks a
month + year and clicks Start: the app downloads that month's
candles (H1 / M15 / M5, all 28 symbols, plus the lead-in the
400-bar windows need) from the Twelve Data API, walks the
month's own cycle over them slot by slot -- the same stateful
walk the builders run, with the module's state form pointed at
a throwaway file, so the app's live ledgers are never touched
-- then compares the built memory against the stored past for
that month-year and offers the result as an XLSX download (and
the walked state as JSON).

Data basis is Twelve Data throughout. Hardening (user order
2026-11-28): a build must NEVER die mid-run on a data hole.
Every slot is gated 28/28, but an incomplete slot is first
HEALED (one fresh Twelve re-fetch of the missing window, then
M5->M15 assembly for M15 gaps); a slot that still cannot be
completed is recorded DATA ERROR with its reason and the walk
CONTINUES with the next slot in order — the same pattern as
the market-closed skip. (The live check/precheck gates
elsewhere in the app are unchanged; this applies only to
this memory-building section.) Nothing here reads the
Dukascopy store for the calculation; the stored past is read
only AFTER the walk, for the comparison.
"""
import io
import json
import os
import tempfile
import time
import datetime as dt

import pandas as pd

from core.replay_section import (
    _month_module, _twelve_pool, _twelve_fetch_values,
    _m15_bars, _window_ok, _assemble_m15_from_twelve_m5)
from core.check_candle_runtime import normalize_ohlc

_MONTH_NAMES = ["January", "February", "March", "April", "May",
                "June", "July", "August", "September", "October",
                "November", "December"]
_TF_STEP_MIN = {"H1": 60, "M5": 5, "M15": 15}
_TF_INTERVAL = {"H1": "1h", "M15": "15min", "M5": "5min"}
_MAX_BARS_PER_CALL = 5000


def _slots_for_month(mod, year, month):
    hours = None
    for k, v in vars(mod).items():
        if k.endswith("_CHECK_HOURS"):
            hours = v
            break
    out = []
    d = dt.date(year, month, 1)
    while d.month == month:
        if d.weekday() < 5:
            for h in hours:
                out.append(pd.Timestamp(
                    dt.datetime(d.year, d.month, d.day, int(h), 30)))
        d += dt.timedelta(days=1)
    return out


def _feed_ended_or_continues(idx, point, end_point):
    """Closed-market signature for one symbol's series at a
    slot: either the series continues past the slot (a holiday
    inside the window), or it ends within 4 days before the
    slot without trading past it — the feed stops at a
    year-end close, possibly right AT the slot's own stamps
    (e.g. Twelve H1 whose last Dec 31 bar is the 12:00 or
    13:00 stamp itself, with the other stamp missing).
    Anything else is a data hole, not a closure."""
    if len(idx) == 0:
        return False
    last = idx.max()
    if last > end_point:
        return True
    return bool(end_point - pd.Timedelta(days=4) <= last
                <= end_point)


def _fetch_window(pool, sym, tf, start_ts, end_ts, errors):
    """One symbol/timeframe's full window from Twelve Data,
    fetched backwards in <=5000-bar calls. Returns a normalized
    frame (Datetime column + data_basis for M15/M5, mirroring
    the replay fetcher) or None. Requests are paced (2 s
    between calls) so the download stays under the plan's
    per-minute credit limit instead of bursting past it —
    slower, but no limit failures (user request 2026-11-27)."""
    interval = _TF_INTERVAL[tf]
    step = _TF_STEP_MIN[tf]
    chunks = []
    end = pd.Timestamp(end_ts)
    start = pd.Timestamp(start_ts)
    while end > start:
        time.sleep(2.0)
        values, note = _twelve_fetch_values(
            pool, sym, interval, _MAX_BARS_PER_CALL, end,
            step_minutes=step)
        if not values:
            if note and len(errors) < 8:
                errors.append(f"{sym} {tf}: {note}")
            return None
        raw = pd.DataFrame(values)
        frame = normalize_ohlc(raw, 1)
        if frame is None or frame.empty:
            return None
        chunks.append(frame)
        earliest = frame.index.min()
        if earliest <= start:
            break
        end = earliest - pd.Timedelta(minutes=step)
        if len(chunks) > 6:
            break
    if not chunks:
        return None
    out = pd.concat(chunks)
    out = out.loc[~out.index.duplicated(keep="first")]
    out = out.sort_index()
    out = out.loc[start:end_ts]
    if tf in ("M15", "M5"):
        out = out.assign(Datetime=out.index)
        out.attrs["data_basis"] = "twelve"
    return out


def _merge_frames(old, fresh):
    """Merge a fresh re-fetch into a downloaded frame: fresh
    bars win on shared stamps, the result is sorted and
    deduped, with the Datetime column the consumers read."""
    if old is None or not len(old):
        out = fresh
    elif fresh is None or not len(fresh):
        out = old
    else:
        out = pd.concat([old, fresh])
        out = out.loc[~out.index.duplicated(keep="last")]
        out = out.sort_index()
    if out is not None and len(out):
        out = out.assign(Datetime=out.index)
    return out


def _refetch_window(pool, sym, tf, end_ts, bars=500):
    """One FRESH Twelve window for ONE symbol/timeframe ending
    at end_ts — the walk's second chance for a single-symbol
    gap (fix 2026-11-27): the month download fetches each
    series once, so a hole in that one response (e.g. EURUSD
    M15 at 2025-11-03 17:30, where the series the download
    returned was missing the entry window while other feeds
    carry it) otherwise reaches the walk unrepaired. Returns a
    normalized frame like _fetch_window's, or None."""
    interval = _TF_INTERVAL[tf]
    step = _TF_STEP_MIN[tf]
    values, _note = _twelve_fetch_values(
        pool, sym, interval, bars, pd.Timestamp(end_ts),
        step_minutes=step)
    if not values:
        return None
    frame = normalize_ohlc(pd.DataFrame(values), 1)
    if frame is None or frame.empty:
        return None
    frame = frame.loc[:pd.Timestamp(end_ts)]
    if frame.empty:
        return None
    if tf in ("M15", "M5"):
        frame = frame.assign(Datetime=frame.index)
        frame.attrs["data_basis"] = "twelve"
    return frame


class BuildInterrupted(Exception):
    """Raised only by the explicit _interrupt_after_walked
    test/stop hook in build_memory — the simulated crash.
    Data errors never raise it; they are recorded per slot."""


_PROGRESS_DIR = "data/twelve_memory_progress"


def _progress_rel(cycle, year):
    return f"{_PROGRESS_DIR}/{cycle}_{year}.json"


def _progress_local_path(cycle, year):
    here = os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))
    return os.path.join(here, *_progress_rel(cycle, year
                                              ).split("/"))


def load_progress_record(cycle, year, try_github=True):
    """The resumable progress record for a month-year: the
    local copy first, else restored from GitHub through the
    save-back machinery (and cached locally), exactly like
    the other synced files. Returns the record dict or None.
    Never raises."""
    path = _progress_local_path(cycle, year)
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    if try_github:
        try:
            from core.data import github_saveback as _gsb
            token = _gsb._secret_token()
            if token:
                raw = _gsb._fetch_bytes(
                    _progress_rel(cycle, year), token)
                if raw:
                    rec = json.loads(raw.decode("utf-8"))
                    os.makedirs(os.path.dirname(path),
                                exist_ok=True)
                    with open(path, "wb") as f:
                        f.write(raw)
                    return rec
        except Exception:
            pass
    return None


def _past_ledger(cycle, year, month):
    """The stored past for this month-year, read AFTER the walk
    for comparison only: the 2026 walk ledgers, else the
    historical ledgers (2015-2025) the user uploaded."""
    here = os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))
    cands = [os.path.join(
        here, "data", "walk_ledgers_hist",
        f"{cycle}_{year}.json")]
    if year == 2026:
        cands.insert(0, os.path.join(
            here, "data", "walk_ledgers_new8", f"{cycle}.json"))
    for p in cands:
        if os.path.exists(p):
            try:
                with open(p) as f:
                    return json.load(f), os.path.basename(p)
            except Exception:
                continue
    return None, None


def _compare(built_state, past):
    def norm(ts):
        return str(ts).replace("T", " ")[:19]

    def picks(state):
        out = {}
        for d in state.get("delivered", []):
            out[norm(d["check"])] = (
                d["symbol"], d["direction"], float(d["entry_px"]))
        return out

    mp = {norm(t) for t in built_state.get("processed", [])}
    rp = {norm(t) for t in past.get("processed", [])}
    md, rd = picks(built_state), picks(past)
    shared = sorted(mp & rp)
    match = differ = only_built = only_past = 0
    rows = []
    for s in shared:
        a, b = md.get(s), rd.get(s)
        if a and b:
            pip = 0.01 if "JPY" in a[0] else 0.0001
            if a[0] == b[0] and a[1] == b[1] and \
                    abs(a[2] - b[2]) <= 0.5 * pip:
                match += 1
                rows.append((s, a, b, "MATCH"))
            else:
                differ += 1
                rows.append((s, a, b, "DIFFERENT"))
        elif a:
            only_built += 1
            rows.append((s, a, None, "ONLY IN TWELVE BUILD"))
        elif b:
            only_past += 1
            rows.append((s, None, b, "ONLY IN STORED PAST"))
    sim = (100.0 * match / len(shared)) if shared else 0.0
    return {"shared_slots": len(shared), "match": match,
            "differ": differ, "only_built": only_built,
            "only_past": only_past, "similarity_pct": sim,
            "rows": rows}


def _xlsx_bytes(month, year, cycle, built_state, compare,
                past_name, skipped=(), note=None,
                skip_reasons=None, healed=0):
    buf = io.BytesIO()
    delivered = built_state.get("delivered", [])
    processed = [str(t).replace("T", " ")[:19]
                 for t in built_state.get("processed", [])]
    skipped = [str(t).replace("T", " ")[:19] for t in skipped]
    by_slot = {}
    for d in delivered:
        by_slot[str(d["check"]).replace("T", " ")[:19]] = d
    summary = pd.DataFrame([
        ("Month", f"{_MONTH_NAMES[month - 1]} {year}"),
        ("Cycle (system)", cycle),
        ("Data basis", "Twelve Data API (downloaded at build "
                       "time)"),
        ("Slots walked", len(processed)),
        ("Slots skipped — DATA ERROR", len(skipped)),
        ("Slots healed (re-fetch / M5 assembly)", healed),
        ("Picks delivered", len(delivered)),
        ("Result note", note or "complete run"),
        ("Compared against", past_name or "no stored past found"),
        ("Shared slots", compare["shared_slots"] if compare
         else ""),
        ("Matching picks", compare["match"] if compare else ""),
        ("Different picks", compare["differ"] if compare
         else ""),
        ("Similarity %", (round(compare["similarity_pct"], 1)
                          if compare else "")),
    ], columns=["Item", "Value"])
    picks = pd.DataFrame([{
        "check_utc": str(d["check"]).replace("T", " "),
        "symbol": d["symbol"], "direction": d["direction"],
        "entry_px": d["entry_px"], "tp_pips": d.get("tp_pips"),
        "sl_pips": d.get("sl_pips"),
        "exit_time_utc": str(d.get("exit_time", "")).replace(
            "T", " "),
        "mult": d.get("mult"), "layer": d.get("layer"),
    } for d in delivered])
    slots = pd.DataFrame([{
        "slot_utc": s,
        "pick": (f"{by_slot[s]['symbol']} "
                 f"{by_slot[s]['direction']} "
                 f"@{by_slot[s]['entry_px']}"
                 if s in by_slot else "—"),
    } for s in processed] + [{
        "slot_utc": s,
        "pick": ("DATA ERROR — "
                 f"{(skip_reasons or {}).get(s, 'market closed')}"),
    } for s in skipped]).sort_values("slot_utc")
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        summary.to_excel(xw, sheet_name="Summary", index=False)
        picks.to_excel(xw, sheet_name="Picks", index=False)
        slots.to_excel(xw, sheet_name="Slots", index=False)
        if compare:
            comp = pd.DataFrame([{
                "slot_utc": s,
                "twelve_build": (f"{a[0]} {a[1]} @{a[2]}"
                                 if a else "—"),
                "stored_past": (f"{b[0]} {b[1]} @{b[2]}"
                                if b else "—"),
                "result": r,
            } for s, a, b, r in compare["rows"]])
            comp.to_excel(xw, sheet_name="Compare", index=False)
    return buf.getvalue()


def build_memory(month, year, state=None, progress=None,
                 resume=True, _interrupt_after_walked=None):
    """Download the month's candles from Twelve Data and walk
    its cycle over them. progress(frac, text) is called as work
    advances. Returns a result dict. Hardening (2026-11-28):
    the walk never stops early on a data hole — an incomplete
    slot is healed (fresh re-fetch, then M5->M15 assembly) or
    recorded DATA ERROR with its reason in skip_reasons /
    slot_errors while the walk continues in order, so the
    result always covers the whole month: walked N, healed H,
    skipped S. A DATA ERROR status is returned only when the
    build cannot start at all (no slots, no key pool) or the
    walk machinery itself produced no state."""
    def report(frac, text):
        if progress is not None:
            progress(frac, text)

    system, mod = _month_module(month)
    cycle = system
    symbols = list(mod.SYMBOLS)
    slots = _slots_for_month(mod, year, month)
    if not slots:
        return {"status": "DATA ERROR",
                "missing": "no check slots in that month"}
    if month == 1:
        start = pd.Timestamp(dt.date(year - 1, 12, 10))
    else:
        start = pd.Timestamp(dt.date(year, month - 1, 10))
    last_day = slots[-1].date()
    end = pd.Timestamp(dt.datetime(last_day.year, last_day.month,
                                   last_day.day, 19, 0))

    try:
        pool = _twelve_pool(state)
    except Exception as exc:
        return {"status": "DATA ERROR",
                "missing": f"Twelve Data key pool unavailable: "
                           f"{exc}"}

    # ---- Resume (user order 2026-11-28): a saved progress
    # record for this month-year means the build continues
    # from where it stopped — already-walked slots are not
    # re-walked and recorded DATA ERROR slots stay recorded.
    events: list = []
    resume_rec = None
    done_slots = set()
    if resume:
        try:
            rec = load_progress_record(cycle, year)
        except Exception:
            rec = None
        if rec and not rec.get("complete") \
                and int(rec.get("year", 0)) == int(year) \
                and int(rec.get("month", 0)) == int(month) \
                and rec.get("state"):
            resume_rec = rec
            done_slots = set(rec.get("processed", [])) \
                | set(rec.get("skipped", []))
            events.append(
                f"↻ Resuming from saved progress: "
                f"{len(done_slots)} of {len(slots)} slots "
                f"already built "
                f"({len(rec.get('processed', []))} walked, "
                f"{len(rec.get('skipped', []))} recorded "
                f"DATA ERROR) — continuing in order.")

    # ---- Phase 1: download the month (0% -> 30%) ----
    # Hardening 2026-11-28: a missing series no longer aborts
    # the build. Each missing series gets ONE retry fetch; a
    # series still missing becomes an empty frame, so every
    # slot that needs it goes through the walk's heal-then-
    # skip path and is recorded DATA ERROR individually while
    # the rest of the month still builds.
    errors: list = []
    data = {tf: {} for tf in ("H1", "M15", "M5")}
    total = len(symbols) * 3
    done = 0
    for tf in ("H1", "M15", "M5"):
        for sym in symbols:
            try:
                frame = _fetch_window(pool, sym, tf, start, end,
                                      errors)
            except Exception as exc:
                errors.append(f"{sym} {tf}: {exc}")
                frame = None
            if frame is not None:
                data[tf][sym] = frame
            done += 1
            report(0.30 * done / total,
                   f"Downloading Twelve Data candles: {sym} {tf} "
                   f"({done}/{total})")
    download_missing = []
    for tf in ("H1", "M15", "M5"):
        for sym in symbols:
            if sym in data[tf]:
                continue
            try:
                frame = _fetch_window(pool, sym, tf, start, end,
                                      errors)
            except Exception:
                frame = None
            if frame is not None and len(frame):
                data[tf][sym] = frame
                continue
            download_missing.append(f"{sym} {tf}")
            empty = pd.DataFrame(
                {"Open": pd.Series(dtype=float),
                 "High": pd.Series(dtype=float),
                 "Low": pd.Series(dtype=float),
                 "Close": pd.Series(dtype=float),
                 "Volume": pd.Series(dtype=float)},
                index=pd.DatetimeIndex([]))
            if tf in ("M15", "M5"):
                empty = empty.assign(Datetime=empty.index)
            data[tf][sym] = empty

    if download_missing:
        events.append(
            f"⚠ Download incomplete for "
            f"{len(download_missing)} symbol/timeframes after "
            f"one retry ({', '.join(download_missing[:10])}) — "
            f"affected slots will be healed per slot or "
            f"recorded DATA ERROR; the build continues.")

    # ---- Phase 2: the walk (30% -> 95%) ----
    import core.signal_mode as sm
    tmpdir = tempfile.mkdtemp(prefix="twelve_memory_")
    state_path = os.path.join(
        tmpdir, f"{cycle}_{year}-{month:02d}.json")
    prev_form = getattr(mod, "_STATE", None)
    prev_saveback = sm._saveback_ledgers
    built_state = None
    skipped = []
    skip_reasons = {}
    healed_slots = []
    if resume_rec:
        skipped = [str(s) for s in resume_rec.get("skipped",
                                                  [])]
        skip_reasons = {str(k): v for k, v in
                        (resume_rec.get("skip_reasons")
                         or {}).items()}
        healed_slots = [str(s) for s in
                        resume_rec.get("healed_slots", [])]
        events = list(resume_rec.get("events", [])) + events

    _push_gate = {"last": 0.0}

    def _save_progress(complete=False, force_push=False):
        """Persist the resumable progress record: local file
        synchronously, GitHub via the save-back machinery on
        a daemon thread (hash-gated there; throttled here to
        one push per 20 s plus the final save). The record
        MAY be overwritten as progress advances — it is a
        work record, distinct from the finished hist archive.
        Never raises."""
        try:
            state_now = None
            if os.path.exists(state_path):
                with open(state_path) as f:
                    state_now = json.load(f)
            rec = {
                "cycle": cycle, "year": int(year),
                "month": int(month),
                "total_slots": len(slots),
                "processed": (state_now or {}).get(
                    "processed", []),
                "skipped": list(skipped),
                "skip_reasons": dict(skip_reasons),
                "healed_slots": list(healed_slots),
                "events": list(events),
                "state": state_now,
                "complete": bool(complete),
                "updated_at_utc": dt.datetime.now(
                    dt.timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"),
            }
            path = _progress_local_path(cycle, year)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(rec, f, indent=1)
            now = time.time()
            if force_push or now - _push_gate["last"] >= 20:
                _push_gate["last"] = now
                import threading

                def _push(p=path, r=_progress_rel(cycle, year)):
                    try:
                        from core.data import github_saveback \
                            as _gsb
                        _gsb.saveback_file(p, r)
                    except Exception:
                        pass

                threading.Thread(target=_push,
                                 daemon=True).start()
        except Exception:
            pass

    def _record_skip(slot, reason):
        skipped.append(str(slot))
        skip_reasons[str(slot)] = reason
        events.append(
            f"⛔ {slot:%Y-%m-%d %H:%M} UTC — DATA ERROR: "
            f"{reason} (recorded; build continues)")
        report(0.30 + 0.65 * (slots.index(slot) + 1) / len(slots),
               f"Walking {_MONTH_NAMES[month - 1]} {year}: "
               f"slot {slots.index(slot) + 1}/{len(slots)} "
               f"({slot:%Y-%m-%d %H:%M} UTC) — DATA ERROR "
               f"({reason}), skipped")
        _save_progress()

    walked_this_run = 0
    try:
        sm._saveback_ledgers = lambda: None
        if resume_rec and resume_rec.get("state"):
            with open(state_path, "w") as f:
                json.dump(resume_rec["state"], f)
        mod._STATE = mod.load_state_form(path=state_path)
        for i, slot in enumerate(slots):
            if str(slot) in done_slots:
                report(0.30 + 0.65 * (i + 1) / len(slots),
                       f"Walking {_MONTH_NAMES[month - 1]} "
                       f"{year}: slot {i + 1}/{len(slots)} "
                       f"({slot:%Y-%m-%d %H:%M} UTC) — already "
                       f"built (saved progress)")
                continue
            sig = slot - pd.Timedelta(hours=1, minutes=30)
            ent = slot - pd.Timedelta(minutes=30)
            entry_bar = slot - pd.Timedelta(minutes=15)
            frames = {}
            for sym in symbols:
                f = data["H1"][sym]
                f = f.loc[:ent]
                if len(f) > 450:
                    f = f.iloc[-450:]
                frames[sym] = f
            h1_missing = [s for s in symbols
                          if sig not in frames[s].index
                          or ent not in frames[s].index]
            if h1_missing:
                # Heal first (2026-11-28): ONE fresh Twelve
                # re-fetch of each missing symbol's H1 window
                # ending at the entry stamp, merged into the
                # month data (later slots benefit too).
                for sym in h1_missing:
                    try:
                        fresh = _refetch_window(pool, sym, "H1",
                                                ent)
                    except Exception:
                        fresh = None
                    if fresh is not None and len(fresh):
                        data["H1"][sym] = _merge_frames(
                            data["H1"].get(sym), fresh)
                frames = {}
                for sym in symbols:
                    f = data["H1"][sym].loc[:ent]
                    if len(f) > 450:
                        f = f.iloc[-450:]
                    frames[sym] = f
                still = [s for s in symbols
                         if sig not in frames[s].index
                         or ent not in frames[s].index]
                if not still:
                    healed_slots.append(str(slot))
                    events.append(
                        f"🩹 {slot:%Y-%m-%d %H:%M} UTC — H1 hole "
                        f"healed by a fresh Twelve re-fetch; "
                        f"slot walked.")
                    _save_progress()
                    h1_missing = []
                else:
                    h1_missing = still
            if h1_missing and len(h1_missing) == len(symbols) \
                    and all(_feed_ended_or_continues(
                        data["H1"][s].index, sig, ent)
                            for s in symbols):
                # Market closed (user ruling 2026-11-27): the
                # candles do not exist, but the downloaded data
                # continues past the slot. Record DATA ERROR
                # for the slot and walk on.
                _record_skip(
                    slot, "market closed — no H1 candles exist "
                          "for this slot; data continues past it")
                continue
            if h1_missing:
                # Heal failed: record this slot DATA ERROR and
                # CONTINUE with the next slot (2026-11-28) —
                # never abort the whole run for one slot.
                _record_skip(
                    slot,
                    f"H1 sig/entry candles missing for "
                    f"{len(h1_missing)} symbols after re-fetch: "
                    f"{', '.join(h1_missing)}")
                continue
            m15_frames = {}
            m5_frames = {}
            for sym in symbols:
                f15 = data["M15"][sym].loc[:entry_bar]
                if len(f15) > 400:
                    f15 = f15.iloc[-400:]
                m15_frames[sym] = f15
                f5 = data["M5"][sym].loc[:entry_bar]
                if len(f5) > 400:
                    f5 = f5.iloc[-400:]
                m5_frames[sym] = f5
            bars = _m15_bars(mod, m15_frames)
            _ok, m15_missing = _window_ok(bars, slot)
            absent = [s for s in symbols if s not in bars]
            bad = sorted(set(m15_missing) | set(absent))
            m15_was_bad = bool(bad)
            if bad:
                for sym in bad:
                    filled, n_asm = _assemble_m15_from_twelve_m5(
                        m15_frames.get(sym), m5_frames.get(sym),
                        slot)
                    if n_asm:
                        m15_frames[sym] = filled
                bars = _m15_bars(mod, m15_frames)
                _ok, m15_missing = _window_ok(bars, slot)
                absent = [s for s in symbols if s not in bars]
                bad = sorted(set(m15_missing) | set(absent))
            if bad:
                # Second chance (fix 2026-11-27): ONE fresh
                # Twelve re-fetch of each bad symbol's M15 + M5
                # window ending at this slot's entry bar — the
                # month download fetched each series once, so a
                # hole in that single response (the live
                # 2025-11-03 EURUSD case) otherwise stops the
                # build unrepaired. Fresh bars are merged into
                # the month data (later slots benefit too), the
                # slot frames are rebuilt, and the M5->M15
                # assembly runs again. Only a window STILL
                # incomplete after both falls through to the
                # market-closed skip / DATA ERROR stop below.
                for sym in bad:
                    fresh15 = _refetch_window(pool, sym, "M15",
                                              entry_bar)
                    if fresh15 is not None and len(fresh15):
                        data["M15"][sym] = _merge_frames(
                            data["M15"].get(sym), fresh15)
                        f15 = data["M15"][sym].loc[:entry_bar]
                        if len(f15) > 400:
                            f15 = f15.iloc[-400:]
                        m15_frames[sym] = f15
                    fresh5 = _refetch_window(pool, sym, "M5",
                                             slot)
                    if fresh5 is not None and len(fresh5):
                        data["M5"][sym] = _merge_frames(
                            data["M5"].get(sym), fresh5)
                        # The M5 parts of the entry bar itself
                        # live past entry_bar (entry_bar+5/+10),
                        # so the repaired M5 frame is cut at the
                        # slot — the same bound replay_check
                        # fetches M5 with.
                        f5 = data["M5"][sym].loc[:slot]
                        if len(f5) > 400:
                            f5 = f5.iloc[-400:]
                        m5_frames[sym] = f5
                for sym in bad:
                    filled, n_asm = _assemble_m15_from_twelve_m5(
                        m15_frames.get(sym), m5_frames.get(sym),
                        slot)
                    if n_asm:
                        m15_frames[sym] = filled
                bars = _m15_bars(mod, m15_frames)
                _ok, m15_missing = _window_ok(bars, slot)
                absent = [s for s in symbols if s not in bars]
                bad = sorted(set(m15_missing) | set(absent))
            if not bad and m15_was_bad \
                    and str(slot) not in healed_slots:
                healed_slots.append(str(slot))
                events.append(
                    f"🩹 {slot:%Y-%m-%d %H:%M} UTC — M15 window "
                    f"healed (re-fetch / M5 assembly); slot "
                    f"walked.")
                _save_progress()
            if bad:
                if len(bad) == len(symbols) and all(
                        _feed_ended_or_continues(
                            data["M15"][s].index, entry_bar,
                            entry_bar)
                        for s in symbols):
                    # Market closed (user ruling 2026-11-27):
                    # Twelve has H1 bars for the day but no M15
                    # session at all (e.g. Christmas Day), while
                    # the downloaded data continues past the
                    # slot. Record DATA ERROR for the slot and
                    # walk on.
                    _record_skip(
                        slot, "market closed — no M15 session "
                              "for this slot; data continues "
                              "past it")
                    continue
                # Heal failed: record this slot DATA ERROR and
                # CONTINUE with the next slot (2026-11-28) —
                # never abort the whole run for one slot.
                _record_skip(
                    slot,
                    f"M15 entry window incomplete for "
                    f"{len(bad)} symbols after re-fetch + M5 "
                    f"assembly: {', '.join(bad)}")
                continue
            try:
                mod.panel_entries(frames, slot,
                                  m15_frames=m15_frames,
                                  open_symbols=(),
                                  m5_frames=m5_frames)
            except Exception as exc:
                # One slot's evaluation failure must not kill
                # the run either (2026-11-28): record it and
                # walk on in order.
                _record_skip(slot, f"evaluation error: {exc}")
                continue
            walked_this_run += 1
            if walked_this_run % 10 == 0:
                _save_progress()
            if _interrupt_after_walked \
                    and walked_this_run >= _interrupt_after_walked:
                _save_progress(force_push=True)
                raise BuildInterrupted(
                    f"simulated stop after {walked_this_run} "
                    f"walked slots (progress saved)")
            report(0.30 + 0.65 * (i + 1) / len(slots),
                   f"Walking {_MONTH_NAMES[month - 1]} {year}: "
                   f"slot {i + 1}/{len(slots)} "
                   f"({slot:%Y-%m-%d %H:%M} UTC)")
        if os.path.exists(state_path):
            with open(state_path) as f:
                built_state = json.load(f)
    finally:
        sm._saveback_ledgers = prev_saveback
        mod._STATE = prev_form
    if not built_state:
        if skipped and len(skipped) == len(slots):
            # Every slot was recorded DATA ERROR individually
            # (e.g. a whole series missing): the run still
            # completed — return the empty walked state with
            # the full skip record instead of a hard error.
            built_state = {"processed": [], "delivered": []}
        else:
            return {"status": "DATA ERROR",
                    "missing": "the walk produced no state"}

    # ---- Phase 3: compare + files (95% -> 100%) ----
    # The slot loop now always runs to the end of the month
    # (heal-then-skip, 2026-11-28): there is no early stop, so
    # progress truthfully reaches 100% with the end summary
    # naming walked / healed / skipped counts.
    report(0.97, "Comparing against the stored past…")
    past, past_name = _past_ledger(cycle, year, month)
    compare = _compare(built_state, past) if past else None
    slot_errors = [{"slot": s, "reason": skip_reasons[s]}
                   for s in skipped
                   if not skip_reasons.get(
                       s, "").startswith("market closed")]
    walked_n = len(built_state.get("processed", []))
    if slot_errors:
        note = (f"complete run — {walked_n} walked, "
                f"{len(healed_slots)} healed, "
                f"{len(skipped)} skipped as DATA ERROR "
                f"(reasons in the Slots sheet)")
    elif skipped:
        note = (f"complete run — {walked_n} walked, "
                f"{len(healed_slots)} healed, "
                f"{len(skipped)} skipped (market closed)")
    elif healed_slots:
        note = (f"complete run — {walked_n} walked, "
                f"{len(healed_slots)} healed")
    else:
        note = None
    xlsx = _xlsx_bytes(month, year, cycle, built_state, compare,
                       past_name, skipped=skipped,
                       skip_reasons=skip_reasons,
                       healed=len(healed_slots), note=note)
    if slot_errors or skipped:
        report(1.0,
               f"Done — {walked_n} walked, "
               f"{len(healed_slots)} healed, "
               f"{len(skipped)} skipped as DATA ERROR")
    else:
        report(1.0, "Done")
    events.append(
        f"🏁 Build finished: {walked_n} walked, "
        f"{len(healed_slots)} healed, {len(skipped)} skipped "
        f"as DATA ERROR — {walked_n + len(skipped)} of "
        f"{len(slots)} slots processed (100%).")
    _save_progress(complete=True, force_push=True)
    # ---- Persistent memory (user order 2026-11-28): the
    # built month is saved into the GitHub-synced store as
    # data/walk_ledgers_hist/<cycle>_<year>.json, so a month
    # built once is available to every section — but ONLY
    # when the repo does not already hold that month-year;
    # an existing historical ledger is never overwritten.
    # Dormant without the save-back token, like the rest of
    # the save-back. Never raises.
    persistent_status = None
    try:
        from core.data import github_saveback as _gsb_mem
        persistent_status = _gsb_mem.saveback_new_bytes(
            json.dumps(built_state, indent=1).encode("utf-8"),
            f"data/walk_ledgers_hist/{cycle}_{year}.json")
    except Exception:
        persistent_status = None
    return {"status": "OK",
            "missing": None,
            "partial": False,
            "total_slots": len(slots),
            "cycle": cycle,
            "slots": len(built_state.get("processed", [])),
            "skipped": skipped,
            "skip_reasons": skip_reasons,
            "slot_errors": slot_errors,
            "healed": len(healed_slots),
            "healed_slots": healed_slots,
            "events": events,
            "progress_record": _progress_rel(cycle, year),
            "download_missing": download_missing,
            "delivered": len(built_state.get("delivered", [])),
            "state": built_state, "compare": compare,
            "past_name": past_name, "xlsx": xlsx,
            "persistent_status": persistent_status}


def render_twelve_memory_section(st):
    st.markdown("---")
    # Highlighted header (user order 2026-11-28): this
    # section stands out from the others — gradient glass
    # panel, accent glow border, and a HIGHLIGHT badge.
    st.markdown(
        "<div class='fx-accent-glow' style='border:2px solid "
        "#0ea5e9;border-radius:12px;padding:10px 14px;"
        "margin:8px 0 6px 0;background:linear-gradient(90deg,"
        "rgba(14,165,233,.85),rgba(124,58,237,.75));"
        "color:#fff;font-size:18px;font-weight:800;'>"
        "🔷 Twelve Data API Memory Building"
        "<span style='background:#fff;color:#0369a1;"
        "border-radius:999px;padding:2px 9px;font-size:11px;"
        "font-weight:800;margin-left:8px;vertical-align:2px;'>"
        "⭐ HIGHLIGHT</span></div>",
        unsafe_allow_html=True)
    st.caption(
        "Pick a month and year, then Start: the app downloads "
        "that month's candles (H1 / M15 / M5, 28 symbols) from "
        "the Twelve Data API, walks the month's cycle over them "
        "to build its memory, compares the result against the "
        "stored past, and gives you an Excel (XLSX) download. "
        "Calculation data: Twelve Data only. The app's live "
        "memory is not touched. A full month takes a while — "
        "keep this tab open and watch the progress bar.")
    c1, c2 = st.columns(2)
    with c1:
        month_name = st.selectbox(
            "Month (cycle)", _MONTH_NAMES,
            index=11, key="twmem_month")
    with c2:
        year = st.selectbox(
            "Year", list(range(2026, 2014, -1)),
            index=1, key="twmem_year")
    month = _MONTH_NAMES.index(month_name) + 1
    store_key = f"twmem_result_{year}_{month}"
    # Saved-progress state (user order 2026-11-28): a partial
    # progress record for the chosen month-year — local copy
    # checked every render (cheap), GitHub restore attempted
    # once per session per month-year — readies the
    # Recalculate (resume) button.
    _cycle_name = _month_module(month)[0]
    _rec = load_progress_record(_cycle_name, int(year),
                                try_github=False)
    _gh_key = f"twmem_progress_checked_{_cycle_name}_{year}"
    if _rec is None and not st.session_state.get(_gh_key):
        st.session_state[_gh_key] = True
        _rec = load_progress_record(_cycle_name, int(year),
                                    try_github=True)
    _partial_rec = (_rec if _rec and not _rec.get("complete")
                    else None)
    if _partial_rec:
        _done_n = len(_partial_rec.get("processed", [])) \
            + len(_partial_rec.get("skipped", []))
        st.info(
            f"💾 **Saved progress found — {_done_n} of "
            f"{_partial_rec.get('total_slots', '?')} slots "
            f"already built** for "
            f"{_MONTH_NAMES[month - 1]} {year}. Start or "
            f"Recalculate continues from there — finished "
            f"slots are not re-walked and recorded DATA ERROR "
            f"slots stay recorded.")

    def _run_build():
        bar = st.progress(0.0)
        note = st.empty()

        def _prog(frac, text):
            bar.progress(min(max(float(frac), 0.0), 1.0))
            note.caption(
                f"{text} — **{int(round(100 * frac))}%**")

        with st.spinner("Building memory from Twelve Data…"):
            _res = build_memory(month, int(year),
                                state=st.session_state,
                                progress=_prog)
        st.session_state[store_key] = _res
        st.session_state.pop(_gh_key, None)

    bc1, bc2 = st.columns(2)
    with bc1:
        if st.button("▶ Start building memory (Twelve Data)",
                     key="twmem_start"):
            _run_build()
    with bc2:
        if _partial_rec and st.button(
                "↻ Recalculate (resume)",
                key="twmem_resume"):
            _run_build()
    result = st.session_state.get(store_key)
    if not result:
        return
    comp = result.get("compare")
    if result.get("status") != "OK":
        st.error(f"DATA ERROR — {result.get('missing', '')}")
        if not result.get("xlsx"):
            return
        st.warning(
            f"**Partial result — as far as the build got.** "
            f"{result['slots']} of "
            f"{result.get('total_slots', '?')} slots walked, "
            f"{result['delivered']} picks delivered, before "
            f"the error above. The table and downloads below "
            f"are everything walked up to that point — you do "
            f"not need a 100% run to use them.")
    else:
        st.success(
            f"✅ Built {_MONTH_NAMES[month - 1]} {year} "
            f"({result['cycle']}) from Twelve Data: "
            f"{result['slots']} slots walked, "
            f"{result['delivered']} picks delivered."
            + (f" {result['healed']} slot(s) healed by "
               f"re-fetch / M5 assembly."
               if result.get("healed") else "")
            + (f" {len(result['skipped'])} slot(s) recorded "
               f"DATA ERROR and skipped (see below)."
               if result.get("skipped") else ""))
    if result.get("slot_errors"):
        _errs = result["slot_errors"]
        st.warning(
            f"**{len(_errs)} slot(s) could not be completed "
            f"even after healing** — recorded DATA ERROR, the "
            f"build continued past them:\n"
            + "\n".join(
                f"- {e['slot']} UTC — {e['reason']}"
                for e in _errs[:10])
            + (f"\n- …and {len(_errs) - 10} more (full list "
               f"in the XLSX Slots sheet)."
               if len(_errs) > 10 else ""))
    if result.get("events"):
        # The build's text log (user order 2026-11-28): every
        # error, heal and skip event, in order — errors are
        # text in a log, never a dead run.
        with st.expander(
                "🧾 Build log — every error, heal and skip",
                expanded=bool(result.get("slot_errors"))):
            st.text("\n".join(str(e) for e in
                              result["events"]))
    if result.get("persistent_status") == "saved":
        st.caption(
            "💾 Saved to persistent memory — this month-year "
            "is now in the GitHub-synced store, available to "
            "every section.")
    elif result.get("persistent_status") == "exists":
        st.caption(
            "💾 Persistent memory already holds this "
            "month-year — the stored ledger was kept exactly "
            "as it was (never overwritten).")
    if comp:
        st.markdown(
            f"**Compare vs stored past "
            f"({result['past_name']}): similarity "
            f"{comp['similarity_pct']:.1f}%** — "
            f"{comp['match']} matching picks, "
            f"{comp['differ']} different, "
            f"{comp['only_built']} only in the Twelve build, "
            f"{comp['only_past']} only in the stored past, "
            f"out of {comp['shared_slots']} shared slots.")
        # Similarity gauge + per-slot match/differ visual
        # (user order 2026-11-28): rendered from the stored
        # compare result only — no extra data is loaded.
        try:
            _sim_v = float(comp["similarity_pct"])
            _sim_c = ("#16a34a" if _sim_v >= 70 else
                      "#d97706" if _sim_v >= 40 else "#dc2626")
            st.markdown(
                f"<div style='margin:6px 0 2px 0;"
                f"font-size:13px;'><b>Similarity</b> "
                f"{_sim_v:.1f}%</div>"
                f"<div style='height:14px;border-radius:7px;"
                f"background:rgba(148,163,184,.35);"
                f"overflow:hidden;'>"
                f"<div style='height:100%;"
                f"width:{max(0.0, min(100.0, _sim_v)):.1f}%;"
                f"background:{_sim_c};border-radius:7px;'>"
                f"</div></div>",
                unsafe_allow_html=True)
            _cell_colors = {"MATCH": "#16a34a",
                            "DIFFERENT": "#ea580c",
                            "ONLY IN TWELVE BUILD": "#2563eb",
                            "ONLY IN STORED PAST": "#94a3b8"}
            _cells = []
            for _s, _a, _b, _verdict in comp.get("rows") or []:
                _cells.append(
                    f"<span title='{_s} — {_verdict}' "
                    f"style='display:inline-block;width:12px;"
                    f"height:12px;border-radius:3px;"
                    f"background:"
                    f"{_cell_colors.get(_verdict, '#64748b')};'>"
                    f"</span>")
            if _cells:
                st.markdown(
                    "<div style='display:flex;flex-wrap:wrap;"
                    "gap:3px;margin:6px 0 2px 0;'>"
                    + "".join(_cells) + "</div>",
                    unsafe_allow_html=True)
                st.caption(
                    "One square per shared slot — 🟩 match · "
                    "🟧 different · 🟦 only in the Twelve build "
                    "· ⬜ only in the stored past. Hover a "
                    "square for its slot.")
        except Exception:
            pass
        # OpenRouter narration (user order 2026-11-28): one
        # plain line glossing the similarity. Dormant without
        # an [openrouter] key — the sentence above is then
        # the whole display, exactly as before. Cached on
        # the result dict, so re-renders never re-call.
        if "narration_similarity" not in result:
            try:
                from core.data import narration as _narr_mem
                result["narration_similarity"] = \
                    _narr_mem.one_line(
                        "similarity",
                        {"month_year": (f"{_MONTH_NAMES[month - 1]} "
                                        f"{year}"),
                         "cycle": result["cycle"],
                         "similarity_pct": round(
                             float(comp["similarity_pct"]), 1),
                         "match": comp["match"],
                         "differ": comp["differ"],
                         "shared_slots": comp["shared_slots"]})
            except Exception:
                result["narration_similarity"] = None
        if result.get("narration_similarity"):
            st.caption(f"🧾 {result['narration_similarity']}")
    else:
        st.caption("No stored past found for this month-year "
                   "to compare against.")
    fname = (f"twelve_memory_{result['cycle']}_"
             f"{year}-{month:02d}.xlsx")
    st.download_button(
        "⬇ Download memory (XLSX)", data=result["xlsx"],
        file_name=fname,
        mime=("application/vnd.openxmlformats-officedocument."
              "spreadsheetml.sheet"),
        key=f"twmem_dl_{year}_{month}")
    st.download_button(
        "⬇ Download walked state (JSON)",
        data=json.dumps(result["state"], indent=1),
        file_name=(f"{result['cycle']}_{year}.json"),
        mime="application/json",
        key=f"twmem_dljson_{year}_{month}")
    picks = result["state"].get("delivered", [])
    if picks:
        st.dataframe(pd.DataFrame([{
            "check (UTC)": str(d["check"]).replace("T", " "),
            "symbol": d["symbol"],
            "direction": d["direction"],
            "entry": d["entry_px"],
        } for d in picks]), use_container_width=True)
