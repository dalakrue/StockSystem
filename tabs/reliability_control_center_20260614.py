"""Reliability Control Center for Home/Lunch (2026-06-14).

Additive display/copy layer only. It uses existing OHLC, history, regime,
priority, forecast, and metric values already present in Streamlit state.
No external APIs, no new prediction engines, and no heavy model imports.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st

UNIQUE = "20260614_reliability_control_center"


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        if isinstance(v, str):
            v = v.replace("%", "").replace("/10", "").replace(",", "").strip()
        x = float(v)
        return x if math.isfinite(x) else float(default)
    except Exception:
        return float(default)


def _clip(v: Any, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, _num(v, lo))))


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def _label(score: float) -> str:
    score = _clip(score)
    if score >= 90:
        return "Elite"
    if score >= 80:
        return "Strong"
    if score >= 70:
        return "Good"
    if score >= 60:
        return "Weak"
    return "Avoid"


def _drift_label(score: float) -> str:
    if score < 35:
        return "Normal"
    if score < 65:
        return "Caution"
    return "Dangerous"


def _find_col(df: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    nmap = {_norm(c): c for c in df.columns}
    for a in aliases:
        if _norm(a) in nmap:
            return nmap[_norm(a)]
    for nk, col in nmap.items():
        for a in aliases:
            na = _norm(a)
            if na and na in nk:
                return col
    return None


def _series(df: pd.DataFrame, aliases: Iterable[str], default: float = 0.0) -> pd.Series:
    col = _find_col(df, aliases)
    if col is None:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default).astype(float)


def _time_to_naive(s: pd.Series) -> pd.Series:
    out = pd.to_datetime(s, errors="coerce")
    try:
        if getattr(out.dt, "tz", None) is not None:
            out = out.dt.tz_convert(None)
    except Exception:
        try:
            out = out.dt.tz_localize(None)
        except Exception:
            pass
    return out


def _market_df() -> pd.DataFrame:
    for key in ["last_df", "dv_pp_df", "lunch_visual_df", "custom_h1_df", "home_df", "full_metric_history_df"]:
        obj = st.session_state.get(key)
        if isinstance(obj, pd.DataFrame) and not obj.empty:
            d = obj.copy().tail(7000).reset_index(drop=True)
            break
    else:
        return pd.DataFrame()

    rename: Dict[str, str] = {}
    cols = {_norm(c): c for c in d.columns}
    for src, dst in {
        "datetime": "time", "timestamp": "time", "date": "time",
        "o": "open", "h": "high", "l": "low", "c": "close",
    }.items():
        if src in cols and dst not in d.columns:
            rename[cols[src]] = dst
    if rename:
        d = d.rename(columns=rename)
    if "time" not in d.columns:
        return pd.DataFrame()
    d["time"] = _time_to_naive(d["time"])
    if "close" not in d.columns:
        return pd.DataFrame()
    for c in ["open", "high", "low", "close"]:
        if c not in d.columns:
            d[c] = d["close"]
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").reset_index(drop=True)


def _flat(obj: Any, prefix: str = "", depth: int = 0) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if depth > 4:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.update(_flat(v, key, depth + 1))
            elif not isinstance(v, (pd.DataFrame, list, tuple)):
                out[key] = v
    return out


def _flat_state() -> Dict[str, Any]:
    keys = [
        "eurusd_h1_matrix_export", "dv_pp_regime_summary", "dv_pp_bt_summary",
        "lunch_5layer_powerbi_result", "nylo_unified_home_sync_20260612",
        "final_merged_intelligence_pack_20260612", "final_synced_research_merge_pack_20260612",
        "technical_logic_upgrade_lunch_v20260611", "dv_research_alignment_pack_20260612",
        "powerbi_projection_upgrade_20260614", "regime_context_20260614",
    ]
    flat: Dict[str, Any] = {}
    for key in keys:
        obj = st.session_state.get(key, {})
        if isinstance(obj, dict):
            flat.update(_flat(obj, key))
    for k, v in st.session_state.items():
        if not isinstance(v, (pd.DataFrame, dict, list, tuple)):
            flat[str(k)] = v
    return flat


def _find_state(flat: Dict[str, Any], aliases: Iterable[str], default: Any = None) -> Any:
    nmap = {_norm(k): v for k, v in flat.items()}
    for a in aliases:
        if _norm(a) in nmap:
            return nmap[_norm(a)]
    for nk, v in nmap.items():
        for a in aliases:
            na = _norm(a)
            if na and na in nk:
                return v
    return default


def _returns(d: pd.DataFrame) -> pd.Series:
    if d.empty:
        return pd.Series(dtype=float)
    return d["close"].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _atr(d: pd.DataFrame, window: int = 14) -> pd.Series:
    if d.empty:
        return pd.Series(dtype=float)
    tr = (d["high"] - d["low"]).abs()
    return tr.rolling(window, min_periods=2).mean().fillna(tr.expanding(min_periods=1).mean()).ffill().fillna(0.0)


def _safe_metric(value: Any, suffix: str = "") -> str:
    if isinstance(value, (int, float, np.number)) and math.isfinite(float(value)):
        if suffix == "%":
            return f"{float(value):.1f}%"
        if abs(float(value)) >= 100:
            return f"{float(value):.0f}{suffix}"
        return f"{float(value):.2f}{suffix}"
    return str(value)


def _feature_leakage_guard(d: pd.DataFrame) -> Dict[str, Any]:
    cols = [str(c) for c in d.columns] if isinstance(d, pd.DataFrame) else []
    ncols = [_norm(c) for c in cols]
    future_terms = ["future", "target", "label", "nextclose", "nextopen", "nexthigh", "nextlow", "shiftminus", "ytrue", "actualfuture"]
    pred_terms = ["prediction", "predicted", "forecast", "backtest", "actual"]
    future_cols = [c for c, nc in zip(cols, ncols) if any(t in nc for t in future_terms)]
    target_cols = [c for c, nc in zip(cols, ncols) if any(t in nc for t in ["target", "label", "ytrue", "actualfuture"])]
    pred_cols = [c for c, nc in zip(cols, ncols) if any(t in nc for t in pred_terms)]
    backtest_keys = [k for k in st.session_state.keys() if any(x in str(k).lower() for x in ["backtest", "bt_summary", "actual_vs_pred"])]
    risk = 8 + min(50, len(future_cols) * 18) + min(30, len(target_cols) * 18)
    if pred_cols and future_cols:
        risk += 20
    if future_cols and st.session_state.get("source", "").upper() not in {"BACKTEST", "TRAIN", "RESEARCH"}:
        risk += 15
    risk = _clip(risk)
    return {
        "Leakage Risk %": round(risk, 1),
        "Future Column Warning": "YES: " + ", ".join(future_cols[:5]) if future_cols else "NO future/target columns in live OHLC",
        "Target Alignment Warning": "YES: target-like column found" if target_cols else "NO target column detected in active OHLC",
        "Backtest-only Warning": "CAUTION: backtest artifacts active" if backtest_keys and future_cols else "NO live/backtest leakage pattern detected",
        "Live-safe / Unsafe": "Unsafe" if risk >= 65 else "Live-safe" if risk < 35 else "Caution",
    }


def _data_quality(d: pd.DataFrame) -> Dict[str, Any]:
    if d.empty:
        return {"Missing Candle Count": 999, "Duplicate Time Count": 0, "OHLC Error Count": 0, "Gap Hour Count": 999, "Last Update Age": "NO DATA", "Bad Row Warning": "NO OHLC DATA", "Data Quality Score": 0.0}
    raw_time = d["time"]
    dup = int(raw_time.duplicated().sum())
    clean = d.drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)
    diff_h = clean["time"].diff().dt.total_seconds().div(3600).dropna()
    step = float(diff_h[(diff_h > 0) & (diff_h < 72)].median()) if not diff_h.empty else 1.0
    if not math.isfinite(step) or step <= 0:
        step = 1.0
    expected = int(round((clean["time"].iloc[-1] - clean["time"].iloc[0]).total_seconds() / 3600 / step)) + 1 if len(clean) > 1 else len(clean)
    missing = max(0, expected - len(clean))
    gap_count = int((diff_h > step * 1.5).sum()) if not diff_h.empty else 0
    ohlc_err = int(((clean["high"] < clean[["open", "close", "low"]].max(axis=1)) | (clean["low"] > clean[["open", "close", "high"]].min(axis=1)) | (clean[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
    now = pd.Timestamp.now()
    age_hours = max(0.0, (now - clean["time"].iloc[-1]).total_seconds() / 3600.0) if pd.notna(clean["time"].iloc[-1]) else 999.0
    score = 100 - missing * 1.8 - dup * 3.0 - ohlc_err * 6.0 - gap_count * 4.0 - max(0, age_hours - max(2.5, step * 2.5)) * 2.0
    score = _clip(score)
    return {
        "Missing Candle Count": int(missing),
        "Duplicate Time Count": int(dup),
        "OHLC Error Count": int(ohlc_err),
        "Gap Hour Count": int(gap_count),
        "Last Update Age": f"{age_hours:.1f}h",
        "Bad Row Warning": "YES" if (missing + dup + ohlc_err + gap_count) else "NO",
        "Data Quality Score": round(score, 1),
        "_age_hours": age_hours,
    }


def _direction_from_regime(regime: Any) -> str:
    s = str(regime or "").upper()
    if "BULL" in s:
        return "BUY"
    if "BEAR" in s:
        return "SELL"
    return "WAIT"


def _regime_reliability(ns: dict, d: pd.DataFrame, flat: Dict[str, Any]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {}
    build_regime = ns.get("build_regime_context_20260614")
    if callable(build_regime):
        try:
            ctx = build_regime(False) or {}
        except Exception:
            ctx = {}
    metrics = ctx.get("metrics", {}) if isinstance(ctx, dict) else {}
    regime = metrics.get("Current Regime") or _find_state(flat, ["current_regime", "major_regime", "dv_pp_regime_summary.current_regime"], "RANGE_NORMAL")
    conf = _clip(metrics.get("Regime Confidence %", _find_state(flat, ["Regime Confidence %", "regime_confidence", "bull_probability"], 55)))
    age = _num(metrics.get("Regime Age Hours", 0), 0)
    stability = _clip(metrics.get("Regime Stability Score", 55))
    shift = _clip(metrics.get("Transition Risk %", 45))
    expected = max(1.0, _num(metrics.get("Expected Duration Hours", 36), 36))
    decay = _clip(age / expected * 100)
    reliability = _clip(metrics.get("Regime Reliable Score", conf * .35 + stability * .35 + (100 - shift) * .30 - decay * .12))
    hist = ctx.get("history", pd.DataFrame()) if isinstance(ctx, dict) else pd.DataFrame()
    similar = 0
    if isinstance(hist, pd.DataFrame) and not hist.empty and "Regime" in hist.columns:
        similar = int((hist["Regime"].astype(str) == str(regime)).sum())
    return {
        "Current Regime": str(regime),
        "Regime Confidence %": round(conf, 1),
        "Regime Age": f"{int(age)}h",
        "Regime Stability": round(stability, 1),
        "Regime Shift Risk": round(shift, 1),
        "Regime Decay %": round(decay, 1),
        "Similar Historical Regimes": similar,
        "Regime Reliability Score": round(reliability, 1),
        "Regime Trusted?": "Trusted" if reliability >= 70 and shift < 55 else "Not trusted / wait" if reliability < 55 else "Caution",
    }


def _priority_table_from_ohlc(d: pd.DataFrame, flat: Dict[str, Any]) -> pd.DataFrame:
    if d.empty:
        return pd.DataFrame()
    x = d.tail(96).copy().reset_index(drop=True)
    ret = x["close"].pct_change().fillna(0)
    atr = _atr(x, 14).replace(0, np.nan).ffill().fillna(1e-9)
    hour = x["time"].dt.hour.astype(float)
    master = _num(_find_state(flat, ["Master /10", "master_score"], 5), 5)
    entry = _num(_find_state(flat, ["Entry /10", "entry_score"], 5), 5)
    tp = _num(_find_state(flat, ["TP /10", "TP Quality"], 5), 5)
    risk = _num(_find_state(flat, ["Exit Risk /10", "exit_risk"], 5), 5)
    if master <= 10: master *= 10
    if entry <= 10: entry *= 10
    if tp <= 10: tp *= 10
    if risk <= 10: risk *= 10
    wave = 7 * np.sin((hour.to_numpy() - 6) / 24 * 2 * np.pi)
    momentum = ret.rolling(6, min_periods=2).mean().fillna(0).to_numpy() * 80000
    range_rank = ((x["high"] - x["low"]) / atr).clip(0, 3).fillna(1).to_numpy()
    base = 48 + master * .10 + entry * .12 + tp * .08 + (100 - risk) * .10
    greedy = np.clip(base + wave + momentum - np.maximum(0, range_rank - 1.5) * 8, 1, 100)
    knn = np.clip(greedy * .86 + (50 + np.cos((hour.to_numpy() - 12) / 24 * 2 * np.pi) * 10) * .14, 1, 100)
    labels = pd.cut(greedy, bins=[0, 45, 60, 70, 80, 90, 101], labels=["Avoid", "C", "B", "B+", "A", "A+"])
    return pd.DataFrame({
        "Time": x["time"], "Hour": hour.astype(int), "Greedy Score": np.round(greedy, 1),
        "KNN Priority Score": np.round(knn, 1), "Priority Label": labels.astype(str),
    }).tail(48).reset_index(drop=True)


def _collect_priority_table(ns: dict, d: pd.DataFrame, flat: Dict[str, Any]) -> pd.DataFrame:
    candidates: List[pd.DataFrame] = []
    for key in ["final_priority_history_Lunch", "final_priority_history_Lunch Tables", "ny_london_overlap_table", "ny_london_overlap_history"]:
        obj = st.session_state.get(key)
        if isinstance(obj, pd.DataFrame) and not obj.empty:
            candidates.append(obj.copy())
    pack = st.session_state.get("nylo_unified_home_sync_20260612")
    if isinstance(pack, dict) and isinstance(pack.get("table"), pd.DataFrame) and not pack.get("table").empty:
        candidates.append(pack.get("table").copy())
    for obj in candidates:
        names = " ".join(str(c).lower() for c in obj.columns)
        if any(x in names for x in ["priority", "greedy", "knn", "score", "hour"]):
            enricher = ns.get("_dynamic_priority_enrich_20260614")
            if callable(enricher):
                try:
                    obj = enricher(obj)
                except Exception:
                    pass
            return obj.tail(80).reset_index(drop=True)
    return _priority_table_from_ohlc(d, flat)


def _priority_anti_constant(ns: dict, d: pd.DataFrame, flat: Dict[str, Any]) -> Tuple[Dict[str, Any], pd.DataFrame]:
    tab = _collect_priority_table(ns, d, flat)
    if tab.empty:
        return {"Hourly Priority Variance": 0.0, "Greedy Score Change %": 0.0, "KNN Score Change %": 0.0, "Constant Score Warning": "NO PRIORITY TABLE", "Priority Movement Score": 0.0, "Dynamic Priority Reliability": 0.0}, tab
    g = _series(tab, ["Greedy Score", "Priority Score", "KNN Priority Score", "Reliability Score"], 60)
    k = _series(tab, ["KNN Priority Score", "Priority Score", "Greedy Score"], 60)
    label_col = _find_col(tab, ["Priority Label", "Label", "Decision", "Entry Opportunity"])
    label_unique = int(tab[label_col].astype(str).nunique()) if label_col else 999
    score_unique = int(g.round(2).nunique())
    variance = float(g.var()) if len(g) > 1 else 0.0
    greedy_change = float((g.max() - g.min()) / max(abs(g.mean()), 1e-9) * 100) if len(g) else 0.0
    knn_change = float((k.max() - k.min()) / max(abs(k.mean()), 1e-9) * 100) if len(k) else 0.0
    constant = (score_unique <= 1 or label_unique <= 1) and len(tab) > 3
    movement = _clip(greedy_change * 4 + min(30, variance) * 2 + (0 if constant else 25))
    reliability = _clip(35 + movement * .55 - (35 if constant else 0))
    return {
        "Hourly Priority Variance": round(variance, 2),
        "Greedy Score Change %": round(greedy_change, 1),
        "KNN Score Change %": round(knn_change, 1),
        "Constant Score Warning": "Priority unreliable / constant score detected" if constant else "NO — priority moves by hour",
        "Priority Movement Score": round(movement, 1),
        "Dynamic Priority Reliability": round(reliability, 1),
    }, tab


def _mfe_mae(d: pd.DataFrame, regime: str) -> Dict[str, Any]:
    if len(d) < 20:
        return {"Maximum Favorable Excursion": 0.0, "Maximum Adverse Excursion": 0.0, "Average MAE before winning trades": 0.0, "Average MFE before reversal": 0.0, "Safer TP Zone": "NO DATA", "Danger SL Zone": "NO DATA", "Exit Early / Hold / Protect Profit": "WAIT", "Day-trading TP/SL risk explanation": "Need more H1 history."}
    x = d.tail(700).reset_index(drop=True)
    direction = _direction_from_regime(regime)
    if direction == "WAIT":
        direction = "BUY" if x["close"].iloc[-1] >= x["close"].iloc[max(0, len(x)-24)] else "SELL"
    horizon = 6
    rows = []
    for i in range(0, len(x) - horizon):
        entry = float(x.loc[i, "close"])
        fut = x.iloc[i + 1:i + 1 + horizon]
        if direction == "SELL":
            mfe = (entry - float(fut["low"].min())) * 10000
            mae = (float(fut["high"].max()) - entry) * 10000
            final = (entry - float(fut["close"].iloc[-1])) * 10000
        else:
            mfe = (float(fut["high"].max()) - entry) * 10000
            mae = (entry - float(fut["low"].min())) * 10000
            final = (float(fut["close"].iloc[-1]) - entry) * 10000
        rows.append((mfe, mae, final))
    arr = np.array(rows, dtype=float)
    if arr.size == 0:
        return {"Maximum Favorable Excursion": 0.0, "Maximum Adverse Excursion": 0.0, "Average MAE before winning trades": 0.0, "Average MFE before reversal": 0.0, "Safer TP Zone": "NO DATA", "Danger SL Zone": "NO DATA", "Exit Early / Hold / Protect Profit": "WAIT", "Day-trading TP/SL risk explanation": "No future windows in history."}
    winning = arr[arr[:, 2] > 0]
    reversal = arr[(arr[:, 0] > 0) & (arr[:, 2] <= 0)]
    avg_mae_win = float(np.nanmean(winning[:, 1])) if len(winning) else float(np.nanmean(arr[:, 1]))
    avg_mfe_rev = float(np.nanmean(reversal[:, 0])) if len(reversal) else float(np.nanmean(arr[:, 0]))
    max_mfe = float(np.nanpercentile(arr[:, 0], 90))
    max_mae = float(np.nanpercentile(arr[:, 1], 90))
    tp1, tp2 = max(1.0, avg_mfe_rev * .55), max(2.0, avg_mfe_rev * .85)
    sl = max(1.5, avg_mae_win * 1.15)
    action = "Protect Profit" if avg_mfe_rev < max_mae * .8 else "Hold" if max_mfe > max_mae * 1.25 else "Exit Early"
    return {
        "Maximum Favorable Excursion": round(max_mfe, 1),
        "Maximum Adverse Excursion": round(max_mae, 1),
        "Average MAE before winning trades": round(avg_mae_win, 1),
        "Average MFE before reversal": round(avg_mfe_rev, 1),
        "Safer TP Zone": f"{tp1:.1f} → {tp2:.1f} pips",
        "Danger SL Zone": f"above {sl:.1f} pips adverse move",
        "Exit Early / Hold / Protect Profit": action,
        "Day-trading TP/SL risk explanation": "TP should sit before average reversal MFE; SL danger starts beyond MAE that winners usually survive.",
    }


def _pressure_proxy(d: pd.DataFrame) -> Dict[str, Any]:
    if d.empty:
        return {"Buy Pressure Proxy": 0.0, "Sell Pressure Proxy": 0.0, "Spread Stress Proxy": 0.0, "Inventory Pressure Proxy": 0.0, "Liquidity Stress": 0.0, "Mean Reversion Pressure": 0.0}
    x = d.tail(72).copy()
    rng = (x["high"] - x["low"]).replace(0, np.nan)
    body = (x["close"] - x["open"])
    lower_wick = (x[["open", "close"]].min(axis=1) - x["low"]).clip(lower=0)
    upper_wick = (x["high"] - x[["open", "close"]].max(axis=1)).clip(lower=0)
    buy = _clip(50 + (body / rng).fillna(0).tail(24).mean() * 35 + (lower_wick / rng).fillna(0).tail(24).mean() * 30)
    sell = _clip(50 - (body / rng).fillna(0).tail(24).mean() * 35 + (upper_wick / rng).fillna(0).tail(24).mean() * 30)
    atr = _atr(x, 24).replace(0, np.nan)
    spread = _clip(((rng.iloc[-1] / max(float(atr.iloc[-1]), 1e-9)) - 1) * 50 + 50)
    pos = ((x["close"].iloc[-1] - x["low"].tail(24).min()) / max(x["high"].tail(24).max() - x["low"].tail(24).min(), 1e-9)) * 100
    liq = _clip(spread * .55 + abs(body.tail(6).sum()) / max(float(atr.tail(24).mean()), 1e-9) * 15)
    ma = x["close"].rolling(20, min_periods=5).mean().iloc[-1]
    mrev = _clip(abs(x["close"].iloc[-1] - ma) / max(float(atr.iloc[-1]), 1e-9) * 35)
    return {"Buy Pressure Proxy": round(buy, 1), "Sell Pressure Proxy": round(sell, 1), "Spread Stress Proxy": round(spread, 1), "Inventory Pressure Proxy": round(_clip(pos), 1), "Liquidity Stress": round(liq, 1), "Mean Reversion Pressure": round(mrev, 1)}


def _wasserstein_style(a: pd.Series, b: pd.Series) -> float:
    a = pd.to_numeric(a, errors="coerce").dropna()
    b = pd.to_numeric(b, errors="coerce").dropna()
    if len(a) < 5 or len(b) < 5:
        return 0.0
    qs = np.linspace(.05, .95, 19)
    qa = np.quantile(a, qs)
    qb = np.quantile(b, qs)
    scale = max(float(np.nanstd(b)), 1e-9)
    return float(np.mean(np.abs(qa - qb)) / scale * 100)


def _drift(d: pd.DataFrame, regime: str) -> Dict[str, Any]:
    if len(d) < 40:
        return {"Today vs Last 25 Days Similarity": 0.0, "Current Return Distribution Shift": 0.0, "Volatility Distribution Shift": 0.0, "Regime Distribution Shift": 0.0, "Drift Warning": "Dangerous"}
    ret = _returns(d)
    today_date = d["time"].iloc[-1].date()
    today = ret[d["time"].dt.date == today_date]
    last25 = ret[d["time"] >= d["time"].iloc[-1] - pd.Timedelta(days=25)]
    baseline = last25[d["time"].dt.date != today_date]
    rshift = _clip(_wasserstein_style(today, baseline))
    vol_t = today.rolling(6, min_periods=2).std().dropna()
    vol_b = baseline.rolling(6, min_periods=2).std().dropna()
    vshift = _clip(_wasserstein_style(vol_t, vol_b))
    current_dir = _direction_from_regime(regime)
    sign = "BUY" if today.sum() > 0 else "SELL" if today.sum() < 0 else "WAIT"
    reg_shift = 20 if current_dir == sign or current_dir == "WAIT" else 70
    total = _clip(rshift * .45 + vshift * .35 + reg_shift * .20)
    return {"Today vs Last 25 Days Similarity": round(100 - total, 1), "Current Return Distribution Shift": round(rshift, 1), "Volatility Distribution Shift": round(vshift, 1), "Regime Distribution Shift": round(reg_shift, 1), "Drift Warning": _drift_label(total)}


def _factor_dashboard(d: pd.DataFrame, regime_rel: float, priority_rel: float) -> Dict[str, Any]:
    if len(d) < 30:
        return {"Trend Factor": 0.0, "Volatility Factor": 0.0, "Reversal Factor": 0.0, "Compression Factor": 0.0, "Noise Factor": 100.0, "Factor Stability": 0.0}
    ret = _returns(d)
    atr = _atr(d, 24)
    trend = _clip(50 + ret.tail(24).mean() * 90000)
    vol_now = float(ret.tail(24).std())
    vol_base = max(float(ret.tail(240).std()), 1e-9)
    vol = _clip(vol_now / vol_base * 50)
    x = d.tail(40)
    rng = (x["high"] - x["low"]).replace(0, np.nan)
    wick = ((x["high"] - x[["open", "close"]].max(axis=1)) + (x[["open", "close"]].min(axis=1) - x["low"])) / rng
    reversal = _clip(float(wick.fillna(0).tail(12).mean()) * 100)
    compression = _clip(100 - float(atr.tail(12).mean() / max(float(atr.tail(120).mean()), 1e-9)) * 50)
    noise = _clip(100 - abs(trend - 50) + reversal * .25)
    stability = _clip(regime_rel * .38 + priority_rel * .34 + (100 - noise) * .16 + compression * .12)
    return {"Trend Factor": round(trend, 1), "Volatility Factor": round(vol, 1), "Reversal Factor": round(reversal, 1), "Compression Factor": round(compression, 1), "Noise Factor": round(noise, 1), "Factor Stability": round(stability, 1)}


def _anomaly(d: pd.DataFrame) -> Dict[str, Any]:
    if len(d) < 40:
        return {"Anomaly Score": 100.0, "Shock Risk": 100.0, "Strange Candle Pattern Warning": "NO DATA", "Abnormal Volatility Warning": "NO DATA", "Abnormal Direction Change Warning": "NO DATA", "Similar Anomaly History Result": "Need more history"}
    ret = _returns(d)
    rng = (d["high"] - d["low"]).abs()
    rz = abs((ret.iloc[-1] - ret.tail(240).mean()) / max(float(ret.tail(240).std()), 1e-9))
    vz = abs((rng.iloc[-1] - rng.tail(240).mean()) / max(float(rng.tail(240).std()), 1e-9))
    flips = (np.sign(ret.tail(12)).diff().abs() > 0).sum()
    flip_score = _clip(flips / 11 * 100)
    score = _clip(max(rz, vz) * 22 + flip_score * .25)
    shock = _clip(vz * 25 + max(0, rz - 1) * 15)
    candle_range = max(float(rng.iloc[-1]), 1e-9)
    body = abs(float(d["close"].iloc[-1] - d["open"].iloc[-1]))
    strange = body / candle_range < .18 or body / candle_range > .82
    hist_hits = int(((abs((ret - ret.tail(240).mean()) / max(float(ret.tail(240).std()), 1e-9)) > 2.5) | (abs((rng - rng.tail(240).mean()) / max(float(rng.tail(240).std()), 1e-9)) > 2.5)).tail(25 * 24).sum())
    return {"Anomaly Score": round(score, 1), "Shock Risk": round(shock, 1), "Strange Candle Pattern Warning": "YES" if strange else "NO", "Abnormal Volatility Warning": "YES" if vz > 2.2 else "NO", "Abnormal Direction Change Warning": "YES" if flip_score > 65 else "NO", "Similar Anomaly History Result": f"{hist_hits} similar shock/anomaly candles in last 25D", "Action": "Avoid / wait for confirmation" if score >= 65 or shock >= 65 else "Normal confirmation enough"}


def _error_from_state(flat: Dict[str, Any], aliases: Iterable[str], default: float) -> float:
    val = _find_state(flat, aliases, None)
    if val is not None:
        x = _num(val, default)
        return x if x <= 100 else default
    return default


def _forecast_freshness(d: pd.DataFrame, flat: Dict[str, Any], data_age: float) -> Dict[str, Any]:
    built = st.session_state.get("lunch_metric_result_built_at") or st.session_state.get("reliability_last_forecast_built_at")
    age_h = data_age
    if built:
        try:
            bt = pd.to_datetime(built, errors="coerce")
            if pd.notna(bt):
                try:
                    bt = bt.tz_localize(None) if getattr(bt, "tzinfo", None) else bt
                except Exception:
                    pass
                age_h = max(0.0, (pd.Timestamp.now() - bt).total_seconds() / 3600.0)
        except Exception:
            pass
    err2 = _error_from_state(flat, ["last_2_day_error", "2dayerror", "last2error", "avg_abs_close_error_pct"], 4.5)
    err25 = _error_from_state(flat, ["last_25_day_error", "25dayerror", "avg_abs_close_error_pct", "close_error_pct"], 5.5)
    decay = _clip(age_h * 3.5 + err2 * 2.5 + err25 * 1.5)
    freshness = _clip(100 - age_h * 8)
    conf = _clip(100 - decay)
    return {"Forecast Age": f"{age_h:.1f}h", "Prediction Freshness": round(freshness, 1), "Reliability Decay %": round(decay, 1), "Last 2-Day Error": round(err2, 2), "Last 25-Day Error": round(err25, 2), "Decayed Confidence Score": round(conf, 1)}


def _canonical_reliability_context(existing: Dict[str, Any], canonical: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay one operational reliability result on existing component detail."""
    ctx = dict(existing or {})
    reliability = canonical.get("reliability", {}) if isinstance(canonical.get("reliability"), dict) else {}
    final = canonical.get("final_decision", {}) if isinstance(canonical.get("final_decision"), dict) else {}
    drift = canonical.get("drift", {}) if isinstance(canonical.get("drift"), dict) else {}
    quality = canonical.get("data_quality", {}) if isinstance(canonical.get("data_quality"), dict) else {}
    score = _clip(reliability.get("score", 0))
    blockers = list(final.get("blocking_reasons") or [])
    ctx["summary"] = {
        "Forecast Robustness Score": round(score, 1),
        "Reliability Label": str(reliability.get("status") or _label(score)),
        "Main Weakness": blockers[0] if blockers else "No canonical blocker",
        "Best Action Now": final.get("tradeability_decision", "WAIT"),
        "Why priority changed": "Uses the canonical Full Metric priority table; no local priority recalculation.",
        "Why regime is trusted or not trusted": f"Canonical regime reliability {canonical.get('regime_reliability', score)}; drift {drift.get('status', 'UNKNOWN')}.",
    }
    ctx["data_quality_market_feed_health"] = {
        "Data Quality Status": quality.get("status", "UNKNOWN"),
        "Data Quality Score": quality.get("score", 0),
        "Warnings": quality.get("warnings", []),
        "Blocking Reasons": quality.get("blocking_reasons", []),
    }
    ctx["regime_state_reliability"] = {
        "Current Regime": canonical.get("current_major_regime", (canonical.get("regime") or {}).get("major_regime", "UNKNOWN")),
        "Regime Reliability Score": canonical.get("regime_reliability", score),
        "Canonical Direction": canonical.get("full_metric_direction", final.get("directional_market_view", "WAIT")),
        "Tradeability Decision": final.get("tradeability_decision", "WAIT"),
    }
    ctx["distribution_shift_wasserstein_style_drift"] = {**ctx.get("distribution_shift_wasserstein_style_drift", {}), **drift}
    ctx["canonical_reliability_components"] = reliability
    ctx["priority_table_preview"] = list(canonical.get("canonical_priority_table") or canonical.get("priority_table") or [])[:24]
    ctx["run_id"] = canonical.get("run_id")
    ctx["calculation_generation"] = canonical.get("calculation_generation")
    ctx["data_signature"] = canonical.get("data_signature")
    ctx["symbol"] = canonical.get("symbol")
    ctx["timeframe"] = canonical.get("timeframe")
    ctx["latest_completed_candle_time"] = canonical.get("latest_completed_candle_time")
    ctx["built_at"] = canonical.get("created_at")
    ctx["canonical_read_only"] = True
    return ctx


def _build_context(ns: dict, force: bool = False) -> Dict[str, Any]:
    canonical = st.session_state.get("canonical_decision_result_20260617")
    main_run_staging = isinstance(st.session_state.get("calculation_staging_ohlc_df_20260617"), pd.DataFrame)
    if isinstance(canonical, dict) and canonical and not (force and main_run_staging):
        existing = st.session_state.get("reliability_control_center_20260614")
        ctx = _canonical_reliability_context(existing if isinstance(existing, dict) else {}, canonical)
        st.session_state["reliability_control_center_20260614"] = ctx
        canonical_table = st.session_state.get("canonical_priority_table_20260617")
        if isinstance(canonical_table, pd.DataFrame):
            st.session_state["reliability_dynamic_priority_table_20260614"] = canonical_table
        return ctx
    if not force and isinstance(st.session_state.get("reliability_control_center_20260614"), dict):
        return st.session_state["reliability_control_center_20260614"]
    d = _market_df()
    flat = _flat_state()
    leak = _feature_leakage_guard(d)
    quality = _data_quality(d)
    regime = _regime_reliability(ns, d, flat)
    priority, priority_table = _priority_anti_constant(ns, d, flat)
    mfe = _mfe_mae(d, regime.get("Current Regime", "RANGE_NORMAL"))
    pressure = _pressure_proxy(d)
    drift = _drift(d, regime.get("Current Regime", "RANGE_NORMAL"))
    factor = _factor_dashboard(d, _num(regime.get("Regime Reliability Score"), 55), _num(priority.get("Dynamic Priority Reliability"), 55))
    anomaly = _anomaly(d)
    freshness = _forecast_freshness(d, flat, _num(quality.get("_age_hours"), 999))

    leak_pen = _num(leak.get("Leakage Risk %")) * .22
    drift_pen = 0 if drift.get("Drift Warning") == "Normal" else 12 if drift.get("Drift Warning") == "Caution" else 24
    anomaly_pen = max(0, _num(anomaly.get("Anomaly Score")) - 50) * .28
    robustness = _clip(
        _num(quality.get("Data Quality Score")) * .20
        + _num(regime.get("Regime Reliability Score")) * .18
        + _num(priority.get("Dynamic Priority Reliability")) * .17
        + _num(factor.get("Factor Stability")) * .13
        + _num(freshness.get("Decayed Confidence Score")) * .17
        + _num(drift.get("Today vs Last 25 Days Similarity")) * .15
        - leak_pen - drift_pen - anomaly_pen
    )
    weak_map = {
        "feature leakage": 100 - _num(leak.get("Leakage Risk %")),
        "data quality": _num(quality.get("Data Quality Score")),
        "regime reliability": _num(regime.get("Regime Reliability Score")),
        "priority movement": _num(priority.get("Dynamic Priority Reliability")),
        "distribution drift": _num(drift.get("Today vs Last 25 Days Similarity")),
        "forecast freshness": _num(freshness.get("Decayed Confidence Score")),
        "anomaly/shock": 100 - _num(anomaly.get("Anomaly Score")),
    }
    main_weakness = min(weak_map, key=weak_map.get)
    if robustness >= 80 and anomaly.get("Action") != "Avoid / wait for confirmation":
        action = "Trade only if entry table and regime agree"
    elif robustness >= 65:
        action = "Small size / wait for confirmation"
    else:
        action = "Avoid / wait for cleaner signal"
    summary = {
        "Forecast Robustness Score": round(robustness, 1),
        "Reliability Label": _label(robustness),
        "Main Weakness": main_weakness,
        "Best Action Now": action,
        "Why priority changed": priority.get("Constant Score Warning", "priority movement measured") + f"; movement {priority.get('Priority Movement Score')}.",
        "Why regime is trusted or not trusted": f"{regime.get('Regime Trusted?')} — confidence {regime.get('Regime Confidence %')}%, shift risk {regime.get('Regime Shift Risk')}%.",
    }
    ctx = {
        "summary": summary, "feature_leakage_guard": leak, "data_quality_market_feed_health": {k: v for k, v in quality.items() if not str(k).startswith("_")},
        "regime_state_reliability": regime, "priority_anti_constant_engine": priority,
        "mfe_mae_exit_control": mfe, "market_maker_pressure_proxy": pressure,
        "distribution_shift_wasserstein_style_drift": drift, "pca_factor_structure_dashboard": factor,
        "anomaly_and_shock_detector": anomaly, "model_decay_forecast_freshness": freshness,
        "priority_table_preview": priority_table.tail(24).to_dict("records") if isinstance(priority_table, pd.DataFrame) and not priority_table.empty else [],
        "built_at": str(pd.Timestamp.now()), "rows_used": int(len(d)),
    }
    st.session_state["reliability_control_center_20260614"] = ctx
    st.session_state["reliability_dynamic_priority_table_20260614"] = priority_table
    return ctx


def _table(title: str, data: Dict[str, Any]) -> None:
    st.markdown(f"#### {title}")
    rows = [{"Check": k, "Value": v} for k, v in data.items()]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _copy_text(ns: dict, compact: bool = False) -> str:
    ctx = _build_context(ns, force=True) if bool(st.session_state.get("metric_run_calculate", False)) else {"summary": {"Status": "Press Run Calculating first"}}
    if compact:
        s = ctx.get("summary", {})
        keep = {"Reliability Control Center Summary": s, "Data Quality": ctx.get("data_quality_market_feed_health", {}), "Regime": ctx.get("regime_state_reliability", {}), "Priority": ctx.get("priority_anti_constant_engine", {})}
        return "\n\nRELIABILITY CONTROL CENTER — SHORT\n" + json.dumps(keep, indent=2, default=str)
    return "\n\nRELIABILITY CONTROL CENTER — FULL\n" + json.dumps(ctx, indent=2, default=str)


def render(ns: dict) -> None:
    with st.expander("🛡️ Open / Close — Reliability Control Center", expanded=False):
        st.caption("Manual-run, display-only reliability layer. Uses existing OHLC/history/regime/priority/forecast metrics; no external API, no heavy model, no new prediction engine.")
        if not bool(st.session_state.get("metric_run_calculate", False)):
            st.info("Press **Run Calculating** first. Reliability Control Center stays idle so Home/Lunch remains fast on iPhone 11 Pro.")
            return
        if st.button("▶ Refresh Reliability Control Center", key=f"refresh_{UNIQUE}", use_container_width=True):
            st.session_state.pop("reliability_control_center_20260614", None)
        ctx = _build_context(ns, force=False)
        s = ctx.get("summary", {})
        c = st.columns(4)
        c[0].metric("Forecast Robustness", _safe_metric(s.get("Forecast Robustness Score"), "%"))
        c[1].metric("Reliability Label", s.get("Reliability Label", "-"))
        c[2].metric("Main Weakness", s.get("Main Weakness", "-"))
        c[3].metric("Best Action", s.get("Best Action Now", "-"))
        st.info(f"Priority: {s.get('Why priority changed', '-')}")
        st.caption(f"Regime trust: {s.get('Why regime is trusted or not trusted', '-')}")
        sections = [
            ("1. Feature Leakage Guard", "feature_leakage_guard"),
            ("2. Data Quality + Market Feed Health", "data_quality_market_feed_health"),
            ("3. Regime State Reliability", "regime_state_reliability"),
            ("4. Priority Anti-Constant Engine", "priority_anti_constant_engine"),
            ("5. MFE / MAE Exit Control", "mfe_mae_exit_control"),
            ("6. Market Maker Pressure Proxy", "market_maker_pressure_proxy"),
            ("7. Distribution Shift / Wasserstein-style Drift", "distribution_shift_wasserstein_style_drift"),
            ("8. PCA / Factor Structure Dashboard", "pca_factor_structure_dashboard"),
            ("9. Anomaly and Shock Detector", "anomaly_and_shock_detector"),
            ("10. Model Decay / Forecast Freshness", "model_decay_forecast_freshness"),
        ]
        for title, key in sections:
            _table(title, ctx.get(key, {}))
        ptab = st.session_state.get("reliability_dynamic_priority_table_20260614")
        if isinstance(ptab, pd.DataFrame) and not ptab.empty:
            st.markdown("#### Dynamic hourly priority preview")
            st.caption("Shows changing hourly priority made from existing rows/metrics only. It does not replace any prediction engine.")
            st.dataframe(ptab.tail(24), use_container_width=True, hide_index=True)


def install(ns: dict) -> None:
    if ns.get("_reliability_control_center_installed_20260614"):
        return
    prev_full = ns.get("_build_lunch_all_copy_text")
    prev_short = ns.get("_build_short_necessary_copy_text")

    def _build_full_with_reliability() -> str:
        base = prev_full() if callable(prev_full) else ""
        return str(base) + _copy_text(ns, compact=False)

    def _build_short_with_reliability() -> str:
        base = prev_short() if callable(prev_short) else ""
        return str(base) + _copy_text(ns, compact=True)

    if callable(prev_full):
        ns["_build_lunch_all_copy_text"] = _build_full_with_reliability
    if callable(prev_short):
        ns["_build_short_necessary_copy_text"] = _build_short_with_reliability
    ns["render_reliability_control_center_20260614"] = lambda: render(ns)
    ns["build_reliability_control_center_20260614"] = lambda force=False: _build_context(ns, force=force)
    ns["_reliability_control_center_installed_20260614"] = True
