"""Section 7 — Performance Analytics (user order 2026-11-28).

Advanced statistics + visualization computed from the app's
OWN stored records only: the persistent eval-history store
(live + Replay records), the precheck day log, and the walk
ledgers / historical archive. Zero network fetches.

Every pick is marked to the latest price in the local candle
store via core.data.moved_pips (the same figure shown beside
each pick in the other sections); net = moved - 2.5 pips,
the system's standing convention. These are
marked-to-market figures, NOT settled results — labelled as
such wherever they appear. Honest empty states when a store
holds nothing yet. Never raises.
"""
import json
import os
import sqlite3
from pathlib import Path

_NET_COST = 2.5
_MMT_OFFSET_H = 6.5


def _repo_root():
    return Path(__file__).resolve().parents[1]


def _eval_db_path():
    env = os.environ.get("FOREX_EVAL_HISTORY_DB")
    if env:
        return Path(env)
    return _repo_root() / "data" / "signal_eval_history.sqlite3"


def _load_eval_rows():
    """All eval-history rows (every cycle), newest first.
    Local sqlite read only. Returns [] on any problem."""
    path = _eval_db_path()
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(str(path), timeout=10)
        try:
            try:
                raw = conn.execute(
                    "SELECT cycle, window_utc, entries_json "
                    "FROM signal_eval_history "
                    "ORDER BY window_utc DESC").fetchall()
            except Exception:
                return []
        finally:
            conn.close()
    except Exception:
        return []
    out = []
    for cycle, win, ej in raw:
        try:
            entries = json.loads(ej or "[]")
        except Exception:
            entries = []
        out.append({"cycle": str(cycle), "window_utc": str(win),
                    "entries": entries if isinstance(
                        entries, list) else []})
    return out


def collect_picks():
    """Every recorded pick that can be priced from the local
    candle store: {cycle, source, window_utc, day, symbol,
    direction, entry, moved, net}. Unpriceable picks are
    counted in 'unpriced' and excluded from the sums."""
    from core.data.moved_pips import moved_pips
    picks, unpriced = [], 0
    for row in _load_eval_rows():
        cycle = row["cycle"]
        source = "replay" if cycle.endswith(":replay") else "live"
        base = cycle[:-len(":replay")] if source == "replay" \
            else cycle
        for e in row["entries"]:
            sym = str(e.get("symbol") or "")
            if not sym or e.get("entry") is None:
                continue
            v = moved_pips(sym, e.get("direction"),
                           e.get("entry"))
            if v is None:
                unpriced += 1
                continue
            picks.append({
                "cycle": base, "source": source,
                "window_utc": row["window_utc"],
                "day": row["window_utc"][:10],
                "symbol": sym,
                "direction": str(e.get("direction") or ""),
                "entry": e.get("entry"),
                "moved": float(v), "net": float(v) - _NET_COST})
    picks.sort(key=lambda p: p["window_utc"])
    return picks, unpriced


def summarize(picks):
    """Aggregates over priced picks (pure — unit-testable)."""
    total_net = sum(p["net"] for p in picks)
    wins = sum(1 for p in picks if p["net"] > 0)
    losses = sum(1 for p in picks if p["net"] < 0)
    flat = len(picks) - wins - losses
    daily, curve, run = {}, [], 0.0
    for p in picks:
        daily[p["day"]] = daily.get(p["day"], 0.0) + p["net"]
    for p in picks:
        run += p["net"]
        curve.append((p["window_utc"], round(run, 1)))
    per_cycle, per_symbol = {}, {}
    for p in picks:
        c = per_cycle.setdefault(
            p["cycle"], {"picks": 0, "wins": 0, "net": 0.0})
        c["picks"] += 1
        c["wins"] += 1 if p["net"] > 0 else 0
        c["net"] = round(c["net"] + p["net"], 1)
        s = per_symbol.setdefault(
            p["symbol"], {"picks": 0, "net": 0.0})
        s["picks"] += 1
        s["net"] = round(s["net"] + p["net"], 1)
    return {"total_net": round(total_net, 1), "wins": wins,
            "losses": losses, "flat": flat,
            "win_pct": (100.0 * wins / len(picks)
                        if picks else 0.0),
            "daily": daily, "curve": curve,
            "per_cycle": per_cycle, "per_symbol": per_symbol}


def ledger_stats():
    """Walked/delivered counts per cycle from the walk
    ledgers (current + historical archive). Stored files
    only."""
    out = {}
    root = _repo_root() / "data"
    for sub, keyf in (("walk_ledgers_new8", lambda n: n),
                      ("walk_ledgers_hist",
                       lambda n: n.rsplit("_", 1)[0])):
        d = root / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                state = json.loads(f.read_text())
            except Exception:
                continue
            cyc = keyf(f.stem)
            cur = out.setdefault(
                cyc, {"processed": 0, "delivered": 0})
            cur["processed"] += len(state.get("processed", []))
            cur["delivered"] += len(state.get("delivered", []))
    return out


def precheck_agreement():
    """Precheck-vs-final agreement where BOTH are recorded:
    pairs the precheck day log (MMT date + check HH:MM) with
    eval-history finals for the same MMT date + check time.
    Returns {pairs, agree, pct} or None when no pairs."""
    import datetime as _dt
    try:
        from core import precheck_day_log as _pdl
        rows = _pdl._load()
    except Exception:
        return None
    finals = {}
    for row in _load_eval_rows():
        if row["cycle"].endswith(":replay"):
            continue
        try:
            t = _dt.datetime.fromisoformat(
                row["window_utc"].replace("Z", "+00:00"))
        except Exception:
            continue
        mmt = t + _dt.timedelta(hours=_MMT_OFFSET_H)
        key = (mmt.strftime("%Y-%m-%d"), mmt.strftime("%H:%M"))
        pick = None
        for e in row["entries"]:
            if e.get("symbol"):
                pick = (str(e.get("direction") or "").upper(),
                        str(e["symbol"]).upper())
                break
        finals[key] = pick  # rows are newest-first: keep first
    pairs = agree = 0
    for r in rows:
        key = (str(r.get("date")), str(r.get("check")))
        if key not in finals:
            continue
        res = str(r.get("result") or "")
        if res.startswith("No entry"):
            pre = None
        else:
            parts = res.split()
            if len(parts) >= 2 and parts[0] in ("BUY", "SELL"):
                pre = (parts[0], parts[1].upper())
            else:
                continue
        pairs += 1
        if pre == finals[key]:
            agree += 1
    if not pairs:
        return None
    return {"pairs": pairs, "agree": agree,
            "pct": 100.0 * agree / pairs}


def _css_bars(st, daily, title):
    days = sorted(daily)[-14:]
    if not days:
        return
    mx = max((abs(daily[d]) for d in days), default=1.0) or 1.0
    bars = []
    for d in days:
        v = daily[d]
        w = max(2.0, 100.0 * abs(v) / mx)
        c = "#16a34a" if v >= 0 else "#dc2626"
        bars.append(
            f"<div style='display:flex;align-items:center;"
            f"gap:8px;margin:2px 0;font-size:12px;'>"
            f"<span style='width:86px;color:inherit;'>{d}</span>"
            f"<span style='display:inline-block;height:12px;"
            f"width:{w:.0f}%;max-width:60%;background:{c};"
            f"border-radius:3px;'></span>"
            f"<b>{v:+.1f}</b></div>")
    st.markdown(f"**{title}**", unsafe_allow_html=True)
    st.markdown("".join(bars), unsafe_allow_html=True)


def render_performance_analytics(st):
    st.markdown("---")
    st.markdown(
        "<div style='border:1.5px solid #7c3aed;"
        "border-radius:12px;padding:10px 14px;margin:8px 0 6px 0;"
        "background:linear-gradient(90deg,rgba(124,58,237,.80),"
        "rgba(14,165,233,.70));color:#fff;font-size:18px;"
        "font-weight:800;'>📈 Performance Analytics</div>",
        unsafe_allow_html=True)
    st.caption(
        "Statistics from the app's own stored records only "
        "(eval-history store incl. Replay records, precheck "
        "day log, walk ledgers). Picks are marked to the "
        "latest stored price; net = moved − 2.5 pips. "
        "Marked-to-market — not settled results.")
    try:
        picks, unpriced = collect_picks()
    except Exception:
        picks, unpriced = [], 0
    if not picks:
        st.info(
            "No priced records yet — analytics appear here "
            "once checks, prechecks or Replay calculations "
            "have been recorded in the history store and the "
            "candle store can price them.")
        led = ledger_stats()
        if led:
            import pandas as pd
            st.markdown("**Walk ledgers on record**")
            st.dataframe(pd.DataFrame([
                {"cycle": c, "slots walked": v["processed"],
                 "picks delivered": v["delivered"]}
                for c, v in sorted(led.items())]),
                use_container_width=True)
        return
    s = summarize(picks)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Recorded picks (priced)", len(picks))
    c2.metric("Win % (net > 0)", f"{s['win_pct']:.0f}%")
    c3.metric("Total net pips (MTM)", f"{s['total_net']:+.1f}")
    c4.metric("Win / Loss / Flat",
              f"{s['wins']} / {s['losses']} / {s['flat']}")
    if unpriced:
        st.caption(f"{unpriced} recorded pick(s) could not be "
                   f"priced from the local candle store and "
                   f"are excluded from the sums.")
    # Cumulative net curve.
    st.markdown("**Cumulative net pips over time "
                "(marked-to-market)**")
    charted = False
    try:
        import plotly.graph_objects as _go
        xs = [w for w, _ in s["curve"]]
        ys = [v for _, v in s["curve"]]
        fig = _go.Figure(_go.Scatter(
            x=xs, y=ys, mode="lines",
            line=dict(color="#7c3aed", width=2)))
        fig.update_layout(
            height=230, margin=dict(l=6, r=6, t=6, b=6),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="Check window (UTC)",
            yaxis_title="Cumulative net pips")
        st.plotly_chart(fig, use_container_width=True)
        charted = True
    except Exception:
        charted = False
    if not charted:
        _css_bars(st, s["daily"], "Net pips per day")
    else:
        _css_bars(st, s["daily"], "Net pips per day")
    # Win/loss/flat stacked bar.
    tot = max(1, s["wins"] + s["losses"] + s["flat"])
    st.markdown(
        f"<div style='display:flex;height:16px;border-radius:"
        f"8px;overflow:hidden;margin:6px 0;'>"
        f"<div style='width:{100 * s['wins'] / tot:.1f}%;"
        f"background:#16a34a;'></div>"
        f"<div style='width:{100 * s['losses'] / tot:.1f}%;"
        f"background:#dc2626;'></div>"
        f"<div style='width:{100 * s['flat'] / tot:.1f}%;"
        f"background:#94a3b8;'></div></div>"
        f"<div style='font-size:12px;'>🟩 win {s['wins']} · "
        f"🟥 loss {s['losses']} · ⬜ flat {s['flat']}</div>",
        unsafe_allow_html=True)
    import pandas as pd
    led = ledger_stats()
    if s["per_cycle"]:
        st.markdown("**Per cycle (month system)**")
        rows = []
        for cyc, v in sorted(s["per_cycle"].items()):
            lg = led.get(cyc, {})
            rows.append({
                "cycle": cyc,
                "recorded picks": v["picks"],
                "wins": v["wins"],
                "net pips (MTM)": v["net"],
                "ledger slots walked": lg.get("processed", "—"),
                "ledger picks delivered": lg.get(
                    "delivered", "—")})
        st.dataframe(pd.DataFrame(rows),
                     use_container_width=True)
    if s["per_symbol"]:
        st.markdown("**Most-traded symbols**")
        rows = sorted(
            ({"symbol": k, "picks": v["picks"],
              "net pips (MTM)": v["net"]}
             for k, v in s["per_symbol"].items()),
            key=lambda r: -r["picks"])[:10]
        st.dataframe(pd.DataFrame(rows),
                     use_container_width=True)
    ag = None
    try:
        ag = precheck_agreement()
    except Exception:
        ag = None
    if ag:
        st.markdown(
            f"**Precheck vs final agreement: "
            f"{ag['pct']:.0f}%** — {ag['agree']} of "
            f"{ag['pairs']} paired slots recorded the same "
            f"pick (or both no-pick).")
    else:
        st.caption(
            "Precheck-vs-final agreement: not enough paired "
            "records yet (needs a precheck and a final "
            "recorded for the same check).")
