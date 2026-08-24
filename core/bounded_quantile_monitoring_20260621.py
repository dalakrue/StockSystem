"""DDSketch-style mergeable relative-error summaries with recent raw evidence."""
from __future__ import annotations

from collections import deque
from typing import Any, Iterable, Mapping
import math

from core.research_validation_common_20260621 import finite, json_safe, stable_hash, utc_now_iso

VERSION = "bounded-quantile-monitoring-20260621-v1"
ALLOWED_METRICS = {
    "calculation_latency", "database_write_latency", "memory_usage",
    "absolute_forecast_error", "normalized_residual", "interval_width",
    "mfe", "mae", "drift_score", "anomaly_score",
}


class BoundedDDSketch:
    def __init__(self, relative_error: float = 0.01, recent_raw_limit: int = 256, exact_threshold: int = 1024) -> None:
        if not 0 < relative_error < 1:
            raise ValueError("relative_error must be between 0 and 1")
        self.relative_error = float(relative_error)
        self.gamma = (1.0 + self.relative_error) / (1.0 - self.relative_error)
        self.log_gamma = math.log(self.gamma)
        self.recent_raw_limit = max(16, int(recent_raw_limit))
        self.exact_threshold = max(self.recent_raw_limit, int(exact_threshold))
        self.count = 0
        self.zero_count = 0
        self.positive: dict[int, int] = {}
        self.negative: dict[int, int] = {}
        self.exact: list[float] = []
        self.recent = deque(maxlen=self.recent_raw_limit)

    def _key(self, value: float) -> int:
        return int(math.ceil(math.log(abs(value)) / self.log_gamma))

    def add(self, value: Any) -> None:
        number = finite(value)
        if number is None:
            return
        self.count += 1
        self.recent.append(float(number))
        if self.count <= self.exact_threshold:
            self.exact.append(float(number))
            return
        if self.count == self.exact_threshold + 1 and self.exact:
            prior = self.exact; self.exact = []
            for item in prior:
                self._bucket(item)
        self._bucket(float(number))

    def _bucket(self, number: float) -> None:
        if abs(number) < 1e-15:
            self.zero_count += 1
        elif number > 0:
            key = self._key(number); self.positive[key] = self.positive.get(key, 0) + 1
        else:
            key = self._key(number); self.negative[key] = self.negative.get(key, 0) + 1

    def merge(self, other: "BoundedDDSketch") -> None:
        if abs(self.relative_error - other.relative_error) > 1e-12:
            raise ValueError("Cannot merge sketches with different relative errors")
        for value in other.exact:
            self.add(value)
        if other.positive or other.negative or other.zero_count:
            if self.exact:
                prior = self.exact; self.exact = []
                for value in prior:
                    self._bucket(value)
            self.count += max(0, other.count - len(other.exact))
            self.zero_count += other.zero_count
            for key, value in other.positive.items(): self.positive[int(key)] = self.positive.get(int(key), 0) + int(value)
            for key, value in other.negative.items(): self.negative[int(key)] = self.negative.get(int(key), 0) + int(value)
            for value in other.recent: self.recent.append(float(value))

    def quantile(self, q: float) -> float | None:
        if self.count <= 0:
            return None
        quantile = max(0.0, min(1.0, float(q)))
        if self.exact:
            ordered = sorted(self.exact)
            return float(ordered[min(len(ordered) - 1, int(round(quantile * (len(ordered) - 1))))])
        target = int(math.floor(quantile * (self.count - 1))) + 1
        cumulative = 0
        for key in sorted(self.negative, reverse=True):
            cumulative += self.negative[key]
            if cumulative >= target: return -float(self.gamma ** key)
        cumulative += self.zero_count
        if cumulative >= target: return 0.0
        for key in sorted(self.positive):
            cumulative += self.positive[key]
            if cumulative >= target: return float(self.gamma ** key)
        return float(self.gamma ** max(self.positive, default=0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_error": self.relative_error, "recent_raw_limit": self.recent_raw_limit,
            "exact_threshold": self.exact_threshold, "count": self.count, "zero_count": self.zero_count,
            "positive": {str(k): v for k, v in self.positive.items()}, "negative": {str(k): v for k, v in self.negative.items()},
            "exact": self.exact, "recent": list(self.recent),
            "quantiles": {str(q): self.quantile(q) for q in (0.5, 0.9, 0.95, 0.99)},
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "BoundedDDSketch":
        p = dict(payload or {})
        sketch = cls(float(p.get("relative_error") or 0.01), int(p.get("recent_raw_limit") or 256), int(p.get("exact_threshold") or 1024))
        sketch.count = int(p.get("count") or 0); sketch.zero_count = int(p.get("zero_count") or 0)
        sketch.positive = {int(k): int(v) for k, v in (p.get("positive") or {}).items()}
        sketch.negative = {int(k): int(v) for k, v in (p.get("negative") or {}).items()}
        sketch.exact = [float(v) for v in p.get("exact", []) if finite(v) is not None]
        for value in p.get("recent", []):
            if finite(value) is not None: sketch.recent.append(float(value))
        return sketch


def update_quantile_summaries(previous: Mapping[str, Any] | None, observations: Mapping[str, Iterable[Any]], *, relative_error: float = 0.01, exact_threshold: int = 1024) -> dict[str, Any]:
    state = dict(previous or {})
    summaries: dict[str, Any] = {}
    for name, values in observations.items():
        if name not in ALLOWED_METRICS:
            continue
        sketch = BoundedDDSketch.from_dict(state.get(name)) if isinstance(state.get(name), Mapping) else BoundedDDSketch(relative_error=relative_error, exact_threshold=exact_threshold)
        for value in values or []: sketch.add(value)
        summaries[name] = sketch.to_dict()
    result = {"version": VERSION, "updated_at": utc_now_iso(), "relative_error_tolerance": relative_error, "summaries": summaries, "recent_raw_preserved": True}
    result["state_id"] = "DDS-" + stable_hash(result)[:24]
    return json_safe(result)


__all__ = ["VERSION", "ALLOWED_METRICS", "BoundedDDSketch", "update_quantile_summaries"]
