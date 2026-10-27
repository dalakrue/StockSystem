"""
2026-06-01 Home Full Upgrade
Non-destructive Home enhancement layer.
- Does not remove original Home / Doo Prime / Engine code.
- Uses shared st.session_state data so every tab keeps one data pipeline.
- Keeps heavy analysis lazy; no 60k-candle work unless the user opens it.
"""
from __future__ import annotations

import importlib
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
    from core.data_connectors import manual_connect
except Exception:
    manual_connect = None

try:
    from core.styles import request_close_sidebar
except Exception:
    def request_close_sidebar(*args, **kwargs):
        return None


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


def _safe_df(df: Any) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "time" in out.columns:
        out["time"] = pd.to_datetime(out["time"], errors="coerce")
        out = out.dropna(subset=["time"]).sort_values("time")
    for c in ["open", "high", "low", "close", "volume"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out.reset_index(drop=True)


def _impl(name: str, fallback=None):
    try:
        mod = importlib.import_module("tabs.home_split.implementation")
        return getattr(mod, name, fallback)
    except Exception:
        return fallback


def _safe_rerun() -> None:
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def _open_main_tab(tab: str) -> None:
    st.session_state.tab_choice = tab
    st.session_state.ui_navigation_click_ts = time.time()
    st.session_state.ui_navigation_target = f"home_full_upgrade:{tab}"
    try:
        log_event(f"Home full launcher opened: {tab}")
    except Exception:
        pass
    try:
        request_close_sidebar()
    except Exception:
        pass
    _safe_rerun()


def _read_account() -> None:
    fn = _impl("_safe_mt5_account_info")
    if callable(fn):
        info, ok, msg = fn()
        if isinstance(info, dict):
            st.session_state.account_snapshot = info
            st.session_state.doo_positions = info.get("positions", []) or []
        if ok:
            st.success(msg)
        else:
            st.warning(msg)
    else:
        st.warning("Account reader is not available from the original Home implementation.")


def _fast_refresh(bars: int = 600) -> None:
    if manual_connect is None:
        st.error("manual_connect is unavailable. Check core/data_connectors.py.")
        return
    try:
        with st.spinner(f"Loading {bars:,} candles from the shared connector..."):
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
        if ok and str(source).upper() == "SAFE_DEMO":
            st.warning(f"SAFE_DEMO loaded: {len(df):,} rows. Use only for UI testing, not real exit decisions.")
        elif ok:
            st.success(f"{source}: {len(df):,} rows loaded. {msg}")
        else:
            st.error(str(msg))
    except Exception as exc:
        st.error(f"Fast refresh failed safely: {exc}")


def _data_health(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"status": "NO DATA", "rows": 0, "last_time": "-", "message": "Connect MT5 / Doo Bridge / TwelveData from the sidebar or use Fast Refresh."}
    missing_close = int(df["close"].isna().sum()) if "close" in df.columns else len(df)
    duplicates = int(df["time"].duplicated().sum()) if "time" in df.columns else 0
    last_time = str(df["time"].iloc[-1]) if "time" in df.columns and len(df) else "-"
    source = str(st.session_state.get("source", "DISCONNECTED")).upper()
    if "SAFE_DEMO" in source:
        return {"status": "DEMO", "rows": len(df), "last_time": last_time, "message": "SAFE_DEMO source. Do not use for live exit timing."}
    if len(df) < 50 or missing_close > len(df) * 0.05:
        return {"status": "BAD", "rows": len(df), "last_time": last_time, "message": "Too few candles or too many missing close values."}
    if duplicates > max(5, len(df) * 0.02):
        return {"status": "CHECK", "rows": len(df), "last_time": last_time, "message": "Duplicate candle timestamps detected. Refresh before relying on signals."}
    return {"status": "GOOD", "rows": len(df), "last_time": last_time, "message": "Shared market dataframe is usable by Home, Engine, Train Data, and Doo Prime analysis."}


def _market_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {}
    out: Dict[str, Any] = {}
    try:
        qfn = _impl("_safe_quant_stack")
        if callable(qfn):
            out["quant"] = qfn(df) or {}
    except Exception as exc:
        out["quant"] = {"error": str(exc)}
    try:
        mfn = _impl("_calc_market_analytics")
        if callable(mfn):
            market, _frame = mfn(df)
            out["market"] = market or {}
    except Exception as exc:
        out["market"] = {"error": str(exc)}
    return out


def _account_metrics(account: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(account, dict) or not account:
        return {}
    balance = _safe_num(account.get("balance"))
    equity = _safe_num(account.get("equity"), balance)
    margin = _safe_num(account.get("margin"))
    ml = _safe_num(account.get("margin_level"), equity / max(margin, 1e-9) * 100.0 if margin else 0)
    stopout = _safe_num(account.get("margin_so_so"), _safe_num(st.session_state.get("doo_stopout_level", 30), 30))
    return {
        "balance": balance,
        "equity": equity,
        "margin": margin,
        "margin_level": ml,
        "stopout_gap": ml - stopout if ml else 0,
        "floating": _safe_num(account.get("profit"), equity - balance),
        "positions": len(account.get("positions", []) or st.session_state.get("doo_positions", []) or []),
    }


def render_home_full_upgrade() -> None:
    st.markdown("## 🚀 Full Home Control Center")
    st.caption("One-screen launcher + shared-data health. This is additive and keeps the original code intact.")

    # Direct tab launchers are visible, not hidden in an expander.
    tabs = [t for t in DEFAULT_TABS if t]
    cols = st.columns(min(5, max(1, len(tabs))))
    icons = {"Home": "🏠", "Engine": "⚡", "Train Data": "🧠", "Pre Original": "🧾", "Database": "🗄️", "Profile": "👤"}
    for i, tab in enumerate(tabs):
        with cols[i % len(cols)]:
            active = tab == st.session_state.get("tab_choice", "Home")
            label = ("✅ " if active else "") + icons.get(tab, "➡️") + " " + tab
            if st.button(label, use_container_width=True, key=f"home_full_open_{tab}"):
                _open_main_tab(tab)

    df = _safe_df(st.session_state.get("last_df"))
    account = st.session_state.get("account_snapshot", {}) or {}
    health = _data_health(df)
    mm = _market_metrics(df)
    q = mm.get("quant", {}) if isinstance(mm.get("quant", {}), dict) else {}
    market = mm.get("market", {}) if isinstance(mm.get("market", {}), dict) else {}
    am = _account_metrics(account)

    quick = st.columns(4)
    with quick[0]:
        if st.button("⚡ Refresh 600", use_container_width=True, key="home_full_refresh_600"):
            _fast_refresh(600)
            _safe_rerun()
    with quick[1]:
        if st.button("📊 Refresh chosen bars", use_container_width=True, key="home_full_refresh_chosen"):
            _fast_refresh(int(st.session_state.get("connector_bars", 600)))
            _safe_rerun()
    with quick[2]:
        if st.button("🏦 Read account", use_container_width=True, key="home_full_read_account"):
            _read_account()
            _safe_rerun()
    with quick[3]:
        if st.button("🧹 Clear UI cache", use_container_width=True, key="home_full_clear_ui_cache"):
            for k in ["home_copy_export_text", "doo_deep_results", "deferred_auto_refresh_reason"]:
                st.session_state.pop(k, None)
            st.success("Cleared Home copy/deep UI cache. Market data is preserved.")

    st.markdown("### ✅ Shared System Status")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Source", st.session_state.get("source", "DISCONNECTED"))
    c2.metric("Symbol", st.session_state.get("symbol", "XAUUSD"))
    c3.metric("TF", st.session_state.get("timeframe", "M1"))
    c4.metric("Rows", f"{health.get('rows', 0):,}")
    c5.metric("Quality", health.get("status", "UNKNOWN"))
    c6.metric("Last Candle", str(health.get("last_time", "-"))[-19:])
    st.caption(health.get("message", ""))

    st.markdown("### 🧠 Fast Decision Metrics")
    d1, d2, d3, d4, d5, d6 = st.columns(6)
    d1.metric("12H Bias", q.get("bias", "WAIT"))
    d2.metric("Safety %", round(_safe_num(q.get("safe_pct")), 1))
    d3.metric("Regime", market.get("regime", "NO DATA"))
    d4.metric("Direction", market.get("trend_direction", "UNKNOWN"))
    d5.metric("DVE %", round(_safe_num(market.get("directional_efficiency")), 2))
    d6.metric("Trust %", round(_safe_num(market.get("trust")), 1))

    if am:
        st.markdown("### 🏦 Doo Prime Survival Snapshot")
        a1, a2, a3, a4, a5, a6 = st.columns(6)
        a1.metric("Margin Level %", round(am.get("margin_level", 0), 2))
        a2.metric("Stop-out Gap %", round(am.get("stopout_gap", 0), 2))
        a3.metric("Equity", round(am.get("equity", 0), 2))
        a4.metric("Margin", round(am.get("margin", 0), 2))
        a5.metric("Floating P/L", round(am.get("floating", 0), 2))
        a6.metric("Positions", am.get("positions", 0))
        if am.get("margin_level", 0) and am.get("margin_level", 0) <= 80:
            st.error("Margin level is dangerous. Prioritize paired reduction/survival room over one-side full exit unless your scenario table confirms safety.")
        elif am.get("margin_level", 0) and am.get("margin_level", 0) <= 150:
            st.warning("Margin level is tight. Full BUY/SELL side exit needs strong trend confirmation and enough stop-out room.")
    else:
        st.info("Account snapshot not loaded. Click Read account to show margin-level, stop-out gap, and open-position count.")

    with st.expander("🔎 Open compact candle preview", expanded=False):
        if df.empty:
            st.info("No dataframe loaded yet.")
        else:
            keep = [c for c in ["time", "open", "high", "low", "close", "volume"] if c in df.columns]
            st.dataframe(df[keep].tail(80), use_container_width=True, hide_index=True)

    with st.expander("🧩 Open all-tab relationship map", expanded=False):
        relation = pd.DataFrame([
            {"Tab": "Home", "Uses": "shared last_df + account_snapshot", "Purpose": "launcher, risk, quick decision screen"},
            {"Tab": "Engine", "Uses": "shared last_df", "Purpose": "ADX/DI/quant signal analysis"},
            {"Tab": "Train Data", "Uses": "shared last_df + saved database", "Purpose": "training cache and learning over time"},
            {"Tab": "Pre Original", "Uses": "manual/API-free emergency tools", "Purpose": "pre-trade and survivability checks"},
            {"Tab": "Profile", "Uses": "profile/session settings", "Purpose": "trader setup and preferences"},
            {"Tab": "Doo Prime Analysis", "Uses": "shared last_df or manual deep fetch", "Purpose": "M1/H1 600 and 60k analytics"},
        ])
        st.dataframe(relation, use_container_width=True, hide_index=True)
