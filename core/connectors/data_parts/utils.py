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




def _connect_signature(mode, symbol, timeframe, bars, bridge_url=""):
    return "|".join([
        str(mode or "fallback").lower(),
        _clean_symbol(symbol),
        str(timeframe or "M1").upper(),
        str(int(bars or 0)),
        str(bridge_url or "").strip(),
    ])

def _recent_shared_dataframe(signature, max_age_seconds=3):
    """Return a hot shared dataframe to prevent duplicate connector calls.

    Streamlit reruns can call the connector from sidebar, Home, and Doo Prime
    during the same user action. A short hot-cache window keeps navigation fast
    and avoids repeated MT5/TwelveData calls without changing the longer
    auto-refresh rules.
    """
    try:
        if not st.session_state.get("connected"):
            return None
        if st.session_state.get("connector_last_signature") != signature:
            return None
        age = time.time() - float(st.session_state.get("last_fetch", 0) or 0)
        if age > float(max_age_seconds):
            return None
        df = _normalize_ohlc(st.session_state.get("last_df"))
        if df.empty:
            return None
        return df
    except Exception:
        return None

def _safe_log(msg):
    try:
        log_event(msg)
    except Exception:
        pass

def _import_mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except Exception:
        return None

def _clean_symbol(symbol="XAUUSD"):
    return str(symbol or "XAUUSD").strip().upper().replace("/", "").replace(" ", "")

def _resolve_mt5_symbol(mt5, symbol="XAUUSD"):
    """Select the best MT5 alias, including broker suffix variants."""
    canonical = _clean_symbol(symbol)
    try:
        from core.multi_symbol_field10_20260701 import PROVIDER_ALIASES, normalize_symbol
        canonical = normalize_symbol(canonical)
        alias_values = list(PROVIDER_ALIASES.get("mt5", {}).get(canonical, (canonical,)))
    except Exception:
        alias_values = [canonical]
    bases = []
    for alias in [canonical, *alias_values]:
        base = _clean_symbol(alias)
        if base not in bases:
            bases.append(base)

    for base in bases:
        try:
            if mt5.symbol_select(base, True):
                return base, True, "exact" if base == canonical else f"provider alias matched {canonical} -> {base}"
        except Exception:
            pass

    names = []
    for base in bases:
        try:
            candidates = list(mt5.symbols_get(f"*{base}*") or [])
        except Exception:
            candidates = []
        for item in candidates:
            try:
                name = str(getattr(item, "name", "") or "")
                if name:
                    names.append((base, name))
            except Exception:
                pass

    names = sorted(set(names), key=lambda pair: (not pair[1].upper().startswith(pair[0]), len(pair[1]), pair[1]))
    for base, name in names:
        try:
            if mt5.symbol_select(name, True):
                return name, True, f"broker symbol matched {canonical} -> {name}"
        except Exception:
            continue

    return canonical, False, f"MT5 symbol not found/selected for {canonical}. Add it in Market Watch or use the broker exact symbol name."

def _twelve_symbol(symbol="XAUUSD"):
    """Return a Twelve Data-compatible symbol without hard-coding only majors.

    The previous formatter cleaned ``EUR/CHF`` into ``EURCHF`` and then only
    re-added the slash for a short whitelist of major pairs. Selector 2 often
    contains crosses such as EURCHF, EURAUD, EURCAD, EURNZD, GBPCHF; sending
    those as unslashed symbols makes Twelve Data answer HTTP 404 / invalid
    symbol and burns local credits.

    Keep explicit aliases for metals, crypto, and index names, but format any
    valid six-letter FX pair as BASE/QUOTE before the request is sent.
    """
    raw = _clean_symbol(symbol)

    mapping = {
        "XAUUSD": "XAU/USD",
        "XAGUSD": "XAG/USD",
        "XPTUSD": "XPT/USD",
        "XPDUSD": "XPD/USD",
        "BTCUSD": "BTC/USD",
        "ETHUSD": "ETH/USD",
        "SOLUSD": "SOL/USD",
        "XRPUSD": "XRP/USD",
        "BNBUSD": "BNB/USD",
        "ADAUSD": "ADA/USD",
        "DOGEUSD": "DOGE/USD",
        "AVAXUSD": "AVAX/USD",
        "DOTUSD": "DOT/USD",
        "LINKUSD": "LINK/USD",
        "NAS100": "NDX",
        "US500": "SPX",
    }
    if raw in mapping:
        return mapping[raw]

    fiat_codes = {
        "AUD", "CAD", "CHF", "CNH", "CNY", "CZK", "DKK", "EUR", "GBP",
        "HKD", "HUF", "JPY", "MXN", "NOK", "NZD", "PLN", "SEK", "SGD",
        "TRY", "USD", "ZAR", "RON", "THB", "ILS", "INR", "KRW", "MYR",
    }
    if len(raw) == 6 and raw.isalpha():
        base, quote = raw[:3], raw[3:]
        if base in fiat_codes and quote in fiat_codes:
            return f"{base}/{quote}"

    return raw

def _normalize_ohlc(df):
    if df is None or len(df) == 0:
        return pd.DataFrame()

    df = df.copy()

    rename_map = {
        "datetime": "time",
        "date": "time",
        "timestamp": "time",
        "tick_volume": "volume",
        "real_volume": "volume",
    }

    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})

    if "time" not in df.columns:
        return pd.DataFrame()

    df["time"] = pd.to_datetime(df["time"], errors="coerce")

    for c in ["open", "high", "low", "close"]:
        if c not in df.columns:
            return pd.DataFrame()
        df[c] = pd.to_numeric(df[c], errors="coerce")

    if "volume" not in df.columns:
        df["volume"] = 0

    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)

    df = df.dropna(subset=["time", "open", "high", "low", "close"])
    df = df.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)

    if df.empty:
        return pd.DataFrame()

    return df[["time", "open", "high", "low", "close", "volume"]].copy()

def resample_ohlc(df, timeframe="M2"):
    df = _normalize_ohlc(df)
    try:
        from core.code_quality import normalize_market_frame
        df = normalize_market_frame(df)
    except Exception:
        pass

    if df.empty:
        return pd.DataFrame()

    tf = str(timeframe or "M1").strip().upper()

    if tf in ("M1", "1MIN", "1T"):
        return df.copy()

    minute_map = {
        "M2": "2min",
        "M3": "3min",
        "M4": "4min",
        "M5": "5min",
        "M10": "10min",
        "M15": "15min",
        "M30": "30min",
    }

    rule = minute_map.get(tf)

    if not rule:
        return df.copy()

    out = (
        df.set_index("time")
        .resample(rule, label="right", closed="right")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
        .reset_index()
    )

    return out[["time", "open", "high", "low", "close", "volume"]].copy()

