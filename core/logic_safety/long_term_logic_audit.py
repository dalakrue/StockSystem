"""Long-Term Logic Audit Table."""
from __future__ import annotations
from typing import Any, Dict, Tuple
from ._shared import normalize_ohlc


def build(df: Any, metrics: Dict[str, Any], health: Dict[str, Any], danger: Dict[str, Any], drift: Dict[str, Any], guard: Dict[str, Any], data_quality: Dict[str, Any]):
    try:
        import pandas as pd
        import numpy as np
    except Exception:
        return None, {"message": "pandas unavailable"}
    x = normalize_ohlc(df)
    if x is None or len(x) == 0:
        return pd.DataFrame(columns=["Date", "Hour", "Regime", "Original Decision", "Safety Decision", "Priority", "Confidence", "Logic Health Score", "Danger Level", "Actual Direction", "Prediction Error", "Drift Level", "Conflict Count", "Data Quality Status", "Result Quality"]), {"message": "No history dataframe available"}
    rows = x.tail(min(len(x), 600)).copy()
    rows["Date"] = rows["time"].dt.strftime("%Y-%m-%d")
    rows["Hour"] = rows["time"].dt.hour
    close = pd.to_numeric(rows.get("close"), errors="coerce")
    direction = close.diff().apply(lambda v: "UP" if v > 0 else "DOWN" if v < 0 else "FLAT")
    audit = pd.DataFrame({
        "Date": rows["Date"],
        "Hour": rows["Hour"],
        "Regime": str(metrics.get("current_regime", "Current/Unknown")),
        "Original Decision": guard.get("original_decision", "Unknown"),
        "Safety Decision": guard.get("safety_adjusted_decision", "Unknown"),
        "Priority": metrics.get("master_score", "Partial"),
        "Confidence": metrics.get("raw_confidence", "Partial"),
        "Logic Health Score": health.get("score", "Partial"),
        "Danger Level": danger.get("danger_level", "Partial"),
        "Actual Direction": direction.values,
        "Prediction Error": drift.get("avg_close_error", "Partial"),
        "Drift Level": drift.get("drift_level", "Partial"),
        "Conflict Count": metrics.get("conflict_count", "Partial"),
        "Data Quality Status": data_quality.get("status", "Partial"),
        "Result Quality": "Audit row / display-only",
    })
    ret = close.pct_change().dropna()
    summary = {
        "rows": int(len(audit)),
        "best_hour_accuracy": "Needs labeled results" if audit.empty else int(audit.groupby("Hour").size().idxmax()),
        "worst_hour_accuracy": "Needs labeled results",
        "average_logic_health": health.get("score"),
        "average_prediction_error": drift.get("avg_close_error"),
        "false_entry_rate": "Needs completed entry labels",
        "most_common_danger": danger.get("main_danger"),
    }
    return audit, summary
