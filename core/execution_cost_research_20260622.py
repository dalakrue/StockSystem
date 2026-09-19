"""Advisory-only Almgren-Chriss-style execution cost analysis for Quant V3."""
from __future__ import annotations

from typing import Any, Mapping
import math
import time

import numpy as np

from core.quant_research_v3_contract_20260622 import ResearchIdentity, finite_or_none, method_contract, unavailable_contract

VERSION = "execution-cost-research-20260622-v1"


def _first_number(*values: Any) -> float | None:
    for value in values:
        number = finite_or_none(value)
        if number is not None:
            return number
    return None


def _extract_inputs(canonical: Mapping[str, Any], volatility_stack: Mapping[str, Any]) -> dict[str, Any]:
    risk = canonical.get("risk_plan") if isinstance(canonical.get("risk_plan"), Mapping) else {}
    final = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
    market = canonical.get("market") if isinstance(canonical.get("market"), Mapping) else {}
    execution = canonical.get("execution_inputs") if isinstance(canonical.get("execution_inputs"), Mapping) else {}
    yz = (volatility_stack.get("yang_zhang") or {}) if isinstance(volatility_stack, Mapping) else {}
    har = (volatility_stack.get("har_style") or {}) if isinstance(volatility_stack, Mapping) else {}
    jump = (volatility_stack.get("jump_proxy") or {}) if isinstance(volatility_stack, Mapping) else {}
    har_h = ((har.get("horizons") or {}).get(str(int(final.get("selected_horizon") or 1))) or {})
    return {
        "lot_size": _first_number(execution.get("lot_size"), risk.get("recommended_lots"), risk.get("lot_size"), canonical.get("lot_size")),
        "spread_pips": _first_number(execution.get("spread_pips"), market.get("spread_pips"), canonical.get("spread_pips")),
        "slippage_pips": _first_number(execution.get("historical_slippage_pips"), market.get("historical_slippage_pips"), canonical.get("historical_slippage_pips")),
        "pip_value_per_lot": _first_number(execution.get("pip_value_per_lot"), risk.get("pip_value_per_lot"), canonical.get("pip_value_per_lot")),
        "yz_volatility": _first_number(yz.get("yang_zhang_volatility")),
        "har_volatility": _first_number(har_h.get("forecast_volatility")),
        "execution_horizon_hours": int(execution.get("execution_horizon_hours") or final.get("selected_horizon") or 1),
        "expected_move_price": _first_number(((yz.get("expected_move") or {}).get(str(int(final.get("selected_horizon") or 1))))),
        "jump_status": jump.get("latest_move_is_jump"),
        "session_liquidity_proxy": _first_number(execution.get("session_liquidity_proxy"), market.get("session_liquidity_proxy"), 1.0),
        "tick_volume": _first_number(execution.get("tick_volume"), market.get("tick_volume")),
        "risk_aversion": _first_number(execution.get("risk_aversion"), risk.get("risk_aversion"), 1.0),
        "current_price": _first_number(canonical.get("last_close"), market.get("current_price")),
        "expected_edge_pips": _first_number(execution.get("expected_edge_pips"), final.get("expected_edge_pips")),
    }


def execution_cost_advisory(
    identity: ResearchIdentity,
    canonical: Mapping[str, Any],
    volatility_stack: Mapping[str, Any],
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        inputs = _extract_inputs(canonical, volatility_stack)
        required = ("lot_size", "spread_pips", "slippage_pips", "pip_value_per_lot")
        missing = [name for name in required if inputs.get(name) is None]
        if missing:
            return method_contract(
                identity,
                method_name="ALMGREN_CHRISS_EXECUTION_ADVISORY",
                method_version=VERSION,
                sample_count=0,
                minimum_sample_required=1,
                fallback_level="UNVERIFIED_COST_INPUTS",
                reliability_status="UNVERIFIED_COST_MODEL",
                assumption_status="UNSUPPORTED_COST_INPUTS",
                limitations=(
                    "Verified lot size, spread, historical slippage and pip value are required for a numerical cost estimate.",
                    "No broker order endpoint is connected and no order can be submitted, edited or closed.",
                ),
                status="UNVERIFIED_COST_MODEL",
                missing_verified_inputs=missing,
                verified_inputs=False,
                advisory_only=True,
                order_api_called=False,
                order_submission_allowed=False,
                inputs=inputs,
                runtime_ms=round((time.perf_counter() - started) * 1000.0, 3),
            )
        lot = max(0.0, float(inputs["lot_size"]))
        pip_value = max(0.0, float(inputs["pip_value_per_lot"]))
        spread = max(0.0, float(inputs["spread_pips"]))
        slippage = max(0.0, float(inputs["slippage_pips"]))
        liquidity = max(float(inputs.get("session_liquidity_proxy") or 1.0), 0.1)
        risk_aversion = max(float(inputs.get("risk_aversion") or 1.0), 0.0)
        volatility = max(float(inputs.get("har_volatility") or inputs.get("yz_volatility") or 0.0), 0.0)
        price = max(float(inputs.get("current_price") or 1.0), 1e-12)
        expected_move_pips = float(inputs.get("expected_move_price") or 0.0) / 0.0001
        expected_edge_pips = inputs.get("expected_edge_pips")
        if expected_edge_pips is None:
            expected_edge_pips = expected_move_pips * 0.25
        expected_edge_value = float(expected_edge_pips) * pip_value * lot

        schedules: list[dict[str, Any]] = []
        for slices in range(1, 7):
            schedule_types = ("IMMEDIATE",) if slices == 1 else ("EQUAL_SLICE", "FRONT_LOADED")
            for schedule in schedule_types:
                if schedule == "IMMEDIATE":
                    weights = np.array([1.0])
                elif schedule == "EQUAL_SLICE":
                    weights = np.repeat(1.0 / slices, slices)
                else:
                    raw = np.arange(slices, 0, -1, dtype=float)
                    weights = raw / raw.sum()
                concentration = float(np.sum(weights ** 2))
                spread_cost = spread * pip_value * lot
                slippage_cost = slippage * pip_value * lot * (0.85 + 0.15 * slices) / math.sqrt(liquidity)
                impact_pips = (0.02 * lot / liquidity) * concentration * (1.5 if bool(inputs.get("jump_status")) else 1.0)
                impact_cost = impact_pips * pip_value * lot
                execution_risk_pips = volatility * price / 0.0001 * math.sqrt(max(inputs["execution_horizon_hours"], 1)) * math.sqrt(concentration)
                variance_cost = (execution_risk_pips * pip_value * lot) ** 2
                expected_cost = spread_cost + slippage_cost + impact_cost
                objective = expected_cost + risk_aversion * variance_cost
                schedules.append({
                    "schedule": schedule,
                    "slice_count": slices,
                    "weights": [float(x) for x in weights],
                    "expected_spread_cost": spread_cost,
                    "expected_slippage_cost": slippage_cost,
                    "temporary_impact_proxy": impact_cost,
                    "volatility_execution_risk": execution_risk_pips * pip_value * lot,
                    "total_expected_execution_cost": expected_cost,
                    "variance_of_execution_cost": variance_cost,
                    "expected_edge_after_costs": expected_edge_value - expected_cost,
                    "bounded_objective": objective,
                })
        best = min(schedules, key=lambda item: (item["bounded_objective"], item["slice_count"], item["schedule"]))
        immediate = next(item for item in schedules if item["schedule"] == "IMMEDIATE")
        equal_best = min((x for x in schedules if x["schedule"] == "EQUAL_SLICE"), key=lambda x: x["bounded_objective"], default=None)
        front_best = min((x for x in schedules if x["schedule"] == "FRONT_LOADED"), key=lambda x: x["bounded_objective"], default=None)
        return method_contract(
            identity,
            method_name="ALMGREN_CHRISS_EXECUTION_ADVISORY",
            method_version=VERSION,
            sample_count=1,
            minimum_sample_required=1,
            fallback_level="DETERMINISTIC_BOUNDED_GRID",
            reliability_status="VERIFIED_INPUT_MODEL",
            assumption_status="ADVISORY_PROXY_NOT_EXACT_MARKET_IMPACT_CALIBRATION",
            limitations=(
                "The bounded schedule grid is an advisory adaptation; temporary impact is a proxy unless calibrated transaction data exist.",
                "Tick volume is not treated as verified executable market depth.",
                "No broker order endpoint is connected and no order can be submitted, edited or closed.",
            ),
            status="AVAILABLE",
            verified_inputs=True,
            advisory_only=True,
            order_api_called=False,
            order_submission_allowed=False,
            inputs=inputs,
            expected_spread_cost=best["expected_spread_cost"],
            expected_slippage_cost=best["expected_slippage_cost"],
            temporary_impact_proxy=best["temporary_impact_proxy"],
            volatility_execution_risk=best["volatility_execution_risk"],
            total_expected_execution_cost=best["total_expected_execution_cost"],
            variance_of_execution_cost=best["variance_of_execution_cost"],
            expected_edge_after_costs=best["expected_edge_after_costs"],
            immediate_execution_result=immediate,
            equal_slice_result=equal_best,
            front_loaded_result=front_best,
            recommended_number_of_slices=best["slice_count"],
            recommended_schedule=best["schedule"],
            execution_warning="Expected edge is nonpositive after estimated costs." if best["expected_edge_after_costs"] <= 0 else "Cost model is advisory and input-dependent.",
            bounded_objective="expected_cost + lambda * execution_cost_variance",
            schedules=schedules,
            runtime_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )
    except Exception as exc:
        result = unavailable_contract(identity, "ALMGREN_CHRISS_EXECUTION_ADVISORY", VERSION, exc, minimum_sample_required=1)
        result.update({"advisory_only": True, "order_api_called": False, "order_submission_allowed": False})
        return result


__all__ = ["VERSION", "execution_cost_advisory"]
