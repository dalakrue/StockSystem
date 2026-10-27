from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

ALGORITHM_VERSION = "ARCEF-SV-1.0.0"

@dataclass(frozen=True)
class DecisionEvidence:
    source_field: str; source_table: str; raw_label: str; normalized_label: str
    standardized_action: float; intended_direction: str; mapping_reason: str
    published_confidence: float = 0.0; calibrated_reliability: float = 0.5
    conditional_reliability: float = 0.5; dynamic_weight: float = 0.0
    validation_status: str = "SHADOW"; mcs_status: str = "UNKNOWN"
    pbo_penalty: float = 1.0; correlation_penalty: float = 1.0
    data_quality_factor: float = 1.0; final_weight: float = 0.0
    weighted_contribution: float = 0.0; exclusion_reason: str = ""
    probabilities: dict[str, float] | None = None
    def to_dict(self) -> dict[str, Any]: return asdict(self)
