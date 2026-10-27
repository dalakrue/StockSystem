"""Pesaran-Timmermann direction-skill tests for settled chronological forecasts."""
from __future__ import annotations

from typing import Any, Mapping
import math

import numpy as np
import pandas as pd

from core.quant_research_v4_contract_20260622 import common_result, unavailable

METHOD_ID = "PESARAN_TIMMERMANN_DIRECTION_TEST"
PAPER_TITLE = "A Simple Nonparametric Test of Predictive Performance"
PAPER_AUTHORS = "M. Hashem Pesaran and Allan Timmermann"


def _normal_sf(z: float) -> float:
    return float(0.5 * math.erfc(float(z) / math.sqrt(2.0)))


def pesaran_timmermann_test(predicted_direction: np.ndarray, actual_direction: np.ndarray) -> dict[str, Any]:
    pred = np.asarray(predicted_direction, dtype=float)
    actual = np.asarray(actual_direction, dtype=float)
    mask = np.isfinite(pred) & np.isfinite(actual) & np.isin(pred, [0, 1]) & np.isin(actual, [0, 1])
    pred, actual = pred[mask], actual[mask]
    n = len(pred)
    if n < 30 or min(int(pred.sum()), int(n - pred.sum()), int(actual.sum()), int(n - actual.sum())) < 5:
        return {"status": "NOT_TESTABLE", "sample_count": n}
    hit = float(np.mean(pred == actual))
    p_pred = float(np.mean(pred))
    p_actual = float(np.mean(actual))
    expected = p_pred * p_actual + (1.0 - p_pred) * (1.0 - p_actual)
    variance = (
        (2.0 * p_actual - 1.0) ** 2 * p_pred * (1.0 - p_pred)
        + (2.0 * p_pred - 1.0) ** 2 * p_actual * (1.0 - p_actual)
        + 4.0 * p_pred * p_actual * (1.0 - p_pred) * (1.0 - p_actual)
    ) / n
    if variance <= 1e-15:
        return {"status": "NOT_TESTABLE", "sample_count": n, "hit_rate": hit, "expected_hit_rate_under_independence": expected}
    statistic = float((hit - expected) / math.sqrt(variance))
    p_value = float(2.0 * _normal_sf(abs(statistic)))
    return {
        "status": "TESTABLE",
        "sample_count": n,
        "hit_rate": hit,
        "expected_hit_rate_under_independence": expected,
        "PT_statistic": statistic,
        "asymptotic_p_value": p_value,
    }


def moving_block_bootstrap_p_value(predicted: np.ndarray, actual: np.ndarray, *, replications: int = 500, block_length: int | None = None, seed: int = 20260622) -> tuple[float | None, int]:
    """Independence-null moving-block bootstrap with bounded vectorized batches.

    Prediction and actual-direction blocks are sampled independently, preserving
    serial dependence within each stream while removing contemporaneous skill.
    Vectorized batches avoid thousands of Python list allocations under the
    orchestrator's memory tracing.
    """
    pred = np.asarray(predicted, dtype=np.int8)
    act = np.asarray(actual, dtype=np.int8)
    n = len(pred)
    observed = pesaran_timmermann_test(pred, act)
    if observed.get("status") != "TESTABLE":
        return None, 0
    block = int(block_length or max(2, round(n ** (1.0 / 3.0))))
    reps = max(1, int(replications))
    rng = np.random.default_rng(seed)
    blocks_needed = int(math.ceil(n / block))
    offsets = np.arange(block, dtype=np.int64)
    observed_abs = abs(float(observed["PT_statistic"]))
    exceed = 0
    valid_count = 0
    batch_size = min(64, reps)
    for first in range(0, reps, batch_size):
        size = min(batch_size, reps - first)
        starts_p = rng.integers(0, n, size=(size, blocks_needed), dtype=np.int64)
        starts_a = rng.integers(0, n, size=(size, blocks_needed), dtype=np.int64)
        idx_p = ((starts_p[:, :, None] + offsets[None, None, :]) % n).reshape(size, -1)[:, :n]
        idx_a = ((starts_a[:, :, None] + offsets[None, None, :]) % n).reshape(size, -1)[:, :n]
        p_sample = pred[idx_p]
        a_sample = act[idx_a]
        p_pred = p_sample.mean(axis=1)
        p_actual = a_sample.mean(axis=1)
        hit = (p_sample == a_sample).mean(axis=1)
        expected = p_pred * p_actual + (1.0 - p_pred) * (1.0 - p_actual)
        variance = (
            (2.0 * p_actual - 1.0) ** 2 * p_pred * (1.0 - p_pred)
            + (2.0 * p_pred - 1.0) ** 2 * p_actual * (1.0 - p_actual)
            + 4.0 * p_pred * p_actual * (1.0 - p_pred) * (1.0 - p_actual)
        ) / n
        valid = variance > 1e-15
        if np.any(valid):
            stats = np.abs((hit[valid] - expected[valid]) / np.sqrt(variance[valid]))
            exceed += int(np.sum(stats >= observed_abs))
            valid_count += int(len(stats))
    if valid_count == 0:
        return None, block
    return float((1.0 + exceed) / (valid_count + 1.0)), block


def _direction_arrays(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    lower = {str(c).lower(): c for c in frame.columns}
    pred_col = next((lower[n] for n in ("predicted_direction", "direction", "forecast_direction", "directional_market_view") if n in lower), None)
    actual_col = next((lower[n] for n in ("actual_direction", "settled_direction", "target_direction") if n in lower), None)

    def _decode(series: pd.Series) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce")
        finite = numeric.dropna()
        if not finite.empty and finite.isin([-1, 0, 1]).all():
            # Both common encodings are accepted: {-1,+1} and {0,1}.
            if (finite < 0).any():
                return pd.Series(np.where(numeric > 0, 1.0, np.where(numeric < 0, 0.0, np.nan)), index=series.index)
            return numeric.where(numeric.isin([0, 1])).astype(float)
        text = series.astype(str).str.strip().str.upper()
        return text.map({
            "BUY": 1.0, "UP": 1.0, "BULL": 1.0, "LONG": 1.0, "1": 1.0, "+1": 1.0,
            "SELL": 0.0, "DOWN": 0.0, "BEAR": 0.0, "SHORT": 0.0, "-1": 0.0, "0": 0.0,
        })

    if pred_col is not None:
        pred = _decode(frame[pred_col])
    else:
        predicted_price = next((lower[n] for n in ("predicted_price", "forecast_price", "predicted_close") if n in lower), None)
        origin_price = next((lower[n] for n in ("current_price", "origin_close", "forecast_origin_close", "source_close") if n in lower), None)
        if predicted_price is not None and origin_price is not None:
            diff = pd.to_numeric(frame[predicted_price], errors="coerce") - pd.to_numeric(frame[origin_price], errors="coerce")
            pred = pd.Series(np.where(diff > 0, 1.0, np.where(diff < 0, 0.0, np.nan)), index=frame.index)
        else:
            pred = pd.Series(np.nan, index=frame.index)
    if actual_col is not None:
        actual = _decode(frame[actual_col])
    else:
        actual_price = next((lower[n] for n in ("actual_price", "actual_close", "target_price", "settled_price", "target_close") if n in lower), None)
        origin_price = next((lower[n] for n in ("current_price", "origin_close", "forecast_origin_close", "source_close") if n in lower), None)
        if actual_price is not None and origin_price is not None:
            diff = pd.to_numeric(frame[actual_price], errors="coerce") - pd.to_numeric(frame[origin_price], errors="coerce")
            actual = pd.Series(np.where(diff > 0, 1.0, np.where(diff < 0, 0.0, np.nan)), index=frame.index)
        else:
            actual = pd.Series(np.nan, index=frame.index)
    return pred, actual


def _session_from_time(values: pd.Series) -> pd.Series:
    ts = pd.to_datetime(values, errors="coerce", utc=True)
    hour = ts.dt.hour
    return pd.Series(np.select(
        [(hour >= 7) & (hour < 13), (hour >= 13) & (hour < 16), (hour >= 16) & (hour < 22)],
        ["LONDON", "OVERLAP", "NEW_YORK"], default="OTHER"), index=values.index)


def run_pesaran_timmermann(identity: Mapping[str, Any], settled: pd.DataFrame, *, bootstrap_replications: int = 500) -> dict[str, Any]:
    n = int(len(settled)) if isinstance(settled, pd.DataFrame) else 0
    minimum = 60
    try:
        if not isinstance(settled, pd.DataFrame) or settled.empty:
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="CHRONOLOGICAL_DIRECTION_TEST", sample_count=0, minimum_required_samples=minimum,
                status="INSUFFICIENT_EVIDENCE", limitations=["No settled direction outcomes were available."])
        pred, actual = _direction_arrays(settled)
        work = settled.copy()
        work["__pred"] = pred; work["__actual"] = actual
        if "horizon_hours" not in work.columns:
            work["horizon_hours"] = 1
        origin = work.get("__origin_time", work.get("created_at", pd.Series(pd.NaT, index=work.index)))
        work["__session"] = _session_from_time(origin)
        groups: dict[str, pd.Series] = {"OVERALL": pd.Series(True, index=work.index)}
        for horizon in (1, 2, 3, 6):
            groups[f"H{horizon}"] = pd.to_numeric(work["horizon_hours"], errors="coerce").fillna(-1).astype(int) == horizon
        for session in ("LONDON", "NEW_YORK", "OVERLAP"):
            groups[session] = work["__session"] == session
        if "major_regime" in work.columns:
            for regime in work["major_regime"].dropna().astype(str).value_counts().head(4).index:
                groups[f"REGIME:{regime}"] = work["major_regime"].astype(str) == regime
        results = {}
        for name, mask in groups.items():
            p = work.loc[mask, "__pred"].to_numpy(float)
            a = work.loc[mask, "__actual"].to_numpy(float)
            valid = np.isfinite(p) & np.isfinite(a)
            p, a = p[valid], a[valid]
            test = pesaran_timmermann_test(p, a)
            bootstrap_p, block = moving_block_bootstrap_p_value(p.astype(int), a.astype(int), replications=bootstrap_replications) if test.get("status") == "TESTABLE" else (None, 0)
            if test.get("status") == "TESTABLE":
                significant = test["asymptotic_p_value"] < 0.05 and (bootstrap_p is None or bootstrap_p < 0.05) and test["PT_statistic"] > 0
                test["block_bootstrap_p_value"] = bootstrap_p
                test["block_length"] = block
                test["direction_skill_status"] = "SIGNIFICANT_POSITIVE_SKILL" if significant else ("NO_SIGNIFICANT_SKILL" if test["PT_statistic"] >= 0 else "NEGATIVE_SKILL_WARNING")
            else:
                test["block_bootstrap_p_value"] = None
                test["direction_skill_status"] = "NOT_TESTABLE"
            results[name] = test
        overall = results["OVERALL"]
        status = "AVAILABLE" if overall.get("status") == "TESTABLE" else "INSUFFICIENT_EVIDENCE"
        return common_result(
            identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            exact_or_adaptation="DEPENDENCE_CONFIRMED_CHRONOLOGICAL_PT_TEST",
            sample_count=n, effective_sample_count=int(overall.get("sample_count") or 0), minimum_required_samples=minimum,
            status=status, score=overall.get("PT_statistic"), p_value=overall.get("block_bootstrap_p_value") or overall.get("asymptotic_p_value"),
            confidence=(1.0 - (overall.get("block_bootstrap_p_value") or overall.get("asymptotic_p_value"))) if overall.get("status") == "TESTABLE" else None,
            reliability=overall.get("direction_skill_status", "NOT_TESTABLE"),
            assumptions=["Predicted direction is recorded before the target close settles.", "Exact-zero price movements are excluded as neutral, never relabeled."],
            limitations=["PT tests directional association, not profitability or calibration.", "Moving-block bootstrap uses a deterministic seed and bounded replications."],
            hit_rate=overall.get("hit_rate"),
            expected_hit_rate_under_independence=overall.get("expected_hit_rate_under_independence"),
            PT_statistic=overall.get("PT_statistic"),
            asymptotic_p_value=overall.get("asymptotic_p_value"),
            block_bootstrap_p_value=overall.get("block_bootstrap_p_value"),
            direction_skill_status=overall.get("direction_skill_status", "NOT_TESTABLE"),
            tests=results,
            bootstrap_replications=int(bootstrap_replications),
            bootstrap_seed=20260622,
            neutral_policy="EXCLUDE_EXACT_ZERO_MOVEMENTS",
        )
    except Exception as exc:
        return unavailable(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            error=exc, minimum_required_samples=minimum, sample_count=n,
            limitations=["No directional skill is claimed when one class or settled support is insufficient."])


__all__ = ["run_pesaran_timmermann", "pesaran_timmermann_test", "moving_block_bootstrap_p_value"]
