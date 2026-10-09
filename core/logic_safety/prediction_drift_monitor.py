"""Prediction Drift Monitor.
Uses existing prediction history if present; otherwise a transparent volatility/error proxy."""
from __future__ import annotations
from typing import Any, Dict
from ._shared import normalize_ohlc, clamp, find_number


def monitor(df: Any, metrics: Dict[str, Any]) -> Dict[str, Any]:
    x = normalize_ohlc(df)
    if x is None or len(x) < 20 or "close" not in x.columns:
        return {"drift_level": "Medium", "drift_score": 50.0, "source": "partial/no dataframe", "forecast_trust_adjustment": "Reduced until price history loads", "avg_close_error": None, "direction_error": None, "band_break_count": 0, "recent_error_trend": "Unknown", "warning": "No reliable close history found."}
    try:
        import numpy as np
        import pandas as pd
        close = x["close"].astype(float)
        # Look for existing prediction columns first.
        pred_cols = [c for c in x.columns if any(t in str(c).lower() for t in ["pred", "forecast", "projection", "expected"])]
        used_col = None
        errors = None
        for c in pred_cols:
            vals = pd.to_numeric(x[c], errors="coerce")
            if vals.notna().sum() >= 10:
                used_col = c
                errors = (vals - close).abs() / close.replace(0, np.nan) * 10000.0  # pips-ish for EURUSD percent-scaled
                break
        if errors is None:
            # Transparent fallback: use naive previous-close forecast error as drift proxy.
            used_col = "naive previous-close proxy"
            errors = (close.shift(1) - close).abs() / close.replace(0, np.nan) * 10000.0
        errors = errors.replace([np.inf, -np.inf], np.nan).dropna()
        avg_error = float(errors.tail(24).mean()) if len(errors) else 0.0
        last_error = float(errors.tail(6).mean()) if len(errors) else 0.0
        prior_error = float(errors.tail(30).head(24).mean()) if len(errors) >= 30 else avg_error
        trend = "Rising" if last_error > prior_error * 1.15 else "Falling" if last_error < prior_error * 0.85 else "Flat"
        ret = close.diff()
        direction_error = float((ret.tail(24).fillna(0).apply(lambda v: 1 if v >= 0 else -1) != ret.shift(1).tail(24).fillna(0).apply(lambda v: 1 if v >= 0 else -1)).mean() * 100) if len(ret) >= 30 else None
        rolling = close.pct_change().rolling(48, min_periods=12).std().fillna(close.pct_change().std()).fillna(0)
        band = rolling * close * 2.2
        band_breaks = int(((close - close.shift(1)).abs() > band).tail(48).sum()) if len(close) > 50 else 0
        drift_score = clamp(avg_error * 3.0 + (12 if trend == "Rising" else 0) + band_breaks * 3.5, 0, 100, 35)
        level = "High" if drift_score >= 65 else "Medium" if drift_score >= 35 else "Low"
        return {"drift_level": level, "drift_score": round(drift_score, 1), "source": str(used_col), "forecast_trust_adjustment": "Reduced" if level == "High" else "Caution" if level == "Medium" else "Normal", "avg_close_error": round(avg_error, 4), "error_1h": round(float(errors.tail(1).mean()), 4) if len(errors) else None, "error_2h": round(float(errors.tail(2).mean()), 4) if len(errors) else None, "error_4h": round(float(errors.tail(4).mean()), 4) if len(errors) else None, "error_6h": round(float(errors.tail(6).mean()), 4) if len(errors) else None, "direction_error": None if direction_error is None else round(direction_error, 1), "band_break_count": band_breaks, "recent_error_trend": trend, "warning": "Forecast trust reduced" if level == "High" else "No major drift alarm"}
    except Exception as exc:
        return {"drift_level": "Medium", "drift_score": 50.0, "source": "partial/error", "forecast_trust_adjustment": "Reduced until drift monitor is reviewed", "avg_close_error": None, "direction_error": None, "band_break_count": 0, "recent_error_trend": "Unknown", "warning": str(exc)[:140]}
