"""Pure EURUSD risk-based position-sizing guardrail.

This service is display-only. It never changes protected BUY/SELL/WAIT logic,
forecast values, priority scores, or Full Metric History calculations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_FLOOR, InvalidOperation
from math import ceil, isfinite
from typing import Any, Mapping

PIP_VALUE_PER_STANDARD_LOT_USD = 10.0
CONTRACT_SIZE = 100_000.0


@dataclass(frozen=True)
class PositionSizingInputs:
    balance: float = 600.0
    leverage: float = 100.0
    current_eurusd_price: float = 1.15
    risk_pct: float = 1.0
    stop_loss_pips: float = 20.0
    existing_eurusd_open_lots: float = 0.0
    existing_combined_open_risk_pct: float = 0.0
    daily_realized_loss: float = 0.0
    broker_minimum_lot: float = 0.01
    broker_lot_step: float = 0.01
    available_margin: float | None = None
    maximum_margin_pct: float = 25.0
    maximum_combined_risk_pct: float = 2.0
    maximum_individual_idea_risk_pct: float = 1.5
    daily_loss_block_pct: float = 3.0
    snapshot_current: bool = True
    calculation_complete: bool = True
    related_scale_in_entries: int = 0


@dataclass(frozen=True)
class PositionSizingResult:
    status: str
    reason: str
    risk_dollars: float
    raw_lots: float
    recommended_lots: float
    scale_in_entries: int
    scale_in_splits: tuple[float, ...]
    planned_dollar_loss: float
    planned_risk_pct: float
    margin_estimate: float
    margin_pct: float
    theoretical_margin_capacity_lots: float
    current_available_margin: float
    existing_open_lots: float
    combined_open_risk_pct: float
    daily_risk_remaining_dollars: float
    daily_risk_remaining_pct: float
    pip_value_for_recommended_lots: float
    minimum_lot_exceeds_allowance: bool
    inputs: PositionSizingInputs

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["scale_in_splits"] = list(self.scale_in_splits)
        return payload


def _finite_positive(value: Any) -> bool:
    try:
        number = float(value)
        return isfinite(number) and number > 0
    except Exception:
        return False


def floor_to_lot_step(value: float, step: float) -> float:
    """Round downward to the broker lot step, never upward."""
    if not _finite_positive(step) or not isfinite(float(value)) or float(value) <= 0:
        return 0.0
    try:
        d_value = Decimal(str(value))
        d_step = Decimal(str(step))
        units = (d_value / d_step).to_integral_value(rounding=ROUND_FLOOR)
        return float(units * d_step)
    except (InvalidOperation, ValueError, TypeError, ZeroDivisionError):
        return 0.0


def _splits(total: float, step: float, maximum_entries: int = 3) -> tuple[float, ...]:
    total = floor_to_lot_step(total, step)
    if total <= 0 or step <= 0:
        return ()
    units = int(Decimal(str(total)) / Decimal(str(step)))
    entries = max(1, min(maximum_entries, units))
    base = units // entries
    remainder = units % entries
    result = [float(Decimal(base + (1 if i >= entries - remainder and remainder else 0)) * Decimal(str(step))) for i in range(entries)]
    return tuple(x for x in result if x > 0)


def calculate_position_size(inputs: PositionSizingInputs) -> PositionSizingResult:
    invalid = []
    if not _finite_positive(inputs.balance): invalid.append("Invalid balance")
    if not _finite_positive(inputs.leverage): invalid.append("Invalid leverage")
    if not _finite_positive(inputs.current_eurusd_price): invalid.append("Invalid EURUSD price")
    if not _finite_positive(inputs.stop_loss_pips): invalid.append("No valid stop")
    if not _finite_positive(inputs.broker_lot_step): invalid.append("Invalid lot step")
    if not _finite_positive(inputs.broker_minimum_lot): invalid.append("Invalid minimum lot")
    if float(inputs.risk_pct) <= 0: invalid.append("Invalid risk percentage")
    if not inputs.snapshot_current: invalid.append("Snapshot stale")
    if not inputs.calculation_complete: invalid.append("Calculation incomplete")

    balance = max(0.0, float(inputs.balance or 0.0))
    risk_pct = max(0.0, float(inputs.risk_pct or 0.0))
    risk_dollars = balance * risk_pct / 100.0
    available_margin = balance if inputs.available_margin is None else max(0.0, float(inputs.available_margin))
    daily_limit_dollars = balance * max(0.0, float(inputs.daily_loss_block_pct)) / 100.0
    daily_remaining = max(0.0, daily_limit_dollars - max(0.0, float(inputs.daily_realized_loss or 0.0)))

    if invalid:
        return PositionSizingResult(
            status="BLOCK", reason="; ".join(invalid), risk_dollars=risk_dollars,
            raw_lots=0.0, recommended_lots=0.0, scale_in_entries=0, scale_in_splits=(),
            planned_dollar_loss=0.0, planned_risk_pct=0.0, margin_estimate=0.0,
            margin_pct=0.0, theoretical_margin_capacity_lots=0.0,
            current_available_margin=available_margin,
            existing_open_lots=max(0.0, float(inputs.existing_eurusd_open_lots or 0.0)),
            combined_open_risk_pct=max(0.0, float(inputs.existing_combined_open_risk_pct or 0.0)),
            daily_risk_remaining_dollars=daily_remaining,
            daily_risk_remaining_pct=(daily_remaining / balance * 100.0) if balance else 0.0,
            pip_value_for_recommended_lots=0.0, minimum_lot_exceeds_allowance=False, inputs=inputs,
        )

    raw_lots = risk_dollars / (float(inputs.stop_loss_pips) * PIP_VALUE_PER_STANDARD_LOT_USD)
    minimum_exceeds = raw_lots + 1e-12 < float(inputs.broker_minimum_lot)
    recommended = 0.0 if minimum_exceeds else floor_to_lot_step(raw_lots, float(inputs.broker_lot_step))
    if 0 < recommended < float(inputs.broker_minimum_lot):
        recommended = 0.0
        minimum_exceeds = True

    planned_loss = recommended * float(inputs.stop_loss_pips) * PIP_VALUE_PER_STANDARD_LOT_USD
    planned_risk_pct = planned_loss / balance * 100.0 if balance else 0.0
    margin = recommended * CONTRACT_SIZE * float(inputs.current_eurusd_price) / float(inputs.leverage)
    margin_pct = margin / balance * 100.0 if balance else 0.0
    theoretical = balance * float(inputs.leverage) / (CONTRACT_SIZE * float(inputs.current_eurusd_price))
    combined = max(0.0, float(inputs.existing_combined_open_risk_pct or 0.0)) + planned_risk_pct
    splits = _splits(recommended, float(inputs.broker_lot_step), maximum_entries=3)

    blockers: list[str] = []
    cautions: list[str] = []
    if minimum_exceeds:
        blockers.append("SKIP — minimum lot exceeds risk allowance")
    if max(0.0, float(inputs.daily_realized_loss or 0.0)) >= daily_limit_dollars > 0:
        blockers.append("Daily loss limit reached")
    if planned_risk_pct > max(2.0, float(inputs.maximum_individual_idea_risk_pct)):
        blockers.append("Trade risk exceeds hard limit")
    elif planned_risk_pct > float(inputs.maximum_individual_idea_risk_pct):
        blockers.append("Trade risk exceeds configured idea limit")
    elif planned_risk_pct > 1.0:
        cautions.append("Trade risk above 1%")
    if combined > float(inputs.maximum_combined_risk_pct):
        blockers.append("Combined related risk exceeds configured limit")
    elif combined > 1.5:
        cautions.append("Combined related risk above 1.5%")
    if margin > available_margin + 1e-9:
        blockers.append("Margin buffer insufficient")
    if margin_pct > float(inputs.maximum_margin_pct):
        blockers.append("Estimated margin exceeds configured maximum")
    elif margin_pct > 15.0:
        cautions.append("Estimated margin above 15% of balance")
    if int(inputs.related_scale_in_entries or 0) >= 3:
        cautions.append("Several related scale-in entries already open")

    status = "BLOCK" if blockers else "CAUTION" if cautions else "SAFE"
    reason = "; ".join(blockers or cautions or ["Risk and margin checks passed"])
    return PositionSizingResult(
        status=status, reason=reason, risk_dollars=risk_dollars, raw_lots=raw_lots,
        recommended_lots=recommended, scale_in_entries=len(splits), scale_in_splits=splits,
        planned_dollar_loss=planned_loss, planned_risk_pct=planned_risk_pct,
        margin_estimate=margin, margin_pct=margin_pct,
        theoretical_margin_capacity_lots=theoretical, current_available_margin=available_margin,
        existing_open_lots=max(0.0, float(inputs.existing_eurusd_open_lots or 0.0)),
        combined_open_risk_pct=combined, daily_risk_remaining_dollars=daily_remaining,
        daily_risk_remaining_pct=(daily_remaining / balance * 100.0) if balance else 0.0,
        pip_value_for_recommended_lots=recommended * PIP_VALUE_PER_STANDARD_LOT_USD,
        minimum_lot_exceeds_allowance=minimum_exceeds, inputs=inputs,
    )


def inputs_from_state(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> PositionSizingInputs:
    market = canonical.get("market") if isinstance(canonical.get("market"), Mapping) else {}
    final = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
    price = canonical.get("last_close") or market.get("current_price") or market.get("last_close") or 0.0
    status = str(canonical.get("calculation_status") or "").upper()
    stale = bool(canonical.get("stale") or (canonical.get("metadata") or {}).get("stale"))
    return PositionSizingInputs(
        balance=float(state.get("risk_balance_20260619", state.get("account_balance", 600.0)) or 600.0),
        leverage=float(state.get("risk_leverage_20260619", state.get("leverage", 100.0)) or 100.0),
        current_eurusd_price=float(price or 0.0),
        risk_pct=float(state.get("risk_pct_20260619", 1.0) or 1.0),
        stop_loss_pips=float(state.get("risk_stop_pips_20260619", final.get("stop_distance_pips", 20.0)) or 20.0),
        existing_eurusd_open_lots=float(state.get("risk_existing_lots_20260619", 0.0) or 0.0),
        existing_combined_open_risk_pct=float(state.get("risk_existing_combined_pct_20260619", 0.0) or 0.0),
        daily_realized_loss=float(state.get("risk_daily_realized_loss_20260619", 0.0) or 0.0),
        broker_minimum_lot=float(state.get("risk_min_lot_20260619", 0.01) or 0.01),
        broker_lot_step=float(state.get("risk_lot_step_20260619", 0.01) or 0.01),
        available_margin=float(state.get("risk_available_margin_20260619", state.get("free_margin", state.get("account_balance", 600.0))) or 0.0),
        maximum_margin_pct=float(state.get("risk_max_margin_pct_20260619", 25.0) or 25.0),
        maximum_combined_risk_pct=float(state.get("risk_max_combined_pct_20260619", 2.0) or 2.0),
        maximum_individual_idea_risk_pct=float(state.get("risk_max_idea_pct_20260619", 1.5) or 1.5),
        daily_loss_block_pct=float(state.get("risk_daily_block_pct_20260619", 3.0) or 3.0),
        snapshot_current=not stale,
        calculation_complete=status.startswith("COMPLETED"),
        related_scale_in_entries=int(state.get("risk_related_entries_20260619", 0) or 0),
    )


def build_risk_plan(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    return calculate_position_size(inputs_from_state(state, canonical)).to_dict()


def reference_table(balance: float, risk_pct: float, stops: tuple[int, ...] = (10, 15, 20, 25, 30, 40, 50), *, lot_step: float = 0.01, minimum_lot: float = 0.01) -> list[dict[str, Any]]:
    rows = []
    for stop in stops:
        result = calculate_position_size(PositionSizingInputs(
            balance=balance, leverage=100, current_eurusd_price=1.15, risk_pct=risk_pct,
            stop_loss_pips=stop, broker_lot_step=lot_step, broker_minimum_lot=minimum_lot,
        ))
        rows.append({"Stop (pips)": stop, "Risk budget ($)": round(result.risk_dollars, 2), "Safe aggregate lots": "SKIP" if result.minimum_lot_exceeds_allowance else f"{result.recommended_lots:.2f}"})
    return rows


__all__ = ["PositionSizingInputs", "PositionSizingResult", "calculate_position_size", "floor_to_lot_step", "inputs_from_state", "build_risk_plan", "reference_table"]
