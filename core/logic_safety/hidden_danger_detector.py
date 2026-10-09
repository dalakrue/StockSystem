"""Hidden Danger Detector."""
from __future__ import annotations
from typing import Any, Dict, List
from ._shared import current_values, danger_label, clamp


def detect(metrics: Dict[str, Any], drift: Dict[str, Any] | None = None, data_quality: Dict[str, Any] | None = None, signal: Dict[str, Any] | None = None, conflicts: Dict[str, Any] | None = None, regime: Dict[str, Any] | None = None) -> Dict[str, Any]:
    v = current_values(metrics)
    drift = drift or {}; data_quality = data_quality or {}; signal = signal or {}; conflicts = conflicts or {}; regime = regime or {}
    dangers: List[Dict[str, Any]] = []
    def add(name, severity, reason, action):
        dangers.append({"Danger": name, "Severity": int(clamp(severity, 0, 100)), "Reason": reason, "Suggested Defensive Action": action})
    if v["regime_confidence"] < 55: add("Regime Conflict", 62, "Regime confidence is weak or unavailable.", "Do not overtrust regime direction.")
    if v["forecast_agreement"] < 58: add("Forecast Conflict", 60, "Forecast agreement/confidence is below safe threshold.", "Wait for cleaner forecast alignment.")
    if conflicts.get("conflict_count", 0) >= 2: add("KNN/Greedy or source conflict", 68, "Multiple conflict-matrix rows are conflicting.", "Reduce confidence and compare visible KNN/Greedy rows.")
    if v["exit_risk"] >= 65: add("High Exit Risk", v["exit_risk"], "Exit risk is elevated.", "Avoid forced entry; protect or wait.")
    if v["tp_quality"] < 50: add("Low TP Quality", 58, "TP quality is weak relative to risk.", "Avoid chasing; require better reward/risk.")
    if drift.get("drift_level") == "High": add("Prediction Drift", 72, "Recent prediction/price drift is high or rising.", "Reduce forecast trust.")
    if v["market_quality"] < 55: add("Weak Market Quality", 61, "Market quality/tradeability is weak.", "Wait for higher-quality hour.")
    if signal.get("label") == "Unstable": add("Signal Instability", 70, "Signals flipped too often in recent candles.", "Wait for stable confirmation.")
    if data_quality.get("status") == "FAIL": add("Data Quality Failure", 88, data_quality.get("most_serious_issue", "data issue"), "No-trade until data is fixed.")
    elif data_quality.get("status") == "WARNING": add("Data Staleness / Quality Warning", 65, data_quality.get("most_serious_issue", "data warning"), "Reduce logic health and verify latest candle.")
    if int(drift.get("band_break_count", 0) or 0) > 1: add("Band Break Risk", 64, "Recent price movement broke expected band more than once.", "Wait for volatility to normalize.")
    if regime.get("risk_label") in {"Exhausted", "Regime Break Warning", "Change Pressure Rising"}: add("Regime Aging Risk", 66, regime.get("reason", "regime is aging"), "Do not assume old regime continues.")
    overconf = v["raw_confidence"] - min(v["forecast_agreement"], v["prediction_reliability"], v["regime_confidence"])
    if overconf >= 25: add("Overconfidence Risk", 67, "Raw confidence is much higher than supporting trust inputs.", "Use calibrated confidence, not raw confidence.")
    if not dangers:
        add("No critical hidden danger detected", 18, "Current wrapper did not find a major logic danger.", "Continue normal risk management.")
    max_sev = max(d["Severity"] for d in dangers)
    main = sorted(dangers, key=lambda d: d["Severity"], reverse=True)[0]
    return {"danger_level": danger_label(max_sev), "danger_score": max_sev, "main_danger": main["Danger"], "reason": main["Reason"], "suggested_defensive_action": main["Suggested Defensive Action"], "dangers": dangers, "secondary_dangers": [d["Danger"] for d in sorted(dangers, key=lambda d: d["Severity"], reverse=True)[1:6]]}
