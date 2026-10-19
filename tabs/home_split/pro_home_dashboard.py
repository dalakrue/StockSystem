"""
Home Pro Dashboard Upgrade - additive layer.
This module keeps original Home logic intact and adds a faster, clearer
control center that uses the same shared session data as the rest of the app.
"""
from __future__ import annotations

import time
from typing import Any, Dict

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


def _safe_rerun() -> None:
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return float(default)
        if isinstance(v, str):
            v = v.strip().replace(',', '')
            if not v:
                return float(default)
        out = float(v)
        if pd.isna(out):
            return float(default)
        return out
    except Exception:
        return float(default)


def _df() -> pd.DataFrame:
    raw = st.session_state.get("last_df")
    if raw is None or not isinstance(raw, pd.DataFrame) or raw.empty:
        return pd.DataFrame()
    out = raw.copy()
    if "time" in out.columns:
        out["time"] = pd.to_datetime(out["time"], errors="coerce")
        out = out.dropna(subset=["time"]).sort_values("time")
    for c in ["open", "high", "low", "close", "volume"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out.reset_index(drop=True)


def _jump(tab: str) -> None:
    st.session_state.tab_choice = tab
    st.session_state.ui_navigation_click_ts = time.time()
    st.session_state.ui_navigation_target = f"home_pro:{tab}"
    try:
        log_event(f"Home Pro opened {tab}")
    except Exception:
        pass
    try:
        request_close_sidebar()
    except Exception:
        pass
    _safe_rerun()


def _status_badge(text: str, kind: str = "info") -> None:
    css = {
        "good": "badge-buy",
        "bad": "badge-danger",
        "warn": "badge-warning",
        "info": "badge-info",
        "wait": "badge-wait",
    }.get(kind, "badge-info")
    st.markdown(f'<span class="{css}">{text}</span>', unsafe_allow_html=True)


def _data_quality(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"kind": "bad", "quality": "NO DATA", "rows": 0, "last": "-", "msg": "Connect once from the sidebar or press Fast Refresh."}
    missing = int(df["close"].isna().sum()) if "close" in df.columns else len(df)
    duplicates = int(df["time"].duplicated().sum()) if "time" in df.columns else 0
    last = str(df["time"].iloc[-1]) if "time" in df.columns and len(df) else "-"
    source = str(st.session_state.get("source", "DISCONNECTED")).upper()
    if source == "SAFE_DEMO":
        return {"kind": "warn", "quality": "DEMO", "rows": len(df), "last": last, "msg": "SAFE_DEMO loaded. UI testing only, not live exit timing."}
    if len(df) < 100:
        return {"kind": "warn", "quality": "LOW ROWS", "rows": len(df), "last": last, "msg": "Usable for UI, but not enough candles for strong quant decision."}
    if missing > max(3, len(df) * 0.03) or duplicates > max(5, len(df) * 0.02):
        return {"kind": "warn", "quality": "CHECK", "rows": len(df), "last": last, "msg": "Missing close values or duplicate timestamps detected."}
    return {"kind": "good", "quality": "GOOD", "rows": len(df), "last": last, "msg": "Shared dataframe is ready for Home, Engine, Train Data, and Doo Prime analysis."}


def _mini_market(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty or "close" not in df.columns:
        return {"bias": "WAIT", "move_10": 0, "move_60": 0, "vol": 0, "close": 0}
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if close.empty:
        return {"bias": "WAIT", "move_10": 0, "move_60": 0, "vol": 0, "close": 0}
    last = float(close.iloc[-1])
    ret = close.pct_change().dropna()
    move_10 = ((last / float(close.iloc[-11])) - 1) * 100 if len(close) > 11 and close.iloc[-11] else 0
    move_60 = ((last / float(close.iloc[-61])) - 1) * 100 if len(close) > 61 and close.iloc[-61] else 0
    vol = float(ret.tail(120).std() * 100) if len(ret) else 0
    bias = "BUY" if move_10 > 0 and move_60 > 0 else ("SELL" if move_10 < 0 and move_60 < 0 else "WAIT")
    return {"bias": bias, "move_10": move_10, "move_60": move_60, "vol": vol, "close": last}


def _account() -> Dict[str, Any]:
    acct = st.session_state.get("account_snapshot") or {}
    if not isinstance(acct, dict) or not acct:
        return {}
    balance = _num(acct.get("balance"))
    equity = _num(acct.get("equity"), balance)
    margin = _num(acct.get("margin"))
    ml = _num(acct.get("margin_level"), equity / max(margin, 1e-9) * 100 if margin else 0)
    stop = _num(acct.get("margin_so_so"), _num(st.session_state.get("doo_stopout_level", 30), 30))
    return {
        "balance": balance,
        "equity": equity,
        "margin": margin,
        "margin_level": ml,
        "stop_gap": ml - stop if ml else 0,
        "floating": _num(acct.get("profit"), equity - balance),
        "positions": len(acct.get("positions", []) or st.session_state.get("doo_positions", []) or []),
    }


def _refresh(bars: int) -> None:
    if manual_connect is None:
        st.error("manual_connect is unavailable. Check core/data_connectors.py")
        return
    try:
        with st.spinner(f"Refreshing {bars:,} candles through the shared connector..."):
            df, ok, source, msg = manual_connect(
                mode=st.session_state.get("connector_mode", "mt5"),
                symbol=st.session_state.get("symbol", "XAUUSD"),
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
        st.error(f"Fast Refresh failed safely: {exc}")


def render_pro_home_dashboard() -> None:
    df = _df()
    quality = _data_quality(df)
    market = _mini_market(df)
    account = _account()

    st.markdown(
        f"""
        <div class="qx-home-hero">
          <h2>🏠 Home Pro Control Center</h2>
          <p>Fast launcher + shared-data health + survival snapshot. Original Home tools stay below, unchanged.</p>
          <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;">
            <span class="qx-mini-pill">Source: {st.session_state.get('source', 'DISCONNECTED')}</span>
            <span class="qx-mini-pill">Symbol: {st.session_state.get('symbol', 'XAUUSD')}</span>
            <span class="qx-mini-pill">TF: {st.session_state.get('timeframe', 'M1')}</span>
            <span class="qx-mini-pill">Rows: {quality['rows']:,}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="qx-soft-popup-note"><b>Animated glass UI active.</b><br><span>Home is optimized for faster tab switching, smaller transparent cards, and copy/export workflow.</span></div>', unsafe_allow_html=True)

    cols = st.columns(6)
    launch_tabs = [t for t in DEFAULT_TABS if t]
    for i, tab in enumerate(launch_tabs[:6]):
        with cols[i % 6]:
            active = "✅ " if st.session_state.get("tab_choice", "Home") == tab else ""
            if st.button(f"{active}{tab}", key=f"home_pro_launch_{tab}", use_container_width=True):
                _jump(tab)

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    top = st.columns(6)
    top[0].metric("Source", st.session_state.get("source", "DISCONNECTED"))
    top[1].metric("Symbol", st.session_state.get("symbol", "XAUUSD"))
    top[2].metric("TF", st.session_state.get("timeframe", "M1"))
    top[3].metric("Rows", f"{quality['rows']:,}")
    top[4].metric("Quality", quality["quality"])
    top[5].metric("Last", str(quality["last"])[-19:])
    _status_badge(quality["msg"], quality["kind"])
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        f'''
        <div class="qx-snapshot-strip">
          <div class="qx-snapshot-card"><b>Data Quality</b><span>{quality['quality']}</span></div>
          <div class="qx-snapshot-card"><b>Mini Bias</b><span>{market['bias']}</span></div>
          <div class="qx-snapshot-card"><b>Last Close</b><span>{round(market['close'], 3)}</span></div>
          <div class="qx-snapshot-card"><b>120 Vol %</b><span>{round(market['vol'], 4)}</span></div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    m = st.columns(5)
    m[0].metric("Mini Bias", market["bias"])
    m[1].metric("Last Close", round(market["close"], 3))
    m[2].metric("10 Candle %", round(market["move_10"], 4))
    m[3].metric("60 Candle %", round(market["move_60"], 4))
    m[4].metric("120 Ret Vol %", round(market["vol"], 4))

    if account:
        a = st.columns(6)
        a[0].metric("Margin Level %", round(account["margin_level"], 2))
        a[1].metric("Stop-out Gap %", round(account["stop_gap"], 2))
        a[2].metric("Equity", round(account["equity"], 2))
        a[3].metric("Margin", round(account["margin"], 2))
        a[4].metric("Floating", round(account["floating"], 2))
        a[5].metric("Positions", account["positions"])
        if account["margin_level"] and account["margin_level"] <= 80:
            st.error("Danger zone: prioritize survival room. Avoid full one-side exit unless the Doo Prime scenario table confirms enough stop-out gap.")
        elif account["margin_level"] and account["margin_level"] <= 150:
            st.warning("Tight margin: full BUY/SELL side exit needs strong trend confirmation and enough stop-out gap.")
    else:
        st.info("Account snapshot not loaded yet. Open Doo Prime > Account or press MT5 account refresh inside that section.")

    q1, q2, q3, q4 = st.columns(4)
    if q1.button("⚡ Fast Refresh 600", key="home_pro_refresh_600", use_container_width=True):
        _refresh(600); _safe_rerun()
    if q2.button("📈 Refresh chosen bars", key="home_pro_refresh_chosen", use_container_width=True):
        _refresh(int(st.session_state.get("connector_bars", 600))); _safe_rerun()
    if q3.button("🧠 Open Engine", key="home_pro_open_engine", use_container_width=True):
        _jump("Engine")
    if q4.button("🏦 Open Doo Prime", key="home_pro_open_doo", use_container_width=True):
        st.session_state.home_lazy_section = "🏦 Doo Prime"
        _safe_rerun()

    with st.expander("📋 Compact GPT copy text", expanded=False):
        copy_text = [
            "HOME_PRO_EXPORT",
            f"source={st.session_state.get('source', 'DISCONNECTED')}",
            f"symbol={st.session_state.get('symbol', 'XAUUSD')}",
            f"timeframe={st.session_state.get('timeframe', 'M1')}",
            f"rows={quality['rows']}",
            f"quality={quality['quality']}",
            f"last_candle={quality['last']}",
            f"mini_bias={market['bias']}",
            f"last_close={market['close']}",
            f"move_10_candle_pct={market['move_10']}",
            f"move_60_candle_pct={market['move_60']}",
        ]
        if account:
            copy_text += [
                f"margin_level_pct={account['margin_level']}",
                f"stopout_gap_pct={account['stop_gap']}",
                f"equity={account['equity']}",
                f"floating_pl={account['floating']}",
                f"positions={account['positions']}",
            ]
        st.text_area("Copy this into GPT", "\n".join(copy_text), height=220, key="home_pro_copy_area")

    with st.expander("🔎 Latest candle preview", expanded=False):
        if df.empty:
            st.info("No candle data loaded.")
        else:
            keep = [c for c in ["time", "open", "high", "low", "close", "volume"] if c in df.columns]
            st.dataframe(df[keep].tail(120), use_container_width=True, hide_index=True)
