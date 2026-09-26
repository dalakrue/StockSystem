"""Memory-bounded operational counters using exponential-histogram concepts."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable, Mapping

from core.research_validation_common_20260621 import json_safe, stable_hash, utc_now_iso

VERSION = "sliding-monitoring-statistics-20260621-v1"
ALLOWED_COUNTERS = {
    "coverage_pass", "coverage_fail", "validation_failure", "connector_failure",
    "drift_alert", "regime_change", "wait_downgrade", "calculation_failure",
}


@dataclass
class Bucket:
    size: int
    end_index: int


class ExponentialHistogramCounter:
    """Approximate binary-event count over the last ``window_size`` updates.

    No financial price, accounting, TP/SL or promotion statistic may use this
    class. The error is bounded by the configured buckets-per-size policy.
    """
    def __init__(self, window_size: int = 4096, buckets_per_size: int = 2) -> None:
        self.window_size = max(2, int(window_size))
        self.buckets_per_size = max(2, int(buckets_per_size))
        self.index = 0
        self.buckets: list[Bucket] = []

    def update(self, event: bool) -> None:
        self.index += 1
        if bool(event):
            self.buckets.insert(0, Bucket(1, self.index))
            self._compress()
        cutoff = self.index - self.window_size
        self.buckets = [bucket for bucket in self.buckets if bucket.end_index > cutoff]

    def _compress(self) -> None:
        size = 1
        while True:
            positions = [i for i, bucket in enumerate(self.buckets) if bucket.size == size]
            if len(positions) <= self.buckets_per_size:
                if not positions and size > max((b.size for b in self.buckets), default=1):
                    break
                size *= 2
                if size > self.window_size * 2:
                    break
                continue
            oldest_two = positions[-2:]
            newer, older = oldest_two[0], oldest_two[1]
            merged = Bucket(size * 2, self.buckets[newer].end_index)
            for index in sorted([newer, older], reverse=True):
                del self.buckets[index]
            self.buckets.insert(newer, merged)

    def estimate(self) -> float:
        if not self.buckets:
            return 0.0
        total = float(sum(bucket.size for bucket in self.buckets))
        return max(0.0, total - self.buckets[-1].size / 2.0)

    def to_dict(self) -> dict[str, Any]:
        return {"window_size": self.window_size, "buckets_per_size": self.buckets_per_size, "index": self.index, "buckets": [asdict(b) for b in self.buckets], "estimate": self.estimate()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "ExponentialHistogramCounter":
        p = dict(payload or {})
        counter = cls(p.get("window_size", 4096), p.get("buckets_per_size", 2))
        counter.index = int(p.get("index") or 0)
        counter.buckets = [Bucket(int(row.get("size") or 1), int(row.get("end_index") or 0)) for row in p.get("buckets", []) if isinstance(row, Mapping)]
        return counter


def update_operational_counters(previous: Mapping[str, Any] | None, events: Mapping[str, bool], *, window_size: int = 4096) -> dict[str, Any]:
    state = dict(previous or {})
    output: dict[str, Any] = {}
    for name in sorted(ALLOWED_COUNTERS):
        counter = ExponentialHistogramCounter.from_dict(state.get(name) if isinstance(state.get(name), Mapping) else {"window_size": window_size})
        counter.update(bool(events.get(name, False)))
        output[name] = counter.to_dict()
    result = {"version": VERSION, "updated_at": utc_now_iso(), "counters": output, "financial_use_prohibited": True}
    result["state_id"] = "EHG-" + stable_hash(result)[:24]
    return json_safe(result)


__all__ = ["VERSION", "ALLOWED_COUNTERS", "ExponentialHistogramCounter", "update_operational_counters"]
