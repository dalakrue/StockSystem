"""ONE cost model shared by simulation, metrics, risk checks and exports.

Declared costs (provenance: config/audited_execution.json):
    spread 1.0 pip, slippage 0.0, commission 0.0, financing 0.0 / day.

Deduction rule — costs are deducted EXACTLY ONCE:
  * OHLC/mid simulation (research replay on H1 OHLC): the declared cost is
    applied once per trade:  net_pips = gross_pips - total_cost_pips.
  * Broker bid/ask fills: the spread is already embedded in the fill prices,
    so NO additional spread is deducted (double-deduction is forbidden).
    Only non-embedded costs (commission, financing) may still apply.

Scenarios:
  * 'legacy_1pip'      — 1 pip spread deducted once. Legacy reproduction
                         scenario; it is the app's historical convention, NOT
                         a measured broker cost.
  * 'sensitivity_3pip' — 3 pips total cost deducted once. Sensitivity
                         analysis ONLY, explicitly labelled
                         "sensitivity — NOT a measured broker cost".

Reward/risk formulas (both documented; the gate uses the corrected one):
  * legacy reproduction: gross RR = TP_pips / SL_pips
    (core/live_execution.py :: target_display_columns 'Gross Reward Risk').
  * corrected gate:      net RR = (TP_pips - cost_pips) / (SL_pips + cost_pips)
    (core/live_execution.py :: target_display_columns 'Net Reward Risk').
"""
from __future__ import annotations

import math

COST_MODEL_VERSION = "cost-model-20261009-v1"

SCENARIOS = {
    "legacy_1pip": {
        "spread_pips": 1.0,
        "slippage_pips": 0.0,
        "commission_pips": 0.0,
        "financing_pips_per_day": 0.0,
        "label": "legacy reproduction — 1 pip spread deducted once (NOT a measured broker cost)",
    },
    "sensitivity_3pip": {
        "spread_pips": 1.0,
        "slippage_pips": 0.0,
        "commission_pips": 0.0,
        "financing_pips_per_day": 0.0,
        "extra_sensitivity_pips": 2.0,
        "label": "sensitivity — NOT a measured broker cost",
    },
}

SENSITIVITY_LABEL = "sensitivity — NOT a measured broker cost"


def _scenario(name: str) -> dict:
    if name not in SCENARIOS:
        raise ValueError(f"unknown cost scenario {name!r}; known: {sorted(SCENARIOS)}")
    return SCENARIOS[name]


def total_cost_pips(scenario: str = "legacy_1pip", *, fill_type: str = "OHLC_MID",
                    hold_days: float = 0.0) -> float:
    """Total cost in pips deducted for one trade.

    fill_type='OHLC_MID'   — declared cost applied once.
    fill_type='BROKER_BID_ASK' — spread already embedded in fills: only
        non-embedded costs (commission, financing) apply; embedded spread is
        never deducted twice.
    """
    cfg = _scenario(scenario)
    if fill_type not in ("OHLC_MID", "BROKER_BID_ASK"):
        raise ValueError(f"fill_type must be OHLC_MID or BROKER_BID_ASK, got {fill_type!r}")
    hold_days = max(0.0, float(hold_days))
    if fill_type == "BROKER_BID_ASK":
        spread = 0.0  # embedded in the fill prices — deducting again is forbidden
    else:
        spread = float(cfg["spread_pips"])
    total = (spread + float(cfg["slippage_pips"]) + float(cfg["commission_pips"])
             + float(cfg.get("extra_sensitivity_pips", 0.0))
             + float(cfg["financing_pips_per_day"]) * hold_days)
    if total < 0:
        raise ValueError("trading costs cannot be negative")
    return total


def net_pips(gross_pips: float, scenario: str = "legacy_1pip", *,
             fill_type: str = "OHLC_MID", hold_days: float = 0.0) -> float:
    """Apply the declared cost exactly once. NaN gross (unknown outcome)
    stays NaN — unknown outcomes are never converted to zero profit."""
    if gross_pips is None or (isinstance(gross_pips, float) and math.isnan(gross_pips)):
        return float("nan")
    return float(gross_pips) - total_cost_pips(scenario, fill_type=fill_type, hold_days=hold_days)


def gross_reward_risk(tp_pips: float, sl_pips: float) -> float:
    """Legacy reproduction formula: TP / SL (no cost adjustment)."""
    if sl_pips <= 0:
        raise ValueError("SL must be positive")
    return float(tp_pips) / float(sl_pips)


def net_reward_risk(tp_pips: float, sl_pips: float, cost_pips: float = 1.0) -> float:
    """Corrected gate formula: (TP - cost) / (SL + cost).

    The active mode-D risk gate uses the equivalent inequality
    (TP - cost) >= 0.5 * SL (see core/exit_registry_20261009.py :: risk_gate).
    """
    if sl_pips + cost_pips <= 0:
        raise ValueError("SL + cost must be positive")
    return (float(tp_pips) - float(cost_pips)) / (float(sl_pips) + float(cost_pips))


def describe() -> dict:
    return {"cost_model_version": COST_MODEL_VERSION,
            "scenarios": {k: v["label"] for k, v in SCENARIOS.items()},
            "deduction_rule": "deducted exactly once; broker bid/ask fills never double-deduct embedded spread",
            "provenance": "config/audited_execution.json :: spread_pips=1.0, slippage=0.0, commission=0.0, financing=0.0"}
