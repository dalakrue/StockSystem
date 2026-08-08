from __future__ import annotations
import numpy as np
import pandas as pd


def probability_of_backtest_overfitting(in_sample: pd.DataFrame, out_of_sample: pd.DataFrame) -> dict[str, float]:
    """Estimate PBO from aligned path-by-candidate performance matrices."""
    if in_sample.shape != out_of_sample.shape or in_sample.empty:
        raise ValueError("aligned non-empty in/out performance matrices required")
    logits: list[float] = []
    underperform = 0
    for path in in_sample.index:
        winner = in_sample.loc[path].astype(float).idxmax()
        ranks = out_of_sample.loc[path].astype(float).rank(method="average", pct=True)
        rank = float(ranks[winner])
        clipped = min(max(rank, 1e-9), 1 - 1e-9)
        logits.append(float(np.log(clipped / (1 - clipped))))
        underperform += rank <= 0.5
    return {
        "pbo": underperform / len(logits),
        "median_logit_rank": float(np.median(logits)),
        "path_count": float(len(logits)),
    }
