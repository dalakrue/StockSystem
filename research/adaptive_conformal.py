"""Adaptive conformal diagnostics from stored interval evidence."""
from __future__ import annotations
from typing import Any, Mapping
from research._utils import clamp, deep_find, number


def evaluate(intervals: Mapping[str, Any], horizon: int, *, sample_size: int, target_coverage: float = 90.0) -> dict[str, Any]:
    scope = intervals.get(str(horizon)) or intervals.get(f"{horizon}h") or intervals
    scope = scope if isinstance(scope, Mapping) else {}
    actual = number(deep_find(scope, ("actual_coverage", "coverage", "coverage_pct", "empirical_coverage")), None)
    lower = number(deep_find(scope, ("lower", "lower_band", "lower_bound")), None)
    upper = number(deep_find(scope, ("upper", "upper_band", "upper_bound")), None)
    width = (upper - lower) if lower is not None and upper is not None else number(deep_find(scope, ("interval_width", "width")), None)
    violations = int(number(deep_find(scope, ("consecutive_violations", "violations")), 0) or 0)
    if actual is None or sample_size < 10:
        return {
            "target_coverage": target_coverage, "actual_coverage": actual, "interval_width": width,
            "coverage_debt": None, "consecutive_violations": violations,
            "required_widening": None, "required_narrowing": None, "status": "INSUFFICIENT EVIDENCE",
        }
    actual = clamp(actual)
    debt = max(0.0, target_coverage - actual)
    surplus = max(0.0, actual - target_coverage)
    status = "UNDERCOVERED" if debt > 3.0 else "OVERCOVERED" if surplus > 5.0 else "CALIBRATED"
    return {
        "target_coverage": target_coverage, "actual_coverage": round(actual, 3), "interval_width": width,
        "coverage_debt": round(debt, 3), "consecutive_violations": violations,
        "required_widening": round(debt / max(target_coverage, 1.0), 4) if debt else 0.0,
        "required_narrowing": round(surplus / max(target_coverage, 1.0), 4) if surplus else 0.0,
        "status": status,
    }
