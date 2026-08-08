import pandas as pd
import numpy as np
import streamlit as st

from .connectors import safe_connect
from .shared_state import sync_backtest_keys_from_last_df, shared_data_status

try:
    from .pro_engine_upgrade import render_engine_pro_panel
except Exception:
    render_engine_pro_panel = None

try:
    from .original_engine_inner import _safe_add_indicators, _safe_quant_stack
except Exception:
    _safe_add_indicators = None
    _safe_quant_stack = None


try:
    from core.ui_helpers import choice_buttons
except Exception:
    choice_buttons = None


def _show_shared_market_status():
    df = st.session_state.get("last_df")
    if isinstance(df, pd.DataFrame) and not df.empty:
        cols = st.columns(5)
        cols[0].metric("Shared Data", "ACTIVE")
        cols[1].metric("Rows", f"{len(df):,}")
        cols[2].metric("Source", st.session_state.get("source", "UNKNOWN"))
        cols[3].metric("Symbol", st.session_state.get("symbol", "XAUUSD"))
        cols[4].metric("TF", st.session_state.get("timeframe", "M1"))
        st.success("Twelve/MT5 data is available globally. All Engine inner tabs are reading the same st.session_state['last_df'].")
    else:
        st.warning("No shared market data yet. Connect Twelve/MT5 from the sidebar, then press Refresh if needed.")


def _safe_rerun():
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def _top_shared_connector():
    df = st.session_state.get("last_df")
    rows = len(df) if isinstance(df, pd.DataFrame) else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Symbol", st.session_state.get("symbol", "XAUUSD"))
    c2.metric("Timeframe", st.session_state.get("timeframe", "M1"))
    c3.metric("Shared Rows", f"{rows:,}")
    c4.metric("Current Source", st.session_state.get("source", "DISCONNECTED"))

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Use sidebar connection in Engine", use_container_width=True, key="engine_sync_sidebar_df"):
            sync_backtest_keys_from_last_df()
            st.success("Shared data synced into Engine / Prelive / Backtest.")
            _safe_rerun()
    with b2:
        if st.button("Clear Shared Data", use_container_width=True, key="combined_clear_shared"):
            for k in [
                "last_df", "connected", "source", "engine_shared_rows",
                "combined_original_backtest_raw_df",
                "combined_original_backtest_source",
                "combined_original_backtest_symbol",
                "combined_original_backtest_last_load",
            ]:
                st.session_state.pop(k, None)
            st.session_state.connected = False
            st.session_state.source = "DISCONNECTED"
            st.success("Shared data cleared.")
            _safe_rerun()

    ok, rows = shared_data_status()
    if ok:
        sync_backtest_keys_from_last_df()
        st.success(f"Shared data active: {rows:,} rows. Engine / Prelive / Backtest use the same loaded data.")
    else:
        st.info("No shared data yet. Use the global sidebar connector first.")

def _call_original_show(module_name):
    try:
        if module_name == "engine":
            from . import original_engine_inner as mod
        elif module_name == "prelive":
            from . import original_prelive_inner as mod
        else:
            from . import original_backtest_inner as mod

        if hasattr(mod, "show"):
            mod.show()
        else:
            st.error(f"{module_name} module has no show() function.")

    except Exception as exc:
        st.error(f"{module_name} inner tab crashed safely: {exc}")
        with st.expander("Debug error"):
            st.exception(exc)




# ==========================================================
# 2026-06-01 NON-DESTRUCTIVE ENGINE FULL UPGRADE LAYER
# ==========================================================

def _engine_df():
    df = st.session_state.get("last_df")
    if isinstance(df, pd.DataFrame) and not df.empty:
        try:
            return df.copy()
        except Exception:
            return df
    return pd.DataFrame()


def _engine_numeric(v, default=0.0):
    try:
        if v is None:
            return float(default)
        out = float(v)
        if not np.isfinite(out):
            return float(default)
        return out
    except Exception:
        return float(default)


def _basic_engine_indicators(df):
    """Small internal fallback so Engine summary never blanks if original indicator stack is unavailable."""
    try:
        work = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
        if work.empty:
            return pd.DataFrame()
        rename = {}
        for c in work.columns:
            lc = str(c).lower().strip()
            if lc in ["datetime", "date", "timestamp"]:
                rename[c] = "time"
            elif lc in ["o", "open"]:
                rename[c] = "open"
            elif lc in ["h", "high"]:
                rename[c] = "high"
            elif lc in ["l", "low"]:
                rename[c] = "low"
            elif lc in ["c", "close", "price"]:
                rename[c] = "close"
        work = work.rename(columns=rename)
        if "time" not in work.columns:
            work["time"] = pd.date_range(end=pd.Timestamp.now(), periods=len(work), freq="min")
        work["time"] = pd.to_datetime(work["time"], errors="coerce")
        if "close" not in work.columns:
            return pd.DataFrame()
        work["close"] = pd.to_numeric(work["close"], errors="coerce").ffill()
        if "open" not in work.columns:
            work["open"] = work["close"].shift(1).fillna(work["close"])
        if "high" not in work.columns:
            work["high"] = work[["open", "close"]].max(axis=1)
        if "low" not in work.columns:
            work["low"] = work[["open", "close"]].min(axis=1)
        for c in ["open", "high", "low", "close"]:
            work[c] = pd.to_numeric(work[c], errors="coerce").ffill()
        work = work.dropna(subset=["time", "open", "high", "low", "close"]).reset_index(drop=True)
        if work.empty:
            return pd.DataFrame()
        close = work["close"]
        high = work["high"]
        low = work["low"]
        up = close.diff().clip(lower=0).rolling(14, min_periods=1).mean()
        dn = (-close.diff().clip(upper=0)).rolling(14, min_periods=1).mean()
        rng = (high - low).abs().rolling(14, min_periods=1).mean().replace(0, np.nan)
        work["plus_di"] = (up / rng * 25).replace([np.inf, -np.inf], np.nan).fillna(10).clip(0, 60)
        work["minus_di"] = (dn / rng * 25).replace([np.inf, -np.inf], np.nan).fillna(10).clip(0, 60)
        work["pressure"] = work["plus_di"] - work["minus_di"]
        work["adx"] = work["pressure"].abs().rolling(14, min_periods=1).mean().clip(0, 60)
        work["atr"] = (high - low).abs().rolling(14, min_periods=1).mean().fillna(0)
        work["adx_slope"] = work["adx"].diff().fillna(0)
        work["momentum"] = close.diff(10).fillna(0)
        return work.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
    except Exception:
        return pd.DataFrame()


def _basic_engine_quant(dfi):
    if not isinstance(dfi, pd.DataFrame) or dfi.empty:
        return {"bias": "WAIT", "safe_pct": 0, "scale10": 0}
    last = dfi.iloc[-1]
    pressure = _engine_numeric(last.get("pressure", 0))
    adx = _engine_numeric(last.get("adx", 0))
    slope = _engine_numeric(last.get("adx_slope", 0))
    raw = min(100.0, max(0.0, abs(pressure) * 2.2 + adx * 1.1 + max(0, slope) * 8))
    bias = "BUY" if pressure > 3 else ("SELL" if pressure < -3 else "WAIT")
    if adx < 12:
        bias = "WAIT"
        raw *= 0.55
    return {"bias": bias, "safe_pct": round(raw, 2), "scale10": round(raw / 10, 2), "adx": adx, "pressure": pressure}


def _engine_analyze_shared_df(df):
    out = {
        "status": "NO DATA",
        "rows": 0,
        "bias": "WAIT",
        "safe_pct": 0.0,
        "adx": 0.0,
        "pressure": 0.0,
        "trend": "UNKNOWN",
        "price_speed_1": 0.0,
        "price_speed_10": 0.0,
        "volatility_pct": 0.0,
        "fat_tail_z": "N/A",
        "data_warning": "Connect MT5 / Doo Bridge / TwelveData from the sidebar.",
    }
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return out
    try:
        if callable(_safe_add_indicators):
            dfi = _safe_add_indicators(df)
        else:
            dfi = _basic_engine_indicators(df)
        if dfi.empty:
            out["status"] = "BAD DATA"
            out["rows"] = len(df)
            out["data_warning"] = "OHLC normalization failed. Check time/open/high/low/close columns."
            return out
        if callable(_safe_quant_stack):
            q = _safe_quant_stack(df, dfi) or {}
        else:
            q = _basic_engine_quant(dfi)
        last = dfi.iloc[-1]
        close = pd.to_numeric(dfi["close"], errors="coerce").ffill()
        ret = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0)
        rstd = ret.tail(120).std()
        rz = "N/A"
        if rstd and np.isfinite(rstd) and rstd > 0:
            rz = round(float((ret.iloc[-1] - ret.tail(120).mean()) / rstd), 3)
        out.update({
            "status": "ACTIVE",
            "rows": int(len(dfi)),
            "bias": str(q.get("bias", "WAIT")),
            "safe_pct": round(_engine_numeric(q.get("safe_pct")), 2),
            "scale10": round(_engine_numeric(q.get("scale10")), 2),
            "adx": round(_engine_numeric(q.get("adx", last.get("adx", 0))), 2),
            "pressure": round(_engine_numeric(q.get("pressure", last.get("pressure", 0))), 2),
            "trend": "BUY pressure" if _engine_numeric(last.get("pressure")) > 3 else ("SELL pressure" if _engine_numeric(last.get("pressure")) < -3 else "Mixed / wait"),
            "price_speed_1": round(float(ret.tail(1).sum() * 100), 4),
            "price_speed_10": round(float(ret.tail(10).sum() * 100), 4),
            "volatility_pct": round(float(ret.tail(120).std() * 100), 5),
            "fat_tail_z": rz,
            "last_time": str(dfi["time"].iloc[-1]) if "time" in dfi.columns else "-",
            "data_warning": "Shared data is usable by Engine, Home, Train Data, and Pre Original.",
        })
        return out
    except Exception as exc:
        out["status"] = "SAFE ERROR"
        out["data_warning"] = f"Engine quick analysis failed safely: {exc}"
        return out


def _render_engine_decision_notes(summary):
    """Compact interpretation panel for Engine tab."""
    bias = str(summary.get("bias", "WAIT")).upper()
    safe = _engine_numeric(summary.get("safe_pct", 0))
    adx = _engine_numeric(summary.get("adx", 0))
    pressure = _engine_numeric(summary.get("pressure", 0))
    speed10 = _engine_numeric(summary.get("price_speed_10", 0))

    if bias == "BUY":
        action = "BUY side has stronger current pressure"
    elif bias == "SELL":
        action = "SELL side has stronger current pressure"
    else:
        action = "WAIT / hedge-protect mode"

    strength = "LOW"
    if safe >= 70 and adx >= 20:
        strength = "HIGH"
    elif safe >= 45 or adx >= 16:
        strength = "MEDIUM"

    c1, c2, c3 = st.columns(3)
    c1.info(f"Decision read: **{action}**")
    c2.info(f"Trust strength: **{strength}**")
    c3.info(f"Momentum: **{speed10}% / 10 candles**")

    if abs(pressure) < 3 or adx < 12:
        st.warning("Engine guard: pressure/ADX is weak. Avoid treating small BUY/SELL changes as a full-side exit signal.")
    elif safe >= 70:
        st.success("Engine guard: trend pressure is strong enough for serious monitoring. Confirm with account margin and Doo Prime position risk before full exit.")
    else:
        st.info("Engine guard: usable signal, but not maximum confidence. Prefer staged reduction or paired close logic if margin is dangerous.")


def _engine_export_text(summary, df):
    import json
    tail = []
    try:
        cols = [c for c in ["time", "open", "high", "low", "close", "volume"] if c in df.columns]
        if cols:
            tail = df[cols].tail(50).copy().to_dict(orient="records")
    except Exception:
        tail = []
    payload = {
        "export_time": str(pd.Timestamp.now()),
        "tab": "Engine",
        "symbol": st.session_state.get("symbol", "XAUUSD"),
        "source": st.session_state.get("source", "DISCONNECTED"),
        "timeframe": st.session_state.get("timeframe", "M1"),
        "connector_mode": st.session_state.get("connector_mode", "fallback"),
        "summary": summary,
        "engine_interpretation": {
            "bias_rule": "BUY if pressure is positive and ADX confirms; SELL if pressure is negative and ADX confirms; WAIT if weak/mixed.",
            "risk_warning": "This is market-direction analysis only. For hedged Doo Prime baskets, never exit one full side without checking margin level and remaining naked exposure.",
            "copy_paste_ready": True,
        },
        "latest_candles_tail_50": tail,
        "instruction_for_gpt": "Analyze Engine bias, ADX/DI pressure, speed, volatility, fat-tail z-score, and whether BUY/SELL/WAIT is safer. Do not treat N/A as zero.",
    }
    try:
        return "ENGINE TAB DATA EXPORT FOR GPT\n" + "=" * 40 + "\n" + json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    except Exception:
        return str(payload)


def _render_engine_full_upgrade():
    st.markdown("### 🚀 Engine Full Upgrade — shared-data decision layer")
    st.caption("Additive layer: your original Engine inner tabs still render below. This layer makes the Engine faster, safer, and easier to copy into GPT.")
    df = _engine_df()
    summary = _engine_analyze_shared_df(df)
    cols = st.columns(8)
    cols[0].metric("Status", summary.get("status", "NO DATA"))
    cols[1].metric("Rows", f"{summary.get('rows', 0):,}")
    cols[2].metric("Bias", summary.get("bias", "WAIT"))
    cols[3].metric("Safe %", summary.get("safe_pct", 0))
    cols[4].metric("ADX", summary.get("adx", 0))
    cols[5].metric("Pressure", summary.get("pressure", 0))
    cols[6].metric("10-candle %", summary.get("price_speed_10", 0))
    cols[7].metric("Fat-tail Z", summary.get("fat_tail_z", "N/A"))
    msg = str(summary.get("data_warning", ""))
    if summary.get("status") in ["ACTIVE"]:
        st.success(msg)
        _render_engine_decision_notes(summary)
    elif summary.get("status") == "NO DATA":
        st.info(msg)
    else:
        st.warning(msg)

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("🔄 Sync shared data into Engine", use_container_width=True, key="engine_upgrade_sync_now"):
            sync_backtest_keys_from_last_df()
            st.success("Synced shared dataframe into Engine inner modules.")
            _safe_rerun()
    with b2:
        if st.button("📋 Build Engine GPT export", use_container_width=True, key="engine_upgrade_build_export"):
            st.session_state["engine_gpt_export_text"] = _engine_export_text(summary, df)
            st.session_state["engine_gpt_export_built_at"] = str(pd.Timestamp.now())
    with b3:
        if st.button("🧹 Clear Engine export", use_container_width=True, key="engine_upgrade_clear_export"):
            st.session_state.pop("engine_gpt_export_text", None)
            st.session_state.pop("engine_gpt_export_built_at", None)

    text = st.session_state.get("engine_gpt_export_text", "")
    if text:
        st.caption(f"Engine export built at: {st.session_state.get('engine_gpt_export_built_at', '')}")
        st.text_area("Copy Engine data — click inside, Ctrl+A, Ctrl+C", value=text, height=260, key="engine_upgrade_export_textarea")
        st.download_button("⬇️ Download Engine GPT export TXT", data=text.encode("utf-8"), file_name="engine_tab_gpt_export.txt", mime="text/plain", use_container_width=True, key="engine_upgrade_export_download")

    with st.expander("🔎 Engine data quality + latest candles", expanded=False):
        if df.empty:
            st.info("No dataframe loaded yet.")
        else:
            keep = [c for c in ["time", "open", "high", "low", "close", "volume"] if c in df.columns]
            st.dataframe(df[keep].tail(120), use_container_width=True, hide_index=True)


def show():
    st.markdown("# ⚡ Engine workspace")
    st.caption("Fast mode: only the selected inner workspace renders. The duplicated Doo Prime Analysis inner tab was removed from Engine.")

    try:
        _render_engine_full_upgrade()
    except Exception as exc:
        st.warning(f"Engine full upgrade layer failed safely: {exc}")

    if callable(render_engine_pro_panel):
        try:
            render_engine_pro_panel()
        except Exception as exc:
            st.warning(f"Engine Pro upgrade layer failed safely: {exc}")

    with st.expander("🔗 Open shared Engine connection/status controls", expanded=False):
        _top_shared_connector()

    ok, rows = shared_data_status()
    quick = st.columns(4)
    quick[0].metric("Shared Data", "ACTIVE" if ok else "NO DATA")
    quick[1].metric("Rows", f"{rows:,}")
    quick[2].metric("Source", st.session_state.get("source", "DISCONNECTED"))
    quick[3].metric("TF", st.session_state.get("timeframe", "M1"))

    workspaces = ["⚡ Decision Engine", "📡 Prelive", "🌐 Websocket Live", "🧪 Backtest Original"]
    if callable(choice_buttons):
        workspace = choice_buttons(
            "Open Engine inner workspace",
            workspaces,
            key="engine_lazy_workspace",
            columns=4,
            default="⚡ Decision Engine",
            help_text="Only the selected inner workspace renders, so switching is faster.",
        )
    else:
        workspace = st.radio(
            "Open Engine inner workspace",
            workspaces,
            horizontal=True,
            key="engine_lazy_workspace",
        )

    if workspace == "⚡ Decision Engine":
        _show_shared_market_status()
        _call_original_show("engine")
        return

    if workspace == "📡 Prelive":
        _show_shared_market_status()
        _call_original_show("prelive")
        return

    if workspace == "🌐 Websocket Live":
        st.markdown("### 🌐 Websocket Live Feed")
        st.info("Optional fast tick layer. If it fails, your original sidebar connectors still work.")
        try:
            from core.websocket_feed import render_websocket_panel, websocket_status
            render_websocket_panel(location="engine")
            ws = websocket_status()
            c = st.columns(4)
            c[0].metric("WS Enabled", str(ws.get("enabled")))
            c[1].metric("Runtime Live", str(ws.get("runtime_connected")))
            c[2].metric("Queued Ticks", ws.get("queued_ticks", 0))
            c[3].metric("Provider", ws.get("provider", "generic"))
        except Exception as exc:
            st.error(f"Websocket panel failed safely: {exc}")
            with st.expander("Debug error"):
                st.exception(exc)
        return

    sync_backtest_keys_from_last_df()
    _show_shared_market_status()
    _call_original_show("backtest")

