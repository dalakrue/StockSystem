from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np

@dataclass
class ADWINMonitor:
    delta: float = 0.002
    min_window: int = 20
    max_window: int = 1000
    values: list[float] = None

    def __post_init__(self):
        if self.values is None:
            self.values = []

    def update(self, value: float) -> dict:
        self.values.append(float(value))
        self.values[:] = self.values[-self.max_window:]
        result = {"drift": False, "old_mean": None, "new_mean": None, "magnitude": 0.0, "window_size_before": len(self.values), "window_size_after": len(self.values)}
        if len(self.values) < 2 * self.min_window:
            return result
        array = np.asarray(self.values, dtype=float)
        best = None
        variance = float(np.var(array))
        for split in range(self.min_window, len(array) - self.min_window + 1):
            old, new = array[:split], array[split:]
            n_eff = 1 / (1 / len(old) + 1 / len(new))
            epsilon = math.sqrt(2 * variance * math.log(2 / self.delta) / max(n_eff, 1)) + 2 * math.log(2 / self.delta) / (3 * max(n_eff, 1))
            magnitude = abs(float(old.mean() - new.mean()))
            if magnitude > epsilon and (best is None or magnitude > best[0]):
                best = (magnitude, split, float(old.mean()), float(new.mean()))
        if best is not None:
            magnitude, split, old_mean, new_mean = best
            before = len(self.values)
            self.values[:] = self.values[split:]
            result.update({"drift": True, "old_mean": old_mean, "new_mean": new_mean, "magnitude": magnitude, "window_size_before": before, "window_size_after": len(self.values)})
        return result
