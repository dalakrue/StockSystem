from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Evidence:
    name: str
    directional_value: float
    quality_score: float
    calibration_quality: float = 1.0
    regime_relevance: float = 1.0

    def bounded(self) -> "Evidence":
        return Evidence(self.name, max(-1.0, min(1.0, float(self.directional_value))), max(0.0, min(1.0, float(self.quality_score))), max(0.0, min(1.0, float(self.calibration_quality))), max(0.0, min(1.0, float(self.regime_relevance))))
