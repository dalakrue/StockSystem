"""Section 6 — MT5 Live Result (user order 2026-11-28).

Shows the user's own MT5 account as the laptop bridge reports
it: open positions with their live result and the time left
before the system's 48 h exit horizon, today's closed results,
and a weekly report with the statistics MT5 does not
auto-calculate (win rate, net pips, per-symbol and per-day
nets, best/worst trade).

Data comes ONLY from the local snapshot file
(``data/mt5_live.json``, written by the bridge and restored
from the repo on boot — see core.data.mt5_live). This section
performs ZERO network fetches; when no snapshot exists it
shows an honest waiting state and never fabricates a row.
Net pips follow the system convention: net = gross - 2.5.
"""
from __future__ import annotations

import datetime as _dt
import html as _html

from core.data import mt5_live as _mt5

_TEAL = "#0d9488"


def _fmt_px(value):
    if value is None:
        return "—"
    try:
        return f"{float(value):.5f}".rstrip("0").rstrip(".")
    except Exception:
        return "—"


def _pips_html(value):
    if value is None:
        return "<span style='color:#64748b;'>—</span>"
    colour = "#16a34a" if value >= 0 else "#dc2626"
    return (f"<span style='color:{colour};font-weight:700;'>"
            f"{value:+.1f}</span>")


def _position_card(view):
    """One open position as a glass card (HTML). The card grid
    wraps 2-across on wide screens, 1-across on phones (CSS in
    the shared glass theme: .fx-card-grid / .fx-pos-card)."""
    sym = _html.escape(view.get("symbol") or "—")
    direction = _html.escape(view.get("direction") or "")
    dir_colour = "#16a34a" if direction == "BUY" else "#dc2626"
    overdue = bool(view.get("overdue"))
    bar_colour = "#dc2626" if overdue else _TEAL
    progress_pct = (view.get("progress") or 0.0) * 100.0
    opened = view.get("opened_at_utc")
    opened_txt = (opened.strftime("%b %d · %H:%M UTC")
                  if opened is not None else "—")
    remain = _html.escape(view.get("remaining_text") or "")
    remain_style = ("color:#dc2626;font-weight:800;" if overdue
                    else "color:#0f172a;font-weight:700;")
    tp = _fmt_px(view.get("tp"))
    sl = _fmt_px(view.get("sl"))
    vol = view.get("volume")
    vol_txt = f"{vol:g}" if isinstance(vol, float) else "—"
    return (
        "<div class='fx-pos-card'>"
        f"<div style='display:flex;justify-content:space-between;"
        f"align-items:baseline;'>"
        f"<span style='font-size:17px;font-weight:800;'>{sym} "
        f"<span style='color:{dir_colour};'>{direction}</span></span>"
        f"<span style='font-size:12px;color:#64748b;'>"
        f"{vol_txt} lots</span></div>"
        f"<div style='font-size:13.5px;line-height:1.75;"
        f"margin-top:4px;'>"
        f"Entry <b>{_fmt_px(view.get('entry'))}</b> · "
        f"Now <b>{_fmt_px(view.get('current'))}</b><br/>"
        f"Gross {_pips_html(view.get('gross_pips'))} pips · "
        f"Net {_pips_html(view.get('net_pips'))} pips<br/>"
        f"TP {tp} · SL {sl}<br/>"
        f"Opened {opened_txt}</div>"
        f"<div style='margin-top:6px;font-size:13.5px;"
        f"{remain_style}'>⏳ {remain}</div>"
        f"<div style='height:9px;border-radius:5px;"
        f"background:rgba(100,116,139,.25);overflow:hidden;"
        f"margin-top:3px;'>"
        f"<div style='height:100%;width:{progress_pct:.0f}%;"
        f"background:{bar_colour};border-radius:5px;'></div>"
        f"</div>"
        f"<div style='font-size:11.5px;color:#64748b;"
        f"margin-top:2px;'>48h window "
        f"{progress_pct:.0f}% used</div>"
        "</div>")


def render_mt5_live_section(st):
    """Section 6 — MT5 Live Result, after History (user order
    2026-11-28). Renders from the local snapshot only."""
    st.markdown(
        f"<div style='border-top:8px solid {_TEAL};"
        "margin:22px 0 8px 0;'></div>"
        f"<div style='background:{_TEAL};color:#fff;"
        "border-radius:10px;padding:10px 14px;font-size:20px;"
        "font-weight:800;'>📟 MT5 LIVE RESULT</div>"
        "<div style='font-size:14px;margin:6px 2px;'>"
        "Your MT5 account as the laptop bridge reports it — "
        "open trades, closed results, and the time left "
        "before each trade's 48h close.</div>",
        unsafe_allow_html=True)

    # Boot restore / background refresh — non-blocking; the
    # render below reads the local file only (zero fetches).
    _mt5.ensure_snapshot_async()
    snap = _mt5.load_snapshot()
    if not snap:
        st.info(
            "Waiting for the laptop bridge — open MT5 + "
            "Tailscale on the laptop and run the MT5 Bridge "
            "(run_laptop.bat); results appear here "
            "automatically.")
        return

    now = _dt.datetime.now(_dt.timezone.utc)
    age = _mt5.snapshot_age_text(snap, now)
    account = str(snap.get("account") or "").strip()
    head = f"🕒 Snapshot {age}"
    if account:
        head += f" · Account {account}"
    st.markdown(f"**{head}**")
    balance = snap.get("balance")
    equity = snap.get("equity")
    if balance is not None or equity is not None:
        _c1, _c2 = st.columns(2)
        with _c1:
            st.metric("Balance",
                      f"{float(balance):,.2f}"
                      if balance is not None else "—")
        with _c2:
            st.metric("Equity",
                      f"{float(equity):,.2f}"
                      if equity is not None else "—")

    # ---- Open positions -------------------------------------
    open_rows = [r for r in (snap.get("open") or [])
                 if isinstance(r, dict)]
    views = [_mt5.open_position_view(r, now) for r in open_rows]
    st.markdown(f"#### 📂 Open positions ({len(views)})")
    if not views:
        st.caption("No open positions in the latest snapshot.")
    else:
        cards = "".join(_position_card(v) for v in views)
        st.markdown(f"<div class='fx-card-grid'>{cards}</div>",
                    unsafe_allow_html=True)
        _og = sum(v["gross_pips"] for v in views
                  if v.get("gross_pips") is not None)
        _on = sum(v["net_pips"] for v in views
                  if v.get("net_pips") is not None)
        st.markdown(
            f"**Open totals — gross {_og:+.1f} pips · "
            f"net {_on:+.1f} pips** (marked at the snapshot's "
            "prices)")

    # ---- Closed today ---------------------------------------
    today_views, today_totals = _mt5.closed_today(snap, now)
    st.markdown(
        f"#### ✅ Closed today ({today_totals['count']})")
    if not today_views:
        st.caption("Nothing closed yet today (UTC day).")
    else:
        import pandas as _pd
        _rows = [{
            "Symbol": v["symbol"],
            "Side": v["direction"],
            "Entry": _fmt_px(v["entry"]),
            "Exit": _fmt_px(v["exit"]),
            "Gross": (f"{v['gross_pips']:+.1f}"
                      if v["gross_pips"] is not None else "—"),
            "Net": (f"{v['net_pips']:+.1f}"
                    if v["net_pips"] is not None else "—"),
            "Exit by": v["exit_reason"],
            "Closed (UTC)": (v["closed_at_utc"].strftime("%H:%M")
                             if v["closed_at_utc"] else "—"),
        } for v in today_views]
        st.dataframe(_pd.DataFrame(_rows),
                     use_container_width=True, hide_index=True)
        st.markdown(
            f"**Today — TP {today_totals['tp']} · "
            f"SL {today_totals['sl']} · "
            f"48H {today_totals['h48']} · "
            f"Manual {today_totals['manual']} · "
            f"Other {today_totals['other']} · "
            f"gross {today_totals['gross']:+.1f} · "
            f"net {today_totals['net']:+.1f} pips**")

    # ---- Weekly report --------------------------------------
    report = _mt5.weekly_report(snap, now)
    st.markdown("#### 📅 Weekly report — this week (Mon–Sun, "
                "UTC)")
    st.caption("The statistics MT5 does not auto-calculate: "
               "win rate and net pips use the system "
               "convention (net = gross − 2.5 per trade).")
    if not report["trades"]:
        st.caption("No closed trades yet this week.")
    else:
        _w1, _w2, _w3, _w4 = st.columns(4)
        with _w1:
            st.metric("Trades", report["trades"])
        with _w2:
            st.metric(
                "Win %",
                f"{report['win_pct']:.0f}%"
                if report["win_pct"] is not None else "—",
                help=f"{report['wins']} wins / "
                     f"{report['losses']} losses (on gross pips)")
        with _w3:
            st.metric("Gross pips", f"{report['gross']:+.1f}")
        with _w4:
            st.metric("Net pips", f"{report['net']:+.1f}")
        _best, _worst = report["best"], report["worst"]
        if _best is not None and _worst is not None:
            st.markdown(
                f"**Best** — {_best['symbol']} "
                f"{_best['direction']} "
                f"{_best['gross_pips']:+.1f} pips · "
                f"**Worst** — {_worst['symbol']} "
                f"{_worst['direction']} "
                f"{_worst['gross_pips']:+.1f} pips")
        if report["per_symbol"]:
            import pandas as _pd
            st.dataframe(_pd.DataFrame([{
                "Symbol": s["symbol"],
                "Trades": s["trades"],
                "Gross": round(s["gross"], 1),
                "Net": round(s["net"], 1),
            } for s in report["per_symbol"]]),
                use_container_width=True, hide_index=True)
        if report["per_day"]:
            _days = sorted(report["per_day"])
            _mx = max((abs(report["per_day"][d]) for d in _days),
                      default=1.0) or 1.0
            _bars = []
            for d in _days:
                v = report["per_day"][d]
                w = max(2.0, 100.0 * abs(v) / _mx)
                c = "#16a34a" if v >= 0 else "#dc2626"
                _bars.append(
                    "<div style='display:flex;align-items:"
                    "center;gap:6px;margin:2px 0;'>"
                    f"<span style='min-width:82px;font-size:"
                    f"12px;'>{d}</span>"
                    f"<span style='display:inline-block;"
                    f"height:12px;width:{w:.0f}%;background:"
                    f"{c};border-radius:4px;'></span>"
                    f"<b style='font-size:12.5px;'>{v:+.1f}</b>"
                    "</div>")
            st.markdown("**Net pips per day**",
                        unsafe_allow_html=True)
            st.markdown("".join(_bars), unsafe_allow_html=True)
    _at = report["all_time"]
    if _at["count"]:
        st.caption(
            f"All time (in this snapshot): {_at['count']} "
            f"closed · gross {_at['gross']:+.1f} · "
            f"net {_at['net']:+.1f} pips")
