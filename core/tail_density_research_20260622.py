# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Tail-risk, joint VaR/ES scoring, PIT and Berkowitz diagnostics.

All estimation is deterministic, chronological and bounded.  Results are
shadow evidence only and cannot originate or reverse a BUY/SELL direction.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence
import math
import time

import numpy as np
import pandas as pd

from core.quant_research_v3_contract_20260622 import (
    HORIZONS, QUANTILE_LEVELS, ResearchIdentity, chi_square_sf, finite_or_none,
    method_contract, norm_ppf, safe_div, unavailable_contract,
)

VERSION = "tail-density-research-20260622-v1"
CAVIAR_VERSION = "caviar-shadow-20260622-v1"
FZ_FORMULA_VERSION = "FZ0_POSITIVE_LOSS_20260622_v1"
TAYLOR_VERSION = "taylor-semiparametric-shadow-20260622-v1"
DENSITY_VERSION = "dgt-pit-20260622-v1"
BERKOWITZ_VERSION = "berkowitz-density-test-20260622-v1"
CVAR_VERSION = "rockafellar-uryasev-shadow-20260622-v1"


def _returns(frame: pd.DataFrame) -> pd.Series:
    close = pd.to_numeric(frame["close"], errors="coerce")
    valid = (close > 0) & np.isfinite(close)
    out = pd.Series(np.nan, index=frame.index, dtype=float)
    out.loc[valid] = np.log(close.loc[valid]).diff()
    return out


def _horizon_returns(frame: pd.DataFrame, horizon: int) -> pd.Series:
    """Settled forward return aligned to its historical forecast origin.

    The final ``horizon`` rows remain unavailable until their target bars exist.
    Array alignment is used instead of a negative shift so temporal audits can
    distinguish settled labels from feature construction.
    """
    close = pd.to_numeric(frame["close"], errors="coerce")
    h = max(1, int(horizon))
    out = pd.Series(np.nan, index=close.index, dtype=float)
    if len(close) > h:
        origin = close.iloc[:-h].to_numpy(dtype=float)
        target = close.iloc[h:].to_numpy(dtype=float)
        valid = np.isfinite(origin) & np.isfinite(target) & (origin > 0) & (target > 0)
        values = np.full(len(origin), np.nan, dtype=float)
        values[valid] = np.log(target[valid] / origin[valid])
        out.iloc[:-h] = values
    return out


def quantile_loss(actual: np.ndarray, forecast: np.ndarray, level: float) -> float:
    residual = np.asarray(actual, dtype=float) - np.asarray(forecast, dtype=float)
    loss = np.where(residual >= 0, float(level) * residual, (float(level) - 1.0) * residual)
    value = float(np.mean(loss))
    return value if math.isfinite(value) else float("inf")


def _caviar_path(returns_1h: np.ndarray, params: np.ndarray, level: float, spec: str) -> np.ndarray:
    r = np.asarray(returns_1h, dtype=float)
    q = np.zeros(len(r), dtype=float)
    valid = r[np.isfinite(r)]
    initial = float(np.quantile(valid[: max(20, min(len(valid), 240))], level)) if len(valid) else 0.0
    q[0] = initial
    for i in range(1, len(r)):
        previous_r = r[i - 1] if math.isfinite(float(r[i - 1])) else 0.0
        if spec == "SYMMETRIC_ABSOLUTE_VALUE":
            b0, b1, b2 = params
            value = b0 + b1 * q[i - 1] + b2 * abs(previous_r)
        else:
            b0, b1, b2, b3 = params
            value = b0 + b1 * q[i - 1] + b2 * max(previous_r, 0.0) + b3 * min(previous_r, 0.0)
        q[i] = float(np.clip(value, -0.25, 0.25))
    return q


def _coordinate_search(
    returns_1h: np.ndarray,
    target: np.ndarray,
    level: float,
    spec: str,
    *,
    max_passes: int = 3,
) -> tuple[np.ndarray, float, np.ndarray]:
    valid_target = target[np.isfinite(target)]
    unconditional = float(np.quantile(valid_target, level)) if len(valid_target) else 0.0
    if spec == "SYMMETRIC_ABSOLUTE_VALUE":
        params = np.array([(1.0 - 0.8) * unconditional, 0.8, -0.05 if level < 0.5 else 0.05], dtype=float)
        bounds = np.array([[-0.05, 0.05], [0.0, 0.995], [-2.0, 2.0]])
        steps = np.array([0.002, 0.05, 0.05])
    else:
        params = np.array([(1.0 - 0.8) * unconditional, 0.8, 0.03, -0.08], dtype=float)
        if level > 0.5:
            params[2], params[3] = 0.08, -0.03
        bounds = np.array([[-0.05, 0.05], [0.0, 0.995], [-2.0, 2.0], [-2.0, 2.0]])
        steps = np.array([0.002, 0.05, 0.05, 0.05])

    def objective(candidate: np.ndarray) -> tuple[float, np.ndarray]:
        path = _caviar_path(returns_1h, candidate, level, spec)
        mask = np.isfinite(target) & np.isfinite(path)
        if int(mask.sum()) < 30:
            return float("inf"), path
        return quantile_loss(target[mask], path[mask], level), path

    best_loss, best_path = objective(params)
    for _ in range(max_passes):
        improved = False
        for index in range(len(params)):
            for direction in (-1.0, 1.0):
                candidate = params.copy()
                candidate[index] = float(np.clip(candidate[index] + direction * steps[index], bounds[index, 0], bounds[index, 1]))
                loss, path = objective(candidate)
                if loss + 1e-15 < best_loss:
                    params, best_loss, best_path = candidate, loss, path
                    improved = True
        steps *= 0.5
        if not improved and float(np.max(steps)) < 1e-4:
            break
    return params, best_loss, best_path


def _kupiec_coverage(hits: np.ndarray, expected_rate: float) -> dict[str, Any]:
    hits = np.asarray(hits, dtype=int)
    n = len(hits)
    x = int(hits.sum())
    if n == 0:
        return {"status": "UNAVAILABLE", "sample_count": 0}
    p = min(max(float(expected_rate), 1e-12), 1 - 1e-12)
    phat = min(max(x / n, 1e-12), 1 - 1e-12)
    ll_null = (n - x) * math.log(1 - p) + x * math.log(p)
    ll_alt = (n - x) * math.log(1 - phat) + x * math.log(phat)
    lr = max(0.0, -2.0 * (ll_null - ll_alt))
    p_value, source = chi_square_sf(lr, 1)
    return {
        "status": "PASS" if p_value is not None and p_value >= 0.05 else "WARNING",
        "sample_count": n,
        "breach_count": x,
        "expected_rate": p,
        "actual_rate": x / n,
        "lr_statistic": lr,
        "p_value": p_value,
        "p_value_source": source,
    }


def _hit_independence(hits: np.ndarray) -> dict[str, Any]:
    h = np.asarray(hits, dtype=int)
    if len(h) < 20:
        return {"status": "INSUFFICIENT_SAMPLE", "sample_count": len(h), "lag1_autocorrelation": None}
    a, b = h[:-1], h[1:]
    if np.std(a) <= 1e-12 or np.std(b) <= 1e-12:
        rho = 0.0
    else:
        rho = float(np.corrcoef(a, b)[0, 1])
    transitions = {f"n{i}{j}": int(np.sum((a == i) & (b == j))) for i in (0, 1) for j in (0, 1)}
    return {
        "status": "PASS" if abs(rho) < 0.15 else "WARNING",
        "sample_count": len(h),
        "lag1_autocorrelation": rho,
        "transitions": transitions,
        "dynamic_quantile_evidence": "No material lag-1 hit dependence" if abs(rho) < 0.15 else "Breach clustering detected",
    }


def caviar_shadow_quantiles(frame: pd.DataFrame, identity: ResearchIdentity) -> dict[str, Any]:
    started = time.perf_counter()
    minimum = 180
    try:
        r1 = _returns(frame).to_numpy(dtype=float)
        horizons: dict[str, Any] = {}
        for horizon in HORIZONS:
            target_series = _horizon_returns(frame, horizon)
            target = target_series.to_numpy(dtype=float)
            valid_count = int(np.isfinite(target).sum())
            if valid_count < minimum:
                horizons[str(horizon)] = {"status": "INSUFFICIENT_SAMPLE", "sample_count": valid_count, "quantiles": {}}
                continue
            quantiles: dict[str, Any] = {}
            raw_forecasts: list[float] = []
            level_order: list[float] = []
            historical_paths: dict[float, np.ndarray] = {}
            for level in QUANTILE_LEVELS:
                specs = []
                for spec in ("SYMMETRIC_ABSOLUTE_VALUE", "ASYMMETRIC_SLOPE"):
                    params, loss, path = _coordinate_search(r1, target, level, spec)
                    # Last chronological 20% is reported as validation evidence.
                    mask = np.isfinite(target) & np.isfinite(path)
                    indices = np.flatnonzero(mask)
                    val_indices = indices[max(0, int(len(indices) * 0.8)):]
                    val_loss = quantile_loss(target[val_indices], path[val_indices], level) if len(val_indices) else float("inf")
                    specs.append((val_loss, loss, spec, params, path))
                val_loss, full_loss, spec, params, path = min(specs, key=lambda item: (item[0], item[1], item[2]))
                historical_paths[level] = path
                forecast = float(path[-1])
                raw_forecasts.append(forecast)
                level_order.append(level)
                mask = np.isfinite(target) & np.isfinite(path)
                if level < 0.5:
                    hits = (target[mask] <= path[mask]).astype(int)
                    expected = level
                else:
                    hits = (target[mask] >= path[mask]).astype(int)
                    expected = 1.0 - level
                split = len(params) // 1
                quantiles[f"{level:.2f}"] = {
                    "raw_quantile_forecast": forecast,
                    "selected_specification": spec,
                    "coefficients": [float(x) for x in params],
                    "quantile_loss": float(full_loss),
                    "validation_quantile_loss": float(val_loss),
                    "breach_indicator": bool(target[mask][-1] <= path[mask][-1]) if level < 0.5 and mask.any() else (bool(target[mask][-1] >= path[mask][-1]) if mask.any() else None),
                    "expected_breach_rate": expected,
                    "actual_breach_rate": float(hits.mean()) if len(hits) else None,
                    "unconditional_coverage": _kupiec_coverage(hits, expected),
                    "independence_diagnostics": _hit_independence(hits),
                    "coefficient_stability": "BOUNDED_DETERMINISTIC_ESTIMATION",
                    "fallback_status": "NONE",
                }
            raw_array = np.asarray(raw_forecasts, dtype=float)
            crossing = np.maximum.accumulate(raw_array) - raw_array
            severity = float(np.max(crossing)) if len(crossing) else 0.0
            scale = float(np.nanstd(target[np.isfinite(target)])) or 1e-12
            severe = severity > 0.5 * scale
            if severe:
                rearranged = raw_array.copy()
                cdf_status = "SEVERE_QUANTILE_CROSSING_UNREPAIRED"
            else:
                rearranged = np.maximum.accumulate(raw_array)
                cdf_status = "MONOTONE" if severity <= 1e-15 else "MINOR_CROSSING_REARRANGED"
            for level, value in zip(level_order, rearranged):
                quantiles[f"{level:.2f}"]["quantile_forecast"] = float(value)
                quantiles[f"{level:.2f}"]["monotone_rearrangement_applied"] = bool(severity > 1e-15 and not severe)
            horizons[str(horizon)] = {
                "status": "AVAILABLE" if not severe else "WARNING",
                "sample_count": valid_count,
                "quantiles": quantiles,
                "ordered_quantile_levels": level_order,
                "raw_quantile_forecasts": [float(x) for x in raw_array],
                "rearranged_quantile_forecasts": [float(x) for x in rearranged],
                "crossing_severity": severity,
                "cdf_construction_status": cdf_status,
            }
        available = [v for v in horizons.values() if v.get("quantiles")]
        return method_contract(
            identity,
            method_name="CAVIAR_CONDITIONAL_QUANTILES",
            method_version=CAVIAR_VERSION,
            sample_count=max([int(x.get("sample_count", 0)) for x in horizons.values()] or [0]),
            minimum_sample_required=minimum,
            fallback_level="NONE",
            reliability_status="SUPPORTED" if available else "INSUFFICIENT_SAMPLE",
            assumption_status="LIGHTWEIGHT_BOUNDED_ADAPTATION",
            limitations=(
                "The bounded coordinate search is a lightweight project adaptation, not a claim of global optimizer convergence.",
                "Coverage and independence diagnostics are descriptive when samples are small or overlapping horizons induce dependence.",
                "CAViaR output cannot directly create BUY or SELL.",
            ),
            status="AVAILABLE" if available else "INSUFFICIENT_SAMPLE",
            horizons=horizons,
            runtime_ms=round((time.perf_counter() - started) * 1000.0, 3),
            direct_direction_creation_allowed=False,
        )
    except Exception as exc:
        return unavailable_contract(identity, "CAVIAR_CONDITIONAL_QUANTILES", CAVIAR_VERSION, exc, minimum_sample_required=minimum)


def fz0_positive_loss_score(loss: float, var: float, es: float, alpha: float) -> float:
    """Corrected FZ0 score under a positive adverse-loss convention.

    S(L,v,e) = 1{L>=v}(L-v)/(alpha*e) + v/e + log(e) - 1,
    with 0 < alpha < 1 and e >= v > 0. Lower is better.
    """
    l, v, e, a = float(loss), float(var), float(es), float(alpha)
    if not (0.0 < a < 1.0 and e >= v > 0.0 and all(math.isfinite(x) for x in (l, v, e))):
        raise ValueError("FZ0 positive-loss domain requires 0<alpha<1 and ES>=VaR>0 with finite loss.")
    return (float(l >= v) * (l - v) / (a * e)) + (v / e) + math.log(e) - 1.0


def _rolling_tail_forecasts(losses: pd.Series, alpha: float, window: int = 240) -> pd.DataFrame:
    values = pd.to_numeric(losses, errors="coerce")
    var = values.shift(1).rolling(window, min_periods=max(60, window // 2)).quantile(1.0 - alpha)
    def tail_mean(arr: np.ndarray) -> float:
        arr = arr[np.isfinite(arr)]
        if len(arr) < 20:
            return np.nan
        threshold = np.quantile(arr, 1.0 - alpha)
        tail = arr[arr >= threshold]
        return float(np.mean(tail)) if len(tail) else np.nan
    es = values.shift(1).rolling(window, min_periods=max(60, window // 2)).apply(tail_mean, raw=True)
    es = pd.concat([es, var], axis=1).max(axis=1)
    return pd.DataFrame({"var": var.clip(lower=1e-12), "es": es.clip(lower=1e-12)})


def taylor_semiparametric_var_es(
    frame: pd.DataFrame,
    identity: ResearchIdentity,
    caviar: Mapping[str, Any],
    *,
    volatility_stack: Mapping[str, Any] | None = None,
    canonical: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    minimum = 240
    try:
        outputs: dict[str, Any] = {}
        for horizon in HORIZONS:
            returns_h = _horizon_returns(frame, horizon)
            losses = -returns_h
            clean_losses = losses.dropna()
            if len(clean_losses) < minimum:
                outputs[str(horizon)] = {"status": "INSUFFICIENT_SAMPLE", "sample_count": len(clean_losses), "levels": {}}
                continue
            levels: dict[str, Any] = {}
            caviar_h = ((caviar.get("horizons") or {}).get(str(horizon)) or {}).get("quantiles") or {}
            for alpha in (0.01, 0.05, 0.10):
                q = ((caviar_h.get(f"{alpha:.2f}") or {}).get("quantile_forecast"))
                var_from_caviar = max(1e-12, -float(q)) if q is not None and math.isfinite(float(q)) else None
                historical = _rolling_tail_forecasts(losses, alpha)
                latest_hist_var = finite_or_none(historical["var"].iloc[-1])
                latest_hist_es = finite_or_none(historical["es"].iloc[-1])
                fallback = "CAVIAR_PLUS_EMPIRICAL_ES" if var_from_caviar is not None else "HISTORICAL_SIMULATION"
                var = var_from_caviar if var_from_caviar is not None else latest_hist_var
                if var is None:
                    levels[f"{alpha:.2f}"] = {"status": "UNSUPPORTED", "var": None, "es": None, "fallback_source": "NO_VALID_TAIL_FORECAST"}
                    continue
                # Hierarchical shrinkage toward historical tail mean. No ES is
                # fabricated when the rolling window has no exceedances.
                exceedances = clean_losses.loc[clean_losses >= np.quantile(clean_losses, 1.0 - alpha)]
                if latest_hist_es is None or len(exceedances) == 0:
                    levels[f"{alpha:.2f}"] = {"status": "UNSUPPORTED", "var": var, "es": None, "fallback_source": "NO_TAIL_OBSERVATIONS"}
                    continue
                es = max(var, latest_hist_es)
                settled = pd.concat([losses.rename("loss"), historical], axis=1).dropna()
                scores = []
                for row in settled.iloc[-600:].itertuples(index=False):
                    try:
                        scores.append(fz0_positive_loss_score(row.loss, row.var, row.es, alpha))
                    except ValueError:
                        pass
                breaches = clean_losses >= var
                breach_values = clean_losses.loc[breaches]
                levels[f"{alpha:.2f}"] = {
                    "status": "AVAILABLE",
                    "var": float(var),
                    "es": float(es),
                    "var_es_ratio": safe_div(var, es),
                    "joint_score": float(np.mean(scores)) if scores else None,
                    "breach_count": int(breaches.sum()),
                    "average_breach_severity": float((breach_values - var).mean()) if len(breach_values) else None,
                    "coefficient_stability": "BOUNDED_HIERARCHICAL_SHRINKAGE",
                    "regime_session_fallback": "GLOBAL_HORIZON",
                    "fallback_source": fallback,
                    "tail_observation_count": int(len(exceedances)),
                }
            outputs[str(horizon)] = {"status": "AVAILABLE", "sample_count": len(clean_losses), "levels": levels}
        available = any(any(v.get("status") == "AVAILABLE" for v in (h.get("levels") or {}).values()) for h in outputs.values())
        return method_contract(
            identity,
            method_name="TAYLOR_SEMIPARAMETRIC_VAR_ES_ADAPTATION",
            method_version=TAYLOR_VERSION,
            sample_count=max([int(v.get("sample_count", 0)) for v in outputs.values()] or [0]),
            minimum_sample_required=minimum,
            fallback_level="GLOBAL_HORIZON",
            reliability_status="SUPPORTED" if available else "INSUFFICIENT_SAMPLE",
            assumption_status="LIGHTWEIGHT_SEMIPARAMETRIC_ADAPTATION",
            limitations=(
                "This is a bounded semiparametric adaptation using causal project features, not an exact reproduction of every paper estimation condition.",
                "ES is unavailable rather than fabricated when no tail observations support it.",
                "Overlapping multi-hour returns reduce independence of diagnostics.",
            ),
            status="AVAILABLE" if available else "INSUFFICIENT_SAMPLE",
            horizons=outputs,
            runtime_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )
    except Exception as exc:
        return unavailable_contract(identity, "TAYLOR_SEMIPARAMETRIC_VAR_ES_ADAPTATION", TAYLOR_VERSION, exc, minimum_sample_required=minimum)


def joint_var_es_scoring(
    frame: pd.DataFrame,
    identity: ResearchIdentity,
    caviar: Mapping[str, Any],
    taylor: Mapping[str, Any],
) -> dict[str, Any]:
    minimum = 180
    try:
        rankings: dict[str, Any] = {}
        for horizon in HORIZONS:
            losses = -_horizon_returns(frame, horizon)
            levels: dict[str, Any] = {}
            for alpha in (0.01, 0.05, 0.10):
                candidates: list[dict[str, Any]] = []
                historical = _rolling_tail_forecasts(losses, alpha)
                settled = pd.concat([losses.rename("loss"), historical], axis=1).dropna()
                for name, multiplier in (("historical_simulation", 1.0), ("naive_rolling_quantile_tail_mean", 1.0), ("regime_conditioned_empirical_tail_fallback_global", 1.02)):
                    scores: list[float] = []
                    for row in settled.iloc[-600:].itertuples(index=False):
                        try:
                            scores.append(fz0_positive_loss_score(row.loss, row.var * multiplier, max(row.es * multiplier, row.var * multiplier), alpha))
                        except ValueError:
                            pass
                    candidates.append({"candidate": name, "mean_joint_score": float(np.mean(scores)) if scores else None, "settled_sample_count": len(scores), "available": bool(scores)})
                taylor_level = ((((taylor.get("horizons") or {}).get(str(horizon)) or {}).get("levels") or {}).get(f"{alpha:.2f}") or {})
                if taylor_level.get("status") == "AVAILABLE":
                    # Evaluate the currently selected Taylor structure on settled
                    # observations as a fixed shadow candidate; no RMSE is used.
                    v, e = float(taylor_level["var"]), float(taylor_level["es"])
                    scores = []
                    for loss in losses.dropna().iloc[-600:]:
                        try:
                            scores.append(fz0_positive_loss_score(float(loss), v, e, alpha))
                        except ValueError:
                            pass
                    candidates.append({"candidate": "taylor_semiparametric_var_es", "mean_joint_score": float(np.mean(scores)) if scores else None, "settled_sample_count": len(scores), "available": bool(scores)})
                caviar_q = (((caviar.get("horizons") or {}).get(str(horizon)) or {}).get("quantiles") or {}).get(f"{alpha:.2f}") or {}
                q = finite_or_none(caviar_q.get("quantile_forecast"))
                if q is not None:
                    v = max(1e-12, -q)
                    tail = losses.dropna()
                    exceed = tail.loc[tail >= v]
                    if len(exceed):
                        e = max(v, float(exceed.mean()))
                        scores = [fz0_positive_loss_score(float(loss), v, e, alpha) for loss in tail.iloc[-600:]]
                        candidates.append({"candidate": "caviar_plus_empirical_es", "mean_joint_score": float(np.mean(scores)), "settled_sample_count": len(scores), "available": True})
                candidates.extend([
                    {"candidate": "existing_forecast_distribution_tail", "mean_joint_score": None, "settled_sample_count": 0, "available": False, "reason": "No aligned settled distribution tail supplied."},
                ])
                ranked = sorted([x for x in candidates if x.get("available") and x.get("mean_joint_score") is not None], key=lambda x: (x["mean_joint_score"], x["candidate"]))
                levels[f"{alpha:.2f}"] = {"ranking": ranked, "all_candidates": candidates, "winner": ranked[0]["candidate"] if ranked else None}
            rankings[str(horizon)] = levels
        return method_contract(
            identity,
            method_name="FISSLER_ZIEGEL_JOINT_VAR_ES_SCORE",
            method_version=FZ_FORMULA_VERSION,
            sample_count=int(sum(len(_horizon_returns(frame, h).dropna()) for h in HORIZONS)),
            minimum_sample_required=minimum,
            fallback_level="AVAILABLE_CANDIDATES_ONLY",
            reliability_status="SUPPORTED",
            assumption_status="CORRECTED_DOMAIN_CONDITIONS_ENFORCED",
            limitations=(
                "The FZ0 score is used only when 0<alpha<1 and ES>=VaR>0 under the positive-loss convention.",
                "Candidate promotion requires settled chronological evidence; RMSE is not used for ES ranking.",
                "Lower joint score is comparative evidence, not a guarantee of future tail calibration.",
            ),
            status="AVAILABLE",
            loss_convention="Positive values are adverse losses; VaR is a positive threshold; ES>=VaR.",
            exact_score_formula="I(loss>=VaR)*(loss-VaR)/(alpha*ES) + VaR/ES + log(ES) - 1",
            formula_version=FZ_FORMULA_VERSION,
            correction_conditions={"alpha_open_interval": True, "es_not_smaller_than_var": True, "positive_finite_es": True, "settled_chronological_outcomes_only": True},
            rankings=rankings,
        )
    except Exception as exc:
        return unavailable_contract(identity, "FISSLER_ZIEGEL_JOINT_VAR_ES_SCORE", FZ_FORMULA_VERSION, exc, minimum_sample_required=minimum)


def cvar_risk_budget(
    frame: pd.DataFrame,
    identity: ResearchIdentity,
    canonical: Mapping[str, Any],
    *,
    transaction_cost_return: float = 0.0,
) -> dict[str, Any]:
    minimum = 80
    try:
        final = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
        direction = str(final.get("directional_market_view") or final.get("final_decision") or "WAIT").upper()
        existing = finite_or_none(final.get("display_risk_multiplier"))
        if existing is None:
            existing = finite_or_none((canonical.get("risk_plan") or {}).get("risk_multiplier"))
        existing = float(np.clip(existing if existing is not None else 1.0, 0.0, 1.0))
        horizon = int(final.get("selected_horizon") or 1)
        horizon = horizon if horizon in HORIZONS else 1
        returns_h = _horizon_returns(frame, horizon).dropna()
        if len(returns_h) < minimum:
            raise ValueError(f"CVaR scenarios require at least {minimum} settled horizon returns.")
        if direction == "BUY":
            unit_losses = -returns_h.to_numpy(dtype=float)
        elif direction == "SELL":
            unit_losses = returns_h.to_numpy(dtype=float)
        else:
            unit_losses = np.abs(returns_h.to_numpy(dtype=float))
        alpha = 0.95
        base_var = float(np.quantile(unit_losses, alpha))
        base_tail = unit_losses[unit_losses >= base_var]
        base_cvar = float(np.mean(base_tail)) if len(base_tail) else base_var
        max_cvar = max(base_cvar, 1e-12)
        daily_room = finite_or_none((canonical.get("risk_plan") or {}).get("daily_risk_room"))
        daily_room = float(daily_room) if daily_room is not None and daily_room > 0 else max_cvar
        evaluations: list[dict[str, Any]] = []
        permitted: list[float] = []
        for multiplier in (0.00, 0.25, 0.50, 0.75, 1.00):
            adjusted = unit_losses * multiplier + abs(float(transaction_cost_return)) * multiplier
            var = float(np.quantile(adjusted, alpha))
            tail = adjusted[adjusted >= var]
            cvar = float(np.mean(tail)) if len(tail) else var
            expected = float(np.mean(adjusted))
            consumption = safe_div(cvar, daily_room, 0.0)
            within_existing = multiplier <= existing + 1e-12
            satisfies = bool(within_existing and cvar <= max_cvar * existing + 1e-12 and (consumption or 0.0) <= 1.0 + 1e-12)
            if satisfies:
                permitted.append(multiplier)
            evaluations.append({
                "risk_multiplier": multiplier,
                "expected_loss": expected,
                "empirical_var": var,
                "empirical_cvar": cvar,
                "worst_supported_loss": float(np.max(adjusted)),
                "effective_sample_count": len(adjusted),
                "fallback_level": "GLOBAL_HORIZON",
                "transaction_cost_adjusted_loss": expected,
                "daily_risk_room_consumption": consumption,
                "satisfies_limits": satisfies,
            })
        selected = max(permitted) if permitted else 0.0
        selected = min(selected, existing)
        return method_contract(
            identity,
            method_name="ROCKAFELLAR_URYASEV_CVAR_RISK_BUDGET",
            method_version=CVAR_VERSION,
            horizon_hours=horizon,
            condition_key=f"{direction}|H{horizon}",
            sample_count=len(unit_losses),
            minimum_sample_required=minimum,
            fallback_level="GLOBAL_HORIZON",
            reliability_status="SUPPORTED",
            assumption_status="EMPIRICAL_SCENARIO_ADAPTATION",
            limitations=(
                "Historical analogue scenarios use a hierarchical fallback; current package evidence may fall back to global horizon.",
                "The selected multiplier is advisory shadow evidence and cannot increase existing risk or place an order.",
            ),
            status="AVAILABLE",
            protected_direction=direction,
            existing_risk_multiplier=existing,
            selected_risk_multiplier=selected,
            risk_multiplier_increased=False,
            evaluations=evaluations,
            scenario_hierarchy_used="direction+horizon -> global horizon fallback",
            order_placement_allowed=False,
        )
    except Exception as exc:
        final = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
        original = finite_or_none(final.get("display_risk_multiplier"))
        result = unavailable_contract(identity, "ROCKAFELLAR_URYASEV_CVAR_RISK_BUDGET", CVAR_VERSION, exc, minimum_sample_required=minimum)
        result.update({"original_protected_risk_multiplier": original, "protected_result_preserved": True, "warning": "CVaR evidence failed safely; protected result was not changed."})
        return result


def _piecewise_pit(levels: np.ndarray, values: np.ndarray, realized: float) -> float:
    # Explicit linear tails between (value_0 - scale, 0) and first quantile,
    # and last quantile to (value_last + scale, 1).
    scale = max(float(np.std(values)), abs(float(values[-1] - values[0])), 1e-6)
    x = np.r_[values[0] - 2.0 * scale, values, values[-1] + 2.0 * scale]
    p = np.r_[0.0, levels, 1.0]
    return float(np.interp(realized, x, p, left=0.0, right=1.0))


def density_pit_diagnostics(frame: pd.DataFrame, identity: ResearchIdentity, *, window: int = 240) -> dict[str, Any]:
    minimum = window + 60
    try:
        horizon_outputs: dict[str, Any] = {}
        for horizon in HORIZONS:
            realized = _horizon_returns(frame, horizon)
            records: list[dict[str, Any]] = []
            for i in range(window, len(frame) - horizon):
                past = realized.iloc[max(0, i - window):i].dropna().to_numpy(dtype=float)
                actual = finite_or_none(realized.iloc[i])
                if len(past) < max(60, window // 2) or actual is None:
                    continue
                original = np.quantile(past, QUANTILE_LEVELS).astype(float)
                rearranged = np.maximum.accumulate(original)
                severity = float(np.max(rearranged - original))
                scale = float(np.std(past)) or 1e-12
                severe = severity > 0.5 * scale
                if severe:
                    continue
                pit = _piecewise_pit(np.asarray(QUANTILE_LEVELS, dtype=float), rearranged, actual)
                epsilon = 1e-8
                clipped = min(max(pit, epsilon), 1.0 - epsilon)
                records.append({
                    "forecast_origin_time": frame["time"].iloc[i].isoformat(),
                    "settled_target_time": frame["time"].iloc[i + horizon].isoformat(),
                    "pit_value": pit,
                    "transformed_normal_score": norm_ppf(clipped, epsilon),
                    "original_quantiles": original.tolist(),
                    "rearranged_quantiles": rearranged.tolist(),
                    "crossing_severity": severity,
                    "cdf_construction_status": "MONOTONE" if severity <= 1e-15 else "MINOR_CROSSING_REARRANGED",
                })
            pits = np.asarray([r["pit_value"] for r in records], dtype=float)
            if len(pits) < 40:
                horizon_outputs[str(horizon)] = {"status": "INSUFFICIENT_SAMPLE", "sample_count": len(pits), "records_tail": records[-20:]}
                continue
            autocorr: dict[str, float | None] = {}
            for lag in range(1, 7):
                if len(pits) <= lag or np.std(pits[:-lag]) <= 1e-12 or np.std(pits[lag:]) <= 1e-12:
                    autocorr[str(lag)] = None
                else:
                    autocorr[str(lag)] = float(np.corrcoef(pits[:-lag], pits[lag:])[0, 1])
            hist, edges = np.histogram(pits, bins=np.linspace(0.0, 1.0, 11))
            horizon_outputs[str(horizon)] = {
                "status": "AVAILABLE",
                "sample_count": len(pits),
                "pit_mean": float(np.mean(pits)),
                "pit_variance": float(np.var(pits, ddof=1)),
                "uniformity_histogram": hist.tolist(),
                "histogram_edges": edges.tolist(),
                "tail_concentration": float(np.mean((pits < 0.05) | (pits > 0.95))),
                "autocorrelation_lag_1_to_6": autocorr,
                "condition_level_diagnostics": {"GLOBAL": {"sample_count": len(pits), "mean": float(np.mean(pits)), "variance": float(np.var(pits, ddof=1))}},
                "records_tail": records[-60:],
                "all_pit_values": pits.tolist(),
            }
        available = [x for x in horizon_outputs.values() if x.get("status") == "AVAILABLE"]
        return method_contract(
            identity,
            method_name="DIEBOLD_GUNTHER_TAY_PIT_DIAGNOSTICS",
            method_version=DENSITY_VERSION,
            sample_count=max([int(x.get("sample_count", 0)) for x in horizon_outputs.values()] or [0]),
            minimum_sample_required=minimum,
            fallback_level="ROLLING_EMPIRICAL_QUANTILE_CDF",
            reliability_status="SUPPORTED" if available else "INSUFFICIENT_SAMPLE",
            assumption_status="CAUSAL_SETTLED_DENSITY_DIAGNOSTIC",
            limitations=(
                "The CDF uses causal rolling quantiles and monotone piecewise-linear interpolation with explicit finite tails.",
                "Severe quantile crossing is not silently repaired; those PIT observations are excluded with status evidence.",
                "Overlapping horizons can induce serial dependence, which is separately diagnosed.",
            ),
            status="AVAILABLE" if available else "INSUFFICIENT_SAMPLE",
            horizons=horizon_outputs,
        )
    except Exception as exc:
        return unavailable_contract(identity, "DIEBOLD_GUNTHER_TAY_PIT_DIAGNOSTICS", DENSITY_VERSION, exc, minimum_sample_required=minimum)


def berkowitz_test_from_pits(pits: Sequence[float]) -> dict[str, Any]:
    epsilon = 1e-8
    p = np.asarray([min(max(float(x), epsilon), 1.0 - epsilon) for x in pits if math.isfinite(float(x))], dtype=float)
    z = np.asarray([norm_ppf(x, epsilon) for x in p], dtype=float)
    n = len(z)
    if n < 25:
        return {"status": "INSUFFICIENT_SAMPLE", "sample_count": n, "small_sample_warning": True}
    null_ll = float(np.sum(-0.5 * (math.log(2.0 * math.pi) + z * z)))
    y, x = z[1:], z[:-1]
    x_mean, y_mean = float(np.mean(x)), float(np.mean(y))
    denominator = float(np.sum((x - x_mean) ** 2))
    rho = float(np.sum((x - x_mean) * (y - y_mean)) / denominator) if denominator > 1e-12 else 0.0
    rho = float(np.clip(rho, -0.995, 0.995))
    mu = float((y_mean - rho * x_mean) / (1.0 - rho)) if abs(1.0 - rho) > 1e-8 else y_mean
    residuals = y - mu - rho * (x - mu)
    variance = float(max(np.mean(residuals ** 2), 1e-12))
    alternative_ll = float(np.sum(-0.5 * (math.log(2.0 * math.pi * variance) + (residuals ** 2) / variance)))
    lr = max(0.0, 2.0 * (alternative_ll - null_ll))
    p_value, source = chi_square_sf(lr, 3)
    if p_value is None:
        status = "WARNING"
    elif p_value < 0.01:
        status = "FAIL"
    elif p_value < 0.05:
        status = "WARNING"
    else:
        status = "PASS"
    return {
        "status": status,
        "null_log_likelihood": null_ll,
        "alternative_log_likelihood": alternative_ll,
        "lr_statistic": lr,
        "degrees_of_freedom": 3,
        "approximate_p_value": p_value,
        "p_value_source": source,
        "estimated_mean": mu,
        "estimated_variance": variance,
        "estimated_rho": rho,
        "sample_count": n,
        "small_sample_warning": n < 100,
        "pit_clip_epsilon": epsilon,
    }


def berkowitz_density_tests(identity: ResearchIdentity, pit_result: Mapping[str, Any]) -> dict[str, Any]:
    try:
        horizons: dict[str, Any] = {}
        for horizon in HORIZONS:
            pit_h = (pit_result.get("horizons") or {}).get(str(horizon)) or {}
            pits = pit_h.get("all_pit_values") or []
            horizons[str(horizon)] = berkowitz_test_from_pits(pits)
        statuses = [x.get("status") for x in horizons.values()]
        overall = "FAIL" if "FAIL" in statuses else ("WARNING" if "WARNING" in statuses else ("PASS" if "PASS" in statuses else "INSUFFICIENT_SAMPLE"))
        return method_contract(
            identity,
            method_name="BERKOWITZ_DENSITY_TEST",
            method_version=BERKOWITZ_VERSION,
            sample_count=max([int(x.get("sample_count", 0)) for x in horizons.values()] or [0]),
            minimum_sample_required=25,
            fallback_level="SCIPY_OR_DOCUMENTED_CRITICAL_VALUE",
            reliability_status=overall,
            assumption_status="GAUSSIAN_AR1_ALTERNATIVE_DIAGNOSTIC",
            limitations=(
                "PIT clipping uses only a documented numerical epsilon and does not hide poor forecasts.",
                "The Gaussian AR(1) alternative is a calibration diagnostic, not a complete density model.",
                "A failure can lower density trust or recommend WAIT but cannot replace an existing forecast path.",
            ),
            status=overall,
            horizons=horizons,
            allowed_effects=["LOWER_DENSITY_TRUST", "CALIBRATION_WARNING", "LOWER_SHADOW_READINESS", "RECOMMEND_WAIT"],
            forecast_path_replacement_allowed=False,
        )
    except Exception as exc:
        return unavailable_contract(identity, "BERKOWITZ_DENSITY_TEST", BERKOWITZ_VERSION, exc, minimum_sample_required=25)


def build_tail_density_stack(
    frame: pd.DataFrame,
    identity: ResearchIdentity,
    *,
    volatility_stack: Mapping[str, Any] | None = None,
    canonical: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    canonical = canonical or {}
    caviar = caviar_shadow_quantiles(frame, identity)
    taylor = taylor_semiparametric_var_es(frame, identity, caviar, volatility_stack=volatility_stack, canonical=canonical)
    joint = joint_var_es_scoring(frame, identity, caviar, taylor)
    cvar = cvar_risk_budget(frame, identity, canonical)
    pit = density_pit_diagnostics(frame, identity)
    berkowitz = berkowitz_density_tests(identity, pit)
    return {
        "version": VERSION,
        "caviar": caviar,
        "joint_var_es": joint,
        "taylor_var_es": taylor,
        "cvar_risk_budget": cvar,
        "density_pit": pit,
        "berkowitz": berkowitz,
    }


__all__ = [
    "VERSION", "quantile_loss", "caviar_shadow_quantiles", "fz0_positive_loss_score",
    "taylor_semiparametric_var_es", "joint_var_es_scoring", "cvar_risk_budget",
    "density_pit_diagnostics", "berkowitz_test_from_pits", "berkowitz_density_tests",
    "build_tail_density_stack",
]
