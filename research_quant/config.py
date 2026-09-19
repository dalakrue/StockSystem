from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ResearchConfig:
    minimum_sample_size: int = 60
    calibration_bins: int = 10
    target_coverage: float = 0.90
    embargo_candles: int = 6
    pbo_limit: float = 0.25
    buy_threshold: float = 0.20
    sell_threshold: float = -0.20
    actionability_threshold: float = 0.55
    maximum_uncertainty_pct: float = 55.0
    softmax_temperature: float = 0.50
    transaction_cost_pips: float = 1.2

DEFAULT_CONFIG = ResearchConfig()
