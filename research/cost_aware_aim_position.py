"""Shadow-only cost-aware desired exposure and no-trade-band calculation."""
from __future__ import annotations

from typing import Any
import math


def evaluate(*, expected_return_pips: Any, probability_win: Any = 0.5, expected_loss_pips: Any = 0.0, spread_pips: Any = 0.0, slippage_pips: Any = 0.0, commission_pips: Any = 0.0, current_exposure: Any = 0.0, risk_scale_pips: float = 10.0, adjustment_speed: float = 0.25, no_trade_band_pips: float = 0.5, max_abs_exposure: float = 1.0) -> dict[str, Any]:
    p = min(1.0, max(0.0, float(probability_win)))
    gain = float(expected_return_pips)
    loss = abs(float(expected_loss_pips))
    gross_ev = p * gain - (1.0 - p) * loss
    total_cost = max(0.0, float(spread_pips)) + max(0.0, float(slippage_pips)) + max(0.0, float(commission_pips))
    net_ev = gross_ev - total_cost
    scale = max(float(risk_scale_pips), 1e-9)
    maximum = max(0.0, float(max_abs_exposure))
    raw_target = maximum * math.tanh(net_ev / scale)
    band = max(0.0, float(no_trade_band_pips))
    target = 0.0 if abs(net_ev) <= band else raw_target
    current = max(-maximum, min(maximum, float(current_exposure)))
    speed = max(0.0, min(1.0, float(adjustment_speed)))
    adjusted = current + speed * (target - current)
    adjusted = max(-maximum, min(maximum, adjusted))
    return {
        "status": "COST-DOMINATED" if gross_ev > 0.0 and net_ev <= 0.0 else "NO-TRADE-BAND" if target == 0.0 else "SHADOW TARGET AVAILABLE",
        "gross_ev_pips": gross_ev,
        "transaction_cost_pips": total_cost,
        "net_ev_pips": net_ev,
        "desired_exposure": target,
        "adjusted_exposure": adjusted,
        "adjustment_speed": speed,
        "no_trade_band_pips": band,
        "execute_trade": False,
        "shadow_only": True,
    }


__all__ = ["evaluate"]
