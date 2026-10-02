"""Non-destructive code-quality and efficiency helpers.

This module is intentionally additive. It centralizes lightweight cleanup that all
existing tabs can use without changing their original UI or trading logic.
"""
from __future__ import annotations

import gc
import importlib
import time
from typing import Any, Dict, Iterable, List

import pandas as pd
import streamlit as st

REQUIRED_MARKET_COLUMNS = ["time", "open", "high", "low", "close"]
MAX_SESSION_LIST_ITEMS = 1000


def _now_text() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_market_frame(df: Any, max_rows: int | None = None) -> pd.DataFrame:
    """Return a clean OHLC dataframe without mutating the caller's object.

    Keeps original columns when possible, but guarantees ordered unique time rows,
    numeric OHLCV, no infinite values, and compact dtypes for faster tab work.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    rename = {"datetime": "time", "timestamp": "time", "date": "time", "tick_volume": "volume", "real_volume": "volume"}
    for old, new in rename.items():
        if old in out.columns and new not in out.columns:
            out = out.rename(columns={old: new})

    if "time" not in out.columns:
        return pd.DataFrame()
    out["time"] = pd.to_datetime(out["time"], errors="coerce")

    for col in ["open", "high", "low", "close", "volume"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    missing = [c for c in REQUIRED_MARKET_COLUMNS if c not in out.columns]
    if missing:
        return pd.DataFrame()

    out = out.replace([float("inf"), float("-inf")], pd.NA)
    out = out.dropna(subset=REQUIRED_MARKET_COLUMNS)
    out = out.sort_values("time").drop_duplicates("time", keep="last")
    if "volume" not in out.columns:
        out["volume"] = 0
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0)

    if max_rows:
        try:
            out = out.tail(int(max_rows))
        except Exception:
            pass

    # Compact numeric dtypes reduce Streamlit memory pressure on large M1/M2 data.
    for col in ["open", "high", "low", "close", "volume"]:
        try:
            out[col] = pd.to_numeric(out[col], errors="coerce", downcast="float")
        except Exception:
            pass

    return out.reset_index(drop=True)


def dataframe_quality(df: Any) -> Dict[str, Any]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return {"status": "NO_DATA", "score": 0, "rows": 0, "issues": ["No shared market dataframe loaded."]}

    issues: List[str] = []
    rows_before = len(df)
    cols = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED_MARKET_COLUMNS if c not in cols]
    if missing:
        issues.append("Missing columns: " + ", ".join(missing))

    clean = normalize_market_frame(df)
    if clean.empty:
        issues.append("Dataframe cannot be normalized into valid OHLC candles.")
    else:
        dropped = rows_before - len(clean)
        if dropped > 0:
            issues.append(f"Cleaned/dropped invalid or duplicate rows: {dropped}")
        if len(clean) < 100:
            issues.append("Low candle count; analysis confidence is weaker.")
        if "time" in clean.columns and len(clean) > 5:
            deltas = clean["time"].diff().dropna().dt.total_seconds()
            if not deltas.empty:
                med = float(deltas.median() or 0)
                mx = float(deltas.max() or 0)
                if med > 0 and mx > med * 8:
                    issues.append(f"Large time gap detected: max {int(mx)}s vs median {int(med)}s")

    score = 100
    score -= 35 if missing else 0
    score -= min(45, len(issues) * 12)
    score = max(0, min(100, int(score)))
    status = "GOOD" if score >= 80 else "CHECK" if score >= 55 else "WEAK"
    return {"status": status, "score": score, "rows": int(len(clean)) if not clean.empty else 0, "issues": issues or ["No critical issue detected."]}


def optimize_session_market_data(max_rows: int | None = None) -> Dict[str, Any]:
    """Normalize st.session_state.last_df in-place only when it is safe to do so."""
    df = st.session_state.get("last_df")
    before_rows = len(df) if isinstance(df, pd.DataFrame) else 0
    clean = normalize_market_frame(df, max_rows=max_rows)
    report = dataframe_quality(clean if not clean.empty else df)
    if not clean.empty:
        st.session_state.last_df = clean
        after_rows = len(clean)
        if after_rows != before_rows:
            st.session_state["last_connection_rows"] = after_rows
            st.session_state["data_version"] = int(st.session_state.get("data_version", 0) or 0) + 1
            st.session_state["data_version_source"] = "quality_optimizer"
    st.session_state["last_code_quality_report"] = report
    return report


def trim_session_lists(keys: Iterable[str] | None = None, max_items: int = MAX_SESSION_LIST_ITEMS) -> None:
    keys = list(keys or ["activity_log", "system_events", "notes", "trade_history", "training_rows"])
    for key in keys:
        try:
            value = st.session_state.get(key)
            if isinstance(value, list) and len(value) > max_items:
                st.session_state[key] = value[:max_items]
        except Exception:
            pass


def run_light_maintenance() -> Dict[str, Any]:
    """Small per-rerun maintenance with throttle so navigation remains fast."""
    now = time.time()
    last = float(st.session_state.get("last_light_maintenance_ts", 0.0) or 0.0)
    if now - last < 20:
        return st.session_state.get("last_code_quality_report", {}) or {}
    st.session_state["last_light_maintenance_ts"] = now
    trim_session_lists()
    report = dataframe_quality(st.session_state.get("last_df"))
    st.session_state["last_code_quality_report"] = report
    try:
        gc.collect()
    except Exception:
        pass
    return report


def audit_core_imports() -> Dict[str, Any]:
    """Fast import audit for important modules. Returns data, never raises."""
    modules = [
        "core.app_shell", "core.app.runner", "core.navigation", "core.data_connectors",
        "core.database", "core.quant_models", "tabs.home", "tabs.engine", "tabs.train_data",
        "tabs.pre_original", "tabs.profile",
    ]
    results = []
    ok_count = 0
    for name in modules:
        try:
            importlib.import_module(name)
            results.append({"module": name, "status": "OK", "error": ""})
            ok_count += 1
        except Exception as exc:
            results.append({"module": name, "status": "FAIL", "error": str(exc)[:250]})
    return {"checked_at": _now_text(), "ok": ok_count == len(modules), "passed": ok_count, "total": len(modules), "results": results}


def render_code_quality_panel(location: str = "sidebar") -> None:
    """Optional UI panel; safe to show in any tab/expander."""
    report = st.session_state.get("last_code_quality_report") or dataframe_quality(st.session_state.get("last_df"))
    st.markdown("#### 🧪 Code/Data Quality")
    c1, c2, c3 = st.columns(3)
    c1.metric("Data status", report.get("status", "NO_DATA"))
    c2.metric("Quality score", f"{int(report.get('score', 0) or 0)}/100")
    c3.metric("Rows", f"{int(report.get('rows', 0) or 0):,}")
    with st.expander("Quality issues / checks", expanded=False):
        for issue in report.get("issues", [])[:8]:
            st.caption(f"• {issue}")
        if st.button("Run import self-check", key=f"import_self_check_{location}"):
            audit = audit_core_imports()
            st.write(f"Passed {audit['passed']}/{audit['total']} module imports")
            st.dataframe(pd.DataFrame(audit["results"]), use_container_width=True, hide_index=True)
