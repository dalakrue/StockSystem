"""Chronological moving/stationary block-bootstrap rank uncertainty."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import math

import numpy as np
import pandas as pd

from core.field10_research_common_20260705 import deterministic_hash

VERSION = "field10-rank-uncertainty-20260705-v1"


def _moving_block_indices(rng: np.random.Generator, n: int, block_length: int) -> np.ndarray:
    blocks = max(1, math.ceil(n / block_length))
    starts = rng.integers(0, max(1, n - block_length + 1), size=blocks)
    return np.concatenate([np.arange(start, min(start + block_length, n)) for start in starts])[:n]


def _stationary_indices(rng: np.random.Generator, n: int, block_length: int) -> np.ndarray:
    probability = 1.0 / max(block_length, 1)
    output = np.empty(n, dtype=int)
    output[0] = int(rng.integers(0, n))
    for i in range(1, n):
        output[i] = int(rng.integers(0, n)) if rng.random() < probability else (output[i - 1] + 1) % n
    return output


def chronological_rank_uncertainty(
    settled_returns: pd.DataFrame, *, base_scores: Mapping[str, float] | None = None,
    snapshot_id: str, formula_version: str, horizon: int = 6,
    draws: int = 500, block_length: int | None = None,
    session_labels: pd.Series | None = None, regime_labels: pd.Series | None = None,
) -> dict[str, Any]:
    work = settled_returns.apply(pd.to_numeric, errors="coerce").dropna(how="all")
    symbols = list(work.columns)
    n = len(work)
    chosen_block = int(block_length or max(6, min(48, 2 * int(horizon))))
    if n < max(60, 3 * chosen_block) or len(symbols) < 2:
        return {"status": "INSUFFICIENT_SETTLED_CHRONOLOGICAL_OUTCOMES", "rows": [],
                "sample_count": n, "block_length": chosen_block, "draws": int(draws)}
    seed = int(deterministic_hash({"snapshot": snapshot_id, "formula": formula_version, "symbols": symbols})[:16], 16) % (2**32)
    rng = np.random.default_rng(seed)
    rank_values = {symbol: [] for symbol in symbols}
    membership = {symbol: [] for symbol in symbols}
    prior_order: list[str] | None = None
    turnover: list[float] = []
    for draw in range(int(draws)):
        indexes = _moving_block_indices(rng, n, chosen_block) if draw % 2 == 0 else _stationary_indices(rng, n, chosen_block)
        sample = work.iloc[indexes]
        # Session/regime stratification is applied when labels align; otherwise
        # the method transparently falls back to chronological block resampling.
        stratified = False
        if session_labels is not None and len(session_labels) == n:
            stratified = True
            grouped = []
            labels = pd.Series(session_labels).reset_index(drop=True)
            for _, locs in labels.groupby(labels).groups.items():
                local = np.asarray(list(locs), dtype=int)
                grouped.append(work.iloc[rng.choice(local, size=len(local), replace=True)])
            sample = pd.concat(grouped).sort_index() if grouped else sample
        estimates = sample.mean(skipna=True)
        if base_scores:
            bounded = pd.Series({symbol: float(base_scores.get(symbol, 0.0)) / 100.0 for symbol in symbols})
            scale = max(float(estimates.abs().median()), 1e-6)
            estimates = estimates / scale + 0.15 * bounded
        ordered = list(estimates.sort_values(ascending=False, kind="mergesort").index)
        ranks = {symbol: ordered.index(symbol) + 1 for symbol in ordered}
        for symbol in symbols:
            rank_values[symbol].append(float(ranks[symbol]))
            membership[symbol].append(int(ranks[symbol] <= 3))
        if prior_order is not None:
            turnover.append(float(np.mean([prior_order.index(symbol) != ordered.index(symbol) for symbol in symbols])))
        prior_order = ordered
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        values = np.asarray(rank_values[symbol], dtype=float)
        rows.append({
            "symbol": symbol, "median_bootstrap_rank": float(np.median(values)),
            "rank_lower_90": float(np.quantile(values, 0.05)), "rank_upper_90": float(np.quantile(values, 0.95)),
            "probability_rank_1": float(np.mean(values == 1)), "probability_top_3": float(np.mean(values <= 3)),
            "probability_top_4": float(np.mean(values <= 4)), "rank_standard_deviation": float(np.std(values, ddof=0)),
            "top_3_membership_stability": float(np.mean(membership[symbol])),
            "rank_turnover_risk": float(np.mean(turnover)) if turnover else 0.0,
            "rank_confidence_status": "HIGH" if np.std(values) <= 1.0 and np.mean(values <= 3) >= 0.70 else "MEDIUM" if np.std(values) <= 2.0 else "LOW",
        })
    return {
        "status": "AVAILABLE", "method": "MOVING_AND_STATIONARY_BLOCK_BOOTSTRAP",
        "rows": rows, "sample_count": n, "draws": int(draws), "block_length": chosen_block,
        "seed": int(seed), "session_stratified": session_labels is not None and len(session_labels) == n,
        "regime_stratified": regime_labels is not None and len(regime_labels) == n,
    }


__all__ = ["VERSION", "chronological_rank_uncertainty"]
