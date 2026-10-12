# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Canonical regime, decision, error and 25-day table synchronization.

The module only reconciles existing calculation outputs. It does not create a
new market model. Lunch, PowerBI, Finder and Research read the same snapshot so
regime/start/end/decision/error cannot drift between sections.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Tuple

import numpy as np
import pandas as pd
import streamlit as st

REGIME_KEYS = (
    "major_regime_history_df", "full_metric_regime_history_df",
    "full_metric_detail_history_df", "lunch_regime_history", "regime_history_df",
    "dv_pp_regime_hist", "regime_history", "smooth_regime_history",
)
OHLC_KEYS = (
    "calculation_staging_ohlc_df_20260617", "canonical_completed_ohlc_df_20260617", "dv_pp_df", "lunch_5layer_powerbi_df", "last_df", "full_metric_history_df",
    "lunch_visual_df", "ohlc_df", "df",
)
PRIORITY_KEYS = (
    "adx_hourly_priority_calibrated_20260615", "three_center_priority_sorted_20260614",
    "reliability_dynamic_priority_table_20260614", "priority_table_df", "knn_greedy_priority_table",
)
NLP_KEYS = (
    "regime_nlp_today_table", "nlp_ranked_news_df", "news_nlp_ranked_df",
    "news_nlp_table", "nlp_news_df", "latest_news_df",
)


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _dt_series(values: Any) -> pd.Series:
    """Parse mixed API/history timestamps into timezone-naive UTC values."""
    try:
        index = values.index if isinstance(values, pd.Series) else None
        raw = pd.Series(values, index=index)
        return pd.to_datetime(raw, errors="coerce", utc=True).dt.tz_convert(None)
    except Exception:
        return pd.Series(pd.NaT, index=getattr(values, "index", None))


def _dt_scalar(value: Any) -> pd.Timestamp:
    try:
        parsed = pd.to_datetime(value, errors="coerce", utc=True)
        if pd.isna(parsed):
            return pd.NaT
        return pd.Timestamp(parsed).tz_convert(None)
    except Exception:
        return pd.NaT


def _clip(value: Any, low: float = 0.0, high: float = 100.0, default: float = 50.0) -> float:
    parsed = _num(value, default)
    return max(low, min(high, float(default if parsed is None else parsed)))


def _iter_state_dfs(keys: Iterable[str]):
    for key in keys:
        obj = st.session_state.get(key)
        if isinstance(obj, pd.DataFrame) and not obj.empty:
            yield key, obj
        elif isinstance(obj, dict):
            for subkey, value in obj.items():
                if isinstance(value, pd.DataFrame) and not value.empty:
                    yield f"{key}.{subkey}", value


def _first_df(keys: Iterable[str]) -> pd.DataFrame:
    for _key, df in _iter_state_dfs(keys):
        return df
    return pd.DataFrame()


def _find_col(df: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    norm = {str(c).strip().lower().replace("_", " "): c for c in df.columns}
    normalized_aliases = [str(a).strip().lower().replace("_", " ") for a in aliases]
    for alias in normalized_aliases:
        if alias in norm:
            return norm[alias]
    for key, col in norm.items():
        if any(alias and alias in key for alias in normalized_aliases):
            return col
    return None


def _shared() -> Dict[str, Any]:
    try:
        from core.canonical_runtime_20260617 import shared_from_runtime
        return shared_from_runtime(st.session_state)
    except Exception:
        value = st.session_state.get("adx_shared_calc_result_20260615") or st.session_state.get("shared_calc_result")
        return value if isinstance(value, dict) else {}


def _current_regime_from_state(shared: Dict[str, Any]) -> str:
    candidates = []
    for key in (
        "dv_pp_regime_summary", "regime_context_20260614", "lunch_5layer_powerbi_result",
        "final_merged_intelligence_pack_20260612", "lunch_metric_result_cache",
    ):
        obj = st.session_state.get(key)
        if isinstance(obj, dict):
            candidates.extend([
                obj.get("current_regime"), obj.get("major_regime"), obj.get("master_regime"),
                obj.get("regime"), (obj.get("scores") or {}).get("Regime") if isinstance(obj.get("scores"), dict) else None,
            ])
    current = shared.get("current", {}) if isinstance(shared.get("current"), dict) else {}
    alpha = shared.get("regime_alpha_delta", {}) if isinstance(shared.get("regime_alpha_delta"), dict) else {}
    candidates.extend([alpha.get("current_regime"), current.get("regime"), st.session_state.get("current_regime")])
    for value in candidates:
        text = str(value or "").strip()
        if text and text not in {"-", "None", "nan", "WAIT", "NO TRADE"}:
            return text
    return "RANGE_NORMAL"


def _normalize_ohlc() -> pd.DataFrame:
    best = pd.DataFrame()
    best_score = -1.0
    for key, candidate in _iter_state_dfs(OHLC_KEYS):
        try:
            from core.runtime_cache_20260617 import cached_clean_ohlc
            canonical = st.session_state.get("canonical_decision_result_20260617") or {}
            df = cached_clean_ohlc(
                candidate,
                symbol=str(canonical.get("symbol") or st.session_state.get("symbol") or "EURUSD"),
                timeframe=str(canonical.get("timeframe") or st.session_state.get("timeframe") or "H1"),
                source=str(canonical.get("source") or st.session_state.get("source") or key),
                data_signature=str(canonical.get("data_signature") or f"{key}:{len(candidate)}"),
                calculation_version=str(canonical.get("calculation_version") or "decision-product-20260617-v1"),
            )
        except Exception:
            df = pd.DataFrame()
        if df.empty:
            st.session_state["regime_data_not_ready_reason_20260617"] = f"{key} has no valid completed timestamped OHLC data"
            continue
        freshness = pd.Timestamp(df["time"].max())
        age_hours = max(0.0, (pd.Timestamp.now(tz=freshness.tz) - freshness).total_seconds() / 3600.0) if freshness.tzinfo else max(0.0, (pd.Timestamp.now() - freshness).total_seconds() / 3600.0)
        score = min(len(df), 5000) / 100.0 + max(0.0, 80.0 - age_hours / 3.0)
        if key.startswith("dv_pp_df") or key.startswith("last_df"):
            score += 8.0
        if score > best_score:
            best, best_score = df.reset_index(drop=True), score
    return best


def _momentum_direction(ohlc: pd.DataFrame, regime: str = "") -> str:
    try:
        from core.decision_policy_20260617 import infer_direction_from_regime
        return infer_direction_from_regime(regime, ohlc)
    except Exception:
        return "WAIT"


def _select_regime_source() -> Tuple[pd.DataFrame, str]:
    """Choose the freshest structurally complete regime table, not first key."""
    preference = {
        "major_regime_history_df": 28.0,
        "full_metric_regime_history_df": 27.5,
        "full_metric_detail_history_df": 27.0,
        "lunch_regime_history": 26.0,
        "regime_history_df": 24.0,
        "dv_pp_regime_hist": 22.0,
        "regime_history": 18.0,
        "smooth_regime_history": 16.0,
    }
    best_df, best_key, best_score = pd.DataFrame(), "", -1e9
    now = pd.Timestamp.now()
    fixed = list(_iter_state_dfs(REGIME_KEYS))
    seen_names = set()
    for key, df in fixed:
        if key in seen_names:
            continue
        seen_names.add(key)
        rcol = _find_col(df, ("major regime", "current regime", "master regime", "regime", "label", "state"))
        if not rcol:
            continue
        scol = _find_col(df, ("regime start", "start time", "started", "start"))
        tcol = _find_col(df, ("time", "datetime", "timestamp", "date", "bar time"))
        ecol = _find_col(df, ("regime end", "end time", "ended", "end", "next change"))
        times = pd.Series(dtype="datetime64[ns]")
        open_current_segment = False
        if ecol and scol:
            parsed_end = _dt_series(df[ecol])
            parsed_start = _dt_series(df[scol])
            open_current_segment = bool(parsed_end.isna().any() and parsed_start.notna().any())
        for col in (ecol, tcol, scol):
            if col:
                parsed = _dt_series(df[col]).dropna()
                if not parsed.empty:
                    times = parsed
                    break
        fresh_bonus = 55.0 if open_current_segment else 0.0
        if not open_current_segment and not times.empty:
            latest = pd.Timestamp(times.max())
            try:
                reference = pd.Timestamp.now(tz=latest.tz) if latest.tzinfo else now
                age_days = max(0.0, (reference - latest).total_seconds() / 86400.0)
                fresh_bonus = max(0.0, 55.0 - age_days * 4.0)
            except Exception:
                fresh_bonus = 5.0
        explicit_bonus = 20.0 if scol else 0.0
        explicit_bonus += 12.0 if ecol else 0.0
        size_bonus = min(16.0, math.log2(max(2, len(df))) * 2.0)
        root = key.split(".", 1)[0]
        name_low = str(key).lower()
        semantic_bonus = 0.0
        if "full_metric" in name_low or "full metric" in name_low:
            semantic_bonus += 38.0
        if "major_regime" in name_low or "major regime" in name_low:
            semantic_bonus += 28.0
        if "history" in name_low:
            semantic_bonus += 8.0
        score = preference.get(root, 0.0) + semantic_bonus + fresh_bonus + explicit_bonus + size_bonus
        if score > best_score:
            best_df, best_key, best_score = df.copy(), key, score
    return best_df, best_key


def _regime_runs(shared: Dict[str, Any], days: int = 10, anchor: pd.Timestamp | None = None) -> Tuple[pd.DataFrame, str]:
    raw, source_key = _select_regime_source()
    fallback_regime = _current_regime_from_state(shared)
    now = _dt_scalar(anchor).floor("s") if anchor is not None and not pd.isna(anchor) else pd.Timestamp.now(tz="UTC").tz_convert(None).floor("s")
    if raw.empty:
        return pd.DataFrame([{
            "Regime": fallback_regime, "Regime Start": pd.NaT, "Regime End": pd.NaT,
            "Status": "CURRENT", "Source": "current shared result",
        }]), "current shared result"

    rcol = _find_col(raw, ("major regime", "current regime", "master regime", "regime", "label", "state"))
    scol = _find_col(raw, ("regime start", "start time", "started", "start"))
    ecol = _find_col(raw, ("regime end", "end time", "ended", "end", "next change"))
    tcol = _find_col(raw, ("time", "datetime", "timestamp", "date", "bar time"))
    if not rcol:
        return pd.DataFrame([{
            "Regime": fallback_regime, "Regime Start": pd.NaT, "Regime End": pd.NaT,
            "Status": "CURRENT", "Source": "shared fallback",
        }]), "shared fallback"

    work = pd.DataFrame({"Regime": raw[rcol].astype(str).str.strip()})
    # Segment-level tables already contain regime start/end. Preserve them.
    if scol:
        work["Regime Start"] = _dt_series(raw[scol])
        work["Regime End"] = _dt_series(raw[ecol]) if ecol else pd.NaT
        work = work.dropna(subset=["Regime Start"]).sort_values("Regime Start").drop_duplicates(
            subset=["Regime", "Regime Start"], keep="last"
        ).reset_index(drop=True)
        if not work.empty:
            next_start = pd.Series(list(work["Regime Start"].iloc[1:]) + [pd.NaT], index=work.index, dtype="datetime64[ns]")
            missing_closed = work["Regime End"].isna() & next_start.notna()
            work.loc[missing_closed, "Regime End"] = next_start[missing_closed]
            runs = work
        else:
            runs = pd.DataFrame()
    else:
        if tcol:
            work["time"] = _dt_series(raw[tcol])
        else:
            st.session_state["regime_data_not_ready_reason_20260617"] = f"{source_key or 'regime source'} has no valid timestamps"
            return pd.DataFrame([{"Regime": "DATA NOT READY", "Regime Start": pd.NaT, "Regime End": pd.NaT, "Status": "DATA NOT READY", "Source": source_key or "missing timestamp"}]), source_key or "missing timestamp"
        work = work.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
        if work.empty:
            runs = pd.DataFrame()
        else:
            group = work["Regime"].ne(work["Regime"].shift()).cumsum()
            runs = work.groupby(group, as_index=False).agg(
                Regime=("Regime", "last"),
                **{"Regime Start": ("time", "min"), "Regime End": ("time", "max")},
            )
            if not runs.empty:
                next_start = pd.Series(list(runs["Regime Start"].iloc[1:]) + [pd.NaT], index=runs.index, dtype="datetime64[ns]")
                runs.loc[next_start.notna(), "Regime End"] = next_start[next_start.notna()]
                runs.loc[runs.index[-1], "Regime End"] = pd.NaT

    if runs.empty:
        runs = pd.DataFrame([{"Regime": fallback_regime, "Regime Start": pd.NaT, "Regime End": pd.NaT}])
    # If every recorded segment ended before the latest available market bar,
    # append the shared current regime instead of silently re-labelling a stale
    # historical segment as current.
    starts_all = _dt_series(runs["Regime Start"])
    ends_all = _dt_series(runs["Regime End"])
    active_mask = starts_all.notna() & (starts_all <= now) & (ends_all.isna() | (ends_all >= now))
    if not active_mask.any():
        latest_regime = str(runs.iloc[-1].get("Regime", "")) if not runs.empty else ""
        latest_end = ends_all.dropna().max() if ends_all.notna().any() else pd.NaT
        latest_start = starts_all.dropna().max() if starts_all.notna().any() else pd.NaT
        inferred_start = latest_end if not pd.isna(latest_end) else latest_start
        if fallback_regime and (latest_regime != fallback_regime or pd.isna(latest_end) or latest_end < now):
            runs = pd.concat([
                runs,
                pd.DataFrame([{
                    "Regime": fallback_regime,
                    "Regime Start": inferred_start,
                    "Regime End": pd.NaT,
                }]),
            ], ignore_index=True)
            starts_all = _dt_series(runs["Regime Start"])
            ends_all = _dt_series(runs["Regime End"])

    cutoff = now - pd.Timedelta(days=max(1, int(days)))
    starts = _dt_series(runs["Regime Start"])
    ends = _dt_series(runs["Regime End"])
    # Keep a segment if it overlaps the window; this preserves a current regime
    # that started before the requested 10-day window.
    overlap = ends.isna() | (ends >= cutoff) | (starts >= cutoff)
    filtered = runs.loc[overlap].copy()
    if filtered.empty:
        filtered = runs.tail(1).copy()
    filtered["Status"] = "CLOSED"
    fstart = _dt_series(filtered["Regime Start"])
    fend = _dt_series(filtered["Regime End"])
    current_mask = fstart.notna() & (fstart <= now) & (fend.isna() | (fend >= now))
    if current_mask.any():
        filtered.loc[current_mask, "Status"] = "CURRENT"
    elif not filtered.empty:
        filtered.loc[filtered.index[-1], "Status"] = "CURRENT"
    filtered["Source"] = source_key or "regime history"
    return filtered.tail(100).reset_index(drop=True), source_key or "regime history"


def _error_snapshot(shared: Dict[str, Any], ohlc: pd.DataFrame) -> Dict[str, Any]:
    """Use completed prediction-vs-actual data first; never present fake 0.00%."""
    fb = shared.get("prediction_feedback", {}) if isinstance(shared.get("prediction_feedback"), dict) else {}
    value = _num(fb.get("avg_abs_close_error_pct"), None)
    samples = int(_num(fb.get("samples") or fb.get("tested_candles"), 0) or 0)
    method = str(fb.get("method") or "")

    # Read the exact PowerBI/backtest caches when shared feedback is stale or rounded to zero.
    summaries = []
    history_frames = []
    for key, obj in list(st.session_state.items()):
        key_low = str(key).lower()
        if isinstance(obj, dict) and any(t in key_low for t in ("bt", "backtest", "prediction", "powerbi", "feedback")):
            summaries.append((str(key), obj))
        if isinstance(obj, pd.DataFrame) and not obj.empty and any(t in key_low for t in ("bt", "backtest", "prediction", "actual", "projection")):
            history_frames.append((str(key), obj.copy()))
    for key in ("dv_pp_bt_summary", "prediction_feedback", "prediction_backtest_summary"):
        obj = st.session_state.get(key)
        if isinstance(obj, dict):
            summaries.insert(0, (key, obj))
    for name, summary in summaries:
        candidate = None
        for field in ("avg_abs_close_error_pct", "average_error_pct", "avg_close_error_pct", "prediction_error_pct", "close_error_pct", "Prediction vs Actual Close Error"):
            if field in summary:
                candidate = _num(summary.get(field), None)
                break
        candidate_samples = int(_num(summary.get("samples") or summary.get("tested_candles") or summary.get("count"), 0) or 0)
        if candidate is not None and candidate > 1e-9 and (candidate_samples > 0 or samples <= 0):
            value, samples, method = float(candidate), max(samples, candidate_samples), f"{name} completed prediction-vs-actual summary"
            break

    if value is None or value <= 1e-9 or samples <= 0:
        preferred = ["dv_pp_bt_hist", "prediction_vs_actual_history_df", "prediction_history_df", "dv_pp_projection_history"]
        ordered = []
        for key in preferred:
            obj = st.session_state.get(key)
            if isinstance(obj, pd.DataFrame) and not obj.empty:
                ordered.append((key, obj.copy()))
        ordered += history_frames
        seen = set()
        for name, frame in ordered:
            if id(frame) in seen:
                continue
            seen.add(id(frame))
            error_col = _find_col(frame, ("close error %", "absolute error %", "abs error", "prediction error %", "error %", "close_error_pct"))
            if error_col:
                values = pd.to_numeric(frame[error_col], errors="coerce").abs().replace([np.inf, -np.inf], np.nan).dropna()
                values = values[values > 1e-12]
                if not values.empty:
                    value, samples, method = float(values.mean()), int(len(values)), f"{name} completed prediction-vs-actual rows"
                    break
            actual_col = _find_col(frame, ("actual close", "actual", "observed close"))
            pred_col = _find_col(frame, ("pred close", "predicted close", "forecast close", "prediction"))
            if actual_col and pred_col:
                actual = pd.to_numeric(frame[actual_col], errors="coerce")
                pred = pd.to_numeric(frame[pred_col], errors="coerce")
                errors = ((pred - actual).abs() / actual.abs().replace(0, np.nan) * 100.0).dropna()
                errors = errors[errors > 1e-12]
                if not errors.empty:
                    value, samples, method = float(errors.mean()), int(len(errors)), f"{name} calculated prediction-vs-actual rows"
                    break

    is_actual = bool(samples > 0 and value is not None and value > 1e-9 and "proxy" not in method.lower())
    if is_actual:
        return {"value": float(value), "samples": samples, "method": method or "prediction-vs-actual history", "is_proxy": False, "available": True}
    if not ohlc.empty:
        ret = pd.to_numeric(ohlc["close"], errors="coerce").pct_change().abs() * 100.0
        proxy = _num(ret.tail(48).dropna().mean(), None)
        if proxy is not None and proxy > 1e-9:
            return {
                "value": float(proxy), "samples": 0,
                "method": "recent H1 volatility proxy; completed prediction-vs-actual rows unavailable",
                "is_proxy": True, "available": True,
            }
    return {
        "value": None, "samples": 0,
        "method": "N/A; run PowerBI prediction-vs-actual backtest to create error samples",
        "is_proxy": False, "available": False,
    }


def _decision_from_evidence(direction: str, existing: str, reliability: float, data_quality: float, exit_risk: float) -> str:
    try:
        from core.decision_policy_20260617 import reconcile_decision
        return reconcile_decision(direction, existing, reliability, data_quality, exit_risk)
    except Exception:
        return "WAIT"


def canonical_regime_snapshot(days: int = 25) -> Dict[str, Any]:
    shared = _shared()
    try:
        from core.canonical_runtime_20260617 import get_canonical
        canonical = {} if st.session_state.get("settings_calculation_lock_20260617") else get_canonical(st.session_state)
    except Exception:
        canonical = {}
    if canonical:
        ohlc = _normalize_ohlc()
        anchor = _dt_series(ohlc["time"]).max() if not ohlc.empty and "time" in ohlc.columns else None
        history, source = _regime_runs(shared, days=days, anchor=anchor)
        regime_payload = canonical.get("regime") or {}
        final = canonical.get("final_decision") or {}
        quality = canonical.get("data_quality") or {}
        reliability_payload = canonical.get("reliability") or {}
        latest = history.iloc[-1] if isinstance(history, pd.DataFrame) and not history.empty else pd.Series(dtype=object)
        start = latest.get("Regime Start", pd.NaT)
        end = latest.get("Regime End", pd.NaT)
        error_value = canonical.get("risk", {}).get("error_estimate_pct") if isinstance(canonical.get("risk"), dict) else None
        snapshot = {
            "regime": regime_payload.get("major_regime", "UNKNOWN"),
            "regime_direction": final.get("directional_market_view", "WAIT"),
            "decision": final.get("final_decision", "DATA NOT READY"),
            "regime_start": start, "regime_end": end,
            "regime_end_display": "OPEN / CURRENT" if pd.isna(end) else str(pd.Timestamp(end)),
            "regime_true": str(quality.get("status", "")).startswith("PASS"),
            "regime_validation": "TRUE" if str(quality.get("status", "")).startswith("PASS") else "FALSE / WATCH",
            "reliability": _clip(reliability_payload.get("score"), 0, 100, 0),
            "data_quality": _clip(quality.get("score"), 0, 100, 0),
            "exit_risk_pct": _clip((canonical.get("risk") or {}).get("uncertainty_pct"), 0, 100, 100),
            "avg_error_pct": error_value, "error_samples": int(reliability_payload.get("sample_count", 0) or 0),
            "error_method": "canonical selected-horizon reliability", "error_is_proxy": False,
            "error_available": error_value is not None, "direction_accuracy_pct": reliability_payload.get("direction_accuracy"),
            "source": source, "history": history, "shared": shared, "ohlc": ohlc,
            "decision_policy": final.get("main_reason", "Canonical decision policy"),
            "run_id": canonical.get("run_id"), "calculation_generation": canonical.get("calculation_generation"),
            "data_signature": canonical.get("data_signature"),
        }
        st.session_state["canonical_regime_snapshot_20260617"] = snapshot
        return snapshot
    ohlc = _normalize_ohlc()
    anchor = _dt_series(ohlc["time"]).max() if not ohlc.empty else None
    history, source = _regime_runs(shared, days=days, anchor=anchor)
    current_rows = history[history.get("Status", "") == "CURRENT"] if not history.empty and "Status" in history.columns else pd.DataFrame()
    latest = current_rows.iloc[-1] if not current_rows.empty else (history.iloc[-1] if not history.empty else pd.Series(dtype=object))
    regime = str(latest.get("Regime") or _current_regime_from_state(shared))
    direction = _momentum_direction(ohlc, regime)
    current = shared.get("current", {}) if isinstance(shared.get("current"), dict) else {}
    rel = shared.get("reliability_calibration", {}) if isinstance(shared.get("reliability_calibration"), dict) else {}
    quality = shared.get("data_quality", {}) if isinstance(shared.get("data_quality"), dict) else {}
    reliability = _clip(rel.get("score"), 0, 100, 50)
    data_quality = _clip(quality.get("score"), 0, 100, 50)
    exit_risk_raw = _num(current.get("exit_risk"), 5.0) or 5.0
    exit_risk = exit_risk_raw * 10.0 if exit_risk_raw <= 10 else exit_risk_raw
    existing = str(current.get("decision") or "").upper().strip()
    decision = _decision_from_evidence(direction, existing, reliability, data_quality, exit_risk)
    # Write the reconciled values back into the shared object so AI Assistant,
    # Finder, PowerBI and Lunch do not keep an older WAIT/NO TRADE snapshot.
    current["regime"] = regime
    current["regime_direction"] = direction
    current["decision"] = decision
    try:
        from core.decision_policy_20260617 import DECISION_POLICY_TEXT
        current["decision_policy"] = DECISION_POLICY_TEXT
    except Exception:
        current["decision_policy"] = "Shared directional policy"
    if isinstance(shared, dict):
        shared["current"] = current
        try:
            st.session_state["adx_shared_calc_result_20260615"] = shared
            st.session_state["shared_calc_result"] = shared
        except Exception:
            pass

    start = latest.get("Regime Start") if not latest.empty else pd.NaT
    end = latest.get("Regime End") if not latest.empty else pd.NaT
    source_is_history = source not in {"", "current shared result", "shared fallback"}
    start_ok = not pd.isna(start)
    regime_true = bool(source_is_history and start_ok and reliability >= 32 and data_quality >= 22)
    error = _error_snapshot(shared, ohlc)
    snapshot = {
        "regime": regime,
        "regime_direction": direction,
        "decision": decision,
        "regime_start": start,
        "regime_end": end,
        "regime_end_display": "OPEN / CURRENT" if pd.isna(end) else str(pd.Timestamp(end)),
        "regime_true": regime_true,
        "regime_validation": "TRUE" if regime_true else "FALSE / WATCH",
        "reliability": reliability,
        "data_quality": data_quality,
        "exit_risk_pct": round(exit_risk, 2),
        "avg_error_pct": error["value"],
        "error_samples": error["samples"],
        "error_method": error["method"],
        "error_is_proxy": error["is_proxy"],
        "error_available": error["available"],
        "direction_accuracy_pct": _num((shared.get("prediction_feedback") or {}).get("direction_accuracy_pct"), None) if isinstance(shared.get("prediction_feedback"), dict) else None,
        "source": source,
        "history": history,
        "shared": shared,
        "ohlc": ohlc,
        "decision_policy": current.get("decision_policy", "Shared directional policy"),
    }
    st.session_state["canonical_regime_snapshot_20260617"] = snapshot
    st.session_state["current_regime"] = regime
    st.session_state["synced_current_decision_20260617"] = decision
    return snapshot


def _nlp_table(days: int = 25, anchor: pd.Timestamp | None = None) -> pd.DataFrame:
    raw = _first_df(NLP_KEYS)
    if raw.empty:
        return pd.DataFrame()
    tcol = _find_col(raw, ("time", "datetime", "published", "date"))
    rankcol = _find_col(raw, ("rank", "priority"))
    titlecol = _find_col(raw, ("headline", "title", "news", "text", "summary"))
    impactcol = _find_col(raw, ("impact", "sentiment", "direction", "effect"))
    out = pd.DataFrame(index=raw.index)
    out["NLP Time"] = _dt_series(raw[tcol]) if tcol else pd.NaT
    out["NLP Rank"] = pd.to_numeric(raw[rankcol], errors="coerce") if rankcol else np.arange(1, len(raw) + 1)
    out["NLP News"] = raw[titlecol].astype(str).str.slice(0, 120) if titlecol else "-"
    out["NLP Impact"] = raw[impactcol].astype(str).str.slice(0, 40) if impactcol else "-"
    if out["NLP Time"].notna().any():
        ref = _dt_scalar(anchor) if anchor is not None and not pd.isna(anchor) else pd.Timestamp.now(tz="UTC").tz_convert(None)
        out = out[out["NLP Time"] >= ref - pd.Timedelta(days=max(1, int(days)))]
    return out.sort_values(["NLP Rank", "NLP Time"], ascending=[True, False], na_position="last").head(500).reset_index(drop=True)


def merged_hourly_regime_nlp_priority(days: int = 25) -> pd.DataFrame:
    snap = canonical_regime_snapshot(days=days)
    ohlc = snap["ohlc"].copy()
    error_value = snap.get("avg_error_pct")
    error_display: Any = round(float(error_value), 5) if error_value is not None else "N/A"
    if ohlc.empty:
        return pd.DataFrame([{
            "Time": "-", "Hour": "-", "Major Regime": snap["regime"],
            "Regime Start": snap.get("regime_start"), "Regime End": snap.get("regime_end_display"),
            "Regime True / False": snap["regime_validation"],
            "Decision": snap["decision"], "KNN Priority": 14, "Greedy Priority": 14,
            "Reliability %": round(snap["reliability"], 2), "Avg Error %": error_display,
            "NLP Rank": "-", "NLP Impact": "-", "NLP News": "-",
        }])
    anchor = _dt_series(ohlc["time"]).max()
    cutoff = anchor - pd.Timedelta(days=max(1, int(days)))
    ohlc = ohlc[ohlc["time"] >= cutoff].tail(max(24, min(600, int(days) * 24))).copy()
    ohlc["Hour"] = ohlc["time"].dt.hour
    ohlc["Move %"] = ohlc["close"].pct_change().fillna(0.0) * 100.0

    priority = _first_df(PRIORITY_KEYS)
    hour_map: Dict[int, Dict[str, Any]] = {}
    if not priority.empty:
        hcol = _find_col(priority, ("hour", "h1 hour"))
        rcol = _find_col(priority, ("priority rank 1-14", "priority rank", "knn priority", "rank"))
        scol = _find_col(priority, ("shared sync score", "knn priority score", "priority score", "score"))
        if hcol:
            for _, row in priority.iterrows():
                hour = int(_num(row.get(hcol), 0) or 0) % 24
                score = _clip(row.get(scol) if scol else None, 0, 100, 50)
                rank_value = _num(row.get(rcol), None) if rcol else None
                rank = int(round(_clip(rank_value, 1, 14, max(1, min(14, math.ceil((100.0 - score) / 7.15))))))
                old = hour_map.get(hour)
                if old is None or score > float(old.get("score", 0)):
                    hour_map[hour] = {"rank": rank, "score": score}

    hist = snap["history"].copy()
    hist["Regime Start"] = _dt_series(hist["Regime Start"])
    hist["Regime End"] = _dt_series(hist["Regime End"])

    def segment_for_time(ts: pd.Timestamp) -> Dict[str, Any]:
        valid = hist[hist["Regime Start"].notna() & (hist["Regime Start"] <= ts)]
        if not valid.empty:
            bounded = valid[valid["Regime End"].isna() | (valid["Regime End"] >= ts)]
            row = bounded.iloc[-1] if not bounded.empty else valid.iloc[-1]
            start = row.get("Regime Start", pd.NaT)
            end = row.get("Regime End", pd.NaT)
            structurally_valid = bool(str(row.get("Regime", "")).strip() and not pd.isna(start) and (pd.isna(end) or end >= start))
            return {
                "regime": str(row.get("Regime") or snap["regime"]),
                "start": start, "end": end,
                "validation": "TRUE" if structurally_valid else "FALSE / WATCH",
            }
        return {
            "regime": snap["regime"], "start": snap.get("regime_start"),
            "end": snap.get("regime_end"), "validation": snap["regime_validation"],
        }

    rows = []
    for idx, row in ohlc.iterrows():
        hour = int(row["Hour"])
        mapped = hour_map.get(hour, {})
        move_pct = float(row["Move %"])
        fallback_score = snap["reliability"] * 0.72 + min(28.0, abs(move_pct) * 900.0)
        score = float(mapped.get("score", _clip(fallback_score, 0, 100, 50)))
        knn_rank = int(mapped.get("rank", max(1, min(14, int(math.ceil((100.0 - score) / 7.15))))))
        segment = segment_for_time(pd.Timestamp(row["time"]))
        regime = segment["regime"]
        direction = _momentum_direction(ohlc.loc[:idx].tail(8), regime)
        decision = _decision_from_evidence(direction, "", snap["reliability"], snap["data_quality"], snap["exit_risk_pct"])
        greedy_score = _clip(score * 0.62 + snap["reliability"] * 0.23 + min(15.0, abs(move_pct) * 600.0), 0, 100, 50)
        greedy_rank = max(1, min(14, int(math.ceil((100.0 - greedy_score) / 7.15))))
        rows.append({
            "Time": pd.Timestamp(row["time"]), "Hour": f"{hour:02d}:00", "Major Regime": regime,
            "Regime Start": segment.get("start"),
            "Regime End": "OPEN / CURRENT" if pd.isna(segment.get("end")) else segment.get("end"),
            "Regime True / False": segment.get("validation", snap["regime_validation"]), "Decision": decision,
            "KNN Priority": knn_rank, "Greedy Priority": greedy_rank, "Priority Score": round(score, 2),
            "Reliability %": round(snap["reliability"], 2), "Avg Error %": error_display,
            "Move %": round(move_pct, 5), "NLP Rank": "-", "NLP Impact": "-", "NLP News": "-",
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out

    nlp = _nlp_table(days=days, anchor=anchor)
    if not nlp.empty:
        nlp = nlp.copy()
        nlp["join_hour"] = _dt_series(nlp["NLP Time"]).dt.floor("h")
        best = nlp.sort_values(["NLP Rank", "NLP Time"], ascending=[True, False]).drop_duplicates("join_hour")
        mapper = best.set_index("join_hour")[["NLP Rank", "NLP Impact", "NLP News"]].to_dict("index")
        for idx, ts in out["Time"].items():
            item = mapper.get(pd.Timestamp(ts).floor("h"))
            if item:  # Do not copy today's latest news into unrelated historical hours.
                out.at[idx, "NLP Rank"] = item.get("NLP Rank", "-")
                out.at[idx, "NLP Impact"] = item.get("NLP Impact", "-")
                out.at[idx, "NLP News"] = item.get("NLP News", "-")

    return out.sort_values(["KNN Priority", "Greedy Priority", "Time"], ascending=[True, True, True]).reset_index(drop=True)


def _less_risky_bias(row: pd.Series) -> str:
    """Return the safest directional bias without forcing a trade through weak evidence."""
    decision = str(row.get("Decision") or "WAIT").upper().strip()
    reliability = float(pd.to_numeric(pd.Series([row.get("Reliability %")]), errors="coerce").fillna(0).iloc[0])
    valid = str(row.get("Regime True / False") or "").upper()
    if reliability < 32 or "FALSE" in valid:
        return "WAIT"
    if decision in {"BUY", "SELL"}:
        return decision
    regime = str(row.get("Major Regime") or "").upper()
    if any(token in regime for token in ("BULL", "UP", "RALLY")):
        return "BUY"
    if any(token in regime for token in ("BEAR", "DOWN", "DROP")):
        return "SELL"
    return "WAIT"


def _standard_detail_table(label: str, days: int, source: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(source, pd.DataFrame) or source.empty:
        return pd.DataFrame()
    out = source.copy()
    for column in ("KNN Priority", "Greedy Priority", "Priority Score", "Reliability %"):
        out[column] = pd.to_numeric(out.get(column), errors="coerce")
    out["KNN Score /10"] = ((15.0 - out["KNN Priority"].fillna(14.0)) / 14.0 * 10.0).clip(0, 10)
    out["Greedy Score /10"] = ((15.0 - out["Greedy Priority"].fillna(14.0)) / 14.0 * 10.0).clip(0, 10)
    out["Reliability /10"] = (out["Reliability %"].fillna(0.0) / 10.0).clip(0, 10)
    out["Regime Score /10"] = (
        (out["Priority Score"].fillna(50.0) / 10.0).clip(0, 10) * 0.40
        + out["Reliability /10"] * 0.25
        + out["KNN Score /10"] * 0.20
        + out["Greedy Score /10"] * 0.15
    ).clip(0, 10)
    out["Less Risky Bias"] = out.apply(_less_risky_bias, axis=1)
    out["Standard"] = label
    out["Range"] = f"{days} day" if days == 1 else f"{days} days"
    out = out.sort_values(
        ["KNN Priority", "Greedy Priority", "Regime Score /10", "Time"],
        ascending=[True, True, False, False], na_position="last",
    ).reset_index(drop=True)
    out.insert(0, "Ascending Priority", range(1, len(out) + 1))
    columns = [
        "Ascending Priority", "Standard", "Range", "Time", "Hour", "Major Regime",
        "Decision", "Less Risky Bias", "Regime Score /10", "KNN Priority", "KNN Score /10",
        "Greedy Priority", "Greedy Score /10", "Reliability /10", "Regime True / False",
        "Regime Start", "Regime End", "NLP Rank", "NLP Impact", "NLP News",
    ]
    available = [c for c in columns if c in out.columns]
    result = out[available].copy()
    for column in ("Regime Score /10", "KNN Priority", "KNN Score /10", "Greedy Priority", "Greedy Score /10", "Reliability /10"):
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce").round(2)
    # 25 days on H1 is at most 600 rows. Keep the full requested range while
    # preventing accidental multi-thousand-row mobile rendering.
    return result.head(min(600, max(24, days * 24)))


def regime_standard_detail_tables(force: bool = False) -> Dict[str, pd.DataFrame]:
    """Return three cached, mobile-bounded tables for 1D, 5D and 25D standards."""
    cache_key = "regime_standard_detail_tables_20260617"
    signature_key = "regime_standard_detail_signature_20260617"
    ohlc = _normalize_ohlc()
    latest = str(ohlc["time"].iloc[-1]) if isinstance(ohlc, pd.DataFrame) and not ohlc.empty and "time" in ohlc.columns else "NO_DATA"
    signature = (latest, len(ohlc) if isinstance(ohlc, pd.DataFrame) else 0, str(st.session_state.get("symbol", "EURUSD")), str(st.session_state.get("timeframe", "H1")))
    cached = st.session_state.get(cache_key)
    if not force and st.session_state.get(signature_key) == signature and isinstance(cached, dict):
        if all(isinstance(cached.get(k), pd.DataFrame) for k in ("lower", "medium", "higher")):
            return cached
    if not force and not bool(st.session_state.get("settings_calculation_lock_20260617", False)):
        # Ordinary Lunch/Dinner tab switches are read-only. The existing main
        # Settings Run Calculation is the only place allowed to build the 1/5/25
        # day tables. Missing cache means not-ready, never a hidden recalculation.
        return {"lower": pd.DataFrame(), "medium": pd.DataFrame(), "higher": pd.DataFrame()}

    specs = (("lower", "Lower Standard", 1), ("medium", "Medium Standard", 5), ("higher", "Higher Standard", 25))
    tables: Dict[str, pd.DataFrame] = {}
    for key, label, days in specs:
        tables[key] = _standard_detail_table(label, days, merged_hourly_regime_nlp_priority(days=days))
    st.session_state[cache_key] = tables
    st.session_state[signature_key] = signature
    return tables


def regime_standard_table(force: bool = False) -> pd.DataFrame:
    """Compact summary of the same three detailed regime-standard tables."""
    details = regime_standard_detail_tables(force=force)
    rows = []
    for key, label, days in (("lower", "Lower Standard", 1), ("medium", "Middle Standard", 5), ("higher", "Higher Standard", 25)):
        usable = details.get(key, pd.DataFrame())
        if not isinstance(usable, pd.DataFrame) or usable.empty:
            continue
        def mean(column: str, default: float) -> float:
            values = pd.to_numeric(usable.get(column), errors="coerce").dropna()
            return float(values.mean()) if not values.empty else default
        regime = "-"
        if "Major Regime" in usable.columns:
            modes = usable["Major Regime"].astype(str).replace("", np.nan).dropna().mode()
            if not modes.empty:
                regime = str(modes.iloc[0])
        bias = "WAIT"
        if "Less Risky Bias" in usable.columns:
            modes = usable["Less Risky Bias"].astype(str).replace("", np.nan).dropna().mode()
            if not modes.empty:
                bias = str(modes.iloc[0])
        rows.append({
            "Standard": label,
            "Range": f"{days} day" if days == 1 else f"{days} days",
            "Rows": int(len(usable)),
            "Major Regime": regime,
            "Less Risky Bias": bias,
            "Regime Score /10": round(mean("Regime Score /10", 5.0), 2),
            "KNN Priority": round(mean("KNN Priority", 14.0), 2),
            "KNN Score /10": round(mean("KNN Score /10", 0.71), 2),
            "Greedy Priority": round(mean("Greedy Priority", 14.0), 2),
            "Greedy Score /10": round(mean("Greedy Score /10", 0.71), 2),
            "Reliability /10": round(mean("Reliability /10", 5.0), 2),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(["KNN Priority", "Greedy Priority", "Regime Score /10"], ascending=[True, True, False]).reset_index(drop=True)
    out.insert(0, "Ascending Priority", range(1, len(out) + 1))
    st.session_state["regime_standard_table_20260617"] = out
    return out
