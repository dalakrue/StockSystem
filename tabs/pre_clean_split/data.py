import json
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
import streamlit as st

from .symbols import mt5_symbol, twelve_symbol, timeframe_minutes, twelve_interval


def normalize_ohlc(df):
    base_cols = ["time", "open", "high", "low", "close", "volume"]

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=base_cols)

    work = df.copy()
    work.columns = [str(c).strip() for c in work.columns]

    rename = {
        "datetime": "time",
        "date": "time",
        "timestamp": "time",
        "Time": "time",
        "Datetime": "time",
        "Date": "time",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
        "tick_volume": "volume",
        "real_volume": "volume",
        "Tick Volume": "volume",
    }

    for old, new in rename.items():
        if old in work.columns and new not in work.columns:
            work = work.rename(columns={old: new})

    work = work.rename(columns={c: str(c).lower().strip() for c in work.columns})

    if "datetime" in work.columns and "time" not in work.columns:
        work = work.rename(columns={"datetime": "time"})

    if "date" in work.columns and "time" not in work.columns:
        work = work.rename(columns={"date": "time"})

    required = ["time", "open", "high", "low", "close"]
    missing = [c for c in required if c not in work.columns]

    if missing:
        raise ValueError(f"CSV/data missing columns: {missing}. Need time/open/high/low/close.")

    if pd.api.types.is_numeric_dtype(work["time"]):
        numeric_time = pd.to_numeric(work["time"], errors="coerce")
        max_time = numeric_time.dropna().max()

        if pd.isna(max_time):
            work["time"] = pd.NaT
        else:
            unit = "ms" if max_time > 10_000_000_000 else "s"
            work["time"] = pd.to_datetime(numeric_time, unit=unit, errors="coerce")
    else:
        work["time"] = pd.to_datetime(work["time"], errors="coerce")

    for c in ["open", "high", "low", "close", "volume"]:
        if c not in work.columns:
            work[c] = 0
        work[c] = pd.to_numeric(work[c], errors="coerce")

    work = work.dropna(subset=["time", "open", "high", "low", "close"])

    if work.empty:
        return pd.DataFrame(columns=base_cols)

    work = work.sort_values("time").drop_duplicates("time").reset_index(drop=True)

    return work[base_cols].copy()


def resample_m2_m3(df, tf):
    df = normalize_ohlc(df)
    tf = str(tf).upper().strip()

    if df.empty:
        return df

    if tf not in ["M2", "M3"]:
        return df

    rule = "2min" if tf == "M2" else "3min"
    temp = df.set_index("time").sort_index()

    out = pd.DataFrame()
    out["open"] = temp["open"].resample(rule).first()
    out["high"] = temp["high"].resample(rule).max()
    out["low"] = temp["low"].resample(rule).min()
    out["close"] = temp["close"].resample(rule).last()
    out["volume"] = temp["volume"].resample(rule).sum()

    return out.dropna(subset=["open", "high", "low", "close"]).reset_index()


@st.cache_data(ttl=300, show_spinner=False)
def load_twelve(symbol, tf, bars, api_key):
    api_key = str(api_key or "").strip()

    if not api_key:
        return pd.DataFrame(), "Twelve Data API key is empty."

    try:
        symbol = twelve_symbol(symbol)
        tf = str(tf).upper().strip()
        interval = twelve_interval(tf)
        bars = int(max(int(bars), 1))
    except Exception as exc:
        return pd.DataFrame(), f"Twelve Data input error: {exc}"

    outputsize = int(min(bars, 5000))

    if tf in ["M2", "M3"]:
        outputsize = int(min(outputsize * 3, 5000))

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
        "format": "JSON",
    }

    url = "https://api.twelvedata.com/time_series?" + urllib.parse.urlencode(params)

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
        )

        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode("utf-8", errors="replace")

        payload = json.loads(raw)

        if not isinstance(payload, dict):
            return pd.DataFrame(), "Twelve Data returned invalid JSON."

        if payload.get("status") == "error":
            return pd.DataFrame(), payload.get("message", "Twelve Data returned error.")

        values = payload.get("values", [])

        if not values:
            return pd.DataFrame(), "Twelve Data returned no candle values."

        df = pd.DataFrame(values)
        df = normalize_ohlc(df)
        df = resample_m2_m3(df, tf)

        if df.empty:
            return pd.DataFrame(), "Twelve Data candles could not be normalized."

        return df.tail(int(bars)).reset_index(drop=True), ""

    except Exception as exc:
        return pd.DataFrame(), f"Twelve Data failed: {exc}"


@st.cache_data(ttl=300, show_spinner=False)
def load_mt5(symbol, tf, bars):
    try:
        import MetaTrader5 as mt5
    except Exception:
        return pd.DataFrame(), (
            "MetaTrader5 is not installed. Use Twelve Data, CSV Upload, Session last_df, or Demo Data. "
            "For MT5 install: pip install MetaTrader5"
        )

    try:
        symbol = mt5_symbol(symbol)
        tf = str(tf).upper().strip()
        bars = int(max(int(bars), 1))
    except Exception as exc:
        return pd.DataFrame(), f"MT5 input error: {exc}"

    try:
        if not mt5.initialize():
            mt5.shutdown()

            if not mt5.initialize():
                return pd.DataFrame(), "MT5 initialize failed. Open MT5 terminal and log in first."

        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M2": getattr(mt5, "TIMEFRAME_M2", mt5.TIMEFRAME_M1),
            "M3": getattr(mt5, "TIMEFRAME_M3", mt5.TIMEFRAME_M1),
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }

        timeframe = tf_map.get(tf, mt5.TIMEFRAME_M1)

        if not mt5.symbol_select(symbol, True):
            return pd.DataFrame(), f"MT5 symbol not selectable: {symbol}"

        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)

        if rates is None or len(rates) == 0:
            return pd.DataFrame(), f"MT5 returned no candles for {symbol} {tf}"

        df = normalize_ohlc(pd.DataFrame(rates))

        if df.empty:
            return pd.DataFrame(), "MT5 candles could not be normalized."

        return df.tail(bars).reset_index(drop=True), ""

    except Exception as exc:
        return pd.DataFrame(), f"MT5 failed: {exc}"


def make_demo_data(symbol="XAUUSD", tf="M2", days=140, seed=10):
    rng = np.random.default_rng(seed)

    try:
        tf_min = int(timeframe_minutes(tf))
    except Exception:
        tf_min = 2

    tf = str(tf).upper().strip()

    if tf == "D1":
        periods = int(days)
        freq = "1D"
    else:
        periods = int(days * 24 * 60 / max(1, tf_min))
        freq = f"{max(1, tf_min)}min"

    periods = max(periods, 2000)

    end = pd.Timestamp.now().floor("min")
    times = pd.date_range(end=end, periods=periods, freq=freq)

    base = 2300 if "XAU" in str(symbol).upper() else 1.1000

    slow_regime = np.sin(np.linspace(0, 20 * np.pi, periods)) * 0.00045
    vol_regime = 0.00045 + 0.00075 * (np.sin(np.linspace(0, 8 * np.pi, periods)) > 0)
    noise = rng.standard_t(df=4, size=periods) * vol_regime
    rets = slow_regime + noise

    close = base * np.exp(np.cumsum(rets))
    open_ = np.r_[close[0], close[:-1]]

    spread = np.abs(rng.normal(0, 0.0007, periods)) * close

    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.integers(50, 2500, periods)

    if periods > 60:
        wick_idx = rng.choice(
            np.arange(50, periods),
            size=max(5, periods // 250),
            replace=False,
        )

        high[wick_idx] += spread[wick_idx] * rng.uniform(2, 5, len(wick_idx))
        low[wick_idx] -= spread[wick_idx] * rng.uniform(2, 5, len(wick_idx))
        volume[wick_idx] *= rng.integers(2, 6, len(wick_idx))

    return pd.DataFrame(
        {
            "time": times,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )