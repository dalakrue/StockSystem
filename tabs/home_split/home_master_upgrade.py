"""
2026-06-01 Home Master Upgrade
Additive Home-tab layer for faster launch, clearer shared-state health,
smarter copy text, and all-tab relationship visibility.

Design rule: do not remove original Home code. This module reads/writes the
same st.session_state keys already used by sidebar, Engine, Train Data,
Pre Original, Profile, and Doo Prime sections.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd
import streamlit as st

try:
    from core.common import DEFAULT_TABS, log_event
except Exception:
    DEFAULT_TABS = ["Home", "Engine", "Train Data", "Pre Original", "Database", "Profile"]
    def log_event(*args, **kwargs):
        return None

try:
    from core.styles import request_close_sidebar
except Exception:
    def request_close_sidebar(*args, **kwargs):
        return None

try:
    from core.data_connectors import manual_connect
except Exception:
    manual_connect = None

try:
    from core.database import append_csv
except Exception:
    append_csv = None


def _safe_rerun() -> None:
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def _safe_num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return float(default)
        if isinstance(v, str):
            v = v.strip().replace(",", "")
            if not v:
                return float(default)
        out = float(v)
        if pd.isna(out):
            return float(default)
        return out
    except Exception:
        return float(default)


def _clean_symbol(symbol: Any) -> str:
    return str(symbol or "XAUUSD").strip().upper().replace("/", "").replace(" ", "")


def _safe_df(raw: Any) -> pd.DataFrame:
    if raw is None or not isinstance(raw, pd.DataFrame) or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        df = df.dropna(subset=["time"]).sort_values("time")
    for c in ["open", "high", "low", "close", "volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.drop_duplicates(subset=["time"] if "time" in df.columns else None).reset_index(drop=True)


def _open_tab(tab: str) -> None:
    st.session_state.tab_choice = tab
    st.session_state.ui_navigation_click_ts = time.time()
    st.session_state.ui_navigation_target = f"home_master:{tab}"
    try:
        log_event(f"Home Master opened {tab}")
    except Exception:
        pass
    try:
        request_close_sidebar()
    except Exception:
        pass
    _safe_rerun()


def _connection_health(df: pd.DataFrame) -> Dict[str, Any]:
    source = str(st.session_state.get("source", "DISCONNECTED") or "DISCONNECTED").upper()
    if df.empty:
        return {"status": "NO DATA", "score": 0, "kind": "danger", "message": "No shared dataframe. Connect MT5 / Doo Bridge / TwelveData once from the sidebar."}

    score = 100
    notes: List[str] = []
    if source in ["SAFE_DEMO", "DEMO"]:
        score -= 45
        notes.append("SAFE_DEMO source")
    if len(df) < 120:
        score -= 30
        notes.append("low candle count")
    if "close" not in df.columns or df["close"].isna().sum() > max(3, len(df) * 0.03):
        score -= 25
        notes.append("close column has missing values")
    if "time" in df.columns and df["time"].duplicated().sum() > max(3, len(df) * 0.02):
        score -= 15
        notes.append("duplicate timestamps")
    if source.endswith("FAILED") or "FAILED" in source:
        score -= 35
        notes.append("last connector failed")

    score = max(0, min(100, int(score)))
    if score >= 80:
        status, kind = "GOOD", "good"
    elif score >= 50:
        status, kind = "CHECK", "warning"
    else:
        status, kind = "DANGER", "danger"
    msg = "; ".join(notes) if notes else "Shared dataframe is ready for Home, Engine, Train Data, and Doo Prime analysis."
    return {"status": status, "score": score, "kind": kind, "message": msg}


def _market_summary(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty or "close" not in df.columns:
        return {"bias": "WAIT", "close": 0.0, "m10": 0.0, "m60": 0.0, "vol120": 0.0, "range120": 0.0}
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if close.empty:
        return {"bias": "WAIT", "close": 0.0, "m10": 0.0, "m60": 0.0, "vol120": 0.0, "range120": 0.0}
    last = float(close.iloc[-1])
    m10 = ((last / float(close.iloc[-11])) - 1.0) * 100.0 if len(close) > 11 and close.iloc[-11] else 0.0
    m60 = ((last / float(close.iloc[-61])) - 1.0) * 100.0 if len(close) > 61 and close.iloc[-61] else 0.0
    ret = close.pct_change().dropna()
    vol120 = float(ret.tail(120).std() * 100.0) if not ret.empty else 0.0
    hi = pd.to_numeric(df.get("high", close), errors="coerce").tail(120).max()
    lo = pd.to_numeric(df.get("low", close), errors="coerce").tail(120).min()
    range120 = ((float(hi) / float(lo)) - 1.0) * 100.0 if lo and pd.notna(hi) and pd.notna(lo) else 0.0
    if m10 > 0 and m60 > 0:
        bias = "BUY"
    elif m10 < 0 and m60 < 0:
        bias = "SELL"
    else:
        bias = "WAIT"
    return {"bias": bias, "close": last, "m10": m10, "m60": m60, "vol120": vol120, "range120": range120}


def _account_summary() -> Dict[str, Any]:
    acct = st.session_state.get("account_snapshot") or {}
    if not isinstance(acct, dict) or not acct:
        return {}
    balance = _safe_num(acct.get("balance"))
    equity = _safe_num(acct.get("equity"), balance)
    margin = _safe_num(acct.get("margin"))
    margin_level = _safe_num(acct.get("margin_level"), equity / max(margin, 1e-9) * 100 if margin else 0)
    stopout = _safe_num(acct.get("margin_so_so"), _safe_num(st.session_state.get("doo_stopout_level", 30), 30))
    positions = acct.get("positions", []) or st.session_state.get("doo_positions", []) or []
    return {
        "balance": balance,
        "equity": equity,
        "margin": margin,
        "margin_level": margin_level,
        "stopout_gap": margin_level - stopout if margin_level else 0.0,
        "floating": _safe_num(acct.get("profit"), equity - balance),
        "positions": len(positions),
        "stopout": stopout,
    }


def _status_chip(text: str, kind: str = "info") -> None:
    cls = {
        "good": "badge-buy",
        "danger": "badge-danger",
        "warning": "badge-warning",
        "info": "badge-info",
        "wait": "badge-wait",
    }.get(kind, "badge-info")
    st.markdown(f'<span class="{cls}">{text}</span>', unsafe_allow_html=True)


def _refresh_shared_data(bars: int) -> None:
    if manual_connect is None:
        st.error("manual_connect is unavailable. Check core/data_connectors.py.")
        return
    symbol = _clean_symbol(st.session_state.get("symbol", "XAUUSD"))
    st.session_state.symbol = symbol
    try:
        with st.spinner(f"Refreshing {symbol} {st.session_state.get('timeframe', 'M1')} with {int(bars):,} candles..."):
            df, ok, source, msg = manual_connect(
                mode=st.session_state.get("connector_mode", "mt5"),
                symbol=symbol,
                api_key=st.session_state.get("twelve_api_key", ""),
                bars=int(bars),
                timeframe=st.session_state.get("timeframe", "M1"),
                bridge_url=st.session_state.get("doo_bridge_url", ""),
                bridge_token=st.session_state.get("doo_bridge_token", ""),
                allow_demo=bool(st.session_state.get("allow_safe_demo", False)),
            )
        if ok:
            st.success(f"{source}: {len(df):,} rows loaded. {msg}")
        else:
            st.error(str(msg))
    except Exception as exc:
        st.error(f"Shared refresh failed safely: {exc}")


def _save_home_snapshot(payload: Dict[str, Any]) -> None:
    if append_csv is None:
        return
    try:
        append_csv("home_snapshots", payload)
    except Exception:
        pass


def _copy_payload(df: pd.DataFrame, health: Dict[str, Any], market: Dict[str, Any], account: Dict[str, Any]) -> str:
    last_time = "-"
    if not df.empty and "time" in df.columns:
        last_time = str(df["time"].iloc[-1])
    rows = [
        "HOME_MASTER_EXPORT=1",
        f"created_at={pd.Timestamp.now()}",
        f"source={st.session_state.get('source', 'DISCONNECTED')}",
        f"symbol={st.session_state.get('symbol', 'XAUUSD')}",
        f"timeframe={st.session_state.get('timeframe', 'M1')}",
        f"rows={len(df)}",
        f"last_candle={last_time}",
        f"data_quality={health.get('status')} score={health.get('score')}/100 note={health.get('message')}",
        f"mini_bias={market.get('bias')}",
        f"last_close={market.get('close')}",
        f"move_10_candle_pct={round(_safe_num(market.get('m10')), 5)}",
        f"move_60_candle_pct={round(_safe_num(market.get('m60')), 5)}",
        f"vol_120_return_pct={round(_safe_num(market.get('vol120')), 5)}",
        f"range_120_pct={round(_safe_num(market.get('range120')), 5)}",
    ]
    if account:
        rows.extend([
            f"margin_level_pct={round(account.get('margin_level', 0), 4)}",
            f"stopout_level_pct={round(account.get('stopout', 30), 4)}",
            f"stopout_gap_pct={round(account.get('stopout_gap', 0), 4)}",
            f"equity={round(account.get('equity', 0), 4)}",
            f"margin={round(account.get('margin', 0), 4)}",
            f"floating_pl={round(account.get('floating', 0), 4)}",
            f"positions={account.get('positions', 0)}",
        ])
    rows.append("instruction=Analyze survival first; do not assume full one-side exit is safe without account scenario confirmation.")
    return "\n".join(rows)




def _copy_button_component(text: str, key_suffix: str = "master") -> None:
    """Small mobile-friendly copy button with hidden payload."""
    try:
        import json
        import streamlit.components.v1 as components
        payload = json.dumps(str(text), ensure_ascii=False)
        components.html(
            f"""
            <div style="padding:8px;border-radius:16px;background:rgba(245,252,255,.72);border:1px solid rgba(80,170,220,.30);font-family:Arial,sans-serif;">
              <button id="copyBtn_{key_suffix}" style="width:100%;min-height:44px;border-radius:999px;border:1px solid rgba(76,180,230,.45);background:rgba(232,247,255,.96);font-weight:800;cursor:pointer;">📋 Copy All Home Data</button>
              <div id="copyStatus_{key_suffix}" style="text-align:center;font-size:12px;font-weight:700;color:#075985;margin-top:6px;">No text box. Tap once to copy.</div>
              <textarea id="copyText_{key_suffix}" style="position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;opacity:0;"></textarea>
            </div>
            <script>
              const payload_{key_suffix} = {payload};
              const b_{key_suffix} = document.getElementById('copyBtn_{key_suffix}');
              const t_{key_suffix} = document.getElementById('copyText_{key_suffix}');
              const s_{key_suffix} = document.getElementById('copyStatus_{key_suffix}');
              t_{key_suffix}.value = payload_{key_suffix};
              async function doCopy_{key_suffix}() {{
                try {{
                  if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(payload_{key_suffix});
                  else {{ t_{key_suffix}.style.left='0'; t_{key_suffix}.style.top='0'; t_{key_suffix}.focus(); t_{key_suffix}.select(); document.execCommand('copy'); t_{key_suffix}.style.left='-9999px'; }}
                  b_{key_suffix}.innerText='✅ Copied All Data'; s_{key_suffix}.innerText='Paste into GPT now.';
                }} catch(e) {{
                  t_{key_suffix}.style.position='static'; t_{key_suffix}.style.width='100%'; t_{key_suffix}.style.height='120px'; t_{key_suffix}.style.opacity='1';
                  t_{key_suffix}.focus(); t_{key_suffix}.select(); s_{key_suffix}.innerText='Phone blocked auto-copy. Select all text below and copy.';
                }}
              }}
              b_{key_suffix}.addEventListener('click', doCopy_{key_suffix});
              b_{key_suffix}.addEventListener('touchend', function(e){{e.preventDefault(); doCopy_{key_suffix}();}}, {{passive:false}});
            </script>
            """,
            height=76,
        )
    except Exception:
        st.text_area("Fallback copy box", value=str(text), height=160, key=f"home_master_copy_fallback_{key_suffix}")

def _relationship_rows() -> List[Dict[str, str]]:
    return [
        {"Area": "Sidebar connector", "Reads/Writes": "symbol, timeframe, connector_mode, last_df, source", "Impact": "One shared data source for every tab"},
        {"Area": "Home", "Reads/Writes": "last_df, account_snapshot, doo_positions, home_snapshots", "Impact": "Fast command center and GPT copy export"},
        {"Area": "Engine", "Reads/Writes": "last_df, quant/model outputs", "Impact": "Main ADX/DI and math/ML decision layer"},
        {"Area": "Train Data", "Reads/Writes": "last_df + database training cache", "Impact": "Improves saved learning data over time"},
        {"Area": "Doo Prime", "Reads/Writes": "account_snapshot, doo_positions, last_df", "Impact": "Margin, positions, exit/survival analysis"},
        {"Area": "Pre Original", "Reads/Writes": "manual emergency inputs", "Impact": "API-free backup checks"},
        {"Area": "Profile", "Reads/Writes": "profile/session settings", "Impact": "Trader configuration"},
    ]


def render_home_master_upgrade() -> None:
    df = _safe_df(st.session_state.get("last_df"))
    health = _connection_health(df)
    market = _market_summary(df)
    account = _account_summary()

    st.markdown("## 🏠 Home Master Command Center")
    st.caption("Fast Home upgrade: tab launcher, shared data health, survival snapshot, and compact GPT export. Original Home remains below.")

    tabs = [t for t in DEFAULT_TABS if t]
    if tabs:
        cols = st.columns(min(5, len(tabs)))
        icons = {"Home": "🏠", "Engine": "⚡", "Train Data": "🧠", "Pre Original": "🧾", "Profile": "👤", "Database": "🗄️"}
        for i, tab in enumerate(tabs):
            with cols[i % len(cols)]:
                active = "✅ " if tab == st.session_state.get("tab_choice", "Home") else ""
                if st.button(f"{active}{icons.get(tab, '➡️')} {tab}", key=f"home_master_open_{tab}", use_container_width=True):
                    _open_tab(tab)

    with st.container():
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Source", st.session_state.get("source", "DISCONNECTED"))
        c2.metric("Symbol", st.session_state.get("symbol", "XAUUSD"))
        c3.metric("TF", st.session_state.get("timeframe", "M1"))
        c4.metric("Rows", f"{len(df):,}")
        c5.metric("Quality", health.get("status", "UNKNOWN"))
        c6.metric("Score", f"{health.get('score', 0)}/100")
        _status_chip(health.get("message", ""), health.get("kind", "info"))
        st.markdown('</div>', unsafe_allow_html=True)

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Mini Bias", market.get("bias", "WAIT"))
    m2.metric("Last Close", round(_safe_num(market.get("close")), 3))
    m3.metric("10 Candle %", round(_safe_num(market.get("m10")), 4))
    m4.metric("60 Candle %", round(_safe_num(market.get("m60")), 4))
    m5.metric("120 Vol %", round(_safe_num(market.get("vol120")), 4))
    m6.metric("120 Range %", round(_safe_num(market.get("range120")), 4))

    if account:
        a1, a2, a3, a4, a5, a6 = st.columns(6)
        a1.metric("Margin Level %", round(account.get("margin_level", 0), 2))
        a2.metric("Stop-out Gap %", round(account.get("stopout_gap", 0), 2))
        a3.metric("Equity", round(account.get("equity", 0), 2))
        a4.metric("Margin", round(account.get("margin", 0), 2))
        a5.metric("Floating", round(account.get("floating", 0), 2))
        a6.metric("Positions", account.get("positions", 0))
        if account.get("margin_level", 0) and account.get("margin_level", 0) <= 80:
            st.error("Danger: margin level is near stop-out zone. Prefer survival/paired reduction logic before any full one-side exit.")
        elif account.get("margin_level", 0) and account.get("margin_level", 0) <= 150:
            st.warning("Tight margin: full-side exit needs strong directional evidence and enough stop-out gap.")
    else:
        st.info("No account snapshot loaded yet. Use sidebar MT5/Doo Bridge connection or Home/Doo Prime account refresh.")

    q1, q2, q3, q4 = st.columns(4)
    if q1.button("⚡ Refresh 600", key="home_master_refresh_600", use_container_width=True):
        _refresh_shared_data(600)
        _safe_rerun()
    if q2.button("📈 Refresh chosen bars", key="home_master_refresh_chosen", use_container_width=True):
        _refresh_shared_data(int(st.session_state.get("connector_bars", 600) or 600))
        _safe_rerun()
    if q3.button("🏦 Open Doo Prime", key="home_master_open_doo", use_container_width=True):
        st.session_state.home_lazy_section = "🏦 Doo Prime"
        _safe_rerun()
    if q4.button("⚡ Open Doo Analysis", key="home_master_open_doo_deep", use_container_width=True):
        st.session_state.home_lazy_section = "⚡ Doo Prime Analysis"
        _safe_rerun()

    with st.expander("📋 Copy All Home Data", expanded=False):
        text = _copy_payload(df, health, market, account)
        st.caption("Simple copy button. The long export text stays hidden and works better on phone.")
        _copy_button_component(text, key_suffix="master")
        if st.button("💾 Save Home snapshot", key="home_master_save_snapshot", use_container_width=True):
            payload = {
                "time": pd.Timestamp.now(),
                "source": st.session_state.get("source", "DISCONNECTED"),
                "symbol": st.session_state.get("symbol", "XAUUSD"),
                "timeframe": st.session_state.get("timeframe", "M1"),
                "rows": len(df),
                "quality": health.get("status"),
                "quality_score": health.get("score"),
                "mini_bias": market.get("bias"),
                "last_close": market.get("close"),
                "margin_level": account.get("margin_level") if account else None,
                "stopout_gap": account.get("stopout_gap") if account else None,
            }
            _save_home_snapshot(payload)
            st.success("Home snapshot saved safely if database writer is available.")

    with st.expander("🧩 All-tab relationship map", expanded=False):
        st.dataframe(pd.DataFrame(_relationship_rows()), use_container_width=True, hide_index=True)
        st.caption("This map helps verify that every tab reads the same shared session pipeline instead of creating conflicting duplicate connectors.")

    with st.expander("🔎 Latest candle preview", expanded=False):
        if df.empty:
            st.caption("No candles loaded.")
        else:
            keep = [c for c in ["time", "open", "high", "low", "close", "volume"] if c in df.columns]
            st.dataframe(df[keep].tail(100), use_container_width=True, hide_index=True)
