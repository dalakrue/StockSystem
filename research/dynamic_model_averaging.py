"""Bounded, settled-outcome Dynamic Model Averaging for shadow diagnostics."""
from __future__ import annotations

from typing import Any, Iterable, Mapping
import math
import numpy as np


def _bounded_simplex(raw: np.ndarray, floor: float, cap: float) -> np.ndarray:
    n = raw.size
    if n == 0:
        return raw
    floor = max(0.0, min(float(floor), 1.0 / n))
    cap = max(1.0 / n, min(float(cap), 1.0))
    if n * cap < 1.0 - 1e-12:
        raise ValueError("weight cap is infeasible")
    w = np.maximum(np.asarray(raw, dtype=float), 0.0)
    w = w / w.sum() if w.sum() > 0 else np.full(n, 1.0 / n)
    for _ in range(64):
        prev = w.copy()
        w = np.clip(w, floor, cap)
        residual = 1.0 - w.sum()
        if abs(residual) <= 1e-12:
            break
        if residual > 0:
            room = cap - w
        else:
            room = w - floor
        total = room[room > 1e-15].sum()
        if total <= 0:
            break
        w += residual * np.where(room > 1e-15, room / total, 0.0)
        if np.max(np.abs(w - prev)) <= 1e-14:
            break
    w /= w.sum()
    return w


def update_weights(previous: Mapping[str, Any], losses: Mapping[str, Any], *, forgetting_factor: float = 0.98, weight_floor: float = 0.02, weight_cap: float = 0.8, temperature: float = 1.0) -> dict[str, float]:
    names = sorted(set(previous) | set(losses))
    if not names:
        return {}
    f = min(0.9999, max(0.5, float(forgetting_factor)))
    temp = max(float(temperature), 1e-9)
    prior = np.asarray([max(float(previous.get(name, 1.0 / len(names))), 1e-300) for name in names])
    loss = np.asarray([float(losses.get(name, 0.0)) for name in names])
    loss = np.where(np.isfinite(loss), loss, np.nanmax(loss[np.isfinite(loss)]) if np.any(np.isfinite(loss)) else 0.0)
    logw = f * np.log(prior) - loss / temp
    logw -= np.max(logw)
    weights = _bounded_simplex(np.exp(logw), weight_floor, weight_cap)
    return {name: float(value) for name, value in zip(names, weights)}


def recursive_probabilities(loss_history: Iterable[Mapping[str, Any]], *, initial: Mapping[str, Any] | None = None, forgetting_factor: float = 0.98, weight_floor: float = 0.02, weight_cap: float = 0.8, temperature: float = 1.0) -> dict[str, Any]:
    rows = [dict(row) for row in loss_history if isinstance(row, Mapping)]
    names = sorted({str(k) for row in rows for k in row if not str(k).startswith("_")})
    if not names:
        return {"status": "INSUFFICIENT EVIDENCE", "sample_size": 0, "weights": {}, "path": []}
    weights = dict(initial or {name: 1.0 / len(names) for name in names})
    path = []
    for index, row in enumerate(rows):
        losses = {name: row.get(name, 0.0) for name in names}
        weights = update_weights(weights, losses, forgetting_factor=forgetting_factor, weight_floor=weight_floor, weight_cap=weight_cap, temperature=temperature)
        path.append({"step": index + 1, **weights})
        if len(path) > 500:
            del path[0]
    return {
        "status": "OK",
        "sample_size": len(rows),
        "weights": weights,
        "path": path,
        "sum_weights": float(sum(weights.values())),
        "bounds_respected": all(weight_floor - 1e-10 <= value <= weight_cap + 1e-10 for value in weights.values()),
        "production_weights_changed": False,
        "shadow_only": True,
    }


__all__ = ["update_weights", "recursive_probabilities"]
