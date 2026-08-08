import time
import pandas as pd
import requests
import streamlit as st

from core.common import synthetic_ohlc, log_event

try:
    from core.system_contract import (
        mark_data_version,
        update_connection_health,
        update_data_quality_from_session,
        record_system_event,
    )
except Exception:  # keeps old connector usable even if upgrade file is missing
    mark_data_version = None
    update_connection_health = None
    update_data_quality_from_session = None
    record_system_event = None


MT5_TIMEFRAMES = {
    "M1": "TIMEFRAME_M1",
    "M2": "TIMEFRAME_M2",
    "M3": "TIMEFRAME_M3",
    "M4": "TIMEFRAME_M4",
    "M5": "TIMEFRAME_M5",
    "M10": "TIMEFRAME_M10",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}

TWELVE_INTERVALS = {
    "M1": "1min",
    "M2": "1min",
    "M3": "1min",
    "M4": "1min",
    "M5": "5min",
    "M10": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1day",
}




from .utils import (
    _connect_signature,
    _recent_shared_dataframe,
    _safe_log,
    _clean_symbol,
    _normalize_ohlc,
    resample_ohlc,
    TWELVE_INTERVALS,
)
from .fetchers import fetch_mt5, fetch_twelve, fetch_doo_bridge

def manual_connect(
    mode="fallback",
    symbol="XAUUSD",
    api_key="",
    bars=500,
    timeframe="M1",
    bridge_url="",
    bridge_token="",
    allow_demo=None,
):
    timeframe = str(timeframe or "M1").upper()
    mode = str(mode or "fallback").lower()
    # Server-side Streamlit Secrets fallback. The resolved key is passed
    # directly to the connector and is never populated into a browser widget.
    if mode in {"twelve", "fallback", "finnhub"} and not str(api_key or "").strip():
        try:
            from core.secure_api_startup_20260619 import resolve_api_key
            logical_provider = "finnhub" if mode == "finnhub" else "second_api"
            api_key = resolve_api_key(logical_provider, st.session_state)
        except Exception:
            api_key = str(api_key or "")
    if allow_demo is None:
        try:
            allow_demo = bool(st.session_state.get("allow_safe_demo", False))
        except Exception:
            allow_demo = False
    allow_demo = bool(allow_demo)

    signature = _connect_signature(mode, symbol, timeframe, bars, bridge_url)
    hot_df = _recent_shared_dataframe(signature, max_age_seconds=3)
    if hot_df is not None:
        source = st.session_state.get("source", "CACHE")
        return hot_df, True, source, "Fast shared cache reused; duplicate connector call skipped."

    df = None
    ok = False
    msg = ""
    source = "UNKNOWN"

    if mode in ["safe_demo", "demo"]:
        base_bars = int(bars or 1500)
        raw = synthetic_ohlc(symbol, max(base_bars, 1500))
        if timeframe in ["M2", "M3", "M4", "M10"]:
            raw = resample_ohlc(raw, timeframe)
        df = raw
        ok = True
        source = "SAFE_DEMO"
        msg = "Safe demo data loaded by explicit user choice"

    elif mode == "mt5":
        df, ok, msg = fetch_mt5(symbol, timeframe=timeframe, bars=bars)
        source = "MT5" if ok else "MT5_FAILED"

    elif mode == "doo_bridge":
        df, ok, msg = fetch_doo_bridge(
            symbol=symbol,
            timeframe=timeframe,
            bars=bars,
            bridge_url=bridge_url,
            bridge_token=bridge_token,
        )
        source = "DOO_BRIDGE" if ok else "DOO_BRIDGE_FAILED"

    elif mode == "finnhub":
        # Route the legacy connector surface through the same exact-symbol,
        # exact-timeframe orchestrator used by the three multi-symbol loaders.
        # This keeps Finnhub and Twelve Data interchangeable without creating a
        # second candle-normalisation or persistence path.
        try:
            from core.data.market_data_orchestrator import MarketDataOrchestrator
            runtime_state = dict(st.session_state)
            runtime_state["connector_mode"] = "twelve_pool"
            runtime_state["finnhub_api_key"] = str(api_key or "").strip()
            result = MarketDataOrchestrator().fetch(
                symbol=symbol,
                timeframe=timeframe,
                state=runtime_state,
                bars=int(bars),
                run_id=str(runtime_state.get("settings_active_run_id_20260705") or "CONNECTOR"),
                force_live=True,
                essential=True,
            )
            df = result.frame.copy() if result.ok else pd.DataFrame()
            if not df.empty and "open_time" in df.columns and "time" not in df.columns:
                df = df.rename(columns={"open_time": "time"})
            ok = bool(result.ok and not df.empty)
            source = str(result.provider or "FINNHUB") if ok else "FINNHUB_FAILED"
            msg = str(result.message or "Finnhub candle load completed")
        except Exception as exc:
            df = pd.DataFrame()
            ok = False
            source = "FINNHUB_FAILED"
            msg = f"Finnhub load failed: {exc}"

    elif mode == "twelve":
        raw_tf = TWELVE_INTERVALS.get(timeframe, "1min")

        raw_bars = int(bars)

        if timeframe in ["M2", "M3", "M4", "M10"]:
            raw_tf = "1min"
            raw_bars = int(bars) * 5

        df, ok, msg = fetch_twelve(symbol, api_key, interval=raw_tf, bars=raw_bars)

        if ok and timeframe in ["M2", "M3", "M4", "M10"]:
            df = resample_ohlc(df, timeframe)
            msg = f"{msg} → resampled to {timeframe}"

        source = "TWELVE" if ok else "TWELVE_FAILED"

    else:
        # Strict fallback order: Twelve Data Plan A, MT5 Plan B. Finnhub and
        # Alpha Vantage are handled by the central market-data orchestrator.
        raw_tf = TWELVE_INTERVALS.get(timeframe, "1min")
        raw_bars = int(bars)
        if timeframe in ["M2", "M3", "M4", "M10"]:
            raw_tf = "1min"
            raw_bars = int(bars) * 5
        df, ok, msg = fetch_twelve(symbol, api_key, interval=raw_tf, bars=raw_bars)
        if ok and timeframe in ["M2", "M3", "M4", "M10"]:
            df = resample_ohlc(df, timeframe)
            msg = f"{msg} → resampled to {timeframe}"
        source = "TWELVE" if ok else "TWELVE_FAILED"

        if not ok:
            df, ok, msg = fetch_mt5(symbol, timeframe=timeframe, bars=bars)
            source = "MT5" if ok else "MT5_FAILED"

        if not ok and bridge_url:
            df, ok, msg = fetch_doo_bridge(
                symbol=symbol,
                timeframe=timeframe,
                bars=bars,
                bridge_url=bridge_url,
                bridge_token=bridge_token,
            )
            source = "DOO_BRIDGE" if ok else "FALLBACK_FAILED"

    # Use a previous real/cache dataframe only when it was not SAFE_DEMO. This
    # prevents the app from silently keeping demo candles after an MT5/Doo Prime
    # connection failure.
    previous_source = str(st.session_state.get("source", "") or "").upper()
    if (not ok) and st.session_state.get("last_df") is not None and previous_source not in ["SAFE_DEMO", "DISCONNECTED", ""]:
        cached = _normalize_ohlc(st.session_state.last_df)
        if not cached.empty:
            df = cached
            ok = True
            source = "CACHE"
            msg = f"{msg} | using previous non-demo cached dataframe so tabs do not blank"

    if not ok and allow_demo:
        base_bars = int(bars or 1500)

        if timeframe in ["M2", "M3", "M4", "M10"]:
            base_bars *= 5

        df = synthetic_ohlc(symbol, max(base_bars, 1500))

        if timeframe in ["M2", "M3", "M4", "M10"]:
            df = resample_ohlc(df, timeframe)

        ok = True
        source = "SAFE_DEMO"
        msg = f"{msg} | using safe demo data because Safe Demo fallback is enabled"

    if not ok:
        # Real connection failed and demo fallback is OFF. Do not overwrite the
        # screen with fake market data. This is safer for live Doo Prime decisions.
        st.session_state.connected = False
        st.session_state.source = source
        st.session_state.last_connection_error = str(msg)
        st.session_state.last_connection_message = str(msg)
        st.session_state.last_connection_rows = 0
        st.session_state.last_connection_mode = mode
        st.session_state.last_connected_symbol = _clean_symbol(symbol)
        st.session_state.last_connected_timeframe = timeframe
        try:
            if update_connection_health is not None:
                update_connection_health(
                    mode=mode,
                    source=source,
                    ok=False,
                    message=f"{msg} | Safe Demo fallback is OFF",
                    rows=0,
                    symbol=_clean_symbol(symbol),
                    timeframe=timeframe,
                    persist=True,
                )
        except Exception:
            pass
        _safe_log(f"Connection failed {source}: {_clean_symbol(symbol)} {timeframe} — demo disabled")
        return pd.DataFrame(), False, source, f"{msg} | Safe Demo fallback is OFF, so no fake candles were loaded"

    df = _normalize_ohlc(df)

    if df.empty:
        if allow_demo or source == "SAFE_DEMO":
            df = synthetic_ohlc(symbol, 1500)
            if timeframe in ["M2", "M3", "M4", "M10"]:
                df = resample_ohlc(df, timeframe)
            df = _normalize_ohlc(df)
            source = "SAFE_DEMO"
            msg = f"{msg} | normalized data empty, replaced by safe demo because Safe Demo fallback is enabled"
        else:
            st.session_state.connected = False
            st.session_state.source = f"{source}_EMPTY" if source else "DATA_EMPTY"
            st.session_state.last_connection_error = "Loaded data normalized to empty; Safe Demo fallback is OFF"
            return pd.DataFrame(), False, st.session_state.source, "Loaded data normalized to empty; Safe Demo fallback is OFF"

    st.session_state.last_df = df
    st.session_state.connected = True
    st.session_state.source = source
    st.session_state.last_fetch = time.time()
    st.session_state.timeframe = timeframe
    st.session_state.symbol = _clean_symbol(symbol)
    st.session_state.connector_last_signature = signature
    st.session_state.connector_last_result_ts = time.time()

    # 2026 non-destructive relationship/timing upgrade:
    # every successful connector run increments one shared data version and
    # writes a compact API/connection health event for all tabs to read.
    try:
        if mark_data_version is not None:
            mark_data_version(source=source, rows=len(df))
        if update_connection_health is not None:
            update_connection_health(
                mode=mode,
                source=source,
                ok=bool(ok),
                message=msg,
                rows=len(df),
                symbol=_clean_symbol(symbol),
                timeframe=timeframe,
                persist=True,
            )
        if update_data_quality_from_session is not None:
            update_data_quality_from_session(persist=True)
    except Exception:
        pass

    _safe_log(f"Connected {source}: {_clean_symbol(symbol)} {timeframe}")

    return df, bool(ok), source, msg

def maybe_refresh(
    symbol="XAUUSD",
    api_key="",
    refresh_seconds=600,
    bridge_url="",
    bridge_token="",
):
    if not st.session_state.get("connected"):
        return st.session_state.get("last_df")

    last = st.session_state.get("last_fetch", 0)

    try:
        should_refresh = time.time() - float(last) >= float(refresh_seconds)
    except Exception:
        should_refresh = True

    if should_refresh:
        source = st.session_state.get("source", "")

        if source == "MT5":
            mode = "mt5"
        elif source == "TWELVE":
            mode = "twelve"
        elif source == "DOO_BRIDGE":
            mode = "doo_bridge"
        else:
            mode = "fallback"

        manual_connect(
            mode=mode,
            symbol=symbol,
            api_key=api_key,
            bars=int(st.session_state.get("connector_bars", 600)),
            timeframe=st.session_state.get("timeframe", "M1"),
            bridge_url=bridge_url,
            bridge_token=bridge_token,
            allow_demo=bool(st.session_state.get("allow_safe_demo", False)),
        )

    return st.session_state.get("last_df")

def connect_history_60d(
    mode="fallback",
    symbol="XAUUSD",
    api_key="",
    timeframe="M1",
    bridge_url="",
    bridge_token="",
):
    tf = str(timeframe or "M1").upper()

    if tf == "M1":
        bars = 120000
    elif tf in ["M2", "M3", "M4"]:
        bars = 80000
    elif tf in ["M5", "M10", "M15"]:
        bars = 30000
    elif tf in ["M30", "H1"]:
        bars = 10000
    else:
        bars = 5000

    return manual_connect(
        mode=mode,
        symbol=symbol,
        api_key=api_key,
        bars=bars,
        timeframe=tf,
        bridge_url=bridge_url,
        bridge_token=bridge_token,
    )



def refresh_now(
    symbol="XAUUSD",
    api_key="",
    *,
    bridge_url="",
    bridge_token="",
    bars=None,
    timeframe=None,
    mode=None,
    allow_demo=None,
):
    """Public, connector-only forced refresh.

    This reuses :func:`manual_connect`, bypasses the interval timer, and never
    invokes the protected calculation orchestrator.  The last completed
    canonical generation remains published for read-only display.
    """
    current_source = str(st.session_state.get("source", "") or "").upper()
    resolved_mode = str(mode or "").lower().strip()
    if not resolved_mode:
        resolved_mode = {
            "MT5": "mt5",
            "TWELVE": "twelve",
            "DOO_BRIDGE": "doo_bridge",
            "SAFE_DEMO": "safe_demo",
        }.get(current_source, str(st.session_state.get("connector_mode", "fallback") or "fallback").lower())
    # Bypass the three-second duplicate-rerun cache for an explicit user refresh.
    # This changes only connector freshness state; it does not touch the last
    # completed canonical generation.
    st.session_state["last_fetch"] = 0.0
    return manual_connect(
        mode=resolved_mode,
        symbol=symbol or st.session_state.get("symbol", "XAUUSD"),
        api_key=api_key,
        bars=int(bars or st.session_state.get("connector_bars", 600)),
        timeframe=str(timeframe or st.session_state.get("timeframe", "M1")),
        bridge_url=bridge_url,
        bridge_token=bridge_token,
        allow_demo=bool(st.session_state.get("allow_safe_demo", False) if allow_demo is None else allow_demo),
    )
