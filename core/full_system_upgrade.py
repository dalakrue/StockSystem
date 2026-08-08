"""V21 full-system polish layer.

Non-destructive upgrade module for Home, Sidebar, Engine, Train Data,
Database, Profile, CSS/UIUX, helper functions, background effects, and popup
feedback. It never replaces original tab logic; wrappers can call these helpers
before/after existing implementations.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd
import streamlit as st


@dataclass(frozen=True)
class SystemHealth:
    source: str
    symbol: str
    timeframe: str
    rows: int
    connected: bool
    stale_minutes: float
    data_quality: str


def _now() -> float:
    try:
        return time.time()
    except Exception:
        return 0.0


def safe_len(obj: Any) -> int:
    try:
        return len(obj) if obj is not None else 0
    except Exception:
        return 0


def get_shared_df() -> pd.DataFrame:
    """Return the best available shared market dataframe without mutating it."""
    for key in ("last_df", "shared_df", "market_df", "doo_df", "cached_df"):
        val = st.session_state.get(key)
        if isinstance(val, pd.DataFrame) and not val.empty:
            return val.copy()
    return pd.DataFrame()


def normalize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize common OHLC aliases into open/high/low/close/time columns."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    out = df.copy()
    aliases = {
        "time": ["time", "datetime", "date", "timestamp", "Time"],
        "open": ["open", "o", "Open"],
        "high": ["high", "h", "High"],
        "low": ["low", "l", "Low"],
        "close": ["close", "c", "Close", "price"],
        "volume": ["volume", "tick_volume", "real_volume", "Volume"],
    }
    for canonical, names in aliases.items():
        if canonical in out.columns:
            continue
        for name in names:
            if name in out.columns:
                out[canonical] = out[name]
                break
    if "time" in out.columns:
        out["time"] = pd.to_datetime(out["time"], errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def system_health() -> SystemHealth:
    df = get_shared_df()
    rows = int(len(df)) if isinstance(df, pd.DataFrame) else 0
    last_fetch = float(st.session_state.get("last_fetch", 0) or 0)
    stale_minutes = max(0.0, (_now() - last_fetch) / 60.0) if last_fetch else 9999.0
    connected = bool(st.session_state.get("connected", False)) and rows > 0
    if rows <= 0:
        q = "NO DATA"
    elif stale_minutes > 30:
        q = "STALE"
    elif rows < 100:
        q = "THIN"
    else:
        q = "OK"
    return SystemHealth(
        source=str(st.session_state.get("source", "DISCONNECTED")),
        symbol=str(st.session_state.get("symbol", "XAUUSD")),
        timeframe=str(st.session_state.get("timeframe", "M1")),
        rows=rows,
        connected=connected,
        stale_minutes=stale_minutes,
        data_quality=q,
    )


def apply_v21_uiux() -> None:
    """Extra CSS: glass background, compact mobile grid, popup animation, tables."""
    phone = bool(st.session_state.get("phone_mode", False))
    gap = "0.32rem" if phone else "0.56rem"
    radius = "14px" if phone else "20px"
    st.markdown(
        f"""
<style>
:root {{
  --v21-bg1: rgba(255,255,255,.82);
  --v21-bg2: rgba(224,242,254,.62);
  --v21-line: rgba(14,116,144,.16);
  --v21-blue: #0284c7;
  --v21-ink: #0f172a;
}}
.stApp:before {{
  content:""; position:fixed; inset:0; pointer-events:none; z-index:0;
  background:
    radial-gradient(circle at 12% 18%, rgba(56,189,248,.22), transparent 22%),
    radial-gradient(circle at 86% 12%, rgba(59,130,246,.17), transparent 24%),
    radial-gradient(circle at 78% 82%, rgba(125,211,252,.18), transparent 30%);
  animation:v21Float 12s ease-in-out infinite alternate;
}}
@keyframes v21Float {{ from {{ transform:translate3d(0,0,0) scale(1); }} to {{ transform:translate3d(0,-10px,0) scale(1.018); }} }}
@keyframes v21Pop {{ from {{ transform:translateY(8px) scale(.985); opacity:0; }} to {{ transform:translateY(0) scale(1); opacity:1; }} }}
.v21-card, .v21-pop, .v21-shell, div[data-testid="stExpander"] details {{
  border-radius:{radius}!important;
  border:1px solid var(--v21-line)!important;
  background:linear-gradient(135deg,var(--v21-bg1),var(--v21-bg2))!important;
  box-shadow:0 10px 30px rgba(2,132,199,.08), inset 0 1px 0 rgba(255,255,255,.74)!important;
  backdrop-filter:blur(20px) saturate(170%)!important;
}}
.v21-pop {{ padding:.75rem .85rem; margin:.35rem 0; animation:v21Pop .22s ease both; }}
.v21-title {{ font-weight:900; color:var(--v21-ink); letter-spacing:-.02em; }}
.v21-muted {{ color:#075985; opacity:.86; font-size:.86rem; }}
.v21-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax({ '106px' if phone else '150px' },1fr)); gap:{gap}; margin:.45rem 0 .7rem; }}
.v21-kpi {{ padding:.65rem .7rem; border-radius:{radius}; border:1px solid var(--v21-line); background:rgba(255,255,255,.72); }}
.v21-kpi b {{ display:block; font-size:{ '1.02rem' if phone else '1.20rem' }; line-height:1.12; }}
.v21-kpi span {{ color:#075985; font-weight:800; font-size:.72rem; }}
[data-testid="stDataFrame"] {{ border-radius:{radius}!important; overflow:hidden!important; }}
textarea, input, .stTextInput input, .stNumberInput input {{ border-radius:14px!important; }}
section[data-testid="stSidebar"] .v21-sidebar-sticky {{ position:sticky; top:.25rem; z-index:5; }}
@media (max-width: 760px) {{
  .main .block-container {{ padding-left:.32rem!important; padding-right:.32rem!important; }}
  .v21-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
  div[data-testid="column"] {{ min-width:0!important; }}
}}
</style>
""",
        unsafe_allow_html=True,
    )


def render_kpi_grid(items: Sequence[Mapping[str, Any]]) -> None:
    html = ['<div class="v21-grid">']
    for item in items:
        label = str(item.get("label", ""))
        value = str(item.get("value", "—"))
        delta = str(item.get("delta", ""))
        html.append(f'<div class="v21-kpi"><span>{label}</span><b>{value}</b><small>{delta}</small></div>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_upgrade_banner(tab_name: str, subtitle: str = "") -> None:
    h = system_health()
    st.markdown(
        f"""
<div class="v21-pop">
  <div class="v21-title">✨ V21 {tab_name} Upgrade Layer</div>
  <div class="v21-muted">{subtitle or 'Original logic preserved. Extra guardrails, compact UI, health checks, and helper tools are active.'}</div>
</div>
""",
        unsafe_allow_html=True,
    )
    render_kpi_grid([
        {"label": "Source", "value": h.source, "delta": h.data_quality},
        {"label": "Symbol", "value": h.symbol, "delta": h.timeframe},
        {"label": "Rows", "value": f"{h.rows:,}", "delta": "shared dataframe"},
        {"label": "Stale", "value": f"{h.stale_minutes:.1f}m" if h.stale_minutes < 999 else "—", "delta": "refresh age"},
    ])


def queue_popup(message: str, level: str = "info") -> None:
    st.session_state["v21_popup"] = {"message": str(message), "level": str(level), "ts": _now()}


def render_popup() -> None:
    pop = st.session_state.get("v21_popup")
    if not isinstance(pop, dict):
        return
    age = _now() - float(pop.get("ts", 0) or 0)
    if age > 10:
        return
    icon = {"success": "✅", "warning": "⚠️", "error": "⛔", "info": "💡"}.get(str(pop.get("level")), "💡")
    st.markdown(f'<div class="v21-pop">{icon} {pop.get("message", "")}</div>', unsafe_allow_html=True)


def render_home_upgrade_panel() -> None:
    render_upgrade_banner("Home", "Fast copy/refresh, TP range helper, live data health, and mobile glass cards.")
    df = normalize_ohlc(get_shared_df())
    with st.expander("📌 Open / Close — V21 Home TP + Range Helper", expanded=False):
        if df.empty or "close" not in df.columns:
            st.info("Connect or refresh market data first. This helper will not block the original Home tab.")
            return
        close = df["close"].dropna()
        high = df["high"].dropna() if "high" in df.columns else close
        low = df["low"].dropna() if "low" in df.columns else close
        if close.empty:
            st.info("Close prices not available yet.")
            return
        price = float(close.iloc[-1])
        atr_like = float((df["high"] - df["low"]).rolling(14, min_periods=1).mean().dropna().iloc[-1]) if {"high", "low"}.issubset(df.columns) else max(price * 0.0015, 1.0)
        trend = "BUY pressure" if len(close) > 5 and close.iloc[-1] >= close.iloc[-5] else "SELL pressure / pullback"
        render_kpi_grid([
            {"label": "Now", "value": f"{price:.2f}", "delta": trend},
            {"label": "ATR-like", "value": f"{atr_like:.2f}", "delta": "14 bars"},
            {"label": "BUY TP1", "value": f"{price + atr_like*0.65:.2f}", "delta": "conservative"},
            {"label": "BUY TP2", "value": f"{price + atr_like*1.25:.2f}", "delta": "normal"},
            {"label": "SELL TP1", "value": f"{price - atr_like*0.65:.2f}", "delta": "conservative"},
            {"label": "SELL TP2", "value": f"{price - atr_like*1.25:.2f}", "delta": "normal"},
        ])
        st.caption("TP helper is calculated from the active shared dataframe only. It is a decision aid, not an order sender.")


def render_engine_upgrade_panel() -> None:
    render_upgrade_banner("Engine", "Decision matrix guardrail, websocket status, noise risk note, and inner-tab safety.")
    with st.expander("⚡ Open / Close — V21 Engine Decision Guardrail", expanded=False):
        df = normalize_ohlc(get_shared_df())
        if df.empty or "close" not in df.columns:
            st.info("Need shared market data for the guardrail matrix.")
            return
        close = df["close"].dropna()
        ret1 = float(close.pct_change().tail(1).iloc[-1] * 100) if len(close) > 2 else 0.0
        ret5 = float((close.iloc[-1] / close.iloc[-5] - 1) * 100) if len(close) > 5 else 0.0
        decision = "BUY HOLD / WAIT TP" if ret5 > 0 and ret1 >= -0.05 else "WAIT / PROTECT" if abs(ret5) < 0.08 else "SELL PRESSURE"
        render_kpi_grid([
            {"label": "1-Bar Return", "value": f"{ret1:+.3f}%", "delta": "latest"},
            {"label": "5-Bar Return", "value": f"{ret5:+.3f}%", "delta": "short momentum"},
            {"label": "Guardrail", "value": decision, "delta": "no auto-trade"},
        ])


def render_train_upgrade_panel() -> None:
    render_upgrade_banner("Train Data", "Incremental learning status, feature readiness, and current/previous DB workflow.")
    with st.expander("🧠 Open / Close — V21 Incremental Training Checklist", expanded=False):
        df = normalize_ohlc(get_shared_df())
        rows = len(df)
        cols = set(df.columns)
        needed = ["open", "high", "low", "close"]
        ready = all(c in cols for c in needed) and rows >= 100
        render_kpi_grid([
            {"label": "Training Rows", "value": f"{rows:,}", "delta": "current shared"},
            {"label": "OHLC Ready", "value": "YES" if ready else "NO", "delta": ", ".join([c for c in needed if c not in cols]) or "complete"},
            {"label": "Mode", "value": "Incremental", "delta": "append-safe"},
        ])
        st.caption("The original Train Data logic still runs below. This panel only checks readiness and does not overwrite models.")


def render_database_upgrade_panel() -> None:
    render_upgrade_banner("Database", "Read-only DB health, file awareness, preview safety, and export centralization.")
    with st.expander("🗄️ Open / Close — V21 Database Safety Notes", expanded=False):
        st.write("• Database tab remains read-only by default.")
        st.write("• Exports stay centralized in the sidebar to avoid duplicate buttons.")
        st.write("• Large tables should be previewed with row limits before filtering.")


def render_profile_upgrade_panel() -> None:
    render_upgrade_banner("Profile", "System profile, UI preferences, runtime state, and project health overview.")
    with st.expander("👤 Open / Close — V21 Profile Runtime", expanded=False):
        h = system_health()
        st.json({
            "connected": h.connected,
            "source": h.source,
            "symbol": h.symbol,
            "timeframe": h.timeframe,
            "rows": h.rows,
            "phone_mode": bool(st.session_state.get("phone_mode", False)),
            "websocket_enabled": bool(st.session_state.get("ws_enabled", False)),
        })


def render_sidebar_v21_top() -> None:
    h = system_health()
    st.markdown('<div class="v21-sidebar-sticky">', unsafe_allow_html=True)
    st.markdown(f"**✨ V21 Control**  \n{h.symbol} · {h.timeframe} · {h.source} · {h.rows:,} rows")
    st.markdown('</div>', unsafe_allow_html=True)


def build_copy_payload() -> str:
    """JSON payload for Copy All Data fallback helpers."""
    h = system_health()
    df = normalize_ohlc(get_shared_df())
    tail = []
    try:
        tail = df.tail(12).to_dict(orient="records") if not df.empty else []
    except Exception:
        tail = []
    payload = {
        "export_time": pd.Timestamp.now().isoformat(),
        "symbol": h.symbol,
        "timeframe": h.timeframe,
        "source": h.source,
        "rows": h.rows,
        "connected": h.connected,
        "data_quality": h.data_quality,
        "account_snapshot": st.session_state.get("account_snapshot", {}),
        "tail_12_rows": tail,
        "eurusd_h1_decision_matrix": st.session_state.get("eurusd_h1_matrix_export", {}),
        "custom_timeframe_frames": {
            "custom_h1_rows": len(st.session_state.get("custom_h1_df")) if hasattr(st.session_state.get("custom_h1_df"), "__len__") else 0,
            "custom_m1_rows": len(st.session_state.get("custom_m1_df")) if hasattr(st.session_state.get("custom_m1_df"), "__len__") else 0,
            "rule": "H1 main data; M1 confirmation/pullback timing only; do not mix."
        },
    }
    return json.dumps(payload, default=str, indent=2)
