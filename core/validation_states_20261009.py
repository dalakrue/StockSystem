"""Validation states for research exits (2026-10-09).

States
------
RESEARCH ONLY              — fitted on training data; diagnostics only.
INSUFFICIENT SAMPLE        — compatible training sample < 30 trades.
FAILED DIAGNOSTIC          — later-period diagnostics both negative
                             ("REMOVE FROM RESEARCH" classification).
REUSED-TEST DIAGNOSTIC ONLY — a portfolio run whose "test" period is the
                             already-mined last year (2025-10-01 → 2026-10-05):
                             diagnostic, not validation.
FRESH VALIDATION PENDING   — promotion requested, no fresh data yet.
FRESH VALIDATION PASSED    — passed on frozen params + unused-for-selection
                             data (none exist in this project).

Live promotion requires a recorded validation manifest. ``build_validation_manifest``
returns "pending — no fresh data" because no fresh data exists: the 4y dataset
selected the entry equations, so the last year is REUSED test, never "unseen".
Strict_Valid stays NO everywhere; import candidates are research-only.
"""
from __future__ import annotations

from typing import Any, Dict, List

STATES = (
    "RESEARCH ONLY",
    "INSUFFICIENT SAMPLE",
    "FAILED DIAGNOSTIC",
    "REUSED-TEST DIAGNOSTIC ONLY",
    "FRESH VALIDATION PENDING",
    "FRESH VALIDATION PASSED",
)

# Central criteria config — provenance: config/research_fix_20261009.json
CRITERIA = {
    "min_training_trades": 30,
    "reward_risk_gate": "(TP_pips - cost_pips) >= 0.5 * SL_pips  (cost_pips = 1.0)",
    "stop_distance_budget_pips": 103.0,
    "cost_scenario": "legacy_1pip (1 pip deducted once)",
    "execution": "SL-first intrabar default; adverse stop gaps fill at observed open",
    "data_requirement": "frozen strategy + param version; data unused for selection; "
                        "no fresh data currently exists",
}


def classify_equation(compatible_training_trades: float | None,
                      classification: str | None) -> str:
    """Map a research row to its equation-level validation state."""
    trades = compatible_training_trades or 0.0
    if trades < CRITERIA["min_training_trades"]:
        return "INSUFFICIENT SAMPLE"
    if (classification or "").strip().upper() == "REMOVE FROM RESEARCH":
        return "FAILED DIAGNOSTIC"
    return "RESEARCH ONLY"


def build_validation_manifest(*, strategy_version: str, exit_params_version: str,
                              test_period: str, sample_trades: int,
                              risk_criteria: Dict[str, Any] | None = None,
                              cost_scenario: str = "legacy_1pip",
                              execution: str = "SL-first intrabar; adverse gaps at observed open",
                              requested_by: str = "") -> Dict[str, Any]:
    """Build a live-promotion validation manifest.

    Because no fresh (unused-for-selection) data exists, this ALWAYS returns a
    manifest with status "pending — no fresh data". It records everything a
    future validation run must satisfy; nothing here approves live use.
    """
    manifest = {
        "manifest_version": "validation-manifest-20261009-v1",
        "status": "pending — no fresh data",
        "strategy_version": strategy_version,
        "exit_params_version": exit_params_version,
        "test_period": test_period,
        "sample_trades": int(sample_trades),
        "risk_criteria": risk_criteria or dict(CRITERIA),
        "cost_scenario": cost_scenario,
        "execution": execution,
        "pass_fail_rules": {
            "sample": f"sample_trades >= {CRITERIA['min_training_trades']} on fresh data",
            "risk_gate": CRITERIA["reward_risk_gate"] + " and SL <= 103.0 pips",
            "diagnostics": "positive net on fresh data with all risk checks passing",
        },
        "blockers": [
            "no fresh data exists: the 4y dataset selected the entry equations, "
            "so 2025-10-01 → 2026-10-05 is REUSED test, never unseen",
            "Strict_Valid = NO for all 240 equations",
        ],
        "requested_by": requested_by,
        "live_approved": False,
    }
    return manifest


def promotion_checklist() -> List[str]:
    return [
        "1. Freeze strategy + exit param versions (recorded in manifest).",
        "2. Obtain data strictly unused for selection (none exists yet).",
        "3. Run replay with identical entry signals, SL-first, 1-pip cost.",
        "4. Apply all active risk checks; record rejections with reasons.",
        "5. Require sample >= 30 trades and positive diagnostics on the fresh data.",
        "6. Record pass/fail reasons in the manifest before any live promotion.",
    ]
