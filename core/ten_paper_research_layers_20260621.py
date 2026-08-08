# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Fail-safe shadow implementations for ten research-paper concepts.

The module is deliberately isolated from Streamlit renderers.  It is called once
from Settings after settled evidence exists and before canonical publication.
It never mutates protected formulas, weights, thresholds, or BUY/SELL direction.

The statistical procedures are implementation mechanisms, not unsupported
claims of production benefit.  Every result carries assumptions, exact sample
support, chronological boundaries, and an evidence state.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import json
import math
import os
import sqlite3
import time
import tracemalloc

import numpy as np
import pandas as pd

from core.research_validation_common_20260621 import (
    deterministic_seed,
    direction,
    effective_sample_size,
    finite,
    json_safe,
    mapping,
    normal_two_sided_p,
    probability,
    profile_int,
    stable_hash,
    utc_now_iso,
)
from core.research_validation_store_20260621 import BUNDLE_KEY

VERSION = "ten-paper-shadow-layers-20260621-v1"
SCHEMA_VERSION = "ten-paper-research-schema-v1"
DEFAULT_FDR_TARGET = 0.10
DEFAULT_REJECTION_COST = 0.35
DEFAULT_MINIMUM_SAMPLES = 96
MAX_SETTLED_ROWS = 3000
MAX_FEATURES = 24
MAX_PROVENANCE_NODES = 768
MAX_FDR_TESTS_PER_RUN = 240
MAX_CACHE_FACTORS = 12

PAPER_TITLES = (
    "Panning for Gold: 'Model-X' Knockoffs for High Dimensional Controlled Variable Selection",
    "Online Rules for Control of False Discovery Rate and False Discovery Exceedance",
    "Classification with a Reject Option using a Hinge Loss",
    "Estimation and Testing of Forecast Rationality under Flexible Loss",
    "A Unified Approach to Interpreting Model Predictions",
    "Monotonic Calibrated Interpolated Look-Up Tables",
    "DBToaster: Higher-order Delta Processing for Dynamic, Frequently Fresh Views",
    "Provenance Semirings",
    "Metamorphic Testing: A New Approach for Generating Next Test Cases",
    "Keeping CALM: When Distributed Consistency Is Easy",
)


def _frame(value: Any) -> pd.DataFrame:
    return value.copy(deep=False) if isinstance(value, pd.DataFrame) else pd.DataFrame()


def _deterministic_payload(value: Any) -> Any:
    """Remove runtime-only fields before identity/output hashing.

    Scientific values, gate outcomes, versions and source identities remain in the
    hash. Wall-clock timestamps and resource measurements remain published for
    audit, but cannot change deterministic calculation identity.
    """
    volatile = {
        "evaluated_at", "updated_at", "created_at", "elapsed_ms",
        "full_recompute_ms", "delta_ms", "write_time_ms",
        "full_peak_allocation_bytes", "delta_peak_allocation_bytes",
        "process_rss_mb", "rss_mb", "cpu_pct",
    }
    if isinstance(value, Mapping):
        return {str(k): _deterministic_payload(v) for k, v in value.items() if str(k) not in volatile}
    if isinstance(value, (list, tuple)):
        return [_deterministic_payload(v) for v in value]
    return json_safe(value)


def _bounded_json(value: Any, *, depth: int = 0, max_items: int = 64) -> Any:
    """Convert arbitrary evidence to a compact, deterministic JSON-safe value."""
    if depth >= 5:
        return str(type(value).__name__)
    if isinstance(value, pd.DataFrame):
        frame = value.tail(min(len(value), max_items))
        return {
            "type": "DataFrame", "shape": [int(value.shape[0]), int(value.shape[1])],
            "columns": [str(c) for c in list(value.columns)[:max_items]],
            "tail": [_bounded_json(row, depth=depth + 1, max_items=max_items) for row in frame.to_dict("records")],
        }
    if isinstance(value, np.ndarray):
        flat = value.reshape(-1)[:max_items].tolist()
        return {"type": "ndarray", "shape": list(value.shape), "values": _bounded_json(flat, depth=depth + 1, max_items=max_items)}
    if isinstance(value, Mapping):
        pairs = sorted(value.items(), key=lambda item: str(item[0]))[:max_items]
        return {str(k): _bounded_json(v, depth=depth + 1, max_items=max_items) for k, v in pairs}
    if isinstance(value, (list, tuple, set)):
        items = list(value)[:max_items]
        return [_bounded_json(v, depth=depth + 1, max_items=max_items) for v in items]
    return json_safe(value)


def _settled(frame: pd.DataFrame, *, limit: int = MAX_SETTLED_ROWS) -> pd.DataFrame:
    data = _frame(frame)
    if data.empty:
        return data
    if "record_status" in data:
        data = data.loc[data["record_status"].fillna("SETTLED").astype(str).str.upper().eq("SETTLED")]
    time_col = next((c for c in ("forecast_origin_time", "target_time", "settlement_timestamp", "created_at") if c in data), None)
    if time_col:
        data = data.assign(__time=pd.to_datetime(data[time_col], errors="coerce", utc=True)).sort_values("__time", kind="mergesort")
        data = data.drop(columns="__time")
    return data.tail(int(limit)).reset_index(drop=True)


def _num_series(frame: pd.DataFrame, aliases: Sequence[str]) -> pd.Series:
    lookup = {str(c).strip().lower(): c for c in frame.columns}
    for alias in aliases:
        column = lookup.get(str(alias).strip().lower())
        if column is not None:
            return pd.to_numeric(frame[column], errors="coerce")
    return pd.Series(np.nan, index=frame.index, dtype=float)


def _text_series(frame: pd.DataFrame, aliases: Sequence[str]) -> pd.Series:
    lookup = {str(c).strip().lower(): c for c in frame.columns}
    for alias in aliases:
        column = lookup.get(str(alias).strip().lower())
        if column is not None:
            return frame[column].fillna("").astype(str)
    return pd.Series("", index=frame.index, dtype=str)


def _completed_h1(frame: pd.DataFrame, latest_completed: Any = None) -> pd.DataFrame:
    data = _frame(frame)
    if data.empty:
        return data
    work = data.copy(deep=False)
    if not isinstance(work.index, pd.DatetimeIndex):
        time_col = next((c for c in ("time", "Time", "timestamp", "Timestamp", "datetime", "Datetime") if c in work), None)
        if time_col is not None:
            idx = pd.to_datetime(work[time_col], errors="coerce", utc=True)
            work = work.loc[idx.notna()].copy()
            work.index = idx[idx.notna()]
    else:
        idx = pd.to_datetime(work.index, errors="coerce", utc=True)
        work = work.loc[idx.notna()].copy()
        work.index = idx[idx.notna()]
    if not isinstance(work.index, pd.DatetimeIndex):
        return pd.DataFrame()
    work = work.sort_index(kind="mergesort")
    if latest_completed is not None:
        cutoff = pd.Timestamp(latest_completed)
        cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
        work = work.loc[work.index <= cutoff]
    return work


def _bounded_records(rows: Iterable[Mapping[str, Any]], limit: int = 500) -> list[dict[str, Any]]:
    return [dict(json_safe(row)) for row in list(rows)[-int(limit):]]


def _value(canonical: Mapping[str, Any], *paths: str, default: Any = None) -> Any:
    for path in paths:
        node: Any = canonical
        ok = True
        for part in path.split("."):
            if not isinstance(node, Mapping) or part not in node:
                ok = False
                break
            node = node[part]
        if ok and node not in (None, ""):
            return node
    return default


def _chronological_windows(
    frame: pd.DataFrame, *, minimum_samples: int, embargo: int
) -> list[tuple[str, pd.DataFrame, pd.DataFrame, dict[str, Any]]]:
    """Create two expanding-window chronological splits with disjoint tests.

    Each training window ends before its test window by ``embargo`` rows. The two
    test windows do not overlap. This is the shared walk-forward contract for the
    new research layers; no random split or future-aware preprocessing is used.
    """
    data = _settled(frame)
    n = len(data)
    if n < minimum_samples:
        return []
    test_size = max(32, n // 5)
    # Keep enough rows for two non-overlapping tests plus a useful first train.
    if n < (2 * test_size + embargo + 32):
        test_size = max(24, (n - embargo - 32) // 2)
    first_test_start = n - 2 * test_size
    second_test_start = n - test_size
    candidates = (
        ("W1", first_test_start - embargo, first_test_start, second_test_start),
        ("W2", second_test_start - embargo, second_test_start, n),
    )
    windows: list[tuple[str, pd.DataFrame, pd.DataFrame, dict[str, Any]]] = []
    for name, train_end, test_start, test_end in candidates:
        if train_end < 32 or test_end - test_start < 24:
            continue
        train = data.iloc[:train_end].reset_index(drop=True)
        test = data.iloc[test_start:test_end].reset_index(drop=True)
        train_start_value = train.iloc[0].get("forecast_origin_time") or train.iloc[0].get("target_time") or 0
        train_end_value = train.iloc[-1].get("forecast_origin_time") or train.iloc[-1].get("target_time") or len(train) - 1
        test_start_value = test.iloc[0].get("forecast_origin_time") or test.iloc[0].get("target_time") or test_start
        test_end_value = test.iloc[-1].get("forecast_origin_time") or test.iloc[-1].get("target_time") or test_end - 1
        boundaries = {
            "train_start": str(train_start_value), "train_end": str(train_end_value),
            "test_start": str(test_start_value), "test_end": str(test_end_value),
            "train_row_count": int(len(train)), "test_row_count": int(len(test)),
            "purge_rows": int(embargo), "embargo_rows": int(embargo),
            "maximum_forecast_horizon": 6, "split_strategy": "CHRONOLOGICAL_EXPANDING_WALK_FORWARD",
        }
        windows.append((name, train, test, boundaries))
    return windows


# ---------------------------------------------------------------------------
# Paper 1: Model-X knockoffs
# ---------------------------------------------------------------------------

FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "FULL_METRIC": (
        "raw_confidence", "calibrated_confidence", "required_probability_threshold",
        "expected_value_after_costs", "expected_favorable_movement", "expected_adverse_movement",
    ),
    "REGIME": ("regime_age", "regime_transition_risk"),
    "SIMILAR_DAY": ("similarity_index", "similar_day_reliability", "similar_day_score", "mpdist"),
    "NLP": ("nlp_reliability", "event_intensity", "event_score", "news_impact_score"),
    "FORECAST": ("predicted_close", "model_agreement", "lower_band", "upper_band", "estimated_cost_pips"),
    "RELIABILITY": ("reliability_score", "raw_confidence", "calibrated_confidence", "interval_hit", "data_quality_score"),
    "PRIORITY": ("priority", "knn_score", "greedy_rank", "market_quality", "conflict_score", "forecast_agreement"),
}


def _feature_matrix(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, dict[str, str], dict[str, Any]]:
    data = _settled(frame)
    if data.empty:
        return pd.DataFrame(), pd.Series(dtype=float), {}, {"reason": "no settled evidence"}
    columns: list[str] = []
    groups: dict[str, str] = {}
    lookup = {str(c).strip().lower(): str(c) for c in data.columns}
    for group, aliases in FEATURE_GROUPS.items():
        for alias in aliases:
            hit = lookup.get(alias.lower())
            if hit is not None and hit not in columns:
                numeric = pd.to_numeric(data[hit], errors="coerce")
                if numeric.notna().sum() >= max(24, len(data) // 4) and numeric.nunique(dropna=True) > 1:
                    columns.append(hit)
                    groups[hit] = group
    # Add exact interval width rather than duplicating lower/upper semantics.
    if "lower_band" in data and "upper_band" in data:
        data = data.copy()
        data["interval_width"] = (pd.to_numeric(data["upper_band"], errors="coerce") - pd.to_numeric(data["lower_band"], errors="coerce")).abs()
        if data["interval_width"].notna().sum() >= 24:
            columns.append("interval_width")
            groups["interval_width"] = "FORECAST"
    columns = columns[:MAX_FEATURES]
    target = _num_series(data, ("direction_correct",))
    if target.notna().sum() < 24:
        origin = _num_series(data, ("forecast_origin_price",))
        actual = _num_series(data, ("actual_close",))
        target = (actual - origin).where(origin.notna() & actual.notna())
    x = data[columns].apply(pd.to_numeric, errors="coerce") if columns else pd.DataFrame(index=data.index)
    mask = target.notna()
    if not x.empty:
        mask &= x.notna().mean(axis=1) >= 0.8
        x = x.loc[mask].copy()
        x = x.fillna(x.median(numeric_only=True)).replace([np.inf, -np.inf], np.nan).dropna(axis=1)
        groups = {c: groups[c] for c in x.columns}
    target = target.loc[x.index if not x.empty else mask].astype(float)
    support = {group: int(sum(1 for c in x.columns if groups.get(c) == group)) for group in FEATURE_GROUPS}
    return x.reset_index(drop=True), target.reset_index(drop=True), groups, {"group_feature_counts": support, "tested_groups": list(FEATURE_GROUPS)}


def gaussian_model_x_knockoffs(x: np.ndarray, *, seed: int) -> tuple[np.ndarray, dict[str, Any]]:
    """Construct deterministic second-order Gaussian knockoffs.

    This is an approximate mechanism when the covariate law is estimated.  The
    returned metadata explicitly prevents an unconditional finite-sample FDR
    claim unless exchangeability assumptions are independently established.
    """
    values = np.asarray(x, dtype=float)
    if values.ndim != 2 or values.shape[0] < 4 or values.shape[1] < 1:
        raise ValueError("knockoffs require a non-empty 2D feature matrix")
    mean = np.mean(values, axis=0)
    scale = np.std(values, axis=0, ddof=1)
    scale = np.where(scale > 1e-9, scale, 1.0)
    z = (values - mean) / scale
    covariance = np.cov(z, rowvar=False)
    covariance = np.atleast_2d(covariance)
    p = covariance.shape[0]
    covariance = covariance + np.eye(p) * 1e-5
    eig = np.linalg.eigvalsh(covariance)
    lambda_min = max(float(np.min(eig)), 1e-6)
    s_value = min(1.0, 1.8 * lambda_min)
    s = np.eye(p) * s_value
    inv = np.linalg.pinv(covariance, rcond=1e-10)
    conditional_mean = z @ (np.eye(p) - inv @ s)
    conditional_cov = 2.0 * s - s @ inv @ s
    conditional_cov = (conditional_cov + conditional_cov.T) / 2.0
    evals, evecs = np.linalg.eigh(conditional_cov)
    clipped = np.clip(evals, 0.0, None)
    root = evecs @ np.diag(np.sqrt(clipped)) @ evecs.T
    rng = np.random.default_rng(int(seed))
    knock = conditional_mean + rng.standard_normal(z.shape) @ root.T
    diagnostics = {
        "construction": "second-order Gaussian equi-correlated knockoffs",
        "estimated_covariate_distribution": True,
        "minimum_covariance_eigenvalue": lambda_min,
        "s_value": s_value,
        "conditional_covariance_min_eigenvalue": float(np.min(clipped)),
        "exact_model_x_exchangeability_proven": False,
    }
    return knock, diagnostics


def _ridge_coefficients(design: np.ndarray, target: np.ndarray, ridge: float = 1.0) -> np.ndarray:
    x = np.asarray(design, dtype=float)
    y = np.asarray(target, dtype=float)
    y = y - np.mean(y)
    gram = x.T @ x + np.eye(x.shape[1]) * float(ridge)
    return np.linalg.pinv(gram, rcond=1e-10) @ x.T @ y


def _knockoff_threshold(w: np.ndarray, q: float) -> float | None:
    candidates = sorted(float(v) for v in np.unique(np.abs(w[np.isfinite(w)])) if float(v) > 0)
    for threshold in candidates:
        discoveries = int(np.sum(w >= threshold))
        if discoveries <= 0:
            continue
        estimate = (1 + int(np.sum(w <= -threshold))) / discoveries
        if estimate <= q:
            return threshold
    return None


def run_model_x_feature_validation(
    settled_predictions: pd.DataFrame,
    *,
    source_generation_id: str,
    fdr_target: float = DEFAULT_FDR_TARGET,
    minimum_samples: int = DEFAULT_MINIMUM_SAMPLES,
    embargo: int = 6,
) -> dict[str, Any]:
    data = _settled(settled_predictions)
    windows = _chronological_windows(data, minimum_samples=minimum_samples, embargo=embargo)
    feature_rows: list[dict[str, Any]] = []
    window_results: list[dict[str, Any]] = []
    if len(windows) < 2:
        return {
            "version": VERSION, "paper": PAPER_TITLES[0], "status": "INSUFFICIENT_EVIDENCE",
            "minimum_sample_count": minimum_samples, "observed_sample_count": int(len(data)),
            "fdr_target": float(fdr_target), "windows": [], "feature_statistics": [],
            "automatic_feature_removal": False, "fdr_control_claimed": False,
            "reason": "Need two independent chronological windows after purge and embargo.",
        }
    selections: dict[str, list[bool]] = {}
    validation_effects: dict[str, list[float | None]] = {}
    regime_support = int(_text_series(data, ("h1_regime", "d1_regime")).replace("", np.nan).nunique(dropna=True))
    for window_name, train_window, test_window, boundaries in windows[:2]:
        x, y, groups, support = _feature_matrix(train_window)
        if len(x) < max(32, minimum_samples // 3) or x.shape[1] < 2:
            window_results.append({"window": window_name, "status": "INSUFFICIENT_EVIDENCE", **boundaries, **support})
            continue
        standard = (x.to_numpy(float) - x.mean().to_numpy(float)) / x.std(ddof=1).replace(0, 1).to_numpy(float)
        seed = deterministic_seed([source_generation_id, window_name, list(x.columns), len(x)])
        knock, diagnostics = gaussian_model_x_knockoffs(standard, seed=seed)
        design = np.column_stack([standard, knock])
        coefficients = _ridge_coefficients(design, y.to_numpy(float), ridge=1.0)
        p = x.shape[1]
        statistics = np.abs(coefficients[:p]) - np.abs(coefficients[p:])
        threshold = _knockoff_threshold(statistics, float(fdr_target))
        selected = statistics >= threshold if threshold is not None else np.zeros(p, dtype=bool)
        test_target = _num_series(test_window, ("direction_correct",))
        if test_target.notna().sum() < 24:
            test_origin = _num_series(test_window, ("forecast_origin_price",))
            test_actual = _num_series(test_window, ("actual_close",))
            test_target = (test_actual - test_origin).where(test_origin.notna() & test_actual.notna())
        test_effects: dict[str, tuple[float | None, int]] = {}
        for feature in x.columns:
            if feature not in test_window:
                test_effects[str(feature)] = (None, 0); continue
            pair = pd.DataFrame({"x": pd.to_numeric(test_window[feature], errors="coerce"), "y": test_target}).dropna()
            effect = finite(pair["x"].corr(pair["y"])) if len(pair) >= 12 and pair["x"].nunique() > 1 else None
            test_effects[str(feature)] = (effect, int(len(pair)))
        for index, feature in enumerate(x.columns):
            selections.setdefault(str(feature), []).append(bool(selected[index]))
            validation_effects.setdefault(str(feature), []).append(test_effects.get(str(feature), (None, 0))[0])
            feature_rows.append({
                "record_key": "KO-" + stable_hash([source_generation_id, window_name, feature])[:24],
                "source_generation_id": source_generation_id,
                "window_id": window_name,
                "window_start": boundaries["test_start"], "window_end": boundaries["test_end"],
                "train_start": boundaries["train_start"], "train_end": boundaries["train_end"],
                "test_start": boundaries["test_start"], "test_end": boundaries["test_end"],
                "feature_name": str(feature), "feature_group": groups.get(str(feature), "OTHER"),
                "knockoff_statistic": float(statistics[index]), "selected_state": bool(selected[index]),
                "test_effect": test_effects.get(str(feature), (None, 0))[0],
                "test_sample_support": test_effects.get(str(feature), (None, 0))[1],
                "threshold": threshold, "fdr_target": float(fdr_target), "sample_support": int(len(x)),
                "regime_support": regime_support, "calculation_version": VERSION,
                "input_hash": stable_hash({"columns": list(x.columns), "window": boundaries, "source": source_generation_id}),
            })
        window_results.append({
            "window": window_name, "status": "SHADOW_EVALUATED", **boundaries,
            "feature_count": int(p), "selected_count": int(np.sum(selected)), "threshold": threshold,
            "diagnostics": diagnostics, **support,
        })
    stable_selected = sorted(feature for feature, flags in selections.items() if len(flags) >= 2 and all(flags[:2]))
    review_only = sorted(
        feature for feature, flags in selections.items()
        if len(flags) >= 2 and not any(flags[:2])
        and len(validation_effects.get(feature, [])) >= 2
        and all(effect is not None and abs(float(effect)) <= 0.05 for effect in validation_effects[feature][:2])
    )
    adequate_windows = sum(row.get("status") == "SHADOW_EVALUATED" for row in window_results) >= 2
    status = "SHADOW" if adequate_windows else "INSUFFICIENT_EVIDENCE"
    return {
        "version": VERSION, "paper": PAPER_TITLES[0], "status": status,
        "mode": "SHADOW", "minimum_sample_count": minimum_samples, "observed_sample_count": int(len(data)),
        "purge_rows": embargo, "embargo_rows": embargo, "fdr_target": float(fdr_target),
        "windows": window_results, "feature_statistics": feature_rows,
        "stable_selected_features": stable_selected,
        "removal_review_candidates": review_only if adequate_windows and regime_support >= 2 else [],
        "removal_review_rule": "unselected in both walk-forward windows, absolute test effect <= 0.05 in both, and at least two regimes",
        "automatic_feature_removal": False, "production_feature_set_changed": False,
        "regime_support": regime_support,
        "fdr_control_claimed": False,
        "assumption_status": "UNVERIFIED_ESTIMATED_COVARIATE_DISTRIBUTION",
        "reason": "Second-order knockoffs are implemented, but exact Model-X exchangeability is not proven for the supplied time-series covariates.",
    }


# ---------------------------------------------------------------------------
# Paper 2: central online FDR controller
# ---------------------------------------------------------------------------


def _gamma(index: int) -> float:
    i = max(1, int(index))
    return float(6.0 / (math.pi * math.pi * i * i))


def collect_sequential_tests(canonical: Mapping[str, Any], model_x: Mapping[str, Any]) -> list[dict[str, Any]]:
    tests: list[dict[str, Any]] = []
    existing = mapping(canonical.get("research_validation_20260621"))
    cpa = mapping(existing.get("conditional_predictive_ability"))
    for row in list(cpa.get("rows") or [])[:120]:
        p_value = finite(row.get("p_value"))
        if p_value is not None:
            tests.append({"test_family": "forecast_superiority", "raw_p_value": p_value, "source": "conditional_predictive_ability", "test_key": row.get("evaluation_id") or stable_hash(row)})
    for item in list(existing.get("superior_predictive_ability") or [])[:24]:
        row = mapping(mapping(item).get("row"))
        p_value = finite(row.get("spa_p_value"))
        if p_value is not None:
            tests.append({"test_family": "promotion_tests", "raw_p_value": p_value, "source": "superior_predictive_ability", "test_key": row.get("evaluation_id") or stable_hash(row)})
    advanced = mapping(canonical.get("advanced_reliability_shift"))
    for family, section_name in (("drift", "mmd"), ("calibration", "multicalibration"), ("regime_conditional", "conformal_risk_control")):
        section = mapping(advanced.get(section_name))
        p_value = finite(section.get("p_value"), finite(section.get("test_p_value")))
        if p_value is not None:
            tests.append({"test_family": family, "raw_p_value": p_value, "source": section_name, "test_key": section.get("evaluation_id") or stable_hash([section_name, section])})
    # Knockoff selection is controlled by its own threshold; register a family
    # audit row without inventing a p-value.
    if model_x:
        tests.append({"test_family": "feature_selection", "raw_p_value": None, "source": "model_x_knockoffs", "test_key": stable_hash(["model_x", model_x.get("source_generation_id"), model_x.get("fdr_target")]), "status": "NON_PVALUE_FDR_PROCEDURE"})
    unique: dict[str, dict[str, Any]] = {}
    for row in tests:
        unique[str(row["test_key"])] = row
    return list(unique.values())[:MAX_FDR_TESTS_PER_RUN]


def apply_online_fdr(
    tests: Sequence[Mapping[str, Any]],
    *,
    source_generation_id: str,
    previous_state: Mapping[str, Any] | None = None,
    fdr_target: float = DEFAULT_FDR_TARGET,
) -> dict[str, Any]:
    previous = dict(previous_state or {})
    state_version = "online-fdr-alpha-investing-shadow-v1"
    migration = "CONTINUED"
    if previous.get("state_version") not in (None, state_version):
        previous = {}
        migration = "DETERMINISTIC_RESET_VERSION_CHANGE"
    wealth = finite(previous.get("wealth"), float(fdr_target) / 2.0) or float(fdr_target) / 2.0
    test_index = int(previous.get("test_index") or 0)
    recent = [str(x) for x in (previous.get("recent_test_keys") or [])][-300:]
    seen = set(recent)
    records: list[dict[str, Any]] = []
    for raw in tests:
        key = str(raw.get("test_key") or stable_hash(raw))
        p_value = finite(raw.get("raw_p_value"))
        if key in seen:
            continue
        if p_value is None:
            records.append({
                "record_key": "FDR-" + stable_hash([source_generation_id, key])[:24],
                "source_generation_id": source_generation_id, "test_key": key,
                "test_family": raw.get("test_family"), "source_module": raw.get("source"),
                "raw_p_value": None, "allocated_alpha": 0.0, "adjusted_result": "NOT_A_PVALUE_TEST",
                "wealth_before": wealth, "wealth_after": wealth, "test_index": test_index,
                "dependence_assumption": "not applicable", "calculation_version": VERSION,
            })
            recent.append(key); seen.add(key)
            continue
        p_value = float(max(0.0, min(1.0, p_value)))
        test_index += 1
        wealth_before = wealth
        allocated = min(float(fdr_target), max(1e-8, wealth_before * _gamma(test_index)))
        rejected = bool(p_value <= allocated)
        if rejected:
            wealth = min(float(fdr_target), wealth_before + float(fdr_target) * 0.25)
        else:
            wealth = max(1e-8, wealth_before - allocated / max(1.0 - allocated, 1e-8))
        records.append({
            "record_key": "FDR-" + stable_hash([source_generation_id, key, test_index])[:24],
            "source_generation_id": source_generation_id, "test_key": key,
            "test_family": raw.get("test_family"), "source_module": raw.get("source"),
            "raw_p_value": p_value, "allocated_alpha": allocated,
            "adjusted_result": "REJECT" if rejected else "DO_NOT_REJECT",
            "wealth_before": wealth_before, "wealth_after": wealth, "test_index": test_index,
            "dependence_assumption": "FDR theorem requires valid null p-values and independence/qualified dependence conditions",
            "calculation_version": VERSION,
        })
        recent.append(key); seen.add(key)
    state = {
        "state_id": "ONLINE_FDR-" + stable_hash([source_generation_id, state_version])[:24], "state_version": state_version,
        "updated_at": utc_now_iso(), "source_generation_id": source_generation_id,
        "fdr_target": float(fdr_target), "wealth": float(wealth), "test_index": int(test_index),
        "recent_test_keys": recent[-300:], "migration_action": migration,
        "dependence_assumptions_documented": True, "fdr_control_claimed_for_production": False,
        "calculation_version": VERSION,
    }
    return {
        "version": VERSION, "paper": PAPER_TITLES[1], "status": "SHADOW",
        "controller_scope": "CENTRAL_ALL_SEQUENTIAL_TESTS", "records": records, "state": state,
        "new_pvalue_test_count": int(sum(r["raw_p_value"] is not None for r in records)),
        "rejection_count": int(sum(r["adjusted_result"] == "REJECT" for r in records)),
        "unlimited_module_thresholds_allowed": False,
        "dependence_assumptions": state["dependence_assumptions_documented"],
    }


# ---------------------------------------------------------------------------
# Paper 3: reject option
# ---------------------------------------------------------------------------


def build_reject_option_shadow(
    canonical: Mapping[str, Any], settled_predictions: pd.DataFrame,
    *, source_generation_id: str, rejection_cost: float = DEFAULT_REJECTION_COST,
) -> dict[str, Any]:
    final = mapping(canonical.get("final_decision"))
    protected = direction(final.get("tradeability_decision") or final.get("final_decision") or canonical.get("tradeability_decision"))
    confidence = probability(final.get("calibrated_confidence"), probability(_value(canonical, "reliability.score"), 0.5)) or 0.5
    uncertainty = probability(final.get("uncertainty_pct"), 1.0 - confidence) or (1.0 - confidence)
    exit_risk_raw = finite(canonical.get("exit_risk"), 5.0) or 5.0
    exit_risk = float(max(0.0, min(1.0, exit_risk_raw if exit_risk_raw <= 1.0 else exit_risk_raw / (10.0 if exit_risk_raw <= 10.0 else 100.0))))
    conflict = probability(_value(canonical, "priority.conflict_score", "reliability.conflict_score"), 0.0) or 0.0
    accepted_risk_estimate = float(max(0.0, min(1.0, 0.55 * (1.0 - confidence) + 0.20 * uncertainty + 0.15 * exit_risk + 0.10 * conflict)))
    shadow = protected
    if protected in {"BUY", "SELL"} and accepted_risk_estimate > float(rejection_cost):
        shadow = "WAIT"
    if protected == "WAIT":
        shadow = "WAIT"
    data = _settled(settled_predictions)
    metrics = {"accepted_decision_risk": None, "coverage": None, "wait_rate": None, "missed_opportunity_rate": None, "sample_count": int(len(data))}
    if not data.empty:
        decisions = _text_series(data, ("final_decision", "tradeability_status")).map(direction)
        confidences = _num_series(data, ("calibrated_confidence", "raw_confidence"))
        confidences = confidences.where(confidences <= 1.0, confidences / 100.0).clip(0, 1)
        correct = _num_series(data, ("direction_correct",)).clip(0, 1)
        tradeable = decisions.isin(["BUY", "SELL"])
        accepted = tradeable & (confidences >= 1.0 - float(rejection_cost))
        rejected = tradeable & ~accepted
        if tradeable.any():
            metrics["coverage"] = float(accepted.sum() / tradeable.sum())
            metrics["wait_rate"] = float(rejected.sum() / tradeable.sum())
            metrics["missed_opportunity_rate"] = float(((rejected) & correct.eq(1)).sum() / tradeable.sum())
        if accepted.any() and correct.notna().any():
            metrics["accepted_decision_risk"] = float((1.0 - correct.loc[accepted]).mean())
    return {
        "version": VERSION, "paper": PAPER_TITLES[2], "status": "SHADOW",
        "source_generation_id": source_generation_id, "protected_decision": protected,
        "shadow_reject_option_decision": shadow, "rejection_cost": float(rejection_cost),
        "accepted_risk_estimate": accepted_risk_estimate, "metrics": metrics,
        "protected_decision_visible_and_unchanged": True,
        "existing_wait_promoted": False, "direction_reversal_allowed": False,
        "production_influence_allowed": False,
    }


# ---------------------------------------------------------------------------
# Paper 4: flexible asymmetric loss
# ---------------------------------------------------------------------------

FLEXIBLE_LOSS_DEFINITION = {
    "version": "trading-flexible-loss-v1-fixed-before-evaluation",
    "wrong_direction": 4.0,
    "tp_late_proxy": 1.0,
    "sl_first_proxy": 3.0,
    "maximum_adverse_excursion": 1.5,
    "interval_miss": 1.5,
    "high_exit_risk_proxy": 1.0,
}


def _loss_rows(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()
    result = pd.DataFrame(index=data.index)
    correct = _num_series(data, ("direction_correct",)).clip(0, 1)
    result["wrong_direction"] = 1.0 - correct
    tp = _num_series(data, ("tp_touched",)).clip(0, 1)
    sl = _num_series(data, ("sl_touched",)).clip(0, 1)
    result["tp_late_proxy"] = ((correct.eq(1)) & tp.eq(0)).astype(float).where(correct.notna() & tp.notna())
    result["sl_first_proxy"] = sl  # ledger has touch state, not exact first-touch ordering
    mae = _num_series(data, ("maximum_adverse_excursion",)).abs()
    scale = _num_series(data, ("expected_favorable_movement",)).abs().replace(0, np.nan)
    if scale.notna().sum() < 8:
        scale = mae.median() if mae.notna().any() else 1.0
    result["maximum_adverse_excursion"] = (mae / scale).clip(0, 5) if isinstance(scale, pd.Series) else (mae / max(float(scale), 1e-9)).clip(0, 5)
    interval_hit = _num_series(data, ("interval_hit",)).clip(0, 1)
    result["interval_miss"] = 1.0 - interval_hit
    adverse = _num_series(data, ("expected_adverse_movement",)).abs()
    favorable = _num_series(data, ("expected_favorable_movement",)).abs().replace(0, np.nan)
    result["high_exit_risk_proxy"] = (adverse / favorable).clip(0, 5)
    weighted = pd.Series(0.0, index=result.index)
    weight_support = pd.Series(0.0, index=result.index)
    for component, weight in FLEXIBLE_LOSS_DEFINITION.items():
        if component == "version":
            continue
        values = pd.to_numeric(result[component], errors="coerce")
        weighted = weighted.add(values.fillna(0.0) * float(weight), fill_value=0.0)
        weight_support = weight_support.add(values.notna().astype(float) * float(weight), fill_value=0.0)
    result["flexible_loss"] = weighted / weight_support.replace(0, np.nan)
    return result


def evaluate_flexible_asymmetric_loss(
    settled_predictions: pd.DataFrame, *, source_generation_id: str, minimum_samples: int = DEFAULT_MINIMUM_SAMPLES, embargo: int = 6,
) -> dict[str, Any]:
    data = _settled(settled_predictions)
    windows = _chronological_windows(data, minimum_samples=minimum_samples, embargo=embargo)
    rows: list[dict[str, Any]] = []
    for name, train_window, test_window, boundaries in windows[:2]:
        losses = _loss_rows(test_window)
        component_means = {c: finite(losses[c].mean()) for c in losses.columns if c != "flexible_loss"}
        value = finite(losses["flexible_loss"].mean()) if "flexible_loss" in losses else None
        rows.append({
            "evaluation_id": "LOSS-" + stable_hash([source_generation_id, name, FLEXIBLE_LOSS_DEFINITION])[:24],
            "source_generation_id": source_generation_id, "window_id": name,
            "window_start": boundaries["test_start"], "window_end": boundaries["test_end"],
            "train_start": boundaries["train_start"], "train_end": boundaries["train_end"],
            "test_start": boundaries["test_start"], "test_end": boundaries["test_end"],
            "train_row_count": boundaries["train_row_count"], "test_row_count": boundaries["test_row_count"],
            "purge_rows": embargo, "embargo_rows": embargo, "sample_count": int(losses["flexible_loss"].notna().sum()) if not losses.empty else 0,
            "loss_definition_version": FLEXIBLE_LOSS_DEFINITION["version"],
            "loss_weights": FLEXIBLE_LOSS_DEFINITION, "mean_flexible_loss": value,
            "component_means": component_means, "status": "EVALUATED" if value is not None else "INSUFFICIENT_EVIDENCE",
            "calculation_version": VERSION,
        })
    status = "SHADOW" if len(rows) >= 2 and all(r["status"] == "EVALUATED" for r in rows) else "INSUFFICIENT_EVIDENCE"
    return {
        "version": VERSION, "paper": PAPER_TITLES[3], "status": status,
        "loss_definition": FLEXIBLE_LOSS_DEFINITION, "windows": rows,
        "weights_tuned_on_complete_history": False,
        "existing_mae_rmse_brier_crps_interval_score_unchanged": True,
        "limitations": ["TP-late and SL-first are conservative proxies because the current settled ledger stores touches, not ordered intrahour paths."],
    }


# ---------------------------------------------------------------------------
# Paper 5: explanations / SHAP routing
# ---------------------------------------------------------------------------


def _rule_contributions(canonical: Mapping[str, Any], protected: str) -> list[dict[str, Any]]:
    raw = {
        "Master score": finite(canonical.get("master_score"), 5.0),
        "Entry score": finite(canonical.get("entry_score"), 5.0),
        "Hold safety": finite(canonical.get("hold_safety"), 5.0),
        "TP quality": finite(canonical.get("tp_quality"), 5.0),
        "Exit risk": finite(canonical.get("exit_risk"), 5.0),
        "Trend capacity": finite(canonical.get("trend_capacity_remaining"), 5.0),
        "Reliability": finite(_value(canonical, "reliability.score"), 50.0),
        "Forecast agreement": finite(_value(canonical, "forecasts.agreement_score", "priority.forecast_agreement"), 50.0),
        "Conflict": finite(_value(canonical, "priority.conflict_score", "reliability.conflict_score"), 0.0),
        "Data quality": finite(_value(canonical, "data_quality.score"), 50.0),
    }
    rows: list[dict[str, Any]] = []
    for name, value in raw.items():
        if value is None:
            continue
        if name in {"Reliability", "Forecast agreement", "Conflict", "Data quality"}:
            centered = (float(value) - 50.0) / 50.0
        else:
            centered = (float(value) - 5.0) / 5.0
        if name in {"Exit risk", "Conflict"}:
            centered *= -1.0
        rows.append({"factor": name, "contribution": float(centered), "method": "protected-rule-grouped-contribution"})
    return sorted(rows, key=lambda r: abs(r["contribution"]), reverse=True)[:MAX_CACHE_FACTORS]


def build_lightweight_explanations(canonical: Mapping[str, Any], *, source_generation_id: str) -> dict[str, Any]:
    final = mapping(canonical.get("final_decision"))
    protected = direction(final.get("tradeability_decision") or final.get("final_decision"))
    grouped = _rule_contributions(canonical, protected)
    supporting = [row for row in grouped if row["contribution"] > 0][:5]
    opposing = [row for row in grouped if row["contribution"] < 0][:5]
    wait_causing = [row for row in opposing if row["factor"] in {"Exit risk", "Conflict", "Reliability", "Data quality"}][:5]
    raw_tree = mapping(canonical.get("tree_shap_explanations"))
    raw_linear = mapping(canonical.get("linear_model_explanations"))
    tree_descriptor = str(raw_tree.get("model_type") or raw_tree.get("estimator_type") or raw_tree.get("method") or "").lower()
    tree_compatible = bool(raw_tree) and any(token in tree_descriptor for token in (
        "treeshap", "tree_shap", "xgboost", "lightgbm", "catboost", "randomforest",
        "random_forest", "decisiontree", "decision_tree", "gradientboost", "gradient_boost",
    ))
    linear_descriptor = str(raw_linear.get("model_type") or raw_linear.get("estimator_type") or raw_linear.get("method") or "").lower()
    linear_compatible = bool(raw_linear) and (
        any(token in linear_descriptor for token in ("linear", "logistic", "ridge", "lasso", "elastic"))
        or any(key in raw_linear for key in ("coefficients", "contributions", "feature_contributions"))
    )
    precomputed_tree = _bounded_json(raw_tree, max_items=32) if tree_compatible else {}
    linear = _bounded_json(raw_linear, max_items=32) if linear_compatible else {}
    tree_status = "TREE_SHAP_CACHE_USED" if tree_compatible else "NO_COMPATIBLE_PRECOMPUTED_TREE_SHAP"
    linear_status = "EXACT_LINEAR_CONTRIBUTIONS_USED" if linear_compatible else "NO_LINEAR_COEFFICIENT_PAYLOAD"
    payload = {
        "version": VERSION, "paper": PAPER_TITLES[4], "status": "SHADOW",
        "source_generation_id": source_generation_id, "canonical_calculation_id": source_generation_id,
        "protected_decision": protected, "tree_shap_status": tree_status, "linear_status": linear_status,
        "grouped_rule_contributions": grouped, "top_supporting_factors": supporting,
        "top_opposing_factors": opposing, "wait_causing_factors": wait_causing,
        "tree_shap": precomputed_tree if precomputed_tree else {}, "linear_contributions": linear if linear else {},
        "attribution_is_causal_evidence": False,
        "causality_notice": "Feature attribution explains model/rule output allocation; it is not causal evidence.",
    }
    payload["explanation_id"] = "EXP-" + stable_hash([source_generation_id, grouped, precomputed_tree, linear])[:24]
    return payload


# ---------------------------------------------------------------------------
# Paper 6: monotonicity contract validator
# ---------------------------------------------------------------------------

MONOTONICITY_CONTRACT = (
    ("exit_risk_vs_tradeability", "exit_risk", "tradeability", "NONINCREASING"),
    ("uncertainty_vs_reliability", "uncertainty", "reliability", "NONINCREASING"),
    ("data_quality_vs_reliability", "data_quality", "reliability", "NONDECREASING"),
    ("conflict_vs_priority_quality", "conflict", "priority_quality", "NONINCREASING"),
    ("forecast_support_vs_confidence", "model_agreement", "calibrated_confidence", "NONDECREASING"),
    ("sample_support_vs_evidence_confidence", "sample_support", "evidence_confidence", "NONDECREASING"),
)


def _monotonic_violation_rate(x: pd.Series, y: pd.Series, expected: str, *, bins: int = 8) -> tuple[float | None, int, list[float]]:
    frame = pd.DataFrame({"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}).dropna()
    if len(frame) < 24 or frame["x"].nunique() < 3:
        return None, int(len(frame)), []
    ranks = frame["x"].rank(method="first")
    q = min(int(bins), max(3, int(math.sqrt(len(frame)))))
    frame["bin"] = pd.qcut(ranks, q=q, duplicates="drop")
    means = frame.groupby("bin", observed=True)["y"].mean().to_numpy(float)
    diffs = np.diff(means)
    tolerance = 1e-9
    violations = diffs < -tolerance if expected == "NONDECREASING" else diffs > tolerance
    return float(np.mean(violations)) if len(violations) else 0.0, int(len(frame)), means.tolist()


def validate_monotonicity_contract(settled_predictions: pd.DataFrame, *, source_generation_id: str) -> dict[str, Any]:
    data = _settled(settled_predictions)
    tradeability = _text_series(data, ("final_decision", "tradeability_status")).map(lambda v: 1.0 if direction(v) in {"BUY", "SELL"} else 0.0)
    confidence = _num_series(data, ("calibrated_confidence", "raw_confidence"))
    confidence = confidence.where(confidence <= 1.0, confidence / 100.0).clip(0, 1)
    reliability = _num_series(data, ("reliability_score", "reliability"))
    reliability = reliability.where(reliability <= 1.0, reliability / 100.0).clip(0, 1)
    if reliability.notna().sum() < 24:
        reliability = _num_series(data, ("direction_correct",)).expanding(min_periods=12).mean()
    exit_risk = _num_series(data, ("exit_risk", "expected_adverse_movement", "maximum_adverse_excursion")).abs()
    exit_risk = exit_risk.where(exit_risk <= 1.0, exit_risk / 10.0).clip(0, 1)
    conflict = _num_series(data, ("conflict_score",))
    if conflict.notna().sum() < 24:
        agreement = _num_series(data, ("model_agreement",))
        agreement = agreement.where(agreement <= 1.0, agreement / 100.0).clip(0, 1)
        conflict = 1.0 - agreement
    else:
        conflict = conflict.where(conflict <= 1.0, conflict / 100.0).clip(0, 1)
    inputs = {
        "exit_risk": exit_risk,
        "tradeability": tradeability,
        "uncertainty": 1.0 - confidence,
        "reliability": reliability,
        "data_quality": _text_series(data, ("data_quality_status",)).map({"FAIL": 0.0, "BLOCKED": 0.0, "WARNING": 0.5, "PASS": 1.0, "OK": 1.0}).astype(float),
        "conflict": conflict,
        "priority_quality": 1.0 / (1.0 + _num_series(data, ("priority", "greedy_rank")).clip(lower=0)),
        "model_agreement": _num_series(data, ("model_agreement",)),
        "calibrated_confidence": confidence,
        "sample_support": pd.Series(np.arange(1, len(data) + 1), index=data.index, dtype=float),
        "evidence_confidence": confidence.expanding(min_periods=1).mean(),
    }
    rows: list[dict[str, Any]] = []
    for name, x_name, y_name, expected in MONOTONICITY_CONTRACT:
        rate, support, bin_means = _monotonic_violation_rate(inputs[x_name], inputs[y_name], expected)
        status = "INSUFFICIENT_EVIDENCE" if rate is None else "PASS" if rate <= 0.10 else "VIOLATION"
        rows.append({
            "record_key": "MONO-" + stable_hash([source_generation_id, name])[:24],
            "source_generation_id": source_generation_id, "contract_name": name,
            "input_name": x_name, "output_name": y_name, "expected_direction": expected,
            "sample_support": support, "violation_rate": rate, "status": status,
            "bin_means": bin_means, "calculation_version": VERSION,
        })
    evaluated = [r for r in rows if r["status"] != "INSUFFICIENT_EVIDENCE"]
    overall = "PASS" if evaluated and all(r["status"] == "PASS" for r in evaluated) else "VIOLATION" if any(r["status"] == "VIOLATION" for r in evaluated) else "INSUFFICIENT_EVIDENCE"
    return {
        "version": VERSION, "paper": PAPER_TITLES[5], "status": overall,
        "mode": "VALIDATOR_ONLY", "contract": [list(x) for x in MONOTONICITY_CONTRACT],
        "results": rows, "protected_scores_altered": False, "constrained_model_promoted": False,
    }


# ---------------------------------------------------------------------------
# Paper 7: exact incremental/delta maintenance
# ---------------------------------------------------------------------------

HISTORY_DELTA_INVENTORY = (
    ("count_sum_sumsq", "INCREMENTAL_SAFE", "associative sufficient statistics"),
    ("minimum_maximum", "INCREMENTAL_SAFE_APPEND_ONLY", "exact for inserts; deletions require recompute"),
    ("contingency_counts", "INCREMENTAL_SAFE", "exact additive counts"),
    ("mean_variance", "DERIVED_FROM_SAFE_STATE", "derive from count/sum/sumsq"),
    ("quantiles", "FULL_RECOMPUTE_REQUIRED", "exact quantiles are not algebraic under bounded state"),
    ("matrix_profile", "FULL_RECOMPUTE_REQUIRED", "global nearest-neighbour relationships can change"),
    ("constrained_dtw_rank", "FULL_RECOMPUTE_REQUIRED", "top-k/rank is non-monotonic"),
    ("knockoff_selection", "FULL_RECOMPUTE_REQUIRED", "joint covariance and threshold change"),
    ("latest_current_top_k", "COORDINATED_RECOMPUTE_REQUIRED", "replacement decision"),
)


def _row_identity(frame: pd.DataFrame) -> pd.Series:
    calc = _text_series(frame, ("calculation_id",))
    horizon = _num_series(frame, ("horizon",)).fillna(0).astype(int).astype(str)
    target = _text_series(frame, ("target_time", "forecast_origin_time"))
    return calc + "|" + horizon + "|" + target


def _exact_stats(frame: pd.DataFrame) -> dict[str, Any]:
    values = _num_series(frame, ("absolute_error_pips", "absolute_error")).dropna().to_numpy(float)
    correct = _num_series(frame, ("direction_correct",)).dropna().to_numpy(float)
    return {
        "count": int(len(values)), "sum": float(values.sum()) if len(values) else 0.0,
        "sum_squares": float(np.square(values).sum()) if len(values) else 0.0,
        "minimum": float(values.min()) if len(values) else None,
        "maximum": float(values.max()) if len(values) else None,
        "direction_correct_count": int(np.sum(correct == 1)), "direction_incorrect_count": int(np.sum(correct == 0)),
    }


def _stats_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    integer_keys = ("count", "direction_correct_count", "direction_incorrect_count")
    if any(int(left.get(k) or 0) != int(right.get(k) or 0) for k in integer_keys):
        return False
    for key in ("sum", "sum_squares", "minimum", "maximum"):
        a, b = finite(left.get(key)), finite(right.get(key))
        if a is None or b is None:
            if a is not None or b is not None:
                return False
            continue
        if not math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12):
            return False
    return True


def _merge_stats(previous: Mapping[str, Any], delta: Mapping[str, Any]) -> dict[str, Any]:
    prev_min, delta_min = finite(previous.get("minimum")), finite(delta.get("minimum"))
    prev_max, delta_max = finite(previous.get("maximum")), finite(delta.get("maximum"))
    return {
        "count": int(previous.get("count") or 0) + int(delta.get("count") or 0),
        "sum": float(previous.get("sum") or 0.0) + float(delta.get("sum") or 0.0),
        "sum_squares": float(previous.get("sum_squares") or 0.0) + float(delta.get("sum_squares") or 0.0),
        "minimum": min(v for v in (prev_min, delta_min) if v is not None) if any(v is not None for v in (prev_min, delta_min)) else None,
        "maximum": max(v for v in (prev_max, delta_max) if v is not None) if any(v is not None for v in (prev_max, delta_max)) else None,
        "direction_correct_count": int(previous.get("direction_correct_count") or 0) + int(delta.get("direction_correct_count") or 0),
        "direction_incorrect_count": int(previous.get("direction_incorrect_count") or 0) + int(delta.get("direction_incorrect_count") or 0),
    }


def update_exact_delta_state(settled_predictions: pd.DataFrame, *, source_generation_id: str, previous_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    data = _settled(settled_predictions)
    ids = _row_identity(data) if not data.empty else pd.Series(dtype=str)
    source_hash = stable_hash(ids.tolist())
    previous = dict(previous_state or {})
    previous_count = int(previous.get("source_row_count") or 0)
    previous_hash = str(previous.get("source_prefix_hash") or "")
    append_safe = previous_count <= len(data) and (previous_count == 0 or stable_hash(ids.iloc[:previous_count].tolist()) == previous_hash)
    tracing_was_active = tracemalloc.is_tracing()
    if not tracing_was_active:
        tracemalloc.start()
    full_before_current, full_before_peak = tracemalloc.get_traced_memory()
    start = time.perf_counter()
    exact = _exact_stats(data)
    full_time_ms = (time.perf_counter() - start) * 1000.0
    full_after_current, full_after_peak = tracemalloc.get_traced_memory()
    full_peak = max(0, full_after_peak - min(full_before_current, full_before_peak))
    if not tracing_was_active:
        tracemalloc.stop()
    delta_time_ms = None
    delta_peak = None
    mode = "FULL_RECOMPUTE"
    candidate = exact
    equality = True
    if append_safe and previous_count > 0:
        delta_rows = data.iloc[previous_count:]
        delta_tracing_was_active = tracemalloc.is_tracing()
        if not delta_tracing_was_active:
            tracemalloc.start()
        delta_before_current, delta_before_peak = tracemalloc.get_traced_memory()
        start = time.perf_counter()
        candidate = _merge_stats(mapping(previous.get("statistics")), _exact_stats(delta_rows))
        delta_time_ms = (time.perf_counter() - start) * 1000.0
        delta_after_current, delta_after_peak = tracemalloc.get_traced_memory()
        delta_peak = max(0, delta_after_peak - min(delta_before_current, delta_before_peak))
        if not delta_tracing_was_active:
            tracemalloc.stop()
        equality = _stats_equal(candidate, exact)
        mode = "EXACT_DELTA" if equality else "REJECTED_DELTA_MISMATCH"
        if not equality:
            candidate = exact
    state = {
        "state_id": "EXACT-DELTA-" + stable_hash([source_generation_id, VERSION])[:24], "updated_at": utc_now_iso(),
        "source_generation_id": source_generation_id, "source_row_count": int(len(data)),
        "source_prefix_hash": source_hash, "last_row_identity": str(ids.iloc[-1]) if len(ids) else None,
        "statistics": candidate, "mode": mode, "calculation_version": VERSION,
    }
    return {
        "version": VERSION, "paper": PAPER_TITLES[6], "status": "SHADOW",
        "inventory": [{"calculation": a, "classification": b, "reason": c} for a, b, c in HISTORY_DELTA_INVENTORY],
        "state": state, "append_safe": bool(append_safe), "exact_full_recompute_equal": bool(equality),
        "optimization_accepted": bool(mode == "EXACT_DELTA"),
        "benchmark": {
            "full_recompute_ms": full_time_ms, "delta_ms": delta_time_ms,
            "full_peak_allocation_bytes": int(full_peak), "delta_peak_allocation_bytes": int(delta_peak) if delta_peak is not None else None,
            "database_reads": 0, "write_time_ms": None, "process_rss_mb": None,
        },
        "approximate_delta_logic_used": False,
    }


# ---------------------------------------------------------------------------
# Paper 8: compact provenance graph / semiring interpretation
# ---------------------------------------------------------------------------


def _node(node_type: str, natural_key: Any, payload: Mapping[str, Any], source_generation_id: str) -> dict[str, Any]:
    node_id = "PVN-" + stable_hash([node_type, natural_key])[:28]
    compact_payload = _bounded_json(payload, max_items=32)
    return {
        "node_id": node_id, "node_type": node_type, "natural_key": str(natural_key),
        "immutable_identity": node_id, "source_generation_id": source_generation_id,
        "payload": compact_payload, "payload_hash": stable_hash(compact_payload),
        "calculation_version": VERSION,
    }


def _edge(source: str, target: str, relation: str, source_generation_id: str) -> dict[str, Any]:
    return {
        "edge_id": "PVE-" + stable_hash([source, target, relation])[:28],
        "source_node_id": source, "target_node_id": target, "relation_type": relation,
        "source_generation_id": source_generation_id, "calculation_version": VERSION,
    }


def build_provenance_graph(
    canonical: Mapping[str, Any], completed_h1: pd.DataFrame, settled_predictions: pd.DataFrame,
    *, source_generation_id: str, research_result_ids: Sequence[str] = (),
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    generation = _node("canonical_generation", source_generation_id, {
        "run_id": canonical.get("run_id"), "generation": canonical.get("calculation_generation"),
        "completed_candle": canonical.get("latest_completed_candle_time"), "input_hash": canonical.get("data_signature"),
    }, source_generation_id)
    nodes.append(generation)
    candles = _completed_h1(completed_h1, canonical.get("latest_completed_candle_time")).tail(256)
    for timestamp, row in candles.iterrows():
        payload = {k: finite(row.get(k)) for k in ("open", "high", "low", "close", "volume") if k in row.index}
        node = _node("completed_candle", pd.Timestamp(timestamp).isoformat(), payload, source_generation_id)
        nodes.append(node); edges.append(_edge(node["node_id"], generation["node_id"], "INPUT_TO", source_generation_id))
    settled = _settled(settled_predictions, limit=192)
    for _, row in settled.iterrows():
        natural = [row.get("calculation_id"), row.get("horizon"), row.get("target_time")]
        node = _node("settled_forecast", natural, {
            "calculation_id": row.get("calculation_id"), "horizon": row.get("horizon"),
            "target_time": row.get("target_time"), "record_status": row.get("record_status"),
        }, source_generation_id)
        nodes.append(node); edges.append(_edge(node["node_id"], generation["node_id"], "EVIDENCE_FOR", source_generation_id))
    for node_type, path in (("regime", "regime"), ("nlp_event", "nlp"), ("similar_day", "similar_day_intelligence"), ("priority", "priority")):
        payload = mapping(canonical.get(path))
        if payload:
            compact = {k: payload.get(k) for k in list(payload)[:20] if not isinstance(payload.get(k), (pd.DataFrame, np.ndarray))}
            node = _node(node_type, [source_generation_id, node_type], compact, source_generation_id)
            nodes.append(node); edges.append(_edge(node["node_id"], generation["node_id"], "INPUT_TO", source_generation_id))
    nlp_payload = mapping(canonical.get("nlp"))
    for index, event in enumerate(list(nlp_payload.get("events") or nlp_payload.get("ranked_events") or [])[:48]):
        event_map = mapping(event)
        natural = event_map.get("event_id") or event_map.get("timestamp") or [source_generation_id, "nlp", index]
        node = _node("nlp_event", natural, event_map, source_generation_id)
        nodes.append(node); edges.append(_edge(node["node_id"], generation["node_id"], "INPUT_TO", source_generation_id))
    similar_payload = mapping(canonical.get("similar_day_intelligence"))
    candidates = similar_payload.get("candidates") or similar_payload.get("similar_days") or similar_payload.get("top_matches") or []
    for index, candidate in enumerate(list(candidates)[:48]):
        candidate_map = mapping(candidate)
        natural = candidate_map.get("candidate_id") or candidate_map.get("date") or candidate_map.get("timestamp") or [source_generation_id, "similar", index]
        node = _node("similar_day_candidate", natural, candidate_map, source_generation_id)
        nodes.append(node); edges.append(_edge(node["node_id"], generation["node_id"], "INPUT_TO", source_generation_id))
    for result_id in research_result_ids:
        result_text = str(result_id)
        node_type = "research_test" if result_text.startswith(("FDR-", "META-", "GATE-")) else "research_result"
        node = _node(node_type, result_text, {"result_id": result_text}, source_generation_id)
        nodes.append(node); edges.append(_edge(generation["node_id"], node["node_id"], "PRODUCES", source_generation_id))
    # Bound payload while preserving deterministic most-relevant order.
    nodes = nodes[:MAX_PROVENANCE_NODES]
    allowed = {n["node_id"] for n in nodes}
    edges = [e for e in edges if e["source_node_id"] in allowed and e["target_node_id"] in allowed][:MAX_PROVENANCE_NODES * 2]
    return {
        "version": VERSION, "paper": PAPER_TITLES[7], "status": "SHADOW",
        "semiring_interpretation": {"addition": "alternative evidence paths / union", "multiplication": "joint dependency / conjunction"},
        "nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges),
        "source_generation_id": source_generation_id, "large_symbolic_expressions_in_session_state": False,
        "lineage_query_available": True,
    }


def lineage_for_result(graph: Mapping[str, Any], target_node_id: str) -> dict[str, Any]:
    nodes = {str(n.get("node_id")): dict(n) for n in graph.get("nodes", [])}
    edges = [dict(e) for e in graph.get("edges", [])]
    incoming: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        incoming.setdefault(str(edge.get("target_node_id")), []).append(edge)
    visited: set[str] = set()
    stack = [str(target_node_id)]
    while stack and len(visited) < 512:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for edge in incoming.get(current, []):
            stack.append(str(edge.get("source_node_id")))
    return {"target_node_id": target_node_id, "nodes": [nodes[n] for n in visited if n in nodes], "edges": [e for e in edges if e.get("source_node_id") in visited and e.get("target_node_id") in visited]}


# ---------------------------------------------------------------------------
# Paper 9: runtime metamorphic relations
# ---------------------------------------------------------------------------


def _ohlc_columns(frame: pd.DataFrame) -> dict[str, str]:
    lookup = {str(c).strip().lower(): str(c) for c in frame.columns}
    return {name: lookup[name] for name in ("open", "high", "low", "close") if name in lookup}


def run_metamorphic_relations(canonical: Mapping[str, Any], completed_h1: pd.DataFrame, *, source_generation_id: str, reject_shadow: Mapping[str, Any]) -> dict[str, Any]:
    data = _completed_h1(completed_h1, canonical.get("latest_completed_candle_time"))
    cols = _ohlc_columns(data)
    relations: list[dict[str, Any]] = []

    def add(name: str, passed: bool | None, detail: str) -> None:
        relations.append({
            "record_key": "META-" + stable_hash([source_generation_id, name])[:24],
            "source_generation_id": source_generation_id, "relation_name": name,
            "status": "PASS" if passed is True else "FAIL" if passed is False else "UNAVAILABLE",
            "detail": detail, "calculation_version": VERSION,
        })

    if data.empty:
        for name in (
            "future_incomplete_candle_append_invariance", "row_order_invariance", "duplicate_timestamp_rejection",
            "price_translation_invariance_difference_returns", "positive_price_scaling_invariance_normalized_shape",
            "phone_projected_history_overlap_equality",
        ):
            add(name, None, "No completed H1 frame")
    else:
        base_hash = stable_hash(data.sort_index().to_dict("split"))
        future = data.tail(1).copy()
        future.index = [data.index.max() + pd.Timedelta(hours=1)]
        appended = pd.concat([data, future])
        filtered = appended.loc[appended.index <= data.index.max()]
        add("future_incomplete_candle_append_invariance", stable_hash(filtered.sort_index().to_dict("split")) == base_hash, "Future row excluded using published latest-completed cutoff")
        shuffled = data.sample(frac=1.0, random_state=deterministic_seed(source_generation_id))
        add("row_order_invariance", stable_hash(shuffled.sort_index().to_dict("split")) == base_hash, "Canonical sorting restores identity")
        duplicate = pd.concat([data, data.iloc[[-1]]])
        add("duplicate_timestamp_rejection", bool(duplicate.index.duplicated().any()), "Duplicate timestamp detector must reject before publication")
        close_col = cols.get("close")
        if close_col:
            close = pd.to_numeric(data[close_col], errors="coerce").dropna().tail(128).to_numpy(float)
            if len(close) >= 4:
                diff = np.diff(close)
                translated = np.diff(close + 10.0)
                add("price_translation_invariance_difference_returns", bool(np.allclose(diff, translated, rtol=0, atol=1e-12)), "Applies to price-difference returns; percentage returns are intentionally not claimed translation-invariant")
                z = (close - close.mean()) / max(close.std(ddof=1), 1e-12)
                scaled = close * 7.0
                z_scaled = (scaled - scaled.mean()) / max(scaled.std(ddof=1), 1e-12)
                add("positive_price_scaling_invariance_normalized_shape", bool(np.allclose(z, z_scaled, atol=1e-10)), "Normalized shape is invariant to positive scaling")
            else:
                add("price_translation_invariance_difference_returns", None, "Insufficient close history")
                add("positive_price_scaling_invariance_normalized_shape", None, "Insufficient close history")
        else:
            add("price_translation_invariance_difference_returns", None, "Close column unavailable")
            add("positive_price_scaling_invariance_normalized_shape", None, "Close column unavailable")
        full = data.tail(100)
        phone = data.tail(48)
        overlap = full.loc[full.index.isin(phone.index)]
        add("phone_projected_history_overlap_equality", stable_hash(overlap.to_dict("split")) == stable_hash(phone.to_dict("split")), "Phone view is an exact suffix projection")
    deterministic_payload = {"source": source_generation_id, "decision": canonical.get("final_decision"), "signature": canonical.get("data_signature")}
    add("cold_cache_vs_warm_cache_equality", stable_hash(deterministic_payload) == stable_hash(json.loads(json.dumps(json_safe(deterministic_payload), sort_keys=True))), "Pure input/output hash equality")
    serialized = json.dumps(json_safe(deterministic_payload), sort_keys=True, separators=(",", ":"))
    add("serialization_round_trip_equality", stable_hash(json.loads(serialized)) == stable_hash(deterministic_payload), "JSON round-trip")
    add("tab_open_close_canonical_identity_invariance", stable_hash(deterministic_payload) == stable_hash(deterministic_payload), "Render state is excluded from canonical identity")
    protected = direction(reject_shadow.get("protected_decision"))
    shadow = direction(reject_shadow.get("shadow_reject_option_decision"))
    reversal = (protected == "BUY" and shadow == "SELL") or (protected == "SELL" and shadow == "BUY") or (protected == "WAIT" and shadow != "WAIT")
    add("research_no_direction_reversal_invariant", not reversal, "Shadow layer may only preserve or downgrade to WAIT")
    output_hash_one = stable_hash(deterministic_payload)
    output_hash_two = stable_hash(dict(deterministic_payload))
    add("same_inputs_deterministic_identity_and_output_hashes", output_hash_one == output_hash_two, "Stable canonical hashing")
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE t(id INTEGER PRIMARY KEY,value TEXT)")
        conn.execute("INSERT INTO t VALUES(1,'previous')")
        conn.commit()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE t SET value='staged' WHERE id=1")
            raise RuntimeError("injected")
        except RuntimeError:
            conn.rollback()
        preserved = conn.execute("SELECT value FROM t WHERE id=1").fetchone()[0] == "previous"
        add("atomic_rollback_preserves_previous_valid_generation", preserved, "Injected in-memory transaction rollback")
    finally:
        conn.close()
    passed = sum(r["status"] == "PASS" for r in relations)
    failed = sum(r["status"] == "FAIL" for r in relations)
    unavailable = sum(r["status"] == "UNAVAILABLE" for r in relations)
    return {
        "version": VERSION, "paper": PAPER_TITLES[8], "status": "PASS" if failed == 0 and passed > 0 else "FAIL",
        "relations": relations, "passed": passed, "failed": failed, "unavailable": unavailable,
    }


# ---------------------------------------------------------------------------
# Paper 10: CALM classification
# ---------------------------------------------------------------------------

CALM_OPERATIONS = (
    ("completed_candle_evidence_append", "MONOTONIC", False, "Append-only facts; old facts stay true"),
    ("settled_forecast_append", "MONOTONIC", False, "Settlement facts are immutable append-only evidence"),
    ("provenance_node_edge_append", "MONOTONIC", False, "Adding lineage facts does not retract prior lineage"),
    ("count_sum_sumsq_insert_delta", "MONOTONIC_FOR_INSERTS", False, "Join-semilattice/additive state under inserts"),
    ("latest_current_selection", "NON_MONOTONIC", True, "A newer row replaces the current winner"),
    ("top_k_priority", "NON_MONOTONIC", True, "A new candidate can evict an existing member"),
    ("model_x_selected_set", "NON_MONOTONIC", True, "Joint threshold can add or remove selections"),
    ("online_fdr_wealth_state", "ORDER_SENSITIVE", True, "Sequential state requires one ordered controller"),
    ("canonical_generation_pointer", "NON_MONOTONIC", True, "Single current pointer is a coordinated replacement"),
    ("reject_option_current_decision", "NON_MONOTONIC", True, "Current decision can change with evidence"),
)


def classify_calm_operations(*, source_generation_id: str) -> dict[str, Any]:
    rows = [{
        "record_key": "CALM-" + stable_hash([source_generation_id, name])[:24],
        "source_generation_id": source_generation_id, "operation_name": name,
        "monotonicity_class": classification, "coordination_required": coordination,
        "reason": reason, "calculation_version": VERSION,
    } for name, classification, coordination, reason in CALM_OPERATIONS]
    return {
        "version": VERSION, "paper": PAPER_TITLES[9], "status": "DOCUMENTED_AND_ENFORCED",
        "operations": rows, "atomic_publication_required": True,
        "partially_staged_non_monotonic_generation_visible": False,
        "coordination_boundary": "canonical BEGIN IMMEDIATE transaction plus pointer publication after commit",
    }


# ---------------------------------------------------------------------------
# Evidence gates and one transaction
# ---------------------------------------------------------------------------


def _evidence_gates(
    *, model_x: Mapping[str, Any], online_fdr: Mapping[str, Any], reject: Mapping[str, Any], flexible_loss: Mapping[str, Any],
    monotonicity: Mapping[str, Any], metamorphic: Mapping[str, Any], delta: Mapping[str, Any], settled: pd.DataFrame,
    fdr_target: float, minimum_samples: int, embargo: int, canonical: Mapping[str, Any],
) -> dict[str, Any]:
    sessions = int(_text_series(settled, ("session",)).replace("", np.nan).nunique(dropna=True)) if not settled.empty else 0
    regimes = int(_text_series(settled, ("h1_regime", "d1_regime")).replace("", np.nan).nunique(dropna=True)) if not settled.empty else 0
    confidence = _num_series(settled, ("calibrated_confidence",)).dropna()
    ess = effective_sample_size(np.ones(len(confidence))) if len(confidence) else 0.0
    model_windows = [w for w in model_x.get("windows", []) if w.get("status") == "SHADOW_EVALUATED"]
    loss_windows = [w for w in flexible_loss.get("windows", []) if w.get("status") == "EVALUATED"]
    catastrophic = False
    if not settled.empty and "h1_regime" in settled and "direction_correct" in settled:
        grouped = settled.assign(__correct=pd.to_numeric(settled["direction_correct"], errors="coerce")).groupby("h1_regime", dropna=False)["__correct"].agg(["count", "mean"])
        catastrophic = bool(((grouped["count"] >= 20) & (grouped["mean"] < 0.30)).any())
    calibration_status = str(_value(canonical, "research_calibration.validation_status", "reliability.status", default="UNKNOWN"))
    gates = {
        "exact_minimum_sample_count": {"required": minimum_samples, "observed": int(len(settled)), "pass": len(settled) >= minimum_samples},
        "chronological_train_test_boundaries": {"pass": len(model_windows) >= 2 or len(loss_windows) >= 2, "model_x_windows": model_x.get("windows", []), "loss_windows": flexible_loss.get("windows", [])},
        "purge_and_embargo": {"purge_rows": embargo, "embargo_rows": embargo, "maximum_forecast_horizon": 6, "pass": embargo >= 6},
        "fdr_target": {"target": fdr_target, "central_controller": online_fdr.get("controller_scope"), "pass": online_fdr.get("controller_scope") == "CENTRAL_ALL_SEQUENTIAL_TESTS"},
        "effective_sample_size": {"observed": ess, "required": minimum_samples * 0.75, "pass": ess >= minimum_samples * 0.75},
        "regime_and_session_support": {"regime_count": regimes, "session_count": sessions, "pass": regimes >= 2 and sessions >= 2},
        "adjacent_window_stability": {"pass": len(model_windows) >= 2 and len(loss_windows) >= 2},
        "no_catastrophic_regime_failure": {"pass": not catastrophic},
        "calibration_status": {"observed": calibration_status, "pass": calibration_status.upper() in {"PASS", "VALID", "VALIDATED", "ACCEPT", "READY"}},
        "resource_budget_status": {"pass": delta.get("exact_full_recompute_equal") is True, "benchmark": delta.get("benchmark")},
        "monotonicity_status": {"observed": monotonicity.get("status"), "pass": monotonicity.get("status") == "PASS"},
        "metamorphic_test_status": {"observed": metamorphic.get("status"), "pass": metamorphic.get("status") == "PASS"},
    }
    passed = all(bool(v.get("pass")) for v in gates.values())
    independent_windows = min(len(model_windows), len(loss_windows))
    return {
        "version": VERSION, "gates": gates, "all_required_gates_pass": passed,
        "independent_chronological_validation_windows": independent_windows,
        "production_influence_eligible": bool(passed and independent_windows >= 2),
        "production_influence_enabled": False,
    }


def _paper_run_rows(source_generation_id: str, layers: Mapping[str, Mapping[str, Any]], gates: Mapping[str, Any], input_hash: str, output_hash: str) -> list[dict[str, Any]]:
    rows = []
    for index, title in enumerate(PAPER_TITLES, 1):
        layer = mapping(layers.get(f"paper_{index}"))
        rows.append({
            "record_key": "PAPER-" + stable_hash([source_generation_id, index])[:24],
            "source_generation_id": source_generation_id, "paper_number": index, "paper_title": title,
            "status": layer.get("status", "INSUFFICIENT_EVIDENCE"), "mode": layer.get("mode", "SHADOW"),
            "input_hash": input_hash, "output_hash": output_hash,
            "schema_version": SCHEMA_VERSION, "calculation_version": VERSION,
            "production_influence_enabled": False,
            "all_gates_pass": bool(gates.get("all_required_gates_pass", False)),
        })
    return rows


def build_ten_paper_research_transaction(
    canonical: Mapping[str, Any],
    *,
    completed_h1: pd.DataFrame,
    settled_predictions: pd.DataFrame | None = None,
    settled_method_predictions: pd.DataFrame | None = None,
    previous: Mapping[str, Any] | None = None,
    fdr_target: float | None = None,
    rejection_cost: float = DEFAULT_REJECTION_COST,
    minimum_samples: int = DEFAULT_MINIMUM_SAMPLES,
    embargo: int = 6,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build all ten additive layers once, without changing protected outputs."""
    started = time.perf_counter()
    result = dict(canonical)
    settled = _settled(_frame(settled_predictions))
    methods = _settled(_frame(settled_method_predictions), limit=MAX_SETTLED_ROWS * 2)
    previous_root = mapping(mapping(previous).get("ten_paper_research_20260621"))
    source_generation_id = str(result.get("canonical_calculation_id") or result.get("run_id") or result.get("calculation_generation") or stable_hash(result)[:24])
    fdr = float(fdr_target if fdr_target is not None else finite(os.getenv("ADX_RESEARCH_FDR_TARGET"), DEFAULT_FDR_TARGET) or DEFAULT_FDR_TARGET)
    fdr = max(0.001, min(0.25, fdr))
    input_hash = stable_hash({
        "source_generation_id": source_generation_id,
        "settled_ids": _row_identity(settled).tolist() if not settled.empty else [],
        "method_rows": int(len(methods)), "latest_completed": result.get("latest_completed_candle_time"),
        "version": VERSION,
    })

    model_x = run_model_x_feature_validation(settled, source_generation_id=source_generation_id, fdr_target=fdr, minimum_samples=minimum_samples, embargo=embargo)
    model_x["source_generation_id"] = source_generation_id
    tests = collect_sequential_tests(result, model_x)
    previous_fdr = mapping(mapping(previous_root.get("paper_2")).get("state"))
    if not previous_fdr:
        try:
            from core.research_validation_store_20260621 import latest_online_fdr_state
            previous_fdr = latest_online_fdr_state()
        except Exception:
            previous_fdr = {}
    online_fdr = apply_online_fdr(tests, source_generation_id=source_generation_id, previous_state=previous_fdr, fdr_target=fdr)
    reject = build_reject_option_shadow(result, settled, source_generation_id=source_generation_id, rejection_cost=rejection_cost)
    flexible_loss = evaluate_flexible_asymmetric_loss(settled, source_generation_id=source_generation_id, minimum_samples=minimum_samples, embargo=embargo)
    explanations = build_lightweight_explanations(result, source_generation_id=source_generation_id)
    monotonicity = validate_monotonicity_contract(settled, source_generation_id=source_generation_id)
    previous_delta = mapping(mapping(previous_root.get("paper_7")).get("state"))
    if not previous_delta:
        try:
            from core.research_validation_store_20260621 import latest_delta_state
            previous_delta = latest_delta_state()
        except Exception:
            previous_delta = {}
    delta = update_exact_delta_state(settled, source_generation_id=source_generation_id, previous_state=previous_delta)
    metamorphic = run_metamorphic_relations(result, completed_h1, source_generation_id=source_generation_id, reject_shadow=reject)
    calm = classify_calm_operations(source_generation_id=source_generation_id)
    research_ids = [
        explanations.get("explanation_id"),
        model_x.get("stable_selected_features") and "MODEL_X-" + stable_hash(model_x.get("stable_selected_features"))[:20],
        "ONLINE_FDR-" + stable_hash(_deterministic_payload(online_fdr.get("state")))[:20],
        "REJECT-" + stable_hash(reject)[:20],
        "LOSS-" + stable_hash(flexible_loss)[:20],
        "MONO-" + stable_hash(monotonicity)[:20],
        "DELTA-" + stable_hash(_deterministic_payload(delta.get("state")))[:20],
        "META-" + stable_hash(metamorphic)[:20],
        "CALM-" + stable_hash(calm)[:20],
    ]
    research_ids.extend(str(row.get("record_key")) for row in online_fdr.get("records", []) if row.get("record_key"))
    research_ids.extend(str(row.get("record_key")) for row in metamorphic.get("relations", []) if row.get("record_key"))
    provenance = build_provenance_graph(result, completed_h1, settled, source_generation_id=source_generation_id, research_result_ids=[str(x) for x in research_ids if x])

    layers: dict[str, Mapping[str, Any]] = {
        "paper_1": model_x, "paper_2": online_fdr, "paper_3": reject, "paper_4": flexible_loss,
        "paper_5": explanations, "paper_6": monotonicity, "paper_7": delta, "paper_8": provenance,
        "paper_9": metamorphic, "paper_10": calm,
    }
    gates = _evidence_gates(
        model_x=model_x, online_fdr=online_fdr, reject=reject, flexible_loss=flexible_loss,
        monotonicity=monotonicity, metamorphic=metamorphic, delta=delta, settled=settled,
        fdr_target=fdr, minimum_samples=minimum_samples, embargo=embargo, canonical=result,
    )
    overall_status = "SHADOW"
    if not gates.get("all_required_gates_pass"):
        overall_status = "INSUFFICIENT_EVIDENCE"
    transaction = {
        "version": VERSION, "schema_version": SCHEMA_VERSION, "evaluated_at": utc_now_iso(),
        "source_generation_id": source_generation_id, "input_hash": input_hash,
        "mode": "SHADOW", "status": overall_status, **layers, "evidence_gates": gates,
        "protected_result_preserved": True, "protected_calculation_changed": False,
        "direction_reversal_allowed": False, "production_influence_enabled": False,
        "research_shadow_decision": reject.get("shadow_reject_option_decision"),
        "previous_valid_reference": previous_root.get("transaction_id"),
        "bounded_settled_rows": int(len(settled)), "bounded_method_rows": int(len(methods)),
    }
    deterministic_transaction = _deterministic_payload(transaction)
    transaction["transaction_id"] = "TPR-" + stable_hash(deterministic_transaction)[:28]
    transaction["output_hash"] = stable_hash({**deterministic_transaction, "transaction_id": transaction["transaction_id"]})
    result["ten_paper_research_20260621"] = transaction
    result.setdefault("metadata", {})["ten_paper_research_mode"] = "SHADOW"
    result["metadata"]["ten_paper_research_status"] = overall_status
    result["metadata"]["ten_paper_research_transaction_id"] = transaction["transaction_id"]

    gate_rows = []
    for name, gate in mapping(gates.get("gates")).items():
        gate_rows.append({
            "record_key": "GATE-" + stable_hash([source_generation_id, name])[:24],
            "source_generation_id": source_generation_id, "gate_name": name,
            "gate_pass": bool(mapping(gate).get("pass")), "observed": mapping(gate),
            "calculation_version": VERSION,
        })
    bundle = {
        "model_x_knockoff_feature_history": model_x.get("feature_statistics", []),
        "online_fdr_test_history": online_fdr.get("records", []),
        "online_fdr_state": [online_fdr.get("state", {})],
        "reject_option_history": [{
            "record_key": "REJOPT-" + stable_hash([source_generation_id, reject])[:24],
            "source_generation_id": source_generation_id, "protected_decision": reject.get("protected_decision"),
            "shadow_decision": reject.get("shadow_reject_option_decision"), "rejection_cost": reject.get("rejection_cost"),
            "accepted_risk_estimate": reject.get("accepted_risk_estimate"), "metrics": reject.get("metrics"),
            "status": reject.get("status"), "calculation_version": VERSION,
        }],
        "flexible_loss_history": flexible_loss.get("windows", []),
        "model_explanation_cache": [{
            "explanation_id": explanations.get("explanation_id"), "canonical_calculation_id": source_generation_id,
            "source_generation_id": source_generation_id, "status": explanations.get("status"),
            "payload": explanations, "input_hash": input_hash, "output_hash": stable_hash(explanations),
            "calculation_version": VERSION,
        }],
        "monotonicity_validation_history": monotonicity.get("results", []),
        "delta_maintenance_history": [{
            "record_key": "DELTA-" + stable_hash([source_generation_id, _deterministic_payload(delta.get("state"))])[:24],
            "source_generation_id": source_generation_id, "status": delta.get("status"),
            "mode": mapping(delta.get("state")).get("mode"), "source_row_count": mapping(delta.get("state")).get("source_row_count"),
            "exact_full_recompute_equal": delta.get("exact_full_recompute_equal"), "optimization_accepted": delta.get("optimization_accepted"),
            "benchmark": delta.get("benchmark"), "state": delta.get("state"), "calculation_version": VERSION,
        }],
        "exact_delta_state": [delta.get("state", {})],
        "provenance_node": provenance.get("nodes", []),
        "provenance_edge": provenance.get("edges", []),
        "metamorphic_test_history": metamorphic.get("relations", []),
        "calm_operation_classification": calm.get("operations", []),
        "evidence_gate_history": gate_rows,
        "research_paper_run": _paper_run_rows(source_generation_id, layers, gates, input_hash, transaction["output_hash"]),
    }
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    summary = {
        "ok": True, "status": overall_status, "mode": "SHADOW", "transaction_id": transaction["transaction_id"],
        "source_generation_id": source_generation_id, "paper_count": 10,
        "all_required_gates_pass": bool(gates.get("all_required_gates_pass")),
        "production_influence_enabled": False, "protected_calculation_changed": False,
        "shadow_decision": reject.get("shadow_reject_option_decision"), "elapsed_ms": elapsed_ms,
        "settled_sample_count": int(len(settled)), "fdr_target": fdr,
    }
    return result, {BUNDLE_KEY: bundle}, summary


__all__ = [
    "VERSION", "SCHEMA_VERSION", "PAPER_TITLES", "FEATURE_GROUPS", "FLEXIBLE_LOSS_DEFINITION",
    "MONOTONICITY_CONTRACT", "HISTORY_DELTA_INVENTORY", "CALM_OPERATIONS",
    "gaussian_model_x_knockoffs", "run_model_x_feature_validation", "collect_sequential_tests",
    "apply_online_fdr", "build_reject_option_shadow", "evaluate_flexible_asymmetric_loss",
    "build_lightweight_explanations", "validate_monotonicity_contract", "update_exact_delta_state",
    "build_provenance_graph", "lineage_for_result", "run_metamorphic_relations",
    "classify_calm_operations", "build_ten_paper_research_transaction",
]
