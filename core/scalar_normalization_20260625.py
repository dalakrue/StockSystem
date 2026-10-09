from __future__ import annotations

from typing import Any, Iterable, Mapping
import math
import json

import numpy as np
import pandas as pd


def normalize_scalar(value: Any, default: Any = None) -> Any:
    """Return a JSON/Streamlit-safe scalar where possible.

    - 0-d or single-item arrays/Series/lists collapse to one value.
    - empty containers become ``default``.
    - multi-item arrays are converted to plain Python lists so callers can
      decide whether to display, serialize, or reject them.
    """
    if value is None:
        return default
    if isinstance(value, (np.generic,)):
        value = value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, pd.Series):
        if value.empty:
            return default
        if len(value) == 1:
            return normalize_scalar(value.iloc[0], default)
        return [normalize_scalar(v, default) for v in value.tolist()]
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return default
        flat = value.reshape(-1)
        if flat.size == 1:
            return normalize_scalar(flat[0], default)
        return [normalize_scalar(v, default) for v in flat.tolist()]
    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            return default
        if len(value) == 1:
            return normalize_scalar(value[0], default)
        return [normalize_scalar(v, default) for v in value]
    if isinstance(value, Mapping):
        return {str(k): normalize_scalar(v, default) for k, v in value.items()}
    if isinstance(value, float):
        return value if math.isfinite(value) else default
    return value


def scalar_series(value: Any, index: Iterable[Any], default: Any = np.nan) -> pd.Series:
    idx = pd.Index(index)
    normalized = normalize_scalar(value, default)
    if isinstance(normalized, list):
        if len(normalized) == len(idx):
            return pd.Series(normalized, index=idx)
        if len(normalized) == 0:
            return pd.Series([default] * len(idx), index=idx)
        if len(normalized) == 1:
            return pd.Series([normalized[0]] * len(idx), index=idx)
        trimmed = normalized[: len(idx)] + [default] * max(0, len(idx) - len(normalized))
        return pd.Series(trimmed[: len(idx)], index=idx)
    return pd.Series([normalized] * len(idx), index=idx)


def metric_text(value: Any, default: str = "—") -> str:
    normalized = normalize_scalar(value, default)
    if normalized in (None, ""):
        return default
    if isinstance(normalized, list):
        if not normalized:
            return default
        return json.dumps(normalized, ensure_ascii=False)
    return str(normalized)


__all__ = ["normalize_scalar", "scalar_series", "metric_text"]
