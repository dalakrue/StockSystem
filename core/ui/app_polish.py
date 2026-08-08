"""Next-level soft-light UI/UX polish layer.

Visual-only upgrade. This module does not change trading logic, calculations,
connector behavior, tab functions, model outputs, or signal generation. It only
adds a softer premium light theme, real-app shell, mobile spacing, safer visual
containers, and clearer status presentation.
"""
from __future__ import annotations

import html
from typing import Any

import streamlit as st


def _safe_text(value: Any, default: str = "-") -> str:
    try:
        if value is None or value == "":
            return default
        return html.escape(str(value))
    except Exception:
        return default


def _rows_count() -> int:
    try:
        df = st.session_state.get("last_df") or st.session_state.get("shared_df")
        return int(len(df)) if df is not None else 0
    except Exception:
        return 0


def apply_next_level_uiux() -> None:
    """Inject visual-only soft-light CSS. Safe to call every rerun."""
    st.markdown(
        """
<style>
:root{
  --app-bg-0:#eef7fb; --app-bg-1:#e7f2f6; --app-bg-2:#dfeef4;
  --app-card:rgba(255,255,255,.62); --app-card-2:rgba(248,252,255,.46);
  --app-line:rgba(15,118,140,.14); --app-line-strong:rgba(8,145,178,.28);
  --app-text:#0f172a; --app-muted:#557083; --app-soft:#f8fbfd;
  --app-cyan:#0891b2; --app-blue:#2563eb; --app-green:#059669; --app-red:#e11d48;
  --app-amber:#b45309; --app-radius:24px;
}
html, body, [data-testid="stAppViewContainer"]{
  background:
    radial-gradient(circle at 10% 2%, rgba(125,211,252,.34), transparent 30%),
    radial-gradient(circle at 88% 0%, rgba(153,246,228,.30), transparent 28%),
    radial-gradient(circle at 50% 105%, rgba(219,234,254,.56), transparent 42%),
    linear-gradient(135deg, var(--app-bg-0), var(--app-bg-1) 52%, var(--app-bg-2))!important;
  color:var(--app-text)!important;
}
[data-testid="stAppViewContainer"]:before{content:"";position:fixed;inset:0;pointer-events:none;background-image:linear-gradient(rgba(15,23,42,.025) 1px, transparent 1px),linear-gradient(90deg,rgba(15,23,42,.025) 1px, transparent 1px);background-size:28px 28px;mask-image:linear-gradient(to bottom,rgba(0,0,0,.65),transparent 75%);}
.block-container{padding-top:1rem!important; max-width:1480px!important;}
[data-testid="stHeader"]{background:rgba(238,247,251,.72)!important;backdrop-filter:blur(18px)!important;}
[data-testid="stSidebar"]{
  background:linear-gradient(180deg, rgba(248,252,255,.92), rgba(229,244,250,.88))!important;
  border-right:1px solid var(--app-line)!important; box-shadow:12px 0 32px rgba(14,116,144,.08)!important;
}
[data-testid="stSidebar"] *{color:#0f172a!important;}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] label, [data-testid="stSidebar"] span{color:#173247!important;}
.app-shell-hero{
  position:relative; overflow:hidden; border:1px solid var(--app-line-strong); border-radius:30px;
  padding:18px 18px 15px; margin:0 0 16px;
  background:linear-gradient(135deg, rgba(255,255,255,.70), rgba(224,242,254,.44) 48%, rgba(240,253,250,.46));
  box-shadow:0 22px 62px rgba(14,116,144,.13), inset 0 1px 0 rgba(255,255,255,.80);
  backdrop-filter:blur(22px) saturate(175%);
}
.app-shell-hero:before{content:""; position:absolute; inset:-90px -35px auto auto; width:280px; height:280px;
  border-radius:999px; background:radial-gradient(circle, rgba(8,145,178,.20), transparent 66%); pointer-events:none;}
.app-shell-hero:after{content:""; position:absolute; left:-80px; bottom:-120px; width:260px; height:260px; border-radius:999px; background:radial-gradient(circle, rgba(45,212,191,.18), transparent 66%); pointer-events:none;}
.app-kicker{font-size:12px; font-weight:950; letter-spacing:.14em; text-transform:uppercase; color:#0e7490;}
.app-title{font-size:clamp(24px,4vw,40px); line-height:1.04; font-weight:950; margin:2px 0 7px;
  background:linear-gradient(90deg, #0f172a, #075985 50%, #0f766e); -webkit-background-clip:text; color:transparent;}
.app-subtitle{color:var(--app-muted); font-size:14px; max-width:900px; font-weight:720;}
.app-pill-row{display:flex; flex-wrap:wrap; gap:8px; margin-top:13px; position:relative; z-index:1;}
.app-pill{border:1px solid rgba(14,116,144,.16); border-radius:999px; padding:8px 11px; background:rgba(255,255,255,.56);
  color:#17435b; font-size:12px; font-weight:900; display:inline-flex; gap:7px; align-items:center; box-shadow:0 8px 18px rgba(14,116,144,.06), inset 0 1px 0 rgba(255,255,255,.70);}
.app-dot{width:8px; height:8px; border-radius:99px; background:var(--app-green); box-shadow:0 0 18px rgba(5,150,105,.55);}
.app-dot.warn{background:#d97706; box-shadow:0 0 18px rgba(217,119,6,.45);}
.stButton>button, .stDownloadButton>button, section[data-testid="stSidebar"] .stButton>button{
  border-radius:999px!important; border:1px solid rgba(14,116,144,.18)!important;
  background:linear-gradient(135deg, rgba(255,255,255,.88), rgba(224,242,254,.76) 48%, rgba(204,251,241,.72))!important;
  color:#075985!important; font-weight:950!important; letter-spacing:.01em; min-height:44px;
  box-shadow:0 12px 26px rgba(14,116,144,.12), inset 0 1px 0 rgba(255,255,255,.80)!important;
  transition:transform .16s ease, box-shadow .16s ease, border-color .16s ease, filter .16s ease;
  touch-action:manipulation!important; -webkit-tap-highlight-color:transparent!important;
}
.stButton>button:hover, .stDownloadButton>button:hover{transform:translateY(-1px); filter:saturate(1.08); box-shadow:0 16px 36px rgba(14,116,144,.18)!important; border-color:rgba(8,145,178,.38)!important; color:#0f766e!important;}
.stButton>button:active, .stDownloadButton>button:active{transform:translateY(1px) scale(.99); background:linear-gradient(135deg, rgba(224,242,254,.92), rgba(204,251,241,.82))!important;}
div[data-testid="stMetric"], div[data-testid="stExpander"], div[data-testid="stDataFrame"], div[data-testid="stPlotlyChart"], div[data-testid="stPyplot"]{
  border-radius:var(--app-radius)!important; border:1px solid var(--app-line)!important;
  background:linear-gradient(180deg, rgba(255,255,255,.64), rgba(240,249,255,.44))!important;
  box-shadow:0 14px 34px rgba(14,116,144,.10), inset 0 1px 0 rgba(255,255,255,.78)!important; overflow:hidden!important;
  backdrop-filter:blur(16px) saturate(155%);
}
div[data-testid="stMetric"]{padding:13px 14px!important;}
div[data-testid="stMetric"] label{color:#075985!important; font-weight:900!important;}
div[data-testid="stMetricValue"]{font-weight:950!important; letter-spacing:-.03em; color:#0f172a!important;}
div[data-testid="stMetricDelta"]{font-weight:900!important;}
[data-testid="stMarkdownContainer"] h1,[data-testid="stMarkdownContainer"] h2,[data-testid="stMarkdownContainer"] h3{color:#0f172a!important;letter-spacing:-.02em;}
[data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] li{color:#244055!important;}
div[data-testid="stDataFrame"]{padding:4px!important;}
.stTabs [data-baseweb="tab-list"]{gap:8px; background:rgba(255,255,255,.44); border:1px solid var(--app-line); border-radius:999px; padding:6px; box-shadow:inset 0 1px 0 rgba(255,255,255,.8);}
.stTabs [data-baseweb="tab"]{border-radius:999px; font-weight:950; padding:8px 14px; color:#17435b;}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg, rgba(14,165,233,.18), rgba(20,184,166,.16)); color:#075985!important; box-shadow:0 8px 18px rgba(14,116,144,.10);}
[data-testid="stAlert"]{border-radius:20px!important; border:1px solid var(--app-line)!important; background:rgba(255,255,255,.62)!important; color:#0f172a!important;}
input, textarea, [data-baseweb="select"] > div{border-radius:16px!important; border-color:rgba(14,116,144,.18)!important; background:rgba(255,255,255,.72)!important; color:#0f172a!important;}
hr{border-color:var(--app-line)!important;}
/* readable dataframe/toolbars on soft theme */
[data-testid="stDataFrame"] *{color:#0f172a!important;}
/* premium cards used by older patches */
.qx-terminal-hero,.qx-home-pop-card,.qx-command-lite{background:linear-gradient(135deg,rgba(255,255,255,.66),rgba(224,242,254,.40))!important;border-color:rgba(14,116,144,.16)!important;box-shadow:0 18px 46px rgba(14,116,144,.10)!important;}
.qx-terminal-title,.qx-command-lite-title{color:#0f172a!important}.qx-terminal-sub{color:#557083!important}.qx-hero-card,.qx-command-lite-card{background:rgba(255,255,255,.58)!important;border-color:rgba(14,116,144,.14)!important;}
.qx-hero-card b,.qx-command-lite-card b{color:#075985!important}.qx-hero-card span,.qx-command-lite-card span{color:#0f172a!important;}
@media (max-width: 820px){
  .block-container{padding:.55rem .55rem 4.5rem!important;}
  .app-shell-hero{border-radius:22px; padding:14px; margin-bottom:12px;}
  .app-subtitle{font-size:12.5px}.app-pill{font-size:11px; padding:7px 9px;}
  [data-testid="stHorizontalBlock"]{gap:.5rem!important; flex-wrap:wrap!important;}
  .stButton>button,.stDownloadButton>button{min-height:48px!important; font-size:14px!important; white-space:normal!important;}
  div[data-testid="stMetric"]{padding:10px 11px!important; border-radius:18px!important;}
  .stTabs [data-baseweb="tab-list"]{overflow-x:auto; flex-wrap:nowrap; justify-content:flex-start;}
  section[data-testid="stSidebar"]{width:min(88vw,340px)!important;}
  [data-testid="stDataFrame"]{overflow-x:auto!important;}
}
</style>
        """,
        unsafe_allow_html=True,
    )
    try:
        big_mobile = bool(st.session_state.get("phone_mode", False)) or bool(st.session_state.get("mobile_app_big_mode_20260612", False))
        if big_mobile:
            st.markdown(
                """
<style>
@media (max-width: 920px){
  .block-container{padding-left:.38rem!important;padding-right:.38rem!important;padding-bottom:6rem!important;}
  .stButton>button,.stDownloadButton>button{min-height:58px!important;font-size:17px!important;font-weight:950!important;border-radius:22px!important;}
  div[data-testid="stMetric"]{padding:15px 14px!important;border-radius:22px!important;}
  div[data-testid="stMetricValue"]{font-size:1.55rem!important;}
  [data-testid="stMarkdownContainer"] h1{font-size:1.85rem!important;}
  [data-testid="stMarkdownContainer"] h2{font-size:1.55rem!important;}
  [data-testid="stMarkdownContainer"] h3{font-size:1.32rem!important;}
  .stTabs [data-baseweb="tab"]{font-size:15px!important;padding:10px 16px!important;}
  input, textarea, [data-baseweb="select"] > div{font-size:16px!important;min-height:48px!important;}
  [data-testid="stHorizontalBlock"]{gap:.45rem!important;}
}
</style>
                """,
                unsafe_allow_html=True,
            )
    except Exception:
        pass


def render_real_app_header(active_tab: str | None = None) -> None:
    """Render a compact premium app header using current session state only."""
    # 2026-06-12: On Lunch, the user asked to move Quant Control Center into
    # the merged NY/London open/close field to reduce stacked sections.
    tab_check = _safe_text(active_tab or st.session_state.get("tab_choice", "Lunch"), "Lunch")
    if tab_check in {"Lunch", "Home"} and bool(st.session_state.get("lunch_merge_global_status_20260612", True)):
        st.session_state["quant_control_center_snapshot_20260612"] = {
            "symbol": st.session_state.get("symbol", "EURUSD"),
            "timeframe": st.session_state.get("timeframe", "H1"),
            "source": st.session_state.get("source", st.session_state.get("connector_mode", "DISCONNECTED")),
            "tab": tab_check,
            "rows": _rows_count(),
            "phone_mode": bool(st.session_state.get("phone_mode", False)),
        }
        return
    symbol = _safe_text(st.session_state.get("symbol", "EURUSD"), "EURUSD")
    timeframe = _safe_text(st.session_state.get("timeframe", "H1"), "H1")
    source = _safe_text(st.session_state.get("source", st.session_state.get("connector_mode", "DISCONNECTED")), "DISCONNECTED")
    tab = _safe_text(active_tab or st.session_state.get("tab_choice", "Lunch"), "Lunch")
    rows = _rows_count()
    phone = bool(st.session_state.get("phone_mode", False))
    rows_badge = f"{rows:,} rows" if rows else "No data loaded"
    dot_class = "" if rows else " warn"
    mode = "Phone UI" if phone else "Soft Light UI"
    st.markdown(
        f"""
<div class="app-shell-hero">
  <div class="app-kicker">Quant Control Center</div>
  <div class="app-title">M1 ADX Quant Pro</div>
  <div class="app-subtitle">Soft light premium theme applied. Trading logic, calculations, functions, connectors, and signal outputs stay unchanged.</div>
  <div class="app-pill-row">
    <span class="app-pill"><span class="app-dot{dot_class}"></span>{source}</span>
    <span class="app-pill">{symbol}</span>
    <span class="app-pill">{timeframe}</span>
    <span class="app-pill">{tab}</span>
    <span class="app-pill">{rows_badge}</span>
    <span class="app-pill">{mode}</span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )
