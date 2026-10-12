"""Bounded Wald sequential probability-ratio monitors for settled outcomes."""
from __future__ import annotations

from typing import Any, Iterable, Mapping
import math

import numpy as np
import pandas as pd

from core.quant_research_v4_contract_20260622 import common_result, stable_hash, unavailable

METHOD_ID = "WALD_SEQUENTIAL_PERFORMANCE_MONITOR"
PAPER_TITLE = "Sequential Tests of Statistical Hypotheses"
PAPER_AUTHORS = "Abraham Wald"
ALPHA = 0.05
BETA = 0.10
UPPER = math.log((1.0 - BETA) / ALPHA)
LOWER = math.log(BETA / (1.0 - ALPHA))


def update_sprt(
    previous: Mapping[str, Any] | None,
    observations: Iterable[tuple[str, int]],
    *,
    p0: float,
    p1: float,
    epoch_id: str,
    reset_reason: str = "INITIALIZATION",
) -> dict[str, Any]:
    """Update one one-sided degradation monitor; H1 is the degraded Bernoulli rate."""
    prev = dict(previous or {})
    if prev and str(prev.get("epoch_id")) != str(epoch_id):
        # Epoch changes are explicit and retain the old state in audit metadata.
        prev = {"previous_epoch_state": prev, "epoch_id": epoch_id, "reset_reason": reset_reason}
    seen = set(str(x) for x in (prev.get("seen_keys") or []))
    log_lr = float(prev.get("log_LR", 0.0) or 0.0)
    state_before = str(prev.get("state") or "CONTINUE_MONITORING")
    count = int(prev.get("observation_count", 0) or 0)
    accepted = 0
    for key, raw in observations:
        key = str(key)
        if key in seen:
            continue
        obs = 1 if int(raw) else 0
        log_lr += math.log((p1 if obs else 1.0 - p1) / (p0 if obs else 1.0 - p0))
        seen.add(key); count += 1; accepted += 1
    if log_lr >= UPPER:
        state = "DEGRADATION_EVIDENCE"
    elif log_lr <= LOWER:
        state = "ACCEPTABLE_PERFORMANCE_EVIDENCE"
    else:
        state = "CONTINUE_MONITORING"
    last_notified = str(prev.get("last_notified_state") or "")
    boundary_crossed = state in {"DEGRADATION_EVIDENCE", "ACCEPTABLE_PERFORMANCE_EVIDENCE"} and state != state_before
    notify = boundary_crossed and last_notified != state
    if notify:
        last_notified = state
    # Bound the canonical payload; durable normalized storage retains current state.
    seen_tail = sorted(seen)[-3000:]
    return {
        "epoch_id": str(epoch_id),
        "reset_reason": str(prev.get("reset_reason") or reset_reason),
        "log_LR": float(log_lr),
        "upper_boundary": float(UPPER),
        "lower_boundary": float(LOWER),
        "state": state,
        "observation_count": count,
        "new_unique_observations": accepted,
        "seen_keys": seen_tail,
        "p0": float(p0), "p1": float(p1),
        "boundary_crossed_this_update": bool(boundary_crossed),
        "notify_once": bool(notify),
        "last_notified_state": last_notified,
    }


def _key(row: Mapping[str, Any], index: Any) -> str:
    return stable_hash({
        "prediction_id": row.get("prediction_id") or row.get("id") or row.get("run_id") or index,
        "horizon": row.get("horizon_hours") or 1,
        "target_time": row.get("__target_time") or row.get("actual_time") or row.get("due_time"),
    })


def _binary(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series | None:
    lower = {str(c).lower(): c for c in frame.columns}
    found = next((lower[n] for n in names if n in lower), None)
    return pd.to_numeric(frame[found], errors="coerce") if found is not None else None


def run_wald_monitors(
    identity: Mapping[str, Any],
    settled: pd.DataFrame,
    *,
    canonical: Mapping[str, Any] | None = None,
    previous_states: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    n = int(len(settled)) if isinstance(settled, pd.DataFrame) else 0
    try:
        previous_states = dict(previous_states or {})
        epoch = str(previous_states.get("epoch_id") or "QUANT_V4_EPOCH_1")
        monitors: dict[str, Any] = {}
        rows = settled.to_dict("records") if isinstance(settled, pd.DataFrame) else []
        keys = [_key(row, i) for i, row in enumerate(rows)]

        direction = _binary(settled, ("direction_correct", "direction_hit", "correct_direction")) if isinstance(settled, pd.DataFrame) else None
        if direction is not None:
            obs = [(keys[i], int(1 - v)) for i, v in enumerate(direction.fillna(np.nan)) if np.isfinite(v)]  # event=incorrect
            monitors["direction_correctness"] = update_sprt(previous_states.get("direction_correctness"), obs, p0=0.45, p1=0.60, epoch_id=epoch)
        else:
            monitors["direction_correctness"] = update_sprt(previous_states.get("direction_correctness"), [], p0=0.45, p1=0.60, epoch_id=epoch)

        interval = _binary(settled, ("interval_hit", "coverage_flag", "inside_interval")) if isinstance(settled, pd.DataFrame) else None
        if interval is not None:
            obs = [(keys[i], int(1 - v)) for i, v in enumerate(interval.fillna(np.nan)) if np.isfinite(v)]
            monitors["interval_misses"] = update_sprt(previous_states.get("interval_misses"), obs, p0=0.10, p1=0.25, epoch_id=epoch)
        else:
            monitors["interval_misses"] = update_sprt(previous_states.get("interval_misses"), [], p0=0.10, p1=0.25, epoch_id=epoch)

        direct_tp = _binary(settled, ("tp_before_sl", "tp_first", "target_before_stop")) if isinstance(settled, pd.DataFrame) else None
        if direct_tp is not None:
            observations = [(keys[i], int(1 - v)) for i, v in enumerate(direct_tp.fillna(np.nan)) if np.isfinite(v)]
            monitors["tp_before_sl"] = update_sprt(previous_states.get("tp_before_sl"), observations, p0=0.45, p1=0.60, epoch_id=epoch)
        else:
            target = _binary(settled, ("target_hit", "tp_hit", "take_profit_hit")) if isinstance(settled, pd.DataFrame) else None
            stop = _binary(settled, ("stop_hit", "sl_hit", "stop_loss_hit")) if isinstance(settled, pd.DataFrame) else None
            if target is not None and stop is not None:
                observations = []
                for i, (tp, sl) in enumerate(zip(target, stop)):
                    if not np.isfinite(tp) or not np.isfinite(sl) or (tp == sl):
                        continue
                    observations.append((keys[i], int(sl == 1 and tp != 1)))  # event=SL before TP
                monitors["tp_before_sl"] = update_sprt(previous_states.get("tp_before_sl"), observations, p0=0.45, p1=0.60, epoch_id=epoch)
            else:
                monitors["tp_before_sl"] = update_sprt(previous_states.get("tp_before_sl"), [], p0=0.45, p1=0.60, epoch_id=epoch)

        severity = _binary(settled, ("tail_severity_failure", "es_severity_failure")) if isinstance(settled, pd.DataFrame) else None
        if severity is None and isinstance(settled, pd.DataFrame):
            loss = _binary(settled, ("realized_loss", "loss", "positive_loss", "maximum_adverse_excursion"))
            es_forecast = _binary(settled, ("predicted_es", "expected_shortfall", "es", "cvar", "es_forecast"))
            var_forecast = _binary(settled, ("predicted_var", "var", "value_at_risk", "var_forecast"))
            if loss is not None and es_forecast is not None and var_forecast is not None:
                valid_tail = loss > var_forecast
                severity = ((loss > es_forecast) & valid_tail).astype(float).where(valid_tail)
        if severity is not None:
            obs = [(keys[i], int(v)) for i, v in enumerate(severity.fillna(np.nan)) if np.isfinite(v)]
            monitors["tail_severity_failures"] = update_sprt(previous_states.get("tail_severity_failures"), obs, p0=0.05, p1=0.20, epoch_id=epoch)
        else:
            monitors["tail_severity_failures"] = update_sprt(previous_states.get("tail_severity_failures"), [], p0=0.05, p1=0.20, epoch_id=epoch)

        canonical = dict(canonical or {})
        freshness_fail = bool(canonical.get("stale") or (canonical.get("data_quality") or {}).get("freshness") == "STALE")
        freshness_key = stable_hash({"calculation_id": identity.get("calculation_id"), "completed_h1": identity.get("latest_completed_broker_h1_time")})
        monitors["canonical_freshness_failures"] = update_sprt(
            previous_states.get("canonical_freshness_failures"), [(freshness_key, int(freshness_fail))],
            p0=0.02, p1=0.15, epoch_id=epoch,
        )
        states = [m["state"] for m in monitors.values()]
        overall = "DEGRADATION_EVIDENCE" if "DEGRADATION_EVIDENCE" in states else ("ACCEPTABLE_PERFORMANCE_EVIDENCE" if all(s == "ACCEPTABLE_PERFORMANCE_EVIDENCE" for s in states) else "CONTINUE_MONITORING")
        total_new = sum(int(m["new_unique_observations"]) for m in monitors.values())
        return common_result(
            identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            exact_or_adaptation="BOUNDED_ONE_SIDED_BERNOULLI_SPRT_MONITORS",
            sample_count=n, effective_sample_count=total_new, minimum_required_samples=1,
            status="AVAILABLE", score=max((m["log_LR"] for m in monitors.values()), default=0.0),
            confidence=None, reliability=overall,
            assumptions=["Each settled prediction-horizon-target tuple updates a monitor at most once.", "H1 is a pre-registered one-sided degradation rate for each Bernoulli stream."],
            limitations=["Sequential boundaries provide evidence under the configured Bernoulli hypotheses; they do not guarantee profit.", "Epoch resets require an explicit epoch ID and reset reason and are never silent."],
            alpha=ALPHA, beta=BETA, upper=UPPER, lower=LOWER,
            monitors=monitors, sequential_monitor_status=overall,
            epoch_id=epoch, reset_reason=str(previous_states.get("reset_reason") or "INITIALIZATION"),
            repeated_boundary_notifications_prevented=True,
        )
    except Exception as exc:
        return unavailable(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            error=exc, minimum_required_samples=1, sample_count=n,
            limitations=["A failed monitor update preserves prior durable state through the canonical transaction boundary."])


__all__ = ["run_wald_monitors", "update_sprt", "UPPER", "LOWER"]
