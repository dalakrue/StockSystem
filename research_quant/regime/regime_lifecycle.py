from __future__ import annotations
from typing import Iterable
import pandas as pd


def regime_age(states: Iterable[str]) -> int:
    values = list(states)
    if not values:
        return 0
    current = values[-1]
    age = 0
    for value in reversed(values):
        if value != current:
            break
        age += 1
    return age


def expected_duration(self_transition_probability: float) -> float:
    p = min(max(float(self_transition_probability), 0.0), 0.999999)
    return float(1.0 / (1.0 - p))


def lifecycle_summary(states: Iterable[str], matrix: pd.DataFrame) -> dict[str, float | str | int]:
    values = list(states)
    if not values:
        return {"current_regime": "UNAVAILABLE", "regime_age": 0, "expected_duration": 0.0, "estimated_remaining_duration": 0.0}
    current = str(values[-1])
    age = regime_age(values)
    p_stay = float(matrix.loc[current, current]) if not matrix.empty and current in matrix.index else 0.0
    duration = expected_duration(p_stay)
    return {"current_regime": current, "regime_age": age, "expected_duration": duration, "estimated_remaining_duration": max(0.0, duration - age)}
