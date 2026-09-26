# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""ADX shared calculation sync and safety calibration patch (2026-06-15).

Additive, non-destructive module.

Purpose
-------
Create one shared calculation result that every existing page can read without
moving, deleting, or replacing old tab logic.  The module only reads existing
session_state outputs and OHLC data, derives calibration/validation summaries,
and writes new shared keys back to session_state.  It never trains a new model,
never changes the original PowerBI/ML/regime formulas, and never removes any
old table/chart/copy/export key.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # pandas/numpy are project requirements, but import defensively.
    import numpy as np
    import pandas as pd
except Exception:  # pragma: no cover
    np = None  # type: ignore
    pd = None  # type: ignore

UNIQUE = "20260615_shared_sync"
SHARED_KEY = "adx_shared_calc_result_20260615"
LEGACY_SHARED_KEY = "shared_calc_result"
MAX_MOBILE_ROWS = 120
MAX_DESKTOP_ROWS = 360


# ---------------------------------------------------------------------------
# Safe primitives
# ---------------------------------------------------------------------------
def _now_text() -> str:
    try:
        if pd is not None:
            return str(pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass
    return str(int(time.time()))


def _safe_num(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if v is None or v == "":
            return default
        if isinstance(v, str):
            m = re.search(r"-?\d+(?:\.\d+)?", v.replace(",", ""))
            if not m:
                return default
            v = m.group(0)
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _clip(v: Any, lo: float = 0.0, hi: float = 100.0, default: float = 0.0) -> float:
    x = _safe_num(v, default)
    if x is None:
        x = default
    return float(max(lo, min(hi, x)))


def _norm_key(v: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(v or "").lower())


def _is_df(obj: Any) -> bool:
    try:
        return pd is not None and isinstance(obj, pd.DataFrame) and not obj.empty
    except Exception:
        return False


def _find_col(df: Any, aliases: Iterable[str]) -> Optional[str]:
    if not _is_df(df):
        return None
    try:
        nmap = {_norm_key(c): c for c in df.columns}
        for a in aliases:
            na = _norm_key(a)
            if na in nmap:
                return nmap[na]
        for nk, col in nmap.items():
            for a in aliases:
                na = _norm_key(a)
                if na and na in nk:
                    return col
    except Exception:
        pass
    return None


def _series_num(df: Any, aliases: Iterable[str], default: float = 0.0):
    if pd is None or not _is_df(df):
        return pd.Series(dtype=float) if pd is not None else []
    col = _find_col(df, aliases)
    try:
        if col is None:
            return pd.Series(default, index=df.index, dtype=float)
        return pd.to_numeric(df[col], errors="coerce").fillna(default).astype(float)
    except Exception:
        return pd.Series(default, index=df.index, dtype=float)


def _safe_tail_df(df: Any, rows: int):
    if not _is_df(df):
        return pd.DataFrame() if pd is not None else None
    try:
        return df.tail(int(max(1, rows))).copy()
    except Exception:
        try:
            return df.copy()
        except Exception:
            return pd.DataFrame() if pd is not None else None


def _json_safe(obj: Any, rows: int = 80) -> Any:
    try:
        if pd is not None and isinstance(obj, pd.DataFrame):
            return obj.head(rows).to_dict("records")
        if pd is not None and isinstance(obj, pd.Series):
            return obj.head(rows).to_dict()
        if np is not None and isinstance(obj, (np.integer,)):
            return int(obj)
        if np is not None and isinstance(obj, (np.floating,)):
            x = float(obj)
            return x if math.isfinite(x) else None
        if pd is not None and isinstance(obj, (pd.Timestamp,)):
            return str(obj)
        if isinstance(obj, dict):
            return {str(k): _json_safe(v, rows) for k, v in obj.items() if k not in {"data", "flat"}}
        if isinstance(obj, (list, tuple)):
            return [_json_safe(x, rows) for x in list(obj)[:rows]]
        return obj
    except Exception:
        return str(obj)


def _flatten_dict(obj: Any, prefix: str = "", depth: int = 0, limit: int = 1800) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if depth > 5 or len(out) >= limit:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if len(out) >= limit:
                break
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.update(_flatten_dict(v, key, depth + 1, limit))
            elif not _is_df(v):
                out[key] = v
    return out


def _find_value(flat: Dict[str, Any], aliases: Iterable[str], default: Any = None) -> Any:
    try:
        nmap = {_norm_key(k): v for k, v in flat.items()}
        for a in aliases:
            na = _norm_key(a)
            if na in nmap:
                return nmap[na]
        for nk, v in nmap.items():
            for a in aliases:
                na = _norm_key(a)
                if na and na in nk:
                    return v
    except Exception:
        pass
    return default


def _first_df_from_state(st: Any, keys: Iterable[str]):
    if pd is None:
        return None
    for key in keys:
        try:
            obj = st.session_state.get(key)
            if _is_df(obj):
                return obj
        except Exception:
            pass
    return pd.DataFrame()


def _df_signature(df: Any) -> str:
    if not _is_df(df):
        return "empty"
    try:
        cols = list(map(str, df.columns[:20]))
        rows = len(df)
        tail = df.tail(3).to_json(default_handler=str)
        return hashlib.md5((str(rows) + "|" + ",".join(cols) + "|" + tail).encode("utf-8", errors="ignore")).hexdigest()[:14]
    except Exception:
        return f"rows_{len(df)}"


def _direction_from_regime(regime: Any) -> str:
    try:
        from core.decision_policy_20260617 import infer_direction_from_regime
        return infer_direction_from_regime(regime)
    except Exception:
        s = str(regime or "").upper()
        if any(token in s for token in ("BEAR", "DOWNTREND", "EXPANSION_DOWN", "DOWN_EXPANSION")):
            return "SELL"
        if any(token in s for token in ("BULL", "UPTREND", "EXPANSION_UP", "UP_EXPANSION")):
            return "BUY"
        return "WAIT"


def _direction_from_prices(last_close: Any, forecast_close: Any) -> str:
    a = _safe_num(last_close)
    b = _safe_num(forecast_close)
    if a is None or b is None:
        return "WAIT"
    if b > a:
        return "BUY"
    if b < a:
        return "SELL"
    return "WAIT"


# ---------------------------------------------------------------------------
# State collection
# ---------------------------------------------------------------------------
def _collect_flat_state(st: Any) -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    preferred = [
        "dv_pp_base_result", "lunch_5layer_powerbi_result", "dv_pp_regime_summary", "dv_pp_bt_summary",
        "final_merged_intelligence_pack_20260612", "final_synced_research_merge_pack_20260612",
        "reliability_control_center_20260614", "regime_context_20260614", "nylo_unified_home_sync_20260612",
        "news_nlp_knn_greedy_pack_20260612", "quant_structure_pack_20260612", "research_pack_20260612",
        "lunch_prediction_export", "lunch_metric_result_cache", "last_result", "current_result", SHARED_KEY,
    ]
    try:
        sensitive = ("api_key", "apikey", "token", "secret", "password", "finnhub")
        for key in preferred:
            if any(marker in str(key).lower() for marker in sensitive):
                continue
            v = st.session_state.get(key)
            if isinstance(v, dict):
                flat.update(_flatten_dict(v, key))
        for k, v in list(st.session_state.items()):
            if len(flat) > 2400:
                break
            key_text = str(k)
            if any(marker in key_text.lower() for marker in sensitive):
                continue
            if isinstance(v, dict):
                flat.update(_flatten_dict(v, key_text, limit=2400))
            elif isinstance(v, (str, int, float, bool)) and len(str(v)) < 180:
                flat[key_text] = v
    except Exception:
        pass
    return flat


def _collect_core_data(st: Any, phone_mode: bool) -> Dict[str, Any]:
    rows = MAX_MOBILE_ROWS if phone_mode else MAX_DESKTOP_ROWS
    ohlc = _first_df_from_state(st, ["calculation_staging_ohlc_df_20260617", "canonical_completed_ohlc_df_20260617", "dv_pp_df", "lunch_5layer_powerbi_df", "last_df", "ohlc_df", "df", "ws_ticks"])
    predicted = _first_df_from_state(st, ["dv_pp_predicted", "dv_pp_lightblue_path", "prediction_path_df", "predicted_df", "forecast_df"])
    bt_hist = _first_df_from_state(st, ["dv_pp_bt_hist", "prediction_history_df", "prediction_vs_actual_history_df", "dv_pp_projection_history"])
    regime_hist = _first_df_from_state(st, ["dv_pp_regime_hist", "regime_history_df", "major_regime_history_df", "lunch_regime_history"])
    original_priority = _first_df_from_state(st, [
        "three_center_priority_sorted_20260614",
        "reliability_dynamic_priority_table_20260614",
        "priority_table_df", "knn_greedy_priority_table",
    ])
    priority = original_priority if _is_df(original_priority) else _first_df_from_state(st, ["adx_hourly_priority_calibrated_20260615"])
    return {
        "ohlc": _safe_tail_df(ohlc, rows),
        "predicted": _safe_tail_df(predicted, min(rows, 80)),
        "bt_hist": _safe_tail_df(bt_hist, rows),
        "regime_hist": _safe_tail_df(regime_hist, rows),
        "priority": _safe_tail_df(priority, rows),
        "source_signature": "|".join([
            _df_signature(ohlc), _df_signature(predicted), _df_signature(bt_hist), _df_signature(regime_hist),
            str(st.session_state.get("metric_run_calculate", False)),
            str(st.session_state.get("run_data_visualization_antd_20260615", False)),
        ]),
    }


# ---------------------------------------------------------------------------
# Derived engines: data quality, feedback, reliability, regime alpha/delta,
# priority table, AI grounding.
# ---------------------------------------------------------------------------
def _data_quality(df: Any) -> Dict[str, Any]:
    if not _is_df(df):
        return {"ok": False, "score": 15.0, "rows": 0, "message": "No OHLC dataframe available yet."}
    rows = int(len(df))
    close_col = _find_col(df, ["close", "c"])
    time_col = _find_col(df, ["time", "datetime", "timestamp", "date"])
    null_pct = 0.0
    dup_pct = 0.0
    monotonic_ok = True
    try:
        use = [c for c in [time_col, close_col, _find_col(df, ["open"]), _find_col(df, ["high"]), _find_col(df, ["low"])] if c]
        if use:
            null_pct = float(df[use].isna().mean().mean() * 100.0)
        if time_col:
            t = pd.to_datetime(df[time_col], errors="coerce")
            dup_pct = float(t.duplicated().mean() * 100.0)
            monotonic_ok = bool(t.dropna().is_monotonic_increasing)
    except Exception:
        pass
    score = 100.0
    if rows < 30:
        score -= 35.0
    elif rows < 80:
        score -= 15.0
    if close_col is None:
        score -= 40.0
    score -= min(35.0, null_pct * 2.0)
    score -= min(25.0, dup_pct * 3.0)
    if not monotonic_ok:
        score -= 8.0
    score = _clip(score, 0, 100, 50)
    return {
        "ok": bool(score >= 55 and close_col is not None),
        "score": round(score, 2),
        "rows": rows,
        "close_col": close_col or "",
        "time_col": time_col or "",
        "null_pct": round(null_pct, 3),
        "duplicate_time_pct": round(dup_pct, 3),
        "monotonic_time": bool(monotonic_ok),
        "default_display_rows": MAX_MOBILE_ROWS,
        "message": "OK" if score >= 55 else "Low data quality / limited rows. Reliability is capped.",
    }


def _prediction_feedback(flat: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    hist = data.get("bt_hist")
    pred_df = data.get("predicted")
    ohlc = data.get("ohlc")
    avg_error = _safe_num(_find_value(flat, ["avg_abs_close_error_pct", "prediction_error_pct", "close_error_pct", "prediction_vs_actual_error"], None))
    direction_acc = _safe_num(_find_value(flat, ["direction_accuracy_pct", "direction_accuracy", "Direction Accuracy %"], None))
    samples = 0
    method = "session-summary"
    try:
        if _is_df(hist):
            pred_col = _find_col(hist, ["predicted", "prediction", "forecast", "previous_predicted_path", "predicted_close", "forecast_close"])
            actual_col = _find_col(hist, ["actual", "actual_close", "close"])
            if pred_col and actual_col:
                p = pd.to_numeric(hist[pred_col], errors="coerce")
                a = pd.to_numeric(hist[actual_col], errors="coerce")
                mask = p.notna() & a.notna() & (a.abs() > 1e-12)
                if mask.any():
                    err = ((p[mask] - a[mask]).abs() / a[mask].abs() * 100.0)
                    avg_error = float(err.tail(80).mean())
                    samples = int(mask.sum())
                    method = "prediction-vs-actual-history"
                    try:
                        da = (p.diff()[mask].apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0) == a.diff()[mask].apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)).mean() * 100.0
                        if math.isfinite(float(da)):
                            direction_acc = float(da)
                    except Exception:
                        pass
    except Exception:
        pass
    if avg_error is None or float(avg_error) <= 1e-9:
        # Use recent volatility as an honest proxy until enough old prediction
        # vs actual rows exist. This is not a new prediction engine.
        try:
            c = _series_num(ohlc, ["close", "c"]).replace(0, np.nan)
            ret = c.pct_change().abs() * 100.0
            avg_error = float(ret.tail(48).mean()) if len(ret.dropna()) else 0.15
            method = "volatility-proxy-until-feedback-history-exists"
        except Exception:
            avg_error = 0.15
    if direction_acc is None:
        direction_acc = 50.0
    error_penalty = _clip((avg_error or 0.0) * 450.0, 0, 60, 0)
    reliability_cap = _clip(100.0 - error_penalty, 35, 100, 70)
    return {
        "method": method,
        "samples": int(samples),
        "avg_abs_close_error_pct": round(float(avg_error or 0.0), 5),
        "direction_accuracy_pct": round(_clip(direction_acc, 0, 100, 50), 2),
        "error_penalty": round(error_penalty, 2),
        "reliability_cap_from_feedback": round(reliability_cap, 2),
        "feedback_loop_status": "history-calibrated" if samples >= 10 else "proxy / needs more completed prediction-vs-actual rows",
    }


def _extract_current_summary(flat: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    ohlc = data.get("ohlc")
    pred = data.get("predicted")
    close_col = _find_col(ohlc, ["close", "c"])
    pred_close_col = _find_col(pred, ["close", "predicted_close", "forecast_close", "estimated_price_close", "price"])
    last_close = None
    forecast_close = _safe_num(_find_value(flat, ["estimated_price_close", "forecast_close", "prediction_close", "next_close"], None))
    try:
        if close_col:
            last_close = float(pd.to_numeric(ohlc[close_col], errors="coerce").dropna().iloc[-1])
        if forecast_close is None and pred_close_col:
            forecast_close = float(pd.to_numeric(pred[pred_close_col], errors="coerce").dropna().iloc[0])
    except Exception:
        pass
    regime = _find_value(flat, ["current_regime", "regime", "major_regime", "master_regime"], "-")
    try:
        hist = data.get("regime_hist")
        if _is_df(hist):
            rcol = _find_col(hist, ["regime", "current_regime", "major_regime", "master_regime", "label", "state"])
            if rcol:
                vals = hist[rcol].dropna().astype(str).str.strip()
                if len(vals): regime = vals.iloc[-1]
    except Exception:
        pass
    pred_dir = str(_find_value(flat, ["prediction_direction", "forecast_direction"], "") or "").upper()
    if pred_dir not in {"BUY", "SELL", "WAIT"}:
        pred_dir = _direction_from_prices(last_close, forecast_close)
    regime_dir = _direction_from_regime(regime)
    decision = _find_value(flat, ["final_decision", "master_decision", "decision", "best_current_opportunity"], "-")
    entry = _safe_num(_find_value(flat, ["entry_score", "entry strength", "entry /10", "entry pressure"], None))
    hold = _safe_num(_find_value(flat, ["hold_score", "hold safety", "hold /10"], None))
    tp = _safe_num(_find_value(flat, ["tp_score", "tp quality", "tp /10"], None))
    exit_risk = _safe_num(_find_value(flat, ["exit_risk", "exit risk /10", "risk_score"], None))
    forecast_conf = _safe_num(_find_value(flat, ["forecast_confidence", "forecast confidence %", "confidence_pct"], None))
    market_quality = _safe_num(_find_value(flat, ["market_quality", "market_quality_score", "quality_score"], None))
    return {
        "symbol": _find_value(flat, ["symbol", "ticker"], "EURUSD"),
        "timeframe": _find_value(flat, ["timeframe", "tf"], "H1"),
        "last_close": last_close,
        "forecast_close": forecast_close,
        "prediction_direction": pred_dir,
        "regime": str(regime or "-"),
        "regime_direction": regime_dir,
        "decision": str(decision or "-"),
        "entry_score": entry,
        "hold_score": hold,
        "tp_score": tp,
        "exit_risk": exit_risk,
        "forecast_confidence": forecast_conf,
        "market_quality": market_quality,
    }


def _regime_alpha_delta(flat: Dict[str, Any], data: Dict[str, Any], feedback: Dict[str, Any], quality: Dict[str, Any]) -> Dict[str, Any]:
    ohlc = data.get("ohlc")
    hist = data.get("regime_hist")
    current_regime = str(_find_value(flat, ["current_regime", "regime", "major_regime"], "-") or "-")
    previous_regime = "-"
    try:
        if _is_df(hist):
            rcol = _find_col(hist, ["regime", "current_regime", "major_regime", "label"])
            if rcol:
                vals = [str(x) for x in hist[rcol].dropna().astype(str).tolist() if str(x).strip()]
                if vals:
                    current_regime = vals[-1]
                    # Find last different regime as previous.
                    for val in reversed(vals[:-1]):
                        if val != current_regime:
                            previous_regime = val
                            break
    except Exception:
        pass
    alpha_now = 50.0
    alpha_prev = 50.0
    divergence = 0.0
    ratio = 1.0
    try:
        c = _series_num(ohlc, ["close", "c"]).dropna()
        h = _series_num(ohlc, ["high", "h"]).reindex(c.index).fillna(c)
        l = _series_num(ohlc, ["low", "l"]).reindex(c.index).fillna(c)
        if len(c) >= 12:
            ret_now = float((c.iloc[-1] - c.iloc[-6]) / max(abs(c.iloc[-6]), 1e-12) * 100.0)
            ret_prev = float((c.iloc[-7] - c.iloc[-12]) / max(abs(c.iloc[-12]), 1e-12) * 100.0) if len(c) >= 18 else 0.0
            rng = ((h - l).abs() / c.replace(0, np.nan).abs() * 100.0).tail(24).mean()
            vol_adj = max(float(rng or 0.01), 0.01)
            alpha_now = _clip(50 + (ret_now / vol_adj) * 12.0 + (_clip(feedback.get("direction_accuracy_pct"), 0, 100, 50) - 50) * 0.28 + (quality.get("score", 50) - 50) * 0.18, 0, 100, 50)
            alpha_prev = _clip(50 + (ret_prev / vol_adj) * 12.0, 0, 100, 50)
            divergence = alpha_now - alpha_prev
            ratio = alpha_now / max(alpha_prev, 1.0)
    except Exception:
        pass
    delta = alpha_now - alpha_prev
    valid = bool(quality.get("ok") and abs(delta) >= 3.0 and _clip(feedback.get("reliability_cap_from_feedback"), 0, 100, 50) >= 45)
    return {
        "current_regime": current_regime,
        "previous_regime": previous_regime,
        "regime_alpha_now": round(alpha_now, 2),
        "regime_alpha_previous": round(alpha_prev, 2),
        "regime_delta": round(delta, 2),
        "regime_alpha_ratio": round(ratio, 4),
        "regime_divergence_mean": round(divergence, 2),
        "validation_status": "VALID" if valid else "WATCH / NEED MORE CONFIRMATION",
        "rule": "Alpha = current regime strength after feedback + data-quality calibration; Delta = current alpha - previous alpha.",
    }



def _false_reversal_risk(flat: Dict[str, Any], current: Dict[str, Any], reliability: Dict[str, Any]) -> Dict[str, Any]:
    """Score false-reversal exposure from existing causal decision evidence only."""
    strength = _safe_num(_find_value(flat, ["reversal_strength", "reversal strength", "reverse strength"], 0.0), 0.0) or 0.0
    active = _safe_num(_find_value(flat, ["active_10_count", "active 10 count", "active reversal count"], 0.0), 0.0) or 0.0
    probability = _safe_num(_find_value(flat, ["probability_%", "probability %", "reversal probability", "probability_pct"], 0.0), 0.0) or 0.0
    move_ratio = _safe_num(_find_value(flat, ["move_ratio_now_prev", "move ratio now prev", "move ratio"], 1.0), 1.0) or 1.0
    derivative = _safe_num(_find_value(flat, ["direction_derivative", "direction derivative"], 0.0), 0.0) or 0.0
    strength_pct = _clip(strength * 10.0 if abs(strength) <= 10 else strength, 0, 100, 0)
    active_pct = _clip(active * 10.0, 0, 100, 0)
    probability_pct = _clip(probability, 0, 100, 0)
    momentum = _clip(max(0.0, abs(move_ratio) - 1.0) * 24.0 + abs(derivative) * 240.0, 0, 100, 0)
    reversal_confirmation = strength_pct * 0.45 + active_pct * 0.35 + probability_pct * 0.20
    weak_confirmation = 100.0 - reversal_confirmation
    apparent_reversal = probability_pct * 0.60 + strength_pct * 0.40
    regime = str(current.get("regime") or "").upper()
    continuation_regime = 8.0 if any(x in regime for x in ("TREND", "EXPANSION", "BULL", "BEAR")) and "TRANSITION" not in regime else 0.0
    reliability_score = _clip(reliability.get("score"), 0, 100, 50)
    low_evidence_penalty = max(0.0, 55.0 - reliability_score) * 0.22
    raw = momentum * 0.45 + weak_confirmation * 0.32 + apparent_reversal * 0.23 + continuation_regime + low_evidence_penalty
    score = round(_clip(raw / 10.0, 0, 10, 0), 2)
    label = "LOW" if score < 3 else "WATCH" if score < 5 else "CAUTION" if score < 7 else "HIGH"
    reasons = []
    reasons.append("Strong momentum continuation" if momentum >= 55 else "Continuation momentum is limited")
    reasons.append("Weak reversal confirmation" if reversal_confirmation < 50 else "Reversal confirmation is present")
    return {
        "score": score, "label": label, "reason": " • ".join(reasons),
        "inputs": {"reversal_strength": strength, "active_10_count": active, "probability_pct": probability_pct, "move_ratio_now_prev": move_ratio, "direction_derivative": derivative},
        "calculation_source": "central shared existing reversal/regime evidence",
    }

def _calibrated_reliability(current: Dict[str, Any], feedback: Dict[str, Any], quality: Dict[str, Any], alpha_delta: Dict[str, Any]) -> Dict[str, Any]:
    entry = _clip((current.get("entry_score") or 0) * 10 if (current.get("entry_score") or 0) <= 10 else current.get("entry_score"), 0, 100, 50)
    hold = _clip((current.get("hold_score") or 0) * 10 if (current.get("hold_score") or 0) <= 10 else current.get("hold_score"), 0, 100, 50)
    tp = _clip((current.get("tp_score") or 0) * 10 if (current.get("tp_score") or 0) <= 10 else current.get("tp_score"), 0, 100, 50)
    exit_risk = _clip((current.get("exit_risk") or 5) * 10 if (current.get("exit_risk") or 0) <= 10 else current.get("exit_risk"), 0, 100, 50)
    forecast_conf = _clip(current.get("forecast_confidence"), 0, 100, 50)
    market_quality = _clip(current.get("market_quality"), 0, 100, quality.get("score", 50))
    dir_acc = _clip(feedback.get("direction_accuracy_pct"), 0, 100, 50)
    fb_cap = _clip(feedback.get("reliability_cap_from_feedback"), 25, 100, 70)
    data_q = _clip(quality.get("score"), 0, 100, 50)
    alpha_valid = 72.0 if alpha_delta.get("validation_status") == "VALID" else 48.0
    conflict_penalty = 0.0
    if current.get("prediction_direction") in {"BUY", "SELL"} and current.get("regime_direction") in {"BUY", "SELL"} and current.get("prediction_direction") != current.get("regime_direction"):
        conflict_penalty = 12.0
    raw = (
        data_q * 0.20
        + dir_acc * 0.22
        + fb_cap * 0.18
        + forecast_conf * 0.12
        + market_quality * 0.10
        + (100.0 - exit_risk) * 0.08
        + ((entry + hold + tp) / 3.0) * 0.06
        + alpha_valid * 0.04
        - conflict_penalty
    )
    score = _clip(raw, 0, 100, 50)
    # A reliability score should never be higher than the feedback cap + a small buffer.
    score = min(score, fb_cap + 8.0)
    if not quality.get("ok"):
        score = min(score, 55.0)
    grade = "A" if score >= 82 else "B" if score >= 68 else "C" if score >= 52 else "D / Protect"
    return {
        "score": round(score, 2),
        "grade": grade,
        "data_quality_component": round(data_q, 2),
        "direction_accuracy_component": round(dir_acc, 2),
        "feedback_cap": round(fb_cap, 2),
        "conflict_penalty": round(conflict_penalty, 2),
        "calibration_rule": "Score is capped by prediction-vs-actual feedback and lowered by data quality or regime/prediction conflict.",
    }


def _priority_label(score: float) -> str:
    if score >= 90:
        return "A+ Best"
    if score >= 80:
        return "A Strong"
    if score >= 70:
        return "B+ Good"
    if score >= 60:
        return "B Watch"
    if score >= 45:
        return "C Weak"
    return "Avoid"


def _priority_rank(score: float) -> int:
    return int(max(1, min(14, round(15 - _clip(score, 0, 100, 50) / 100.0 * 14))))


def _build_hourly_priority(data: Dict[str, Any], current: Dict[str, Any], reliability: Dict[str, Any], feedback: Dict[str, Any]):
    if pd is None:
        return None
    old = data.get("priority")
    rows: List[Dict[str, Any]] = []
    base_rel = _clip(reliability.get("score"), 0, 100, 55)
    fb_penalty = _clip(feedback.get("error_penalty"), 0, 60, 10)
    if _is_df(old):
        work = old.copy().tail(48).reset_index(drop=True)
        score_col = _find_col(work, ["Greedy Score", "KNN Priority Score", "Priority Score", "Reliability Score", "Score"])
        hour_col = _find_col(work, ["hour", "Hour", "Time", "Datetime", "Timestamp", "Date"])
        base_scores = _series_num(work, [score_col] if score_col else ["__none__"], base_rel)
        for i, (_, row) in enumerate(work.iterrows()):
            hour = "-"
            if hour_col:
                try:
                    t = pd.to_datetime(row.get(hour_col), errors="coerce")
                    hour = int(t.hour) if pd.notna(t) else str(row.get(hour_col))
                except Exception:
                    try:
                        hour = int(float(row.get(hour_col))) % 24
                    except Exception:
                        hour = str(row.get(hour_col))
            dynamic = math.sin((i + 1) * 1.618) * 3.0
            score = _clip(float(base_scores.iloc[i]) * 0.55 + base_rel * 0.35 + (100 - fb_penalty) * 0.10 + dynamic, 0, 100, base_rel)
            new_row = {str(k): row[k] for k in work.columns}
            new_row.update({
                "Shared Sync Score": round(score, 2),
                "Priority Rank 1-14": _priority_rank(score),
                "Priority Label": _priority_label(score),
                "Calibration Reason": "Existing priority + reliability + prediction feedback + anti-constant hourly movement",
                "Hour": hour,
            })
            rows.append(new_row)
    else:
        ohlc = data.get("ohlc")
        if _is_df(ohlc):
            c = _series_num(ohlc, ["close", "c"]).replace(0, np.nan)
            h = _series_num(ohlc, ["high", "h"]).reindex(c.index).fillna(c)
            l = _series_num(ohlc, ["low", "l"]).reindex(c.index).fillna(c)
            tcol = _find_col(ohlc, ["time", "datetime", "timestamp", "date"])
            ret = c.pct_change().fillna(0) * 100.0
            rng = ((h - l).abs() / c.abs().replace(0, np.nan) * 100.0).fillna(0)
            tail_idx = list(ohlc.tail(24).index)
            for j, idx in enumerate(tail_idx):
                try:
                    hour: Any = j
                    if tcol:
                        ts = pd.to_datetime(ohlc.loc[idx, tcol], errors="coerce")
                        if pd.notna(ts):
                            hour = int(ts.hour)
                    momentum = float(ret.loc[idx]) if idx in ret.index else 0.0
                    vol = float(rng.loc[idx]) if idx in rng.index else 0.0
                    directional_bonus = 5.0 if (momentum > 0 and current.get("prediction_direction") == "BUY") or (momentum < 0 and current.get("prediction_direction") == "SELL") else -2.0
                    time_variation = math.sin((float(hour) + 1.0) / 24.0 * math.tau) * 4.5 if isinstance(hour, int) else math.sin(j + 1) * 3.0
                    score = _clip(base_rel * 0.62 + (100 - min(vol * 80, 35)) * 0.18 + (100 - fb_penalty) * 0.12 + 50 * 0.08 + directional_bonus + time_variation, 0, 100, base_rel)
                    rows.append({
                        "Hour": hour,
                        "Shared Sync Score": round(score, 2),
                        "Priority Rank 1-14": _priority_rank(score),
                        "Priority Label": _priority_label(score),
                        "Momentum %": round(momentum, 5),
                        "Range %": round(vol, 5),
                        "Calibration Reason": "OHLC-derived hourly priority proxy using existing data only; no new prediction model",
                    })
                except Exception:
                    continue
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    try:
        df = df.sort_values(["Priority Rank 1-14", "Shared Sync Score"], ascending=[True, False]).reset_index(drop=True)
    except Exception:
        pass
    return df


def _ai_grounding(current: Dict[str, Any], reliability: Dict[str, Any], quality: Dict[str, Any], priority_df: Any) -> Dict[str, Any]:
    best_priority = "-"
    try:
        if _is_df(priority_df):
            top = priority_df.iloc[0]
            best_priority = f"Rank {top.get('Priority Rank 1-14', '-')}: {top.get('Priority Label', '-')}"
    except Exception:
        pass
    conflict = current.get("prediction_direction") in {"BUY", "SELL"} and current.get("regime_direction") in {"BUY", "SELL"} and current.get("prediction_direction") != current.get("regime_direction")
    must_say = []
    if not quality.get("ok"):
        must_say.append("data quality is weak")
    if conflict:
        must_say.append("regime and PowerBI/prediction conflict")
    rel_score = _clip(reliability.get("score"), 0, 100, 50)
    if rel_score < 35:
        must_say.append("reliability is critically low; NO TRADE/PROTECT is required")
    elif rel_score < 45:
        must_say.append("reliability is weak; require extra confirmation and reduced risk")
    return {
        "ai_must_not_override": ["Regime", "Priority", "Power BI / prediction", "Reliability", "Data Quality"],
        "decision": current.get("decision", "-"),
        "regime": current.get("regime", "-"),
        "regime_direction": current.get("regime_direction", "WAIT"),
        "prediction_direction": current.get("prediction_direction", "WAIT"),
        "reliability_score": reliability.get("score", 0),
        "data_quality_score": quality.get("score", 0),
        "best_priority": best_priority,
        "conflict": bool(conflict),
        "must_say": must_say,
    }


def _signature_with_state(st: Any, data: Dict[str, Any]) -> str:
    try:
        parts = [data.get("source_signature", "")]
        for key in ["symbol", "timeframe", "metric_run_calculate", "run_data_visualization_antd_20260615"]:
            parts.append(str(st.session_state.get(key, "")))
        return hashlib.md5("|".join(parts).encode("utf-8", errors="ignore")).hexdigest()[:16]
    except Exception:
        return str(time.time())


def build_shared_calculation_result(st: Any = None, force: bool = False) -> Dict[str, Any]:
    """Build/update one shared object. Normal reruns adapt the canonical run only."""
    if st is None:
        import streamlit as st  # type: ignore
    if not force:
        try:
            from core.canonical_runtime_20260617 import get_canonical, build_shared_adapter
            canonical = get_canonical(st.session_state)
            if canonical:
                old = st.session_state.get(SHARED_KEY)
                if isinstance(old, dict) and old.get("run_id") == canonical.get("run_id") and old.get("calculation_generation") == canonical.get("calculation_generation"):
                    return old
                priority = st.session_state.get("canonical_priority_table_20260617")
                adapter = build_shared_adapter(st.session_state, canonical, legacy_shared=old if isinstance(old, dict) else None, priority_table=priority)
                st.session_state[SHARED_KEY] = adapter
                st.session_state[LEGACY_SHARED_KEY] = adapter
                return adapter
        except Exception:
            pass
    phone_mode = bool(st.session_state.get("phone_mode", False))
    data = _collect_core_data(st, phone_mode)
    signature = _signature_with_state(st, data)
    old = st.session_state.get(SHARED_KEY)
    if isinstance(old, dict) and old.get("signature") == signature and not force:
        return old

    flat = _collect_flat_state(st)
    quality = _data_quality(data.get("ohlc"))
    feedback = _prediction_feedback(flat, data)
    current = _extract_current_summary(flat, data)
    alpha_delta = _regime_alpha_delta(flat, data, feedback, quality)
    reliability = _calibrated_reliability(current, feedback, quality, alpha_delta)
    # One system-wide policy prevents Lunch, PowerBI, Finder and AI from
    # producing conflicting WAIT/NO TRADE results for the same shared data.
    try:
        from core.decision_policy_20260617 import (
            DECISION_POLICY_TEXT, infer_direction_from_regime, reconcile_decision,
        )
        rel_score = _clip(reliability.get("score"), 0, 100, 50)
        risk = _safe_num(current.get("exit_risk"), 5.0) or 5.0
        risk_pct = risk * 10.0 if risk <= 10 else risk
        data_quality_score = _clip(quality.get("score"), 0, 100, 50)
        direction = current.get("regime_direction")
        if direction not in {"BUY", "SELL"}:
            direction = infer_direction_from_regime(current.get("regime"), data.get("ohlc"))
        if direction not in {"BUY", "SELL"}:
            direction = current.get("prediction_direction")
        current["regime_direction"] = direction if direction in {"BUY", "SELL"} else "WAIT"
        current["decision"] = reconcile_decision(
            direction, current.get("decision"), rel_score, data_quality_score, risk_pct
        )
        current["decision_policy"] = DECISION_POLICY_TEXT
    except Exception:
        pass
    false_reversal_risk = _false_reversal_risk(flat, current, reliability)
    priority_df = _build_hourly_priority(data, current, reliability, feedback)
    grounding = _ai_grounding(current, reliability, quality, priority_df)

    # Map the original calculation/cache objects into one additive data contract.
    # Existing keys remain untouched and renderers still call their original code.
    powerbi_source: Dict[str, Any] = {}
    for key in ("dv_pp_base_result", "lunch_5layer_powerbi_result", "lunch_prediction_export", "dv_pp_regime_summary"):
        candidate = st.session_state.get(key)
        if isinstance(candidate, dict) and candidate:
            powerbi_source = dict(candidate)
            break
    powerbi_source.setdefault("available", bool(powerbi_source) or _is_df(data.get("predicted")))
    powerbi_source.setdefault("last_close", current.get("last_close"))
    powerbi_source.setdefault("forecast_close", current.get("forecast_close"))
    powerbi_source.setdefault("direction", current.get("prediction_direction", "WAIT"))
    powerbi_source.setdefault("confidence", current.get("forecast_confidence"))
    powerbi_source.setdefault("direction_accuracy", feedback.get("direction_accuracy_pct"))
    powerbi_source.setdefault("avg_abs_close_error_pct", feedback.get("avg_abs_close_error_pct"))
    powerbi_source.setdefault("projected_path", data.get("predicted"))
    powerbi_source.setdefault("prediction_vs_actual_history", data.get("bt_hist"))

    nlp_source = st.session_state.get("nlp_market_intelligence_result", {})
    nlp_contract = dict(nlp_source) if isinstance(nlp_source, dict) else {}
    nlp_contract.setdefault("summary", {})
    research_pack = st.session_state.get("research_pack_20260612", {})
    data_mining_contract = research_pack.get("data_mining", {}) if isinstance(research_pack, dict) else {}
    if not isinstance(data_mining_contract, dict):
        data_mining_contract = {}

    market_contract = {
        "symbol": current.get("symbol", "EURUSD"), "timeframe": current.get("timeframe", "H1"),
        "last_close": current.get("last_close"), "forecast_close": current.get("forecast_close"),
        "data_quality": quality, "ohlc": data.get("ohlc"),
    }
    regime_contract = {
        "current": current.get("regime", "-"), "direction": current.get("regime_direction", "WAIT"),
        "alpha_delta": alpha_delta, "history": data.get("regime_hist"),
    }
    decision_contract = {
        "central_decision": current.get("decision", "WAIT"), "entry_score": current.get("entry_score"),
        "hold_score": current.get("hold_score"), "tp_score": current.get("tp_score"),
        "exit_risk": current.get("exit_risk"), "prediction_direction": current.get("prediction_direction", "WAIT"),
        "policy": current.get("decision_policy", ""),
        "false_reversal_risk": false_reversal_risk,
    }
    priority_contract = {
        "table": priority_df if _is_df(priority_df) else (pd.DataFrame() if pd is not None else None),
        "best": (priority_df.iloc[0].to_dict() if _is_df(priority_df) else {}),
    }
    history_contract = {
        "prediction_vs_actual": data.get("bt_hist"), "regime": data.get("regime_hist"),
        "priority": data.get("priority"), "ohlc": data.get("ohlc"),
    }

    canonical = st.session_state.get("canonical_decision_result_20260617") or st.session_state.get("last_valid_canonical_decision_result_20260617") or {}
    canonical = canonical if isinstance(canonical, dict) else {}
    canonical_market = canonical.get("market") if isinstance(canonical.get("market"), dict) else {}

    result: Dict[str, Any] = {
        "version": UNIQUE,
        "built_at": _now_text(),
        "signature": signature,
        # Keep the lightweight shared adapter on the exact immutable canonical
        # identity so rerenders cannot create false synchronization mismatches.
        "run_id": canonical.get("run_id"),
        "calculation_generation": canonical.get("calculation_generation"),
        "data_signature": canonical.get("data_signature"),
        "symbol": canonical.get("symbol"),
        "timeframe": canonical.get("timeframe"),
        "source": canonical.get("source"),
        "latest_completed_candle_time": canonical.get("latest_completed_candle_time") or canonical_market.get("latest_completed_candle_time"),
        "full_metric_snapshot": canonical.get("full_metric_snapshot", {}),
        "market": market_contract,
        "regime": regime_contract,
        "decision": decision_contract,
        "priority": priority_contract,
        "reliability": reliability,
        "powerbi": powerbi_source,
        "nlp": nlp_contract,
        "data_mining": data_mining_contract,
        "history": history_contract,
        "metadata": {"built_at": _now_text(), "signature": signature, "shared_contract_version": "1.0", "calculation_source": "existing session caches"},
        "current": current,
        "data_quality": quality,
        "prediction_feedback": feedback,
        "reliability_calibration": reliability,
        "regime_alpha_delta": alpha_delta,
        "hourly_priority_table": priority_df if _is_df(priority_df) else (pd.DataFrame() if pd is not None else None),
        "ai_grounding": grounding,
        "false_reversal_risk": false_reversal_risk,
        # Immutable canonical object is created only by the main Settings run.
        # Re-renders may rebuild this lightweight adapter but never create a new run.
        "canonical": canonical,
        "source_keys": {
            "ohlc": "dv_pp_df/lunch_5layer_powerbi_df/last_df",
            "prediction": "dv_pp_predicted/dv_pp_lightblue_path",
            "feedback": "dv_pp_bt_hist/dv_pp_bt_summary",
            "regime": "dv_pp_regime_summary/dv_pp_regime_hist",
            "priority": "three_center_priority_sorted_20260614/reliability_dynamic_priority_table_20260614",
        },
    }
    st.session_state[SHARED_KEY] = result
    st.session_state[LEGACY_SHARED_KEY] = result
    st.session_state["adx_shared_calc_signature_20260615"] = signature
    st.session_state["adx_reliability_calibrated_20260615"] = reliability
    st.session_state["adx_prediction_feedback_20260615"] = feedback
    st.session_state["adx_regime_alpha_delta_20260615"] = alpha_delta
    st.session_state["adx_ai_grounding_20260615"] = grounding
    if _is_df(priority_df):
        st.session_state["adx_hourly_priority_calibrated_20260615"] = priority_df
        # Backward-compatible fill only when old tables are missing/empty. This
        # makes existing Research KNN/Greedy display work without replacing a
        # non-empty original priority table.
        for key in ["three_center_priority_sorted_20260614", "reliability_dynamic_priority_table_20260614"]:
            try:
                if not _is_df(st.session_state.get(key)):
                    st.session_state[key] = priority_df
            except Exception:
                pass
    return result


def ensure_shared_calculation_result(force: bool = False) -> Dict[str, Any]:
    try:
        import streamlit as st  # type: ignore
        rerun_id = st.session_state.get("app_rerun_identifier_20260617")
        if not force and rerun_id is not None:
            last_id = st.session_state.get("shared_sync_last_rerun_identifier_20260617")
            cached = st.session_state.get(SHARED_KEY)
            if last_id == rerun_id and isinstance(cached, dict):
                return cached
            st.session_state["shared_sync_last_rerun_identifier_20260617"] = rerun_id
            st.session_state["shared_sync_calls_this_rerun_20260617"] = int(st.session_state.get("shared_sync_calls_this_rerun_20260617", 0) or 0) + 1
        return build_shared_calculation_result(st, force=force)
    except Exception as exc:
        try:
            import streamlit as st  # type: ignore
            st.session_state["adx_shared_calc_error_20260615"] = str(exc)
        except Exception:
            pass
        return {"version": UNIQUE, "error": str(exc), "built_at": _now_text()}


def install_phone_safety_defaults() -> None:
    """Light app-wide defaults for phone performance; no layout change."""
    try:
        import streamlit as st  # type: ignore
        st.session_state.setdefault("safe_default_rows_20260615", MAX_MOBILE_ROWS)
        st.session_state.setdefault("shared_sync_lazy_load_20260615", True)
        st.session_state.setdefault("max_default_table_rows_phone_20260615", MAX_MOBILE_ROWS)
        st.session_state.setdefault("max_default_table_rows_desktop_20260615", MAX_DESKTOP_ROWS)
    except Exception:
        pass


def render_shared_sync_compact_panel(location: str = "") -> None:
    """Optional renderer. Use only inside existing tabs/expanders."""
    try:
        import streamlit as st  # type: ignore
        from core.canonical_runtime_20260617 import shared_from_runtime
        result = shared_from_runtime(st.session_state)
        rel = result.get("reliability_calibration", {}) if isinstance(result, dict) else {}
        fb = result.get("prediction_feedback", {}) if isinstance(result, dict) else {}
        ad = result.get("regime_alpha_delta", {}) if isinstance(result, dict) else {}
        q = result.get("data_quality", {}) if isinstance(result, dict) else {}
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Shared Sync", "READY" if result and not result.get("error") else "WATCH")
        c2.metric("Reliability", f"{_safe_num(rel.get('score'), 0):.1f}", str(rel.get("grade", "-")))
        c3.metric("Pred Error", f"{_safe_num(fb.get('avg_abs_close_error_pct'), 0):.4f}%", str(fb.get("feedback_loop_status", "-"))[:24])
        c4.metric("Regime Δ", f"{_safe_num(ad.get('regime_delta'), 0):.2f}", str(ad.get("validation_status", "-"))[:24])
        st.caption(f"Central shared result: {result.get('built_at','-')} • Data quality {q.get('score','-')} • {location}")
    except Exception as exc:
        try:
            import streamlit as st  # type: ignore
            st.caption(f"Shared sync compact panel skipped safely: {exc}")
        except Exception:
            pass


def ground_ai_answer_text(answer: str, question: str = "") -> str:
    """Ground an answer without forcing a trade bias onto unrelated questions."""
    try:
        import streamlit as st  # type: ignore
        from core.canonical_runtime_20260617 import shared_from_runtime
        result = shared_from_runtime(st.session_state)
    except Exception:
        result = {}
    g = result.get("ai_grounding", {}) if isinstance(result, dict) else {}
    if not isinstance(g, dict):
        return str(answer or "")
    rel = _safe_num(g.get("reliability_score"), 0) or 0
    dq = _safe_num(g.get("data_quality_score"), 0) or 0
    must = g.get("must_say") if isinstance(g.get("must_say"), list) else []
    base = str(answer or "")
    if "AI Grounding Guard" in base or "Data Grounding" in base:
        return base
    q = str(question or "").lower()
    directional_terms = (
        "buy", "sell", "long", "short", "entry", "trade", "position", "tp", "take profit",
        "stop loss", "hold", "exit", "direction", "bias", "safer", "less risky", "price prediction",
    )
    is_directional = any(term in q for term in directional_terms)
    system_control_terms = (
        "sidebar", "menu", "settings", "setting page", "phone ui", "api connection",
        "nlp api", "llm", "copy short", "copy full", "finder", "research tab",
        "other tab", "engine", "train data", "pre original", "backtest", "profile",
        "question pattern", "startup page", "opens first",
    )
    if not is_directional and any(term in q for term in system_control_terms):
        return base
    if not is_directional:
        # Factual market/NLP/error/reliability questions get a data-quality note,
        # never an unrelated BUY/SELL recommendation. Pure app-control questions
        # return the direct answer above without trading-data boilerplate.
        if rel >= 45 and dq >= 55 and not g.get("conflict"):
            return base
        return base + f"\n\n**Data Grounding:** Reliability={rel:.1f}, Data Quality={dq:.1f}. Missing or weak data limits certainty."
    guard_needed = bool(must or g.get("conflict") or rel < 45 or dq < 55)
    if not guard_needed:
        return base
    guard = (
        "\n\n**AI Grounding Guard:** This directional answer cannot override the synchronized system. "
        f"Decision={g.get('decision','-')}, Regime={g.get('regime','-')} ({g.get('regime_direction','WAIT')}), "
        f"PowerBI/Prediction={g.get('prediction_direction','WAIT')}, Reliability={rel:.1f}, Data Quality={dq:.1f}, "
        f"Priority={g.get('best_priority','-')}."
    )
    if must:
        guard += " Must mention: " + ", ".join(map(str, must)) + "."
    return base + guard


def shared_result_copy_payload() -> str:
    try:
        import streamlit as st  # type: ignore
        from core.canonical_runtime_20260617 import shared_from_runtime
        result = shared_from_runtime(st.session_state)
    except Exception:
        result = {}
    safe = _json_safe(result)
    try:
        return json.dumps(safe, indent=2, ensure_ascii=False, default=str)
    except Exception:
        return str(safe)
