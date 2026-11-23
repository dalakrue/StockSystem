"""Canonical signal feed — the app's ONE live signal source.

User order 2026-11-22: integrate/migrate/sync the app to the
precheck/check chain so the app's signal MUST be the same as
the chain's. The chain machine (FULL WAY canonical: one frame
builder, memory stepped from the month start, delivery gate +
ledger check) publishes an hourly full-sync feed to this
repo's `canonical-feed` branch; this module fetches and
renders it. The app never computes a competing live signal
for the feed's month — it displays the chain's numbers.

Feed contents: latest CHECK and PRECHECK entries plus the
last 24 CHECK and last 24 PRECHECK live replay rows
(weekdays only), settled exactly like the chain's morning
replay table. Fallback: the copy bundled at
data/canonical_signal_feed.json (refreshed on app pushes).
"""
from __future__ import annotations

import json
from pathlib import Path

FEED_URL = ("https://raw.githubusercontent.com/dalakrue/"
            "StockSystem/canonical-feed/"
            "canonical_signal_feed.json")
_LOCAL = (Path(__file__).resolve().parent.parent / "data"
          / "canonical_signal_feed.json")


def _fetch_feed():
    try:
        import requests
        r = requests.get(FEED_URL, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    try:
        return json.loads(_LOCAL.read_text(encoding="utf-8"))
    except Exception:
        return None


def feed_is_fresh(feed, max_age_minutes=90):
    """True only when the chain machine's feed was generated
    recently. The publisher runs hourly; if it stops, the feed
    goes stale and the app must fall back to its own live
    calculation instead of displaying an old precheck as the
    current signal (failure seen 2026-11-23: the feed froze at
    2026-11-22 23:40 MMT, so the 20:00 MMT check showed no
    precheck at all). An unparseable timestamp counts as
    stale — the safe direction is the live calculation."""
    try:
        import datetime as _dt
        gen = _dt.datetime.strptime(
            str((feed or {}).get("generated_at_mmt")),
            "%Y-%m-%d %H:%M")
        _mmt = _dt.timezone(_dt.timedelta(hours=6, minutes=30))
        _now = _dt.datetime.now(_mmt).replace(tzinfo=None)
        _age = (_now - gen).total_seconds() / 60.0
        return -15.0 <= _age <= float(max_age_minutes)
    except Exception:
        return False


try:
    import streamlit as _st

    @_st.cache_data(ttl=3600, show_spinner=False)
    def _cached_feed(_hour_bucket: int):
        return _fetch_feed()

    def load_feed():
        import time
        feed = _cached_feed(int(time.time() // 3600))
        # Freshness gate (fix 2026-11-23): a stale feed is
        # treated as NO feed, so the dashboard falls back to
        # its own live calculation instead of retiring it in
        # favour of a days-old precheck.
        return feed if feed_is_fresh(feed) else None

except Exception:  # streamlit unavailable (offline checks)
    def load_feed():
        feed = _fetch_feed()
        return feed if feed_is_fresh(feed) else None


_BOX = ("background:rgba(255,255,255,.55);"
        "border:1px solid rgba(255,255,255,.65);"
        "border-radius:12px;box-shadow:0 4px 14px "
        "rgba(15,23,42,.06);backdrop-filter:blur(10px) "
        "saturate(150%);-webkit-backdrop-filter:blur(10px) "
        "saturate(150%);padding:10px 14px;margin:6px 0;"
        "font-size:15px;color:#0f172a;")


def _row_line(r):
    if not r:
        return "—"
    return (f"{r['date']} · {r['check_mmt']} · {r['entry']} · "
            f"{r['exit']} · ${r['net']:+.2f}")


def render_canonical_panel(st, feed):
    """The chain's current signal, as a glass box."""
    if not feed:
        return
    lc = feed.get("latest_check")
    lp = feed.get("latest_precheck")
    html = (
        f"<div style='{_BOX}'>"
        "<b>\U0001f4e1 CHAIN SIGNAL — canonical (FULL WAY)</b>"
        f"<br>Latest CHECK: <b>{_row_line(lc)}</b>"
        f"<br>Latest PRECHECK: <b>{_row_line(lp)}</b>"
        f"<br><span style='font-size:12px;color:#475569;'>"
        f"System {feed.get('system')} · feed updated "
        f"{feed.get('generated_at_mmt')} MMT · refreshed hourly"
        "</span></div>")
    st.markdown(html, unsafe_allow_html=True)


def _table(st, title, block):
    rows = (block or {}).get("rows") or []
    st.markdown(f"**{title} — total "
                f"${(block or {}).get('total', 0):+.2f}**")
    if not rows:
        st.caption("No rows yet.")
        return
    import pandas as pd
    df = pd.DataFrame([{
        "Date": r["date"], "Check": r["check_mmt"],
        "Entry": r["entry"], "Exit": r["exit"],
        "Net": f"${r['net']:+.2f}"} for r in rows])
    st.dataframe(df, hide_index=True, use_container_width=True)


def render_history_section(st):
    """History — the very bottom of the dashboard (user order
    2026-11-22): the last 24 CHECK and PRECHECK live replay
    tables from the canonical feed, updated hourly."""
    feed = load_feed()
    st.markdown("## \U0001f559 History")
    if not feed:
        st.caption("Canonical feed unavailable right now — the "
                   "table returns at the next hourly refresh.")
        return
    st.caption("Last 24 CHECK and PRECHECK live replay — "
               "FULL WAY canonical, recalculated from candles "
               "by the chain machine and updated every hour. "
               "Weekends ignored. "
               f"Feed updated {feed.get('generated_at_mmt')} MMT "
               f"· {feed.get('system')}.")
    _table(st, "per CHECK", feed.get("check"))
    _table(st, "per PRECHECK", feed.get("precheck"))
    st.markdown(f"**BEST: {feed.get('best_last24', '—')}** "
                "(last 24 rows)")
