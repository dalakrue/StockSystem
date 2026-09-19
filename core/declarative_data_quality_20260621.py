"""Declarative, single-pass data-quality constraints for EURUSD H1.

The module evaluates data; it never repairs OHLC values. Critical failures are
returned to the caller, which decides whether publication is allowed.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from core.research_validation_common_20260621 import json_safe

VERSION = "declarative-data-quality-20260621-v1"


@dataclass(frozen=True)
class Constraint:
    name: str
    severity: str
    description: str
    evaluator: Callable[[Mapping[str, Any]], tuple[bool, Any, Any, int, str]]


@dataclass(frozen=True)
class ConstraintResult:
    constraint_name: str
    status: str
    severity: str
    observed_value: Any
    expected_value: Any
    failed_rows: int
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))


def _result(constraint: Constraint, evaluated: tuple[bool, Any, Any, int, str]) -> ConstraintResult:
    passed, observed, expected, failed_rows, detail = evaluated
    return ConstraintResult(
        constraint_name=constraint.name,
        status="PASS" if passed else "FAIL",
        severity=constraint.severity,
        observed_value=observed,
        expected_value=expected,
        failed_rows=int(failed_rows or 0),
        detail=str(detail or constraint.description),
    )


def evaluate_constraints(context: Mapping[str, Any], constraints: Sequence[Constraint]) -> list[ConstraintResult]:
    output: list[ConstraintResult] = []
    for constraint in constraints:
        try:
            output.append(_result(constraint, constraint.evaluator(context)))
        except Exception as exc:
            output.append(ConstraintResult(
                constraint_name=constraint.name,
                status="FAIL",
                severity=constraint.severity,
                observed_value=None,
                expected_value="constraint executes without exception",
                failed_rows=0,
                detail=f"Constraint evaluation failed safely: {exc}",
            ))
    return output


def shared_frame_aggregates(frame: pd.DataFrame, *, time_col: str, price_cols: Sequence[str]) -> dict[str, Any]:
    """Calculate reusable validation aggregates with one projected frame."""
    projected = frame[[time_col, *price_cols]].copy(deep=False)
    times = pd.to_datetime(projected[time_col], errors="coerce", utc=True)
    numeric = projected[list(price_cols)].apply(pd.to_numeric, errors="coerce")
    values = numeric.to_numpy(dtype=float, copy=False)
    finite_mask = np.isfinite(values)
    sorted_times = times.sort_values(kind="mergesort")
    gaps = sorted_times.diff().dt.total_seconds().div(3600.0)
    interior_gap_mask = gaps.gt(1.01) & gaps.lt(48.0)
    weekday_pair = sorted_times.dt.weekday.le(4) & sorted_times.shift(1).dt.weekday.le(4)
    missing_estimate = int(np.maximum(0.0, np.floor(gaps.where(interior_gap_mask & weekday_pair, 1.0) - 1.0)).sum())
    return {
        "times": times,
        "numeric": numeric,
        "finite_mask": finite_mask,
        "duplicate_count": int(times.duplicated(keep=False).sum()),
        "monotonic": bool(times.is_monotonic_increasing),
        "invalid_time_count": int(times.isna().sum()),
        "nonfinite_count": int((~finite_mask).sum()),
        "gaps_hours": gaps,
        "missing_candle_estimate": missing_estimate,
        "latest_time": times.max() if times.notna().any() else None,
        "earliest_time": times.min() if times.notna().any() else None,
    }


__all__ = ["VERSION", "Constraint", "ConstraintResult", "evaluate_constraints", "shared_frame_aggregates"]
