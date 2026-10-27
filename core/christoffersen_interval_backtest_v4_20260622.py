"""Christoffersen interval coverage and independence tests for settled forecasts."""
from __future__ import annotations

from typing import Any, Mapping
import math
import re

import numpy as np
import pandas as pd

from core.quant_research_v4_contract_20260622 import chi2_sf, common_result, unavailable

METHOD_ID = "CHRISTOFFERSEN_INTERVAL_BACKTEST"
PAPER_TITLE = "Evaluating Interval Forecasts"
PAPER_AUTHORS = "Peter F. Christoffersen"
EPS = 1e-12


def _xlog(count: int, probability: float) -> float:
    if count <= 0:
        return 0.0
    return float(count * math.log(float(np.clip(probability, EPS, 1.0 - EPS))))


def _max_run(values: np.ndarray, target: int = 1) -> int:
    best = current = 0
    for value in values:
        if int(value) == target:
            current += 1; best = max(best, current)
        else:
            current = 0
    return best


def christoffersen_test(interval_hits: np.ndarray, nominal_coverage: float) -> dict[str, Any]:
    hits = np.asarray(interval_hits, dtype=float)
    hits = hits[np.isfinite(hits)]
    hits = hits[np.isin(hits, [0, 1])].astype(int)
    n = len(hits)
    if n < 30:
        return {"status": "INSUFFICIENT_EVIDENCE", "sample_count": n}
    misses = 1 - hits
    x = int(misses.sum())
    miss_nominal = float(np.clip(1.0 - nominal_coverage, EPS, 1.0 - EPS))
    miss_empirical = float(np.clip(x / n, EPS, 1.0 - EPS))
    ll_null = _xlog(n - x, 1.0 - miss_nominal) + _xlog(x, miss_nominal)
    ll_alt = _xlog(n - x, 1.0 - miss_empirical) + _xlog(x, miss_empirical)
    lr_uc = max(0.0, -2.0 * (ll_null - ll_alt))
    n00 = n01 = n10 = n11 = 0
    for a, b in zip(misses[:-1], misses[1:]):
        if a == 0 and b == 0: n00 += 1
        elif a == 0 and b == 1: n01 += 1
        elif a == 1 and b == 0: n10 += 1
        else: n11 += 1
    total = n00 + n01 + n10 + n11
    pi = float(np.clip((n01 + n11) / max(total, 1), EPS, 1.0 - EPS))
    pi01 = float(np.clip(n01 / max(n00 + n01, 1), EPS, 1.0 - EPS))
    pi11 = float(np.clip(n11 / max(n10 + n11, 1), EPS, 1.0 - EPS))
    ll_ind_null = _xlog(n00 + n10, 1.0 - pi) + _xlog(n01 + n11, pi)
    ll_ind_alt = _xlog(n00, 1.0 - pi01) + _xlog(n01, pi01) + _xlog(n10, 1.0 - pi11) + _xlog(n11, pi11)
    lr_ind = max(0.0, -2.0 * (ll_ind_null - ll_ind_alt))
    lr_cc = lr_uc + lr_ind
    p_uc = chi2_sf(lr_uc, 1); p_ind = chi2_sf(lr_ind, 1); p_cc = chi2_sf(lr_cc, 2)
    max_misses = _max_run(misses, 1)
    miss_cluster_rate = float(n11 / max(n10 + n11, 1))
    cluster_warning = bool(p_ind < 0.05 or max_misses >= 3 or miss_cluster_rate > max(0.25, miss_nominal * 2.0))
    status = "PASS" if p_cc >= 0.05 else ("MISS_CLUSTER_FAILURE" if p_ind < 0.05 else "COVERAGE_FAILURE")
    return {
        "status": "AVAILABLE",
        "sample_count": n,
        "nominal_coverage": float(nominal_coverage),
        "empirical_coverage": float(hits.mean()),
        "LR_uc": float(lr_uc), "LR_ind": float(lr_ind), "LR_cc": float(lr_cc),
        "p_uc": float(p_uc), "p_ind": float(p_ind), "p_cc": float(p_cc),
        "N00": n00, "N01": n01, "N10": n10, "N11": n11,
        "maximum_consecutive_misses": max_misses,
        "miss_cluster_rate": miss_cluster_rate,
        "miss_cluster_warning": cluster_warning,
        "conditional_coverage_status": status,
    }


def _interval_specs(settled: pd.DataFrame) -> list[tuple[float, pd.Series]]:
    lower = {str(c).lower(): c for c in settled.columns}
    specs: list[tuple[float, pd.Series]] = []
    actual_col = next((lower[n] for n in ("actual_price", "actual_close", "target_price", "settled_price", "target_close") if n in lower), None)
    # Direct interval-hit + nominal coverage fields.
    hit_col = next((lower[n] for n in ("interval_hit", "coverage_flag", "inside_interval") if n in lower), None)
    nominal_col = next((lower[n] for n in ("nominal_coverage", "interval_coverage_probability", "interval_probability", "coverage_probability") if n in lower), None)
    if hit_col is not None and nominal_col is not None:
        levels = pd.to_numeric(settled[nominal_col], errors="coerce")
        if levels.max(skipna=True) > 1:
            levels = levels / 100.0
        for level in sorted(levels.dropna().unique()):
            mask = np.isclose(levels, level)
            specs.append((float(level), pd.to_numeric(settled[hit_col], errors="coerce").where(mask)))
    # Level-specific lower/upper columns, e.g. lower_90 / upper_90.
    if actual_col is not None:
        actual = pd.to_numeric(settled[actual_col], errors="coerce")
        for name, original in lower.items():
            match = re.match(r"(?:lower|lo|interval_lower|lower_bound)_?(50|80|90|95)$", name)
            if not match:
                continue
            level_text = match.group(1)
            candidates = [f"upper_{level_text}", f"upper{level_text}", f"hi_{level_text}", f"interval_upper_{level_text}", f"upper_bound_{level_text}"]
            upper_col = next((lower[c] for c in candidates if c in lower), None)
            if upper_col is not None:
                lo = pd.to_numeric(settled[original], errors="coerce")
                hi = pd.to_numeric(settled[upper_col], errors="coerce")
                specs.append((int(level_text) / 100.0, ((actual >= lo) & (actual <= hi)).astype(float).where(actual.notna() & lo.notna() & hi.notna())))
        generic_lower = next((lower[n] for n in ("lower_bound", "interval_lower", "forecast_lower") if n in lower), None)
        generic_upper = next((lower[n] for n in ("upper_bound", "interval_upper", "forecast_upper") if n in lower), None)
        if generic_lower and generic_upper:
            nominal = float(pd.to_numeric(settled.get(nominal_col, 0.90), errors="coerce").dropna().median()) if nominal_col else 0.90
            if nominal > 1: nominal /= 100.0
            lo = pd.to_numeric(settled[generic_lower], errors="coerce"); hi = pd.to_numeric(settled[generic_upper], errors="coerce")
            specs.append((nominal, ((actual >= lo) & (actual <= hi)).astype(float).where(actual.notna() & lo.notna() & hi.notna())))
    # Deduplicate levels, preferring the first explicit supported sequence.
    dedup = {}
    for level, hits in specs:
        if level not in dedup or hits.notna().sum() > dedup[level].notna().sum():
            dedup[level] = hits
    return sorted(dedup.items())


def run_christoffersen_backtest(identity: Mapping[str, Any], settled: pd.DataFrame) -> dict[str, Any]:
    n = int(len(settled)) if isinstance(settled, pd.DataFrame) else 0
    minimum = 60
    try:
        if not isinstance(settled, pd.DataFrame) or settled.empty:
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="HORIZON_SAFE_INTERVAL_BACKTEST", sample_count=0, minimum_required_samples=minimum,
                status="INSUFFICIENT_EVIDENCE", limitations=["No settled interval forecasts were available."])
        specs = _interval_specs(settled)
        if not specs:
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="HORIZON_SAFE_INTERVAL_BACKTEST", sample_count=n, minimum_required_samples=minimum,
                status="INSUFFICIENT_EVIDENCE", limitations=["No pre-issued lower/upper interval or settled interval-hit field was found."])
        horizons = pd.to_numeric(settled.get("horizon_hours", pd.Series([1] * n)), errors="coerce").fillna(1).astype(int)
        output = {}
        support = 0
        for horizon in sorted(set(horizons)):
            hmask = horizons == horizon
            output[str(horizon)] = {}
            for level, hits in specs:
                sequence = hits.loc[hmask].dropna().astype(int).to_numpy()
                approximation = False
                if horizon > 1 and len(sequence) >= 30:
                    sequence = sequence[::horizon]
                    approximation = False
                elif horizon > 1:
                    approximation = True
                test = christoffersen_test(sequence, level)
                test["horizon_safe_non_overlapping_sequence"] = bool(horizon == 1 or not approximation)
                test["independence_test_approximate"] = bool(approximation)
                output[str(horizon)][str(int(round(level * 100)))] = test
                support += int(test.get("sample_count") or 0)
        available = [x for h in output.values() for x in h.values() if x.get("status") == "AVAILABLE"]
        status = "AVAILABLE" if available else "INSUFFICIENT_EVIDENCE"
        worst = min((x.get("p_cc", 1.0) for x in available), default=None)
        overall = "PASS" if available and all(x.get("conditional_coverage_status") == "PASS" for x in available) else ("WARNING" if available else "NOT_TESTABLE")
        return common_result(
            identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            exact_or_adaptation="NUMERICALLY_PROTECTED_CHRISTOFFERSEN_COVERAGE_TESTS",
            sample_count=n, effective_sample_count=support, minimum_required_samples=minimum,
            status=status, score=(1.0 - worst) if worst is not None else None, p_value=worst,
            confidence=(1.0 - worst) if worst is not None else None, reliability=overall,
            assumptions=["Intervals are recorded before the target settles.", "Overlapping H2-H6 sequences are subsampled to horizon-safe non-overlapping origins when support permits."],
            limitations=["The standard independence test is explicitly marked approximate when horizon-safe support is unavailable.", "Existing conformal results remain authoritative and are not replaced."],
            tests=output,
            conditional_coverage_status=overall,
            miss_cluster_warning=any(x.get("miss_cluster_warning") for x in available),
            supported_test_count=len(available),
            existing_conformal_results_replaced=False,
        )
    except Exception as exc:
        return unavailable(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            error=exc, minimum_required_samples=minimum, sample_count=n,
            limitations=["Average coverage alone is never reported as sufficient when miss clustering cannot be tested."])


__all__ = ["run_christoffersen_backtest", "christoffersen_test"]
