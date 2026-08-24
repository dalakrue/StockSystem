from __future__ import annotations
import numpy as np
from research_quant.nlp_event_memory.similarity_memory import softmax_distance_weights

def weighted_response(distances, historical_returns, temperature: float = 0.25) -> dict[str, float]:
    returns = np.asarray(historical_returns, dtype=float)
    weights = softmax_distance_weights(distances, temperature)
    mask = np.isfinite(returns) & np.isfinite(weights)
    if not mask.any(): return {"expected_response": float("nan"), "uncertainty": float("nan"), "sample_size": 0}
    weights = weights[mask]; weights /= max(weights.sum(), 1e-12); returns = returns[mask]
    mean = float(np.sum(weights * returns))
    uncertainty = float(np.sqrt(np.sum(weights * (returns - mean) ** 2)))
    return {"expected_response": mean, "uncertainty": uncertainty, "sample_size": int(mask.sum())}
