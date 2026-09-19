from __future__ import annotations
import numpy as np
import pandas as pd


def reliability_bins(y_true, probability, bins: int = 10) -> pd.DataFrame:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(probability, dtype=float)
    mask = np.isfinite(y) & np.isfinite(p)
    y, p = y[mask], np.clip(p[mask], 0, 1)
    rows = []
    edges = np.linspace(0, 1, bins + 1)
    for index, (low, high) in enumerate(zip(edges[:-1], edges[1:])):
        selected = (p >= low) & (p < high if high < 1 else p <= high)
        rows.append({
            "bin": index, "lower": low, "upper": high, "sample_count": int(selected.sum()),
            "mean_predicted_probability": float(p[selected].mean()) if selected.any() else np.nan,
            "actual_outcome_frequency": float(y[selected].mean()) if selected.any() else np.nan,
        })
    return pd.DataFrame(rows)
