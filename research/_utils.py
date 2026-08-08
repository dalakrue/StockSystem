from __future__ import annotations

from typing import Any, Iterable, Mapping
import math


def number(value: Any, default: float | None = 0.0) -> float | None:
    try:
        output = float(value)
        return output if math.isfinite(output) else default
    except Exception:
        return default


def clamp(value: Any, low: float = 0.0, high: float = 100.0, default: float = 0.0) -> float:
    parsed = number(value, default)
    return max(low, min(high, float(parsed if parsed is not None else default)))


def deep_find(mapping: Mapping[str, Any], aliases: Iterable[str]) -> Any:
    normalized = {str(k).lower().replace(" ", "_").replace("/", "_").replace("-", "_"): v for k, v in mapping.items()}
    for alias in aliases:
        key = str(alias).lower().replace(" ", "_").replace("/", "_").replace("-", "_")
        if key in normalized and normalized[key] not in (None, ""):
            return normalized[key]
    for value in mapping.values():
        if isinstance(value, Mapping):
            found = deep_find(value, aliases)
            if found not in (None, ""):
                return found
    return None


def prediction_for_horizon(predictions: Mapping[str, Any], horizon: int) -> float | None:
    aliases = (
        f"predicted_{horizon}h_price", f"prediction_{horizon}h", f"target_{horizon}h",
        f"h{horizon}_price", f"{horizon}h_price", f"price_{horizon}h",
    )
    found = deep_find(predictions, aliases)
    parsed = number(found, None)
    if parsed is not None:
        return float(parsed)
    for key in ("path", "main_path", "predicted_path", "projection", "future"):
        value = predictions.get(key)
        if isinstance(value, list) and value:
            index = min(max(horizon - 1, 0), len(value) - 1)
            point = value[index]
            if isinstance(point, Mapping):
                parsed = number(deep_find(point, ("close", "price", "predicted_price", "target")), None)
            else:
                parsed = number(point, None)
            if parsed is not None:
                return float(parsed)
    return None
