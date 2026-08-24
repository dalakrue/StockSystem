from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

class ResearchStatus(str, Enum):
    VALID = "VALID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    STALE = "STALE"
    DRIFT_DETECTED = "DRIFT_DETECTED"
    CALIBRATION_FAILED = "CALIBRATION_FAILED"
    COVERAGE_FAILED = "COVERAGE_FAILED"
    LEAKAGE_RISK = "LEAKAGE_RISK"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    RESEARCH_ONLY = "RESEARCH_ONLY"

class PromotionStatus(str, Enum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    SHADOW_APPROVED = "SHADOW_APPROVED"
    PRODUCTION_CANDIDATE = "PRODUCTION_CANDIDATE"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"

@dataclass(frozen=True)
class ResearchEnvelope:
    run_id: str
    generation_id: str
    symbol: str
    timeframe: str
    completed_broker_candle: datetime
    model_name: str
    model_version: str
    research_mode: bool
    source_snapshot_hash: str
    input_feature_hash: str
    created_at_broker_time: datetime
    status: str
    reason: str
    sample_size: int
    quality_flags: tuple[str, ...] = field(default_factory=tuple)
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        # ``MappingProxyType`` is intentionally immutable but cannot be deep-
        # copied by dataclasses.asdict. Build the publication explicitly.
        return {
            "run_id": self.run_id,
            "generation_id": self.generation_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "completed_broker_candle": self.completed_broker_candle,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "research_mode": self.research_mode,
            "source_snapshot_hash": self.source_snapshot_hash,
            "input_feature_hash": self.input_feature_hash,
            "created_at_broker_time": self.created_at_broker_time,
            "status": self.status,
            "reason": self.reason,
            "sample_size": self.sample_size,
            "quality_flags": list(self.quality_flags),
            "payload": dict(self.payload),
        }


def immutable_payload(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))
