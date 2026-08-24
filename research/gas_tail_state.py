"""Bounded Student-t score-driven residual location, scale and tail state."""
from __future__ import annotations

from typing import Any, Iterable
import math
import numpy as np


def evaluate(residuals: Iterable[Any], *, omega_scale: float = -0.02, alpha_scale: float = 0.08, beta_scale: float = 0.96, alpha_location: float = 0.08, beta_location: float = 0.92, initial_nu: float = 8.0, min_scale: float = 1e-6, max_scale: float = 1e6, max_abs_location: float = 1e6, min_nu: float = 2.1, max_nu: float = 60.0) -> dict[str, Any]:
    values = np.asarray(list(residuals), dtype=float).reshape(-1)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"status": "INSUFFICIENT EVIDENCE", "sample_size": 0, "path": []}
    nu = float(np.clip(initial_nu, min_nu, max_nu))
    location_bound = max(float(abs(max_abs_location)), min_scale)
    location = float(np.clip(np.median(values[: min(values.size, 20)]), -location_bound, location_bound))
    robust = float(np.median(np.abs(values[: min(values.size, 50)] - location)) * 1.4826)
    scale = float(np.clip(robust if robust > 0 else np.std(values[: min(values.size, 50)]) or 1.0, min_scale, max_scale))
    log_scale = math.log(scale)
    path = []
    clipping_count = 0
    for index, residual in enumerate(values):
        scale = float(np.clip(math.exp(float(np.clip(log_scale, math.log(min_scale), math.log(max_scale)))), min_scale, max_scale))
        z = float(np.clip((residual - location) / scale, -1e6, 1e6))
        denominator = max(nu + z * z, 1e-12)
        location_score = (nu + 1.0) * z / denominator
        scale_score = -1.0 + (nu + 1.0) * z * z / denominator
        tail_score = float(np.clip((z * z - 1.0) / (nu + z * z), -1.0, 1.0))
        new_location = beta_location * location + (1.0 - beta_location) * residual + alpha_location * scale * location_score
        new_log_scale = omega_scale + beta_scale * log_scale + alpha_scale * scale_score
        new_nu = nu - 0.05 * tail_score
        bounded_location = float(np.clip(new_location, -location_bound, location_bound))
        bounded_log_scale = float(np.clip(new_log_scale, math.log(min_scale), math.log(max_scale)))
        bounded_nu = float(np.clip(new_nu, min_nu, max_nu))
        clipping_count += int(bounded_location != new_location) + int(bounded_log_scale != new_log_scale) + int(bounded_nu != new_nu)
        location, log_scale, nu = bounded_location, bounded_log_scale, bounded_nu
        state_scale = float(math.exp(log_scale))
        if not all(math.isfinite(v) for v in (location, state_scale, nu)):
            raise FloatingPointError("non-finite GAS state")
        path.append({"step": index + 1, "location": location, "scale": state_scale, "nu": nu, "standardized_residual": z})
        if len(path) > 500:
            del path[0]
    return {
        "status": "OK",
        "sample_size": int(values.size),
        "location": location,
        "scale": float(math.exp(log_scale)),
        "nu": nu,
        "tail_state": "HEAVY" if nu < 6.0 else "MODERATE" if nu < 15.0 else "LIGHT",
        "finite": True,
        "clipping_count": clipping_count,
        "location_bound": location_bound,
        "path": path,
    }


__all__ = ["evaluate"]
