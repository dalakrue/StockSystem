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

Data basis is Twelve Data throughout; the gate is the Signal
Law's: every slot must read 28/28 or the build stops with a
DATA ERROR naming the slot and the missing symbols. Nothing
here reads the Dukascopy store for the calculation; the stored
past is read only AFTER the walk, for the comparison.
"""
import io
import json
import os
import tempfile
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


def _fetch_window(pool, sym, tf, start_ts, end_ts, errors):
    """One symbol/timeframe's full window from Twelve Data,
    fetched backwards in <=5000-bar calls. Returns a normalized
    frame (Datetime column + data_basis for M15/M5, mirroring
    the replay fetcher) or None."""
    interval = _TF_INTERVAL[tf]
    step = _TF_STEP_MIN[tf]
    chunks = []
    end = pd.Timestamp(end_ts)
    start = pd.Timestamp(start_ts)
    while end > start:
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
                past_name, skipped=()):
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
        ("Slots skipped — DATA ERROR (market closed)",
         len(skipped)),
        ("Picks delivered", len(delivered)),
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
        "pick": "DATA ERROR (market closed)",
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


def build_memory(month, year, state=None, progress=None):
    """Download the month's candles from Twelve Data and walk
    its cycle over them. progress(frac, text) is called as work
    advances. Returns a result dict; on any gate failure the
    status is DATA ERROR and no partial memory is returned."""
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

    # ---- Phase 1: download the month (0% -> 30%) ----
    errors: list = []
    data = {tf: {} for tf in ("H1", "M15", "M5")}
    total = len(symbols) * 3
    done = 0
    for tf in ("H1", "M15", "M5"):
        for sym in symbols:
            frame = _fetch_window(pool, sym, tf, start, end,
                                  errors)
            if frame is not None:
                data[tf][sym] = frame
            done += 1
            report(0.30 * done / total,
                   f"Downloading Twelve Data candles: {sym} {tf} "
                   f"({done}/{total})")
    missing = [f"{sym} {tf}" for tf in ("H1", "M15", "M5")
               for sym in symbols if sym not in data[tf]]
    if missing:
        note = f"; {errors[0]}" if errors else ""
        return {"status": "DATA ERROR",
                "missing": (f"Twelve Data download incomplete for "
                            f"{len(missing)} symbol/timeframes: "
                            f"{', '.join(missing[:10])}{note}")}

    # ---- Phase 2: the walk (30% -> 95%) ----
    import core.signal_mode as sm
    tmpdir = tempfile.mkdtemp(prefix="twelve_memory_")
    state_path = os.path.join(
        tmpdir, f"{cycle}_{year}-{month:02d}.json")
    prev_form = getattr(mod, "_STATE", None)
    prev_saveback = sm._saveback_ledgers
    built_state = None
    skipped = []
    try:
        sm._saveback_ledgers = lambda: None
        mod._STATE = mod.load_state_form(path=state_path)
        for i, slot in enumerate(slots):
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
            if h1_missing and len(h1_missing) == len(symbols) \
                    and all(data["H1"][s].index.max() > ent
                            for s in symbols):
                # Market closed (user ruling 2026-11-27): the
                # candles do not exist, but the downloaded data
                # continues past the slot. Record DATA ERROR
                # for the slot and walk on.
                skipped.append(str(slot))
                report(0.30 + 0.65 * (i + 1) / len(slots),
                       f"Walking {_MONTH_NAMES[month - 1]} {year}: "
                       f"slot {i + 1}/{len(slots)} "
                       f"({slot:%Y-%m-%d %H:%M} UTC) — DATA ERROR "
                       f"(market closed), skipped")
                continue
            if h1_missing:
                return {"status": "DATA ERROR",
                        "missing": (f"{slot}: H1 sig/entry candles "
                                    f"from Twelve Data missing "
                                    f"for {len(h1_missing)} "
                                    f"symbols: "
                                    f"{', '.join(h1_missing)}")}
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
                if len(bad) == len(symbols) and all(
                        data["M15"][s].index.max() > entry_bar
                        for s in symbols):
                    # Market closed (user ruling 2026-11-27):
                    # Twelve has H1 bars for the day but no M15
                    # session at all (e.g. Christmas Day), while
                    # the downloaded data continues past the
                    # slot. Record DATA ERROR for the slot and
                    # walk on.
                    skipped.append(str(slot))
                    report(0.30 + 0.65 * (i + 1) / len(slots),
                           f"Walking {_MONTH_NAMES[month - 1]} "
                           f"{year}: slot {i + 1}/{len(slots)} "
                           f"({slot:%Y-%m-%d %H:%M} UTC) — DATA "
                           f"ERROR (market closed), skipped")
                    continue
                return {"status": "DATA ERROR",
                        "missing": (f"{slot}: M15 entry window "
                                    f"from Twelve Data missing "
                                    f"for {len(bad)} symbols: "
                                    f"{', '.join(bad)}")}
            mod.panel_entries(frames, slot, m15_frames=m15_frames,
                              open_symbols=(), m5_frames=m5_frames)
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
        return {"status": "DATA ERROR",
                "missing": "the walk produced no state"}

    # ---- Phase 3: compare + files (95% -> 100%) ----
    report(0.97, "Comparing against the stored past…")
    past, past_name = _past_ledger(cycle, year, month)
    compare = _compare(built_state, past) if past else None
    xlsx = _xlsx_bytes(month, year, cycle, built_state, compare,
                       past_name, skipped=skipped)
    report(1.0, "Done")
    return {"status": "OK", "cycle": cycle,
            "slots": len(built_state.get("processed", [])),
            "skipped": skipped,
            "delivered": len(built_state.get("delivered", [])),
            "state": built_state, "compare": compare,
            "past_name": past_name, "xlsx": xlsx}


def render_twelve_memory_section(st):
    st.markdown("---")
    st.markdown("#### 🔷 Twelve Data API Memory Building")
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
    if st.button("▶ Start building memory (Twelve Data)",
                 key="twmem_start"):
        bar = st.progress(0.0)
        note = st.empty()

        def _prog(frac, text):
            bar.progress(min(max(float(frac), 0.0), 1.0))
            note.caption(
                f"{text} — **{int(round(100 * frac))}%**")

        with st.spinner("Building memory from Twelve Data…"):
            result = build_memory(month, int(year),
                                  state=st.session_state,
                                  progress=_prog)
        st.session_state[store_key] = result
    result = st.session_state.get(store_key)
    if not result:
        return
    if result.get("status") != "OK":
        st.error(f"DATA ERROR — {result.get('missing', '')}")
        return
    comp = result.get("compare")
    st.success(
        f"✅ Built {_MONTH_NAMES[month - 1]} {year} "
        f"({result['cycle']}) from Twelve Data: "
        f"{result['slots']} slots walked, "
        f"{result['delivered']} picks delivered."
        + (f" {len(result['skipped'])} slot(s) recorded DATA "
           f"ERROR (market closed) and skipped."
           if result.get("skipped") else ""))
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
