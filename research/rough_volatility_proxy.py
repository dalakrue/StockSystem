"""Multi-scale realized-volatility roughness proxy with evidence rejection."""
from __future__ import annotations

from typing import Any, Iterable, Sequence
import numpy as np


def evaluate(returns: Iterable[Any], *, scales: Sequence[int] = (1, 2, 4, 8, 16), min_points_per_scale: int = 8, min_scales: int = 3) -> dict[str, Any]:
    r = np.asarray(list(returns), dtype=float).reshape(-1)
    r = r[np.isfinite(r)]
    rows = []
    for raw_scale in sorted({int(s) for s in scales if int(s) > 0}):
        scale = int(raw_scale)
        blocks = r.size // scale
        if blocks < int(min_points_per_scale):
            continue
        values = r[-blocks * scale:].reshape(blocks, scale).sum(axis=1)
        rv = float(np.mean(values ** 2))
        if rv > 0 and np.isfinite(rv):
            rows.append((scale, rv, blocks))
    if len(rows) < int(min_scales):
        return {"status": "INSUFFICIENT EVIDENCE", "sample_size": int(r.size), "usable_scales": len(rows), "required_scales": int(min_scales), "scales": rows}
    x = np.log(np.asarray([row[0] for row in rows], dtype=float))
    y = np.log(np.asarray([row[1] for row in rows], dtype=float))
    design = np.column_stack([np.ones_like(x), x])
    coeff, *_ = np.linalg.lstsq(design, y, rcond=None)
    fitted = design @ coeff
    residual = y - fitted
    dof = max(1, len(rows) - 2)
    sigma2 = float(np.sum(residual ** 2) / dof)
    covariance = sigma2 * np.linalg.pinv(design.T @ design)
    slope = float(coeff[1])
    slope_se = float(np.sqrt(max(covariance[1, 1], 0.0)))
    h = float(np.clip(slope / 2.0, 0.01, 0.99))
    h_se = slope_se / 2.0
    return {
        "status": "ROUGH" if h < 0.5 else "SMOOTH",
        "sample_size": int(r.size),
        "usable_scales": len(rows),
        "scales": [{"scale": s, "realized_variance": rv, "blocks": b} for s, rv, b in rows],
        "roughness_h": h,
        "uncertainty_se": h_se,
        "confidence_interval_95": [max(0.0, h - 1.96 * h_se), min(1.0, h + 1.96 * h_se)],
        "log_log_slope": slope,
        "r_squared": float(1.0 - np.sum(residual ** 2) / max(np.sum((y - np.mean(y)) ** 2), 1e-15)),
    }


__all__ = ["evaluate"]
