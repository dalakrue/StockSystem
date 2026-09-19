"""Settings-owned orchestrator for the ten Project Quant V12 shadow layers."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Iterable, Mapping
import math

import numpy as np

from core.canonical.snapshot import CanonicalRunSnapshot
from research import calibration_sharpness_frontier, cost_aware_aim_position
from research import dcc_dependency_state, dynamic_model_averaging, gas_tail_state
from research import hawkes_event_intensity, proper_scoring, rough_volatility_proxy
from research import selective_risk_coverage, time_uniform_confidence
from research.run_snapshot_v12 import ResearchRunSnapshot, stable_hash

CONFIGURATION = {
    "max_outcomes": 5000,
    "dma_forgetting_factor": 0.98,
    "dma_weight_floor": 0.02,
    "dma_weight_cap": 0.80,
    "dcc_alpha": 0.03,
    "dcc_beta": 0.95,
    "rough_scales": [1, 2, 4, 8, 16],
    "hawkes_baseline": 0.05,
    "hawkes_excitation": 0.35,
    "hawkes_decay": 1.0,
    "confidence_alpha": 0.05,
    "history_cap": 500,
    "shadow_only": True,
}


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _row_time(row: Mapping[str, Any]) -> datetime | None:
    for key in ("settled_at", "settled_at_utc", "actual_time", "target_time", "forecast_origin_time"):
        parsed = _parse_time(row.get(key))
        if parsed is not None:
            return parsed
    return None


def chronological_settled_outcomes(rows: Iterable[Mapping[str, Any]], *, cutoff: datetime, apply_embargo: bool = True) -> tuple[list[dict[str, Any]], list[str]]:
    """Filter to settled, dated, prediction-time-safe rows and apply horizon embargo."""
    accepted: list[tuple[datetime, dict[str, Any]]] = []
    warnings: list[str] = []
    undated = future = unsettled = 0
    cutoff_utc = cutoff.astimezone(timezone.utc)
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        status = str(row.get("outcome_status") or row.get("status") or ("SETTLED" if row.get("settled_outcome") is not None else "")).upper()
        if status != "SETTLED":
            unsettled += 1
            continue
        when = _row_time(row)
        if when is None:
            undated += 1
            continue
        if when.astimezone(timezone.utc) > cutoff_utc:
            future += 1
            continue
        accepted.append((when.astimezone(timezone.utc), row))
    accepted.sort(key=lambda item: (item[0], str(item[1].get("run_id", "")), int(float(item[1].get("horizon_hours", 0) or 0))))
    if apply_embargo:
        kept: list[tuple[datetime, dict[str, Any]]] = []
        last_by_horizon: dict[int, datetime] = {}
        embargoed = 0
        for when, row in accepted:
            try:
                horizon = max(1, int(float(row.get("horizon_hours", 1) or 1)))
            except (TypeError, ValueError):
                horizon = 1
            origin = _parse_time(row.get("forecast_origin_time")) or when - timedelta(hours=horizon)
            previous = last_by_horizon.get(horizon)
            if previous is not None and origin.astimezone(timezone.utc) < previous + timedelta(hours=horizon):
                embargoed += 1
                continue
            last_by_horizon[horizon] = origin.astimezone(timezone.utc)
            kept.append((when, row))
        accepted = kept
        if embargoed:
            warnings.append(f"overlapping-horizon embargo removed {embargoed} settled rows")
    if undated:
        warnings.append(f"strict chronology rejected {undated} undated settled rows")
    if future:
        warnings.append(f"no-look-ahead cutoff rejected {future} future-settled rows")
    if unsettled:
        warnings.append(f"ignored {unsettled} unsettled rows")
    return [row for _, row in accepted], warnings


def _float(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        try:
            value = float(row.get(key))
            if math.isfinite(value):
                return value
        except (TypeError, ValueError):
            pass
    return None


def _probabilities(rows: list[Mapping[str, Any]]) -> tuple[list[float], list[float]]:
    p, y = [], []
    for row in rows:
        value = _float(row, "direction_probability", "probability", "confidence", "priority_score")
        actual = _float(row, "direction_correct")
        if actual is None:
            actual = 1.0 if str(row.get("settled_outcome")).upper() == "WIN" else 0.0 if str(row.get("settled_outcome")).upper() == "LOSS" else None
        if value is None or actual is None:
            continue
        if value > 1.0:
            value /= 100.0
        p.append(float(np.clip(value, 0.0, 1.0))); y.append(float(np.clip(actual, 0.0, 1.0)))
    return p, y


def _intervals(rows: list[Mapping[str, Any]]) -> tuple[list[float], list[float], list[float], list[float]]:
    lower, upper, actual, pit = [], [], [], []
    for row in rows:
        lo = _float(row, "lower_bound", "lower_90")
        hi = _float(row, "upper_bound", "upper_90")
        y = _float(row, "actual_price", "actual_close")
        pred = _float(row, "predicted_price", "predicted_close")
        if lo is None or hi is None or y is None or lo > hi:
            continue
        lower.append(lo); upper.append(hi); actual.append(y)
        if pred is not None and hi > lo:
            pit.append(float(np.clip(0.5 + (y - pred) / (hi - lo), 0.0, 1.0)))
    return lower, upper, actual, pit


def _residuals(rows: list[Mapping[str, Any]]) -> list[float]:
    result = []
    for row in rows:
        residual = _float(row, "residual")
        if residual is None:
            actual = _float(row, "actual_price", "actual_close")
            predicted = _float(row, "predicted_price", "predicted_close")
            residual = actual - predicted if actual is not None and predicted is not None else None
        if residual is not None:
            result.append(residual)
    return result


def _returns(rows: list[Mapping[str, Any]]) -> list[float]:
    prices = [_float(row, "actual_price", "actual_close") for row in rows]
    prices = [value for value in prices if value is not None and value > 0]
    if len(prices) < 2:
        return []
    values = np.asarray(prices, dtype=float)
    return np.diff(np.log(values)).tolist()


def _model_losses(rows: list[Mapping[str, Any]]) -> list[dict[str, float]]:
    history = []
    for row in rows:
        mapping = row.get("model_losses")
        if isinstance(mapping, Mapping):
            clean = {str(k): float(v) for k, v in mapping.items() if _float({"v": v}, "v") is not None}
            if clean:
                history.append(clean)
    return history


def _cross_market(snapshot: CanonicalRunSnapshot) -> dict[str, list[float]]:
    series: dict[str, list[float]] = {}
    for key, value in snapshot.histories.items():
        if isinstance(value, Mapping):
            for asset, points in value.items():
                if isinstance(points, (list, tuple)) and len(points) >= 2:
                    try:
                        arr = np.asarray(points, dtype=float)
                        arr = arr[np.isfinite(arr)]
                        if arr.size >= 2:
                            series[str(asset)] = np.diff(np.log(arr[arr > 0])).tolist() if np.all(arr > 0) else arr.tolist()
                    except Exception:
                        pass
        elif isinstance(value, list) and value and all(isinstance(row, Mapping) for row in value):
            numeric_keys = [name for name in value[0] if any(token in str(name).lower() for token in ("eurusd", "xauusd", "return"))]
            for name in numeric_keys:
                values = [_float(row, str(name)) for row in value]
                clean = [v for v in values if v is not None]
                if len(clean) >= 2:
                    series[str(name)] = clean
    return series


def _events(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    events = []
    previous_decision = None
    for index, row in enumerate(rows):
        when = _row_time(row)
        t = when.timestamp() / 3600.0 if when else float(index)
        correct = _float(row, "direction_correct")
        if correct == 0.0 or str(row.get("settled_outcome")).upper() == "LOSS":
            events.append({"time": t, "event_type": "prediction_miss"})
        decision = str(row.get("decision") or row.get("predicted_direction") or "").upper()
        if previous_decision and decision and decision != previous_decision:
            events.append({"time": t, "event_type": "decision_flip"})
        if decision:
            previous_decision = decision
        error = _float(row, "absolute_error")
        if error is not None and error > 0:
            events.append({"time": t, "event_type": "jump", "weight": min(3.0, 1.0 + error)})
    return events


def evaluate_v12(snapshot: CanonicalRunSnapshot, settled_outcomes: Iterable[Mapping[str, Any]]) -> ResearchRunSnapshot:
    cutoff = snapshot.broker_candle_time
    rows, warnings = chronological_settled_outcomes(settled_outcomes, cutoff=cutoff, apply_embargo=True)
    probabilities, binary = _probabilities(rows)
    lower, upper, actual, pit = _intervals(rows)
    residuals = _residuals(rows)
    returns = _returns(rows)
    model_losses = _model_losses(rows)
    direction_correct = binary
    interval_covered = [float(lo <= y <= hi) for lo, hi, y in zip(lower, upper, actual)]
    losses = [abs(v) for v in residuals]
    loss_scale = max(max(losses, default=1.0), 1e-12)
    normalized_losses = [min(1.0, value / loss_scale) for value in losses]

    proper = proper_scoring.evaluate_settled(rows)
    calibration = calibration_sharpness_frontier.evaluate(lower=lower, upper=upper, observations=actual, pit_values=pit, nominal_coverage=0.9)
    dma = dynamic_model_averaging.recursive_probabilities(model_losses, forgetting_factor=CONFIGURATION["dma_forgetting_factor"], weight_floor=CONFIGURATION["dma_weight_floor"], weight_cap=CONFIGURATION["dma_weight_cap"])
    dcc = dcc_dependency_state.evaluate(_cross_market(snapshot), alpha=CONFIGURATION["dcc_alpha"], beta=CONFIGURATION["dcc_beta"])
    rough = rough_volatility_proxy.evaluate(returns, scales=CONFIGURATION["rough_scales"])
    hawkes = hawkes_event_intensity.evaluate(_events(rows), baseline=CONFIGURATION["hawkes_baseline"], excitation=CONFIGURATION["hawkes_excitation"], decay=CONFIGURATION["hawkes_decay"])
    confidence = time_uniform_confidence.evaluate(direction_correct=direction_correct, interval_covered=interval_covered, loss_differential=[-v for v in normalized_losses], selective_errors=[1.0 - v for v in direction_correct], loss_bounds=(-1.0, 1.0), alpha=CONFIGURATION["confidence_alpha"])
    selective_rows = [{"decision": row.get("decision") or row.get("predicted_direction"), "confidence": p, "direction_correct": y} for row, p, y in zip(rows[-len(probabilities):], probabilities, binary)] if probabilities else []
    selective = selective_risk_coverage.evaluate(selective_rows)
    latest = rows[-1] if rows else {}
    gross = _float(latest, "expected_value", "gross_ev", "realized_pips") or 0.0
    cost = _float(latest, "estimated_cost", "transaction_cost", "spread_pips") or 0.0
    cost_aware = cost_aware_aim_position.evaluate(expected_return_pips=gross, probability_win=probabilities[-1] if probabilities else 0.5, expected_loss_pips=abs(gross) if gross < 0 else 0.0, spread_pips=cost, current_exposure=0.0)
    gas = gas_tail_state.evaluate(residuals)

    results = {
        "proper_scoring": proper,
        "calibration_sharpness_frontier": calibration,
        "dynamic_model_averaging": dma,
        "dcc_dependency_state": dcc,
        "rough_volatility_proxy": rough,
        "hawkes_event_intensity": hawkes,
        "time_uniform_confidence": confidence,
        "selective_risk_coverage": selective,
        "cost_aware_aim_position": cost_aware,
        "gas_tail_state": gas,
    }
    statuses = {name: str(value.get("status") or value.get("interval_frontier", {}).get("status") or "AVAILABLE") for name, value in results.items()}
    sizes = {name: int(value.get("sample_size") or value.get("interval_frontier", {}).get("sample_size") or 0) for name, value in results.items()}
    if not model_losses:
        warnings.append("DMA unavailable: settled outcomes contain no per-model loss vectors")
    if len(_cross_market(snapshot)) < 2:
        warnings.append("DCC unavailable: fewer than two synchronized local cross-market series")
    compact = {
        "mode": "SHADOW ONLY",
        "proper_score_status": proper.get("status"),
        "brier_score": proper.get("brier_score"),
        "interval_frontier_status": calibration.get("interval_frontier", {}).get("status"),
        "interval_coverage": calibration.get("interval_frontier", {}).get("actual_coverage"),
        "dma_status": dma.get("status"),
        "dcc_status": dcc.get("status"),
        "roughness_status": rough.get("status"),
        "hawkes_current_intensity": hawkes.get("current_intensity"),
        "direction_cs": [confidence.get("direction_accuracy", {}).get("final_lower"), confidence.get("direction_accuracy", {}).get("final_upper")],
        "selective_risk": selective.get("best_operating_point", {}).get("selective_risk"),
        "net_ev_pips": cost_aware.get("net_ev_pips"),
        "gas_tail_state": gas.get("tail_state"),
        "production_changed": False,
    }
    source_hashes = {
        "canonical_snapshot": snapshot.source_snapshot_hash or stable_hash(snapshot.to_dict()),
        "settled_outcomes": stable_hash(rows),
        "canonical_histories": stable_hash(snapshot.histories),
    }
    generation = snapshot.generation_id or snapshot.run_id
    cutoff_text = cutoff.isoformat()
    return ResearchRunSnapshot.build(
        run_id=snapshot.run_id,
        calculation_generation=generation,
        broker_time=cutoff_text,
        candle_time=cutoff_text,
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        settled_outcome_cutoff=cutoff_text,
        source_hashes=source_hashes,
        configuration=CONFIGURATION,
        module_statuses=statuses,
        sample_sizes=sizes,
        warnings=warnings,
        compact_results=compact,
        full_results=results,
        created_at_utc=snapshot.created_at_utc.isoformat(),
    )


__all__ = ["CONFIGURATION", "chronological_settled_outcomes", "evaluate_v12"]
