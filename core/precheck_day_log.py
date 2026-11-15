"""All-day precheck signal log (user order 2026-11-16).

Every precheck computation the app runs is recorded here, keyed by the
Myanmar-time (Asia/Yangon) calendar date on which the run happened, so
the Field 3 page can show a "Today's precheck signals" table that never
disappears within the day: it survives page refreshes and Streamlit
reruns because it is read back from disk on every render, and it starts
empty on a new Myanmar date because older dates are simply not shown
(rows from previous days are pruned on write).

One row per (date, month, check time): repeat computations of the same
check update the row's result and run count instead of adding noise.

Store: a small JSON file in the app's data area, next to the signal
evaluation-history DB (data/precheck_day_log.json). The location can be
overridden with the FOREX_PRECHECK_DAY_LOG environment variable (used
by tests). On Streamlit Cloud the app working directory survives reruns
of the same deployment, but a full redeploy/restart can reset it -- the
table is a same-day convenience record, not an archive.

Result text follows the signal-delivery law for prechecks: an entry is
recorded as symbol + side only (no prices, no score); a no-entry read is
recorded as "No entry". This module never raises into the UI.
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import os as _os
from pathlib import Path as _Path

_MMT = _dt.timezone(_dt.timedelta(hours=6, minutes=30))
_KEEP_DAYS = 2  # today + yesterday are kept on disk; older rows pruned


def _store_path() -> _Path:
    env = _os.environ.get("FOREX_PRECHECK_DAY_LOG")
    if env:
        return _Path(env)
    return (_Path(__file__).resolve().parents[1] / "data"
            / "precheck_day_log.json")


def mmt_today(now_utc: _dt.datetime | None = None) -> str:
    """Myanmar-time calendar date (YYYY-MM-DD) for `now_utc` (default: now)."""
    if now_utc is None:
        now_utc = _dt.datetime.now(_dt.timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=_dt.timezone.utc)
    return now_utc.astimezone(_MMT).strftime("%Y-%m-%d")


def _mmt_hhmm(ts_utc: _dt.datetime) -> str:
    if ts_utc.tzinfo is None:
        ts_utc = ts_utc.replace(tzinfo=_dt.timezone.utc)
    return ts_utc.astimezone(_MMT).strftime("%H:%M")


def _load() -> list:
    try:
        path = _store_path()
        if not path.exists():
            return []
        data = _json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("rows") if isinstance(data, dict) else None
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def _save(rows: list) -> None:
    try:
        path = _store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(_json.dumps({"rows": rows}, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass


def record_precheck(month, system, check_hhmm, status, symbol=None,
                    direction=None, note=None, run_at_utc=None) -> None:
    """Record one precheck computation. Never raises.

    month: 1..12; system: the registry cycle id that was evaluated
    (e.g. "cycle93ah"); check_hhmm: the targeted check time in Myanmar
    time ("19:30"); status: "pick" | "none"; symbol/direction for a
    pick. The row is keyed by (run date in MMT, month, check time)."""
    try:
        if run_at_utc is None:
            run_at_utc = _dt.datetime.now(_dt.timezone.utc)
        date = mmt_today(run_at_utc)
        run_hhmm = _mmt_hhmm(run_at_utc)
        if status == "pick" and symbol:
            result = f"{str(direction or '').upper()} {str(symbol).upper()}".strip()
        elif status == "pick":
            result = "Entry"
        else:
            result = "No entry"
        if note:
            result = f"{result} — {note}"
        rows = _load()
        key = (date, int(month), str(check_hhmm))
        found = None
        for row in rows:
            if (row.get("date"), row.get("month"), row.get("check")) == key:
                found = row
                break
        if found is None:
            rows.append({
                "date": date, "month": int(month), "system": str(system),
                "check": str(check_hhmm), "result": result,
                "first_run": run_hhmm, "last_run": run_hhmm, "runs": 1,
            })
        else:
            found["system"] = str(system)
            found["result"] = result
            found["last_run"] = run_hhmm
            found["runs"] = int(found.get("runs", 1)) + 1
        cutoff = (_dt.datetime.now(_dt.timezone.utc).astimezone(_MMT)
                  - _dt.timedelta(days=_KEEP_DAYS)).strftime("%Y-%m-%d")
        rows = [r for r in rows if str(r.get("date", "")) >= cutoff]
        _save(rows)
    except Exception:
        pass


def load_day(date: str | None = None) -> list:
    """Rows recorded on one Myanmar date (default: today), in check-time
    order. Each row: check, system, result, runs, first_run, last_run."""
    try:
        if date is None:
            date = mmt_today()
        rows = [r for r in _load() if r.get("date") == date]
        rows.sort(key=lambda r: (str(r.get("check", "")), int(r.get("month", 0))))
        return rows
    except Exception:
        return []
