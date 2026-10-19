"""Pro quality upgrade layer for UI/UX, connectors, database, math, and ML.

This file is additive and safe: it never removes original functions.  It only
normalizes shared session state, exposes reusable diagnostics, and gives all tabs
one consistent contract for data quality and model readiness.
"""
from __future__ import annotations
from core.global_symbol_compat import set_legacy_calculation_symbol

import time
from typing import Any, Dict, Iterable, List

import numpy as np
import pandas as pd
import streamlit as st

OHLC_REQUIRED = ["open", "high", "low", "close"]


def _now_text() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        out = float(v)
        if not np.isfinite(out):
            return float(default)
        return out
    except Exception:
        return float(default)


def normalize_tab_name(tab: Any, tabs: Iterable[str]) -> str:
    tabs = list(tabs or [])
    wanted = str(tab or "").strip()
    if wanted in tabs:
        return wanted
    lowered = {str(t).lower(): str(t) for t in tabs}
    return lowered.get(wanted.lower(), tabs[0] if tabs else "Home")


def normalize_shared_dataframe(df: Any, max_rows: int = 250_000) -> pd.DataFrame:
    """Return a clean OHLCV dataframe without mutating the caller's object."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out = out.rename(columns={c: str(c).strip().lower() for c in out.columns})
    aliases = {"datetime": "time", "date": "time", "timestamp": "time", "tick_volume": "volume"}
    for old, new in aliases.items():
        if old in out.columns and new not in out.columns:
            out = out.rename(columns={old: new})
    if "time" in out.columns:
        out["time"] = pd.to_datetime(out["time"], errors="coerce")
        out = out.dropna(subset=["time"]).sort_values("time").drop_duplicates("time", keep="last")
    for col in ["open", "high", "low", "close", "volume"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    present = [c for c in OHLC_REQUIRED if c in out.columns]
    if len(present) == len(OHLC_REQUIRED):
        out = out.dropna(subset=OHLC_REQUIRED)
        out = out[(out["high"] >= out[["open", "close", "low"]].max(axis=1)) & (out["low"] <= out[["open", "close", "high"]].min(axis=1))]
    if "volume" not in out.columns:
        out["volume"] = 0
    out = out.replace([np.inf, -np.inf], np.nan)
    if max_rows and len(out) > int(max_rows):
        out = out.tail(int(max_rows))
    keep = [c for c in ["time", "open", "high", "low", "close", "volume"] if c in out.columns]
    return out[keep].reset_index(drop=True) if keep else pd.DataFrame()


def dataframe_quality_report(df: Any) -> Dict[str, Any]:
    clean = normalize_shared_dataframe(df)
    raw_rows = len(df) if isinstance(df, pd.DataFrame) else 0
    rows = len(clean)
    missing = [c for c in ["time"] + OHLC_REQUIRED if c not in clean.columns]
    score = 100.0
    if raw_rows <= 0:
        score = 0.0
    else:
        score -= max(0, raw_rows - rows) / max(raw_rows, 1) * 45.0
        score -= len(missing) * 12.0
        if rows < 120:
            score -= 20.0
        if rows >= 2 and "time" in clean.columns:
            gaps = clean["time"].diff().dropna()
            if not gaps.empty:
                med = gaps.median()
                if med and (gaps > med * 5).sum() > max(2, rows * 0.02):
                    score -= 12.0
    score = max(0.0, min(100.0, score))
    return {
        "score": round(score, 2),
        "raw_rows": raw_rows,
        "clean_rows": rows,
        "missing": missing,
        "ready": rows >= 120 and not missing,
        "last_time": str(clean["time"].iloc[-1]) if rows and "time" in clean.columns else "",
    }


def _market_regime(clean: pd.DataFrame) -> Dict[str, Any]:
    if clean.empty or len(clean) < 30:
        return {"regime": "WAIT", "volatility_pct": 0.0, "directional_efficiency": 0.0, "logic_score": 0.0}
    close = clean["close"].astype(float)
    ret = close.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    volatility = _safe_float(ret.tail(60).std() * 100.0, 0.0)
    net = abs(close.iloc[-1] - close.iloc[max(0, len(close) - 60)])
    path = close.diff().abs().tail(60).sum()
    eff = _safe_float((net / path) * 100.0 if path else 0.0, 0.0)
    slope = _safe_float((close.iloc[-1] - close.iloc[max(0, len(close) - 30)]) / max(close.iloc[-1], 1e-9) * 100.0, 0.0)
    if eff >= 55 and slope > 0:
        regime = "BUY_TREND_CONTROL"
    elif eff >= 55 and slope < 0:
        regime = "SELL_TREND_CONTROL"
    elif volatility > 0.18:
        regime = "HIGH_VOLATILITY_MIXED"
    else:
        regime = "RANGE_OR_WAIT"
    logic_score = max(0.0, min(100.0, 50.0 + eff * 0.35 - volatility * 40.0))
    return {"regime": regime, "volatility_pct": round(volatility, 4), "directional_efficiency": round(eff, 2), "logic_score": round(logic_score, 2)}


def ml_readiness_report(df: Any) -> Dict[str, Any]:
    clean = normalize_shared_dataframe(df)
    q = dataframe_quality_report(clean)
    rows = q["clean_rows"]
    if rows < 300:
        status = "NOT_ENOUGH_DATA"
        readiness = min(45.0, rows / 300.0 * 45.0)
    elif rows < 1000:
        status = "BASIC_TRAINING_READY"
        readiness = 60.0 + min(20.0, (rows - 300) / 700.0 * 20.0)
    else:
        status = "ROBUST_TRAINING_READY"
        readiness = 82.0 + min(18.0, (rows - 1000) / 4000.0 * 18.0)
    regime = _market_regime(clean)
    return {**q, **regime, "ml_status": status, "ml_readiness": round(readiness, 2)}


def repair_session_contract() -> Dict[str, Any]:
    """Make cross-tab state coherent before the active tab renders."""
    from core.common import DEFAULT_TABS

    st.session_state["tab_choice"] = normalize_tab_name(st.session_state.get("tab_choice", "Home"), DEFAULT_TABS)
    set_legacy_calculation_symbol(st.session_state, st.session_state.get("symbol") or "", connector=True)
    st.session_state["timeframe"] = str(st.session_state.get("timeframe", "M1") or "M1").strip().upper()

    df = st.session_state.get("last_df")
    clean = normalize_shared_dataframe(df)
    if isinstance(df, pd.DataFrame) and not clean.empty and len(clean) != len(df):
        st.session_state["last_df"] = clean
    report = ml_readiness_report(clean)
    st.session_state["pro_quality_report"] = report
    st.session_state["connected"] = bool(st.session_state.get("connected", False)) and report["clean_rows"] > 0
    st.session_state.setdefault("pro_quality_events", [])
    return report


def persist_quality_event(tab_name: str, report: Dict[str, Any]) -> None:
    try:
        last = float(st.session_state.get("last_quality_persist_ts", 0) or 0)
        if time.time() - last < 120:
            return
        from core.database import append_csv
        row = {"saved_at": _now_text(), "tab": tab_name, **dict(report or {})}
        append_csv("pro_quality_events", row)
        st.session_state["last_quality_persist_ts"] = time.time()
    except Exception:
        pass


def render_quality_hud(tab_name: str) -> None:
    report = st.session_state.get("pro_quality_report") or repair_session_contract()
    persist_quality_event(tab_name, report)
    score = _safe_float(report.get("score"), 0.0)
    ready = bool(report.get("ready"))
    badge = "✅ READY" if ready else "⚠️ NEED DATA"
    st.markdown(
        f"""
        <div class="pro-quality-hud">
          <div><b>Quality Contract</b> <span>{badge}</span></div>
          <div class="pro-quality-grid">
            <span>Data score <b>{score:.0f}/100</b></span>
            <span>Rows <b>{int(report.get('clean_rows', 0)):,}</b></span>
            <span>Regime <b>{report.get('regime', 'WAIT')}</b></span>
            <span>ML <b>{report.get('ml_status', 'WAIT')}</b></span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
