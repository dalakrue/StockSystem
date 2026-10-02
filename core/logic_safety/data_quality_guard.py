"""Data Quality Guard for OHLC/history data."""
from __future__ import annotations
from typing import Any, Dict, List
from ._shared import normalize_ohlc


def check(df: Any) -> Dict[str, Any]:
    x = normalize_ohlc(df)
    issues: List[str] = []
    affected: List[str] = []
    if x is None or len(x) == 0:
        return {"status": "WARNING", "issue_count": 1, "most_serious_issue": "No usable dataframe found", "issues": ["No usable OHLC/history dataframe found"], "affected_rows": "unknown", "defensive_action": "Run normal data loading first; do not trust safety score until data is available."}
    required = ["time", "close"]
    for c in required:
        if c not in x.columns:
            issues.append(f"Missing required column: {c}")
    if len(x) < 60:
        issues.append("Too few candles for robust safety check")
    try:
        if x["time"].isna().any(): issues.append("Invalid timestamps detected")
        if not x["time"].is_monotonic_increasing: issues.append("Timestamp order is not increasing")
        dup = int(x["time"].duplicated().sum())
        if dup: issues.append(f"Duplicate timestamps detected: {dup}")
        gaps = x["time"].diff().dropna()
        if len(gaps):
            modal = gaps.mode().iloc[0] if len(gaps.mode()) else gaps.median()
            gap_count = int((gaps > modal * 1.75).sum())
            if gap_count: issues.append(f"Possible missing candles / time gaps: {gap_count}")
    except Exception:
        issues.append("Timestamp validation partial failure")
    for c in ["open", "high", "low", "close"]:
        if c in x.columns:
            try:
                nulls = int(x[c].isna().sum())
                if nulls: issues.append(f"NaN values in {c}: {nulls}")
                import numpy as np
                infs = int(np.isinf(x[c]).sum())
                if infs: issues.append(f"Infinite values in {c}: {infs}")
            except Exception:
                pass
    try:
        if all(c in x.columns for c in ["open", "high", "low", "close"]):
            flat = int(((x["open"] == x["high"]) & (x["high"] == x["low"]) & (x["low"] == x["close"])).sum())
            if flat > max(3, len(x) * 0.03): issues.append(f"Many flat candles detected: {flat}")
            rng = (x["high"] - x["low"]).abs()
            med = float(rng.rolling(50, min_periods=10).median().iloc[-1] or rng.median() or 0)
            if med > 0:
                outliers = int((rng > med * 8).sum())
                if outliers: issues.append(f"Abnormal outlier candle ranges: {outliers}")
            body = (x["close"] - x["open"]).abs()
            wick = (x["high"] - x["low"]).abs()
            wick_out = int(((wick > body.replace(0, body.median() or 1e-12) * 12) & (wick > med * 3)).sum()) if med > 0 else 0
            if wick_out: issues.append(f"Abnormal wick risk candles: {wick_out}")
    except Exception:
        issues.append("OHLC candle-shape validation partial failure")
    try:
        import pandas as pd
        last_time = pd.Timestamp(x["time"].iloc[-1])
        now = pd.Timestamp.now(tz=last_time.tz) if last_time.tzinfo else pd.Timestamp.now()
        age_hours = max((now - last_time).total_seconds() / 3600.0, 0.0)
        if age_hours > 3.2:
            issues.append(f"Stale uploaded/live data: latest candle age about {age_hours:.1f}h")
        if age_hours < 0.15:
            issues.append("Latest candle may be incomplete")
    except Exception:
        pass
    if "volume" in x.columns:
        try:
            zero_vol = int((x["volume"].fillna(0) == 0).sum())
            if zero_vol > max(5, len(x) * 0.2): issues.append(f"Zero/blank volume is common: {zero_vol} rows")
        except Exception:
            pass
    if issues:
        status = "FAIL" if any("Missing required" in s or "No usable" in s for s in issues) or len(issues) >= 7 else "WARNING"
        action = "Reduce trust and activate defensive/no-trade review before entry."
    else:
        status = "PASS"
        action = "Data quality checks passed for the safety wrapper."
    return {"status": status, "issue_count": len(issues), "most_serious_issue": issues[0] if issues else "None", "issues": issues, "affected_rows": "; ".join(affected) if affected else "see issue text", "defensive_action": action, "rows_checked": int(len(x))}
