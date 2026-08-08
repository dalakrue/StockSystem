from __future__ import annotations
from typing import Iterable
import numpy as np
import pandas as pd


def information_intervals(starts: Iterable, ends: Iterable | None = None) -> pd.DataFrame:
    start = pd.to_datetime(pd.Series(list(starts)), errors="coerce", utc=True)
    end = pd.to_datetime(pd.Series(list(ends)), errors="coerce", utc=True) if ends is not None else start.copy()
    if len(start) != len(end):
        raise ValueError("starts and ends must have equal length")
    frame = pd.DataFrame({"start": start, "end": end}).dropna()
    if (frame["end"] < frame["start"]).any():
        raise ValueError("label end precedes label start")
    return frame


def purge_overlaps(train_indices: np.ndarray, test_indices: np.ndarray, intervals: pd.DataFrame) -> np.ndarray:
    """Remove training samples whose information intervals overlap a test label."""
    if len(test_indices) == 0:
        return np.asarray(train_indices, dtype=int)
    test = intervals.iloc[np.asarray(test_indices, dtype=int)]
    test_start, test_end = test["start"].min(), test["end"].max()
    train = intervals.iloc[np.asarray(train_indices, dtype=int)]
    keep = ~((train["start"] <= test_end) & (train["end"] >= test_start))
    return np.asarray(train_indices, dtype=int)[keep.to_numpy()]


def leakage_free(train_indices: np.ndarray, test_indices: np.ndarray, intervals: pd.DataFrame) -> bool:
    purged = purge_overlaps(train_indices, test_indices, intervals)
    return len(purged) == len(train_indices)
