"""Causal 1D/5D/25D Alpha/Delta regime analytics from one completed H1 history.

No prediction model is introduced.  The Alpha history is the signed [-10, 10]
normalization of the existing regime-strength return/range core used by
``adx_shared_sync_20260615._regime_alpha_delta``.  It is calculated once over
completed rows; the three standards are tail windows of that same history.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional
import math
import numpy as np
import pandas as pd

VERSION = "regime-window-analytics-20260618-v1"
WINDOWS = (("lower", "Lower Standard", "1 Day", 24), ("medium", "Medium Standard", "5 Days", 120), ("higher", "Higher Standard", "25 Days", 600))


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else float(default)
    except Exception:
        return float(default)


def _clip(value: Any, low: float, high: float) -> float:
    return float(max(low, min(high, _finite(value, low))))


def _find_col(frame: pd.DataFrame, aliases: Iterable[str]) -> Optional[str]:
    if not isinstance(frame, pd.DataFrame):
        return None
    norm = {str(c).strip().lower().replace("_", " "): c for c in frame.columns}
    for alias in aliases:
        key = str(alias).strip().lower().replace("_", " ")
        if key in norm:
            return norm[key]
    for alias in aliases:
        key = str(alias).strip().lower().replace("_", " ")
        for n, c in norm.items():
            if key and key in n:
                return c
    return None


def _prepare_ohlc(data: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(data, pd.DataFrame) or data.empty:
        return pd.DataFrame()
    t = _find_col(data, ("time", "datetime", "timestamp", "date"))
    c = _find_col(data, ("close", "c"))
    if t is None or c is None:
        return pd.DataFrame()
    h = _find_col(data, ("high", "h")); l = _find_col(data, ("low", "l")); o = _find_col(data, ("open", "o"))
    out = pd.DataFrame({"time": pd.to_datetime(data[t], errors="coerce", utc=True), "close": pd.to_numeric(data[c], errors="coerce")})
    out["open"] = pd.to_numeric(data[o], errors="coerce") if o else out["close"]
    out["high"] = pd.to_numeric(data[h], errors="coerce") if h else out[["open", "close"]].max(axis=1)
    out["low"] = pd.to_numeric(data[l], errors="coerce") if l else out[["open", "close"]].min(axis=1)
    out = out.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
    out["high"] = out[["open", "high", "close"]].max(axis=1)
    out["low"] = out[["open", "low", "close"]].min(axis=1)
    return out.tail(600).reset_index(drop=True)


def build_alpha_history(data: pd.DataFrame) -> pd.DataFrame:
    market = _prepare_ohlc(data)
    if market.empty:
        return pd.DataFrame()
    close = market["close"].astype(float)
    # Same directional core as existing Alpha: six-bar return divided by recent
    # percentage range. Rolling/trailing values are strictly causal.
    ret6 = close.pct_change(6) * 100.0
    range_pct = ((market["high"] - market["low"]).abs() / close.replace(0, np.nan).abs() * 100.0)
    vol_adj = range_pct.rolling(24, min_periods=6).mean().clip(lower=0.01)
    alpha = ((ret6 / vol_adj) * 2.4).replace([np.inf, -np.inf], np.nan).clip(-10.0, 10.0)
    # A short causal EMA reduces isolated spikes without changing final sign.
    alpha = alpha.ewm(span=3, adjust=False, min_periods=1).mean()
    out = market[["time", "open", "high", "low", "close"]].copy()
    out["alpha"] = alpha
    out["delta"] = out["alpha"].diff()
    out["alpha_velocity"] = out["alpha"].diff()
    out["alpha_acceleration"] = out["alpha_velocity"].diff()
    out["delta_velocity"] = out["delta"].diff()
    out["range_pct"] = range_pct
    return out.dropna(subset=["alpha"]).reset_index(drop=True)


def _normalized_slope(series: pd.Series) -> float:
    y = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    if len(y) < 2:
        return 0.0
    x = np.linspace(0.0, 1.0, len(y))
    return _finite(np.polyfit(x, y, 1)[0], 0.0)


def _regime_name(alpha: float, alpha_std: float, delta: float, existing: str = "") -> str:
    """Map each window to the project's existing regime group vocabulary."""
    existing_upper = str(existing or "").strip().upper()
    if abs(alpha) < 0.75:
        return "RANGE" if abs(delta) < 0.75 else "TRANSITION"
    direction = "BULL" if alpha > 0 else "BEAR"
    if alpha_std >= 2.5 or abs(delta) >= 1.25 or "EXPANSION" in existing_upper:
        phase = "EXPANSION"
    elif alpha_std <= 1.15 and ("COMPRESSION" in existing_upper or abs(delta) < .35):
        phase = "COMPRESSION"
    else:
        phase = "NORMAL"
    return f"{direction}_{phase}"


def _initial_row(key: str, name: str, length_name: str, requested: int, history: pd.DataFrame, existing_regime: str, existing_reliability: float) -> Dict[str, Any]:
    w = history.tail(requested).copy()
    alpha = pd.to_numeric(w["alpha"], errors="coerce").dropna()
    delta = pd.to_numeric(w["delta"], errors="coerce").dropna()
    n = int(len(alpha))
    if n == 0:
        return {"Window Name": name, "Window Length": length_name, "Actual Sample Count": 0, "Less-Risky Bias": "WAIT", "_key": key}
    a_now = _finite(alpha.iloc[-1]); d_now = _finite(delta.iloc[-1]) if len(delta) else 0.0
    a_std = _finite(alpha.std(ddof=0), 0.0); d_std = _finite(delta.std(ddof=0), 0.0)
    a_slope = _normalized_slope(alpha); d_slope = _normalized_slope(delta)
    velocity = _finite(w["alpha_velocity"].iloc[-1], 0.0); acceleration = _finite(w["alpha_acceleration"].iloc[-1], 0.0); d_velocity = _finite(w["delta_velocity"].iloc[-1], 0.0)
    neutral = 0.45
    current_sign = 1 if a_now > neutral else -1 if a_now < -neutral else 0
    signs = np.where(alpha > neutral, 1, np.where(alpha < -neutral, -1, 0))
    persistence = float(np.mean(signs == current_sign) * 100.0) if current_sign else float(np.mean(signs == 0) * 100.0)
    alpha_pos = float((alpha > 0).mean() * 100.0); delta_pos = float((delta > 0).mean() * 100.0) if len(delta) else 0.0
    sign_consistency = max(alpha_pos, 100.0 - alpha_pos)
    variability_score = 100.0 - _clip(a_std / 4.0 * 100.0, 0, 100)
    delta_stability = 100.0 - _clip(d_std / 2.5 * 100.0, 0, 100)
    duration_consistency = _clip(n / max(requested, 1) * 100.0, 0, 100)
    stability = _clip(persistence * .30 + variability_score * .25 + duration_consistency * .15 + sign_consistency * .15 + delta_stability * .15, 0, 100)
    disagreement = 100.0 if (a_now * d_now < 0 and abs(d_now) > .35) else 20.0 if abs(d_now) > .8 else 0.0
    near_zero = 100.0 - _clip(abs(a_now) / 3.0 * 100.0, 0, 100)
    slope_reversal = 100.0 if a_now * a_slope < 0 else 0.0
    rising_variability = _clip(a_std / 4.0 * 100.0, 0, 100)
    transition = _clip(near_zero * .30 + disagreement * .25 + slope_reversal * .15 + rising_variability * .15 + (100.0 - stability) * .15, 0, 100)
    missing_ratio = max(0.0, 1.0 - n / max(requested, 1))
    reliability = _clip((1.0 - missing_ratio) * 30.0 + stability * .40 + persistence * .20 + _clip(existing_reliability, 0, 100) * .10, 0, 100)
    regime = _regime_name(a_now, a_std, d_now, existing_regime)
    return {
        "Window Name": name, "Window Length": length_name, "Start Time": w["time"].iloc[0], "End Time": w["time"].iloc[-1],
        "Actual Sample Count": n, "Current Regime": regime, "Alpha Point": round(a_now, 2), "Delta Point": round(d_now, 2),
        "Mean Alpha": round(_finite(alpha.mean()), 2), "Mean Delta": round(_finite(delta.mean()), 2), "Median Alpha": round(_finite(alpha.median()), 2),
        "Alpha Slope": round(a_slope, 4), "Delta Slope": round(d_slope, 4), "Alpha Velocity": round(velocity, 4),
        "Alpha Acceleration": round(acceleration, 4), "Delta Velocity": round(d_velocity, 4), "Alpha Standard Deviation": round(a_std, 3),
        "Delta Standard Deviation": round(d_std, 3), "Alpha Positive Ratio": round(alpha_pos, 2), "Delta Positive Ratio": round(delta_pos, 2),
        "Directional Persistence": round(persistence, 2), "Regime Stability": round(stability, 2), "Transition Risk": round(transition, 2),
        "Reliability": round(reliability, 2), "Less-Risky Bias": "WAIT", "_key": key,
    }


def build_regime_window_analytics(data: pd.DataFrame, *, existing_regime: str = "", existing_reliability: float = 50.0) -> Dict[str, Any]:
    history = build_alpha_history(data)
    if history.empty:
        return {"ok": False, "version": VERSION, "message": "No completed timestamped OHLC rows.", "history": history, "tables": {}}
    rows = [_initial_row(*spec, history, existing_regime, existing_reliability) for spec in WINDOWS]
    signs = [1 if _finite(r.get("Alpha Point")) > .45 else -1 if _finite(r.get("Alpha Point")) < -.45 else 0 for r in rows]
    slopes = [1 if _finite(r.get("Alpha Slope")) > .05 else -1 if _finite(r.get("Alpha Slope")) < -.05 else 0 for r in rows]
    deltas = [1 if _finite(r.get("Delta Point")) > .15 else -1 if _finite(r.get("Delta Point")) < -.15 else 0 for r in rows]
    sign_agreement = max(signs.count(1), signs.count(-1), signs.count(0)) / 3.0 * 100.0
    slope_agreement = max(slopes.count(1), slopes.count(-1), slopes.count(0)) / 3.0 * 100.0
    delta_agreement = max(deltas.count(1), deltas.count(-1), deltas.count(0)) / 3.0 * 100.0
    alignment = (sign_agreement * .55 + slope_agreement * .25 + delta_agreement * .20)
    if all(v > 0 for v in signs) and sum(v > 0 for v in slopes) >= 2:
        alignment_label = "STRONG BULLISH ALIGNMENT"
    elif all(v < 0 for v in signs) and sum(v < 0 for v in slopes) >= 2:
        alignment_label = "STRONG BEARISH ALIGNMENT"
    elif signs[2] > 0 and signs[1] > 0 and signs[0] < 0:
        alignment_label = "SHORT-TERM BULLISH PULLBACK"
    elif signs[2] > 0 and signs[1] < 0 and signs[0] < 0 and all(v <= 0 for v in deltas):
        alignment_label = "POSSIBLE BEARISH TRANSITION"
    else:
        alignment_label = "MIXED / TRANSITION"
    tables: Dict[str, pd.DataFrame] = {}
    for row in rows:
        conflict = 100.0 - alignment
        row["Transition Risk"] = round(_clip(_finite(row["Transition Risk"]) * .72 + conflict * .28, 0, 100), 2)
        row["Reliability"] = round(_clip(_finite(row["Reliability"]) * .76 + alignment * .24, 0, 100), 2)
        a = _finite(row["Alpha Point"]); d = _finite(row["Delta Point"]); slope = _finite(row["Alpha Slope"])
        sufficient = int(row["Actual Sample Count"]) >= min(12, next(x[3] for x in WINDOWS if x[0] == row["_key"]) // 2)
        if not sufficient or row["Reliability"] < 55 or row["Transition Risk"] >= 62 or abs(a) < .75 or (a * d < 0 and abs(d) >= .45) or alignment < 58:
            bias = "WAIT"
        elif a > 0 and slope >= -.10 and signs[2] >= 0:
            bias = "BUY"
        elif a < 0 and slope <= .10 and signs[2] <= 0:
            bias = "SELL"
        else:
            bias = "WAIT"
        row["Less-Risky Bias"] = bias
        row["Cross-Window Alignment"] = round(alignment, 2)
        row["Alignment Interpretation"] = alignment_label
        key = row.pop("_key")
        tables[key] = pd.DataFrame([row])
    return {
        "ok": True, "version": VERSION, "history": history, "tables": tables,
        "alignment": {"score": round(alignment, 2), "label": alignment_label, "signs": signs, "slopes": slopes, "deltas": deltas},
        "last_completed_candle": str(history["time"].iloc[-1]), "actual_history_rows": int(len(history)),
    }
