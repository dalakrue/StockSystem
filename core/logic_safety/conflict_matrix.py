"""Logic Conflict Matrix."""
from __future__ import annotations
from typing import Any, Dict, List
from ._shared import current_values, clamp


def _status(diff: float, weak: bool = False) -> str:
    if weak:
        return "Mixed"
    if abs(diff) >= 35:
        return "Conflict"
    if abs(diff) >= 18:
        return "Mixed"
    return "Aligned"


def build(metrics: Dict[str, Any], drift: Dict[str, Any] | None = None, signal: Dict[str, Any] | None = None) -> Dict[str, Any]:
    v = current_values(metrics)
    drift = drift or {}
    signal = signal or {}
    rows: List[Dict[str, Any]] = []
    def add(a, b, status, strength, explanation, action):
        rows.append({"Source A": a, "Source B": b, "Status": status, "Strength": strength, "Explanation": explanation, "Defensive Action": action})
    add("Regime", "Forecast", _status(v["regime_confidence"] - v["forecast_agreement"]), round(abs(v["regime_confidence"] - v["forecast_agreement"]), 1), "Compares regime confidence with forecast agreement.", "Reduce confidence when not aligned.")
    add("Regime", "Priority", _status(v["regime_confidence"] - v["master_score"]), round(abs(v["regime_confidence"] - v["master_score"]), 1), "Compares current regime trust with master/priority score.", "Wait if priority is high but regime is weak.")
    add("KNN", "Greedy", "Partial" if "knn" not in str(metrics).lower() else "Mixed", "Partial", "KNN/Greedy raw outputs were not safely exposed as scalars in session state." if "knn" not in str(metrics).lower() else "KNN/Greedy context detected; detailed comparison is display-only.", "Manually compare visible KNN and Greedy rows.")
    add("PowerBI", "Actual", "Conflict" if drift.get("drift_level") == "High" else "Mixed" if drift.get("drift_level") == "Medium" else "Aligned", drift.get("drift_score", "Partial"), "Uses Prediction Drift Monitor as PowerBI/actual drift proxy.", "Reduce forecast trust when drift rises.")
    add("NLP", "Price Direction", "Partial", "Partial", "Local NLP context may exist, but no external/news API is used.", "Use price confirmation before trusting NLP bias.")
    add("Market Quality", "Entry Signal", _status(v["market_quality"] - v["master_score"]), round(abs(v["market_quality"] - v["master_score"]), 1), "Checks whether entry/priority is supported by market quality.", "Avoid entries in poor market quality.")
    add("TP Quality", "Exit Risk", "Conflict" if v["tp_quality"] < 50 and v["exit_risk"] > 60 else "Mixed" if v["exit_risk"] > 65 else "Aligned", round(v["exit_risk"], 1), "High exit risk with weak TP quality is dangerous.", "Prefer wait/no-trade or smaller confidence.")
    add("History Similarity", "Current Signal", "Partial", "Partial", "History similarity is included when existing system exposes it; otherwise partial.", "Do not rely on similarity if table is not loaded.")
    add("Forecast Agreement", "Decision", "Mixed" if v["forecast_agreement"] < 60 else "Aligned", round(v["forecast_agreement"], 1), "Decision trust depends on forecast agreement.", "Require pullback confirmation if weak.")
    add("Signal Stability", "Entry Timing", "Conflict" if signal.get("label") == "Unstable" else "Mixed" if signal.get("label") == "Mixed" else "Aligned", signal.get("stability_score", "Partial"), "Unstable signals are bad for immediate entries.", "Wait for stable candle confirmation.")
    conflict_count = sum(1 for r in rows if r["Status"] == "Conflict")
    mixed_count = sum(1 for r in rows if r["Status"] in {"Mixed", "Partial"})
    return {"rows": rows, "conflict_count": conflict_count, "mixed_count": mixed_count, "status": "Conflict" if conflict_count else "Mixed" if mixed_count else "Aligned"}
