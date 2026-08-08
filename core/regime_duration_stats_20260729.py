"""Completed regime-run duration statistics measured in candles.

The current trailing run is excluded because it has not changed yet.  The
average therefore answers: how many completed candles did comparable regimes
usually last before the next regime change?
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np


def completed_regime_run_stats(values: Iterable[Any], *, current_value: Any | None = None) -> dict[str, Any]:
    """Return completed-run durations and their average.

    The final trailing run is always excluded.  When ``current_value`` is
    supplied, completed runs matching the current regime are preferred.  If no
    matching completed run exists, all completed regime runs are used so the
    table can still provide a historical baseline.
    """
    sequence = list(values)
    if not sequence:
        return {"average": None, "count": 0, "durations": [], "basis": "NO_HISTORY"}

    runs: list[tuple[Any, int]] = []
    run_value = sequence[0]
    run_length = 1
    for value in sequence[1:]:
        if value == run_value:
            run_length += 1
        else:
            runs.append((run_value, int(run_length)))
            run_value = value
            run_length = 1

    # The trailing/current run is intentionally not appended.
    completed = [(value, length) for value, length in runs if length > 0]
    if not completed:
        return {"average": None, "count": 0, "durations": [], "basis": "NO_COMPLETED_RUN"}

    matching = [length for value, length in completed if current_value is not None and value == current_value]
    if matching:
        durations = matching
        basis = "CURRENT_REGIME_MATCH"
    else:
        durations = [length for _, length in completed]
        basis = "ALL_COMPLETED_REGIMES"

    return {
        "average": float(np.mean(durations)) if durations else None,
        "count": int(len(durations)),
        "durations": [int(length) for length in durations],
        "basis": basis,
    }


__all__ = ["completed_regime_run_stats"]
