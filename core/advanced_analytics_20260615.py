# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Lightweight advanced analytics add-ons for ADX Quant Pro (2026-06-15).

Non-destructive display helpers only.  They read existing session dataframe,
regime context, prediction/error caches, and AI context.  No new tab, no new ML
engine, no external API, and no heavy model is created here.
"""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

UNIQUE = "20260615_adv_analytics"


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        x = float(v)
        return x if math.isfinite(x) else float(default)
    except Exception:
        return float(default)


def _clip(v: Any, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, _num(v, lo))))


def _norm_col(v: Any) -> str:
    return "".join(ch for ch in str(v).lower() if ch.isalnum())


def _find_col(df: pd.DataFrame, aliases: Iterable[str]) -> Optional[str]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    nmap = {_norm_col(c): c for c in df.columns}
    for a in aliases:
        na = _norm_col(a)
        if na in nmap:
            return nmap[na]
    for nk, col in nmap.items():
        for a in aliases:
            na = _norm_col(a)
            if na and na in nk:
                return col
    return None


def get_market_df(limit: int = 5000) -> pd.DataFrame:
    """Return a normalized OHLC dataframe from existing session_state caches."""
    for key in [
        "dv_pp_df", "last_df", "live_df", "shared_df", "cached_df",
        "market_df", "eurusd_h1_df", "lunch_df",
    ]:
        raw = st.session_state.get(key)
        if isinstance(raw, pd.DataFrame) and not raw.empty:
            d = raw.copy().tail(int(limit)).reset_index(drop=True)
            break
    else:
        return pd.DataFrame()

    low = {str(c).lower().strip(): c for c in d.columns}
    rename_map = {
        "datetime": "time", "date": "time", "timestamp": "time", "timeopen": "time",
        "o": "open", "h": "high", "l": "low", "c": "close",
    }
    for src, dst in rename_map.items():
        if src in low and dst not in d.columns:
            d = d.rename(columns={low[src]: dst})
    if "time" not in d.columns:
        d["time"] = pd.date_range(end=pd.Timestamp.now().floor("h"), periods=len(d), freq="h")
    for col in ["open", "high", "low", "close"]:
        if col not in d.columns:
            d[col] = d.get("close", np.nan)
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d["time"] = pd.to_datetime(d["time"], errors="coerce")
    d = d.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates("time", keep="last")
    return d.reset_index(drop=True)


def _feature_frame(d: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(d, pd.DataFrame) or d.empty:
        return pd.DataFrame()
    x = d.copy().reset_index(drop=True)
    close = pd.to_numeric(x["close"], errors="coerce").astype(float)
    x["ret1"] = close.pct_change().fillna(0.0)
    x["move_pips"] = close.diff().fillna(0.0) * 10000.0
    x["abs_move_pips"] = x["move_pips"].abs()
    x["range_pips"] = (pd.to_numeric(x["high"], errors="coerce") - pd.to_numeric(x["low"], errors="coerce")).abs().fillna(0.0) * 10000.0
    x["ma12"] = close.rolling(12, min_periods=3).mean()
    x["ma48"] = close.rolling(48, min_periods=10).mean()
    x["trend_gap_pips"] = (x["ma12"] - x["ma48"]).fillna(0.0) * 10000.0
    x["vol24_pips"] = x["move_pips"].rolling(24, min_periods=6).std().fillna(x["move_pips"].abs().expanding().mean())
    x["hour"] = pd.to_datetime(x["time"]).dt.hour
    x["day_name"] = pd.to_datetime(x["time"]).dt.day_name().str[:3]
    x["direction"] = np.where(x["move_pips"] > 0, "BUY", np.where(x["move_pips"] < 0, "SELL", "WAIT"))
    x["regime_direction"] = np.where(x["ma12"] > x["ma48"], "BULL", np.where(x["ma12"] < x["ma48"], "BEAR", "RANGE"))
    try:
        vol_q = pd.qcut(x["vol24_pips"].rank(method="first"), 3, labels=["Low Vol", "Mid Vol", "High Vol"])
        x["vol_bucket"] = vol_q.astype(str)
    except Exception:
        x["vol_bucket"] = "Mid Vol"
    try:
        trend_abs = x["trend_gap_pips"].abs()
        x["trend_bucket"] = pd.qcut(trend_abs.rank(method="first"), 3, labels=["Flat", "Normal", "Strong"]).astype(str)
    except Exception:
        x["trend_bucket"] = "Normal"
    return x.dropna(subset=["time", "close"]).reset_index(drop=True)


def _regime_score(value: Any) -> float:
    s = str(value or "").upper()
    if "BULL" in s or s == "BUY":
        return 1.0
    if "BEAR" in s or s == "SELL":
        return -1.0
    if "RANGE" in s or "WAIT" in s:
        return 0.0
    return _num(value, 0.0)


def _safe_ratio(now: float, prev: float) -> float:
    if abs(prev) < 1e-12:
        return 0.0
    return float(now / prev)


def _fmt_pct(v: Any) -> str:
    return f"{_num(v):.1f}%"


def build_diagnostic_analysis_table(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    d = get_market_df(3000) if df is None else df.copy()
    x = _feature_frame(d)
    if x.empty:
        return pd.DataFrame([{
            "Diagnostic Area": "Data availability",
            "Cause Found": "No usable OHLC data in session_state",
            "Evidence": "Rows = 0",
            "Impact": "Cannot diagnose regime, volatility, error, or priority.",
            "Action / Fix": "Load/connect data, then press Run Calculation.",
            "Severity": "HIGH",
        }])
    last = x.iloc[-1]
    ret24 = float(x["move_pips"].tail(24).sum()) if len(x) else 0.0
    vol_now = float(x["vol24_pips"].tail(1).iloc[0]) if len(x) else 0.0
    vol_med = float(x["vol24_pips"].tail(240).median()) if len(x) else 0.0
    range_now = float(x["range_pips"].tail(24).mean()) if len(x) else 0.0
    trend_gap = float(last.get("trend_gap_pips", 0.0))

    bt = st.session_state.get("dv_pp_bt_summary", {})
    err_pct = _num(bt.get("avg_abs_close_error_pct", 0) if isinstance(bt, dict) else 0, 0)
    acc_pct = _num(bt.get("direction_accuracy_pct", 0) if isinstance(bt, dict) else 0, 0)
    q = st.session_state.get("last_data_quality", {})
    data_score = _num(q.get("score", q.get("Data Quality Score", 0)) if isinstance(q, dict) else 0, 0)
    regime = st.session_state.get("current_regime") or st.session_state.get("master_regime") or str(last.get("regime_direction", "RANGE"))
    rctx = st.session_state.get("regime_context_20260614", {})
    shift = 0.0
    rel = 0.0
    if isinstance(rctx, dict):
        metrics = rctx.get("metrics", {}) if isinstance(rctx.get("metrics", {}), dict) else rctx
        shift = _num(metrics.get("Transition Risk %", metrics.get("Shift Risk", 0)), 0)
        rel = _num(metrics.get("Regime Reliable Score", metrics.get("Regime Reliability", 0)), 0)

    rows = [
        {
            "Diagnostic Area": "Trend driver",
            "Cause Found": "MA12 above MA48" if trend_gap > 0 else "MA12 below MA48" if trend_gap < 0 else "MA12/MA48 flat",
            "Evidence": f"Trend gap {trend_gap:.2f} pips; 24H net {ret24:.2f} pips",
            "Impact": "Directional bias can dominate entries." if abs(trend_gap) >= 2 else "Trend is weak; prediction can flip faster.",
            "Action / Fix": "Require regime + priority sync before entry.",
            "Severity": "MEDIUM" if abs(trend_gap) >= 2 else "LOW",
        },
        {
            "Diagnostic Area": "Volatility / heat",
            "Cause Found": "Volatility above recent median" if vol_now > vol_med * 1.15 else "Volatility normal/compressed",
            "Evidence": f"Vol24 {vol_now:.2f} pips vs median {vol_med:.2f}; avg range {range_now:.2f} pips",
            "Impact": "TP/SL error risk increases." if vol_now > vol_med * 1.15 else "Lower movement but less phone/system stress.",
            "Action / Fix": "Use run-gated views; avoid auto-refreshing heavy charts.",
            "Severity": "HIGH" if vol_now > vol_med * 1.6 else "MEDIUM" if vol_now > vol_med * 1.15 else "LOW",
        },
        {
            "Diagnostic Area": "Regime conflict / transition",
            "Cause Found": f"Current regime {regime}",
            "Evidence": f"Reliability {rel:.1f}%; shift risk {shift:.1f}%",
            "Impact": "Regime may change; priority should wait." if shift >= 55 or rel < 55 else "Regime state is usable for confirmation.",
            "Action / Fix": "Use alpha/delta regime metrics and resolver before trusting one label.",
            "Severity": "HIGH" if shift >= 60 or rel < 45 else "MEDIUM" if shift >= 45 or rel < 60 else "LOW",
        },
        {
            "Diagnostic Area": "Prediction error",
            "Cause Found": "Backtest/error cache found" if err_pct or acc_pct else "Prediction error cache not ready",
            "Evidence": f"Avg abs close error {err_pct:.4f}%; direction accuracy {acc_pct:.2f}%",
            "Impact": "Projection should be treated as low confidence." if err_pct > 0.08 or (acc_pct and acc_pct < 50) else "Projection quality acceptable if regime agrees.",
            "Action / Fix": "Show confidence, error, freshness, alpha point, and delta point together.",
            "Severity": "HIGH" if err_pct > 0.12 else "MEDIUM" if err_pct > 0.06 else "LOW",
        },
        {
            "Diagnostic Area": "Data quality",
            "Cause Found": "Session dataframe available",
            "Evidence": f"Rows {len(x):,}; data quality score {data_score:.1f}",
            "Impact": "Missing/low quality rows can make analysis unreliable." if data_score and data_score < 60 else "Enough data for lightweight diagnostics.",
            "Action / Fix": "Keep calculations manually run-gated and cache results.",
            "Severity": "MEDIUM" if data_score and data_score < 60 else "LOW",
        },
    ]
    return pd.DataFrame(rows)


def build_sampling_estimating_hypothesis_tables(df: Optional[pd.DataFrame] = None) -> Dict[str, pd.DataFrame]:
    d = get_market_df(4000) if df is None else df.copy()
    x = _feature_frame(d)
    if x.empty or len(x) < 20:
        return {"sampling": pd.DataFrame(), "estimating": pd.DataFrame(), "hypothesis": pd.DataFrame()}
    x = x.tail(1500).copy()
    # Sampling: deterministic stratified sample by session/hour buckets; no random CPU-heavy work.
    bins = pd.cut(x["hour"], bins=[-1, 5, 11, 17, 23], labels=["Asia 00-05", "EU 06-11", "NY 12-17", "Late 18-23"])
    x["session_bucket"] = bins.astype(str)
    sampling = x.groupby("session_bucket", dropna=False).agg(
        Sample_Size=("move_pips", "size"),
        Avg_Move_Pips=("move_pips", "mean"),
        Avg_Abs_Move_Pips=("abs_move_pips", "mean"),
        Up_Rate_Pct=("move_pips", lambda s: float((s > 0).mean() * 100)),
        Avg_Range_Pips=("range_pips", "mean"),
    ).reset_index().rename(columns={"session_bucket": "Sampling Stratum"})
    for col in ["Avg_Move_Pips", "Avg_Abs_Move_Pips", "Up_Rate_Pct", "Avg_Range_Pips"]:
        sampling[col] = pd.to_numeric(sampling[col], errors="coerce").round(3)

    ret = x["move_pips"].dropna().astype(float)
    n = int(len(ret))
    mean = float(ret.mean()) if n else 0.0
    std = float(ret.std(ddof=1)) if n > 1 else 0.0
    se = std / math.sqrt(max(n, 1))
    ci = 1.96 * se
    estimating = pd.DataFrame([
        {"Estimate": "Mean H1 move", "Value": round(mean, 4), "Lower 95%": round(mean - ci, 4), "Upper 95%": round(mean + ci, 4), "Sample Size": n},
        {"Estimate": "Mean absolute H1 move", "Value": round(float(ret.abs().mean()), 4), "Lower 95%": "-", "Upper 95%": "-", "Sample Size": n},
        {"Estimate": "Expected range pips", "Value": round(float(x["range_pips"].mean()), 4), "Lower 95%": "-", "Upper 95%": "-", "Sample Size": n},
    ])
    z = mean / se if se > 1e-12 else 0.0
    try:
        p = 2 * (1 - NormalDist().cdf(abs(z)))
    except Exception:
        p = 1.0
    hypothesis = pd.DataFrame([
        {
            "Hypothesis Test": "H0: average H1 move = 0 pips",
            "Statistic": round(z, 4),
            "p_value_approx": round(float(p), 5),
            "Decision": "Reject H0: directional drift exists" if p < 0.05 else "Do not reject H0: drift not strong",
            "Trading Meaning": "Use trend/regime confirmation" if p < 0.05 else "Avoid forcing direction from mean alone",
        },
        {
            "Hypothesis Test": "H0: high-volatility hours are not larger than normal hours",
            "Statistic": round(float(x.loc[x["vol_bucket"] == "High Vol", "abs_move_pips"].mean() - x["abs_move_pips"].mean()), 4),
            "p_value_approx": "effect-size only",
            "Decision": "High-vol hours move more" if float(x.loc[x["vol_bucket"] == "High Vol", "abs_move_pips"].mean()) > float(x["abs_move_pips"].mean()) else "No high-vol advantage",
            "Trading Meaning": "More TP opportunity but more exit risk" if float(x.loc[x["vol_bucket"] == "High Vol", "abs_move_pips"].mean()) > float(x["abs_move_pips"].mean()) else "Use normal priority rules",
        },
    ])
    return {"sampling": sampling, "estimating": estimating, "hypothesis": hypothesis}


def build_data_mining_extension_tables(df: Optional[pd.DataFrame] = None) -> Dict[str, pd.DataFrame]:
    d = get_market_df(4000) if df is None else df.copy()
    x = _feature_frame(d)
    if x.empty or len(x) < 40:
        empty = pd.DataFrame()
        return {"pattern": empty, "cluster": empty, "association": empty, "anomaly": empty, "cube": empty}
    x = x.tail(1800).copy()

    # Pattern evaluation.
    x["prev_direction"] = x["direction"].shift(1).fillna("WAIT")
    x["momentum_hit"] = x["direction"] == x["prev_direction"]
    x["reversal_hit"] = (x["direction"] != x["prev_direction"]) & (x["direction"] != "WAIT") & (x["prev_direction"] != "WAIT")
    pattern = pd.DataFrame([
        {"Pattern Evaluation": "Momentum continuation", "Hit Rate %": round(float(x["momentum_hit"].mean() * 100), 2), "Evidence": "Current candle direction equals previous candle direction", "Use": "Good for hold/follow only when regime agrees"},
        {"Pattern Evaluation": "Reversal pressure", "Hit Rate %": round(float(x["reversal_hit"].mean() * 100), 2), "Evidence": "Direction flips after previous candle", "Use": "Use with exit-risk/protect logic"},
        {"Pattern Evaluation": "Regime-aligned move", "Hit Rate %": round(float(((x["regime_direction"].eq("BULL") & x["direction"].eq("BUY")) | (x["regime_direction"].eq("BEAR") & x["direction"].eq("SELL"))).mean() * 100), 2), "Evidence": "Move direction matches derived regime", "Use": "Confirm priority and reliability"},
    ])

    # Lightweight clustering by volatility/trend buckets.
    cluster = x.groupby(["vol_bucket", "trend_bucket", "regime_direction"], dropna=False).agg(
        Rows=("move_pips", "size"),
        Avg_Move_Pips=("move_pips", "mean"),
        Avg_Abs_Move_Pips=("abs_move_pips", "mean"),
        Up_Rate_Pct=("move_pips", lambda s: float((s > 0).mean() * 100)),
        Avg_Range_Pips=("range_pips", "mean"),
    ).reset_index().sort_values(["Rows", "Avg_Abs_Move_Pips"], ascending=[False, False]).head(60)
    for col in ["Avg_Move_Pips", "Avg_Abs_Move_Pips", "Up_Rate_Pct", "Avg_Range_Pips"]:
        cluster[col] = pd.to_numeric(cluster[col], errors="coerce").round(3)

    # Association rules for simple market baskets.
    total = max(len(x), 1)
    high_vol = x["vol_bucket"].eq("High Vol")
    strong_trend = x["trend_bucket"].eq("Strong")
    bull_regime = x["regime_direction"].eq("BULL")
    bear_regime = x["regime_direction"].eq("BEAR")
    big_move = x["abs_move_pips"] >= float(x["abs_move_pips"].quantile(0.70))
    up_move = x["move_pips"] > 0
    down_move = x["move_pips"] < 0

    def assoc_row(name: str, antecedent: pd.Series, consequent: pd.Series, use: str) -> Dict[str, Any]:
        a = antecedent.fillna(False)
        c = consequent.fillna(False)
        support = float((a & c).mean() * 100)
        conf = float(((a & c).sum() / max(int(a.sum()), 1)) * 100)
        base = float(c.mean())
        lift = float((conf / 100) / max(base, 1e-9))
        return {"Association Rule": name, "Support %": round(support, 2), "Confidence %": round(conf, 2), "Lift": round(lift, 3), "Use": use}

    association = pd.DataFrame([
        assoc_row("High Vol → Big Move", high_vol, big_move, "TP possible but risk wider"),
        assoc_row("Strong Trend → Big Move", strong_trend, big_move, "Follow only with priority sync"),
        assoc_row("Bull Regime → Up Move", bull_regime, up_move, "BUY confirmation proxy"),
        assoc_row("Bear Regime → Down Move", bear_regime, down_move, "SELL confirmation proxy"),
    ]).sort_values(["Lift", "Confidence %"], ascending=[False, False])

    # Anomaly detection: z-score on move and range.
    mv = x["move_pips"].astype(float)
    rg = x["range_pips"].astype(float)
    z_move = (mv - mv.rolling(96, min_periods=20).mean()) / mv.rolling(96, min_periods=20).std().replace(0, np.nan)
    z_range = (rg - rg.rolling(96, min_periods=20).mean()) / rg.rolling(96, min_periods=20).std().replace(0, np.nan)
    work = x.copy()
    work["Move_Z"] = z_move.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    work["Range_Z"] = z_range.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    work["Anomaly Score"] = (work["Move_Z"].abs() * 0.55 + work["Range_Z"].abs() * 0.45).round(3)
    anomaly = work.sort_values(["Anomaly Score", "time"], ascending=[False, False]).head(30)[["time", "hour", "direction", "regime_direction", "move_pips", "range_pips", "Move_Z", "Range_Z", "Anomaly Score"]].copy()
    for col in ["move_pips", "range_pips", "Move_Z", "Range_Z", "Anomaly Score"]:
        anomaly[col] = pd.to_numeric(anomaly[col], errors="coerce").round(3)

    # 3D data cube: Hour × Regime × Volatility bucket.
    cube = x.groupby(["hour", "regime_direction", "vol_bucket"], dropna=False).agg(
        Candle_Count=("move_pips", "size"),
        Avg_Move_Pips=("move_pips", "mean"),
        Avg_Abs_Move_Pips=("abs_move_pips", "mean"),
        Up_Rate_Pct=("move_pips", lambda s: float((s > 0).mean() * 100)),
        Avg_Range_Pips=("range_pips", "mean"),
    ).reset_index().sort_values(["Candle_Count", "Avg_Abs_Move_Pips"], ascending=[False, False]).head(120)
    for col in ["Avg_Move_Pips", "Avg_Abs_Move_Pips", "Up_Rate_Pct", "Avg_Range_Pips"]:
        cube[col] = pd.to_numeric(cube[col], errors="coerce").round(3)
    cube = cube.rename(columns={"hour": "Hour Dimension", "regime_direction": "Regime Dimension", "vol_bucket": "Volatility Dimension"})

    return {"pattern": pattern, "cluster": cluster, "association": association, "anomaly": anomaly, "cube": cube}


def build_regime_alpha_delta_table(ns: Optional[dict] = None) -> pd.DataFrame:
    """Calculate regime alpha/delta from previous vs current regime path.

    Alpha = current-vs-previous regime difference + ratio drift + divergence
    mean.  Delta = now-alpha vs previous-alpha difference/ratio/divergence. It
    is display-only and does not modify regime formulas.
    """
    hist = pd.DataFrame()
    if ns:
        try:
            builder = ns.get("build_regime_context_20260614")
            rctx = builder(force=False) if callable(builder) and bool(st.session_state.get("metric_run_calculate", False)) else st.session_state.get("regime_context_20260614", {})
            if isinstance(rctx, dict):
                raw = rctx.get("history", pd.DataFrame())
                if isinstance(raw, pd.DataFrame) and not raw.empty:
                    hist = raw.copy()
        except Exception:
            hist = pd.DataFrame()
    if hist.empty:
        d = get_market_df(900)
        x = _feature_frame(d)
        if not x.empty:
            hist = x[["time", "regime_direction", "trend_gap_pips", "vol24_pips"]].copy().rename(columns={"regime_direction": "regime"})
    if hist.empty:
        return pd.DataFrame()

    tcol = _find_col(hist, ["time", "datetime", "date", "end", "end time", "timestamp"])
    rcol = _find_col(hist, ["regime", "major regime", "current regime", "h1 regime", "regime_direction"])
    score_col = _find_col(hist, ["path", "score", "regime score", "Regime Score", "confidence score"])
    out = pd.DataFrame()
    if rcol is not None:
        out["Now Regime"] = hist[rcol].astype(str)
        out["Now Regime Score"] = out["Now Regime"].map(_regime_score).astype(float)
    elif score_col is not None:
        out["Now Regime Score"] = pd.to_numeric(hist[score_col], errors="coerce").fillna(0.0).astype(float)
        out["Now Regime"] = np.where(out["Now Regime Score"] > 0.25, "BULL", np.where(out["Now Regime Score"] < -0.25, "BEAR", "RANGE"))
    else:
        return pd.DataFrame()
    out["time"] = pd.to_datetime(hist[tcol], errors="coerce") if tcol else pd.date_range(end=pd.Timestamp.now().floor("h"), periods=len(out), freq="h")
    out = out.dropna(subset=["time"]).tail(120).reset_index(drop=True)
    out["Prev Regime"] = out["Now Regime"].shift(1).fillna(out["Now Regime"].iloc[0])
    out["Prev Regime Score"] = out["Now Regime Score"].shift(1).fillna(out["Now Regime Score"].iloc[0])
    out["Regime Difference"] = out["Now Regime Score"] - out["Prev Regime Score"]
    out["Regime Ratio Now/Prev"] = [_safe_ratio(n, p) for n, p in zip(out["Now Regime Score"], out["Prev Regime Score"])]
    out["Regime Ratio Drift"] = out["Regime Ratio Now/Prev"].replace([np.inf, -np.inf], np.nan).fillna(0.0) - 1.0
    out["Regime Divergence Mean"] = out["Regime Difference"].abs().expanding().mean()
    out["Regime Alpha"] = (out["Regime Difference"] + out["Regime Ratio Drift"] + out["Regime Divergence Mean"]) / 3.0
    out["Prev Alpha"] = out["Regime Alpha"].shift(1).fillna(0.0)
    out["Alpha Difference"] = out["Regime Alpha"] - out["Prev Alpha"]
    out["Alpha Ratio Now/Prev"] = [_safe_ratio(n, p) for n, p in zip(out["Regime Alpha"], out["Prev Alpha"])]
    out["Alpha Ratio Drift"] = out["Alpha Ratio Now/Prev"].replace([np.inf, -np.inf], np.nan).fillna(0.0) - 1.0
    out["Alpha Divergence Mean"] = out["Alpha Difference"].abs().expanding().mean()
    out["Regime Delta"] = (out["Alpha Difference"] + out["Alpha Ratio Drift"] + out["Alpha Divergence Mean"]) / 3.0
    out["Delta Meaning"] = np.where(out["Regime Delta"].abs() >= 0.65, "Strong regime change pressure", np.where(out["Regime Delta"].abs() >= 0.25, "Moderate regime movement", "Stable / low change"))
    for c in ["Now Regime Score", "Prev Regime Score", "Regime Difference", "Regime Ratio Now/Prev", "Regime Ratio Drift", "Regime Divergence Mean", "Regime Alpha", "Prev Alpha", "Alpha Difference", "Alpha Ratio Now/Prev", "Alpha Ratio Drift", "Alpha Divergence Mean", "Regime Delta"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0).round(4)
    return out


def render_regime_alpha_delta_metrics(ns: Optional[dict] = None, *, key: str = "regime_alpha_delta") -> pd.DataFrame:
    table = build_regime_alpha_delta_table(ns)
    st.session_state[f"{key}_table_{UNIQUE}"] = table
    if not isinstance(table, pd.DataFrame) or table.empty:
        st.info("Regime Alpha/Delta needs regime history or OHLC data. Run Regime Sync/Data Visualization first.")
        return table
    last = table.iloc[-1]
    c = st.columns(4)
    c[0].metric("Regime Alpha", f"{_num(last.get('Regime Alpha')):.4f}")
    c[1].metric("Regime Delta", f"{_num(last.get('Regime Delta')):.4f}")
    c[2].metric("Regime Diff", f"{_num(last.get('Regime Difference')):.4f}")
    c[3].metric("Div Mean", f"{_num(last.get('Regime Divergence Mean')):.4f}")
    st.caption(f"Alpha uses previous-vs-now regime difference + ratio drift + divergence mean. Delta uses previous-alpha vs now-alpha difference + ratio drift + divergence mean. Latest: {last.get('Delta Meaning', '-')}")
    with st.expander("Open / Close — Regime Alpha / Delta calculation table", expanded=False):
        try:
            from ui.stable_ui_libs_20260615 import modern_table
            modern_table(table.tail(80), f"{key}_modern_table_{UNIQUE}", height=320)
        except Exception:
            st.dataframe(table.tail(80), use_container_width=True, hide_index=True, height=320)
    return table


def _render_table(df: pd.DataFrame, key: str, height: int = 260) -> None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        st.info("No rows yet. Load data and press Run Calculation.")
        return
    try:
        from ui.stable_ui_libs_20260615 import modern_table
        modern_table(df, key, height=height)
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True, height=height)


def render_diagnostic_analysis_table(*, key: str = "diagnostic_analysis", expanded: bool = False) -> pd.DataFrame:
    table = build_diagnostic_analysis_table()
    st.session_state[f"{key}_table_{UNIQUE}"] = table
    with st.expander("Open / Close — Diagnostic Analysis Table", expanded=expanded):
        st.caption("Shows WHY the current market/system result may be happening. Lightweight and cached; no new model.")
        _render_table(table, f"{key}_{UNIQUE}", height=260)
    return table


def render_sampling_estimation_hypothesis_panel(*, key: str = "sampling_hypothesis", expanded: bool = False) -> Dict[str, pd.DataFrame]:
    tabs = build_sampling_estimating_hypothesis_tables()
    with st.expander("Open / Close — Sampling + Estimating + Hypothesis Testing", expanded=expanded):
        st.caption("Deterministic lightweight statistics using existing candles only. No SciPy/sklearn required.")
        sub = st.tabs(["Sampling", "Estimating", "Hypothesis"])
        with sub[0]:
            _render_table(tabs.get("sampling", pd.DataFrame()), f"{key}_sampling_{UNIQUE}", 240)
        with sub[1]:
            _render_table(tabs.get("estimating", pd.DataFrame()), f"{key}_estimating_{UNIQUE}", 220)
        with sub[2]:
            _render_table(tabs.get("hypothesis", pd.DataFrame()), f"{key}_hypothesis_{UNIQUE}", 240)
    return tabs


def render_data_mining_advanced_panel(*, key: str = "data_mining_advanced", expanded: bool = False) -> Dict[str, pd.DataFrame]:
    tables = build_data_mining_extension_tables()
    with st.expander("Open / Close — Pattern Evaluation + Cluster + Association + Anomaly + 3D Data Cube", expanded=expanded):
        st.caption("Adds requested data-mining views inside one open/close field. CPU/RAM safe: quantile buckets and groupby only; no new ML model.")
        sub = st.tabs(["Pattern", "Cluster", "Association", "Anomaly", "3D Cube"])
        with sub[0]:
            _render_table(tables.get("pattern", pd.DataFrame()), f"{key}_pattern_{UNIQUE}", 230)
        with sub[1]:
            _render_table(tables.get("cluster", pd.DataFrame()), f"{key}_cluster_{UNIQUE}", 310)
        with sub[2]:
            _render_table(tables.get("association", pd.DataFrame()), f"{key}_association_{UNIQUE}", 240)
        with sub[3]:
            _render_table(tables.get("anomaly", pd.DataFrame()), f"{key}_anomaly_{UNIQUE}", 320)
        with sub[4]:
            _render_table(tables.get("cube", pd.DataFrame()), f"{key}_cube_{UNIQUE}", 340)
    st.session_state[f"{key}_tables_{UNIQUE}"] = {k: (v.head(120).to_dict("records") if isinstance(v, pd.DataFrame) else []) for k, v in tables.items()}
    return tables


def render_data_mining_advanced_inline(*, key: str = "data_mining_advanced_inline") -> Dict[str, pd.DataFrame]:
    """Inline version for existing open/close fields, avoiding nested expanders."""
    tables = build_data_mining_extension_tables()
    st.caption("Pattern evaluation, sampling-aware clustering, association rules, anomaly analysis, and 3D cube use existing candles only.")
    sub = st.tabs(["Pattern", "Cluster", "Association", "Anomaly", "3D Cube"])
    with sub[0]:
        _render_table(tables.get("pattern", pd.DataFrame()), f"{key}_pattern_{UNIQUE}", 230)
    with sub[1]:
        _render_table(tables.get("cluster", pd.DataFrame()), f"{key}_cluster_{UNIQUE}", 310)
    with sub[2]:
        _render_table(tables.get("association", pd.DataFrame()), f"{key}_association_{UNIQUE}", 240)
    with sub[3]:
        _render_table(tables.get("anomaly", pd.DataFrame()), f"{key}_anomaly_{UNIQUE}", 320)
    with sub[4]:
        _render_table(tables.get("cube", pd.DataFrame()), f"{key}_cube_{UNIQUE}", 340)
    return tables
