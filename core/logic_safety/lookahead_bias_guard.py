"""Lookahead Bias Guard.
Static/structural diagnostics only; it does not claim full formal proof.
"""
from __future__ import annotations
from typing import Any, Dict, List


def check(df: Any = None, metrics: Dict[str, Any] | None = None) -> Dict[str, Any]:
    issues: List[str] = []
    notes: List[str] = []
    status = "PARTIAL"
    try:
        if df is not None and hasattr(df, "columns"):
            cols = [str(c).lower() for c in df.columns]
            future_like = [c for c in cols if any(t in c for t in ["future", "actual_result", "result", "next_close", "target"])]
            decision_like = [c for c in cols if any(t in c for t in ["decision", "score", "priority", "signal"])]
            if future_like and decision_like:
                notes.append("Result/target-style columns exist near decision columns. Review formulas to ensure they are evaluation-only.")
            else:
                notes.append("No obvious future/result columns detected in the visible dataframe.")
            status = "PASS" if not future_like else "WARNING"
    except Exception as exc:
        issues.append(str(exc)[:140])
    if status == "PARTIAL":
        notes.append("Partial Check — manual review recommended. Runtime wrapper cannot prove every historical formula avoids future candles.")
    return {"status": status, "detected_risk": issues[0] if issues else (notes[0] if notes else "No obvious risk"), "issues": issues, "notes": notes, "explanation": "Historical decision rows must only use information available at that historical time. Actual/result columns should be used for evaluation only."}
