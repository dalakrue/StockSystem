"""MT5 live snapshot store + Section 6 data preparation.

The laptop bridge (the user's own MT5 terminal, connected over
Tailscale) publishes a small JSON snapshot of the account's open
positions and recent closed deals to the repo file
``data/mt5_live.json``. This module is the app's side of that
contract:

* ``load_snapshot()`` reads ONLY the local copy — rendering never
  fetches (the section's zero-fetch rule).
* ``ensure_snapshot_async()`` keeps the local copy present and
  reasonably fresh the same way the history save-back restore
  does (user order 2026-11-27): a daemon thread, started once
  per process and re-armed on a slow TTL, pulls the repo copy
  when the local file is missing or its snapshot is stale. The
  render path never waits on it.

The data-preparation functions below are pure (``now`` is a
parameter) so the section's math — time left before the 48 h
exit horizon, window progress, net pips, the weekly report —
is unit-testable offline against a fixture snapshot.

Net pips convention (the system's): net = gross - 2.5 per
position. Never raises into the UI.
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import os as _os
import threading as _threading
from pathlib import Path as _Path

_REPO_REL = "data/mt5_live.json"
_RAW_URL = ("https://raw.githubusercontent.com/dalakrue/"
            "StockSystem/main/data/mt5_live.json")
_EXIT_HORIZON_HOURS = 48.0
_COST_PIPS = 2.5
_REFETCH_MIN_SECONDS = 300.0        # at most one fetch / 5 min
_STALE_AFTER_SECONDS = 900.0        # refetch if snapshot > 15 min old

_LOCK = _threading.Lock()
_FETCH_STARTED = False
_LAST_FETCH_TS = 0.0


def snapshot_path() -> _Path:
    """Local snapshot location. FOREX_MT5_LIVE_JSON overrides
    it (used by tests)."""
    env = _os.environ.get("FOREX_MT5_LIVE_JSON")
    if env:
        return _Path(env)
    return (_Path(__file__).resolve().parents[2]
            / "data" / "mt5_live.json")


def parse_ts(value):
    """ISO timestamp -> aware UTC datetime, or None. Naive
    values are read as UTC. Never raises."""
    try:
        if value is None:
            return None
        if isinstance(value, _dt.datetime):
            ts = value
        else:
            text = str(value).strip()
            if not text:
                return None
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            ts = _dt.datetime.fromisoformat(text)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=_dt.timezone.utc)
        return ts.astimezone(_dt.timezone.utc)
    except Exception:
        return None


def load_snapshot():
    """The local snapshot dict, or None when there is no usable
    local copy. Local read only — no network. Never raises."""
    try:
        path = snapshot_path()
        if not path.is_file() or path.stat().st_size == 0:
            return None
        with open(path, "r", encoding="utf-8") as fh:
            data = _json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# ----------------------------------------------------------------
# Boot restore / background refresh (github_saveback pattern)
# ----------------------------------------------------------------

def _fetch_repo_bytes():
    """The repo copy of the snapshot, or None. Tries the
    save-back token route first (the Contents API), then the
    public raw URL (the repo is public). Never raises."""
    try:
        from core.data import github_saveback as _gsb
        token = _gsb._secret_token()
        if token:
            raw = _gsb._fetch_bytes(_REPO_REL, token)
            if raw:
                return raw
    except Exception:
        pass
    try:
        import urllib.request as _u
        req = _u.Request(_RAW_URL, headers={
            "User-Agent": "StockSystem-MT5-restore"})
        with _u.urlopen(req, timeout=20) as resp:
            if int(getattr(resp, "status", 200)) == 200:
                return resp.read()
    except Exception:
        pass
    return None


def _refresh_once():
    """Fetch the repo snapshot and replace the local copy when
    the fetched one is newer (or the local one is missing /
    unreadable). Atomic write. Never raises."""
    global _LAST_FETCH_TS
    try:
        import time as _time
        with _LOCK:
            _LAST_FETCH_TS = _time.time()
        raw = _fetch_repo_bytes()
        if not raw:
            return
        try:
            fresh = _json.loads(raw.decode("utf-8"))
        except Exception:
            return
        if not isinstance(fresh, dict):
            return
        local = load_snapshot()
        fresh_ts = parse_ts(fresh.get("updated_at_utc"))
        local_ts = parse_ts(
            local.get("updated_at_utc")) if local else None
        if local is not None and fresh_ts is not None \
                and local_ts is not None and fresh_ts <= local_ts:
            return  # local copy is already at least as new
        path = snapshot_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(path) + ".restore-tmp"
        with open(tmp, "wb") as fh:
            fh.write(raw)
        _os.replace(tmp, path)
    except Exception:
        pass


def ensure_snapshot_async(now=None):
    """Start the snapshot restore/refresh on a daemon thread
    when it is due; a no-op otherwise. Due = never fetched this
    process, or the last fetch is older than the refetch floor
    AND (no local copy OR the local snapshot is stale). Render
    code calls this and moves on — it never blocks. Returns
    True iff a thread was started by this call. Never raises."""
    global _FETCH_STARTED
    try:
        import time as _time
        if now is None:
            now = _dt.datetime.now(_dt.timezone.utc)
        with _LOCK:
            if _FETCH_STARTED and (
                    _time.time() - _LAST_FETCH_TS
                    < _REFETCH_MIN_SECONDS):
                return False
            local = load_snapshot()
            due = local is None
            if not due:
                ts = parse_ts(local.get("updated_at_utc"))
                if ts is None or (now - ts).total_seconds() \
                        > _STALE_AFTER_SECONDS:
                    due = True
            if not due and _FETCH_STARTED:
                return False
            _FETCH_STARTED = True
        thread = _threading.Thread(
            target=_refresh_once, daemon=True,
            name="mt5-live-restore")
        thread.start()
        return True
    except Exception:
        return False


# ----------------------------------------------------------------
# Pure data preparation (unit-tested offline)
# ----------------------------------------------------------------

def _num(value, default=None):
    try:
        return float(value)
    except Exception:
        return default


def snapshot_age_text(snapshot, now):
    """'updated 12s ago' / '5m ago' / '2h 05m ago' / '3d ago'
    from the snapshot's own updated_at_utc stamp."""
    ts = parse_ts((snapshot or {}).get("updated_at_utc"))
    if ts is None:
        return "update time unknown"
    secs = max(0.0, (now - ts).total_seconds())
    if secs < 60:
        return f"updated {int(secs)}s ago"
    if secs < 3600:
        return f"updated {int(secs // 60)}m ago"
    if secs < 86400:
        return (f"updated {int(secs // 3600)}h "
                f"{int((secs % 3600) // 60):02d}m ago")
    return f"updated {int(secs // 86400)}d ago"


def open_position_view(pos, now):
    """View model for one open position: the 48 h exit-horizon
    math (elapsed, time left, window progress, overdue) and the
    net-pips figure (gross - 2.5). Pure; never raises."""
    opened = parse_ts(pos.get("opened_at_utc"))
    gross = _num(pos.get("gross_pips"))
    view = {
        "ticket": pos.get("ticket"),
        "symbol": str(pos.get("symbol") or ""),
        "direction": str(pos.get("direction") or "").upper(),
        "volume": _num(pos.get("volume")),
        "entry": _num(pos.get("entry")),
        "current": _num(pos.get("current")),
        "tp": _num(pos.get("tp")),
        "sl": _num(pos.get("sl")),
        "opened_at_utc": opened,
        "gross_pips": gross,
        "net_pips": (gross - _COST_PIPS) if gross is not None
        else None,
        "elapsed_hours": None,
        "remaining_text": "opened time unknown",
        "progress": None,
        "overdue": False,
    }
    if opened is not None:
        elapsed_h = (now - opened).total_seconds() / 3600.0
        view["elapsed_hours"] = elapsed_h
        view["progress"] = max(
            0.0, min(1.0, elapsed_h / _EXIT_HORIZON_HOURS))
        remaining_h = _EXIT_HORIZON_HOURS - elapsed_h
        if remaining_h >= 0:
            total_min = int(remaining_h * 60)
            view["remaining_text"] = (
                f"{total_min // 60}h {total_min % 60:02d}m left")
        else:
            view["overdue"] = True
            over_min = int(-remaining_h * 60)
            view["remaining_text"] = (
                f"over 48h by {over_min // 60}h "
                f"{over_min % 60:02d}m")
    return view


def _closed_view(row):
    gross = _num(row.get("gross_pips"))
    return {
        "ticket": row.get("ticket"),
        "symbol": str(row.get("symbol") or ""),
        "direction": str(row.get("direction") or "").upper(),
        "volume": _num(row.get("volume")),
        "entry": _num(row.get("entry")),
        "exit": _num(row.get("exit")),
        "opened_at_utc": parse_ts(row.get("opened_at_utc")),
        "closed_at_utc": parse_ts(row.get("closed_at_utc")),
        "gross_pips": gross,
        "net_pips": (gross - _COST_PIPS) if gross is not None
        else None,
        "exit_reason": str(row.get("exit_reason") or "OTHER")
        .upper(),
    }


def _totals(views):
    """Count / exit-reason split / gross / net over closed
    views. Reasons outside TP/SL/48H count as MANUAL here only
    when the bridge said MANUAL; OTHER stays OTHER."""
    out = {"count": len(views), "tp": 0, "sl": 0, "h48": 0,
           "manual": 0, "other": 0, "gross": 0.0, "net": 0.0,
           "wins": 0, "losses": 0}
    for v in views:
        reason = v.get("exit_reason") or "OTHER"
        if reason == "TP":
            out["tp"] += 1
        elif reason == "SL":
            out["sl"] += 1
        elif reason == "48H":
            out["h48"] += 1
        elif reason == "MANUAL":
            out["manual"] += 1
        else:
            out["other"] += 1
        gross = v.get("gross_pips")
        if gross is not None:
            out["gross"] += gross
            out["net"] += gross - _COST_PIPS
            if gross > 0:
                out["wins"] += 1
            elif gross < 0:
                out["losses"] += 1
    return out


def closed_today(snapshot, now):
    """(views, totals) for positions closed on ``now``'s UTC
    calendar day."""
    views = []
    for row in (snapshot or {}).get("closed") or []:
        if not isinstance(row, dict):
            continue
        view = _closed_view(row)
        closed = view.get("closed_at_utc")
        if closed is not None and closed.date() == now.date():
            views.append(view)
    views.sort(key=lambda v: v.get("closed_at_utc")
               or now, reverse=True)
    return views, _totals(views)


def weekly_report(snapshot, now):
    """The current week (Mon-Sun, UTC) report MT5 does not
    auto-calculate, from the snapshot's closed list: trades,
    wins/losses, win %, gross/net pips, best/worst trade,
    per-symbol net, per-day net — plus an all-time totals row
    over whatever the snapshot holds. Pure; never raises."""
    monday = (now - _dt.timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    next_monday = monday + _dt.timedelta(days=7)
    week_views, all_views = [], []
    for row in (snapshot or {}).get("closed") or []:
        if not isinstance(row, dict):
            continue
        view = _closed_view(row)
        all_views.append(view)
        closed = view.get("closed_at_utc")
        if closed is not None and monday <= closed < next_monday:
            week_views.append(view)
    totals = _totals(week_views)
    decided = totals["wins"] + totals["losses"]
    best = worst = None
    for v in week_views:
        if v.get("gross_pips") is None:
            continue
        if best is None or v["gross_pips"] > best["gross_pips"]:
            best = v
        if worst is None or v["gross_pips"] < worst["gross_pips"]:
            worst = v
    per_symbol = {}
    for v in week_views:
        slot = per_symbol.setdefault(
            v.get("symbol") or "—",
            {"symbol": v.get("symbol") or "—", "trades": 0,
             "gross": 0.0, "net": 0.0})
        slot["trades"] += 1
        if v.get("gross_pips") is not None:
            slot["gross"] += v["gross_pips"]
            slot["net"] += v["gross_pips"] - _COST_PIPS
    per_day = {}
    for v in week_views:
        closed = v.get("closed_at_utc")
        if closed is None or v.get("gross_pips") is None:
            continue
        day = closed.strftime("%Y-%m-%d")
        per_day[day] = per_day.get(day, 0.0) \
            + v["gross_pips"] - _COST_PIPS
    return {
        "week_start": monday,
        "trades": totals["count"],
        "wins": totals["wins"],
        "losses": totals["losses"],
        "win_pct": (100.0 * totals["wins"] / decided)
        if decided else None,
        "gross": totals["gross"],
        "net": totals["net"],
        "best": best,
        "worst": worst,
        "per_symbol": sorted(
            per_symbol.values(),
            key=lambda s: s["net"], reverse=True),
        "per_day": per_day,
        "all_time": _totals(all_views),
    }
