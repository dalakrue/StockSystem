from __future__ import annotations
import numpy as np


def apply_embargo(train_indices: np.ndarray, test_indices: np.ndarray, n_samples: int, embargo_candles: int) -> np.ndarray:
    """Remove observations immediately after every contiguous test block."""
    train = np.asarray(train_indices, dtype=int)
    test = np.sort(np.asarray(test_indices, dtype=int))
    if not len(test) or embargo_candles <= 0:
        return train
    blocked: set[int] = set()
    block_end = test[0]
    for previous, current in zip(test, test[1:]):
        if current != previous + 1:
            blocked.update(range(block_end + 1, min(n_samples, block_end + 1 + embargo_candles)))
        block_end = current
    blocked.update(range(block_end + 1, min(n_samples, block_end + 1 + embargo_candles)))
    return train[~np.isin(train, np.fromiter(blocked, dtype=int))]
