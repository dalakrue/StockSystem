"""Logic Health Score: tells whether original outputs are safe to trust."""
from __future__ import annotations
from typing import Any, Dict, List
from ._shared import clamp, current_values, score_label


def calculate(metrics: Dict[str, Any], drift: Dict[str, Any] | None = None, data_quality: Dict[str, Any] | None = None, signal: Dict[str, Any] | None = None, conflicts: Dict[str, Any] | None = None) -> Dict[str, Any]:
    v = current_values(metrics)
    drift = drift or {}
    data_quality = data_quality or {}
    signal = signal or {}
    conflicts = conflicts or {}
    drift_penalty = clamp(drift.get("drift_score", 35), 0, 100) * 0.16
    data_penalty = float(data_quality.get("issue_count", 0) or 0) * 3.5
    conflict_penalty = float(conflicts.get("conflict_count", 0) or 0) * 4.0
    exit_penalty = max(0.0, v["exit_risk"] - 55.0) * 0.24
    score = (
        v["forecast_agreement"] * 0.17 +
        v["prediction_reliability"] * 0.17 +
        v["regime_confidence"] * 0.16 +
        v["market_quality"] * 0.14 +
        v["tp_quality"] * 0.09 +
        clamp(signal.get("stability_score", 60), default=60) * 0.12 +
        max(0.0, 100.0 - drift_penalty) * 0.08 +
        max(0.0, 100.0 - data_penalty) * 0.07
    ) - conflict_penalty - exit_penalty
    score = clamp(score, 0, 100, 50)
    positives: List[str] = []
    negatives: List[str] = []
    if v["forecast_agreement"] >= 70: positives.append("forecast agreement supports trust")
    if v["prediction_reliability"] >= 70: positives.append("prediction reliability is acceptable")
    if v["regime_confidence"] >= 70: positives.append("regime confidence supports the decision")
    if v["market_quality"] >= 70: positives.append("market quality is supportive")
    if v["exit_risk"] >= 65: negatives.append("exit risk is elevated")
    if v["tp_quality"] < 50: negatives.append("TP quality is weak")
    if data_quality.get("status") in {"WARNING", "FAIL"}: negatives.append("data quality warning reduces trust")
    if drift.get("drift_level") in {"High", "Critical"}: negatives.append("prediction drift is rising")
    if conflicts.get("conflict_count", 0): negatives.append(f"{conflicts.get('conflict_count')} logic conflicts detected")
    if signal.get("label") == "Unstable": negatives.append("signals are flipping too often")
    defensive = "Trade logic can be read normally, but still use risk control."
    if score < 60:
        defensive = "Do not force entry. Wait for cleaner confirmation or reduce confidence."
    elif score < 75:
        defensive = "Use caution. Confirm with fresh candle, regime, and drift before entry."
    return {
        "score": round(score, 1),
        "label": score_label(score),
        "trust_level": "High" if score >= 80 else "Medium" if score >= 60 else "Low",
        "main_positive": positives[0] if positives else "No strong positive trust driver detected",
        "main_negative": negatives[0] if negatives else "No critical trust reducer detected",
        "positives": positives,
        "negatives": negatives,
        "defensive_action": defensive,
    }
