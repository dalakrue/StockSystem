"""Versioned configuration for Similar-Day Intelligence.

The weights live in this single module so the research blend is auditable and
is not duplicated across calculation or rendering code.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class SimilarDayConfig:
    engine_version: str = "similar-day-engine-20260619-v1"
    feature_version: str = "similar-day-features-20260619-v1"
    schema_version: str = "similar-day-schema-1.0.0"
    candidate_days: int = 25
    stage2_candidates: int = 8
    top_matches: int = 5
    dtw_window_ratio: float = 0.12
    minimum_prefix_hours: int = 4
    maximum_missing_ratio: float = 0.10
    cache_generations: int = 2
    cache_ttl_seconds: int = 6 * 60 * 60
    validation_origins: int = 12
    validation_min_training_days: int = 10
    tp_sl_atr_multiplier: float = 1.0
    weights: Mapping[str, float] = MappingProxyType({
        "price_path_shape": 0.30,
        "regime_compatibility": 0.20,
        "volatility_atr": 0.15,
        "adx_di_pressure": 0.15,
        "elapsed_session": 0.10,
        "data_event_quality": 0.10,
    })
    shape_weights: Mapping[str, float] = MappingProxyType({
        "euclidean": 0.45,
        "matrix_profile_style": 0.25,
        "mpdist_inspired": 0.20,
        "dtw": 0.10,
    })


CONFIG = SimilarDayConfig()


def validate_weights(config: SimilarDayConfig = CONFIG) -> None:
    if abs(sum(config.weights.values()) - 1.0) > 1e-9:
        raise ValueError("Similar-Day composite weights must sum to 1.0")
    if abs(sum(config.shape_weights.values()) - 1.0) > 1e-9:
        raise ValueError("Similar-Day shape weights must sum to 1.0")


validate_weights()

__all__ = ["SimilarDayConfig", "CONFIG", "validate_weights"]
