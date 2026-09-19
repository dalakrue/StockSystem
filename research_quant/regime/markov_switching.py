from __future__ import annotations
from typing import Iterable
import pandas as pd
from research_quant.regime.transition_model import transition_matrix, horizon_transition_probability
from research_quant.regime.regime_lifecycle import lifecycle_summary

INTERPRETABLE_STATES = (
    "BULL_NORMAL", "BULL_COMPRESSION", "BULL_EXPANSION", "BEAR_NORMAL",
    "BEAR_COMPRESSION", "BEAR_EXPANSION", "RANGE_LOW_VOLATILITY",
    "RANGE_HIGH_VOLATILITY", "TRANSITION",
)


def summarize_markov_regime(states: Iterable[str]) -> dict:
    values = [str(value) for value in states]
    matrix = transition_matrix(values)
    summary = lifecycle_summary(values, matrix)
    current = str(summary["current_regime"])
    for horizon in (1, 3, 6):
        probabilities = horizon_transition_probability(matrix, current, horizon)
        summary[f"{horizon}h_transition_probability"] = float(1.0 - probabilities.get(current, 0.0)) if probabilities else None
    summary["transition_matrix"] = matrix.to_dict() if isinstance(matrix, pd.DataFrame) else {}
    summary["sample_size"] = len(values)
    return summary
