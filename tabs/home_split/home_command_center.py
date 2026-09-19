"""
Home Command Center upgrade.

Non-destructive layer: reads the same session_state data used by the original
Home/Doo Prime panels, adds faster quality checks, safer action gates, and
one-screen decision context. It does not place trades and does not remove or
replace the original Home logic.
"""
from __future__ import annotations

import importlib
import json
import time
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
import streamlit as st

try:
    from core.data_connectors import manual_connect, _normalize_ohlc
except Exception:  # pragma: no cover - Streamlit runtime fallback
    manual_connect = None
    _normalize_ohlc = None

try:
    from core.database import append_csv
except Exception:  # pragma: no cover
    append_csv = None


def _impl_func(name: str, fallback=None):
    """Lazy import to avoid circular imports with implementation.py."""
    try:
        impl = importlib.import_module("tabs.home_split.implementation")
        return getattr(impl, name, fallback)
    except Exception:
        return fallback


def _safe_num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return float(default)
        if isinstance(v, str):
            v = v.strip().replace(",", "")
            if not v:
                return float(default)
        out = float(v)
        if not np.isfinite(out):
            return float(default)
        return out
    except Exception:
        return float(default)


def _safe_df(df: Any) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    try:
        out = _normalize_ohlc(df) if callable(_normalize_ohlc) else df.copy()
    except Exception:
        out = df.copy()
    if out is None or not isinstance(out, pd.DataFrame):
        return pd.DataFrame()
    return out.reset_index(drop=True)


def _safe_rerun() -> None:
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def _age_text(ts: Any) -> str:
    try:
        if not ts:
            return "never"
        sec = max(0, int(time.time() - float(ts)))
        if sec < 60:
            return f"{sec}s ago"
        if sec < 3600:
            return f"{sec // 60}m {sec % 60}s ago"
        return f"{sec // 3600}h {(sec % 3600) // 60}m ago"
    except Exception:
        return "unknown"


def _session_name(dt: Any) -> str:
    """Approximate market session from the candle timestamp hour.

    We do not know broker server timezone, so this is a practical screen label,
    not a guaranteed exchange session classifier.
    """
    try:
        t = pd.to_datetime(dt, errors="coerce")
        if pd.isna(t):
            return "UNKNOWN"
        h = int(t.hour)
        if 0 <= h < 7:
            return "Asia / early liquidity"
        if 7 <= h < 12:
            return "London opening window"
        if 12 <= h < 16:
            return "London + NY overlap"
        if 16 <= h < 21:
            return "NY continuation"
        return "Late NY / rollover risk"
    except Exception:
        return "UNKNOWN"


def _data_quality(df: pd.DataFrame) -> Dict[str, Any]:
    df = _safe_df(df)
    if df.empty:
        return {
            "status": "NO DATA",
            "rows": 0,
            "message": "No shared candle dataframe is loaded yet.",
            "last_time": "-",
            "session": "UNKNOWN",
            "median_step_seconds": 0,
        }

    out = df.copy()
    if "time" in out.columns:
        out["time"] = pd.to_datetime(out["time"], errors="coerce")
        out = out.dropna(subset=["time"]).sort_values("time")
    for col in ["open", "high", "low", "close"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    rows = len(out)
    close_na = int(out["close"].isna().sum()) if "close" in out.columns else rows
    duplicate_times = int(out["time"].duplicated().sum()) if "time" in out.columns else 0
    last_time = out["time"].iloc[-1] if "time" in out.columns and rows else None
    first_time = out["time"].iloc[0] if "time" in out.columns and rows else None

    step_seconds = 0.0
    if "time" in out.columns and rows >= 3:
        diffs = out["time"].diff().dt.total_seconds().dropna()
        if len(diffs):
            step_seconds = float(diffs.median())

    source = str(st.session_state.get("source", "DISCONNECTED") or "DISCONNECTED").upper()
    if rows < 30 or close_na > rows * 0.05:
        status = "BAD"
        message = "Loaded data is too small or has many missing closes."
    elif "SAFE_DEMO" in source:
        status = "DEMO"
        message = "Source is SAFE_DEMO. Use for UI testing only, not real exit decisions."
    elif duplicate_times > max(3, rows * 0.02):
        status = "CHECK"
        message = "Many duplicate candle times were found. Refresh/reconnect before relying on signals."
    else:
        status = "GOOD"
        message = "Shared dataframe is usable. Still confirm account/margin before any exit action."

    return {
        "status": status,
        "rows": int(rows),
        "first_time": str(first_time) if first_time is not None else "-",
        "last_time": str(last_time) if last_time is not None else "-",
        "session": _session_name(last_time),
        "median_step_seconds": round(step_seconds, 2),
        "duplicate_times": duplicate_times,
        "missing_close": close_na,
        "message": message,
    }


def _market_read(df: pd.DataFrame) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    market: Dict[str, Any] = {}
    q: Dict[str, Any] = {}
    try:
        calc = _impl_func("_calc_market_analytics")
        if callable(calc):
            market, _frame = calc(df)
            market = market or {}
    except Exception as exc:
        market = {"error": str(exc)}
    try:
        qfunc = _impl_func("_safe_quant_stack")
        if callable(qfunc):
            q = qfunc(df) or {}
    except Exception as exc:
        q = {"error": str(exc)}
    return market, q


def _positions_df(account: Dict[str, Any]) -> pd.DataFrame:
    try:
        fn = _impl_func("_positions_frame")
        if callable(fn):
            return fn(account)
    except Exception:
        pass
    return pd.DataFrame()


def _read_account_now() -> None:
    fn = _impl_func("_safe_mt5_account_info")
    if callable(fn):
        info, ok, msg = fn()
        st.session_state.account_snapshot = info if isinstance(info, dict) else {}
        if ok:
            st.success(msg)
        else:
            st.warning(msg)
    else:
        st.warning("Account reader is unavailable. Check tabs/home_split/implementation.py.")


def _quick_market_refresh() -> None:
    if manual_connect is None:
        st.error("manual_connect is unavailable. Check core/data_connectors.py.")
        return
    try:
        with st.spinner("Fast refresh: loading 600 candles from the shared sidebar connector..."):
            df, ok, source, msg = manual_connect(
                mode=st.session_state.get("connector_mode", "fallback"),
                symbol=st.session_state.get("symbol", "XAUUSD"),
                api_key=st.session_state.get("twelve_api_key", ""),
                bars=600,
                timeframe=st.session_state.get("timeframe", "M1"),
                bridge_url=st.session_state.get("doo_bridge_url", ""),
                bridge_token=st.session_state.get("doo_bridge_token", ""),
            )
        if ok and str(source).upper() != "SAFE_DEMO":
            st.success(f"{source}: {len(df):,} rows loaded. {msg}")
        elif ok:
            st.warning(f"{source}: demo data loaded because live sources failed. {msg}")
        else:
            st.error(str(msg))
    except Exception as exc:
        st.error(f"Fast refresh failed safely: {exc}")


def _exit_gate_rows(action: Dict[str, Any], scenarios: pd.DataFrame, market: Dict[str, Any]) -> pd.DataFrame:
    direction = str(market.get("trend_direction", "UNKNOWN")).upper()
    dve = _safe_num(market.get("directional_efficiency"))
    trust = _safe_num(market.get("trust"))
    falling = _safe_num(market.get("efficiency_falling"))
    fat_available = bool(market.get("fat_tail_available", False))
    fat = abs(_safe_num(market.get("fat_tail_z"))) if fat_available else 0.0

    def pts(name: str) -> float:
        try:
            row = scenarios.loc[scenarios["Scenario"] == name]
            if row.empty:
                return 0.0
            v = row.iloc[0].get("Points To Stop-Out", 0)
            if isinstance(v, str) and "∞" in v:
                return float("inf")
            return _safe_num(v)
        except Exception:
            return 0.0

    hold_pts = pts("HOLD BOTH SIDES")
    exit_buy_pts = pts("EXIT ALL BUY NOW")
    exit_sell_pts = pts("EXIT ALL SELL NOW")

    gates = []
    gates.append({
        "Action": "EXIT ALL BUY only when",
        "Needed": "SELL/DOWN pressure is clean and BUY-only risk is not left behind",
        "Current Evidence": f"direction={direction}, DVE={round(dve,1)}, trust={round(trust,1)}, falling={round(falling,1)}",
        "Pass?": direction in ["DOWN", "SELL"] and dve >= 60 and trust >= 55 and exit_buy_pts >= 25 and (exit_buy_pts >= hold_pts * 0.55 or hold_pts == 0),
    })
    gates.append({
        "Action": "EXIT ALL SELL only when",
        "Needed": "BUY/UP pressure is clean and SELL-only risk is not left behind",
        "Current Evidence": f"direction={direction}, DVE={round(dve,1)}, trust={round(trust,1)}, falling={round(falling,1)}",
        "Pass?": direction in ["UP", "BUY"] and dve >= 60 and trust >= 55 and exit_sell_pts >= 25 and (exit_sell_pts >= hold_pts * 0.55 or hold_pts == 0),
    })
    gates.append({
        "Action": "Avoid full-side exit when",
        "Needed": "Fat tail extreme, trust weak, or scenario stop-out room is tiny",
        "Current Evidence": f"fat_tail={'N/A' if not fat_available else round(fat,2)}, exitBUY room={exit_buy_pts}, exitSELL room={exit_sell_pts}",
        "Pass?": (fat_available and fat >= 3) or trust < 50 or min(exit_buy_pts or 0, exit_sell_pts or 0) < 25,
    })
    return pd.DataFrame(gates)


def _emergency_context(account: Dict[str, Any], df: pd.DataFrame, market: Dict[str, Any], q: Dict[str, Any]):
    positions = _positions_df(account)
    if not isinstance(account, dict) or not account or positions.empty:
        return {}, pd.DataFrame(), positions
    try:
        fn = _impl_func("_build_emergency_exit_decision")
        if callable(fn):
            action, scenarios = fn(account, positions, market, q)
            return action or {}, scenarios if isinstance(scenarios, pd.DataFrame) else pd.DataFrame(), positions
    except Exception as exc:
        return {"action_short": "ERROR", "reason": str(exc)}, pd.DataFrame(), positions
    return {}, pd.DataFrame(), positions


def _save_home_snapshot(q: Dict[str, Any], market: Dict[str, Any], quality: Dict[str, Any], action: Dict[str, Any]) -> None:
    if append_csv is None:
        st.warning("CSV writer unavailable. Check core/database.py.")
        return
    try:
        append_csv("home_command_snapshots", {
            "time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": st.session_state.get("symbol", "XAUUSD"),
            "source": st.session_state.get("source", "DISCONNECTED"),
            "timeframe": st.session_state.get("timeframe", "M1"),
            "rows": quality.get("rows", 0),
            "quality": quality.get("status", "UNKNOWN"),
            "bias": q.get("bias", "WAIT"),
            "safe_pct": q.get("safe_pct", 0),
            "market_direction": market.get("trend_direction", "UNKNOWN"),
            "regime": market.get("regime", "NO DATA"),
            "dve": market.get("directional_efficiency", 0),
            "trust": market.get("trust", 0),
            "fat_tail_z": market.get("fat_tail_z", 0),
            "emergency_action": action.get("action_short", "READ"),
        })
        st.success("Home command snapshot saved.")
    except Exception as exc:
        st.warning(f"Snapshot save failed: {exc}")


def _json_ready(obj: Any) -> Any:
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient="records")
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _json_ready(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_ready(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    return obj


def render_home_command_center() -> None:
    st.markdown("## 🧭 Home Command Center — fast risk + trend screen")
    st.caption("Built from the same shared sidebar data. It is a decision-support layer only; it never opens/closes trades.")

    df = _safe_df(st.session_state.get("last_df"))
    account = st.session_state.get("account_snapshot", {}) or {}
    quality = _data_quality(df)
    market, q = _market_read(df)
    action, scenarios, positions = _emergency_context(account, df, market, q)

    action_cols = st.columns(3)
    with action_cols[0]:
        if st.button("⚡ Fast refresh 600", use_container_width=True, key="home_cmd_fast_refresh"):
            _quick_market_refresh()
            _safe_rerun()
    with action_cols[1]:
        if st.button("🏦 Read account now", use_container_width=True, key="home_cmd_read_account"):
            _read_account_now()
            _safe_rerun()
    with action_cols[2]:
        if st.button("🧠 Open Train Data", use_container_width=True, key="home_cmd_train"):
            st.session_state.tab_choice = "Train Data"
            _safe_rerun()

    # Silent auto-save replaces the old manual Home snapshot button.
    try:
        last_save = float(st.session_state.get("home_cmd_last_auto_save", 0) or 0)
        if append_csv is not None and time.time() - last_save >= 60 and (quality.get("rows", 0) or action):
            append_csv("home_command_snapshots", {
                "time": pd.Timestamp.now(),
                "symbol": st.session_state.get("symbol", "XAUUSD"),
                "source": st.session_state.get("source", "DISCONNECTED"),
                "quality_status": quality.get("status", ""),
                "rows": quality.get("rows", 0),
                "bias": q.get("bias", "WAIT") if isinstance(q, dict) else "WAIT",
                "safe_pct": q.get("safe_pct", 0) if isinstance(q, dict) else 0,
                "direction": market.get("trend_direction", "") if isinstance(market, dict) else "",
                "dve": market.get("directional_efficiency", 0) if isinstance(market, dict) else 0,
                "emergency_action": action.get("action_short", "") if isinstance(action, dict) else "",
            })
            st.session_state.home_cmd_last_auto_save = time.time()
    except Exception:
        pass

    st.markdown(
        f"""
        <div class="glass-card">
            <b>Data quality:</b> {quality.get('status')} • rows: <b>{quality.get('rows',0):,}</b> • source: <b>{st.session_state.get('source','DISCONNECTED')}</b> • last fetch: <b>{_age_text(st.session_state.get('last_fetch',0))}</b><br>
            <small>{quality.get('message','')} Last candle: {quality.get('last_time','-')} • Median step: {quality.get('median_step_seconds',0)}s • Practical session: {quality.get('session','UNKNOWN')}</small>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if quality.get("status") == "DEMO":
        st.error("SAFE_DEMO is active. Do not use this screen for real BUY/SELL exit timing until MT5, Doo Bridge, or Twelve Data returns live candles.")
    elif quality.get("status") in ["NO DATA", "BAD"]:
        st.warning("Market data is not reliable yet. Use Fast refresh or sidebar connector before reading trend direction.")

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("12H Bias", q.get("bias", "WAIT"))
    m2.metric("Safety %", round(_safe_num(q.get("safe_pct")), 1))
    m3.metric("Regime", market.get("regime", "NO DATA"))
    m4.metric("Direction", market.get("trend_direction", "UNKNOWN"))
    m5.metric("DVE %", round(_safe_num(market.get("directional_efficiency")), 2))
    m6.metric("Trust %", round(_safe_num(market.get("trust")), 1))

    if isinstance(account, dict) and account:
        balance = _safe_num(account.get("balance"))
        equity = _safe_num(account.get("equity"), balance)
        margin = _safe_num(account.get("margin"))
        free = _safe_num(account.get("margin_free"))
        ml = _safe_num(account.get("margin_level"), equity / max(margin, 1e-9) * 100.0 if margin else 0)
        floating = _safe_num(account.get("profit"), equity - balance)
        stopout = _safe_num(account.get("margin_so_so"), _safe_num(st.session_state.get("doo_stopout_level", 30.0), 30.0))
        stopout_gap = ml - stopout
        ac = st.columns(6)
        ac[0].metric("Margin Level %", round(ml, 2))
        ac[1].metric("Stop-out Gap %", round(stopout_gap, 2))
        ac[2].metric("Equity", round(equity, 2))
        ac[3].metric("Free Margin", round(free, 2))
        ac[4].metric("Floating P/L", round(floating, 2))
        ac[5].metric("Open Positions", len(positions) if isinstance(positions, pd.DataFrame) else 0)
        if ml and ml <= 80:
            st.error("Margin level is in the danger zone. Priority is survival room; avoid opening new positions and avoid full-side exit unless the scenario table confirms enough room.")
        elif ml and ml <= 150:
            st.warning("Margin level is tight. Full BUY/SELL basket exit needs stronger confirmation than normal.")
    else:
        st.info("No account snapshot loaded yet. Click Read account now to enable margin-level and position-basket checks.")

    st.markdown("### 🚦 Exit Decision Guard")
    if action:
        short = action.get("action_short", "READ")
        reason = action.get("reason", "")
        if short in ["URGENT BOTH", "DANGER HOLD", "HOLD/PAIR"]:
            st.warning(f"{short}: {reason}")
        elif short in ["EXIT BUY", "EXIT SELL"]:
            st.success(f"{short}: {reason}")
        else:
            st.info(f"{short}: {reason}")
    else:
        st.info("Read both market data and account/positions before choosing BUY or SELL basket exit.")

    if isinstance(scenarios, pd.DataFrame) and not scenarios.empty:
        gate_df = _exit_gate_rows(action, scenarios, market)
        with st.expander("📋 Open gate decision table", expanded=False):
            st.dataframe(gate_df, use_container_width=True, hide_index=True)
        with st.expander("🚨 Open emergency scenario stop-out table", expanded=False):
            st.dataframe(scenarios, use_container_width=True, hide_index=True)

    with st.expander("📋 Copy compact Home Command Center report", expanded=False):
        report = {
            "time": str(pd.Timestamp.now()),
            "symbol": st.session_state.get("symbol", "XAUUSD"),
            "source": st.session_state.get("source", "DISCONNECTED"),
            "timeframe": st.session_state.get("timeframe", "M1"),
            "data_quality": quality,
            "quant_stack": q,
            "market": market,
            "emergency_action": action,
            "scenarios": scenarios,
            "account_loaded": bool(account),
            "position_count": int(len(positions)) if isinstance(positions, pd.DataFrame) else 0,
        }
        text = json.dumps(_json_ready(report), ensure_ascii=False, indent=2, default=str)
        st.text_area("Select all / copy", text, height=240, key="home_cmd_copy_text")
        st.caption("⬇️ File downloads are centralized in the sidebar Download Center. Copy text remains here for GPT paste workflow.")
