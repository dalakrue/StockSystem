from __future__ import annotations
from typing import Iterable
import numpy as np
import pandas as pd


def transition_matrix(states: Iterable[str], smoothing: float = 1.0) -> pd.DataFrame:
    values = [str(value) for value in states]
    labels = sorted(set(values))
    if not labels:
        return pd.DataFrame()
    counts = pd.DataFrame(smoothing, index=labels, columns=labels, dtype=float)
    for current, following in zip(values[:-1], values[1:]):
        counts.loc[current, following] += 1.0
    return counts.div(counts.sum(axis=1), axis=0)


def horizon_transition_probability(matrix: pd.DataFrame, current_state: str, hours: int) -> dict[str, float]:
    if matrix.empty or current_state not in matrix.index:
        return {}
    powered = np.linalg.matrix_power(matrix.to_numpy(dtype=float), max(1, int(hours)))
    row = powered[list(matrix.index).index(current_state)]
    return {state: float(probability) for state, probability in zip(matrix.columns, row)}
