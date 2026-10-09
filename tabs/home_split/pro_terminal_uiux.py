"""Home/Doo Prime professional terminal widgets.

This module is additive: it only renders UI summaries from existing session data.
"""
from __future__ import annotations

import html
from typing import Any

import pandas as pd
import streamlit as st

from core.pro_terminal_uiux import apply_pro_terminal_css
from core.v6_final_ui_logic_patch import get_best_shared_df


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        out = float(v)
        if pd.isna(out):
            return default
        return out
    except Exception:
        return default


def _fmt(v: Any, digits: int = 2) -> str:
    n = _num(v, None)
    if n is None:
        return str(v or "N/A")
    return f"{n:.{digits}f}"


def _latest_df() -> pd.DataFrame:
    # Do not copy large OHLC frames for visual-only Home header.
    # V6 uses all known shared-data keys so the hero does not show Rows 0 when data is loaded.
    return get_best_shared_df()


def _deep_market_values() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        results = st.session_state.get("doo_deep_results", {}) or {}
        for item in results.values():
            if not isinstance(item, dict):
                continue
            market = item.get("market", {}) or {}
            for k, v in market.items():
                out.setdefault(str(k), v)
    except Exception:
        pass
    return out


def _derive_snapshot() -> dict[str, Any]:
    df = _latest_df()
    market = _deep_market_values()
    last_close = _num(market.get("price", market.get("close", st.session_state.get("last_close", 0))))
    if not last_close and not df.empty and "close" in df.columns:
        last_close = _num(df["close"].iloc[-1])

    adx = _num(market.get("adx", market.get("ADX", st.session_state.get("adx", 0))))
    pressure = _num(market.get("pressure", market.get("directional_pressure", st.session_state.get("pressure", 0))))
    fat_tail = _num(market.get("fat_tail_z", market.get("fat_tail", 0)))
    dve = _num(market.get("dve_%", market.get("dve", market.get("DVE", 0))))
    rising = _num(market.get("rising_eff_%", market.get("rising_eff", 0)))
    falling = _num(market.get("falling_eff_%", market.get("falling_eff", 0)))
    trust = _num(market.get("trust_%", market.get("trust", st.session_state.get("trust", 0))))

    reversal = _num(st.session_state.get("last_reversal_score", st.session_state.get("reversal_score", 0)))
    try:
        scan = st.session_state.get("home_reversal_25d_scan")
        if isinstance(scan, pd.DataFrame) and not scan.empty:
            if "score" in scan.columns:
                reversal = max(reversal, _num(scan["score"].max()))
            elif "decision" in scan.columns:
                reversal = max(reversal, _num(scan["decision"].astype(str).str.extract(r"(\d+)")[0].dropna().astype(float).max()))
    except Exception:
        pass

    if not reversal:
        # Conservative visual fallback only; actual engine is unchanged.
        reversal = max(0, min(10, round((abs(fat_tail) >= 2.5) + (adx > 25) + (abs(pressure) > 10) + (max(rising, falling) > 45) + (trust < 45), 0)))

    direction = str(market.get("direction", st.session_state.get("mini_bias", "WAIT"))).upper()
    if direction in ("UP", "BUY/UP", "BULL", "BULLISH"):
        direction = "BUY"
    elif direction in ("DOWN", "SELL/DOWN", "BEAR", "BEARISH"):
        direction = "SELL"
    elif not direction or direction == "NAN":
        direction = "WAIT"

    margin = _num(st.session_state.get("margin_level_pct", st.session_state.get("doo_margin_level", 0)))
    health = 70
    if margin:
        health = min(100, max(0, margin - 30))
    pulse = int(max(0, min(100, (trust or 55) + min(adx, 40) * .45 - reversal * 4)))

    if reversal >= 7:
        danger = "HIGH"
    elif reversal >= 5:
        danger = "MEDIUM"
    else:
        danger = "LOW"

    return {
        "price": last_close,
        "adx": adx,
        "pressure": pressure,
        "fat_tail": fat_tail,
        "dve": dve,
        "rising": rising,
        "falling": falling,
        "trust": trust,
        "reversal": int(round(reversal)),
        "direction": direction,
        "margin": margin,
        "health": int(max(0, min(100, health))),
        "pulse": pulse,
        "danger": danger,
        "rows": len(df) if isinstance(df, pd.DataFrame) else 0,
    }


def _heat_icon(name: str, snap: dict[str, Any]) -> str:
    if name == "ADX":
        return "🟢" if snap["adx"] >= 25 else "🟡"
    if name == "Pressure":
        return "🟢" if abs(snap["pressure"]) >= 10 else "🟡"
    if name == "Fat Tail":
        return "🔴" if abs(snap["fat_tail"]) >= 2.5 else "🟢"
    if name == "DVE":
        return "🟢" if snap["dve"] >= 45 else "🟡"
    if name == "Reversal":
        return "🔴" if snap["reversal"] >= 7 else ("🟡" if snap["reversal"] >= 5 else "🟢")
    return "⚪"


def _timeline_rows() -> str:
    rows = []
    scan = st.session_state.get("home_reversal_25d_scan")
    if isinstance(scan, pd.DataFrame) and not scan.empty:
        data = scan.copy().tail(6)
        for _, r in data.iterrows():
            date = str(r.get("time", r.get("date", r.get("hour", "Loaded"))))[:10]
            score = _num(r.get("score", r.get("active_count", 0)))
            if not score and "decision" in r:
                score = _num(str(r.get("decision", "")).split("/")[0])
            rows.append((date, int(max(0, min(10, score)))))
    if not rows:
        rows = [("Latest", 0), ("Need data", 0), ("25D scan", 0)]
    html_rows = []
    for date, score in rows[-6:]:
        width = max(3, score * 10)
        html_rows.append(
            f'<div class="qx-line-row"><div class="qx-line-date">{html.escape(str(date))}</div><div class="qx-line-bar"><div class="qx-line-fill" style="--w:{width}%"></div></div><div class="qx-line-score">{score}/10</div></div>'
        )
    return "".join(html_rows)


def render_home_pro_terminal() -> None:
    apply_pro_terminal_css()
    snap = _derive_snapshot()
    mode = "danger" if snap["reversal"] >= 7 else ("trend" if snap["adx"] > 25 else "calm")
    if snap["reversal"] >= 7:
        st.markdown(
            f'<div class="qx-alert-popup"><b>⚠ REVERSAL ALERT — Score: {snap["reversal"]}/10</b><span>Trend exhaustion / pressure transfer / shock-move monitor is in danger mode. Use this as warning UI only; original reversal engine remains unchanged.</span></div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        f'''
<div class="qx-terminal-hero qx-market-{mode}">
  <div class="qx-terminal-inner">
    <div>
      <div class="qx-terminal-title">⚡ Professional Quant Trading Terminal</div>
      <div class="qx-terminal-sub">Glassmorphism command center with dynamic market mood, 10-Reversal alert layer, Doo/Finder summary, and interview-ready dashboard visuals.</div>
      <div class="qx-terminal-badges"><span class="qx-chip">{html.escape(snap["direction"])}</span><span class="qx-chip">Rows {snap["rows"]:,}</span><span class="qx-chip">Danger {snap["danger"]}</span><span class="qx-chip">Reversal {snap["reversal"]}/10</span></div>
    </div>
    <div class="qx-hero-grid">
      <div class="qx-hero-card"><b>Account Health</b><span>{snap["health"]}%</span></div>
      <div class="qx-hero-card"><b>Market Pulse</b><span>{snap["pulse"]}</span></div>
      <div class="qx-hero-card"><b>Reversal Danger</b><span>{snap["reversal"]}/10</span></div>
      <div class="qx-hero-card"><b>Margin Safety</b><span>{_fmt(snap["margin"], 1)}%</span></div>
    </div>
  </div>
</div>
<div class="qx-pulse-wrap"><div class="qx-pulse-ring" style="--score:{snap["pulse"]}%"><div class="qx-pulse-core"><strong>{snap["pulse"]}</strong><small>{html.escape(snap["direction"])} PULSE</small></div></div></div>
<div class="qx-heatmap">
  {''.join(f'<div class="qx-heat"><b>{name}</b><span>{_heat_icon(name, snap)}</span></div>' for name in ["ADX","Pressure","Fat Tail","DVE","Reversal"])}
</div>
''',
        unsafe_allow_html=True,
    )
    with st.expander("🕒 Open 10-Reversal Timeline — Last 25 Days", expanded=False):
        st.markdown(f'<div class="qx-timeline">{_timeline_rows()}</div>', unsafe_allow_html=True)
        st.caption("This visual reads existing 25D reversal scan state when available. It does not alter the reversal calculation.")

    st.markdown(
        f'''
<div class="qx-assistant">
  <div class="qx-assistant-title">🤖 Quant Assistant</div>
  <div class="qx-assistant-grid">
    <div class="qx-assistant-cell"><b>Trend</b><span>{html.escape(snap["direction"])}</span></div>
    <div class="qx-assistant-cell"><b>12H Prob.</b><span>{snap["pulse"]}%</span></div>
    <div class="qx-assistant-cell"><b>Danger</b><span>{snap["danger"]}</span></div>
    <div class="qx-assistant-cell"><b>Last Rev.</b><span>{snap["reversal"]}/10</span></div>
  </div>
</div>
''',
        unsafe_allow_html=True,
    )


def install(g: dict[str, Any]) -> None:
    """Wrap Finder in one open/close shell after older patches install."""
    old = g.get("_render_doo_finder")

    def _wrapped_finder(results):
        apply_pro_terminal_css()
        st.markdown('<div class="qx-finder-shell">', unsafe_allow_html=True)
        with st.expander("🔎 Open / Close Finder Pro Replay + Doo Metrics", expanded=True):
            st.caption("All Finder controls, same-as-Doo metric tables, 10-Reversal scan, candle preview, and copy output are grouped here so the top of Finder stays clean.")
            if callable(old):
                out = old(results)
            else:
                out = st.warning("Finder renderer is not available in this build.")
        st.markdown('</div>', unsafe_allow_html=True)
        return out

    g["_render_doo_finder"] = _wrapped_finder


__all__ = ["render_home_pro_terminal", "install"]
