"""Field 7 certificate formatting."""
from __future__ import annotations
from typing import Any, Mapping


def certificate_rows(summary: Mapping[str, Any]) -> list[tuple[str, Any]]:
    return [
        ("Canonical decision", summary.get("canonical_decision")),
        ("Research-approved action", summary.get("research_approved_action")),
        ("Approved horizons", ", ".join(summary.get("approved_horizons") or []) or "None"),
        ("Abstained horizons", ", ".join(summary.get("abstained_horizons") or []) or "None"),
        ("Structural stability", summary.get("structural_stability")),
        ("Model confidence set", summary.get("model_confidence_set")),
        ("Forecastability 1H", summary.get("forecastability_1h")),
        ("Forecastability 3H", summary.get("forecastability_3h")),
        ("Forecastability 6H", summary.get("forecastability_6h")),
        ("Raw target", summary.get("raw_target")),
        ("Bias-corrected target", summary.get("bias_corrected_target")),
        ("Conformal coverage", summary.get("conformal_coverage")),
        ("Nominal expected value", summary.get("nominal_ev")),
        ("Robust expected value", summary.get("robust_ev")),
        ("Tail-risk status", summary.get("tail_risk")),
        ("Decision stability", summary.get("decision_stability")),
        ("Regime remaining edge", summary.get("regime_remaining_edge")),
        ("Event risk", summary.get("event_state")),
        ("Overfitting risk", summary.get("overfitting_risk")),
        ("Research trust score", summary.get("research_trust_score")),
        ("Final risk multiplier", summary.get("risk_multiplier")),
        ("Research status", summary.get("research_status")),
    ]
