"""Global UI/UX effects and relationship HUD for all tabs.

Additive layer only: it reads Streamlit session state and renders compact status,
soft popups, and relation badges. It never changes trading calculations.
"""
from __future__ import annotations

import time
from typing import Any

import streamlit as st



def render_effect_styles_once() -> None:
    if st.session_state.get("_qx_effect_css_loaded"):
        return
    st.session_state["_qx_effect_css_loaded"] = True
    st.markdown("""
<style>
.qx-live-hud{position:sticky; top:.20rem; z-index:20; display:flex; justify-content:space-between; align-items:center; gap:8px; margin:.25rem 0 .45rem 0; padding:7px 9px; border-radius:16px; background:linear-gradient(135deg, rgba(255,255,255,.58), rgba(224,242,254,.32)); border:1px solid rgba(14,165,233,.16); backdrop-filter:blur(22px) saturate(180%); box-shadow:0 8px 22px rgba(2,132,199,.06), inset 0 1px 0 rgba(255,255,255,.72); animation: qxSlideIn .22s ease both;}
.qx-hud-left,.qx-hud-right{display:flex; align-items:center; flex-wrap:wrap; gap:6px;}
.qx-live-hud span{font-size:10.5px!important; padding:3px 7px; border-radius:999px; background:rgba(255,255,255,.54); border:1px solid rgba(14,116,144,.08); color:#075985; font-weight:800;}
.qx-live-hud b{font-size:10.8px!important; color:#0f172a; font-weight:950;}
.qx-hud-dot{width:9px; height:9px; border-radius:999px; display:inline-block; padding:0!important;}
.qx-hud-dot.qx-live{background:#16a34a; box-shadow:0 0 0 6px rgba(22,163,74,.12); animation: qxPulse 1.3s infinite;}
.qx-hud-dot.qx-wait{background:#f59e0b; box-shadow:0 0 0 6px rgba(245,158,11,.12);}
.qx-smart-popup{position:fixed; top:74px; right:18px; z-index:99999; max-width:340px; display:flex; gap:10px; align-items:center; padding:10px 12px; border-radius:18px; background:linear-gradient(135deg, rgba(255,255,255,.72), rgba(224,242,254,.46)); border:1px solid rgba(14,165,233,.20); backdrop-filter:blur(24px) saturate(180%); box-shadow:0 18px 40px rgba(2,132,199,.14); animation: qxPopupIn .28s cubic-bezier(.2,.8,.2,1) both;}
.qx-smart-popup b{font-size:11px!important; color:#0f172a;}.qx-smart-popup span{font-size:10px!important; color:#075985;}
.qx-popup-pulse{width:11px; height:11px; border-radius:999px; background:#38bdf8; box-shadow:0 0 0 7px rgba(56,189,248,.16); animation: qxPulse 1.1s infinite; flex:0 0 auto;}
.qx-popup-success .qx-popup-pulse{background:#16a34a; box-shadow:0 0 0 7px rgba(22,163,74,.14);}.qx-popup-danger .qx-popup-pulse{background:#dc2626; box-shadow:0 0 0 7px rgba(220,38,38,.12);}
.qx-guard-card,.qx-relation-hub{margin:.35rem 0 .55rem 0; padding:9px 11px; border-radius:16px; background:linear-gradient(135deg, rgba(255,247,237,.76), rgba(224,242,254,.42)); border:1px solid rgba(245,158,11,.22); color:#0f172a; box-shadow:0 8px 22px rgba(2,132,199,.055); animation:glassPop .24s ease both;}
.qx-relation-hub{background:linear-gradient(135deg, rgba(240,249,255,.82), rgba(255,255,255,.54)); border-color:rgba(14,165,233,.16);}.qx-guard-card span,.qx-relation-hub span{font-size:10.4px!important; color:#075985;}
@keyframes qxPopupIn{from{opacity:0; transform:translateY(-8px) scale(.985); filter:blur(2px);}to{opacity:1; transform:translateY(0) scale(1); filter:blur(0);}}
@keyframes qxSlideIn{from{opacity:0; transform:translateY(-5px);}to{opacity:1; transform:translateY(0);}}
@keyframes qxPulse{0%,100%{transform:scale(1); opacity:1;}50%{transform:scale(.78); opacity:.66;}}
@media(max-width:430px){.qx-live-hud{position:relative; top:auto; align-items:flex-start; flex-direction:column; padding:7px; border-radius:14px;}.qx-live-hud span{font-size:9.5px!important; padding:2px 5px;}.qx-smart-popup{left:10px; right:10px; top:58px; max-width:none;}}
</style>
""", unsafe_allow_html=True)


def _rows(obj: Any) -> int:
    try:
        return int(len(obj)) if obj is not None else 0
    except Exception:
        return 0


def _age_text(ts: Any) -> str:
    try:
        ts = float(ts or 0)
        if ts <= 0:
            return "not refreshed"
        age = max(0, time.time() - ts)
        if age < 60:
            return f"{int(age)}s"
        if age < 3600:
            return f"{int(age // 60)}m"
        return f"{age / 3600:.1f}h"
    except Exception:
        return "unknown"


def queue_ui_popup(title: str, body: str = "", kind: str = "info") -> None:
    q = st.session_state.setdefault("ui_popup_queue", [])
    q.insert(0, {"title": str(title), "body": str(body), "kind": str(kind), "ts": time.time()})
    del q[4:]


def render_global_effects(tab_name: str) -> None:
    source = st.session_state.get("source", "DISCONNECTED")
    symbol = st.session_state.get("symbol", "XAUUSD")
    tf = st.session_state.get("timeframe", "M1")
    df = st.session_state.get("last_df")
    rows = _rows(df)
    connected = bool(st.session_state.get("connected", False)) and rows > 0
    status_cls = "qx-live" if connected else "qx-wait"
    status = "SHARED DATA READY" if connected else "WAITING FOR CONNECTOR"
    age = _age_text(st.session_state.get("last_fetch", 0))
    density = "Phone" if bool(st.session_state.get("phone_mode", False)) else "Laptop"
    epoch = int(st.session_state.get("shared_connection_epoch", 0) or 0)
    st.markdown(
        f'''
        <div class="qx-live-hud">
          <div class="qx-hud-left">
            <span class="qx-hud-dot {status_cls}"></span>
            <b>{tab_name}</b>
            <span>{symbol}</span><span>{tf}</span><span>{source}</span>
          </div>
          <div class="qx-hud-right">
            <span>{status}</span><span>{rows:,} rows</span><span>age {age}</span><span>data v{epoch}</span><span>{density}</span>
          </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def render_popup_queue() -> None:
    q = st.session_state.get("ui_popup_queue", [])
    if not q:
        return
    item = q[0]
    if time.time() - float(item.get("ts", 0) or 0) > 3.5:
        try:
            st.session_state["ui_popup_queue"] = q[1:]
        except Exception:
            pass
        return
    kind = str(item.get("kind", "info"))
    st.markdown(
        f'''
        <div class="qx-smart-popup qx-popup-{kind}">
          <div class="qx-popup-pulse"></div>
          <div><b>{item.get('title','Update')}</b><br><span>{item.get('body','')}</span></div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def render_connection_guard(tab_name: str) -> None:
    df = st.session_state.get("last_df")
    rows = _rows(df)
    connected = bool(st.session_state.get("connected", False)) and rows > 0
    if connected or tab_name in {"Home", "Profile"}:
        return
    st.markdown(
        '''
        <div class="qx-guard-card">
          <b>Shared connector guard</b><br>
          <span>No real shared dataframe is loaded yet. Use the sidebar connector once; Engine, Train Data, Pre Original and Database will reuse the same data.</span>
        </div>
        ''',
        unsafe_allow_html=True,
    )
