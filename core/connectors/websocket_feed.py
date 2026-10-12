"""
Optional websocket live feed layer for the Streamlit quant app.
This module is intentionally safe: if websocket-client is not installed or a
server disconnects, the original MT5/Twelve/Doo connector flow still works.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import streamlit as st

from core.common import log_event
from core.data_connectors import _normalize_ohlc, _clean_symbol

try:
    import websocket  # websocket-client package
except Exception:  # pragma: no cover
    websocket = None


@dataclass
class WSRuntime:
    thread: Optional[threading.Thread] = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    queue: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=5000))
    connected: bool = False
    last_error: str = ""
    last_message_time: float = 0.0
    url: str = ""
    provider: str = "generic"
    symbol: str = "XAUUSD"


_RUNTIME = WSRuntime()


def _runtime() -> WSRuntime:
    return _RUNTIME


def _safe_log(msg: str) -> None:
    try:
        log_event(msg)
    except Exception:
        pass


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        v = float(value)
        if pd.isna(v):
            return default
        return v
    except Exception:
        return default


def _message_to_tick(raw: Any, symbol: str = "XAUUSD") -> Optional[Dict[str, Any]]:
    """Convert many common websocket JSON shapes into a normalized tick."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    # Twelve Data websocket commonly sends event=price with price/symbol/timestamp.
    event = str(data.get("event", data.get("type", ""))).lower()
    if event in {"heartbeat", "ping", "status"}:
        return None

    price = None
    for key in ["price", "bid", "ask", "close", "last", "c", "p"]:
        price = _safe_float(data.get(key), None)
        if price is not None:
            break

    if price is None:
        # Sometimes payload is nested under data.
        nested = data.get("data")
        if isinstance(nested, dict):
            for key in ["price", "bid", "ask", "close", "last", "c", "p"]:
                price = _safe_float(nested.get(key), None)
                if price is not None:
                    data = nested
                    break

    if price is None:
        return None

    ts = data.get("timestamp", data.get("time", data.get("datetime", None)))
    try:
        if ts is None:
            tick_time = pd.Timestamp.utcnow().tz_localize(None)
        elif isinstance(ts, (int, float)):
            # Handle seconds and milliseconds.
            unit = "ms" if float(ts) > 10_000_000_000 else "s"
            tick_time = pd.to_datetime(ts, unit=unit, errors="coerce")
        else:
            tick_time = pd.to_datetime(ts, errors="coerce")
        if pd.isna(tick_time):
            tick_time = pd.Timestamp.utcnow().tz_localize(None)
    except Exception:
        tick_time = pd.Timestamp.utcnow().tz_localize(None)

    return {
        "time": tick_time,
        "symbol": _clean_symbol(data.get("symbol", symbol)),
        "price": float(price),
        "bid": _safe_float(data.get("bid"), float(price)),
        "ask": _safe_float(data.get("ask"), float(price)),
        "raw": data,
    }



def _provider_symbol(provider: str, symbol: str) -> str:
    raw = _clean_symbol(symbol)
    if str(provider or "").lower() == "twelve":
        mapping = {
            "XAUUSD": "XAU/USD", "XAGUSD": "XAG/USD", "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD",
            "USDJPY": "USD/JPY", "AUDUSD": "AUD/USD", "USDCAD": "USD/CAD", "USDCHF": "USD/CHF",
            "NZDUSD": "NZD/USD", "BTCUSD": "BTC/USD", "ETHUSD": "ETH/USD",
        }
        return mapping.get(raw, raw)
    return raw

def _worker(url: str, provider: str, symbol: str, api_key: str, stop_event: threading.Event, q: queue.Queue) -> None:
    rt = _runtime()
    if websocket is None:
        rt.last_error = "websocket-client is not installed. Run: pip install websocket-client"
        rt.connected = False
        return

    ws = None
    try:
        ws = websocket.WebSocketApp(
            url,
            on_open=lambda wsapp: _on_open(wsapp, provider, symbol),
            on_message=lambda wsapp, msg: _on_message(msg, symbol, q),
            on_error=lambda wsapp, err: _on_error(str(err)),
            on_close=lambda wsapp, code, msg: _on_close(code, msg),
        )
        rt.connected = False
        rt.last_error = ""
        while not stop_event.is_set():
            ws.run_forever(ping_interval=20, ping_timeout=10, reconnect=5)
            if not stop_event.is_set():
                time.sleep(2)
    except Exception as exc:
        rt.last_error = str(exc)
        rt.connected = False
    finally:
        rt.connected = False
        try:
            if ws is not None:
                ws.close()
        except Exception:
            pass


def _on_open(wsapp: Any, provider: str, symbol: str) -> None:
    rt = _runtime()
    rt.connected = True
    rt.last_error = ""
    _safe_log(f"Websocket opened: {provider} {symbol}")
    try:
        if provider == "twelve":
            wsapp.send(json.dumps({"action": "subscribe", "params": {"symbols": _provider_symbol(provider, symbol)}}))
    except Exception as exc:
        rt.last_error = f"Subscribe failed: {exc}"


def _on_message(message: Any, symbol: str, q: queue.Queue) -> None:
    rt = _runtime()
    tick = _message_to_tick(message, symbol=symbol)
    if tick is None:
        return
    rt.last_message_time = time.time()
    try:
        q.put_nowait(tick)
    except queue.Full:
        try:
            q.get_nowait()
            q.put_nowait(tick)
        except Exception:
            pass


def _on_error(error: str) -> None:
    rt = _runtime()
    rt.last_error = error


def _on_close(code: Any, message: Any) -> None:
    rt = _runtime()
    rt.connected = False
    if code or message:
        rt.last_error = f"Closed: {code} {message}"


def build_ws_url(provider: str, url: str, api_key: str) -> str:
    provider = str(provider or "generic").lower()
    if provider == "twelve":
        key = str(api_key or "").strip()
        return f"wss://ws.twelvedata.com/v1/quotes/price?apikey={key}"
    return str(url or "").strip()


def start_websocket(provider: str, url: str, symbol: str, api_key: str = "") -> Tuple[bool, str]:
    rt = _runtime()
    stop_websocket()

    provider = str(provider or "generic").lower()
    symbol = _clean_symbol(symbol)
    final_url = build_ws_url(provider, url, api_key)

    if not final_url:
        return False, "Missing websocket URL. For Twelve Data, choose provider=twelve and enter API key."

    rt.stop_event = threading.Event()
    rt.queue = queue.Queue(maxsize=5000)
    rt.url = final_url
    rt.provider = provider
    rt.symbol = symbol
    rt.last_error = ""
    rt.last_message_time = 0.0

    thread = threading.Thread(
        target=_worker,
        args=(final_url, provider, symbol, api_key, rt.stop_event, rt.queue),
        daemon=True,
        name="quant-websocket-feed",
    )
    rt.thread = thread
    thread.start()

    st.session_state.ws_enabled = True
    st.session_state.ws_provider = provider
    st.session_state.ws_url = url
    st.session_state.ws_symbol = symbol
    st.session_state.ws_last_start = time.time()
    _safe_log(f"Websocket start requested: {provider} {symbol}")
    return True, "Websocket started. Wait a few seconds, then use Refresh/auto-refresh to consume ticks."


def stop_websocket() -> Tuple[bool, str]:
    rt = _runtime()
    try:
        rt.stop_event.set()
        rt.connected = False
    except Exception:
        pass
    try:
        st.session_state.ws_enabled = False
    except Exception:
        pass
    return True, "Websocket stopped."


def drain_ticks(max_ticks: int = 1000) -> pd.DataFrame:
    rt = _runtime()
    rows = []
    for _ in range(int(max_ticks)):
        try:
            rows.append(rt.queue.get_nowait())
        except queue.Empty:
            break
        except Exception:
            break
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def ticks_to_ohlc(ticks: pd.DataFrame, timeframe: str = "M1") -> pd.DataFrame:
    if ticks is None or ticks.empty or "price" not in ticks.columns:
        return pd.DataFrame()
    df = ticks.copy()
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["time", "price"]).sort_values("time")
    if df.empty:
        return pd.DataFrame()

    tf = str(timeframe or "M1").upper()
    rules = {
        "M1": "1min", "M2": "2min", "M3": "3min", "M5": "5min", "M10": "10min",
        "M15": "15min", "M30": "30min", "H1": "1h", "H4": "4h", "D1": "1D",
    }
    rule = rules.get(tf, "1min")
    ohlc = (
        df.set_index("time")["price"]
        .resample(rule, label="right", closed="right")
        .ohlc()
        .dropna()
        .reset_index()
    )
    ohlc["volume"] = 0
    return _normalize_ohlc(ohlc)


def consume_websocket_into_session() -> Tuple[int, str]:
    ticks = drain_ticks(2000)
    if ticks.empty:
        return 0, "No new websocket ticks."

    st.session_state.ws_ticks = pd.concat(
        [st.session_state.get("ws_ticks", pd.DataFrame()), ticks],
        ignore_index=True,
    ).tail(20000)

    tf = st.session_state.get("timeframe", "M1")
    ws_ohlc = ticks_to_ohlc(st.session_state.ws_ticks, tf)
    if ws_ohlc.empty:
        return len(ticks), "Ticks received, waiting for candle build."

    existing = st.session_state.get("last_df")
    if isinstance(existing, pd.DataFrame) and not existing.empty:
        combined = pd.concat([existing, ws_ohlc], ignore_index=True)
        combined = _normalize_ohlc(combined)
        if "time" in combined.columns:
            combined = combined.drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)
    else:
        combined = ws_ohlc

    st.session_state.last_df = combined.tail(max(600, int(st.session_state.get("connector_bars", 600))))
    st.session_state.connected = True
    st.session_state.source = "WEBSOCKET"
    st.session_state.last_fetch = time.time()
    st.session_state.symbol = _clean_symbol(st.session_state.get("symbol", st.session_state.get("ws_symbol", "XAUUSD")))
    return len(ticks), f"Merged {len(ticks)} websocket ticks into shared dataframe."


def websocket_status() -> Dict[str, Any]:
    rt = _runtime()
    age = None
    if rt.last_message_time:
        age = max(0.0, time.time() - rt.last_message_time)
    return {
        "enabled": bool(st.session_state.get("ws_enabled", False)),
        "runtime_connected": bool(rt.connected),
        "provider": rt.provider,
        "symbol": rt.symbol,
        "url": rt.url,
        "last_error": rt.last_error,
        "last_message_age": age,
        "queued_ticks": rt.queue.qsize() if rt.queue is not None else 0,
    }


def render_websocket_panel(location: str = "sidebar") -> None:
    provider_options = ["generic", "twelve"]
    provider = st.selectbox(
        "Websocket provider",
        provider_options,
        index=provider_options.index(st.session_state.get("ws_provider", "generic")) if st.session_state.get("ws_provider", "generic") in provider_options else 0,
        key=f"{location}_ws_provider",
    )
    st.session_state.ws_provider = provider

    if provider == "generic":
        st.session_state.ws_url = st.text_input(
            "Generic websocket URL",
            value=st.session_state.get("ws_url", ""),
            placeholder="ws://127.0.0.1:8765 or wss://...",
            key=f"{location}_ws_url",
        )
    else:
        st.info("Twelve Data websocket uses your Twelve API key and subscribes to the current symbol.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶ Start WS", use_container_width=True, key=f"{location}_start_ws"):
            ok, msg = start_websocket(
                provider=provider,
                url=st.session_state.get("ws_url", ""),
                symbol=st.session_state.get("symbol", "XAUUSD"),
                api_key=st.session_state.get("twelve_api_key", ""),
            )
            (st.success if ok else st.error)(msg)
    with c2:
        if st.button("■ Stop WS", use_container_width=True, key=f"{location}_stop_ws"):
            ok, msg = stop_websocket()
            (st.success if ok else st.warning)(msg)

    if st.button("⬇ Consume WS ticks", use_container_width=True, key=f"{location}_consume_ws"):
        n, msg = consume_websocket_into_session()
        if n:
            st.success(msg)
        else:
            st.info(msg)

    status = websocket_status()
    st.caption(
        f"WS enabled={status['enabled']} | live={status['runtime_connected']} | queued={status['queued_ticks']} | last tick age={status['last_message_age']}"
    )
    if status.get("last_error"):
        st.warning(status["last_error"])
