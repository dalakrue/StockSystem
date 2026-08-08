"""Numeric conversion helpers shared by tabs/connectors/models."""

import numpy as np


def safe_float(v, default=0.0):
    try:
        if v is None:
            return float(default)
        if isinstance(v, str):
            v = v.strip().replace(",", "")
            if v == "":
                return float(default)
        value = float(v)
        if np.isnan(value) or np.isinf(value):
            return float(default)
        return value
    except Exception:
        return float(default)


def safe_int(v, default=0):
    try:
        return int(safe_float(v, default))
    except Exception:
        return int(default)
