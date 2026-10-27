"""Compact deterministic ADWIN-style drift state for selected monitoring streams."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Iterable
import math
import numpy as np

VERSION = "compact-adwin-v8-20260622"
MONITORED_STREAMS = ("absolute_forecast_error", "direction_correctness", "interval_miss", "reliability_error", "conflict_rate", "spread", "slippage", "api_latency", "missing_row_rate")

@dataclass
class CompactADWIN:
    delta: float = 0.002
    min_window: int = 16
    max_window: int = 512
    values: list[float] | None = None
    drift_count: int = 0
    last_drift_index: int | None = None

    def __post_init__(self) -> None:
        self.values = list(self.values or [])[-self.max_window:]

    def update(self, value: Any) -> dict[str, Any]:
        try: x = float(value)
        except Exception: return {"drift": False, "accepted": False, "reason": "non-numeric"}
        if not math.isfinite(x): return {"drift": False, "accepted": False, "reason": "non-finite"}
        self.values.append(x); self.values = self.values[-self.max_window:]
        drift = False; cut = None; magnitude = 0.0
        n = len(self.values)
        if n >= 2 * self.min_window:
            arr = np.asarray(self.values, dtype=float)
            candidates = range(self.min_window, n - self.min_window + 1, max(1, n // 16))
            for k in candidates:
                left, right = arr[:k], arr[k:]
                eps = math.sqrt(0.5 * math.log(4.0 / max(self.delta, 1e-12)) * (1.0 / len(left) + 1.0 / len(right)))
                diff = abs(float(left.mean() - right.mean()))
                scale = max(float(arr.std(ddof=1)) if n > 2 else 0.0, 1e-9)
                if diff > eps * scale:
                    drift, cut, magnitude = True, k, diff
                    break
        if drift and cut is not None:
            self.values = self.values[cut:]
            self.drift_count += 1; self.last_drift_index = n
        return {"drift": drift, "accepted": True, "window_size": len(self.values), "magnitude": magnitude, "drift_count": self.drift_count}

    def state(self) -> dict[str, Any]:
        return {**asdict(self), "version": VERSION}


def update_detectors(previous: dict[str, Any] | None, observations: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    previous = previous or {}; states: dict[str, Any] = {}; events: list[dict[str, Any]] = []
    for name in MONITORED_STREAMS:
        raw = previous.get(name) if isinstance(previous.get(name), dict) else {}
        detector = CompactADWIN(delta=float(raw.get("delta", .002)), min_window=int(raw.get("min_window", 16)), max_window=int(raw.get("max_window", 512)), values=raw.get("values"), drift_count=int(raw.get("drift_count", 0)), last_drift_index=raw.get("last_drift_index"))
        if name in observations and observations.get(name) is not None:
            result = detector.update(observations[name])
            if result.get("drift"): events.append({"stream": name, **result})
        states[name] = detector.state()
    return states, events

__all__ = ["CompactADWIN", "update_detectors", "MONITORED_STREAMS", "VERSION"]
