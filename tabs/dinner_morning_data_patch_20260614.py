"""Dinner/Morning display reorganization patch (2026-06-14).

Display-only, non-destructive final wrapper:
- Regime inner tab label becomes Dinner.
- Doo Prime inner tab label becomes Morning.
- Master Decision + Reliability + Priority Center and Final Synced Intelligence
  are displayed inside Dinner under run-gated inner tabs.
- AI Assistant is rendered inside Dinner with a ChatGPT-like local-only layout.
- Data Analysis gets a current descriptive/predictive/prescriptive result table.
- Lunch gets a red prediction-line warning/display layer using existing cached
  projection and actual/error metrics only.

No new prediction engine, no external API, no heavy neural network.
"""
from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

UNIQUE = "20260614_dinner_morning_data_final"


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        if isinstance(v, str):
            m = re.search(r"-?\d+(?:\.\d+)?", v.replace(",", "").replace("%", ""))
            v = m.group(0) if m else default
        x = float(v)
        return x if math.isfinite(x) else float(default)
    except Exception:
        return float(default)


def _clip(v: Any, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, _num(v, lo))))


def _fmt(v: Any, suffix: str = "") -> str:
    try:
        x = float(v)
        if not math.isfinite(x):
            return str(v)
        if suffix == "%":
            return f"{x:.1f}%"
        if abs(x) >= 100:
            return f"{x:.0f}{suffix}"
        return f"{x:.2f}{suffix}"
    except Exception:
        return str(v)


def _fmt_time(v: Any, default: str = "Not recorded") -> str:
    try:
        if v is None or pd.isna(v):
            return default
        return pd.Timestamp(v).strftime("%Y-%m-%d %H:%M")
    except Exception:
        text = str(v or "").strip()
        return text or default


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def _safe_json(obj: Any, rows: int = 120) -> str:
    def conv(x: Any) -> Any:
        if isinstance(x, pd.DataFrame):
            return x.head(rows).to_dict("records")
        if isinstance(x, pd.Series):
            return x.head(rows).to_dict()
        if isinstance(x, (pd.Timestamp, np.datetime64)):
            return str(x)
        if isinstance(x, dict):
            return {str(k): conv(v) for k, v in x.items() if not str(k).startswith("_")}
        if isinstance(x, (list, tuple)):
            return [conv(v) for v in list(x)[:rows]]
        if isinstance(x, (np.integer,)):
            return int(x)
        if isinstance(x, (np.floating,)):
            y = float(x)
            return y if math.isfinite(y) else None
        return x
    return json.dumps(conv(obj), indent=2, ensure_ascii=False, default=str)


def _copy_button(label: str, text: str, key: str) -> None:
    try:
        from streamlit_copy_button import copy_button
        copy_button(str(text), label, key=key)
    except Exception:
        try:
            from core.pro_terminal_uiux import render_mobile_copy_button
            render_mobile_copy_button(label, str(text), key)
        except Exception:
            st.text_area(label, str(text), height=180, key=key + "_fallback")


def _find_col(df: pd.DataFrame, aliases: Iterable[str]) -> Optional[str]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    nmap = {_norm(c): c for c in df.columns}
    for a in aliases:
        na = _norm(a)
        if na in nmap:
            return nmap[na]
    for nk, col in nmap.items():
        for a in aliases:
            na = _norm(a)
            if na and na in nk:
                return col
    return None


def _market_df(limit: int = 7000) -> pd.DataFrame:
    for key in ["dv_pp_df", "last_df", "lunch_visual_df", "home_df", "custom_h1_df", "full_metric_history_df"]:
        obj = st.session_state.get(key)
        if isinstance(obj, pd.DataFrame) and not obj.empty:
            d = obj.copy().tail(int(limit)).reset_index(drop=True)
            break
    else:
        return pd.DataFrame()
    low = {_norm(c): c for c in d.columns}
    ren = {}
    for src, dst in {"datetime": "time", "timestamp": "time", "date": "time", "o": "open", "h": "high", "l": "low", "c": "close"}.items():
        if src in low and dst not in d.columns:
            ren[low[src]] = dst
    if ren:
        d = d.rename(columns=ren)
    if "time" not in d.columns:
        # Operational analysis must not manufacture H1 timestamps. A not-ready
        # result is safer than a synthetic row that could become a decision.
        return pd.DataFrame()
    d["time"] = pd.to_datetime(d["time"], errors="coerce")
    for col in ["open", "high", "low", "close"]:
        if col not in d.columns:
            d[col] = d.get("close", np.nan)
        d[col] = pd.to_numeric(d[col], errors="coerce")
    return d.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)


def _direction_from_regime(regime: Any) -> str:
    s = str(regime or "").upper()
    if "BULL" in s or s == "BUY":
        return "BUY"
    if "BEAR" in s or s == "SELL":
        return "SELL"
    return "WAIT"


def _regime_score(regime: Any) -> float:
    s = str(regime or "").upper()
    if "BULL" in s or s == "BUY":
        return 1.0
    if "BEAR" in s or s == "SELL":
        return -1.0
    if "COMPRESSION" in s:
        return 0.25
    return 0.0


def _ctx(ns: dict, force: bool = False) -> Dict[str, Any]:
    builder = ns.get("build_reliability_control_center_20260614")
    if callable(builder) and (force or bool(st.session_state.get("metric_run_calculate", False))):
        try:
            return builder(force=force) or {}
        except TypeError:
            try:
                return builder(force) or {}
            except Exception:
                pass
        except Exception:
            pass
    obj = st.session_state.get("reliability_control_center_20260614")
    return obj if isinstance(obj, dict) else {}


def _rctx(ns: dict, force: bool = False) -> Dict[str, Any]:
    builder = ns.get("build_regime_context_20260614")
    if callable(builder) and (force or bool(st.session_state.get("metric_run_calculate", False)) or isinstance(st.session_state.get("regime_context_20260614"), dict)):
        try:
            return builder(force=force) or {}
        except TypeError:
            try:
                return builder(force) or {}
            except Exception:
                pass
        except Exception:
            pass
    obj = st.session_state.get("regime_context_20260614")
    return obj if isinstance(obj, dict) else {}


def _regime_metrics(ns: dict) -> Dict[str, Any]:
    r = _rctx(ns, False)
    m = r.get("metrics", {}) if isinstance(r, dict) else {}
    return m if isinstance(m, dict) else {}


def _priority_table_from_state(ctx: Dict[str, Any]) -> pd.DataFrame:
    # Every priority display is a subset of the one Full Metric-ranked table.
    canonical = st.session_state.get("canonical_priority_table_20260617")
    if isinstance(canonical, pd.DataFrame) and not canonical.empty:
        return canonical
    for key in ["three_center_priority_sorted_20260614", "reliability_dynamic_priority_table_20260614"]:
        obj = st.session_state.get(key)
        if isinstance(obj, pd.DataFrame) and not obj.empty:
            return obj.copy()
    if isinstance(ctx, dict):
        rec = ctx.get("priority_table_preview", [])
        if rec:
            try:
                return pd.DataFrame(rec)
            except Exception:
                pass
    pack = st.session_state.get("final_synced_research_merge_pack_20260612") or st.session_state.get("final_merged_intelligence_pack_20260612")
    if isinstance(pack, dict):
        obj = pack.get("priority_1_to_14")
        if not isinstance(obj, pd.DataFrame) or obj.empty:
            obj = pack.get("knn_greedy_priority")
        if isinstance(obj, pd.DataFrame) and not obj.empty:
            return obj.copy()
    return pd.DataFrame()


def _analysis_result_dataframe(ns: Optional[dict] = None) -> pd.DataFrame:
    ns = ns or {}
    d = _market_df(3000)
    ctx = _ctx(ns, False) if ns else {}
    rctx = _rctx(ns, False) if ns else {}
    m = rctx.get("metrics", {}) if isinstance(rctx, dict) else {}
    summary = ctx.get("summary", {}) if isinstance(ctx, dict) else {}
    quality = ctx.get("data_quality_market_feed_health", {}) if isinstance(ctx, dict) else {}
    fresh = ctx.get("model_decay_forecast_freshness", {}) if isinstance(ctx, dict) else {}
    pack = st.session_state.get("final_synced_research_merge_pack_20260612") or st.session_state.get("final_merged_intelligence_pack_20260612")
    pred_dir = "WAIT"
    pred_conf = fresh.get("Prediction Freshness", fresh.get("Decayed Confidence Score", 0)) if isinstance(fresh, dict) else 0
    if isinstance(pack, dict) and pack:
        pred_dir = str(pack.get("master_direction", pack.get("prediction_direction", pred_dir)))
        pred_conf = pack.get("projection_confidence", pred_conf)
    if pred_dir == "WAIT":
        pred = st.session_state.get("dv_pp_predicted", pd.DataFrame())
        if isinstance(pred, pd.DataFrame) and not pred.empty and not d.empty:
            ccol = _find_col(pred, ["Accuracy Adjusted Price", "Predicted Close", "Projected Close", "close"])
            if ccol:
                y = pd.to_numeric(pred[ccol], errors="coerce").dropna()
                if not y.empty:
                    last_close = float(d["close"].iloc[-1])
                    pred_dir = "BUY" if float(y.iloc[-1]) > last_close else "SELL" if float(y.iloc[-1]) < last_close else "WAIT"
    regime = m.get("Current Regime", st.session_state.get("current_regime", "-"))
    regime_dir = m.get("Regime Direction", _direction_from_regime(regime))
    reliability = _num(m.get("Regime Reliable Score", summary.get("Forecast Robustness Score", 0)), 0)
    shift = _num(m.get("Transition Risk %", 0), 0)
    data_score = _num(quality.get("Data Quality Score", 0), 0) if isinstance(quality, dict) else 0
    last_close = round(float(d["close"].iloc[-1]), 5) if not d.empty else "-"
    rows = [
        {
            "Analysis Type": "Descriptive Analysis",
            "Current Market/System Status": f"Last close {last_close}; current regime {regime}; data quality {_fmt(data_score, '%')}",
            "System Reading": f"Regime direction {regime_dir}; shift risk {_fmt(shift, '%')}",
            "Reliability / Score": _fmt(reliability, "%"),
            "Action Use": "Read market condition only; do not enter from descriptive data alone.",
        },
        {
            "Analysis Type": "Predictive Analysis",
            "Current Market/System Status": f"Existing forecast direction {pred_dir}; regime forecast {m.get('Regime Forecast', '-')}",
            "System Reading": str(m.get("Regime Prediction", f"{pred_dir} prediction vs {regime_dir} regime")),
            "Reliability / Score": _fmt(pred_conf if _num(pred_conf, 0) else reliability, "%"),
            "Action Use": "Use existing forecast/error metrics only; confirm with priority and risk before action.",
        },
        {
            "Analysis Type": "Prescriptive Analysis",
            "Current Market/System Status": "Decision rule combines regime, priority, reliability, exit risk, and shift risk.",
            "System Reading": "FOLLOW bias" if reliability >= 70 and shift < 50 and regime_dir in {"BUY", "SELL"} else "WAIT / reduce size / avoid" if reliability < 60 or shift >= 55 else "Small size only after confirmation",
            "Reliability / Score": _fmt(max(0.0, min(100.0, reliability - max(0.0, shift - 45) * 0.6)), "%"),
            "Action Use": "Prescriptive result for current system status; it does not replace your original calculations.",
        },
    ]
    return pd.DataFrame(rows)


def render_data_analysis_result_table_20260614(source: str = "research") -> None:
    """Public helper imported by Research/Data Analysis renderers."""
    with st.expander("📊 Open / Close — Current Result Table: Descriptive + Predictive + Prescriptive + Diagnostic", expanded=True):
        st.caption("Uses current existing session data only. No API, no new model, no duplicate heavy calculation.")
        st.dataframe(_analysis_result_dataframe({}), use_container_width=True, hide_index=True, height=190)
        try:
            from core.advanced_analytics_20260615 import build_diagnostic_analysis_table, build_sampling_estimating_hypothesis_tables, build_data_mining_extension_tables
            st.markdown("##### Diagnostic Analysis")
            st.dataframe(build_diagnostic_analysis_table(), use_container_width=True, hide_index=True, height=260)
            stats = build_sampling_estimating_hypothesis_tables()
            cube = build_data_mining_extension_tables().get("cube")
            st.markdown("##### Sampling / Estimating / Hypothesis Testing / 3D Data Cube")
            sub = st.tabs(["Sampling", "Estimating", "Hypothesis", "3D Data Cube"] )
            with sub[0]:
                st.dataframe(stats.get("sampling"), use_container_width=True, hide_index=True, height=220)
            with sub[1]:
                st.dataframe(stats.get("estimating"), use_container_width=True, hide_index=True, height=200)
            with sub[2]:
                st.dataframe(stats.get("hypothesis"), use_container_width=True, hide_index=True, height=220)
            with sub[3]:
                st.dataframe(cube, use_container_width=True, hide_index=True, height=300)
        except Exception as exc:
            st.caption(f"Diagnostic analysis skipped safely: {exc}")


def _regime_projection_source(ns: dict) -> pd.DataFrame:
    r = _rctx(ns, False)
    hist = r.get("history", pd.DataFrame()) if isinstance(r, dict) else pd.DataFrame()
    m = r.get("metrics", {}) if isinstance(r, dict) else {}
    rows: List[Dict[str, Any]] = []
    if isinstance(hist, pd.DataFrame) and not hist.empty:
        work = hist.copy().tail(48)
        tcol = _find_col(work, ["End", "End Time", "time", "Datetime", "Date", "Start"])
        rcol = _find_col(work, ["Regime", "Major Regime", "Current Regime", "H1 Regime"])
        conf_col = _find_col(work, ["Avg Confidence", "Regime Confidence", "Confidence"])
        rel_col = _find_col(work, ["Avg Reliability", "Regime Reliability", "Reliability"])
        shift_col = _find_col(work, ["Shift Risk", "Transition Risk"])
        if tcol and rcol:
            for _, row in work.iterrows():
                rows.append({
                    "time": pd.to_datetime(row.get(tcol), errors="coerce"),
                    "regime": row.get(rcol),
                    "path": _regime_score(row.get(rcol)),
                    "confidence": _clip(row.get(conf_col) if conf_col else m.get("Regime Confidence %", 55), 0, 100),
                    "reliability": _clip(row.get(rel_col) if rel_col else m.get("Regime Reliable Score", 55), 0, 100),
                    "shift_risk": _clip(row.get(shift_col) if shift_col else m.get("Transition Risk %", 45), 0, 100),
                })
    if not rows:
        d = _market_df(500)
        if not d.empty:
            c = d["close"].astype(float)
            ma12 = c.rolling(12, min_periods=3).mean()
            ma48 = c.rolling(48, min_periods=10).mean()
            reg = np.where(ma12 > ma48, "BULL_DERIVED", np.where(ma12 < ma48, "BEAR_DERIVED", "RANGE_DERIVED"))
            tail = d.tail(90).copy()
            for i, (_, row) in enumerate(tail.iterrows()):
                rr = reg[row.name] if row.name < len(reg) else "RANGE_DERIVED"
                rows.append({
                    "time": row["time"],
                    "regime": rr,
                    "path": _regime_score(rr),
                    "confidence": _clip(m.get("Regime Confidence %", 55), 0, 100),
                    "reliability": _clip(m.get("Regime Reliable Score", 55), 0, 100),
                    "shift_risk": _clip(m.get("Transition Risk %", 45), 0, 100),
                })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    out["previous_path"] = out["path"].shift(1)
    return out


def _render_powerbi_regime_projection(ns: dict) -> None:
    st.markdown("#### 📈 PowerBI Regime Projection")
    try:
        from core.regime_sync_20260617 import canonical_regime_snapshot
        _snap = canonical_regime_snapshot(days=25)
        _mc = st.columns(4)
        _mc[0].metric("Current Regime", _snap.get("regime", "-"), _snap.get("regime_validation", "FALSE / WATCH"))
        _mc[1].metric("Regime Start", _fmt_time(_snap.get("regime_start")))
        _mc[2].metric("Regime End", _snap.get("regime_end_display", "OPEN / CURRENT"))
        _err = _snap.get("avg_error_pct")
        _err_text = f"{float(_err):.5f}%" if _err is not None else "N/A"
        _err_kind = "proxy" if _snap.get("error_is_proxy") else "actual"
        _mc[3].metric("Avg Error (Proxy)" if _snap.get("error_is_proxy") else "Avg Error", _err_text, f"{int(_snap.get('error_samples',0))} samples • {_err_kind}" if _err is not None else "Run prediction-vs-actual backtest")
    except Exception:
        pass
    st.caption("Current regime path, previous regime path, expected next regime path, confidence/reliability line, and shift-risk band. Existing regime/history/forecast calculations only.")
    c1, c2 = st.columns([1.0, 2.2])
    horizon = c1.slider("Expected path H1", 6, 24, 12, 6, key=f"regime_projection_horizon_{UNIQUE}")
    c2.caption("Auto-loaded from the Settings-published generation. Display-only projection transform; no inner Run button or new prediction engine.")
    try:
        from core.advanced_analytics_20260615 import render_regime_alpha_delta_metrics
        render_regime_alpha_delta_metrics(ns, key="powerbi_regime_projection")
    except Exception as exc:
        st.caption(f"Regime Alpha/Delta skipped safely: {exc}")
    if not bool(st.session_state.get("metric_run_calculate", False)) and not isinstance(st.session_state.get("regime_context_20260614"), dict):
        try:
            from core.system_wide_completion_20260618 import readiness_message
            st.info(readiness_message(st.session_state, "Regime History"))
        except Exception:
            st.info("The published regime projection is unavailable. Open Settings → Errors / Fix Fast.")
        return
    src = _regime_projection_source(ns)
    if src.empty:
        try:
            from core.system_wide_completion_20260618 import readiness_message
            st.info(readiness_message(st.session_state, "Regime History"))
        except Exception:
            st.info("No published regime history is available. Open Settings → Errors / Fix Fast.")
        return
    m = _regime_metrics(ns)
    last_t = pd.to_datetime(src["time"].iloc[-1], errors="coerce")
    if pd.isna(last_t):
        last_t = pd.Timestamp.now().floor("h")
    forecast_dir = str(m.get("Forecast Direction", "WAIT"))
    next_regime = m.get("Regime Forecast") or m.get("Regime Prediction") or forecast_dir
    next_score = _regime_score(forecast_dir if forecast_dir in {"BUY", "SELL", "WAIT"} else next_regime)
    if next_score == 0:
        next_score = float(src["path"].iloc[-1])
    shift = _clip(m.get("Transition Risk %", src["shift_risk"].tail(1).iloc[0] if "shift_risk" in src else 45), 0, 100)
    future = pd.DataFrame({
        "time": [last_t + pd.Timedelta(hours=i) for i in range(1, int(horizon) + 1)],
        "expected_path": [next_score for _ in range(int(horizon))],
        "upper_band": [min(1.4, next_score + shift / 100.0) for _ in range(int(horizon))],
        "lower_band": [max(-1.4, next_score - shift / 100.0) for _ in range(int(horizon))],
        "confidence": [_clip(m.get("Regime Confidence %", src["confidence"].tail(1).iloc[0]), 0, 100) for _ in range(int(horizon))],
        "reliability": [_clip(m.get("Regime Reliable Score", src["reliability"].tail(1).iloc[0]), 0, 100) for _ in range(int(horizon))],
        "shift_risk": [shift for _ in range(int(horizon))],
    })
    try:
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=src["time"], y=src["path"], mode="lines+markers", name="Current regime path", line={"shape": "hv", "width": 3}))
        fig.add_trace(go.Scatter(x=src["time"], y=src["previous_path"], mode="lines", name="Previous regime path", line={"dash": "dot", "width": 2}))
        fig.add_trace(go.Scatter(x=future["time"], y=future["upper_band"], mode="lines", name="Shift-risk upper band", line={"dash": "dash"}, showlegend=True))
        fig.add_trace(go.Scatter(x=future["time"], y=future["lower_band"], mode="lines", name="Shift-risk lower band", line={"dash": "dash"}, fill="tonexty", showlegend=True))
        fig.add_trace(go.Scatter(x=future["time"], y=future["expected_path"], mode="lines+markers", name="Expected next regime path", line={"width": 4, "shape": "spline", "smoothing": 1.05}))
        fig.add_trace(go.Scatter(x=src["time"], y=src["confidence"], mode="lines", name="Confidence %", yaxis="y2"))
        fig.add_trace(go.Scatter(x=src["time"], y=src["reliability"], mode="lines", name="Reliability %", yaxis="y2"))
        try:
            from core.alpha_delta_points_20260615 import add_alpha_delta_vertical_markers
            current_path = src[["time", "path"]].rename(columns={"path": "Blue Path"})
            expected_path = future[["time", "expected_path"]].rename(columns={"expected_path": "Red Path"})
            fig = add_alpha_delta_vertical_markers(fig, current_path, expected_path, blue_label="Blue Path", red_label="Red Path", key="regime_blue_red")
        except Exception:
            pass
        fig.update_layout(
            height=520,
            margin=dict(l=4, r=4, t=42, b=4),
            xaxis_title="H1 time",
            yaxis=dict(title="Regime path", tickvals=[-1, 0, 1], ticktext=["BEAR", "RANGE", "BULL"], range=[-1.45, 1.45]),
            yaxis2=dict(title="Confidence/Reliability %", overlaying="y", side="right", range=[0, 100]),
            legend=dict(orientation="h"),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})
    except Exception as exc:
        st.warning(f"Regime projection chart could not render; table view is shown instead. {exc}")
    try:
        from core.alpha_delta_points_20260615 import render_alpha_delta_point_panel
        current_path = src[["time", "path"]].rename(columns={"path": "Blue Path"})
        expected_path = future[["time", "expected_path"]].rename(columns={"expected_path": "Red Path"})
        render_alpha_delta_point_panel(current_path, expected_path, key="regime_blue_red", title="Regime Alpha / Delta Data Point", blue_label="Blue Path", red_label="Red Path")
    except Exception as exc:
        st.caption(f"Regime alpha/delta data point skipped safely: {exc}")
    show = pd.concat([src.tail(30), future.rename(columns={"expected_path": "path"})], ignore_index=True, sort=False)
    with st.expander("Open / Close — PowerBI Regime Projection data table", expanded=False):
        st.dataframe(show, use_container_width=True, hide_index=True, height=320)


def _build_red_projection_from_lunch_data_v20260615(d: pd.DataFrame, horizon: int = 6) -> pd.DataFrame:
    """Lightweight fallback red display from currently entered Lunch OHLC data.

    It is a visual/error-adjusted path only. It uses existing OHLC momentum,
    volatility, and any cached reliability/error metrics. It does not train or
    add a heavy model and does not change the original PowerBI calculation.
    """
    if not isinstance(d, pd.DataFrame) or d.empty or "close" not in d.columns:
        return pd.DataFrame()
    x = d.copy().tail(260).reset_index(drop=True)
    if "time" not in x.columns:
        x["time"] = pd.date_range(end=pd.Timestamp.now().floor("h"), periods=len(x), freq="h")
    x["time"] = pd.to_datetime(x["time"], errors="coerce")
    for col in ["open", "high", "low", "close"]:
        if col not in x.columns:
            x[col] = x.get("close", np.nan)
        x[col] = pd.to_numeric(x[col], errors="coerce")
    x = x.dropna(subset=["time", "close"]).sort_values("time").reset_index(drop=True)
    if len(x) < 8:
        return pd.DataFrame()
    close = x["close"].astype(float)
    ret = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    mom_3 = float(ret.tail(3).mean()) if len(ret) else 0.0
    mom_12 = float(ret.tail(12).mean()) if len(ret) >= 4 else mom_3
    ema_fast = close.ewm(span=min(12, max(3, len(close)//4)), adjust=False).mean()
    ema_slow = close.ewm(span=min(48, max(6, len(close)//2)), adjust=False).mean()
    trend_gap = float((ema_fast.iloc[-1] - ema_slow.iloc[-1]) / max(abs(close.iloc[-1]), 1e-12)) if len(close) >= 6 else 0.0
    # Existing reliability/error data, if available, dampens the visual path.
    bt = st.session_state.get("dv_pp_bt_summary", {})
    err_pct = _num(bt.get("avg_abs_close_error_pct", 0) if isinstance(bt, dict) else 0, 0)
    acc_pct = _num(bt.get("direction_accuracy_pct", 0) if isinstance(bt, dict) else 0, 0)
    reliability = 55.0
    for key in ["Forecast Reliability %", "Prediction Reliability", "Reliability", "reliability"]:
        for obj in [st.session_state.get("reliability_control_center_20260614"), st.session_state.get("regime_context_20260614"), st.session_state.get("three_center_priority_summary_20260614")]:
            if isinstance(obj, dict) and key in obj:
                reliability = _clip(obj.get(key), 0, 100)
                break
    if acc_pct:
        reliability = max(0.0, min(100.0, (reliability + acc_pct) / 2.0))
    damp = max(0.25, min(1.0, reliability / 100.0)) * max(0.45, 1.0 - min(abs(err_pct), 0.25))
    raw_drift = mom_3 * 0.45 + mom_12 * 0.35 + trend_gap / 180.0
    drift = max(-0.0025, min(0.0025, raw_drift)) * damp
    try:
        diffs = x["time"].diff().dropna()
        step = diffs.median() if len(diffs) else pd.Timedelta(hours=1)
        if pd.isna(step) or step.total_seconds() <= 0:
            step = pd.Timedelta(hours=1)
    except Exception:
        step = pd.Timedelta(hours=1)
    last_time = pd.Timestamp(x["time"].iloc[-1])
    prev = float(close.iloc[-1])
    if "high" in x.columns and "low" in x.columns:
        atr = float((x["high"] - x["low"]).tail(48).median())
    else:
        atr = abs(prev) * 0.0004
    if not math.isfinite(atr) or atr <= 0:
        atr = abs(prev) * 0.0004
    rows: List[Dict[str, Any]] = []
    for i in range(1, int(max(3, min(horizon, 24))) + 1):
        wave = math.sin(i / 2.7) * (atr / max(abs(prev), 1e-12)) * 0.11 * damp
        red_close = prev * (1.0 + drift * (0.96 ** (i - 1)) + wave)
        band = atr * (1.0 + i / 10.0) * (1.15 if reliability < 55 else 0.90)
        rows.append({
            "time": last_time + step * i,
            "Accuracy Adjusted Price": round(float(red_close), 6),
            "Predicted Close": round(float(red_close), 6),
            "Upper Band": round(float(red_close + band), 6),
            "Lower Band": round(float(red_close - band), 6),
            "Reliability %": round(float(reliability), 2),
            "Source": "Lunch OHLC fallback red display",
            "Step": int(i),
        })
        prev = float(red_close)
    out = pd.DataFrame(rows)
    st.session_state["lunch_red_projection_fallback_20260615"] = out
    return out


def _yellow_projection_from_lunch_data_v20260615(d: pd.DataFrame, horizon: int = 6, anchor_offset: int = 0, mode: str = "Balanced", risk_filter: str = "Medium") -> pd.DataFrame:
    """Lightweight yellow/previous projection from existing OHLC.

    This first reuses the existing Home yellow builder when available. If that
    builder is not loaded, it falls back to the same simple momentum/ATR display
    transform used by the previous yellow section. It does not train a new model.
    """
    if not isinstance(d, pd.DataFrame) or d.empty:
        return pd.DataFrame()
    x = d.copy().sort_values("time").reset_index(drop=True)
    for col in ["open", "high", "low", "close"]:
        if col not in x.columns:
            x[col] = x.get("close", np.nan)
        x[col] = pd.to_numeric(x[col], errors="coerce")
    x["time"] = pd.to_datetime(x["time"], errors="coerce")
    x = x.dropna(subset=["time", "close"]).reset_index(drop=True)
    if len(x) < 12:
        return pd.DataFrame()
    anchor_idx = max(0, len(x) - 1 - int(max(0, anchor_offset)))
    if anchor_idx < 6:
        return pd.DataFrame()
    sub = x.iloc[: anchor_idx + 1].copy()

    # Prefer the existing yellow builder that the main PowerBI tab already uses.
    try:
        import tabs.home as home
        build = home.__dict__.get("_build_last_candle_yellow_6h_projection_v5")
        if callable(build):
            fut = build(sub, horizon=int(horizon), mode=mode, risk_filter=risk_filter)
            if isinstance(fut, pd.DataFrame) and not fut.empty:
                out = fut.copy()
                tcol = _find_col(out, ["time", "Future Time", "Datetime"])
                ycol = _find_col(out, ["Yellow Predicted Close", "Predicted Close", "Projected Close", "close"])
                ucol = _find_col(out, ["Upper Risk Band", "Upper Band", "upper"])
                lcol = _find_col(out, ["Lower Risk Band", "Lower Band", "lower"])
                if tcol and ycol:
                    res = pd.DataFrame({
                        "step": range(1, len(out) + 1),
                        "time": pd.to_datetime(out[tcol], errors="coerce"),
                        "path": pd.to_numeric(out[ycol], errors="coerce"),
                        "upper": pd.to_numeric(out[ucol], errors="coerce") if ucol else np.nan,
                        "lower": pd.to_numeric(out[lcol], errors="coerce") if lcol else np.nan,
                    }).dropna(subset=["time", "path"])
                    res["anchor_time"] = pd.Timestamp(sub["time"].iloc[-1])
                    res["anchor_price"] = float(sub["close"].iloc[-1])
                    return res.reset_index(drop=True)
    except Exception:
        pass

    close = sub["close"].astype(float).ffill()
    high = sub["high"].astype(float).ffill() if "high" in sub else close
    low = sub["low"].astype(float).ffill() if "low" in sub else close
    ret = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if mode == "Trend follow":
        base_ret = float(ret.ewm(span=6, adjust=False).mean().iloc[-1])
    elif mode == "Pullback safer":
        base_ret = float(ret.ewm(span=12, adjust=False).mean().iloc[-1]) * 0.45
    else:
        base_ret = float(ret.ewm(span=9, adjust=False).mean().iloc[-1]) * 0.75
    risk_mult = {"Low": 0.55, "Medium": 0.80, "High": 1.00}.get(str(risk_filter), 0.80)
    base_ret *= risk_mult
    atr = float((high - low).rolling(14, min_periods=4).mean().ffill().fillna((high - low).mean()).iloc[-1] or 0)
    if not math.isfinite(atr) or atr <= 0:
        atr = abs(float(close.iloc[-1])) * 0.00035
    last_time = pd.Timestamp(sub["time"].iloc[-1])
    price = float(close.iloc[-1])
    try:
        step_delta = sub["time"].diff().dropna().median()
        if pd.isna(step_delta) or step_delta.total_seconds() <= 0:
            step_delta = pd.Timedelta(hours=1)
    except Exception:
        step_delta = pd.Timedelta(hours=1)
    rows = []
    for step in range(1, int(max(1, min(horizon, 24))) + 1):
        damp = 1.0 / (1.0 + step * 0.10)
        pred = price * (1.0 + base_ret * step * damp)
        band = atr * (0.35 + step * 0.10) * risk_mult
        rows.append({
            "step": int(step),
            "time": last_time + step_delta * step,
            "path": round(float(pred), 6),
            "upper": round(float(pred + band), 6),
            "lower": round(float(pred - band), 6),
            "anchor_time": last_time,
            "anchor_price": price,
        })
    return pd.DataFrame(rows)


def _normalize_price_projection_v20260615(proj: pd.DataFrame, d: pd.DataFrame, horizon: int = 6) -> pd.DataFrame:
    if not isinstance(proj, pd.DataFrame) or proj.empty:
        return pd.DataFrame()
    tcol = _find_col(proj, ["time", "Future Time", "Datetime", "Date"])
    ccol = _find_col(proj, ["Accuracy Adjusted Price", "Predicted Close", "Projected Close", "close", "Projected Path"])
    ucol = _find_col(proj, ["Upper Band", "upper", "Predicted High", "Projection High", "Upper Risk Band"])
    lcol = _find_col(proj, ["Lower Band", "lower", "Predicted Low", "Projection Low", "Lower Risk Band"])
    if not (tcol and ccol):
        return pd.DataFrame()
    p = pd.DataFrame({
        "step": range(1, len(proj) + 1),
        "time": pd.to_datetime(proj[tcol], errors="coerce"),
        "path": pd.to_numeric(proj[ccol], errors="coerce"),
    })
    if ucol:
        p["upper"] = pd.to_numeric(proj[ucol], errors="coerce")
    else:
        p["upper"] = np.nan
    if lcol:
        p["lower"] = pd.to_numeric(proj[lcol], errors="coerce")
    else:
        p["lower"] = np.nan
    p = p.dropna(subset=["time", "path"]).sort_values("time").reset_index(drop=True).head(int(max(1, horizon)))
    if p.empty:
        return p
    try:
        atr = float((pd.to_numeric(d["high"], errors="coerce") - pd.to_numeric(d["low"], errors="coerce")).tail(48).median())
    except Exception:
        atr = 0.0
    if not math.isfinite(atr) or atr <= 0:
        atr = abs(float(p["path"].iloc[0])) * 0.00035
    for i in p.index:
        step = int(p.loc[i, "step"])
        if pd.isna(p.loc[i, "upper"]):
            p.loc[i, "upper"] = float(p.loc[i, "path"]) + atr * (0.85 + step / 10.0)
        if pd.isna(p.loc[i, "lower"]):
            p.loc[i, "lower"] = float(p.loc[i, "path"]) - atr * (0.85 + step / 10.0)
    return p


def _smooth_price_path_v20260615(p: pd.DataFrame, value_col: str = "path", out_col: str = "smooth") -> pd.DataFrame:
    if not isinstance(p, pd.DataFrame) or p.empty or "time" not in p.columns or value_col not in p.columns:
        return pd.DataFrame()
    if len(p) < 2:
        return pd.DataFrame({"time": p["time"], out_col: p[value_col]})
    rows: List[Dict[str, Any]] = []
    for i in range(len(p) - 1):
        t0, t1 = p["time"].iloc[i], p["time"].iloc[i + 1]
        y0, y1 = float(p[value_col].iloc[i]), float(p[value_col].iloc[i + 1])
        for j in range(4):
            u = j / 4.0
            s = u * u * (3 - 2 * u)
            rows.append({"time": t0 + (t1 - t0) * u, out_col: y0 + (y1 - y0) * s})
    rows.append({"time": p["time"].iloc[-1], out_col: float(p[value_col].iloc[-1])})
    return pd.DataFrame(rows)


def _regime_meta_for_red_chart_v20260615() -> Dict[str, Any]:
    try:
        from core.regime_sync_20260617 import canonical_regime_snapshot
        snap = canonical_regime_snapshot(days=25)
        return {
            "current_regime": snap.get("regime", "-"),
            "regime_start_display": _fmt_time(snap.get("regime_start")),
            "regime_end_display": snap.get("regime_end_display", "OPEN / CURRENT"),
            "avg_error_pct": snap.get("avg_error_pct"),
            "error_samples": int(snap.get("error_samples", 0) or 0),
            "error_is_proxy": bool(snap.get("error_is_proxy", False)),
            "regime_validation": snap.get("regime_validation", "FALSE / WATCH"),
            "reliability": float(snap.get("reliability", 0)),
            "direction_accuracy_pct": snap.get("direction_accuracy_pct"),
            "error_method": snap.get("error_method", ""),
        }
    except Exception:
        return {"current_regime":"-", "regime_start_display":"Not recorded", "regime_end_display":"OPEN / CURRENT", "avg_error_pct":None, "error_samples":0, "error_is_proxy":False, "regime_validation":"FALSE / WATCH", "reliability":0.0, "direction_accuracy_pct":None, "error_method":""}


def _render_lunch_red_prediction_line() -> None:
    with st.expander("🔴 Open / Close — Lunch Red Prediction Line: smoother + error-adjusted + reliability warning", expanded=True):
        st.caption("Full version: red error-adjusted path + red bands, yellow current path + yellow bands, blue dotted previous-candle predicted path, and green alpha difference line. Uses existing cached projections or current Lunch OHLC fallback only.")
        d = _market_df(420)
        if d.empty:
            st.info("Enter/connect Lunch OHLC data first. After Lunch data exists, this section builds the red/yellow/blue/green display without opening the heavy original PowerBI renderer.")
            return

        cols = st.columns([.9, .9, .9, 1.15])
        with cols[0]:
            horizon = st.slider("Path candles", 3, 12, int(st.session_state.get("lunch_red_projection_horizon_20260615", 6) or 6), 1, key="lunch_red_projection_horizon_slider_20260615")
            st.session_state["lunch_red_projection_horizon_20260615"] = int(horizon)
        with cols[1]:
            mode = st.selectbox("Yellow mode", ["Balanced", "Trend follow", "Pullback safer"], index=["Balanced", "Trend follow", "Pullback safer"].index(str(st.session_state.get("lunch_red_yellow_mode_20260615", "Balanced"))) if str(st.session_state.get("lunch_red_yellow_mode_20260615", "Balanced")) in ["Balanced", "Trend follow", "Pullback safer"] else 0, key="lunch_red_yellow_mode_20260615")
        with cols[2]:
            risk_filter = st.selectbox("Risk filter", ["Low", "Medium", "High"], index=["Low", "Medium", "High"].index(str(st.session_state.get("lunch_red_yellow_risk_20260615", "Medium"))) if str(st.session_state.get("lunch_red_yellow_risk_20260615", "Medium")) in ["Low", "Medium", "High"] else 1, key="lunch_red_yellow_risk_20260615")
        with cols[3]:
            st.metric("Data rows", len(d))

        pack = st.session_state.get("final_synced_research_merge_pack_20260612") or st.session_state.get("final_merged_intelligence_pack_20260612")
        proj = pd.DataFrame()
        if isinstance(pack, dict):
            for key in ["accuracy_adjusted_projection", "red_projection", "prediction_projection", "future_blue_predicted_candles"]:
                val = pack.get(key)
                if isinstance(val, pd.DataFrame) and not val.empty:
                    proj = val.copy()
                    break
        if proj.empty:
            pred = st.session_state.get("dv_pp_predicted", pd.DataFrame())
            if isinstance(pred, pd.DataFrame) and not pred.empty:
                proj = pred.copy()
        if proj.empty:
            proj = _build_red_projection_from_lunch_data_v20260615(d, horizon=int(horizon))
            if isinstance(proj, pd.DataFrame) and not proj.empty:
                st.success("Showing red prediction line from current Lunch data. Original synced PowerBI can overwrite it after you run the original projection.")
        red = _normalize_price_projection_v20260615(proj, d, horizon=int(horizon))
        if red.empty:
            st.info("Projection table does not expose clean time/price columns yet.")
            return

        yellow = _yellow_projection_from_lunch_data_v20260615(d, horizon=int(horizon), anchor_offset=0, mode=str(mode), risk_filter=str(risk_filter))
        blue_prev = _yellow_projection_from_lunch_data_v20260615(d, horizon=int(horizon), anchor_offset=1, mode=str(mode), risk_filter=str(risk_filter))
        if yellow.empty:
            st.warning("Yellow current path could not be built yet; need more clean candles.")
        if blue_prev.empty:
            st.warning("Blue dotted previous-candle path could not be built yet; need at least one previous candle and enough history.")

        # Accuracy/reliability calibration uses only existing path outputs,
        # completed prediction-vs-actual history, regime reliability and robust
        # OHLC statistics. It adds no model and never replaces source caches.
        try:
            from core.powerbi_path_calibration_20260617 import calibrate_projection_bundle
            regime_meta = _regime_meta_for_red_chart_v20260615()
            calibration = calibrate_projection_bundle(
                d,
                red=red,
                yellow=yellow,
                blue=blue_prev,
                horizon=int(horizon),
                bt_history=st.session_state.get("dv_pp_bt_hist", pd.DataFrame()),
                bt_summary=st.session_state.get("dv_pp_bt_summary", {}),
                regime_reliability=regime_meta.get("reliability"),
                current_regime=regime_meta.get("current_regime"),
                transition_or_conflict=regime_meta.get("regime_validation"),
                source_data_timestamp=d["time"].iloc[-1] if "time" in d.columns else None,
            )
        except Exception as exc:
            calibration = {"ok": False, "message": str(exc)}
        calibrated_main = calibration.get("main", pd.DataFrame()) if isinstance(calibration, dict) else pd.DataFrame()
        red_display = calibration.get("red", pd.DataFrame()) if isinstance(calibration, dict) else pd.DataFrame()
        yellow_display = calibration.get("yellow", pd.DataFrame()) if isinstance(calibration, dict) else pd.DataFrame()
        blue_display = calibration.get("blue", pd.DataFrame()) if isinstance(calibration, dict) else pd.DataFrame()
        if isinstance(red_display, pd.DataFrame) and not red_display.empty:
            red_display = red_display.rename(columns={"red_path": "path"})
        else:
            red_display = red[[c for c in ("step", "time", "path") if c in red.columns]].copy()
        if isinstance(yellow_display, pd.DataFrame) and not yellow_display.empty:
            yellow_display = yellow_display.rename(columns={"yellow_path": "path"})
        else:
            yellow_display = yellow[[c for c in ("step", "time", "path") if c in yellow.columns]].copy() if not yellow.empty else pd.DataFrame()
        if isinstance(blue_display, pd.DataFrame) and not blue_display.empty:
            blue_display = blue_display.rename(columns={"blue_path": "path"})
        else:
            blue_display = blue_prev[[c for c in ("step", "time", "path") if c in blue_prev.columns]].copy() if not blue_prev.empty else pd.DataFrame()
        st.session_state["powerbi_calibrated_bundle_20260617"] = calibration

        smooth_red = _smooth_price_path_v20260615(red_display, "path", "red_path")
        bt = st.session_state.get("dv_pp_bt_summary", {})
        err = _num(bt.get("avg_abs_close_error_pct", 0) if isinstance(bt, dict) else 0, 0)
        acc = _num(bt.get("direction_accuracy_pct", 0) if isinstance(bt, dict) else 0, 0)
        reliability = float(red.get("Reliability %", pd.Series([55])).iloc[0]) if "Reliability %" in red.columns and len(red) else (acc or 55.0)

        alpha_df = pd.DataFrame()
        alpha_label = "-"
        delta_label = "-"
        if not yellow_display.empty and not blue_display.empty:
            y = yellow_display[["step", "time", "path"]].rename(columns={"path": "yellow_path", "time": "yellow_time"})
            b = blue_display[["step", "time", "path"]].rename(columns={"path": "blue_path", "time": "blue_time"})
            alpha_df = y.merge(b, on="step", how="inner")
            if not alpha_df.empty:
                alpha_df["alpha_diff_pips"] = (pd.to_numeric(alpha_df["yellow_path"], errors="coerce") - pd.to_numeric(alpha_df["blue_path"], errors="coerce")) * 10000.0
                alpha_df["delta_point_pips"] = pd.to_numeric(alpha_df["alpha_diff_pips"], errors="coerce").diff().fillna(0.0)
                alpha_df["abs_alpha"] = alpha_df["alpha_diff_pips"].abs()
                alpha_df["abs_delta"] = alpha_df["delta_point_pips"].abs()
                # Pick the strongest absolute alpha/delta candle-time points for vertical markers.
                alpha_row = alpha_df.sort_values("abs_alpha", ascending=False).iloc[0]
                delta_row = alpha_df.sort_values("abs_delta", ascending=False).iloc[0]
                alpha_label = f"H+{int(alpha_row.get('step', 0))} / {float(alpha_row.get('alpha_diff_pips', 0)):.1f} pips"
                delta_label = f"H+{int(delta_row.get('step', 0))} / {float(delta_row.get('delta_point_pips', 0)):.1f}"
                st.session_state["lunch_red_chart_alpha_20260615"] = alpha_df

        meta = _regime_meta_for_red_chart_v20260615()
        meta_error = meta.get("avg_error_pct")
        err = float(meta_error) if meta_error is not None else None
        calibration_summary = calibration.get("summary", {}) if isinstance(calibration, dict) else {}
        reliability = float(calibration_summary.get("reliability_pct", meta.get("reliability", reliability)) or 0)
        meta_acc = calibration_summary.get("direction_accuracy_pct", meta.get("direction_accuracy_pct"))
        if meta_acc is not None:
            acc = _num(meta_acc, acc)
        m = st.columns(7)
        m[0].metric("Current Regime", meta.get("current_regime", "-"), meta.get("regime_validation", "FALSE / WATCH"))
        m[1].metric("Regime Start", meta.get("regime_start_display", "Not recorded"))
        m[2].metric("Regime End", meta.get("regime_end_display", "OPEN / CURRENT"))
        m[3].metric("Path Reliability", f"{reliability:.1f}%", f"Agreement {float(calibration_summary.get('path_agreement_pct', 0) or 0):.1f}%")
        calibrated_error = calibration_summary.get("median_abs_error_pct")
        if calibrated_error is not None:
            err = float(calibrated_error)
        error_proxy = bool(calibration_summary.get("error_is_proxy", meta.get("error_is_proxy")))
        error_samples = int(calibration_summary.get("error_samples", meta.get("error_samples", 0)) or 0)
        m[4].metric("Avg Error (Proxy)" if error_proxy else "Avg Error", f"{err:.5f}%" if err is not None else "N/A", f"{error_samples} samples • {'proxy' if error_proxy else 'actual'}" if err is not None else "Run prediction-vs-actual backtest")
        m[5].metric("Alpha Point", alpha_label)
        m[6].metric("Delta Point", delta_label)
        latest_red = calibrated_main.iloc[-1] if isinstance(calibrated_main, pd.DataFrame) and not calibrated_main.empty else pd.Series(dtype=object)
        bounds = st.columns(4)
        bounds[0].metric("Lower Bound", f"{float(latest_red.get('lower_band', 0) or 0):.5f}" if not latest_red.empty else "N/A")
        bounds[1].metric("Main Projection", f"{float(latest_red.get('main_path', 0) or 0):.5f}" if not latest_red.empty else "N/A")
        bounds[2].metric("Upper Bound", f"{float(latest_red.get('upper_band', 0) or 0):.5f}" if not latest_red.empty else "N/A")
        bounds[3].metric("Band Coverage", f"{float(calibration_summary.get('estimated_band_coverage_pct', 0) or 0):.1f}%", "Empirical estimate")

        vertical_points = calibrated_main[[c for c in ["step", "time", "lower_band", "main_path", "upper_band"] if c in calibrated_main.columns]].copy() if isinstance(calibrated_main, pd.DataFrame) else pd.DataFrame()
        if "step" not in vertical_points.columns:
            vertical_points.insert(0, "step", range(1, len(vertical_points) + 1))
        if not alpha_df.empty:
            alpha_cols = alpha_df[[c for c in ["step", "alpha_diff_pips", "delta_point_pips"] if c in alpha_df.columns]].copy()
            vertical_points = vertical_points.merge(alpha_cols, on="step", how="left")
        vertical_points = vertical_points.rename(columns={
            "step": "Horizon Point", "time": "Projection Time", "lower_band": "Lower Bound",
            "main_path": "Projected Price", "upper_band": "Upper Bound",
            "alpha_diff_pips": "Alpha Point (pips)", "delta_point_pips": "Delta Point (pips)",
        })
        st.session_state["lunch_powerbi_vertical_projection_points_20260617"] = vertical_points

        if err is None:
            st.warning("Reliability warning: prediction-vs-actual error is unavailable. Run the backtest before treating projection accuracy as verified.")
        elif error_proxy:
            st.warning(
                f"Accuracy is not verified yet: {err:.5f}% is a recent-H1 volatility proxy, not completed prediction-vs-actual error. "
                "Run the PowerBI backtest before treating the path as accuracy-tested."
            )
        elif err > 0.08 or (acc and acc < 52):
            st.warning(f"Reliability warning: close-error {err:.4f}% and direction accuracy {acc:.1f}%. Treat the red/yellow paths as weaker until actual/error improves.")
        else:
            st.success(f"Reliability OK: close-error {err:.4f}% and direction accuracy {acc:.1f}% from existing actual/error metrics.")

        try:
            import plotly.graph_objects as go
            view = d.tail(110)
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=view["time"], open=view["open"], high=view["high"], low=view["low"], close=view["close"], name="Actual H1 candles"))

            # Reliability-calibrated MAIN path and empirically expanding bands.
            if isinstance(calibrated_main, pd.DataFrame) and not calibrated_main.empty:
                anchor_time = pd.Timestamp(d["time"].iloc[-1])
                anchor_close = float(d["close"].iloc[-1])
                anchored_times = [anchor_time] + list(calibrated_main["time"])
                fig.add_trace(go.Scatter(x=anchored_times, y=[anchor_close] + list(calibrated_main["upper_band"]), mode="lines", name="Calibrated upper band", line={"color": "rgba(124,58,237,.45)", "dash": "dash"}))
                fig.add_trace(go.Scatter(x=anchored_times, y=[anchor_close] + list(calibrated_main["lower_band"]), mode="lines", name="Calibrated lower band", line={"color": "rgba(124,58,237,.45)", "dash": "dash"}, fill="tonexty", fillcolor="rgba(124,58,237,.09)"))
                fig.add_trace(go.Scatter(x=anchored_times, y=[anchor_close] + list(calibrated_main["main_path"]), mode="lines+markers", name="MAIN reliability-weighted path", line={"color": "#111827", "width": 5, "shape": "spline", "smoothing": 1.0}, marker={"size": 7}))

            # RED/YELLOW/BLUE retain their identities but are shrinkage-calibrated
            # toward the shared main path when reliability or agreement is weak.
            if not red_display.empty:
                fig.add_trace(go.Scatter(x=[pd.Timestamp(d["time"].iloc[-1])] + list(red_display["time"]), y=[float(d["close"].iloc[-1])] + list(red_display["path"]), mode="lines+markers", name="RED calibrated model path", line={"color": "#DC2626", "width": 3}, marker={"size": 5}))
            if isinstance(smooth_red, pd.DataFrame) and not smooth_red.empty:
                fig.add_trace(go.Scatter(x=[pd.Timestamp(d["time"].iloc[-1])] + list(smooth_red["time"]), y=[float(d["close"].iloc[-1])] + list(smooth_red["red_path"]), mode="lines", name="RED smooth calibrated path", line={"color": "#EF4444", "width": 4, "shape": "spline", "smoothing": 1.05}))
            last_time = pd.Timestamp(d["time"].iloc[-1])
            last_close = float(d["close"].iloc[-1])
            if not yellow_display.empty:
                fig.add_trace(go.Scatter(x=[last_time] + list(yellow_display["time"]), y=[last_close] + list(yellow_display["path"]), mode="lines+markers", name="YELLOW calibrated current path", line={"color": "#FACC15", "width": 4}, marker={"color": "#FACC15", "size": 8, "line": {"color": "#111827", "width": 1}}))
            if not blue_display.empty:
                fig.add_trace(go.Scatter(x=[last_time] + list(blue_display["time"]), y=[last_close] + list(blue_display["path"]), mode="lines+markers", name="BLUE calibrated previous path", line={"color": "#2563EB", "width": 3, "dash": "dot"}, marker={"color": "#2563EB", "size": 6}))

            # Alpha/Delta: vertical candle-time points, not horizontal or y2 lines.
            if not alpha_df.empty:
                alpha_row = alpha_df.sort_values("abs_alpha", ascending=False).iloc[0]
                delta_row = alpha_df.sort_values("abs_delta", ascending=False).iloc[0]
                for label, row, dash, symbol in [("Alpha Point", alpha_row, "dot", "star"), ("Delta Point", delta_row, "dash", "diamond")]:
                    xval = row.get("yellow_time")
                    yval = row.get("yellow_path")
                    try:
                        fig.add_vline(x=xval, line_dash=dash, line_width=2, opacity=.82, annotation_text=label, annotation_position="top")
                    except Exception:
                        pass
                    try:
                        fig.add_trace(go.Scatter(x=[xval], y=[yval], mode="markers+text", name=label, text=[label], textposition="top center", marker={"size": 13, "symbol": symbol}))
                    except Exception:
                        pass

            fig.update_layout(
                height=660,
                margin=dict(l=4, r=4, t=52, b=4),
                title="PowerBI Price Projection — calibrated MAIN + upper/lower bands + RED/YELLOW/BLUE paths",
                xaxis_rangeslider_visible=False,
                yaxis=dict(title="Price"),
                legend=dict(orientation="h"),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})
        except Exception as exc:
            st.warning(f"Chart skipped safely: {exc}")

        with st.expander("Open / Close — Vertical Alpha / Delta + Lower / Upper Bounds", expanded=True):
            st.caption("Each projected H1 point is shown vertically with its lower bound, projected price, upper bound, Alpha point and Delta point. The chart whiskers use the same lower/upper values.")
            if isinstance(vertical_points, pd.DataFrame) and not vertical_points.empty:
                st.dataframe(vertical_points, use_container_width=True, hide_index=True, height=300)
            else:
                st.info("Vertical projection points are not ready yet.")

        with st.expander("Open / Close — Prediction line source tables", expanded=False):
            st.markdown("##### Calibrated MAIN path + empirical bands")
            st.dataframe(calibrated_main.head(80), use_container_width=True, hide_index=True, height=220)
            st.markdown("##### RED calibrated source")
            st.dataframe(red_display.head(80), use_container_width=True, hide_index=True, height=220)
            if not yellow_display.empty:
                st.markdown("##### YELLOW calibrated current source")
                st.dataframe(yellow_display.head(80), use_container_width=True, hide_index=True, height=220)
            if not blue_display.empty:
                st.markdown("##### BLUE calibrated previous-candle source")
                st.dataframe(blue_display.head(80), use_container_width=True, hide_index=True, height=220)
            if not alpha_df.empty:
                st.markdown("##### GREEN alpha difference table")
                st.dataframe(alpha_df.head(80), use_container_width=True, hide_index=True, height=220)


def _render_lunch_reorganized(ns: dict) -> None:
    st.markdown("### 🍱 Lunch — Metric + Price Projection Center")
    st.caption("Lunch keeps metric/history and the red prediction-line display. Master reliability and Final Synced Intelligence have moved to Dinner.")
    try:
        import tabs.final_three_center_upgrade_20260614 as three
        three._render_metric_detail_section(ns)
    except Exception as exc:
        st.error("Lunch metric/history section could not render safely.")
        st.exception(exc)
    _render_lunch_red_prediction_line()
    with st.expander("📌 Open / Close — Lunch placement note", expanded=False):
        st.write("Master Decision + Reliability + Priority Center and Final Synced Intelligence are now in **Dinner → Combine Logic**. Original source logic is still visible there at the last place.")


def _render_final_synced_intelligence(ns: dict, prev_data) -> None:
    renderer = ns.get("_render_final_synced_intelligence_inner_20260612")
    if callable(renderer):
        renderer()
        return
    with st.expander("🧠 Open / Close — Final Synced Intelligence: ML Tables + KNN/Greedy + News/NLP + Quant Structure + Research", expanded=False):
        st.caption("Original source is preserved below. This fallback shows cached data without rerunning hidden calculations.")
        pack = st.session_state.get("final_synced_research_merge_pack_20260612") or st.session_state.get("final_merged_intelligence_pack_20260612")
        if isinstance(pack, dict) and pack:
            pr = pack.get("priority_1_to_14")
            if not isinstance(pr, pd.DataFrame) or pr.empty:
                pr = pack.get("knn_greedy_priority")
            cols = st.columns(5)
            cols[0].metric("Master Regime", pack.get("master_regime", "-"))
            cols[1].metric("Master Direction", pack.get("master_direction", "WAIT"))
            cols[2].metric("Forecast Conf", _fmt(pack.get("projection_confidence", 0), "%"))
            cols[3].metric("News Sync", (pack.get("news_nlp", {}) if isinstance(pack.get("news_nlp", {}), dict) else {}).get("news_sync", "-"))
            cols[4].metric("Structure", (pack.get("quant_structure", {}) if isinstance(pack.get("quant_structure", {}), dict) else {}).get("quant_structure_score", "-"))
            if isinstance(pr, pd.DataFrame) and not pr.empty:
                st.dataframe(pr, use_container_width=True, hide_index=True, height=320)
            _copy_button("Copy Cached Final Synced Intelligence", _safe_json(pack), f"copy_cached_final_synced_{UNIQUE}")
        else:
            st.info("Run the original Data Visualization synced intelligence source from the Advanced Details section below.")


def _render_original_data_last(ns: dict, prev_data) -> None:
    with st.expander("📦 Open / Close — Original Data / Advanced Details at Last Place", expanded=False):
        st.caption("This preserved original renderer now reads the same main Settings run automatically. No separate Run or Load button is shown anywhere in the Regime/Dinner workflow.")
        ready = bool(st.session_state.get("metric_run_calculate", False))
        if ready and callable(prev_data):
            try:
                # Existing renderer reads the caches already primed by Settings.
                # It is not allowed to create a separate canonical run.
                st.session_state["dinner_load_original_advanced_details_20260614"] = True
                prev_data()
            except Exception as exc:
                st.error("Original Data Visualization / Final Synced Intelligence source failed safely.")
                with st.expander("Open / Close — technical detail", expanded=False):
                    st.code(str(exc))
        elif not ready:
            try:
                from core.system_wide_completion_20260618 import readiness_message
                st.info(readiness_message(st.session_state, "Research Data Analysis"))
            except Exception:
                st.info("Use Settings → Run Calculation + Open Lunch once.")
        else:
            st.info("Original Data Visualization source is not available in this ZIP.")
        with st.expander("Open / Close — Session source keys for audit", expanded=False):
            keys = [k for k in st.session_state.keys() if any(x in str(k).lower() for x in ["regime", "priority", "reliability", "powerbi", "projection", "synced", "research"])]
            st.dataframe(pd.DataFrame({"Source Key": sorted(map(str, keys))}), use_container_width=True, hide_index=True, height=260)


def _render_priority_decision_reliability(ns: dict) -> None:
    try:
        import tabs.final_three_center_upgrade_20260614 as three
        three._render_master_center(ns)
    except Exception as exc:
        st.error("Priority + Decision + Reliability KNN/Greedy center could not render safely.")
        st.exception(exc)
    ctx = _ctx(ns, False)
    ptab = _priority_table_from_state(ctx)
    if isinstance(ptab, pd.DataFrame) and not ptab.empty:
        with st.expander("📌 Open / Close — Priority + Decision + Reliability KNN/Greedy table", expanded=False):
            st.dataframe(ptab.head(120), use_container_width=True, hide_index=True, height=360)


def _render_chatgpt_style_ai() -> None:
    st.markdown("### 🤖 AI Assistant — Dinner Local Chat")
    st.caption("ChatGPT-like layout. Local NLP + fuzzy matching + history matching only. Regime-aware, priority-aware, reliability-aware. No API, no heavy neural network.")
    try:
        import tabs.ai_assistant_lite as ai
    except Exception as exc:
        st.error("AI Assistant source could not load safely.")
        st.exception(exc)
        return
    try:
        ai._inject_mobile_css()
    except Exception:
        pass
    ctx = ai.build_ai_context_from_existing_data()
    try:
        from core.canonical_runtime_20260617 import get_canonical, shared_from_runtime
        from core.ai_canonical_grounding_20260618 import build_ai_grounding
        canonical = get_canonical(st.session_state)
        shared_runtime = shared_from_runtime(st.session_state)
        ai_component = shared_runtime.get("ai_grounding", {}) if isinstance(shared_runtime, dict) else {}
        canonical_grounding = build_ai_grounding(canonical, ai_component)
        if isinstance(ctx, dict):
            ctx["canonical_grounding_20260618"] = canonical_grounding
            current = ctx.setdefault("current", {})
            current.update({
                "decision": canonical_grounding.get("current_canonical_decision", "WAIT"),
                "direction": canonical_grounding.get("directional_market_view", "WAIT"),
                "regime": canonical_grounding.get("current_regime", "UNKNOWN"),
                "entry_permission": canonical_grounding.get("entry_permission", "NO ENTRY / WAIT"),
                "less_risky_decision": canonical_grounding.get("less_risky_decision", "WAIT"),
            })
    except Exception:
        canonical_grounding = {}
    if "ai_lite_messages" not in st.session_state:
        st.session_state["ai_lite_messages"] = []
    if not st.session_state["ai_lite_messages"]:
        st.session_state["ai_lite_messages"].append({"role": "assistant", "content": "Ask about regime, priority, reliability, TP, exit risk, or next H1 bias. I use only local system data.", "meta": {}})
    st.markdown(
        """
        <style>
        .dinner-chat-shell{border:1px solid rgba(15,23,42,.10);border-radius:22px;padding:.75rem;background:linear-gradient(180deg,rgba(248,250,252,.96),rgba(239,246,255,.86));box-shadow:0 12px 34px rgba(15,23,42,.06);}
        .dinner-chat-meta{font-size:.82rem;color:#475569;padding:.55rem .75rem;border-radius:16px;background:rgba(255,255,255,.70);margin-bottom:.7rem;}
        @media(max-width:780px){.dinner-chat-shell{padding:.55rem;border-radius:18px}.dinner-chat-meta{font-size:.76rem}}
        </style>
        """,
        unsafe_allow_html=True,
    )
    cur = ctx.get("current", {}) if isinstance(ctx, dict) else {}
    st.markdown(
        f"<div class='dinner-chat-shell'><div class='dinner-chat-meta'>EURUSD H1 • Decision <b>{cur.get('decision','-')}</b> • Direction <b>{cur.get('direction','-')}</b> • Regime <b>{cur.get('regime','-')}</b> • Entry {cur.get('entry_score','-')} • Exit Risk {cur.get('exit_risk','-')}</div></div>",
        unsafe_allow_html=True,
    )
    chat_box = st.container(height=420, border=True)
    with chat_box:
        for msg in st.session_state.get("ai_lite_messages", [])[-18:]:
            role = str(msg.get("role", "assistant"))
            with st.chat_message("user" if role == "user" else "assistant"):
                st.markdown(str(msg.get("content", "")))
    labels = ["Use typed question"]
    label_to_item: Dict[str, Dict[str, Any]] = {"Use typed question": {"question": "", "category": "Free Chat"}}
    for item in getattr(ai, "PREPARED_QUESTION_PATTERNS", []):
        q = str(item.get("question", "")).strip()
        if not q:
            continue
        cat = str(item.get("category", "All Questions"))
        label = f"{cat} — {q}"
        if label in label_to_item:
            label = f"{label} #{len(label_to_item)}"
        labels.append(label)
        label_to_item[label] = item
    st.markdown("#### Ask at bottom")
    selected = st.selectbox("One selector", labels, key=f"dinner_ai_selector_{UNIQUE}")
    typed = st.text_area("One question input", height=74, key=f"dinner_ai_input_{UNIQUE}", placeholder="Type: what is current regime risk, best hour, TP for sell, exit now or hold, why priority changed...")
    send = st.button("🚀 Send / Analyze", key=f"dinner_ai_send_{UNIQUE}", use_container_width=True)
    if send:
        selected_item = label_to_item.get(selected, {})
        prompt = str(typed or "").strip() or str(selected_item.get("question", "What should I do now?")).strip()
        if not prompt:
            prompt = "What should I do now?"
        category = "Free Chat" if typed.strip() else str(selected_item.get("category", "Prepared Question"))
        parsed = ai.local_ai_detect_intent(prompt)
        # A selected prepared question already has an explicit tested intent.
        # Preserve it so 1,000 similar variants do not collapse to one fuzzy answer.
        if not typed.strip() and selected_item.get("intent"):
            parsed["intent"] = str(selected_item.get("intent"))
            parsed["intent_label"] = ai.INTENT_REGISTRY.get(parsed["intent"], {}).get("label", parsed["intent"])
            parsed["matched_prepared_question"] = str(selected_item.get("question", prompt))
            parsed["intent_source"] = "prepared-question-exact"
            for field in ("pattern_id", "answer_rule", "category", "pattern", "keywords"):
                if selected_item.get(field) not in (None, ""):
                    parsed[field] = selected_item.get(field)
        parsed["selected_question_category"] = category
        parsed["answer_mode"] = "Auto"
        answer = ai.local_ai_generate_answer(parsed, ctx)
        try:
            answer = ai.apply_prepared_question_focus_20260618(answer, parsed, ctx)
        except Exception:
            pass
        try:
            answer = ai._apply_answer_mode(answer, "Auto", parsed, ctx)
        except Exception:
            pass
        try:
            from core.ai_canonical_grounding_20260618 import format_grounded_answer
            answer = format_grounded_answer(canonical_grounding, answer, question=prompt)
        except Exception:
            pass
        # Add current reliability/regime/priority awareness using existing state.
        warnings = []
        try:
            risk = ai._risk_level(cur)
            if str(risk).upper() in {"HIGH", "DANGER", "AVOID"}:
                warnings.append(f"Risk: {risk}")
        except Exception:
            pass
        regime = cur.get("regime")
        direction = cur.get("direction")
        if regime:
            warnings.append(f"Regime-aware: {regime}")
        if direction:
            warnings.append(f"Priority/decision-aware direction: {direction}")
        missing = ctx.get("missing_fields", []) if isinstance(ctx, dict) else []
        if missing:
            warnings.append(f"Missing fields: {len(missing)}")
        if warnings:
            answer = answer + "\n\nReliability-aware note: " + " • ".join(map(str, warnings))
        st.session_state["ai_lite_messages"].append({"role": "user", "content": prompt, "meta": {"category": category}})
        st.session_state["ai_lite_messages"].append({"role": "assistant", "content": answer, "meta": parsed})
        st.session_state["ai_lite_messages"] = st.session_state["ai_lite_messages"][-32:]
        try:
            ai._store_question_memory(prompt, parsed.get("normalized_question", ""), parsed.get("intent", "nearest_answer_fallback"), answer)
        except Exception:
            pass
        try:
            st.session_state["ai_lite_last_copy_payload"] = ai._copy_payload(prompt, parsed, answer, ctx, category, "Auto")
            st.session_state["ai_lite_last_answer_summary_20260614"] = st.session_state["ai_lite_last_copy_payload"]
        except Exception:
            st.session_state["ai_lite_last_answer_summary_20260614"] = answer
        try:
            from core.styles import request_close_sidebar
            request_close_sidebar()
        except Exception:
            pass
        st.rerun()
    c1, c2 = st.columns(2)
    with c1:
        _copy_button("📋 Copy Last AI Answer", st.session_state.get("ai_lite_last_copy_payload", "No AI answer yet."), f"dinner_copy_last_ai_{UNIQUE}")
    with c2:
        if st.button("🧹 Clear Chat", key=f"dinner_ai_clear_{UNIQUE}", use_container_width=True):
            st.session_state["ai_lite_messages"] = []
            st.session_state["ai_lite_last_copy_payload"] = "No AI answer yet."
            st.rerun()


def _render_dinner(ns: dict, prev_data) -> None:
    """Legacy callable retained with the new two-choice Dinner layout."""
    st.markdown("### 🌙 Dinner — Regime + Synced Intelligence Center")
    options = ["Regime + Combined Logic", "AI Assistant"]
    active = st.session_state.get("dinner_active_inner_20260615", "Regime + Combined Logic")
    if active not in options:
        active = "Regime + Combined Logic"
    try:
        from ui.stable_ui_libs_20260615 import segmented_choice
        active = segmented_choice(
            "Dinner workspace",
            options,
            key="dinner_active_inner_20260615",
            default=active,
        )
    except Exception:
        active = st.selectbox("Dinner workspace", options, index=options.index(active), key=f"dinner_inner_select_{UNIQUE}")
        st.session_state["dinner_active_inner_20260615"] = active
    if active == "AI Assistant":
        _render_chatgpt_style_ai()
    else:
        from tabs.dinner_unified_center_20260617 import render_dinner_unified_center
        render_dinner_unified_center(ns, prev_data)


def _selector() -> str:
    """Stable top page selector.

    Fixes the old locked state where Dinner was visually selected but Lunch
    content still rendered.  One selection now writes to active_page,
    tab_choice, home_inner_tab, and fast-tab state, then reruns immediately.
    """
    choices = [("Lunch", "🍱"), ("Dinner", "🌙"), ("Research", "🎓"), ("Morning", "🌅")]
    aliases = {"Regime": "Dinner", "Dinner Tab": "Dinner", "Doo Prime": "Morning", "Morning Tab": "Morning", "AI Assistant": "Dinner", "AI Assistant Lite": "Dinner", "Data Visualization": "Lunch", "Home": "Lunch"}
    current = st.session_state.get("active_page", st.session_state.get("home_inner_tab", "Lunch"))
    current = aliases.get(str(current), str(current))
    names = [name for name, _ in choices]
    if current not in names:
        current = aliases.get(str(st.session_state.get("home_inner_tab", "Lunch")), "Lunch")
    if current not in names:
        current = "Lunch"
    st.session_state["home_inner_tab"] = current
    selected = current
    try:
        from ui.safe_tab_switch_20260615 import safe_tab_choice
        selected = safe_tab_choice(
            label="Home / Lunch tab choice",
            options=names,
            icons=["box-seam", "moon", "search", "sun"],
            state_key="home_inner_tab",
            widget_key=f"safe_home_inner_tab_switch_{UNIQUE}",
            default=current,
            horizontal=True,
            rerun_on_change=False,
        )
    except Exception:
        cols = st.columns(len(choices))
        for i, (name, icon) in enumerate(choices):
            active = selected == name
            if cols[i].button(("✅ " if active else "") + f"{icon} {name}", key=f"selector_{i}_{UNIQUE}", use_container_width=True):
                selected = name

    selected = aliases.get(str(selected), str(selected))
    if selected not in names:
        selected = "Lunch"

    # Main bug fix: the visible selector and actual router now use the same page key.
    if (
        st.session_state.get("active_page") != selected
        or st.session_state.get("tab_choice") != selected
        or st.session_state.get("home_inner_tab") != selected
    ):
        st.session_state["home_inner_tab"] = selected
        st.session_state["active_page"] = selected
        st.session_state["tab_choice"] = selected
        st.session_state["active_subpage"] = ""
        st.session_state["ui_navigation_click_ts"] = time.time()
        st.session_state["fast_tab_switch_active"] = True
        try:
            st.rerun()
        except Exception:
            pass
    return selected

def install(ns: dict) -> None:
    if ns.get("_dinner_morning_data_patch_installed_20260614"):
        return
    prev_data = ns.get("_render_lunch_data_visualization_inner_tab")
    prev_research = ns.get("_render_home_research_inner_20260612")
    prev_morning = ns.get("_render_doo_prime_inner_tab")
    footer = ns.get("render_tab_footer")
    prev_full_copy = ns.get("_build_lunch_all_copy_text")
    prev_short_copy = ns.get("_build_short_necessary_copy_text")

    def _full_copy_with_dinner() -> str:
        base = prev_full_copy() if callable(prev_full_copy) else ""
        payload = {
            "Dinner Regime Metrics": _regime_metrics(ns),
            "Data Analysis Current Result Table": _analysis_result_dataframe(ns),
            "AI Assistant Last Answer": st.session_state.get("ai_lite_last_answer_summary_20260614", "No AI answer yet."),
        }
        return str(base) + "\n\nDINNER / MORNING / DATA ANALYSIS DISPLAY PATCH 20260614\n" + "=" * 78 + "\n" + _safe_json(payload)

    def _short_copy_with_dinner() -> str:
        base = prev_short_copy() if callable(prev_short_copy) else ""
        table = _analysis_result_dataframe(ns)
        return str(base) + "\n\nDINNER CURRENT ANALYSIS TABLE\n" + table.to_string(index=False)

    if callable(prev_full_copy):
        ns["_build_lunch_all_copy_text"] = _full_copy_with_dinner
    if callable(prev_short_copy):
        ns["_build_short_necessary_copy_text"] = _short_copy_with_dinner

    def _show_final_reorganized() -> None:
        try:
            from core.streamlit_safe_dataframe import install_safe_dataframe_patch
            install_safe_dataframe_patch()
        except Exception:
            pass
        try:
            from core.styles import request_close_sidebar
            request_close_sidebar()
        except Exception:
            pass
        selected = _selector()
        if selected == "Lunch":
            _render_lunch_reorganized(ns)
        elif selected == "Dinner":
            _render_dinner(ns, prev_data)
        elif selected == "Research":
            if callable(prev_research):
                prev_research()
            else:
                try:
                    import tabs.research as research
                    research.show()
                except Exception as exc:
                    st.error("Research / Data Analysis could not load safely.")
                    st.exception(exc)
        elif selected == "Morning":
            st.markdown("### 🌅 Morning — Doo Prime")
            st.caption("Former Doo Prime tab. Source logic is unchanged; only the tab label is renamed.")
            if callable(prev_morning):
                prev_morning()
            else:
                st.info("Morning / Doo Prime source is not available in this ZIP.")
        if callable(footer):
            try:
                footer("Lunch")
            except Exception:
                pass

    ns["show"] = _show_final_reorganized
    ns["render_data_analysis_result_table_20260614"] = render_data_analysis_result_table_20260614
    ns["_dinner_morning_data_patch_installed_20260614"] = True
