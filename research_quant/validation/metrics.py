from __future__ import annotations
from typing import Iterable
import numpy as np


def path_stability(scores: Iterable[float]) -> float:
    values = np.asarray(list(scores), dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return 0.0
    scale = max(abs(float(np.mean(values))), 1e-9)
    return float(max(0.0, 1.0 - np.std(values) / scale))


def score_degradation(in_sample: float, out_of_sample: float) -> float:
    return float(in_sample - out_of_sample)
