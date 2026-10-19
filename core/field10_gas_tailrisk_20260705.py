"""Bounded GAS state updates and directional dynamic VaR/Expected Shortfall."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import math

import numpy as np
import pandas as pd

from core.field10_research_common_20260705 import HORIZONS, direction_sign, finite
from core.quant_research_v14_caviar import evaluate as caviar_evaluate

VERSION = "field10-gas-tailrisk-20260705-v1"
ALPHA = 0.05

GAS_REGISTRY: dict[str, dict[str, float]] = {
    "volatility_state": {"omega": 0.001, "A": 0.08, "B": 0.90, "lower": 1e-6, "upper": 0.25},
    "return_location_state": {"omega": 0.0, "A": 0.06, "B": 0.92, "lower": -0.05, "upper": 0.05},
    "tail_thickness_state": {"omega": 0.02, "A": 0.05, "B": 0.92, "lower": 0.0, "upper": 5.0},
    "dependence_state": {"omega": 0.0, "A": 0.05, "B": 0.94, "lower": -0.99, "upper": 0.99},
    "transition_risk_sensitivity": {"omega": 0.01, "A": 0.06, "B": 0.92, "lower": 0.0, "upper": 1.0},
    "reliability_state": {"omega": 0.01, "A": 0.05, "B": 0.94, "lower": 0.0, "upper": 1.0},
}


def _initial_states(returns: pd.Series, transition_risk: float | None, reliability: float | None) -> dict[str, float]:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    vol = float(clean.tail(120).std(ddof=1)) if len(clean) > 2 else 0.01
    location = float(clean.tail(120).mean()) if len(clean) else 0.0
    z = (clean.tail(120) - location) / max(vol, 1e-9)
    tail = float(max(0.0, z.pow(4).mean() - 3.0)) if len(z) >= 20 else 0.0
    return {
        "volatility_state": vol,
        "return_location_state": location,
        "tail_thickness_state": tail,
        "dependence_state": 0.0,
        "transition_risk_sensitivity": float(np.clip((transition_risk or 50.0) / 100.0, 0.0, 1.0)),
        "reliability_state": float(np.clip((reliability or 50.0) / 100.0, 0.0, 1.0)),
    }


def bounded_gas_update(
    returns: pd.Series,
    *,
    previous_state: Mapping[str, Any] | None = None,
    dependence_innovation: float | None = None,
    transition_risk: float | None = None,
    reliability: float | None = None,
) -> dict[str, Any]:
    clean = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(clean) < 30:
        return {"status": "INSUFFICIENT_SAMPLE", "version": VERSION, "states": {}}
    initialized = _initial_states(clean, transition_risk, reliability)
    previous = {name: finite((previous_state or {}).get(name)) for name in GAS_REGISTRY}
    previous = {name: initialized[name] if value is None else float(value) for name, value in previous.items()}
    latest = float(clean.iloc[-1])
    center = float(clean.tail(120).mean())
    scale = max(float(clean.tail(120).std(ddof=1)), 1e-9)
    z = (latest - center) / scale
    scores = {
        "volatility_state": abs(latest) - previous["volatility_state"],
        "return_location_state": z,
        "tail_thickness_state": max(0.0, z * z - 1.0),
        "dependence_state": float(np.clip(dependence_innovation or 0.0, -3.0, 3.0)),
        "transition_risk_sensitivity": float(np.clip((transition_risk or 50.0) / 100.0 - previous["transition_risk_sensitivity"], -1.0, 1.0)),
        "reliability_state": float(np.clip((reliability or 50.0) / 100.0 - previous["reliability_state"], -1.0, 1.0)),
    }
    rows: dict[str, dict[str, Any]] = {}
    for name, params in GAS_REGISTRY.items():
        score = float(scores[name])
        raw = params["omega"] + params["A"] * score + params["B"] * previous[name]
        new = float(np.clip(raw, params["lower"], params["upper"]))
        rows[name] = {
            "state_name": name, "previous_state": previous[name], "scaled_score": score,
            "omega": params["omega"], "score_loading": params["A"], "persistence": params["B"],
            "update_magnitude": new - previous[name], "resulting_state": new,
            "lower_bound": params["lower"], "upper_bound": params["upper"],
            "finite_validation": bool(math.isfinite(new)), "bound_validation": params["lower"] <= new <= params["upper"],
        }
    state_values = {name: row["resulting_state"] for name, row in rows.items()}
    tail_warning = state_values["tail_thickness_state"] >= 1.5
    transition_warning = state_values["transition_risk_sensitivity"] >= 0.70
    uncertainty_multiplier = float(np.clip(1.0 + 0.15 * state_values["tail_thickness_state"] + 0.25 * state_values["transition_risk_sensitivity"], 1.0, 2.5))
    return {
        "status": "AVAILABLE", "version": VERSION, "states": rows, "state_values": state_values,
        "forecast_uncertainty_multiplier": uncertainty_multiplier,
        "tail_risk_warning": tail_warning, "transition_warning": transition_warning,
        "entry_permission": "BLOCK" if tail_warning and transition_warning else "CAUTION" if tail_warning or transition_warning else "UNCHANGED",
        "locked_bias_modified": False,
    }


def _horizon_strategy_returns(frame: pd.DataFrame, horizon: int, sign: int) -> pd.Series:
    close = pd.to_numeric(frame["close"], errors="coerce")
    raw = np.log(close.shift(-horizon) / close)
    return (float(sign) * raw).replace([np.inf, -np.inf], np.nan)


def _fz0_loss(y: float, q: float, es: float, alpha: float = ALPHA) -> float | None:
    # FZ0 strictly-consistent joint VaR/ES loss for negative-return lower tails.
    if not all(math.isfinite(v) for v in (y, q, es)) or es >= -1e-12:
        return None
    indicator = 1.0 if y <= q else 0.0
    value = indicator * (y - q) / (alpha * es) + q / es + math.log(-es) - 1.0
    return value if math.isfinite(value) else None


def _independence_p_value(exceptions: list[int]) -> float | None:
    if len(exceptions) < 30 or sum(exceptions) < 2:
        return None
    n00 = n01 = n10 = n11 = 0
    for a, b in zip(exceptions[:-1], exceptions[1:]):
        if a == 0 and b == 0: n00 += 1
        elif a == 0 and b == 1: n01 += 1
        elif a == 1 and b == 0: n10 += 1
        else: n11 += 1
    def safe_prob(num: int, den: int) -> float:
        return (num + 0.5) / (den + 1.0)
    pi0 = safe_prob(n01, n00 + n01)
    pi1 = safe_prob(n11, n10 + n11)
    pi = safe_prob(n01 + n11, n00 + n01 + n10 + n11)
    ll0 = (n00 + n10) * math.log(max(1 - pi, 1e-12)) + (n01 + n11) * math.log(max(pi, 1e-12))
    ll1 = n00 * math.log(max(1 - pi0, 1e-12)) + n01 * math.log(max(pi0, 1e-12)) + n10 * math.log(max(1 - pi1, 1e-12)) + n11 * math.log(max(pi1, 1e-12))
    lr = max(0.0, -2.0 * (ll0 - ll1))
    return float(math.erfc(math.sqrt(lr / 2.0)))


def directional_var_es(
    frame: pd.DataFrame,
    *,
    bias: str,
    gas_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    sign = direction_sign(bias)
    if sign == 0 or not isinstance(frame, pd.DataFrame) or len(frame) < 180:
        return {"status": "DIRECTION_OR_SAMPLE_UNAVAILABLE", "version": VERSION, "bias": bias, "horizons": {}}
    gas_values = (gas_result or {}).get("state_values") if isinstance(gas_result, Mapping) else {}
    gas_values = gas_values if isinstance(gas_values, Mapping) else {}
    tail_multiplier = float(np.clip(1.0 + 0.05 * float(gas_values.get("tail_thickness_state") or 0.0), 1.0, 1.5))
    output: dict[int, dict[str, Any]] = {}
    for horizon in HORIZONS:
        strategy = _horizon_strategy_returns(frame, horizon, sign)
        settled = strategy.dropna()
        if len(settled) < 120:
            output[horizon] = {"horizon": horizon, "status": "INSUFFICIENT_SETTLED_HISTORICAL_TARGETS", "sample_count": int(len(settled))}
            continue
        history = settled.tail(300)
        q = float(history.quantile(ALPHA)) * tail_multiplier
        tail = history.loc[history <= history.quantile(ALPHA)]
        es = float(tail.mean()) * tail_multiplier if not tail.empty else q
        if es > q:
            es = q
        rolling_q: list[float] = []
        rolling_es: list[float] = []
        outcomes: list[float] = []
        exceptions: list[int] = []
        losses: list[float] = []
        # Origin i may only use horizon-return labels whose due candle is <= i.
        for i in range(120 + horizon, len(strategy) - horizon):
            available = strategy.iloc[: i - horizon + 1].dropna().tail(300)
            y = finite(strategy.iloc[i])
            if y is None or len(available) < 120:
                continue
            q_i = float(available.quantile(ALPHA))
            tail_i = available.loc[available <= q_i]
            es_i = float(tail_i.mean()) if not tail_i.empty else q_i
            rolling_q.append(q_i); rolling_es.append(es_i); outcomes.append(y)
            exceptions.append(int(y <= q_i))
            loss = _fz0_loss(y, q_i, min(es_i, q_i))
            if loss is not None:
                losses.append(loss)
        exception_rate = None if not exceptions else float(np.mean(exceptions))
        independence_p = _independence_p_value(exceptions)
        coverage = None if exception_rate is None else 1.0 - exception_rate
        severity_ratio = None if abs(q) <= 1e-12 else abs(es) / abs(q)
        tail_loss_probability = float((history < 0).mean())
        expected = float(history.mean())
        tail_adjusted = expected - 0.35 * abs(es)
        caviar = caviar_evaluate(history.tolist())
        sufficient = len(exceptions) >= 60 and sum(exceptions) >= 3
        coverage_ok = exception_rate is not None and 0.02 <= exception_rate <= 0.08
        independence_ok = independence_p is not None and independence_p >= 0.05
        status = "RESEARCH_BACKTEST_PASS" if sufficient and coverage_ok and independence_ok else "RESEARCH_BACKTEST_REVIEW" if sufficient else "INSUFFICIENT_CHRONOLOGICAL_EXCEPTIONS"
        output[horizon] = {
            "horizon": horizon, "status": status, "direction": str(bias).upper(),
            "directional_var_95": q, "directional_expected_shortfall_95": es,
            "es_var_severity_ratio": severity_ratio, "tail_loss_probability": tail_loss_probability,
            "tail_adjusted_expected_value": tail_adjusted, "tail_model_coverage": coverage,
            "tail_exception_count": int(sum(exceptions)), "tail_exception_total": int(len(exceptions)),
            "tail_exception_independence": independence_p,
            "tail_backtest_status": status, "joint_var_es_loss": None if not losses else float(np.mean(losses)),
            "sample_count": int(len(history)), "purge_hours": horizon, "embargo_hours": horizon,
            "caviar_reuse_status": caviar.get("status"), "caviar_pinball_loss": caviar.get("pinball_loss"),
            "training_rows_strictly_before_origin": True,
        }
    return {"status": "AVAILABLE", "version": VERSION, "bias": str(bias).upper(), "horizons": output}


__all__ = ["VERSION", "GAS_REGISTRY", "bounded_gas_update", "directional_var_es"]
