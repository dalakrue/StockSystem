from __future__ import annotations
from dataclasses import dataclass
import numpy as np

@dataclass
class EnbPI:
    alpha: float = 0.10
    window: int = 200
    residuals: list[float] = None

    def __post_init__(self):
        if self.residuals is None:
            self.residuals = []

    def update(self, actual: float, prediction: float) -> None:
        self.residuals.append(abs(float(actual) - float(prediction)))
        self.residuals[:] = self.residuals[-self.window :]

    def quantile(self) -> float:
        if not self.residuals:
            return float("nan")
        level = min(1.0, np.ceil((len(self.residuals) + 1) * (1 - self.alpha)) / len(self.residuals))
        return float(np.quantile(self.residuals, level, method="higher"))

    def interval(self, prediction: float) -> tuple[float, float]:
        q = self.quantile()
        return (float(prediction - q), float(prediction + q)) if np.isfinite(q) else (float("nan"), float("nan"))
