"""
Engine Pro Upgrade Layer
Non-destructive: this module only reads st.session_state['last_df'] and writes optional
Engine history/export keys. It does not replace the original Engine inner modules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple

import numpy as np
import pandas as pd
import streamlit as st

try:
    from core.database import append_csv
except Exception:  # pragma: no cover
    append_csv = None


OHLC_ALIASES = {
    "datetime": "time", "date": "time", "timestamp": "time", "time_msc": "time",
    "o": "open", "open_price": "open", "bidopen": "open",
    "h": "high", "high_price": "high", "bidhigh": "high",
    "l": "low", "low_price": "low", "bidlow": "low",
    "c": "close", "price": "close", "last": "close", "bid": "close", "ask": "close",
    "tick_volume": "volume", "real_volume": "volume", "vol": "volume",
}


@dataclass
class EngineDecision:
    status: str = "NO DATA"
    rows: int = 0
    symbol: str = "XAUUSD"
    source: str = "DISCONNECTED"
    timeframe: str = "M1"
    last_time: str = "-"
    last_close: float = 0.0
    bias: str = "WAIT"
    confidence_pct: float = 0.0
    scale10: float = 0.0
    adx: float = 0.0
    plus_di: float = 0.0
    minus_di: float = 0.0
    pressure: float = 0.0
    atr: float = 0.0
    atr_pct: float = 0.0
    momentum_10_pct: float = 0.0
    momentum_30_pct: float = 0.0
    volatility_120_pct: float = 0.0
    fat_tail_z: float = 0.0
    dve_pct: float = 0.0
    rising_efficiency_pct: float = 0.0
    falling_efficiency_pct: float = 0.0
    regime: str = "UNKNOWN"
    exit_buy_guard: str = "BLOCK"
    exit_sell_guard: str = "BLOCK"
    data_quality_pct: float = 0.0
    warning: str = "Connect shared data first."


def _num(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        if np.isfinite(x):
            return x
    except Exception:
        pass
    return float(default)


def normalize_engine_df(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    work = df.copy()
    rename = {}
    for c in work.columns:
        key = str(c).strip().lower()
        if key in OHLC_ALIASES:
            rename[c] = OHLC_ALIASES[key]
    if rename:
        work = work.rename(columns=rename)
    if "time" not in work.columns:
        if isinstance(work.index, pd.DatetimeIndex):
            work = work.reset_index().rename(columns={"index": "time"})
        else:
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
    if "volume" not in work.columns:
        work["volume"] = 0
    for c in ["open", "high", "low", "close", "volume"]:
        work[c] = pd.to_numeric(work[c], errors="coerce").ffill()
        if c in {"open", "high", "low"}:
            work[c] = work[c].fillna(work["close"])
        else:
            work[c] = work[c].fillna(0)
    work = work.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").reset_index(drop=True)
    return work.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)


def add_engine_features(df: pd.DataFrame) -> pd.DataFrame:
    work = normalize_engine_df(df)
    if work.empty:
        return work
    high = work["high"].astype(float)
    low = work["low"].astype(float)
    close = work["close"].astype(float)
    open_ = work["open"].astype(float)

    prev_close = close.shift(1).fillna(close)
    tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False, min_periods=1).mean()

    up_move = high.diff().fillna(0)
    down_move = -low.diff().fillna(0)
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_di = 100 * pd.Series(plus_dm, index=work.index).ewm(alpha=1 / 14, adjust=False, min_periods=1).mean() / atr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=work.index).ewm(alpha=1 / 14, adjust=False, min_periods=1).mean() / atr.replace(0, np.nan)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100).fillna(0)
    adx = dx.ewm(alpha=1 / 14, adjust=False, min_periods=1).mean()

    ret = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0)
    body = (close - open_).abs()
    candle_range = (high - low).abs().replace(0, np.nan)
    direction = np.sign(close.diff().fillna(0))
    directional_consistency = direction.rolling(30, min_periods=1).sum().abs() / 30
    realized_move = (close - close.shift(30)).abs()
    path = close.diff().abs().rolling(30, min_periods=1).sum().replace(0, np.nan)
    dve = (realized_move / path * 100).replace([np.inf, -np.inf], np.nan).fillna(0)

    work["atr"] = atr.fillna(0)
    work["atr_pct"] = (atr / close.abs().replace(0, np.nan) * 100).fillna(0)
    work["plus_di"] = plus_di.replace([np.inf, -np.inf], np.nan).fillna(0).clip(0, 100)
    work["minus_di"] = minus_di.replace([np.inf, -np.inf], np.nan).fillna(0).clip(0, 100)
    work["pressure"] = work["plus_di"] - work["minus_di"]
    work["adx"] = adx.replace([np.inf, -np.inf], np.nan).fillna(0).clip(0, 100)
    work["adx_slope"] = work["adx"].diff().fillna(0)
    work["return_pct"] = ret * 100
    work["momentum_10_pct"] = close.pct_change(10).fillna(0) * 100
    work["momentum_30_pct"] = close.pct_change(30).fillna(0) * 100
    work["volatility_120_pct"] = ret.rolling(120, min_periods=10).std().fillna(ret.std()) * 100
    std = ret.rolling(120, min_periods=20).std().replace(0, np.nan)
    mean = ret.rolling(120, min_periods=20).mean()
    work["fat_tail_z"] = ((ret - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0)
    work["body_efficiency_pct"] = (body / candle_range * 100).replace([np.inf, -np.inf], np.nan).fillna(0).clip(0, 100)
    work["dve_pct"] = dve.clip(0, 100)
    work["rising_efficiency_pct"] = np.where(close.diff().fillna(0) > 0, work["body_efficiency_pct"], 0)
    work["falling_efficiency_pct"] = np.where(close.diff().fillna(0) < 0, work["body_efficiency_pct"], 0)
    work["directional_consistency_pct"] = (directional_consistency * 100).fillna(0).clip(0, 100)
    return work.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)


def quality_score(df: pd.DataFrame) -> Tuple[float, str]:
    if df.empty:
        return 0.0, "No usable OHLC data."
    required = ["time", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return 20.0, "Missing: " + ", ".join(missing)
    score = 100.0
    if len(df) < 120:
        score -= 25
    if df[required].isna().mean().mean() > 0.02:
        score -= 20
    if df["time"].duplicated().mean() > 0.01:
        score -= 15
    if ((df["high"] < df[["open", "close"]].max(axis=1)) | (df["low"] > df[["open", "close"]].min(axis=1))).mean() > 0.01:
        score -= 20
    score = max(0.0, min(100.0, score))
    msg = "Good shared market data." if score >= 80 else "Usable but needs caution; check rows, duplicates, and OHLC columns."
    return round(score, 2), msg


def decide_engine(df: pd.DataFrame) -> Tuple[EngineDecision, pd.DataFrame]:
    dfi = add_engine_features(df)
    q, qmsg = quality_score(dfi)
    dec = EngineDecision(
        status="ACTIVE" if not dfi.empty else "NO DATA",
        rows=int(len(dfi)),
        symbol=str(st.session_state.get("symbol", "XAUUSD")),
        source=str(st.session_state.get("source", "DISCONNECTED")),
        timeframe=str(st.session_state.get("timeframe", "M1")),
        data_quality_pct=q,
        warning=qmsg,
    )
    if dfi.empty:
        return dec, dfi

    last = dfi.iloc[-1]
    pressure = _num(last.get("pressure"))
    adx = _num(last.get("adx"))
    adx_slope = _num(last.get("adx_slope"))
    m10 = _num(last.get("momentum_10_pct"))
    m30 = _num(last.get("momentum_30_pct"))
    atr_pct = _num(last.get("atr_pct"))
    fatz = _num(last.get("fat_tail_z"))
    dve = _num(last.get("dve_pct"))
    rising = _num(pd.Series(dfi["rising_efficiency_pct"]).tail(30).mean())
    falling = _num(pd.Series(dfi["falling_efficiency_pct"]).tail(30).mean())

    raw = 0.0
    raw += min(35, abs(pressure) * 1.15)
    raw += min(30, adx * 0.9)
    raw += min(15, abs(m10) * 5)
    raw += min(10, max(0, adx_slope) * 8)
    raw += min(10, dve * 0.16)
    if abs(fatz) > 2.5:
        raw -= 12
    if q < 70:
        raw *= 0.72
    confidence = round(max(0.0, min(100.0, raw)), 2)

    if adx < 13 or abs(pressure) < 4 or confidence < 38:
        bias = "WAIT"
    elif pressure > 0 and m10 >= -0.03:
        bias = "BUY"
    elif pressure < 0 and m10 <= 0.03:
        bias = "SELL"
    else:
        bias = "WAIT"

    if adx >= 25 and dve >= 45 and abs(pressure) >= 12:
        regime = "TRENDING"
    elif abs(fatz) >= 2.5 or atr_pct > dfi["atr_pct"].tail(300).quantile(0.9):
        regime = "FAT-TAIL / VOLATILE"
    elif adx < 13:
        regime = "RANGE / WEAK"
    else:
        regime = "MIXED"

    # Full-side exit guards for hedged account thinking.
    # Exit BUY means remaining SELL-only exposure; only consider when SELL pressure is strong and stable.
    exit_buy_guard = "ALLOW WATCH" if bias == "SELL" and confidence >= 62 and falling > rising + 8 else "BLOCK"
    exit_sell_guard = "ALLOW WATCH" if bias == "BUY" and confidence >= 62 and rising > falling + 8 else "BLOCK"
    if regime == "FAT-TAIL / VOLATILE":
        exit_buy_guard = "BLOCK unless paired reduction"
        exit_sell_guard = "BLOCK unless paired reduction"

    dec.last_time = str(last.get("time", "-"))
    dec.last_close = round(_num(last.get("close")), 5)
    dec.bias = bias
    dec.confidence_pct = confidence
    dec.scale10 = round(confidence / 10, 2)
    dec.adx = round(adx, 2)
    dec.plus_di = round(_num(last.get("plus_di")), 2)
    dec.minus_di = round(_num(last.get("minus_di")), 2)
    dec.pressure = round(pressure, 2)
    dec.atr = round(_num(last.get("atr")), 5)
    dec.atr_pct = round(atr_pct, 5)
    dec.momentum_10_pct = round(m10, 5)
    dec.momentum_30_pct = round(m30, 5)
    dec.volatility_120_pct = round(_num(last.get("volatility_120_pct")), 5)
    dec.fat_tail_z = round(fatz, 3)
    dec.dve_pct = round(dve, 2)
    dec.rising_efficiency_pct = round(rising, 2)
    dec.falling_efficiency_pct = round(falling, 2)
    dec.regime = regime
    dec.exit_buy_guard = exit_buy_guard
    dec.exit_sell_guard = exit_sell_guard
    dec.warning = qmsg if bias != "WAIT" else qmsg + " Engine says WAIT unless account-risk panel confirms staged/paired reduction."
    return dec, dfi


def _save_snapshot(dec: EngineDecision) -> None:
    row = asdict(dec)
    row["saved_at"] = str(pd.Timestamp.now())
    history = st.session_state.setdefault("engine_pro_history", [])
    history.append(row)
    st.session_state["engine_pro_history"] = history[-300:]
    if append_csv is not None:
        try:
            append_csv("engine_pro_snapshots", row)
        except Exception:
            pass


def export_text(dec: EngineDecision, dfi: pd.DataFrame) -> str:
    tail_cols = [c for c in ["time", "open", "high", "low", "close", "volume", "adx", "plus_di", "minus_di", "pressure", "atr_pct", "momentum_10_pct", "fat_tail_z", "dve_pct"] if c in dfi.columns]
    payload = {
        "export_time": str(pd.Timestamp.now()),
        "engine_decision": asdict(dec),
        "risk_rule": "For hedged baskets, full BUY exit or full SELL exit is blocked unless the opposite directional pressure is strong, stable, and account margin can survive remaining one-way exposure.",
        "thresholds": {
            "weak_or_wait": "ADX < 13, pressure abs < 4, or confidence < 38",
            "serious_watch": "confidence >= 62 and DVE/DI agree",
            "fat_tail_block": "absolute fat_tail_z >= 2.5 blocks full-side exit unless paired reduction",
        },
        "latest_rows": dfi[tail_cols].tail(80).to_dict(orient="records") if not dfi.empty else [],
    }
    return "ENGINE PRO EXPORT FOR GPT\n" + "=" * 34 + "\n" + json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def render_engine_pro_panel() -> None:
    st.markdown("### 🧠 Engine Pro Decision Matrix")
    st.caption("Non-destructive upgrade: reads the same shared dataframe, adds stronger DI/ADX/ATR/volatility/fat-tail/DVE checks, and keeps your original Engine below.")
    df = st.session_state.get("last_df")
    dec, dfi = decide_engine(df)

    c = st.columns(8)
    c[0].metric("Status", dec.status)
    c[1].metric("Rows", f"{dec.rows:,}")
    c[2].metric("Bias", dec.bias)
    c[3].metric("Trust %", dec.confidence_pct)
    c[4].metric("ADX", dec.adx)
    c[5].metric("Pressure", dec.pressure)
    c[6].metric("DVE %", dec.dve_pct)
    c[7].metric("Quality %", dec.data_quality_pct)

    c2 = st.columns(6)
    c2[0].metric("+DI", dec.plus_di)
    c2[1].metric("-DI", dec.minus_di)
    c2[2].metric("ATR %", dec.atr_pct)
    c2[3].metric("M10 %", dec.momentum_10_pct)
    c2[4].metric("Fat-tail Z", dec.fat_tail_z)
    c2[5].metric("Regime", dec.regime)

    g1, g2 = st.columns(2)
    g1.warning(f"Exit BUY guard: **{dec.exit_buy_guard}**")
    g2.warning(f"Exit SELL guard: **{dec.exit_sell_guard}**")

    if dec.status == "ACTIVE" and dec.bias != "WAIT" and dec.confidence_pct >= 62:
        st.success(dec.warning)
    elif dec.status == "ACTIVE":
        st.info(dec.warning)
    else:
        st.warning(dec.warning)

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("💾 Save Engine snapshot", use_container_width=True, key="engine_pro_save_snapshot"):
            _save_snapshot(dec)
            st.success("Engine snapshot saved.")
    with b2:
        if st.button("📋 Build Pro GPT export", use_container_width=True, key="engine_pro_build_export"):
            st.session_state["engine_pro_export_text"] = export_text(dec, dfi)
            st.session_state["engine_pro_export_at"] = str(pd.Timestamp.now())
    with b3:
        if st.button("🧹 Clear Pro export", use_container_width=True, key="engine_pro_clear_export"):
            st.session_state.pop("engine_pro_export_text", None)
            st.session_state.pop("engine_pro_export_at", None)

    txt = st.session_state.get("engine_pro_export_text", "")
    if txt:
        st.caption("Built at: " + str(st.session_state.get("engine_pro_export_at", "")))
        st.text_area("Copy Engine Pro data", value=txt, height=300, key="engine_pro_export_area")
        st.download_button("⬇️ Download Engine Pro export", txt.encode("utf-8"), "engine_pro_export.txt", "text/plain", use_container_width=True, key="engine_pro_download_export")

    with st.expander("📈 Engine Pro chart + latest feature table", expanded=False):
        if dfi.empty:
            st.info("No usable data loaded yet.")
        else:
            st.line_chart(dfi.set_index("time")[["close"]].tail(240), use_container_width=True)
            show_cols = [c for c in ["time", "open", "high", "low", "close", "adx", "plus_di", "minus_di", "pressure", "atr_pct", "momentum_10_pct", "fat_tail_z", "dve_pct"] if c in dfi.columns]
            st.dataframe(dfi[show_cols].tail(150), use_container_width=True, hide_index=True)

    hist = st.session_state.get("engine_pro_history", [])
    if hist:
        with st.expander("🧾 Current-session Engine snapshot history", expanded=False):
            st.dataframe(pd.DataFrame(hist).tail(80), use_container_width=True, hide_index=True)
