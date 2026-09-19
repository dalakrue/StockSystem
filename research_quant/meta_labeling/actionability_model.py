from __future__ import annotations
from typing import Mapping, Any
import math


def estimate_actionability(features: Mapping[str, Any]) -> float:
    """Bounded interpretable shadow score; training adapters may replace weights."""
    probability = float(features.get("calibrated_probability", 0.5) or 0.5)
    coverage = float(features.get("coverage", 0.0) or 0.0)
    conflict = float(features.get("conflict", 1.0) or 0.0)
    drift = float(features.get("drift_level", 0.0) or 0.0)
    width = float(features.get("normalized_interval_width", 1.0) or 0.0)
    spread = float(features.get("normalized_spread", 0.0) or 0.0)
    raw = 2.4 * (probability - 0.5) + 1.0 * coverage - 1.4 * conflict - 1.2 * drift - 0.6 * width - 0.5 * spread
    return float(1 / (1 + math.exp(-raw)))
