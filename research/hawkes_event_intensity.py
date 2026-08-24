"""Bounded exponential-kernel Hawkes-style event intensity diagnostics."""
from __future__ import annotations

from typing import Any, Iterable, Mapping
import math
import numpy as np


def intensity(event_times: Iterable[Any], query_times: Iterable[Any], *, baseline: float = 0.05, excitation: float = 0.35, decay: float = 1.0, event_weights: Iterable[Any] | None = None, intensity_cap: float = 25.0) -> list[float]:
    events = np.asarray(list(event_times), dtype=float).reshape(-1)
    queries = np.asarray(list(query_times), dtype=float).reshape(-1)
    weights = np.ones(events.size, dtype=float) if event_weights is None else np.asarray(list(event_weights), dtype=float).reshape(-1)
    if weights.size != events.size:
        raise ValueError("event_weights length must match event_times")
    valid = np.isfinite(events) & np.isfinite(weights) & (weights >= 0)
    events, weights = events[valid], weights[valid]
    order = np.argsort(events)
    events, weights = events[order], weights[order]
    mu = max(0.0, float(baseline)); alpha = max(0.0, float(excitation)); beta = max(float(decay), 1e-9); cap = max(mu, float(intensity_cap))
    output = []
    for q in queries:
        if not np.isfinite(q):
            output.append(mu)
            continue
        lags = q - events
        past = lags >= 0.0
        value = mu + alpha * float(np.sum(weights[past] * np.exp(-beta * lags[past])))
        output.append(float(np.clip(value, mu, cap)))
    return output


def evaluate(events: Iterable[Mapping[str, Any]], *, query_times: Iterable[Any] | None = None, baseline: float = 0.05, excitation: float = 0.35, decay: float = 1.0, intensity_cap: float = 25.0) -> dict[str, Any]:
    rows = [dict(row) for row in events if isinstance(row, Mapping)]
    times, weights, types = [], [], []
    type_weight = {"jump": 1.0, "spread": 0.8, "news": 1.2, "decision_flip": 1.0, "prediction_miss": 1.1}
    for index, row in enumerate(rows):
        try:
            t = float(row.get("time", row.get("event_time", index)))
            if not math.isfinite(t):
                continue
        except (TypeError, ValueError):
            continue
        event_type = str(row.get("event_type", row.get("type", "event"))).lower()
        weight = row.get("weight", type_weight.get(event_type, 1.0))
        try:
            w = max(0.0, float(weight))
        except (TypeError, ValueError):
            w = 1.0
        times.append(t); weights.append(w); types.append(event_type)
    if query_times is None:
        if times:
            start, stop = min(times), max(times) + 5.0 / max(float(decay), 1e-9)
            queries = np.linspace(start, stop, min(256, max(32, len(times) * 8)))
        else:
            queries = np.asarray([], dtype=float)
    else:
        queries = np.asarray(list(query_times), dtype=float)
    values = intensity(times, queries, baseline=baseline, excitation=excitation, decay=decay, event_weights=weights, intensity_cap=intensity_cap) if queries.size else []
    branching_ratio = float(excitation) * (float(np.mean(weights)) if weights else 1.0) / max(float(decay), 1e-9)
    return {
        "status": "OK" if times else "INSUFFICIENT EVIDENCE",
        "sample_size": len(times),
        "event_type_counts": {name: types.count(name) for name in sorted(set(types))},
        "query_times": queries.tolist(),
        "intensity": values,
        "current_intensity": values[-1] if values else max(0.0, float(baseline)),
        "peak_intensity": max(values) if values else max(0.0, float(baseline)),
        "branching_ratio_proxy": branching_ratio,
        "stability_status": "BOUNDED" if branching_ratio < 1.0 else "HIGH-EXCITATION WATCH",
        "intensity_cap": float(intensity_cap),
    }


__all__ = ["intensity", "evaluate"]
