from __future__ import annotations
from dataclasses import dataclass
from itertools import combinations
from typing import Iterator
import numpy as np
import pandas as pd

from research_quant.validation.purging import purge_overlaps
from research_quant.validation.embargo import apply_embargo

@dataclass(frozen=True)
class CPCVSplit:
    split_id: int
    train_indices: np.ndarray
    test_indices: np.ndarray
    test_groups: tuple[int, ...]
    purge_count: int
    embargo_count: int


def chronological_groups(n_samples: int, n_groups: int) -> list[np.ndarray]:
    if n_groups < 2 or n_groups > n_samples:
        raise ValueError("n_groups must be between 2 and n_samples")
    return [np.asarray(group, dtype=int) for group in np.array_split(np.arange(n_samples), n_groups)]


def combinatorial_purged_splits(
    intervals: pd.DataFrame,
    *,
    n_groups: int = 6,
    test_groups_per_split: int = 2,
    embargo_candles: int = 0,
) -> Iterator[CPCVSplit]:
    n_samples = len(intervals)
    groups = chronological_groups(n_samples, n_groups)
    if not 1 <= test_groups_per_split < n_groups:
        raise ValueError("test_groups_per_split must be in [1, n_groups)")
    all_indices = np.arange(n_samples)
    for split_id, selected in enumerate(combinations(range(n_groups), test_groups_per_split)):
        test = np.sort(np.concatenate([groups[index] for index in selected]))
        initial_train = all_indices[~np.isin(all_indices, test)]
        purged_train = purge_overlaps(initial_train, test, intervals)
        embargoed_train = apply_embargo(purged_train, test, n_samples, embargo_candles)
        yield CPCVSplit(
            split_id=split_id,
            train_indices=embargoed_train,
            test_indices=test,
            test_groups=tuple(selected),
            purge_count=int(len(initial_train) - len(purged_train)),
            embargo_count=int(len(purged_train) - len(embargoed_train)),
        )
