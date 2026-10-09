"""Deterministic Hansen-style Superior Predictive Ability shadow test."""
from __future__ import annotations

from typing import Any, Mapping, Sequence
import math
import numpy as np
import pandas as pd

from core.research_validation_common_20260621 import deterministic_seed, finite, profile_int, stable_hash, utc_now_iso

VERSION = "superior-predictive-ability-20260621-v1"


def _moving_block_indices(n: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    block = max(1, min(int(block_length), n))
    starts = rng.integers(0, n, size=int(math.ceil(n / block)))
    return np.concatenate([(np.arange(start, start + block) % n) for start in starts])[:n]


def evaluate_superior_predictive_ability(
    loss_panel: Any,
    *,
    benchmark_id: str = "canonical",
    loss_name: str = "MAE",
    horizon: int = 1,
    minimum_samples: int = 48,
    alpha: float = 0.05,
    block_length: int | None = None,
    bootstrap_iterations: int | None = None,
    calibration_pass: bool = False,
    regime_catastrophe_pass: bool = False,
    resource_budget_pass: bool = False,
    second_window_pass: bool = False,
    rollback_available: bool = True,
    source_generation_id: str = "",
) -> dict[str, Any]:
    evaluated_at = utc_now_iso()
    if isinstance(loss_panel, pd.DataFrame):
        panel = loss_panel.copy(deep=False)
    else:
        try:
            panel = pd.DataFrame(loss_panel)
        except Exception:
            panel = pd.DataFrame()
    if panel.empty or benchmark_id not in panel.columns:
        return {
            "version": VERSION, "status": "INSUFFICIENT_EVIDENCE", "evaluated_at": evaluated_at,
            "benchmark_id": benchmark_id, "number_of_challengers": 0, "promotion_allowed": False,
            "reason": "No aligned benchmark/challenger loss panel.", "row": {},
        }
    numeric = panel.apply(pd.to_numeric, errors="coerce")
    challengers = [c for c in numeric.columns if c != benchmark_id and numeric[c].notna().any()]
    aligned = numeric[[benchmark_id] + challengers].dropna() if challengers else pd.DataFrame()
    n = len(aligned)
    iterations = int(bootstrap_iterations or profile_int(1000, 49))
    block = int(block_length or max(2, round(n ** (1 / 3)))) if n else 1
    minimum_pass = n >= minimum_samples and bool(challengers)
    row: dict[str, Any] = {
        "evaluation_id": "",
        "benchmark_id": benchmark_id,
        "challenger_family": "existing_prediction_paths",
        "number_of_challengers": len(challengers),
        "loss_name": loss_name,
        "horizon": int(horizon),
        "bootstrap_method": "deterministic_moving_block",
        "block_length": block,
        "bootstrap_iterations": iterations,
        "spa_statistic": None,
        "spa_p_value": None,
        "best_challenger_id": None,
        "best_effect_size": None,
        "minimum_sample_pass": bool(minimum_pass),
        "stability_pass": bool(second_window_pass),
        "resource_budget_pass": bool(resource_budget_pass),
        "promotion_allowed": False,
        "source_generation_id": str(source_generation_id),
        "evaluated_at": evaluated_at,
        "calculation_version": VERSION,
    }
    if not minimum_pass:
        row["evaluation_id"] = "SPA-" + stable_hash({k: v for k, v in row.items() if k not in {"evaluation_id", "evaluated_at"}})[:24]
        return {"version": VERSION, "status": "INSUFFICIENT_EVIDENCE", "evaluated_at": evaluated_at, "row": row, "promotion_allowed": False}

    # Positive differential means the challenger has lower loss than benchmark.
    differential = np.column_stack([(aligned[benchmark_id] - aligned[c]).to_numpy(float) for c in challengers])
    means = differential.mean(axis=0)
    std = differential.std(axis=0, ddof=1)
    se = np.where(std > 1e-12, std / math.sqrt(n), 1e-12)
    observed = float(np.max(np.maximum(means, 0.0) / se))
    best_idx = int(np.argmax(means))
    best_effect = float(means[best_idx] / max(float(aligned[benchmark_id].mean()), 1e-12))
    centered = differential - means
    rng = np.random.default_rng(deterministic_seed([source_generation_id, benchmark_id, challengers, horizon, iterations, block]))
    boot_stats = np.empty(iterations, dtype=float)
    for index in range(iterations):
        sample = centered[_moving_block_indices(n, block, rng)]
        boot_mean = sample.mean(axis=0)
        boot_stats[index] = float(np.max(np.maximum(boot_mean, 0.0) / se))
    p_value = float((1 + np.count_nonzero(boot_stats >= observed)) / (iterations + 1))
    row.update({
        "spa_statistic": finite(observed),
        "spa_p_value": finite(p_value),
        "best_challenger_id": str(challengers[best_idx]),
        "best_effect_size": finite(best_effect),
    })
    effect_pass = best_effect >= 0.01
    row["promotion_allowed"] = bool(
        p_value <= alpha and effect_pass and calibration_pass and regime_catastrophe_pass
        and resource_budget_pass and second_window_pass and rollback_available
    )
    row["evaluation_id"] = "SPA-" + stable_hash({k: v for k, v in row.items() if k not in {"evaluation_id", "evaluated_at"}})[:24]
    return {
        "version": VERSION,
        "status": "SUPERIORITY_SUPPORTED" if p_value <= alpha and effect_pass else "NO_SUPERIORITY_EVIDENCE",
        "evaluated_at": evaluated_at,
        "row": row,
        "promotion_allowed": row["promotion_allowed"],
        "gates": {
            "calibration_not_worse": bool(calibration_pass),
            "no_regime_catastrophe": bool(regime_catastrophe_pass),
            "resource_budget": bool(resource_budget_pass),
            "second_chronological_window": bool(second_window_pass),
            "rollback_available": bool(rollback_available),
        },
    }


__all__ = ["VERSION", "evaluate_superior_predictive_ability"]
